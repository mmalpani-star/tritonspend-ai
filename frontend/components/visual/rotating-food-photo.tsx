"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { FOOD_PHOTOS, FoodPhotoId } from "../../lib/food-photos";

const ROTATE_EVERY_MS = 6000;

type Props = {
  photos: FoodPhotoId[];
  /** Responsive sizes hint for next/image. */
  sizes: string;
  /** Extra delay before the first change, so neighbouring cards don't swap together. */
  offsetMs?: number;
  className?: string;
};

/**
 * A fixed-ratio photo frame that crossfades through food photos every ~6s.
 * All layers stay mounted (already loaded, no layout shift); only opacity changes.
 * Rotation stops under reduced motion, while the tab is hidden, and while hovered.
 */
export function RotatingFoodPhoto({ photos, sizes, offsetMs = 0, className = "" }: Props) {
  const [active, setActive] = useState(0);
  const hovered = useRef(false);
  const resume = useRef<() => void>(() => {});

  useEffect(() => {
    if (photos.length < 2) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: number | undefined;
    let firstRun = true;
    const stop = () => {
      window.clearTimeout(timer);
      timer = undefined;
    };
    const sync = () => {
      if (document.hidden || reducedMotion.matches || hovered.current) return stop();
      if (timer !== undefined) return;
      const delay = ROTATE_EVERY_MS + (firstRun ? offsetMs : 0);
      firstRun = false;
      timer = window.setTimeout(() => {
        timer = undefined;
        setActive((index) => (index + 1) % photos.length);
        sync();
      }, delay);
    };
    resume.current = sync;
    sync();
    document.addEventListener("visibilitychange", sync);
    reducedMotion.addEventListener("change", sync);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", sync);
      reducedMotion.removeEventListener("change", sync);
    };
  }, [photos.length, offsetMs]);

  const setHovered = (value: boolean) => {
    hovered.current = value;
    resume.current();
  };

  return (
    <div
      className={`campus-photo food-rotator ${className}`}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      {photos.map((id, index) => {
        const photo = FOOD_PHOTOS[id];
        return (
          <div key={id} className={`food-layer ${index === active ? "food-layer-active" : ""}`}>
            <Image src={photo.src} alt="" fill sizes={sizes} className="object-cover" style={photo.position ? { objectPosition: photo.position } : undefined} />
          </div>
        );
      })}
      {photos.map((id, index) => (
        <span key={id} className={`campus-photo-label food-caption ${index === active ? "food-caption-active" : ""}`}>
          {FOOD_PHOTOS[id].caption}
        </span>
      ))}
    </div>
  );
}
