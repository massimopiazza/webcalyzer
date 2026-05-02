from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from webcalyzer.config import save_profile
from webcalyzer.extract import extract_telemetry
from webcalyzer.fixtures import generate_review_frames
from webcalyzer.models import ProfileConfig, VideoOverlayConfig
from webcalyzer.ocr_factory import OCRBackendOptions, resolve_backend_name
from webcalyzer.overlay import render_telemetry_overlay_video
from webcalyzer.plotting import create_plots
from webcalyzer.trajectory import TRAJECTORY_FILENAME, write_trajectory_outputs


@dataclass
class JobOptions:
    video_path: Path
    output_dir: Path
    profile: ProfileConfig
    sample_fps: float | None
    ocr_backend: str
    ocr_recognition_level: str
    ocr_workers: int
    ocr_skip_detection: bool
    overlay_engine: str
    overlay_encoder: str


@dataclass
class JobEvent:
    kind: str  # "log" | "phase" | "progress" | "done" | "error" | "cancelled"
    message: str = ""
    payload: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "payload": self.payload or {},
            "timestamp": self.timestamp,
        }


@dataclass
class JobRecord:
    id: str
    state: str  # "queued" | "running" | "succeeded" | "failed" | "cancelled"
    started_at: float
    ended_at: float | None
    options: JobOptions
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    events: list[JobEvent] = field(default_factory=list)
    listeners: list[asyncio.Queue[JobEvent]] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    thread: threading.Thread | None = None
    loop: asyncio.AbstractEventLoop | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
            "video_path": str(self.options.video_path),
            "output_dir": str(self.options.output_dir),
            "profile_name": self.options.profile.profile_name,
            "outputs": self.output_paths,
        }


class JobCancelled(RuntimeError):
    """Raised when a job is cancelled between phases."""


