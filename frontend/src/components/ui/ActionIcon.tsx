/**
 * The two marks either side of the commit slab.
 *
 * ## Why they are not characters any more
 *
 * They were `▣` and `▢` -- filled and empty of one shape, on the argument that
 * this *is* the relationship between "every legal choice" and "none of them".
 * The relationship is real; the reading of it is not. `mockups/handheld-board/`
 * is a document you study, and a player who has not read it sees two squares and
 * has no way to tell which is which, let alone that one of them ends the
 * declaration. Playtest called them out by name.
 *
 * The rest of the argument survives intact, and `SeatIcon` already made it for
 * the seat marks: **a glyph in a font is a different picture on every machine**,
 * so a mark that has to be recognised has to be drawn. These are pictures rather
 * than words, so both are `aria-hidden` and the real name stays on the button's
 * `aria-label` and `data-hint` -- which `HintBar` surfaces from the cursor as
 * well as from the pointer, and which a `title` would have reached the mouse and
 * nothing else with. Nothing about the names, the ids or the handlers changed.
 *
 * ## Why a second file and not two more keys in `SeatIcon`
 *
 * `SeatIconName` is a published type and `SeatIcon` is a closed vocabulary --
 * the eleven things a *seat* is read by, consumed by `OpponentSeat` and
 * `PlayerOrb`. These are controls in a bar. Sharing the map would mean either
 * file's additions widening the other's type for no shared behaviour; the
 * pattern is what is worth sharing, and it is copied here deliberately and in
 * full.
 *
 * ## Not to be unified with `⏩`
 *
 * The tools row has a narration-skip button that is still a glyph. It is a
 * different verb -- skip the *animation*, not the *decision* -- in a different
 * row, and giving the two one mark would say they are the same control. If a
 * later pass tidies glyphs into this file, that one stays out.
 */

/** Every mark, as the path data inside a 16x16 box. */
const ICON = {
  /*
   * Every legal choice: select-all.
   *
   * Three rows with a tick against them, which is the mark a list-with-checkboxes
   * has used for "all of these" everywhere for thirty years. Not a fan of cards
   * leaning forward, which was the other candidate: this button also means "block
   * where it is worth it", and a picture of an attack would be wrong half the
   * time it is on screen.
   */
  all: '<rect x="1" y="2.4" width="7.4" height="1.9" rx="0.95"/><rect x="1" y="7.05" width="7.4" height="1.9" rx="0.95"/><rect x="1" y="11.7" width="7.4" height="1.9" rx="0.95"/><path d="M10.4 8.9l1.9 2.1 3.1-4.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  /*
   * None of them: skip to the end.
   *
   * A triangle against a bar. It is the transport control for "I am done here,
   * move past it", which is exactly what `finish_declaration` does -- and unlike
   * a slashed circle it does not read as "forbidden", which would say the game
   * is refusing rather than that you are declining.
   */
  skip: '<path d="M2.6 2.7l8.1 5.3-8.1 5.3z"/><rect x="11.7" y="2.7" width="2.2" height="10.6" rx="1.1"/>',
} as const;

export type ActionIconName = keyof typeof ICON;

/**
 * `dangerouslySetInnerHTML` on the path data, for `SeatIcon`'s reason: the
 * alternative is hand-transcribed JSX for strings that are already correct, and
 * every transcription is a chance to be wrong about a number nobody will read
 * again. The strings are a module constant in this file and nothing outside it
 * can reach the prop, so there is no path from any input to this markup.
 */
export function ActionIcon({ name }: { name: ActionIconName }) {
  return (
    <svg
      className="ico ico--mark"
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
      fill="currentColor"
      // biome-ignore lint/security/noDangerouslySetInnerHtml: a module constant; see above.
      dangerouslySetInnerHTML={{ __html: ICON[name] }}
    />
  );
}
