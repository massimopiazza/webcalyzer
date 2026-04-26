# Webcalyzer

`webcalyzer` is a modernized telemetry extraction tool for launch webcast videos.
This repository is tuned for Blue Origin New Glenn style telemetry overlays and
was validated against `BlueOrigin_NG-3.mp4`.

## Features

- Interactive OpenCV calibration UI for relaxed telemetry bounding boxes.
- OCR-based extraction with field-specific sanitization instead of brittle
  template matching.
- Stage-aware parsing for a single-stack to dual-stage overlay transition.
- SI-normalized clean outputs plus raw OCR/debug outputs.
- Representative frame sampling and regression-fixture generation.
- Automatic PDF plotting for extracted telemetry.

## Install

```bash
python3 -m pip install -e .
```

## Typical workflow

Generate representative review frames:

```bash
webcalyzer sample-frames \
  --video BlueOrigin_NG-3.mp4 \
  --output outputs/ng3_review
```

Launch the interactive calibration UI:

```bash
webcalyzer calibrate \
  --video BlueOrigin_NG-3.mp4 \
  --config configs/blue_origin/new_glenn_default.yaml \
  --output configs/blue_origin/new_glenn_ng3.yaml
```

Run extraction and plotting:

```bash
webcalyzer run \
  --video BlueOrigin_NG-3.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs/ng3
```

Re-render the synchronized video overlay after outlier rejection:

```bash
webcalyzer render-overlay \
  --video BlueOrigin_NG-3.mp4 \
  --output outputs/ng3 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --plot-mode with_rejected
```

## Output files

- `telemetry_raw.csv`
- `telemetry_clean.csv`
- `telemetry_rejected.csv`
- `run_metadata.json`
- `config_resolved.yaml`
- `telemetry_overlay.mp4`
- `plots/filtered/summary.pdf`
- `plots/filtered/coverage.pdf`
- `plots/filtered/stage1.pdf`
- `plots/filtered/stage2.pdf`
- `plots/with_rejected/` mirrored plot set with hollow rejected outlier points
- `review/` sampled frames and contact sheets

The YAML profile uses `fixture_frame_count` plus `fixture_time_range_s` for
representative calibration/review frames. Field boxes are normalized
`bbox_x1y1x2y2: [x1, y1, x2, y2]` arrays. `video_overlay` controls the rendered
video copy, including `plot_mode`, `width_fraction`, and `height_fraction`.

## Calibration controls

- `1`-`5`: select field
- `n` / `p`: next or previous representative frame
- `c`: clear selected field
- `s`: save config
- `q`: quit
- Mouse drag: draw a new bounding box for the selected field

Field order:

1. `stage1_velocity`
2. `stage1_altitude`
3. `met`
4. `stage2_velocity`
5. `stage2_altitude`
