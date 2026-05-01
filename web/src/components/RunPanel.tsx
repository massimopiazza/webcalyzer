import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpToLine,
  Ban,
  CheckCircle2,
  CircleAlert,
  Download,
  ExternalLink,
  Loader2,
  Maximize2,
  PlayCircle,
} from "lucide-react";
import { Button, ButtonProps } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, JobEvent, JobSummary, api } from "@/lib/api";
import { cn, formatTimeAgo } from "@/lib/utils";
import { toast } from "sonner";

type ConsoleViewMode = "dialog" | "docked";

type Props = {
  jobId: string | null;
  onCleared: () => void;
};

export function RunPanel({ jobId, onCleared }: Props) {
  const [job, setJob] = useState<JobSummary | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [viewMode, setViewMode] = useState<ConsoleViewMode>("dialog");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setEvents([]);
      return;
    }
    let cancelled = false;
    setViewMode("dialog");
    setEvents([]);
    api
      .job(jobId)
      .then((data) => {
        if (cancelled) return;
        setJob(data);
        setEvents(data.events);
      })
      .catch((err: ApiError) => toast.error(err.message));

    const source = new EventSource(`/api/jobs/${jobId}/events`);
    source.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as JobEvent;
        setEvents((prev) => [...prev, event]);
        if (event.kind === "done" || event.kind === "error" || event.kind === "cancelled") {
          api.job(jobId).then(setJob).catch(() => null);
          source.close();
        }
      } catch {
        /* ignore non-JSON keep-alive lines */
      }
    };
    source.onerror = () => {
      // Browser may auto-reconnect; if backend is gone we'll just stay quiet.
    };

    return () => {
      cancelled = true;
      source.close();
    };
  }, [jobId]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [events.length]);

  const phase = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].kind === "phase") return events[i].message;
    }
    return null;
  }, [events]);

  const handleCancel = async () => {
    if (!jobId) return;
    try {
      await api.cancelJob(jobId);
      toast.message("Cancellation requested");
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  if (!jobId) return null;

  const content = (
    <RunConsoleContent
      events={events}
      job={job}
      phase={phase}
      scrollRef={scrollRef}
      viewMode={viewMode}
      onCancel={handleCancel}
      onCleared={onCleared}
      onToggleView={() => setViewMode((current) => (current === "dialog" ? "docked" : "dialog"))}
    />
  );

  if (viewMode === "dialog") {
    return (
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open) setViewMode("docked");
        }}
      >
        <DialogContent className="flex max-h-[calc(100vh-1rem)] max-w-5xl flex-col gap-0 overflow-hidden p-0 sm:max-h-[calc(100vh-2rem)]">
          {content}
        </DialogContent>
      </Dialog>
    );
  }

  return <Card>{content}</Card>;
}

