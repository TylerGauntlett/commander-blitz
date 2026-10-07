/**
 * Gesture routing for the table: every press on a card, a lane, a seat or a
 * panel row, turned into a legal action or a staging step.
 *
 * Lifted out of `Table.tsx` as it was. `Table`'s header still holds the rule:
 * if a gesture cannot be mapped to a legal action, it does nothing at all -- it
 * never invents one.
 */

import { useCallback } from "react";
import type { CardView, GameView, LegalAction, StackItemView } from "../api/types";
import type { SoundName } from "../audio/sfx";
import { abilityRoute } from "../logic/abilities";
import { actionsForCard, blockableBy, canDropOnLane, defendersFor } from "../logic/actionMatch";
import type { Gesture } from "../logic/followUp";
import { isPickSeveral, pickKey, pickOptions } from "../logic/pickSeveral";
import type { Lane as LaneName } from "../logic/zoneGrouping";
import { useUiStore } from "../state/uiStore";
import type { useGame } from "../state/useGame";
import type { useTableDerived } from "../state/useTableDerived";

type Derived = ReturnType<typeof useTableDerived>;

interface Args {
  state: GameView;
  actions: LegalAction[];
  gateInput: () => boolean;
  act: (actionId: string) => void;
  cue: (sound: SoundName) => void;
  followUp: (gesture: Gesture) => void;
  targeting: Derived["targeting"];
  targetableOids: Derived["targetableOids"];
  combatCandidates: Derived["combatCandidates"];
  decisionKind: string | null;
  inCombatDecision: boolean;
  declareMutate: ReturnType<typeof useGame>["declare"]["mutate"];
  /** Open the full-screen read on a card. `A` on a stack ply is a read. */
  holdCard: (oid: number) => void;
}

