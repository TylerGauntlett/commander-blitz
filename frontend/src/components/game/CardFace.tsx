/**
 * A card, drawn as a card.
 *
 * A real title bar, type line, art window, rules box and P/T corner, sized in
 * proportion so it reads as a playing card rather than a list item. Every
 * dimension derives from `--card-w`, which the containing zone sets -- one
 * component therefore serves the hand, the battlefield and the preview panel.
 *
 * The art is served by this application, never by a third party: the build
 * script downloads each crop once and the API serves the bytes. Three cards in
 * a hundred have no printing at all (they are original designs), and those get
 * a deliberate plate rather than a broken image.
 *
 * **Card type is encoded twice, on purpose.** The paper's fill carries it, as a
 * luminance ladder that survives greyscale -- but art covers most of the paper,
 * which is the objection mockups/README.md raises against putting art on the
 * board at all. So the type also gets a ring, drawn *over* the art at the
 * frame's inner edge, and the glyph in the title bar stays whatever else
 * happens. `tests/palette.test.ts` asserts the ring's ladder stays separable,
 * because that is the channel doing the work once the art is in place.
 */

import { useState } from "react";
import type { CardView } from "../../api/types";
import { artUrl } from "../../logic/cardArt";
import {
  counterBadges,
  frameTone,
  isPlainLand,
  isWounded,
  keywordLabel,
  landSymbols,
  landTone,
  manaPips,
  statLine,
  typeGlyph,
  typeLabel,
  typeTone,
} from "../../logic/cardStyle";
import { useUiStore } from "../../state/uiStore";
import { SymbolText } from "./SymbolText";

interface Props {
  card: CardView;
  /** Render the rules text box. Off on the battlefield, where it will not fit. */
  detail?: boolean;
}

export function CardFace({ card, detail = false }: Props) {
  const images = useUiStore((s) => s.images);
  // `undefined` = the map has not arrived; draw no band at all rather than
  // flashing a "no art" plate on every card during the first paint.
  const art = artUrl(images, card.card_id);
  const [broken, setBroken] = useState(false);
  const showArt = art !== undefined && art !== null && !broken;

  const pips = manaPips(card.mana_cost);
  const stats = statLine(card);
  const badges = counterBadges(card);
  const damage = card.damage ?? 0;
  const hurt = isWounded(card);

  // What a land taps for, on the two channels a land has spare. Every land used
  // to be the same tan rectangle, so a board of twelve of them was unreadable
  // without stopping to read names -- see docs/playtest-feedback-02.md item 8.
  const land = landTone(card);
  const mana = landSymbols(card);

  const classes = [
    "face",
    // Border carries colour identity, body fill carries card type. Two axes
    // that both matter at a glance, on two channels that do not collide.
    `face--${frameTone(card)}`,
    `face--type-${typeTone(card)}`,
    // Lands narrow the type fill to the colour they make. It overrides only the
    // same two stops `face--type-*` sets, so nothing else about the frame moves.
    land ? `face--land-${land}` : "",
    card.is_commander ? "face--commander" : "",
    card.is_token ? "face--token" : "",
    // A face that also shows rules text caps its art band instead of letting
    // it take the remaining height, or the text is squeezed to nothing.
    detail ? "face--detail" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} data-card-name={card.name} data-type-tone={typeTone(card)}>
      <div className="face__title">
        <span className="face__glyph" title={typeLabel(card)} aria-hidden="true">
          {typeGlyph(card)}
        </span>
        <span className="face__name">{card.name}</span>
        {pips.length > 0 && (
          <span className="face__cost">
            {pips.map((pip) => (
              <span className={`pip pip--${pip.tone}`} key={pip.key}>
                {pip.symbol}
              </span>
            ))}
          </span>
        )}
      </div>

      <div className="face__type">{card.type_line}</div>

      {/*
        The art window.

        A hairline of the type tint is kept all the way round -- see `.face`'s
        padding and the type ring in cards.css -- so the fill that encodes card
        type is never completely replaced by somebody's illustration.
      */}
      {art !== undefined && (
        <div
          className={showArt ? "face__art" : "face__art face__art--none"}
          data-art={showArt ? "ready" : "none"}
        >
          {showArt ? (
            // A 404 is a real case: art is fetched lazily for anything outside
            // the shipped card pool, and a fetch can fail. Fall back to the
            // plate rather than to the browser's broken-image glyph.
            <img src={art} alt="" loading="lazy" onError={() => setBroken(true)} />
          ) : (
            <span>no art</span>
          )}
          {/*
            On a land the mana symbol rides *over* the art rather than replacing
            it. That symbol is the channel that reads at 60px in a pod, and it
            is a shape as well as a colour, so it survives greyscale and colour
            deficiency the way the type glyph does -- losing it to the art would
            cost more than the art gains.
          */}
          {mana.length > 0 && (
            <div className="watermark-row" aria-hidden="true">
              {mana.map((symbol) => (
                <span className={`watermark-pip watermark-pip--${symbol}`} key={symbol}>
                  {symbol}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/*
        Before the art map loads -- and it may never load, if the server has no
        images -- a land still shows its mana symbols in the space the art would
        occupy. This is the pre-art layout, kept intact.
      */}
      {art === undefined && mana.length > 0 && (
        <div className="face__watermark" aria-hidden="true">
          {mana.map((symbol) => (
            <span className={`watermark-pip watermark-pip--${symbol}`} key={symbol}>
              {symbol}
            </span>
          ))}
        </div>
      )}

      {/*
        A basic land's rules text *is* its mana ability, which the watermark now
        says better. Anything else keeps its text -- a nonbasic that taps for
        mana and does something else is exactly the card you need to read.
      */}
      {/*
        The wrapper stays a div and `SymbolText` goes inside it. `.face__rules`
        is a flex column, so putting the class on `SymbolText`'s own span made
        every pip a flex *item* -- each one stretched to the full width of the
        card and the rules box became a stack of coloured bars.
      */}
      {detail && card.oracle_text && !isPlainLand(card) && (
        <div className="face__rules">
          <SymbolText text={card.oracle_text} />
        </div>
      )}

      <div className="face__footer">
        {/* Keywords used to have a row of their own; the art band took it, so
            they share the footer with the counters and the P/T. */}
        {!detail && card.keywords.length > 0 && (
          <span className="face__kwline">{card.keywords.map(keywordLabel).join(" · ")}</span>
        )}
        {badges.length > 0 && (
          <span className="face__counters">
            {badges.map((badge) => (
              <span className="counter-badge" key={badge}>
                {badge}
              </span>
            ))}
          </span>
        )}
        <span className="spacer" />
        {stats && (
          <span
            className={hurt ? "face__stats face__stats--hurt" : "face__stats"}
            title={hurt ? `${damage} damage marked` : undefined}
          >
            {stats}
          </span>
        )}
      </div>

      {card.is_commander && (
        <span className="face__tag face__tag--cmd" title="Commander">
          CMD
        </span>
      )}
      {card.summoning_sick && card.types.includes("Creature") && (
        <span className="face__tag face__tag--sick" title="Summoning sick">
          &#9203;
        </span>
      )}
    </div>
  );
}
