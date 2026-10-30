// Food Nearby stage 1: eligibility rules, catalog integrity, distance, hours, filtering, and explanations.
import assert from "node:assert/strict";
import { test } from "node:test";
import { CAMPUS_LANDMARKS } from "./campus-landmarks.ts";
import { VENUES } from "./food-venues-data.ts";
import {
  campusClock, describeOpenState, distanceTo, formatDistance, haversineMeters, idealDailyTargets,
  openState, visibleVenues, walletEligibility, whyReasons
} from "./food-venues.ts";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;
const byId = (id) => VENUES.find((venue) => venue.id === id);
const FRI = 5, SAT = 6, SUN = 0, MON = 1, TUE = 2;
const at = (day, h, m = 0) => ({ day, minutes: h * 60 + m });
const ALL = { query: "", category: "all", wallets: [], openNow: false };

test("wallet eligibility follows the official listings and never upgrades unknown to accepted", () => {
  assert.deepEqual(
    Object.fromEntries(Object.entries(walletEligibility({ operator: "hdh" })).map(([k, v]) => [k, v.status])),
    { dining_dollars: "accepted", triton_cash: "accepted" }
  );
  const partner = walletEligibility({ operator: "triton_cash_partner" });
  assert.equal(partner.triton_cash.status, "accepted");
  assert.equal(partner.dining_dollars.status, "not_accepted");
  assert.equal(partner.dining_dollars.source, "diningDollarsFaq");
  const unknown = walletEligibility({ operator: "somewhere_else" });
  assert.equal(unknown.dining_dollars.status, "not_verified");
  assert.equal(unknown.triton_cash.status, "not_verified");
});

test("catalog: every venue is officially listed, and unverifiable fields stay empty", () => {
  assert.equal(new Set(VENUES.map((v) => v.id)).size, VENUES.length);
  const hdh = VENUES.filter((v) => v.operator === "hdh");
  assert.equal(hdh.length, 16);
  for (const venue of VENUES) {
    assert.ok(venue.sources.includes(venue.operator === "hdh" ? "hdhMenus" : "tritonCashLocations"), venue.id);
    assert.equal(venue.coordinates !== null, venue.sources.includes("campusMap"), venue.id);
    assert.equal(venue.hours !== null, venue.operator === "hdh", venue.id); // only HDH publishes hours we use
    if (!venue.onCampus) assert.equal(venue.coordinates, null, venue.id);
    if (venue.coordinates) {
      // Sanity: every campus-map point is on or right next to campus.
      assert.ok(Math.abs(venue.coordinates.lat - 32.88) < 0.03 && Math.abs(venue.coordinates.lng + 117.24) < 0.03, venue.id);
    }
  }
  // No merchant is shown as accepting Dining Dollars.
  assert.ok(VENUES.filter((v) => v.operator !== "hdh").every((v) => walletEligibility(v).dining_dollars.status !== "accepted"));
  // Non-food Triton Cash locations are left out.
  for (const name of ["Imprints", "Triton Outfitters", "UCSD Bookstore", "The Trove"]) assert.equal(VENUES.some((v) => v.name === name), false);
});

test("straight-line distance is exact Haversine and never manufactured", () => {
  assert.equal(Math.round(haversineMeters({ lat: 0, lng: 0 }, { lat: 0, lng: 1 })), 111_195);
  const geisel = CAMPUS_LANDMARKS.find((l) => l.id === "geisel-library");
  const price = CAMPUS_LANDMARKS.find((l) => l.id === "price-center");
  // Small-distance check against an equirectangular estimate.
  const dy = (price.lat - geisel.lat) * 111_195;
  const dx = (price.lng - geisel.lng) * 111_195 * Math.cos((geisel.lat * Math.PI) / 180);
  assert.ok(Math.abs(haversineMeters(geisel, price) - Math.hypot(dx, dy)) < 0.5);
  assert.equal(haversineMeters(geisel, price), haversineMeters(price, geisel));
  assert.equal(distanceTo(byId("the-melt"), geisel), null); // off campus, no verified coordinates
  assert.equal(distanceTo(byId("pines"), null), null); // no location shared
  assert.equal(formatDistance(100), "330 ft");
  assert.equal(formatDistance(1609.344 * 0.42), "0.4 mi");
  assert.equal(formatDistance(1609.344 * 23.4), "23 mi");
});

test("campus clock reads Pacific time across daylight saving", () => {
  assert.deepEqual(campusClock(new Date(Date.UTC(2026, 9, 30, 19, 30))), { day: FRI, minutes: 12 * 60 + 30 }); // PDT
  assert.deepEqual(campusClock(new Date(Date.UTC(2026, 10, 2, 8, 0))), { day: MON, minutes: 0 }); // PST
});

