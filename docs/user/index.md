# Webcalyzer User Guide

Webcalyzer extracts launch telemetry from webcast videos. It samples frames, OCRs calibrated telemetry regions, converts readings into SI units, filters noisy measurements, reconstructs a trajectory, and writes reviewable outputs. Use this guide when you run the local web UI, calibrate a new overlay, manage YAML templates, inspect outputs, or operate the CLI directly.

## Contents

| Guide | What it covers |
|---|---|
| [Getting Started](getting-started.md) | Installation, web UI launch, local roots, and a first run |
| [Run Extraction](run-extraction.md) | The **Run** page, paths, run overrides, live console, cancellation, and output links |
| [Calibration](calibration.md) | Fixture frames, bounding boxes, field metadata, and calibration saves |
| [Templates](templates.md) | Loading, saving, importing, downloading, deleting, and repairing YAML templates |
| [Profile Configuration](profile-configuration.md) | General settings, fields, parsing, trajectory, overlay, and anchor points |
| [Trajectory Reconstruction](trajectory-reconstruction.md) | Unit conversion, mission-time grids, interpolation, integration, downrange, acceleration, and geodesic projection |
| [Outputs and Review](outputs-and-review.md) | Review frames, CSVs, plots, rejected points, trajectory data, and overlay videos |
| [CLI Reference](cli-reference.md) | Command-line workflows and subcommand responsibilities |

## Core concepts

**Profile.** A YAML configuration that defines how one webcast overlay should be sampled, parsed, filtered, reconstructed, and rendered. The profile is the source of truth for both the CLI and the web UI.

**Template.** A saved profile under the server templates directory. Templates can be loaded into **Run** or **Calibrate**, edited, saved, and reused from the CLI.

**Field.** A named telemetry region in the video frame. Each field has a type (`velocity`, `altitude`, or `met`), an optional stage (`stage1` or `stage2`), and a normalized bounding box.

**Mission elapsed time.** The extracted time axis from the video overlay. Webcalyzer uses mission elapsed time to align readings across frames and to build trajectory outputs.

**Review frame.** A sampled JPEG with calibrated field boxes drawn on top. Review frames are written before OCR so you can confirm the profile is looking at the correct overlay regions.

**Clean telemetry.** The retained telemetry table after parsing, anchor-point injection, stage logic, and outlier filtering. This table feeds plotting, trajectory reconstruction, and overlay rendering.

**Trajectory.** A dense reconstruction of velocity, altitude, acceleration, distance, and optional geodesic position. It is derived from clean telemetry through interpolation, integration, and smoothing.

**Trajectory reconstruction.** The kinematic interpretation behind trajectory outputs. The [trajectory reconstruction](trajectory-reconstruction.md) guide explains what webcalyzer computes and which assumptions the results depend on.

**Run output.** The directory written by an extraction. It contains raw telemetry, clean telemetry, rejected points, trajectory data, plots, metadata, the resolved profile, review frames, and optionally an overlay video.
