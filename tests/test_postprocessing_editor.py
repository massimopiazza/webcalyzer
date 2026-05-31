from pathlib import Path

import pandas as pd
import pytest

from webcalyzer.config import save_profile
from webcalyzer.models import HardcodedRawDataPoint, ProfileConfig, TrajectoryConfig, VideoOverlayConfig
from webcalyzer.postprocess import rebuild_clean_in_output_dir
from webcalyzer.postprocessing_editor import (
    RAW_BACKUP_FILENAME,
    PostprocessingConflict,
    acquire_session,
    apply_draft_to_raw,
    ensure_raw_sample_ids,
    initialize_manifest,
    mark_raw_materialized,
    mutate_draft,
)


def _profile(*, hardcoded: list[HardcodedRawDataPoint] | None = None) -> ProfileConfig:
    return ProfileConfig(
        profile_name="postprocessing_test",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        trajectory=TrajectoryConfig(enabled=False, outlier_rejection_enabled=False),
        video_overlay=VideoOverlayConfig(enabled=False),
        hardcoded_raw_data_points=hardcoded or [],
    )


def _write_output(tmp_path: Path, *, profile: ProfileConfig | None = None) -> ProfileConfig:
    profile = profile or _profile()
    save_profile(profile, tmp_path / "config_resolved.yaml")
    pd.DataFrame(
        [
            {
                "frame_index": 10,
                "sample_time_s": 1.0,
                "mission_elapsed_time_s": 1.0,
                "stage1_velocity_raw_text": "100 MPH",
                "stage1_velocity_parse_status": "parsed",
                "stage1_velocity_raw_unit": "MPH",
                "stage1_velocity_raw_value": 100.0,
                "stage1_velocity_si_value": 44.704,
                "stage1_velocity_variant": "vision",
            },
            {
                "frame_index": 20,
                "sample_time_s": 2.0,
                "mission_elapsed_time_s": 2.0,
                "stage1_velocity_raw_text": "200 MPH",
                "stage1_velocity_parse_status": "parsed",
                "stage1_velocity_raw_unit": "MPH",
                "stage1_velocity_raw_value": 200.0,
                "stage1_velocity_si_value": 89.408,
                "stage1_velocity_variant": "vision",
            },
        ]
    ).to_csv(tmp_path / "telemetry_raw.csv", index=False)
    pd.DataFrame(columns=["mission_elapsed_time_s", "stage1_velocity_mps"]).to_csv(
        tmp_path / "telemetry_rejected.csv",
        index=False,
    )
    initialize_manifest(tmp_path, profile=profile)
    mark_raw_materialized(tmp_path)
    return profile


def test_sample_ids_are_deterministic(tmp_path: Path) -> None:
    _write_output(tmp_path)

    first = ensure_raw_sample_ids(tmp_path, persist=True)
    second = ensure_raw_sample_ids(tmp_path, persist=True)

    assert first["sample_id"].tolist() == ["frame:10:time:1", "frame:20:time:2"]
    assert second["sample_id"].tolist() == first["sample_id"].tolist()


def test_workspace_marks_field_outliers_without_removing_raw_observations(tmp_path: Path) -> None:
    _write_output(tmp_path)
    raw_df = pd.read_csv(tmp_path / "telemetry_raw.csv")
    duplicate_met = raw_df.iloc[1].copy()
    duplicate_met["frame_index"] = 21
    duplicate_met["stage1_velocity_raw_text"] = "201 MPH"
    duplicate_met["stage1_velocity_raw_value"] = 201.0
    duplicate_met["stage1_velocity_si_value"] = 89.85504
    pd.concat([raw_df, duplicate_met.to_frame().T], ignore_index=True).to_csv(
        tmp_path / "telemetry_raw.csv",
        index=False,
    )
    pd.DataFrame(
        [{"mission_elapsed_time_s": 2.0, "stage1_velocity_mps": 89.408}]
    ).to_csv(tmp_path / "telemetry_rejected.csv", index=False)

    workspace = acquire_session(tmp_path, action="create")
    velocity = next(field for field in workspace["fields"] if field["id"] == "stage1_velocity")

    assert [item["outlier"] for item in velocity["observations"]] == [False, True, False]
    assert velocity["rejected"] == [{"mission_elapsed_time_s": 2.0, "value": 89.408}]


def test_manual_override_survives_rebuild_and_preserves_ocr_text(tmp_path: Path) -> None:
    _write_output(tmp_path)
    workspace = acquire_session(tmp_path, action="create")

    mutate_draft(
        tmp_path,
        session_token=workspace["session_token"],
        action="override",
        field_name="stage1_velocity",
        sample_ids=["frame:10:time:1"],
        value=100.0,
        unit="KPH",
    )
    apply_draft_to_raw(tmp_path, session_token=workspace["session_token"])
    clean_df = rebuild_clean_in_output_dir(tmp_path)
    raw_df = pd.read_csv(tmp_path / "telemetry_raw.csv")

    assert raw_df.at[0, "stage1_velocity_raw_text"] == "100 MPH"
    assert raw_df.at[0, "stage1_velocity_parse_status"] == "manual"
    assert raw_df.at[0, "stage1_velocity_raw_unit"] == "KPH"
    assert clean_df.at[0, "stage1_velocity_mps"] == pytest.approx(27.7777778)
    assert (tmp_path / RAW_BACKUP_FILENAME).is_file()


def test_saved_delete_clears_only_selected_observation(tmp_path: Path) -> None:
    _write_output(tmp_path)
    workspace = acquire_session(tmp_path, action="create")

    mutate_draft(
        tmp_path,
        session_token=workspace["session_token"],
        action="delete",
        field_name="stage1_velocity",
        sample_ids=["frame:10:time:1"],
    )
    apply_draft_to_raw(tmp_path, session_token=workspace["session_token"])
    raw_df = pd.read_csv(tmp_path / "telemetry_raw.csv")

    assert pd.isna(raw_df.at[0, "stage1_velocity_raw_text"])
    assert raw_df.at[1, "stage1_velocity_raw_text"] == "200 MPH"


def test_manifest_enabled_rebuild_does_not_reinject_hardcoded_anchor(tmp_path: Path) -> None:
    profile = _profile(hardcoded=[HardcodedRawDataPoint(mission_elapsed_time_s=5.0, stage1_velocity_mps=123.0)])
    _write_output(tmp_path, profile=profile)

    clean_df = rebuild_clean_in_output_dir(tmp_path, profile=profile)

    assert clean_df["mission_elapsed_time_s"].tolist() == [1.0, 2.0]


def test_save_rejects_external_raw_change(tmp_path: Path) -> None:
    _write_output(tmp_path)
    workspace = acquire_session(tmp_path, action="create")
    raw_path = tmp_path / "telemetry_raw.csv"
    raw_path.write_text(raw_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(PostprocessingConflict, match="changed"):
        apply_draft_to_raw(tmp_path, session_token=workspace["session_token"])
