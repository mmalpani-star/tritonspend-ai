"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Info, LineChart, PencilLine, Trash2, WalletCards } from "lucide-react";
import { ConfirmDialog } from "./confirm-dialog";
import { ForecastDashboard } from "./forecast-dashboard";
import { ForecastForm } from "./forecast-form";
import { accountLabels } from "./prediction-chart";
import { createParticipantForecast, deleteParticipantForecast, listParticipantForecasts, readParticipantForecast } from "../lib/api";
import { campusToday, formatCalendarDate, formatTimestamp } from "../lib/datetime";
import { forgetForecastSelection, rememberForecastSelection, withoutForecast } from "../lib/trajectory";
import { ForecastResponse, ParticipantForecastDetail, ParticipantForecastRequest, ParticipantForecastSummary, Wallet } from "../lib/types";
import { WalletLoad, forecastStartFor, formatMoney as money } from "../lib/wallet";

type Load<T> = { status: "idle" } | { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: T };

const shortDate = (date: string) => formatCalendarDate(date, { month: "short", day: "numeric" });
const errorMessage = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);
export const scenarioLabels: Record<string, string> = { expected: "Expected", frugal: "Frugal", higher: "Higher spending" };

function isForecastResponse(value: ParticipantForecastDetail["forecast"]): value is ForecastResponse {
  return Array.isArray(value.days) && typeof value.projected_balances === "object" && typeof value.limits === "object";
}

/** Names a saved forecast in delete confirmations: when it was saved and the period it covers. */
export function DeleteForecastDetails({ item }: { item: ParticipantForecastSummary }) {
  return (
    <>
      <p>
        You’re deleting the forecast saved <strong className="text-[var(--text)]">{formatTimestamp(item.created_at)}</strong> covering{" "}
        <strong className="text-[var(--text)]">{formatCalendarDate(item.start_date)} – {formatCalendarDate(item.end_date)}</strong>
        {item.scenario ? ` (${scenarioLabels[item.scenario] ?? item.scenario} scenario)` : ""}.
      </p>
      <p>This can’t be undone. Your wallet balances, warning amounts, and other forecasts are not affected.</p>
    </>
  );
}

