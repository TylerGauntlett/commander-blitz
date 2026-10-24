/**
 * Every deck, as cards, in the same room the door and the pod stand in.
 *
 * A full takeover rather than a panel, and that is the honest consequence of
 * the metaphor rather than an oversight: a row of four large cards owns the
 * lobby, so there is nowhere to put a two-dozen-deck browser except over the
 * top of it. Being a takeover is also why it is a `Room` rather than a scrim
 * over one -- a panel floating on a blurred copy of the screen behind it is the
 * web's idea of a modal, and this is the shelf you walk to.
 *
 * **The card is the control.** A "Take it" button under something already the
 * size and shape of a thing you pick up was a second target for the first
 * target's job. `role`/`tabIndex` rather than a real `<button>`, because a
 * `<button>` may not contain the divs a card face is made of; the key handler
 * supplies Enter and Space in exchange.
 *
 * The colour filter is an AND, deliberately: three colours means decks that
 * play all three, which is the question somebody filtering by colour is asking.
 *
 * ---------------------------------------------------------------------------
 * ## The ring opens on a deck, not on the ✕
 *
 * `resolveCursor` falls back to the first stop of whatever surface is on top,
 * which here is the close button -- so opening the catalogue with a pad put the
 * ring on the way OUT of the screen you had just asked for. The one line in the
 * layout effect below is the whole fix, and it lands on the deck you already
 * hold when there is one, because "change my deck" and "choose a deck" are the
 * same control and only one of them starts from nothing.
 */

import { Fragment, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DeckImportResponse, DeckSummary, UpcomingPrecon } from "../../api/types";
import { setCursor } from "../../input/cursor";
import { useDismiss } from "../../input/useDismiss";
import { canImport } from "../../logic/desktop";
import {
  archetypeName,
  archetypeOptions,
  type CatalogFilters,
  type DeckSort,
  type DeckSource,
  EMPTY_FILTERS,
  groupDecks,
  nextArchetype,
  visibleDecks,
  visibleShells,
} from "../../logic/lobby";
import { useAppConfig } from "../../state/useAppConfig";
import { ManaSymbol } from "../game/ManaSymbol";
import { DeckImport } from "../menu/DeckImport";
import { Glyph } from "../ui/Glyph";
import { CommanderCard } from "./CommanderCard";
import { RatingBar } from "./DeckDossier";
import { Room, SHELF_HUE } from "./Room";

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

/** The order after this one, wrapping round. */
function nextSort(sort: DeckSort): DeckSort {
  const at = SORTS.findIndex(([id]) => id === sort);
  return SORTS[(at + 1) % SORTS.length][0];
}

function sortName(sort: DeckSort): string {
  return SORTS.find(([id]) => id === sort)?.[1] ?? SORTS[0][1];
}

/* ADR 0024: each segment is a promise about where its decks came from. */
const SOURCES: [DeckSource, string][] = [
  ["all", "All"],
  ["precon", "Precons"],
  ["favorite", "Favorites"],
  ["moxfield", "Yours"],
];

interface Props {
  decks: DeckSummary[];
  /**
   * The precons of the release window that cannot be dealt yet. Each is drawn
   * as a "Coming soon" shell in its release's run, and none is a control.
   */
  upcoming?: readonly UpcomingPrecon[];
  /** Which seat this catalogue is choosing for. 0-3, or null when browsing. */
  forSeat: number | null;
  /** Whose chair, in three words or fewer -- it sits after "Choosing for". */
  forWhom: string;
  /** The deck that seat is already holding, so its card can carry the tick. */
  chosen: string | null;
  onPick: (deckId: string) => void;
  onDossier: (deckId: string) => void;
  onClose: () => void;
  onImported: (result: DeckImportResponse) => void;
  /** Throw an imported deck away. Never called for a shipped deck. */
  onDelete: (deckId: string) => void;
  /**
   * Star or unstar an import, which pins it to the top of Yours. The tile
   * draws `DeckSummary.starred` and nothing else, so the star changes when the
   * server's answer comes back as a new deck list, never on the press.
   */
  onStar: (deckId: string, starred: boolean) => void;
  /**
   * Deck ids somebody at this table has already taken. They get no remove
   * control.
   *
   * A guard rather than a repair, because there is nothing to repair with: the
   * pod API can set a seat's deck but not un-set it. `PodRegistry.start` does
   * catch this -- it re-checks every seat's deck under the lock and refuses with
   * `unknown_deck` -- so what is being prevented is not a crash but a dead end:
   * a seat still showing a deck, a Deal button that keeps saying no, and no way
   * from there to a game. Browsing passes nothing, having no table.
   */
  inUse?: readonly string[];
}

