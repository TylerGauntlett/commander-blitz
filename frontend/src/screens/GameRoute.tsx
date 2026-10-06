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
 *
 * COMING BACK TO A GAME DOES NOT DEAL IT AGAIN (TECH_DEBT FT-07). The held
 * seat is null on every mount, and the table used to wait for it -- so a back
 * press into a game whose state was sitting in the query cache still drew
 * "Dealing…", faded it out, and only then faded the table in. The seat the
 * table draws for is now `held ?? game.yourSeat`: a cached response already
 * says whose seat this is, so it renders the table on the first frame, and
 * `useGame` keeps that response as placeholder data across the key change
 * the held seat then makes.
 */

import { AnimatePresence } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ApiError, setPlayerToken } from "../api/client";
import type { SeatConfig } from "../api/types";
import { Table } from "../components/game/Table";
import { Screen } from "../components/screen/Screen";
import { gamePath } from "../logic/routes";
import { useUiStore } from "../state/uiStore";
import { useGame, useNewGame } from "../state/useGame";
import { useGameSession } from "../state/usePodSession";

export function GameRoute() {
  const navigate = useNavigate();
  const gameId = useParams().gameId ?? "";
  const session = useGameSession(gameId);
  const clearStaging = useUiStore((s) => s.clearStaging);
  const setError = useUiStore((s) => s.setError);

  /*
   * The seat, and the address it belongs to.
   *
   * A plain `useState<number | null>` was enough while the only way to a second
   * game was through the front door, which unmounts this route. A rematch is
   * not: it navigates from `/games/a` to `/games/b` and React keeps the same
   * component, so a bare seat would carry seat 2 of the game that just ended
   * into a game that may not have a seat 2. Held with the id it was learnt for
   * and adjusted during render -- the same shape, and for the same reason, as
   * `usePodSession`'s `arm`: an effect would let the new game's first request
   * go out under the old game's seat.
   */
  const [held, setHeld] = useState<{ gameId: string; seat: number | null }>({
    gameId,
    seat: null,
  });
  if (held.gameId !== gameId) setHeld({ gameId, seat: null });
  const heldSeat = held.gameId === gameId ? held.seat : null;
  // Memoised: `useGame` keys its listener on this object, and a fresh literal
  // every render tore the long poll down and re-issued it on every re-render,
  // leaving a parked server thread behind each time.
  const gameSession = useMemo(
    () => (gameId ? { gameId, seat: heldSeat } : null),
    [gameId, heldSeat],
  );
  const game = useGame(gameSession);

  /*
   * The seat to DRAW for, which is not the same question as the seat to ASK
   * for. The query key moves once, from null to the seat, and that is the
   * effect below; the table does not have to wait for it. A response for this
   * game -- including one already in the cache when the route mounts -- names
   * the seat, and `useGame` only reports a response for the game in the key.
   */
  const seat = heldSeat ?? game.yourSeat;

  useEffect(() => {
    if (heldSeat === null && game.yourSeat !== null) {
      setHeld({ gameId, seat: game.yourSeat });
    }
  }, [heldSeat, game.yourSeat, gameId]);

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

  /*
   * REMATCH DEALS A NEW GAME. IT USED TO BE `onRematch={quit}`.
   *
   * The button said Rematch and went to the front door -- so the one thing
   * somebody wants at the end of a game they enjoyed was three screens away:
   * the door, a new pod, a deck for every chair, and a deal. This is that,
   * done: the same decks, the same seats, the same opponents, one press.
   *
   * `POST /api/games` rather than a new pod, because that endpoint already
   * takes exactly the lineup a finished game can describe -- a deck and a kind
   * per seat -- and needs no code, no invite and no lock-in from four people
   * who have just agreed to play again. It also produces a session with no
   * token map, which is the right shape: nobody is joining this one.
   *
   * `agent` is deliberately omitted. The table view does not carry which agent
   * an AI seat is running -- only the pod knew -- and guessing at `heuristic`
   * would quietly change the difficulty of the rematch. The server's default is
   * the same default a pod's CPU chair takes.
   *
   * NO SEED. The point is another game, not the same one again.
   */
  const rematching = useNewGame();
  const rematch = () => {
    const finished = game.state;
    if (!finished || rematching.isPending) return;
    const seats: SeatConfig[] = finished.players.map((player) => ({
      deck_id: player.deck_id,
      kind: game.humanSeats.includes(player.pid) ? "human" : "ai",
      name: player.name,
    }));
    clearStaging();
    setError(null);
    rematching.mutate(
      { seats },
      {
        onSuccess: (made) => {
          // The pod's token belongs to the game that just ended, and the new
          // session has no token map at all -- `useGameSession` re-arms from
          // `gamePodCode`, which has no record of this id, so it clears itself.
          // Cleared here as well so nothing goes out under it in between.
          setPlayerToken(null);
          // `replace`, for the reason the pod's deal gives: the table behind us
          // is over, and back must not offer to walk into it.
          navigate(gamePath(made.game_id), { replace: true });
        },
        onError: (caught: Error) => setError(caught.message),
      },
    );
  };

  const failed = game.error;
  const status = failed instanceof ApiError ? failed.status : 0;

  /*
   * A CROSS-FADE, NOT A WAIT.
   *
   * `mode="wait"` is right for `App`'s boundary, for the history-gesture reason
   * `Screen` gives, and it stays there. Here it only ever cost time: the deal
   * had to fade "Dealing…" all the way out before the table could start
   * fading in, two back-to-back fades for one change. `popLayout` lifts the
   * leaving screen out of the flow so the arriving one takes its place at
   * once, and the two fade across each other. `Screen` stands its controller
   * and its ring down the moment it starts to leave, so the overlap never has
   * two of either.
   */
  return (
    <AnimatePresence mode="popLayout">
      {game.state && seat !== null ? (
        <Screen key="table" variant="zoom">
          <Table
            session={{ gameId, seat }}
            game={game}
            state={game.state}
            onQuit={quit}
            onRematch={rematch}
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
