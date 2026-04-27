from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from webcalyzer.config import load_profile
from webcalyzer.extract import _build_strip_union_box, _field_specific_option_is_valid
from webcalyzer.models import Box, ParsingProfile, ProfileConfig
from webcalyzer.ocr import RescueOCR
from webcalyzer.ocr_factory import OCRBackendOptions, make_backend
from webcalyzer.sanitize import (
    MeasurementOption,
    choose_best_measurement,
    parse_measurement_options,
    parse_met,
)
from webcalyzer.video import open_capture


MEASUREMENT_FIELDS: list[tuple[str, str]] = [
    ("stage1_velocity", "velocity"),
    ("stage1_altitude", "altitude"),
    ("stage2_velocity", "velocity"),
    ("stage2_altitude", "altitude"),
]

TIERS = ("fast", "medium", "full")
OFFSET_SCHEDULE: list[tuple[str, list[int]]] = [
    ("fast", [0]),
    ("medium", [0]),
    ("full", [0]),
    ("fast", [-3, 3, -6, 6]),
    ("medium", [-12, 12, -24, 24]),
]


@dataclass(slots=True)
class RescueTarget:
    row_index: int
    frame_index: int
    mission_elapsed_time_s: float | None
    field_name: str
    kind: str


def _collect_targets(raw_df: pd.DataFrame) -> list[RescueTarget]:
    targets: list[RescueTarget] = []
    for row_index, row in raw_df.iterrows():
        frame_index = int(row["frame_index"])
        met = row.get("mission_elapsed_time_s")
        met_val = float(met) if pd.notna(met) else None
        for field_name, kind in MEASUREMENT_FIELDS:
            status = row.get(f"{field_name}_parse_status")
            if status == "missing":
                targets.append(
                    RescueTarget(
                        row_index=row_index,
                        frame_index=frame_index,
                        mission_elapsed_time_s=met_val,
                        field_name=field_name,
                        kind=kind,
                    )
                )
        met_status = row.get("met_parse_status")
        if met_status == "missing":
            targets.append(
                RescueTarget(
                    row_index=row_index,
                    frame_index=frame_index,
                    mission_elapsed_time_s=met_val,
                    field_name="met",
                    kind="met",
                )
            )
    return targets


_STRIP_KEYWORDS = (
    "MPH",
    "VELOCITY",
    "ALTITUDE",
    "STAGE",
    "GLENN",
    "FT",
    "MI",
    "T+",
    "T-",
)


def _strip_text_looks_like_telemetry(text: str) -> bool:
    if not text:
        return False
    upper = text.upper()
    if any(keyword in upper for keyword in _STRIP_KEYWORDS):
        return True
    digit_count = sum(1 for ch in upper if ch.isdigit())
    return digit_count >= 4


def _crop_from_frame(frame: np.ndarray, box: Box) -> np.ndarray:
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = box.as_int_xyxy(width=width, height=height)
    return frame[y0:y1, x0:x1].copy()


def _rescue_option_is_acceptable(option: MeasurementOption) -> bool:
    """Strict gate for rescue candidates.

    The genuine overlay is always "XXX,XXX MPH" / "XXX,XXX FT" / "XX MI" with
    explicit unit labels. To avoid fabricating values from pre-strip noise we
    require an explicit unit label and (separator-bearing token OR a 6+ digit
    token like "003998" that lost its separator under heavy preprocessing).
    """
    token = option.raw_token
    if not option.explicit_unit:
        return False
    has_separator = any(separator in token for separator in ",.:")
    if has_separator and len(token) >= 5:
        return True
    if not has_separator and len(token) >= 6:
        return True
    return False


def _parse_for_field(
    field_name: str,
    kind: str,
    candidates: list[tuple[str, str]],
    previous_value_si: float | None,
    previous_met_s: float | None,
    current_met_s: float | None,
    parsing: ParsingProfile | None = None,
) -> MeasurementOption | None:
    options: list[MeasurementOption] = []
    for text, variant in candidates:
        options.extend(parse_measurement_options(text, kind=kind, variant=variant, parsing=parsing))
    options = [
        opt
        for opt in options
        if _field_specific_option_is_valid(field_name, opt, current_met_s)
    ]
    options = [opt for opt in options if _rescue_option_is_acceptable(opt)]
    if not options:
        return None
    return choose_best_measurement(
        options=options,
        kind=kind,
        previous_value_si=previous_value_si,
        previous_met_s=previous_met_s,
        current_met_s=current_met_s,
    )


