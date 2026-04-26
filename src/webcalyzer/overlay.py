from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np
import pandas as pd

from webcalyzer.models import VideoOverlayConfig
from webcalyzer.video import get_video_metadata, open_capture


@dataclass(frozen=True, slots=True)
class AxisRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PlotSeries:
    x: np.ndarray
    y: np.ndarray
    color: tuple[int, int, int, int]


SUMMARY_COLUMNS = {
    "velocity": ("stage1_velocity_mps", "stage2_velocity_mps"),
    "altitude": ("stage1_altitude_m", "stage2_altitude_m"),
}

STAGE_COLORS_BGRA = {
    "stage1": (180, 119, 31, 255),
    "stage2": (14, 127, 255, 255),
}

WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
GRID = (255, 255, 255, 70)


def render_telemetry_overlay_video(
    video_path: str | Path,
    clean_df: pd.DataFrame,
    output_dir: str | Path,
    config: VideoOverlayConfig,
    rejected_df: pd.DataFrame | None = None,
) -> Path | None:
    if not config.enabled:
        return None

    plot_mode = config.plot_mode.strip().lower()
    if plot_mode not in {"filtered", "with_rejected"}:
        raise ValueError("video_overlay.plot_mode must be 'filtered' or 'with_rejected'")

    source_path = Path(video_path)
    output_path = Path(output_dir) / config.output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = get_video_metadata(source_path)
    overlay_width = _scaled_dimension(metadata.width, config.width_fraction)
    overlay_height = _scaled_dimension(metadata.height, config.height_fraction)
    overlay_width = min(metadata.width, overlay_width)
    overlay_height = min(metadata.height, overlay_height)

    include_rejected = plot_mode == "with_rejected" and rejected_df is not None and not rejected_df.empty
    x_range = _range_for_columns(clean_df, rejected_df if include_rejected else None, ["mission_elapsed_time_s"])
    velocity_range = _range_for_columns(
        clean_df,
        rejected_df if include_rejected else None,
        list(SUMMARY_COLUMNS["velocity"]),
        lower_floor=0.0,
    )
    altitude_range = _range_for_columns(
        clean_df,
        rejected_df if include_rejected else None,
        list(SUMMARY_COLUMNS["altitude"]),
        lower_floor=0.0,
    )
    velocity_axis, altitude_axis = _axis_layout(overlay_width, overlay_height)
    font_scale = _font_scale(overlay_width, overlay_height)
    base_overlay = _draw_base_overlay(
        width=overlay_width,
        height=overlay_height,
        x_range=x_range,
        velocity_range=velocity_range,
        altitude_range=altitude_range,
        velocity_axis=velocity_axis,
        altitude_axis=altitude_axis,
        include_rejected=include_rejected,
    )

    retained_series = _build_series(clean_df, x_range, velocity_range, altitude_range)
    rejected_series = (
        _build_series(rejected_df, x_range, velocity_range, altitude_range) if include_rejected and rejected_df is not None else {}
    )
    reveal_times = _build_reveal_times(retained_series, rejected_series)
    overlay_cache: dict[int, np.ndarray] = {}
    progress = _build_progress_mapper(clean_df)

    temp_path = output_path.with_name(f"{output_path.stem}.noaudio{output_path.suffix}")
    if temp_path.exists():
        temp_path.unlink()
    if output_path.exists():
        output_path.unlink()

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(temp_path), fourcc, metadata.fps, (metadata.width, metadata.height))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open video writer: {temp_path}")

    capture = open_capture(source_path)
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break

            current_time_s = frame_index / metadata.fps if metadata.fps else 0.0
            current_x = progress(current_time_s)
            reveal_index = int(np.searchsorted(reveal_times, current_x, side="right"))
            overlay = overlay_cache.get(reveal_index)
            if overlay is None:
                overlay = base_overlay.copy()
                threshold_x = reveal_times[reveal_index - 1] if reveal_index > 0 else x_range[0] - 1.0
                _draw_summary_data(
                    overlay=overlay,
                    current_x=threshold_x,
                    velocity_axis=velocity_axis,
                    altitude_axis=altitude_axis,
                    retained_series=retained_series,
                    rejected_series=rejected_series,
                    x_range=x_range,
                    velocity_range=velocity_range,
                    altitude_range=altitude_range,
                    font_scale=font_scale,
                    include_rejected=include_rejected,
                )
                overlay_cache[reveal_index] = overlay
            _composite_overlay(frame, overlay)
            writer.write(frame)
            frame_index += 1

            if frame_index % max(1, int(round(metadata.fps * 30))) == 0:
                print(f"[webcalyzer] rendered overlay video frame {frame_index}/{metadata.frame_count}")
    finally:
        capture.release()
        writer.release()

    return _mux_audio_if_available(
        rendered_video=temp_path,
        source_video=source_path,
        target_video=output_path,
        include_audio=config.include_audio,
    )


