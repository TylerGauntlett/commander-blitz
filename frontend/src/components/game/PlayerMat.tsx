/**
 * One player's side of the table: their orb, and their permanents in lanes.
 *
 * Opponents render compact (smaller cards, no lane labels) because their board
 * matters but their ergonomics do not -- you never drag onto it.
 */

import type { CardView, GameView, PlayerView } from "../../api/types";
import { LANES, groupBattlefield } from "../../logic/zoneGrouping";
import { Lane } from "./Lane";
import { PlayerOrb } from "./PlayerOrb";

interface Props {
  state: GameView;
  player: PlayerView;
  names: string[];
  compact?: boolean;
  cardWidth: number;
  actionableOids: ReadonlySet<number>;
  /** Lanes that would accept the card currently being dragged. */
  activeLanes?: ReadonlySet<string>;
  draggable?: boolean;
  isPlayable?: (card: CardView) => boolean;
  isTargetable?: (card: CardView) => boolean;
  isStaged?: (card: CardView) => boolean;
  onActivate?: (card: CardView) => void;
  onDropOn?: (card: CardView, zone: string) => void;
  /** This player can be pointed at right now. */
  playerTargetable?: boolean;
  onSelectPlayer?: (pid: number) => void;
}

export function PlayerMat({
  state,
  player,
  names,
  compact = false,
  cardWidth,
  actionableOids,
  activeLanes,
  draggable = false,
  isPlayable,
  isTargetable,
  isStaged,
  onActivate,
  onDropOn,
  playerTargetable = false,
  onSelectPlayer,
}: Props) {
  const lanes = groupBattlefield(state, player.pid);
  // An empty lane is noise on an opponent's board; keep all four for the
  // viewer so drop targets never move around under the pointer.
  const shown = compact ? LANES.filter((lane) => lanes[lane].length > 0) : LANES;

  return (
    <section className={compact ? "mat mat--compact" : "mat"} data-testid={`mat-${player.pid}`}>
      <PlayerOrb
        player={player}
        isViewer={player.pid === state.seat}
        isActive={player.pid === state.active_player}
        hasPriority={state.priority_player === player.pid}
        names={names}
        compact={compact}
        targetable={playerTargetable}
        onSelect={onSelectPlayer}
      />
      <div className="mat__lanes">
        {shown.map((lane) => (
          <Lane
            key={lane}
            lane={lane}
            pid={player.pid}
            cards={lanes[lane]}
            cardWidth={cardWidth}
            active={activeLanes?.has(`${player.pid}:${lane}`) ?? false}
            draggable={draggable}
            actionableOids={actionableOids}
            isPlayable={isPlayable}
            isTargetable={isTargetable}
            isStaged={isStaged}
            onActivate={onActivate}
            onDropOn={onDropOn}
          />
        ))}
        {compact && shown.length === 0 && <div className="mat__empty">No permanents</div>}
      </div>
    </section>
  );
}
