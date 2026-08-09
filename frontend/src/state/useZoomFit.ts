/**
 * The zoom, solved against the space the board actually has.
 *
 * `logic/zoomFit.ts` does the arithmetic and knows nothing about the DOM. This is
 * the half that measures, and the interesting part is not the measuring -- it is
 * **which measurements are allowed to be inputs.**
 *
 * A fit solver reads the layout and then changes it, so the obvious version feeds
 * back on itself and oscillates. Three couplings exist here and each is broken
 * deliberately:
 *
 * 1. **Lane height depends on card width, so it is never read.** Lane *width* is,
 *    because it comes from `minmax(0, 1fr)` grid tracks all the way down and does
 *    not move when cards resize. (Hence `scrollbar-gutter: stable` in `board.css`:
 *    a scrollbar appearing was the one thing that could move it.)
 * 2. **The hand's height comes out of the board's row**, because `.table__foot` is
 *    an `auto` grid row. So the hand is solved *first*, against a fraction of the
 *    table; that makes the foot definite, and the board then solves whatever is
 *    left. A cascade, not a loop -- the board's answer provably cannot change the
 *    foot's height.
 * 3. **The opponent row's height used to depend on the opponents' card size**, via
 *    `.play`'s `fit-content(58%)` reading their content. Solving their card size
 *    against that row would have been solving a value against a box it defines.
 *    `--pod-lanes-h` pins the box, which is why that change had to land first.
 *
 * The discipline in one line: *observe elements, but consume only the dimension
 * proven independent of the zoom.* Never observe `.play__mine .mat`, a
 * `.mat__lanes` height, or a `.lane` -- all three are outputs.
 */

import { type RefObject, useCallback, useEffect, useMemo, useState } from "react";
import type { GameView } from "../api/types";
import { CARD_SCALE, MAX_CARD_W, MIN_CARD_W, opponentCardScale } from "../logic/cardSize";
import {
  COMPACT_MAT,
  HAND_FAN_W,
  VIEWER_MAT,
  bandsFor,
  footprintsFor,
  lanesHeightIn,
  lanesWidthIn,
  solveBoardCardWidth,
  solveHandCardWidth,
} from "../logic/zoomFit";
import { useCardBase } from "./useCardBase";

/**
 * Most the foot may ever take of the table.
 *
 * A ceiling, not a target. The hand's real cap is its designed ratio (below), so
 * this only bites on a short viewport -- which is the case the old `--hand-scale`
 * media queries existed for, and the case that made the *board* spill instead when
 * they were removed.
 */
const HAND_FRACTION = 0.26;

/**
 * The foot's height past the hand's cards: `.hand`'s 44px droop allowance plus
 * `.table__foot`'s 16px of padding. The droop is for the arc's rotation, which is
 * a transform and contributes nothing to layout, so it has to be reserved.
 */
const FOOT_CHROME = 60;

/** `.play__opponents` gap between mats. */
const POD_GAP = 10;

/** How much narrower than the table the fan is allowed to be: `.hand`'s padding. */
const FAN_INSET = 20;

/** Absolute card widths, in px, per zone. */
export interface ZoomFit {
  /** The viewer's battlefield, as a multiple of `--card-w-base`. */
  board: number;
  /** Every opponent's battlefield, likewise. */
  pod: number;
  /** The hand, likewise. */
  hand: number;
  /** True when the zoom is pinned to the sizes that shipped before it existed. */
  locked: boolean;
}

interface Measurements {
  tableW: number;
  tableH: number;
  mineW: number;
  mineH: number;
  podW: number;
  podLanesH: number;
}

/**
 * Pinned zoom: every zone at the ratio it had before this feature.
 *
 * Two callers, and it matters that they are the same code path. `e2e` pins the
 * zoom so `layout.spec.ts`'s "the viewer's bands do not move" can keep asserting a
 * still board without the feature deliberately moving it. And jsdom has no
 * `ResizeObserver` at all, so every component test takes this branch and renders
 * the geometry it was written against.
 */
function locked(opponents: number): ZoomFit {
  return {
    board: CARD_SCALE.own,
    pod: opponentCardScale(opponents),
    hand: CARD_SCALE.hand,
    locked: true,
  };
}

/**
 * `?zoom=lock`, or `window.__AUTOMTG_ZOOM_LOCK`.
 *
 * A window flag rather than a persisted preference: `e2e/helpers.ts` sets it with
 * `addInitScript`, the same way it forces instant narration, and unlike a
 * localStorage key it cannot get stuck on for a real player who will then never
 * see the feature and have no idea why. The query parameter is for eyeballing the
 * before-and-after by hand.
 */
function zoomLocked(): boolean {
  if (typeof window === "undefined") return true;
  if ((window as { __AUTOMTG_ZOOM_LOCK?: boolean }).__AUTOMTG_ZOOM_LOCK === true) return true;
  try {
    return new URLSearchParams(window.location.search).get("zoom") === "lock";
  } catch {
    return false;
  }
}

