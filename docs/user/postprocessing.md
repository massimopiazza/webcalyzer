# Postprocessing

Use **Postprocessing** to correct telemetry observations from a compatible
previous run without repeating OCR. Select an output directory containing
`postprocessing_manifest.json`, then choose one telemetry field at a time.
After a web run succeeds, the latest generated output directory is
preselected when you open **Postprocessing**.

## Edit Observations

Drag across the chart to select points. Hold **Shift** to add points and
**Option** or **Alt** to remove points from the selection.

Available actions:

- **Delete** removes selected field observations from the saved raw data.
- **Restore** brings back draft deletions before Save.
- **Edit** changes one selected point's numeric value and unit while keeping
  its OCR text as evidence.
- **Override unit** reinterprets the OCR numeric values of selected points
  using another configured unit.
- **Undo** and **Redo** move through draft operations.

Use the zoom, reset, and pan tools above the chart for close inspection.
Rectangle zoom is a one-shot action and returns to selection mode after the
drag completes. Trackpad scrolling pans a zoomed chart. Draft actions clear
the current point selection without resetting the visible zoom range.

Enable **Show outliers** when you want to review points already rejected by
the configured outlier filter. The toggle is off by default. Rejected points
are red and never affect the chart's default range.

## Save And Regenerate

The editor persists draft operations immediately but does not overwrite raw
telemetry until Save is confirmed. Save retains one rolling raw backup,
materializes the corrections into `telemetry_raw.csv`, reruns filtering,
reconstructs enabled trajectory outputs, and regenerates plots.

Overlay video rendering is separate. The overlay action is available only
when it is enabled in the resolved profile and the original video remains
inside an allowed server root.

If automatic regeneration fails or is cancelled after raw data was written,
the corrected raw file remains in place. Reopen the session and retry
regeneration, or use:

```bash
webcalyzer postprocess-regenerate --output outputs/my-run
```

## Compatibility

Only new `extract` and `run` outputs include a post-processing manifest.
Older output folders remain usable by existing CLI commands but are not
accepted by the visual editor.
