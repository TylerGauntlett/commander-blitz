/**
 * The lit hall every menu screen stands in.
 *
 * Extracted from `HomeScreen` the moment a second screen needed it, and the
 * extraction is the feature rather than a tidy-up. The front door was ported
 * from the door round's 01 'The Hand' and came out looking like a game; the
 * pod lobby and the deck catalogue it opens onto were still the flat panels
 * that shipped. Pressing PLAY therefore took the player from a game to a
 * settings dialog -- which is not experienced as two screens with different
 * budgets, it is experienced as the game ending one second after it started.
 *
 * So this owns the four things all three screens have to agree on:
 *
 *   1. `--du`, the stage scale. `stageScale()` is exactly 1 at 1280x800, so a
 *      Steam Deck gets the composition the mockup round measured, to the pixel.
 *      The room is full-bleed; only the furniture scales.
 *   2. `--lit` and its three derivatives -- the colour the room takes. A screen
 *      hands in a two-tone hue and everything from the floor sigil to the motes
 *      to a selected card's glow follows it, through CSS inheritance rather
 *      than through React.
 *   3. The drawn hall, the floor sigil, the pool of light, and the motes --
 *      which are `components/ui/Motes.tsx` now, because the board wanted them
 *      too and one drifting speck defined twice is how two screens drift apart.
 *   4. `data-du`, so a test can read the scale the screen actually resolved to
 *      rather than recomputing it and asserting against its own arithmetic.
 *
 * WHAT IT DOES NOT OWN is anything selectable. Every screen's content is its
 * own, and none of it is registered here -- the three cards of the door, the
 * four chairs of the pod and the shelf of decks are native controls, so
 * `input/stops.ts` picks them up with no registration and the whole pad layer
 * comes with them.
 */

import type { CSSProperties, ReactNode } from "react";
import { useLayoutEffect, useRef } from "react";
import { stageScale } from "../../logic/doorRow";
import { Motes } from "../ui/Motes";
import { RoomFloor, RoomGround } from "./doorArt";

/** A hex to `rgb(r g b / a)`, so one token can be both a line and a glow. */
export function soft(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255} / ${alpha})`;
}

/** The palette a screen lights its room with: a key colour and a floor colour. */
export type Hue = readonly [string, string];

/** The pod's own light: warm gold, the colour of a table with a game on it. */
export const POD_HUE: Hue = ["#d8a63c", "#8a3a2e"];
/** The catalogue's: cold green, the colour the door's Decks card lights. */
export const SHELF_HUE: Hue = ["#3f9e93", "#2b5a86"];

interface Props {
  /** What colour this screen makes the hall. Changes fade over `--t-room`. */
  hue: Hue;
  /** Extra classes -- `door`, `pod`, `shelf`. Always alongside `room`. */
  className?: string;
  testId?: string;
  /**
   * Where the floor sigil's centre hangs, as a percentage of the stage.
   *
   * A screen's furniture is not always at the door's 40.25%, and a sigil
   * centred under nothing is a rug in the wrong room.
   */
  floorY?: string;
  /** Where the pool of light is brightest, likewise. */
  washY?: string;
  children: ReactNode;
  /**
   * Called when the stage scale changes, for a screen whose own layout is
   * arithmetic rather than CSS -- the door's row is the only one.
   */
  onScale?: (du: number) => void;
}

export function Room({ hue, className, testId, floorY, washY, children, onScale }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  /* Read by the resize handler, which must not be re-bound every time a screen
     changes colour -- and a stale closure here would call last render's
     callback with this render's size. */
  const scaleRef = useRef(onScale);
  scaleRef.current = onScale;

  /*
   * THE STAGE SCALES; THE MOCKUP'S FIXED DECK DOES NOT.
   *
   * The mockup is a fixed 1280x800 scaled to the window, which is right for a
   * review surface and wrong here -- at 1600x950 that is a blurry 1280 in a
   * letterbox. `--du` is the same number applied to the furniture instead.
   * Written straight to the element rather than held in state, because screens
   * that paint imperatively read it from a ref and a re-render would be a frame
   * late.
   */
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const fitStage = () => {
      const du = stageScale(el.clientWidth, el.clientHeight);
      el.style.setProperty("--du", String(du));
      el.dataset.du = du.toFixed(3);
      scaleRef.current?.(du);
    };
    fitStage();
    /* jsdom has no `ResizeObserver`, which is the same hole `useZoomFit.ts:365`
       guards. A window listener is the honest fallback rather than a no-op: the
       stage IS the window here, so the two only differ when something else on
       the page reflows, which on these screens is nothing. */
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", fitStage);
      return () => window.removeEventListener("resize", fitStage);
    }
    const observer = new ResizeObserver(fitStage);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  /* The room's colour, written to the stage rather than to `:root`, so the tint
     is a property of this screen and not of the document. */
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    el.style.setProperty("--lit", hue[0]);
    el.style.setProperty("--lit-soft", soft(hue[0], 0.36));
    el.style.setProperty("--lit2-soft", soft(hue[1], 0.24));
    el.style.setProperty("--lit-beam", soft(hue[0], 0.13));
  }, [hue]);

  const vars: CSSProperties = {};
  if (floorY) (vars as Record<string, string>)["--floor-y"] = floorY;
  if (washY) (vars as Record<string, string>)["--wash-y"] = washY;

  return (
    <div
      className={className ? `room ${className}` : "room"}
      data-testid={testId}
      ref={rootRef}
      style={vars}
    >
      <RoomGround />
      <RoomFloor />
      <div className="room__wash" aria-hidden="true" />

      {/* Sixteen, the full field: a menu screen has nothing else moving on it.
          They take `--lit` from this element, so they change colour with the
          room. See `components/ui/Motes.tsx`. */}
      <Motes />

      {children}
    </div>
  );
}
