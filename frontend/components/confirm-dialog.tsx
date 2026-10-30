"use client";

import { type ReactNode, useEffect, useId, useRef } from "react";

type Props = {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  error?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * A modal confirmation built on the native <dialog>: focus stays inside while it
 * is open, Escape cancels, and focus returns to the opener when it closes.
 * Nothing happens until the confirm button is pressed.
 */
export function ConfirmDialog({ open, title, children, confirmLabel, busy = false, error, onConfirm, onCancel }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const bodyId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      cancelRef.current?.focus(); // the safe choice gets initial focus
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="confirm-dialog"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      onCancel={(event) => {
        event.preventDefault(); // keep React in control of `open`
        if (!busy) onCancel();
      }}
      onClick={(event) => {
        if (event.target === ref.current && !busy) onCancel(); // backdrop click
      }}
    >
      <div className="confirm-dialog-body">
        <h2 id={titleId} className="font-display text-xl font-bold text-[var(--text)]">{title}</h2>
        <div id={bodyId} className="mt-3 space-y-2 text-sm leading-6 text-[var(--text-muted)]">{children}</div>
        {error && <p role="alert" className="error-box mt-4">{error}</p>}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button ref={cancelRef} type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Cancel</button>
          <button type="button" className="primary-button danger-fill" disabled={busy} onClick={onConfirm}>{busy ? "Deleting…" : confirmLabel}</button>
        </div>
      </div>
    </dialog>
  );
}
