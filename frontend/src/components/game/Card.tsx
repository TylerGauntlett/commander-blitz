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
 *
 * It cannot do that for a card leaving the *board*, because there is no second
 * mount point: the graveyard is a count pile. So this also posts its final box
 * to `logic/cardRects` on the way out, which is what the exit animation draws
 * the ghost from. See that module for why the FX layer cannot simply look the
 * element up when the beat plays.
 */

import { type Transition, motion } from "motion/react";
import { type CSSProperties, useLayoutEffect, useRef } from "react";
import type { CardView } from "../../api/types";
import { remember } from "../../logic/cardRects";
import { bouncy, mechanical, settle } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { CardFace, type CardVariant } from "./CardFace";

export interface CardProps {
  card: CardView;
  /** How much card there is room to draw. See `CardVariant`. */
  variant?: CardVariant;
  /** Enable drag-to-play. */
  draggable?: boolean;
  /** A legal action would play this card: green rim. */
  playable?: boolean;
  /** This permanent has an activated ability available right now. */
  hasAbility?: boolean;
  /** The ability's label, shown in a popover while the card is hovered. */
  abilityLabel?: string | null;
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
  variant = "board",
  draggable = false,
  playable = false,
  hasAbility = false,
  abilityLabel = null,
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
  const box = useRef<HTMLDivElement>(null);

  /*
   * Post the final position on the way out, and only on the way out.
   *
   * React runs a layout effect's cleanup *before* it detaches the node, so the
   * element is still in the document here and still has a real box. That is the
   * entire mechanism.
   *
   * Empty deps on purpose. Measuring on every commit as well would call
   * `getBoundingClientRect` for every card on the table on every server
   * response -- forty forced synchronous reflows a tick, continuously, for the
   * whole time the AI pump is running -- to refresh a number that only one card
   * per departure ever reads.
   */
  const oid = card.oid;
  useLayoutEffect(
    () => () => {
      const el = box.current;
      if (el) remember(oid, el.getBoundingClientRect());
    },
    [oid],
  );

  const classes = [
    "card",
    variant === "big" ? "card--big" : "",
    // Swaps the outer box to a landscape footprint so the lane reflows around
    // the rotated card instead of letting it lie across its neighbour.
    tapped ? "card--tapped" : "",
    playable ? "card--playable" : "",
    hasAbility ? "card--ability" : "",
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
      ref={box}
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
        <CardFace card={card} variant={variant} />
      </motion.div>
      {staged && <span className="card__pin" />}
      {/*
        An activated ability had no presence on the card at all: the only
        surface was a sentence-shaped button in the action bar's overflow, so
        the affordance existed but nothing pointed at it.

        Deliberately carries no `data-action-id`. `ActionBar` already renders
        every `activate` action, and `clarity.spec.ts` fails the run if two
        rendered nodes share an id -- so this is a *sign*, and clicking the
        card is what routes into `Table.onBoardCard`.
      */}
      {hasAbility && (
        <span className="rune" aria-hidden="true" title="Has an activated ability">
          &#8631;
        </span>
      )}
      {/*
        What the ability actually *is*, on hover. The rune says "there is
        something here"; without this you still had to go and read the action
        bar to find out what. Carries no `data-action-id` -- clicking the card
        routes through `Table.onBoardCard` exactly as it always has.
      */}
      {hasAbility && abilityLabel && (
        <span className="ability-pop" role="note">
          <span className="ability-pop__label">Ability available</span>
          <span className="ability-pop__text">{abilityLabel}</span>
        </span>
      )}
    </motion.div>
  );
}

/** The same face with no physics: for previews and dialogs, where a second
 *  `layoutId` for the same oid would make framer animate between them. */
export function StaticCard({
  card,
  variant = "detail",
  className,
  style,
}: {
  card: CardView;
  variant?: CardVariant;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <motion.div
      className={`card card--static ${variant === "big" ? "card--big " : ""}${className ?? ""}`}
      style={style}
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.94 }}
      transition={bouncy}
      data-card-name={card.name}
    >
      <div className="card__pivot">
        <CardFace card={card} variant={variant} />
      </div>
    </motion.div>
  );
}
