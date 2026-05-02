import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Crosshair, Plus, Save, Trash2 } from "lucide-react";
import { ApiError, FixtureFrames, ProfileDTO, api } from "@/lib/api";
import { useProfileForm } from "@/lib/profileForm";
import { Profile, emptyProfile } from "@/lib/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { SaveAsTemplateButton, TemplatePicker } from "@/components/TemplatePicker";
import { PathPicker } from "@/components/PathPicker";
import { PageHeader } from "@/components/PageHeader";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Box = [number, number, number, number];

const FIELD_COLORS = [
  "#ffae42",
  "#5cc4ff",
  "#7eea7e",
  "#c879ff",
  "#ffd64d",
  "#ff85a1",
];

export function CalibratePage() {
  const state = useProfileForm(emptyProfile());
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [templateRefreshKey, setTemplateRefreshKey] = useState(0);
  const [videoPath, setVideoPath] = useState("");
  const [fixtures, setFixtures] = useState<FixtureFrames | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [activeField, setActiveField] = useState<string | null>(null);
  const [drawing, setDrawing] = useState<Box | null>(null);
  const [loadingFrames, setLoadingFrames] = useState(false);

  const fieldNames = useMemo(() => Object.keys(state.profile.fields), [state.profile.fields]);

  useEffect(() => {
    if (!activeField && fieldNames.length > 0) setActiveField(fieldNames[0]);
    if (activeField && !fieldNames.includes(activeField)) setActiveField(fieldNames[0] ?? null);
  }, [fieldNames, activeField]);

  const loadFixtures = async () => {
    if (!videoPath) {
      toast.error("Pick a video first.");
      return;
    }
    setLoadingFrames(true);
    try {
      const range = state.profile.fixture_time_range_s;
      const data = await api.fixtureFrames(
        videoPath,
        state.profile.fixture_frame_count,
        range ? range[0] : null,
        range ? range[1] : null,
      );
      setFixtures(data);
      setFrameIndex(0);
    } catch (err) {
      toast.error((err as ApiError).message);
    } finally {
      setLoadingFrames(false);
    }
  };

  useEffect(() => {
    if (videoPath && !fixtures) {
      loadFixtures();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoPath]);

  const onLoadTemplate = (name: string, profile: ProfileDTO) => {
    state.reset(profile as Profile);
    setTemplateName(name);
  };

  const onSavedTemplate = (name: string) => {
    setTemplateName(name);
    setTemplateRefreshKey((key) => key + 1);
  };

  const updateActiveBbox = (box: Box) => {
    if (!activeField) return;
    state.patch(["fields", activeField, "bbox_x1y1x2y2"], normalizeBox(box));
  };

  const removeField = (name: string) => {
    state.setProfile((prev) => {
      const next = { ...prev.fields };
      delete next[name];
      return { ...prev, fields: next };
    });
  };

  const renameField = (oldName: string, newName: string) => {
    if (!newName || newName === oldName) return;
    state.setProfile((prev) => {
      const next: typeof prev.fields = {};
      for (const [k, v] of Object.entries(prev.fields)) {
        next[k === oldName ? newName : k] = v;
      }
      return { ...prev, fields: next };
    });
    if (activeField === oldName) setActiveField(newName);
  };

  const addField = () => {
    state.setProfile((prev) => {
      let i = 1;
      while (`field_${i}` in prev.fields) i += 1;
      const name = `field_${i}`;
      return {
        ...prev,
        fields: {
          ...prev.fields,
          [name]: {
            kind: "velocity",
            stage: "stage1",
            bbox_x1y1x2y2: [0.4, 0.4, 0.6, 0.6],
          },
        },
      };
    });
  };

  return (
    <>
      <PageHeader
        title="Calibrate field bboxes"
        description="Drag on the frame to place the active field's bounding box. Use the navigation arrows to step through fixture frames."
        badges={
          templateName ? (
            <Badge variant="outline" className="gap-1">
              loaded · <span className="font-mono">{templateName}</span>
            </Badge>
          ) : null
        }
        actions={
          <>
            <SaveAsTemplateButton
              profile={state.profile as ProfileDTO}
              isValid={state.isValid}
              currentName={templateName}
              onSaved={onSavedTemplate}
            />
            <Button
              onClick={async () => {
                if (!templateName) {
                  toast.error('Use "Save as template" to choose a destination first.');
                  return;
                }
                try {
                  await api.saveCalibration(templateName, state.profile as ProfileDTO);
                  toast.success(`Saved bboxes to ${templateName}`);
                } catch (err) {
                  toast.error((err as ApiError).message);
                }
              }}
              disabled={!state.isValid || !templateName}
              size="sm"
            >
              <Save className="mr-1 h-4 w-4" /> Save calibration
            </Button>
          </>
        }
      />

      <div className="mx-auto w-full max-w-7xl space-y-5 p-6">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Inputs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Profile template">
            <TemplatePicker
              selected={templateName}
              onLoad={onLoadTemplate}
              refreshKey={templateRefreshKey}
            />
          </Field>
          <div className="grid gap-4 md:grid-cols-[1fr_auto]">
            <Field label="Input video" required>
              <PathPicker value={videoPath} onChange={setVideoPath} mode="video" />
            </Field>
            <div className="flex items-end">
              <Button onClick={loadFixtures} disabled={!videoPath || loadingFrames}>
                <Crosshair className="mr-1 h-4 w-4" />
                {loadingFrames ? "Loading…" : "Sample frames"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {fixtures && fixtures.frames.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle>Frame {frameIndex + 1} / {fixtures.frames.length}</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                video index {fixtures.frames[frameIndex].index} · time{" "}
                {fixtures.frames[frameIndex].time_s.toFixed(2)}s · {fixtures.video.width}×
                {fixtures.video.height}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="icon"
                variant="outline"
                onClick={() => setFrameIndex((i) => Math.max(0, i - 1))}
                disabled={frameIndex === 0}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                size="icon"
                variant="outline"
                onClick={() =>
                  setFrameIndex((i) => Math.min(fixtures.frames.length - 1, i + 1))
                }
                disabled={frameIndex === fixtures.frames.length - 1}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <div className="rounded-md border border-border/70 bg-black/40">
              <CalibrationCanvas
                videoPath={videoPath}
                frameIndex={fixtures.frames[frameIndex].index}
                fields={state.profile.fields}
                activeField={activeField}
                drawing={drawing}
                onDrawing={setDrawing}
                onCommit={updateActiveBbox}
              />
            </div>
            <FieldList
              fields={state.profile.fields}
              activeField={activeField}
              onSelect={setActiveField}
              onRemove={removeField}
              onRename={renameField}
              onAdd={addField}
              onKindChange={(name, kind) => {
                state.patch(["fields", name, "kind"], kind);
                if (kind === "met") state.patch(["fields", name, "stage"], null);
                else if (state.profile.fields[name].stage === null)
                  state.patch(["fields", name, "stage"], "stage1");
              }}
              onStageChange={(name, stage) => state.patch(["fields", name, "stage"], stage)}
            />
          </CardContent>
        </Card>
      )}
      </div>
    </>
  );
}

function normalizeBox(box: Box): Box {
  const x0 = Math.min(box[0], box[2]);
  const y0 = Math.min(box[1], box[3]);
  const x1 = Math.max(box[0], box[2]);
  const y1 = Math.max(box[1], box[3]);
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  return [clamp(x0), clamp(y0), clamp(x1), clamp(y1)];
}

function CalibrationCanvas({
  videoPath,
  frameIndex,
  fields,
  activeField,
  drawing,
  onDrawing,
  onCommit,
}: {
  videoPath: string;
  frameIndex: number;
  fields: Record<string, Profile["fields"][string]>;
  activeField: string | null;
  drawing: Box | null;
  onDrawing: (next: Box | null) => void;
  onCommit: (box: Box) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [size, setSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const startRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    if (!videoPath) return;
    setImgUrl(api.videoFrameByIndexUrl(videoPath, frameIndex, 1600));
  }, [videoPath, frameIndex]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (!activeField) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    startRef.current = { x, y };
    onDrawing([x, y, x, y]);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!startRef.current) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    onDrawing([startRef.current.x, startRef.current.y, x, y]);
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!startRef.current || !drawing) {
      startRef.current = null;
      return;
    }
    onCommit(drawing);
    onDrawing(null);
    startRef.current = null;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
  };

  const fieldsList = Object.entries(fields);
  return (
    <div
      ref={containerRef}
      className="relative aspect-video w-full select-none"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onLoad={() => {
        if (containerRef.current) {
          const rect = containerRef.current.getBoundingClientRect();
          setSize({ width: rect.width, height: rect.height });
        }
      }}
    >
      {imgUrl && (
        <img
          src={imgUrl}
          alt="Frame"
          className="pointer-events-none absolute inset-0 h-full w-full object-contain"
          draggable={false}
        />
      )}
      <svg className="pointer-events-none absolute inset-0 h-full w-full">
        {fieldsList.map(([name, field], idx) => {
          const [x0, y0, x1, y1] = field.bbox_x1y1x2y2;
          const color = FIELD_COLORS[idx % FIELD_COLORS.length];
          const isActive = name === activeField;
          return (
            <g key={name} opacity={isActive ? 1 : 0.7}>
              <rect
                x={`${x0 * 100}%`}
                y={`${y0 * 100}%`}
                width={`${(x1 - x0) * 100}%`}
                height={`${(y1 - y0) * 100}%`}
                fill={`${color}20`}
                stroke={color}
                strokeWidth={isActive ? 2 : 1.25}
              />
              <text
                x={`${x0 * 100}%`}
                y={`${y0 * 100}%`}
                dy={-4}
                fontSize={11}
                fill={color}
                style={{ paintOrder: "stroke", stroke: "#000", strokeWidth: 3 }}
              >
                {idx + 1} · {name}
              </text>
            </g>
          );
        })}
        {drawing && (
          <rect
            x={`${Math.min(drawing[0], drawing[2]) * 100}%`}
            y={`${Math.min(drawing[1], drawing[3]) * 100}%`}
            width={`${Math.abs(drawing[2] - drawing[0]) * 100}%`}
            height={`${Math.abs(drawing[3] - drawing[1]) * 100}%`}
            fill="rgba(92, 196, 255, 0.25)"
            stroke="#5cc4ff"
            strokeWidth={2}
            strokeDasharray="4 2"
          />
        )}
      </svg>
      {!activeField && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-sm text-muted-foreground">
          Select a field on the right to start drawing
        </div>
      )}
    </div>
  );
}

