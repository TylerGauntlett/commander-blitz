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
 *
 * THE ONE SHAPE A ROW OF BUTTONS CANNOT CARRY is a decision with hundreds of
 * options in it. `op_choose_type` asks for a creature type by listing every
 * subtype in the pool, and four hundred buttons is not a choice -- see
 * `ChoiceCombo`, which this hands those decisions to.
 */

import { AnimatePresence, motion, usePresence } from "motion/react";
import { useEffect, useRef } from "react";
import type { CardView, GameView, LegalAction } from "../../api/types";
import { actionAttrs } from "../../input/stops";
import { mulliganPhase } from "../../logic/openingHand";
import { COMBO_MIN } from "../../logic/promptFilter";
import { findCard } from "../../logic/zoneGrouping";
import { bouncy, ease } from "../../motion/springs";
import { StaticCard } from "./Card";
import { type Choice, ChoiceCombo } from "./ChoiceCombo";

/** Decisions that have their own richer surface elsewhere. */
const HANDLED_ELSEWHERE = new Set([
  "priority",
  "declare_attackers",
  "declare_blockers",
  // The rail draws X as a stepper. This set is a *denylist*, so a new kind
  // is modal by default and forgetting this line would silently move the
  // question into the centre of the screen and stand the panel down.
  "choose_x",
  // `OpeningHand` draws the whole screen. Its second half -- "put N on the
  // bottom" -- is a `choose_objects`, which cannot be named here because every
  // other `choose_objects` still belongs to this dialog; `mulliganPhase` is
  // what tells them apart, and `ownsDecision` below is what keeps the two
  // predicates from disagreeing.
  "mulligan",
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
    !HANDLED_ELSEWHERE.has(pending.kind) &&
    mulliganPhase(state) === null
  );
}

/**
 * Whether ANY full-screen surface owns the decision.
 *
 * `ActionPanel` reads this and stands down, so a decision's buttons exist
 * exactly once in the document. It has to be a wider question than
 * `isModalDecision`: the moment `mulligan` joined the denylist above, this
 * dialog stopped opening for it -- and had `Table` kept asking
 * `isModalDecision`, the panel would have stopped standing down at the same
 * time and rendered `keep` and `mulligan` a second time behind the new screen.
 * Two ids, one decision, and `expectUniqueActionIds` failing across a whole
 * game.
 */
export function ownsDecision(state: GameView): boolean {
  return isModalDecision(state) || mulliganPhase(state) !== null;
}

interface Props {
  state: GameView;
  actions: LegalAction[];
  onAct: (actionId: string) => void;
  disabled: boolean;
}

/** One option, with whatever the server gave us to draw it as. */
interface Row {
  action: LegalAction;
  card: CardView | null;
  playerName: string | null;
  /** The label the option itself carries, when it is not the action's own. */
  optionLabel: string | null;
}

/**
 * The options, resolved once.
 *
 * `choice` is the index into `pending.options`, so the face the server attached
 * is reachable directly. `findCard` stays as the fallback for any action that
 * names an object without being one of the enumerated choices.
 */
function rowsFor(state: GameView, actions: LegalAction[]): Row[] {
  const pending = state.pending;
  return actions.map((action) => {
    const option =
      pending === null || action.choice === null ? undefined : pending.options[action.choice];
    const ref = option?.ref ?? action.targets[0];
    const card =
      option?.card ?? (ref && ref.kind === "object" ? findCard(state, ref.id) : null);
    const playerName =
      ref?.kind === "player" ? (state.players[ref.id]?.name ?? `P${ref.id}`) : null;
    return {
      action,
      card,
      playerName,
      optionLabel: option && option.label !== action.label ? option.label : null,
    };
  });
}

/**
 * Whether this decision is a list to search rather than a row to read.
 *
 * Two conditions, and the second is the one that keeps the change small: a
 * decision whose options are CARDS keeps the grid of faces however many there
 * are, because a card face is not a combobox row and looking at your board is
 * the whole reason those are drawn as cards. Only walls of bare labels move.
 */
function isWall(rows: Row[]): boolean {
  return rows.length > COMBO_MIN && rows.every((row) => row.card === null);
}

function choiceOf({ action, optionLabel }: Row): Choice {
  return {
    id: action.id,
    kind: action.kind,
    label: action.label,
    text: optionLabel ? `${action.label} ${optionLabel}` : action.label,
  };
}

/**
 * The enumerated options, and everything else.
 *
 * `Done` is the everything else, and it is why this split exists: a decision
 * that takes several picks sends it alongside the options, and dropping it into
 * an alphabetical list of two hundred creature types would make finishing look
 * like one more type to choose. `choice` is the engine's own distinction --
 * it is the index into `pending.options` -- so nothing here has to guess.
 */
