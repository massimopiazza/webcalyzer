# Run Extraction

The **Run** page performs the full telemetry pipeline from a selected video and profile. It generates review frames, runs OCR, rebuilds clean telemetry, reconstructs the trajectory, writes plots, and optionally renders a synchronized overlay video. The page posts the same profile shape used by `webcalyzer run`, so saved templates remain interchangeable between the web UI and CLI.

## Run Setup

### Anatomy of a run

| Field | Description |
|---|---|
| **Profile template** | YAML profile loaded from the configured templates directory. Loading a template replaces the current form values. |
| **Input video** | Source webcast video. The path must be inside one of the server roots. |
| **Output directory** | Destination for CSVs, plots, metadata, review frames, and optional overlay video. The path must be inside one of the server roots. |
| **Profile form** | Editable profile surface. The run button stays disabled until the form passes client validation. |
| **Run overrides** | One-run settings such as sample rate, OCR backend, worker count, overlay engine, and overlay encoder. |
| **Run console** | Live status, phase events, stdout and stderr logs, cancellation, and finished output links. |

### Load a template

Click **Profile template** and choose a YAML profile. The template list is read from the server templates directory, and it updates after a new template is saved from the web app.

After loading a template, edit the profile sections as needed. Use **Preview YAML** to inspect the exact YAML that the server would write after validation.

Note: Loading another template replaces unsaved form edits. Save the current profile with **Save as template** before switching if you want to keep those edits.

### Select input and output paths

Click **Input video** and choose a supported video file from the file browser. Click **Output directory** and choose or type the destination folder.

The file picker is server-side. It sees the filesystem from the FastAPI process and only exposes paths under the configured roots.

### Set run overrides

Use **Run overrides** when a choice is specific to this run:

| Override | Description |
|---|---|
| **Sample fps override** | Replaces `default_sample_fps` for this run. Empty means use the profile value. |
| **OCR backend** | `auto`, `rapidocr`, or `vision`. `auto` chooses Vision on macOS when available and RapidOCR elsewhere. |
| **Recognition level** | `accurate` or `fast` for the Vision backend. |
| **OCR workers** | Number of OCR worker processes for Phase A. `0` means automatic. |
| **Overlay engine** | `auto`, `ffmpeg`, or `opencv`. `auto` uses ffmpeg when available and falls back to OpenCV. |
| **Overlay encoder** | ffmpeg H.264 encoder choice. `auto` tries hardware encoders before `libx264`. |
| **Skip OCR detection** | Runs recognition directly on calibrated field crops. This can be faster after boxes are stable. |

Rule of thumb: keep overrides at `auto` unless you are comparing backends, working around local encoder support, or running a quick low-sample experiment.

## Job Execution

### Run an extraction

Click **Run pipeline**. The job starts only when the profile is valid and both input and output paths are present.

The job phases are:

1. Generate review frames
2. Run OCR extraction
3. Reconstruct trajectory, when enabled
4. Generate plots
5. Render the overlay video, when enabled
6. Save `config_resolved.yaml`

The app allows one active job at a time. If another job is running, wait for it to finish or cancel it.

### Review the run console

The run console opens as a centered dialog by default. This keeps live progress visible and dims the rest of the app while the pipeline runs.

Use the console view button for either mode:

| Mode | Icon behavior | Use case |
|---|---|---|
| **Focused dialog** | The maximize-style icon returns the console to the centered focused view. | Watch a running job without page distractions. |
| **Docked on page** | The arrow-to-line icon docks the console at the top of the run page. | Keep the console in the page flow while checking configuration or output links. |

The console stream includes phase events, regular logs, warnings, errors, and the final output list. Files inside `review/` are generated for visual inspection but are not shown in the finished output-link list.

### Cancel a run

Click **Cancel** in the run console. Cancellation is checked between major phases, so a long OCR or render step may finish its current work before the job stops.

Cancelled jobs keep files that were already written. For a clean retry, choose a new output directory or remove partial files manually.

## Verification

### Verify finished outputs

When a job succeeds, the run console lists the main output files. Start with:

- `run_metadata.json` for backend choices and sample settings
- `telemetry_clean.csv` for retained telemetry
- `telemetry_rejected.csv` when outliers were removed
- `trajectory.csv` for reconstructed downrange and augmented values
- `plots/` for PDF review
- `telemetry_overlay.mp4` when overlay rendering is enabled

See [outputs and review](outputs-and-review.md) for the meaning of each output and the recommended inspection order.

For the physical interpretation of `trajectory.csv`, acceleration plots, and downrange estimates, see [trajectory reconstruction](trajectory-reconstruction.md).
