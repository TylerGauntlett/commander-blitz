/**
 * Everything that flies over the board: damage numerals, banners, spotlights.
 *
 * `useNarration` hands out one beat at a time, but effects need to *overlap* --
 * a combat step where four numerals appear in sequence should read as one
 * motion, not four slides. So this layer keeps its own short-lived list of
 * what it has been shown and lets each entry expire on its own clock.
 *
 * Anchors are resolved from the DOM (`data-oid`, `data-player`) at the moment
 * the beat plays, because the cards are inside springs and layout flights and
 * there is no reliable static position to precompute.
 *
 * Departing cards are the exception, and they are why `logic/cardRects.ts`
 * exists. A card being destroyed is one the board has *stopped* drawing -- the
 * new state is committed before the beats are pushed -- so there is no element
 * left to anchor to and the DOM lookup returns null. That is why a dying
 * permanent used to produce no effect at all despite `dies` carrying a flash.
 * Its last known box is posted here by `Card` on unmount instead.
 */

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { CardView, GameView } from "../../api/types";
import { play } from "../../audio/sfx";
import { recall } from "../../logic/cardRects";
import { CARD_SCALE, cardWidthVar } from "../../logic/cardSize";
import type { Beat, BeatAnchor, ExitFx, Tone } from "../../logic/events";
import { findCard, findCardByDefId } from "../../logic/zoneGrouping";
import type { LiveBeat } from "../../state/narration";
import { SPEED_MULTIPLIER, type Speed, useUiStore } from "../../state/uiStore";
import { StaticCard } from "./Card";
import { CardGhost } from "./CardGhost";

/** How long a numeral floats, before speed scaling. */
const FLOAT_MS = 1100;
const BANNER_MS = 900;
const SPOTLIGHT_MS = 800;
const FLASH_MS = 600;
/** The whole of a departure: the pause on the caption plus the fall. */
const GHOST_MS = 900;
/**
 * How long a wipe takes to sweep, regardless of how wide it is.
 *
 * Ten deaths at a comfortable 60ms apart is 600ms of stagger on top of a beat
 * the queue has already moved past, so the gap closes as the board gets wider.
 */
const GHOST_SWEEP_MS = 400;

interface Positioned {
  uid: number;
  x: number;
  y: number;
}

interface FloatFx extends Positioned {
  value: string;
  tone: Tone;
}

interface FlashFx extends Positioned {
  tone: Tone;
}

interface BannerFx {
  uid: number;
  text: string;
  tone: Tone;
}

interface SpotlightFx {
  uid: number;
  name: string;
  controller: number;
  kind: "spell" | "trigger";
  /** The real card, when one can be found. Null falls back to a name plate. */
  card: CardView | null;
}

interface GhostFx {
  /** Unique per ghost, not per beat: a wipe puts several in one beat. */
  key: string;
  oid: number;
  card: CardView | null;
  name: string;
  caption: string;
  to: string;
  from: { x: number; y: number };
  toPoint: { x: number; y: number };
  width: number;
  duration: number;
  delay: number;
}

/** How wide a spotlit card is drawn. Big enough to read the rules text. */
/** Ratio of `--card-w-base`; see logic/cardSize.ts. */

