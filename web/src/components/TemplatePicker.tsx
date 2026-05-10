import { type ReactNode, useEffect, useState } from "react";
import { FilePlus2, FolderOpen, Save } from "lucide-react";
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
import { HelpTip } from "@/components/ui/tooltip";
import { toast } from "sonner";

type Props = {
  selected: string | null;
  onLoad: (name: string, profile: ProfileDTO) => void;
  refreshKey?: number;
  onStartBlank: () => void;
  hasUnsavedChanges?: boolean;
};

export function TemplatePicker({
  selected,
  onLoad,
  refreshKey,
  onStartBlank,
  hasUnsavedChanges = false,
}: Props) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

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

  const requestStartBlank = () => {
    if (hasUnsavedChanges) {
      setConfirmOpen(true);
      return;
    }
    onStartBlank();
    toast.info("Started a blank template.");
  };

  const confirmStartBlank = () => {
    setConfirmOpen(false);
    onStartBlank();
    toast.info("Started a blank template.");
  };

  return (
    <>
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
                {tpl.error && <span className="ml-2 text-xs text-destructive">!</span>}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <HelpTip text="Start with a blank template. Unsaved edits will be discarded.">
          <Button
            variant="outline"
            size="icon"
            onClick={requestStartBlank}
            aria-label="Start blank template"
          >
            <FilePlus2 className="h-4 w-4" />
          </Button>
        </HelpTip>
        {selected && (
          <Button variant="outline" size="sm" asChild>
            <a href={api.templateYamlUrl(selected)} target="_blank" rel="noreferrer">
              <FolderOpen className="mr-1 h-3 w-3" /> Open YAML
            </a>
          </Button>
        )}
      </div>
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Start blank template?</DialogTitle>
            <DialogDescription>
              This will discard unsaved edits and clear the current template selection.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmStartBlank}>
              Discard and start blank
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

type SaveAsTemplateButtonProps = {
  profile: ProfileDTO;
  isValid: boolean;
  currentName?: string | null;
  onSaved: (name: string) => void;
  variant?: "default" | "outline" | "ghost" | "secondary";
  size?: "default" | "sm" | "lg" | "icon";
  label?: string;
  title?: string;
  dialogTitle?: string;
  dialogDescription?: ReactNode;
};

export function SaveAsTemplateButton({
  profile,
  isValid,
  currentName,
  onSaved,
  variant = "outline",
  size = "sm",
  label = "Save as template",
  title = "Save the entire current configuration as a YAML template",
  dialogTitle = "Save profile as template",
  dialogDescription = (
    <>
      Saves the entire current configuration to a YAML file under the templates directory.
      Use a relative path for subfolders (e.g.{" "}
      <code className="font-mono text-xs">blue_origin/ng3.yaml</code>).
    </>
  ),
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
        title={isValid ? title : "Fix validation errors before saving"}
      >
        <Save className="mr-1 h-4 w-4" /> {label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
            <DialogDescription>{dialogDescription}</DialogDescription>
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
              <Save className="mr-1 h-4 w-4" /> Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
