from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd

from webcalyzer.acceleration import ACCELERATION_SOURCE_GAP_THRESHOLD_S, acceleration_profile, smoothed_velocity_profile

ALTITUDE_SCALE = 0.001


SUMMARY_COLORS = {
    "stage1": "#1f77b4",
    "stage2": "#d62728",
}

INTERPOLATED_COLORS = SUMMARY_COLORS

STAGE_COLORS = {
    "velocity": "#1f77b4",
    "altitude": "#d62728",
}

FILTERED_ALPHA = 0.75
FILTERED_LINEWIDTH = 1.4
INTERPOLATED_LINEWIDTH = 0.4


def create_plots(
    clean_df: pd.DataFrame,
    output_dir: str | Path,
    rejected_df: pd.DataFrame | None = None,
    trajectory_df: pd.DataFrame | None = None,
) -> None:
    output_path = Path(output_dir)
    if rejected_df is None:
        rejected_path = output_path / "telemetry_rejected.csv"
        if rejected_path.exists():
            rejected_df = pd.read_csv(rejected_path)
    if trajectory_df is None:
        trajectory_path = output_path / "trajectory.csv"
        if trajectory_path.exists():
            trajectory_df = pd.read_csv(trajectory_path)

    plots_dir = output_path / "plots"
    for stale_name in ("summary.pdf", "coverage.pdf", "stage1.pdf", "stage2.pdf", "trajectory.pdf", "downrange.pdf"):
        stale_path = plots_dir / stale_name
        if stale_path.exists():
            stale_path.unlink()
    _create_plot_set(clean_df, plots_dir / "filtered", rejected_df=None, trajectory_df=trajectory_df)
    _create_plot_set(clean_df, plots_dir / "with_rejected", rejected_df=rejected_df, trajectory_df=trajectory_df)


def _create_plot_set(
    clean_df: pd.DataFrame,
    plots_dir: Path,
    rejected_df: pd.DataFrame | None,
    trajectory_df: pd.DataFrame | None,
) -> None:
    plots_dir.mkdir(parents=True, exist_ok=True)
    stale_trajectory_path = plots_dir / "trajectory.pdf"
    if stale_trajectory_path.exists():
        stale_trajectory_path.unlink()
    _create_summary_pdf(clean_df, plots_dir / "summary.pdf", rejected_df=rejected_df, trajectory_df=trajectory_df)
    _create_coverage_pdf(clean_df, plots_dir / "coverage.pdf")
    _create_stage_pdf(clean_df, stage="stage1", path=plots_dir / "stage1.pdf", rejected_df=rejected_df)
    _create_stage_pdf(clean_df, stage="stage2", path=plots_dir / "stage2.pdf", rejected_df=rejected_df)
    if trajectory_df is not None and not trajectory_df.empty:
        _create_downrange_pdf(trajectory_df, plots_dir / "downrange.pdf")


def _create_summary_pdf(
    df: pd.DataFrame,
    path: Path,
    rejected_df: pd.DataFrame | None,
    trajectory_df: pd.DataFrame | None,
) -> None:
    with PdfPages(path) as pdf:
        has_trajectory = trajectory_df is not None and not trajectory_df.empty
        row_count = 4 if has_trajectory else 2
        fig_height = 10.5 if has_trajectory else 8.5
        fig, axes = plt.subplots(row_count, 1, figsize=(11, fig_height), sharex=True)
        _plot_metric(
            axes[0],
            df,
            "stage1_velocity_mps",
            "stage2_velocity_mps",
            ylabel="Velocity [m/s]",
            rejected_df=rejected_df,
            trajectory_df=trajectory_df,
            metric_name="velocity",
        )
        _plot_metric(
            axes[1],
            df,
            "stage1_altitude_m",
            "stage2_altitude_m",
            ylabel="Altitude [km]",
            rejected_df=rejected_df,
            trajectory_df=trajectory_df,
            metric_name="altitude",
        )
        bottom_axis = axes[1]
        if has_trajectory:
            _plot_downrange(axes[2], trajectory_df)
            _plot_acceleration(axes[3], df, trajectory_df)
            bottom_axis = axes[3]
        bottom_axis.set_xlabel("Mission Elapsed Time [s]")
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
        axes[1].set_ylabel("Altitude [km]")
        axes[1].set_xlabel("Mission Elapsed Time [s]")
        axes[1].set_title(f"{stage.upper()} Altitude")
        axes[1].grid(alpha=0.25)
        axes[1].legend()

        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)


def _create_downrange_pdf(trajectory_df: pd.DataFrame, path: Path) -> None:
    with PdfPages(path) as pdf:
        fig, axis = plt.subplots(1, 1, figsize=(11, 5.5))
        _plot_downrange(axis, trajectory_df)
        axis.set_xlabel("Mission Elapsed Time [s]")
        fig.suptitle("Downrange Reconstruction")
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
    trajectory_df: pd.DataFrame | None,
    metric_name: str,
) -> None:
    _plot_line_with_rejected(
        axis=axis,
        df=df,
        column=stage1_column,
        color=SUMMARY_COLORS["stage1"],
        label="Stage 1 filtered",
        rejected_df=rejected_df,
        alpha=FILTERED_ALPHA,
        linewidth=FILTERED_LINEWIDTH,
    )
    _plot_line_with_rejected(
        axis=axis,
        df=df,
        column=stage2_column,
        color=SUMMARY_COLORS["stage2"],
        label="Stage 2 filtered",
        rejected_df=rejected_df,
        alpha=FILTERED_ALPHA,
        linewidth=FILTERED_LINEWIDTH,
    )
    _plot_interpolated_metric(axis, trajectory_df, metric_name)
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
    alpha: float = 1.0,
    linewidth: float = 1.2,
) -> None:
    y_values = _plot_values(df[column], column)
    axis.plot(
        df["mission_elapsed_time_s"],
        y_values,
        color=color,
        alpha=alpha,
        label=label,
        linewidth=linewidth,
    )
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
        alpha=alpha,
        linewidths=0.8,
        label=f"{label} rejected",
    )


