/**
 * The opening hand, as a screen rather than as a dialog.
 *
 * Ported from the mulligan round's 01 'The Deal' (`docs/design-record.md#mulligan`), the direction that round
 * converged on. What it replaces is `PromptDialog` drawing the first decision of
 * every game as a centred rectangle with an 18px title and two identical grey
 * buttons, standing on top of the hand it is asking about -- and
 * `styles/ui.css:934-951` is the admission, because that backdrop is a
 * *gradient* rather than a flat dim, with a comment saying it exists since "a
 * flat dim over the whole viewport hid the one thing the player has to look at".
 * Behind it the hand was drawn at `--card-w-base`, which is 73.6px on a Deck,
 * where `.face`'s rules text resolves to 8.5px and is dropped entirely.
 *
 * So: the hand IS the screen, at the size its own rules text needs, and the two
 * answers are face buttons rather than rectangles.
 *
 * ## Both halves of a London mulligan, in one room
 *
 * `engine/game.py` asks twice -- keep-or-mulligan, then "put N on the bottom"
 * once you have kept -- and those went through the same dialog looking nothing
 * like each other: the first carries no object refs so it rendered two bare
 * labels, the second carries them so the same component rendered a grid of card
 * faces. Here the room does not change between them. The cards stay where they
 * are and the arch stays where it is; what changes is the question and what the
 * buttons are called. `logic/openingHand.ts`'s `mulliganPhase` is that routing,
 * and it reads the engine's `purpose` tag rather than the prompt string.
 *
 * ## Controller support is the app's, not a second copy of it
 *
 * The cards and the answers are native `<button>`s, so `input/stops.ts` picks
 * them up with no registration and the pad layer, the DAS/ARR ramp, the wall
 * nudge and the rumble all come with them. `onFocus` selects, so the row follows
 * wherever the ring already is. That is the door's rule
 * (`HomeScreen.tsx:51-58`), and it is why there is no gamepad loop in this file.
 *
 * The one binding it adds is `A` **on a card**, which keeps the hand. `A` is
 * `el.click()` on the focused stop app-wide (`input/useCursorNav.ts:31-46`) and
 * that is deliberately not overridable, so a card's own click stays "select" --
 * a mouse must never commit a game by clicking a card it only wanted to read.
 * The pad reaches Keep from the card row instead, which is the ninety-percent
 * path: glance across the hand, press A.
 *
 * ## `StaticCard`, never `Card`
 *
 * `HandFan` is still mounted underneath this, so a second `layoutId` for the
 * same oid would make Motion animate the board card into this one. Both
 * `CardPreview` and `CardHold` carry the same note for the same reason.
 *
 * `variant="detail"` is `CardFace.tsx:50-76`'s own description of this exact
 * surface: "the stack, the mulligan dialog, the zone peek -- big enough to carry
 * rules, still a 1.4 portrait card".
 */

import { AnimatePresence, motion, usePresence } from "motion/react";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CardView, GameView, LegalAction } from "../../api/types";
import { getCursor, refollowCursor, setCursor } from "../../input/cursor";
import { on as onPad } from "../../input/pad";
import { actionAttrs, stopId } from "../../input/stops";
import {
  handRow,
  MULL_TUNE,
  type MulliganPhase,
  mulliganCost,
  mulliganPhase,
  stageUnit,
  zFor,
} from "../../logic/openingHand";
import { parseStop } from "../../logic/verbs";
import { ease } from "../../motion/springs";
import { Glyph } from "../ui/Glyph";
import { StaticCard } from "./Card";

/** What the stage measured, and what that makes the composition. */
interface Fit {
  width: number;
  unit: number;
}

interface Props {
  state: GameView;
  actions: LegalAction[];
  onAct: (actionId: string) => void;
  disabled: boolean;
}

/** The viewer's hand. Only the seat being asked is ever sent one. */
function handOf(state: GameView): CardView[] {
  return state.players[state.seat]?.hand ?? [];
}

