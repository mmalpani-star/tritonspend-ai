"use client";

import { ArrowLeft, Clock } from "lucide-react";
import type { ReactNode } from "react";

type Props = {
  title: string;
  description: string;
  icon: ReactNode;
  planned: string[];
  note?: ReactNode;
  /** Optional decorative preview shown above the details. */
  visual?: ReactNode;
  onBack: () => void;
};

/** Clearly marked placeholder for a product area that is not built yet. */
export function ComingSoon({ title, description, icon, planned, note, visual, onBack }: Props) {
  return (
    <section className="panel" aria-labelledby="coming-soon-title">
      <button type="button" className="secondary-button mb-6" onClick={onBack}><ArrowLeft size={14} aria-hidden="true" /> Back to dashboard</button>
      {visual}
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
        <div className="empty-icon mb-0 shrink-0">{icon}</div>
        <div className="min-w-0">
          <span className="feature-badge inline-flex items-center gap-1.5"><Clock size={12} aria-hidden="true" /> Coming soon</span>
          <h1 id="coming-soon-title" className="panel-title mt-3 text-3xl">{title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">{description}</p>
          <h2 className="mt-6 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Planned</h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {planned.map((item) => <li key={item} className="runway-row planned-item justify-start">{item}</li>)}
          </ul>
          {note && <p className="field-help mt-5 text-xs">{note}</p>}
        </div>
      </div>
    </section>
  );
}
