from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from webcalyzer.models import (
    Box,
    CalibrationSegmentConfig,
    CalibrationVideoConfig,
    CANONICAL_FIELD_ORDER,
    FieldConfig,
    FieldKindParsing,
    HardcodedRawDataPoint,
    LaunchSiteConfig,
    MetParsing,
    ParsingProfile,
    ProfileConfig,
    TelemetryQuantityDefinition,
    TrajectoryConfig,
    UnitAlias,
    VideoOverlayConfig,
)
from webcalyzer.dimensions import normalize_dimension_expression
from webcalyzer.quantities import make_quantity_slug
from webcalyzer.units import validate_unit_compatible_with_dimension


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
    return ProfileConfig(
        profile_name=data["profile_name"],
        description=data.get("description", ""),
        default_sample_fps=float(data.get("default_sample_fps", 3.0)),
        default_ocr_workers=int(data.get("default_ocr_workers", data.get("ocr_workers", 0))),
        ocr_backend=str(data.get("ocr_backend", "auto")),
        ocr_recognition_level=str(data.get("ocr_recognition_level", "accurate")),
        skip_full_frame_ocr_fallback=bool(
            data.get(
                "skip_full_frame_ocr_fallback",
                data.get("ocr_skip_detection", False),
            )
        ),
        fixture_frame_count=int(data.get("fixture_frame_count", 20)),
        fixture_time_range_s=_load_fixture_time_range(data),
        calibration_video=_load_calibration_video(data.get("calibration_video")),
        video_overlay=_load_video_overlay(data.get("video_overlay", {})),
        trajectory=_load_trajectory(data.get("trajectory", {})),
        parsing=_load_parsing(data.get("parsing")),
        custom_telemetry_quantities=_load_custom_quantities(data.get("custom_telemetry_quantities")),
        hardcoded_raw_data_points=_load_hardcoded_raw_data_points(data),
        segments=_load_segments(data),
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
    for segment_data in data.get("segments", []):
        for field_data in segment_data.get("fields", {}).values():
            bbox = field_data.get("bbox_x1y1x2y2")
            if isinstance(bbox, list):
                field_data["bbox_x1y1x2y2"] = _FlowList(bbox)
    return data


def _load_field(name: str, field_data: dict[str, Any]) -> FieldConfig:
    return FieldConfig(
        name=name,
        kind=field_data["kind"],
        stage=field_data.get("stage"),
        box=_load_box(field_data),
        quantity_id=field_data.get("quantity_id"),
    )


def _load_box(field_data: dict[str, Any]) -> Box | None:
    bbox = _load_bbox(field_data)
    if bbox is None:
        return None
    return Box.from_sequence(bbox)


def _load_bbox(field_data: dict[str, Any]) -> list[float] | None:
    if "bbox_x1y1x2y2" in field_data:
        return field_data["bbox_x1y1x2y2"]
    return field_data.get("box")


def _load_calibration_video(data: dict[str, Any] | None) -> CalibrationVideoConfig:
    data = data or {}
    return CalibrationVideoConfig(
        path=None if data.get("path") in (None, "") else str(data.get("path")),
        fps=_optional_float(data.get("fps")),
        frame_count=_optional_int(data.get("frame_count")),
        width=_optional_int(data.get("width")),
        height=_optional_int(data.get("height")),
    )


def _load_segments(data: dict[str, Any]) -> list[CalibrationSegmentConfig]:
    segments_data = data.get("segments")
    if segments_data is None:
        legacy_fields = data.get("fields") or {}
        if not legacy_fields:
            return []
        calibration_video = _load_calibration_video(data.get("calibration_video"))
        end_frame = int(calibration_video.frame_count or 0)
        end_time = _derive_time_s(end_frame, calibration_video.fps)
        fields = _load_fields(legacy_fields)
        return [
            CalibrationSegmentConfig(
                id="segment_1",
                start_frame_index=0,
                start_time_s=0.0,
                end_frame_index=end_frame,
                end_time_s=end_time,
                visible_fields=list(fields.keys()),
                fields=fields,
            )
        ]
    if not isinstance(segments_data, list):
        raise ValueError("segments must be a list")
    return [
        _load_segment(index=index, data=segment_data, calibration_video=_load_calibration_video(data.get("calibration_video")))
        for index, segment_data in enumerate(segments_data, start=1)
    ]


def _load_segment(
    *,
    index: int,
    data: dict[str, Any],
    calibration_video: CalibrationVideoConfig,
) -> CalibrationSegmentConfig:
    if not isinstance(data, dict):
        raise ValueError("Each segment must be a mapping")
    start_frame = int(data.get("start_frame_index", 0))
    end_frame = int(data.get("end_frame_index", start_frame))
    start_time = float(data.get("start_time_s", _derive_time_s(start_frame, calibration_video.fps)))
    end_time = float(data.get("end_time_s", _derive_time_s(end_frame, calibration_video.fps)))
    fields_data = data.get("fields") or {}
    if not isinstance(fields_data, dict):
        raise ValueError("segment.fields must be a mapping")
    fields = _load_fields(fields_data)
    visible_data = data.get("visible_fields")
    visible_fields = (
        [str(name) for name in visible_data]
        if isinstance(visible_data, list)
        else list(fields.keys())
    )
    return CalibrationSegmentConfig(
        id=str(data.get("id") or f"segment_{index}"),
        start_frame_index=start_frame,
        start_time_s=start_time,
        end_frame_index=end_frame,
        end_time_s=end_time,
        visible_fields=visible_fields,
        fields=fields,
    )


def _load_fields(fields_data: dict[str, Any]) -> dict[str, FieldConfig]:
    return {
        name: _load_field(name, fields_data[name])
        for name in CANONICAL_FIELD_ORDER
        if name in fields_data
    } | {
        name: _load_field(name, field_data)
        for name, field_data in fields_data.items()
        if name not in CANONICAL_FIELD_ORDER
    }


def _derive_time_s(frame_index: int, fps: float | None) -> float:
    if fps is None or fps <= 0.0:
        return 0.0
    return float(frame_index) / float(fps)


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
    custom_values_raw = point_data.get("custom_values", {}) or {}
    if not isinstance(custom_values_raw, dict):
        raise ValueError("hardcoded raw custom_values must be a mapping")
    custom_values = {
        str(name): float(value)
        for name, value in custom_values_raw.items()
        if value is not None and value != ""
    }

    if all(value is None for value in values.values()) and not custom_values:
        raise ValueError("Each hardcoded raw data point must define at least one telemetry value")

    return HardcodedRawDataPoint(
        mission_elapsed_time_s=float(mission_elapsed_time_s),
        stage1_velocity_mps=values["stage1_velocity_mps"],
        stage1_altitude_m=values["stage1_altitude_m"],
        stage2_velocity_mps=values["stage2_velocity_mps"],
        stage2_altitude_m=values["stage2_altitude_m"],
        custom_values=custom_values,
    )


def _load_video_overlay(data: dict[str, Any] | None) -> VideoOverlayConfig:
    data = data or {}
    return VideoOverlayConfig(
        enabled=bool(data.get("enabled", True)),
        plot_mode=str(data.get("plot_mode", "filtered")),
        engine=str(data.get("engine", data.get("overlay_engine", "auto"))),
        encoder=str(data.get("encoder", data.get("overlay_encoder", "auto"))),
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
    UnitAlias(name="MPH", aliases=("MPH", "MPN", "MРН", "MPI", "M/H"), unit_expression="mile/hour"),
    UnitAlias(name="KPH", aliases=("KPH", "KMH", "KM/H", "KMPH"), unit_expression="kilometer/hour"),
    UnitAlias(name="MPS", aliases=("M/S", "MPS", "MS"), unit_expression="meter/second"),
    UnitAlias(name="KPS", aliases=("KM/S", "KPS"), unit_expression="kilometer/second"),
)
_DEFAULT_ALTITUDE_UNITS: tuple[UnitAlias, ...] = (
    UnitAlias(name="FT", aliases=("FT", "F7", "FI", "ET", "E7", "EI"), unit_expression="foot"),
    UnitAlias(name="MI", aliases=("MI", "ML", "M1"), unit_expression="mile"),
    UnitAlias(name="KM", aliases=("KM",), unit_expression="kilometer"),
    UnitAlias(name="M", aliases=("M",), unit_expression="meter"),
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
        output_unit="meter/second",
    )
    altitude = FieldKindParsing(
        units=_DEFAULT_ALTITUDE_UNITS,
        default_unit="FT",
        ambiguous_default_unit="FT",
        inferred_units_with_separator=("FT", "MI"),
        inferred_units_without_separator=("FT",),
        output_unit="meter",
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
        output_unit="meter/second",
    )
    altitude = _load_field_kind_parsing(
        data.get("altitude"),
        defaults=_DEFAULT_ALTITUDE_UNITS,
        default_unit="FT",
        ambiguous_default_unit="FT",
        inferred_units_with_separator=("FT", "MI"),
        inferred_units_without_separator=("FT",),
        output_unit="meter",
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
    output_unit: str | None = None,
) -> FieldKindParsing:
    if not data:
        return FieldKindParsing(
            units=defaults,
            default_unit=default_unit,
            ambiguous_default_unit=ambiguous_default_unit,
            inferred_units_with_separator=inferred_units_with_separator,
            inferred_units_without_separator=inferred_units_without_separator,
            output_unit=output_unit or _output_unit_for_default(default_unit),
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
        output_unit=str(data.get("output_unit", output_unit or _output_unit_for_default(default_unit))),
    )


def _load_unit_alias(name: str, body: dict[str, Any]) -> UnitAlias:
    if not isinstance(body, dict):
        raise ValueError(f"parsing unit {name!r} must be a mapping")
    aliases_raw = body.get("aliases", [name])
    if isinstance(aliases_raw, str):
        aliases_raw = [aliases_raw]
    if not isinstance(aliases_raw, (list, tuple)) or not aliases_raw:
        raise ValueError(f"parsing unit {name!r} aliases must be a non-empty list")
    unit_expression = body.get("unit")
    if unit_expression is None:
        si_factor_raw = body.get("si_factor")
        if si_factor_raw is None:
            raise ValueError(f"parsing unit {name!r} must define unit")
        unit_expression = _legacy_unit_expression(str(name).upper(), float(si_factor_raw))
    return UnitAlias(
        name=str(name).upper(),
        aliases=tuple(str(alias).upper() for alias in aliases_raw),
        unit_expression=str(unit_expression),
    )


def _load_custom_quantities(data: Any) -> list[TelemetryQuantityDefinition]:
    if not data:
        return []
    if not isinstance(data, list):
        raise ValueError("custom_telemetry_quantities must be a list")
    quantities = [_load_custom_quantity(item) for item in data]
    names: set[str] = set()
    slugs: set[str] = set()
    ids: set[str] = set()
    for quantity in quantities:
        lowered = quantity.name.casefold()
        if lowered in names:
            raise ValueError(f"Duplicate custom quantity name {quantity.name!r}")
        if quantity.slug in slugs:
            raise ValueError(f"Duplicate custom quantity slug {quantity.slug!r}")
        if quantity.id in ids:
            raise ValueError(f"Duplicate custom quantity id {quantity.id!r}")
        names.add(lowered)
        slugs.add(quantity.slug)
        ids.add(quantity.id)
    return quantities


def _load_custom_quantity(data: Any) -> TelemetryQuantityDefinition:
    if not isinstance(data, dict):
        raise ValueError("Each custom telemetry quantity must be a mapping")
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("custom telemetry quantity name is required")
    dimensionality = normalize_dimension_expression(str(data.get("dimensionality", "")).strip())
    display_unit = str(data.get("display_unit", "")).strip()
    if not display_unit:
        raise ValueError(f"custom telemetry quantity {name!r} must define display_unit")
    validate_unit_compatible_with_dimension(display_unit, dimensionality)
    aliases = data.get("unit_aliases", {}) or {}
    if not isinstance(aliases, dict):
        raise ValueError(f"custom telemetry quantity {name!r} unit_aliases must be a mapping")
    slug = make_quantity_slug(str(data.get("slug", "") or name))
    quantity_id = str(data.get("id", "")).strip()
    if not quantity_id:
        quantity_id = f"q_{slug}"
    return TelemetryQuantityDefinition(
        id=quantity_id,
        name=name,
        slug=slug,
        dimensionality=dimensionality,
        display_unit=display_unit,
        description=str(data.get("description", "") or ""),
        unit_aliases={str(alias): str(unit) for alias, unit in aliases.items()},
    )


def _output_unit_for_default(default_unit: str) -> str:
    if default_unit.upper() in {"MPH", "KPH", "MPS", "KPS"}:
        return "meter/second"
    if default_unit.upper() in {"FT", "MI", "KM", "M"}:
        return "meter"
    return "dimensionless"


def _legacy_unit_expression(name: str, si_factor: float) -> str:
    known = {
        "MPH": "mile/hour",
        "KPH": "kilometer/hour",
        "MPS": "meter/second",
        "KPS": "kilometer/second",
        "FT": "foot",
        "MI": "mile",
        "KM": "kilometer",
        "M": "meter",
    }
    if name in known:
        return known[name]
    return f"{si_factor:.17g} * dimensionless"


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
