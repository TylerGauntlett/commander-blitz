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
 *    The box is pinned instead, and pinned to the *viewport* -- `tableH` and the
 *    seat count, and nothing else that a game can move. See
 *    `solvePodLanesHeight`, which also records why "independent of every card
 *    size" was not a strong enough test to pin it by.
 *
 * The discipline in one line: *observe elements, but consume only the dimension
 * proven independent of the zoom.* Never observe `.play__mine .mat`, a
 * `.mat__lanes` height, or a `.lane` -- all three are outputs.
 */

import { type RefObject, useCallback, useEffect, useMemo, useState } from "react";
import type { GameView } from "../api/types";
import {
  CARD_SCALE,
  HANDHELD_MIN_CARD_W,
  MAX_CARD_W,
  MIN_CARD_W,
  opponentCardScale,
  PHONE_MAX_CARD_W,
  PHONE_MIN_CARD_W,
} from "../logic/cardSize";
import {
  bandsFor,
  COMPACT_MAT,
  footprintsFor,
  HAND_FAN_W,
  lanesHeightIn,
  lanesWidthIn,
  solveBoardCardWidth,
  solveHandCardWidth,
  solvePodLanesHeight,
  VIEWER_MAT,
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
 * ...and what it may take on a handheld, which is more.
 *
 * the handheld-board round (`docs/client.md`, Layout modes) gives the foot 270px of an 800px screen -- 0.34 --
 * and spends it on a hand at 152px, on the argument that the hand is the
 * surface a main phase is actually spent reading. The board can afford most of
 * that because an opponent is a 96px seat there rather than a board.
 *
 * MEASURED DOWN FROM 0.34, and the 0.06 is not rounding. A four-seat pod played
 * several turns in put `.play__mine` over its row by 11px at 0.34 and 6px at
 * 0.30, at 1280x800; `e2e/deckfit.spec.ts` is the gate, and its claim is the
 * whole board on screen with no scroller, which the roadmap asked for by
 * name. The mockup can afford the extra because its board is a fixture: nothing
 * on it ever grows a fourth land row.
 *
 * It is a CEILING and not a target either way, so the hand only reaches it on a
 * board that has room to give.
 */
const HANDHELD_HAND_FRACTION = 0.28;

/**
 * The foot's height past the hand's cards: `.hand`'s 44px droop allowance plus
 * `.table__foot`'s 16px of padding. The droop is for the arc's rotation, which is
 * a transform and contributes nothing to layout, so it has to be reserved.
 */
const FOOT_CHROME = 60;

/**
 * What the handheld foot adds: the hint bar, and the tool row beside it.
 *
 * It was 56 and included "the commit slab portalled beside it". The slab is
 * back in the rail -- which runs the full height of the screen now, so the 65px
 * it costs is affordable there and under the list it commits is where it
 * belongs -- so what is left is one 44px row holding the tools and the hints
 * side by side, plus the foot's own 6px of vertical padding.
 *
 * The cascade in this file's header depends on the foot's height being definite
 * before the board solves, which is why this is a stated number and not a
 * measurement: the foot's height is an OUTPUT of the card size being solved
 * for, and reading it here would be the loop.
 */
const HANDHELD_FOOT_EXTRA = 50;

/**
 * The same three numbers on a phone, where every one of them is smaller.
 *
 * `styles/phone.css` cuts the hand's droop allowance from 44px to 16 (a fan of
 * 56px cards barely droops) and the foot's padding with it, and the tool row is
 * one 44px line with no hint bar beside it -- the hints name controller
 * buttons, and a phone has none. With the Deck's numbers the hand's budget came
 * out NEGATIVE on a phone held sideways, so the hand sat on its floor and the
 * board got nothing.
 */
const PHONE_HAND_FRACTION = 0.3;
/**
 * Held upright, the sheet takes the bottom of the screen under the hand
 * (`styles/phone.css`), so the hand gives up a share of its own to keep the
 * viewer's board in view. Orientation is read from the table's own box, which
 * nothing in it can move -- the rule `useZoomFit`'s header states.
 */
const PHONE_PORTRAIT_HAND_FRACTION = 0.25;
const PHONE_FOOT_CHROME = 22;
const PHONE_FOOT_EXTRA = 44;

/**
 * The rotation slack, again, and bigger on a phone.
 *
 * `FAN_INSET`'s 20px covers the turned outermost cards on a fan 1000px wide,
 * where they are a small share of it. On a 360px foot an eight-card fan is all
 * overlap, its end cards are turned the furthest they ever are, and measured at
 * 390x844 each end card's box ran 25px past the foot.
 */
const PHONE_FAN_INSET_EXTRA = 50;

/** `.play__opponents` gap between mats. */
const POD_GAP = 10;

/**
 * How much narrower than its ROW the fan is allowed to be.
 *
 * `.hand`'s own padding, plus the slack the outermost cards' rotation needs at
 * the ends of the arc -- a card at the edge of the fan is turned, so its box is
 * wider than its width. The foot's padding is taken off separately, by
 * `horizontalPadding`, because it differs by layout.
 */
const FAN_INSET = 20;

/**
 * An element's left plus right padding.
 *
 * `clientWidth` counts padding as part of the box, which is right for a
 * scroller and wrong for "how much room is there inside this". One helper
 * rather than a constant, because the foot's padding differs by layout and a
 * literal here would be a third place that has to be kept in step with
 * `board.css` and `handheld.css`.
 */
function horizontalPadding(el: HTMLElement): number {
  const style = getComputedStyle(el);
  return Number.parseFloat(style.paddingLeft) + Number.parseFloat(style.paddingRight) || 0;
}

/** Absolute card widths, in px, per zone. */
export interface ZoomFit {
  /** The viewer's battlefield, as a multiple of `--card-w-base`. */
  board: number;
  /** Every opponent's battlefield, likewise. */
  pod: number;
  /** The hand, likewise. */
  hand: number;
  /**
   * The width the fan was SOLVED against, in px.
   *
   * `HandFan` has to lay out against the same number, and it did not: it used
   * the `HAND_FAN_W` constant while the solver used the foot's real width. On a
   * desktop the two agreed by luck, because 1180 was under the full screen; the
   * moment the foot moved inside the board's column they stopped agreeing, and
   * the fan ran 26-30px past its box with `overflow: hidden` hiding it. Found by
   * `fanOverflow` against a real engine.
   */
  fanW: number;
  /**
   * The height an opponent's lanes were solved inside, in px.
   *
   * `Table` writes it back out as `--pod-lanes-h`, so the box CSS draws and the
   * budget the cards were packed into are the same number rather than two
   * numbers that agree today. `null` on the pinned path, which leaves the
   * stylesheet's own clamp in force -- that is what "pinned" means.
   */
  podLanesH: number | null;
  /** True when the zoom is pinned to the sizes that shipped before it existed. */
  locked: boolean;
}

interface Measurements {
  tableW: number;
  tableH: number;
  /**
   * The foot's own width, which is no longer the table's.
   *
   * The foot moved inside `.table__body`'s first column when the right rail was
   * given the full height, so it is now the board's width rather than the
   * screen's -- about 1024 of 1600 on a desktop and 1017 of 1280 on a handheld.
   * Laying a 1180px fan inside it is exactly the failure
   * the handheld-board round (`docs/adr/0014-measured-numbers-invariant-relationships.md`) records: six cards at 176px is 1056px in the 947
   * the foot had, the hand ran 79px past it onto the commit panel's first
   * control, and `overflow: hidden` meant nothing reported it at all.
   *
   * Its WIDTH is safe to read and its HEIGHT is not, for the reason `mineW`
   * gives: the width is a grid track between the board and a fixed rail token
   * and no part of the solve moves it, while the height is an output of the
   * card size this function is solving for.
   */
  footW: number;
  mineW: number;
  mineH: number;
  podW: number;
  /**
   * `--pod-lanes-h`, which is now the FLOOR of the pod box rather than the box.
   *
   * The box itself is `solvePodLanesHeight(tableH, ...)`, and `tableH` is
   * already up there. Nothing measured is read for it, deliberately -- see that
   * function on why "does not depend on a card size" was not a strong enough
   * test.
   */
  podLanesH: number;
  /**
   * `.mat`'s orb column, read from `--mat-side` rather than restated.
   *
   * Legal under this file's own discipline, and it is worth saying why: a fit
   * solver may only take inputs the solve cannot move. `--mat-side` is a CSS
   * constant resolved from the viewport -- the same class of input as
   * `--pod-lanes-h` above -- so it cannot feed back off a card size this solve
   * produces. What it replaces is `VIEWER_MAT.sideW`, a literal duplicating
   * `board.css`, which is a number that could silently disagree with the
   * layout it was packing cards into.
   */
  matSide: number;
  /** The same for a compact mat, from `--mat-side-compact`. */
  matSideCompact: number;
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
    // The designed width, which is what a pinned board is pinned to.
    fanW: HAND_FAN_W,
    // Nothing written, so `theme.css`'s clamp stands. e2e and jsdom both take
    // this path and both were written against that box.
    podLanesH: null,
    locked: true,
  };
}

