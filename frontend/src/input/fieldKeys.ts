/**
 * Which keys a text field or a `<select>` keeps, and which go to the ring.
 *
 * The keyboard half of `pad.ts`: `onKeyDown` asks `fieldKeeps` before it turns
 * a key into a pad intent, and an overlay asks `padTakesKey`.
 */

import { KEYS } from "./buttons";

/** The four keys a text field and the ring both have a claim on. */
export const ARROWS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);

/** A native option list, which bargains over a different set -- see `SELECT_KEEPS`. */
export function isSelect(target: EventTarget | null): boolean {
  return (target as HTMLElement | null)?.tagName === "SELECT";
}

/** Anything with a caret in it, which is the only thing `fieldKeeps` bargains with. */
export function isField(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el?.tagName) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable === true;
}

/**
 * Whether a field keeps this key for itself, or hands it to the ring.
 *
 * THE OLD ANSWER WAS "A FIELD KEEPS EVERYTHING", AND IT WAS A ONE-WAY DOOR.
 *
 * A field is a stop like any other off the board, so the ring walks onto the
 * seat-name box, the search box or the code box in the ordinary course of
 * moving around -- and once there, every arrow went to the caret and none of
 * them to navigation. On a desktop Tab is the way out; on a Deck there is no
 * Tab, so the ring was in the field for the rest of the session and the screen
 * was over. The handheld playtest log has no word for this because no loop
 * ever got past it.
 *
 * The rule is the one every console text field uses, and it needs no mode and
 * no extra button: **a direction is the caret's while the caret has somewhere
 * to go in that direction, and the ring's at the end of the line.** Left with
 * the caret mid-word moves the caret; left again from column zero leaves the
 * field. Up and Down only ever belong to a textarea, and only while there is
 * another line that way.
 *
 * Everything that is not a direction is still the field's without asking:
 * letters, Enter, Escape, Backspace. `w`/`a`/`s`/`d` are directions to the pad
 * layer and letters here, which is the whole reason this asks about the key
 * rather than about the element.
 */
/**
 * What a `<select>` keeps, which is NOT everything.
 *
 * IT USED TO BE EVERYTHING, AND THAT MADE THE SORT DROPDOWN A ONE-WAY DOOR
 * WITH A HISTORY STEP IN IT. Two separate failures came out of the one line.
 *
 * The trap first: a select has no caret, so the bargain the text fields strike
 * above -- a direction is the caret's while the caret has somewhere to go --
 * has nothing to measure and was skipped entirely. Every arrow went to the
 * control, so the ring walking onto the deck catalogue's `Sort` box could never
 * walk off it again. The old comment here said "`B` is the way out", and B was
 * bound on exactly one surface in the app and not on the catalogue.
 *
 * And the worse half: `Backspace` was kept too, which meant `SWALLOW` never ran
 * for it -- and `Backspace` on a `<select>` is not a character, it is the
 * browser's BACK BUTTON. From `/pods/{code}` that is the front door, so a
 * player whose controller sends Backspace for B (which is what a Steam Deck's
 * stock browser template does) was dropped out of the pod entirely by the
 * button that should have closed the catalogue over it.
 *
 * So a select now keeps only the keys that OPERATE one: up and down step the
 * option, page up and page down jump it, Enter opens it. Left and Right have
 * nothing to do on a list with no caret and belong to the ring, which is also
 * the only exit a direction can give. Everything else -- Escape, Backspace, B
 * -- is a way out and is treated as one.
 */
const SELECT_KEEPS = new Set(["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Enter"]);

export function fieldKeeps(target: EventTarget | null, key: string): boolean {
  const el = target as HTMLElement | null;
  if (!el?.tagName) return false;
  if (el.tagName === "SELECT") return SELECT_KEEPS.has(key);
  const typed = el.tagName === "INPUT" || el.tagName === "TEXTAREA";
  if (!typed && el.isContentEditable !== true) return false;
  if (!ARROWS.has(key)) return true;
  // No caret arithmetic to do on a contenteditable, and nothing in this client
  // is one; keeping the old behaviour there is the conservative half.
  if (!typed) return true;

  const field = el as HTMLInputElement | HTMLTextAreaElement;
  let at: number | null = null;
  let end: number | null = null;
  try {
    // `selectionStart` throws on an `<input type="number">` in some engines and
    // is null on several other types. Either way we have no caret to reason
    // about, so the ring takes the key rather than the field trapping it.
    at = field.selectionStart;
    end = field.selectionEnd;
  } catch {
    return false;
  }
  if (at === null || end === null) return false;
  // A range somebody is extending with Shift: collapsing it is the field's job.
  if (at !== end) return true;

  if (key === "ArrowLeft") return at > 0;
  if (key === "ArrowRight") return at < field.value.length;
  // Only a textarea has another line to reach, and only on the side it has one.
  if (el.tagName !== "TEXTAREA") return false;
  return key === "ArrowUp"
    ? field.value.slice(0, at).includes("\n")
    : field.value.slice(at).includes("\n");
}

/**
 * Whether this key press will arrive as a pad intent, or was kept by a field.
 *
 * Exported for the one caller that has to know: an overlay's Back listener.
 * `Escape` is `B`, so a dialog answering the pad's `b` has already handled every
 * Escape the ring hears -- but a text field keeps Escape for itself (see
 * `fieldKeeps`, and `ChoiceCombo` which depends on it), and no intent is emitted
 * for those. Asking here is what lets a dialog cover that gap without covering
 * the presses twice: two listeners answering one Escape closed two overlays at
 * once, which is a Back that goes one level too far.
 */
export function padTakesKey(event: KeyboardEvent): boolean {
  return KEYS[event.key] !== undefined && !fieldKeeps(event.target, event.key);
}
