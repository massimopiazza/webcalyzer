from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from webcalyzer.calibration import launch_calibration_ui
from webcalyzer.config import load_profile
from webcalyzer.extract import extract_telemetry
from webcalyzer.fixtures import generate_review_frames
from webcalyzer.models import ProfileConfig, VideoOverlayConfig
from webcalyzer.overlay import render_telemetry_overlay_video
from webcalyzer.plotting import create_plots
from webcalyzer.postprocess import (
    apply_outlier_rejection_in_output_dir,
    rebuild_clean_in_output_dir,
)
from webcalyzer.rescue import rescue_output_dir
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

    outlier_parser = subparsers.add_parser(
        "reject-outliers",
        help="Apply Mahalanobis-distance outlier rejection to telemetry_clean.csv.",
    )
    outlier_parser.add_argument("--output", required=True, help="Extraction output directory.")
    outlier_parser.add_argument("--chi2", type=float, default=13.82, help="Chi^2 threshold (default 13.82 for 99.9%% / 2 DoF).")
    outlier_parser.add_argument("--window-s", type=float, default=40.0, help="Neighbor window in seconds.")

    run_parser = subparsers.add_parser("run", help="Run extraction and plotting.")
    _add_video_config_args(run_parser)
    run_parser.add_argument("--output", required=True, help="Directory for extraction outputs.")
    run_parser.add_argument("--sample-fps", type=float, default=None, help="Sampling cadence in frames per second.")
    _add_video_overlay_args(run_parser)

    overlay_parser = subparsers.add_parser("render-overlay", help="Render a video copy with synchronized telemetry plot overlay.")
    overlay_parser.add_argument("--video", required=True, help="Path to the source video.")
    overlay_parser.add_argument("--output", required=True, help="Extraction output directory containing telemetry_clean.csv.")
    overlay_parser.add_argument("--config", required=False, help="Optional YAML profile with video_overlay settings.")
    overlay_parser.add_argument("--plot-mode", choices=["filtered", "with_rejected"], default=None)
    overlay_parser.add_argument("--width-fraction", type=float, default=None)
    overlay_parser.add_argument("--height-fraction", type=float, default=None)
    overlay_parser.add_argument("--output-filename", default=None)
    overlay_parser.add_argument("--no-audio", action="store_true", help="Do not mux the original audio into the rendered copy.")

    return parser


def _add_video_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--video", required=True, help="Path to the source video.")
    parser.add_argument("--config", required=True, help="YAML profile path.")


def _add_video_overlay_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skip-video-overlay", action="store_true", help="Do not render the configured video overlay copy.")
    parser.add_argument("--overlay-plot-mode", choices=["filtered", "with_rejected"], default=None)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "plot":
        import pandas as pd

        output_dir = Path(args.output)
        clean_df = pd.read_csv(output_dir / "telemetry_clean.csv")
        create_plots(clean_df, output_dir)
        return

    if args.command == "rebuild-clean":
        clean_df = rebuild_clean_in_output_dir(args.output)
        create_plots(clean_df, args.output)
        return

    if args.command == "rescue":
        profile = load_profile(args.config) if args.config else None
        rescue_output_dir(output_dir=args.output, video_path=args.video, profile=profile)
        clean_df = rebuild_clean_in_output_dir(args.output)
        create_plots(clean_df, args.output)
        return

    if args.command == "reject-outliers":
        cleaned = apply_outlier_rejection_in_output_dir(
            output_dir=args.output,
            chi2_threshold=args.chi2,
            window_s=args.window_s,
        )
        create_plots(cleaned, args.output)
        return

    if args.command == "render-overlay":
        import pandas as pd

        output_dir = Path(args.output)
        profile = load_profile(args.config) if args.config else None
        overlay_config = _overlay_config_from_args(profile, args)
        clean_df = pd.read_csv(output_dir / "telemetry_clean.csv")
        render_telemetry_overlay_video(
            video_path=args.video,
            clean_df=clean_df,
            output_dir=output_dir,
            config=overlay_config,
            rejected_df=_read_rejected_df(output_dir),
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
        extract_telemetry(args.video, profile, args.output, sample_fps=args.sample_fps)
        return

    if args.command == "run":
        generate_review_frames(args.video, profile, Path(args.output) / "review")
        _raw_df, clean_df = extract_telemetry(args.video, profile, args.output, sample_fps=args.sample_fps)
        create_plots(clean_df, args.output)
        _render_overlay_if_enabled(args.video, clean_df, args.output, profile, args)
        return

    raise ValueError(f"Unsupported command: {args.command}")


def _read_rejected_df(output_dir: str | Path):
    import pandas as pd

    rejected_path = Path(output_dir) / "telemetry_rejected.csv"
    if not rejected_path.exists():
        return None
    rejected_df = pd.read_csv(rejected_path)
    return rejected_df if not rejected_df.empty else None


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


def _render_overlay_if_enabled(
    video_path: str | Path,
    clean_df,
    output_dir: str | Path,
    profile: ProfileConfig,
    args: argparse.Namespace,
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
    )
