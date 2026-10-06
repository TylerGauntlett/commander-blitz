/**
 * The play area: the floating stack, the opponents' row, and the viewer's own
 * board -- or the board of whoever they are standing at.
 *
 * Lifted out of `Table.tsx`'s render as it was, in the pattern `TableFoot`
 * set: everything here is drawn from values `Table` owns and hands down.
 */

import type { RefObject } from "react";
import type { CardView, GameView, PlayerView, StackItemView } from "../../api/types";
import { stopId } from "../../input/stops";
import type { useTableDerived } from "../../state/useTableDerived";
import type { useZoomFit } from "../../state/useZoomFit";
import { PlayerMat } from "./PlayerMat";
import { StackPanel } from "./StackPanel";

type Derived = ReturnType<typeof useTableDerived>;

interface Props {
  state: GameView;
  viewer: PlayerView;
  opponents: number[];
  podRef: RefObject<HTMLDivElement>;
  mineRef: RefObject<HTMLDivElement>;
  zoom: ReturnType<typeof useZoomFit>;
  derived: Derived;
  selectedOid: number | null;
  stagedAttacks: Record<number, number>;
  stagedBlocks: Record<number, number>;
  viewing: number | null;
  setViewing: (pid: number | null) => void;
  locked: boolean;
  hover: (oid: number | null) => void;
  onBoardCard: (card: CardView) => void;
  onStackItem: (item: StackItemView) => void;
  onSelectPlayer: (pid: number) => void;
  playFromHand: (card: CardView) => void;
}

export function TablePlay({
  state,
  viewer,
  opponents,
  podRef,
  mineRef,
  zoom,
  derived,
  selectedOid,
  stagedAttacks,
  stagedBlocks,
  viewing,
  setViewing,
  locked,
  hover,
  onBoardCard,
  onStackItem,
  onSelectPlayer,
  playFromHand,
}: Props) {
  const {
    playableOids,
    abilityOids,
    abilityLabels,
    actionableOids,
    targetableOids,
    targetablePids,
    combatCandidates,
    blockedAttackers,
    spending,
    activeLanes,
  } = derived;
  return (
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
      {state.stack.length > 0 && <StackPanel state={state} onPress={onStackItem} />}

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
  );
}
