import argparse
import os
import platform

import pytest

from webcalyzer.cli import _resolve_workers, build_parser
from webcalyzer.ocr_factory import OCRBackendOptions


def test_ocr_workers_defaults_to_profile_value() -> None:
    parser = build_parser()
    extract_args = parser.parse_args(
        ["extract", "--video", "video.mp4", "--config", "profile.yaml", "--output", "outputs/run"]
    )
    run_args = parser.parse_args(
        ["run", "--video", "video.mp4", "--config", "profile.yaml", "--output", "outputs/run"]
    )

    assert extract_args.ocr_workers is None
    assert run_args.ocr_workers is None
    assert extract_args.ocr_backend is None
    assert run_args.ocr_backend is None
    assert extract_args.ocr_recognition_level is None
    assert run_args.ocr_recognition_level is None
    assert extract_args.ocr_skip_detection is None
    assert run_args.ocr_skip_detection is None


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


def test_none_ocr_workers_uses_profile_default() -> None:
    args = argparse.Namespace(ocr_workers=None)

    workers = _resolve_workers(args, OCRBackendOptions(backend="rapidocr"), default_workers=5)

    assert workers == 5


def test_reject_outliers_uses_chi2_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["reject-outliers", "--output", "outputs/run", "--chi2", "20"])
    assert args.chi2 == 20.0

    with pytest.raises(SystemExit):
        parser.parse_args(["reject-outliers", "--output", "outputs/run", "--sigma", "4.5"])


def test_postprocess_regenerate_requires_output() -> None:
    parser = build_parser()

    args = parser.parse_args(["postprocess-regenerate", "--output", "outputs/run"])

    assert args.output == "outputs/run"
