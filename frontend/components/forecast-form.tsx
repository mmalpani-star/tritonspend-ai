"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Account, ForecastRequest, HabitInput, Scenario } from "../lib/types";

type Props = { loading: boolean; onSubmit: (request: ForecastRequest) => Promise<void> };
const accountLabels: Record<Account, string> = {
  dining_dollars: "Dining Dollars",
  triton_cash: "Triton Cash"
};

const emptyHabit = (): HabitInput => ({
  name: "",
  frequency: "1",
  price_cents: 0,
  eligible_accounts: []
});

function dollarsToCents(value: string): number | null {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const [whole, fraction = ""] = value.trim().split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

export function ForecastForm({ loading, onSubmit }: Props) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [dining, setDining] = useState("");
  const [cash, setCash] = useState("");
  const [scenario, setScenario] = useState<Scenario>("expected");
  const [habits, setHabits] = useState<HabitInput[]>([emptyHabit()]);
  const [error, setError] = useState("");

  function updateHabit(index: number, patch: Partial<HabitInput>) {
    setHabits((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  function toggleAccount(index: number, account: Account) {
    const habit = habits[index];
    const eligible_accounts = habit.eligible_accounts.includes(account)
      ? habit.eligible_accounts.filter((item) => item !== account)
      : [...habit.eligible_accounts, account];
    updateHabit(index, { eligible_accounts });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const diningCents = dollarsToCents(dining);
    const cashCents = dollarsToCents(cash);
    if (!startDate || !endDate || diningCents === null || cashCents === null) {
      setError("Add both dates and enter balances as dollars with up to two decimal places.");
      return;
    }
    if (habits.some((habit) => !habit.name.trim() || !/^\d+(?:\/\d+)?$/.test(habit.frequency) || habit.eligible_accounts.length === 0)) {
      setError("Each habit needs a name, a fraction-style frequency, and at least one eligible account.");
      return;
    }
    try {
      await onSubmit({
        start_date: startDate,
        end_date: endDate,
        dining_dollars_cents: diningCents,
        triton_cash_cents: cashCents,
        scenario,
        habits
      });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Unable to create forecast.");
    }
  }

  return (
    <form onSubmit={submit} className="space-y-7">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="field-label">Start date<input required type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label className="field-label">End date<input required type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <label className="field-label">Dining Dollars balance<input required inputMode="decimal" placeholder="0.00" value={dining} onChange={(event) => setDining(event.target.value)} /><span className="field-help">Stored and sent as exact cents.</span></label>
        <label className="field-label">Triton Cash balance<input required inputMode="decimal" placeholder="0.00" value={cash} onChange={(event) => setCash(event.target.value)} /><span className="field-help">Kept separate from Dining Dollars.</span></label>
      </div>
      <div>
        <label className="field-label">Spending scenario<select value={scenario} onChange={(event) => setScenario(event.target.value as Scenario)}><option value="expected">Expected</option><option value="frugal">Frugal</option><option value="higher">Higher spending</option></select></label>
        <p className="field-help mt-2">Illustrative multipliers, not probability ranges.</p>
      </div>
      <div className="space-y-4">
        <div className="flex items-end justify-between gap-4">
          <div><h3 className="text-lg font-bold text-[var(--text)]">Eating habits</h3><p className="mt-1 text-sm text-[var(--text-muted)]">Example: “Breakfast · 1/2 · $3.75”. Prices and account eligibility are user-provided.</p></div>
          <button type="button" onClick={() => setHabits((items) => [...items, emptyHabit()])} className="secondary-button whitespace-nowrap"><Plus size={16} /> Add habit</button>
        </div>
        {habits.map((habit, index) => (
          <div key={index} className="habit-card">
            <div className="grid gap-3 sm:grid-cols-[1.4fr_0.8fr_0.8fr_auto]">
              <label className="field-label">Label<input placeholder="Breakfast" value={habit.name} onChange={(event) => updateHabit(index, { name: event.target.value })} /></label>
              <label className="field-label">Frequency<input placeholder="1/2" value={habit.frequency} onChange={(event) => updateHabit(index, { frequency: event.target.value })} /><span className="field-help">Per day</span></label>
              <label className="field-label">Price<input inputMode="decimal" placeholder="3.75" value={(habit.price_cents / 100).toFixed(2)} onChange={(event) => updateHabit(index, { price_cents: dollarsToCents(event.target.value) ?? 0 })} /><span className="field-help">Dollars</span></label>
              <button type="button" aria-label={`Remove ${habit.name || "habit"}`} onClick={() => setHabits((items) => items.filter((_, itemIndex) => itemIndex !== index))} className="icon-button self-end"><Trash2 size={17} /></button>
            </div>
            <fieldset className="mt-4">
              <legend className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">Eligible accounts</legend>
              <div className="mt-2 flex flex-wrap gap-2">
                {(["dining_dollars", "triton_cash"] as Account[]).map((account) => (
                  <label key={account} className={`check-chip ${habit.eligible_accounts.includes(account) ? "check-chip-active" : ""}`}><input type="checkbox" checked={habit.eligible_accounts.includes(account)} onChange={() => toggleAccount(index, account)} />{accountLabels[account]}</label>
                ))}
              </div>
            </fieldset>
          </div>
        ))}
      </div>
      {error && <p role="alert" className="error-box">{error}</p>}
      <button disabled={loading} type="submit" className="primary-button w-full sm:w-auto">{loading ? "Building your forecast…" : "Create forecast"}</button>
    </form>
  );
}
