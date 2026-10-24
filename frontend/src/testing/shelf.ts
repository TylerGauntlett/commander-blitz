/**
 * The shelf at the sizes it is built for: the shipped favorites, precons from
 * more than one release, and a player's imports with one of them starred.
 *
 * The favorites mirror `data/decks/` (ADR 0024 moved them out of `precon`).
 * The precons are fixtures with a `release` each, since what the shelf does
 * with a precon is group it by product, and two products is the least that
 * shows the order.
 */

import type { DeckRelease, DeckSummary, UpcomingPrecon } from "../api/types";
import { stubImage } from "./art";
import { cardResponse, deckSummary } from "./fixtures";

function favorite(
  id: string,
  name: string,
  commander: string,
  colours: string[],
  tags: string[],
): DeckSummary {
  return deckSummary({
    id,
    name,
    commanders: [commander],
    commander_names: [name],
    color_identity: colours,
    notes: `${name}, as the maintainer plays it.`,
    tags,
  });
}

/** The twelve shipped lists, under the word that is true of them. */
export const FAVORITES: DeckSummary[] = [
  favorite(
    "aesi",
    "Aesi, Tyrant of Gyre Strait",
    "aesi_tyrant_of_gyre_strait",
    ["G", "U"],
    ["Landfall", "Ramp"],
  ),
  favorite(
    "atraxa_praetors_voice",
    "Atraxa, Praetors' Voice",
    "atraxa_praetors_voice",
    ["B", "G", "U", "W"],
    ["Proliferate"],
  ),
  favorite(
    "bard_king_of_dale",
    "Bard, King of Dale",
    "bard_king_of_dale",
    ["U", "W"],
    ["Tokens"],
  ),
  favorite(
    "blor_the_impervious",
    "Blor the Impervious",
    "blor_the_impervious",
    ["G"],
    ["Voltron"],
  ),
  favorite(
    "bruvac_the_grandiloquent",
    "Bruvac the Grandiloquent",
    "bruvac_the_grandiloquent",
    ["U"],
    ["Mill"],
  ),
  favorite("edgar", "Edgar Markov", "edgar_markov", ["B", "R", "W"], ["Tribal"]),
  favorite(
    "giada_font_of_hope",
    "Giada, Font of Hope",
    "giada_font_of_hope",
    ["W"],
    ["Fliers"],
  ),
  favorite(
    "isperia",
    "Isperia, Supreme Judge",
    "isperia_supreme_judge",
    ["U", "W"],
    ["Flyers"],
  ),
  favorite(
    "sheoldred_the_apocalypse",
    "Sheoldred, the Apocalypse",
    "sheoldred_the_apocalypse",
    ["B"],
    ["Punisher"],
  ),
  favorite(
    "the_ur_dragon",
    "The Ur-Dragon",
    "the_ur_dragon",
    ["B", "G", "R", "U", "W"],
    ["Tribal"],
  ),
  favorite("vivi_ornitier", "Vivi Ornitier", "vivi_ornitier", ["R", "U"], ["Spellslinger"]),
  favorite("zurgo", "Zurgo Stormrender", "zurgo_stormrender", ["B", "R", "W"], ["Tokens"]),
];

export const FOUNDATIONS: DeckRelease = {
  set_code: "FDC",
  set_name: "Foundations Commander",
  date: "2026-10-02",
};

export const DUSKMOURN: DeckRelease = {
  set_code: "DSC",
  set_name: "Duskmourn Commander",
  date: "2024-09-27",
};

function precon(
  id: string,
  name: string,
  commander: string,
  commanderName: string,
  colours: string[],
  archetype: string,
  release: DeckRelease,
): DeckSummary {
  return deckSummary({
    id,
    name,
    source: "precon",
    commanders: [commander],
    commander_names: [commanderName],
    color_identity: colours,
    notes: `${name}, as it came in the box.`,
    tags: [],
    archetype,
    release,
  });
}

/**
 * Two releases, the older one listed first, so a story that finds the newer
 * one on top has watched `groupDecks` order them rather than the fixture.
 */
export const PRECONS: DeckSummary[] = [
  precon(
    "dsc_endless_punishment",
    "Endless Punishment",
    "valgavoth_harrower_of_souls",
    "Valgavoth, Harrower of Souls",
    ["B", "R"],
    "punisher",
    DUSKMOURN,
  ),
  precon(
    "dsc_death_toll",
    "Death Toll",
    "winter_cynical_opportunist",
    "Winter, Cynical Opportunist",
    ["B", "G", "U"],
    "aristocrats",
    DUSKMOURN,
  ),
  precon(
    "fdc_calling_all_angels",
    "Calling All Angels",
    "fdc_angel_commander",
    "Seraph of the Dawn Choir",
    ["W"],
    "tribal",
    FOUNDATIONS,
  ),
  precon(
    "fdc_wild_hunt",
    "The Wild Hunt",
    "fdc_wolf_commander",
    "Alpha of the Wild Hunt",
    ["G"],
    "go_wide",
    FOUNDATIONS,
  ),
];

function mine(id: string, name: string, commander: string, colours: string[], starred = false) {
  return deckSummary({
    id,
    name,
    source: "moxfield",
    source_id: id,
    commanders: [commander],
    commander_names: [name],
    color_identity: colours,
    notes: "",
    tags: [],
    playable: 96,
    simplified: 4,
    starred,
  });
}

/** Three imports, the starred one last by name, so its place on top is the star's. */
export const YOURS: DeckSummary[] = [
  mine("mox_alela", "Alela, Cunning Conqueror", "alela_cunning_conqueror", ["U", "B"]),
  mine("mox_krenko", "Krenko, Mob Boss", "krenko_mob_boss", ["R"]),
  mine(
    "mox_yuriko",
    "Yuriko, the Tiger's Shadow",
    "yuriko_the_tigers_shadow",
    ["U", "B"],
    true,
  ),
];

export const BLOOMBURROW: DeckRelease = {
  set_code: "BLC",
  set_name: "Bloomburrow Commander",
  date: "2025-08-02",
};

function shell(
  id: string,
  product: string,
  release: DeckRelease,
  commanders: [name: string, art: boolean][],
): UpcomingPrecon {
  return {
    id,
    product,
    set_code: release.set_code,
    set_name: release.set_name,
    date: release.date,
    commanders: commanders.map(([name, art]) => ({
      name,
      art_url: art ? stubImage(name) : null,
    })),
  };
}

/**
 * Precons the shelf names but cannot deal yet. One shares Foundations with
 * the playable decks, so it must come after them in that run; Bloomburrow
 * has nothing playable, so it is a run of shells alone, between the two
 * releases by date. One shell has no printing known and draws a plain plate.
 */
export const UPCOMING: UpcomingPrecon[] = [
  shell("fdc_grave_danger", "Grave Danger", FOUNDATIONS, [["Ghoul Lord of the Crypt", true]]),
  shell("blc_squirreled_away", "Squirreled Away", BLOOMBURROW, [
    ["Hazel of the Rootbloom", true],
  ]),
  shell("blc_family_matters", "Family Matters", BLOOMBURROW, [
    ["Zinnia, Valley's Voice", false],
    ["Bello, Bard of the Brambles", false],
  ]),
];

/** A printed card per commander, so every tile on the shelf draws a face. */
export function shelfCards(decks: DeckSummary[]): [string[], unknown][] {
  return decks.map((deck) => [
    ["card", deck.commanders[0]],
    cardResponse({ id: deck.commanders[0], name: deck.commander_names[0] }),
  ]);
}
