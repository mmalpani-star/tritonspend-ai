/**
 * The signed-in student's own area ("You"): sidebar sections, page routes, API types for the
 * private /api/v1/me endpoints, and the pure helpers behind those pages. No runtime imports so
 * Node's test runner can load it directly.
 */

import type { NamedRef, RatingSummary } from "./food-chat";

// --- Pages and the sidebar -----------------------------------------------------------------------

export type YouPage = "account" | "favourite-dishes" | "favourite-venues" | "ratings" | "messages" | "settings";
export const YOU_PAGES: readonly YouPage[] = ["account", "favourite-dishes", "favourite-venues", "ratings", "messages", "settings"];
// Addresses from before Food Chat became ratings + chat.
const PAGE_ALIASES: Record<string, YouPage> = { reviews: "ratings", discussions: "messages" };

export type SidebarItem = { kind: "page"; page: YouPage; label: string } | { kind: "sign-out"; label: string };
export type SidebarSection = { title: string; items: SidebarItem[] };

export const SIDEBAR_SECTIONS: readonly SidebarSection[] = [
  { title: "Your account", items: [{ kind: "page", page: "account", label: "Your Account" }] },
  {
    title: "Your food",
    items: [
      { kind: "page", page: "favourite-dishes", label: "Favourite Dishes" },
      { kind: "page", page: "favourite-venues", label: "Favourite Venues" }
    ]
  },
  {
    title: "Your activity",
    items: [
      { kind: "page", page: "ratings", label: "Your Ratings" },
      { kind: "page", page: "messages", label: "Your Messages" }
    ]
  },
  {
    title: "Settings",
    items: [
      { kind: "page", page: "settings", label: "Settings" },
      { kind: "sign-out", label: "Sign Out" }
    ]
  }
];

export const PAGE_TITLES: Record<YouPage, string> = {
  account: "Your Account",
  "favourite-dishes": "Favourite Dishes",
  "favourite-venues": "Favourite Venues",
  ratings: "Your Ratings",
  messages: "Your Messages",
  settings: "Settings"
};

/** "#you/settings" -> "settings"; "#you" or an unknown page -> "account"; anything else -> null. */
export function parseYouPage(hash: string): YouPage | null {
  const [view, raw] = hash.replace(/^#/, "").split("/");
  if (view !== "you") return null;
  const page = PAGE_ALIASES[raw] ?? raw;
  return (YOU_PAGES as readonly string[]).includes(page) ? (page as YouPage) : "account";
}

export function youPageHash(page: YouPage): string {
  return `#you/${page}`;
}

// --- API types -----------------------------------------------------------------------------------

export type AccountSummary = {
  email: string | null;
  account_created_at: string;
  last_login_at: string | null;
  timezone: string;
  consent: { active: boolean; version: string | null; accepted_at: string | null; document_url: string | null };
  display_name: string | null;
  is_moderator: boolean;
  activity: { ratings: number; messages: number; favorite_venues: number; favorite_dishes: number };
};

export type FavoriteVenue = {
  id: string; name: string; kind: string; campus_area: string | null; location: string | null;
  is_active: boolean; rating: RatingSummary; saved_at: string;
};
export type FavoriteDish = {
  id: string; name: string; description: string | null; station: NamedRef; venue: NamedRef;
  is_active: boolean; rating: RatingSummary; saved_at: string;
};
export type Favorites = { venues: FavoriteVenue[]; dishes: FavoriteDish[] };
export type FavoriteKind = "venue" | "dish";
export type FavoriteChange = { kind: FavoriteKind; id: string; saved: boolean };

export type MyRating = { venue: NamedRef; rating: number; venue_average: number | null; venue_rating_count: number; updated_at: string };
export type MyRatings = { ratings: MyRating[] };
export type MyMessage = {
  id: string; venue: NamedRef; body: string; edited: boolean; moderation_state: "visible" | "hidden" | "removed";
  created_at: string; updated_at: string;
};
export type MyMessages = { messages: MyMessage[]; total: number; limit: number; offset: number };

// --- Favourites ----------------------------------------------------------------------------------

export function isFavorite(favorites: Favorites | null, kind: FavoriteKind, id: string): boolean {
  if (!favorites) return false;
  return kind === "venue" ? favorites.venues.some((venue) => venue.id === id) : favorites.dishes.some((dish) => dish.id === id);
}

/** The list after a removal confirmed by the server. Additions need the full record, so the caller
 * reloads the list instead (the server is the source of truth). */
export function withoutFavorite(favorites: Favorites, kind: FavoriteKind, id: string): Favorites {
  return kind === "venue"
    ? { ...favorites, venues: favorites.venues.filter((venue) => venue.id !== id) }
    : { ...favorites, dishes: favorites.dishes.filter((dish) => dish.id !== id) };
}

export function favoriteButtonLabel(saved: boolean, name: string): string {
  return saved ? `Remove ${name} from favourites` : `Save ${name} to favourites`;
}

// --- Activity ------------------------------------------------------------------------------------

export function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
