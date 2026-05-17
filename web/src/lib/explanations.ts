// Centralized help text shown in tooltips throughout the profile editor.
// Keep entries SHORT (≤ 2 short sentences). When you add a new field to the
// profile, add its tooltip here and reference it from the matching section.

export const FIELD_HELP: Record<string, string> = {
  // General
  profile_name:
    "Identifier for this profile. Used as the YAML's profile_name and shown in dashboards. Letters, digits, dot, underscore, dash, and space allowed.",
  description:
    "Free-form notes describing the profile (mission, source feed, who tuned it).",
  default_sample_fps:
    "How many frames per second to sample from the video for OCR. Higher = denser data, slower runs. Typical: 1-4.",
  default_ocr_workers:
    "Parallel OCR worker count saved with this template. 0 = auto: 1 for Vision, max(1, CPUs-1) for RapidOCR.",
  ocr_backend: "Which OCR engine this template uses.",
  ocr_recognition_level:
    "Vision-only. accurate is recommended; fast is lower quality but quicker. Ignored for RapidOCR.",
  skip_full_frame_ocr_fallback:
    "Disable the full-frame OCR recovery pass. Keep it on only when fallback OCR is picking up unrelated values elsewhere in the video.",
  fixture_frame_count:
    "Number of representative frames evenly sampled across the calibration window. Used by Calibrate and the review folder.",
  fixture_time_range_start:
    "Earliest video time (seconds from start) included in fixture sampling. Leave blank to use the whole video.",
  fixture_time_range_end:
    "Latest video time (seconds) included in fixture sampling. Must be greater than the start.",

  // Video overlay
  video_overlay_enabled:
    "Render a copy of the input video with the synchronized telemetry plot composited onto it. When off, only CSVs and PDFs are produced.",
  video_overlay_plot_mode:
    "Which series to draw on the rendered overlay video.",
  video_overlay_engine:
    "Renderer for the overlay video. ffmpeg is faster when available.",
  video_overlay_encoder:
    "ffmpeg H.264 encoder. auto picks the first available supported encoder.",
  video_overlay_width_fraction:
    "Plot width as a fraction of the video width. Range: 0.05-1.0.",
  video_overlay_height_fraction:
    "Plot height as a fraction of the video height. Range: 0.05-1.0.",
  video_overlay_output_filename:
    "Name of the rendered overlay file inside the run output directory. Bare filename only. Path separators are not allowed.",
  video_overlay_include_audio:
    "Mux the source audio track into the rendered overlay video.",

  // Trajectory
  trajectory_enabled:
    "Reconstruct a dense interpolated and integrated trajectory from the OCR samples. When off, only the raw and clean CSVs are produced.",
  trajectory_interpolation_method:
    "Algorithm used to fill the dense grid between OCR samples.",
  trajectory_integration_method:
    "Numerical integration scheme used to derive position from velocity (and velocity from acceleration).",
  trajectory_outlier_rejection:
    "Remove samples whose local Mahalanobis residual is too large before plots and trajectory reconstruction use them.",
  trajectory_outlier_rejection_chi2_threshold:
    "Squared local residual threshold. In 1-D, 9 means 3 sigma because Mahalanobis distance is squared.",
  trajectory_outlier_rejection_window_s:
    "Time window used to fit the local trend around each sample.",
  trajectory_outlier_preconditioning:
    "Run a first pass that removes egregious outliers before interpolation, so a single bad OCR sample doesn't distort the spline.",
  trajectory_coarse_step_smoothing:
    "Smooth the staircase-like jumps that arise when the on-screen telemetry is rounded to a coarse step (e.g. integer km/h).",
  trajectory_coarse_step_max_gap_s:
    "Maximum gap (seconds) treated as a single coarse step for smoothing. Larger jumps in time disable the smoothing locally.",
  trajectory_coarse_altitude_threshold_m:
    "Altitude jump (meters) above which two consecutive samples are treated as a coarse step rather than a real change.",
  trajectory_coarse_velocity_threshold_mps:
    "Velocity jump (m/s) above which two consecutive samples are treated as a coarse step rather than a real change.",
  trajectory_acceleration_source_gap_threshold_s:
    "If velocity samples are spaced wider than this (seconds), fall back to numeric differentiation of position to estimate acceleration.",
  trajectory_derivative_smoothing_window_s:
    "Savitzky-Golay window length (seconds) used to smooth the derivative when computing acceleration.",
  trajectory_derivative_smoothing_polyorder:
    "Polynomial order of the Savitzky-Golay filter. Higher = more wiggle preserved, but more sensitive to noise.",
  trajectory_derivative_min_window_samples:
    "Minimum number of samples required inside the smoothing window. Smaller windows skip the smoothing pass.",
  trajectory_derivative_smoothing_mode:
    "How the convolution handles the boundaries of the data.",

  // Launch site
  launch_site_enabled:
    "Use the launch pad coordinates and flight path azimuth for downrange computation (WGS84 geodesic). When off, downrange uses a flat-Earth approximation.",
  launch_site_latitude_deg:
    "Launch pad latitude in degrees. Range: -90 to +90.",
  launch_site_longitude_deg:
    "Launch pad longitude in degrees. Range: -180 to +180.",
  launch_site_azimuth_deg:
    "Flight path azimuth: nominal heading of the trajectory measured clockwise from True North, in degrees (0 to 360).",

  // Anchor points
  anchor_met_s:
    "Time in seconds (signed) at which this synthetic sample is injected into the raw OCR stream.",
  anchor_stage1_velocity_mps:
    "Hardcoded stage-1 velocity (m/s) injected at this time. Useful for a known anchor (e.g. T+0 = 0 m/s).",
  anchor_stage1_altitude_m:
    "Hardcoded stage-1 altitude (m) injected at this time. Useful for a known anchor (e.g. T+0 = 0 m).",
  anchor_stage2_velocity_mps:
    "Hardcoded stage-2 velocity (m/s) injected at this time.",
  anchor_stage2_altitude_m:
    "Hardcoded stage-2 altitude (m) injected at this time.",

  // Fields
  field_name:
    "Field identifier, used as the column name in CSVs and as the legend label in plots.",
  field_type:
    "What type of measurement this field reports. Velocity / altitude get unit parsing; time is the on-screen clock.",
  field_stage:
    "Which stage owns this field. Time fields must have no stage; velocity/altitude fields must declare one.",
  field_bbox_x0:
    "Left edge of the bounding box, normalized to the video width (0 = left, 1 = right).",
  field_bbox_y0:
    "Top edge of the bounding box, normalized to the video height (0 = top, 1 = bottom).",
  field_bbox_x1:
    "Right edge of the bounding box, normalized. Must be strictly greater than the left edge.",
  field_bbox_y1:
    "Bottom edge of the bounding box, normalized. Must be strictly greater than the top edge.",

  // Parsing (advanced)
  parsing_enabled:
    "Override the bundled OCR vocabulary, unit aliases, and time regex patterns. Leave off to use the project defaults.",
  parsing_default_unit:
    "Unit assumed when the OCR text contains a numeric value but no recognizable unit label.",
  parsing_ambiguous_default_unit:
    "Fallback unit used when the OCR text is ambiguous between multiple units. Optional.",
  parsing_inferred_with_separator:
    "Comma-separated list of candidate units tried when the unit label is missing and the value contains a thousands separator (comma or dot).",
  parsing_inferred_without_separator:
    "Comma-separated list of candidate units tried when the unit label is missing and the value has no thousands separator.",
  parsing_unit_name:
    "Canonical unit name (uppercased). Used as the key referenced by default_unit and the inferred lists.",
  parsing_unit_aliases:
    "Comma-separated alternate spellings the OCR might produce for this unit (e.g. M/S, MPS, MS).",
  parsing_unit_si_factor:
    "Multiply the parsed numeric value by this factor to convert it to SI (meters or meters/second).",
  parsing_met_patterns:
    "Regex pattern matching the on-screen time format. Capture groups (in order): sign, hours, minutes, seconds.",
  parsing_custom_words:
    "Comma-separated tokens fed to the OCR engine as vocabulary hints (Apple Vision custom words). Auto-derived from the alias list when omitted.",

};

