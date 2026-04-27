# Webcalyzer

`webcalyzer` extracts numeric telemetry (velocity, altitude, mission elapsed
time) from a launch webcast video by OCR'ing the on-screen overlay frame by
frame, sanitizing the text, and producing CSVs, plots, and a video copy with
a synchronized telemetry plot.

The repository was originally tuned for Blue Origin New Glenn-style overlays and was
validated against it, but the calibration profile is
generic: any printed-digit telemetry overlay with stable bounding boxes can
be supported by writing a new YAML profile.

## High-level pipeline

```
                            ┌─────────────────────────┐
   1. sample-frames    ───▶ │ representative JPEGs +  │
                            │ contact_sheet.jpg       │
                            └─────────────────────────┘
                                       │
                                       ▼
                            ┌─────────────────────────┐
   2. calibrate        ───▶ │ YAML profile with field │
                            │ bounding boxes          │
                            └─────────────────────────┘
                                       │
                                       ▼
   3. run / extract  ──▶ Phase A (parallel)        Phase B (sequential)
                          ├─ frame decode          ├─ MET tracking
                          ├─ strip OCR             ├─ stage activation
                          └─ field-fallback OCR    ├─ plausibility filter
                                                   └─ choose best measurement
                                       │
                                       ▼
                            ┌─────────────────────────┐
   outputs/<run>/      ───▶ │ telemetry_raw.csv       │
                            │ telemetry_clean.csv     │
                            │ trajectory.csv          │
                            │ telemetry_rejected.csv  │
                            │ run_metadata.json       │
                            │ config_resolved.yaml    │
                            │ plots/{filtered,…}/     │
                            │ telemetry_overlay.mp4   │
                            └─────────────────────────┘
                                       │
                          ┌────────────┴───────────┐
                          ▼                        ▼
                  4. reject-outliers        5. rescue (re-OCR)
                          │                        │
                          └─────────► rebuild-clean
                          ▲
                          └─ idempotent against telemetry_raw.csv
```

The `run` subcommand stitches `extract → plot → render-overlay` together;
the individual subcommands exist so each stage can be re-run independently
without redoing the slow OCR work.

## Install

```bash
python3 -m pip install -e .
```

On macOS the install will additionally pull in `pyobjc-framework-Vision` and
`pyobjc-framework-Quartz`, enabling the Apple Vision OCR backend. On Linux
and Windows those are skipped automatically and the project falls back to
the cross-platform RapidOCR backend.

<img width="1280" height="720" alt="telemetry_overlay" src="https://github.com/user-attachments/assets/ed088a44-bccb-4c0c-88f6-f8021880f63a" />

## Argument reference

### Flags shared across OCR-bearing subcommands (`extract`, `run`, `rescue`)

| Flag | Type | Required | Default | Options | Notes |
|------|------|----------|---------|---------|-------|
| `--video` | path | yes | — | any video file readable by OpenCV/AVFoundation | The source video. |
| `--config` | path | yes (`extract`/`run`); optional (`rescue`) | — | path to a YAML profile | Loaded via `webcalyzer.config.load_profile`. |
| `--output` | path | yes | — | any directory path | Created if missing; CSVs and metadata are written here. |
| `--ocr-backend` | choice | no | `auto` | `auto`, `rapidocr`, `vision` | `auto` selects Vision on macOS when pyobjc-Vision is importable, RapidOCR otherwise. Forcing `vision` on a non-macOS host raises a clear error. |
| `--ocr-recognition-level` | choice | no | `accurate` | `accurate`, `fast` | Vision-only. Ignored when the resolved backend is RapidOCR. |
| `--ocr-workers` | int or `auto` | no (`extract`/`run` only) | `auto` | positive integer or `auto` | `auto` resolves to `max(1, physical_cores - 1)` for RapidOCR and `1` for Vision. |
| `--ocr-skip-detection` | flag | no (`extract`/`run` only) | off | — | Opt-in. Bypasses detection and runs recognition only on each calibrated field crop. |

### Subcommand-specific arguments

