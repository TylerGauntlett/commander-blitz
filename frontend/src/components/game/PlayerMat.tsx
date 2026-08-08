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
  cardScale: number;
  actionableOids: ReadonlySet<number>;
  /** Lanes that would accept the card currently being dragged. */
  activeLanes?: ReadonlySet<string>;
  draggable?: boolean;
  isPlayable?: (card: CardView) => boolean;
  hasAbility?: (card: CardView) => boolean;
  abilityLabel?: (card: CardView) => string | null;
  isTargetable?: (card: CardView) => boolean;
  isStaged?: (card: CardView) => boolean;
  isSelected?: (card: CardView) => boolean;
  onActivate?: (card: CardView) => void;
  onDropOn?: (card: CardView, zone: string) => void;
  /** This player can be pointed at right now. */
  playerTargetable?: boolean;
  onSelectPlayer?: (pid: number) => void;
  /** Oids a legal play action names, for the commander plinth's ready state. */
  playableOids?: ReadonlySet<number>;
  /**
   * Casting a commander out of the command zone. Deliberately not `onActivate`:
   * that one routes a click on a *permanent* (target, block, activate), and a
   * card in the command zone is being played, not used.
   */
  onCastCommander?: (card: CardView) => void;
  onHoverCard?: (oid: number | null) => void;
  /** Sources a hovered spell would tap, for the orb's mana row. */
  spending?: ReadonlySet<number>;
  /** Input is gated (narration playing, request in flight). */
  locked?: boolean;
}

export function PlayerMat({
  state,
  player,
  names,
  compact = false,
  cardScale,
  actionableOids,
  activeLanes,
  draggable = false,
  isPlayable,
  hasAbility,
  abilityLabel,
  isTargetable,
  isStaged,
  isSelected,
  onActivate,
  onDropOn,
  playerTargetable = false,
  onSelectPlayer,
  playableOids,
  onCastCommander,
  onHoverCard,
  spending,
  locked = false,
}: Props) {
  const lanes = groupBattlefield(state, player.pid);
  // An empty lane is noise on an opponent's board; keep all four for the
  // viewer so drop targets never move around under the pointer.
  const shown = compact ? LANES.filter((lane) => lanes[lane].length > 0) : LANES;

  return (
    <section className={compact ? "mat mat--compact" : "mat"} data-testid={`mat-${player.pid}`}>
      {/* The mat's first column is everything that is a fact about this player
          rather than a permanent on their board -- commander, life, mana,
          zones. All of it lives inside the orb; see PlayerOrb. */}
      <div className="mat__side">
        <PlayerOrb
          state={state}
          player={player}
          isViewer={player.pid === state.seat}
          isActive={player.pid === state.active_player}
          hasPriority={state.priority_player === player.pid}
          names={names}
          compact={compact}
          targetable={playerTargetable}
          onSelect={onSelectPlayer}
          spending={spending}
          playableOids={playableOids}
          onCastCommander={onCastCommander}
          onHoverCard={onHoverCard}
          locked={locked}
        />
      </div>
      <div className="mat__lanes">
        {shown.map((lane) => (
          <Lane
            key={lane}
            lane={lane}
            pid={player.pid}
            cards={lanes[lane]}
            cardScale={cardScale}
            active={activeLanes?.has(`${player.pid}:${lane}`) ?? false}
            draggable={draggable}
            actionableOids={actionableOids}
            isPlayable={isPlayable}
            hasAbility={hasAbility}
            abilityLabel={abilityLabel}
            isTargetable={isTargetable}
            isStaged={isStaged}
            isSelected={isSelected}
            onActivate={onActivate}
            onDropOn={onDropOn}
          />
        ))}
        {compact && shown.length === 0 && <div className="mat__empty">No permanents</div>}
      </div>
    </section>
  );
}
