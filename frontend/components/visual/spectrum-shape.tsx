type Props = {
  /** "orb", "arc", or "pill" silhouettes; positioning comes from className. */
  variant?: "orb" | "arc" | "pill";
  /** Slow, restrained drift. Off by default; disabled under reduced motion. */
  drift?: boolean;
  className?: string;
};

/** Translucent purple → periwinkle → light-blue → cyan gradient shape. */
export function SpectrumShape({ variant = "orb", drift = false, className = "" }: Props) {
  return <span aria-hidden="true" className={`spectrum-shape spectrum-shape-${variant} ${drift ? "spectrum-drift" : ""} ${className}`} />;
}
