import numpy as np
import pandas as pd

from webcalyzer.config import default_parsing_profile
from webcalyzer.models import HardcodedRawDataPoint
from webcalyzer.models import ProfileConfig
from webcalyzer.models import TrajectoryConfig
from webcalyzer.postprocess import (
    apply_mahalanobis_outlier_rejection_with_rejected,
    apply_outlier_rejection_in_output_dir,
    rebuild_clean_from_raw,
)


def test_outlier_rejection_flags_first_sample_when_grossly_inconsistent() -> None:
    """Boundary fallback: an outlier on the first sample with no left
    neighbors must still be evaluated. Without the boundary fallback the
    bilateral side-count check skipped index 0 entirely, letting a 90 km
    spike at MET=1 reach the trajectory module."""

    times = np.array([1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0, 15.0, 17.0, 19.0, 21.0, 23.0])
    altitude = np.array([90123.264, 60.0, 90.0, 130.0, 180.0, 250.0, 350.0, 470.0, 620.0, 800.0, 1010.0, 1260.0])
    velocity = np.linspace(0.0, 25.0, len(times))
    clean_df = pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "stage1_velocity_mps": velocity,
            "stage1_altitude_m": altitude,
            "stage2_velocity_mps": np.nan,
            "stage2_altitude_m": np.nan,
        }
    )

    cleaned, rejected = apply_mahalanobis_outlier_rejection_with_rejected(clean_df, window_s=40.0)

    assert pd.isna(cleaned.at[0, "stage1_altitude_m"])
    assert rejected.at[0, "stage1_altitude_m"] == 90123.264


def test_outlier_rejection_scales_neighbor_count_with_fps() -> None:
    """When `min_neighbors` is left as default the threshold scales with FPS:
    at high FPS each window contains many more samples, so we ask for more
    of them before trusting the local fit."""

    # 10-second window at 4 fps => 40 expected neighbors. At 0.5 fps => 5.
    # The function should not raise and should return more flagged samples
    # at the higher rate, demonstrating the scaling kicked in.
    high_fps_times = np.arange(0.0, 50.0, 0.25)
    low_fps_times = np.arange(0.0, 50.0, 2.0)

    def _make_df(times: np.ndarray, spike_index: int) -> pd.DataFrame:
        altitude = np.linspace(0.0, 5000.0, times.size)
        altitude[spike_index] = 100000.0  # gross outlier
        return pd.DataFrame(
            {
                "frame_index": np.arange(times.size),
                "sample_time_s": times,
                "mission_elapsed_time_s": times,
                "stage1_velocity_mps": np.linspace(0.0, 100.0, times.size),
                "stage1_altitude_m": altitude,
                "stage2_velocity_mps": np.nan,
                "stage2_altitude_m": np.nan,
            }
        )

    high_cleaned, _ = apply_mahalanobis_outlier_rejection_with_rejected(
        _make_df(high_fps_times, spike_index=20), window_s=40.0
    )
    low_cleaned, _ = apply_mahalanobis_outlier_rejection_with_rejected(
        _make_df(low_fps_times, spike_index=5), window_s=40.0
    )

    assert pd.isna(high_cleaned.at[20, "stage1_altitude_m"])
    assert pd.isna(low_cleaned.at[5, "stage1_altitude_m"])


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


