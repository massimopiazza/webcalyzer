import numpy as np
import pandas as pd

from webcalyzer.models import LaunchSiteConfig, TrajectoryConfig
from webcalyzer.trajectory import infer_sample_fps, reconstruct_trajectory


def _clean_frame(times: np.ndarray, velocity: np.ndarray, altitude: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "stage1_velocity_mps": velocity,
            "stage1_altitude_m": altitude,
            "stage2_velocity_mps": np.nan,
            "stage2_altitude_m": np.nan,
        }
    )


def test_reconstructs_downrange_from_integrated_total_speed() -> None:
    times = np.arange(0.0, 11.0)
    velocity = np.full_like(times, 10.0)
    velocity[0] = 0.0
    altitude = np.zeros_like(times)

    augmented, trajectory = reconstruct_trajectory(
        _clean_frame(times, velocity, altitude),
        TrajectoryConfig(interpolation_method="linear", integration_method="rk4"),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    assert stage1["total_distance_m"].iloc[-1] == 95.0
    assert stage1["downrange_m"].iloc[-1] == 95.0
    assert augmented["stage1_downrange_m"].notna().all()


def test_missing_velocity_and_altitude_are_only_interpolated_for_trajectory() -> None:
    times = np.arange(0.0, 5.0)
    velocity = np.array([0.0, 10.0, np.nan, 10.0, 10.0])
    altitude = np.array([0.0, 0.0, np.nan, 0.0, 0.0])
    clean_df = _clean_frame(times, velocity, altitude)

    augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(interpolation_method="linear", integration_method="trapezoid"),
        sample_fps=1.0,
    )

    assert np.isnan(augmented.loc[2, "stage1_velocity_mps"])
    assert np.isnan(augmented.loc[2, "stage1_altitude_m"])
    assert np.isfinite(augmented.loc[2, "stage1_downrange_m"])
    assert trajectory["downrange_m"].notna().all()


def test_coarse_altitude_plateaus_are_smoothed_only_for_reconstruction() -> None:
    times = np.arange(0.0, 6.0)
    velocity = np.full_like(times, 1000.0)
    velocity[0] = 0.0
    altitude = np.array([0.0, 0.0, 1000.0, 1000.0, 2000.0, 2000.0])
    clean_df = _clean_frame(times, velocity, altitude)

    augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_altitude_threshold_m=500.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    altitude_at_one = stage1.loc[stage1["mission_elapsed_time_s"] == 1.0, "altitude_m"].iloc[0]

    assert augmented.loc[1, "stage1_altitude_m"] == 0.0
    assert 0.0 < altitude_at_one < 1000.0


def test_coarse_velocity_plateaus_are_smoothed_for_reconstruction() -> None:
    times = np.arange(0.0, 6.0)
    velocity = np.array([0.0, 0.0, 100.0, 100.0, 200.0, 200.0])
    altitude = np.zeros_like(times)
    clean_df = _clean_frame(times, velocity, altitude)

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_velocity_threshold_mps=50.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    velocity_at_one = stage1.loc[stage1["mission_elapsed_time_s"] == 1.0, "velocity_mps"].iloc[0]

    assert 0.0 < velocity_at_one < 100.0


def test_subthreshold_changes_keep_original_sample_timing_even_with_later_plateau() -> None:
    times = np.arange(0.0, 7.0)
    velocity = np.array([0.0, 10.0, 20.0, 30.0, 100.0, 100.0, 200.0])
    altitude = np.zeros_like(times)
    clean_df = _clean_frame(times, velocity, altitude)

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_velocity_threshold_mps=50.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]

    assert stage1.loc[stage1["mission_elapsed_time_s"] == 1.0, "velocity_mps"].iloc[0] == 10.0


def test_subthreshold_plateaus_are_not_smoothed() -> None:
    times = np.arange(0.0, 6.0)
    velocity = np.full_like(times, 1000.0)
    velocity[0] = 0.0
    altitude = np.array([0.0, 0.0, 100.0, 100.0, 200.0, 200.0])
    clean_df = _clean_frame(times, velocity, altitude)

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_altitude_threshold_m=500.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    altitude_at_one = stage1.loc[stage1["mission_elapsed_time_s"] == 1.0, "altitude_m"].iloc[0]

    assert altitude_at_one == 0.0


def test_large_non_plateau_changes_are_not_treated_as_coarse_steps() -> None:
    times = np.arange(0.0, 5.0)
    velocity = np.full_like(times, 1000.0)
    velocity[0] = 0.0
    altitude = np.array([0.0, 1000.0, 2000.0, 3000.0, 4000.0])
    clean_df = _clean_frame(times, velocity, altitude)

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_altitude_threshold_m=500.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]

    assert stage1.loc[stage1["mission_elapsed_time_s"] == 1.0, "altitude_m"].iloc[0] == 1000.0


