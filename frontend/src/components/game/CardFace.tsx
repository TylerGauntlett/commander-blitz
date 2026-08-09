/**
 * A card, drawn as a card.
 *
 * **The art is the card.** It fills the whole frame, and the text sits on graded
 * scrims at the top and bottom -- direction D, "Art Bleed", of
 * `mockups/cards/index.html`. Three rows of tinted paper with a window cut in
 * them is what this replaced, and the window was always the part anyone actually
 * looked at.
 *
 * Every dimension derives from `--card-w`, which the containing zone sets -- one
 * component therefore serves the hand, the battlefield and the preview panel.
 *
 * The art is served by this application, never by a third party: the build
 * script downloads each crop once and the API serves the bytes. Three cards in
 * a hundred have no printing at all (they are original designs), and those get
 * a deliberate plate rather than a broken image.
 *
 * **Card type is no longer a colour.** It used to be: an eight-step luminance
 * ladder on the card stock, plus a matching ring, because a type line renders at
 * 5.6px on a pod board and something had to say "creature" from across the
 * table. A full-bleed illustration says it better and says it per *card* rather
 * than per category, so the ladder is gone. What carries the category at pod
 * size instead is the type glyph in the title and the type line itself. The
 * frame keeps colour *identity*, which is a different fact and was never the
 * thing the ladder encoded.
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
  shortType,
  statLine,
  typeGlyph,
  typeLabel,
  typeTone,
} from "../../logic/cardStyle";
import { useUiStore } from "../../state/uiStore";
import { ManaSymbol } from "./ManaSymbol";
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
  // `undefined` = the map has not arrived; draw no art layer at all rather than
  // flashing a "no art" plate on every card during the first paint.
  const art = artUrl(images, card.card_id);
  const [broken, setBroken] = useState(false);
  const showArt = art !== undefined && art !== null && !broken;

  const pips = manaPips(card.mana_cost);
  const stats = statLine(card);
  const badges = counterBadges(card);
  const damage = card.damage ?? 0;
  const hurt = isWounded(card);

  // What a land taps for. Every land used to be the same tan rectangle, so a
  // board of twelve of them was unreadable without stopping to read names --
  // see docs/playtest-feedback-02.md item 8. On a bleed face the symbols are
  // large and centred over the art, which is direction D's answer for lands.
  const land = landTone(card);
  const mana = landSymbols(card);

  const classes = [
    "face",
    // The frame carries colour identity, and now the ground the art sits on
    // too -- on the ~4% of cards with no printing that gradient is the whole
    // card, so it has to be worth looking at.
    `face--${frameTone(card)}`,
    // Kept for the selectors that read it (`data-type-tone` below, and
    // `e2e/clarity.spec.ts`). It no longer sets a colour: see the note at the
    // top of the file.
    `face--type-${typeTone(card)}`,
    // Lands narrow the frame to the colour they make, so a lane of them reads
    // as a row of spines without reading a single name.
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

  /*
    A basic land's rules text *is* its mana ability, which the symbols now say
    better. Anything else keeps its text -- a nonbasic that taps for mana and
    does something else is exactly the card you need to read.
  */
  const rules = showsRules && card.oracle_text && !isPlainLand(card);

  const isLand = card.types.includes("Land");

  /*
    The mana symbols a land makes, centred over the art.

    Two class names for one idea, and both are load-bearing: `.watermark-row`
    rides on top of a real illustration, `.face__watermark` is what a land shows
    before the art map has arrived -- or forever, on a server with no images.
    They render identically now that neither one has a layout slot to reserve.

    A land that taps for no colour at all -- Terramorphic Expanse -- gets a
    neutral mark rather than nothing. It is the one land on the board that is
    actually interesting, and it was the only one with no centre symbol at all.
  */
  const watermark = (className: string) => (
    <div className={className} aria-hidden="true">
      {mana.length > 0 ? (
        mana.map((symbol) => (
          <ManaSymbol
            code={symbol}
            className={`watermark-pip watermark-pip--${symbol}`}
            key={symbol}
          />
        ))
      ) : (
        <span className="watermark-none" title="Produces no colour">
          &#9650;
        </span>
      )}
    </div>
  );

  return (
    <div className={classes} data-card-name={card.name} data-type-tone={typeTone(card)}>
      {/*
        The art, and it is the whole face: `position: absolute; inset: 0` under
        both scrims. Everything else on the card is drawn over it.
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
            // `face__art-img` rather than a bare `<img>`: a land's mana symbols
            // are images too and they live inside this same box, so `.face__art
            // img` stopped meaning "the illustration" the moment the symbols
            // became real artwork.
            <img
              className="face__art-img"
              src={art}
              alt=""
              loading="lazy"
              onError={() => setBroken(true)}
            />
          ) : (
            <span>no art</span>
          )}
          {isLand && watermark("watermark-row")}
        </div>
      )}

      {art === undefined && isLand && watermark("face__watermark")}

      {/*
        The top scrim: what the card is called, and what it costs.

        The cost gets a row of its own rather than sharing the title's. That is
        the point of the direction -- a name can be as long as it likes and
        never meets its own mana cost, which is what "Aesi, Tyrant of Gyre
        Strait" against {4}{G}{U} used to do at every size.
      */}
      <div className="face__head">
        <div className="face__title">
          <span className="face__glyph" title={typeLabel(card)} aria-hidden="true">
            {typeGlyph(card)}
          </span>
          <span className="face__name">
            {/*
              The commander mark goes *inside* the name, not in a corner.

              It was a `CMD` badge pinned to the frame. A corner tag is a second
              thing competing for a corner the P/T and the sickness mark have
              already claimed, and at pod size it rendered at under 3px, which is
              not a word. A real legendary wears a crown on its frame; this is
              the cheap version of the same idea, it scales with the name, and it
              costs no space that was not already the name's.
            */}
            {card.is_commander && (
              <span className="crown" title="Commander" aria-label="Commander">
                &#9819;
              </span>
            )}
            {card.name}
          </span>
        </div>
        {pips.length > 0 && (
          <span className="face__cost">
            {pips.map((pip) => (
              <ManaSymbol code={pip.symbol} className={`pip--${pip.tone}`} key={pip.key} />
            ))}
          </span>
        )}
      </div>

      {/*
        The bottom scrim: what it is, what it does, and what it is wearing.

        `margin-top: auto` pushes it to the foot whatever the head above it
        weighs, so the art between them is never squeezed by a two-line name.
      */}
      <div className="face__foot">
        {/* Supertypes come off where the line has no room for them; see
            `shortType`. The rail and the dialogs keep the full line. */}
        <div className="face__type">
          {showsRules ? card.type_line : shortType(card.type_line)}
        </div>

        {/*
          The wrapper stays a div and `SymbolText` goes inside it.
          `.face__rules` is a flex column, so putting the class on
          `SymbolText`'s own span made every pip a flex *item* -- each one
          stretched to the full width of the card and the rules box became a
          stack of coloured bars.
        */}
        {rules && (
          <div className="face__rules">
            <SymbolText text={card.oracle_text} />
          </div>
        )}

        <div className="face__footer">
          {/* Keywords have no row of their own; they share the footer with the
              counters and the P/T. Only where there is no rules box --
              otherwise the text already says them. */}
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
      </div>

      {/* The commander mark is the crown in the name above; see the note there. */}
      {card.summoning_sick && card.types.includes("Creature") && (
        <span className="face__tag face__tag--sick" title="Summoning sick">
          &#9203;
        </span>
      )}
    </div>
  );
}
