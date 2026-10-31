// Forecast form checks mirror the API limits (backend/app/schemas.py).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  MAX_BALANCE_CENTS, MAX_FORECAST_DAYS, MAX_HABITS, MAX_PRICE_CENTS,
  balanceError, dateRangeError, dollarsToCents, frequencyError, inclusiveDays, parseWalletAmounts, validateHabits
} from "./forecast-limits.ts";

const meal = (overrides = {}) => ({ name: "Lunch", frequency: "1", eligible_accounts: ["dining_dollars"], ...overrides });

test("limits match the API", () => {
  assert.deepEqual([MAX_FORECAST_DAYS, MAX_HABITS, MAX_BALANCE_CENTS, MAX_PRICE_CENTS], [366, 50, 10_000_000, 100_000]);
});

test("frequency: same accepted and rejected values as the API", () => {
  for (const ok of ["0", "1", "1/2", "24", "1/365", "8760/365", "0/7", "000000001"]) assert.equal(frequencyError(ok), null, ok);
  const reasons = {
    "25": "per day", "8761/365": "per day", "1/366": "denominator", "1/0": "denominator", "0/0": "denominator",
    "0000000001": "characters", ["9".repeat(100_000)]: "characters",
    "²": "like 1", "١": "like 1", "１": "like 1", "": "like 1", "/": "like 1", "1/": "like 1", "1/2/3": "like 1",
    "0.5": "like 1", "-1": "like 1", " 1": "like 1", "1 /2": "like 1"
  };
  for (const [value, reason] of Object.entries(reasons)) assert.match(frequencyError(value), new RegExp(reason), JSON.stringify(value).slice(0, 20));
});

test("dates: inclusive day count and the 366-day limit", () => {
  assert.equal(inclusiveDays("2026-10-30", "2026-10-30"), 1);
  assert.equal(inclusiveDays("2026-10-16", "2027-10-16"), 366);
  assert.equal(inclusiveDays("2026-03-07", "2026-03-09"), 3); // across a daylight-saving change
  assert.equal(dateRangeError("2026-10-16", "2027-10-16"), null);
  assert.match(dateRangeError("2026-10-16", "2027-10-17"), /at most 366 days/);
  assert.match(dateRangeError("2026-01-01", "9999-12-31"), /at most 366 days/);
  assert.match(dateRangeError("2026-10-31", "2026-10-30"), /on or before/);
});

test("balances: $100,000 per wallet", () => {
  assert.equal(balanceError("The Dining Dollars balance", MAX_BALANCE_CENTS), null);
  assert.equal(balanceError("The Triton Cash balance", MAX_BALANCE_CENTS + 1), "The Triton Cash balance can be at most $100,000.");
  assert.equal(dollarsToCents("100000"), MAX_BALANCE_CENTS);
  assert.equal(dollarsToCents("9".repeat(400)), null); // unsafe integer, never sent
});

test("habits: converted to cents, or the first problem naming the habit", () => {
  assert.deepEqual(validateHabits([meal(), meal({ name: "Coffee", frequency: "1/2" })], ["3.75", "0"]), {
    habits: [{ ...meal(), price_cents: 375 }, { ...meal({ name: "Coffee", frequency: "1/2" }), price_cents: 0 }]
  });
  assert.deepEqual(validateHabits([meal({ frequency: "24" })], ["1000"]), { habits: [{ ...meal({ frequency: "24" }), price_cents: MAX_PRICE_CENTS }] });

  const error = (habits, prices) => validateHabits(habits, prices).error;
  assert.equal(error([], []), "Add at least one habit to forecast spending.");
  assert.equal(error(Array.from({ length: 51 }, () => meal()), Array(51).fill("1")), "A forecast can include at most 50 habits.");
  assert.equal(validateHabits(Array.from({ length: 50 }, () => meal()), Array(50).fill("1")).habits.length, 50);
  assert.equal(error([meal(), meal({ name: "" })], ["1", "1"]), "Habit 2: add a name.");
  assert.equal(error([meal(), meal({ name: "Boba", frequency: "25" })], ["1", "1"]), "Boba: the frequency can be at most 24 per day.");
  assert.equal(error([meal({ frequency: "²" })], ["1"]), "Lunch: use a frequency like 1, 2 or 1/2 (per day).");
  assert.equal(error([meal()], ["3.756"]), "Lunch: enter the price in dollars with up to two decimal places, like 3.75 or 0.");
  assert.equal(error([meal()], ["1000.01"]), "Lunch: the price can be at most $1,000.");
  assert.equal(error([meal({ eligible_accounts: [] })], ["1"]), "Lunch: choose at least one eligible account.");
});

