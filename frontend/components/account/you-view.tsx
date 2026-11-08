"use client";

import {
  ArrowLeft, ChevronRight, ExternalLink, Heart, Lock, MessagesSquare, Palette, Pencil, ShieldCheck, Star, Store, Trash2,
  UserRound, Wallet
} from "lucide-react";
import { useEffect, useState } from "react";
import { deleteVenueMessage, editVenueMessage, readAccountSummary, readFoodMe, readMyMessages, readMyRatings } from "../../lib/api";
import {
  AccountSummary, FavoriteDish, FavoriteVenue, Favorites, MyMessage, PAGE_TITLES, YouPage, countLabel, parseYouPage, youPageHash
} from "../../lib/account";
import { formatTimestamp } from "../../lib/datetime";
import { FoodMe, FoodRoute, MAX_MESSAGE_LENGTH, formatAverage, formatVenueAverage, foodRouteHash, messageError, ratedByLabel, reviewCountLabel } from "../../lib/food-chat";
import { THEMES } from "../../lib/theme";
import { ConfirmDialog } from "../confirm-dialog";
import { LoadState, useLoad } from "../food/food-pages";
import { Stars, StatusLine, when } from "../food/food-ui";
import { THEME_LABELS } from "../theme-switcher";
import { useTheme } from "../theme-provider";
import { DataControls } from "../wallet-alerts-view";
import { useFavorites } from "./favorites";

type Status = { error: boolean; text: string } | null;
const message = (failure: unknown, fallback: string) => (failure instanceof Error ? failure.message : fallback);

