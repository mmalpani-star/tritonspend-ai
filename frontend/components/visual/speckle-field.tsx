type Edge = "top" | "right" | "bottom" | "left" | "top-right" | "bottom-left";

type Props = {
  /** Where speckles concentrate; density falls off away from this edge. */
  edge: Edge;
  /** Kept small on purpose: the texture should stay sparse. */
  count?: number;
  seed?: number;
  className?: string;
};

// Deterministic PRNG so server and client render identical markup.
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const W = 400;
const H = 300;
// Colour classes map to per-theme speckle tokens in visual.css.
const COLOR_CLASSES = ["speckle-c0", "speckle-c1", "speckle-c2", "speckle-c3"];

function distanceToEdge(edge: Edge, x: number, y: number): number {
  const nx = x / W;
  const ny = y / H;
  switch (edge) {
    case "top": return ny;
    case "bottom": return 1 - ny;
    case "left": return nx;
    case "right": return 1 - nx;
    case "top-right": return Math.min(ny, 1 - nx);
    case "bottom-left": return Math.min(1 - ny, nx);
  }
}

/** Sparse blue-purple stipple concentrated near one edge. Static SVG, no animation. */
export function SpeckleField({ edge, count = 70, seed = 7, className = "" }: Props) {
  const random = mulberry32(seed);
  const dots: { x: number; y: number; r: number; color: string; opacity: number }[] = [];
  for (let attempts = 0; dots.length < count && attempts < count * 60; attempts += 1) {
    const x = random() * W;
    const y = random() * H;
    // Rejection sampling: keep a point with probability that decays away from the edge.
    if (random() > Math.exp(-distanceToEdge(edge, x, y) * 7)) continue;
    dots.push({
      x,
      y,
      r: 0.5 + random() * 1.1,
      color: COLOR_CLASSES[Math.floor(random() * COLOR_CLASSES.length)],
      opacity: 0.25 + random() * 0.4
    });
  }
  return (
    <svg className={`speckle-field ${className}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      {dots.map((dot, index) => (
        <circle key={index} className={dot.color} cx={dot.x.toFixed(1)} cy={dot.y.toFixed(1)} r={dot.r.toFixed(2)} opacity={dot.opacity.toFixed(2)} />
      ))}
    </svg>
  );
}
