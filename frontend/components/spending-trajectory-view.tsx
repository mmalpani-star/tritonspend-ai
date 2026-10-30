"use client";

import { ArrowLeft, CircleAlert, Info, PencilLine, Sparkles, Trash2, WalletCards } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { deleteParticipantForecast, listParticipantForecasts, readPrediction } from "../lib/api";
import { formatCalendarDate, formatTimestamp } from "../lib/datetime";
import { CONFIDENCE_LABELS } from "../lib/prediction";
import { forgetForecastSelection, pickForecastId, rememberForecastSelection, rememberedForecastSelection, withoutForecast } from "../lib/trajectory";
import { AccountPrediction, ParticipantForecastSummary, Prediction } from "../lib/types";
import { formatMoney as money } from "../lib/wallet";
import { ConfirmDialog } from "./confirm-dialog";
import { DeleteForecastDetails, FundsStatus, scenarioLabels } from "./forecast-history-panel";
import { PredictionChart, accountLabels } from "./prediction-chart";

type Load<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: T };

const NO_COMPARISON = "";
const errorMessage = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);
const period = (item: { start_date: string; end_date: string }) => `${formatCalendarDate(item.start_date)} – ${formatCalendarDate(item.end_date)}`;
const optionLabel = (item: ParticipantForecastSummary) =>
  `Saved ${formatTimestamp(item.created_at)} · ${period(item)}${item.scenario ? ` · ${scenarioLabels[item.scenario] ?? item.scenario}` : ""}`;
const perDay = (cents: number) => `${money(cents)} a day`;
const TARGET_TEXT = {
  forecast_threshold: "the warning amount saved with the selected forecast",
  current_threshold: "your current warning amount",
  zero: "$0.00 (no warning amount set)"
} as const;

function AccountSummary({ summary, prediction }: { summary: AccountPrediction; prediction: Prediction }) {
  const horizon = prediction.horizon;
  const end = horizon ? formatCalendarDate(horizon.end_date) : "";
  return (
    <div className="space-y-2 text-sm leading-6 text-[var(--text-muted)]">
      {summary.daily_pace_cents === null ? (
        <p className="notice-info"><Info size={16} aria-hidden="true" /> {summary.confidence_text}</p>
      ) : (
        <>
          <p>
            <strong className="text-[var(--text)]">Predicted pace:</strong> balance goes down about {perDay(summary.daily_pace_cents)}.{" "}
            {summary.range_basis === "learned_range"
              ? `Your recent history ranges from ${perDay(summary.lower_pace_cents ?? 0)} (slower) to ${perDay(summary.higher_pace_cents ?? 0)} (faster).`
              : `Slower and faster paths are simple ±25% what-ifs (${perDay(summary.lower_pace_cents ?? 0)} to ${perDay(summary.higher_pace_cents ?? 0)}) until there’s enough history to learn your range.`}
          </p>
          {summary.predicted_end_cents !== null && (
            <p>
              <strong className="text-[var(--text)]">By the end of {end}:</strong> predicted {money(summary.predicted_end_cents)}
              {summary.higher_end_cents !== null && summary.lower_end_cents !== null ? ` (faster spending ${money(summary.higher_end_cents)}, slower ${money(summary.lower_end_cents)})` : ""}.
              {summary.runs_out_on ? ` At the predicted pace it would reach $0.00 around the end of ${formatCalendarDate(summary.runs_out_on)}.` : ""}
            </p>
          )}
          {summary.ideal_available && summary.predicted_end_cents !== null && (
            <p>
              <strong className="text-[var(--text)]">Compared with ideal:</strong>{" "}
              {summary.predicted_end_cents < summary.target_cents
                ? `the prediction ends ${money(summary.target_cents - summary.predicted_end_cents)} below ${TARGET_TEXT[summary.target_basis]} — spending is running faster than the ideal pace.`
                : `the prediction ends ${money(summary.predicted_end_cents - summary.target_cents)} above ${TARGET_TEXT[summary.target_basis]}.`}
            </p>
          )}
        </>
      )}
      {!summary.ideal_available && summary.latest_cents !== null && (
        <p>No ideal line: the latest balance is already below {TARGET_TEXT[summary.target_basis]} ({money(summary.target_cents)}).</p>
      )}
      {summary.replenishments.map((change) => (
        <p key={`${change.from_boundary}-${change.to_boundary}`} className="flex items-start gap-2">
          <CircleAlert size={15} className="mt-1 shrink-0 text-[var(--primary)]" aria-hidden="true" />
          <span>Balance went up {money(change.increase_cents ?? 0)} between {formatCalendarDate(change.from_boundary)} and {formatCalendarDate(change.to_boundary)}. That may be a deposit, refund, or transfer, so it isn’t counted toward your pace.</span>
        </p>
      ))}
      {summary.unusual_changes.map((change) => (
        <p key={`${change.from_boundary}-${change.to_boundary}`} className="flex items-start gap-2">
          <CircleAlert size={15} className="mt-1 shrink-0 text-[var(--danger)]" aria-hidden="true" />
          <span>Unusually fast drop between {formatCalendarDate(change.from_boundary)} and {formatCalendarDate(change.to_boundary)} (about {perDay(change.daily_pace_cents ?? 0)}). It’s kept, but has limited influence on the prediction.</span>
        </p>
      ))}
    </div>
  );
}

