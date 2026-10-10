/**
 * Narration pacing.
 *
 * The multipliers are divisors on every beat's hold and every FX lifetime, so
 * their absolute values are the game's sense of speed. Cycle 3 halved them:
 * "the game moves too quickly" (a cycle-2 playtest finding) was true at both
 * watchable settings, and the slowest thing on offer was 1x.
 *
 * The per-beat holds in `logic/events.ts` were deliberately left alone -- they
 * encode the *relative* weight of events, and rescaling twenty of them by hand
 * to change one thing is how a palette drifts.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { SPEED_MULTIPLIER, type Speed, useUiStore } from "../src/state/uiStore";

const WATCHABLE: Speed[] = ["cinematic", "fast"];

describe("SPEED_MULTIPLIER", () => {
  it("makes the default setting the old 'cinematic' pace", () => {
    // `fast` is the stored default, and it used to divide holds by 2.
    expect(SPEED_MULTIPLIER.fast).toBe(1);
  });

  it("offers something slower than the old floor", () => {
    // There was no way to ask for less than 1x, which is what the complaint was
    // really about.
    expect(SPEED_MULTIPLIER.cinematic).toBeLessThan(1);
  });

  it("orders the watchable settings slowest first", () => {
    expect(SPEED_MULTIPLIER.cinematic).toBeLessThan(SPEED_MULTIPLIER.fast);
  });

  it("keeps every watchable setting slow enough to read a beat", () => {
    // A 260ms land drop must not fall under the ~120ms it takes to notice one.
    for (const speed of WATCHABLE) {
      expect(260 / SPEED_MULTIPLIER[speed]).toBeGreaterThan(120);
    }
  });

  it("keeps instant effectively instant", () => {
    // Not a speed so much as a bypass: `narration.ts` short-circuits on it and
    // drops beats rather than holding them for ~0ms.
    expect(1100 / SPEED_MULTIPLIER.instant).toBeLessThan(5);
  });

  it("defines every speed exactly once", () => {
    expect(Object.keys(SPEED_MULTIPLIER).sort()).toEqual(["cinematic", "fast", "instant"]);
  });

  it("never divides by zero or a negative", () => {
    for (const value of Object.values(SPEED_MULTIPLIER)) {
      expect(value).toBeGreaterThan(0);
    }
  });
});

/**
 * Narrowing a selection rather than resolving it.
 *
 * Picking a target answers one of the questions a click can be asking. Into the
 * Roil aimed at a creature is still two legal actions -- kicked and not -- and
 * `Table` used to take the first, which `legality` emits unkicked, so the
 * kicked cast could not be reached by any gesture at all.
 */
describe("narrowTargeting", () => {
  beforeEach(() => {
    useUiStore.setState({ selectedOid: null, targetingActionIds: [] });
  });

  it("drops the ids that are no longer in the running", () => {
    useUiStore.getState().beginTargeting(7, ["a1-cast", "a2-cast", "a3-cast"]);
    useUiStore.getState().narrowTargeting(["a2-cast", "a3-cast"]);
    expect(useUiStore.getState().targetingActionIds).toEqual(["a2-cast", "a3-cast"]);
  });

  it("keeps the selection open, so the panel can ask the rest", () => {
    // The distinction from `endTargeting`, which clears both: narrowing is
    // mid-question, and dropping the selection would strand the player with a
    // target picked and nothing saying so.
    useUiStore.getState().beginTargeting(7, ["a1-cast", "a2-cast"]);
    useUiStore.getState().narrowTargeting(["a2-cast"]);
    expect(useUiStore.getState().selectedOid).toBe(7);
  });

  it("leaves the card selected where endTargeting would clear it", () => {
    useUiStore.getState().beginTargeting(7, ["a1-cast", "a2-cast"]);
    useUiStore.getState().endTargeting();
    expect(useUiStore.getState().selectedOid).toBeNull();
    expect(useUiStore.getState().targetingActionIds).toEqual([]);
  });
});

/**
 * The hint bar is a setting, and it starts off.
 *
 * The flag is what `html[data-hints]` reads, so toggling it has to stamp the
 * document as well as remember itself -- nothing subscribes to the attribute.
 */
describe("hints", () => {
  beforeEach(() => {
    localStorage.removeItem("commanderblitz.hints");
    useUiStore.setState({ hints: false });
  });

  it("starts hidden, and the document says so", () => {
    expect(useUiStore.getState().hints).toBe(false);
    useUiStore.getState().toggleHints();
    useUiStore.getState().toggleHints();
    expect(document.documentElement.getAttribute("data-hints")).toBe("off");
  });

  it("toggles on, remembers it, and stamps the document", () => {
    useUiStore.getState().toggleHints();
    expect(useUiStore.getState().hints).toBe(true);
    expect(localStorage.getItem("commanderblitz.hints")).toBe("on");
    expect(document.documentElement.getAttribute("data-hints")).toBe("on");
  });
});