def _scaled_dimension(source: int, fraction: float) -> int:
    return max(120, int(round(source * max(0.05, min(1.0, fraction)))))


def _axis_layout(width: int, height: int) -> tuple[AxisRect, AxisRect]:
    left = max(64, int(round(width * 0.10)))
    right = max(18, int(round(width * 0.03)))
    top = max(22, int(round(height * 0.06)))
    bottom = max(42, int(round(height * 0.12)))
    gap = max(22, int(round(height * 0.06)))
    axis_height = max(48, int((height - top - bottom - gap) / 2))
    axis_width = max(80, width - left - right)
    velocity_axis = AxisRect(left, top, axis_width, axis_height)
    altitude_axis = AxisRect(left, top + axis_height + gap, axis_width, axis_height)
    return velocity_axis, altitude_axis


def _draw_base_overlay(
    width: int,
    height: int,
    x_range: tuple[float, float],
    velocity_range: tuple[float, float],
    altitude_range: tuple[float, float],
    velocity_axis: AxisRect,
    altitude_axis: AxisRect,
    include_rejected: bool,
) -> np.ndarray:
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    font_scale = _font_scale(width, height)

    _draw_axis(overlay, velocity_axis, x_range, velocity_range, "Velocity [m/s]", font_scale)
    _draw_axis(overlay, altitude_axis, x_range, altitude_range, "Altitude [m]", font_scale)
    _put_text(
        overlay,
        "Mission Elapsed Time [s]",
        (altitude_axis.x + max(0, altitude_axis.width // 2 - 90), height - 12),
        font_scale,
    )
    _draw_legend(overlay, velocity_axis, font_scale, include_rejected)
    return overlay


def _font_scale(width: int, height: int) -> float:
    return max(0.32, min(width / 960.0, height / 432.0) * 0.46)


def _draw_axis(
    overlay: np.ndarray,
    rect: AxisRect,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    label: str,
    font_scale: float,
) -> None:
    _line(overlay, (rect.x, rect.y), (rect.x, rect.y + rect.height), WHITE, thickness=1)
    _line(overlay, (rect.x, rect.y + rect.height), (rect.x + rect.width, rect.y + rect.height), WHITE, thickness=1)

    for tick in np.linspace(x_range[0], x_range[1], 5):
        x = _map_x(float(tick), rect, x_range)
        cv2.line(overlay, (x, rect.y), (x, rect.y + rect.height), GRID, 1, cv2.LINE_AA)
        _put_text(overlay, f"{tick:,.0f}", (x - 14, rect.y + rect.height + 16), font_scale * 0.82)

    for tick in np.linspace(y_range[0], y_range[1], 4):
        y = _map_y(float(tick), rect, y_range)
        cv2.line(overlay, (rect.x, y), (rect.x + rect.width, y), GRID, 1, cv2.LINE_AA)
        _put_text(overlay, f"{tick:,.0f}", (max(1, rect.x - 58), y + 4), font_scale * 0.82)

    _put_text(overlay, label, (rect.x + 4, max(12, rect.y - 6)), font_scale)


def _draw_legend(overlay: np.ndarray, rect: AxisRect, font_scale: float, include_rejected: bool) -> None:
    x = rect.x + rect.width - 150
    y = rect.y + 16
    _line(overlay, (x, y - 4), (x + 28, y - 4), STAGE_COLORS_BGRA["stage1"], thickness=2)
    _put_text(overlay, "Stage 1", (x + 36, y), font_scale * 0.92)
    _line(overlay, (x, y + 16), (x + 28, y + 16), STAGE_COLORS_BGRA["stage2"], thickness=2)
    _put_text(overlay, "Stage 2", (x + 36, y + 20), font_scale * 0.92)
    if include_rejected:
        cv2.circle(overlay, (x + 14, y + 36), 4, STAGE_COLORS_BGRA["stage1"], 1, cv2.LINE_AA)
        _put_text(overlay, "Rejected", (x + 36, y + 40), font_scale * 0.92)


def _build_series(
    df: pd.DataFrame | None,
    x_range: tuple[float, float],
    velocity_range: tuple[float, float],
    altitude_range: tuple[float, float],
) -> dict[str, PlotSeries]:
    if df is None or df.empty:
        return {}

    result: dict[str, PlotSeries] = {}
    for stage_name, color in STAGE_COLORS_BGRA.items():
        for metric_name, columns in SUMMARY_COLUMNS.items():
            column = columns[0] if stage_name == "stage1" else columns[1]
            if column not in df.columns or "mission_elapsed_time_s" not in df.columns:
                continue
            x = pd.to_numeric(df["mission_elapsed_time_s"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
            finite = np.isfinite(x) & np.isfinite(y)
            order = np.argsort(x[finite])
            key = f"{metric_name}:{stage_name}"
            result[key] = PlotSeries(x=x[finite][order], y=y[finite][order], color=color)
    return result


def _build_reveal_times(
    retained_series: dict[str, PlotSeries],
    rejected_series: dict[str, PlotSeries],
) -> np.ndarray:
    arrays = [series.x for series in retained_series.values()]
    arrays.extend(series.x for series in rejected_series.values())
    if not arrays:
        return np.array([], dtype=float)
    return np.unique(np.concatenate(arrays))


def _draw_summary_data(
    overlay: np.ndarray,
    current_x: float,
    velocity_axis: AxisRect,
    altitude_axis: AxisRect,
    retained_series: dict[str, PlotSeries],
    rejected_series: dict[str, PlotSeries],
    x_range: tuple[float, float],
    velocity_range: tuple[float, float],
    altitude_range: tuple[float, float],
    font_scale: float,
    include_rejected: bool,
) -> None:
    for stage in ("stage1", "stage2"):
        _draw_retained_series(
            overlay,
            retained_series.get(f"velocity:{stage}"),
            velocity_axis,
            x_range,
            velocity_range,
            current_x,
        )
        _draw_retained_series(
            overlay,
            retained_series.get(f"altitude:{stage}"),
            altitude_axis,
            x_range,
            altitude_range,
            current_x,
        )
        _draw_rejected_series(
            overlay,
            rejected_series.get(f"velocity:{stage}"),
            velocity_axis,
            x_range,
            velocity_range,
            current_x,
        )
        _draw_rejected_series(
            overlay,
            rejected_series.get(f"altitude:{stage}"),
            altitude_axis,
            x_range,
            altitude_range,
            current_x,
        )

    _draw_legend(overlay, velocity_axis, font_scale, include_rejected)


def _draw_retained_series(
    overlay: np.ndarray,
    series: PlotSeries | None,
    rect: AxisRect,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    current_x: float,
) -> None:
    if series is None or series.x.size == 0:
        return

    mask = series.x <= current_x
    if not np.any(mask):
        return
    points = [
        [_map_x(float(x), rect, x_range), _map_y(float(y), rect, y_range)]
        for x, y in zip(series.x[mask], series.y[mask], strict=True)
    ]
    if len(points) == 1:
        cv2.circle(overlay, tuple(points[0]), 2, series.color, -1, cv2.LINE_AA)
        return
    cv2.polylines(overlay, [np.array(points, dtype=np.int32)], False, series.color, 2, cv2.LINE_AA)


def _draw_rejected_series(
    overlay: np.ndarray,
    series: PlotSeries | None,
    rect: AxisRect,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    current_x: float,
) -> None:
    if series is None or series.x.size == 0:
        return
    mask = series.x <= current_x
    for x, y in zip(series.x[mask], series.y[mask], strict=True):
        point = (_map_x(float(x), rect, x_range), _map_y(float(y), rect, y_range))
        cv2.circle(overlay, point, 4, series.color, 1, cv2.LINE_AA)


def _build_progress_mapper(clean_df: pd.DataFrame):
    if "sample_time_s" not in clean_df.columns or "mission_elapsed_time_s" not in clean_df.columns:
        return lambda time_s: time_s

    sample_times = pd.to_numeric(clean_df["sample_time_s"], errors="coerce").to_numpy(dtype=float)
    met_times = pd.to_numeric(clean_df["mission_elapsed_time_s"], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(sample_times) & np.isfinite(met_times)
    if np.sum(finite) < 2:
        return lambda time_s: time_s

    sample_times = sample_times[finite]
    met_times = met_times[finite]
    order = np.argsort(sample_times)
    sample_times = sample_times[order]
    met_times = met_times[order]

    def map_time(time_s: float) -> float:
        return float(np.interp(time_s, sample_times, met_times, left=met_times[0], right=met_times[-1]))

    return map_time


def _range_for_columns(
    clean_df: pd.DataFrame,
    rejected_df: pd.DataFrame | None,
    columns: list[str],
    lower_floor: float | None = None,
) -> tuple[float, float]:
    arrays: list[np.ndarray] = []
    for df in (clean_df, rejected_df):
        if df is None:
            continue
        for column in columns:
            if column in df.columns:
                arrays.append(pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float))
    values = np.concatenate(arrays) if arrays else np.array([], dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return (0.0, 1.0)

    low = float(np.min(finite))
    high = float(np.max(finite))
    if lower_floor is not None:
        low = min(lower_floor, low)
    if high <= low:
        high = low + 1.0
    padding = (high - low) * 0.06
    return (low, high + padding)


def _map_x(value: float, rect: AxisRect, x_range: tuple[float, float]) -> int:
    low, high = x_range
    if high <= low:
        return rect.x
    fraction = max(0.0, min(1.0, (value - low) / (high - low)))
    return int(round(rect.x + fraction * rect.width))


def _map_y(value: float, rect: AxisRect, y_range: tuple[float, float]) -> int:
    low, high = y_range
    if high <= low:
        return rect.y + rect.height
    fraction = max(0.0, min(1.0, (value - low) / (high - low)))
    return int(round(rect.y + rect.height - fraction * rect.height))


def _line(
    image: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int, int],
    thickness: int,
) -> None:
    cv2.line(image, start, end, BLACK, thickness + 2, cv2.LINE_AA)
    cv2.line(image, start, end, color, thickness, cv2.LINE_AA)


def _put_text(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    font_scale: float,
    color: tuple[int, int, int, int] = WHITE,
) -> None:
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, BLACK, 3, cv2.LINE_AA)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1, cv2.LINE_AA)


def _composite_overlay(frame: np.ndarray, overlay: np.ndarray) -> None:
    overlay_height, overlay_width = overlay.shape[:2]
    roi = frame[:overlay_height, :overlay_width]
    alpha = overlay[:, :, 3:4].astype(np.float32) / 255.0
    blended = overlay[:, :, :3].astype(np.float32) * alpha + roi.astype(np.float32) * (1.0 - alpha)
    roi[:] = np.clip(blended, 0, 255).astype(np.uint8)


def _mux_audio_if_available(
    rendered_video: Path,
    source_video: Path,
    target_video: Path,
    include_audio: bool,
) -> Path:
    if not include_audio:
        rendered_video.replace(target_video)
        return target_video

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        rendered_video.replace(target_video)
        return target_video

    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(rendered_video),
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-shortest",
        str(target_video),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        rendered_video.replace(target_video)
        return target_video

    rendered_video.unlink(missing_ok=True)
    return target_video
