/**
 * The X stepper: the one control that changes WHICH id the commit slab points
 * at, rather than adding more.
 *
 * Lifted out of `ActionPanel.tsx` as it was. The panel keeps the answer
 * (`useState` keyed on the decision, so a new spell starts from zero) and
 * hands this the clamped value and the setter.
 */

interface Props {
  clampedX: number;
  maxX: number;
  perPoint: number;
  disabled: boolean;
  setChosenX: (value: number) => void;
}

export function XStepper({ clampedX, maxX, perPoint, disabled, setChosenX }: Props) {
  return (
    <div className="xstep" data-testid="choose-x" data-x={clampedX}>
      <button
        type="button"
        className="xstep__btn"
        data-testid="choose-x-down"
        disabled={disabled || clampedX <= 0}
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
        disabled={disabled || clampedX >= maxX}
        onClick={() => setChosenX(clampedX + 1)}
        aria-label="One more"
      >
        +
      </button>
      <span className="xstep__hint">
        up to {maxX}
        {perPoint > 1 && ` · ${perPoint} mana per point`}
      </span>
    </div>
  );
}
