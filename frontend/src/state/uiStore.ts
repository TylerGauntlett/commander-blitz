/**
 * UI-only state.
 *
 * Nothing here is ever sent to the server except through an action id. Staged
 * attackers and blockers live here until the player confirms; selection and
 * targeting are gestures, not rules.
 */

import { create } from "zustand";
import type { ImageMap, SeatImages } from "../logic/cardArt";

/** How fast the narration queue plays back. */
export type Speed = "instant" | "fast" | "cinematic";

/**
 * Divisors applied to every beat's hold and every FX lifetime.
 *
 * Halved in cycle 3: the game moved too fast to follow at either watchable
 * setting, so what used to be the default (2) is now the slow setting and the
 * new default plays at what used to be "cinematic". The per-beat holds in
 * `logic/events.ts` were left alone deliberately -- they encode the *relative*
 * weight of events (a death matters more than a draw), and rescaling them one
 * by one would have meant re-deciding twenty judgements to change one.
 *
 * `instant` is not a speed so much as a bypass: `narration.ts` short-circuits on
 * it and drops beats rather than holding them for ~0ms, because even a zero
 * timer costs a React tick per beat.
 */
export const SPEED_MULTIPLIER: Record<Speed, number> = {
  instant: 1000,
  fast: 1,
  cinematic: 0.5,
};

/**
 * Playback speed, with no control on screen.
 *
 * There was a three-way selector in the action panel and it is gone. Two
 * reasons, and the second is the real one. It took a third of the tool strip's
 * width, which is a fixed 304px rail, and that is what pushed the quit button
 * off the end. And in a multiplayer game it is a confusing thing to offer at
 * all: it changes only *your* narration while everyone else plays at theirs, so
 * "slower" does not mean the game slows down, it means you fall further behind a
 * board that has already moved on.
 *
 * The value survives because narration still has to be paced, and it is still
 * read from storage so `e2e/helpers.ts` can force `instant` and a run does not
 * spend its time watching beats. There is simply no longer a way to set it from
 * inside the game.
 */
const SPEED_KEY = "automtg.speed";
const MUTED_KEY = "automtg.muted";

function storedSpeed(): Speed {
  try {
    const saved = localStorage.getItem(SPEED_KEY);
    if (saved === "instant" || saved === "fast" || saved === "cinematic") return saved;
  } catch {
    // Private mode, or no DOM at all under vitest. The default is fine.
  }
  return "fast";
}

/**
 * Sound starts on.
 *
 * It used to start off, on the reasoning that a page making noise before being
 * asked is a bad guest. The cost of that was that essentially nobody ever heard
 * the game: every impact, every death toll and every one of the gesture voices
 * that make the board feel responsive was behind a toggle in the tool strip
 * that gave no hint there was anything to turn on.
 *
 * The original worry is handled anyway, and not by this flag. Browsers park an
 * `AudioContext` until a user gesture, and `audio/sfx.ts` builds one lazily on
 * the first sound -- so nothing can make a noise before the player has clicked
 * something regardless of what this returns. The e2e suite mutes explicitly.
 */
function storedMuted(): boolean {
  try {
    return localStorage.getItem(MUTED_KEY) === "on";
  } catch {
    // No storage at all -- private mode, or vitest with no DOM. Stay quiet:
    // a test run is the one context where silence is the safer default.
    return true;
  }
}

function rememberMuted(muted: boolean): void {
  try {
    localStorage.setItem(MUTED_KEY, muted ? "on" : "off");
  } catch {
    // As above.
  }
}

export interface PeekTarget {
  pid: number;
  zone: "graveyard" | "exile" | "command" | "hand";
}

interface UiState {
  /** Card the player has picked up, either to target with or to inspect. */
  selectedOid: number | null;
  /** Card under the pointer, drawn large in the preview panel. */
  hoveredOid: number | null;
  /** Actions the current selection could still resolve to, awaiting a target. */
  targetingActionIds: string[];
  /** attacker oid -> defending player id, staged before "Confirm attacks". */
  stagedAttacks: Record<number, number>;
  /** blocker oid -> attacker oid, staged before "Confirm blocks". */
  stagedBlocks: Record<number, number>;
  /** Stack group currently fanned open, keyed by `stackKey`. */
  openStack: string | null;

  /**
   * Card art, fetched once and kept forever.
   *
   * Lives here rather than in react-query context because `CardFace` is
   * rendered bare in unit tests with no providers around it. `null` is the
   * "not loaded" state and makes the face draw no art band at all -- which is
   * exactly the layout that shipped before art existed.
   */
  images: ImageMap;
  /**
   * Per-seat overrides: the printings an imported deck's author chose. Layered
   * over `images` by `artUrlFor` and friends; `null` until the map arrives.
   */
  seatImages: SeatImages;

