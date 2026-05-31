# CLI Reference

The `webcalyzer` command exposes each major processing stage. Use `run` for the full pipeline, then use narrower subcommands when you want to inspect, rebuild, rescue, or rerender without repeating every stage. The CLI consumes the same YAML profiles used by the web UI, described in [profile configuration](profile-configuration.md).

## CLI Overview

### Anatomy of the CLI

| Subcommand | Description |
|---|---|
| `serve` | Launch the local FastAPI and React UI. |
| `sample-frames` | Generate representative review JPEGs and a contact sheet. |
| `calibrate` | Launch the OpenCV desktop calibration tool for segmented frame ranges and field slots. |
| `quantities` | Manage reusable telemetry quantity definitions. |
| `extract` | Run OCR extraction and write raw and clean telemetry. |
| `run` | Run review frame generation, extraction, trajectory reconstruction, plotting, and optional overlay rendering. |
| `plot` | Generate plots from an existing output directory. |
| `rebuild-clean` | Rebuild `telemetry_clean.csv` from `telemetry_raw.csv`. |
| `rescue` | Re-OCR failed samples with additional variants. |
| `reject-outliers` | Apply outlier rejection to an existing clean output. |
| `reconstruct-trajectory` | Rebuild `trajectory.csv` and trajectory-aware plots. |
| `render-overlay` | Render or rerender the synchronized overlay video. |
| `postprocess-regenerate` | Regenerate downstream artifacts from corrected raw telemetry. |

## Common Runs

### Run the full pipeline

Use `run` for normal processing:

```bash
webcalyzer run \
  --video /path/to/video.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs
```

This creates a child directory such as `outputs/new_glenn_ng3_2026-05-11T02-03-04`.

Add a sample-rate override for fast experiments:

```bash
webcalyzer run \
  --video /path/to/video.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs \
  --sample-fps 0.1
```

### Launch the web UI

Use `serve` to start the local UI:

```bash
webcalyzer serve --root "$PWD" --templates-dir "$PWD/configs"
```

Useful flags:

| Flag | Description |
|---|---|
| `--host` | Bind host, default `127.0.0.1`. |
| `--port` | Bind port, default `8765`. |
| `--root` | Allowed file browser root, repeatable. |
| `--templates-dir` | Directory containing YAML profiles. |
| `--dist-dir` | Built frontend bundle directory. |
| `--reload` | Enable development reload. |
| `--cors-origin` | Allowed frontend origin for development. |

### Generate review frames

Use `sample-frames` when you only need fixture JPEGs:

```bash
webcalyzer sample-frames \
  --video /path/to/video.mp4 \
  --config /path/to/profile.yaml \
  --output outputs/review \
  --count 20
```

Review frames include the active segment label and field bounding-box overlays. Use them to confirm [calibration](calibration.md) before running expensive OCR.

### Extract without overlay rendering

Use `extract` when you want OCR outputs but not the full `run` workflow:

```bash
webcalyzer extract \
  --video /path/to/video.mp4 \
  --config /path/to/profile.yaml \
  --output outputs/extract-only \
  --ocr-backend auto \
  --ocr-workers auto
```

When OCR flags are omitted, the CLI uses `ocr_backend`, `ocr_recognition_level`, `default_ocr_workers`, and `skip_full_frame_ocr_fallback` from the profile. A worker value of `0` keeps automatic worker selection.

Use `--ocr-skip-detection` when the full-frame OCR fallback is pulling in unrelated values from elsewhere in the image. It keeps recognition inside calibrated field crops only.

### Manage telemetry quantities

Use `quantities` to inspect or edit the shared custom quantity library:

```bash
webcalyzer quantities --templates-dir configs list
```

With the default `configs` templates directory, the library is stored at
`lib/custom_quantities.yaml`. The `--templates-dir` value still controls
which saved templates receive embedded snapshot updates.

Add a quantity:

```bash
webcalyzer quantities --templates-dir configs add \
  --name Acceleration \
  --dimensionality 'L/T^2' \
  --display-unit 'm/s^2' \
  --alias G=standard_gravity
```

Edit and delete commands update affected templates immediately:

```bash
webcalyzer quantities --templates-dir configs edit q_acceleration --display-unit 'm/s^2'
webcalyzer quantities --templates-dir configs delete q_acceleration
```

Default quantities are present in the library for canonical fields. They can be edited but cannot be deleted.

## Downstream Commands

### Rebuild downstream outputs

Use `rebuild-clean` after editing raw data or anchor points:

```bash
webcalyzer rebuild-clean --output outputs/my-run
```

Use `reject-outliers` when you want to adjust filtering. If `--chi2` or
`--window-s` are omitted, the command uses the saved trajectory outlier
settings from `config_resolved.yaml`, falling back to `9.0` and `40.0`
when no profile is present:

```bash
webcalyzer reject-outliers --output outputs/my-run --chi2 9 --window-s 40
```

Use `reconstruct-trajectory` when changing interpolation or integration settings:

```bash
webcalyzer reconstruct-trajectory \
  --output outputs/my-run \
  --trajectory-interpolation pchip \
  --trajectory-integration rk4
```

The physics behind these options is described in [trajectory reconstruction](trajectory-reconstruction.md#integrate-velocity-into-path-distance).

### Rescue failed OCR samples

Use `rescue` when raw extraction produced parse failures:

```bash
webcalyzer rescue \
  --video /path/to/video.mp4 \
  --output outputs/my-run \
  --config outputs/my-run/config_resolved.yaml
```

If `--config` is omitted, rescue attempts to use `config_resolved.yaml` from the output directory.

### Rerender the overlay

Use `render-overlay` after changing overlay settings or when you want to try another renderer:

```bash
webcalyzer render-overlay \
  --video /path/to/video.mp4 \
  --output outputs/my-run \
  --plot-mode with_rejected \
  --overlay-engine ffmpeg \
  --overlay-encoder libx264
```

Note: `render-overlay` reads `telemetry_clean.csv`, optional `telemetry_rejected.csv`, optional `trajectory.csv`, and the profile from `config_resolved.yaml` unless you pass `--config`.

### Retry post-processing regeneration

Use `postprocess-regenerate` after a visual editor save was interrupted or
when a manifest-enabled raw dataset was corrected:

```bash
webcalyzer postprocess-regenerate --output outputs/my-run
```

For manifest-enabled outputs, downstream rebuild commands consume the
current materialized `telemetry_raw.csv` exactly as saved. Profile anchor
points are injected during initial extraction and are not reinserted during
later regeneration.

## Verification

### Verify CLI behavior

For a configuration change, run at least:

```bash
webcalyzer run --video /path/to/video.mp4 --config /path/to/profile.yaml --output /path/to/output-parent
webcalyzer reconstruct-trajectory --output /path/to/output-parent/profile_yyyy-mm-ddThh-mm-ss
webcalyzer render-overlay --video /path/to/video.mp4 --output /path/to/output-parent/profile_yyyy-mm-ddThh-mm-ss
```

For a local environment check without a full run, use:

```bash
webcalyzer serve --root "$PWD" --templates-dir "$PWD/configs"
```

Then confirm `/api/meta` responds and the web UI can load at `http://127.0.0.1:8765`. Continue with [run extraction](run-extraction.md) for the web workflow.
