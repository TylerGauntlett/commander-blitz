/**
 * Everything about one deck, in an overlay.
 *
 * The half of this that is editorial (tags, ratings, strategy, signature cards)
 * and the half that is derived from the list (curve, lands, swaps) are drawn
 * differently on purpose: an imported deck has none of the first half, and the
 * honest thing is to say so rather than to invent a strategy paragraph or draw
 * a flat rating bar. Every empty state below is a real state something reaches.
 */

import { useRef } from "react";
import type { DeckRatings } from "../../api/types";
import { useDismiss } from "../../input/useDismiss";
import { artistOf } from "../../logic/cardArt";
import { useUiStore } from "../../state/uiStore";
import { useDeckDetail } from "../../state/usePod";
import { ManaSymbol } from "../game/ManaSymbol";
import { SymbolText } from "../game/SymbolText";
import { CommanderCard } from "./CommanderCard";

const BAR_LABELS: [keyof DeckRatings, string][] = [
  ["speed", "Speed"],
  ["complexity", "Complexity"],
  ["interaction", "Interaction"],
  ["resilience", "Resilience"],
  ["pilot", "Demands on you"],
];

/** A 1-4 rating, as four segments. Four, not five: an odd scale has a middle. */
export function RatingBar({
  label,
  value,
  tiny = false,
}: {
  label: string;
  value: number;
  tiny?: boolean;
}) {
  return (
    <div className={tiny ? "bar bar--tiny" : "bar"} data-testid={`bar-${label}`}>
      <span className="bar__label">{label}</span>
      <span className="bar__track" role="img" aria-label={`${label}: ${value} of 4`}>
        {[1, 2, 3, 4].map((step) => (
          <i key={step} className={step <= value ? "bar__seg bar__seg--on" : "bar__seg"} />
        ))}
      </span>
    </div>
  );
}

/**
 * Seven columns: mana values 1..6 and 7+.
 *
 * Heights are a share of the tallest bucket rather than of the card count --
 * against 37 lands every column would be a stub. Lands are excluded server-side
 * for the same reason.
 */
export function ManaCurve({ values }: { values: number[] }) {
  if (!values.length || values.every((v) => v === 0)) {
    return (
      <div className="curve__none" data-testid="curve-empty">
        No curve for this one. A curve is a count of a list, and this deck's list is not one the
        engine holds.
      </div>
    );
  }
  const max = Math.max(...values);
  const label = (i: number) => `${i + 1}${i === values.length - 1 ? "+" : ""}`;
  return (
    <div className="curve" data-testid="curve">
      <div className="curve__cols">
        {values.map((value, i) => (
          <span
            key={label(i)}
            className="curve__bar"
            style={{ height: `${Math.round((value / max) * 100)}%` }}
            data-hint={`${value} cards at ${label(i)} mana`}
          />
        ))}
      </div>
      <div className="curve__axis">
        {values.map((_, i) => (
          <span key={label(i)} className="curve__n tabular">
            {label(i)}
          </span>
        ))}
      </div>
    </div>
  );
}

interface Props {
  deckId: string;
  /** Shown only when this dossier was opened from a seat you may change. */
  canTake: boolean;
  onTake: (deckId: string) => void;
  onClose: () => void;
}

