"use client";

import Image from "next/image";
import { KeyboardEvent, useRef, useState } from "react";
import { THEMES, Theme } from "../lib/theme";
import { useTheme } from "./theme-provider";

export const THEME_LABELS: Record<Theme, { short: string; full: string; note: string }> = {
  classic: { short: "Classic", full: "Classic Triton", note: "Light + blue" },
  midnight: { short: "Midnight", full: "Midnight Triton", note: "Deep navy" },
  formal: { short: "Formal", full: "Formal Triton", note: "Warm sand" },
  coastal: { short: "Coastal", full: "Coastal Triton", note: "Turquoise" }
};

const KEY_STEPS: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

/**
 * Segmented theme slider whose thumb is the UC San Diego trident. The thumb's
 * position is driven by html[data-theme] in CSS, so it is correct before hydration.
 */
export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  // Increments on each change so the glow, shimmer, and trident pop replay once.
  const [changes, setChanges] = useState(0);
  const options = useRef<(HTMLButtonElement | null)[]>([]);

  function select(next: Theme) {
    if (next === theme) return;
    setTheme(next);
    setChanges((count) => count + 1);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let target: number;
    if (event.key in KEY_STEPS) target = (index + KEY_STEPS[event.key] + THEMES.length) % THEMES.length;
    else if (event.key === "Home") target = 0;
    else if (event.key === "End") target = THEMES.length - 1;
    else return;
    event.preventDefault();
    select(THEMES[target]);
    options.current[target]?.focus();
  }

  return (
    <div role="radiogroup" aria-label="Color theme" className="theme-slider w-full sm:w-[23rem]">
      {changes > 0 && <span key={`shimmer-${changes}`} className="theme-slider-shimmer" aria-hidden="true" />}
      <span className="theme-slider-indicator" aria-hidden="true">
        {changes > 0 && <span key={`glow-${changes}`} className="theme-slider-glow" />}
        <Image
          key={`trident-${changes}`}
          src="/brand/ucsd-trident-gold.png"
          alt=""
          width={28}
          height={28}
          priority
          className={`theme-slider-trident ${changes > 0 ? "theme-slider-trident-pop" : ""}`}
        />
      </span>
      {THEMES.map((value, index) => {
        const selected = theme === value;
        return (
          <button
            key={value}
            ref={(element) => {
              options.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={`${THEME_LABELS[value].full} theme`}
            title={`${THEME_LABELS[value].full} · ${THEME_LABELS[value].note}`}
            tabIndex={selected ? 0 : -1}
            className="theme-slider-option"
            onClick={() => select(value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <span>{THEME_LABELS[value].short}</span>
          </button>
        );
      })}
    </div>
  );
}
