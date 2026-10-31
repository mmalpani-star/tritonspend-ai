/**
 * Forecast input limits and checks for early, specific form feedback. They mirror
 * backend/app/schemas.py (see README "API input limits"); the backend stays authoritative.
 * No runtime imports so Node's test runner can load this file directly.
 */
import type { HabitInput } from "./types";

export const MAX_FORECAST_DAYS = 366;
export const MAX_HABITS = 50;
export const MAX_FREQUENCY_LENGTH = 9;
export const MAX_FREQUENCY_DENOMINATOR = 365;
export const MAX_FREQUENCY_PER_DAY = 24;
export const MAX_BALANCE_CENTS = 10_000_000;
export const MAX_PRICE_CENTS = 100_000;

const dollars = (cents: number) => `$${(cents / 100).toLocaleString("en-US")}`;

/** "12.5" -> 1250. Null for anything but plain dollars with up to two decimals, or unsafe sizes. */
export function dollarsToCents(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(trimmed)) return null;
  const [whole, fraction = ""] = trimmed.split(".");
  const cents = Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
  return Number.isSafeInteger(cents) ? cents : null;
}

/** Why a per-day frequency ("n" or "n/d", ASCII digits) is invalid, or null. Same rules as the API. */
export function frequencyError(value: string): string | null {
  if (value.length > MAX_FREQUENCY_LENGTH) return `the frequency can be at most ${MAX_FREQUENCY_LENGTH} characters`;
  // [0-9], not \d: the API rejects non-ASCII digits.
  const match = /^([0-9]+)(?:\/([0-9]+))?$/.exec(value);
  if (!match) return "use a frequency like 1, 2 or 1/2 (per day)";
  const denominator = match[2] === undefined ? 1 : Number(match[2]);
  if (denominator < 1 || denominator > MAX_FREQUENCY_DENOMINATOR) return `the frequency's denominator must be between 1 and ${MAX_FREQUENCY_DENOMINATOR}`;
  if (Number(match[1]) > MAX_FREQUENCY_PER_DAY * denominator) return `the frequency can be at most ${MAX_FREQUENCY_PER_DAY} per day`;
  return null;
}

/** Inclusive calendar days from start to end (YYYY-MM-DD), independent of the device time zone. */
export function inclusiveDays(start: string, end: string): number {
  const utc = (value: string) => {
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(0);
    date.setUTCFullYear(year, month - 1, day); // Date.UTC would map years 0-99 to 1900-1999
    return date.getTime();
  };
  return Math.round((utc(end) - utc(start)) / 86_400_000) + 1;
}

/** Period checks for a forecast whose start date the student chose. */
export function dateRangeError(start: string, end: string): string | null {
  if (start > end) return "The start date must be on or before the end date.";
  if (inclusiveDays(start, end) > MAX_FORECAST_DAYS) return `A forecast can cover at most ${MAX_FORECAST_DAYS} days.`;
  return null;
}

/** A manually entered balance in cents, already parsed. */
export function balanceError(label: string, cents: number): string | null {
  return cents > MAX_BALANCE_CENTS ? `${label} can be at most ${dollars(MAX_BALANCE_CENTS)}.` : null;
}

export type WalletAmountsInput = {
  /** Field names used in messages, e.g. "The Dining Dollars balance". */
  labels: { dining: string; cash: string };
  /** Shown for malformed input, e.g. "like 1250 or 1250.50". */
  example: string;
};

/**
 * Both wallet amounts (balances or warning amounts) in cents, or the first problem naming its field.
 * Same rules as the API: dollars with up to two decimals, $0 to $100,000 per wallet.
 */
export function parseWalletAmounts(dining: string, cash: string, { labels, example }: WalletAmountsInput):
  { dining_dollars_cents: number; triton_cash_cents: number } | { error: string } {
  const parse = (value: string, label: string): number | string => {
    const cents = dollarsToCents(value);
    if (cents === null) {
      // Well-formed but too large to convert safely is still just "over the limit" to the student.
      const wellFormed = /^\d+(?:\.\d{1,2})?$/.test(value.trim());
      return wellFormed ? `${label} can be at most ${dollars(MAX_BALANCE_CENTS)}.` : `${label}: enter dollars with up to two decimal places, ${example}.`;
    }
    return balanceError(label, cents) ?? cents;
  };
  const diningCents = parse(dining, labels.dining);
  if (typeof diningCents === "string") return { error: diningCents };
  const cashCents = parse(cash, labels.cash);
  if (typeof cashCents === "string") return { error: cashCents };
  return { dining_dollars_cents: diningCents, triton_cash_cents: cashCents };
}

type HabitDraft = Pick<HabitInput, "name" | "frequency" | "eligible_accounts">;

/**
 * The habits as API input, or the first problem, naming the habit ("Breakfast: …" or "Habit 2: …").
 * `prices` are the typed dollar strings, kept as text until submit.
 */
export function validateHabits(habits: HabitDraft[], prices: string[]): { habits: HabitInput[] } | { error: string } {
  if (habits.length === 0) return { error: "Add at least one habit to forecast spending." };
  if (habits.length > MAX_HABITS) return { error: `A forecast can include at most ${MAX_HABITS} habits.` };
  const result: HabitInput[] = [];
  for (const [index, habit] of habits.entries()) {
    const label = habit.name.trim() || `Habit ${index + 1}`;
    if (!habit.name.trim()) return { error: `${label}: add a name.` };
    const frequency = frequencyError(habit.frequency);
    if (frequency) return { error: `${label}: ${frequency}.` };
    const cents = dollarsToCents(prices[index] ?? "");
    if (cents === null) return { error: `${label}: enter the price in dollars with up to two decimal places, like 3.75 or 0.` };
    if (cents > MAX_PRICE_CENTS) return { error: `${label}: the price can be at most ${dollars(MAX_PRICE_CENTS)}.` };
    if (habit.eligible_accounts.length === 0) return { error: `${label}: choose at least one eligible account.` };
    result.push({ ...habit, price_cents: cents });
  }
  return { habits: result };
}
