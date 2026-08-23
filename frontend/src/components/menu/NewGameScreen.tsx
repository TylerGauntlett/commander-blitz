/**
 * Title and setup: pick a deck, pick how many opponents, deal.
 *
 * The seed field is kept because a reproducible game is the fastest way to
 * re-examine something that went wrong.
 *
 * The deck list is not fixed any more -- `DeckImport` below the grid adds a
 * Moxfield deck, which then appears as one more tile. That is a deliberate
 * divergence from `mockups/flow/01-front-door.html`, which opens a modal
 * catalogue: the grid's `deck-${id}` hooks are what ~14 e2e specs click, and a
 * modal would cost a re-verify of every one of them for nothing this feature
 * needs. See docs/mockup-fidelity.md.
 */

import { motion } from "motion/react";
import { useState } from "react";
import type { DeckSummary, SeatConfig } from "../../api/types";
import { bouncy, ease } from "../../motion/springs";
import { ManaSymbol } from "../game/ManaSymbol";
import { DeckImport } from "./DeckImport";

const COLOR_NAMES: Record<string, string> = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
};

type AgentName = "heuristic" | "random";

interface Props {
  decks: DeckSummary[];
  loading: boolean;
  error: Error | null;
  onStart: (seats: SeatConfig[], seed?: number) => void;
  starting: boolean;
  /** Re-reads `/api/decks` after an import so the new tile appears. */
  onDecksChanged?: () => void;
}

export function NewGameScreen({
  decks,
  loading,
  error,
  onStart,
  starting,
  onDecksChanged,
}: Props) {
  const [deckId, setDeckId] = useState<string | null>(null);
  const [opponents, setOpponents] = useState(1);
  const [agent, setAgent] = useState<AgentName>("heuristic");
  const [seed, setSeed] = useState("");

  const chosen = deckId ?? decks[0]?.id ?? null;

  const start = () => {
    if (!chosen) return;
    const seats: SeatConfig[] = [{ deck_id: chosen, kind: "human", name: "You" }];
    for (let i = 0; i < opponents; i += 1) {
      // Opponents cycle through the other decks so a pod is not a mirror match.
      const pool = decks.filter((deck) => deck.id !== chosen);
      const deck = pool.length > 0 ? pool[i % pool.length] : decks[0];
      seats.push({
        deck_id: deck.id,
        kind: "ai",
        agent,
        name: `${deck.commander_names[0] ?? deck.name} AI${pool.length > 1 ? ` ${i + 1}` : ""}`,
      });
    }
    const parsed = seed.trim() === "" ? undefined : Number(seed);
    onStart(seats, Number.isFinite(parsed) ? parsed : undefined);
  };

  return (
    <div className="menu" data-testid="new-game">
      <motion.header
        className="menu__head"
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={ease}
      >
        <h1 className="menu__title">Commander Blitz</h1>
        <p className="menu__sub">A Commander table against the engine</p>
      </motion.header>

      {loading && <p className="menu__note">Loading decks&hellip;</p>}
      {error && <p className="menu__error">Could not reach the engine: {error.message}</p>}

      <div className="menu__decks">
        {decks.map((deck, index) => (
          <motion.button
            type="button"
            key={deck.id}
            className={deck.id === chosen ? "deck deck--on" : "deck"}
            data-testid={`deck-${deck.id}`}
            onClick={() => setDeckId(deck.id)}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...bouncy, delay: 0.06 * index }}
            whileHover={{ y: -6, scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <span className="deck__name">
              {deck.name}
              {deck.source === "moxfield" && <span className="deck__badge">Yours</span>}
            </span>
            <span className="deck__cmd">{deck.commander_names.join(" & ")}</span>
            <span className="deck__colors">
              {deck.color_identity.map((color) => (
                <ManaSymbol
                  key={color}
                  code={color}
                  className={`pip--${color}`}
                  data-hint={COLOR_NAMES[color] ?? color}
                />
              ))}
              <span className="deck__count">{deck.card_count} cards</span>
            </span>
            {/* Only when there is something to admit. A precon is all
                hand-written, so this stays off its tiles entirely. */}
            {deck.simplified > 0 && (
              <span className="deck__engine" data-testid={`deck-${deck.id}-simplified`}>
                {deck.simplified} of {deck.card_count} cards simplified
              </span>
            )}
            {deck.notes && <span className="deck__notes">{deck.notes}</span>}
          </motion.button>
        ))}
      </div>

      <DeckImport
        onImported={(imported) => {
          onDecksChanged?.();
          // Select what was just imported: somebody who pasted a link wants to
          // play that deck, and making them find it in the grid afterwards is a
          // step with no decision in it.
          setDeckId(imported.deck.id);
        }}
      />

      <div className="menu__options">
        {/* A button group is not a form control, so these are fieldsets rather
            than labels -- a <label> here would point at nothing. */}
        <fieldset className="field">
          <legend className="field__label">Opponents</legend>
          <div className="segmented">
            {[1, 2, 3].map((count) => (
              <button
                type="button"
                key={count}
                className={
                  count === opponents ? "segmented__btn segmented__btn--on" : "segmented__btn"
                }
                onClick={() => setOpponents(count)}
                data-testid={`opponents-${count}`}
              >
                {count}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="field">
          <legend className="field__label">AI</legend>
          <div className="segmented">
            {(["heuristic", "random"] as AgentName[]).map((option) => (
              <button
                type="button"
                key={option}
                className={
                  option === agent ? "segmented__btn segmented__btn--on" : "segmented__btn"
                }
                onClick={() => setAgent(option)}
                data-hint={
                  option === "heuristic"
                    ? "Plays to a real evaluation: removal, blocks, curve"
                    : "Uniformly random legal actions"
                }
              >
                {option}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="field">
          <span className="field__label">Seed</span>
          <input
            className="field__input"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            placeholder="random"
            inputMode="numeric"
          />
        </label>
      </div>

      <motion.button
        type="button"
        className="btn btn--big"
        onClick={start}
        disabled={!chosen || starting}
        data-testid="start-game"
        whileHover={{ y: -3, scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        transition={bouncy}
      >
        {starting ? "Shuffling…" : "Play"}
      </motion.button>
    </div>
  );
}
