"use client";

import { Info } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

/**
 * A field label with a small "i" button that opens a short explanation.
 * Opens on click or tap (not hover) so it works on touch screens; Escape or a
 * click elsewhere closes it. The button sits beside the <label>, never inside
 * it, so the label stays associated with its input.
 */
export function InfoLabel({ htmlFor, label, children }: { htmlFor: string; label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const popoverId = useId();
  const wrapper = useRef<HTMLSpanElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <span ref={wrapper} className="info-label">
      <label htmlFor={htmlFor}>{label}</label>
      <button
        ref={button}
        type="button"
        className="info-button"
        aria-label={`What is ${label}?`}
        aria-expanded={open}
        aria-controls={popoverId}
        onClick={() => setOpen((value) => !value)}
      >
        <Info size={14} aria-hidden="true" />
      </button>
      <span id={popoverId} role="note" hidden={!open} className="info-popover">{children}</span>
    </span>
  );
}
