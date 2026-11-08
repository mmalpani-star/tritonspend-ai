import {
  AuthStatus,
  BalanceWarnings,
  ForecastRequest,
  ForecastResponse,
  ForecastTrajectory,
  ParticipantForecastDetail,
  ParticipantForecastRequest,
  ParticipantForecastSummary,
  Prediction,
  WalletBalances,
  WalletStatus
} from "./types";
import { errorDetail } from "./api-errors";
import type { AccountSummary, FavoriteChange, FavoriteKind, Favorites, MyMessages, MyRatings } from "./account";
import {
  CommentList,
  CommentSort,
  FoodMe,
  FoodStationDetail,
  FoodVenueDetail,
  FoodVenueSummary,
  MenuItemDetail,
  ModerationAction,
  ModerationReport,
  ReportReason,
  Review,
  ReviewList,
  ReviewSort,
  StationMenu,
  VoteResult,
  foodErrorMessage
} from "./food-chat";
import type { ChatMessage, MessagePage, VenueRating } from "./food-chat";

// Unset → the local backend. "/" → this site's own origin (hosted deployments proxy /api/* to the
// backend so the session cookie stays first-party; see next.config.mjs). Otherwise an absolute origin.
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").trim().replace(/\/+$/, "");

export async function createForecast(request: ForecastRequest): Promise<ForecastResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/forecasts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    // A non-JSON body (e.g. a proxy error page) keeps the useful HTTP status in the fallback.
    throw new Error(errorDetail(await response.json().catch(() => null), `Forecast request failed (${response.status})`));
  }
  return (await response.json()) as ForecastResponse;
}

let csrfToken: string | null = null;

export async function getAuthStatus(): Promise<AuthStatus | null> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/status`, { credentials: "include" });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Unable to check authentication status.");
  return (await response.json()) as AuthStatus;
}

export async function redeemInvite(token: string): Promise<AuthStatus> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/redeem`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  });
  if (!response.ok) throw new Error("That invitation is invalid or expired.");
  await bootstrapCsrf();
  return (await getAuthStatus()) as AuthStatus;
}

/** Turns FastAPI's string or validation-list `detail` into one readable message. */
async function startAccountSession(path: string, body: object, fallback: string): Promise<AuthStatus> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), fallback));
  await bootstrapCsrf();
  return (await getAuthStatus()) as AuthStatus;
}

export async function signUp(email: string, password: string, passwordConfirmation: string): Promise<AuthStatus> {
  return startAccountSession(
    "/api/v1/auth/signup",
    { email, password, password_confirmation: passwordConfirmation },
    "Unable to create your account."
  );
}

export async function logIn(email: string, password: string): Promise<AuthStatus> {
  return startAccountSession("/api/v1/auth/login", { email, password }, "Unable to sign in.");
}

async function bootstrapCsrf(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/csrf`, { credentials: "include" });
  if (!response.ok) throw new Error("Unable to start the authenticated session.");
  csrfToken = ((await response.json()) as { csrf_token: string }).csrf_token;
}

export async function acceptConsent(): Promise<AuthStatus> {
  if (!csrfToken) await bootstrapCsrf();
  const token = csrfToken;
  if (!token) throw new Error("Unable to start the authenticated session.");
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/consent`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
    body: JSON.stringify({})
  });
  if (!response.ok) throw new Error("Unable to record consent.");
  return (await getAuthStatus()) as AuthStatus;
}

export async function logoutParticipant(): Promise<void> {
  if (!csrfToken) await bootstrapCsrf();
  const token = csrfToken;
  if (!token) throw new Error("Unable to start the authenticated session.");
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": token }
  });
  if (!response.ok) throw new Error("Unable to sign out.");
  csrfToken = null;
}