function FieldList({
  fields,
  activeField,
  onSelect,
  onRemove,
  onRename,
  onAdd,
  onKindChange,
  onStageChange,
}: {
  fields: Record<string, Profile["fields"][string]>;
  activeField: string | null;
  onSelect: (name: string) => void;
  onRemove: (name: string) => void;
  onRename: (oldName: string, newName: string) => void;
  onAdd: () => void;
  onKindChange: (name: string, kind: Profile["fields"][string]["kind"]) => void;
  onStageChange: (name: string, stage: Profile["fields"][string]["stage"]) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">Fields</div>
        <Button size="sm" variant="outline" onClick={onAdd}>
          <Plus className="mr-1 h-3 w-3" /> Add
        </Button>
      </div>
      {Object.entries(fields).map(([name, field], idx) => (
        <div
          key={name}
          className={cn(
            "rounded-md border bg-muted/20 p-3 transition-colors",
            activeField === name
              ? "border-primary/60 bg-primary/10"
              : "border-border/60 hover:border-primary/40",
          )}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 text-left text-sm"
            onClick={() => onSelect(name)}
          >
            <span
              className="h-3 w-3 rounded-sm"
              style={{ background: FIELD_COLORS[idx % FIELD_COLORS.length] }}
            />
            <Input
              value={name}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => onRename(name, e.target.value.trim() || name)}
              className="h-8 font-mono text-xs"
            />
            <Button
              size="icon"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                onRemove(name);
              }}
              title="Remove field"
            >
              <Trash2 className="h-3 w-3 text-destructive/80" />
            </Button>
          </button>
          <div className="mt-2 grid gap-2">
            <Select
              value={field.kind}
              onValueChange={(v) => onKindChange(name, v as Profile["fields"][string]["kind"])}
            >
              <SelectTrigger className="h-8 min-h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="velocity">velocity</SelectItem>
                <SelectItem value="altitude">altitude</SelectItem>
                <SelectItem value="met">met</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={field.stage ?? "__none__"}
              onValueChange={(v) =>
                onStageChange(
                  name,
                  v === "__none__"
                    ? null
                    : (v as NonNullable<Profile["fields"][string]["stage"]>),
                )
              }
              disabled={field.kind === "met"}
            >
              <SelectTrigger className="h-8 min-h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="stage1">stage1</SelectItem>
                <SelectItem value="stage2">stage2</SelectItem>
                <SelectItem value="__none__">(none)</SelectItem>
              </SelectContent>
            </Select>
            <div className="font-mono text-[10px] text-muted-foreground">
              [{field.bbox_x1y1x2y2.map((v) => v.toFixed(3)).join(", ")}]
            </div>
          </div>
        </div>
      ))}
      {Object.keys(fields).length === 0 && (
        <div className="rounded-md border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
          No fields yet. Use Add to create one.
        </div>
      )}
    </div>
  );
}
