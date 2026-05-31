import { useEffect, useMemo, useRef, useState } from "react";
import {
  Focus,
  Hand,
  Info,
  MousePointer2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PostprocessingObservation } from "@/lib/api";
import { cn } from "@/lib/utils";

export type TelemetryChartTool = "select" | "zoom" | "pan";
export type TelemetryChartBounds = { x0: number; x1: number; y0: number; y1: number };
export type TelemetryChartViewState = {
  tool: TelemetryChartTool;
  bounds: TelemetryChartBounds | null;
  shortcutsOpen: boolean;
};

type Tool = TelemetryChartTool;
type Bounds = TelemetryChartBounds;
type Point = { observation: PostprocessingObservation; x: number; y: number };
type Drag = {
  startX: number;
  startY: number;
  x: number;
  y: number;
  bounds: Bounds;
  shift: boolean;
  alt: boolean;
} | null;

const WIDTH = 1100;
const HEIGHT = 560;
const PAD = { left: 76, right: 24, top: 24, bottom: 52 };
const SHORTCUTS = [
  ["S", "Select tool"],
  ["Z", "Zoom-to-rectangle tool"],
  ["= / +", "Zoom in"],
  ["-", "Zoom out"],
  ["P", "Pan tool"],
  ["I", "Open chart help"],
  ["Click or drag", "Select points"],
  ["Shift + click or drag", "Add points to the selection"],
  ["Option / Alt + click or drag", "Remove points from the selection"],
  ["Esc", "Clear the selection"],
  ["Delete / Backspace", "Delete selected points"],
  ["R", "Restore selected points"],
  ["Enter", "Edit a single selected point"],
  ["Cmd / Ctrl + Z", "Undo the last correction"],
  ["Shift + Cmd / Ctrl + Z", "Redo the last correction"],
];

