/*
 * Drive every mockup and print the README's table.
 *
 *     node mockups/door/measure.mjs            the table
 *     node mockups/door/measure.mjs --json     the raw gate output
 *     node mockups/door/measure.mjs --shots    ...and write shots/*.png
 *
 * `assert.js` is the gate; this is the thing that runs it five times so a README
 * table is measured rather than estimated. It reuses the frontend's own
 * Playwright install rather than adding a dependency to a folder that has never
 * had one -- the mockups still open standalone from file:// and this script is
 * not needed to look at them.
 *
 * The viewport is 1280x800 and the page is opened from file://, which is how
 * every one of these is meant to be read.
 *
 * ---------------------------------------------------------------------------
 * IT TAKES THREE SHOTS PER FILE, NOT ONE, and that is this round's difference
 * from `../handheld-board/measure.mjs`.
 *
 * The subject is what the row does when the selection moves, and the default
 * pose is the one pose in which nothing is stacked -- so a folder of five
 * default screenshots would show the one state the brief is not about. Each
 * file therefore writes `-left`, `-mid` and `-right`. The gate itself already
 * walks all three internally; this walks them again for the eye.
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
   in the seat round, which reports zero errors on every run and is worse than
   no check. */
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

/* Any request that is not the file itself. These open from file:// with no
   network, and a direction that grew a webfont or a CDN would still look
   perfectly fine on the machine that wrote it. 05's `../art/*.jpg` are local
   files and arrive as file:// too, so they are not requests either. */
const external = [];
page.on("request", (r) => {
  if (!r.url().startsWith("file://")) external.push(r.url());
});

const POSES = ["left", "mid", "right"];

const rows = [];
for (const file of files) {
  await page.goto("file://" + join(HERE, file).replace(/\\/g, "/"));
  await page.waitForTimeout(140);

  const out = await page.evaluate(() => {
    const r = DOOR_ASSERT();
    delete r.faults;
    return r;
  });
  rows.push({ file, ...out });

  if (SHOTS) {
    mkdirSync(join(HERE, "shots"), { recursive: true });
    for (let i = 0; i < POSES.length; i += 1) {
      await page.evaluate((n) => DOOR.select(n, true), i);
      // The sheen loops forever and never finishes, so there is nothing to wait
      // on: one frame is enough for a snapped layout to have painted.
      await page.waitForTimeout(60);
      await page.screenshot({
        path: join(HERE, "shots", file.replace(".html", "") + "-" + POSES[i] + ".png"),
      });
    }
    await page.evaluate(() => DOOR.select(1, true));
  }
}

await browser.close();

if (JSON_OUT) {
  console.log(JSON.stringify(rows, null, 2));
} else {
  const head = [
    "file", "label", "ink%", "spill", "row", "margin",
    "traverse", "fr", "settle", "over", "mid", "card", "font", "hit", "esc", "clip", "PASS",
  ];
  const body = rows.map((r) => [
    r.file.slice(0, 16),
    r.labelClear ? "clear" : "COVERED",
    r.inkClear ? r.inkWorstPct : "CUT " + r.inkWorstPct,
    r.cardSpill,
    r.rowFits ? r.rowWidthPx : "OFF",
    r.rowMarginPx,
    (r.slideReads ? "" : "!") + r.traverseMs,
    r.traverseFrames,
    r.settleMs,
    r.overshootPx,
    r.defaultCentre ? r.defaultOn : "NO",
    r.minCardPx,
    r.minFontPx,
    r.minHitPx,
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

if (external.length) {
  console.error("\nexternal requests:\n" + [...new Set(external)].join("\n"));
  process.exitCode = 1;
}
if (errors.length) {
  console.error("\nconsole errors:\n" + errors.join("\n"));
  process.exitCode = 1;
}
if (rows.some((r) => !r.PASS)) process.exitCode = 1;