function partition(rows: Row[]): { options: Row[]; extras: Row[] } {
  return {
    options: rows.filter((row) => row.action.choice !== null),
    extras: rows.filter((row) => row.action.choice === null),
  };
}

export function PromptDialog({ state, actions, onAct, disabled }: Props) {
  const pending = state.pending;
  const open = isModalDecision(state) && actions.length > 0;
  // Only while it is up: `findCard` walks the zones per action, and `Table`
  // re-renders on every engine push with the whole priority action list in
  // hand. Resolving faces for a dialog nobody can see is work per push for
  // nothing.
  const rows = open ? rowsFor(state, actions) : [];

  return (
    <AnimatePresence>
      {open && pending && (
        <PromptSurface pending={pending} rows={rows} onAct={onAct} disabled={disabled} />
      )}
    </AnimatePresence>
  );
}

interface SurfaceProps {
  pending: NonNullable<GameView["pending"]>;
  rows: Row[];
  onAct: (actionId: string) => void;
  disabled: boolean;
}

/**
 * How long a leaving dialog stays in the DOM: enough for `bouncy` to settle
 * the slide, not a frame more. See `PromptSurface` for why this is a number.
 */
const EXIT_MS = 320;

/**
 * The dialog itself: a child of `AnimatePresence`, so it can tell when it is
 * leaving.
 *
 * `usePresence` only answers from inside the presence boundary, which is why
 * this is not inlined in `PromptDialog`. `present` is false for exactly the
 * exit animation, and that window matters: the dialog is still in the DOM,
 * still `[data-modal-root]`, and still carries its option buttons while it
 * fades. `stopRoot` (`input/stops.ts`) reads
 * `[data-modal-root]:not([data-closing])` so the ring is not trapped in a
 * surface that is going away -- `OpeningHand` has set the attribute since it
 * was written, and this dialog satisfied the guard only by never having been
 * measured mid-exit. The e2e helpers that clear a board of prompts read the
 * same selector, and one that did not clicked an option in an exiting dialog,
 * waited for it to come back, and timed out six minutes later against a board
 * with no dialog on it at all.
 *
 * AND IT LEAVES ON A CLOCK, NOT ON AN ANIMATION -- the same shape as the
 * opening hand's `Stage`, for the reason given there: `AnimatePresence` waits
 * for every `exit` inside the child to report complete, and an opacity exit
 * started while the entrance was still in flight was measured never to. This
 * dialog is answered fast in every e2e spec, so it carries no `exit` at all:
 * the backdrop and the box `animate` toward their closed look, which needs
 * nobody's completion, and `safeToRemove` runs on a timer. A lost fade means
 * a cut, never a dialog left over the board.
 */
function PromptSurface({ pending, rows, onAct, disabled }: SurfaceProps) {
  const [present, safeToRemove] = usePresence();
  // Through a ref, and keyed on `present` ALONE: `safeToRemove` is rebuilt on
  // every render of the presence boundary, and a timer restarted on each state
  // push never fired while the game was moving. `OpeningHand` says the same.
  const removeRef = useRef(safeToRemove);
  removeRef.current = safeToRemove;
  useEffect(() => {
    if (present) return;
    const timer = setTimeout(() => removeRef.current?.(), EXIT_MS);
    return () => clearTimeout(timer);
  }, [present]);
  const { options, extras } = partition(rows);

  return (
    <motion.div
      className="prompt-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: present ? 1 : 0 }}
      transition={ease}
    >
      <motion.div
        className="prompt"
        role="dialog"
        aria-modal="true"
        data-modal-root
        data-closing={present ? undefined : true}
        aria-label={pending.prompt || pending.kind}
        data-testid="prompt-dialog"
        data-decision-kind={pending.kind}
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={present ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: 12, scale: 0.98 }}
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

        {isWall(options) ? (
          /*
           * Keyed by the decision, so a new question arrives with an empty
           * field and the first row highlighted. Without it the query typed
           * at the last prompt would still be narrowing this one.
           */
          <ChoiceCombo
            key={`${pending.kind}:${pending.prompt}`}
            choices={options.map(choiceOf)}
            extras={extras.map(choiceOf)}
            onAct={onAct}
            disabled={disabled}
          />
        ) : (
          <div className="prompt__options">
            {rows.map(({ action, card, playerName }) => (
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
                    {/* `onSurface`: the backdrop fades as one thing; see `StaticCard`. */}
                    <StaticCard card={card} variant="detail" onSurface />
                    <span className="opt__caption">{action.label}</span>
                  </>
                ) : (
                  <span className="opt__label">
                    {playerName ? `${action.label} (${playerName})` : action.label}
                  </span>
                )}
              </motion.button>
            ))}
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
