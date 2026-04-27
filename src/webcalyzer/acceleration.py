from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


G0_MPS2 = 9.80665
ACCELERATION_SOURCE_GAP_THRESHOLD_S = 10.0

# Savitzky-Golay defaults. These are intentionally mirrored into
# TrajectoryConfig/YAML so runs have explicit visibility and control.
DEFAULT_DERIVATIVE_WINDOW_S = 20.0
DEFAULT_DERIVATIVE_POLYORDER = 3
DEFAULT_MIN_WINDOW_SAMPLES = DEFAULT_DERIVATIVE_POLYORDER + 2
DEFAULT_DERIVATIVE_MODE = "interp"
SAVGOL_MODES = frozenset({"mirror", "constant", "nearest", "wrap", "interp"})

# Backward-compatible aliases for callers/tests that imported the old names.
SMOOTHING_POLYORDER = DEFAULT_DERIVATIVE_POLYORDER
MIN_WINDOW_SAMPLES = DEFAULT_MIN_WINDOW_SAMPLES


def acceleration_profile(
    *,
    clean_df: pd.DataFrame,
    trajectory_df: pd.DataFrame,
    stage: str,
    max_source_gap_s: float = ACCELERATION_SOURCE_GAP_THRESHOLD_S,
    derivative_window_s: float = DEFAULT_DERIVATIVE_WINDOW_S,
    derivative_polyorder: int = DEFAULT_DERIVATIVE_POLYORDER,
    derivative_min_window_samples: int = DEFAULT_MIN_WINDOW_SAMPLES,
    derivative_mode: str = DEFAULT_DERIVATIVE_MODE,
) -> tuple[np.ndarray, np.ndarray]:
    if max_source_gap_s <= 0 or not np.isfinite(max_source_gap_s):
        raise ValueError("acceleration_source_gap_threshold_s must be a positive finite value")
    stage_df = trajectory_df[trajectory_df["stage"] == stage]
    times, velocity = _trajectory_velocity_points(stage_df)
    if times.size < 2:
        return np.array([], dtype=float), np.array([], dtype=float)

    source_times = source_velocity_times(clean_df, stage)
    valid_mask = source_gap_mask(
        trajectory_times=times,
        source_times=source_times,
        max_gap_s=max_source_gap_s,
    )
    acceleration_g = np.full_like(velocity, np.nan, dtype=float)
    for start, end in _contiguous_true_runs(valid_mask):
        if end - start < 2:
            continue
        segment_times = times[start:end]
        segment_velocity = velocity[start:end]
        _smoothed, derivative_mps2 = smoothed_velocity_and_derivative(
            segment_times,
            segment_velocity,
            window_s=derivative_window_s,
            polyorder=derivative_polyorder,
            min_window_samples=derivative_min_window_samples,
            mode=derivative_mode,
        )
        acceleration_g[start:end] = derivative_mps2 / G0_MPS2
    return times, acceleration_g


def smoothed_velocity_profile(
    *,
    clean_df: pd.DataFrame,
    trajectory_df: pd.DataFrame,
    stage: str,
    max_source_gap_s: float = ACCELERATION_SOURCE_GAP_THRESHOLD_S,
    derivative_window_s: float = DEFAULT_DERIVATIVE_WINDOW_S,
    derivative_polyorder: int = DEFAULT_DERIVATIVE_POLYORDER,
    derivative_min_window_samples: int = DEFAULT_MIN_WINDOW_SAMPLES,
    derivative_mode: str = DEFAULT_DERIVATIVE_MODE,
) -> tuple[np.ndarray, np.ndarray]:
    if max_source_gap_s <= 0 or not np.isfinite(max_source_gap_s):
        raise ValueError("acceleration_source_gap_threshold_s must be a positive finite value")
    stage_df = trajectory_df[trajectory_df["stage"] == stage]
    times, velocity = _trajectory_velocity_points(stage_df)
    if times.size < 2:
        return np.array([], dtype=float), np.array([], dtype=float)

    source_times = source_velocity_times(clean_df, stage)
    valid_mask = source_gap_mask(
        trajectory_times=times,
        source_times=source_times,
        max_gap_s=max_source_gap_s,
    )
    smoothed = np.full_like(velocity, np.nan, dtype=float)
    for start, end in _contiguous_true_runs(valid_mask):
        if end - start < 2:
            continue
        segment_times = times[start:end]
        segment_velocity = velocity[start:end]
        smoothed_segment, _derivative_mps2 = smoothed_velocity_and_derivative(
            segment_times,
            segment_velocity,
            window_s=derivative_window_s,
            polyorder=derivative_polyorder,
            min_window_samples=derivative_min_window_samples,
            mode=derivative_mode,
        )
        smoothed[start:end] = smoothed_segment
    return times, smoothed


