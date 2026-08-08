/**
 * The hovered card, full size, with its rules text readable.
 *
 * The old client wrote `hoveredOid` into its store and nothing ever read it;
 * oracle text lived only in a native `title` tooltip. On a board of 104px
 * cards this panel is how you actually find out what something does.
 *
 * Rendered with `StaticCard`, never `Card`: a second `layoutId` for the same
 * oid would make framer try to animate the board card into the preview.
 */

import { AnimatePresence, motion } from "motion/react";
import type { CardView, GameView } from "../../api/types";
import { artistOf } from "../../logic/cardArt";
import { CARD_SCALE, cardWidthVar } from "../../logic/cardSize";
import { isWounded, keywordLabel } from "../../logic/cardStyle";
import { findCard } from "../../logic/zoneGrouping";
import { ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { StaticCard } from "./Card";

/** Ratio of `--card-w-base`; see logic/cardSize.ts. */

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

export function CardPreview({ state }: Props) {
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const images = useUiStore((s) => s.images);
  const card = hoveredOid === null ? null : findCard(state, hoveredOid);
  const artist = card ? artistOf(images, card.card_id) : null;

  return (
    <section className="preview pane" data-testid="card-preview">
      {/* The rail says what it is for. Without it the panel reads as an empty
          slot rather than as the place a card goes when you point at one. */}
      <div className="preview__note">Reading a card — art and rules together</div>
      <AnimatePresence mode="wait">
        {card ? (
          <motion.div
            key={card.oid}
            className="preview__body"
            style={{ ["--card-w" as string]: cardWidthVar(CARD_SCALE.preview) }}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={ease}
          >
            <StaticCard card={card} detail />
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
              {/* What this permanent is *doing* right now, which the frame
                  cannot show and is the first thing you look for mid-combat. */}
              <dt>Status</dt>
              <dd>{cardStatus(card)}</dd>
              <dt>Controller</dt>
              <dd>{state.players[card.controller]?.name ?? card.controller}</dd>
              {/* Crediting the illustrator is the one thing the rail was
                  missing once it started showing their work. */}
              {artist && (
                <>
                  <dt>Art</dt>
                  <dd>{artist}</dd>
                </>
              )}
            </dl>
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
            Hover a card to read it.
          </motion.p>
        )}
      </AnimatePresence>
    </section>
  );
}
