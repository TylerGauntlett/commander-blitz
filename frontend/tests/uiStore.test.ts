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
import { NOTHING_STAGED, pickedFor, stagedAs } from "../src/logic/staging";
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

/**
 * The one staged set (`logic/staging.ts`).
 *
 * Attackers, blockers and picks were three sets with three shapes; they are
 * one map from the thing staged to what it is staged as, owned by the decision
 * it answers. What these pin: the three call sites stage into the same set, a
 * different decision empties it, `clearStaging` empties it, and `B` backs it
 * out without discarding what one press could not put back.
 */
describe("the staged set", () => {
  beforeEach(() => useUiStore.getState().clearStaging());
  const store = () => useUiStore.getState();

  it("stages an attacker, a blocker and a pick through one call", () => {
    store().stage("k", "attack", 301, 1);
    store().stage("k", "attack", 302, 2);
    expect(stagedAs(store().staged, "attack")).toEqual({ 301: 1, 302: 2 });

    // Re-aiming keeps the attacker where it was in the set.
    store().stage("k", "attack", 301, 3);
    expect(stagedAs(store().staged, "attack")).toEqual({ 301: 3, 302: 2 });
    expect(store().staged.order).toEqual([301, 302]);

    store().stage("b", "block", 401, 410);
    expect(stagedAs(store().staged, "block")).toEqual({ 401: 410 });
    // One set: staging blocks for another decision left no attackers behind.
    expect(stagedAs(store().staged, "attack")).toEqual({});

    store().stage("p", "pick", 2, 1);
    store().stage("p", "pick", 0, 1);
    expect(pickedFor(store().staged, "p")).toEqual([2, 0]);
    expect(stagedAs(store().staged, "block")).toEqual({});
  });

  it("takes one thing out with unstage", () => {
    store().stage("k", "attack", 301, 1);
    store().stage("k", "attack", 302, 1);
    store().unstage(301);
    expect(stagedAs(store().staged, "attack")).toEqual({ 302: 1 });
  });

  it("is emptied when the decision changes, and kept while it does not", () => {
    store().stage("k", "pick", 1, 1);
    store().rekeyStaging("k");
    expect(pickedFor(store().staged, "k")).toEqual([1]);

    store().rekeyStaging("next");
    expect(store().staged.order).toEqual([]);
    expect(pickedFor(store().staged, "k")).toEqual([]);
  });

  it("starts a new set when a stage names another decision", () => {
    store().stage("k", "pick", 1, 1);
    store().stage("next", "pick", 3, 1);
    expect(pickedFor(store().staged, "next")).toEqual([3]);
    expect(pickedFor(store().staged, "k")).toEqual([]);
  });

  it("is emptied by clearStaging", () => {
    store().stage("k", "attack", 301, 1);
    store().clearStaging();
    expect(store().staged).toEqual(NOTHING_STAGED);
  });

  it("backs a hand-built set out one entry per press, newest first", () => {
    store().stage("k", "attack", 302, 1);
    store().stage("k", "attack", 301, 1);
    expect(store().backOutStaged()).toBe(true);
    expect(store().staged.order).toEqual([302]);
    expect(store().backOutStaged()).toBe(true);
    expect(store().staged.order).toEqual([]);
    expect(store().backOutStaged()).toBe(false);
  });

  it("backs a set the 'all' mark built out whole, since the mark rebuilds it", () => {
    store().stageMarked("k", "attack", [
      [301, 1],
      [302, 1],
    ]);
    expect(store().staged.marked).toBe(true);
    expect(store().backOutStaged()).toBe(true);
    expect(store().staged.order).toEqual([]);
  });

  it("stops treating the set as the mark's once a hand has changed it", () => {
    store().stageMarked("k", "block", [[401, 410]]);
    store().stage("k", "block", 402, 410);
    expect(store().staged.marked).toBe(false);
    expect(store().backOutStaged()).toBe(true);
    expect(store().staged.order).toEqual([401]);

    // A set started by hand is not the mark's even after the mark adds to it.
    store().clearStaging();
    store().stage("k", "pick", 0, 1);
    store().stageMarked("k", "pick", [[1, 1]]);
    expect(store().staged.marked).toBe(false);
  });
});
