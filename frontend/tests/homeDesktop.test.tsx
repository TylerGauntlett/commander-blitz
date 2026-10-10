/**
 * The front door on the desktop.
 *
 * Three cards still, but the third is Online rather than Join: pods with
 * friends live on the hosted site, and the local server has nobody to join.
 * Offline, the card stays a stop and says why; online, its hold takes a code
 * or goes with none -- both through `onPlayOnline`, never `onJoin`.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HomeScreen } from "../src/components/lobby/HomeScreen";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad } from "../src/input/pad";

type Props = Parameters<typeof HomeScreen>[0];

function mount(overrides: Partial<Props> = {}) {
  const props: Props = {
    deckCount: 3,
    busy: false,
    error: null,
    onCreate: vi.fn(),
    onJoin: vi.fn(),
    onPlayOnline: vi.fn(),
    ...overrides,
  };
  render(<HomeScreen {...props} />);
  return props;
}

/** The row opens on Play; a click on another card selects it, a second presses. */
function pressCard(testId: string) {
  fireEvent.click(screen.getByTestId(testId));
  fireEvent.click(screen.getByTestId(testId));
}

afterEach(() => {
  resetPad();
  resetInputMode();
});

describe("the site", () => {
  it("is unchanged: three cards, Join joins, nothing is greyed", () => {
    const props = mount();
    expect(screen.getByTestId("join-pod").textContent).toContain("Join");
    expect(screen.getByTestId("join-pod").getAttribute("aria-disabled")).toBeNull();
    expect(screen.queryByTestId("return-local")).toBeNull();

    pressCard("join-pod");
    fireEvent.change(screen.getByTestId("pod-code"), { target: { value: "gyre-8412" } });
    fireEvent.click(screen.getByTestId("join-go"));
    expect(props.onJoin).toHaveBeenCalledWith("GYRE-8412");
    expect(props.onPlayOnline).not.toHaveBeenCalled();
    expect(screen.queryByTestId("play-online")).toBeNull();
  });

  it("offers the way back to the app only when the desktop sent you", () => {
    const onReturnLocal = vi.fn();
    mount({ onReturnLocal });
    fireEvent.click(screen.getByTestId("return-local"));
    expect(onReturnLocal).toHaveBeenCalled();
  });
});

describe("the desktop, offline", () => {
  it("keeps the card in the row, dimmed, and says why when pressed", () => {
    const props = mount({ mode: "desktop", online: false });
    const card = screen.getByTestId("join-pod");
    expect(card.textContent).toContain("Online");
    expect(card.getAttribute("aria-disabled")).toBe("true");
    expect(card.className).toContain("door__card--off");

    pressCard("join-pod");
    expect(screen.queryByTestId("join-hold")).toBeNull();
    expect(screen.getByTestId("offline-note").textContent).toMatch(/Offline/);
    expect(props.onPlayOnline).not.toHaveBeenCalled();
    expect(props.onJoin).not.toHaveBeenCalled();
  });

  it("still deals a solo pod: Play is the local server's", () => {
    const props = mount({ mode: "desktop", online: false });
    fireEvent.click(screen.getByTestId("create-pod"));
    expect(props.onCreate).toHaveBeenCalled();
  });
});

describe("the desktop, online", () => {
  it("is not greyed and the hold takes a code to the site", () => {
    const props = mount({ mode: "desktop", online: true });
    expect(screen.getByTestId("join-pod").getAttribute("aria-disabled")).toBeNull();

    pressCard("join-pod");
    expect(screen.getByTestId("join-hold").getAttribute("aria-label")).toBe("Play online");
    fireEvent.change(screen.getByTestId("pod-code"), { target: { value: "GYRE-8412" } });
    fireEvent.click(screen.getByTestId("join-go"));
    expect(props.onPlayOnline).toHaveBeenCalledWith("GYRE-8412");
    expect(props.onJoin).not.toHaveBeenCalled();
  });

  it("or goes with no code at all", () => {
    const props = mount({ mode: "desktop", online: true });
    pressCard("join-pod");
    fireEvent.click(screen.getByTestId("play-online"));
    expect(props.onPlayOnline).toHaveBeenCalledWith();
  });

  it("drops the offline note the moment the connection returns", () => {
    const props = mount({ mode: "desktop", online: false });
    pressCard("join-pod");
    expect(screen.getByTestId("offline-note")).toBeTruthy();
    // Re-render with the connection back: the note has nothing left to say.
    render(<HomeScreen {...props} mode="desktop" online={true} />);
    expect(screen.queryAllByTestId("offline-note")).toHaveLength(1);
  });
});
