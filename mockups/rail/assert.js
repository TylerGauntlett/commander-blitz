/*
 * The gates, as numbers.
 *
 * Inlined into every file by `inline.py`, so opening any mockup and typing
 * `RAIL_ASSERT()` in the console works with no server and no paste -- `fetch()`
 * is blocked on file://, so a page cannot load its own checker off disk. `m`
 * runs it and draws the failures on the elements that failed.
 *
 *     copy(JSON.stringify(RAIL_ASSERT(), null, 2))
 *
 * Four of these are `../handheld/assert.js`'s, unchanged, because this round is
 * one column of that round's screen and a floor that only applies to the rest of
 * the screen is not a floor: 16px of type, 44px of target, zero native tooltips,
 * nothing escaping its box.
 *
 * THREE ARE NEW, AND THEY ARE THE ONES THIS ROUND EXISTS FOR.
 *
 * `listShare` -- how much of the rail is actually the decision. This is the
 * complaint the round was opened on, reduced to a fraction.
 * `handheld.css:1540-1554` records the shipped column: 514px, of which the
 * preview takes 152, the stack 84, the gaps 16, and the action panel 262 -- and
 * inside that panel the pane's own chrome takes ~22 and the prompt and its help
 * line ~68, so the rows get 172. **A third of the column is the thing the turn
 * is spent in.** A direction that does not move that number has not answered the
 * complaint however good it looks.
 *
 * `surfaces` -- how many boxed containers the rail draws. The shipped rail is
 * four: stack pane, preview pane, action pane, commit dock. Four bordered wells
 * stacked in a 243px column is why it reads as a control panel from a different
 * application than the board beside it. A number is not a verdict -- a direction
 * may spend a second surface on purpose to separate the choices from the
 * commit -- but it forbids spending one by accident.
 *
 * `scrollers` and `overflowing` -- the reflow-on-hover defect, as a count.
 * `.stackpanel` and `.acts__list` both scroll (handheld.css:1571-1599) and the
 * styled `::-webkit-scrollbar` (theme.css:403) is a classic bar, so it takes 8px
 * out of the content box the instant it appears and every row re-wraps under the
 * pointer. Two numbers, because they fail differently: a scroller with a
 * reserved gutter is fine, and a scroller that is ALREADY overflowing at rest is
 * a list too short for its own content.
 */

