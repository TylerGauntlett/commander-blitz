/**
 * UI-only state.
 *
 * Nothing here is ever sent to the server except through an action id. Staged
 * attackers and blockers live here until the player confirms; selection and
 * targeting are gestures, not rules.
 */

import { create } from "zustand";

/** How fast the narration queue plays back. */
export type Speed = "instant" | "fast" | "cinematic";

export const SPEED_MULTIPLIER: Record<Speed, number> = {
  instant: 1000,
  fast: 2,
  cinematic: 1,
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

  logOpen: boolean;
  peek: PeekTarget | null;
  error: string | null;
  speed: Speed;

  select: (oid: number | null) => void;
  hover: (oid: number | null) => void;
  beginTargeting: (oid: number, actionIds: string[]) => void;
  endTargeting: () => void;

  stageAttack: (attacker: number, defender: number) => void;
  unstageAttack: (attacker: number) => void;
  stageBlock: (blocker: number, attacker: number) => void;
  unstageBlock: (blocker: number) => void;
  clearStaging: () => void;

  openStackGroup: (key: string | null) => void;
  toggleLog: () => void;
  setPeek: (peek: PeekTarget | null) => void;
  setError: (message: string | null) => void;
  setSpeed: (speed: Speed) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedOid: null,
  hoveredOid: null,
  targetingActionIds: [],
  stagedAttacks: {},
  stagedBlocks: {},
  openStack: null,
  logOpen: true,
  peek: null,
  error: null,
  speed: storedSpeed(),

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
  setPeek: (peek) => set({ peek }),
  setError: (message) => set({ error: message }),
  setSpeed: (speed) => {
    rememberSpeed(speed);
    set({ speed });
  },
}));
