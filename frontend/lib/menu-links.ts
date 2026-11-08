/**
 * Links to official menus. TritonSpend does not copy, cache or republish menu content: it only
 * opens the official page in a new tab. Every URL comes from the verified catalog
 * (backend/app/data/food_catalog.json); nothing here builds or guesses URLs or query parameters.
 *
 * HDH publishes one menu page per venue that lists all of its stations, so a station uses its own
 * official URL if the catalog ever has one, and otherwise its venue's, labelled as the venue's menu.
 * No runtime imports so Node's test runner can load it directly.
 */

/** Attributes for every external menu link: new tab, no access to this page, no referrer. */
export const EXTERNAL_LINK = { target: "_blank", rel: "noopener noreferrer" } as const;

export type MenuLink = {
  href: string;
  /** Visible text, e.g. "Today's menu" or "64 Degrees menu". */
  label: string;
  /** "station": the station's own page; "venue": the venue's page covering all its stations. */
  scope: "station" | "venue";
  /** Accessible name and tooltip, saying exactly what opens. */
  description: string;
};

/** A usable official URL, or null for missing, blank or non-web values (never a broken link). */
export function officialUrl(value: string | null | undefined): string | null {
  if (!value || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/** HDH's dated menu pages ("Venue_V3"); other HDH links (e.g. the Markets page) are general pages. */
export function isHdhMenuPage(url: string): boolean {
  return /^https:\/\/hdh-web\.ucsd\.edu\/dining\/apps\/diningservices\/Restaurants\/Venue_V3\?/.test(url);
}

/** The venue's official menu link, for venue cards and the venue page. */
export function venueMenuLink(venue: { name: string; operator?: string; menuUrl: string | null | undefined }): MenuLink | null {
  const href = officialUrl(venue.menuUrl);
  if (!href) return null;
  if (isHdhMenuPage(href)) {
    return { href, label: "Today's menu", scope: "venue", description: `Open the official HDH menu for ${venue.name} in a new tab` };
  }
  const hdh = venue.operator === undefined ? href.includes("ucsd.edu") : venue.operator === "hdh";
  return hdh
    ? { href, label: "HDH page", scope: "venue", description: `Open HDH's official page for ${venue.name} in a new tab` }
    : { href, label: "Menu", scope: "venue", description: `Open the menu for ${venue.name} in a new tab` };
}

/** A station's menu: its own official page if the catalog has one, else its venue's menu. */
export function stationMenuLink(
  station: { name: string; menu_url: string | null | undefined },
  venue: { name: string; menu_url: string | null | undefined }
): MenuLink | null {
  const own = officialUrl(station.menu_url);
  if (own) {
    return { href: own, label: "Station menu", scope: "station", description: `Open the official menu for ${station.name} in a new tab` };
  }
  const href = officialUrl(venue.menu_url);
  if (!href) return null;
  return isHdhMenuPage(href)
    ? {
      href, label: `${venue.name} menu`, scope: "venue",
      description: `Open the official HDH menu for ${venue.name}, which covers all its stations including ${station.name}, in a new tab`
    }
    : {
      href, label: `${venue.name} on HDH`, scope: "venue",
      description: `Open HDH's official page for ${venue.name} (it covers ${station.name}) in a new tab`
    };
}

/** One line explaining a venue-level link on a station, so it never looks station-specific. */
export function venueScopeNote(link: MenuLink, venueName: string, stationName: string): string | null {
  if (link.scope === "station") return null;
  return isHdhMenuPage(link.href)
    ? `HDH publishes one official menu for ${venueName} that covers all its stations, including ${stationName}.`
    : `There's no official menu page for ${stationName}; this opens HDH's page for ${venueName}.`;
}
