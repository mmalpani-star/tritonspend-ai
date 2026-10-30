/**
 * Campus spots a student can pick instead of sharing their location. Coordinates are the official
 * campus map's "Campus Points Of Interest - Public" layer entries for these places, checked 2026-10-30.
 */
import type { LatLng } from "./food-venues";

export type Landmark = LatLng & { id: string; name: string };

export const CAMPUS_LANDMARKS: Landmark[] = [
  { id: "geisel-library", name: "Geisel Library", lat: 32.881479, lng: -117.23762 },
  { id: "price-center", name: "Price Center", lat: 32.879368, lng: -117.237007 },
  { id: "student-services-center", name: "Student Services Center", lat: 32.87886, lng: -117.235878 },
  { id: "pepper-canyon-hall", name: "Pepper Canyon Hall", lat: 32.878445, lng: -117.233795 },
  { id: "central-campus-trolley", name: "Central Campus Trolley Station", lat: 32.878848, lng: -117.232003 },
  { id: "main-gym", name: "Main Gymnasium", lat: 32.877144, lng: -117.241241 },
  { id: "rimac", name: "RIMAC", lat: 32.885197, lng: -117.239639 }
];
