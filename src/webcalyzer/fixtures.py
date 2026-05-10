from __future__ import annotations

from pathlib import Path
from typing import Callable

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


def _annotate_review_frame(frame: np.ndarray, profile: ProfileConfig, frame_index: int) -> np.ndarray:
    output = frame.copy()
    segment = profile.active_segment_for_frame(frame_index) or (profile.segments[0] if profile.segments else None)
    if segment is None:
        return output
    for idx, field_name in enumerate(segment.ordered_field_names()):
        field = segment.fields[field_name]
        if field.box is None:
            continue
        output = draw_box(
            output,
            field.box,
            label=f"{idx + 1}: {field_name}",
            color=REVIEW_FIELD_COLORS[idx % len(REVIEW_FIELD_COLORS)],
        )
    import cv2

    cv2.rectangle(output, (10, 10), (260, 44), (0, 0, 0), -1)
    cv2.putText(output, segment.id, (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
    return output


def generate_review_frames(
    video_path: str | Path,
    profile: ProfileConfig,
    output_dir: str | Path,
    count: int | None = None,
    *,
    cancel_check: Callable[[], None] | None = None,
) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata = get_video_metadata(video_path)
    sample_count = int(count or profile.fixture_frame_count)
    indices = evenly_spaced_indices(metadata, sample_count, time_range_s=profile.fixture_time_range_s)
    frames = iterate_frames(video_path, indices)
    saved_frames = []
    labels = []
    for ordinal, (frame_index, frame) in enumerate(frames):
        if cancel_check is not None:
            cancel_check()
        time_s = frame_index / metadata.fps
        label = f"{frame_index} | {time_s:0.1f}s"
        review_frame = _annotate_review_frame(frame, profile, frame_index)
        labels.append(label)
        saved_frames.append(review_frame)
        write_frame(output_path / f"frame_{ordinal:02d}_{frame_index:05d}.jpg", review_frame)
    if cancel_check is not None:
        cancel_check()
    contact_sheet = build_contact_sheet(saved_frames, labels)
    write_frame(output_path / "contact_sheet.jpg", contact_sheet)
