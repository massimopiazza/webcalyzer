from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from webcalyzer.config import save_profile
from webcalyzer.models import (
    Box,
    CANONICAL_FIELD_ORDER,
    CalibrationSegmentConfig,
    CalibrationVideoConfig,
    FieldConfig,
    ProfileConfig,
)
from webcalyzer.quantities import (
    default_quantity_library_dir,
    is_default_quantity_id,
    load_quantity_library,
    normalize_quantity_mapping,
    save_quantity_library,
    upsert_quantity,
)
from webcalyzer.video import draw_box, read_frame


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


def _build_fixture_frame_indices(
    video_frame_count: int,
    fps: float,
    time_range_s: tuple[float, float] | None,
    fallback_count: int,
) -> list[int]:
    if fallback_count <= 1:
        start_s = min(time_range_s) if time_range_s is not None else 0.0
        return [max(0, min(video_frame_count - 1, int(round(start_s * fps))))]

    duration_s = video_frame_count / fps if fps else 0.0
    start_s = 0.0
    end_s = duration_s
    if time_range_s is not None:
        lower, upper = sorted((float(time_range_s[0]), float(time_range_s[1])))
        start_s = max(0.0, min(lower, duration_s))
        end_s = max(start_s, min(upper, duration_s))

    indices = [int(round(index)) for index in np.linspace(start_s * fps, end_s * fps, fallback_count)]
    return [max(0, min(video_frame_count - 1, index)) for index in indices]


