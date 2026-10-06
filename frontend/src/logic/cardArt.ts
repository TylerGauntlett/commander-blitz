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
 * Per-seat art: `seat index -> card id -> ref`.
 *
 * A deck imported from Moxfield names the printing its author chose, and that
 * choice belongs to *their* seat -- two players can hold the same card and want
 * different illustrations, which the flat map above cannot express. `null` is
 * "not loaded", exactly as for `ImageMap`.
 */
export type SeatImages = Record<string, Record<string, ImageRef>> | null;

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
  if (!ref?.art) return null;
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
 * The ref for a card *at a seat*, which is the one a board should draw.
 *
 * A seat's own deck wins: if its author chose an illustration for this card,
 * that is what makes the deck recognisable as theirs, and the catalog's pick is
 * only the answer for everybody who did not choose. Whole refs, never a
 * field-by-field merge -- an override with no `artist` means we do not know who
 * painted it, and borrowing the base printing's illustrator would credit the
 * wrong person.
 *
 * Keyed on `owner`, not `controller`: a creature somebody steals is still the
 * card its owner shuffled up, and it goes home looking the same.
 */
function refFor(
  images: Record<string, ImageRef | null>,
  seats: SeatImages,
  cardId: string,
  owner?: number,
): ImageRef | null {
  if (seats !== null && owner !== undefined) {
    const ref = seats[String(owner)]?.[cardId];
    if (ref) return ref;
  }
  // A key this map does not carry is a card with no printing, exactly as in
  // `artUrl`. Only a `null` *map* means "not loaded", and that is handled by
  // the callers below -- collapsing the two here would make every card flash a
  // hatched plate on first paint.
  return images[cardId] ?? null;
}

/**
 * A token has no printing of its own in the engine's registry sense -- it is
 * created by a card -- but it does have a `card_id`, so it resolves like
 * anything else. This exists so callers do not have to remember that.
 */
export function artUrlFor(
  images: ImageMap,
  seats: SeatImages,
  card: CardView,
): string | null | undefined {
  if (images === null) return undefined;
  const ref = refFor(images, seats, card.card_id, seatOf(card));
  if (!ref?.art) return null;
  return ref.art;
}

/**
 * The seat whose deck this card came out of, or `undefined` for a card that is
 * not in a game at all.
 *
 * The lobby draws real card faces from `GET /api/cards/{id}` with synthetic
 * fields -- `oid: -1` and a filler `owner: 0` (see `CommanderCard`). That zero
 * is not a seat, and taking it for one would draw seat 0's chosen printings on
 * a card belonging to no deck.
 */
function seatOf(card: CardView): number | undefined {
  return card.oid < 0 ? undefined : card.owner;
}

/** `artState`, for a card whose seat is known. */
export function artStateFor(
  images: ImageMap,
  seats: SeatImages,
  card: CardView,
): "pending" | "none" | "ready" {
  const url = artUrlFor(images, seats, card);
  if (url === undefined) return "pending";
  return url === null ? "none" : "ready";
}

/** `artistOf`, for a card whose seat is known. */
export function artistFor(images: ImageMap, seats: SeatImages, card: CardView): string | null {
  if (images === null) return null;
  return refFor(images, seats, card.card_id, seatOf(card))?.artist ?? null;
}
