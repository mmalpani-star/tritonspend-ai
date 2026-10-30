// Run with `npm test` (Node's built-in runner; Node strips the TypeScript types).
import assert from "node:assert/strict";
import { test } from "node:test";
import { addDays, campusDate, daysBetween, formatCalendarDate, formatTimestamp, mondayOf, parseTimestamp } from "./datetime.ts";

test("date-only values keep their calendar day in any runtime time zone", () => {
  assert.equal(formatCalendarDate("2026-10-30"), "Oct 30, 2026");
  assert.equal(formatCalendarDate("2026-01-01"), "Jan 1, 2026");
  assert.equal(formatCalendarDate("2026-12-31", { month: "long", year: "numeric" }), "December 2026");
  assert.throws(() => formatCalendarDate("2026-10-30T07:00:00Z"));
});

test("calendar arithmetic ignores daylight-saving changes", () => {
  assert.equal(addDays("2026-11-01", 1), "2026-11-02");
  assert.equal(addDays("2026-03-08", 1), "2026-03-09");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2026-10-30", -1), "2026-10-29");
  assert.equal(daysBetween("2026-10-30", "2026-11-15"), 16);
  assert.equal(daysBetween("2026-03-07", "2026-03-09"), 2);
  // Week grouping for results: Friday Oct 30 and Sunday Nov 1 are in the week of Monday Oct 26.
  assert.equal(mondayOf("2026-10-30"), "2026-10-26");
  assert.equal(mondayOf("2026-11-01"), "2026-10-26");
  assert.equal(mondayOf("2026-11-02"), "2026-11-02");
});

test("a UTC timestamp is shown as San Diego time", () => {
  // 07:49 UTC on Oct 30 is 12:49 AM PDT, not 7:49 AM.
  assert.equal(formatTimestamp("2026-10-30T07:49:12Z"), "Oct 30, 2026, 12:49 AM PDT");
  assert.equal(formatTimestamp("2026-10-30T07:49:12+00:00"), "Oct 30, 2026, 12:49 AM PDT");
  assert.equal(formatTimestamp("2026-10-30T07:49:12Z", { year: false }), "Oct 30, 12:49 AM PDT");
});

test("timestamps without an offset are read as UTC, not browser-local time", () => {
  assert.equal(parseTimestamp("2026-10-30T07:49:12").toISOString(), "2026-10-30T07:49:12.000Z");
  assert.equal(formatTimestamp("2026-10-30T07:49:12.913229"), "Oct 30, 2026, 12:49 AM PDT");
});

test("daylight-saving transitions use the correct offset", () => {
  // Fall back: 2026-11-01 02:00 PDT -> 01:00 PST (09:00 UTC).
  assert.equal(formatTimestamp("2026-11-01T08:30:00Z"), "Nov 1, 2026, 1:30 AM PDT");
  assert.equal(formatTimestamp("2026-11-01T09:30:00Z"), "Nov 1, 2026, 1:30 AM PST");
  // Spring forward: 2026-03-08 02:00 PST -> 03:00 PDT (10:00 UTC).
  assert.equal(formatTimestamp("2026-03-08T09:59:00Z"), "Mar 8, 2026, 1:59 AM PST");
  assert.equal(formatTimestamp("2026-03-08T10:00:00Z"), "Mar 8, 2026, 3:00 AM PDT");
  assert.equal(formatTimestamp("2026-01-15T20:00:00Z"), "Jan 15, 2026, 12:00 PM PST");
});

test("the campus date follows San Diego midnight, not UTC midnight", () => {
  assert.equal(campusDate(new Date("2026-10-30T07:49:00Z")), "2026-10-30");
  assert.equal(campusDate(new Date("2026-10-31T06:59:00Z")), "2026-10-30");
  assert.equal(campusDate(new Date("2026-10-31T07:00:00Z")), "2026-10-31");
});
