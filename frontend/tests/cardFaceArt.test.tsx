/**
 * The art layer on a real card face.
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
  it("draws no art layer at all", () => {
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
    // `data-symbol`, not `textContent`: these are Scryfall's real symbols drawn
    // as images, so there is no letter to read back.
    expect(
      [...(watermark?.querySelectorAll(".watermark-pip") ?? [])].map((n) =>
        n.getAttribute("data-symbol"),
      ),
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
    const img = container.querySelector<HTMLImageElement>(".face__art-img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src")).toBe("/art/t_bear.jpg");
  });

  it("marks the art as ready", () => {
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".face__art")?.getAttribute("data-art")).toBe("ready");
  });

  it("gives the image empty alt text", () => {
    // The card's name is already on the card; announcing the illustration
    // again is noise to a screen reader.
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".face__art-img")?.getAttribute("alt")).toBe("");
  });

  it("moves a land's mana symbols on top of the art", () => {
    const { container } = render(<CardFace card={forest} />);
    expect(container.querySelector(".face__art .watermark-row")).not.toBeNull();
    // And out of the standalone block that replaced the art before.
    expect(container.querySelector(".face__watermark")).toBeNull();
  });

  it("keeps the illustration tellable from the symbols drawn over it", () => {
    // Both are `<img>` inside `.face__art` now that the symbols are real
    // artwork, so `.face__art img` means "either". `e2e/art.spec.ts` counts
    // decoded illustrations and would have passed on a board with no card art
    // at all as long as one Forest was on it -- hence the separate class.
    const { container } = render(<CardFace card={forest} />);
    const all = container.querySelectorAll(".face__art img");
    expect(all.length).toBeGreaterThan(1);
    expect(container.querySelectorAll(".face__art-img")).toHaveLength(1);
    expect(container.querySelector(".face__art-img")?.getAttribute("src")).toBe(
      "/art/forest.jpg",
    );
  });

  it("still renders rules text over the art", () => {
    const { container } = render(
      <CardFace card={card({ card_id: "t_bear", oracle_text: "Trample." })} variant="detail" />,
    );
    expect(container.querySelector(".face__art")).not.toBeNull();
    expect(container.querySelector(".face__rules")).not.toBeNull();
    // The art no longer has a band to be capped to; the rules box sits on the
    // foot scrim, which is what `.face--detail` sizes.
    expect(container.querySelector(".face--detail")).not.toBeNull();
    expect(container.querySelector(".face__foot .face__rules")).not.toBeNull();
  });
});

describe("the scrims", () => {
  // Structural, not visual: jsdom applies no stylesheet, so what can be
  // asserted here is that every run of text is inside a band that has a scrim,
  // rather than loose over the illustration. `tests/palette.test.ts` checks the
  // gradients themselves and `e2e/greyscale.spec.ts` checks what resolved.
  it("puts the name and cost in the head", () => {
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".face__head .face__name")).not.toBeNull();
    expect(container.querySelector(".face__head .face__glyph")).not.toBeNull();
    expect(container.querySelector(".face__head .face__cost")).not.toBeNull();
  });

  it("puts the type line, rules and footer in the foot", () => {
    const { container } = render(
      <CardFace card={card({ card_id: "t_bear", oracle_text: "Trample." })} variant="detail" />,
    );
    expect(container.querySelector(".face__foot .face__type")).not.toBeNull();
    expect(container.querySelector(".face__foot .face__footer")).not.toBeNull();
  });

  it("gives the cost a row of its own, not the title's", () => {
    // The point of the direction: a name can be as long as it likes and never
    // meets its own mana cost.
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".face__title .face__cost")).toBeNull();
  });
});

describe("a land that taps for no colour", () => {
  // Terramorphic Expanse. `produces` is empty, so every design that leans on the
  // produced symbol leaves the one land that is actually interesting with no
  // mark at all -- which is the case worth having a test for.
  const expanse = card({
    card_id: "terramorphic_expanse",
    name: "Terramorphic Expanse",
    type_line: "Land",
    types: ["Land"],
    produces: [],
    power: null,
    toughness: null,
  });

  beforeEach(() => seed({ terramorphic_expanse: null }));

  it("still gets a mark", () => {
    const { container } = render(<CardFace card={expanse} />);
    expect(container.querySelector(".watermark-none")).not.toBeNull();
  });

  it("does not claim to produce a colour", () => {
    // Deliberately not `.watermark-pip`: it is not a mana symbol, and the specs
    // that read produced colours off that class would have to special-case it.
    const { container } = render(<CardFace card={expanse} />);
    expect(container.querySelector(".watermark-pip")).toBeNull();
  });

  it("leaves a non-land alone", () => {
    const { container } = render(<CardFace card={bear} />);
    expect(container.querySelector(".watermark-none")).toBeNull();
    expect(container.querySelector(".watermark-row")).toBeNull();
  });
});

describe("when the card has no printing", () => {
  beforeEach(() => seed({ t_bear: null, forest: null }));

  it("draws the plate rather than a broken image", () => {
    const { container } = render(<CardFace card={bear} />);
    const band = container.querySelector(".face__art--none");
    expect(band).not.toBeNull();
    expect(band?.getAttribute("data-art")).toBe("none");
    expect(container.querySelector(".face__art-img")).toBeNull();
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
