import numpy as np
import pandas as pd

from webcalyzer.postprocess import apply_mahalanobis_outlier_rejection_with_rejected, apply_outlier_rejection_in_output_dir


def test_outlier_rejection_scores_velocity_and_altitude_independently() -> None:
    times = np.arange(0, 42, 2, dtype=float)
    clean_df = pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "stage1_velocity_mps": 10.0 * times,
            "stage1_altitude_m": 100.0 * times,
            "stage2_velocity_mps": np.nan,
            "stage2_altitude_m": np.nan,
        }
    )
    velocity_outlier = clean_df.index[10]
    altitude_outlier = clean_df.index[12]
    clean_df.at[velocity_outlier, "stage1_velocity_mps"] = 0.0
    clean_df.at[velocity_outlier, "stage1_altitude_m"] = np.nan
    clean_df.at[altitude_outlier, "stage1_altitude_m"] = 0.0

    cleaned, rejected = apply_mahalanobis_outlier_rejection_with_rejected(clean_df, window_s=30.0)

    assert pd.isna(cleaned.at[velocity_outlier, "stage1_velocity_mps"])
    assert pd.isna(cleaned.at[velocity_outlier, "stage1_altitude_m"])
    assert rejected.at[velocity_outlier, "stage1_velocity_mps"] == 0.0
    assert pd.isna(rejected.at[velocity_outlier, "stage1_altitude_m"])

    assert cleaned.at[altitude_outlier, "stage1_velocity_mps"] == 10.0 * times[altitude_outlier]
    assert pd.isna(cleaned.at[altitude_outlier, "stage1_altitude_m"])
    assert pd.isna(rejected.at[altitude_outlier, "stage1_velocity_mps"])
    assert rejected.at[altitude_outlier, "stage1_altitude_m"] == 0.0


def test_output_dir_outlier_rejection_is_repeatable_from_raw(tmp_path) -> None:
    times = np.arange(0, 42, 2, dtype=float)
    rows = []
    for index, time_s in enumerate(times):
        velocity_mps = 10.0 * time_s
        altitude_m = 100.0 * time_s
        velocity_mph = int(round(velocity_mps / 0.44704))
        altitude_ft = int(round(altitude_m / 0.3048))
        if index == 10:
            velocity_text = "000,000 MPH"
            altitude_text = np.nan
        else:
            velocity_text = f"{velocity_mph:06,} MPH"
            altitude_text = f"{altitude_ft:06,} FT"
        rows.append(
            {
                "frame_index": index,
                "sample_time_s": time_s,
                "mission_elapsed_time_s": time_s,
                "stage1_velocity_raw_text": velocity_text,
                "stage1_altitude_raw_text": altitude_text,
                "stage2_velocity_raw_text": np.nan,
                "stage2_altitude_raw_text": np.nan,
            }
        )
    pd.DataFrame(rows).to_csv(tmp_path / "telemetry_raw.csv", index=False)

    apply_outlier_rejection_in_output_dir(tmp_path, window_s=30.0)
    first_rejected = pd.read_csv(tmp_path / "telemetry_rejected.csv")
    apply_outlier_rejection_in_output_dir(tmp_path, window_s=30.0)
    second_rejected = pd.read_csv(tmp_path / "telemetry_rejected.csv")

    assert first_rejected["stage1_velocity_mps"].notna().sum() == 1
    assert second_rejected["stage1_velocity_mps"].notna().sum() == 1
