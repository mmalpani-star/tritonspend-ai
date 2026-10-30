"use client";

import { ArrowRight, Calculator, TrendingDown, UtensilsCrossed } from "lucide-react";
import { DashboardView, PRODUCT_AREAS } from "../lib/dashboard-views";
import type { CampusPhotoId } from "../lib/campus-photos";
import { useWallet } from "../lib/wallet";
import { CampusBanner } from "./campus-hero";
import { CampusPhoto } from "./visual/campus-photo";
import { SpeckleField } from "./visual/speckle-field";
import { SpectrumShape } from "./visual/spectrum-shape";
import { WalletBalancesCard } from "./wallet-balances";

const ICONS = { forecast: Calculator, "food-nearby": UtensilsCrossed, "spending-trajectory": TrendingDown } as const;
// Each card gets its own campus photo and crop so the dashboard isn't one repeated image.
const MEDIA: Record<(typeof PRODUCT_AREAS)[number]["view"], { photo: CampusPhotoId; position: string; shape: "orb" | "arc" | "pill" }> = {
  forecast: { photo: "geiselDetail", position: "object-[50%_30%]", shape: "arc" },
  "food-nearby": { photo: "priceCenterTriton", position: "object-[50%_60%]", shape: "orb" },
  "spending-trajectory": { photo: "laJollaShores", position: "object-[60%_50%]", shape: "pill" }
};

export function DashboardHome({ onNavigate }: { onNavigate: (view: DashboardView) => void }) {
  const [wallet, reload] = useWallet();
  return (
    <section aria-labelledby="dashboard-title">
      <CampusBanner>
        <p className="campus-hero-eyebrow">Your dashboard</p>
        <h1 id="dashboard-title" className="mt-3 font-display text-3xl font-bold tracking-tight text-white sm:text-4xl">What would you like to do?</h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-white/80">Plan from your saved wallet balances. Forecasts are illustrative estimates, not guarantees.</p>
      </CampusBanner>
      <div className="mb-6">
        <WalletBalancesCard wallet={wallet} reload={reload} onOpenAlerts={() => onNavigate("wallet")} />
      </div>
      <div className="grid gap-5 md:grid-cols-3">
        {PRODUCT_AREAS.map((area, index) => {
          const Icon = ICONS[area.view];
          const media = MEDIA[area.view];
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
              <span className="feature-card-media" aria-hidden="true">
                <CampusPhoto photo={media.photo} sizes="(min-width: 768px) 33vw, 100vw" decorative className="h-full w-full" imageClassName={media.position} />
                <SpectrumShape variant={media.shape} className={`feature-card-shape-${media.shape}`} />
                <SpeckleField edge="top-right" count={34} seed={41 + index * 7} className="feature-card-speckles" />
              </span>
              <span className="feature-card-body">
                <span className="flex items-end justify-between gap-3">
                  <span className="feature-card-icon"><Icon size={22} aria-hidden="true" /></span>
                  <span className={`feature-badge ${available ? "feature-badge-ready" : ""}`}>{available ? "Available" : "Coming soon"}</span>
                </span>
                <span className="mt-4 block font-display text-xl font-bold tracking-tight text-[var(--text)]">{area.title}</span>
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
