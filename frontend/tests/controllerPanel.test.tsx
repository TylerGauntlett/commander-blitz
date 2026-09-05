/**
 * The controller diagnosis, on screen.
 *
 * `causes()` is the part worth holding still: it turns the three facts
 * `padDiagnostics` reports into an ordered list of things to try, and the ORDER
 * is the point -- secure context first, because every Steam-side fix is wasted
 * until the page is served over https, and the page-focus one last, because it
 * is the cheapest to rule out. The render is pinned around it (TECH_DEBT CG-02).
 */

import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ControllerPanel, causes } from "../src/components/ui/ControllerPanel";

type Diag = Parameters<typeof causes>[0];

const diag = (over: Partial<Diag> = {}): Diag => ({
  listening: false,
  connected: false,
  polling: false,
  supported: true,
  secure: true,
  focused: true,
  pads: [],
  bound: {},
  ...over,
});

describe("causes()", () => {
  it("always offers the two Steam-side fixes, in that order", () => {
    expect(causes(diag()).map((c) => c.title)).toEqual([
      "Steam is sending a keyboard, not a gamepad",
      "A Flatpak browser cannot reach the device",
    ]);
  });

  it("puts the secure context first, because nothing else helps until it is fixed", () => {
    const titles = causes(diag({ secure: false })).map((c) => c.title);
    expect(titles[0]).toBe("This page is not a secure context");
    expect(titles).toHaveLength(3);
  });

  it("treats a missing Gamepad API the same as an insecure page", () => {
    expect(causes(diag({ supported: false }))[0].title).toBe(
      "This page is not a secure context",
    );
  });

  it("adds the focus cause last, and only when the page is not focused", () => {
    const titles = causes(diag({ focused: false })).map((c) => c.title);
    expect(titles.at(-1)).toBe("The page is not focused");
    expect(causes(diag({ focused: true })).some((c) => /focused/.test(c.title))).toBe(false);
  });

  it("can name all four at once", () => {
    expect(causes(diag({ secure: false, focused: false }))).toHaveLength(4);
  });
});

describe("<ControllerPanel />", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    (navigator as unknown as { getGamepads: () => unknown[] }).getGamepads = () => [];
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("says no controller was found, explains why, and promises the keyboard path", () => {
    render(<ControllerPanel />);
    const status = document.querySelector("[data-testid='controller-status']");
    expect(status?.textContent).toContain("No controller detected");
    expect(document.querySelectorAll(".ctrl__cause").length).toBeGreaterThan(0);
    expect(document.querySelector(".ctrl__foot")?.textContent).toMatch(/d-pad, Enter and Esc/);
    // The same scheme picker the in-game settings menu uses.
    expect(document.querySelector("[data-testid='controller-panel'] .scheme")).not.toBeNull();
  });

  it("lists the pads once one appears, and drops the explanations", () => {
    render(<ControllerPanel />);
    (navigator as unknown as { getGamepads: () => unknown[] }).getGamepads = () => [
      {
        id: "Steam Virtual Gamepad",
        index: 0,
        connected: true,
        buttons: [],
        axes: [],
        mapping: "standard",
      },
    ];
    act(() => {
      vi.advanceTimersByTime(1100);
    });
    expect(document.querySelectorAll(".ctrl__pad").length).toBe(1);
    expect(document.querySelectorAll(".ctrl__cause").length).toBe(0);
  });

  it("stops polling when it unmounts", () => {
    const { unmount } = render(<ControllerPanel />);
    const spy = vi.spyOn(navigator, "getGamepads");
    unmount();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(spy).not.toHaveBeenCalled();
  });
});
