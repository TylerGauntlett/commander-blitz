/**
 * Where we are in the turn.
 *
 * The engine walks thirteen steps and auto-passes any decision with only one
 * legal action, so steps go by fast and invisibly. Laying them out as a track
 * with the current one lit is the difference between "something happened" and
 * "we are in declare blockers".
 */

import { motion } from "motion/react";
import type { GameView } from "../../api/types";
import { STEP_ORDER, stepShort } from "../../logic/labels";
import { settle } from "../../motion/springs";

interface Props {
  state: GameView;
}

export function PhaseTrack({ state }: Props) {
  const found = STEP_ORDER.indexOf(state.step as (typeof STEP_ORDER)[number]);
  if (found === -1 && import.meta.env.DEV) {
    // Silently marking every step "future" looks exactly like a track that
    // never advances, so say so rather than degrade into the old bug.
    console.warn(`PhaseTrack: unknown step ${state.step}`);
  }
  const currentIndex = found;
  const active = state.players[state.active_player];
  const yourTurn = state.active_player === state.seat;

  return (
    <div className="track" data-testid="phase-track">
      <div className="track__turn">
        <span className="track__turn-n tabular">T{state.turn}</span>
        <span className={yourTurn ? "track__who track__who--you" : "track__who"}>
          {yourTurn ? "Your turn" : `${active.name}'s turn`}
        </span>
      </div>
      <ol className="track__steps">
        {STEP_ORDER.map((step, index) => {
          const state_ =
            index === currentIndex ? "now" : index < currentIndex ? "past" : "future";
          return (
            <li key={step} className={`track__step track__step--${state_}`}>
              {index === currentIndex && (
                <motion.span
                  className="track__marker"
                  layoutId="track-marker"
                  transition={settle}
                />
              )}
              <span className="track__step-label">{stepShort(step)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
