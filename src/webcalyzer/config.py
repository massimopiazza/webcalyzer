from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from webcalyzer.models import (
    Box,
    FieldConfig,
    FieldKindParsing,
    HardcodedRawDataPoint,
    LaunchSiteConfig,
    MetParsing,
    ParsingProfile,
    ProfileConfig,
    TrajectoryConfig,
    UnitAlias,
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
    return ProfileConfig(
        profile_name=data["profile_name"],
        description=data.get("description", ""),
        default_sample_fps=float(data.get("default_sample_fps", 3.0)),
        fixture_frame_count=int(data.get("fixture_frame_count", 20)),
        fixture_time_range_s=_load_fixture_time_range(data),
        video_overlay=_load_video_overlay(data.get("video_overlay", {})),
        trajectory=_load_trajectory(data.get("trajectory", {})),
        parsing=_load_parsing(data.get("parsing")),
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
        height_fraction=float(data.get("height_fraction", 0.55)),
        output_filename=str(data.get("output_filename", "telemetry_overlay.mp4")),
        include_audio=bool(data.get("include_audio", True)),
    )


def _load_trajectory(data: dict[str, Any] | None) -> TrajectoryConfig:
    data = data or {}
    launch_site_data = data.get("launch_site") or {}
    # `integration_step_s` is deliberately ignored: integration now uses the
    # OCR sample period so the trajectory grid stays consistent with the
    # input cadence. We accept it silently for backward compatibility.
    return TrajectoryConfig(
        enabled=bool(data.get("enabled", True)),
        interpolation_method=str(data.get("interpolation_method", "pchip")),
        integration_method=str(data.get("integration_method", "rk4")),
        outlier_preconditioning_enabled=bool(data.get("outlier_preconditioning_enabled", True)),
        coarse_step_smoothing_enabled=bool(data.get("coarse_step_smoothing_enabled", True)),
        coarse_step_max_gap_s=float(data.get("coarse_step_max_gap_s", 10.0)),
        coarse_altitude_threshold_m=float(data.get("coarse_altitude_threshold_m", 500.0)),
        coarse_velocity_threshold_mps=float(data.get("coarse_velocity_threshold_mps", 50.0)),
        acceleration_source_gap_threshold_s=float(data.get("acceleration_source_gap_threshold_s", 10.0)),
        derivative_smoothing_window_s=float(data.get("derivative_smoothing_window_s", 20.0)),
        derivative_smoothing_polyorder=int(data.get("derivative_smoothing_polyorder", 3)),
        derivative_min_window_samples=int(data.get("derivative_min_window_samples", 5)),
        derivative_smoothing_mode=str(data.get("derivative_smoothing_mode", "interp")),
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


_DEFAULT_VELOCITY_UNITS: tuple[UnitAlias, ...] = (
    UnitAlias(name="MPH", aliases=("MPH", "MPN", "MРН", "MPI", "M/H"), si_factor=0.44704),
    UnitAlias(name="KPH", aliases=("KPH", "KMH", "KM/H", "KMPH"), si_factor=0.27777777777777778),
    UnitAlias(name="MPS", aliases=("M/S", "MPS", "MS"), si_factor=1.0),
)
_DEFAULT_ALTITUDE_UNITS: tuple[UnitAlias, ...] = (
    UnitAlias(name="FT", aliases=("FT", "F7", "FI", "ET", "E7", "EI"), si_factor=0.3048),
    UnitAlias(name="MI", aliases=("MI", "ML", "M1"), si_factor=1609.344),
    UnitAlias(name="KM", aliases=("KM",), si_factor=1000.0),
    UnitAlias(name="M", aliases=("M",), si_factor=1.0),
)
_DEFAULT_MET_PATTERNS: tuple[str, ...] = (
    r"T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",
    r"([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?",
)
_BASE_CUSTOM_WORDS: tuple[str, ...] = ("STAGE", "VELOCITY", "ALTITUDE", "T+", "T-")


def default_parsing_profile() -> ParsingProfile:
    """Return the parsing profile baked-in for legacy YAMLs without a `parsing` block."""

    velocity = FieldKindParsing(
        units=_DEFAULT_VELOCITY_UNITS,
        default_unit="MPH",
        inferred_units_with_separator=("MPH",),
        inferred_units_without_separator=("MPH",),
    )
    altitude = FieldKindParsing(
        units=_DEFAULT_ALTITUDE_UNITS,
        default_unit="FT",
        ambiguous_default_unit="FT",
        inferred_units_with_separator=("FT", "MI"),
        inferred_units_without_separator=("FT",),
    )
    met = MetParsing(timestamp_patterns=_DEFAULT_MET_PATTERNS)
    return ParsingProfile(
        velocity=velocity,
        altitude=altitude,
        met=met,
        custom_words=_derive_custom_words(velocity, altitude),
    )


def _derive_custom_words(velocity: FieldKindParsing, altitude: FieldKindParsing) -> tuple[str, ...]:
    seen: list[str] = []
    for word in _BASE_CUSTOM_WORDS:
        if word not in seen:
            seen.append(word)
    for parsing in (velocity, altitude):
        for unit in parsing.units:
            for alias in unit.aliases:
                upper = alias.upper().strip()
                if upper and upper not in seen:
                    seen.append(upper)
    return tuple(seen)


def _load_parsing(data: dict[str, Any] | None) -> ParsingProfile:
    if not data:
        return default_parsing_profile()

    velocity = _load_field_kind_parsing(
        data.get("velocity"),
        defaults=_DEFAULT_VELOCITY_UNITS,
        default_unit="MPH",
        inferred_units_with_separator=("MPH",),
        inferred_units_without_separator=("MPH",),
    )
    altitude = _load_field_kind_parsing(
        data.get("altitude"),
        defaults=_DEFAULT_ALTITUDE_UNITS,
        default_unit="FT",
        ambiguous_default_unit="FT",
        inferred_units_with_separator=("FT", "MI"),
        inferred_units_without_separator=("FT",),
    )
    met_data = data.get("met") or {}
    patterns_raw = met_data.get("timestamp_patterns") or list(_DEFAULT_MET_PATTERNS)
    if not isinstance(patterns_raw, (list, tuple)) or not patterns_raw:
        raise ValueError("parsing.met.timestamp_patterns must be a non-empty list of regex strings")
    met = MetParsing(timestamp_patterns=tuple(str(pattern) for pattern in patterns_raw))

    custom_words_raw = data.get("custom_words")
    if custom_words_raw is None:
        custom_words = _derive_custom_words(velocity, altitude)
    else:
        if not isinstance(custom_words_raw, (list, tuple)):
            raise ValueError("parsing.custom_words must be a list of strings")
        custom_words = tuple(str(word).upper() for word in custom_words_raw if str(word).strip())
    return ParsingProfile(
        velocity=velocity,
        altitude=altitude,
        met=met,
        custom_words=custom_words,
    )


def _load_field_kind_parsing(
    data: dict[str, Any] | None,
    *,
    defaults: tuple[UnitAlias, ...],
    default_unit: str,
    ambiguous_default_unit: str | None = None,
    inferred_units_with_separator: tuple[str, ...] = (),
    inferred_units_without_separator: tuple[str, ...] = (),
) -> FieldKindParsing:
    if not data:
        return FieldKindParsing(
            units=defaults,
            default_unit=default_unit,
            ambiguous_default_unit=ambiguous_default_unit,
            inferred_units_with_separator=inferred_units_with_separator,
            inferred_units_without_separator=inferred_units_without_separator,
        )
    units_raw = data.get("units")
    if units_raw is None:
        units = defaults
    else:
        if not isinstance(units_raw, dict) or not units_raw:
            raise ValueError("parsing.<kind>.units must be a non-empty mapping")
        units = tuple(_load_unit_alias(name, body) for name, body in units_raw.items())

    def _string_tuple(value: Any, fallback: tuple[str, ...]) -> tuple[str, ...]:
        if value is None:
            return fallback
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            raise ValueError("inferred_units_* must be a list of strings")
        return tuple(str(item).upper() for item in value if str(item).strip())

    return FieldKindParsing(
        units=units,
        default_unit=str(data.get("default_unit", default_unit)).upper(),
        ambiguous_default_unit=(
            None
            if data.get("ambiguous_default_unit", ambiguous_default_unit) is None
            else str(data.get("ambiguous_default_unit", ambiguous_default_unit)).upper()
        ),
        inferred_units_with_separator=_string_tuple(
            data.get("inferred_units_with_separator"), inferred_units_with_separator
        ),
        inferred_units_without_separator=_string_tuple(
            data.get("inferred_units_without_separator"), inferred_units_without_separator
        ),
    )


def _load_unit_alias(name: str, body: dict[str, Any]) -> UnitAlias:
    if not isinstance(body, dict):
        raise ValueError(f"parsing unit {name!r} must be a mapping")
    aliases_raw = body.get("aliases", [name])
    if isinstance(aliases_raw, str):
        aliases_raw = [aliases_raw]
    if not isinstance(aliases_raw, (list, tuple)) or not aliases_raw:
        raise ValueError(f"parsing unit {name!r} aliases must be a non-empty list")
    si_factor_raw = body.get("si_factor")
    if si_factor_raw is None:
        raise ValueError(f"parsing unit {name!r} must define si_factor")
    return UnitAlias(
        name=str(name).upper(),
        aliases=tuple(str(alias).upper() for alias in aliases_raw),
        si_factor=float(si_factor_raw),
    )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
