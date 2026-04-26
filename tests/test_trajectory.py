import numpy as np
import pandas as pd

from webcalyzer.models import LaunchSiteConfig, TrajectoryConfig
from webcalyzer.trajectory import reconstruct_trajectory


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
        TrajectoryConfig(interpolation_method="linear", integration_method="rk4", integration_step_s=1.0),
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
        TrajectoryConfig(interpolation_method="linear", integration_method="trapezoid", integration_step_s=1.0),
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
            integration_step_s=1.0,
            coarse_altitude_threshold_m=500.0,
        ),
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
            integration_step_s=1.0,
            coarse_velocity_threshold_mps=50.0,
        ),
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
            integration_step_s=1.0,
            coarse_velocity_threshold_mps=50.0,
        ),
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
            integration_step_s=1.0,
            coarse_altitude_threshold_m=500.0,
        ),
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
            integration_step_s=1.0,
            coarse_altitude_threshold_m=500.0,
        ),
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
            integration_step_s=1.0,
            coarse_step_max_gap_s=10.0,
            coarse_altitude_threshold_m=500.0,
        ),
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
            integration_step_s=1.0,
            coarse_step_max_gap_s=200.0,
            coarse_altitude_threshold_m=500.0,
        ),
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
            integration_step_s=1.0,
            coarse_altitude_threshold_m=500.0,
        ),
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
            integration_step_s=1.0,
            outlier_preconditioning_enabled=False,
            coarse_altitude_threshold_m=500.0,
        ),
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
        TrajectoryConfig(interpolation_method="linear", integration_method="rk4", integration_step_s=1.0),
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
            integration_step_s=1.0,
            launch_site=LaunchSiteConfig(latitude_deg=28.0),
        ),
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
            integration_step_s=1.0,
            launch_site=LaunchSiteConfig(latitude_deg=0.0, longitude_deg=0.0, azimuth_deg=90.0),
        ),
    )

    assert set(trajectory["coordinate_model"]) == {"wgs84"}
    assert trajectory["latitude_deg"].abs().max() < 1e-8
    assert trajectory["longitude_deg"].iloc[-1] > 0.0
