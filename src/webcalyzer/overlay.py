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
    segments: tuple[tuple[np.ndarray, np.ndarray], ...]
    color: tuple[int, int, int, int]


SUMMARY_COLUMNS = {
    "velocity": ("stage1_velocity_mps", "stage2_velocity_mps"),
    "altitude": ("stage1_altitude_m", "stage2_altitude_m"),
}

ALTITUDE_SCALE = 0.001

STAGE_COLORS_BGRA = {
    "stage1": (180, 119, 31, 255),
    "stage2": (14, 127, 255, 255),
}

WHITE = (255, 255, 255, 255)
GRID = (255, 255, 255, 70)
BACKGROUND = (0, 0, 0, 153)
X_TICK_TARGET = 5
Y_TICK_TARGET = 4

# Quantize panel reveals onto a 0.5 s MET grid. Plot updates faster than
# this are imperceptible at typical playback fps and just multiply the
# panel cache + concat list size with no visual benefit.
REVEAL_QUANTIZE_STEP_S = 0.5


@dataclass(frozen=True, slots=True)
class OverlayPlan:
    """Everything the renderers need to draw and time the overlay panel.

    Both the OpenCV path and the FFmpeg path consume this plan. Building
    it once per run also means the panel cache is shared instead of being
    rebuilt by whichever engine runs.
    """

    metadata: object
    display_overlay_width: int
    display_overlay_height: int
    top_margin_px: int
    left_margin_px: int
    panel_cache: dict[int, np.ndarray]
    panel_segments: list[tuple[int, float, float]]


def render_telemetry_overlay_video(
    video_path: str | Path,
    clean_df: pd.DataFrame,
    output_dir: str | Path,
    config: VideoOverlayConfig,
    rejected_df: pd.DataFrame | None = None,
    trajectory_df: pd.DataFrame | None = None,
    *,
    engine: str = "auto",
    encoder: str = "auto",
) -> Path | None:
    if not config.enabled:
        return None

    plot_mode = config.plot_mode.strip().lower()
    if plot_mode not in {"filtered", "with_rejected"}:
        raise ValueError("video_overlay.plot_mode must be 'filtered' or 'with_rejected'")

    source_path = Path(video_path)
    output_path = Path(output_dir) / config.output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plan = _build_overlay_plan(
        source_path=source_path,
        clean_df=clean_df,
        rejected_df=rejected_df,
        trajectory_df=trajectory_df,
        config=config,
        plot_mode=plot_mode,
    )

    selected_engine = _resolve_overlay_engine(engine)
    if selected_engine == "ffmpeg":
        from webcalyzer.overlay_ffmpeg import render_via_ffmpeg

        try:
            return render_via_ffmpeg(
                source_path=source_path,
                output_path=output_path,
                plan=plan,
                include_audio=config.include_audio,
                encoder=encoder,
            )
        except Exception as exc:  # pragma: no cover - safety fallback
            print(f"[webcalyzer] ffmpeg overlay engine failed ({exc}); falling back to opencv")

    return _render_via_opencv(
        source_path=source_path,
        output_path=output_path,
        plan=plan,
        include_audio=config.include_audio,
    )


def _resolve_overlay_engine(engine: str) -> str:
    """Resolve ``auto`` to ``ffmpeg`` when ffmpeg is on PATH, else ``opencv``."""

    if engine not in {"auto", "ffmpeg", "opencv"}:
        raise ValueError(
            f"Unknown overlay engine {engine!r}; expected 'auto', 'ffmpeg', or 'opencv'."
        )
    if engine == "ffmpeg":
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "overlay engine 'ffmpeg' was requested but ffmpeg is not on PATH."
            )
        return "ffmpeg"
    if engine == "opencv":
        return "opencv"
    # auto
    return "ffmpeg" if shutil.which("ffmpeg") is not None else "opencv"


