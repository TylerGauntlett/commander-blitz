/**
 * Everything that flies over the board.
 *
 * `useNarration` hands out one beat at a time, but effects need to *overlap* --
 * a combat step where four numerals appear in sequence should read as one
 * motion, not four slides. So this layer keeps its own short-lived list of what
 * it has been shown and lets each entry expire on its own clock.
 *
 * Anchors are resolved from the DOM (`data-oid`, `data-player`) at the moment
 * the beat plays, because the cards are inside springs and layout flights and
 * there is no reliable static position to precompute.
 *
 * Departing cards are the exception, and they are why `logic/cardRects.ts`
 * exists. A card being destroyed is one the board has *stopped* drawing -- the
 * new state is committed before the beats are pushed -- so there is no element
 * left to anchor to and the DOM lookup returns null. Its last known box is
 * posted here by `Card` on unmount instead.
 *
 * ## Two kinds of effect, and only one of them is React's business
 *
 * The overlays below -- numerals, rings, banners, spotlights, ghosts, the
 * damage vignette -- are elements, and they live in one list with one expiry
 * path. This used to be five separate `useState` arrays with five sets of timer
 * bookkeeping, which is a structure that grows a sixth copy every time the
 * board learns a new trick.
 *
 * The *physical* effects are not elements at all. A particle burst goes to a
 * canvas, a lunge goes straight to a card's motion values, screen shake goes to
 * a transform on the board wrapper. None of them render, and routing them
 * through component state would reconcile a ninety-card board sixty times a
 * second during every combat step.
 */

import { AnimatePresence, motion, useMotionValue } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { CardView, GameView } from "../../api/types";
import { play } from "../../audio/sfx";
import { drive } from "../../fx/actuators";
import { prefersReducedMotion } from "../../fx/reducedMotion";
import { onFrame, overTime } from "../../fx/scheduler";
import type { Beat, BeatAnchor, ExitFx, FxPoint, TimedFx, Tone } from "../../logic/beats/types";
import { recall } from "../../logic/cardRects";
import { CARD_SCALE, cardWidthVar } from "../../logic/cardSize";
import { findCard, findCardByDefId } from "../../logic/zoneGrouping";
import type { LiveBeat } from "../../state/narration";
import { SPEED_MULTIPLIER, type Speed, useUiStore } from "../../state/uiStore";
import { StaticCard } from "./Card";
import { CardGhost } from "./CardGhost";
import { burst } from "./ParticleLayer";

/** How long a numeral floats, before speed scaling. */
const FLOAT_MS = 1100;
const BANNER_MS = 900;
const SPOTLIGHT_MS = 800;
const FLASH_MS = 600;
const VIGNETTE_MS = 520;
/** The whole of a departure: the pause on the caption plus the fall. */
const GHOST_MS = 900;
/**
 * How long a wipe takes to sweep, regardless of how wide it is.
 *
 * Ten deaths at a comfortable 60ms apart is 600ms of stagger on top of a beat
 * the queue has already moved past, so the gap closes as the board gets wider.
 */
const GHOST_SWEEP_MS = 400;

interface Point {
  x: number;
  y: number;
}

/**
 * One thing drawn over the board.
 *
 * A discriminated union in one list, rather than a list per kind: they all have
 * the same lifecycle -- appear, sit for a while, be removed -- and the only
 * thing that differed between the five old arrays was the element at the end.
 */
type Overlay =
  | ({ kind: "float"; uid: number; value: string; tone: Tone } & Point)
  | ({ kind: "flash"; uid: number; tone: Tone } & Point)
  | { kind: "banner"; uid: number; text: string; tone: Tone }
  | {
      kind: "spotlight";
      uid: number;
      name: string;
      controller: number;
      spell: "spell" | "trigger";
      /** The real card, when one can be found. Null falls back to a name plate. */
      card: CardView | null;
    }
  | { kind: "vignette"; uid: number; tone: Tone }
  | {
      kind: "ghost";
      /** Unique per ghost, not per beat: a wipe puts several in one beat. */
      uid: number;
      oid: number;
      card: CardView | null;
      name: string;
      caption: string;
      to: string;
      cause: string;
      from: Point;
      toPoint: Point;
      width: number;
      duration: number;
      delay: number;
    };

