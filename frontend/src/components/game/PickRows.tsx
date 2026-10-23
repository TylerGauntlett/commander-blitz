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
import type { GameView, LegalAction } from "../../api/types";
import { actionAttrs, stopId } from "../../input/stops";
import type { PickOption } from "../../logic/pickSeveral";
import type { Previewing } from "./previewing";

interface Props {
  state: GameView;
  options: PickOption[];
  chosen: readonly number[];
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

interface OneProps {
  state: GameView;
  options: PickOption[];
  actions: LegalAction[];
  disabled: boolean;
  onAct: (actionId: string) => void;
  ptOf: (oid: number) => string | null;
  previewing: Previewing;
}

/**
 * The mirror of a board pick (`logic/pickSeveral.isBoardPick`): one row per
 * permanent, and the row IS the answer.
 *
 * Unlike a set's rows these carry the `choose` action's id, because a pick of
 * one has nothing to build -- the press sends it, on the board or here. The
 * board's cards carry `card:` stops and no id, so each id is still in the
 * document once. They are the surface for a permanent the layout does not
 * draw: an opponent's lane at the handheld size.
 */
export function PickOneRows({
  state,
  options,
  actions,
  disabled,
  onAct,
  ptOf,
  previewing,
}: OneProps) {
  return (
    <>
      {options.map((option) => {
        const action = actions.find((a) => a.kind === "choose" && a.choice === option.choice);
        if (!action) return null;
        const pt = option.oid !== null ? ptOf(option.oid) : null;
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
            className="act"
            {...actionAttrs(action.id)}
            data-action-kind={action.kind}
            data-testid="pick-one"
            data-choice={option.choice}
            disabled={disabled}
            onClick={() => onAct(action.id)}
            data-hint={`Choose ${option.label}`}
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
