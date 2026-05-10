from pathlib import Path
import asyncio
import threading
import time

import pytest

from webcalyzer.models import ProfileConfig, VideoOverlayConfig
from webcalyzer.ocr_factory import OCRBackendOptions
from webcalyzer.web import jobs as jobs_module
from webcalyzer.web.jobs import JobManager, JobOptions, _collect_output_paths


def test_collect_output_paths_omits_review_files(tmp_path: Path) -> None:
    (tmp_path / "plot.pdf").write_text("", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "telemetry.csv").write_text("", encoding="utf-8")
    (tmp_path / "review").mkdir()
    (tmp_path / "review" / "frame_00.jpg").write_bytes(b"jpeg")

    assert set(_collect_output_paths(tmp_path)) == {"plot.pdf", "data/telemetry.csv"}


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
