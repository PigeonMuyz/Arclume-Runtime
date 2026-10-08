"""Exercise the actual inline Wine configure fingerprint without building Wine."""
import contextlib
import io
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch


BUILD = Path(__file__).resolve().parents[1] / 'script/build-runtime.sh'
FINGERPRINT = re.search(
    r"wine_configuration=.*?<<'PY'\n(.*?)\nPY\n", BUILD.read_text(), re.S).group(1)


class WineMediaCacheTests(unittest.TestCase):
    def test_fingerprint_binds_source_patch_compiler_and_config_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = ('script/build-runtime.sh', 'work/wine/configure',
                      'sources/WINE_SOURCE.lock', 'sources/FINEWINE_PATCHSET.lock',
                      'patches/media/example.patch')
            for name in inputs:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('original')

            def fingerprint(media='media-recipe', compiler=b'clang fixture'):
                output = io.StringIO()
                with patch('sys.argv', ['-', str(root), media, 'SDK', '10.15']), \
                        patch('subprocess.check_output', return_value=compiler), \
                        contextlib.redirect_stdout(output):
                    exec(compile(FINGERPRINT, str(BUILD), 'exec'), {})
                return output.getvalue().strip()

            initial = fingerprint()
            self.assertRegex(initial, r'^[0-9a-f]{64}$')
            self.assertEqual(initial, fingerprint())
            self.assertNotEqual(initial, fingerprint(media='changed-media'))
            self.assertNotEqual(initial, fingerprint(compiler=b'changed clang'))
            for name in inputs:
                with self.subTest(input=name):
                    (root / name).write_text('changed')
                    self.assertNotEqual(initial, fingerprint())
                    (root / name).write_text('original')


if __name__ == '__main__':
    unittest.main()
