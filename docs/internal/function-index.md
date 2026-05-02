# Function Index

This index lists the functions, classes, and frontend exports that most often matter when changing behavior. Private helpers are included when they define important invariants or phase boundaries. Use [file-map.md](file-map.md) for file ownership and [pipeline.md](pipeline.md) for stage order.

## CLI and configuration

| Symbol | Location | Purpose |
|---|---|---|
| `build_parser()` | `src/webcalyzer/cli.py` | Builds the argparse command tree and subcommand flags. |
| `main(argv)` | `src/webcalyzer/cli.py` | Dispatches parsed CLI subcommands to pipeline functions. |
| `_trajectory_config_from_args(...)` | `src/webcalyzer/cli.py` | Applies trajectory CLI overrides to a config copy. |
| `_write_trajectory_for_output(...)` | `src/webcalyzer/cli.py` | Resolves profile and sample fps, then writes trajectory outputs. |
| `_overlay_config_from_args(...)` | `src/webcalyzer/cli.py` | Applies overlay CLI overrides to a config copy. |
| `_resolve_workers(...)` | `src/webcalyzer/cli.py` | Resolves `--ocr-workers`, including automatic worker selection. |
| `_run_serve(...)` | `src/webcalyzer/cli.py` | Creates and runs the FastAPI app for the local UI. |
| `load_profile(path)` | `src/webcalyzer/config.py` | Converts YAML into `ProfileConfig`. |
| `save_profile(profile, path)` | `src/webcalyzer/config.py` | Serializes `ProfileConfig` back to YAML. |
| `default_parsing_profile()` | `src/webcalyzer/config.py` | Returns bundled parser defaults for profiles with no `parsing` block. |

## Data models and schema

| Symbol | Location | Purpose |
|---|---|---|
| `ProfileConfig` | `src/webcalyzer/models.py` | Canonical runtime configuration dataclass. |
| `FieldConfig` | `src/webcalyzer/models.py` | Runtime field definition with `kind`, `stage`, and bbox. |
| `TrajectoryConfig` | `src/webcalyzer/models.py` | Runtime trajectory reconstruction settings. |
| `ParsingProfile` | `src/webcalyzer/models.py` | Runtime parser rules for units, MET, and OCR vocabulary. |
| `ProfileModel` | `src/webcalyzer/web/schema.py` | Pydantic validation model for API profile payloads. |
| `profile_dataclass_to_model(...)` | `src/webcalyzer/web/schema.py` | Converts `ProfileConfig` to `ProfileModel`. |
| `model_to_profile_dataclass(...)` | `src/webcalyzer/web/schema.py` | Converts validated web JSON into `ProfileConfig`. |
| `default_parsing_model()` | `src/webcalyzer/web/schema.py` | Exposes parser defaults to the web UI. |
| `serialize_for_yaml(model)` | `src/webcalyzer/web/schema.py` | Converts a validated `ProfileModel` into YAML-native data. |

## OCR and parsing

| Symbol | Location | Purpose |
|---|---|---|
| `extract_telemetry(...)` | `src/webcalyzer/extract.py` | Main extraction entry point. Writes raw and clean telemetry. |
| `_run_phase_a(...)` | `src/webcalyzer/extract.py` | Runs stateless OCR work serially or across worker processes. |
| `_ocr_frame(...)` | `src/webcalyzer/extract.py` | OCRs one sampled frame. |
| `_ocr_with_detection(...)` | `src/webcalyzer/extract.py` | Runs strip OCR, assigns detections, and uses field fallback. |
| `_ocr_skip_detection(...)` | `src/webcalyzer/extract.py` | Runs OCR directly on calibrated field crops. |
| `_run_phase_b(...)` | `src/webcalyzer/extract.py` | Runs sequential MET, stage, plausibility, and measurement selection logic. |
| `normalize_text(text)` | `src/webcalyzer/sanitize.py` | Normalizes OCR text before parsing. |
| `detect_unit(text, kind, parsing)` | `src/webcalyzer/sanitize.py` | Finds a configured unit alias for a measurement type. |
| `parse_met_candidates(text, parsing)` | `src/webcalyzer/sanitize.py` | Returns possible MET values from OCR text. |
| `parse_measurement_options(...)` | `src/webcalyzer/sanitize.py` | Returns possible parsed telemetry values with unit candidates. |
| `choose_best_measurement(...)` | `src/webcalyzer/sanitize.py` | Selects the most plausible measurement option. |
| `resolve_backend_name(name)` | `src/webcalyzer/ocr_factory.py` | Resolves `auto`, `rapidocr`, or `vision` backend requests. |
| `make_backend(options)` | `src/webcalyzer/ocr_factory.py` | Constructs the selected OCR backend. |

## Postprocessing and trajectory