/**
 * The action that answers for each card, in the bottoming phase.
 *
 * `action.choice` indexes `pending.options` and the option's `ref` carries the
 * oid, so the mapping is the engine's own and nothing here matches on a name.
 */
function choiceByOid(state: GameView, actions: LegalAction[]): Map<number, LegalAction> {
  const options = state.pending?.options ?? [];
  const out = new Map<number, LegalAction>();
  for (const action of actions) {
    if (action.choice === null) continue;
    const ref = options[action.choice]?.ref ?? action.targets[0];
    if (ref && ref.kind === "object") out.set(ref.id, action);
  }
  return out;
}

/**
 * How long a leaving stage stays in the DOM: `ease`'s 220ms, with a frame or
 * two of slack so the fade is seen to finish. See `Stage` for why this is a
 * number and not an animation's word for "done".
 */
const EXIT_MS = 260;

export function OpeningHand({ state, actions, onAct, disabled }: Props) {
  const phase = mulliganPhase(state);

  return (
    <AnimatePresence>
      {phase !== null && actions.length > 0 && (
        <Stage
          key="opening-hand"
          state={state}
          actions={actions}
          onAct={onAct}
          disabled={disabled}
          phase={phase}
        />
      )}
    </AnimatePresence>
  );
}

function Stage({ state, actions, onAct, disabled, phase }: Props & { phase: MulliganPhase }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const hand = handOf(state);
  const middle = Math.floor(Math.max(0, hand.length - 1) / 2);
  const [on, setOn] = useState(middle);

  /*
   * WHAT THE STAGE MEASURED, RECOMPUTED ON RESIZE AND ON NOTHING ELSE.
   *
   * Held in state rather than written straight to the elements the way `Room`
   * writes `--du`, and the difference is that this is not a paint loop: the door
   * runs a spring every frame and cannot afford a render, whereas `handRow` is
   * called once per resize and its result is rendered rather than animated.
   *
   * `--mu` goes on the element as well so the stylesheet sizes its type and its
   * answers off the same number, and `data-mu` is the resolved value in the DOM
   * so a spec can read the scale rather than recompute it -- `Room` exposes its
   * own the same way.
   */
  const [fit, setFit] = useState<Fit>({ width: 1280, unit: 1 });
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const measure = () => {
      const width = el.clientWidth;
      const unit = stageUnit(width, el.clientHeight, hand.length);
      el.dataset.mu = unit.toFixed(3);
      setFit((was) => (was.width === width && was.unit === unit ? was : { width, unit }));
    };
    measure();
    /* jsdom has no `ResizeObserver` -- the hole `Room.tsx:105-112` and
       `useZoomFit.ts:365` both guard. The stage IS the window here, so a resize
       listener is the honest fallback rather than a no-op. */
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [hand.length]);

  const row = useMemo(
    () => handRow(hand.length, fit.width, fit.unit),
    [hand.length, fit.width, fit.unit],
  );

  const pending = state.pending;
  const keep = actions.find((action) => action.kind === "keep");
  const mull = actions.find((action) => action.kind === "mulligan");
  const choices = useMemo(() => choiceByOid(state, actions), [state, actions]);
  const chosen = useMemo(() => new Set(pending?.selected ?? []), [pending?.selected]);
  const me = state.players[state.seat];
  const taken = me?.mulligans_taken ?? 0;
  /* The engine's rules, off the wire: six at most, the first one free. */
  const free = me?.mulligans_free ?? 0;
  const max = me?.mulligans_max ?? 6;
  const cost = mulliganCost(taken, free);
  const bottoming = phase === "bottom";
  const wanted = Math.max(0, (pending?.min_count ?? 0) - chosen.size);

  const commit = useCallback(
    (action: LegalAction | undefined) => {
      if (!action || disabled) return;
      onAct(action.id);
    },
    [onAct, disabled],
  );

  /*
   * THE RING OPENS ON THE MIDDLE CARD.
   *
   * `resolveCursor`'s `enter` path lands on the first stop in document order
   * when a new `data-modal-root` appears, which here is the leftmost card -- the
   * one the arch tilts furthest and the one nobody starts by reading. The door
   * sets its cursor by name for the same reason.
   */
  const middleOid = hand[middle]?.oid;
  useEffect(() => {
    if (middleOid !== undefined) setCursor(stopId.card(middleOid));
  }, [middleOid]);

  /*
   * Told to WATCH rather than to re-measure: this runs on the commit that starts
   * the lift, not on the one that finishes it. `HandFan.tsx:175` makes the
   * identical call for the identical reason.
   *
   * ON EVERY POSE CHANGE, not just on mount, because the slot itself is what
   * rises now: `retargetRing` measures once, at the instant the cursor lands,
   * and 150ms of `transition: transform` happen after that. The watch window is
   * how the ring arrives with the card instead of at the pixel the card was
   * leaving. `chosen` is in the list for the bottoming phase, where a card sinks
   * without the cursor going anywhere at all.
   */
  // biome-ignore lint/correctness/useExhaustiveDependencies: `on` and `chosen` are triggers, not reads; see above.
  useEffect(() => {
    refollowCursor();
  }, [on, chosen]);

  /*
   * `A` ON A CARD KEEPS THE HAND, and `B` mulligans from anywhere.
   *
   * Scoped to the card stops on purpose. With the ring on the Keep button
   * `useCursorNav` has already dispatched the click, so answering here as well
   * would answer twice -- the same branch-on-the-stop-kind shape `Table` uses
   * for `Y`.
   *
   * The bottoming phase binds neither: there a card's click IS the answer, so
   * `A` needs no help, and `B` belongs to `Table`'s own unwind.
   */
  useEffect(() => {
    if (phase !== "keep") return;
    const unbind = [
      onPad("a", () => {
        if (parseStop(getCursor()).kind !== "card") return;
        commit(keep);
      }),
      onPad("b", () => commit(mull)),
    ];
    return () => {
      for (const off of unbind) off();
    };
  }, [phase, keep, mull, commit]);

  /*
   * An exiting stage stops claiming the ring.
   *
   * `stopRoot` reads `[data-modal-root]:not([data-closing])`, and its header
   * says why: every dialog here animates out through `AnimatePresence`, so an
   * exiting one is still in the DOM for its exit duration and the ring stays
   * trapped in a screen that is fading away. `present` is false for exactly
   * that window, which is the cheapest honest answer -- the existing dialogs
   * satisfy the guard only by never having been measured mid-exit.
   *
   * AND THE STAGE LEAVES ON A CLOCK, NOT ON AN ANIMATION. `AnimatePresence`
   * removes a child only once every `exit` inside it has reported complete,
   * and an opacity exit started while the entrance was still in flight was
   * measured never to -- the stage stayed in the DOM at the modal z-index,
   * `inset: 0`, over a board that had gone on without it, on about one keep in
   * two in `e2e/orb.spec.ts`. So the root carries no `exit`: the fade is an
   * `animate` toward the closed look, which needs nobody's completion, and
   * `safeToRemove` is called by a timer the fade cannot hold up. If the fade
   * is ever lost again the stage cuts instead of fading; it does not stay.
   */
  const [present, safeToRemove] = usePresence();
  // Through a ref, and keyed on `present` ALONE. `safeToRemove` is rebuilt
  // whenever the presence boundary re-renders, which is every state push --
  // the AI pump lands one every ~110ms while this fades -- and a timer that
  // restarted on each of them never fired while the game was moving.
  const removeRef = useRef(safeToRemove);
  removeRef.current = safeToRemove;
  useEffect(() => {
    if (present) return;
    const timer = setTimeout(() => removeRef.current?.(), EXIT_MS);
    return () => clearTimeout(timer);
  }, [present]);

  return (
    <motion.div
      ref={rootRef}
      className="mull"
      data-modal-root
      data-closing={present ? undefined : true}
      data-phase={phase}
      /* The same attribute `PromptDialog` puts on itself, carrying the same
         vocabulary -- the engine's kind, not this screen's phase. `full-game`
         collects it across a whole game to prove every decision kind reached a
         surface, and a second name for one idea would have quietly excluded the
         two kinds that moved here. */
      data-decision-kind={pending?.kind}
      data-testid="opening-hand"
      role="dialog"
      aria-modal="true"
      aria-label={bottoming ? "Put cards on the bottom of your library" : "Keep this hand?"}
      style={{ "--mu": fit.unit } as CSSProperties}
      initial={{ opacity: 0 }}
      animate={{ opacity: present ? 1 : 0 }}
      transition={ease}
    >
      <p className="mull__eyebrow">{bottoming ? "To the bottom" : "Opening hand"}</p>

      {/* How many mulligans are left, as lamps rather than as "(2 taken)" buried
          in a prompt string. The engine has written that number into its own
          prompt since London mulligans landed; `serialize._player` only started
          sending it with this screen. The free ones are a different lamp, and
          spending one does not light it red: it cost nothing. */}
      <div className="mull__lamps">
        <span className="mull__lampsLabel">Mulligans</span>
        {/* biome-ignore lint/a11y/useAriaPropsSupportedByRole: a labelled readout on a generic element, written before Biome 2 had this rule. The fix is a role, which changes what a screen reader announces -- a behaviour change, so it waits for an a11y pass rather than riding a dependency upgrade. */}
        <span
          className="mull__lampsRow"
          aria-label={`${taken} of ${max} taken${free > 0 ? `, first ${free === 1 ? "one" : free} free` : ""}`}
        >
          {Array.from({ length: max }, (_, i) => (
            <span
              className="mull__lamp"
              // biome-ignore lint/suspicious/noArrayIndexKey: identical lamps with no identity of their own.
              key={i}
              data-free={i < free || undefined}
              data-spent={i < taken || undefined}
            />
          ))}
        </span>
      </div>

      <div
        className="mull__row"
        data-testid="opening-hand-row"
        style={{ top: `${row.top}px`, height: `${row.height}px` }}
      >
        {hand.map((card, i) => {
          const slot = row.slots[i];
          const isOn = i === on;
          const choice = choices.get(card.oid);
          const marked =
            choice !== undefined && choice.choice !== null && chosen.has(choice.choice);
          /* Marked beats read, the way the stylesheet's two rules did: a card
             already going to the bottom stays down even while you are on it. */
          const shift = marked ? row.sink : isOn ? -row.lift : 0;
          /*
           * In the bottoming phase a card IS the answer, so it carries the
           * action id and `A` is a click on it. In the keep phase it is a stop
           * and nothing more: clicking selects, which is what hovering does.
           */
          const attrs =
            bottoming && choice
              ? { ...actionAttrs(choice.id), "data-action-kind": choice.kind }
              : { "data-stop": stopId.card(card.oid) };
          return (
            <button
              type="button"
              key={card.oid}
              className="mull__slot"
              style={
                {
                  left: `${slot.x}px`,
                  top: `${slot.y}px`,
                  width: `${row.cardW}px`,
                  height: `${row.cardH}px`,
                  /*
                   * THE POSE IS ONE TRANSFORM, AND THE SLOT WEARS IT.
                   *
                   * The lift used to be on `.mull__lift` inside, so that the box
                   * the pointer is in never moved. The ring measures the STOP --
                   * `input/ring.ts`'s `ringTargetFor` and `handheld.css`'s
                   * `[data-cursor]` outline both -- so a card that rose out of
                   * its own button left the ring standing 20px below it, around
                   * an empty rectangle, which is what an arrow key looked like on
                   * this screen. `.mull__slot::after` is what pays for moving it;
                   * see `pad` in `logic/openingHand.ts`.
                   *
                   * `translateY` FIRST, so it is read in the row's frame rather
                   * than in the card's own tilted one: every card rises straight
                   * up the screen, and the end cards do not drift sideways as
                   * they do it.
                   */
                  transform: `translateY(${shift.toFixed(2)}px) rotate(${slot.rot.toFixed(3)}deg)`,
                  transformOrigin: `50% ${row.pivot}px`,
                  zIndex: zFor(i, on),
                  "--card-w": `${row.cardW}px`,
                  "--mull-pad": `${row.pad}px`,
                } as CSSProperties
              }
              data-on={isOn || undefined}
              data-marked={marked || undefined}
              data-card-oid={card.oid}
              /*
               * A CARD IS ONLY EVER DISABLED IN THE BOTTOMING PHASE.
               *
               * `disabled` means a request is in flight, and the answers below
               * take it because pressing one twice would send it twice. A card
               * in the keep phase is not an answer -- clicking it selects, and
               * selecting during a round trip is harmless.
               *
               * It also costs something to get wrong: a disabled `<button>` is
               * not focusable, so `input/stops.ts` stops seeing it, and
               * disabling all seven would take the ring's home out from under it
               * for the length of every request. The one it lands on next is
               * whatever `resolveCursor` can still find.
               */
              disabled={bottoming && (disabled || !choice)}
              aria-label={card.name}
              aria-pressed={bottoming ? marked : undefined}
              onFocus={() => setOn(i)}
              onMouseEnter={() => setOn(i)}
              onClick={() => {
                setOn(i);
                if (bottoming && choice) commit(choice);
              }}
              {...attrs}
            >
              <span className="mull__lift">
                {/* `onSurface`: the stage fades out as one thing, and a card
                    with an exit of its own is a registration this stage's
                    removal then waits on. `StaticCard` says what happened. */}
                <StaticCard card={card} variant="detail" onSurface />
              </span>
              {marked && <span className="mull__tag">&#8595; Bottom</span>}
            </button>
          );
        })}
      </div>

      <div className="mull__acts" style={{ top: `${MULL_TUNE.ACTS_TOP * fit.unit}px` }}>
        {bottoming ? (
          <p className="mull__ask" data-testid="opening-hand-ask">
            {wanted > 0
              ? `Choose ${wanted} more card${wanted === 1 ? "" : "s"} to put on the bottom`
              : "That is all of them"}
          </p>
        ) : (
          <>
            <button
              type="button"
              className="mull__act mull__act--mull"
              disabled={disabled || !mull}
              onClick={() => commit(mull)}
              {...(mull ? { ...actionAttrs(mull.id), "data-action-kind": mull.kind } : {})}
            >
              <span className="mull__glyph">
                <Glyph btn="b" />
              </span>
              <span className="mull__words">
                <span className="mull__verb">Mulligan</span>
                <span className="mull__sub">
                  {/* "Free" only while it is: the first mulligan bottoms nothing. */}
                  {cost.nextIsFree
                    ? "Free — shuffle back, draw seven"
                    : `Shuffle back, draw seven, keep ${cost.keepAfterNext}`}
                </span>
              </span>
            </button>
            <button
              type="button"
              className="mull__act mull__act--keep"
              disabled={disabled || !keep}
              onClick={() => commit(keep)}
              {...(keep ? { ...actionAttrs(keep.id), "data-action-kind": keep.kind } : {})}
            >
              <span className="mull__glyph">
                <Glyph btn="a" />
              </span>
              <span className="mull__words">
                <span className="mull__verb">Keep</span>
                <span className="mull__sub">
                  {cost.bottomIfKept > 0
                    ? `Keep ${Math.max(0, hand.length - cost.bottomIfKept)}, bottom ${cost.bottomIfKept}`
                    : `${hand.length} card${hand.length === 1 ? "" : "s"}`}
                </span>
              </span>
            </button>
          </>
        )}
      </div>

      {/* The one hint this screen carries itself. `HintBar` is lifted over the
          modal layer for a pad and already says the two verbs from `verbs.ts`,
          so this names only the thing the bar does not: that moving is reading.
          `aria-hidden`, because it is a picture of hardware over a screen whose
          own markup says all of it. */}
      <div className="mull__move" aria-hidden="true">
        <Glyph btn="dpad" />
        <span>{bottoming ? "Pick a card" : "Read a card"}</span>
      </div>
    </motion.div>
  );
}
