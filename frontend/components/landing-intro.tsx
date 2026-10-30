"use client";

import {
  Activity,
  BellRing,
  CalendarClock,
  CalendarRange,
  ChartSpline,
  Coffee,
  Database,
  GitCompare,
  History,
  Info,
  Layers,
  Moon,
  Sandwich,
  Scale,
  Sparkles,
  Store,
  Target,
  TrendingDown,
  UserPlus,
  WalletCards,
  type LucideIcon
} from "lucide-react";
import { useEffect, useRef } from "react";
import type { FoodPhotoId } from "../lib/food-photos";
import { RotatingFoodPhoto } from "./visual/rotating-food-photo";
import { SpeckleField } from "./visual/speckle-field";
import { SpectrumShape } from "./visual/spectrum-shape";

type Point = { icon: LucideIcon; title: string; text: string };

// Each moment owns its own dishes so no photo shows in two tiles at once; offsets stagger the swaps.
const FOOD_MOMENTS: { icon: LucideIcon; label: string; text: string; photos: FoodPhotoId[]; offsetMs: number }[] = [
  { icon: Coffee, label: "Mornings", text: "Breakfast before class", photos: ["honeyPancakes", "acaiBowl"], offsetMs: 0 },
  { icon: Sandwich, label: "Between classes", text: "Lunch on the go", photos: ["italianSandwich", "salmonPokeBowl", "gourmetBurger"], offsetMs: 1500 },
  { icon: Moon, label: "Late nights", text: "Study-session takeout", photos: ["margheritaPizza", "shoyuRamen", "sushiPlatter"], offsetMs: 3000 }
];

const PROBLEMS: Point[] = [
  { icon: WalletCards, title: "Two wallets", text: "Dining Dollars and Triton Cash are separate." },
  { icon: Store, title: "Different rules", text: "Each is accepted in different places." },
  { icon: TrendingDown, title: "Hidden pace", text: "How fast is each one dropping?" },
  { icon: CalendarClock, title: "Will it last?", text: "To the end of the quarter, or the year?" }
];

const FOR_YOU: Point[] = [
  { icon: WalletCards, title: "Both wallets, one view", text: "Balances side by side." },
  { icon: CalendarRange, title: "Plan any period", text: "A week, a quarter, or the year." },
  { icon: Activity, title: "See your habits’ impact", text: "How meals change your balance." },
  { icon: BellRing, title: "Low-balance warnings", text: "You choose the amount." },
  { icon: GitCompare, title: "Compare with your goals", text: "Predicted vs. ideal and saved forecast." }
];

const BEHIND_THE_SCENES: Point[] = [
  { icon: Database, title: "Dated balance updates", text: "Each save is a snapshot in time." },
  { icon: Layers, title: "Each wallet on its own", text: "A separate model per wallet." },
  { icon: TrendingDown, title: "Daily pace", text: "Learned from changes between snapshots." },
  { icon: History, title: "Recent changes matter more", text: "A recency-weighted statistical model." },
  { icon: Sparkles, title: "Gets more personal", text: "More updates, more like you." }
];

const STEPS: Point[] = [
  { icon: UserPlus, title: "Get started", text: "Create an account with any email." },
  { icon: WalletCards, title: "Save wallet balances", text: "Both wallets, plus the date." },
  { icon: CalendarRange, title: "Create a forecast", text: "Dates, habits, where each is accepted." },
  { icon: ChartSpline, title: "Track your trajectory", text: "Predicted, actual and ideal paths." },
  { icon: Target, title: "Stay ahead", text: "Warnings keep you on track." }
];

const delay = (index: number) => ({ "--reveal-delay": `${index * 90}ms` }) as React.CSSProperties;

/**
 * Fades [data-reveal] children in as they scroll into view. Content renders visible on the server and
 * stays visible without IntersectionObserver or under reduced motion; only then is anything hidden.
 */
function useScrollReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root || !("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.15 });
    root.querySelectorAll("[data-reveal]").forEach((element) => observer.observe(element));
    root.classList.add("intro-animate");
    return () => observer.disconnect();
  }, []);
  return ref;
}

function SectionHeading({ id, eyebrow, title, text }: { id: string; eyebrow: string; title: string; text?: string }) {
  return (
    <div className="intro-heading" data-reveal>
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={id} className="intro-title">{title}</h2>
      {text && <p className="intro-lede">{text}</p>}
    </div>
  );
}

