/*
 * The gates, as numbers.
 *
 * Inlined into every file by `inline.py`, so opening any mockup and typing
 * `SEAT_ASSERT()` in the console works with no server and no paste -- `fetch()`
 * is blocked on file://, so a page cannot load its own checker off disk. `m`
 * runs it and draws the failures on the elements that failed.
 *
 *     copy(JSON.stringify(SEAT_ASSERT(), null, 2))
 *
 * Four of these are `../handheld/assert.js`'s, unchanged, because this round is
 * a component inside that round's screen and a floor that only applies to the
 * rest of the screen is not a floor: 16px of type, 44px of target, zero native
 * tooltips, nothing escaping its box.
 *
 * TWO ARE NEW, AND THEY ARE THE ONES THIS ROUND EXISTS FOR.
 *
 * `boxKinds` counts the distinct GEOMETRIES among the seat's cells -- height,
 * padding and radius, rounded. "All items should fit cleanly and uniformly" is
 * the complaint this round was opened on, and it reduces to a number: a strip
 * whose marks are 28px tall with 0 6px of padding, whose damage chips are 30px
 * tall with 2px 5px, and whose threat line is a 22px text run with 3px 6px is
 * three unrelated objects standing in a row, and it counts three.
 *
 * `padKinds` does the same for every padded box in the seat, including the
 * containers. The shipped strip measures FIVE at one opponent: the mat's
 * `5px 7px`, the body grid's `2px`, the spine's `3px 6px`, the plate's own
 * padding and the pile chip's `0 6px`. Nothing about that is visible in the
 * CSS, where each of the five is locally reasonable, and all of it is visible
 * on screen as the ragged left edge the round was opened about.
 *
 * A number is not a verdict -- one is not automatically better than two, and a
 * direction may spend a second geometry on purpose to separate two families of
 * fact. What the gate forbids is spending one by accident.
 */

