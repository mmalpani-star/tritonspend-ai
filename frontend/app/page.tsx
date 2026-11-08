"use client";

import { CircleHelp, WalletCards } from "lucide-react";
import { useId, useState } from "react";
import { FavoritesProvider } from "../components/account/favorites";
import { YouView, useYouPage } from "../components/account/you-view";
import { AuthMode, AuthPanel, AuthRequest } from "../components/auth-panel";
import { CampusHero } from "../components/campus-hero";
import { CreateForecastView } from "../components/create-forecast-view";
import { DashboardHome } from "../components/dashboard-home";
import { DashboardNav } from "../components/dashboard-nav";
import { FoodNearbyView } from "../components/food-nearby-view";
import { GlobalSidebar, SidebarTrigger } from "../components/global-sidebar";
import { LandingIntro } from "../components/landing-intro";
import { SpendingTrajectoryView } from "../components/spending-trajectory-view";
import { ThemeSwitcher } from "../components/theme-switcher";
import { WalletAlertsView } from "../components/wallet-alerts-view";
import { SiteFooter } from "../components/site-footer";
import { youPageHash } from "../lib/account";
import { useDashboardView } from "../lib/dashboard-views";
import { AuthStatus } from "../lib/types";

export default function Home() {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authRequest, setAuthRequest] = useState<AuthRequest | null>(null);
  const [view, navigate] = useDashboardView();
  const youPage = useYouPage();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [signOutRequest, setSignOutRequest] = useState(0);
  const sidebarId = useId();
  const signedIn = Boolean(authStatus?.authenticated);
  const home = () => navigate("home");
  const openAuth = (mode: AuthMode) => setAuthRequest({ mode, at: Date.now() });
  const signUp = () => openAuth("signup");
  const logIn = () => openAuth("login");
  const openYou = (page: Parameters<typeof youPageHash>[0]) => {
    window.location.hash = youPageHash(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const signOut = () => {
    navigate("home");
    setSignOutRequest((count) => count + 1);
  };

  return (
    <main className="min-h-screen">
      <div className="site-header-bar">
        <header className="site-header page-shell flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3"><SidebarTrigger open={sidebarOpen} controls={sidebarId} onOpen={() => setSidebarOpen(true)} /><div className="brand-mark"><WalletCards size={21} /></div><div><span className="brand-word block">TritonSpend <span className="text-[var(--primary)]">AI</span></span><span className="hidden text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--text-muted)] sm:block">Student dining planning</span></div></div>
          <div className="flex w-full items-center justify-end gap-3 sm:w-auto"><span className="hidden items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] xl:flex"><CircleHelp size={14} /> Built for your own account rules</span><ThemeSwitcher /></div>
        </header>
      </div>
      <GlobalSidebar
        id={sidebarId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        signedIn={signedIn}
        email={authStatus?.email ?? null}
        current={view === "you" ? youPage : null}
        onSelect={openYou}
        onSignOut={signOut}
        onSignIn={logIn}
        onSignUp={signUp}
      />
      <div className="page-shell pb-8 pt-[clamp(1rem,0.6rem+1.2vw,2rem)]">
        {/* Signed out, the introduction comes first and the account form closes the page. The panel keeps
            the same position among its siblings so signing in never remounts it. */}
        {!signedIn && (
          <>
            <CampusHero onSignUp={signUp} onLogIn={logIn} />
            <LandingIntro />
          </>
        )}
        <AuthPanel onStatusChange={setAuthStatus} compact request={authRequest} signOutRequest={signOutRequest} />
        {signedIn && (
          <FavoritesProvider>
            <DashboardNav view={view} onNavigate={navigate} />
            {view === "home" && <DashboardHome onNavigate={navigate} />}
            {view === "forecast" && <CreateForecastView onBack={home} onOpenWallet={() => navigate("wallet")} onOpenTrajectory={() => navigate("spending-trajectory")} />}
            {view === "food-nearby" && <FoodNearbyView onBack={home} onOpenForecast={() => navigate("forecast")} onOpenWallet={() => navigate("wallet")} />}
            {view === "spending-trajectory" && <SpendingTrajectoryView onBack={home} onOpenForecast={() => navigate("forecast")} onOpenWallet={() => navigate("wallet")} />}
            {view === "wallet" && <WalletAlertsView onBack={home} />}
            {view === "you" && youPage && <YouView page={youPage} onBack={home} onOpenWallet={() => navigate("wallet")} />}
          </FavoritesProvider>
        )}
      </div>
      <SiteFooter />
    </main>
  );
}
