import { useState } from "react";
import { Folder } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FileBrowserDialog } from "./FileBrowserDialog";

type Props = {
  value: string;
  onChange: (next: string) => void;
  mode: "video" | "directory";
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
};

export function PathPicker({ value, onChange, mode, placeholder, disabled, invalid }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        className={invalid ? "border-destructive font-mono text-xs" : "font-mono text-xs"}
        disabled={disabled}
      />
      <Button type="button" variant="outline" size="icon" onClick={() => setOpen(true)} disabled={disabled}>
        <Folder className="h-4 w-4" />
      </Button>
      <FileBrowserDialog
        open={open}
        onOpenChange={setOpen}
        mode={mode}
        initialPath={value || null}
        onSelect={(path) => {
          onChange(path);
          setOpen(false);
        }}
      />
    </div>
  );
}
