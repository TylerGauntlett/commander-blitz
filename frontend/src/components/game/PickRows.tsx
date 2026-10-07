/**
 * The pick rows: one per candidate of a pick-several decision, toggled into a
 * set that the commit slab sends whole.
 *
 * `AttackRows`' shape on purpose -- "any number of target permanents" is the
 * same question as "which creatures attack": a set of things on the table,
 * built one toggle at a time, committed once. See `logic/pickSeveral.ts` for
 * why it is here rather than a dialog.
 *
 * NOT ACTIONS. The rows carry a `combo:` stop and no `data-action-id`: the
 * engine's `choose` actions are one pick each, and the set goes through
 * `/choose`. The slab is the one control carrying an id for this decision --
 * the split the dialog made before this, and `ChoiceCombo` makes.
 */

import type { MouseEvent } from "react";
import type { GameView } from "../../api/types";
import { stopId } from "../../input/stops";
import type { PickOption } from "../../logic/pickSeveral";
import type { Previewing } from "./previewing";

interface Props {
  state: GameView;
  options: PickOption[];
  chosen: number[];
  full: boolean;
  disabled: boolean;
  onToggle: (option: PickOption, index: number, event: MouseEvent<HTMLButtonElement>) => void;
  ptOf: (oid: number) => string | null;
  previewing: Previewing;
}

/** The stop a pick row carries, so the panel can send the ring to the next one. */
export const pickStop = (option: PickOption) => stopId.combo(`pick:${option.choice}`);

export function PickRows({
  state,
  options,
  chosen,
  full,
  disabled,
  onToggle,
  ptOf,
  previewing,
}: Props) {
  return (
    <>
      {options.map((option, index) => {
        const on = chosen.includes(option.choice);
        const pt = option.oid !== null ? ptOf(option.oid) : null;
        // Whose it is, on every permanent: "any number of target permanents"
        // can reach across the table, and your Rhystic Study and theirs read
        // the same. Its own class -- the handheld rail hides `.act__type`.
        const owner =
          option.card === null
            ? null
            : option.rank === 0
              ? "You"
              : (state.players[option.card.controller]?.name ?? null);
        return (
          <button
            type="button"
            key={option.choice}
            className={`act act--staged${on ? " act--on" : ""}`}
            data-stop={pickStop(option)}
            data-testid="pick-option"
            data-choice={option.choice}
            data-staged={on ? "true" : undefined}
            aria-pressed={on}
            // A full set takes nothing more; what is in it can still come out.
            disabled={disabled || (full && !on)}
            onClick={(event) => onToggle(option, index, event)}
            data-hint={
              on ? `${option.label} — click to take it back` : `Choose ${option.label}`
            }
            {...previewing(option.oid)}
          >
            <span className="act__name">{option.label}</span>
            {owner && <span className="act__owner">{owner}</span>}
            {pt && <span className="act__pt tabular">{pt}</span>}
          </button>
        );
      })}
    </>
  );
}
