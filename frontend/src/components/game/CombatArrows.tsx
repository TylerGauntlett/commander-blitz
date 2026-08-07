/**
 * Who is hitting whom, and what is aimed at what.
 *
 * The server has always sent a full `combat` view -- attackers, blockers, and
 * the damage order -- and the old client threw it away, leaving a coloured
 * outline as the only clue. Drawn as curves, a five-creature crack-back is
 * legible at a glance. Spells on the stack get the same treatment: a targeted
 * removal spell draws a line to what it is pointed at.
 *
 * Anchors are found by `data-oid` / `data-player` / `data-stack-sid` in the DOM
 * rather than threaded through props, because the cards move: they are inside
 * spring animations, fanned stacks and layout flights.
 *
 * ## Why not a frame loop
 *
 * This used to re-measure every anchor on `requestAnimationFrame` for as long
 * as combat was live -- a full `querySelector` plus `getBoundingClientRect` per
 * arrow per frame, forever, including the long stretches where nothing moved.
 * On a wide pod board that was the first thing to drop frames.
 *
 * It now measures on the events that can actually change a position: a resize,
 * a scroll, and the settling of a layout animation. Springs are the awkward
 * case -- framer drives them off its own clock and emits nothing per frame --
 * so a short rAF burst covers each disturbance and then stops. Idle combat now
 * costs nothing.
 */

import { useCallback, useEffect, useState } from "react";
import type { GameView } from "../../api/types";
import { useUiStore } from "../../state/uiStore";

/**
 * How long to keep re-measuring after something disturbs the board.
 *
 * Long enough to outlast the springs in `motion/springs` (the bouncy one
 * settles well inside 600ms), short enough that a quiet board is quiet.
 */
const SETTLE_MS = 700;

interface Arrow {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  kind: "attack" | "block" | "staged" | "target";
}

interface Point {
  x: number;
  y: number;
}

function centreOf(selector: string, origin: DOMRect): Point | null {
  const element = document.querySelector(selector);
  if (!element) return null;
  const box = element.getBoundingClientRect();
  if (box.width === 0 && box.height === 0) return null;
  return {
    x: box.left + box.width / 2 - origin.left,
    y: box.top + box.height / 2 - origin.top,
  };
}

/** A curve that bows sideways, so two arrows between the same rows stay apart. */
function path(arrow: Arrow): string {
  const dx = arrow.x2 - arrow.x1;
  const dy = arrow.y2 - arrow.y1;
  const bow = Math.min(60, Math.abs(dy) * 0.35);
  const cx = arrow.x1 + dx * 0.5 + (dy < 0 ? bow : -bow) * 0.4;
  const cy = arrow.y1 + dy * 0.5;
  return `M ${arrow.x1} ${arrow.y1} Q ${cx} ${cy} ${arrow.x2} ${arrow.y2}`;
}

interface Props {
  state: GameView;
  /** The element arrows are drawn over; positions are relative to it. */
  boardRef: React.RefObject<HTMLElement>;
}

export function CombatArrows({ state, boardRef }: Props) {
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const [arrows, setArrows] = useState<Arrow[]>([]);

  const combat = state.combat;
  const hasStaging =
    Object.keys(stagedAttacks).length > 0 || Object.keys(stagedBlocks).length > 0;
  const targeted = state.stack.filter((item) => item.targets.length > 0);
  const live =
    hasStaging ||
    targeted.length > 0 ||
    (combat !== null &&
      (Object.keys(combat.attackers).length > 0 || Object.keys(combat.blockers).length > 0));

  const measure = useCallback(() => {
    const board = boardRef.current;
    if (!board) return;
    const origin = board.getBoundingClientRect();
    const next: Arrow[] = [];

    const link = (fromSel: string, toSel: string, key: string, kind: Arrow["kind"]) => {
      const from = centreOf(fromSel, origin);
      const to = centreOf(toSel, origin);
      if (from && to) {
        next.push({ key, x1: from.x, y1: from.y, x2: to.x, y2: to.y, kind });
      }
    };

    for (const [attacker, defender] of Object.entries(combat?.attackers ?? {})) {
      link(`[data-oid="${attacker}"]`, `[data-player="${defender}"]`, `a${attacker}`, "attack");
    }
    for (const [blocker, attacker] of Object.entries(combat?.blockers ?? {})) {
      link(`[data-oid="${blocker}"]`, `[data-oid="${attacker}"]`, `b${blocker}`, "block");
    }
    // Staged arrows show intent before it is submitted.
    for (const [attacker, defender] of Object.entries(stagedAttacks)) {
      link(
        `[data-oid="${attacker}"]`,
        `[data-player="${defender}"]`,
        `sa${attacker}`,
        "staged",
      );
    }
    for (const [blocker, attacker] of Object.entries(stagedBlocks)) {
      link(`[data-oid="${blocker}"]`, `[data-oid="${attacker}"]`, `sb${blocker}`, "staged");
    }
    // What is on the stack, and what it is pointed at. Responding to the stack
    // is the skill in this format, and the relationship was text-only before.
    for (const item of targeted) {
      for (const ref of item.targets) {
        const to =
          ref.kind === "player" ? `[data-player="${ref.id}"]` : `[data-oid="${ref.id}"]`;
        link(
          `[data-stack-sid="${item.sid}"]`,
          to,
          `t${item.sid}-${ref.kind}${ref.id}`,
          "target",
        );
      }
    }

    setArrows(next);
    // Rebuilt whenever the inputs change, which is also the signal that cards
    // are mid-flight and need re-measuring -- the effect below re-bursts on it.
  }, [boardRef, combat, stagedAttacks, stagedBlocks, targeted]);

  useEffect(() => {
    if (!live) {
      setArrows([]);
      return;
    }

    let frame = 0;
    let until = 0;

    /** Re-measure every frame for a moment, then stop. */
    const burst = () => {
      until = performance.now() + SETTLE_MS;
      if (frame !== 0) return;
      const tick = () => {
        measure();
        if (performance.now() < until) {
          frame = requestAnimationFrame(tick);
        } else {
          frame = 0;
        }
      };
      frame = requestAnimationFrame(tick);
    };

    // Re-runs whenever `measure` changes identity -- that is, whenever the
    // arrows themselves change -- which is exactly when the cards are flying
    // into their new positions and most need following.

    // The board itself changing size moves every anchor on it.
    const observer = new ResizeObserver(burst);
    const board = boardRef.current;
    if (board) {
      observer.observe(board);
      // Cards live in scrollable lanes and mats; scrolling one moves its cards
      // without resizing anything. `capture` catches those inner scrolls too.
      board.addEventListener("scroll", burst, { capture: true, passive: true });
    }
    window.addEventListener("resize", burst);

    burst();

    return () => {
      if (frame !== 0) cancelAnimationFrame(frame);
      observer.disconnect();
      board?.removeEventListener("scroll", burst, { capture: true });
      window.removeEventListener("resize", burst);
    };
  }, [live, boardRef, measure]);

  if (arrows.length === 0) return null;

  return (
    <svg className="arrows" aria-hidden="true" data-testid="combat-arrows">
      <defs>
        <marker
          id="arrowhead"
          markerWidth="7"
          markerHeight="7"
          refX="5.5"
          refY="3"
          orient="auto"
        >
          <path d="M 0 0 L 6 3 L 0 6 z" fill="currentColor" />
        </marker>
      </defs>
      {arrows.map((arrow) => (
        <path
          key={arrow.key}
          className={`arrow arrow--${arrow.kind}`}
          d={path(arrow)}
          markerEnd="url(#arrowhead)"
        />
      ))}
    </svg>
  );
}
