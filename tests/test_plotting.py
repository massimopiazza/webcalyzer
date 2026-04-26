import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
import pandas as pd

from webcalyzer.plotting import (
    FILTERED_ALPHA,
    INTERPOLATED_COLORS,
    SUMMARY_COLORS,
    _plot_coverage,
    _plot_downrange,
    _plot_metric,
)


def test_coverage_points_use_sixty_percent_alpha() -> None:
    df = pd.DataFrame(
        {
            "mission_elapsed_time_s": [0.0, 1.0],
            "stage1_velocity_mps": [100.0, None],
            "stage1_altitude_m": [None, 1000.0],
        }
    )
    fig, axis = plt.subplots()
    try:
        _plot_coverage(axis, df, "stage1_velocity_mps", "stage1_altitude_m", "Coverage")

        assert [collection.get_alpha() for collection in axis.collections] == [0.6, 0.6]
    finally:
        plt.close(fig)


def test_summary_metric_distinguishes_filtered_and_interpolated_telemetry() -> None:
    clean_df = pd.DataFrame(
        {
            "mission_elapsed_time_s": [0.0, 1.0],
            "stage1_velocity_mps": [0.0, 10.0],
            "stage2_velocity_mps": [None, 20.0],
        }
    )
    trajectory_df = pd.DataFrame(
        {
            "stage": ["stage1", "stage1", "stage2", "stage2"],
            "mission_elapsed_time_s": [0.0, 1.0, 1.0, 2.0],
            "velocity_mps": [0.0, 10.0, 20.0, 30.0],
            "altitude_m": [0.0, 0.0, 0.0, 0.0],
            "downrange_m": [0.0, 10.0, 10.0, 30.0],
        }
    )
    fig, axis = plt.subplots()
    try:
        _plot_metric(
            axis,
            clean_df,
            "stage1_velocity_mps",
            "stage2_velocity_mps",
            ylabel="Velocity [m/s]",
            rejected_df=None,
            trajectory_df=trajectory_df,
            metric_name="velocity",
        )

        lines = axis.lines
        assert lines[0].get_alpha() == FILTERED_ALPHA
        assert lines[1].get_alpha() == FILTERED_ALPHA
        assert lines[0].get_color() == SUMMARY_COLORS["stage1"]
        assert lines[1].get_color() == SUMMARY_COLORS["stage2"]
        assert lines[0].get_label() == "Stage 1 filtered"
        assert lines[1].get_label() == "Stage 2 filtered"
        assert to_rgba(lines[2].get_color()) == to_rgba(INTERPOLATED_COLORS["stage1"])
        assert to_rgba(lines[3].get_color()) == to_rgba(INTERPOLATED_COLORS["stage2"])
        assert lines[2].get_color() == lines[0].get_color()
        assert lines[3].get_color() == lines[1].get_color()
        assert lines[2].get_alpha() == 1.0
        assert lines[3].get_alpha() == 1.0
        assert lines[2].get_linewidth() < lines[0].get_linewidth()
    finally:
        plt.close(fig)


def test_downrange_uses_stage_colors() -> None:
    trajectory_df = pd.DataFrame(
        {
            "stage": ["stage1", "stage1", "stage2", "stage2"],
            "mission_elapsed_time_s": [0.0, 1.0, 1.0, 2.0],
            "downrange_m": [0.0, 10.0, 10.0, 30.0],
        }
    )
    fig, axis = plt.subplots()
    try:
        _plot_downrange(axis, trajectory_df)

        assert axis.lines[0].get_color() == SUMMARY_COLORS["stage1"]
        assert axis.lines[1].get_color() == SUMMARY_COLORS["stage2"]
    finally:
        plt.close(fig)
