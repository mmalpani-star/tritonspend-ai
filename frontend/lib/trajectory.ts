/** The remembered forecast if it is still in the history, otherwise the newest. */
export function pickForecastId(history: ReadonlyArray<{ id: string }>, remembered: string | null): string | null {
  if (remembered && history.some((item) => item.id === remembered)) return remembered;
  return history[0]?.id ?? null;
}

/** History and selection after a forecast is deleted: a deleted selection falls back to the newest remaining. */
export function withoutForecast<T extends { id: string }>(history: readonly T[], deletedId: string, selectedId: string | null): { history: T[]; selectedId: string | null } {
  const remaining = history.filter((item) => item.id !== deletedId);
  return { history: remaining, selectedId: selectedId === deletedId ? remaining[0]?.id ?? null : selectedId };
}

const STORAGE_KEY = "tritonspend-trajectory-forecast";
let selected: string | null = null;

/** Remembers which saved forecast Spending Trajectory should open (e.g. one just created). */
export function rememberForecastSelection(id: string): void {
  selected = id;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Storage can be unavailable (private mode); the in-memory value still works.
  }
}

export function rememberedForecastSelection(): string | null {
  if (selected) return selected;
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Forgets a remembered forecast that was deleted. */
export function forgetForecastSelection(id: string): void {
  if (rememberedForecastSelection() !== id) return;
  selected = null;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear when storage is unavailable.
  }
}
