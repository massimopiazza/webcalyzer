from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CANONICAL_FIELD_ORDER = (
    "met",
    "stage1_velocity",
    "stage1_altitude",
    "stage2_velocity",
    "stage2_altitude",
)

CANONICAL_FIELD_DEFINITIONS: dict[str, tuple[str, str | None]] = {
    "met": ("met", None),
    "stage1_velocity": ("velocity", "stage1"),
    "stage1_altitude": ("altitude", "stage1"),
    "stage2_velocity": ("velocity", "stage2"),
    "stage2_altitude": ("altitude", "stage2"),
}


@dataclass(slots=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    def clamp(self) -> "Box":
        return Box(
            x0=max(0.0, min(1.0, self.x0)),
            y0=max(0.0, min(1.0, self.y0)),
            x1=max(0.0, min(1.0, self.x1)),
            y1=max(0.0, min(1.0, self.y1)),
        )

    def normalized_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def as_int_xyxy(self, width: int, height: int) -> tuple[int, int, int, int]:
        x0 = int(round(self.x0 * width))
        y0 = int(round(self.y0 * height))
        x1 = int(round(self.x1 * width))
        y1 = int(round(self.y1 * height))
        x0 = max(0, min(width - 1, x0))
        x1 = max(x0 + 1, min(width, x1))
        y0 = max(0, min(height - 1, y0))
        y1 = max(y0 + 1, min(height, y1))
        return x0, y0, x1, y1

    @classmethod
    def from_sequence(cls, values: list[float] | tuple[float, float, float, float]) -> "Box":
        return cls(float(values[0]), float(values[1]), float(values[2]), float(values[3])).clamp()


@dataclass(slots=True)
class FieldConfig:
    name: str
    kind: str
    stage: str | None
    box: Box | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "stage": self.stage,
            "bbox_x1y1x2y2": list(self.box.normalized_tuple()) if self.box is not None else None,
        }

    @classmethod
    def canonical(cls, name: str, box: Box | None = None) -> "FieldConfig":
        kind, stage = CANONICAL_FIELD_DEFINITIONS[name]
        return cls(name=name, kind=kind, stage=stage, box=box)


@dataclass(slots=True)
class VideoOverlayConfig:
    enabled: bool = True
    plot_mode: str = "filtered"
    engine: str = "auto"
    encoder: str = "auto"
    width_fraction: float = 0.5
    height_fraction: float = 0.55
    output_filename: str = "telemetry_overlay.mp4"
    include_audio: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "plot_mode": self.plot_mode,
            "engine": self.engine,
            "encoder": self.encoder,
            "width_fraction": self.width_fraction,
            "height_fraction": self.height_fraction,
            "output_filename": self.output_filename,
            "include_audio": self.include_audio,
        }


@dataclass(slots=True)
class LaunchSiteConfig:
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    azimuth_deg: float | None = None

    def is_complete(self) -> bool:
        return (
            self.latitude_deg is not None
            and self.longitude_deg is not None
            and self.azimuth_deg is not None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "azimuth_deg": self.azimuth_deg,
        }


@dataclass(slots=True)
class TrajectoryConfig:
    enabled: bool = True
    interpolation_method: str = "pchip"
    integration_method: str = "rk4"
    outlier_preconditioning_enabled: bool = True
    coarse_step_smoothing_enabled: bool = True
    coarse_step_max_gap_s: float = 10.0
    coarse_altitude_threshold_m: float = 500.0
    coarse_velocity_threshold_mps: float = 50.0
    acceleration_source_gap_threshold_s: float = 10.0
    derivative_smoothing_window_s: float = 20.0
    derivative_smoothing_polyorder: int = 3
    derivative_min_window_samples: int = 5
    derivative_smoothing_mode: str = "interp"
    launch_site: LaunchSiteConfig = field(default_factory=LaunchSiteConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interpolation_method": self.interpolation_method,
            "integration_method": self.integration_method,
            "outlier_preconditioning_enabled": self.outlier_preconditioning_enabled,
            "coarse_step_smoothing_enabled": self.coarse_step_smoothing_enabled,
            "coarse_step_max_gap_s": self.coarse_step_max_gap_s,
            "coarse_altitude_threshold_m": self.coarse_altitude_threshold_m,
            "coarse_velocity_threshold_mps": self.coarse_velocity_threshold_mps,
            "acceleration_source_gap_threshold_s": self.acceleration_source_gap_threshold_s,
            "derivative_smoothing_window_s": self.derivative_smoothing_window_s,
            "derivative_smoothing_polyorder": self.derivative_smoothing_polyorder,
            "derivative_min_window_samples": self.derivative_min_window_samples,
            "derivative_smoothing_mode": self.derivative_smoothing_mode,
            "launch_site": self.launch_site.to_dict(),
        }


