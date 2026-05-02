# Profile Configuration

A profile describes how webcalyzer should read one family of webcast overlays. It controls sampling, field boxes, parsing rules, trusted anchor points, trajectory reconstruction, and overlay rendering. The YAML file is the same configuration surface shown in the web UI.

## Profile Structure

### Anatomy of a profile

| Field | Description |
|---|---|
| **Profile name** (`profile_name`) | Identifier shown in the UI and stored in run metadata. It may contain letters, digits, dot, underscore, hyphen, and space. |
| **Description** (`description`) | Human-readable note about the mission, vehicle, source video, or overlay family. |
| **Default sample fps** (`default_sample_fps`) | Default OCR cadence in frames per second. Higher values improve temporal resolution and increase runtime. |
| **Fixture frame count** (`fixture_frame_count`) | Number of frames sampled for calibration and review. |
| **Fixture time range** (`fixture_time_range_s`) | Optional `[start, end]` source-video window used when selecting fixture frames. |
| **Video overlay** (`video_overlay`) | Controls whether the output video is rendered and how large the embedded telemetry plot is. |
| **Trajectory** (`trajectory`) | Controls interpolation, integration, smoothing, acceleration, and launch-site downrange behavior. See [trajectory reconstruction](trajectory-reconstruction.md). |
| **Parsing** (`parsing`) | Optional custom OCR unit aliases, unit conversions, MET regex patterns, and OCR vocabulary. See [trajectory reconstruction](trajectory-reconstruction.md#convert-ocr-readings-into-physical-units). |
| **Anchor points** (`hardcoded_raw_data_points`) | Trusted values inserted at specific mission elapsed times before clean reconstruction. |
| **Fields** (`fields`) | Mapping of telemetry box names to type, stage, and normalized bounding box. |

### Edit general settings

Open **Run** and edit **General**.

Fill in:

- **Profile name:** stable identifier for this overlay family
- **Description:** short reminder of the mission or broadcast format
- **Default sample fps:** normal OCR cadence for production runs
- **Fixture frame count:** number of calibration and review frames to sample
- **Fixture time range start (s)** and **Fixture time range end (s):** optional source-video window for fixture frame selection

Rule of thumb: use a low `default_sample_fps` for early experiments, then raise it when boxes and parsing rules are stable.

## Telemetry Fields and Parsing

### Configure fields

Open **Advanced settings** and edit **Fields** when you need direct control over calibrated boxes.

Each field has:

- **Name:** YAML mapping key, such as `stage1_velocity`, `stage1_altitude`, or `met`
- **Type:** `velocity`, `altitude`, or `met`
- **Stage:** `stage1`, `stage2`, or `(none)`
- **x0, y0, x1, y1:** normalized box coordinates in `[0, 1]`

A valid bounding box must satisfy `x1 > x0` and `y1 > y0`.

Note: The web UI labels this value as **Type** throughout the advanced settings.

### Customize parsing

Open **Advanced settings**, then **Parsing**, and turn on **Customize parsing**. When this switch is off, webcalyzer uses bundled defaults for velocity, altitude, mission elapsed time, and OCR custom words.

For velocity and altitude parsing, configure:

- **Default unit:** unit used when no explicit unit is found
- **Ambiguous default unit:** fallback unit for ambiguous OCR cases
- **Inferred with separator:** units considered when a numeric token contains a separator
- **Inferred without separator:** units considered when a numeric token has no separator
- **Unit aliases:** accepted OCR tokens and SI conversion factors

Each parsed numeric value is converted to SI units before filtering:

$$
x_{\mathrm{SI}} = x_{\mathrm{raw}} \cdot c_{\mathrm{unit}}
$$

The conversion factor $c_{\mathrm{unit}}$ comes from the selected unit definition. For velocity, the SI target is meters per second. For altitude, the SI target is meters.

For mission elapsed time parsing, configure one or more regex patterns. Patterns must compile as regular expressions and should capture the time-like text printed by the overlay.

Note: `default_unit`, `ambiguous_default_unit`, and inferred units must refer to unit names declared in the same parsing block.

### Add anchor points

Use **Anchor points** when a value is known independently of OCR. Click **Add anchor point** and fill in:

- **MET (s):** mission elapsed time for the anchor
- **Stage 1 velocity (m/s)** or **Stage 1 altitude (m):** trusted stage 1 values
- **Stage 2 velocity (m/s)** or **Stage 2 altitude (m):** trusted stage 2 values

At least one telemetry value is required for each anchor point. Anchor points are written into the raw data and then participate in clean rebuild, outlier handling, plotting, and trajectory reconstruction.

## Trajectory and Overlay

### Configure trajectory reconstruction

Use **Trajectory** to control dense reconstruction from retained OCR points.

For the physical meaning of these controls, read [trajectory reconstruction](trajectory-reconstruction.md) before comparing trajectory outputs.

| Field | Description |
|---|---|
| **Reconstruct trajectory** | Enables `trajectory.csv` and trajectory-aware plots. |
| **Interpolation method** | Estimates values between retained telemetry samples. Options are `linear`, `pchip`, `akima`, and `cubic`. |
| **Integration method** | Integrates velocity into total distance. Options are `euler`, `midpoint`, `trapezoid`, `rk4`, and `simpson`. |
| **Outlier preconditioning** | Removes isolated points before interpolation when enabled. |
| **Coarse step smoothing** | Smooths obvious quantization steps in coarse telemetry values. |
| **Coarse-step max gap (s)** | Maximum time gap considered by coarse-step smoothing. |
| **Coarse altitude threshold (m)** | Minimum altitude jump treated as a coarse-step candidate. |
| **Coarse velocity threshold (m/s)** | Minimum velocity jump treated as a coarse-step candidate. |
| **Acceleration source gap (s)** | Marks acceleration output as unavailable across gaps larger than this threshold. |
| **Derivative smoothing window (s)** | Time window for smoothing velocity before acceleration derivation. |
| **Derivative polyorder** | Polynomial order used by Savitzky-Golay smoothing. |
| **Derivative min window samples** | Minimum sample count for derivative smoothing. |
| **Smoothing mode** | Edge mode for smoothing: `interp`, `nearest`, `mirror`, `constant`, or `wrap`. |
| **Launch site** | Optional latitude, longitude, and azimuth for WGS84 downrange coordinates. |

The dense trajectory grid uses mission elapsed time as its independent variable. If samples are spaced by $\Delta t$, the grid advances as:

$$
t_{i+1}=t_i+\Delta t
$$

Interpolated velocity $v(t)$ and altitude $h(t)$ are evaluated on that grid. The integration method controls how velocity contributes to total path distance $s(t)$.

Downrange distance removes the vertical altitude change from the total path increment:

$$
\Delta r_i = \sqrt{\max\left(0, \Delta s_i^2-\Delta h_i^2\right)}
$$

This prevents climb from being double-counted as horizontal travel.

Savitzky-Golay smoothing estimates acceleration by fitting a local polynomial around each sample:

$$
a_{\mathrm{smooth}}(t_i)=\frac{d}{dt}p_i(t)\bigg|_{t=t_i}
$$

The smoothing window and polynomial order control how much local structure is preserved before acceleration is reported.

Remark: `simpson` is accepted as an integration choice for compatibility. The implementation keeps the trajectory flow consistent with the supported integration path.

### Configure video overlay output

Use **Video overlay** to control the optional rendered video.

Fill in:

- **Render overlay video:** enables or disables the overlay video
- **Plot mode:** `filtered` includes retained points only, `with_rejected` also shows rejected points
- **Output filename:** bare filename inside the output directory
- **Width fraction:** overlay panel width relative to the source frame
- **Height fraction:** overlay panel height relative to the source frame
- **Include source audio:** attempts to mux original audio into the rendered copy

Note: The output filename must not contain path separators. Choose the output directory separately on **Run**.

## YAML and Verification

### Preview YAML

Click **Preview YAML** on **Run**. The server validates the current form and renders the exact profile shape it would save.

Use this before copying a web-edited profile into CLI workflows or before comparing a saved template with `config_resolved.yaml`.

### Verify profile changes

After changing a profile, run these checks:

- **Preview YAML** succeeds without validation errors
- **Save as template** writes the intended YAML name
- **Profile template** can reload the saved template immediately
- a low-sample run writes `telemetry_raw.csv`, `telemetry_clean.csv`, `run_metadata.json`, and `config_resolved.yaml`
- review frames show boxes around the intended telemetry text
