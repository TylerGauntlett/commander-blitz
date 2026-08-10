/**
 * A small card pool, spelled once.
 *
 * `fixtures.card()` fills in a plausible bear for any field you leave out, which
 * is right for a test asserting one property and wrong for a story: a board of
 * seven identical Test Bears cannot show lane assignment, colour tones, stacking
 * or the mana row. These are the cards the stories play with -- real names, real
 * costs, real types -- so that a scenario reads like a position rather than a
 * pile of overrides.
 *
 * Each is a function so that callers get their own object and can give it an
 * `oid`; sharing one frozen instance across two zones is how a fixture starts
 * lying about where a card is.
 */

import type { CardView } from "../api/types";
import { card } from "./fixtures";

/* ------------------------------------------------------------------ */
/* Lands                                                               */
/* ------------------------------------------------------------------ */

function land(id: string, name: string, subtype: string, colour: string) {
  return (overrides: Partial<CardView> = {}): CardView =>
    card({
      card_id: id,
      name,
      type_line: `Basic Land — ${subtype}`,
      mana_cost: "",
      mana_value: 0,
      colors: [],
      types: ["Land"],
      supertypes: ["Basic"],
      subtypes: [subtype],
      produces: [colour],
      power: null,
      toughness: null,
      ...overrides,
    });
}

export const forest = land("forest", "Forest", "Forest", "G");
export const island = land("island", "Island", "Island", "U");
export const swamp = land("swamp", "Swamp", "Swamp", "B");
export const mountain = land("mountain", "Mountain", "Mountain", "R");
export const plains = land("plains", "Plains", "Plains", "W");

/** A nonbasic dual: the case the board cannot infer a colour for from subtype. */
export const breedingPool = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "breeding_pool",
    name: "Breeding Pool",
    type_line: "Land — Forest Island",
    mana_cost: "",
    mana_value: 0,
    colors: [],
    types: ["Land"],
    subtypes: ["Forest", "Island"],
    produces: ["U", "G"],
    power: null,
    toughness: null,
    ...overrides,
  });

/* ------------------------------------------------------------------ */
/* Creatures                                                           */
/* ------------------------------------------------------------------ */

export const llanowarElves = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "llanowar_elves",
    name: "Llanowar Elves",
    type_line: "Creature — Elf Druid",
    mana_cost: "{G}",
    mana_value: 1,
    power: 1,
    toughness: 1,
    subtypes: ["Elf", "Druid"],
    produces: ["G"],
    oracle_text: "{T}: Add {G}.",
    ...overrides,
  });

export const grizzlyBears = (overrides: Partial<CardView> = {}): CardView =>
  card({ card_id: "grizzly_bears", name: "Grizzly Bears", ...overrides });

export const thragtusk = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "thragtusk",
    name: "Thragtusk",
    type_line: "Creature — Beast",
    mana_cost: "{4}{G}",
    mana_value: 5,
    power: 5,
    toughness: 3,
    subtypes: ["Beast"],
    oracle_text: "When Thragtusk enters the battlefield, you gain 5 life.",
    ...overrides,
  });

export const serraAngel = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "serra_angel",
    name: "Serra Angel",
    type_line: "Creature — Angel",
    mana_cost: "{3}{W}{W}",
    mana_value: 5,
    colors: ["W"],
    power: 4,
    toughness: 4,
    subtypes: ["Angel"],
    keywords: ["flying", "vigilance"],
    ...overrides,
  });

export const wallOfRoots = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "wall_of_roots",
    name: "Wall of Roots",
    type_line: "Creature — Plant Wall",
    mana_cost: "{1}{G}",
    mana_value: 2,
    power: 0,
    toughness: 5,
    subtypes: ["Plant", "Wall"],
    keywords: ["defender"],
    ...overrides,
  });

export const krakenToken = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "kraken_token",
    name: "Kraken",
    type_line: "Token Creature — Kraken",
    mana_cost: "",
    mana_value: 0,
    colors: ["U"],
    power: 9,
    toughness: 9,
    subtypes: ["Kraken"],
    is_token: true,
    ...overrides,
  });

/* ------------------------------------------------------------------ */
/* Spells and permanents                                               */
/* ------------------------------------------------------------------ */

