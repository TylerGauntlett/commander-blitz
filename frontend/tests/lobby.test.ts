/**
 * The lobby's decisions.
 *
 * `canStart` and `whyNot` are the pair worth being careful about: they answer
 * the same question -- "can the host deal, and if not why not" -- and a screen
 * whose button and explanation disagree is worse than one with neither. So
 * every case below asserts on both together.
 */

import { describe, expect, it } from "vitest";
import {
  canStart,
  cpuNumber,
  EMPTY_FILTERS,
  filledSeats,
  firstEmpty,
  looksLikeCode,
  normaliseCode,
  openSeats,
  podSize,
  readyTrack,
  seatLabel,
  visibleDecks,
  whyNot,
  yourSeat,
} from "../src/logic/lobby";
import { deckSummary, podView } from "./fixtures";

const me = { kind: "human" as const, is_you: true, is_host: true, name: "You" };
const cpu = { kind: "cpu" as const, ready: true, locked: true, name: "CPU 1" };

function locked(overrides = {}) {
  return { ...me, deck: deckSummary(), locked: true, ready: true, ...overrides };
}

describe("seat arithmetic", () => {
  it("counts only the seats that would become players", () => {
    const pod = podView([locked(), cpu, { kind: "open" }]);
    expect(podSize(pod)).toBe(2);
    expect(openSeats(pod)).toBe(1);
    expect(filledSeats(pod).map((seat) => seat.index)).toEqual([0, 1]);
  });

  it("finds your own chair", () => {
    const pod = podView([cpu, { ...me, index: 1 }]);
    expect(yourSeat(pod)?.index).toBe(1);
  });

  it("has no chair for a spectator", () => {
    expect(yourSeat(podView([cpu]))).toBeNull();
  });

  it("never offers seat 0 as the first empty one", () => {
    // A host who cleared their own chair would have no way back into their pod.
    expect(firstEmpty(podView([{ kind: "empty" }]))).toBe(1);
  });

  it("numbers CPUs among the CPUs, not by seat index", () => {
    // The second CPU in a pod whose seat 1 is a human is still "CPU 2".
    const pod = podView([locked(), { kind: "human", name: "Priya" }, cpu, cpu]);
    expect(cpuNumber(pod, 2)).toBe(1);
    expect(cpuNumber(pod, 3)).toBe(2);
  });
});

describe("seatLabel", () => {
  it("names you, not your name", () => {
    expect(seatLabel(podView([{ ...me, deck: deckSummary() }]), 0).title).toBe("You");
  });

  it("says what a player is doing", () => {
    const pod = podView([locked(), { kind: "human", name: "Priya" }]);
    expect(seatLabel(pod, 1)).toEqual({ title: "Priya", sub: "Choosing a deck…" });
  });

  it("says locked in once they are", () => {
    const pod = podView([
      locked(),
      { kind: "human", name: "Priya", locked: true, deck: deckSummary(), ready: true },
    ]);
    expect(seatLabel(pod, 1).sub).toBe("Locked in");
  });

  it("says a CPU is ready, which is the only thing true about it", () => {
    expect(seatLabel(podView([locked(), cpu]), 1).sub).toBe("Ready");
  });

  it("describes an open chair and an empty one differently", () => {
    const pod = podView([locked(), { kind: "open" }]);
    expect(seatLabel(pod, 1).title).toBe("Open chair");
    expect(seatLabel(pod, 2).title).toBe("No one yet");
  });
});

