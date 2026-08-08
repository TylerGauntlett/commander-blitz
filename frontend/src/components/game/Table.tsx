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
import { useCallback, useEffect, useMemo, useRef } from "react";
import type { CardView, GameView } from "../../api/types";
import {
  actionsForCard,
  availableAttackers,
  blockableBy,
  canDropOnLane,
  defendersFor,
} from "../../logic/actionMatch";
import { CARD_SCALE, opponentCardScale } from "../../logic/cardSize";
import { sourcesSpentBy } from "../../logic/mana";
import type { Lane as LaneName } from "../../logic/zoneGrouping";
import { LANES, seatOrder } from "../../logic/zoneGrouping";
import { type PeekTarget, useUiStore } from "../../state/uiStore";
import type { GameSession, useGame } from "../../state/useGame";
import { ActionPanel } from "./ActionPanel";
import { CardPreview } from "./CardPreview";
import { CombatArrows } from "./CombatArrows";
import { EventTicker } from "./EventTicker";
import { FxLayer, useScreenShake } from "./FxLayer";
import { GameOverScreen } from "./GameOverScreen";
import { HandFan } from "./HandFan";
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

  const speed = useUiStore((s) => s.speed);
  const selectedOid = useUiStore((s) => s.selectedOid);
  const targetingActionIds = useUiStore((s) => s.targetingActionIds);
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const beginTargeting = useUiStore((s) => s.beginTargeting);
  const endTargeting = useUiStore((s) => s.endTargeting);
  const select = useUiStore((s) => s.select);
  const stageAttack = useUiStore((s) => s.stageAttack);
  const unstageAttack = useUiStore((s) => s.unstageAttack);
  const stageBlock = useUiStore((s) => s.stageBlock);
  const unstageBlock = useUiStore((s) => s.unstageBlock);
  const setPeek = useUiStore((s) => s.setPeek);
  const peek = useUiStore((s) => s.peek);
  const hover = useUiStore((s) => s.hover);
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const error = useUiStore((s) => s.error);
  const setError = useUiStore((s) => s.setError);

  const shake = useScreenShake(narration.current);
  const viewer = state.players[state.seat];
  const names = useMemo(() => state.players.map((p) => p.name), [state.players]);
  const decisionKind = state.pending?.player === state.seat ? state.pending.kind : null;
  const inCombatDecision = decisionKind !== null && COMBAT_DECISIONS.has(decisionKind);
  const locked = busy || narration.busy;

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

  /**
   * Whether this gesture should be dropped, and the side effect of not dropping it.
   *
   * A click while narration is playing means "get on with it", exactly as a
   * keypress already does. Swallowing those clicks is what made the board feel
   * like it needed spamming: the input landed on nothing and said nothing.
   */
  const narrationBusy = narration.busy;
  const skipNarration = narration.skip;
  const gateInput = useCallback(() => {
    if (narrationBusy) {
      skipNarration();
      return true;
    }
    return busy;
  }, [busy, narrationBusy, skipNarration]);

  const act = useCallback(
    (actionId: string) => {
      if (gateInput()) return;
      endTargeting();
      actMutate(actionId);
    },
    [gateInput, endTargeting, actMutate],
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

  /** The first available ability's label, by source oid, for the popover. */
  const abilityLabels = useMemo(() => {
    const byOid = new Map<number, string>();
    for (const action of actions) {
      if (action.kind !== "activate" || action.source_oid === null) continue;
      if (!byOid.has(action.source_oid)) byOid.set(action.source_oid, action.label);
    }
    return byOid;
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

  const onDropOnZone = useCallback(
    (card: CardView, zone: string) => {
      if (gateInput()) return;
      const [kind, , lane] = zone.split(":");
      if (kind !== "lane") return;
      if (!canDropOnLane(state, actions, card.oid, lane as LaneName)) return;
      playFromHand(card);
    },
    [gateInput, state, actions, playFromHand],
  );

  /** Clicking a permanent: resolve a target, or stage it for combat. */
  const onBoardCard = useCallback(
    (card: CardView) => {
      if (gateInput()) return;

      // 1. Finishing a targeted spell.
      if (targeting.length > 0 && targetableOids.has(card.oid)) {
        const match = targeting.find((a) =>
          a.targets.some((ref) => ref.kind === "object" && ref.id === card.oid),
        );
        if (match) {
          act(match.id);
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
      // Finish a spell that targets a player.
      const match = targeting.find((a) =>
        a.targets.some((ref) => ref.kind === "player" && ref.id === pid),
      );
      if (match) act(match.id);
    },
    [gateInput, decisionKind, selectedOid, actions, stageAttack, targeting, act],
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

  // ------------------------------------------------------------- keyboard

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

      if (event.key === "Escape") {
        endTargeting();
        setPeek(null);
        return;
      }
      if (narration.busy && event.key !== "Escape") {
        narration.skip();
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
      if (event.key === "Enter") {
        const confirm = actions.find((a) =>
          ["keep", "yes", "finish_declaration"].includes(a.kind),
        );
        if (confirm) act(confirm.id);
        return;
      }
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
    endTargeting,
    setPeek,
    playFromHand,
    viewer.hand,
    undoMutate,
    peek,
    state.seat,
  ]);

  // ---------------------------------------------------------------- render

  const opponents = seatOrder(state).filter((pid) => pid !== state.seat);
  const opponentScale = opponentCardScale(opponents.length);

  return (
    <div className="table" data-testid="table">
      <PhaseTrack state={state} />

      <motion.div className="table__body" ref={boardRef} animate={shake}>
        <aside className="rail rail--left">
          <StackPanel state={state} />
          <EventTicker state={state} events={events} cardName={game.cardName} />
        </aside>

        <main className="play">
          <div className="play__opponents">
            {opponents.map((pid) => (
              <PlayerMat
                key={pid}
                state={state}
                player={state.players[pid]}
                names={names}
                compact
                cardScale={opponentScale}
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
              />
            ))}
          </div>

          <div className="play__mine">
            <PlayerMat
              state={state}
              player={viewer}
              names={names}
              cardScale={CARD_SCALE.own}
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
              locked={locked}
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
            narrating={narration.busy}
            onSkipNarration={narration.skip}
            busy={busy}
            aiThinking={aiThinking}
            standDown={modalOwnsDecision}
          />
        </aside>

        <CombatArrows state={state} boardRef={boardRef} />
        <FxLayer beat={narration.current} speed={speed} boardRef={boardRef} state={state} />
      </motion.div>

      <div className="table__foot">
        {targeting.length > 0 && targetableOids.size === 0 && targetablePids.size === 0 && (
          <div className="choices" data-testid="choice-list">
            <span className="choices__label">Choose:</span>
            {targeting.map((action) => (
              <button
                type="button"
                key={action.id}
                className="btn btn--ghost"
                data-action-id={action.id}
                onClick={() => act(action.id)}
              >
                {action.label}
              </button>
            ))}
            <button type="button" className="btn btn--ghost" onClick={endTargeting}>
              Cancel
            </button>
          </div>
        )}

        {targeting.length > 0 && (targetableOids.size > 0 || targetablePids.size > 0) && (
          <div className="choices" data-testid="targeting-hint">
            <span className="choices__label">Pick a target</span>
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
          onActivate={playFromHand}
          onDropOn={onDropOnZone}
          disabled={locked}
        />
      </div>

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

      <PromptDialog state={state} actions={actions} onAct={act} disabled={locked} />
      <ZonePeek state={state} />
      <GameOverScreen state={state} onRematch={onRematch} onQuit={onQuit} />
    </div>
  );
}
