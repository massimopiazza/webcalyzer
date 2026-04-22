from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd


def create_plots(clean_df: pd.DataFrame, output_dir: str | Path) -> None:
    plots_dir = Path(output_dir) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    _create_summary_pdf(clean_df, plots_dir / "summary.pdf")
    _create_stage_pdf(clean_df, stage="stage1", path=plots_dir / "stage1.pdf")
    _create_stage_pdf(clean_df, stage="stage2", path=plots_dir / "stage2.pdf")


def _create_summary_pdf(df: pd.DataFrame, path: Path) -> None:
    with PdfPages(path) as pdf:
        fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
        _plot_metric(axes[0], df, "stage1_velocity_mps", "stage2_velocity_mps", ylabel="Velocity [m/s]")
        _plot_metric(axes[1], df, "stage1_altitude_m", "stage2_altitude_m", ylabel="Altitude [m]")
        axes[1].set_xlabel("Mission Elapsed Time [s]")
        fig.suptitle("Telemetry Summary")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
        _plot_coverage(axes[0], df, "stage1_velocity_mps", "stage1_altitude_m", "Stage 1 coverage")
        _plot_coverage(axes[1], df, "stage2_velocity_mps", "stage2_altitude_m", "Stage 2 coverage")
        axes[1].set_xlabel("Mission Elapsed Time [s]")
        fig.suptitle("Extraction Coverage")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)


def _create_stage_pdf(df: pd.DataFrame, stage: str, path: Path) -> None:
    with PdfPages(path) as pdf:
        fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
        axes[0].plot(df["mission_elapsed_time_s"], df[f"{stage}_velocity_mps"], color="#1f77b4", linewidth=1.2)
        axes[0].set_ylabel("Velocity [m/s]")
        axes[0].set_title(f"{stage.upper()} Velocity")
        axes[0].grid(alpha=0.25)

        axes[1].plot(df["mission_elapsed_time_s"], df[f"{stage}_altitude_m"], color="#d62728", linewidth=1.2)
        axes[1].set_ylabel("Altitude [m]")
        axes[1].set_xlabel("Mission Elapsed Time [s]")
        axes[1].set_title(f"{stage.upper()} Altitude")
        axes[1].grid(alpha=0.25)

        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)


def _plot_metric(axis: plt.Axes, df: pd.DataFrame, stage1_column: str, stage2_column: str, ylabel: str) -> None:
    axis.plot(df["mission_elapsed_time_s"], df[stage1_column], label="Stage 1", linewidth=1.2)
    axis.plot(df["mission_elapsed_time_s"], df[stage2_column], label="Stage 2", linewidth=1.2)
    axis.set_ylabel(ylabel)
    axis.grid(alpha=0.25)
    axis.legend()


def _plot_coverage(axis: plt.Axes, df: pd.DataFrame, velocity_column: str, altitude_column: str, title: str) -> None:
    axis.scatter(df["mission_elapsed_time_s"], df[velocity_column].notna().astype(int), s=4, label="velocity")
    axis.scatter(df["mission_elapsed_time_s"], df[altitude_column].notna().astype(int), s=4, label="altitude")
    axis.set_yticks([0, 1])
    axis.set_yticklabels(["missing", "present"])
    axis.set_title(title)
    axis.grid(alpha=0.25)
    axis.legend()
