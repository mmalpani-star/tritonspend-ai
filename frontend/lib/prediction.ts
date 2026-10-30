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
