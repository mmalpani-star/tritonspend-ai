"use client";

import { CircleHelp, WalletCards } from "lucide-react";
import { useState } from "react";
import { AuthMode, AuthPanel, AuthRequest } from "../components/auth-panel";
import { CampusHero } from "../components/campus-hero";
import { CreateForecastView } from "../components/create-forecast-view";
import { DashboardHome } from "../components/dashboard-home";
import { DashboardNav } from "../components/dashboard-nav";
import { FoodNearbyView } from "../components/food-nearby-view";
import { LandingIntro } from "../components/landing-intro";
import { SpendingTrajectoryView } from "../components/spending-trajectory-view";
import { ThemeSwitcher } from "../components/theme-switcher";
import { WalletAlertsView } from "../components/wallet-alerts-view";
import { PhotoCredits } from "../components/visual/photo-credits";
import { useDashboardView } from "../lib/dashboard-views";
import { AuthStatus } from "../lib/types";

export default function Home() {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authRequest, setAuthRequest] = useState<AuthRequest | null>(null);
  const [view, navigate] = useDashboardView();
  const signedIn = Boolean(authStatus?.authenticated);
  const home = () => navigate("home");
  const openAuth = (mode: AuthMode) => setAuthRequest({ mode, at: Date.now() });
  const signUp = () => openAuth("signup");
  const logIn = () => openAuth("login");

  return (
    <main className="min-h-screen">
      <header className="site-header mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-5 lg:px-8">
        <div className="flex items-center gap-3"><div className="brand-mark"><WalletCards size={21} /></div><div><span className="block font-display text-lg font-bold tracking-tight text-[var(--text)]">TritonSpend <span className="text-[var(--primary)]">AI</span></span><span className="hidden text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--text-muted)] sm:block">Student dining planning</span></div></div>
        <div className="flex w-full items-center justify-end gap-3 sm:w-auto"><span className="hidden items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] lg:flex"><CircleHelp size={14} /> Built for your own account rules</span><ThemeSwitcher /></div>
      </header>
      <div className="mx-auto max-w-7xl px-5 pb-16 lg:px-8">
        {/* Signed out, the introduction comes first and the account form closes the page. The panel keeps
            the same position among its siblings so signing in never remounts it. */}
        {!signedIn && (
          <>
            <CampusHero onSignUp={signUp} onLogIn={logIn} />
            <LandingIntro />
          </>
        )}
        <AuthPanel onStatusChange={setAuthStatus} compact request={authRequest} />
        {signedIn && (
          <>
            <DashboardNav view={view} onNavigate={navigate} />
            {view === "home" && <DashboardHome onNavigate={navigate} />}
            {view === "forecast" && <CreateForecastView onBack={home} onOpenWallet={() => navigate("wallet")} onOpenTrajectory={() => navigate("spending-trajectory")} />}
            {view === "food-nearby" && <FoodNearbyView onBack={home} onOpenForecast={() => navigate("forecast")} onOpenWallet={() => navigate("wallet")} />}
            {view === "spending-trajectory" && <SpendingTrajectoryView onBack={home} onOpenForecast={() => navigate("forecast")} onOpenWallet={() => navigate("wallet")} />}
            {view === "wallet" && <WalletAlertsView onBack={home} />}
          </>
        )}
      </div>
      <footer className="site-footer mx-auto flex max-w-7xl flex-col flex-wrap gap-2 border-t border-[var(--border)] px-5 py-6 text-xs text-[var(--text-muted)] sm:flex-row sm:items-center sm:justify-between lg:px-8"><span>TritonSpend AI · Keep your own account rules in the driver&apos;s seat.</span><span>Forecasts are illustrative planning estimates.</span><div className="sm:basis-full"><PhotoCredits /></div></footer>
    </main>
  );
}
