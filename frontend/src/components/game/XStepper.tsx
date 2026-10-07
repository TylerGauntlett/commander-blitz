/**
 * The X stepper: the one control that changes WHICH id the commit slab points
 * at, rather than adding more.
 *
 * Lifted out of `ActionPanel.tsx` as it was. The panel keeps the answer
 * (`useState` keyed on the decision, so a new spell starts from its floor) and
 * hands this the clamped value and the setter.
 *
 * `minX` is the floor a mana-value casting lock puts under X -- Brisela's
 * "can't cast spells with mana value 3 or less" leaves a Fireball castable only
 * for X = 3 or more. It is 0 for every other question.
 *
 * BOTH BUTTONS ARE STOPS. They were plain buttons, and the panel is a surface
 * that declares its stops (`input/stops.ts:stopsIn`), so the ring walked from
 * the slab straight past them: on a pad, X could only be paid at its floor.
 * Finale of Devastation for X = 0 is a tutor for a 0-drop.
 */

import { stopId } from "../../input/stops";

interface Props {
  clampedX: number;
  minX: number;
  maxX: number;
  perPoint: number;
  disabled: boolean;
  setChosenX: (value: number) => void;
}

export function XStepper({ clampedX, minX, maxX, perPoint, disabled, setChosenX }: Props) {
  return (
    <div className="xstep" data-testid="choose-x" data-x={clampedX}>
      <button
        type="button"
        className="xstep__btn"
        data-testid="choose-x-down"
        data-stop={stopId.combo("x-down")}
        disabled={disabled || clampedX <= minX}
        onClick={() => setChosenX(clampedX - 1)}
        aria-label="One less"
      >
        −
      </button>
      <span className="xstep__value tabular">X = {clampedX}</span>
      <button
        type="button"
        className="xstep__btn"
        data-testid="choose-x-up"
        data-stop={stopId.combo("x-up")}
        disabled={disabled || clampedX >= maxX}
        onClick={() => setChosenX(clampedX + 1)}
        aria-label="One more"
      >
        +
      </button>
      <span className="xstep__hint">
        {minX > 0 ? `${minX} to ${maxX}` : `up to ${maxX}`}
        {perPoint > 1 && ` · ${perPoint} mana per point`}
      </span>
    </div>
  );
}
