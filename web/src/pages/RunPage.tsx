import { useMemo, useState } from "react";
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
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { NumberInput } from "@/components/profile/NumberInput";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FIELD_HELP, SELECT_HELP } from "@/lib/explanations";
import { toast } from "sonner";

const OCR_BACKENDS = [
  { value: "auto", label: "auto (Vision on macOS, RapidOCR elsewhere)" },
  { value: "rapidocr", label: "rapidocr (cross-platform)" },
  { value: "vision", label: "vision (macOS only)" },
];

const RECOGNITION_LEVELS = [
  { value: "accurate", label: "accurate (Vision)" },
  { value: "fast", label: "fast (Vision)" },
];

const OVERLAY_ENGINES = [
  { value: "auto", label: "auto (ffmpeg → opencv)" },
  { value: "ffmpeg", label: "ffmpeg" },
  { value: "opencv", label: "opencv" },
];

const OVERLAY_ENCODERS = [
  "auto",
  "videotoolbox",
  "h264_videotoolbox",
  "nvenc",
  "h264_nvenc",
  "qsv",
  "h264_qsv",
  "vaapi",
  "h264_vaapi",
  "libx264",
];

type RunOverrides = {
  sample_fps: number | null;
  ocr_backend: string;
  ocr_recognition_level: string;
  ocr_workers: number;
  ocr_skip_detection: boolean;
  overlay_engine: string;
  overlay_encoder: string;
};

const DEFAULT_OVERRIDES: RunOverrides = {
  sample_fps: null,
  ocr_backend: "auto",
  ocr_recognition_level: "accurate",
  ocr_workers: 0,
  ocr_skip_detection: false,
  overlay_engine: "auto",
  overlay_encoder: "auto",
};

function displayErrorPath(path: string): string {
  return path
    .split(".")
    .map((segment) => (segment === "kind" ? "type" : segment))
    .join(".");
}

