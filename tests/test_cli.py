import argparse
import os
import platform

from webcalyzer.cli import _resolve_workers, build_parser
from webcalyzer.ocr_factory import OCRBackendOptions


def test_ocr_workers_defaults_to_auto() -> None:
    parser = build_parser()
    extract_args = parser.parse_args(
        ["extract", "--video", "video.mp4", "--config", "profile.yaml", "--output", "outputs/run"]
    )
    run_args = parser.parse_args(
        ["run", "--video", "video.mp4", "--config", "profile.yaml", "--output", "outputs/run"]
    )

    assert extract_args.ocr_workers == "auto"
    assert run_args.ocr_workers == "auto"


def test_omitted_ocr_workers_resolves_like_auto(monkeypatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    args = argparse.Namespace()

    workers = _resolve_workers(args, OCRBackendOptions(backend="rapidocr"))

    assert workers == 7


def test_none_ocr_workers_resolves_like_auto(monkeypatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    args = argparse.Namespace(ocr_workers=None)

    workers = _resolve_workers(args, OCRBackendOptions(backend="rapidocr"))

    assert workers == 3
