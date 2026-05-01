import { useEffect, useMemo, useRef, useState } from "react";
import {
  Ban,
  CheckCircle2,
  CircleAlert,
  Download,
  ExternalLink,
  Loader2,
  PlayCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, JobEvent, JobSummary, api } from "@/lib/api";
import { cn, formatTimeAgo } from "@/lib/utils";
import { toast } from "sonner";

type Props = {
  jobId: string | null;
  onCleared: () => void;
};

export function RunPanel({ jobId, onCleared }: Props) {
  const [job, setJob] = useState<JobSummary | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setEvents([]);
      return;
    }
    let cancelled = false;
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

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <CardTitle>Run</CardTitle>
          {job && (
            <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="font-mono">
                {job.id}
              </Badge>
              <span>{formatTimeAgo(job.started_at)}</span>
              <span>·</span>
              <span className="truncate font-mono">{job.output_dir}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <StateBadge state={job?.state} />
          {(job?.state === "queued" || job?.state === "running") && (
            <Button variant="outline" size="sm" onClick={handleCancel}>
              <Ban className="mr-1 h-4 w-4" /> Cancel
            </Button>
          )}
          {job?.state && job.state !== "running" && job.state !== "queued" && (
            <Button variant="ghost" size="sm" onClick={onCleared}>
              Close
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
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
          <ScrollArea className="h-72">
            <div ref={scrollRef} className="p-3 font-mono text-[12px] leading-relaxed">
              {events.length === 0 && (
                <div className="text-muted-foreground">Waiting for output…</div>
              )}
              {events.map((event, idx) => (
                <LogLine key={idx} event={event} />
              ))}
            </div>
          </ScrollArea>
        </div>
        {job && job.outputs.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Output files
            </div>
            <div className="grid grid-cols-2 gap-1 md:grid-cols-3">
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
      </CardContent>
    </Card>
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
}: {
  disabled?: boolean;
  onClick: () => void;
  loading?: boolean;
}) {
  return (
    <Button onClick={onClick} disabled={disabled || loading} size="lg" className="gap-2">
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
      Run pipeline
    </Button>
  );
}
