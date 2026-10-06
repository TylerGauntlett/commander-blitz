/**
 * The front door: a main menu made of cards.
 *
 * Ported from the door round's 01 'The Hand' (`docs/design-record.md#door`), the direction that round
 * converged on. **THE MENU IS A HAND OF CARDS AND YOU ARE ALREADY HOLDING IT** --
 * the one you are on squares up, lifts and lights the room; the other two tilt
 * away and stack behind it. Selecting is casting: pressing A on a card is the
 * gesture the whole game is built on, so the front door teaches the board's one
 * verb before the board exists.
 *
 * Nothing on the screen is new work for the player. Create a pod and join by
 * code are what the shipped door already offered; this is what they look like
 * when the more important one is not a `.big` in the middle and the second is
 * not a text field beside it. Settings is the third card and the one addition,
 * because a pad sometimes has to be told it is a pad.
 *
 * THE CATALOGUE IS NOT ON THE DOOR. It was a fourth card, and before that an
 * 11px underlined link in the footer that a pad could only reach by walking
 * through the text field. Browsing decks from the door starts nothing and ends
 * nowhere -- the place you actually choose a deck is a seat, and a seat has its
 * own way into the same catalogue. `/decks` still answers to anybody who types
 * it. What is left on the row is three things you would come here to do.
 *
 * ---------------------------------------------------------------------------
 * ## Why Play is the default card
 *
 * The brief asked that the middle card be selected by default, and that only
 * agrees with itself one way: a menu whose default selection is not its default
 * action has picked the wrong default. So Play is the middle. Join stays to
 * Play's right, which is the shipped door's own reading order -- "Create a pod",
 * or, a code -- and Settings goes to the left, where the least-committing thing
 * belongs. The row runs from least committing to most, and changing a control
 * scheme starts nothing at all.
 *
 * THE ROW HAS BEEN THREE, THEN FOUR, AND IS THREE AGAIN, which is why nothing
 * here reads a literal index. `DEFAULT_INDEX` looks Play up by name; the literal
 * 1 it replaced was right for the first row and silently wrong the moment a card
 * was added at the head, and nothing in the suite asserts a default by name.
 * That Play is once again the true middle card is an accident of the count, and
 * none of the arithmetic below depends on it.
 *
 * ## The row is one number
 *
 * Everything on screen is derived from `s`, where the selection currently is in
 * card-index space, which a spring moves between 0, 1 and 2. No keyframes and
 * no discrete states -- see `logic/doorRow.ts`. The spring is stated in time
 * rather than in stiffness, which is `input/ring.ts:18-35`'s rule, and it
 * borrows that module's closed-form step for that module's reason: the naive
 * integrator overshoots 1.6px at 60fps and 4.5px at 144fps, so the menu would
 * be a different menu on a monitor than on the Deck's panel.
 *
 * ## Controller support is the app's, not a second copy of it
 *
 * The three cards are native `<button>`s, so `input/stops.ts` picks them up as
 * stops with no registration -- and the whole of the pad layer, the DAS/ARR
 * ramp, the wall nudge and the rumble come with them. All this file does is
 * move the ROW to wherever the ring already is: `onFocus` selects. A second
 * gamepad loop here would be a second set of ramp bugs.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../../fx/reducedMotion";
import { onFrame } from "../../fx/scheduler";
import { refollowCursor, setCursor } from "../../input/cursor";
import { on, rumble } from "../../input/pad";
import { springStep } from "../../input/ring";
import { DOOR_TUNE, type DoorTune, poseOf, scaleTune } from "../../logic/doorRow";
import { looksLikeCode, normaliseCode } from "../../logic/lobby";
import { ControllerPanel } from "../ui/ControllerPanel";
import { Glyph } from "../ui/Glyph";
import { DoorCardArt, DoorCardFrame } from "./doorArt";
import { type Hue, Room } from "./Room";

/**
 * The longest code the server can issue: `BRAMBLE-123456` -- a seven-letter
 * word, a hyphen, and the six-digit collision fallback. A shorter cap silently
 * truncates what somebody pasted, and Join then sits disabled next to a code
 * that looks perfectly right on screen.
 */
