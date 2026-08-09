/**
 * The geometry of a collapsed stack, shared by the thing that draws it and the
 * thing that predicts how much room it will take.
 *
 * These four numbers used to live only in `CardStack`, which was right while it
 * was the only reader. `logic/zoomFit.ts` now has to compute a stack's footprint
 * at a card width nothing has rendered at yet, so it needs the same constants --
 * and a copy of them in the solver would be a copy that silently stops matching
 * the moment somebody tunes the peek. Both import from here instead.
 *
 * `CardStack` keeps the constants that are only about *drawing* a stack (the fan
 * step, the ply's vertical lift, the z-order): nothing outside it needs those,
 * and the reason each is the value it is belongs next to the code it governs.
 */

/** How far each hidden ply peeks out from under the top card, in px. */
export const PLY_X = 7;

/**
 * Beyond this many, plies sit on top of each other and the count badge carries
 * the number. So a stack's footprint stops growing here -- which is exactly why
 * the solver can treat twelve basics as one box.
 */
export const MAX_PLIES = 2;

/**
 * How far an aura or equipment peeks out from under its host, as a fraction of a
 * card. Down and to the right, far enough that the attachment's own title bar
 * stays readable and clickable.
 */
export const ATTACH_X_RATIO = 0.22;
export const ATTACH_Y_RATIO = 0.1;
