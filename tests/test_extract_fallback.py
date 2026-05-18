import numpy as np

from webcalyzer.config import default_parsing_profile
from webcalyzer.extract import _ocr_with_detection
from webcalyzer.models import Box, CalibrationSegmentConfig, FieldConfig, ProfileConfig
from webcalyzer.ocr import OCRCandidate, OCRDetection


class _FallbackBackend:
    name = "test"

    def __init__(self, strip_text: str, fallback_text: str) -> None:
        self.strip_text = strip_text
        self.fallback_text = fallback_text
        self.extract_text_calls = 0

    def extract_detections(self, image: np.ndarray, mode: str) -> list[OCRDetection]:
        return [
            OCRDetection(
                text=self.strip_text,
                variant="strip",
                x0=0,
                y0=0,
                x1=image.shape[1],
                y1=image.shape[0],
            )
        ]

    def extract_text(self, image: np.ndarray, field_kind: str) -> list[OCRCandidate]:
        self.extract_text_calls += 1
        return [OCRCandidate(text=self.fallback_text, variant="field")]

    def recognize_field_crops(self, crops: dict[str, np.ndarray]) -> dict[str, list[OCRCandidate]]:
        return {}

    def detect_image_text(self, image: np.ndarray) -> list[OCRDetection]:
        return []


def test_detection_path_retries_field_crop_for_unrecognized_unit_token() -> None:
    profile, segment = _profile_and_segment()
    backend = _FallbackBackend(strip_text="000,063 М", fallback_text="000,063 MI")

    result = _ocr_with_detection(
        frame=np.zeros((100, 200, 3), dtype=np.uint8),
        profile=profile,
        segment=segment,
        backend=backend,
    )

    assert backend.extract_text_calls == 1
    assert result["stage1_altitude"] == [("000,063 MI", "field")]


def test_detection_path_keeps_strip_ocr_when_unit_is_recognized() -> None:
    profile, segment = _profile_and_segment()
    backend = _FallbackBackend(strip_text="000,063 MI", fallback_text="000,063 FT")

    result = _ocr_with_detection(
        frame=np.zeros((100, 200, 3), dtype=np.uint8),
        profile=profile,
        segment=segment,
        backend=backend,
    )

    assert backend.extract_text_calls == 0
    assert result["stage1_altitude"] == [("000,063 MI", "strip")]


def _profile_and_segment() -> tuple[ProfileConfig, CalibrationSegmentConfig]:
    segment = CalibrationSegmentConfig(
        id="segment_1",
        start_frame_index=0,
        start_time_s=0.0,
        end_frame_index=10,
        end_time_s=1.0,
        fields={
            "stage1_altitude": FieldConfig(
                name="stage1_altitude",
                kind="altitude",
                stage="stage1",
                box=Box(0.1, 0.1, 0.5, 0.3),
            )
        },
    )
    profile = ProfileConfig(
        profile_name="test",
        description="",
        default_sample_fps=1.0,
        fixture_frame_count=1,
        fixture_time_range_s=None,
        parsing=default_parsing_profile(),
        segments=[segment],
    )
    return profile, segment