/**
 * `?zoom=lock`, or `window.__COMMANDERBLITZ_ZOOM_LOCK`.
 *
 * A window flag rather than a persisted preference: `e2e/helpers.ts` sets it with
 * `addInitScript`, the same way it forces instant narration, and unlike a
 * localStorage key it cannot get stuck on for a real player who will then never
 * see the feature and have no idea why. The query parameter is for eyeballing the
 * before-and-after by hand.
 */
function zoomLocked(): boolean {
  if (typeof window === "undefined") return true;
  if ((window as { __COMMANDERBLITZ_ZOOM_LOCK?: boolean }).__COMMANDERBLITZ_ZOOM_LOCK === true)
    return true;
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
  /** The compact layout: a 96px card floor, no pod solve, a taller foot. */
  handheld?: boolean;
  /** A handheld too small for its floors: 56-96px cards and a shorter foot. */
  phone?: boolean;
  tableRef: RefObject<HTMLElement | null>;
  mineRef: RefObject<HTMLElement | null>;
  podRef: RefObject<HTMLElement | null>;
  /** The foot, whose WIDTH the fan is solved against. See `Measurements`. */
  footRef: RefObject<HTMLElement | null>;
}): ZoomFit {
  const {
    state,
    actionableOids,
    opponents,
    handCount,
    handheld = false,
    phone = false,
    tableRef,
    mineRef,
    podRef,
    footRef,
  } = args;
  const base = useCardBase();
  const pinned = zoomLocked();

  const [measured, setMeasured] = useState<Measurements | null>(null);

  const measure = useCallback(() => {
    const table = tableRef.current;
    const mine = mineRef.current;
    const pod = podRef.current;
    const foot = footRef.current;
    if (!table || !mine) return;
    /*
     * THE SCROLLBAR GUTTER, PUBLISHED, because two panels have to agree about it.
     *
     * `.play__mine` reserves a permanent gutter (`scrollbar-gutter: stable`) so
     * that `mineW` below is a number that does not move when the board starts
     * scrolling -- that reservation is the whole reason this measurement is
     * trustworthy. What it costs is that the mat inside it stops short of the
     * column's right edge, while `.table__foot` -- a sibling, which does not
     * scroll and cannot be given a gutter without clipping the hand card as it
     * rises -- runs the full width. Two bordered panels, one above the other,
     * eight pixels out of line.
     *
     * The width is the browser's own and no stylesheet can ask for it, so it is
     * measured HERE, where the element is already in hand, and handed to CSS as
     * `--sbw`. `board.css` spends it on `.table__foot`'s right margin and
     * nowhere else.
     */
    document.documentElement.style.setProperty(
      "--sbw",
      `${mine.offsetWidth - mine.clientWidth}px`,
    );
    const next: Measurements = {
      tableW: table.clientWidth,
      tableH: table.clientHeight,
      /*
       * The foot's CONTENT width, padding taken off.
       *
       * `clientWidth` includes padding, and `.table__foot` has 16px of it on a
       * handheld -- so solving against it laid a fan 16px wider than the row it
       * had to sit in, plus whatever `.hand`'s own padding took. The gate
       * measured `.hand__rail` 26-30px past its box against a real engine,
       * which is exactly the failure `fanOverflow` was written for arriving in
       * the code that was supposed to have prevented it.
       *
       * Falls back to the table until the foot has mounted, which is the first
       * paint only -- and erring wide there is the safe direction, because the
       * fan solves again the moment the observer fires.
       */
      footW: foot ? foot.clientWidth - horizontalPadding(foot) : table.clientWidth,
      // Width and height only. Never the mat inside it, whose height is an output.
      mineW: mine.clientWidth,
      mineH: mine.clientHeight,
      podW: pod?.clientWidth ?? 0,
      /** `--pod-lanes-h`, which is now the FLOOR of the pod box rather than the box. */
      podLanesH: readLengthVar("--pod-lanes-h", 228),
      matSide: readLengthVar("--mat-side", VIEWER_MAT.sideW),
      matSideCompact: readLengthVar("--mat-side-compact", COMPACT_MAT.sideW),
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
  }, [tableRef, mineRef, podRef, footRef]);

  useEffect(() => {
    if (pinned) return;
    // jsdom has no ResizeObserver. Component tests take the pinned path instead,
    // and the solver itself is covered by pure unit tests.
    if (typeof ResizeObserver === "undefined") return;

    measure();
    const observer = new ResizeObserver(measure);
    for (const ref of [tableRef, mineRef, podRef, footRef]) {
      if (ref.current) observer.observe(ref.current);
    }
    return () => observer.disconnect();
  }, [pinned, measure, tableRef, mineRef, podRef, footRef]);

  return useMemo(() => {
    if (pinned || !measured) return locked(opponents.length);

    /*
     * The card floor.
     *
     * `HANDHELD_MIN_CARD_W` is `assert.js`'s `CARD_FLOOR`: any card the ring can
     * land on has to be at least 96px, because below that its illustration and
     * its stats stop being readable on a 7-inch panel at arm's length. At 96 the
     * board will not always fit -- that is intended and not a regression:
     * `.play__mine` already scrolls, and a board you have to scroll is better
     * than a board you cannot read.
     */
    const floor = phone ? PHONE_MIN_CARD_W : handheld ? HANDHELD_MIN_CARD_W : MIN_CARD_W;

    /*
     * 1. The hand, first, because the foot's height is taken out of the board's row.
     *
     * Its ceiling is the ratio it was designed at, so the hand never *grows* into
     * the board's space -- at 1600x950 the board has none to give. It grows only
     * because `--card-w-base` grew, which happens on a display with the room. What
     * this solve adds is the shrink: a fifteen-card fan, or a short viewport.
     */
    const handCeiling = Math.min(phone ? PHONE_MAX_CARD_W : MAX_CARD_W, base * CARD_SCALE.hand);
    const fanW = Math.min(
      HAND_FAN_W,
      measured.footW - FAN_INSET - (phone ? PHONE_FAN_INSET_EXTRA : 0),
    );
    const handHeight = phone
      ? measured.tableH *
          (measured.tableH > measured.tableW
            ? PHONE_PORTRAIT_HAND_FRACTION
            : PHONE_HAND_FRACTION) -
        PHONE_FOOT_CHROME -
        PHONE_FOOT_EXTRA
      : measured.tableH * (handheld ? HANDHELD_HAND_FRACTION : HAND_FRACTION) -
        FOOT_CHROME -
        (handheld ? HANDHELD_FOOT_EXTRA : 0);
    const handW = solveHandCardWidth(handCount, fanW, {
      heightPx: handHeight,
      minCardW: floor,
      maxCardW: handCeiling,
    });

    /*
     * 2. The viewer's board, against whatever `.play__mine` has left.
     *
     * The ceiling is a hand card at its designed ratio, not the hand's *solved*
     * width. A crowded hand shrinking must not drag the board down with it -- the
     * board is not the thing that is crowded -- but the board should still never
     * out-size the zone whose whole job is to be readable.
     */
    const boardCeiling = handCeiling;
    /*
     * The mat chrome, with its one viewport-dependent field filled in from the
     * stylesheet. Everything else about a mat -- its gaps, padding and border --
     * is the same at every size, so only `sideW` is measured.
     */
    /*
     * `labels: false` on a handheld, and the solver has to be told or the space
     * is not actually recovered.
     *
     * `styles/handheld.css` drops the lane headings -- "CREATURES", "GLOBAL
     * ARTIFACTS & ENCHANTMENTS", "LANDS" -- because on a 7-inch panel a row of
     * creatures says "creatures" better than the word above it does, and the
     * word was costing `labelAboveH` off every front band and `labelBesideW`
     * (74px) off the lands. Hiding them in CSS alone would leave this solve
     * still reserving both, so the board would keep packing cards into a box
     * smaller than the one it now has -- the same class of model drift that
     * `theme.css`'s rail tokens were introduced to end, and the opposite
     * direction of the wrapped-label bug that started this pass.
     *
     * `COMPACT_MAT` has always said `labels: false` for exactly this, so this is
     * the existing switch rather than a new one.
     */
    const viewerMat = { ...VIEWER_MAT, sideW: measured.matSide, labels: !handheld };
    const compactMat = { ...COMPACT_MAT, sideW: measured.matSideCompact };
    const viewerLanesW = lanesWidthIn(measured.mineW, viewerMat);
    const boardW = solveBoardCardWidth(
      bandsFor(footprintsFor(state, state.seat, actionableOids), viewerLanesW, {
        hideEmpty: false,
        labels: viewerMat.labels,
        // A handheld board overlaps a full lane rather than wrapping it, so a
        // fourth artifact does not add a row (`handheld.css`, `.lane__cards`).
        overlap: handheld,
      }),
      {
        heightPx: lanesHeightIn(measured.mineH, viewerMat),
        minCardW: floor,
        maxCardW: boardCeiling,
      },
    );

    /*
     * 3. The opponents, inside the box solved for them.
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
     *
     * THE BOX IS SOLVED NOW, NOT READ. `--pod-lanes-h` used to be the budget
     * outright, and it is a `vh` clamp measured against a four-seat pod -- which
     * at one opponent left a two-band board needing 181.6px to hold even a 52px
     * card inside 142px, so the scan fell through to the floor beside half an
     * empty table. `solvePodLanesHeight` takes the clamp as a FLOOR and grows it
     * into `playH` where the seat count says the room is going spare; above two
     * opponents it returns the clamp unchanged, so the measured trade and the
     * gates that pin it are untouched. `Table` writes the answer back out as
     * `--pod-lanes-h` so CSS sizes the box with the same number the cards were
     * packed into -- one value, both languages, exactly as `cardWidthVar` and
     * `cardWidthPx` already share one `scale`.
     */
    const count = Math.max(1, opponents.length);
    const podCeiling = boardW * opponentCardScale(opponents.length);
    // Mats are `flex: 1 1 0`, so they share the row evenly. Their 288px `min-width`
    // can win on a narrow viewport, at which point the row scrolls horizontally and
    // each mat is really *wider* than this -- so the solve is conservative there
    // rather than wrong, which is the direction to be wrong in.
    const podMatW = (measured.podW - (count - 1) * POD_GAP) / count;
    const podLanesW = lanesWidthIn(podMatW, compactMat);
    /*
     * Not on a handheld, where an opponent has no lanes to give room to.
     *
     * `handheld.css` clips `.mat--compact .mat__lanes` to `height: 0` outright,
     * so growing this would be writing a variable that the cascade throws away
     * two files later -- and the `podW` branch below does not consult it at
     * this size either. `null` leaves `theme.css`'s clamp in force, which is
     * what a handheld had before and still wants.
     */
    const podLanesH = handheld
      ? null
      : solvePodLanesHeight({
          tableH: measured.tableH,
          cssFloor: measured.podLanesH,
          opponents: opponents.length,
        });
    const podW = handheld
      ? // No lanes are drawn for an opponent at this size -- their mat is an orb
        // and a summary line -- so there is nothing to pack and three shelf
        // solves per resize would be spent on a box with no cards in it.
        podCeiling
      : opponents.length
        ? Math.min(
            ...opponents.map((pid) =>
              solveBoardCardWidth(
                bandsFor(footprintsFor(state, pid, actionableOids), podLanesW, {
                  hideEmpty: true,
                  labels: compactMat.labels,
                }),
                // `--pod-lanes-h` *is* the lanes' box, so it is the budget as it
                // stands -- no mat chrome to subtract.
                {
                  // Non-null here by construction: this arm is the `!handheld`
                  // one, and only a handheld leaves the box unsolved.
                  heightPx: podLanesH ?? measured.podLanesH,
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
      fanW,
      podLanesH,
      locked: false,
    };
  }, [pinned, measured, base, state, actionableOids, opponents, handCount, handheld, phone]);
}
