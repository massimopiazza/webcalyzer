"""Factory + settings for selecting and building OCR backends.

The factory keeps backend resolution in one place so that workers spawned
for parallel OCR can reconstruct the exact same backend by passing
:class:`OCRBackendOptions` through the multiprocessing boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from webcalyzer.ocr import OCRBackend, RapidOCRBackend


_VALID_BACKENDS = ("auto", "rapidocr", "vision")
_VALID_RECOGNITION_LEVELS = ("accurate", "fast")


@dataclass(frozen=True, slots=True)
class OCRBackendOptions:
    backend: str = "auto"
    recognition_level: str = "accurate"
    intra_op_num_threads: int = -1
    inter_op_num_threads: int = 1
    custom_words: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> "OCRBackendOptions":
        if self.backend not in _VALID_BACKENDS:
            raise ValueError(
                f"Unknown ocr backend {self.backend!r}; expected one of {_VALID_BACKENDS}."
            )
        if self.recognition_level not in _VALID_RECOGNITION_LEVELS:
            raise ValueError(
                f"Unknown recognition level {self.recognition_level!r}; expected one of "
                f"{_VALID_RECOGNITION_LEVELS}."
            )
        return self


def resolve_backend_name(name: str) -> str:
    """Resolve ``"auto"`` to a concrete backend name based on the host."""

    if name not in _VALID_BACKENDS:
        raise ValueError(
            f"Unknown ocr backend {name!r}; expected one of {_VALID_BACKENDS}."
        )
    if name != "auto":
        return name

    try:
        from webcalyzer.vision_backend import is_available as vision_is_available
    except Exception:
        return "rapidocr"
    return "vision" if vision_is_available() else "rapidocr"


def make_backend(options: OCRBackendOptions) -> OCRBackend:
    """Build a concrete :class:`OCRBackend` from options.

    Forcing a backend that is unavailable raises ``RuntimeError`` rather
    than silently falling back, so users see a clear message when a flag
    or config setting cannot be honored.
    """

    options.validate()
    resolved = resolve_backend_name(options.backend)
    if resolved == "vision":
        from webcalyzer.vision_backend import VisionBackend, is_available

        if not is_available():
            raise RuntimeError(
                "ocr.backend=vision requested but Vision is unavailable on this host. "
                "Vision requires macOS with pyobjc-framework-Vision and pyobjc-framework-Quartz "
                "installed."
            )
        return VisionBackend(
            recognition_level=options.recognition_level,
            custom_words=options.custom_words or None,
        )
    return RapidOCRBackend(
        intra_op_num_threads=options.intra_op_num_threads,
        inter_op_num_threads=options.inter_op_num_threads,
    )
