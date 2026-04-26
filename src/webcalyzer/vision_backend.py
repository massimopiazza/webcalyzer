"""Apple Vision (``VNRecognizeTextRequest``) OCR backend.

This module is only importable on macOS with ``pyobjc-framework-Vision`` and
``pyobjc-framework-Quartz`` installed. The :func:`is_available` helper is the
import-safe gate used by the backend factory.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

from webcalyzer.ocr import OCRCandidate, OCRDetection, ensure_color


def is_available() -> bool:
    """Return ``True`` iff the Vision framework can be imported on this host."""

    try:
        import platform

        if platform.system() != "Darwin":
            return False
        import Vision  # noqa: F401
        import Quartz  # noqa: F401
    except ImportError:
        return False
    return True


_TELEMETRY_CUSTOM_WORDS = (
    "MPH",
    "FT",
    "MI",
    "STAGE",
    "T+",
    "T-",
    "VELOCITY",
    "ALTITUDE",
)


class VisionBackend:
    """OCR backend backed by Apple's Vision framework.

    Each call wraps the input ndarray in a ``CGImage`` and runs a
    ``VNRecognizeTextRequest``. The framework runs on the ANE/GPU
    automatically on Apple Silicon and is dramatically faster than
    CPU-bound ONNX inference for printed digit overlays.
    """

    name = "vision"

    def __init__(self, *, recognition_level: str = "accurate") -> None:
        if not is_available():
            raise RuntimeError(
                "Vision backend requires macOS with pyobjc-framework-Vision "
                "and pyobjc-framework-Quartz installed."
            )
        import Vision

        self._recognition_level_name = recognition_level
        if recognition_level == "fast":
            self._recognition_level = Vision.VNRequestTextRecognitionLevelFast
        elif recognition_level == "accurate":
            self._recognition_level = Vision.VNRequestTextRecognitionLevelAccurate
        else:
            raise ValueError(
                f"Unknown recognition_level={recognition_level!r}; expected 'accurate' or 'fast'."
            )

    def extract_detections(self, image: np.ndarray, mode: str) -> list[OCRDetection]:
        observations = self._recognize(image)
        height, width = image.shape[:2]
        detections: list[OCRDetection] = []
        for text, bbox in observations:
            normalized = " ".join(str(text).strip().split())
            if not normalized:
                continue
            x0, y0, x1, y1 = _bbox_to_pixel_xyxy(bbox, width=width, height=height)
            detections.append(
                OCRDetection(
                    text=normalized,
                    variant="vision",
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                )
            )
        return detections

    def detect_image_text(self, image: np.ndarray) -> list[OCRDetection]:
        return self.extract_detections(image, mode="strip")

    def extract_text(self, image: np.ndarray, field_kind: str) -> list[OCRCandidate]:
        observations = self._recognize(image)
        if not observations:
            return []
        ordered = sorted(observations, key=lambda obs: (obs[1].origin.y * -1, obs[1].origin.x))
        joined = " ".join(str(obs[0]).strip() for obs in ordered if str(obs[0]).strip())
        if not joined:
            return []
        return [OCRCandidate(text=joined, variant="vision")]

    def recognize_field_crops(
        self, crops: dict[str, np.ndarray]
    ) -> dict[str, list[OCRCandidate]]:
        results: dict[str, list[OCRCandidate]] = {field_name: [] for field_name in crops}
        for field_name, crop in crops.items():
            observations = self._recognize(crop)
            if not observations:
                continue
            ordered = sorted(observations, key=lambda obs: (obs[1].origin.y * -1, obs[1].origin.x))
            joined = " ".join(str(obs[0]).strip() for obs in ordered if str(obs[0]).strip())
            if not joined:
                continue
            results[field_name] = [OCRCandidate(text=joined, variant="vision:recog")]
        return results

    def _recognize(self, image: np.ndarray) -> list[tuple[str, "Rect"]]:
        import Vision
        import Quartz

        bgr = ensure_color(image)
        rgb = bgr[:, :, ::-1].copy()  # BGR → RGB; Vision expects RGB(A) byte order
        cg_image = _ndarray_to_cgimage(rgb)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            cg_image, {}
        )
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(self._recognition_level)
        request.setUsesLanguageCorrection_(False)
        request.setRecognitionLanguages_(["en-US"])
        request.setCustomWords_(list(_TELEMETRY_CUSTOM_WORDS))
        request.setMinimumTextHeight_(0.0)
        success, _error = handler.performRequests_error_([request], None)
        if not success:
            return []
        observations = request.results() or []
        results: list[tuple[str, Rect]] = []
        for observation in observations:
            top_candidate = observation.topCandidates_(1)
            if not top_candidate:
                continue
            text = str(top_candidate[0].string())
            bbox = observation.boundingBox()
            results.append((text, bbox))
        return results


class Rect:
    """Small adapter so type-hints don't need to import Vision at module load."""

    origin: object
    size: object


def _ndarray_to_cgimage(rgb: np.ndarray):
    """Wrap an RGB uint8 ndarray in a ``CGImage`` without copying twice."""

    import Quartz
    import CoreFoundation
    import Foundation

    if rgb.dtype != np.uint8:
        rgb = rgb.astype(np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Expected an HxWx3 uint8 array.")
    height, width, _ = rgb.shape
    rgb_contig = np.ascontiguousarray(rgb)

    color_space = Quartz.CGColorSpaceCreateDeviceRGB()
    bytes_per_row = width * 3
    data_provider = Quartz.CGDataProviderCreateWithData(
        None, rgb_contig.tobytes(), height * bytes_per_row, None
    )
    bitmap_info = Quartz.kCGBitmapByteOrderDefault | Quartz.kCGImageAlphaNone
    image = Quartz.CGImageCreate(
        width,
        height,
        8,  # bits per component
        24,  # bits per pixel
        bytes_per_row,
        color_space,
        bitmap_info,
        data_provider,
        None,
        False,
        Quartz.kCGRenderingIntentDefault,
    )
    return image


def _bbox_to_pixel_xyxy(bbox, *, width: int, height: int) -> tuple[int, int, int, int]:
    """Convert a Vision normalized bounding box (origin bottom-left) into
    pixel (x0, y0, x1, y1) with origin top-left, the convention the rest of
    the pipeline uses."""

    x0_norm = float(bbox.origin.x)
    y0_norm = float(bbox.origin.y)
    w_norm = float(bbox.size.width)
    h_norm = float(bbox.size.height)
    x0 = int(round(x0_norm * width))
    x1 = int(round((x0_norm + w_norm) * width))
    # Vision's y axis grows upward; flip to image coordinates.
    y0 = int(round((1.0 - (y0_norm + h_norm)) * height))
    y1 = int(round((1.0 - y0_norm) * height))
    x0 = max(0, min(width - 1, x0))
    x1 = max(x0 + 1, min(width, x1))
    y0 = max(0, min(height - 1, y0))
    y1 = max(y0 + 1, min(height, y1))
    return x0, y0, x1, y1