| Subcommand | Flag | Type | Required | Default | Options | Notes |
|------------|------|------|----------|---------|---------|-------|
| `sample-frames` | `--video` | path | yes | — | — | |
|                 | `--config` | path | yes | — | — | |
|                 | `--output` | path | yes | — | — | Directory for review JPEGs and `contact_sheet.jpg`. |
|                 | `--count` | int | no | profile's `fixture_frame_count` | any positive int | Override the per-profile count for this run only. |
| `calibrate` | `--video` | path | yes | — | — | |
|             | `--config` | path | yes | — | — | Loaded as the starting point; saved into `--output`. |
|             | `--output` | path | yes | — | — | Destination YAML for the edited profile. |
| `extract` | `--sample-fps` | float | no | profile's `default_sample_fps` (0.5 in the shipped NG-3 profile) | any positive float | Sampling cadence in frames per second. Lower = fewer samples = faster, less detail. |
| `run` | `--sample-fps` | float | no | profile's `default_sample_fps` | any positive float | Same semantics as `extract`. |
|       | `--skip-video-overlay` | flag | no | overlay enabled | — | Skip the post-extract overlay render. |
|       | `--overlay-plot-mode` | choice | no | profile's `video_overlay.plot_mode` | `filtered`, `with_rejected` | Choose which dataset drives the embedded plot. |
|       | `--overlay-engine` | choice | no | `auto` | `auto`, `ffmpeg`, `opencv` | `auto` picks `ffmpeg` when it's on `PATH`, else `opencv`. Force `ffmpeg` to fail loudly if missing. |
|       | `--overlay-encoder` | choice | no | `auto` | `auto`, `videotoolbox`, `nvenc`, `qsv`, `vaapi`, `libx264` (each also accepts the `h264_…` long form) | `auto` walks the hardware-encoder priority and falls through to `libx264`. Ignored when the resolved engine is `opencv`. |
| `plot` | `--output` | path | yes | — | — | Existing run directory containing `telemetry_clean.csv`. |
| `rebuild-clean` | `--output` | path | yes | — | — | Re-derives `telemetry_clean.csv` from `telemetry_raw.csv`. |
| `rescue` | `--video` | path | yes | — | — | |
|          | `--config` | path | no | falls back to `<output>/config_resolved.yaml` | — | Optional override of the profile saved alongside the run. |
|          | `--output` | path | yes | — | — | |
| `reject-outliers` | `--output` | path | yes | — | — | |
|                   | `--chi2` | float | no | `36.0` | any positive float | Per-field squared residual threshold (1-D Mahalanobis). |
|                   | `--window-s` | float | no | `40.0` | any positive float | Neighbor window in seconds for the local residual fit. |
| `reconstruct-trajectory` | `--output` | path | yes | — | — | Existing run directory containing `telemetry_clean.csv`. |
|                          | `--config` | path | no | `<output>/config_resolved.yaml` | — | Optional YAML profile override. |
|                          | `--trajectory-interpolation` | choice | no | profile's `trajectory.interpolation_method` | `linear`, `pchip`, `akima`, `cubic` | |
|                          | `--trajectory-integration` | choice | no | profile's `trajectory.integration_method` | `euler`, `midpoint`, `trapezoid`, `rk4`, `simpson` | `simpson` is accepted as an alias for `rk4`. |
|                          | `--trajectory-derivative-window-s` | float | no | profile's `trajectory.derivative_smoothing_window_s` | any positive float | Savitzky-Golay window length (seconds) for the acceleration plot. |
| `render-overlay` | `--video` | path | yes | — | — | |
|                  | `--output` | path | yes | — | — | |
|                  | `--config` | path | no | `<output>/config_resolved.yaml` if present | — | Optional YAML profile with `video_overlay` and trajectory acceleration settings. |
|                  | `--plot-mode` | choice | no | profile's `video_overlay.plot_mode` (`filtered`) | `filtered`, `with_rejected` | |
|                  | `--width-fraction` | float | no | profile's `video_overlay.width_fraction` | 0.05–1.0 | Overlay panel width as a fraction of the source frame width. |
|                  | `--height-fraction` | float | no | profile's `video_overlay.height_fraction` | 0.05–1.0 | Overlay panel height as a fraction of the source frame height. |
|                  | `--output-filename` | string | no | profile's `video_overlay.output_filename` (`telemetry_overlay.mp4`) | any filename | Output video filename inside `--output`. |
|                  | `--no-audio` | flag | no | audio muxed when `ffmpeg` is on `PATH` | — | Skip the audio re-mux step. |
|                  | `--overlay-engine` | choice | no | `auto` | `auto`, `ffmpeg`, `opencv` | Same semantics as `run --overlay-engine`. |
|                  | `--overlay-encoder` | choice | no | `auto` | `auto`, `videotoolbox`, `nvenc`, `qsv`, `vaapi`, `libx264` | Ignored when the resolved engine is `opencv`. |

