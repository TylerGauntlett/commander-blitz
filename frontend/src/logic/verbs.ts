/**
 * What each button would do, right now, in words.
 *
 * The hint bar is the controller's answer to a mouse's most under-appreciated
 * property: a pointer tells you what a click will do *before* you click, by
 * where it is and what changes under it. A ring tells you where you are and
 * nothing about what happens next, so the verb has to be written down.
 *
 * THIS IS TEXT ABOUT THE RING, NOT A SECOND COPY OF THE ACTION SPACE. Nothing
 * here produces or names an action id, and `HintBar` renders spans rather than
 * buttons. That is what keeps the panel's "every legal action is a button
 * carrying `data-action-id`, exactly once in the document" invariant intact --
 * see the header of `components/game/ActionPanel.tsx`. It is the same
 * discipline the targeting hint in `Table.tsx` already follows.
 *
 * The verbs are derived from the *same predicates* `Table.onBoardCard` routes
 * on, and in the same order, because a hint that disagrees with what the button
 * actually does is worse than no hint at all. When that routing changes, this
 * changes with it, and `tests/verbs.test.ts` is what notices.
 */

import type { GameView, LegalAction } from "../api/types";
import { blockableBy, defendersFor } from "./actionMatch";
import { mulliganPhase } from "./openingHand";
import { findCard } from "./zoneGrouping";

/** The kinds of thing the ring can be resting on. See `input/stops.ts`. */
export type StopKind =
  | "card"
  | "orb"
  | "act"
  | "tool"
  | "pile"
  | "lane"
  | "commit"
  | "combo"
  | "unknown";

export interface StopRef {
  kind: StopKind;
  /** Card oid, player pid, or zone name, depending on `kind`. */
  id: number | null;
  /** The raw stop id, for kinds that carry a string payload. */
  raw: string;
}

/**
 * Split a stop id into its kind and payload.
 *
 * Stops are a string namespace rather than an index precisely so this is
 * possible without a registry: the id survives a re-render, a reorder, and a
 * whole new game, and it can be read back without asking the DOM anything.
 */
export function parseStop(stop: string | null): StopRef {
  if (!stop) return { kind: "unknown", id: null, raw: "" };
  const [head, ...rest] = stop.split(":");
  const tail = rest.join(":");
  switch (head) {
    case "card":
    case "orb":
      return { kind: head, id: Number(tail), raw: stop };
    case "act":
    case "tool":
    case "pile":
    case "lane":
    case "combo":
      return { kind: head, id: null, raw: stop };
    case "commit":
      return { kind: "commit", id: null, raw: stop };
    default:
      return { kind: "unknown", id: null, raw: stop };
  }
}

export interface Verbs {
  /** What `A` does. Always present: `A` is never a no-op the player can see. */
  a: string;
  /** What `X` does, when it does anything. */
  x?: string;
  /** What `Y` does. Reading a card is available wherever there is a card. */
  y?: string;
  /** What `B` does, or absent at the top of the unwind stack. */
  b?: string;
}

/** The player's own combat staging, as `uiStore` holds it. */
export interface Staging {
  stagedAttacks: Record<number, number>;
  stagedBlocks: Record<number, number>;
  /** The blocker picked but not yet pointed at an attacker. */
  selectedOid: number | null;
  /** True while a spell is waiting for a target. */
  targeting: boolean;
}

const EMPTY: Staging = {
  stagedAttacks: {},
  stagedBlocks: {},
  selectedOid: null,
  targeting: false,
};

/** The action an `act:` stop names, if the list still has it. */
function actionFor(actions: LegalAction[], ref: StopRef): LegalAction | undefined {
  const id = ref.raw.slice("act:".length);
  return actions.find((candidate) => candidate.id === id);
}

/**
 * The verbs for the stop the ring is on.
 *
 * The branch order mirrors `Table.onBoardCard` exactly:
 *
 *   1. finishing a targeted spell
 *   2. attacking -- a plain toggle
 *   3. blocking -- pick your creature, then the attacker it stops
 *   4. otherwise, an activated ability
 *
 * A stop the player can reach but cannot act on gets `"Read"` rather than a
 * blank: "nothing happens" is a legitimate answer and the bar should say it,
 * because a bar that goes empty reads as a bar that has broken.
 */
