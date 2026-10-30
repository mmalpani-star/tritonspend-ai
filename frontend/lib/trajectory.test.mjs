// Run with `npm test`. Forecast selection rules for Spending Trajectory.
import assert from "node:assert/strict";
import { test } from "node:test";
import { pickForecastId, withoutForecast } from "./trajectory.ts";

test("the remembered (e.g. newly created) forecast is selected, else the newest", () => {
  const history = [{ id: "newest" }, { id: "older" }];
  assert.equal(pickForecastId(history, "older"), "older");
  assert.equal(pickForecastId(history, "deleted-or-other-account"), "newest");
  assert.equal(pickForecastId(history, null), "newest");
  assert.equal(pickForecastId([], "older"), null);
});

test("deleting a forecast removes it and falls back to the newest remaining selection", () => {
  const history = [{ id: "c" }, { id: "b" }, { id: "a" }];
  assert.deepEqual(withoutForecast(history, "b", "b"), { history: [{ id: "c" }, { id: "a" }], selectedId: "c" });
  assert.deepEqual(withoutForecast(history, "c", "c"), { history: [{ id: "b" }, { id: "a" }], selectedId: "b" });
  assert.deepEqual(withoutForecast(history, "a", "b"), { history: [{ id: "c" }, { id: "b" }], selectedId: "b" });
  assert.deepEqual(withoutForecast([{ id: "a" }], "a", "a"), { history: [], selectedId: null });
  assert.deepEqual(withoutForecast(history, "c", null), { history: [{ id: "b" }, { id: "a" }], selectedId: null });
  // Cancelling is not deleting: nothing changes until a deletion actually succeeds.
  assert.equal(history.length, 3);
});
