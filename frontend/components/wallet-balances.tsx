"use client";

import { BellRing, CalendarClock, CircleAlert, PencilLine } from "lucide-react";
import { useId, useState } from "react";
import { saveWalletBalances } from "../lib/api";
import { Account, Wallet, WalletBalances } from "../lib/types";
import { campusToday, formatCalendarDate, formatTimestamp } from "../lib/datetime";
import { WalletLoad, centsToInput, describeAge, formatMoney } from "../lib/wallet";
import { parseWalletAmounts } from "../lib/forecast-limits";
import { InfoLabel } from "./info-label";
import { AnimatedMoney } from "./visual/animated-money";

const ACCOUNTS: ReadonlyArray<{ account: Account; key: keyof Wallet; label: string }> = [
  { account: "dining_dollars", key: "dining_dollars_cents", label: "Dining Dollars" },
  { account: "triton_cash", key: "triton_cash_cents", label: "Triton Cash" }
];

const AS_OF_HELP = (
  <>
    Enter the date when these wallet balances were accurate. Usually, this is today—the date you checked your Dining Dollars and Triton Cash accounts. If you are entering balances you recorded on an earlier date, select that date instead.
    <span className="mt-1.5 block">TritonSpend treats them as your balances on that date before any of that day’s spending, so a new forecast starts on that same date.</span>
  </>
);

type FormProps = {
  initial?: Wallet;
  submitLabel: string;
  onSaved: (saved: WalletBalances) => Promise<void> | void;
  onCancel?: () => void;
};

