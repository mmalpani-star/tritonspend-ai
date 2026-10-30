"use client";

import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { useWallet } from "../lib/wallet";
import { ForecastHistoryPanel } from "./forecast-history-panel";
import { CampusStrip } from "./visual/campus-strip";
import { ManualForecast } from "./manual-forecast";

type Mode = "saved" | "manual";

type Props = { onBack: () => void; onOpenWallet: () => void; onOpenTrajectory: () => void };

export function CreateForecastView({ onBack, onOpenWallet, onOpenTrajectory }: Props) {
  const [mode, setMode] = useState<Mode>("saved");
  const [wallet] = useWallet();
  return (
    <section aria-labelledby="create-forecast-title">
      <button type="button" className="secondary-button mb-6" onClick={onBack}><ArrowLeft size={14} aria-hidden="true" /> Back to dashboard</button>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Create Forecast</p>
          <h1 id="create-forecast-title" className="panel-title text-3xl">How long will your balances last?</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
            Your forecast uses your latest saved wallet balances and eating habits. Every forecast is saved to your account, so you can revisit and compare previous plans.
          </p>
        </div>
        <div className="scale-selector mb-0" role="group" aria-label="Forecast type">
          <button type="button" className={`scale-button ${mode === "saved" ? "scale-button-selected" : ""}`} aria-pressed={mode === "saved"} onClick={() => setMode("saved")}>Saved forecast</button>
          <button type="button" className={`scale-button ${mode === "manual" ? "scale-button-selected" : ""}`} aria-pressed={mode === "manual"} onClick={() => setMode("manual")}>Quick estimate</button>
        </div>
      </div>
      <CampusStrip photo="eucalyptusWalk" position="object-[50%_55%]">
        <p className="campus-hero-eyebrow">Plan the quarter</p>
        <p className="mt-2 font-display text-xl font-bold tracking-tight">Walk into every week knowing your runway.</p>
      </CampusStrip>
      {/* Both stay mounted so switching modes keeps form input and results. */}
      <div hidden={mode !== "saved"}><ForecastHistoryPanel wallet={wallet} onOpenWallet={onOpenWallet} onOpenTrajectory={onOpenTrajectory} /></div>
      <div hidden={mode !== "manual"}>
        <p className="mb-4 text-sm text-[var(--text-muted)]">Try a what-if with any balances. Quick estimates aren’t saved and don’t change your wallet.</p>
        <ManualForecast />
      </div>
    </section>
  );
}