def _build_overlay_plan(
    *,
    source_path: Path,
    clean_df: pd.DataFrame,
    rejected_df: pd.DataFrame | None,
    trajectory_df: pd.DataFrame | None,
    config: VideoOverlayConfig,
    plot_mode: str,
) -> OverlayPlan:
    metadata = get_video_metadata(source_path)
    display_overlay_width = _scaled_dimension(metadata.width, config.width_fraction)
    display_overlay_height = _scaled_dimension(metadata.height, config.height_fraction)
    margin_px = _corner_margin_px(metadata.height)
    top_margin_px = min(margin_px, max(0, metadata.height - display_overlay_height))
    left_margin_px = min(margin_px, max(0, metadata.width - display_overlay_width))
    display_overlay_width = min(metadata.width - left_margin_px, display_overlay_width)
    display_overlay_height = min(metadata.height - top_margin_px, display_overlay_height)
    render_scale = _overlay_render_scale(metadata.width, metadata.height)
    overlay_width = display_overlay_width * render_scale
    overlay_height = display_overlay_height * render_scale

    include_rejected = plot_mode == "with_rejected" and rejected_df is not None and not rejected_df.empty
    include_trajectory = _has_trajectory_data(trajectory_df)
    x_range = _nice_range(
        _range_for_columns(clean_df, rejected_df if include_rejected else None, ["mission_elapsed_time_s"], lower_floor=0.0),
        target_count=X_TICK_TARGET,
    )
    velocity_range = _nice_range(
        _range_for_columns(
            clean_df,
            rejected_df if include_rejected else None,
            list(SUMMARY_COLUMNS["velocity"]),
            lower_floor=0.0,
        ),
        target_count=Y_TICK_TARGET,
    )
    altitude_range = _nice_range(
        _range_for_columns(
            clean_df,
            rejected_df if include_rejected else None,
            list(SUMMARY_COLUMNS["altitude"]),
            lower_floor=0.0,
        ),
        target_count=Y_TICK_TARGET,
    )
    downrange_range = _nice_range(
        _range_for_trajectory(trajectory_df, lower_floor=0.0),
        target_count=Y_TICK_TARGET,
    )
    velocity_axis, altitude_axis, downrange_axis = _axis_layout(overlay_width, overlay_height, include_trajectory)
    font_scale = _font_scale(overlay_width, overlay_height)
    base_overlay = _draw_base_overlay(
        width=overlay_width,
        height=overlay_height,
        x_range=x_range,
        velocity_range=velocity_range,
        altitude_range=altitude_range,
        downrange_range=downrange_range,
        velocity_axis=velocity_axis,
        altitude_axis=altitude_axis,
        downrange_axis=downrange_axis,
        include_rejected=include_rejected,
    )

    retained_series = _build_series(clean_df, x_range, velocity_range, altitude_range)
    rejected_series = (
        _build_series(rejected_df, x_range, velocity_range, altitude_range) if include_rejected and rejected_df is not None else {}
    )
    trajectory_series = (
        _build_trajectory_series(trajectory_df, x_range, downrange_range) if include_trajectory and trajectory_df is not None else {}
    )
    reveal_times = _build_reveal_times(retained_series, rejected_series, trajectory_series)

    panel_cache = _build_panel_cache(
        base_overlay=base_overlay,
        reveal_times=reveal_times,
        x_range=x_range,
        velocity_range=velocity_range,
        altitude_range=altitude_range,
        downrange_range=downrange_range,
        velocity_axis=velocity_axis,
        altitude_axis=altitude_axis,
        downrange_axis=downrange_axis,
        retained_series=retained_series,
        rejected_series=rejected_series,
        trajectory_series=trajectory_series,
        font_scale=font_scale,
        include_rejected=include_rejected,
        render_scale=render_scale,
        display_overlay_width=display_overlay_width,
        display_overlay_height=display_overlay_height,
    )
    panel_segments = _build_panel_segments(
        clean_df=clean_df,
        reveal_times=reveal_times,
        duration_s=metadata.duration_s,
    )

    return OverlayPlan(
        metadata=metadata,
        display_overlay_width=display_overlay_width,
        display_overlay_height=display_overlay_height,
        top_margin_px=top_margin_px,
        left_margin_px=left_margin_px,
        panel_cache=panel_cache,
        panel_segments=panel_segments,
    )


