/**
 * The one CSS rule that can silently erase the focus ring.
 *
 * `handheld.css` draws the ring as `outline: 3px solid var(--focus)` on
 * `[data-cursor]`. A bare `:focus { outline: none }` anywhere in the same
 * document matches that element too, at *equal specificity* -- one class-level
 * selector each -- so it wins on source order and leaves the rule computing
 * `outline-width: 3px` with `outline-style: none`.
 *
 * That failure mode is vicious in a specific way: every property except
 * `outline-style` still reports the value you expect, so a test that measures
 * the width passes, devtools shows the declaration applied and not struck
 * through, and the ring is simply invisible. It is also the single most common
 * line in any stylesheet that has ever been told its focus rings are ugly.
 *
 * The suppression the app genuinely needs is `:focus:not([data-cursor])`, which
 * `cursor.ts` requires because it calls `.focus()` to keep assistive tech on
 * the same object the ring is on -- so without the `:not()` there would be two
 * rings, and with an unqualified one there is none.
 *
 * `e2e/handheldAssert.ts` asserts the rendered `outline-style` for the same
 * reason. This is the cheaper half: it fails at the line somebody wrote.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const STYLES = join(__dirname, "..", "src", "styles");

/**
 * CSS with its comments removed.
 *
 * The guard below reads selectors, and a doc comment explaining the rule
 * inevitably *contains* the rule -- this file's own note in `lobby.css` quotes
 * `:focus { outline: none }` verbatim to say why it is banned. A guard that
 * fires on its own documentation is a guard people delete the documentation to
 * satisfy, which is the opposite of what it is for.
 */
function withoutComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function stylesheets(): { name: string; text: string }[] {
  const here = readdirSync(STYLES).filter((name) => name.endsWith(".css"));
  const files = here.map((name) => ({
    name,
    text: withoutComments(readFileSync(join(STYLES, name), "utf8")),
  }));
  files.push({
    name: "theme.css",
    text: withoutComments(readFileSync(join(__dirname, "..", "src", "theme.css"), "utf8")),
  });
  return files;
}

/**
 * Any focus suppression that does not exempt the cursor.
 *
 * This started out narrow -- it banned only the *bare* `:focus { outline: none }`
 * on the reasoning that a class-qualified one "cannot silently blank the ring
 * across the board". That reasoning was exactly backwards, and driving the
 * front door with a controller proved it: `.join__in:focus { outline: none }`
 * is one class plus a pseudo-class, which OUTRANKS the ring's single attribute
 * selector, so it did not merely fail to blank the ring across the board -- it
 * reliably blanked it on every element it named, and nowhere else, which is
 * harder to notice.
 *
 * So the rule is now the simple one: if a selector ends in `:focus` and turns
 * an outline off, it must say `:not([data-cursor])`.
 */
const BARE_FOCUS =
  /[^{}]*:focus(?:-visible|-within)?(?![\w-]|:not\(\[data-cursor\]\))[^{]*\{[^}]*outline\s*:\s*(?:none|0)/g;

describe("the focus outline", () => {
  it.each(stylesheets().map((sheet) => [sheet.name, sheet.text]))(
    "%s writes no unqualified :focus { outline: none }",
    (_name, text) => {
      expect([...text.matchAll(BARE_FOCUS)].map((match) => match[0])).toEqual([]);
    },
  );

  it("still finds the qualified suppression the cursor depends on", () => {
    /*
     * A guard that only ever says "no" is a guard nobody can tell is working.
     * This is the positive half: the rule the app actually needs is present, so
     * if somebody deletes it the suite says so rather than going quietly green.
     */
    const handheld = readFileSync(join(STYLES, "handheld.css"), "utf8");
    expect(handheld).toMatch(/:focus:not\(\[data-cursor\]\)/);
    expect(handheld).toMatch(/\[data-cursor\][^{]*\{[^}]*outline:/);
  });

  it("detects the bad pattern when it is present", () => {
    // The gate has to be shown to fail, or it is only decoration.
    const bad = "button:hover {} :focus { outline: none; }";
    expect([...bad.matchAll(BARE_FOCUS)].length).toBe(1);
    const good = ":focus:not([data-cursor]) { outline: none; }";
    expect([...good.matchAll(BARE_FOCUS)].length).toBe(0);
  });
});
