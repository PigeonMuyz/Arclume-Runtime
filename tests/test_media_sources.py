"""Exercise corresponding-source packaging without network or user data."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'script/package-runtime-sources.sh'


class SourceBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('script', 'sources', 'patches', 'manifests', 'LICENSES',
                          'cache/media', 'work', 'dist'):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRIPT, self.root / 'script/package-runtime-sources.sh')
        (self.root / 'runtime.env').write_text('RUNTIME_VERSION="1.1.3"\n')
        (self.root / 'THIRD-PARTY-NOTICES.md').write_text('notices\n')
        (self.root / 'cache/wine.tar.gz').write_bytes(b'wine input')
        (self.root / 'cache/media/media.tar.xz').write_bytes(b'media input')
        (self.root / 'sources/WINE_SOURCE.lock').write_text(
            'SOURCE_ARCHIVE="wine.tar.gz"\nSOURCE_SHA256="' +
            hashlib.sha256(b'wine input').hexdigest() + '"\n')
        (self.root / 'sources/MEDIA_SOURCES.json').write_text(json.dumps({
            'dependencies': [{'archive': 'media.tar.xz',
                              'sha256': hashlib.sha256(b'media input').hexdigest()}]}))
        self.git('init', '-q')
        self.git('add', 'script', 'sources', 'runtime.env', 'THIRD-PARTY-NOTICES.md')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()

    def run_bundle(self):
        return subprocess.run(['bash', 'script/package-runtime-sources.sh', '--output',
                               'dist/sources.tar.gz'], cwd=self.root, capture_output=True)

    def test_includes_exact_commit_and_verified_sources_not_build_tree(self):
        (self.root / 'work/private-log').write_text('never publish')
        result = self.run_bundle()
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / 'dist/sources.tar.gz') as archive:
            base = 'arclume-wine-1.1.3-sources/'
            self.assertEqual(archive.extractfile(base + 'SOURCE_COMMIT').read().decode().strip(),
                             self.git('rev-parse', 'HEAD'))
            self.assertEqual(archive.extractfile(base + 'sources/upstream/media.tar.xz').read(),
                             b'media input')
            self.assertEqual(archive.extractfile(base + 'sources/upstream/wine.tar.gz').read(),
                             b'wine input')
            self.assertFalse(any('/work/' in n for n in archive.getnames()))

    def test_rejects_corrupt_cached_input(self):
        (self.root / 'cache/media/media.tar.xz').write_bytes(b'corrupt')
        self.assertNotEqual(self.run_bundle().returncode, 0)
        self.assertFalse((self.root / 'dist/sources.tar.gz').exists())

    def test_rejects_uncommitted_recipe(self):
        (self.root / 'runtime.env').write_text('RUNTIME_VERSION="1.1.4"\n')
        self.assertNotEqual(self.run_bundle().returncode, 0)

    def test_refuses_existing_output(self):
        output = self.root / 'dist/sources.tar.gz'
        output.write_bytes(b'keep')
        self.assertNotEqual(self.run_bundle().returncode, 0)
        self.assertEqual(output.read_bytes(), b'keep')
