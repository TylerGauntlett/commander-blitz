/**
 * Every deck, as cards, over the whole screen.
 *
 * A full takeover rather than a panel, and that is the honest consequence of the
 * metaphor rather than an oversight: a row of four large cards owns the lobby,
 * so there is nowhere to put a two-dozen-deck browser except over the top of it.
 *
 * **The card is the control.** A "Take it" button under something already the
 * size and shape of a thing you pick up was a second target for the first
 * target's job. `role`/`tabIndex` rather than a real `<button>`, because a
 * `<button>` may not contain the divs a card face is made of; the key handler
 * supplies Enter and Space in exchange.
 *
 * The colour filter is an AND, deliberately: three colours means decks that play
 * all three, which is the question somebody filtering by colour is asking.
 */

import { useEffect, useMemo, useState } from "react";
import type { DeckImportResponse, DeckSummary } from "../../api/types";
import {
  type CatalogFilters,
  type DeckSort,
  type DeckSource,
  EMPTY_FILTERS,
  visibleDecks,
} from "../../logic/lobby";
import { ManaSymbol } from "../game/ManaSymbol";
import { DeckImport } from "../menu/DeckImport";
import { CommanderCard } from "./CommanderCard";
import { RatingBar } from "./DeckDossier";

const COLOURS: [string, string][] = [
  ["W", "White"],
  ["U", "Blue"],
  ["B", "Black"],
  ["R", "Red"],
  ["G", "Green"],
];

const SORTS: [DeckSort, string][] = [
  ["name", "Name"],
  ["speed", "Fastest"],
  ["complexity", "Most complex"],
  ["pilot", "Easiest to pilot"],
];

const SOURCES: [DeckSource, string][] = [
  ["all", "All"],
  ["precon", "Precons"],
  ["moxfield", "Yours"],
];

interface Props {
  decks: DeckSummary[];
  /** Which seat this catalogue is choosing for. 0-3, or null when browsing. */
  forSeat: number | null;
  forWhom: string;
  /** The deck that seat is already holding, so its card can carry the tick. */
  chosen: string | null;
  onPick: (deckId: string) => void;
  onDossier: (deckId: string) => void;
  onClose: () => void;
  onImported: (result: DeckImportResponse) => void;
}

