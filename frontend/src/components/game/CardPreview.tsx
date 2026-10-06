/**
 * The hovered card, with its rules text readable.
 *
 * The old client wrote `hoveredOid` into its store and nothing ever read it;
 * oracle text lived only in a native `title` tooltip. On a board of 104px
 * cards this panel is how you actually find out what something does.
 *
 * Rendered with `StaticCard`, never `Card`: a second `layoutId` for the same
 * oid would make framer try to animate the board card into the preview.
 *
 * ## Two bodies, one component
 *
 * A 1280px board gives this rail 243px, and a card frame at that width is 116px
 * across -- SMALLER than the board card it is supposed to be helping you read,
 * with `object-fit: cover` throwing away most of the painting to get there. So
 * the compressed variant is not a smaller card: it is a **landscape window**
 * onto the same `art_crop`, which is 626x457. the handheld-board round (`docs/design-record.md#handheld-board`)
 * measures 227x84 as keeping the painting's full width for a third of the
 * height, and the 78px that hands back is what the rules text is made of.
 *
 * ONE COMPONENT AND NOT TWO, because a second one would be a second subscriber
 * to `hoveredOid` and a second `findCard` per hover -- and `input/cursor.ts` is
 * explicit that what cost this app its frame rate was components subscribing to
 * what the pointer is on.
 *
 * `useHandheldLayout` and not `useHandheld`: this swaps a NODE, so it has to
 * agree with the stylesheet in Storybook, where the Layout toolbar sets the
 * attribute without resizing anything.
 */

