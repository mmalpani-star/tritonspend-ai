import { ForecastRequest, ForecastResponse } from "./types";

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
