from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd

ALTITUDE_SCALE = 0.001


SUMMARY_COLORS = {
    "stage1": "#1f77b4",
    "stage2": "#ff7f0e",
}

STAGE_COLORS = {
    "velocity": "#1f77b4",
    "altitude": "#d62728",
}


def create_plots(
    clean_df: pd.DataFrame,
    output_dir: str | Path,
    rejected_df: pd.DataFrame | None = None,
) -> None:
    output_path = Path(output_dir)
    if rejected_df is None:
        rejected_path = output_path / "telemetry_rejected.csv"
        if rejected_path.exists():
            rejected_df = pd.read_csv(rejected_path)

    plots_dir = output_path / "plots"
    for stale_name in ("summary.pdf", "coverage.pdf", "stage1.pdf", "stage2.pdf"):
        stale_path = plots_dir / stale_name
        if stale_path.exists():
            stale_path.unlink()
    _create_plot_set(clean_df, plots_dir / "filtered", rejected_df=None)
    _create_plot_set(clean_df, plots_dir / "with_rejected", rejected_df=rejected_df)


def _create_plot_set(clean_df: pd.DataFrame, plots_dir: Path, rejected_df: pd.DataFrame | None) -> None:
    plots_dir.mkdir(parents=True, exist_ok=True)
    _create_summary_pdf(clean_df, plots_dir / "summary.pdf", rejected_df=rejected_df)
    _create_coverage_pdf(clean_df, plots_dir / "coverage.pdf")
    _create_stage_pdf(clean_df, stage="stage1", path=plots_dir / "stage1.pdf", rejected_df=rejected_df)
    _create_stage_pdf(clean_df, stage="stage2", path=plots_dir / "stage2.pdf", rejected_df=rejected_df)


def _create_summary_pdf(df: pd.DataFrame, path: Path, rejected_df: pd.DataFrame | None) -> None:
    with PdfPages(path) as pdf:
        fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
        _plot_metric(
            axes[0],
            df,
            "stage1_velocity_mps",
            "stage2_velocity_mps",
            ylabel="Velocity [m/s]",
            rejected_df=rejected_df,
        )
        _plot_metric(
            axes[1],
            df,
            "stage1_altitude_m",
            "stage2_altitude_m",
            ylabel="Altitude [km]",
            rejected_df=rejected_df,
        )
        axes[1].set_xlabel("Mission Elapsed Time [s]")
        fig.suptitle("Telemetry Summary")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)


def _create_coverage_pdf(df: pd.DataFrame, path: Path) -> None:
    with PdfPages(path) as pdf:
        fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
        _plot_coverage(axes[0], df, "stage1_velocity_mps", "stage1_altitude_m", "Stage 1 coverage")
        _plot_coverage(axes[1], df, "stage2_velocity_mps", "stage2_altitude_m", "Stage 2 coverage")
        axes[1].set_xlabel("Mission Elapsed Time [s]")
        fig.suptitle("Extraction Coverage")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)


def _create_stage_pdf(df: pd.DataFrame, stage: str, path: Path, rejected_df: pd.DataFrame | None) -> None:
    with PdfPages(path) as pdf:
        fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
        velocity_column = f"{stage}_velocity_mps"
        altitude_column = f"{stage}_altitude_m"
        _plot_line_with_rejected(
            axis=axes[0],
            df=df,
            column=velocity_column,
            color=STAGE_COLORS["velocity"],
            label="Velocity",
            rejected_df=rejected_df,
        )
        axes[0].set_ylabel("Velocity [m/s]")
        axes[0].set_title(f"{stage.upper()} Velocity")
        axes[0].grid(alpha=0.25)
        axes[0].legend()

        _plot_line_with_rejected(
            axis=axes[1],
            df=df,
            column=altitude_column,
            color=STAGE_COLORS["altitude"],
            label="Altitude",
            rejected_df=rejected_df,
        )
        axes[1].set_ylabel("Altitude [m]")
        axes[1].set_xlabel("Mission Elapsed Time [s]")
        axes[1].set_title(f"{stage.upper()} Altitude")
        axes[1].grid(alpha=0.25)
        axes[1].legend()

        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)


def _plot_metric(
    axis: plt.Axes,
    df: pd.DataFrame,
    stage1_column: str,
    stage2_column: str,
    ylabel: str,
    rejected_df: pd.DataFrame | None,
) -> None:
    _plot_line_with_rejected(
        axis=axis,
        df=df,
        column=stage1_column,
        color=SUMMARY_COLORS["stage1"],
        label="Stage 1",
        rejected_df=rejected_df,
    )
    _plot_line_with_rejected(
        axis=axis,
        df=df,
        column=stage2_column,
        color=SUMMARY_COLORS["stage2"],
        label="Stage 2",
        rejected_df=rejected_df,
    )
    axis.set_ylabel(ylabel)
    axis.grid(alpha=0.25)
    axis.legend()


def _plot_line_with_rejected(
    axis: plt.Axes,
    df: pd.DataFrame,
    column: str,
    color: str,
    label: str,
    rejected_df: pd.DataFrame | None,
) -> None:
    axis.plot(df["mission_elapsed_time_s"], df[column], color=color, label=label, linewidth=1.2)
    y_values = _plot_values(df[column], column)
    axis.plot(df["mission_elapsed_time_s"], y_values, color=color, label=label, linewidth=1.2)
    if rejected_df is None or column not in rejected_df.columns:
        return

    rejected = rejected_df[["mission_elapsed_time_s", column]].dropna()
    if rejected.empty:
        return
    axis.scatter(
        rejected["mission_elapsed_time_s"],
        _plot_values(rejected[column], column),
        s=16,
        facecolors="none",
        edgecolors=color,
        linewidths=0.8,
        label=f"{label} rejected",
    )


def _plot_values(values: pd.Series, column: str) -> pd.Series:
    if column.endswith("_altitude_m"):
        return values * ALTITUDE_SCALE
    return values


def _plot_coverage(axis: plt.Axes, df: pd.DataFrame, velocity_column: str, altitude_column: str, title: str) -> None:
    axis.scatter(df["mission_elapsed_time_s"], df[velocity_column].notna().astype(int), s=4, label="velocity")
    axis.scatter(df["mission_elapsed_time_s"], df[altitude_column].notna().astype(int), s=4, label="altitude")
    axis.set_yticks([0, 1])
    axis.set_yticklabels(["missing", "present"])
    axis.set_title(title)
    axis.grid(alpha=0.25)
    axis.legend()
