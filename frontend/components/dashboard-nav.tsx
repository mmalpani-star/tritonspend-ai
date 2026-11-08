"use client";

import { Calculator, LayoutGrid, TrendingDown, UtensilsCrossed, Wallet } from "lucide-react";
import { DashboardView } from "../lib/dashboard-views";

const ITEMS: ReadonlyArray<{ view: DashboardView; label: string; Icon: typeof LayoutGrid }> = [
  { view: "home", label: "Dashboard", Icon: LayoutGrid },
  { view: "forecast", label: "Create Forecast", Icon: Calculator },
  { view: "food-nearby", label: "Food Nearby", Icon: UtensilsCrossed },
  { view: "spending-trajectory", label: "Spending Trajectory", Icon: TrendingDown }
];

type Props = { view: DashboardView; onNavigate: (view: DashboardView) => void };

export function DashboardNav({ view, onNavigate }: Props) {
  const link = (item: { view: DashboardView; label: string; Icon: typeof LayoutGrid }, extra = "") => (
    <a
      key={item.view}
      href={item.view === "home" ? "#" : `#${item.view}`}
      aria-current={view === item.view ? "page" : undefined}
      className={`nav-tab ${view === item.view ? "nav-tab-active" : ""} ${extra}`}
      onClick={(event) => {
        event.preventDefault();
        onNavigate(item.view);
      }}
    >
      <item.Icon size={16} aria-hidden="true" />
      {item.label}
    </a>
  );

  return (
    <nav aria-label="Dashboard" className="dashboard-nav">
      <div className="flex min-w-0 gap-1 overflow-x-auto">{ITEMS.map((item) => link(item))}</div>
      {link({ view: "wallet", label: "Wallet & Alerts", Icon: Wallet }, "sm:ml-auto")}
    </nav>
  );
}
