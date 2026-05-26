import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Crosshair,
  GitBranchPlus,
  LoaderCircle,
  MoreVertical,
  Plus,
  RotateCcw,
  Scissors,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { ApiError, ProfileDTO, QuantityDTO, VideoMetadata, api } from "@/lib/api";
import { useProfileForm } from "@/lib/profileForm";
import {
  CANONICAL_FIELD_DEFINITIONS,
  CANONICAL_FIELD_ORDER,
  CanonicalFieldName,
  FieldValue,
  Profile,
  QuantityValue,
  SegmentValue,
  customFieldValue,
  defaultSegmentFields,
  emptyProfile,
} from "@/lib/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { SaveAsTemplateButton, TemplatePicker } from "@/components/TemplatePicker";
import { PathPicker } from "@/components/PathPicker";
import { PageHeader } from "@/components/PageHeader";
import { Switch } from "@/components/ui/switch";
import { HelpTip } from "@/components/ui/tooltip";
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
const FIELD_BOX_FILL_ALPHA = 0.13;
const FIELD_DRAFT_FILL_ALPHA = 0.2;
const CALIBRATION_VIDEO_DEFAULT_ZOOM = 1;
const CALIBRATION_VIDEO_MIN_ZOOM = 1;
const CALIBRATION_VIDEO_MAX_ZOOM = 4;
const CALIBRATION_VIDEO_ZOOM_STEP = 0.25;

const FIELD_COLORS: Record<CanonicalFieldName, string> = {
  met: "#5cc4ff",
  stage1_velocity: "#ffae42",
  stage1_altitude: "#7eea7e",
  stage2_velocity: "#c879ff",
  stage2_altitude: "#ffd64d",
};

type FieldSlotName = string;
type QuantityOption = QuantityValue & Pick<QuantityDTO, "field_name" | "is_default">;
type VisibleFieldSlotsBySegment = FieldSlotName[][];

const CANONICAL_FIELD_LABELS: Record<CanonicalFieldName, string> = {
  met: "time",
  stage1_velocity: "stage1_velocity",
  stage1_altitude: "stage1_altitude",
  stage2_velocity: "stage2_velocity",
  stage2_altitude: "stage2_altitude",
};

function fieldFor(name: FieldSlotName, profile?: Profile): FieldValue {
  if (name.startsWith("custom_")) {
    const quantity = profile?.custom_telemetry_quantities.find((item) => `custom_${item.slug}` === name);
    if (quantity) return customFieldValue(quantity);
  }
  const def = CANONICAL_FIELD_DEFINITIONS[name as CanonicalFieldName];
  if (!def) return { kind: "custom", stage: null, quantity_id: null, bbox_x1y1x2y2: null };
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
  activeSlot: FieldSlotName;
  calibrationBaseline: CalibrationBaseline | null;
  visibleFieldSlotsBySegment: VisibleFieldSlotsBySegment;
};

