/**
 * Food Chat: API types and the pure logic behind the screens (routing, threads, votes, input
 * checks, error messages). No runtime imports so Node's test runner can load it directly.
 * Limits mirror backend/app/food_chat_schemas.py; the backend stays authoritative.
 */

import type { WeeklyHours } from "./food-venues";

export const MAX_REVIEW_LENGTH = 2000;
export const MAX_COMMENT_LENGTH = 1000;
export const MAX_REPORT_DETAILS_LENGTH = 500;

export type NamedRef = { id: string; name: string };
export type RatingSummary = { review_count: number; average_rating: number | null };
export type RatingBreakdown = RatingSummary & { breakdown: Record<string, number> };
export type Acceptance = "accepted" | "not_accepted" | "not_verified";

export type FoodStation = {
  id: string; venue_id: string; name: string; menu_url: string | null; hours: WeeklyHours | null;
  is_active: boolean; verified_on: string; menu_item_count: number;
};
export type FoodVenueSummary = {
  id: string; name: string; operator: "hdh" | "triton_cash_partner"; kind: "restaurant" | "market" | "merchant";
  summary: string | null; campus_area: string | null; location: string | null; on_campus: boolean;
  coordinates: { lat: number; lng: number } | null; has_published_hours: boolean;
  wallets: Record<"dining_dollars" | "triton_cash", { status: Acceptance; reason: string; source: string | null }>;
  station_count: number; rating: RatingSummary; is_active: boolean; verified_on: string;
};
export type FoodVenueDetail = FoodVenueSummary & {
  description: string | null; tags: string[]; hours: WeeklyHours | null; menu_url: string | null;
  website_url: string | null; sources: { key: string; label: string; url: string }[]; notes: string[];
  catalog_version: string; stations: FoodStation[];
};
export type FoodStationDetail = FoodStation & { venue: NamedRef & { menu_url: string | null }; sources: { key: string; label: string; url: string }[]; catalog_version: string };
export type FoodMenuItem = {
  id: string; station_id: string; name: string; description: string | null; dietary_labels: string[] | null;
  allergens: string[] | null; source_url: string; verified_at: string; is_active: boolean; rating: RatingSummary;
};
export type StationMenu = { station_id: string; menu_status: "no_verified_menu_data" | "verified_items"; items: FoodMenuItem[]; total: number };
export type MenuItemDetail = Omit<FoodMenuItem, "station_id" | "rating"> & { station: NamedRef; venue: NamedRef; rating: RatingBreakdown };

export type ModerationState = "visible" | "hidden" | "removed";
export type Review = {
  id: string; target_type: "venue" | "menu_item"; venue: NamedRef; station: NamedRef | null; menu_item: NamedRef | null;
  rating: number; body: string; author_name: string; is_mine: boolean; edited: boolean; comment_count: number;
  moderation_state: ModerationState | null; created_at: string; updated_at: string;
};
export type ReviewSort = "newest" | "highest" | "lowest";
export type ReviewList = { summary: RatingBreakdown; reviews: Review[]; my_review: Review | null; total: number; limit: number; offset: number; sort: ReviewSort };
export type VoteValue = -1 | 0 | 1;
export type Comment = {
  id: string; parent_id: string | null; is_placeholder: boolean; body: string | null; author_name: string | null;
  is_mine: boolean; score: number; upvotes: number; downvotes: number; my_vote: VoteValue; edited: boolean; created_at: string;
};
export type CommentSort = "top" | "newest" | "oldest";
export type CommentList = { review_id: string; comments: Comment[]; sort: CommentSort };
export type VoteResult = { comment_id: string; score: number; upvotes: number; downvotes: number; my_vote: VoteValue };
export type FoodMe = { display_name: string | null; is_moderator: boolean; consent_active: boolean };
export type ReportReason = "spam" | "harassment" | "hate" | "sexual_content" | "misinformation" | "off_topic" | "other";
export type ModerationReport = {
  id: string; reason: ReportReason; details: string | null; status: "open" | "actioned" | "dismissed"; created_at: string;
  resolved_at: string | null; open_reports_on_target: number;
  content: { kind: "message" | "review" | "comment"; id: string; body: string | null; rating: number | null; author_name: string;
    moderation_state: ModerationState; review_id: string | null; venue: NamedRef; created_at: string };
};
export type ModerationAction = {
  id: string; moderator_name: string; action: "hide" | "restore" | "remove" | "resolve_report" | "dismiss_report";
  target_type: "review" | "comment" | "report" | "message"; target_id: string; note: string | null; created_at: string;
};

