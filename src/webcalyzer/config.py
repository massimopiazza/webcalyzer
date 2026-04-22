from __future__ import annotations

from pathlib import Path

import yaml

from webcalyzer.models import Box, FieldConfig, ProfileConfig


def load_profile(path: str | Path) -> ProfileConfig:
    profile_path = Path(path)
    data = yaml.safe_load(profile_path.read_text())
    fields = {
        name: FieldConfig(
            name=name,
            kind=field_data["kind"],
            stage=field_data.get("stage"),
            box=Box.from_sequence(field_data["box"]),
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
        fixture_reference_times_s=[float(value) for value in data.get("fixture_reference_times_s", [])],
        fields=fields,
    )


def save_profile(profile: ProfileConfig, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(profile.to_dict(), sort_keys=False))
    return target
