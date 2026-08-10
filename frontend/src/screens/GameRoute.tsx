/**
 * The table, at its own address.
 *
 * Two things happen here that used to be two separate screens. `dealing` was
 * never a page -- it is the gap between knowing a game id and knowing which of
 * its seats is yours, which only the first state response can say, because the
 * lobby's four chairs are compacted down to the players actually in the game.
 * So it is a state of this route rather than an address of its own: there is no
 * URL worth minting for a wait that resolves in one round trip.
 *
 * The seat starts null -- "ask my token" -- and moves once. `useGame`'s query
 * key contains the seat, so that single change refetches exactly once, which is
 * the same number of requests the two-hook version made.
 */

import { AnimatePresence } from "motion/react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ApiError, setPlayerToken } from "../api/client";
import { Table } from "../components/game/Table";
import { Screen } from "../components/screen/Screen";
import { useUiStore } from "../state/uiStore";
import { useGame } from "../state/useGame";
import { useGameSession } from "../state/usePodSession";

export function GameRoute() {
  const navigate = useNavigate();
  const gameId = useParams().gameId ?? "";
  const session = useGameSession(gameId);
  const clearStaging = useUiStore((s) => s.clearStaging);
  const setError = useUiStore((s) => s.setError);

  const [seat, setSeat] = useState<number | null>(null);
  const game = useGame(gameId ? { gameId, seat } : null);

  useEffect(() => {
    if (seat === null && game.yourSeat !== null) setSeat(game.yourSeat);
  }, [seat, game.yourSeat]);

  // Leaving the table is one-way: the game is still running on the server, but
  // this client has said it is done with it. `replace` so the back button does
  // not offer to walk back into a game nobody is playing any more.
  //
  // The module's token slot is disarmed but the *stored* token is left alone:
  // walking away from a table is not resigning a seat, and coming back to this
  // address re-arms it from storage.
  const quit = () => {
    setPlayerToken(null);
    clearStaging();
    setError(null);
    navigate("/", { replace: true });
  };

  const failed = game.error;
  const status = failed instanceof ApiError ? failed.status : 0;

  return (
    <AnimatePresence mode="wait">
      {game.state && seat !== null ? (
        <Screen key="table" variant="zoom">
          <Table
            session={{ gameId, seat }}
            game={game}
            state={game.state}
            onQuit={quit}
            onRematch={quit}
          />
        </Screen>
      ) : (
        <Screen key="dealing" variant="fade" center testId="dealing">
          <p className="menu__note">
            {!failed
              ? "Dealing…"
              : status === 403 || !session
                ? "This table belongs to a pod you are not in."
                : status === 404
                  ? "That game is over, or the server has restarted."
                  : `Could not load the game: ${failed.message}`}
          </p>
          {failed && (
            <button type="button" className="btn btn--ghost" onClick={quit}>
              Back
            </button>
          )}
        </Screen>
      )}
    </AnimatePresence>
  );
}
