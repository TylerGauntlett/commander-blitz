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
import { decisionPrompt, thinkingLabel } from "../../logic/labels";
import { bouncy, ease } from "../../motion/springs";
import { type Speed, useUiStore } from "../../state/uiStore";
import { SymbolText } from "./SymbolText";

/** Actions worth a big button; everything else goes in the overflow row. */
const PRIMARY = new Set(["pass", "keep", "mulligan", "yes", "no", "finish_declaration"]);

const SPEEDS: Speed[] = ["cinematic", "fast", "instant"];

const SPEED_LABELS: Record<Speed, string> = {
  cinematic: "0.5x",
  fast: "1x",
  instant: "≫",
};

const SPEED_TITLES: Record<Speed, string> = {
  cinematic: "Half speed — watch every beat",
  fast: "Normal speed",
  instant: "Skip narration entirely",
};

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
  /**
   * Another surface owns the current decision, so the bar shows only its tools.
   *
   * It already renders no *buttons* in that case -- `Table` passes an empty
   * action list -- but it kept printing the prompt, so "Declare blockers"
   * appeared twice in the same rail once combat moved up here.
   */
  standDown?: boolean;
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
  standDown = false,
}: Props) {
  const speed = useUiStore((s) => s.speed);
  const setSpeed = useUiStore((s) => s.setSpeed);
  const muted = useUiStore((s) => s.muted);
  const toggleMuted = useUiStore((s) => s.toggleMuted);

  const disabled = busy || narrating;
  const primary = actions.filter((a) => PRIMARY.has(a.kind));
  const rest = actions.filter((a) => !PRIMARY.has(a.kind));

  return (
    <div className={standDown ? "bar bar--quiet" : "bar"} data-testid="action-bar">
      {!standDown && (
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
                {narrating ? "Playing it out" : thinkingLabel(state)}
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      )}

      {!standDown && (
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
                  {/* Activation costs live in these labels ("{2}, {T}, Sacrifice:
                    ..."), and they were the last place mana stayed raw text. */}
                  <SymbolText text={action.label} />
                </motion.button>
              ))}
            </div>
          )}

          {actions.length === 0 && !state.game_over && (
            <span className="bar__idle">Waiting&hellip;</span>
          )}
        </div>
      )}

      <div className="bar__tools">
        {narrating && (
          <button type="button" className="btn btn--ghost" onClick={onSkip}>
            Skip &raquo;
          </button>
        )}
        {/*
          The labels name the multiplier honestly. They used to read 1x/2x while
          the underlying divisors were 1 and 2, so "1x" was the *slowest* thing
          on offer and there was no way to ask for less than that -- which is
          what "the game moves too quickly" was really about.
        */}
        <fieldset className="speed">
          <legend className="visually-hidden">Animation speed</legend>
          {SPEEDS.map((option) => (
            <button
              type="button"
              key={option}
              className={option === speed ? "speed__btn speed__btn--on" : "speed__btn"}
              data-speed={option}
              onClick={() => setSpeed(option)}
              title={SPEED_TITLES[option]}
            >
              {SPEED_LABELS[option]}
            </button>
          ))}
        </fieldset>
        <button
          type="button"
          className={muted ? "btn btn--ghost" : "btn btn--ghost btn--on"}
          onClick={toggleMuted}
          aria-pressed={!muted}
          data-testid="mute"
          title={muted ? "Sound off" : "Sound on"}
        >
          {muted ? "🔇" : "🔊"}
        </button>
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