async function pilotRequest(path: string, method: string, body?: object) {
  if (!csrfToken) {
    const csrf = await fetch(`${API_BASE_URL}/api/v1/auth/csrf`, { credentials: "include" });
    if (!csrf.ok) throw new Error("Sign in before recording participant data.");
    csrfToken = ((await csrf.json()) as { csrf_token: string }).csrf_token;
  }
  const token = csrfToken;
  if (!token) throw new Error("Unable to start the authenticated session.");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!response.ok) {
    if (response.status === 403) csrfToken = null;
    throw new Error(errorDetail(await response.json().catch(() => null), `Participant data request failed (${response.status})`));
  }
  return response.json();
}

export async function saveWalletBalances(payload: {
  effective_date: string;
  dining_dollars_cents: number;
  triton_cash_cents: number;
}): Promise<WalletBalances> {
  return (await pilotRequest("/api/v1/pilot/wallet", "POST", payload)) as WalletBalances;
}

export async function setBalanceThresholds(payload: {
  dining_dollars_cents: number;
  triton_cash_cents: number;
}): Promise<BalanceWarnings> {
  return (await pilotRequest("/api/v1/pilot/balance-thresholds", "POST", payload)) as BalanceWarnings;
}

export async function downloadParticipantData(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/pilot/export`, {
    credentials: "include"
  });
  if (!response.ok) throw new Error("Sign in to download your participant data.");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "tritonspend-data-export.json";
  link.click();
  URL.revokeObjectURL(url);
}

export async function deleteParticipantData(): Promise<void> {
  await pilotRequest("/api/v1/pilot/account", "DELETE", { confirmation: "DELETE_MY_DATA" });
  csrfToken = null;
}

async function pilotRead<T>(path: string, fallback: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : `${fallback} (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function readWallet(): Promise<WalletStatus> {
  return pilotRead("/api/v1/pilot/wallet", "Unable to load your wallet balances");
}

export async function createParticipantForecast(request: ParticipantForecastRequest): Promise<ParticipantForecastDetail> {
  return (await pilotRequest("/api/v1/pilot/forecasts", "POST", request)) as ParticipantForecastDetail;
}

export async function listParticipantForecasts(limit = 20): Promise<ParticipantForecastSummary[]> {
  const body = await pilotRead<{ forecasts: ParticipantForecastSummary[] }>(`/api/v1/pilot/forecasts?limit=${limit}`, "Unable to load saved forecasts");
  return body.forecasts;
}

export async function deleteParticipantForecast(id: string): Promise<void> {
  await pilotRequest(`/api/v1/pilot/forecasts/${encodeURIComponent(id)}`, "DELETE");
}

export async function readParticipantForecast(id: string): Promise<ParticipantForecastDetail> {
  return pilotRead(`/api/v1/pilot/forecasts/${encodeURIComponent(id)}`, "Unable to load that forecast");
}

export async function readForecastTrajectory(id: string): Promise<ForecastTrajectory> {
  return pilotRead(`/api/v1/pilot/forecasts/${encodeURIComponent(id)}/trajectory`, "Unable to load the balance trajectory");
}

export async function readPrediction(forecastId: string | null): Promise<Prediction> {
  const query = forecastId ? `?forecast_id=${encodeURIComponent(forecastId)}` : "";
  return pilotRead(`/api/v1/pilot/prediction${query}`, "Unable to load your personalized prediction");
}


// --- Food Nearby catalog and Food Chat -------------------------------------------------------------

/** A failed request with its HTTP status (0 = network failure) and a student-friendly message. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function failureDetail(response: Response): Promise<string | null> {
  return errorDetail(await response.json().catch(() => null), "") || null;
}

async function foodRead<T>(path: string, fallback: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  } catch {
    throw new ApiError(foodErrorMessage(0, null, fallback), 0);
  }
  if (!response.ok) throw new ApiError(foodErrorMessage(response.status, await failureDetail(response), fallback), response.status);
  return (await response.json()) as T;
}

/** A Food Chat change using the shared CSRF token. If the server rejects the token (e.g. after a
 * new sign-in), fetch a fresh one and retry once; other refusals are reported as they are. */
async function foodWrite<T>(path: string, method: string, body: object | undefined, fallback: string): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    if (!csrfToken) {
      const csrf = await fetch(`${API_BASE_URL}/api/v1/auth/csrf`, { credentials: "include" }).catch(() => null);
      if (!csrf) throw new ApiError(foodErrorMessage(0, null, fallback), 0);
      if (!csrf.ok) throw new ApiError(foodErrorMessage(401, null, fallback), 401);
      csrfToken = ((await csrf.json()) as { csrf_token: string }).csrf_token;
    }
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method,
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: body ? JSON.stringify(body) : undefined
      });
    } catch {
      throw new ApiError(foodErrorMessage(0, null, fallback), 0);
    }
    if (response.ok) return (response.status === 204 ? null : await response.json()) as T;
    const detail = await failureDetail(response);
    const csrfRejected = response.status === 403 && /csrf/i.test(detail ?? "");
    if (csrfRejected) csrfToken = null;
    if (!csrfRejected || attempt > 0) throw new ApiError(foodErrorMessage(response.status, detail, fallback), response.status);
  }
}

