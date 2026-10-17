"use client";

import { createContext, useContext, useEffect, useState } from "react";

export type Theme = "classic" | "midnight" | "formal" | "coastal";

const ThemeContext = createContext<{ theme: Theme; setTheme: (theme: Theme) => void } | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("classic");

  useEffect(() => {
    const saved = window.localStorage.getItem("tritonspend-theme") as Theme | null;
    if (saved && ["classic", "midnight", "formal", "coastal"].includes(saved)) setTheme(saved);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme === "classic" ? "classic" : theme;
    window.localStorage.setItem("tritonspend-theme", theme);
  }, [theme]);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
