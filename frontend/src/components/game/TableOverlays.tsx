/**
 * Everything drawn over the board: the toasts, the card hold, the region
 * dial, the log overlay and the four modals.
 *
 * Lifted out of `Table.tsx`'s render as it was. The order is the stacking
 * order, and the comments that explain each surface travel with it. Nothing
 * here decides anything -- `Table` owns every flag and hands the setters down.
 */

import { motion } from "motion/react";
import type { GameEvent, GameView, LegalAction } from "../../api/types";
import { type GroupId, getGroup } from "../../input/groups";
import { stopId } from "../../input/stops";
import type { Gesture } from "../../logic/followUp";
import type { NameLookup } from "../../logic/labels";
import { findCard } from "../../logic/zoneGrouping";
import { AbilityMenu } from "./AbilityMenu";
import { CardHold } from "./CardHold";
import { EventTicker } from "./EventTicker";
import { GameOverScreen } from "./GameOverScreen";
import { GroupDial } from "./GroupDial";
import { OpeningHand } from "./OpeningHand";
import { PromptDialog } from "./PromptDialog";
import { ZonePeek } from "./ZonePeek";

interface Props {
  state: GameView;
  actions: LegalAction[];
  events: GameEvent[];
  cardName: NameLookup | undefined;
  error: string | null;
  setError: (error: string | null) => void;
  stalled: boolean;
  heldCard: number | null;
  /** Put the held card down -- the pointer's way out, which a pad never needed. */
  closeHold: () => void;
  dialOpen: boolean;
  setDialOpen: (open: boolean) => void;
  enterGroup: (id: GroupId) => void;
  logOverlay: boolean;
  toggleLogOverlay: () => void;
  act: (actionId: string) => void;
  /** Where the ring goes after a gesture that moved the decision elsewhere. */
  followUp: (gesture: Gesture) => void;
  locked: boolean;
  /** How each card in a graveyard or exile pile got there, by oid. */
  removals: Map<number, string>;
  onRematch: () => void;
  onQuit: () => void;
}

export function TableOverlays({
  state,
  actions,
  events,
  cardName,
  error,
  setError,
  stalled,
  heldCard,
  closeHold,
  dialOpen,
  setDialOpen,
  enterGroup,
  logOverlay,
  toggleLogOverlay,
  act,
  followUp,
  locked,
  removals,
  onRematch,
  onQuit,
}: Props) {
  return (
    <>
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

      {/*
      The card hold.

      No `AnimatePresence`: it is gone the instant you press
      anything else, and an exit animation on a thing you dismissed by acting
      would still be fading while the action it was covering resolved.
    */}
      <CardHold
        card={heldCard === null ? null : findCard(state, heldCard)}
        onClose={closeHold}
      />

      {/*
      Which ability, when a press on a permanent could mean two. Under the
      hold, so `Y` can read the card the question is about over it.
    */}
      <AbilityMenu
        state={state}
        actions={actions}
        act={act}
        followUp={followUp}
        disabled={locked}
      />

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
          <EventTicker state={state} events={events} cardName={cardName} />
        </div>
      )}

      <PromptDialog state={state} actions={actions} onAct={act} disabled={locked} />
      <OpeningHand state={state} actions={actions} onAct={act} disabled={locked} />
      <ZonePeek state={state} reasons={removals} />
      <GameOverScreen state={state} onRematch={onRematch} onQuit={onQuit} />
    </>
  );
}