## Tips

- Heaviest-load configurations first: run `webcalyzer run` once, eyeball
  the plots, then iterate on the YAML profile and use the lighter
  subcommands (`rebuild-clean`, `reject-outliers`, `render-overlay`) to
  avoid re-OCR'ing the entire video.
- For quick experiments, drop `--sample-fps` to e.g. `0.1` so each
  iteration takes a fraction of the time. Production runs at the
  profile's default usually look right at `0.5`.
- On Apple Silicon, leaving `--ocr-backend auto` is the right default;
  override with `--ocr-backend rapidocr` when you want platform-parity
  output for a regression diff against a Linux/Windows run.

---
---

# Architecture
## Overlay rendering architecture

The synchronized telemetry overlay video sits behind the same kind of
backend selector as the OCR pipeline. Two engines ship in-tree:

- **`ffmpeg`**: single-shot pipeline. Pre-renders the unique overlay
  panels to PNGs in a temp dir, hands them to a single `ffmpeg`
  invocation via the `concat` demuxer, and lets ffmpeg do the alpha
  compositing (in its SIMD-optimized `overlay` filter) and the encode
  on a hardware H.264 encoder when one is available
  (`h264_videotoolbox` / `h264_nvenc` / `h264_qsv` / `h264_vaapi`,
  with `libx264` as the cross-platform fallback). This is the default
  when ffmpeg is on `PATH`.
- **`opencv`**: the in-process Python loop using `cv2.VideoCapture`
  and `cv2.VideoWriter`. Numpy alpha-blends each frame, writes via the
  AVFoundation/FFmpeg `cv2` backend on the platform. Used as the
  fallback when `ffmpeg` isn't installed.

`--overlay-engine auto` (the default) picks `ffmpeg` if `which ffmpeg`
finds it, otherwise `opencv`. Force one with `--overlay-engine ffmpeg`
or `--overlay-engine opencv`. The FFmpeg path also exposes
`--overlay-encoder` for choosing the H.264 encoder; `auto` walks
`videotoolbox → nvenc → qsv → vaapi → libx264` and picks the first one
present in the local ffmpeg build.

The overlay only changes at sample reveal points (one new measurement
per OCR sample, plus per-step trajectory reconstruction points), so we
build a small panel cache once and replay it across all source frames.
Reveal times are quantized to a 0.5 s MET grid (`REVEAL_QUANTIZE_STEP_S`
in `overlay.py`) so the panel cache and concat list don't balloon when
the trajectory module emits sub-second integration steps.

## OCR architecture (Layer 1 + Layer 2)

OCR is split behind a small backend interface (`OCRBackend`) so the rest of
the pipeline doesn't care which engine is producing the text. Two backends
ship in-tree:

- **`rapidocr`**: ONNXRuntime-backed RapidOCR running on CPU. Available
  on every platform. The default everywhere except macOS.
- **`vision`**: Apple Vision (`VNRecognizeTextRequest`). Runs on the ANE
  and GPU on Apple Silicon. The default on macOS when the pyobjc bindings
  are installed.

`--ocr-backend auto` (the default) picks whichever is available; pass
`rapidocr` or `vision` explicitly to force one or the other.

The OCR step itself is split into two phases:

- **Phase A (stateless)** For each sampled frame, run the strip OCR and
  any per-field fallback. Phase A is *parallelizable*: with
  `--ocr-workers N>1` the sample list is chunked across `N` worker
  processes (each opens its own video capture) and Phase A runs in
  parallel.
- **Phase B (sequential)** Walk the per-frame OCR results in frame
  order and apply the order-dependent logic: MET tracking with rolling
  offset filter, stage activation, plausibility scoring against the
  previous parsed value, and `choose_best_measurement`.

`--ocr-skip-detection` (opt-in, off by default) is an alternative
Phase A path that bypasses text detection entirely. It uses the
calibrated field boxes directly and runs recognition only on each
crop, in a single batched call (RapidOCR) or a per-crop call (Vision).
It is the fastest option on RapidOCR; on Vision it is roughly the
same speed as the default path because Vision still detects internally
on each crop.