// Per-option help shown when hovering items inside dropdown menus.
export const SELECT_HELP: Record<string, Record<string, string>> = {
  trajectory_interpolation_method: {
    linear: "Straight lines between samples. Simplest, no smoothing.",
    pchip: "Piecewise cubic Hermite, shape-preserving, avoids overshoot. Good default.",
    akima: "Akima spline, smooth without ringing on rapid changes.",
    cubic: "Natural cubic spline, smoothest but may overshoot at rapid transitions.",
  },
  trajectory_integration_method: {
    euler: "Forward Euler. First-order, simplest, can drift.",
    midpoint: "Midpoint rule. Second-order accuracy.",
    trapezoid: "Trapezoidal rule. Second-order, robust on noisy data.",
    rk4: "Classical 4th-order Runge-Kutta. Accurate default.",
    simpson: "Simpson's rule. Fourth-order on uniform grids.",
  },
  trajectory_derivative_smoothing_mode: {
    interp: "Pad the boundary by extrapolating the polynomial fit.",
    nearest: "Repeat the nearest edge sample as padding.",
    mirror: "Reflect samples around the edge.",
    constant: "Pad with a constant value.",
    wrap: "Wrap-around (treat the data as periodic).",
  },
  video_overlay_plot_mode: {
    filtered: "Show only telemetry that passed the outlier filter.",
    with_rejected: "Also draw rejected outlier points as a separate series.",
  },
  field_type: {
    velocity: "A speed reading. Parsed via the velocity parsing rules.",
    altitude: "A height reading. Parsed via the altitude parsing rules.",
    met: "Time, the on-screen launch clock. Drives the time axis.",
  },
  field_stage: {
    stage1: "First stage, typically the booster.",
    stage2: "Second stage / upper stage.",
    __none__: "No stage assignment. Only valid for time fields.",
  },
  ocr_backend: {
    auto: "Apple Vision on macOS when available, RapidOCR everywhere else.",
    rapidocr: "Force the cross-platform RapidOCR backend, even on macOS.",
    vision: "Force Apple Vision (macOS only). Errors out elsewhere.",
  },
  ocr_recognition_level: {
    accurate: "Higher-quality Apple Vision recognition. Slower per frame.",
    fast: "Quicker but lower-quality Apple Vision recognition.",
  },
  video_overlay_engine: {
    auto: "Use ffmpeg if it's installed, otherwise fall back to OpenCV.",
    ffmpeg: "Force the ffmpeg pipeline (hardware-accelerated when possible).",
    opencv: "Force the in-process OpenCV pipeline. Slower but no external deps.",
  },
  video_overlay_encoder: {
    auto: "Walk videotoolbox → nvenc → qsv → vaapi → libx264 and pick the first available.",
    videotoolbox: "Apple VideoToolbox. macOS hardware encode.",
    h264_videotoolbox: "Apple VideoToolbox H.264 encoder.",
    nvenc: "NVIDIA NVENC. Requires a recent NVIDIA GPU.",
    h264_nvenc: "NVIDIA NVENC H.264 encoder.",
    qsv: "Intel Quick Sync Video.",
    h264_qsv: "Intel Quick Sync H.264 encoder.",
    vaapi: "Linux VA-API hardware encoder.",
    h264_vaapi: "Linux VA-API H.264 encoder.",
    libx264: "Software x264 encoder. Slowest but ubiquitous.",
  },
};

export const SECTION_HELP: Record<string, string> = {
  general:
    "Identity of this profile and how the video is sampled for OCR / calibration.",
  trajectory:
    "Outlier rejection plus interpolation, integration, and smoothing controls for telemetry outputs.",
  hardcoded:
    "Manually injected raw samples, useful when you have known anchors (e.g. T+0 altitude is 0 m) the OCR can't see.",
  video_overlay:
    "Settings for the synchronized telemetry overlay video.",
  fields:
    "Each field maps a normalized bbox on the video to a measurement type. Use the Calibrate page to draw bboxes visually.",
  parsing:
    "OCR vocabulary, unit aliases, and time regex patterns. Leave disabled to use the bundled defaults.",
};
