/**
 * A long-press reads the card under the finger -- the phone's way into the
 * full card view, which a desktop opens with a right-click and a Deck with Y.
 *
 * The two things that would make it worse than nothing: a mouse button held
 * down opening it (a mouse has hover and a right-click already), and the tap
 * that ends the hold going on to PLAY the card it just read.
 */

import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { HOLD_MS, HOLD_SLOP, oidAt, useLongPress } from "../src/input/longPress";

// jsdom has no `PointerEvent`, so `fireEvent.pointerDown` builds a bare `Event`
// and drops `pointerType` and the coordinates the hook reads.
beforeAll(() => {
  if (typeof window.PointerEvent === "function") return;
  class PointerEventShim extends MouseEvent {
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerType = init.pointerType ?? "";
    }
  }
  window.PointerEvent = PointerEventShim as unknown as typeof PointerEvent;
});

function Harness({ onHold, onClick }: { onHold: (oid: number) => void; onClick: () => void }) {
  const press = useLongPress(onHold);
  return (
    <div {...press}>
      {/* biome-ignore lint/a11y/noStaticElementInteractions: a stand-in for a card on the board, which takes a click without being a control; the hook under test is what matters here. */}
      <div data-oid="42" data-testid="card" onClick={onClick}>
        <span data-testid="inside">art</span>
      </div>
      <div data-preview-oid="7" data-oid="99" data-testid="plinth" />
      <div data-testid="nothing" />
    </div>
  );
}

describe("oidAt", () => {
  it("finds the card an element is part of", () => {
    const { getByTestId } = render(
      <Harness onHold={() => undefined} onClick={() => undefined} />,
    );
    expect(oidAt(getByTestId("inside"))).toBe(42);
    expect(oidAt(getByTestId("nothing"))).toBeNull();
    expect(oidAt(null)).toBeNull();
  });

  it("prefers what a surface says it would preview over its own id", () => {
    const { getByTestId } = render(
      <Harness onHold={() => undefined} onClick={() => undefined} />,
    );
    expect(oidAt(getByTestId("plinth"))).toBe(7);
  });
});

describe("useLongPress", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function press(el: Element, pointerType: string, x = 10, y = 10) {
    fireEvent.pointerDown(el, { pointerType, clientX: x, clientY: y });
  }

  it("reads the card after a still touch of HOLD_MS", () => {
    const onHold = vi.fn();
    const { getByTestId } = render(<Harness onHold={onHold} onClick={() => undefined} />);
    press(getByTestId("inside"), "touch");
    act(() => vi.advanceTimersByTime(HOLD_MS - 1));
    expect(onHold).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onHold).toHaveBeenCalledWith(42);
  });

  it("is not a mouse gesture", () => {
    const onHold = vi.fn();
    const { getByTestId } = render(<Harness onHold={onHold} onClick={() => undefined} />);
    press(getByTestId("inside"), "mouse");
    act(() => vi.advanceTimersByTime(HOLD_MS * 2));
    expect(onHold).not.toHaveBeenCalled();
  });

  it("is cancelled by a lift or a drift, which is a tap or a scroll", () => {
    const onHold = vi.fn();
    const { getByTestId } = render(<Harness onHold={onHold} onClick={() => undefined} />);
    const card = getByTestId("inside");

    press(card, "touch");
    fireEvent.pointerUp(card, { pointerType: "touch" });
    act(() => vi.advanceTimersByTime(HOLD_MS * 2));

    press(card, "touch", 10, 10);
    fireEvent.pointerMove(card, {
      pointerType: "touch",
      clientX: 10 + HOLD_SLOP + 1,
      clientY: 10,
    });
    act(() => vi.advanceTimersByTime(HOLD_MS * 2));

    expect(onHold).not.toHaveBeenCalled();
  });

  it("swallows the click the finger's lift delivers, so reading never plays", () => {
    const onHold = vi.fn();
    const onClick = vi.fn();
    const { getByTestId } = render(<Harness onHold={onHold} onClick={onClick} />);
    const card = getByTestId("card");

    press(card, "touch");
    act(() => vi.advanceTimersByTime(HOLD_MS));
    fireEvent.click(card);
    expect(onHold).toHaveBeenCalledOnce();
    expect(onClick).not.toHaveBeenCalled();

    // ...once. The next deliberate tap goes through.
    fireEvent.click(card);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("does nothing over something that is not a card", () => {
    const onHold = vi.fn();
    const { getByTestId } = render(<Harness onHold={onHold} onClick={() => undefined} />);
    press(getByTestId("nothing"), "touch");
    act(() => vi.advanceTimersByTime(HOLD_MS * 2));
    expect(onHold).not.toHaveBeenCalled();
  });
});