Per-run choices (backend, worker count, skip-detection) are recorded in
`run_metadata.json` so result directories are self-describing.

## Subcommands

The single CLI entry point `webcalyzer` exposes every stage as a
subcommand. All sub-options shown below also have short help text via
`webcalyzer <subcommand> --help`.

### `sample-frames`: produce review JPEGs

Generates `fixture_frame_count` representative frames inside
`fixture_time_range_s` plus a contact sheet, used as input to
calibration and as a regression set.

```bash
webcalyzer sample-frames \
  --video BlueOrigin_NG-3.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs/ng3/review
```

### `calibrate`: interactive bounding-box editor

Opens an OpenCV window with the representative frames. Mouse-drag to
draw a box, press a number key to switch field, `n`/`p` to flip pages,
`s` to save, `q` to quit.

```bash
webcalyzer calibrate \
  --video BlueOrigin_NG-3.mp4 \
  --config configs/blue_origin/new_glenn_default.yaml \
  --output configs/blue_origin/new_glenn_ng3.yaml
```

| Key | Action |
|-----|--------|
| `1`–`5` | Select field (stage1_velocity, stage1_altitude, met, stage2_velocity, stage2_altitude) |
| `n` / `p` | Next / previous representative frame |
| `c` | Clear the selected field's box |
| `s` | Save the YAML profile |
| `q` | Quit |
| Mouse drag | Draw a new bounding box for the selected field |

### `extract`:  OCR + sanitize, no plots/overlay

Reads the video and produces just the CSVs and metadata. Use this when
iterating on OCR settings without wanting to re-render the overlay
video.

```bash
webcalyzer extract \
  --video BlueOrigin_NG-3.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs/ng3 \
  --ocr-backend auto \
  --ocr-workers auto
```

### `run`: extract + plot + render overlay

The convenience subcommand. Equivalent to running `sample-frames`,
`extract`, `plot`, and `render-overlay` back to back into the same
output directory.

```bash
webcalyzer run \
  --video BlueOrigin_NG-3.mp4 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --output outputs/ng3
```

### `plot`: regenerate plots from an existing run

Re-renders the PDF plots from `telemetry_clean.csv` without re-OCR'ing.

```bash
webcalyzer plot --output outputs/ng3
```

### `rebuild-clean`:  re-derive `telemetry_clean.csv` from raw text

Re-runs the sanitization and stage-activation logic over
`telemetry_raw.csv` without reading the video. Useful after editing
sanitization rules.

```bash
webcalyzer rebuild-clean --output outputs/ng3
```

### `rescue`:  multi-variant re-OCR for missing rows

For rows whose strip OCR failed, re-reads the video, runs a tiered
multi-variant OCR (`fast → medium → full`) and tries multiple frame
offsets around the original sample. Updates `telemetry_raw.csv` in
place and rebuilds the clean CSV.

```bash
webcalyzer rescue \
  --video BlueOrigin_NG-3.mp4 \
  --output outputs/ng3 \
  --config configs/blue_origin/new_glenn_ng3.yaml
```

### `reject-outliers`:  Mahalanobis filter

Drops samples whose squared local residual exceeds the threshold and
moves them to `telemetry_rejected.csv`. Operates per field, per stage,
on a sliding MET window. Repeatable: re-running on the same directory
re-derives clean+rejected from `telemetry_raw.csv` so you can tighten
or loosen thresholds without losing data.

```bash
webcalyzer reject-outliers --output outputs/ng3 --chi2 36 --window-s 40
```

### `reconstruct-trajectory`:  integrate velocity into downrange

Rebuilds `trajectory.csv`, appends trajectory columns to
`telemetry_clean.csv`, and refreshes plots without re-OCR'ing.

```bash
webcalyzer reconstruct-trajectory \
  --output outputs/ng3 \
  --trajectory-interpolation pchip \
  --trajectory-integration rk4
```

### `render-overlay`:  synchronized plot-on-video

Re-renders the telemetry overlay video from
`telemetry_clean.csv`. Useful when you've updated the plot mode or
overlay margins without re-OCR'ing.

