/*
 * The board state every mockup renders, and the renderer that draws it.
 *
 * NOT LOADED BY THE MOCKUPS. Each .html file is required to open standalone from
 * file://, so this file is inlined into each one rather than linked. It is kept
 * here as the single readable copy: edit this, then re-inline.
 *
 * The state is turn 8 of the reference screenshot, at DECLARE_ATTACKERS.
 *
 * One deliberate deviation from the screenshot: one of the eight Forests is a
 * Terramorphic Expanse. The mockups exist partly to show an affordance for
 * available activated abilities, and nothing on the screenshot's board has one --
 * Gyre Sage's only ability is a mana ability, and engine/legality.py never offers
 * those as actions (the payment solver taps them). Terramorphic Expanse's
 * "{T}, Sacrifice:" is a real `activate` action at this exact step.
 */

// n=name cost tl=type line t=type tone f=frame tone land=produces pt kw=keywords
// rules  tapped sick cmd token art=slug in art/  count=stack size
// ability=available activated ability text (drives the rune + popover)

const OPP_LANDS = [
  { n: "Mountain", tl: "Basic Land — Mountain", t: "land", f: "land", land: "R", produces: "R", art: "mountain", count: 2 },
  { n: "Scoured Barrens", tl: "Land", t: "land", f: "land", land: "multi", produces: "WB", tapped: true, art: "scoured-barrens" },
];

const OPP_CREATURES = [
  { n: "Vampire", tl: "Token Creature — Vampire", t: "creature", f: "B", pt: "1/1", token: true, tapped: true, art: "token-vampire", count: 2 },
  { n: "Vampire Neonate", cost: "1B", tl: "Creature — Vampire", t: "creature", f: "B", pt: "0/3", art: "vampire-neonate" },
  { n: "Vampire", tl: "Token Creature — Vampire", t: "creature", f: "B", pt: "1/1", token: true, art: "token-vampire" },
  { n: "Falkenrath Noble", cost: "3B", tl: "Creature — Vampire Noble", t: "creature", f: "B", pt: "2/2", kw: "Flying", art: "falkenrath-noble" },
];

const MY_LANDS = [
  { n: "Forest", tl: "Basic Land — Forest", t: "land", f: "land", land: "G", produces: "G", art: "forest", count: 7 },
  { n: "Island", tl: "Basic Land — Island", t: "land", f: "land", land: "U", produces: "U", art: "island", count: 3 },
  { n: "Thornwood Falls", tl: "Land", t: "land", f: "land", land: "multi", produces: "GU", art: "thornwood-falls" },
  {
    n: "Terramorphic Expanse", tl: "Land", t: "land", f: "land", land: "C", produces: "",
    ability: "{T}, Sacrifice: Search for a basic land tapped.",
  },
];

const MY_CREATURES = [
  { n: "Gyre Strait Leviathan", cost: "5UU", tl: "Creature — Leviathan", t: "creature", f: "U", pt: "7/7", kw: "Trample", attacker: true },
  { n: "Aesi, Tyrant of Gyre Strait", cost: "4GU", tl: "Legendary Creature — Serpent", t: "creature", f: "gold", pt: "5/5", kw: "Trample", cmd: true, attacker: true, art: "aesi-tyrant-of-gyre-strait" },
  { n: "Elvish Visionary", cost: "1G", tl: "Creature — Elf Shaman", t: "creature", f: "G", pt: "1/1", attacker: true, art: "elvish-visionary" },
  { n: "Elemental Token", tl: "Token Creature — Elemental", t: "creature", f: "G", pt: "2/2", token: true, attacker: true, art: "token-elemental", count: 2 },
  { n: "Acidic Slime", cost: "3GG", tl: "Creature — Ooze", t: "creature", f: "G", pt: "2/2", kw: "Deathtouch", sick: true, art: "acidic-slime" },
  { n: "Yavimaya Elder", cost: "1G", tl: "Creature — Human Druid", t: "creature", f: "G", pt: "1/2", sick: true, art: "yavimaya-elder" },
];

const MY_OTHER = [
  { n: "Zendikar's Roil", cost: "4G", tl: "Enchantment", t: "enchantment", f: "G", art: "zendikar-s-roil" },
];

const HAND = [
  { n: "Vorel of the Hull Clade", cost: "1GU", tl: "Legendary Creature — Human Merfolk", t: "creature", f: "gold", pt: "1/4", rules: "{1}{G}{U}, {T}: Put a +1/+1 counter on target creature you control.", art: "vorel-of-the-hull-clade", playable: true },
  { n: "Explosive Vegetation", cost: "3G", tl: "Sorcery", t: "sorcery", f: "G", rules: "Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.", art: "explosive-vegetation", playable: true },
  { n: "Garruk's Packleader", cost: "4G", tl: "Creature — Beast", t: "creature", f: "G", pt: "3/3", rules: "Whenever another creature with power 3 or greater enters under your control, draw a card.", art: "garruk-s-packleader", playable: true },
  { n: "Nimble Mongoose", cost: "G", tl: "Creature — Mongoose", t: "creature", f: "G", pt: "1/1", rules: "Hexproof", art: "nimble-mongoose", playable: true },
  { n: "Gyre Sage", cost: "1G", tl: "Creature — Elf Druid", t: "creature", f: "G", pt: "0/2", rules: "{T}: Add {G}.", art: "gyre-sage", playable: true },
  { n: "Explore", cost: "1G", tl: "Sorcery", t: "sorcery", f: "G", rules: "You may play an additional land this turn. Draw a card.", art: "explore", playable: true },
];

const COMMANDER = {
  n: "Aesi, Tyrant of Gyre Strait", cost: "4GU", tl: "Legendary Creature — Serpent",
  t: "creature", f: "gold", pt: "5/5", kw: "Trample", cmd: true,
  rules: "Trample. Whenever you play a land, draw a card. You may play an additional land on each of your turns.",
  art: "aesi-tyrant-of-gyre-strait", where: "On the battlefield", tax: "+4",
};

const OPP_COMMANDER = {
  n: "Edgar Markov", cost: "3RWB", tl: "Legendary Creature — Vampire Knight",
  t: "creature", f: "gold", pt: "4/4", kw: "First strike", cmd: true,
  art: "edgar-markov", where: "Command zone", tax: "+2",
};

// Attackers staged in the mockup: three of the five candidates.
const STAGED = ["Gyre Strait Leviathan", "Aesi, Tyrant of Gyre Strait", "Elemental Token"];

const LOG = [
  "— Your turn 8 —",
  "You play Forest",
  "Zendikar's Roil creates a 2/2 Elemental",
  "Aesi, Tyrant of Gyre Strait draws you a card",
  "You cast Acidic Slime",
  "Acidic Slime destroys Bloodcrypt Vault",
];
