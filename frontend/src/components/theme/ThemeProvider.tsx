"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "hodi-theme";
const CHANGE_EVENT = "hodi-theme-change";
let memoryTheme: Theme | null = null;

type ThemeContextValue = { theme: Theme; setTheme: (theme: Theme) => void };
const ThemeContext = createContext<ThemeContextValue | null>(null);

function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "dark";
}

function savedTheme(): Theme | null {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isTheme(saved)) return saved;
  } catch {
    // Storage can be blocked. The in-memory choice still applies for this tab.
  }
  return memoryTheme;
}

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function currentTheme(): Theme {
  return savedTheme() ?? systemTheme();
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

function subscribe(onStoreChange: () => void) {
  const notify = () => {
    applyTheme(currentTheme());
    onStoreChange();
  };
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener(CHANGE_EVENT, notify);
  window.addEventListener("storage", notify);
  media.addEventListener("change", notify);
  return () => {
    window.removeEventListener(CHANGE_EVENT, notify);
    window.removeEventListener("storage", notify);
    media.removeEventListener("change", notify);
  };
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(subscribe, currentTheme, () => "light" as Theme);

  const setTheme = useCallback((next: Theme) => {
    memoryTheme = next;
    applyTheme(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The selected theme still applies for this page when storage is blocked.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used within ThemeProvider.");
  return context;
}
