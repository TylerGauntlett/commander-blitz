/**
 * The table.
 *
 * Owns layout and gesture routing; every rules question is answered by the
 * server's legal-action list. Three input paths converge on one `act(id)`:
 *
 *   1. drag a card from hand onto a lane
 *   2. click a card, then click its target
 *   3. press the button in the action bar
 *
 * The third always exists. If a gesture cannot be mapped to a legal action, it
 * does nothing at all -- it never invents one.
 */

import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CardView, GameView } from "../../api/types";
import { type SoundName, play } from "../../audio/sfx";
import { drive, restAll } from "../../fx/actuators";
import { getCursor, setCursor, setCursorContext, subscribeCursor } from "../../input/cursor";
import {
  type GroupId,
  getGroup,
  groupOf,
  groupRoot,
  landableStopsIn,
  nextGroup,
  rememberStop,
  rememberedStop,
  resetGroups,
  setGroup,
} from "../../input/groups";
import { onAny as onAnyPad, on as onPad, onFrame as onPadFrame } from "../../input/pad";
import { stopElement, stopId } from "../../input/stops";
import {
  actionsForCard,
  availableAttackers,
  blockableBy,
  canDropOnLane,
  defendersFor,
} from "../../logic/actionMatch";
import { reset as forgetCardRects } from "../../logic/cardRects";
import { groupForDecision } from "../../logic/focusGroup";
import { sourcesSpentBy } from "../../logic/mana";
import { removalsByOid } from "../../logic/removals";
import { parseStop } from "../../logic/verbs";
import type { Lane as LaneName } from "../../logic/zoneGrouping";
import { LANES, commandersOf, findCard, seatOrder } from "../../logic/zoneGrouping";
import { type PeekTarget, useUiStore } from "../../state/uiStore";
import type { GameSession, useGame } from "../../state/useGame";
import { useHandheldLayout } from "../../state/useHandheld";
import { useZoomFit } from "../../state/useZoomFit";
import { ActionPanel } from "./ActionPanel";
import { CardHold } from "./CardHold";
import { CardPreview } from "./CardPreview";
import { CombatArrows } from "./CombatArrows";
import { EventTicker } from "./EventTicker";
import { useCursorResolve } from "./FocusRing";
import { FxLayer, useScreenShake } from "./FxLayer";
import { GameOverScreen } from "./GameOverScreen";
import { Glyph } from "../ui/Glyph";
import { GroupDial } from "./GroupDial";
import { HandFan } from "./HandFan";
import { HintBar } from "./HintBar";
import { OpponentBoard } from "./OpponentBoard";
import { ParticleLayer, clearParticles } from "./ParticleLayer";
import { PhaseTrack } from "./PhaseTrack";
import { PlayerMat } from "./PlayerMat";
import { PromptDialog, isModalDecision } from "./PromptDialog";
import { StackPanel } from "./StackPanel";
import { ZonePeek } from "./ZonePeek";

/** Keyboard routes into the zone viewer, which previously had none. */
const PEEK_KEYS: Record<string, PeekTarget["zone"]> = {
  g: "graveyard",
  e: "exile",
  c: "command",
};

/** Decisions where clicking your own creatures means "commit it to combat". */
const COMBAT_DECISIONS = new Set(["declare_attackers", "declare_blockers"]);

type Game = ReturnType<typeof useGame>;

interface Props {
  session: GameSession;
  game: Game;
  state: GameView;
  onQuit: () => void;
  onRematch: () => void;
}