function anchorPoint(anchor: BeatAnchor, origin: DOMRect): Point | null {
  const selector =
    anchor.kind === "player" ? `[data-player="${anchor.pid}"]` : `[data-oid="${anchor.oid}"]`;
  const element = document.querySelector(selector);
  if (!element) return null;
  const box = element.getBoundingClientRect();
  return {
    x: box.left + box.width / 2 - origin.left,
    y: box.top + box.height / 2 - origin.top,
  };
}

/**
 * Resolve an effect's position, including the point two cards meet at.
 *
 * `between` returns null unless *both* ends are on screen. Falling back to
 * whichever end resolved would put a collision on top of one of the
 * combatants, which is precisely the reading it exists to avoid.
 */
function resolve(point: FxPoint, origin: DOMRect): Point | null {
  if (point.kind !== "between") return anchorPoint(point, origin);
  const a = anchorPoint(point.a, origin);
  const b = anchorPoint(point.b, origin);
  if (!a || !b) return null;
  const t = point.t ?? 0.5;
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

/** The board-relative centre of the first element matching a selector. */
function centreOf(selector: string, origin: DOMRect): Point | null {
  const element = document.querySelector(selector);
  if (!element) return null;
  const box = element.getBoundingClientRect();
  // Zero-sized means not laid out -- jsdom, or a pile that is not rendered.
  if (box.width <= 0 && box.height <= 0) return null;
  return {
    x: box.left + box.width / 2 - origin.left,
    y: box.top + box.height / 2 - origin.top,
  };
}

/**
 * The pile a departing card lands in, or null when there is nothing to aim at.
 *
 * Keyed off the destination the engine reported and never off the cause: rule
 * 903.9a sends a *destroyed commander* to the command zone, so a ghost routed
 * by its cause would fly to a graveyard the card is not in.
 */
function pilePoint(exit: ExitFx, origin: DOMRect): Point | null {
  const pile = centreOf(`[data-testid="pile-${exit.owner}-${exit.to}"]`, origin);
  if (pile) return pile;
  // The library is drawn as a pile named "library", and there is no pile for
  // the stack at all -- fall back to the owner's orb, which is beside both.
  return centreOf(`[data-player="${exit.owner}"]`, origin);
}

/**
 * How a permanent comes apart, by why it left.
 *
 * `ExitFx` has carried `cause` and `to` since ghosts were built, and until now
 * they only picked a caption and a tint. A creature burned down, a creature
 * sacrificed and a creature exiled are three different things happening, and
 * the board said the same thing about all three.
 *
 * A bounce gets nothing on purpose: it is the one departure that is not a loss,
 * and giving it a burst would make returning a creature to hand look like
 * losing it.
 */
function exitBurst(exit: ExitFx): { preset: "explode" | "dissolve" | "shatter" } | null {
  if (exit.to === "exile") return { preset: "dissolve" };
  if (exit.to === "hand" || exit.to === "library" || exit.to === "library_top") return null;
  if (exit.cause === "countered") return { preset: "shatter" };
  if (exit.to === "graveyard") return { preset: "explode" };
  return null;
}

/**
 * One ghost, or null if there is nothing worth drawing.
 *
 * The start point is the card's last known box rather than a live DOM lookup,
 * because a card leaving the battlefield is exactly a card that is no longer in
 * the DOM -- see `logic/cardRects.ts`. When even that is missing the ghost is
 * dropped rather than guessed at: a card whose position was never recorded was
 * never on this screen, and inventing one (the board's centre, say) would put
 * an opponent's creature in the middle of the viewer's own board.
 */
function ghostFor(
  exit: ExitFx,
  index: number,
  count: number,
  state: GameView,
  origin: DOMRect,
  multiplier: number,
): Omit<Extract<Overlay, { kind: "ghost" }>, "uid"> | null {
  const rect = recall(exit.oid);
  if (!rect) return null;
  const toPoint = pilePoint(exit, origin);
  if (!toPoint) return null;

  return {
    kind: "ghost",
    oid: exit.oid,
    // By oid first, which finds any real card in the zone it just landed in.
    // By definition id second, for a *token*: tokens cease to exist on the way
    // out, so they are in no zone by the time this runs, and without the
    // fallback the commonest death in Commander would animate nothing.
    card:
      findCard(state, exit.oid) ?? (exit.cardId ? findCardByDefId(state, exit.cardId) : null),
    name: exit.name,
    caption: exit.caption,
    to: exit.to,
    cause: exit.cause,
    from: {
      x: rect.x + rect.width / 2 - origin.left,
      y: rect.y + rect.height / 2 - origin.top,
    },
    toPoint,
    // A tapped card lies on its side, so its box is wider than it is tall and
    // its *height* is the card width. Take the smaller side either way.
    width: Math.min(rect.width, rect.height),
    duration: GHOST_MS / multiplier / 1000,
    delay: (Math.min(60, GHOST_SWEEP_MS / count) * index) / multiplier / 1000,
  };
}

interface Props {
  beat: LiveBeat | null;
  speed: Speed;
  boardRef: React.RefObject<HTMLElement>;
  /** For resolving a spotlit card's face; see `findCardByDefId`. */
  state: GameView;
}

export function FxLayer({ beat, speed, boardRef, state }: Props) {
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const id of pending) clearTimeout(id);
    };
  }, []);

  // Read through a ref so toggling mute never re-runs the beat effect and
  // replays whatever was last on screen.
  const muted = useUiStore((s) => s.muted);
  const mutedRef = useRef(muted);
  mutedRef.current = muted;

  // Same trick for the state: the spotlight reads it once, when the beat plays.
  // Listing it as a dependency would replay every effect on every server
  // response, which arrives constantly while the AI pump runs.
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    if (!beat) return;
    const board = boardRef.current;
    if (!board) return;
    const origin = board.getBoundingClientRect();
    const multiplier = SPEED_MULTIPLIER[speed];

    const add = (overlay: Overlay, ms: number) => {
      setOverlays((current) => [...current, overlay]);
      const id = window.setTimeout(
        () => setOverlays((c) => c.filter((o) => o !== overlay)),
        ms / multiplier,
      );
      timers.current.push(id);
    };

    if (beat.sound && !mutedRef.current) play(beat.sound);

    if (beat.float) {
      const point = anchorPoint(beat.float.anchor, origin);
      if (point) {
        add({ kind: "float", uid: beat.uid, ...point, ...beat.float }, FLOAT_MS);
      }
    }

    if (beat.flash) {
      const point = anchorPoint(beat.flash.anchor, origin);
      if (point)
        add({ kind: "flash", uid: beat.uid, ...point, tone: beat.flash.tone }, FLASH_MS);
    }

    if (beat.banner) {
      add({ kind: "banner", uid: beat.uid, ...beat.banner }, BANNER_MS);
    }

    if (beat.spotlight) {
      add(
        {
          kind: "spotlight",
          uid: beat.uid,
          name: beat.spotlight.name,
          controller: beat.spotlight.controller,
          spell: beat.spotlight.kind ?? "spell",
          // Resolved once, here, rather than on every render: by the time this
          // expires the card may well have moved zones again.
          card: beat.spotlight.cardId
            ? findCardByDefId(
                stateRef.current,
                beat.spotlight.cardId,
                beat.spotlight.controller,
              )
            : null,
        },
        SPOTLIGHT_MS,
      );
    }

    if (beat.exits?.length) {
      const exits = beat.exits;
      // The last ghost's own delay is already baked in, so the whole sweep is
      // gone one flight after the last one starts.
      const sweep = GHOST_MS + Math.min(60, GHOST_SWEEP_MS / exits.length) * exits.length;

      exits.forEach((exit, i) => {
        const ghost = ghostFor(exit, i, exits.length, stateRef.current, origin, multiplier);
        // Null means the card was never on this screen -- an opponent's
        // permanent in a zone this seat cannot see. Nothing to draw, and
        // nothing to detonate either.
        if (!ghost) return;
        add({ ...ghost, uid: beat.uid * 1000 + i }, sweep);

        // The card comes apart where it stood, on the ghost's own stagger, so a
        // wrath detonates across the board rather than all at once. Paired with
        // its exit by construction here: a wrath can put two copies of the same
        // token in one beat, and looking the exit back up by oid would give
        // both of them the first one's treatment.
        const fx = exitBurst(exit);
        if (!fx) return;
        const id = window.setTimeout(() => burst(fx.preset, ghost.from), ghost.delay * 1000);
        timers.current.push(id);
      });
    }

    if (beat.fx?.length) {
      for (const fx of beat.fx) {
        const id = window.setTimeout(
          () => runFx(fx, origin, add, mutedRef.current),
          Math.max(0, fx.at) / multiplier,
        );
        timers.current.push(id);
      }
    }
  }, [beat, speed, boardRef]);

  return (
    <div className="fx" aria-hidden="true" data-testid="fx-layer">
      <AnimatePresence>
        {overlays.map((fx) => (
          <OverlayView key={`${fx.kind}-${fx.uid}`} fx={fx} />
        ))}
      </AnimatePresence>
    </div>
  );
}

