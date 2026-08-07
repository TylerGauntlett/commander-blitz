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
 */

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { Beat, BeatAnchor, Tone } from "../../logic/events";
import type { LiveBeat } from "../../state/narration";
import { SPEED_MULTIPLIER, type Speed } from "../../state/uiStore";

/** How long a numeral floats, before speed scaling. */
const FLOAT_MS = 1100;
const BANNER_MS = 900;
const SPOTLIGHT_MS = 800;
const FLASH_MS = 600;

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
}

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

interface Props {
  beat: LiveBeat | null;
  speed: Speed;
  boardRef: React.RefObject<HTMLElement>;
}

export function FxLayer({ beat, speed, boardRef }: Props) {
  const [floats, setFloats] = useState<FloatFx[]>([]);
  const [flashes, setFlashes] = useState<FlashFx[]>([]);
  const [banners, setBanners] = useState<BannerFx[]>([]);
  const [spotlights, setSpotlights] = useState<SpotlightFx[]>([]);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const id of pending) clearTimeout(id);
    };
  }, []);

  useEffect(() => {
    if (!beat) return;
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
      };
      setSpotlights((current) => [...current, fx]);
      expire(() => setSpotlights((c) => c.filter((s) => s.uid !== fx.uid)), SPOTLIGHT_MS);
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

      <AnimatePresence>
        {spotlights.map((fx) => (
          <motion.div
            key={`spot-${fx.uid}`}
            className="fx-spotlight"
            initial={{ opacity: 0, scale: 0.7, rotate: -6 }}
            animate={{ opacity: 1, scale: 1, rotate: 0 }}
            exit={{ opacity: 0, scale: 1.25, y: -30 }}
            transition={{ type: "spring", stiffness: 340, damping: 24 }}
          >
            {fx.name}
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
