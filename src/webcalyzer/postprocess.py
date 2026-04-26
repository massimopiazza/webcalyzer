from __future__ import annotations

from pathlib import Path

import numpy as np
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
    _empty_rejected_frame(clean_df).dropna(how="all").to_csv(output_path / "telemetry_rejected.csv", index=False)
    return clean_df


STAGE_COLUMNS = {
    "stage1": ("stage1_velocity_mps", "stage1_altitude_m"),
    "stage2": ("stage2_velocity_mps", "stage2_altitude_m"),
}

FIELD_COLUMNS = [
    ("stage1_velocity_mps", "velocity"),
    ("stage1_altitude_m", "altitude"),
    ("stage2_velocity_mps", "velocity"),
    ("stage2_altitude_m", "altitude"),
]


def apply_mahalanobis_outlier_rejection(
    clean_df: pd.DataFrame,
    chi2_threshold: float = 36.0,
    window_s: float = 40.0,
    min_neighbors: int = 6,
    min_side_neighbors: int = 2,
    min_variance: tuple[float, float] = (144.0, 22500.0),
    passes: int = 5,
) -> pd.DataFrame:
    cleaned, _rejected = apply_mahalanobis_outlier_rejection_with_rejected(
        clean_df=clean_df,
        chi2_threshold=chi2_threshold,
        window_s=window_s,
        min_neighbors=min_neighbors,
        min_side_neighbors=min_side_neighbors,
        min_variance=min_variance,
        passes=passes,
    )
    return cleaned


def apply_mahalanobis_outlier_rejection_with_rejected(
    clean_df: pd.DataFrame,
    chi2_threshold: float = 36.0,
    window_s: float = 40.0,
    min_neighbors: int = 6,
    min_side_neighbors: int = 2,
    min_variance: tuple[float, float] = (144.0, 22500.0),
    passes: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject outliers with a per-field Mahalanobis distance on local residuals.

    OCR failures in velocity and altitude are independent, so each telemetry
    column is scored separately. For each sample we fit a local quadratic to the
    same column in the surrounding window, excluding the sample itself. The
    squared residual divided by robust local variance is the 1-D Mahalanobis
    distance. Rejection is repeated because removing one bad point can reveal a
    neighboring one.
    """
    df = clean_df.copy()
    rejected_df = _empty_rejected_frame(clean_df)
    met = df["mission_elapsed_time_s"].to_numpy(dtype=float)

    min_variance_by_kind = {
        "velocity": float(min_variance[0]),
        "altitude": float(min_variance[1]),
    }
    for column, kind in FIELD_COLUMNS:
        if column not in df.columns:
            continue
        _reject_column_outliers(
            df=df,
            rejected_df=rejected_df,
            met=met,
            column=column,
            chi2_threshold=chi2_threshold,
            window_s=window_s,
            min_neighbors=min_neighbors,
            min_side_neighbors=min_side_neighbors,
            min_variance=min_variance_by_kind[kind],
            passes=passes,
        )
    return df, rejected_df


def _reject_column_outliers(
    df: pd.DataFrame,
    rejected_df: pd.DataFrame,
    met: np.ndarray,
    column: str,
    chi2_threshold: float,
    window_s: float,
    min_neighbors: int,
    min_side_neighbors: int,
    min_variance: float,
    passes: int,
) -> None:
    row_positions = np.arange(len(df))
    for _ in range(passes):
        values = df[column].to_numpy(dtype=float)
        mask = np.isfinite(values) & np.isfinite(met)
        indices = np.where(mask)[0]
        if indices.size < min_neighbors + 1:
            return

        flagged: list[int] = []
        for idx in indices:
            t0 = met[idx]
            neighbor_mask = mask & (np.abs(met - t0) <= window_s) & (row_positions != idx)
            neighbor_idx = np.where(neighbor_mask)[0]
            if neighbor_idx.size < min_neighbors:
                continue
            left = int(np.sum(met[neighbor_idx] < t0))
            right = int(np.sum(met[neighbor_idx] > t0))
            if left < min_side_neighbors or right < min_side_neighbors:
                continue

            t_neighbors = met[neighbor_idx]
            y_neighbors = values[neighbor_idx]
            try:
                degree = 2 if neighbor_idx.size >= 5 else 1
                coefficients = np.polyfit(t_neighbors, y_neighbors, degree)
            except (np.linalg.LinAlgError, ValueError):
                continue

            predicted_neighbors = np.polyval(coefficients, t_neighbors)
            residuals = y_neighbors - predicted_neighbors
            variance = _robust_residual_variance(residuals, min_variance=min_variance)
            predicted_sample = float(np.polyval(coefficients, t0))
            delta = values[idx] - predicted_sample
            md2 = float((delta * delta) / variance)
            if md2 > chi2_threshold:
                flagged.append(idx)

        if not flagged:
            return

        for idx in flagged:
            row_label = df.index[idx]
            rejected_df.at[row_label, "frame_index"] = df.at[row_label, "frame_index"]
            rejected_df.at[row_label, "sample_time_s"] = df.at[row_label, "sample_time_s"]
            rejected_df.at[row_label, "mission_elapsed_time_s"] = df.at[row_label, "mission_elapsed_time_s"]
            rejected_df.at[row_label, column] = df.at[row_label, column]
            df.at[row_label, column] = np.nan


def _robust_residual_variance(residuals: np.ndarray, min_variance: float) -> float:
    residuals = residuals[np.isfinite(residuals)]
    if residuals.size == 0:
        return min_variance
    median = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - median)))
    robust_sigma = 1.4826 * mad
    if not np.isfinite(robust_sigma) or robust_sigma <= 0.0:
        robust_sigma = float(np.std(residuals, ddof=1)) if residuals.size > 1 else 0.0
    variance = robust_sigma * robust_sigma
    return max(float(variance), float(min_variance))


def _empty_rejected_frame(clean_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "frame_index",
        "sample_time_s",
        "mission_elapsed_time_s",
        "stage1_velocity_mps",
        "stage1_altitude_m",
        "stage2_velocity_mps",
        "stage2_altitude_m",
    ]
    available_columns = [column for column in columns if column in clean_df.columns]
    return pd.DataFrame(index=clean_df.index, columns=available_columns, dtype="float64")


def apply_outlier_rejection_in_output_dir(
    output_dir: str | Path,
    chi2_threshold: float = 36.0,
    window_s: float = 40.0,
) -> pd.DataFrame:
    output_path = Path(output_dir)
    raw_path = output_path / "telemetry_raw.csv"
    if raw_path.exists():
        clean_df = rebuild_clean_from_raw(pd.read_csv(raw_path))
    else:
        clean_df = pd.read_csv(output_path / "telemetry_clean.csv")
    cleaned, rejected = apply_mahalanobis_outlier_rejection_with_rejected(
        clean_df, chi2_threshold=chi2_threshold, window_s=window_s
    )
    cleaned.to_csv(output_path / "telemetry_clean.csv", index=False)
    rejected.dropna(how="all", subset=list(STAGE_COLUMNS["stage1"] + STAGE_COLUMNS["stage2"])).to_csv(
        output_path / "telemetry_rejected.csv",
        index=False,
    )
    return cleaned
