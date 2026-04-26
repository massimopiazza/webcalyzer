import numpy as np

from webcalyzer.overlay import BACKGROUND, Y_TICK_TARGET, _draw_rounded_rect, _nice_range, _nice_ticks


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
