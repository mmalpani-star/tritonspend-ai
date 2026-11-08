// Official menu links: destinations, labels, missing URLs and external-link safety.
import assert from "node:assert/strict";
import { test } from "node:test";
import { EXTERNAL_LINK, isHdhMenuPage, officialUrl, stationMenuLink, venueMenuLink, venueScopeNote } from "./menu-links.ts";
import { VENUES } from "./food-venues-data.ts";

const SIXTY_FOUR = "https://hdh-web.ucsd.edu/dining/apps/diningservices/Restaurants/Venue_V3?locId=2&locDetID=37&dayNum=0";
const MARKETS = "https://hdh-web.ucsd.edu/dining/apps/diningservices/Restaurants/Markets";

test("external links open in a new tab without access to TritonSpend or a referrer", () => {
  assert.deepEqual(EXTERNAL_LINK, { target: "_blank", rel: "noopener noreferrer" });
  assert.ok(EXTERNAL_LINK.rel.split(" ").includes("noopener"));
});

test("only real web URLs are used; missing or malformed ones give no link", () => {
  assert.equal(officialUrl(SIXTY_FOUR), SIXTY_FOUR); // kept exactly, query parameters included
  for (const bad of [null, undefined, "", "   ", "not a url", "javascript:alert(1)", "ftp://example.com/menu", "data:text/html,hi"]) {
    assert.equal(officialUrl(bad), null, String(bad));
  }
  assert.equal(isHdhMenuPage(SIXTY_FOUR), true);
  assert.equal(isHdhMenuPage(MARKETS), false);
  assert.equal(isHdhMenuPage("https://evil.example/dining/apps/diningservices/Restaurants/Venue_V3?locId=2"), false);
});

test("venue cards: HDH menu pages are 'Today's menu', other official pages are named for what they are", () => {
  assert.deepEqual(venueMenuLink({ name: "64 Degrees", operator: "hdh", menuUrl: SIXTY_FOUR }), {
    href: SIXTY_FOUR, label: "Today's menu", scope: "venue", description: "Open the official HDH menu for 64 Degrees in a new tab"
  });
  assert.equal(venueMenuLink({ name: "Sixth Market", operator: "hdh", menuUrl: MARKETS }).label, "HDH page");
  assert.equal(venueMenuLink({ name: "Some Cafe", operator: "triton_cash_partner", menuUrl: "https://cafe.example/menu" }).label, "Menu");
  assert.equal(venueMenuLink({ name: "No Menu", operator: "hdh", menuUrl: null }), null);
});

test("stations prefer their own official menu, else use the venue's and say so", () => {
  const own = stationMenuLink({ name: "Triton Grill", menu_url: "https://hdh-web.ucsd.edu/station-page" }, { name: "64 Degrees", menu_url: SIXTY_FOUR });
  assert.deepEqual([own.href, own.label, own.scope], ["https://hdh-web.ucsd.edu/station-page", "Station menu", "station"]);
  assert.equal(venueScopeNote(own, "64 Degrees", "Triton Grill"), null);

  const shared = stationMenuLink({ name: "Triton Grill", menu_url: null }, { name: "64 Degrees", menu_url: SIXTY_FOUR });
  assert.deepEqual([shared.href, shared.label, shared.scope], [SIXTY_FOUR, "64 Degrees menu", "venue"]);
  assert.match(shared.description, /official HDH menu for 64 Degrees, which covers all its stations including Triton Grill/);
  assert.match(venueScopeNote(shared, "64 Degrees", "Triton Grill"), /one official menu for 64 Degrees that covers all its stations, including Triton Grill/);

  const market = stationMenuLink({ name: "Sixth Market Coffeehouse", menu_url: "" }, { name: "Sixth Market", menu_url: MARKETS });
  assert.deepEqual([market.label, market.scope], ["Sixth Market on HDH", "venue"]);
  assert.match(venueScopeNote(market, "Sixth Market", "Sixth Market Coffeehouse"), /no official menu page for Sixth Market Coffeehouse/);

  assert.equal(stationMenuLink({ name: "X", menu_url: null }, { name: "Y", menu_url: null }), null); // no fake button
  assert.equal(stationMenuLink({ name: "X", menu_url: "nonsense" }, { name: "Y", menu_url: "  " }), null);
});

test("catalog: every venue with stations has a usable official link, taken verbatim from the data", () => {
  const withStations = VENUES.filter((venue) => venue.stations.length > 0);
  assert.ok(withStations.length >= 10);
  for (const venue of withStations) {
    for (const station of venue.stations) {
      const link = stationMenuLink({ name: station, menu_url: null }, { name: venue.name, menu_url: venue.links.menu });
      assert.ok(link, `${venue.name} / ${station}`);
      assert.equal(link.href, venue.links.menu); // never rewritten or guessed
      assert.equal(link.scope, "venue");
      assert.ok(link.href.startsWith("https://hdh-web.ucsd.edu/"), link.href);
    }
  }
});
