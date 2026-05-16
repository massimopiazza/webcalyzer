import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "webcalyzer.sidebar.collapsed";

type SidebarContextValue = {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (next: boolean) => void;
};

const SidebarContext = createContext<SidebarContextValue | null>(null);

function readInitial(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsedState] = useState<boolean>(() => readInitial());

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  const setCollapsed = useCallback((next: boolean) => setCollapsedState(next), []);
  const toggle = useCallback(() => setCollapsedState((prev) => !prev), []);

  const value = useMemo(() => ({ collapsed, toggle, setCollapsed }), [collapsed, toggle, setCollapsed]);
  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (!ctx) {
    // Sensible fallback when used outside the provider (e.g. tests).
    return { collapsed: false, toggle: () => undefined, setCollapsed: () => undefined };
  }
  return ctx;
}
