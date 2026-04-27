from __future__ import annotations

from dataclasses import replace
from math import atan, atan2, cos, degrees, isfinite, radians, sin, sqrt, tan
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.interpolate import Akima1DInterpolator, CubicSpline, PchipInterpolator, interp1d

from webcalyzer.acceleration import SAVGOL_MODES
from webcalyzer.models import LaunchSiteConfig, TrajectoryConfig


STAGES = ("stage1", "stage2")
TRAJECTORY_FILENAME = "trajectory.csv"
TRAJECTORY_COLUMNS = [
    "stage",
    "mission_elapsed_time_s",
    "velocity_mps",
    "altitude_m",
    "total_distance_m",
    "downrange_m",
    "latitude_deg",
    "longitude_deg",
    "coordinate_model",
    "interpolation_method",
    "integration_method",
    "integration_step_s",
    "sample_fps",
]

INTERPOLATION_METHODS = {"linear", "pchip", "akima", "cubic"}
INTEGRATION_METHODS = {"euler", "midpoint", "trapezoid", "rk4", "simpson"}
DEFAULT_INFERRED_FPS = 4.0
MIN_INFERRED_FPS = 0.05

WGS84_A_M = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_B_M = WGS84_A_M * (1 - WGS84_F)


ScalarFunction = Callable[[float], float]


