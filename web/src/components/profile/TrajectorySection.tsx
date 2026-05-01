import { useEffect, useRef } from "react";
import { Field, Section } from "@/components/Field";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ProfileFormState } from "@/lib/profileForm";
import { getError } from "@/lib/errors";
import { useMeta } from "@/lib/meta";
import { NumberInput } from "./NumberInput";
import { FIELD_HELP, SELECT_HELP } from "@/lib/explanations";

const SMOOTHING_MODES = ["interp", "nearest", "mirror", "constant", "wrap"] as const;

const DEFAULT_LAUNCH_SITE = {
  latitude_deg: 28.47056,
  longitude_deg: -80.54,
  azimuth_deg: 90.0,
};

export function TrajectorySection({ state }: { state: ProfileFormState }) {
  const meta = useMeta();
  const { profile, patch, setProfile, errors } = state;
  const trajectory = profile.trajectory;
  const launch = trajectory.launch_site;
  const interpMethods = meta?.trajectory.interpolation_methods ?? ["pchip", "linear", "cubic", "akima"];
  const integMethods =
    meta?.trajectory.integration_methods ?? ["rk4", "euler", "midpoint", "trapezoid", "simpson"];

  // Launch site is "enabled" iff at least one of its fields is set. We
  // remember the most recently used values so toggling off-and-on restores
  // them instead of falling back to defaults.
  const launchEnabled =
    launch.latitude_deg !== null ||
    launch.longitude_deg !== null ||
    launch.azimuth_deg !== null;
  const lastLaunchRef = useRef<typeof launch | null>(null);
  useEffect(() => {
    if (launchEnabled) lastLaunchRef.current = launch;
  }, [launch, launchEnabled]);

  const toggleLaunchSite = (enabled: boolean) => {
    if (!enabled) {
      lastLaunchRef.current = launch;
      setProfile((prev) => ({
        ...prev,
        trajectory: {
          ...prev.trajectory,
          launch_site: { latitude_deg: null, longitude_deg: null, azimuth_deg: null },
        },
      }));
      return;
    }
    const restored = lastLaunchRef.current;
    const next =
      restored &&
      (restored.latitude_deg !== null ||
        restored.longitude_deg !== null ||
        restored.azimuth_deg !== null)
        ? restored
        : DEFAULT_LAUNCH_SITE;
    setProfile((prev) => ({
      ...prev,
      trajectory: { ...prev.trajectory, launch_site: next },
    }));
  };

  return (
    <Section description="Interpolation, integration, and smoothing controls.">
      <div className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 p-3">
        <Switch
          checked={trajectory.enabled}
          onCheckedChange={(checked) => patch(["trajectory", "enabled"], checked)}
        />
        <div>
          <div className="text-sm font-medium">Reconstruct trajectory</div>
          <p className="text-xs text-muted-foreground">
            Disabled = skip dense interpolation and integration.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Field
          label="Interpolation method"
          tooltip={FIELD_HELP.trajectory_interpolation_method}
          error={getError(errors, ["trajectory", "interpolation_method"])}
        >
          <Select
            value={trajectory.interpolation_method}
            onValueChange={(v) => patch(["trajectory", "interpolation_method"], v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {interpMethods.map((m) => (
                <SelectItem
                  key={m}
                  value={m}
                  tooltip={SELECT_HELP.trajectory_interpolation_method[m]}
                >
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field
          label="Integration method"
          tooltip={FIELD_HELP.trajectory_integration_method}
          error={getError(errors, ["trajectory", "integration_method"])}
        >
          <Select
            value={trajectory.integration_method}
            onValueChange={(v) => patch(["trajectory", "integration_method"], v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {integMethods.map((m) => (
                <SelectItem
                  key={m}
                  value={m}
                  tooltip={SELECT_HELP.trajectory_integration_method[m]}
                >
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field
          label="Coarse-step max gap (s)"
          tooltip={FIELD_HELP.trajectory_coarse_step_max_gap_s}
          error={getError(errors, ["trajectory", "coarse_step_max_gap_s"])}
        >
          <NumberInput
            value={trajectory.coarse_step_max_gap_s}
            onChange={(v) => patch(["trajectory", "coarse_step_max_gap_s"], v ?? 0)}
          />
        </Field>
        <Field
          label="Coarse altitude threshold (m)"
          tooltip={FIELD_HELP.trajectory_coarse_altitude_threshold_m}
          error={getError(errors, ["trajectory", "coarse_altitude_threshold_m"])}
        >
          <NumberInput
            value={trajectory.coarse_altitude_threshold_m}
            onChange={(v) => patch(["trajectory", "coarse_altitude_threshold_m"], v ?? 0)}
          />
        </Field>
        <Field
          label="Coarse velocity threshold (m/s)"
          tooltip={FIELD_HELP.trajectory_coarse_velocity_threshold_mps}
          error={getError(errors, ["trajectory", "coarse_velocity_threshold_mps"])}
        >
          <NumberInput
            value={trajectory.coarse_velocity_threshold_mps}
            onChange={(v) => patch(["trajectory", "coarse_velocity_threshold_mps"], v ?? 0)}
          />
        </Field>
        <Field
          label="Acceleration source gap (s)"
          tooltip={FIELD_HELP.trajectory_acceleration_source_gap_threshold_s}
          error={getError(errors, ["trajectory", "acceleration_source_gap_threshold_s"])}
        >
          <NumberInput
            value={trajectory.acceleration_source_gap_threshold_s}
            onChange={(v) => patch(["trajectory", "acceleration_source_gap_threshold_s"], v ?? 0)}
          />
        </Field>
        <Field
          label="Derivative smoothing window (s)"
          tooltip={FIELD_HELP.trajectory_derivative_smoothing_window_s}
          error={getError(errors, ["trajectory", "derivative_smoothing_window_s"])}
        >
          <NumberInput
            value={trajectory.derivative_smoothing_window_s}
            onChange={(v) => patch(["trajectory", "derivative_smoothing_window_s"], v ?? 0)}
          />
        </Field>
        <Field
          label="Derivative polyorder"
          tooltip={FIELD_HELP.trajectory_derivative_smoothing_polyorder}
          error={getError(errors, ["trajectory", "derivative_smoothing_polyorder"])}
        >
          <NumberInput
            value={trajectory.derivative_smoothing_polyorder}
            onChange={(v) =>
              patch(["trajectory", "derivative_smoothing_polyorder"], Math.round(v ?? 0))
            }
          />
        </Field>
        <Field
          label="Derivative min window samples"
          tooltip={FIELD_HELP.trajectory_derivative_min_window_samples}
          error={getError(errors, ["trajectory", "derivative_min_window_samples"])}
        >
          <NumberInput
            value={trajectory.derivative_min_window_samples}
            onChange={(v) =>
              patch(["trajectory", "derivative_min_window_samples"], Math.round(v ?? 2))
            }
          />
        </Field>
        <Field
          label="Smoothing mode"
          tooltip={FIELD_HELP.trajectory_derivative_smoothing_mode}
          error={getError(errors, ["trajectory", "derivative_smoothing_mode"])}
        >
          <Select
            value={trajectory.derivative_smoothing_mode}
            onValueChange={(v) => patch(["trajectory", "derivative_smoothing_mode"], v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SMOOTHING_MODES.map((m) => (
                <SelectItem
                  key={m}
                  value={m}
                  tooltip={SELECT_HELP.trajectory_derivative_smoothing_mode[m]}
                >
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      <div className="grid gap-3 md:grid-cols-3 rounded-md border border-border/60 bg-muted/30 p-3">
        <ToggleRow
          label="Outlier preconditioning"
          tooltip={FIELD_HELP.trajectory_outlier_preconditioning}
          checked={trajectory.outlier_preconditioning_enabled}
          onChange={(checked) =>
            patch(["trajectory", "outlier_preconditioning_enabled"], checked)
          }
        />
        <ToggleRow
          label="Coarse step smoothing"
          tooltip={FIELD_HELP.trajectory_coarse_step_smoothing}
          checked={trajectory.coarse_step_smoothing_enabled}
          onChange={(checked) =>
            patch(["trajectory", "coarse_step_smoothing_enabled"], checked)
          }
        />
      </div>

      {/* ── Launch site ─────────────────────────────────────────────────── */}
      <div className="rounded-md border border-border/60 bg-muted/15 p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold">Launch site</h4>
            <p className="text-xs text-muted-foreground/90">
              {launchEnabled
                ? "Downrange distance is computed via WGS84 geodesic from the launch pad along the flight path azimuth."
                : "Disabled - downrange uses a flat-Earth approximation (great-circle effects ignored)."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground/80">
              {launchEnabled ? "On" : "Off"}
            </span>
            <Switch checked={launchEnabled} onCheckedChange={toggleLaunchSite} />
          </div>
        </div>
        <div className="mt-3 grid gap-4 md:grid-cols-3">
          <Field
            label="Latitude (deg)"
            tooltip={FIELD_HELP.launch_site_latitude_deg}
            disabled={!launchEnabled}
            error={getError(errors, ["trajectory", "launch_site", "latitude_deg"])}
          >
            <NumberInput
              value={launch.latitude_deg}
              allowNull
              disabled={!launchEnabled}
              onChange={(v) => patch(["trajectory", "launch_site", "latitude_deg"], v)}
            />
          </Field>
          <Field
            label="Longitude (deg)"
            tooltip={FIELD_HELP.launch_site_longitude_deg}
            disabled={!launchEnabled}
            error={getError(errors, ["trajectory", "launch_site", "longitude_deg"])}
          >
            <NumberInput
              value={launch.longitude_deg}
              allowNull
              disabled={!launchEnabled}
              onChange={(v) => patch(["trajectory", "launch_site", "longitude_deg"], v)}
            />
          </Field>
          <Field
            label="Flight path azimuth (deg)"
            tooltip={FIELD_HELP.launch_site_azimuth_deg}
            disabled={!launchEnabled}
            error={getError(errors, ["trajectory", "launch_site", "azimuth_deg"])}
          >
            <NumberInput
              value={launch.azimuth_deg}
              allowNull
              disabled={!launchEnabled}
              onChange={(v) => patch(["trajectory", "launch_site", "azimuth_deg"], v)}
            />
          </Field>
        </div>
      </div>
    </Section>
  );
}

function ToggleRow({
  label,
  tooltip,
  checked,
  onChange,
}: {
  label: string;
  tooltip?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <Field label={label} tooltip={tooltip}>
      <div className="flex items-center gap-2 pt-1">
        <Switch checked={checked} onCheckedChange={onChange} />
        <span className="text-xs text-muted-foreground">{checked ? "On" : "Off"}</span>
      </div>
    </Field>
  );
}
