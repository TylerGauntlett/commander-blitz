/**
 * A card with physics.
 *
 * Two motion layers, and the split is not cosmetic:
 *
 *   outer  -- layoutId, drag, hover lift. Owns *position*.
 *   inner  -- the 90-degree tap rotation. Owns *orientation*.
 *
 * Both would otherwise write `transform` on the same node, and the last one to
 * render would win: a tapped creature would untap itself the moment you picked
 * it up. Splitting them is what makes tapping and dragging coexist.
 *
 * `layoutId` is keyed on the object id, which the engine preserves across zone
 * changes. That single fact is what makes a card *fly* from hand to stack to
 * battlefield instead of vanishing and reappearing -- framer interpolates
 * between the two mount points for free.
 */

import { type Transition, motion } from "motion/react";
import type { CSSProperties } from "react";
import type { CardView } from "../../api/types";
import { bouncy, mechanical, settle } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { CardFace } from "./CardFace";

export interface CardProps {
  card: CardView;
  detail?: boolean;
  /** Enable drag-to-play. */
  draggable?: boolean;
  /** A legal action would play this card: green rim. */
  playable?: boolean;
  /** A legal action could target this card: blue rim. */
  targetable?: boolean;
  /** Staged as an attacker or blocker, not yet submitted: amber rim. */
  staged?: boolean;
  selected?: boolean;
  /** Nothing can be done with this right now. */
  dimmed?: boolean;
  /** Lift on hover. Off inside a fanned stack, where the fan does the lifting. */
  lift?: boolean;
  onActivate?: (card: CardView) => void;
  /** Called with the `data-dropzone` value of whatever it was dropped on. */
  onDropOn?: (card: CardView, zone: string) => void;
  style?: CSSProperties;
  transition?: Transition;
  className?: string;
}

/** The drop zone under a point, or null. */
function dropZoneAt(x: number, y: number): string | null {
  for (const element of document.elementsFromPoint(x, y)) {
    const zone = (element as HTMLElement).dataset?.dropzone;
    if (zone) return zone;
  }
  return null;
}

export function Card({
  card,
  detail = false,
  draggable = false,
  playable = false,
  targetable = false,
  staged = false,
  selected = false,
  dimmed = false,
  lift = true,
  onActivate,
  onDropOn,
  style,
  transition,
  className,
}: CardProps) {
  const hover = useUiStore((s) => s.hover);
  const tapped = card.tapped === true;

  const classes = [
    "card",
    // Swaps the outer box to a landscape footprint so the lane reflows around
    // the rotated card instead of letting it lie across its neighbour.
    tapped ? "card--tapped" : "",
    playable ? "card--playable" : "",
    targetable ? "card--targetable" : "",
    staged ? "card--staged" : "",
    selected ? "card--selected" : "",
    dimmed ? "card--dimmed" : "",
    card.attacking ? "card--attacking" : "",
    card.blocking ? "card--blocking" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <motion.div
      layoutId={`card-${card.oid}`}
      layout="position"
      className={classes}
      style={style}
      data-oid={card.oid}
      data-testid={`card-${card.oid}`}
      data-card-name={card.name}
      transition={transition ?? settle}
      whileHover={lift ? { y: -10, scale: 1.04, zIndex: 30 } : undefined}
      whileTap={{ scale: 0.97 }}
      drag={draggable}
      dragSnapToOrigin
      dragElastic={0.18}
      dragMomentum={false}
      dragTransition={{ bounceStiffness: 480, bounceDamping: 26 }}
      whileDrag={{ scale: 1.12, zIndex: 200, cursor: "grabbing" }}
      onDragEnd={(event) => {
        if (!onDropOn) return;
        const point = event as unknown as { clientX?: number; clientY?: number };
        if (point.clientX === undefined || point.clientY === undefined) return;
        const zone = dropZoneAt(point.clientX, point.clientY);
        if (zone) onDropOn(card, zone);
      }}
      onHoverStart={() => hover(card.oid)}
      onHoverEnd={() => hover(null)}
      onClick={() => onActivate?.(card)}
      role={onActivate ? "button" : undefined}
      tabIndex={onActivate ? 0 : undefined}
      onKeyDown={(e) => {
        if (onActivate && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onActivate(card);
        }
      }}
    >
      <motion.div
        className="card__pivot"
        animate={{ rotate: tapped ? 90 : 0 }}
        transition={mechanical}
      >
        <CardFace card={card} detail={detail} />
      </motion.div>
      {staged && <span className="card__pin" />}
    </motion.div>
  );
}

/** The same face with no physics: for previews and dialogs, where a second
 *  `layoutId` for the same oid would make framer animate between them. */
export function StaticCard({
  card,
  detail = true,
  className,
  style,
}: {
  card: CardView;
  detail?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <motion.div
      className={`card card--static ${className ?? ""}`}
      style={style}
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.94 }}
      transition={bouncy}
      data-card-name={card.name}
    >
      <div className="card__pivot">
        <CardFace card={card} detail={detail} />
      </div>
    </motion.div>
  );
}
