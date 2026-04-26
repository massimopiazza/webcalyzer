from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np


@dataclass(slots=True)
class OCRCandidate:
    text: str
    variant: str


@dataclass(slots=True)
class OCRDetection:
    text: str
    variant: str
    x0: int
    y0: int
    x1: int
    y1: int


class OCRBackend(Protocol):
    """Backend-neutral OCR surface used by the extraction pipeline."""

    name: str

    def extract_detections(self, image: np.ndarray, mode: str) -> list[OCRDetection]:
        """Run a detection-driven OCR pass and return per-region detections.

        ``mode`` is one of ``"strip"`` (single-variant, used for the unioned
        telemetry strip) or ``"field:<kind>"`` (multi-variant fallback for a
        single field crop).
        """

    def extract_text(self, image: np.ndarray, field_kind: str) -> list[OCRCandidate]:
        """Run the per-field multi-variant fallback used when strip OCR fails."""

    def recognize_field_crops(
        self, crops: dict[str, np.ndarray]
    ) -> dict[str, list[OCRCandidate]]:
        """Recognition-only path that bypasses detection.

        Each crop is fed straight to the recognition step (no detection),
        which is much cheaper than a full OCR pass when bounding boxes are
        already known. Returns one candidate per field (variant ``"recog"``).
        """

    def detect_image_text(self, image: np.ndarray) -> list[OCRDetection]:
        """Run OCR on ``image`` exactly as given, without applying any further
        preprocessing variants. Used by the rescue path which produces its
        own preprocessed variants and just wants the OCR engine to read
        them verbatim.
        """


class RapidOCRBackend:
    """ONNXRuntime-backed RapidOCR backend, available on every platform."""

    name = "rapidocr"

    def __init__(self, *, intra_op_num_threads: int = -1, inter_op_num_threads: int = 1) -> None:
        from rapidocr_onnxruntime import RapidOCR

        # RapidOCR's UpdateParameters propagates Global thread settings to
        # Det/Cls/Rec automatically, so a single pair of kwargs is enough.
        self.engine = RapidOCR(
            intra_op_num_threads=intra_op_num_threads,
            inter_op_num_threads=inter_op_num_threads,
        )

    def extract_detections(self, image: np.ndarray, mode: str) -> list[OCRDetection]:
        variants = build_variants(image=image, mode=mode)
        scale = _strip_resize_scale(mode)
        detections: list[OCRDetection] = []
        for variant_name, variant_image in variants:
            result, _elapsed = self.engine(variant_image)
            if not result:
                continue
            for polygon, text, _score in result:
                normalized = " ".join(str(text).strip().split())
                if not normalized:
                    continue
                xs = [int(round(point[0] / scale)) for point in polygon]
                ys = [int(round(point[1] / scale)) for point in polygon]
                detections.append(
                    OCRDetection(
                        text=normalized,
                        variant=variant_name,
                        x0=min(xs),
                        y0=min(ys),
                        x1=max(xs),
                        y1=max(ys),
                    )
                )
        return detections

    def extract_text(self, image: np.ndarray, field_kind: str) -> list[OCRCandidate]:
        detections = self.extract_detections(image=image, mode=f"field:{field_kind}")
        per_variant: dict[str, list[OCRDetection]] = {}
        for detection in detections:
            per_variant.setdefault(detection.variant, []).append(detection)

        candidates: list[OCRCandidate] = []
        seen: set[tuple[str, str]] = set()
        for variant_name, variant_detections in per_variant.items():
            ordered = sorted(variant_detections, key=lambda item: (item.y0, item.x0))
            normalized = " ".join(item.text for item in ordered if item.text)
            if not normalized:
                continue
            key = (variant_name, normalized)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(OCRCandidate(text=normalized, variant=variant_name))
        return candidates

    def detect_image_text(self, image: np.ndarray) -> list[OCRDetection]:
        result, _elapsed = self.engine(ensure_color(image))
        if not result:
            return []
        detections: list[OCRDetection] = []
        for polygon, text, _score in result:
            normalized = " ".join(str(text).strip().split())
            if not normalized:
                continue
            xs = [int(round(point[0])) for point in polygon]
            ys = [int(round(point[1])) for point in polygon]
            detections.append(
                OCRDetection(
                    text=normalized,
                    variant="raw",
                    x0=min(xs),
                    y0=min(ys),
                    x1=max(xs),
                    y1=max(ys),
                )
            )
        return detections

    def recognize_field_crops(
        self, crops: dict[str, np.ndarray]
    ) -> dict[str, list[OCRCandidate]]:
        if not crops:
            return {}
        prepared: list[np.ndarray] = []
        keys: list[str] = []
        for field_name, crop in crops.items():
            color = ensure_color(crop)
            prepared.append(_resize_for_rec(color))
            keys.append(field_name)
        results, _elapsed = self.engine.text_rec(prepared)
        per_field: dict[str, list[OCRCandidate]] = {field_name: [] for field_name in crops}
        for field_name, (text, _score) in zip(keys, results, strict=True):
            normalized = " ".join(str(text).strip().split())
            if not normalized:
                continue
            per_field[field_name] = [OCRCandidate(text=normalized, variant="recog")]
        return per_field


