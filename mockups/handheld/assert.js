/*
 * The gates, as numbers.
 *
 * Paste into a DevTools console on any of the five, or run it through
 * `measure.py`, which drives all five and prints the README's table.
 *
 *     copy(JSON.stringify(HANDHELD_ASSERT(), null, 2))
 *
 * WHY THIS FILE EXISTS. The board round learned that `overflow: hidden` hides
 * layout failure completely -- the page reports `scrollHeight === clientHeight`
 * while the board visibly runs under the foot -- so a naive overflow check
 * passes straight through the exact bug it was written for. The lesson it drew
 * was: WHERE A VISUAL PROPERTY REDUCES TO A NUMBER, ASSERT THE NUMBER.
 *
 * This round has more of those than any earlier one, because "can you read this
 * on a 7-inch screen" and "can a thumb hit this" are both literally numbers.
 * The shipped client's own figures, measured at 1280x800 before any of this was
 * designed, are the baseline every gate is set against:
 *
 *     444 of 635 elements below 12px   ·   smallest 2.11px   ·   card width 73.6px
 */

function HANDHELD_ASSERT() {
  /* SCOPE: THE 1280x800 STAGE, NOT THE REVIEW CHROME AROUND IT.
     06 draws a bezel with the scale printed on it, and that caption is a note
     to whoever is reviewing -- it is not on the Deck's screen and holding it to
     the Deck's floor is measuring the wrong thing. Everything inside `.deck` is
     the design; everything outside it is the frame it is being shown in. */
  const ROOT = document.querySelector(".deck") || document.body;
  const FS_FLOOR = 16;      // nothing carrying information may be smaller
  const CARD_FLOOR = 96;    // any card the cursor can land on
  const HIT_FLOOR = 44;     // any focusable or tappable box
  const RING_FLOOR = 3;     // focus outline width

  const vis = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || +s.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  /* Only elements that OWN text. Walking every element counts a wrapper at its
     inherited size and reports failures that are not on screen.

     `aria-hidden` is skipped, and that is the honest line between a font-size
     floor and a font-size ban: this gate is about TEXT SOMEBODY READS. A type
     glyph on a card, the ↻ on a card with an ability, the ▲ on a staged
     attacker -- these are drawn as characters because that is cheaper than an
     SVG, but they are pictures, and every one of them is named in real type
     somewhere else on the screen. A mana pip is NOT in this set: its letter is
     the only thing telling you which mana it is, so it is held to the floor
     like any other word. The rule is that if hiding it from a screen reader
     would lose information, it is text. */
  const textOwners = [...ROOT.querySelectorAll("*")].filter((el) =>
    vis(el) &&
    !el.closest('[aria-hidden="true"]') &&
    [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));

  const sizes = textOwners.map((el) => ({
    px: Math.round(parseFloat(getComputedStyle(el).fontSize) * 100) / 100,
    text: el.textContent.trim().slice(0, 40),
    sel: el.className && typeof el.className === "string" ? "." + el.className.split(" ")[0] : el.tagName,
  }));

  const tooSmall = sizes.filter((s) => s.px < FS_FLOOR);

  // Every stop the cursor can reach, and every real button.
  const stops = [...ROOT.querySelectorAll("[data-stop], button")].filter(vis);
  const smallHits = stops
    .map((el) => ({ r: el.getBoundingClientRect(), sel: el.dataset.stop || el.textContent.trim().slice(0, 24) }))
    .filter((h) => h.r.width < HIT_FLOOR || h.r.height < HIT_FLOOR)
    .map((h) => ({ sel: h.sel, w: Math.round(h.r.width), h: Math.round(h.r.height) }));

  // Card width, read off a rendered face rather than off the token, because the
  // token is what the design INTENDED and the box is what the player got.
  const faces = [...ROOT.querySelectorAll(".face")].filter(vis);
  const faceW = faces.map((f) => f.getBoundingClientRect().width);
  /* The floor applies to a card that IS the identification of its object.
     `.face--thumb` marks one that sits beside its own name in real type, where
     the card is a row icon and the name is doing the work -- see faceHTML.
     Counted separately so the exemption is visible rather than invisible. */
  const reachableFaces = faces
    .filter((f) => f.closest("[data-stop]") && !f.classList.contains("face--thumb"))
    .map((f) => Math.round(f.getBoundingClientRect().width));

  // Exactly one cursor, and it is fully on screen. An offset focus ring clipped
  // by a parent is invisible focus, which is worse than none.
  const cursors = [...ROOT.querySelectorAll("[data-cursor]")];
  const cur = cursors[0];
  const curRect = cur ? cur.getBoundingClientRect() : null;
  const curOnScreen = curRect
    ? curRect.left >= -1 && curRect.top >= -1 &&
      curRect.right <= innerWidth + 1 && curRect.bottom <= innerHeight + 1
    : false;

  /* Read the STYLE as well as the width. `outline-width: 3px` with
     `outline-style: none` computes as a perfectly healthy 3, and draws nothing
     -- which is exactly what a bare `:focus { outline: none }` does to the
     cursor, and exactly what this check missed the first time it was written. */
  const ring = cur ? getComputedStyle(cur, null) : null;
  const ringStyle = ring ? ring.outlineStyle : "none";
  const ringW = ring && ringStyle !== "none" ? parseFloat(ring.outlineWidth) || 0 : 0;

  // Spill: measure the CHILDREN against the foot, never the stretched container
  // -- a grid-stretched box always ends exactly at its row edge no matter how
  // far the cards inside overflow it.
  const foot = ROOT.querySelector(".hints") || ROOT.querySelector(".foot");
  const footTop = foot ? foot.getBoundingClientRect().top : innerHeight;
  const spill = [...ROOT.querySelectorAll(".slot, .tile")]
    .filter(vis)
    .map((el) => el.getBoundingClientRect())
    .filter((r) => r.bottom > footTop + 1).length;

  // Collapse: any scrolling or flexible region silently flattened to zero.
  const collapsed = [...ROOT.querySelectorAll(".pane, .strip__b, .grid, .lane, .cat, .seats")]
    .filter((el) => getComputedStyle(el).display !== "none")
    .filter((el) => el.getBoundingClientRect().height < 1).length;

  const out = {
    screen: `${innerWidth}x${innerHeight}`,
    dpr: devicePixelRatio,

    // The gate this round exists for
    minFontPx: sizes.length ? Math.min(...sizes.map((s) => s.px)) : null,
    textNodes: sizes.length,
    belowFloor: tooSmall.length,
    belowFloorWorst: tooSmall.sort((a, b) => a.px - b.px).slice(0, 6),

    minCardPx: reachableFaces.length ? Math.min(...reachableFaces) : null,
    maxCardPx: faceW.length ? Math.round(Math.max(...faceW)) : null,
    thumbsExempted: faces.filter((f) => f.classList.contains("face--thumb")).length,

    stops: stops.length,
    smallHits: smallHits.length,
    smallHitsWorst: smallHits.slice(0, 6),

    cursors: cursors.length,
    cursorOnScreen: curOnScreen,
    ringWidthPx: ringW,
    ringStyle,

    spilledElements: spill,
    collapsedRegions: collapsed,

    // Native tooltips do not exist on a controller. The shipped client has 45.
    titleAttrs: ROOT.querySelectorAll("[title]").length,

    // Art is never drawn above ~1.25x of art_crop's native 626x457.
    oversizedArt: [...ROOT.querySelectorAll(".face__art")]
      .filter((i) => i.getBoundingClientRect().width > 780).length,

    brokenImages: [...ROOT.querySelectorAll("img")].filter((i) => i.complete && i.naturalWidth === 0).length,
    presses: typeof Pad !== "undefined" ? Pad.presses() : null,
  };

  /* NEVER TWO CURSORS, rather than always exactly one.
     Two is always a bug -- a controller UI's one unforgivable failure is the
     player not knowing which of two highlighted things they are on. Zero is a
     legitimate position and two directions here take it: 02's board has no
     resting cursor because nothing is selected until you hold L2, and 04 has no
     board to put one on. Failing them for it would be the gate enforcing 01's
     design on the other four, which is the opposite of what a round is for. So
     zero is reported and compared, not failed; the ring is only checked when
     there is a cursor to draw it on. */
  out.PASS =
    out.belowFloor === 0 &&
    (out.minCardPx === null || out.minCardPx >= CARD_FLOOR) &&
    out.smallHits === 0 &&
    out.cursors <= 1 &&
    (out.cursors === 0 || (out.cursorOnScreen && out.ringWidthPx >= RING_FLOOR)) &&
    out.spilledElements === 0 &&
    out.collapsedRegions === 0 &&
    out.titleAttrs === 0 &&
    out.oversizedArt === 0 &&
    out.brokenImages === 0;

  return out;
}

if (typeof window !== "undefined") window.HANDHELD_ASSERT = HANDHELD_ASSERT;