describe("canStart and whyNot agree", () => {
  it("a host with no deck is told to pick one", () => {
    const pod = podView([me, cpu]);
    expect(canStart(pod)).toBe(false);
    expect(whyNot(pod)).toMatch(/pick a deck/i);
  });

  it("a lone host is told to find an opponent", () => {
    const pod = podView([locked()]);
    expect(canStart(pod)).toBe(false);
    expect(whyNot(pod)).toMatch(/at least one opponent/i);
  });

  it("an unlocked host is told their card is not stamped", () => {
    const pod = podView([{ ...me, deck: deckSummary() }, cpu]);
    expect(canStart(pod)).toBe(false);
    expect(whyNot(pod)).toMatch(/not stamped/i);
  });

  it("names the players it is waiting on", () => {
    const pod = podView([
      locked(),
      { kind: "human", name: "Priya", deck: deckSummary() },
      { kind: "human", name: "Marco" },
    ]);
    expect(canStart(pod)).toBe(false);
    expect(whyNot(pod)).toBe("Waiting on Priya and Marco.");
  });

  it("uses a comma list past two", () => {
    const pod = podView([
      locked(),
      { kind: "human", name: "Priya" },
      { kind: "human", name: "Marco" },
      { kind: "human", name: "Sam" },
    ]);
    expect(whyNot(pod)).toBe("Waiting on Priya, Marco and Sam.");
  });

  it("an open chair does not block the deal -- a CPU will fill it", () => {
    const pod = podView([locked(), cpu, { kind: "open" }]);
    expect(canStart(pod)).toBe(true);
    expect(whyNot(pod)).toMatch(/1 chair still open/);
  });

  it("counts an open chair towards the two-player minimum", () => {
    // The host plus a chair somebody may take is a pod worth dealing: the open
    // chair becomes a CPU server-side.
    const pod = podView([locked(), { kind: "open" }]);
    expect(canStart(pod)).toBe(true);
  });

  it("a ready pod says how many cards are up", () => {
    const pod = podView([locked(), cpu]);
    expect(canStart(pod)).toBe(true);
    expect(whyNot(pod)).toBe("2 cards up. Deal them.");
  });

  it("a guest cannot deal and is told the host will", () => {
    const pod = podView([
      {
        kind: "human",
        name: "Host",
        is_host: true,
        locked: true,
        ready: true,
        deck: deckSummary(),
      },
      { ...me, is_host: false, deck: deckSummary(), locked: true, ready: true },
    ]);
    expect(canStart(pod)).toBe(false);
    expect(whyNot(pod)).toMatch(/waiting on the host/i);
  });

  it("a dealt pod cannot be dealt again", () => {
    const pod = podView([locked(), cpu], { status: "in_game", game_id: "abc" });
    expect(canStart(pod)).toBe(false);
    expect(whyNot(pod)).toMatch(/taking you to the table/i);
  });

  it("a closed pod says so", () => {
    const pod = podView([locked()], { status: "closed" });
    expect(whyNot(pod)).toMatch(/closed/i);
  });

  it("a spectator is told they are watching", () => {
    expect(whyNot(podView([cpu, cpu]))).toMatch(/watching/i);
  });
});

describe("readyTrack", () => {
  it("draws one segment per chair, whatever is in it", () => {
    const pod = podView([locked(), cpu, { kind: "human", name: "Priya" }]);
    expect(readyTrack(pod)).toEqual(["on", "on", "wait", "none"]);
  });
});

