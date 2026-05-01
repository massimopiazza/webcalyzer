import * as React from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type Props = {
  label: string;
  hint?: string;
  error?: string | null;
  className?: string;
  children: React.ReactNode;
  required?: boolean;
  tooltip?: React.ReactNode;
  disabled?: boolean;
};

export function Field({
  label,
  hint,
  error,
  className,
  children,
  required,
  tooltip,
  disabled,
}: Props) {
  return (
    <div className={cn("space-y-1.5", disabled && "opacity-60", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <Label className="flex items-center gap-1.5">
          <span>{label}</span>
          {required && <span className="text-destructive/80">*</span>}
          {tooltip && (
            <Tooltip delayDuration={150}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={`What is ${label}?`}
                  className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-muted-foreground/70 transition-colors hover:text-primary"
                >
                  <Info className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">{tooltip}</TooltipContent>
            </Tooltip>
          )}
        </Label>
        {hint && <span className="text-[10px] uppercase text-muted-foreground/70">{hint}</span>}
      </div>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function Section({
  title,
  description,
  children,
  className,
}: {
  title?: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3", className)}>
      {(title || description) && (
        <div>
          {title && <h3 className="text-sm font-semibold">{title}</h3>}
          {description && (
            <p className="text-xs text-muted-foreground/80">{description}</p>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
