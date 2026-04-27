from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.interpolate import UnivariateSpline


G0_MPS2 = 9.80665
ACCELERATION_SOURCE_GAP_THRESHOLD_S = 10.0
DERIVATIVE_SMOOTHING_STRENGTH = 300.0


def acceleration_profile(
    *,
    clean_df: pd.DataFrame,
    trajectory_df: pd.DataFrame,
    stage: str,
    max_source_gap_s: float = ACCELERATION_SOURCE_GAP_THRESHOLD_S,
) -> tuple[np.ndarray, np.ndarray]:
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
        smoothed_velocity, derivative_mps2 = smoothed_velocity_and_derivative(segment_times, segment_velocity)
        acceleration_g[start:end] = derivative_mps2 / G0_MPS2
    return times, acceleration_g


def smoothed_velocity_profile(
    *,
    clean_df: pd.DataFrame,
    trajectory_df: pd.DataFrame,
    stage: str,
    max_source_gap_s: float = ACCELERATION_SOURCE_GAP_THRESHOLD_S,
) -> tuple[np.ndarray, np.ndarray]:
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
        smoothed_velocity, _derivative_mps2 = smoothed_velocity_and_derivative(segment_times, segment_velocity)
        smoothed[start:end] = smoothed_velocity
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


def smoothed_velocity_for_derivative(times: np.ndarray, velocity_mps: np.ndarray) -> np.ndarray:
    """Return a hidden smoothed velocity series used only for derivatives."""

    smoothed_velocity, _derivative_mps2 = smoothed_velocity_and_derivative(times, velocity_mps)
    return smoothed_velocity


def smoothed_velocity_and_derivative(
    times: np.ndarray,
    velocity_mps: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return derivative-ready velocity and its time derivative.

    The smoothing factor is automatic: estimate high-frequency velocity
    scatter robustly from the segment itself, then allow a middle-ground
    residual budget around that scatter. This intentionally smooths more
    aggressively than GCV, which was too willing to chase OCR jitter.
    """

    if times.size < 5:
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)

    smoothing_factor = _automatic_smoothing_factor(times, velocity_mps)
    try:
        spline = UnivariateSpline(times, velocity_mps, s=smoothing_factor, k=3)
    except ValueError:
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)

    smoothed = np.asarray(spline(times), dtype=float)
    if smoothed.shape != velocity_mps.shape or not np.isfinite(smoothed).all():
        velocity = velocity_mps.astype(float, copy=True)
        return velocity, velocity_derivative(times, velocity)
    derivative = np.asarray(spline.derivative()(times), dtype=float)
    if derivative.shape != velocity_mps.shape or not np.isfinite(derivative).all():
        derivative = velocity_derivative(times, smoothed)
    return smoothed, derivative


def velocity_derivative(times: np.ndarray, velocity_mps: np.ndarray) -> np.ndarray:
    edge_order = 2 if times.size >= 3 else 1
    return np.gradient(velocity_mps, times, edge_order=edge_order)


def _automatic_smoothing_factor(times: np.ndarray, velocity_mps: np.ndarray) -> float:
    del times
    sigma = _robust_velocity_noise(velocity_mps)
    return max(float(velocity_mps.size) * sigma * sigma * DERIVATIVE_SMOOTHING_STRENGTH, 1e-9)


def _robust_velocity_noise(values: np.ndarray) -> float:
    if values.size < 5:
        return 1e-6

    rolling_window = max(7, min(101, (values.size // 12) | 1))
    if rolling_window % 2 == 0:
        rolling_window += 1
    local_trend = (
        pd.Series(values)
        .rolling(rolling_window, center=True, min_periods=1)
        .median()
        .to_numpy(dtype=float)
    )
    residual = values - local_trend
    residual_sigma = _mad_sigma(residual)

    # Dense interpolation can make pointwise residuals look deceptively
    # small. First differences give a second estimate of local jitter.
    diff_sigma = float(np.std(np.diff(values))) * 0.15 if values.size >= 2 else 0.0
    return max(residual_sigma, diff_sigma, 1e-6)


def _mad_sigma(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    return 1.4826 * mad


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