def reconstruct_trajectory(
    clean_df: pd.DataFrame,
    config: TrajectoryConfig | None = None,
    *,
    sample_fps: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct total and downrange distance for each extracted stage.

    The integration grid step is the OCR sample period (``1 / sample_fps``)
    so the trajectory grid stays consistent with the input cadence.
    ``sample_fps`` is inferred from ``clean_df`` when not supplied.

    Velocity and altitude interpolation is intentionally internal to this
    module. The returned clean dataframe keeps the original velocity/altitude
    gaps and only appends reconstructed trajectory columns.
    """

    config = _validated_config(config or TrajectoryConfig())
    augmented = clean_df.copy()
    for stage in STAGES:
        _ensure_augmented_columns(augmented, stage)

    if not config.enabled:
        return augmented, _empty_trajectory_frame()

    effective_fps = _resolve_sample_fps(clean_df, sample_fps)
    integration_step_s = 1.0 / effective_fps

    trajectory_frames: list[pd.DataFrame] = []
    stage1_trajectory = _reconstruct_stage(
        clean_df, "stage1", config, integration_step_s=integration_step_s, sample_fps=effective_fps
    )
    if not stage1_trajectory.empty:
        trajectory_frames.append(stage1_trajectory)
        _append_stage_trajectory_columns(augmented, "stage1", stage1_trajectory)

    stage2_trajectory = _reconstruct_stage(
        clean_df,
        "stage2",
        config,
        integration_step_s=integration_step_s,
        sample_fps=effective_fps,
        reference_trajectory=stage1_trajectory,
    )
    if not stage2_trajectory.empty:
        trajectory_frames.append(stage2_trajectory)
        _append_stage_trajectory_columns(augmented, "stage2", stage2_trajectory)

    if not trajectory_frames:
        return augmented, _empty_trajectory_frame()
    return augmented, pd.concat(trajectory_frames, ignore_index=True)


def write_trajectory_outputs(
    clean_df: pd.DataFrame,
    output_dir: str | Path,
    config: TrajectoryConfig | None = None,
    *,
    sample_fps: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    augmented, trajectory_df = reconstruct_trajectory(
        clean_df, config=config, sample_fps=sample_fps
    )
    output_path = Path(output_dir)
    augmented.to_csv(output_path / "telemetry_clean.csv", index=False)
    trajectory_df.to_csv(output_path / TRAJECTORY_FILENAME, index=False)
    return augmented, trajectory_df


def infer_sample_fps(clean_df: pd.DataFrame) -> float | None:
    """Estimate the OCR sample FPS from ``clean_df``.

    Uses the median positive difference of ``sample_time_s`` if present,
    otherwise of ``mission_elapsed_time_s``. Returns None when there is
    no usable cadence (single sample, etc.).
    """

    for column in ("sample_time_s", "mission_elapsed_time_s"):
        if column not in clean_df.columns:
            continue
        times = pd.to_numeric(clean_df[column], errors="coerce").to_numpy(dtype=float)
        times = times[np.isfinite(times)]
        if times.size < 2:
            continue
        diffs = np.diff(np.sort(times))
        positive = diffs[diffs > 1e-6]
        if positive.size == 0:
            continue
        median_dt = float(np.median(positive))
        if median_dt <= 0 or not isfinite(median_dt):
            continue
        return 1.0 / median_dt
    return None


def _resolve_sample_fps(clean_df: pd.DataFrame, sample_fps: float | None) -> float:
    if sample_fps is not None:
        if not isfinite(sample_fps) or sample_fps <= 0.0:
            raise ValueError("sample_fps must be a positive finite value")
        return float(sample_fps)
    inferred = infer_sample_fps(clean_df)
    if inferred is None:
        return DEFAULT_INFERRED_FPS
    return max(float(inferred), MIN_INFERRED_FPS)


def _validated_config(config: TrajectoryConfig) -> TrajectoryConfig:
    interpolation_method = config.interpolation_method.strip().lower()
    integration_method = config.integration_method.strip().lower()
    if interpolation_method not in INTERPOLATION_METHODS:
        raise ValueError(
            f"trajectory.interpolation_method must be one of {sorted(INTERPOLATION_METHODS)}; "
            f"got {config.interpolation_method!r}"
        )
    if integration_method not in INTEGRATION_METHODS:
        raise ValueError(
            f"trajectory.integration_method must be one of {sorted(INTEGRATION_METHODS)}; "
            f"got {config.integration_method!r}"
        )
    if config.coarse_altitude_threshold_m <= 0 or not isfinite(config.coarse_altitude_threshold_m):
        raise ValueError("trajectory.coarse_altitude_threshold_m must be a positive finite value")
    if config.coarse_velocity_threshold_mps <= 0 or not isfinite(config.coarse_velocity_threshold_mps):
        raise ValueError("trajectory.coarse_velocity_threshold_mps must be a positive finite value")
    if config.coarse_step_max_gap_s <= 0 or not isfinite(config.coarse_step_max_gap_s):
        raise ValueError("trajectory.coarse_step_max_gap_s must be a positive finite value")
    if config.acceleration_source_gap_threshold_s <= 0 or not isfinite(config.acceleration_source_gap_threshold_s):
        raise ValueError("trajectory.acceleration_source_gap_threshold_s must be a positive finite value")
    if config.derivative_smoothing_window_s <= 0 or not isfinite(config.derivative_smoothing_window_s):
        raise ValueError("trajectory.derivative_smoothing_window_s must be a positive finite value")
    if config.derivative_smoothing_polyorder < 1:
        raise ValueError("trajectory.derivative_smoothing_polyorder must be at least 1")
    if config.derivative_min_window_samples <= config.derivative_smoothing_polyorder:
        raise ValueError(
            "trajectory.derivative_min_window_samples must be greater than "
            "trajectory.derivative_smoothing_polyorder"
        )
    if config.derivative_min_window_samples % 2 == 0:
        raise ValueError("trajectory.derivative_min_window_samples must be odd")
    derivative_smoothing_mode = config.derivative_smoothing_mode.strip().lower()
    if derivative_smoothing_mode not in SAVGOL_MODES:
        raise ValueError(f"trajectory.derivative_smoothing_mode must be one of {sorted(SAVGOL_MODES)}")
    return replace(
        config,
        interpolation_method=interpolation_method,
        integration_method="rk4" if integration_method == "simpson" else integration_method,
        outlier_preconditioning_enabled=bool(config.outlier_preconditioning_enabled),
        coarse_step_smoothing_enabled=bool(config.coarse_step_smoothing_enabled),
        derivative_smoothing_polyorder=int(config.derivative_smoothing_polyorder),
        derivative_min_window_samples=int(config.derivative_min_window_samples),
        derivative_smoothing_mode=derivative_smoothing_mode,
    )


def _empty_trajectory_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=TRAJECTORY_COLUMNS)


def _ensure_augmented_columns(df: pd.DataFrame, stage: str) -> None:
    for suffix in ("total_distance_m", "downrange_m", "latitude_deg", "longitude_deg"):
        column = f"{stage}_{suffix}"
        if column not in df.columns:
            df[column] = np.nan


def _reconstruct_stage(
    clean_df: pd.DataFrame,
    stage: str,
    config: TrajectoryConfig,
    *,
    integration_step_s: float,
    sample_fps: float,
    reference_trajectory: pd.DataFrame | None = None,
) -> pd.DataFrame:
    time_column = "mission_elapsed_time_s"
    velocity_column = f"{stage}_velocity_mps"
    altitude_column = f"{stage}_altitude_m"
    if time_column not in clean_df.columns or velocity_column not in clean_df.columns or altitude_column not in clean_df.columns:
        return _empty_trajectory_frame()

    is_primary_stage = reference_trajectory is None
    velocity_points = _signal_points(
        clean_df,
        time_column,
        velocity_column,
        include_liftoff_anchor=is_primary_stage,
        coarse_threshold=config.coarse_velocity_threshold_mps,
        coarse_max_gap_s=config.coarse_step_max_gap_s,
        outlier_preconditioning_enabled=config.outlier_preconditioning_enabled,
        smoothing_enabled=config.coarse_step_smoothing_enabled,
    )
    altitude_points = _signal_points(
        clean_df,
        time_column,
        altitude_column,
        include_liftoff_anchor=is_primary_stage,
        coarse_threshold=config.coarse_altitude_threshold_m,
        coarse_max_gap_s=config.coarse_step_max_gap_s,
        outlier_preconditioning_enabled=config.outlier_preconditioning_enabled,
        smoothing_enabled=config.coarse_step_smoothing_enabled,
    )
    if len(velocity_points[0]) < 2 or len(altitude_points[0]) < 2:
        return _empty_trajectory_frame()

    start_time_s = 0.0 if is_primary_stage else max(float(velocity_points[0][0]), float(altitude_points[0][0]))
    end_time_s = min(float(velocity_points[0][-1]), float(altitude_points[0][-1]))
    if end_time_s <= start_time_s:
        return _empty_trajectory_frame()

    velocity = _make_interpolator(*velocity_points, method=config.interpolation_method)
    altitude = _make_interpolator(*altitude_points, method=config.interpolation_method)
    grid = _fixed_time_grid(start_time_s, end_time_s, integration_step_s)
    velocity_values = np.array([velocity(float(time_s)) for time_s in grid], dtype=float)
    altitude_values = np.array([altitude(float(time_s)) for time_s in grid], dtype=float)

    initial_total_distance = _reference_value(reference_trajectory, start_time_s, "total_distance_m")
    initial_downrange = _reference_value(reference_trajectory, start_time_s, "downrange_m")
    total_distance = np.full_like(grid, initial_total_distance, dtype=float)
    downrange = np.full_like(grid, initial_downrange, dtype=float)
    for index in range(1, len(grid)):
        left = float(grid[index - 1])
        right = float(grid[index])
        distance_step = max(0.0, _integrate_scalar(velocity, left, right, config.integration_method))
        altitude_step = float(altitude_values[index] - altitude_values[index - 1])
        horizontal_step_sq = max(0.0, distance_step * distance_step - altitude_step * altitude_step)
        total_distance[index] = total_distance[index - 1] + distance_step
        downrange[index] = downrange[index - 1] + sqrt(horizontal_step_sq)

    latitude, longitude, coordinate_model = _trajectory_coordinates(config.launch_site, downrange)
    return pd.DataFrame(
        {
            "stage": stage,
            "mission_elapsed_time_s": grid,
            "velocity_mps": velocity_values,
            "altitude_m": altitude_values,
            "total_distance_m": total_distance,
            "downrange_m": downrange,
            "latitude_deg": latitude,
            "longitude_deg": longitude,
            "coordinate_model": coordinate_model,
            "interpolation_method": config.interpolation_method,
            "integration_method": config.integration_method,
            "integration_step_s": integration_step_s,
            "sample_fps": sample_fps,
        },
        columns=TRAJECTORY_COLUMNS,
    )


def _reference_value(reference_trajectory: pd.DataFrame | None, time_s: float, column: str) -> float:
    if reference_trajectory is None or reference_trajectory.empty or column not in reference_trajectory.columns:
        return 0.0
    times = reference_trajectory["mission_elapsed_time_s"].to_numpy(dtype=float)
    values = reference_trajectory[column].to_numpy(dtype=float)
    finite = np.isfinite(times) & np.isfinite(values)
    if np.count_nonzero(finite) < 2:
        return 0.0
    times = times[finite]
    values = values[finite]
    return float(np.interp(time_s, times, values, left=values[0], right=values[-1]))


def _signal_points(
    df: pd.DataFrame,
    time_column: str,
    value_column: str,
    *,
    include_liftoff_anchor: bool,
    coarse_threshold: float,
    coarse_max_gap_s: float,
    outlier_preconditioning_enabled: bool,
    smoothing_enabled: bool,
) -> tuple[np.ndarray, np.ndarray]:
    times = pd.to_numeric(df[time_column], errors="coerce").to_numpy(dtype=float)
    values = pd.to_numeric(df[value_column], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(times) & np.isfinite(values) & (times >= 0.0)
    times = times[finite]
    values = values[finite]
    if include_liftoff_anchor:
        positive = times > 0.0
        times = np.concatenate([np.array([0.0]), times[positive]])
        values = np.concatenate([np.array([0.0]), values[positive]])
    times, values = _dedupe_points(times, values)
    if outlier_preconditioning_enabled:
        protected_indices = (
            {0}
            if include_liftoff_anchor and times.size > 0 and np.isclose(times[0], 0.0)
            else set()
        )
        times, values = _remove_isolated_outliers(times, values, coarse_threshold, protected_indices)
    if smoothing_enabled:
        return _smooth_coarse_steps(times, values, coarse_threshold, coarse_max_gap_s)
    return times, values


def _dedupe_points(times: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if times.size == 0:
        return times, values
    points = pd.DataFrame({"time": times, "value": values})
    points = points[np.isfinite(points["time"]) & np.isfinite(points["value"])]
    if points.empty:
        return np.array([], dtype=float), np.array([], dtype=float)
    points = points.sort_values("time").drop_duplicates("time", keep="first")
    return points["time"].to_numpy(dtype=float), points["value"].to_numpy(dtype=float)


def _remove_isolated_outliers(
    times: np.ndarray,
    values: np.ndarray,
    residual_threshold: float,
    protected_indices: set[int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if times.size < 3 or residual_threshold <= 0 or not isfinite(residual_threshold):
        return times, values

    protected_indices = protected_indices or set()
    keep = np.ones(times.size, dtype=bool)
    max_iterations = 3
    for _ in range(max_iterations):
        kept_indices = np.flatnonzero(keep)
        if kept_indices.size < 3:
            break
        candidates: list[int] = []
        for local_index, original_index in enumerate(kept_indices):
            if original_index in protected_indices:
                continue
            if _is_isolated_outlier(
                int(local_index),
                times[kept_indices],
                values[kept_indices],
                residual_threshold,
            ):
                candidates.append(int(original_index))
        if not candidates:
            break
        keep[candidates] = False

    if np.all(keep):
        return times, values
    return times[keep], values[keep]


def _is_isolated_outlier(index: int, times: np.ndarray, values: np.ndarray, residual_threshold: float) -> bool:
    prediction = _predict_from_local_trend(index, times, values)
    if prediction is None:
        return False

    predicted_value, lower_bound, upper_bound, interior = prediction
    residual = abs(float(values[index]) - predicted_value)
    threshold = residual_threshold if interior else residual_threshold * 2.0
    if residual <= threshold:
        return False
    if interior and lower_bound - threshold <= values[index] <= upper_bound + threshold:
        return False
    return True


def _predict_from_local_trend(
    index: int,
    times: np.ndarray,
    values: np.ndarray,
) -> tuple[float, float, float, bool] | None:
    left_indices = np.flatnonzero(times < times[index])
    right_indices = np.flatnonzero(times > times[index])
    if left_indices.size > 0 and right_indices.size > 0:
        left = int(left_indices[-1])
        right = int(right_indices[0])
        predicted = _linear_prediction(
            times[index],
            times[left],
            values[left],
            times[right],
            values[right],
        )
        lower_bound = min(float(values[left]), float(values[right]))
        upper_bound = max(float(values[left]), float(values[right]))
        return predicted, lower_bound, upper_bound, True

    if right_indices.size >= 2:
        first = int(right_indices[0])
        second = int(right_indices[1])
        predicted = _linear_prediction(
            times[index],
            times[first],
            values[first],
            times[second],
            values[second],
        )
        lower_bound = min(float(values[first]), float(values[second]))
        upper_bound = max(float(values[first]), float(values[second]))
        return predicted, lower_bound, upper_bound, False

    if left_indices.size >= 2:
        first = int(left_indices[-2])
        second = int(left_indices[-1])
        predicted = _linear_prediction(
            times[index],
            times[first],
            values[first],
            times[second],
            values[second],
        )
        lower_bound = min(float(values[first]), float(values[second]))
        upper_bound = max(float(values[first]), float(values[second]))
        return predicted, lower_bound, upper_bound, False

    return None


def _linear_prediction(
    target_time: float,
    left_time: float,
    left_value: float,
    right_time: float,
    right_value: float,
) -> float:
    dt = float(right_time - left_time)
    if dt == 0.0:
        return float(left_value)
    fraction = float((target_time - left_time) / dt)
    return float(left_value + fraction * (right_value - left_value))


def _smooth_coarse_steps(
    times: np.ndarray,
    values: np.ndarray,
    threshold: float,
    max_gap_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    if times.size < 3 or threshold <= 0 or not isfinite(threshold):
        return times, values
    if max_gap_s <= 0 or not isfinite(max_gap_s):
        return times, values

    runs = _constant_runs(times, values, threshold)
    if len(runs) < 2:
        return times, values

    smoothed_times = [runs[0]["start_time"]]
    smoothed_values = [runs[0]["value"]]
    smoothed_any_transition = False
    for previous_run, current_run in zip(runs, runs[1:]):
        if _is_coarse_transition(previous_run, current_run, threshold, max_gap_s):
            transition_time = 0.5 * (previous_run["end_time"] + current_run["start_time"])
            smoothed_any_transition = True
        else:
            transition_time = current_run["start_time"]
        smoothed_times.append(float(transition_time))
        smoothed_values.append(float(current_run["value"]))
    if not smoothed_any_transition:
        return times, values
    if smoothed_times[-1] < runs[-1]["end_time"]:
        smoothed_times.append(float(runs[-1]["end_time"]))
        smoothed_values.append(float(runs[-1]["value"]))
    return _dedupe_points(np.array(smoothed_times, dtype=float), np.array(smoothed_values, dtype=float))


def _constant_runs(times: np.ndarray, values: np.ndarray, threshold: float) -> list[dict[str, float]]:
    tolerance = max(1e-9, threshold * 1e-3)
    runs: list[dict[str, float]] = []
    start = 0
    for index in range(1, len(values)):
        if abs(values[index] - values[start]) <= tolerance:
            continue
        runs.append(
            {
                "start_time": float(times[start]),
                "end_time": float(times[index - 1]),
                "value": float(np.median(values[start:index])),
                "length": float(index - start),
            }
        )
        start = index
    runs.append(
        {
            "start_time": float(times[start]),
            "end_time": float(times[-1]),
            "value": float(np.median(values[start:])),
            "length": float(len(values) - start),
        }
    )
    return runs


def _is_coarse_transition(
    previous_run: dict[str, float],
    current_run: dict[str, float],
    threshold: float,
    max_gap_s: float,
) -> bool:
    gap_s = current_run["start_time"] - previous_run["end_time"]
    if gap_s > max_gap_s:
        return False
    change = abs(current_run["value"] - previous_run["value"])
    if change < threshold:
        return False
    return previous_run["length"] > 1 or current_run["length"] > 1


def _make_interpolator(times: np.ndarray, values: np.ndarray, method: str) -> ScalarFunction:
    if method == "linear" or times.size < 3:
        interpolator = interp1d(times, values, kind="linear", bounds_error=True)
    elif method == "pchip":
        interpolator = PchipInterpolator(times, values, extrapolate=False)
    elif method == "akima":
        interpolator = Akima1DInterpolator(times, values, extrapolate=False)
    elif method == "cubic":
        interpolator = CubicSpline(times, values, bc_type="natural", extrapolate=False)
    else:
        raise ValueError(f"Unsupported interpolation method: {method}")

    def evaluate(time_s: float) -> float:
        value = float(interpolator(time_s))
        if not np.isfinite(value):
            raise ValueError(f"Interpolation produced a non-finite value at MET {time_s:.3f}s")
        return value

    return evaluate


def _fixed_time_grid(start_time_s: float, end_time_s: float, step_s: float) -> np.ndarray:
    grid = np.arange(start_time_s, end_time_s, step_s, dtype=float)
    if grid.size == 0 or not np.isclose(grid[0], start_time_s):
        grid = np.insert(grid, 0, start_time_s)
    if not np.isclose(grid[-1], end_time_s):
        grid = np.append(grid, end_time_s)
    return grid


def _integrate_scalar(function: ScalarFunction, left: float, right: float, method: str) -> float:
    dt = right - left
    if dt <= 0:
        return 0.0
    midpoint = left + 0.5 * dt
    if method == "euler":
        return function(left) * dt
    if method == "midpoint":
        return function(midpoint) * dt
    if method == "trapezoid":
        return 0.5 * (function(left) + function(right)) * dt
    if method == "rk4":
        return (function(left) + 4.0 * function(midpoint) + function(right)) * dt / 6.0
    raise ValueError(f"Unsupported integration method: {method}")


def _append_stage_trajectory_columns(
    clean_df: pd.DataFrame,
    stage: str,
    stage_trajectory: pd.DataFrame,
) -> None:
    met = pd.to_numeric(clean_df["mission_elapsed_time_s"], errors="coerce").to_numpy(dtype=float)
    finite_time = np.isfinite(met)
    trajectory_time = stage_trajectory["mission_elapsed_time_s"].to_numpy(dtype=float)
    in_range = finite_time & (met >= trajectory_time[0]) & (met <= trajectory_time[-1])
    for source_column, target_suffix in [
        ("total_distance_m", "total_distance_m"),
        ("downrange_m", "downrange_m"),
        ("latitude_deg", "latitude_deg"),
        ("longitude_deg", "longitude_deg"),
    ]:
        target_column = f"{stage}_{target_suffix}"
        values = stage_trajectory[source_column].to_numpy(dtype=float)
        if np.all(~np.isfinite(values)):
            continue
        clean_df.loc[in_range, target_column] = np.interp(met[in_range], trajectory_time, values)


def _trajectory_coordinates(
    launch_site: LaunchSiteConfig,
    downrange_m: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, str]:
    if not _launch_site_is_complete(launch_site):
        return (
            np.full_like(downrange_m, np.nan, dtype=float),
            np.full_like(downrange_m, np.nan, dtype=float),
            "flat",
        )

    latitude = np.empty_like(downrange_m, dtype=float)
    longitude = np.empty_like(downrange_m, dtype=float)
    for index, distance_m in enumerate(downrange_m):
        latitude[index], longitude[index] = _wgs84_direct(
            latitude_deg=float(launch_site.latitude_deg),
            longitude_deg=float(launch_site.longitude_deg),
            azimuth_deg=float(launch_site.azimuth_deg),
            distance_m=float(distance_m),
        )
    return latitude, longitude, "wgs84"


def _launch_site_is_complete(launch_site: LaunchSiteConfig) -> bool:
    values = (launch_site.latitude_deg, launch_site.longitude_deg, launch_site.azimuth_deg)
    return all(value is not None and isfinite(float(value)) for value in values)


def _wgs84_direct(
    *,
    latitude_deg: float,
    longitude_deg: float,
    azimuth_deg: float,
    distance_m: float,
) -> tuple[float, float]:
    if distance_m == 0.0:
        return latitude_deg, _normalize_longitude(longitude_deg)

    alpha1 = radians(azimuth_deg)
    phi1 = radians(latitude_deg)
    lambda1 = radians(longitude_deg)
    sin_alpha1 = sin(alpha1)
    cos_alpha1 = cos(alpha1)
    tan_u1 = (1 - WGS84_F) * tan(phi1)
    cos_u1 = 1.0 / sqrt(1.0 + tan_u1 * tan_u1)
    sin_u1 = tan_u1 * cos_u1
    sigma1 = atan2(tan_u1, cos_alpha1)
    sin_alpha = cos_u1 * sin_alpha1
    cos2_alpha = 1.0 - sin_alpha * sin_alpha
    u_sq = cos2_alpha * (WGS84_A_M * WGS84_A_M - WGS84_B_M * WGS84_B_M) / (WGS84_B_M * WGS84_B_M)
    a_coeff = 1.0 + (u_sq / 16384.0) * (
        4096.0 + u_sq * (-768.0 + u_sq * (320.0 - 175.0 * u_sq))
    )
    b_coeff = (u_sq / 1024.0) * (
        256.0 + u_sq * (-128.0 + u_sq * (74.0 - 47.0 * u_sq))
    )

    sigma = distance_m / (WGS84_B_M * a_coeff)
    for _ in range(100):
        two_sigma_m = 2.0 * sigma1 + sigma
        sin_sigma = sin(sigma)
        cos_sigma = cos(sigma)
        cos_two_sigma_m = cos(two_sigma_m)
        delta_sigma = b_coeff * sin_sigma * (
            cos_two_sigma_m
            + (b_coeff / 4.0)
            * (
                cos_sigma * (-1.0 + 2.0 * cos_two_sigma_m * cos_two_sigma_m)
                - (b_coeff / 6.0)
                * cos_two_sigma_m
                * (-3.0 + 4.0 * sin_sigma * sin_sigma)
                * (-3.0 + 4.0 * cos_two_sigma_m * cos_two_sigma_m)
            )
        )
        next_sigma = distance_m / (WGS84_B_M * a_coeff) + delta_sigma
        if abs(next_sigma - sigma) < 1e-12:
            sigma = next_sigma
            break
        sigma = next_sigma

    sin_sigma = sin(sigma)
    cos_sigma = cos(sigma)
    two_sigma_m = 2.0 * sigma1 + sigma
    cos_two_sigma_m = cos(two_sigma_m)
    tmp = sin_u1 * sin_sigma - cos_u1 * cos_sigma * cos_alpha1
    phi2 = atan2(
        sin_u1 * cos_sigma + cos_u1 * sin_sigma * cos_alpha1,
        (1.0 - WGS84_F) * sqrt(sin_alpha * sin_alpha + tmp * tmp),
    )
    lambda_delta = atan2(
        sin_sigma * sin_alpha1,
        cos_u1 * cos_sigma - sin_u1 * sin_sigma * cos_alpha1,
    )
    c_coeff = (WGS84_F / 16.0) * cos2_alpha * (4.0 + WGS84_F * (4.0 - 3.0 * cos2_alpha))
    longitude_correction = (1.0 - c_coeff) * WGS84_F * sin_alpha * (
        sigma
        + c_coeff
        * sin_sigma
        * (
            cos_two_sigma_m
            + c_coeff * cos_sigma * (-1.0 + 2.0 * cos_two_sigma_m * cos_two_sigma_m)
        )
    )
    lambda2 = lambda1 + lambda_delta - longitude_correction
    return degrees(phi2), _normalize_longitude(degrees(lambda2))


def _normalize_longitude(longitude_deg: float) -> float:
    return ((longitude_deg + 540.0) % 360.0) - 180.0
