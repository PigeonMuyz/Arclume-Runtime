#!/usr/bin/env python3
"""Decode short local media fixtures with an extracted Arclume Runtime."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable


FIXTURE_SPECS: tuple[dict[str, Any], ...] = (
    {"name": "h264", "kind": "video", "encoders": ("libx264",),
     "args": ("-preset", "ultrafast", "-tune", "zerolatency", "-crf", "38", "-pix_fmt", "yuv420p")},
    {"name": "h265", "kind": "video", "encoders": ("libx265",),
     "args": ("-preset", "ultrafast", "-x265-params", "pools=1:frame-threads=1", "-crf", "40", "-pix_fmt", "yuv420p")},
    {"name": "vp8", "kind": "video", "encoders": ("libvpx",),
     "args": ("-deadline", "realtime", "-cpu-used", "8", "-b:v", "0", "-crf", "42", "-pix_fmt", "yuv420p")},
    {"name": "vp9", "kind": "video", "encoders": ("libvpx-vp9",),
     "args": ("-deadline", "realtime", "-cpu-used", "8", "-threads", "1", "-b:v", "0", "-crf", "45", "-pix_fmt", "yuv420p")},
    {"name": "av1", "kind": "video", "encoders": ("libaom-av1", "libsvtav1", "librav1e"),
     "args": (), "encoder_args": {
         "libaom-av1": ("-cpu-used", "8", "-threads", "1", "-crf", "48", "-b:v", "0", "-pix_fmt", "yuv420p"),
         "libsvtav1": ("-preset", "12", "-crf", "48", "-pix_fmt", "yuv420p"),
         "librav1e": ("-speed", "10", "-crf", "45", "-pix_fmt", "yuv420p"),
     }},
    {"name": "mpeg4", "kind": "video", "encoders": ("mpeg4",),
     "args": ("-q:v", "12", "-pix_fmt", "yuv420p")},
    {"name": "mpeg2", "kind": "video", "encoders": ("mpeg2video",),
     "args": ("-q:v", "10", "-pix_fmt", "yuv420p")},
    {"name": "mjpeg", "kind": "video", "encoders": ("mjpeg",),
     "args": ("-q:v", "10", "-pix_fmt", "yuvj420p")},
    {"name": "wmv", "kind": "video", "encoders": ("wmv1", "wmv2"),
     "args": ("-q:v", "10", "-pix_fmt", "yuv420p"),
     "fixture_extension": "avi", "fixture_container": "avi"},
    {"name": "aac", "kind": "audio", "encoders": ("aac",),
     "args": ("-b:a", "64k")},
    {"name": "mp3", "kind": "audio", "encoders": ("libmp3lame",),
     "args": ("-b:a", "64k")},
    {"name": "vorbis", "kind": "audio", "encoders": ("libvorbis", "vorbis"),
     "args": ("-q:a", "1"),
     "encoder_args": {"vorbis": ("-strict", "experimental", "-q:a", "1")}},
    {"name": "opus", "kind": "audio", "encoders": ("libopus",),
     "args": ("-b:a", "64k", "-vbr", "off")},
    {"name": "flac", "kind": "audio", "encoders": ("flac",),
     "args": ()},
    {"name": "ac3", "kind": "audio", "encoders": ("ac3",),
     "args": ("-b:a", "96k"), "fixture_extension": "mka",
     "fixture_container": "matroska"},
    {"name": "eac3", "kind": "audio", "encoders": ("eac3",),
     "args": ("-b:a", "96k"), "fixture_extension": "mka",
     "fixture_container": "matroska"},
    {"name": "wma1", "kind": "audio", "encoders": ("wmav1",),
     "args": ("-b:a", "64k"), "fixture_extension": "asf",
     "fixture_container": "asf"},
    {"name": "wma2", "kind": "audio", "encoders": ("wmav2",),
     "args": ("-b:a", "64k"), "fixture_extension": "asf",
     "fixture_container": "asf"},
    {"name": "alac", "kind": "audio", "encoders": ("alac",),
     "args": (), "fixture_extension": "m4a", "fixture_container": "mp4"},
    {"name": "pcm_s16le", "kind": "audio", "encoders": ("pcm_s16le",),
     "args": ()},
)

COMMAND_OUTPUT_LIMIT = 12000
FIXTURE_SECONDS = 0.6
CONTAINER_CASES: tuple[dict[str, Any], ...] = (
    {"name": "h264_mp4", "source": "h264", "container": "mp4", "extension": "mp4", "stream": "video"},
    {"name": "h264_mov", "source": "h264", "container": "mov", "extension": "mov", "stream": "video"},
    {"name": "h264_mpegts", "source": "h264", "container": "mpegts", "extension": "ts", "stream": "video"},
    {"name": "mpeg4_avi", "source": "mpeg4", "container": "avi", "extension": "avi", "stream": "video"},
    {"name": "wmv_asf", "source": "wmv", "container": "asf", "extension": "asf", "stream": "video"},
    {"name": "aac_adts", "source": "aac", "container": "adts", "extension": "aac", "stream": "audio"},
    {"name": "mp3_raw", "source": "mp3", "container": "mp3", "extension": "mp3", "stream": "audio"},
    {"name": "vorbis_ogg", "source": "vorbis", "container": "ogg", "extension": "ogg", "stream": "audio"},
    {"name": "opus_ogg", "source": "opus", "container": "ogg", "extension": "ogg", "stream": "audio"},
    {"name": "flac_raw", "source": "flac", "container": "flac", "extension": "flac", "stream": "audio"},
    {"name": "pcm_wav", "source": "pcm_s16le", "container": "wav", "extension": "wav", "stream": "audio"},
)


def parse_ffmpeg_codecs(output: str) -> set[str]:
    """Read encoder or decoder names from `ffmpeg -encoders/-decoders`."""
    names: set[str] = set()
    for line in output.splitlines():
        match = re.match(r"^\s*[VAS.][A-Z.]{5}\s+(\S+)\s", line)
        if match:
            names.add(match.group(1))
    return names


def parse_gst_plugin_names(output: str) -> list[str]:
    """Parse top-level plugin names from gst-inspect's all-plugins listing."""
    names: set[str] = set()
    for line in output.splitlines():
        if line[:1].isspace():
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9_.+-]*):\s", line)
        if match:
            names.add(match.group(1))
    return sorted(names)


