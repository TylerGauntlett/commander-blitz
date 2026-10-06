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

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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

/**
 * The pointer's way out.
 *
 * A pad puts the hold down with any press; a mouse opens it now (right-click,
 * or `i` over a card) and has no "any press", so the hold has to take a click
 * itself -- and the click must never fall through to the board card under it.
 */
describe("CardHold, from a mouse", () => {
  it("is a dialog named for its card", () => {
    render(<CardHold card={pool.aesi({ oid: 900 })} onClose={() => undefined} />);
    const hold = document.querySelector<HTMLElement>("[data-testid='card-hold']");
    expect(hold?.getAttribute("role")).toBe("dialog");
    expect(hold?.getAttribute("aria-modal")).toBe("true");
    expect(hold?.getAttribute("aria-label")).toMatch(/Aesi/);
  });

  it("closes on a click outside the card", () => {
    const onClose = vi.fn();
    render(<CardHold card={pool.aesi({ oid: 900 })} onClose={onClose} />);
    fireEvent.click(document.querySelector("[data-testid='card-hold']") as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("stays open on a click on the card itself", () => {
    // The card may scroll on a very long one; grabbing its scrollbar is not
    // asking to close it.
    const onClose = vi.fn();
    render(<CardHold card={pool.aesi({ oid: 900 })} onClose={onClose} />);
    fireEvent.click(document.querySelector(".hold__card .card") as HTMLElement);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes from its Close button, once", () => {
    const onClose = vi.fn();
    const { getByTestId } = render(
      <CardHold card={pool.aesi({ oid: 900 })} onClose={onClose} />,
    );
    fireEvent.click(getByTestId("card-hold-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on a right-click, and keeps the browser's menu off the card", () => {
    const onClose = vi.fn();
    render(<CardHold card={pool.aesi({ oid: 900 })} onClose={onClose} />);
    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    (document.querySelector("[data-testid='card-hold']") as HTMLElement).dispatchEvent(event);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("gives the ring nothing to land on, Close button included", () => {
    // On a pad any press is still the way out; a stop in here would pull the
    // ring off the board for a surface it has no business on.
    render(<CardHold card={pool.aesi({ oid: 900 })} onClose={() => undefined} />);
    expect(document.querySelectorAll("[data-stop]").length).toBe(0);
  });
});
