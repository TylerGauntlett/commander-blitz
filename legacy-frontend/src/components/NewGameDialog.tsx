/** Deck and seat selection for a new game. */

import { useState } from "react";
import type { SeatConfig } from "../api/types";
import { useDecks } from "../state/useGame";

interface Props {
  busy: boolean;
  onStart: (seats: SeatConfig[], seed?: number) => void;
}

export function NewGameDialog({ busy, onStart }: Props) {
  const decks = useDecks();
  const [playerCount, setPlayerCount] = useState(2);
  const [yourDeck, setYourDeck] = useState("aesi");
  const [agent, setAgent] = useState<"heuristic" | "random">("heuristic");
  const [seed, setSeed] = useState("");

  if (decks.isLoading) return <div className="dialog">Loading decks...</div>;
  if (decks.error) {
    return (
      <div className="dialog dialog--error">
        <h1>Cannot reach the engine</h1>
        <p>{(decks.error as Error).message}</p>
        <p className="dialog__hint">
          Start it with: <code>uvicorn automtg.server.app:get_app --factory --reload</code>
        </p>
      </div>
    );
  }

  const available = decks.data ?? [];
  const otherDeck = available.find((deck) => deck.id !== yourDeck)?.id ?? yourDeck;

  const start = () => {
    const seats: SeatConfig[] = [{ deck_id: yourDeck, kind: "human", name: "You" }];
    for (let i = 1; i < playerCount; i += 1) {
      seats.push({
        deck_id: i % 2 === 1 ? otherDeck : yourDeck,
        kind: "ai",
        agent,
        name: `AI ${i}`,
      });
    }
    onStart(seats, seed.trim() === "" ? undefined : Number(seed));
  };

  return (
    <div className="dialog">
      <h1>Auto MTG</h1>
      <p className="dialog__subtitle">Commander playtest</p>

      <label className="field">
        <span>Your deck</span>
        <select value={yourDeck} onChange={(event) => setYourDeck(event.target.value)}>
          {available.map((deck) => (
            <option key={deck.id} value={deck.id}>
              {deck.name} ({deck.color_identity.join("") || "C"})
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Players</span>
        <select
          value={playerCount}
          onChange={(event) => setPlayerCount(Number(event.target.value))}
        >
          <option value={2}>2 (duel)</option>
          <option value={3}>3</option>
          <option value={4}>4 (pod)</option>
        </select>
      </label>

      <label className="field">
        <span>Opponents</span>
        <select
          value={agent}
          onChange={(event) => setAgent(event.target.value as "heuristic" | "random")}
        >
          <option value="heuristic">Heuristic (plays properly)</option>
          <option value="random">Random (for testing)</option>
        </select>
      </label>

      <label className="field">
        <span>Seed</span>
        <input
          value={seed}
          placeholder="random"
          onChange={(event) => setSeed(event.target.value)}
        />
      </label>

      <button type="button" className="action-button" disabled={busy} onClick={start}>
        {busy ? "Dealing..." : "Start game"}
      </button>

      <div className="dialog__decks">
        {available.map((deck) => (
          <div className="dialog__deck" key={deck.id}>
            <strong>{deck.name}</strong>
            <span>{deck.commander_names.join(", ")}</span>
            <p>{deck.notes}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
