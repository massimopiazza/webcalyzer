# File Map

This map gives maintainers a fast way to locate behavior. It is a reference snapshot of the repository structure, not a generated API contract. Use [function-index.md](function-index.md) when you need symbol-level entry points and [architecture.md](architecture.md) when you need runtime context.

## Repository root

| Path | Purpose |
|---|---|
| `README.md` | Project overview, install instructions, CLI argument reference, and architecture notes. |
| `AGENTS.md` | Repository-specific instructions for coding agents. |
| `pyproject.toml` | Python package metadata, dependencies, console script, and pytest configuration. |
| `configs/` | Bundled YAML profile templates. |
| `fixtures/` | Sample review frame assets for bundled profiles. |
| `outputs/` | Conventional local run output directory, not required by code. |
| `docs/` | User and internal documentation source. |
| `web/` | Vite React frontend project. |
| `tests/` | Pytest suite for CLI, configuration, OCR backend selection, video helpers, plotting, overlay, fixtures, jobs, and processing. |

## `src/webcalyzer/`

| File | Purpose |
|---|---|
| `__init__.py` | Package version export. |
| `__main__.py` | Allows `python -m webcalyzer` to call the CLI. |
| `acceleration.py` | Velocity smoothing, derivative calculation, acceleration profiles, and source-gap masking. |
| `calibration.py` | OpenCV desktop calibration UI for drawing field bounding boxes. |
| `cli.py` | Argparse setup and subcommand orchestration. |
| `config.py` | YAML load/save, parser defaults, profile compatibility aliases, and flow-style list serialization. |
| `extract.py` | Main OCR extraction pipeline, including Phase A workers and Phase B sequential state logic. |
| `fixtures.py` | Review frame annotation and contact sheet generation. |
| `models.py` | Runtime dataclasses for profiles, fields, observations, metadata, and extraction rows. |
| `ocr.py` | OCR backend protocol, RapidOCR backend, preprocessing variants, and rescue OCR helpers. |
| `ocr_factory.py` | OCR backend option dataclass, backend resolution, and backend construction. |
| `overlay.py` | Overlay planning, panel drawing, OpenCV rendering, audio muxing, and preview GIF helpers. |
| `overlay_ffmpeg.py` | ffmpeg overlay renderer, progress parsing, encoder detection, and command construction. |
| `plotting.py` | Matplotlib PDF generation for summaries, stage plots, coverage, downrange, and acceleration. |
| `postprocess.py` | Raw-to-clean rebuild, Mahalanobis outlier rejection, rejected file writing, and profile loading from output dirs. |
| `raw_points.py` | Hardcoded raw data point injection and raw dataframe normalization. |
| `rescue.py` | Multi-variant re-OCR for failed raw samples and output-directory rescue workflow. |
| `sanitize.py` | OCR text normalization, MET parsing, unit detection, numeric parsing, and best-measurement selection. |
| `trajectory.py` | Trajectory interpolation, integration, coarse-step smoothing, WGS84 direct geodesic, and CSV output. |
| `video.py` | OpenCV video metadata, sample indices, frame reads, crops, drawing, writing, and contact sheets. |
| `vision_backend.py` | Apple Vision OCR backend and coordinate conversion helpers. |

## `src/webcalyzer/web/`

| File | Purpose |
|---|---|
| `__init__.py` | Web package marker. |
| `app.py` | FastAPI app factory, API endpoints, validation formatting, static frontend serving, and path guards. |
| `files.py` | Browse root model, safe path resolution, root containment checks, and directory listings. |
| `jobs.py` | In-memory single-active-job runner, event records, stdout and stderr capture, and SSE fan-out. |
| `schema.py` | Pydantic profile schema, dataclass converters, default parsing model, and YAML serialization bridge. |

## `web/`

| File | Purpose |
|---|---|
| `index.html` | Vite HTML entry. |
| `package.json` | Frontend dependencies and scripts. |
| `package-lock.json` | Locked frontend dependency graph. |
| `postcss.config.js` | PostCSS configuration for Tailwind. |
| `tailwind.config.ts` | Tailwind theme tokens, content globs, and plugin configuration. |
| `tsconfig.json` | TypeScript compiler options. |
| `vite.config.ts` | Vite React plugin, alias, dev proxy, and build options. |

## `web/src/`

| File | Purpose |
|---|---|
| `main.tsx` | React entry point and root render. |
| `App.tsx` | Route table under `AppShell`. |
| `index.css` | Tailwind layers, dark theme CSS variables, scrollbar styling, and docs prose styles. |
| `vite-env.d.ts` | Vite client type declarations, including raw Markdown imports. |

## `web/src/pages/`

| File | Route | Purpose |
|---|---|---|
| `RunPage.tsx` | `/` | Profile editing, input/output selection, run overrides, YAML preview, job submission, and validation summary. |
| `CalibratePage.tsx` | `/calibrate` | Fixture sampling, frame display, field boxes, and calibration save workflow. |
| `TemplatesPage.tsx` | `/templates` | Template inventory, import, download, delete, and parse-error reporting. |
| `DocumentationPage.tsx` | `/documentation` | Markdown documentation reader with page groups, local table of contents, and math styling. |

## `web/src/components/`

| Path | Purpose |
|---|---|
| `AppShell.tsx` | Global app shell, sidebar, mobile navigation, and layout constraints. |
| `RunPanel.tsx` | Run console, EventSource subscription, output links, cancellation, and dialog/docked modes. |
| `TemplatePicker.tsx` | Template dropdown loading, template save dialog, and refresh handling. |
| `PathPicker.tsx` | Path input plus file browser dialog integration. |
| `FileBrowserDialog.tsx` | Root-scoped file browser UI. |
| `Field.tsx` | Shared field label, error, and tooltip behavior. |
| `PageHeader.tsx` | Page title, description, badges, and action area. |
| `profile/*Section.tsx` | Profile editor sections. |
| `ui/*` | shadcn-style primitives used across the app. |

## `web/src/lib/`

| File | Purpose |
|---|---|
| `api.ts` | Fetch wrapper, DTO types, job file URLs, and API errors. |
| `schema.ts` | Zod profile schema, empty profile defaults, and frontend validation. |
| `profileForm.ts` | Shared profile form state hook and nested path patching. |
| `docsNav.ts` | Documentation Markdown imports and group/page registry. |
| `explanations.ts` | Tooltip and select help copy. |
| `errors.ts` | Error formatting helpers. |
| `meta.ts` | Metadata loading helpers. |
| `utils.ts` | Shared utility functions including `cn(...)`. |