function PointList({ points }: { points: Point[] }) {
  return (
    <ul className="intro-point-list">
      {points.map(({ icon: Icon, title, text }) => (
        <li key={title}>
          <span className="intro-point-icon"><Icon size={18} aria-hidden="true" /></span>
          <span><strong>{title}</strong><span>{text}</span></span>
        </li>
      ))}
    </ul>
  );
}

function FoodMoments() {
  return (
    <section className="intro-section" aria-labelledby="intro-food-title">
      <SectionHeading id="intro-food-title" eyebrow="Everyday spending" title="Every meal moves a balance." text="Small purchases add up, across two wallets." />
      <div className="intro-food-grid">
        {FOOD_MOMENTS.map(({ icon: Icon, label, text, photos, offsetMs }, index) => (
          <figure key={label} className="intro-food-card" data-reveal style={delay(index)}>
            <RotatingFoodPhoto photos={photos} offsetMs={offsetMs} sizes="(min-width: 768px) 30vw, 100vw" className="aspect-[4/3]" />
            <figcaption><Icon size={17} aria-hidden="true" /><span><strong>{label}</strong> · {text}</span></figcaption>
          </figure>
        ))}
      </div>
      <p className="intro-footnote">Illustrative photos, not UC San Diego dining menu items.</p>
    </section>
  );
}

/** Illustrative split: a comfortable total that hides one wallet running low. Bars fill in when revealed. */
function SplitTotal() {
  return (
    <div className="intro-split" role="img" aria-label="Illustration: a $620 total made of $580 in Dining Dollars and $40 in Triton Cash. Triton Cash runs low first.">
      <span className="preview-tag">Illustration</span>
      <SpectrumShape variant="orb" drift className="intro-split-orb" />
      <SpeckleField edge="top-right" count={40} seed={83} className="intro-split-speckles" />
      <div className="relative">
        <span className="metric-label text-white/70">Total balance</span>
        <strong className="campus-glass-value block">$620.00</strong>
        <span className="text-sm text-white/75">Looks fine…</span>
      </div>
      <div className="intro-split-bar" aria-hidden="true">
        <span className="intro-split-dining" style={{ width: "93.5%" }} />
        <span className="intro-split-cash" style={{ width: "6.5%" }} />
      </div>
      <div className="relative flex flex-wrap justify-between gap-2 text-sm text-white/85">
        <span><span className="intro-dot intro-dot-dining" /> Dining Dollars $580.00</span>
        <span><span className="intro-dot intro-dot-cash" /> Triton Cash $40.00</span>
      </div>
      <p className="relative mt-2 text-base font-semibold text-white">…but Triton Cash runs out weeks earlier.</p>
    </div>
  );
}

function Problem() {
  return (
    <section id="problem" tabIndex={-1} className="intro-section intro-anchor" aria-labelledby="intro-problem-title">
      <SectionHeading id="intro-problem-title" eyebrow="The problem" title="Managing two wallets shouldn’t be a guessing game." />
      <div className="intro-problem-grid">
        <ul className="intro-problem-cards">
          {PROBLEMS.map(({ icon: Icon, title, text }, index) => (
            <li key={title} className="intro-card" data-reveal style={delay(index)}>
              <span className="feature-card-icon intro-icon"><Icon size={22} aria-hidden="true" /></span>
              <strong>{title}</strong>
              <span>{text}</span>
            </li>
          ))}
        </ul>
        <div className="intro-split-wrap" data-reveal style={delay(2)}>
          <SplitTotal />
          <p className="intro-split-caption"><Scale size={16} aria-hidden="true" /> A healthy total can hide a wallet that’s running low.</p>
        </div>
      </div>
    </section>
  );
}

