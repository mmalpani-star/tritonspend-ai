"use client";

import { ArrowLeft, Check, ChevronRight, Clock, ExternalLink, HelpCircle, MapPin, ShieldCheck, Store, UtensilsCrossed, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  moderateContent,
  readFoodStation,
  readFoodVenue,
  readMenuItem,
  readModerationHistory,
  readModerationQueue,
  readStationMenu,
  settleReport
} from "../../lib/api";
import {
  FoodMe,
  FoodRoute,
  FoodStationDetail,
  FoodVenueDetail,
  MenuItemDetail,
  ModerationAction,
  ModerationReport,
  REPORT_REASONS,
  StationMenu
} from "../../lib/food-chat";
import { WALLET_LABELS, campusClock, describeOpenState, formatHours, openState, DAY_KEYS } from "../../lib/food-venues";
import type { Account } from "../../lib/types";
import { FavoriteButton } from "../account/favorites";
import { VenueChat, VenueRatingBar } from "./food-chat";
import { StationBanner, VenueBanner } from "./food-media";
import { OfficialMenuLink, when } from "./food-ui";
import { EXTERNAL_LINK, MenuLink, stationMenuLink, venueMenuLink, venueScopeNote } from "../../lib/menu-links";

export type Load<T> = { status: "loading" } | { status: "error"; text: string; notFound: boolean } | { status: "ready"; data: T };
const SHORT_DAY: Record<string, string> = { sun: "Sun", mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat" };
const STATUS_ICON = { accepted: Check, not_accepted: X, not_verified: HelpCircle } as const;
const STATUS_TEXT = { accepted: "accepted", not_accepted: "not accepted", not_verified: "not verified" } as const;

export function useLoad<T>(loader: () => Promise<T>, key: string): [Load<T>, () => void] {
  const [state, setState] = useState<Load<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    loader()
      .then((data) => active && setState({ status: "ready", data }))
      .catch((failure) => active && setState({
        status: "error",
        text: failure instanceof Error ? failure.message : "Something went wrong.",
        notFound: (failure as { status?: number }).status === 404
      }));
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when the key (the record) changes
  }, [key, attempt]);
  return [state, () => setAttempt((value) => value + 1)];
}

export function LoadState<T>({ state, retry, what }: { state: Load<T>; retry: () => void; what: string }) {
  if (state.status === "loading") return <div className="panel"><p className="food-muted">Loading {what}…</p></div>;
  if (state.status === "error") {
    return (
      <div className="panel" role="alert">
        <p className="error-box">{state.notFound ? `We couldn't find that ${what}.` : state.text}</p>
        {!state.notFound && <button type="button" className="secondary-button mt-3" onClick={retry}>Try again</button>}
      </div>
    );
  }
  return null;
}

function Crumbs({ items, onOpen }: { items: { label: string; route?: FoodRoute }[]; onOpen: (route: FoodRoute) => void }) {
  return (
    <nav aria-label="Breadcrumb" className="food-crumbs">
      <ol>
        {items.map((item, index) => (
          <li key={item.label + index}>
            {item.route ? <button type="button" className="food-link" onClick={() => onOpen(item.route!)}>{item.label}</button> : <span aria-current="page">{item.label}</span>}
            {index < items.length - 1 && <ChevronRight size={14} aria-hidden="true" />}
          </li>
        ))}
      </ol>
    </nav>
  );
}

// --- Venue ---------------------------------------------------------------------------------------

