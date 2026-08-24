/*
 * Drive every mockup the way a player does, and check what happened.
 *
 *     node mockups/door/drive.mjs           the table
 *     node mockups/door/drive.mjs --json    the raw rows
 *
 * `assert.js` measures a screen that is sitting still. This presses things.
 *
 * ---------------------------------------------------------------------------
 * WHY THE ROUND HAS TWO DRIVERS, WHICH NO EARLIER ONE NEEDED.
 *
 * Every previous round in this folder is about a LAYOUT: does the seat fit, does
 * the list get its share, is anything under 16px. A still is the whole subject,
 * so `measure.mjs` is the whole harness.
 *
 * This round's subject is a control. "Three cards that are actually selectable"
 * is a claim about what happens when you press something, and a mockup can
 * satisfy every measurement here while being unpressable -- which is exactly
 * what 04 was. Its Join tile passed the type floor, the target floor, the label
 * gate, the ink gate and the spill gate, and clicking it did nothing at all,
 * because the code field inside it sat in the plate's centre and swallowed the
 * click it had to swallow to be typeable. Nothing that measures a still could
 * ever have seen that.
 *
 * So the six things checked here are the six the brief actually asks for:
 *
 *   cold      the pad caption is up at load and retires on the first input
 *   default   the middle card is the one selected
 *   move      a direction moves the selection one place, once per press
 *   2tap      two taps inside a frame are two presses, not one
 *   wall      the end of the row refuses rather than wrapping
 *   press     the selected card commits, visibly
 *   code      where this direction put the pod code -- inline on the screen, or
 *             behind a hold that has to trap the row and close on B
 *   type      typing a code does not steer the row, and the press reads it
 *
 * `type` is there because the keyboard fallback maps `a`, `d`, `s` and `w` to
 * directions, and BRAMBLE has a `d` in it -- so a fallback written without care
 * silently steers the menu while somebody types a pod code. `PAD.start` returns
 * early on an input, and this is what says so.
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readdirSync } from "node:fs";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { chromium } = require(join(HERE, "..", "..", "frontend", "node_modules", "playwright"));

const JSON_OUT = process.argv.includes("--json");
const CODE = "BRAMBLE-4821";

const files = readdirSync(HERE).filter((f) => /^\d\d-.*\.html$/.test(f)).sort();
if (!files.length) throw new Error("no mockups here");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

/* The commit plate removes itself after 1400ms. Waiting it out between checks is
   what stops the next assertion reading the previous press's plate -- which
   reports every file as passing whatever it does. */
const COMMIT_MS = 1500;

