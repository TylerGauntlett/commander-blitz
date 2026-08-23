/*
 * Drive every mockup at every density and print the README's table.
 *
 *     node mockups/seat/measure.mjs            the table
 *     node mockups/seat/measure.mjs --json     the raw gate output
 *     node mockups/seat/measure.mjs --shots    ...and write shots/*.png
 *
 * `assert.js` is the gate; this is the thing that runs it fifteen times so a
 * README table is measured rather than estimated. It reuses the frontend's own
 * Playwright install rather than adding a dependency to a folder that has never
 * had one -- the mockups still open standalone from file:// and this script is
 * not needed to look at them.
 *
 * The viewport is 1280x800 and the page is opened from file://, which is how
 * every one of these is meant to be read. See `_seat.css` for why the stage is
 * a fixed Deck screen rather than the window.
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mkdirSync, readdirSync, writeFileSync } from "node:fs";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = require(join(HERE, "..", "..", "frontend", "node_modules", "playwright"));

const JSON_OUT = process.argv.includes("--json");
const SHOTS = process.argv.includes("--shots");

const files = readdirSync(HERE).filter((f) => /^\d\d-.*\.html$/.test(f)).sort();
if (!files.length) throw new Error("no mockups here");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

/* Attached before anything loads. It was attached after the loop the first
   time, which reports zero errors on every run and is worse than no check. */
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

const rows = [];
for (const file of files) {
  await page.goto("file://" + join(HERE, file).replace(/\\/g, "/"));
  for (const density of [1, 2, 3]) {
    await page.keyboard.press(String(density));
    await page.waitForTimeout(90);
    const out = await page.evaluate(() => {
      const r = SEAT_ASSERT();
      delete r.faults;
      return r;
    });
    rows.push({ file, density, ...out });
    if (SHOTS) {
      mkdirSync(join(HERE, "shots"), { recursive: true });
      await page.screenshot({
        path: join(HERE, "shots", file.replace(".html", "") + "-" + density + ".png"),
      });
    }
  }
}

await browser.close();

if (JSON_OUT) {
  console.log(JSON.stringify(rows, null, 2));
} else {
  const head = ["file", "n", "seat", "row/budget", "cells", "box", "pad", "gap", "font", "hit", "esc", "clip", "PASS"];
  const body = rows.map((r) => [
    r.file.slice(0, 18),
    r.density,
    r.seats[0] || "-",
    r.rowHeightPx + "/" + r.budgetPx,
    r.cells,
    r.boxKinds,
    r.padKinds,
    r.gapKinds,
    r.minFontPx,
    r.minHitPx,
    r.escaped,
    r.clipped,
    r.PASS ? "yes" : "NO",
  ]);
  const w = head.map((h, i) => Math.max(h.length, ...body.map((b) => String(b[i]).length)));
  const line = (cells) => cells.map((c, i) => String(c).padEnd(w[i])).join("  ");
  console.log(line(head));
  console.log(w.map((n) => "-".repeat(n)).join("  "));
  for (const b of body) console.log(line(b));
}

if (errors.length) {
  console.error("\nconsole errors:\n" + errors.join("\n"));
  process.exitCode = 1;
}
