import { type Dispatch, type SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import {
  Edit3,
  Film,
  FolderOpen,
  LogOut,
  RefreshCw,
  RotateCcw,
  Save,
  Trash2,
  Undo2,
  Redo2,
  Ruler,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/PageHeader";
import { PathPicker } from "@/components/PathPicker";
import { RunPanel } from "@/components/RunPanel";
import {
  TelemetryChart,
  TelemetryChartViewState,
} from "@/components/postprocessing/TelemetryChart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ApiError,
  PostprocessingField,
  PostprocessingObservation,
  PostprocessingOpen,
  PostprocessingWorkspace,
  api,
} from "@/lib/api";

type OverrideMode = "point" | "unit" | null;

export type PostprocessingPagePersistedState = {
  outputDir: string;
  workspace: PostprocessingWorkspace | null;
  openSummary: PostprocessingOpen | null;
  activeFieldId: string;
  selectedSampleIds: string[];
  showOutliers: boolean;
  jobId: string | null;
  saveOpen: boolean;
  discardOpen: boolean;
  overrideMode: OverrideMode;
  overrideValue: string;
  overrideUnit: string;
  chartViewState: (TelemetryChartViewState & { fieldId: string }) | null;
};

export function createDefaultPostprocessingPageState(
  suggestedOutputDir = "",
): PostprocessingPagePersistedState {
  return {
    outputDir: suggestedOutputDir,
    workspace: null,
    openSummary: null,
    activeFieldId: "",
    selectedSampleIds: [],
    showOutliers: false,
    jobId: null,
    saveOpen: false,
    discardOpen: false,
    overrideMode: null,
    overrideValue: "",
    overrideUnit: "",
    chartViewState: null,
  };
}

export function PostprocessingPage({
  persistedState,
  onPersistedStateChange,
  suggestedOutputDir = "",
}: {
  persistedState: PostprocessingPagePersistedState;
  onPersistedStateChange: Dispatch<SetStateAction<PostprocessingPagePersistedState>>;
  suggestedOutputDir?: string;
}) {
  const [outputDir, setOutputDir] = useState(persistedState.outputDir);
  const [workspace, setWorkspace] = useState<PostprocessingWorkspace | null>(persistedState.workspace);
  const [openSummary, setOpenSummary] = useState<PostprocessingOpen | null>(persistedState.openSummary);
  const [activeFieldId, setActiveFieldId] = useState(persistedState.activeFieldId);
  const [selectedSampleIds, setSelectedSampleIds] = useState(persistedState.selectedSampleIds);
  const [showOutliers, setShowOutliers] = useState(persistedState.showOutliers);
  const [jobId, setJobId] = useState<string | null>(persistedState.jobId);
  const [saveOpen, setSaveOpen] = useState(persistedState.saveOpen);
  const [discardOpen, setDiscardOpen] = useState(persistedState.discardOpen);
  const [overrideMode, setOverrideMode] = useState<OverrideMode>(persistedState.overrideMode);
  const [overrideValue, setOverrideValue] = useState(persistedState.overrideValue);
  const [overrideUnit, setOverrideUnit] = useState(persistedState.overrideUnit);
  const [chartViewState, setChartViewState] = useState(persistedState.chartViewState);
  const [loading, setLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const mutationInFlight = useRef(false);
  const selected = useMemo(() => new Set(selectedSampleIds), [selectedSampleIds]);

  useEffect(() => {
    onPersistedStateChange({
      outputDir,
      workspace,
      openSummary,
      activeFieldId,
      selectedSampleIds,
      showOutliers,
      jobId,
      saveOpen,
      discardOpen,
      overrideMode,
      overrideValue,
      overrideUnit,
      chartViewState,
    });
  }, [
    activeFieldId,
    chartViewState,
    discardOpen,
    jobId,
    onPersistedStateChange,
    openSummary,
    outputDir,
    overrideMode,
    overrideUnit,
    overrideValue,
    saveOpen,
    selectedSampleIds,
    showOutliers,
    workspace,
  ]);

  const activeField = useMemo(
    () => workspace?.fields.find((field) => field.id === activeFieldId) ?? workspace?.fields[0] ?? null,
    [activeFieldId, workspace],
  );
  const selectedObservations = useMemo(
    () => activeField?.observations.filter((item) => selected.has(item.sample_id)) ?? [],
    [activeField, selected],
  );
  const activeChartViewState =
    activeField && chartViewState?.fieldId === activeField.id
      ? {
          tool: chartViewState.tool,
          bounds: chartViewState.bounds,
          shortcutsOpen: chartViewState.shortcutsOpen,
        }
      : null;
  const currentPoint = selectedObservations.length === 1 ? selectedObservations[0] : null;
  const isSaving = Boolean(jobId);
  const applied = workspace?.draft?.applied ?? false;
  const editingFrozen = isSaving || applied || mutating;

  useEffect(() => {
    if (!workspace && suggestedOutputDir) {
      setOutputDir((current) => (current === suggestedOutputDir ? current : suggestedOutputDir));
    }
  }, [suggestedOutputDir, workspace]);

  useEffect(() => {
    if (!workspace) return;
    setActiveFieldId((current) =>
      workspace.fields.some((field) => field.id === current) ? current : workspace.fields[0]?.id || "",
    );
  }, [workspace]);

  useEffect(() => {
    setSelectedSampleIds([]);
  }, [activeFieldId]);

  useEffect(() => {
    if (!jobId || !workspace) return;
    const timer = window.setInterval(async () => {
      try {
        const job = await api.job(jobId);
        if (job.state === "queued" || job.state === "running") return;
        window.clearInterval(timer);
        if (job.state === "succeeded") {
          toast.success("Post-processing outputs regenerated.");
          const next = await api.postprocessingSession(workspace.path, "create");
          rememberSession(next.path, next.session_token);
          setWorkspace(next);
        } else {
          toast.error(job.state === "cancelled" ? "Regeneration cancelled." : "Regeneration failed.");
          const token = workspace.session_token;
          const next = await api.postprocessingSession(workspace.path, "resume", token);
          setWorkspace(next);
        }
        setSelectedSampleIds([]);
        setJobId(null);
      } catch {
        window.clearInterval(timer);
      }
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [jobId, workspace]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!workspace || isTextEntry(event.target)) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        mutate(event.shiftKey ? "redo" : "undo");
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        mutate("delete");
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        mutate("restore");
      } else if (event.key === "Escape") {
        setSelectedSampleIds([]);
      } else if (event.key === "Enter" && selected.size === 1) {
        openPointEditor();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const loadDirectory = async () => {
    if (!outputDir) return;
    setLoading(true);
    try {
      const summary = await api.postprocessingOpen(outputDir);
      if (summary.draft) {
        setOpenSummary(summary);
      } else {
        const next = await api.postprocessingSession(outputDir, "create");
        rememberSession(next.path, next.session_token);
        setWorkspace(next);
      }
    } catch (error) {
      toast.error(messageFor(error));
    } finally {
      setLoading(false);
    }
  };

  const resume = async (action: "resume" | "discard" | "takeover") => {
    if (!openSummary) return;
    try {
      const savedToken = window.localStorage.getItem(sessionKey(openSummary.path));
      const next = await api.postprocessingSession(openSummary.path, action, savedToken);
      rememberSession(next.path, next.session_token);
      setWorkspace(next);
      setOpenSummary(null);
    } catch (error) {
      toast.error(messageFor(error));
    }
  };

  const mutate = async (
    action: "delete" | "restore" | "undo" | "redo",
    sampleIds: string[] = selectedSampleIds,
  ) => {
    if (!workspace || editingFrozen || mutationInFlight.current) return;
    if ((action === "delete" || action === "restore") && sampleIds.length === 0) return;
    mutationInFlight.current = true;
    setMutating(true);
    try {
      const next = await api.postprocessingDraft(workspace.path, workspace.session_token, {
        action,
        field_name: activeField?.id,
        sample_ids: sampleIds,
      });
      setWorkspace(next);
      setSelectedSampleIds([]);
    } catch (error) {
      toast.error(messageFor(error));
    } finally {
      mutationInFlight.current = false;
      setMutating(false);
    }
  };

  const openPointEditor = (observation = currentPoint) => {
    if (!observation || !activeField || editingFrozen) return;
    setSelectedSampleIds([observation.sample_id]);
    setOverrideValue(String(observation.raw_value ?? ""));
    setOverrideUnit(observation.raw_unit || activeField.units[0]?.name || "");
    setOverrideMode("point");
  };

  const openUnitEditor = () => {
    if (editingFrozen || !activeField || selectedObservations.filter((item) => !item.deleted).length === 0) return;
    setOverrideUnit(activeField.units[0]?.name || "");
    setOverrideMode("unit");
  };

  const applyOverride = async () => {
    if (!workspace || !activeField || !overrideUnit || editingFrozen) return;
    const ids = selectedObservations.filter((item) => !item.deleted).map((item) => item.sample_id);
    if (!ids.length) return;
    try {
      let next = workspace;
      if (overrideMode === "point") {
        const value = Number(overrideValue);
        if (!Number.isFinite(value)) {
          toast.error("Enter a numeric value.");
          return;
        }
        next = await api.postprocessingDraft(workspace.path, workspace.session_token, {
          action: "override",
          field_name: activeField.id,
          sample_ids: ids,
          value,
          unit: overrideUnit,
        });
      } else {
        for (const observation of selectedObservations.filter((item) => !item.deleted)) {
          if (observation.raw_value === null) continue;
          next = await api.postprocessingDraft(next.path, next.session_token, {
            action: "override",
            field_name: activeField.id,
            sample_ids: [observation.sample_id],
            value: observation.raw_value,
            unit: overrideUnit,
          });
        }
      }
      setWorkspace(next);
      setSelectedSampleIds([]);
      setOverrideMode(null);
    } catch (error) {
      toast.error(messageFor(error));
    }
  };

  const save = async () => {
    if (!workspace) return;
    try {
      const job = await api.savePostprocessingDraft(workspace.path, workspace.session_token);
      setSaveOpen(false);
      setJobId(job.id);
    } catch (error) {
      toast.error(messageFor(error));
    }
  };

  const retry = async () => {
    if (!workspace) return;
    try {
      const job = await api.retryPostprocessing(workspace.path);
      setJobId(job.id);
    } catch (error) {
      toast.error(messageFor(error));
    }
  };

  const regenerateOverlay = async () => {
    if (!workspace) return;
    try {
      const job = await api.regeneratePostprocessingOverlay(workspace.path);
      setJobId(job.id);
    } catch (error) {
      toast.error(messageFor(error));
    }
  };

  const discard = async () => {
    if (!workspace) return;
    try {
      await api.discardPostprocessingDraft(workspace.path, workspace.session_token);
      window.localStorage.removeItem(sessionKey(workspace.path));
      setOutputDir(workspace.path);
      setWorkspace(null);
      setOpenSummary(null);
      setActiveFieldId("");
      setSelectedSampleIds([]);
      setShowOutliers(false);
      setSaveOpen(false);
      setDiscardOpen(false);
      setOverrideMode(null);
      setOverrideValue("");
      setOverrideUnit("");
      setChartViewState(null);
      toast.success(applied ? "Editor closed with stale derived outputs." : "Draft discarded.");
    } catch (error) {
      toast.error(messageFor(error));
    }
  };

  const exitEditor = () => {
    if (!workspace || isSaving) return;
    setOutputDir(workspace.path);
    setWorkspace(null);
    setOpenSummary(null);
    setActiveFieldId("");
    setSelectedSampleIds([]);
    setShowOutliers(false);
    setSaveOpen(false);
    setDiscardOpen(false);
    setOverrideMode(null);
    setOverrideValue("");
    setOverrideUnit("");
    setChartViewState(null);
    if (hasEdits) {
      toast.message("Editor closed. Unsaved draft preserved.");
    }
  };

  const hasEdits = Boolean(workspace?.draft?.operation_count);
  const failedNodes = workspace ? Object.values(workspace.manifest.nodes).filter((node) => node.status === "failed") : [];

  return (
    <div className="min-h-full">
      <PageHeader
        title="Postprocessing"
        description="Review and correct extracted telemetry observations."
        badges={
          workspace && (
            <>
              <Badge variant={hasEdits ? "warning" : "success"}>{hasEdits ? "Unsaved draft" : "Current baseline"}</Badge>
              {workspace.pending_recomputations.length > 0 && (
                <Badge variant="outline">Save recomputes {workspace.pending_recomputations.join(", ")}</Badge>
              )}
            </>
          )
        }
        actions={
          workspace && (
            <>
              {(failedNodes.length > 0 || applied) && (
                <Button variant="outline" onClick={retry} disabled={isSaving}>
                  <RefreshCw className="mr-2 h-4 w-4" /> Retry regeneration
                </Button>
              )}
              <Button variant="outline" onClick={exitEditor} disabled={isSaving}>
                <LogOut className="mr-2 h-4 w-4" /> Exit
              </Button>
              <Button variant="outline" onClick={() => setDiscardOpen(true)} disabled={isSaving}>
                <RotateCcw className="mr-2 h-4 w-4" /> Discard
              </Button>
              <Button onClick={() => setSaveOpen(true)} disabled={!hasEdits || editingFrozen}>
                <Save className="mr-2 h-4 w-4" /> Save
              </Button>
            </>
          )
        }
      />
      <div className="space-y-5 p-4 sm:p-6">
        {!workspace && (
          <Card>
            <CardHeader>
              <CardTitle>Open extracted telemetry</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <PathPicker value={outputDir} onChange={setOutputDir} mode="directory" placeholder="Select an output directory" />
              <Button onClick={loadDirectory} disabled={!outputDir || loading}>
                <FolderOpen className="mr-2 h-4 w-4" /> Open output
              </Button>
            </CardContent>
          </Card>
        )}

        {workspace && activeField && (
          <>
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_290px]">
              <Card className="min-w-0">
                <CardHeader className="gap-3 border-b border-border/70">
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <CardTitle>{activeField.label}</CardTitle>
                      <div className="mt-1 font-mono text-xs text-muted-foreground">{activeField.output_unit}</div>
                    </div>
                    <div className="w-full md:w-60">
                      <Select value={activeField.id} onValueChange={setActiveFieldId}>
                        <SelectTrigger aria-label="Active telemetry field">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {workspace.fields.map((field) => (
                            <SelectItem key={field.id} value={field.id}>
                              {field.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button size="sm" variant="outline" onClick={() => mutate("delete")} disabled={!selected.size || editingFrozen}>
                      <Trash2 className="mr-2 h-4 w-4" /> Delete
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => mutate("restore")} disabled={!selected.size || editingFrozen}>
                      <RotateCcw className="mr-2 h-4 w-4" /> Restore
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => openPointEditor()} disabled={selected.size !== 1 || editingFrozen}>
                      <Edit3 className="mr-2 h-4 w-4" /> Edit
                    </Button>
                    <Button size="sm" variant="outline" onClick={openUnitEditor} disabled={!selected.size || editingFrozen}>
                      <Ruler className="mr-2 h-4 w-4" /> Override unit
                    </Button>
                    <Button size="icon" variant="ghost" title="Undo" aria-label="Undo" onClick={() => mutate("undo")} disabled={editingFrozen}>
                      <Undo2 className="h-4 w-4" />
                    </Button>
                    <Button size="icon" variant="ghost" title="Redo" aria-label="Redo" onClick={() => mutate("redo")} disabled={editingFrozen}>
                      <Redo2 className="h-4 w-4" />
                    </Button>
                    <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        aria-label="Show outliers"
                        checked={showOutliers}
                        onChange={(event) => setShowOutliers(event.target.checked)}
                      />
                      Show outliers
                    </label>
                  </div>
                </CardHeader>
                <CardContent className="p-4">
                  <TelemetryChart
                    key={activeField.id}
                    observations={activeField.observations}
                    selected={selected}
                    showOutliers={showOutliers}
                    onSelected={(next) => setSelectedSampleIds([...next])}
                    onEdit={openPointEditor}
                    initialViewState={activeChartViewState}
                    onViewStateChange={(next) =>
                      setChartViewState({ fieldId: activeField.id, ...next })
                    }
                  />
                </CardContent>
              </Card>

              <div className="space-y-5">
                <SelectionPanel observations={selectedObservations} />
                <UnparsedPanel field={activeField} onEdit={openPointEditor} />
                <ManifestPanel workspace={workspace} onOverlay={regenerateOverlay} disabled={editingFrozen} />
              </div>
            </div>
            <RunPanel jobId={jobId} onCleared={() => setJobId(null)} />
          </>
        )}
      </div>

      <ResumeDialog summary={openSummary} onCancel={() => setOpenSummary(null)} onAction={resume} />
      <SaveDialog open={saveOpen} workspace={workspace} onOpenChange={setSaveOpen} onSave={save} />
      <ConfirmDialog
        open={discardOpen}
        title={applied ? "Close with stale outputs?" : "Discard draft?"}
        description={
          applied
            ? "Corrected raw telemetry will remain saved. Derived outputs stay stale until Retry regeneration completes."
            : "Unsaved corrections will be removed and the persisted raw baseline will be restored."
        }
        confirmLabel={applied ? "Close editor" : "Discard draft"}
        onOpenChange={setDiscardOpen}
        onConfirm={discard}
      />
      <OverrideDialog
        mode={overrideMode}
        field={activeField}
        point={currentPoint}
        value={overrideValue}
        unit={overrideUnit}
        onValueChange={setOverrideValue}
        onUnitChange={setOverrideUnit}
        onOpenChange={(open) => !open && setOverrideMode(null)}
        onConfirm={applyOverride}
      />
    </div>
  );
}

function SelectionPanel({ observations }: { observations: PostprocessingObservation[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{observations.length} selected</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-muted-foreground">
        {observations.slice(0, 5).map((item) => (
          <div key={item.sample_id} className="flex items-center justify-between gap-2">
            <span className="font-mono">T+{item.mission_elapsed_time_s?.toFixed(2) ?? "-"}</span>
            <span className="truncate">{item.deleted ? "deleted" : item.raw_text || "manual"}</span>
          </div>
        ))}
        {observations.length > 5 && <div>+ {observations.length - 5} more</div>}
      </CardContent>
    </Card>
  );
}

function UnparsedPanel({ field, onEdit }: { field: PostprocessingField; onEdit: (item: PostprocessingObservation) => void }) {
  const items = field.observations.filter((item) => !item.plottable && item.raw_value !== null && !item.deleted);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Unparsed observations</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.length === 0 && <div className="text-xs text-muted-foreground">No editable unparsed values.</div>}
        {items.slice(0, 8).map((item) => (
          <button
            key={item.sample_id}
            type="button"
            className="flex w-full items-center justify-between gap-2 rounded-md border border-border/70 px-2 py-1.5 text-left text-xs hover:bg-muted/50"
            onClick={() => onEdit(item)}
          >
            <span className="font-mono">T+{item.mission_elapsed_time_s?.toFixed(2) ?? "-"}</span>
            <span className="truncate text-muted-foreground">{item.raw_text}</span>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

function ManifestPanel({
  workspace,
  onOverlay,
  disabled,
}: {
  workspace: PostprocessingWorkspace;
  onOverlay: () => void;
  disabled: boolean;
}) {
  const nodes = Object.entries(workspace.manifest.nodes);
  const overlay = workspace.manifest.nodes.overlay;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Derived outputs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {nodes.map(([id, node]) => (
          <div key={id} className="flex items-center justify-between gap-2 text-xs">
            <span className="truncate">{id.replaceAll("_", " ")}</span>
            <StatusBadge status={node.status} />
          </div>
        ))}
        <Button className="mt-3 w-full" size="sm" variant="outline" onClick={onOverlay} disabled={disabled || overlay.status === "disabled"}>
          <Film className="mr-2 h-4 w-4" /> Regenerate overlay
        </Button>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variant = status === "current" ? "success" : status === "failed" ? "destructive" : status === "stale" ? "warning" : "outline";
  return <Badge variant={variant}>{status}</Badge>;
}

function ResumeDialog({
  summary,
  onCancel,
  onAction,
}: {
  summary: PostprocessingOpen | null;
  onCancel: () => void;
  onAction: (action: "resume" | "discard" | "takeover") => void;
}) {
  return (
    <Dialog open={Boolean(summary)} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Unsaved draft found</DialogTitle>
          <DialogDescription>Resume the existing correction session or discard it and reopen the persisted baseline.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button variant="outline" onClick={() => onAction("discard")}>Discard</Button>
          {summary?.draft?.expired && <Button variant="outline" onClick={() => onAction("takeover")}>Take over</Button>}
          <Button onClick={() => onAction("resume")}>Resume</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SaveDialog({
  open,
  workspace,
  onOpenChange,
  onSave,
}: {
  open: boolean;
  workspace: PostprocessingWorkspace | null;
  onOpenChange: (open: boolean) => void;
  onSave: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Save corrections?</DialogTitle>
          <DialogDescription>Raw telemetry will be overwritten atomically. One rolling backup will be retained.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 text-sm text-muted-foreground">
          <div>{workspace?.draft?.edit_counts.deleted ?? 0} deleted observations</div>
          <div>{workspace?.draft?.edit_counts.manual ?? 0} manual overrides</div>
          <div>Recomputes: {workspace?.pending_recomputations.join(", ") || "derived outputs"}</div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onSave}><Save className="mr-2 h-4 w-4" /> Save and regenerate</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OverrideDialog({
  mode,
  field,
  point,
  value,
  unit,
  onValueChange,
  onUnitChange,
  onOpenChange,
  onConfirm,
}: {
  mode: OverrideMode;
  field: PostprocessingField | null;
  point: PostprocessingObservation | null;
  value: string;
  unit: string;
  onValueChange: (next: string) => void;
  onUnitChange: (next: string) => void;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={Boolean(mode)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "point" ? "Edit observation" : "Override selected units"}</DialogTitle>
          <DialogDescription>
            {mode === "point" ? "Preserved OCR evidence remains unchanged." : "Selected OCR numeric values will be reinterpreted in this unit."}
          </DialogDescription>
        </DialogHeader>
        {mode === "point" && (
          <div className="rounded-md border border-border/70 bg-background/50 p-3 text-xs">
            <div className="text-muted-foreground">OCR text</div>
            <div className="mt-1 font-mono">{point?.raw_text || "-"}</div>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {mode === "point" && (
            <div className="space-y-2">
              <Label htmlFor="override-value">Value</Label>
              <Input id="override-value" value={value} onChange={(event) => onValueChange(event.target.value)} />
            </div>
          )}
          <div className="space-y-2">
            <Label>Unit</Label>
            <Select value={unit} onValueChange={onUnitChange}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {field?.units.map((item) => <SelectItem key={item.name} value={item.name}>{item.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onConfirm}>Apply override</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function messageFor(error: unknown) {
  return error instanceof ApiError ? error.message : "Unexpected error";
}

function isTextEntry(target: EventTarget | null) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
}

function sessionKey(path: string) {
  return `webcalyzer:postprocessing:${path}`;
}

function rememberSession(path: string, token: string) {
  window.localStorage.setItem(sessionKey(path), token);
}
