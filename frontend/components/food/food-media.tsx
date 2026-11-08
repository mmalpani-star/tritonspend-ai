import Image from "next/image";
import { FOOD_PHOTOS, FoodPhotoId, foodCategories, photosFor } from "../../lib/food-photos";

/**
 * Food photography for Food Nearby. Photos come from the licensed library in lib/food-photos.ts and
 * are always presented as illustrative: they show the kind of food a place is about, never a dish
 * a venue is known to serve today.
 */

type PlaceTexts = (string | null | undefined)[];

export function FoodPhotoImage({ id, sizes, priority = false, decorative = false, className = "" }: {
  id: FoodPhotoId;
  sizes: string;
  priority?: boolean;
  decorative?: boolean;
  className?: string;
}) {
  const photo = FOOD_PHOTOS[id];
  return (
    <Image
      src={photo.src}
      alt={decorative ? "" : `Illustrative photo: ${photo.alt}`}
      fill
      sizes={sizes}
      priority={priority}
      loading={priority ? undefined : "lazy"}
      className={`object-cover ${className}`}
      style={{ objectPosition: photo.position ?? "50% 50%" }}
    />
  );
}

/** Stable illustrative photos for a venue or station, from its own name, summary and tags. */
export function placePhotos(key: string, texts: PlaceTexts, kind: string | undefined, count: number): FoodPhotoId[] {
  return photosFor(key, foodCategories(texts, kind), count);
}

/** The Food Nearby hero: one large plate with smaller plates floating around it. */
export function FoodMosaic({ ids }: { ids: [FoodPhotoId, FoodPhotoId, FoodPhotoId, FoodPhotoId, FoodPhotoId] }) {
  return (
    <div className="food-mosaic" aria-hidden="true">
      {ids.map((id, index) => (
        <span key={id} className="food-mosaic-tile">
          <FoodPhotoImage id={id} decorative priority={index < 2} sizes={index === 0 ? "(min-width: 1024px) 34vw, 70vw" : "(min-width: 1024px) 14vw, 30vw"} />
        </span>
      ))}
    </div>
  );
}

/** A venue card's cover photo, labelled as illustrative. */
export function VenueCover({ placeKey, texts, kind, photoId }: { placeKey: string; texts: PlaceTexts; kind?: string; photoId?: FoodPhotoId }) {
  const id = photoId ?? placePhotos(placeKey, texts, kind, 1)[0];
  return (
    <span className="food-cover">
      <FoodPhotoImage id={id} sizes="(min-width: 1700px) 22vw, (min-width: 1180px) 30vw, (min-width: 720px) 46vw, 92vw" />
      <span className="photo-tag" aria-hidden="true">Illustrative · {FOOD_PHOTOS[id].caption}</span>
    </span>
  );
}

/** A three-photo banner for a venue page. */
export function VenueBanner({ placeKey, texts, kind }: { placeKey: string; texts: PlaceTexts; kind?: string }) {
  const ids = placePhotos(placeKey, texts, kind, 3);
  return (
    <div className="venue-banner">
      {ids.map((id, index) => (
        <span key={id}>
          <FoodPhotoImage id={id} priority={index === 0} sizes={index === 0 ? "(min-width: 640px) 62vw, 92vw" : "30vw"} />
          {index === 0 && <span className="photo-tag" aria-hidden="true">Illustrative photos</span>}
        </span>
      ))}
    </div>
  );
}

/** A single wide photo for a station page. */
export function StationBanner({ placeKey, texts }: { placeKey: string; texts: PlaceTexts }) {
  const [id] = placePhotos(placeKey, texts, undefined, 1);
  return (
    <div className="station-banner">
      <FoodPhotoImage id={id} priority sizes="92vw" />
      <span className="photo-tag" aria-hidden="true">Illustrative · {FOOD_PHOTOS[id].caption}</span>
    </div>
  );
}
