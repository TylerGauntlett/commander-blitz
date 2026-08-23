/*
 * Drive every mockup at every density and print the README's table.
 *
 *     node mockups/self/measure.mjs            the table
 *     node mockups/self/measure.mjs --json     the raw gate output
 *     node mockups/self/measure.mjs --shots    ...and write shots/*.png
 *
 * `assert.js` is the gate; this is the thing that runs it fifteen times so a
 * README table is measured rather than estimated. It reuses the frontend's own
 * Playwright install rather than adding a dependency to a folder that has never
 * had one -- the mockups still open standalone from file:// and this script is
 * not needed to look at them.
 *
 * The viewport is 1280x800 and the page is opened from file://, which is how
 * every one of these is meant to be read. See `_self.css` for why the stage is
 * a fixed Deck screen rather than the window.
 *
 * WHY THE STATE LOOP IS LONGER THAN THE SEAT ROUND'S. That round varied one
 * knob that mattered -- how many opponents -- because a seat's problem is its
 * width and its width is a function of the density. An orb's box does not move
 * with the density at all; what moves is WHAT IS IN IT: priority arrives, a
 * hovered spell adds a `-n` to three mana groups, and the commander going back
 * to the command zone adds a tax chip and a state word that were not there a
 * moment ago. Those are the states that break a column, so the table is taken
 * over the states as well and `--json` carries every one of them.
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

/* The cycle `s` walks, in order, so pressing it N times lands where this says.
   Boot is `priority`, which is index 1. */
const MARKS = ["rest", "priority", "spending", "cmdzone", "unpaid", "out", "noart"];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

/* Attached before anything loads. It was attached after the loop the first
   time, which reports zero errors on every run and is worse than no check. */
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

const gate = () =>
  page.evaluate(() => {
    const r = ORB_ASSERT();
    delete r.faults;
    return r;
  });

const rows = [];
const states = [];

for (const file of files) {
  await page.goto("file://" + join(HERE, file).replace(/\\/g, "/"));

  /* The densities, at the boot state. An orb's box does not change with the
     density; the number of commander-damage sources in it does. */
  for (const density of [1, 2, 3]) {
    await page.keyboard.press(String(density));
    await page.waitForTimeout(90);
    rows.push({ file, density, mark: "priority", ...(await gate()) });
    if (SHOTS && density === 3) {
      mkdirSync(join(HERE, "shots"), { recursive: true });
      await page.screenshot({ path: join(HERE, "shots", file.replace(".html", "") + ".png") });
    }
  }

  /* Then every state, at three opponents -- the hardest density for all of
     them, because it is the one with three commander-damage sources. */
  let at = MARKS.indexOf("priority");
  for (let i = 0; i < MARKS.length; i += 1) {
    const want = MARKS[i];
    while (MARKS[at] !== want) {
      await page.keyboard.press("s");
      at = (at + 1) % MARKS.length;
    }
    await page.waitForTimeout(90);
    states.push({ file, density: 3, mark: want, ...(await gate()) });
    if (SHOTS) {
      mkdirSync(join(HERE, "shots"), { recursive: true });
      await page.screenshot({
        path: join(HERE, "shots", file.replace(".html", "") + "-" + want + ".png"),
      });
    }
  }
}

await browser.close();

if (JSON_OUT) {
  console.log(JSON.stringify({ densities: rows, states }, null, 2));
} else {
  const table = (title, data, keyCol, keyName) => {
    const head = [
      "file", keyName, "orb", "budget", "lanes", "cells",
      "box", "pad", "gap", "font", "hit", "esc", "clip", "PASS",
    ];
    const body = data.map((r) => [
      r.file.slice(0, 18),
      String(r[keyCol]),
      r.orb,
      r.budget,
      r.laneCards,
      r.cells,
      r.boxKinds,
      r.padKinds,
      r.gapKinds,
      r.minFontPx,
      r.minHitPx === null ? "-" : r.minHitPx,
      r.escaped,
      r.clipped,
      r.PASS ? "yes" : "NO",
    ]);
    const w = head.map((h, i) => Math.max(h.length, ...body.map((b) => String(b[i]).length)));
    const line = (cells) => cells.map((c, i) => String(c).padEnd(w[i])).join("  ");
    console.log("\n" + title);
    console.log(line(head));
    console.log(w.map((n) => "-".repeat(n)).join("  "));
    for (const b of body) console.log(line(b));
  };

  table("BY DENSITY (state: priority)", rows, "density", "n");
  table("BY STATE (three opponents)", states, "mark", "state");
}

if (errors.length) {
  console.error("\nconsole errors:\n" + errors.join("\n"));
  process.exitCode = 1;
}
