/**
 * The handoff: the desktop sends a visitor to the hosted site with the decks
 * they imported at home, and the site imports them before showing the door.
 *
 * Driven through `renderApp` because the whole point is the address: what
 * `?from=desktop&import=` makes the route do, and where it lands afterwards.
 */

import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppConfig } from "../src/api/types";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad } from "../src/input/pad";
import { deckSummary } from "../src/testing/fixtures";
import { renderApp } from "./renderWithRouter";

interface Call {
  method: string;
  path: string;
  body: unknown;
}

let calls: Call[];
let decks: ReturnType<typeof deckSummary>[];
let config: AppConfig;

beforeEach(() => {
  calls = [];
  decks = [deckSummary()];
  config = {
    mode: "hosted",
    online: true,
    remote_origin: null,
    app_version: "0.1.0",
    content_version: "0.1.0",
  };
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const path = String(url);
    const method = init?.method ?? "GET";
    calls.push({
      method,
      path,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    });
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (path === "/api/config") return json(config);
    if (path === "/api/decks") return json(decks);
    if (path === "/api/decks/import") {
      const id = String((init?.body && JSON.parse(String(init.body)).url) ?? "")
        .split("/")
        .pop();
      if (id === "broken") return json({ detail: { code: "private", detail: "private" } }, 403);
      return json({
        deck: deckSummary({ id: `mox_${id?.toLowerCase()}`, source: "moxfield" }),
        source: "moxfield",
        source_id: id,
        total: 100,
        playable: 100,
        simplified: 0,
        cards: [],
        problems: [],
      });
    }
    if (path === "/api/decks/complete") {
      // The server finishes what it can and the list says so afterwards.
      decks = decks.map((deck) =>
        deck.source === "moxfield" ? { ...deck, complete: true } : deck,
      );
      return json([]);
    }
    if (path.startsWith("/api/images")) return json({ images: {}, seats: null });
    // Anything else hangs, the way a long poll does.
    return new Promise<Response>(() => undefined);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetPad();
  resetInputMode();
});

const imports = () => calls.filter((c) => c.path === "/api/decks/import");

describe("arriving from the desktop", () => {
  it("imports each deck by its Moxfield link, in order, then shows the door", async () => {
    const app = renderApp("/?from=desktop&import=AbC,xYz");
    expect(await screen.findByTestId("handoff-import")).toBeTruthy();

    await waitFor(() => expect(imports()).toHaveLength(2));
    expect(imports().map((c) => c.body)).toEqual([
      { url: "https://moxfield.com/decks/AbC", dry_run: false },
      { url: "https://moxfield.com/decks/xYz", dry_run: false },
    ]);

    // The address starts at `/` already, so waiting on the pathname proves
    // nothing (it passed locally and raced on the slower runner); what says
    // the handoff is over is the replace that drops the query string.
    await waitFor(() => expect(app.where.how).toBe("REPLACE"));
    expect(app.where.pathname).toBe("/");
    expect(app.where.search).toBe("");
    expect(await screen.findByTestId("home")).toBeTruthy();
  });

  it("lands in the pod when a code came along", async () => {
    const app = renderApp("/?from=desktop&join=GYRE-8412&import=AbC");
    await waitFor(() => expect(app.where.search).toBe("?join=GYRE-8412"));
    expect(app.where.how).toBe("REPLACE");
    const field = (await screen.findByTestId("pod-code")) as HTMLInputElement;
    expect(field.value).toBe("GYRE-8412");
  });

  it("skips a deck this server already has", async () => {
    decks = [
      deckSummary(),
      deckSummary({ id: "mox_abc", source: "moxfield", source_id: "AbC" }),
    ];
    const app = renderApp("/?from=desktop&import=AbC,xYz");
    // The address starts at `/` already; what says the handoff is over is
    // the replace that drops the query string.
    await waitFor(() => expect(app.where.how).toBe("REPLACE"));
    expect(imports().map((c) => c.body)).toEqual([
      { url: "https://moxfield.com/decks/xYz", dry_run: false },
    ]);
  });

  it("carries on past a deck that cannot be imported", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const app = renderApp("/?from=desktop&import=broken,xYz");
    await waitFor(() => expect(app.where.how).toBe("REPLACE"));
    expect(imports()).toHaveLength(2);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("broken"), expect.anything());
    warn.mockRestore();
  });

  it("is nothing without the marker: a plain visit never imports", async () => {
    renderApp("/?import=AbC");
    expect(await screen.findByTestId("home")).toBeTruthy();
    expect(imports()).toHaveLength(0);
    expect(screen.queryByTestId("handoff-import")).toBeNull();
  });
});

