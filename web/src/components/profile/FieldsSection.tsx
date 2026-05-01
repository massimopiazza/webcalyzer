import { Plus, Trash2 } from "lucide-react";
import { Field, Section } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ProfileFormState } from "@/lib/profileForm";
import { Profile } from "@/lib/schema";
import { getError } from "@/lib/errors";
import { NumberInput } from "./NumberInput";
import { FIELD_HELP, SECTION_HELP, SELECT_HELP } from "@/lib/explanations";

const KIND_OPTIONS = [
  { value: "velocity", label: "velocity" },
  { value: "altitude", label: "altitude" },
  { value: "met", label: "met (mission elapsed time)" },
] as const;

const STAGE_OPTIONS = [
  { value: "stage1", label: "stage1" },
  { value: "stage2", label: "stage2" },
  { value: "__none__", label: "(none)" },
] as const;

const BBOX_HELP: [string, string][] = [
  ["x0", FIELD_HELP.field_bbox_x0],
  ["y0", FIELD_HELP.field_bbox_y0],
  ["x1", FIELD_HELP.field_bbox_x1],
  ["y1", FIELD_HELP.field_bbox_y1],
];

function defaultName(profile: Profile): string {
  let i = 1;
  while (`field_${i}` in profile.fields) i += 1;
  return `field_${i}`;
}

export function FieldsSection({ state }: { state: ProfileFormState }) {
  const { profile, patch, setProfile, errors } = state;
  const entries = Object.entries(profile.fields);

  const removeField = (name: string) => {
    setProfile((prev) => {
      const next = { ...prev.fields };
      delete next[name];
      return { ...prev, fields: next };
    });
  };

  const renameField = (oldName: string, newName: string) => {
    if (!newName || newName === oldName) return;
    setProfile((prev) => {
      const next: typeof prev.fields = {};
      for (const [k, v] of Object.entries(prev.fields)) {
        next[k === oldName ? newName : k] = v;
      }
      return { ...prev, fields: next };
    });
  };

  const addField = () => {
    setProfile((prev) => ({
      ...prev,
      fields: {
        ...prev.fields,
        [defaultName(prev)]: {
          kind: "velocity",
          stage: "stage1",
          bbox_x1y1x2y2: [0.05, 0.85, 0.2, 0.95],
        },
      },
    }));
  };

  return (
    <Section description={SECTION_HELP.fields}>
      <div className="space-y-3">
        {entries.length === 0 && (
          <div className="rounded-md border border-dashed border-border/70 p-4 text-center text-sm text-muted-foreground">
            No fields defined. Add at least one.
          </div>
        )}
        {entries.map(([name, field]) => {
          const stageValue = field.stage ?? "__none__";
          const fieldErrorPrefix = ["fields", name];
          return (
            <div
              key={name}
              className="rounded-md border border-border/70 bg-muted/20 p-3"
            >
              <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end">
                <Field label="Name" tooltip={FIELD_HELP.field_name}>
                  <Input
                    value={name}
                    onChange={(e) => renameField(name, e.target.value.trim() || name)}
                    spellCheck={false}
                  />
                </Field>
                <Field
                  label="Kind"
                  tooltip={FIELD_HELP.field_kind}
                  error={getError(errors, [...fieldErrorPrefix, "kind"])}
                >
                  <Select
                    value={field.kind}
                    onValueChange={(v) => {
                      patch(["fields", name, "kind"], v);
                      if (v === "met") {
                        patch(["fields", name, "stage"], null);
                      } else if (field.stage === null) {
                        patch(["fields", name, "stage"], "stage1");
                      }
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KIND_OPTIONS.map((o) => (
                        <SelectItem
                          key={o.value}
                          value={o.value}
                          tooltip={SELECT_HELP.field_kind[o.value]}
                        >
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field
                  label="Stage"
                  tooltip={FIELD_HELP.field_stage}
                  error={getError(errors, [...fieldErrorPrefix, "stage"])}
                >
                  <Select
                    value={stageValue}
                    onValueChange={(v) =>
                      patch(["fields", name, "stage"], v === "__none__" ? null : v)
                    }
                    disabled={field.kind === "met"}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STAGE_OPTIONS.map((o) => (
                        <SelectItem
                          key={o.value}
                          value={o.value}
                          tooltip={SELECT_HELP.field_stage[o.value]}
                        >
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeField(name)}
                    title="Remove field"
                  >
                    <Trash2 className="h-4 w-4 text-destructive/80" />
                  </Button>
                </div>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-4">
                {BBOX_HELP.map(([label, tooltip], idx) => (
                  <Field
                    key={label}
                    label={label}
                    tooltip={tooltip}
                    error={getError(errors, [...fieldErrorPrefix, "bbox_x1y1x2y2"]) ?? undefined}
                  >
                    <NumberInput
                      value={field.bbox_x1y1x2y2[idx]}
                      onChange={(v) => {
                        const bbox = [...field.bbox_x1y1x2y2] as [number, number, number, number];
                        bbox[idx] = v ?? 0;
                        patch(["fields", name, "bbox_x1y1x2y2"], bbox);
                      }}
                    />
                  </Field>
                ))}
              </div>
            </div>
          );
        })}
        <Button variant="outline" onClick={addField}>
          <Plus className="mr-1 h-4 w-4" /> Add field
        </Button>
      </div>
    </Section>
  );
}
