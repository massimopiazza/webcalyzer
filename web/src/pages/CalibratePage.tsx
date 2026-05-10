import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Crosshair,
  GitBranchPlus,
  LoaderCircle,
  RotateCcw,
  Scissors,
  X,
} from "lucide-react";
import { ApiError, ProfileDTO, VideoMetadata, api } from "@/lib/api";
import { useProfileForm } from "@/lib/profileForm";
import {
  CANONICAL_FIELD_DEFINITIONS,
  CANONICAL_FIELD_ORDER,
  CanonicalFieldName,
  FieldValue,
  Profile,
  SegmentValue,
  defaultSegmentFields,
  emptyProfile,
} from "@/lib/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import { SaveAsTemplateButton, TemplatePicker } from "@/components/TemplatePicker";
import { PathPicker } from "@/components/PathPicker";
import { PageHeader } from "@/components/PageHeader";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Box = [number, number, number, number];
type PreviewMode = "immediate" | "cadence";
export type CalibrationBaseline = {
  calibration_video: Profile["calibration_video"];
  segments: SegmentValue[];
};

const FRAME_PREVIEW_CADENCE_MS = 120;
const FRAME_LOADING_DELAY_MS = 500;

const FIELD_COLORS: Record<CanonicalFieldName, string> = {
  met: "#5cc4ff",
  stage1_velocity: "#ffae42",
  stage1_altitude: "#7eea7e",
  stage2_velocity: "#c879ff",
  stage2_altitude: "#ffd64d",
};

function fieldFor(name: CanonicalFieldName): FieldValue {
  const def = CANONICAL_FIELD_DEFINITIONS[name];
  return { kind: def.kind, stage: def.stage, bbox_x1y1x2y2: null };
}

export type CalibratePagePersistedState = {
  profile: Profile;
  templateName: string | null;
  templateRefreshKey: number;
  videoPath: string;
  metadata: VideoMetadata | null;
  frameIndex: number;
  previewFrameIndex: number;
  activeSlot: CanonicalFieldName;
  calibrationBaseline: CalibrationBaseline | null;
};

export function createDefaultCalibratePageState(): CalibratePagePersistedState {
  return {
    profile: emptyProfile(),
    templateName: null,
    templateRefreshKey: 0,
    videoPath: "",
    metadata: null,
    frameIndex: 0,
    previewFrameIndex: 0,
    activeSlot: "met",
    calibrationBaseline: null,
  };
}

