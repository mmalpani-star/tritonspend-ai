"use client";

import {
  ArrowLeft, Check, ChevronDown, ChevronRight, Clock, CreditCard, ExternalLink, HelpCircle, Info, LocateFixed, Loader2, MapPin,
  MessageSquare, Search, ShieldCheck, Store, UtensilsCrossed, WalletCards, X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listParticipantForecasts, readFoodMe, readFoodVenues, readPrediction } from "../lib/api";
import { CAMPUS_LANDMARKS } from "../lib/campus-landmarks";
import { campusToday, formatCalendarDate } from "../lib/datetime";
import { VENUES, VENUES_VERIFIED_ON } from "../lib/food-venues-data";
import {
  DAY_KEYS, DailyTargets, EligibilityStatus, LatLng, VENUE_SOURCES, VenueCategory, VenueView, WALLET_LABELS,
  campusClock, describeOpenState, formatDistance, formatHours, idealDailyTargets, visibleVenues, whyReasons
} from "../lib/food-venues";
import type { Account } from "../lib/types";
import { formatMoney, useWallet } from "../lib/wallet";
import { FoodMe, FoodRoute, RatingSummary, formatVenueAverage, ratedByLabel } from "../lib/food-chat";
import { DishPage, ModerationPage, StationPage, VenuePage } from "./food/food-pages";
import { OfficialMenuLink, Stars, useFoodRoute } from "./food/food-ui";
import { EXTERNAL_LINK, officialUrl, venueMenuLink } from "../lib/menu-links";
import { FoodMosaic, VenueCover } from "./food/food-media";
import { FoodPhotoId, coverPhotos, foodCategories } from "../lib/food-photos";
import { FavoriteButton } from "./account/favorites";

const WALLETS: Account[] = ["dining_dollars", "triton_cash"];
const CATEGORIES: { value: VenueCategory; label: string }[] = [
  { value: "all", label: "All" },
  { value: "campus-dining", label: "Campus Dining" },
  { value: "triton-cash", label: "Triton Cash Nearby" }
];
const SHORT_DAY: Record<string, string> = { sun: "Sun", mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat" };

// ---------------------------------------------------------------------------------------------
// Location: asked for only on click, kept in memory, never sent or stored.

type LocationState =
  | { status: "idle" }
  | { status: "locating" }
  | { status: "ready"; origin: LatLng; label: string; fromDevice: boolean }
  | { status: "denied" | "unavailable" | "timeout" | "unsupported" };

const LOCATION_PROBLEMS: Record<"denied" | "unavailable" | "timeout" | "unsupported", string> = {
  denied: "Location permission was turned off. You can allow it in your browser settings, or pick a campus spot.",
  unavailable: "Your device couldn't find your location right now.",
  timeout: "Finding your location took too long.",
  unsupported: "This browser can't share your location."
};

function useDeviceLocation() {
  const [state, setState] = useState<LocationState>({ status: "idle" });
  const locate = () => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator) || !window.isSecureContext) {
      setState({ status: "unsupported" });
      return;
    }
    setState({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      (position) => setState({ status: "ready", origin: { lat: position.coords.latitude, lng: position.coords.longitude }, label: "your location", fromDevice: true }),
      (error) => setState({ status: error.code === error.PERMISSION_DENIED ? "denied" : error.code === error.TIMEOUT ? "timeout" : "unavailable" }),
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 }
    );
  };
  const chooseLandmark = (id: string) => {
    const landmark = CAMPUS_LANDMARKS.find((item) => item.id === id);
    if (landmark) setState({ status: "ready", origin: { lat: landmark.lat, lng: landmark.lng }, label: landmark.name, fromDevice: false });
  };
  const clear = () => setState({ status: "idle" });
  return { state, locate, chooseLandmark, clear };
}

// ---------------------------------------------------------------------------------------------
// Budget context from the existing saved forecast + prediction (no new model).

type BudgetState = { status: "loading" } | { status: "ready"; targets: DailyTargets; endDate: string } | { status: "none" } | { status: "error" };

