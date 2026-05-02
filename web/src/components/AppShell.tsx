import { NavLink, Outlet } from "react-router-dom";
import { BookOpen, Cog, Crosshair, FolderOpen, PanelLeft, Play } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMeta } from "@/lib/meta";
import { useSidebar } from "@/lib/sidebar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { to: "/", label: "Run", icon: Play, end: true },
  { to: "/calibrate", label: "Calibrate", icon: Crosshair },
  { to: "/templates", label: "Templates", icon: FolderOpen },
  { to: "/documentation", label: "Documentation", icon: BookOpen },
];

export function AppShell() {
  const meta = useMeta();
  const { collapsed, toggle } = useSidebar();
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <aside
        aria-hidden={collapsed}
        className={cn(
          "hidden h-screen shrink-0 overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out md:block",
          collapsed ? "w-0 border-r-0" : "w-64",
        )}
      >
        <div className="hidden h-full w-64 flex-col md:flex">
          <div className="flex items-center justify-between gap-2 px-5 py-5">
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                <Cog className="h-5 w-5" />
              </div>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-sm font-semibold tracking-tight">webcalyzer</div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  telemetry studio
                </div>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              className="h-7 w-7"
              title="Toggle sidebar"
              aria-label="Toggle sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <nav className="flex flex-col gap-1 px-3 pb-3">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-sidebar-accent text-foreground"
                        : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
            <div className="mt-auto space-y-3 border-t border-sidebar-border px-5 py-4 text-xs text-muted-foreground">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground/70">
                  Templates dir
                </div>
                <div className="mt-1 truncate font-mono text-[11px]">
                  {meta?.templates_dir || "-"}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground/70">
                  Browsable roots
                </div>
                <div className="mt-1 space-y-1">
                  {meta?.roots.map((root) => (
                    <div key={root.path} className="truncate font-mono text-[11px]">
                      {root.path}
                    </div>
                  ))}
                </div>
              </div>
              <Badge variant="outline" className="mt-2">
                v{meta?.version || "0.1.0"}
              </Badge>
            </div>
          </div>
        </div>
      </aside>
      <main className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <nav
          aria-label="Primary"
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-border/60 bg-background/90 p-2 md:hidden"
        >
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-xs font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
