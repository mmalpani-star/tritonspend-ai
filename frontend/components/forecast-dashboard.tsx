"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, CheckCircle2, CircleAlert, WalletCards } from "lucide-react";
import { formatCalendarDate, mondayOf } from "../lib/datetime";
import { DailyForecast, ForecastResponse } from "../lib/types";
import { AnimatedMoney } from "./visual/animated-money";

type Scale = "daily" | "weekly" | "monthly";
type Period = { key: string; label: string; start: string; end: string; cents: number; days: DailyForecast[] };

const money = (cents: number) => new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
}).format(cents / 100);
const shortDate = (date: string) => formatCalendarDate(date, { month: "short", day: "numeric" });
const monthLabel = (date: string) => formatCalendarDate(date, { month: "long", year: "numeric" });
const longDate = (date: string) => formatCalendarDate(date);

function makePeriods(days: DailyForecast[], scale: Scale): Period[] {
  const groups = new Map<string, DailyForecast[]>();
  days.forEach((day) => {
    const key = scale === "daily" ? day.date : scale === "weekly" ? mondayOf(day.date) : day.date.slice(0, 7);
    groups.set(key, [...(groups.get(key) ?? []), day]);
  });
  return [...groups.entries()].map(([key, groupedDays]) => {
    const start = groupedDays[0].date;
    const end = groupedDays[groupedDays.length - 1].date;
    const label = scale === "daily"
      ? shortDate(start)
      : scale === "weekly"
        ? `${shortDate(start)} – ${shortDate(end)}`
        : monthLabel(start);
    return { key, label, start, end, cents: groupedDays.reduce((total, day) => total + day.expected_spending_cents, 0), days: groupedDays };
  });
}

function PeriodDetail({ period, scale }: { period: Period; scale: Scale }) {
  const lastDay = period.days[period.days.length - 1];
  return (
    <div className="period-detail" aria-live="polite">
      <div>
        <p className="eyebrow">{scale === "daily" ? "Selected day" : `Selected ${scale.slice(0, -2) === "week" ? "week" : "month"}`}</p>
        <h4 className="period-detail-title">{scale === "daily" ? longDate(period.start) : period.label}</h4>
      </div>
      <div className="period-detail-total">{money(period.cents)}</div>
      <div className="period-detail-meta">
        <span>{period.days.length} {period.days.length === 1 ? "day" : "days"} in forecast</span>
        <span>DD {money(lastDay.paid_dining_dollars_cents)}</span>
        <span>Cash {money(lastDay.paid_triton_cash_cents)}</span>
        {lastDay.unfunded_cents > 0 && <span className="text-[var(--danger)]">Unfunded {money(lastDay.unfunded_cents)}</span>}
      </div>
    </div>
  );
}

