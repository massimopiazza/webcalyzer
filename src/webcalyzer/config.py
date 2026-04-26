from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from webcalyzer.models import (
    Box,
    FieldConfig,
    HardcodedRawDataPoint,
    LaunchSiteConfig,
    ProfileConfig,
    TrajectoryConfig,
    VideoOverlayConfig,
)


class _FlowList(list):
    pass


class _ProfileDumper(yaml.SafeDumper):
    pass


def _represent_flow_list(dumper: yaml.Dumper, data: _FlowList) -> yaml.SequenceNode:
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


_ProfileDumper.add_representer(_FlowList, _represent_flow_list)


def load_profile(path: str | Path) -> ProfileConfig:
    profile_path = Path(path)
    data = yaml.safe_load(profile_path.read_text())
    fields = {
        name: FieldConfig(
            name=name,
            kind=field_data["kind"],
            stage=field_data.get("stage"),
            box=Box.from_sequence(_load_bbox(field_data)),
        )
        for name, field_data in data["fields"].items()
    }
    reference_resolution = data["reference_resolution"]
    return ProfileConfig(
        profile_name=data["profile_name"],
        description=data.get("description", ""),
        reference_width=int(reference_resolution["width"]),
        reference_height=int(reference_resolution["height"]),
        default_sample_fps=float(data.get("default_sample_fps", 3.0)),
        fixture_frame_count=int(data.get("fixture_frame_count", 20)),
        fixture_time_range_s=_load_fixture_time_range(data),
        video_overlay=_load_video_overlay(data.get("video_overlay", {})),
        trajectory=_load_trajectory(data.get("trajectory", {})),
        hardcoded_raw_data_points=_load_hardcoded_raw_data_points(data),
        fields=fields,
    )


def save_profile(profile: ProfileConfig, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.dump(_profile_to_yaml_dict(profile), Dumper=_ProfileDumper, sort_keys=False, width=1000))
    return target


def _profile_to_yaml_dict(profile: ProfileConfig) -> dict[str, Any]:
    data = profile.to_dict()
    fixture_time_range = data.get("fixture_time_range_s")
    if isinstance(fixture_time_range, list):
        data["fixture_time_range_s"] = _FlowList(fixture_time_range)
    for field_data in data.get("fields", {}).values():
        bbox = field_data.get("bbox_x1y1x2y2")
        if isinstance(bbox, list):
            field_data["bbox_x1y1x2y2"] = _FlowList(bbox)
    return data


def _load_bbox(field_data: dict[str, Any]) -> list[float]:
    if "bbox_x1y1x2y2" in field_data:
        return field_data["bbox_x1y1x2y2"]
    return field_data["box"]


def _load_fixture_time_range(data: dict[str, Any]) -> tuple[float, float] | None:
    range_data = data.get("fixture_time_range_s")
    if isinstance(range_data, dict):
        start = range_data.get("start", range_data.get("lower"))
        end = range_data.get("end", range_data.get("upper"))
        if start is None or end is None:
            return None
        return (float(start), float(end))
    if isinstance(range_data, (list, tuple)) and len(range_data) == 2:
        return (float(range_data[0]), float(range_data[1]))

    reference_times = [float(value) for value in data.get("fixture_reference_times_s", [])]
    if reference_times:
        return (min(reference_times), max(reference_times))
    return None


def _load_hardcoded_raw_data_points(data: dict[str, Any]) -> list[HardcodedRawDataPoint]:
    raw_points = data.get("hardcoded_raw_data_points", data.get("hardcoded_raw_points", [])) or []
    if not isinstance(raw_points, list):
        raise ValueError("hardcoded_raw_data_points must be a list")
    return [_load_hardcoded_raw_data_point(point_data) for point_data in raw_points]


def _load_hardcoded_raw_data_point(point_data: dict[str, Any]) -> HardcodedRawDataPoint:
    if not isinstance(point_data, dict):
        raise ValueError("Each hardcoded raw data point must be a mapping")

    mission_elapsed_time_s = point_data.get(
        "mission_elapsed_time_s",
        point_data.get("met_s", point_data.get("timestamp_s")),
    )
    if mission_elapsed_time_s is None:
        raise ValueError("Each hardcoded raw data point must define mission_elapsed_time_s")

    values: dict[str, float | None] = {}
    for stage in ("stage1", "stage2"):
        stage_data = point_data.get(stage, {}) or {}
        if not isinstance(stage_data, dict):
            raise ValueError(f"{stage} hardcoded raw data must be a mapping")
        values[f"{stage}_velocity_mps"] = _optional_float(
            point_data.get(f"{stage}_velocity_mps", stage_data.get("velocity_mps", stage_data.get("velocity")))
        )
        values[f"{stage}_altitude_m"] = _optional_float(
            point_data.get(f"{stage}_altitude_m", stage_data.get("altitude_m", stage_data.get("altitude")))
        )

    if all(value is None for value in values.values()):
        raise ValueError("Each hardcoded raw data point must define at least one telemetry value")

    return HardcodedRawDataPoint(
        mission_elapsed_time_s=float(mission_elapsed_time_s),
        stage1_velocity_mps=values["stage1_velocity_mps"],
        stage1_altitude_m=values["stage1_altitude_m"],
        stage2_velocity_mps=values["stage2_velocity_mps"],
        stage2_altitude_m=values["stage2_altitude_m"],
    )


def _load_video_overlay(data: dict[str, Any] | None) -> VideoOverlayConfig:
    data = data or {}
    return VideoOverlayConfig(
        enabled=bool(data.get("enabled", True)),
        plot_mode=str(data.get("plot_mode", "filtered")),
        width_fraction=float(data.get("width_fraction", 0.5)),
        height_fraction=float(data.get("height_fraction", 0.4)),
        output_filename=str(data.get("output_filename", "telemetry_overlay.mp4")),
        include_audio=bool(data.get("include_audio", True)),
    )


def _load_trajectory(data: dict[str, Any] | None) -> TrajectoryConfig:
    data = data or {}
    launch_site_data = data.get("launch_site") or {}
    return TrajectoryConfig(
        enabled=bool(data.get("enabled", True)),
        interpolation_method=str(data.get("interpolation_method", "pchip")),
        integration_method=str(data.get("integration_method", "rk4")),
        integration_step_s=float(data.get("integration_step_s", 0.25)),
        outlier_preconditioning_enabled=bool(data.get("outlier_preconditioning_enabled", True)),
        coarse_step_smoothing_enabled=bool(data.get("coarse_step_smoothing_enabled", True)),
        coarse_step_max_gap_s=float(data.get("coarse_step_max_gap_s", 10.0)),
        coarse_altitude_threshold_m=float(data.get("coarse_altitude_threshold_m", 500.0)),
        coarse_velocity_threshold_mps=float(data.get("coarse_velocity_threshold_mps", 50.0)),
        launch_site=LaunchSiteConfig(
            latitude_deg=_optional_float(
                launch_site_data.get("latitude_deg", data.get("launch_latitude_deg"))
            ),
            longitude_deg=_optional_float(
                launch_site_data.get("longitude_deg", data.get("launch_longitude_deg"))
            ),
            azimuth_deg=_optional_float(
                launch_site_data.get("azimuth_deg", data.get("launch_azimuth_deg"))
            ),
        ),
    )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
