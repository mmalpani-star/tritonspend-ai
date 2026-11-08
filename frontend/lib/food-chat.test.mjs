// Food Chat screen logic: navigation routes, threads, votes, ratings, input checks and errors.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  MAX_COMMENT_LENGTH, MAX_REVIEW_LENGTH, applyVoteResult, breakdownRows, buildThread, commentError, foodErrorMessage,
  foodRouteHash, formatAverage, nextVote, parseFoodRoute, reviewCountLabel, reviewDraftError, reviewPlace
} from "./food-chat.ts";

test("navigation: Food Nearby -> venue -> station -> dish, and back from the URL", () => {
  const routes = [
    [{ page: "list" }, "#food-nearby"],
    [{ page: "venue", venueId: "64-degrees" }, "#food-nearby/venue/64-degrees"],
    [{ page: "station", stationId: "pines--slice-at-pines" }, "#food-nearby/station/pines--slice-at-pines"],
    [{ page: "dish", itemId: "3f1c" }, "#food-nearby/dish/3f1c"],
    [{ page: "moderation" }, "#food-nearby/moderation"]
  ];
  for (const [route, hash] of routes) {
    assert.equal(foodRouteHash(route), hash);
    assert.deepEqual(parseFoodRoute(hash), route);
  }
  assert.deepEqual(parseFoodRoute("#food-nearby/venue/canyon-vista-marketplace"), { page: "venue", venueId: "canyon-vista-marketplace" });
  // Unknown or incomplete addresses fall back to the directory instead of breaking.
  for (const hash of ["", "#wallet", "#food-nearby/venue", "#food-nearby/nope/x", "#food-nearby/venue/%E0%A4%A"]) {
    assert.deepEqual(parseFoodRoute(hash), { page: "list" }, hash);
  }
  assert.equal(parseFoodRoute(foodRouteHash({ page: "venue", venueId: "a b/c" })).venueId, "a b/c"); // safely encoded
});

const comment = (id, parent_id = null, extra = {}) => ({
  id, parent_id, is_placeholder: false, body: id, author_name: "Sunny Otter 1234", is_mine: false,
  score: 0, upvotes: 0, downvotes: 0, my_vote: 0, edited: false, created_at: "2026-11-07T20:00:00Z", ...extra
});

test("threads: nested replies keep the server's sibling order and depth", () => {
  const tree = buildThread([comment("a"), comment("b"), comment("a1", "a"), comment("a1x", "a1"), comment("a2", "a"), comment("b1", "b")]);
  const shape = (nodes) => nodes.map((node) => [node.id, node.depth, shape(node.children)]);
  assert.deepEqual(shape(tree), [
    ["a", 0, [["a1", 1, [["a1x", 2, []]]], ["a2", 1, []]]],
    ["b", 0, [["b1", 1, []]]]
  ]);
});

test("threads: a placeholder keeps its replies; a missing parent never hides a reply", () => {
  const tree = buildThread([comment("gone", null, { is_placeholder: true, body: null, author_name: null }), comment("kept", "gone"), comment("orphan", "not-loaded")]);
  assert.deepEqual(tree.map((node) => node.id), ["gone", "orphan"]);
  assert.equal(tree[0].children[0].id, "kept");
  assert.equal(tree[1].depth, 0);
  assert.deepEqual(buildThread([]), []);
});

test("votes: clicking toggles, switching changes direction, and the score comes from the server", () => {
  assert.equal(nextVote(0, 1), 1);
  assert.equal(nextVote(1, 1), 0); // clicking your upvote again removes it
  assert.equal(nextVote(1, -1), -1);
  assert.equal(nextVote(-1, -1), 0);
  const updated = applyVoteResult(comment("c", null, { score: 2, upvotes: 2 }), { comment_id: "c", score: 0, upvotes: 1, downvotes: 1, my_vote: -1 });
  assert.deepEqual([updated.score, updated.upvotes, updated.downvotes, updated.my_vote, updated.body], [0, 1, 1, -1, "c"]);
});