function RunConsoleContent({
  events,
  job,
  phase,
  scrollRef,
  viewMode,
  onCancel,
  onCleared,
  onToggleView,
}: {
  events: JobEvent[];
  job: JobSummary | null;
  phase: string | null;
  scrollRef: React.RefObject<HTMLDivElement>;
  viewMode: ConsoleViewMode;
  onCancel: () => void;
  onCleared: () => void;
  onToggleView: () => void;
}) {
  const isRunning = job?.state === "queued" || job?.state === "running";
  const isDialog = viewMode === "dialog";

  return (
    <div className={cn("flex min-h-0 flex-col", isDialog && "max-h-[calc(100vh-1rem)]")}>
      <div
        className={cn(
          "flex flex-col gap-3 border-b border-border/60 p-4 sm:flex-row sm:items-start sm:justify-between",
          isDialog && "pr-12",
        )}
      >
        <div className="min-w-0">
          {isDialog ? (
            <>
              <DialogTitle>Run console</DialogTitle>
              <DialogDescription className="mt-1">
                Live pipeline progress and output files.
              </DialogDescription>
            </>
          ) : (
            <>
              <CardTitle>Run console</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Live pipeline progress and output files.
              </p>
            </>
          )}
          {job && (
            <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="font-mono">
                {job.id}
              </Badge>
              <span>{formatTimeAgo(job.started_at)}</span>
              <span>·</span>
              <span className="min-w-0 truncate font-mono">{job.output_dir}</span>
            </div>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <StateBadge state={job?.state} />
          <Button
            variant="outline"
            size="sm"
            onClick={onToggleView}
            title={isDialog ? "Dock console to page" : "Focus console"}
            aria-label={isDialog ? "Dock console to page" : "Focus console"}
          >
            {isDialog ? <ArrowUpToLine className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            <span className="hidden sm:inline">{isDialog ? "Dock" : "Focus"}</span>
          </Button>
          {isRunning && (
            <Button variant="outline" size="sm" onClick={onCancel}>
              <Ban className="h-4 w-4" /> Cancel
            </Button>
          )}
          {job?.state && !isRunning && (
            <Button variant="ghost" size="sm" onClick={onCleared}>
              Close
            </Button>
          )}
        </div>
      </div>

      <div className="min-h-0 space-y-3 overflow-y-auto p-4">
        {phase && (
          <div className="flex items-center gap-2 rounded-md bg-muted/40 px-3 py-2 text-sm">
            <Loader2
              className={cn(
                "h-4 w-4",
                job?.state === "running" ? "animate-spin text-primary" : "text-muted-foreground",
              )}
            />
            {phase}
          </div>
        )}
        <div className="rounded-md border border-border/70 bg-black/30">
          <div
            ref={scrollRef}
            className={cn(
              "overflow-y-auto p-3 font-mono text-[12px] leading-relaxed",
              isDialog ? "h-[52vh] max-h-[28rem]" : "h-64 sm:h-72",
            )}
          >
            {events.length === 0 && (
              <div className="text-muted-foreground">Waiting for output…</div>
            )}
            {events.map((event, idx) => (
              <LogLine key={idx} event={event} />
            ))}
          </div>
        </div>
        {job && job.outputs.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Output files
            </div>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 md:grid-cols-3">
              {job.outputs.slice(0, 30).map((relpath) => (
                <a
                  key={relpath}
                  href={api.jobFileUrl(job.id, relpath)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 truncate rounded-md border border-border/60 bg-muted/30 px-2 py-1 text-xs hover:border-primary/60"
                >
                  {relpath.endsWith(".pdf") ? (
                    <ExternalLink className="h-3 w-3 text-primary" />
                  ) : (
                    <Download className="h-3 w-3 text-muted-foreground" />
                  )}
                  <span className="truncate font-mono">{relpath}</span>
                </a>
              ))}
            </div>
            {job.outputs.length > 30 && (
              <div className="mt-1 text-xs text-muted-foreground">
                +{job.outputs.length - 30} more in {job.output_dir}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function LogLine({ event }: { event: JobEvent }) {
  const className = cn(
    event.kind === "phase" && "text-primary",
    event.kind === "error" && "text-destructive",
    event.kind === "cancelled" && "text-warning",
    event.kind === "done" && "text-success",
  );
  const stamp = new Date(event.timestamp * 1000).toLocaleTimeString();
  return (
    <div className={className}>
      <span className="text-muted-foreground">{stamp}</span>{" "}
      <span className="text-muted-foreground">[{event.kind}]</span> {event.message}
    </div>
  );
}

function StateBadge({ state }: { state?: JobSummary["state"] }) {
  if (!state) return <Badge variant="secondary">…</Badge>;
  if (state === "running" || state === "queued")
    return (
      <Badge variant="default" className="gap-1">
        <Loader2 className="h-3 w-3 animate-spin" /> {state}
      </Badge>
    );
  if (state === "succeeded")
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" /> succeeded
      </Badge>
    );
  if (state === "failed")
    return (
      <Badge variant="destructive" className="gap-1">
        <CircleAlert className="h-3 w-3" /> failed
      </Badge>
    );
  return (
    <Badge variant="warning" className="gap-1">
      <Ban className="h-3 w-3" /> cancelled
    </Badge>
  );
}

export function StartButton({
  disabled,
  onClick,
  loading,
  size = "lg",
  className,
}: {
  disabled?: boolean;
  onClick: () => void;
  loading?: boolean;
  size?: ButtonProps["size"];
  className?: string;
}) {
  return (
    <Button
      onClick={onClick}
      disabled={disabled || loading}
      size={size}
      className={cn("gap-2", className)}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
      Run pipeline
    </Button>
  );
}
