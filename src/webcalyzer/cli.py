from __future__ import annotations

import argparse
from pathlib import Path

from webcalyzer.calibration import launch_calibration_ui
from webcalyzer.config import load_profile
from webcalyzer.extract import extract_telemetry
from webcalyzer.fixtures import generate_review_frames
from webcalyzer.plotting import create_plots
from webcalyzer.postprocess import rebuild_clean_in_output_dir
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

    run_parser = subparsers.add_parser("run", help="Run extraction and plotting.")
    _add_video_config_args(run_parser)
    run_parser.add_argument("--output", required=True, help="Directory for extraction outputs.")
    run_parser.add_argument("--sample-fps", type=float, default=None, help="Sampling cadence in frames per second.")

    return parser


def _add_video_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--video", required=True, help="Path to the source video.")
    parser.add_argument("--config", required=True, help="YAML profile path.")


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
        return

    raise ValueError(f"Unsupported command: {args.command}")
