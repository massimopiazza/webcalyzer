import numpy as np
from matplotlib.colors import to_rgb

from webcalyzer.overlay import (
    BACKGROUND,
    PREVIEW_GIF_DURATION_S,
    PREVIEW_GIF_FPS,
    PREVIEW_GIF_MAX_HEIGHT,
    PREVIEW_GIF_MAX_WIDTH,
    STAGE_COLORS_BGRA,
    Y_TICK_TARGET,
    _axis_layout,
    _build_preview_gif_command,
    _draw_rounded_rect,
    _nice_range,
    _nice_ticks,
)
from webcalyzer.plotting import SUMMARY_COLORS


def test_overlay_ticks_do_not_label_values_outside_axis_range() -> None:
    ticks = _nice_ticks(0.0, 250.0, target_count=Y_TICK_TARGET)

    assert np.all(ticks <= 250.0)
    assert 300.0 not in ticks


def test_overlay_nice_range_and_ticks_use_same_target_density() -> None:
    axis_range = _nice_range((0.0, 236.0), target_count=Y_TICK_TARGET)
    ticks = _nice_ticks(axis_range[0], axis_range[1], target_count=Y_TICK_TARGET)

    assert axis_range == (0.0, 300.0)
    assert 300.0 in ticks


def test_overlay_background_is_transparent_rounded_rectangle() -> None:
    image = np.zeros((80, 100, 4), dtype=np.uint8)

    _draw_rounded_rect(image, (0, 0), (99, 79), radius=16, color=BACKGROUND)

    assert tuple(image[40, 50]) == BACKGROUND
    assert image[0, 0, 3] == 0


def test_overlay_four_axis_layout_stays_inside_panel() -> None:
    axes = _axis_layout(320, 120, include_trajectory=True)

    assert axes[2] is not None
    assert axes[3] is not None
    assert axes[3].y < axes[2].y
    assert max(axis.y + axis.height for axis in axes if axis is not None) < 120


def test_overlay_stage_colors_match_pdf_summary_colors() -> None:
    def bgra_to_rgb01(color: tuple[int, int, int, int]) -> tuple[float, float, float]:
        blue, green, red, _alpha = color
        return (red / 255.0, green / 255.0, blue / 255.0)

    assert bgra_to_rgb01(STAGE_COLORS_BGRA["stage1"]) == to_rgb(SUMMARY_COLORS["stage1"])
    assert bgra_to_rgb01(STAGE_COLORS_BGRA["stage2"]) == to_rgb(SUMMARY_COLORS["stage2"])


def test_preview_gif_command_remaps_full_clip_to_fixed_duration(tmp_path) -> None:
    command = _build_preview_gif_command(
        ffmpeg="ffmpeg",
        source_path=tmp_path / "telemetry_overlay.mp4",
        target_path=tmp_path / "telemetry_overlay.gif",
        source_duration_s=840.0,
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert f"fps={PREVIEW_GIF_FPS}" in filter_complex
    assert f"scale={PREVIEW_GIF_MAX_WIDTH}:{PREVIEW_GIF_MAX_HEIGHT}" in filter_complex
    assert f"trim=duration={PREVIEW_GIF_DURATION_S:.6f}" in filter_complex
    assert "setpts=0.0178571428571*PTS" in filter_complex
    assert "palettegen=max_colors=128" in filter_complex
    assert command[-1].endswith("telemetry_overlay.gif")