@dataclass(slots=True)
class UnitAlias:
    """A surface unit token plus its conversion to SI for one measurement kind."""

    name: str
    aliases: tuple[str, ...]
    si_factor: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "aliases": list(self.aliases),
            "si_factor": self.si_factor,
        }


@dataclass(slots=True)
class FieldKindParsing:
    """Parsing rules applicable to a measurement kind (velocity / altitude).

    ``inferred_units_with_separator`` and ``inferred_units_without_separator``
    are the unit candidates tried when the OCR text has no explicit unit
    label. They default to ``(default_unit,)`` so a single-unit feed (e.g.
    velocity-as-MPH only) doesn't see false alternatives. Altitude
    overrides ``inferred_units_with_separator`` with both MI and FT so a
    "000,056" reading whose unit label was lost in OCR noise can still be
    disambiguated.
    """

    units: tuple[UnitAlias, ...]
    default_unit: str
    ambiguous_default_unit: str | None = None
    inferred_units_with_separator: tuple[str, ...] = ()
    inferred_units_without_separator: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.inferred_units_with_separator:
            self.inferred_units_with_separator = (self.default_unit,)
        if not self.inferred_units_without_separator:
            self.inferred_units_without_separator = (self.default_unit,)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "default_unit": self.default_unit,
            "units": {unit.name: unit.to_dict() for unit in self.units},
            "inferred_units_with_separator": list(self.inferred_units_with_separator),
            "inferred_units_without_separator": list(self.inferred_units_without_separator),
        }
        if self.ambiguous_default_unit is not None:
            data["ambiguous_default_unit"] = self.ambiguous_default_unit
        return data


@dataclass(slots=True)
class MetParsing:
    """Parsing rules for the mission elapsed time field."""

    timestamp_patterns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp_patterns": list(self.timestamp_patterns)}


@dataclass(slots=True)
class ParsingProfile:
    """Profile-driven OCR vocabulary and unit parsing rules.

    Built from YAML so the OCR vocabulary (Apple Vision custom words),
    accepted unit aliases, unit-to-SI conversions and timestamp patterns
    can all be tuned per webcast without code changes.
    """

    velocity: FieldKindParsing
    altitude: FieldKindParsing
    met: MetParsing
    custom_words: tuple[str, ...]

    def custom_words_list(self) -> list[str]:
        return list(self.custom_words)

    def kind(self, kind: str) -> FieldKindParsing:
        if kind == "velocity":
            return self.velocity
        if kind == "altitude":
            return self.altitude
        raise ValueError(f"Unsupported measurement kind: {kind}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "velocity": self.velocity.to_dict(),
            "altitude": self.altitude.to_dict(),
            "met": self.met.to_dict(),
            "custom_words": list(self.custom_words),
        }


@dataclass(slots=True)
class HardcodedRawDataPoint:
    mission_elapsed_time_s: float
    stage1_velocity_mps: float | None = None
    stage1_altitude_m: float | None = None
    stage2_velocity_mps: float | None = None
    stage2_altitude_m: float | None = None

    def field_values(self) -> dict[str, float]:
        return {
            field_name: value
            for field_name, value in {
                "stage1_velocity": self.stage1_velocity_mps,
                "stage1_altitude": self.stage1_altitude_m,
                "stage2_velocity": self.stage2_velocity_mps,
                "stage2_altitude": self.stage2_altitude_m,
            }.items()
            if value is not None
        }

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"mission_elapsed_time_s": self.mission_elapsed_time_s}
        for stage in ("stage1", "stage2"):
            stage_data: dict[str, float] = {}
            velocity = getattr(self, f"{stage}_velocity_mps")
            altitude = getattr(self, f"{stage}_altitude_m")
            if velocity is not None:
                stage_data["velocity_mps"] = velocity
            if altitude is not None:
                stage_data["altitude_m"] = altitude
            if stage_data:
                data[stage] = stage_data
        return data


@dataclass(slots=True)
class CalibrationVideoConfig:
    path: str | None = None
    fps: float | None = None
    frame_count: int | None = None
    width: int | None = None
    height: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
        }


