from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from webcalyzer.models import HardcodedRawDataPoint


BASE_COLUMNS = ["frame_index", "sample_time_s", "mission_elapsed_time_s"]
TELEMETRY_FIELDS = {
    "stage1_velocity": ("velocity", "m/s"),
    "stage1_altitude": ("altitude", "m"),
    "stage2_velocity": ("velocity", "m/s"),
    "stage2_altitude": ("altitude", "m"),
}
OBSERVATION_SUFFIXES = ["raw_text", "parse_status", "raw_unit", "raw_value", "si_value", "variant"]
TEXT_SUFFIXES = {"raw_text", "parse_status", "raw_unit", "variant"}


def apply_hardcoded_raw_data_points(
    raw_df: pd.DataFrame,
    points: Iterable[HardcodedRawDataPoint] | None,
) -> pd.DataFrame:
    hardcoded_points = sorted(points or [], key=lambda point: point.mission_elapsed_time_s)
    df = raw_df.copy()
    if not hardcoded_points:
        return df

    _ensure_raw_columns(df)
    for point in hardcoded_points:
        row_index = _find_existing_row_index(df, point.mission_elapsed_time_s)
        if row_index is None:
            row = _empty_raw_row(df, point.mission_elapsed_time_s)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            row_index = int(df.index[-1])
        else:
            df.at[row_index, "mission_elapsed_time_s"] = point.mission_elapsed_time_s

        _write_met_observation(df, row_index, point.mission_elapsed_time_s)
        for field_name, value in point.field_values().items():
            _write_telemetry_observation(df, row_index, field_name, value)

    return _sort_raw_dataframe(df)


def _ensure_raw_columns(df: pd.DataFrame) -> None:
    for column in BASE_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan
    for field_name in ("met", *TELEMETRY_FIELDS.keys()):
        for suffix in OBSERVATION_SUFFIXES:
            column = f"{field_name}_{suffix}"
            if column not in df.columns:
                if suffix in TEXT_SUFFIXES:
                    df[column] = pd.Series([pd.NA] * len(df), dtype="object")
                else:
                    df[column] = np.nan
            elif suffix in TEXT_SUFFIXES:
                df[column] = df[column].astype("object")


def _find_existing_row_index(df: pd.DataFrame, mission_elapsed_time_s: float) -> int | None:
    met = pd.to_numeric(df["mission_elapsed_time_s"], errors="coerce").to_numpy(dtype=float)
    matches = np.where(np.isclose(met, mission_elapsed_time_s, rtol=0.0, atol=1e-6, equal_nan=False))[0]
    if matches.size == 0:
        return None
    return int(df.index[int(matches[0])])


def _empty_raw_row(df: pd.DataFrame, mission_elapsed_time_s: float) -> dict[str, object]:
    row = {column: np.nan for column in df.columns}
    row["mission_elapsed_time_s"] = mission_elapsed_time_s
    row["sample_time_s"] = _interpolate_column_for_met(
        df=df,
        column="sample_time_s",
        mission_elapsed_time_s=mission_elapsed_time_s,
        fallback=mission_elapsed_time_s,
    )
    frame_index = _interpolate_column_for_met(
        df=df,
        column="frame_index",
        mission_elapsed_time_s=mission_elapsed_time_s,
        fallback=-1.0,
    )
    row["frame_index"] = int(round(frame_index)) if np.isfinite(frame_index) else -1
    return row


def _interpolate_column_for_met(
    df: pd.DataFrame,
    column: str,
    mission_elapsed_time_s: float,
    fallback: float,
) -> float:
    if column not in df.columns:
        return fallback
    pairs = pd.DataFrame(
        {
            "mission_elapsed_time_s": pd.to_numeric(df["mission_elapsed_time_s"], errors="coerce"),
            column: pd.to_numeric(df[column], errors="coerce"),
        }
    ).dropna()
    if pairs.empty:
        return fallback
    grouped = pairs.groupby("mission_elapsed_time_s", as_index=True)[column].mean().sort_index()
    if grouped.size == 1:
        return float(grouped.iloc[0])
    return float(np.interp(mission_elapsed_time_s, grouped.index.to_numpy(dtype=float), grouped.to_numpy(dtype=float)))


def _write_met_observation(df: pd.DataFrame, row_index: int, mission_elapsed_time_s: float) -> None:
    df.at[row_index, "met_raw_text"] = _format_met_text(mission_elapsed_time_s)
    df.at[row_index, "met_parse_status"] = "hardcoded"
    df.at[row_index, "met_raw_unit"] = "s"
    df.at[row_index, "met_raw_value"] = mission_elapsed_time_s
    df.at[row_index, "met_si_value"] = mission_elapsed_time_s
    df.at[row_index, "met_variant"] = "hardcoded"


def _write_telemetry_observation(df: pd.DataFrame, row_index: int, field_name: str, value: float) -> None:
    _kind, unit = TELEMETRY_FIELDS[field_name]
    df.at[row_index, f"{field_name}_raw_text"] = f"{value:g} {unit}"
    df.at[row_index, f"{field_name}_parse_status"] = "hardcoded"
    df.at[row_index, f"{field_name}_raw_unit"] = unit
    df.at[row_index, f"{field_name}_raw_value"] = float(value)
    df.at[row_index, f"{field_name}_si_value"] = float(value)
    df.at[row_index, f"{field_name}_variant"] = "hardcoded"


def _format_met_text(mission_elapsed_time_s: float) -> str:
    rounded = int(round(mission_elapsed_time_s))
    if abs(mission_elapsed_time_s - rounded) > 1e-6:
        return f"{mission_elapsed_time_s:g} s"
    sign = "-" if rounded < 0 else "+"
    absolute = abs(rounded)
    hours, remainder = divmod(absolute, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"T{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"


def _sort_raw_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    sort_df = df.copy()
    sort_df["_sort_met"] = pd.to_numeric(sort_df["mission_elapsed_time_s"], errors="coerce")
    sort_df["_sort_sample"] = pd.to_numeric(sort_df["sample_time_s"], errors="coerce")
    sort_df = sort_df.sort_values(
        by=["_sort_met", "_sort_sample"],
        kind="mergesort",
        na_position="last",
    )
    sort_df = sort_df.drop(columns=["_sort_met", "_sort_sample"]).reset_index(drop=True)
    return sort_df[_ordered_columns(sort_df)]


def _ordered_columns(df: pd.DataFrame) -> list[str]:
    base = [column for column in BASE_COLUMNS if column in df.columns]
    raw_columns: list[str] = []
    for field_name in ("met", *TELEMETRY_FIELDS.keys()):
        raw_columns.extend(
            column
            for suffix in OBSERVATION_SUFFIXES
            if (column := f"{field_name}_{suffix}") in df.columns
        )
    rest = [column for column in df.columns if column not in {*base, *raw_columns}]
    return base + raw_columns + rest