```bash
webcalyzer render-overlay \
  --video BlueOrigin_NG-3.mp4 \
  --output outputs/ng3 \
  --config configs/blue_origin/new_glenn_ng3.yaml \
  --plot-mode with_rejected
```

When the overlay video is written, webcalyzer also writes a same-stem GIF
preview, for example `telemetry_overlay.gif`. The preview remaps the full
source duration to 15 seconds, samples it at 4 fps, and scales it down to
fit within 1280×720.

## Output files

Every successful `extract` / `run` writes the following into the output
directory:

| File | Purpose |
|------|---------|
| `telemetry_raw.csv` | One row per sampled frame, all fields, with raw OCR text, parse status, raw value, raw unit, SI value, OCR variant. Append-only source of truth. |
| `telemetry_clean.csv` | Same rows in SI units (m/s, m, s) with plausibility filtering, stage activation, and appended trajectory columns applied. |
| `trajectory.csv` | Dense fixed-step trajectory reconstruction. Interpolated velocity/altitude live here only; the original telemetry columns keep their gaps. |
| `telemetry_rejected.csv` | Outliers removed by `reject-outliers`. Initially empty; populated by the outlier rejection step. |
| `run_metadata.json` | Video metadata + sample count + OCR settings used for the run (backend, workers, skip_detection, recognition level, Phase A wall time). |
| `config_resolved.yaml` | The profile actually used by the run, written verbatim so the result directory is self-describing even if the source YAML changes later. |
| `plots/filtered/{summary,coverage,stage1,stage2,downrange}.pdf` | Plots driven by `telemetry_clean.csv` and `trajectory.csv`. |
| `plots/with_rejected/…` | Mirrored plot set with hollow circles for rejected samples. |
| `telemetry_overlay.mp4` | Source video copy with a translucent telemetry plot composited into the top-left corner (margins are symmetric). |
| `telemetry_overlay.gif` | 15-second looping preview of the overlay video, sampled across the full clip at 4 fps and scaled down to 720p. |
| `review/` | Representative frame JPEGs and the contact sheet, produced by `sample-frames`. |

## YAML profile

```yaml
profile_name: blue_origin_new_glenn
description: Default New Glenn telemetry profile derived from BlueOrigin_NG-3.mp4.

default_sample_fps: 0.5         # default cadence used by extract/run
fixture_frame_count: 20         # representative frame count for sample-frames/calibrate
fixture_time_range_s: [0, 840]  # MET window (in seconds) to draw fixtures from

video_overlay:
  enabled: true
  plot_mode: filtered           # 'filtered' or 'with_rejected'
  width_fraction: 0.5           # overlay panel width as fraction of frame width
  height_fraction: 0.65
  output_filename: telemetry_overlay.mp4
  include_audio: true

trajectory:
  enabled: true
  interpolation_method: pchip     # linear, pchip, akima, cubic
  integration_method: rk4         # euler, midpoint, trapezoid, rk4
  outlier_preconditioning_enabled: true
  coarse_step_smoothing_enabled: true
  coarse_step_max_gap_s: 10.0
  coarse_altitude_threshold_m: 500.0
  coarse_velocity_threshold_mps: 50.0
  acceleration_source_gap_threshold_s: 10.0
  derivative_smoothing_window_s: 20.0  # Savitzky-Golay window for d/dt(velocity)
  derivative_smoothing_polyorder: 3
  derivative_min_window_samples: 5
  derivative_smoothing_mode: interp
  launch_site:
    latitude_deg: null            # WGS84 inputs are optional
    longitude_deg: null
    azimuth_deg: null

# Optional. When omitted, the built-in MPH/FT/MI/T+ vocabulary is used.
# Add this block to retarget the OCR pipeline to a feed that uses different
# units, language, or timestamp formatting without code changes. customWords
# (Apple Vision) are auto-derived from the alias list below.
parsing:
  velocity:
    default_unit: MPH
    inferred_units_with_separator: [MPH]      # used when no explicit unit label
    inferred_units_without_separator: [MPH]
    units:
      MPH: { aliases: [MPH, MPN, MРН, MPI, M/H], si_factor: 0.44704 }
      KPH: { aliases: [KPH, KMH, KM/H, KMPH], si_factor: 0.27777777777777778 }
      MPS: { aliases: [M/S, MPS], si_factor: 1.0 }
  altitude:
    default_unit: FT
    ambiguous_default_unit: FT                # ties prefer the smaller value
    inferred_units_with_separator: [FT, MI]   # 6-digit FT vs 3-digit MI
    inferred_units_without_separator: [FT]
    units:
      FT: { aliases: [FT, F7, FI, ET, E7, EI], si_factor: 0.3048 }
      MI: { aliases: [MI, ML, M1], si_factor: 1609.344 }
      KM: { aliases: [KM], si_factor: 1000.0 }
      M:  { aliases: [M], si_factor: 1.0 }
  met:
    timestamp_patterns:
      - 'T\s*([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?'
      - '([+-])?\s*(\d{2})(?::(\d{2}))(?::(\d{2}))?'

hardcoded_raw_data_points:       # optional synthetic raw points keyed by MET
  - mission_elapsed_time_s: 560.0
    stage1:
      velocity_mps: 0.0
      altitude_m: 0.0

fields:
  stage1_velocity:              # one entry per field
    kind: velocity              # one of: velocity, altitude, met
    stage: stage1               # one of: stage1, stage2, null (for met)
    bbox_x1y1x2y2: [0.123, 0.903, 0.233, 0.957]  # normalized [x0, y0, x1, y1]
  stage1_altitude: { … }
  met:               { kind: met, stage: null, bbox_x1y1x2y2: [ … ] }
  stage2_velocity:   { … }
  stage2_altitude:   { … }
```

