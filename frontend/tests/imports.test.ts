/**
 * Test code must not be reachable from the app.
 *
 * `src/testing/` and `*.stories.tsx` live under `src/` so the unit tests and the
 * Storybook glob can share one definition of what a card is. The cost of that
 * convenience is that they are now one import away from the bundle: Rollup
 * includes a module because something reachable from `main.tsx` imports it, not
 * because of which directory it sits in. Nothing enforces the boundary at the
 * type level, so it is enforced here.
 *
 * A failure means a component imported a fixture -- almost certainly to reuse a
 * default it wanted anyway. Move the value into the component's own module; do
 * not relax this.
 */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");

/** Every .ts/.tsx file under `dir`, recursively. */
function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

/** What the app actually ships: everything under `src/` that is not a fixture. */
const shipped = sources(SRC).filter(
  (path) => !path.includes(`${join("src", "testing")}`) && !path.includes(".stories."),
);

describe("the production graph", () => {
  it("has files in it", () => {
    // Guards the guard: a glob that silently matched nothing would pass every
    // assertion below forever.
    expect(shipped.length).toBeGreaterThan(40);
  });

  it.each([
    "testing/fixtures",
    "testing/scenarios",
    "testing/art",
    "testing/asserts",
    "testing/mounts",
    "testing/appGeometry",
    "testing/cards",
    "testing/pods",
    "testing/fakeGame",
    ".stories",
  ])("never imports %s", (module) => {
    const offenders = shipped.filter((path) => {
      const text = readFileSync(path, "utf8");
      return new RegExp(`from\\s+["'][^"']*${module.replace(".", "\\.")}["']`).test(text);
    });
    expect(offenders).toEqual([]);
  });
});

/**
 * Every story says where it hangs.
 *
 * `parameters` is loosely typed at the call site, so a story left carrying the
 * old `frame:` key would be a silent no-op -- it would inherit nothing, and
 * `withMount` would throw at render rather than here. Cheaper to say it in a
 * test, and it keeps the rename honest.
 */
describe("stories", () => {
  const stories = sources(SRC).filter((path) => path.includes(".stories."));

  it("has stories in it", () => {
    expect(stories.length).toBeGreaterThan(20);
  });

  it.each(stories.map((path) => [path.slice(path.indexOf("components")), path]))(
    "%s declares a mount and no stale frame",
    (_label, path) => {
      const text = readFileSync(path, "utf8");
      expect(text.includes("frame:"), "`frame:` was renamed to `mount:`").toBe(false);
      expect(text.includes("mount:"), "no story in this file names its mount").toBe(true);
    },
  );
});