test("ratings: averages, counts and the star breakdown", () => {
  assert.equal(formatAverage({ review_count: 0, average_rating: null }), "No reviews yet"); // never 0/5
  assert.equal(formatAverage({ review_count: 2, average_rating: 4.5 }), "4.5");
  assert.equal(formatAverage({ review_count: 3, average_rating: 4 }), "4.0");
  assert.equal(reviewCountLabel(1), "1 review");
  assert.equal(reviewCountLabel(12), "12 reviews");
  const rows = breakdownRows({ review_count: 4, average_rating: 3.75, breakdown: { 1: 0, 2: 1, 3: 0, 4: 1, 5: 2 } });
  assert.deepEqual(rows, [
    { stars: 5, count: 2, percent: 50 }, { stars: 4, count: 1, percent: 25 }, { stars: 3, count: 0, percent: 0 },
    { stars: 2, count: 1, percent: 25 }, { stars: 1, count: 0, percent: 0 }
  ]);
  assert.ok(breakdownRows({ review_count: 0, average_rating: null, breakdown: {} }).every((row) => row.percent === 0 && row.count === 0));
});

test("review composer: only a venue, stars and text; any dish can be mentioned freely", () => {
  const draft = { venueId: "pines", rating: 4, body: "I tried the Slice at Pines pepperoni pizza. The crust was great, but it was a little overpriced." };
  assert.equal(reviewDraftError(draft), null); // no station or dish to choose
  assert.equal(reviewDraftError({ ...draft, venueId: "" }), "Choose the venue you're reviewing.");
  assert.equal(reviewDraftError({ ...draft, rating: 0 }), "Choose a rating from 1 to 5 stars.");
  assert.equal(reviewDraftError({ ...draft, rating: 6 }), "Choose a rating from 1 to 5 stars.");
  assert.equal(reviewDraftError({ ...draft, body: "   " }), "Write a few words about your experience.");
  assert.equal(reviewDraftError({ ...draft, body: "x".repeat(MAX_REVIEW_LENGTH) }), null);
  assert.match(reviewDraftError({ ...draft, body: "x".repeat(MAX_REVIEW_LENGTH + 1) }), /at most 2000/);
});

test("review feed: every review shows its venue; older dish reviews still render with their dish", () => {
  const pines = { id: "pines", name: "Pines" };
  assert.deepEqual(reviewPlace({ venue: pines, station: null, menu_item: null }), { venue: pines, about: null });
  const old = { venue: { id: "64-degrees", name: "64 Degrees" }, station: { id: "s", name: "Triton Grill" }, menu_item: { id: "d", name: "Chicken Rice Bowl" } };
  assert.deepEqual(reviewPlace(old), { venue: old.venue, about: "Chicken Rice Bowl · Triton Grill" });
  assert.equal(reviewPlace({ ...old, station: null }).about, "Chicken Rice Bowl");
});

test("comments and replies: required text within the limit", () => {
  assert.equal(commentError("Agreed!"), null);
  assert.equal(commentError("  \n "), "Write something first.");
  assert.equal(commentError("x".repeat(MAX_COMMENT_LENGTH)), null);
  assert.match(commentError("x".repeat(MAX_COMMENT_LENGTH + 1)), /at most 1000/);
});

