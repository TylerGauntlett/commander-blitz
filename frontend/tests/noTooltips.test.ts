/**
 * No native tooltips.
 *
 * A `title` attribute opens on hover and on nothing else. There is no keyboard
 * route into one, no controller route, and no touch route — so on a Steam Deck
 * every one of them is information that simply cannot be reached, and the
 * board had 142 of them at one point in a single rendered frame.
 *
 * They were carrying real things: which card is revealed on top of a library,
 * how much commander damage is from whom, what a mode toggle actually changes,
 * why the deal button is disabled. `data-hint` carries the same string to the
 * hint bar and the read rail, driven from the *focused* element rather than the
 * hovered one — which also means a mouse player gets it immediately instead of
 * after the browser's ~500ms delay.
 *
 * Two things are deliberately still allowed:
 *
 *   - `title` as a **prop of one of our own components** (`ManaSymbol`'s
 *     override for its braced notation). That is an API, not an attribute.
 *   - `<title>` inside SVG, which is the accessible name of a graphic and is
 *     read out rather than hovered.
 */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.tsx$/.test(entry.name) ? [path] : [];
  });
}

/** A `title=` attribute on a DOM element, not on a component. */
const DOM_TITLE = /(?<!<[A-Z][\w]*[^>]{0,400})\stitle=/;

function offendingLines(text: string): string[] {
  return (
    text
      .split("\n")
      .filter((line) => / title=/.test(line))
      // A `title` handed to one of our own components is a prop.
      .filter((line) => !/<[A-Z]\w*/.test(line))
      .map((line) => line.trim())
  );
}

describe("native tooltips", () => {
  const files = sources(SRC).filter((path) => !path.includes(".stories."));

  it.each(files.map((path) => [path.slice(path.indexOf("components")) || path, path]))(
    "%s writes no title attribute",
    (_label, path) => {
      expect(offendingLines(readFileSync(path, "utf8"))).toEqual([]);
    },
  );

  it("detects one when it is there", () => {
    // A guard nobody has seen fail is a guard nobody should trust.
    expect(offendingLines('<button title="Quit">x</button>')).toHaveLength(1);
    expect(offendingLines("<ManaSymbol code={c} title={name} />")).toHaveLength(0);
    expect(offendingLines('<button data-hint="Quit">x</button>')).toHaveLength(0);
  });

  it("leaves the DOM_TITLE shape documented even though the line filter is what runs", () => {
    // Kept so the intent is greppable; the line-based filter above is the one
    // that handles multi-line JSX correctly.
    expect(DOM_TITLE.test(' title="x"')).toBe(true);
  });
});
