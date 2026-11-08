import type { Account, Prediction } from "./types";

export type PredictionRow = {
  date: string;
  moment: "start" | "end";
  /** Only a balance the student actually saved; null everywhere else. */
  actual: number | null;
  actualAsOf: string | null;
  predicted: number | null;
  lower: number | null;
  higher: number | null;
  ideal: number | null;
  plan: number | null;
};

/** One wallet's chart rows, taken directly from the prediction response. */
export function predictionRows(prediction: Prediction, account: Account): PredictionRow[] {
  const key = account === "dining_dollars" ? "dining_dollars_cents" : "triton_cash_cents";
  return prediction.points.map((point) => ({
    date: point.date,
    moment: point.moment,
    actual: point.actual[key],
    actualAsOf: point.actual_as_of,
    predicted: point.predicted[key],
    lower: point.lower[key],
    higher: point.higher[key],
    ideal: point.ideal[key],
    plan: point.original_plan[key]
  }));
}

export const CONFIDENCE_LABELS = {
  none: "No data yet",
  starting: "Starting point",
  preliminary: "Preliminary",
  developing: "Developing",
  established: "Established"
} as const;

// --- Chart geometry: the moving marker and date ticks ---------------------------------------------

export type PlottedPoint = { index: number; x: number; y: number };
export type PolylineLengths = { cumulative: number[]; total: number };

/** Two plotted points are joined by a drawn segment only when their rows are adjacent: a missing
 * value breaks the line, and the dot must never travel across that gap. */
const joined = (a: PlottedPoint, b: PlottedPoint) => b.index - a.index === 1;

/** Cumulative distance along the drawn line at each plotted point (gaps add no length). */
export function polylineLengths(points: PlottedPoint[]): PolylineLengths {
  const cumulative = [0];
  for (let i = 1; i < points.length; i += 1) {
    const step = joined(points[i - 1], points[i]) ? Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y) : 0;
    cumulative.push(cumulative[i - 1] + step);
  }
  return { cumulative, total: cumulative[cumulative.length - 1] ?? 0 };
}

/**
 * Where the marker is at `progress` (0-1 of the line's length). It always lies on a drawn straight
 * segment between two plotted points; `passedIndex` is the latest real plotted row it has reached,
 * which is the only row a readout may name (no invented in-between values).
 */
export function markerAt(points: PlottedPoint[], lengths: PolylineLengths, progress: number): { x: number; y: number; passedIndex: number } {
  if (points.length === 0) throw new Error("no points");
  const target = Math.min(1, Math.max(0, progress)) * lengths.total;
  let segment = 0;
  while (segment < points.length - 2 && lengths.cumulative[segment + 1] < target) segment += 1;
  const start = points[segment];
  const end = points[Math.min(segment + 1, points.length - 1)];
  const span = lengths.cumulative[Math.min(segment + 1, points.length - 1)] - lengths.cumulative[segment];
  const t = span > 0 ? (target - lengths.cumulative[segment]) / span : 0;
  const reached = t >= 1 - 1e-9 ? Math.min(segment + 1, points.length - 1) : segment;
  return { x: start.x + (end.x - start.x) * t, y: start.y + (end.y - start.y) * t, passedIndex: points[reached].index };
}

/** Up to `count` row indices for date labels: the first and last, evenly spaced, one per date. */
export function chartTicks(dates: string[], count: number): number[] {
  if (dates.length === 0) return [];
  const firstOfDate: number[] = [];
  dates.forEach((date, index) => { if (index === 0 || dates[index - 1] !== date) firstOfDate.push(index); });
  if (firstOfDate.length <= count) return firstOfDate;
  const picks = new Set<number>();
  for (let i = 0; i < count; i += 1) picks.add(firstOfDate[Math.round((i * (firstOfDate.length - 1)) / (count - 1))]);
  return [...picks].sort((a, b) => a - b);
}

export type MarkerTrack = { kind: "prediction" | "ideal"; indices: number[] };

/** Which plotted line the moving dot follows: the personalized prediction when it exists, otherwise
 * the ideal path (a goal, never presented as a prediction), otherwise none. Indices are the rows
 * that line is actually drawn through. */
export function markerTrack(rows: Pick<PredictionRow, "predicted" | "ideal">[]): MarkerTrack | null {
  const predicted = rows.flatMap((row, index) => (row.predicted !== null ? [index] : []));
  if (predicted.length > 0) return { kind: "prediction", indices: predicted };
  const ideal = rows.flatMap((row, index) => (row.ideal !== null ? [index] : []));
  return ideal.length > 0 ? { kind: "ideal", indices: ideal } : null;
}

/** The plotted point on the track nearest to a selected row (the dot never leaves the line). */
export function nearestTrackPoint(track: MarkerTrack, rowIndex: number): number {
  let best = 0;
  track.indices.forEach((index, position) => {
    if (Math.abs(index - rowIndex) < Math.abs(track.indices[best] - rowIndex)) best = position;
  });
  return best;
}

// --- Line-aware dot: which plotted series the pointer is on ----------------------------------------

export type SelectableSeries = { key: string; points: PlottedPoint[]; /** separate dots, never joined */ discrete?: boolean };

/** Shortest distance (in SVG units) from (px, py) to what is actually drawn for a series: its points,
 * plus the straight segments between adjacent rows (never across a gap, never for discrete dots). */
export function distanceToSeries(series: SelectableSeries, px: number, py: number): number {
  let best = Infinity;
  series.points.forEach((point, i) => {
    best = Math.min(best, Math.hypot(point.x - px, point.y - py));
    const next = series.points[i + 1];
    if (series.discrete || !next || !joined(point, next)) return;
    const dx = next.x - point.x;
    const dy = next.y - point.y;
    const t = Math.max(0, Math.min(1, ((px - point.x) * dx + (py - point.y) * dy) / (dx * dx + dy * dy || 1)));
    best = Math.min(best, Math.hypot(point.x + t * dx - px, point.y + t * dy - py));
  });
  return best;
}

/** The series closest to the pointer, if it is within `maxDistance`; otherwise null (keep the current one). */
export function closestSeries(list: SelectableSeries[], px: number, py: number, maxDistance: number): string | null {
  let best: { key: string; distance: number } | null = null;
  for (const series of list) {
    if (series.points.length === 0) continue;
    const distance = distanceToSeries(series, px, py);
    if (distance <= maxDistance && (!best || distance < best.distance)) best = { key: series.key, distance };
  }
  return best?.key ?? null;
}

/** Position (in `points`) of the plotted point whose row is nearest `rowIndex`. */
export function nearestPointPosition(points: PlottedPoint[], rowIndex: number): number {
  let best = 0;
  points.forEach((point, position) => {
    if (Math.abs(point.index - rowIndex) < Math.abs(points[best].index - rowIndex)) best = position;
  });
  return best;
}