export function useTableGestures({
  state,
  actions,
  gateInput,
  act,
  cue,
  followUp,
  targeting,
  targetableOids,
  combatCandidates,
  decisionKind,
  inCombatDecision,
  declareMutate,
  holdCard,
}: Args) {
  const selectedOid = useUiStore((s) => s.selectedOid);
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const beginTargeting = useUiStore((s) => s.beginTargeting);
  const narrowTargeting = useUiStore((s) => s.narrowTargeting);
  const select = useUiStore((s) => s.select);
  const stageAttack = useUiStore((s) => s.stageAttack);
  const unstageAttack = useUiStore((s) => s.unstageAttack);
  const stageBlock = useUiStore((s) => s.stageBlock);
  const unstageBlock = useUiStore((s) => s.unstageBlock);
  const viewingPid = useUiStore((s) => s.viewingPid);
  const setViewing = useUiStore((s) => s.setViewing);
  const setAbilityMenu = useUiStore((s) => s.setAbilityMenu);
  const togglePick = useUiStore((s) => s.togglePick);

  /** Play a card from hand: straight through if unambiguous, else start targeting. */
  const playFromHand = useCallback(
    (card: CardView) => {
      if (gateInput()) return;
      const candidates = actionsForCard(actions, card.oid);
      if (candidates.length === 0) return;
      if (candidates.length === 1 && candidates[0].targets.length === 0) {
        act(candidates[0].id);
        // The card is leaving your hand, so the ring must not leave with it.
        followUp({ kind: "played-from-hand", oid: card.oid });
        return;
      }
      beginTargeting(
        card.oid,
        candidates.map((a) => a.id),
      );
      // The board has just lit up somewhere else; go and stand on it.
      followUp({ kind: "targeting", actionIds: candidates.map((a) => a.id) });
    },
    [gateInput, actions, act, beginTargeting, followUp],
  );

  /**
   * A drop, and the two ways it can fail.
   *
   * Both used to `return` in silence, which is the worst possible answer to a
   * deliberate gesture: the card sprang back to the hand and nothing said
   * whether the game had refused it or simply not noticed. `deny` is the
   * difference between "you cannot do that" and "is this thing on".
   */
  const onDropOnZone = useCallback(
    (card: CardView, zone: string) => {
      if (gateInput()) return;
      /*
       * WHOSE lane, and it was being thrown away.
       *
       * `lane:<pid>:<lane>` names a seat and this read the lane and skipped the
       * pid, so a drop onto an opponent's creature row was treated as a drop
       * onto your own. It could not be reached while their lanes were the only
       * other drop zones and nothing dragged there; standing at their seat puts
       * their lanes under the viewer's own hand.
       */
      const [kind, pid, lane] = zone.split(":");
      if (
        kind !== "lane" ||
        Number(pid) !== state.seat ||
        !canDropOnLane(state, actions, card.oid, lane as LaneName)
      ) {
        cue("deny");
        return;
      }
      playFromHand(card);
    },
    [gateInput, state, actions, playFromHand, cue],
  );

  /** Clicking a permanent: resolve a target, or stage it for combat. */
  const onBoardCard = useCallback(
    (card: CardView) => {
      if (gateInput()) return;

      // 0. Building a pick-several set: the card is a toggle, the way an
      //    attacker is. The panel holds the same set (`logic/pickSeveral.ts`).
      if (isPickSeveral(state)) {
        const option = pickOptions(state, actions).find((o) => o.oid === card.oid);
        if (option) {
          const ceiling = Math.min(
            state.pending?.max_count ?? 0,
            pickOptions(state, actions).length,
          );
          togglePick(pickKey(state), option.choice, ceiling);
        } else {
          cue("deny");
        }
        return;
      }

      // 1. Finishing a targeted spell.
      //
      //    All the matches, not the first one. A target is only *one* of the
      //    questions a selection can be asking: Into the Roil aimed at a
      //    creature is still two actions, kicked and not, and `legality`
      //    emits unkicked first -- so `.find` here silently spent the player's
      //    kicker decision for them and made the kicked cast unreachable by
      //    any gesture. Narrowing hands the leftover choice to the panel.
      if (targeting.length > 0 && targetableOids.has(card.oid)) {
        const matches = targeting.filter((a) =>
          a.targets.some((ref) => ref.kind === "object" && ref.id === card.oid),
        );
        if (matches.length === 1) {
          act(matches[0].id);
          return;
        }
        if (matches.length > 1) {
          narrowTargeting(matches.map((a) => a.id));
          // The leftover choice is the panel's, so send the ring to it -- the
          // rows are the only surface that carries a kicked cast and an
          // unkicked one as two separate things to press.
          followUp({ kind: "targeting", actionIds: matches.map((a) => a.id) });
          return;
        }
      }

      // 2. Attacking: a plain toggle. Clicking an opponent re-points a staged
      //    attacker, so cycling defenders here would just make cancelling cost
      //    one click per opponent in a pod.
      if (decisionKind === "declare_attackers" && combatCandidates.has(card.oid)) {
        if (stagedAttacks[card.oid] !== undefined) {
          unstageAttack(card.oid);
          select(null);
          return;
        }
        const [first] = defendersFor(actions, card.oid);
        if (first !== undefined) {
          stageAttack(card.oid, first);
          select(card.oid);
        }
        return;
      }

      // 3. Blocking: pick your creature, then the attacker it stops. Every step
      //    of that is reversible -- click your blocker again to release it, or
      //    click the attacker to clear everything aimed at it.
      if (decisionKind === "declare_blockers") {
        if (stagedBlocks[card.oid] !== undefined) {
          unstageBlock(card.oid);
          return;
        }
        if (combatCandidates.has(card.oid)) {
          const picked = selectedOid === card.oid ? null : card.oid;
          select(picked);
          // Picking a blocker is only half of a block. The other half is an
          // attacker on somebody else's board, which on a handheld is not a
          // stop at all -- see `logic/followUp.ts`.
          if (picked !== null) followUp({ kind: "blocker-selected", blocker: picked });
          return;
        }
        if (selectedOid !== null && blockableBy(actions, selectedOid).includes(card.oid)) {
          stageBlock(selectedOid, card.oid);
          select(null);
          // ...and on to the next creature with a job, so a pod's worth of
          // attackers is two presses each rather than two plus a walk back.
          followUp({ kind: "block-staged", blocker: selectedOid });
          return;
        }
        const aimedHere = Object.entries(stagedBlocks)
          .filter(([, attacker]) => attacker === card.oid)
          .map(([blocker]) => Number(blocker));
        if (aimedHere.length > 0) {
          for (const blocker of aimedHere) unstageBlock(blocker);
          return;
        }
      }

      // 4. Otherwise: an activated ability. `logic/abilities.ts` decides which
      //    of the three things a press means, and `X` asks it the same thing.
      const route = abilityRoute(actions, card.oid);
      switch (route.kind) {
        case "act":
          act(route.id);
          return;
        case "target":
          // One ability, still a choice: a target on the board, or a variant
          // the panel's chips draw. Entering targeting on exactly its ids is
          // what lights the targets up; the follow-up is what sends the ring
          // to stand on one, or to the panel row when nothing on the board
          // is a target. `playFromHand` does both; this used to do neither.
          beginTargeting(card.oid, route.ids);
          followUp({ kind: "targeting", actionIds: route.ids });
          return;
        case "menu":
          // Several abilities. This used to select the card and leave the
          // choice to the panel, where on a handheld both rows read as the
          // card's name and an ellipsis; a sacrifice ability chosen by
          // guessing is a card lost. `AbilityMenu` asks instead.
          setAbilityMenu(card.oid);
          return;
        case "none":
          return;
      }
    },
    [
      gateInput,
      targeting,
      targetableOids,
      act,
      decisionKind,
      combatCandidates,
      actions,
      stagedAttacks,
      stagedBlocks,
      selectedOid,
      stageAttack,
      unstageAttack,
      stageBlock,
      unstageBlock,
      select,
      beginTargeting,
      narrowTargeting,
      followUp,
      setAbilityMenu,
      state,
      togglePick,
      cue,
    ],
  );

  /**
   * A press on a ply of the stack.
   *
   * A target first, the way a board card is (step 1 of `onBoardCard`): a
   * counterspell's legal targets are stack ids, and before this the only way
   * to aim one was a chip in the panel. Otherwise a read -- the hold `Y`
   * opens -- because the reason to stand on the stack is to decide whether to
   * answer what is on it, and that needs the text.
   */
  const onStackItem = useCallback(
    (item: StackItemView) => {
      if (gateInput()) return;
      if (targeting.length > 0) {
        const matches = targeting.filter((a) =>
          a.targets.some((ref) => ref.kind === "stack" && ref.id === item.sid),
        );
        if (matches.length === 1) {
          act(matches[0].id);
          return;
        }
        if (matches.length > 1) {
          narrowTargeting(matches.map((a) => a.id));
          followUp({ kind: "targeting", actionIds: matches.map((a) => a.id) });
          return;
        }
        cue("deny");
        return;
      }
      if (item.card) holdCard(item.card.oid);
    },
    [gateInput, targeting, act, narrowTargeting, followUp, cue, holdCard],
  );

  const onSelectPlayer = useCallback(
    (pid: number) => {
      if (gateInput()) return;
      // Re-point a staged attacker at whoever was clicked.
      if (decisionKind === "declare_attackers" && selectedOid !== null) {
        const legal = actions.some(
          (a) =>
            a.kind === "add_attacker" &&
            a.source_oid === selectedOid &&
            a.targets.some((ref) => ref.kind === "player" && ref.id === pid),
        );
        if (legal) {
          stageAttack(selectedOid, pid);
          return;
        }
      }
      // Finish a spell that targets a player -- all the matches, for the
      // reason `onBoardCard` step 1 gives.
      const matches = targeting.filter((a) =>
        a.targets.some((ref) => ref.kind === "player" && ref.id === pid),
      );
      if (matches.length === 1) act(matches[0].id);
      else if (matches.length > 1) narrowTargeting(matches.map((a) => a.id));
      /*
       * Otherwise: go and look at their board.
       *
       * Last, and that ordering is the whole rule. Aiming at a seat is a move
       * in the game and looking at one is not, so a press that could be either
       * has to be the game move -- an attacker that silently opened a board
       * viewer mid-combat would be the worst kind of surprise.
       *
       * Toggles, so the seat you are already reading takes you home. Never your
       * own seat: `.play__mine` is already your board.
       */ else if (matches.length === 0 && pid !== state.seat) {
        setViewing(viewingPid === pid ? null : pid);
      }
    },
    [
      gateInput,
      decisionKind,
      selectedOid,
      actions,
      stageAttack,
      targeting,
      act,
      narrowTargeting,
      state.seat,
      viewingPid,
      setViewing,
    ],
  );

  const onDeclare = useCallback(
    (kind: "attackers" | "blockers", pairs: [number, number][]) => {
      if (gateInput()) return;
      declareMutate({ kind, pairs });
    },
    [gateInput, declareMutate],
  );

  /**
   * The action bar during a combat declaration.
   *
   * The bar lists every legal action, which for combat is one `add_attacker` or
   * `add_blocker` per legal pair. Posting those straight to the server commits
   * them one at a time and there is no inverse action -- only Undo -- and a
   * single blocker committed onto a menace attacker can strand the declaration
   * with no legal `finish_declaration` at all. So the buttons stage instead,
   * exactly like clicking the card does, and the whole set goes up at once.
   */
  const onBarAct = useCallback(
    (actionId: string) => {
      if (gateInput()) return;
      const action = actions.find((a) => a.id === actionId);
      if (!action || !inCombatDecision) {
        act(actionId);
        return;
      }

      if (action.kind === "add_attacker" && action.source_oid !== null) {
        const defender = action.targets.find((ref) => ref.kind === "player")?.id;
        if (defender === undefined) return;
        if (stagedAttacks[action.source_oid] === defender) {
          unstageAttack(action.source_oid);
        } else {
          stageAttack(action.source_oid, defender);
        }
        return;
      }

      if (action.kind === "add_blocker" && action.source_oid !== null) {
        const attacker = action.targets.find((ref) => ref.kind === "object")?.id;
        if (attacker === undefined) return;
        if (stagedBlocks[action.source_oid] === attacker) {
          unstageBlock(action.source_oid);
        } else {
          stageBlock(action.source_oid, attacker);
          // The row and the card are two ways to make one gesture, so they get
          // the same follow-up. Only on staging: releasing a block is the
          // player putting a decision back, not making the next one.
          followUp({ kind: "block-staged", blocker: action.source_oid });
        }
        return;
      }

      if (action.kind === "finish_declaration") {
        const kind = decisionKind === "declare_attackers" ? "attackers" : "blockers";
        const staged = kind === "attackers" ? stagedAttacks : stagedBlocks;
        const pairs = Object.entries(staged).map(
          ([source, target]) => [Number(source), target] as [number, number],
        );
        // Nothing staged still means what it always meant: decline entirely.
        if (pairs.length > 0) {
          onDeclare(kind, pairs);
          return;
        }
      }

      act(actionId);
    },
    [
      gateInput,
      actions,
      inCombatDecision,
      decisionKind,
      stagedAttacks,
      stagedBlocks,
      stageAttack,
      unstageAttack,
      stageBlock,
      unstageBlock,
      onDeclare,
      act,
      followUp,
    ],
  );

  return {
    playFromHand,
    onStackItem,
    onDropOnZone,
    onBoardCard,
    onSelectPlayer,
    onDeclare,
    onBarAct,
  };
}
