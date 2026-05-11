# Run Extraction

The **Run** page performs the full telemetry pipeline from a selected video and profile. It generates review frames, runs OCR, rebuilds clean telemetry, reconstructs the trajectory, writes plots, and optionally renders a synchronized overlay video. The page posts the same profile shape used by `webcalyzer run`, so saved templates remain interchangeable between the web UI and CLI.

## Run Setup

### Anatomy of a run

| Field | Description |
|---|---|
| **Profile template** | YAML profile loaded from the configured templates directory. Loading a template replaces the current form values. |
| **Input video** | Source webcast video. The path must be inside one of the server roots. |
| **Output parent folder** | Parent folder for run outputs. The app creates a timestamped child folder inside it. The path must be inside one of the server roots. |
| **Profile form** | Editable profile surface. The run button stays disabled until the form passes client validation. |
| **Run console** | Live status, phase events, stdout and stderr logs, cancellation, and finished output links. |

### Load a template

Click **Profile template** and choose a YAML profile. The template list is read from the server templates directory, and it updates after a new template is saved from the web app.

After loading a template, edit the profile sections as needed. Use **Preview YAML** to inspect the exact YAML that the server would write after validation.

Note: Loading another template replaces unsaved form edits. Save the current profile with **Save as template** before switching if you want to keep those edits.

### Select input and output paths

Click **Input video** and choose a supported video file from the file browser. Click **Output parent folder** and choose or type the destination folder. The run writes into a new child folder named `<YAML-FILENAME>_yyyy-mm-ddThh-mm-ss`.

The file picker is server-side. It sees the filesystem from the FastAPI process and only exposes paths under the configured roots.

### Configure runtime settings

Runtime choices are saved in the same profile sections as the rest of the YAML:

| Section | Settings |
|---|---|
| **General** | **Sample fps**, **OCR workers**, **OCR backend**, **Recognition level**, and **Skip full-frame OCR fallback**. |
| **Video overlay** | **Overlay engine**, **Overlay encoder**, plot mode, output filename, size, audio, and enablement. |

Rule of thumb: keep OCR backend, OCR workers, overlay engine, and overlay encoder on automatic settings unless you are comparing backends, working around local encoder support, or running a quick low-sample experiment.

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

Close the dialog with the **Dock run console** X or by clicking outside the dialog. This docks the console into the run page. Use the focus button in the docked console to reopen the centered dialog.

| Mode | Icon behavior | Use case |
|---|---|---|
| **Focused dialog** | The maximize-style icon returns the console to the centered focused view. | Watch a running job without page distractions. |
| **Docked on page** | The console sits at the top of the run page. | Keep the console in the page flow while checking configuration or output links. |

The console stream includes phase events, regular logs, warnings, errors, and output links as files are written. Files inside `review/` are generated for visual inspection but are not shown in the output-link list.

### Cancel a run

Click **Cancel** in the run console. Cancellation is checked between major phases and inside long-running work. During OCR extraction, including the default one-worker Vision path, the backend runs cancellable worker chunks and terminates the OCR worker pool as soon as the cancel request is observed.

Cancelled jobs keep files that were already written. For a clean retry, start another run from the same parent folder to get a fresh timestamped child folder, or remove partial files manually.

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
