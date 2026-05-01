# AGENTS.md - webcalyzer specification for coding agents

This file is the canonical reference for AI coding agents working on this
repository. **Read it in full before making non-trivial changes.** It
defines how the two configuration surfaces (YAML and web UI) stay in sync,
what the CLI must keep doing, and which invariants are non-negotiable.

If you change anything that touches configuration shape, update **every
layer in §3 in the same change**. A diff that adds a YAML field but
forgets the Pydantic / Zod / form layer is incomplete.

---

## 1. What this software does

webcalyzer extracts numeric telemetry (velocity, altitude, mission elapsed
time) from launch webcast videos by:

1. Sampling frames at a configured cadence.
2. OCR-ing the on-screen telemetry overlay (Apple Vision on macOS,
   RapidOCR otherwise).
3. Parsing/sanitizing the OCR text into SI units.
4. Filtering and reconstructing a dense trajectory (interpolation +
   numerical integration).
5. Producing CSVs, PDF plots, and a synchronized telemetry overlay video.

The pipeline is configured by a YAML profile. The profile is the **single
source of truth** for "what should this run do." Both the CLI and the web
UI consume / produce this exact same YAML shape.

## 2. High-level architecture

```
src/webcalyzer/
  cli.py                # argparse subcommands incl. `serve`
  models.py             # ProfileConfig + nested @dataclasses (canonical types)
  config.py             # YAML <-> ProfileConfig (load_profile / save_profile)
  extract.py            # OCR + parse pipeline (Phase A + Phase B)
  trajectory.py         # interpolation + integration (write_trajectory_outputs)
  plotting.py           # matplotlib PDF generation (create_plots)
  overlay.py            # video compositing (render_telemetry_overlay_video)
  fixtures.py           # generate_review_frames
  calibration.py        # OpenCV interactive bbox editor (CLI)
  ocr.py / vision_backend.py / ocr_factory.py
  postprocess.py        # outlier rejection / clean rebuild
  rescue.py             # multi-variant re-OCR
  acceleration.py       # Savitzky-Golay derivatives
  raw_points.py         # injection of hardcoded anchor points
  video.py              # OpenCV/AVFoundation wrappers
  web/                  # web UI backend (FastAPI). Optional surface.
    app.py              # FastAPI factory + endpoints
    schema.py           # Pydantic v2 mirror of ProfileConfig
    files.py            # server-side file browser (root-scoped)
    jobs.py             # in-memory job runner + SSE event fan-out

web/                    # web UI frontend (Vite + React + TS + Tailwind + shadcn)
  src/
    App.tsx, main.tsx, index.css
    pages/{RunPage,CalibratePage,TemplatesPage,DocumentationPage}.tsx
    components/profile/*           # one component per ProfileConfig section
    components/{AppShell,RunPanel,FileBrowserDialog,PathPicker,
                TemplatePicker,Field,Toaster}.tsx
    components/ui/*                # shadcn-style primitives
    lib/{api.ts,schema.ts,profileForm.ts,errors.ts,meta.ts,utils.ts}
  dist/                            # built bundle, served by FastAPI

configs/                # YAML profile templates (default --templates-dir)
outputs/                # convention: per-run output directory
```

The runtime stays a single Python package. The web UI is bundled to static
files (`web/dist/`) at build time and **served by the same FastAPI
process** - no Node runtime needed at execution.

## 3. The four-layer configuration model

Any field a user can set lives in **all four** of these layers. When you
add, remove, rename, or change the type of a field, update them in the
order below and verify the round-trip.

