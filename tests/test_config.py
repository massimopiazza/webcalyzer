from pathlib import Path

from webcalyzer.config import load_profile, save_profile
from webcalyzer.web.schema import (
    SegmentModel,
    profile_dataclass_to_model,
    validate_runnable_profile_model,
)


def test_profile_uses_explicit_bbox_and_fixture_range_schema(tmp_path: Path) -> None:
    profile = load_profile("configs/blue_origin/new_glenn_ng3.yaml")

    assert profile.fixture_frame_count == 20
    assert profile.default_ocr_workers == 0
    assert profile.ocr_backend == "auto"
    assert profile.ocr_recognition_level == "accurate"
    assert profile.skip_full_frame_ocr_fallback is False
    assert profile.fixture_time_range_s == (0.0, 840.0)
    assert profile.calibration_video.frame_count == 53179
    assert profile.segments[0].id == "segment_1"
    assert profile.segments[0].end_frame_index == 50349
    assert len(profile.segments[0].fields["stage1_velocity"].box.normalized_tuple()) == 4
    assert profile.video_overlay.width_fraction == 0.5
    assert profile.video_overlay.height_fraction == 0.65
    assert profile.video_overlay.engine == "auto"
    assert profile.video_overlay.encoder == "auto"
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
    assert "default_ocr_workers: 0" in saved_text
    assert "ocr_backend: auto" in saved_text
    assert "ocr_recognition_level: accurate" in saved_text
    assert "skip_full_frame_ocr_fallback: false" in saved_text
    assert "  engine: auto" in saved_text
    assert "  encoder: auto" in saved_text
    assert "fixture_reference_times_s" not in saved_text
    assert "reference_resolution" not in saved_text
    assert "hardcoded_raw_data_points:" in saved_text
    assert "mission_elapsed_time_s: 560.0" in saved_text
    assert "calibration_video:" in saved_text
    assert "segments:" in saved_text
    assert "bbox_x1y1x2y2" in saved_text
    assert "bbox_x1y1x2y2: [" in saved_text
    assert "trajectory:" in saved_text
    assert "\nfields:" not in saved_text
    assert "\n    box:" not in saved_text


def test_draft_profile_can_omit_met_but_runnable_rejects_it() -> None:
    profile = load_profile("configs/blue_origin/new_glenn_ng3.yaml")
    del profile.segments[0].fields["met"]

    model = profile_dataclass_to_model(profile)
    assert isinstance(model.segments[0], SegmentModel)

    try:
        validate_runnable_profile_model(model)
    except ValueError as exc:
        assert "met field is required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Runnable validation should reject missing MET")


def test_split_frame_belongs_to_next_segment() -> None:
    profile = load_profile("configs/blue_origin/new_glenn_ng3.yaml")
    original = profile.segments[0]
    fields = dict(original.fields)
    original.end_frame_index = 100
    original.end_time_s = 10.0
    profile.segments.append(
        type(original)(
            id="segment_2",
            start_frame_index=100,
            start_time_s=10.0,
            end_frame_index=200,
            end_time_s=20.0,
            fields=fields,
        )
    )

    assert profile.active_segment_for_frame(99).id == "segment_1"
    assert profile.active_segment_for_frame(100).id == "segment_2"
