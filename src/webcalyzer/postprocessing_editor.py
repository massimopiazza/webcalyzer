from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Callable, Iterable
import uuid

from webcalyzer.config import default_parsing_profile, load_profile
from webcalyzer.models import ProfileConfig
from webcalyzer.units import convert_value


MANIFEST_FILENAME = "postprocessing_manifest.json"
DRAFT_FILENAME = ".postprocessing_draft.json"
RAW_FILENAME = "telemetry_raw.csv"
RAW_BACKUP_FILENAME = "telemetry_raw.backup.csv"
LOCK_EXPIRY_S = 60.0
OBSERVATION_SUFFIXES = ("raw_text", "parse_status", "raw_unit", "raw_value", "si_value", "variant")
SOURCE_NODE = "raw_telemetry"
AUTOMATIC_REGENERATION_NODES = ("clean_telemetry", "rejected_telemetry", "trajectory", "acceleration", "plots")


class PostprocessingError(RuntimeError):
    pass


class PostprocessingConflict(PostprocessingError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def has_manifest(output_dir: str | Path) -> bool:
    return (Path(output_dir) / MANIFEST_FILENAME).is_file()


def initialize_manifest(
    output_dir: str | Path,
    *,
    profile: ProfileConfig | None = None,
    source_video: str | Path | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    profile = profile or _profile_from_output(output_path)
    overlay_enabled = bool(profile and profile.video_overlay.enabled)
    trajectory_enabled = bool(profile is None or profile.trajectory.enabled)
    now = utc_now()
    nodes = {
        SOURCE_NODE: _node("source_series", [], "stale", now),
        "clean_telemetry": _node("derived_series", [SOURCE_NODE], "stale", now),
        "rejected_telemetry": _node("derived_series", ["clean_telemetry"], "stale", now),
        "trajectory": _node(
            "derived_series",
            ["clean_telemetry"],
            "stale" if trajectory_enabled else "disabled",
            now,
            handler="trajectory",
        ),
        "acceleration": _node(
            "derived_series",
            ["trajectory", "clean_telemetry"],
            "stale" if trajectory_enabled else "disabled",
            now,
            handler="virtual",
        ),
        "plots": _node(
            "artifact",
            ["clean_telemetry", "rejected_telemetry", "trajectory", "acceleration"],
            "stale",
            now,
            handler="plots",
        ),
        "overlay": _node(
            "artifact",
            ["clean_telemetry", "rejected_telemetry", "trajectory", "acceleration"],
            "stale" if overlay_enabled else "disabled",
            now,
            handler="overlay",
        ),
    }
    manifest = {
        "schema_version": 1,
        "created_at": now,
        "updated_at": now,
        "source_video": str(Path(source_video).expanduser().resolve()) if source_video else None,
        "nodes": nodes,
        "last_save": None,
    }
    _write_json_atomic(output_path / MANIFEST_FILENAME, manifest)
    return manifest


def load_manifest(output_dir: str | Path) -> dict[str, Any]:
    path = Path(output_dir) / MANIFEST_FILENAME
    if not path.is_file():
        raise PostprocessingError("This output folder is not compatible with the Postprocessing editor.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("nodes"), dict):
        raise PostprocessingError("Unsupported post-processing manifest version.")
    return manifest


def update_manifest_nodes(
    output_dir: str | Path,
    statuses: dict[str, str],
    *,
    errors: dict[str, str | None] | None = None,
) -> dict[str, Any] | None:
    if not has_manifest(output_dir):
        return None
    output_path = Path(output_dir)
    manifest = load_manifest(output_path)
    now = utc_now()
    for node_id, status in statuses.items():
        node = manifest["nodes"].get(node_id)
        if node is None:
            continue
        node["status"] = status
        node["updated_at"] = now
        node["error"] = (errors or {}).get(node_id)
    manifest["updated_at"] = now
    _write_json_atomic(output_path / MANIFEST_FILENAME, manifest)
    return manifest


def mark_raw_materialized(output_dir: str | Path) -> dict[str, Any] | None:
    if not has_manifest(output_dir):
        return None
    ensure_raw_sample_ids(output_dir, persist=True)
    return update_manifest_nodes(
        output_dir,
        {
            SOURCE_NODE: "current",
            "clean_telemetry": "current",
            "rejected_telemetry": "current",
        },
    )


def mark_clean_current(output_dir: str | Path) -> dict[str, Any] | None:
    if not has_manifest(output_dir):
        return None
    manifest = load_manifest(output_dir)
    statuses = {"clean_telemetry": "current", "rejected_telemetry": "current", "plots": "stale"}
    if manifest["nodes"]["trajectory"]["status"] != "disabled":
        statuses["trajectory"] = "stale"
        statuses["acceleration"] = "stale"
    if manifest["nodes"]["overlay"]["status"] != "disabled":
        statuses["overlay"] = "stale"
    return update_manifest_nodes(output_dir, statuses)


def mark_trajectory_current(output_dir: str | Path) -> dict[str, Any] | None:
    if not has_manifest(output_dir):
        return None
    manifest = load_manifest(output_dir)
    statuses = {"trajectory": "current", "acceleration": "current", "plots": "stale"}
    if manifest["nodes"]["overlay"]["status"] != "disabled":
        statuses["overlay"] = "stale"
    return update_manifest_nodes(output_dir, statuses)


def mark_plots_current(output_dir: str | Path) -> dict[str, Any] | None:
    return update_manifest_nodes(output_dir, {"plots": "current"})


def ensure_raw_sample_ids(output_dir: str | Path, *, persist: bool) -> Any:
    import pandas as pd

    raw_path = Path(output_dir) / RAW_FILENAME
    raw_df = pd.read_csv(raw_path)
    if "sample_id" in raw_df.columns and raw_df["sample_id"].notna().all():
        return raw_df
    ids = _deterministic_sample_ids(raw_df)
    if "sample_id" in raw_df.columns:
        raw_df["sample_id"] = ids
    else:
        raw_df.insert(0, "sample_id", ids)
    if persist:
        _write_csv_atomic(raw_path, raw_df)
    return raw_df


def open_workspace(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    manifest = load_manifest(output_path)
    _assert_editable_manifest(manifest)
    draft = _read_draft(output_path)
    return {
        "path": str(output_path),
        "manifest": manifest,
        "draft": _draft_summary(draft) if draft else None,
    }


def acquire_session(
    output_dir: str | Path,
    *,
    action: str,
    session_token: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    manifest = load_manifest(output_path)
    _assert_editable_manifest(manifest)
    raw_df = ensure_raw_sample_ids(output_path, persist=True)
    current = _read_draft(output_path)
    now = time.time()

    if action == "discard":
        if current:
            _remove_draft(output_path)
        current = None
        action = "create"

    if current:
        expired = _draft_expired(current, now=now)
        same_owner = bool(session_token and session_token == current.get("session_token"))
        if action == "takeover" and expired:
            current["session_token"] = uuid.uuid4().hex
        elif action == "resume" and (expired or same_owner):
            current["session_token"] = current.get("session_token") or uuid.uuid4().hex
        elif action == "resume":
            raise PostprocessingConflict("The draft is active in another browser tab.")
        elif action == "create":
            raise PostprocessingConflict("An unsaved draft already exists.")
        else:
            raise PostprocessingConflict("The draft lock is still active.")
        current["heartbeat_at"] = now
        _write_draft(output_path, current)
        return _workspace_payload(output_path, current, raw_df=raw_df)

    if action not in {"create", "resume"}:
        raise PostprocessingError("There is no draft to resume or take over.")
    draft = {
        "schema_version": 1,
        "session_token": uuid.uuid4().hex,
        "created_at": utc_now(),
        "heartbeat_at": now,
        "raw_checksum": _file_checksum(output_path / RAW_FILENAME),
        "operations": [],
        "redo_operations": [],
        "applied": False,
        "applied_at": None,
    }
    _write_draft(output_path, draft)
    return _workspace_payload(output_path, draft, raw_df=raw_df)


def heartbeat(output_dir: str | Path, *, session_token: str) -> dict[str, Any]:
    output_path = Path(output_dir)
    draft = _owned_draft(output_path, session_token)
    draft["heartbeat_at"] = time.time()
    _write_draft(output_path, draft)
    return _draft_summary(draft)


def mutate_draft(
    output_dir: str | Path,
    *,
    session_token: str,
    action: str,
    field_name: str | None = None,
    sample_ids: Iterable[str] = (),
    value: float | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    draft = _owned_draft(output_path, session_token)
    if draft.get("applied"):
        raise PostprocessingConflict("Regeneration must finish before further edits.")

    if action in {"undo", "redo"}:
        _undo_or_redo(draft, action)
    else:
        if not field_name:
            raise PostprocessingError("field_name is required")
        raw_df = ensure_raw_sample_ids(output_path, persist=True)
        fields = _field_specs(_profile_from_output_required(output_path))
        field = next((item for item in fields if item["id"] == field_name), None)
        if field is None:
            raise PostprocessingError(f"Unknown telemetry field: {field_name}")
        existing = _correction_map(draft)
        changes: list[dict[str, Any]] = []
        for sample_id in dict.fromkeys(str(item) for item in sample_ids):
            if sample_id not in set(raw_df["sample_id"].astype(str)):
                raise PostprocessingError(f"Unknown sample_id: {sample_id}")
            key = _correction_key(sample_id, field_name)
            before = deepcopy(existing.get(key))
            if action == "delete":
                after: dict[str, Any] | None = {"kind": "deleted"}
            elif action == "restore":
                after = None
            elif action == "override":
                if value is None or unit is None:
                    raise PostprocessingError("value and unit are required for overrides")
                after = _manual_correction(field, float(value), unit)
            else:
                raise PostprocessingError(f"Unsupported draft action: {action}")
            if before != after:
                changes.append({"key": key, "before": before, "after": after})
        if changes:
            draft["operations"].append({"action": action, "changes": changes, "timestamp": utc_now()})
            draft["redo_operations"] = []
    draft["heartbeat_at"] = time.time()
    _write_draft(output_path, draft)
    return _workspace_payload(output_path, draft)


def discard_draft(output_dir: str | Path, *, session_token: str) -> dict[str, Any]:
    output_path = Path(output_dir)
    _owned_draft(output_path, session_token)
    _remove_draft(output_path)
    return {"discarded": True}


def apply_draft_to_raw(output_dir: str | Path, *, session_token: str) -> dict[str, Any]:
    output_path = Path(output_dir)
    draft = _owned_draft(output_path, session_token)
    raw_path = output_path / RAW_FILENAME
    if draft.get("applied"):
        return draft
    if _file_checksum(raw_path) != draft.get("raw_checksum"):
        raise PostprocessingConflict("telemetry_raw.csv changed after this draft was created. Reopen the editor.")

    raw_df = ensure_raw_sample_ids(output_path, persist=False)
    shutil.copy2(raw_path, output_path / RAW_BACKUP_FILENAME)
    corrections = _correction_map(draft)
    for key, correction in corrections.items():
        sample_id, field_name = _split_correction_key(key)
        matches = raw_df.index[raw_df["sample_id"].astype(str) == sample_id]
        if len(matches) != 1:
            raise PostprocessingError(f"Could not resolve draft target: {sample_id}")
        row_index = matches[0]
        if correction["kind"] == "deleted":
            for suffix in OBSERVATION_SUFFIXES:
                column = f"{field_name}_{suffix}"
                if column in raw_df.columns:
                    raw_df.at[row_index, column] = None
        else:
            raw_df.at[row_index, f"{field_name}_parse_status"] = "manual"
            raw_df.at[row_index, f"{field_name}_raw_unit"] = correction["unit"]
            raw_df.at[row_index, f"{field_name}_raw_value"] = correction["value"]
            raw_df.at[row_index, f"{field_name}_si_value"] = correction["si_value"]
            raw_df.at[row_index, f"{field_name}_variant"] = "manual"
    _write_csv_atomic(raw_path, raw_df)
    draft["applied"] = True
    draft["applied_at"] = utc_now()
    draft["raw_checksum"] = _file_checksum(raw_path)
    _write_draft(output_path, draft)
    manifest = load_manifest(output_path)
    statuses = {SOURCE_NODE: "current"}
    for node_id in AUTOMATIC_REGENERATION_NODES:
        if manifest["nodes"][node_id]["status"] != "disabled":
            statuses[node_id] = "stale"
    if manifest["nodes"]["overlay"]["status"] != "disabled":
        statuses["overlay"] = "stale"
    manifest = update_manifest_nodes(output_path, statuses)
    if manifest is not None:
        manifest["last_save"] = {
            "started_at": draft["applied_at"],
            "completed_at": None,
            "edit_counts": _edit_counts(draft),
        }
        _write_json_atomic(output_path / MANIFEST_FILENAME, manifest)
    return draft


def regenerate_output_dir(
    output_dir: str | Path,
    *,
    cancel_check: Callable[[], None] | None = None,
    phase_callback: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    from webcalyzer.plotting import create_plots
    from webcalyzer.postprocess import apply_outlier_rejection_in_output_dir, rebuild_clean_in_output_dir
    from webcalyzer.trajectory import write_trajectory_outputs

    output_path = Path(output_dir)
    profile = _profile_from_output_required(output_path)
    manifest = load_manifest(output_path)
    try:
        if cancel_check:
            cancel_check()
        if phase_callback:
            phase_callback("rebuild_clean", "Rebuilding clean telemetry")
        if profile.trajectory.outlier_rejection_enabled:
            clean_df = apply_outlier_rejection_in_output_dir(output_path, profile=profile)
        else:
            clean_df = rebuild_clean_in_output_dir(output_path, profile=profile)
        update_manifest_nodes(output_path, {"clean_telemetry": "current", "rejected_telemetry": "current"})

        if cancel_check:
            cancel_check()
        trajectory_df = None
        if profile.trajectory.enabled:
            if phase_callback:
                phase_callback("trajectory", "Reconstructing trajectory")
            clean_df, trajectory_df = write_trajectory_outputs(clean_df, output_path, profile.trajectory)
            update_manifest_nodes(output_path, {"trajectory": "current", "acceleration": "current"})
        else:
            update_manifest_nodes(output_path, {"trajectory": "disabled", "acceleration": "disabled"})

        if cancel_check:
            cancel_check()
        if phase_callback:
            phase_callback("plots", "Generating plots")
        create_plots(
            clean_df,
            output_path,
            trajectory_df=trajectory_df,
            trajectory_config=profile.trajectory,
            profile=profile,
        )
        manifest = update_manifest_nodes(output_path, {"plots": "current"})
        if cancel_check:
            cancel_check()
    except Exception as exc:
        if exc.__class__.__name__ != "JobCancelled":
            mark_regeneration_failed(output_path, str(exc))
        raise

    draft = _read_draft(output_path)
    if draft and draft.get("applied"):
        _remove_draft(output_path)
    manifest = manifest or load_manifest(output_path)
    if manifest.get("last_save"):
        manifest["last_save"]["completed_at"] = utc_now()
        manifest["updated_at"] = utc_now()
        _write_json_atomic(output_path / MANIFEST_FILENAME, manifest)
    return manifest


def mark_regeneration_failed(output_dir: str | Path, error: str) -> None:
    manifest = load_manifest(output_dir)
    statuses: dict[str, str] = {}
    errors: dict[str, str] = {}
    for node_id in AUTOMATIC_REGENERATION_NODES:
        node = manifest["nodes"][node_id]
        if node["status"] == "stale":
            statuses[node_id] = "failed"
            errors[node_id] = error
            break
    update_manifest_nodes(output_dir, statuses, errors=errors)


def mark_overlay_current(output_dir: str | Path) -> None:
    update_manifest_nodes(output_dir, {"overlay": "current"})


def workspace_after_regeneration(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    return {
        "path": str(output_path),
        "manifest": load_manifest(output_path),
        "draft": _draft_summary(_read_draft(output_path)) if _read_draft(output_path) else None,
    }


def _workspace_payload(output_path: Path, draft: dict[str, Any], *, raw_df: Any | None = None) -> dict[str, Any]:
    import pandas as pd

    raw_df = raw_df if raw_df is not None else ensure_raw_sample_ids(output_path, persist=True)
    profile = _profile_from_output_required(output_path)
    fields = _field_specs(profile)
    corrections = _correction_map(draft)
    rejected_df = _read_optional_csv(output_path / "telemetry_rejected.csv")
    fields_payload: list[dict[str, Any]] = []
    for field in fields:
        observations = []
        clean_column = field["clean_column"]
        rejected = []
        rejected_keys: set[tuple[float, float]] = set()
        if rejected_df is not None and clean_column in rejected_df.columns:
            for _, row in rejected_df.iterrows():
                value = _optional_float(row.get(clean_column))
                met = _optional_float(row.get("mission_elapsed_time_s"))
                if value is not None and met is not None:
                    rejected.append({"mission_elapsed_time_s": met, "value": value})
                    rejected_keys.add(_observation_key(met, value))
        for _, row in raw_df.iterrows():
            sample_id = str(row["sample_id"])
            correction = corrections.get(_correction_key(sample_id, field["id"]))
            met = _optional_float(row.get("mission_elapsed_time_s"))
            baseline_si = _optional_float(row.get(f"{field['id']}_si_value"))
            baseline_raw = _optional_float(row.get(f"{field['id']}_raw_value"))
            deleted = bool(correction and correction.get("kind") == "deleted")
            manual = bool(correction and correction.get("kind") == "manual")
            si_value = correction["si_value"] if manual else baseline_si
            raw_value = correction["value"] if manual else baseline_raw
            raw_unit = correction["unit"] if manual else _optional_text(row.get(f"{field['id']}_raw_unit"))
            raw_text = _optional_text(row.get(f"{field['id']}_raw_text"))
            status = "manual" if manual else _optional_text(row.get(f"{field['id']}_parse_status"))
            if raw_text is None and raw_value is None and si_value is None and not deleted:
                continue
            observations.append(
                {
                    "sample_id": sample_id,
                    "mission_elapsed_time_s": met,
                    "raw_text": raw_text,
                    "raw_value": raw_value,
                    "raw_unit": raw_unit,
                    "value": si_value,
                    "parse_status": status,
                    "deleted": deleted,
                    "manual": manual,
                    "plottable": si_value is not None,
                    "outlier": (
                        _observation_key(met, baseline_si) in rejected_keys
                        if met is not None and baseline_si is not None
                        else False
                    ),
                }
            )
        fields_payload.append({**field, "observations": observations, "rejected": rejected})
    return {
        "path": str(output_path),
        "manifest": load_manifest(output_path),
        "draft": _draft_summary(draft),
        "session_token": draft["session_token"],
        "fields": fields_payload,
        "pending_recomputations": _pending_recomputations(load_manifest(output_path)),
    }


def _field_specs(profile: ProfileConfig) -> list[dict[str, Any]]:
    parsing = profile.parsing or default_parsing_profile()
    fields = [
        _standard_field("stage1_velocity", "Stage 1 velocity", "stage1_velocity_mps", "velocity", parsing.velocity),
        _standard_field("stage1_altitude", "Stage 1 altitude", "stage1_altitude_m", "altitude", parsing.altitude),
        _standard_field("stage2_velocity", "Stage 2 velocity", "stage2_velocity_mps", "velocity", parsing.velocity),
        _standard_field("stage2_altitude", "Stage 2 altitude", "stage2_altitude_m", "altitude", parsing.altitude),
    ]
    for quantity in profile.custom_telemetry_quantities:
        units = [{"name": "DISPLAY", "label": quantity.display_unit, "expression": quantity.display_unit}]
        units.extend(
            {"name": alias, "label": alias, "expression": expression}
            for alias, expression in sorted(quantity.unit_aliases.items())
        )
        fields.append(
            {
                "id": quantity.field_name(),
                "label": quantity.name,
                "clean_column": quantity.field_name(),
                "kind": "custom",
                "output_unit": quantity.display_unit,
                "units": units,
            }
        )
    return fields


def _standard_field(field_id: str, label: str, clean_column: str, kind: str, parsing: Any) -> dict[str, Any]:
    output_unit = parsing.output_unit or ("meter/second" if kind == "velocity" else "meter")
    return {
        "id": field_id,
        "label": label,
        "clean_column": clean_column,
        "kind": kind,
        "output_unit": output_unit,
        "units": [
            {"name": unit.name, "label": unit.name, "expression": unit.unit_expression}
            for unit in parsing.units
        ],
    }


def _manual_correction(field: dict[str, Any], value: float, unit_name: str) -> dict[str, Any]:
    option = next((item for item in field["units"] if item["name"] == unit_name), None)
    if option is None:
        raise PostprocessingError(f"Unsupported unit {unit_name!r} for {field['label']}")
    converted = convert_value(value, option["expression"], field["output_unit"])
    if converted is None:
        raise PostprocessingError(f"Could not convert {value:g} {unit_name} into {field['output_unit']}")
    return {"kind": "manual", "value": value, "unit": unit_name, "si_value": converted}


def _deterministic_sample_ids(raw_df: Any) -> list[str]:
    ids: list[str] = []
    counts: dict[str, int] = {}
    for _, row in raw_df.iterrows():
        statuses = [
            _optional_text(row.get(column))
            for column in raw_df.columns
            if column.endswith("_parse_status")
        ]
        met = _format_identity_number(row.get("mission_elapsed_time_s"))
        if "hardcoded" in statuses:
            base = f"anchor:{met}"
        else:
            frame = _format_identity_number(row.get("frame_index"))
            sample = _format_identity_number(row.get("sample_time_s"))
            base = f"frame:{frame}:time:{sample}"
        ordinal = counts.get(base, 0)
        counts[base] = ordinal + 1
        ids.append(base if ordinal == 0 else f"{base}:{ordinal + 1}")
    return ids


def _pending_recomputations(manifest: dict[str, Any]) -> list[str]:
    labels = {
        "clean_telemetry": "clean telemetry",
        "rejected_telemetry": "outlier rejection",
        "trajectory": "trajectory",
        "acceleration": "acceleration",
        "plots": "plots",
        "overlay": "overlay video",
    }
    return [
        labels[node_id]
        for node_id, node in manifest["nodes"].items()
        if node_id in labels and node["status"] in {"stale", "failed"}
    ]


def _node(kind: str, depends_on: list[str], status: str, now: str, *, handler: str | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "depends_on": depends_on,
        "handler": handler,
        "status": status,
        "updated_at": now,
        "error": None,
    }


def _assert_editable_manifest(manifest: dict[str, Any]) -> None:
    raw = manifest["nodes"].get(SOURCE_NODE)
    if not raw or raw.get("status") != "current":
        raise PostprocessingError("Raw telemetry is not current. Finish or repair extraction before editing.")


def _draft_summary(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_token": draft.get("session_token"),
        "created_at": draft.get("created_at"),
        "heartbeat_at": draft.get("heartbeat_at"),
        "expired": _draft_expired(draft),
        "applied": bool(draft.get("applied")),
        "operation_count": len(draft.get("operations", [])),
        "redo_count": len(draft.get("redo_operations", [])),
        "edit_counts": _edit_counts(draft),
    }


def _edit_counts(draft: dict[str, Any]) -> dict[str, int]:
    counts = {"deleted": 0, "manual": 0}
    for correction in _correction_map(draft).values():
        counts[correction["kind"]] = counts.get(correction["kind"], 0) + 1
    return counts


def _correction_map(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
    corrections: dict[str, dict[str, Any]] = {}
    for operation in draft.get("operations", []):
        for change in operation.get("changes", []):
            if change.get("after") is None:
                corrections.pop(change["key"], None)
            else:
                corrections[change["key"]] = deepcopy(change["after"])
    return corrections


def _undo_or_redo(draft: dict[str, Any], action: str) -> None:
    if action == "undo":
        if draft["operations"]:
            draft["redo_operations"].append(draft["operations"].pop())
        return
    if draft["redo_operations"]:
        draft["operations"].append(draft["redo_operations"].pop())


def _correction_key(sample_id: str, field_name: str) -> str:
    return f"{sample_id}\u001f{field_name}"


def _split_correction_key(key: str) -> tuple[str, str]:
    return tuple(key.split("\u001f", 1))  # type: ignore[return-value]


def _read_draft(output_path: Path) -> dict[str, Any] | None:
    path = output_path / DRAFT_FILENAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_draft(output_path: Path, draft: dict[str, Any]) -> None:
    _write_json_atomic(output_path / DRAFT_FILENAME, draft)


def _remove_draft(output_path: Path) -> None:
    path = output_path / DRAFT_FILENAME
    if path.exists():
        path.unlink()


def _owned_draft(output_path: Path, session_token: str) -> dict[str, Any]:
    draft = _read_draft(output_path)
    if draft is None:
        raise PostprocessingError("No active post-processing draft.")
    if draft.get("session_token") != session_token:
        raise PostprocessingConflict("This draft belongs to another browser session.")
    return draft


def _draft_expired(draft: dict[str, Any], *, now: float | None = None) -> bool:
    return (now or time.time()) - float(draft.get("heartbeat_at", 0.0)) > LOCK_EXPIRY_S


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def _write_csv_atomic(path: Path, df: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temp_name = handle.name
    try:
        df.to_csv(temp_name, index=False)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_optional_csv(path: Path) -> Any | None:
    if not path.is_file():
        return None
    import pandas as pd

    return pd.read_csv(path)


def _profile_from_output(output_path: Path) -> ProfileConfig | None:
    profile_path = output_path / "config_resolved.yaml"
    return load_profile(profile_path) if profile_path.is_file() else None


def _profile_from_output_required(output_path: Path) -> ProfileConfig:
    profile = _profile_from_output(output_path)
    if profile is None:
        raise PostprocessingError("config_resolved.yaml is required for post-processing.")
    return profile


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _observation_key(mission_elapsed_time_s: float, value: float) -> tuple[float, float]:
    return round(mission_elapsed_time_s, 9), round(value, 9)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except TypeError:
        pass
    return str(value)


def _format_identity_number(value: object) -> str:
    parsed = _optional_float(value)
    return "na" if parsed is None else f"{parsed:.9g}"
