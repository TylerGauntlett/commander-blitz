/*
 * The gates, as numbers.
 *
 * Inlined into every file by `inline.py`, so opening any mockup and typing
 * `ORB_ASSERT()` in the console works with no server and no paste -- `fetch()`
 * is blocked on file://, so a page cannot load its own checker off disk. `m`
 * runs it and draws the failures on the elements that failed.
 *
 *     copy(JSON.stringify(ORB_ASSERT(), null, 2))
 *
 * This is `../seat/assert.js` retargeted from `.mat` to `.orb`, and it keeps
 * every floor that round set: 16px of type, zero native tooltips, nothing
 * escaping its box, nothing collapsed, no broken images, and the uniformity
 * counts -- `boxKinds`, `padKinds`, `gapKinds` -- that the seat round was
 * opened on. A component inside that round's screen does not get a softer
 * floor because it belongs to the viewer.
 *
 * ---------------------------------------------------------------------------
 * TWO THINGS DIFFER, AND BOTH ARE THE POINT OF THIS ROUND.
 *
 * 1. THE 44px TARGET FLOOR IS A LIVE GATE HERE AND WAS NOT ON THE SEAT.
 *
 *    `06-muster.html` demoted an opponent's five zone marks to non-controls,
 *    because 96px will not hold a 44px row and the battlefield row as well, and
 *    argued the case: two of the five were never buttons anyway. On the
 *    viewer's own orb the arithmetic is different -- 518px of column holds five
 *    44px targets with 298 left over -- and four of the five have something
 *    real behind them. So they are buttons again and this gate has teeth.
 *
 *    `smallHits` therefore counts. A direction that ships a 30px graveyard
 *    button fails, and no amount of "it is only a mockup" changes that a thumb
 *    on a 7-inch touchscreen cannot hit it.
 *
 * 2. BOTH DIMENSIONS OF THE BOX ARE CHECKED, NOT JUST THE HEIGHT.
 *
 *    The seat round capped a row's height because that row's overflow came off
 *    the viewer's board. The orb is a COLUMN inside that board, so it can fail
 *    in either direction: too tall and it runs under the hand, too wide and it
 *    eats the lane the cards are in. `handheld.css:1218` records what the first
 *    failure actually looked like in the shipped client -- `.mat__side` grew,
 *    `overflow-y: auto` turned it into a scrollbar rather than into a visible
 *    fault, and the graveyard pile ended up behind the hand where it was
 *    neither visible nor clickable and nothing said it was there.
 */

