from __future__ import annotations

import argparse
import os
from dataclasses import replace
from pathlib import Path

from webcalyzer.calibration import launch_calibration_ui
from webcalyzer.config import load_profile
from webcalyzer.extract import extract_telemetry
from webcalyzer.fixtures import generate_review_frames
from webcalyzer.models import ProfileConfig, TrajectoryConfig, VideoOverlayConfig
from webcalyzer.ocr_factory import OCRBackendOptions, resolve_backend_name
from webcalyzer.overlay import render_telemetry_overlay_video
from webcalyzer.plotting import create_plots
from webcalyzer.postprocess import (
    apply_outlier_rejection_in_output_dir,
    rebuild_clean_in_output_dir,
)
from webcalyzer.rescue import rescue_output_dir
from webcalyzer.trajectory import (
    INTEGRATION_METHODS,
    INTERPOLATION_METHODS,
    TRAJECTORY_FILENAME,
    write_trajectory_outputs,
)
from webcalyzer.video import get_video_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telemetry extraction from webcast videos.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample_parser = subparsers.add_parser("sample-frames", help="Generate representative review frames.")
    _add_video_config_args(sample_parser)
    sample_parser.add_argument("--output", required=True, help="Directory for sampled frames.")
    sample_parser.add_argument("--count", type=int, default=None, help="Override representative frame count.")

    calibrate_parser = subparsers.add_parser("calibrate", help="Launch interactive calibration.")
    _add_video_config_args(calibrate_parser)
    calibrate_parser.add_argument("--output", required=True, help="Path to write the calibrated YAML profile.")

    extract_parser = subparsers.add_parser("extract", help="Run OCR extraction.")
    _add_video_config_args(extract_parser)
    extract_parser.add_argument("--output", required=True, help="Directory for extraction outputs.")
    extract_parser.add_argument("--sample-fps", type=float, default=None, help="Sampling cadence in frames per second.")
    _add_ocr_args(extract_parser)
    _add_trajectory_args(extract_parser)

    plot_parser = subparsers.add_parser("plot", help="Generate plots from an extraction output folder.")
    plot_parser.add_argument("--output", required=True, help="Extraction output directory containing telemetry_clean.csv.")

    rebuild_parser = subparsers.add_parser("rebuild-clean", help="Rebuild telemetry_clean.csv from telemetry_raw.csv.")
    rebuild_parser.add_argument("--output", required=True, help="Extraction output directory containing telemetry_raw.csv.")

    rescue_parser = subparsers.add_parser(
        "rescue",
        help="Re-OCR samples whose raw parse failed (multi-variant, multi-frame).",
    )
    rescue_parser.add_argument("--video", required=True, help="Path to the source video.")
    rescue_parser.add_argument("--output", required=True, help="Extraction output directory.")
    rescue_parser.add_argument("--config", required=False, help="Optional YAML profile override.")
    _add_ocr_args(rescue_parser, include_workers=False, include_skip_detection=False)

    outlier_parser = subparsers.add_parser(
        "reject-outliers",
        help="Apply Mahalanobis-distance outlier rejection to telemetry_clean.csv.",
    )
    outlier_parser.add_argument("--output", required=True, help="Extraction output directory.")
    outlier_parser.add_argument("--chi2", type=float, default=36.0, help="Per-field squared residual threshold.")
    outlier_parser.add_argument("--window-s", type=float, default=40.0, help="Neighbor window in seconds.")

    trajectory_parser = subparsers.add_parser(
        "reconstruct-trajectory",
        help="Reconstruct downrange trajectory from telemetry_clean.csv.",
    )
    trajectory_parser.add_argument("--output", required=True, help="Extraction output directory containing telemetry_clean.csv.")
    trajectory_parser.add_argument("--config", required=False, help="Optional YAML profile override.")
    _add_trajectory_args(trajectory_parser)

    run_parser = subparsers.add_parser("run", help="Run extraction and plotting.")
    _add_video_config_args(run_parser)
    run_parser.add_argument("--output", required=True, help="Directory for extraction outputs.")
    run_parser.add_argument("--sample-fps", type=float, default=None, help="Sampling cadence in frames per second.")
    _add_ocr_args(run_parser)
    _add_trajectory_args(run_parser)
    _add_video_overlay_args(run_parser)

    overlay_parser = subparsers.add_parser("render-overlay", help="Render a video copy with synchronized telemetry plot overlay.")
    overlay_parser.add_argument("--video", required=True, help="Path to the source video.")
    overlay_parser.add_argument("--output", required=True, help="Extraction output directory containing telemetry_clean.csv.")
    overlay_parser.add_argument(
        "--config",
        required=False,
        help=(
            "Optional YAML profile with video_overlay and trajectory acceleration "
            "settings. Defaults to <output>/config_resolved.yaml when present."
        ),
    )
    overlay_parser.add_argument("--plot-mode", choices=["filtered", "with_rejected"], default=None)
    overlay_parser.add_argument("--width-fraction", type=float, default=None)
    overlay_parser.add_argument("--height-fraction", type=float, default=None)
    overlay_parser.add_argument("--output-filename", default=None)
    overlay_parser.add_argument("--no-audio", action="store_true", help="Do not mux the original audio into the rendered copy.")
    _add_overlay_engine_args(overlay_parser)

    return parser


