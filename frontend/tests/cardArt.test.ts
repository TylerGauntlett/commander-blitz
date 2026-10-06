/**
 * Which of three states a card's art is in.
 *
 * The distinction that matters is between "not loaded yet" and "this card has
 * no art". Collapsing them makes every card on the board flash a hatched
 * placeholder during the first paint, which looks like a bug and is one.
 */

import { describe, expect, it } from "vitest";
import type { CardView } from "../src/api/types";
import {
  artistFor,
  artistOf,
  artState,
  artStateFor,
  artUrl,
  artUrlFor,
  type ImageMap,
  type SeatImages,
} from "../src/logic/cardArt";

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

/**
 * Per-seat art: the printing a deck's author chose on Moxfield.
 *
 * Before this, every deck asked the catalog which Sol Ring to draw and the
 * catalog keeps one printing per card name -- so every deck looked the same and
 * nobody could recognise their own cards.
 */
const SEATS: SeatImages = {
  "0": {
    forest: {
      card_id: "forest",
      art: "/art/forest.jpg?p=11112222-3333-4444-5555-666677778888",
      artist: "Sam Burley",
    },
    // An override we have no illustrator for, which is the normal case: the
    // catalog has one row per card name, essentially never this printing's.
    odd_one: {
      card_id: "odd_one",
      art: "/art/odd_one.jpg?p=99998888-7777-6666-5555-444433332222",
      artist: null,
    },
  },
};

const card = (card_id: string, owner: number): CardView =>
  ({ card_id, owner, oid: 1, controller: owner }) as CardView;

describe("artUrlFor", () => {
  it("draws the printing that seat's deck chose", () => {
    expect(artUrlFor(LOADED, SEATS, card("forest", 0))).toBe(
      "/art/forest.jpg?p=11112222-3333-4444-5555-666677778888",
    );
  });

  it("leaves another seat with the catalog's pick", () => {
    // The reason this is a per-seat layer at all: both players run Forests and
    // only one of them chose that illustration.
    expect(artUrlFor(LOADED, SEATS, card("forest", 1))).toBe("/art/forest.jpg");
  });

  it("falls back to the base map for a card the deck said nothing about", () => {
    expect(artUrlFor(LOADED, SEATS, card("aetherling_serpent", 0))).toBeNull();
  });

  it("behaves exactly as before when there are no seat overrides", () => {
    for (const id of ["forest", "aetherling_serpent", "odd_one", "never_heard_of_it"]) {
      expect(artUrlFor(LOADED, null, card(id, 0))).toBe(artUrl(LOADED, id));
    }
  });

  it("returns undefined before the map has loaded", () => {
    expect(artUrlFor(null, SEATS, card("forest", 0))).toBeUndefined();
  });

  it("never yields a third-party URL", () => {
    // Same guarantee as above, and it has to hold across the seat layer too --
    // an override is still served by this server, printing and all.
    for (const [seat, refs] of Object.entries(SEATS ?? {})) {
      for (const id of Object.keys(refs)) {
        const url = artUrlFor(LOADED, SEATS, card(id, Number(seat)));
        if (typeof url === "string") expect(url.startsWith("/art/")).toBe(true);
      }
    }
  });
});

describe("artistFor", () => {
  it("credits the illustrator of the printing actually shown", () => {
    expect(artistFor(LOADED, SEATS, card("forest", 0))).toBe("Sam Burley");
  });

  it("credits nobody rather than the wrong person", () => {
    // `odd_one` has no artist on its override. Falling through to the base
    // map's credit would put someone else's name under this painting, which is
    // worse than no credit at all.
    expect(artistFor(LOADED, SEATS, card("odd_one", 0))).toBeNull();
  });

  it("still credits the catalog's illustrator at a seat with no overrides", () => {
    expect(artistFor(LOADED, SEATS, card("forest", 1))).toBe("Leon Tukker");
  });
});

describe("artStateFor", () => {
  it.each([
    ["pending", null as ImageMap, "forest", 0],
    ["ready", LOADED, "forest", 0],
    ["ready", LOADED, "forest", 1],
    ["none", LOADED, "aetherling_serpent", 0],
  ])("is %s", (expected, map, id, owner) => {
    expect(artStateFor(map, SEATS, card(id, owner))).toBe(expected);
  });
});

describe("a card that is not in a game", () => {
  it("takes no seat's printing", () => {
    /*
     * The lobby draws real card faces out of `GET /api/cards/{id}` with
     * synthetic fields: `oid: -1` and a filler `owner: 0`. That zero is not a
     * seat, and reading it as one would put seat 0's chosen illustrations on a
     * commander that belongs to no deck in this game.
     */
    const lobbyCard = { ...card("forest", 0), oid: -1 } as CardView;
    expect(artUrlFor(LOADED, SEATS, lobbyCard)).toBe("/art/forest.jpg");
    expect(artistFor(LOADED, SEATS, lobbyCard)).toBe("Leon Tukker");
  });
});
