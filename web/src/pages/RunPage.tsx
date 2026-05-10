import { useEffect, useMemo, useState } from "react";
import { CircleAlert, Code2, RotateCcw } from "lucide-react";
import { ApiError, ProfileDTO, api } from "@/lib/api";
import { useProfileForm } from "@/lib/profileForm";
import { Profile, emptyProfile } from "@/lib/schema";
import { ProfileForm } from "@/components/profile/ProfileForm";
import { RunPanel, StartButton } from "@/components/RunPanel";
import { SaveAsTemplateButton, TemplatePicker } from "@/components/TemplatePicker";
import { PathPicker } from "@/components/PathPicker";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";

export type RunPagePersistedState = {
  profile: Profile;
  profileBaseline: Profile;
  templateName: string | null;
  templateRefreshKey: number;
  videoPath: string;
  outputDir: string;
  activeJobId: string | null;
};

export function createDefaultRunPageState(): RunPagePersistedState {
  const profile = emptyProfile();
  return {
    profile,
    profileBaseline: cloneProfile(profile),
    templateName: null,
    templateRefreshKey: 0,
    videoPath: "",
    outputDir: "",
    activeJobId: null,
  };
}

function displayErrorPath(path: string): string {
  return path
    .split(".")
    .map((segment) => (segment === "kind" ? "type" : segment))
    .join(".");
}