def _build_panel_cache(
    *,
    base_overlay: np.ndarray,
    reveal_times: np.ndarray,
    x_range: tuple[float, float],
    velocity_range: tuple[float, float],
    altitude_range: tuple[float, float],
    downrange_range: tuple[float, float],
    velocity_axis: AxisRect,
    altitude_axis: AxisRect,
    downrange_axis: AxisRect | None,
    retained_series: dict[str, "PlotSeries"],
    rejected_series: dict[str, "PlotSeries"],
    trajectory_series: dict[str, "PlotSeries"],
    font_scale: float,
    include_rejected: bool,
    render_scale: int,
    display_overlay_width: int,
    display_overlay_height: int,
) -> dict[int, np.ndarray]:
    cache: dict[int, np.ndarray] = {}
    panel_count = int(reveal_times.size) + 1
    for reveal_index in range(panel_count):
        overlay = base_overlay.copy()
        threshold_x = (
            float(reveal_times[reveal_index - 1])
            if reveal_index > 0
            else x_range[0] - 1.0
        )
        _draw_summary_data(
            overlay=overlay,
            current_x=threshold_x,
            velocity_axis=velocity_axis,
            altitude_axis=altitude_axis,
            downrange_axis=downrange_axis,
            retained_series=retained_series,
            rejected_series=rejected_series,
            trajectory_series=trajectory_series,
            x_range=x_range,
            velocity_range=velocity_range,
            altitude_range=altitude_range,
            downrange_range=downrange_range,
            font_scale=font_scale,
            include_rejected=include_rejected,
        )
        if render_scale != 1:
            overlay = cv2.resize(
                overlay,
                (display_overlay_width, display_overlay_height),
                interpolation=cv2.INTER_AREA,
            )
        cache[reveal_index] = overlay
    return cache


def _build_panel_segments(
    *,
    clean_df: pd.DataFrame,
    reveal_times: np.ndarray,
    duration_s: float,
) -> list[tuple[int, float, float]]:
    """Compute (reveal_index, source_start_s, source_end_s) for each panel.

    Source-time boundaries are obtained by inverting the MET↔source-time
    mapping derived from clean_df. When the inverse cannot be built (e.g.
    no parsed MET rows) the panel sequence collapses to a single empty
    panel that covers the entire video duration.
    """

    inverse = _build_inverse_progress_mapper(clean_df)
    boundaries: list[float] = [0.0]
    for met in reveal_times:
        boundaries.append(min(max(0.0, inverse(float(met))), duration_s))
    boundaries.append(duration_s)
    segments: list[tuple[int, float, float]] = []
    for index, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:], strict=True)):
        if end <= start:
            continue
        segments.append((index, float(start), float(end)))
    if not segments:
        segments = [(0, 0.0, duration_s)]
    return segments