const MAX_CODE_LENGTH = 14;

/**
 * A CARD IS A PICTURE AND A WORD. THERE IS NO THIRD THING ON IT.
 *
 * Each of these carried a line of copy under its name -- "Four seats. Deal a
 * new table.", and three like it. That line was the last survivor of a panel
 * with room: first a paragraph, then one clause, and one clause is still one
 * clause too many here. The illustration already says what is behind the card
 * (`doorArt.tsx` draws the thing itself rather than an icon of it) and the name
 * says it again in a word, so the sentence was a third statement of the same
 * fact, in the smallest type on the screen, on the card furthest from the eye.
 *
 * `verb` stays and is not copy: it is the second half of the `aria-label`, the
 * only place a screen reader hears what pressing this does.
 *
 * `hue` is the colour the room takes when that card is selected. Settings makes
 * the hall cold and blue, Play warm, Join violet -- all six out of
 * `theme.css`'s own palette.
 */
const DOOR_CARDS = [
  {
    id: "settings",
    label: "Settings",
    verb: "Set up your controller",
    testId: "open-settings",
    hue: ["#5c7a99", "#2b3f5a"] as Hue,
  },
  {
    id: "play",
    label: "Play",
    verb: "Create a pod",
    testId: "create-pod",
    hue: ["#d8a63c", "#8a3a2e"] as Hue,
  },
  {
    id: "join",
    label: "Join",
    verb: "Enter a pod code",
    testId: "join-pod",
    hue: ["#7d6bd8", "#2b5a86"] as Hue,
  },
] as const;

/** Where a card is, by name. */
function indexOf(id: string): number {
  return DOOR_CARDS.findIndex((card) => card.id === id);
}

/**
 * The card the row opens on, and the one A presses if nothing is touched.
 *
 * BY NAME, because it used to be the literal 1 and the row has changed length
 * twice. Adding a card at the head of the list silently moved the default one
 * place -- the menu opened on the wrong card, and nothing in the suite asserts
 * the default by name.
 */
const DEFAULT_INDEX = indexOf("play");

/**
 * w 22, z 0.82: 98% of the gap in 179ms -- eleven frames at 60Hz -- overshooting
 * 2.8px and permanently inside 2px at 294ms.
 *
 * IT WAS w 38, z 0.62, AND THE GATE THAT LET THAT THROUGH WAS THE PROBLEM. On
 * paper that is a 169ms settle, comfortably inside the 180ms budget. What it
 * actually did was cross the entire row in FOUR frames and then ring for
 * fourteen more, 21px each way: a cut, followed by a wobble, which is what
 * "jerky" was and what no still could have shown. A one-sided ceiling on a
 * duration is satisfied most cheaply by making the animation violent, so an
 * animation needs a floor as well -- at least 100ms of traverse or it is not a
 * move, no more than 320ms of settle or it is a wait.
 *
 * The 2.8px is deliberate and is the difference between this and the focus
 * ring's 2%: a ring is an outline and should read as ARRIVING, a card has
 * weight and should read as LANDING.
 */
const SLIDE = { w: 22, z: 0.82 } as const;

/** Settled, for the hover guard and for stopping the loop. */
const REST_X = 0.004;
const REST_V = 0.02;

interface Props {
  /** Prefilled from `?join=CODE` when somebody followed an invite link. */
  initialCode?: string;
  deckCount: number;
  onCreate: () => void;
  onJoin: (code: string) => void;
  busy: boolean;
  error: Error | null;
}