export const solRing = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "sol_ring",
    name: "Sol Ring",
    type_line: "Artifact",
    mana_cost: "{1}",
    mana_value: 1,
    colors: [],
    types: ["Artifact"],
    subtypes: [],
    power: null,
    toughness: null,
    produces: ["C"],
    oracle_text: "{T}: Add {C}{C}.",
    ...overrides,
  });

export const counterspell = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "counterspell",
    name: "Counterspell",
    type_line: "Instant",
    mana_cost: "{U}{U}",
    mana_value: 2,
    colors: ["U"],
    types: ["Instant"],
    subtypes: [],
    power: null,
    toughness: null,
    oracle_text: "Counter target spell.",
    ...overrides,
  });

export const cultivate = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "cultivate",
    name: "Cultivate",
    type_line: "Sorcery",
    mana_cost: "{2}{G}",
    mana_value: 3,
    types: ["Sorcery"],
    subtypes: [],
    power: null,
    toughness: null,
    oracle_text:
      "Search your library for up to two basic land cards, reveal them, put one onto the battlefield tapped and the other into your hand, then shuffle.",
    ...overrides,
  });

export const simicCharm = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "simic_charm",
    name: "Simic Charm",
    type_line: "Instant",
    mana_cost: "{G}{U}",
    mana_value: 2,
    colors: ["G", "U"],
    types: ["Instant"],
    subtypes: [],
    power: null,
    toughness: null,
    oracle_text:
      "Choose one — Target creature gets +3/+3 until end of turn; or return target creature to its owner's hand; or target creature you control gains hexproof until end of turn.",
    ...overrides,
  });

/** An Aura, for the tucked-attachment path no shipped precon can reach. */
export const rancor = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "rancor",
    name: "Rancor",
    type_line: "Enchantment — Aura",
    mana_cost: "{G}",
    mana_value: 1,
    types: ["Enchantment"],
    subtypes: ["Aura"],
    power: null,
    toughness: null,
    oracle_text: "Enchanted creature gets +2/+0 and has trample.",
    ...overrides,
  });

export const swordOfFireAndIce = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "sword_of_fire_and_ice",
    name: "Sword of Fire and Ice",
    type_line: "Artifact — Equipment",
    mana_cost: "{2}",
    mana_value: 2,
    colors: [],
    types: ["Artifact"],
    subtypes: ["Equipment"],
    power: null,
    toughness: null,
    oracle_text: "Equipped creature gets +2/+2 and has protection from red and from blue.",
    ...overrides,
  });

export const rhysticStudy = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "rhystic_study",
    name: "Rhystic Study",
    type_line: "Enchantment",
    mana_cost: "{2}{U}",
    mana_value: 3,
    colors: ["U"],
    types: ["Enchantment"],
    subtypes: [],
    power: null,
    toughness: null,
    oracle_text:
      "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
    ...overrides,
  });

/* ------------------------------------------------------------------ */
/* Commanders                                                          */
/* ------------------------------------------------------------------ */

export const aesi = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "aesi_tyrant_of_gyre_strait",
    name: "Aesi, Tyrant of Gyre Strait",
    type_line: "Legendary Creature — Serpent",
    mana_cost: "{4}{G}{U}",
    mana_value: 6,
    colors: ["G", "U"],
    power: 5,
    toughness: 5,
    subtypes: ["Serpent"],
    supertypes: ["Legendary"],
    keywords: ["trample"],
    is_commander: true,
    zone: "command",
    oracle_text:
      "Trample. Whenever you play a land, draw a card. You may play an additional land on each of your turns.",
    ...overrides,
  });

export const edgarMarkov = (overrides: Partial<CardView> = {}): CardView =>
  card({
    card_id: "edgar_markov",
    name: "Edgar Markov",
    type_line: "Legendary Creature — Vampire Knight",
    mana_cost: "{3}{R}{W}{B}",
    mana_value: 6,
    colors: ["B", "R", "W"],
    power: 4,
    toughness: 4,
    subtypes: ["Vampire", "Knight"],
    supertypes: ["Legendary"],
    keywords: ["first_strike"],
    is_commander: true,
    zone: "command",
    ...overrides,
  });