export function verbsFor(
  state: GameView,
  actions: LegalAction[],
  stop: string | null,
  staging: Staging = EMPTY,
): Verbs {
  const ref = parseStop(stop);
  const decision = state.pending?.player === state.seat ? state.pending.kind : null;

  /*
   * THE OPENING HAND OWNS THE WHOLE SCREEN, SO IT OWNS THE BAR.
   *
   * Two things below would otherwise be lies on that screen, and both are the
   * exact defect this file exists to prevent.
   *
   * `A` on a hand card would fall to the generic card tail and say `Read`,
   * because a card in your opening hand has no legal action of its own. What
   * `A` actually does there is KEEP -- `OpeningHand` binds it, scoped to card
   * stops, because a card's own click has to stay "select" for a mouse.
   *
   * And `b: "Back"` is on almost every branch below, which is true on a board
   * and false here: declining to mulligan is itself an answer, so `B` is bound
   * to Mulligan while the first question is up and to nothing at all while the
   * second is. A bar that says `B Back` over a button that does not go back is
   * how a player learns to stop reading it.
   */
  const mulligan = mulliganPhase(state);
  if (mulligan !== null) {
    const chosen = ref.kind === "act" ? actionFor(actions, ref) : undefined;
    const verb = chosen?.base_label || chosen?.label;
    if (mulligan === "bottom") {
      // A card IS the answer here, so it carries the action and `A` is a click
      // on it. Nothing un-picks, so `B` is deliberately absent.
      return { a: verb || "To the bottom" };
    }
    return {
      a: verb || "Keep",
      b: "Mulligan",
      y: ref.kind === "card" ? "Read" : undefined,
    };
  }

  /*
   * The combat bar: the `all` mark, and the slab it sits beside.
   *
   * Both are `commit` stops rather than `act:` ones because neither is a
   * server action -- they stage into `uiStore` and declare what is staged. So
   * there is no `base_label` to read and the verb has to be written here, and
   * it is written to match the button's own words: a bar reading `A Confirm`
   * over a button reading `Attack` is the small kind of lie this file exists
   * to stop.
   */
  if (ref.kind === "commit") {
    if (ref.raw === "commit:all") {
      if (decision === "declare_attackers") return { a: "All attack", b: "Back" };
      if (decision === "declare_blockers") return { a: "All defend", b: "Back" };
      return { a: "All", b: "Back" };
    }
    if (decision === "declare_attackers") return { a: "Attack", b: "Back" };
    if (decision === "declare_blockers") return { a: "Block", b: "Back" };
    return { a: "Confirm", b: "Back" };
  }

  if (ref.kind === "act") {
    const action = actionFor(actions, ref);
    return { a: action?.base_label || action?.label || "Choose", b: "Back" };
  }

  if (ref.kind === "tool") return { a: "Toggle", b: "Back" };

  /*
   * The combobox a long decision opens with, and the two things in it.
   *
   * A row is a HIGHLIGHT, not a commitment: only the Choose button beside the
   * list submits, and it is an `act:` stop that answers with the action's own
   * label. Saying "Choose" over a row would promise a press that does not
   * happen, which is the one failure this whole file exists to prevent.
   */
  if (ref.kind === "combo") {
    return ref.raw === "combo:filter" ? { a: "Type", b: "Back" } : { a: "Select", b: "Back" };
  }
  if (ref.kind === "pile") return { a: "Look", b: "Back" };
  if (ref.kind === "lane") return { a: "Play here", b: "Back" };

  if (ref.kind === "orb" && ref.id !== null) {
    // During attacker declaration an opponent is where you point an attacker.
    if (decision === "declare_attackers" && staging.selectedOid !== null) {
      return { a: `Attack ${state.players[ref.id]?.name ?? "them"}`, b: "Back" };
    }
    if (staging.targeting) return { a: "Target", b: "Cancel" };
    return { a: "Look", y: "Read", b: "Back" };
  }

  if (ref.kind !== "card" || ref.id === null) return { a: "Select", b: "Back" };

  const oid = ref.id;
  const card = findCard(state, oid);

  // 1. Finishing a targeted spell.
  if (staging.targeting) {
    const targetable = actions.some((action) =>
      action.targets.some((target) => target.kind === "object" && target.id === oid),
    );
    if (targetable) return { a: `Target ${card?.name ?? "it"}`, y: "Read", b: "Cancel" };
    return { a: "Not a legal target", y: "Read", b: "Cancel" };
  }

  // 2. Attacking: a plain toggle, and `X` re-aims a staged attacker.
  if (decision === "declare_attackers") {
    const staged = staging.stagedAttacks[oid];
    if (staged !== undefined) {
      const canReaim = defendersFor(actions, oid).length > 1;
      return {
        a: "Withdraw",
        x: canReaim ? `Re-aim (${state.players[staged]?.name ?? "seat"})` : undefined,
        y: "Read",
        b: "Back",
      };
    }
    if (defendersFor(actions, oid).length > 0) return { a: "Attack", y: "Read", b: "Back" };
  }

  // 3. Blocking: pick your creature, then the attacker it stops.
  if (decision === "declare_blockers") {
    if (staging.stagedBlocks[oid] !== undefined) return { a: "Release", y: "Read", b: "Back" };
    if (
      staging.selectedOid !== null &&
      blockableBy(actions, staging.selectedOid).includes(oid)
    ) {
      return { a: `Block ${card?.name ?? "it"}`, y: "Read", b: "Back" };
    }
    if (blockableBy(actions, oid).length > 0) {
      return {
        a: staging.selectedOid === oid ? "Deselect" : "Block with",
        y: "Read",
        b: "Back",
      };
    }
    const aimedHere = Object.values(staging.stagedBlocks).includes(oid);
    if (aimedHere) return { a: "Clear blocks", y: "Read", b: "Back" };
  }

  // 4. Otherwise: casting from hand, or an activated ability.
  const own = actions.filter((action) => action.source_oid === oid);
  const casts = own.filter((action) => action.kind === "cast" || action.kind === "play_land");
  if (casts.length > 0) {
    /*
     * THE VERB ONLY, AND NOT THE CARD'S NAME.
     *
     * This was `base_label`, which is "Cast Vicious Conquistador" -- and the
     * hint bar is one line shared with the navigation half, so a long name
     * pushed `Region` and `Jump` onto a second row and the bar grew under the
     * hand. The name is not what the hint is for either: the ring is already on
     * the card, the reader beside it is already showing the card, and every
     * other stop here says a bare verb. `A` on a land is still `Play`, because
     * playing a land and casting a spell are different moves.
     */
    return {
      a: casts.every((action) => action.kind === "play_land") ? "Play" : "Cast",
      x: own.some((action) => action.kind === "activate") ? "Activate" : undefined,
      y: "Read",
      b: "Back",
    };
  }
  const abilities = own.filter((action) => action.kind === "activate");
  if (abilities.length > 0) {
    return {
      a: abilities.length === 1 ? (abilities[0].base_label ?? "Activate") : "Abilities",
      y: "Read",
      b: "Back",
    };
  }

  return { a: "Read", y: "Read", b: "Back" };
}