def _trajectory_velocity_points(stage_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    if stage_df.empty:
        return np.array([], dtype=float), np.array([], dtype=float)
    points = pd.DataFrame(
        {
            "time": pd.to_numeric(stage_df["mission_elapsed_time_s"], errors="coerce"),
            "velocity": pd.to_numeric(stage_df["velocity_mps"], errors="coerce"),
        }
    ).dropna()
    points = points[np.isfinite(points["time"]) & np.isfinite(points["velocity"])]
    if points.shape[0] < 2:
        return np.array([], dtype=float), np.array([], dtype=float)
    points = points.sort_values("time").drop_duplicates("time", keep="first")
    if points.shape[0] < 2:
        return np.array([], dtype=float), np.array([], dtype=float)
    return points["time"].to_numpy(dtype=float), points["velocity"].to_numpy(dtype=float)


def smoothed_velocity_for_derivative(
    times: np.ndarray,
    velocity_mps: np.ndarray,
    window_s: float = DEFAULT_DERIVATIVE_WINDOW_S,
    polyorder: int = DEFAULT_DERIVATIVE_POLYORDER,
    min_window_samples: int = DEFAULT_MIN_WINDOW_SAMPLES,
    mode: str = DEFAULT_DERIVATIVE_MODE,
) -> np.ndarray:
    """Return a hidden smoothed velocity series used only for derivatives."""

    smoothed_velocity, _derivative_mps2 = smoothed_velocity_and_derivative(
        times,
        velocity_mps,
        window_s=window_s,
        polyorder=polyorder,
        min_window_samples=min_window_samples,
        mode=mode,
    )
    return smoothed_velocity


def smoothed_velocity_and_derivative(
    times: np.ndarray,
    velocity_mps: np.ndarray,
    *,
    window_s: float = DEFAULT_DERIVATIVE_WINDOW_S,
    polyorder: int = DEFAULT_DERIVATIVE_POLYORDER,
    min_window_samples: int = DEFAULT_MIN_WINDOW_SAMPLES,
    mode: str = DEFAULT_DERIVATIVE_MODE,
) -> tuple[np.ndarray, np.ndarray]:
    """Return derivative-ready velocity and its time derivative.

    Uses a Savitzky-Golay filter sized in seconds. A textbook approach for
    differentiating a noisy uniformly-sampled signal: fit a local polynomial
    of degree ``polyorder`` over a sliding window, then evaluate the
    polynomial (or its analytical derivative) at the centre. Sizing the
    window in seconds rather than samples keeps the smoothing FPS-independent
    while letting denser sampling automatically buy more noise rejection.
    """

    times = np.asarray(times, dtype=float)
    velocity_mps = np.asarray(velocity_mps, dtype=float)
    if window_s <= 0 or not np.isfinite(window_s):
        raise ValueError("derivative_smoothing_window_s must be a positive finite value")
    polyorder, min_window_samples, mode = _validated_savgol_settings(
        polyorder=polyorder,
        min_window_samples=min_window_samples,
        mode=mode,
    )
    if times.size < min_window_samples:
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)

    median_dt = _median_positive_dt(times)
    if median_dt is None:
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)

    target_samples = max(min_window_samples, int(round(window_s / median_dt)))
    window_length = target_samples if target_samples % 2 == 1 else target_samples + 1
    if window_length > times.size:
        # Fall back to the largest odd window the segment can support.
        window_length = times.size if times.size % 2 == 1 else times.size - 1
    if window_length < min_window_samples:
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)

    try:
        smoothed = savgol_filter(
            velocity_mps,
            window_length=window_length,
            polyorder=polyorder,
            delta=median_dt,
            mode=mode,
        )
        derivative = savgol_filter(
            velocity_mps,
            window_length=window_length,
            polyorder=polyorder,
            delta=median_dt,
            deriv=1,
            mode=mode,
        )
    except ValueError:
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)

    if not np.isfinite(smoothed).all() or not np.isfinite(derivative).all():
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)

    return np.asarray(smoothed, dtype=float), np.asarray(derivative, dtype=float)


