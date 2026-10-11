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
import { PHASES, STEP_ORDER, stepShort } from "../../logic/labels";
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
      {/*
        The big number is the *round*, not the engine's turn counter.

        `state.turn` counts player-turns, which is what the rules need but not
        what anyone means by "my second turn": in a two-player game your second
        turn used to read 3, and in a pod it climbed four times a lap. The rules
        counter stays available in the tooltip, since it is the one that decides
        summoning sickness and the turn cap.
      */}
      <div
        className="track__turn"
        data-testid="turn-counter"
        data-round={state.round}
        data-turn={state.turn}
        data-hint={`Round ${state.round} — player-turn ${state.turn}`}
      >
        <span className="track__turn-n tabular">T{state.round}</span>
        <span className="track__turn-round">round {state.round}</span>
      </div>
      {/*
        Five phases, and only the live one opens into its steps.

        Thirteen equal ticks was thirteen things to read, twelve of which are
        never the answer to "where are we". Every step label stays in the DOM
        even while its phase is collapsed -- the closed phases are hidden with
        `display: none`, not unmounted, so the thirteen labels
        `e2e/smoke.spec.ts` counts are all still present and non-empty.
      */}
      <ol className="track__steps">
        {PHASES.map((phase) => {
          const indices = phase.steps.map((step) =>
            STEP_ORDER.indexOf(step as (typeof STEP_ORDER)[number]),
          );
          const isNow = indices.includes(currentIndex);
          const isPast = Math.max(...indices) < currentIndex;
          const tone = isNow ? "now" : isPast ? "past" : "future";

          return (
            <li key={phase.name} className={`ph ph--${tone}`} data-phase={phase.name}>
              <span className="ph__name">{phase.name}</span>
              <ol className="ph__steps">
                {phase.steps.map((step) => {
                  const index = STEP_ORDER.indexOf(step as (typeof STEP_ORDER)[number]);
                  const stepTone =
                    index === currentIndex ? "now" : index < currentIndex ? "past" : "future";
                  return (
                    <li key={step} className={`track__step track__step--${stepTone}`}>
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
            </li>
          );
        })}
      </ol>

      {/* Whose turn it is, at the far end of the ribbon. It is the one piece of
          state you re-check between every action, so it gets a chip of its own
          rather than sitting as a word beside the round counter. */}
      {/*
        The two chips share the ribbon's third column.

        `.track` is a three-column grid, so a fourth child auto-places into a
        SECOND ROW -- which is what the priority pill did on its first draft,
        landing at the far left under the ribbon, 40px from anything it relates
        to. Grouping them is also right on the merits: they are two halves of
        one question.
      */}
      <span className="track__end">
        <span className={yourTurn ? "track__who track__who--you" : "track__who"}>
          {yourTurn ? "Your turn" : `${active.name}'s turn`}
        </span>

        {/*
        WHOSE TURN IT IS AND WHO HOLDS PRIORITY ARE TWO DIFFERENT FACTS.
        
        The ribbon ran them together into one chip, which is wrong in the case
        that matters most: on somebody else's turn, holding your own priority is
        the whole of a Commander player's job. the handheld-board round's
        `02-blockers` was the file that proved it -- Edgar's turn, your decision,
        so the seat wears the priority tick and not the active ring.

        Drawn only when the two DISAGREE. On your own turn with your own
        priority it would be a second chip saying the same thing, and the strip
        is 34px on a handheld.
      */}
        {!yourTurn && state.priority_player === state.seat && (
          <span className="track__pri" data-testid="priority-pill">
            You have priority
          </span>
        )}
      </span>
    </div>
  );
}
