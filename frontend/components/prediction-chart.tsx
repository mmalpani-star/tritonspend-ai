"use client";

import { Pause, Play, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { formatCalendarDate } from "../lib/datetime";
import { chartTicks, closestSeries, markerAt, markerTrack, nearestPointPosition, polylineLengths, predictionRows, type PlottedPoint, type PredictionRow } from "../lib/prediction";
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

const PLAY_MS = 2800;

/** The plotted series the glowing dot can sit on. Each keeps its own colour; the dot adopts it. */
type SeriesKey = "prediction" | "ideal" | "plan" | "actual";
const SERIES: Record<SeriesKey, { label: string; short: string; color: string; pick: (row: PredictionRow) => number | null; discrete?: boolean; note?: string }> = {
  prediction: { label: "Personalized prediction", short: "prediction", color: "var(--chart-projected)", pick: (row) => row.predicted },
  ideal: { label: "Ideal path", short: "ideal path", color: "var(--chart-ideal)", pick: (row) => row.ideal, note: "a goal, not a prediction" },
  plan: { label: "Original forecast plan", short: "original plan", color: "var(--chart-plan)", pick: (row) => row.plan },
  actual: { label: "Saved balance (actual)", short: "saved balances", color: "var(--chart-actual)", pick: (row) => row.actual, discrete: true }
};
const SERIES_ORDER: SeriesKey[] = ["prediction", "ideal", "plan", "actual"];
type Series = { key: SeriesKey; points: PlottedPoint[]; discrete: boolean };

/** Fraction of the way along a series at one of its plotted points (dots: evenly by count). */
function progressAt(series: Series, position: number): number {
  if (series.discrete) return series.points.length > 1 ? position / (series.points.length - 1) : 1;
  const lengths = polylineLengths(series.points);
  return lengths.total > 0 ? lengths.cumulative[position] / lengths.total : 1;
}

/** Chart geometry in real pixels for the available width, so labels stay readable on phones. */
function chartBox(width: number) {
  const W = Math.max(300, Math.round(width));
  if (W < 640) return { W, H: Math.round(Math.max(280, W * 0.82)), PAD: { top: 30, right: 74, bottom: 46, left: 74 }, ticks: 3, compact: true };
  if (W < 1000) return { W, H: 400, PAD: { top: 30, right: 96, bottom: 52, left: 80 }, ticks: 5, compact: false };
  return { W, H: Math.min(520, Math.round(W * 0.42)), PAD: { top: 30, right: 108, bottom: 56, left: 86 }, ticks: 7, compact: false };
}

type Props = { prediction: Prediction; account: Account; summary: AccountPrediction; showPlan: boolean };

const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** One wallet: saved balances, the personalized prediction with its slower/faster range, the ideal, and the original plan. */
export function PredictionChart({ prediction, account, summary, showPlan }: Props) {
  const rows = predictionRows(prediction, account);
  const uid = useId().replace(/:/g, "");
  const [hover, setHover] = useState<number | null>(null);
  const [progress, setProgress] = useState(0); // 0..1 along the drawn prediction line
  const [playing, setPlaying] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const figureRef = useRef<HTMLElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  const { W, H, PAD, ticks: tickCount, compact } = chartBox(width);

  useEffect(() => {
    const element = boxRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const frame = useRef<number | null>(null);
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
  const ranged = rows.map((row, index) => ({ row, index })).filter(({ row }) => row.lower !== null && row.higher !== null);
  const band = ranged.length > 1
    ? `M${ranged.map(({ row, index }) => `${x(index).toFixed(1)},${y(row.lower as number).toFixed(1)}`).join("L")}L${[...ranged].reverse().map(({ row, index }) => `${x(index).toFixed(1)},${y(row.higher as number).toFixed(1)}`).join("L")}Z`
    : "";
  const last = rows[rows.length - 1];
  const observedCount = rows.filter((row) => row.actual !== null).length;

  // Every visible series the dot can sit on, as its exact plotted vertices (row index + position).
  const seriesList: Series[] = useMemo(
    () => SERIES_ORDER.filter((key) => key !== "plan" || showPlan)
      .map((key) => ({
        key,
        discrete: Boolean(SERIES[key].discrete),
        points: rows.flatMap((row, index) => { const value = SERIES[key].pick(row); return value === null ? [] : [{ index, x: x(index), y: y(value) }]; })
      }))
      .filter((series) => series.points.length > 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- geometry depends only on the plotted values
    [prediction, account, showPlan, max, W, H]
  );
  // Default: the personalized prediction, else the ideal path (labelled as a goal), else saved balances.
  const defaultKey: SeriesKey | undefined = markerTrack(rows)?.kind ?? seriesList[0]?.key;
  const [chosenKey, setChosenKey] = useState<SeriesKey | null>(null);
  const active = seriesList.find((series) => series.key === chosenKey) ?? seriesList.find((series) => series.key === defaultKey) ?? null;
  const meta = active ? SERIES[active.key] : null;
  const [pinned, setPinned] = useState<number | null>(null); // a selected point on the active series
  const wasPlaying = useRef(false);
  const lengths = useMemo(() => (active && !active.discrete ? polylineLengths(active.points) : null), [active]);
  const markerPoint = (() => {
    if (!active) return null;
    const n = active.points.length;
    if (pinned !== null) { const point = active.points[Math.min(pinned, n - 1)]; return { x: point.x, y: point.y, passedIndex: point.index }; }
    if (active.discrete || n === 1 || !lengths) { const point = active.points[Math.round(progress * (n - 1))]; return { x: point.x, y: point.y, passedIndex: point.index }; }
    return markerAt(active.points, lengths, progress);
  })();
  const marker = markerPoint;
  const predicted = seriesList.find((series) => series.key === "prediction")?.points ?? [];
  const area = predicted.length > 1
    ? `M${predicted[0].x.toFixed(1)},${(H - PAD.bottom).toFixed(1)}L${predicted.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("L")}L${predicted[predicted.length - 1].x.toFixed(1)},${(H - PAD.bottom).toFixed(1)}Z`
    : "";
  const latestActual = rows.reduce((found, row, index) => (row.actual !== null ? index : found), -1);
  const predictionStart = predicted.length ? predicted[0].index : null;
  const ticks = chartTicks(rows.map((row) => row.date), tickCount);
  const hovered = hover === null ? null : rows[hover];
  const canPlay = Boolean(active && active.points.length > 1);

  const stop = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    setPlaying(false);
  }, []);

  /** Animate the dot along the active series, from where it is (or from the start once finished). */
  const play = useCallback((from = 0) => {
    stop();
    setPinned(null);
    if (prefersReducedMotion()) { setProgress(1); return; } // no motion: rest at the end of the line
    const begin = from >= 0.999 ? 0 : from;
    setHover(null);
    setPlaying(true);
    const start = performance.now();
    const duration = PLAY_MS * (1 - begin);
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / Math.max(1, duration));
      setProgress(begin + (1 - begin) * (1 - (1 - t) ** 3)); // ease out
      if (t < 1) frame.current = requestAnimationFrame(tick);
      else { frame.current = null; setPlaying(false); }
    };
    frame.current = requestAnimationFrame(tick);
  }, [stop]);

  // Play once when the chart scrolls into view (or show it complete with reduced motion).
  useEffect(() => {
    const element = figureRef.current;
    if (!element) return;
    setProgress(prefersReducedMotion() ? 1 : 0);
    if (typeof IntersectionObserver === "undefined") { setProgress(1); return; }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { observer.disconnect(); play(0); }
    }, { threshold: 0.45 });
    observer.observe(element);
    return () => { observer.disconnect(); stop(); };
  }, [play, stop]);

  /** Put the dot on `key`'s plotted point nearest `rowIndex` and show that point. */
  function selectOn(key: SeriesKey, rowIndex: number) {
    const series = seriesList.find((item) => item.key === key);
    if (!series) return;
    const position = nearestPointPosition(series.points, rowIndex);
    if (key !== active?.key) setChosenKey(key);
    setPinned(position);
    setProgress(progressAt(series, position));
    setHover(series.points[position].index);
  }

  function pointerToView(clientX: number, clientY: number) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return null;
    return { x: ((clientX - rect.left) / rect.width) * W, y: ((clientY - rect.top) / rect.height) * H };
  }
  const rowFromViewX = (viewX: number) => Math.min(rows.length - 1, Math.max(0, Math.round(((viewX - PAD.left) / plotWidth) * (rows.length - 1))));

  /** Hover or drag: the series closest to the pointer becomes active (if close enough), and the dot
   * snaps to that series' plotted point nearest the pointer. Playback pauses while you inspect. */
  function onPointer(clientX: number, clientY: number) {
    const view = pointerToView(clientX, clientY);
    if (!view || !active) return;
    if (playing) { wasPlaying.current = true; stop(); }
    const near = closestSeries(seriesList, view.x, view.y, compact ? 22 : 18) as SeriesKey | null;
    selectOn(near ?? active.key, rowFromViewX(view.x));
  }

  function onKey(event: React.KeyboardEvent<SVGSVGElement>) {
    if (!active || !marker) return;
    const current = nearestPointPosition(active.points, marker.passedIndex);
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      stop();
      const next = Math.max(0, Math.min(active.points.length - 1, current + (event.key === "ArrowRight" ? 1 : -1)));
      selectOn(active.key, active.points[next].index);
    }
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      stop();
      const order = seriesList.map((series) => series.key);
      const at = order.indexOf(active.key);
      const key = order[(at + (event.key === "ArrowDown" ? 1 : order.length - 1)) % order.length];
      selectOn(key, marker.passedIndex);
    }
  }

  // Right-edge labels, nudged apart so they never overlap (the values themselves stay exact).
  const endLabels = [
    { text: "Predicted", value: last.predicted, className: "fill-[var(--text)] font-semibold" },
    { text: "Ideal", value: last.ideal, className: "fill-[var(--text-muted)]" },
    { text: "Warning", value: threshold, className: "fill-[var(--danger)]" }
  ]
    .filter((item): item is { text: string; value: number; className: string } => item.value !== null)
    .map((item) => ({ ...item, at: y(item.value) + 5 }))
    .sort((a, b) => a.at - b.at);
  for (let i = 1; i < endLabels.length; i += 1) endLabels[i].at = Math.max(endLabels[i].at, endLabels[i - 1].at + 18);

  const markerRow = marker ? rows[marker.passedIndex] : null;
  const markerValue = markerRow && meta ? meta.pick(markerRow) : null;

  return (
    <figure ref={figureRef} className="trajectory-card">
      <figcaption className="mb-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex items-center gap-3">
            <h3 className="font-display text-xl font-bold tracking-tight text-[var(--text)]">{label}</h3>
            {canPlay && meta && (
              <button type="button" className="chart-play" style={{ "--series": meta.color } as React.CSSProperties} onClick={() => (playing ? stop() : play(progress))}
                aria-label={`${playing ? "Pause" : progress >= 1 ? "Replay" : "Play"} the dot along the ${meta.short}`}>
                {playing ? <Pause size={14} aria-hidden="true" /> : progress >= 1 ? <RotateCcw size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
                <span>{playing ? "Pause" : progress >= 1 ? "Replay" : "Play"}</span>
              </button>
            )}
          </div>
          {last.predicted !== null && <p className="text-sm text-[var(--text-muted)]">Predicted by {shortDate(last.date)}: <strong className="text-[var(--text)] tabular-nums">{money(last.predicted)}</strong></p>}
        </div>
        <ul className="chart-legend" aria-label={`${label} chart legend`}>
          <li><svg width="14" height="14" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="var(--chart-actual)" stroke="var(--surface)" strokeWidth="2" /></svg>Saved balance (actual)</li>
          {summary.daily_pace_cents !== null && <li><svg width="26" height="8" aria-hidden="true"><line x1="1" y1="4" x2="25" y2="4" stroke="var(--chart-projected)" strokeWidth="3.5" strokeLinecap="round" /></svg>Personalized prediction</li>}
          {summary.lower_pace_cents !== null && <li><svg width="26" height="10" aria-hidden="true"><rect x="1" y="1" width="24" height="8" rx="2" fill="var(--chart-band)" opacity="0.22" /></svg>Slower to faster spending</li>}
          {summary.ideal_available && <li><svg width="26" height="8" aria-hidden="true"><line x1="1" y1="4" x2="25" y2="4" stroke="var(--chart-ideal)" strokeWidth="2" strokeDasharray="6 4" /></svg>Ideal to {money(summary.target_cents)}</li>}
          {showPlan && <li><svg width="26" height="8" aria-hidden="true"><line x1="1" y1="4" x2="25" y2="4" stroke="var(--chart-plan)" strokeWidth="2" strokeDasharray="1 4" strokeLinecap="round" /></svg>Original forecast plan</li>}
          {threshold !== null && <li><svg width="26" height="8" aria-hidden="true"><line x1="1" y1="4" x2="25" y2="4" stroke="var(--danger)" strokeWidth="1.5" strokeDasharray="2 3" /></svg>Warning amount {money(threshold)}</li>}
        </ul>
      </figcaption>
      <div className="relative" ref={boxRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full touch-none select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded-xl"
          role="img"
          tabIndex={0}
          aria-label={`${label}: ${observedCount} saved balance${observedCount === 1 ? "" : "s"} from ${pointLabel(rows[0])} to ${pointLabel(last)}.${last.predicted !== null ? ` Predicted ${money(last.predicted)} by ${pointLabel(last)}, between ${money(last.higher ?? last.predicted)} and ${money(last.lower ?? last.predicted)}.` : " No personalized prediction yet."}${last.ideal !== null ? ` Ideal ${money(last.ideal)}.` : ""} Hover or drag across the chart to move the dot onto the nearest line; use the left and right arrow keys to move along it and up and down to switch lines.`}
          onPointerDown={(event) => { event.currentTarget.setPointerCapture?.(event.pointerId); onPointer(event.clientX, event.clientY); }}
          onPointerMove={(event) => onPointer(event.clientX, event.clientY)}
          onPointerLeave={() => {
            setHover(null);
            // Keep the chosen series; if it was playing before you hovered, continue along it.
            if (wasPlaying.current) { wasPlaying.current = false; play(progress); }
          }}
          onFocus={() => setHover(marker ? marker.passedIndex : rows.length - 1)}
          onBlur={() => setHover(null)}
          onKeyDown={onKey}
        >
          <defs>
            <linearGradient id={`${uid}-area`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="var(--chart-projected)" stopOpacity="0.28" />
              <stop offset="1" stopColor="var(--chart-projected)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id={`${uid}-line`} x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="var(--chart-projected)" />
              <stop offset="1" stopColor="var(--chart-band)" />
            </linearGradient>
            <radialGradient id={`${uid}-halo`}>
              <stop offset="0" style={{ stopColor: meta?.color ?? "var(--chart-projected)", stopOpacity: 0.75 }} />
              <stop offset="0.5" style={{ stopColor: meta?.color ?? "var(--chart-projected)", stopOpacity: 0.28 }} />
              <stop offset="1" style={{ stopColor: meta?.color ?? "var(--chart-projected)", stopOpacity: 0 }} />
            </radialGradient>
            <filter id={`${uid}-glow`} x="-20%" y="-50%" width="140%" height="200%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* Saved history vs prediction zone. */}
          {predictionStart !== null && predictionStart > 0 && (
            <>
              <rect x={x(predictionStart)} y={PAD.top} width={W - PAD.right - x(predictionStart)} height={plotHeight} fill="var(--chart-band)" opacity="0.05" />
              <line x1={x(predictionStart)} x2={x(predictionStart)} y1={PAD.top - 6} y2={H - PAD.bottom} stroke="var(--chart-ideal)" strokeWidth="1" strokeDasharray="3 4" />
              <text x={x(predictionStart) - 8} y={PAD.top - 10} textAnchor="end" className="fill-[var(--text-muted)] text-[13px] font-semibold">{compact ? "Saved" : "Saved history"}</text>
              <text x={x(predictionStart) + 8} y={PAD.top - 10} className="fill-[var(--text-muted)] text-[13px] font-semibold">{compact ? "Predicted →" : "Prediction →"}</text>
            </>
          )}

          {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
            <g key={fraction}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(max * fraction)} y2={y(max * fraction)} stroke="var(--border)" strokeWidth="1" strokeDasharray={fraction === 0 ? undefined : "2 6"} />
              <text x={PAD.left - 12} y={y(max * fraction) + 5} textAnchor="end" className={`fill-[var(--text-muted)] ${compact ? "text-[12px]" : "text-[14px]"} tabular-nums`}>{money(max * fraction)}</text>
            </g>
          ))}
          {ticks.map((index) => (
            <g key={index}>
              <line x1={x(index)} x2={x(index)} y1={H - PAD.bottom} y2={H - PAD.bottom + 6} stroke="var(--border)" />
              <text x={x(index)} y={H - PAD.bottom + 26} textAnchor={index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle"} className={`fill-[var(--text-muted)] ${compact ? "text-[12px]" : "text-[14px]"}`}>{shortDate(rows[index].date)}</text>
            </g>
          ))}

          {threshold !== null && <line x1={PAD.left} x2={W - PAD.right} y1={y(threshold)} y2={y(threshold)} stroke="var(--danger)" strokeWidth="1.5" strokeDasharray="2 5" opacity="0.8" />}
          {band && <path d={band} fill="var(--chart-band)" opacity="0.16" />}
          {area && <path d={area} fill={`url(#${uid}-area)`} />}
          {showPlan && <path d={path((row) => row.plan)} fill="none" stroke="var(--chart-plan)" strokeWidth={active?.key === "plan" ? 3.25 : 2.25} strokeDasharray="1 6" strokeLinecap="round" className="chart-series" />}
          <path d={path((row) => row.ideal)} fill="none" stroke="var(--chart-ideal)" strokeWidth={active?.key === "ideal" ? 3.25 : 2.25} strokeDasharray="8 6" strokeLinecap="round" className="chart-series" />
          <path d={path((row) => row.lower)} fill="none" stroke="var(--chart-band)" strokeWidth="1.25" opacity="0.6" />
          <path d={path((row) => row.higher)} fill="none" stroke="var(--chart-band)" strokeWidth="1.25" opacity="0.6" />
          {/* The prediction line, dimmed ahead of the marker and bright behind it (the trail). */}
          <path d={path((row) => row.predicted)} fill="none" stroke={`url(#${uid}-line)`} strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" opacity="0.32" />
          {/* Glowing trail behind the dot — only on the prediction, so other lines never look like one. */}
          {active?.key === "prediction" && active.points.length > 1 && (
            <path d={path((row) => row.predicted)} pathLength={1} strokeDasharray="1 1" strokeDashoffset={1 - progress} fill="none" stroke={`url(#${uid}-line)`} strokeWidth="4.5" strokeLinejoin="round" strokeLinecap="round" filter={`url(#${uid}-glow)`} />
          )}
          {endLabels.map((item) => <text key={item.text} x={W - PAD.right + (compact ? 14 : 20)} y={item.at} className={`${compact ? "text-[12px]" : "text-[14px]"} ${item.className}`}>{item.text}</text>)}
          {/* Saved balances are separate dots: days without one stay empty. */}
          {rows.map((row, index) => row.actual !== null && (
            <g key={`${row.date}-${row.moment}`}>
              <circle cx={x(index)} cy={y(row.actual)} r="11" fill="var(--chart-actual)" opacity={index === latestActual ? 0.22 : 0.12} />
              <circle cx={x(index)} cy={y(row.actual)} r="6.5" fill="var(--chart-actual)" stroke="var(--surface)" strokeWidth="2.5" />
            </g>
          ))}
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--text-muted)" strokeWidth="1" opacity="0.7" />}
          {marker && meta && (
            <g
              aria-hidden="true"
              className={`chart-marker ${playing ? "" : "is-settling"}`}
              data-track={active?.key}
              data-x={marker.x.toFixed(2)}
              data-y={marker.y.toFixed(2)}
              style={{ transform: `translate(${marker.x}px, ${marker.y}px)`, "--series": meta.color } as React.CSSProperties}
            >
              <circle r="22" fill={`url(#${uid}-halo)`} className="chart-marker-halo" />
              <circle r="7" className="chart-marker-ring" strokeWidth="3.5" />
              <circle r="2.75" className="chart-marker-core" />
            </g>
          )}
        </svg>
        {hovered && hover !== null && (
          <div
            className="chart-tooltip"
            style={{ left: `${(x(hover) / W) * 100}%`, transform: x(hover) > W / 2 ? "translateX(calc(-100% - 14px))" : "translateX(14px)" }}
            aria-hidden="true"
          >
            <p className="font-semibold text-[var(--text)]">{label} · {pointLabel(hovered)}</p>
            {meta && SERIES[active!.key].pick(hovered) !== null && (
              <p className="chart-tooltip-active" style={{ "--series": meta.color } as React.CSSProperties}>
                <span className="chart-swatch" aria-hidden="true" /><strong>{money(SERIES[active!.key].pick(hovered) as number)}</strong> <span>{meta.label}{meta.note ? ` (${meta.note})` : ""}{active!.key === "actual" && hovered.actualAsOf ? ` · as of ${shortDate(hovered.actualAsOf)}` : ""}</span>
              </p>
            )}
            {hovered.actual !== null && active?.key !== "actual" && <p><strong>{money(hovered.actual)}</strong> <span>Saved balance (as of {shortDate(hovered.actualAsOf as string)})</span></p>}
            {hovered.predicted !== null && active?.key !== "prediction" && <p><strong>{money(hovered.predicted)}</strong> <span>Predicted</span></p>}
            {hovered.lower !== null && hovered.higher !== null && <p><strong>{money(hovered.higher)}–{money(hovered.lower)}</strong> <span>Faster–slower spending</span></p>}
            {hovered.ideal !== null && active?.key !== "ideal" && <p><strong>{money(hovered.ideal)}</strong> <span>Ideal</span></p>}
            {showPlan && hovered.plan !== null && active?.key !== "plan" && <p><strong>{money(hovered.plan)}</strong> <span>Original forecast plan</span></p>}
            {hovered.actual === null && hovered.predicted === null && hovered.ideal === null && (!showPlan || hovered.plan === null) && <p>No saved balance for this day.</p>}
          </div>
        )}
      </div>

      <p className="chart-readout mt-3" aria-live="polite">
        {meta && markerRow && (
          <>
            <span className="chart-swatch" style={{ "--series": meta.color } as React.CSSProperties} aria-hidden="true" />
            Dot on <strong>{meta.label}</strong>{meta.note ? ` — ${meta.note}` : ""} · {pointLabel(markerRow)}
            {markerValue !== null && <> · <strong>{money(markerValue)}</strong></>}
          </>
        )}
      </p>

      <details className="weekly-caps mt-3">
        <summary>View {label} as a table</summary>
        <div className="mt-3 max-h-72 overflow-auto">
          <table className="w-full text-left text-sm tabular-nums text-[var(--text-muted)]">
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
