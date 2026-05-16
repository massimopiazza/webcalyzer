from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from webcalyzer.config import default_parsing_profile
from webcalyzer.models import (
    Box,
    CalibrationSegmentConfig,
    CalibrationVideoConfig,
    CANONICAL_FIELD_DEFINITIONS,
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
from webcalyzer.trajectory import INTEGRATION_METHODS, INTERPOLATION_METHODS
from webcalyzer.units import validate_unit_compatible_with_dimension

InterpolationMethod = Literal["linear", "pchip", "akima", "cubic"]
IntegrationMethod = Literal["euler", "midpoint", "trapezoid", "rk4", "simpson"]
PlotMode = Literal["filtered", "with_rejected"]
OcrBackend = Literal["auto", "rapidocr", "vision"]
OcrRecognitionLevel = Literal["accurate", "fast"]
OverlayEngine = Literal["auto", "ffmpeg", "opencv"]
OverlayEncoder = Literal[
    "auto",
    "videotoolbox",
    "h264_videotoolbox",
    "nvenc",
    "h264_nvenc",
    "qsv",
    "h264_qsv",
    "vaapi",
    "h264_vaapi",
    "libx264",
]
DerivativeSmoothingMode = Literal["interp", "nearest", "mirror", "constant", "wrap"]
FieldKind = Literal["velocity", "altitude", "met", "custom"]
FieldStage = Literal["stage1", "stage2"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VideoOverlayModel(StrictModel):
    enabled: bool = True
    plot_mode: PlotMode = "filtered"
    engine: OverlayEngine = "auto"
    encoder: OverlayEncoder = "auto"
    width_fraction: float = Field(0.5, ge=0.05, le=1.0)
    height_fraction: float = Field(0.55, ge=0.05, le=1.0)
    output_filename: str = Field("telemetry_overlay.mp4", min_length=1, max_length=255)
    include_audio: bool = True

    @field_validator("output_filename")
    @classmethod
    def _no_path_separator(cls, value: str) -> str:
        if "/" in value or "\\" in value:
            raise ValueError("output_filename must be a bare filename, not a path")
        return value


class LaunchSiteModel(StrictModel):
    latitude_deg: float | None = Field(None, ge=-90.0, le=90.0)
    longitude_deg: float | None = Field(None, ge=-180.0, le=180.0)
    azimuth_deg: float | None = Field(None, ge=0.0, le=360.0)


class TrajectoryModel(StrictModel):
    enabled: bool = True
    interpolation_method: InterpolationMethod = "pchip"
    integration_method: IntegrationMethod = "rk4"
    outlier_preconditioning_enabled: bool = True
    coarse_step_smoothing_enabled: bool = True
    coarse_step_max_gap_s: float = Field(10.0, gt=0.0)
    coarse_altitude_threshold_m: float = Field(500.0, ge=0.0)
    coarse_velocity_threshold_mps: float = Field(50.0, ge=0.0)
    acceleration_source_gap_threshold_s: float = Field(10.0, gt=0.0)
    derivative_smoothing_window_s: float = Field(20.0, gt=0.0)
    derivative_smoothing_polyorder: int = Field(3, ge=0, le=10)
    derivative_min_window_samples: int = Field(5, ge=2, le=1000)
    derivative_smoothing_mode: DerivativeSmoothingMode = "interp"
    launch_site: LaunchSiteModel = Field(default_factory=LaunchSiteModel)


class FieldModel(StrictModel):
    kind: FieldKind
    stage: FieldStage | None = None
    bbox_x1y1x2y2: tuple[float, float, float, float] | None = None
    quantity_id: str | None = None

    @field_validator("bbox_x1y1x2y2")
    @classmethod
    def _validate_bbox(
        cls, value: tuple[float, float, float, float] | None
    ) -> tuple[float, float, float, float] | None:
        if value is None:
            return value
        x0, y0, x1, y1 = value
        for component in value:
            if not 0.0 <= component <= 1.0:
                raise ValueError("bbox components must be in [0, 1] (normalized)")
        if x1 <= x0 or y1 <= y0:
            raise ValueError("bbox must satisfy x1 > x0 and y1 > y0")
        return value

    @model_validator(mode="after")
    def _stage_consistency(self) -> "FieldModel":
        if self.kind == "met":
            if self.stage is not None:
                raise ValueError("MET fields must not have a stage")
            if self.quantity_id is not None:
                raise ValueError("MET fields must not declare quantity_id")
        elif self.kind == "custom":
            if self.stage is not None:
                raise ValueError("custom fields must not have a stage")
            if not self.quantity_id:
                raise ValueError("custom fields must declare quantity_id")
        else:
            if self.stage is None:
                raise ValueError(f"{self.kind} fields must declare a stage")
            if self.quantity_id is not None:
                raise ValueError(f"{self.kind} fields must not declare quantity_id")
        return self


class TelemetryQuantityModel(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = None
    dimensionality: str = Field(min_length=1)
    display_unit: str = Field(min_length=1)
    description: str = ""
    unit_aliases: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> "TelemetryQuantityModel":
        self.slug = make_quantity_slug(self.slug or self.name)
        self.dimensionality = normalize_dimension_expression(self.dimensionality)
        validate_unit_compatible_with_dimension(self.display_unit, self.dimensionality)
        for alias, unit_expression in self.unit_aliases.items():
            if not alias.strip() or not unit_expression.strip():
                raise ValueError("unit aliases must have non-empty alias and unit expression")
            validate_unit_compatible_with_dimension(unit_expression, self.dimensionality)
        return self


class CalibrationVideoModel(StrictModel):
    path: str | None = None
    fps: float | None = Field(None, gt=0.0)
    frame_count: int | None = Field(None, ge=0)
    width: int | None = Field(None, ge=0)
    height: int | None = Field(None, ge=0)


class SegmentModel(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    start_frame_index: int = Field(ge=0)
    start_time_s: float = Field(ge=0.0)
    end_frame_index: int = Field(ge=0)
    end_time_s: float = Field(ge=0.0)
    visible_fields: list[str] = Field(default_factory=list)
    fields: dict[str, FieldModel] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _segment_consistency(self) -> "SegmentModel":
        if self.end_frame_index < self.start_frame_index:
            raise ValueError("end_frame_index must be greater than or equal to start_frame_index")
        for name, field_model in self.fields.items():
            if field_model.kind == "custom":
                if not name.startswith("custom_"):
                    raise ValueError(f"custom field {name!r} must use a custom_<slug> name")
                continue
            if name not in CANONICAL_FIELD_DEFINITIONS:
                raise ValueError(f"Unsupported canonical field {name!r}")
            expected_kind, expected_stage = CANONICAL_FIELD_DEFINITIONS[name]
            if field_model.kind != expected_kind or field_model.stage != expected_stage:
                raise ValueError(
                    f"{name} must use kind={expected_kind!r} and stage={expected_stage!r}"
                )
        visible = set(self.visible_fields)
        missing_visible = [name for name in self.fields if name not in visible]
        if missing_visible:
            raise ValueError(f"enabled fields must be visible: {', '.join(missing_visible)}")
        return self


class HardcodedStageModel(StrictModel):
    velocity_mps: float | None = None
    altitude_m: float | None = None


class HardcodedRawPointModel(StrictModel):
    mission_elapsed_time_s: float
    stage1: HardcodedStageModel = Field(default_factory=HardcodedStageModel)
    stage2: HardcodedStageModel = Field(default_factory=HardcodedStageModel)
    custom_values: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _at_least_one_value(self) -> "HardcodedRawPointModel":
        values = [
            self.stage1.velocity_mps,
            self.stage1.altitude_m,
            self.stage2.velocity_mps,
            self.stage2.altitude_m,
            *self.custom_values.values(),
        ]
        if all(value is None for value in values):
            raise ValueError(
                "Each hardcoded raw data point must define at least one telemetry value"
            )
        return self


class UnitAliasModel(StrictModel):
    aliases: list[str] = Field(min_length=1)
    unit: str = Field(min_length=1)

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().upper() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("aliases must include at least one non-empty token")
        return cleaned


class FieldKindParsingModel(StrictModel):
    units: dict[str, UnitAliasModel] = Field(min_length=1)
    default_unit: str = Field(min_length=1)
    ambiguous_default_unit: str | None = None
    inferred_units_with_separator: list[str] = Field(default_factory=list)
    inferred_units_without_separator: list[str] = Field(default_factory=list)
    output_unit: str | None = None

    @field_validator("default_unit", "ambiguous_default_unit")
    @classmethod
    def _upper_optional(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().upper()

    @field_validator("inferred_units_with_separator", "inferred_units_without_separator")
    @classmethod
    def _upper_list(cls, value: list[str]) -> list[str]:
        return [item.strip().upper() for item in value if item and item.strip()]

    @model_validator(mode="after")
    def _check_default_unit_in_units(self) -> "FieldKindParsingModel":
        unit_names = {key.upper() for key in self.units}
        if self.default_unit not in unit_names:
            raise ValueError(
                f"default_unit {self.default_unit!r} must be one of the declared units"
            )
        if self.ambiguous_default_unit and self.ambiguous_default_unit not in unit_names:
            raise ValueError(
                "ambiguous_default_unit must be one of the declared units"
            )
        for inferred in (
            *self.inferred_units_with_separator,
            *self.inferred_units_without_separator,
        ):
            if inferred not in unit_names:
                raise ValueError(
                    f"inferred unit {inferred!r} not present in units"
                )
        return self


class MetParsingModel(StrictModel):
    timestamp_patterns: list[str] = Field(min_length=1)

    @field_validator("timestamp_patterns")
    @classmethod
    def _validate_patterns(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            text = raw.strip() if isinstance(raw, str) else ""
            if not text:
                continue
            try:
                re.compile(text)
            except re.error as exc:
                raise ValueError(f"Invalid regex {text!r}: {exc}") from exc
            cleaned.append(text)
        if not cleaned:
            raise ValueError("at least one non-empty regex pattern is required")
        return cleaned


class ParsingModel(StrictModel):
    velocity: FieldKindParsingModel
    altitude: FieldKindParsingModel
    met: MetParsingModel
    custom_words: list[str] = Field(default_factory=list)

    @field_validator("custom_words")
    @classmethod
    def _upper_words(cls, value: list[str]) -> list[str]:
        return [item.strip().upper() for item in value if item and item.strip()]


class ProfileModel(StrictModel):
    profile_name: str = Field(min_length=1, max_length=128)
    description: str = ""
    default_sample_fps: float = Field(3.0, gt=0.0, le=240.0)
    default_ocr_workers: int = Field(0, ge=0)
    ocr_backend: OcrBackend = "auto"
    ocr_recognition_level: OcrRecognitionLevel = "accurate"
    skip_full_frame_ocr_fallback: bool = False
    fixture_frame_count: int = Field(20, ge=1, le=2000)
    fixture_time_range_s: tuple[float, float] | None = None
    calibration_video: CalibrationVideoModel = Field(default_factory=CalibrationVideoModel)
    video_overlay: VideoOverlayModel = Field(default_factory=VideoOverlayModel)
    trajectory: TrajectoryModel = Field(default_factory=TrajectoryModel)
    parsing: ParsingModel | None = None
    custom_telemetry_quantities: list[TelemetryQuantityModel] = Field(default_factory=list)
    hardcoded_raw_data_points: list[HardcodedRawPointModel] = Field(default_factory=list)
    segments: list[SegmentModel] = Field(min_length=1)

    @field_validator("profile_name")
    @classmethod
    def _profile_name_chars(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._\- ]+", value):
            raise ValueError(
                "profile_name may only contain letters, digits, dot, underscore, dash, space"
            )
        return value

    @field_validator("fixture_time_range_s")
    @classmethod
    def _fixture_time_range_ordered(
        cls, value: tuple[float, float] | None
    ) -> tuple[float, float] | None:
        if value is None:
            return value
        start, end = value
        if start < 0 or end < 0:
            raise ValueError("fixture_time_range_s components must be >= 0")
        if end <= start:
            raise ValueError("fixture_time_range_s end must be greater than start")
        return value

    @model_validator(mode="after")
    def _segments_are_ordered(self) -> "ProfileModel":
        ids: set[str] = set()
        names: set[str] = set()
        slugs: set[str] = set()
        quantity_by_id: dict[str, TelemetryQuantityModel] = {}
        for quantity in self.custom_telemetry_quantities:
            if quantity.id in ids:
                raise ValueError(f"Duplicate custom quantity id {quantity.id!r}")
            lowered = quantity.name.casefold()
            if lowered in names:
                raise ValueError(f"Duplicate custom quantity name {quantity.name!r}")
            if quantity.slug in slugs:
                raise ValueError(f"Duplicate custom quantity slug {quantity.slug!r}")
            ids.add(quantity.id)
            names.add(lowered)
            slugs.add(quantity.slug or "")
            quantity_by_id[quantity.id] = quantity
        previous_end: int | None = None
        for segment in self.segments:
            if previous_end is not None and segment.start_frame_index < previous_end:
                raise ValueError("segments must be sorted and non-overlapping")
            previous_end = segment.end_frame_index
            for field_name, field_model in segment.fields.items():
                if field_model.kind != "custom":
                    continue
                if field_model.quantity_id not in quantity_by_id:
                    raise ValueError(f"{field_name}: custom quantity is not embedded in profile")
                expected = f"custom_{quantity_by_id[field_model.quantity_id].slug}"
                if field_name != expected:
                    raise ValueError(f"{field_name}: expected field name {expected!r}")
            custom_visible_names = {
                f"custom_{quantity.slug}" for quantity in self.custom_telemetry_quantities
            }
            for field_name in segment.visible_fields:
                if field_name in CANONICAL_FIELD_DEFINITIONS:
                    continue
                if field_name.startswith("custom_") and field_name in custom_visible_names:
                    continue
                raise ValueError(f"{field_name}: visible field is not defined")
        enabled_custom_names = {
            field_name
            for segment in self.segments
            for field_name, field_model in segment.fields.items()
            if field_model.kind == "custom"
        }
        for point in self.hardcoded_raw_data_points:
            for field_name in point.custom_values:
                if field_name not in enabled_custom_names:
                    raise ValueError(
                        f"anchor point custom value {field_name!r} is not enabled in any segment"
                    )
        return self


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def _field_dataclass_to_model(name: str, field: FieldConfig) -> FieldModel:
    box = field.box
    return FieldModel(
        kind=field.kind,  # type: ignore[arg-type]
        stage=field.stage,  # type: ignore[arg-type]
        bbox_x1y1x2y2=(box.x0, box.y0, box.x1, box.y1) if box is not None else None,
        quantity_id=field.quantity_id,
    )


def _field_kind_dataclass_to_model(parsing: FieldKindParsing) -> FieldKindParsingModel:
    units = {
        unit.name: UnitAliasModel(aliases=list(unit.aliases), unit=unit.unit_expression)
        for unit in parsing.units
    }
    return FieldKindParsingModel(
        units=units,
        default_unit=parsing.default_unit,
        ambiguous_default_unit=parsing.ambiguous_default_unit,
        inferred_units_with_separator=list(parsing.inferred_units_with_separator),
        inferred_units_without_separator=list(parsing.inferred_units_without_separator),
        output_unit=parsing.output_unit,
    )


def _quantity_dataclass_to_model(quantity: TelemetryQuantityDefinition) -> TelemetryQuantityModel:
    return TelemetryQuantityModel(
        id=quantity.id,
        name=quantity.name,
        slug=quantity.slug,
        dimensionality=quantity.dimensionality,
        display_unit=quantity.display_unit,
        description=quantity.description,
        unit_aliases=dict(quantity.unit_aliases),
    )


def profile_dataclass_to_model(profile: ProfileConfig) -> ProfileModel:
    parsing_model: ParsingModel | None = None
    if profile.parsing is not None:
        parsing_model = ParsingModel(
            velocity=_field_kind_dataclass_to_model(profile.parsing.velocity),
            altitude=_field_kind_dataclass_to_model(profile.parsing.altitude),
            met=MetParsingModel(timestamp_patterns=list(profile.parsing.met.timestamp_patterns)),
            custom_words=list(profile.parsing.custom_words),
        )
    segments = [
        SegmentModel(
            id=segment.id,
            start_frame_index=segment.start_frame_index,
            start_time_s=segment.start_time_s,
            end_frame_index=segment.end_frame_index,
            end_time_s=segment.end_time_s,
            visible_fields=segment.ordered_visible_field_names(),
            fields={
                name: _field_dataclass_to_model(name, segment.fields[name])
                for name in segment.ordered_field_names()
            },
        )
        for segment in profile.segments
    ]
    return ProfileModel(
        profile_name=profile.profile_name,
        description=profile.description or "",
        default_sample_fps=profile.default_sample_fps,
        default_ocr_workers=profile.default_ocr_workers,
        ocr_backend=profile.ocr_backend,  # type: ignore[arg-type]
        ocr_recognition_level=profile.ocr_recognition_level,  # type: ignore[arg-type]
        skip_full_frame_ocr_fallback=profile.skip_full_frame_ocr_fallback,
        fixture_frame_count=profile.fixture_frame_count,
        fixture_time_range_s=tuple(profile.fixture_time_range_s)
        if profile.fixture_time_range_s is not None
        else None,
        calibration_video=CalibrationVideoModel(**profile.calibration_video.to_dict()),
        video_overlay=VideoOverlayModel(**profile.video_overlay.to_dict()),
        trajectory=TrajectoryModel(
            **{
                **profile.trajectory.to_dict(),
                "launch_site": LaunchSiteModel(
                    **profile.trajectory.launch_site.to_dict()
                ),
            }
        ),
        parsing=parsing_model,
        custom_telemetry_quantities=[
            _quantity_dataclass_to_model(quantity)
            for quantity in profile.custom_telemetry_quantities
        ],
        hardcoded_raw_data_points=[
            HardcodedRawPointModel(
                mission_elapsed_time_s=point.mission_elapsed_time_s,
                stage1=HardcodedStageModel(
                    velocity_mps=point.stage1_velocity_mps,
                    altitude_m=point.stage1_altitude_m,
                ),
                stage2=HardcodedStageModel(
                    velocity_mps=point.stage2_velocity_mps,
                    altitude_m=point.stage2_altitude_m,
                ),
                custom_values=dict(point.custom_values),
            )
            for point in profile.hardcoded_raw_data_points
        ],
        segments=segments,
    )


def _model_field_to_dataclass(name: str, model: FieldModel) -> FieldConfig:
    return FieldConfig(
        name=name,
        kind=model.kind,
        stage=model.stage,
        box=Box.from_sequence(list(model.bbox_x1y1x2y2)) if model.bbox_x1y1x2y2 is not None else None,
        quantity_id=model.quantity_id,
    )


def _model_field_kind_to_dataclass(model: FieldKindParsingModel) -> FieldKindParsing:
    units = tuple(
        UnitAlias(
            name=name.upper(),
            aliases=tuple(item.upper() for item in body.aliases),
            unit_expression=body.unit,
        )
        for name, body in model.units.items()
    )
    return FieldKindParsing(
        units=units,
        default_unit=model.default_unit.upper(),
        ambiguous_default_unit=model.ambiguous_default_unit.upper()
        if model.ambiguous_default_unit
        else None,
        inferred_units_with_separator=tuple(model.inferred_units_with_separator),
        inferred_units_without_separator=tuple(model.inferred_units_without_separator),
        output_unit=model.output_unit,
    )


def _model_quantity_to_dataclass(model: TelemetryQuantityModel) -> TelemetryQuantityDefinition:
    return TelemetryQuantityDefinition(
        id=model.id,
        name=model.name,
        slug=model.slug or make_quantity_slug(model.name),
        dimensionality=model.dimensionality,
        display_unit=model.display_unit,
        description=model.description,
        unit_aliases=dict(model.unit_aliases),
    )


def model_to_profile_dataclass(model: ProfileModel) -> ProfileConfig:
    parsing: ParsingProfile | None
    if model.parsing is not None:
        parsing = ParsingProfile(
            velocity=_model_field_kind_to_dataclass(model.parsing.velocity),
            altitude=_model_field_kind_to_dataclass(model.parsing.altitude),
            met=MetParsing(timestamp_patterns=tuple(model.parsing.met.timestamp_patterns)),
            custom_words=tuple(model.parsing.custom_words),
        )
    else:
        parsing = None
    return ProfileConfig(
        profile_name=model.profile_name,
        description=model.description,
        default_sample_fps=float(model.default_sample_fps),
        default_ocr_workers=int(model.default_ocr_workers),
        ocr_backend=model.ocr_backend,
        ocr_recognition_level=model.ocr_recognition_level,
        skip_full_frame_ocr_fallback=model.skip_full_frame_ocr_fallback,
        fixture_frame_count=int(model.fixture_frame_count),
        fixture_time_range_s=tuple(model.fixture_time_range_s)
        if model.fixture_time_range_s is not None
        else None,
        calibration_video=CalibrationVideoConfig(**model.calibration_video.model_dump()),
        video_overlay=VideoOverlayConfig(**model.video_overlay.model_dump()),
        trajectory=TrajectoryConfig(
            enabled=model.trajectory.enabled,
            interpolation_method=model.trajectory.interpolation_method,
            integration_method=model.trajectory.integration_method,
            outlier_preconditioning_enabled=model.trajectory.outlier_preconditioning_enabled,
            coarse_step_smoothing_enabled=model.trajectory.coarse_step_smoothing_enabled,
            coarse_step_max_gap_s=model.trajectory.coarse_step_max_gap_s,
            coarse_altitude_threshold_m=model.trajectory.coarse_altitude_threshold_m,
            coarse_velocity_threshold_mps=model.trajectory.coarse_velocity_threshold_mps,
            acceleration_source_gap_threshold_s=model.trajectory.acceleration_source_gap_threshold_s,
            derivative_smoothing_window_s=model.trajectory.derivative_smoothing_window_s,
            derivative_smoothing_polyorder=model.trajectory.derivative_smoothing_polyorder,
            derivative_min_window_samples=model.trajectory.derivative_min_window_samples,
            derivative_smoothing_mode=model.trajectory.derivative_smoothing_mode,
            launch_site=LaunchSiteConfig(**model.trajectory.launch_site.model_dump()),
        ),
        parsing=parsing,
        custom_telemetry_quantities=[
            _model_quantity_to_dataclass(quantity)
            for quantity in model.custom_telemetry_quantities
        ],
        hardcoded_raw_data_points=[
            HardcodedRawDataPoint(
                mission_elapsed_time_s=point.mission_elapsed_time_s,
                stage1_velocity_mps=point.stage1.velocity_mps,
                stage1_altitude_m=point.stage1.altitude_m,
                stage2_velocity_mps=point.stage2.velocity_mps,
                stage2_altitude_m=point.stage2.altitude_m,
                custom_values=dict(point.custom_values),
            )
            for point in model.hardcoded_raw_data_points
        ],
        segments=[
            CalibrationSegmentConfig(
                id=segment.id,
                start_frame_index=segment.start_frame_index,
                start_time_s=segment.start_time_s,
                end_frame_index=segment.end_frame_index,
                end_time_s=segment.end_time_s,
                visible_fields=list(segment.visible_fields),
                fields={
                    name: _model_field_to_dataclass(name, segment.fields[name])
                    for name in [
                        *[canonical for canonical in CANONICAL_FIELD_ORDER if canonical in segment.fields],
                        *[name for name in segment.fields if name not in CANONICAL_FIELD_ORDER],
                    ]
                },
            )
            for segment in model.segments
        ],
    )


def validate_runnable_profile_model(model: ProfileModel) -> ProfileModel:
    if not model.segments:
        raise ValueError("At least one segment is required")

    previous_end: int | None = None
    for index, segment in enumerate(model.segments):
        label = segment.id or f"segment_{index + 1}"
        if segment.end_frame_index <= segment.start_frame_index:
            raise ValueError(f"{label}: end_frame_index must be greater than start_frame_index")
        if previous_end is not None and segment.start_frame_index != previous_end:
            raise ValueError(f"{label}: segments must be contiguous")
        previous_end = segment.end_frame_index

        if "met" not in segment.fields:
            raise ValueError(f"{label}: met field is required")
        for name, field_model in segment.fields.items():
            if field_model.bbox_x1y1x2y2 is None:
                raise ValueError(f"{label}: {name} must define bbox_x1y1x2y2")
            if field_model.kind == "custom" and not field_model.quantity_id:
                raise ValueError(f"{label}: {name} must reference a custom quantity")

    video = model.calibration_video
    if video.frame_count is not None:
        first = model.segments[0]
        last = model.segments[-1]
        if last.end_frame_index > video.frame_count:
            raise ValueError("Last segment end_frame_index exceeds calibration video frame_count")
        if first.start_frame_index >= video.frame_count:
            raise ValueError("First segment start_frame_index exceeds calibration video frame_count")

    return model


def default_parsing_model() -> ParsingModel:
    """Return a `ParsingModel` populated with the same defaults as the Python pipeline."""

    return profile_dataclass_to_model(
        ProfileConfig(
            profile_name="defaults",
            description="",
            default_sample_fps=3.0,
            fixture_frame_count=20,
            fixture_time_range_s=None,
            parsing=default_parsing_profile(),
            segments=[
                CalibrationSegmentConfig(
                    id="segment_1",
                    start_frame_index=0,
                    start_time_s=0.0,
                    end_frame_index=1,
                    end_time_s=1.0,
                    visible_fields=["stage1_velocity"],
                    fields={
                        "stage1_velocity": FieldConfig(
                            name="stage1_velocity",
                            kind="velocity",
                            stage="stage1",
                            box=Box(0.0, 0.0, 0.1, 0.1),
                        )
                    },
                )
            ],
        )
    ).parsing  # type: ignore[return-value]


def trajectory_choices() -> dict[str, list[str]]:
    return {
        "interpolation_methods": sorted(INTERPOLATION_METHODS),
        "integration_methods": sorted(INTEGRATION_METHODS),
    }


def serialize_for_yaml(model: ProfileModel) -> dict[str, Any]:
    """Render the validated profile back into the dataclass-native dict that
    `save_profile` expects."""

    return model_to_profile_dataclass(model).to_dict()
