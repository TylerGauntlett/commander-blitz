/**
 * Every decision that is not priority and not a combat declaration.
 *
 * Mulligans, discarding to hand size, modal spells, "you may", choosing
 * players, choosing objects, commander zone changes -- the engine expresses all
 * of them through the same `pending` shape, so one generic dialog covers them
 * all rather than seven bespoke ones.
 *
 * The part that matters for feel: when an option refers to an object, it is
 * drawn as an actual card. Choosing what to sacrifice should look like looking
 * at your board, not like reading a dropdown.
 *
 * That worked only for cards in a zone the client could see. Search, scry,
 * surveil and mulligan-bottom all name cards in a *library*, which `player_view`
 * sends as a count, so `findCard` came back null and the whole prompt collapsed
 * to a row of names with no way to tell what you were choosing between. The
 * server now attaches the face to the option itself (serialize._pending), and
 * that is what this prefers.
 */

import { AnimatePresence, motion } from "motion/react";
import type { GameView, LegalAction } from "../../api/types";
import { actionAttrs } from "../../input/stops";
import { findCard } from "../../logic/zoneGrouping";
import { bouncy, ease } from "../../motion/springs";
import { StaticCard } from "./Card";

/** Decisions that have their own richer surface elsewhere. */
const HANDLED_ELSEWHERE = new Set([
  "priority",
  "declare_attackers",
  "declare_blockers",
  // The rail draws X as a stepper. This set is a *denylist*, so a new kind
  // is modal by default and forgetting this line would silently move the
  // question into the centre of the screen and stand the panel down.
  "choose_x",
]);

/**
 * True when this dialog owns the current decision.
 *
 * The action bar reads this and stands down, so a decision's buttons exist
 * exactly once in the document. Rendering them in both places left a row of
 * identical buttons behind the modal backdrop -- unclickable, and ambiguous to
 * anything selecting by action id.
 */
export function isModalDecision(state: GameView): boolean {
  const pending = state.pending;
  return (
    pending !== null &&
    pending.player === state.seat &&
    !state.game_over &&
    !HANDLED_ELSEWHERE.has(pending.kind)
  );
}

interface Props {
  state: GameView;
  actions: LegalAction[];
  onAct: (actionId: string) => void;
  disabled: boolean;
}

export function PromptDialog({ state, actions, onAct, disabled }: Props) {
  const pending = state.pending;
  const open = isModalDecision(state) && actions.length > 0;

  return (
    <AnimatePresence>
      {open && pending && (
        <motion.div
          className="prompt-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={ease}
        >
          <motion.div
            className="prompt"
            role="dialog"
            aria-modal="true"
            data-modal-root
            aria-label={pending.prompt || pending.kind}
            data-testid="prompt-dialog"
            data-decision-kind={pending.kind}
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={bouncy}
          >
            <header className="prompt__head">
              <h2 className="prompt__title">{pending.prompt || pending.kind}</h2>
              {pending.max_count > 1 && (
                <p className="prompt__hint">
                  Choose{" "}
                  {pending.min_count === pending.max_count
                    ? pending.max_count
                    : `${pending.min_count}–${pending.max_count}`}
                  {pending.selected.length > 0 && ` · ${pending.selected.length} chosen`}
                </p>
              )}
            </header>

            <div className="prompt__options">
              {actions.map((action) => {
                // `choice` is the index into `pending.options`, so the face the
                // server attached is reachable directly. `findCard` stays as the
                // fallback for any action that names an object without being one
                // of the enumerated choices.
                const option =
                  action.choice === null ? undefined : pending.options[action.choice];
                const ref = option?.ref ?? action.targets[0];
                const card =
                  option?.card ??
                  (ref && ref.kind === "object" ? findCard(state, ref.id) : null);
                const isPlayerRef = ref?.kind === "player";
                const playerName = isPlayerRef
                  ? (state.players[ref.id]?.name ?? `P${ref.id}`)
                  : null;

                return (
                  <motion.button
                    type="button"
                    key={action.id}
                    className={card ? "opt opt--card" : "opt"}
                    {...actionAttrs(action.id)}
                    data-action-kind={action.kind}
                    disabled={disabled}
                    onClick={() => onAct(action.id)}
                    whileHover={disabled ? undefined : { y: -4, scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    transition={bouncy}
                  >
                    {card ? (
                      <>
                        <StaticCard card={card} variant="detail" />
                        <span className="opt__caption">{action.label}</span>
                      </>
                    ) : (
                      <span className="opt__label">
                        {playerName ? `${action.label} (${playerName})` : action.label}
                      </span>
                    )}
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