`hardcoded_raw_data_points` are merged into `telemetry_raw.csv` before clean
telemetry is built. A point with a new `mission_elapsed_time_s` inserts a
synthetic row; a point whose timestamp already exists replaces the configured
field values in that row. Supported stage keys are `stage1` and `stage2`, each
with optional `velocity_mps` and `altitude_m`.

The video overlay panel sits in the top-left corner with a symmetric pixel
margin (`max(8, height * 0.012)`) on both the top and left, so the plot is
inset from the corner instead of flush against the screen edges.

## Trajectory reconstruction

Trajectory reconstruction treats webcast velocity as total speed magnitude
and altitude as authoritative. Stage 1 is anchored at MET 0. Stage 2 is not
anchored at liftoff; it starts at the first interval where Stage 2 velocity
and altitude are both available and inherits Stage 1's reconstructed
downrange at that time. From there the two stage paths can bifurcate.

For each reconstructed stage, the pipeline interpolates velocity and
altitude internally on a fixed time grid, integrates total speed, then
derives each downrange increment from the integrated path-length increment
and altitude change. The interpolated velocity/altitude samples are written
only to `trajectory.csv`; stage plots still show gaps in the original
telemetry. The summary plot overlays those interpolated series on top of
the filtered telemetry from `telemetry_clean.csv`, adds reconstructed
downrange as the third subplot, and adds estimated acceleration in g as the
bottom subplot. The acceleration subplot also shows the hidden smoothed
velocity series on a second y-axis. The video overlay uses the same
downrange/acceleration order and the same acceleration series. For
acceleration only, each source-supported interpolated velocity segment is
passed through a cubic smoothing spline with an automatically estimated
robust smoothing factor before the derivative is taken. Acceleration is
masked across source velocity gaps longer than 10 seconds, so long telemetry
outages do not produce derivative spikes.

Before interpolation, reconstruction preconditions the filtered values for
trajectory use only. With `outlier_preconditioning_enabled`, isolated
knots whose local linear residual exceeds the altitude or velocity
threshold are removed from the interpolation input, which prevents a single
surviving OCR artifact from forcing a large reconstructed excursion. The
same trajectory-only pass then detects coarse stepwise telemetry. By
default, altitude plateaus with changes of at least `500 m` and velocity
plateaus with changes of at least `50 m/s` are converted into smooth
transition knots at the midpoint between the last sample on the old plateau
and the first sample on the new plateau. That midpoint conversion is
gap-aware: it is only applied when the gap between the two plateaus is at
most `coarse_step_max_gap_s` (`10 s` by default), so long telemetry outages
remain long-gap interpolation problems instead of being collapsed into a
fake midpoint step. This conditioning is used only inside `trajectory.csv`
and the interpolated summary overlays; the filtered telemetry columns and
stage plots remain unchanged.

Interpolation options:

