/**
 * Which decks the desktop door finishes before it draws (ADR 0022).
 *
 * The rule is the cost of a launch: nothing on the site, nothing offline, and
 * no request at all once every imported deck says it is complete.
 */

import { describe, expect, it } from "vitest";
import type { AppConfig, DeckSummary } from "../src/api/types";
import { decksToFinish, HOSTED_DEFAULT } from "../src/logic/desktop";
import { deckSummary } from "../src/testing/fixtures";

const DESKTOP: AppConfig = { ...HOSTED_DEFAULT, mode: "desktop", online: true };

function imported(id: string, complete: DeckSummary["complete"]): DeckSummary {
  return deckSummary({ id, source: "moxfield", complete });
}

describe("decksToFinish", () => {
  it("names every import not known to be complete", () => {
    const decks = [
      deckSummary({ id: "aesi" }),
      imported("half", false),
      imported("unchecked", null),
      imported("older", undefined),
      imported("done", true),
    ];
    expect(decksToFinish(DESKTOP, decks)).toEqual(["half", "unchecked", "older"]);
  });

  it("asks nothing once every deck is complete", () => {
    expect(
      decksToFinish(DESKTOP, [imported("done", true), deckSummary({ id: "aesi" })]),
    ).toEqual([]);
  });

  it("asks nothing offline: there is nobody to fetch from", () => {
    expect(decksToFinish({ ...DESKTOP, online: false }, [imported("half", false)])).toEqual([]);
  });

  it("asks nothing on the site, which never fetches eagerly", () => {
    expect(decksToFinish(HOSTED_DEFAULT, [imported("half", false)])).toEqual([]);
  });

  it("waits for the deck list", () => {
    expect(decksToFinish(DESKTOP, undefined)).toEqual([]);
  });
});
