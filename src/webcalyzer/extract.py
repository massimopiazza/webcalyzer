from __future__ import annotations

from dataclasses import dataclass, field
import json
import multiprocessing as mp
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

from webcalyzer.config import save_profile
from webcalyzer.models import Box, ExtractionRow, OCRObservation, ProfileConfig
from webcalyzer.ocr import OCRBackend, OCRDetection
from webcalyzer.ocr_factory import OCRBackendOptions, make_backend, resolve_backend_name
from webcalyzer.raw_points import apply_hardcoded_raw_data_points
from webcalyzer.sanitize import MeasurementOption, choose_best_measurement, parse_measurement_options, parse_met_candidates
from webcalyzer.video import build_sample_indices, crop_box, get_video_metadata, iterate_frames


@dataclass(slots=True)
class FieldState:
    previous_value_si: float | None = None
    previous_met_s: float | None = None


@dataclass(slots=True)
class StageState:
    activated: bool = False
    fields: dict[str, FieldState] | None = None

    def __post_init__(self) -> None:
        if self.fields is None:
            self.fields = {}


@dataclass(slots=True)
class FrameRawOCR:
    """Output of Phase A: raw OCR candidates for one frame.

    No state-dependent filtering happens here so workers can produce these
    records out of order and Phase B replays them sequentially to apply MET
    tracking, stage activation and plausibility checks.
    """

    frame_index: int
    sample_time_s: float
    candidates_by_field: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