  /** The log section in the left rail is expanded. Desktop only. */
  logOpen: boolean;
  /**
   * The log is up as an overlay over the board. Handheld only.
   *
   * A separate flag from `logOpen` rather than a reuse of it, because the two
   * mean genuinely different things and want opposite defaults. In the rail,
   * "open" is a section that is expanded and costs the player nothing, so it
   * starts open. As an overlay it covers the board, so arriving at the table
   * with it up would hide the game behind its own history -- it starts closed.
   */
  logOverlay: boolean;
  /**
   * Whose board is drawn in the viewer's lane area, or `null` for your own.
   *
   * At 1280x800 an opponent is a 96px seat and their cards are not drawn at
   * all, so "let me actually look at that board" needs an answer -- and the one
   * a pod wants is not a peek but a *place*: you go and stand at their seat,
   * read it, and come back. Pressing a seat latches it here.
   *
   * IN THE STORE AND NOT IN `Table`, because four things read it: the unwind on
   * `B`, `PlayerMat` (which mat draws lanes), `OpponentSeat` (which seat wears
   * the ring), and the strip that says whose board you are looking at. The R2
   * hold is deliberately NOT here -- a hold has no meaning across a re-render,
   * and a hold kept in a store is a hold that can get stuck.
   */
  viewingPid: number | null;
  peek: PeekTarget | null;
  error: string | null;
  speed: Speed;
  muted: boolean;

  select: (oid: number | null) => void;
  hover: (oid: number | null) => void;
  beginTargeting: (oid: number, actionIds: string[]) => void;
  /**
   * Narrow an in-flight selection to the actions still in play.
   *
   * Picking a target answers only *one* of the questions a click can be asking.
   * Into the Roil aimed at a creature is still two actions -- kicked and not --
   * and taking the first would silently spend the player's kicker decision for
   * them. This keeps the selection open on what is left so the panel can ask.
   */
  narrowTargeting: (actionIds: string[]) => void;
  endTargeting: () => void;

  stageAttack: (attacker: number, defender: number) => void;
  unstageAttack: (attacker: number) => void;
  stageBlock: (blocker: number, attacker: number) => void;
  unstageBlock: (blocker: number) => void;
  clearStaging: () => void;

  setImages: (images: ImageMap, seatImages?: SeatImages) => void;
  openStackGroup: (key: string | null) => void;
  toggleLog: () => void;
  toggleLogOverlay: () => void;
  /** Look at a seat's board, or `null` to come back to your own. */
  setViewing: (pid: number | null) => void;
  setPeek: (peek: PeekTarget | null) => void;
  setError: (message: string | null) => void;
  toggleMuted: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedOid: null,
  hoveredOid: null,
  targetingActionIds: [],
  stagedAttacks: {},
  stagedBlocks: {},
  openStack: null,
  images: null,
  seatImages: null,
  logOpen: true,
  logOverlay: false,
  viewingPid: null,
  peek: null,
  error: null,
  speed: storedSpeed(),
  muted: storedMuted(),

  select: (oid) => set({ selectedOid: oid }),
  hover: (oid) => set({ hoveredOid: oid }),

  beginTargeting: (oid, actionIds) => set({ selectedOid: oid, targetingActionIds: actionIds }),
  narrowTargeting: (actionIds) => set({ targetingActionIds: actionIds }),
  endTargeting: () => set({ targetingActionIds: [], selectedOid: null }),

  stageAttack: (attacker, defender) =>
    set((s) => ({ stagedAttacks: { ...s.stagedAttacks, [attacker]: defender } })),
  unstageAttack: (attacker) =>
    set((s) => {
      const next = { ...s.stagedAttacks };
      delete next[attacker];
      return { stagedAttacks: next };
    }),

  stageBlock: (blocker, attacker) =>
    set((s) => ({ stagedBlocks: { ...s.stagedBlocks, [blocker]: attacker } })),
  unstageBlock: (blocker) =>
    set((s) => {
      const next = { ...s.stagedBlocks };
      delete next[blocker];
      return { stagedBlocks: next };
    }),

  clearStaging: () =>
    set({
      stagedAttacks: {},
      stagedBlocks: {},
      selectedOid: null,
      targetingActionIds: [],
      openStack: null,
    }),

  openStackGroup: (key) => set({ openStack: key }),
  toggleLog: () => set((s) => ({ logOpen: !s.logOpen })),
  toggleLogOverlay: () => set((s) => ({ logOverlay: !s.logOverlay })),
  setViewing: (pid) => set({ viewingPid: pid }),
  setImages: (images, seatImages = null) => set({ images, seatImages }),
  setPeek: (peek) => set({ peek }),
  setError: (message) => set({ error: message }),
  toggleMuted: () =>
    set((s) => {
      rememberMuted(!s.muted);
      return { muted: !s.muted };
    }),
}));