/**
 * The always-there half of the bar: how to move, and how to jump.
 *
 * IT ADVERTISED THREE BUTTONS THAT WERE NOT BOUND. `L1 Zone` and `L2 Menu` were
 * here from the first draft, `verbsFor` returns `Y Read` on every card stop,
 * and nothing in the app listened for any of the three -- so a player who read
 * the bar and pressed what it said got nothing back, three times.
 *
 * All three are bound now. `L1`/`R1` step between the board's regions
 * (`input/groups.ts`), `L2` held opens the dial that jumps straight to one and
 * tapped sends the ring to the commit slab, and `Y` reads the card the ring is
 * on at full size. `L1` stands for the pair because two glyphs for one idea is
 * what the bar is short of room for, and the direction is the obvious half.
 *
 * `L2` said `Jump`, which named the mechanism rather than the destination and
 * pointed at the tool strip -- a jump `Menu` already made. It says `Decide`
 * now, because the place worth a button of its own is the slab that ends the
 * decision: Attack, Block, Done, Pass. That control lives in the right rail,
 * and the ring is almost never near it.
 *
 * `tests/hintsBound.test.ts` fails the build if a button named here loses its
 * listener, which is the cheap way to stop this happening a second time. It
 * reads the binding sites rather than mounting the board -- see its header for
 * what that does and does not prove.
 */
export const NAVIGATION_HINTS = [
  { btn: "dpad", label: "Move" },
  { btn: "l1", label: "Region" },
  { btn: "l2", label: "Decide" },
] as const;