/**
 * Play one scheduled effect.
 *
 * The imperative kinds never touch component state -- they go to the canvas, to
 * a card's motion values, or to the board's transform. Only the two that are
 * genuinely elements come back through `add`.
 */
function runFx(
  fx: TimedFx,
  origin: DOMRect,
  add: (overlay: Overlay, ms: number) => void,
  muted: boolean,
): void {
  switch (fx.kind) {
    case "emit": {
      const point = resolve(fx.at_point, origin);
      if (point) burst(fx.preset, point, { angle: fx.angle, scale: fx.scale });
      return;
    }
    case "actuate": {
      const actuator = drive(fx.oid);
      if (!actuator) return; // already dead, or in a zone this seat cannot see
      const toward = fx.toward ? resolve(fx.toward, origin) : null;
      if (fx.move === "lunge" && toward) actuator.lunge(toward);
      else if (fx.move === "recoil" && toward) actuator.recoil(toward, fx.power ?? 0.5);
      else if (fx.move === "shudder") actuator.shudder(fx.power ?? 0.5);
      else if (fx.move === "pulse") actuator.pulse(fx.power ?? 1);
      return;
    }
    case "float": {
      const point = resolve(fx.at_point, origin);
      if (point) {
        add(
          { kind: "float", uid: nextUid(), ...point, value: fx.value, tone: fx.tone },
          FLOAT_MS,
        );
      }
      return;
    }
    case "flash": {
      const point = resolve(fx.at_point, origin);
      if (point) add({ kind: "flash", uid: nextUid(), ...point, tone: fx.tone }, FLASH_MS);
      return;
    }
    case "shake":
      shakeBoard(fx.power);
      return;
    case "vignette":
      add({ kind: "vignette", uid: nextUid(), tone: fx.tone }, VIGNETTE_MS);
      return;
    case "sound":
      if (!muted) play(fx.sound);
      return;
  }
}

