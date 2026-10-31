"use client";

import { ArrowLeft, Download, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { deleteParticipantData, downloadParticipantData, setBalanceThresholds } from "../lib/api";
import { Account, Wallet, WalletStatus } from "../lib/types";
import { centsToInput, formatMoney, useWallet } from "../lib/wallet";
import { parseWalletAmounts } from "../lib/forecast-limits";
import { WalletBalancesCard } from "./wallet-balances";

const LABELS: Record<Account, string> = { dining_dollars: "Dining Dollars", triton_cash: "Triton Cash" };

function WarningSettings({ data, onSaved }: { data: WalletStatus; onSaved: () => Promise<void> }) {
  const [dining, setDining] = useState(data.thresholds ? centsToInput(data.thresholds.dining_dollars_cents) : "");
  const [cash, setCash] = useState(data.thresholds ? centsToInput(data.thresholds.triton_cash_cents) : "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);

  // Show the saved amounts once they arrive (e.g. after signing back in).
  useEffect(() => {
    if (!data.thresholds) return;
    setDining(centsToInput(data.thresholds.dining_dollars_cents));
    setCash(centsToInput(data.thresholds.triton_cash_cents));
  }, [data.thresholds]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const amounts = parseWalletAmounts(dining, cash, {
      labels: { dining: "The Dining Dollars warning amount", cash: "The Triton Cash warning amount" },
      example: "like 100 or 75.50 (use 0 to turn a warning off)"
    });
    if ("error" in amounts) {
      setMessage({ error: true, text: amounts.error });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await setBalanceThresholds(amounts);
      await onSaved();
      setMessage({ error: false, text: "Warning amounts saved to your account." });
    } catch (error) {
      setMessage({ error: true, text: error instanceof Error ? error.message : "Unable to save warning amounts." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="warning-settings-title">
      <p className="eyebrow">Balance warnings</p>
      <h2 id="warning-settings-title" className="panel-title">Warn me when balances get low</h2>
      <p className="mb-5 mt-2 text-sm leading-6 text-[var(--text-muted)]">Receive a warning when your wallet balance falls below this amount.</p>
      <form onSubmit={submit} noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field-label">Minimum Dining Dollars balance<input inputMode="decimal" autoComplete="off" placeholder="0.00" value={dining} onChange={(event) => setDining(event.target.value)} /></label>
          <label className="field-label">Minimum Triton Cash balance<input inputMode="decimal" autoComplete="off" placeholder="0.00" value={cash} onChange={(event) => setCash(event.target.value)} /></label>
        </div>
        <p className="field-help mt-2">A warning shows when a saved balance is at or below its amount. Saved forecasts also use these amounts as the target for their ideal spending line.</p>
        <button type="submit" disabled={busy} className="primary-button mt-5">{busy ? "Saving…" : "Save warning amounts"}</button>
      </form>
      {message && <p role={message.error ? "alert" : "status"} className={message.error ? "error-box mt-4" : "field-help mt-4"}>{message.text}</p>}
      {data.warnings && (
        <ul className="mt-5 grid gap-2 text-sm" aria-label="Current warning status">
          {(["dining_dollars", "triton_cash"] as Account[]).map((account) => {
            const item = data.warnings![account];
            const key = `${account}_cents` as keyof Wallet;
            const text = item.current_balance_cents === null
              ? "No balance saved yet, so no warning."
              : item.warning
                ? `${formatMoney(item.current_balance_cents)} is at or below your ${formatMoney(item.threshold_cents)} warning amount.`
                : `${formatMoney(item.current_balance_cents)} is above your ${formatMoney(item.threshold_cents)} warning amount.`;
            return <li key={key} className={item.warning ? "notice-danger" : "runway-row"}><span><strong>{LABELS[account]}:</strong> {text}</span></li>;
          })}
        </ul>
      )}
    </section>
  );
}

function DataControls() {
  const [deleted, setDeleted] = useState(false);
  const [message, setMessage] = useState("");

  async function download() {
    setMessage("");
    try {
      await downloadParticipantData();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to download your data.");
    }
  }

  async function remove() {
    if (!window.confirm("Delete your participant data? This removes your account login, saved wallet balances, warning amounts, saved forecasts, and any older spending records. This cannot be undone.")) return;
    setMessage("");
    try {
      await deleteParticipantData();
      setDeleted(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to delete your data.");
    }
  }

  return (
    <section className="panel" aria-labelledby="data-controls-title">
      <p className="eyebrow">Your data</p>
      <h2 id="data-controls-title" className="panel-title">Download or delete your data</h2>
      <p className="mb-5 mt-2 flex items-start gap-2 text-sm leading-6 text-[var(--text-muted)]"><ShieldCheck size={17} className="mt-1 shrink-0" aria-hidden="true" /> Your data is visible only to your account. The download includes everything saved for you, including any older spending records.</p>
      <p className="mb-5 -mt-2 text-sm leading-6 text-[var(--text-muted)]">Every wallet balance you save is kept as history and used to personalize <em>your own</em> spending predictions. It is never used for other students’ predictions or sent to outside AI services, it’s included in Download my data, and it’s removed when you delete your participant data.</p>
      {deleted ? (
        <div className="error-box" role="alert">
          <strong>Your participant data was deleted and you were signed out.</strong>
          <button type="button" className="secondary-button mt-2 w-fit" onClick={() => window.location.assign("/")}>Return to sign in</button>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="secondary-button" onClick={() => void download()}><Download size={15} aria-hidden="true" /> Download my data</button>
          <button type="button" className="secondary-button danger-button" onClick={() => void remove()}><Trash2 size={15} aria-hidden="true" /> Delete my participant data</button>
        </div>
      )}
      {message && <p className="error-box mt-4" role="alert">{message}</p>}
    </section>
  );
}

/** Wallet balances, warning amounts, and account data controls. */
export function WalletAlertsView({ onBack }: { onBack: () => void }) {
  const [wallet, reload] = useWallet();
  return (
    <section aria-labelledby="wallet-alerts-title" className="space-y-6">
      <button type="button" className="secondary-button" onClick={onBack}><ArrowLeft size={14} aria-hidden="true" /> Back to dashboard</button>
      <div>
        <p className="eyebrow">Wallet &amp; Alerts</p>
        <h1 id="wallet-alerts-title" className="panel-title text-3xl">Your wallet and balance warnings</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">Keep your balances current and choose when TritonSpend should warn you. You never need to log individual purchases.</p>
      </div>
      <WalletBalancesCard wallet={wallet} reload={reload} />
      {wallet.status === "ready" && <WarningSettings data={wallet.data} onSaved={reload} />}
      <DataControls />
    </section>
  );
}
