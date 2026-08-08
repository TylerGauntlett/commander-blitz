/**
 * A card, drawn as a card.
 *
 * An art window, title bar, type line, rules box and P/T corner, sized in
 * proportion so it reads as a playing card rather than a list item. Every
 * dimension derives from `--card-w`, which the containing zone sets -- one
 * component therefore serves the hand, the battlefield and the preview panel.
 *
 * **The art sits above the text, in every variant.** It used to sit between the
 * type line and the footer, taking the remaining height as `flex: 1` -- which on
 * a hand card meant the rules box was whatever was left after a greedy art band,
 * about six pixels of type. Art first at a fixed 1.4 aspect gives the text a
 * contiguous block of known height underneath it, which is both the arrangement
 * mockups/05-planar-art.html uses for its enlarged card and the reason that card
 * is the readable one. See docs/mockup-fidelity.md.
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

/**
 * How much card there is room to draw.
 *
 * All three share the layout above and differ only in scale and in whether
 * there is room for rules text:
 *
 *   board   -- hand, battlefield, opponents' mats, command zone. No rules box;
 *              at these sizes it renders at six pixels, which is not text.
 *   detail  -- the stack, the mulligan dialog, the zone peek. Big enough to
 *              carry rules, still a 1.4 portrait card.
 *   big     -- the preview rail alone. Width-driven rather than portrait, so it
 *              grows to fit the rules rather than clipping them, with absolute
 *              type sizes instead of ratios of `--card-w`.
 */
export type CardVariant = "board" | "detail" | "big";

interface Props {
  card: CardView;
  variant?: CardVariant;
}

export function CardFace({ card, variant = "board" }: Props) {
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
    variant === "detail" ? "face--detail" : "",
    variant === "big" ? "face--big" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // `board` is every small card on screen, and a rules box there is six pixels
  // tall. The text is one hover away in the preview rail, which is the surface
  // that was rebuilt to hold it.
  const showsRules = variant !== "board";

  return (
    <div className={classes} data-card-name={card.name} data-type-tone={typeTone(card)}>
      {/*
        The art window, and it comes first.

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
        occupy. It takes the art's slot at the top and the art's aspect, so the
        text below it does not jump when the map arrives.
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
      {showsRules && card.oracle_text && !isPlainLand(card) && (
        <div className="face__rules">
          <SymbolText text={card.oracle_text} />
        </div>
      )}

      <div className="face__footer">
        {/* Keywords used to have a row of their own; the art band took it, so
            they share the footer with the counters and the P/T. Only where
            there is no rules box -- otherwise the text already says them. */}
        {!showsRules && card.keywords.length > 0 && (
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
