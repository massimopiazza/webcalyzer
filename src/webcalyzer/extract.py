from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from webcalyzer.config import save_profile
from webcalyzer.models import Box, ExtractionRow, OCRObservation, ProfileConfig
from webcalyzer.ocr import OCRDetection, OCRRunner
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


def extract_telemetry(
    video_path: str | Path,
    profile: ProfileConfig,
    output_dir: str | Path,
    sample_fps: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    metadata = get_video_metadata(video_path)
    effective_fps = float(sample_fps or profile.default_sample_fps)
    sample_indices = build_sample_indices(metadata=metadata, target_fps=effective_fps)
    frames = iterate_frames(video_path, sample_indices)
    strip_box = _build_strip_union_box(profile)

    ocr = OCRRunner()
    raw_rows: list[dict[str, object]] = []
    clean_rows: list[dict[str, object]] = []
    stage_states = {
        "stage1": StageState(),
        "stage2": StageState(),
    }
    met_observations: list[tuple[float, float]] = []

    for frame_index, frame in frames:
        sample_number = len(raw_rows) + 1
        sample_time_s = frame_index / metadata.fps
        per_field_obs: dict[str, OCRObservation] = {}

        strip_crop = crop_box(frame, strip_box)
        strip_detections = ocr.extract_detections(strip_crop, mode="strip")
        ocr_candidates_by_field = _assign_strip_detections(
            profile=profile,
            frame=frame,
            strip_box=strip_box,
            detections=strip_detections,
        )

        met_choice = parse_met_candidates(ocr_candidates_by_field.get("met", []))
        if met_choice is None:
            met_crop = crop_box(frame, profile.fields["met"].box)
            met_fallback = ocr.extract_text(met_crop, field_kind="met")
            if met_fallback:
                ocr_candidates_by_field["met"] = [(candidate.text, candidate.variant) for candidate in met_fallback]
                met_choice = parse_met_candidates(ocr_candidates_by_field["met"])
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
                options.extend(parse_measurement_options(raw_text, kind=field_cfg.kind, variant=variant))
            options = [option for option in options if _field_specific_option_is_valid(field_name, option)]
            if not options:
                crop = crop_box(frame, field_cfg.box)
                field_fallback = ocr.extract_text(crop, field_kind=field_cfg.kind)
                if field_fallback:
                    ocr_candidates_by_field[field_name] = [(candidate.text, candidate.variant) for candidate in field_fallback]
                    for candidate in field_fallback:
                        options.extend(parse_measurement_options(candidate.text, kind=field_cfg.kind, variant=candidate.variant))
                    options = [option for option in options if _field_specific_option_is_valid(field_name, option)]

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
            "frame_index": frame_index,
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
                frame_index=frame_index,
                sample_time_s=sample_time_s,
                mission_elapsed_time_s=mission_elapsed_time_s,
                stage1_velocity_mps=stage1_velocity,
                stage1_altitude_m=stage1_altitude,
                stage2_velocity_mps=stage2_velocity,
                stage2_altitude_m=stage2_altitude,
            ).to_dict()
        )

        if sample_number % 25 == 0 or sample_number == len(frames):
            print(
                f"[webcalyzer] processed {sample_number}/{len(frames)} samples "
                f"(video t={sample_time_s:.1f}s, met={mission_elapsed_time_s if mission_elapsed_time_s is not None else 'n/a'})"
            )

    raw_df = pd.DataFrame(raw_rows)
    clean_df = pd.DataFrame(clean_rows)
    raw_df.to_csv(output_path / "telemetry_raw.csv", index=False)
    clean_df.to_csv(output_path / "telemetry_clean.csv", index=False)
    save_profile(profile, output_path / "config_resolved.yaml")
    (output_path / "run_metadata.json").write_text(
        json.dumps(
            {
                "video": metadata.to_dict(),
                "sample_fps_requested": effective_fps,
                "sample_count": len(sample_indices),
                "profile_name": profile.profile_name,
            },
            indent=2,
        )
    )
    return raw_df, clean_df


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
            int(round(detection.x0 / 2)) + strip_x0,
            int(round(detection.y0 / 2)) + strip_y0,
            int(round(detection.x1 / 2)) + strip_x0,
            int(round(detection.y1 / 2)) + strip_y0,
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


def _field_specific_option_is_valid(field_name: str, option: MeasurementOption) -> bool:
    upper_bounds = {
        "stage1_velocity": 2500.0,
        "stage1_altitude": 150000.0,
        "stage2_velocity": 9000.0,
        "stage2_altitude": 600000.0,
    }
    upper_bound = upper_bounds.get(field_name)
    if upper_bound is None:
        return True
    return 0.0 <= option.value_si <= upper_bound


def _update_field_state(stage_state: StageState, field_name: str, value_si: float | None, mission_elapsed_time_s: float | None) -> None:
    if value_si is None or mission_elapsed_time_s is None:
        return
    field_state = stage_state.fields.setdefault(field_name, FieldState())
    field_state.previous_value_si = value_si
    field_state.previous_met_s = mission_elapsed_time_s