export function HomeScreen({
  initialCode = "",
  deckCount,
  onCreate,
  onJoin,
  busy,
  error,
}: Props) {
  // Initialised, not synced: `initialCode` comes from `?join=` and is read once
  // at boot. A `useEffect` that pushed it into state later would arrive after
  // the field had already mounted empty -- and would fight anybody typing.
  const [code, setCode] = useState(() => normaliseCode(initialCode));
  /*
   * An invite link has already asked the question the hold exists to ask, so it
   * opens on arrival with the code in it. This is also what keeps
   * `/pods/CODE`-on-a-cold-machine landing somewhere a player can act: the
   * field is on screen and prefilled rather than behind a card they would have
   * to know to press.
   */
  const [joinOpen, setJoinOpen] = useState(() => normaliseCode(initialCode).length > 0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  /** Where the selection is GOING. An integer, always, and the only part of the
      row React knows about. */
  const [sel, setSel] = useState(DEFAULT_INDEX);

  const slotRefs = useRef<(HTMLDivElement | null)[]>([]);
  const codeRef = useRef<HTMLInputElement>(null);

  /** Where the selection IS, continuously. The spring moves it; everything on
      screen is derived from it, and React never sees it. */
  const sRef = useRef(DEFAULT_INDEX);
  const vRef = useRef(0);
  const targetRef = useRef(DEFAULT_INDEX);
  const tuneRef = useRef<DoorTune>(DOOR_TUNE);
  const stopRef = useRef<(() => void) | null>(null);
  /** What was last written to each slot, so a frame in the middle of a slide
      touches three transforms and nothing else. */
  const wroteRef = useRef<{ t: string; z: number }[]>([]);

  /*
   * ONE STRING PER MOVING THING, AND NOTHING WRITTEN THAT HAS NOT CHANGED.
   *
   * Assembled here rather than handed to CSS as four custom properties: that
   * shape is eighteen custom-property invalidations a frame, each one a style
   * recalc on the subtree, plus a `z-index` rewritten sixty times a second to
   * the number it already held.
   */
  const paint = useCallback(() => {
    const tune = tuneRef.current;
    const s = sRef.current;
    for (let i = 0; i < DOOR_CARDS.length; i += 1) {
      const el = slotRefs.current[i];
      if (!el) continue;
      wroteRef.current[i] ??= { t: "", z: 0 };
      const was = wroteRef.current[i];
      const p = poseOf(i, s, tune, DOOR_CARDS.length);
      const t = `translate(calc(-50% + ${p.x.toFixed(2)}px), ${p.y.toFixed(2)}px) rotate(${p.rot.toFixed(2)}deg) scale(${p.scale.toFixed(4)})`;
      if (t !== was.t) {
        el.style.transform = t;
        was.t = t;
      }
      if (p.z !== was.z) {
        el.style.zIndex = String(p.z);
        was.z = p.z;
      }
    }
  }, []);

  /*
   * THE LOOP STOPS WHEN IT SETTLES, which is `ring.ts:10-13`'s rule and is here
   * for its reason: this is a battery-powered seven-inch computer and a rAF
   * that never stops costs play time for nothing. A menu is also the screen a
   * Deck sits on longest -- somebody who opens the game and walks away leaves
   * it here, not on a board.
   *
   * REDUCED MOTION SNAPS THE SPRING RATHER THAN STILLING IT. Where the
   * selection is is the one thing this screen exists to say, so it is the one
   * thing that may not be dropped; the sheen and the motes go instead, in CSS.
   */
  const wake = useCallback(() => {
    if (stopRef.current) return;
    if (prefersReducedMotion()) {
      sRef.current = targetRef.current;
      vRef.current = 0;
      paint();
      return;
    }
    stopRef.current = onFrame((dt) => {
      const next = springStep(
        sRef.current,
        vRef.current,
        targetRef.current,
        SLIDE.w,
        SLIDE.z,
        dt / 1000,
      );
      sRef.current = next.x;
      vRef.current = next.v;
      const moving =
        Math.abs(sRef.current - targetRef.current) > REST_X || Math.abs(vRef.current) > REST_V;
      if (!moving) {
        sRef.current = targetRef.current;
        vRef.current = 0;
        paint();
        stopRef.current = null;
        return false;
      }
      paint();
      return true;
    });
  }, [paint]);

  const moving = useCallback(
    () =>
      Math.abs(sRef.current - targetRef.current) > REST_X || Math.abs(vRef.current) > REST_V,
    [],
  );

  const select = useCallback(
    (i: number) => {
      const next = Math.max(0, Math.min(DOOR_CARDS.length - 1, i));
      if (targetRef.current === next) return;
      targetRef.current = next;
      setSel(next);
      wake();
    },
    [wake],
  );

  /*
   * The row's tune, at the stage scale `Room` resolved.
   *
   * The room is full-bleed and only the furniture scales, which is `Room`'s
   * job; what is left here is the half only this screen knows -- the mockup's
   * px terms in `DOOR_TUNE` are numbers the paint loop reads out of a ref, so
   * they are converted once per resize rather than once per frame. Every cached
   * transform string is in the old scale's pixels and has to go with them.
   */
  const rescale = useCallback(
    (du: number) => {
      tuneRef.current = scaleTune(DOOR_TUNE, du);
      wroteRef.current = [];
      paint();
    },
    [paint],
  );

  /* The ring is on a card that is about to slide 248px. `HandFan` makes the
     same call for the same reason: the effect runs on the commit that STARTS
     the animation, when the element has not moved a pixel, so the ring needs
     telling to watch rather than to re-measure once. */
  // biome-ignore lint/correctness/useExhaustiveDependencies: `sel` is a trigger, not a read; see above.
  useLayoutEffect(() => {
    refollowCursor();
  }, [sel]);

  useEffect(() => () => stopRef.current?.(), []);

  /*
   * THE RING OPENS ON PLAY, and it has to be said out loud.
   *
   * `resolveCursor` falls back to the first stop in document order, which here
   * is Settings -- and because focus drives the row, that would slide the menu
   * off its own default on the first frame. The default selection and the
   * default action have to be the same card or one of them is wrong.
   */
  useLayoutEffect(() => {
    setCursor(`ui:${DOOR_CARDS[DEFAULT_INDEX].testId}`);
  }, []);

  const press = useCallback(
    (i: number) => {
      if (busy) return;
      const el = slotRefs.current[i];
      if (el) {
        el.classList.remove("door__slot--press");
        // Reading `offsetWidth` is what restarts a CSS animation already on the
        // element: without it a second press inside the 90ms does nothing and
        // the control reads as having missed the input.
        void el.offsetWidth;
        el.classList.add("door__slot--press");
      }
      rumble(70, 0.3);
      /*
       * EXHAUSTIVE, and it was an `else`. With three cards the fallthrough was
       * Join and read fine; with a fourth it would have made Settings open the
       * pod-code hold. A menu whose last branch is "whatever is left" acquires a
       * bug every time somebody adds an item.
       */
      const id = DOOR_CARDS[i].id;
      if (id === "play") onCreate();
      else if (id === "join") setJoinOpen(true);
      else if (id === "settings") setSettingsOpen(true);
    },
    [busy, onCreate],
  );

  const submit = useCallback(() => {
    if (looksLikeCode(code)) onJoin(normaliseCode(code));
  }, [code, onJoin]);

  const closeJoin = useCallback(() => setJoinOpen(false), []);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  /**
   * Which hold is up, as one value.
   *
   * The two are mutually exclusive by construction -- both are opened only from
   * `press`, which can only press one card -- and collapsing them to a single
   * value is what lets one effect own the ring for both. Two effects, each
   * watching its own flag, would each hand the ring back on close and the second
   * would hand it back from a card the first had already left.
   */
  const openHold: "join" | "settings" | null = joinOpen
    ? "join"
    : settingsOpen
      ? "settings"
      : null;
  const closeHold = joinOpen ? closeJoin : closeSettings;

  /*
   * A HOLD OWNS THE INPUT WHILE IT IS UP, AND HANDS IT BACK WHEN IT GOES.
   *
   * `data-modal-root` is what traps the ring inside the panel, but the ring has
   * to be MOVED into it as well or the trap is only a picture of one:
   * `resolveCursor` runs off `FocusRing`'s render, and opening this changes the
   * DOM under a component that did not re-render. Landing on the field is also
   * the only sensible place -- somebody who pressed Join has a code to type.
   *
   * AND BOTH HALVES LIVE IN THIS EFFECT, which is the fix for a bug that looked
   * like the close was ignored. Putting the hand-back inside `closeJoin` runs it
   * a render too early: the dialog is still in the document, so `activeRoot` is
   * still the dialog, so `stopElement("ui:join-pod")` -- a card behind it -- is
   * not found and the call does nothing. React then removes the panel, the
   * cursor is naming a field that no longer exists, and `resolveCursor` falls
   * back to the first stop on the screen -- the leftmost card. Pressing B on the
   * Join hold slid the whole row across.
   */
  const wasOpen = useRef<"join" | "settings" | null>(openHold);
  useLayoutEffect(() => {
    if (openHold === "join") {
      setCursor("ui:pod-code");
      codeRef.current?.focus({ preventScroll: true });
    } else if (openHold === "settings") {
      // The first option of the scheme picker, which is what the panel is for.
      setCursor("ui:scheme-auto");
    } else if (wasOpen.current) {
      /*
       * BY NAME, not by index. This was `DOOR_CARDS[2]` -- correct while Join
       * was the third of three cards, and silently the Play card the moment a
       * fourth was added at the head. Closing the hold would have slid the row
       * one place and left the ring on a card nobody pressed. The row is three
       * again and the 2 would work again, which is exactly the accident that
       * makes an index look safe; it stays a name.
       */
      setCursor(`ui:${DOOR_CARDS[indexOf(wasOpen.current)].testId}`);
    }
    wasOpen.current = openHold;
  }, [openHold]);

  /* Three ways out, which is what every overlay in this client owes: the
     control, outside the panel, and Escape -- which arrives as B on a pad. */
  useEffect(() => {
    if (!openHold) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeHold();
    };
    window.addEventListener("keydown", onKey);
    const offB = on("b", closeHold);
    return () => {
      window.removeEventListener("keydown", onKey);
      offB();
    };
  }, [openHold, closeHold]);

  return (
    <Room hue={DOOR_CARDS[sel].hue} className="door" testId="home" onScale={rescale}>
      {/* The mark appears ONCE, at this screen's largest brand moment, which is
          `Mark.tsx`'s own rule and the one the shipped door broke. It is not
          `<Mark/>` because this copy takes the room's colour and drops the
          filled plate behind the bolt -- a lit hall does not need a swatch of
          `--void-0` floating in it. */}
      <div className="door__title">
        <svg
          className="door__badge"
          viewBox="0 0 64 64"
          aria-hidden="true"
          focusable="false"
          role="presentation"
        >
          <rect
            x="1.5"
            y="1.5"
            width="61"
            height="61"
            rx="12"
            fill="none"
            stroke="currentColor"
            strokeOpacity="0.32"
            strokeWidth="1.5"
          />
          <path
            d="M37.2 11.2 L20.4 34 H29.2 L26.8 52.8 L43.6 29.6 H34.8 Z"
            fill="currentColor"
          />
        </svg>
        <h1 className="door__word">Commander Blitz</h1>
      </div>

      <div className="door__row">
        {DOOR_CARDS.map((card, i) => (
          // biome-ignore lint/a11y/noStaticElementInteractions: a pointer-only hover affordance. The pad and the keyboard reach the same preview through the focus ring, which is why `useKeyWithClickEvents` is off in biome.json for the same reason.
          <div
            key={card.id}
            className={i === sel ? "door__slot door__slot--on" : "door__slot"}
            ref={(el) => {
              slotRefs.current[i] = el;
            }}
            /*
             * HOVER SELECTS, AND THE FEEDBACK LOOP IS CUT ON THE OTHER SIDE.
             *
             * `.hand__slot` keeps its hit box still while only the picture
             * moves, because in a hand the card is lifted BY the hover. That is
             * not available here -- sliding IS the design, so the box has to
             * move. Two rules make it safe instead: a hover is ignored while
             * the row is still moving, so a card arriving under a stationary
             * pointer cannot re-trigger anything; and a hover never
             * DE-selects, so the selection only ever moves toward the pointer
             * and has nowhere to oscillate to.
             */
            onMouseEnter={() => {
              if (openHold || moving()) return;
              select(i);
            }}
          >
            <button
              type="button"
              className={i === sel ? "plank plank--on door__card" : "plank door__card"}
              data-testid={card.testId}
              aria-label={`${card.label}. ${card.verb}`}
              onFocus={() => select(i)}
              onClick={() => {
                if (i !== targetRef.current) {
                  select(i);
                  return;
                }
                press(i);
              }}
            >
              <DoorCardFrame />
              <span className="door__win">
                <DoorCardArt id={card.id} />
              </span>
              <span className="door__name">{card.label}</span>
              <span className="sheen" />
            </button>
          </div>
        ))}
      </div>

      <p className="door__count">
        <b className="tabular">{deckCount}</b> deck{deckCount === 1 ? "" : "s"} in the catalogue
      </p>

      <div className="room__hints" aria-hidden="true">
        <span className="hint">
          <Glyph btn="a" />
          <span className="hint__verb">Select</span>
        </span>
        <span className="hint">
          <Glyph btn="dpad" />
          <span className="hint__verb">Move</span>
        </span>
      </div>

      {error && !openHold && (
        <p className="door__err" data-testid="home-error">
          {error.message.replace(/^\d+:\s*/, "")}
        </p>
      )}

      {joinOpen && (
        <div className="door__hold">
          {/* The scrim is a real element rather than a shadow, so a click
              anywhere outside the panel closes it -- one of the three ways out.
              `aria-hidden` because the dialog beside it carries the semantics. */}
          <div className="door__scrim" onClick={closeJoin} aria-hidden="true" />
          <section
            className="door__panel"
            role="dialog"
            aria-modal="true"
            data-modal-root
            aria-label="Join a pod"
            data-testid="join-hold"
          >
            <h2 className="door__h">Join a pod</h2>
            <p className="door__p">Type the code somebody sent you.</p>
            <div className="door__holdrow">
              <span className="door__code">
                <input
                  ref={codeRef}
                  className="door__codein"
                  type="text"
                  value={code}
                  onChange={(event) => setCode(normaliseCode(event.target.value))}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") submit();
                  }}
                  placeholder="BRAMBLE-4821"
                  spellCheck={false}
                  maxLength={MAX_CODE_LENGTH}
                  aria-label="Pod code"
                  data-testid="pod-code"
                />
              </span>
              <button
                type="button"
                className="door__go"
                data-testid="join-go"
                disabled={busy || !looksLikeCode(code)}
                onClick={submit}
              >
                Join
              </button>
            </div>
            {error && (
              <p className="door__err" data-testid="home-error">
                {error.message.replace(/^\d+:\s*/, "")}
              </p>
            )}
            {/*
              A REAL CONTROL, NOT A LEGEND.

              This was a `<p>` carrying the B glyph and the word Back -- a hint,
              in the shape of a button, in the place a button goes. On a mouse
              it did nothing when clicked; with a ring it could not be reached
              at all, because a paragraph is not a stop. Somebody walking the
              hold with a pad found two stops, neither of them the way out, and
              the one thing on screen that looked like the exit.

              Escape and B still close the hold and always did -- that is the
              half that worked, and it is why the paragraph survived review.
              This is the third of the three ways out every overlay in this
              client owes, and the only one you can point at.
            */}
            <button
              type="button"
              className="door__back"
              data-testid="join-back"
              onClick={closeJoin}
            >
              <Glyph btn="b" />
              Back
            </button>
          </section>
        </div>
      )}

      {/*
        The same shell as the join hold, and deliberately the same shell: scrim,
        `data-modal-root` so `stops.ts` traps the ring inside it, and the three
        ways out every overlay in this client owes -- the Back control, the scrim,
        and Escape-as-B. The ring handling for both lives in the one layout effect
        above, for the reason its comment gives.
      */}
      {settingsOpen && (
        <div className="door__hold">
          <div className="door__scrim" onClick={closeSettings} aria-hidden="true" />
          <section
            className="door__panel door__panel--wide"
            role="dialog"
            aria-modal="true"
            data-modal-root
            aria-label="Settings"
            data-testid="settings-hold"
          >
            <h2 className="door__h">Settings</h2>
            <p className="door__p">
              Which controls the game draws, and whether it can see your pad.
            </p>
            <ControllerPanel />
            <button
              type="button"
              className="door__back"
              data-testid="settings-back"
              onClick={closeSettings}
            >
              <Glyph btn="b" />
              Back
            </button>
          </section>
        </div>
      )}
    </Room>
  );
}