def extract_telemetry(
    video_path: str | Path,
    profile: ProfileConfig,
    output_dir: str | Path,
    sample_fps: float | None = None,
    *,
    backend_options: OCRBackendOptions | None = None,
    workers: int = 1,
    skip_detection: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    metadata = get_video_metadata(video_path)
    effective_fps = float(sample_fps or profile.default_sample_fps)
    sample_indices = build_sample_indices(metadata=metadata, target_fps=effective_fps)
    if not sample_indices:
        raise RuntimeError("No frames selected for extraction; check the video and sample_fps.")
    backend_options = (backend_options or OCRBackendOptions()).validate()
    if profile.parsing is not None and not backend_options.custom_words:
        # Inject the OCR vocabulary derived from the parsing profile so the
        # OCR engine can be steered without code changes.
        from dataclasses import replace as dataclass_replace

        backend_options = dataclass_replace(
            backend_options,
            custom_words=tuple(profile.parsing.custom_words_list()),
        ).validate()
    workers = max(1, int(workers))

    resolved_backend = resolve_backend_name(backend_options.backend)
    print(
        f"[webcalyzer] extraction settings: backend={resolved_backend} workers={workers} "
        f"skip_detection={skip_detection} samples={len(sample_indices)}"
    )

    started_at = time.perf_counter()
    raw_frames = _run_phase_a(
        video_path=video_path,
        profile=profile,
        metadata_fps=metadata.fps,
        sample_indices=sample_indices,
        backend_options=backend_options,
        workers=workers,
        skip_detection=skip_detection,
    )
    phase_a_elapsed = time.perf_counter() - started_at
    print(
        f"[webcalyzer] phase A complete: {len(raw_frames)} frames OCR'd in "
        f"{phase_a_elapsed:.1f}s ({len(raw_frames) / max(phase_a_elapsed, 1e-9):.2f} fps)"
    )

    raw_rows, clean_rows = _run_phase_b(
        profile=profile,
        raw_frames=raw_frames,
        metadata_fps=metadata.fps,
    )

    raw_df = pd.DataFrame(raw_rows)
    if profile.hardcoded_raw_data_points:
        from webcalyzer.postprocess import rebuild_clean_from_raw

        raw_df = apply_hardcoded_raw_data_points(raw_df, profile.hardcoded_raw_data_points)
        clean_df = rebuild_clean_from_raw(raw_df)
    else:
        clean_df = pd.DataFrame(clean_rows)
    raw_df.to_csv(output_path / "telemetry_raw.csv", index=False)
    clean_df.to_csv(output_path / "telemetry_clean.csv", index=False)
    pd.DataFrame(columns=clean_df.columns).to_csv(output_path / "telemetry_rejected.csv", index=False)
    save_profile(profile, output_path / "config_resolved.yaml")
    (output_path / "run_metadata.json").write_text(
        json.dumps(
            {
                "video": metadata.to_dict(),
                "sample_fps_requested": effective_fps,
                "sample_count": len(sample_indices),
                "profile_name": profile.profile_name,
                "ocr": {
                    "backend": resolved_backend,
                    "backend_requested": backend_options.backend,
                    "workers": workers,
                    "skip_detection": skip_detection,
                    "recognition_level": backend_options.recognition_level,
                    "phase_a_seconds": phase_a_elapsed,
                },
            },
            indent=2,
        )
    )
    return raw_df, clean_df


def _run_phase_a(
    *,
    video_path: str | Path,
    profile: ProfileConfig,
    metadata_fps: float,
    sample_indices: list[int],
    backend_options: OCRBackendOptions,
    workers: int,
    skip_detection: bool,
) -> list[FrameRawOCR]:
    if workers <= 1:
        backend = make_backend(backend_options)
        results: list[FrameRawOCR] = []
        frames = iterate_frames(video_path, sample_indices)
        total = len(frames)
        for idx, (frame_index, frame) in enumerate(frames, start=1):
            results.append(
                _ocr_frame(
                    frame_index=frame_index,
                    frame=frame,
                    profile=profile,
                    metadata_fps=metadata_fps,
                    backend=backend,
                    skip_detection=skip_detection,
                )
            )
            if idx % 25 == 0 or idx == total:
                print(f"[webcalyzer] phase A: processed {idx}/{total} samples")
        return results

    chunks = _split_indices_into_chunks(sample_indices, workers)
    ctx = mp.get_context("spawn")
    payloads = [
        (str(video_path), profile, metadata_fps, backend_options, skip_detection, chunk)
        for chunk in chunks
    ]
    print(f"[webcalyzer] phase A: dispatching {len(payloads)} chunks across {workers} workers")
    with ctx.Pool(processes=workers) as pool:
        chunk_results = pool.map(_phase_a_worker, payloads)
    flattened: list[FrameRawOCR] = []
    for chunk in chunk_results:
        flattened.extend(chunk)
    flattened.sort(key=lambda item: item.frame_index)
    return flattened


def _phase_a_worker(payload: tuple) -> list[FrameRawOCR]:
    video_path, profile, metadata_fps, backend_options, skip_detection, frame_indices = payload
    backend = make_backend(backend_options)
    frames = iterate_frames(video_path, list(frame_indices))
    return [
        _ocr_frame(
            frame_index=frame_index,
            frame=frame,
            profile=profile,
            metadata_fps=metadata_fps,
            backend=backend,
            skip_detection=skip_detection,
        )
        for frame_index, frame in frames
    ]


def _ocr_frame(
    *,
    frame_index: int,
    frame,
    profile: ProfileConfig,
    metadata_fps: float,
    backend: OCRBackend,
    skip_detection: bool,
) -> FrameRawOCR:
    sample_time_s = frame_index / metadata_fps if metadata_fps else 0.0
    if skip_detection:
        candidates_by_field = _ocr_skip_detection(frame=frame, profile=profile, backend=backend)
    else:
        candidates_by_field = _ocr_with_detection(frame=frame, profile=profile, backend=backend)
    return FrameRawOCR(
        frame_index=frame_index,
        sample_time_s=sample_time_s,
        candidates_by_field=candidates_by_field,
    )


def _ocr_with_detection(
    *,
    frame,
    profile: ProfileConfig,
    backend: OCRBackend,
) -> dict[str, list[tuple[str, str]]]:
    strip_box = _build_strip_union_box(profile)
    strip_crop = crop_box(frame, strip_box)
    strip_detections = backend.extract_detections(strip_crop, mode="strip")
    ocr_candidates_by_field = _assign_strip_detections(
        profile=profile,
        frame=frame,
        strip_box=strip_box,
        detections=strip_detections,
    )

    # Per-field multi-variant fallback. Triggered when strip-level parsing
    # cannot produce a usable measurement (or, for MET, a usable timestamp).
    # This mirrors the original sequential pipeline; the parse is cheap and
    # stateless, so it stays in Phase A.
    parsing = profile.parsing
    for field_name, field_cfg in profile.fields.items():
        candidates = ocr_candidates_by_field.get(field_name, [])
        if field_cfg.kind == "met":
            if parse_met_candidates(candidates, parsing=parsing) is not None:
                continue
        else:
            options = [
                option
                for raw_text, variant in candidates
                for option in parse_measurement_options(
                    raw_text, kind=field_cfg.kind, variant=variant, parsing=parsing
                )
                if _field_specific_option_is_valid(field_name, option)
            ]
            if options:
                continue
        crop = crop_box(frame, field_cfg.box)
        fallback = backend.extract_text(crop, field_kind=field_cfg.kind)
        if fallback:
            ocr_candidates_by_field[field_name] = [
                (candidate.text, candidate.variant) for candidate in fallback
            ]
    return ocr_candidates_by_field


def _ocr_skip_detection(
    *,
    frame,
    profile: ProfileConfig,
    backend: OCRBackend,
) -> dict[str, list[tuple[str, str]]]:
    crops: dict[str, "object"] = {}
    for field_name, field_cfg in profile.fields.items():
        crops[field_name] = crop_box(frame, field_cfg.box)
    per_field = backend.recognize_field_crops(crops)
    return {
        field_name: [(candidate.text, candidate.variant) for candidate in candidates]
        for field_name, candidates in per_field.items()
    }


def _split_indices_into_chunks(indices: list[int], workers: int) -> list[list[int]]:
    if workers <= 1:
        return [list(indices)]
    chunks: list[list[int]] = [[] for _ in range(workers)]
    chunk_size = max(1, len(indices) // workers)
    for slot, start in enumerate(range(0, len(indices), chunk_size)):
        if slot >= workers:
            chunks[-1].extend(indices[start:])
            break
        chunks[slot] = indices[start : start + chunk_size]
    chunks = [chunk for chunk in chunks if chunk]
    return chunks


def _run_phase_b(
    *,
    profile: ProfileConfig,
    raw_frames: list[FrameRawOCR],
    metadata_fps: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    raw_rows: list[dict[str, object]] = []
    clean_rows: list[dict[str, object]] = []
    stage_states = {
        "stage1": StageState(),
        "stage2": StageState(),
    }
    met_observations: list[tuple[float, float]] = []

    parsing = profile.parsing
    for frame_data in raw_frames:
        per_field_obs: dict[str, OCRObservation] = {}
        ocr_candidates_by_field = {
            field_name: list(values)
            for field_name, values in frame_data.candidates_by_field.items()
        }
        sample_time_s = frame_data.sample_time_s

        met_choice = parse_met_candidates(ocr_candidates_by_field.get("met", []), parsing=parsing)
        mission_elapsed_time_s = met_choice.value if met_choice else None
        if mission_elapsed_time_s is not None and met_observations:
            previous_met = met_observations[-1][0]
            recent_offsets = [met - wall for met, wall in met_observations[-30:]]
            expected_met = sample_time_s + (sum(recent_offsets) / len(recent_offsets))
            if mission_elapsed_time_s < previous_met - 2 or abs(mission_elapsed_time_s - expected_met) > 5:
                mission_elapsed_time_s = None
                met_choice = None
        if mission_elapsed_time_s is not None:
            met_observations.append((mission_elapsed_time_s, sample_time_s))
        elif met_observations:
            offsets = [met - wall for met, wall in met_observations[-30:]]
            mission_elapsed_time_s = sample_time_s + (sum(offsets) / len(offsets))

        if met_choice is None:
            candidates = ocr_candidates_by_field.get("met", [])
            per_field_obs["met"] = OCRObservation(
                field_name="met",
                raw_text=candidates[0][0] if candidates else None,
                parse_status="missing",
                raw_unit=None,
                raw_value=None,
                normalized_si_value=mission_elapsed_time_s,
                variant=candidates[0][1] if candidates else None,
            )
        else:
            per_field_obs["met"] = OCRObservation(
                field_name="met",
                raw_text=met_choice.raw_text,
                parse_status="parsed",
                raw_unit="s",
                raw_value=met_choice.value,
                normalized_si_value=met_choice.value,
                variant=met_choice.variant,
            )

        for field_name, field_cfg in profile.fields.items():
            if field_cfg.kind == "met":
                continue
            stage_state = stage_states[field_cfg.stage]
            field_state = stage_state.fields.setdefault(field_name, FieldState())
            options: list[MeasurementOption] = []
            for raw_text, variant in ocr_candidates_by_field.get(field_name, []):
                options.extend(
                    parse_measurement_options(
                        raw_text, kind=field_cfg.kind, variant=variant, parsing=parsing
                    )
                )
            options = [
                option
                for option in options
                if _field_specific_option_is_valid(field_name, option, mission_elapsed_time_s)
            ]
            chosen = choose_best_measurement(
                options=options,
                kind=field_cfg.kind,
                previous_value_si=field_state.previous_value_si,
                previous_met_s=field_state.previous_met_s,
                current_met_s=mission_elapsed_time_s,
            )
            if chosen is None:
                candidates = ocr_candidates_by_field.get(field_name, [])
                per_field_obs[field_name] = OCRObservation(
                    field_name=field_name,
                    raw_text=candidates[0][0] if candidates else None,
                    parse_status="missing",
                    raw_unit=None,
                    raw_value=None,
                    normalized_si_value=None,
                    variant=candidates[0][1] if candidates else None,
                )
            else:
                per_field_obs[field_name] = OCRObservation(
                    field_name=field_name,
                    raw_text=chosen.raw_text,
                    parse_status="parsed",
                    raw_unit=chosen.unit,
                    raw_value=chosen.raw_value,
                    normalized_si_value=chosen.value_si,
                    variant=chosen.variant,
                )

        stage1_velocity = per_field_obs["stage1_velocity"].normalized_si_value
        stage1_altitude = per_field_obs["stage1_altitude"].normalized_si_value
        stage2_velocity = per_field_obs["stage2_velocity"].normalized_si_value
        stage2_altitude = per_field_obs["stage2_altitude"].normalized_si_value

        if stage2_velocity is not None or stage2_altitude is not None:
            if _stage2_measurement_is_active(stage2_velocity, stage2_altitude):
                stage_states["stage2"].activated = True
            elif not stage_states["stage2"].activated:
                stage2_velocity = None
                stage2_altitude = None

        if stage1_velocity is None and stage1_altitude is None:
            stage_states["stage1"].activated = False
        else:
            stage_states["stage1"].activated = True

        _update_field_state(stage_states["stage1"], "stage1_velocity", stage1_velocity, mission_elapsed_time_s)
        _update_field_state(stage_states["stage1"], "stage1_altitude", stage1_altitude, mission_elapsed_time_s)
        _update_field_state(stage_states["stage2"], "stage2_velocity", stage2_velocity, mission_elapsed_time_s)
        _update_field_state(stage_states["stage2"], "stage2_altitude", stage2_altitude, mission_elapsed_time_s)

        raw_row: dict[str, object] = {
            "frame_index": frame_data.frame_index,
            "sample_time_s": sample_time_s,
            "mission_elapsed_time_s": mission_elapsed_time_s,
        }
        for name, obs in per_field_obs.items():
            raw_row[f"{name}_raw_text"] = obs.raw_text
            raw_row[f"{name}_parse_status"] = obs.parse_status
            raw_row[f"{name}_raw_unit"] = obs.raw_unit
            raw_row[f"{name}_raw_value"] = obs.raw_value
            raw_row[f"{name}_si_value"] = obs.normalized_si_value
            raw_row[f"{name}_variant"] = obs.variant
        raw_rows.append(raw_row)

        clean_rows.append(
            ExtractionRow(
                frame_index=frame_data.frame_index,
                sample_time_s=sample_time_s,
                mission_elapsed_time_s=mission_elapsed_time_s,
                stage1_velocity_mps=stage1_velocity,
                stage1_altitude_m=stage1_altitude,
                stage2_velocity_mps=stage2_velocity,
                stage2_altitude_m=stage2_altitude,
            ).to_dict()
        )
    return raw_rows, clean_rows


def _build_strip_union_box(profile: ProfileConfig) -> Box:
    x0 = min(field.box.x0 for field in profile.fields.values())
    y0 = min(field.box.y0 for field in profile.fields.values())
    x1 = max(field.box.x1 for field in profile.fields.values())
    y1 = max(field.box.y1 for field in profile.fields.values())
    return Box(x0=x0, y0=y0, x1=x1, y1=y1)


def _assign_strip_detections(
    profile: ProfileConfig,
    frame,
    strip_box: Box,
    detections: list[OCRDetection],
) -> dict[str, list[tuple[str, str]]]:
    frame_height, frame_width = frame.shape[:2]
    strip_x0, strip_y0, _strip_x1, _strip_y1 = strip_box.as_int_xyxy(width=frame_width, height=frame_height)
    field_pixel_boxes = {
        field_name: field_cfg.box.as_int_xyxy(width=frame_width, height=frame_height)
        for field_name, field_cfg in profile.fields.items()
    }
    per_field_parts: dict[str, dict[str, list[tuple[int, int, str]]]] = {field_name: {} for field_name in profile.fields}

    for detection in detections:
        global_box = (
            detection.x0 + strip_x0,
            detection.y0 + strip_y0,
            detection.x1 + strip_x0,
            detection.y1 + strip_y0,
        )
        best_field = None
        best_overlap = 0
        for field_name, field_box in field_pixel_boxes.items():
            overlap = _intersection_area(global_box, field_box)
            if overlap > best_overlap:
                best_overlap = overlap
                best_field = field_name
        if best_field is None or best_overlap <= 0:
            continue
        per_field_parts[best_field].setdefault(detection.variant, []).append((global_box[1], global_box[0], detection.text))

    result: dict[str, list[tuple[str, str]]] = {field_name: [] for field_name in profile.fields}
    for field_name, variant_parts in per_field_parts.items():
        for variant, parts in variant_parts.items():
            ordered = sorted(parts)
            result[field_name].append((" ".join(text for _y, _x, text in ordered), variant))
    return result


def _intersection_area(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> int:
    x_left = max(box_a[0], box_b[0])
    y_top = max(box_a[1], box_b[1])
    x_right = min(box_a[2], box_b[2])
    y_bottom = min(box_a[3], box_b[3])
    if x_right <= x_left or y_bottom <= y_top:
        return 0
    return (x_right - x_left) * (y_bottom - y_top)


def _stage2_measurement_is_active(velocity_mps: float | None, altitude_m: float | None) -> bool:
    thresholds = (
        (velocity_mps is not None and velocity_mps > 44.704),
        (altitude_m is not None and altitude_m > 160.9344),
    )
    return any(thresholds)


def _field_specific_option_is_valid(
    field_name: str,
    option: MeasurementOption,
    mission_elapsed_time_s: float | None = None,
) -> bool:
    """Cheap physical-plausibility gate applied per option.

    The hard upper bound is the long-flight ceiling. The MET-aware bound is
    a kinematic ceiling: a chemical-rocket vehicle can't realistically be
    above ``0.5 * g * (3 * MET)^2`` in altitude, nor above ``3 * g * MET``
    in velocity. The factor 3 leaves comfortable headroom around real
    launch profiles while still rejecting cases where OCR misreads "FT" as
    "MI" right after liftoff and wraps a 50 ft reading into 90 km.
    """

    upper_bounds = {
        "stage1_velocity": 2500.0,
        "stage1_altitude": 150000.0,
        "stage2_velocity": 9000.0,
        "stage2_altitude": 600000.0,
    }
    upper_bound = upper_bounds.get(field_name)
    if upper_bound is None:
        return True
    if not (0.0 <= option.value_si <= upper_bound):
        return False
    if (
        mission_elapsed_time_s is None
        or not isinstance(mission_elapsed_time_s, (int, float))
        or mission_elapsed_time_s <= 0.0
    ):
        return True
    kind = field_name.rsplit("_", 1)[-1]
    met_bound = _met_kinematic_bound(kind=kind, mission_elapsed_time_s=float(mission_elapsed_time_s))
    if met_bound is None:
        return True
    return option.value_si <= met_bound


def _met_kinematic_bound(*, kind: str, mission_elapsed_time_s: float) -> float | None:
    """Return a generous physical upper bound at the given MET, or None.

    Only applied during the first minute after liftoff, where OCR
    confusion between FT and MI on a 3-digit reading can otherwise mint a
    value 5000× larger than reality. Past 60 s the static field-specific
    upper bounds already box in any real launch profile and this gate
    adds no value.
    """

    if mission_elapsed_time_s > 60.0:
        return None
    g0 = 9.80665
    effective_acceleration_g = 5.0
    if kind == "altitude":
        return 0.5 * effective_acceleration_g * g0 * mission_elapsed_time_s * mission_elapsed_time_s
    if kind == "velocity":
        return effective_acceleration_g * g0 * mission_elapsed_time_s
    return None


def _update_field_state(stage_state: StageState, field_name: str, value_si: float | None, mission_elapsed_time_s: float | None) -> None:
    if value_si is None or mission_elapsed_time_s is None:
        return
    field_state = stage_state.fields.setdefault(field_name, FieldState())
    field_state.previous_value_si = value_si
    field_state.previous_met_s = mission_elapsed_time_s
