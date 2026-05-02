# Templates

Templates are YAML profiles stored under the server templates directory. The **Templates** page lets you inspect the available profiles, import new YAML, download existing YAML, and remove profiles that are no longer needed. Templates are the bridge between visual web editing and repeatable CLI runs.

## Template Concepts

### Anatomy of a template

| Field | Description |
|---|---|
| **Name** | Relative path under the templates directory, usually ending in `.yaml`. |
| **Profile name** (`profile_name`) | Display name stored inside the YAML profile. |
| **Description** (`description`) | Short note stored inside the profile. |
| **Size and modified time** | Filesystem metadata for the YAML file. |
| **Parse error badge** | Indicates that the file exists but cannot be loaded as a valid profile. |

## Template Actions

### Load a template

Open **Run** or **Calibrate**, then choose **Profile template**. Loading a template copies its values into the form. See [run extraction](run-extraction.md) for run-time use and [calibration](calibration.md) for visual box editing.

The template file is not overwritten just by editing the form. Use **Save as template**, **Save calibration**, or the **Templates** import flow to write YAML.

### Save a template from Run

On **Run**, edit the profile form and click **Save as template**. Choose a relative YAML name such as `blue_origin/my_profile.yaml`.

The server validates the profile before writing it. After the save succeeds, the **Profile template** dropdown refreshes immediately and selects the new template. Field and parsing validation rules are described in [profile configuration](profile-configuration.md).

Note: If validation fails, fix the inline form errors and save again. Server validation is the final authority even when the client form appears valid.

### Import YAML

Open **Templates** and click **Import YAML**. Fill in:

- **Name:** destination filename. If `.yaml` is omitted, the app appends it.
- **YAML:** profile text to import

Click **Import**. The server parses the YAML and confirms that it can load as a webcalyzer profile before keeping the file.

Note: The import flow writes only under the configured templates directory. It rejects absolute paths and parent directory traversal.

### Download YAML

Click **YAML** next to a template. The browser downloads the current file contents from the server.

Use this when you want to compare a saved profile with **Preview YAML** on the **Run** page or keep a copy outside the templates directory.

### Delete a template

Click the delete button next to a template and confirm the prompt. The YAML file is removed from the templates directory.

Note: Deleting a template does not delete previous run outputs. Output directories contain their own `config_resolved.yaml` snapshot.

### Handle parse errors

A template with a **parse error** badge is still listed, but it cannot be loaded into the form. Download the YAML, fix the profile structure, then re-import it or edit the file outside the app.

Common causes are:

- missing `fields`
- invalid bounding boxes
- a `met` field with a stage
- a velocity or altitude field without a stage
- a parsing unit reference that does not exist in `units`
- a timestamp regex that does not compile

The same constraints are visible inline on **Run** under [profile configuration](profile-configuration.md).

## Verification

### Verify template changes

After saving or importing a template:

- reload the template from **Run**
- open **Preview YAML** and confirm the expected keys are present
- run a short extraction into a new output directory
- compare the output `config_resolved.yaml` with the saved template when diagnosing defaults or overrides
