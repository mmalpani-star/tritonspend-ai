"use client";

import { ExternalLink, Star } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { FoodRoute, MAX_REPORT_DETAILS_LENGTH, REPORT_REASONS, ReportReason, foodRouteHash, parseFoodRoute } from "../../lib/food-chat";
import { formatTimestamp } from "../../lib/datetime";
import { EXTERNAL_LINK, MenuLink } from "../../lib/menu-links";

/** The current Food Nearby sub-page, kept in the URL hash so links, refresh and Back work. */
export function useFoodRoute(): [FoodRoute, (route: FoodRoute) => void] {
  const [route, setRoute] = useState<FoodRoute>({ page: "list" });
  useEffect(() => {
    const sync = () => setRoute(parseFoodRoute(window.location.hash));
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const go = useCallback((next: FoodRoute) => {
    window.location.hash = foodRouteHash(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);
  return [route, go];
}

/** Read-only stars, e.g. 4.5 -> four and a half filled. */
export function Stars({ value, size = 16, label }: { value: number | null; size?: number; label?: string }) {
  const filled = value ?? 0;
  return (
    <span className="food-stars" role="img" aria-label={label ?? (value === null ? "No rating yet" : `${value.toFixed(1)} out of 5 stars`)}>
      {[1, 2, 3, 4, 5].map((star) => {
        const fill = Math.max(0, Math.min(1, filled - (star - 1)));
        return (
          <span key={star} className="food-star" style={{ width: size, height: size }} aria-hidden="true">
            <Star size={size} className="food-star-empty" />
            <span className="food-star-fill" style={{ width: `${fill * 100}%` }}><Star size={size} /></span>
          </span>
        );
      })}
    </span>
  );
}

/** A 1-5 star picker made of radio buttons (keyboard and screen-reader friendly). */
export function StarInput({ value, onChange, name }: { value: number; onChange: (value: number) => void; name: string }) {
  return (
    <fieldset className="food-star-input">
      <legend className="sr-only">Your rating</legend>
      {[1, 2, 3, 4, 5].map((star) => (
        <label key={star} className={star <= value ? "food-star-on" : ""} title={`${star} star${star === 1 ? "" : "s"}`}>
          <input type="radio" name={name} value={star} checked={value === star} onChange={() => onChange(star)} />
          <Star size={24} aria-hidden="true" />
          <span className="sr-only">{star} star{star === 1 ? "" : "s"}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function when(timestamp: string): string {
  return formatTimestamp(timestamp, { year: false });
}

export function StatusLine({ status }: { status: { error: boolean; text: string } | null }) {
  if (!status) return null;
  return <p role={status.error ? "alert" : "status"} className={status.error ? "error-box mt-3" : "food-success mt-3"}>{status.text}</p>;
}

/** Report a review or comment: reason plus optional details, in a native modal dialog. */
export function ReportDialog({ open, what, onSubmit, onClose }: {
  open: boolean;
  what: string;
  onSubmit: (reason: ReportReason, details: string) => Promise<void>;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [reason, setReason] = useState<ReportReason>("spam");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setReason("spam");
      setDetails("");
      setError("");
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSubmit(reason, details);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Couldn't send your report.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} className="confirm-dialog" aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}
      onClick={(event) => { if (event.target === ref.current && !busy) onClose(); }}>
      <form className="confirm-dialog-body space-y-4" onSubmit={submit}>
        <h2 id={titleId} className="panel-title text-xl">Report this {what}</h2>
        <p className="text-sm text-[var(--text-muted)]">A moderator will review it. The author isn&apos;t told who reported it.</p>
        <label className="field-label">Reason
          <select value={reason} onChange={(event) => setReason(event.target.value as ReportReason)}>
            {REPORT_REASONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="field-label">Details (optional)
          <textarea rows={3} maxLength={MAX_REPORT_DETAILS_LENGTH} value={details} onChange={(event) => setDetails(event.target.value)} />
        </label>
        {error && <p role="alert" className="error-box">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="primary-button" disabled={busy}>{busy ? "Sending…" : "Send report"}</button>
        </div>
      </form>
    </dialog>
  );
}

/** An official menu, opened in a new tab (never copied into TritonSpend). `prominent` is the
 * button-style version for page headers. */
export function OfficialMenuLink({ link, prominent = false }: { link: MenuLink; prominent?: boolean }) {
  return (
    <a href={link.href} {...EXTERNAL_LINK} className={prominent ? "food-menu-cta" : "food-menu-link"} aria-label={link.description} title={link.description}>
      {link.label} <ExternalLink size={prominent ? 15 : 13} aria-hidden="true" />
    </a>
  );
}
