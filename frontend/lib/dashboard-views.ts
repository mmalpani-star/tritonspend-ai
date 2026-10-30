"use client";

import { useCallback, useEffect, useState } from "react";

export type DashboardView = "home" | "forecast" | "food-nearby" | "spending-trajectory" | "wallet";

/** The three product areas, in dashboard order. "home" and "wallet" are not product areas. */
export const PRODUCT_AREAS = [
  {
    view: "forecast",
    title: "Create Forecast",
    summary: "See how long your Dining Dollars and Triton Cash may last, starting from your saved wallet balances.",
    status: "available"
  },
  {
    view: "food-nearby",
    title: "Food Nearby",
    summary: "Campus dining and Triton Cash spots near you, with the wallet each one accepts.",
    status: "available"
  },
  {
    view: "spending-trajectory",
    title: "Spending Trajectory",
    summary: "A personalized prediction learned from your saved balances, with slower, faster, and ideal paths.",
    status: "available"
  }
] as const satisfies ReadonlyArray<{ view: DashboardView; title: string; summary: string; status: "available" | "coming-soon" }>;

const VIEWS: readonly DashboardView[] = ["home", "forecast", "food-nearby", "spending-trajectory", "wallet"];
// Old links to the retired "My data" page land on Wallet & Alerts.
const ALIASES: Record<string, DashboardView> = { "my-data": "wallet" };

function viewFromHash(): DashboardView {
  const hash = window.location.hash.slice(1);
  const value = ALIASES[hash] ?? hash;
  return (VIEWS as readonly string[]).includes(value) ? (value as DashboardView) : "home";
}

/** Keeps the active dashboard view in the URL hash so links, refresh, and back/forward work. */
export function useDashboardView(): [DashboardView, (next: DashboardView) => void] {
  const [view, setView] = useState<DashboardView>("home");

  useEffect(() => {
    const sync = () => setView(viewFromHash());
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const navigate = useCallback((next: DashboardView) => {
    window.location.hash = next === "home" ? "" : next;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  return [view, navigate];
}
