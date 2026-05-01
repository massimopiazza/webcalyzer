"""FFmpeg-native overlay renderer.

Compared to the OpenCV path, this module pre-renders the unique overlay
panels to PNGs, builds a ``concat`` demuxer playlist holding each panel
for its source-time duration, and lets ``ffmpeg`` overlay + encode in a
single invocation. The alpha compositing lives entirely inside ffmpeg's
SIMD-optimized ``overlay`` filter and the encode happens on the
hardware encoder (``h264_videotoolbox`` / ``h264_nvenc`` / ``h264_vaapi``
/ ``h264_qsv``) when available.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
    from webcalyzer.overlay import OverlayPlan


_ENCODER_PREFERENCE: tuple[str, ...] = (
    "h264_videotoolbox",
    "h264_nvenc",
    "h264_qsv",
    "h264_vaapi",
    "libx264",
)

_VALID_ENCODERS: frozenset[str] = frozenset(
    ("auto", *_ENCODER_PREFERENCE, "videotoolbox", "nvenc", "qsv", "vaapi", "libx264")
)


def render_via_ffmpeg(
    *,
    source_path: Path,
    output_path: Path,
    plan: "OverlayPlan",
    include_audio: bool,
    encoder: str,
) -> Path:
    """Render the overlay video by handing the work to a single ffmpeg call."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not on PATH but the ffmpeg overlay engine was requested.")

    resolved_encoder = _resolve_encoder(encoder)
    if output_path.exists():
        output_path.unlink()

    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="webcalyzer_overlay_") as tmp:
        tmp_dir = Path(tmp)
        png_paths = _write_panels_as_pngs(plan.panel_cache, tmp_dir)
        concat_path = _write_concat_list(
            tmp_dir / "concat.txt",
            panel_segments=plan.panel_segments,
            png_paths=png_paths,
        )

        command = _build_ffmpeg_command(
            ffmpeg=ffmpeg,
            source_path=source_path,
            concat_path=concat_path,
            output_path=output_path,
            plan=plan,
            include_audio=include_audio,
            encoder=resolved_encoder,
        )
        print(
            f"[webcalyzer] ffmpeg overlay engine: encoder={resolved_encoder} "
            f"panels={len(plan.panel_cache)} segments={len(plan.panel_segments)}"
        )
        returncode, output_tail = _run_ffmpeg_with_progress(
            command,
            total_duration_s=float(plan.metadata.duration_s),
        )
        if returncode != 0:
            stderr_tail = "\n".join(output_tail[-30:])
            raise RuntimeError(
                f"ffmpeg overlay encode failed (exit={returncode}). Last output lines:\n{stderr_tail}"
            )

    print(
        f"[webcalyzer] ffmpeg overlay completed in {time.perf_counter() - started_at:.1f}s "
        f"→ {output_path}"
    )
    return output_path


def _run_ffmpeg_with_progress(
    command: list[str],
    *,
    total_duration_s: float,
    log_interval_s: float = 10.0,
    min_percent_step: float = 5.0,
) -> tuple[int, list[str]]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_tail: deque[str] = deque(maxlen=80)
    progress: dict[str, str] = {}
    last_log_time = time.perf_counter()
    last_log_percent = -min_percent_step

    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        output_tail.append(line)
        if "=" not in line:
            print(f"[webcalyzer] ffmpeg: {line}")
            continue
        key, value = line.split("=", 1)
        progress[key] = value
        if key != "progress":
            continue
        percent = _ffmpeg_progress_percent(progress, total_duration_s)
        now = time.perf_counter()
        is_final = value == "end"
        should_log = (
            is_final
            or percent >= last_log_percent + min_percent_step
            or now - last_log_time >= log_interval_s
        )
        if should_log:
            print(_format_ffmpeg_progress(progress, percent, final=is_final))
            last_log_time = now
            last_log_percent = percent

    return process.wait(), list(output_tail)


