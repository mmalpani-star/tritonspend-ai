/** Grouping and totals for the forecast result's daily / weekly / monthly views. No runtime imports (Node tests load it directly). */
import type { DailyForecast } from "./types";

export type PeriodTotals = {
  dayCount: number;
  spendingCents: number;
  paidDiningDollarsCents: number;
  paidTritonCashCents: number;
  unfundedCents: number;
};

/** Sums every day in the period. An empty period is all zeros. */
export function periodTotals(days: DailyForecast[]): PeriodTotals {
  return days.reduce<PeriodTotals>(
    (total, day) => ({
      dayCount: total.dayCount + 1,
      spendingCents: total.spendingCents + day.expected_spending_cents,
      paidDiningDollarsCents: total.paidDiningDollarsCents + day.paid_dining_dollars_cents,
      paidTritonCashCents: total.paidTritonCashCents + day.paid_triton_cash_cents,
      unfundedCents: total.unfundedCents + day.unfunded_cents
    }),
    { dayCount: 0, spendingCents: 0, paidDiningDollarsCents: 0, paidTritonCashCents: 0, unfundedCents: 0 }
  );
}

/** Consecutive days grouped by `keyOf` (e.g. the date, its Monday, or its month), in first-seen order. */
export function groupDays(days: DailyForecast[], keyOf: (date: string) => string): { key: string; days: DailyForecast[] }[] {
  const groups = new Map<string, DailyForecast[]>();
  for (const day of days) {
    const key = keyOf(day.date);
    groups.set(key, [...(groups.get(key) ?? []), day]);
  }
  return [...groups.entries()].map(([key, grouped]) => ({ key, days: grouped }));
}
