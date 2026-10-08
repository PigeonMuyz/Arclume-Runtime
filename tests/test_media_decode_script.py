"""Focused unit tests for script/test-media-decode.py."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "script/test-media-decode.py"
SPEC = importlib.util.spec_from_file_location("test_media_decode_script", SCRIPT_PATH)
media_decode = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(media_decode)


class MediaDecodeScriptTests(unittest.TestCase):
    def test_parses_ffmpeg_encoder_and_decoder_rows(self):
        listing = """
 V..... h264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
 A..... aac AAC (Advanced Audio Coding)
 V..... libx264 libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
"""
        self.assertEqual(media_decode.parse_ffmpeg_codecs(listing), {"h264", "aac", "libx264"})

    def test_encoder_selection_prefers_first_available_software_encoder(self):
        spec = {"encoders": ("libaom-av1", "libsvtav1", "librav1e")}
        self.assertEqual(media_decode.choose_encoder(spec, {"libsvtav1", "librav1e"}), "libsvtav1")
        self.assertIsNone(media_decode.choose_encoder(spec, {"av1_nvenc"}))

    def test_parses_only_top_level_gstreamer_plugin_names(self):
        output = """coreelements:  fakesink: Fake Sink
  filesrc: File Source
libav:  avdec_h264: libav H.264 decoder
Plugin Details:
"""
        self.assertEqual(media_decode.parse_gst_plugin_names(output), ["coreelements", "libav"])

    def test_requires_framehash_records_and_gstreamer_buffers(self):
        framehash = "#stream#, dts, pts, duration, size, hash\n0, 0, 0, 1, 12, abcd\n"
        gst_log = ('identity0: last-message = chain   ******* (identity0:sink) '
                   '(4096 bytes, dts: 0, pts: 0, duration: 1) 0x1234\n'
                   'identity1: last-message = "chain ******* (identity1:sink) '
                   '(2048 bytes, dts: 0, pts: 0, duration: 1) 0x5678\n')
        self.assertEqual(media_decode.count_ffmpeg_framehash_records(framehash), 1)
        self.assertEqual(media_decode.count_ffmpeg_framehash_records("# EOS\n"), 0)
        self.assertEqual(media_decode.count_gst_identity_buffers(gst_log), 2)
        self.assertEqual(media_decode.count_gst_identity_buffers("Got EOS from pipeline\n"), 0)

    def test_gstreamer_environment_uses_only_the_runtime_plugin_directory(self):
        runtime = Path("/candidate/runtime")
        plugin_dir = runtime / "lib/gstreamer-1.0"
        scanner = runtime / "libexec/gstreamer-1.0/gst-plugin-scanner"
        env = media_decode.build_runtime_env(
            {
                "PATH": "/system/bin",
                "GST_PLUGIN_PATH": "/system/plugins",
                "GST_PLUGIN_PATH_1_0": "/system/plugins-v1",
                "GST_PLUGIN_SYSTEM_PATH": "/system/gst",
                "GST_PLUGIN_SCANNER": "/system/scanner",
                "DYLD_LIBRARY_PATH": "/system/libs",
            },
            runtime,
            plugin_dir,
            Path("/tmp/private-registry.bin"),
            scanner,
        )
        self.assertEqual(env["GST_PLUGIN_SYSTEM_PATH"], "")
        self.assertEqual(env["GST_PLUGIN_SYSTEM_PATH_1_0"], "")
        self.assertEqual(env["GST_PLUGIN_PATH"], str(plugin_dir))
        self.assertEqual(env["GST_PLUGIN_PATH_1_0"], str(plugin_dir))
        self.assertEqual(env["GST_REGISTRY"], "/tmp/private-registry.bin")
        self.assertEqual(env["GST_PLUGIN_SCANNER"], str(scanner))
        self.assertEqual(env["DYLD_LIBRARY_PATH"], str(runtime / "lib64"))
        self.assertEqual(env["PATH"], f"{runtime / 'bin'}:/system/bin")

    def test_pipeline_reads_a_local_file_and_ends_at_fakesink(self):
        command = media_decode.make_gst_decode_command(
            Path("/runtime/bin/gst-launch-1.0"), Path('/tmp/media test/clip "1".mkv'))
        self.assertEqual(command[0], "/runtime/bin/gst-launch-1.0")
        self.assertEqual(command[1:3], ["-v", "filesrc"])
        self.assertEqual(command[3], 'location="/tmp/media test/clip \\\"1\\\".mkv"')
        self.assertEqual(command[4:], ["!", "decodebin", "!", "identity", "silent=false",
                                       "!", "fakesink", "sync=false"])
        self.assertEqual(command[-2:], ["fakesink", "sync=false"])
        self.assertIn("decodebin", command)

    def test_mux_pipeline_counts_video_and_audio_on_separate_fakesinks(self):
        command = media_decode.make_gst_decode_command(
            Path("/runtime/bin/gst-launch-1.0"), Path("/tmp/combined.mp4"), dual_streams=True)
        self.assertIn("decodebin", command)
        self.assertIn("video/x-raw", command)
        self.assertIn("audio/x-raw", command)
        self.assertEqual(command.count("fakesink"), 2)
        self.assertEqual(command.count("silent=false"), 2)

    def test_remux_command_copies_selected_streams_without_encoding(self):
        command = media_decode.make_remux_command(
            Path("/system/bin/ffmpeg"), [Path("/tmp/video.mkv"), Path("/tmp/audio.mkv")],
            ["0:v:0", "1:a:0"], Path("/tmp/combined.mp4"))
        self.assertEqual(command.count("-i"), 2)
        self.assertIn("-c", command)
        self.assertIn("copy", command)
        self.assertIn("0:v:0", command)
        self.assertIn("1:a:0", command)
        self.assertEqual(command[-1], "/tmp/combined.mp4")

    def test_plugin_filenames_produce_clean_runtime_plugin_names(self):
        self.assertEqual(
            media_decode.plugin_names_from_files(
                ["libgstcoreelements.dylib", "libgstlibav.dylib", "libgstmatroska.so.1"]),
            ["coreelements", "libav", "matroska"],
        )

    def test_generated_fixtures_are_short_and_local(self):
        spec = next(item for item in media_decode.FIXTURE_SPECS if item["name"] == "aac")
        command = media_decode.make_fixture_command(
            Path("/system/bin/ffmpeg"), spec, "aac", Path("/results/fixtures/aac.mkv"))
        self.assertIn("sine=frequency=880:sample_rate=48000:duration=0.6", command)
        self.assertIn("0.6", command)
        self.assertEqual(command[-1], "/results/fixtures/aac.mkv")
        self.assertNotIn("-f", command[command.index("-i") + 1:])

    def test_additional_audio_codecs_use_compatible_short_fixtures(self):
        expected = {
            "ac3": ("ac3", "mka", "matroska"),
            "eac3": ("eac3", "mka", "matroska"),
            "wma1": ("wmav1", "asf", "asf"),
            "wma2": ("wmav2", "asf", "asf"),
            "alac": ("alac", "m4a", "mp4"),
        }
        specs = {item["name"]: item for item in media_decode.FIXTURE_SPECS}
        for name, (encoder, extension, container) in expected.items():
            with self.subTest(codec=name):
                spec = specs[name]
                self.assertEqual(spec["encoders"], (encoder,))
                self.assertFalse(encoder.startswith("lib"))
                path = media_decode.fixture_path_for_spec(Path("/results/fixtures"), spec)
                self.assertEqual(path.suffix, f".{extension}")
                self.assertEqual(media_decode.fixture_container_for_spec(spec), container)
                command = media_decode.make_fixture_command(
                    Path("/system/bin/ffmpeg"), spec, encoder, path)
                self.assertIn("sine=frequency=880:sample_rate=48000:duration=0.6", command)
                self.assertIn("-t", command)
                self.assertEqual(command[command.index("-t") + 1], "0.6")
                self.assertEqual(command[-1], str(path))

    def test_all_skips_are_incomplete_not_a_pass(self):
        self.assertEqual(media_decode.summarize([{"status": "skip"}], [])[
            "overall"], "incomplete")


if __name__ == "__main__":
    unittest.main()