def count_ffmpeg_framehash_records(output: str) -> int:
    return sum(bool(re.match(r"^\s*\d+\s*,", line)) for line in output.splitlines())


def gst_identity_buffer_counts(output: str) -> dict[str, int]:
    pattern = re.compile(
        r'\b(?P<name>identity\d+|video_buffers|audio_buffers):\s*'
        r'last-message\s*=\s*"?chain\s+\*+\s+\(\1:sink\)')
    counts: dict[str, int] = {}
    for line in output.splitlines():
        match = pattern.search(line)
        if match:
            name = match.group("name")
            counts[name] = counts.get(name, 0) + 1
    return counts


def count_gst_identity_buffers(output: str) -> int:
    return sum(gst_identity_buffer_counts(output).values())


def choose_encoder(spec: dict[str, Any], available: Iterable[str]) -> str | None:
    available_names = set(available)
    return next((name for name in spec["encoders"] if name in available_names), None)


def fixture_path_for_spec(fixture_dir: Path, spec: dict[str, Any]) -> Path:
    extension = spec.get("fixture_extension", "mkv")
    return fixture_dir / f"{spec['name']}.{extension}"


def fixture_container_for_spec(spec: dict[str, Any]) -> str:
    return spec.get("fixture_container", "matroska")


def gst_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def make_fixture_command(ffmpeg: Path, spec: dict[str, Any], encoder: str,
                         fixture_path: Path) -> list[str]:
    command = [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-v", "error",
               "-f", "lavfi"]
    if spec["kind"] == "video":
        command += ["-i", "color=c=black:s=64x64:r=5:d=0.6", "-an", "-t", "0.6",
                    "-frames:v", "3", "-threads", "1", "-c:v", encoder]
    else:
        command += ["-i", "sine=frequency=880:sample_rate=48000:duration=0.6",
                    "-vn", "-t", "0.6", "-threads", "1", "-ac", "2", "-ar", "48000",
                    "-c:a", encoder]
    command += list(spec.get("encoder_args", {}).get(encoder, spec["args"]))
    command.append(str(fixture_path))
    return command


