from pathlib import Path

from webcalyzer.config import load_profile, save_profile


def test_profile_uses_explicit_bbox_and_fixture_range_schema(tmp_path: Path) -> None:
    profile = load_profile("configs/blue_origin/new_glenn_ng3.yaml")

    assert profile.fixture_frame_count == 20
    assert profile.fixture_time_range_s == (0.0, 840.0)
    assert len(profile.fields["stage1_velocity"].box.normalized_tuple()) == 4
    assert profile.video_overlay.width_fraction == 0.5
    assert profile.video_overlay.height_fraction == 0.65
    assert profile.trajectory.interpolation_method == "pchip"
    assert profile.trajectory.integration_method == "rk4"
    assert profile.trajectory.outlier_preconditioning_enabled is True
    assert profile.trajectory.coarse_step_max_gap_s == 10.0
    assert profile.trajectory.coarse_altitude_threshold_m == 500.0
    assert profile.trajectory.coarse_velocity_threshold_mps == 50.0
    assert profile.trajectory.acceleration_source_gap_threshold_s == 10.0
    assert profile.trajectory.derivative_smoothing_window_s == 20.0
    assert profile.trajectory.derivative_smoothing_polyorder == 3
    assert profile.trajectory.derivative_min_window_samples == 5
    assert profile.trajectory.derivative_smoothing_mode == "interp"
    assert profile.trajectory.launch_site.latitude_deg is None or isinstance(
        profile.trajectory.launch_site.latitude_deg,
        float,
    )
    assert len(profile.hardcoded_raw_data_points) == 1
    hardcoded_point = profile.hardcoded_raw_data_points[0]
    assert hardcoded_point.mission_elapsed_time_s == 560.0
    assert hardcoded_point.stage1_velocity_mps == 0.0
    assert hardcoded_point.stage1_altitude_m == 0.0
    assert hardcoded_point.stage2_velocity_mps is None

    saved_path = save_profile(profile, tmp_path / "profile.yaml")
    saved_text = saved_path.read_text()
    assert "fixture_time_range_s: [0.0, 840.0]" in saved_text
    assert "fixture_reference_times_s" not in saved_text
    assert "reference_resolution" not in saved_text
    assert "hardcoded_raw_data_points:" in saved_text
    assert "mission_elapsed_time_s: 560.0" in saved_text
    assert "bbox_x1y1x2y2" in saved_text
    assert "bbox_x1y1x2y2: [" in saved_text
    assert "trajectory:" in saved_text
    assert "\n    box:" not in saved_text
