/** The result, with why each player is out of the game. */

import { AnimatePresence, motion } from "motion/react";
import type { GameView } from "../../api/types";
import { stopId } from "../../input/stops";
import { lossReason } from "../../logic/labels";
import { bouncy, ease } from "../../motion/springs";

interface Props {
  state: GameView;
  onRematch: () => void;
  onQuit: () => void;
}

export function GameOverScreen({ state, onRematch, onQuit }: Props) {
  const won = state.winners.includes(state.seat);
  const draw = state.winners.length === 0;
  const headline = draw ? "Draw" : won ? "Victory" : "Defeat";

  return (
    <AnimatePresence>
      {state.game_over && (
        <motion.div
          className="over-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={ease}
        >
          <motion.div
            className={`over over--${draw ? "draw" : won ? "win" : "loss"}`}
            /*
              A full-screen surface that owns the whole screen, so it owns the
              ring too -- and it was the case the design round found first: the
              game-over screen opened with the cursor still on an opponent's
              seat, because the board comes first in the markup. It had no
              dialog role either, which is the same omission said twice.
            */
            role="dialog"
            aria-modal="true"
            aria-label={headline}
            data-modal-root
            data-testid="game-over"
            data-result={draw ? "draw" : won ? "win" : "loss"}
            initial={{ opacity: 0, y: 40, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ ...bouncy, delay: 0.15 }}
          >
            <motion.h1
              className="over__headline"
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ ...bouncy, delay: 0.3 }}
            >
              {headline}
            </motion.h1>
            <p className="over__sub">
              {draw
                ? state.result || "Nobody won."
                : `${state.winners.map((pid) => state.players[pid]?.name).join(", ")} wins on turn ${state.round}.`}
            </p>

            <ul className="over__players">
              {state.players.map((player) => (
                <li
                  key={player.pid}
                  className={
                    state.winners.includes(player.pid)
                      ? "over__player over__player--won"
                      : "over__player"
                  }
                >
                  <span className="over__name">{player.name}</span>
                  <span className="over__life tabular">{player.life}</span>
                  <span className="over__why">
                    {state.winners.includes(player.pid)
                      ? "survived"
                      : lossReason(player.loss_reason) || "still standing"}
                  </span>
                </li>
              ))}
            </ul>

            <div className="over__buttons">
              <button
                type="button"
                className="btn btn--primary"
                data-stop={stopId.tool("rematch")}
                onClick={onRematch}
              >
                Rematch
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                data-stop={stopId.tool("quit-over")}
                onClick={onQuit}
              >
                Main menu
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
