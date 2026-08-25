/*
 * Shoot every direction at 1280x800, and run its own gates while there.
 *
 *     node mockups/mulligan/shoot.mjs            all five
 *     node mockups/mulligan/shoot.mjs 03         one
 *
 * The viewport is 1306x840 rather than 1280x800 on purpose: `STAGE.fit` sizes
 * the deck to `(innerWidth - 26) / 1280` and `(innerHeight - 40) / 800`, so
 * those are the two numbers at which the scale is exactly 1 and the PNG is the
 * panel pixel for pixel. Shooting at 1280x800 would hand back a 96% deck and
 * every measurement taken off the image would be quietly 4% small.
 *
 * `MULL_ASSERT` runs in the page, not here, because two of its three gates are
 * about COMPUTED type and rendered boxes -- facts that only exist once a
 * browser has laid the thing out. A gate written in Node against the stylesheet
 * would be checking what the file says instead of what the screen does, which
 * is the failure `../handheld-board/README.md` built `seatsAgree` to stop.
 */

import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { readdirSync, mkdirSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "../../frontend/package.json"));
const { chromium } = require("playwright");

const only = process.argv[2];
const files = readdirSync(here)
  .filter((f) => /^\d\d-.*\.html$/.test(f))
  .filter((f) => !only || f.startsWith(only))
  .sort();

mkdirSync(join(here, "shots"), { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1306, height: 840 } });

let bad = 0;
for (const file of files) {
  await page.goto(pathToFileURL(join(here, file)).href);
  await page.waitForSelector(".deck");
  // The deal animation is 460ms plus a 90 + 6*70 stagger; nothing is where it
  // belongs until it has finished.
  await page.waitForTimeout(1200);

  /* WARM BEFORE SHOOTING. The cold caption sits at the foot of the deck, which
     is also where every direction puts its commitment, so a cold shot of 02 is
     a picture of the Keep plate with a pill across its subtitle. That is a real
     overlap for about half a second and a misleading one for the rest of the
     game, and the shots are what the round is reviewed from. 01's own cold
     frame is shot separately below. */
  await page.evaluate(() => STAGE.warm());

  const scale = await page.evaluate(() => STAGE.scale);
  if (Math.abs(scale - 1) > 0.001) {
    console.log(`  ! ${file}: deck is at ${(scale * 100).toFixed(1)}%, not 100%`);
    bad += 1;
  }

  const fails = await page.evaluate(() => MULL_ASSERT());
  const shot = file.replace(/\.html$/, ".png");
  await page.locator(".deck").screenshot({ path: join(here, "shots", shot) });

  if (fails.length === 0) {
    console.log(`  ok ${file}  ->  shots/${shot}`);
  } else {
    bad += fails.length;
    console.log(`  ${fails.length} FAIL ${file}`);
    for (const f of fails) console.log(`      ${f}`);
  }

  /* Every file that has more than one state shoots each of them. `STATES` is
     the file's own list; a file without one has a single frame and says so by
     not declaring it. */
  const states = await page.evaluate(() => (typeof STATES === "undefined" ? [] : STATES));
  for (const s of states) {
    await page.evaluate((name) => GOTO(name), s);
    await page.waitForTimeout(500);
    const more = await page.evaluate(() => MULL_ASSERT());
    const alt = file.replace(/\.html$/, `-${s}.png`);
    await page.locator(".deck").screenshot({ path: join(here, "shots", alt) });
    if (more.length) {
      bad += more.length;
      console.log(`  ${more.length} FAIL ${file} [${s}]`);
      for (const f of more) console.log(`      ${f}`);
    } else {
      console.log(`  ok ${file} [${s}]  ->  shots/${alt}`);
    }
  }
}

/* One picture of the state every file opens in, taken once rather than five
   times: it is the same pill in the same place on all five. */
await page.goto(pathToFileURL(join(here, files[0] || "01-the-deal.html")).href);
await page.waitForTimeout(1200);
await page.locator(".deck").screenshot({ path: join(here, "shots", "00-cold.png") });
console.log("  ok cold state  ->  shots/00-cold.png");

await browser.close();
process.exit(bad ? 1 : 0);
