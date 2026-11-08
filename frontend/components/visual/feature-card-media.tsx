"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { CAMPUS_PHOTOS, CampusPhotoId } from "../../lib/campus-photos";
import { RotatingFoodPhoto } from "./rotating-food-photo";
import { FoodPhotoImage } from "../food/food-media";

/** How long each campus photo stays before crossfading to the next. */
export const CAMPUS_ROTATE_MS = 30_000;

/**
 * Create Forecast card: UCSD campus photos that crossfade every 30 seconds. Every layer stays
 * mounted (already loaded, no layout shift); only opacity changes. Rotation pauses while the tab is
 * hidden and is off under reduced motion (the first photo, Geisel Library, stays).
 */
export function RotatingCampusPhoto({ photos, sizes, intervalMs = CAMPUS_ROTATE_MS }: { photos: CampusPhotoId[]; sizes: string; intervalMs?: number }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (photos.length < 2) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: number | undefined;
    const stop = () => { window.clearTimeout(timer); timer = undefined; };
    const sync = () => {
      if (document.hidden || reducedMotion.matches) return stop();
      if (timer !== undefined) return;
      timer = window.setTimeout(() => {
        timer = undefined;
        setActive((index) => (index + 1) % photos.length);
        sync();
      }, intervalMs);
    };
    sync();
    document.addEventListener("visibilitychange", sync);
    reducedMotion.addEventListener("change", sync);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", sync);
      reducedMotion.removeEventListener("change", sync);
    };
  }, [photos.length, intervalMs]);

  return (
    <span className="campus-rotator" data-active={photos[active]}>
      {photos.map((id, index) => {
        const photo = CAMPUS_PHOTOS[id];
        return (
          <span key={id} className={`campus-rotator-layer ${index === active ? "is-active" : ""}`}>
            <Image src={photo.src} alt="" fill sizes={sizes} priority={index === 0} className="object-cover" />
          </span>
        );
      })}
      <span className="campus-rotator-place">{CAMPUS_PHOTOS[photos[active]].place}</span>
    </span>
  );
}

/** Food Nearby card: a food collage — a large plate plus two tiles that slowly alternate dishes. */
export function FoodCollage({ sizes }: { sizes: string }) {
  return (
    <span className="food-collage-card">
      <span className="food-collage-main">
        <FoodPhotoImage id="gourmetPizza" decorative sizes={sizes} />
        <span className="photo-tag">Illustrative food photos</span>
      </span>
      <RotatingFoodPhoto photos={["sushiPlatter", "salmonPokeBowl", "friedRice"]} sizes="(min-width: 768px) 12vw, 40vw" className="food-collage-tile" />
      <RotatingFoodPhoto photos={["shoyuRamen", "burgerAndFries", "tacos"]} sizes="(min-width: 768px) 12vw, 40vw" offsetMs={3000} className="food-collage-tile" />
    </span>
  );
}

/** Spending Trajectory card: an illustration of balance trajectories in the chart's own language —
 * saved-balance dots, a glowing prediction with its range, a dashed ideal and a travelling dot. */
export function TrajectoryArt() {
  const actual: [number, number][] = [[40, 92], [86, 112], [128, 124], [170, 146], [214, 158], [256, 176]];
  const predicted = "M256,176 C320,196 380,214 440,226 S540,246 584,254";
  return (
    <svg className="trajectory-art" viewBox="0 0 600 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="ta-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#070b26" />
          <stop offset="0.55" stopColor="#1a1d6e" />
          <stop offset="1" stopColor="#4b1f8f" />
        </linearGradient>
        <radialGradient id="ta-glow-a" cx="0.2" cy="0.1" r="0.6"><stop offset="0" stopColor="#36c4ff" stopOpacity="0.45" /><stop offset="1" stopColor="#36c4ff" stopOpacity="0" /></radialGradient>
        <radialGradient id="ta-glow-b" cx="0.9" cy="0.95" r="0.55"><stop offset="0" stopColor="#ff5caa" stopOpacity="0.4" /><stop offset="1" stopColor="#ff5caa" stopOpacity="0" /></radialGradient>
        <linearGradient id="ta-line" x1="0" x2="1"><stop offset="0" stopColor="#5eead4" /><stop offset="0.5" stopColor="#7f9bff" /><stop offset="1" stopColor="#c084fc" /></linearGradient>
        <linearGradient id="ta-area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#7f9bff" stopOpacity="0.38" /><stop offset="1" stopColor="#7f9bff" stopOpacity="0" /></linearGradient>
        <filter id="ta-blur" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="6" /></filter>
      </defs>
      <rect width="600" height="300" fill="url(#ta-bg)" />
      <rect width="600" height="300" fill="url(#ta-glow-a)" />
      <rect width="600" height="300" fill="url(#ta-glow-b)" />
      {/* Grid and abstract balance figures. */}
      {[60, 110, 160, 210, 260].map((y) => <line key={y} x1="0" x2="600" y1={y} y2={y} stroke="#ffffff" strokeOpacity="0.07" />)}
      {[100, 200, 300, 400, 500].map((x) => <line key={x} x1={x} x2={x} y1="0" y2="300" stroke="#ffffff" strokeOpacity="0.05" />)}
      {["$1,000", "$750", "$500", "$250", "$0"].map((label, i) => (
        <text key={label} x="10" y={56 + i * 50} fill="#c7d2fe" fillOpacity="0.45" fontSize="11" fontFamily="ui-monospace, monospace">{label}</text>
      ))}
      <rect x="256" y="20" width="344" height="270" fill="#9b8bff" fillOpacity="0.06" />
      <line x1="256" x2="256" y1="20" y2="290" stroke="#c7d2fe" strokeOpacity="0.35" strokeDasharray="3 5" />
      {/* Slower–faster range, area and the glowing prediction. */}
      <path d="M256,176 C320,188 380,198 440,206 S540,222 584,228 L584,282 C540,272 480,262 440,250 S320,212 256,176 Z" fill="#9b8bff" fillOpacity="0.16" />
      <path d={`${predicted} L584,300 L256,300 Z`} fill="url(#ta-area)" />
      <path d="M256,176 L584,286" stroke="#c7d2fe" strokeOpacity="0.55" strokeWidth="2" strokeDasharray="8 7" fill="none" />
      <path d={predicted} stroke="url(#ta-line)" strokeWidth="9" fill="none" filter="url(#ta-blur)" opacity="0.7" />
      <path d={predicted} stroke="url(#ta-line)" strokeWidth="3.5" fill="none" strokeLinecap="round" className="trajectory-art-line" pathLength={1} />
      {actual.map(([x, y]) => (
        <g key={x}>
          <circle cx={x} cy={y} r="10" fill="#ff8a5c" fillOpacity="0.18" />
          <circle cx={x} cy={y} r="5" fill="#ff8a5c" stroke="#0b1236" strokeWidth="2" />
        </g>
      ))}
      <g className="trajectory-art-dot">
        <circle cx="440" cy="226" r="18" fill="#5eead4" fillOpacity="0.25" className="trajectory-art-halo" />
        <circle cx="440" cy="226" r="7" fill="#ffffff" stroke="#7f9bff" strokeWidth="3.5" />
      </g>
    </svg>
  );
}