/**
 * Ids for effects that are born inside a beat rather than being the beat.
 *
 * A strike emits a dozen numerals off one beat, so `beat.uid` is not unique
 * enough to key them -- React would collapse the lot into one element.
 */
let uidSeed = 1_000_000;
function nextUid(): number {
  uidSeed += 1;
  return uidSeed;
}

function OverlayView({ fx }: { fx: Overlay }) {
  switch (fx.kind) {
    case "flash":
      return (
        <motion.span
          className={`fx-flash fx-flash--${fx.tone}`}
          style={{ left: fx.x, top: fx.y }}
          initial={{ opacity: 0.9, scale: 0.5 }}
          animate={{ opacity: 0, scale: 2.1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
        />
      );

    case "float":
      return (
        <motion.span
          className={`fx-float fx-float--${fx.tone}`}
          style={{ left: fx.x, top: fx.y }}
          initial={{ opacity: 0, y: 0, scale: 0.6 }}
          animate={{ opacity: 1, y: -54, scale: 1.15 }}
          exit={{ opacity: 0, y: -76, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 260, damping: 20 }}
        >
          {fx.value}
        </motion.span>
      );

    case "ghost":
      return (
        <CardGhost
          oid={fx.oid}
          card={fx.card}
          name={fx.name}
          caption={fx.caption}
          to={fx.to}
          cause={fx.cause}
          from={fx.from}
          toPoint={fx.toPoint}
          width={fx.width}
          duration={fx.duration}
          delay={fx.delay}
        />
      );

    case "vignette":
      // A hit landing on *you* should be felt at the edge of the screen, not
      // read off a numeral above an orb. Deliberately not anchored to the
      // player: it is the whole viewport that gets hit.
      return (
        <motion.div
          className={`fx-vignette fx-vignette--${fx.tone}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.14, ease: "easeOut" }}
        />
      );

    case "spotlight":
      return (
        <motion.div
          className={`fx-spotlight fx-spotlight--${fx.spell}`}
          data-testid={`spotlight-${fx.spell}`}
          initial={{ opacity: 0, scale: 0.7, rotate: -6 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          exit={{ opacity: 0, scale: 1.25, y: -30 }}
          transition={{ type: "spring", stiffness: 340, damping: 24 }}
        >
          {/* A trigger is not a card being cast, so it says so. Without the
              label a triggered ability and a spell look identical here. */}
          {fx.spell === "trigger" && <span className="fx-spotlight__kind">Triggered</span>}
          {/*
            The real card, not a name plate. The plate stays as the fallback --
            a countered spell has already left every zone the viewer can see,
            and a name is better than a gap.
          */}
          {fx.card ? (
            <div
              className="fx-spotlight__card"
              style={{ ["--card-w" as string]: cardWidthVar(CARD_SCALE.spotlight) }}
            >
              <StaticCard card={fx.card} variant="detail" />
            </div>
          ) : (
            <span className="fx-spotlight__name">{fx.name}</span>
          )}
        </motion.div>
      );

    case "banner":
      return (
        <motion.div
          className={`fx-banner fx-banner--${fx.tone}`}
          initial={{ opacity: 0, x: "-30%" }}
          animate={{ opacity: 1, x: "0%" }}
          exit={{ opacity: 0, x: "30%" }}
          transition={{ type: "spring", stiffness: 220, damping: 26 }}
        >
          <span className="fx-banner__text">{fx.text}</span>
        </motion.div>
      );
  }
}

/*
 * Screen shake.
 *
 * Two motion values written by the frame loop, never component state. The old
 * version called `setOffset` on every animation frame, which re-rendered the
 * entire board subtree -- ninety cards, the arrows, the panels -- sixty times a
 * second for the duration of every shake, i.e. at exactly the moment the board
 * was already busiest. It also made the shake read as mush, because each
 * offset had to wait for a React commit to reach the DOM.
 *
 * The values are module-level so `runFx` can drive a shake from a scheduled
 * effect without a ref threaded down to it, in the same spirit as `burst`.
 */
const shakeX = { current: null as null | ((v: number) => void) };
const shakeY = { current: null as null | ((v: number) => void) };

/**
 * `power` is 0..1.
 *
 * Decays linearly over 320ms and is re-randomised per frame rather than
 * oscillating on a wave: an impact is broadband, and a sine reads as the board
 * swaying.
 */
function shakeBoard(power: number): void {
  if (prefersReducedMotion()) return;
  const amp = Math.min(1, power) * 11;
  overTime(320, (t) => {
    const decay = 1 - t;
    shakeX.current?.((Math.random() - 0.5) * amp * decay * 2);
    shakeY.current?.((Math.random() - 0.5) * amp * decay * 2);
  });
}

/** Board offset, for `Table` to spread onto the wrapper's style. */
export function useScreenShake(beat: Beat | null): {
  x: ReturnType<typeof useMotionValue<number>>;
  y: ReturnType<typeof useMotionValue<number>>;
} {
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  useEffect(() => {
    shakeX.current = (v) => x.set(v);
    shakeY.current = (v) => y.set(v);
    return () => {
      shakeX.current = null;
      shakeY.current = null;
      x.set(0);
      y.set(0);
    };
  }, [x, y]);

  useEffect(() => {
    if (!beat?.shake) return;
    shakeBoard(beat.shake);
  }, [beat]);

  return { x, y };
}

/** Exported for the effect stories, which drive the layer without a queue. */
export { onFrame as __onFrame };
