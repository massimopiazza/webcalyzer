# Trajectory Reconstruction

Webcalyzer reconstructs trajectory quantities from broadcast telemetry. It does not solve the vehicle equations of motion from thrust, mass, drag, gravity, guidance, or atmosphere. It treats the on-screen velocity, altitude, and mission elapsed time as measured signals, converts them into consistent units, filters obvious OCR failures, and builds a reviewable kinematic trajectory.

## Reconstruction Model

### Anatomy of the reconstruction

| Quantity | Description |
|---|---|
| **Mission elapsed time** (`mission_elapsed_time_s`) | Independent time axis extracted from the video overlay. |
| **Velocity** (`*_velocity_mps`) | Broadcast speed converted to meters per second. Webcalyzer treats this as path speed for distance reconstruction. |
| **Altitude** (`*_altitude_m`) | Broadcast altitude converted to meters. |
| **Path distance** (`s`) | Integrated distance traveled along the reconstructed path. |
| **Downrange distance** (`r`) | Horizontal distance inferred after removing the altitude component from path distance. |
| **Acceleration** (`a`) | Time derivative of velocity after smoothing. |
| **Geodesic position** | Optional latitude and longitude projection from launch site, azimuth, and downrange distance. |

For the configuration controls that enable these outputs, see [profile configuration](profile-configuration.md#configure-trajectory-reconstruction). For the generated files, see [outputs and review](outputs-and-review.md#review-trajectory).

### Convert OCR readings into physical units

OCR returns text, not physical quantities. The parsing stage identifies a numeric value and a unit, then converts the value into SI units:

$$
x_{\mathrm{SI}} = x_{\mathrm{raw}} c_{\mathrm{unit}}
$$

Here $x_{\mathrm{raw}}$ is the parsed number and $c_{\mathrm{unit}}$ is the configured conversion factor. Velocity is stored in meters per second, and altitude is stored in meters.

Remark: The quality of every later trajectory output depends on correct unit identification. If the parser chooses miles instead of feet, or kilometers per hour instead of miles per hour, the reconstructed trajectory will be physically wrong even if OCR read the digits correctly.

### Use mission elapsed time as the clock

Webcalyzer aligns all measurements to mission elapsed time, written as $t$. The OCR sample cadence determines the expected spacing:

$$
\Delta t = \frac{1}{f_{\mathrm{sample}}}
$$

The dense reconstruction grid advances by that spacing:

$$
t_{i+1}=t_i+\Delta t
$$

This keeps velocity, altitude, acceleration, plots, and overlay rendering on the same mission-time axis. Source video time is still used to read frames and synchronize the overlay, but the physical reconstruction is expressed in mission elapsed time.

### Interpret velocity and altitude

The trajectory model uses two broadcast signals:

| Signal | Symbol | Interpretation |
|---|---|---|
| Velocity | $v(t)$ | Vehicle speed along the reconstructed path. |
| Altitude | $h(t)$ | Height above the launch reference used by the webcast. |

The model assumes that the broadcast velocity is close to path speed. Under that assumption, total path distance is the time integral of speed:

$$
s(t)=\int_0^t v(\tau)\,d\tau
$$

If a webcast reports a different velocity definition, such as horizontal speed or inertial speed in another frame, the distance and downrange outputs inherit that assumption. The tool reconstructs from the displayed data; it does not infer the broadcast provider's hidden telemetry definition.

### Handle stage-specific trajectories

Launch webcasts often expose separate Stage 1 and Stage 2 overlays. Webcalyzer reconstructs each configured stage independently where that stage has usable velocity and altitude.

Stage 1 is anchored at liftoff when data is available. Stage 2 starts at the first interval where Stage 2 velocity and altitude are both available. At that handoff, Stage 2 inherits the reconstructed Stage 1 downrange value so the two paths remain connected before they diverge:

$$
r_{\mathrm{stage2}}(t_{\mathrm{start}})=r_{\mathrm{stage1}}(t_{\mathrm{start}})
$$

After that point, each stage uses its own velocity and altitude samples. The paths can bifurcate because the displayed stage telemetry no longer describes the same physical body.

## Signal Conditioning

### Clean raw telemetry

Trajectory reconstruction starts from retained telemetry rows, not from every OCR candidate. Before reconstruction, the pipeline has already parsed units, aligned values to mission elapsed time, applied stage/type consistency checks, injected trusted anchor points, and removed rejected outliers when configured.

The clean table remains the source of truth for observed telemetry. Interpolated values are written only to `trajectory.csv` and to summary overlays. The original stage plots still show gaps in retained telemetry rather than pretending that interpolated samples were directly observed.

### Precondition trajectory inputs

Reconstruction applies additional trajectory-only conditioning before interpolation. This step protects the dense trajectory from isolated values that survived the earlier filters but would force a large interpolated excursion.

For a local linear prediction $\hat{x}_i$ at sample $i$, the residual is:

$$
e_i = x_i-\hat{x}_i
$$

When `outlier_preconditioning_enabled` is active, isolated knots can be removed from the interpolation input if their residual exceeds the configured altitude or velocity threshold. The retained clean telemetry file is not changed by this trajectory-only pass.

### Smooth coarse stepwise telemetry

Some broadcasts update altitude or velocity in coarse plateaus rather than smooth samples. Webcalyzer can convert a short step between two plateaus into a midpoint transition knot for trajectory interpolation:

$$
t_{\mathrm{mid}}=\frac{t_{\mathrm{old}}+t_{\mathrm{new}}}{2}
$$

The midpoint conversion is gap-aware. It is applied only when the time gap between plateaus is no larger than `coarse_step_max_gap_s`, and only when the altitude or velocity jump exceeds the configured coarse-step threshold. Long telemetry outages remain long-gap interpolation problems instead of being collapsed into a false midpoint step.

### Interpolate sparse measurements

OCR samples are sparse and occasionally missing. Webcalyzer interpolates retained values so velocity and altitude can be evaluated on a dense time grid.

| Method | Practical behavior |
|---|---|
| `linear` | Straight line between retained samples. It is stable and easy to inspect. |
| `pchip` | Shape-preserving cubic Hermite interpolation. It reduces overshoot for monotonic trends. |
| `akima` | Local cubic interpolation that can behave well around unevenly spaced samples. |
| `cubic` | Smooth cubic interpolation. It can overshoot when samples are noisy or sparse. |

Rule of thumb: use `pchip` for production trajectory reconstruction unless plots show a reason to prefer a simpler or smoother method. Compare the result in [outputs and review](outputs-and-review.md#review-plots).

## Path Reconstruction

### Integrate velocity into path distance

Once velocity is available on the dense grid, webcalyzer integrates it over time. The simplest interval estimate is Euler integration:

$$
\Delta s_i \approx v_i\Delta t
$$

The trapezoid estimate averages the endpoint velocities:

$$
\Delta s_i \approx \frac{v_i+v_{i+1}}{2}\Delta t
$$

The cumulative path distance is then:

$$
s_{i+1}=s_i+\Delta s_i
$$

The configured integration method controls how each interval estimate is computed. `trapezoid` is easy to interpret, while `rk4` and `simpson` are useful when the interpolated velocity function is smooth enough to justify a higher-order quadrature.

### Separate climb from downrange travel

Altitude change is part of the path traveled, but downrange is the horizontal component. Webcalyzer estimates the horizontal increment by removing the vertical altitude increment:

$$
\Delta r_i=\sqrt{\max\left(0,\Delta s_i^2-\Delta h_i^2\right)}
$$

The cumulative downrange distance is:

$$
r_{i+1}=r_i+\Delta r_i
$$

The `max` term prevents small numerical inconsistencies from producing an imaginary value when $\Delta h_i$ is slightly larger than $\Delta s_i$ after filtering or interpolation.

### Project downrange onto Earth

When launch-site latitude $\phi_0$, longitude $\lambda_0$, and launch azimuth $\alpha_{\mathrm{az}}$ are configured, webcalyzer projects downrange distance onto the WGS84 ellipsoid. Conceptually, each point is computed from:

$$
(\phi_i,\lambda_i)=\mathrm{GeodesicDirect}(\phi_0,\lambda_0,\alpha_{\mathrm{az}},r_i)
$$

This gives approximate latitude and longitude along the configured azimuth. It is useful for map-based review, but it is still based on reconstructed downrange distance rather than an independent navigation solution.

## Acceleration Reconstruction

### Estimate acceleration

Acceleration is the derivative of velocity:

$$
a(t)=\frac{dv(t)}{dt}
$$

Direct derivatives amplify OCR noise, so webcalyzer applies Savitzky-Golay smoothing to source-supported velocity segments. Acceleration is masked across source velocity gaps longer than `acceleration_source_gap_threshold_s`, so long telemetry outages do not create derivative spikes.

### Why Savitzky-Golay is used

If the measured velocity is $y(t)=v(t)+\varepsilon(t)$, with noise $\varepsilon(t)$ of variance $\sigma^2$, a finite-difference derivative has noise variance proportional to:

$$
\frac{\sigma^2}{\Delta t^2}
$$

That means naive differentiation can turn small OCR jitter into large acceleration spikes. A Savitzky-Golay filter reduces that problem by fitting a local polynomial inside a sliding window and differentiating the fitted polynomial rather than the raw sample-to-sample difference.

Inside a window of length $2M+1$ centered on $t_i$, the fitted polynomial is:

$$
\hat{v}(t;t_i)=\sum_{k=0}^{K}c_k(i)(t-t_i)^k
$$

The smoothed velocity at $t_i$ is $c_0(i)$, and the acceleration estimate is the first derivative at the center:

$$
a_{\mathrm{smooth}}(t_i)=\frac{d}{dt}\hat{v}(t;t_i)\bigg|_{t=t_i}=c_1(i)
$$

For uniformly spaced samples, the fitted value and derivative can be evaluated with fixed convolution kernels:

$$
\hat{v}(t_i)=\sum_{j=-M}^{M}h_0[j]y_{i+j}
$$

$$
a_{\mathrm{smooth}}(t_i)=\frac{1}{\Delta t}\sum_{j=-M}^{M}h_1[j]y_{i+j}
$$

The filter exactly preserves polynomial trends up to degree $K$ while reducing high-frequency noise. A longer window reduces jitter but can flatten real acceleration features; a shorter window follows quick events but passes more OCR noise.

### Configure derivative smoothing

The relevant settings live under `trajectory` in the profile:

| Setting | Meaning |
|---|---|
| `derivative_smoothing_window_s` | Window length in seconds. Sizing the window in seconds makes the filter less sensitive to sample FPS. |
| `derivative_smoothing_polyorder` | Polynomial order $K$. Order `3` is a practical default for preserving curved velocity trends without passing excessive noise. |
| `derivative_min_window_samples` | Minimum number of samples required for a smoothing window. |
| `derivative_smoothing_mode` | Edge handling mode passed to the smoothing implementation. |
| `acceleration_source_gap_threshold_s` | Maximum source-data gap over which acceleration remains trusted. |

The CLI `--trajectory-derivative-window-s` flag is a quick override for the window length. Polyorder, minimum samples, edge mode, and source-gap masking stay explicit in the profile so a template remains reproducible.

## Limits and Verification

### Understand uncertainty

The reconstruction is only as strong as the visible telemetry. The main uncertainty sources are:

- OCR digit errors and missing frames
- unit misclassification
- sparse sampling around rapid events
- broadcast rounding or quantization
- interpolation overshoot
- unknown meaning of the provider's displayed velocity
- launch-site azimuth assumptions

Note: Webcalyzer produces a reviewable kinematic reconstruction, not a certified trajectory. Use plots, review frames, and raw CSVs to decide whether a run is physically credible.

### Verify physical plausibility

After a run, inspect these checks:

- `telemetry_clean.csv` has increasing `mission_elapsed_time_s`
- altitude trends match the visible webcast timeline
- velocity and altitude units are consistent with the mission phase
- rejected points explain obvious spikes or OCR failures
- `trajectory.csv` downrange distance is nondecreasing
- acceleration plots do not show isolated spikes that align with OCR errors
- geodesic coordinates move in the configured launch azimuth direction when launch-site data is enabled

When a check fails, start with [calibration](calibration.md), then inspect [profile configuration](profile-configuration.md#customize-parsing), and finally review the generated files in [outputs and review](outputs-and-review.md).
