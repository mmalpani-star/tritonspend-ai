"use client";

import { useState } from "react";
import { confirmZeroSpending, deleteParticipantData, downloadParticipantData, readBalanceWarnings, readPilotData, setBalanceThresholds, submitBalanceCheckin, submitLedgerEntry } from "../lib/api";
import { Account, PilotData } from "../lib/types";

function cents(value: string): number | null {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const [whole, fraction = ""] = value.trim().split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

export function DataCollectionPanel() {
  const [day, setDay] = useState("");
  const [dining, setDining] = useState("");
  const [cash, setCash] = useState("");
  const [account, setAccount] = useState<Account>("dining_dollars");
  const [entryType, setEntryType] = useState<"spending" | "deposit" | "refund">("spending");
  const [amount, setAmount] = useState("");
  const [data, setData] = useState<PilotData | null>(null);
  const [message, setMessage] = useState("");
  const [diningThreshold, setDiningThreshold] = useState("");
  const [cashThreshold, setCashThreshold] = useState("");
  const [warnings, setWarnings] = useState<Awaited<ReturnType<typeof readBalanceWarnings>> | null>(null);
  const [deleted, setDeleted] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setMessage("");
    try {
      await action();
      setMessage("Saved. Days without a check-in or confirmation remain unknown.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save participant data.");
    }
  }

  async function refresh() {
    if (!day) return;
    try {
      setData(await readPilotData(day, day));
      try {
        setWarnings(await readBalanceWarnings());
      } catch {
        setWarnings(null);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load participant data.");
    }
  }

  async function deleteData() {
    if (!window.confirm("Delete your participant data? This removes your recorded balances, ledger entries, confirmations, thresholds, and forecast snapshots. This cannot be undone.")) return;
    try {
      await deleteParticipantData();
      setDeleted(true);
      setData(null);
      setWarnings(null);
      setMessage("Your participant data was deleted. Sign in again only if you receive a new invitation.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to delete participant data.");
    }
  }

  return (
    <section className="panel mt-6">
      <div className="panel-heading">
        <div><p className="eyebrow">Participant data</p><h2 className="panel-title">Record what you know.</h2></div>
        <span className="step-badge">02</span>
      </div>
      <p className="mb-5 text-sm leading-6 text-[var(--text-muted)]">Authenticated participants can record balances, positive ledger amounts, or an explicit zero-spending confirmation. Nothing is inferred for missing days.</p>
      <div className="mb-5 flex flex-wrap gap-2">
        <button type="button" className="secondary-button" onClick={() => void run(downloadParticipantData)}>Download my data</button>
        <button type="button" className="secondary-button" onClick={() => void deleteData()}>Delete my participant data</button>
      </div>
      {deleted && <p className="error-box mb-5" role="alert">Your participant data was deleted. Sign in again only if you receive a new invitation.</p>}
      <div className={`mb-5 grid gap-3 sm:grid-cols-2${deleted ? " pointer-events-none opacity-50" : ""}`}>
        <label className="field-label">Dining Dollars warning threshold<input inputMode="decimal" placeholder="0.00" value={diningThreshold} onChange={(event) => setDiningThreshold(event.target.value)} /></label>
        <label className="field-label">Triton Cash warning threshold<input inputMode="decimal" placeholder="0.00" value={cashThreshold} onChange={(event) => setCashThreshold(event.target.value)} /></label>
        <button type="button" className="secondary-button sm:w-fit" onClick={() => { const diningCents = cents(diningThreshold); const cashCents = cents(cashThreshold); if (diningCents !== null && cashCents !== null) void run(async () => { const next = await setBalanceThresholds({ dining_dollars_cents: diningCents, triton_cash_cents: cashCents }); setWarnings(next); }); }}>Save warning thresholds</button>
      </div>
      <div className={`grid gap-4 sm:grid-cols-2${deleted ? " pointer-events-none opacity-50" : ""}`}>
        <label className="field-label">Date<input required type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label>
        <div className="flex items-end gap-2"><button type="button" className="secondary-button" onClick={refresh}>Load day</button><button type="button" className="secondary-button" onClick={() => day && run(() => confirmZeroSpending(day))}>Confirm no spending</button></div>
        <label className="field-label">Dining Dollars<input inputMode="decimal" placeholder="0.00" value={dining} onChange={(event) => setDining(event.target.value)} /></label>
        <label className="field-label">Triton Cash<input inputMode="decimal" placeholder="0.00" value={cash} onChange={(event) => setCash(event.target.value)} /></label>
        <button type="button" className="primary-button sm:w-fit" onClick={() => { const diningCents = cents(dining); const cashCents = cents(cash); if (day && diningCents !== null && cashCents !== null) void run(() => submitBalanceCheckin({ effective_date: day, dining_dollars_cents: diningCents, triton_cash_cents: cashCents })); }}>Save balance check-in</button>
        <div className="grid grid-cols-2 gap-2">
          <select value={account} onChange={(event) => setAccount(event.target.value as Account)}><option value="dining_dollars">Dining Dollars</option><option value="triton_cash">Triton Cash</option></select>
          <select value={entryType} onChange={(event) => setEntryType(event.target.value as typeof entryType)}><option value="spending">Spending</option><option value="deposit">Deposit</option><option value="refund">Refund</option></select>
          <input className="col-span-2" inputMode="decimal" placeholder="Amount" value={amount} onChange={(event) => setAmount(event.target.value)} />
          <button type="button" className="secondary-button col-span-2" onClick={() => { const amountCents = cents(amount); if (day && amountCents && amountCents > 0) void run(() => submitLedgerEntry({ occurred_on: day, account, entry_type: entryType, amount_cents: amountCents })); }}>Record ledger entry</button>
        </div>
      </div>
      {message && <p className="field-help mt-4" role="status">{message}</p>}
      {data && <p className="mt-4 text-sm text-[var(--text-muted)]">Status for {day}: <strong className="text-[var(--text)]">{data.days[0]?.status ?? "unknown"}</strong>. Ledger entries: {data.ledger_entries.length}.</p>}
      {warnings && <div className="mt-4 grid gap-2 text-sm">{[warnings.dining_dollars, warnings.triton_cash].map((item) => <p key={item.account} className={item.warning ? "error-box" : "field-help"}><strong>{item.account === "dining_dollars" ? "Dining Dollars" : "Triton Cash"}:</strong> {item.explanation}</p>)}</div>}
    </section>
  );
}
