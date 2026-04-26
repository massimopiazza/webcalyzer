from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from webcalyzer.models import Box, FieldConfig, ProfileConfig, VideoOverlayConfig


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
        fields=fields,
    )


def save_profile(profile: ProfileConfig, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(profile.to_dict(), sort_keys=False))
    return target


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
