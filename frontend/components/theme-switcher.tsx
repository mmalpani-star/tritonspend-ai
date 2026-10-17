"use client";

import { Check, Palette } from "lucide-react";
import { Theme, useTheme } from "./theme-provider";

const themes: { value: Theme; label: string; note: string }[] = [
  { value: "classic", label: "Classic Triton", note: "Light + blue" },
  { value: "midnight", label: "Midnight Triton", note: "Deep navy" },
  { value: "formal", label: "Formal Triton", note: "Warm sand" },
  { value: "coastal", label: "Coastal Triton", note: "Turquoise" }
];

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <details className="relative">
      <summary className="flex list-none items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm font-semibold text-[var(--text)] shadow-sm transition hover:border-[var(--primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]">
        <Palette size={16} aria-hidden="true" />
        <span className="hidden sm:inline">Theme</span>
        <span className="text-[var(--primary)]">{themes.find((item) => item.value === theme)?.label}</span>
      </summary>
      <div className="absolute right-0 z-20 mt-2 w-64 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-2 shadow-xl">
        {themes.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setTheme(item.value)}
            className="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left transition hover:bg-[var(--surface-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
          >
            <span>
              <span className="block text-sm font-semibold text-[var(--text)]">{item.label}</span>
              <span className="block text-xs text-[var(--text-muted)]">{item.note}</span>
            </span>
            {theme === item.value && <Check size={17} className="text-[var(--primary)]" aria-label="Selected" />}
          </button>
        ))}
      </div>
    </details>
  );
}
