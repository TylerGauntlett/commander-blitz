/**
 * UI-only state.
 *
 * Nothing here is ever sent to the server except through an action id. Staged
 * attackers and blockers live here until the player confirms; selection and
 * targeting are gestures, not rules.
 */

import { create } from "zustand";
import type { ImageMap } from "../logic/cardArt";

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
 * Animation speed survives a reload.
 *
 * It is a preference, not session state -- somebody who has decided they want
 * instant should not have to say so again every game. It also means the setting
 * can be chosen before the page loads, which is the only way to reach it while
 * a modal decision is on screen.
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

function rememberSpeed(speed: Speed): void {
  try {
    localStorage.setItem(SPEED_KEY, speed);
  } catch {
    // Not being able to remember a preference is not worth an error.
  }
}

/**
 * Sound starts off.
 *
 * A page that makes noise before being asked is a bad guest, browsers block
 * autoplay before a gesture anyway, and the e2e suite would otherwise be
 * synthesising audio on every run.
 */
function storedMuted(): boolean {
  try {
    return localStorage.getItem(MUTED_KEY) !== "off";
  } catch {
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

  logOpen: boolean;
  peek: PeekTarget | null;
  error: string | null;
  speed: Speed;
  muted: boolean;

  select: (oid: number | null) => void;
  hover: (oid: number | null) => void;
  beginTargeting: (oid: number, actionIds: string[]) => void;
  endTargeting: () => void;

  stageAttack: (attacker: number, defender: number) => void;
  unstageAttack: (attacker: number) => void;
  stageBlock: (blocker: number, attacker: number) => void;
  unstageBlock: (blocker: number) => void;
  clearStaging: () => void;

  setImages: (images: ImageMap) => void;
  openStackGroup: (key: string | null) => void;
  toggleLog: () => void;
  setPeek: (peek: PeekTarget | null) => void;
  setError: (message: string | null) => void;
  setSpeed: (speed: Speed) => void;
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
  logOpen: true,
  peek: null,
  error: null,
  speed: storedSpeed(),
  muted: storedMuted(),

  select: (oid) => set({ selectedOid: oid }),
  hover: (oid) => set({ hoveredOid: oid }),

  beginTargeting: (oid, actionIds) => set({ selectedOid: oid, targetingActionIds: actionIds }),
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
  setImages: (images) => set({ images }),
  setPeek: (peek) => set({ peek }),
  setError: (message) => set({ error: message }),
  setSpeed: (speed) => {
    rememberSpeed(speed);
    set({ speed });
  },
  toggleMuted: () =>
    set((s) => {
      rememberMuted(!s.muted);
      return { muted: !s.muted };
    }),
}));
