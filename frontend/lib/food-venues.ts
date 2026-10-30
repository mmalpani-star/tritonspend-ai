/**
 * Food Nearby, stage 1: venue types, sources, and the rules that turn the curated catalog
 * (food-venues-data.ts) into what a student sees. No runtime imports so Node's test runner can load it.
 *
 * - Wallet eligibility is derived from where a venue is officially listed, never stored per venue.
 *   Unknown stays "not_verified"; it is never shown as accepted.
 * - Opening status comes only from published weekly hours; venues without them are "unknown".
 * - Distance is straight-line (Haversine) from coordinates computed on the device. Travel modes
 *   (walking, e-scooter, bus) are a later stage and need a routing-data decision.
 */
import type { Account } from "./types";

export type DayKey = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
/** [open, close] as "HH:MM" in campus time. A close at or before the open time runs past midnight. */
export type WeeklyHours = Record<DayKey, [string, string][]>;
export type SourceKey = keyof typeof VENUE_SOURCES;

export type Venue = {
  id: string;
  name: string;
  /** Where the venue is officially listed; this alone decides wallet eligibility. */
  operator: "hdh" | "triton_cash_partner";
  kind: "restaurant" | "market" | "merchant";
  /** Short paraphrase of the official description, or the campus map's keywords. */
  summary: string | null;
  description: string | null;
  stations: string[];
  tags: string[];
  /** Area named by an official source (e.g. the Triton Cash list's headings). */
  campusArea: string | null;
  /** Building named by the official campus map. */
  location: string | null;
  onCampus: boolean;
  coordinates: { lat: number; lng: number; layer: string; feature: string; building: string | null } | null;
  hours: WeeklyHours | null;
  links: { menu?: string; website?: string };
  sources: SourceKey[];
  notes: string[];
};

export const VENUE_SOURCES = {
  hdhMenus: { label: "HDH Menus & Hours", url: "https://hdh-web.ucsd.edu/dining/apps/diningservices" },
  hdhRestaurants: { label: "HDH Restaurants", url: "https://hdh-web.ucsd.edu/dining/apps/diningservices/Restaurants/Restaurants" },
  hdhMarkets: { label: "HDH Markets", url: "https://hdh-web.ucsd.edu/dining/apps/diningservices/Restaurants/Markets" },
  tritonCashLocations: { label: "Triton Cash participating locations", url: "https://hdhtcas.ucsd.edu/accounts/triton-cash/discounts.html" },
  tritonCashOverview: { label: "Triton Cash overview", url: "https://hdhtcas.ucsd.edu/accounts/triton-cash/index.html" },
  diningDollarsFaq: { label: "Dining Dollars FAQ", url: "https://hdhdining.ucsd.edu/dining-plans/dining-dollars-faq.html" },
  campusMap: { label: "UC San Diego campus map", url: "https://maps.ucsd.edu/map/default.htm" }
} as const;

// ---------------------------------------------------------------------------------------------
// Wallet eligibility

export type EligibilityStatus = "accepted" | "not_accepted" | "not_verified";
export type Eligibility = { status: EligibilityStatus; reason: string; source: SourceKey | null };

export const WALLET_LABELS: Record<Account, string> = { dining_dollars: "Dining Dollars", triton_cash: "Triton Cash" };

/**
 * - Dining Dollars: only HDH residential dining and market locations (Dining Dollars FAQ).
 * - Triton Cash: HDH Dining Services locations plus the participating third-party locations on the
 *   official list (which may not be exhaustive).
 * Anything else is "not_verified".
 */
export function walletEligibility(venue: Pick<Venue, "operator">): Record<Account, Eligibility> {
  if (venue.operator === "hdh") {
    return {
      dining_dollars: { status: "accepted", reason: "HDH dining and market locations accept Dining Dollars.", source: "diningDollarsFaq" },
      triton_cash: { status: "accepted", reason: "Triton Cash is accepted at HDH Dining Services locations.", source: "tritonCashLocations" }
    };
  }
  if (venue.operator === "triton_cash_partner") {
    return {
      dining_dollars: { status: "not_accepted", reason: "Dining Dollars are only for HDH dining and market locations.", source: "diningDollarsFaq" },
      triton_cash: { status: "accepted", reason: "Listed as a participating Triton Cash location.", source: "tritonCashLocations" }
    };
  }
  const unknown: Eligibility = { status: "not_verified", reason: "Not on an official list we could check.", source: null };
  return { dining_dollars: unknown, triton_cash: unknown };
}

// ---------------------------------------------------------------------------------------------
// Opening hours (campus time)

export const DAY_KEYS: DayKey[] = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const WEEKDAY_INDEX: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

