/**
 * A card, drawn as a card.
 *
 * No images anywhere: the engine's card data is JSON in the repo with no
 * network dependency, and rendering text keeps the client the same. What has
 * changed from the old text tile is the *frame* -- a real title bar, type line,
 * rules box and P/T corner, sized in proportion so it reads as a playing card
 * rather than a list item.
 *
 * Every dimension derives from `--card-w`, which the containing zone sets. One
 * component therefore serves the hand, the battlefield and the preview panel.
 */

import type { CardView } from "../../api/types";
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
import { SymbolText } from "./SymbolText";

interface Props {
  card: CardView;
  /** Render the rules text box. Off on the battlefield, where it will not fit. */
  detail?: boolean;
}

export function CardFace({ card, detail = false }: Props) {
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
        The mana a land makes, big, where the art would be. This is the channel
        that reads at 66px in a pod, and it is a shape as well as a colour, so it
        survives greyscale and colour deficiency the way the type glyph does.
      */}
      {mana.length > 0 && (
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

      {!detail && card.keywords.length > 0 && (
        <div className="face__keywords">{card.keywords.map(keywordLabel).join(" · ")}</div>
      )}

      <div className="face__footer">
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
