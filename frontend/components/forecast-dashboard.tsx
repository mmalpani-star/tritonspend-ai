import { ArrowDownRight, ArrowUpRight, CheckCircle2, CircleAlert, WalletCards } from "lucide-react";
import { ForecastResponse } from "../lib/types";

const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;
const shortDate = (date: string) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(`${date}T12:00:00`));

export function ForecastDashboard({ result }: { result: ForecastResponse }) {
  const totalProjected = result.days.reduce((total, day) => total + day.expected_spending_cents, 0);
  const maxSpend = Math.max(...result.days.map((day) => day.expected_spending_cents), 1);
  return (
    <section aria-live="polite" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow">Forecast result</p><h2 className="section-title">Your plan, in clear numbers.</h2><p className="mt-2 text-sm text-[var(--text-muted)]">{shortDate(result.days[0].date)} — {shortDate(result.days[result.days.length - 1].date)} · {result.scenario} scenario · illustrative estimate</p></div>
        <div className={`status-pill ${result.funds_last ? "status-good" : "status-danger"}`}>{result.funds_last ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}{result.funds_last ? "Funds projected to last" : "Unfunded spending projected"}</div>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="metric-card"><span className="metric-label">Projected spending</span><strong>{money(totalProjected)}</strong><span className="metric-note">{result.days.length} projected days</span></div>
        <div className="metric-card"><span className="metric-label">Dining Dollars left</span><strong>{money(result.projected_balances.dining_dollars_cents)}</strong><span className="metric-note">Independent wallet</span></div>
        <div className="metric-card"><span className="metric-label">Triton Cash left</span><strong>{money(result.projected_balances.triton_cash_cents)}</strong><span className="metric-note">Independent wallet</span></div>
      </div>
      {result.total_unfunded_cents > 0 && <div className="notice-danger"><ArrowDownRight size={18} /><span><strong>{money(result.total_unfunded_cents)}</strong> of projected expenses are unfunded. Accounts are never substituted silently.</span></div>}
      <div className="dashboard-grid">
        <div className="panel">
          <div className="panel-heading"><div><p className="eyebrow">By day</p><h3 className="panel-title">Expected spending</h3></div><WalletCards size={20} className="text-[var(--primary)]" /></div>
          <div className="space-y-4">
            {result.days.map((day) => <div key={day.date}><div className="mb-2 flex justify-between text-sm"><span className="font-semibold text-[var(--text)]">{shortDate(day.date)}</span><span className="text-[var(--text-muted)]">{money(day.expected_spending_cents)}</span></div><div className="h-2 overflow-hidden rounded-full bg-[var(--surface-muted)]"><div className="h-full rounded-full bg-[var(--primary)] transition-all" style={{ width: `${Math.max((day.expected_spending_cents / maxSpend) * 100, 3)}%` }} /></div><div className="mt-2 flex gap-3 text-xs text-[var(--text-muted)]"><span>DD {money(day.paid_dining_dollars_cents)}</span><span>Cash {money(day.paid_triton_cash_cents)}</span>{day.unfunded_cents > 0 && <span className="font-semibold text-[var(--danger)]">Unfunded {money(day.unfunded_cents)}</span>}</div></div>)}
          </div>
        </div>
        <div className="panel">
          <div className="panel-heading"><div><p className="eyebrow">Guardrails</p><h3 className="panel-title">Wallet runway caps</h3></div><ArrowUpRight size={20} className="text-[var(--accent)]" /></div>
          <p className="mb-5 text-sm leading-6 text-[var(--text-muted)]">These caps divide each starting wallet across the projected period. They are not meal recommendations and do not account for habit eligibility.</p>
          <div className="space-y-3"><div className="runway-row"><span>Dining Dollars / day</span><strong>{money(result.limits.daily_wallet_runway_caps.dining_dollars_cents)}</strong></div><div className="runway-row"><span>Triton Cash / day</span><strong>{money(result.limits.daily_wallet_runway_caps.triton_cash_cents)}</strong></div></div>
          <div className="mt-6 border-t border-[var(--border)] pt-5"><p className="eyebrow">Weekly caps</p><div className="mt-3 space-y-2">{Object.entries(result.limits.weekly_wallet_runway_caps).map(([week, cap]) => <div className="runway-row text-sm" key={week}><span>Week of {shortDate(week)}</span><span><strong>{money(cap.dining_dollars_cents)}</strong> DD · <strong>{money(cap.triton_cash_cents)}</strong> Cash</span></div>)}</div></div>
        </div>
      </div>
    </section>
  );
}