# Back-compat alias: existing call sites used ``OCRRunner`` before backends.
OCRRunner = RapidOCRBackend


def ensure_color(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def _strip_resize_scale(mode: str) -> int:
    """Match the upscale used inside :func:`build_variants` so detection
    coordinates can be mapped back to the original crop space."""

    if mode == "strip":
        return 2
    field_kind = mode.split(":", 1)[1] if ":" in mode else ""
    return 2 if field_kind == "met" else 3


def _resize_for_rec(image: np.ndarray, target_height: int = 48) -> np.ndarray:
    """Resize a crop so it matches the height that the rec model expects.

    The PP-OCRv4 recognizer takes ``[3, 48, W]`` inputs. We pre-resize to
    ``target_height`` while preserving aspect ratio so the rec preprocessor
    has a consistent input.
    """

    color = ensure_color(image)
    h, w = color.shape[:2]
    if h == 0 or w == 0:
        return color
    scale = target_height / float(h)
    new_w = max(target_height, int(round(w * scale)))
    return cv2.resize(color, (new_w, target_height), interpolation=cv2.INTER_LINEAR)


def build_variants(image: np.ndarray, mode: str) -> list[tuple[str, np.ndarray]]:
    base = image.copy()
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    variants: list[tuple[str, np.ndarray]] = []

    def add_variant(name: str, img: np.ndarray, scale: int) -> None:
        resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        variants.append((name, ensure_color(resized)))

    if mode == "strip":
        add_variant("raw", base, scale=2)
        return variants

    field_kind = mode.split(":", 1)[1]
    add_variant("raw", base, scale=3 if field_kind != "met" else 2)
    add_variant("gray", gray, scale=3 if field_kind != "met" else 2)
    add_variant("clahe", clahe, scale=3 if field_kind != "met" else 2)

    width = base.shape[1]
    if field_kind in {"velocity", "altitude"} and width > 30:
        focus = base[:, int(width * 0.20) : width]
        focus_gray = cv2.cvtColor(focus, cv2.COLOR_BGR2GRAY)
        focus_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(focus_gray)
        add_variant("focus_raw", focus, scale=3)
        add_variant("focus_clahe", focus_clahe, scale=3)

    return variants


def build_rescue_variants(
    image: np.ndarray, pad_px: int = 8, tier: str = "full"
) -> list[tuple[str, np.ndarray]]:
    base = image.copy()
    if base.ndim == 2:
        base = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    color_pad = cv2.copyMakeBorder(base, pad_px, pad_px, pad_px, pad_px, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    gray_pad = cv2.copyMakeBorder(gray, pad_px, pad_px, pad_px, pad_px, cv2.BORDER_CONSTANT, value=0)

    variants: list[tuple[str, np.ndarray]] = []

    def add(name: str, img: np.ndarray, scale: int, interp: int = cv2.INTER_CUBIC) -> None:
        resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)
        variants.append((name, ensure_color(resized)))

    add("col_x3", color_pad, 3)
    add("gry_x3", gray_pad, 3)
    thresh_b21 = cv2.adaptiveThreshold(
        gray_pad, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 2
    )
    add("adapt_b21", thresh_b21, 3)

    if tier == "fast":
        return variants

    add("col_x2", color_pad, 2)
    add("col_x4", color_pad, 4)
    add("gry_x2", gray_pad, 2)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray_pad)
    add("clahe_x3", clahe, 3)

    if tier == "medium":
        return variants

    for block in (15, 31):
        thresh = cv2.adaptiveThreshold(
            gray_pad, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 2
        )
        add(f"adapt_b{block}", thresh, 3)
    _, otsu = cv2.threshold(gray_pad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    add("otsu", otsu, 3)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharp = cv2.filter2D(gray_pad, -1, kernel)
    add("sharp", sharp, 3)
    return variants


class RescueOCR:
    def __init__(self, backend: OCRBackend) -> None:
        self.backend = backend

    def _run_variants(
        self, variants: list[tuple[str, np.ndarray]]
    ) -> list[OCRCandidate]:
        candidates: list[OCRCandidate] = []
        seen: set[tuple[str, str]] = set()
        for variant_name, variant_image in variants:
            # Rescue variants are already preprocessed (padded, scaled,
            # thresholded), so run OCR on them verbatim instead of layering
            # another set of variants on top.
            detections = self.backend.detect_image_text(variant_image)
            if not detections:
                continue
            ordered = sorted(detections, key=lambda d: (d.y0, d.x0))
            joined = " ".join(d.text for d in ordered if d.text)
            if not joined:
                continue
            key = (variant_name, joined)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(OCRCandidate(text=joined, variant=f"rescue:{variant_name}"))
        return candidates

    def extract(self, image: np.ndarray, tier: str = "full") -> list[OCRCandidate]:
        variants = build_rescue_variants(image, tier=tier)
        return self._run_variants(variants)
