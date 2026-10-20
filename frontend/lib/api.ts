import { AuthStatus, BalanceWarnings, ForecastRequest, ForecastResponse, PilotData } from "./types";

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
    const detail = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(detail.detail || `Participant data request failed (${response.status})`);
  }
  return response.json();
}

export async function readPilotData(startDate: string, endDate: string): Promise<PilotData> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/pilot/data?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`,
    { credentials: "include" }
  );
  if (!response.ok) throw new Error("Sign in before viewing participant data.");
  return (await response.json()) as PilotData;
}

export async function submitBalanceCheckin(payload: object) {
  return pilotRequest("/api/v1/pilot/balance-checkins", "POST", payload);
}

export async function submitLedgerEntry(payload: object) {
  return pilotRequest("/api/v1/pilot/ledger-entries", "POST", payload);
}

export async function confirmZeroSpending(day: string) {
  return pilotRequest("/api/v1/pilot/zero-spending-confirmations", "POST", { day });
}

export async function setBalanceThresholds(payload: {
  dining_dollars_cents: number;
  triton_cash_cents: number;
}): Promise<BalanceWarnings> {
  return (await pilotRequest("/api/v1/pilot/balance-thresholds", "POST", payload)) as BalanceWarnings;
}

export async function readBalanceWarnings(): Promise<BalanceWarnings> {
  const response = await fetch(`${API_BASE_URL}/api/v1/pilot/balance-warnings`, {
    credentials: "include"
  });
  if (!response.ok) throw new Error("Sign in and configure thresholds to view warnings.");
  return (await response.json()) as BalanceWarnings;
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
