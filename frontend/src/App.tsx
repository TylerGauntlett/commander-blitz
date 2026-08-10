/**
 * The four screens, and the route between them.
 *
 * `home` -> `lobby` -> `dealing` -> `table`. Still no router: a discriminated
 * union in `useState`, matching the `AnimatePresence mode="wait"` pattern the
 * two-screen version already used. A router would buy back-button navigation
 * between a lobby and a game that are both *server* state -- going "back" to a
 * pod that has already dealt is not a thing that can work, and a URL that
 * pretends otherwise is worse than no URL.
 *
 * The one exception is `?join=CODE`, which an invite link carries. It is read
 * once, at boot, and drops somebody straight into the join flow.
 */

import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useState } from "react";
import { ApiError, setPlayerToken } from "./api/client";
import type { PodView } from "./api/types";
import { Table } from "./components/game/Table";
import { DeckCatalog } from "./components/lobby/DeckCatalog";
import { DeckDossier } from "./components/lobby/DeckDossier";
import { HomeScreen } from "./components/lobby/HomeScreen";
import { PodLobby } from "./components/lobby/PodLobby";
import { ease } from "./motion/springs";
import { useUiStore } from "./state/uiStore";
import { type GameSession, useDecks, useGame } from "./state/useGame";
import { useImages } from "./state/useImages";
import {
  type PodSession,
  adoptPod,
  forgetPod,
  inviteCode,
  storedToken,
  useCreatePod,
  useJoinPod,
  usePod,
} from "./state/usePod";

type Route =
  | { kind: "home" }
  | { kind: "lobby"; pod: PodSession }
  | { kind: "dealing"; gameId: string }
  | { kind: "table"; session: GameSession };