export const REPORT_REASONS: { value: ReportReason; label: string }[] = [
  { value: "spam", label: "Spam or advertising" },
  { value: "harassment", label: "Harassment or bullying" },
  { value: "hate", label: "Hate speech" },
  { value: "sexual_content", label: "Sexual content" },
  { value: "misinformation", label: "False or misleading" },
  { value: "off_topic", label: "Off topic" },
  { value: "other", label: "Something else" }
];

// --- Routing: #food-nearby, #food-nearby/venue/<id>, /station/<id>, /dish/<id>, /moderation ---

export type FoodRoute =
  | { page: "list" }
  | { page: "venue"; venueId: string }
  | { page: "station"; stationId: string }
  | { page: "dish"; itemId: string }
  | { page: "moderation" };

export function parseFoodRoute(hash: string): FoodRoute {
  const parts = hash.replace(/^#/, "").split("/").map((part) => { try { return decodeURIComponent(part); } catch { return ""; } });
  if (parts[0] !== "food-nearby") return { page: "list" };
  const [, kind, id] = parts;
  if (kind === "venue" && id) return { page: "venue", venueId: id };
  if (kind === "station" && id) return { page: "station", stationId: id };
  if (kind === "dish" && id) return { page: "dish", itemId: id };
  if (kind === "moderation") return { page: "moderation" };
  return { page: "list" };
}

export function foodRouteHash(route: FoodRoute): string {
  switch (route.page) {
    case "venue": return `#food-nearby/venue/${encodeURIComponent(route.venueId)}`;
    case "station": return `#food-nearby/station/${encodeURIComponent(route.stationId)}`;
    case "dish": return `#food-nearby/dish/${encodeURIComponent(route.itemId)}`;
    case "moderation": return "#food-nearby/moderation";
    default: return "#food-nearby";
  }
}

// --- Threads -------------------------------------------------------------------------------------

export type ThreadNode = Comment & { depth: number; children: ThreadNode[] };

/** Builds the reply tree, keeping the server's order among siblings. A reply whose parent is
 * missing is shown at the top level rather than dropped. */
export function buildThread(comments: Comment[]): ThreadNode[] {
  const nodes = new Map<string, ThreadNode>(comments.map((comment) => [comment.id, { ...comment, depth: 0, children: [] }]));
  const roots: ThreadNode[] = [];
  for (const comment of comments) {
    const node = nodes.get(comment.id)!;
    const parent = comment.parent_id ? nodes.get(comment.parent_id) : undefined;
    (parent ? parent.children : roots).push(node);
  }
  const setDepth = (list: ThreadNode[], depth: number) => list.forEach((node) => { node.depth = depth; setDepth(node.children, depth + 1); });
  setDepth(roots, 0);
  return roots;
}

// --- Votes ---------------------------------------------------------------------------------------

/** Clicking your current vote removes it; otherwise it becomes the clicked value. */
export function nextVote(current: VoteValue, clicked: 1 | -1): VoteValue {
  return current === clicked ? 0 : clicked;
}

/** The comment as it looks after the server applied a vote. */
export function applyVoteResult(comment: Comment, result: VoteResult): Comment {
  return { ...comment, score: result.score, upvotes: result.upvotes, downvotes: result.downvotes, my_vote: result.my_vote };
}

// --- Ratings -------------------------------------------------------------------------------------

export function formatAverage(summary: RatingSummary): string {
  return summary.average_rating === null ? "No reviews yet" : summary.average_rating.toFixed(1);
}

export function reviewCountLabel(count: number): string {
  return count === 1 ? "1 review" : `${count} reviews`;
}

/** Five rows, 5 stars first, with the share of reviews (0-100, whole numbers). */
export function breakdownRows(summary: RatingBreakdown): { stars: number; count: number; percent: number }[] {
  return [5, 4, 3, 2, 1].map((stars) => {
    const count = summary.breakdown[String(stars)] ?? 0;
    return { stars, count, percent: summary.review_count ? Math.round((count / summary.review_count) * 100) : 0 };
  });
}

// --- Input checks --------------------------------------------------------------------------------

/** A review is about a venue; dishes and stations are mentioned freely in the text. */
export type ReviewDraft = { venueId: string; rating: number; body: string };

export function reviewDraftError(draft: ReviewDraft): string | null {
  if (!draft.venueId) return "Choose the venue you're reviewing.";
  if (!Number.isInteger(draft.rating) || draft.rating < 1 || draft.rating > 5) return "Choose a rating from 1 to 5 stars.";
  const body = draft.body.trim();
  if (!body) return "Write a few words about your experience.";
  if (body.length > MAX_REVIEW_LENGTH) return `Reviews can be at most ${MAX_REVIEW_LENGTH} characters.`;
  return null;
}

export function commentError(body: string): string | null {
  const text = body.trim();
  if (!text) return "Write something first.";
  if (text.length > MAX_COMMENT_LENGTH) return `Comments can be at most ${MAX_COMMENT_LENGTH} characters.`;
  return null;
}

// --- Errors --------------------------------------------------------------------------------------

/** A friendly message for a failed Food Chat request. */
export function foodErrorMessage(status: number, detail: string | null, fallback: string): string {
  if (status === 0) return "Couldn't reach TritonSpend. Check your connection and try again.";
  if (status === 401) return "Your session has expired. Sign in again to continue.";
  if (status === 403 && detail && /consent/i.test(detail)) return "Accept the consent document (top of the page) before posting in Food Chat or saving favourites.";
  if (status === 403 && detail && /moderator/i.test(detail)) return "Only Food Chat moderators can do that.";
  if (status === 403) return "Your session needs refreshing. Reload the page and try again.";
  if (status === 429) return detail ?? "You're doing that too often. Please wait a few minutes.";
  if (status >= 500) return `${fallback}. Something went wrong on the server; try again in a moment.`;
  return detail || fallback;
}

// --- Where a review belongs ----------------------------------------------------------------------

/** The venue every review belongs to, plus the dish for older dish reviews (made before Food Chat
 * became venue-only). Venue reviews have no station or menu item, and need none to render. */
export function reviewPlace(review: Pick<Review, "venue" | "station" | "menu_item">): { venue: NamedRef; about: string | null } {
  if (!review.menu_item) return { venue: review.venue, about: null };
  return { venue: review.venue, about: review.station ? `${review.menu_item.name} · ${review.station.name}` : review.menu_item.name };
}

// --- Venue ratings and venue chat (the current Food Chat) ----------------------------------------

export const MAX_MESSAGE_LENGTH = 1000;
/** How often an open chat checks for new messages. */
export const CHAT_POLL_MS = 10_000;

export type VenueRating = { venue_id: string; average_rating: number | null; rating_count: number; my_rating: number | null };
export type ChatMessage = {
  id: string; author_name: string; is_mine: boolean; body: string; edited: boolean; created_at: string; updated_at: string;
  moderation_state: ModerationState | null;
};
export type MessagePage = { venue_id: string; messages: ChatMessage[]; has_older: boolean };

/** "4.3/5", or "No ratings yet" (never 0/5). */
export function formatVenueAverage(rating: Pick<VenueRating, "average_rating" | "rating_count">): string {
  return rating.average_rating === null || rating.rating_count === 0 ? "No ratings yet" : `${rating.average_rating.toFixed(1)}/5`;
}

export function ratedByLabel(count: number): string {
  return count === 1 ? "1 student rated" : `${count} students rated`;
}

export function messageError(body: string): string | null {
  const text = body.trim();
  if (!text) return "Write a message first.";
  if (text.length > MAX_MESSAGE_LENGTH) return `Messages can be at most ${MAX_MESSAGE_LENGTH} characters.`;
  return null;
}

const position = (message: Pick<ChatMessage, "created_at" | "id">): [number, string] => [Date.parse(message.created_at), message.id];
function isBefore(a: Pick<ChatMessage, "created_at" | "id">, b: Pick<ChatMessage, "created_at" | "id">): boolean {
  const [timeA, idA] = position(a);
  const [timeB, idB] = position(b);
  return timeA < timeB || (timeA === timeB && idA < idB);
}

/** The feed after a poll of the newest page: messages older than that page stay as loaded; the
 * page replaces everything from its first message on, so new, edited, deleted and hidden messages
 * all show up correctly. */
export function mergeLatest(current: ChatMessage[], latest: MessagePage): ChatMessage[] {
  if (latest.messages.length === 0) return latest.has_older ? current : [];
  const first = latest.messages[0];
  return [...current.filter((message) => isBefore(message, first)), ...latest.messages];
}

/** The feed after "Load older messages": the older page goes on top, without duplicates. */
export function withOlder(current: ChatMessage[], older: MessagePage): ChatMessage[] {
  const seen = new Set(current.map((message) => message.id));
  return [...older.messages.filter((message) => !seen.has(message.id)), ...current];
}

export function replaceMessage(current: ChatMessage[], updated: ChatMessage): ChatMessage[] {
  return current.map((message) => (message.id === updated.id ? updated : message));
}

export function withoutMessage(current: ChatMessage[], id: string): ChatMessage[] {
  return current.filter((message) => message.id !== id);
}
