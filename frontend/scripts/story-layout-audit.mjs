/**
 * Audit every Storybook story for layout failure, desktop vs handheld.
 *
 *     npm run storybook            # in one terminal
 *     npm run audit:stories        # in another
 *     npm run audit:stories -- --only=lobby --limit=20
 *
 * ## Why a paired run
 *
 * The question worth asking is not "does this story have findings" -- plenty
 * have had one forever and nobody minds -- but "does turning the handheld
 * layout ON break it". So every story is measured twice, desktop then handheld,
 * and only the DELTA is reported. A single-mode run was tried first and buried
 * the signal: 25 stories had findings on desktop and the interesting ones were
 * not among them.
 *
 * ## What it looks for
 *
 * Two things, both structural rather than aesthetic, because those are the ones
 * a machine can be trusted with:
 *
 *   - **bleed** -- a box outside the viewport. A story canvas is the whole
 *     window, so anything past its edge is unreachable.
 *   - **clipped** -- `scrollHeight > clientHeight` on a non-`visible` overflow.
 *     Content the box cannot show.
 *
 * Deliberate truncation is excluded: an element with `line-clamp` or an
 * ellipsis is doing what it was told, and counting it drowns the real findings.
 *
 * ## What it found
 *
 * 112 of 308 stories, on the run that introduced it. The largest single cause
 * was one missing declaration -- `testing/mounts.tsx` hard-coded the board's
 * DESKTOP grid column, so every card story drew its mat at the right rail's
 * width with the cards off the screen. Fifty-odd stories, invisible to the
 * suite, and it also found a discard prompt with 668px of overflow and a seat
 * arrangement that failed at exactly two opponents -- the density between the
 * two the e2e gate covered. See handheld playtest loop 7.
 *
 * It is a sweep, not a gate: it needs Storybook running and takes a few
 * minutes. The gates are `e2e/deckfit.spec.ts` and `e2e/handheldAssert.ts`.
 */
import { chromium } from "playwright";

const SB = "http://127.0.0.1:6007";
const only = (process.argv.find((a) => a.startsWith("--only=")) ?? "").slice(7);
const limit = Number(
  (process.argv.find((a) => a.startsWith("--limit=")) ?? "--limit=9999").slice(8),
);

const index = await (await fetch(`${SB}/index.json`)).json();
let stories = Object.values(index.entries).filter((e) => e.type === "story");
if (only)
  stories = stories.filter((s) =>
    (s.title + s.name + s.id).toLowerCase().includes(only.toLowerCase()),
  );
stories = stories.slice(0, limit);

const audit = () => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const out = { bleed: [], clipped: [] };
  const path = (el) => {
    const bits = [];
    for (let n = el; n && n.nodeType === 1 && bits.length < 3; n = n.parentElement) {
      const c = n.className && typeof n.className === "string" ? n.className.split(" ")[0] : "";
      bits.unshift(c ? `.${c}` : n.tagName.toLowerCase());
    }
    return bits.join(">");
  };
  const visible = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || s.opacity === "0") return false;
    const b = el.getBoundingClientRect();
    return b.width > 0.5 && b.height > 0.5;
  };
  const seen = new Set();
  for (const el of document.querySelectorAll("body *")) {
    if (!visible(el)) continue;
    const b = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const p = path(el);
    if (b.right > vw + 2 || b.left < -2 || b.bottom > vh + 2 || b.top < -2) {
      // Report the outermost offender per path, not every descendant of it.
      const key = `b:${p}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.bleed.push({
          p,
          r: [Math.round(b.left), Math.round(b.top), Math.round(b.right), Math.round(b.bottom)],
        });
      }
    }
    const oy = el.scrollHeight - el.clientHeight;
    const ox = el.scrollWidth - el.clientWidth;
    // A line clamp and an ellipsis are deliberate truncation, not a layout
    // failure -- the element is doing exactly what it was told to.
    const clamped =
      (s.webkitLineClamp && s.webkitLineClamp !== "none") || s.textOverflow === "ellipsis";
    if ((oy > 2 || ox > 2) && s.overflow !== "visible" && !clamped) {
      const key = `c:${p}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.clipped.push({ p, oy, ox, ov: s.overflow });
      }
    }
  }
  return {
    ...out,
    docScroll: document.documentElement.scrollHeight - document.documentElement.clientHeight,
  };
};

const settle = async (page) => {
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
  await page
    .waitForFunction(
      () =>
        document
          .getAnimations()
          .filter((a) => Number.isFinite(a.effect?.getTiming().iterations ?? 1))
          .every((a) => a.playState !== "running"),
      undefined,
      { timeout: 3000 },
    )
    .catch(() => {});
  await page.waitForTimeout(120);
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

const run = async (s, mode, input) => {
  const url = `${SB}/iframe.html?id=${s.id}&globals=handheld:${mode};input:${input}&viewMode=story`;
  await page.goto(url, { waitUntil: "load", timeout: 20000 });
  await settle(page);
  return page.evaluate(audit);
};

const score = (r) => r.bleed.length * 2 + r.clipped.length + (r.docScroll > 2 ? 3 : 0);

const rows = [];
for (const s of stories) {
  try {
    const off = await run(s, "off", "mouse");
    const on = await run(s, "on", "pad");
    rows.push({ s, off, on, d: score(on) - score(off) });
  } catch (e) {
    rows.push({ s, err: String(e).slice(0, 90) });
  }
}
await browser.close();

const broken = rows.filter((r) => r.err || r.d > 0).sort((a, b) => (b.d ?? 99) - (a.d ?? 99));
console.log(`\n${broken.length}/${rows.length} stories that HANDHELD makes worse\n`);
for (const r of broken.slice(0, 30)) {
  if (r.err) {
    console.log(`  ERROR ${r.s.title}/${r.s.name}: ${r.err}`);
    continue;
  }
  console.log(`+${r.d}  ${r.s.title} / ${r.s.name}   (${r.s.id})`);
  if (r.on.docScroll > 2 && r.off.docScroll <= 2)
    console.log(`      document scrolls by ${r.on.docScroll}`);
  const offB = new Set(r.off.bleed.map((b) => b.p));
  const offC = new Set(r.off.clipped.map((c) => c.p));
  for (const b of r.on.bleed.filter((b) => !offB.has(b.p)).slice(0, 3))
    console.log(`      bleed   ${b.p} [${b.r}]`);
  for (const c of r.on.clipped.filter((c) => !offC.has(c.p)).slice(0, 3))
    console.log(`      clipped ${c.p} oy=${c.oy} ox=${c.ox}`);
}
const byTitle = {};
for (const r of broken) byTitle[r.s.title] = (byTitle[r.s.title] ?? 0) + 1;
console.log("\nby component:");
for (const [t, n] of Object.entries(byTitle).sort((a, b) => b[1] - a[1]))
  console.log(`  ${String(n).padStart(3)}  ${t}`);
