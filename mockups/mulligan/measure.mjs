/*
 * The table in `README.md`, taken from the rendered files rather than typed.
 *
 *     node mockups/mulligan/measure.mjs
 *
 * One question per column, and all three are questions a still cannot answer by
 * being looked at:
 *
 *   CARD     how wide the hand is drawn, which is the number every direction is
 *            really trading against something else
 *   NAMES    how many of the seven names FIT -- `scrollWidth > clientWidth` on
 *            `.face__name`, which is what ellipsis actually means. A name that
 *            has been cut is a card you identify by its art, and three of the
 *            seven in this hand are green.
 *   COVERED  how much of each face its neighbour is sitting on. This is what
 *            decides whether the mana cost survives, because the cost is the
 *            rightmost thing in the head.
 */

import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { readdirSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "../../frontend/package.json"));
const { chromium } = require("playwright");

const files = readdirSync(here).filter((f) => /^\d\d-.*\.html$/.test(f)).sort();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1306, height: 840 } });

const rows = [];
for (const file of files) {
  await page.goto(pathToFileURL(join(here, file)).href);
  await page.waitForTimeout(1200);
  rows.push(
    await page.evaluate(() => {
      const faces = [...document.querySelectorAll(".deck .face")]
        .filter((f) => f.closest("[data-i], .fan__slot"));
      /*
       * `offsetWidth`, NOT `getBoundingClientRect().width`.
       *
       * Three of the five fan their cards, and a rect is the AXIS-ALIGNED BOX of
       * a rotated element -- so 01's 176px card measured 202 and 04's 172
       * measured 220, both of them reporting the rotation as if it were card.
       * The first table this script printed had every fanned direction 15-28%
       * too wide and 05, which does not rotate, correct -- which is exactly the
       * shape of error that gets believed.
       */
      const w = faces.length ? faces[0].offsetWidth : 0;
      /* Strict, for `probe.mjs`'s reason: an ellipsis appears at one pixel of
         overflow, so a tolerance here undercounts the cut names by exactly the
         borderline cases -- which are the ones a width table is for. */
      const cut = faces.filter((f) => {
        const n = f.querySelector(".face__name");
        return n && n.scrollWidth > n.clientWidth;
      }).length;
      /* Pitch from the two leftmost slots' laid-out positions, for the same
         reason. A row whose pitch exceeds the card width reports a negative
         cover, which is a gap -- one figure rather than two. */
      let covered = 0;
      if (faces.length > 1) {
        const a = faces[0].closest("[data-i], .fan__slot") || faces[0];
        const b = faces[1].closest("[data-i], .fan__slot") || faces[1];
        if (a.offsetParent === b.offsetParent) covered = w - (b.offsetLeft - a.offsetLeft);
      }
      return { faces: faces.length, w, cut, covered };
    })
  );
}
await browser.close();

const pad = (s, n) => String(s).padEnd(n);
console.log(pad("file", 32) + pad("cards", 7) + pad("card w", 8) + pad("names cut", 11) + "covered");
files.forEach((f, i) => {
  const r = rows[i];
  console.log(
    pad(f, 32) + pad(r.faces, 7) + pad(r.w + "px", 8) +
    pad(r.cut + " of " + r.faces, 11) +
    (r.covered > 0 ? r.covered + "px" : r.covered === 0 ? "flush" : (-r.covered) + "px gap")
  );
});

/*
 * THE SECOND TABLE, and it is the one that decides the round.
 *
 * Every direction above cuts the same three names, at five different card
 * widths, which is not a coincidence -- so the question is not "how wide should
 * the card be" but "how wide would it have to be", and that has an answer.
 *
 * Measured off 05 because 05 is the only file whose row neither rotates nor
 * overlaps: a card there is exactly as wide as it is laid out, so
 * `.face__name`'s `scrollWidth` is the text and nothing else. A name that FITS
 * reports its box rather than its text, so only the cut rows are readings --
 * which is enough, because the widest requirement is necessarily among them.
 */
const need = await (async () => {
  const b2 = await chromium.launch();
  const p2 = await b2.newPage({ viewport: { width: 1306, height: 840 } });
  await p2.goto(pathToFileURL(join(here, "05-the-second-question.html")).href);
  await p2.waitForTimeout(900);
  const out = await p2.evaluate(() => {
    const rowsOut = [];
    for (const f of document.querySelectorAll(".deck .face")) {
      const head = f.querySelector(".face__head");
      const n = f.querySelector(".face__name");
      const c = f.querySelector(".face__cost");
      const cs = getComputedStyle(head);
      const chrome =
        parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + (parseFloat(cs.gap) || 0) + 4;
      const costW = c ? c.getBoundingClientRect().width : 0;
      rowsOut.push({
        name: n.textContent,
        fits: n.scrollWidth <= n.clientWidth,
        needs: Math.ceil(n.scrollWidth + costW + chrome),
      });
    }
    return rowsOut;
  });
  await b2.close();
  return out;
})();

console.log("");
console.log("what each card would need, to print its name and cost at 16px:");
for (const r of need) {
  console.log("  " + pad(r.name, 26) + pad(r.needs + "px", 8) + (r.fits ? "(fits — box, not text)" : ""));
}
const worst = need.filter((r) => !r.fits).reduce((a, b) => (b.needs > a.needs ? b : a));
console.log("");
console.log("  widest:                    " + worst.name + " at " + worst.needs + "px");
console.log("  seven of those, flush:     " + worst.needs * 7 + "px");
console.log("  the panel:                 1280px");
console.log("  seven flush across 1280:   " + Math.floor(1280 / 7) + "px each");
