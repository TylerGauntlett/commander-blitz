/**
 * Paste a Moxfield link, get a deck.
 *
 * Following the flow round's shared state (`docs/design-record.md#flow`)'s `CUSTOM`, whose comment is the design
 * brief: *"The error state matters more than the happy path, because it is the
 * state the real feature will spend its life in."* So this component is mostly
 * error states, and the one success state leads with what the import could not
 * do rather than with congratulations.
 *
 * The honesty requirement is concrete. The engine plays ~149 hand-written cards;
 * everything else is generated with its non-keyword rules text inert. A player
 * who is not told that will spend a game wondering why their removal spell does
 * nothing. So the headline is "N playable / N simplified", every simplified card
 * can be expanded to see exactly what changed, and the mana base gets its own
 * line because a deck that looks like 37 lands and behaves like 34 is the single
 * most confusing thing an import can produce.
 *
 * Two chromes, one machine. `panel` is the standalone block; `row` is the
 * catalogue's footer strip, which is the same interaction in a different box.
 * The four-state machine and `messageFor` are shared rather than reimplemented:
 * the error mapping is the part of this component with real knowledge in it,
 * and a second copy would be a second copy to get out of date.
 */

import { motion } from "motion/react";
import { useState } from "react";
import { ApiError, api } from "../../api/client";
import type { DeckImportResponse } from "../../api/types";
import { ease } from "../../motion/springs";

/**
 * Checked before the request, so a paste that is obviously not a deck link costs
 * nothing. The server applies the same rule and returns `bad_url`; this is the
 * fast path, not the authority.
 */
const LOOKS_LIKE_MOXFIELD = /^https?:\/\/(www\.)?moxfield\.com\/decks\/\S+/i;

const COPY = {
  badUrl: "That is not a Moxfield deck link.",
  private: "That deck is private. Set it to public and try again.",
  notFound: "No deck with that link.",
  unreachable: "Could not reach Moxfield. Check your connection and try again.",
};

interface Props {
  onImported: (result: DeckImportResponse) => void;
  /** `row` is the deck catalogue's footer strip; `panel` is the standalone block. */
  variant?: "panel" | "row";
  /**
   * False on the desktop with no connection: the field and the button are
   * disabled and the hint says why, because Moxfield is the one thing in the
   * game that cannot be reached from a server on the device.
   */
  enabled?: boolean;
}

type Status = "idle" | "fetching" | "error" | "ready";

export function DeckImport({ onImported, variant = "panel", enabled = true }: Props) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeckImportResponse | null>(null);
  const [expanded, setExpanded] = useState(false);

  const run = async () => {
    const trimmed = url.trim();
    if (!LOOKS_LIKE_MOXFIELD.test(trimmed)) {
      setStatus("error");
      setError(COPY.badUrl);
      return;
    }
    setStatus("fetching");
    setError(null);
    try {
      const imported = await api.importDeck(trimmed);
      setResult(imported);
      setStatus("ready");
      setExpanded(false);
      onImported(imported);
    } catch (caught) {
      setStatus("error");
      setError(messageFor(caught));
    }
  };

  const simplified = result?.cards.filter((card) => card.origin === "partial") ?? [];
  // Not `lands - lands_producing_mana`: a fetchland makes no mana and is a
  // perfectly good land, so that subtraction would keep flagging cards that
  // work. What is worth a warning is a land with no abilities at all.
  const inertLands = result?.lands_inert ?? 0;

  const row = variant === "row";

  return (
    <section className={row ? "import import--row" : "import"} data-testid="deck-import">
      {row ? (
        <span className="import__label">Import</span>
      ) : (
        <>
          <h2 className="import__title">Or bring your own</h2>
          <p className="import__hint">Paste a public Moxfield deck link.</p>
        </>
      )}

      <div className="import__row">
        <input
          className="field__input import__input"
          value={url}
          onChange={(event) => {
            setUrl(event.target.value);
            if (status === "error") setStatus("idle");
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") run();
          }}
          placeholder="https://moxfield.com/decks/..."
          spellCheck={false}
          disabled={!enabled}
          data-testid="import-url"
          aria-label="Moxfield deck link"
        />
        <button
          type="button"
          className="btn"
          onClick={run}
          disabled={!enabled || status === "fetching" || url.trim() === ""}
          data-testid="import-go"
        >
          {status === "fetching" ? "Reading the list…" : row ? "Fetch" : "Import"}
        </button>
        {/* In the row the hint is beside the field rather than above it: the
            footer is one line tall and a paragraph over it would double that. */}
        {!enabled ? (
          <span className="import__hint import__hint--inline" data-testid="import-offline">
            Importing a Moxfield deck needs a connection.
          </span>
        ) : (
          row &&
          status === "idle" && (
            <span className="import__hint import__hint--inline">
              Paste a public Moxfield deck link.
            </span>
          )
        )}
      </div>

      {status === "error" && error && (
        <motion.p
          className="menu__error"
          data-testid="import-error"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={ease}
        >
          {error}
        </motion.p>
      )}

      {status === "ready" && result && (
        <motion.div
          className="import__report"
          data-testid="import-coverage"
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={ease}
        >
          <p className="import__headline">
            <strong>{result.deck.name}</strong>
            {" — "}
            <span data-testid="import-playable">{result.playable} playable</span>
            {" · "}
            <span data-testid="import-simplified">{result.simplified} simplified</span>
          </p>

          {/* Only when it differs. "37 lands, none of them inert" is noise. */}
          {inertLands > 0 && (
            <p className="import__mana" data-testid="import-mana">
              {result.lands} lands, but {inertLands} of them do nothing here — they are on the
              board with the right name and cost, and no ability the engine can run.
            </p>
          )}

          {result.problems.map((problem) => (
            <p className="import__problem" key={problem}>
              {problem}
            </p>
          ))}

          {simplified.length > 0 && (
            <>
              <button
                type="button"
                className="import__toggle"
                onClick={() => setExpanded((open) => !open)}
                data-testid="import-toggle"
                aria-expanded={expanded}
              >
                {expanded ? "Hide" : "Show"} the {simplified.length} simplified cards
              </button>
              {expanded && (
                <ul className="import__list">
                  {simplified.map((card) => (
                    <li className="import__card" key={card.card_id}>
                      <span className="import__card-name">{card.name}</span>
                      <ul className="import__notes">
                        {card.notes.map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </motion.div>
      )}
    </section>
  );
}

function messageFor(caught: unknown): string {
  if (caught instanceof ApiError) {
    // Switch on the code, never on the sentence: the sentence is copy and will
    // be reworded, the code is a contract.
    switch (caught.code) {
      case "bad_url":
        return COPY.badUrl;
      case "private":
        return COPY.private;
      case "not_found":
        return COPY.notFound;
      case "unreachable":
        return COPY.unreachable;
      default:
        // `bad_size`, `not_commander`, `unknown_cards`, `illegal`: the server's
        // own sentence names the deck or the card, which is more use than
        // anything this component could write.
        return caught.message.replace(/^\d+:\s*/, "");
    }
  }
  return caught instanceof Error ? caught.message : "Something went wrong.";
}
