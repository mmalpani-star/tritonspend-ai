// Failed API responses become readable messages, never "[object Object]".
import assert from "node:assert/strict";
import { test } from "node:test";
import { errorDetail } from "./api-errors.ts";

const FALLBACK = "Forecast request failed (422)";

test("string details are shown as is", () => {
  assert.equal(errorDetail({ detail: "date range must not be reversed" }, FALLBACK), "date range must not be reversed");
});

test("FastAPI validation lists become readable text", () => {
  const body = { detail: [
    { loc: ["body", "habits", 0, "frequency"], msg: "Value error, frequency must be at most 24 per day", type: "value_error" },
    { loc: ["body", "dining_dollars_cents"], msg: "Input should be less than or equal to 10000000", type: "less_than_equal" }
  ] };
  const message = errorDetail(body, FALLBACK);
  assert.equal(message, "frequency must be at most 24 per day Input should be less than or equal to 10000000");
  assert.ok(!message.includes("[object Object]"));
});

test("anything else falls back to the status message", () => {
  for (const body of [null, {}, { detail: "" }, { detail: [] }, { detail: [{}] }, { detail: [null] }, { detail: { nested: true } }, "plain text"]) {
    assert.equal(errorDetail(body, FALLBACK), FALLBACK, JSON.stringify(body));
  }
});