def _add_video_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--video", required=True, help="Path to the source video.")
    parser.add_argument("--config", required=True, help="YAML profile path.")


def _add_ocr_args(
    parser: argparse.ArgumentParser,
    *,
    include_workers: bool = True,
    include_skip_detection: bool = True,
) -> None:
    parser.add_argument(
        "--ocr-backend",
        choices=["auto", "rapidocr", "vision"],
        default="auto",
        help=(
            "OCR backend selection. 'auto' picks Vision on macOS when available "
            "and RapidOCR everywhere else. Use 'rapidocr' to force the portable "
            "ONNX path even on macOS, or 'vision' to require Apple Vision."
        ),
    )
    parser.add_argument(
        "--ocr-recognition-level",
        choices=["accurate", "fast"],
        default="accurate",
        help="Vision recognition level. Ignored when the resolved backend is RapidOCR.",
    )
    if include_workers:
        parser.add_argument(
            "--ocr-workers",
            default="auto",
            help=(
                "Number of worker processes for OCR Phase A. 'auto' picks "
                "max(1, physical_cores - 1) for RapidOCR and 1 for Vision."
            ),
        )
    if include_skip_detection:
        parser.add_argument(
            "--ocr-skip-detection",
            action="store_true",
            help=(
                "Opt-in: skip text detection and run recognition only on each "
                "calibrated field crop. Faster but loses the rescue net for "
                "frames where the overlay drifts; default off."
            ),
        )


def _add_video_overlay_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skip-video-overlay", action="store_true", help="Do not render the configured video overlay copy.")
    parser.add_argument("--overlay-plot-mode", choices=["filtered", "with_rejected"], default=None)
    _add_overlay_engine_args(parser)


def _add_overlay_engine_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--overlay-engine",
        choices=["auto", "ffmpeg", "opencv"],
        default="auto",
        help=(
            "Rendering engine for the telemetry overlay video. 'auto' uses "
            "ffmpeg when available (single-shot pipeline with hardware encode) "
            "and falls back to the in-process OpenCV path otherwise. Force "
            "'ffmpeg' to fail loudly if ffmpeg is missing."
        ),
    )
    parser.add_argument(
        "--overlay-encoder",
        choices=[
            "auto",
            "videotoolbox",
            "h264_videotoolbox",
            "nvenc",
            "h264_nvenc",
            "qsv",
            "h264_qsv",
            "vaapi",
            "h264_vaapi",
            "libx264",
        ],
        default="auto",
        help=(
            "ffmpeg H.264 encoder. 'auto' walks videotoolbox→nvenc→qsv→vaapi→"
            "libx264 and picks the first one available in the local ffmpeg "
            "build. Ignored unless the resolved overlay engine is 'ffmpeg'."
        ),
    )