/** Day of week (0 = Sunday) and minutes after midnight in America/Los_Angeles. */
export function campusClock(now: Date): { day: number; minutes: number } {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return { day: WEEKDAY_INDEX[get("weekday")], minutes: Number(get("hour")) * 60 + Number(get("minute")) };
}

const toMinutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5));

/** Every opening as absolute minutes from the start of this week's Sunday; overnight closes spill into the next day. */
function weekIntervals(hours: WeeklyHours): [number, number][] {
  const result: [number, number][] = [];
  DAY_KEYS.forEach((key, day) => {
    for (const [open, close] of hours[key]) {
      const start = day * 1440 + toMinutes(open);
      let end = day * 1440 + toMinutes(close);
      if (end <= start) end += 1440;
      result.push([start, end]);
    }
  });
  return result;
}

export type OpenState =
  | { status: "unknown" }
  | { status: "open"; closesAt: string; closesTomorrow: boolean }
  | { status: "closed"; opensAt: string; opensDay: "today" | "tomorrow" | DayKey }
  | { status: "closed_all_week" };

/** Open/closed from published weekly hours; "unknown" without them. */
export function openState(hours: WeeklyHours | null, clock: { day: number; minutes: number }): OpenState {
  if (!hours) return { status: "unknown" };
  const week = 7 * 1440;
  const now = clock.day * 1440 + clock.minutes;
  const intervals = weekIntervals(hours);
  if (intervals.length === 0) return { status: "closed_all_week" };
  // Last week's Saturday-night opening can still be running early on Sunday.
  for (const [start, end] of intervals.flatMap(([s, e]) => [[s, e], [s - week, e - week]])) {
    if (start <= now && now < end) {
      const close = ((end % 1440) + 1440) % 1440;
      return { status: "open", closesAt: clockLabel(close), closesTomorrow: Math.floor(end / 1440) !== Math.floor(now / 1440) };
    }
  }
  const next = intervals.map(([start]) => (start > now ? start : start + week)).sort((a, b) => a - b)[0];
  const dayOffset = Math.floor(next / 1440) - clock.day;
  const opensDay = dayOffset === 0 ? "today" : dayOffset === 1 ? "tomorrow" : DAY_KEYS[Math.floor(next / 1440) % 7];
  return { status: "closed", opensAt: clockLabel(next % 1440), opensDay };
}

/** 1260 -> "9 PM", 450 -> "7:30 AM", 0 -> "12 AM". */
export function clockLabel(minutes: number): string {
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;
  const suffix = hour < 12 ? "AM" : "PM";
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return minute === 0 ? `${display} ${suffix}` : `${display}:${String(minute).padStart(2, "0")} ${suffix}`;
}

