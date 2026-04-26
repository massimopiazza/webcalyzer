import numpy as np
from matplotlib.colors import to_rgb

from webcalyzer.overlay import BACKGROUND, STAGE_COLORS_BGRA, Y_TICK_TARGET, _axis_layout, _draw_rounded_rect, _nice_range, _nice_ticks
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


def test_overlay_three_axis_layout_stays_inside_panel() -> None:
    axes = _axis_layout(320, 120, include_trajectory=True)

    assert axes[2] is not None
    assert max(axis.y + axis.height for axis in axes if axis is not None) < 120


def test_overlay_stage_colors_match_pdf_summary_colors() -> None:
    def bgra_to_rgb01(color: tuple[int, int, int, int]) -> tuple[float, float, float]:
        blue, green, red, _alpha = color
        return (red / 255.0, green / 255.0, blue / 255.0)

    assert bgra_to_rgb01(STAGE_COLORS_BGRA["stage1"]) == to_rgb(SUMMARY_COLORS["stage1"])
    assert bgra_to_rgb01(STAGE_COLORS_BGRA["stage2"]) == to_rgb(SUMMARY_COLORS["stage2"])