def _parse_met_candidates(
    candidates: list[tuple[str, str]],
    parsing: ParsingProfile | None = None,
) -> tuple[float | None, str | None, str | None]:
    best_value: float | None = None
    best_text: str | None = None
    best_variant: str | None = None
    best_score = -1.0
    for text, variant in candidates:
        parsed = parse_met(text, parsing=parsing)
        if parsed is None:
            continue
        upper = text.upper()
        score = 2.0 if "T" in upper else 1.0
        if best_value is None or score > best_score:
            best_value = parsed
            best_text = text
            best_variant = variant
            best_score = score
    return best_value, best_text, best_variant


def _previous_value(
    raw_df: pd.DataFrame, row_index: int, field_name: str
) -> tuple[float | None, float | None]:
    start = max(0, row_index - 30)
    window = raw_df.iloc[start:row_index]
    for _, prev_row in window[::-1].iterrows():
        candidate_val = prev_row.get(f"{field_name}_si_value")
        candidate_met = prev_row.get("mission_elapsed_time_s")
        if pd.notna(candidate_val) and pd.notna(candidate_met):
            return float(candidate_val), float(candidate_met)
    return None, None


def rescue_raw_dataframe(
    raw_df: pd.DataFrame,
    video_path: str | Path,
    profile: ProfileConfig,
    log_prefix: str = "[rescue]",
    backend_options: OCRBackendOptions | None = None,
) -> pd.DataFrame:
    options = backend_options or OCRBackendOptions()
    if profile.parsing is not None and not options.custom_words:
        from dataclasses import replace as dataclass_replace

        options = dataclass_replace(options, custom_words=tuple(profile.parsing.custom_words_list()))
    backend = make_backend(options)
    rescue = RescueOCR(backend)
    raw_df = raw_df.copy()
    parsing = profile.parsing

    capture = open_capture(video_path)
    frame_count = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    strip_box = _build_strip_union_box(profile)

    try:
        targets = _collect_targets(raw_df)
        grouped: dict[int, list[RescueTarget]] = {}
        for target in targets:
            grouped.setdefault(target.row_index, []).append(target)

        ordered_rows = sorted(grouped.keys())
        total = len(ordered_rows)
        rescued_count = 0

        for processed, row_index in enumerate(ordered_rows, start=1):
            row_targets = grouped[row_index]
            primary_frame_index = int(raw_df.iloc[row_index]["frame_index"])
            current_met = raw_df.iloc[row_index]["mission_elapsed_time_s"]
            current_met_val = float(current_met) if pd.notna(current_met) else None

            remaining: dict[str, RescueTarget] = {t.field_name: t for t in row_targets}
            frame_cache: dict[int, np.ndarray] = {}
            candidates_cache: dict[tuple[int, str, str], list[tuple[str, str]]] = {}

            # Cheap presence check: if no field on the primary frame returns
            # anything from the fast OCR, the strip is almost certainly absent
            # and further offsets/tiers would just produce noise.
            row_data = raw_df.iloc[row_index]
            all_fields_have_no_text = all(
                pd.isna(row_data.get(f"{f}_raw_text"))
                for f, _ in MEASUREMENT_FIELDS
            ) and pd.isna(row_data.get("met_raw_text"))

            strip_likely_absent = all_fields_have_no_text

            if strip_likely_absent:
                capture.set(cv2.CAP_PROP_POS_FRAMES, primary_frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    if processed % 10 == 0 or processed == total:
                        print(
                            f"{log_prefix} rescued {rescued_count} fields across {processed}/{total} target rows",
                            flush=True,
                        )
                    continue
                frame_cache[primary_frame_index] = frame
                strip_crop = _crop_from_frame(frame, strip_box)
                strip_candidates = rescue.extract(strip_crop, tier="fast")
                if not any(_strip_text_looks_like_telemetry(c.text) for c in strip_candidates):
                    if processed % 10 == 0 or processed == total:
                        print(
                            f"{log_prefix} rescued {rescued_count} fields across {processed}/{total} target rows",
                            flush=True,
                        )
                    continue

            field_absent_at_primary: set[str] = set()

            for tier, offsets in OFFSET_SCHEDULE:
                if not remaining:
                    break
                for offset in offsets:
                    if not remaining:
                        break
                    frame_idx = primary_frame_index + offset
                    if frame_idx < 0 or frame_idx >= frame_count:
                        continue
                    frame = frame_cache.get(frame_idx)
                    if frame is None:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                        ok, frame = capture.read()
                        if not ok or frame is None:
                            continue
                        frame_cache[frame_idx] = frame

                    for field_name in list(remaining):
                        # If the fast pass at the primary frame found no
                        # candidates whatsoever for this field, the slot is
                        # blank in the overlay and further tiers/offsets are
                        # pure noise.
                        if field_name in field_absent_at_primary:
                            continue
                        target = remaining[field_name]
                        field_cfg = profile.fields[field_name]
                        cache_key = (frame_idx, field_name, tier)
                        if cache_key in candidates_cache:
                            candidates = candidates_cache[cache_key]
                        else:
                            crop = _crop_from_frame(frame, field_cfg.box)
                            candidates = [
                                (cand.text, cand.variant)
                                for cand in rescue.extract(crop, tier=tier)
                            ]
                            candidates_cache[cache_key] = candidates
                        if tier == "fast" and offset == 0 and not candidates:
                            field_absent_at_primary.add(field_name)
                        if not candidates:
                            continue

                        if target.kind == "met":
                            value, text, variant = _parse_met_candidates(candidates, parsing=parsing)
                            if value is None:
                                continue
                            if current_met_val is not None and abs(value - current_met_val) > 5:
                                continue
                            raw_df.at[row_index, "met_raw_text"] = text
                            raw_df.at[row_index, "met_parse_status"] = "parsed"
                            raw_df.at[row_index, "met_raw_unit"] = "s"
                            raw_df.at[row_index, "met_raw_value"] = value
                            raw_df.at[row_index, "met_si_value"] = value
                            raw_df.at[row_index, "met_variant"] = variant
                            if pd.isna(raw_df.at[row_index, "mission_elapsed_time_s"]):
                                raw_df.at[row_index, "mission_elapsed_time_s"] = value
                                current_met_val = value
                            rescued_count += 1
                            del remaining[field_name]
                            continue

                        prev_val, prev_met = _previous_value(raw_df, row_index, field_name)
                        chosen = _parse_for_field(
                            field_name=field_name,
                            kind=target.kind,
                            candidates=candidates,
                            previous_value_si=prev_val,
                            previous_met_s=prev_met,
                            current_met_s=current_met_val,
                            parsing=parsing,
                        )
                        if chosen is None:
                            continue
                        raw_df.at[row_index, f"{field_name}_raw_text"] = chosen.raw_text
                        raw_df.at[row_index, f"{field_name}_parse_status"] = "parsed"
                        raw_df.at[row_index, f"{field_name}_raw_unit"] = chosen.unit
                        raw_df.at[row_index, f"{field_name}_raw_value"] = chosen.raw_value
                        raw_df.at[row_index, f"{field_name}_si_value"] = chosen.value_si
                        raw_df.at[row_index, f"{field_name}_variant"] = chosen.variant
                        rescued_count += 1
                        del remaining[field_name]

            if processed % 10 == 0 or processed == total:
                print(
                    f"{log_prefix} rescued {rescued_count} fields across {processed}/{total} target rows",
                    flush=True,
                )
    finally:
        capture.release()

    return raw_df


def rescue_output_dir(
    output_dir: str | Path,
    video_path: str | Path,
    profile: ProfileConfig | None = None,
    backend_options: OCRBackendOptions | None = None,
) -> pd.DataFrame:
    output_path = Path(output_dir)
    raw_df = pd.read_csv(output_path / "telemetry_raw.csv")
    if profile is None:
        profile = load_profile(output_path / "config_resolved.yaml")
    rescued = rescue_raw_dataframe(
        raw_df=raw_df,
        video_path=video_path,
        profile=profile,
        backend_options=backend_options,
    )
    rescued.to_csv(output_path / "telemetry_raw.csv", index=False)
    return rescued