export function DeckCatalog({
  decks,
  upcoming = [],
  forSeat,
  forWhom,
  chosen,
  onPick,
  onDossier,
  onClose,
  onImported,
  onDelete,
  onStar,
  inUse = [],
}: Props) {
  const [filters, setFilters] = useState<CatalogFilters>(EMPTY_FILTERS);
  // Whether the import strip can work: it needs Moxfield, and on the desktop
  // the sidecar's probe is the best word there is on whether that is reachable.
  const config = useAppConfig();

  /* Escape and B, and only while nothing is open over this. The footer has
     advertised `B — Back` since the first draft and nothing was listening for
     it; see `input/useDismiss.ts` for what that cost. */
  const stage = useRef<HTMLElement>(null);
  useDismiss(stage, onClose);

  const shown = useMemo(() => visibleDecks(decks, filters), [decks, filters]);
  const shells = useMemo(() => visibleShells([...upcoming], filters), [upcoming, filters]);
  const groups = useMemo(
    () => groupDecks(shown, filters.source, shells),
    [shown, filters.source, shells],
  );
  const archetypes = useMemo(() => archetypeOptions(decks, filters), [decks, filters]);

  /* The ring lands on a deck. See the header: without this it opens on the ✕,
     which is the way out of the screen the player just asked for. Once, on
     mount -- re-running it as the filter narrows would yank the ring off
     whatever somebody had walked to. */
  // biome-ignore lint/correctness/useExhaustiveDependencies: mount only, by design.
  useLayoutEffect(() => {
    // The first DECK: a release with nothing playable yet is a run of shells,
    // and a shell is not somewhere the ring can stand.
    const first = chosen ?? groups.find((group) => group.decks.length > 0)?.decks[0]?.id;
    if (first) setCursor(`ui:deck-${first}-take`);
  }, []);

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
    <Room
      hue={SHELF_HUE}
      className="shelf"
      floorY="70%"
      washY="34%"
      /* `data-modal-root` is what traps the ring inside the catalogue while it
         is over the pod, and `stopRoot` takes the LAST one in the document so a
         dossier opening over this keeps it. */
    >
      <section
        ref={stage}
        className="shelf__stage"
        role="dialog"
        aria-modal="true"
        data-modal-root
        aria-label="Deck catalogue"
        data-testid="deck-catalog"
      >
        <header className="shelf__bar">
          {/*
            One line where there were two.

            It said "Turn a card face up" over "Choosing your deck" -- a poetic
            restatement of the screen's own picture stacked on the only half of
            it that carries a fact. What is left says which chair this is for,
            because that is the one thing a player cannot see from the grid.
          */}
          <h1 className="room__word shelf__t">
            {forSeat === null ? "Decks" : `Choosing for ${forWhom}`}
          </h1>

          <span className="shelf__gap" />

          <span className="shelf__n tabular" data-testid="deck-count">
            {shown.length}/{decks.length}
          </span>

          <button
            type="button"
            className="key key--mark"
            aria-label="Close"
            data-testid="deck-catalog-close"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        {/*
          THE SEARCH BOX IS A FILTER, AND IT SITS WITH THE OTHER FILTERS.
          
          It was up in the bar between the title and the count, which is where
          the web puts a search box and is the wrong place here for a reason a
          mouse cannot feel: nothing in the strip below it lined up with it, so
          pressing Up from the colour pips was a WALL. The box was reachable
          only by walking to the sort dropdown first and going up from there --
          which nobody would guess, and which reads as the box not being
          reachable at all. One row, and every filter is one press from its
          neighbours.
        */}
        <div className="shelf__filters">
          <label className="shelf__find">
            <span className="shelf__glass" aria-hidden="true">
              ⌕
            </span>
            <input
              className="shelf__findin"
              type="text"
              value={filters.q}
              onChange={(event) => set("q", event.target.value)}
              placeholder="Search"
              spellCheck={false}
              aria-label="Search decks"
              data-testid="deck-search"
            />
          </label>

          <span className="shelf__group">
            {COLOURS.map(([code, name]) => {
              const on = filters.colours.includes(code);
              return (
                <button
                  type="button"
                  key={code}
                  className={on ? "pip-key pip-key--on" : "pip-key"}
                  onClick={() => toggleColour(code)}
                  data-hint={name}
                  aria-label={name}
                  aria-pressed={on}
                  data-testid={`colour-${code}`}
                >
                  <ManaSymbol code={code} title={name} />
                </button>
              );
            })}
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

          {/*
            A BUTTON THAT CYCLES, NOT A `<select>`. A pad's `A` is a synthetic
            `click()`, and a native select opens on nothing but a real pointer
            or key -- so on a Steam Deck the sort could be landed on and never
            changed. Four orders is a short enough loop that pressing through
            them is quicker than opening a list would be anyway.
          */}
          <button
            type="button"
            className="shelf__sort"
            onClick={() => set("sort", nextSort(filters.sort))}
            aria-label={`Sort decks: ${sortName(filters.sort)}`}
            data-hint="Change the order"
            data-testid="deck-sort"
            data-sort={filters.sort}
          >
            <span className="shelf__sortk" aria-hidden="true">
              Sort
            </span>{" "}
            {sortName(filters.sort)}
          </button>

          {/*
            The archetype cycles for the sort's reason, and only through the
            archetypes the other filters leave (`archetypeOptions`). When no
            visible deck names one there is nothing to choose, so there is no
            control -- a button whose every press says "Any" is a dead stop.
          */}
          {archetypes.length > 0 && (
            <button
              type="button"
              className="shelf__sort"
              onClick={() => set("archetype", nextArchetype(filters.archetype, archetypes))}
              aria-label={`Archetype: ${archetypeName(filters.archetype)}`}
              data-hint="Show one archetype"
              data-testid="deck-archetype"
              data-archetype={filters.archetype}
            >
              <span className="shelf__sortk" aria-hidden="true">
                Archetype
              </span>{" "}
              {archetypeName(filters.archetype)}
            </button>
          )}

          <span className="shelf__gap" />

          {/* The one line browsing needs and choosing does not: a pick here
              opens the deck rather than taking it, because there is no chair. */}
          {forSeat === null && (
            <span className="shelf__note" data-testid="catalog-browsing">
              Nothing to take one for yet
            </span>
          )}
        </div>

        <div className="shelf__body">
          {/*
            RUNS, EACH A REGION. A precon is a product, so the shelf runs them
            by release, newest first (`groupDecks`), and each run is a labelled
            region under its own header: a screen reader can jump between them,
            and a pad walking down meets a heading between two sets rather than
            one sweep with no landmarks in it. The header is not a stop; the
            next press lands on the first deck of the next run.
          */}
          {groups.length > 0 ? (
            groups.map((group) => {
              const grid = (
                <div className="shelf__grid">
                  {group.decks.map((deck) => (
                    <DeckPick
                      key={deck.id}
                      deck={deck}
                      selected={deck.id === chosen}
                      onPick={onPick}
                      onDossier={onDossier}
                      onDelete={inUse.includes(deck.id) ? null : onDelete}
                      onStar={onStar}
                    />
                  ))}
                  {group.shells.map((shell) => (
                    <ShellTile key={shell.id} shell={shell} />
                  ))}
                </div>
              );
              if (group.title === null) {
                return <Fragment key={group.key}>{grid}</Fragment>;
              }
              return (
                <div
                  key={group.key}
                  className="shelf__run"
                  role="region"
                  aria-label={group.title}
                  data-testid={`deck-group-${group.key}`}
                >
                  <h2 className="shelf__runh">{group.title}</h2>
                  {grid}
                </div>
              );
            })
          ) : (
            <div className="shelf__empty" data-testid="deck-catalog-empty">
              Nothing matches. Colours are an AND.
            </div>
          )}
        </div>

        <footer className="shelf__foot">
          {/* The same component the front door used to carry, in the
              catalogue's box. See the note at the top of `DeckImport`. */}
          <DeckImport variant="row" onImported={onImported} enabled={canImport(config)} />
        </footer>
      </section>

      <div className="room__hints" aria-hidden="true">
        <span className="hint">
          <Glyph btn="a" />
          <span className="hint__verb">{forSeat === null ? "Read" : "Take"}</span>
        </span>
        <span className="hint">
          <Glyph btn="b" />
          <span className="hint__verb">Back</span>
        </span>
      </div>
    </Room>
  );
}