function SpendingChart({ periods, selectedKey, onSelect }: { periods: Period[]; selectedKey: string; onSelect: (key: string) => void }) {
  const maxSpend = Math.max(...periods.map((period) => period.cents), 1);
  return (
    <div className="spending-chart" role="img" aria-label="Spending by selected time period">
      <div className="chart-axis" aria-hidden="true"><span>{money(maxSpend)}</span><span>{money(Math.round(maxSpend / 2))}</span><span>$0.00</span></div>
      <div className="chart-bars">
        {periods.map((period, index) => (
          <button
            type="button"
            key={period.key}
            className={`chart-bar-button ${period.key === selectedKey ? "chart-bar-selected" : ""}`}
            onClick={() => onSelect(period.key)}
            aria-label={`${period.label}: ${money(period.cents)}`}
            aria-pressed={period.key === selectedKey}
            title={`${period.label}: ${money(period.cents)}`}
          >
            <span className="chart-bar-track"><span className="chart-bar" style={{ height: `${Math.max((period.cents / maxSpend) * 100, period.cents > 0 ? 4 : 0)}%`, "--i": index } as React.CSSProperties} /></span>
            <span className="chart-label">{period.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ForecastDashboard({ result }: { result: ForecastResponse }) {
  const [scale, setScale] = useState<Scale>("daily");
  const [page, setPage] = useState(0);
  const [selectedKey, setSelectedKey] = useState(result.days[0]?.date ?? "");
  const totalProjected = result.days.reduce((total, day) => total + day.expected_spending_cents, 0);
  const periods = useMemo(() => makePeriods(result.days, scale), [result.days, scale]);
  const pageCount = Math.max(1, Math.ceil(periods.length / 10));
  const visiblePeriods = periods.slice(page * 10, page * 10 + 10);
  const selectedPeriod = periods.find((period) => period.key === selectedKey) ?? visiblePeriods[0];

  useEffect(() => {
    setPage((currentPage) => Math.min(currentPage, Math.max(pageCount - 1, 0)));
    if (!periods.some((period) => period.key === selectedKey)) {
      setSelectedKey(periods[0]?.key ?? "");
    }
  }, [pageCount, periods, selectedKey]);

  const changeScale = (nextScale: Scale) => {
    setScale(nextScale);
    setPage(0);
    const nextPeriods = makePeriods(result.days, nextScale);
    setSelectedKey(nextPeriods[0]?.key ?? "");
  };

  const changePage = (nextPage: number) => {
    const boundedPage = Math.max(0, Math.min(nextPage, pageCount - 1));
    setPage(boundedPage);
    setSelectedKey(periods[boundedPage * 10]?.key ?? "");
  };

  return (
    <section aria-live="polite" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow">Forecast result</p><h2 className="section-title">Your plan, in clear numbers.</h2><p className="mt-2 text-sm text-[var(--text-muted)]">{result.days[0] ? `${shortDate(result.days[0].date)} — ${shortDate(result.days[result.days.length - 1].date)}` : "No forecast dates"} · {result.scenario} scenario · illustrative estimate</p></div>
        <div className={`status-pill ${result.funds_last ? "status-good" : "status-danger"}`}>{result.funds_last ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}{result.funds_last ? "Funds projected to last" : "Unfunded spending projected"}</div>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="metric-card"><span className="metric-label">Projected spending</span><strong><AnimatedMoney cents={totalProjected} /></strong><span className="metric-note">{result.days.length} projected days</span></div>
        <div className="metric-card"><span className="metric-label">Dining Dollars left</span><strong><AnimatedMoney cents={result.projected_balances.dining_dollars_cents} /></strong><span className="metric-note">Independent wallet</span></div>
        <div className="metric-card"><span className="metric-label">Triton Cash left</span><strong><AnimatedMoney cents={result.projected_balances.triton_cash_cents} /></strong><span className="metric-note">Independent wallet</span></div>
      </div>
      {result.total_unfunded_cents > 0 && <div className="notice-danger"><ArrowDownRight size={18} /><span><strong>{money(result.total_unfunded_cents)}</strong> of projected expenses are unfunded. Accounts are never substituted silently.</span></div>}
      <div className="dashboard-grid">
        <div className="panel">
          <div className="panel-heading"><div><p className="eyebrow">Spending timeline</p><h3 className="panel-title">Projected spending</h3></div><WalletCards size={20} className="text-[var(--primary)]" /></div>
          <div className="scale-selector" role="group" aria-label="Spending time scale">
            {(["daily", "weekly", "monthly"] as Scale[]).map((option) => <button type="button" key={option} className={`scale-button ${scale === option ? "scale-button-selected" : ""}`} onClick={() => changeScale(option)} aria-pressed={scale === option}>{option[0].toUpperCase() + option.slice(1)}</button>)}
          </div>
          {periods.length === 0 ? <div className="chart-empty">No daily spending data is available for this forecast.</div> : (
            <>
              <p className="chart-caption">Bars show actual projected spending returned by the forecast. Select a bar to inspect its period.</p>
              <SpendingChart periods={visiblePeriods} selectedKey={selectedPeriod?.key ?? ""} onSelect={setSelectedKey} />
              <div className="pagination-row"><span>{scale[0].toUpperCase() + scale.slice(1)} periods {page * 10 + 1}–{Math.min((page + 1) * 10, periods.length)} of {periods.length}</span><div className="pagination-controls"><button type="button" className="secondary-button" onClick={() => changePage(page - 1)} disabled={page === 0}><ArrowLeft size={14} /> Previous</button><button type="button" className="secondary-button" onClick={() => changePage(page + 1)} disabled={page === pageCount - 1}>Next <ArrowRight size={14} /></button></div></div>
              {selectedPeriod && <PeriodDetail period={selectedPeriod} scale={scale} />}
            </>
          )}
        </div>
        <div className="panel">
          <div className="panel-heading"><div><p className="eyebrow">Guardrails</p><h3 className="panel-title">Wallet runway caps</h3></div><ArrowUpRight size={20} className="text-[var(--accent)]" /></div>
          <p className="mb-5 text-sm leading-6 text-[var(--text-muted)]">These caps divide each starting wallet across the projected period. They are not meal recommendations and do not account for habit eligibility.</p>
          <div className="space-y-3"><div className="runway-row"><span>Dining Dollars / day</span><strong>{money(result.limits.daily_wallet_runway_caps.dining_dollars_cents)}</strong></div><div className="runway-row"><span>Triton Cash / day</span><strong>{money(result.limits.daily_wallet_runway_caps.triton_cash_cents)}</strong></div></div>
          <details className="weekly-caps">
            <summary>View weekly wallet runway caps</summary>
            <div className="mt-3 space-y-2">{Object.entries(result.limits.weekly_wallet_runway_caps).map(([week, cap]) => <div className="runway-row text-sm" key={week}><span>Week of {shortDate(week)}</span><span><strong>{money(cap.dining_dollars_cents)}</strong> DD · <strong>{money(cap.triton_cash_cents)}</strong> Cash</span></div>)}</div>
          </details>
        </div>
      </div>
    </section>
  );
}
