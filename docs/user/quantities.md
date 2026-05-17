# Quantities

Quantities define reusable telemetry measurements that can be enabled as custom calibration slots. Use the **Quantities** page when a webcast prints a value beyond the built-in mission time, stage velocity, and stage altitude slots.

## Quantity Library

### Anatomy of a quantity

| Field | Description |
|---|---|
| **Name** | Human label shown in the library, calibration picker, anchors, CSV columns, and plots. |
| **ID** | Stable library identifier. New custom quantities receive a generated `q_...` ID. |
| **Slug** | Field-name suffix. A custom quantity with slug `acceleration` becomes `custom_acceleration`. |
| **Dimensionality** | Physical dimension expression such as `L/T^2`, `M/L^3`, `ANG/T`, `BIT/T`, or `1`. |
| **Display unit** | Pint unit expression used as the normalized output unit. |
| **Description** | Optional note for the library row. |
| **Unit aliases** | Optional OCR text to unit expression mappings, one `ALIAS=UNIT` per line. |

The library is stored as `custom_quantities.yaml` inside the server templates directory. It is separate from profile templates, but profiles embed snapshots of quantities that are enabled in calibration.

### Default quantities

The library is seeded with default quantities for mission time and the four stage velocity and altitude slots. These defaults can be edited so aliases and display units fit local OCR needs, but they cannot be deleted from the web UI or CLI.

Default quantities map to the canonical fields:

| Quantity ID | Field |
|---|---|
| `q_time` | `met` |
| `q_stage1_velocity` | `stage1_velocity` |
| `q_stage1_altitude` | `stage1_altitude` |
| `q_stage2_velocity` | `stage2_velocity` |
| `q_stage2_altitude` | `stage2_altitude` |

## Manage Quantities

### Create or edit a quantity

Open **Quantities**, then click **New quantity** or open an existing row.

Fill in:

- **Name:** readable label, for example `Acceleration`
- **Dimensionality:** physical dimension, for example `L/T^2`
- **Display unit:** compatible Pint unit, for example `m/s^2`
- **Description:** optional library note
- **Unit aliases:** optional OCR mappings such as `G=standard_gravity`

Click **SI** when you want webcalyzer to fill the typical display unit for the current dimensionality. The form normalizes dimensionality expressions before saving.

### Use dimensionality expressions

Dimensionality expressions use base symbols:

| Symbol | Meaning |
|---|---|
| `L` | length |
| `M` | mass |
| `T` | time |
| `TEMP` | temperature |
| `ANG` | plane angle |
| `BIT` | information |
| `COUNT` | count |

You can combine bases with `*`, `/`, parentheses, and powers. Fractional powers are accepted with syntax such as `L^(1/2)`.

Examples:

| Quantity | Dimensionality | Display unit |
|---|---|---|
| Acceleration | `L/T^2` | `m/s^2` |
| Dynamic pressure | `M/(L*T^2)` | `N/m^2` |
| Angular rate | `ANG/T` | `rad/s` |
| Packet rate | `COUNT/T` | `count/s` |

The display unit and every alias target must be compatible with the normalized dimensionality. Invalid Pint units or incompatible units are rejected before the library is saved.

### Add unit aliases

Aliases teach the parser how to interpret OCR text that follows a number.

Use one entry per line:

```text
G=standard_gravity
GEES=standard_gravity
PCT=percent
```

For custom quantities, values are normalized to the quantity's display unit. If OCR sees an explicit alias, webcalyzer converts from the alias target. If OCR omits the unit, webcalyzer uses recent explicit context or the display unit so the output stream remains continuous.

### Delete a quantity

Open the delete button on a custom quantity. The confirmation dialog lists template usage when it can be found.

Deleting a custom quantity removes it from:

- the library
- embedded profile snapshots
- custom calibration fields that reference it
- custom anchor values that reference the removed field

Default quantities cannot be deleted.

## Calibration Use

### Enable a custom quantity

Open **Calibrate**, choose an input video, then click **Add quantity**. The dialog searches by name, dimensionality, display unit, and field name.

Selecting a quantity enables it across every segment and embeds a snapshot in the current profile. Draw a bounding box for the new custom slot just like the canonical slots. The generated field name is `custom_<slug>`, and the slot uses `kind: custom`, `stage: null`, and the quantity ID.

### Remove a custom slot

In the calibration slot panel, custom quantities can be removed from the current segment or from all segments. Removing a custom slot from a segment disables OCR for that measurement in that segment. Removing it from all segments leaves the library quantity intact.

### Use custom anchor points

Once a custom quantity is enabled in at least one segment, **Anchor points** shows an input for that quantity. Anchor values are written in the quantity's display unit and saved under `custom_values` with the custom field name.

For example:

```yaml
hardcoded_raw_data_points:
  - mission_elapsed_time_s: 15.0
    custom_values:
      custom_acceleration: 0.0
```

Custom anchor points are valid only for custom fields enabled in at least one segment.

## Verification

### Verify quantity changes

After editing the library:

- reload **Quantities** and confirm the row appears with the expected dimensionality and display unit
- add the quantity from **Calibrate** and confirm the new slot appears in every segment
- save the profile and confirm `custom_telemetry_quantities` appears in **Preview YAML**
- run a short extraction and inspect the custom field columns in `telemetry_raw.csv` and `telemetry_clean.csv`
- open `plots/filtered/custom_telemetry.pdf` when custom telemetry is present
