"use client";

import { ArrowDown, ArrowRight, LogIn, Sparkles } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { CampusPhoto } from "./visual/campus-photo";
import { RotatingFoodPhoto } from "./visual/rotating-food-photo";
import { SpeckleField } from "./visual/speckle-field";
import { SpectrumShape } from "./visual/spectrum-shape";

/** Writes pointer position (-1..1) to --px/--py for CSS parallax. Fine pointers only, never under reduced motion. */
function usePointerParallax<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (!window.matchMedia("(pointer: fine)").matches || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const set = (x: number, y: number) => {
      element.style.setProperty("--px", x.toFixed(3));
      element.style.setProperty("--py", y.toFixed(3));
    };
    const move = (event: PointerEvent) => {
      const rect = element.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      const y = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => set(x, y));
    };
    const leave = () => {
      cancelAnimationFrame(frame);
      set(0, 0);
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerleave", leave);
    return () => {
      cancelAnimationFrame(frame);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerleave", leave);
    };
  }, []);
  return ref;
}

function DepthCard({ depth, delay, className, children }: { depth: number; delay: number; className: string; children: ReactNode }) {
  return (
    // The shell runs the entrance animation; the inner card owns the parallax transform.
    <div className={`campus-card-shell ${className}`} style={{ "--delay": `${delay}ms` } as React.CSSProperties}>
      <div className="campus-card" style={{ "--depth": depth } as React.CSSProperties}>{children}</div>
    </div>
  );
}

/** Scrolls to the introduction's problem section and moves focus there, without smooth motion under reduced motion. */
function showWhy(event: React.MouseEvent) {
  const target = document.getElementById("problem");
  if (!target) return;
  event.preventDefault();
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  target.focus({ preventScroll: true });
}

/** Signed-out landing hero: Geisel Library with rotating food photo cards, spectrum shapes, and sparse speckles. */
export function CampusHero({ onSignUp, onLogIn }: { onSignUp: () => void; onLogIn: () => void }) {
  const ref = usePointerParallax<HTMLElement>();
  return (
    <section ref={ref} className="campus-hero" aria-labelledby="campus-hero-title">
      <div className="campus-hero-backdrop" aria-hidden="true">
        <div className="campus-hero-backdrop-photo">
          <CampusPhoto photo="geiselLibrary" sizes="(min-width: 1024px) 75vw, 100vw" priority className="h-full w-full" imageClassName="object-[50%_40%]" />
        </div>
        <div className="campus-hero-atmosphere">
          <SpectrumShape variant="arc" drift className="campus-hero-arc" />
          <SpectrumShape variant="orb" drift className="campus-hero-orb" />
          <SpectrumShape variant="pill" className="campus-hero-pill" />
          <SpeckleField edge="top-right" count={80} className="campus-hero-speckles-top" />
          <SpeckleField edge="bottom" count={36} seed={19} className="campus-hero-speckles-bottom" />
        </div>
      </div>

      <div className="campus-hero-inner">
        <div className="campus-hero-copy">
          <p className="campus-hero-eyebrow"><Sparkles size={14} aria-hidden="true" /> Built by and for Tritons</p>
          <h1 id="campus-hero-title" className="campus-hero-title">Make your <span>Dining Dollars</span> last.</h1>
          <p className="campus-hero-text">See your Dining Dollars and Triton Cash side by side, plan for any stretch of the quarter, and know whether each balance will last.</p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a href="#account" className="campus-hero-cta" onClick={(event) => { event.preventDefault(); onSignUp(); }}>Sign up <ArrowRight size={17} aria-hidden="true" /></a>
            <a href="#account" className="campus-hero-ghost" onClick={(event) => { event.preventDefault(); onLogIn(); }}><LogIn size={16} aria-hidden="true" /> Log in</a>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <a href="#problem" className="campus-hero-why" onClick={showWhy}><ArrowDown size={16} aria-hidden="true" /> Why TritonSpend?</a>
            <span className="campus-hero-chip">Exact cents · Accounts stay separate</span>
          </div>
          <p className="campus-hero-note">Independent student project · not affiliated with UC San Diego</p>
        </div>

        <div className="campus-hero-visual" aria-hidden="true">
          {/* Each card owns its own dishes so no photo shows twice at once; offsets stagger the swaps. */}
          <DepthCard depth={1.4} delay={260} className="campus-card-detail">
            <RotatingFoodPhoto photos={["sushiPlatter", "salmonPokeBowl"]} offsetMs={1800} sizes="15rem" className="aspect-[4/3]" />
          </DepthCard>
          <DepthCard depth={2.2} delay={380} className="campus-card-triton">
            <RotatingFoodPhoto photos={["gourmetBurger", "honeyPancakes", "italianSandwich"]} sizes="12rem" className="aspect-[4/3]" />
          </DepthCard>
          <DepthCard depth={0.9} delay={500} className="campus-card-coast">
            <RotatingFoodPhoto photos={["margheritaPizza", "shoyuRamen", "acaiBowl"]} offsetMs={900} sizes="12rem" className="aspect-[16/9]" />
          </DepthCard>
          <DepthCard depth={1.8} delay={620} className="campus-card-stat">
            <div className="campus-glass">
              <span className="metric-label text-white/70">Runway snapshot</span>
              <strong className="campus-glass-value">$24.80</strong>
              <span className="text-xs text-white/75">per day cap · illustrative</span>
            </div>
          </DepthCard>
        </div>
      </div>
    </section>
  );
}

/** Compact campus banner for the signed-in dashboard; static apart from the entrance. */
export function CampusBanner({ children }: { children: ReactNode }) {
  return (
    <section className="campus-banner">
      <div className="campus-banner-photo" aria-hidden="true">
        <CampusPhoto photo="geiselLibrary" sizes="(min-width: 768px) 60vw, 100vw" className="h-full w-full" imageClassName="object-[50%_35%]" />
      </div>
      <SpectrumShape variant="pill" drift className="campus-banner-pill" />
      <SpectrumShape variant="orb" className="campus-banner-orb" />
      <SpeckleField edge="right" count={44} seed={31} className="campus-banner-speckles" />
      <div className="campus-banner-copy">{children}</div>
    </section>
  );
}
