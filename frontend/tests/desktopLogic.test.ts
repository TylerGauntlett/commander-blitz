/**
 * `logic/desktop`: the decisions behind the desktop build, as pure functions.
 */

import { describe, expect, it } from "vitest";
import type { AppConfig } from "../src/api/types";
import {
  canImport,
  canPlayOnline,
  HOSTED_DEFAULT,
  HOSTED_ORIGIN,
  handoffImports,
  isHandoff,
  MAX_HANDOFF_DECKS,
  moxfieldUrl,
  onlineUrl,
} from "../src/logic/desktop";

const desktop = (online: boolean): AppConfig => ({
  mode: "desktop",
  online,
  remote_origin: "https://commanderblitz.com",
  app_version: "0.1.0",
  content_version: "1.2.3",
});

describe("what needs a connection", () => {
  it("the site never greys anything: it cannot know, and it is the server", () => {
    expect(canPlayOnline(HOSTED_DEFAULT)).toBe(true);
    expect(canImport(HOSTED_DEFAULT)).toBe(true);
    expect(canPlayOnline({ ...HOSTED_DEFAULT, online: false })).toBe(true);
  });

  it("the desktop goes by the sidecar's probe", () => {
    expect(canPlayOnline(desktop(true))).toBe(true);
    expect(canPlayOnline(desktop(false))).toBe(false);
    expect(canImport(desktop(false))).toBe(false);
  });
});

describe("onlineUrl", () => {
  it("is the hosted door, marked as a handoff", () => {
    expect(onlineUrl("https://commanderblitz.com")).toBe(
      "https://commanderblitz.com/?from=desktop",
    );
  });

  it("falls back to the known site when the sidecar names no remote", () => {
    expect(onlineUrl(null)).toBe(`${HOSTED_ORIGIN}/?from=desktop`);
  });

  it("carries a code to land in and the decks to bring", () => {
    const url = new URL(
      onlineUrl("http://127.0.0.1:8000", { join: "GYRE-8412", importIds: ["AbC", "xYz"] }),
    );
    expect(url.origin).toBe("http://127.0.0.1:8000");
    expect(url.searchParams.get("from")).toBe("desktop");
    expect(url.searchParams.get("join")).toBe("GYRE-8412");
    expect(url.searchParams.get("import")).toBe("AbC,xYz");
  });

  it("keeps the ids' case: a Moxfield id is case-sensitive", () => {
    expect(
      handoffImports(
        new URL(onlineUrl(null, { importIds: ["vVdybWVgC0imBOlW63FlTg"] })).search,
      ),
    ).toEqual(["vVdybWVgC0imBOlW63FlTg"]);
  });

  it("drops blanks and caps the list", () => {
    const many = Array.from({ length: 30 }, (_, i) => `d${i}`);
    const url = new URL(onlineUrl(null, { importIds: ["", ...many] }));
    expect(url.searchParams.get("import")?.split(",")).toHaveLength(MAX_HANDOFF_DECKS);
    expect(onlineUrl(null, { importIds: ["", ""] })).not.toContain("import=");
  });
});

describe("reading the handoff on the other side", () => {
  it("knows a desktop sent this visitor", () => {
    expect(isHandoff("?from=desktop")).toBe(true);
    expect(isHandoff("?from=desktop&join=X")).toBe(true);
    expect(isHandoff("")).toBe(false);
    expect(isHandoff("?join=X")).toBe(false);
  });

  it("lists the decks to import, trimmed and capped", () => {
    expect(handoffImports("?import=a,%20b,,c")).toEqual(["a", "b", "c"]);
    expect(handoffImports("?from=desktop")).toEqual([]);
    const many = Array.from({ length: 12 }, (_, i) => `d${i}`).join(",");
    expect(handoffImports(`?import=${many}`)).toHaveLength(MAX_HANDOFF_DECKS);
  });

  it("builds the address the import route expects", () => {
    expect(moxfieldUrl("vVdybWVgC0imBOlW63FlTg")).toBe(
      "https://moxfield.com/decks/vVdybWVgC0imBOlW63FlTg",
    );
    expect(moxfieldUrl("a/b")).toBe("https://moxfield.com/decks/a%2Fb");
  });
});