export function CalibratePage({
  persistedState,
  onPersistedStateChange,
}: {
  persistedState: CalibratePagePersistedState;
  onPersistedStateChange: (next: CalibratePagePersistedState) => void;
}) {
  const state = useProfileForm(persistedState.profile);
  const [templateName, setTemplateName] = useState<string | null>(persistedState.templateName);
  const [templateRefreshKey, setTemplateRefreshKey] = useState(persistedState.templateRefreshKey);
  const [videoPath, setVideoPath] = useState(persistedState.videoPath);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(persistedState.metadata);
  const [frameIndex, setFrameIndex] = useState(persistedState.frameIndex);
  const [previewFrameIndex, setPreviewFrameIndex] = useState(persistedState.previewFrameIndex);
  const [activeSlot, setActiveSlot] = useState<CanonicalFieldName>(persistedState.activeSlot);
  const [calibrationBaseline, setCalibrationBaseline] =
    useState<CalibrationBaseline | null>(persistedState.calibrationBaseline);
  const [drawing, setDrawing] = useState<Box | null>(null);
  const frameIndexRef = useRef(persistedState.frameIndex);
  const previewFrameAtRef = useRef(performance.now());
  const sliderDraggingRef = useRef(false);
  const holdRef = useRef<{
    direction: -1 | 1;
    startedAt: number;
    lastAt: number;
    carry: number;
    raf: number | null;
  } | null>(null);

  const activeSegmentIndex = useMemo(
    () => activeSegmentForFrame(state.profile.segments, frameIndex),
    [state.profile.segments, frameIndex],
  );
  const activeSegment = state.profile.segments[activeSegmentIndex] ?? state.profile.segments[0];

  const hasCalibrationChanges = useMemo(() => {
    if (!templateName || !calibrationBaseline) return false;
    return (
      calibrationSignature(calibrationFromProfile(state.profile)) !==
      calibrationSignature(calibrationBaseline)
    );
  }, [calibrationBaseline, state.profile, templateName]);

  const hasUnsavedCalibrationTemplateChanges = useMemo(() => {
    const current = calibrationSignature(calibrationFromProfile(state.profile));
    if (calibrationBaseline) {
      return current !== calibrationSignature(calibrationBaseline);
    }
    return current !== calibrationSignature(calibrationFromProfile(emptyProfile()));
  }, [calibrationBaseline, state.profile]);

  useEffect(() => {
    onPersistedStateChange({
      profile: state.profile,
      templateName,
      templateRefreshKey,
      videoPath,
      metadata,
      frameIndex,
      previewFrameIndex,
      activeSlot,
      calibrationBaseline,
    });
  }, [
    activeSlot,
    calibrationBaseline,
    frameIndex,
    metadata,
    onPersistedStateChange,
    previewFrameIndex,
    state.profile,
    templateName,
    templateRefreshKey,
    videoPath,
  ]);

  const clampFrameIndex = useCallback(
    (value: number) => {
      const rounded = Math.round(value);
      if (!metadata) return Math.max(0, rounded);
      return Math.max(0, Math.min(Math.max(0, metadata.frame_count - 1), rounded));
    },
    [metadata],
  );

  const showPreviewFrame = useCallback(
    (value: number, mode: PreviewMode) => {
      const next = clampFrameIndex(value);
      const now = performance.now();
      if (mode === "immediate" || now - previewFrameAtRef.current >= FRAME_PREVIEW_CADENCE_MS) {
        previewFrameAtRef.current = now;
        setPreviewFrameIndex(next);
      }
    },
    [clampFrameIndex],
  );

  const setSelectedFrameIndex = useCallback(
    (value: number | ((current: number) => number), previewMode: PreviewMode = "immediate") => {
      const current = frameIndexRef.current;
      const next = clampFrameIndex(typeof value === "function" ? value(current) : value);
      frameIndexRef.current = next;
      setFrameIndex(next);
      showPreviewFrame(next, previewMode);
      return next;
    },
    [clampFrameIndex, showPreviewFrame],
  );

  const advanceFrame = useCallback(
    (delta: number, previewMode: PreviewMode = "cadence") => {
      setSelectedFrameIndex((current) => current + delta, previewMode);
    },
    [setSelectedFrameIndex],
  );

  const cancelFrameHold = useCallback(() => {
    const hold = holdRef.current;
    if (hold?.raf !== null && hold?.raf !== undefined) {
      window.cancelAnimationFrame(hold.raf);
    }
    holdRef.current = null;
  }, []);

  const stopFrameHold = useCallback(() => {
    cancelFrameHold();
    showPreviewFrame(frameIndexRef.current, "immediate");
  }, [cancelFrameHold, showPreviewFrame]);

  const startFrameHold = useCallback(
    (direction: -1 | 1) => {
      if (!metadata) return;
      if (holdRef.current?.direction === direction) return;
      stopFrameHold();
      advanceFrame(direction, "immediate");

      const now = performance.now();
      holdRef.current = {
        direction,
        startedAt: now,
        lastAt: now,
        carry: 0,
        raf: null,
      };

      const maxRate = Math.max(1, metadata.fps * 10);
      const baseRate = 4;
      const rampDelayS = 0.3;
      const rampDurationS = 1.4;

      const tick = (timestamp: number) => {
        const hold = holdRef.current;
        if (!hold || hold.direction !== direction) return;
        const elapsedS = (timestamp - hold.startedAt) / 1000;
        const deltaS = Math.max(0, (timestamp - hold.lastAt) / 1000);
        hold.lastAt = timestamp;
        const rampT = Math.min(1, Math.max(0, (elapsedS - rampDelayS) / rampDurationS));
        const eased = 1 - Math.pow(1 - rampT, 3);
        const rate = baseRate + (maxRate - baseRate) * eased;
        hold.carry += rate * deltaS;
        const wholeFrames = Math.floor(hold.carry);
        if (wholeFrames > 0) {
          advanceFrame(direction * wholeFrames, "cadence");
          hold.carry -= wholeFrames;
        }
        hold.raf = window.requestAnimationFrame(tick);
      };

      holdRef.current.raf = window.requestAnimationFrame(tick);
    },
    [advanceFrame, metadata, stopFrameHold],
  );

  useEffect(() => cancelFrameHold, [cancelFrameHold]);

  useEffect(() => {
    const isTypingTarget = (target: EventTarget | null) => {
      if (!(target instanceof HTMLElement)) return false;
      if (target.isContentEditable) return true;
      if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
      if (target instanceof HTMLInputElement) return target.type !== "range";
      return false;
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      if (event.repeat) return;
      startFrameHold(event.key === "ArrowLeft" ? -1 : 1);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      stopFrameHold();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [startFrameHold, stopFrameHold]);

  const loadVideo = async (path: string) => {
    if (!path) return;
    try {
      const video = await api.videoMetadata(path);
      setMetadata(video);
      setFrameIndex(0);
      frameIndexRef.current = 0;
      setPreviewFrameIndex(0);
      previewFrameAtRef.current = performance.now();
      state.setProfile((prev) => ({
        ...prev,
        calibration_video: {
          path,
          fps: video.fps,
          frame_count: video.frame_count,
          width: video.width,
          height: video.height,
        },
        segments: [
          {
            id: "segment_1",
            start_frame_index: 0,
            start_time_s: 0,
            end_frame_index: video.frame_count,
            end_time_s: timeForFrame(video.frame_count, video.fps),
            fields: defaultSegmentFields(),
          },
        ],
      }));
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  useEffect(() => {
    if (videoPath && (videoPath !== state.profile.calibration_video.path || !metadata)) {
      loadVideo(videoPath);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoPath, state.profile.calibration_video.path, metadata]);

  const onLoadTemplate = (name: string, profile: ProfileDTO) => {
    const nextProfile = profile as Profile;
    state.reset(nextProfile);
    setTemplateName(name);
    setCalibrationBaseline(calibrationFromProfile(nextProfile));
    applyCalibrationViewState(nextProfile);
  };

  const applyCalibrationViewState = (profile: Profile) => {
    const path = profile.calibration_video.path;
    if (path) {
      setVideoPath(path);
      setMetadata({
        path,
        fps: profile.calibration_video.fps ?? 0,
        frame_count: profile.calibration_video.frame_count ?? 0,
        width: profile.calibration_video.width ?? 0,
        height: profile.calibration_video.height ?? 0,
        duration_s:
          profile.calibration_video.fps && profile.calibration_video.frame_count
            ? profile.calibration_video.frame_count / profile.calibration_video.fps
            : 0,
      });
      const nextFrame = Math.max(0, profile.segments[0]?.start_frame_index ?? 0);
      frameIndexRef.current = nextFrame;
      setFrameIndex(nextFrame);
      setPreviewFrameIndex(nextFrame);
      previewFrameAtRef.current = performance.now();
    } else {
      setVideoPath("");
      setMetadata(null);
      frameIndexRef.current = 0;
      setFrameIndex(0);
      setPreviewFrameIndex(0);
      previewFrameAtRef.current = performance.now();
    }
  };

  const onSavedTemplate = (name: string) => {
    setTemplateName(name);
    setCalibrationBaseline(calibrationFromProfile(state.profile));
    setTemplateRefreshKey((key) => key + 1);
  };

  const startBlankTemplate = () => {
    const blankProfile = emptyProfile();
    state.reset(blankProfile);
    setTemplateName(null);
    setCalibrationBaseline(null);
    setDrawing(null);
    setActiveSlot("met");
    applyCalibrationViewState(blankProfile);
  };

  const discardCalibrationChanges = () => {
    if (!calibrationBaseline) return;
    const baseline = cloneCalibration(calibrationBaseline);
    state.setProfile((prev) => ({
      ...prev,
      calibration_video: baseline.calibration_video,
      segments: baseline.segments,
    }));
    applyCalibrationViewState({
      ...state.profile,
      calibration_video: baseline.calibration_video,
      segments: baseline.segments,
    });
  };

  const patchSegments = (updater: (segments: SegmentValue[]) => SegmentValue[]) => {
    state.setProfile((prev) => ({ ...prev, segments: updater(prev.segments) }));
  };

  const updateActiveBbox = (box: Box) => {
    patchSegments((segments) => {
      const next = [...segments];
      const segment = cloneSegment(next[activeSegmentIndex]);
      const field = segment.fields[activeSlot] ?? fieldFor(activeSlot);
      field.bbox_x1y1x2y2 = normalizeBox(box);
      segment.fields[activeSlot] = field;
      next[activeSegmentIndex] = segment;
      return next;
    });
    setActiveSlot(nextEnabledSlot(activeSegment.fields, activeSlot));
  };

  const toggleSlot = (name: CanonicalFieldName, enabled: boolean) => {
    if (!enabled && name === activeSlot) {
      const nextFields = { ...activeSegment.fields };
      delete nextFields[name];
      setActiveSlot(nextEnabledSlot(nextFields, activeSlot));
    }
    patchSegments((segments) => {
      const next = [...segments];
      const segment = cloneSegment(next[activeSegmentIndex]);
      if (enabled) segment.fields[name] = segment.fields[name] ?? fieldFor(name);
      else delete segment.fields[name];
      next[activeSegmentIndex] = segment;
      return next;
    });
  };

  const splitAtFrame = () => {
    if (!metadata) return;
    patchSegments((segments) => {
      const index = activeSegmentForFrame(segments, frameIndex);
      const segment = segments[index];
      if (!segment || frameIndex <= segment.start_frame_index || frameIndex >= segment.end_frame_index) {
        toast.error("Choose a frame inside a segment before splitting.");
        return segments;
      }
      const first = cloneSegment(segment);
      const second: SegmentValue = {
        id: "segment_new",
        start_frame_index: frameIndex,
        start_time_s: timeForFrame(frameIndex, metadata.fps),
        end_frame_index: segment.end_frame_index,
        end_time_s: segment.end_time_s,
        fields: defaultSegmentFields(),
      };
      first.end_frame_index = frameIndex;
      first.end_time_s = timeForFrame(frameIndex, metadata.fps);
      const next = [...segments.slice(0, index), first, second, ...segments.slice(index + 1)];
      return renumber(next);
    });
  };

  const mergeSplitAtBoundary = (rightSegmentIndex: number) => {
    if (!metadata) return;
    patchSegments((segments) => {
      if (rightSegmentIndex <= 0 || rightSegmentIndex >= segments.length) return segments;
      const left = cloneSegment(segments[rightSegmentIndex - 1]);
      const right = segments[rightSegmentIndex];
      left.end_frame_index = right.end_frame_index;
      left.end_time_s = right.end_time_s;
      const next = [
        ...segments.slice(0, rightSegmentIndex - 1),
        left,
        ...segments.slice(rightSegmentIndex + 1),
      ];
      return renumber(next);
    });
  };

  const setCropStart = () => {
    if (!metadata) return;
    patchSegments((segments) => {
      if (segments.length === 0) return segments;
      const next = [...segments];
      const first = cloneSegment(next[0]);
      first.start_frame_index = Math.min(frameIndex, first.end_frame_index - 1);
      first.start_time_s = timeForFrame(first.start_frame_index, metadata.fps);
      next[0] = first;
      return next;
    });
  };

  const setCropEnd = () => {
    if (!metadata) return;
    patchSegments((segments) => {
      if (segments.length === 0) return segments;
      const next = [...segments];
      const lastIndex = next.length - 1;
      const last = cloneSegment(next[lastIndex]);
      last.end_frame_index = Math.max(frameIndex + 1, last.start_frame_index + 1);
      last.end_frame_index = Math.min(last.end_frame_index, metadata.frame_count);
      last.end_time_s = timeForFrame(last.end_frame_index, metadata.fps);
      next[lastIndex] = last;
      return next;
    });
  };

  return (
    <>
      <PageHeader
        title="Calibrate segments"
        description="Scrub by frame, split the video into phases, and draw the active segment's enabled field boxes."
        badges={
          templateName ? (
            <Badge variant="outline" className="gap-1">
              loaded · <span className="font-mono">{templateName}</span>
            </Badge>
          ) : null
        }
        actions={
          <>
            {hasCalibrationChanges && (
              <Button size="sm" variant="outline" onClick={discardCalibrationChanges}>
                <RotateCcw className="mr-1 h-4 w-4" /> Discard changes
              </Button>
            )}
            <SaveAsTemplateButton
              profile={state.profile as ProfileDTO}
              isValid={state.isValid}
              currentName={templateName}
              onSaved={onSavedTemplate}
              variant="default"
              label="Save calibration as template"
              title="Save this calibration into a YAML template. Loaded templates keep their other settings unless you changed them."
              dialogTitle="Save calibration as template"
              dialogDescription={
                <>
                  Use the loaded name to update that template with the current calibration while
                  keeping the other profile settings currently in the form. Enter a new relative
                  path to create a template from this calibration plus the current profile settings,
                  which are defaults if you started blank.
                </>
              }
            />
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
                onStartBlank={startBlankTemplate}
                hasUnsavedChanges={hasUnsavedCalibrationTemplateChanges}
              />
            </Field>
            <Field label="Input video" required>
              <PathPicker value={videoPath} onChange={setVideoPath} mode="video" />
            </Field>
          </CardContent>
        </Card>

        {metadata && activeSegment && (
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
              <div>
                <CardTitle>{activeSegment.id}</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  frame {frameIndex} · {timeForFrame(frameIndex, metadata.fps).toFixed(3)}s ·
                  range [{activeSegment.start_frame_index}, {activeSegment.end_frame_index})
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={setCropStart}>
                  <Scissors className="mr-1 h-4 w-4" /> Crop start
                </Button>
                <Button size="sm" variant="outline" onClick={setCropEnd}>
                  <Scissors className="mr-1 h-4 w-4" /> Crop end
                </Button>
                <Button size="sm" onClick={splitAtFrame}>
                  <GitBranchPlus className="mr-1 h-4 w-4" /> Split here
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
                <div className="rounded-md border border-border/70 bg-black/40">
                  <CalibrationCanvas
                    videoPath={videoPath}
                    frameIndex={previewFrameIndex}
                    fields={activeSegment.fields}
                    activeSlot={activeSlot}
                    drawing={drawing}
                    onDrawing={setDrawing}
                    onCommit={updateActiveBbox}
                  />
                </div>
                <SlotPanel
                  segment={activeSegment}
                  activeSlot={activeSlot}
                  onActiveSlot={setActiveSlot}
                  onToggle={toggleSlot}
                />
              </div>
              <div className="space-y-3">
                <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-2">
                  <Button
                    size="icon"
                    variant="outline"
                    onPointerDown={(event) => {
                      event.currentTarget.setPointerCapture(event.pointerId);
                      startFrameHold(-1);
                    }}
                    onPointerUp={stopFrameHold}
                    onPointerCancel={stopFrameHold}
                    onPointerLeave={stopFrameHold}
                    aria-label="Previous frame"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <div className="min-w-0 space-y-2">
                    <input
                      type="range"
                      min={0}
                      max={Math.max(0, metadata.frame_count - 1)}
                      value={frameIndex}
                      onPointerDown={() => {
                        sliderDraggingRef.current = true;
                        stopFrameHold();
                      }}
                      onInput={(event) =>
                        setSelectedFrameIndex(
                          Number(event.currentTarget.value),
                          sliderDraggingRef.current ? "cadence" : "immediate",
                        )
                      }
                      onChange={(event) =>
                        setSelectedFrameIndex(
                          Number(event.currentTarget.value),
                          sliderDraggingRef.current ? "cadence" : "immediate",
                        )
                      }
                      onPointerUp={(event) => {
                        sliderDraggingRef.current = false;
                        setSelectedFrameIndex(Number(event.currentTarget.value), "immediate");
                      }}
                      onPointerCancel={(event) => {
                        sliderDraggingRef.current = false;
                        setSelectedFrameIndex(Number(event.currentTarget.value), "immediate");
                      }}
                      onTouchEnd={(event) => {
                        sliderDraggingRef.current = false;
                        setSelectedFrameIndex(Number(event.currentTarget.value), "immediate");
                      }}
                      className="w-full"
                    />
                    <SegmentRail
                      segments={state.profile.segments}
                      frameCount={metadata.frame_count}
                      onMergeSplit={mergeSplitAtBoundary}
                    />
                  </div>
                  <Button
                    size="icon"
                    variant="outline"
                    onPointerDown={(event) => {
                      event.currentTarget.setPointerCapture(event.pointerId);
                      startFrameHold(1);
                    }}
                    onPointerUp={stopFrameHold}
                    onPointerCancel={stopFrameHold}
                    onPointerLeave={stopFrameHold}
                    aria-label="Next frame"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {metadata && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle>Readiness</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">
              {state.isRunnable ? (
                <span className="text-success">Runnable profile</span>
              ) : (
                <span className="text-destructive">
                  Template saving is allowed for drafts. Run is blocked until every segment has a
                  valid MET box.
                </span>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}

function CalibrationCanvas({
  videoPath,
  frameIndex,
  fields,
  activeSlot,
  drawing,
  onDrawing,
  onCommit,
}: {
  videoPath: string;
  frameIndex: number;
  fields: SegmentValue["fields"];
  activeSlot: CanonicalFieldName;
  drawing: Box | null;
  onDrawing: (next: Box | null) => void;
  onCommit: (box: Box) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [isSlowLoading, setIsSlowLoading] = useState(false);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const pendingLoadStartedAtRef = useRef<number | null>(null);
  const activeEnabled = Boolean(fields[activeSlot]);

  useEffect(() => {
    if (!videoPath) {
      setImgUrl(null);
      setIsSlowLoading(false);
      pendingLoadStartedAtRef.current = null;
      return;
    }
    let cancelled = false;
    const now = performance.now();
    pendingLoadStartedAtRef.current = pendingLoadStartedAtRef.current ?? now;
    const loadingDelay = Math.max(
      0,
      FRAME_LOADING_DELAY_MS - (now - pendingLoadStartedAtRef.current),
    );
    const loadingTimer = window.setTimeout(() => {
      if (!cancelled) setIsSlowLoading(true);
    }, loadingDelay);
    const url = api.videoFrameByIndexUrl(videoPath, frameIndex, 1600);
    const image = new Image();
    image.onload = () => {
      if (!cancelled) {
        window.clearTimeout(loadingTimer);
        pendingLoadStartedAtRef.current = null;
        setImgUrl(url);
        setIsSlowLoading(false);
      }
    };
    image.onerror = () => {
      if (!cancelled) {
        window.clearTimeout(loadingTimer);
        pendingLoadStartedAtRef.current = null;
        setIsSlowLoading(false);
      }
    };
    image.src = url;
    return () => {
      cancelled = true;
      window.clearTimeout(loadingTimer);
    };
  }, [videoPath, frameIndex]);

  const pointFor = (event: React.PointerEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return {
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height,
    };
  };

  const onPointerDown = (event: React.PointerEvent) => {
    if (!activeEnabled) return;
    const point = pointFor(event);
    if (!point) return;
    startRef.current = point;
    onDrawing([point.x, point.y, point.x, point.y]);
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent) => {
    if (!startRef.current) return;
    const point = pointFor(event);
    if (!point) return;
    onDrawing([startRef.current.x, startRef.current.y, point.x, point.y]);
  };

  const onPointerUp = (event: React.PointerEvent) => {
    if (startRef.current && drawing) onCommit(drawing);
    onDrawing(null);
    startRef.current = null;
    const target = event.target as HTMLElement;
    if (target.hasPointerCapture?.(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative aspect-video w-full select-none"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      {imgUrl && (
        <img
          src={imgUrl}
          key={imgUrl}
          alt={`Frame ${frameIndex}`}
          className={cn(
            "pointer-events-none absolute inset-0 h-full w-full object-contain transition-opacity duration-150",
            isSlowLoading && "opacity-35 grayscale",
          )}
          draggable={false}
        />
      )}
      {isSlowLoading && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-muted/35">
          <LoaderCircle className="h-8 w-8 animate-spin text-primary drop-shadow" />
        </div>
      )}
      <svg className="pointer-events-none absolute inset-0 h-full w-full">
        {CANONICAL_FIELD_ORDER.map((name) => {
          const field = fields[name];
          const box = field?.bbox_x1y1x2y2;
          if (!box) return null;
          const [x0, y0, x1, y1] = box;
          const color = FIELD_COLORS[name];
          const active = name === activeSlot;
          return (
            <g key={name} opacity={active ? 1 : 0.72}>
              <rect
                x={`${x0 * 100}%`}
                y={`${y0 * 100}%`}
                width={`${(x1 - x0) * 100}%`}
                height={`${(y1 - y0) * 100}%`}
                fill={`${color}22`}
                stroke={color}
                strokeWidth={active ? 2 : 1.25}
              />
              <text
                x={`${x0 * 100}%`}
                y={`${y0 * 100}%`}
                dy={-4}
                fontSize={11}
                fill={color}
                style={{ paintOrder: "stroke", stroke: "#000", strokeWidth: 3 }}
              >
                {name}
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
            fill={`${FIELD_COLORS[activeSlot]}33`}
            stroke={FIELD_COLORS[activeSlot]}
            strokeWidth={2}
            strokeDasharray="4 2"
          />
        )}
      </svg>
      {!activeEnabled && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-sm text-muted-foreground">
          Enable the active slot before drawing
        </div>
      )}
    </div>
  );
}

function SlotPanel({
  segment,
  activeSlot,
  onActiveSlot,
  onToggle,
}: {
  segment: SegmentValue;
  activeSlot: CanonicalFieldName;
  onActiveSlot: (name: CanonicalFieldName) => void;
  onToggle: (name: CanonicalFieldName, enabled: boolean) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Crosshair className="h-4 w-4 text-primary" /> Field slots
      </div>
      {CANONICAL_FIELD_ORDER.map((name) => {
        const field = segment.fields[name];
        return (
          <button
            type="button"
            key={name}
            className={cn(
              "w-full rounded-md border bg-muted/20 p-3 text-left transition-colors",
              activeSlot === name ? "border-primary/60 bg-primary/10" : "border-border/60",
            )}
            onClick={() => onActiveSlot(name)}
          >
            <div className="flex items-center gap-2">
              <span
                className="h-3 w-3 rounded-sm"
                style={{ background: FIELD_COLORS[name] }}
              />
              <span className="flex-1 font-mono text-xs">{name}</span>
              <Switch
                checked={Boolean(field)}
                onClick={(event) => event.stopPropagation()}
                onCheckedChange={(checked) => onToggle(name, checked)}
              />
            </div>
            <div className="mt-2 font-mono text-[10px] text-muted-foreground">
              {field?.bbox_x1y1x2y2
                ? `[${field.bbox_x1y1x2y2.map((value) => value.toFixed(3)).join(", ")}]`
                : "bbox not set"}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function SegmentRail({
  segments,
  frameCount,
  onMergeSplit,
}: {
  segments: SegmentValue[];
  frameCount: number;
  onMergeSplit: (rightSegmentIndex: number) => void;
}) {
  return (
    <div className="relative h-14">
      <div className="absolute inset-x-0 top-0 h-8 rounded-md border border-border/70 bg-muted/20">
        {segments.map((segment) => {
          const left = (segment.start_frame_index / Math.max(1, frameCount)) * 100;
          const width =
            ((segment.end_frame_index - segment.start_frame_index) / Math.max(1, frameCount)) *
            100;
          return (
            <div
              key={segment.id}
              className="absolute top-1 h-6 rounded-sm bg-primary/30 px-1 text-[10px] leading-6 text-primary"
              style={{ left: `${left}%`, width: `${Math.max(width, 1)}%` }}
            >
              <span className="truncate">{segment.id}</span>
            </div>
          );
        })}
      </div>
      {segments.slice(1).map((segment, index) => {
        const rightSegmentIndex = index + 1;
        const leftSegment = segments[rightSegmentIndex - 1];
        const left = (segment.start_frame_index / Math.max(1, frameCount)) * 100;
        return (
          <button
            key={`${leftSegment.id}-${segment.id}`}
            type="button"
            className="absolute top-9 flex h-5 w-5 -translate-x-1/2 items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:border-destructive/70 hover:bg-destructive/15 hover:text-destructive"
            style={{ left: `${left}%` }}
            onClick={() => onMergeSplit(rightSegmentIndex)}
            aria-label={`Remove split between ${leftSegment.id} and ${segment.id}`}
            title={`Remove split between ${leftSegment.id} and ${segment.id}`}
          >
            <X className="h-3 w-3" />
          </button>
        );
      })}
    </div>
  );
}

function activeSegmentForFrame(segments: SegmentValue[], frameIndex: number): number {
  const index = segments.findIndex(
    (segment) => frameIndex >= segment.start_frame_index && frameIndex < segment.end_frame_index,
  );
  if (index >= 0) return index;
  if (segments.length === 0) return 0;
  if (frameIndex < segments[0].start_frame_index) return 0;
  return segments.length - 1;
}

function cloneSegment(segment: SegmentValue): SegmentValue {
  return {
    ...segment,
    fields: Object.fromEntries(
      Object.entries(segment.fields).map(([name, field]) => [
        name,
        {
          ...field,
          bbox_x1y1x2y2: field.bbox_x1y1x2y2
            ? ([...field.bbox_x1y1x2y2] as Box)
            : null,
        },
      ]),
    ),
  };
}

function calibrationFromProfile(profile: Profile): CalibrationBaseline {
  return {
    calibration_video: { ...profile.calibration_video },
    segments: profile.segments.map(cloneSegment),
  };
}

function cloneCalibration(calibration: CalibrationBaseline): CalibrationBaseline {
  return {
    calibration_video: { ...calibration.calibration_video },
    segments: calibration.segments.map(cloneSegment),
  };
}

function calibrationSignature(calibration: CalibrationBaseline): string {
  return JSON.stringify(calibration);
}

function renumber(segments: SegmentValue[]): SegmentValue[] {
  return segments.map((segment, index) => ({ ...segment, id: `segment_${index + 1}` }));
}

function normalizeBox(box: Box): Box {
  const x0 = Math.min(box[0], box[2]);
  const y0 = Math.min(box[1], box[3]);
  const x1 = Math.max(box[0], box[2]);
  const y1 = Math.max(box[1], box[3]);
  const clamp = (value: number) => Math.min(1, Math.max(0, value));
  return [clamp(x0), clamp(y0), clamp(x1), clamp(y1)];
}

function nextEnabledSlot(
  fields: SegmentValue["fields"],
  activeSlot: CanonicalFieldName,
): CanonicalFieldName {
  const start = CANONICAL_FIELD_ORDER.indexOf(activeSlot);
  for (let offset = 1; offset <= CANONICAL_FIELD_ORDER.length; offset += 1) {
    const candidate = CANONICAL_FIELD_ORDER[(start + offset) % CANONICAL_FIELD_ORDER.length];
    if (fields[candidate]) return candidate;
  }
  return activeSlot;
}

function timeForFrame(frameIndex: number, fps: number): number {
  return fps > 0 ? frameIndex / fps : 0;
}
