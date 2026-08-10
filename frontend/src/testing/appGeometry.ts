/**
 * The sizes the app states for itself, in one place.
 *
 * A story that checks its own box has to compare against something, and the one
 * thing it must not compare against is the mount that produced it -- that is
 * circular, and a wrong mount would produce a wrong-but-consistent pair and pass.
 * So these are the numbers as `board.css` and `lobby.css` write them, each citing
 * where, and an assertion that disagrees means either the story lost its mount or
 * the app's layout moved. Both are worth knowing.
 *
 * Constants and clamps are separated because they are checked differently. A
 * clamp cannot be compared to a literal: `vh` resolves against the *iframe* a
 * story runs in, not the window, and this app has one media query keyed on
 * viewport height as well. `expectMountedLike` resolves the clamp in the same
 * document it is measuring, which is correct in the tall canvas and on the short
 * docs page alike.
 */

/** Fixed pixel tracks. */
export const APP_BOX = {
  /** The stack and the log. `board.css`, `.table__body` grid-template-columns. */
  railLeft: 232,
  /** The preview, the action panel and the commit dock. Same rule. */
  railRight: 304,
  /** Your mat's info column, which is what sizes `PlayerOrb`. `.mat`. */
  matSide: 190,
  /** An opponent's, same job. `.mat--compact`. */
  matSideCompact: 112,
  /** The floor a compact mat may not shrink past. `.mat--compact`. */
  matCompactMinWidth: 288,
} as const;

/** Sizes the app expresses as a clamp, so they are resolved rather than read. */
export const APP_CLAMP = {
  /** The card preview's fixed frame. `board.css`, `.preview`. */
  previewHeight: "clamp(240px, 34vh, 420px)",
  /** A seat's whole width in the lobby. `lobby.css`, `.podhand` `--card-w`. */
  podhandCardW: "clamp(152px, 25vh, 296px)",
  /** A tile's card in the deck catalogue. `lobby.css`, `.rack` `--card-w`. */
  rackCardW: "clamp(122px, 15vh, 168px)",
  /** The dossier's commander. `lobby.css`, `.dos__top` `--card-w`. */
  dossierCardW: "clamp(150px, 22vh, 214px)",
} as const;
