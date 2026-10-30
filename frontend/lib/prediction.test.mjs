// Run with `npm test`. Fixture mirrors GET /api/v1/pilot/prediction.
import assert from "node:assert/strict";
import { test } from "node:test";
import { predictionRows } from "./prediction.ts";

const w = (dining, cash) => ({ dining_dollars_cents: dining, triton_cash_cents: cash });
const none = w(null, null);
const point = (date, moment, values) => ({
  date, moment, actual: none, actual_as_of: null, predicted: none, lower: none, higher: none, ideal: none, original_plan: none, ...values,
});
const prediction = {
  points: [
    point("2026-10-30", "start", { actual: w(420_000, 45_000), actual_as_of: "2026-10-30", original_plan: w(420_000, 45_000) }),
    point("2026-10-30", "end", { original_plan: w(418_000, 45_000) }),
    point("2026-10-31", "end", { actual: w(415_000, 44_000), actual_as_of: "2026-11-01", predicted: w(415_000, 44_000), lower: w(415_000, 44_000), higher: w(415_000, 44_000), ideal: w(415_000, 44_000) }),
    point("2026-11-01", "end", { predicted: w(412_000, 43_400), lower: w(412_750, 43_550), higher: w(411_250, 43_250), ideal: w(400_000, 40_000) }),
  ],
};

test("rows keep each wallet's own values and never fill in actual balances", () => {
  const dining = predictionRows(prediction, "dining_dollars");
  assert.deepEqual(dining.map((row) => row.actual), [420_000, null, 415_000, null]);
  assert.deepEqual(dining.map((row) => row.actualAsOf), ["2026-10-30", null, "2026-11-01", null]);
  assert.deepEqual(dining.map((row) => row.predicted), [null, null, 415_000, 412_000]);
  assert.deepEqual(dining.map((row) => row.plan), [420_000, 418_000, null, null]);
  const cash = predictionRows(prediction, "triton_cash");
  assert.deepEqual(cash.map((row) => [row.lower, row.predicted, row.higher]).at(-1), [43_550, 43_400, 43_250]);
  assert.equal(cash.at(-1).ideal, 40_000);
});
