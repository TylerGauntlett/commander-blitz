/**
 * The attack rows: one per creature that may attack, staging on a click.
 *
 * Lifted out of `ActionPanel.tsx` as it was. The invariant it inherits from the
 * panel's header: a creature with one legal defender is a row carrying the
 * pair's `data-action-id`; one with several is an inert row whose defender
 * chips each carry their own -- N pairs on N controls, never one id twice.
 */

import type { GameView, LegalAction } from "../../api/types";
import { actionAttrs } from "../../input/stops";
import { defendersFor } from "../../logic/actionMatch";
import type { Previewing } from "./previewing";

interface Props {
  attackers: number[];
  actions: LegalAction[];
  state: GameView;
  stagedAttacks: Record<number, number>;
  disabled: boolean;
  onStage: (actionId: string) => void;
  attackActionFor: (attacker: number, defender: number) => LegalAction | null;
  nameOf: (oid: number) => string;
  ptOf: (oid: number) => string | null;
  previewing: Previewing;
}

export function AttackRows({
  attackers,
  actions,
  state,
  stagedAttacks,
  disabled,
  onStage,
  attackActionFor,
  nameOf,
  ptOf,
  previewing,
}: Props) {
  return (
    <>
      {attackers.map((attacker) => {
        const defenders = defendersFor(actions, attacker);
        const chosen = stagedAttacks[attacker];
        const on = chosen !== undefined;
        const single = defenders.length === 1;
        const action = single ? attackActionFor(attacker, defenders[0]) : null;
        const rowClass = ["act", "act--staged", on ? "act--on" : ""].filter(Boolean).join(" ");
        // No `act__key` here. The rows used to number themselves 1, 2, 3 --
        // the attacker's position in a list nothing else refers to, in the
        // slot `PlayRows` uses for a hand card's real 1-9 key. On a handheld
        // rail that was 19px of badge per row saying nothing.
        const body = (
          <>
            <span className="act__name">{nameOf(attacker)}</span>
            {on && <span className="act__aim">→ {state.players[chosen]?.name ?? chosen}</span>}
            {ptOf(attacker) && <span className="act__pt tabular">{ptOf(attacker)}</span>}
          </>
        );

        // One legal defender: the row *is* the action, so attacking is a
        // single click on the obvious thing.
        if (single && action) {
          return (
            <button
              type="button"
              key={attacker}
              className={rowClass}
              {...actionAttrs(action.id)}
              data-action-kind={action.kind}
              data-attacker={attacker}
              data-defender={defenders[0]}
              data-staged={on ? "true" : undefined}
              aria-pressed={on}
              disabled={disabled}
              onClick={() => onStage(action.id)}
              {...previewing(attacker)}
            >
              {body}
            </button>
          );
        }

        // Several: the row is inert and each defender carries its own id,
        // which is what keeps N pairs on N controls. Only in a pod.
        return (
          <div
            key={attacker}
            className={`${rowClass} act--group`}
            data-attacker={attacker}
            data-staged={on ? "true" : undefined}
            {...previewing(attacker)}
          >
            {body}
            <span className="act__aims">
              {defenders.map((pid) => {
                const pairAction = attackActionFor(attacker, pid);
                if (!pairAction) return null;
                const aimed = chosen === pid;
                return (
                  <button
                    type="button"
                    key={pid}
                    className={aimed ? "aim aim--on" : "aim"}
                    {...actionAttrs(pairAction.id)}
                    data-action-kind={pairAction.kind}
                    data-attacker={attacker}
                    data-defender={pid}
                    // The pointer gets this from the group row it is
                    // inside; the ring lands on the chip itself and needs
                    // it said here. See `previewing`.
                    data-preview-oid={attacker}
                    aria-pressed={aimed}
                    disabled={disabled}
                    onClick={() => onStage(pairAction.id)}
                    data-hint={
                      aimed
                        ? `Attacking ${state.players[pid]?.name} — click to call it back`
                        : `Send at ${state.players[pid]?.name}`
                    }
                  >
                    {state.players[pid]?.name ?? pid}
                  </button>
                );
              })}
            </span>
          </div>
        );
      })}
    </>
  );
}