const rows = [];
for (const file of files) {
  await page.goto("file://" + join(HERE, file).replace(/\\/g, "/"));
  await page.waitForTimeout(150);

  const r = { file };

  r.cold = await page.locator("#cold").isVisible();
  r.defaultOn = await page.evaluate(() => CARDS[DOOR.target].label);
  r.defaultCentre = (await page.evaluate(() => DOOR.target)) === 1;

  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(240);
  r.moved = (await page.evaluate(() => DOOR.target)) === 2;
  r.coldRetired = !(await page.locator("#cold").isVisible());

  /* The end of the row. It must refuse -- not wrap, and not silently do
     nothing: `DOOR.nudge` leans the spring into the wall and `PAD.rumble` is
     the redundant half. What can be checked from here is that the selection did
     not move; the lean is in the shots and the rumble is in your hands. */
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(240);
  r.wallHeld = (await page.evaluate(() => DOOR.target)) === 2;

  /*
   * ONE PRESS, ONE CHECK. This was two `ArrowLeft`s in a row followed by a
   * single assertion that the row had moved ONE place -- which passed, because
   * the keyboard fallback was silently merging two taps inside a frame into
   * one. The driver was asserting a bug as the expected result, and only
   * noticed when a slower spring changed the timing enough to stop merging.
   *
   * So each press is checked on its own, and the merge itself gets a test.
   */
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(120);
  const midStep = (await page.evaluate(() => DOOR.target)) === 1;
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(120);
  r.backToMid = midStep && (await page.evaluate(() => DOOR.target)) === 0;

  /* Two taps inside one frame are two presses. On a three-card row that is the
     difference between crossing it and stepping into the middle of it. */
  await page.evaluate(() => DOOR.select(0, true));
  await page.waitForTimeout(60);
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(200);
  r.doubleTap = (await page.evaluate(() => DOOR.target)) === 2;

  await page.evaluate(() => DOOR.select(1, true));
  await page.waitForTimeout(60);

  await page.keyboard.press("Enter");
  await page.waitForTimeout(90);
  r.press = (await page.locator("#commit").count()) ? await page.locator("#commit").textContent() : null;
  await page.waitForTimeout(COMMIT_MS);

  /* Hover selects, and it is the one interaction with a feedback loop in it --
     the card moves out from under the pointer that chose it. See `DOOR.wire`
     for the two rules that cut it. */
  await page.locator('[data-card="join"]').hover();
  await page.waitForTimeout(340);
  r.hoverSelects = (await page.evaluate(() => CARDS[DOOR.target].id)) === "join";

  /*
   * THE JOIN FLOW, WHICHEVER SHAPE THIS DIRECTION GAVE IT.
   *
   * Four files put the code field on the screen -- on a card, in a ledger, in
   * the strip, on a plate -- and 01 puts it behind a hold that opens when you
   * press Join, so the card stays a card. Both are legitimate answers and the
   * driver has to be able to check either, so it asks the screen rather than
   * assuming: press Join, and if something opened over the row, that is where
   * the field is.
   *
   * A hold gets three extra questions, which are the three that make an overlay
   * an overlay rather than a panel: does it take the input away from the row,
   * does B close it, and is what it opened over still there afterwards.
   */
  await page.evaluate(() => DOOR.select(2, true));
  await page.waitForTimeout(80);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(240);

  const hold = page.locator(".hold:not([hidden])");
  r.hold = (await hold.count()) > 0;

  if (r.hold) {
    /* The row must not move while a hold is up. */
    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(160);
    r.holdTraps = (await page.evaluate(() => DOOR.target)) === 2;

    await page.locator("#code").fill(CODE);
    r.typed = (await page.locator("#code").inputValue()) === CODE;
    r.rowHeld = (await page.evaluate(() => CARDS[DOOR.target].id)) === "join";

    /* B closes it, and the row is where it was. */
    await page.keyboard.press("Escape");
    await page.waitForTimeout(220);
    r.holdCloses =
      (await page.locator(".hold:not([hidden])").count()) === 0 &&
      (await page.evaluate(() => DOOR.target)) === 2;

    /* ...and round again, to the confirm. */
    await page.keyboard.press("Enter");
    await page.waitForTimeout(240);
    await page.locator("#code").fill(CODE);
    await page.locator('[data-testid="join-go"]').click();
  } else {
    r.holdTraps = null;
    r.holdCloses = null;
    const field = page.locator("#code");
    if (await field.count()) {
      await field.fill(CODE);
      r.typed = (await field.inputValue()) === CODE;
      r.rowHeld = (await page.evaluate(() => CARDS[DOOR.target].id)) === "join";
    } else {
      r.typed = null;
      r.rowHeld = null;
    }
    /* The id an e2e suite would drive, clicked at its centre, which is where
       Playwright and a thumb both aim. */
    await page.locator('[data-testid="join-pod"]').click();
  }

  await page.waitForTimeout(120);
  const plate = (await page.locator("#commit").count())
    ? await page.locator("#commit").textContent()
    : null;
  r.joinPress = plate;
  r.joinReadsCode = !!plate && plate.includes(CODE);
  await page.waitForTimeout(COMMIT_MS);

  r.PASS =
    r.cold && r.defaultCentre && r.moved && r.coldRetired && r.wallHeld &&
    r.backToMid && r.doubleTap && !!r.press && r.hoverSelects && r.typed !== false &&
    r.rowHeld !== false && r.joinReadsCode &&
    r.holdTraps !== false && r.holdCloses !== false;

  rows.push(r);
}

await browser.close();

if (JSON_OUT) {
  console.log(JSON.stringify(rows, null, 2));
} else {
  const head = ["file", "cold", "default", "move", "2tap", "wall", "press", "hover", "code", "type", "join", "PASS"];
  const body = rows.map((r) => [
    r.file.slice(0, 16),
    r.cold && r.coldRetired ? "up→gone" : "NO",
    r.defaultCentre ? r.defaultOn : "NO",
    r.moved && r.backToMid ? "yes" : "NO",
    r.doubleTap ? "two" : "LOST",
    r.wallHeld ? "holds" : "WRAPS",
    r.press ? "yes" : "NO",
    r.hoverSelects ? "yes" : "NO",
    r.hold ? (r.holdTraps && r.holdCloses ? "hold" : "HOLD!") : "inline",
    r.typed === null ? "-" : r.typed && r.rowHeld ? "safe" : "STEERS",
    r.joinReadsCode ? "reads" : "NO",
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
if (rows.some((r) => !r.PASS)) process.exitCode = 1;
