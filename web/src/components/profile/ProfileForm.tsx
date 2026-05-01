import { useState } from "react";
import { ChevronDown, Settings2 } from "lucide-react";
import { ProfileFormState } from "@/lib/profileForm";
import { hasErrorWithPrefix } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GeneralSection } from "./GeneralSection";
import { VideoOverlaySection } from "./VideoOverlaySection";
import { TrajectorySection } from "./TrajectorySection";
import { FieldsSection } from "./FieldsSection";
import { HardcodedPointsSection } from "./HardcodedPointsSection";
import { ParsingSection } from "./ParsingSection";

type SectionDef = {
  id: string;
  title: string;
  Component: (props: { state: ProfileFormState }) => JSX.Element;
  /** State paths whose validation errors should be attributed to this section. */
  errorPrefixes: string[];
};

const PRIMARY_SECTIONS: SectionDef[] = [
  {
    id: "general",
    title: "General",
    Component: GeneralSection,
    errorPrefixes: [
      "profile_name",
      "description",
      "default_sample_fps",
      "fixture_frame_count",
      "fixture_time_range_s",
    ],
  },
  {
    id: "trajectory",
    title: "Trajectory",
    Component: TrajectorySection,
    errorPrefixes: ["trajectory"],
  },
  {
    id: "hardcoded",
    title: "Anchor points",
    Component: HardcodedPointsSection,
    errorPrefixes: ["hardcoded_raw_data_points"],
  },
  {
    id: "video_overlay",
    title: "Video overlay",
    Component: VideoOverlaySection,
    errorPrefixes: ["video_overlay"],
  },
];

const ADVANCED_SECTIONS: SectionDef[] = [
  {
    id: "fields",
    title: "Fields",
    Component: FieldsSection,
    errorPrefixes: ["fields"],
  },
  {
    id: "parsing",
    title: "Parsing",
    Component: ParsingSection,
    errorPrefixes: ["parsing"],
  },
];

export function ProfileForm({ state }: { state: ProfileFormState }) {
  const advancedHasErrors = ADVANCED_SECTIONS.some((section) =>
    section.errorPrefixes.some((prefix) =>
      hasErrorWithPrefix(state.errors, prefix.split(".")),
    ),
  );
  const [advancedOpen, setAdvancedOpen] = useState<boolean>(advancedHasErrors);

  // Auto-expand if a validation error appears under an advanced section.
  if (advancedHasErrors && !advancedOpen) {
    // setState in render is fine here because it converges immediately.
    setAdvancedOpen(true);
  }

  return (
    <div className="space-y-4">
      {PRIMARY_SECTIONS.map((section) => (
        <SectionCard key={section.id} section={section} state={state} />
      ))}

      <Card className={cn(advancedOpen && "border-primary/30")}>
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-muted/30"
        >
          <Settings2 className="h-4 w-4 text-muted-foreground" />
          <div className="flex-1">
            <div className="flex items-center gap-2 text-sm font-semibold">
              Advanced settings
              {advancedHasErrors && (
                <Badge variant="destructive" className="text-[10px]">
                  errors
                </Badge>
              )}
            </div>
            <div className="text-xs text-muted-foreground">
              Field bbox table and parsing rules. Most users won't need these - Calibrate handles
              fields visually, and parsing falls back to bundled defaults.
            </div>
          </div>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform",
              advancedOpen && "rotate-180",
            )}
          />
        </button>
        {advancedOpen && (
          <div className="border-t border-border/60">
            <div className="space-y-4 p-5">
              {ADVANCED_SECTIONS.map((section) => (
                <div key={section.id} id={`section-${section.id}`} className="space-y-3">
                  <h3 className="text-sm font-semibold">{section.title}</h3>
                  <section.Component state={state} />
                </div>
              ))}
            </div>
            <div className="flex justify-end px-5 py-3 border-t border-border/40">
              <Button variant="ghost" size="sm" onClick={() => setAdvancedOpen(false)}>
                Collapse advanced
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function SectionCard({ section, state }: { section: SectionDef; state: ProfileFormState }) {
  return (
    <Card id={`section-${section.id}`}>
      <CardHeader className="pb-2">
        <CardTitle>{section.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <section.Component state={state} />
      </CardContent>
    </Card>
  );
}
