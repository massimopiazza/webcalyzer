from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from webcalyzer.config import save_profile
from webcalyzer.models import Box, ProfileConfig
from webcalyzer.video import draw_box, iterate_frames


FIELD_COLORS: list[tuple[int, int, int]] = [
    (255, 128, 64),
    (64, 200, 255),
    (120, 255, 120),
    (200, 120, 255),
    (255, 220, 80),
]


@dataclass
class _MouseState:
    active: bool = False
    start: tuple[int, int] | None = None
    current: tuple[int, int] | None = None


def _build_fixture_frame_indices(video_frame_count: int, fps: float, reference_times_s: list[float], fallback_count: int) -> list[int]:
    if reference_times_s:
        indices = [int(round(time_s * fps)) for time_s in reference_times_s]
        return [max(0, min(video_frame_count - 1, index)) for index in indices]
    if fallback_count <= 1:
        return [0]
    return [int(round(index)) for index in np.linspace(0, video_frame_count - 1, fallback_count)]


def launch_calibration_ui(
    video_path: str | Path,
    profile: ProfileConfig,
    output_path: str | Path,
    video_frame_count: int,
    video_fps: float,
) -> Path:
    frame_indices = _build_fixture_frame_indices(
        video_frame_count=video_frame_count,
        fps=video_fps,
        reference_times_s=profile.fixture_reference_times_s,
        fallback_count=profile.fixture_frame_count,
    )
    fixtures = iterate_frames(video_path, frame_indices)
    if not fixtures:
        raise RuntimeError("No calibration frames could be loaded from the video.")

    mouse_state = _MouseState()
    window_name = "webcalyzer calibration"
    field_names = profile.ordered_field_names()
    selected_index = 0
    frame_cursor = 0
    save_target = Path(output_path)

    def on_mouse(event: int, x: int, y: int, _flags: int, _userdata: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            mouse_state.active = True
            mouse_state.start = (x, y)
            mouse_state.current = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and mouse_state.active:
            mouse_state.current = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and mouse_state.active:
            mouse_state.active = False
            mouse_state.current = (x, y)
            frame = fixtures[frame_cursor][1]
            height, width = frame.shape[:2]
            x0 = min(mouse_state.start[0], mouse_state.current[0]) / width
            y0 = min(mouse_state.start[1], mouse_state.current[1]) / height
            x1 = max(mouse_state.start[0], mouse_state.current[0]) / width
            y1 = max(mouse_state.start[1], mouse_state.current[1]) / height
            profile.fields[field_names[selected_index]].box = Box(x0, y0, x1, y1).clamp()

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        frame_index, frame = fixtures[frame_cursor]
        canvas = frame.copy()
        for idx, field_name in enumerate(field_names):
            canvas = draw_box(
                canvas,
                profile.fields[field_name].box,
                label=f"{idx + 1}: {field_name}",
                color=FIELD_COLORS[idx % len(FIELD_COLORS)],
            )

        if mouse_state.active and mouse_state.start and mouse_state.current:
            cv2.rectangle(canvas, mouse_state.start, mouse_state.current, FIELD_COLORS[selected_index], 2)

        overlay_lines = [
            f"frame {frame_cursor + 1}/{len(fixtures)} | source index {frame_index}",
            f"selected field: {selected_index + 1} {field_names[selected_index]}",
            "keys: 1-5 select field | n/p change frame | c clear | s save | q quit",
        ]
        for row_index, line in enumerate(overlay_lines):
            y = 30 + row_index * 28
            cv2.rectangle(canvas, (10, y - 22), (920, y + 6), (0, 0, 0), -1)
            cv2.putText(canvas, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.imshow(window_name, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key == ord("q"):
            break
        if key == ord("n"):
            frame_cursor = (frame_cursor + 1) % len(fixtures)
        elif key == ord("p"):
            frame_cursor = (frame_cursor - 1) % len(fixtures)
        elif key == ord("c"):
            profile.fields[field_names[selected_index]].box = Box(0.0, 0.0, 0.0, 0.0)
        elif key == ord("s"):
            save_profile(profile, save_target)
        elif ord("1") <= key <= ord(str(min(9, len(field_names)))):
            selected_index = key - ord("1")

    cv2.destroyWindow(window_name)
    return save_profile(profile, save_target)