def test_coarse_plateaus_are_not_smoothed_across_long_gaps() -> None:
    times = np.array([0.0, 1.0, 2.0, 100.0, 101.0, 102.0])
    velocity = np.full_like(times, 1000.0)
    velocity[0] = 0.0
    altitude = np.array([0.0, 0.0, 0.0, 1000.0, 1000.0, 1000.0])
    clean_df = _clean_frame(times, velocity, altitude)

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_step_max_gap_s=10.0,
            coarse_altitude_threshold_m=500.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    altitude_at_fifty = stage1.loc[stage1["mission_elapsed_time_s"] == 50.0, "altitude_m"].iloc[0]

    assert 400.0 < altitude_at_fifty < 600.0


def test_coarse_step_max_gap_can_be_relaxed() -> None:
    times = np.array([0.0, 1.0, 2.0, 100.0, 101.0, 102.0])
    velocity = np.full_like(times, 1000.0)
    velocity[0] = 0.0
    altitude = np.array([0.0, 0.0, 0.0, 1000.0, 1000.0, 1000.0])
    clean_df = _clean_frame(times, velocity, altitude)

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_step_max_gap_s=200.0,
            coarse_altitude_threshold_m=500.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    altitude_at_fifty = stage1.loc[stage1["mission_elapsed_time_s"] == 50.0, "altitude_m"].iloc[0]

    assert altitude_at_fifty > 900.0


def test_isolated_altitude_outlier_is_removed_only_for_reconstruction() -> None:
    times = np.array([0.0, 1.0, 9.0, 11.0, 13.0])
    velocity = np.full_like(times, 1000.0)
    velocity[0] = 0.0
    altitude = np.array([0.0, 90123.264, 60.0456, 87.1728, 117.3480])
    clean_df = _clean_frame(times, velocity, altitude)

    augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            coarse_altitude_threshold_m=500.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    altitude_at_one = stage1.loc[stage1["mission_elapsed_time_s"] == 1.0, "altitude_m"].iloc[0]

    assert augmented.loc[1, "stage1_altitude_m"] == 90123.264
    assert altitude_at_one < 100.0


def test_outlier_preconditioning_can_be_disabled() -> None:
    times = np.array([0.0, 1.0, 9.0, 11.0, 13.0])
    velocity = np.full_like(times, 1000.0)
    velocity[0] = 0.0
    altitude = np.array([0.0, 90123.264, 60.0456, 87.1728, 117.3480])
    clean_df = _clean_frame(times, velocity, altitude)

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="trapezoid",
            outlier_preconditioning_enabled=False,
            coarse_altitude_threshold_m=500.0,
        ),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]

    assert stage1.loc[stage1["mission_elapsed_time_s"] == 1.0, "altitude_m"].iloc[0] == 90123.264


def test_stage2_starts_at_its_first_real_interval_and_inherits_stage1_downrange() -> None:
    times = np.arange(0.0, 7.0)
    clean_df = pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "stage1_velocity_mps": [0.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
            "stage1_altitude_m": np.zeros_like(times),
            "stage2_velocity_mps": [np.nan, np.nan, np.nan, 20.0, 20.0, 20.0, 20.0],
            "stage2_altitude_m": [np.nan, np.nan, np.nan, 0.0, 0.0, 0.0, 0.0],
        }
    )

    augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(interpolation_method="linear", integration_method="rk4"),
        sample_fps=1.0,
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    stage2 = trajectory[trajectory["stage"] == "stage2"]
    inherited_downrange = float(np.interp(3.0, stage1["mission_elapsed_time_s"], stage1["downrange_m"]))

    assert stage2["mission_elapsed_time_s"].min() == 3.0
    assert stage2["downrange_m"].iloc[0] == inherited_downrange
    assert augmented.loc[times < 3.0, "stage2_downrange_m"].isna().all()
    assert augmented.loc[times >= 3.0, "stage2_downrange_m"].notna().all()


def test_partial_launch_site_falls_back_to_flat_coordinates() -> None:
    times = np.arange(0.0, 3.0)
    clean_df = _clean_frame(times, np.array([0.0, 10.0, 10.0]), np.zeros_like(times))

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="rk4",
            launch_site=LaunchSiteConfig(latitude_deg=28.0),
        ),
        sample_fps=1.0,
    )

    assert set(trajectory["coordinate_model"]) == {"flat"}
    assert trajectory["latitude_deg"].isna().all()
    assert trajectory["longitude_deg"].isna().all()


def test_complete_launch_site_uses_wgs84_coordinates() -> None:
    times = np.arange(0.0, 3.0)
    clean_df = _clean_frame(times, np.array([0.0, 10.0, 10.0]), np.zeros_like(times))

    _augmented, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(
            interpolation_method="linear",
            integration_method="rk4",
            launch_site=LaunchSiteConfig(latitude_deg=0.0, longitude_deg=0.0, azimuth_deg=90.0),
        ),
        sample_fps=1.0,
    )

    assert set(trajectory["coordinate_model"]) == {"wgs84"}
    assert trajectory["latitude_deg"].abs().max() < 1e-8
    assert trajectory["longitude_deg"].iloc[-1] > 0.0


def test_infer_sample_fps_uses_median_step() -> None:
    df = pd.DataFrame(
        {
            "sample_time_s": np.arange(0.0, 10.0, 0.25),
            "mission_elapsed_time_s": np.arange(0.0, 10.0, 0.25),
        }
    )
    assert abs(infer_sample_fps(df) - 4.0) < 1e-9


