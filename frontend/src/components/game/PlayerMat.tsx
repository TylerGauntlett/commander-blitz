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
import { OpponentSeat } from "./OpponentSeat";
import { PlayerOrb } from "./PlayerOrb";

/** Toward the opponent: what fights, and what sits behind it. */
const FRONT_BAND: readonly LaneName[] = ["Creatures", "Artifacts & Enchantments"];
/** Nearest this player: their mana. */
const BACK_BAND: readonly LaneName[] = ["Lands"];

interface Props {
  state: GameView;
  player: PlayerView;
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
  /** This opponent's board is the one currently drawn in the viewer's area. */
  viewing?: boolean;
  /**
   * `"lanes"` draws the permanents and no side column at all.
   *
   * The seat swap wants it: it shows somebody's BOARD somewhere other than that
   * somebody's seat, putting an opponent's lanes in the viewer's area (by a
   * click on their seat, or while `R2` is held) -- and the facts about that
   * player are already on screen, on their seat six pixels above.
   *
   * It is also what stops the document holding two `data-player="1"`s. `FxLayer`
   * resolves a damage numeral with `document.querySelector`, so a second one
   * takes whichever comes first -- which the old `R2` overlay did, drawing a
   * whole second `PlayerOrb` with a duplicate `life-<pid>` beside it while held.
   *
   * `"side"` is the mirror: the panel and no permanents. Two things want it.
   * The seat whose board has been moved into the viewer's area must stop
   * drawing that board, or the same permanents are laid out twice -- on a
   * handheld their lanes are already clipped to zero height, which is NOT the
   * same as absent, and a clipped card still owns its `data-oid`; the story
   * that asserts this found two of them the first time it ran. And the viewer
   * keeps their own panel beside somebody else's board, because life and open
   * mana are most of what you are assessing a threat against.
   */
  variant?: "full" | "lanes" | "side";
}

export function PlayerMat({
  state,
  player,
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
  viewing = false,
  variant = "full",
}: Props) {
  const lanes = groupBattlefield(state, player.pid);
  const attachments = attachmentsFor(state, player.pid);
  /*
   * The viewer keeps every lane, always. An opponent keeps only the ones
   * holding something.
   *
   * The viewer's mat is the one that has to hold still: it owns every drop
   * target, and a collapsing lane meant playing your first creature shoved your
   * land row down by a whole card and killing it shoved the row back up, under
   * the cursor, mid-decision. Reserving all three costs one card height on a mat
   * that will fill anyway.
   *
   * A compact mat cannot afford the same deal, and it was measured rather than
   * assumed. Three opponents leave each mat about 158px of lane width against a
   * 51px card, so the front band's 2:1 split gives creatures room for one card
   * per row -- an always-present, usually-empty global lane wrapped an
   * opponent's creatures onto a second row, which grew the opponents row and
   * pushed the viewer's whole board down. Hiding their empty lanes buys that
   * width back. The cost is that an opponent's first artifact still nudges the
   * layout, which is what it did before any of this.
   */
  const visible = (band: readonly LaneName[]) =>
    compact ? band.filter((lane) => lanes[lane].length > 0) : band;
  const bands = (mirrored ? [BACK_BAND, FRONT_BAND] : [FRONT_BAND, BACK_BAND])
    .map((band) => ({ band, shown: visible(band) }))
    .filter(({ shown }) => shown.length > 0);

  return (
    <section
      className={[
        "mat",
        compact ? "mat--compact" : "",
        variant === "lanes" ? "mat--lanes" : "",
        variant === "side" ? "mat--side" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid={`mat-${player.pid}`}
    >
      {/*
        Everything that is a fact about this player rather than a permanent on
        their board -- and it is a different component depending on whose seat
        it is, which is the whole of the seat round's (`docs/design-record.md#seat`) argument.

        THE VIEWER GETS A PANEL THEY OPERATE. Commander, life, mana, zones: all
        of it is theirs to press, and all of it lives inside the orb.

        AN OPPONENT GETS A SUMMARY THEY READ. None of an orb's controls is
        yours on somebody else's seat, so a pod was three control panels for
        controls nobody could press -- while the question actually being asked
        across the table, how developed is that board, was answered by counting
        cards at 51px. See `OpponentSeat`.

        Drawn at every size. A desktop that summarised opponents differently
        from a handheld would be two designs for one fact; what changes with the
        size is whether their lanes are drawn underneath, not what the seat is.
      */}
      {variant !== "lanes" && (
        <div className="mat__side">
          {compact ? (
            <OpponentSeat
              state={state}
              player={player}
              isActive={player.pid === state.active_player}
              hasPriority={state.priority_player === player.pid}
              targetable={playerTargetable}
              viewing={viewing}
              onSelect={onSelectPlayer}
              onHoverCard={onHoverCard}
              locked={locked}
            />
          ) : (
            <PlayerOrb
              state={state}
              player={player}
              isViewer={player.pid === state.seat}
              isActive={player.pid === state.active_player}
              hasPriority={state.priority_player === player.pid}
              targetable={playerTargetable}
              onSelect={onSelectPlayer}
              spending={spending}
              playableOids={playableOids}
              onCastCommander={onCastCommander}
              onHoverCard={onHoverCard}
              locked={locked}
            />
          )}
        </div>
      )}

      {/*
        Their permanents, unless they are being drawn somewhere else.

        `"side"` is the case where the seat swap has moved this board into
        the viewer's area -- or where this is the viewer's own panel, sitting
        beside somebody else's lanes. Their lanes are already clipped to zero
        height on a handheld, and a clipped card still owns its `data-oid` --
        so the cards have to LEAVE rather than be hidden, or the document holds
        two boxes for every permanent and `FxLayer` picks one.
      */}
      {variant !== "side" && (
        <div className="mat__lanes">
          {bands.map(({ band, shown }) => (
            <div
              key={band === FRONT_BAND ? "front" : "back"}
              // A front band down to one lane takes the whole width: leaving the
              // hidden lane's track in place would give away the third of a
              // compact mat that hiding it was meant to reclaim.
              className={[
                "band",
                band === FRONT_BAND ? "band--front" : "band--back",
                shown.length === 1 ? "band--solo" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {shown.map((lane) => (
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
      )}
    </section>
  );
}
