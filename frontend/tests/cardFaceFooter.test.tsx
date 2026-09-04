/**
 * The counters and the P/T do not share a line.
 *
 * They used to. `.face__footer` was one flex row -- keywords, counters, spacer,
 * P/T -- which is fine until a creature is actually carrying counters. A board
 * card is about a hundred pixels wide, and "+1/+1 x3" beside a stun counter has
 * spent all of it before the P/T asks for its corner, so the number was pushed
 * off the card exactly when counters made it worth reading.
 *
 * `CardPreview` reached the same arrangement one size up and says so in its own
 * comment; this is that decision on the small face. The claim is structural
 * rather than visual, because jsdom lays nothing out: the counters are a sibling
 * of the row the P/T is in, never inside it.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CardFace } from "../src/components/game/CardFace";
import { card } from "./fixtures";

afterEach(cleanup);

const plain = card({
  card_id: "t_bear",
  name: "Test Bear",
  power: 2,
  toughness: 2,
  zone: "battlefield",
});

const countered = card({
  ...plain,
  counters: { "+1/+1": 3, stun: 1 },
});

describe("a creature with counters on it", () => {
  it("puts the counters on their own line", () => {
    const { container } = render(<CardFace card={countered} />);
    const counters = container.querySelector(".face__counters");
    const row = container.querySelector(".face__footrow");
    expect(counters).not.toBeNull();
    expect(row).not.toBeNull();
    expect(row?.contains(counters as Node)).toBe(false);
  });

  it("keeps the P/T, which is what used to be pushed off", () => {
    const { container } = render(<CardFace card={countered} />);
    const stats = container.querySelector(".face__footrow .face__stats");
    expect(stats?.textContent).toContain("2");
  });

  it("draws every badge it was given", () => {
    const { container } = render(<CardFace card={countered} />);
    expect(container.querySelectorAll(".face__counters .counter-badge").length).toBe(2);
  });
});

describe("a creature with no counters", () => {
  it("draws no counter line at all", () => {
    // The line is not a reserved slot: an empty one would eat a card's height
    // on every creature on the board to serve the few that have counters.
    const { container } = render(<CardFace card={plain} />);
    expect(container.querySelector(".face__counters")).toBeNull();
  });

  it("still shows the P/T", () => {
    const { container } = render(<CardFace card={plain} />);
    expect(container.querySelector(".face__stats")?.textContent).toContain("2");
  });
});