- `pchip` (default): shape-preserving cubic Hermite interpolation. This is
  the recommended default because it avoids the overshoot that ordinary
  cubic splines can introduce across OCR gaps while still being smoother
  than linear interpolation.
- `akima`: local cubic interpolation that can behave well around irregular
  samples and moderate noise, but it is not as strictly shape-preserving as
  PCHIP.
- `cubic`: natural cubic spline. Smooth, but can overshoot across long gaps
  and is best reserved for very clean telemetry.
- `linear`: most conservative and least smooth; useful for debugging.

Integration is fixed-step at the OCR sample period (`1 / sample_fps`),
so the trajectory grid stays consistent with the input cadence and there
is no separate `integration_step_s` to keep in sync. `rk4` is the
default integrator; for this time-only telemetry integration it is
equivalent to Simpson-style quadrature over each step. `trapezoid`,
`midpoint`, and `euler` are available for simpler comparisons.

The `--trajectory-interpolation`, `--trajectory-integration`, and
`--trajectory-derivative-window-s` overrides are accepted by `extract`,
`run`, and `reconstruct-trajectory`.

For the acceleration estimate, velocity is differentiated with a
Savitzky-Golay filter whose settings live in YAML:
`derivative_smoothing_window_s` (default `20 s`),
`derivative_smoothing_polyorder` (default `3`),
`derivative_min_window_samples` (default `5`),
`derivative_smoothing_mode` (default `interp`), and
`acceleration_source_gap_threshold_s` (default `10 s`).

### Why Savitzky–Golay for ẏ

Differentiating a measured signal amplifies high-frequency noise: if
y(t) = s(t) + ε(t) with white-noise ε of variance σ², a finite-difference
estimator returns dy/dt with variance ∝ σ²/Δt², so naive `np.gradient`
on OCR-derived velocity produces a derivative dominated by jitter. The
classic remedy — and the one we use — is a Savitzky–Golay filter
(Savitzky & Golay, 1964; Schafer, 2011).

Inside a sliding window of length `2M+1` centred on time `t_i`, fit a
polynomial of degree `K` to the local samples in least-squares:

```
              K
ŝ(t; t_i) =   Σ   c_k(i) · (t − t_i)^k
              k=0
```

The smoothed value at `t_i` is `ŝ(t_i; t_i) = c_0(i)`; its derivative
is `dŝ/dt|_{t_i} = c_1(i)`. Because the design matrix depends only on
the *offsets* (t_{i+j} − t_i), uniform sampling makes the least-squares
solution a single fixed convolution kernel:

```
              M
ŝ(t_i)   =   Σ    h_0[j] · y_{i+j}
            j=−M

dŝ/dt|_{t_i} = (1/Δt) · Σ    h_1[j] · y_{i+j}
                       j=−M
```

so each filter pass is one FIR convolution with kernels precomputed by
`scipy.signal.savgol_coeffs`. The kernel has two useful properties:

1. **Polynomial reproduction.** Signals that are exactly polynomial of
   degree ≤ K pass through (and their derivative likewise) with zero
   bias, so a constant-jerk segment is reproduced exactly when K ≥ 3.
2. **Noise reduction.** For zero-mean white noise, the variance of
   `dŝ/dt|_{t_i}` is `σ² · ‖h_1‖² / Δt²`. Increasing the window halves
   `‖h_1‖²` per doubling, so a longer window quadratically improves
   noise rejection — at the cost of bandwidth, which is roughly
   `f_c ≈ (K + 1) / (π · (2M+1) · Δt)`.

Two design choices follow:

- **Sizing the window in seconds** (rather than samples) is what makes
  the filter FPS-independent: at higher sample rate, more samples fall
  inside the same time window, lowering `‖h_1‖²` and automatically
  buying noise rejection without retuning. The configured 20 s default
  was chosen by sweeping `(window, polyorder)` against (a) a synthetic
  rocket-like profile with Gaussian velocity noise and (b) the NG-3
  trajectory; it gives ~3.5× lower RMSE versus ground truth than a 5 s
  window without visibly blunting staging or MECO transitions.
- **Polynomial order 3** is the minimum that reproduces both the value
  and the derivative of a constant-jerk segment exactly (`a = a₀ + j·t`
  ⇒ `v = v₀ + a₀·t + ½ j·t²`, cubic in `t`). Going to K = 4 buys
  marginal bandwidth at the cost of more noise pass-through; K = 2
  is smoother but introduces a few-percent peak-shaving bias around
  rapid transitions.

