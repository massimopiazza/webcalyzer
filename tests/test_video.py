from pathlib import Path

from webcalyzer.models import VideoMetadata
from webcalyzer.video import build_sample_indices


def test_sample_indices_are_rounded_without_duplicates() -> None:
    metadata = VideoMetadata(
        path=Path("dummy.mp4"),
        width=1920,
        height=1080,
        fps=59.94,
        frame_count=100,
        duration_s=100 / 59.94,
    )
    indices = build_sample_indices(metadata=metadata, target_fps=2.5)
    assert indices == sorted(indices)
    assert len(indices) == len(set(indices))
    assert indices[0] == 0
