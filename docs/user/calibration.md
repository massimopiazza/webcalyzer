# Calibration

Calibration tells webcalyzer where each telemetry value appears in the video frame. The **Calibrate** page samples representative frames, displays the selected frame, and lets you draw normalized bounding boxes for every configured field. Use calibration before a production run whenever a webcast overlay layout changes.

## Calibration Setup

### Anatomy of calibration

| Field | Description |
|---|---|
| **Profile template** | Starting YAML profile. Existing fields, types, stages, and boxes are loaded into the editor. |
| **Input video** | Video used to sample fixture frames. |
| **Sample frames** | Action that asks the server for evenly spaced frames based on the profile fixture settings. |
| **Frame canvas** | Selected sampled frame with boxes drawn over the video image. Drag on the image to set the active field box. |
| **Fields** | Editable list of field names, types, stages, and normalized box values. |
| **Save calibration** | Writes the current profile back to the chosen template destination. |

### Load a starting profile

Open **Calibrate** and choose a **Profile template**. If you are creating a new overlay profile, start from the closest existing template, then use **Save as template** with a new YAML name. Template management is covered in [templates](templates.md).

The profile must define at least one field. Add or remove fields in the **Fields** panel before drawing boxes.

### Sample frames

Choose **Input video**, then click **Sample frames**. Webcalyzer selects frames according to:

- **Fixture frame count:** number of review frames to sample
- **Fixture time range start (s):** optional lower bound in source video time
- **Fixture time range end (s):** optional upper bound in source video time

The page shows the current frame number, source video index, timestamp, and video dimensions above the canvas.

## Box Editing

### Draw a bounding box

Select a field in the **Fields** panel. Drag across the frame canvas around the printed text for that field. The box is stored as `[x0, y0, x1, y1]`, where all values are normalized from `0` to `1`.

Field boxes should include the printed digits and unit label when possible. Avoid adjacent labels or values that belong to another field.

Note: A `met` field must have stage `(none)`. Velocity and altitude fields must use `stage1` or `stage2`.

### Edit field metadata

Use the **Fields** panel to set:

- **Name:** identifier written into the YAML mapping, such as `stage1_velocity`, `stage1_altitude`, `met`, `stage2_velocity`, or `stage2_altitude`
- **Type:** `velocity`, `altitude`, or `met`
- **Stage:** `stage1`, `stage2`, or `(none)` for MET only
- **Box values:** exact normalized coordinates for small numeric corrections

Use **Add** to create another field. Use the remove button to delete a field.

### Check boxes across frames

Use the left and right arrow buttons to move through sampled frames. Verify that each box still contains the intended telemetry text as the video progresses.

Rule of thumb: use the tightest crop that remains stable across all sampled frames. If the overlay moves, make the crop large enough to cover that movement without touching neighboring telemetry.

## Save and Verify

### Save calibration

Click **Save as template** to choose a YAML destination if none is loaded. Then click **Save calibration**.

The saved template can be loaded on **Run** or used directly with the CLI:

```bash
webcalyzer run --video /path/to/video.mp4 --config /path/to/profile.yaml --output /path/to/output
```

For direct edits to field type, stage, and parsing settings, use [profile configuration](profile-configuration.md).

### Verify calibration

After saving, run a quick extraction with a low **Sample fps override**. The run workflow is described in [run extraction](run-extraction.md). Review:

- `review/contact_sheet.jpg` for box placement on sampled frames
- `telemetry_raw.csv` for OCR text and unit parsing
- `telemetry_clean.csv` for retained values by mission elapsed time
- the first summary PDFs under `plots/`

Review JPEGs include the configured field boxes, which makes them the fastest check that the pipeline is reading the intended overlay regions.
Continue with [outputs and review](outputs-and-review.md) when the quick run finishes.