test("opening status uses published hours, including closes after midnight", () => {
  const sixtyFour = byId("64-degrees").hours; // Fri 7 AM - 9 PM, Sat 9 AM - 9 PM
  assert.deepEqual(openState(sixtyFour, at(FRI, 20, 59)), { status: "open", closesAt: "9 PM", closesTomorrow: false });
  assert.deepEqual(openState(sixtyFour, at(FRI, 21)), { status: "closed", opensAt: "9 AM", opensDay: "tomorrow" });
  assert.deepEqual(openState(sixtyFour, at(FRI, 6, 30)), { status: "closed", opensAt: "7 AM", opensDay: "today" });

  const goodys = byId("goodys-marketplace").hours; // Mon 7 AM - 2 AM, Sun 9 AM - 2 AM
  assert.deepEqual(openState(goodys, at(MON, 23)), { status: "open", closesAt: "2 AM", closesTomorrow: true });
  assert.deepEqual(openState(goodys, at(TUE, 1, 30)), { status: "open", closesAt: "2 AM", closesTomorrow: false });
  assert.equal(openState(goodys, at(MON, 1)).status, "open"); // Sunday night's opening spills into Monday

  const lateSaturday = { sun: [], mon: [], tue: [], wed: [], thu: [], fri: [], sat: [["20:00", "02:00"]] };
  assert.equal(openState(lateSaturday, at(SUN, 1)).status, "open"); // wraps across the week boundary
  assert.equal(openState(lateSaturday, at(SUN, 3)).status, "closed");

  const bistro = byId("bistro").hours; // closed weekends
  assert.equal(describeOpenState(openState(bistro, at(SAT, 12))), "Closed · opens Monday 11 AM");
  assert.deepEqual(openState(null, at(FRI, 12)), { status: "unknown" });
  assert.equal(describeOpenState({ status: "unknown" }), "Hours not verified");
});

test("categories, wallet filters, search and open-now filter", () => {
  const noon = at(FRI, 12);
  assert.equal(visibleVenues(VENUES, { ...ALL, category: "campus-dining" }, noon, null).length, 16);
  assert.equal(visibleVenues(VENUES, { ...ALL, category: "triton-cash" }, noon, null).length, VENUES.length - 16);
  const dd = visibleVenues(VENUES, { ...ALL, wallets: ["dining_dollars"] }, noon, null);
  assert.ok(dd.length === 16 && dd.every((v) => v.venue.operator === "hdh"));
  assert.equal(visibleVenues(VENUES, { ...ALL, wallets: ["triton_cash"] }, noon, null).length, VENUES.length);
  assert.deepEqual(visibleVenues(VENUES, { ...ALL, query: "ramen" }, noon, null).map((v) => v.venue.id), ["showa-ramen"]);
  const sushi = visibleVenues(VENUES, { ...ALL, query: "SUSHI" }, noon, null).map((v) => v.venue.id);
  assert.ok(sushi.includes("64-degrees") && sushi.includes("bistro") && sushi.includes("del-sushi"));
  // Open now never includes venues without verified hours.
  const open = visibleVenues(VENUES, { ...ALL, openNow: true }, at(SAT, 12), null);
  assert.ok(open.length > 0 && open.every((v) => v.venue.hours && v.open.status === "open"));
  assert.ok(!open.some((v) => v.venue.id === "bistro"));
});

test("with a location, nearest venues come first and unknown distances go last", () => {
  const price = CAMPUS_LANDMARKS.find((l) => l.id === "price-center");
  const views = visibleVenues(VENUES, ALL, at(FRI, 12), price);
  const known = views.filter((v) => v.meters !== null);
  assert.equal(known.length, VENUES.filter((v) => v.coordinates).length);
  assert.ok(known.every((v, i) => i === 0 || known[i - 1].meters <= v.meters));
  assert.ok(views.slice(known.length).every((v) => v.meters === null));
  assert.equal(views[0].venue.campusArea, "Price Center");
});

test("'why this works' only states facts that exist", () => {
  const noon = at(FRI, 12);
  const melt = visibleVenues(VENUES, { ...ALL, query: "the melt" }, noon, null)[0];
  assert.deepEqual(whyReasons(melt, [], null, money).map((r) => r.text), [
    "Accepts Triton Cash.",
    "Budget fit unavailable — menu prices not yet verified."
  ]);
  const geisel = CAMPUS_LANDMARKS.find((l) => l.id === "geisel-library");
  const pines = visibleVenues(VENUES, { ...ALL, query: "pines" }, noon, geisel)[0];
  const texts = whyReasons(pines, ["triton_cash"], { dining_dollars: 1_840, triton_cash: 310 }, money).map((r) => r.text);
  assert.equal(texts[0], "Accepts Triton Cash."); // the student's chosen wallet first
  assert.equal(texts[1], "Accepts Dining Dollars.");
  assert.match(texts[2], /^0\.\d mi away \(straight line\)\.$/);
  assert.equal(texts[3], "Open until 9 PM.");
  assert.equal(texts[4], "Daily target: $18.40 Dining Dollars · $3.10 Triton Cash.");
  // A merchant only gets the target for the wallet it accepts.
  const melTexts = whyReasons(melt, [], { dining_dollars: 1_840, triton_cash: 310 }, money).map((r) => r.text);
  assert.ok(melTexts.includes("Daily target: $3.10 Triton Cash."));
});

test("daily target is the ideal line's slope for a current saved forecast only", () => {
  const prediction = {
    comparison: { id: "f1", start_date: "2026-10-30", end_date: "2026-12-08" },
    horizon: { end_date: "2026-12-08", rule: "selected_forecast_end", days: 40 },
    accounts: [
      { account: "dining_dollars", latest_cents: 420_000, target_cents: 20_000, ideal_available: true },
      { account: "triton_cash", latest_cents: 1_000, target_cents: 5_000, ideal_available: false }
    ]
  };
  assert.deepEqual(idealDailyTargets(prediction, "2026-10-30"), { dining_dollars: 10_000 });
  assert.equal(idealDailyTargets(prediction, "2026-12-09"), null); // forecast already ended
  assert.equal(idealDailyTargets({ ...prediction, comparison: null }, "2026-10-30"), null);
  assert.equal(idealDailyTargets({ ...prediction, horizon: { ...prediction.horizon, rule: "default" } }, "2026-10-30"), null);
});