def _validated_savgol_settings(
    *,
    polyorder: int,
    min_window_samples: int,
    mode: str,
) -> tuple[int, int, str]:
    polyorder = int(polyorder)
    min_window_samples = int(min_window_samples)
    mode = str(mode).strip().lower()
    if polyorder < 1:
        raise ValueError("derivative_smoothing_polyorder must be at least 1")
    if min_window_samples <= polyorder:
        raise ValueError("derivative_min_window_samples must be greater than derivative_smoothing_polyorder")
    if min_window_samples % 2 == 0:
        raise ValueError("derivative_min_window_samples must be odd")
    if mode not in SAVGOL_MODES:
        raise ValueError(f"derivative_smoothing_mode must be one of {sorted(SAVGOL_MODES)}")
    return polyorder, min_window_samples, mode


def velocity_derivative(times: np.ndarray, velocity_mps: np.ndarray) -> np.ndarray:
    edge_order = 2 if times.size >= 3 else 1
    return np.gradient(velocity_mps, times, edge_order=edge_order)


def _median_positive_dt(times: np.ndarray) -> float | None:
    if times.size < 2:
        return None
    diffs = np.diff(times)
    positive = diffs[diffs > 1e-9]
    if positive.size == 0:
        return None
    median = float(np.median(positive))
    if not np.isfinite(median) or median <= 0.0:
        return None
    return median


def source_velocity_times(clean_df: pd.DataFrame, stage: str) -> np.ndarray:
    time_column = "mission_elapsed_time_s"
    velocity_column = f"{stage}_velocity_mps"
    if time_column not in clean_df.columns or velocity_column not in clean_df.columns:
        return np.array([], dtype=float)
    times = pd.to_numeric(clean_df[time_column], errors="coerce").to_numpy(dtype=float)
    values = pd.to_numeric(clean_df[velocity_column], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(times) & np.isfinite(values)
    times = times[finite]
    if stage == "stage1":
        times = np.concatenate([np.array([0.0]), times[times > 0.0]])
    return np.unique(np.sort(times))


def source_gap_mask(
    trajectory_times: np.ndarray,
    source_times: np.ndarray,
    max_gap_s: float,
) -> np.ndarray:
    if source_times.size < 2:
        return np.zeros_like(trajectory_times, dtype=bool)
    source_times = np.unique(np.sort(source_times[np.isfinite(source_times)]))
    if source_times.size < 2:
        return np.zeros_like(trajectory_times, dtype=bool)

    mask = np.zeros_like(trajectory_times, dtype=bool)
    for left, right in zip(source_times[:-1], source_times[1:]):
        if right - left <= max_gap_s:
            mask |= (trajectory_times >= left) & (trajectory_times <= right)
    return mask


def _contiguous_true_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(mask):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(mask) - 1):
            end = index + 1 if value and index == len(mask) - 1 else index
            runs.append((start, end))
            start = None
    return runs