| Symbol | Location | Purpose |
|---|---|---|
| `apply_hardcoded_raw_data_points(...)` | `src/webcalyzer/raw_points.py` | Injects trusted anchor values into raw telemetry. |
| `rebuild_clean_from_raw(...)` | `src/webcalyzer/postprocess.py` | Rebuilds clean telemetry from raw observations. |
| `apply_mahalanobis_outlier_rejection(...)` | `src/webcalyzer/postprocess.py` | Filters outliers from clean telemetry. |
| `apply_outlier_rejection_in_output_dir(...)` | `src/webcalyzer/postprocess.py` | CLI wrapper that reads, filters, and writes output-dir CSVs. |
| `reconstruct_trajectory(...)` | `src/webcalyzer/trajectory.py` | Builds dense stage trajectory data. |
| `write_trajectory_outputs(...)` | `src/webcalyzer/trajectory.py` | Writes `trajectory.csv` and augments clean telemetry. |
| `infer_sample_fps(clean_df)` | `src/webcalyzer/trajectory.py` | Estimates sample rate from clean MET spacing. |
| `_make_interpolator(...)` | `src/webcalyzer/trajectory.py` | Creates interpolation functions for supported methods. |
| `_integrate_scalar(...)` | `src/webcalyzer/trajectory.py` | Integrates one scalar interval with the selected method. |
| `_wgs84_direct(...)` | `src/webcalyzer/trajectory.py` | Computes WGS84 direct geodesic coordinates. |
| `acceleration_profile(...)` | `src/webcalyzer/acceleration.py` | Computes smoothed acceleration from trajectory or clean telemetry. |

## Outputs, overlay, and rescue

| Symbol | Location | Purpose |
|---|---|---|
| `generate_review_frames(...)` | `src/webcalyzer/fixtures.py` | Writes annotated review frames and contact sheet. |
| `create_plots(...)` | `src/webcalyzer/plotting.py` | Creates plot output directories and PDFs. |
| `render_telemetry_overlay_video(...)` | `src/webcalyzer/overlay.py` | Main overlay rendering entry point. |
| `_resolve_overlay_engine(engine)` | `src/webcalyzer/overlay.py` | Resolves `auto`, `ffmpeg`, or `opencv`. |
| `_build_overlay_plan(...)` | `src/webcalyzer/overlay.py` | Builds all data needed to draw overlay panels. |
| `_build_panel_cache(...)` | `src/webcalyzer/overlay.py` | Pre-renders unique overlay panels. |
| `_render_via_opencv(...)` | `src/webcalyzer/overlay.py` | In-process OpenCV overlay renderer. |
| `render_with_ffmpeg(...)` | `src/webcalyzer/overlay_ffmpeg.py` | ffmpeg overlay renderer and command runner. |
| `rescue_output_dir(...)` | `src/webcalyzer/rescue.py` | Runs rescue OCR against a previous output directory. |

## Web backend

| Symbol | Location | Purpose |
|---|---|---|
| `ServeConfig` | `src/webcalyzer/web/app.py` | Runtime configuration for roots, templates, dist, and CORS. |
| `create_app(config)` | `src/webcalyzer/web/app.py` | Builds the FastAPI app, routes, middleware, and static serving. |
| `_format_validation_error(...)` | `src/webcalyzer/web/app.py` | Converts Pydantic errors into JSON-safe API details. |
| `_resolve_template_path(...)` | `src/webcalyzer/web/app.py` | Resolves template names inside `templates_dir`. |
| `_ensure_within(...)` | `src/webcalyzer/web/app.py` | Enforces read containment inside configured roots. |
| `_ensure_within_writable(...)` | `src/webcalyzer/web/app.py` | Enforces writable output containment inside configured roots. |
| `safe_resolve(...)` | `src/webcalyzer/web/files.py` | Root-scoped filesystem resolution. |
| `list_directory(...)` | `src/webcalyzer/web/files.py` | Directory listing for the file browser. |
| `JobManager` | `src/webcalyzer/web/jobs.py` | Single-active-job runner, event fan-out, and cancellation state. |
| `JobOptions` | `src/webcalyzer/web/jobs.py` | Run payload resolved by the API before execution. |

## Web frontend

| Symbol | Location | Purpose |
|---|---|---|
| `App` | `web/src/App.tsx` | Defines client routes under `AppShell`. |
| `AppShell` | `web/src/components/AppShell.tsx` | Persistent layout, navigation, and environment badges. |
| `RunPage` | `web/src/pages/RunPage.tsx` | Profile editing, run overrides, template save, and job submission. |
| `CalibratePage` | `web/src/pages/CalibratePage.tsx` | Frame sampling and visual bbox editing. |
| `TemplatesPage` | `web/src/pages/TemplatesPage.tsx` | Template list, import, download, and delete UI. |
| `DocumentationPage` | `web/src/pages/DocumentationPage.tsx` | Markdown documentation reader and local table of contents. |
| `RunPanel` | `web/src/components/RunPanel.tsx` | Run console, EventSource subscription, output links, and view toggle. |
| `TemplatePicker` | `web/src/components/TemplatePicker.tsx` | Template loading and save-as-template support. |
| `Field` | `web/src/components/Field.tsx` | Field label, error, and tooltip behavior. |
| `useProfileForm(...)` | `web/src/lib/profileForm.ts` | Central profile form state and validation wrapper. |
| `profileSchema` | `web/src/lib/schema.ts` | Zod validation mirror for `ProfileModel`. |
| `api` | `web/src/lib/api.ts` | Typed fetch wrapper for backend endpoints. |
| `DOC_GROUPS` | `web/src/lib/docsNav.ts` | Documentation page registry and raw Markdown imports. |
