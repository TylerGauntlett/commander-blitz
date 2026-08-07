/** Thin fetch wrapper around the engine's HTTP API. */

import type { DeckSummary, GameCreated, SeatConfig, StateResponse } from "./types";

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

export const api = {
  decks: () => request<DeckSummary[]>("/decks"),

  newGame: (seats: SeatConfig[], seed?: number) =>
    request<GameCreated>("/games", {
      method: "POST",
      body: JSON.stringify({ seats, seed }),
    }),

  state: (gameId: string, seat: number, since = 0) =>
    request<StateResponse>(`/games/${gameId}/state?seat=${seat}&since=${since}`),

  applyAction: (gameId: string, seat: number, actionId: string) =>
    request<StateResponse>(`/games/${gameId}/actions`, {
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
  ) =>
    request<StateResponse>(`/games/${gameId}/declare`, {
      method: "POST",
      body: JSON.stringify({ seat, kind, pairs }),
    }),

  undo: (gameId: string, seat: number) =>
    request<StateResponse>(`/games/${gameId}/undo`, {
      method: "POST",
      body: JSON.stringify({ seat }),
    }),

  deleteGame: (gameId: string) => request<void>(`/games/${gameId}`, { method: "DELETE" }),
};