function useDailyTargets(): BudgetState {
  const [state, setState] = useState<BudgetState>({ status: "loading" });
  useEffect(() => {
    let active = true;
    (async () => {
      const today = campusToday();
      const forecasts = await listParticipantForecasts(20);
      const current = forecasts.filter((item) => item.end_date >= today).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
      if (!current) return { status: "none" } as const;
      const prediction = await readPrediction(current.id);
      const targets = idealDailyTargets(prediction, today);
      return targets ? ({ status: "ready", targets, endDate: current.end_date } as const) : ({ status: "none" } as const);
    })()
      .then((next) => active && setState(next))
      .catch(() => active && setState({ status: "error" }));
    return () => {
      active = false;
    };
  }, []);
  return state;
}

function WalletSummary({ budget, onOpenWallet, onOpenForecast }: { budget: BudgetState; onOpenWallet: () => void; onOpenForecast: () => void }) {
  const [wallet] = useWallet();
  const latest = wallet.status === "ready" ? wallet.data.latest : null;
  return (
    <div className="food-wallet" aria-label="Your wallets">
      <WalletCards size={18} aria-hidden="true" className="shrink-0 text-[var(--primary)]" />
      {wallet.status === "loading" && <span className="text-[var(--text-muted)]">Loading balances…</span>}
      {wallet.status === "error" && <span className="text-[var(--text-muted)]">Balances unavailable right now.</span>}
      {wallet.status === "ready" && !latest && (
        <span>No balances saved yet. <button type="button" className="food-link" onClick={onOpenWallet}>Add balances</button></span>
      )}
      {latest && (
        <span className="food-wallet-balances">
          <span><span className="food-wallet-label">Dining Dollars</span> <strong>{formatMoney(latest.dining_dollars_cents)}</strong></span>
          <span><span className="food-wallet-label">Triton Cash</span> <strong>{formatMoney(latest.triton_cash_cents)}</strong></span>
          <span className="food-wallet-label">as of {formatCalendarDate(latest.effective_date, { month: "short", day: "numeric" })}</span>
        </span>
      )}
      <span className="food-wallet-target">
        {budget.status === "ready" && (
          <>Daily target{" "}
            {WALLETS.filter((w) => budget.targets[w] !== undefined).map((w) => `${formatMoney(budget.targets[w]!)} ${WALLET_LABELS[w]}`).join(" · ")}
            <span className="food-wallet-label"> · ideal path to {formatCalendarDate(budget.endDate, { month: "short", day: "numeric" })}</span>
          </>
        )}
        {budget.status === "none" && <>No daily target yet. <button type="button" className="food-link" onClick={onOpenForecast}>Create a forecast</button></>}
        {budget.status === "error" && <span className="food-wallet-label">Daily target unavailable right now.</span>}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Venue card

const STATUS_ICON: Record<EligibilityStatus, typeof Check> = { accepted: Check, not_accepted: X, not_verified: HelpCircle };
const STATUS_TEXT: Record<EligibilityStatus, string> = { accepted: "accepted", not_accepted: "not accepted", not_verified: "not verified" };

function WalletPill({ wallet, status }: { wallet: Account; status: EligibilityStatus }) {
  const Icon = STATUS_ICON[status];
  return (
    <span className={`food-pill food-pill-${status}`} title={`${WALLET_LABELS[wallet]} ${STATUS_TEXT[status]}`}>
      <Icon size={13} aria-hidden="true" />
      {WALLET_LABELS[wallet]}
      <span className="sr-only"> {STATUS_TEXT[status]}</span>
    </span>
  );
}

function placeLine(view: VenueView): string {
  const { venue } = view;
  const parts = [venue.location, venue.campusArea && venue.campusArea !== venue.location ? venue.campusArea : null].filter(Boolean);
  if (!venue.onCampus) return `${parts.join(" · ")} · off campus`;
  return parts.length > 0 ? parts.join(" · ") : "On campus";
}

const venueTexts = (venue: VenueView["venue"]) => [venue.name, venue.summary, venue.description, ...venue.tags, ...venue.stations];

function VenueCard({ view, preferred, targets, rating, cover, onOpen }: {
  view: VenueView;
  cover?: FoodPhotoId;
  preferred: Account[];
  targets: DailyTargets | null;
  rating: RatingSummary | undefined;
  onOpen: (route: FoodRoute) => void;
}) {
  const { venue, wallets, open, meters } = view;
  const reasons = whyReasons(view, preferred, targets, formatMoney);
  const Icon = venue.operator === "triton_cash_partner" ? CreditCard : venue.kind === "market" ? Store : UtensilsCrossed;
  const kindLabel = venue.operator === "hdh" ? (venue.kind === "market" ? "Campus market" : "Campus dining") : "Triton Cash merchant";
  const menuLink = venueMenuLink({ name: venue.name, operator: venue.operator, menuUrl: venue.links.menu });
  const website = menuLink ? null : officialUrl(venue.links.website);
  return (
    <article className="food-card" aria-labelledby={`venue-${venue.id}`}>
      <VenueCover placeKey={venue.id} texts={venueTexts(venue)} kind={venue.kind} photoId={cover} />
      <div className="food-card-body">
      <div className="flex items-start gap-3">
        <span className="food-card-icon"><Icon size={19} aria-hidden="true" /></span>
        <div className="min-w-0 flex-1">
          <h3 id={`venue-${venue.id}`} className="food-card-title">
            <button type="button" className="food-card-title-link" onClick={() => onOpen({ page: "venue", venueId: venue.id })}>{venue.name}</button>
          </h3>
          <p className="food-card-kind">{kindLabel}{venue.summary ? ` · ${venue.summary}` : ""}</p>
          {rating && (
            <p className="food-rating-line mt-1" aria-label={`Student rating: ${formatVenueAverage({ average_rating: rating.average_rating, rating_count: rating.review_count })}`}>
              <Stars value={rating.average_rating} size={14} />
              <span className="food-muted">{rating.review_count ? `${formatVenueAverage({ average_rating: rating.average_rating, rating_count: rating.review_count })} · ${ratedByLabel(rating.review_count)}` : "No ratings yet"}</span>
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {meters !== null && <span className="food-distance" title="Straight-line distance">{formatDistance(meters)}</span>}
          <FavoriteButton kind="venue" id={venue.id} name={venue.name} />
        </div>
      </div>
      <p className="food-card-line"><MapPin size={14} aria-hidden="true" /> {placeLine(view)}</p>
      <p className={`food-card-line food-open-${open.status}`}><Clock size={14} aria-hidden="true" /> {describeOpenState(open)}</p>
      <div className="flex flex-wrap gap-1.5">
        {WALLETS.map((wallet) => <WalletPill key={wallet} wallet={wallet} status={wallets[wallet].status} />)}
      </div>
      <details className="food-why">
        <summary><span>Why this works for you</span><ChevronDown size={15} aria-hidden="true" /></summary>
        <ul>
          {reasons.map((reason) => <li key={reason.text} className={`food-why-${reason.tone}`}>{reason.text}</li>)}
        </ul>
      </details>
      <button type="button" className="food-open-venue" onClick={() => onOpen({ page: "venue", venueId: venue.id })}>
        <MessageSquare size={14} aria-hidden="true" /> Ratings, chat &amp; stations <ChevronRight size={14} aria-hidden="true" />
      </button>
      <div className="food-card-actions">
        {menuLink && <OfficialMenuLink link={menuLink} />}
        {website && <a className="food-link" href={website} {...EXTERNAL_LINK}>Website <ExternalLink size={13} aria-hidden="true" /></a>}
        <details className="food-details">
          <summary>Details</summary>
          <VenueDetails view={view} />
        </details>
      </div>
      </div>
    </article>
  );
}

function VenueDetails({ view }: { view: VenueView }) {
  const { venue, wallets } = view;
  return (
    <div className="food-details-body">
      {venue.description && <p>{venue.description}</p>}
      {venue.stations.length > 0 && <p><strong>Stations:</strong> {venue.stations.join(", ")}</p>}
      <div>
        <strong>Payment</strong>
        <ul className="mt-1 space-y-1">
          {WALLETS.map((wallet) => {
            const item = wallets[wallet];
            const source = item.source ? VENUE_SOURCES[item.source] : null;
            return <li key={wallet}>{WALLET_LABELS[wallet]}: {STATUS_TEXT[item.status]}. {item.reason}{source && <> <a className="food-link" href={source.url} target="_blank" rel="noreferrer">Source</a></>}</li>;
          })}
        </ul>
      </div>
      <div>
        <strong>Hours</strong>
        {venue.hours ? (
          <>
            <table className="food-hours"><tbody>
              {[...DAY_KEYS.slice(1), DAY_KEYS[0]].map((day) => <tr key={day}><th scope="row">{SHORT_DAY[day]}</th><td>{formatHours(venue.hours![day])}</td></tr>)}
            </tbody></table>
            <p className="food-muted">HDH&apos;s published weekly hours. Holiday and break hours can differ.</p>
          </>
        ) : <p className="food-muted">Not verified. Check with the venue before you go.</p>}
      </div>
      <p>
        <strong>Location:</strong> {placeLine(view)}.{" "}
        {venue.coordinates ? <span className="food-muted">Position from the official campus map; distances are straight-line.</span> : <span className="food-muted">No verified map position, so no distance is shown.</span>}
      </p>
      {venue.notes.map((note) => <p key={note} className="food-muted">{note}</p>)}
      <p className="food-muted">
        Sources: {venue.sources.map((key, index) => <span key={key}>{index > 0 && ", "}<a className="food-link" href={VENUE_SOURCES[key].url} target="_blank" rel="noreferrer">{VENUE_SOURCES[key].label}</a></span>)}. Checked {formatCalendarDate(VENUES_VERIFIED_ON)}.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Page

function VenueDirectory({ onBack, onOpenForecast, onOpenWallet, onOpen, ratings, me }: {
  onBack: () => void;
  onOpenForecast: () => void;
  onOpenWallet: () => void;
  onOpen: (route: FoodRoute) => void;
  ratings: Record<string, RatingSummary>;
  me: FoodMe | null;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<VenueCategory>("all");
  const [wallets, setWallets] = useState<Account[]>([]);
  const [openNow, setOpenNow] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const location = useDeviceLocation();
  const budget = useDailyTargets();

  // Keep "open now" honest while the page stays open.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const origin = location.state.status === "ready" ? location.state.origin : null;
  const openCount = useMemo(
    () => visibleVenues(VENUES, { query: "", category: "all", wallets: [], openNow: true }, campusClock(now), null).length,
    [now]
  );
  const views = useMemo(
    () => visibleVenues(VENUES, { query, category, wallets, openNow }, campusClock(now), origin),
    [query, category, wallets, openNow, now, origin]
  );
  // Cover photos in list order, so neighbouring cards never share a photo.
  const covers = useMemo(
    () => coverPhotos(views.map(({ venue }) => ({ key: venue.id, categories: foodCategories(venueTexts(venue), venue.kind) }))),
    [views]
  );
  const targets = budget.status === "ready" ? budget.targets : null;
  const toggleWallet = (wallet: Account) => setWallets((current) => (current.includes(wallet) ? current.filter((w) => w !== wallet) : [...current, wallet]));
  const filtered = query !== "" || category !== "all" || wallets.length > 0 || openNow;
  const reset = () => {
    setQuery("");
    setCategory("all");
    setWallets([]);
    setOpenNow(false);
  };
  const problem = location.state.status === "denied" || location.state.status === "unavailable" || location.state.status === "timeout" || location.state.status === "unsupported" ? location.state.status : null;

  return (
    <section aria-labelledby="food-title" className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className="secondary-button" onClick={onBack}><ArrowLeft size={14} aria-hidden="true" /> Back to dashboard</button>
        {me?.is_moderator && <button type="button" className="secondary-button" onClick={() => onOpen({ page: "moderation" })}><ShieldCheck size={14} aria-hidden="true" /> Moderation</button>}
      </div>

      <header className="stage food-stage">
        <div>
          <p className="stage-eyebrow">Food Nearby</p>
          <h1 id="food-title" className="stage-title mt-4">Find your <em>next meal.</em></h1>
          <p className="stage-lede mt-4">Good food, student-friendly prices, and the right wallet — every campus dining spot and Triton Cash partner in one place.</p>
          <div className="food-search-row">
            <label className="food-search">
              <Search size={18} aria-hidden="true" />
              <span className="sr-only">Search food or places</span>
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search pizza, ramen, coffee, Price Center…" autoComplete="off" />
            </label>
            <button type="button" className="food-locate" onClick={location.locate} disabled={location.state.status === "locating"}>
              {location.state.status === "locating" ? <Loader2 size={17} className="animate-spin" aria-hidden="true" /> : <LocateFixed size={17} aria-hidden="true" />}
              {location.state.status === "locating" ? "Finding you…" : origin && location.state.status === "ready" && location.state.fromDevice ? "Update location" : "Use my current location"}
            </button>
          </div>
          <dl className="food-stage-stats">
            <div><dt className="sr-only">Places</dt><dd><strong>{VENUES.length}</strong> places to eat</dd></div>
            <div><dt className="sr-only">Open now</dt><dd><strong>{openCount}</strong> open right now</dd></div>
            <div><dt className="sr-only">Wallets</dt><dd><strong>2</strong> wallets compared</dd></div>
          </dl>
        </div>
        <FoodMosaic ids={["salmonPokeBowl", "tacos", "galaxySmoothieBowl", "gourmetPizza", "matchaBubbleTea"]} />
      </header>

      <div aria-live="polite">
        {location.state.status === "ready" && (
          <p className="food-location-note">
            <MapPin size={15} aria-hidden="true" /> Nearest first from {location.state.label}. Distances are straight-line, not walking routes.{" "}
            <button type="button" className="food-link" onClick={location.clear}>Stop using location</button>
          </p>
        )}
        {problem && (
          <div className="food-location-problem" role="status">
            <span>{LOCATION_PROBLEMS[problem]}</span>
            <div className="flex flex-wrap items-center gap-2">
              {problem !== "unsupported" && <button type="button" className="secondary-button" onClick={location.locate}>Try again</button>}
              <label className="food-landmark">
                <span className="sr-only">Pick a campus spot</span>
                <select defaultValue="" onChange={(event) => location.chooseLandmark(event.target.value)}>
                  <option value="" disabled>Pick a campus spot…</option>
                  {CAMPUS_LANDMARKS.map((landmark) => <option key={landmark.id} value={landmark.id}>{landmark.name}</option>)}
                </select>
              </label>
            </div>
          </div>
        )}
      </div>

      <div className="food-controls">
        <div className="scale-selector mb-0" role="group" aria-label="Category">
          {CATEGORIES.map((item) => <button key={item.value} type="button" className={`scale-button ${category === item.value ? "scale-button-selected" : ""}`} aria-pressed={category === item.value} onClick={() => setCategory(item.value)}>{item.label}</button>)}
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filters">
          {WALLETS.map((wallet) => (
            <button key={wallet} type="button" className={`food-filter ${wallets.includes(wallet) ? "food-filter-on" : ""}`} aria-pressed={wallets.includes(wallet)} onClick={() => toggleWallet(wallet)}>
              {wallets.includes(wallet) && <Check size={13} aria-hidden="true" />} {WALLET_LABELS[wallet]}
            </button>
          ))}
          <button type="button" className={`food-filter ${openNow ? "food-filter-on" : ""}`} aria-pressed={openNow} onClick={() => setOpenNow((value) => !value)} title="Only places with published hours that are open now">
            {openNow && <Check size={13} aria-hidden="true" />} Open now
          </button>
        </div>
      </div>

      <WalletSummary budget={budget} onOpenWallet={onOpenWallet} onOpenForecast={onOpenForecast} />

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-[var(--text)]" aria-live="polite">{views.length} {views.length === 1 ? "place" : "places"}</p>
        <p className="food-muted flex items-center gap-1.5"><Info size={13} aria-hidden="true" /> Curated from official UCSD sources, checked {formatCalendarDate(VENUES_VERIFIED_ON, { month: "short", day: "numeric", year: "numeric" })}. Not live.</p>
      </div>

      {views.length === 0 ? (
        <div className="empty-result">
          <div className="empty-icon"><Search size={24} aria-hidden="true" /></div>
          <h2>No places match.</h2>
          <p>{openNow ? "Nothing with published hours is open right now. " : ""}Try a different search or fewer filters.</p>
          {filtered && <button type="button" className="secondary-button mx-auto mt-4" onClick={reset}>Clear search and filters</button>}
        </div>
      ) : (
        <div className="food-grid">
          {views.map((view) => <VenueCard key={view.venue.id} view={view} preferred={wallets} targets={targets} rating={ratings[view.venue.id]} cover={covers[view.venue.id]} onOpen={onOpen} />)}
        </div>
      )}

      <details className="food-about">
        <summary>About this information</summary>
        <ul>
          <li>Wallet acceptance follows the official lists: Dining Dollars at HDH dining and markets only; Triton Cash at HDH plus listed partners. The partner list may not be complete, so a place missing here may still accept Triton Cash.</li>
          <li>Opening hours are HDH&apos;s published weekly hours. Other places&apos; hours aren&apos;t verified yet.</li>
          <li>Positions come from the official campus map. Off-campus places have no verified position, so no distance is shown.</li>
          <li>Your location stays on this device. It isn&apos;t sent to TritonSpend or saved.</li>
          <li>Food photos are illustrative, not menu items.</li>
        </ul>
        <p className="mt-2">
          Sources: {Object.values(VENUE_SOURCES).map((source, index) => <span key={source.url}>{index > 0 && " · "}<a className="food-link" href={source.url} target="_blank" rel="noreferrer">{source.label}</a></span>)}
        </p>
      </details>
    </section>
  );
}

/** Food Nearby: the venue directory, plus venue, station, dish and moderation pages (URL hash routes). */
export function FoodNearbyView({ onBack, onOpenForecast, onOpenWallet }: { onBack: () => void; onOpenForecast: () => void; onOpenWallet: () => void }) {
  const [route, go] = useFoodRoute();
  const [me, setMe] = useState<FoodMe | null>(null);
  const [ratings, setRatings] = useState<Record<string, RatingSummary>>({});

  useEffect(() => {
    // Both are optional extras: the directory works without them.
    readFoodMe().then(setMe).catch(() => setMe(null));
  }, []);
  useEffect(() => {
    if (route.page !== "list") return;
    let active = true;
    readFoodVenues()
      .then((data) => active && setRatings(Object.fromEntries(data.venues.map((venue) => [venue.id, venue.rating]))))
      .catch(() => active && setRatings({}));
    return () => { active = false; };
  }, [route.page]);

  if (route.page === "list") {
    return <VenueDirectory onBack={onBack} onOpenForecast={onOpenForecast} onOpenWallet={onOpenWallet} onOpen={go} ratings={ratings} me={me} />;
  }
  return (
    <section className="space-y-5" aria-label="Food Nearby">
      <button type="button" className="secondary-button" onClick={() => window.history.length > 1 ? window.history.back() : go({ page: "list" })}>
        <ArrowLeft size={14} aria-hidden="true" /> Back
      </button>
      {route.page === "venue" && <VenuePage venueId={route.venueId} me={me} onOpen={go} />}
      {route.page === "station" && <StationPage stationId={route.stationId} onOpen={go} />}
      {route.page === "dish" && <DishPage itemId={route.itemId} me={me} onOpen={go} />}
      {route.page === "moderation" && <ModerationPage me={me} onOpen={go} />}
    </section>
  );
}
