import { CAMPUS_PHOTOS, PHOTO_MODIFICATION_NOTE } from "../../lib/campus-photos";
import { FOOD_PHOTOS } from "../../lib/food-photos";

type Credit = { author: string; license: string; licenseUrl: string; source: string };

function CreditLine({ label, credit }: { label: string; credit: Credit }) {
  return (
    <li>
      {label}: <a href={credit.source} target="_blank" rel="noreferrer">photo</a> by {credit.author}, licensed <a href={credit.licenseUrl} target="_blank" rel="noreferrer">{credit.license}</a>.
    </li>
  );
}

/** Required attribution for the campus and food photography. */
export function PhotoCredits() {
  return (
    <details className="photo-credits">
      <summary>Photo credits</summary>
      <ul className="mt-2 space-y-1">
        {Object.values(CAMPUS_PHOTOS).map((photo) => <CreditLine key={photo.src} label={photo.place} credit={photo.credit} />)}
      </ul>
      <p className="mt-3 font-semibold">Food photos</p>
      <ul className="mt-1 space-y-1">
        {Object.values(FOOD_PHOTOS).map((photo) => <CreditLine key={photo.src} label={photo.caption} credit={photo.credit} />)}
      </ul>
      <p className="mt-2">Food photos are illustrative and were not taken at UC San Diego dining locations.</p>
      <p className="mt-2">Via Wikimedia Commons. {PHOTO_MODIFICATION_NOTE} TritonSpend is an independent student project and is not affiliated with or endorsed by UC San Diego.</p>
    </details>
  );
}