export function TelemetryChart({
  observations,
  selected,
  showOutliers,
  onSelected,
  onEdit,
  initialViewState,
  onViewStateChange,
}: {
  observations: PostprocessingObservation[];
  selected: Set<string>;
  showOutliers: boolean;
  onSelected: (next: Set<string>) => void;
  onEdit: (observation: PostprocessingObservation) => void;
  initialViewState?: TelemetryChartViewState | null;
  onViewStateChange?: (next: TelemetryChartViewState) => void;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dataBounds = useMemo(() => boundsFor(observations), [observations]);
  const [tool, setTool] = useState<Tool>(initialViewState?.tool ?? "select");
  const [drag, setDrag] = useState<Drag>(null);
  const [bounds, setBounds] = useState<Bounds>(
    initialViewState?.bounds ? clampBoundsToReference(initialViewState.bounds, dataBounds) : dataBounds,
  );
  const [shortcutsOpen, setShortcutsOpen] = useState(initialViewState?.shortcutsOpen ?? false);

  const points = useMemo(
    () =>
      observations
        .filter((item) => showOutliers || !item.outlier)
        .filter(
          (item): item is PostprocessingObservation & { mission_elapsed_time_s: number; value: number } =>
            item.mission_elapsed_time_s !== null && item.value !== null,
        )
        .map((observation) => ({
          observation,
          x: xScale(observation.mission_elapsed_time_s, bounds),
          y: yScale(observation.value, bounds),
        })),
    [bounds, observations, showOutliers],
  );

  const finishDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    const end = svgPoint(event, svgRef.current);
    const rect = normalizedRect(drag.startX, drag.startY, end.x, end.y);
    if (tool === "zoom" && rect.width > 8 && rect.height > 8) {
      setBounds(
        clampBoundsToReference(
          {
            x0: xValue(rect.x, bounds),
            x1: xValue(rect.x + rect.width, bounds),
            y0: yValue(rect.y + rect.height, bounds),
            y1: yValue(rect.y, bounds),
          },
          dataBounds,
        ),
      );
      setTool("select");
    } else if (tool === "select") {
      const hits = selectionHits(points, rect);
      const next = drag.shift || drag.alt ? new Set(selected) : new Set<string>();
      for (const sampleId of hits) {
        if (drag.alt) next.delete(sampleId);
        else next.add(sampleId);
      }
      onSelected(next);
    } else if (tool === "pan") {
      const dx = end.x - drag.startX;
      const dy = end.y - drag.startY;
      setBounds(clampBoundsToReference(translateBounds(drag.bounds, -dx, -dy), dataBounds));
    }
    setDrag(null);
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const zoom = (factor: number) =>
    setBounds((current) => clampBoundsToReference(zoomBounds(current, factor), dataBounds));

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || isTextEntry(event.target) || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      const key = event.key;
      const lowerKey = key.toLowerCase();
      if (key === "=" || key === "+") {
        event.preventDefault();
        zoom(0.78);
        return;
      }
      if (key === "-" || key === "_") {
        event.preventDefault();
        zoom(1.28);
        return;
      }
      if (lowerKey === "s") {
        event.preventDefault();
        setTool("select");
      } else if (lowerKey === "z") {
        event.preventDefault();
        setTool("zoom");
      } else if (lowerKey === "p") {
        event.preventDefault();
        setTool("pan");
      } else if (lowerKey === "i") {
        event.preventDefault();
        setShortcutsOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dataBounds]);

  useEffect(() => {
    onViewStateChange?.({ tool, bounds, shortcutsOpen });
  }, [bounds, onViewStateChange, shortcutsOpen, tool]);

  return (
    <div className="overflow-hidden rounded-lg border border-border/70 bg-background/45">
      <div className="flex flex-wrap items-center gap-1 border-b border-border/70 bg-card/70 p-2">
        <ToolButton active={tool === "select"} title="Select points" shortcut="S" ariaKeyShortcuts="S" onClick={() => setTool("select")}>
          <MousePointer2 />
        </ToolButton>
        <ToolButton
          active={tool === "zoom"}
          title="Zoom to rectangle once"
          shortcut="Z"
          ariaKeyShortcuts="Z"
          onClick={() => setTool("zoom")}
        >
          <Focus />
        </ToolButton>
        <ToolButton title="Zoom in" shortcut="= / +" ariaKeyShortcuts="= Shift+=" onClick={() => zoom(0.78)}>
          <ZoomIn />
        </ToolButton>
        <ToolButton title="Zoom out" shortcut="-" ariaKeyShortcuts="-" onClick={() => zoom(1.28)}>
          <ZoomOut />
        </ToolButton>
        <ToolButton title="Reset zoom" onClick={() => setBounds(dataBounds)}>
          <RotateCcw />
        </ToolButton>
        <ToolButton active={tool === "pan"} title="Pan" shortcut="P" ariaKeyShortcuts="P" onClick={() => setTool("pan")}>
          <Hand />
        </ToolButton>
        <div className="ml-2 text-xs text-muted-foreground">
          {tool === "zoom" ? "Drag a zoom region" : tool === "pan" ? "Drag to pan" : "Drag to select points"}
        </div>
        <div className="ml-auto">
          <ToolButton
            title="Keyboard shortcuts"
            shortcut="I"
            ariaKeyShortcuts="I"
            onClick={() => setShortcutsOpen(true)}
          >
            <Info />
          </ToolButton>
        </div>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className={cn(
          "block aspect-[1100/560] w-full touch-none select-none",
          tool === "pan" ? "cursor-grab active:cursor-grabbing" : "cursor-crosshair",
        )}
        role="img"
        aria-label="Editable telemetry time series"
        onPointerDown={(event) => {
          const point = svgPoint(event, svgRef.current);
          event.currentTarget.setPointerCapture(event.pointerId);
          setDrag({
            startX: point.x,
            startY: point.y,
            x: point.x,
            y: point.y,
            bounds,
            shift: event.shiftKey,
            alt: event.altKey,
          });
        }}
        onPointerMove={(event) => {
          if (!drag) return;
          const point = svgPoint(event, svgRef.current);
          setDrag({ ...drag, x: point.x, y: point.y });
          if (tool === "pan") {
            setBounds(
              clampBoundsToReference(
                translateBounds(drag.bounds, -(point.x - drag.startX), -(point.y - drag.startY)),
                dataBounds,
              ),
            );
          }
        }}
        onPointerUp={finishDrag}
        onPointerCancel={() => setDrag(null)}
        onWheel={(event) => {
          event.preventDefault();
          setBounds((current) =>
            clampBoundsToReference(translateBounds(current, event.deltaX, event.deltaY), dataBounds),
          );
        }}
      >
        <rect width={WIDTH} height={HEIGHT} className="fill-background" />
        <ChartGrid bounds={bounds} />
        {points.map(({ observation, x, y }) => (
          <circle
            key={observation.sample_id}
            cx={x}
            cy={y}
            r={selected.has(observation.sample_id) ? 6 : 4}
            className={cn(
              observation.deleted
                ? "fill-muted-foreground/40"
                : observation.outlier
                  ? "fill-destructive"
                  : observation.manual
                    ? "fill-success"
                    : "fill-primary",
              selected.has(observation.sample_id) && "stroke-warning stroke-[2.5]",
            )}
            onDoubleClick={(event) => {
              event.stopPropagation();
              if (!observation.deleted && observation.raw_value !== null) {
                onEdit(observation);
              }
            }}
          />
        ))}
        {drag && tool !== "pan" && (
          <rect
            {...normalizedRect(drag.startX, drag.startY, drag.x, drag.y)}
            className="fill-primary/10 stroke-primary stroke-[1.5] [stroke-dasharray:6_4]"
          />
        )}
      </svg>
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}

function ToolButton({
  active,
  title,
  shortcut,
  ariaKeyShortcuts,
  onClick,
  children,
}: {
  active?: boolean;
  title: string;
  shortcut?: string;
  ariaKeyShortcuts?: string;
  onClick: () => void;
  children: React.ReactElement;
}) {
  const label = shortcut ? `${title} (${shortcut})` : title;
  return (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="icon"
      className="h-8 w-8"
      title={label}
      aria-label={label}
      aria-pressed={active || undefined}
      aria-keyshortcuts={ariaKeyShortcuts}
      onClick={onClick}
    >
      {<span className="[&>svg]:h-4 [&>svg]:w-4">{children}</span>}
    </Button>
  );
}

function ChartGrid({ bounds }: { bounds: Bounds }) {
  const xTicks = ticks(bounds.x0, bounds.x1, 7);
  const yTicks = ticks(bounds.y0, bounds.y1, 6);
  return (
    <>
      {xTicks.map((value) => {
        const x = xScale(value, bounds);
        return (
          <g key={`x:${value}`}>
            <line x1={x} x2={x} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="stroke-border/70" />
            <text x={x} y={HEIGHT - 20} textAnchor="middle" className="fill-muted-foreground text-[13px]">
              {formatTick(value)}
            </text>
          </g>
        );
      })}
      {yTicks.map((value) => {
        const y = yScale(value, bounds);
        return (
          <g key={`y:${value}`}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y} className="stroke-border/70" />
            <text x={PAD.left - 12} y={y + 4} textAnchor="end" className="fill-muted-foreground text-[13px]">
              {formatTick(value)}
            </text>
          </g>
        );
      })}
      <text x={(WIDTH + PAD.left - PAD.right) / 2} y={HEIGHT - 4} textAnchor="middle" className="fill-muted-foreground text-[13px]">
        Mission elapsed time [s]
      </text>
    </>
  );
}