def _build_inverse_progress_mapper(clean_df: pd.DataFrame):
    """Inverse of :func:`_build_progress_mapper`: maps MET → source video time."""

    if "sample_time_s" not in clean_df.columns or "mission_elapsed_time_s" not in clean_df.columns:
        return lambda met: float(met)

    sample_times = pd.to_numeric(clean_df["sample_time_s"], errors="coerce").to_numpy(dtype=float)
    met_times = pd.to_numeric(clean_df["mission_elapsed_time_s"], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(sample_times) & np.isfinite(met_times)
    if np.sum(finite) < 2:
        return lambda met: float(met)

    sample_times = sample_times[finite]
    met_times = met_times[finite]
    order = np.argsort(met_times)
    met_times = met_times[order]
    sample_times = sample_times[order]

    def map_back(met: float) -> float:
        return float(np.interp(met, met_times, sample_times, left=sample_times[0], right=sample_times[-1]))

    return map_back


def _render_via_opencv(
    *,
    source_path: Path,
    output_path: Path,
    plan: OverlayPlan,
    include_audio: bool,
) -> Path | None:
    metadata = plan.metadata
    temp_path = output_path.with_name(f"{output_path.stem}.noaudio{output_path.suffix}")
    if temp_path.exists():
        temp_path.unlink()
    if output_path.exists():
        output_path.unlink()

    writer = _open_video_writer(temp_path, metadata.fps, (metadata.width, metadata.height))
    capture = open_capture(source_path)

    # Build a per-frame index → reveal_index lookup from the panel segments.
    fps = metadata.fps if metadata.fps else 1.0
    segment_starts = np.asarray([seg[1] for seg in plan.panel_segments], dtype=float)
    segment_indices = np.asarray([seg[0] for seg in plan.panel_segments], dtype=int)

    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            current_time_s = frame_index / fps
            slot = int(np.searchsorted(segment_starts, current_time_s, side="right") - 1)
            slot = max(0, min(slot, segment_indices.size - 1))
            reveal_index = int(segment_indices[slot])
            overlay = plan.panel_cache[reveal_index]
            _composite_overlay(
                frame,
                overlay,
                top_margin_px=plan.top_margin_px,
                left_margin_px=plan.left_margin_px,
            )
            writer.write(frame)
            frame_index += 1
            if frame_index % max(1, int(round(fps * 30))) == 0:
                print(f"[webcalyzer] rendered overlay video frame {frame_index}/{metadata.frame_count}")
    finally:
        capture.release()
        writer.release()

    return _mux_audio_if_available(
        rendered_video=temp_path,
        source_video=source_path,
        target_video=output_path,
        include_audio=include_audio,
    )


def _scaled_dimension(source: int, fraction: float) -> int:
    return max(120, int(round(source * max(0.05, min(1.0, fraction)))))


def _corner_margin_px(frame_height: int) -> int:
    """Symmetric pixel margin used for both the top and the left side of the
    overlay so the panel sits in a balanced top-left inset rather than
    flush against the screen edges."""

    return max(8, int(round(frame_height * 0.012)))


def _top_margin_px(frame_height: int) -> int:
    """Back-compat alias kept for callers that may import the old name."""

    return _corner_margin_px(frame_height)


def _overlay_render_scale(frame_width: int, frame_height: int) -> int:
    if frame_width >= 3840 or frame_height >= 2160:
        return 3
    if frame_width >= 1920 or frame_height >= 1080:
        return 2
    return 1


def _open_video_writer(path: Path, fps: float, size: tuple[int, int]) -> cv2.VideoWriter:
    for codec in ("avc1", "H264", "mp4v"):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            writer.set(cv2.VIDEOWRITER_PROP_QUALITY, 100)
            return writer
        writer.release()
    raise RuntimeError(f"Failed to open video writer: {path}")


def _axis_layout(width: int, height: int, include_trajectory: bool = False) -> tuple[AxisRect, AxisRect, AxisRect | None]:
    left = max(64, int(round(width * 0.10)))
    right = max(18, int(round(width * 0.03)))
    axis_width = max(80, width - left - right)
    if include_trajectory:
        top = max(16, int(round(height * 0.05)))
        bottom = max(34, int(round(height * 0.10)))
        gap = max(12, int(round(height * 0.04)))
        available_height = max(54, height - top - bottom - 2 * gap)
        axis_height = max(18, int(available_height / 3))
        velocity_axis = AxisRect(left, top, axis_width, axis_height)
        altitude_axis = AxisRect(left, top + axis_height + gap, axis_width, axis_height)
        downrange_axis = AxisRect(left, top + 2 * (axis_height + gap), axis_width, axis_height)
        return velocity_axis, altitude_axis, downrange_axis
    top = max(22, int(round(height * 0.06)))
    bottom = max(42, int(round(height * 0.12)))
    gap = max(22, int(round(height * 0.06)))
    axis_height = max(48, int((height - top - bottom - gap) / 2))
    velocity_axis = AxisRect(left, top, axis_width, axis_height)
    altitude_axis = AxisRect(left, top + axis_height + gap, axis_width, axis_height)
    return velocity_axis, altitude_axis, None


def _draw_base_overlay(
    width: int,
    height: int,
    x_range: tuple[float, float],
    velocity_range: tuple[float, float],
    altitude_range: tuple[float, float],
    downrange_range: tuple[float, float],
    velocity_axis: AxisRect,
    altitude_axis: AxisRect,
    downrange_axis: AxisRect | None,
    include_rejected: bool,
) -> np.ndarray:
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    font_scale = _font_scale(width, height)
    _draw_rounded_rect(
        overlay,
        (0, 0),
        (width - 1, height - 1),
        radius=max(18, int(round(min(width, height) * 0.045))),
        color=BACKGROUND,
    )

    _draw_axis(overlay, velocity_axis, x_range, velocity_range, "Velocity [m/s]", font_scale)
    _draw_axis(overlay, altitude_axis, x_range, altitude_range, "Altitude [km]", font_scale)
    bottom_axis = altitude_axis
    if downrange_axis is not None:
        _draw_axis(overlay, downrange_axis, x_range, downrange_range, "Downrange [km]", font_scale)
        bottom_axis = downrange_axis
    _put_text(
        overlay,
        "Mission Elapsed Time [s]",
        (bottom_axis.x + max(0, bottom_axis.width // 2 - 90), height - 12),
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
    axis_thickness = max(1, int(round(font_scale * 2.0)))
    grid_thickness = max(1, axis_thickness // 2)
    _line(overlay, (rect.x, rect.y), (rect.x, rect.y + rect.height), WHITE, thickness=axis_thickness)
    _line(overlay, (rect.x, rect.y + rect.height), (rect.x + rect.width, rect.y + rect.height), WHITE, thickness=axis_thickness)

    for tick in _nice_ticks(x_range[0], x_range[1], target_count=X_TICK_TARGET):
        x = _map_x(float(tick), rect, x_range)
        cv2.line(overlay, (x, rect.y), (x, rect.y + rect.height), GRID, grid_thickness, cv2.LINE_AA)
        _put_text(overlay, _format_tick(float(tick)), (x - int(24 * font_scale), rect.y + rect.height + int(34 * font_scale)), font_scale * 0.82)

    for tick in _nice_ticks(y_range[0], y_range[1], target_count=Y_TICK_TARGET):
        y = _map_y(float(tick), rect, y_range)
        cv2.line(overlay, (rect.x, y), (rect.x + rect.width, y), GRID, grid_thickness, cv2.LINE_AA)
        _put_text(overlay, _format_tick(float(tick)), (max(1, rect.x - int(126 * font_scale)), y + int(8 * font_scale)), font_scale * 0.82)

    _put_text(overlay, label, (rect.x + 4, max(12, rect.y - 6)), font_scale)


def _draw_legend(overlay: np.ndarray, rect: AxisRect, font_scale: float, include_rejected: bool) -> None:
    x = rect.x + rect.width - int(round(320 * font_scale))
    y = rect.y + int(round(34 * font_scale))
    line_length = int(round(60 * font_scale))
    line_gap = int(round(42 * font_scale))
    line_thickness = max(2, int(round(font_scale * 2.0)))
    _line(overlay, (x, y - int(8 * font_scale)), (x + line_length, y - int(8 * font_scale)), STAGE_COLORS_BGRA["stage1"], thickness=line_thickness)
    _put_text(overlay, "Stage 1", (x + line_length + int(14 * font_scale), y), font_scale * 0.92)
    _line(overlay, (x, y + line_gap - int(8 * font_scale)), (x + line_length, y + line_gap - int(8 * font_scale)), STAGE_COLORS_BGRA["stage2"], thickness=line_thickness)
    _put_text(overlay, "Stage 2", (x + line_length + int(14 * font_scale), y + line_gap), font_scale * 0.92)
    if include_rejected:
        cv2.circle(overlay, (x + line_length // 2, y + 2 * line_gap - int(8 * font_scale)), max(4, int(8 * font_scale)), STAGE_COLORS_BGRA["stage1"], line_thickness, cv2.LINE_AA)
        _put_text(overlay, "Rejected", (x + line_length + int(14 * font_scale), y + 2 * line_gap), font_scale * 0.92)


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
            y = _display_values(pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float), column)
            finite_x = np.isfinite(x)
            order = np.argsort(x[finite_x])
            ordered_x = x[finite_x][order]
            ordered_y = y[finite_x][order]
            finite = np.isfinite(ordered_y)
            key = f"{metric_name}:{stage_name}"
            result[key] = PlotSeries(
                x=ordered_x[finite],
                y=ordered_y[finite],
                segments=_finite_segments(ordered_x, ordered_y),
                color=color,
            )
    return result


def _has_trajectory_data(trajectory_df: pd.DataFrame | None) -> bool:
    if trajectory_df is None or trajectory_df.empty:
        return False
    required = {"stage", "mission_elapsed_time_s", "downrange_m"}
    return required.issubset(set(trajectory_df.columns)) and trajectory_df["downrange_m"].notna().any()


def _build_trajectory_series(
    trajectory_df: pd.DataFrame | None,
    x_range: tuple[float, float],
    downrange_range: tuple[float, float],
) -> dict[str, PlotSeries]:
    if trajectory_df is None or trajectory_df.empty:
        return {}

    result: dict[str, PlotSeries] = {}
    for stage_name, color in STAGE_COLORS_BGRA.items():
        stage_df = trajectory_df[trajectory_df["stage"] == stage_name]
        if stage_df.empty:
            continue
        x = pd.to_numeric(stage_df["mission_elapsed_time_s"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(stage_df["downrange_m"], errors="coerce").to_numpy(dtype=float) * ALTITUDE_SCALE
        finite_x = np.isfinite(x)
        order = np.argsort(x[finite_x])
        ordered_x = x[finite_x][order]
        ordered_y = y[finite_x][order]
        finite = np.isfinite(ordered_y)
        result[f"downrange:{stage_name}"] = PlotSeries(
            x=ordered_x[finite],
            y=ordered_y[finite],
            segments=_finite_segments(ordered_x, ordered_y),
            color=color,
        )
    return result


def _display_values(values: np.ndarray, column: str) -> np.ndarray:
    if column.endswith("_altitude_m"):
        return values * ALTITUDE_SCALE
    return values


def _finite_segments(x: np.ndarray, y: np.ndarray) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    start: int | None = None
    finite = np.isfinite(x) & np.isfinite(y)
    for index, is_finite in enumerate(finite):
        if is_finite and start is None:
            start = index
        if start is not None and (not is_finite or index == len(finite) - 1):
            end = index if is_finite and index == len(finite) - 1 else index - 1
            segments.append((x[start : end + 1], y[start : end + 1]))
            start = None
    return tuple(segments)


def _build_reveal_times(
    retained_series: dict[str, PlotSeries],
    rejected_series: dict[str, PlotSeries],
    trajectory_series: dict[str, PlotSeries],
) -> np.ndarray:
    arrays = [series.x for series in retained_series.values()]
    arrays.extend(series.x for series in rejected_series.values())
    arrays.extend(series.x for series in trajectory_series.values())
    if not arrays:
        return np.array([], dtype=float)
    times = np.unique(np.concatenate(arrays))
    return _quantize_reveal_times(times, step_s=REVEAL_QUANTIZE_STEP_S)


def _quantize_reveal_times(times: np.ndarray, *, step_s: float) -> np.ndarray:
    """Round reveal times onto a fixed MET grid so we don't generate one
    overlay panel per integration step.

    Trajectory series produce a sample every ``integration_step_s`` (often
    50–100 ms), which would otherwise give us thousands of unique panels
    even though the visual change between adjacent panels is imperceptible
    at typical playback fps. Quantizing to ``step_s`` caps the panel count
    at ``ceil(span_s / step_s) + 1`` while keeping reveals frame-accurate
    at human perception scales.
    """

    if times.size == 0 or step_s <= 0:
        return times
    bins = np.round(times / step_s).astype(np.int64)
    _, first_indices = np.unique(bins, return_index=True)
    return np.sort(times[first_indices])


def _draw_summary_data(
    overlay: np.ndarray,
    current_x: float,
    velocity_axis: AxisRect,
    altitude_axis: AxisRect,
    downrange_axis: AxisRect | None,
    retained_series: dict[str, PlotSeries],
    rejected_series: dict[str, PlotSeries],
    trajectory_series: dict[str, PlotSeries],
    x_range: tuple[float, float],
    velocity_range: tuple[float, float],
    altitude_range: tuple[float, float],
    downrange_range: tuple[float, float],
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
        if downrange_axis is not None:
            _draw_retained_series(
                overlay,
                trajectory_series.get(f"downrange:{stage}"),
                downrange_axis,
                x_range,
                downrange_range,
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
    line_thickness = max(2, int(round(rect.height / 85)))
    for x_values, y_values in series.segments:
        mask = x_values <= current_x
        if np.count_nonzero(mask) < 2:
            continue
        points = [
            [_map_x(float(x), rect, x_range), _map_y(float(y), rect, y_range)]
            for x, y in zip(x_values[mask], y_values[mask], strict=True)
        ]
        cv2.polylines(overlay, [np.array(points, dtype=np.int32)], False, series.color, line_thickness, cv2.LINE_AA)


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
    radius = max(4, int(round(rect.height / 45)))
    thickness = max(1, int(round(rect.height / 120)))
    for x, y in zip(series.x[mask], series.y[mask], strict=True):
        point = (_map_x(float(x), rect, x_range), _map_y(float(y), rect, y_range))
        cv2.circle(overlay, point, radius, series.color, thickness, cv2.LINE_AA)


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
                arrays[-1] = _display_values(arrays[-1], column)
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


def _range_for_trajectory(
    trajectory_df: pd.DataFrame | None,
    lower_floor: float | None = None,
) -> tuple[float, float]:
    if trajectory_df is None or trajectory_df.empty or "downrange_m" not in trajectory_df.columns:
        return (0.0, 1.0)
    values = pd.to_numeric(trajectory_df["downrange_m"], errors="coerce").to_numpy(dtype=float) * ALTITUDE_SCALE
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


def _nice_range(value_range: tuple[float, float], target_count: int) -> tuple[float, float]:
    ticks = _nice_ticks(value_range[0], value_range[1], target_count=target_count, clip_to_range=False)
    return (float(ticks[0]), float(ticks[-1]))


def _nice_ticks(low: float, high: float, target_count: int, *, clip_to_range: bool = True) -> np.ndarray:
    if not np.isfinite(low) or not np.isfinite(high):
        return np.array([0.0, 1.0])
    if high <= low:
        high = low + 1.0
    step = _nice_step((high - low) / max(1, target_count))
    tick_low = np.floor(low / step) * step
    tick_high = np.ceil(high / step) * step
    ticks = np.arange(tick_low, tick_high + step * 0.5, step)
    while ticks.size > target_count + 3:
        step = _nice_step(step * 1.5)
        tick_low = np.floor(low / step) * step
        tick_high = np.ceil(high / step) * step
        ticks = np.arange(tick_low, tick_high + step * 0.5, step)
    if clip_to_range:
        eps = step * 1e-9
        ticks = ticks[(ticks >= low - eps) & (ticks <= high + eps)]
    return ticks


def _nice_step(raw_step: float) -> float:
    if raw_step <= 0 or not np.isfinite(raw_step):
        return 1.0
    exponent = np.floor(np.log10(raw_step))
    base = 10 ** exponent
    fraction = raw_step / base
    if fraction <= 1:
        nice_fraction = 1.0
    elif fraction <= 2:
        nice_fraction = 2.0
    elif fraction <= 2.5:
        nice_fraction = 2.5
    elif fraction <= 5:
        nice_fraction = 5.0
    else:
        nice_fraction = 10.0
    return float(nice_fraction * base)


def _format_tick(value: float) -> str:
    if abs(value) >= 100 or abs(value - round(value)) < 1e-9:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.1f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


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
    cv2.line(image, start, end, color, thickness, cv2.LINE_AA)


def _put_text(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    font_scale: float,
    color: tuple[int, int, int, int] = WHITE,
) -> None:
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1, cv2.LINE_AA)


def _draw_rounded_rect(
    image: np.ndarray,
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    radius: int,
    color: tuple[int, int, int, int],
) -> None:
    x0, y0 = top_left
    x1, y1 = bottom_right
    radius = max(0, min(radius, (x1 - x0) // 2, (y1 - y0) // 2))
    if radius == 0:
        cv2.rectangle(image, top_left, bottom_right, color, -1)
        return
    cv2.rectangle(image, (x0 + radius, y0), (x1 - radius, y1), color, -1)
    cv2.rectangle(image, (x0, y0 + radius), (x1, y1 - radius), color, -1)
    cv2.circle(image, (x0 + radius, y0 + radius), radius, color, -1, cv2.LINE_AA)
    cv2.circle(image, (x1 - radius, y0 + radius), radius, color, -1, cv2.LINE_AA)
    cv2.circle(image, (x0 + radius, y1 - radius), radius, color, -1, cv2.LINE_AA)
    cv2.circle(image, (x1 - radius, y1 - radius), radius, color, -1, cv2.LINE_AA)


def _composite_overlay(
    frame: np.ndarray,
    overlay: np.ndarray,
    top_margin_px: int,
    left_margin_px: int = 0,
) -> None:
    overlay_height, overlay_width = overlay.shape[:2]
    y0 = max(0, min(frame.shape[0] - overlay_height, top_margin_px))
    x0 = max(0, min(frame.shape[1] - overlay_width, left_margin_px))
    roi = frame[y0 : y0 + overlay_height, x0 : x0 + overlay_width]
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
