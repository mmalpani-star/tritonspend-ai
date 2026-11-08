"use client";

import { Flag, Pencil, Send, Trash2 } from "lucide-react";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import {
  clearVenueRating,
  deleteVenueMessage,
  editVenueMessage,
  rateVenue,
  readVenueMessages,
  readVenueRating,
  reportFoodContent,
  sendVenueMessage
} from "../../lib/api";
import {
  CHAT_POLL_MS,
  ChatMessage,
  FoodMe,
  MAX_MESSAGE_LENGTH,
  VenueRating,
  formatVenueAverage,
  mergeLatest,
  messageError,
  ratedByLabel,
  replaceMessage,
  withOlder,
  withoutMessage
} from "../../lib/food-chat";
import { ConfirmDialog } from "../confirm-dialog";
import { ReportDialog, StarInput, Stars, StatusLine, when } from "./food-ui";

type Status = { error: boolean; text: string } | null;
const message = (failure: unknown, fallback: string) => (failure instanceof Error ? failure.message : fallback);

// --- Venue rating --------------------------------------------------------------------------------

/** The venue's average star rating, how many students rated it, and your own 1-5 rating. */
export function VenueRatingBar({ venueId, venueName, me }: { venueId: string; venueName: string; me: FoodMe | null }) {
  const id = useId();
  const [rating, setRating] = useState<VenueRating | null>(null);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  useEffect(() => {
    let active = true;
    setRating(null);
    setLoadError("");
    readVenueRating(venueId)
      .then((value) => active && setRating(value))
      .catch((failure) => active && setLoadError(message(failure, "Couldn't load ratings.")));
    return () => { active = false; };
  }, [venueId, me?.consent_active]);

  async function change(stars: number | null) {
    setBusy(true);
    setStatus(null);
    try {
      setRating(stars === null ? await clearVenueRating(venueId) : await rateVenue(venueId, stars));
      setStatus({ error: false, text: stars === null ? "Your rating was removed." : "Your rating is saved." });
    } catch (failure) {
      setStatus({ error: true, text: message(failure, "Couldn't save your rating.") });
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <p role="alert" className="error-box">{loadError}</p>;
  if (!rating) return <p className="food-muted text-sm">Loading ratings…</p>;
  return (
    <div className="venue-rating" aria-label={`${venueName} rating`}>
      <div className="venue-rating-summary">
        <Stars value={rating.average_rating} size={18} />
        <strong>{formatVenueAverage(rating)}</strong>
        {rating.rating_count > 0 && <span className="food-muted">{" "}{ratedByLabel(rating.rating_count)}</span>}
      </div>
      {me?.consent_active ? (
        <div className="venue-rating-mine">
          <span className="food-muted text-sm" id={`${id}-label`}>{rating.my_rating ? "Your rating" : "Rate it"}</span>
          <fieldset disabled={busy} aria-labelledby={`${id}-label`} className="contents">
            <StarInput value={rating.my_rating ?? 0} onChange={(stars) => void change(stars)} name={`${id}-stars`} />
          </fieldset>
          {rating.my_rating && <button type="button" className="food-link text-sm" disabled={busy} onClick={() => void change(null)}>Remove</button>}
        </div>
      ) : (
        me && <p className="food-muted text-sm">Accept the consent document at the top of the page to rate venues.</p>
      )}
      <StatusLine status={status} />
    </div>
  );
}

// --- Venue chat ----------------------------------------------------------------------------------

function MessageRow({ item, canPost, onChanged, onRemoved }: {
  item: ChatMessage;
  canPost: boolean;
  onChanged: (updated: ChatMessage) => void;
  onRemoved: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.body);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [reporting, setReporting] = useState(false);
  const hidden = item.moderation_state !== null && item.moderation_state !== "visible";

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const problem = messageError(text);
    if (problem) return setStatus({ error: true, text: problem });
    setBusy(true);
    try {
      onChanged(await editVenueMessage(item.id, text));
      setEditing(false);
      setStatus(null);
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
      onRemoved(item.id);
    } catch (failure) {
      setConfirmDelete(false);
      setStatus({ error: true, text: message(failure, "Couldn't delete your message.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`chat-message ${item.is_mine ? "chat-message-mine" : ""}`}>
      <div className="chat-meta">
        <strong>{item.author_name}{item.is_mine && <span className="food-you"> (you)</span>}</strong>
        <time dateTime={item.created_at}>{when(item.created_at)}</time>
        {item.edited && <span>· edited</span>}
      </div>
      {hidden && <p className="chat-hidden">A moderator {item.moderation_state === "hidden" ? "hid" : "removed"} this message; only you can see it.</p>}
      {editing ? (
        <form onSubmit={save} className="chat-edit">
          <label className="sr-only" htmlFor={`edit-${item.id}`}>Edit your message</label>
          <textarea id={`edit-${item.id}`} rows={2} maxLength={MAX_MESSAGE_LENGTH} value={text} onChange={(event) => setText(event.target.value)} />
          <div className="flex gap-2">
            <button type="submit" className="primary-button" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="secondary-button" onClick={() => { setEditing(false); setText(item.body); setStatus(null); }}>Cancel</button>
          </div>
        </form>
      ) : (
        <p className="chat-body">{item.body}</p>
      )}
      {canPost && !editing && (
        <div className="chat-actions">
          {item.is_mine ? (
            <>
              {!hidden && <button type="button" onClick={() => setEditing(true)}><Pencil size={13} aria-hidden="true" /> Edit</button>}
              <button type="button" className="chat-action-danger" onClick={() => setConfirmDelete(true)}><Trash2 size={13} aria-hidden="true" /> Delete</button>
            </>
          ) : (
            <button type="button" onClick={() => setReporting(true)}><Flag size={13} aria-hidden="true" /> Report</button>
          )}
        </div>
      )}
      <StatusLine status={status} />
      <ConfirmDialog open={confirmDelete} title="Delete your message?" confirmLabel="Delete message" busy={busy} onConfirm={() => void remove()} onCancel={() => setConfirmDelete(false)}>
        This permanently deletes your message from the chat. It can&apos;t be undone.
      </ConfirmDialog>
      <ReportDialog open={reporting} what="message" onClose={() => setReporting(false)} onSubmit={async (reason, details) => {
        await reportFoodContent({ message_id: item.id }, reason, details);
        setReporting(false);
        setStatus({ error: false, text: "Thanks, a moderator will take a look." });
      }} />
    </li>
  );
}

/** The venue's group chat: a flat, chronological feed with the composer at the bottom. */
export function VenueChat({ venueId, venueName, me }: { venueId: string; venueName: string; me: FoodMe | null }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [state, setState] = useState<{ status: "loading" } | { status: "error"; text: string } | { status: "ready" }>({ status: "loading" });
  const [olderBusy, setOlderBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const feed = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true); // follow new messages unless the reader scrolled up
  const keepOffset = useRef<number | null>(null); // distance from the bottom to keep after loading older messages
  const canPost = Boolean(me?.consent_active);

  const load = useCallback(async () => {
    try {
      const page = await readVenueMessages(venueId);
      setMessages(page.messages);
      setHasOlder(page.has_older);
      setState({ status: "ready" });
      stickToBottom.current = true;
    } catch (failure) {
      setState({ status: "error", text: message(failure, "Couldn't load the chat.") });
    }
  }, [venueId]);

  useEffect(() => {
    setState({ status: "loading" });
    setMessages([]);
    void load();
  }, [load, me?.consent_active]);

  // Poll for new, edited and deleted messages while the tab is visible.
  useEffect(() => {
    if (state.status !== "ready") return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      readVenueMessages(venueId).then((page) => {
        setMessages((current) => mergeLatest(current, page));
        setHasOlder((older) => older || page.has_older);
      }).catch(() => { /* a missed poll is retried on the next tick */ });
    }, CHAT_POLL_MS);
    return () => window.clearInterval(timer);
  }, [venueId, state.status]);

  useLayoutEffect(() => {
    const element = feed.current;
    if (!element) return;
    if (keepOffset.current !== null) {
      element.scrollTop = element.scrollHeight - keepOffset.current;
      keepOffset.current = null;
    } else if (stickToBottom.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages]);

  const hasMessages = messages.length > 0;
  // Text can re-wrap after the first paint (web fonts, narrow screens), growing the feed; stay at
  // the newest message unless the reader has scrolled up.
  useEffect(() => {
    const element = feed.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (stickToBottom.current && keepOffset.current === null) element.scrollTop = element.scrollHeight;
    });
    observer.observe(element);
    const list = element.querySelector(".chat-list");
    if (list) observer.observe(list);
    return () => observer.disconnect();
  }, [state.status, hasMessages]);

  async function loadOlder() {
    if (!messages.length) return;
    setOlderBusy(true);
    try {
      const page = await readVenueMessages(venueId, messages[0].id);
      if (feed.current) keepOffset.current = feed.current.scrollHeight - feed.current.scrollTop;
      setMessages((current) => withOlder(current, page));
      setHasOlder(page.has_older);
    } catch (failure) {
      setStatus({ error: true, text: message(failure, "Couldn't load older messages.") });
    } finally {
      setOlderBusy(false);
    }
  }

  async function send(event?: React.FormEvent) {
    event?.preventDefault();
    const problem = messageError(draft);
    if (problem) return setStatus({ error: true, text: problem });
    setSending(true);
    setStatus(null);
    try {
      const sent = await sendVenueMessage(venueId, draft);
      setDraft("");
      stickToBottom.current = true;
      setMessages((current) => [...withoutMessage(current, sent.id), sent]);
    } catch (failure) {
      setStatus({ error: true, text: message(failure, "Couldn't send your message.") });
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="panel venue-chat" aria-labelledby={`chat-${venueId}`}>
      <div className="venue-chat-head">
        <h2 id={`chat-${venueId}`} className="panel-title text-xl">{venueName} chat</h2>
        <p className="food-muted text-sm">Talk about any dish, station, price or visit. You appear by your Food Chat name, never your email.</p>
      </div>
      <div
        ref={feed}
        className="chat-feed"
        role="log"
        aria-live="polite"
        aria-label={`Messages about ${venueName}`}
        tabIndex={0}
        onScroll={(event) => {
          const element = event.currentTarget;
          stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 48;
        }}
      >
        {state.status === "loading" && <p className="chat-empty">Loading messages…</p>}
        {state.status === "error" && (
          <p role="alert" className="error-box m-3">{state.text} <button type="button" className="food-link" onClick={() => void load()}>Try again</button></p>
        )}
        {state.status === "ready" && hasOlder && (
          <button type="button" className="chat-older" disabled={olderBusy} onClick={() => void loadOlder()}>{olderBusy ? "Loading…" : "Load older messages"}</button>
        )}
        {state.status === "ready" && messages.length === 0 && <p className="chat-empty">No messages yet. Start the conversation about {venueName}.</p>}
        {messages.length > 0 && (
          <ol className="chat-list">
            {messages.map((item) => (
              <MessageRow
                key={`${item.id}-${item.updated_at}-${item.moderation_state ?? ""}`}
                item={item}
                canPost={canPost}
                onChanged={(updated) => setMessages((current) => replaceMessage(current, updated))}
                onRemoved={(removed) => setMessages((current) => withoutMessage(current, removed))}
              />
            ))}
          </ol>
        )}
      </div>
      {canPost ? (
        <form className="chat-composer" onSubmit={send}>
          <label className="sr-only" htmlFor={`compose-${venueId}`}>Message {venueName}</label>
          <textarea
            id={`compose-${venueId}`}
            rows={1}
            maxLength={MAX_MESSAGE_LENGTH}
            value={draft}
            placeholder={`Message ${venueName}…`}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void send();
              }
            }}
          />
          <button type="submit" className="primary-button" disabled={sending || !draft.trim()} aria-label="Send message">
            <Send size={16} aria-hidden="true" /> <span className="chat-send-label">{sending ? "Sending…" : "Send"}</span>
          </button>
        </form>
      ) : (
        <p className="chat-locked">{me ? "Accept the consent document at the top of the page to join the chat. You can still read it." : "Sign in to join the chat."}</p>
      )}
      <StatusLine status={status} />
    </section>
  );
}