The Savitzky-Golay configuration is exposed in YAML under `trajectory`.
The CLI `--trajectory-derivative-window-s` flag remains as a quick
override for the window length, while polyorder, minimum window samples,
edge mode, and source-gap masking stay explicit in the profile.

If `trajectory.launch_site.latitude_deg`, `longitude_deg`, and
`azimuth_deg` are all present, downrange is projected along a WGS84
geodesic from the launch site. If any of the three fields is missing or
empty, reconstruction still produces scalar downrange using the flat
fallback and leaves latitude/longitude empty.

## OCR performance

Measured on `BlueOrigin_NG-3.mp4` (1080p / 887 s / 443 samples at the
default 0.5 fps cadence) on an Apple M1 Pro:

| Configuration | Phase A wall time | Speedup vs baseline |
|---------------|------------------:|--------------------:|
| `--ocr-backend rapidocr` (no skip, workers=1) is the *baseline* | 1182.0 s | 1.0× |
| `--ocr-backend vision` (auto on macOS) | 87.7 s | **13.5×** |
| `--ocr-backend vision --ocr-skip-detection` | 109.2 s | 10.8× |
| `--ocr-backend rapidocr --ocr-skip-detection` | 75.8 s | 15.6× |
| `--ocr-backend rapidocr --ocr-skip-detection --ocr-workers auto` | 72.4 s | **16.3×** |

A few takeaways from those numbers:

- The portable RapidOCR path with `--ocr-skip-detection` is the fastest
  configuration. Skip-detection collapses the 5 fields into a single
  batched recognition call per frame, which beats Vision's per-crop
  detection-internal pipeline on this hardware.
- Vision wins when detection is *not* skipped: a single ANE call across
  the full strip is dramatically faster than RapidOCR's CPU detection
  pass.
- Adding workers to the RapidOCR rec-only path gives a marginal win
  (~5%) on this video because each frame is already so cheap that
  worker overhead dominates. The flag is more impactful when the
  per-frame OCR work is heavier (full detection, longer videos).

Functional parity vs the baseline `telemetry_clean.csv`: `mission_elapsed_time_s`
matches within 1 sample on 100% of overlapping rows for every config.
Velocity/altitude columns match within 1% on 96–100% of overlapping rows;
the few outliers come from individual frames whose strip OCR was
ambiguous and where the new path's parsing chose a different valid
candidate. The skip-detection path is more aggressive on Stage 2, e.g. it
recovered ~7x more parseable rows than the baseline before the stage 2
activation gate trips in the NG-3 flight test case.

## Overlay performance

Same 1080p60 / 887 s / 53,179 frames source. Times measured on the same
M1 Pro:

| Configuration | Wall time | Speedup |
|---|---:|---:|
| `--overlay-engine opencv` (in-process numpy alpha + cv2 encode) is the *baseline* | ~1438 s (extrapolated) | 1.0× |
| `--overlay-engine ffmpeg --overlay-encoder libx264` | 337.9 s | 4.3× |
| `--overlay-engine ffmpeg --overlay-encoder videotoolbox` (auto on Mac) | 287.2 s | **5.0×** |

What's bottlenecking each engine, from the profile run:

- The OpenCV path spends roughly 16 ms per frame in numpy alpha
  compositing (`astype(float32)` × 4 large temporaries per frame), 6 ms
  in CPU H.264 encoding, and 5 ms in `cv2.VideoCapture.read()`.
  Compositing alone is more than half the wall time.
- The FFmpeg path moves compositing into ffmpeg's SIMD `overlay`
  filter, offloads the encode to a hardware H.264 encoder
  (VideoToolbox on Apple Silicon, NVENC/QSV/VAAPI elsewhere), and
  collapses the entire pipeline into a single `ffmpeg` invocation.
  Decode and encode become the bottleneck instead of compositing.

The unique overlay panels are also reduced by quantizing reveal times
to a 0.5 s MET grid (controlled by `REVEAL_QUANTIZE_STEP_S` in
`overlay.py`), so the trajectory module's per-step samples don't
balloon the panel cache and the concat playlist.