function readLengthVar(name: string, fallback: number): number {
  if (typeof getComputedStyle !== "function") return fallback;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name);
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function useZoomFit(args: {
  state: GameView;
  actionableOids: ReadonlySet<number>;
  /** Opponent seat ids, in display order. */
  opponents: number[];
  handCount: number;
  tableRef: RefObject<HTMLElement>;
  mineRef: RefObject<HTMLElement>;
  podRef: RefObject<HTMLElement>;
}): ZoomFit {
  const { state, actionableOids, opponents, handCount, tableRef, mineRef, podRef } = args;
  const base = useCardBase();
  const pinned = zoomLocked();

  const [measured, setMeasured] = useState<Measurements | null>(null);

  const measure = useCallback(() => {
    const table = tableRef.current;
    const mine = mineRef.current;
    const pod = podRef.current;
    if (!table || !mine) return;
    const next: Measurements = {
      tableW: table.clientWidth,
      tableH: table.clientHeight,
      // Width and height only. Never the mat inside it, whose height is an output.
      mineW: mine.clientWidth,
      mineH: mine.clientHeight,
      podW: pod?.clientWidth ?? 0,
      podLanesH: readLengthVar("--pod-lanes-h", 228),
    };
    setMeasured((current) => {
      if (!current) return next;
      // A pixel of noise is not worth a re-solve, and re-solving on noise is how a
      // fit loop starts.
      const same = (Object.keys(next) as (keyof Measurements)[]).every(
        (key) => Math.abs(next[key] - current[key]) < 1,
      );
      return same ? current : next;
    });
  }, [tableRef, mineRef, podRef]);

  useEffect(() => {
    if (pinned) return;
    // jsdom has no ResizeObserver. Component tests take the pinned path instead,
    // and the solver itself is covered by pure unit tests.
    if (typeof ResizeObserver === "undefined") return;

    measure();
    const observer = new ResizeObserver(measure);
    for (const ref of [tableRef, mineRef, podRef]) {
      if (ref.current) observer.observe(ref.current);
    }
    return () => observer.disconnect();
  }, [pinned, measure, tableRef, mineRef, podRef]);

  return useMemo(() => {
    if (pinned || !measured) return locked(opponents.length);

    /*
     * 1. The hand, first, because the foot's height is taken out of the board's row.
     *
     * Its ceiling is the ratio it was designed at, so the hand never *grows* into
     * the board's space -- at 1600x950 the board has none to give. It grows only
     * because `--card-w-base` grew, which happens on a display with the room. What
     * this solve adds is the shrink: a fifteen-card fan, or a short viewport.
     */
    const handCeiling = Math.min(MAX_CARD_W, base * CARD_SCALE.hand);
    const handW = solveHandCardWidth(
      handCount,
      Math.min(HAND_FAN_W, measured.tableW - FAN_INSET),
      {
        heightPx: measured.tableH * HAND_FRACTION - FOOT_CHROME,
        minCardW: MIN_CARD_W,
        maxCardW: handCeiling,
      },
    );

    /*
     * 2. The viewer's board, against whatever `.play__mine` has left.
     *
     * The ceiling is a hand card at its designed ratio, not the hand's *solved*
     * width. A crowded hand shrinking must not drag the board down with it -- the
     * board is not the thing that is crowded -- but the board should still never
     * out-size the zone whose whole job is to be readable.
     */
    const boardCeiling = handCeiling;
    const viewerLanesW = lanesWidthIn(measured.mineW, VIEWER_MAT);
    const boardW = solveBoardCardWidth(
      bandsFor(footprintsFor(state, state.seat, actionableOids), viewerLanesW, {
        hideEmpty: false,
        labels: VIEWER_MAT.labels,
      }),
      {
        heightPx: lanesHeightIn(measured.mineH, VIEWER_MAT),
        minCardW: MIN_CARD_W,
        maxCardW: boardCeiling,
      },
    );

    /*
     * 3. The opponents, inside the box `--pod-lanes-h` pins for them.
     *
     * Their ceiling is the viewer's solved width times the seat ratio, so they
     * scale *with* the viewer's zoom and keep the proportion the board was designed
     * at. Capping them at today's absolute size instead would have meant the
     * roadmap's "both user and CPU" quietly becoming "user only"; capping them at
     * `MAX_CARD_W` would let a one-opponent pod with two lands render cards bigger
     * than the viewer's own, which is the wrong hierarchy in the wrong direction.
     *
     * Every mat is solved, and the *smallest* answer wins for all of them. Mats
     * sitting side by side at different card sizes would read as a broken layout
     * rather than as differently-full boards, so the fullest opponent sets the size
     * the row renders at -- which is also the only shape `Table` can express, since
     * one `cardScale` goes to every compact mat.
     */
    const count = Math.max(1, opponents.length);
    const podCeiling = boardW * opponentCardScale(opponents.length);
    // Mats are `flex: 1 1 0`, so they share the row evenly. Their 288px `min-width`
    // can win on a narrow viewport, at which point the row scrolls horizontally and
    // each mat is really *wider* than this -- so the solve is conservative there
    // rather than wrong, which is the direction to be wrong in.
    const podMatW = (measured.podW - (count - 1) * POD_GAP) / count;
    const podLanesW = lanesWidthIn(podMatW, COMPACT_MAT);
    const podW = opponents.length
      ? Math.min(
          ...opponents.map((pid) =>
            solveBoardCardWidth(
              bandsFor(footprintsFor(state, pid, actionableOids), podLanesW, {
                hideEmpty: true,
                labels: COMPACT_MAT.labels,
              }),
              // `--pod-lanes-h` *is* the lanes' box, so it is the budget as it
              // stands -- no mat chrome to subtract.
              {
                heightPx: measured.podLanesH,
                minCardW: MIN_CARD_W,
                maxCardW: podCeiling,
              },
            ),
          ),
        )
      : podCeiling;

    // Returned as multiples of the base, because that is what `cardWidthVar` and
    // `cardWidthPx` both take -- one coefficient per zone, read by both languages.
    return {
      board: boardW / base,
      pod: podW / base,
      hand: handW / base,
      locked: false,
    };
  }, [pinned, measured, base, state, actionableOids, opponents, handCount]);
}
