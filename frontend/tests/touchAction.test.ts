/**
 * Which cards a finger may scroll past.
 *
 * `.card` turns panning off, because a board card is dragged onto a lane and a
 * browser that took the drag for a scroll would never deliver it. A static card
 * is never dragged, and inheriting `none` meant a finger landing on a deck tile
 * could not scroll the catalogue the tiles fill. Read off disk, as
 * `breakpoints.test.ts` reads its queries, because jsdom does not cascade.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "..", "src", "styles", "cards.css"), "utf8");

function rule(selector: string): string {
  const match = new RegExp(`^${selector.replace(".", "\\.")} \\{([^}]*)\\}`, "m").exec(css);
  if (!match) throw new Error(`no ${selector} rule in cards.css`);
  // Comments say why; only the declarations decide.
  return match[1].replace(/\/\*[\s\S]*?\*\//g, "");
}

describe("touch-action on cards", () => {
  it("keeps the browser's pan off a draggable card", () => {
    expect(rule(".card")).toMatch(/touch-action:\s*none/);
  });

  it("gives a static card the pan back", () => {
    const declared = /touch-action:\s*([^;]+);/.exec(rule(".card--static"))?.[1].trim();
    expect(["manipulation", "auto", "pan-y", "pan-x pan-y"]).toContain(declared);
  });
});
