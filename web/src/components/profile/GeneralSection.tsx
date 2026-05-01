import { Field, Section } from "@/components/Field";
import { Input, Textarea } from "@/components/ui/input";
import { ProfileFormState } from "@/lib/profileForm";
import { getError } from "@/lib/errors";
import { NumberInput } from "./NumberInput";
import { FIELD_HELP, SECTION_HELP } from "@/lib/explanations";

export function GeneralSection({ state }: { state: { state: ProfileFormState }["state"] }) {
  const { profile, patch, errors } = state;
  const range = profile.fixture_time_range_s;
  return (
    <Section description={SECTION_HELP.general}>
      <div className="grid gap-4 md:grid-cols-2">
        <Field
          label="Profile name"
          required
          tooltip={FIELD_HELP.profile_name}
          error={getError(errors, ["profile_name"])}
        >
          <Input
            value={profile.profile_name}
            onChange={(e) => patch(["profile_name"], e.target.value)}
            spellCheck={false}
          />
        </Field>
        <Field
          label="Description"
          tooltip={FIELD_HELP.description}
          error={getError(errors, ["description"])}
        >
          <Input
            value={profile.description}
            onChange={(e) => patch(["description"], e.target.value)}
          />
        </Field>
        <Field
          label="Default sample fps"
          hint="OCR sample rate"
          tooltip={FIELD_HELP.default_sample_fps}
          error={getError(errors, ["default_sample_fps"])}
        >
          <NumberInput
            value={profile.default_sample_fps}
            onChange={(v) => patch(["default_sample_fps"], v ?? 0)}
            min={0.05}
            invalid={!!getError(errors, ["default_sample_fps"])}
          />
        </Field>
        <Field
          label="Fixture frame count"
          hint="Calibration sample frames"
          tooltip={FIELD_HELP.fixture_frame_count}
          error={getError(errors, ["fixture_frame_count"])}
        >
          <NumberInput
            value={profile.fixture_frame_count}
            onChange={(v) => patch(["fixture_frame_count"], Math.round(v ?? 1))}
            min={1}
            invalid={!!getError(errors, ["fixture_frame_count"])}
          />
        </Field>
        <Field
          label="Fixture time range start (s)"
          tooltip={FIELD_HELP.fixture_time_range_start}
          error={getError(errors, ["fixture_time_range_s", "0"])}
        >
          <NumberInput
            value={range ? range[0] : null}
            allowNull
            onChange={(v) => {
              if (v === null) {
                patch(["fixture_time_range_s"], null);
                return;
              }
              const end = range ? range[1] : Math.max(v + 1, 60);
              patch(["fixture_time_range_s"], [v, end]);
            }}
            invalid={!!getError(errors, ["fixture_time_range_s", "0"])}
          />
        </Field>
        <Field
          label="Fixture time range end (s)"
          tooltip={FIELD_HELP.fixture_time_range_end}
          error={getError(errors, ["fixture_time_range_s", "1"])}
        >
          <NumberInput
            value={range ? range[1] : null}
            allowNull
            onChange={(v) => {
              if (v === null) {
                patch(["fixture_time_range_s"], null);
                return;
              }
              const start = range ? range[0] : 0;
              patch(["fixture_time_range_s"], [start, v]);
            }}
            invalid={!!getError(errors, ["fixture_time_range_s", "1"])}
          />
        </Field>
      </div>

      <Field
        label="Notes"
        tooltip={FIELD_HELP.description}
      >
        <Textarea
          rows={3}
          value={profile.description}
          onChange={(e) => patch(["description"], e.target.value)}
        />
      </Field>
    </Section>
  );
}