/** Illustrative chart: dated updates, the learned pace continuing as a prediction, and an ideal path. */
function LearningSketch() {
  return (
    <figure className="intro-card intro-sketch-card" data-reveal>
      <div className="intro-sketch">
        <svg viewBox="0 0 400 130" role="img" aria-label="Illustration: four dated balance updates form a downward line; a dashed prediction with a shaded range continues it, next to a straight ideal path.">
          <path className="intro-sketch-band" d="M228 68 L384 100 L384 126 Z" />
          <path className="intro-sketch-ideal" pathLength={1} d="M228 68 L384 94" />
          <path className="intro-sketch-predicted" pathLength={1} d="M228 68 L384 113" />
          <path className="intro-sketch-actual" pathLength={1} d="M24 16 L92 32 L160 44 L228 68" />
          {[[24, 16], [92, 32], [160, 44], [228, 68]].map(([x, y], index) => (
            <circle key={x} className="intro-sketch-dot" cx={x} cy={y} r="5.5" style={delay(index + 2)} />
          ))}
        </svg>
      </div>
      <figcaption className="intro-sketch-side">
        <ul className="intro-sketch-legend">
          <li><i className="intro-key intro-key-actual" /><span><strong>Your updates</strong>Dated balances you saved</span></li>
          <li><i className="intro-key intro-key-predicted" /><span><strong>Predicted</strong>Continues your learned pace</span></li>
          <li><i className="intro-key intro-key-ideal" /><span><strong>Ideal</strong>An even path to your target</span></li>
        </ul>
        <p className="notice-info intro-note"><Info size={16} aria-hidden="true" /><span>A transparent statistical model. It sees net balance changes, never individual purchases.</span></p>
      </figcaption>
    </figure>
  );
}

function Solution() {
  return (
    <section className="intro-section" aria-labelledby="intro-solution-title">
      <SectionHeading id="intro-solution-title" eyebrow="How TritonSpend helps" title="One place to plan both wallets." />
      <LearningSketch />
      <div className="intro-solution-grid">
        <div className="intro-card intro-card-panel" data-reveal>
          <h3 className="intro-card-title">For you</h3>
          <PointList points={FOR_YOU} />
        </div>
        <div className="intro-card intro-card-panel" data-reveal style={delay(1)}>
          <h3 className="intro-card-title">Behind the scenes</h3>
          <PointList points={BEHIND_THE_SCENES} />
        </div>
      </div>
    </section>
  );
}

// Curved connectors. Desktop arcs over the gap between two icons; mobile bends down the icon column.
// Each ends in its own chevron along the curve's final direction, so the flow reads left-to-right / top-to-bottom.
const ARC = "M4 30 C 36 2, 84 2, 112 28";
const ARC_HEAD = "M110.3 20.2 L112 28 L104.1 26.9";
const DROP = "M16 2 C 44 10, 24 22, 24 36";
const DROP_HEAD = "M19 30 L24 36 L29 30";

function Connector({ index }: { index: number }) {
  const style = { "--i": index } as React.CSSProperties;
  return (
    <>
      <svg className="intro-connector intro-connector-arc" viewBox="0 0 120 36" aria-hidden="true" style={style}>
        <path className="intro-connector-track" pathLength={1} d={ARC} />
        <path className="intro-connector-glint" pathLength={1} d={ARC} />
        <path className="intro-connector-head" d={ARC_HEAD} />
      </svg>
      <svg className="intro-connector intro-connector-drop" viewBox="0 0 48 40" aria-hidden="true" style={style}>
        <path className="intro-connector-track" pathLength={1} d={DROP} />
        <path className="intro-connector-glint" pathLength={1} d={DROP} />
        <path className="intro-connector-head" d={DROP_HEAD} />
      </svg>
    </>
  );
}

function Flow() {
  return (
    <section className="intro-section" aria-labelledby="intro-flow-title">
      <SectionHeading id="intro-flow-title" eyebrow="How it works" title="Five steps to a clear picture." />
      <ol className="intro-flow" data-reveal>
        {STEPS.map(({ icon: Icon, title, text }, index) => (
          <li key={title} className="intro-step" style={{ "--i": index } as React.CSSProperties}>
            <span className="intro-step-icon"><Icon size={22} aria-hidden="true" /><span className="intro-step-number">{index + 1}</span></span>
            <strong>{title}</strong>
            <span>{text}</span>
            {index < STEPS.length - 1 && <Connector index={index} />}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Signed-out introduction below the hero: why students use TritonSpend and how it works. */
export function LandingIntro() {
  const ref = useScrollReveal<HTMLDivElement>();
  return (
    <div ref={ref} className="intro">
      <FoodMoments />
      <Problem />
      <Solution />
      <Flow />
    </div>
  );
}
