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

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setPlayerToken } from "../src/api/client";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad } from "../src/input/pad";
import { storeToken } from "../src/state/usePod";
import { linkGame } from "../src/state/usePodSession";
import {
  deckDetail,
  deckSummary,
  gameView,
  player,
  podView,
  stateResponse,
} from "../src/testing/fixtures";
import { renderApp } from "./renderWithRouter";

interface Call {
  path: string;
  token: string | null;
}

let calls: Call[];
/** path prefix -> what to answer with. The *longest* match wins. */
let routes: { prefix: string; status?: number; body: unknown; repeat?: boolean }[];

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
    /*
     * `repeat` opts a route out of answer-once, and the table is what needs it.
     *
     * `useGame`'s query key holds the seat, which starts null and moves once the
     * server has said which seat is yours -- so a rendered table asks for its
     * state TWICE under two keys, and a stub that answered once left the second
     * hanging and the screen on "Dealing…" forever. Only the routes a test
     * genuinely wants to poll say so; everything else keeps the blocking
     * default, which is what stops a long poll spinning the event loop.
     */
    if (!found?.repeat) {
      if (answered.has(key)) return new Promise<Response>(() => undefined);
      answered.add(key);
    }
    const status = found?.status ?? (found ? 200 : 404);
    return {
      ok: status < 400,
      status,
      statusText: "",
      // An error route may say what went wrong; one that does not gets a shrug.
      json: async () =>
        status < 400 ? found?.body : (found?.body ?? { detail: { code: "nope" } }),
    } as Response;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  // The app starts the pad poll on mount and nothing here unmounts it: its
  // idle timer fired after this environment was torn down and reached for a
  // `requestAnimationFrame` that no longer existed -- an "unhandled error"
  // that failed a run in which every test had passed.
  resetPad();
  resetInputMode();
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

describe("joining from the door", () => {
  it("sends a player whose pod has already dealt straight to the table", async () => {
    // The server answers `already_started` with the game id in the detail, and
    // this tab still holds the token it was given for that pod -- a reload
    // after the deal, not a stranger with a stale link.
    storeToken("GYRE-8412", "tok-1");
    routes.push({
      prefix: "/api/pods/GYRE-8412/join",
      status: 409,
      body: { detail: { code: "already_started", detail: "dealt", game_id: "g9" } },
    });
    routes.push({ prefix: "/api/games/g9/state", body: stateResponse(), repeat: true });

    const app = renderApp("/?join=GYRE-8412");
    fireEvent.click(await screen.findByTestId("join-pod"));
    fireEvent.click(await screen.findByTestId("join-go"));
    await waitFor(() => expect(app.where.pathname).toBe("/games/g9"));
    expect(app.where.how).toBe("REPLACE");
    // ...and everything asked on behalf of that game carries the token.
    //
    // Waited for, not read off at once: the address moves when the table
    // commits, and the table's first state request goes out from an effect
    // after that commit. Between the two is a gap wide enough for a loaded
    // runner to assert into, and an empty list would then pass the `every`.
    const forGame = () => calls.filter((call) => call.path.includes("g9"));
    await waitFor(() => expect(forGame().length).toBeGreaterThan(0));
    expect(forGame().every((call) => call.token === "tok-1")).toBe(true);
  });

  it("stays at the door, saying why, when the join is refused for any other reason", async () => {
    routes.push({
      prefix: "/api/pods/GYRE-8412/join",
      status: 404,
      body: { detail: { code: "not_found", detail: "no such pod" } },
    });
    const app = renderApp("/?join=GYRE-8412");
    fireEvent.click(await screen.findByTestId("join-pod"));
    fireEvent.click(await screen.findByTestId("join-go"));
    await waitFor(() => expect(calls.some((c) => c.path.includes("/join"))).toBe(true));
    expect(await screen.findByText(/no such pod/)).toBeTruthy();
    expect(app.where.pathname).toBe("/");
  });
});

describe("a pod that cannot be found", () => {
  it("says there is no such pod, and offers the way back", async () => {
    storeToken("GYRE-8412", "tok-1");
    routes.push({ prefix: "/api/pods/GYRE-8412", status: 404, body: null });
    const app = renderApp("/pods/GYRE-8412");
    expect(await screen.findByText(/There is no pod with that code/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await waitFor(() => expect(app.where.pathname).toBe("/"));
  });

  it("says a closed pod has closed", async () => {
    storeToken("GYRE-8412", "tok-1");
    routes.push({ prefix: "/api/pods/GYRE-8412", status: 410, body: null });
    renderApp("/pods/GYRE-8412");
    expect(await screen.findByText(/That pod has closed/)).toBeTruthy();
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

/**
 * The rematch, which used to be the front door wearing a different word.
 *
 * `onRematch={quit}` -- the button said Rematch and navigated to `/`. So the
 * one thing somebody wants at the end of a game they enjoyed was four steps
 * away: the door, a new pod, a deck for every chair, and a deal. It deals the
 * same lineup now, through `POST /api/games`, which is the endpoint that
 * already takes exactly what a finished game can describe.
 */
describe("a rematch", () => {
  /** A finished game, and a `POST /api/games` that answers with the next one. */
  function overAndReady() {
    const finished = gameView({
      game_over: true,
      winners: [0],
      players: [
        player({ pid: 0, name: "You", deck_id: "aesi" }),
        player({ pid: 1, name: "AI 1", deck_id: "edgar", hand: null }),
      ],
      pending: null,
    });
    routes.push({
      prefix: "/api/games/g1/state",
      body: stateResponse({ state: finished }),
      repeat: true,
    });
    routes.push({
      prefix: "/api/games",
      body: {
        game_id: "g2",
        your_seat: 0,
        state: gameView({ seat: 0 }),
        actions: [],
        events: [],
        event_cursor: 0,
        version: 1,
        human_seats: [0],
      },
    });
    routes.push({ prefix: "/api/games/g2/state", body: stateResponse(), repeat: true });
  }

  it("deals a new game with the same decks and seats, and goes to it", async () => {
    linkGame("g1", "GYRE-8412");
    storeToken("GYRE-8412", "tok-1");
    overAndReady();

    const app = renderApp("/games/g1");
    fireEvent.click(await screen.findByText("Rematch"));

    await waitFor(() => expect(app.where.pathname).toBe("/games/g2"));
    // Replaced, not pushed: the table behind us is over, and back must not
    // offer to walk into it -- the same rule the pod's deal follows.
    expect(app.where.how).toBe("REPLACE");

    const made = calls.find((call) => call.path.endsWith("/api/games"));
    expect(made, "nothing was posted to /api/games").toBeTruthy();
  });

  it("does not go to the front door, which is what it used to do", async () => {
    linkGame("g1", "GYRE-8412");
    storeToken("GYRE-8412", "tok-1");
    overAndReady();

    const app = renderApp("/games/g1");
    fireEvent.click(await screen.findByText("Rematch"));
    await waitFor(() => expect(app.where.pathname).not.toBe("/games/g1"));
    expect(app.where.pathname).not.toBe("/");
  });
});