class JobManager:
    """In-memory single-job runner with SSE-friendly event fan-out."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._active_id: str | None = None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [record.to_summary() for record in self._jobs.values()]

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active(self) -> JobRecord | None:
        with self._lock:
            if self._active_id is None:
                return None
            return self._jobs.get(self._active_id)

    def submit(self, options: JobOptions, loop: asyncio.AbstractEventLoop) -> JobRecord:
        with self._lock:
            if self._active_id is not None:
                running = self._jobs.get(self._active_id)
                if running and running.state in {"queued", "running"}:
                    raise RuntimeError(
                        "A job is already running. Cancel or wait for it to finish."
                    )
            job = JobRecord(
                id=uuid.uuid4().hex[:12],
                state="queued",
                started_at=time.time(),
                ended_at=None,
                options=options,
                loop=loop,
            )
            self._jobs[job.id] = job
            self._active_id = job.id

        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        job.thread = thread
        thread.start()
        return job

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.state in {"succeeded", "failed", "cancelled"}:
            return False
        job.cancel_event.set()
        return True

    def subscribe(self, job_id: str) -> tuple[JobRecord, asyncio.Queue[JobEvent]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=1024)
            job.listeners.append(queue)
        return job, queue

    def unsubscribe(self, job: JobRecord, queue: asyncio.Queue[JobEvent]) -> None:
        with self._lock:
            try:
                job.listeners.remove(queue)
            except ValueError:
                pass

    def _emit(self, job: JobRecord, event: JobEvent) -> None:
        job.events.append(event)
        if job.loop is None:
            return
        for listener in list(job.listeners):
            asyncio.run_coroutine_threadsafe(listener.put(event), job.loop)

    def _check_cancel(self, job: JobRecord) -> None:
        if job.cancel_event.is_set():
            raise JobCancelled()

    def _run(self, job: JobRecord) -> None:
        job.state = "running"
        self._emit(job, JobEvent("phase", "Starting job", {"phase": "start"}))

        log_handler = _StreamingLogHandler(lambda message: self._emit(job, JobEvent("log", message)))
        log_handler.setLevel(logging.INFO)
        log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(log_handler)

        stream = _StreamingTextIO(lambda message: self._emit(job, JobEvent("log", message)))

        try:
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                self._execute(job)
        except JobCancelled:
            job.state = "cancelled"
            self._emit(job, JobEvent("cancelled", "Job cancelled"))
        except Exception as exc:  # noqa: BLE001
            job.state = "failed"
            job.error = "".join(traceback.format_exception(exc))
            self._emit(job, JobEvent("error", str(exc), {"traceback": job.error}))
        else:
            if job.state == "running":
                job.state = "succeeded"
                self._emit(
                    job,
                    JobEvent("done", "Job complete", {"outputs": job.output_paths}),
                )
        finally:
            root_logger.removeHandler(log_handler)
            job.ended_at = time.time()
            with self._lock:
                if self._active_id == job.id:
                    self._active_id = None

    def _execute(self, job: JobRecord) -> None:
        options = job.options
        output_path = Path(options.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        backend_options = OCRBackendOptions(
            backend=options.ocr_backend,
            recognition_level=options.ocr_recognition_level,
        )
        resolved_backend = resolve_backend_name(backend_options.backend)
        workers = options.ocr_workers
        if workers <= 0:
            workers = 1 if resolved_backend == "vision" else max(1, _physical_cpu_count() - 1)

        effective_fps = float(options.sample_fps or options.profile.default_sample_fps)

        self._emit(
            job,
            JobEvent(
                "phase",
                "Generating review frames",
                {"phase": "review_frames"},
            ),
        )
        generate_review_frames(options.video_path, options.profile, output_path / "review")
        self._check_cancel(job)

        self._emit(
            job,
            JobEvent("phase", "Running OCR extraction", {"phase": "extract"}),
        )
        _raw_df, clean_df = extract_telemetry(
            options.video_path,
            options.profile,
            output_path,
            sample_fps=options.sample_fps,
            backend_options=backend_options,
            workers=workers,
            skip_detection=options.ocr_skip_detection,
        )
        self._check_cancel(job)

        self._emit(
            job,
            JobEvent("phase", "Reconstructing trajectory", {"phase": "trajectory"}),
        )
        clean_df, trajectory_df = write_trajectory_outputs(
            clean_df,
            output_path,
            options.profile.trajectory,
            sample_fps=effective_fps,
        )
        self._check_cancel(job)

        self._emit(
            job,
            JobEvent("phase", "Generating plots", {"phase": "plots"}),
        )
        create_plots(
            clean_df,
            output_path,
            trajectory_df=trajectory_df,
            trajectory_config=options.profile.trajectory,
        )
        self._check_cancel(job)

        if options.profile.video_overlay.enabled:
            self._emit(
                job,
                JobEvent("phase", "Rendering telemetry overlay video", {"phase": "overlay"}),
            )
            from webcalyzer.web.app import _read_rejected_df  # avoid cycles

            rejected_df = _read_rejected_df(output_path)
            render_telemetry_overlay_video(
                video_path=options.video_path,
                clean_df=clean_df,
                output_dir=output_path,
                config=options.profile.video_overlay,
                rejected_df=rejected_df,
                trajectory_df=trajectory_df,
                trajectory_config=options.profile.trajectory,
                engine=options.overlay_engine,
                encoder=options.overlay_encoder,
            )
        else:
            self._emit(
                job,
                JobEvent("phase", "Skipping overlay (disabled)", {"phase": "overlay_skipped"}),
            )

        save_profile(options.profile, output_path / "config_resolved.yaml")
        job.output_paths = sorted(_collect_output_paths(output_path))


def _physical_cpu_count() -> int:
    import os

    return os.cpu_count() or 1


def _collect_output_paths(output_dir: Path) -> list[str]:
    if not output_dir.exists():
        return []
    paths: list[str] = []
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(output_dir)
        if relative.parts and relative.parts[0] == "review":
            continue
        paths.append(str(relative))
    return paths


class _StreamingLogHandler(logging.Handler):
    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001
            message = record.getMessage()
        self._callback(message)


class _StreamingTextIO(io.TextIOBase):
    """Tee-like file-like object that also forwards every line to a callback."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self._callback = callback
        self._buffer = ""
        self._real = sys.__stdout__

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:  # type: ignore[override]
        if not text:
            return 0
        self._buffer += text
        try:
            if self._real is not None:
                self._real.write(text)
        except Exception:  # noqa: BLE001
            pass
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._callback(line)
        return len(text)

    def flush(self) -> None:  # type: ignore[override]
        if self._buffer.strip():
            self._callback(self._buffer)
        self._buffer = ""
        try:
            if self._real is not None:
                self._real.flush()
        except Exception:  # noqa: BLE001
            pass


def iter_event_dicts(events: Iterator[JobEvent]):
    for event in events:
        yield event.to_dict()