def _ffmpeg_progress_percent(progress: dict[str, str], total_duration_s: float) -> float:
    if total_duration_s <= 0:
        return 0.0
    out_time_s = _ffmpeg_out_time_s(progress)
    return min(100.0, max(0.0, (out_time_s / total_duration_s) * 100.0))


def _ffmpeg_out_time_s(progress: dict[str, str]) -> float:
    for key in ("out_time_us", "out_time_ms"):
        value = progress.get(key)
        if value is None:
            continue
        try:
            return float(value) / 1_000_000.0
        except ValueError:
            pass
    value = progress.get("out_time")
    if value is None:
        return 0.0
    parts = value.split(":")
    if len(parts) != 3:
        return 0.0
    try:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
    except ValueError:
        return 0.0
    return hours * 3600.0 + minutes * 60.0 + seconds


def _format_ffmpeg_progress(progress: dict[str, str], percent: float, *, final: bool) -> str:
    label = "complete" if final else "progress"
    frame = progress.get("frame", "?")
    out_time = progress.get("out_time", "?")
    return (
        f"[webcalyzer] ffmpeg overlay {label}: "
        f"{percent:5.1f}% frame={frame} time={out_time}"
    )


def _resolve_encoder(encoder: str) -> str:
    """Pick a concrete ``ffmpeg`` encoder name from the user's choice.

    ``auto`` walks :data:`_ENCODER_PREFERENCE` and returns the first one
    that's present in the local ffmpeg build. A short alias like
    ``videotoolbox`` is expanded to ``h264_videotoolbox``.
    """

    if encoder not in _VALID_ENCODERS:
        raise ValueError(
            f"Unknown overlay encoder {encoder!r}; expected one of {sorted(_VALID_ENCODERS)}"
        )
    available = _available_encoders()
    if encoder == "auto":
        for candidate in _ENCODER_PREFERENCE:
            if candidate in available:
                return candidate
        raise RuntimeError(
            "No supported H.264 encoder found in ffmpeg. Install a build with libx264."
        )
    full_name = encoder if encoder.startswith("h264_") or encoder == "libx264" else f"h264_{encoder}"
    if full_name not in available:
        raise RuntimeError(
            f"ffmpeg encoder {full_name!r} is not available in this ffmpeg build "
            f"(available: {sorted(available)})."
        )
    return full_name


