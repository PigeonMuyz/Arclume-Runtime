import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / 'script' / 'build-media.py'
SPEC = importlib.util.spec_from_file_location('build_media', SCRIPT_PATH)
BUILD_MEDIA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_MEDIA)


def dependency(data=b'pinned media archive', url='https://example.invalid/source.tar.gz'):
    return {
        'id': 'test-media',
        'archive': 'source.tar.gz',
        'url': url,
        'sha256': hashlib.sha256(data).hexdigest(),
    }


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.seed = self.root / 'seed'
        self.cache.mkdir()
        self.seed.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_cached_archive_is_reused(self):
        dep = dependency()
        cached = self.cache / dep['archive']
        cached.write_bytes(b'pinned media archive')

        with patch.object(BUILD_MEDIA, 'run') as run:
            result = BUILD_MEDIA.fetch(dep, self.cache)

        self.assertEqual(result, cached)
        run.assert_not_called()

    def test_invalid_download_hash_is_rejected_without_leaving_cache_entry(self):
        dep = dependency()

        def write_bad_download(args, **kwargs):
            Path(args[args.index('-o') + 1]).write_bytes(b'tampered archive')

        with patch.object(BUILD_MEDIA, 'run', side_effect=write_bad_download) as run:
            with self.assertRaisesRegex(ValueError, 'Source hash mismatch: test-media'):
                BUILD_MEDIA.fetch(dep, self.cache)

        run.assert_called_once()
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_invalid_cached_archive_is_rejected(self):
        dep = dependency()
        (self.cache / dep['archive']).write_bytes(b'tampered archive')

        with patch.object(BUILD_MEDIA, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Invalid cached source: test-media'):
                BUILD_MEDIA.fetch(dep, self.cache)

        run.assert_not_called()

    def test_symlink_in_cache_is_rejected_even_when_target_hash_matches(self):
        dep = dependency()
        target = self.root / dep['archive']
        target.write_bytes(b'pinned media archive')
        (self.cache / dep['archive']).symlink_to(target)

        with patch.object(BUILD_MEDIA, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Invalid cached source: test-media'):
                BUILD_MEDIA.fetch(dep, self.cache)

        run.assert_not_called()

    def test_non_https_source_is_rejected(self):
        dep = dependency(url='http://example.invalid/source.tar.gz')

        with patch.object(BUILD_MEDIA, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Only HTTPS sources are accepted'):
                BUILD_MEDIA.fetch(dep, self.cache)

        run.assert_not_called()
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_valid_seed_archive_is_copied_without_network(self):
        dep = dependency()
        seeded = self.seed / dep['archive']
        seeded.write_bytes(b'pinned media archive')

        with patch.object(BUILD_MEDIA, 'run') as run:
            result = BUILD_MEDIA.fetch(dep, self.cache, self.seed)

        self.assertEqual(result.read_bytes(), seeded.read_bytes())
        run.assert_not_called()

    def test_seed_with_wrong_hash_is_ignored_and_https_download_is_verified(self):
        dep = dependency()
        (self.seed / dep['archive']).write_bytes(b'tampered seed')

        def write_verified_download(args, **kwargs):
            Path(args[args.index('-o') + 1]).write_bytes(b'pinned media archive')

        with patch.object(BUILD_MEDIA, 'run', side_effect=write_verified_download) as run:
            result = BUILD_MEDIA.fetch(dep, self.cache, self.seed)

        self.assertEqual(result.read_bytes(), b'pinned media archive')
        run.assert_called_once()


class SourceLockTests(unittest.TestCase):
    def test_media_source_lock_has_unique_ids_archives_sha256_and_https_urls(self):
        lock = json.loads((ROOT / 'sources' / 'MEDIA_SOURCES.json').read_text())
        dependencies = lock['dependencies']

        self.assertTrue(dependencies)
        ids = [dep['id'] for dep in dependencies]
        archives = [dep['archive'] for dep in dependencies]
        self.assertEqual(len(ids), len(set(ids)), 'dependency ids must be unique')
        self.assertEqual(len(archives), len(set(archives)), 'archive names must be unique')

        for dep in dependencies:
            with self.subTest(dependency=dep.get('id')):
                self.assertRegex(dep['sha256'], re.compile(r'^[0-9a-f]{64}$'))
                self.assertTrue(dep['url'].startswith('https://'), dep['url'])


if __name__ == '__main__':
    unittest.main()
