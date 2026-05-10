from webcalyzer.extract import FrameRawOCR, _run_phase_b
from webcalyzer.models import (
    Box,
    CalibrationSegmentConfig,
    FieldConfig,
    ProfileConfig,
)


def test_phase_b_marks_absent_segment_fields_not_configured() -> None:
    profile = ProfileConfig(
        profile_name="test",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        segments=[
            CalibrationSegmentConfig(
                id="segment_1",
                start_frame_index=0,
                start_time_s=0.0,
                end_frame_index=10,
                end_time_s=1.0,
                fields={
                    "met": FieldConfig(
                        name="met",
                        kind="met",
                        stage=None,
                        box=Box(0.1, 0.1, 0.2, 0.2),
                    ),
                    "stage2_velocity": FieldConfig(
                        name="stage2_velocity",
                        kind="velocity",
                        stage="stage2",
                        box=Box(0.2, 0.1, 0.3, 0.2),
                    ),
                },
            )
        ],
    )

    raw_rows, clean_rows = _run_phase_b(
        profile=profile,
        metadata_fps=10.0,
        raw_frames=[
            FrameRawOCR(
                frame_index=0,
                sample_time_s=0.0,
                segment_id="segment_1",
                candidates_by_field={"met": [("T+00:00:05", "raw")]},
            )
        ],
    )

    assert raw_rows[0]["segment_id"] == "segment_1"
    assert raw_rows[0]["stage1_velocity_parse_status"] == "not_configured"
    assert clean_rows[0]["segment_id"] == "segment_1"
    assert clean_rows[0]["stage1_velocity_mps"] is None
