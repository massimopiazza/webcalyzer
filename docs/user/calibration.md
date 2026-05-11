# Calibration

Calibration tells webcalyzer where each telemetry value appears in the video frame. The **Calibrate** page scrubs through source frames, splits the video into calibration segments, and lets you draw normalized bounding boxes for each enabled canonical slot in the active segment. Use calibration before a production run whenever a webcast overlay layout changes.

## Calibration Setup

### Anatomy of calibration

| Field | Description |
|---|---|
| **Profile template** | Starting YAML profile. Existing segments, enabled slots, and boxes are loaded into the editor. |
| **Input video** | Video used for frame-accurate calibration and saved as `calibration_video` metadata. |
| **Frame canvas** | Selected source frame with boxes drawn for the active segment. Drag on the image to set the active enabled slot box. |
| **Frame scrubber** | Slider plus previous and next-frame buttons for frame-level placement. |
| **Field slots** | The five canonical slots: `met`, `stage1_velocity`, `stage1_altitude`, `stage2_velocity`, `stage2_altitude`. |
| **Discard changes** | Appears after editing a loaded template's calibration. Restores the loaded calibration until the next save makes the edited calibration the baseline. |
| **Save calibration as template** | Writes the current calibration and the current profile settings to a YAML template. Drafts may be incomplete. |

### Load a starting profile

Open **Calibrate** and choose a **Profile template**. If you are creating a new overlay profile, start from the closest existing template, then use **Save calibration as template** with a new YAML name. Template management is covered in [templates](templates.md).

When you choose an input video, calibration records the reference FPS, frame count, width, and height. Frame indices are authoritative. Timestamps shown in the UI and saved in YAML are derived from the frame index and FPS.

### Scrub frames

Choose **Input video**, then move the scrubber. A click on the scrubber updates the preview to the selected frame. A drag updates the selected frame continuously, samples preview images at a capped cadence, and loads the released frame immediately. If a frame image takes more than half a second to load, the canvas dims and shows the primary loading indicator until the requested frame is ready.

Use the previous and next-frame buttons or the physical left and right arrow keys for exact frame placement. Holding a button or arrow key advances continuously with a capped acceleration profile while the preview image updates at a limited cadence. Releasing the button or key loads the final selected frame immediately. The page shows the current frame, timestamp, active segment, and active segment frame range above the canvas.

### Split segments

Click **Split here** to create a new segment at the current frame. The split frame becomes the first frame of the next segment. New segments start with all five canonical slots enabled, with empty boxes. Use **Crop start** and **Crop end** to define the portion of the source video that should be processed.

Each segment boundary has a small remove-split button below the rail. Removing a split merges the right segment back into the left segment and keeps the left segment's enabled slots and boxes.

## Box Editing

### Draw a bounding box

Select a slot in the **Field slots** panel. All new slots start enabled. Drag across the frame canvas around the printed text for that slot. The box is stored as `[x0, y0, x1, y1]`, where all values are normalized from `0` to `1`. After a box is drawn, the selected slot advances to the next enabled slot.

Field boxes should include the printed digits and unit label when possible. Avoid adjacent labels or values that belong to another field.

Every runnable segment must enable `met` and define a valid `met` box. Other slots are optional; disable slots when that telemetry disappears during a later mission phase.

### Edit slot metadata

The slot names, types, and stages are canonical:

- `met`: mission elapsed time, no stage
- `stage1_velocity`: velocity for stage 1
- `stage1_altitude`: altitude for stage 1
- `stage2_velocity`: velocity for stage 2
- `stage2_altitude`: altitude for stage 2

Use **Advanced settings** on **Run** for numeric inspection of segment ranges and slot bboxes.

### Check boxes across frames

Use the scrubber to inspect frames near each segment boundary. Verify that each active segment's boxes contain the intended telemetry text and disabled slots are truly absent.

Rule of thumb: use the tightest crop that remains stable across all sampled frames. If the overlay moves, make the crop large enough to cover that movement without touching neighboring telemetry.

## Save and Verify

### Save calibration

Click **Save calibration as template**. The dialog starts with the loaded template name when one is available, or lets you enter a new relative YAML path.

Saving writes a full YAML profile. If you loaded an existing template and keep that same name, the edited calibration video, segment ranges, enabled slots, and boxes are saved together with the other settings already in that template. Those other settings are not replaced by defaults unless you changed them in the form.

After a successful save, the saved calibration becomes the new baseline and **Discard changes** disappears until you make another calibration edit.

If you start from a blank/default profile and save a new file, the new template contains the current calibration plus the default settings currently present in the form for parsing, trajectory, overlay, and run-related profile fields.

The saved template can be loaded on **Run** or used directly with the CLI:

```bash
webcalyzer run --video /path/to/video.mp4 --config /path/to/profile.yaml --output /path/to/output-parent
```

For direct edits to segment ranges, bbox values, and parsing settings, use [profile configuration](profile-configuration.md).

### Verify calibration

After saving, run a quick extraction with a low **Sample fps** value in **General**. The run workflow is described in [run extraction](run-extraction.md). Review:

- `review/contact_sheet.jpg` for box placement on sampled frames
- `telemetry_raw.csv` for OCR text and unit parsing
- `telemetry_clean.csv` for retained values by mission elapsed time
- the first summary PDFs under `plots/`

Review JPEGs include the configured field boxes, which makes them the fastest check that the pipeline is reading the intended overlay regions.
Continue with [outputs and review](outputs-and-review.md) when the quick run finishes.
