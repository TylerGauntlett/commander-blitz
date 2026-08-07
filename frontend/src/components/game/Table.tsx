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
import { actionsForCard, availableAttackers, canDropOnLane } from "../../logic/actionMatch";
import type { Lane as LaneName } from "../../logic/zoneGrouping";
import { LANES, seatOrder } from "../../logic/zoneGrouping";
import { useUiStore } from "../../state/uiStore";
import type { GameSession, useGame } from "../../state/useGame";
import { ActionBar } from "./ActionBar";
import { CardPreview } from "./CardPreview";
import { CombatArrows } from "./CombatArrows";
import { CombatPanel, legalBlockTargets, nextDefender } from "./CombatPanel";
import { EventTicker } from "./EventTicker";
import { FxLayer, useScreenShake } from "./FxLayer";
import { GameOverScreen } from "./GameOverScreen";
import { HandFan } from "./HandFan";
import { PhaseTrack } from "./PhaseTrack";
import { PlayerMat } from "./PlayerMat";
import { PromptDialog, isModalDecision } from "./PromptDialog";
import { StackPanel } from "./StackPanel";
import { ZonePeek } from "./ZonePeek";

const OWN_CARD_W = 104;
const OPPONENT_CARD_W = 82;

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
  const error = useUiStore((s) => s.error);
  const setError = useUiStore((s) => s.setError);

  const shake = useScreenShake(narration.current);
  const viewer = state.players[state.seat];
  const names = useMemo(() => state.players.map((p) => p.name), [state.players]);
  const decisionKind = state.pending?.player === state.seat ? state.pending.kind : null;
  const inCombatDecision = decisionKind !== null && COMBAT_DECISIONS.has(decisionKind);
  const locked = busy || narration.busy;

  // A decision's buttons must exist exactly once in the document. When the
  // modal owns the decision the bar shows the prompt but no actions.
  const modalOwnsDecision = isModalDecision(state);
  const barActions = modalOwnsDecision ? [] : actions;

  // Depend on the `mutate` functions, which react-query keeps stable, rather
  // than on the mutation objects, which are new every render -- otherwise every
  // callback below is rebuilt each render and the keyboard listener with it.
  const actMutate = game.act.mutate;
  const declareMutate = game.declare.mutate;
  const undoMutate = game.undo.mutate;

  const act = useCallback(
    (actionId: string) => {
      if (locked) return;
      endTargeting();
      actMutate(actionId);
    },
    [locked, endTargeting, actMutate],
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
      if (locked) return;
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
    [locked, actions, act, beginTargeting],
  );

  const onDropOnZone = useCallback(
    (card: CardView, zone: string) => {
      if (locked) return;
      const [kind, , lane] = zone.split(":");
      if (kind !== "lane") return;
      if (!canDropOnLane(state, actions, card.oid, lane as LaneName)) return;
      playFromHand(card);
    },
    [locked, state, actions, playFromHand],
  );

  /** Clicking a permanent: resolve a target, or stage it for combat. */
  const onBoardCard = useCallback(
    (card: CardView) => {
      if (locked) return;

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

      // 2. Attacking: each click sends it at the next legal defender, then home.
      if (decisionKind === "declare_attackers" && combatCandidates.has(card.oid)) {
        const next = nextDefender(actions, card.oid, stagedAttacks[card.oid]);
        if (next === null) {
          unstageAttack(card.oid);
          select(null);
        } else {
          stageAttack(card.oid, next);
          select(card.oid);
        }
        return;
      }

      // 3. Blocking: pick your creature, then the attacker it stops.
      if (decisionKind === "declare_blockers") {
        if (stagedBlocks[card.oid] !== undefined) {
          unstageBlock(card.oid);
          return;
        }
        if (combatCandidates.has(card.oid)) {
          select(selectedOid === card.oid ? null : card.oid);
          return;
        }
        if (
          selectedOid !== null &&
          legalBlockTargets(actions, selectedOid).includes(card.oid)
        ) {
          stageBlock(selectedOid, card.oid);
          select(null);
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
      locked,
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
      if (locked) return;
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
    [locked, decisionKind, selectedOid, actions, stageAttack, targeting, act],
  );

  const onDeclare = useCallback(
    (kind: "attackers" | "blockers", pairs: [number, number][]) => {
      if (locked) return;
      declareMutate({ kind, pairs });
    },
    [locked, declareMutate],
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
      if (locked) return;

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
    locked,
    narration,
    endTargeting,
    setPeek,
    playFromHand,
    viewer.hand,
    undoMutate,
  ]);

  // ---------------------------------------------------------------- render

  const opponents = seatOrder(state).filter((pid) => pid !== state.seat);

  return (
    <div className="table" data-testid="table">
      <PhaseTrack state={state} />

      <motion.div className="table__body" ref={boardRef} animate={shake}>
        <aside className="rail rail--left">
          <StackPanel state={state} />
          <EventTicker state={state} events={events} />
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
                cardWidth={OPPONENT_CARD_W}
                actionableOids={actionableOids}
                isTargetable={(card) => targetableOids.has(card.oid)}
                isStaged={(card) => stagedBlocks[card.oid] !== undefined}
                onActivate={onBoardCard}
                playerTargetable={targetablePids.has(pid)}
                onSelectPlayer={onSelectPlayer}
              />
            ))}
          </div>

          <div className="play__mine">
            <PlayerMat
              state={state}
              player={viewer}
              names={names}
              cardWidth={OWN_CARD_W}
              actionableOids={actionableOids}
              activeLanes={activeLanes}
              isPlayable={(card) => combatCandidates.has(card.oid)}
              isTargetable={(card) => targetableOids.has(card.oid)}
              isStaged={(card) =>
                stagedAttacks[card.oid] !== undefined || stagedBlocks[card.oid] !== undefined
              }
              onActivate={onBoardCard}
              playerTargetable={targetablePids.has(state.seat)}
              onSelectPlayer={onSelectPlayer}
            />
          </div>
        </main>

        <aside className="rail rail--right">
          <CardPreview state={state} />
        </aside>

        <CombatArrows state={state} boardRef={boardRef} />
        <FxLayer beat={narration.current} speed={speed} boardRef={boardRef} />
      </motion.div>

      <div className="table__foot">
        <CombatPanel
          state={state}
          actions={actions}
          onDeclare={onDeclare}
          onSkip={act}
          disabled={locked}
        />

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

        <div className="table__hand-row">
          <HandFan
            cards={viewer.hand ?? []}
            playableOids={playableOids}
            selectedOid={selectedOid}
            onActivate={playFromHand}
            onDropOn={onDropOnZone}
            disabled={locked}
          />
          <ActionBar
            state={state}
            actions={barActions}
            onAct={act}
            onUndo={() => undoMutate()}
            onQuit={onQuit}
            narrating={narration.busy}
            onSkip={narration.skip}
            busy={busy}
            aiThinking={aiThinking}
          />
        </div>
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
