# Webcalyzer User Guide

Webcalyzer extracts launch telemetry from webcast videos. It samples frames, OCRs calibrated telemetry regions, converts readings into SI units, filters noisy measurements, reconstructs a trajectory, and writes reviewable outputs. Use this guide when you run the local web UI, calibrate a new overlay, manage YAML templates, inspect outputs, or operate the CLI directly.

## Contents

| Guide | What it covers |
|---|---|
| [Getting Started](getting-started.md) | Installation, web UI launch, local roots, and a first run |
| [Run Extraction](run-extraction.md) | The **Run** page, paths, profile settings, live console, cancellation, and output links |
| [Calibration](calibration.md) | Frame scrubbing, segment splits, bounding boxes, field slots, and calibration saves |
| [Quantities](quantities.md) | Reusable telemetry quantities, dimensionality, display units, aliases, and custom slots |
| [Templates](templates.md) | Loading, saving, importing, downloading, deleting, and repairing YAML templates |
| [Profile Configuration](profile-configuration.md) | General settings, segments, parsing, trajectory, overlay, and anchor points |
| [Trajectory Reconstruction](trajectory-reconstruction.md) | Unit conversion, mission-time grids, interpolation, integration, downrange, acceleration, and geodesic projection |
| [Outputs and Review](outputs-and-review.md) | Review frames, CSVs, plots, rejected points, trajectory data, and overlay videos |
| [CLI Reference](cli-reference.md) | Command-line workflows and subcommand responsibilities |

## Core concepts

**Profile.** A YAML configuration that defines how one webcast overlay should be sampled, parsed, filtered, reconstructed, and rendered. The profile is the source of truth for both the CLI and the web UI.

**Template.** A saved profile under the server templates directory. Templates can be loaded into **Run** or **Calibrate**, edited, saved, and reused from the CLI.

**Segment.** A source-video frame range with its own enabled telemetry slots and bounding boxes. Segment end frames are exclusive.

**Field slot.** One telemetry region in a segment. Canonical slots are `met`, `stage1_velocity`, `stage1_altitude`, `stage2_velocity`, and `stage2_altitude`. Custom slots use `custom_<slug>` names from the quantity library. Enabled slots have a fixed type, optional stage, and normalized bounding box.

**Quantity.** A reusable telemetry definition with dimensionality, display unit, optional aliases, and an optional description. Quantities live in `custom_quantities.yaml`; enabled custom quantities are copied into profile templates.

**Mission elapsed time.** The extracted time axis from the video overlay. Webcalyzer uses mission elapsed time to align readings across frames and to build trajectory outputs.

**Review frame.** A sampled JPEG with the active segment label and calibrated field boxes drawn on top. Review frames are written before OCR so you can confirm the profile is looking at the correct overlay regions.

**Clean telemetry.** The retained telemetry table after parsing, anchor-point injection, stage logic, and outlier filtering. This table feeds plotting, trajectory reconstruction, and overlay rendering.

**Trajectory.** A dense reconstruction of velocity, altitude, acceleration, distance, and optional geodesic position. It is derived from clean telemetry through interpolation, integration, and smoothing.

**Trajectory reconstruction.** The kinematic interpretation behind trajectory outputs. The [trajectory reconstruction](trajectory-reconstruction.md) guide explains what webcalyzer computes and which assumptions the results depend on.

**Run output.** The directory written by an extraction. It contains raw telemetry, clean telemetry, rejected points, trajectory data, plots, metadata, the resolved profile, review frames, and optionally an overlay video.