export function App() {
  const [route, setRoute] = useState<Route>({ kind: "home" });
  // An invite link boots straight into the join flow. Read during the first
  // render rather than in an effect: an effect lands after `HomeScreen` has
  // already mounted with an empty field, and its `useState` would ignore the
  // prop arriving late. Read once, so it cannot drag somebody back to a lobby
  // they have already left.
  const [invited] = useState(inviteCode);
  const [seed, setSeed] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const [browseDossier, setBrowseDossier] = useState<string | null>(null);

  const decks = useDecks();
  const createPod = useCreatePod();
  const joinPod = useJoinPod();

  const podSession = route.kind === "lobby" ? route.pod : null;
  const lobby = usePod(podSession);

  const gameId =
    route.kind === "table"
      ? route.session.gameId
      : route.kind === "dealing"
        ? route.gameId
        : undefined;

  // Commander art has to be on screen in the lobby, before there is a game to
  // scope the map to. Unscoped on the way in, scoped once there is a game --
  // an unscoped map grows with every imported deck and a board only ever draws
  // its own ~90 cards.
  useImages(gameId);

  const game = useGame(route.kind === "table" ? route.session : null);
  const clearStaging = useUiStore((s) => s.clearStaging);
  const setError = useUiStore((s) => s.setError);

  /* -- entering a pod ------------------------------------------------- */

  const enter = useCallback((code: string, token: string) => {
    setRoute({ kind: "lobby", pod: adoptPod(code, token) });
  }, []);

  const create = useCallback(() => {
    // No name: the door does not ask for one and the server names the chair
    // after its seat. You say who you are from the plate, once there is a
    // table for it to mean anything to.
    createPod.mutate({}, { onSuccess: (made) => enter(made.pod.code, made.player_token) });
  }, [createPod, enter]);

  const join = useCallback(
    (code: string) => {
      joinPod.mutate(
        { code },
        {
          onSuccess: (joined) => enter(joined.pod.code, joined.player_token),
          onError: (caught) => {
            // A pod that already dealt is not a failure to show, it is somebody
            // who should be at the table. The server puts the game id in the
            // error detail for exactly this.
            if (caught instanceof ApiError && caught.code === "already_started") {
              const found = caught.detail?.game_id;
              const stored = storedToken(code);
              if (typeof found === "string" && stored) {
                setPlayerToken(stored);
                setRoute({ kind: "dealing", gameId: found });
              }
            }
          },
        },
      );
    },
    [joinPod, enter],
  );

  /* -- leaving one --------------------------------------------------- */

  const leave = useCallback(() => {
    if (route.kind === "lobby") {
      lobby.leave.mutate();
      forgetPod(route.pod.code);
    }
    setPlayerToken(null);
    setRoute({ kind: "home" });
    clearStaging();
    setError(null);
  }, [route, lobby.leave, clearStaging, setError]);

  /* -- the deal ------------------------------------------------------- */

  // Everybody in the pod -- host and guests alike -- learns the game id from
  // their own poll of the pod, so they arrive at the table together rather than
  // the host navigating and the guests waiting for a nudge.
  const podView: PodView | null = lobby.pod;
  useEffect(() => {
    if (route.kind !== "lobby") return;
    if (podView?.status === "in_game" && podView.game_id) {
      setRoute({ kind: "dealing", gameId: podView.game_id });
    }
  }, [route.kind, podView?.status, podView?.game_id]);

  // `dealing` resolves the moment the first state fetch lands: that response is
  // what carries this client's *table* seat, which a pod seat does not imply.
  const dealingGame = useGame(
    route.kind === "dealing" ? { gameId: route.gameId, seat: null } : null,
  );
  useEffect(() => {
    if (route.kind !== "dealing") return;
    const seat = dealingGame.yourSeat;
    if (seat !== null) setRoute({ kind: "table", session: { gameId: route.gameId, seat } });
  }, [route, dealingGame.yourSeat]);

  const quit = useCallback(() => {
    setPlayerToken(null);
    setRoute({ kind: "home" });
    clearStaging();
    setError(null);
  }, [clearStaging, setError]);

  /* -- render --------------------------------------------------------- */

  const deckList = decks.data ?? [];

  return (
    <>
      <AnimatePresence mode="wait">
        {route.kind === "table" && game.state ? (
          <motion.div
            key="table"
            className="screen"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.02 }}
            transition={ease}
          >
            <Table
              session={route.session}
              game={game}
              state={game.state}
              onQuit={quit}
              onRematch={quit}
            />
          </motion.div>
        ) : route.kind === "table" || route.kind === "dealing" ? (
          <motion.div
            key="dealing"
            className="screen screen--center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            data-testid="dealing"
          >
            <p className="menu__note">
              {dealingGame.error
                ? `Could not load the game: ${dealingGame.error.message}`
                : "Dealing…"}
            </p>
            {dealingGame.error && (
              <button type="button" className="btn btn--ghost" onClick={quit}>
                Back
              </button>
            )}
          </motion.div>
        ) : route.kind === "lobby" && lobby.pod ? (
          <motion.div
            key="lobby"
            className="screen"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={ease}
          >
            <PodLobby
              pod={lobby.pod}
              decks={deckList}
              busy={lobby.busy}
              starting={lobby.start.isPending || lobby.pod.status !== "open"}
              error={lobby.error}
              seed={seed}
              onSeedChange={setSeed}
              onUpdateSeat={(body) => lobby.updateSeat.mutate(body)}
              onAdminSeat={(index, action) => lobby.adminSeat.mutate({ index, action })}
              onSetSeatDeck={(index, deckId) =>
                lobby.adminSeat.mutate({ index, action: "set_deck", deck_id: deckId })
              }
              onStart={() => {
                // An empty field means "surprise me", which is a *different*
                // game every deal -- so it must reach the server as no seed at
                // all rather than as 0, which is a perfectly good seed.
                const parsed = Number(seed.trim());
                lobby.start.mutate(
                  seed.trim() !== "" && Number.isFinite(parsed) ? parsed : undefined,
                );
              }}
              onLeave={leave}
              onDecksChanged={() => decks.refetch()}
            />
          </motion.div>
        ) : route.kind === "lobby" ? (
          <motion.div
            key="joining"
            className="screen screen--center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <p className="menu__note">Finding the pod…</p>
          </motion.div>
        ) : (
          <motion.div
            key="home"
            className="screen screen--center"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={ease}
          >
            <HomeScreen
              initialCode={invited ?? ""}
              deckCount={deckList.length}
              onCreate={create}
              onJoin={join}
              busy={createPod.isPending || joinPod.isPending}
              error={
                (createPod.error as Error | null) ??
                (joinPod.error as Error | null) ??
                (decks.error as Error | null)
              }
              onBrowse={() => setBrowsing(true)}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Browsing from the front door: the same catalogue, choosing for nobody.
          Somebody deciding whether this is worth installing should be able to
          look at the decks before committing to a pod. */}
      {browsing && (
        <DeckCatalog
          decks={deckList}
          forSeat={null}
          forWhom="Browsing the catalogue"
          chosen={null}
          onPick={(deckId) => setBrowseDossier(deckId)}
          onDossier={(deckId) => setBrowseDossier(deckId)}
          onClose={() => setBrowsing(false)}
          onImported={() => decks.refetch()}
        />
      )}
      {browseDossier && (
        <DeckDossier
          deckId={browseDossier}
          canTake={false}
          onTake={() => undefined}
          onClose={() => setBrowseDossier(null)}
        />
      )}
    </>
  );
}
