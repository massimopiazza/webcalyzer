from __future__ import annotations

from pathlib import Path

from webcalyzer.models import ProfileConfig
from webcalyzer.video import build_contact_sheet, evenly_spaced_indices, get_video_metadata, iterate_frames, write_frame


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
        labels.append(label)
        saved_frames.append(frame)
        write_frame(output_path / f"frame_{ordinal:02d}_{frame_index:05d}.jpg", frame)
    contact_sheet = build_contact_sheet(saved_frames, labels)
    write_frame(output_path / "contact_sheet.jpg", contact_sheet)
