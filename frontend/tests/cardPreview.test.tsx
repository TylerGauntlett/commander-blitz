/**
 * The right-hand rail: the hovered card, big enough to read.
 *
 * This panel had no test at all, which `docs/mockup-fidelity.md` lists as an
 * open defect -- and it is the surface the commander plinth points at, so it
 * gets one now. The cases worth holding are the two that were broken rather than
 * the rendering, which the card face's own tests already cover.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CardView } from "../src/api/types";
import { CardPreview } from "../src/components/game/CardPreview";
import { useUiStore } from "../src/state/uiStore";
import { card, gameView, player, stackItem } from "./fixtures";

afterEach(() => {
  cleanup();
  useUiStore.setState({ hoveredOid: null, images: null });
});

function commander(overrides: Partial<CardView> = {}): CardView {
  return card({
    oid: 99,
    card_id: "aesi",
    name: "Aesi, Tyrant of Gyre Strait",
    mana_cost: "{4}{G}{U}",
    is_commander: true,
    zone: "command",
    ...overrides,
  });
}

describe("the preview rail", () => {
  it("says what to do with it when nothing is hovered", () => {
    const { getByTestId } = render(<CardPreview state={gameView()} />);
    expect(getByTestId("card-preview").textContent).toContain("Hover a card to read it");
  });

  it("draws the commander a plinth hover named", () => {
    // The plinth deliberately is not a card face -- this rail is where the full
    // card lives, and the whole arrangement depends on this resolving.
    useUiStore.setState({ hoveredOid: 99 });
    const state = gameView({
      players: [player({ pid: 0, command: [commander()] }), player({ pid: 1, hand: null })],
    });
    const { getByTestId } = render(<CardPreview state={state} />);
    expect(getByTestId("card-preview").textContent).toContain("Aesi, Tyrant of Gyre Strait");
  });

  it("draws a commander that is mid-cast, on the stack", () => {
    // `commandersOf` keeps a commander on the plinth while it is on the stack --
    // "casting a commander is the whole point of the dock". `findCard` did not
    // search the stack, so hovering it during exactly that beat blanked the rail.
    useUiStore.setState({ hoveredOid: 99 });
    const state = gameView({
      players: [player({ pid: 0, command: [] }), player({ pid: 1, hand: null })],
      stack: [stackItem({ card: commander({ zone: "stack" }) })],
    });
    const { getByTestId } = render(<CardPreview state={state} />);
    const text = getByTestId("card-preview").textContent ?? "";
    expect(text).toContain("Aesi, Tyrant of Gyre Strait");
    expect(text).not.toContain("Hover a card to read it");
  });

  it("falls back to the idle line for an oid it cannot see", () => {
    // Hidden zones have no view to return. An empty panel beats a crash.
    useUiStore.setState({ hoveredOid: 4242 });
    const { getByTestId } = render(<CardPreview state={gameView()} />);
    expect(getByTestId("card-preview").textContent).toContain("Hover a card to read it");
  });

  it("credits the illustrator once the image map has arrived", () => {
    useUiStore.setState({
      hoveredOid: 99,
      images: { aesi: { card_id: "aesi", art: "/art/aesi.jpg", artist: "Chris Rahn" } },
    });
    const state = gameView({
      players: [player({ pid: 0, command: [commander()] }), player({ pid: 1, hand: null })],
    });
    const { getByTestId } = render(<CardPreview state={state} />);
    expect(getByTestId("card-preview").textContent).toContain("Chris Rahn");
  });
});
