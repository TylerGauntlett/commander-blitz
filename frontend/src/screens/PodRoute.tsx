/**
 * A pod, at its own address.
 *
 * The address says which pod; `sessionStorage` says whether this tab is in it.
 * Those are two different questions and the split is deliberate -- a link is
 * something people paste into a group chat, so it must not be the thing that
 * grants a seat. A tab with no token for this code goes to the front door with
 * the code filled in, which is the join flow that already existed.
 *
 * Reloading with a token is the case this whole route exists for: it lands you
 * back in your chair with nothing to click. Before, the code was in a `useState`
 * and a refresh forgot which pod you were in.
 */

import { useEffect } from "react";
import { Navigate, useNavigate, useParams } from "react-router";
import { ApiError } from "../api/client";
import { PodLobby } from "../components/lobby/PodLobby";
import { Screen } from "../components/screen/Screen";
import { normaliseCode } from "../logic/lobby";
import { gamePath, joinPath } from "../logic/routes";
import { useDecks, useStarDeck } from "../state/useGame";
import { usePod } from "../state/usePod";
import { linkGame, usePodSession } from "../state/usePodSession";

/**
 * The shuffle a test pinned, or nothing.
 *
 * EVERY DEAL A PLAYER MAKES IS RANDOM, AND THERE IS NO CONTROL FOR IT.
 *
 * There was a "Seed" field on the pod rail, host-only, and it was wrong twice
 * over. A reproducible shuffle is a debugging tool -- it is on the screen the
 * moment before a match starts, it asks a question nobody arriving to play has,
 * and every reader of the rail had to skip past it. It was also one of the two
 * text fields the focus ring could walk into and, before `fieldKeys.ts:fieldKeeps`,
 * never walk out of.
 *
 * The specs still need determinism, so it is a window flag set by
 * `page.addInitScript` -- exactly the seam `__COMMANDERBLITZ_ZOOM_LOCK` already uses,
 * and for the same stated reason: `localStorage` would survive into a real
 * player's browser and silently pin their shuffle with nothing on screen to
 * point at, whereas a window global cannot outlive the page it was injected
 * into.
 *
 * Non-finite values are dropped rather than sent, because an empty seed means
 * "surprise me" and must reach the server as no seed at all -- 0 is a perfectly
 * good seed and would deal the same game every time.
 */
function pinnedSeed(): number | undefined {
  const pinned = (window as { __COMMANDERBLITZ_SEED?: unknown }).__COMMANDERBLITZ_SEED;
  return typeof pinned === "number" && Number.isFinite(pinned) ? pinned : undefined;
}

export function PodRoute() {
  const navigate = useNavigate();
  const raw = useParams().code ?? "";
  const code = normaliseCode(raw);
  const { session, forget } = usePodSession(code || undefined);
  const lobby = usePod(session);
  const decks = useDecks();
  const starDeck = useStarDeck();

  const pod = lobby.pod;
  const gameId = pod?.status === "in_game" ? pod.game_id : null;

  // Everybody in the pod -- host and guests alike -- learns the game id from
  // their own poll, so they arrive at the table together rather than the host
  // navigating and the guests waiting for a nudge.
  //
  // `replace`, because this is the transition the old no-router argument was
  // about: the pod is now `in_game` and its lobby cannot be re-entered, so the
  // history entry must stop existing rather than sit there offering to go back
  // to a room that is gone.
  useEffect(() => {
    if (!gameId) return;
    linkGame(gameId, code);
    navigate(gamePath(gameId), { replace: true });
  }, [gameId, code, navigate]);

  const leave = () => {
    lobby.leave.mutate();
    forget();
    navigate("/", { replace: true });
  };

  if (!session) return <Navigate to={joinPath(code)} replace />;

  if (lobby.error && !pod) {
    const status = lobby.error instanceof ApiError ? lobby.error.status : 0;
    return (
      <Screen variant="fade" center>
        <p className="menu__note">
          {status === 404
            ? "There is no pod with that code."
            : status === 410
              ? "That pod has closed."
              : `Could not find the pod: ${lobby.error.message}`}
        </p>
        <button type="button" className="btn btn--ghost" onClick={() => navigate("/")}>
          Back
        </button>
      </Screen>
    );
  }

  if (!pod) {
    return (
      <Screen variant="fade" center>
        <p className="menu__note">Finding the pod…</p>
      </Screen>
    );
  }

  return (
    <Screen>
      <PodLobby
        pod={pod}
        decks={decks.data ?? []}
        busy={lobby.busy}
        starting={lobby.start.isPending || pod.status !== "open"}
        error={lobby.error}
        onUpdateSeat={(body) => lobby.updateSeat.mutate(body)}
        onAdminSeat={(index, action) => lobby.adminSeat.mutate({ index, action })}
        onSetSeatDeck={(index, deckId) =>
          lobby.adminSeat.mutate({ index, action: "set_deck", deck_id: deckId })
        }
        onStart={() => lobby.start.mutate(pinnedSeed())}
        onLeave={leave}
        onDecksChanged={() => decks.refetch()}
        onStarDeck={starDeck}
      />
    </Screen>
  );
}