describe("the door on the desktop", () => {
  it("hands the window to the site with the imported decks' ids", async () => {
    config = {
      mode: "desktop",
      online: true,
      remote_origin: "https://commanderblitz.com",
      app_version: "0.1.0",
      content_version: "1.2.3",
    };
    decks = [
      deckSummary(),
      deckSummary({ id: "mox_abc", source: "moxfield", source_id: "AbC" }),
      deckSummary({ id: "mox_old", source: "moxfield", source_id: "" }),
    ];
    const openOnline = vi.fn<(url: string) => Promise<void>>(async () => undefined);
    window.commanderblitz = {
      version: { shell: "1.0.0", content: "1.2.3" },
      onUpdate: () => () => undefined,
      restartToUpdate: async () => undefined,
      openOnline,
      returnLocal: async () => undefined,
      onConnectivity: () => () => undefined,
      diagnostics: async () => {
        throw new Error("unused");
      },
    };
    try {
      renderApp("/");
      const card = await screen.findByTestId("join-pod");
      await waitFor(() => expect(card.textContent).toContain("Online"));
      // The row opens on Play: one click selects the card, the second presses.
      card.click();
      card.click();
      (await screen.findByTestId("play-online")).click();
      await waitFor(() => expect(openOnline).toHaveBeenCalled());
      const url = new URL(openOnline.mock.calls[0][0]);
      expect(url.origin).toBe("https://commanderblitz.com");
      expect(url.searchParams.get("from")).toBe("desktop");
      // Only decks with a known Moxfield id; a precon and a pre-field import
      // have nothing to send.
      expect(url.searchParams.get("import")).toBe("AbC");
    } finally {
      window.commanderblitz = undefined;
    }
  });

  it("finishes an import's art before showing the door, once", async () => {
    config = {
      mode: "desktop",
      online: true,
      remote_origin: "https://commanderblitz.com",
      app_version: "0.1.0",
      content_version: "1.2.3",
    };
    decks = [
      deckSummary(),
      deckSummary({ id: "mox_abc", source: "moxfield", complete: false }),
    ];
    renderApp("/");
    const finishing = () => calls.filter((c) => c.path === "/api/decks/complete");
    await waitFor(() => expect(finishing()).toHaveLength(1));
    // Back at the door, with the list refetched and nothing asked twice.
    await waitFor(() => expect(screen.queryByTestId("finishing-art")).toBeNull());
    await screen.findByTestId("join-pod");
    expect(finishing()).toHaveLength(1);
  });

  it("asks nothing when every deck is complete", async () => {
    config = {
      mode: "desktop",
      online: true,
      remote_origin: "https://commanderblitz.com",
      app_version: "0.1.0",
      content_version: "1.2.3",
    };
    decks = [deckSummary(), deckSummary({ id: "mox_abc", source: "moxfield", complete: true })];
    renderApp("/");
    await screen.findByTestId("join-pod");
    // Once the list has been read and the door has had a chance to act on it.
    await waitFor(() => expect(calls.some((c) => c.path === "/api/decks")).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls.filter((c) => c.path === "/api/decks/complete")).toHaveLength(0);
  });
});
