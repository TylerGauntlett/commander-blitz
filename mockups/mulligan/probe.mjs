/*
 * How wide a card has to be before it can carry its own rules text at 16px.
 *
 *     node mockups/mulligan/probe.mjs
 *
 * This is the round's second measurement and it answers a different question
 * from `measure.mjs`. That one asks how wide the cards ARE in each direction
 * and what gets cut. This one asks what width would be ENOUGH -- for the whole
 * card, name and cost and type line and rules text, at the floor.
 *
 * It works by binary search on a real `.face--full` in a real browser, because
 * the thing being searched for is a text reflow and there is no closed form for
 * it: a card is a fixed 1.4 portrait, its head, type line, rules box and footer
 * are all sized by their own text and cannot shrink, and the ILLUSTRATION is
 * the only member that gives. So the search is for the width at which the fixed
 * members stop overflowing a box that is 1.4 times as tall as it is wide.
 *
 * Two answers per card, because they are two different design questions:
 *
 *   TEXT      the narrowest card that shows everything, with the illustration
 *             squeezed to whatever is left -- possibly nothing
 *   CARD      the narrowest card that shows everything AND keeps a third of its
 *             height as picture, which is about where it stops looking like a
 *             Magic card and starts looking like a rules pane with a stripe
 *
 * It probes against 01's page rather than a fixture of its own, so it is
 * measuring the same stylesheet, the same font stack and the same seven cards
 * the round is drawn with.
 */

import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "../../frontend/package.json"));
const { chromium } = require("playwright");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1306, height: 840 } });
await page.goto(pathToFileURL(join(here, "01-the-deal.html")).href);
await page.waitForTimeout(900);

const results = await page.evaluate(async () => {
  const host = document.createElement("div");
  /* Off-stage but LAID OUT. `display: none` measures nothing and `visibility:
     hidden` still reflows, but a probe inside `.deck` would be inside a scaled
     transform -- and every reading would come back multiplied by 0.98 or
     whatever the window happened to be. */
  host.style.cssText = "position:fixed;left:-4000px;top:0;";
  document.body.appendChild(host);

  const fits = (card, w) => {
    host.innerHTML = fullFaceHTML(card, { w, fs: 16 });
    const face = host.firstChild;
    const name = face.querySelector(".face__name");
    const type = face.querySelector(".ffull__type");
    const art = face.querySelector(".ffull__art");
    /*
     * STRICT ON THE TWO WIDTHS, and the slack on the height is a different
     * thing rather than an inconsistency.
     *
     * `text-overflow: ellipsis` fires the moment `scrollWidth` exceeds
     * `clientWidth` by anything at all, so a `+1` tolerance here is not
     * absorbing subpixel noise -- it is calling a line that HAS an ellipsis on
     * it "fitting". This probe reported Tatyova at 295px on exactly that
     * margin: 292 against 291, one pixel, and the raised card in every file
     * came out reading "Legendary Creature — Merfolk Dru...". Found by looking
     * at a screenshot of the thing the measurement had already approved.
     *
     * The height keeps its pixel because it is a different mechanism: nothing
     * is clipped at +1, the box is simply that much taller than its content
     * box after rounding, and being strict there makes the search fail on
     * fractional layout rather than on anything visible.
     */
    return {
      ok:
        name.scrollWidth <= name.clientWidth &&
        type.scrollWidth <= type.clientWidth &&
        face.scrollHeight <= face.clientHeight + 1,
      artFrac: art.clientHeight / face.clientHeight,
    };
  };

  /* Integer bisection over [120, 900]. Monotone in width for every card here:
     more width is fewer lines is less fixed height. */
  const search = (card, extra) => {
    let lo = 120;
    let hi = 900;
    if (!(extra ? extra(fits(card, hi)) : fits(card, hi).ok)) return null;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      const r = fits(card, mid);
      if (extra ? extra(r) : r.ok) hi = mid;
      else lo = mid + 1;
    }
    return lo;
  };

  const out = HAND.map((c) => ({
    name: c.name,
    text: search(c),
    card: search(c, (r) => r.ok && r.artFrac >= 1 / 3),
    lines: (c.oracle || "").length,
  }));
  host.remove();
  return out;
});

await browser.close();

const pad = (s, n) => String(s).padEnd(n);
console.log(pad("card", 26) + pad("oracle", 8) + pad("TEXT", 8) + "CARD");
for (const r of results) {
  console.log(pad(r.name, 26) + pad(r.lines + "ch", 8) + pad(r.text + "px", 8) + r.card + "px");
}

const worstText = Math.max(...results.map((r) => r.text));
const worstCard = Math.max(...results.map((r) => r.card));
console.log("");
console.log("  widest TEXT:                " + worstText + "px");
console.log("  widest CARD:                " + worstCard + "px");
console.log("  seven at TEXT, flush:       " + worstText * 7 + "px");
console.log("  seven at CARD, flush:       " + worstCard * 7 + "px");
console.log("  the panel:                  1280px");
console.log("");
console.log("  one at CARD + six at 168:   " + (worstCard + 6 * 168) + "px  (a fan, un-overlapped)");
console.log("  ...with 40px of overlap:    " + (worstCard + 6 * 128) + "px");
