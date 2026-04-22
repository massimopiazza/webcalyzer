from __future__ import annotations

from pathlib import Path

import pandas as pd

from webcalyzer.extract import _field_specific_option_is_valid, _stage2_measurement_is_active
from webcalyzer.sanitize import choose_best_measurement, parse_measurement_options


def rebuild_clean_from_raw(raw_df: pd.DataFrame) -> pd.DataFrame:
    state = {
        "stage1_velocity": {"prev_val": None, "prev_met": None},
        "stage1_altitude": {"prev_val": None, "prev_met": None},
        "stage2_velocity": {"prev_val": None, "prev_met": None},
        "stage2_altitude": {"prev_val": None, "prev_met": None},
    }
    stage2_activated = False
    rows: list[dict[str, object]] = []

    for _, row in raw_df.iterrows():
        mission_elapsed_time_s = row["mission_elapsed_time_s"]
        parsed: dict[str, float | None] = {}
        for field_name, kind in [
            ("stage1_velocity", "velocity"),
            ("stage1_altitude", "altitude"),
            ("stage2_velocity", "velocity"),
            ("stage2_altitude", "altitude"),
        ]:
            raw_text = row.get(f"{field_name}_raw_text")
            if pd.isna(raw_text):
                parsed[field_name] = None
                continue
            options = parse_measurement_options(str(raw_text), kind=kind, variant="raw")
            options = [option for option in options if _field_specific_option_is_valid(field_name, option)]
            chosen = choose_best_measurement(
                options=options,
                kind=kind,
                previous_value_si=state[field_name]["prev_val"],
                previous_met_s=state[field_name]["prev_met"],
                current_met_s=mission_elapsed_time_s,
            )
            value = chosen.value_si if chosen else None
            parsed[field_name] = value
            if value is not None and not pd.isna(mission_elapsed_time_s):
                state[field_name]["prev_val"] = value
                state[field_name]["prev_met"] = mission_elapsed_time_s

        stage2_velocity = parsed["stage2_velocity"]
        stage2_altitude = parsed["stage2_altitude"]
        if stage2_velocity is not None or stage2_altitude is not None:
            if _stage2_measurement_is_active(stage2_velocity, stage2_altitude):
                stage2_activated = True
            elif not stage2_activated:
                stage2_velocity = None
                stage2_altitude = None

        rows.append(
            {
                "frame_index": row["frame_index"],
                "sample_time_s": row["sample_time_s"],
                "mission_elapsed_time_s": mission_elapsed_time_s,
                "stage1_velocity_mps": parsed["stage1_velocity"],
                "stage1_altitude_m": parsed["stage1_altitude"],
                "stage2_velocity_mps": stage2_velocity,
                "stage2_altitude_m": stage2_altitude,
            }
        )
    return pd.DataFrame(rows)


def rebuild_clean_in_output_dir(output_dir: str | Path) -> pd.DataFrame:
    output_path = Path(output_dir)
    raw_df = pd.read_csv(output_path / "telemetry_raw.csv")
    clean_df = rebuild_clean_from_raw(raw_df)
    clean_df.to_csv(output_path / "telemetry_clean.csv", index=False)
    return clean_df
