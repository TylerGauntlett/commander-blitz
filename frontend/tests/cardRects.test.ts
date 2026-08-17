/**
 * The last-known-position registry behind the exit animation.
 *
 * Safe in jsdom precisely because the module never touches the DOM: the caller
 * measures and hands a box over. What cannot be proved here is that `Card`
 * actually posts a real box on unmount -- jsdom's rects are all zero and the
 * guard below would reject them -- so that contract lives in a story instead.
 */

import { afterEach, describe, expect, it } from "vitest";
import { recall, remember, reset, setClock } from "../src/logic/cardRects";

const BOX = { x: 100, y: 200, width: 80, height: 112 };

afterEach(() => {
  reset();
  setClock();
});

describe("cardRects", () => {
  it("gives back what it was told", () => {
    remember(7, BOX);
    expect(recall(7)).toEqual(BOX);
  });

  it("returns null for a card it has never seen", () => {
    expect(recall(999)).toBeNull();
  });

  it("copies the rect rather than holding the caller's object", () => {
    // `getBoundingClientRect` returns a fresh object, but a caller passing a
    // reused scratch box would otherwise see every entry mutate together.
    const scratch = { ...BOX };
    remember(7, scratch);
    scratch.x = -1;
    expect(recall(7)?.x).toBe(100);
  });

  it("rejects a zero-sized box", () => {
    // jsdom reports every element as 0x0. Without this guard, any unit test
    // that mounts a board would fill the map with origin-anchored positions and
    // ghosts would fly out of the top-left corner of the screen.
    remember(7, { x: 0, y: 0, width: 0, height: 0 });
    expect(recall(7)).toBeNull();
  });

  it("forgets a position that has gone stale", () => {
    let clock = 0;
    setClock(() => clock);
    remember(7, BOX);
    clock = 29_000;
    expect(recall(7)).toEqual(BOX);
    // A window resize or a zoom change makes an old coordinate meaningless, and
    // there is no event that tells this module either has happened.
    clock = 31_000;
    expect(recall(7)).toBeNull();
  });

  it("evicts the oldest entry past its cap", () => {
    for (let oid = 0; oid < 205; oid++) remember(oid, BOX);
    expect(recall(0)).toBeNull();
    expect(recall(4)).toBeNull();
    expect(recall(5)).toEqual(BOX);
    expect(recall(204)).toEqual(BOX);
  });

  it("re-remembering a card moves it out of the eviction queue", () => {
    remember(1, BOX);
    for (let oid = 100; oid < 250; oid++) remember(oid, BOX);
    remember(1, BOX);
    for (let oid = 250; oid < 349; oid++) remember(oid, BOX);
    expect(recall(1)).toEqual(BOX);
  });

  it("reset empties it", () => {
    remember(7, BOX);
    reset();
    expect(recall(7)).toBeNull();
  });
});