const enc = encodeURIComponent;

export const readFoodVenues = () =>
  foodRead<{ venues: FoodVenueSummary[]; total: number }>("/api/v1/food/venues?limit=200", "Couldn't load community ratings");
export const readFoodVenue = (id: string) => foodRead<FoodVenueDetail>(`/api/v1/food/venues/${enc(id)}`, "Couldn't load this venue");
export const readFoodStation = (id: string) => foodRead<FoodStationDetail>(`/api/v1/food/stations/${enc(id)}`, "Couldn't load this station");
export const readStationMenu = (id: string) => foodRead<StationMenu>(`/api/v1/food/stations/${enc(id)}/menu-items`, "Couldn't load this station's menu");
export const readMenuItem = (id: string) => foodRead<MenuItemDetail>(`/api/v1/food/menu-items/${enc(id)}`, "Couldn't load this dish");
export const readFoodMe = () => foodRead<FoodMe>("/api/v1/food/me", "Couldn't load your Food Chat profile");
export const readVenueReviews = (id: string, sort: ReviewSort) =>
  foodRead<ReviewList>(`/api/v1/food/venues/${enc(id)}/reviews?sort=${sort}&limit=50`, "Couldn't load reviews");
export const readDishReviews = (id: string, sort: ReviewSort) =>
  foodRead<ReviewList>(`/api/v1/food/menu-items/${enc(id)}/reviews?sort=${sort}&limit=50`, "Couldn't load reviews");
export const readReviewComments = (id: string, sort: CommentSort) =>
  foodRead<CommentList>(`/api/v1/food/reviews/${enc(id)}/comments?sort=${sort}`, "Couldn't load the discussion");

/** Reviews are about a venue; dishes and stations are named in the text. */
export type NewReview = { venue_id: string; rating: number; body: string };
export const createReview = (review: NewReview) => foodWrite<Review>("/api/v1/food/reviews", "POST", review, "Couldn't post your review");
export const updateReview = (id: string, changes: { rating?: number; body?: string }) =>
  foodWrite<Review>(`/api/v1/food/reviews/${enc(id)}`, "PATCH", changes, "Couldn't save your review");
export const deleteReview = (id: string) => foodWrite<null>(`/api/v1/food/reviews/${enc(id)}`, "DELETE", undefined, "Couldn't delete your review");
export const createComment = (reviewId: string, body: string, parentId: string | null) =>
  foodWrite<{ id: string }>(`/api/v1/food/reviews/${enc(reviewId)}/comments`, "POST", { body, parent_id: parentId }, "Couldn't post your comment");
export const updateComment = (id: string, body: string) =>
  foodWrite<{ id: string }>(`/api/v1/food/comments/${enc(id)}`, "PATCH", { body }, "Couldn't save your comment");
export const deleteComment = (id: string) => foodWrite<null>(`/api/v1/food/comments/${enc(id)}`, "DELETE", undefined, "Couldn't delete your comment");
export const voteOnComment = (id: string, value: 1 | -1) =>
  foodWrite<VoteResult>(`/api/v1/food/comments/${enc(id)}/vote`, "PUT", { value }, "Couldn't record your vote");