@dataclass(slots=True)
class CalibrationSegmentConfig:
    id: str
    start_frame_index: int
    start_time_s: float
    end_frame_index: int
    end_time_s: float
    fields: dict[str, FieldConfig] = field(default_factory=dict)

    def contains_frame(self, frame_index: int) -> bool:
        return self.start_frame_index <= frame_index < self.end_frame_index

    def ordered_field_names(self) -> list[str]:
        ordered = [name for name in CANONICAL_FIELD_ORDER if name in self.fields]
        ordered.extend(name for name in self.fields if name not in CANONICAL_FIELD_ORDER)
        return ordered

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start_frame_index": self.start_frame_index,
            "start_time_s": self.start_time_s,
            "end_frame_index": self.end_frame_index,
            "end_time_s": self.end_time_s,
            "fields": {
                name: self.fields[name].to_dict()
                for name in self.ordered_field_names()
            },
        }


@dataclass(slots=True)
class ProfileConfig:
    profile_name: str
    description: str
    default_sample_fps: float
    fixture_frame_count: int
    fixture_time_range_s: tuple[float, float] | None
    default_ocr_workers: int = 0
    ocr_backend: str = "auto"
    ocr_recognition_level: str = "accurate"
    skip_full_frame_ocr_fallback: bool = False
    calibration_video: CalibrationVideoConfig = field(default_factory=CalibrationVideoConfig)
    video_overlay: VideoOverlayConfig = field(default_factory=VideoOverlayConfig)
    trajectory: TrajectoryConfig = field(default_factory=TrajectoryConfig)
    parsing: "ParsingProfile | None" = None
    hardcoded_raw_data_points: list[HardcodedRawDataPoint] = field(default_factory=list)
    segments: list[CalibrationSegmentConfig] = field(default_factory=list)

    @property
    def fields(self) -> dict[str, FieldConfig]:
        return self.segments[0].fields if self.segments else {}

    def ordered_field_names(self) -> list[str]:
        return self.segments[0].ordered_field_names() if self.segments else []

    def active_segment_for_frame(self, frame_index: int) -> CalibrationSegmentConfig | None:
        for segment in self.segments:
            if segment.contains_frame(frame_index):
                return segment
        return None

    def segment_by_id(self, segment_id: str | None) -> CalibrationSegmentConfig | None:
        if not segment_id:
            return None
        for segment in self.segments:
            if segment.id == segment_id:
                return segment
        return None

    def frame_bounds(self) -> tuple[int, int] | None:
        if not self.segments:
            return None
        return (
            min(segment.start_frame_index for segment in self.segments),
            max(segment.end_frame_index for segment in self.segments),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "profile_name": self.profile_name,
            "description": self.description,
            "default_sample_fps": self.default_sample_fps,
            "default_ocr_workers": self.default_ocr_workers,
            "ocr_backend": self.ocr_backend,
            "ocr_recognition_level": self.ocr_recognition_level,
            "skip_full_frame_ocr_fallback": self.skip_full_frame_ocr_fallback,
            "fixture_frame_count": self.fixture_frame_count,
            "fixture_time_range_s": list(self.fixture_time_range_s) if self.fixture_time_range_s is not None else None,
            "calibration_video": self.calibration_video.to_dict(),
            "video_overlay": self.video_overlay.to_dict(),
            "trajectory": self.trajectory.to_dict(),
        }
        if self.parsing is not None:
            data["parsing"] = self.parsing.to_dict()
        if self.hardcoded_raw_data_points:
            data["hardcoded_raw_data_points"] = [
                point.to_dict() for point in self.hardcoded_raw_data_points
            ]
        data["segments"] = [segment.to_dict() for segment in self.segments]
        return data


@dataclass(slots=True)
class VideoMetadata:
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int
    duration_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "duration_s": self.duration_s,
        }


@dataclass(slots=True)
class OCRObservation:
    field_name: str
    raw_text: str | None
    parse_status: str
    raw_unit: str | None
    raw_value: float | None
    normalized_si_value: float | None
    variant: str | None
    parse_confidence: float | None = None
    unit_source: str | None = None
    unit_match_text: str | None = None
    unit_match_score: float | None = None
    candidate_count: int | None = None
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractionRow:
    frame_index: int
    sample_time_s: float
    segment_id: str | None
    mission_elapsed_time_s: float | None
    stage1_velocity_mps: float | None
    stage1_altitude_m: float | None
    stage2_velocity_mps: float | None
    stage2_altitude_m: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