/** "Funds last" or the unfunded amount, as stored with the forecast. */
export function FundsStatus({ fundsLast, unfundedCents }: { fundsLast: boolean | null; unfundedCents: number | null }) {
  if (fundsLast === null) return null;
  return (
    <span className={`status-pill py-1 ${fundsLast ? "status-good" : "status-danger"}`}>
      {fundsLast ? <CheckCircle2 size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
      {fundsLast ? "Funds last" : `${money(unfundedCents ?? 0)} unfunded`}
    </span>
  );
}

/** The original inputs and headline results stored with a saved forecast; never recomputed. */
function ForecastInputs({ detail, onOpenTrajectory }: { detail: ParticipantForecastDetail; onOpenTrajectory: () => void }) {
  const { inputs, forecast } = detail;
  const starting: Wallet | undefined = inputs.starting_balances ?? inputs.reconciled_balances;
  const projected = forecast.projected_balances;
  const habits = inputs.request?.habits ?? [];
  const scenario = inputs.request?.scenario;
  return (
    <section className="period-detail mt-0" aria-label="Selected forecast">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="metric-label">Forecast inputs and results (as saved)</p>
        <FundsStatus fundsLast={typeof forecast.funds_last === "boolean" ? forecast.funds_last : null} unfundedCents={typeof forecast.total_unfunded_cents === "number" ? forecast.total_unfunded_cents : null} />
      </div>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
        <div><dt className="field-help">Created</dt><dd className="font-semibold text-[var(--text)]">{formatTimestamp(detail.created_at)}</dd></div>
        <div><dt className="field-help">Forecast period</dt><dd className="font-semibold text-[var(--text)]">{formatCalendarDate(detail.start_date)} – {formatCalendarDate(detail.end_date)}</dd></div>
        <div>
          <dt className="field-help">Starting balances{inputs.reference_date ? ` (as of ${formatCalendarDate(inputs.reference_date)})` : ""}</dt>
          <dd className="font-semibold tabular-nums text-[var(--text)]">{starting ? `DD ${money(starting.dining_dollars_cents)} · Cash ${money(starting.triton_cash_cents)}` : "Not recorded"}</dd>
        </div>
        <div>
          <dt className="field-help">Projected remaining on {formatCalendarDate(detail.end_date, { month: "short", day: "numeric" })}</dt>
          <dd className="font-semibold tabular-nums text-[var(--text)]">{projected ? `DD ${money(projected.dining_dollars_cents)} · Cash ${money(projected.triton_cash_cents)}` : "Not recorded"}</dd>
        </div>
        <div><dt className="field-help">Scenario</dt><dd className="font-semibold text-[var(--text)]">{scenario ? scenarioLabels[scenario] ?? scenario : "Not recorded"}</dd></div>
      </dl>
      {habits.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-xs tabular-nums text-[var(--text-muted)]">
            <caption className="sr-only">Eating habits used for this forecast</caption>
            <thead><tr className="text-[var(--text)]"><th className="py-1 pr-3">Habit</th><th className="py-1 pr-3">Per day</th><th className="py-1 pr-3">Price</th><th className="py-1">Paid with</th></tr></thead>
            <tbody>
              {habits.map((habit, index) => (
                <tr key={`${habit.name}-${index}`} className="border-t border-[var(--border)]">
                  <td className="py-1 pr-3 text-[var(--text)]">{habit.name}</td>
                  <td className="py-1 pr-3">{habit.frequency}</td>
                  <td className="py-1 pr-3">{money(habit.price_cents)}</td>
                  <td className="py-1">{habit.eligible_accounts.map((account) => accountLabels[account]).join(" or ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button type="button" className="secondary-button mt-4" onClick={onOpenTrajectory}><LineChart size={14} aria-hidden="true" /> Compare with saved balances in Spending Trajectory</button>
    </section>
  );
}

/** What a new saved forecast will start from, or a prompt to save balances first. */
function WalletStart({ wallet, onOpenWallet }: { wallet: WalletLoad; onOpenWallet: () => void }) {
  if (wallet.status === "loading") return <p className="field-help mb-5" role="status">Loading your wallet balances…</p>;
  if (wallet.status === "error") return <div className="error-box mb-5" role="alert"><strong>Couldn’t load your wallet balances.</strong><span>{wallet.message}</span></div>;
  const { latest, stale, days_since_update: age } = wallet.data;
  if (!latest) {
    return (
      <div className="wallet-callout mb-6" role="status">
        <WalletCards size={22} aria-hidden="true" className="shrink-0 text-[var(--primary)]" />
        <div>
          <p className="font-bold text-[var(--text)]">Enter your wallet balances first</p>
          <p className="mt-1 text-sm text-[var(--text-muted)]">Saved forecasts start from your current Dining Dollars and Triton Cash balances. Add them once and you can forecast right away.</p>
          <button type="button" className="primary-button mt-3" onClick={onOpenWallet}>Add wallet balances</button>
        </div>
      </div>
    );
  }
  const start = forecastStartFor(latest);
  return (
    <div className="mb-6 space-y-3">
      <div className="wallet-callout">
        <WalletCards size={22} aria-hidden="true" className="shrink-0 text-[var(--primary)]" />
        <div className="min-w-0 flex-1">
          <p className="metric-label">Starting balances</p>
          <p className="mt-1 font-display text-lg font-bold tabular-nums text-[var(--text)]">DD {money(latest.dining_dollars_cents)} · Cash {money(latest.triton_cash_cents)}</p>
          <p className="text-xs text-[var(--text-muted)]">As of {formatCalendarDate(latest.effective_date)} · new forecasts start {start === campusToday() ? "today" : "on"} {formatCalendarDate(start)}</p>
        </div>
        <button type="button" className="secondary-button self-center" onClick={onOpenWallet}><PencilLine size={14} aria-hidden="true" /> Update balances</button>
      </div>
      {stale && <p className="notice-info"><Info size={16} aria-hidden="true" /> Your balances are {age} days old. Update them for a forecast that starts from today’s numbers.</p>}
    </div>
  );
}

type Props = { wallet: WalletLoad; onOpenWallet: () => void; onOpenTrajectory: () => void };

export function ForecastHistoryPanel({ wallet, onOpenWallet, onOpenTrajectory }: Props) {
  const [history, setHistory] = useState<Load<ParticipantForecastSummary[]>>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Load<ParticipantForecastDetail>>({ status: "idle" });
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ParticipantForecastSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const latestSelection = useRef<string | null>(null);

  const loadHistory = useCallback(async () => {
    setHistory({ status: "loading" });
    try {
      setHistory({ status: "ready", data: await listParticipantForecasts() });
    } catch (error) {
      setHistory({ status: "error", message: errorMessage(error, "Unable to load saved forecasts.") });
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const select = useCallback(async (id: string) => {
    latestSelection.current = id;
    setSelectedId(id);
    setDetail({ status: "loading" });
    try {
      const value = await readParticipantForecast(id);
      if (latestSelection.current === id) setDetail({ status: "ready", data: value });
    } catch (error) {
      if (latestSelection.current === id) setDetail({ status: "error", message: errorMessage(error, "Unable to load that forecast.") });
    }
  }, []);

  async function create(request: ParticipantForecastRequest) {
    setCreating(true);
    try {
      const created = await createParticipantForecast(request);
      // Spending Trajectory opens on the forecast just saved.
      rememberForecastSelection(created.id);
      await loadHistory();
      await select(created.id);
    } finally {
      setCreating(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete || history.status !== "ready") return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteParticipantForecast(pendingDelete.id);
      forgetForecastSelection(pendingDelete.id);
      const next = withoutForecast(history.data, pendingDelete.id, selectedId);
      setHistory({ status: "ready", data: next.history });
      if (next.selectedId !== selectedId) {
        if (next.selectedId) {
          void select(next.selectedId);
        } else {
          latestSelection.current = null;
          setSelectedId(null);
          setDetail({ status: "idle" });
        }
      }
      setPendingDelete(null);
    } catch (error) {
      setDeleteError(errorMessage(error, "Unable to delete that forecast."));
    } finally {
      setDeleting(false);
    }
  }

  const warnings = detail.status === "ready" && Array.isArray(detail.data.inputs.warnings) ? detail.data.inputs.warnings : [];
  const walletReady = wallet.status === "ready" && wallet.data.latest !== null;

  return (
    <section className="panel mt-6">
      <div className="panel-heading">
        <div><p className="eyebrow">Saved forecasts</p><h2 className="panel-title">Forecast from your wallet.</h2></div>
      </div>
      <WalletStart wallet={wallet} onOpenWallet={onOpenWallet} />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        {walletReady ? <ForecastForm loading={creating} onSubmitSaved={create} /> : <div className="chart-empty min-h-40">Your forecast form appears here once your wallet balances are saved.</div>}
        <div>
          <h3 className="mb-3 text-sm font-bold text-[var(--text)]">Forecast history</h3>
          {history.status === "loading" && <p className="field-help" role="status">Loading saved forecasts…</p>}
          {history.status === "error" && (
            <div className="error-box" role="alert"><strong>Couldn’t load saved forecasts.</strong><span>{history.message}</span><button type="button" className="secondary-button mt-2 w-fit" onClick={() => void loadHistory()}>Try again</button></div>
          )}
          {history.status === "ready" && history.data.length === 0 && (
            <div className="chart-empty min-h-40">No saved forecasts yet. Your first forecast will be saved here so you can come back to it anytime.</div>
          )}
          {history.status === "ready" && history.data.length > 0 && (
            <ul className="space-y-2">
              {history.data.map((item) => (
                <li key={item.id} className="flex items-start gap-2">
                  <button type="button" aria-pressed={item.id === selectedId} onClick={() => void select(item.id)} className={`history-item min-w-0 flex-1 ${item.id === selectedId ? "history-item-selected" : ""}`}>
                    <span className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-bold text-[var(--text)]">{shortDate(item.start_date)} – {shortDate(item.end_date)}{item.scenario ? ` · ${scenarioLabels[item.scenario] ?? item.scenario}` : ""}</span>
                      <FundsStatus fundsLast={item.funds_last} unfundedCents={item.total_unfunded_cents} />
                    </span>
                    <span className="mt-1 block">Saved {formatTimestamp(item.created_at)}</span>
                    {item.starting_balances && item.projected_balances && (
                      <span className="mt-1 block tabular-nums">DD {money(item.starting_balances.dining_dollars_cents)} → {money(item.projected_balances.dining_dollars_cents)} · Cash {money(item.starting_balances.triton_cash_cents)} → {money(item.projected_balances.triton_cash_cents)}</span>
                    )}
                    {item.warnings.length > 0 && <span className="mt-1 block">{item.warnings.length} note{item.warnings.length === 1 ? "" : "s"} about its starting balances</span>}
                  </button>
                  <button
                    type="button"
                    className="history-delete"
                    aria-label={`Delete forecast saved ${formatTimestamp(item.created_at)} for ${formatCalendarDate(item.start_date)} – ${formatCalendarDate(item.end_date)}`}
                    title="Delete forecast"
                    onClick={() => { setDeleteError(""); setPendingDelete(item); }}
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      {selectedId && (
        <div className="mt-8 space-y-5 border-t border-[var(--border)] pt-6" aria-live="polite">
          {detail.status === "loading" && <p className="field-help" role="status">Loading that forecast…</p>}
          {detail.status === "ready" && (
            <ForecastInputs
              detail={detail.data}
              onOpenTrajectory={() => {
                rememberForecastSelection(detail.data.id);
                onOpenTrajectory();
              }}
            />
          )}
          {warnings.map((warning) => <p key={warning} className="notice-info"><Info size={16} aria-hidden="true" /> {warning}</p>)}
          {detail.status === "error" && <div className="error-box" role="alert"><strong>Couldn’t load forecast details.</strong><span>{detail.message}</span></div>}
          {detail.status === "ready" && isForecastResponse(detail.data.forecast) && <ForecastDashboard key={detail.data.id} result={detail.data.forecast} />}
        </div>
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