def make_gst_decode_command(gst_launch: Path, fixture_path: Path,
                            dual_streams: bool = False) -> list[str]:
    location = gst_quote(str(fixture_path))
    command = [str(gst_launch), "-v", "filesrc", f"location={location}", "!", "decodebin"]
    if not dual_streams:
        return command + ["!", "identity", "silent=false", "!", "fakesink", "sync=false"]
    return command + [
        "name=decoder", "decoder.", "!", "queue", "!", "video/x-raw", "!",
        "identity", "name=video_buffers", "silent=false", "!", "fakesink", "sync=false",
        "decoder.", "!", "queue", "!", "audio/x-raw", "!",
        "identity", "name=audio_buffers", "silent=false", "!", "fakesink", "sync=false",
    ]


def make_remux_command(ffmpeg: Path, sources: list[Path], maps: list[str],
                       output: Path) -> list[str]:
    command = [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-v", "error"]
    for source in sources:
        command += ["-i", str(source)]
    for stream_map in maps:
        command += ["-map", stream_map]
    return command + ["-c", "copy", "-shortest", str(output)]


def decode_ffmpeg_stream(ffmpeg: Path, fixture_path: Path, kind: str,
                         env: dict[str, str], timeout: float) -> dict[str, Any]:
    stream_map = "0:v:0" if kind == "video" else "0:a:0"
    record = run_command(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-v", "error", "-xerror",
         "-threads", "1", "-i", str(fixture_path), "-map", stream_map,
         "-f", "framemd5", "-"], env, timeout)
    record["decoded_units"] = count_ffmpeg_framehash_records(record.get("stdout", ""))
    if record["status"] == "pass" and record["decoded_units"] == 0:
        record["status"] = "fail"
        record["error"] = "FFmpeg exited successfully but produced no framehash records"
    return record


def decode_gstreamer(gst_launch: Path, fixture_path: Path, env: dict[str, str],
                     timeout: float, dual_streams: bool = False) -> dict[str, Any]:
    record = run_command(make_gst_decode_command(gst_launch, fixture_path, dual_streams), env, timeout)
    output = record.get("stdout", "") + "\n" + record.get("stderr", "")
    counts = gst_identity_buffer_counts(output)
    if dual_streams:
        per_stream = {
            "video": counts.get("video_buffers", 0),
            "audio": counts.get("audio_buffers", 0),
        }
        record["decoded_buffers_by_stream"] = per_stream
        record["decoded_buffers"] = sum(per_stream.values())
        if record["status"] == "pass" and not all(per_stream.values()):
            record["status"] = "fail"
            record["error"] = "GStreamer did not report decoded buffers for both MP4 streams"
    else:
        record["decoded_buffers"] = sum(counts.values())
        if record["status"] == "pass" and record["decoded_buffers"] == 0:
            record["status"] = "fail"
            record["error"] = "GStreamer reached EOS without reporting a decoded buffer"
    return record