export function DeckCatalog({
  decks,
  forSeat,
  forWhom,
  chosen,
  onPick,
  onDossier,
  onClose,
  onImported,
}: Props) {
  const [filters, setFilters] = useState<CatalogFilters>(EMPTY_FILTERS);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shown = useMemo(() => visibleDecks(decks, filters), [decks, filters]);

  const set = <K extends keyof CatalogFilters>(key: K, value: CatalogFilters[K]) =>
    setFilters((current) => ({ ...current, [key]: value }));

  const toggleColour = (colour: string) =>
    setFilters((current) => ({
      ...current,
      colours: current.colours.includes(colour)
        ? current.colours.filter((c) => c !== colour)
        : [...current.colours, colour],
    }));

  return (
    <section
      className="cat"
      role="dialog"
      aria-modal="true"
      aria-label="Deck catalogue"
      data-testid="deck-catalog"
    >
      <div className="cat__head">
        <span className="cat__t">Turn a card face up</span>
        <span className="cat__for">{forWhom}</span>
        <button
          type="button"
          className="cat__x"
          aria-label="Close"
          data-testid="deck-catalog-close"
          onClick={onClose}
        >
          ✕
        </button>
      </div>

      <div className="filters">
        <label className="search">
          <span className="search__g" aria-hidden="true">
            ⌕
          </span>
          <input
            className="search__i"
            type="text"
            value={filters.q}
            onChange={(event) => set("q", event.target.value)}
            placeholder="Search decks, commanders, archetypes"
            spellCheck={false}
            aria-label="Search decks"
            data-testid="deck-search"
          />
        </label>

        <span className="fgroup">
          <span className="fgroup__l">Colours</span>
          {COLOURS.map(([code, name]) => {
            const on = filters.colours.includes(code);
            return (
              <button
                type="button"
                key={code}
                className={on ? "cbtn cbtn--on" : "cbtn"}
                onClick={() => toggleColour(code)}
                title={name}
                aria-label={name}
                aria-pressed={on}
                data-testid={`colour-${code}`}
              >
                <ManaSymbol code={code} title={name} />
              </button>
            );
          })}
          {filters.colours.length > 0 && (
            <button type="button" className="link" onClick={() => set("colours", [])}>
              clear
            </button>
          )}
        </span>

        <span className="seg">
          {SOURCES.map(([id, name]) => (
            <button
              type="button"
              key={id}
              className={filters.source === id ? "seg__b seg__b--on" : "seg__b"}
              onClick={() => set("source", id)}
              data-testid={`source-${id}`}
            >
              {name}
            </button>
          ))}
        </span>

        <select
          className="sel"
          value={filters.sort}
          onChange={(event) => set("sort", event.target.value as DeckSort)}
          aria-label="Sort decks"
          data-testid="deck-sort"
        >
          {SORTS.map(([id, name]) => (
            <option value={id} key={id}>
              Sort: {name}
            </option>
          ))}
        </select>

        <span className="filters__spacer" />
        <span className="filters__n tabular" data-testid="deck-count">
          {shown.length} of {decks.length}
        </span>
      </div>

      <div className="cat__body">
        {shown.length > 0 ? (
          <div className="rack">
            {shown.map((deck) => (
              <DeckPick
                key={deck.id}
                deck={deck}
                selected={deck.id === chosen}
                onPick={onPick}
                onDossier={onDossier}
              />
            ))}
          </div>
        ) : (
          <div className="empty" data-testid="deck-catalog-empty">
            Nothing matches that.
            <br />
            Clear a colour or two — the filter is an AND, so three colours means decks that play
            all three.
          </div>
        )}
      </div>

      <div className="cat__foot">
        {/* The same component the front door used to carry, in the catalogue's
            box. See the note at the top of `DeckImport`. */}
        <DeckImport variant="row" onImported={onImported} />
      </div>

      {forSeat === null && (
        <span className="cat__browsing" data-testid="catalog-browsing">
          Browsing. Create or join a pod to take one of these.
        </span>
      )}
    </section>
  );
}

function DeckPick({
  deck,
  selected,
  onPick,
  onDossier,
}: {
  deck: DeckSummary;
  selected: boolean;
  onPick: (deckId: string) => void;
  onDossier: (deckId: string) => void;
}) {
  const take = () => onPick(deck.id);
  return (
    <div
      className={selected ? "pick pick--on" : "pick"}
      data-testid={`deck-${deck.id}`}
      data-selected={selected ? "yes" : "no"}
    >
      <div
        className="pick__card"
        role="button"
        tabIndex={0}
        aria-label={selected ? `${deck.name} — selected` : `Take ${deck.name}`}
        onClick={take}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            take();
          }
        }}
      >
        <CommanderCard cardId={deck.commanders[0] ?? null} variant="board" />
        {selected && (
          <span className="pick__tick" aria-hidden="true">
            ✓
          </span>
        )}
      </div>
      <div className="pick__n">{deck.name}</div>
      <div className="pick__s">{deck.commander_names.join(" & ")}</div>
      <div className="pick__meta">
        {deck.color_identity.map((colour) => (
          <ManaSymbol key={colour} code={colour} />
        ))}
        <span className="badge badge--src">
          {deck.source === "moxfield" ? "Yours" : "Precon"}
        </span>
        {/* Only when there is something to admit. A precon is hand-written all
            the way through, so this stays off its tiles entirely. */}
        {deck.simplified > 0 && (
          <span className="badge badge--partial" data-testid={`deck-${deck.id}-simplified`}>
            {deck.simplified} simplified
          </span>
        )}
        <button
          type="button"
          className="ibtn"
          title="Deck details"
          aria-label={`Details for ${deck.name}`}
          onClick={() => onDossier(deck.id)}
          data-testid={`deck-${deck.id}-info`}
        >
          i
        </button>
      </div>
      {deck.tags.length > 0 && (
        <div className="pick__tags">
          {deck.tags.slice(0, 3).map((tag) => (
            <span className="chip chip--tiny" key={tag}>
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Re-exported so a screen can draw one bar without reaching into the dossier. */
export { RatingBar };
