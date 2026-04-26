import platform

import pytest

from webcalyzer.ocr_factory import (
    OCRBackendOptions,
    make_backend,
    resolve_backend_name,
)


def test_resolve_auto_picks_rapidocr_off_macos(monkeypatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert resolve_backend_name("auto") == "rapidocr"


def test_resolve_auto_picks_vision_on_macos_when_available(monkeypatch) -> None:
    if platform.system() != "Darwin":
        pytest.skip("Vision backend availability test is macOS-only")
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    resolved = resolve_backend_name("auto")
    assert resolved in {"vision", "rapidocr"}


def test_resolve_invalid_backend_raises() -> None:
    with pytest.raises(ValueError):
        resolve_backend_name("not_a_backend")


def test_options_validate_rejects_bad_recognition_level() -> None:
    with pytest.raises(ValueError):
        OCRBackendOptions(backend="vision", recognition_level="medium").validate()


def test_make_backend_force_vision_off_macos_errors(monkeypatch) -> None:
    if platform.system() == "Darwin":
        pytest.skip("Forced-Vision-fail test is non-macOS-only")
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    with pytest.raises(RuntimeError):
        make_backend(OCRBackendOptions(backend="vision"))
