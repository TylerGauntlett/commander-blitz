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
 *
 * There is now a third layer between those two:
 *
 *   outer  -- layoutId, drag, hover lift. Owns *position*.
 *   actor  -- lunges, recoils, shudders. Owns *transient force*.
 *   pivot  -- the 90-degree tap rotation. Owns *orientation*.
 *
 * The actor is what `fx/actuators.ts` drives when a creature strikes something.
 * It is its own node for exactly the reason the pivot is: it writes `transform`
 * on its own clock, and sharing a node with the layout animation would mean a
 * creature that lunges mid-flight snaps to wherever the strike left it.
 *
 * ## `data-stop`, and the thing it is careful not to be
 *
 * The outer node carries `data-stop`, which is where the focus ring is allowed
 * to land. It is a **static prop derived from `oid`** -- this component does not
 * subscribe to the cursor and never re-renders because the ring moved. That is
 * not an optimisation, it is the design: a cursor in a store that thirty cards
 * read re-renders all thirty on every step of a sweep, which measured 18.5fps
 * under a 4x CPU throttle against 59.7fps for moving one attribute. See the
 * header of `input/cursor.ts`.
 *
 * Keying it on the oid rather than on a position also means the ring survives a
 * zone change for the same reason `layoutId` does: it stays on the card you
 * were reading as it moves from hand to stack to battlefield.
 */

import { motion, type Transition, useMotionValue } from "motion/react";
import { type CSSProperties, useEffect, useLayoutEffect, useRef } from "react";
import type { CardView } from "../../api/types";
import { register } from "../../fx/actuators";
import { stopId } from "../../input/stops";
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
  /**
   * A hand card with more than one way to be played -- a modal double-faced
   * card's spell and land, a shock land's two land drops. Pressing it asks
   * which (`logic/abilities.ts`), and this mark says so before it is pressed.
   */
  twoWays?: boolean;
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
  /**
   * Whether this card drives `hoveredOid` itself.
   *
   * Off inside the hand fan, where `.hand__slot` -- a fixed rectangle extended
   * upward past the card -- owns both the lift and the hover. With both writing
   * it there were two nested enter/leave pairs on one global scalar, and the
   * order in which framer's gesture and the slot's DOM handler fire across a
   * slot boundary is not defined: leaving A after entering B blanks the rail on
   * the card you just moved onto.
   */
  ownsHover?: boolean;
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
  twoWays = false,
  abilityLabel = null,
  targetable = false,
  staged = false,
  selected = false,
  dimmed = false,
  lift = true,
  ownsHover = true,
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

  /*
   * The channel the FX layer pushes this card around through.
   *
   * Motion values rather than state: an actuator writes these sixty times a
   * second during a combat exchange, and going through React would reconcile
   * the whole board on every frame of every strike.
   */
  const fxX = useMotionValue(0);
  const fxY = useMotionValue(0);
  const fxRotate = useMotionValue(0);
  const fxScale = useMotionValue(1);

  useEffect(
    () => register(oid, { x: fxX, y: fxY, rotate: fxRotate, scale: fxScale }),
    [oid, fxX, fxY, fxRotate, fxScale],
  );

  /*
   * The pointer left because the card stopped existing.
   *
   * `onHoverEnd` is a `pointerleave` gesture: it does not fire when the node
   * unmounts, and it does not fire when framer moves a `layoutId` node to a new
   * mount point -- which is exactly what casting a hovered card from the hand
   * does. `hoveredOid` then names a card that is no longer anywhere, pinning
   * the preview rail and leaving a `CardStack` member raised.
   *
   * The same guard `CommandZone` carries, for the same reason and with the same
   * ownership test: clear it only if it is still *ours*, or a card unmounting
   * behind a newly hovered one would blank the rail on the new one.
   */
  useEffect(() => {
    if (!ownsHover) return;
    return () => {
      if (useUiStore.getState().hoveredOid === oid) useUiStore.getState().hover(null);
    };
  }, [oid, ownsHover]);

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
      data-stop={stopId.card(card.oid)}
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
      onHoverStart={ownsHover ? () => hover(card.oid) : undefined}
      onHoverEnd={ownsHover ? () => hover(null) : undefined}
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
      {/*
        The force layer. Sits at rest at identity and costs nothing until an
        actuator pushes it -- `fx/actuators.ts` writes these four values
        directly, so nothing here re-renders during a strike.

        THE RIM AND THE PIN ARE INSIDE IT. `cards.css` paints every interaction
        rim as `.card__actor::after`, and the pin is a child here rather than of
        `.card`, because `lean` holds a transform on this node for as long as an
        attacker is declared -- and a transform on a child cannot carry a
        pseudo-element of its parent with it. Anything that must travel with the
        card belongs at this level or below; anything that must stay put (the
        `[data-oid]` box the arrows and the death ghost measure) belongs above.
      */}
      <motion.div
        className="card__actor"
        style={{ x: fxX, y: fxY, rotate: fxRotate, scale: fxScale }}
      >
        <motion.div
          className="card__pivot"
          animate={{ rotate: tapped ? 90 : 0 }}
          transition={mechanical}
        >
          <CardFace card={card} variant={variant} />
        </motion.div>
        {/* Outside `.card__pivot` on purpose: the pin is a marker, so it rides
            the lean but must not take the quarter turn with a tapped card. */}
        {staged && <span className="card__pin" />}
      </motion.div>
      {/*
        An activated ability had no presence on the card at all: the only
        surface was a sentence-shaped button in the action bar's overflow, so
        the affordance existed but nothing pointed at it.

        Deliberately carries no `data-action-id`. `ActionBar` already renders
        every `activate` action, and `clarity.spec.ts` fails the run if two
        rendered nodes share an id -- so this is a *sign*, and clicking the
        card is what routes into `Table.onBoardCard`.
      */}
      {twoWays && (
        <span className="rune rune--ways" aria-hidden="true" data-hint="Two ways to play this">
          &#8644;
        </span>
      )}
      {hasAbility && (
        <span className="rune" aria-hidden="true" data-hint="Has an activated ability">
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
  onSurface = false,
}: {
  card: CardView;
  variant?: CardVariant;
  className?: string;
  style?: CSSProperties;
  /**
   * The card sits on a surface that fades out as a whole -- the opening hand,
   * a prompt dialog -- so it must not carry an `exit` of its own.
   *
   * Not decorative. A `motion` element with `exit` registers with the nearest
   * `AnimatePresence`, and that presence removes its child only once EVERY
   * registered exit has reported complete. Seven cards on the opening hand were
   * seven such registrations, for a fade nobody could see under the stage's own
   * 220ms fade -- and when one of them was answered while its entrance spring
   * was still in flight, its opacity exit sometimes never finished. The stage
   * then stayed in the DOM at `opacity: 0`, `position: absolute; inset: 0`,
   * over a board that had gone on without it, eating every click. Measured in
   * `e2e/orb.spec.ts` on a four-player pod, about one game in two. With the
   * surface owning the exit there is one registration, the surface's own.
   * The entrance stays: that is the part a person sees.
   */
  onSurface?: boolean;
}) {
  return (
    <motion.div
      className={`card card--static ${variant === "big" ? "card--big " : ""}${className ?? ""}`}
      style={style}
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={onSurface ? undefined : { opacity: 0, scale: 0.94 }}
      transition={bouncy}
      data-card-name={card.name}
    >
      <div className="card__pivot">
        <CardFace card={card} variant={variant} />
      </div>
    </motion.div>
  );
}
