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

// --- Chart geometry -------------------------------------------------------------------------------
import { chartTicks, markerAt, polylineLengths } from "./prediction.ts";

const line = [{ index: 4, x: 0, y: 0 }, { index: 5, x: 30, y: 40 }, { index: 6, x: 60, y: 40 }]; // segments of 50 and 30

test("chart marker: travels exactly along the drawn segments", () => {
  const lengths = polylineLengths(line);
  assert.deepEqual(lengths, { cumulative: [0, 50, 80], total: 80 });
  assert.deepEqual(markerAt(line, lengths, 0), { x: 0, y: 0, passedIndex: 4 });
  assert.deepEqual(markerAt(line, lengths, 1), { x: 60, y: 40, passedIndex: 6 });
  const quarter = markerAt(line, lengths, 0.25); // 20 of 80: 40% along the first segment
  assert.ok(Math.abs(quarter.x - 12) < 1e-9 && Math.abs(quarter.y - 16) < 1e-9);
  assert.equal(quarter.passedIndex, 4); // never names an in-between value
  const corner = markerAt(line, lengths, 50 / 80);
  assert.deepEqual([corner.x, corner.y, corner.passedIndex], [30, 40, 5]);
  const second = markerAt(line, lengths, 0.9); // on the flat second segment
  assert.ok(Math.abs(second.y - 40) < 1e-9 && second.x > 30 && second.x < 60);
  assert.deepEqual(markerAt(line, lengths, 7), markerAt(line, lengths, 1)); // clamped
  const single = [{ index: 2, x: 5, y: 9 }];
  assert.deepEqual(markerAt(single, polylineLengths(single), 0.5), { x: 5, y: 9, passedIndex: 2 });
});

test("chart ticks: first and last date, evenly spaced, one label per date", () => {
  const dates = ["d1", "d1", "d2", "d2", "d3", "d3", "d4", "d4", "d5", "d5", "d6", "d6", "d7", "d7"];
  assert.deepEqual(chartTicks(dates, 4), [0, 4, 8, 12]);
  assert.deepEqual(chartTicks(["a", "a", "b"], 6), [0, 2]);
  assert.deepEqual(chartTicks([], 5), []);
});

import { markerTrack, nearestTrackPoint } from "./prediction.ts";

test("chart marker track: prediction first, ideal as a labelled fallback, never invented", () => {
  const rows = [
    { predicted: null, ideal: null }, { predicted: null, ideal: 900 }, { predicted: 880, ideal: 850 }, { predicted: 840, ideal: 800 }
  ];
  assert.deepEqual(markerTrack(rows), { kind: "prediction", indices: [2, 3] });
  const noPrediction = rows.map((row) => ({ ...row, predicted: null }));
  assert.deepEqual(markerTrack(noPrediction), { kind: "ideal", indices: [1, 2, 3] });
  assert.equal(markerTrack(rows.map(() => ({ predicted: null, ideal: null }))), null);
  const track = markerTrack(rows);
  assert.equal(nearestTrackPoint(track, 0), 0); // a history day snaps to the start of the line
  assert.equal(nearestTrackPoint(track, 3), 1);
  assert.equal(nearestTrackPoint(track, 2), 0);
});

import { closestSeries, distanceToSeries, nearestPointPosition } from "./prediction.ts";

test("line-aware dot: the series nearest the pointer, measured against what is actually drawn", () => {
  const prediction = { key: "prediction", points: [{ index: 0, x: 0, y: 100 }, { index: 1, x: 100, y: 100 }] };
  const ideal = { key: "ideal", points: [{ index: 0, x: 0, y: 140 }, { index: 1, x: 100, y: 140 }] };
  const actual = { key: "actual", discrete: true, points: [{ index: 0, x: 0, y: 60 }, { index: 1, x: 100, y: 60 }] };
  assert.equal(distanceToSeries(prediction, 50, 108), 8); // on the segment, not just the points
  assert.equal(distanceToSeries(actual, 50, 60), 50); // dots are never joined
  assert.equal(closestSeries([prediction, ideal, actual], 50, 104, 18), "prediction");
  assert.equal(closestSeries([prediction, ideal, actual], 50, 135, 18), "ideal");
  assert.equal(closestSeries([prediction, ideal, actual], 98, 62, 18), "actual");
  assert.equal(closestSeries([prediction, ideal, actual], 50, 200, 18), null); // too far: keep the current series
  // A gap in the data is not a segment: the middle of the gap is far from the series.
  const gappy = { key: "plan", points: [{ index: 0, x: 0, y: 0 }, { index: 3, x: 300, y: 0 }] };
  assert.equal(distanceToSeries(gappy, 150, 0), 150);
  assert.equal(nearestPointPosition(gappy.points, 2), 1);
  assert.equal(nearestPointPosition(gappy.points, 1), 0);
});

test("chart marker never travels across a gap in the data", () => {
  const points = [{ index: 0, x: 0, y: 0 }, { index: 1, x: 10, y: 0 }, { index: 4, x: 40, y: 0 }, { index: 5, x: 50, y: 0 }];
  const lengths = polylineLengths(points);
  assert.deepEqual(lengths.cumulative, [0, 10, 10, 20]); // the gap adds no length
  for (let p = 0; p <= 1; p += 0.05) {
    const m = markerAt(points, lengths, p);
    assert.ok(m.x <= 10 + 1e-9 || m.x >= 40 - 1e-9, `marker inside the gap at x=${m.x}`);
  }
});
