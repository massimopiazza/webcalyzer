import { Field, Section } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ProfileFormState } from "@/lib/profileForm";
import {
  CANONICAL_FIELD_DEFINITIONS,
  CANONICAL_FIELD_ORDER,
  CanonicalFieldName,
  FieldValue,
} from "@/lib/schema";
import { getError } from "@/lib/errors";
import { NumberInput } from "./NumberInput";

function fieldFor(name: CanonicalFieldName): FieldValue {
  const def = CANONICAL_FIELD_DEFINITIONS[name];
  return {
    kind: def.kind,
    stage: def.stage,
    bbox_x1y1x2y2: null,
  };
}

export function SegmentsSection({ state }: { state: ProfileFormState }) {
  const { profile, patch, setProfile, errors } = state;

  return (
    <Section description="Calibration segments define the active field boxes for frame ranges. End frame is exclusive.">
      <div className="space-y-4">
        {profile.segments.map((segment, segmentIndex) => (
          <div key={segment.id} className="rounded-md border border-border/70 bg-muted/20 p-3">
            <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_1fr_1fr]">
              <Field label="ID" error={getError(errors, ["segments", segmentIndex, "id"])}>
                <Input
                  value={segment.id}
                  onChange={(event) => patch(["segments", segmentIndex, "id"], event.target.value)}
                  className="font-mono text-xs"
                />
              </Field>
              <Field label="Start frame">
                <NumberInput
                  value={segment.start_frame_index}
                  onChange={(value) =>
                    patch(["segments", segmentIndex, "start_frame_index"], Math.max(0, Math.round(value ?? 0)))
                  }
                />
              </Field>
              <Field label="Start seconds">
                <NumberInput
                  value={segment.start_time_s}
                  onChange={(value) => patch(["segments", segmentIndex, "start_time_s"], value ?? 0)}
                />
              </Field>
              <Field label="End frame">
                <NumberInput
                  value={segment.end_frame_index}
                  onChange={(value) =>
                    patch(["segments", segmentIndex, "end_frame_index"], Math.max(0, Math.round(value ?? 0)))
                  }
                />
              </Field>
              <Field label="End seconds">
                <NumberInput
                  value={segment.end_time_s}
                  onChange={(value) => patch(["segments", segmentIndex, "end_time_s"], value ?? 0)}
                />
              </Field>
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-5">
              {CANONICAL_FIELD_ORDER.map((name) => {
                const field = segment.fields[name];
                return (
                  <div key={name} className="rounded-md border border-border/60 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px]">{name}</span>
                      <Switch
                        checked={Boolean(field)}
                        onCheckedChange={(checked) => {
                          setProfile((prev) => {
                            const segments = [...prev.segments];
                            const nextSegment = {
                              ...segments[segmentIndex],
                              fields: { ...segments[segmentIndex].fields },
                            };
                            if (checked) nextSegment.fields[name] = fieldFor(name);
                            else delete nextSegment.fields[name];
                            segments[segmentIndex] = nextSegment;
                            return { ...prev, segments };
                          });
                        }}
                      />
                    </div>
                    <div className="mt-2 font-mono text-[10px] text-muted-foreground">
                      {field?.bbox_x1y1x2y2
                        ? `[${field.bbox_x1y1x2y2.map((value) => value.toFixed(3)).join(", ")}]`
                        : "bbox not set"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}