export function VenuePage({ venueId, me, onOpen }: { venueId: string; me: FoodMe | null; onOpen: (route: FoodRoute) => void }) {
  const [state, retry] = useLoad(() => readFoodVenue(venueId), venueId);
  if (state.status !== "ready") return <><Crumbs items={[{ label: "Food Nearby", route: { page: "list" } }, { label: "Venue" }]} onOpen={onOpen} /><LoadState state={state} retry={retry} what="venue" /></>;
  const venue: FoodVenueDetail = state.data;
  const open = openState(venue.hours, campusClock(new Date()));
  const menuLink = venueMenuLink({ name: venue.name, operator: venue.operator, menuUrl: venue.menu_url });
  const stationLinks = venue.stations.map((station) => stationMenuLink(station, venue));
  const sharedMenu = stationLinks.find((link) => link?.scope === "venue");
  return (
    <div className="space-y-5">
      <Crumbs items={[{ label: "Food Nearby", route: { page: "list" } }, { label: venue.name }]} onOpen={onOpen} />
      <VenueBanner placeKey={venue.id} texts={[venue.name, venue.summary, venue.description, ...venue.tags, ...venue.stations.map((station) => station.name)]} kind={venue.kind} />
      <header className="panel food-venue-header">
        <p className="eyebrow">{venue.operator === "hdh" ? (venue.kind === "market" ? "Campus market" : "Campus dining") : "Triton Cash merchant"}</p>
        <div className="food-title-row">
          <h1 className="food-hero-title text-[var(--text)]">{venue.name}</h1>
          <FavoriteButton kind="venue" id={venue.id} name={venue.name} withLabel />
        </div>
        <VenueRatingBar venueId={venue.id} venueName={venue.name} me={me} />
        {venue.summary && <p className="food-muted text-base">{venue.summary}</p>}
        <p className="food-card-line"><MapPin size={15} aria-hidden="true" /> {[venue.location, venue.campus_area].filter(Boolean).join(" · ") || (venue.on_campus ? "On campus" : "Off campus")}</p>
        <p className={`food-card-line food-open-${open.status}`}><Clock size={15} aria-hidden="true" /> {describeOpenState(open)}</p>
        <div className="flex flex-wrap gap-1.5">
          {(["dining_dollars", "triton_cash"] as Account[]).map((wallet) => {
            const status = venue.wallets[wallet].status;
            const Icon = STATUS_ICON[status];
            return <span key={wallet} className={`food-pill food-pill-${status}`} title={venue.wallets[wallet].reason}><Icon size={13} aria-hidden="true" />{WALLET_LABELS[wallet]}<span className="sr-only"> {STATUS_TEXT[status]}</span></span>;
          })}
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          {menuLink && <OfficialMenuLink link={menuLink} />}
          {venue.website_url && <a className="food-link" href={venue.website_url} {...EXTERNAL_LINK}>Website <ExternalLink size={13} aria-hidden="true" /></a>}
        </div>
        {venue.hours && (
          <details className="food-details">
            <summary>Weekly hours</summary>
            <table className="food-hours"><tbody>
              {[...DAY_KEYS.slice(1), DAY_KEYS[0]].map((day) => <tr key={day}><th scope="row">{SHORT_DAY[day]}</th><td>{formatHours(venue.hours![day])}</td></tr>)}
            </tbody></table>
            <p className="food-muted">HDH&apos;s published weekly hours, checked {venue.verified_on}. Holiday hours can differ.</p>
          </details>
        )}
      </header>

      <VenueChat venueId={venue.id} venueName={venue.name} me={me} />

      <section className="panel" aria-labelledby="stations-title">
        <p className="eyebrow">Stations</p>
        <h2 id="stations-title" className="panel-title">{venue.stations.length ? `${venue.stations.length} stations` : "Stations"}</h2>
        {sharedMenu && (
          <p className="food-muted mt-1 text-sm">Stations don&apos;t have their own official menu pages. &ldquo;{sharedMenu.label}&rdquo; opens HDH&apos;s official page for all of {venue.name} in a new tab.</p>
        )}
        {venue.stations.length === 0 ? (
          <p className="food-muted mt-2">No stations are listed for this venue.</p>
        ) : (
          <ul className="food-station-grid">
            {venue.stations.map((station, index) => (
              <li key={station.id} className="food-station-row">
                <button type="button" className="food-station-card" onClick={() => onOpen({ page: "station", stationId: station.id })}>
                  <span className="food-card-icon"><UtensilsCrossed size={17} aria-hidden="true" /></span>
                  <span className="min-w-0 flex-1 text-left">
                    <strong>{station.name}</strong>
                    <span className="food-muted block">{station.menu_item_count ? `${station.menu_item_count} verified menu items` : "No dishes listed here yet"}</span>
                  </span>
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
                {stationLinks[index] && <OfficialMenuLink link={stationLinks[index]!} />}
              </li>
            ))}
          </ul>
        )}
      </section>

    </div>
  );
}

// --- Station -------------------------------------------------------------------------------------

export function StationPage({ stationId, onOpen }: { stationId: string; onOpen: (route: FoodRoute) => void }) {
  const [station, retryStation] = useLoad(() => readFoodStation(stationId), stationId);
  const [menu, retryMenu] = useLoad(() => readStationMenu(stationId), stationId);
  if (station.status !== "ready") return <><Crumbs items={[{ label: "Food Nearby", route: { page: "list" } }, { label: "Station" }]} onOpen={onOpen} /><LoadState state={station} retry={retryStation} what="station" /></>;
  const value: FoodStationDetail = station.data;
  const menuLink = stationMenuLink(value, value.venue);
  const scopeNote = menuLink ? venueScopeNote(menuLink, value.venue.name, value.name) : null;
  return (
    <div className="space-y-5">
      <Crumbs items={[{ label: "Food Nearby", route: { page: "list" } }, { label: value.venue.name, route: { page: "venue", venueId: value.venue.id } }, { label: value.name }]} onOpen={onOpen} />
      <StationBanner placeKey={value.id} texts={[value.name, value.venue.name]} />
      <header className="panel">
        <p className="eyebrow">Station at {value.venue.name}</p>
        <h1 className="food-hero-title text-[var(--text)]">{value.name}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          {menuLink
            ? <OfficialMenuLink link={menuLink} prominent />
            : <span className="food-muted">No official menu link is available for this station.</span>}
          <button type="button" className="secondary-button" onClick={() => onOpen({ page: "venue", venueId: value.venue.id })}><ArrowLeft size={14} aria-hidden="true" /> {value.venue.name}</button>
        </div>
        {scopeNote && <p className="food-muted mt-2 text-sm">{scopeNote}</p>}
      </header>
      <section className="panel" aria-labelledby="menu-title">
        <p className="eyebrow">Menu</p>
        <h2 id="menu-title" className="panel-title">Dishes</h2>
        {menu.status === "loading" && <p className="food-muted">Loading the menu…</p>}
        {menu.status === "error" && <p role="alert" className="error-box">{menu.text} <button type="button" className="food-link" onClick={retryMenu}>Try again</button></p>}
        {menu.status === "ready" && <MenuList menu={menu.data} venue={value.venue} menuLink={menuLink} onOpen={onOpen} />}
      </section>
    </div>
  );
}

