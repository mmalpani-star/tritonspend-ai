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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function createForecast(request: ForecastRequest): Promise<ForecastResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/forecasts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    let message = `Forecast request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Preserve the useful HTTP status when the server has no JSON error body.
    }
    throw new Error(message);
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
function errorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => String((item as { msg?: unknown }).msg ?? "").replace(/^Value error, /, ""))
      .filter(Boolean)
      .join(" ") || fallback;
  }
  return fallback;
}

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
