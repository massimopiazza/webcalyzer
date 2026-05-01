import { Plus, Trash2 } from "lucide-react";
import { Field, Section } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { ProfileFormState } from "@/lib/profileForm";
import { getError } from "@/lib/errors";
import { NumberInput } from "./NumberInput";
import { FIELD_HELP, SECTION_HELP } from "@/lib/explanations";

export function HardcodedPointsSection({ state }: { state: ProfileFormState }) {
  const { profile, patch, setProfile, errors } = state;

  const addPoint = () =>
    setProfile((prev) => ({
      ...prev,
      hardcoded_raw_data_points: [
        ...prev.hardcoded_raw_data_points,
        {
          mission_elapsed_time_s: 0,
          stage1: { velocity_mps: null, altitude_m: null },
          stage2: { velocity_mps: null, altitude_m: null },
        },
      ],
    }));

  const remove = (index: number) =>
    setProfile((prev) => ({
      ...prev,
      hardcoded_raw_data_points: prev.hardcoded_raw_data_points.filter((_, i) => i !== index),
    }));

  return (
    <Section description={SECTION_HELP.hardcoded}>
      <div className="space-y-3">
        {profile.hardcoded_raw_data_points.length === 0 && (
          <div className="rounded-md border border-dashed border-border/70 p-4 text-center text-sm text-muted-foreground">
            None defined.
          </div>
        )}
        {profile.hardcoded_raw_data_points.map((point, index) => (
          <div key={index} className="rounded-md border border-border/70 bg-muted/20 p-3">
            <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
              <Field
                label="MET (s)"
                tooltip={FIELD_HELP.anchor_met_s}
                error={
                  getError(errors, ["hardcoded_raw_data_points", index, "mission_elapsed_time_s"]) ??
                  undefined
                }
              >
                <NumberInput
                  value={point.mission_elapsed_time_s}
                  onChange={(v) =>
                    patch(["hardcoded_raw_data_points", index, "mission_elapsed_time_s"], v ?? 0)
                  }
                />
              </Field>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => remove(index)}
                title="Remove point"
              >
                <Trash2 className="h-4 w-4 text-destructive/80" />
              </Button>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              <Field
                label="Stage 1 velocity (m/s)"
                tooltip={FIELD_HELP.anchor_stage1_velocity_mps}
              >
                <NumberInput
                  value={point.stage1.velocity_mps}
                  allowNull
                  onChange={(v) =>
                    patch(["hardcoded_raw_data_points", index, "stage1", "velocity_mps"], v)
                  }
                />
              </Field>
              <Field
                label="Stage 1 altitude (m)"
                tooltip={FIELD_HELP.anchor_stage1_altitude_m}
              >
                <NumberInput
                  value={point.stage1.altitude_m}
                  allowNull
                  onChange={(v) =>
                    patch(["hardcoded_raw_data_points", index, "stage1", "altitude_m"], v)
                  }
                />
              </Field>
              <Field
                label="Stage 2 velocity (m/s)"
                tooltip={FIELD_HELP.anchor_stage2_velocity_mps}
              >
                <NumberInput
                  value={point.stage2.velocity_mps}
                  allowNull
                  onChange={(v) =>
                    patch(["hardcoded_raw_data_points", index, "stage2", "velocity_mps"], v)
                  }
                />
              </Field>
              <Field
                label="Stage 2 altitude (m)"
                tooltip={FIELD_HELP.anchor_stage2_altitude_m}
              >
                <NumberInput
                  value={point.stage2.altitude_m}
                  allowNull
                  onChange={(v) =>
                    patch(["hardcoded_raw_data_points", index, "stage2", "altitude_m"], v)
                  }
                />
              </Field>
            </div>
          </div>
        ))}
        <Button variant="outline" onClick={addPoint}>
          <Plus className="mr-1 h-4 w-4" /> Add anchor point
        </Button>
      </div>
    </Section>
  );
}
