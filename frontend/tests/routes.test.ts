/**
 * The addresses.
 *
 * `screenKey` is the one worth being careful about: it decides what counts as a
 * screen change, and `AnimatePresence` unmounts a whole subtree every time it
 * moves. Getting it wrong is not a wrong pixel, it is the catalogue vanishing
 * underneath a dossier -- so the cases that must *share* a key are asserted as
 * deliberately as the ones that must not.
 */

import { describe, expect, it } from "vitest";
import {
  BRAND,
  deckPath,
  gamePath,
  joinPath,
  podPath,
  screenKey,
  titleFor,
} from "../src/logic/routes";

describe("path builders", () => {
  it("normalises a code on the way into a path", () => {
    expect(podPath("gyre 8412")).toBe("/pods/GYRE-8412");
    expect(podPath("GYRE-8412")).toBe("/pods/GYRE-8412");
  });

  it("encodes an id that would otherwise change the path's shape", () => {
    expect(gamePath("a/b")).toBe("/games/a%2Fb");
    expect(deckPath("a b")).toBe("/decks/a%20b");
  });

  it("sends a cold pod link to the front door with the code in hand", () => {
    expect(joinPath("gyre8412")).toBe("/?join=GYRE-8412");
  });
});

describe("screenKey", () => {
  it("names the four screens", () => {
    expect(screenKey("/")).toBe("home");
    expect(screenKey("/decks")).toBe("decks");
    expect(screenKey("/pods/GYRE-8412")).toBe("pod:GYRE-8412");
    expect(screenKey("/games/g1")).toBe("game:g1");
  });

  it("keeps a dossier on the catalogue's screen", () => {
    // Otherwise opening one fades the catalogue out from under it, and the
    // filters somebody just set go with it.
    expect(screenKey("/decks/aesi")).toBe(screenKey("/decks"));
  });

  it("treats another pod as another room", () => {
    expect(screenKey("/pods/GYRE-8412")).not.toBe(screenKey("/pods/BRAMBLE-1234"));
    expect(screenKey("/games/g1")).not.toBe(screenKey("/games/g2"));
  });

  it("gives everything unrouted the same key", () => {
    expect(screenKey("/nonsense")).toBe("404");
    // The singular is a typo, not an alias -- it must not resolve to a pod.
    expect(screenKey("/pod/GYRE-8412")).toBe("404");
  });
});

describe("titleFor", () => {
  it("leaves the front door as the bare name", () => {
    expect(titleFor("/")).toBe(BRAND);
  });

  it("puts the pod's code in the tab", () => {
    // The case this exists for: four tabs on four pods, told apart at a glance.
    expect(titleFor("/pods/GYRE-8412")).toBe(`Pod GYRE-8412 · ${BRAND}`);
    expect(titleFor("/pods/gyre8412")).toBe(`Pod GYRE-8412 · ${BRAND}`);
  });

  it("names the other screens", () => {
    expect(titleFor("/games/g1")).toBe(`At the table · ${BRAND}`);
    expect(titleFor("/decks")).toBe(`Decks · ${BRAND}`);
    expect(titleFor("/decks/aesi")).toBe(`Decks · ${BRAND}`);
  });

  it("says so when there is nothing there", () => {
    expect(titleFor("/nonsense")).toBe(`Not found · ${BRAND}`);
    expect(titleFor("/pod/GYRE-8412")).toBe(`Not found · ${BRAND}`);
  });

  it("survives a hand-typed address", () => {
    // A stray percent is a malformed escape: decoding one throws, and a title
    // that throws takes the whole render with it.
    expect(() => titleFor("/pods/%")).not.toThrow();
  });

  it("ends every screen with the name", () => {
    for (const path of ["/", "/decks", "/pods/GYRE-8412", "/games/g1", "/nonsense"]) {
      expect(titleFor(path).endsWith(BRAND)).toBe(true);
    }
  });
});