def decode_case(name: str, container: str, fixture_path: Path,
                fixture_record: dict[str, Any], stream_kinds: tuple[str, ...],
                ffmpeg: Path, gst_launch: Path, env: dict[str, str], timeout: float,
                dual_streams: bool = False, case_type: str = "codec") -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name, "case_type": case_type, "container": container,
        "fixture_path": str(fixture_path), "fixture": fixture_record,
    }
    if fixture_record["status"] != "pass":
        item["status"] = fixture_record["status"]
        item["ffmpeg_decode"] = {"status": "skip", "reason": "Fixture was not created"}
        item["gstreamer_decode"] = {"status": "skip", "reason": "Fixture was not created"}
        return item

    stream_checks = {
        kind: decode_ffmpeg_stream(ffmpeg, fixture_path, kind, env, timeout)
        for kind in stream_kinds
    }
    if dual_streams:
        item["ffmpeg_decode"] = {"status": "pass" if all(
            record["status"] == "pass" for record in stream_checks.values()) else "fail",
            "streams": stream_checks}
    else:
        item["ffmpeg_decode"] = stream_checks[stream_kinds[0]]
    item["gstreamer_decode"] = decode_gstreamer(
        gst_launch, fixture_path, env, timeout, dual_streams=dual_streams)
    item["status"] = "pass" if (
        item["ffmpeg_decode"]["status"] == "pass" and
        item["gstreamer_decode"]["status"] == "pass") else "fail"
    return item


def build_runtime_env(base_env: dict[str, str], runtime: Path, plugin_dir: Path,
                      registry: Path, scanner: Path | None = None) -> dict[str, str]:
    """Pin GStreamer to this runtime and give tools its private libraries."""
    env = dict(base_env)
    lib_dir = runtime / "lib64"
    bin_dir = runtime / "bin"
    env["PATH"] = os.pathsep.join((str(bin_dir), base_env.get("PATH", "")))
    env["LD_LIBRARY_PATH"] = str(lib_dir)
    env["DYLD_LIBRARY_PATH"] = str(lib_dir)
    env["DYLD_FALLBACK_LIBRARY_PATH"] = str(lib_dir)
    env["GST_REGISTRY"] = str(registry)
    env["GST_REGISTRY_1_0"] = str(registry)
    env["GST_PLUGIN_SYSTEM_PATH"] = ""
    env["GST_PLUGIN_SYSTEM_PATH_1_0"] = ""
    env["GST_PLUGIN_PATH"] = str(plugin_dir)
    env["GST_PLUGIN_PATH_1_0"] = str(plugin_dir)
    for variable in ("GST_PLUGIN_SCANNER", "GST_PLUGIN_SCANNER_1_0"):
        env.pop(variable, None)
        if scanner:
            env[variable] = str(scanner)
    return env


def run_command(command: list[str], env: dict[str, str], timeout: float,
                parse_full_output: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {"command": command, "status": "fail"}
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", env=env,
                                   timeout=timeout, check=False)
        record.update({
            "returncode": completed.returncode,
            "status": "pass" if completed.returncode == 0 else "fail",
            "stdout": completed.stdout[-COMMAND_OUTPUT_LIMIT:],
            "stderr": completed.stderr[-COMMAND_OUTPUT_LIMIT:],
            "stdout_truncated": len(completed.stdout) > COMMAND_OUTPUT_LIMIT,
            "stderr_truncated": len(completed.stderr) > COMMAND_OUTPUT_LIMIT,
        })
        if parse_full_output:
            record["_stdout_full"] = completed.stdout
            record["_stderr_full"] = completed.stderr
    except subprocess.TimeoutExpired as exc:
        record.update({
            "status": "timeout",
            "timeout_seconds": timeout,
            "stdout": _output_text(exc.stdout)[-COMMAND_OUTPUT_LIMIT:],
            "stderr": _output_text(exc.stderr)[-COMMAND_OUTPUT_LIMIT:],
        })
    except OSError as exc:
        record["error"] = str(exc)
    return record


def _output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def scanner_path(runtime: Path) -> Path | None:
    candidates = (
        runtime / "libexec/gstreamer-1.0/gst-plugin-scanner",
        runtime / "lib/gstreamer-1.0/gst-plugin-scanner",
        runtime / "libexec/gstreamer-1.0/gst-plugin-scanner-1.0",
    )
    return next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def plugin_files(plugin_dir: Path) -> list[str]:
    if not plugin_dir.is_dir():
        return []
    return sorted(path.name for path in plugin_dir.iterdir()
                  if path.is_file() and path.name.startswith("libgst")
                  and (path.suffix in {".dylib", ".so"} or ".so." in path.name))