// Wallet balances (Wallet panel) and warning amounts (Wallet & Alerts): same $100,000 cap as the API.
const BALANCES = { labels: { dining: "The Dining Dollars balance", cash: "The Triton Cash balance" }, example: "like 1250 or 1250.50" };
const WARNINGS = { labels: { dining: "The Dining Dollars warning amount", cash: "The Triton Cash warning amount" }, example: "like 100 or 75.50 (use 0 to turn a warning off)" };

test("wallet amounts: exactly $100,000, zero and ordinary values are accepted", () => {
  for (const form of [BALANCES, WARNINGS]) {
    assert.deepEqual(parseWalletAmounts("100000", "100000.00", form), { dining_dollars_cents: MAX_BALANCE_CENTS, triton_cash_cents: MAX_BALANCE_CENTS });
    assert.deepEqual(parseWalletAmounts("0", "0.00", form), { dining_dollars_cents: 0, triton_cash_cents: 0 });
    assert.deepEqual(parseWalletAmounts(" 1250.5 ", "75.05", form), { dining_dollars_cents: 125_050, triton_cash_cents: 7_505 });
  }
});

test("wallet amounts: just above $100,000 is refused in dollars, naming the field", () => {
  assert.deepEqual(parseWalletAmounts("100000.01", "1", BALANCES), { error: "The Dining Dollars balance can be at most $100,000." });
  assert.deepEqual(parseWalletAmounts("1", "100000.01", BALANCES), { error: "The Triton Cash balance can be at most $100,000." });
  assert.deepEqual(parseWalletAmounts("100001", "0", WARNINGS), { error: "The Dining Dollars warning amount can be at most $100,000." });
  assert.deepEqual(parseWalletAmounts("0", "100000.01", WARNINGS), { error: "The Triton Cash warning amount can be at most $100,000." });
  // Never the raw cents the API uses.
  assert.ok(!parseWalletAmounts("100000.01", "1", BALANCES).error.includes("10000001"));
});

test("wallet amounts: malformed decimals name the field and give the form's example", () => {
  for (const bad of ["", "abc", "-5", "1,250", "12.345", "1.2.3", "$12", "1e5", "Infinity", "١٠"]) {
    assert.deepEqual(parseWalletAmounts(bad, "1", BALANCES), { error: "The Dining Dollars balance: enter dollars with up to two decimal places, like 1250 or 1250.50." }, bad);
  }
  assert.deepEqual(parseWalletAmounts("0", "75.555", WARNINGS), { error: "The Triton Cash warning amount: enter dollars with up to two decimal places, like 100 or 75.50 (use 0 to turn a warning off)." });
});

test("wallet amounts: numbers too large to convert safely are over the limit, never sent", () => {
  const huge = "9".repeat(400);
  assert.equal(dollarsToCents(huge), null);
  assert.deepEqual(parseWalletAmounts(huge, "1", BALANCES), { error: "The Dining Dollars balance can be at most $100,000." });
  assert.deepEqual(parseWalletAmounts("1", "90071992547409.93", WARNINGS), { error: "The Triton Cash warning amount can be at most $100,000." });
});
