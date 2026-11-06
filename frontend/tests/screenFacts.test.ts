/**
 * The Settings screen readout (`state/viewportFit.ts:screenFacts`).
 *
 * jsdom resolves no `env()`, so the insets read as zero on every side; what
 * this holds is the shape a bug report screenshot depends on.
 */

import { afterEach, describe, expect, it } from "vitest";
import { screenFacts } from "../src/state/viewportFit";

afterEach(() => {
  document.head.innerHTML = "";
});

describe("screenFacts", () => {
  it("names each inset side, and reads the tags the page carries", () => {
    document.head.innerHTML =
      '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">' +
      '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">';
    const facts = screenFacts();
    expect(facts.insets).toBe("t0 r0 b0 l0");
    expect(facts.tag).toBe("width=device-width, initial-scale=1.0, viewport-fit=cover");
    expect(facts.statusBar).toBe("black-translucent");
    expect(facts.mode).toBe("browser");
    expect(facts.viewport).toMatch(/^\d+ x \d+$/);
  });

  it("says none for a tag the page does not carry", () => {
    const facts = screenFacts();
    expect(facts.tag).toBe("none");
    expect(facts.statusBar).toBe("none");
  });

  it("leaves no probe behind", () => {
    const before = document.body.childElementCount;
    screenFacts();
    expect(document.body.childElementCount).toBe(before);
  });
});
