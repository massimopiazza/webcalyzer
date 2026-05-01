from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from webcalyzer.config import default_parsing_profile
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
from webcalyzer.trajectory import INTEGRATION_METHODS, INTERPOLATION_METHODS

InterpolationMethod = Literal["linear", "pchip", "akima", "cubic"]
IntegrationMethod = Literal["euler", "midpoint", "trapezoid", "rk4", "simpson"]
PlotMode = Literal["filtered", "with_rejected"]
DerivativeSmoothingMode = Literal["interp", "nearest", "mirror", "constant", "wrap"]
FieldKind = Literal["velocity", "altitude", "met"]
FieldStage = Literal["stage1", "stage2"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VideoOverlayModel(StrictModel):
    enabled: bool = True
    plot_mode: PlotMode = "filtered"
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
    bbox_x1y1x2y2: tuple[float, float, float, float]

    @field_validator("bbox_x1y1x2y2")
    @classmethod
    def _validate_bbox(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
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
        else:
            if self.stage is None:
                raise ValueError(f"{self.kind} fields must declare a stage")
        return self


class HardcodedStageModel(StrictModel):
    velocity_mps: float | None = None
    altitude_m: float | None = None


class HardcodedRawPointModel(StrictModel):
    mission_elapsed_time_s: float
    stage1: HardcodedStageModel = Field(default_factory=HardcodedStageModel)
    stage2: HardcodedStageModel = Field(default_factory=HardcodedStageModel)

    @model_validator(mode="after")
    def _at_least_one_value(self) -> "HardcodedRawPointModel":
        values = [
            self.stage1.velocity_mps,
            self.stage1.altitude_m,
            self.stage2.velocity_mps,
            self.stage2.altitude_m,
        ]
        if all(value is None for value in values):
            raise ValueError(
                "Each hardcoded raw data point must define at least one telemetry value"
            )
        return self


class UnitAliasModel(StrictModel):
    aliases: list[str] = Field(min_length=1)
    si_factor: float = Field(gt=0.0)

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
    fixture_frame_count: int = Field(20, ge=1, le=2000)
    fixture_time_range_s: tuple[float, float] | None = None
    video_overlay: VideoOverlayModel = Field(default_factory=VideoOverlayModel)
    trajectory: TrajectoryModel = Field(default_factory=TrajectoryModel)
    parsing: ParsingModel | None = None
    hardcoded_raw_data_points: list[HardcodedRawPointModel] = Field(default_factory=list)
    fields: dict[str, FieldModel] = Field(min_length=1)

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
    def _at_least_one_field(self) -> "ProfileModel":
        if not self.fields:
            raise ValueError("at least one field must be defined")
        return self


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------


def _field_dataclass_to_model(name: str, field: FieldConfig) -> FieldModel:
    box = field.box
    return FieldModel(
        kind=field.kind,  # type: ignore[arg-type]
        stage=field.stage,  # type: ignore[arg-type]
        bbox_x1y1x2y2=(box.x0, box.y0, box.x1, box.y1),
    )


def _field_kind_dataclass_to_model(parsing: FieldKindParsing) -> FieldKindParsingModel:
    units = {
        unit.name: UnitAliasModel(aliases=list(unit.aliases), si_factor=unit.si_factor)
        for unit in parsing.units
    }
    return FieldKindParsingModel(
        units=units,
        default_unit=parsing.default_unit,
        ambiguous_default_unit=parsing.ambiguous_default_unit,
        inferred_units_with_separator=list(parsing.inferred_units_with_separator),
        inferred_units_without_separator=list(parsing.inferred_units_without_separator),
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
    fields = {
        name: _field_dataclass_to_model(name, field) for name, field in profile.fields.items()
    }
    return ProfileModel(
        profile_name=profile.profile_name,
        description=profile.description or "",
        default_sample_fps=profile.default_sample_fps,
        fixture_frame_count=profile.fixture_frame_count,
        fixture_time_range_s=tuple(profile.fixture_time_range_s)
        if profile.fixture_time_range_s is not None
        else None,
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
            )
            for point in profile.hardcoded_raw_data_points
        ],
        fields=fields,
    )


def _model_field_to_dataclass(name: str, model: FieldModel) -> FieldConfig:
    return FieldConfig(
        name=name,
        kind=model.kind,
        stage=model.stage,
        box=Box.from_sequence(list(model.bbox_x1y1x2y2)),
    )


def _model_field_kind_to_dataclass(model: FieldKindParsingModel) -> FieldKindParsing:
    units = tuple(
        UnitAlias(
            name=name.upper(),
            aliases=tuple(item.upper() for item in body.aliases),
            si_factor=float(body.si_factor),
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
        fixture_frame_count=int(model.fixture_frame_count),
        fixture_time_range_s=tuple(model.fixture_time_range_s)
        if model.fixture_time_range_s is not None
        else None,
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
        hardcoded_raw_data_points=[
            HardcodedRawDataPoint(
                mission_elapsed_time_s=point.mission_elapsed_time_s,
                stage1_velocity_mps=point.stage1.velocity_mps,
                stage1_altitude_m=point.stage1.altitude_m,
                stage2_velocity_mps=point.stage2.velocity_mps,
                stage2_altitude_m=point.stage2.altitude_m,
            )
            for point in model.hardcoded_raw_data_points
        ],
        fields={name: _model_field_to_dataclass(name, model_field) for name, model_field in model.fields.items()},
    )


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
            fields={
                "stage1_velocity": FieldConfig(
                    name="stage1_velocity",
                    kind="velocity",
                    stage="stage1",
                    box=Box(0.0, 0.0, 0.1, 0.1),
                )
            },
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
