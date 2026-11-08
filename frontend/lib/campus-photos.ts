/**
 * Campus photography used by the visual language. Every photo is an openly
 * licensed Wikimedia Commons image stored as a resized local copy in
 * public/campus/. Attribution is required for all of them and is rendered by
 * <PhotoCredits />. These are not official UC San Diego assets.
 */
export type CampusPhotoId =
  | "geiselLibrary" | "geiselDetail" | "priceCenterTriton" | "eucalyptusWalk" | "laJollaShores"
  | "priceCenterEast" | "warrenMall" | "libraryWalk" | "conradPrebys" | "scrippsPier";

export type CampusPhoto = {
  src: string;
  width: number;
  height: number;
  alt: string;
  place: string;
  credit: { author: string; license: string; licenseUrl: string; source: string };
};

const RESIZED_NOTE = "Resized for the web.";

export const CAMPUS_PHOTOS: Record<CampusPhotoId, CampusPhoto> = {
  geiselLibrary: {
    src: "/campus/geisel-library.jpg",
    width: 2400,
    height: 1600,
    alt: "Geisel Library at UC San Diego, its stacked concrete and glass tiers rising above native plantings",
    place: "Geisel Library",
    credit: {
      author: "Jami (Wiki Ed)",
      license: "CC BY-SA 4.0",
      licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
      source: "https://commons.wikimedia.org/wiki/File:Geisel_Library,_UCSD,_October_2016.jpg"
    }
  },
  geiselDetail: {
    src: "/campus/geisel-detail.jpg",
    width: 1200,
    height: 900,
    alt: "Close-up of Geisel Library's angled concrete supports against a blue sky",
    place: "Geisel Library",
    credit: {
      author: "sarahmirk",
      license: "CC BY 4.0",
      licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
      source: "https://commons.wikimedia.org/wiki/File:Geisel_Library_at_UCSD.jpg"
    }
  },
  priceCenterTriton: {
    src: "/campus/price-center-triton.jpg",
    width: 1200,
    height: 900,
    alt: "Bronze Triton statue and fountain in front of the Price Center East steps",
    place: "Price Center · Triton statue",
    credit: {
      author: "Tktktk",
      license: "CC BY 3.0",
      licenseUrl: "https://creativecommons.org/licenses/by/3.0/",
      source: "https://commons.wikimedia.org/wiki/File:Price_Center_East_Triton,_UCSD.JPG"
    }
  },
  eucalyptusWalk: {
    src: "/campus/eucalyptus-walk.jpg",
    width: 1200,
    height: 900,
    alt: "Students walking along a path through the UC San Diego eucalyptus grove",
    place: "Eucalyptus grove",
    credit: {
      author: "FASTILY",
      license: "CC BY-SA 4.0",
      licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
      source: "https://commons.wikimedia.org/wiki/File:UCSD_Eucalyptus_Grove_2_2016-05-14.jpg"
    }
  },
  laJollaShores: {
    src: "/campus/la-jolla-shores.jpg",
    width: 1600,
    height: 900,
    alt: "La Jolla Shores beach and coastline seen from Scripps Pier",
    place: "La Jolla Shores",
    credit: {
      author: "RightCowLeftCoast",
      license: "CC BY-SA 4.0",
      licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
      source: "https://commons.wikimedia.org/wiki/File:La_Jolla_Shores_from_Scripps_Pier.jpg"
    }
  },
  priceCenterEast: {
    src: "/campus/price-center-east.jpg",
    width: 1600,
    height: 1200,
    alt: "Price Center East at UC San Diego, a glass and white-panel student center under a clear blue sky",
    place: "Price Center",
    credit: {
      author: "Tktktk",
      license: "CC BY 3.0",
      licenseUrl: "https://creativecommons.org/licenses/by/3.0",
      source: "https://commons.wikimedia.org/wiki/File:Price_Center_East_-_North_Entrance,_UCSD.JPG"
    }
  },
  warrenMall: {
    src: "/campus/warren-mall.jpg",
    width: 1600,
    height: 1200,
    alt: "Warren Mall at UC San Diego, a wide paved walkway lined with trees and lawns",
    place: "Warren Mall",
    credit: {
      author: "Tktktk",
      license: "CC BY 3.0",
      licenseUrl: "https://creativecommons.org/licenses/by/3.0",
      source: "https://commons.wikimedia.org/wiki/File:Warren_Mall,_UCSD.JPG"
    }
  },
  libraryWalk: {
    src: "/campus/library-walk.jpg",
    width: 1400,
    height: 1040,
    alt: "Library Walk at UC San Diego, a long pedestrian path through eucalyptus trees",
    place: "Library Walk",
    credit: {
      author: "Znode at English Wikipedia",
      license: "CC BY-SA 3.0",
      licenseUrl: "http://creativecommons.org/licenses/by-sa/3.0/",
      source: "https://commons.wikimedia.org/wiki/File:Ucsd-librarywalk.JPG"
    }
  },
  conradPrebys: {
    src: "/campus/conrad-prebys.jpg",
    width: 1600,
    height: 1200,
    alt: "Students walking past the white colonnade of the Conrad Prebys Music Center at UC San Diego",
    place: "Conrad Prebys Music Center",
    credit: {
      author: "Tktktk",
      license: "CC BY 3.0",
      licenseUrl: "https://creativecommons.org/licenses/by/3.0",
      source: "https://commons.wikimedia.org/wiki/File:Conrad_Prebys_Music_Center,_UCSD.JPG"
    }
  },
  scrippsPier: {
    src: "/campus/scripps-pier.jpg",
    width: 1600,
    height: 1001,
    alt: "Shorebirds wading in front of the Scripps Pier at UC San Diego's Scripps Institution of Oceanography",
    place: "Scripps Pier",
    credit: {
      author: "Mkeipper",
      license: "CC BY-SA 3.0",
      licenseUrl: "https://creativecommons.org/licenses/by-sa/3.0",
      source: "https://commons.wikimedia.org/wiki/File:Scripps_Pier_La_Jolla_CA.jpg"
    }
  }
};

export const PHOTO_MODIFICATION_NOTE = RESIZED_NOTE;
