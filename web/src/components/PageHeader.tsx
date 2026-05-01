import * as React from "react";
import { PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSidebar } from "@/lib/sidebar";
import { cn } from "@/lib/utils";

type Props = {
  title: string;
  description?: React.ReactNode;
  badges?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
};

export function PageHeader({ title, description, badges, actions, className }: Props) {
  const { collapsed, toggle } = useSidebar();
  return (
    <div
      className={cn(
        "sticky top-0 z-30 border-b border-border/60 bg-background/65 backdrop-blur-md backdrop-saturate-150 supports-[backdrop-filter]:bg-background/55",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 px-6 py-4">
        <div className="flex min-w-0 items-start gap-2">
          {collapsed && (
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              className="-ml-2 mt-0.5 shrink-0"
              title="Show sidebar"
              aria-label="Show sidebar"
            >
              <PanelLeftOpen className="h-4 w-4" />
            </Button>
          )}
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
            {description && (
              <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
            )}
            {badges && <div className="mt-2 flex flex-wrap items-center gap-2">{badges}</div>}
          </div>
        </div>
        {actions && (
          <div className="flex flex-wrap items-center justify-end gap-2">{actions}</div>
        )}
      </div>
    </div>
  );
}
