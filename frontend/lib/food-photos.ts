/**
 * The food photo library (asset manifest). Every photo is an openly licensed image from Wikimedia
 * Commons (CC0, CC BY or CC BY-SA; many are Unsplash photos mirrored there under CC0), stored as a
 * resized local copy in public/food/ — never hotlinked. None was taken at UC San Diego, so photos
 * are always presented as illustrative: captions and alt text name only the kind of dish, never a
 * campus venue, and nothing implies a dish is on any menu. Credits render in <PhotoCredits />.
 * No runtime imports so Node's test runner can load it directly.
 */

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

const PHOTOS = {
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
  },
  tacos: {
    src: "/food/tacos.jpg",
    width: 1200,
    height: 900,
    alt: "Three street tacos with carnitas, carne asada and al pastor, topped with onion and cilantro, with lime and radish",
    caption: "Tacos",
    credit: { author: "Larry Miller", license: "CC BY-SA 2.0", licenseUrl: "https://creativecommons.org/licenses/by-sa/2.0", source: "https://commons.wikimedia.org/wiki/File:001_Tacos_de_carnitas,_carne_asada_y_al_pastor.jpg" }
  },
  streetTacos: {
    src: "/food/street-tacos.jpg",
    width: 1200,
    height: 675,
    alt: "Close-up of tacos topped with diced onion and tomato, with lime wedges",
    caption: "Tacos",
    credit: { author: "Popo le Chien", license: "CC BY-SA 3.0", licenseUrl: "https://creativecommons.org/licenses/by-sa/3.0", source: "https://commons.wikimedia.org/wiki/File:Tacos_2.jpg" }
  },
  breakfastBurritos: {
    src: "/food/breakfast-burritos.jpg",
    width: 1200,
    height: 797,
    alt: "Two halved breakfast burritos filled with egg and potatoes, with cherry tomatoes",
    caption: "Burritos",
    credit: { author: "jeffreyw", license: "CC BY 2.0", licenseUrl: "https://creativecommons.org/licenses/by/2.0", source: "https://commons.wikimedia.org/wiki/File:Breakfast_burritos.jpg" }
  },
  friedChicken: {
    src: "/food/fried-chicken.jpg",
    width: 1200,
    height: 800,
    alt: "Basket of golden fried chicken pieces",
    caption: "Fried chicken",
    credit: { author: "Brian Chan", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Fried_Chicken_(Unsplash).jpg" }
  },
  chickenSandwich: {
    src: "/food/chicken-sandwich.jpg",
    width: 900,
    height: 1200,
    alt: "Crispy chicken sandwich with purple slaw on a glossy brioche bun",
    caption: "Chicken sandwich",
    credit: { author: "Eaters Collective", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Chicken_Sandwich_(Unsplash).jpg" }
  },
  pastaPlate: {
    src: "/food/pasta-plate.jpg",
    width: 1200,
    height: 877,
    alt: "Plate of wide ribbon pasta with herbs and grated cheese",
    caption: "Pasta",
    credit: { author: "Eaters Collective", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Plate_of_Pasta_(Unsplash).jpg" }
  },
  pestoPasta: {
    src: "/food/pesto-pasta.jpg",
    width: 1200,
    height: 800,
    alt: "Bow-tie pasta tossed in basil pesto with cherry tomatoes",
    caption: "Pasta",
    credit: { author: "Eaters Collective", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Pesto_Pasta_(Unsplash).jpg" }
  },
  noodleDish: {
    src: "/food/noodle-dish.jpg",
    width: 1200,
    height: 800,
    alt: "Stir-fried noodles with vegetables and sprouts on a wooden board, with chili and lime",
    caption: "Noodles",
    credit: { author: "Elli O.", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Noodle_Dish_(Unsplash).jpg" }
  },
  noodleBowl: {
    src: "/food/noodle-bowl.jpg",
    width: 1200,
    height: 800,
    alt: "White bowl of noodles with vegetables and fresh greens",
    caption: "Noodle bowl",
    credit: { author: "Tran Mau Tri Tam", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Noodle_Bowl_for_Lunch_(Unsplash).jpg" }
  },
  coffeeAndCake: {
    src: "/food/coffee-and-cake.jpg",
    width: 1200,
    height: 800,
    alt: "Cappuccino with latte art beside a slice of coffee cake",
    caption: "Coffee",
    credit: { author: "Stephanie McCabe", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Coffee_and_coffee_cake_(Unsplash).jpg" }
  },
  redCurry: {
    src: "/food/red-curry.jpg",
    width: 1200,
    height: 800,
    alt: "Bowl of red curry with vegetables, surrounded by peppercorns and dried chilies",
    caption: "Curry",
    credit: { author: "Elli O.", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Red_Curry_(Unsplash).jpg" }
  },
  latteCroissant: {
    src: "/food/latte-croissant.jpg",
    width: 1200,
    height: 900,
    alt: "Latte with leaf latte art next to a croissant",
    caption: "Coffee and pastry",
    credit: { author: "Sergey Zolkin", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Latte_and_croissant_(Unsplash).jpg" }
  },
  frothyCoffee: {
    src: "/food/frothy-coffee.jpg",
    width: 1200,
    height: 800,
    alt: "Overhead view of a frothy cappuccino with a spoon on a wooden table",
    caption: "Coffee",
    credit: { author: "Bryan Burgos", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Frothy_coffee_(Unsplash).jpg" }
  },
  dumplings: {
    src: "/food/dumplings.jpg",
    width: 1200,
    height: 800,
    alt: "Steamed dumplings with chopsticks on a wooden plate",
    caption: "Dumplings",
    credit: { author: "Charles Deluvio", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Dumplings_(Unsplash).jpg" }
  },
  galaxySmoothieBowl: {
    src: "/food/galaxy-smoothie-bowl.jpg",
    width: 1200,
    height: 827,
    alt: "Violet smoothie bowl topped with coconut and star-shaped fruit on a deep blue background",
    caption: "Smoothie bowl",
    credit: { author: "Brenda Godinez", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Galaxy_Smoothie_Bowl_(Unsplash).jpg" }
  },
  acaiSmoothieBowls: {
    src: "/food/acai-smoothie-bowls.jpg",
    width: 1200,
    height: 800,
    alt: "Two smoothie bowls topped with berries, grapefruit and star fruit",
    caption: "Smoothie bowls",
    credit: { author: "Brenda Godinez", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Acai_Smoothie_Bowls_(Unsplash).jpg" }
  },
  bakeryTreats: {
    src: "/food/bakery-treats.jpg",
    width: 800,
    height: 1200,
    alt: "Croissant and seeded energy bites on a dark table",
    caption: "Bakery",
    credit: { author: "Olenka Kotyk", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Rustic_Bakery_Treats_(Unsplash).jpg" }
  },
  freshBread: {
    src: "/food/fresh-bread.jpg",
    width: 1200,
    height: 800,
    alt: "Rows of crusty bread loaves behind a hand-lettered Fresh Bread sign",
    caption: "Bread",
    credit: { author: "Clem Onojeghuo", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Fresh_Loaves_of_Bread_(Unsplash).jpg" }
  },
  pho: {
    src: "/food/pho.jpg",
    width: 1200,
    height: 800,
    alt: "Red bowl of pho with noodles, herbs and broth",
    caption: "Pho",
    credit: { author: "Matthew Hamilton", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Pho_for_Dinner_(Unsplash).jpg" }
  },
  nachos: {
    src: "/food/nachos.jpg",
    width: 1200,
    height: 800,
    alt: "Plate of loaded nachos with cheese, peppers and sour cream",
    caption: "Nachos",
    credit: { author: "Herson Rodriguez", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Eating_Nachos_(Unsplash).jpg" }
  },
  truffleFries: {
    src: "/food/truffle-fries.jpg",
    width: 1200,
    height: 800,
    alt: "Cup of skinny fries dusted with herbs and parmesan",
    caption: "Fries",
    credit: { author: "Stephanie McCabe", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Truffle_Fries_(Unsplash).jpg" }
  },
  jellyDoughnuts: {
    src: "/food/jelly-doughnuts.jpg",
    width: 1200,
    height: 800,
    alt: "Trays of sugar-dusted jelly doughnuts",
    caption: "Doughnuts",
    credit: { author: "Leon Ephra\u00efm", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Jelly_Doughnuts_(Unsplash).jpg" }
  },
  burgerAndFries: {
    src: "/food/burger-and-fries.jpg",
    width: 1200,
    height: 800,
    alt: "Burger on a white plate with fries and a drink",
    caption: "Burger and fries",
    credit: { author: "quentin lagache", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Burgers_and_Fries_(Unsplash).jpg" }
  },
  marketProduce: {
    src: "/food/market-produce.jpg",
    width: 1200,
    height: 800,
    alt: "Market stall piled with apples, limes, peppers and other fresh produce",
    caption: "Fresh produce",
    credit: { author: "Julian Hanslmaier", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Farmer%27s_Market_Produce_(Unsplash).jpg" }
  },
  fruitWaffles: {
    src: "/food/fruit-waffles.jpg",
    width: 1200,
    height: 1092,
    alt: "Waffle topped with yogurt, blueberries and strawberries on a blue plate",
    caption: "Waffles",
    credit: { author: "Joseph Gonzalez", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Fruit_waffles_and_coffee_(Unsplash).jpg" }
  },
  greenGrocer: {
    src: "/food/green-grocer.jpg",
    width: 1200,
    height: 800,
    alt: "Colorful grocery display of fresh fruit and vegetables",
    caption: "Groceries",
    credit: { author: "ja ma", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Green_shop_(Unsplash).jpg" }
  },
  fruitMarket: {
    src: "/food/fruit-market.jpg",
    width: 1200,
    height: 675,
    alt: "Fruit stand with oranges, pineapples and price signs",
    caption: "Fruit market",
    credit: { author: "Redd Angelo", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Fruit_Market_(Unsplash).jpg" }
  },
  gourmetPizza: {
    src: "/food/gourmet-pizza.jpg",
    width: 1200,
    height: 800,
    alt: "Thin-crust pizza with arugula and fresh mozzarella, sliced",
    caption: "Pizza",
    credit: { author: "Brenan Greene", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Pizza_for_High-End_Italian_Restaurant_(Unsplash).jpg" }
  },
  saladBowl: {
    src: "/food/salad-bowl.jpg",
    width: 1200,
    height: 800,
    alt: "Plated salad with greens, vegetables and seeds",
    caption: "Salad",
    credit: { author: "Henrique F\u00e9lix", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Salad_Bowl_(Unsplash).jpg" }
  },
  friedRice: {
    src: "/food/fried-rice.jpg",
    width: 1200,
    height: 800,
    alt: "Hands holding a bowl of fried rice",
    caption: "Fried rice",
    credit: { author: "Kawin Harasai", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Fried_rice_(Unsplash).jpg" }
  },
  dimSum: {
    src: "/food/dim-sum.jpg",
    width: 1200,
    height: 806,
    alt: "Table of dim sum in bamboo steamers with tea cups",
    caption: "Dim sum",
    credit: { author: "Tara B", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Dim_Sum_Dinner_(Unsplash).jpg" }
  },
  matchaBubbleTea: {
    src: "/food/matcha-bubble-tea.jpg",
    width: 1200,
    height: 797,
    alt: "Glass of matcha milk tea with tapioca pearls and a straw",
    caption: "Bubble tea",
    credit: { author: "cyclonebill from Copenhagen, Denmark", license: "CC BY-SA 2.0", licenseUrl: "https://creativecommons.org/licenses/by-sa/2.0", source: "https://commons.wikimedia.org/wiki/File:Matcha_bubble_tea_(7660765558).jpg" }
  },
  fruityBreakfast: {
    src: "/food/fruity-breakfast.jpg",
    width: 1200,
    height: 800,
    alt: "Bowl of banana and blueberry breakfast with a cup of black coffee",
    caption: "Breakfast",
    credit: { author: "Nirzar Pangarkar", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Fruity_breakfast_(Unsplash).jpg" }
  },
  sandwichAndFries: {
    src: "/food/sandwich-and-fries.jpg",
    width: 1200,
    height: 797,
    alt: "Pulled-meat sandwich on a soft bun with crinkle-cut fries in a basket",
    caption: "Sandwich and fries",
    credit: { author: "Brandon Morgan", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Sandwich_with_Fries_(Unsplash).jpg" }
  },
  hummusPita: {
    src: "/food/hummus-pita.jpg",
    width: 1200,
    height: 900,
    alt: "Plate of homemade pita with hummus, diced tomato and onion",
    caption: "Hummus and pita",
    credit: { author: "Satdeep Gill", license: "CC BY-SA 4.0", licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0", source: "https://commons.wikimedia.org/wiki/File:Homemade_hummus_and_pita_03.jpg" }
  },
  freshSalad: {
    src: "/food/fresh-salad.jpg",
    width: 1200,
    height: 801,
    alt: "Fresh green salad on a white plate outdoors",
    caption: "Salad",
    credit: { author: "fireskystudios.com", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Fresh_Salad_(Unsplash).jpg" }
  },
  iceCreamCone: {
    src: "/food/ice-cream-cone.jpg",
    width: 1200,
    height: 800,
    alt: "Hand holding an ice cream cone against a sunset sky",
    caption: "Ice cream",
    credit: { author: "Alex Jones", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Ice_Cream_Dessert_(Unsplash).jpg" }
  },
  bagelBrunch: {
    src: "/food/bagel-brunch.jpg",
    width: 1200,
    height: 800,
    alt: "Brunch table with bagels and small plates",
    caption: "Brunch",
    credit: { author: "Toa Heftiba heftiba", license: "CC0", licenseUrl: "http://creativecommons.org/publicdomain/zero/1.0/deed.en", source: "https://commons.wikimedia.org/wiki/File:Bagel_Heaven_(Unsplash).jpg" }
  }
} satisfies Record<string, FoodPhoto>;

export type FoodPhotoId = keyof typeof PHOTOS;
export const FOOD_PHOTOS: Record<FoodPhotoId, FoodPhoto> = PHOTOS;

// --- Matching photos to venues and stations (illustrative only) --------------------------------

/** Dish families, each with photos that show that kind of food. */
export const FOOD_CATEGORIES = {
  pizza: ["gourmetPizza", "margheritaPizza"],
  burgers: ["burgerAndFries", "gourmetBurger", "chickenSandwich", "truffleFries", "friedChicken"],
  mexican: ["tacos", "streetTacos", "breakfastBurritos", "nachos"],
  noodles: ["shoyuRamen", "noodleDish", "pho", "noodleBowl"],
  asian: ["friedRice", "dumplings", "dimSum", "noodleDish", "redCurry"],
  sushi: ["sushiPlatter", "salmonPokeBowl"],
  coffee: ["frothyCoffee", "latteCroissant", "coffeeAndCake", "bagelBrunch"],
  tea: ["matchaBubbleTea", "coffeeAndCake"],
  healthy: ["saladBowl", "freshSalad", "acaiBowl", "galaxySmoothieBowl", "acaiSmoothieBowls"],
  breakfast: ["fruitWaffles", "honeyPancakes", "fruityBreakfast", "breakfastBurritos"],
  italian: ["pastaPlate", "pestoPasta", "margheritaPizza"],
  deli: ["italianSandwich", "sandwichAndFries", "chickenSandwich", "bagelBrunch"],
  dessert: ["jellyDoughnuts", "iceCreamCone", "bakeryTreats"],
  bakery: ["bakeryTreats", "freshBread", "latteCroissant"],
  market: ["greenGrocer", "marketProduce", "fruitMarket", "freshBread"],
  global: ["redCurry", "hummusPita", "dumplings", "friedRice"],
  grill: ["burgerAndFries", "friedChicken", "truffleFries", "sandwichAndFries"]
} as const satisfies Record<string, readonly FoodPhotoId[]>;
export type FoodCategory = keyof typeof FOOD_CATEGORIES;

/** Words in a venue's or station's name, summary, tags or stations that suggest a dish family. */
const CATEGORY_WORDS: [FoodCategory, RegExp][] = [
  ["pizza", /pizza|slice|flatbread/i],
  ["sushi", /sushi|poke|umi\b|sashimi|japanese/i],
  ["noodles", /noodle|ramen|pho|udon|lemongrass/i],
  ["asian", /asian|wok|chinese|dumpling|dim sum|panda|teriyaki|thai|korean|spice|makai|bao/i],
  ["mexican", /taco|taqueria|burrito|mexican|latin|cantina|wolftown/i],
  ["burgers", /burger|grill|char\b|shake|fries|chicken|wings/i],
  ["deli", /deli|sandwich|sub\b|bagel|panini|melt/i],
  ["coffee", /coffee|cafe|café|espresso|latte|kaldi|earl's|morning fog|starbucks|peet/i],
  ["tea", /boba|tea\b|tapioca|matcha/i],
  ["healthy", /salad|bowl|garden|fresh\b|smoothie|juice|acai|açaí|vegan|plant/i],
  ["breakfast", /breakfast|brunch|pancake|waffle/i],
  ["italian", /pasta|italian|al dente|scholar's italian|dente/i],
  ["dessert", /dessert|ice cream|gelato|donut|doughnut|bakery|crème|creme|sweet|cookie/i],
  ["global", /tandoor|indian|curry|mediterranean|halal|falafel|global|world|journey|soul|hapi|vibe/i],
  ["market", /market|grocery|groceries|convenience|store/i]
];

/** Dish families for a place, best match first (from its own words; never from a menu). */
export function foodCategories(texts: (string | null | undefined)[], kind?: string): FoodCategory[] {
  const text = texts.filter(Boolean).join(" · ");
  const found = CATEGORY_WORDS.filter(([, pattern]) => pattern.test(text)).map(([category]) => category);
  if (kind === "market" && !found.includes("market")) found.unshift("market");
  return found.length ? found : kind === "market" ? ["market"] : ["global", "healthy", "grill"];
}

/** A small stable number for a string, so the same venue always gets the same photos. */
function seed(value: string): number {
  let hash = 0;
  for (const char of value) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash;
}

/** `count` distinct illustrative photos for a place: its dish families first, then a stable,
 * venue-specific rotation so neighbouring cards rarely share a photo. */
export function photosFor(key: string, categories: FoodCategory[], count = 1): FoodPhotoId[] {
  const pool: FoodPhotoId[] = [];
  for (const category of categories) for (const id of FOOD_CATEGORIES[category]) if (!pool.includes(id)) pool.push(id);
  const offset = seed(key) % pool.length;
  const ordered = [...pool.slice(offset), ...pool.slice(0, offset)];
  // Prefer the strongest category's photos first, rotated by venue.
  const primary = FOOD_CATEGORIES[categories[0]] as readonly FoodPhotoId[];
  const first = primary[seed(key) % primary.length];
  const result = [first, ...ordered.filter((id) => id !== first)];
  return result.slice(0, Math.max(1, Math.min(count, result.length)));
}

/** One cover photo per place, in list order, never repeating a photo within `spread` neighbours
 * (so a row of similar cafés still looks varied). Each place keeps its best-fitting photos first. */
export function coverPhotos(places: { key: string; categories: FoodCategory[] }[], spread = 6): Record<string, FoodPhotoId> {
  const covers: Record<string, FoodPhotoId> = {};
  const recent: FoodPhotoId[] = [];
  for (const place of places) {
    const ranked = photosFor(place.key, place.categories, 12);
    const choice = ranked.find((id) => !recent.includes(id)) ?? ranked[0];
    covers[place.key] = choice;
    recent.push(choice);
    if (recent.length > spread) recent.shift();
  }
  return covers;
}