/** Both balances and their as-of date, saved together as one wallet snapshot. */
export function WalletForm({ initial, submitLabel, onSaved, onCancel }: FormProps) {
  const id = useId();
  const today = campusToday();
  const [dining, setDining] = useState(initial ? centsToInput(initial.dining_dollars_cents) : "");
  const [cash, setCash] = useState(initial ? centsToInput(initial.triton_cash_cents) : "");
  const [asOf, setAsOf] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const amounts = parseWalletAmounts(dining, cash, {
      labels: { dining: "The Dining Dollars balance", cash: "The Triton Cash balance" },
      example: "like 1250 or 1250.50"
    });
    if ("error" in amounts) {
      setError(amounts.error);
      return;
    }
    if (!asOf || asOf > today) {
      setError("Choose an as-of date that is today or earlier.");
      return;
    }
    setBusy(true);
    try {
      const saved = await saveWalletBalances({ effective_date: asOf, ...amounts });
      await onSaved(saved);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save your wallet balances.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="wallet-form" noValidate>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="field-label">Dining Dollars balance<input required inputMode="decimal" autoComplete="off" placeholder="0.00" value={dining} onChange={(event) => setDining(event.target.value)} /></label>
        <label className="field-label">Triton Cash balance<input required inputMode="decimal" autoComplete="off" placeholder="0.00" value={cash} onChange={(event) => setCash(event.target.value)} /></label>
        <div className="field-label">
          <InfoLabel htmlFor={`${id}-as-of`} label="As-of date">{AS_OF_HELP}</InfoLabel>
          <input id={`${id}-as-of`} required type="date" max={today} value={asOf} onChange={(event) => setAsOf(event.target.value)} />
        </div>
      </div>
      {error && <p role="alert" className="error-box mt-4">{error}</p>}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button type="submit" disabled={busy} className="primary-button">{busy ? "Saving…" : submitLabel}</button>
        {onCancel && <button type="button" className="secondary-button" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}

type CardProps = {
  wallet: WalletLoad;
  reload: () => Promise<void>;
  /** Shown on the dashboard to reach the warning settings. */
  onOpenAlerts?: () => void;
};

/** Latest saved balances with an inline update form, or first-time setup when none are saved. */
export function WalletBalancesCard({ wallet, reload, onOpenAlerts }: CardProps) {
  const headingId = useId();
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState("");

  if (wallet.status === "loading") {
    return <section className="panel wallet-panel" aria-busy="true"><p className="field-help" role="status">Loading your wallet balances…</p></section>;
  }
  if (wallet.status === "error") {
    return (
      <section className="panel wallet-panel">
        <div className="error-box" role="alert"><strong>Couldn’t load your wallet balances.</strong><span>{wallet.message}</span><button type="button" className="secondary-button mt-2 w-fit" onClick={() => void reload()}>Try again</button></div>
      </section>
    );
  }

  const { latest, warnings, stale, days_since_update: age } = wallet.data;

  async function saved(value: WalletBalances) {
    const previous = latest?.effective_date;
    await reload();
    setEditing(false);
    setMessage(
      previous && value.effective_date < previous
        ? `Saved for ${formatCalendarDate(value.effective_date)}. Your balances from ${formatCalendarDate(previous)} are newer, so forecasts keep starting from those.`
        : "Wallet balances saved."
    );
  }

  if (!latest) {
    return (
      <section className="panel wallet-panel" aria-labelledby={headingId}>
        <p className="eyebrow">Wallet setup</p>
        <h2 id={headingId} className="panel-title">Add your wallet balances</h2>
        <p className="mb-5 mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
          Enter the Dining Dollars and Triton Cash balances your UC San Diego account shows. That’s all TritonSpend needs to forecast—no receipts or purchase history.
        </p>
        <WalletForm submitLabel="Save wallet balances" onSaved={saved} />
      </section>
    );
  }

  return (
    <section className="panel wallet-panel" aria-labelledby={headingId}>
      <div className="panel-heading mb-4 flex-wrap">
        <div>
          <p className="eyebrow">Wallet balances</p>
          <h2 id={headingId} className="panel-title">Your wallet</h2>
        </div>
        {!editing && (
          <button type="button" className="primary-button" onClick={() => { setMessage(""); setEditing(true); }}>
            <PencilLine size={16} aria-hidden="true" /> Update balances
          </button>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {ACCOUNTS.map(({ account, key, label }) => {
          const warning = warnings?.[account];
          return (
            <div key={account} className={`metric-card wallet-tile wallet-tile-${account}`}>
              <span className="metric-label">{label}</span>
              <strong className="wallet-amount"><AnimatedMoney cents={latest[key]} /></strong>
              {warning?.warning ? (
                <span className="wallet-alert"><CircleAlert size={14} aria-hidden="true" /> At or below your {formatMoney(warning.threshold_cents)} warning amount</span>
              ) : warning ? (
                <span className="metric-note">Warning below {formatMoney(warning.threshold_cents)}</span>
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-[var(--text-muted)]">
        <CalendarClock size={15} aria-hidden="true" />
        <span>Last updated: balances as of <strong className="text-[var(--text)]">{formatCalendarDate(latest.effective_date)}</strong> ({describeAge(age)}) · saved {formatTimestamp(latest.observed_at)}</span>
        {onOpenAlerts && (
          <button type="button" className="ml-auto inline-flex items-center gap-1.5 text-xs font-bold text-[var(--primary)] underline-offset-2 hover:underline" onClick={onOpenAlerts}>
            <BellRing size={14} aria-hidden="true" /> {warnings ? "Balance warnings" : "Set balance warnings"}
          </button>
        )}
      </p>
      {stale && !editing && (
        <p className="notice-info mt-4"><CircleAlert size={16} aria-hidden="true" /> These balances are {age} days old. Update them so your next forecast starts from current numbers.</p>
      )}
      {message && <p className="field-help mt-3" role="status">{message}</p>}
      {editing && (
        <div className="mt-5 border-t border-[var(--border)] pt-5">
          <h3 className="mb-3 text-sm font-bold text-[var(--text)]">Update both balances</h3>
          <WalletForm initial={latest} submitLabel="Save balances" onSaved={saved} onCancel={() => setEditing(false)} />
        </div>
      )}
    </section>
  );
}
