/**
 * The full-screen card read, as a component.
 *
 * `CardHold` owns no state and no dismissal: it renders when it is given a
 * card and renders nothing when it is not, and `Table` decides which. What it
 * promises is the shape the input layer relies on -- a `data-modal-root` so the
 * ring stays put under a surface with nothing to press, and one big
 * `StaticCard` rather than a `Card`, so framer never animates the board's copy
 * into this one. These characterise that contract as it stands (TECH_DEBT
 * CG-02, FB-08 lives in `Table`'s `Y` binding, not here).
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CardHold } from "../src/components/game/CardHold";
import * as pool from "../src/testing/cards";

afterEach(cleanup);

describe("CardHold", () => {
  it("renders nothing without a card", () => {
    const { container } = render(<CardHold card={null} />);
    expect(container.innerHTML).toBe("");
    expect(document.querySelector("[data-testid='card-hold']")).toBeNull();
  });

  it("renders the card big, inside a modal root, and announces it", () => {
    render(<CardHold card={pool.llanowarElves({ oid: 7 })} />);
    const hold = document.querySelector<HTMLElement>("[data-testid='card-hold']");
    expect(hold).not.toBeNull();
    expect(hold?.className).toBe("hold hold--card");
    expect(hold?.hasAttribute("data-modal-root")).toBe(true);
    expect(hold?.getAttribute("aria-live")).toBe("polite");
    // One card, the big variant, and not the board's animated `Card`.
    const faces = hold?.querySelectorAll(".hold__card .card") ?? [];
    expect(faces.length).toBe(1);
    expect(faces[0].className).toMatch(/card--big/);
    expect(hold?.textContent).toContain("Llanowar Elves");
  });

  it("carries no stop and no action id: it is a picture, not a control", () => {
    render(<CardHold card={pool.llanowarElves({ oid: 7 })} />);
    expect(document.querySelectorAll("[data-stop]").length).toBe(0);
    expect(document.querySelectorAll("[data-action-id]").length).toBe(0);
  });

  it("follows the card it is given, and goes when it is taken away", () => {
    const { rerender } = render(<CardHold card={pool.llanowarElves({ oid: 7 })} />);
    rerender(<CardHold card={pool.aesi({ oid: 900 })} />);
    expect(document.querySelector("[data-testid='card-hold']")?.textContent).toContain("Aesi");
    rerender(<CardHold card={null} />);
    expect(document.querySelector("[data-testid='card-hold']")).toBeNull();
  });
});