import { AnimatePresence, motion } from "motion/react";
import type { CardView, GameView } from "../../api/types";
import {
  artistFor,
  artStateFor,
  artUrlFor,
  type ImageMap,
  type SeatImages,
} from "../../logic/cardArt";
import { counterBadges, isWounded, keywordLabel, manaPips } from "../../logic/cardStyle";
import { findCard } from "../../logic/zoneGrouping";
import { ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { useHandheldLayout } from "../../state/useHandheld";
import { StaticCard } from "./Card";
import { ManaSymbol } from "./ManaSymbol";
import { SymbolText } from "./SymbolText";

interface Props {
  state: GameView;
}

/** A one-line summary of what a card is currently doing. */
function cardStatus(card: CardView): string {
  if (card.attacking) return "Attacking";
  if (card.blocking) return "Blocking";
  if (card.zone !== "battlefield") return `In ${card.zone}`;
  const notes: string[] = [];
  if (card.tapped) notes.push("tapped");
  if (card.summoning_sick && card.types.includes("Creature")) notes.push("summoning sick");
  return notes.length > 0 ? `On the battlefield, ${notes.join(", ")}` : "On the battlefield";
}

/**
 * The compressed body: a landscape window, and the text that fits under it.
 *
 * Three findings from the handheld-board round (`docs/design-record.md#handheld-board`) are encoded here.
 *
 * **The P/T goes on the art, not on the type line.** The first draft put
 * "Legendary Creature — Serpent · 5/5" on one 227px line; it ellipsised, and
 * the half it dropped was the number.
 *
 * **The panel is a fixed height and the RULES are what give.** Content-sized it
 * comes to 179px on "Trample." and 260 on three clauses, so the action list
 * below would grow and shrink and every row would slide under the cursor
 * mid-turn -- which is the thing `.preview`'s own height note already exists to
 * stop on a desktop.
 *
 * **The fact list is dropped.** Keywords are in the rules text, status is the
 * tap state and the lane it is in, the controller is whose mat it is on, and
 * the artist is not why anybody opens this at 1280x800.
 *
 * **So is the unplayable reason**, which used to be the last row. See the note
 * on `.reader__rules` below.
 */
function CompressedBody({
  card,
  images,
  seatImages,
}: {
  card: CardView;
  images: ImageMap;
  seatImages: SeatImages;
}) {
  const art = artUrlFor(images, seatImages, card);
  const pips = manaPips(card.mana_cost);
  const pt =
    card.power !== null && card.toughness !== null ? `${card.power}/${card.toughness}` : null;
  /*
   * The counters, on the picture beside the P/T.
   *
   * The panel drops the fact list on a handheld -- keywords are in the rules
   * text, status is the tap state, the controller is whose mat it is on -- and
   * counters went with them, which was wrong for the one reason the others were
   * right: a counter is not restated anywhere. A +1/+1 counter is visible in
   * the derived P/T and nothing else is; a stun, a loyalty, a charge or an oil
   * counter is a fact about the permanent that this panel is the only place to
   * read. So they come back here, where the P/T already lives, and nowhere
   * else.
   */
  const badges = counterBadges(card);

  return (
    <>
      {/*
        `undefined` draws NOTHING, and that is not the same as `null`.

        `undefined` means the image map has not been fetched yet; `null` means
        this printing genuinely has no art. Drawing the plate for both would
        flash a hatch across the panel for the first second of every game, on
        every card the pointer crossed. See `logic/cardArt.ts`, which documents
        the two states looking identical on screen as its own small finding.
      */}
      {art !== undefined && (
        <div
          className={art === null ? "reader__art reader__art--empty" : "reader__art"}
          data-art-state={artStateFor(images, seatImages, card)}
        >
          {art !== null && <img className="reader__img" src={art} alt="" aria-hidden="true" />}
          {/*
            STACKED, NOT SIDE BY SIDE. The window is 227px wide and a card with
            two kinds of counter on it -- "+1/+1 x3" and "stun" -- is already
            most of that before the P/T asks for its corner. In a row the two
            collided; in a column the counters sit above the number, both hard
            against the right edge, and the picture keeps its left half.
          */}
          {(badges.length > 0 || pt) && (
            <div className="reader__marks" data-testid="reader-marks">
              {badges.length > 0 && (
                <span className="reader__counters" data-testid="reader-counters">
                  {badges.map((badge) => (
                    <span className="counter-badge" key={badge}>
                      {badge}
                    </span>
                  ))}
                </span>
              )}
              {pt && <span className="reader__pt tabular">{pt}</span>}
            </div>
          )}
        </div>
      )}

      <div className="reader__body">
        <div className="reader__nm">
          {card.is_commander && (
            // biome-ignore lint/a11y/useAriaPropsSupportedByRole: a labelled readout on a generic element, written before Biome 2 had this rule. The fix is a role, which changes what a screen reader announces -- a behaviour change, so it waits for an a11y pass rather than riding a dependency upgrade.
            <span className="crown" aria-label="Commander">
              &#9819;
            </span>
          )}
          <span className="reader__nm-text">{card.name}</span>
          {pips.length > 0 && (
            <span className="reader__cost">
              {pips.map((pip) => (
                <ManaSymbol code={pip.symbol} className={`pip--${pip.tone}`} key={pip.key} />
              ))}
            </span>
          )}
        </div>

        {/* Ellipsised rather than wrapped: a type line that wrapped would take
            its height out of the rules box, which is the one thing on this
            panel that has to be readable in full. */}
        <div className="reader__tl">{card.type_line}</div>

        {/*
          The rules text, and it is what the rest of this panel exists to make
          room for.

          IT USED TO SHARE THE COLUMN WITH "Needs {4}{G}{G}{G} -- you have {G}".
          That sentence is two lines at the 16px floor and it is `flex: none`,
          so it took its height out of the one box here that is allowed to give
          -- and on a card with real rules text the result was Elder Deep-Fiend
          cut 75px into its own paragraph, mid-word, with no scrollbar drawn.
          The reason a card is dim is a fact about the hand, not about the card,
          and `HandFan` already draws it there as `.hand__hint`; it is no longer
          suppressed on a handheld, so nothing was lost by moving it back.
        */}
        {card.oracle_text && (
          <div className="reader__rules">
            <SymbolText text={card.oracle_text} />
          </div>
        )}
      </div>
    </>
  );
}

/**
 * The desktop rail's card and fact list, unchanged.
 *
 * Kept as it was so `orb.spec.ts` ("hovering a commander fills the preview
 * rail"), `art.spec.ts` ("credits the illustrator") and `acceptance.spec.ts`
 * keep passing against a surface this round did not set out to change.
 */
function FullBody({
  card,
  state,
  artist,
}: {
  card: CardView;
  state: GameView;
  artist: string | null;
}) {
  return (
    <>
      {/*
        The `big` variant, which is the one card on screen that is not a 1.4
        portrait: it is as wide as the rail and as tall as its rules text needs,
        with absolute type sizes. Scaling the portrait card up instead -- what
        this did -- left the rules box squeezed by the card's own aspect ratio
        and clipped after a line or two, on the one surface whose entire job is
        showing that text.

        It sets its own `--card-w`, so there is deliberately no inline width
        here to fight with it.
      */}
      <StaticCard card={card} variant="big" />
      <dl className="preview__facts">
        {card.keywords.length > 0 && (
          <>
            <dt>Keywords</dt>
            <dd>{card.keywords.map(keywordLabel).join(", ")}</dd>
          </>
        )}
        {isWounded(card) && (
          <>
            <dt>Damage</dt>
            <dd className="preview__hurt">{card.damage} marked</dd>
          </>
        )}
        {/* What this permanent is *doing* right now, which the frame cannot
            show and is the first thing you look for mid-combat. */}
        <dt>Status</dt>
        <dd>{cardStatus(card)}</dd>
        <dt>Controller</dt>
        <dd>{state.players[card.controller]?.name ?? card.controller}</dd>
        {/* Crediting the illustrator is the one thing the rail was missing once
            it started showing their work. */}
        {artist && (
          <>
            <dt>Art</dt>
            <dd>{artist}</dd>
          </>
        )}
      </dl>
    </>
  );
}

export function CardPreview({ state }: Props) {
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const images = useUiStore((s) => s.images);
  const seatImages = useUiStore((s) => s.seatImages);
  const compressed = useHandheldLayout();
  const card = hoveredOid === null ? null : findCard(state, hoveredOid);
  const artist = card ? artistFor(images, seatImages, card) : null;

  /*
   * The panel is a fixed height, whether it is holding a card or not.
   *
   * It used to size to its content, which meant the whole action panel below it
   * jumped every time the pointer crossed a card -- and jumped again between a
   * creature and a land, because a land has no P/T row and shorter rules. The
   * panel underneath is where the turn happens; it cannot move because you
   * glanced at something. See `.rail--right .preview` in board.css.
   */
  return (
    <section
      className={compressed ? "preview preview--reader pane" : "preview pane"}
      data-testid="card-preview"
    >
      <AnimatePresence mode="wait">
        {card ? (
          <motion.div
            key={card.oid}
            className="preview__body"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={ease}
          >
            {compressed ? (
              <CompressedBody card={card} images={images} seatImages={seatImages} />
            ) : (
              <FullBody card={card} state={state} artist={artist} />
            )}
          </motion.div>
        ) : (
          <motion.p
            key="idle"
            className="preview__idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={ease}
          >
            {/*
              The desktop's whole-card view, said where somebody looking for
              it would look. The rail is a fixed frame and long rules scroll
              inside it; right-click (or `i`) opens the same card unclipped in
              `CardHold`. Not said on the compressed body: on a Deck the hint
              bar already advertises `Y Read` on every card.
            */}
            {compressed ? (
              "Point at a card to read it."
            ) : (
              <>
                Hover a card to read it.
                <span className="preview__more" data-testid="preview-more">
                  Right-click it, or press I, to see the whole card.
                </span>
              </>
            )}
          </motion.p>
        )}
      </AnimatePresence>
    </section>
  );
}
