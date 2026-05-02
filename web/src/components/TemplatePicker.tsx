import { useEffect, useState } from "react";
import { FolderOpen, RefreshCw, Save, Upload } from "lucide-react";
import { ApiError, ProfileDTO, TemplateSummary, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";

type Props = {
  selected: string | null;
  onLoad: (name: string, profile: ProfileDTO) => void;
  refreshKey?: number;
};

export function TemplatePicker({ selected, onLoad, refreshKey }: Props) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    try {
      setLoading(true);
      const list = await api.templates();
      setTemplates(list);
    } catch (err) {
      toast.error((err as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [refreshKey]);

  const load = async (name: string) => {
    if (!name) return;
    try {
      const result = await api.template(name);
      onLoad(result.name, result.profile);
      toast.success(`Loaded ${name}`);
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select value={selected || ""} onValueChange={(v) => load(v)}>
        <SelectTrigger className="w-72">
          <SelectValue placeholder="Load YAML template…" />
        </SelectTrigger>
        <SelectContent>
          {templates.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              {loading ? "Loading…" : "No templates yet."}
            </div>
          )}
          {templates.map((tpl) => (
            <SelectItem key={tpl.name} value={tpl.name}>
              <span className="font-mono text-xs">{tpl.name}</span>
              {tpl.error && <span className="ml-2 text-xs text-destructive">⚠</span>}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="outline" size="icon" onClick={refresh} title="Refresh templates">
        <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
      </Button>
      {selected && (
        <Button variant="outline" size="sm" asChild>
          <a href={api.templateYamlUrl(selected)} target="_blank" rel="noreferrer">
            <FolderOpen className="mr-1 h-3 w-3" /> Open YAML
          </a>
        </Button>
      )}
    </div>
  );
}

type SaveAsTemplateButtonProps = {
  profile: ProfileDTO;
  isValid: boolean;
  currentName?: string | null;
  onSaved: (name: string) => void;
  variant?: "default" | "outline" | "ghost" | "secondary";
  size?: "default" | "sm" | "lg" | "icon";
};

export function SaveAsTemplateButton({
  profile,
  isValid,
  currentName,
  onSaved,
  variant = "outline",
  size = "sm",
}: SaveAsTemplateButtonProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(currentName || "");

  useEffect(() => {
    setName(currentName || "");
  }, [currentName, open]);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error("Provide a template name.");
      return;
    }
    if (!isValid) {
      toast.error("Fix validation errors before saving.");
      return;
    }
    try {
      const result = await api.saveTemplate(trimmed, profile);
      toast.success(`Saved ${result.name}`);
      setOpen(false);
      onSaved(result.name);
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  return (
    <>
      <Button
        variant={variant}
        size={size}
        onClick={() => setOpen(true)}
        disabled={!isValid}
        title={
          isValid
            ? "Save the entire current configuration as a YAML template"
            : "Fix validation errors before saving"
        }
      >
        <Save className="mr-1 h-4 w-4" /> Save as template
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Save profile as template</DialogTitle>
            <DialogDescription>
              Saves the entire current configuration to a YAML file under the templates directory.
              Use a relative path for subfolders (e.g.{" "}
              <code className="font-mono text-xs">blue_origin/ng3.yaml</code>).
            </DialogDescription>
          </DialogHeader>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my_profile.yaml"
            spellCheck={false}
            className="font-mono"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                submit();
              }
            }}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={!name.trim() || !isValid}>
              <Upload className="mr-1 h-4 w-4" /> Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
