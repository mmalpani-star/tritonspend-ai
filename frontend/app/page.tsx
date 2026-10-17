"use client";

import { ArrowRight, CircleHelp, Sparkles, WalletCards } from "lucide-react";
import { useState } from "react";
import { ForecastForm } from "../components/forecast-form";
import { ForecastDashboard } from "../components/forecast-dashboard";
import { ThemeSwitcher } from "../components/theme-switcher";
import { createForecast } from "../lib/api";
import { ForecastRequest, ForecastResponse } from "../lib/types";

export default function Home() {
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
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 lg:px-8">
        <div className="flex items-center gap-3"><div className="brand-mark"><WalletCards size={21} /></div><div><span className="block font-display text-lg font-bold tracking-tight text-[var(--text)]">TritonSpend <span className="text-[var(--primary)]">AI</span></span><span className="hidden text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--text-muted)] sm:block">Student dining planning</span></div></div>
        <div className="flex items-center gap-3"><span className="hidden items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] md:flex"><CircleHelp size={14} /> Built for your own account rules</span><ThemeSwitcher /></div>
      </header>
      <div className="mx-auto max-w-7xl px-5 pb-16 lg:px-8">
        <section className="hero-grid">
          <div className="py-10 lg:py-16"><p className="eyebrow flex items-center gap-2"><Sparkles size={15} /> A clearer way to plan campus meals</p><h1 className="hero-title">Make your <span>Dining Dollars</span> last.</h1><p className="hero-copy">Plan your meals. Forecast your balances. Spend with confidence — using your own habits and explicit account eligibility.</p><a href="#forecast-form" className="primary-button inline-flex">Create a forecast <ArrowRight size={17} /></a></div>
          <div className="hero-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="art-card art-card-main"><span className="metric-label">Runway snapshot</span><strong>$24.80</strong><span className="metric-note">per day cap · illustrative</span></div><div className="art-card art-card-small"><span className="dot" /> Accounts stay separate</div></div>
        </section>
        <section id="forecast-form" className="main-grid">
          <div className="panel form-panel"><div className="panel-heading"><div><p className="eyebrow">Build a forecast</p><h2 className="panel-title">Start with what you know.</h2></div><span className="step-badge">01</span></div><p className="mb-7 text-sm leading-6 text-[var(--text-muted)]">Use cents-accurate balances and fraction-style frequencies. Your account eligibility is always explicit — no UCSD payment rules are assumed.</p><ForecastForm loading={loading} onSubmit={submit} /></div>
          <div className="result-column">{apiError && <div className="error-box mb-5" role="alert"><strong>Couldn’t build that forecast.</strong><span>{apiError}</span></div>}{result ? <ForecastDashboard result={result} /> : <div className="empty-result"><div className="empty-icon"><WalletCards size={25} /></div><h2>Results will meet you here.</h2><p>Once you submit your dates, balances, and habits, you&apos;ll see wallet-by-wallet runway, daily spending, and any unfunded amount.</p><div className="empty-rule"><span /> Estimates are planning tools, not guarantees <span /></div></div>}</div>
        </section>
      </div>
      <footer className="mx-auto flex max-w-7xl flex-col gap-2 border-t border-[var(--border)] px-5 py-6 text-xs text-[var(--text-muted)] sm:flex-row sm:items-center sm:justify-between lg:px-8"><span>TritonSpend AI · Keep your own account rules in the driver&apos;s seat.</span><span>Forecasts are illustrative planning estimates.</span></footer>
    </main>
  );
}
