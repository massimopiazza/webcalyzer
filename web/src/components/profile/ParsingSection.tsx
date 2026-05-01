import { Plus, Trash2 } from "lucide-react";
import { Field, Section } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ProfileFormState } from "@/lib/profileForm";
import { useMeta } from "@/lib/meta";
import { getError } from "@/lib/errors";
import { NumberInput } from "./NumberInput";
import { ParsingDTO } from "@/lib/api";
import { ParsingValue } from "@/lib/schema";
import { FIELD_HELP, SECTION_HELP } from "@/lib/explanations";

type ParsingType = "velocity" | "altitude";

function defaultParsing(meta: ParsingDTO | null): ParsingValue {
  return (meta as ParsingValue) ?? {
    velocity: {
      units: { MPS: { aliases: ["M/S", "MPS"], si_factor: 1.0 } },
      default_unit: "MPS",
      ambiguous_default_unit: null,
      inferred_units_with_separator: ["MPS"],
      inferred_units_without_separator: ["MPS"],
    },
    altitude: {
      units: { M: { aliases: ["M"], si_factor: 1.0 } },
      default_unit: "M",
      ambiguous_default_unit: null,
      inferred_units_with_separator: ["M"],
      inferred_units_without_separator: ["M"],
    },
    met: { timestamp_patterns: ["T\\s*([+-])?\\s*(\\d{2})(?::(\\d{2}))(?::(\\d{2}))?"] },
    custom_words: [],
  };
}

export function ParsingSection({ state }: { state: ProfileFormState }) {
  const meta = useMeta();
  const { profile, patch, setProfile, errors } = state;
  const enabled = profile.parsing !== null;

  const toggle = (next: boolean) => {
    if (next) {
      const defaults = defaultParsing(meta?.default_parsing ?? null);
      setProfile((prev) => ({ ...prev, parsing: defaults }));
    } else {
      setProfile((prev) => ({ ...prev, parsing: null }));
    }
  };

  return (
    <Section description={SECTION_HELP.parsing}>
      <div className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 p-3">
        <Switch checked={enabled} onCheckedChange={toggle} />
        <div>
          <div className="text-sm font-medium">Customize parsing</div>
          <p className="text-xs text-muted-foreground">{FIELD_HELP.parsing_enabled}</p>
        </div>
      </div>

      {enabled && profile.parsing && (
        <div className="space-y-4">
          <ParsingTypeEditor state={state} type="velocity" />
          <ParsingTypeEditor state={state} type="altitude" />
          <MetEditor state={state} />
          <CustomWordsEditor state={state} />
          {getError(errors, ["parsing"]) && (
            <p className="text-xs text-destructive">{getError(errors, ["parsing"])}</p>
          )}
        </div>
      )}
    </Section>
  );
}