/** Opens a Food Nearby page (venue, station, dish) from anywhere in the app. */
function openFood(route: FoodRoute) {
  window.location.hash = foodRouteHash(route);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openYou(page: YouPage) {
  window.location.hash = youPageHash(page);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/** The current "You" page, kept in the URL hash (#you/<page>) so links, refresh and Back work. */
export function useYouPage(): YouPage | null {
  const [page, setPage] = useState<YouPage | null>(null);
  useEffect(() => {
    const sync = () => setPage(parseYouPage(window.location.hash));
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  return page;
}

function Empty({ icon: Icon, title, children, action }: { icon: typeof Heart; title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="empty-result">
      <div className="empty-icon"><Icon size={24} aria-hidden="true" /></div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

const browseFood = <button type="button" className="secondary-button" onClick={() => openFood({ page: "list" })}><Store size={15} aria-hidden="true" /> Browse Food Nearby</button>;

// --- Your Account --------------------------------------------------------------------------------

function Fact({ label, children, note }: { label: string; children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="you-fact">
      <dt>{label}</dt>
      <dd>{children}{note && <span className="you-fact-note">{note}</span>}</dd>
    </div>
  );
}

function AccountPage({ onOpenWallet }: { onOpenWallet: () => void }) {
  const [state, retry] = useLoad(readAccountSummary, "account");
  if (state.status !== "ready") return <LoadState state={state} retry={retry} what="account" />;
  const account: AccountSummary = state.data;
  const activity: { page: YouPage; count: number; one: string; many: string; Icon: typeof Heart }[] = [
    { page: "ratings", count: account.activity.ratings, one: "venue rating", many: "venue ratings", Icon: Star },
    { page: "messages", count: account.activity.messages, one: "chat message", many: "chat messages", Icon: MessagesSquare },
    { page: "favourite-venues", count: account.activity.favorite_venues, one: "favourite venue", many: "favourite venues", Icon: Store },
    { page: "favourite-dishes", count: account.activity.favorite_dishes, one: "favourite dish", many: "favourite dishes", Icon: Heart }
  ];
  return (
    <div className="space-y-6">
      <section className="panel" aria-labelledby="account-details-title">
        <p className="eyebrow">Account</p>
        <h2 id="account-details-title" className="panel-title">Account details</h2>
        <dl className="you-facts">
          <Fact label="Email" note={<><Lock size={12} aria-hidden="true" /> Private. Only you can see it; it&apos;s never shown in Food Chat.</>}>{account.email ?? "No email on this account"}</Fact>
          <Fact label="Food Chat name" note="Shown on your reviews and comments instead of your email. It's generated for you and can't be changed.">
            {account.display_name ?? <span className="food-muted">Assigned once you accept the consent document</span>}
          </Fact>
          <Fact label="Member since">{formatTimestamp(account.account_created_at)}</Fact>
          <Fact label="Last sign-in">{account.last_login_at ? formatTimestamp(account.last_login_at) : "Not recorded"}</Fact>
          <Fact label="Time zone">{account.timezone}</Fact>
          <Fact label="Consent">
            {account.consent.active ? (
              <>Accepted{account.consent.version ? ` (${account.consent.version})` : ""}{account.consent.accepted_at ? ` on ${formatTimestamp(account.consent.accepted_at)}` : ""}
                {account.consent.document_url && <> · <a className="food-link" href={account.consent.document_url} target="_blank" rel="noreferrer">Read it <ExternalLink size={12} aria-hidden="true" /></a></>}
              </>
            ) : "Not accepted. Accept it at the top of the page to save data and post in Food Chat."}
          </Fact>
          {account.is_moderator && (
            <Fact label="Role">Food Chat moderator · <button type="button" className="food-link" onClick={() => openFood({ page: "moderation" })}>Open moderation</button></Fact>
          )}
        </dl>
      </section>

      <section className="panel" aria-labelledby="account-activity-title">
        <p className="eyebrow">Activity</p>
        <h2 id="account-activity-title" className="panel-title">Your TritonSpend at a glance</h2>
        <ul className="you-stat-grid">
          {activity.map((item) => (
            <li key={item.page}>
              <button type="button" className="you-stat" onClick={() => openYou(item.page)}>
                <item.Icon size={18} aria-hidden="true" />
                <span><strong>{item.count}</strong> <span className="food-muted">{item.count === 1 ? item.one : item.many}</span></span>
                <ChevronRight size={15} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-5 flex flex-wrap gap-2">
          <button type="button" className="secondary-button" onClick={onOpenWallet}><Wallet size={15} aria-hidden="true" /> Wallet &amp; Alerts</button>
          <button type="button" className="secondary-button" onClick={() => openYou("settings")}><ShieldCheck size={15} aria-hidden="true" /> Download or delete your data</button>
        </div>
      </section>
    </div>
  );
}

// --- Favourites ----------------------------------------------------------------------------------

function FavoritesLoad({ what, render }: { what: string; render: (favorites: Favorites) => React.ReactNode }) {
  const favorites = useFavorites();
  if (!favorites) return null;
  if (favorites.error && !favorites.favorites) {
    return (
      <div className="panel" role="alert">
        <p className="error-box">{favorites.error}</p>
        <button type="button" className="secondary-button mt-3" onClick={() => void favorites.reload()}>Try again</button>
      </div>
    );
  }
  if (!favorites.favorites) return <div className="panel"><p className="food-muted">Loading your {what}…</p></div>;
  return <>{render(favorites.favorites)}</>;
}

function RemoveFavorite({ kind, id, name }: { kind: "venue" | "dish"; id: string; name: string }) {
  const favorites = useFavorites();
  const [problem, setProblem] = useState("");
  if (!favorites) return null;
  return (
    <>
      <button type="button" className="food-action food-action-danger" disabled={favorites.isPending(kind, id)} aria-label={`Remove ${name} from favourites`}
        onClick={() => { setProblem(""); favorites.toggle(kind, id).catch((failure) => setProblem(message(failure, "Couldn't remove this favourite."))); }}>
        <Heart size={14} aria-hidden="true" fill="currentColor" /> {favorites.isPending(kind, id) ? "Removing…" : "Remove"}
      </button>
      {problem && <p role="alert" className="error-box mt-2 w-full">{problem}</p>}
    </>
  );
}

function RatingText({ rating }: { rating: { review_count: number; average_rating: number | null } }) {
  return (
    <span className="food-rating-line">
      <Stars value={rating.average_rating} size={14} />
      <span className="food-muted">{rating.review_count ? `${formatAverage(rating)} · ${reviewCountLabel(rating.review_count)}` : "No reviews yet"}</span>
    </span>
  );
}

function FavouriteDishesPage() {
  return (
<FavoritesLoad what="favourite dishes" render={(favorites) => <DishList dishes={favorites.dishes} />} />
  );
}

function DishList({ dishes }: { dishes: FavoriteDish[] }) {
  if (dishes.length === 0) {
    return (
      <div className="panel">
        <Empty icon={Heart} title="No favourite dishes yet" action={browseFood}>
          Save a dish with the heart on its page and it shows up here. TritonSpend only lists dishes from verified menus, and most stations don&apos;t have verified dishes yet, so there may be nothing to save for now.
        </Empty>
      </div>
    );
  }
  return (
    <ul className="you-list" aria-label="Favourite dishes">
      {dishes.map((dish) => (
        <li key={dish.id} className="you-card">
          <div className="min-w-0 flex-1">
            <button type="button" className="food-card-title-link you-card-title" onClick={() => openFood({ page: "dish", itemId: dish.id })}>{dish.name}</button>
            <p className="food-muted text-sm">{dish.station.name} · {dish.venue.name}</p>
            {dish.description && <p className="food-muted text-sm">{dish.description}</p>}
            {!dish.is_active && <p className="notice-info mt-2 text-sm">No longer on a verified menu.</p>}
            <p className="food-muted mt-1 text-xs">Saved {when(dish.saved_at)}</p>
          </div>
          <div className="you-card-actions">
            <button type="button" className="food-action" onClick={() => openFood({ page: "dish", itemId: dish.id })}>Open <ChevronRight size={14} aria-hidden="true" /></button>
            <RemoveFavorite kind="dish" id={dish.id} name={dish.name} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** "Stewart Commons · Revelle", skipping parts that just repeat the venue's name. */
const placeLine = (venue: FavoriteVenue) => [venue.location, venue.campus_area].filter((part) => part && part !== venue.name).join(" · ");

function FavouriteVenuesPage() {
  return (
<FavoritesLoad what="favourite venues" render={(favorites) => <VenueList venues={favorites.venues} />} />
  );
}

function VenueList({ venues }: { venues: FavoriteVenue[] }) {
  if (venues.length === 0) {
    return (
      <div className="panel">
        <Empty icon={Store} title="No favourite venues yet" action={browseFood}>
          Tap the heart on any venue in Food Nearby to keep it here for quick access.
        </Empty>
      </div>
    );
  }
  return (
    <ul className="you-list" aria-label="Favourite venues">
      {venues.map((venue) => (
        <li key={venue.id} className="you-card">
          <div className="min-w-0 flex-1">
            <button type="button" className="food-card-title-link you-card-title" onClick={() => openFood({ page: "venue", venueId: venue.id })}>{venue.name}</button>
            {placeLine(venue) && <p className="food-muted text-sm">{placeLine(venue)}</p>}
            <RatingText rating={venue.rating} />
            {!venue.is_active && <p className="notice-info mt-2 text-sm">This venue is no longer listed in Food Nearby.</p>}
            <p className="food-muted mt-1 text-xs">Saved {when(venue.saved_at)}</p>
          </div>
          <div className="you-card-actions">
            {venue.is_active && <button type="button" className="food-action" onClick={() => openFood({ page: "venue", venueId: venue.id })}>Ratings, chat &amp; stations <ChevronRight size={14} aria-hidden="true" /></button>}
            <RemoveFavorite kind="venue" id={venue.id} name={venue.name} />
          </div>
        </li>
      ))}
    </ul>
  );
}

// --- Your Ratings --------------------------------------------------------------------------------

function useFoodMe(): FoodMe | null {
  const [me, setMe] = useState<FoodMe | null>(null);
  useEffect(() => { readFoodMe().then(setMe).catch(() => setMe(null)); }, []);
  return me;
}

function RatingsPage() {
  const [state, retry] = useLoad(readMyRatings, "ratings");
  if (state.status !== "ready") return <LoadState state={state} retry={retry} what="ratings" />;
  const { ratings } = state.data;
  if (ratings.length === 0) {
    return (
      <div className="panel">
        <Empty icon={Star} title="You haven't rated any venues yet" action={browseFood}>
          Open a venue in Food Nearby and tap the stars. You can change your rating any time.
        </Empty>
      </div>
    );
  }
  return (
    <ul className="you-list" aria-label="Your venue ratings">
      {ratings.map((item) => (
        <li key={item.venue.id} className="you-card">
          <div className="min-w-0 flex-1">
            <button type="button" className="food-card-title-link you-card-title" onClick={() => openFood({ page: "venue", venueId: item.venue.id })}>{item.venue.name}</button>
            <p className="food-rating-line mt-1"><span className="food-muted">You:</span> <Stars value={item.rating} size={15} label={`Your rating: ${item.rating} out of 5`} /></p>
            <p className="food-muted text-sm">Everyone: {formatVenueAverage({ average_rating: item.venue_average, rating_count: item.venue_rating_count })}{item.venue_rating_count ? ` · ${ratedByLabel(item.venue_rating_count)}` : ""}</p>
            <p className="food-muted mt-1 text-xs">Updated {when(item.updated_at)}</p>
          </div>
          <div className="you-card-actions">
            <button type="button" className="food-action" onClick={() => openFood({ page: "venue", venueId: item.venue.id })}>Change rating <ChevronRight size={14} aria-hidden="true" /></button>
          </div>
        </li>
      ))}
    </ul>
  );
}

// --- Your Messages -------------------------------------------------------------------------------

function MessageItem({ item, canPost, onChanged }: { item: MyMessage; canPost: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.body);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const hidden = item.moderation_state !== "visible";

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const problem = messageError(text);
    if (problem) return setStatus({ error: true, text: problem });
    setBusy(true);
    try {
      await editVenueMessage(item.id, text);
      setEditing(false);
      onChanged();
    } catch (failure) {
      setStatus({ error: true, text: message(failure, "Couldn't save your message.") });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteVenueMessage(item.id);
      setConfirmDelete(false);
      onChanged();
    } catch (failure) {
      setConfirmDelete(false);
      setStatus({ error: true, text: message(failure, "Couldn't delete your message.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="you-card you-message">
      <div className="min-w-0 flex-1">
        <p className="food-muted text-xs">
          <button type="button" className="food-link" onClick={() => openFood({ page: "venue", venueId: item.venue.id })}>{item.venue.name} chat</button>
          {" "}· {when(item.created_at)}{item.edited ? " · edited" : ""}
        </p>
        {hidden && <p className="notice-info mt-2 text-sm">A moderator {item.moderation_state === "hidden" ? "hid" : "removed"} this message; only you can see it.</p>}
        {editing ? (
          <form onSubmit={save} className="chat-edit mt-2">
            <label className="sr-only" htmlFor={`mine-${item.id}`}>Edit your message</label>
            <textarea id={`mine-${item.id}`} rows={2} maxLength={MAX_MESSAGE_LENGTH} value={text} onChange={(event) => setText(event.target.value)} />
            <div className="flex gap-2">
              <button type="submit" className="primary-button" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
              <button type="button" className="secondary-button" onClick={() => { setEditing(false); setText(item.body); }}>Cancel</button>
            </div>
          </form>
        ) : (
          <p className="chat-body mt-1">{item.body}</p>
        )}
        <StatusLine status={status} />
      </div>
      {canPost && !editing && (
        <div className="you-card-actions">
          {!hidden && <button type="button" className="food-action" onClick={() => setEditing(true)}><Pencil size={14} aria-hidden="true" /> Edit</button>}
          <button type="button" className="food-action food-action-danger" onClick={() => setConfirmDelete(true)}><Trash2 size={14} aria-hidden="true" /> Delete</button>
        </div>
      )}
      <ConfirmDialog open={confirmDelete} title="Delete your message?" confirmLabel="Delete message" busy={busy} onConfirm={() => void remove()} onCancel={() => setConfirmDelete(false)}>
        This permanently deletes your message from the {item.venue.name} chat. It can&apos;t be undone.
      </ConfirmDialog>
    </li>
  );
}

function MessagesPage() {
  const [version, setVersion] = useState(0);
  const [state, retry] = useLoad(readMyMessages, `messages-${version}`);
  const me = useFoodMe();
  if (state.status !== "ready") return <LoadState state={state} retry={retry} what="messages" />;
  const { messages, total } = state.data;
  if (messages.length === 0) {
    return (
      <div className="panel">
        <Empty icon={MessagesSquare} title="No chat messages yet" action={browseFood}>
          Every venue in Food Nearby has its own chat. Your messages will be listed here.
        </Empty>
      </div>
    );
  }
  return (
    <section className="space-y-3" aria-label="Your chat messages">
      <p className="food-muted text-sm">{countLabel(total, "message")}, newest first.</p>
      <ul className="you-list">
        {messages.map((item) => (
          <MessageItem key={`${item.id}-${item.updated_at}`} item={item} canPost={Boolean(me?.consent_active)} onChanged={() => setVersion((value) => value + 1)} />
        ))}
      </ul>
      {total > messages.length && <p className="food-muted text-sm">Showing your {messages.length} newest messages.</p>}
    </section>
  );
}

// --- Settings ------------------------------------------------------------------------------------

function SettingsPage({ onOpenWallet }: { onOpenWallet: () => void }) {
  const { theme, setTheme } = useTheme();
  return (
    <div className="space-y-6">
      <section className="panel" aria-labelledby="appearance-title">
        <p className="eyebrow">Appearance</p>
        <h2 id="appearance-title" className="panel-title">Theme</h2>
        <p className="mt-2 text-sm text-[var(--text-muted)]">Saved on this device. The slider in the header changes the same setting.</p>
        <div role="radiogroup" aria-label="Color theme" className="you-theme-grid">
          {THEMES.map((value) => (
            <label key={value} className={`you-theme ${theme === value ? "you-theme-on" : ""}`} data-preview={value}>
              <input type="radio" name="settings-theme" value={value} checked={theme === value} onChange={() => setTheme(value)} className="sr-only" />
              <span className="you-theme-swatch" aria-hidden="true" />
              <span><strong>{THEME_LABELS[value].full}</strong><span className="food-muted block text-xs">{THEME_LABELS[value].note}</span></span>
            </label>
          ))}
        </div>
      </section>

      <section className="panel" aria-labelledby="account-settings-title">
        <p className="eyebrow">Account</p>
        <h2 id="account-settings-title" className="panel-title">Account and alerts</h2>
        <ul className="mt-4 grid gap-2">
          <li><button type="button" className="you-stat" onClick={() => openYou("account")}><UserRound size={18} aria-hidden="true" /><span>Your account details, Food Chat name and consent</span><ChevronRight size={15} aria-hidden="true" /></button></li>
          <li><button type="button" className="you-stat" onClick={onOpenWallet}><Wallet size={18} aria-hidden="true" /><span>Wallet balances and low-balance warnings</span><ChevronRight size={15} aria-hidden="true" /></button></li>
        </ul>
        <p className="field-help mt-3">Email and password changes aren&apos;t available yet.</p>
      </section>

      <DataControls />
    </div>
  );
}

// --- The view ------------------------------------------------------------------------------------

const PAGE_ICONS: Record<YouPage, typeof Heart> = {
  account: UserRound, "favourite-dishes": Heart, "favourite-venues": Store, ratings: Star, messages: MessagesSquare, settings: Palette
};
const PAGE_INTROS: Record<YouPage, string> = {
  account: "Your private account information and Food Chat identity.",
  "favourite-dishes": "Dishes you saved from verified menus. Only you can see this list.",
  "favourite-venues": "Venues you saved in Food Nearby. Only you can see this list.",
  ratings: "The star ratings you've given venues. Change one any time on the venue's page.",
  messages: "Your messages in venue chats.",
  settings: "Appearance, account and data preferences."
};

/** The signed-in student's own pages, opened from the sidebar. */
export function YouView({ page, onBack, onOpenWallet }: { page: YouPage; onBack: () => void; onOpenWallet: () => void }) {
  const Icon = PAGE_ICONS[page];
  return (
    <section aria-labelledby="you-title" className="space-y-6">
      <button type="button" className="secondary-button" onClick={onBack}><ArrowLeft size={14} aria-hidden="true" /> Back to dashboard</button>
      <div className="you-heading">
        <span className="food-card-icon"><Icon size={19} aria-hidden="true" /></span>
        <div>
          <p className="eyebrow">You</p>
          <h1 id="you-title" className="panel-title text-3xl">{PAGE_TITLES[page]}</h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">{PAGE_INTROS[page]}</p>
        </div>
      </div>
      {page === "account" && <AccountPage onOpenWallet={onOpenWallet} />}
      {page === "favourite-dishes" && <FavouriteDishesPage />}
      {page === "favourite-venues" && <FavouriteVenuesPage />}
      {page === "ratings" && <RatingsPage />}
      {page === "messages" && <MessagesPage />}
      {page === "settings" && <SettingsPage onOpenWallet={onOpenWallet} />}
    </section>
  );
}
