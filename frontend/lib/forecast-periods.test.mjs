// Weekly / monthly period totals sum every day, not just the last one.
import assert from "node:assert/strict";
import { test } from "node:test";
import { mondayOf } from "./datetime.ts";
import { groupDays, periodTotals } from "./forecast-periods.ts";

const day = (date, dd, tc, unfunded = 0) => ({
  date, expected_spending_cents: dd + tc + unfunded, paid_dining_dollars_cents: dd, paid_triton_cash_cents: tc,
  unfunded_cents: unfunded, remaining_balances: { dining_dollars_cents: 0, triton_cash_cents: 0 }, funds_last: unfunded === 0
});

// Thu Oct 29 - Tue Nov 3 2026: weeks start Mon Oct 26 and Mon Nov 2; months Oct and Nov.
const DAYS = [
  day("2026-10-29", 1_000, 200), day("2026-10-30", 1_500, 0), day("2026-10-31", 0, 350, 75),
  day("2026-11-01", 800, 125), day("2026-11-02", 650, 0, 40), day("2026-11-03", 0, 900)
];

test("weekly totals", () => {
  const weeks = groupDays(DAYS, mondayOf);
  assert.deepEqual(weeks.map((w) => w.key), ["2026-10-26", "2026-11-02"]);
  assert.deepEqual(periodTotals(weeks[0].days), { dayCount: 4, spendingCents: 3_975 + 75, paidDiningDollarsCents: 3_300, paidTritonCashCents: 675, unfundedCents: 75 });
  assert.deepEqual(periodTotals(weeks[1].days), { dayCount: 2, spendingCents: 1_590, paidDiningDollarsCents: 650, paidTritonCashCents: 900, unfundedCents: 40 });
});

test("monthly totals", () => {
  const months = groupDays(DAYS, (date) => date.slice(0, 7));
  assert.deepEqual(months.map((m) => m.key), ["2026-10", "2026-11"]);
  const october = periodTotals(months[0].days);
  assert.deepEqual([october.paidDiningDollarsCents, october.paidTritonCashCents, october.unfundedCents], [2_500, 550, 75]);
  const november = periodTotals(months[1].days);
  assert.deepEqual([november.paidDiningDollarsCents, november.paidTritonCashCents, november.unfundedCents], [1_450, 1_025, 40]);
});

test("totals equal the sum of the daily values for any grouping", () => {
  const all = periodTotals(DAYS);
  for (const keyOf of [(d) => d, mondayOf, (d) => d.slice(0, 7)]) {
    const parts = groupDays(DAYS, keyOf).map((g) => periodTotals(g.days));
    for (const field of Object.keys(all)) assert.equal(parts.reduce((sum, p) => sum + p[field], 0), all[field], field);
  }
  // The last day alone (the old bug) would understate the first week.
  assert.notEqual(periodTotals(groupDays(DAYS, mondayOf)[0].days).paidDiningDollarsCents, DAYS[3].paid_dining_dollars_cents);
});

test("single-day and empty periods are safe", () => {
  assert.deepEqual(periodTotals([DAYS[1]]), { dayCount: 1, spendingCents: 1_500, paidDiningDollarsCents: 1_500, paidTritonCashCents: 0, unfundedCents: 0 });
  assert.deepEqual(periodTotals([]), { dayCount: 0, spendingCents: 0, paidDiningDollarsCents: 0, paidTritonCashCents: 0, unfundedCents: 0 });
  assert.deepEqual(groupDays([], mondayOf), []);
});
