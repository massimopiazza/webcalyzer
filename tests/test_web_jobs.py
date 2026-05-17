from pathlib import Path
import asyncio
from datetime import datetime
import threading
import time

import pandas as pd
import pytest

from webcalyzer.models import ProfileConfig, VideoOverlayConfig
from webcalyzer.ocr_factory import OCRBackendOptions
from webcalyzer.run_paths import timestamped_run_output_dir
from webcalyzer.web import jobs as jobs_module
from webcalyzer.web.jobs import JobManager, JobOptions, JobRecord, _collect_output_paths


def test_collect_output_paths_omits_review_files(tmp_path: Path) -> None:
    (tmp_path / "plot.pdf").write_text("", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "telemetry.csv").write_text("", encoding="utf-8")
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "frame_00.jpg").write_bytes(b"jpeg")

    assert set(_collect_output_paths(tmp_path)) == {"plot.pdf", "data/telemetry.csv"}


def test_timestamped_run_output_dir_uses_yaml_filename(tmp_path: Path) -> None:
    output_dir = timestamped_run_output_dir(
        tmp_path,
        "configs/Falcon9_EchoStar-XXV.yaml",
        now=datetime(2026, 5, 11, 2, 3, 4),
    )

    assert output_dir == tmp_path / "Falcon9_EchoStar-XXV_2026-05-11T02-03-04"


def test_refresh_output_paths_emits_progress_for_new_files(tmp_path: Path) -> None:
    profile = ProfileConfig(
        profile_name="progress_test",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        video_overlay=VideoOverlayConfig(enabled=False),
    )
    job = JobRecord(
        id="job",
        state="running",
        started_at=time.time(),
        ended_at=None,
        options=JobOptions(
            video_path=tmp_path / "video.mp4",
            output_dir=tmp_path,
            profile=profile,
            sample_fps=None,
            ocr_backend=OCRBackendOptions().backend,
            ocr_recognition_level=OCRBackendOptions().recognition_level,
            ocr_workers=1,
            ocr_skip_detection=False,
            overlay_engine="auto",
            overlay_encoder="auto",
        ),
    )
    manager = JobManager()

    (tmp_path / "telemetry_raw.csv").write_text("", encoding="utf-8")
    manager._refresh_output_paths(job, tmp_path)

    assert job.output_paths == ["telemetry_raw.csv"]
    assert job.events[-1].kind == "progress"
    assert job.events[-1].payload == {
        "outputs": ["telemetry_raw.csv"],
        "new_outputs": ["telemetry_raw.csv"],
    }


def test_job_cancel_stops_running_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entered_extract = threading.Event()

    def fake_review_frames(*_args, **_kwargs) -> None:
        return None

    def fake_extract_telemetry(*_args, cancel_check=None, **_kwargs):
        assert cancel_check is not None
        entered_extract.set()
        while True:
            time.sleep(0.01)
            cancel_check()

    monkeypatch.setattr(jobs_module, "generate_review_frames", fake_review_frames)
    monkeypatch.setattr(jobs_module, "extract_telemetry", fake_extract_telemetry)

    profile = ProfileConfig(
        profile_name="cancel_test",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        video_overlay=VideoOverlayConfig(enabled=False),
    )
    manager = JobManager()
    loop = asyncio.new_event_loop()
    try:
        job = manager.submit(
            JobOptions(
                video_path=tmp_path / "video.mp4",
                output_dir=tmp_path / "out",
                profile=profile,
                sample_fps=None,
                ocr_backend=OCRBackendOptions().backend,
                ocr_recognition_level=OCRBackendOptions().recognition_level,
                ocr_workers=1,
                ocr_skip_detection=False,
                overlay_engine="auto",
                overlay_encoder="auto",
            ),
            loop,
        )
        assert entered_extract.wait(timeout=1)
        assert manager.cancel(job.id) is True
        assert job.thread is not None
        job.thread.join(timeout=2)
        assert not job.thread.is_alive()
        assert job.state == "cancelled"
        assert manager.active() is None
        assert any(event.kind == "cancelled" for event in job.events)
    finally:
        loop.close()


def test_job_applies_outlier_rejection_before_trajectory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    call_order: list[str] = []

    def fake_review_frames(*_args, **_kwargs) -> None:
        call_order.append("review")

    def fake_extract_telemetry(*_args, **_kwargs):
        call_order.append("extract")
        clean_df = pd.DataFrame(
            {
                "frame_index": [0],
                "sample_time_s": [0.0],
                "mission_elapsed_time_s": [0.0],
                "stage1_velocity_mps": [0.0],
                "stage1_altitude_m": [0.0],
            }
        )
        return clean_df.copy(), clean_df

    def fake_reject_outliers(*_args, **_kwargs):
        call_order.append("reject")
        return pd.DataFrame(
            {
                "frame_index": [0],
                "sample_time_s": [0.0],
                "mission_elapsed_time_s": [0.0],
                "stage1_velocity_mps": [0.0],
                "stage1_altitude_m": [123.0],
            }
        )

    def fake_write_trajectory_outputs(clean_df, *_args, **_kwargs):
        call_order.append("trajectory")
        assert clean_df.loc[0, "stage1_altitude_m"] == 123.0
        return clean_df, pd.DataFrame()

    def fake_create_plots(*_args, **_kwargs) -> None:
        call_order.append("plots")

    monkeypatch.setattr(jobs_module, "generate_review_frames", fake_review_frames)
    monkeypatch.setattr(jobs_module, "extract_telemetry", fake_extract_telemetry)
    monkeypatch.setattr(jobs_module, "apply_outlier_rejection_in_output_dir", fake_reject_outliers)
    monkeypatch.setattr(jobs_module, "write_trajectory_outputs", fake_write_trajectory_outputs)
    monkeypatch.setattr(jobs_module, "create_plots", fake_create_plots)

    profile = ProfileConfig(
        profile_name="outlier_job_test",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        video_overlay=VideoOverlayConfig(enabled=False),
    )
    job = JobRecord(
        id="job",
        state="running",
        started_at=time.time(),
        ended_at=None,
        options=JobOptions(
            video_path=tmp_path / "video.mp4",
            output_dir=tmp_path / "out",
            profile=profile,
            sample_fps=None,
            ocr_backend=OCRBackendOptions().backend,
            ocr_recognition_level=OCRBackendOptions().recognition_level,
            ocr_workers=1,
            ocr_skip_detection=False,
            overlay_engine="auto",
            overlay_encoder="auto",
        ),
    )

    JobManager()._execute(job)

    assert call_order == ["review", "extract", "reject", "trajectory", "plots"]
    assert any(event.payload == {"phase": "reject_outliers"} for event in job.events)
