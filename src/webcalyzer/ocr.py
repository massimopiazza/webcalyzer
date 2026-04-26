from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR


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


class OCRRunner:
    def __init__(self) -> None:
        self.engine = RapidOCR()

    def extract_detections(self, image: np.ndarray, mode: str) -> list[OCRDetection]:
        variants = build_variants(image=image, mode=mode)
        detections: list[OCRDetection] = []
        for variant_name, variant_image in variants:
            result, _elapsed = self.engine(variant_image)
            if not result:
                continue
            for polygon, text, _score in result:
                normalized = " ".join(str(text).strip().split())
                if not normalized:
                    continue
                xs = [int(round(point[0])) for point in polygon]
                ys = [int(round(point[1])) for point in polygon]
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


def ensure_color(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


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
    def __init__(self, runner: OCRRunner) -> None:
        self.runner = runner

    def _run_variants(
        self, variants: list[tuple[str, np.ndarray]]
    ) -> list[OCRCandidate]:
        candidates: list[OCRCandidate] = []
        seen: set[tuple[str, str]] = set()
        for variant_name, variant_image in variants:
            result, _elapsed = self.runner.engine(variant_image)
            if not result:
                continue
            parts: list[tuple[int, int, str]] = []
            for polygon, text, _score in result:
                normalized = " ".join(str(text).strip().split())
                if not normalized:
                    continue
                ys = [int(round(point[1])) for point in polygon]
                xs = [int(round(point[0])) for point in polygon]
                parts.append((min(ys), min(xs), normalized))
            if not parts:
                continue
            parts.sort()
            joined = " ".join(text for _y, _x, text in parts)
            key = (variant_name, joined)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(OCRCandidate(text=joined, variant=f"rescue:{variant_name}"))
        return candidates

    def extract(self, image: np.ndarray, tier: str = "full") -> list[OCRCandidate]:
        variants = build_rescue_variants(image, tier=tier)
        return self._run_variants(variants)
