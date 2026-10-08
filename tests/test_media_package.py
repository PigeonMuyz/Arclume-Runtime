"""Headless package tests for staged media runtime candidates.

Run: python3 -m unittest discover -s tests -p test_media_package.py -v
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    'package_media_runtime',
    Path(__file__).resolve().parents[1] / 'script/package-media-runtime.py')
package_media = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package_media
SPEC.loader.exec_module(package_media)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / 'work/build/runtime-staging.test/arclume-runtime-x86_64'
        (self.runtime / 'lib/wine/x86_64-unix').mkdir(parents=True)
        self.metadata = {
            'schemaVersion': 1,
            'id': 'io.arclume.runtime.wine',
            'displayName': 'Arclume Wine',
            'version': '1.2.3-media.1',
            'channel': 'prerelease',
        }
        (self.runtime / '.arclume-runtime.json').write_text(
            json.dumps(self.metadata, indent=2) + '\n', encoding='utf-8')
        self.payload = self.runtime / 'share/media/codec.bin'
        self.payload.parent.mkdir(parents=True)
        self.payload.write_bytes(bytes(range(256)) * 11)
        (self.runtime / '.hidden').write_text('include hidden files\n', encoding='utf-8')
        self.output_parent = self.root / 'dist'
        self.output_parent.mkdir()
        self.output = self.output_parent / 'arclume-wine-1.2.3-media.1-x86_64.tar.xz'
        self.manifest = self.output.with_name(
            self.output.name[:-len('.tar.xz')] + '.runtime.json')

    def test_archive_and_manifest_match_runtime_metadata(self):
        archive_path, manifest_path, digest = package_media.package(
            self.runtime, self.output, root=self.root)
        self.assertEqual(archive_path, self.output)
        self.assertEqual(manifest_path, self.manifest)
        with self.output.open('rb') as stream:
            self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), digest)
        with tarfile.open(self.output, mode='r:xz') as archive:
            self.assertIn(f'{self.runtime.name}/share/media/codec.bin', archive.getnames())
            self.assertIn(f'{self.runtime.name}/.hidden', archive.getnames())
            extracted = archive.extractfile(
                f'{self.runtime.name}/share/media/codec.bin').read()
            self.assertEqual(extracted, self.payload.read_bytes())
        result = json.loads(self.manifest.read_text(encoding='utf-8'))
        expected = dict(self.metadata)
        expected['archive'] = {
            'name': self.output.name,
            'sha256': digest,
            'rootDirectory': self.runtime.name,
        }
        self.assertEqual(result, expected)
        self.assertTrue((self.runtime / '.arclume-runtime.json').is_file())

    def test_existing_archive_or_manifest_is_never_overwritten(self):
        for occupied in (self.output, self.manifest):
            with self.subTest(occupied=occupied.name):
                occupied.write_text('preserve this candidate\n', encoding='utf-8')
                before = occupied.read_bytes()
                with self.assertRaises(FileExistsError):
                    package_media.package(self.runtime, self.output, root=self.root)
                self.assertEqual(occupied.read_bytes(), before)
                other = self.manifest if occupied == self.output else self.output
                self.assertFalse(os.path.lexists(other))
                occupied.unlink()

    def test_dangling_archive_symlink_is_a_collision(self):
        target = self.root / 'not-created'
        self.output.symlink_to(target)
        with self.assertRaises(FileExistsError):
            package_media.package(self.runtime, self.output, root=self.root)
        self.assertTrue(self.output.is_symlink())
        self.assertFalse(target.exists())
        self.assertFalse(os.path.lexists(self.manifest))

    def test_archive_creation_failure_leaves_no_final_artifacts(self):
        with mock.patch.object(package_media, '_create_archive',
                               side_effect=OSError('simulated tar failure')):
            with self.assertRaisesRegex(OSError, 'simulated tar failure'):
                package_media.package(self.runtime, self.output, root=self.root)
        self.assertFalse(os.path.lexists(self.output))
        self.assertFalse(os.path.lexists(self.manifest))
        self.assertEqual(list(self.output_parent.iterdir()), [])

    def test_manifest_collision_during_publication_preserves_raced_file(self):
        publish = package_media._publish_no_clobber

        def race_on_manifest(source, destination):
            if destination == self.manifest:
                destination.write_text('created by another publisher\n', encoding='utf-8')
            return publish(source, destination)

        with mock.patch.object(package_media, '_publish_no_clobber',
                               side_effect=race_on_manifest):
            with self.assertRaises(FileExistsError):
                package_media.package(self.runtime, self.output, root=self.root)
        self.assertFalse(os.path.lexists(self.output))
        self.assertEqual(self.manifest.read_text(encoding='utf-8'),
                         'created by another publisher\n')
        self.assertEqual(list(self.output_parent.iterdir()), [self.manifest])

    def test_invalid_metadata_is_rejected_before_publication(self):
        (self.runtime / '.arclume-runtime.json').write_text(
            '{"schemaVersion": true, "id": "runtime", "version": "1"}\n',
            encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'schemaVersion'):
            package_media.package(self.runtime, self.output, root=self.root)
        self.assertFalse(os.path.lexists(self.output))
        self.assertFalse(os.path.lexists(self.manifest))

    def test_non_staging_path_and_user_prefix_are_rejected(self):
        other = self.root / 'Games/runtime'
        other.mkdir(parents=True)
        with self.assertRaises(ValueError):
            package_media.validate_runtime(other, self.root)
        (self.runtime / 'system.reg').touch()
        with self.assertRaisesRegex(ValueError, 'user prefixes'):
            package_media.package(self.runtime, self.output, root=self.root)

    def test_output_inside_runtime_is_rejected_without_changing_input(self):
        inside = self.runtime / 'candidate.tar.xz'
        before = sorted(str(path.relative_to(self.runtime)) for path in self.runtime.rglob('*'))
        with self.assertRaisesRegex(ValueError, 'cannot be inside'):
            package_media.package(self.runtime, inside, root=self.root)
        after = sorted(str(path.relative_to(self.runtime)) for path in self.runtime.rglob('*'))
        self.assertEqual(after, before)
        self.assertFalse(os.path.lexists(inside))


if __name__ == '__main__':
    unittest.main()
