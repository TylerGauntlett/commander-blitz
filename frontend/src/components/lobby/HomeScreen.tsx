/**
 * The front door: a main menu made of three cards.
 *
 * Ported from `mockups/door/01-the-hand.html`, the direction that round
 * converged on. **THE MENU IS A HAND OF CARDS AND YOU ARE ALREADY HOLDING IT** --
 * the one you are on squares up, lifts and lights the room; the other two tilt
 * away and stack behind it. Selecting is casting: pressing A on a card is the
 * gesture the whole game is built on, so the front door teaches the board's one
 * verb before the board exists.
 *
 * Nothing on the screen is new work for the player. Create a pod, join by code
 * and browse the catalogue are the same three things the shipped door offered;
 * this is what they look like when the most important one is not a `.big` in
 * the middle, the second is a text field beside it, and the third is an 11px
 * underlined link in the footer that a pad could only reach by walking through
 * the text field.
 *
 * ---------------------------------------------------------------------------
 * ## Why Play is the middle card
 *
 * The brief asked for "Play, Join, Decks" and asked that the middle card be
 * selected by default, and those only agree one way: a menu whose default
 * selection is not its default action has picked the wrong default. So Play is
 * the middle and the list order gives. Join stays to Play's right, which is the
 * shipped door's own reading order -- "Create a pod", or, a code -- and Decks
 * comes up out of the footer to the left, where the least-committing thing
 * belongs. Looking at your decks costs nothing and starts nothing.
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

import type { CSSProperties } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../../fx/reducedMotion";
import { onFrame } from "../../fx/scheduler";
import { refollowCursor, setCursor } from "../../input/cursor";
import { on, rumble } from "../../input/pad";
import { springStep } from "../../input/ring";
import { DOOR_TUNE, type DoorTune, poseOf, scaleTune, stageScale } from "../../logic/doorRow";
import { looksLikeCode, normaliseCode } from "../../logic/lobby";
import { Glyph } from "../ui/Glyph";
import { DoorCardArt, DoorCardFrame, DoorFloor, DoorGround } from "./doorArt";

/**
 * The longest code the server can issue: `BRAMBLE-123456` -- a seven-letter
 * word, a hyphen, and the six-digit collision fallback. A shorter cap silently
 * truncates what somebody pasted, and Join then sits disabled next to a code
 * that looks perfectly right on screen.
 */
const MAX_CODE_LENGTH = 14;

/**
 * THE COPY IS ONE LINE AND THE SAME SHAPE THREE TIMES.
 *
 * These were sentences, written for a panel with room. On a 200px card they
 * came to six lines and ran out of the bottom of it. The right fix is not a
 * smaller font or a taller card: a menu item explains itself in a phrase or it
 * is not a menu item, and three items that describe themselves in three
 * different shapes read as three unrelated things. One clause each, a noun and
 * a promise, no marketing.
 *
 * `hue` is the colour the room takes when that card is selected. Decks makes
 * the hall cold and green, Play warm, Join violet -- all six out of
 * `theme.css`'s own palette.
 */
const DOOR_CARDS = [
  {
    id: "decks",
    label: "Decks",
    verb: "Browse the catalogue",
    testId: "browse-decks",
    hue: ["#3f9e93", "#2b5a86"],
  },
  {
    id: "play",
    label: "Play",
    verb: "Create a pod",
    testId: "create-pod",
    hue: ["#d8a63c", "#8a3a2e"],
  },
  {
    id: "join",
    label: "Join",
    verb: "Enter a pod code",
    testId: "join-pod",
    hue: ["#7d6bd8", "#2b5a86"],
  },
] as const;

/** The card the row opens on, and the one A presses if nothing is touched. */
const DEFAULT_INDEX = 1;

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

/** Sixteen specks drifting upward -- `fx/presets.ts:225`'s ambient count, near
    enough. Fixed rather than random so two screenshots of this screen compare. */
const MOTES = Array.from({ length: 16 }, (_, i) => ({
  left: 6 + ((i * 79) % 88),
  dur: 11 + ((i * 7) % 9),
  delay: (i * 13) % 11,
  drift: ((i % 5) - 2) * 22,
}));

