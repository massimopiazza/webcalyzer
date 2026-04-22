from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


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
    box: Box

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "stage": self.stage,
            "box": list(self.box.normalized_tuple()),
        }


@dataclass(slots=True)
class ProfileConfig:
    profile_name: str
    description: str
    reference_width: int
    reference_height: int
    default_sample_fps: float
    fixture_frame_count: int
    fixture_reference_times_s: list[float]
    fields: dict[str, FieldConfig] = field(default_factory=dict)

    def ordered_field_names(self) -> list[str]:
        return list(self.fields.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "description": self.description,
            "reference_resolution": {
                "width": self.reference_width,
                "height": self.reference_height,
            },
            "default_sample_fps": self.default_sample_fps,
            "fixture_frame_count": self.fixture_frame_count,
            "fixture_reference_times_s": list(self.fixture_reference_times_s),
            "fields": {name: field_cfg.to_dict() for name, field_cfg in self.fields.items()},
        }


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractionRow:
    frame_index: int
    sample_time_s: float
    mission_elapsed_time_s: float | None
    stage1_velocity_mps: float | None
    stage1_altitude_m: float | None
    stage2_velocity_mps: float | None
    stage2_altitude_m: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
