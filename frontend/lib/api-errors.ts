/**
 * Readable message from a failed API response body. FastAPI sends a string `detail` for
 * domain errors and a list of `{ loc, msg }` for request validation errors. `body` is null
 * when the response wasn't JSON. No runtime imports (Node tests load it directly).
 */
export function errorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => String((item as { msg?: unknown } | null)?.msg ?? "").replace(/^Value error, /, ""))
      .filter(Boolean)
      .join(" ") || fallback;
  }
  return fallback;
}
