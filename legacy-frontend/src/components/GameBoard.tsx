/**
 * The table.
 *
 * Opponents across the top, the viewer at the bottom, the stack and log to one
 * side. Drag-and-drop is wired here because the drop handler needs both the
 * dragged card and the lane it landed on.
 */

import { DndContext, type DragEndEvent, type DragStartEvent } from "@dnd-kit/core";
import { useMemo, useState } from "react";
import type { CardView, GameEvent, GameView, LegalAction } from "../api/types";
import { actionsForCard, canDropOnLane, resolveSingleAction } from "../logic/actionMatch";
import { LANES, seatOrder } from "../logic/zoneGrouping";
import { useUiStore } from "../state/uiStore";
import { CombatOverlay } from "./CombatOverlay";
import { EventLog } from "./EventLog";
import { Hand } from "./Hand";
import { PlayerMat } from "./PlayerMat";
import { PriorityBar } from "./PriorityBar";
import { StackPanel } from "./StackPanel";
import { TargetPicker } from "./TargetPicker";
import { ZonePeek } from "./ZonePeek";

interface Props {
  state: GameView;
  actions: LegalAction[];
  events: GameEvent[];
  busy: boolean;
  onAct: (action: LegalAction) => void;
  onDeclare: (kind: "attackers" | "blockers", pairs: [number, number][]) => void;
  onUndo: () => void;
  onNewGame: () => void;
}

export function GameBoard({
  state,
  actions,
  events,
  busy,
  onAct,
  onDeclare,
  onUndo,
  onNewGame,
}: Props) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [pickerActions, setPickerActions] = useState<LegalAction[]>([]);
  const error = useUiStore((s) => s.error);
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);

  const order = seatOrder(state);
  const viewer = state.players[state.seat];

  /** Lanes to highlight while a card is being dragged. */
  const activeLanes = useMemo(() => {
    const set = new Set<string>();
    if (dragging === null) return set;
    for (const lane of LANES) {
      if (canDropOnLane(state, actions, dragging, lane)) {
        set.add(`${state.seat}:${lane}`);
      }
    }
    return set;
  }, [dragging, state, actions]);

  const stagedOids = useMemo(
    () =>
      new Set<number>([
        ...Object.keys(stagedAttacks).map(Number),
        ...Object.keys(stagedBlocks).map(Number),
      ]),
    [stagedAttacks, stagedBlocks],
  );

  const targetableOids = useMemo(() => {
    const set = new Set<number>();
    for (const action of pickerActions) {
      for (const ref of action.targets) {
        if (ref.kind === "object") set.add(ref.id);
      }
    }
    return set;
  }, [pickerActions]);

  /** Playing a card: submit it if unambiguous, otherwise open the target picker. */
  const play = (card: CardView) => {
    const candidates = actionsForCard(actions, card.oid);
    if (candidates.length === 0) return;
    const single = resolveSingleAction(actions, card.oid);
    if (single) {
      onAct(single);
      return;
    }
    setPickerActions(candidates);
  };

  const onDragStart = (event: DragStartEvent) => {
    const oid = (event.active.data.current as { oid?: number } | undefined)?.oid;
    setDragging(oid ?? null);
  };

  const onDragEnd = (event: DragEndEvent) => {
    const oid = (event.active.data.current as { oid?: number } | undefined)?.oid;
    setDragging(null);
    if (oid === undefined || !event.over) return;
    const lane = (event.over.data.current as { lane?: string } | undefined)?.lane;
    // Dropping inside a lane is cosmetic; only a legal action is ever submitted.
    if (!lane || !canDropOnLane(state, actions, oid, lane as (typeof LANES)[number])) return;
    const card = viewer.hand?.find((entry) => entry.oid === oid);
    if (card) play(card);
  };

  return (
    <DndContext onDragStart={onDragStart} onDragEnd={onDragEnd}>
      <div className="board">
        <div className="board__opponents">
          {order
            .filter((pid) => pid !== state.seat)
            .map((pid) => (
              <PlayerMat
                key={pid}
                state={state}
                pid={pid}
                isViewer={false}
                activeLanes={activeLanes}
                targetableOids={targetableOids}
                stagedOids={stagedOids}
                onCardClick={() => undefined}
              />
            ))}
        </div>

        <div className="board__middle">
          <StackPanel state={state} />
          <CombatOverlay
            state={state}
            actions={actions}
            busy={busy}
            onConfirm={onDeclare}
            onSkip={onAct}
          />
          {pickerActions.length > 0 && (
            <TargetPicker
              state={state}
              actions={pickerActions}
              busy={busy}
              onPick={(action) => {
                setPickerActions([]);
                onAct(action);
              }}
              onCancel={() => setPickerActions([])}
            />
          )}
          <EventLog state={state} events={events} />
        </div>

        <PlayerMat
          state={state}
          pid={state.seat}
          isViewer
          activeLanes={activeLanes}
          targetableOids={targetableOids}
          stagedOids={stagedOids}
          onCardClick={() => undefined}
        />

        <Hand cards={viewer.hand ?? []} actions={actions} onPlay={play} />

        {error && <div className="error-banner">{error}</div>}

        <PriorityBar
          state={state}
          actions={actions}
          busy={busy}
          onAct={onAct}
          onUndo={onUndo}
          onNewGame={onNewGame}
        />

        <ZonePeek state={state} />
      </div>
    </DndContext>
  );
}
