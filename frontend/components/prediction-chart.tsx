"use client";

import { useRef, useState } from "react";
import { formatCalendarDate } from "../lib/datetime";
import { predictionRows, type PredictionRow } from "../lib/prediction";
import { Account, AccountPrediction, Prediction } from "../lib/types";
import { formatMoney as money } from "../lib/wallet";

export const accountLabels: Record<Account, string> = { dining_dollars: "Dining Dollars", triton_cash: "Triton Cash" };

const shortDate = (date: string) => formatCalendarDate(date, { month: "short", day: "numeric" });
/** "Oct 30 · start of day" / "Oct 31 · end of day". */
const pointLabel = (row: PredictionRow) => `${shortDate(row.date)} · ${row.moment === "start" ? "start of day" : "end of day"}`;

function niceMax(cents: number): number {
  const dollars = Math.max(cents, 100) / 100;
  const power = 10 ** Math.floor(Math.log10(dollars));
  const step = [1, 2, 2.5, 5, 10].find((multiple) => multiple * power >= dollars) ?? 10;
  return step * power * 100;
}

const W = 640;
const H = 260;
const PAD = { top: 16, right: 92, bottom: 28, left: 64 };

type Props = { prediction: Prediction; account: Account; summary: AccountPrediction; showPlan: boolean };

