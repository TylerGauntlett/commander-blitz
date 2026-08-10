/**
 * A commander, drawn with the real card face.
 *
 * The lobby shows cards that are not in a game -- there is no board, no oid, no
 * controller -- but they must be the *same object* the table will put in the
 * preview rail. A lookalike would be two card designs to keep in step, and the
 * one place a player compares them directly is the moment the pod deals.
 *
 * So this adapts `GET /api/cards/{id}` into the `CardView` shape `CardFace`
 * takes. The synthetic fields are all honest: a card outside a game genuinely
 * has no damage, no counters and no controller, and `oid: -1` marks it as an
 * object that is not on any battlefield.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { CardResponse, CardView } from "../../api/types";
import { StaticCard } from "../game/Card";
import { CardBack } from "./CardBack";

/**
 * Split a type line into the three lists `cardStyle` reads.
 *
 * "Legendary Creature — Serpent" -> supertypes, types, subtypes. The em dash is
 * what Scryfall prints and what the engine stores, so it is what is split on;
 * a plain hyphen is accepted because hand-written card files occasionally use
 * one.
 */
export function splitTypeLine(typeLine: string): {
  supertypes: string[];
  types: string[];
  subtypes: string[];
} {
  const [front, back] = typeLine.split(/\s+[—-]\s+/);
  const words = (front ?? "").split(/\s+/).filter(Boolean);
  const SUPER = new Set(["Legendary", "Basic", "Snow", "World", "Ongoing", "Token"]);
  return {
    supertypes: words.filter((word) => SUPER.has(word)),
    types: words.filter((word) => !SUPER.has(word)),
    subtypes: (back ?? "").split(/\s+/).filter(Boolean),
  };
}

/** A printed card, as the face component wants it. */
export function cardViewFor(
  card: CardResponse,
  options: { commander?: boolean } = {},
): CardView {
  const { supertypes, types, subtypes } = splitTypeLine(card.type_line);
  return {
    // Not on any battlefield. Negative rather than 0, which is a real oid.
    oid: -1,
    card_id: card.id,
    name: card.name,
    type_line: card.type_line,
    mana_cost: card.mana_cost,
    mana_value: card.mana_value,
    colors: card.colors,
    oracle_text: card.oracle_text,
    controller: 0,
    owner: 0,
    zone: "command",
    is_token: false,
    is_commander: options.commander ?? true,
    power: card.power,
    toughness: card.toughness,
    types,
    subtypes,
    keywords: card.keywords,
    supertypes,
    // A printed card outside a game taps for nothing in particular; the lobby
    // never shows a land, so this is empty rather than guessed from the text.
    produces: [],
  };
}

interface Props {
  cardId: string | null;
  variant?: "board" | "detail" | "big";
  /** What the back should say while the card is loading or absent. */
  placeholder?: string;
}

export function CommanderCard({ cardId, variant = "big", placeholder = "Loading" }: Props) {
  const query = useQuery({
    queryKey: ["card", cardId],
    queryFn: () => api.card(cardId as string),
    enabled: cardId !== null,
    // A printed card is immutable for the life of the process.
    staleTime: Number.POSITIVE_INFINITY,
  });

  if (!cardId || !query.data) {
    return <CardBack mark={placeholder} tone="empty" testId="card-loading" />;
  }
  /*
    `podcard` is what `lobby.css` scopes the enlarged card's box on.

    `cards.css`'s `.card--big` is the *preview rail's* card: width-driven with
    `height: 100%`, and it only holds its shape because `.rail--right .preview`
    gives it a fixed frame. The lobby has no such container, so the same rule
    collapses to content sizing and a card ends up as tall as its own rules
    text. `lobby.css` re-boxes it under this class.

    Emitted unconditionally rather than passed per call site: this component is
    the lobby's only door to `StaticCard`, so a class it always adds cannot be
    forgotten -- and it matches nothing on `variant="board"`, which the deck
    catalogue's rack uses and which is already correct.
  */
  return <StaticCard card={cardViewFor(query.data)} variant={variant} className="podcard" />;
}
