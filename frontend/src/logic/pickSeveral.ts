/**
 * "Any number of target permanents", as a set the player builds.
 *
 * The engine takes several picks one `choose` at a time and closes the decision
 * on the last allowed one -- right for an agent, and no way for a person to
 * change their mind. So the client keeps the set itself and sends it whole
 * through `/choose` (`server/sessions.choose`).
 *
 * IT LIVES IN THE ACTION PANEL, the way declaring attackers does. It used to be
 * a modal of card faces; before that, a spell's "any number" was one cast line
 * per subset, drawn as a column of "A + B + C" chips and capped at twelve --
 * Clever Concealment over six permanents offered eleven of sixty-three. The
 * engine now asks for the set as the cast happens
 * (`engine/casting.deferred_target_spec`), and this is where it is answered:
 * one row per candidate to toggle, an "all" mark, and a Confirm slab -- the
 * attack declaration's shape, and the board's cards toggle it too.
 */

import type { CardView, GameView, LegalAction } from "../api/types";
import { findCard } from "./zoneGrouping";

/**
 * The engine purposes that are a free choice of several things on the table.
 *
 * `target` is `ask_targets`' default -- "exile up to two target artifacts",
 * "any number of target creatures" -- and `proliferate` is the same shape with
 * players in it. Discarding to hand size and the mulligan's bottoming are
 * multi-picks too, and deliberately not here: they keep answering one press at
 * a time, which is what every e2e helper that clears a board of prompts does.
 */
const PICK_SEVERAL = new Set(["target", "proliferate"]);

/**
 * Is the decision on the table ours, and a set to build?
 *
 * Only before the first pick: a decision already part answered some other way
 * is finished the way it was started.
 */
export function isPickSeveral(state: GameView): boolean {
  const pending = state.pending;
  if (pending === null || pending.player !== state.seat || state.game_over) return false;
  const purpose = pending.context?.purpose;
  return (
    pending.max_count > 1 &&
    pending.selected.length === 0 &&
    typeof purpose === "string" &&
    PICK_SEVERAL.has(purpose)
  );
}

/** One thing that can be put in the set. */
export interface PickOption {
  /** The ordinal into `pending.options`, which is what `/choose` takes. */
  choice: number;
  /** A permanent's oid, or null for a player. */
  oid: number | null;
  /** A player's seat, or null for a permanent. */
  pid: number | null;
  card: CardView | null;
  label: string;
  /** Whose it is: 0 yours, 1 somebody else's, 2 a player. */
  rank: 0 | 1 | 2;
}

/**
 * The candidates, yours first, then each opponent's, then players -- the order
 * the table reads in.
 */
export function pickOptions(state: GameView, actions: LegalAction[]): PickOption[] {
  const pending = state.pending;
  if (pending === null) return [];
  const out: PickOption[] = [];
  for (const action of actions) {
    if (action.kind !== "choose" || action.choice === null) continue;
    const option = pending.options[action.choice];
    const ref = option?.ref ?? action.targets[0] ?? null;
    const oid = ref?.kind === "object" ? ref.id : null;
    const pid = ref?.kind === "player" ? ref.id : null;
    const card = option?.card ?? (oid !== null ? findCard(state, oid) : null);
    const label =
      card?.name ??
      (pid !== null
        ? (state.players[pid]?.name ?? `P${pid}`)
        : (option?.label ?? action.label));
    const rank = card === null ? 2 : card.controller === pending.player ? 0 : 1;
    out.push({ choice: action.choice, oid, pid, card, label, rank });
  }
  return out.sort((a, b) => a.rank - b.rank);
}

/**
 * The action Confirm carries, so the slab is a real `data-action-id` control.
 *
 * `Done` when there is one, which is what committing nothing means; any choose
 * action otherwise, because the press sends the set, not the id.
 */
export function pickCarrier(actions: LegalAction[]): LegalAction | null {
  return (
    actions.find((a) => a.kind === "finish_declaration") ??
    actions.find((a) => a.kind === "choose") ??
    null
  );
}

/**
 * Is the decision on the table ours, and one pick of a permanent at a time?
 *
 * "Sacrifice a creature", "destroy target artifact", a trigger's target: a
 * `choose_objects` whose every option is a permanent on the battlefield. The
 * board answers it -- the press on the card IS the answer, so a pick of one
 * costs one press, the ring opening on the first option -- and the panel's
 * rows mirror it for whatever the layout does not draw. Before this it was a
 * modal of card faces over the board, so the press a handheld player makes on
 * the board went nowhere for exactly the decision whose subject is the board.
 *
 * A set to build (`isPickSeveral`) is not this, and neither is anything whose
 * options are off the table -- a library, a hand, a graveyard, a player, a
 * mode -- which `PromptDialog` keeps. `isModalDecision` reads this, so the
 * split between the board and the dialog is decided once.
 */
export function isBoardPick(state: GameView): boolean {
  const pending = state.pending;
  if (pending === null || pending.player !== state.seat || state.game_over) return false;
  if (pending.kind !== "choose_objects" || isPickSeveral(state)) return false;
  if (pending.options.length === 0) return false;
  return pending.options.every((option) => {
    const ref = option.ref;
    return ref?.kind === "object" && findCard(state, ref.id)?.zone === "battlefield";
  });
}

/** The `choose` action a press on `oid` answers a board pick with, if any. */
export function boardPickAction(
  state: GameView,
  actions: LegalAction[],
  oid: number,
): LegalAction | null {
  const pending = state.pending;
  if (pending === null) return null;
  return (
    actions.find((action) => {
      if (action.kind !== "choose") return false;
      const ref =
        action.choice !== null
          ? (pending.options[action.choice]?.ref ?? action.targets[0])
          : action.targets[0];
      return ref?.kind === "object" && ref.id === oid;
    }) ?? null
  );
}
