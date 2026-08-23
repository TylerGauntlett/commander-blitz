/**
 * The marks a seat is read by.
 *
 * ## Why these exist at all
 *
 * It is a legibility argument rather than a colour one, and it is ADR 0006's.
 *
 * The compact layout drops a zone's word at the 16px floor -- "Lib", "Hand",
 * "GY" and "CMD" all go, because a 96px seat has one 20px row for five of them
 * -- and what is left of a zone is a coloured chip with a number in it. **A
 * fixed order only helps somebody who has already learned the order**, and a
 * colour code has to be learned too. A shape can say it without being taught: a
 * headstone is a graveyard, a fan of three cards is a hand, a face-down card is
 * a library.
 *
 * The same goes for the three permanent counts. "5/7" beside "2/3" beside "1"
 * is three numbers in a row and nothing about which is which; a plot of ground,
 * a figure and a cut gem are.
 *
 * ## Why SVG and not characters
 *
 * A glyph in a font is a different picture on every machine, and three of these
 * have no reliable character at all. They are also *pictures rather than
 * words*, so every one is `aria-hidden` and the real name is carried by the
 * cell's `aria-label` -- which `HintBar` surfaces on the cursor and a hover
 * bubble surfaces on the pointer, because a native `title` opens on hover and
 * on nothing else.
 */

/** Every mark, as the path data inside a 16x16 box. */
const ICON = {
  /** A figure. Creatures. */
  creature:
    '<circle cx="8" cy="4.4" r="2.7"/><path d="M2.6 14.6c0-4.3 2.3-6.2 5.4-6.2s5.4 1.9 5.4 6.2z"/>',
  /** Total power on board: a hammer. */
  power:
    '<path d="M8 .6l2.9 4.8v5.4H5.1V5.4z"/><rect x="2.2" y="10.6" width="11.6" height="2.3" rx="1.15"/>',
  /*
   * A land: a plot of ground, in perspective.
   *
   * A trapezoid because every other rectangle on this seat is a card, and
   * orientation is the one difference this family of designs has already ruled
   * out -- a tapped card is a rotated rectangle, so a rotated rectangle cannot
   * also mean "land".
   */
  land: '<path d="M1.4 13.8L4.4 5.4h7.2l3 8.4z"/>',
  /*
   * Everything on the battlefield that is neither a creature nor a land -- the
   * artifacts and enchantments. A cut gem, which is neither the star nor the
   * crown at 14px, both of which are already spoken for below.
   */
  other: '<path d="M8 1.1l6.2 5.1-6.2 8.7-6.2-8.7z"/>',
  /*
   * Commander damage: a crown. Twenty-one of these kills you and nothing else
   * in the game does, so it gets a mark of its own rather than sharing life's.
   */
  crown: '<path d="M1.6 13.2L2.9 4.4 6 8.2 8 2.8l2 5.4 3.1-3.8 1.3 8.8z"/>',
  /** The library: a face-down card. */
  lib: '<rect x="3.2" y="1.6" width="9.6" height="12.8" rx="1.5"/><path d="M8 4.4l1.7 3.6L8 11.6 6.3 8z" fill="var(--chip-ink, #0d0c1a)"/>',
  /** The hand: a fan of three. */
  hand: '<g transform="rotate(-22 8 13)"><rect x="1.9" y="4.2" width="4.8" height="9.2" rx="1.1"/></g><g transform="rotate(22 8 13)"><rect x="9.3" y="4.2" width="4.8" height="9.2" rx="1.1"/></g><rect x="5.6" y="2.6" width="4.8" height="10.8" rx="1.1"/>',
  /** The graveyard: a headstone. */
  gy: '<path d="M3.4 15V7.2a4.6 4.6 0 019.2 0V15z"/>',
  /** Exile: a card with a dashed edge -- there, and not here. */
  ex: '<rect x="3.2" y="1.8" width="9.6" height="12.4" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="3.4 2.6"/>',
  /** The command zone: a star. */
  cmd: '<path d="M8 1l2.1 4.5L15 6.2l-3.6 3.4.9 4.9L8 12.2 3.7 14.5l.9-4.9L1 6.2l4.9-.7z"/>',
} as const;

export type SeatIconName = keyof typeof ICON;

/**
 * `dangerouslySetInnerHTML` on the path data, which is the honest way to do
 * this: the alternative is eleven components of hand-transcribed JSX for eleven
 * strings that are already correct, and every transcription is a chance to be
 * wrong about a number nobody will ever read again.
 *
 * The strings are a module constant in this file. Nothing outside it can reach
 * the prop, so there is no path from any input to this markup.
 */
export function SeatIcon({ name }: { name: SeatIconName }) {
  return (
    <svg
      className="ico"
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
      // biome-ignore lint/security/noDangerouslySetInnerHtml: a module constant; see above.
      dangerouslySetInnerHTML={{ __html: ICON[name] }}
    />
  );
}