| Layer | File | Role |
|-------|------|------|
| **L1 · Dataclass** | `src/webcalyzer/models.py` | Canonical Python type. Everything in the pipeline reads this. |
| **L2 · YAML I/O**  | `src/webcalyzer/config.py` (`load_profile` / `save_profile` / `default_parsing_profile`) | YAML mapping ↔ L1. Defines defaults for missing keys, accepts legacy aliases, decides flow vs. block style for round-trip cleanliness. |
| **L3 · Pydantic schema** | `src/webcalyzer/web/schema.py` (`ProfileModel` + nested `*Model` + `*_to_model` / `model_to_*_dataclass` converters) | Authoritative server-side validation. Mirrors L1 1:1. The API layer uses `ProfileModel.model_validate(...)` on every write/run/validate endpoint. |
| **L4 · Zod schema + form** | `web/src/lib/schema.ts` (`profileSchema`, `emptyProfile`) and `web/src/components/profile/*Section.tsx` | Client-side validation (inline errors) and the form UI. The UI **must** allow the user to edit every L1 field (per the user's product requirement). |

A typed DTO mirror (`web/src/lib/api.ts`) sits alongside L4 - keep it in
sync with L3 so TypeScript callers get the right shapes.

### Round-trip invariants

These must hold for any change to pass:

1. **YAML → L1 → L3 → JSON → L3 → L1 → YAML** is a fixed point for any
   profile that loads cleanly. The conversion functions
   `profile_dataclass_to_model` and `model_to_profile_dataclass` enforce
   this; do not let a field exist in only one direction.
2. **Default round-trip**: `default_parsing_profile()` (L2) and
   `default_parsing_model()` (L3) describe the same defaults. The
   `/api/meta` endpoint surfaces the L3 form so the UI can pre-populate
   the parsing section without duplicating defaults in TypeScript.
3. **Validation is symmetric**: every Pydantic constraint in L3 has a Zod
   counterpart in L4 (numeric ranges, regex compile, bbox ordering, stage
   consistency, default_unit must exist in units, etc.). The server is
   the final authority - the client check exists only for inline UX.
4. The `run` subcommand must consume an identical `ProfileConfig` whether
   it was loaded from YAML or constructed via `model_to_profile_dataclass`
   from the web UI's posted JSON. Do not branch the pipeline by source.

### The full config surface (current as of this writing)

`ProfileConfig` (root):
- `profile_name: str` - identifier (validated `[A-Za-z0-9._\- ]+`).
- `description: str`
- `default_sample_fps: float` (>0, ≤240).
- `fixture_frame_count: int` (≥1, ≤2000).
- `fixture_time_range_s: tuple[float, float] | None` - `[start, end]`,
  `end > start`, both ≥0.
- `video_overlay: VideoOverlayConfig` - `enabled`, `plot_mode`
  (`filtered` | `with_rejected`), `width_fraction` (0.05–1),
  `height_fraction` (0.05–1), `output_filename` (no path separators),
  `include_audio`.
- `trajectory: TrajectoryConfig` - `enabled`, `interpolation_method`
  (`linear|pchip|akima|cubic`), `integration_method`
  (`euler|midpoint|trapezoid|rk4|simpson`),
  `outlier_preconditioning_enabled`, `coarse_step_smoothing_enabled`,
  `coarse_step_max_gap_s` (>0), `coarse_altitude_threshold_m` (≥0),
  `coarse_velocity_threshold_mps` (≥0),
  `acceleration_source_gap_threshold_s` (>0),
  `derivative_smoothing_window_s` (>0),
  `derivative_smoothing_polyorder` (0–10),
  `derivative_min_window_samples` (2–1000),
  `derivative_smoothing_mode`
  (`interp|nearest|mirror|constant|wrap`),
  `launch_site: { latitude_deg, longitude_deg, azimuth_deg }`
  (each optional; ranges enforced).
- `parsing: ParsingProfile | None` - when `None`, the bundled defaults
  from `default_parsing_profile()` are used:
  - `velocity / altitude: FieldKindParsing` - `units: { NAME: { aliases:
    [...], si_factor } }`, `default_unit`, `ambiguous_default_unit`,
    `inferred_units_with_separator`, `inferred_units_without_separator`.
    The default and inferred unit names must reference declared units.
  - `met: { timestamp_patterns: [regex,...] }` - every pattern must
    compile.
  - `custom_words: [str,...]` - auto-derived from aliases when omitted.
- `hardcoded_raw_data_points: list[HardcodedRawDataPoint]` - each has a
  `mission_elapsed_time_s` plus optional `stage1` / `stage2` velocity/
  altitude. At least one telemetry value must be set.
- `fields: dict[name, FieldConfig]` - at least one entry. Each has
  `kind` (`velocity|altitude|met`), `stage` (`stage1|stage2|null` -
  must be `null` iff `kind == "met"`), and `bbox_x1y1x2y2`
  (4-tuple in [0,1] with `x1>x0 && y1>y0`).

The actual constraint values live in the schema files; treat the list
above as a navigation aid and read the code for authoritative bounds.

## 4. CLI contract

`src/webcalyzer/cli.py` is the user-facing CLI. Subcommands today:

- `sample-frames`, `calibrate`, `extract`, `run`, `plot`,
  `rebuild-clean`, `rescue`, `reject-outliers`,
  `reconstruct-trajectory`, `render-overlay`, **`serve`** (web UI).

**Invariant: the existing CLI must keep working unchanged.** `serve` is
purely additive. If you must alter an existing subcommand's behavior,
flag it explicitly in the changelog/README and update the corresponding
section under "Argument reference" + "Subcommands" in `README.md`.

`serve` accepts:

- `--host` (default `127.0.0.1`)
- `--port` (default `8765`)
- `--root <path>` (repeatable; default `[cwd, $HOME]`) - every path the UI
  reads or writes is sandboxed to one of these roots.
- `--templates-dir <path>` (default `<cwd>/configs`)
- `--dist-dir <path>` (default `<repo>/web/dist` if present)
- `--reload` and `--cors-origin <origin>` (dev-only, for the Vite proxy)

When you add a new flag to `extract`/`run`/`render-overlay`, decide
whether it is also exposable through the web UI's "Run overrides" panel
(`web/src/pages/RunPage.tsx`). If it is, expose it in:

1. The `JobOptions` dataclass + `_execute` in `web/jobs.py`.
2. The `/api/jobs/run` payload handler in `web/app.py`.
3. The `runJob` payload type in `web/src/lib/api.ts`.
4. The "Run overrides" form fields in `web/src/pages/RunPage.tsx`.

## 5. Web backend contract

FastAPI app, factory in `src/webcalyzer/web/app.py`. Conventions:

- All endpoints are under `/api/...`. Anything else falls back to the SPA
  shell (`index.html`) so the React router owns client-side navigation.
- Every path the user sends in is run through `safe_resolve` (read) or
  `_ensure_within_writable` (write). **Do not bypass these.** They are
  what makes "this is a local app" defensible.
- The job runner is single-active-job (`JobManager.submit` raises 409 if
  one is already in flight). Long phases should call
  `JobManager._check_cancel(job)` between steps so the UI cancel button
  takes effect at the next phase boundary.
- Logs from the pipeline reach the UI via two channels: stdout/stderr
  redirection (`_StreamingTextIO`) and a logging handler
  (`_StreamingLogHandler`). Pipeline modules should use `print(...)` or
  the standard logging module - both are captured.
- SSE stream at `/api/jobs/{id}/events` is the live channel; each event
  is `{kind, message, payload, timestamp}`. The frontend opens an
  `EventSource` and stops listening on `done | error | cancelled`.
- Validation errors return HTTP 422 with a structured `detail` array
  produced by `_format_validation_error`. Don't return raw Pydantic
  `ValidationError` objects - they contain non-serializable
  `ValueError` instances.

When you add an endpoint:

1. Define it in `app.py`.
2. Add a typed wrapper in `web/src/lib/api.ts`.
3. Wire it into the page that needs it.

## 6. Web frontend contract

Stack: **React 18 + TypeScript + Vite + Tailwind 3 + shadcn-style
components + Zod + sonner toasts + lucide icons**. No external state
management beyond React state - keep it that way unless there is a clear
reason to grow.

Visual language (do not drift):

- Dark-only theme. Background `hsl(228 30% 6%)`, primary cyan
  `hsl(195 95% 56%)`, success/warning/destructive HSL tokens defined in
  `web/src/index.css`. Use Tailwind tokens (`bg-card`, `text-primary`,
  `text-muted-foreground`, etc.); do not hard-code colors.
- Inter for body, JetBrains Mono for code/paths/bbox values.
- `rounded-lg` for cards, `rounded-md` for inputs/buttons. Generous
  padding (`p-5` cards). Subtle shadows (`shadow-sm`).
- Sidebar + content layout via `AppShell.tsx`.

Form rules:

- Every form for `ProfileConfig` is composed of the section components in
  `web/src/components/profile/`. New top-level fields belong in one of
  those sections. New top-level **groups** get a new section component
  added to the `SECTIONS` array in `ProfileForm.tsx`.
- All form state goes through `useProfileForm(initial)` from
  `lib/profileForm.ts`. It owns the profile, derives errors via
  `profileSchema.safeParse`, and exposes `patch(path, value)` for
  immutable nested updates. Do not hold sub-state in section components.
- Validation surfaces inline via `<Field error={...}>` (see
  `components/Field.tsx`). The `Run` button is disabled while
  `state.isValid` is false. The server re-validates and is final.
- File and directory pickers always go through
  `components/PathPicker.tsx` → `components/FileBrowserDialog.tsx`.
  Browser uploads are never used (videos are too large).

Adding a new page:

1. Create `web/src/pages/<Name>Page.tsx`.
2. Add a route under `<AppShell>` in `App.tsx`.
3. Add the entry to `NAV_ITEMS` in `AppShell.tsx`.

## 7. How a config change flows through the layers

Concrete example: adding a new `trajectory.foo_bar_s: float` field.

1. **L1** - add `foo_bar_s: float = 1.0` to `TrajectoryConfig` in
   `models.py`; include it in `to_dict`.
2. **L2** - read it in `_load_trajectory` in `config.py` with a sensible
   default for back-compat when the YAML omits it.
3. **L3** - add `foo_bar_s: float = Field(1.0, gt=0.0)` (or whatever
   bound) to `TrajectoryModel` in `web/schema.py`. Update the
   `TrajectoryConfig(...)` constructor inside `model_to_profile_dataclass`
   and the `TrajectoryModel(...)` call inside `profile_dataclass_to_model`.
4. **L4** - add the field to `trajectorySchema` and the
   `trajectory: { ... }` block of `emptyProfile()` in `lib/schema.ts`;
   add the same field to the DTO in `lib/api.ts`; render an input for it
   in `components/profile/TrajectorySection.tsx` using `<Field>` +
   `<NumberInput>`.
5. **Pipeline** - actually use the value in `trajectory.py` /
   `acceleration.py` / wherever applies.
6. **Docs** - update `README.md` (the "YAML profile" section and any
   tables that enumerate fields), and update the bullet list in §3 of
   this file.
7. **Smoke test** - restart `serve`, hit `GET /api/templates/<existing>`,
   confirm the field comes back with its default; round-trip via
   `PUT /api/templates/<x>` and re-load.

For a removal, do the same in reverse and also strip the field from any
existing template YAMLs in `configs/`.

## 8. Code style and constraints

- Python ≥ 3.11. `from __future__ import annotations` is fine. Prefer
  dataclasses over plain dicts for internal state.
- Keep the `webcalyzer.web.*` package importable without optional GUI
  dependencies - heavy imports (`cv2`, `pandas`, `scipy`,
  `rapidocr_onnxruntime`) should stay inside function bodies when
  practical so module import is cheap.
- TypeScript: `strict: true`. Avoid `any`; prefer narrow shapes from
  `lib/api.ts`. Tailwind class concatenation goes through `cn(...)` from
  `lib/utils.ts`.
- No new frontend state-management library. No CSS-in-JS. No new icon
  library - extend with `lucide-react`.
- Do not use em dashes in code, comments, documentation, or UI copy. Use
  a comma, colon, parentheses, or an ASCII hyphen instead.
- Do not introduce a backend ORM or database. Templates live as YAML
  files; jobs are in-memory.

## 9. Build and run

```bash
# Backend
python3 -m pip install -e .

# Frontend bundle (one-time, repeat after web/ changes)
cd web && npm install && npm run build && cd ..

# Run web UI
webcalyzer serve --root "$PWD" --templates-dir "$PWD/configs"
# → http://127.0.0.1:8765

# Run CLI (unchanged)
webcalyzer run --video <path> --config <yaml> --output <dir> [...flags]
```

Frontend dev loop (hot reload):

```bash
# terminal A
webcalyzer serve --reload --cors-origin http://localhost:5173
# terminal B
cd web && npm run dev
```

## 10. Definition of done for a config-touching change

- [ ] L1 / L2 / L3 / L4 all updated.
- [ ] Pipeline code actually consumes the new value.
- [ ] `npm run build` in `web/` succeeds with no TypeScript errors.
- [ ] `webcalyzer serve` boots; `/api/meta`, `/api/templates`, and
      `/api/templates/<existing>` return without errors.
- [ ] Round-trip on an existing YAML: `GET → PUT → GET` returns equal
      content (modulo defaults the user accepted).
- [ ] `webcalyzer run` with the canonical `configs/blue_origin/new_glenn_ng3.yaml`
      still parses and starts (full execution is too long; argparse +
      `load_profile` + first phase is enough).
- [ ] README updated (YAML section + relevant subcommand tables).
- [ ] This file (AGENTS.md) updated if you changed the layer model,
      added a page, added a CLI subcommand, or added a top-level
      `ProfileConfig` group.

When in doubt: **the YAML profile is the source of truth, the pipeline
must not care which UI produced it, and the user must be able to edit
every field in both surfaces.**