export function Table({ game, state, onQuit, onRematch }: Props) {
  const { actions, events, narration, busy, aiThinking, stalled } = game;
  const boardRef = useRef<HTMLDivElement>(null);
  // The three the zoom measures. Each is a grid track whose size the cards inside
  // it cannot change, which is the only reason reading them is safe; see
  // `state/useZoomFit.ts`.
  const tableRef = useRef<HTMLDivElement>(null);
  const mineRef = useRef<HTMLDivElement>(null);
  const podRef = useRef<HTMLDivElement>(null);
  const footRef = useRef<HTMLDivElement>(null);

  /*
   * The two holds, declared here because `back` unwinds them.
   *
   * `dialOpen` is the region picker; `heldCard` is the card being read full
   * screen. Both are local rather than in `uiStore` for the reason the `R2`
   * reading hold is: a hold has no meaning across a re-render, and a hold kept
   * in a store is a hold that can get stuck.
   */
  const [dialOpen, setDialOpen] = useState(false);

  /*
   * The card being read full screen, by oid.
   *
   * By oid and not by object, for the reason the reader in the mockup round
   * held a NAME rather than a node: the engine pushes a whole new state on
   * every action, so a card object captured here would be a snapshot that stops
   * matching the board the moment anything happens to it.
   */
  const [heldCard, setHeldCard] = useState<number | null>(null);

  const speed = useUiStore((s) => s.speed);
  const selectedOid = useUiStore((s) => s.selectedOid);
  const targetingActionIds = useUiStore((s) => s.targetingActionIds);
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const beginTargeting = useUiStore((s) => s.beginTargeting);
  const narrowTargeting = useUiStore((s) => s.narrowTargeting);
  const endTargeting = useUiStore((s) => s.endTargeting);
  const select = useUiStore((s) => s.select);
  const stageAttack = useUiStore((s) => s.stageAttack);
  const unstageAttack = useUiStore((s) => s.unstageAttack);
  const stageBlock = useUiStore((s) => s.stageBlock);
  const unstageBlock = useUiStore((s) => s.unstageBlock);
  const setPeek = useUiStore((s) => s.setPeek);
  const logOverlay = useUiStore((s) => s.logOverlay);
  const viewingPid = useUiStore((s) => s.viewingPid);
  const setViewing = useUiStore((s) => s.setViewing);
  const toggleLogOverlay = useUiStore((s) => s.toggleLogOverlay);
  const peek = useUiStore((s) => s.peek);
  const hover = useUiStore((s) => s.hover);
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const error = useUiStore((s) => s.error);
  const setError = useUiStore((s) => s.setError);

  // Motion values, not state: the shake writes these every frame and going
  // through React would re-render the whole board sixty times a second.
  const { x: shakeX, y: shakeY } = useScreenShake(narration.current);
  const viewer = state.players[state.seat];

  // Memoised because `useZoomFit` keys its solve on it: a fresh array every render
  // would re-run the fit on every render rather than when the board changes.
  const opponents = useMemo(
    () => seatOrder(state).filter((pid) => pid !== state.seat),
    [state],
  );

  // How every card in a graveyard or exile pile got there, for the zone modal.
  // Folded from the accumulated log rather than the view, which carries no
  // history; recomputed wholesale so an undo simply un-tells the story.
  const removals = useMemo(() => removalsByOid(events, game.cardName), [events, game.cardName]);
  const decisionKind = state.pending?.player === state.seat ? state.pending.kind : null;
  const inCombatDecision = decisionKind !== null && COMBAT_DECISIONS.has(decisionKind);
  const locked = busy || narration.busy;

  /*
   * Which layout this viewport wants.
   *
   * Viewport-driven and nothing else: a desktop player who picks up a
   * controller keeps the wide board and gains the ring, and a Deck user with no
   * pad gets the compact board and no glyphs. The two signals are deliberately
   * independent -- see `input/inputMode.ts`.
   */
  const handheld = useHandheldLayout();

  // Card positions are remembered globally, by oid, and oids restart with each
  // game. Leaving them behind would let the first death of a new table fly out
  // of wherever the last table's card #12 happened to be sitting.
  useEffect(() => forgetCardRects, []);

  // A decision's buttons must exist exactly once in the document. Whichever
  // surface owns a decision renders its ids; everything else stands down.
  //
  // There used to be two surfaces to keep straight here -- an action bar and a
  // combat panel, each with its own stand-down rule and a comment explaining why
  // they disagreed. `ActionPanel` is both of them, so the only question left is
  // whether the modal dialog owns the decision instead.
  const modalOwnsDecision = isModalDecision(state);

  // Depend on the `mutate` functions, which react-query keeps stable, rather
  // than on the mutation objects, which are new every render -- otherwise every
  // callback below is rebuilt each render and the keyboard listener with it.
  const actMutate = game.act.mutate;
  const declareMutate = game.declare.mutate;
  const undoMutate = game.undo.mutate;
  const fullControlMutate = game.setFullControl.mutate;
  const manualManaMutate = game.setManualMana.mutate;

  /**
   * Empty the queue and put the board back at rest.
   *
   * Skipping used to leave whatever was mid-flight still flying: `narration`
   * owns the beats, but the particles, the card actuators and the screen shake
   * all run on their own clocks past the end of the beat that started them --
   * which is exactly what makes a turn read as continuous, and exactly what you
   * do not want the instant the player says "enough".
   */
  const skipNarration = narration.skip;
  const skipAll = useCallback(() => {
    skipNarration();
    clearParticles();
    restAll();
  }, [skipNarration]);

  /**
   * Whether this gesture should be dropped, and the side effect of not dropping it.
   *
   * A click while narration is playing means "get on with it" -- *and* it means
   * the thing that was clicked. It used to mean only the first: the queue was
   * skipped and the gesture thrown away, so for the second or two after every
   * action the board ignored you, and playing it felt like it needed spamming.
   * Only a genuine in-flight request gates input now.
   */
  const narrationBusy = narration.busy;
  const gateInput = useCallback(() => {
    if (narrationBusy) skipAll();
    return busy;
  }, [busy, narrationBusy, skipAll]);

  /** A sound the player's own hand caused, played without waiting for anybody. */
  const muted = useUiStore((s) => s.muted);
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const cue = useCallback((sound: SoundName) => {
    if (!mutedRef.current) play(sound);
  }, []);

  const act = useCallback(
    (actionId: string) => {
      if (gateInput()) return;
      endTargeting();
      cue("drop");
      actMutate(actionId);
    },
    [gateInput, endTargeting, actMutate, cue],
  );

  // ---------------------------------------------------------------- derived

  /** Cards in hand the server says can be played right now. */
  const playableOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of actions) {
      if (
        action.source_oid !== null &&
        (action.kind === "cast" || action.kind === "play_land")
      ) {
        set.add(action.source_oid);
      }
    }
    return set;
  }, [actions]);

  /**
   * Permanents offering an activated ability right now.
   *
   * The same predicate `onBoardCard` already uses to route a click; this only
   * draws the affordance for it. The action itself stays in the action bar, so
   * the rune adds no `data-action-id` and cannot duplicate one.
   *
   * Note this is only the *available* state. The server can express an ability
   * it is offering but not one you cannot afford -- `unplayable_reason` covers
   * hand cards alone -- so there is deliberately no greyed-out variant.
   */
  const abilityOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of actions) {
      if (action.kind === "activate" && action.source_oid !== null) set.add(action.source_oid);
    }
    return set;
  }, [actions]);

  /** What the popover says a permanent offers, by source oid. */
  const abilityLabels = useMemo(() => {
    // `base_label`, not `label`: the engine offers one action per legal
    // target, so `label` here would name whichever target happened to be
    // first and read as a promise the popover cannot keep.
    const byOid = new Map<number, Set<string>>();
    for (const action of actions) {
      if (action.kind !== "activate" || action.source_oid === null) continue;
      const seen = byOid.get(action.source_oid) ?? new Set<string>();
      seen.add(action.base_label);
      byOid.set(action.source_oid, seen);
    }
    // Naming the first of several was a promise the popover could not keep
    // either: a permanent with a mana ability and a sacrifice ability would
    // advertise only one of them. Count instead, and let the panel enumerate.
    return new Map(
      [...byOid].map(([oid, labels]) => [
        oid,
        labels.size === 1 ? [...labels][0] : `${labels.size} abilities`,
      ]),
    );
  }, [actions]);

  /** Every oid named by any legal action: never hide these inside a stack. */
  const actionableOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of actions) {
      if (action.source_oid !== null) set.add(action.source_oid);
      for (const ref of action.targets) {
        if (ref.kind === "object") set.add(ref.id);
      }
    }
    return set;
  }, [actions]);

  /** The actions the current selection is waiting to resolve to. */
  const targeting = useMemo(
    () => actions.filter((a) => targetingActionIds.includes(a.id)),
    [actions, targetingActionIds],
  );

  const targetableOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of targeting) {
      for (const ref of action.targets) {
        if (ref.kind === "object") set.add(ref.id);
      }
    }
    return set;
  }, [targeting]);

  const targetablePids = useMemo(() => {
    const set = new Set<number>();
    for (const action of targeting) {
      for (const ref of action.targets) {
        if (ref.kind === "player") set.add(ref.id);
      }
    }
    // During attacker declaration, opponents are always pointable.
    if (decisionKind === "declare_attackers" && selectedOid !== null) {
      for (const action of actions) {
        if (action.kind === "add_attacker" && action.source_oid === selectedOid) {
          for (const ref of action.targets) {
            if (ref.kind === "player") set.add(ref.id);
          }
        }
      }
    }
    return set;
  }, [targeting, decisionKind, selectedOid, actions]);

  /**
   * The target question is settled and only the *variant* question is left.
   *
   * True when every action still in the running names the same targets — so
   * clicking the board again cannot narrow anything, and what remains is
   * "kicked or not", which only the panel can ask. Also true for a selection
   * of untargeted variants, where there was never a target to pick.
   */
  const targetChosen = useMemo(() => {
    if (targeting.length < 2) return false;
    const signature = (a: (typeof targeting)[number]) =>
      a.targets.map((ref) => `${ref.kind}:${ref.id}`).join(",");
    const first = signature(targeting[0]);
    return targeting.every((a) => signature(a) === first);
  }, [targeting]);

  /** Creatures that may still be declared, for the amber "click me" rim. */
  const combatCandidates = useMemo(() => {
    if (!inCombatDecision) return new Set<number>();
    if (decisionKind === "declare_attackers") return new Set(availableAttackers(actions));
    return new Set(
      actions
        .filter((a) => a.kind === "add_blocker")
        .map((a) => a.source_oid)
        .filter((oid): oid is number => oid !== null),
    );
  }, [inCombatDecision, decisionKind, actions]);

  /** Opponents' attackers that something of ours is staged to block. */
  const blockedAttackers = useMemo(() => new Set(Object.values(stagedBlocks)), [stagedBlocks]);

  /**
   * The lands a hovered card would tap, straight from the engine's solver.
   *
   * The mana row could say what you have but not what a play would leave you
   * with, which is the interesting question in a turn with two plays in it.
   * Nothing is computed here: `pays` is the payment `solve_payment` actually
   * found, so this cannot disagree with what casting the spell will really do.
   */
  const spending = useMemo(
    () => (hoveredOid === null ? new Set<number>() : sourcesSpentBy(actions, hoveredOid)),
    [hoveredOid, actions],
  );

  /** Lanes that would accept a drop of the selected hand card. */
  const activeLanes = useMemo(() => {
    const set = new Set<string>();
    if (selectedOid === null) return set;
    for (const lane of LANES) {
      if (canDropOnLane(state, actions, selectedOid, lane)) {
        set.add(`${state.seat}:${lane}`);
      }
    }
    return set;
  }, [selectedOid, state, actions]);

  // ------------------------------------------------------------ interaction

  /** Play a card from hand: straight through if unambiguous, else start targeting. */
  const playFromHand = useCallback(
    (card: CardView) => {
      if (gateInput()) return;
      const candidates = actionsForCard(actions, card.oid);
      if (candidates.length === 0) return;
      if (candidates.length === 1 && candidates[0].targets.length === 0) {
        act(candidates[0].id);
        return;
      }
      beginTargeting(
        card.oid,
        candidates.map((a) => a.id),
      );
    },
    [gateInput, actions, act, beginTargeting],
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
          select(selectedOid === card.oid ? null : card.oid);
          return;
        }
        if (selectedOid !== null && blockableBy(actions, selectedOid).includes(card.oid)) {
          stageBlock(selectedOid, card.oid);
          select(null);
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

      // 4. Otherwise: an activated ability with no choice to make.
      const own = actions.filter((a) => a.source_oid === card.oid && a.kind === "activate");
      if (own.length === 1 && own[0].targets.length === 0) {
        act(own[0].id);
        return;
      }
      if (own.length > 0) {
        // Several abilities, none of them targeted -- a Mind Stone offering
        // "{T}: Add {C}" beside its sacrifice ability. There is nothing on the
        // board to point at, so entering targeting mode would leave the player
        // hunting for a target that does not exist. Select it instead and let
        // the panel be the chooser: it lists every play action, not only the
        // narrowed ones, so both rows are already there.
        if (own.every((a) => a.targets.length === 0)) {
          select(selectedOid === card.oid ? null : card.oid);
          return;
        }
        beginTargeting(
          card.oid,
          own.map((a) => a.id),
        );
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
    ],
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

  /*
   * Whose board is actually on screen, guarded.
   *
   * A seat can leave the game while you are standing at it, and a latched pid
   * that no longer names a live player would draw an empty mat with no way back
   * -- so the guard is here rather than at the press, where it would only have
   * been true at the moment of pressing.
   */
  const viewing =
    viewingPid !== null &&
    viewingPid !== state.seat &&
    state.players[viewingPid] &&
    !state.players[viewingPid].has_lost
      ? viewingPid
      : null;

  // A new game, or leaving the table, must not arrive with somebody else's
  // board up. The store outlives the component.
  useEffect(() => () => setViewing(null), [setViewing]);

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
    ],
  );

  // ------------------------------------------------------------ controller

  /**
   * B: a strict unwind, and it never quits from the top.
   *
   * The order is the order things were put on top of each other, so pressing B
   * repeatedly always ends at the board rather than at a dialog you cannot
   * remember opening. Quitting is a deliberate act in the tool strip -- a back
   * button that eventually leaves the game is how somebody loses a match.
   */
  const back = useCallback(() => {
    /*
     * One level per press, outermost first, and each level says so.
     *
     * The voice is not decoration: `B` at the bottom of the stack does nothing
     * at all, and without a sound the player cannot tell "nothing was open"
     * from "the button did not register" -- which on a controller is the
     * difference between trusting the input and hammering it.
     */
    const unwind = () => {
      // The two holds are outermost: both cover the board, and both are things
      // you opened a moment ago and can put down without losing anything.
      if (dialOpen) {
        setDialOpen(false);
        return true;
      }
      if (heldCard !== null) {
        setHeldCard(null);
        return true;
      }
      // The log overlay is the outermost thing that can be open, and it traps
      // the ring while it is. A panel you can open with one button and cannot
      // close with the button that means "back" is worse than no panel: the
      // ring is inside it and every direction is a wall.
      //
      // Not gated on the layout any more: the log is an overlay at every size
      // now that the left rail is retired, so `B` has to close it everywhere.
      if (logOverlay) {
        toggleLogOverlay();
        return true;
      }
      if (peek) {
        setPeek(null);
        return true;
      }
      // Below the overlays and above targeting: standing at somebody else's
      // seat is a place you are, not a thing that is open over you, so `B`
      // brings you home only once nothing is covering the board.
      if (viewing !== null) {
        setViewing(null);
        return true;
      }
      if (targetingActionIds.length > 0) {
        endTargeting();
        return true;
      }
      if (selectedOid !== null) {
        select(null);
        return true;
      }
      return false;
    };
    if (unwind()) cue("back");
  }, [
    dialOpen,
    heldCard,
    logOverlay,
    toggleLogOverlay,
    peek,
    setPeek,
    viewing,
    setViewing,
    targetingActionIds,
    endTargeting,
    selectedOid,
    select,
    cue,
  ]);

  /**
   * X: the secondary verb, which is context's business rather than a fixed one.
   *
   * On a staged attacker it re-aims -- the pod case, where `defendersFor` has
   * several seats and the mouse re-aims by clicking a different orb. Elsewhere
   * it activates an ability on a card whose primary press casts it.
   */
  const secondary = useCallback(() => {
    const ref = parseStop(getCursor());
    if (ref.kind !== "card" || ref.id === null) return;
    const oid = ref.id;
    if (decisionKind === "declare_attackers" && stagedAttacks[oid] !== undefined) {
      const defenders = defendersFor(actions, oid);
      if (defenders.length < 2) return;
      const next = defenders[(defenders.indexOf(stagedAttacks[oid]) + 1) % defenders.length];
      stageAttack(oid, next);
      return;
    }
    const ability = actions.find((a) => a.source_oid === oid && a.kind === "activate");
    if (ability) onBarAct(ability.id);
  }, [decisionKind, stagedAttacks, actions, stageAttack, onBarAct]);

  /**
   * Which opponent is being read, while `R2` is held.
   *
   * A hold rather than a toggle: a toggle needs a second press to put away and
   * leaves the board covered if you forget, whereas letting go is not something
   * you can forget to do. `onFrame` because a trigger is analog and has no
   * press event -- 0.5 is past any resting value and well short of the click.
   *
   * The seat is whichever one the ring is on, falling back to the first
   * opponent, so "look at them" needs no separate act of choosing.
   */
  const [reading, setReading] = useState<number | null>(null);
  const readingRef = useRef<number | null>(null);
  readingRef.current = reading;

  useEffect(() => {
    if (!handheld) return;
    return onPadFrame((frame) => {
      const held = frame.r2 > 0.5;
      if (!held) {
        if (readingRef.current !== null) setReading(null);
        return;
      }
      if (readingRef.current !== null) return;
      const ref = parseStop(getCursor());
      const onSeat = ref.kind === "orb" && ref.id !== null && ref.id !== state.seat;
      setReading(onSeat ? ref.id : (opponents[0] ?? null));
    });
  }, [handheld, opponents, state.seat]);

  /*
   * A staged attacker leans toward the seat it is aimed at, and holds.
   *
   * The amber rim says "selected"; the lean says "aimed at *them*", which in a
   * pod is a different fact and the one that matters -- three creatures staged
   * at three different players look identical under a rim alone.
   *
   * Driven from an effect rather than from the click handler because staging
   * has four entry points (the card, the panel row, the defender chip, and
   * undo), and one of them is the server sending a state where nothing is
   * staged any more. Reconciling from the current staging covers all four.
   */
  useEffect(() => {
    const staged = Object.entries(stagedAttacks);
    if (staged.length === 0) return;
    const board = boardRef.current?.getBoundingClientRect();
    if (!board) return;
    for (const [oid, defender] of staged) {
      const seat = document.querySelector(`[data-player="${defender}"]`);
      if (!seat) continue;
      const box = seat.getBoundingClientRect();
      drive(Number(oid))?.lean({
        x: box.left + box.width / 2 - board.left,
        y: box.top + box.height / 2 - board.top,
      });
    }
    // Released on unstage, on commit, and on unmount -- `rest` is the same
    // cancel path every transient uses, so the hold needs no special teardown.
    return () => {
      for (const [oid] of staged) drive(Number(oid))?.rest();
    };
  }, [stagedAttacks]);

  /*
   * The cursor re-derives after every commit *this* component makes.
   *
   * `Screen` mounts the ring itself, but React only runs layout effects for
   * components that re-render -- and the board re-renders on every engine push
   * without its wrapper doing so. Without this the ring would go out the first
   * time a card it was sitting on left play and never come back, because
   * navigation starts from `[data-cursor]`.
   */
  useCursorResolve();

  /*
   * ...and the context, which decides whether the ring flies or teleports. A
   * dialog opening is a new context: springing 600px from a board card to a
   * modal button is a spring between two things that were never on screen
   * together, which reads as a glitch rather than as movement.
   */
  useEffect(() => {
    setCursorContext(`game|${peek?.zone ?? ""}|${state.pending?.kind ?? ""}`);
  }, [peek?.zone, state.pending?.kind]);

  /* ------------------------------------------------------------- regions
   *
   * `L1`/`R1` step between the board's five regions and trap the ring inside
   * the one it is in, because directional navigation crosses a 96px seat strip,
   * three lanes, a fanned hand and a 243px rail one card at a time.
   * `HintBar` has advertised `L1 Zone` since it was written and nothing has
   * ever been bound to it. See `input/groups.ts`.
   */

  /** Enter a region, landing where the ring was when it last left. */
  const enterGroup = useCallback((id: GroupId | null) => {
    if (id === null) {
      setGroup(null);
      return;
    }
    const here = getGroup();
    const cursor = getCursor();
    // Leaving: note where we were, so coming back is a jump and not a reset.
    if (here && cursor) rememberStop(here, cursor);

    setGroup(id);
    const root = groupRoot(id);
    if (!root) return;
    /*
     * LANDABLE, not merely present.
     *
     * This took the first `[data-stop]` in document order, which is a different
     * question from the one `groupsPresent` asks to decide the region is worth
     * entering at all: on a handheld an opponent's cards are clipped to zero
     * height and still in the document, so the first stop in a region can be
     * one nobody can see while the region genuinely has others. One helper now
     * answers both.
     */
    const stops = landableStopsIn(root);
    const wanted = rememberedStop(id);
    // The remembered stop only if it is still there and still visible -- a card
    // can have left play since, and a stop id that names nothing puts the ring
    // nowhere.
    const remembered = stops.some((el) => el.dataset.stop === wanted) ? wanted : undefined;
    const target = remembered ?? stops[0]?.dataset.stop;
    if (target) setCursor(target);
  }, []);

  const stepGroup = useCallback(
    (step: 1 | -1) => {
      const next = nextGroup(getGroup(), step);
      if (next === null) {
        cue("deny");
        return;
      }
      enterGroup(next);
    },
    [enterGroup, cue],
  );

  /*
   * The dial, on `L2` HELD.
   *
   * Not on a hold of `L1`, which is where this started and could not work:
   * `pad.ts` reports PRESSES and has no release event for a shoulder, so a
   * "hold" there is a timer with nothing to cancel it -- a tap would open the
   * dial 260ms later, having already stepped.
   *
   * `L2` is a TRIGGER, and `onFrame` reports its analog position every frame.
   * That is the same channel the `R2` opponent reader is held on, for the same
   * stated reason: letting go is not something you can forget to do. 0.5 is
   * past any resting value and well short of the click.
   *
   * A tap of `L2` still jumps the ring to the tool strip, because the frame
   * threshold is crossed and released before the dial has anything to pick
   * from -- see the `l2` binding below.
   */
  const l2Held = useRef(false);
  useEffect(() => {
    return onPadFrame((frame) => {
      const held = frame.l2 > 0.5;
      /*
       * ON THE TRIGGER'S EDGE, NOT ON ITS LEVEL.
       *
       * This wrote `dialOpen = held` every frame, which is correct while `L2` is
       * the only thing that opens the dial and wrong the moment anything else
       * does: the button in the foot would set it true, the very next frame
       * would read a resting trigger and set it straight back to false, and the
       * dial would appear not to open at all. A press and a release are events;
       * a trigger at rest is not one.
       */
      if (held === l2Held.current) return;
      l2Held.current = held;
      setDialOpen(held);
    });
  }, []);

  /*
   * The ring keeps its own group in step with where it actually is.
   *
   * The player can leave a region without pressing a shoulder: the pointer
   * snaps the ring anywhere, `A` on a card can open a dialog, and a decision
   * can move it. Reconciling from the cursor means the trap is always about
   * where the ring IS rather than about where it was last sent.
   */
  useEffect(() => {
    return subscribeCursor(() => {
      const stop = getCursor();
      if (!stop) return;
      const el = stopElement(stop, document.querySelector<HTMLElement>(".table") ?? undefined);
      if (!el) return;
      const found = groupOf(el);
      if (found && found !== getGroup()) setGroup(found);
    });
  }, []);

  // A new game must not inherit the last one's region or its remembered stops.
  useEffect(() => () => resetGroups(), []);

  /*
   * Where the decision is, when the decision changes.
   *
   * Keyed on the pending kind and the step ONLY. Run on every render this would
   * drag the ring back each time the engine pushed a state -- several times a
   * second while an AI plays -- and a ring that returns to where the app thinks
   * you should be is worse than one that stays where you put it.
   */
  const modalOwns = modalOwnsDecision;

  /*
   * ONCE PER DECISION, and a ref rather than a dependency list is what makes it
   * once.
   *
   * The first version keyed the effect on the pending kind, the step AND
   * `narration.busy` -- and `busy` flips true then false after every action a
   * player takes. Casting a spell in your main phase changes neither the step
   * nor the pending kind, so the first two are stable and the third re-fired
   * the effect on its own: go and read something on the board, cast, and the
   * ring is yanked back to your hand. That is exactly the "returns to where the
   * app thinks you should be" failure the note above is about, arriving through
   * the dependency list rather than through the rule.
   *
   * So the KEY is the decision, the ref remembers which key was last acted on,
   * and narration only decides *when* -- never *whether*.
   */
  const focusedFor = useRef<string | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: the narrow key is the point; see above.
  useEffect(() => {
    const key = `${state.pending?.kind ?? ""}|${state.step}`;
    if (focusedFor.current === key) return;
    // Wait for the board to stop moving, but do not treat waiting as done: the
    // key is still unclaimed, so the next run after narration settles takes it.
    if (narration.busy) return;
    focusedFor.current = key;
    const wanted = groupForDecision(state, actions, modalOwns);
    if (wanted && wanted !== getGroup()) enterGroup(wanted);
  }, [state.pending?.kind, state.step, narration.busy]);

  useEffect(() => {
    const unbind = [
      onPad("b", back),
      onPad("x", secondary),
      /*
       * A tap steps, a hold opens the dial.
       *
       * `pad.ts` reports a press and this app has no release event, so the hold
       * is a timer started on the press and cancelled by the next press of
       * anything -- which `onAnyPad` below does. A tap therefore steps
       * immediately AND arms a timer that the tap itself cancels; a hold leaves
       * the timer to fire.
       */
      onPad("l1", () => stepGroup(-1)),
      onPad("r1", () => stepGroup(1)),
      /*
       * `Y` reads the card the ring is on, full screen.
       *
       * `logic/verbs.ts` has returned `Y Read` on every card stop since it was
       * written and nothing was ever bound to it. An advertised button that
       * does nothing is worse than an unadvertised one: it teaches the player
       * that the hint bar is not to be trusted.
       */
      onPad("y", () => {
        const ref = parseStop(getCursor());
        if (ref.kind === "card" && ref.id !== null) {
          setHeldCard(ref.id);
          return;
        }
        /*
         * On a SEAT, `Read` means their commander.
         *
         * `verbsFor` returns `Y Read` for an orb stop as well as for a card,
         * and a bar that promises a verb the button does not have is the exact
         * defect this whole binding exists to close -- so the seat answers the
         * only question it could be asking. In Commander the deck IS the
         * commander, and a seat you are deciding whether to attack is one whose
         * commander's text you want.
         */
        if (ref.kind === "orb" && ref.id !== null) {
          const commander = commandersOf(state, ref.id)[0];
          if (commander) {
            setHeldCard(commander.oid);
            return;
          }
        }
        cue("deny");
      }),
      // `View` is the log and `Menu` jumps the ring to the tool strip. Neither
      // renders a control of its own: they flip a flag an existing surface
      // already reads, or move the ring to a button that already exists. That
      // is what keeps `data-action-id` and `data-testid` unique for free.
      onPad("view", toggleLogOverlay),
      // The strip's first stop, which is the settings menu now that sound, undo
      // and quit live inside it. It was `tool:mute`, and a stop that only
      // exists while a menu is open is a jump that does nothing four times out
      // of five.
      onPad("menu", () => {
        setCursor(stopId.tool("settings"));
      }),
      /*
       * `L2` was advertised by the hint bar and bound to nothing -- `Menu` was
       * what actually jumped the ring to the tool strip. It does two things now
       * and they do not collide: a PRESS jumps to the tools, and HOLDING it
       * opens the region dial (the `onPadFrame` above). A tap crosses and
       * releases the analog threshold inside a frame or two, which is over
       * before the dial is worth looking at.
       */
      onPad("l2", () => {
        setCursor(stopId.tool("settings"));
      }),
      /*
       * Any press ends a hold and puts a held card down.
       *
       * `pad.ts` reports presses and has no release event, so "held" here means
       * "until you do something else" -- which is how it behaves in practice
       * anyway, because the thing you do next is the thing you were reading the
       * card in order to decide.
       */
      onAnyPad((button) => {
        if (narration.busy) skipAll();
        if (button !== "y" && heldCard !== null) setHeldCard(null);
      }),
    ];
    return () => {
      for (const off of unbind) off();
    };
  }, [
    back,
    secondary,
    toggleLogOverlay,
    narration.busy,
    skipAll,
    stepGroup,
    heldCard,
    cue,
    state,
  ]);

  // ------------------------------------------------------------- keyboard

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

      /*
       * `Escape` is handled as the pad's `B` rather than here.
       *
       * It used to cancel targeting and close the zone viewer in one go. `B` is
       * a strict unwind instead -- peek, then targeting, then selection -- which
       * is the behaviour a back button needs in order to be predictable, and
       * which is now the same code whether the player pressed Escape,
       * Backspace, or B on a controller. One button, one implementation.
       */
      if (narration.busy && event.key !== "Escape") {
        skipAll();
        return;
      }
      /*
       * Zone peeking. `Esc` closed it and nothing opened it, so the only route
       * in was a chip on the orb. Placed before `gateInput` on purpose: looking
       * at your own graveyard asks the server nothing, so there is no reason to
       * refuse it while a request is in flight.
       */
      const peekZone = PEEK_KEYS[event.key.toLowerCase()];
      if (peekZone) {
        setPeek(peek?.zone === peekZone ? null : { pid: state.seat, zone: peekZone });
        return;
      }

      if (gateInput()) return;

      if (event.key === " ") {
        const pass = actions.find((a) => a.kind === "pass");
        if (pass) {
          event.preventDefault();
          act(pass.id);
        }
        return;
      }
      /*
       * `Enter` is deliberately not handled here any more.
       *
       * It is bound to the pad's `A`, which presses whatever the ring is on --
       * and the ring rests on the commit slab whenever a decision is pending,
       * so the same keystroke still confirms. Keeping this branch as well made
       * one press post two actions: this one took the first `keep`/`yes`/
       * `finish_declaration` in the list while `confirm()` posted the button
       * under the ring.
       *
       * It is also strictly better than what it replaced. The old branch could
       * only ever confirm those three kinds; `A` presses the control the player
       * is actually looking at, which is every kind.
       */
      if (event.key.toLowerCase() === "u") {
        undoMutate();
        return;
      }
      if (/^[1-9]$/.test(event.key)) {
        const card = viewer.hand?.[Number(event.key) - 1];
        if (card) playFromHand(card);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    actions,
    act,
    gateInput,
    narration,
    skipAll,
    setPeek,
    playFromHand,
    viewer.hand,
    undoMutate,
    peek,
    state.seat,
  ]);

  // ---------------------------------------------------------------- render

  /*
   * How big the cards are, solved against the room they actually have.
   *
   * The three refs below are the only measurements taken, and `useZoomFit`
   * documents why each is safe to read -- the short version is that all three are
   * grid tracks whose size the cards inside cannot change. `opponentCardScale` and
   * `CARD_SCALE.own` / `.hand` are still here, but as the *ceilings* the solve may
   * not exceed rather than as the sizes; see `logic/cardSize.ts`.
   */
  const zoom = useZoomFit({
    state,
    actionableOids,
    opponents,
    handCount: viewer.hand?.length ?? 0,
    handheld,
    tableRef,
    mineRef,
    footRef,
    podRef,
  });

  return (
    <div
      className="table"
      data-testid="table"
      ref={tableRef}
      // Read by e2e rather than making it parse a resolved `calc()` off a lane, and
      // handy for eyeballing the solve in devtools. Same spirit as
      // `data-stack-count` on a stack.
      data-zoom-board={zoom.board.toFixed(3)}
      data-zoom-pod={zoom.pod.toFixed(3)}
      data-zoom-hand={zoom.hand.toFixed(3)}
      data-zoom-locked={zoom.locked || undefined}
      data-handheld={handheld || undefined}
      /*
        The box an opponent's lanes were solved inside, handed back to CSS.

        `theme.css` still declares `--pod-lanes-h` and it is still the floor;
        this only ever raises it, and only where the seat count says the room is
        going spare. Written here rather than on `.play` because the property is
        registered `inherits: true` and `.mat--compact` is several levels down.
        `null` on the pinned path leaves the stylesheet's clamp alone.
      */
      style={
        zoom.podLanesH === null
          ? undefined
          : ({ "--pod-lanes-h": `${Math.round(zoom.podLanesH)}px` } as React.CSSProperties)
      }
    >
      <PhaseTrack state={state} />

      {/*
        `data-fx-origin` marks the box every effect coordinate is relative to.
        `FxLayer` and `CombatArrows` already resolve it through `boardRef`, but a
        card actuator is reached from a module function with no props and no
        context, so it finds this by walking up from the card itself.
      */}
      <motion.div
        className="table__body"
        ref={boardRef}
        data-fx-origin
        style={{ x: shakeX, y: shakeY }}
      >
        {/*
          THE STACK FLOATS OVER THE BOARD, and the left rail is gone.

          It held two things. The log is reference you consult rather than
          watch, so it is an overlay on `View` -- which is what a handheld
          already did, and there was never an argument for a desktop keeping a
          232px column permanently open for it. The stack is the other, and it
          is urgent exactly when it is non-empty and absent the rest of the
          time, which is the shape of a thing that should not own a column at
          all.

          So it is a pile of real card faces over the top-left of the play area,
          growing down over the viewer's own panel as it deepens. `StackPanel`
          already drew exactly this -- plies at a 26px offset, each peeking out
          by its own name strip -- it simply drew it inside a rail.

          What the retired column buys is 232px of board at every size, which is
          most of what the foot costs by moving inside this column so the right
          rail can run to the bottom edge.
        */}
        <main className="play">
          {/*
            Inside `.play` and not the body, so it floats over the VIEWER'S own
            area rather than over the opponents.

            Anchored to the body's top-left it covered an opponent's name and
            life on a desktop, where their row is 250px tall -- and covering
            somebody's vitals is a worse trade than covering your own commander.
            It is placed into the same grid cell as `.play__mine`, which two
            grid items are allowed to share, so it overlaps without needing a
            positioned ancestor and without `.play__mine`'s own scrolling
            carrying it off the top.
          */}
          {state.stack.length > 0 && <StackPanel state={state} />}

          <div className="play__opponents" ref={podRef}>
            {opponents.map((pid) => (
              <PlayerMat
                key={pid}
                state={state}
                player={state.players[pid]}
                compact
                // Their lands against their own edge of the screen, so the two
                // creature bands meet across the middle of the table.
                mirrored
                cardScale={zoom.pod}
                actionableOids={actionableOids}
                hasAbility={(card) => abilityOids.has(card.oid)}
                abilityLabel={(card) => abilityLabels.get(card.oid) ?? null}
                isTargetable={(card) => targetableOids.has(card.oid)}
                // stagedBlocks is keyed by blocker; an opponent's attacker is a
                // value in that map, never a key.
                isStaged={(card) => blockedAttackers.has(card.oid)}
                isSelected={(card) => card.oid === selectedOid}
                onActivate={onBoardCard}
                playerTargetable={targetablePids.has(pid)}
                onSelectPlayer={onSelectPlayer}
                // An opponent's commander is reference, never a click target:
                // `playableOids` only ever names the viewer's own cards.
                playableOids={playableOids}
                onHoverCard={hover}
                locked={locked}
                viewing={viewing === pid}
                // Their board has moved into the viewer's area, so this mat
                // stops drawing it. Clipped is not absent: a card in a
                // zero-height lane still owns its `data-oid`.
                variant={viewing === pid ? "side" : "full"}
              />
            ))}
          </div>

          <div className="play__mine" ref={mineRef} data-viewing={viewing ?? undefined}>
            {/*
              WHOSE BOARD IS THIS, when it is not yours.

              A strip and not a toast: it has to be true for as long as you are
              standing there, and it has to say the way back. It carries a
              `data-stop` so the ring can reach it, and NO `data-action-id` --
              coming home is not a move in the game, and `ActionPanel` owns
              every id alone.
            */}
            {viewing !== null && (
              <div className="viewing" data-testid="viewing-strip">
                <span className="viewing__who">
                  Viewing <b>{state.players[viewing]?.name ?? `Player ${viewing}`}</b>
                </span>
                <button
                  type="button"
                  className="btn btn--ghost"
                  data-stop={stopId.tool("stop-viewing")}
                  onClick={() => setViewing(null)}
                >
                  Back to your board
                </button>
              </div>
            )}

            {/*
              THE NODE MOVES; IT IS NEVER COPIED.

              Whichever mat is drawn here is the only place that player's cards
              are laid out, because the seat swap renders `variant="lanes"` and
              the mats in the row above draw no lanes on a handheld anyway. Two
              boxes for one `data-oid` would give `FxLayer` and the ring a
              choice they have no way to make correctly.

              `variant="lanes"` also means no second `PlayerOrb`: the facts
              about the seat you are standing at are on that seat, six pixels
              above, and drawing them twice would put two `data-player`s in the
              document.
            */}
            {/*
              Your own panel stays, whosever board is beside it.

              Life, open mana and commander damage are most of what you are
              assessing a threat AGAINST, so leaving to look at somebody's board
              must not take them off the screen. Rendered as its own mat rather
              than as a half of theirs: a `PlayerMat` is one player's, and a
              component that took two and decided which half belonged to which
              would be a worse thing to have than a grid line.
            */}
            {viewing !== null && (
              <PlayerMat
                key={`mine-${state.seat}`}
                variant="side"
                state={state}
                player={viewer}
                cardScale={zoom.board}
                actionableOids={actionableOids}
                playerTargetable={targetablePids.has(state.seat)}
                onSelectPlayer={onSelectPlayer}
                playableOids={playableOids}
                onHoverCard={hover}
                spending={spending}
                locked={locked}
              />
            )}

            <PlayerMat
              key={viewing ?? state.seat}
              variant={viewing !== null ? "lanes" : "full"}
              state={state}
              player={viewing !== null ? state.players[viewing] : viewer}
              cardScale={zoom.board}
              actionableOids={actionableOids}
              hasAbility={(card) => abilityOids.has(card.oid)}
              abilityLabel={(card) => abilityLabels.get(card.oid) ?? null}
              activeLanes={activeLanes}
              isPlayable={(card) => combatCandidates.has(card.oid)}
              isTargetable={(card) => targetableOids.has(card.oid)}
              isStaged={(card) =>
                stagedAttacks[card.oid] !== undefined || stagedBlocks[card.oid] !== undefined
              }
              isSelected={(card) => card.oid === selectedOid}
              onActivate={onBoardCard}
              playerTargetable={targetablePids.has(state.seat)}
              onSelectPlayer={onSelectPlayer}
              playableOids={playableOids}
              // Casting your commander out of the plinth in the info panel.
              // The same route a hand card takes, so targeting and the real
              // action post identically.
              onCastCommander={playFromHand}
              onHoverCard={hover}
              spending={spending}
              // Standing at somebody else's seat is a reader, not a second way
              // to act: every legal action against those permanents is already
              // a row in the panel, and offering them here would put the same
              // `data-action-id` in the document twice.
              locked={locked || viewing !== null}
            />
          </div>
        </main>

        {/*
          The right rail is three things: the card you are reading, the panel of
          things you can do about it, and the commit slab. Nothing else.

          All of it used to live across the foot -- the action bar took a fixed
          420px out of the row the hand wanted, and combat was a full-width
          banner under the board, which put the decision as far as possible from
          the cards it was about. Here the creature you are reading and the list
          you are staging it into are one glance apart, and the foot belongs to
          the hand alone.
        */}
        <aside className="rail rail--right">
          <CardPreview state={state} />
          <ActionPanel
            state={state}
            actions={actions}
            onAct={act}
            onStage={onBarAct}
            onDeclare={onDeclare}
            onUndo={() => undoMutate()}
            onQuit={onQuit}
            onToggleFullControl={(value) => fullControlMutate(value)}
            onToggleManualMana={(value) => manualManaMutate(value)}
            narrating={narration.busy}
            onSkipNarration={skipAll}
            busy={busy}
            aiThinking={aiThinking}
            standDown={modalOwnsDecision}
          />
        </aside>

        {/*
          THE FOOT IS INSIDE THE BODY NOW, and that is the round's biggest
          single change.

          It used to be a sibling, spanning the full width under both rails, so
          the right rail stopped where the hand started -- 514px at 1280x800,
          of which the rows the turn is actually spent in got 172.
          `mockups/handheld-board/` measures the same rail at 748px when it runs
          to the foot instead, and the action list at 363-398.

          It also fixes something quietly: `data-fx-origin` is on this element,
          and with the foot outside it every card flying from the hand to the
          board crossed the origin's boundary. Every such flight is interior now.
        */}
        <div className="table__foot" ref={footRef}>
          {/*
          Where the tool strip goes on a handheld. A host, not the controls
          themselves.

          What goes in it depends on `ActionPanel`'s own decision state, so
          rebuilding it here would be a second implementation of controls the
          turn is waiting on. `ActionPanel` finds this by class and portals its
          real tool row into it, so there is exactly one in the document and
          every `data-action-id`, `data-testid` and ring stop travels with it.

          THE COMMIT SLAB USED TO HAVE A HOST HERE TOO. It does not need one any
          more: the rail runs the full height of the screen, so the 65px the
          slab costs is affordable there -- and under the list it commits is
          where it belongs, rather than in the corner beside the hand.

          Rendered only on a handheld. On a desktop the tools stay in the rail,
          where 304px of width and a 950px-tall screen make them the right
          shape; here the foot's row is 1017px and they are one line rather than
          the three a 200px column wrapped them to.
        */}
          {handheld && <div className="foot__tools" />}

          {/*
          THE DIAL NEEDED A BUTTON, because holding `L2` was the only way in.

          A Steam Deck in gaming mode hands the page a keyboard rather than a
          gamepad, so `L2` -- and `z`, its keyboard stand-in -- arrive as nothing
          at all. The region dial was therefore unreachable on the one device it
          was designed for. The ring can now walk out of a region at its edge
          (`input/stops.ts:escapeGroup`), so this is a shortcut rather than the
          only road, but a jump the hint bar advertises should have a surface.

          A `tool:` stop and no `data-action-id`: it flips a flag on a surface
          that already exists, which is what keeps the panel's "every legal
          action is a button, exactly once" invariant free.
        */}
          <button
            type="button"
            className="foot__regions"
            onClick={() => setDialOpen(true)}
            aria-label="Jump to a region"
            data-stop={stopId.tool("regions")}
            data-testid="regions"
            data-hint="Jump to a region of the board"
          >
            <Glyph btn="l2" />
            Regions
          </button>

          {/*
          What the buttons do, for whoever is holding one.

          `display: none` unless `html[data-input]` says a pad or a keyboard is
          driving, so a mouse player's foot is exactly the row it has always
          been -- no extra height, no reserved space, nothing to read. See
          `components/ui/Glyph.tsx`.
        */}
          <HintBar state={state} actions={actions} />

          {/*
          One hint, never a second copy of the actions.

          This used to be two blocks, and the first rendered every remaining
          action as a `data-action-id` button -- the same ids `ActionPanel`
          renders from `playRows`, which does *not* stand down for targeting.
          Two controls, one id: exactly what the panel's invariant forbids. It
          escaped CI only because no shipped card could reach it, and manual
          mana (Stage 2) reaches it immediately. The panel owns the choice; the
          foot only ever says what the click is for.
        */}
          {targeting.length > 0 && (
            <div
              className="choices"
              data-testid={targetChosen ? "variant-hint" : "targeting-hint"}
            >
              <span className="choices__label">
                {targetChosen ? "Pick how, in the panel" : "Pick a target"}
              </span>
              <button type="button" className="btn btn--ghost" onClick={endTargeting}>
                Cancel (Esc)
              </button>
            </div>
          )}

          {/*
          The hand owns the foot outright.

          The commander used to sit to its left, on the theory that a zone you
          play from belongs beside the other zone you play from. In practice it
          put the format's defining card in the corner where nothing important
          goes, at a size where its own name did not fit. It is the hero of the
          player's info panel now -- see `CommandZone` and `PlayerOrb` -- and it
          still casts by the same click on the same `playFromHand` path.
        */}
          <HandFan
            cards={viewer.hand ?? []}
            playableOids={playableOids}
            reasons={viewer.hand_reasons ?? {}}
            mana={viewer.mana}
            selectedOid={selectedOid}
            cardScale={zoom.hand}
            fanWidth={zoom.fanW}
            onActivate={playFromHand}
            onDropOn={onDropOnZone}
            // Your lanes are not on screen while you are reading somebody
            // else's, so there is nowhere legal to drop.
            disabled={locked || viewing !== null}
          />
        </div>

        <CombatArrows state={state} boardRef={boardRef} />
        <ParticleLayer boardRef={boardRef} />
        <FxLayer beat={narration.current} speed={speed} boardRef={boardRef} state={state} />
      </motion.div>

      {error && (
        <motion.div
          className="toast toast--error"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          data-testid="error-toast"
        >
          {error}
          <button type="button" className="toast__close" onClick={() => setError(null)}>
            ×
          </button>
        </motion.div>
      )}

      {stalled && (
        <div className="toast toast--warn" data-testid="stall-toast">
          The game stopped progressing. Try Undo, or start a new game.
        </div>
      )}

      {handheld && <OpponentBoard state={state} pid={reading} />}

      {/*
        The two holds.

        `AnimatePresence` on neither: both are gone the instant you press
        anything else, and an exit animation on a thing you dismissed by acting
        would still be fading while the action it was covering resolved.
      */}
      <CardHold card={heldCard === null ? null : findCard(state, heldCard)} />

      {dialOpen && (
        <GroupDial
          current={getGroup()}
          onPick={(id) => {
            setDialOpen(false);
            enterGroup(id);
          }}
        />
      )}

      {logOverlay && (
        <div className="logover" data-modal-root data-testid="log-overlay">
          <div className="logover__head">
            <span>Log</span>
            <button
              type="button"
              className="btn btn--ghost"
              data-stop={stopId.tool("close-log")}
              onClick={toggleLogOverlay}
            >
              Close
            </button>
          </div>
          <EventTicker state={state} events={events} cardName={game.cardName} />
        </div>
      )}

      <PromptDialog state={state} actions={actions} onAct={act} disabled={locked} />
      <ZonePeek state={state} reasons={removals} />
      <GameOverScreen state={state} onRematch={onRematch} onQuit={onQuit} />
    </div>
  );
}
