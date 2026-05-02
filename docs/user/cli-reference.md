# CLI Reference

The `webcalyzer` command exposes each major processing stage. Use `run` for the full pipeline, then use narrower subcommands when you want to inspect, rebuild, rescue, or rerender without repeating every stage. The CLI consumes the same YAML profiles used by the web UI, described in [profile configuration](profile-configuration.md).

## CLI Overview

### Anatomy of the CLI

| Subcommand | Description |
|---|---|
| `serve` | Launch the local FastAPI and React UI. |
| `sample-frames` | Generate representative review JPEGs and a contact sheet. |
| `calibrate` | Launch the OpenCV desktop calibration tool. |
| `extract` | Run OCR extraction and write raw and clean telemetry. |
| `run` | Run review frame generation, extraction, trajectory reconstruction, plotting, and optional overlay rendering. |
| `plot` | Generate plots from an existing output directory. |
| `rebuild-clean` | Rebuild `telemetry_clean.csv` from `telemetry_raw.csv`. |
| `rescue` | Re-OCR failed samples with additional variants. |
| `reject-outliers` | Apply outlier rejection to an existing clean output. |
| `reconstruct-trajectory` | Rebuild `trajectory.csv` and trajectory-aware plots. |
| `render-overlay` | Render or rerender the synchronized overlay video. |

## Common Runs

### Run the full pipeline

Use `run` for normal processing:

```bash
webcalyzer run \
  --video /path/to/video.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs/my-run
```

Add a sample-rate override for fast experiments:

```bash
webcalyzer run \
  --video /path/to/video.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs/quick-check \
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

Review frames include field bounding-box overlays. Use them to confirm [calibration](calibration.md) before running expensive OCR.

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

Use `--ocr-skip-detection` only after boxes are stable. It can speed up crop-based OCR, but it reduces detection fallback behavior.

## Downstream Commands

### Rebuild downstream outputs

Use `rebuild-clean` after editing raw data or anchor points:

```bash
webcalyzer rebuild-clean --output outputs/my-run
```

Use `reject-outliers` when you want to adjust filtering:

```bash
webcalyzer reject-outliers --output outputs/my-run --chi2 36 --window-s 40
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

## Verification

### Verify CLI behavior

For a configuration change, run at least:

```bash
webcalyzer run --video /path/to/video.mp4 --config /path/to/profile.yaml --output /path/to/output
webcalyzer reconstruct-trajectory --output /path/to/output
webcalyzer render-overlay --video /path/to/video.mp4 --output /path/to/output
```

For a local environment check without a full run, use:

```bash
webcalyzer serve --root "$PWD" --templates-dir "$PWD/configs"
```

Then confirm `/api/meta` responds and the web UI can load at `http://127.0.0.1:8765`. Continue with [run extraction](run-extraction.md) for the web workflow.
