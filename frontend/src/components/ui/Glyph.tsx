/**
 * A picture of a button.
 *
 * Text on a disc rather than an icon set, for a reason that is not laziness:
 * the Deck's own face buttons are literally lettered A B X Y in that layout, so
 * the letter *is* the icon. An SVG sprite would be a network request, a
 * licensing question, and a second thing to keep in step with the button map.
 *
 * ## Both labels are always rendered, and CSS picks one
 *
 * A `Glyph` emits the pad label and the keyboard label as siblings, and
 * `handheld.css` shows whichever matches `html[data-input]`. That is the whole
 * mechanism behind "a mouse player never sees a controller hint", and it is
 * deliberately not React: a hook here would re-render every hint in the app on
 * every pointer move. Rendering both and hiding one costs two spans and no
 * renders at all.
 *
 * `aria-hidden` because this is a picture of a control, not the control. Where
 * a glyph sits inside a real button, that button already has its own accessible
 * name; where it sits in the hint bar, the bar is decoration over a board that
 * says the same things in its own markup. Announcing "A" to a screen reader
 * would be describing hardware the listener may not have.
 *
 * Biome's `noAriaHiddenOnFocusable` fires on both, and is suppressed inline. A
 * `<b>` has no tabindex and no implicit role, so it is not focusable; the rule's
 * suggested fix -- remove `aria-hidden` -- would make a decorative letter part
 * of the accessible name of every control it decorates.
 */

import { KEY_LABEL, PAD_LABEL, type PadButton } from "../../input/buttons";

interface Props {
  btn: PadButton | "dpad";
}

/** The d-pad is four buttons and one picture, so it is not in the button map. */
const DPAD = { pad: "✛", key: "↑↓←→" };

export function Glyph({ btn }: Props) {
  const pad = btn === "dpad" ? DPAD.pad : PAD_LABEL[btn];
  const key = btn === "dpad" ? DPAD.key : (KEY_LABEL[btn] ?? PAD_LABEL[btn]);
  return (
    <>
      {/* biome-ignore lint/a11y/noAriaHiddenOnFocusable: a `<b>` is not focusable -- no tabindex, no implicit role -- and the rule's fix, dropping `aria-hidden`, is the opposite of what this needs. See the header. */}
      <b className={`glyph glyph--pad glyph--${btn}`} aria-hidden="true" data-glyph={btn}>
        {pad}
      </b>
      {/* biome-ignore lint/a11y/noAriaHiddenOnFocusable: as above. */}
      <b className={`glyph glyph--key glyph--${btn}`} aria-hidden="true" data-glyph={btn}>
        {key}
      </b>
    </>
  );
}
