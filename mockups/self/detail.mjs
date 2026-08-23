/*
 * One orb, big, for looking at rather than measuring.
 *
 *     node mockups/self/detail.mjs 01-ledger.html cmdzone
 *
 * `measure.mjs` renders the whole 1280x800 Deck, which is the right frame for
 * judging footprint and the wrong one for judging a 148px caption strip -- at
 * 90% of a screenshot the difference between a mana symbol and a grey rectangle
 * is a few pixels. This clips to the panel and renders it at 3x, which is the
 * same thing `../seat/shots/06-muster-detail.png` exists for.
 */

import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { mkdirSync } from "node:fs";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = require(join(HERE, "..", "..", "frontend", "node_modules", "playwright"));

const FILE = process.argv[2] || "01-ledger.html";
const STATE = process.argv[3] || "priority";
const MARKS = ["rest", "priority", "spending", "cmdzone", "unpaid", "out", "noart"];

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 3,
});
page.on("pageerror", (e) => console.log("PAGEERROR", String(e)));
page.on("console", (m) => m.type() === "error" && console.log("CONSOLE", m.text()));

await page.goto(pathToFileURL(join(HERE, FILE)).href);

let at = MARKS.indexOf("priority");
while (MARKS[at] !== STATE) {
  await page.keyboard.press("s");
  at = (at + 1) % MARKS.length;
}
await page.waitForTimeout(120);

const orb = await page.$(".orb");
mkdirSync(join(HERE, "shots"), { recursive: true });
const out = join(HERE, "shots", FILE.replace(".html", "") + "-" + STATE + "-detail.png");
await orb.screenshot({ path: out });
console.log(out);

await browser.close();