def _plot_interpolated_metric(
    axis: plt.Axes,
    trajectory_df: pd.DataFrame | None,
    metric_name: str,
) -> None:
    if trajectory_df is None or trajectory_df.empty:
        return
    value_column = "velocity_mps" if metric_name == "velocity" else "altitude_m"
    for stage, color in INTERPOLATED_COLORS.items():
        stage_df = trajectory_df[trajectory_df["stage"] == stage]
        if stage_df.empty:
            continue
        x = pd.to_numeric(stage_df["mission_elapsed_time_s"], errors="coerce")
        y = pd.to_numeric(stage_df[value_column], errors="coerce")
        if value_column == "altitude_m":
            y = y * ALTITUDE_SCALE
        axis.plot(
            x,
            y,
            color=color,
            alpha=1.0,
            linewidth=INTERPOLATED_LINEWIDTH,
            label=f"{stage.title()} interpolated",
        )


def _plot_downrange(axis: plt.Axes, trajectory_df: pd.DataFrame | None) -> None:
    if trajectory_df is None or trajectory_df.empty:
        return
    for stage, color in SUMMARY_COLORS.items():
        stage_df = trajectory_df[trajectory_df["stage"] == stage]
        if stage_df.empty:
            continue
        x = pd.to_numeric(stage_df["mission_elapsed_time_s"], errors="coerce")
        downrange_km = pd.to_numeric(stage_df["downrange_m"], errors="coerce") * ALTITUDE_SCALE
        axis.plot(x, downrange_km, color=color, label=stage.title(), linewidth=1.2)
    axis.set_ylabel("Downrange [km]")
    axis.set_title("Reconstructed Downrange")
    axis.grid(alpha=0.25)
    axis.legend()


def _plot_acceleration(
    axis: plt.Axes,
    clean_df: pd.DataFrame,
    trajectory_df: pd.DataFrame | None,
) -> None:
    if trajectory_df is None or trajectory_df.empty:
        return
    velocity_axis = axis.twinx()
    plotted = False
    legend_handles = []
    legend_labels = []
    for stage, color in SUMMARY_COLORS.items():
        stage_label = _stage_label(stage)
        x, acceleration_g = acceleration_profile(
            clean_df=clean_df,
            trajectory_df=trajectory_df,
            stage=stage,
            max_source_gap_s=ACCELERATION_SOURCE_GAP_THRESHOLD_S,
        )
        if x.size == 0:
            continue
        (acceleration_line,) = axis.plot(
            x,
            acceleration_g,
            color=color,
            label=f"{stage_label} estimated acceleration",
            linewidth=1.2,
        )
        velocity_x, smoothed_velocity = smoothed_velocity_profile(
            clean_df=clean_df,
            trajectory_df=trajectory_df,
            stage=stage,
            max_source_gap_s=ACCELERATION_SOURCE_GAP_THRESHOLD_S,
        )
        if velocity_x.size:
            (velocity_line,) = velocity_axis.plot(
                velocity_x,
                smoothed_velocity,
                color=color,
                linestyle="--",
                alpha=0.5,
                linewidth=0.9,
                label=f"{stage_label} smoothed velocity",
            )
            legend_handles.append(velocity_line)
            legend_labels.append(velocity_line.get_label())
        legend_handles.append(acceleration_line)
        legend_labels.append(acceleration_line.get_label())
        plotted = True
    axis.set_ylabel("Estimated acceleration [g]")
    velocity_axis.set_ylabel("Smoothed velocity [m/s]")
    axis.set_title("Estimated Acceleration")
    axis.grid(alpha=0.25)
    if plotted:
        axis.legend(legend_handles, legend_labels, loc="best")


def _stage_label(stage: str) -> str:
    return {"stage1": "Stage 1", "stage2": "Stage 2"}.get(stage, stage.title())


def _plot_values(values: pd.Series, column: str) -> pd.Series:
    if column.endswith("_altitude_m"):
        return values * ALTITUDE_SCALE
    return values


def _plot_coverage(axis: plt.Axes, df: pd.DataFrame, velocity_column: str, altitude_column: str, title: str) -> None:
    axis.scatter(df["mission_elapsed_time_s"], df[velocity_column].notna().astype(int), s=4, alpha=0.6, label="velocity")
    axis.scatter(df["mission_elapsed_time_s"], df[altitude_column].notna().astype(int), s=4, alpha=0.6, label="altitude")
    axis.set_yticks([0, 1])
    axis.set_yticklabels(["missing", "present"])
    axis.set_title(title)
    axis.grid(alpha=0.25)
    axis.legend()