function ORB_ASSERT() {
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

  /* SCOPE: THE ORB, NOT THE TABLE AROUND IT.
     The bezel tag is a note to whoever is reviewing and is not on the Deck's
     screen. The ghosted lanes are not the design either: they are the room the
     design is spending, drawn so the spend is visible. And the three opponents
     are `06-muster.html`'s seats rather than this round's work -- measuring them
     here would score every direction on a file none of them wrote. Everything
     inside `.orb` is the design and nothing else is. */
  const orbs = [...DECK.querySelectorAll(".orb")].filter(vis);
  const scale = DECK.getBoundingClientRect().width / (DECK.offsetWidth || 1) || 1;
  const px = (n) => Math.round(n / scale);

  /* The orb ITSELF is in this set, not just its descendants. Its own padding is
     one of the paddings a reader sees at the panel's edge -- leaving it out
     reported `padKinds: 1` for a panel with two, which flatters every direction
     equally and is therefore worse than not measuring it. */
  const all = orbs.flatMap((m) => [m, ...m.querySelectorAll("*")]).filter(vis);
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
     Live here in a way it was not on the seat; see the header. A real button on
     a 7-inch touchscreen is 44px or it is not a button. */
  const stops = orbs.flatMap((m) => [...m.querySelectorAll("button, [data-stop]")]).filter(vis);
  const hits = stops.map((el) => {
    const r = el.getBoundingClientRect();
    return { el, w: px(r.width), h: px(r.height) };
  });
  const smallHits = hits.filter((h) => h.w < HIT_FLOOR || h.h < HIT_FLOOR);
  for (const h of smallHits.slice(0, 8)) faults.push({ el: h.el, why: h.w + "×" + h.h });

  /* --- Uniformity, which is the seat round's own gate and is inherited ----
     `boxKinds` counts the distinct GEOMETRIES among the orb's cells -- height,
     padding and radius, rounded. "All items should fit cleanly and uniformly"
     reduces to a number: a panel whose marks are 28px tall with 0 6px of
     padding, whose damage chips are 30px tall with 2px 5px, and whose threat
     line is a 22px text run with 3px 6px is three unrelated objects standing in
     a column, and it counts three.

     A number is not a verdict -- one is not automatically better than two, and
     a direction may spend a second geometry on purpose to separate two families
     of fact. What the gate forbids is spending one by accident. */
  const cells = orbs.flatMap((m) => [...m.querySelectorAll("[data-cell]")]).filter(vis);
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

  /* Every padded box in the orb, containers included -- the ragged-edge metric.
     The shipped viewer's column measures SEVEN: the mat's `5px 7px`, the body
     grid's `2px`, the cmdslot's `3px`, the spine's `3px 6px`, the panel's
     `1px 4px`, the cmd-pip's `1px 4px 2px` and the pile leaf's `0 6px`. None of
     the seven is visible in the CSS, where each is locally reasonable, and all
     of it is visible on screen. */
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

  /* And the gutters. Three gaps in one column reads as three components. */
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
     measured against the orb's own box rather than asked of the scroller. */
  let escaped = 0;
  for (const m of orbs) {
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

  /* Text that is being ellipsised. Not a failure on its own -- a commander's
     name is allowed to clip and the loss line is allowed to clip -- but a
     direction that clips a COUNT has lost the datum, and this is how you see
     which.

     Asked only of boxes that actually cut. A box with `overflow: visible` shows
     all of its text however wide it is, and `scrollWidth` on one of those also
     counts absolutely-positioned descendants -- which in this round is the
     hover label every mark carries, so the first version of this check reported
     four "clipped" zone counts on a panel with nothing wrong. */
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

  /* --- The box, both ways ------------------------------------------------
     The declared budget is `--orb-w` x `--orb-h` on `.deck`, which each file
     may re-declare and then pays for in the ghosted lanes. The gate holds a
     direction to whatever it declared and to nothing else. */
  const cs = getComputedStyle(DECK);
  const budgetW = Math.round(parseFloat(cs.getPropertyValue("--orb-w")) || 0);
  const budgetH = Math.round(parseFloat(cs.getPropertyValue("--orb-h")) || 0);
  const box = orbs.length ? orbs[0].getBoundingClientRect() : null;
  const orbW = box ? px(box.width) : 0;
  const orbH = box ? px(box.height) : 0;

  const out = {
    screen: innerWidth + "x" + innerHeight,
    density: DECK.dataset.density,
    orb: orbW + "×" + orbH,
    budget: budgetW + "×" + budgetH,

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

    /* The cards the ghosted lanes have room for, which is what a direction's
       footprint claim actually cashes out to. Ten is the 154px column's. */
    laneCards: typeof laneCards === "function" ? laneCards() : null,

    /* A native tooltip opens on hover and on nothing else, so on a controller it
       is information that cannot be reached at all. The shipped client had 45
       and has none left; a mockup that grows one has moved a channel out of
       reach without saying so. */
    titleAttrs: orbs.reduce((n, m) => n + m.querySelectorAll("[title]").length, 0),

    brokenImages: orbs
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
    orbW <= budgetW + 1 &&
    orbH <= budgetH + 1;

  return out;
}

if (typeof window !== "undefined") window.ORB_ASSERT = ORB_ASSERT;
