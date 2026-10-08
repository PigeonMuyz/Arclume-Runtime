"""Focused safety and native relocation tests; no Wine prefix or GUI needed.

Run: python3 -m unittest discover -s tests -p test_stage_media.py -v
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    'stage_media', Path(__file__).resolve().parents[1] / 'script/stage-media.py')
media = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = media
SPEC.loader.exec_module(media)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / 'work/build/runtime-staging.test/runtime'
        (self.runtime / 'lib/wine/x86_64-unix').mkdir(parents=True)

    def test_only_staging_targets_accepted(self):
        self.assertEqual(media.validate_runtime(self.runtime, self.root), self.runtime)
        for name in ('Games/runtime', 'work/build/wine-wow64', 'work/build/runtime-staging.'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                media.validate_runtime(self.root / name, self.root)

    def test_user_prefix_rejected(self):
        (self.runtime / 'system.reg').touch()
        with self.assertRaisesRegex(ValueError, 'user prefixes'):
            media.validate_runtime(self.runtime, self.root)

    def test_symlink_escape_rejected(self):
        link = self.root / 'work/build/runtime-staging.link'
        link.symlink_to(self.runtime.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            media.validate_runtime(link / 'runtime', self.root)

    def test_host_and_missing_dependencies_rejected(self):
        binary = self.runtime / 'bin/tool'
        for dep in ('/opt/homebrew/lib/libfoo.dylib', '/usr/local/lib/libfoo.dylib',
                    '@loader_path/../../../../outside.dylib', '@rpath/missing.dylib'):
            with self.subTest(dep=dep), self.assertRaises(ValueError):
                media.check_reference(dep, binary, self.runtime, set())
        media.check_reference('/usr/lib/libSystem.B.dylib', binary, self.runtime, set())

    def test_non_x86_binary_rejected(self):
        with mock.patch.object(media, 'macho', return_value=True), \
                mock.patch.object(media, 'command', return_value='arm64'), \
                self.assertRaisesRegex(ValueError, 'x86_64'):
            media.inspect(self.runtime / 'fake')

    def test_nonportable_rpath_rejected(self):
        for rpath in ('/opt/homebrew/lib', '@loader_path/../../../../outside', 'lib'):
            with self.subTest(rpath=rpath), self.assertRaises(ValueError):
                media.check_rpath(rpath, self.runtime / 'bin/tool', self.runtime)
        media.check_rpath('@loader_path/../lib64', self.runtime / 'bin/tool', self.runtime)


@unittest.skipUnless(platform.system() == 'Darwin' and shutil.which('clang'),
                     'Native Mach-O relocation requires macOS and clang')
class NativeTests(unittest.TestCase):
    def setUp(self):
        SafetyTests.setUp(self)
        self.sdk = self.root / 'sdk'
        for directory in ('lib/gstreamer-1.0', 'bin', 'libexec/gstreamer-1.0',
                          'share/arclume-media/licenses/test'):
            (self.sdk / directory).mkdir(parents=True)
        (self.sdk / 'share/arclume-media/MEDIA_SOURCES.json').write_text('{}\n')
        (self.sdk / 'share/arclume-media/licenses/test/LICENSE').write_text('Test fixture\n')
        self.library = self.sdk / 'lib/libfixture.1.dylib'
        self.compile(self.library, 'int answer(void) { return 42; }', dynamic=True)
        (self.sdk / 'lib/libfixture.dylib').symlink_to(self.library.name)
        plugin = self.sdk / 'lib/gstreamer-1.0/libgstfixture.dylib'
        self.compile(plugin, 'extern int answer(void); int plugin(void) { return answer(); }',
                     dynamic=True, link=True)
        executable = self.sdk / 'bin/ffmpeg'
        self.compile(executable, 'extern int answer(void); int main(void) { return answer() != 42; }',
                     link=True)
        for name in media.TOOLS:
            if name != 'ffmpeg':
                shutil.copy2(executable, self.sdk / 'bin' / name)
        shutil.copy2(executable, self.sdk / 'libexec/gstreamer-1.0/gst-plugin-scanner')
        self.wine = self.runtime / 'lib/wine/x86_64-unix/winegstreamer.so'
        self.compile(self.wine, 'extern int answer(void); int wine(void) { return answer(); }',
                     dynamic=True, link=True)
        self.unrelated = self.runtime / 'lib64/libbaseline.dylib'
        self.unrelated.parent.mkdir()
        self.compile(self.unrelated, 'int baseline(void) { return 7; }', dynamic=True)

    def compile(self, destination, source, dynamic=False, link=False):
        args = ['/usr/bin/clang', '-arch', 'x86_64', '-x', 'c', '-',
                '-Wl,-headerpad_max_install_names', '-o', str(destination)]
        if dynamic:
            args += ['-dynamiclib', '-Wl,-install_name,' + str(destination)]
        if link:
            args += ['-L' + str(self.sdk / 'lib'), '-lfixture', '-Wl,-rpath,' + str(self.sdk / 'lib')]
        subprocess.run(args, input=source, text=True, check=True, capture_output=True)

    def test_relocation_signing_and_baseline_preservation(self):
        baseline_hash = hashlib.sha256(self.unrelated.read_bytes()).hexdigest()
        media.stage(self.sdk, self.runtime, root=self.root)
        self.assertEqual(hashlib.sha256(self.unrelated.read_bytes()).hexdigest(), baseline_hash)
        self.assertEqual(os.readlink(self.runtime / 'lib64/gstreamer-1.0'), '../lib/gstreamer-1.0')
        self.assertEqual(os.readlink(self.runtime / 'lib64/libfixture.dylib'), 'libfixture.1.dylib')
        info = media.inspect(self.wine)
        self.assertIn('@loader_path/../../../lib64/libfixture.1.dylib', info.dependencies)
        self.assertFalse(info.rpaths)
        self.sdk.rename(self.root / 'sdk-hidden')
        moved = self.root / 'relocated runtime'
        self.runtime.rename(moved)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DYLD_', 'GST_'))}
        subprocess.run(['/usr/bin/arch', '-x86_64', str(moved / 'bin/ffmpeg')],
                       env=env, check=True, capture_output=True)
        self.assertTrue((moved / 'share/arclume-media/licenses/test/LICENSE').is_file())
        for relative in ('bin/ffmpeg', 'lib64/libfixture.1.dylib',
                         'lib/wine/x86_64-unix/winegstreamer.so'):
            media.command(['/usr/bin/codesign', '--verify', '--strict', moved / relative])

    def test_dry_run_leaves_tree_unchanged(self):
        before = {str(p.relative_to(self.runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.runtime.rglob('*') if p.is_file()}
        media.stage(self.sdk, self.runtime, dry_run=True, root=self.root)
        after = {str(p.relative_to(self.runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.runtime.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_collision_rejected_before_editing(self):
        (self.runtime / 'lib64/libfixture.1.dylib').write_text('keep me')
        before = self.wine.read_bytes()
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            media.stage(self.sdk, self.runtime, root=self.root)
        self.assertEqual(self.wine.read_bytes(), before)

    def test_external_sdk_symlink_rejected(self):
        (self.sdk / 'lib/libescape.dylib').symlink_to(self.unrelated)
        with self.assertRaisesRegex(ValueError, 'escaping symlink'):
            media.stage(self.sdk, self.runtime, root=self.root)
        self.assertFalse((self.runtime / 'bin/ffmpeg').exists())

    def test_host_dependency_rejected_before_copy(self):
        media.command(['/usr/bin/install_name_tool', '-change', str(self.library),
                       '/opt/homebrew/lib/libfixture.1.dylib', self.wine])
        with self.assertRaisesRegex(ValueError, 'host dependency'):
            media.stage(self.sdk, self.runtime, root=self.root)
        self.assertFalse((self.runtime / 'bin/ffmpeg').exists())

    def test_hardlinked_wine_module_rejected_before_edit(self):
        copy = self.root / 'shared-wine.so'
        os.link(self.wine, copy)
        original = copy.read_bytes()
        with self.assertRaisesRegex(ValueError, 'hard-linked'):
            media.stage(self.sdk, self.runtime, root=self.root)
        self.assertEqual(copy.read_bytes(), original)
        self.assertFalse((self.runtime / 'bin/ffmpeg').exists())

    def require_proxy_license(self):
        (self.sdk / 'share/arclume-media/MEDIA_SOURCES.json').write_text(
            '{"dependencies": [{"id": "proxy-libintl", "version": "0.5"}]}\n')

    def test_proxy_license_recovered_from_adjacent_source(self):
        self.require_proxy_license()
        source = self.sdk.parent / 'proxy-libintl-src'
        source.mkdir()
        (source / 'COPYING').write_text('Proxy fixture license\n')
        media.stage(self.sdk, self.runtime, root=self.root)
        notice = self.runtime / 'share/arclume-media/licenses/proxy-libintl/COPYING'
        self.assertEqual(notice.read_text(), 'Proxy fixture license\n')
        self.assertFalse((self.sdk / 'share/arclume-media/licenses/proxy-libintl').exists())

    def test_proxy_license_missing_fails_before_copy(self):
        self.require_proxy_license()
        with self.assertRaisesRegex(ValueError, 'proxy-libintl license missing'):
            media.stage(self.sdk, self.runtime, root=self.root)
        self.assertFalse((self.runtime / 'bin/ffmpeg').exists())

    def test_proxy_license_already_in_sdk_needs_no_source(self):
        self.require_proxy_license()
        notices = self.sdk / 'share/arclume-media/licenses/proxy-libintl'
        notices.mkdir()
        (notices / 'LICENSE').write_text('Already installed license\n')
        files, _ = media.collect_sdk(self.sdk, self.runtime)
        self.assertEqual(files[notices / 'LICENSE'],
                         self.runtime / 'share/arclume-media/licenses/proxy-libintl/LICENSE')


if __name__ == '__main__':
    unittest.main()