function SEAT_ASSERT() {
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

  /* SCOPE: THE SEATS, NOT THE REVIEW CHROME AROUND THEM.
     The bezel tag is a note to whoever is reviewing -- it is not on the Deck's
     screen, and holding it to the Deck's floor measures the wrong thing. The
     ghosted board is not the design either: it is the room the design is
     spending, drawn so the spend is visible. Everything inside `.mat` is the
     design and nothing else is. */
  const mats = [...DECK.querySelectorAll(".mat")].filter(vis);
  const scale = DECK.getBoundingClientRect().width / (DECK.offsetWidth || 1) || 1;
  const px = (n) => Math.round(n / scale);

  const all = mats.flatMap((m) => [...m.querySelectorAll("*")]).filter(vis);
  const faults = [];

  /* --- The type floor ---------------------------------------------------
     Only elements that OWN text: walking every element counts a wrapper at its
     inherited size and reports failures that are not on screen. `aria-hidden`
     is skipped, which is the honest line between a font-size floor and a
     font-size ban -- this gate is about TEXT SOMEBODY READS. Every icon in this
     round is an `aria-hidden` SVG and is named in real type by its cell's
     `aria-label`, so none of them is in this set. If hiding it from a screen
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
       here reported a 16px floor as 17.9 and would have passed type that fails
       on the device. */
    px: round(parseFloat(getComputedStyle(el).fontSize)),
    text: el.textContent.trim().slice(0, 32),
  }));
  const belowFloor = sizes.filter((s) => s.px < FS_FLOOR).sort((a, b) => a.px - b.px);
  for (const s of belowFloor.slice(0, 8)) faults.push({ el: s.el, why: s.px + "px" });

  /* --- The target floor -------------------------------------------------
     Four of the five zone marks are the only route into `ZonePeek`. A
     decorative pile makes the graveyard unreachable, so they are real buttons,
     and a real button on a 7-inch touchscreen is 44px or it is not a button. */
  const stops = mats.flatMap((m) => [...m.querySelectorAll("button, [data-stop]")]).filter(vis);
  const hits = stops.map((el) => {
    const r = el.getBoundingClientRect();
    return { el, w: px(r.width), h: px(r.height) };
  });
  const smallHits = hits.filter((h) => h.w < HIT_FLOOR || h.h < HIT_FLOOR);
  for (const h of smallHits.slice(0, 8)) faults.push({ el: h.el, why: h.w + "×" + h.h });

  /* --- Uniformity, which is the round's own gate ------------------------- */
  const cells = mats.flatMap((m) => [...m.querySelectorAll("[data-cell]")]).filter(vis);
  const cellSig = (el) => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return [
      px(r.height),
      s.paddingTop + " " + s.paddingRight + " " + s.paddingBottom + " " + s.paddingLeft,
      s.borderTopLeftRadius,
    ].join(" | ");
  };
  const cellKinds = [...new Set(cells.map(cellSig))];

  /* Every padded box in the seat, containers included -- the ragged-edge
     metric. A container that pads by 2 inside a plate that pads by 7 inside a
     mat that pads by 5 is where an inconsistent-looking strip actually comes
     from, and none of the three is visible on its own. */
  const padded = all.filter((el) => {
    const s = getComputedStyle(el);
    return (
      parseFloat(s.paddingTop) + parseFloat(s.paddingRight) +
      parseFloat(s.paddingBottom) + parseFloat(s.paddingLeft) > 0
    );
  });
  /* CSS pixels, not scaled ones. A padding is authored in the stylesheet and
     the bezel's `transform` does not change it -- dividing by the scale turned
     a shared `6px` into a `7` and reported one gutter as two. */
  const padSig = (el) => {
    const s = getComputedStyle(el);
    return [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft]
      .map((v) => Math.round(parseFloat(v)))
      .join(" ");
  };
  const padKinds = [...new Set(padded.map(padSig))].sort();

  /* And the gutters. Three gaps in one strip reads as three components. */
  const gapKinds = [
    ...new Set(
      all
        .map((el) => getComputedStyle(el))
        .filter((s) => s.display.includes("flex") || s.display.includes("grid"))
        .map((s) => Math.round(parseFloat(s.rowGap) || 0) + " " + Math.round(parseFloat(s.columnGap) || 0))
        .filter((g) => g !== "0 0")
    ),
  ].sort();

  /* --- Escape and clip ---------------------------------------------------
     `overflow: hidden` hides layout failure completely -- the page reports
     `scrollHeight === clientHeight` while content visibly runs under the next
     region -- which is the lesson the board round drew and the reason this is
     measured against the mat's own box rather than asked of the scroller. */
  let escaped = 0;
  for (const m of mats) {
    const box = m.getBoundingClientRect();
    for (const el of [...m.querySelectorAll("*")].filter(vis)) {
      const r = el.getBoundingClientRect();
      if (r.left < box.left - 1 || r.right > box.right + 1 ||
          r.top < box.top - 1 || r.bottom > box.bottom + 1) {
        escaped += 1;
        if (escaped <= 4) faults.push({ el, why: "escapes" });
      }
    }
  }

  /* Text that is being ellipsised. Not a failure on its own -- `threatParts`
     emits in order of what matters, so what falls off the end is always the
     least decision-changing clause -- but a direction that clips a COUNT has
     lost the datum, and this is how you see which. */
  /* Asked only of boxes that actually cut. A box with `overflow: visible` shows
     all of its text however wide it is, and `scrollWidth` on one of those also
     counts absolutely-positioned descendants -- which in this round is the
     hover label every mark carries, so the first version of this check reported
     four "clipped" zone counts on a seat 1017px wide with nothing wrong. */
  const clipped = textOwners
    .filter((el) => {
      const cs = getComputedStyle(el);
      if (cs.overflowX === "visible") return false;
      return el.scrollWidth > el.clientWidth + 1;
    })
    .map((el) => el.textContent.trim().slice(0, 24));

  /* A region that flattened to nothing. `overflow: hidden` hides this too. */
  const collapsed = all.filter((el) => {
    const s = getComputedStyle(el);
    if (s.display === "none") return false;
    const r = el.getBoundingClientRect();
    return r.height < 1 || r.width < 1;
  }).length;

  const matBoxes = mats.map((m) => {
    const r = m.getBoundingClientRect();
    return px(r.width) + "×" + px(r.height);
  });

  /* The row must not be taller than the budget it declared. Every pixel over is
     a pixel off the viewer's own board -- `board.css:55-66` calls that
     load-bearing, and the handheld layout's single largest defect was this row
     going uncapped. */
  const opps = DECK.querySelector(".opps");
  const budget = mats.length ? Math.round(parseFloat(getComputedStyle(mats[0]).height)) : 0;
  const rowH = opps ? px(opps.getBoundingClientRect().height) : 0;

  const out = {
    screen: innerWidth + "x" + innerHeight,
    density: DECK.dataset.density,
    seats: matBoxes,
    rowHeightPx: rowH,
    budgetPx: budget,

    minFontPx: sizes.length ? Math.min(...sizes.map((s) => s.px)) : null,
    textNodes: sizes.length,
    belowFloor: belowFloor.length,
    belowFloorWorst: belowFloor.slice(0, 6).map((s) => ({ px: s.px, text: s.text })),

    stops: stops.length,
    minHitPx: hits.length ? Math.min(...hits.map((h) => Math.min(h.w, h.h))) : null,
    smallHits: smallHits.length,
    smallHitsWorst: smallHits.slice(0, 6).map((h) => ({ w: h.w, h: h.h })),

    cells: cells.length,
    boxKinds: cellKinds.length,
    boxKindList: cellKinds,
    padKinds: padKinds.length,
    padKindList: padKinds,
    gapKinds: gapKinds.length,
    gapKindList: gapKinds,

    escaped,
    clipped: clipped.length,
    clippedWorst: clipped.slice(0, 6),
    collapsedRegions: collapsed,

    /* A native tooltip opens on hover and on nothing else, so on a controller it
       is information that cannot be reached at all. The shipped client had 45
       and has none left; a mockup that grows one has moved a channel out of
       reach without saying so. */
    titleAttrs: mats.reduce((n, m) => n + m.querySelectorAll("[title]").length, 0),

    brokenImages: mats
      .flatMap((m) => [...m.querySelectorAll("img")])
      .filter((i) => i.complete && i.naturalWidth === 0).length,

    faults,
  };

  out.PASS =
    out.belowFloor === 0 &&
    out.smallHits === 0 &&
    out.escaped === 0 &&
    out.collapsedRegions === 0 &&
    out.titleAttrs === 0 &&
    out.brokenImages === 0 &&
    out.rowHeightPx <= out.budgetPx + 1;

  return out;
}

if (typeof window !== "undefined") window.SEAT_ASSERT = SEAT_ASSERT;