/** A hex to `rgb(r g b / a)`, so one token can be both a line and a glow. */
function soft(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255} / ${alpha})`;
}

interface Props {
  /** Prefilled from `?join=CODE` when somebody followed an invite link. */
  initialCode?: string;
  deckCount: number;
  onCreate: () => void;
  onJoin: (code: string) => void;
  busy: boolean;
  error: Error | null;
  onBrowse: () => void;
}

export function HomeScreen({
  initialCode = "",
  deckCount,
  onCreate,
  onJoin,
  busy,
  error,
  onBrowse,
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
  /** Where the selection is GOING. An integer, always, and the only part of the
      row React knows about. */
  const [sel, setSel] = useState(DEFAULT_INDEX);

  const rootRef = useRef<HTMLDivElement>(null);
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
  const wroteRef = useRef<{ t: string; z: number; ink: string }[]>([]);

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
      wroteRef.current[i] ??= { t: "", z: 0, ink: "" };
      const was = wroteRef.current[i];
      const p = poseOf(i, s, tune);
      const t = `translate(calc(-50% + ${p.x.toFixed(2)}px), ${p.y.toFixed(2)}px) rotate(${p.rot.toFixed(2)}deg) scale(${p.scale.toFixed(4)})`;
      if (t !== was.t) {
        el.style.transform = t;
        was.t = t;
      }
      if (p.z !== was.z) {
        el.style.zIndex = String(p.z);
        was.z = p.z;
      }
      const ink = p.ink.toFixed(3);
      if (ink !== was.ink) {
        el.style.setProperty("--ink", ink);
        was.ink = ink;
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
   * THE STAGE SCALES; THE MOCKUP'S DECK DOES NOT.
   *
   * The mockup is a fixed 1280x800 scaled to the window, which is right for a
   * review surface and wrong here. `--du` is the same number applied to the
   * furniture instead, so the room is full-bleed at any size and the row is the
   * shape it was measured at. Written straight to the element, because the
   * paint loop reads the tune from a ref and a re-render would be a frame late.
   */
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const fit = () => {
      const du = stageScale(el.clientWidth, el.clientHeight);
      el.style.setProperty("--du", String(du));
      tuneRef.current = scaleTune(DOOR_TUNE, du);
      // Every cached string is in the old scale's pixels.
      wroteRef.current = [];
      paint();
    };
    fit();
    /* jsdom has no `ResizeObserver`, which is the same hole `useZoomFit.ts:365`
       guards. A window listener is the honest fallback rather than a no-op: the
       stage IS the window here, so the two only differ when something else on
       the page reflows, which on this screen is nothing. */
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", fit);
      return () => window.removeEventListener("resize", fit);
    }
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    return () => observer.disconnect();
  }, [paint]);

  /* The room, off the selection. Written to the stage rather than to `:root`,
     so the tint is a property of this screen and not of the document. */
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const hue = DOOR_CARDS[sel].hue;
    el.style.setProperty("--lit", hue[0]);
    el.style.setProperty("--lit-soft", soft(hue[0], 0.36));
    el.style.setProperty("--lit2-soft", soft(hue[1], 0.24));
    el.style.setProperty("--lit-beam", soft(hue[0], 0.13));
    /* The ring is on a card that is about to slide 248px. `HandFan` makes the
       same call for the same reason: the effect runs on the commit that STARTS
       the animation, when the element has not moved a pixel, so the ring needs
       telling to watch rather than to re-measure once. */
    refollowCursor();
  }, [sel]);

  useEffect(() => () => stopRef.current?.(), []);

  /*
   * THE RING OPENS ON PLAY, and it has to be said out loud.
   *
   * `resolveCursor` falls back to the first stop in document order, which here
   * is Decks -- and because focus drives the row, that would slide the menu off
   * its own default on the first frame. The default selection and the default
   * action have to be the same card or one of them is wrong.
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
      const id = DOOR_CARDS[i].id;
      if (id === "play") onCreate();
      else if (id === "decks") onBrowse();
      else setJoinOpen(true);
    },
    [busy, onCreate, onBrowse],
  );

  const submit = useCallback(() => {
    if (looksLikeCode(code)) onJoin(normaliseCode(code));
  }, [code, onJoin]);

  const closeJoin = useCallback(() => setJoinOpen(false), []);

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
   * back to the first stop on the screen: Decks. Pressing B on the Join hold
   * slid the whole row two places left.
   */
  const wasOpen = useRef(joinOpen);
  useLayoutEffect(() => {
    if (joinOpen) {
      setCursor("ui:pod-code");
      codeRef.current?.focus({ preventScroll: true });
    } else if (wasOpen.current) {
      setCursor(`ui:${DOOR_CARDS[2].testId}`);
    }
    wasOpen.current = joinOpen;
  }, [joinOpen]);

  /* Three ways out, which is what every overlay in this client owes: the
     control, outside the panel, and Escape -- which arrives as B on a pad. */
  useEffect(() => {
    if (!joinOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeJoin();
    };
    window.addEventListener("keydown", onKey);
    const offB = on("b", closeJoin);
    return () => {
      window.removeEventListener("keydown", onKey);
      offB();
    };
  }, [joinOpen, closeJoin]);

  const lines: string[] = [
    `${deckCount} deck${deckCount === 1 ? "" : "s"}, and anything you import.`,
    busy ? "Dealing the table…" : "Four seats. Deal a new table.",
    "Take a chair somebody held open.",
  ];

  return (
    <div className="door" data-testid="home" ref={rootRef}>
      <DoorGround />
      <DoorFloor />
      <div className="door__wash" aria-hidden="true" />

      <div className="door__motes" aria-hidden="true">
        {MOTES.map((m) => (
          <span
            key={`${m.left}-${m.dur}-${m.delay}`}
            className="door__mote"
            style={
              {
                left: `${m.left}%`,
                animationDuration: `${m.dur}s`,
                animationDelay: `-${m.delay}s`,
                "--drift": `${m.drift}px`,
              } as CSSProperties
            }
          />
        ))}
      </div>

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
              if (joinOpen || moving()) return;
              select(i);
            }}
          >
            <button
              type="button"
              className="door__card"
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
              <span className="door__line">{lines[i]}</span>
              <span className="door__sheen" />
            </button>
          </div>
        ))}
      </div>

      <p className="door__count">
        <b className="tabular">{deckCount}</b> deck{deckCount === 1 ? "" : "s"} in the catalogue
      </p>

      <div className="door__hints" aria-hidden="true">
        <span className="hint">
          <Glyph btn="a" />
          <span className="hint__verb">Select</span>
        </span>
        <span className="hint">
          <Glyph btn="dpad" />
          <span className="hint__verb">Move</span>
        </span>
      </div>

      {error && !joinOpen && (
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
            {error ? (
              <p className="door__err" data-testid="home-error">
                {error.message.replace(/^\d+:\s*/, "")}
              </p>
            ) : (
              <p className="door__holdhint">
                <Glyph btn="b" />
                Back
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
