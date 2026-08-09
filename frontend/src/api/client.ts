/** Thin fetch wrapper around the engine's HTTP API. */

import type {
  CardResponse,
  DeckImportResponse,
  DeckSummary,
  GameCreated,
  ImagesResponse,
  SeatConfig,
  StateResponse,
} from "./types";

const BASE = "/api";

/**
 * A failed request, with the server's machine-readable code when there is one.
 *
 * Deck import is the reason this exists: "that deck is private" and "there is no
 * such deck" want different copy, and switching on a translated sentence is how
 * that breaks the first time somebody rewords it.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    let code: string | undefined;
    try {
      const body = await response.json();
      // FastAPI wraps whatever the route raised. A plain string is the usual
      // case; an object is a route that wanted to say more than one thing.
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail && typeof body.detail === "object") {
        detail = body.detail.detail ?? detail;
        code = body.detail.code;
      }
    } catch {
      // Non-JSON error body; the status text is the best we have.
    }
    throw new ApiError(response.status, `${response.status}: ${detail}`, code);
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

  /**
   * Import a public Moxfield deck.
   *
   * `dryRun` reports what would happen without writing anything, so the coverage
   * panel can be shown before the deck is committed to disk. On a real import
   * the deck becomes a `deck_id` like any other and `newGame` takes it unchanged.
   */
  importDeck: (url: string, dryRun = false) =>
    request<DeckImportResponse>("/decks/import", {
      method: "POST",
      body: JSON.stringify({ url, dry_run: dryRun }),
    }),

  deleteDeck: (deckId: string) => request<void>(`/decks/${deckId}`, { method: "DELETE" }),

  card: (cardId: string) => request<CardResponse>(`/cards/${cardId}`),

  /**
   * Card art locations, in one response.
   *
   * Static for the life of the server process, so this is fetched once and
   * cached forever rather than riding along on each state poll -- the AI pump
   * polls several times a second, and the image is a function of the immutable
   * `card_id`.
   *
   * `gameId` narrows it to the cards that game can actually contain. Without it
   * the response carries every card the server knows, which imported decks make
   * unbounded.
   */
  images: (gameId?: string) =>
    request<ImagesResponse>(
      gameId ? `/images?game_id=${encodeURIComponent(gameId)}` : "/images",
    ),

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