describe("the catalogue filter", () => {
  // `notes` is searched too, so the fixture's shared default would make every
  // deck match every word. Each one gets its own.
  const decks = [
    deckSummary({
      id: "aesi",
      name: "Aesi",
      color_identity: ["G", "U"],
      tags: ["Ramp"],
      notes: "Lands, and more lands.",
    }),
    deckSummary({
      id: "edgar",
      name: "Edgar Markov",
      color_identity: ["W", "B", "R"],
      tags: ["Aggro"],
      commander_names: ["Edgar Markov"],
      notes: "Vampires, quickly.",
    }),
    deckSummary({
      id: "mine",
      name: "Zada Storm",
      color_identity: ["R"],
      source: "moxfield",
      tags: [],
      commander_names: ["Zada, Hedron Grinder"],
      notes: "",
    }),
  ];

  it("returns everything by default, sorted by name", () => {
    expect(visibleDecks(decks, EMPTY_FILTERS).map((d) => d.id)).toEqual([
      "aesi",
      "edgar",
      "mine",
    ]);
  });

  it("searches names, commanders and tags", () => {
    const by = (q: string) => visibleDecks(decks, { ...EMPTY_FILTERS, q }).map((d) => d.id);
    expect(by("edgar")).toEqual(["edgar"]);
    expect(by("hedron")).toEqual(["mine"]);
    expect(by("ramp")).toEqual(["aesi"]);
  });

  it("ignores case and surrounding space", () => {
    expect(visibleDecks(decks, { ...EMPTY_FILTERS, q: "  EDGAR " })).toHaveLength(1);
  });

  it("filters colour as an AND", () => {
    // Three colours means decks that play all three, which is the question
    // somebody filtering by colour is asking.
    const by = (colours: string[]) =>
      visibleDecks(decks, { ...EMPTY_FILTERS, colours }).map((d) => d.id);
    expect(by(["G"])).toEqual(["aesi"]);
    expect(by(["W", "B"])).toEqual(["edgar"]);
    expect(by(["G", "R"])).toEqual([]);
  });

  it("filters by source", () => {
    const by = (source: "all" | "precon" | "moxfield") =>
      visibleDecks(decks, { ...EMPTY_FILTERS, source }).map((d) => d.id);
    expect(by("moxfield")).toEqual(["mine"]);
    expect(by("precon")).toEqual(["aesi", "edgar"]);
  });

  it("combines every filter", () => {
    const shown = visibleDecks(decks, {
      ...EMPTY_FILTERS,
      q: "a",
      colours: ["R"],
      source: "precon",
    });
    expect(shown.map((d) => d.id)).toEqual(["edgar"]);
  });

  it("falls back to name when it has no ratings to sort by", () => {
    const shown = visibleDecks(decks, { ...EMPTY_FILTERS, sort: "speed" });
    expect(shown.map((d) => d.id)).toEqual(["aesi", "edgar", "mine"]);
  });

  it("sorts by a rating when one is available", () => {
    const ratings: Record<string, Record<string, number>> = {
      aesi: { speed: 2, complexity: 3, pilot: 2 },
      edgar: { speed: 4, complexity: 2, pilot: 2 },
    };
    const shown = visibleDecks(decks, { ...EMPTY_FILTERS, sort: "speed" }, (id) => ratings[id]);
    expect(shown.map((d) => d.id)).toEqual(["edgar", "aesi", "mine"]);
  });

  it("sorts an unrated deck last rather than first", () => {
    // An imported deck has no ratings, and calling it the fastest deck in the
    // catalogue would be the one lie on the screen.
    const ratings: Record<string, Record<string, number>> = { aesi: { pilot: 4 } };
    const shown = visibleDecks(decks, { ...EMPTY_FILTERS, sort: "pilot" }, (id) => ratings[id]);
    expect(shown[shown.length - 1].id).not.toBe("aesi");
    expect(shown.map((d) => d.id).slice(1)).toEqual(["edgar", "mine"]);
  });

  it("inverts the pilot sort -- easiest is the lowest number", () => {
    const ratings: Record<string, Record<string, number>> = {
      aesi: { pilot: 4 },
      edgar: { pilot: 1 },
      mine: { pilot: 2 },
    };
    const shown = visibleDecks(decks, { ...EMPTY_FILTERS, sort: "pilot" }, (id) => ratings[id]);
    expect(shown.map((d) => d.id)).toEqual(["edgar", "mine", "aesi"]);
  });

  it("does not mutate the list it was handed", () => {
    const original = decks.map((d) => d.id);
    visibleDecks(decks, { ...EMPTY_FILTERS, sort: "speed" });
    expect(decks.map((d) => d.id)).toEqual(original);
  });
});

describe("pod codes", () => {
  it.each([
    ["gyre-8412", "GYRE-8412"],
    ["GYRE8412", "GYRE-8412"],
    ["  gyre 8412 ", "GYRE-8412"],
    ["Gyre_8412", "GYRE-8412"],
  ])("normalises %s", (typed, want) => {
    expect(normaliseCode(typed)).toBe(want);
  });

  it("leaves a half-typed code alone rather than mangling it", () => {
    expect(normaliseCode("GY")).toBe("GY");
    expect(normaliseCode("")).toBe("");
  });

  it("only calls a full code submittable", () => {
    expect(looksLikeCode("gyre-8412")).toBe(true);
    expect(looksLikeCode("GYRE8412")).toBe(true);
    expect(looksLikeCode("GYRE-84")).toBe(false);
    expect(looksLikeCode("GYRE")).toBe(false);
    expect(looksLikeCode("")).toBe(false);
  });
});
