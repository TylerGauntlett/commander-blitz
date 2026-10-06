/**
 * The fetch wrapper, characterised against a stubbed `fetch`.
 *
 * What the rest of the client relies on: every request carries the pod token
 * and the library id when they exist, a failed response becomes an `ApiError`
 * that keeps the status and the server's machine-readable `code` and detail
 * object, a 204 is `undefined` rather than a JSON parse error, and each
 * endpoint spells its path, method and body the way `docs/api.md` says. None
 * of this was covered outside the routing tests, which only reach a handful
 * of endpoints (TECH_DEBT CG-02).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, getPlayerToken, setPlayerToken } from "../src/api/client";

interface Sent {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

let sent: Sent[];
let answer: () => Response;

function json(body: unknown, status = 200): () => Response {
  return () =>
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
}

beforeEach(() => {
  sent = [];
  answer = json({});
  window.localStorage.clear();
  setPlayerToken(null);
  vi.stubGlobal("fetch", async (url: string, init: RequestInit = {}) => {
    sent.push({
      url,
      method: init.method ?? "GET",
      headers: (init.headers ?? {}) as Record<string, string>,
      body: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
    });
    return answer();
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request", () => {
  it("sends JSON to /api, with no identity headers when it holds none", async () => {
    await api.decks();
    expect(sent[0].url).toBe("/api/decks");
    expect(sent[0].headers["Content-Type"]).toBe("application/json");
    expect(sent[0].headers["X-Player-Token"]).toBeUndefined();
  });

  it("attaches the pod token once set, and drops it once cleared", async () => {
    setPlayerToken("tok-1");
    expect(getPlayerToken()).toBe("tok-1");
    await api.decks();
    expect(sent[0].headers["X-Player-Token"]).toBe("tok-1");
    setPlayerToken(null);
    await api.decks();
    expect(sent[1].headers["X-Player-Token"]).toBeUndefined();
  });

  it("says which library is asking, on every request", async () => {
    await api.decks();
    const library = sent[0].headers["X-Library-Id"];
    expect(typeof library).toBe("string");
    expect(library.length).toBeGreaterThan(0);
    await api.card("forest");
    expect(sent[1].headers["X-Library-Id"]).toBe(library);
  });

  it("turns a plain-string failure into an ApiError that keeps the status", async () => {
    answer = json({ detail: "unknown deck 'x'" }, 400);
    const caught = await api.deck("x").catch((e) => e);
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught.status).toBe(400);
    expect(caught.message).toBe("400: unknown deck 'x'");
    expect(caught.code).toBeUndefined();
  });

  it("keeps the server's code and the whole detail object when there is one", async () => {
    answer = json(
      { detail: { code: "already_started", detail: "the pod has dealt", game_id: "g7" } },
      409,
    );
    const caught = await api.joinPod("GYRE-8412").catch((e) => e);
    expect(caught.status).toBe(409);
    expect(caught.code).toBe("already_started");
    expect(caught.detail?.game_id).toBe("g7");
    expect(caught.message).toBe("409: the pod has dealt");
  });

  it("falls back to the status text when the error body is not JSON", async () => {
    answer = () =>
      new Response("<html>gateway</html>", { status: 502, statusText: "Bad Gateway" });
    const caught = await api.decks().catch((e) => e);
    expect(caught.status).toBe(502);
    expect(caught.message).toBe("502: Bad Gateway");
  });

  it("treats 204 as nothing, not as a parse failure", async () => {
    answer = json(null, 204);
    await expect(api.deleteDeck("mine")).resolves.toBeUndefined();
    expect(sent[0]).toMatchObject({ url: "/api/decks/mine", method: "DELETE" });
  });
});

describe("the endpoints", () => {
  it("games: create, state, act, declare, advance, options, undo, delete", async () => {
    await api.newGame([{ deck_id: "aesi", kind: "human", name: "You" }], 7);
    await api.state("g1", 0, 12, 4, 25);
    await api.state("g1", null);
    await api.applyAction("g1", 0, "a3-cast", 1);
    await api.declare("g1", 0, "attackers", [[301, 1]]);
    await api.advance("g1", 0, 1);
    await api.setFullControl("g1", 0, true);
    await api.setManualMana("g1", 0, true, true);
    await api.undo("g1", 0);
    await api.deleteGame("g1");
    expect(sent.map((s) => `${s.method} ${s.url}`)).toEqual([
      "POST /api/games",
      "GET /api/games/g1/state?since=12&seat=0&since_version=4&timeout=25",
      "GET /api/games/g1/state?since=0",
      "POST /api/games/g1/actions?ai_steps=1",
      "POST /api/games/g1/declare",
      "POST /api/games/g1/advance?ai_steps=1",
      "POST /api/games/g1/options",
      "POST /api/games/g1/options",
      "POST /api/games/g1/undo",
      "DELETE /api/games/g1",
    ]);
    expect(sent[0].body).toEqual({
      seats: [{ deck_id: "aesi", kind: "human", name: "You" }],
      seed: 7,
    });
    expect(sent[3].body).toEqual({ seat: 0, action_id: "a3-cast" });
    expect(sent[4].body).toEqual({ seat: 0, kind: "attackers", pairs: [[301, 1]] });
    expect(sent[6].body).toEqual({ seat: 0, full_control: true });
    // `full_control` rides along with manual mana: the server takes the whole block.
    expect(sent[7].body).toEqual({ seat: 0, full_control: true, manual_mana: true });
  });

  it("choose: a pick-several decision goes as one set", async () => {
    await api.choose("g1", 0, [3, 0], 1);
    await api.choose("g1", 1, []);
    expect(sent.map((s) => `${s.method} ${s.url}`)).toEqual([
      "POST /api/games/g1/choose?ai_steps=1",
      "POST /api/games/g1/choose",
    ]);
    expect(sent[0].body).toEqual({ seat: 0, choices: [3, 0] });
    // Choosing none is an answer, not an absent body.
    expect(sent[1].body).toEqual({ seat: 1, choices: [] });
  });

  it("pods: create, join, poll, seat, admin, start, leave", async () => {
    await api.createPod();
    await api.createPod("Ada", "edgar", 3);
    await api.joinPod("gyre 8412", "Bo");
    await api.pod("GYRE-8412");
    await api.pod("GYRE-8412", 5, 20);
    await api.updateSeat("GYRE-8412", { deck_id: "aesi", locked: true });
    await api.adminSeat("GYRE-8412", 2, { action: "add_cpu", agent: "random" });
    await api.startPod("GYRE-8412");
    await api.startPod("GYRE-8412", 7);
    await api.leavePod("GYRE-8412");
    expect(sent.map((s) => `${s.method} ${s.url}`)).toEqual([
      "POST /api/pods",
      "POST /api/pods",
      "POST /api/pods/gyre%208412/join",
      "GET /api/pods/GYRE-8412?since=0",
      "GET /api/pods/GYRE-8412?since=5&timeout=20",
      "PATCH /api/pods/GYRE-8412/seat",
      "PATCH /api/pods/GYRE-8412/seats/2",
      "POST /api/pods/GYRE-8412/start",
      "POST /api/pods/GYRE-8412/start",
      "POST /api/pods/GYRE-8412/leave",
    ]);
    // No name unless given; a null deck and seed mean "the server decides".
    expect(sent[0].body).toEqual({ deck_id: null, seed: null });
    expect(sent[1].body).toEqual({ name: "Ada", deck_id: "edgar", seed: 3 });
    expect(sent[2].body).toEqual({ name: "Bo" });
    expect(sent[7].body).toEqual({ seed: null });
    expect(sent[8].body).toEqual({ seed: 7 });
  });

  it("decks and images", async () => {
    await api.importDeck("https://moxfield.com/decks/x", true);
    await api.images();
    await api.images("g 1");
    expect(sent.map((s) => `${s.method} ${s.url}`)).toEqual([
      "POST /api/decks/import",
      "GET /api/images",
      "GET /api/images?game_id=g%201",
    ]);
    expect(sent[0].body).toEqual({ url: "https://moxfield.com/decks/x", dry_run: true });
  });
});