def _add_trajectory_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--trajectory-interpolation",
        choices=sorted(INTERPOLATION_METHODS),
        default=None,
        help="Override trajectory.interpolation_method for reconstruction.",
    )
    parser.add_argument(
        "--trajectory-integration",
        choices=sorted(INTEGRATION_METHODS),
        default=None,
        help="Override trajectory.integration_method for fixed-step reconstruction.",
    )
    parser.add_argument(
        "--trajectory-derivative-window-s",
        type=float,
        default=None,
        help=(
            "Override trajectory.derivative_smoothing_window_s — Savitzky-Golay "
            "window length in seconds used for the acceleration plot."
        ),
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "plot":
        import pandas as pd

        output_dir = Path(args.output)
        clean_df = pd.read_csv(output_dir / "telemetry_clean.csv")
        create_plots(
            clean_df,
            output_dir,
            trajectory_df=_read_trajectory_df(output_dir),
            trajectory_config=_trajectory_config_from_profile(output_dir),
        )
        return

    if args.command == "rebuild-clean":
        clean_df = rebuild_clean_in_output_dir(args.output)
        clean_df, trajectory_df = _write_trajectory_for_output(clean_df, args.output, profile=None)
        create_plots(
            clean_df,
            args.output,
            trajectory_df=trajectory_df,
            trajectory_config=_trajectory_config_from_profile(args.output),
        )
        return

    if args.command == "rescue":
        profile = load_profile(args.config) if args.config else None
        rescue_output_dir(
            output_dir=args.output,
            video_path=args.video,
            profile=profile,
            backend_options=_ocr_backend_options(args),
        )
        clean_df = rebuild_clean_in_output_dir(args.output, profile=profile)
        clean_df, trajectory_df = _write_trajectory_for_output(clean_df, args.output, profile=profile)
        create_plots(
            clean_df,
            args.output,
            trajectory_df=trajectory_df,
            trajectory_config=_trajectory_config_from_profile(args.output, profile=profile),
        )
        return

    if args.command == "reject-outliers":
        cleaned = apply_outlier_rejection_in_output_dir(
            output_dir=args.output,
            chi2_threshold=args.chi2,
            window_s=args.window_s,
        )
        cleaned, trajectory_df = _write_trajectory_for_output(cleaned, args.output, profile=None)
        create_plots(
            cleaned,
            args.output,
            trajectory_df=trajectory_df,
            trajectory_config=_trajectory_config_from_profile(args.output),
        )
        return

    if args.command == "reconstruct-trajectory":
        import pandas as pd

        output_dir = Path(args.output)
        profile = load_profile(args.config) if args.config else _profile_from_output(output_dir)
        clean_df = pd.read_csv(output_dir / "telemetry_clean.csv")
        clean_df, trajectory_df = _write_trajectory_for_output(clean_df, output_dir, profile=profile, args=args)
        create_plots(
            clean_df,
            output_dir,
            trajectory_df=trajectory_df,
            trajectory_config=_trajectory_config_from_profile(output_dir, profile=profile, args=args),
        )
        return

    if args.command == "render-overlay":
        import pandas as pd

        output_dir = Path(args.output)
        profile = load_profile(args.config) if args.config else _profile_from_output(output_dir)
        overlay_config = _overlay_config_from_args(profile, args)
        clean_df = pd.read_csv(output_dir / "telemetry_clean.csv")
        render_telemetry_overlay_video(
            video_path=args.video,
            clean_df=clean_df,
            output_dir=output_dir,
            config=overlay_config,
            rejected_df=_read_rejected_df(output_dir),
            trajectory_df=_read_trajectory_df(output_dir),
            trajectory_config=_trajectory_config_from_profile(output_dir, profile=profile),
            engine=getattr(args, "overlay_engine", "auto"),
            encoder=getattr(args, "overlay_encoder", "auto"),
        )
        return

    profile = load_profile(args.config)

    if args.command == "sample-frames":
        generate_review_frames(args.video, profile, args.output, args.count)
        return

    if args.command == "calibrate":
        metadata = get_video_metadata(args.video)
        launch_calibration_ui(
            video_path=args.video,
            profile=profile,
            output_path=args.output,
            video_frame_count=metadata.frame_count,
            video_fps=metadata.fps,
        )
        return

    if args.command == "extract":
        profile.trajectory = _trajectory_config_from_args(profile.trajectory, args)
        backend_options = _ocr_backend_options(args)
        effective_fps = float(args.sample_fps or profile.default_sample_fps)
        _raw_df, clean_df = extract_telemetry(
            args.video,
            profile,
            args.output,
            sample_fps=args.sample_fps,
            backend_options=backend_options,
            workers=_resolve_workers(args, backend_options),
            skip_detection=getattr(args, "ocr_skip_detection", False),
        )
        _write_trajectory_for_output(clean_df, args.output, profile=profile, sample_fps=effective_fps)
        return

    if args.command == "run":
        generate_review_frames(args.video, profile, Path(args.output) / "review")
        profile.trajectory = _trajectory_config_from_args(profile.trajectory, args)
        backend_options = _ocr_backend_options(args)
        effective_fps = float(args.sample_fps or profile.default_sample_fps)
        _raw_df, clean_df = extract_telemetry(
            args.video,
            profile,
            args.output,
            sample_fps=args.sample_fps,
            backend_options=backend_options,
            workers=_resolve_workers(args, backend_options),
            skip_detection=getattr(args, "ocr_skip_detection", False),
        )
        clean_df, trajectory_df = _write_trajectory_for_output(
            clean_df, args.output, profile=profile, sample_fps=effective_fps
        )
        create_plots(
            clean_df,
            args.output,
            trajectory_df=trajectory_df,
            trajectory_config=_trajectory_config_from_profile(args.output, profile=profile, args=args),
        )
        _render_overlay_if_enabled(args.video, clean_df, args.output, profile, args, trajectory_df=trajectory_df)
        return

    raise ValueError(f"Unsupported command: {args.command}")


def _read_rejected_df(output_dir: str | Path):
    import pandas as pd

    rejected_path = Path(output_dir) / "telemetry_rejected.csv"
    if not rejected_path.exists():
        return None
    rejected_df = pd.read_csv(rejected_path)
    return rejected_df if not rejected_df.empty else None


def _read_trajectory_df(output_dir: str | Path):
    import pandas as pd

    trajectory_path = Path(output_dir) / TRAJECTORY_FILENAME
    if not trajectory_path.exists():
        return None
    trajectory_df = pd.read_csv(trajectory_path)
    return trajectory_df if not trajectory_df.empty else None


def _profile_from_output(output_dir: str | Path) -> ProfileConfig | None:
    profile_path = Path(output_dir) / "config_resolved.yaml"
    if not profile_path.exists():
        return None
    return load_profile(profile_path)


def _trajectory_config_from_profile(
    output_dir: str | Path,
    profile: ProfileConfig | None = None,
    args: argparse.Namespace | None = None,
) -> TrajectoryConfig:
    """Resolve the trajectory config used by reconstruction-dependent plots.

    Priority: explicit trajectory CLI flags, then profile YAML, then resolved
    profile from ``config_resolved.yaml``, then TrajectoryConfig defaults.
    """

    if profile is None:
        profile = _profile_from_output(output_dir)
    return _trajectory_config_from_args(profile.trajectory if profile else TrajectoryConfig(), args)


def _derivative_window_from_profile(
    output_dir: str | Path,
    profile: ProfileConfig | None = None,
    args: argparse.Namespace | None = None,
) -> float:
    return float(_trajectory_config_from_profile(output_dir, profile=profile, args=args).derivative_smoothing_window_s)


def _trajectory_config_from_args(config: TrajectoryConfig, args: argparse.Namespace | None = None) -> TrajectoryConfig:
    resolved = replace(config)
    if args is None:
        return resolved
    if getattr(args, "trajectory_interpolation", None):
        resolved.interpolation_method = args.trajectory_interpolation
    if getattr(args, "trajectory_integration", None):
        resolved.integration_method = args.trajectory_integration
    if getattr(args, "trajectory_derivative_window_s", None) is not None:
        resolved.derivative_smoothing_window_s = args.trajectory_derivative_window_s
    return resolved


def _sample_fps_for_output(output_dir: str | Path) -> float | None:
    """Read the requested sample FPS from ``run_metadata.json`` if present."""

    import json

    metadata_path = Path(output_dir) / "run_metadata.json"
    if not metadata_path.exists():
        return None
    try:
        data = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        return None
    value = data.get("sample_fps_requested")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_trajectory_for_output(
    clean_df,
    output_dir: str | Path,
    profile: ProfileConfig | None,
    args: argparse.Namespace | None = None,
    sample_fps: float | None = None,
):
    profile = profile or _profile_from_output(output_dir)
    config = _trajectory_config_from_args(profile.trajectory if profile else TrajectoryConfig(), args)
    if sample_fps is None:
        sample_fps = _sample_fps_for_output(output_dir)
    return write_trajectory_outputs(clean_df, output_dir, config, sample_fps=sample_fps)


def _overlay_config_from_args(profile: ProfileConfig | None, args: argparse.Namespace) -> VideoOverlayConfig:
    config = replace(profile.video_overlay) if profile is not None else VideoOverlayConfig()
    if getattr(args, "skip_video_overlay", False):
        config.enabled = False
    if getattr(args, "overlay_plot_mode", None):
        config.plot_mode = args.overlay_plot_mode
    if getattr(args, "plot_mode", None):
        config.plot_mode = args.plot_mode
    if getattr(args, "width_fraction", None) is not None:
        config.width_fraction = args.width_fraction
    if getattr(args, "height_fraction", None) is not None:
        config.height_fraction = args.height_fraction
    if getattr(args, "output_filename", None):
        config.output_filename = args.output_filename
    if getattr(args, "no_audio", False):
        config.include_audio = False
    return config


def _ocr_backend_options(args: argparse.Namespace) -> OCRBackendOptions:
    return OCRBackendOptions(
        backend=getattr(args, "ocr_backend", "auto"),
        recognition_level=getattr(args, "ocr_recognition_level", "accurate"),
    )


def _resolve_workers(args: argparse.Namespace, backend_options: OCRBackendOptions) -> int:
    raw_value = getattr(args, "ocr_workers", "auto")
    if isinstance(raw_value, int):
        return max(1, raw_value)
    if raw_value is None:
        raw_value = "auto"
    text = str(raw_value).strip().lower()
    if text == "auto":
        if resolve_backend_name(backend_options.backend) == "vision":
            return 1
        cpu_count = os.cpu_count() or 1
        return max(1, cpu_count - 1)
    try:
        return max(1, int(text))
    except ValueError as exc:
        raise SystemExit(f"--ocr-workers must be an integer or 'auto'; got {raw_value!r}") from exc


def _render_overlay_if_enabled(
    video_path: str | Path,
    clean_df,
    output_dir: str | Path,
    profile: ProfileConfig,
    args: argparse.Namespace,
    trajectory_df=None,
) -> None:
    overlay_config = _overlay_config_from_args(profile, args)
    if not overlay_config.enabled:
        return
    render_telemetry_overlay_video(
        video_path=video_path,
        clean_df=clean_df,
        output_dir=output_dir,
        config=overlay_config,
        rejected_df=_read_rejected_df(output_dir),
        trajectory_df=trajectory_df if trajectory_df is not None else _read_trajectory_df(output_dir),
        trajectory_config=_trajectory_config_from_profile(output_dir, profile=profile, args=args),
        engine=getattr(args, "overlay_engine", "auto"),
        encoder=getattr(args, "overlay_encoder", "auto"),
    )
