/**
 * One player's side of the table: their orb, and their permanents in lanes.
 *
 * Opponents render compact (smaller cards, no lane labels) because their board
 * matters but their ergonomics do not -- you never drag onto it.
 *
 * The lanes sit in two *bands*, which is the arrangement a physical table has:
 * creatures and the global artifacts and enchantments across the front, lands
 * in the row nearest the player who controls them. `mirrored` flips the two for
 * an opponent, so their lands sit against their own edge of the screen and the
 * two creature bands meet in the middle -- combat is then declared across a
 * line rather than diagonally past a wall of mana.
 */

import type { CardView, GameView, PlayerView } from "../../api/types";
import {
  type Lane as LaneName,
  attachmentsFor,
  groupBattlefield,
} from "../../logic/zoneGrouping";
import { Lane } from "./Lane";
import { PlayerOrb } from "./PlayerOrb";

/** Toward the opponent: what fights, and what sits behind it. */
const FRONT_BAND: readonly LaneName[] = ["Creatures", "Artifacts & Enchantments"];
/** Nearest this player: their mana. */
const BACK_BAND: readonly LaneName[] = ["Lands"];

interface Props {
  state: GameView;
  player: PlayerView;
  names: string[];
  compact?: boolean;
  /** Lands on top instead of underneath: this mat faces the viewer. */
  mirrored?: boolean;
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
  mirrored = false,
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
  const attachments = attachmentsFor(state, player.pid);
  /*
   * Every lane is always rendered, on every mat, empty or not.
   *
   * Opponents used to drop their empty lanes as noise. The noise was real, but
   * the cost was worse: an opponent's first creature grew their mat, which grew
   * the opponents row, which pushed your own board down the screen -- so the
   * table moved under your cursor because of something happening on somebody
   * else's turn. Reserving the slot is what makes a mat a fixed height, and a
   * fixed height is what makes the board hold still.
   */
  const bands = mirrored ? [BACK_BAND, FRONT_BAND] : [FRONT_BAND, BACK_BAND];

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
        {bands.map((band) => (
          <div
            key={band === FRONT_BAND ? "front" : "back"}
            className={band === FRONT_BAND ? "band band--front" : "band band--back"}
          >
            {band.map((lane) => (
              <Lane
                key={lane}
                lane={lane}
                pid={player.pid}
                cards={lanes[lane]}
                attachments={attachments}
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
          </div>
        ))}
      </div>
    </section>
  );
}