function MenuList({ menu, venue, menuLink, onOpen }: { menu: StationMenu; venue: { id: string; name: string }; menuLink: MenuLink | null; onOpen: (route: FoodRoute) => void }) {
  if (menu.menu_status === "no_verified_menu_data" || menu.items.length === 0) {
    return (
      <div className="empty-result mt-3">
        <div className="empty-icon"><Store size={24} aria-hidden="true" /></div>
        <h3>No verified menu items yet</h3>
        <p>TritonSpend only lists dishes from a verified menu source, so this station&apos;s dishes and prices aren&apos;t shown yet. Talk about any dish here in the {venue.name} chat.{menuLink && " See what's served today on the official menu."}</p>
        <div className="mx-auto mt-4 flex flex-wrap justify-center gap-3">
          {menuLink && <OfficialMenuLink link={menuLink} />}
          <button type="button" className="secondary-button" onClick={() => onOpen({ page: "venue", venueId: venue.id })}>Review {venue.name} overall</button>
        </div>
      </div>
    );
  }
  return (
    <ul className="food-menu-list">
      {menu.items.map((item) => (
        <li key={item.id} className="food-menu-row">
          <button type="button" className="food-menu-item" onClick={() => onOpen({ page: "dish", itemId: item.id })}>
            <span className="min-w-0 flex-1 text-left">
              <strong>{item.name}</strong>
              {item.description && <span className="food-muted block">{item.description}</span>}
              {item.dietary_labels && item.dietary_labels.length > 0 && <span className="food-tags">{item.dietary_labels.join(" · ")}</span>}
            </span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
          <FavoriteButton kind="dish" id={item.id} name={item.name} />
        </li>
      ))}
    </ul>
  );
}

// --- Dish ----------------------------------------------------------------------------------------

export function DishPage({ itemId, me, onOpen }: { itemId: string; me: FoodMe | null; onOpen: (route: FoodRoute) => void }) {
  const [state, retry] = useLoad(() => readMenuItem(itemId), itemId);
  if (state.status !== "ready") return <><Crumbs items={[{ label: "Food Nearby", route: { page: "list" } }, { label: "Dish" }]} onOpen={onOpen} /><LoadState state={state} retry={retry} what="dish" /></>;
  const item: MenuItemDetail = state.data;
  return (
    <div className="space-y-5">
      <Crumbs items={[
        { label: "Food Nearby", route: { page: "list" } },
        { label: item.venue.name, route: { page: "venue", venueId: item.venue.id } },
        { label: item.station.name, route: { page: "station", stationId: item.station.id } },
        { label: item.name }
      ]} onOpen={onOpen} />
      <header className="panel">
        <p className="eyebrow">{item.station.name} · {item.venue.name}</p>
        <div className="food-title-row">
          <h1 className="food-hero-title text-[var(--text)]">{item.name}</h1>
          {item.is_active && <FavoriteButton kind="dish" id={item.id} name={item.name} withLabel />}
        </div>
        {item.description && <p className="food-muted text-base">{item.description}</p>}
        {item.dietary_labels && item.dietary_labels.length > 0 && <p className="food-tags mt-2">{item.dietary_labels.join(" · ")}</p>}
        <p className="food-muted mt-2">Listed on a verified menu. Being listed doesn&apos;t mean it&apos;s available right now. <a className="food-link" href={item.source_url} target="_blank" rel="noreferrer">Menu source</a></p>
      </header>
      <p className="notice-info text-sm">
        Talk about this dish in the{" "}
        <button type="button" className="food-link" onClick={() => onOpen({ page: "venue", venueId: item.venue.id })}>{item.venue.name} chat</button>.
      </p>
    </div>
  );
}