function anchorPoint(anchor: BeatAnchor, origin: DOMRect): { x: number; y: number } | null {
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

/** The board-relative centre of the first element matching a selector. */
function centreOf(selector: string, origin: DOMRect): { x: number; y: number } | null {
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
function pilePoint(exit: ExitFx, origin: DOMRect): { x: number; y: number } | null {
  const pile = centreOf(`[data-testid="pile-${exit.owner}-${exit.to}"]`, origin);
  if (pile) return pile;
  // The library is drawn as a pile named "library", and there is no pile for
  // the stack at all -- fall back to the owner's orb, which is beside both.
  return centreOf(`[data-player="${exit.owner}"]`, origin);
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
  uid: number,
  state: GameView,
  origin: DOMRect,
  multiplier: number,
): GhostFx | null {
  const rect = recall(exit.oid);
  if (!rect) return null;
  const toPoint = pilePoint(exit, origin);
  if (!toPoint) return null;

  return {
    key: `${uid}-${exit.oid}-${index}`,
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
  const [floats, setFloats] = useState<FloatFx[]>([]);
  const [flashes, setFlashes] = useState<FlashFx[]>([]);
  const [banners, setBanners] = useState<BannerFx[]>([]);
  const [spotlights, setSpotlights] = useState<SpotlightFx[]>([]);
  const [ghosts, setGhosts] = useState<GhostFx[]>([]);
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
    if (beat.sound && !mutedRef.current) play(beat.sound);
    const board = boardRef.current;
    if (!board) return;
    const origin = board.getBoundingClientRect();
    const multiplier = SPEED_MULTIPLIER[speed];
    const expire = (fn: () => void, ms: number) => {
      const id = window.setTimeout(fn, ms / multiplier);
      timers.current.push(id);
    };

    if (beat.float) {
      const point = anchorPoint(beat.float.anchor, origin);
      if (point) {
        const fx: FloatFx = {
          uid: beat.uid,
          x: point.x,
          y: point.y,
          value: beat.float.value,
          tone: beat.float.tone,
        };
        setFloats((current) => [...current, fx]);
        expire(() => setFloats((c) => c.filter((f) => f.uid !== fx.uid)), FLOAT_MS);
      }
    }

    if (beat.flash) {
      const point = anchorPoint(beat.flash.anchor, origin);
      if (point) {
        const fx: FlashFx = {
          uid: beat.uid,
          x: point.x,
          y: point.y,
          tone: beat.flash.tone,
        };
        setFlashes((current) => [...current, fx]);
        expire(() => setFlashes((c) => c.filter((f) => f.uid !== fx.uid)), FLASH_MS);
      }
    }

    if (beat.banner) {
      const fx: BannerFx = { uid: beat.uid, text: beat.banner.text, tone: beat.banner.tone };
      setBanners((current) => [...current, fx]);
      expire(() => setBanners((c) => c.filter((b) => b.uid !== fx.uid)), BANNER_MS);
    }

    if (beat.spotlight) {
      const fx: SpotlightFx = {
        uid: beat.uid,
        name: beat.spotlight.name,
        controller: beat.spotlight.controller,
        kind: beat.spotlight.kind ?? "spell",
        // Resolved once, here, rather than on every render: by the time this
        // expires the card may well have moved zones again.
        card: beat.spotlight.cardId
          ? findCardByDefId(stateRef.current, beat.spotlight.cardId, beat.spotlight.controller)
          : null,
      };
      setSpotlights((current) => [...current, fx]);
      expire(() => setSpotlights((c) => c.filter((s) => s.uid !== fx.uid)), SPOTLIGHT_MS);
    }

    if (beat.exits?.length) {
      const exits = beat.exits;
      const fx = exits
        .map((exit, i) =>
          ghostFor(exit, i, exits.length, beat.uid, stateRef.current, origin, multiplier),
        )
        .filter((ghost): ghost is GhostFx => ghost !== null);
      if (fx.length > 0) {
        const keys = new Set(fx.map((ghost) => ghost.key));
        setGhosts((current) => [...current, ...fx]);
        // The last ghost's own delay is already baked into `delay`, so the
        // whole sweep is gone one flight after the last one starts. `expire`
        // divides by the multiplier again, which is why this is the raw value.
        const sweep = GHOST_MS + Math.min(60, GHOST_SWEEP_MS / exits.length) * exits.length;
        expire(() => setGhosts((c) => c.filter((ghost) => !keys.has(ghost.key))), sweep);
      }
    }
  }, [beat, speed, boardRef]);

  return (
    <div className="fx" aria-hidden="true" data-testid="fx-layer">
      <AnimatePresence>
        {flashes.map((fx) => (
          <motion.span
            key={`flash-${fx.uid}`}
            className={`fx-flash fx-flash--${fx.tone}`}
            style={{ left: fx.x, top: fx.y }}
            initial={{ opacity: 0.9, scale: 0.5 }}
            animate={{ opacity: 0, scale: 2.1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
          />
        ))}
      </AnimatePresence>

      <AnimatePresence>
        {floats.map((fx) => (
          <motion.span
            key={`float-${fx.uid}`}
            className={`fx-float fx-float--${fx.tone}`}
            style={{ left: fx.x, top: fx.y }}
            initial={{ opacity: 0, y: 0, scale: 0.6 }}
            animate={{ opacity: 1, y: -54, scale: 1.15 }}
            exit={{ opacity: 0, y: -76, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 260, damping: 20 }}
          >
            {fx.value}
          </motion.span>
        ))}
      </AnimatePresence>

      {/*
        Below the spotlights and banners in the stacking order, because a
        departure is a consequence: the spell that caused it is what the player
        is being asked to read first.
      */}
      <AnimatePresence>
        {ghosts.map((fx) => (
          <CardGhost
            key={fx.key}
            oid={fx.oid}
            card={fx.card}
            name={fx.name}
            caption={fx.caption}
            to={fx.to}
            from={fx.from}
            toPoint={fx.toPoint}
            width={fx.width}
            duration={fx.duration}
            delay={fx.delay}
          />
        ))}
      </AnimatePresence>

      <AnimatePresence>
        {spotlights.map((fx) => (
          <motion.div
            key={`spot-${fx.uid}`}
            className={`fx-spotlight fx-spotlight--${fx.kind}`}
            data-testid={`spotlight-${fx.kind}`}
            initial={{ opacity: 0, scale: 0.7, rotate: -6 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 1.25, y: -30 }}
            transition={{ type: "spring", stiffness: 340, damping: 24 }}
          >
            {/* A trigger is not a card being cast, so it says so. Without the
                label a triggered ability and a spell look identical here. */}
            {fx.kind === "trigger" && <span className="fx-spotlight__kind">Triggered</span>}
            {/*
              The real card, not a name plate. `Beat.spotlight` has carried a
              card id since cycle 1 and nothing had ever drawn it; the stack
              panel proved `StaticCard` works away from the battlefield. The
              plate stays as the fallback -- a countered spell has already left
              every zone the viewer can see, and a name is better than a gap.
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
        ))}
      </AnimatePresence>

      <AnimatePresence>
        {banners.map((fx) => (
          <motion.div
            key={`banner-${fx.uid}`}
            className={`fx-banner fx-banner--${fx.tone}`}
            initial={{ opacity: 0, x: "-30%" }}
            animate={{ opacity: 1, x: "0%" }}
            exit={{ opacity: 0, x: "30%" }}
            transition={{ type: "spring", stiffness: 220, damping: 26 }}
          >
            <span className="fx-banner__text">{fx.text}</span>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

/** Screen shake, driven off the same beats. Applied to the board wrapper. */
export function useScreenShake(beat: Beat | null): { x: number; y: number } {
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (!beat?.shake) return;
    const power = Math.min(1, beat.shake) * 9;
    let frame = 0;
    const started = performance.now();
    const tick = () => {
      const elapsed = performance.now() - started;
      const decay = Math.max(0, 1 - elapsed / 320);
      if (decay <= 0) {
        setOffset({ x: 0, y: 0 });
        return;
      }
      setOffset({
        x: (Math.random() - 0.5) * power * decay * 2,
        y: (Math.random() - 0.5) * power * decay * 2,
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      setOffset({ x: 0, y: 0 });
    };
  }, [beat]);

  return offset;
}
