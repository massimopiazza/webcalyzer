import { useEffect, useMemo, useState } from "react";
import { ChevronUp, FileVideo, Folder, FolderOpen, Loader2 } from "lucide-react";
import { ApiError, FileEntry, FileListing, api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { cn, formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

type Mode = "video" | "directory";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: Mode;
  onSelect: (path: string) => void;
  initialPath?: string | null;
};

export function FileBrowserDialog({ open, onOpenChange, mode, onSelect, initialPath }: Props) {
  const meta = useMeta();
  const [path, setPath] = useState<string>(initialPath || meta?.roots[0]?.path || "");
  const [listing, setListing] = useState<FileListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const kinds = mode === "video" ? "dir,video" : "dir,file,video";

  useEffect(() => {
    if (!open) return;
    setPath(initialPath || meta?.roots[0]?.path || "");
  }, [open, initialPath, meta]);

  useEffect(() => {
    if (!open || !path) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .files(path, kinds)
      .then((data) => {
        if (!cancelled) setListing(data);
      })
      .catch((err: ApiError) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, path, kinds]);

  const filteredEntries = useMemo(() => {
    if (!listing) return [];
    const lower = filter.trim().toLowerCase();
    if (!lower) return listing.entries;
    return listing.entries.filter((e) => e.name.toLowerCase().includes(lower));
  }, [listing, filter]);

  const choosable = mode === "directory" && listing?.path;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{mode === "video" ? "Select a video file" : "Select a directory"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Button
              size="icon"
              variant="outline"
              disabled={!listing?.parent}
              onClick={() => listing?.parent && setPath(listing.parent)}
              title="Up one level"
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
            <Input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  setPath((p) => p);
                }
              }}
              spellCheck={false}
              className="font-mono text-xs"
            />
            <Input
              placeholder="Filter…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-40"
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {meta?.roots.map((root) => (
              <Button
                key={root.path}
                size="sm"
                variant={path === root.path ? "secondary" : "ghost"}
                onClick={() => setPath(root.path)}
                className="h-7 text-xs"
              >
                <Folder className="mr-1 h-3 w-3" />
                {root.label}
              </Button>
            ))}
          </div>
          <div className="rounded-md border border-border bg-background/30">
            <ScrollArea className="h-80">
              {loading && (
                <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> loading…
                </div>
              )}
              {error && <div className="p-4 text-sm text-destructive">{error}</div>}
              {!loading &&
                !error &&
                filteredEntries.map((entry) => (
                  <FileRow
                    key={entry.path}
                    entry={entry}
                    onOpen={() => {
                      if (entry.type === "dir") setPath(entry.path);
                      else onSelect(entry.path);
                    }}
                    onSelectFile={() => onSelect(entry.path)}
                    mode={mode}
                  />
                ))}
              {!loading && !error && filteredEntries.length === 0 && (
                <div className="p-6 text-center text-sm text-muted-foreground">No matches</div>
              )}
            </ScrollArea>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            {choosable && (
              <Button onClick={() => listing && onSelect(listing.path)}>
                <FolderOpen className="mr-2 h-4 w-4" /> Use this folder
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function FileRow({
  entry,
  onOpen,
  onSelectFile,
  mode,
}: {
  entry: FileEntry;
  onOpen: () => void;
  onSelectFile: () => void;
  mode: Mode;
}) {
  const Icon = entry.type === "dir" ? Folder : FileVideo;
  return (
    <button
      type="button"
      onDoubleClick={onOpen}
      onClick={mode === "video" && entry.type !== "dir" ? onSelectFile : onOpen}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent/15",
      )}
    >
      <Icon className={cn("h-4 w-4 shrink-0", entry.type === "dir" ? "text-primary" : "text-warning")} />
      <span className="flex-1 truncate">{entry.name}</span>
      {entry.type !== "dir" && (
        <span className="shrink-0 font-mono text-xs text-muted-foreground">
          {formatBytes(entry.size)}
        </span>
      )}
    </button>
  );
}