function RAIL_ASSERT() {
  const DECK = document.querySelector(".deck") || document.body;
  const FS_FLOOR = 16;
  const HIT_FLOOR = 44;

  const round = (n) => Math.round(n * 100) / 100;

  const vis = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || +s.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  /* SCOPE: THE RAIL, NOT THE GHOST AROUND IT.
     The ghosted board and fan are not the design -- they are the room the design
     is spending, drawn so the spend is visible. The bezel tag is a note to
     whoever is reviewing and is not on the Deck's screen. Everything inside
     `.rail` is the design; the holds are too, and are measured when open. */
  const rail = DECK.querySelector(".rail");
  if (!rail) return { PASS: false, why: "no .rail" };

  const holds = [...DECK.querySelectorAll(".over")].filter((el) => !el.hidden);
  const roots = [rail, ...holds];

  const scale = DECK.getBoundingClientRect().width / (DECK.offsetWidth || 1) || 1;
  const px = (n) => Math.round(n / scale);

  const all = roots.flatMap((r) => [...r.querySelectorAll("*")]).filter(vis);
  const faults = [];

  /* --- The type floor ---------------------------------------------------
     Only elements that OWN text: walking every element counts a wrapper at its
     inherited size and reports failures that are not on screen. `aria-hidden` is
     skipped, which is the honest line between a font-size floor and a font-size
     ban -- this gate is about TEXT SOMEBODY READS. If hiding it from a screen
     reader would lose information, it is text. */
  const textOwners = all.filter(
    (el) =>
      !el.closest('[aria-hidden="true"]') &&
      [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
  );

  const sizes = textOwners.map((el) => ({
    el,
    /* A font size is a CSS pixel and the bezel's `transform: scale()` does not
       change it -- only the boxes below are read through the scale. Dividing
       here reports a 16px floor as 17.9 and passes type that fails on the
       device. `../seat/assert.js` learned this the hard way. */
    px: round(parseFloat(getComputedStyle(el).fontSize)),
    text: el.textContent.trim().slice(0, 32),
  }));
  const belowFloor = sizes.filter((s) => s.px < FS_FLOOR).sort((a, b) => a.px - b.px);
  for (const s of belowFloor.slice(0, 8)) faults.push({ el: s.el, why: s.px + "px" });

  /* --- The target floor -------------------------------------------------
     Every row in this rail is the only route to the action it names. A row a
     thumb cannot land on is not a control on this device. */
  const stops = roots.flatMap((r) => [...r.querySelectorAll("button, [data-stop]")]).filter(vis);
  const hits = stops.map((el) => {
    const r = el.getBoundingClientRect();
    return { el, w: px(r.width), h: px(r.height) };
  });
  const smallHits = hits.filter((h) => h.w < HIT_FLOOR || h.h < HIT_FLOOR);
  for (const h of smallHits.slice(0, 8)) faults.push({ el: h.el, why: h.w + "×" + h.h });

  /* --- The round's own gate: how much of the column is the decision ------ */
  const railBox = rail.getBoundingClientRect();
  const list = rail.querySelector(".list");
  const listBox = list ? list.getBoundingClientRect() : { height: 0 };
  const railPx = px(railBox.height);
  const listPx = px(listBox.height);

  /* Rows, not pixels, is what a player experiences. 44 + the 6px gutter. */
  const rowsVisible = Math.floor((listPx + 6) / (HIT_FLOOR + 6));

  /* --- Surfaces: boxed containers inside the rail ------------------------
     A "surface" is something that draws itself as a plate -- it has a visible
     border AND a background of its own. Rows are not surfaces; they are the
     content. The shipped rail draws four. */
  const surfaceEls = [rail, ...rail.querySelectorAll("*")].filter((el) => {
    if (!vis(el)) return false;
    /* A SURFACE IS A CONTAINER, not anything that happens to draw a plate.
       Requiring element children is what separates the two, and it matters:
       without it a filled outcome dot -- a 12px circle with a border and a
       background -- counted as a surface, and 02's gate reported three where
       there is one. `button` is out for the same reason: a control that draws
       itself is a control, and every row and mark in this round is one. */
    if (el.children.length === 0) return false;
    if (el.tagName === "BUTTON") return false;
    if (el.matches(".sitem, .cost, .key")) return false;
    const s = getComputedStyle(el);
    const bg = s.backgroundColor;
    const transparent = bg === "transparent" || /rgba\(.*,\s*0\)$/.test(bg);
    const bordered = parseFloat(s.borderTopWidth) > 0 || parseFloat(s.borderLeftWidth) > 0;
    return !transparent && bordered;
  });

  /* --- Scroll containers ------------------------------------------------- */
  const scrollEls = all.filter((el) => {
    const s = getComputedStyle(el);
    return s.overflowY === "auto" || s.overflowY === "scroll";
  });
  const overflowing = scrollEls.filter((el) => el.scrollHeight > el.clientHeight + 1);
  /* A scroller with no reserved gutter is the reflow bug waiting to happen, and
     it is invisible until content crosses the line. Asked of every one. */
  const ungutteredEls = scrollEls.filter(
    (el) => getComputedStyle(el).scrollbarGutter.indexOf("stable") < 0
  );
  for (const el of ungutteredEls.slice(0, 4)) faults.push({ el, why: "no gutter" });

  /* --- Escape ------------------------------------------------------------
     `overflow: hidden` hides layout failure completely -- the page reports
     `scrollHeight === clientHeight` while content visibly runs under the next
     region -- which is the lesson the board round drew, so this is measured
     against the rail's own box rather than asked of the scroller.

     THE AXIS DEPENDS ON WHETHER THE ELEMENT IS IN A SCROLLER, and getting that
     wrong is how the first version of this gate reported 18 escapes on a file
     with nothing wrong. A row scrolled below the fold of `.list` is not
     escaping -- being outside the visible box on the scroll axis is the entire
     point of a scroll container. What is still a failure there is escaping
     SIDEWAYS: `.list` scrolls vertically only, so a row wider than its box is
     content the player cannot reach by any gesture.

     Outside a scroller both axes count, which is where the real defect lives --
     the rail running under the foot.

     Hover labels are absolutely positioned outside their control on purpose --
     that is the whole "put the name one input away" mechanism -- and they are
     invisible at rest, so `vis()` has already excluded them. */
  let escaped = 0;
  for (const r of roots) {
    const rootBox = r.getBoundingClientRect();
    for (const el of [...r.querySelectorAll("*")].filter(vis)) {
      const scroller = el.parentElement && el.parentElement.closest(".list");
      const box = scroller ? scroller.getBoundingClientRect() : rootBox;
      const b = el.getBoundingClientRect();
      const out =
        b.left < box.left - 1 || b.right > box.right + 1 ||
        (!scroller && (b.top < box.top - 1 || b.bottom > box.bottom + 1));
      if (out) {
        escaped += 1;
        if (escaped <= 4) faults.push({ el, why: "escapes" });
      }
    }
  }

  /* Text being ellipsised. Not a failure on its own -- a card name truncating in
     a 243px column is the trade `.act__type`'s drop already accepted -- but a
     direction that clips a NUMBER has lost the datum, and this is how you see
     which. Asked only of boxes that actually cut: `scrollWidth` on an
     `overflow: visible` box counts absolutely-positioned descendants, which here
     is every hover label. */
  const clipped = textOwners
    .filter((el) => {
      const cs = getComputedStyle(el);
      if (cs.overflowX === "visible") return false;
      return el.scrollWidth > el.clientWidth + 1;
    })
    .map((el) => el.textContent.trim().slice(0, 24));

  /* A region that flattened to nothing. `e2e/layout.spec.ts` measures this on
     the shipped panel because at 950px the action list silently went to 2px
     while every assertion about the buttons still passed. */
  const collapsed = all.filter((el) => {
    const s = getComputedStyle(el);
    if (s.display === "none") return false;
    const r = el.getBoundingClientRect();
    return r.height < 1 || r.width < 1;
  }).length;

  const out = {
    screen: innerWidth + "x" + innerHeight,
    railPx,
    railWidthPx: px(railBox.width),
    listPx,
    listShare: railPx ? Math.round((listPx / railPx) * 100) + "%" : "0%",
    rowsVisible,

    surfaces: surfaceEls.length,

    scrollers: scrollEls.length,
    overflowing: overflowing.length,
    unguttered: ungutteredEls.length,

    minFontPx: sizes.length ? Math.min(...sizes.map((s) => s.px)) : null,
    textNodes: sizes.length,
    belowFloor: belowFloor.length,
    belowFloorWorst: belowFloor.slice(0, 6).map((s) => ({ px: s.px, text: s.text })),

    stops: stops.length,
    minHitPx: hits.length ? Math.min(...hits.map((h) => Math.min(h.w, h.h))) : null,
    smallHits: smallHits.length,
    smallHitsWorst: smallHits.slice(0, 6).map((h) => ({ w: h.w, h: h.h })),

    escaped,
    clipped: clipped.length,
    clippedWorst: clipped.slice(0, 6),
    collapsedRegions: collapsed,

    /* A native tooltip opens on hover and on nothing else, so on a controller it
       is information that cannot be reached at all. The shipped client had 45
       and has none left; a mockup that grows one has moved a channel out of
       reach without saying so. Every hover label in this round is
       `aria-label` + `::after`, which the ring reaches too. */
    titleAttrs: roots.reduce((n, r) => n + r.querySelectorAll("[title]").length, 0),

    faults,
  };

  out.PASS =
    out.belowFloor === 0 &&
    out.smallHits === 0 &&
    out.escaped === 0 &&
    out.collapsedRegions === 0 &&
    out.titleAttrs === 0 &&
    out.unguttered === 0 &&
    /* The round's own bar. The shipped rail is 33%; anything that does not clear
       half has not moved the thing the complaint was about. */
    listPx / railPx >= 0.5;

  return out;
}

if (typeof window !== "undefined") window.RAIL_ASSERT = RAIL_ASSERT;