def test_outlier_rejection_catches_split_decimal_altitude_without_rejecting_landing_crossing() -> None:
    ascent_times = np.arange(21, 103, 2, dtype=float)
    ascent_altitude = np.array(
        [
            500, 600, 800, 900, 1100, 1400, 1600, 1900, 2200, 2500,
            2900, 3200, 3600, 4000, 4500, 5000, 5500, 6000, 6600, 7100,
            700, 8300, 9000, 9600, 10300, 11000, 11700, 12500, 13200, 14100,
            14900, 15800, 16700, 17600, 18600, 19600, 20600, 21700, 22800, 23900,
            25100,
        ],
        dtype=float,
    )
    descent_times = np.array(
        [
            397, 399, 401, 403, 405, 407, 409, 411, 412, 415, 416, 419,
            421, 422, 425, 426, 429, 431, 433, 435, 437, 439, 441, 443,
            445, 446, 448, 451, 452, 455, 457, 459, 461, 463, 465, 467,
            469, 471, 473, 475, 477, 479, 481, 483, 485, 486, 489, 491,
            493, 495, 497, 499, 501, 503, 505, 507, 509, 511, 513, 515,
            517, 519, 521, 523, 525, 527, 529, 531,
        ],
        dtype=float,
    )
    descent_altitude = np.array(
        [
            74200, 72100, 70000, 67800, 65700, 63500, 61200, 58900, 56700, 54400,
            52300, 50200, 48100, 46100, 44200, 42400, 40700, 39000, 37400, 35900,
            34300, 32700, 31100, 29400, 27800, 26200, 24500, 22900, 21400, 19900,
            18400, 17100, 15800, 14600, 13600, 12700, 11900, 11100, 10500, 9900,
            9300, 8800, 8400, 900, 7500, 7100, 7000, 6300, 5900, 5500,
            5100, 4000, 3000, 3900, 3500, 3100, 2700, 2300, 1900, 1600,
            1300, 1000, 700, 500, 300, 200, 100, 0,
        ],
        dtype=float,
    )
    times = np.concatenate([ascent_times, descent_times])
    clean_df = pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "stage1_velocity_mps": np.nan,
            "stage1_altitude_m": np.concatenate([ascent_altitude, descent_altitude]),
            "stage2_velocity_mps": np.nan,
            "stage2_altitude_m": np.nan,
        }
    )

    cleaned, rejected = apply_mahalanobis_outlier_rejection_with_rejected(clean_df, window_s=40.0)

    rejected_altitude = rejected[rejected["stage1_altitude_m"].notna()]
    assert rejected_altitude["mission_elapsed_time_s"].tolist() == [61.0, 483.0]
    assert cleaned.loc[cleaned["mission_elapsed_time_s"].eq(521.0), "stage1_altitude_m"].iloc[0] == 700.0


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


def test_output_dir_outlier_rejection_uses_profile_thresholds(tmp_path) -> None:
    times = np.arange(0, 42, 2, dtype=float)
    altitude = 100.0 * times
    altitude[10] = 0.0
    clean_df = pd.DataFrame(
        {
            "frame_index": np.arange(times.size),
            "sample_time_s": times,
            "mission_elapsed_time_s": times,
            "stage1_velocity_mps": 10.0 * times,
            "stage1_altitude_m": altitude,
            "stage2_velocity_mps": np.nan,
            "stage2_altitude_m": np.nan,
        }
    )
    clean_df.to_csv(tmp_path / "telemetry_clean.csv", index=False)
    profile = ProfileConfig(
        profile_name="wide_outlier_threshold",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        trajectory=TrajectoryConfig(
            outlier_rejection_chi2_threshold=1_000_000.0,
            outlier_rejection_window_s=30.0,
        ),
    )

    cleaned = apply_outlier_rejection_in_output_dir(tmp_path, profile=profile)

    assert cleaned.at[10, "stage1_altitude_m"] == 0.0


def test_rebuild_clean_inserts_hardcoded_raw_data_point() -> None:
    raw_df = pd.DataFrame(
        [
            {
                "frame_index": 0,
                "sample_time_s": 558.0,
                "mission_elapsed_time_s": 558.0,
                "stage1_velocity_raw_text": "001,000 MPH",
                "stage1_altitude_raw_text": "010,000 FT",
            },
            {
                "frame_index": 1,
                "sample_time_s": 562.0,
                "mission_elapsed_time_s": 562.0,
                "stage1_velocity_raw_text": "000,900 MPH",
                "stage1_altitude_raw_text": "009,000 FT",
            },
        ]
    )

    clean_df = rebuild_clean_from_raw(
        raw_df,
        [
            HardcodedRawDataPoint(
                mission_elapsed_time_s=560.0,
                stage1_velocity_mps=0.0,
                stage1_altitude_m=0.0,
            )
        ],
    )

    inserted = clean_df[clean_df["mission_elapsed_time_s"] == 560.0].iloc[0]
    assert clean_df["mission_elapsed_time_s"].tolist() == [558.0, 560.0, 562.0]
    assert inserted["stage1_velocity_mps"] == 0.0
    assert inserted["stage1_altitude_m"] == 0.0


