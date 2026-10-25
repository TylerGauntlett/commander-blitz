/**
 * The floors, per layout mode (ADR 0013, ADR 0025).
 *
 * A floor is the smallest a thing carrying information may be drawn: type, a
 * card the ring or a finger can land on, a control. They are CI gates, asserted
 * by `testing/asserts.ts` on stories and by `e2e/handheldAssert.ts` on a live
 * board, and both read the row for the layout the page is in -- so the phone's
 * floors are the phone's, not the Deck's lowered.
 *
 * - `handheld` comes from a 7-inch panel at 40-50cm.
 * - `phone`'s type and card floors are the ones `styles/phone.css`
 *   (`--type-floor`) and `logic/cardSize.ts` (`PHONE_MIN_CARD_W`) already solve
 *   to; its hit floor is a thumb's, and a phone is held closer than a Deck.
 *
 * The desktop has no row: a mouse is precise and a monitor is large, and
 * `MIN_CARD_W` is the solver's own floor there.
 */

import { PHONE_MIN_CARD_W } from "./cardSize";

export interface Floors {
  /** Nothing carrying information may be smaller, in CSS pixels. */
  font: number;
  /** Any card the ring or a finger can land on. */
  card: number;
  /** Any focusable or tappable box, both ways. */
  hit: number;
}

export const FLOORS = {
  handheld: { font: 16, card: 96, hit: 44 },
  phone: { font: 12, card: PHONE_MIN_CARD_W, hit: 44 },
} as const satisfies Record<"handheld" | "phone", Floors>;

/** The floors for a compact layout, by the name `<html data-layout>` carries. */
export function floorsFor(layout: string | null | undefined): Floors {
  return layout === "phone" ? FLOORS.phone : FLOORS.handheld;
}
