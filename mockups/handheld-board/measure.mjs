/*
 * Drive every mockup and print the README's table.
 *
 *     node mockups/handheld-board/measure.mjs            the table
 *     node mockups/handheld-board/measure.mjs --json     the raw gate output
 *     node mockups/handheld-board/measure.mjs --shots    ...and write shots/*.png
 *
 * `assert.js` is the gate; this is the thing that runs it three times so a README
 * table is measured rather than estimated. It reuses the frontend's own
 * Playwright install rather than adding a dependency to a folder that has never
 * had one -- the mockups still open standalone from file:// and this script is
 * not needed to look at them.
 *
 * The viewport is 1280x800 and the page is opened from file://, which is how
 * every one of these is meant to be read. See `_board.css` for why the stage is a
 * fixed Deck screen rather than the window.
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mkdirSync, readdirSync } from "node:fs";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = require(join(HERE, "..", "..", "frontend", "node_modules", "playwright"));

const JSON_OUT = process.argv.includes("--json");
const SHOTS = process.argv.includes("--shots");

const files = readdirSync(HERE).filter((f) => /^\d\d-.*\.html$/.test(f)).sort();
if (!files.length) throw new Error("no mockups here");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

/* Attached before anything loads. It was attached after the loop the first time
   in the seat round, which reports zero errors on every run and is worse than no
   check. */
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

const rows = [];
for (const file of files) {
  await page.goto("file://" + join(HERE, file).replace(/\\/g, "/"));
  await page.waitForTimeout(120);
  const out = await page.evaluate(() => {
    const r = BOARD_ASSERT();
    delete r.faults;
    return r;
  });
  rows.push({ file, ...out });
  if (SHOTS) {
    mkdirSync(join(HERE, "shots"), { recursive: true });
    await page.screenshot({ path: join(HERE, "shots", file.replace(".html", "") + ".png") });
  }
}

await browser.close();

if (JSON_OUT) {
  console.log(JSON.stringify(rows, null, 2));
} else {
  const head = ["file", "rail", "reader", "list", "share", "rows", "cards", "card", "font", "hit", "seats", "esc", "clip", "PASS"];
  const body = rows.map((r) => [
    r.file.slice(0, 14),
    r.railPx,
    r.readerPx,
    r.listPx,
    r.listShare,
    r.rowsVisible,
    r.cards,
    r.minCardPx,
    r.minFontPx,
    r.minHitPx,
    r.seatsAgree ? "agree" : "NO",
    r.escaped,
    r.silentClips,
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
