"use client";

import { Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { Account, ForecastRequest, HabitInput, ParticipantForecastRequest, Scenario } from "../lib/types";
import { campusToday } from "../lib/datetime";
import { balanceError, dateRangeError, dollarsToCents, validateHabits } from "../lib/forecast-limits";
import { InfoLabel } from "./info-label";

// With onSubmitSaved, the start date and balances come from the participant's
// saved wallet balances on the server, so only the end date, scenario, and habits are asked for.
type Props = { loading: boolean } & (
  | { onSubmit: (request: ForecastRequest) => Promise<void>; onSubmitSaved?: never }
  | { onSubmitSaved: (request: ParticipantForecastRequest) => Promise<void>; onSubmit?: never }
);
const accountLabels: Record<Account, string> = {
  dining_dollars: "Dining Dollars",
  triton_cash: "Triton Cash"
};

const END_DATE_HELP = "Choose the last day you want this forecast to cover. The application calculates how your Dining Dollars and Triton Cash are expected to last through this date.";
const START_DATE_HELP = "Choose the first day this estimate should cover. Enter the balances you expect to have at the start of that day.";

const emptyHabit = (): HabitInput => ({
  name: "",
  frequency: "1",
  price_cents: 0,
  eligible_accounts: []
});

export function ForecastForm({ loading, onSubmit, onSubmitSaved }: Props) {
  const id = useId();
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [dining, setDining] = useState("");
  const [cash, setCash] = useState("");
  const [scenario, setScenario] = useState<Scenario>("expected");
  const [habits, setHabits] = useState<HabitInput[]>([emptyHabit()]);
  const [habitPrices, setHabitPrices] = useState([""]);
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
    const checked = validateHabits(habits, habitPrices);
    if (onSubmitSaved) {
      // The start date and balances come from the saved wallet; the server checks the period against them.
      if (!endDate) {
        setError("Choose an end date of today or later.");
        return;
      }
      if ("error" in checked) {
        setError(checked.error);
        return;
      }
      try {
        await onSubmitSaved({ end_date: endDate, scenario, habits: checked.habits });
      } catch (submissionError) {
        setError(submissionError instanceof Error ? submissionError.message : "Unable to create forecast.");
      }
      return;
    }
    const diningCents = dollarsToCents(dining);
    const cashCents = dollarsToCents(cash);
    if (!startDate || !endDate || diningCents === null || cashCents === null) {
      setError("Add both dates and enter balances as dollars with up to two decimal places.");
      return;
    }
    const inputError = dateRangeError(startDate, endDate)
      ?? balanceError("The Dining Dollars balance", diningCents)
      ?? balanceError("The Triton Cash balance", cashCents);
    if (inputError) {
      setError(inputError);
      return;
    }
    if ("error" in checked) {
      setError(checked.error);
      return;
    }
    try {
      await onSubmit?.({
        start_date: startDate,
        end_date: endDate,
        dining_dollars_cents: diningCents,
        triton_cash_cents: cashCents,
        scenario,
        habits: checked.habits
      });
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Unable to create forecast.");
    }
  }

  return (
    <form onSubmit={submit} className="space-y-7">
      {onSubmitSaved ? (
        <div className="field-label">
          <InfoLabel htmlFor={`${id}-end`} label="End date">{END_DATE_HELP}</InfoLabel>
          <input id={`${id}-end`} required type="date" min={campusToday()} value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          <span className="field-help mt-1.5">Starting balances come from your latest saved wallet balances.</span>
        </div>
      ) : (
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="field-label">
          <InfoLabel htmlFor={`${id}-start`} label="Start date">{START_DATE_HELP}</InfoLabel>
          <input id={`${id}-start`} required type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </div>
        <div className="field-label">
          <InfoLabel htmlFor={`${id}-end`} label="End date">{END_DATE_HELP}</InfoLabel>
          <input id={`${id}-end`} required type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </div>
        <label className="field-label">Dining Dollars balance<input required inputMode="decimal" placeholder="0.00" value={dining} onChange={(event) => setDining(event.target.value)} /><span className="field-help">Enter your balance in US dollars (up to 2 decimal places); converted to cents internally.</span></label>
        <label className="field-label">Triton Cash balance<input required inputMode="decimal" placeholder="0.00" value={cash} onChange={(event) => setCash(event.target.value)} /><span className="field-help">Entered in US dollars; tracked separately from Dining Dollars and converted to cents internally.</span></label>
      </div>
      )}
      <div>
        <label className="field-label">Spending scenario<select value={scenario} onChange={(event) => setScenario(event.target.value as Scenario)}><option value="expected">Expected</option><option value="frugal">Frugal</option><option value="higher">Higher spending</option></select></label>
        <p className="field-help mt-2">Illustrative multipliers, not probability ranges.</p>
      </div>
      <div className="space-y-4">
        <div className="flex items-end justify-between gap-4">
          <div><h3 className="text-lg font-bold text-[var(--text)]">Eating habits</h3><p className="mt-1 text-sm text-[var(--text-muted)]">Example: “Breakfast · 1/2 · $3.75”. Prices and account eligibility are user-provided.</p></div>
          <button type="button" onClick={() => { setHabits((items) => [...items, emptyHabit()]); setHabitPrices((items) => [...items, ""]); }} className="secondary-button whitespace-nowrap"><Plus size={16} /> Add habit</button>
        </div>
        {habits.map((habit, index) => (
          <div key={index} className="habit-card">
            <div className="grid gap-3 sm:grid-cols-[1.4fr_0.8fr_0.8fr_auto]">
              <label className="field-label">Label<input placeholder="Breakfast" value={habit.name} onChange={(event) => updateHabit(index, { name: event.target.value })} /></label>
              <label className="field-label">Frequency<input placeholder="1/2" value={habit.frequency} onChange={(event) => updateHabit(index, { frequency: event.target.value })} /><span className="field-help">Per day</span></label>
              <label className="field-label">Price<input inputMode="decimal" placeholder="3.75" value={habitPrices[index]} onChange={(event) => setHabitPrices((items) => items.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} /><span className="field-help">Enter US dollars (up to 2 decimal places); converted to cents internally.</span></label>
              <button type="button" aria-label={`Remove ${habit.name || "habit"}`} onClick={() => { setHabits((items) => items.filter((_, itemIndex) => itemIndex !== index)); setHabitPrices((items) => items.filter((_, itemIndex) => itemIndex !== index)); }} className="icon-button self-end"><Trash2 size={17} /></button>
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
      <button disabled={loading} type="submit" className="primary-button w-full sm:w-auto">{loading ? "Building your forecast…" : onSubmitSaved ? "Create and save forecast" : "Create forecast"}</button>
    </form>
  );
}
