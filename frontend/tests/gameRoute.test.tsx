/**
 * Coming back to a game draws the table, not the deal (TECH_DEBT FT-07).
 *
 * `GameRoute` holds the seat it asks for in state that starts null on every
 * mount, and used to draw "Dealing…" until that seat was set -- even with the
 * game's state sitting in the query cache. So a back press into a game was a
 * fade out of a deal nobody was waiting for, then a fade in of the table. The
 * table now draws for `held ?? game.yourSeat`, and `useGame` keeps the cached
 * response as placeholder data across the key change the held seat makes.
 *
 * `Table` is stubbed: what is under test is which of the two screens the route
 * chooses, frame by frame, and the board's own rendering has its own suites.
 * Every request is parked unanswered, so nothing here is a network result --
 * only the cache can be what draws the table.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GameRoute } from "../src/screens/GameRoute";
import { useUiStore } from "../src/state/uiStore";
import { gameView, stateResponse } from "./fixtures";

vi.mock("../src/components/game/Table", () => ({
  Table: ({ session }: { session: { seat: number } }) => (
    <div data-testid="table-stub" data-seat={session.seat} />
  ),
}));

beforeEach(() => {
  useUiStore.setState({ speed: "instant", error: null });
  // Parked forever: a request that never answers, so only the cache can draw.
  vi.stubGlobal(
    "fetch",
    (_url: string, init: RequestInit = {}) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        );
      }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(client: QueryClient) {
  // Every node that ever carried the deal's test id, from the first commit on.
  const dealt: Element[] = [];
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (!(node instanceof Element)) continue;
        if (node.matches('[data-testid="dealing"]')) dealt.push(node);
        dealt.push(...node.querySelectorAll('[data-testid="dealing"]'));
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  const view = render(
    <MemoryRouter initialEntries={["/games/g1"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/games/:gameId" element={<GameRoute />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { ...view, dealt, stop: () => observer.disconnect() };
}

function cachedClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("FT-07: returning to a game", () => {
  it("draws the table on the first frame from a cached response, and never deals", async () => {
    const client = cachedClient();
    /*
     * What a first visit leaves behind: the seat-less ask the route always
     * opens with. Only that key -- the seat-keyed one the route moves to next
     * is NOT seeded, which is the harder half: the key changes to one with no
     * data, and the table must not blank for the round trip.
     */
    client.setQueryData(
      ["game", "g1", null],
      stateResponse({ state: gameView({ seat: 2 }), your_seat: 2 }),
    );

    const { getByTestId, queryByTestId, dealt, stop } = mount(client);
    // The first commit, before any effect has set the held seat.
    expect(queryByTestId("dealing")).toBeNull();
    expect(getByTestId("table-stub").dataset.seat).toBe("2");

    // Let the held seat land and the key move to `["game", "g1", 2]`.
    await act(async () => {
      await Promise.resolve();
    });
    expect(client.getQueryCache().find({ queryKey: ["game", "g1", 2] })).toBeDefined();
    expect(getByTestId("table-stub").dataset.seat).toBe("2");
    expect(dealt, "the deal was drawn at some point").toEqual([]);
    stop();
  });

  it("still deals a game it knows nothing about", () => {
    const { getByTestId, queryByTestId, stop } = mount(cachedClient());
    expect(getByTestId("dealing")).toBeTruthy();
    expect(queryByTestId("table-stub")).toBeNull();
    stop();
  });

  it("does not draw another game's cached board as this one", () => {
    // The placeholder is guarded on the game id: a rematch moves `/games/a` to
    // `/games/b` inside one mounted route, and `a`'s board is not `b`'s.
    const client = cachedClient();
    client.setQueryData(["game", "other", 0], stateResponse());
    const { getByTestId, queryByTestId, stop } = mount(client);
    expect(getByTestId("dealing")).toBeTruthy();
    expect(queryByTestId("table-stub")).toBeNull();
    stop();
  });
});
