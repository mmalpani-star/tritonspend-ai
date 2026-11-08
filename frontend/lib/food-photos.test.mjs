// The food photo library: every asset is local and credited, and venues get fitting, varied photos.
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { test } from "node:test";
import { FOOD_CATEGORIES, FOOD_PHOTOS, foodCategories, photosFor } from "./food-photos.ts";
import { VENUES } from "./food-venues-data.ts";

test("library: every photo is a local file with alt text, a caption and a license credit", () => {
  const photos = Object.values(FOOD_PHOTOS);
  assert.ok(photos.length >= 40, `only ${photos.length} photos`);
  for (const photo of photos) {
    assert.match(photo.src, /^\/food\/[a-z0-9-]+\.jpg$/); // never an external hotlink
    assert.ok(existsSync(new URL(`../public${photo.src}`, import.meta.url)), `${photo.src} missing`);
    assert.ok(photo.alt.length > 15 && photo.caption && photo.width > 0 && photo.height > 0, photo.src);
    assert.ok(photo.credit.author && photo.credit.license && photo.credit.licenseUrl.startsWith("http"), photo.src);
    assert.match(photo.credit.source, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
    assert.match(photo.credit.license, /^(CC0|CC BY|Public domain)/);
    assert.doesNotMatch(`${photo.alt} ${photo.caption}`, /ucsd|uc san diego|triton|pines|64 degrees/i); // illustrative, never a venue's dish
  }
});

test("categories only reference real photos", () => {
  for (const [category, ids] of Object.entries(FOOD_CATEGORIES)) {
    assert.ok(ids.length >= 2, category);
    for (const id of ids) assert.ok(FOOD_PHOTOS[id], `${category}: ${id}`);
  }
});

test("venues get fitting dish families from their own words", () => {
  assert.equal(foodCategories(["Slice at Pines", "Personal pizzas"])[0], "pizza");
  assert.equal(foodCategories(["Taqueria", "breakfast burritos"])[0], "mexican");
  assert.ok(foodCategories(["Some Corner Store"], "market").includes("market"));
  assert.deepEqual(foodCategories(["Mystery"], "restaurant"), ["global", "healthy", "grill"]);
});

test("photos per venue are stable, distinct and varied across the catalog", () => {
  const first = photosFor("pines", ["pizza", "healthy"], 4);
  assert.deepEqual(photosFor("pines", ["pizza", "healthy"], 4), first); // stable
  assert.equal(new Set(first).size, first.length); // distinct
  assert.ok(FOOD_CATEGORIES.pizza.includes(first[0])); // leads with the best match
  const covers = VENUES.map((venue) => photosFor(venue.id, foodCategories([venue.name, venue.summary, venue.description, ...venue.tags, ...venue.stations], venue.kind))[0]);
  assert.ok(new Set(covers).size >= 18, `only ${new Set(covers).size} different cover photos across ${VENUES.length} venues`);
});

import { coverPhotos } from "./food-photos.ts";

test("directory covers: bagel places lead with bagels, and neighbours never repeat a photo", () => {
  assert.equal(foodCategories(["Big City Bagels (BCB) Café", "Espresso"])[0], "deli");
  const places = VENUES.map((venue) => ({ key: venue.id, categories: foodCategories([venue.name, venue.summary, venue.description, ...venue.tags, ...venue.stations], venue.kind) }));
  const covers = coverPhotos(places);
  const order = places.map((place) => covers[place.key]);
  for (let i = 0; i < order.length; i += 1) {
    const window = order.slice(Math.max(0, i - 5), i);
    assert.ok(!window.includes(order[i]), `${places[i].key} repeats ${order[i]} within 6 cards`);
  }
  assert.ok(new Set(order).size >= 25, `${new Set(order).size} distinct covers`);
});
