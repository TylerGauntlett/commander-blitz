/** Thin fetch wrapper around the engine's HTTP API. */

import { libraryId } from "../state/library";
import type {
  AppConfig,
  CardResponse,
  DeckCompletion,
  DeckDetail,
  DeckImportResponse,
  DeckSummary,
  GameCreated,
  ImagesResponse,
  PodCredentials,
  PodView,
  SeatAdminAction,
  SeatConfig,
  StateResponse,
  UpcomingPrecon,
} from "./types";

const BASE = "/api";

/**
 * The pod token, set once and sent on every request thereafter.
 *
 * A module-level slot rather than a parameter on every call: `request` already
 * builds the headers in one place, so putting it here means no call site had to
 * change and no future one can forget. It is scoped to the pod that issued it,
 * so it is cleared on leaving.
 *
 * Not a cookie: CORS here is `allow_credentials=false` by design, so a cookie
 * would not be sent cross-origin from the Vite dev server at all.
 */
let playerToken: string | null = null;

export function setPlayerToken(token: string | null): void {
  playerToken = token;
}

export function getPlayerToken(): string | null {
  return playerToken;
}

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
  /**
   * The whole error detail object, when there was one.
   *
   * `already_started` carries a `game_id`: a player who reloads into a pod that
   * has already dealt is not an error case to show, it is somebody who should
   * be sent to the table. Throwing away the id would turn that into a dead end.
   */
  readonly detail?: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    code?: string,
    detail?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const library = libraryId();
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(playerToken ? { "X-Player-Token": playerToken } : {}),
      // Which library is asking. The pod token above says which *seat* you are
      // at one table; this says which decks are yours across every visit.
      ...(library ? { "X-Library-Id": library } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    let code: string | undefined;
    let extra: Record<string, unknown> | undefined;
    try {
      const body = await response.json();
      // FastAPI wraps whatever the route raised. A plain string is the usual
      // case; an object is a route that wanted to say more than one thing.
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail && typeof body.detail === "object") {
        detail = body.detail.detail ?? detail;
        code = body.detail.code;
        extra = body.detail;
      }
    } catch {
      // Non-JSON error body; the status text is the best we have.
    }
    throw new ApiError(response.status, `${response.status}: ${detail}`, code, extra);
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
  /** Which server this is. See `state/useAppConfig`. */
  config: () => request<AppConfig>("/config"),

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

  /**
   * The precons of the release window that are not playable yet, newest
   * first. The shelf draws them as "Coming soon" shells beside the shipped
   * ones; none of them can be taken.
   */
  upcomingPrecons: () => request<UpcomingPrecon[]>("/precons/upcoming"),

  /**
   * Pin an import to the top of Yours, or unpin it. The answer is the deck as
   * the server now holds it, which is what the tile draws; the client never
   * flips the star on its own.
   */
  starDeck: (deckId: string, starred: boolean) =>
    request<DeckSummary>(`/decks/${deckId}/star`, {
      method: "POST",
      body: JSON.stringify({ starred }),
    }),

  /**
   * Finish every imported deck whose art is not all on this machine. The
   * desktop door calls it before drawing when the site answers; the site
   * answers with an empty list.
   */
  completeDecks: () => request<DeckCompletion[]>("/decks/complete", { method: "POST" }),

  /** One deck with the dossier's essays, curve and swap note. */
  deck: (deckId: string) => request<DeckDetail>(`/decks/${deckId}`),

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

  /**
   * This seat's view of the game.
   *
   * `seat` may be null: with a pod token the server resolves it, which is how a
   * client that arrived from a lobby learns which table seat it got. With
   * `sinceVersion` set the request blocks until somebody else moves -- that is
   * how the second human hears about the first one's turn.
   *
   * `since` is the `event_cursor` of the last response the caller absorbed, so
   * the answer carries only the events it has not yet seen. `signal` lets a
   * blocked poll be abandoned when the component that issued it goes away.
   */
  state: (
    gameId: string,
    seat: number | null,
    since = 0,
    sinceVersion?: number,
    timeout?: number,
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams({ since: String(since) });
    if (seat !== null) params.set("seat", String(seat));
    if (sinceVersion !== undefined) params.set("since_version", String(sinceVersion));
    if (timeout !== undefined) params.set("timeout", String(timeout));
    return request<StateResponse>(`/games/${gameId}/state?${params}`, { signal });
  },

  /**
   * Take one of the offered actions.
   *
   * `version` is the `version` of the response the action list came from.
   * Action ids are positional (`a1-play_land` is "the second thing offered"),
   * so they only mean something against that list; with it, the server can
   * answer a click on a list it has since replaced -- a double click, a drop
   * followed by its own click -- with a 409 `stale_action` instead of applying
   * whatever now sits at that index. Omitted, the server falls back to a
   * guess from the id's shape.
   */
  applyAction: (
    gameId: string,
    seat: number,
    actionId: string,
    aiSteps?: number,
    version?: number,
  ) =>
    request<StateResponse>(`/games/${gameId}/actions${stepQuery(aiSteps)}`, {
      method: "POST",
      body: JSON.stringify({ seat, action_id: actionId, version }),
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

  /**
   * Answer a pick-several decision with the whole set at once. `choices` are
   * ordinals into `pending.options`; the server loops the picks and adds Done,
   * so the dialog can toggle cards freely and commit once.
   */
  choose: (gameId: string, seat: number, choices: number[], aiSteps?: number) =>
    request<StateResponse>(`/games/${gameId}/choose${stepQuery(aiSteps)}`, {
      method: "POST",
      body: JSON.stringify({ seat, choices }),
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

  /**
   * Tap your own lands, or let the payment solver do it.
   *
   * `full_control` rides along because `/options` carries the whole per-seat
   * settings block and its `full_control` is required — sending this alone
   * would silently switch the other setting off.
   */
  setManualMana: (gameId: string, seat: number, fullControl: boolean, manualMana: boolean) =>
    request<StateResponse>(`/games/${gameId}/options`, {
      method: "POST",
      body: JSON.stringify({ seat, full_control: fullControl, manual_mana: manualMana }),
    }),

  undo: (gameId: string, seat: number) =>
    request<StateResponse>(`/games/${gameId}/undo`, {
      method: "POST",
      body: JSON.stringify({ seat }),
    }),

  deleteGame: (gameId: string) => request<void>(`/games/${gameId}`, { method: "DELETE" }),

  /* ---------------------------------------------------------------- */
  /* Pods                                                              */
  /* ---------------------------------------------------------------- */

  /**
   * Open a pod and take seat 0. The token comes back exactly once, here.
   *
   * `name` is omitted rather than defaulted: the front door does not ask for
   * one, and the server names an unnamed chair after its seat. A default here
   * would be a second place that decides what to call you.
   */
  createPod: (name?: string, deckId?: string | null, seed?: number) =>
    request<PodCredentials>("/pods", {
      method: "POST",
      body: JSON.stringify({
        ...(name ? { name } : {}),
        deck_id: deckId ?? null,
        seed: seed ?? null,
      }),
    }),

  /**
   * Take a chair in somebody else's pod.
   *
   * Sending a token you already hold returns the seat you had rather than a
   * second one -- which is the whole reconnect story, since `request` attaches
   * the stored token automatically.
   */
  joinPod: (code: string, name?: string) =>
    request<PodCredentials>(`/pods/${encodeURIComponent(code)}/join`, {
      method: "POST",
      body: JSON.stringify(name ? { name } : {}),
    }),

  /**
   * The pod, optionally waiting for it to change.
   *
   * `sinceVersion` of 0 returns immediately -- the first fetch. Anything else
   * blocks server-side until the version moves or the poll ages out, and a
   * timed-out poll is a 200 with the current view, not an error.
   */
  pod: (code: string, sinceVersion = 0, timeout?: number) => {
    const params = new URLSearchParams({ since: String(sinceVersion) });
    if (timeout !== undefined) params.set("timeout", String(timeout));
    return request<PodView>(`/pods/${encodeURIComponent(code)}?${params}`);
  },

  /** Your own chair: say who you are, pick a deck, lock in, unlock. */
  updateSeat: (code: string, body: { deck_id?: string; locked?: boolean; name?: string }) =>
    request<PodView>(`/pods/${encodeURIComponent(code)}/seat`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /** A chair that is not yours. Host only, and never another player's. */
  adminSeat: (
    code: string,
    index: number,
    body: { action: SeatAdminAction; deck_id?: string; agent?: string },
  ) =>
    request<PodView>(`/pods/${encodeURIComponent(code)}/seats/${index}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /**
   * Deal the pod.
   *
   * The seed rides on the deal rather than on the pod: it is the moment the
   * host actually types one, and a seed chosen at create time would be picked
   * before anybody knows what game they are about to play.
   */
  startPod: (code: string, seed?: number) =>
    request<PodView>(`/pods/${encodeURIComponent(code)}/start`, {
      method: "POST",
      body: JSON.stringify({ seed: seed ?? null }),
    }),

  leavePod: (code: string) =>
    request<void>(`/pods/${encodeURIComponent(code)}/leave`, { method: "POST" }),
};
