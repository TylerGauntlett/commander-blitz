/**
 * The listener: `useGame`'s long poll, characterised against a blocking fetch.
 *
 * Every request the hook makes is parked in a queue and answered by hand, one
 * at a time, because a stub that answered instantly would spin the loop as
 * fast as the event loop allows (docs/testing.md). A poll that hangs is exactly
 * a poll waiting for news.
 *
 * The four facts this file guards, each of which was false once:
 *
 *   1. A poll that times out is followed by another. The old effect ran once
 *      and never again, so an opponent who thought for longer than the poll
 *      ceiling left this tab deaf until it was reloaded.
 *   2. A poll carries the event cursor of the last response absorbed, and only
 *      what is new is logged and narrated. The old poll sent `since=0`, got
 *      the whole game back, and replayed it -- most visibly after a reload.
 *   3. The loop stops when it becomes our decision, retries a failed poll
 *      after a pause, gives up on a game that is gone, and abandons the
 *      request in flight when the table unmounts.
 *   4. With several people at a table and an AI on the clock, exactly one of
 *      them pumps and the rest listen -- and a listener whose poll times out
 *      takes the pump over.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GameEvent, StateResponse } from "../src/api/types";
import { beatsFor } from "../src/logic/events";
import { useUiStore } from "../src/state/uiStore";
import { freshEvents, type GameSession, useGame, waitingOnFrom } from "../src/state/useGame";
import { action, gameEvent, gameView, pending, player, stateResponse } from "./fixtures";

interface Parked {
  url: string;
  method: string;
  body: unknown;
  signal: AbortSignal | null | undefined;
  answer: (body: unknown, status?: number) => void;
  fail: (error: Error) => void;
}

/** Every request the hook has made and not yet been answered. */
let parked: Parked[];