export function DeckDossier({ deckId, canTake, onTake, onClose }: Props) {
  const query = useDeckDetail(deckId);
  const deck = query.data;
  // Pulled out so the null check narrows: `deck.ratings` inside a callback is
  // a fresh property read every time and TypeScript will not carry the guard.
  const ratings = deck?.ratings ?? null;

  // The same function and the same map the preview rail reads. Lifting
  // `CommanderCard`'s own card query up here would give the lobby a second
  // answer to "who drew this", which is the duplication that costs -- not the
  // request, which react-query would dedupe anyway.
  const images = useUiStore((state) => state.images);
  const commander = deck?.commanders[0] ?? null;
  const artist = commander ? artistOf(images, commander) : null;

  /* Escape and B alike, and only while this is the top of the stack -- the
     catalogue underneath opens this one and must not close with it. */
  const panel = useRef<HTMLElement>(null);
  useDismiss(panel, onClose);

  return (
    <>
      <div className="veil veil--dossier" onClick={onClose} aria-hidden="true" />
      <aside
        ref={panel}
        className="dos"
        role="dialog"
        aria-modal="true"
        data-modal-root
        aria-label={deck?.name ?? "Deck details"}
        data-testid="deck-dossier"
      >
        <div className="dos__head">
          <span className="dos__n">{deck?.name ?? "Loading…"}</span>
          {deck?.color_identity.map((colour) => (
            <ManaSymbol key={colour} code={colour} />
          ))}
          {deck && deck.simplified > 0 && (
            <span className="badge badge--partial">{deck.simplified} simplified</span>
          )}
          <button
            type="button"
            className="key key--mark dos__x"
            aria-label="Close"
            data-testid="dossier-close"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="dos__body">
          {query.error && (
            <p className="dos__p">Could not load this deck: {(query.error as Error).message}</p>
          )}
          {deck && (
            <>
              <div className="dos__top">
                <div className="dos__card">
                  <CommanderCard cardId={commander} variant="big" />
                  {/* Absent while the image map is still loading, and absent
                      forever on a server with no art. Both are "we do not
                      know", and neither is worth a placeholder. */}
                  {artist && <div className="dos__artist">Art: {artist}</div>}
                </div>
                <div className="dos__col">
                  <h3 className="dos__h">The deck</h3>
                  <p className="dos__p">
                    {deck.notes ||
                      "No description for this one — it was imported, not authored."}
                  </p>

                  <h3 className="dos__h">Playstyle</h3>
                  {deck.tags.length > 0 ? (
                    <div className="dos__tags">
                      {deck.tags.map((tag) => (
                        <span className="chip" key={tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="dos__p dos__p--none">Untagged.</p>
                  )}

                  {ratings ? (
                    <div className="dos__bars" data-testid="dossier-ratings">
                      {BAR_LABELS.map(([key, label]) => (
                        <RatingBar key={key} label={label} value={ratings[key]} />
                      ))}
                    </div>
                  ) : (
                    <p className="dos__p dos__p--none" data-testid="dossier-no-ratings">
                      No ratings. Nothing in a card list says a deck is hard to pilot, so these
                      are editorial — and an imported deck has never been played by anybody
                      here.
                    </p>
                  )}
                </div>
              </div>

              <h3 className="dos__h">How it plays</h3>
              {deck.strategy ? (
                <p className="dos__p">{deck.strategy}</p>
              ) : (
                <p className="dos__p dos__p--none">No write-up. This is whatever you built.</p>
              )}

              <h3 className="dos__h">Cards that define it</h3>
              {deck.signature.length > 0 ? (
                <div className="dos__sigs">
                  {deck.signature.map((card) => (
                    <div className="sig" key={card.card_id}>
                      {card.art_url ? (
                        <img className="sig__art" src={card.art_url} alt="" loading="lazy" />
                      ) : (
                        <span className="sig__art sig__art--none" aria-hidden="true" />
                      )}
                      <div>
                        <div className="sig__n">{card.name}</div>
                        <div className="sig__why">{card.why}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="dos__p dos__p--none" data-testid="dossier-no-signature">
                  None picked. Choosing three cards to call defining is a judgement, and nobody
                  has made it for this list.
                </p>
              )}

              <h3 className="dos__h">Mana curve</h3>
              <ManaCurve values={deck.curve} />
              <p className="dos__p dos__p--foot">
                {deck.lands} lands · {deck.card_count} cards
              </p>

              {deck.swap_note ? (
                <div className="note" data-testid="dossier-swaps">
                  <SymbolText text={deck.swap_note} />
                </div>
              ) : deck.simplified > 0 ? (
                <div className="note">
                  {deck.simplified} of the imported cards use rules the engine does not
                  implement. They are in the deck and they are castable; their non-keyword text
                  does nothing.
                </div>
              ) : (
                <div className="note">Every card implemented and tested.</div>
              )}
            </>
          )}
        </div>

        <div className="dos__foot">
          {canTake && (
            <button
              type="button"
              className="key key--commit dos__take"
              data-testid="dossier-take"
              disabled={!deck}
              onClick={() => deck && onTake(deck.id)}
            >
              Take this deck
            </button>
          )}
          <button type="button" className="key key--quiet" onClick={onClose}>
            Close
          </button>
        </div>
      </aside>
    </>
  );
}