const DAY_NAMES: Record<DayKey, string> = { sun: "Sunday", mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday" };

export function describeOpenState(state: OpenState): string {
  switch (state.status) {
    case "open": return `Open until ${state.closesAt}`;
    case "closed": return `Closed · opens ${state.opensDay === "today" ? "" : state.opensDay === "tomorrow" ? "tomorrow " : `${DAY_NAMES[state.opensDay]} `}${state.opensAt}`;
    case "closed_all_week": return "No published opening hours this week";
    default: return "Hours not verified";
  }
}

export function formatHours(intervals: [string, string][]): string {
  if (intervals.length === 0) return "Closed";
  return intervals.map(([open, close]) => `${clockLabel(toMinutes(open))} – ${clockLabel(toMinutes(close))}`).join(", ");
}

// ---------------------------------------------------------------------------------------------
// Distance (straight line)

export type LatLng = { lat: number; lng: number };
const EARTH_RADIUS_M = 6_371_008.8;
const METERS_PER_MILE = 1609.344;

/** Great-circle distance in meters (Haversine). */
export function haversineMeters(a: LatLng, b: LatLng): number {
  const rad = (degrees: number) => (degrees * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** "450 ft" under a tenth of a mile, otherwise "0.4 mi" / "12 mi". */
export function formatDistance(meters: number): string {
  const miles = meters / METERS_PER_MILE;
  if (miles < 0.1) return `${Math.max(10, Math.round(meters * 3.28084 / 10) * 10)} ft`;
  return miles < 10 ? `${miles.toFixed(1)} mi` : `${Math.round(miles)} mi`;
}

/** Null when either end is unknown: a distance is never manufactured. */
export function distanceTo(venue: Pick<Venue, "coordinates">, origin: LatLng | null): number | null {
  return origin && venue.coordinates ? haversineMeters(origin, venue.coordinates) : null;
}

// ---------------------------------------------------------------------------------------------
// Search, filters, ordering

export type VenueCategory = "all" | "campus-dining" | "triton-cash";
export type VenueFilters = { query: string; category: VenueCategory; wallets: Account[]; openNow: boolean };

export function matchesQuery(venue: Venue, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = [venue.name, venue.summary, venue.description, venue.campusArea, venue.location, ...venue.stations, ...venue.tags]
    .filter(Boolean).join(" ").toLowerCase();
  return words.every((word) => haystack.includes(word));
}

export type VenueView = { venue: Venue; wallets: Record<Account, Eligibility>; open: OpenState; meters: number | null };

/** Filtered venues with derived facts. Nearest first when a location is set (unknown distances last), otherwise open first, then A–Z. */
export function visibleVenues(venues: Venue[], filters: VenueFilters, clock: { day: number; minutes: number }, origin: LatLng | null): VenueView[] {
  const views = venues
    .filter((venue) => filters.category === "all" || (filters.category === "campus-dining" ? venue.operator === "hdh" : venue.operator === "triton_cash_partner"))
    .filter((venue) => matchesQuery(venue, filters.query))
    .map((venue) => ({ venue, wallets: walletEligibility(venue), open: openState(venue.hours, clock), meters: distanceTo(venue, origin) }))
    .filter((view) => filters.wallets.every((wallet) => view.wallets[wallet].status === "accepted"))
    .filter((view) => !filters.openNow || view.open.status === "open");
  const rank = (view: VenueView) => (view.open.status === "open" ? 0 : view.open.status === "unknown" ? 1 : 2);
  return views.sort((a, b) => {
    if (origin) {
      if (a.meters !== null && b.meters !== null && a.meters !== b.meters) return a.meters - b.meters;
      if ((a.meters === null) !== (b.meters === null)) return a.meters === null ? 1 : -1;
    }
    return rank(a) - rank(b) || a.venue.name.localeCompare(b.venue.name);
  });
}

// ---------------------------------------------------------------------------------------------
// "Why this works for you": only facts we actually have.

export type DailyTargets = Partial<Record<Account, number>>;
export type WhyReason = { kind: "wallet" | "distance" | "hours" | "budget"; text: string; tone: "good" | "neutral" | "caution" };

export function whyReasons(view: VenueView, preferred: Account[], targets: DailyTargets | null, formatMoney: (cents: number) => string): WhyReason[] {
  const reasons: WhyReason[] = [];
  const accepted = (Object.keys(view.wallets) as Account[]).filter((wallet) => view.wallets[wallet].status === "accepted");
  const order = [...preferred, ...accepted.filter((wallet) => !preferred.includes(wallet))];
  for (const wallet of order) {
    if (view.wallets[wallet].status === "accepted") reasons.push({ kind: "wallet", text: `Accepts ${WALLET_LABELS[wallet]}.`, tone: "good" });
  }
  if (view.meters !== null) reasons.push({ kind: "distance", text: `${formatDistance(view.meters)} away (straight line).`, tone: "good" });
  if (view.open.status === "open") reasons.push({ kind: "hours", text: `Open until ${view.open.closesAt}.`, tone: "good" });
  if (view.open.status === "closed" || view.open.status === "closed_all_week") reasons.push({ kind: "hours", text: `${describeOpenState(view.open)}.`, tone: "caution" });
  const usable = accepted.filter((wallet) => targets?.[wallet] !== undefined);
  if (usable.length > 0) {
    const text = usable.map((wallet) => `${formatMoney(targets![wallet]!)} ${WALLET_LABELS[wallet]}`).join(" · ");
    reasons.push({ kind: "budget", text: `Daily target: ${text}.`, tone: "neutral" });
  }
  reasons.push({ kind: "budget", text: "Budget fit unavailable — menu prices not yet verified.", tone: "neutral" });
  return reasons;
}

// ---------------------------------------------------------------------------------------------
// Daily budget context from the existing prediction's ideal line (no new spending model).

type IdealSource = {
  horizon: { end_date: string; rule: string; days: number } | null;
  comparison: { id: string; start_date: string; end_date: string } | null;
  accounts: { account: Account; latest_cents: number | null; target_cents: number; ideal_available: boolean }[];
};

/**
 * The ideal line's even daily step: (latest balance - saved target) / days to the selected forecast's end.
 * Only for a selected saved forecast that has not ended; otherwise there is no appropriate target.
 */
export function idealDailyTargets(prediction: IdealSource, today: string): DailyTargets | null {
  if (!prediction.comparison || !prediction.horizon || prediction.horizon.rule !== "selected_forecast_end") return null;
  if (prediction.comparison.end_date < today || prediction.horizon.days <= 0) return null;
  const targets: DailyTargets = {};
  for (const item of prediction.accounts) {
    if (!item.ideal_available || item.latest_cents === null) continue;
    targets[item.account] = Math.floor((item.latest_cents - item.target_cents) / prediction.horizon.days);
  }
  return Object.keys(targets).length > 0 ? targets : null;
}
