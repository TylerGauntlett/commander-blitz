/** Thin fetch wrapper around the engine's HTTP API. */

import type {
  CardResponse,
  DeckSummary,
  GameCreated,
  SeatConfig,
  StateResponse,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Non-JSON error body; the status text is the best we have.
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * `?ai_steps=1` makes the server hand control back after a *single* AI
 * decision instead of playing every opponent's whole turn and returning the
 * finished position. That is what lets the client animate their turns.
 */
function stepQuery(aiSteps?: number): string {
  return aiSteps === undefined ? "" : `?ai_steps=${aiSteps}`;
}

export const api = {
  decks: () => request<DeckSummary[]>("/decks"),

  card: (cardId: string) => request<CardResponse>(`/cards/${cardId}`),

  newGame: (seats: SeatConfig[], seed?: number) =>
    request<GameCreated>("/games", {
      method: "POST",
      body: JSON.stringify({ seats, seed }),
    }),

  state: (gameId: string, seat: number, since = 0) =>
    request<StateResponse>(`/games/${gameId}/state?seat=${seat}&since=${since}`),

  applyAction: (gameId: string, seat: number, actionId: string, aiSteps?: number) =>
    request<StateResponse>(`/games/${gameId}/actions${stepQuery(aiSteps)}`, {
      method: "POST",
      body: JSON.stringify({ seat, action_id: actionId }),
    }),

  /**
   * Submit a whole attack or block at once. The engine declares combat
   * incrementally; the server loops the increments so the UI can stay
   * "select everything, then confirm".
   */
  declare: (
    gameId: string,
    seat: number,
    kind: "attackers" | "blockers",
    pairs: [number, number][],
    aiSteps?: number,
  ) =>
    request<StateResponse>(`/games/${gameId}/declare${stepQuery(aiSteps)}`, {
      method: "POST",
      body: JSON.stringify({ seat, kind, pairs }),
    }),

  /** Pump the opponents forward. With `aiSteps` set, one decision at a time. */
  advance: (gameId: string, seat: number, aiSteps?: number) =>
    request<StateResponse>(`/games/${gameId}/advance${stepQuery(aiSteps)}`, {
      method: "POST",
      body: JSON.stringify({ seat }),
    }),

  /**
   * Stop at every priority window, or only the meaningful ones.
   *
   * The engine auto-passes windows with nothing to respond to; a player who
   * wants an opponent's end step back asks for full control here.
   */
  setFullControl: (gameId: string, seat: number, fullControl: boolean) =>
    request<StateResponse>(`/games/${gameId}/options`, {
      method: "POST",
      body: JSON.stringify({ seat, full_control: fullControl }),
    }),

  undo: (gameId: string, seat: number) =>
    request<StateResponse>(`/games/${gameId}/undo`, {
      method: "POST",
      body: JSON.stringify({ seat }),
    }),

  deleteGame: (gameId: string) => request<void>(`/games/${gameId}`, { method: "DELETE" }),
};
