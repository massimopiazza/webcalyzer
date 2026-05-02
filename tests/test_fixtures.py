from pathlib import Path

import numpy as np

from webcalyzer.fixtures import REVIEW_FIELD_COLORS, generate_review_frames
from webcalyzer.models import Box, FieldConfig, ProfileConfig, VideoMetadata


def test_generate_review_frames_writes_box_overlays(monkeypatch, tmp_path: Path) -> None:
    source_frame = np.zeros((80, 120, 3), dtype=np.uint8)
    metadata = VideoMetadata(
        path=Path("video.mp4"),
        width=120,
        height=80,
        fps=10.0,
        frame_count=100,
        duration_s=10.0,
    )
    profile = ProfileConfig(
        profile_name="test",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        fields={
            "stage1_velocity": FieldConfig(
                name="stage1_velocity",
                kind="velocity",
                stage="stage1",
                box=Box(0.25, 0.25, 0.75, 0.75),
            ),
        },
    )
    written: dict[str, np.ndarray] = {}

    monkeypatch.setattr("webcalyzer.fixtures.get_video_metadata", lambda _video_path: metadata)
    monkeypatch.setattr(
        "webcalyzer.fixtures.evenly_spaced_indices",
        lambda _metadata, _count, time_range_s=None: [12],
    )
    monkeypatch.setattr(
        "webcalyzer.fixtures.iterate_frames",
        lambda _video_path, _indices: [(12, source_frame)],
    )

    def write_frame(path: str | Path, frame: np.ndarray) -> Path:
        target = Path(path)
        written[target.name] = frame.copy()
        return target

    monkeypatch.setattr("webcalyzer.fixtures.write_frame", write_frame)

    generate_review_frames("video.mp4", profile, tmp_path)

    review_frame = written["frame_00_00012.jpg"]
    expected_color = np.array(REVIEW_FIELD_COLORS[0], dtype=np.uint8)
    assert np.any(np.all(review_frame == expected_color, axis=2))
    assert "contact_sheet.jpg" in written
    assert not np.any(source_frame)