export function createDefaultCalibratePageState(): CalibratePagePersistedState {
  const profile = emptyProfile();
  return {
    profile,
    templateName: null,
    templateRefreshKey: 0,
    videoPath: "",
    metadata: null,
    frameIndex: 0,
    previewFrameIndex: 0,
    activeSlot: "met",
    calibrationBaseline: null,
    visibleFieldSlotsBySegment: deriveVisibleFieldSlots(profile),
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
  const [activeSlot, setActiveSlot] = useState<FieldSlotName>(persistedState.activeSlot);
  const [calibrationBaseline, setCalibrationBaseline] =
    useState<CalibrationBaseline | null>(persistedState.calibrationBaseline);
  const [visibleFieldSlotsBySegment, setVisibleFieldSlotsBySegment] =
    useState<VisibleFieldSlotsBySegment>(
      persistedState.visibleFieldSlotsBySegment ?? deriveVisibleFieldSlots(persistedState.profile),
    );
  const [drawing, setDrawing] = useState<Box | null>(null);
  const [quantityDialogOpen, setQuantityDialogOpen] = useState(false);
  const [quantitySearch, setQuantitySearch] = useState("");
  const [quantityOptions, setQuantityOptions] = useState<QuantityOption[]>([]);
  const [quantityOptionsLoading, setQuantityOptionsLoading] = useState(false);
  const videoPanelRef = useRef<HTMLDivElement | null>(null);
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
  const activeVisibleSlots = useMemo(
    () =>
      activeSegment
        ? normalizeVisibleSlotsForSegment(
            visibleFieldSlotsBySegment[activeSegmentIndex],
            activeSegment,
            state.profile,
          )
        : [],
    [activeSegment, activeSegmentIndex, state.profile, visibleFieldSlotsBySegment],
  );
  const [slotPanelMaxHeight, setSlotPanelMaxHeight] = useState<number | null>(null);

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
  const runnableSummary = useMemo(
    () => summarizeRunnableErrors(state.profile, state.runnableErrors),
    [state.profile, state.runnableErrors],
  );

  useEffect(() => {
    if (activeVisibleSlots.length === 0 || activeVisibleSlots.includes(activeSlot)) return;
    setActiveSlot(nextVisibleSlot(activeVisibleSlots, activeSlot));
  }, [activeSlot, activeVisibleSlots]);

  useEffect(() => {
    const element = videoPanelRef.current;
    if (!element) {
      setSlotPanelMaxHeight(null);
      return;
    }
    const update = () => setSlotPanelMaxHeight(element.getBoundingClientRect().height);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [metadata, activeSegmentIndex]);

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
      visibleFieldSlotsBySegment,
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
    visibleFieldSlotsBySegment,
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
    if (!quantityDialogOpen) return;
    let cancelled = false;
    setQuantityOptionsLoading(true);
    api
      .quantities()
      .then(({ quantities }) => {
        if (cancelled) return;
        setQuantityOptions(
          mergeQuantityOptions(quantities, state.profile.custom_telemetry_quantities),
        );
      })
      .catch((err) => {
        if (!cancelled) toast.error((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setQuantityOptionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [quantityDialogOpen, state.profile.custom_telemetry_quantities]);

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
      const segmentFields = defaultFieldsForProfile(state.profile);
      const nextSegments = [
        {
          id: "segment_1",
          start_frame_index: 0,
          start_time_s: 0,
          end_frame_index: video.frame_count,
          end_time_s: timeForFrame(video.frame_count, video.fps),
          visible_fields: fieldSlotsForProfile(state.profile),
          fields: segmentFields,
        },
      ];
      setMetadata(video);
      setFrameIndex(0);
      frameIndexRef.current = 0;
      setPreviewFrameIndex(0);
      previewFrameAtRef.current = performance.now();
      setVisibleFieldSlotsBySegment(deriveVisibleFieldSlots({ ...state.profile, segments: nextSegments }));
      state.setProfile((prev) => ({
        ...prev,
        calibration_video: {
          path,
          fps: video.fps,
          frame_count: video.frame_count,
          width: video.width,
          height: video.height,
        },
        segments: nextSegments,
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
    setVisibleFieldSlotsBySegment(deriveVisibleFieldSlots(nextProfile));
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
    setVisibleFieldSlotsBySegment(deriveVisibleFieldSlots(blankProfile));
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
    setVisibleFieldSlotsBySegment(
      deriveVisibleFieldSlots({
        ...state.profile,
        calibration_video: baseline.calibration_video,
        segments: baseline.segments,
      }),
    );
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
      const field = segment.fields[activeSlot] ?? fieldFor(activeSlot, state.profile);
      field.bbox_x1y1x2y2 = normalizeBox(box);
      segment.fields[activeSlot] = field;
      next[activeSegmentIndex] = segment;
      return next;
    });
    setActiveSlot(nextEnabledSlot(activeSegment.fields, activeSlot));
  };

  const toggleSlot = (name: FieldSlotName, enabled: boolean) => {
    patchSegments((segments) => {
      const next = [...segments];
      const segment = cloneSegment(next[activeSegmentIndex]);
      if (enabled) {
        if (!segment.visible_fields.includes(name)) segment.visible_fields.push(name);
        segment.fields[name] = segment.fields[name] ?? fieldFor(name, state.profile);
      } else {
        delete segment.fields[name];
      }
      next[activeSegmentIndex] = segment;
      return next;
    });
  };

  const removeQuantityFromCurrentSegment = (name: FieldSlotName) => {
    const nextVisibleSlots = activeVisibleSlots.filter((slotName) => slotName !== name);
    if (name === activeSlot) setActiveSlot(nextVisibleSlot(nextVisibleSlots, activeSlot));
    setVisibleFieldSlotsBySegment((previous) =>
      state.profile.segments.map((segment, index) =>
        index === activeSegmentIndex
          ? normalizeVisibleSlotsForSegment(previous[index], segment, state.profile).filter(
              (slotName) => slotName !== name,
            )
          : normalizeVisibleSlotsForSegment(previous[index], segment, state.profile),
      ),
    );
    patchSegments((segments) => {
      const next = [...segments];
      const segment = cloneSegment(next[activeSegmentIndex]);
      delete segment.fields[name];
      segment.visible_fields = segment.visible_fields.filter((slotName) => slotName !== name);
      next[activeSegmentIndex] = segment;
      return next;
    });
  };

  const removeQuantityFromAllSegments = (name: FieldSlotName) => {
    const nextVisibleSlots = activeVisibleSlots.filter((slotName) => slotName !== name);
    if (name === activeSlot) setActiveSlot(nextVisibleSlot(nextVisibleSlots, activeSlot));
    setVisibleFieldSlotsBySegment((previous) =>
      state.profile.segments.map((segment, index) =>
        normalizeVisibleSlotsForSegment(previous[index], segment, state.profile).filter(
          (slotName) => slotName !== name,
        ),
      ),
    );
    patchSegments((segments) =>
      segments.map((segment) => {
        if (!(name in segment.fields) && !segment.visible_fields.includes(name)) return segment;
        const next = cloneSegment(segment);
        delete next.fields[name];
        next.visible_fields = next.visible_fields.filter((slotName) => slotName !== name);
        return next;
      }),
    );
  };

  const openQuantityDialog = () => {
    setQuantitySearch("");
    setQuantityDialogOpen(true);
  };

  const addQuantityToCurrentSegment = (quantity: QuantityOption) => {
    const targetSegment = state.profile.segments[activeSegmentIndex];
    if (!targetSegment) return;

    const fieldName = fieldNameForQuantity(quantity);
    const isCanonical = isCanonicalFieldName(fieldName);
    const profileQuantity = toProfileQuantity(quantity);
    const nextCustomQuantities =
      isCanonical || state.profile.custom_telemetry_quantities.some((current) => current.id === quantity.id)
        ? state.profile.custom_telemetry_quantities
        : [...state.profile.custom_telemetry_quantities, profileQuantity];
    const profileWithQuantity = { ...state.profile, custom_telemetry_quantities: nextCustomQuantities };
    const resolvedQuantity =
      nextCustomQuantities.find((current) => current.id === quantity.id) ?? profileQuantity;
    const nextSegment = cloneSegment(targetSegment);

    nextSegment.visible_fields = addVisibleSlot(
      normalizeVisibleSlotsForSegment(
        visibleFieldSlotsBySegment[activeSegmentIndex],
        targetSegment,
        state.profile,
      ),
      fieldName,
      nextCustomQuantities,
    );
    nextSegment.fields[fieldName] =
      nextSegment.fields[fieldName] ??
      (isCanonical ? fieldFor(fieldName, profileWithQuantity) : customFieldValue(resolvedQuantity));

    setVisibleFieldSlotsBySegment((previous) =>
      state.profile.segments.map((segment, index) => {
        const currentSlots = normalizeVisibleSlotsForSegment(previous[index], segment, state.profile);
        return index === activeSegmentIndex
          ? addVisibleSlot(currentSlots, fieldName, nextCustomQuantities)
          : currentSlots;
      }),
    );
    state.setProfile({
      ...profileWithQuantity,
      segments: state.profile.segments.map((segment, index) =>
        index === activeSegmentIndex ? nextSegment : segment,
      ),
    });
    setActiveSlot(fieldName);
    setQuantityDialogOpen(false);
  };

  const splitAtFrame = () => {
    if (!metadata) return;
    const segments = state.profile.segments;
    const index = activeSegmentForFrame(segments, frameIndex);
    const segment = segments[index];
    if (!segment || frameIndex <= segment.start_frame_index || frameIndex >= segment.end_frame_index) {
      toast.error("Choose a frame inside a segment before splitting.");
      return;
    }
    const first = cloneSegment(segment);
    const second = cloneSegment(segment);
    first.end_frame_index = frameIndex;
    first.end_time_s = timeForFrame(frameIndex, metadata.fps);
    second.id = "segment_new";
    second.start_frame_index = frameIndex;
    second.start_time_s = timeForFrame(frameIndex, metadata.fps);
    const nextSegments = renumber([
      ...segments.slice(0, index),
      first,
      second,
      ...segments.slice(index + 1),
    ]);
    const sourceVisibleSlots = normalizeVisibleSlotsForSegment(
      visibleFieldSlotsBySegment[index],
      segment,
      state.profile,
    );
    first.visible_fields = sourceVisibleSlots;
    second.visible_fields = [...sourceVisibleSlots];
    setVisibleFieldSlotsBySegment([
      ...visibleFieldSlotsBySegment.slice(0, index),
      sourceVisibleSlots,
      [...sourceVisibleSlots],
      ...visibleFieldSlotsBySegment.slice(index + 1),
    ]);
    state.setProfile((prev) => ({ ...prev, segments: nextSegments }));
  };

  const mergeSplitAtBoundary = (rightSegmentIndex: number) => {
    if (!metadata) return;
    const segments = state.profile.segments;
    if (rightSegmentIndex <= 0 || rightSegmentIndex >= segments.length) return;
    const left = cloneSegment(segments[rightSegmentIndex - 1]);
    const right = segments[rightSegmentIndex];
    left.end_frame_index = right.end_frame_index;
    left.end_time_s = right.end_time_s;
    const nextSegments = renumber([
      ...segments.slice(0, rightSegmentIndex - 1),
      left,
      ...segments.slice(rightSegmentIndex + 1),
    ]);
    const leftVisibleSlots = normalizeVisibleSlotsForSegment(
      visibleFieldSlotsBySegment[rightSegmentIndex - 1],
      segments[rightSegmentIndex - 1],
      state.profile,
    );
    const rightVisibleSlots = normalizeVisibleSlotsForSegment(
      visibleFieldSlotsBySegment[rightSegmentIndex],
      right,
      state.profile,
    );
    left.visible_fields = mergeVisibleSlots(
      leftVisibleSlots,
      rightVisibleSlots,
      state.profile.custom_telemetry_quantities,
    );
    setVisibleFieldSlotsBySegment([
      ...visibleFieldSlotsBySegment.slice(0, rightSegmentIndex - 1),
      left.visible_fields,
      ...visibleFieldSlotsBySegment.slice(rightSegmentIndex + 1),
    ]);
    state.setProfile((prev) => ({ ...prev, segments: nextSegments }));
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
              label="Save as template"
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
            <CardHeader className="flex flex-col gap-3 space-y-0 pb-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <CardTitle>{activeSegment.id}</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  frame {frameIndex} · {timeForFrame(frameIndex, metadata.fps).toFixed(3)}s ·
                  range [{activeSegment.start_frame_index}, {activeSegment.end_frame_index})
                </p>
              </div>
              <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
                <Button size="sm" variant="outline" onClick={setCropStart}>
                  <Scissors className="mr-1 h-4 w-4" /> Crop start
                </Button>
                <Button size="sm" variant="outline" onClick={setCropEnd}>
                  <Scissors className="mr-1 h-4 w-4" /> Crop end
                </Button>
                <Button size="sm" onClick={splitAtFrame}>
                  <GitBranchPlus className="mr-1 h-4 w-4" /> Split here
                </Button>
                <Button size="sm" variant="outline" onClick={openQuantityDialog}>
                  <Plus className="mr-1 h-4 w-4" /> Add quantity
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
                <div className="min-w-0 space-y-3">
                  <div ref={videoPanelRef} className="rounded-md border border-border/70 bg-black/40">
                    <CalibrationCanvas
                      videoPath={videoPath}
                      frameIndex={previewFrameIndex}
                      fields={activeSegment.fields}
                      visibleSlots={activeVisibleSlots}
                      activeSlot={activeSlot}
                      customQuantities={state.profile.custom_telemetry_quantities}
                      drawing={drawing}
                      onDrawing={setDrawing}
                      onCommit={updateActiveBbox}
                    />
                  </div>
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
                <SlotPanel
                  segment={activeSegment}
                  visibleSlots={activeVisibleSlots}
                  activeSlot={activeSlot}
                  customQuantities={state.profile.custom_telemetry_quantities}
                  maxHeight={slotPanelMaxHeight}
                  onActiveSlot={setActiveSlot}
                  onToggle={toggleSlot}
                  onRemoveFromCurrentSegment={removeQuantityFromCurrentSegment}
                  onRemoveFromAllSegments={removeQuantityFromAllSegments}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {metadata && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle>Readiness</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {state.isRunnable ? (
                <span className="text-success">Runnable profile</span>
              ) : (
                <>
                  <p className="text-destructive">
                    Template saving is allowed for drafts. Run is blocked by{" "}
                    {runnableSummary.issueCount} issue
                    {runnableSummary.issueCount === 1 ? "" : "s"} across{" "}
                    {runnableSummary.affectedSegmentCount} segment
                    {runnableSummary.affectedSegmentCount === 1 ? "" : "s"}.
                  </p>
                  {runnableSummary.segmentIssues.length > 0 && (
                    <ul className="space-y-2">
                      {runnableSummary.segmentIssues.map((segmentIssue) => (
                        <li
                          key={segmentIssue.segmentId}
                          className="rounded-md border border-border/70 bg-muted/15 px-3 py-2"
                        >
                          <span className="font-mono text-foreground">{segmentIssue.segmentId}</span>
                          :{" "}
                          <span className="text-muted-foreground">
                            {segmentIssue.issues.join(" · ")}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {runnableSummary.generalIssues.length > 0 && (
                    <ul className="space-y-2">
                      {runnableSummary.generalIssues.map((issue) => (
                        <li
                          key={issue}
                          className="rounded-md border border-border/70 bg-muted/15 px-3 py-2 text-muted-foreground"
                        >
                          {issue}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        )}
      </div>
      <AddQuantityDialog
        open={quantityDialogOpen}
        onOpenChange={setQuantityDialogOpen}
        quantities={quantityOptions}
        loading={quantityOptionsLoading}
        search={quantitySearch}
        onSearchChange={setQuantitySearch}
        profile={state.profile}
        activeSegmentIndex={activeSegmentIndex}
        visibleFieldSlotsBySegment={visibleFieldSlotsBySegment}
        onSelect={addQuantityToCurrentSegment}
      />
    </>
  );
}

function AddQuantityDialog({
  open,
  onOpenChange,
  quantities,
  loading,
  search,
  onSearchChange,
  profile,
  activeSegmentIndex,
  visibleFieldSlotsBySegment,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quantities: QuantityOption[];
  loading: boolean;
  search: string;
  onSearchChange: (value: string) => void;
  profile: Profile;
  activeSegmentIndex: number;
  visibleFieldSlotsBySegment: VisibleFieldSlotsBySegment;
  onSelect: (quantity: QuantityOption) => void;
}) {
  const filtered = useMemo(() => filterQuantities(quantities, search), [quantities, search]);
  const activeSegment = profile.segments[activeSegmentIndex];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100vh-3rem)] max-w-3xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="px-6 pb-4 pt-6">
          <DialogTitle>Add quantity</DialogTitle>
          <DialogDescription>
            Choose a quantity to enable in the current segment. Any later split created from this
            segment inherits the same visible quantities by default.
          </DialogDescription>
        </DialogHeader>
        <div className="border-y border-border/70 bg-muted/10 px-6 py-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search name, dimensionality, unit, or field name"
              className="pl-9"
              autoFocus
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center gap-2 rounded-md border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Loading quantities
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-md border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
              {quantities.length === 0
                ? "No quantities are defined in the library yet."
                : "No quantities match this search."}
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map((quantity) => {
                const fieldName = fieldNameForQuantity(quantity);
                const visibleInCurrentSegment = activeSegment
                  ? normalizeVisibleSlotsForSegment(
                      visibleFieldSlotsBySegment[activeSegmentIndex],
                      activeSegment,
                      profile,
                    ).includes(fieldName)
                  : false;
                const visibleSegments = profile.segments.filter((segment, index) =>
                  normalizeVisibleSlotsForSegment(
                    visibleFieldSlotsBySegment[index],
                    segment,
                    profile,
                  ).includes(fieldName),
                ).length;
                return (
                  <button
                    type="button"
                    key={quantity.id}
                    disabled={visibleInCurrentSegment}
                    onClick={() => onSelect(quantity)}
                    className={cn(
                      "group w-full rounded-lg border p-4 text-left transition-colors",
                      visibleInCurrentSegment
                        ? "cursor-default border-border/50 bg-muted/10 opacity-70"
                        : "border-border/70 bg-muted/20 hover:border-primary/60 hover:bg-primary/10",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-foreground">
                          {quantity.name}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-xs">
                          <span className="rounded-md border border-border/70 px-2 py-0.5 text-muted-foreground">
                            {quantity.dimensionality}
                          </span>
                          <span className="rounded-md border border-border/70 px-2 py-0.5 text-primary">
                            {quantity.display_unit}
                          </span>
                          <span className="rounded-md border border-border/70 px-2 py-0.5 text-muted-foreground">
                            {displayFieldName(fieldName)}
                          </span>
                        </div>
                      </div>
                      <Badge variant="outline" className="shrink-0 normal-case tracking-normal">
                        {visibleInCurrentSegment
                          ? `already in ${activeSegment?.id ?? "current segment"}`
                          : visibleSegments > 0
                            ? `${visibleSegments}/${profile.segments.length} segments`
                            : "not visible"}
                      </Badge>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <DialogFooter className="border-t border-border/70 bg-card/95 px-6 py-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CalibrationCanvas({
  videoPath,
  frameIndex,
  fields,
  visibleSlots,
  activeSlot,
  customQuantities,
  drawing,
  onDrawing,
  onCommit,
}: {
  videoPath: string;
  frameIndex: number;
  fields: SegmentValue["fields"];
  visibleSlots: FieldSlotName[];
  activeSlot: FieldSlotName;
  customQuantities: QuantityValue[];
  drawing: Box | null;
  onDrawing: (next: Box | null) => void;
  onCommit: (box: Box) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [isSlowLoading, setIsSlowLoading] = useState(false);
  const [zoom, setZoom] = useState(CALIBRATION_VIDEO_DEFAULT_ZOOM);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const captureRef = useRef<{ element: HTMLElement; pointerId: number } | null>(null);
  const pendingLoadStartedAtRef = useRef<number | null>(null);
  const activeEnabled = Boolean(fields[activeSlot]);

  const clampVideoZoom = (value: number) => {
    const clamped = Math.min(CALIBRATION_VIDEO_MAX_ZOOM, Math.max(CALIBRATION_VIDEO_MIN_ZOOM, value));
    return Math.round(clamped * 100) / 100;
  };

  const shiftVideoZoom = (delta: number) => {
    setZoom((currentZoom) => clampVideoZoom(currentZoom + delta));
  };

  const resetVideoZoom = () => {
    setZoom(CALIBRATION_VIDEO_DEFAULT_ZOOM);
  };

  const zoomButtonClassName =
    "h-8 w-8 border border-border/70 bg-background/65 text-muted-foreground shadow-sm backdrop-blur-md backdrop-saturate-150 hover:bg-accent/20 hover:text-foreground supports-[backdrop-filter]:bg-background/55";

  const cancelDrawing = useCallback(() => {
    const capture = captureRef.current;
    if (capture?.element.hasPointerCapture?.(capture.pointerId)) {
      capture.element.releasePointerCapture(capture.pointerId);
    }
    captureRef.current = null;
    startRef.current = null;
    onDrawing(null);
  }, [onDrawing]);

  useEffect(() => {
    if (!drawing) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      cancelDrawing();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [cancelDrawing, drawing]);

  useEffect(() => {
    setZoom(CALIBRATION_VIDEO_DEFAULT_ZOOM);
  }, [videoPath]);

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
    const target = event.currentTarget as HTMLElement;
    target.setPointerCapture(event.pointerId);
    captureRef.current = { element: target, pointerId: event.pointerId };
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
    const capture = captureRef.current;
    if (capture?.element.hasPointerCapture?.(capture.pointerId)) {
      capture.element.releasePointerCapture(capture.pointerId);
    }
    captureRef.current = null;
  };

  return (
    <div className="calibration-video relative aspect-video w-full select-none overflow-hidden">
      <div className="calibration-video-toolbar">
        <div className="flex items-center gap-1" role="group" aria-label="Video zoom controls">
          <HelpTip text="Zoom out video">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={zoomButtonClassName}
              onClick={() => shiftVideoZoom(-CALIBRATION_VIDEO_ZOOM_STEP)}
              disabled={zoom <= CALIBRATION_VIDEO_MIN_ZOOM}
            >
              <ZoomOut className="h-4 w-4" aria-hidden="true" />
              <span className="sr-only">Zoom out video</span>
            </Button>
          </HelpTip>
          <HelpTip text="Reset video zoom">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={zoomButtonClassName}
              onClick={resetVideoZoom}
              disabled={Math.abs(zoom - CALIBRATION_VIDEO_DEFAULT_ZOOM) < 0.01}
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              <span className="sr-only">Reset video zoom</span>
            </Button>
          </HelpTip>
          <HelpTip text="Zoom in video">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={zoomButtonClassName}
              onClick={() => shiftVideoZoom(CALIBRATION_VIDEO_ZOOM_STEP)}
              disabled={zoom >= CALIBRATION_VIDEO_MAX_ZOOM}
            >
              <ZoomIn className="h-4 w-4" aria-hidden="true" />
              <span className="sr-only">Zoom in video</span>
            </Button>
          </HelpTip>
        </div>
      </div>
      <div className="h-full w-full overflow-auto">
        <div
          ref={containerRef}
          className="relative aspect-video min-w-full"
          style={{ width: `${zoom * 100}%` }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={cancelDrawing}
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
            {visibleSlots.map((name) => {
              const field = fields[name];
              const box = field?.bbox_x1y1x2y2;
              if (!box) return null;
              const [x0, y0, x1, y1] = box;
              const color = colorForField(name);
              const active = name === activeSlot;
              return (
                <g key={name} opacity={active ? 1 : 0.72}>
                  <rect
                    x={`${x0 * 100}%`}
                    y={`${y0 * 100}%`}
                    width={`${(x1 - x0) * 100}%`}
                    height={`${(y1 - y0) * 100}%`}
                    fill={colorWithAlpha(color, FIELD_BOX_FILL_ALPHA)}
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
                    {labelForField(name, customQuantities)}
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
                fill={colorWithAlpha(colorForField(activeSlot), FIELD_DRAFT_FILL_ALPHA)}
                stroke={colorForField(activeSlot)}
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
      </div>
    </div>
  );
}

function SlotPanel({
  segment,
  visibleSlots,
  activeSlot,
  customQuantities,
  maxHeight,
  onActiveSlot,
  onToggle,
  onRemoveFromCurrentSegment,
  onRemoveFromAllSegments,
}: {
  segment: SegmentValue;
  visibleSlots: FieldSlotName[];
  activeSlot: FieldSlotName;
  customQuantities: QuantityValue[];
  maxHeight: number | null;
  onActiveSlot: (name: FieldSlotName) => void;
  onToggle: (name: FieldSlotName, enabled: boolean) => void;
  onRemoveFromCurrentSegment: (name: FieldSlotName) => void;
  onRemoveFromAllSegments: (name: FieldSlotName) => void;
}) {
  const [menu, setMenu] = useState<{ fieldName: FieldSlotName; x: number; y: number } | null>(null);

  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setMenu(null);
    };
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [menu]);

  const openMenu = (fieldName: FieldSlotName, x: number, y: number) => {
    const width = 240;
    const height = 112;
    setMenu({
      fieldName,
      x: Math.min(x, Math.max(8, window.innerWidth - width - 8)),
      y: Math.min(y, Math.max(8, window.innerHeight - height - 8)),
    });
  };

  const style: CSSProperties | undefined = maxHeight
    ? { maxHeight: `${Math.round(maxHeight)}px` }
    : undefined;

  return (
    <div className="relative space-y-2 overflow-y-auto pr-1" style={style}>
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Crosshair className="h-4 w-4 text-primary" /> Field slots
      </div>
      {visibleSlots.map((name) => {
        const field = segment.fields[name];
        const label = labelForField(name, customQuantities);
        return (
          <div
            key={name}
            role="button"
            tabIndex={0}
            className={cn(
              "relative min-h-24 w-full cursor-pointer rounded-md border bg-muted/20 p-3 text-left transition-[background-color,border-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              activeSlot === name
                ? "border-primary/70 bg-primary/10 shadow-[0_0_0_1px_hsl(var(--primary)/0.18)] hover:bg-primary/[0.13]"
                : "border-border/60 hover:border-primary/35 hover:bg-primary/[0.045]",
            )}
            onClick={() => onActiveSlot(name)}
            onContextMenu={(event) => {
              event.preventDefault();
              openMenu(name, event.clientX, event.clientY);
            }}
            onKeyDown={(event) => {
              if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              onActiveSlot(name);
            }}
          >
            <div className="flex items-center gap-2">
              <span
                className="h-3 w-3 rounded-sm"
                style={{ background: colorForField(name) }}
              />
              <span className="flex-1 truncate font-mono text-xs" title={label}>{label}</span>
              <Switch
                checked={Boolean(field)}
                className="shrink-0"
                onClick={(event) => event.stopPropagation()}
                onCheckedChange={(checked) => onToggle(name, checked)}
                aria-label={`Enable ${label}`}
              />
            </div>
            <button
              type="button"
              className="absolute bottom-3 right-3 inline-flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent/15 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`Open actions for ${label}`}
              aria-haspopup="menu"
              aria-expanded={menu?.fieldName === name}
              onClick={(event) => {
                event.stopPropagation();
                const rect = event.currentTarget.getBoundingClientRect();
                openMenu(name, rect.right, rect.bottom + 4);
              }}
            >
              <MoreVertical className="h-4 w-4" />
            </button>
            <div className="mt-2 pr-8 font-mono text-[10px] text-muted-foreground">
              {field?.bbox_x1y1x2y2
                ? `[${field.bbox_x1y1x2y2.map((value) => value.toFixed(3)).join(", ")}]`
                : "bbox not set"}
            </div>
          </div>
        );
      })}
      {menu && (
        <div
          role="menu"
          className="fixed z-50 w-56 overflow-hidden rounded-lg border border-border/70 bg-popover p-1 text-sm shadow-lg"
          style={{ left: menu.x, top: menu.y }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center rounded-md px-3 py-2 text-left text-foreground hover:bg-accent/15"
            onClick={() => {
              onRemoveFromCurrentSegment(menu.fieldName);
              setMenu(null);
            }}
          >
            Remove from current segment
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center rounded-md px-3 py-2 text-left text-destructive hover:bg-destructive/15"
            onClick={() => {
              onRemoveFromAllSegments(menu.fieldName);
              setMenu(null);
            }}
          >
            Remove from all segments
          </button>
        </div>
      )}
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
    visible_fields: [...segment.visible_fields],
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
  activeSlot: FieldSlotName,
): FieldSlotName {
  const names = Object.keys(fields);
  if (names.length === 0) return activeSlot;
  const start = Math.max(0, names.indexOf(activeSlot));
  for (let offset = 1; offset <= names.length; offset += 1) {
    const candidate = names[(start + offset) % names.length];
    if (fields[candidate]) return candidate;
  }
  return activeSlot;
}

function timeForFrame(frameIndex: number, fps: number): number {
  return fps > 0 ? frameIndex / fps : 0;
}

function defaultFieldsForProfile(profile: Profile): Record<string, FieldValue> {
  return {
    ...defaultSegmentFields(),
    ...Object.fromEntries(
      profile.custom_telemetry_quantities.map((quantity) => [
        `custom_${quantity.slug}`,
        customFieldValue(quantity),
      ]),
    ),
  };
}

function mergeQuantityOptions(
  library: QuantityDTO[],
  profileQuantities: QuantityValue[],
): QuantityOption[] {
  const byId = new Map<string, QuantityOption>();
  [...library.map(normalizeQuantityOption), ...profileQuantities.map(normalizeQuantityOption)].forEach((quantity) => {
    byId.set(quantity.id, quantity);
  });
  return Array.from(byId.values()).sort((left, right) => left.name.localeCompare(right.name));
}

function filterQuantities(quantities: QuantityOption[], search: string): QuantityOption[] {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return quantities;
  return quantities.filter((quantity) => {
    const fieldName = fieldNameForQuantity(quantity);
    return [quantity.name, quantity.dimensionality, quantity.display_unit, fieldName].some((value) =>
      value.toLowerCase().includes(normalized),
    );
  });
}

function normalizeQuantityOption(quantity: QuantityDTO | QuantityValue): QuantityOption {
  return {
    ...quantity,
    description: quantity.description ?? "",
    unit_aliases: quantity.unit_aliases ?? {},
    field_name: "field_name" in quantity ? quantity.field_name : undefined,
    is_default: "is_default" in quantity ? quantity.is_default : undefined,
  };
}

function toProfileQuantity(quantity: QuantityOption): QuantityValue {
  return {
    id: quantity.id,
    name: quantity.name,
    slug: quantity.slug,
    dimensionality: quantity.dimensionality,
    display_unit: quantity.display_unit,
    description: quantity.description,
    unit_aliases: quantity.unit_aliases,
  };
}

function fieldNameForQuantity(quantity: Pick<QuantityOption, "field_name" | "slug">): FieldSlotName {
  return quantity.field_name ?? `custom_${quantity.slug}`;
}

function isCanonicalFieldName(name: FieldSlotName): name is CanonicalFieldName {
  return CANONICAL_FIELD_ORDER.includes(name as CanonicalFieldName);
}

function displayFieldName(name: FieldSlotName): string {
  return isCanonicalFieldName(name) ? CANONICAL_FIELD_LABELS[name] : name;
}

function labelForField(name: FieldSlotName, customQuantities: QuantityValue[]): string {
  const quantity = customQuantities.find((item) => `custom_${item.slug}` === name);
  if (quantity) return quantity.name;
  return displayFieldName(name);
}

function deriveVisibleFieldSlots(profile: Profile): VisibleFieldSlotsBySegment {
  return profile.segments.map((segment) =>
    normalizeVisibleSlotsForSegment(undefined, segment, profile),
  );
}

function normalizeVisibleSlotsForSegment(
  slots: FieldSlotName[] | undefined,
  segment: SegmentValue,
  profile: Profile,
): FieldSlotName[] {
  const known = new Set([...fieldSlotsForProfile(profile), ...Object.keys(segment.fields)]);
  const source = slots ?? (segment.visible_fields.length > 0 ? segment.visible_fields : fieldSlotsForProfile(profile));
  return orderFieldSlots(
    [
      ...source.filter((name) => known.has(name)),
      ...Object.keys(segment.fields).filter((name) => known.has(name)),
    ],
    profile.custom_telemetry_quantities,
  );
}

function fieldSlotsForProfile(profile: Profile): FieldSlotName[] {
  return [
    ...CANONICAL_FIELD_ORDER,
    ...profile.custom_telemetry_quantities.map((quantity) => `custom_${quantity.slug}`),
  ];
}

function addVisibleSlot(
  slots: FieldSlotName[],
  fieldName: FieldSlotName,
  customQuantities: QuantityValue[],
): FieldSlotName[] {
  return orderFieldSlots([...slots, fieldName], customQuantities);
}

function mergeVisibleSlots(
  left: FieldSlotName[],
  right: FieldSlotName[],
  customQuantities: QuantityValue[],
): FieldSlotName[] {
  return orderFieldSlots([...left, ...right], customQuantities);
}

function nextVisibleSlot(slots: FieldSlotName[], activeSlot: FieldSlotName): FieldSlotName {
  if (slots.length === 0) return activeSlot;
  const start = Math.max(0, slots.indexOf(activeSlot));
  return slots[(start + 1) % slots.length];
}

function orderFieldSlots(
  names: FieldSlotName[],
  customQuantities: QuantityValue[],
): FieldSlotName[] {
  const unique = new Set(names);
  const ordered = [
    ...CANONICAL_FIELD_ORDER.filter((name) => unique.has(name)),
    ...customQuantities
      .map((quantity) => `custom_${quantity.slug}`)
      .filter((name) => unique.has(name)),
  ];
  const included = new Set(ordered);
  return [...ordered, ...names.filter((name) => !included.has(name))].filter(
    (name, index, array) => array.indexOf(name) === index,
  );
}

function summarizeRunnableErrors(
  profile: Profile,
  runnableErrors: Record<string, string>,
): {
  issueCount: number;
  affectedSegmentCount: number;
  segmentIssues: { segmentId: string; issues: string[] }[];
  generalIssues: string[];
} {
  const segmentIssues = new Map<number, Set<string>>();
  const generalIssues = new Set<string>();

  for (const [key, message] of Object.entries(runnableErrors)) {
    const path = key.split(".");
    if (path[0] !== "segments" || path[1] === undefined) {
      generalIssues.add(message);
      continue;
    }
    const segmentIndex = Number(path[1]);
    if (!Number.isInteger(segmentIndex)) {
      generalIssues.add(message);
      continue;
    }
    const segment = profile.segments[segmentIndex];
    if (!segment) {
      generalIssues.add(message);
      continue;
    }
    const summary = describeRunnableIssue(profile, path.slice(2), message);
    const issues = segmentIssues.get(segmentIndex) ?? new Set<string>();
    issues.add(summary);
    segmentIssues.set(segmentIndex, issues);
  }

  const orderedSegmentIssues = Array.from(segmentIssues.entries())
    .sort(([left], [right]) => left - right)
    .map(([segmentIndex, issues]) => ({
      segmentId: profile.segments[segmentIndex]?.id ?? `segment_${segmentIndex + 1}`,
      issues: Array.from(issues),
    }));

  return {
    issueCount: Object.keys(runnableErrors).length,
    affectedSegmentCount: orderedSegmentIssues.length,
    segmentIssues: orderedSegmentIssues,
    generalIssues: Array.from(generalIssues),
  };
}

function describeRunnableIssue(profile: Profile, path: string[], message: string): string {
  if (path[0] === "fields" && path[1]) {
    return `${labelForField(path[1], profile.custom_telemetry_quantities)}: ${message}`;
  }
  if (
    path[0] === "start_frame_index" ||
    path[0] === "end_frame_index" ||
    path[0] === "start_time_s" ||
    path[0] === "end_time_s"
  ) {
    return `segment range: ${message}`;
  }
  if (path[0] === "visible_fields") {
    return `visible fields: ${message}`;
  }
  return message;
}

function colorForField(name: FieldSlotName): string {
  if (name in FIELD_COLORS) return FIELD_COLORS[name as CanonicalFieldName];
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const hue = hash % 360;
  return `hsl(${hue} 85% 62%)`;
}

function colorWithAlpha(color: string, alpha: number): string {
  if (color.startsWith("#")) {
    const channel = Math.round(alpha * 255).toString(16).padStart(2, "0");
    return `${color}${channel}`;
  }
  if (color.startsWith("hsl(")) {
    return color.replace(/\)$/, ` / ${alpha})`);
  }
  return color;
}
