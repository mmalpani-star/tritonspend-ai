"use client";

import { WalletCards } from "lucide-react";
import { useState } from "react";
import { ForecastDashboard } from "./forecast-dashboard";
import { ForecastForm } from "./forecast-form";
import { createForecast } from "../lib/api";
import { ForecastRequest, ForecastResponse } from "../lib/types";

/** Anonymous forecast from manually entered balances; nothing is saved. */
export function ManualForecast() {
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState("");

  async function submit(request: ForecastRequest) {
    setLoading(true);
    setApiError("");
    try {
      setResult(await createForecast(request));
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "The forecast service is unavailable.");
      throw error;
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="forecast-form" className="main-grid">
      <div className="panel form-panel"><div className="panel-heading"><div><p className="eyebrow">Build a forecast</p><h2 className="panel-title">Start with what you know.</h2></div></div><p className="mb-7 text-sm leading-6 text-[var(--text-muted)]">Use dollar amounts with up to two decimal places and fraction-style frequencies. Your account eligibility is always explicit — no UCSD payment rules are assumed.</p><ForecastForm loading={loading} onSubmit={submit} /></div>
      <div className="result-column">{apiError && <div className="error-box mb-5" role="alert"><strong>Couldn’t build that forecast.</strong><span>{apiError}</span></div>}{result ? <ForecastDashboard result={result} /> : <div className="empty-result"><div className="empty-icon"><WalletCards size={25} /></div><h2>Results will meet you here.</h2><p>Once you submit your dates, balances, and habits, you&apos;ll see wallet-by-wallet runway, daily spending, and any unfunded amount.</p><div className="empty-rule"><span /> Estimates are planning tools, not guarantees <span /></div></div>}</div>
    </section>
  );
}
