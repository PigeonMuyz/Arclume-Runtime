"""Regression checks for the release workflow's candidate media gate."""

import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / '.github/workflows/release-runtime.yml'
BUILD_SCRIPT_PATH = ROOT / 'script/build-runtime.sh'
WORKFLOW = WORKFLOW_PATH.read_text()
BUILD_SCRIPT = BUILD_SCRIPT_PATH.read_text()


class MediaReleaseGateTests(unittest.TestCase):
    def test_workflow_decodes_the_extracted_candidate_with_host_ffmpeg_for_fixtures(self):
        self.assertRegex(WORKFLOW, r'brew install [^\n]*\bffmpeg\b')
        self.assertIn('python3 script/test-media-decode.py', WORKFLOW)
        self.assertIn('--runtime "$runtime_verify_dir/arclume-wine-runtime-x86_64"', WORKFLOW)
        self.assertIn('--fixture-ffmpeg "$fixture_ffmpeg"', WORKFLOW)
        self.assertIn('fixture_ffmpeg="$(brew --prefix ffmpeg)/bin/ffmpeg"', WORKFLOW)

    def test_workflow_gate_rejects_failed_and_skipped_cases(self):
        match = re.search(
            r"if ! jq -e '([^']+)' \\\n\s+\"\$decode_report\" >/dev/null; then",
            WORKFLOW,
        )
        self.assertIsNotNone(match, 'release must evaluate the JSON decode report')
        jq_filter = match.group(1)

        def accepted(report):
            result = subprocess.run(
                ['jq', '-e', jq_filter],
                input=json.dumps(report),
                text=True,
                capture_output=True,
                check=False,
            )
            return result.returncode == 0

        self.assertTrue(accepted({
            'summary': {'overall': 'pass', 'pass': 2, 'fail': 0, 'skip': 0},
            'results': [{'status': 'pass'}, {'status': 'pass'}],
        }))
        self.assertFalse(accepted({
            'summary': {'overall': 'pass', 'pass': 1, 'fail': 0, 'skip': 1},
            'results': [{'status': 'pass'}, {'status': 'skip'}],
        }))
        self.assertFalse(accepted({
            'summary': {'overall': 'fail', 'pass': 1, 'fail': 1, 'skip': 0},
            'results': [{'status': 'pass'}, {'status': 'fail'}],
        }))
        self.assertFalse(accepted({
            'summary': {'overall': 'incomplete', 'pass': 0, 'fail': 0, 'skip': 1},
            'results': [{'status': 'skip'}],
        }))

    def test_decode_report_is_initialized_uploaded_even_after_failure_and_before_publish(self):
        self.assertIn('初始化多媒体解码报告\n        if: always()', WORKFLOW)
        upload_start = WORKFLOW.index('- name: 上传多媒体解码报告')
        upload_end = WORKFLOW.index('\n      - name:', upload_start + 1)
        upload_step = WORKFLOW[upload_start:upload_end]
        self.assertIn('if: always()', upload_step)
        self.assertIn('media-decode-report.json', upload_step)
        self.assertLess(upload_start, WORKFLOW.index('- name: 发布 GitHub Release'))

    def test_pe_arch_guard_accepts_flexible_whitespace_but_requires_both_arches(self):
        match = re.search(
            r"grep -Eq '([^']*PE_ARCHS[^']*)' \"\$BUILD_DIR/Makefile\"",
            BUILD_SCRIPT,
        )
        self.assertIsNotNone(match, 'build-runtime.sh must retain its PE_ARCHS guard')
        pattern = match.group(1)

        def matches(line):
            return subprocess.run(
                ['/usr/bin/grep', '-Eq', pattern],
                input=line + '\n',
                text=True,
                capture_output=True,
                check=False,
            ).returncode == 0

        self.assertTrue(matches('PE_ARCHS = i386 x86_64'))
        self.assertTrue(matches('PE_ARCHS\t=\ti386   x86_64  '))
        self.assertFalse(matches('PE_ARCHS = x86_64 i386'))
        self.assertFalse(matches('PE_ARCHS = i386'))


if __name__ == '__main__':
    unittest.main()
