/**
 * UI-only state.
 *
 * Nothing here is ever sent to the server except through an action id. Staged
 * attackers and blockers live here until the player confirms; lane order is
 * purely cosmetic.
 */

import { create } from "zustand";

interface UiState {
  /** Card currently selected for targeting, or being dragged. */
  selectedOid: number | null;
  /** Card hovered for the detail panel. */
  hoveredOid: number | null;
  /** attacker oid -> defending player id, staged before "Confirm attacks". */
  stagedAttacks: Record<number, number>;
  /** blocker oid -> attacker oid, staged before "Confirm blocks". */
  stagedBlocks: Record<number, number>;
  /** True while the player is picking a target for a multi-option action. */
  targetingActionIds: string[];
  logOpen: boolean;
  peekZone: { pid: number; zone: string } | null;
  error: string | null;

  select: (oid: number | null) => void;
  hover: (oid: number | null) => void;
  stageAttack: (attacker: number, defender: number) => void;
  unstageAttack: (attacker: number) => void;
  stageBlock: (blocker: number, attacker: number) => void;
  unstageBlock: (blocker: number) => void;
  clearStaging: () => void;
  beginTargeting: (actionIds: string[]) => void;
  endTargeting: () => void;
  toggleLog: () => void;
  peek: (pid: number, zone: string) => void;
  closePeek: () => void;
  setError: (message: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedOid: null,
  hoveredOid: null,
  stagedAttacks: {},
  stagedBlocks: {},
  targetingActionIds: [],
  logOpen: true,
  peekZone: null,
  error: null,

  select: (oid) => set({ selectedOid: oid }),
  hover: (oid) => set({ hoveredOid: oid }),

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

  clearStaging: () => set({ stagedAttacks: {}, stagedBlocks: {}, selectedOid: null }),

  beginTargeting: (actionIds) => set({ targetingActionIds: actionIds }),
  endTargeting: () => set({ targetingActionIds: [], selectedOid: null }),

  toggleLog: () => set((s) => ({ logOpen: !s.logOpen })),
  peek: (pid, zone) => set({ peekZone: { pid, zone } }),
  closePeek: () => set({ peekZone: null }),
  setError: (message) => set({ error: message }),
}));