function ParsingTypeEditor({ state, type }: { state: ProfileFormState; type: ParsingType }) {
  const { profile, patch, setProfile, errors } = state;
  if (!profile.parsing) return null;
  const block = profile.parsing[type];

  const renameUnit = (oldName: string, newName: string) => {
    if (!newName || newName === oldName) return;
    setProfile((prev) => {
      if (!prev.parsing) return prev;
      const units: typeof block.units = {};
      for (const [k, v] of Object.entries(prev.parsing[type].units)) {
        units[k === oldName ? newName : k] = v;
      }
      return {
        ...prev,
        parsing: {
          ...prev.parsing,
          [type]: { ...prev.parsing[type], units },
        },
      };
    });
  };

  const removeUnit = (name: string) => {
    setProfile((prev) => {
      if (!prev.parsing) return prev;
      const units = { ...prev.parsing[type].units };
      delete units[name];
      return {
        ...prev,
        parsing: {
          ...prev.parsing,
          [type]: { ...prev.parsing[type], units },
        },
      };
    });
  };

  const addUnit = () => {
    setProfile((prev) => {
      if (!prev.parsing) return prev;
      let i = 1;
      while (`UNIT_${i}` in prev.parsing[type].units) i += 1;
      return {
        ...prev,
        parsing: {
          ...prev.parsing,
          [type]: {
            ...prev.parsing[type],
            units: {
              ...prev.parsing[type].units,
              [`UNIT_${i}`]: { aliases: [`UNIT_${i}`], si_factor: 1.0 },
            },
          },
        },
      };
    });
  };

  return (
    <div className="rounded-md border border-border/70 bg-muted/15 p-3">
      <h4 className="text-sm font-semibold capitalize">{type} parsing</h4>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <Field
          label="Default unit"
          tooltip={FIELD_HELP.parsing_default_unit}
          error={getError(errors, ["parsing", type, "default_unit"])}
        >
          <Input
            value={block.default_unit}
            onChange={(e) => patch(["parsing", type, "default_unit"], e.target.value.toUpperCase())}
            spellCheck={false}
          />
        </Field>
        <Field
          label="Ambiguous default unit"
          tooltip={FIELD_HELP.parsing_ambiguous_default_unit}
          error={getError(errors, ["parsing", type, "ambiguous_default_unit"])}
        >
          <Input
            value={block.ambiguous_default_unit ?? ""}
            onChange={(e) => {
              const v = e.target.value.trim();
              patch(["parsing", type, "ambiguous_default_unit"], v ? v.toUpperCase() : null);
            }}
            spellCheck={false}
          />
        </Field>
        <Field
          label="Inferred (with separator)"
          tooltip={FIELD_HELP.parsing_inferred_with_separator}
        >
          <Input
            value={block.inferred_units_with_separator.join(", ")}
            onChange={(e) =>
              patch(
                ["parsing", type, "inferred_units_with_separator"],
                e.target.value
                  .split(",")
                  .map((s) => s.trim().toUpperCase())
                  .filter(Boolean),
              )
            }
            spellCheck={false}
          />
        </Field>
        <Field
          label="Inferred (without separator)"
          tooltip={FIELD_HELP.parsing_inferred_without_separator}
        >
          <Input
            value={block.inferred_units_without_separator.join(", ")}
            onChange={(e) =>
              patch(
                ["parsing", type, "inferred_units_without_separator"],
                e.target.value
                  .split(",")
                  .map((s) => s.trim().toUpperCase())
                  .filter(Boolean),
              )
            }
            spellCheck={false}
          />
        </Field>
      </div>
      <div className="mt-4 space-y-2">
        <div className="flex items-center justify-between">
          <h5 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Unit aliases
          </h5>
          <Button variant="outline" size="sm" onClick={addUnit}>
            <Plus className="mr-1 h-3 w-3" /> Add unit
          </Button>
        </div>
        {Object.entries(block.units).map(([unitName, unit]) => (
          <div
            key={unitName}
            className="grid gap-2 rounded-md border border-border/60 bg-background/40 p-2 md:grid-cols-[140px_1fr_140px_auto]"
          >
            <Input
              value={unitName}
              onChange={(e) => renameUnit(unitName, e.target.value.trim().toUpperCase() || unitName)}
              spellCheck={false}
              className="font-mono text-xs"
            />
            <Input
              value={unit.aliases.join(", ")}
              onChange={(e) =>
                patch(["parsing", type, "units", unitName, "aliases"],
                  e.target.value
                    .split(",")
                    .map((s) => s.trim().toUpperCase())
                    .filter(Boolean),
                )
              }
              spellCheck={false}
              className="font-mono text-xs"
              placeholder="aliases (comma-separated)"
            />
            <NumberInput
              value={unit.si_factor}
              onChange={(v) => patch(["parsing", type, "units", unitName, "si_factor"], v ?? 1)}
            />
            <Button variant="ghost" size="icon" onClick={() => removeUnit(unitName)}>
              <Trash2 className="h-4 w-4 text-destructive/80" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetEditor({ state }: { state: ProfileFormState }) {
  const { profile, patch, setProfile, errors } = state;
  if (!profile.parsing) return null;
  const patterns = profile.parsing.met.timestamp_patterns;
  const update = (next: string[]) =>
    setProfile((prev) =>
      prev.parsing
        ? { ...prev, parsing: { ...prev.parsing, met: { timestamp_patterns: next } } }
        : prev,
    );

  return (
    <div className="rounded-md border border-border/70 bg-muted/15 p-3">
      <h4 className="text-sm font-semibold">MET regex patterns</h4>
      <div className="mt-2 space-y-2">
        {patterns.map((pattern, index) => (
          <div key={index} className="flex items-start gap-2">
            <Input
              value={pattern}
              onChange={(e) => {
                const next = [...patterns];
                next[index] = e.target.value;
                update(next);
              }}
              spellCheck={false}
              className="font-mono text-xs"
            />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => update(patterns.filter((_, i) => i !== index))}
            >
              <Trash2 className="h-4 w-4 text-destructive/80" />
            </Button>
          </div>
        ))}
        {getError(errors, ["parsing", "met", "timestamp_patterns"]) && (
          <p className="text-xs text-destructive">
            {getError(errors, ["parsing", "met", "timestamp_patterns"])}
          </p>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={() => update([...patterns, "T\\s*([+-])?\\s*(\\d{2})(?::(\\d{2}))(?::(\\d{2}))?"])}
        >
          <Plus className="mr-1 h-3 w-3" /> Add pattern
        </Button>
      </div>
    </div>
  );
}

function CustomWordsEditor({ state }: { state: ProfileFormState }) {
  const { profile, patch } = state;
  if (!profile.parsing) return null;
  const value = profile.parsing.custom_words.join(", ");
  return (
    <Field
      label="Custom OCR words"
      hint="Comma-separated. Helps the OCR engine recognize known tokens."
      tooltip={FIELD_HELP.parsing_custom_words}
    >
      <Input
        value={value}
        onChange={(e) =>
          patch(
            ["parsing", "custom_words"],
            e.target.value
              .split(",")
              .map((s) => s.trim().toUpperCase())
              .filter(Boolean),
          )
        }
        spellCheck={false}
        className="font-mono text-xs"
      />
    </Field>
  );
}
