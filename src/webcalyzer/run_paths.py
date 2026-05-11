from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


def timestamped_run_output_dir(
    output_parent: str | Path,
    profile_source_name: str | Path | None,
    *,
    now: datetime | None = None,
) -> Path:
    """Return a collision-resistant run directory under ``output_parent``."""

    parent = Path(output_parent)
    timestamp = (now or datetime.now()).strftime("%Y-%m-%dT%H-%M-%S")
    stem = _profile_output_stem(profile_source_name)
    candidate = parent / f"{stem}_{timestamp}"
    if not candidate.exists():
        return candidate
    for suffix in range(2, 1000):
        candidate = parent / f"{stem}_{timestamp}-{suffix:02d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate a unique output directory under {parent}")


def _profile_output_stem(profile_source_name: str | Path | None) -> str:
    raw_name = "" if profile_source_name is None else str(profile_source_name).strip()
    raw_name = raw_name.replace("\\", "/")
    stem = Path(raw_name).stem if raw_name else "profile"
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip(" ._-")
    return stem or "profile"
