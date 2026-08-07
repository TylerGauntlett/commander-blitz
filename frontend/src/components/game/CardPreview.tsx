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
import type { GameView } from "../../api/types";
import { keywordLabel } from "../../logic/cardStyle";
import { findCard } from "../../logic/zoneGrouping";
import { ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { StaticCard } from "./Card";

const PREVIEW_W = 236;

interface Props {
  state: GameView;
}

export function CardPreview({ state }: Props) {
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const card = hoveredOid === null ? null : findCard(state, hoveredOid);

  return (
    <section className="preview" data-testid="card-preview">
      <AnimatePresence mode="wait">
        {card ? (
          <motion.div
            key={card.oid}
            className="preview__body"
            style={{ ["--card-w" as string]: `${PREVIEW_W}px` }}
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
              {card.zone === "battlefield" && (card.damage ?? 0) > 0 && (
                <>
                  <dt>Damage</dt>
                  <dd className="preview__hurt">{card.damage} marked</dd>
                </>
              )}
              <dt>Zone</dt>
              <dd>{card.zone}</dd>
              <dt>Controller</dt>
              <dd>{state.players[card.controller]?.name ?? card.controller}</dd>
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
