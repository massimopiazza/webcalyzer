from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from webcalyzer.config import load_profile, save_profile
from webcalyzer.video import evenly_spaced_indices, get_video_metadata, read_frame

from webcalyzer.web.files import (
    BrowseRoot,
    is_within_roots,
    listing,
    normalize_roots,
    safe_resolve,
)
from webcalyzer.web.jobs import JobManager, JobOptions
from webcalyzer.web.schema import (
    ProfileModel,
    default_parsing_model,
    model_to_profile_dataclass,
    profile_dataclass_to_model,
    serialize_for_yaml,
    trajectory_choices,
)


@dataclass
class ServeConfig:
    roots: list[BrowseRoot]
    templates_dir: Path
    dist_dir: Path | None
    cors_origins: list[str]


def _read_rejected_df(output_dir: Path):
    """Re-export so jobs.py can avoid importing pandas at module load time."""
    import pandas as pd

    rejected_path = Path(output_dir) / "telemetry_rejected.csv"
    if not rejected_path.exists():
        return None
    rejected_df = pd.read_csv(rejected_path)
    return rejected_df if not rejected_df.empty else None


def create_app(config: ServeConfig) -> FastAPI:
    app = FastAPI(title="webcalyzer", version="0.1.0")
    app.state.config = config
    app.state.jobs = JobManager()

    if config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ----- meta -----------------------------------------------------------
    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        return {
            "version": "0.1.0",
            "roots": [{"label": root.label, "path": str(root.path)} for root in config.roots],
            "templates_dir": str(config.templates_dir),
            "trajectory": trajectory_choices(),
            "default_parsing": default_parsing_model().model_dump(),
        }

    # ----- file browser ---------------------------------------------------
    @app.get("/api/files")
    def files(
        path: str | None = Query(default=None),
        kinds: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            target = safe_resolve(path, config.roots)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            kinds_set = {k.strip() for k in kinds.split(",")} if kinds else None
            return listing(target, kinds=kinds_set)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ----- video probe ---------------------------------------------------
    @app.get("/api/video/metadata")
    def video_metadata(path: str = Query(...)) -> dict[str, Any]:
        target = _ensure_within(config, path)
        try:
            metadata = get_video_metadata(target)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return metadata.to_dict()

    @app.get("/api/video/frame")
    def video_frame(
        path: str = Query(...),
        time_s: float = Query(0.0, ge=0.0),
        max_width: int = Query(1280, gt=0, le=3840),
    ) -> Response:
        target = _ensure_within(config, path)
        try:
            metadata = get_video_metadata(target)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        frame_index = int(round(min(time_s, metadata.duration_s) * metadata.fps))
        frame_index = max(0, min(metadata.frame_count - 1, frame_index))
        try:
            frame = read_frame(target, frame_index)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        jpeg_bytes = _frame_to_jpeg(frame, max_width=max_width)
        return Response(content=jpeg_bytes, media_type="image/jpeg")

    @app.get("/api/video/fixture-frames")
    def video_fixture_frames(
        path: str = Query(...),
        count: int = Query(20, ge=1, le=200),
        start_s: float | None = Query(None, ge=0.0),
        end_s: float | None = Query(None, ge=0.0),
    ) -> dict[str, Any]:
        target = _ensure_within(config, path)
        metadata = get_video_metadata(target)
        time_range = (start_s, end_s) if start_s is not None and end_s is not None else None
        indices = evenly_spaced_indices(metadata, count=count, time_range_s=time_range)
        frames = [
            {
                "index": int(index),
                "time_s": float(index) / metadata.fps if metadata.fps else 0.0,
            }
            for index in indices
        ]
        return {
            "video": metadata.to_dict(),
            "frames": frames,
        }

    @app.get("/api/video/frame-by-index")
    def video_frame_by_index(
        path: str = Query(...),
        index: int = Query(..., ge=0),
        max_width: int = Query(1280, gt=0, le=3840),
    ) -> Response:
        target = _ensure_within(config, path)
        try:
            frame = read_frame(target, index)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        jpeg_bytes = _frame_to_jpeg(frame, max_width=max_width)
        return Response(content=jpeg_bytes, media_type="image/jpeg")

    # ----- templates -----------------------------------------------------
    @app.get("/api/templates")
    def list_templates() -> list[dict[str, Any]]:
        directory = config.templates_dir
        directory.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        for path in sorted(directory.rglob("*.yaml")):
            stat = path.stat()
            try:
                profile = load_profile(path)
                profile_name = profile.profile_name
                description = profile.description
                error = None
            except Exception as exc:  # noqa: BLE001
                profile_name = path.stem
                description = ""
                error = str(exc)
            results.append(
                {
                    "name": str(path.relative_to(directory)),
                    "profile_name": profile_name,
                    "description": description,
                    "modified": stat.st_mtime,
                    "size": stat.st_size,
                    "error": error,
                }
            )
        return results

    @app.get("/api/templates/{name:path}")
    def get_template(name: str) -> dict[str, Any]:
        target = _resolve_template_path(config, name, must_exist=True)
        profile = load_profile(target)
        model = profile_dataclass_to_model(profile)
        return {"name": name, "profile": model.model_dump(mode="json")}

    @app.put("/api/templates/{name:path}")
    def save_template(name: str, profile: dict[str, Any] = Body(...)) -> dict[str, Any]:
        target = _resolve_template_path(config, name, must_exist=False)
        try:
            model = ProfileModel.model_validate(profile)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=_format_validation_error(exc)) from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        save_profile(model_to_profile_dataclass(model), target)
        return {"name": name, "path": str(target)}

    @app.delete("/api/templates/{name:path}")
    def delete_template(name: str) -> dict[str, Any]:
        target = _resolve_template_path(config, name, must_exist=True)
        target.unlink()
        return {"name": name, "deleted": True}

    @app.post("/api/templates/import")
    def import_template(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        yaml_text = str(payload.get("yaml", ""))
        if not name:
            raise HTTPException(status_code=422, detail="`name` is required")
        if not name.endswith(".yaml"):
            name = f"{name}.yaml"
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise HTTPException(status_code=422, detail="YAML must describe a mapping")
        target = _resolve_template_path(config, name, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml_text)
        try:
            profile = load_profile(target)
            model = profile_dataclass_to_model(profile)
        except Exception as exc:  # noqa: BLE001
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"name": name, "profile": model.model_dump(mode="json")}

    @app.get("/api/templates/{name:path}/yaml")
    def template_yaml(name: str) -> Response:
        target = _resolve_template_path(config, name, must_exist=True)
        return FileResponse(target, media_type="text/yaml", filename=target.name)

    @app.post("/api/profile/validate")
    def validate_profile(profile: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            model = ProfileModel.model_validate(profile)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=_format_validation_error(exc)) from exc
        return {"profile": model.model_dump(mode="json")}

    @app.post("/api/profile/preview-yaml")
    def preview_yaml(profile: dict[str, Any] = Body(...)) -> Response:
        try:
            model = ProfileModel.model_validate(profile)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=_format_validation_error(exc)) from exc
        text = yaml.safe_dump(serialize_for_yaml(model), sort_keys=False, width=1000)
        return Response(content=text, media_type="text/yaml")

    # ----- calibration ---------------------------------------------------
    @app.post("/api/calibrate/save")
    def calibration_save(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        target_name = str(payload.get("template", "")).strip()
        profile_payload = payload.get("profile")
        if not target_name or profile_payload is None:
            raise HTTPException(status_code=422, detail="`template` and `profile` are required")
        try:
            model = ProfileModel.model_validate(profile_payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=_format_validation_error(exc)) from exc
        target = _resolve_template_path(config, target_name, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        save_profile(model_to_profile_dataclass(model), target)
        return {"name": target_name, "path": str(target)}

    # ----- jobs ----------------------------------------------------------
    @app.get("/api/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return app.state.jobs.list_jobs()

    @app.post("/api/jobs/run")
    async def run_job(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            video_path = _ensure_within(config, payload["video_path"])
            output_dir = _ensure_within_writable(config, payload["output_dir"])
            profile_payload = payload["profile"]
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"Missing field: {exc}") from exc

        try:
            model = ProfileModel.model_validate(profile_payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=_format_validation_error(exc)) from exc
        profile = model_to_profile_dataclass(model)

        options = JobOptions(
            video_path=video_path,
            output_dir=output_dir,
            profile=profile,
            sample_fps=_optional_float(payload.get("sample_fps")),
            ocr_backend=str(payload.get("ocr_backend", "auto")),
            ocr_recognition_level=str(payload.get("ocr_recognition_level", "accurate")),
            ocr_workers=int(payload.get("ocr_workers", 0)),
            ocr_skip_detection=bool(payload.get("ocr_skip_detection", False)),
            overlay_engine=str(payload.get("overlay_engine", "auto")),
            overlay_encoder=str(payload.get("overlay_encoder", "auto")),
        )
        loop = asyncio.get_running_loop()
        try:
            job = app.state.jobs.submit(options, loop)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": job.id, "state": job.state}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job")
        return {
            **job.to_summary(),
            "events": [event.to_dict() for event in job.events[-200:]],
        }

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        ok = app.state.jobs.cancel(job_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Unknown or finished job")
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/events")
    async def stream_job_events(job_id: str, request: Request):
        try:
            job, queue = app.state.jobs.subscribe(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job") from exc

        async def event_source():
            try:
                # Replay buffered events first
                for event in list(job.events):
                    yield _format_sse(event.to_dict())
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield _format_sse(event.to_dict())
                    if event.kind in {"done", "error", "cancelled"}:
                        break
            finally:
                app.state.jobs.unsubscribe(job, queue)

        return StreamingResponse(event_source(), media_type="text/event-stream")

    @app.get("/api/jobs/{job_id}/files/{relpath:path}")
    def get_job_file(job_id: str, relpath: str):
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job")
        base = Path(job.options.output_dir).resolve()
        target = (base / relpath).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Path escapes output dir") from exc
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(target)

    # ----- static frontend ----------------------------------------------
    if config.dist_dir and (config.dist_dir / "index.html").exists():
        # Mount built frontend.
        assets_dir = config.dist_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/", response_class=HTMLResponse)
        def index() -> HTMLResponse:
            return HTMLResponse((config.dist_dir / "index.html").read_text())

        @app.get("/{full_path:path}", response_class=HTMLResponse)
        def spa_fallback(full_path: str) -> HTMLResponse:
            # Anything that isn't an API call falls back to the SPA shell so
            # the React router can handle client-side routing.
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            asset_path = config.dist_dir / full_path
            if asset_path.is_file():
                return FileResponse(asset_path)  # type: ignore[return-value]
            return HTMLResponse((config.dist_dir / "index.html").read_text())
    else:

        @app.get("/", response_class=HTMLResponse)
        def index_missing() -> HTMLResponse:
            return HTMLResponse(
                """<!doctype html><meta charset='utf-8'>
                <title>webcalyzer</title>
                <body style='font-family:ui-sans-serif,system-ui;background:#0b0f1a;color:#e6ebf5;padding:2rem;line-height:1.6'>
                <h1 style='color:#5cc4ff'>webcalyzer web UI</h1>
                <p>The frontend bundle is not built. From the project root run:</p>
                <pre style='background:#111728;padding:1rem;border-radius:8px'>cd web && npm install && npm run build</pre>
                <p>Then refresh this page. The API is already running; see <code>/docs</code>.</p>
                </body>"""
            )

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_template_path(config: ServeConfig, name: str, *, must_exist: bool) -> Path:
    if not name:
        raise HTTPException(status_code=422, detail="Template name is required")
    if not re.fullmatch(r"[A-Za-z0-9._\-/ ]+", name):
        raise HTTPException(status_code=422, detail="Invalid template name")
    if name.startswith("/") or ".." in Path(name).parts:
        raise HTTPException(status_code=422, detail="Invalid template name")
    if not name.endswith(".yaml"):
        name = f"{name}.yaml"
    target = (config.templates_dir / name).resolve()
    try:
        target.relative_to(config.templates_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Template escapes templates dir") from exc
    if must_exist and not target.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return target


def _ensure_within(config: ServeConfig, path: str | Path) -> Path:
    try:
        return safe_resolve(str(path), config.roots)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _ensure_within_writable(config: ServeConfig, path: str | Path) -> Path:
    target = Path(str(path)).expanduser().resolve()
    if not is_within_roots(target, config.roots):
        raise HTTPException(
            status_code=403,
            detail=f"Output path is outside the allowed roots: {target}",
        )
    target.mkdir(parents=True, exist_ok=True)
    return target


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_validation_error(exc: Exception) -> Any:
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        cleaned: list[dict[str, Any]] = []
        for err in exc.errors(include_url=False):
            entry: dict[str, Any] = {
                "type": err.get("type"),
                "loc": list(err.get("loc", ())),
                "msg": err.get("msg"),
            }
            ctx = err.get("ctx")
            if ctx:
                entry["ctx"] = {k: str(v) for k, v in ctx.items()}
            input_value = err.get("input")
            if input_value is not None and isinstance(input_value, (str, int, float, bool, list, dict)):
                entry["input"] = input_value
            cleaned.append(entry)
        return cleaned
    return str(exc)


def _format_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _frame_to_jpeg(frame, *, max_width: int) -> bytes:
    import cv2

    height, width = frame.shape[:2]
    if width > max_width:
        scale = max_width / float(width)
        new_size = (max_width, max(1, int(round(height * scale))))
        frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise HTTPException(status_code=500, detail="JPEG encoding failed")
    return bytes(buffer)
