/**
 * Who is hitting whom.
 *
 * The server has always sent a full `combat` view -- attackers, blockers, and
 * the damage order -- and the old client threw it away, leaving a coloured
 * outline as the only clue. Drawn as curves, a five-creature crack-back is
 * legible at a glance.
 *
 * Anchors are found by `data-oid` / `data-player` in the DOM rather than
 * threaded through props, because the cards move: they are inside spring
 * animations, fanned stacks and layout flights. Measuring on a frame loop while
 * combat is live is both simpler and always correct.
 */

import { useEffect, useRef, useState } from "react";
import type { GameView } from "../../api/types";
import { useUiStore } from "../../state/uiStore";

interface Arrow {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  kind: "attack" | "block" | "staged";
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
  const live =
    hasStaging ||
    (combat !== null &&
      (Object.keys(combat.attackers).length > 0 || Object.keys(combat.blockers).length > 0));

  // Keep a ref of the latest inputs so the frame loop does not need to restart
  // every render.
  const inputs = useRef({ combat, stagedAttacks, stagedBlocks });
  inputs.current = { combat, stagedAttacks, stagedBlocks };

  useEffect(() => {
    if (!live) {
      setArrows([]);
      return;
    }
    let frame = 0;

    const measure = () => {
      const board = boardRef.current;
      if (board) {
        const origin = board.getBoundingClientRect();
        const next: Arrow[] = [];
        const { combat: c, stagedAttacks: sa, stagedBlocks: sb } = inputs.current;

        const link = (fromSel: string, toSel: string, key: string, kind: Arrow["kind"]) => {
          const from = centreOf(fromSel, origin);
          const to = centreOf(toSel, origin);
          if (from && to) {
            next.push({ key, x1: from.x, y1: from.y, x2: to.x, y2: to.y, kind });
          }
        };

        for (const [attacker, defender] of Object.entries(c?.attackers ?? {})) {
          link(
            `[data-oid="${attacker}"]`,
            `[data-player="${defender}"]`,
            `a${attacker}`,
            "attack",
          );
        }
        for (const [blocker, attacker] of Object.entries(c?.blockers ?? {})) {
          link(`[data-oid="${blocker}"]`, `[data-oid="${attacker}"]`, `b${blocker}`, "block");
        }
        // Staged arrows show intent before it is submitted.
        for (const [attacker, defender] of Object.entries(sa)) {
          link(
            `[data-oid="${attacker}"]`,
            `[data-player="${defender}"]`,
            `sa${attacker}`,
            "staged",
          );
        }
        for (const [blocker, attacker] of Object.entries(sb)) {
          link(`[data-oid="${blocker}"]`, `[data-oid="${attacker}"]`, `sb${blocker}`, "staged");
        }
        setArrows(next);
      }
      frame = requestAnimationFrame(measure);
    };

    frame = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(frame);
  }, [live, boardRef]);

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
