/**
 * The art band on a real card face.
 *
 * `CardFace` reads the art map straight out of `uiStore`, deliberately: it is
 * rendered bare in `components.test.tsx` with no providers around it, and it
 * must keep working that way. That is why the map is *not* held in react-query
 * context, and why the default of `null` produces the pre-art layout exactly.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CardFace } from "../src/components/game/CardFace";
import type { ImageMap } from "../src/logic/cardArt";
import { useUiStore } from "../src/state/uiStore";
import { card } from "./fixtures";

function seed(images: ImageMap) {
  useUiStore.setState({ images });
}

beforeEach(() => seed(null));
afterEach(() => {
  cleanup();
  seed(null);
});

const bear = card({ card_id: "t_bear", name: "Test Bear" });
const forest = card({
  card_id: "forest",
  name: "Forest",
  type_line: "Basic Land - Forest",
  types: ["Land"],
  supertypes: ["Basic"],
  produces: ["G"],
  power: null,
  toughness: null,
});

describe("before the map loads", () => {
  it("draws no art band at all", () => {
    // Not the "no art" plate. Flashing a hatched placeholder on every card
    // during the first paint reads as a broken board.
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".face__art")).toBeNull();
  });

  it("still shows a land its mana symbols", () => {
    // The pre-art layout, intact -- which is also what a server with no images
    // renders forever.
    const { container } = render(<CardFace card={forest} />);
    const watermark = container.querySelector(".face__watermark");
    expect(watermark).not.toBeNull();
    // Scoped to the watermark: "G" also appears in the mana cost, and a bare
    // text query matches both.
    expect(
      [...(watermark?.querySelectorAll(".watermark-pip") ?? [])].map((n) => n.textContent),
    ).toEqual(["G"]);
  });
});

describe("when the card has art", () => {
  beforeEach(() =>
    seed({
      t_bear: { card_id: "t_bear", art: "/art/t_bear.jpg", artist: "Someone" },
      forest: { card_id: "forest", art: "/art/forest.jpg", artist: "Someone" },
    }),
  );

  it("renders the image from this server", () => {
    const { container } = render(<CardFace card={bear} />);
    const img = container.querySelector<HTMLImageElement>(".face__art img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src")).toBe("/art/t_bear.jpg");
  });

  it("marks the art band as ready", () => {
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".face__art")?.getAttribute("data-art")).toBe("ready");
  });

  it("gives the image empty alt text", () => {
    // The card's name is already on the card; announcing the illustration
    // again is noise to a screen reader.
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".face__art img")?.getAttribute("alt")).toBe("");
  });

  it("moves a land's mana symbols on top of the art", () => {
    const { container } = render(<CardFace card={forest} />);
    expect(container.querySelector(".face__art .watermark-row")).not.toBeNull();
    // And out of the standalone block that replaced the art before.
    expect(container.querySelector(".face__watermark")).toBeNull();
  });

  it("still renders rules text alongside the art", () => {
    const { container } = render(
      <CardFace card={card({ card_id: "t_bear", oracle_text: "Trample." })} variant="detail" />,
    );
    expect(container.querySelector(".face__art")).not.toBeNull();
    expect(container.querySelector(".face__rules")).not.toBeNull();
    // `face--detail` is what caps the band so the text keeps its room.
    expect(container.querySelector(".face--detail")).not.toBeNull();
  });
});

describe("when the card has no printing", () => {
  beforeEach(() => seed({ t_bear: null, forest: null }));

  it("draws the plate rather than a broken image", () => {
    const { container } = render(<CardFace card={bear} />);
    const band = container.querySelector(".face__art--none");
    expect(band).not.toBeNull();
    expect(band?.getAttribute("data-art")).toBe("none");
    expect(container.querySelector(".face__art img")).toBeNull();
    expect(screen.getByText("no art")).toBeTruthy();
  });

  it("keeps the name and type glyph, which is what identifies it", () => {
    render(<CardFace card={bear} />);
    expect(screen.getByText("Test Bear")).toBeTruthy();
  });

  it("keeps a land's mana symbols over the plate", () => {
    // A Forest with no art is still obviously a Forest; the symbol is doing
    // more work here than the illustration would have.
    const { container } = render(<CardFace card={forest} />);
    expect(container.querySelector(".face__art--none .watermark-row")).not.toBeNull();
  });
});