def test_rebuild_clean_replaces_overlapping_hardcoded_raw_data_point() -> None:
    raw_df = pd.DataFrame(
        [
            {
                "frame_index": 0,
                "sample_time_s": 560.0,
                "mission_elapsed_time_s": 560.0,
                "stage1_velocity_raw_text": "001,000 MPH",
                "stage1_altitude_raw_text": "010,000 FT",
            }
        ]
    )

    clean_df = rebuild_clean_from_raw(
        raw_df,
        [
            HardcodedRawDataPoint(
                mission_elapsed_time_s=560.0,
                stage1_velocity_mps=0.0,
                stage1_altitude_m=0.0,
            )
        ],
    )

    assert len(clean_df) == 1
    assert clean_df.loc[0, "stage1_velocity_mps"] == 0.0
    assert clean_df.loc[0, "stage1_altitude_m"] == 0.0


def test_hardcoded_stage2_zero_is_not_suppressed_before_activation() -> None:
    clean_df = rebuild_clean_from_raw(
        pd.DataFrame(
            [
                {
                    "frame_index": 0,
                    "sample_time_s": 10.0,
                    "mission_elapsed_time_s": 10.0,
                }
            ]
        ),
        [
            HardcodedRawDataPoint(
                mission_elapsed_time_s=10.0,
                stage2_velocity_mps=0.0,
                stage2_altitude_m=0.0,
            )
        ],
    )

    assert clean_df.loc[0, "stage2_velocity_mps"] == 0.0
    assert clean_df.loc[0, "stage2_altitude_m"] == 0.0


def test_rebuild_clean_uses_recent_explicit_unit_for_unitless_altitude() -> None:
    raw_df = pd.DataFrame(
        [
            {
                "frame_index": 0,
                "sample_time_s": 1080.0,
                "mission_elapsed_time_s": 1080.0,
                "stage2_altitude_raw_text": "ALTITUDE 166 KM",
            },
            {
                "frame_index": 1,
                "sample_time_s": 1094.0,
                "mission_elapsed_time_s": 1094.0,
                "stage2_altitude_raw_text": "ALTITUDE 166",
            },
            {
                "frame_index": 2,
                "sample_time_s": 1110.0,
                "mission_elapsed_time_s": 1110.0,
                "stage2_altitude_raw_text": "ALTITUDE 166 KM",
            },
        ]
    )
    profile = ProfileConfig(
        profile_name="km_feed",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        parsing=default_parsing_profile(),
    )

    clean_df = rebuild_clean_from_raw(raw_df, profile=profile)

    assert clean_df["stage2_altitude_m"].tolist() == [166000.0, 166000.0, 166000.0]


def test_rebuild_clean_recovers_missing_k_in_kilometer_unit() -> None:
    raw_df = pd.DataFrame(
        [
            {
                "frame_index": 0,
                "sample_time_s": 1080.0,
                "mission_elapsed_time_s": 1080.0,
                "stage2_altitude_raw_text": "ALTITUDE 166 KM",
            },
            {
                "frame_index": 1,
                "sample_time_s": 1082.0,
                "mission_elapsed_time_s": 1082.0,
                "stage2_altitude_raw_text": "ALTITUDE 166 KM",
            },
            {
                "frame_index": 2,
                "sample_time_s": 1084.0,
                "mission_elapsed_time_s": 1084.0,
                "stage2_altitude_raw_text": "ALTITUDE 166 M",
            },
        ]
    )
    profile = ProfileConfig(
        profile_name="km_feed",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        parsing=default_parsing_profile(),
    )

    clean_df = rebuild_clean_from_raw(raw_df, profile=profile)

    assert clean_df["stage2_altitude_m"].tolist() == [166000.0, 166000.0, 166000.0]
