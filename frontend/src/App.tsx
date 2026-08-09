/** Session gate: the setup screen, or the table. */

import { AnimatePresence, motion } from "motion/react";
import { useCallback, useState } from "react";
import type { SeatConfig } from "./api/types";
import { Table } from "./components/game/Table";
import { NewGameScreen } from "./components/menu/NewGameScreen";
import { ease } from "./motion/springs";
import { useUiStore } from "./state/uiStore";
import { type GameSession, useDecks, useGame, useNewGame } from "./state/useGame";
import { useImages } from "./state/useImages";

export function App() {
  const [session, setSession] = useState<GameSession | null>(null);
  // Kept so "Rematch" can deal the same matchup without going back to setup.
  const [lastSetup, setLastSetup] = useState<{ seats: SeatConfig[]; seed?: number } | null>(
    null,
  );

  const decks = useDecks();
  const newGame = useNewGame();
  // One fetch per game. Scoped to it once there is one, because an unscoped map
  // grows with every imported deck and a board only ever draws its own ~90 cards.
  useImages(session?.gameId);
  const game = useGame(session);
  const clearStaging = useUiStore((s) => s.clearStaging);
  const setError = useUiStore((s) => s.setError);

  const start = useCallback(
    (seats: SeatConfig[], seed?: number) => {
      setLastSetup({ seats, seed });
      newGame.mutate(
        { seats, seed },
        {
          onSuccess: (created) => {
            clearStaging();
            setError(null);
            setSession({ gameId: created.game_id, seat: created.your_seat });
          },
        },
      );
    },
    [newGame, clearStaging, setError],
  );

  const quit = useCallback(() => {
    setSession(null);
    clearStaging();
    setError(null);
  }, [clearStaging, setError]);

  const rematch = useCallback(() => {
    if (!lastSetup) {
      quit();
      return;
    }
    setSession(null);
    // A fresh seed, or the same matchup replays identically.
    start(lastSetup.seats, undefined);
  }, [lastSetup, quit, start]);

  const showTable = session !== null && game.state !== null;

  return (
    <AnimatePresence mode="wait">
      {showTable && session && game.state ? (
        <motion.div
          key="table"
          className="screen"
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.02 }}
          transition={ease}
        >
          <Table
            session={session}
            game={game}
            state={game.state}
            onQuit={quit}
            onRematch={rematch}
          />
        </motion.div>
      ) : session !== null ? (
        <motion.div
          key="dealing"
          className="screen screen--center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <p className="menu__note">
            {game.error ? `Could not load the game: ${game.error.message}` : "Dealing…"}
          </p>
          {game.error && (
            <button type="button" className="btn btn--ghost" onClick={quit}>
              Back
            </button>
          )}
        </motion.div>
      ) : (
        <motion.div
          key="menu"
          className="screen screen--center"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={ease}
        >
          <NewGameScreen
            decks={decks.data ?? []}
            loading={decks.isLoading}
            error={(decks.error as Error | null) ?? (newGame.error as Error | null)}
            onStart={start}
            starting={newGame.isPending}
            onDecksChanged={() => decks.refetch()}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