test("errors: expired sessions, consent, CSRF, limits and network failures read clearly", () => {
  const fallback = "Couldn't post your review";
  assert.equal(foodErrorMessage(401, "session has expired", fallback), "Your session has expired. Sign in again to continue.");
  assert.match(foodErrorMessage(403, "active consent is required", fallback), /Accept the consent document/);
  assert.match(foodErrorMessage(403, "CSRF token is invalid", fallback), /Reload the page/);
  assert.equal(foodErrorMessage(403, "Food Chat moderators only", fallback), "Only Food Chat moderators can do that.");
  assert.match(foodErrorMessage(429, null, fallback), /too often/);
  assert.match(foodErrorMessage(0, null, fallback), /Couldn't reach TritonSpend/);
  assert.equal(foodErrorMessage(409, "You've already reviewed this. Edit your existing review instead.", fallback), "You've already reviewed this. Edit your existing review instead.");
  // Server errors keep the page's own wording instead of a bare "Internal server error".
  assert.equal(foodErrorMessage(500, "Internal server error", "Couldn't load your account"), "Couldn't load your account. Something went wrong on the server; try again in a moment.");
});

// --- Venue ratings and venue chat -----------------------------------------------------------------
import {
  MAX_MESSAGE_LENGTH, formatVenueAverage, mergeLatest, messageError, ratedByLabel, replaceMessage, withOlder, withoutMessage
} from "./food-chat.ts";

test("venue rating: average out of 5, how many students rated, and an honest empty state", () => {
  assert.equal(formatVenueAverage({ average_rating: null, rating_count: 0 }), "No ratings yet"); // never 0/5
  assert.equal(formatVenueAverage({ average_rating: 4.33, rating_count: 3 }), "4.3/5");
  assert.equal(formatVenueAverage({ average_rating: 5, rating_count: 1 }), "5.0/5");
  assert.equal(formatVenueAverage({ average_rating: 3.75, rating_count: 4 }), "3.8/5");
  assert.equal(ratedByLabel(1), "1 student rated");
  assert.equal(ratedByLabel(12), "12 students rated");
});

test("chat messages: any free text within the limit", () => {
  assert.equal(messageError("The Slice at Pines pepperoni pizza was great but pricey."), null);
  assert.equal(messageError("   "), "Write a message first.");
  assert.equal(messageError("x".repeat(MAX_MESSAGE_LENGTH)), null);
  assert.match(messageError("x".repeat(MAX_MESSAGE_LENGTH + 1)), /at most 1000/);
});

const msg = (id, minute, extra = {}) => ({
  id, author_name: "Sunny Otter 1234", is_mine: false, body: id, edited: false,
  created_at: `2026-11-08T12:${String(minute).padStart(2, "0")}:00Z`, updated_at: `2026-11-08T12:${String(minute).padStart(2, "0")}:00Z`,
  moderation_state: null, ...extra
});

test("chat polling: new, edited, deleted and hidden messages are reflected; older loaded pages stay", () => {
  const current = [msg("a", 1), msg("b", 2), msg("c", 3), msg("d", 4)];
  // The newest page now starts at "c": "d" was deleted, "c" edited, "e" is new; "a" and "b" (older) stay.
  const merged = mergeLatest(current, { venue_id: "pines", has_older: true, messages: [msg("c", 3, { body: "c edited", edited: true }), msg("e", 5)] });
  assert.deepEqual(merged.map((m) => [m.id, m.body]), [["a", "a"], ["b", "b"], ["c", "c edited"], ["e", "e"]]);
  assert.deepEqual(mergeLatest([], { venue_id: "pines", has_older: false, messages: [msg("x", 9)] }).map((m) => m.id), ["x"]);
  assert.deepEqual(mergeLatest(current, { venue_id: "pines", has_older: false, messages: [] }), []); // every message is gone
  // Same timestamp: the id breaks the tie, as on the server.
  assert.deepEqual(mergeLatest([msg("a", 1), msg("b", 1)], { venue_id: "p", has_older: true, messages: [msg("b", 1), msg("c", 2)] }).map((m) => m.id), ["a", "b", "c"]);
});

test("chat paging: older messages go on top without duplicates; local edits and deletions", () => {
  const current = [msg("c", 3), msg("d", 4)];
  const older = withOlder(current, { venue_id: "pines", has_older: false, messages: [msg("a", 1), msg("b", 2), msg("c", 3)] });
  assert.deepEqual(older.map((m) => m.id), ["a", "b", "c", "d"]);
  assert.deepEqual(replaceMessage(current, msg("d", 4, { body: "fixed" })).map((m) => m.body), ["c", "fixed"]);
  assert.deepEqual(withoutMessage(current, "c").map((m) => m.id), ["d"]);
});
