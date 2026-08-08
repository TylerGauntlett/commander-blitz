/**
 * Which of three states a card's art is in.
 *
 * The distinction that matters is between "not loaded yet" and "this card has
 * no art". Collapsing them makes every card on the board flash a hatched
 * placeholder during the first paint, which looks like a bug and is one.
 */

import { describe, expect, it } from "vitest";
import { type ImageMap, artState, artUrl, artistOf } from "../src/logic/cardArt";

const LOADED: ImageMap = {
  forest: { card_id: "forest", art: "/art/forest.jpg", artist: "Leon Tukker" },
  // A real case: five cards in data/cards/ are original designs with no
  // printing anywhere, so the server reports them as explicitly artless.
  aetherling_serpent: null,
  // Present, but the server could not resolve a printing for it.
  odd_one: { card_id: "odd_one", art: null, artist: null },
};

describe("artUrl", () => {
  it("returns undefined before the map has loaded", () => {
    // Not null: null means "loaded, and there is no art", which draws a plate.
    expect(artUrl(null, "forest")).toBeUndefined();
  });

  it("returns the same-origin path once loaded", () => {
    expect(artUrl(LOADED, "forest")).toBe("/art/forest.jpg");
  });

  it("returns null for a card the server says has no printing", () => {
    expect(artUrl(LOADED, "aetherling_serpent")).toBeNull();
  });

  it("returns null for an entry whose art is null", () => {
    expect(artUrl(LOADED, "odd_one")).toBeNull();
  });

  it("returns null for a card missing from the map entirely", () => {
    expect(artUrl(LOADED, "never_heard_of_it")).toBeNull();
  });

  it("never yields a third-party URL", () => {
    // The guarantee the whole pipeline exists for: the browser talks to this
    // server and nothing else, so the board renders when Scryfall does not.
    for (const id of Object.keys(LOADED)) {
      const url = artUrl(LOADED, id);
      if (typeof url === "string") {
        expect(url.startsWith("/art/")).toBe(true);
      }
    }
  });
});

describe("artState", () => {
  it.each([
    ["pending", null as ImageMap, "forest"],
    ["ready", LOADED, "forest"],
    ["none", LOADED, "aetherling_serpent"],
    ["none", LOADED, "unknown"],
  ])("is %s", (expected, map, id) => {
    expect(artState(map, id)).toBe(expected);
  });
});

describe("artistOf", () => {
  it("credits the illustrator when there is one", () => {
    expect(artistOf(LOADED, "forest")).toBe("Leon Tukker");
  });

  it("is null before the map loads", () => {
    expect(artistOf(null, "forest")).toBeNull();
  });

  it("is null for an artless card", () => {
    expect(artistOf(LOADED, "aetherling_serpent")).toBeNull();
  });
});
