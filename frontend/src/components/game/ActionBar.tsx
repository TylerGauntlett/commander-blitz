/**
 * Every legal action, as a button.
 *
 * This is a load-bearing invariant, not a fallback. Dragging and clicking are
 * ergonomic shortcuts for picking an action out of this list; the whole game
 * stays playable, testable and keyboard-reachable without either of them. When
 * a gesture and this bar disagree, the bar is right.
 */

import { AnimatePresence, motion } from "motion/react";
import type { GameView, LegalAction } from "../../api/types";
import { decisionPrompt } from "../../logic/labels";
import { bouncy, ease } from "../../motion/springs";
import { type Speed, useUiStore } from "../../state/uiStore";

/** Actions worth a big button; everything else goes in the overflow row. */
const PRIMARY = new Set(["pass", "keep", "mulligan", "yes", "no", "finish_declaration"]);

const SPEEDS: Speed[] = ["cinematic", "fast", "instant"];

interface Props {
  state: GameView;
  actions: LegalAction[];
  onAct: (actionId: string) => void;
  onUndo: () => void;
  onQuit: () => void;
  /** Narration is playing: gate input rather than let a click land mid-flight. */
  narrating: boolean;
  onSkip: () => void;
  busy: boolean;
  aiThinking: boolean;
  onToggleFullControl: (value: boolean) => void;
}

export function ActionBar({
  state,
  actions,
  onAct,
  onUndo,
  onQuit,
  narrating,
  onSkip,
  busy,
  aiThinking,
  onToggleFullControl,
}: Props) {
  const speed = useUiStore((s) => s.speed);
  const setSpeed = useUiStore((s) => s.setSpeed);

  const disabled = busy || narrating;
  const primary = actions.filter((a) => PRIMARY.has(a.kind));
  const rest = actions.filter((a) => !PRIMARY.has(a.kind));

  return (
    <div className="bar" data-testid="action-bar">
      <div className="bar__prompt">
        <span className="bar__prompt-text" data-testid="prompt">
          {decisionPrompt(state)}
        </span>
        <AnimatePresence>
          {(narrating || aiThinking) && (
            <motion.span
              className="bar__thinking"
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={ease}
            >
              <span className="bar__dot" />
              {narrating ? "Playing it out" : "Opponent thinking"}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <div className="bar__actions" data-testid="action-list">
        {primary.map((action) => (
          <motion.button
            type="button"
            key={action.id}
            className="btn btn--primary"
            data-action-id={action.id}
            data-action-kind={action.kind}
            disabled={disabled}
            onClick={() => onAct(action.id)}
            whileHover={disabled ? undefined : { y: -2, scale: 1.03 }}
            whileTap={{ scale: 0.96 }}
            transition={bouncy}
          >
            {action.label}
          </motion.button>
        ))}

        {rest.length > 0 && (
          <div className="bar__overflow" data-testid="action-overflow">
            {rest.map((action) => (
              <motion.button
                type="button"
                key={action.id}
                className="btn btn--ghost"
                data-action-id={action.id}
                data-action-kind={action.kind}
                disabled={disabled}
                onClick={() => onAct(action.id)}
                whileHover={disabled ? undefined : { y: -1 }}
                whileTap={{ scale: 0.97 }}
                transition={bouncy}
              >
                {action.label}
              </motion.button>
            ))}
          </div>
        )}

        {actions.length === 0 && !state.game_over && (
          <span className="bar__idle">Waiting&hellip;</span>
        )}
      </div>

      <div className="bar__tools">
        {narrating && (
          <button type="button" className="btn btn--ghost" onClick={onSkip}>
            Skip &raquo;
          </button>
        )}
        <fieldset className="speed">
          <legend className="visually-hidden">Animation speed</legend>
          {SPEEDS.map((option) => (
            <button
              type="button"
              key={option}
              className={option === speed ? "speed__btn speed__btn--on" : "speed__btn"}
              onClick={() => setSpeed(option)}
              title={`Animation speed: ${option}`}
            >
              {option === "cinematic" ? "1x" : option === "fast" ? "2x" : "≫"}
            </button>
          ))}
        </fieldset>
        <button
          type="button"
          className={state.full_control ? "btn btn--ghost btn--on" : "btn btn--ghost"}
          onClick={() => onToggleFullControl(!state.full_control)}
          disabled={busy}
          aria-pressed={state.full_control}
          data-testid="full-control"
          title={
            state.full_control
              ? "Full control: stopping at every priority window"
              : "Stopping only where you have something to respond to. Turn on for every window."
          }
        >
          {state.full_control ? "Full control" : "Auto-pass"}
        </button>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={onUndo}
          disabled={busy}
          title="Undo your last action (U)"
        >
          Undo
        </button>
        <button type="button" className="btn btn--ghost" onClick={onQuit}>
          Quit
        </button>
      </div>
    </div>
  );
}