type Props = { onBack: () => void; onOpenForecast: () => void; onOpenWallet: () => void };

/** The personalized prediction learned from saved balances, compared with a saved forecast. */
export function SpendingTrajectoryView({ onBack, onOpenForecast, onOpenWallet }: Props) {
  const selectId = useId();
  const planId = useId();
  const [history, setHistory] = useState<Load<ParticipantForecastSummary[]>>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string>(NO_COMPARISON);
  const [prediction, setPrediction] = useState<Load<Prediction>>({ status: "loading" });
  const [showPlan, setShowPlan] = useState(true);
  const [pendingDelete, setPendingDelete] = useState<ParticipantForecastSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const latest = useRef(0);

  const load = useCallback(async (forecastId: string) => {
    const request = ++latest.current;
    setPrediction({ status: "loading" });
    try {
      const value = await readPrediction(forecastId || null);
      // Ignore a slower response for a forecast the student has already moved away from.
      if (latest.current === request) setPrediction({ status: "ready", data: value });
    } catch (error) {
      if (latest.current === request) setPrediction({ status: "error", message: errorMessage(error, "Unable to load your prediction.") });
    }
  }, []);

  useEffect(() => {
    (async () => {
      let id: string = NO_COMPARISON;
      try {
        const items = await listParticipantForecasts(100);
        setHistory({ status: "ready", data: items });
        id = pickForecastId(items, rememberedForecastSelection()) ?? NO_COMPARISON;
      } catch (error) {
        setHistory({ status: "error", message: errorMessage(error, "Unable to load saved forecasts.") });
      }
      setSelectedId(id);
      void load(id);
    })();
  }, [load]);

  function choose(id: string) {
    setSelectedId(id);
    if (id) rememberForecastSelection(id);
    void load(id);
  }

  async function confirmDelete() {
    if (!pendingDelete || history.status !== "ready") return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteParticipantForecast(pendingDelete.id);
      forgetForecastSelection(pendingDelete.id);
      const next = withoutForecast(history.data, pendingDelete.id, selectedId || null);
      setHistory({ status: "ready", data: next.history });
      setPendingDelete(null);
      if ((next.selectedId ?? NO_COMPARISON) !== selectedId) choose(next.selectedId ?? NO_COMPARISON);
    } catch (error) {
      setDeleteError(errorMessage(error, "Unable to delete that forecast."));
    } finally {
      setDeleting(false);
    }
  }

  const forecasts = history.status === "ready" ? history.data : [];
  const selected = forecasts.find((item) => item.id === selectedId) ?? null;
  const data = prediction.status === "ready" ? prediction.data : null;
  // Only render a prediction that belongs to the current selection.
  const current = data && (data.comparison?.id ?? NO_COMPARISON) === selectedId ? data : null;
  const planShown = showPlan && Boolean(current?.comparison);

  return (
    <section aria-labelledby="trajectory-title" className="space-y-6">
      <button type="button" className="secondary-button" onClick={onBack}><ArrowLeft size={14} aria-hidden="true" /> Back to dashboard</button>
      <div>
        <p className="eyebrow">Spending Trajectory</p>
        <h1 id="trajectory-title" className="panel-title text-3xl">Where your balances are heading</h1>
        <p className="mt-2 flex max-w-2xl items-start gap-2 text-sm leading-6 text-[var(--text-muted)]">
          <Sparkles size={16} className="mt-1 shrink-0 text-[var(--primary)]" aria-hidden="true" />
          Your prediction learns from changes in your saved wallet balances. It becomes more personalized as you add observations.
        </p>
      </div>

      {prediction.status === "loading" && <p className="field-help" role="status">Loading your prediction…</p>}
      {prediction.status === "error" && <div className="error-box" role="alert"><strong>Couldn’t load your prediction.</strong><span>{prediction.message}</span></div>}

      {current && current.observation_count === 0 && (
        <div className="panel">
          <div className="wallet-callout" role="status">
            <WalletCards size={22} aria-hidden="true" className="shrink-0 text-[var(--primary)]" />
            <div>
              <p className="font-bold text-[var(--text)]">Save your wallet balances to start</p>
              <p className="mt-1 text-sm text-[var(--text-muted)]">Your prediction is built only from balances you save. Add your current Dining Dollars and Triton Cash, then update them every few days.</p>
              <button type="button" className="primary-button mt-3" onClick={onOpenWallet}>Add wallet balances</button>
            </div>
          </div>
        </div>
      )}

      {current && current.latest && (
        <>
          <section className="panel" aria-labelledby="current-wallet-title">
            <h2 id="current-wallet-title" className="sr-only">Current balances and prediction confidence</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {current.accounts.map((summary) => (
                <div key={summary.account} className="metric-card wallet-tile">
                  <span className="metric-label">{accountLabels[summary.account]} now</span>
                  <strong className="wallet-amount">{money(summary.latest_cents ?? 0)}</strong>
                  <span className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <span className={`confidence-chip confidence-${summary.confidence}`}>{CONFIDENCE_LABELS[summary.confidence]}</span>
                    <span className="text-[var(--text-muted)]">{summary.usable_interval_count} balance change{summary.usable_interval_count === 1 ? "" : "s"} learned</span>
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-[var(--text-muted)]">
              <span>Last balance update: as of <strong className="text-[var(--text)]">{formatCalendarDate(current.latest.as_of)}</strong>, saved {formatTimestamp(current.latest.observed_at)} · {current.observation_count} saved date{current.observation_count === 1 ? "" : "s"}</span>
              <button type="button" className="ml-auto inline-flex items-center gap-1.5 text-xs font-bold text-[var(--primary)] hover:underline" onClick={onOpenWallet}><PencilLine size={13} aria-hidden="true" /> Update balances</button>
            </p>
            {current.accounts.some((summary) => summary.confidence === "starting" || summary.confidence === "preliminary") && (
              <p className="notice-info mt-4"><Info size={16} aria-hidden="true" /> Keep updating your balances every few days. Each update teaches the prediction more about your own pace.</p>
            )}
          </section>

          <section className="panel" aria-labelledby={`${selectId}-heading`}>
            <h2 id={`${selectId}-heading`} className="text-sm font-bold text-[var(--text)]">Compare with a saved forecast</h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">The selected forecast sets the time period and the ideal target. Its original plan is shown as a secondary line and never changes.</p>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <div className="field-label min-w-0 flex-1">
                <label htmlFor={selectId}>Saved forecast</label>
                <select id={selectId} value={selectedId} onChange={(event) => choose(event.target.value)}>
                  <option value={NO_COMPARISON}>None — next 30 days, current warning amounts</option>
                  {forecasts.map((item) => <option key={item.id} value={item.id}>{optionLabel(item)}</option>)}
                </select>
              </div>
              {selected && (
                <button type="button" className="secondary-button danger-button" onClick={() => { setDeleteError(""); setPendingDelete(selected); }}>
                  <Trash2 size={14} aria-hidden="true" /> Delete this forecast
                </button>
              )}
            </div>
            {history.status === "ready" && forecasts.length === 0 && (
              <p className="field-help mt-3">No saved forecasts yet. <button type="button" className="font-semibold text-[var(--primary)] underline" onClick={onOpenForecast}>Create one</button> to compare its plan.</p>
            )}
            {selected && (
              <div className="mt-4 flex flex-wrap items-start justify-between gap-3 border-t border-[var(--border)] pt-4" aria-live="polite">
                <div>
                  <p className="metric-label">Comparing with</p>
                  <p className="mt-1 font-semibold text-[var(--text)]">Forecast for {period(selected)}</p>
                  <p className="text-xs text-[var(--text-muted)]">Saved {formatTimestamp(selected.created_at)}{selected.scenario ? ` · ${scenarioLabels[selected.scenario] ?? selected.scenario} scenario` : ""}</p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <FundsStatus fundsLast={selected.funds_last} unfundedCents={selected.total_unfunded_cents} />
                  <label className="check-chip"><input id={planId} type="checkbox" checked={showPlan} onChange={(event) => setShowPlan(event.target.checked)} />Show original forecast plan</label>
                </div>
              </div>
            )}
            {current.horizon && (
              <p className="field-help mt-3">
                Predictions run from {formatCalendarDate(current.horizon.start)} (your latest saved balance) to the end of {formatCalendarDate(current.horizon.end_date)}
                {current.horizon.rule === "selected_forecast_end" ? ", the selected forecast’s last day." : current.comparison ? " — the selected forecast has already ended, so the next 30 days are shown." : "."}
              </p>
            )}
          </section>

          <div className="grid gap-5 xl:grid-cols-2">
            {current.accounts.map((summary) => (
              <div key={`${current.comparison?.id ?? "none"}-${summary.account}`} className="space-y-3">
                <PredictionChart prediction={current} account={summary.account} summary={summary} showPlan={planShown} />
                <AccountSummary summary={summary} prediction={current} />
              </div>
            ))}
          </div>

          <section className="panel" aria-labelledby="prediction-notes-title">
            <h2 id="prediction-notes-title" className="text-sm font-bold text-[var(--text)]">What you’re looking at</h2>
            <ul className="mt-3 grid gap-2 text-sm leading-6 text-[var(--text-muted)]">
              <li><strong className="text-[var(--text)]">Saved balance (actual):</strong> only balances you saved. Days without one stay empty.</li>
              <li><strong className="text-[var(--text)]">Personalized prediction:</strong> where your balance is heading at the pace your own saved balances show, weighting recent changes more. It starts from your latest saved balance and never drops below $0.00.</li>
              <li><strong className="text-[var(--text)]">Slower and faster spending:</strong> the range your history shows (or a simple ±25% what-if while history is short).</li>
              <li><strong className="text-[var(--text)]">Ideal:</strong> spending the same amount each day from your latest balance down to your target by the end of the period. It’s a goal, not a prediction.</li>
              <li><strong className="text-[var(--text)]">Original forecast plan:</strong> what the selected saved forecast projected from your eating habits when you created it.</li>
              <li><strong className="text-[var(--text)]">Limits:</strong> balances don’t show individual purchases. A change can include spending, deposits, refunds, transfers, or corrections, so the prediction is about net balance change, not exact spending. Few updates mean a rough estimate.</li>
            </ul>
          </section>
        </>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this forecast?"
        confirmLabel="Delete Forecast"
        busy={deleting}
        error={deleteError}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      >
        {pendingDelete && <DeleteForecastDetails item={pendingDelete} />}
      </ConfirmDialog>
    </section>
  );
}