function boundsFor(observations: PostprocessingObservation[]): Bounds {
  const pointsWithoutOutliers = observations.filter(
    (item): item is PostprocessingObservation & { mission_elapsed_time_s: number; value: number } =>
      !item.outlier && item.mission_elapsed_time_s !== null && item.value !== null,
  );
  const points = pointsWithoutOutliers.length
    ? pointsWithoutOutliers
    : observations.filter(
        (item): item is PostprocessingObservation & { mission_elapsed_time_s: number; value: number } =>
          item.mission_elapsed_time_s !== null && item.value !== null,
      );
  if (!points.length) return { x0: 0, x1: 1, y0: 0, y1: 1 };
  const xs = points.map((point) => point.mission_elapsed_time_s);
  const ys = points.map((point) => point.value);
  return paddedBounds(Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys));
}

function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-lg overflow-hidden p-0 sm:max-h-[calc(100dvh-3rem)]">
        <div className="flex min-h-0 flex-col gap-4 p-6">
          <DialogHeader className="shrink-0 pr-8">
            <DialogTitle>Keyboard shortcuts</DialogTitle>
            <DialogDescription>Chart navigation, selection, and correction controls for the active telemetry series.</DialogDescription>
          </DialogHeader>
          <div className="-mr-2 min-h-0 overflow-y-auto pr-2">
            <div className="divide-y divide-border/70 rounded-md border border-border/70">
              {SHORTCUTS.map(([keys, description]) => (
                <div key={keys} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-4 px-3 py-2 text-sm">
                  <span className="font-mono text-xs text-foreground">{keys}</span>
                  <span className="text-muted-foreground">{description}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function paddedBounds(x0: number, x1: number, y0: number, y1: number): Bounds {
  const xPad = Math.max((x1 - x0) * 0.04, 1);
  const yPad = Math.max((y1 - y0) * 0.08, 1);
  return { x0: x0 - xPad, x1: x1 + xPad, y0: y0 - yPad, y1: y1 + yPad };
}

function xScale(value: number, bounds: Bounds) {
  return PAD.left + ((value - bounds.x0) / (bounds.x1 - bounds.x0)) * (WIDTH - PAD.left - PAD.right);
}

function yScale(value: number, bounds: Bounds) {
  return HEIGHT - PAD.bottom - ((value - bounds.y0) / (bounds.y1 - bounds.y0)) * (HEIGHT - PAD.top - PAD.bottom);
}

function xValue(pixel: number, bounds: Bounds) {
  return bounds.x0 + ((pixel - PAD.left) / (WIDTH - PAD.left - PAD.right)) * (bounds.x1 - bounds.x0);
}

function yValue(pixel: number, bounds: Bounds) {
  return bounds.y0 + ((HEIGHT - PAD.bottom - pixel) / (HEIGHT - PAD.top - PAD.bottom)) * (bounds.y1 - bounds.y0);
}

function zoomBounds(bounds: Bounds, factor: number): Bounds {
  const cx = (bounds.x0 + bounds.x1) / 2;
  const cy = (bounds.y0 + bounds.y1) / 2;
  const halfX = ((bounds.x1 - bounds.x0) * factor) / 2;
  const halfY = ((bounds.y1 - bounds.y0) * factor) / 2;
  return { x0: cx - halfX, x1: cx + halfX, y0: cy - halfY, y1: cy + halfY };
}

function translateBounds(bounds: Bounds, pixelX: number, pixelY: number): Bounds {
  const dx = (pixelX / (WIDTH - PAD.left - PAD.right)) * (bounds.x1 - bounds.x0);
  const dy = (pixelY / (HEIGHT - PAD.top - PAD.bottom)) * (bounds.y1 - bounds.y0);
  return { x0: bounds.x0 + dx, x1: bounds.x1 + dx, y0: bounds.y0 - dy, y1: bounds.y1 - dy };
}

function clampBoundsToReference(bounds: Bounds, reference: Bounds): Bounds {
  const [x0, x1] = clampAxis(bounds.x0, bounds.x1, reference.x0, reference.x1);
  const [y0, y1] = clampAxis(bounds.y0, bounds.y1, reference.y0, reference.y1);
  return { x0, x1, y0, y1 };
}

function clampAxis(min: number, max: number, referenceMin: number, referenceMax: number) {
  const span = max - min;
  const referenceSpan = referenceMax - referenceMin;
  if (span >= referenceSpan) {
    const center = (referenceMin + referenceMax) / 2;
    return [center - span / 2, center + span / 2] as const;
  }
  if (min < referenceMin) {
    return [referenceMin, referenceMin + span] as const;
  }
  if (max > referenceMax) {
    return [referenceMax - span, referenceMax] as const;
  }
  return [min, max] as const;
}

function normalizedRect(x0: number, y0: number, x1: number, y1: number) {
  return { x: Math.min(x0, x1), y: Math.min(y0, y1), width: Math.abs(x1 - x0), height: Math.abs(y1 - y0) };
}

function selectionHits(points: Point[], rect: { x: number; y: number; width: number; height: number }) {
  if (rect.width < 8 && rect.height < 8) {
    const nearest = points
      .map((point) => ({ point, distance: Math.hypot(point.x - rect.x, point.y - rect.y) }))
      .sort((a, b) => a.distance - b.distance)[0];
    return nearest && nearest.distance <= 14 ? [nearest.point.observation.sample_id] : [];
  }
  return points
    .filter((point) => point.x >= rect.x && point.x <= rect.x + rect.width && point.y >= rect.y && point.y <= rect.y + rect.height)
    .map((point) => point.observation.sample_id);
}

function svgPoint(event: React.PointerEvent<SVGSVGElement>, svg: SVGSVGElement | null) {
  const rect = svg?.getBoundingClientRect();
  if (!rect) return { x: 0, y: 0 };
  return { x: ((event.clientX - rect.left) / rect.width) * WIDTH, y: ((event.clientY - rect.top) / rect.height) * HEIGHT };
}

function ticks(min: number, max: number, count: number) {
  return Array.from({ length: count }, (_, index) => min + ((max - min) * index) / (count - 1));
}

function formatTick(value: number) {
  return Math.abs(value) >= 1000 ? value.toFixed(0) : value.toFixed(Math.abs(value) < 10 ? 2 : 1);
}

function isTextEntry(target: EventTarget | null) {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}
