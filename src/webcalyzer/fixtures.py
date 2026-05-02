from __future__ import annotations

from pathlib import Path

import numpy as np

from webcalyzer.models import ProfileConfig
from webcalyzer.video import (
    build_contact_sheet,
    draw_box,
    evenly_spaced_indices,
    get_video_metadata,
    iterate_frames,
    write_frame,
)


REVIEW_FIELD_COLORS: list[tuple[int, int, int]] = [
    (255, 128, 64),
    (64, 200, 255),
    (120, 255, 120),
    (200, 120, 255),
    (255, 220, 80),
]


def _annotate_review_frame(frame: np.ndarray, profile: ProfileConfig) -> np.ndarray:
    output = frame.copy()
    for idx, field_name in enumerate(profile.ordered_field_names()):
        output = draw_box(
            output,
            profile.fields[field_name].box,
            label=f"{idx + 1}: {field_name}",
            color=REVIEW_FIELD_COLORS[idx % len(REVIEW_FIELD_COLORS)],
        )
    return output


def generate_review_frames(video_path: str | Path, profile: ProfileConfig, output_dir: str | Path, count: int | None = None) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata = get_video_metadata(video_path)
    sample_count = int(count or profile.fixture_frame_count)
    indices = evenly_spaced_indices(metadata, sample_count, time_range_s=profile.fixture_time_range_s)
    frames = iterate_frames(video_path, indices)
    saved_frames = []
    labels = []
    for ordinal, (frame_index, frame) in enumerate(frames):
        time_s = frame_index / metadata.fps
        label = f"{frame_index} | {time_s:0.1f}s"
        review_frame = _annotate_review_frame(frame, profile)
        labels.append(label)
        saved_frames.append(review_frame)
        write_frame(output_path / f"frame_{ordinal:02d}_{frame_index:05d}.jpg", review_frame)
    contact_sheet = build_contact_sheet(saved_frames, labels)
    write_frame(output_path / "contact_sheet.jpg", contact_sheet)
