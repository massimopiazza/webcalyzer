from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from webcalyzer.models import Box, VideoMetadata


def open_capture(video_path: str | Path) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")
    return capture


def get_video_metadata(video_path: str | Path) -> VideoMetadata:
    path = Path(video_path)
    capture = open_capture(path)
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    capture.release()
    duration_s = frame_count / fps if fps else 0.0
    return VideoMetadata(
        path=path,
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration_s=duration_s,
    )


def build_sample_indices(metadata: VideoMetadata, target_fps: float, start_s: float = 0.0, end_s: float | None = None) -> list[int]:
    if target_fps <= 0:
        raise ValueError("target_fps must be positive")
    end_s = metadata.duration_s if end_s is None else min(end_s, metadata.duration_s)
    sample_times = np.arange(start_s, end_s + 1e-9, 1.0 / target_fps)
    indices = np.rint(sample_times * metadata.fps).astype(int)
    indices = np.clip(indices, 0, metadata.frame_count - 1)
    deduped: list[int] = []
    seen: set[int] = set()
    for index in indices:
        if int(index) not in seen:
            seen.add(int(index))
            deduped.append(int(index))
    return deduped


def evenly_spaced_indices(metadata: VideoMetadata, count: int) -> list[int]:
    if count <= 0:
        raise ValueError("count must be positive")
    if count == 1:
        return [0]
    values = np.linspace(0, metadata.frame_count - 1, num=count)
    return [int(round(value)) for value in values]


def read_frame(video_path: str | Path, frame_index: int) -> np.ndarray:
    capture = open_capture(video_path)
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    capture.release()
    if not ok or frame is None:
        raise RuntimeError(f"Failed to read frame {frame_index} from {video_path}")
    return frame


def iterate_frames(video_path: str | Path, frame_indices: list[int]) -> list[tuple[int, np.ndarray]]:
    capture = open_capture(video_path)
    result: list[tuple[int, np.ndarray]] = []
    for frame_index in frame_indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok or frame is None:
            continue
        result.append((frame_index, frame))
    capture.release()
    return result


def crop_box(frame: np.ndarray, box: Box) -> np.ndarray:
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = box.as_int_xyxy(width=width, height=height)
    return frame[y0:y1, x0:x1].copy()


def draw_box(frame: np.ndarray, box: Box, label: str, color: tuple[int, int, int]) -> np.ndarray:
    output = frame.copy()
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = box.as_int_xyxy(width=width, height=height)
    cv2.rectangle(output, (x0, y0), (x1, y1), color, 2)
    cv2.rectangle(output, (x0, max(0, y0 - 28)), (x0 + 220, y0), color, -1)
    cv2.putText(output, label, (x0 + 6, max(18, y0 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)
    return output


def write_frame(path: str | Path, frame: np.ndarray) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), frame):
        raise RuntimeError(f"Failed to write image: {target}")
    return target


def build_contact_sheet(frames: list[np.ndarray], labels: list[str], columns: int = 4, thumb_width: int = 480) -> np.ndarray:
    if not frames:
        raise ValueError("frames must not be empty")
    thumbs: list[np.ndarray] = []
    for frame, label in zip(frames, labels, strict=True):
        height, width = frame.shape[:2]
        thumb_height = int(round(height * thumb_width / width))
        thumb = cv2.resize(frame, (thumb_width, thumb_height))
        cv2.rectangle(thumb, (0, 0), (260, 40), (0, 0, 0), -1)
        cv2.putText(thumb, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        thumbs.append(thumb)

    margin = 10
    rows = int(np.ceil(len(thumbs) / columns))
    thumb_height = thumbs[0].shape[0]
    thumb_width = thumbs[0].shape[1]
    canvas_height = rows * thumb_height + (rows + 1) * margin
    canvas_width = columns * thumb_width + (columns + 1) * margin
    canvas = np.full((canvas_height, canvas_width, 3), 245, dtype=np.uint8)

    for index, thumb in enumerate(thumbs):
        row = index // columns
        col = index % columns
        x = margin + col * (thumb_width + margin)
        y = margin + row * (thumb_height + margin)
        canvas[y : y + thumb_height, x : x + thumb_width] = thumb
    return canvas
