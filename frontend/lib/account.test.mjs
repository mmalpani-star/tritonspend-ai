// The student's own area: sidebar sections, page routes, favourites and activity labels.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  PAGE_TITLES, SIDEBAR_SECTIONS, YOU_PAGES, countLabel, favoriteButtonLabel, isFavorite,
  parseYouPage, withoutFavorite, youPageHash
} from "./account.ts";

test("sidebar: the four sections, in order, with every page and Sign Out", () => {
  assert.deepEqual(SIDEBAR_SECTIONS.map((section) => section.title), ["Your account", "Your food", "Your activity", "Settings"]);
  assert.deepEqual(SIDEBAR_SECTIONS.flatMap((section) => section.items.map((item) => item.label)), [
    "Your Account", "Favourite Dishes", "Favourite Venues", "Your Ratings", "Your Messages", "Settings", "Sign Out"
  ]);
  const pages = SIDEBAR_SECTIONS.flatMap((section) => section.items).filter((item) => item.kind === "page").map((item) => item.page);
  assert.deepEqual([...pages].sort(), [...YOU_PAGES].sort()); // every page is reachable from the sidebar
  assert.equal(SIDEBAR_SECTIONS.at(-1).items.at(-1).kind, "sign-out");
  for (const page of YOU_PAGES) assert.ok(PAGE_TITLES[page]);
});

test("routes: each page has its own address, and unknown ones fall back to Your Account", () => {
  for (const page of YOU_PAGES) assert.equal(parseYouPage(youPageHash(page)), page);
  assert.equal(youPageHash("favourite-venues"), "#you/favourite-venues");
  assert.equal(parseYouPage("#you"), "account");
  assert.equal(parseYouPage("#you/nope"), "account");
  assert.equal(parseYouPage("#you/reviews"), "ratings"); // older links still land on the right page
  assert.equal(parseYouPage("#you/discussions"), "messages");
  for (const hash of ["", "#food-nearby", "#wallet", "#your/settings"]) assert.equal(parseYouPage(hash), null, hash);
});

const favourites = {
  venues: [{ id: "pines", name: "Pines" }, { id: "64-degrees", name: "64 Degrees" }],
  dishes: [{ id: "d1", name: "Chicken Rice Bowl" }]
};

test("favourites: saved state and removal", () => {
  assert.equal(isFavorite(favourites, "venue", "pines"), true);
  assert.equal(isFavorite(favourites, "venue", "d1"), false); // kinds are separate
  assert.equal(isFavorite(favourites, "dish", "d1"), true);
  assert.equal(isFavorite(null, "venue", "pines"), false); // not loaded yet
  const removed = withoutFavorite(favourites, "venue", "pines");
  assert.deepEqual(removed.venues.map((venue) => venue.id), ["64-degrees"]);
  assert.equal(removed.dishes, favourites.dishes);
  assert.deepEqual(withoutFavorite(favourites, "dish", "d1").dishes, []);
  assert.deepEqual(favourites.venues.length, 2); // the original is unchanged
  assert.equal(favoriteButtonLabel(false, "Pines"), "Save Pines to favourites");
  assert.equal(favoriteButtonLabel(true, "Pines"), "Remove Pines from favourites");
});

test("activity: counts read naturally", () => {
  assert.equal(countLabel(1, "rating"), "1 rating");
  assert.equal(countLabel(3, "message"), "3 messages");
  assert.equal(countLabel(2, "reply", "replies"), "2 replies");
});
