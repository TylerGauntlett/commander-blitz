import { useState } from "react";
import type { SeatConfig } from "./api/types";
import { GameBoard } from "./components/GameBoard";
import { NewGameDialog } from "./components/NewGameDialog";
import { type GameSession, useGame, useNewGame } from "./state/useGame";

export function App() {
  const [session, setSession] = useState<GameSession | null>(null);
  const newGame = useNewGame();
  const game = useGame(session);

  const start = (seats: SeatConfig[], seed?: number) => {
    newGame.mutate(
      { seats, seed },
      {
        onSuccess: (created) =>
          setSession({ gameId: created.game_id, seat: created.your_seat }),
      },
    );
  };

  if (!session) {
    return <NewGameDialog busy={newGame.isPending} onStart={start} />;
  }
  if (game.isLoading || !game.state) {
    return <div className="dialog">Shuffling...</div>;
  }
  if (game.error) {
    return (
      <div className="dialog dialog--error">
        <h1>Lost the game</h1>
        <p>{game.error.message}</p>
        <button type="button" className="action-button" onClick={() => setSession(null)}>
          Back
        </button>
      </div>
    );
  }

  const busy = game.act.isPending || game.declare.isPending || game.undo.isPending;

  return (
    <GameBoard
      state={game.state}
      actions={game.actions}
      events={game.events}
      busy={busy}
      onAct={(action) => game.act.mutate(action.id)}
      onDeclare={(kind, pairs) => game.declare.mutate({ kind, pairs })}
      onUndo={() => game.undo.mutate()}
      onNewGame={() => setSession(null)}
    />
  );
}