// --- Moderation ----------------------------------------------------------------------------------

export function ModerationPage({ me, onOpen }: { me: FoodMe | null; onOpen: (route: FoodRoute) => void }) {
  const [filter, setFilter] = useState<"open" | "all">("open");
  const [queue, retry] = useLoad(() => readModerationQueue(filter), filter);
  const [history, retryHistory] = useLoad(() => readModerationHistory(), filter);
  if (me && !me.is_moderator) {
    return <div className="panel"><p className="error-box">Only Food Chat moderators can open this page.</p></div>;
  }
  const refresh = () => { retry(); retryHistory(); };
  return (
    <div className="space-y-5">
      <Crumbs items={[{ label: "Food Nearby", route: { page: "list" } }, { label: "Moderation" }]} onOpen={onOpen} />
      <header className="panel">
        <p className="eyebrow"><ShieldCheck size={13} aria-hidden="true" /> Moderators</p>
        <h1 className="food-hero-title text-[var(--text)]">Food Chat reports</h1>
        <div className="scale-selector mt-3 mb-0 w-fit" role="group" aria-label="Which reports">
          {(["open", "all"] as const).map((value) => (
            <button key={value} type="button" className={`scale-button ${filter === value ? "scale-button-selected" : ""}`} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value === "open" ? "Open" : "All"}</button>
          ))}
        </div>
      </header>
      {queue.status !== "ready" ? <LoadState state={queue} retry={retry} what="reports" /> : queue.data.reports.length === 0 ? (
        <div className="panel"><p className="food-muted">{filter === "open" ? "No open reports. Nice." : "No reports yet."}</p></div>
      ) : (
        <ul className="space-y-3">
          {queue.data.reports.map((report) => <ReportCard key={`${report.id}-${report.status}-${report.content.moderation_state}`} report={report} onDone={refresh} onOpen={onOpen} />)}
        </ul>
      )}
      <section className="panel" aria-labelledby="history-title">
        <h2 id="history-title" className="panel-title text-xl">Recent moderation</h2>
        {history.status === "ready" && history.data.actions.length === 0 && <p className="food-muted mt-2">No moderation actions yet.</p>}
        {history.status === "ready" && history.data.actions.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {history.data.actions.map((action: ModerationAction) => (
              <li key={action.id}><strong>{action.moderator_name}</strong> · {action.action.replace("_", " ")} {action.target_type} · {when(action.created_at)}{action.note ? ` · “${action.note}”` : ""}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ReportCard({ report, onDone, onOpen }: { report: ModerationReport; onDone: () => void; onOpen: (route: FoodRoute) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { content } = report;
  const reason = REPORT_REASONS.find((option) => option.value === report.reason)?.label ?? report.reason;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "That didn't work.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="panel food-report" aria-label={`Report: ${reason}`}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="feature-badge">{report.status}</span>
        <strong>{reason}</strong>
        <span className="food-muted">reported {when(report.created_at)} · {report.open_reports_on_target} open report{report.open_reports_on_target === 1 ? "" : "s"} on this {content.kind}</span>
      </div>
      {report.details && <p className="mt-2 text-sm">“{report.details}”</p>}
      <blockquote className="food-reported">
        <p className="food-muted text-xs">{content.kind === "message" ? "Chat message" : content.kind === "review" ? `Earlier review${content.rating ? ` (${content.rating}★)` : ""}` : "Earlier comment"} by {content.author_name} on <button type="button" className="food-link" onClick={() => onOpen({ page: "venue", venueId: content.venue.id })}>{content.venue.name}</button> · currently <strong>{content.moderation_state}</strong></p>
        <p>{content.body}</p>
      </blockquote>
      <label className="field-label mt-3">Note (optional)
        <input value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        {content.moderation_state !== "hidden" && <button type="button" className="secondary-button" disabled={busy} onClick={() => void run(() => moderateContent(content.kind, content.id, "hide", note))}>Hide {content.kind}</button>}
        {content.moderation_state !== "visible" && <button type="button" className="secondary-button" disabled={busy} onClick={() => void run(() => moderateContent(content.kind, content.id, "restore", note))}>Restore</button>}
        {content.moderation_state !== "removed" && <button type="button" className="secondary-button danger-button" disabled={busy} onClick={() => void run(() => moderateContent(content.kind, content.id, "remove", note))}>Remove</button>}
        {report.status === "open" && <button type="button" className="primary-button" disabled={busy} onClick={() => void run(() => settleReport(report.id, "resolve", note))}>Resolve report</button>}
        {report.status === "open" && <button type="button" className="secondary-button" disabled={busy} onClick={() => void run(() => settleReport(report.id, "dismiss", note))}>Dismiss</button>}
      </div>
      {error && <p role="alert" className="error-box mt-3">{error}</p>}
    </li>
  );
}
