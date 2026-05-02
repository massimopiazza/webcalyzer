import { Field, Section } from "@/components/Field";
import { Input } from "@/components/ui/input";
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
import { NumberInput } from "./NumberInput";
import { FIELD_HELP, SECTION_HELP, SELECT_HELP } from "@/lib/explanations";

export function VideoOverlaySection({ state }: { state: ProfileFormState }) {
  const { profile, patch, errors } = state;
  const overlay = profile.video_overlay;

  return (
    <Section description={SECTION_HELP.video_overlay}>
      <div className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 p-3">
        <Switch
          checked={overlay.enabled}
          onCheckedChange={(checked) => patch(["video_overlay", "enabled"], checked)}
        />
        <div>
          <div className="text-sm font-medium">Render overlay video</div>
          <p className="text-xs text-muted-foreground">{FIELD_HELP.video_overlay_enabled}</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Field
          label="Plot mode"
          tooltip={FIELD_HELP.video_overlay_plot_mode}
          error={getError(errors, ["video_overlay", "plot_mode"])}
        >
          <Select
            value={overlay.plot_mode}
            onValueChange={(v) => patch(["video_overlay", "plot_mode"], v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="filtered" tooltip={SELECT_HELP.video_overlay_plot_mode.filtered}>
                filtered
              </SelectItem>
              <SelectItem
                value="with_rejected"
                tooltip={SELECT_HELP.video_overlay_plot_mode.with_rejected}
              >
                with_rejected
              </SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field
          label="Output filename"
          tooltip={FIELD_HELP.video_overlay_output_filename}
          error={getError(errors, ["video_overlay", "output_filename"])}
        >
          <Input
            value={overlay.output_filename}
            onChange={(e) => patch(["video_overlay", "output_filename"], e.target.value)}
            spellCheck={false}
          />
        </Field>
        <Field
          label="Width fraction"
          hint="0.05-1.0"
          tooltip={FIELD_HELP.video_overlay_width_fraction}
          error={getError(errors, ["video_overlay", "width_fraction"])}
        >
          <NumberInput
            value={overlay.width_fraction}
            onChange={(v) => patch(["video_overlay", "width_fraction"], v ?? 0)}
            invalid={!!getError(errors, ["video_overlay", "width_fraction"])}
          />
        </Field>
        <Field
          label="Height fraction"
          hint="0.05-1.0"
          tooltip={FIELD_HELP.video_overlay_height_fraction}
          error={getError(errors, ["video_overlay", "height_fraction"])}
        >
          <NumberInput
            value={overlay.height_fraction}
            onChange={(v) => patch(["video_overlay", "height_fraction"], v ?? 0)}
            invalid={!!getError(errors, ["video_overlay", "height_fraction"])}
          />
        </Field>
      </div>
      <div className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 p-3">
        <Switch
          checked={overlay.include_audio}
          onCheckedChange={(checked) => patch(["video_overlay", "include_audio"], checked)}
        />
        <div>
          <div className="text-sm font-medium">Include source audio</div>
          <p className="text-xs text-muted-foreground">{FIELD_HELP.video_overlay_include_audio}</p>
        </div>
      </div>
    </Section>
  );
}
