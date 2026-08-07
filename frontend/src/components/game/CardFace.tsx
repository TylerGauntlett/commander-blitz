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
  keywordLabel,
  manaPips,
  statLine,
  typeGlyph,
  typeLabel,
  typeTone,
} from "../../logic/cardStyle";

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

  const classes = [
    "face",
    // Border carries colour identity, body fill carries card type. Two axes
    // that both matter at a glance, on two channels that do not collide.
    `face--${frameTone(card)}`,
    `face--type-${typeTone(card)}`,
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

      {detail && card.oracle_text && <div className="face__rules">{card.oracle_text}</div>}

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
            className={damage > 0 ? "face__stats face__stats--hurt" : "face__stats"}
            title={damage > 0 ? `${damage} damage marked` : undefined}
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