@lru_cache(maxsize=1)
def _available_encoders() -> frozenset[str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return frozenset()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return frozenset()
    names: set[str] = set()
    for line in result.stdout.splitlines():
        # encoder lines look like ' V....D libx264              libx264 H.264 ...'
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return frozenset(names)


def _write_panels_as_pngs(panels: dict[int, "object"], tmp_dir: Path) -> dict[int, Path]:
    paths: dict[int, Path] = {}
    panel_items = list(panels.items())
    total = len(panel_items)
    if total:
        print(f"[webcalyzer] ffmpeg overlay: writing {total} overlay panel PNGs")
    log_step = max(1, total // 10) if total else 1
    for position, (reveal_index, panel) in enumerate(panel_items, start=1):
        path = tmp_dir / f"panel_{reveal_index:04d}.png"
        # cv2 expects BGRA → on disk PNG with alpha. Quality is irrelevant
        # because PNG is lossless; compression level 1 keeps writing fast.
        if not cv2.imwrite(str(path), panel, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
            raise RuntimeError(f"failed to write overlay panel PNG: {path}")
        paths[reveal_index] = path
        if position == total or position % log_step == 0:
            print(f"[webcalyzer] ffmpeg overlay panels: {position}/{total}")
    return paths


def _write_concat_list(
    concat_path: Path,
    *,
    panel_segments: list[tuple[int, float, float]],
    png_paths: dict[int, Path],
) -> Path:
    """Emit the ffmpeg concat-demuxer playlist.

    Each segment becomes a ``file <png>\\nduration <seconds>`` pair. The
    last entry is repeated without a duration directive - the concat
    demuxer requires the final file to be present twice for it to handle
    the trailing edge correctly.
    """

    if not panel_segments:
        raise RuntimeError("no overlay panel segments computed; cannot build concat list.")

    lines: list[str] = []
    last_index = panel_segments[-1][0]
    for reveal_index, start, end in panel_segments:
        duration = max(end - start, 1e-3)
        png_path = png_paths.get(reveal_index)
        if png_path is None:
            raise RuntimeError(f"no panel PNG for reveal_index={reveal_index}")
        lines.append(f"file '{_escape_concat_path(png_path)}'")
        lines.append(f"duration {duration:.6f}")
    last_png = png_paths[last_index]
    lines.append(f"file '{_escape_concat_path(last_png)}'")
    concat_path.write_text("\n".join(lines) + "\n")
    return concat_path


def _escape_concat_path(path: Path) -> str:
    """Escape single quotes for ffmpeg concat-demuxer entries."""

    return str(path).replace("'", "'\\''")


def _build_ffmpeg_command(
    *,
    ffmpeg: str,
    source_path: Path,
    concat_path: Path,
    output_path: Path,
    plan: "OverlayPlan",
    include_audio: bool,
    encoder: str,
) -> list[str]:
    metadata = plan.metadata
    overlay_w = plan.display_overlay_width
    overlay_h = plan.display_overlay_height
    x = plan.left_margin_px
    y = plan.top_margin_px
    fps = metadata.fps

    # The overlay stream comes in at 25 fps from the concat demuxer (the
    # default for the ``image2`` decoder). We force its fps to match the
    # source so durations stay frame-accurate after the overlay filter.
    filter_complex = (
        f"[1:v]format=rgba,scale={overlay_w}:{overlay_h},fps={fps:.6f},setpts=PTS-STARTPTS[ovl];"
        f"[0:v][ovl]overlay=x={x}:y={y}:format=auto:eof_action=pass[v]"
    )

    decode_args = _hwaccel_decode_args(encoder)
    command: list[str] = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-progress",
        "pipe:1",
        *decode_args,
        "-i",
        str(source_path),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
    ]

    if include_audio:
        command += ["-map", "0:a?", "-c:a", "copy"]

    command += [
        "-c:v",
        encoder,
        *_encoder_quality_args(encoder),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    return command


def _hwaccel_decode_args(encoder: str) -> list[str]:
    """Pick a matching hardware-accelerated decoder for the source video.

    Pairing decode and encode on the same hwaccel keeps the source frames
    on-GPU as long as possible. We deliberately leave the output format
    unspecified so the filter graph can still consume the frames as
    standard yuv frames after the decoder copies them back to host
    memory; specifying ``-hwaccel_output_format`` would skip that copy
    but breaks the ``overlay`` filter which expects CPU pixel formats.
    """

    if encoder == "h264_videotoolbox":
        return ["-hwaccel", "videotoolbox"]
    if encoder == "h264_nvenc":
        return ["-hwaccel", "cuda"]
    if encoder == "h264_qsv":
        return ["-hwaccel", "qsv"]
    if encoder == "h264_vaapi":
        return ["-hwaccel", "vaapi"]
    return []


def _encoder_quality_args(encoder: str) -> list[str]:
    """Pick reasonable quality knobs for each encoder.

    Targets ~6 Mbps for 1080p60 - visually transparent on telemetry-style
    overlays without ballooning file size. Bitrate-based control is the
    portable knob across every encoder we support.
    """

    if encoder == "h264_videotoolbox":
        return ["-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M"]
    if encoder == "h264_nvenc":
        return ["-preset", "p5", "-rc:v", "vbr", "-cq", "23", "-b:v", "6M"]
    if encoder == "h264_qsv":
        return ["-preset", "medium", "-global_quality", "23", "-b:v", "6M"]
    if encoder == "h264_vaapi":
        return ["-rc_mode", "VBR", "-b:v", "6M"]
    return ["-preset", "veryfast", "-crf", "23"]
