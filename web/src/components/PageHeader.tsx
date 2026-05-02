import * as React from "react";
import { PanelLeft } from "lucide-react";
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
      <div className="flex flex-col gap-3 px-4 py-3 sm:px-6 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          {collapsed && (
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              className="-ml-2 mt-0.5 h-7 w-7 shrink-0"
              title="Toggle sidebar"
              aria-label="Toggle sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          )}
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
            {description && (
              <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
            )}
            {badges && <div className="mt-2 flex flex-wrap items-center gap-2">{badges}</div>}
          </div>
        </div>
        {actions && (
          <div className="flex w-full flex-wrap items-center gap-2 md:w-auto md:justify-end">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
