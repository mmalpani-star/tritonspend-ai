import Image from "next/image";
import { CAMPUS_PHOTOS, CampusPhotoId } from "../../lib/campus-photos";

type Props = {
  photo: CampusPhotoId;
  /** Responsive sizes hint for next/image. */
  sizes: string;
  priority?: boolean;
  /** Show the place name chip over the photo. */
  label?: boolean;
  className?: string;
  imageClassName?: string;
  /** Use alt="" when the photo is purely decorative (e.g. inside a labelled link). */
  decorative?: boolean;
};

/**
 * A campus photo in a fixed-ratio frame (no layout shift while loading).
 * next/image serves resized WebP/AVIF from the local JPEG.
 */
export function CampusPhoto({ photo, sizes, priority = false, label = false, className = "", imageClassName = "", decorative = false }: Props) {
  const data = CAMPUS_PHOTOS[photo];
  return (
    <figure className={`campus-photo ${className}`}>
      <Image src={data.src} alt={decorative ? "" : data.alt} fill sizes={sizes} priority={priority} className={`object-cover ${imageClassName}`} />
      {label && <figcaption className="campus-photo-label">{data.place}</figcaption>}
    </figure>
  );
}