function DeckPick({
  deck,
  selected,
  onPick,
  onDossier,
  onDelete,
  onStar,
}: {
  deck: DeckSummary;
  selected: boolean;
  onPick: (deckId: string) => void;
  onDossier: (deckId: string) => void;
  /** Null when this deck may not be removed -- see `Props.inUse`. */
  onDelete: ((deckId: string) => void) | null;
  onStar: (deckId: string, starred: boolean) => void;
}) {
  /**
   * Whether this tile is asking "Remove?" rather than offering the ✕.
   *
   * A step rather than nothing, because the glyph sits one deck tile away from
   * the card you press to play the thing -- and what it throws away is an
   * import somebody waited on. A step rather than a `confirm()` dialog, because
   * the catalogue is already a takeover and a second modal over it would be one
   * too many. Local state: one tile mid-question is not a fact the catalogue
   * needs to know.
   */
  const [confirming, setConfirming] = useState(false);

  const take = () => onPick(deck.id);
  return (
    <div
      className={selected ? "tile tile--on" : "tile"}
      data-testid={`deck-${deck.id}`}
      data-selected={selected ? "yes" : "no"}
    >
      <div
        className="tile__card"
        role="button"
        tabIndex={0}
        data-testid={`deck-${deck.id}-take`}
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
          <span className="tile__tick" aria-hidden="true">
            ✓
          </span>
        )}
      </div>
      {/*
        THE STAR SITS BY THE NAME, NOT IN THE META ROW. An import's meta row
        already carries its pips, its simplified count, the `i` and the ✕, and
        a fourth 44px target there runs into the next tile. One toggle with
        `aria-pressed`, which is the only control that sets it: the press sends
        the value it wants rather than "flip", so a second press before the
        answer lands asks for the same thing twice and nothing flickers.
      */}
      {deck.source === "moxfield" ? (
        <div className="tile__head">
          <button
            type="button"
            className={deck.starred ? "tile__star tile__star--on" : "tile__star"}
            aria-pressed={deck.starred}
            aria-label={`Pin ${deck.name} to the top`}
            data-hint={deck.starred ? "Pinned to the top of Yours" : "Pin to the top of Yours"}
            onClick={() => onStar(deck.id, !deck.starred)}
            data-testid={`deck-${deck.id}-star`}
            data-starred={deck.starred ? "yes" : "no"}
          >
            {deck.starred ? "★" : "☆"}
          </button>
          <div className="tile__n">{deck.name}</div>
        </div>
      ) : (
        <div className="tile__n">{deck.name}</div>
      )}
      {/*
        THE CONFIRM REPLACES THE ROW; IT DOES NOT JOIN IT.
        
        Three controls plus the pips do not fit inside a 150px tile, and what
        overflow does here is not clip -- it reaches into the NEXT tile, so
        "Remove?" put its ✕ on top of the neighbour's details glyph and the
        neighbour's glyph took the click. A tile mid-question is asking one
        question and should show one question.
      */}
      <div className="tile__meta">
        {confirming ? (
          <span className="tile__confirm" data-testid={`deck-${deck.id}-remove-confirm`}>
            <span className="tile__q">Remove?</span>
            <button
              type="button"
              className="tile__yes"
              aria-label={`Remove ${deck.name}`}
              onClick={() => onDelete?.(deck.id)}
              data-testid={`deck-${deck.id}-remove-yes`}
            >
              ✓
            </button>
            <button
              type="button"
              className="tile__x"
              aria-label="Keep it"
              onClick={() => setConfirming(false)}
              data-testid={`deck-${deck.id}-remove-no`}
            >
              ✕
            </button>
          </span>
        ) : (
          <>
            <span className="tile__pips">
              {deck.color_identity.map((colour) => (
                <ManaSymbol key={colour} code={colour} />
              ))}
            </span>
            {/* Only when there is something to admit. A shipped deck is native
                all the way through, so this stays off its tiles entirely. */}
            {deck.simplified > 0 && (
              <span className="tile__badge" data-testid={`deck-${deck.id}-simplified`}>
                {deck.simplified}
              </span>
            )}
            {/* Only on the desktop build, and only while some of the deck's art is
                not on the device: offline, those cards would draw plain frames.
                The next launch with a connection finishes it. */}
            {deck.complete === false && (
              <span
                className="tile__badge tile__badge--art"
                role="img"
                aria-label="Some art is not on this device yet"
                data-hint="Some art is not on this device yet"
                data-testid={`deck-${deck.id}-incomplete`}
              >
                art
              </span>
            )}
            <button
              type="button"
              className="tile__i"
              data-hint="Deck details"
              aria-label={`Details for ${deck.name}`}
              onClick={() => onDossier(deck.id)}
              data-testid={`deck-${deck.id}-info`}
            >
              i
            </button>
            {/* Only what somebody imported. A shipped deck has no ✕ at all,
                rather than one that explains itself afterwards. */}
            {deck.source === "moxfield" && onDelete !== null && (
              <button
                type="button"
                className="tile__x"
                data-hint="Remove this deck"
                aria-label={`Remove ${deck.name}`}
                onClick={() => setConfirming(true)}
                data-testid={`deck-${deck.id}-remove`}
              >
                ✕
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * A precon the shelf names but cannot deal yet.
 *
 * NOT A CONTROL. No role, no tabIndex, no handler: there is nothing a press
 * on it could do, so it is text in a card-shaped box, and the ring and Tab
 * both pass over it to the next deck (ADR 0015 counts controls, and this adds
 * none). It says what the product is, who leads it and that it is coming,
 * which is everything the shelf knows about it. The first commander's art is
 * drawn grayed out behind the badge, and an empty `alt`, because the names
 * under it already say whose it is; without a printing it is a plain plate.
 */
function ShellTile({ shell }: { shell: UpcomingPrecon }) {
  const art = shell.commanders.find((commander) => commander.art_url)?.art_url ?? null;
  return (
    <div className="shell" data-testid={`shell-${shell.id}`} data-shell={shell.set_code}>
      <div className="shell__card">
        {art !== null && (
          <img className="shell__art" src={art} alt="" loading="lazy" draggable={false} />
        )}
        <span className="shell__badge">Coming soon</span>
        <span className="shell__cmdrs">
          {shell.commanders.map((commander) => (
            <span key={commander.name} className="shell__cmdr">
              {commander.name}
            </span>
          ))}
        </span>
      </div>
      <div className="shell__n">{shell.product}</div>
    </div>
  );
}

/** Re-exported so a screen can draw one bar without reaching into the dossier. */
export { RatingBar };