export const removeCommentVote = (id: string) =>
  foodWrite<VoteResult>(`/api/v1/food/comments/${enc(id)}/vote`, "DELETE", undefined, "Couldn't remove your vote");
export const reportFoodContent = (target: { message_id: string } | { review_id: string } | { comment_id: string }, reason: ReportReason, details: string) =>
  foodWrite<{ id: string }>("/api/v1/food/reports", "POST", { ...target, reason, details: details.trim() || null }, "Couldn't send your report");

export const readModerationQueue = (status: "open" | "all") =>
  foodRead<{ reports: ModerationReport[]; total: number }>(`/api/v1/food/moderation/reports?status=${status}&limit=200`, "Couldn't load reports");
export const readModerationHistory = () => foodRead<{ actions: ModerationAction[] }>("/api/v1/food/moderation/actions?limit=50", "Couldn't load moderation history");
export const moderateContent = (kind: "message" | "review" | "comment", id: string, action: "hide" | "restore" | "remove", note: string) =>
  foodWrite<{ moderation_state: string }>(`/api/v1/food/moderation/${kind}s/${enc(id)}`, "POST", { action, note: note.trim() || null }, "Couldn't update that content");
export const settleReport = (id: string, action: "resolve" | "dismiss", note: string) =>
  foodWrite<{ status: string }>(`/api/v1/food/moderation/reports/${enc(id)}`, "POST", { action, note: note.trim() || null }, "Couldn't update that report");

// --- Your account, favourites and activity (private to the signed-in student) ---

export const readAccountSummary = () => foodRead<AccountSummary>("/api/v1/me/account", "Couldn't load your account");
export const readFavorites = () => foodRead<Favorites>("/api/v1/me/favorites", "Couldn't load your favourites");
export const setFavorite = (kind: FavoriteKind, id: string, saved: boolean) =>
  foodWrite<FavoriteChange>(`/api/v1/me/favorites/${kind === "venue" ? "venues" : "dishes"}/${enc(id)}`, saved ? "PUT" : "DELETE", undefined,
    saved ? "Couldn't save this favourite" : "Couldn't remove this favourite");
export const readMyRatings = () => foodRead<MyRatings>("/api/v1/me/ratings", "Couldn't load your ratings");
export const readMyMessages = () => foodRead<MyMessages>("/api/v1/me/messages?limit=100", "Couldn't load your messages");

// --- Venue ratings and venue chat ---

export const readVenueRating = (venueId: string) => foodRead<VenueRating>(`/api/v1/food/venues/${enc(venueId)}/rating`, "Couldn't load ratings");
export const rateVenue = (venueId: string, rating: number) =>
  foodWrite<VenueRating>(`/api/v1/food/venues/${enc(venueId)}/rating`, "PUT", { rating }, "Couldn't save your rating");
export const clearVenueRating = (venueId: string) =>
  foodWrite<VenueRating>(`/api/v1/food/venues/${enc(venueId)}/rating`, "DELETE", undefined, "Couldn't remove your rating");
export const readVenueMessages = (venueId: string, before?: string) =>
  foodRead<MessagePage>(`/api/v1/food/venues/${enc(venueId)}/messages?limit=50${before ? `&before=${enc(before)}` : ""}`, "Couldn't load the chat");
export const sendVenueMessage = (venueId: string, body: string) =>
  foodWrite<ChatMessage>(`/api/v1/food/venues/${enc(venueId)}/messages`, "POST", { body: body.trim() }, "Couldn't send your message");
export const editVenueMessage = (id: string, body: string) =>
  foodWrite<ChatMessage>(`/api/v1/food/messages/${enc(id)}`, "PATCH", { body: body.trim() }, "Couldn't save your message");
export const deleteVenueMessage = (id: string) => foodWrite<null>(`/api/v1/food/messages/${enc(id)}`, "DELETE", undefined, "Couldn't delete your message");
