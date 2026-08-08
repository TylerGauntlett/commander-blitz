/**
 * Where a card's art comes from.
 *
 * Every URL here is same-origin (`/art/{card_id}.jpg`). The server downloads
 * from Scryfall once and serves the bytes itself, so the board keeps rendering
 * when Scryfall is rate limiting, down, or simply unreachable. If a
 * `cards.scryfall.io` URL ever appears in this file, that guarantee is gone.
 */

import type { CardView } from "../api/types";

export interface ImageRef {
  card_id: string;
  /** Same-origin path, or absent when the card has no printing. */
  art?: string | null;
  artist?: string | null;
}

/** `null` means the map has not been fetched yet -- not that art is missing. */
export type ImageMap = Record<string, ImageRef | null> | null;

/**
 * Three states, and the distinction between the last two matters.
 *
 * `undefined` -- the map has not loaded. Draw no band at all, which is exactly
 *   the layout the client had before art existed. Rendering the "no art" plate
 *   here would make every card flash a hatched placeholder on first paint.
 * `null` -- loaded, and this card genuinely has no printing (the five custom
 *   designs in `data/cards/`). Draw the plate.
 * `string` -- the URL to put in `<img src>`.
 */
export function artUrl(images: ImageMap, cardId: string): string | null | undefined {
  if (images === null) return undefined;
  const ref = images[cardId];
  if (!ref || !ref.art) return null;
  return ref.art;
}

/** The same decision, as a label -- handy for `data-` attributes and tests. */
export function artState(images: ImageMap, cardId: string): "pending" | "none" | "ready" {
  const url = artUrl(images, cardId);
  if (url === undefined) return "pending";
  return url === null ? "none" : "ready";
}

export function artistOf(images: ImageMap, cardId: string): string | null {
  if (images === null) return null;
  return images[cardId]?.artist ?? null;
}

/**
 * A token has no printing of its own in the engine's registry sense -- it is
 * created by a card -- but it does have a `card_id`, so it resolves like
 * anything else. This exists so callers do not have to remember that.
 */
export function artUrlFor(images: ImageMap, card: CardView): string | null | undefined {
  return artUrl(images, card.card_id);
}
