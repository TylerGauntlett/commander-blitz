/**
 * Card art for stories, in three flavours.
 *
 * `ImageMap` is tri-state and the states are not interchangeable (see
 * `logic/cardArt.ts`): `null` means the map has not arrived and the face draws
 * no art band at all; a present-but-artless entry means it arrived and this card
 * has no printing, so the face draws its hatched plate; a URL means a picture. A
 * story that left the map `null` would be posing every card in the one state the
 * running app shows for about 200ms, which is not what anybody wants to look at.
 *
 * So the default is `stub`: a generated SVG data URI per card, hue derived from
 * the card id. It is offline, byte-identical on every run, and gives every face
 * a real opaque band with real dimensions -- which is what the scrims and the
 * type-size rules are actually laid over. `live` exists for eyeballing the board
 * against real illustrations with uvicorn up, and is deliberately not the
 * default: it would make a play function's outcome depend on whether a Python
 * process happened to be running.
 *
 * The maps are `Proxy` objects rather than built dictionaries so that a story
 * never has to declare which cards it is about -- the art for a card id is a
 * pure function of that id, so it can be answered on demand. Nothing in the app
 * enumerates the map; every read is a keyed lookup, which is what makes this
 * safe.
 */

import type { ImageMap, ImageRef } from "../logic/cardArt";

export type ArtMode = "stub" | "live" | "none";

/** Stable hash -> hue, so one card is always the same colour. */
function hueOf(cardId: string): number {
  let hash = 0;
  for (let i = 0; i < cardId.length; i += 1) {
    hash = (hash * 31 + cardId.charCodeAt(i)) % 360;
  }
  return hash;
}

/**
 * A card's stand-in illustration.
 *
 * Deliberately a *dark* gradient with a bright focal blob rather than a flat
 * mid-grey: the face lays white type on graded scrims over this, and a uniform
 * placeholder would make every legibility judgement look fine in a story when a
 * real illustration would not.
 */
function stubImage(cardId: string): string {
  const hue = hueOf(cardId);
  const svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240">',
    '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">',
    `<stop offset="0" stop-color="hsl(${hue} 55% 46%)"/>`,
    `<stop offset="1" stop-color="hsl(${(hue + 40) % 360} 60% 12%)"/>`,
    '</linearGradient><radialGradient id="f" cx="0.5" cy="0.42" r="0.42">',
    `<stop offset="0" stop-color="hsl(${hue} 70% 82%)" stop-opacity="0.85"/>`,
    `<stop offset="1" stop-color="hsl(${hue} 70% 82%)" stop-opacity="0"/>`,
    "</radialGradient></defs>",
    '<rect width="320" height="240" fill="url(#g)"/>',
    '<ellipse cx="160" cy="100" rx="120" ry="86" fill="url(#f)"/></svg>',
  ].join("");
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

/** A map that answers for any card id, without being told them in advance. */
function onDemand(resolve: (cardId: string) => ImageRef): ImageMap {
  return new Proxy({} as Record<string, ImageRef | null>, {
    // Symbol keys reach here too -- `Symbol.toPrimitive` when something
    // stringifies the map, for one -- and must fall through rather than be
    // answered with a card.
    get: (target, key) => (typeof key === "string" ? resolve(key) : Reflect.get(target, key)),
    // `artUrl` reads `images[cardId]`, but `has` is cheap to keep honest and
    // stops a future `in` check from disagreeing with the getter.
    has: () => true,
  });
}

/** Deterministic offline stand-ins. */
export function stubArt(): ImageMap {
  return onDemand((cardId) => ({
    card_id: cardId,
    art: stubImage(cardId),
    artist: "Storybook",
  }));
}

/** The real thing, served by the engine. Needs uvicorn on :8000. */
export function liveArt(): ImageMap {
  return onDemand((cardId) => ({ card_id: cardId, art: `/art/${cardId}.jpg`, artist: null }));
}

/**
 * Loaded, and nothing has a printing.
 *
 * Not the same as `null`: this is what makes every face draw its plate, which is
 * a state worth posing on purpose.
 */
export const NO_ART: ImageMap = {};

/** The map a story's chosen mode implies. */
export function artFor(mode: ArtMode): ImageMap {
  if (mode === "none") return NO_ART;
  return mode === "live" ? liveArt() : stubArt();
}
