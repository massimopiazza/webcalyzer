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
    return clean_df


STAGE_COLUMNS = {
    "stage1": ("stage1_velocity_mps", "stage1_altitude_m"),
    "stage2": ("stage2_velocity_mps", "stage2_altitude_m"),
}


def apply_mahalanobis_outlier_rejection(
    clean_df: pd.DataFrame,
    chi2_threshold: float = 13.82,
    window_s: float = 40.0,
    min_neighbors: int = 6,
    min_side_neighbors: int = 2,
    min_variance: tuple[float, float] = (25.0, 2500.0),
    passes: int = 2,
) -> pd.DataFrame:
    """Reject outliers using Mahalanobis distance in (velocity, altitude) per stage.

    For each sample we fit a local quadratic to the surrounding window (excluding
    the sample itself), compute residuals and their covariance, and flag any
    sample whose squared Mahalanobis distance exceeds the chi^2 threshold
    (99.9% for 2 DoF defaults to 13.82). The rejection is repeated ``passes``
    times because removing one outlier can reveal another.
    """
    df = clean_df.copy()
    met = df["mission_elapsed_time_s"].to_numpy(dtype=float)

    for _ in range(passes):
        rejected_any = False
        for stage, (v_col, h_col) in STAGE_COLUMNS.items():
            v = df[v_col].to_numpy(dtype=float)
            h = df[h_col].to_numpy(dtype=float)
            mask = np.isfinite(v) & np.isfinite(h) & np.isfinite(met)
            indices = np.where(mask)[0]
            if indices.size < min_neighbors + 1:
                continue

            flagged: list[int] = []
            for idx in indices:
                t0 = met[idx]
                neighbor_mask = (
                    mask
                    & (np.abs(met - t0) <= window_s)
                    & (np.arange(len(met)) != idx)
                )
                neighbor_idx = np.where(neighbor_mask)[0]
                if neighbor_idx.size < min_neighbors:
                    continue
                left = int(np.sum(met[neighbor_idx] < t0))
                right = int(np.sum(met[neighbor_idx] > t0))
                if left < min_side_neighbors or right < min_side_neighbors:
                    continue
                t_neighbors = met[neighbor_idx]
                v_neighbors = v[neighbor_idx]
                h_neighbors = h[neighbor_idx]

                try:
                    degree = 2 if neighbor_idx.size >= 5 else 1
                    v_coef = np.polyfit(t_neighbors, v_neighbors, degree)
                    h_coef = np.polyfit(t_neighbors, h_neighbors, degree)
                except (np.linalg.LinAlgError, ValueError):
                    continue

                v_pred = np.polyval(v_coef, t_neighbors)
                h_pred = np.polyval(h_coef, t_neighbors)
                v_res = v_neighbors - v_pred
                h_res = h_neighbors - h_pred

                cov = np.cov(np.stack([v_res, h_res]))
                if cov.shape == ():
                    continue
                var_v = max(float(cov[0, 0]), min_variance[0])
                var_h = max(float(cov[1, 1]), min_variance[1])
                cov_vh = float(cov[0, 1])
                # Clip correlation to avoid singular matrices from near-linear residuals.
                max_cov = 0.9 * np.sqrt(var_v * var_h)
                cov_vh = float(np.clip(cov_vh, -max_cov, max_cov))
                cov_matrix = np.array([[var_v, cov_vh], [cov_vh, var_h]])

                try:
                    inv_cov = np.linalg.inv(cov_matrix)
                except np.linalg.LinAlgError:
                    continue

                v_sample_pred = float(np.polyval(v_coef, t0))
                h_sample_pred = float(np.polyval(h_coef, t0))
                delta = np.array([v[idx] - v_sample_pred, h[idx] - h_sample_pred])
                md2 = float(delta @ inv_cov @ delta)
                if md2 > chi2_threshold:
                    flagged.append(idx)

            if flagged:
                rejected_any = True
                for idx in flagged:
                    df.at[idx, v_col] = np.nan
                    df.at[idx, h_col] = np.nan

        if not rejected_any:
            break
    return df


def apply_outlier_rejection_in_output_dir(
    output_dir: str | Path,
    chi2_threshold: float = 13.82,
    window_s: float = 40.0,
) -> pd.DataFrame:
    output_path = Path(output_dir)
    clean_df = pd.read_csv(output_path / "telemetry_clean.csv")
    cleaned = apply_mahalanobis_outlier_rejection(
        clean_df, chi2_threshold=chi2_threshold, window_s=window_s
    )
    cleaned.to_csv(output_path / "telemetry_clean.csv", index=False)
    return cleaned
