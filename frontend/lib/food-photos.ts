/**
 * Food photography for the hero's rotating photo cards. Every photo is an
 * openly licensed Wikimedia Commons image (CC0 or CC BY 2.0) stored as a
 * resized local copy in public/food/. None of them were taken at UC San Diego,
 * so captions name only the kind of dish, never a campus dining location.
 */
export type FoodPhotoId =
  | "sushiPlatter"
  | "shoyuRamen"
  | "gourmetBurger"
  | "margheritaPizza"
  | "acaiBowl"
  | "honeyPancakes"
  | "salmonPokeBowl"
  | "italianSandwich";

export type FoodPhoto = {
  src: string;
  width: number;
  height: number;
  alt: string;
  caption: string;
  /** object-position that keeps the dish centred when cropped to the card. */
  position?: string;
  credit: { author: string; license: string; licenseUrl: string; source: string };
};

const CC0 = { license: "CC0 1.0", licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/" };
const CC_BY_2 = { license: "CC BY 2.0", licenseUrl: "https://creativecommons.org/licenses/by/2.0/" };

export const FOOD_PHOTOS: Record<FoodPhotoId, FoodPhoto> = {
  sushiPlatter: {
    src: "/food/sushi-platter.jpg",
    width: 1000,
    height: 750,
    alt: "Salmon and tuna nigiri with salmon roses on a slate board",
    caption: "Sushi",
    credit: { author: "Mojmir Churavy", ...CC0, source: "https://commons.wikimedia.org/wiki/File:Sushi_Plate_in_Organic_Sushi_Prague_4.jpg" }
  },
  shoyuRamen: {
    src: "/food/shoyu-ramen.jpg",
    width: 1000,
    height: 666,
    alt: "Bowl of shoyu ramen with soft-boiled eggs, narutomaki and green onion",
    caption: "Ramen",
    credit: { author: "Guilhem Vellut", ...CC_BY_2, source: "https://commons.wikimedia.org/wiki/File:Shoyu_Ramen.jpg" }
  },
  gourmetBurger: {
    src: "/food/gourmet-burger.jpg",
    width: 1000,
    height: 750,
    alt: "Burger on a glossy brioche bun with red onion and greens",
    caption: "Burgers",
    credit: { author: "Eaters Collective", ...CC0, source: "https://commons.wikimedia.org/wiki/File:Gourmet_Hamburger_(Unsplash).jpg" }
  },
  margheritaPizza: {
    src: "/food/margherita-pizza.jpg",
    width: 1000,
    height: 662,
    alt: "Margherita pizza topped with roasted cherry tomatoes, mozzarella and basil",
    caption: "Pizza",
    credit: { author: "jeffreyw", ...CC_BY_2, source: "https://commons.wikimedia.org/wiki/File:Pizza_Margherita_(14565452088).jpg" }
  },
  acaiBowl: {
    src: "/food/acai-bowl.jpg",
    width: 1000,
    height: 667,
    alt: "Açaí bowl piled with raspberries, blueberries and blackberries",
    caption: "Açaí bowls",
    position: "50% 40%",
    credit: { author: "Ella Olsson", ...CC_BY_2, source: "https://commons.wikimedia.org/wiki/File:Berries_Galore_Acai_Bowl_(30276166867).jpg" }
  },
  honeyPancakes: {
    src: "/food/honey-pancakes.jpg",
    width: 800,
    height: 1000,
    alt: "Stack of pancakes with walnuts and honey being poured on top",
    caption: "Breakfast",
    position: "50% 62%",
    credit: { author: "Mae Mu (Foodiesfeed)", ...CC0, source: "https://commons.wikimedia.org/wiki/File:Foodiesfeed.com_pouring-honey-on-pancakes-with-walnuts.jpg" }
  },
  salmonPokeBowl: {
    src: "/food/salmon-poke-bowl.jpg",
    width: 1000,
    height: 750,
    alt: "Salmon poke bowl with edamame, avocado, cucumber and seaweed",
    caption: "Poke bowls",
    credit: { author: "Andy Li", ...CC0, source: "https://commons.wikimedia.org/wiki/File:Salmon_Poke_Bowl_(S)_with_Spicy_mayo_sauce_-_Kitokito.jpg" }
  },
  italianSandwich: {
    src: "/food/italian-sandwich.jpg",
    width: 1000,
    height: 801,
    alt: "Italian deli sandwich layered with cured meats, cheese and greens",
    caption: "Sandwiches",
    credit: { author: "Eaters Collective", ...CC0, source: "https://commons.wikimedia.org/wiki/File:Italian_Sandwich_(Unsplash).jpg" }
  }
};
