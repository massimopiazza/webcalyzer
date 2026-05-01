import { useEffect, useState } from "react";
import { Download, FileText, RefreshCw, Trash2, Upload } from "lucide-react";
import { ApiError, TemplateSummary, api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Textarea } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageHeader } from "@/components/PageHeader";
import { formatBytes, formatTimeAgo } from "@/lib/utils";
import { toast } from "sonner";

export function TemplatesPage() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importName, setImportName] = useState("");
  const [importYaml, setImportYaml] = useState("");

  const refresh = async () => {
    try {
      setLoading(true);
      setTemplates(await api.templates());
    } catch (err) {
      toast.error((err as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const remove = async (name: string) => {
    if (!confirm(`Delete template ${name}? This cannot be undone.`)) return;
    try {
      await api.deleteTemplate(name);
      toast.success(`Deleted ${name}`);
      refresh();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  const importTemplate = async () => {
    if (!importName.trim()) {
      toast.error("Provide a name for the template.");
      return;
    }
    try {
      await api.importTemplate(importName.trim(), importYaml);
      toast.success(`Imported ${importName.trim()}`);
      setImportOpen(false);
      setImportName("");
      setImportYaml("");
      refresh();
    } catch (err) {
      toast.error((err as ApiError).message);
    }
  };

  return (
    <>
      <PageHeader
        title="Templates"
        description="YAML profiles stored under the templates directory. Open the Run page to load and edit one."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={refresh}>
              <RefreshCw className={loading ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            </Button>
            <Button size="sm" onClick={() => setImportOpen(true)}>
              <Upload className="mr-1 h-4 w-4" /> Import YAML
            </Button>
          </>
        }
      />

      <div className="mx-auto w-full max-w-5xl space-y-5 p-6">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle>{templates.length} template{templates.length === 1 ? "" : "s"}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="max-h-[60vh]">
            {templates.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">
                No templates yet. Save one from the Run page or import a YAML.
              </div>
            )}
            <ul className="divide-y divide-border/60">
              {templates.map((tpl) => (
                <li
                  key={tpl.name}
                  className="flex flex-wrap items-center gap-3 p-4 hover:bg-muted/30"
                >
                  <FileText className="h-4 w-4 text-primary" />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-mono text-sm">{tpl.name}</span>
                      {tpl.error && (
                        <Badge variant="destructive">parse error</Badge>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {tpl.profile_name}
                      {tpl.description ? ` — ${tpl.description}` : ""}
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                      {formatBytes(tpl.size)} · {formatTimeAgo(tpl.modified)}
                    </div>
                  </div>
                  <Button asChild size="sm" variant="outline">
                    <a href={api.templateYamlUrl(tpl.name)} target="_blank" rel="noreferrer">
                      <Download className="mr-1 h-3 w-3" /> YAML
                    </a>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => remove(tpl.name)}
                  >
                    <Trash2 className="h-3 w-3 text-destructive/80" />
                  </Button>
                </li>
              ))}
            </ul>
          </ScrollArea>
        </CardContent>
      </Card>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Import a YAML template</DialogTitle>
            <DialogDescription>
              Paste an existing webcalyzer profile YAML. The structure is validated before saving.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="my_profile.yaml"
              value={importName}
              onChange={(e) => setImportName(e.target.value)}
              spellCheck={false}
              className="font-mono"
            />
            <Textarea
              placeholder="profile_name: …"
              value={importYaml}
              onChange={(e) => setImportYaml(e.target.value)}
              rows={14}
              spellCheck={false}
              className="font-mono text-xs"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setImportOpen(false)}>
              Cancel
            </Button>
            <Button onClick={importTemplate}>
              <Upload className="mr-1 h-4 w-4" /> Import
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </div>
    </>
  );
}