def launch_calibration_ui(
    video_path: str | Path,
    profile: ProfileConfig,
    output_path: str | Path,
    video_frame_count: int,
    video_fps: float,
    video_width: int | None = None,
    video_height: int | None = None,
    templates_dir: str | Path = "configs",
) -> Path:
    library_dir = default_quantity_library_dir(templates_dir)
    _ensure_calibration_video(profile, video_path, video_frame_count, video_fps, video_width, video_height)
    _ensure_segments(profile, video_frame_count, video_fps)
    mouse_state = _MouseState()
    window_name = "webcalyzer calibration"
    selected_index = 0
    current_frame_index = profile.segments[0].start_frame_index if profile.segments else 0
    save_target = Path(output_path)

    def on_mouse(event: int, x: int, y: int, _flags: int, _userdata: object) -> None:
        nonlocal selected_index
        segment = _active_segment(profile, current_frame_index)
        field_names = _field_names(profile)
        selected_index = max(0, min(len(field_names) - 1, selected_index))
        field_name = field_names[selected_index]
        field_cfg = segment.fields.get(field_name)
        if field_cfg is None:
            return
        if event == cv2.EVENT_LBUTTONDOWN:
            mouse_state.active = True
            mouse_state.start = (x, y)
            mouse_state.current = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and mouse_state.active:
            mouse_state.current = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and mouse_state.active:
            mouse_state.active = False
            mouse_state.current = (x, y)
            frame = read_frame(video_path, current_frame_index)
            height, width = frame.shape[:2]
            x0 = min(mouse_state.start[0], mouse_state.current[0]) / width
            y0 = min(mouse_state.start[1], mouse_state.current[1]) / height
            x1 = max(mouse_state.start[0], mouse_state.current[0]) / width
            y1 = max(mouse_state.start[1], mouse_state.current[1]) / height
            field_cfg.box = Box(x0, y0, x1, y1).clamp()
            selected_index = _next_enabled_field_index(profile, segment, selected_index)

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        current_frame_index = max(0, min(video_frame_count - 1, current_frame_index))
        frame = read_frame(video_path, current_frame_index)
        segment = _active_segment(profile, current_frame_index)
        field_names = _field_names(profile)
        selected_index = max(0, min(len(field_names) - 1, selected_index))
        selected_field = field_names[selected_index]
        canvas = frame.copy()
        for idx, field_name in enumerate(segment.ordered_field_names()):
            field = segment.fields[field_name]
            if field.box is None:
                continue
            canvas = draw_box(
                canvas,
                field.box,
                label=f"{idx + 1}: {field_name}",
                color=FIELD_COLORS[idx % len(FIELD_COLORS)],
            )

        if mouse_state.active and mouse_state.start and mouse_state.current:
            cv2.rectangle(canvas, mouse_state.start, mouse_state.current, FIELD_COLORS[selected_index % len(FIELD_COLORS)], 2)

        slot_enabled = selected_field in segment.fields
        time_s = current_frame_index / video_fps if video_fps else 0.0
        overlay_lines = [
            f"frame {current_frame_index}/{video_frame_count - 1} | time {time_s:.3f}s | {segment.id}",
            f"segment frames [{segment.start_frame_index}, {segment.end_frame_index})",
            f"selected slot: {selected_index + 1} {selected_field} | {'enabled' if slot_enabled else 'disabled'}",
            "keys: 1-9 slot | arrows cycle | e toggle | [/]-1/+1 frame | n/p +/-1s | a split",
            "keys: g add custom | G create custom | b/v crop start/end | t jump | c clear | tab segment | s save | q quit",
        ]
        for row_index, line in enumerate(overlay_lines):
            y = 30 + row_index * 28
            cv2.rectangle(canvas, (10, y - 22), (1200, y + 6), (0, 0, 0), -1)
            cv2.putText(canvas, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.imshow(window_name, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key == ord("q"):
            break
        if key == ord("n"):
            current_frame_index = min(video_frame_count - 1, current_frame_index + max(1, int(round(video_fps))))
        elif key == ord("p"):
            current_frame_index = max(0, current_frame_index - max(1, int(round(video_fps))))
        elif key == ord("]"):
            current_frame_index = min(video_frame_count - 1, current_frame_index + 1)
        elif key == ord("["):
            current_frame_index = max(0, current_frame_index - 1)
        elif key == ord("a"):
            _split_segment(profile, current_frame_index, video_fps)
        elif key == ord("g"):
            _add_existing_custom_quantity(profile, library_dir)
        elif key == ord("G"):
            _create_custom_quantity(profile, library_dir)
        elif key == ord("b"):
            _set_crop_start(profile, current_frame_index, video_fps)
        elif key == ord("v"):
            _set_crop_end(profile, current_frame_index + 1, video_fps)
        elif key == ord("t"):
            try:
                text = input("Jump to timestamp seconds: ").strip()
                current_frame_index = int(round(float(text) * video_fps))
            except ValueError:
                print("Invalid timestamp")
        elif key == 9:
            current_frame_index = _next_segment_start(profile, segment.id)
        elif key == ord("c"):
            field_cfg = segment.fields.get(selected_field)
            if field_cfg is not None:
                field_cfg.box = None
        elif key == ord("e"):
            _toggle_field(profile, segment, selected_field)
        elif key == ord("s"):
            save_profile(profile, save_target)
        elif key in {81, 83}:
            direction = -1 if key == 81 else 1
            selected_index = (selected_index + direction) % max(1, len(field_names))
        elif ord("1") <= key <= ord(str(min(9, len(field_names)))):
            selected_index = key - ord("1")

    cv2.destroyWindow(window_name)
    return save_profile(profile, save_target)


def _ensure_calibration_video(
    profile: ProfileConfig,
    video_path: str | Path,
    video_frame_count: int,
    video_fps: float,
    video_width: int | None,
    video_height: int | None,
) -> None:
    profile.calibration_video = CalibrationVideoConfig(
        path=str(video_path),
        fps=video_fps,
        frame_count=video_frame_count,
        width=video_width if video_width is not None else profile.calibration_video.width,
        height=video_height if video_height is not None else profile.calibration_video.height,
    )


def _ensure_segments(profile: ProfileConfig, video_frame_count: int, video_fps: float) -> None:
    if profile.segments and any(segment.end_frame_index > segment.start_frame_index for segment in profile.segments):
        return
    existing_fields = profile.segments[0].fields if profile.segments else {}
    fields = existing_fields if existing_fields else _default_fields(profile)
    profile.segments = [
        CalibrationSegmentConfig(
            id="segment_1",
            start_frame_index=0,
            start_time_s=0.0,
            end_frame_index=video_frame_count,
            end_time_s=_time_s(video_frame_count, video_fps),
            visible_fields=list(fields),
            fields=fields,
        )
    ]


def _active_segment(profile: ProfileConfig, frame_index: int) -> CalibrationSegmentConfig:
    segment = profile.active_segment_for_frame(frame_index)
    if segment is not None:
        return segment
    if not profile.segments:
        raise RuntimeError("No calibration segments are configured")
    if frame_index < profile.segments[0].start_frame_index:
        return profile.segments[0]
    return profile.segments[-1]


def _toggle_field(profile: ProfileConfig, segment: CalibrationSegmentConfig, field_name: str) -> None:
    if field_name in segment.fields:
        del segment.fields[field_name]
    elif field_name.startswith("custom_"):
        quantity = profile.custom_quantity_by_field_name(field_name)
        if quantity is None:
            raise RuntimeError("Custom fields must be added from the quantity library before toggling")
        if field_name not in segment.visible_fields:
            segment.visible_fields.append(field_name)
        segment.fields[field_name] = FieldConfig.custom(field_name, quantity.id, box=None)
    else:
        if field_name not in segment.visible_fields:
            segment.visible_fields.append(field_name)
        segment.fields[field_name] = FieldConfig.canonical(field_name, box=None)


def _default_fields(profile: ProfileConfig | None = None) -> dict[str, FieldConfig]:
    fields = {field_name: FieldConfig.canonical(field_name, box=None) for field_name in CANONICAL_FIELD_ORDER}
    if profile is not None:
        for quantity in profile.custom_telemetry_quantities:
            fields[quantity.field_name()] = FieldConfig.custom(quantity.field_name(), quantity.id, box=None)
    return fields


def _next_enabled_field_index(profile: ProfileConfig, segment: CalibrationSegmentConfig, selected_index: int) -> int:
    field_names = _field_names(profile)
    if not field_names:
        return selected_index
    for offset in range(1, len(field_names) + 1):
        candidate_index = (selected_index + offset) % len(field_names)
        if field_names[candidate_index] in segment.fields:
            return candidate_index
    return selected_index


def _split_segment(profile: ProfileConfig, frame_index: int, fps: float) -> None:
    for index, segment in enumerate(profile.segments):
        if segment.start_frame_index < frame_index < segment.end_frame_index:
            new_segment = CalibrationSegmentConfig(
                id="segment_new",
                start_frame_index=frame_index,
                start_time_s=_time_s(frame_index, fps),
                end_frame_index=segment.end_frame_index,
                end_time_s=segment.end_time_s,
                visible_fields=list(segment.visible_fields),
                fields={
                    name: FieldConfig(
                        name=field.name,
                        kind=field.kind,
                        stage=field.stage,
                        box=Box(*field.box.normalized_tuple()) if field.box is not None else None,
                        quantity_id=field.quantity_id,
                    )
                    for name, field in segment.fields.items()
                },
            )
            segment.end_frame_index = frame_index
            segment.end_time_s = _time_s(frame_index, fps)
            profile.segments.insert(index + 1, new_segment)
            _renumber_segments(profile)
            return


def _set_crop_start(profile: ProfileConfig, frame_index: int, fps: float) -> None:
    if not profile.segments:
        return
    first = profile.segments[0]
    first.start_frame_index = min(frame_index, first.end_frame_index - 1)
    first.start_time_s = _time_s(first.start_frame_index, fps)


def _set_crop_end(profile: ProfileConfig, frame_index: int, fps: float) -> None:
    if not profile.segments:
        return
    last = profile.segments[-1]
    last.end_frame_index = max(frame_index, last.start_frame_index + 1)
    last.end_time_s = _time_s(last.end_frame_index, fps)


def _next_segment_start(profile: ProfileConfig, current_id: str) -> int:
    if not profile.segments:
        return 0
    ids = [segment.id for segment in profile.segments]
    try:
        index = ids.index(current_id)
    except ValueError:
        return profile.segments[0].start_frame_index
    return profile.segments[(index + 1) % len(profile.segments)].start_frame_index


def _renumber_segments(profile: ProfileConfig) -> None:
    for index, segment in enumerate(profile.segments, start=1):
        segment.id = f"segment_{index}"


def _time_s(frame_index: int, fps: float) -> float:
    return float(frame_index) / float(fps) if fps else 0.0


def _field_names(profile: ProfileConfig) -> list[str]:
    names = list(CANONICAL_FIELD_ORDER)
    for quantity in profile.custom_telemetry_quantities:
        field_name = quantity.field_name()
        if field_name not in names:
            names.append(field_name)
    return names


def _add_existing_custom_quantity(profile: ProfileConfig, library_dir: str | Path) -> None:
    try:
        quantities = [
            quantity
            for quantity in load_quantity_library(library_dir)
            if not is_default_quantity_id(quantity.id)
        ]
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load quantity library: {exc}")
        return
    if not quantities:
        print("No custom quantities in library. Press G to create one.")
        return
    for index, quantity in enumerate(quantities, start=1):
        print(f"{index}: {quantity.name} [{quantity.display_unit}] {quantity.dimensionality}")
    try:
        selected = int(input("Add custom quantity number: ").strip())
    except ValueError:
        print("Invalid selection")
        return
    if not 1 <= selected <= len(quantities):
        print("Selection out of range")
        return
    _add_custom_quantity_to_profile(profile, quantities[selected - 1])


def _create_custom_quantity(profile: ProfileConfig, library_dir: str | Path) -> None:
    name = input("Quantity name: ").strip()
    dimensionality = input("Dimensionality (e.g. L/T^2): ").strip()
    display_unit = input("Display unit (e.g. m/s^2): ").strip()
    description = input("Description (optional): ").strip()
    aliases: dict[str, str] = {}
    while True:
        entry = input("Unit alias ALIAS=UNIT, blank to finish: ").strip()
        if not entry:
            break
        if "=" not in entry:
            print("Expected ALIAS=UNIT")
            continue
        alias, unit = entry.split("=", 1)
        if alias.strip() and unit.strip():
            aliases[alias.strip()] = unit.strip()
    try:
        quantity = normalize_quantity_mapping(
            {
                "name": name,
                "dimensionality": dimensionality,
                "display_unit": display_unit,
                "description": description,
                "unit_aliases": aliases,
            }
        )
        quantities = upsert_quantity(load_quantity_library(library_dir), quantity)
        save_quantity_library(library_dir, quantities)
        _add_custom_quantity_to_profile(profile, quantity)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not create quantity: {exc}")


def _add_custom_quantity_to_profile(profile: ProfileConfig, quantity) -> None:
    if all(current.id != quantity.id for current in profile.custom_telemetry_quantities):
        profile.custom_telemetry_quantities.append(quantity)
    field_name = quantity.field_name()
    for segment in profile.segments:
        if field_name not in segment.fields:
            segment.fields[field_name] = FieldConfig.custom(field_name, quantity.id, box=None)
    print(f"Added {quantity.name} to all segments")
