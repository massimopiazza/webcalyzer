# Getting Started

Webcalyzer runs as a local application. The backend is a Python package with a command-line interface, and the optional web UI is a React bundle served by the same FastAPI process. The app reads videos and writes outputs on your machine, with every browser-selected path restricted to configured local roots.

## Local Setup

### Anatomy of a local setup

| Field | Description |
|---|---|
| **Python package** | Provides the `webcalyzer` command and the extraction pipeline. |
| **Web bundle** | Static React files under `web/dist/`, served by the FastAPI process. |
| **Root** (`--root`) | Directory the web file browser may read from and write to. Pass more than one root when videos and outputs live in different trees. |
| **Templates dir** (`--templates-dir`) | Directory containing YAML profile templates. The default is `<current working directory>/configs`. |
| **Output directory** | Destination chosen for each run. It receives CSVs, plots, metadata, review frames, and optional video overlays. |

### Install webcalyzer

From the repository root, install the Python package in editable mode:

```bash
python3 -m pip install -e .
```

On macOS, webcalyzer can use Apple Vision OCR when the required `pyobjc` Vision bindings are installed. On other platforms, or when Vision is unavailable, it uses RapidOCR.

### Build the web UI

Build the React bundle before using the local UI:

```bash
cd web
npm install
npm run build
cd ..
```

Repeat this step after changes under `web/`. The CLI subcommands do not require the frontend bundle.

### Launch the local UI

Run the server from the repository root:

```bash
webcalyzer serve --root "$PWD" --templates-dir "$PWD/configs"
```

Open <http://127.0.0.1:8765>. The sidebar shows the configured templates directory, the allowed roots, and the app version.

Fill in:

- **Root:** directories the file browser may access
- **Templates dir:** directory containing profile YAML files
- **Host and port:** bind address for the local server, default `127.0.0.1:8765`

Note: The file browser rejects paths outside configured roots. Add another `--root` if a video, template, or output directory is not visible.

## First Run

### Run the included profile

Open **Run**, load `blue_origin/new_glenn_ng3.yaml`, choose an input video, choose an output directory, then click **Run pipeline**. The full run workflow is documented in [run extraction](run-extraction.md).

The run console opens as a focused dialog while the job runs. Use the console control to dock it into the page when you want to keep editing or inspecting the run form behind it.

### Use the development UI

For frontend development with hot reload, run two processes:

```bash
webcalyzer serve --reload --cors-origin http://localhost:5173
cd web
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` calls to the FastAPI server.

## Verification

### Verify the setup

A healthy setup has these visible checks:

- `webcalyzer --help` prints the subcommand list
- `webcalyzer serve --root "$PWD" --templates-dir "$PWD/configs"` starts without import errors
- <http://127.0.0.1:8765/api/meta> returns JSON with roots, templates directory, and parser defaults
- The **Run** page can load an existing template and enable **Run pipeline** after valid paths are selected

Use the web UI when you want visual [calibration](calibration.md), safe local file browsing, inline validation, and live logs. Use the CLI when you want scripted runs, batch processing, or a specific downstream stage such as `rescue`, `reject-outliers`, or `render-overlay`; see [CLI reference](cli-reference.md).