/** One wallet: saved balances, the personalized prediction with its slower/faster range, the ideal, and the original plan. */
export function PredictionChart({ prediction, account, summary, showPlan }: Props) {
  const rows = predictionRows(prediction, account);
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const label = accountLabels[account];
  const threshold = summary.target_basis === "zero" ? null : summary.target_cents;
  const values = rows
    .flatMap((row) => [row.actual, row.predicted, row.lower, row.higher, row.ideal, showPlan ? row.plan : null])
    .filter((value): value is number => value !== null);
  const max = niceMax(Math.max(0, threshold ?? 0, ...values));
  const plotWidth = W - PAD.left - PAD.right;
  const plotHeight = H - PAD.top - PAD.bottom;
  const x = (index: number) => PAD.left + (rows.length === 1 ? 0 : (index * plotWidth) / (rows.length - 1));
  const y = (value: number) => PAD.top + (1 - value / max) * plotHeight;
  const path = (pick: (row: PredictionRow) => number | null) =>
    rows.reduce((d, row, index) => {
      const value = pick(row);
      if (value === null) return d;
      const previous = index > 0 ? pick(rows[index - 1]) : null;
      return `${d}${previous === null ? "M" : "L"}${x(index).toFixed(1)},${y(value).toFixed(1)}`;
    }, "");
  // Shaded range between the slower and faster paths.
  const ranged = rows.map((row, index) => ({ row, index })).filter(({ row }) => row.lower !== null && row.higher !== null);
  const band = ranged.length > 1
    ? `M${ranged.map(({ row, index }) => `${x(index).toFixed(1)},${y(row.lower as number).toFixed(1)}`).join("L")}L${[...ranged].reverse().map(({ row, index }) => `${x(index).toFixed(1)},${y(row.higher as number).toFixed(1)}`).join("L")}Z`
    : "";
  const last = rows[rows.length - 1];
  const observedCount = rows.filter((row) => row.actual !== null).length;
  const hovered = hover === null ? null : rows[hover];

  function indexFromPointer(clientX: number) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return null;
    const viewX = ((clientX - rect.left) / rect.width) * W;
    return Math.min(rows.length - 1, Math.max(0, Math.round(((viewX - PAD.left) / plotWidth) * (rows.length - 1))));
  }

  const endLabels = [
    { text: "Predicted", value: last.predicted, className: "fill-[var(--text)] font-semibold" },
    { text: "Ideal", value: last.ideal, className: "fill-[var(--text-muted)]" }
  ].filter((item): item is { text: string; value: number; className: string } => item.value !== null);
  if (endLabels.length === 2 && Math.abs(y(endLabels[0].value) - y(endLabels[1].value)) < 14) endLabels.pop();

  return (
    <figure className="trajectory-card">
      <figcaption className="mb-3">
        <h3 className="text-sm font-bold text-[var(--text)]">{label}</h3>
        <ul className="chart-legend" aria-label={`${label} chart legend`}>
          <li><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4" fill="var(--chart-actual)" stroke="var(--surface)" strokeWidth="2" /></svg>Saved balance (actual)</li>
          {summary.daily_pace_cents !== null && <li><svg width="22" height="8" aria-hidden="true"><line x1="1" y1="4" x2="21" y2="4" stroke="var(--chart-projected)" strokeWidth="3" strokeLinecap="round" /></svg>Personalized prediction</li>}
          {summary.lower_pace_cents !== null && <li><svg width="22" height="10" aria-hidden="true"><rect x="1" y="1" width="20" height="8" rx="2" fill="var(--chart-projected)" opacity="0.18" /></svg>Slower to faster spending</li>}
          {summary.ideal_available && <li><svg width="22" height="8" aria-hidden="true"><line x1="1" y1="4" x2="21" y2="4" stroke="var(--text-muted)" strokeWidth="2" strokeDasharray="5 4" /></svg>Ideal to {money(summary.target_cents)}</li>}
          {showPlan && <li><svg width="22" height="8" aria-hidden="true"><line x1="1" y1="4" x2="21" y2="4" stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="1 3" strokeLinecap="round" /></svg>Original forecast plan</li>}
          {threshold !== null && <li><svg width="22" height="8" aria-hidden="true"><line x1="1" y1="4" x2="21" y2="4" stroke="var(--danger)" strokeWidth="1.5" strokeDasharray="2 3" /></svg>Warning amount {money(threshold)}</li>}
        </ul>
      </figcaption>
      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full touch-none select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
          role="img"
          tabIndex={0}
          aria-label={`${label}: ${observedCount} saved balance${observedCount === 1 ? "" : "s"} from ${pointLabel(rows[0])} to ${pointLabel(last)}.${last.predicted !== null ? ` Predicted ${money(last.predicted)} by ${pointLabel(last)}, between ${money(last.higher ?? last.predicted)} and ${money(last.lower ?? last.predicted)}.` : " No personalized prediction yet."}${last.ideal !== null ? ` Ideal ${money(last.ideal)}.` : ""} Use the arrow keys to inspect days.`}
          onPointerMove={(event) => setHover(indexFromPointer(event.clientX))}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover((current) => current ?? rows.length - 1)}
          onBlur={() => setHover(null)}
          onKeyDown={(event) => {
            if (event.key === "ArrowRight") setHover((current) => Math.min(rows.length - 1, (current ?? -1) + 1));
            if (event.key === "ArrowLeft") setHover((current) => Math.max(0, (current ?? 1) - 1));
          }}
        >
          {[0, 0.5, 1].map((fraction) => (
            <g key={fraction}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(max * fraction)} y2={y(max * fraction)} stroke="var(--border)" strokeWidth="1" />
              <text x={PAD.left - 8} y={y(max * fraction) + 4} textAnchor="end" className="fill-[var(--text-muted)] text-[11px] tabular-nums">{money(max * fraction)}</text>
            </g>
          ))}
          <text x={PAD.left} y={H - 8} className="fill-[var(--text-muted)] text-[11px]">{shortDate(rows[0].date)}</text>
          <text x={W - PAD.right} y={H - 8} textAnchor="end" className="fill-[var(--text-muted)] text-[11px]">{shortDate(last.date)}</text>
          {threshold !== null && <line x1={PAD.left} x2={W - PAD.right} y1={y(threshold)} y2={y(threshold)} stroke="var(--danger)" strokeWidth="1.25" strokeDasharray="2 4" opacity="0.7" />}
          {band && <path d={band} fill="var(--chart-projected)" opacity="0.14" />}
          {showPlan && <path d={path((row) => row.plan)} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="1 4" strokeLinecap="round" opacity="0.9" />}
          <path d={path((row) => row.ideal)} fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeDasharray="6 5" strokeLinecap="round" />
          <path d={path((row) => row.lower)} fill="none" stroke="var(--chart-projected)" strokeWidth="1" opacity="0.55" />
          <path d={path((row) => row.higher)} fill="none" stroke="var(--chart-projected)" strokeWidth="1" opacity="0.55" />
          <path key={`predicted-${prediction.comparison?.id ?? "none"}-${last.predicted}`} className="chart-line-draw" pathLength={1} d={path((row) => row.predicted)} fill="none" stroke="var(--chart-projected)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
          {endLabels.map((item) => <text key={item.text} x={W - PAD.right + 8} y={y(item.value) + 4} className={`text-[11px] ${item.className}`}>{item.text}</text>)}
          {/* Saved balances are separate dots: days without one stay empty. */}
          {rows.map((row, index) => row.actual !== null && (
            <circle key={`${row.date}-${row.moment}`} cx={x(index)} cy={y(row.actual)} r="5" fill="var(--chart-actual)" stroke="var(--surface)" strokeWidth="2" />
          ))}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--text-muted)" strokeWidth="1" />}
        </svg>
        {hovered && hover !== null && (
          <div
            className="chart-tooltip"
            style={{ left: `${(x(hover) / W) * 100}%`, transform: x(hover) > W / 2 ? "translateX(calc(-100% - 12px))" : "translateX(12px)" }}
            aria-hidden="true"
          >
            <p className="font-semibold text-[var(--text)]">{label} · {pointLabel(hovered)}</p>
            {hovered.actual !== null && <p><strong>{money(hovered.actual)}</strong> <span>Saved balance (as of {shortDate(hovered.actualAsOf as string)})</span></p>}
            {hovered.predicted !== null && <p><strong>{money(hovered.predicted)}</strong> <span>Predicted</span></p>}
            {hovered.lower !== null && hovered.higher !== null && <p><strong>{money(hovered.higher)}–{money(hovered.lower)}</strong> <span>Faster–slower spending</span></p>}
            {hovered.ideal !== null && <p><strong>{money(hovered.ideal)}</strong> <span>Ideal</span></p>}
            {showPlan && hovered.plan !== null && <p><strong>{money(hovered.plan)}</strong> <span>Original forecast plan</span></p>}
            {hovered.actual === null && hovered.predicted === null && hovered.ideal === null && (!showPlan || hovered.plan === null) && <p>No saved balance for this day.</p>}
          </div>
        )}
      </div>
      <details className="weekly-caps">
        <summary>View {label} as a table</summary>
        <div className="mt-3 max-h-64 overflow-auto">
          <table className="w-full text-left text-xs tabular-nums text-[var(--text-muted)]">
            <thead><tr className="text-[var(--text)]"><th className="py-1 pr-3">Date</th><th className="py-1 pr-3">Saved (actual)</th><th className="py-1 pr-3">Predicted</th><th className="py-1 pr-3">Faster – slower</th><th className="py-1 pr-3">Ideal</th>{showPlan && <th className="py-1">Original plan</th>}</tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.date}-${row.moment}`} className="border-t border-[var(--border)]">
                  <td className="py-1 pr-3">{pointLabel(row)}</td>
                  <td className="py-1 pr-3">{row.actual === null ? "—" : money(row.actual)}</td>
                  <td className="py-1 pr-3">{row.predicted === null ? "—" : money(row.predicted)}</td>
                  <td className="py-1 pr-3">{row.lower === null || row.higher === null ? "—" : `${money(row.higher)} – ${money(row.lower)}`}</td>
                  <td className="py-1 pr-3">{row.ideal === null ? "—" : money(row.ideal)}</td>
                  {showPlan && <td className="py-1">{row.plan === null ? "—" : money(row.plan)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
