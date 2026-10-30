// Shared by the server layout (pre-paint script) and the client ThemeProvider.
export const THEMES = ["classic", "midnight", "formal", "coastal"] as const;
export type Theme = (typeof THEMES)[number];

export const THEME_STORAGE_KEY = "tritonspend-theme";

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

/**
 * Runs in <head> before first paint so the saved theme is applied without a
 * flash. ThemeProvider then adopts whatever this script applied.
 */
export const themeInitScript = `(function(){var d=document.documentElement,t="classic";try{var s=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});if(${JSON.stringify(THEMES)}.indexOf(s)>-1)t=s}catch(e){}d.dataset.theme=t})();`;