export function RunPage() {
  const state = useProfileForm(emptyProfile());
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [videoPath, setVideoPath] = useState<string>("");
  const [outputDir, setOutputDir] = useState<string>("");
  const [overrides, setOverrides] = useState<RunOverrides>(DEFAULT_OVERRIDES);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [yamlOpen, setYamlOpen] = useState(false);
  const [yamlPreview, setYamlPreview] = useState<string>("");

  const errorList = useMemo(() => Object.entries(state.errors), [state.errors]);

  const onLoadTemplate = (name: string, profile: ProfileDTO) => {
    state.reset(profile as Profile);
    setTemplateName(name);
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
    if (!state.isValid) {
      toast.error("Fix validation errors before running.");
      return;
    }
    setSubmitting(true);
    try {
      const job = await api.runJob({
        video_path: videoPath,
        output_dir: outputDir,
        profile: state.profile as ProfileDTO,
        sample_fps: overrides.sample_fps,
        ocr_backend: overrides.ocr_backend,
        ocr_recognition_level: overrides.ocr_recognition_level,
        ocr_workers: overrides.ocr_workers,
        ocr_skip_detection: overrides.ocr_skip_detection,
        overlay_engine: overrides.overlay_engine,
        overlay_encoder: overrides.overlay_encoder,
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
              onSaved={(name) => setTemplateName(name)}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                state.reset(emptyProfile());
                setTemplateName(null);
              }}
            >
              <RotateCcw className="mr-1 h-4 w-4" /> Reset
            </Button>
            <StartButton
              disabled={!state.isValid || !videoPath || !outputDir}
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
              <TemplatePicker selected={templateName} onLoad={onLoadTemplate} />
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

        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Run overrides</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-3">
            <Field
              label="Sample fps override"
              hint="Empty = use profile"
              tooltip={FIELD_HELP.override_sample_fps}
            >
              <NumberInput
                value={overrides.sample_fps}
                allowNull
                onChange={(v) => setOverrides((s) => ({ ...s, sample_fps: v }))}
              />
            </Field>
            <Field label="OCR backend" tooltip={FIELD_HELP.override_ocr_backend}>
              <Select
                value={overrides.ocr_backend}
                onValueChange={(v) => setOverrides((s) => ({ ...s, ocr_backend: v }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OCR_BACKENDS.map((o) => (
                    <SelectItem
                      key={o.value}
                      value={o.value}
                      tooltip={SELECT_HELP.override_ocr_backend[o.value]}
                    >
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="Recognition level (Vision)"
              tooltip={FIELD_HELP.override_ocr_recognition_level}
            >
              <Select
                value={overrides.ocr_recognition_level}
                onValueChange={(v) => setOverrides((s) => ({ ...s, ocr_recognition_level: v }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RECOGNITION_LEVELS.map((o) => (
                    <SelectItem
                      key={o.value}
                      value={o.value}
                      tooltip={SELECT_HELP.override_ocr_recognition_level[o.value]}
                    >
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="OCR workers"
              hint="0 = auto"
              tooltip={FIELD_HELP.override_ocr_workers}
            >
              <NumberInput
                value={overrides.ocr_workers}
                onChange={(v) =>
                  setOverrides((s) => ({ ...s, ocr_workers: Math.max(0, Math.round(v ?? 0)) }))
                }
              />
            </Field>
            <Field label="Overlay engine" tooltip={FIELD_HELP.override_overlay_engine}>
              <Select
                value={overrides.overlay_engine}
                onValueChange={(v) => setOverrides((s) => ({ ...s, overlay_engine: v }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OVERLAY_ENGINES.map((o) => (
                    <SelectItem
                      key={o.value}
                      value={o.value}
                      tooltip={SELECT_HELP.override_overlay_engine[o.value]}
                    >
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Overlay encoder" tooltip={FIELD_HELP.override_overlay_encoder}>
              <Select
                value={overrides.overlay_encoder}
                onValueChange={(v) => setOverrides((s) => ({ ...s, overlay_encoder: v }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OVERLAY_ENCODERS.map((value) => (
                    <SelectItem
                      key={value}
                      value={value}
                      tooltip={SELECT_HELP.override_overlay_encoder[value]}
                    >
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <div className="md:col-span-3 flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 p-3">
              <Switch
                checked={overrides.ocr_skip_detection}
                onCheckedChange={(checked) =>
                  setOverrides((s) => ({ ...s, ocr_skip_detection: checked }))
                }
              />
              <div>
                <div className="text-sm font-medium">Skip OCR detection</div>
                <p className="text-xs text-muted-foreground">
                  {FIELD_HELP.override_ocr_skip_detection}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <ProfileForm state={state} />

        {!state.isValid && (
          <Card className="border-destructive/40 bg-destructive/10">
            <CardHeader className="flex-row items-center gap-2 pb-2">
              <CircleAlert className="h-4 w-4 text-destructive" />
              <CardTitle className="text-sm text-destructive">
                {errorList.length} validation error{errorList.length === 1 ? "" : "s"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-xs text-destructive/90">
                {errorList.slice(0, 8).map(([path, message]) => (
                  <li key={path}>
                    <span className="font-mono">{displayErrorPath(path) || "(profile)"}</span>:{" "}
                    {message}
                  </li>
                ))}
                {errorList.length > 8 && <li>+{errorList.length - 8} more…</li>}
              </ul>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-border/40 pt-4">
          <div className="text-xs text-muted-foreground">
            {state.isValid ? (
              <span className="text-success">Profile valid · ready to run</span>
            ) : (
              <span className="text-destructive">
                Resolve {errorList.length} error{errorList.length === 1 ? "" : "s"} before running
              </span>
            )}
          </div>
        </div>
      </div>

      <Dialog open={yamlOpen} onOpenChange={setYamlOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>YAML preview</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh] rounded-md border border-border/70 bg-black/40 p-3">
            <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed">{yamlPreview}</pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
}