def plugin_names_from_files(files: Iterable[str]) -> list[str]:
    names = set()
    for filename in files:
        stem = filename[len("libgst"):]
        for suffix in (".dylib", ".so"):
            if suffix in stem:
                stem = stem.split(suffix, 1)[0]
                break
        if stem:
            names.add(stem)
    return sorted(names)


def resolve_fixture_ffmpeg(argument: str | None) -> Path | None:
    candidate = shutil.which(argument) if argument else shutil.which("ffmpeg")
    if candidate is None:
        return None
    path = Path(candidate).expanduser().resolve()
    return path if path.is_file() and os.access(path, os.X_OK) else None


def summarize(results: list[dict[str, Any]], preflight_errors: list[str]) -> dict[str, Any]:
    counts = {state: sum(result["status"] == state for result in results)
              for state in ("pass", "fail", "skip")}
    if preflight_errors or counts["fail"]:
        overall = "fail"
    elif counts["pass"]:
        overall = "pass"
    else:
        overall = "incomplete"
    return {"overall": overall, **counts, "preflight_errors": preflight_errors}


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from exc
    if timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive number")
    return timeout


def run_suite(runtime: Path, output_dir: Path, fixture_ffmpeg: Path | None,
              timeout: float) -> tuple[dict[str, Any], int]:
    bin_dir = runtime / "bin"
    ffmpeg = bin_dir / "ffmpeg"
    gst_launch = bin_dir / "gst-launch-1.0"
    gst_inspect = bin_dir / "gst-inspect-1.0"
    plugin_dir = runtime / "lib/gstreamer-1.0"
    report_path = output_dir / "media-decode-report.json"
    output_dir.mkdir(parents=True, exist_ok=False)

    preflight_errors: list[str] = []
    for path in (runtime, runtime / "lib64", plugin_dir):
        if not path.is_dir():
            preflight_errors.append(f"Required runtime directory is missing: {path}")
    for path in (ffmpeg, gst_launch, gst_inspect):
        if not path.is_file() or not os.access(path, os.X_OK):
            preflight_errors.append(f"Required runtime executable is missing or not executable: {path}")

    plugin_scanner = scanner_path(runtime)
    fixture_dir = output_dir / "fixtures"
    fixture_dir.mkdir()
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="arclume-media-gst-") as registry_root:
        registry = Path(registry_root) / "registry.bin"
        env = build_runtime_env(os.environ, runtime, plugin_dir, registry, plugin_scanner)
        runtime_plugin_files = plugin_files(plugin_dir)
        runtime_plugin_names = plugin_names_from_files(runtime_plugin_files)
        report: dict[str, Any] = {
            "schema_version": 1,
            "started_at": _timestamp(),
            "runtime": str(runtime),
            "output_dir": str(output_dir),
            "fixture_ffmpeg": str(fixture_ffmpeg) if fixture_ffmpeg else None,
            "timeout_seconds": timeout,
            "device_access": False,
            "network_access": False,
            "gstreamer_environment": {
                key: env[key] for key in (
                    "GST_REGISTRY", "GST_REGISTRY_1_0", "GST_PLUGIN_SYSTEM_PATH",
                    "GST_PLUGIN_SYSTEM_PATH_1_0", "GST_PLUGIN_PATH", "GST_PLUGIN_PATH_1_0",
                )
            },
            "preflight_errors": preflight_errors,
            "inventory": {
                "plugin_directory": str(plugin_dir),
                "plugin_files": runtime_plugin_files,
                "plugin_scanner": str(plugin_scanner) if plugin_scanner else None,
                "gst_inspect": None,
                "gst_plugins": runtime_plugin_names,
                "gst_inspect_plugins_observed": [],
                "fixture_ffmpeg_encoders": [],
                "runtime_ffmpeg_decoders": [],
            },
        }

        if gst_inspect.is_file() and os.access(gst_inspect, os.X_OK):
            inspect_record = run_command([str(gst_inspect)], env, timeout, parse_full_output=True)
            inspect_output = inspect_record.pop("_stdout_full", inspect_record.get("stdout", ""))
            inspect_error = inspect_record.pop("_stderr_full", inspect_record.get("stderr", ""))
            report["inventory"]["gst_inspect"] = inspect_record
            observed_plugins = parse_gst_plugin_names(inspect_output + "\n" + inspect_error)
            report["inventory"]["gst_inspect_plugins_observed"] = [
                name for name in observed_plugins if name in runtime_plugin_names or name == "staticelements"]
            if inspect_record["status"] != "pass":
                preflight_errors.append("Runtime gst-inspect-1.0 could not enumerate plugins")

        fixture_encoders: set[str] = set()
        if fixture_ffmpeg:
            fixture_env = os.environ.copy()
            encoder_record = run_command([str(fixture_ffmpeg), "-hide_banner", "-encoders"],
                                         fixture_env, timeout, parse_full_output=True)
            report["inventory"]["fixture_ffmpeg_encoder_command"] = encoder_record
            encoder_output = encoder_record.pop("_stdout_full", encoder_record.get("stdout", ""))
            encoder_error = encoder_record.pop("_stderr_full", encoder_record.get("stderr", ""))
            fixture_encoders = parse_ffmpeg_codecs(encoder_output + "\n" + encoder_error)
            report["inventory"]["fixture_ffmpeg_encoders"] = sorted(fixture_encoders)
            if encoder_record["status"] != "pass":
                preflight_errors.append("Fixture ffmpeg could not enumerate available encoders")
        else:
            preflight_errors.append("No fixture ffmpeg was found; specify --fixture-ffmpeg to create local media samples")

        if ffmpeg.is_file() and os.access(ffmpeg, os.X_OK):
            decoder_record = run_command([str(ffmpeg), "-hide_banner", "-decoders"],
                                         env, timeout, parse_full_output=True)
            report["inventory"]["runtime_ffmpeg_decoder_command"] = decoder_record
            decoder_output = decoder_record.pop("_stdout_full", decoder_record.get("stdout", ""))
            decoder_error = decoder_record.pop("_stderr_full", decoder_record.get("stderr", ""))
            report["inventory"]["runtime_ffmpeg_decoders"] = sorted(
                parse_ffmpeg_codecs(decoder_output + "\n" + decoder_error))
            if decoder_record["status"] != "pass":
                preflight_errors.append("Runtime ffmpeg could not enumerate decoders")

        base_fixtures: dict[str, tuple[Path, dict[str, Any]]] = {}
        encoder_inventory = report["inventory"].get("fixture_ffmpeg_encoder_command", {})
        for spec in FIXTURE_SPECS:
            encoder = choose_encoder(spec, fixture_encoders)
            fixture_path = fixture_path_for_spec(fixture_dir, spec)
            if not fixture_ffmpeg:
                fixture_record = {"status": "skip", "reason": "No fixture ffmpeg is available"}
            elif encoder_inventory.get("status") != "pass":
                fixture_record = {"status": "skip", "reason": "Fixture ffmpeg encoder inventory failed"}
            elif encoder is None:
                fixture_record = {
                    "status": "skip",
                    "reason": "Fixture ffmpeg does not provide a software encoder for this codec",
                }
            else:
                fixture_record = run_command(
                    make_fixture_command(fixture_ffmpeg, spec, encoder, fixture_path), fixture_env, timeout)
                fixture_record["encoder"] = encoder
                fixture_record["operation"] = "generate"
                fixture_record["duration_limit_seconds"] = FIXTURE_SECONDS
            base_fixtures[spec["name"]] = (fixture_path, fixture_record)
            results.append(decode_case(
                spec["name"], fixture_container_for_spec(spec), fixture_path,
                fixture_record, (spec["kind"],),
                ffmpeg, gst_launch, env, timeout, case_type="codec"))

        for case in CONTAINER_CASES:
            source_path, source_record = base_fixtures[case["source"]]
            fixture_path = fixture_dir / f"{case['name']}.{case['extension']}"
            if source_record["status"] != "pass":
                fixture_record = {
                    "status": "skip", "reason": f"Source {case['source']} fixture was not available",
                    "source_fixture": str(source_path),
                }
            else:
                stream_type = "v" if case["stream"] == "video" else "a"
                fixture_record = run_command(
                    make_remux_command(fixture_ffmpeg, [source_path],
                                       [f"0:{stream_type}:0"], fixture_path),
                    fixture_env, timeout)
                fixture_record["operation"] = "remux-copy"
                fixture_record["source_fixture"] = str(source_path)
            results.append(decode_case(
                case["name"], case["container"], fixture_path, fixture_record, (case["stream"],),
                ffmpeg, gst_launch, env, timeout, case_type="container"))

        h264_path, h264_record = base_fixtures["h264"]
        aac_path, aac_record = base_fixtures["aac"]
        mux_path = fixture_dir / "h264_aac_mp4.mp4"
        if h264_record["status"] != "pass" or aac_record["status"] != "pass":
            mux_record = {"status": "skip", "reason": "H.264 or AAC source fixture was not available"}
        else:
            mux_record = run_command(
                make_remux_command(fixture_ffmpeg, [h264_path, aac_path],
                                   ["0:v:0", "1:a:0"], mux_path), fixture_env, timeout)
            mux_record["operation"] = "remux-copy"
            mux_record["source_fixtures"] = [str(h264_path), str(aac_path)]
        results.append(decode_case(
            "h264_aac_mp4", "mp4", mux_path, mux_record, ("video", "audio"),
            ffmpeg, gst_launch, env, timeout, dual_streams=True, case_type="container"))

        report["results"] = results
        report["finished_at"] = _timestamp()
        report["summary"] = summarize(results, preflight_errors)
        _write_report(report_path, report)

    summary = report["summary"]
    print(f"Media decode {summary['overall']}: {summary['pass']} passed, "
          f"{summary['fail']} failed, {summary['skip']} skipped")
    print(f"JSON report: {report_path}")
    if summary["overall"] == "fail":
        return report, 1
    if summary["overall"] == "incomplete":
        return report, 2
    return report, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate short local media fixtures and decode them with an extracted Arclume Runtime.")
    parser.add_argument("--runtime", required=True, type=Path,
                        help="Extracted x86_64 runtime root")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New, nonexistent directory for fixtures and the JSON report")
    parser.add_argument("--fixture-ffmpeg", type=str,
                        help="Optional system ffmpeg executable used only to create fixtures")
    parser.add_argument("--timeout", type=positive_timeout, default=30.0,
                        help="Per-command timeout in seconds (default: 30)")
    args = parser.parse_args(argv)

    runtime = args.runtime.expanduser().resolve()
    output_argument = args.output_dir.expanduser()
    if output_argument.exists() or output_argument.is_symlink():
        parser.error(f"--output-dir must not already exist: {output_argument}")
    output_dir = output_argument.resolve()
    if _path_is_within(output_dir, runtime) or _path_is_within(runtime, output_dir):
        parser.error("--output-dir and --runtime must be separate directories")

    fixture_ffmpeg = resolve_fixture_ffmpeg(args.fixture_ffmpeg)
    if args.fixture_ffmpeg and fixture_ffmpeg is None:
        parser.error(f"Fixture ffmpeg is not an executable file: {args.fixture_ffmpeg}")
    try:
        _, return_code = run_suite(runtime, output_dir, fixture_ffmpeg, args.timeout)
        return return_code
    except FileExistsError:
        parser.error(f"--output-dir appeared before it could be created: {output_dir}")
    except OSError as exc:
        print(f"Could not prepare test output: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
