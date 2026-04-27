import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
import numpy as np
import pandas as pd

from webcalyzer.acceleration import G0_MPS2, acceleration_profile, smoothed_velocity_for_derivative, velocity_derivative
from webcalyzer.plotting import (
    FILTERED_ALPHA,
    INTERPOLATED_COLORS,
    SUMMARY_COLORS,
    _plot_coverage,
    _plot_downrange,
    _plot_acceleration,
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


def test_acceleration_profile_uses_interpolated_velocity_in_g() -> None:
    clean_df = pd.DataFrame(
        {
            "mission_elapsed_time_s": [0.0, 1.0, 2.0],
            "stage1_velocity_mps": [0.0, G0_MPS2, 2.0 * G0_MPS2],
        }
    )
    trajectory_df = pd.DataFrame(
        {
            "stage": ["stage1", "stage1", "stage1"],
            "mission_elapsed_time_s": [0.0, 1.0, 2.0],
            "velocity_mps": [0.0, G0_MPS2, 2.0 * G0_MPS2],
        }
    )

    _time_s, acceleration_g = acceleration_profile(
        clean_df=clean_df,
        trajectory_df=trajectory_df,
        stage="stage1",
    )

    assert np.allclose(acceleration_g, [1.0, 1.0, 1.0])


def test_acceleration_profile_masks_long_source_gaps() -> None:
    clean_df = pd.DataFrame(
        {
            "mission_elapsed_time_s": [0.0, 20.0, 21.0],
            "stage1_velocity_mps": [0.0, 20.0, 21.0],
        }
    )
    trajectory_df = pd.DataFrame(
        {
            "stage": ["stage1"] * 22,
            "mission_elapsed_time_s": np.arange(22.0),
            "velocity_mps": np.arange(22.0),
        }
    )

    time_s, acceleration_g = acceleration_profile(
        clean_df=clean_df,
        trajectory_df=trajectory_df,
        stage="stage1",
        max_source_gap_s=10.0,
    )

    assert np.isnan(acceleration_g[(time_s > 0.0) & (time_s < 20.0)]).all()
    assert np.isfinite(acceleration_g[(time_s >= 20.0) & (time_s <= 21.0)]).all()


def test_acceleration_plot_uses_estimated_title_and_smoothed_velocity_axis() -> None:
    clean_df = pd.DataFrame(
        {
            "mission_elapsed_time_s": [0.0, 1.0, 2.0, 3.0, 4.0],
            "stage1_velocity_mps": [0.0, 10.0, 20.0, 30.0, 40.0],
        }
    )
    trajectory_df = pd.DataFrame(
        {
            "stage": ["stage1"] * 5,
            "mission_elapsed_time_s": [0.0, 1.0, 2.0, 3.0, 4.0],
            "velocity_mps": [0.0, 10.0, 20.0, 30.0, 40.0],
        }
    )
    fig, axis = plt.subplots()
    try:
        _plot_acceleration(axis, clean_df, trajectory_df)

        assert axis.get_title() == "Estimated Acceleration"
        assert axis.get_ylabel() == "Estimated acceleration [g]"
        assert len(fig.axes) == 2
        assert fig.axes[1].get_ylabel() == "Smoothed velocity [m/s]"
        legend_labels = [text.get_text() for text in axis.get_legend().get_texts()]
        assert "Stage 1 estimated acceleration" in legend_labels
        assert "Stage 1 smoothed velocity" in legend_labels
    finally:
        plt.close(fig)


def test_derivative_uses_smoothed_velocity_series() -> None:
    time_s = np.linspace(0.0, 20.0, 81)
    trend = 10.0 * time_s
    jitter = np.where(np.arange(time_s.size) % 2 == 0, 50.0, -50.0)
    noisy_velocity = trend + jitter

    raw_derivative = velocity_derivative(time_s, noisy_velocity)
    smoothed_velocity = smoothed_velocity_for_derivative(time_s, noisy_velocity)
    smoothed_derivative = velocity_derivative(time_s, smoothed_velocity)

    assert np.max(np.abs(smoothed_derivative)) < 0.05 * np.max(np.abs(raw_derivative))
    assert np.isclose(np.mean(smoothed_derivative), 10.0, atol=0.5)
