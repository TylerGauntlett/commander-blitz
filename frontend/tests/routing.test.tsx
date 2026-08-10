/**
 * The addresses, end to end.
 *
 * These are the behaviours the router was added for, and each one is something
 * the previous `useState<Route>` client could not do: opening a pod by URL,
 * surviving a refresh at the table, and -- the promise that the old design said
 * a router could not keep -- never leaving a dead lobby behind for the back
 * button to find.
 *
 * `fetch` is stubbed rather than mocked per-hook, because what is being tested
 * includes *which request went out first and what header it carried*.
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setPlayerToken } from "../src/api/client";
import { storeToken } from "../src/state/usePod";
import { linkGame } from "../src/state/usePodSession";
import { deckDetail, deckSummary, podView } from "../src/testing/fixtures";
import { renderApp } from "./renderWithRouter";

interface Call {
  path: string;
  token: string | null;
}

let calls: Call[];
/** path prefix -> what to answer with. The *longest* match wins. */
let routes: { prefix: string; status?: number; body: unknown }[];

function reply(path: string) {
  // Longest rather than first, so `/api/decks/aesi` cannot be answered with the
  // deck *list* just because `/api/decks` was registered earlier. Ordering
  // traps in a stub read as product bugs.
  return routes
    .filter((route) => path.startsWith(route.prefix))
    .sort((a, b) => b.prefix.length - a.prefix.length)[0];
}

beforeEach(() => {
  calls = [];
  routes = [{ prefix: "/api/decks", body: [deckSummary()] }];
  window.sessionStorage.clear();
  setPlayerToken(null);

  // Answered once per endpoint; every repeat blocks forever.
  //
  // Not a shortcut -- it is what the server does. The pod and the game are read
  // by long polls that re-issue the instant one lands, so a stub that answered
  // every time would spin the loop as fast as the event loop allows and starve
  // the assertions. A poll that hangs is exactly a poll waiting for news.
  const answered = new Set<string>();

  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const path = String(url);
    const headers = (init?.headers ?? {}) as Record<string, string>;
    calls.push({ path, token: headers["X-Player-Token"] ?? null });
    const found = reply(path);
    const key = found?.prefix ?? path;
    if (answered.has(key)) return new Promise<Response>(() => undefined);
    answered.add(key);
    const status = found?.status ?? (found ? 200 : 404);
    return {
      ok: status < 400,
      status,
      statusText: "",
      json: async () => (status < 400 ? found?.body : { detail: { code: "nope" } }),
    } as Response;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the front door", () => {
  it("is what `/` renders", async () => {
    renderApp("/");
    expect(await screen.findByTestId("home")).toBeTruthy();
  });

  it("takes the code from `?join=`, which is where a cold pod link lands", async () => {
    renderApp("/?join=gyre-8412");
    const field = (await screen.findByTestId("pod-code")) as HTMLInputElement;
    expect(field.value).toBe("GYRE-8412");
  });
});

describe("a pod address", () => {
  it("sends a tab holding no token to the front door, code in hand", async () => {
    const app = renderApp("/pods/GYRE-8412");
    // The link is public -- it gets pasted into group chats -- so arriving at
    // it cannot be what grants a seat.
    await waitFor(() => expect(app.where.pathname).toBe("/"));
    expect(app.where.search).toBe("?join=GYRE-8412");
    // Replaced, not pushed: a redirect target is not a place you can go back to.
    expect(app.where.how).toBe("REPLACE");
  });

  it("opens the lobby for a tab that has one, with nothing to click", async () => {
    // The refresh case. Before, a reload forgot which pod you were in.
    storeToken("GYRE-8412", "tok-1");
    routes.push({ prefix: "/api/pods/GYRE-8412", body: podView([{ is_you: true }]) });

    renderApp("/pods/GYRE-8412");
    expect(await screen.findByTestId("new-game")).toBeTruthy();

    // And the very first pod request carried the token -- not a retry after a
    // 403, which is what an effect-armed token would have produced.
    const first = calls.find((call) => call.path.includes("/api/pods/"));
    expect(first?.token).toBe("tok-1");
  });

  it("moves everybody to the table when the pod deals, leaving no way back", async () => {
    storeToken("GYRE-8412", "tok-1");
    routes.push({
      prefix: "/api/pods/GYRE-8412",
      body: podView([{ is_you: true }], { status: "in_game", game_id: "g1" }),
    });

    const app = renderApp("/pods/GYRE-8412");
    await waitFor(() => expect(app.where.pathname).toBe("/games/g1"));
    // The whole argument the old no-router docblock made: the pod is dealt, so
    // its lobby must stop being a history entry rather than sit there offering
    // to return to a room that is gone.
    expect(app.where.how).toBe("REPLACE");
  });
});

describe("a table address", () => {
  it("refuses one this tab was never dealt into", async () => {
    routes.push({ prefix: "/api/games/g1/state", status: 403, body: null });
    renderApp("/games/g1");
    expect(await screen.findByText(/belongs to a pod you are not in/)).toBeTruthy();
  });

  it("says so when the game is gone rather than sitting on 'Dealing…'", async () => {
    linkGame("g1", "GYRE-8412");
    storeToken("GYRE-8412", "tok-1");
    routes.push({ prefix: "/api/games/g1/state", status: 404, body: null });
    renderApp("/games/g1");
    expect(await screen.findByText(/over, or the server has restarted/)).toBeTruthy();
  });

  it("finds its token through the game it remembers being dealt", async () => {
    linkGame("g1", "GYRE-8412");
    storeToken("GYRE-8412", "tok-1");
    routes.push({ prefix: "/api/games/g1/state", status: 500, body: null });

    renderApp("/games/g1");
    await waitFor(() => expect(calls.some((c) => c.path.includes("/api/games/"))).toBe(true));
    const first = calls.find((call) => call.path.includes("/api/games/"));
    expect(first?.token).toBe("tok-1");
  });
});

describe("the catalogue", () => {
  it("is a place, and so is one deck in it", async () => {
    renderApp("/decks");
    expect(await screen.findByTestId("deck-catalog")).toBeTruthy();
  });

  it("keeps the catalogue mounted underneath a dossier", async () => {
    // Same screen key, so opening a deck does not fade the catalogue out from
    // under it -- and the filters somebody just set survive.
    routes.push({ prefix: "/api/decks/aesi", body: deckDetail() });
    renderApp("/decks/aesi");
    expect(await screen.findByTestId("deck-catalog")).toBeTruthy();
    expect(await screen.findByTestId("deck-dossier")).toBeTruthy();
  });
});

describe("an address that is not anything", () => {
  it("says so instead of quietly going home", async () => {
    renderApp("/nonsense");
    expect(await screen.findByTestId("not-found")).toBeTruthy();
  });

  it("does not treat the singular as an alias for a pod", async () => {
    renderApp("/pod/GYRE-8412");
    expect(await screen.findByTestId("not-found")).toBeTruthy();
  });
});
