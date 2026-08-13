/**
 * The graveyard modal, and the notes on it.
 *
 * Text and DOM contract only -- no layout, which is what jsdom can honestly
 * see. That the note sits *under* the card rather than over its art is a
 * cascade question and belongs to the story.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CardView } from "../src/api/types";
import { ZonePeek } from "../src/components/game/ZonePeek";
import { useUiStore } from "../src/state/uiStore";
import { card, gameView, player } from "./fixtures";

afterEach(() => {
  cleanup();
  useUiStore.setState({ images: null, peek: null });
});

/** Seat 0 with `graveyard` in the bin and `exile` off to one side. */
function viewWith(graveyard: CardView[], exile: CardView[] = []) {
  return gameView({
    players: [player({ pid: 0, graveyard, exile }), player({ pid: 1 })],
  });
}

const BEARS = card({
  oid: 4,
  card_id: "grizzly_bears",
  name: "Grizzly Bears",
  zone: "graveyard",
});

function open(zone: "graveyard" | "exile" = "graveyard") {
  useUiStore.setState({ peek: { pid: 0, zone } });
}

describe("ZonePeek removal notes", () => {
  it("says how a card got into the graveyard", () => {
    open();
    const view = render(
      <ZonePeek
        state={viewWith([BEARS])}
        reasons={new Map([[4, "Destroyed by Swords to Plowshares"]])}
      />,
    );
    expect(view.getByTestId("peek-note").textContent).toBe("Destroyed by Swords to Plowshares");
  });

  it("renders nothing extra for a card it has no story for", () => {
    // A creature already in the graveyard at the start of the game, or one
    // milled before this client connected: no note is better than a guess.
    open();
    const view = render(<ZonePeek state={viewWith([BEARS])} reasons={new Map()} />);
    expect(view.queryByTestId("peek-note")).toBeNull();
  });

  it("works with no reasons supplied at all", () => {
    // The prop is optional so every existing caller and story still mounts.
    open();
    const view = render(<ZonePeek state={viewWith([BEARS])} />);
    expect(view.queryByTestId("peek-note")).toBeNull();
    expect(view.getByTestId("zone-peek")).toBeTruthy();
  });

  it("annotates exile too", () => {
    open("exile");
    const exiled = card({ oid: 7, name: "Sol Ring", zone: "exile" });
    const view = render(
      <ZonePeek state={viewWith([], [exiled])} reasons={new Map([[7, "Exiled by Ashiok"]])} />,
    );
    expect(view.getByTestId("peek-note").textContent).toBe("Exiled by Ashiok");
  });

  it("does not annotate the command zone or a hand", () => {
    // Nothing in either arrived by leaving the battlefield in a way worth
    // captioning, and a commander bounced home would otherwise read as a death.
    useUiStore.setState({ peek: { pid: 0, zone: "command" } });
    const cmd = card({ oid: 9, name: "Aesi", zone: "command", is_commander: true });
    const state = gameView({
      players: [player({ pid: 0, command: [cmd] }), player({ pid: 1 })],
    });
    const view = render(
      <ZonePeek state={state} reasons={new Map([[9, "Destroyed by Murder"]])} />,
    );
    expect(view.queryByTestId("peek-note")).toBeNull();
  });

  it("attaches the note to the copy on top of a collapsed stack", () => {
    // Eight Swamps collapse to one entry and did not all die the same way, so
    // the note describes the card actually being shown and claims nothing
    // about the ones underneath it.
    open();
    const swamps = [0, 1, 2].map((i) =>
      card({ oid: 20 + i, card_id: "swamp", name: "Swamp", zone: "graveyard" }),
    );
    const view = render(
      <ZonePeek
        state={viewWith(swamps)}
        reasons={
          new Map([
            [20, "Destroyed by Armageddon"],
            [21, "Sacrificed to Zuran Orb"],
          ])
        }
      />,
    );
    // One entry, therefore one note -- not three.
    expect(view.getAllByTestId("peek-note")).toHaveLength(1);
  });
});