beforeEach(() => {
  parked = [];
  useUiStore.setState({ speed: "instant", error: null });
  vi.stubGlobal(
    "fetch",
    (url: string, init: RequestInit = {}) =>
      new Promise<Response>((resolve, reject) => {
        init.signal?.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        );
        parked.push({
          url: String(url),
          method: init.method ?? "GET",
          body: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
          signal: init.signal,
          answer: (body, status = 200) =>
            resolve(
              new Response(JSON.stringify(body), {
                status,
                headers: { "Content-Type": "application/json" },
              }),
            ),
          fail: reject,
        });
      }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

let latest: ReturnType<typeof useGame>;

function Probe({ session }: { session: GameSession }) {
  latest = useGame(session);
  return null;
}

function mount(session: GameSession = { gameId: "g1", seat: 1 }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Probe session={session} />
    </QueryClientProvider>,
  );
}

/**
 * Let everything in flight land: the answered fetch, React Query's notify
 * batch (a zero timer), and the effects the resulting render schedules.
 *
 * Two passes, deliberately. Inside an async `act` React holds passive effects
 * until the scope closes, so a timer an effect arms -- the pump's 60 ms delay
 * -- is only armed once the first pass is over. The second pass is where it
 * fires.
 */
async function settle(ms = 0) {
  const wait = async (delay: number) => {
    if (vi.isFakeTimers()) {
      await vi.advanceTimersByTimeAsync(delay);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, delay));
    await new Promise((resolve) => setTimeout(resolve, 0));
  };
  await act(() => wait(0));
  await act(() => wait(ms));
}

/** The one request the hook is blocked on. */
function next(): Parked {
  const request = parked.shift();
  if (!request) throw new Error("the hook has nothing in flight");
  return request;
}

const HOST = player({ pid: 0, name: "Host" });
const GUEST = player({ pid: 1, name: "Guest", deck_id: "edgar" });

/** Twelve events of history: shuffles and opening hands, already rendered. */
const HISTORY: GameEvent[] = Array.from({ length: 12 }, (_, index) =>
  gameEvent({ type: "draw", step: index }),
);

/** Seat 1, with seat 0 on the clock. What a guest sees while the host thinks. */
function waiting(overrides: Partial<StateResponse> = {}): StateResponse {
  return stateResponse({
    state: gameView({
      seat: 1,
      players: [HOST, GUEST],
      pending: pending({ player: 0 }),
    }),
    your_seat: 1,
    human_seats: [0, 1],
    version: 3,
    event_cursor: 12,
    events: HISTORY,
    ...overrides,
  });
}

const POLL = "/api/games/g1/state?since=12&seat=1&since_version=3&timeout=25";

/** Mount as the guest and answer the opening fetch, leaving the first poll parked. */
async function guestAtTable(session?: GameSession) {
  const view = mount(session);
  await settle();
  next().answer(waiting());
  await settle();
  return view;
}

describe("the listener", () => {
  it("issues another poll after one that times out", async () => {
    await guestAtTable();

    const first = next();
    expect(first.url).toBe(POLL);
    // A timeout is a 200 with the same version and the same history.
    first.answer(waiting());
    await settle();

    expect(parked.map((request) => request.url)).toEqual([POLL]);
    expect(latest.events).toHaveLength(12);
    expect(latest.waitingForPlayer).toBe(true);
  });

  it("carries the event cursor forward and appends only what is new", async () => {
    await guestAtTable();

    next().answer(
      waiting({
        version: 4,
        event_cursor: 14,
        events: [gameEvent({ step: 12 }), gameEvent({ step: 13 })],
      }),
    );
    await settle();

    expect(latest.events).toHaveLength(14);
    expect(next().url).toBe("/api/games/g1/state?since=14&seat=1&since_version=4&timeout=25");
  });

  it("trims a response that overlaps what it already holds", async () => {
    await guestAtTable();

    // Four events ending at cursor 14: the first two are 10 and 11, which the
    // opening fetch already delivered.
    next().answer(
      waiting({
        version: 4,
        event_cursor: 14,
        events: [10, 11, 12, 13].map((step) => gameEvent({ step })),
      }),
    );
    await settle();

    expect(latest.events).toHaveLength(14);
    expect(latest.events.slice(12).map((event) => event.step)).toEqual([12, 13]);
  });

  it("narrates the new events and nothing it has already shown", async () => {
    useUiStore.setState({ speed: "fast" });
    await guestAtTable();

    // A cast is one beat each; damage would collapse into a single burst.
    const cast = (step: number) =>
      gameEvent({ type: "spell_cast", step, data: { card: "sol_ring" } });
    const batch = [10, 11, 12, 13].map(cast);
    next().answer(waiting({ version: 4, event_cursor: 14, events: batch }));
    await settle();

    const fresh = beatsFor(batch.slice(2), ["Host", "Guest"], undefined, 1);
    const whole = beatsFor(batch, ["Host", "Guest"], undefined, 1);
    expect(fresh.length).toBeGreaterThan(0);
    expect(whole.length).toBeGreaterThan(fresh.length);
    expect(latest.narration.busy).toBe(true);
    expect(latest.narration.queued + 1).toBe(fresh.length);
  });

  it("stops once it is our decision", async () => {
    await guestAtTable();

    next().answer(
      waiting({
        version: 4,
        state: gameView({ seat: 1, players: [HOST, GUEST], pending: pending({ player: 1 }) }),
        actions: [action()],
      }),
    );
    await settle();

    expect(latest.actions).toHaveLength(1);
    expect(latest.waitingForPlayer).toBe(false);
    expect(parked).toHaveLength(0);
  });

  it("retries a failed poll after a pause, but not a game that is gone", async () => {
    vi.useFakeTimers();
    await guestAtTable();

    next().fail(new TypeError("Failed to fetch"));
    await settle();
    expect(parked).toHaveLength(0);
    expect(useUiStore.getState().error).toBe("Failed to fetch");

    await settle(2000);
    expect(parked.map((request) => request.url)).toEqual([POLL]);

    // The server restarted: the game id means nothing to it now.
    next().answer({ detail: "no game g1" }, 404);
    await settle(5000);
    expect(parked).toHaveLength(0);
    expect(useUiStore.getState().error).toContain("404");
  });

  it("abandons the poll in flight when the table unmounts", async () => {
    const view = await guestAtTable();
    const poll = next();
    expect(poll.signal?.aborted).toBe(false);

    view.unmount();
    expect(poll.signal?.aborted).toBe(true);
    await settle();
    expect(parked).toHaveLength(0);
  });
});

describe("with an AI on the clock", () => {
  const CPU = player({ pid: 2, name: "CPU", deck_id: "zurgo", hand: null });

  /** Seat 2 is deciding; seats 0 and 1 are people. */
  function aiTurn(seat: number): StateResponse {
    return stateResponse({
      state: gameView({ seat, players: [HOST, GUEST, CPU], pending: pending({ player: 2 }) }),
      your_seat: seat,
      human_seats: [0, 1],
      version: 3,
      event_cursor: 12,
      events: HISTORY,
    });
  }

  it("the lowest human seat pumps", async () => {
    mount({ gameId: "g1", seat: 0 });
    await settle();
    next().answer(aiTurn(0));
    await settle(100);

    expect(latest.aiThinking).toBe(true);
    expect(parked.map((request) => `${request.method} ${request.url}`)).toEqual([
      "POST /api/games/g1/advance?ai_steps=1",
    ]);
  });

  it("everybody else listens", async () => {
    mount({ gameId: "g1", seat: 1 });
    await settle();
    next().answer(aiTurn(1));
    await settle(100);

    expect(latest.aiThinking).toBe(true);
    expect(parked.map((request) => `${request.method} ${request.url}`)).toEqual([
      `GET ${POLL}`,
    ]);
  });

  it("a listener whose poll times out takes the pump over", async () => {
    mount({ gameId: "g1", seat: 1 });
    await settle();
    next().answer(aiTurn(1));
    await settle();

    // Nobody moved the AI in a whole poll: the pumper's tab is gone.
    next().answer(aiTurn(1));
    await settle(100);

    expect(parked.map((request) => `${request.method} ${request.url}`)).toEqual([
      "POST /api/games/g1/advance?ai_steps=1",
    ]);
  });
});

describe("a click on a list the game has replaced", () => {
  /** Seat 0, on the clock, single player: the list the board is drawing. */
  function ours(overrides: Partial<StateResponse> = {}): StateResponse {
    return stateResponse({
      state: gameView({ seat: 0, players: [HOST, GUEST], pending: pending({ player: 0 }) }),
      your_seat: 0,
      human_seats: [0],
      version: 3,
      event_cursor: 12,
      events: HISTORY,
      actions: [action(), action({ id: "a1-play_land", kind: "play_land" })],
      ...overrides,
    });
  }

  async function atTable() {
    mount({ gameId: "g1", seat: 0 });
    await settle();
    next().answer(ours());
    await settle();
  }

  it("sends the version the list came from", async () => {
    await atTable();
    act(() => latest.act.mutate("a1-play_land"));
    await settle();

    const post = next();
    expect(`${post.method} ${post.url}`).toBe("POST /api/games/g1/actions?ai_steps=1");
    expect(post.body).toEqual({ seat: 0, action_id: "a1-play_land", version: 3 });
  });

  it("answers a 409 stale_action by refetching, not by showing an error", async () => {
    await atTable();
    act(() => latest.act.mutate("a1-play_land"));
    await settle();

    next().answer(
      {
        detail: {
          code: "stale_action",
          detail: "action 'a1-play_land' is from version 3",
          version: 4,
        },
      },
      409,
    );
    await settle();

    // From the cursor already held, so nothing is narrated twice.
    const refetch = next();
    expect(`${refetch.method} ${refetch.url}`).toBe("GET /api/games/g1/state?since=12&seat=0");
    refetch.answer(ours({ version: 4, actions: [action()] }));
    await settle();

    expect(useUiStore.getState().error).toBeNull();
    expect(latest.actions.map((a) => a.id)).toEqual(["a0-pass"]);
    expect(parked).toHaveLength(0);
  });

  it("still shows a genuinely illegal action", async () => {
    await atTable();
    act(() => latest.act.mutate("nonsense"));
    await settle();

    next().answer({ detail: "unknown action id 'nonsense'" }, 400);
    await settle();

    expect(useUiStore.getState().error).toBe("400: unknown action id 'nonsense'");
    expect(parked).toHaveLength(0);
  });
});

describe("the pure halves", () => {
  it("waitingOnFrom names the other seat only when we hold nothing to do", () => {
    expect(waitingOnFrom(waiting(), 1)).toBe(0);
    expect(waitingOnFrom(waiting({ actions: [action()] }), 1)).toBeNull();
    expect(waitingOnFrom(waiting(), 0)).toBeNull();
    expect(waitingOnFrom(waiting(), null)).toBeNull();
    expect(
      waitingOnFrom(
        waiting({ state: gameView({ seat: 1, game_over: true, pending: null }) }),
        1,
      ),
    ).toBeNull();
  });

  it("freshEvents reads the batch's own start from its cursor", () => {
    const response = waiting({
      event_cursor: 14,
      events: [10, 11, 12, 13].map((step) => gameEvent({ step })),
    });
    expect(freshEvents(response, 12).map((event) => event.step)).toEqual([12, 13]);
    expect(freshEvents(response, 14)).toEqual([]);
    expect(freshEvents(response, 0)).toHaveLength(4);
  });
});
