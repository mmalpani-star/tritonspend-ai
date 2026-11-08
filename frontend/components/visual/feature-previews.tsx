import { CampusPhoto } from "./campus-photo";
import { SpeckleField } from "./speckle-field";
import { SpectrumShape } from "./spectrum-shape";

/** Visual preview for the Food Nearby placeholder. Decorative; no data. */
export function FoodPreviewVisual() {
  return (
    <div className="preview-visual" aria-hidden="true">
      <span className="preview-tag">Preview</span>
      <div className="food-collage">
        <CampusPhoto photo="priceCenterTriton" sizes="(min-width: 768px) 40vw, 60vw" decorative label className="food-collage-main" imageClassName="object-[50%_55%]" />
        <CampusPhoto photo="eucalyptusWalk" sizes="(min-width: 768px) 28vw, 40vw" decorative label />
        <CampusPhoto photo="laJollaShores" sizes="(min-width: 768px) 28vw, 40vw" decorative label imageClassName="object-[30%_50%]" />
      </div>
      <SpectrumShape variant="arc" drift className="food-preview-arc" />
      <SpeckleField edge="top-right" count={60} seed={61} className="food-preview-speckles" />
      <span className="food-chip food-chip-a" style={{ "--delay": "350ms" } as React.CSSProperties}>Food Chat<span>Venue ratings and chat</span></span>
      <span className="food-chip food-chip-b" style={{ "--delay": "550ms" } as React.CSSProperties}>Meal prep vs. dining<span>Compare cost per meal</span></span>
    </div>
  );
}

/** Visual preview for the Spending Trajectory placeholder: an illustrative chart, not real data. */
export function TrajectoryPreviewVisual() {
  return (
    <div className="preview-visual" aria-hidden="true">
      <span className="preview-tag">Illustration · not your data</span>
      <div className="trajectory-preview">
        <div className="trajectory-preview-photo">
          <CampusPhoto photo="laJollaShores" sizes="(min-width: 768px) 70vw, 100vw" decorative className="h-full w-full" />
        </div>
        <SpectrumShape variant="orb" drift className="trajectory-preview-orb" />
        <SpeckleField edge="bottom" count={70} seed={73} className="trajectory-preview-speckles" />
        <svg viewBox="0 0 600 260" preserveAspectRatio="none">
          <defs>
            <linearGradient id="trajectory-current" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" style={{ stopColor: "var(--spec-a)" }} />
              <stop offset="0.45" style={{ stopColor: "var(--spec-b)" }} />
              <stop offset="0.75" style={{ stopColor: "var(--spec-c)" }} />
              <stop offset="1" style={{ stopColor: "var(--spec-d)" }} />
            </linearGradient>
            <linearGradient id="trajectory-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" style={{ stopColor: "var(--spec-c)", stopOpacity: 0.35 }} />
              <stop offset="1" style={{ stopColor: "var(--spec-a)", stopOpacity: 0 }} />
            </linearGradient>
          </defs>
          {[60, 120, 180].map((y) => <line key={y} x1="40" x2="580" y1={y} y2={y} stroke="rgb(255 255 255 / 0.12)" strokeWidth="1" />)}
          <path d="M40 40 C 180 70, 300 120, 580 210 L 580 240 L 40 240 Z" fill="url(#trajectory-area)" opacity="0.8" />
          <path className="trajectory-path-ideal" pathLength={1} d="M40 40 L 580 200" fill="none" stroke="var(--ucsd-yellow)" strokeWidth="2.5" strokeLinecap="round" />
          <path className="trajectory-path-current" pathLength={1} d="M40 40 C 180 70, 300 120, 580 210" fill="none" stroke="url(#trajectory-current)" strokeWidth="4" strokeLinecap="round" />
        </svg>
        <span className="trajectory-alert">Low-balance alert · Triton Cash</span>
      </div>
    </div>
  );
}