def test_integration_step_matches_inferred_sample_fps() -> None:
    """The trajectory grid spacing equals the OCR sample period: at 4 fps
    the integration step is 0.25 s, so the result has ~4× as many rows as
    a 1 fps run over the same MET window."""

    times = np.arange(0.0, 11.0, 0.25)
    velocity = np.full_like(times, 10.0)
    velocity[0] = 0.0
    altitude = np.zeros_like(times)
    clean_df = pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "stage1_velocity_mps": velocity,
            "stage1_altitude_m": altitude,
            "stage2_velocity_mps": np.nan,
            "stage2_altitude_m": np.nan,
        }
    )

    _, trajectory = reconstruct_trajectory(
        clean_df,
        TrajectoryConfig(interpolation_method="linear", integration_method="rk4"),
    )

    stage1 = trajectory[trajectory["stage"] == "stage1"]
    inferred_step = float(stage1["integration_step_s"].iloc[0])
    assert abs(inferred_step - 0.25) < 1e-6
    assert float(stage1["sample_fps"].iloc[0]) == 4.0


def test_default_derivative_window_is_20_seconds() -> None:
    """Lock the post-sweep default. 20 s with polyorder 3 was chosen against
    a synthetic rocket profile and the NG-3 dataset; halving it back to
    5 s would regress noise rejection by ~3.5× in synthetic RMSE."""

    from webcalyzer.acceleration import (
        ACCELERATION_SOURCE_GAP_THRESHOLD_S,
        DEFAULT_DERIVATIVE_MODE,
        DEFAULT_DERIVATIVE_POLYORDER,
        DEFAULT_DERIVATIVE_WINDOW_S,
        DEFAULT_MIN_WINDOW_SAMPLES,
    )
    from webcalyzer.models import TrajectoryConfig

    assert DEFAULT_DERIVATIVE_WINDOW_S == 20.0
    assert DEFAULT_DERIVATIVE_POLYORDER == 3
    assert DEFAULT_MIN_WINDOW_SAMPLES == 5
    assert DEFAULT_DERIVATIVE_MODE == "interp"
    assert ACCELERATION_SOURCE_GAP_THRESHOLD_S == 10.0
    config = TrajectoryConfig()
    assert config.derivative_smoothing_window_s == 20.0
    assert config.derivative_smoothing_polyorder == 3
    assert config.derivative_min_window_samples == 5
    assert config.derivative_smoothing_mode == "interp"
    assert config.acceleration_source_gap_threshold_s == 10.0


def test_longer_savgol_window_lowers_derivative_jitter() -> None:
    """A longer Sav-Gol window must produce a smoother derivative on
    noisy data - a sanity check that the new 20 s default is in the
    right direction relative to the previous 5 s."""

    from webcalyzer.acceleration import smoothed_velocity_and_derivative

    times = np.linspace(0.0, 80.0, 321)  # 4 Hz, 80 s
    truth_a = 30.0  # m/s² constant
    truth_v = truth_a * times
    rng = np.random.default_rng(7)
    noisy_v = truth_v + rng.normal(0, 5.0, size=truth_v.shape)
    _, deriv_short = smoothed_velocity_and_derivative(times, noisy_v, window_s=5.0)
    _, deriv_long = smoothed_velocity_and_derivative(times, noisy_v, window_s=20.0)
    short_rmse = float(np.sqrt(np.mean((deriv_short - truth_a) ** 2)))
    long_rmse = float(np.sqrt(np.mean((deriv_long - truth_a) ** 2)))
    assert long_rmse < 0.5 * short_rmse


def test_savgol_smoothing_is_fps_independent() -> None:
    """Same time window of noisy velocity, sampled at 1 Hz vs 4 Hz, should
    yield comparable smoothed derivatives. Specifying the smoothing
    window in seconds (Savitzky-Golay over a fixed time span) is the
    textbook way to make derivative estimates independent of sample rate
    while still benefiting from denser sampling."""

    from webcalyzer.acceleration import smoothed_velocity_and_derivative

    rng_high = np.linspace(0.0, 20.0, 81)  # 4 Hz
    rng_low = np.linspace(0.0, 20.0, 21)  # 1 Hz
    trend_high = 10.0 * rng_high
    trend_low = 10.0 * rng_low
    jitter_high = np.where(np.arange(rng_high.size) % 2 == 0, 50.0, -50.0)
    jitter_low = np.where(np.arange(rng_low.size) % 2 == 0, 50.0, -50.0)

    _, deriv_high = smoothed_velocity_and_derivative(
        rng_high, trend_high + jitter_high, window_s=5.0
    )
    _, deriv_low = smoothed_velocity_and_derivative(
        rng_low, trend_low + jitter_low, window_s=5.0
    )

    # Both should converge to the underlying slope of 10 m/s² regardless
    # of sample rate.
    assert abs(np.mean(deriv_high) - 10.0) < 0.5
    assert abs(np.mean(deriv_low) - 10.0) < 0.5
