/**
 * All user-facing dates and times go through these helpers.
 *
 * - Date-only values ("2026-10-30") are calendar days. They are never converted
 *   through a time zone, so they cannot shift to the previous or next day.
 * - Timestamps from the API are UTC instants and are shown in campus time,
 *   America/Los_Angeles, with daylight saving applied by Intl (no fixed offsets).
 */
export const CAMPUS_TIME_ZONE = "America/Los_Angeles";

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const HAS_OFFSET = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;

function calendarDay(isoDate: string): Date {
  const match = DATE_ONLY.exec(isoDate);
  if (!match) throw new Error(`Not a calendar date: ${isoDate}`);
  // Noon UTC, formatted in UTC: the same calendar day everywhere.
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12));
}

/** "Oct 30, 2026" (or custom fields) for a date-only value. */
export function formatCalendarDate(
  isoDate: string,
  fields: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" }
): string {
  return new Intl.DateTimeFormat("en-US", { ...fields, timeZone: "UTC" }).format(calendarDay(isoDate));
}

/** Calendar arithmetic on date-only values. */
export function addDays(isoDate: string, days: number): string {
  const value = calendarDay(isoDate);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

/** The Monday on or before a date-only value. */
export function mondayOf(isoDate: string): string {
  const weekday = calendarDay(isoDate).getUTCDay();
  return addDays(isoDate, -(weekday === 0 ? 6 : weekday - 1));
}

/** Parses an API timestamp. Values without an offset are treated as UTC, never as browser-local time. */
export function parseTimestamp(value: string): Date {
  return new Date(HAS_OFFSET.test(value) ? value : `${value}Z`);
}

/** "Oct 30, 2026, 12:49 AM PDT" in campus time. */
export function formatTimestamp(value: string, { year = true }: { year?: boolean } = {}): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    ...(year ? { year: "numeric" } : {}),
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
    timeZone: CAMPUS_TIME_ZONE
  }).format(parseTimestamp(value));
}

/** The campus calendar date (YYYY-MM-DD) of an instant; defaults to now. */
export function campusDate(instant: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: CAMPUS_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(instant);
}

/** Today in campus time, the date the server checks against. */
export function campusToday(): string {
  return campusDate();
}

/** Whole calendar days from one date-only value to another. */
export function daysBetween(fromIsoDate: string, toIsoDate: string): number {
  return Math.round((calendarDay(toIsoDate).getTime() - calendarDay(fromIsoDate).getTime()) / 86_400_000);
}
