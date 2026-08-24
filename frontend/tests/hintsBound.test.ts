/**
 * The hint bar may not advertise a button that does nothing.
 *
 * IT DID, THREE TIMES, AND FOR MONTHS. `L1 Zone` and `L2 Menu` were in
 * `NAVIGATION_HINTS` from the first draft and `verbsFor` returned `Y Read` on
 * every card stop, with **nothing in the app listening for any of the three**.
 * A player who read the bar and pressed what it said got nothing back -- which
 * is worse than an unadvertised button, because it teaches them the bar is not
 * to be trusted, and after that they stop reading it.
 *
 * Nothing in the suite could see it. The bar renders spans (deliberately -- see
 * `HintBar.tsx`), and a span cannot fail to work.
 *
 * ## Why this reads the source rather than mounting the board
 *
 * `verbs.ts` and `pad.ts` both said this file mounts `Table` and compares
 * `boundButtons()` against the bar. That would be the better test and it is not
 * the affordable one: `Table` is never rendered anywhere in this suite, and
 * standing one up needs the router, the query client, the engine fixtures and
 * the FX scheduler -- a lot of machinery whose failures would land here and be
 * read as an input regression.
 *
 * So this asks the same question of the source: every button the bar can name
 * has a binding somewhere. It cannot prove the binding RUNS, which the mounted
 * version could. It does catch the thing that actually happened -- a button
 * named in the bar with no listener anywhere in the app -- and it catches it
 * without a board.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { PadButton } from "../src/input/buttons";
import { BTN } from "../src/input/buttons";
import { NAVIGATION_HINTS } from "../src/logic/verbs";

const SRC = join(__dirname, "..", "src");

/** Every file that binds pad intents. Bindings are not allowed to hide. */
const BINDERS = [
  "input/useCursorNav.ts",
  "components/game/Table.tsx",
  "components/lobby/HomeScreen.tsx",
];

/**
 * The buttons bound anywhere, read out of the calls that bind them.
 *
 * `on("b", ...)` and `onPad("b", ...)` are the same function -- `Table` imports
 * it under an alias -- so the pattern is deliberately about the ARGUMENT rather
 * than the callee name, which is the part that cannot drift.
 */
function boundInSource(): Set<PadButton> {
  const found = new Set<PadButton>();
  for (const file of BINDERS) {
    const text = readFileSync(join(SRC, file), "utf8");
    for (const match of text.matchAll(/\bon[A-Za-z]*\(\s*"([a-z0-9]+)"/g)) {
      const name = match[1] as PadButton;
      if (name in BTN) found.add(name);
    }
    // `DIRECTIONS.map((dir) => on(dir, ...))` -- a bind through a variable, and
    // the only one. Named here rather than pattern-matched, because inferring
    // it would mean guessing at what any identifier holds.
    if (/\bon\(dir\b/.test(text)) {
      for (const dir of ["up", "down", "left", "right"] as const) found.add(dir);
    }
  }
  return found;
}

/** What `verbsFor` can put in front of a player. See the `Verbs` shape. */
const VERB_BUTTONS: PadButton[] = ["a", "x", "y", "b"];

describe("every advertised button is bound", () => {
  const bound = boundInSource();

  it.each(VERB_BUTTONS)("binds %s, which verbsFor can name on a stop", (btn) => {
    expect(bound.has(btn), `verbsFor can return ${btn} and nothing binds it`).toBe(true);
  });

  it.each(
    NAVIGATION_HINTS.flatMap((nav) =>
      // `dpad` is one glyph standing for four intents, and all four have to work
      // or the bar is three-quarters honest.
      nav.btn === "dpad" ? (["up", "down", "left", "right"] as const) : [nav.btn],
    ),
  )("binds %s, which the navigation hints name", (btn) => {
    expect(bound.has(btn as PadButton), `the hint bar names ${btn} and nothing binds it`).toBe(
      true,
    );
  });

  it("binds R1 as well as L1, which the bar shows only one of", () => {
    /*
     * `NAVIGATION_HINTS` prints `L1 Region` and lets it stand for the pair,
     * because two glyphs for one idea is what the bar is short of room for. That
     * is only honest while R1 is genuinely bound -- a player who reads "L1
     * Region" and reasonably tries R1 must not find it dead.
     */
    expect(bound.has("r1")).toBe(true);
  });
});
