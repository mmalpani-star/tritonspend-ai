"use client";

import { ArrowRight, Calculator, TrendingDown, UtensilsCrossed } from "lucide-react";
import { DashboardView, PRODUCT_AREAS } from "../lib/dashboard-views";
import type { CampusPhotoId } from "../lib/campus-photos";
import { FoodCollage, RotatingCampusPhoto, TrajectoryArt } from "./visual/feature-card-media";
import { useWallet } from "../lib/wallet";
import { CampusBanner } from "./campus-hero";
import { SpeckleField } from "./visual/speckle-field";
import { SpectrumShape } from "./visual/spectrum-shape";
import { WalletBalancesCard } from "./wallet-balances";

const ICONS = { forecast: Calculator, "food-nearby": UtensilsCrossed, "spending-trajectory": TrendingDown } as const;
// Create Forecast rotates UCSD campus photos (Geisel Library first, every 30 s).
const FORECAST_CAMPUS: CampusPhotoId[] = ["geiselLibrary", "priceCenterEast", "libraryWalk", "warrenMall", "conradPrebys", "scrippsPier"];
const CARD_SIZES = "(min-width: 768px) 33vw, 100vw";

/** Each card's own visual identity: campus life, food, and the trajectory chart's language. */
function CardMedia({ view }: { view: (typeof PRODUCT_AREAS)[number]["view"] }) {
  if (view === "forecast") return <RotatingCampusPhoto photos={FORECAST_CAMPUS} sizes={CARD_SIZES} />;
  if (view === "food-nearby") return <FoodCollage sizes={CARD_SIZES} />;
  return <TrajectoryArt />;
}
const SHAPES = { forecast: "arc", "food-nearby": "orb", "spending-trajectory": "pill" } as const;

export function DashboardHome({ onNavigate }: { onNavigate: (view: DashboardView) => void }) {
  const [wallet, reload] = useWallet();
  return (
    <section aria-labelledby="dashboard-title">
      <CampusBanner>
        <p className="stage-eyebrow">Your dashboard</p>
        <h1 id="dashboard-title" className="stage-title mt-4 text-white">What would you like <em>to do?</em></h1>
        <p className="stage-lede mt-4">Plan from your saved wallet balances. Forecasts are illustrative estimates, not guarantees.</p>
      </CampusBanner>
      <div className="mb-6">
        <WalletBalancesCard wallet={wallet} reload={reload} onOpenAlerts={() => onNavigate("wallet")} />
      </div>
      <div className="grid gap-[clamp(1rem,0.7rem+1vw,1.75rem)] md:grid-cols-3">
        {PRODUCT_AREAS.map((area, index) => {
          const Icon = ICONS[area.view];
          const available = area.status === "available";
          return (
            <a
              key={area.view}
              href={`#${area.view}`}
              className="feature-card rounded-[1.5rem]"
              onClick={(event) => {
                event.preventDefault();
                onNavigate(area.view);
              }}
            >
              <span className={`feature-card-media feature-card-media-${area.view}`} aria-hidden="true">
                <CardMedia view={area.view} />
                {area.view === "forecast" && <SpectrumShape variant={SHAPES[area.view]} className={`feature-card-shape-${SHAPES[area.view]}`} />}
                {area.view !== "spending-trajectory" && <SpeckleField edge="top-right" count={34} seed={41 + index * 7} className="feature-card-speckles" />}
              </span>
              <span className="feature-card-body">
                <span className="flex items-end justify-between gap-3">
                  <span className="feature-card-icon"><Icon size={22} aria-hidden="true" /></span>
                  <span className={`feature-badge ${available ? "feature-badge-ready" : ""}`}>{available ? "Available" : "Coming soon"}</span>
                </span>
                <span className="mt-4 block font-display text-[clamp(1.25rem,1.05rem+0.6vw,1.75rem)] font-bold tracking-tight text-[var(--text)]">{area.title}</span>
                <span className="mt-2 block flex-1 text-sm leading-6 text-[var(--text-muted)]">{area.summary}</span>
                <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold text-[var(--primary)]">{available ? "Open" : "Preview"} <ArrowRight size={16} aria-hidden="true" /></span>
              </span>
            </a>
          );
        })}
      </div>
    </section>
  );
}
