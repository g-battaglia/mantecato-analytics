import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePreferencesStore } from "@/stores/preferences";

type Theme = "light" | "dark" | "system";
type ResolvedTheme = "light" | "dark";
type VisualStyle = "classic" | "glass";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  visualStyle: VisualStyle;
  setTheme: (theme: Theme) => void;
  setVisualStyle: (style: VisualStyle) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === "system" ? getSystemTheme() : theme;
}

function applyTheme(resolved: ResolvedTheme) {
  const root = document.documentElement;
  root.classList.remove("light", "dark");
  root.classList.add(resolved);
}

function applyVisualStyle(style: VisualStyle) {
  const root = document.documentElement;
  root.classList.remove("style-classic", "style-glass");
  root.classList.add(`style-${style}`);
}

function setCookie(theme: Theme) {
  document.cookie = `theme=${theme};path=/;max-age=${60 * 60 * 24 * 365};samesite=lax`;
}

export function ThemeProvider({
  children,
  initialTheme = "dark",
}: {
  children: React.ReactNode;
  initialTheme?: Theme;
}) {
  const storedVisualStyle = usePreferencesStore((s) => s.visualStyle);
  const storeSetVisualStyle = usePreferencesStore((s) => s.setVisualStyle);

  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(initialTheme)
  );
  const [visualStyle, setVisualStyleState] = useState<VisualStyle>(storedVisualStyle);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    const resolved = resolveTheme(next);
    setResolvedTheme(resolved);
    applyTheme(resolved);
    setCookie(next);
  }, []);

  const setVisualStyle = useCallback((style: VisualStyle) => {
    setVisualStyleState(style);
    storeSetVisualStyle(style);
    applyVisualStyle(style);
  }, [storeSetVisualStyle]);

  useEffect(() => {
    if (theme !== "system") return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      const resolved = e.matches ? "dark" : "light";
      setResolvedTheme(resolved);
      applyTheme(resolved);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  useEffect(() => {
    applyTheme(resolveTheme(theme));
  }, [theme]);

  // Apply visual style on mount and when it changes
  useEffect(() => {
    applyVisualStyle(visualStyle);
  }, [visualStyle]);

  const value = useMemo(
    () => ({ theme, resolvedTheme, visualStyle, setTheme, setVisualStyle }),
    [theme, resolvedTheme, visualStyle, setTheme, setVisualStyle]
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