export function RunPage({
  persistedState,
  onPersistedStateChange,
}: {
  persistedState: RunPagePersistedState;
  onPersistedStateChange: (next: RunPagePersistedState) => void;
}) {
  const state = useProfileForm(persistedState.profile);
  const [templateName, setTemplateName] = useState<string | null>(persistedState.templateName);
  const [templateRefreshKey, setTemplateRefreshKey] = useState(persistedState.templateRefreshKey);
  const [videoPath, setVideoPath] = useState<string>(persistedState.videoPath);
  const [outputDir, setOutputDir] = useState<string>(persistedState.outputDir);
  const [profileBaseline, setProfileBaseline] = useState<Profile>(persistedState.profileBaseline);
  const [activeJobId, setActiveJobId] = useState<string | null>(persistedState.activeJobId);
  const [submitting, setSubmitting] = useState(false);
  const [yamlOpen, setYamlOpen] = useState(false);
  const [yamlPreview, setYamlPreview] = useState<string>("");

  useEffect(() => {
    onPersistedStateChange({
      profile: state.profile,
      profileBaseline,
      templateName,
      templateRefreshKey,
      videoPath,
      outputDir,
      activeJobId,
    });
  }, [
    activeJobId,
    onPersistedStateChange,
    outputDir,
    profileBaseline,
    state.profile,
    templateName,
    templateRefreshKey,
    videoPath,
  ]);

  const runnableErrorList = useMemo(
    () => Object.entries(state.runnableErrors),
    [state.runnableErrors],
  );

  const hasUnsavedProfileChanges = useMemo(
    () => profileSignature(state.profile) !== profileSignature(profileBaseline),
    [profileBaseline, state.profile],
  );

  const onLoadTemplate = (name: string, profile: ProfileDTO) => {
    const nextProfile = profile as Profile;
    state.reset(nextProfile);
    setProfileBaseline(cloneProfile(nextProfile));
    setTemplateName(name);
  };

  const onSavedTemplate = (name: string) => {
    setTemplateName(name);
    setProfileBaseline(cloneProfile(state.profile));
    setTemplateRefreshKey((key) => key + 1);
  };

  const startBlankTemplate = () => {
    const blankProfile = emptyProfile();
    state.reset(blankProfile);
    setProfileBaseline(cloneProfile(blankProfile));
    setTemplateName(null);
  };

  const previewYaml = async () => {
    if (!state.isValid) {
      toast.error("Fix validation errors before previewing.");
      return;
    }
    try {
      const text = await api.previewYaml(state.profile as ProfileDTO);
      setYamlPreview(text);
      setYamlOpen(true);
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  const submit = async () => {
    if (!videoPath) {
      toast.error("Select an input video.");
      return;
    }
    if (!outputDir) {
      toast.error("Select an output directory.");
      return;
    }
    if (!state.isRunnable) {
      toast.error("Fix runnable profile errors before running.");
      return;
    }
    setSubmitting(true);
    try {
      const job = await api.runJob({
        video_path: videoPath,
        output_dir: outputDir,
        profile: state.profile as ProfileDTO,
        sample_fps: null,
        ocr_backend: state.profile.ocr_backend,
        ocr_recognition_level: state.profile.ocr_recognition_level,
        ocr_workers: state.profile.default_ocr_workers,
        ocr_skip_detection: state.profile.skip_full_frame_ocr_fallback,
        overlay_engine: state.profile.video_overlay.engine,
        overlay_encoder: state.profile.video_overlay.encoder,
      });
      setActiveJobId(job.id);
      toast.success(`Job ${job.id} started`);
    } catch (err) {
      toast.error((err as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Run extraction"
        description="Configure the profile, point at a video, and run the full pipeline."
        badges={
          templateName ? (
            <Badge variant="outline" className="gap-1">
              loaded · <span className="font-mono">{templateName}</span>
            </Badge>
          ) : null
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={previewYaml}>
              <Code2 className="mr-1 h-4 w-4" /> Preview YAML
            </Button>
            <SaveAsTemplateButton
              profile={state.profile as ProfileDTO}
              isValid={state.isValid}
              currentName={templateName}
              onSaved={onSavedTemplate}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={startBlankTemplate}
            >
              <RotateCcw className="mr-1 h-4 w-4" /> Reset
            </Button>
            <StartButton
              disabled={!state.isRunnable || !videoPath || !outputDir}
              loading={submitting}
              onClick={submit}
              size="sm"
              className="order-first w-full sm:order-none sm:w-auto"
            />
          </>
        }
      />

      <div className="mx-auto w-full max-w-6xl space-y-5 p-4 sm:p-6">
        <RunPanel jobId={activeJobId} onCleared={() => setActiveJobId(null)} />

        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Inputs &amp; templates</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="Profile template">
              <TemplatePicker
                selected={templateName}
                onLoad={onLoadTemplate}
                refreshKey={templateRefreshKey}
                onStartBlank={startBlankTemplate}
                hasUnsavedChanges={hasUnsavedProfileChanges}
              />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Input video" required>
                <PathPicker value={videoPath} onChange={setVideoPath} mode="video" />
              </Field>
              <Field label="Output directory" required>
                <PathPicker value={outputDir} onChange={setOutputDir} mode="directory" />
              </Field>
            </div>
          </CardContent>
        </Card>

        <ProfileForm state={state} />

        {!state.isRunnable && (
          <Card className="border-destructive/40 bg-destructive/10">
            <CardHeader className="flex-row items-center gap-2 pb-2">
              <CircleAlert className="h-4 w-4 text-destructive" />
              <CardTitle className="text-sm text-destructive">
                {runnableErrorList.length} runnable error{runnableErrorList.length === 1 ? "" : "s"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-xs text-destructive/90">
                {runnableErrorList.slice(0, 8).map(([path, message]) => (
                  <li key={path}>
                    <span className="font-mono">{displayErrorPath(path) || "(profile)"}</span>:{" "}
                    {message}
                  </li>
                ))}
                {runnableErrorList.length > 8 && <li>+{runnableErrorList.length - 8} more…</li>}
              </ul>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-border/40 pt-4">
          <div className="text-xs text-muted-foreground">
            {state.isRunnable ? (
              <span className="text-success">Profile runnable · ready to run</span>
            ) : (
              <span className="text-destructive">
                Resolve {runnableErrorList.length} runnable error
                {runnableErrorList.length === 1 ? "" : "s"} before running
              </span>
            )}
          </div>
        </div>
      </div>

      <Dialog open={yamlOpen} onOpenChange={setYamlOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>YAML preview</DialogTitle>
            <DialogDescription className="sr-only">
              Validated YAML for the current profile.
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh] rounded-md border border-border/70 bg-black/40 p-3">
            <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed">{yamlPreview}</pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
}

function cloneProfile(profile: Profile): Profile {
  return JSON.parse(JSON.stringify(profile)) as Profile;
}

function profileSignature(profile: Profile): string {
  return JSON.stringify(profile);
}
