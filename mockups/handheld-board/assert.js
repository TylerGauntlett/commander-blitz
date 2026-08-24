/*
 * The gates, as numbers.
 *
 * Inlined into every file by `inline.py`, so opening any mockup and typing
 * `BOARD_ASSERT()` in the console works with no server and no paste -- `fetch()`
 * is blocked on file://, so a page cannot load its own checker off disk. `m` runs
 * it and draws the failures on the elements that failed.
 *
 *     copy(JSON.stringify(BOARD_ASSERT(), null, 2))
 *
 * ---------------------------------------------------------------------------
 * FIVE OF THESE ARE INHERITED, AND THEY ARE INHERITED WITH THEIR SCOPE WIDENED,
 * which is the main thing this round does to the two it combines.
 *
 * `../seat/assert.js` measured a seat. `../rail/assert.js` measured a rail. Both
 * drew the rest of the screen as a ghost with no type on it, so "16px floor" and
 * "44px target" were being asked of one component at a time. Here they are asked
 * of THE WHOLE 1280x800 STAGE -- every card, every chip, the strip, the orb, the
 * hand -- which is the question `../handheld/` was originally opened on and the
 * only version of it that means anything: 444 of 635 elements below 12px is a
 * count of the whole screen, not of a panel.
 *
 * THREE ARE NEW.
 *
 * `seatsAgree` -- THE ROUND'S OWN GATE, and the reason it exists. The opponent
 * strip claims "3 lands, 2 untapped, 4 creatures, 2 untapped, 0 other". Those
 * numbers are DERIVED from the permanents in the fixture, and this gate derives
 * them a second, independent way and reads a third off the rendered DOM, then
 * fails if the three disagree. `../seat/` could not run this check at any price:
 * the board under its strip was a dashed sketch, so the strip's numbers were
 * unfalsifiable. A summary that cannot be checked against the thing it summarises
 * is the failure mode this whole family of components has.
 *
 * `fanOverflow` -- the overlap arithmetic, as a number. `BOARD.lay()` computes a
 * step per lane so the cards exactly fill it; if that is ever wrong the board
 * runs off its own edge and `overflow: hidden` on the deck hides it completely.
 * That is the board round's lesson -- WHERE A VISUAL PROPERTY REDUCES TO A
 * NUMBER, ASSERT THE NUMBER -- pointed at the one piece of layout here that is
 * computed rather than declared.
 *
 * `silentClips` -- a box that is cutting its own content with no ellipsis to say
 * so. An ellipsised card name is an honest trade this round has already accepted
 * and is only counted. A `nowrap` strip that is 20px too long for its own box
 * looks IDENTICAL to one that fits, which is how the phase ribbon would fail:
 * you would simply never see the last phase and nothing on screen would say a
 * phase was missing.
 */

function BOARD_ASSERT() {
  const DECK = document.querySelector(".deck");
  if (!DECK) return { PASS: false, why: "no .deck" };

  const FS_FLOOR = 16;    // nothing carrying information may be smaller
  const HIT_FLOOR = 44;   // any focusable or tappable box
  const CARD_FLOOR = 96;  // any card the cursor can land on

  const round = (n) => Math.round(n * 100) / 100;

  const vis = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || +s.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  /* The bezel caption is a note to whoever is reviewing. It is not on the Deck's
     screen and holding it to the Deck's floors is measuring the wrong thing --
     which is why the scope is `.deck` and not `body`. */
  const scale = DECK.getBoundingClientRect().width / (DECK.offsetWidth || 1) || 1;
  const px = (n) => Math.round(n / scale);

  const all = [...DECK.querySelectorAll("*")].filter(vis);
  const faults = [];

  /* --- The type floor ---------------------------------------------------
     Only elements that OWN text: walking every element counts a wrapper at its
     inherited size and reports failures that are not on screen. `aria-hidden` is
     skipped, which is the honest line between a font-size floor and a font-size
     ban -- this gate is about TEXT SOMEBODY READS. A mana symbol is an `<img>`
     and owns no text at all; a card's type glyph is a character and IS
     `aria-hidden`, because the type line says the same thing in words in the
     reader. The rule is that if hiding it from a screen reader would lose
     information, it is text. */
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
     Every stop the cursor can reach and every real button. An overlapped board
     card is worth a note here: its BOX is 120 wide but the card to its right
     covers part of it, so what a thumb can actually land on is `--step`, which
     `BOARD.lay()` never lets fall below about 90px on this board. The gate reads
     the box, which is the generous reading -- see `fanOverflow` for the
     arithmetic that keeps the two close. */
  const stops = [...DECK.querySelectorAll("button, [data-stop]")].filter(vis);
  const hits = stops.map((el) => {
    const r = el.getBoundingClientRect();
    return { el, w: px(r.width), h: px(r.height) };
  });
  const smallHits = hits.filter((h) => h.w < HIT_FLOOR || h.h < HIT_FLOOR);
  for (const h of smallHits.slice(0, 8)) faults.push({ el: h.el, why: h.w + "×" + h.h });

  /* --- The card floor ----------------------------------------------------
     Read off a rendered face rather than off the token, because the token is
     what the design INTENDED and the box is what the player got. The shipped
     board's own figure at 1280x800 is 73.6px, which is where the floor came
     from. The reader's card is not reachable -- it is a picture of what you are
     already pointing at -- so the floor is asked only of faces inside a stop. */
  const faces = [...DECK.querySelectorAll(".face")].filter(vis);
  const reachable = faces
    .filter((f) => f.closest("[data-stop]"))
    .map((f) => ({ el: f, w: px(f.getBoundingClientRect().width) }));
  const smallCards = reachable.filter((f) => f.w < CARD_FLOOR);
  for (const f of smallCards.slice(0, 6)) faults.push({ el: f.el, why: f.w + "px card" });

  /* --- The round's own gate: does the strip agree with the board? --------
     Three derivations of the same five numbers, per seat:
       1. `musterOf()`, which the seat is drawn from
       2. this one, walked over the fixture again with different code
       3. the text actually rendered into the three `.perm` cells
     If any two disagree the seat is describing a board that is not there. */
  const seatCheck = OPPS.map((seat) => {
    let lands = 0, landsUp = 0, creatures = 0, creaturesUp = 0, other = 0;
    for (const c of seat.lands) { const n = c.count || 1; lands += n; if (!c.tapped) landsUp += n; }
    for (const c of seat.creatures) { const n = c.count || 1; creatures += n; if (!c.tapped) creaturesUp += n; }
    for (const c of seat.other) other += c.count || 1;

    const el = DECK.querySelector('[data-seat="' + seat.pid + '"]');
    const cells = el ? [...el.querySelectorAll(".perm")] : [];
    const readCell = (i) => (cells[i] ? cells[i].textContent.trim() : "");

    const want = [landsUp + "/" + lands, creaturesUp + "/" + creatures, String(other)];
    const got = [readCell(0), readCell(1), readCell(2)];
    const m = musterOf(seat);
    const viaMuster = [m.landsUp + "/" + m.lands, m.creaturesUp + "/" + m.creatures, String(m.other)];

    const ok = want.join("|") === got.join("|") && want.join("|") === viaMuster.join("|");
    if (!ok && cells[0]) faults.push({ el: cells[0], why: "seat " + seat.pid + " disagrees" });
    return { pid: seat.pid, want, got, ok };
  });
  const seatsAgree = seatCheck.every((s) => s.ok);

  /* --- The overlap arithmetic --------------------------------------------
     Every fan, which is the three lanes AND THE HAND. Naming the lanes only is
     how the hand came to run 79px past the foot and sit on top of the commit
     panel's first mark, with nothing on screen saying so: the deck is
     `overflow: hidden`, so the page reported no overflow at all and the only
     symptom was a control that had quietly stopped being clickable. */
  const fans = [...DECK.querySelectorAll("[data-fan]")].filter(vis);
  const fanOver = fans.filter((l) => l.scrollWidth > l.clientWidth + 1);
  for (const l of fanOver) faults.push({ el: l, why: "fan " + (l.scrollWidth - l.clientWidth) + "px over" });

  /* --- Scroll containers -------------------------------------------------
     A scroller with no reserved gutter is the reflow-on-hover bug waiting to
     happen, and it is invisible until content crosses the line. Asked of every
     one, which is how `../rail/` found the second instance of it inside the
     enlarged card's rules box. */
  const scrollEls = all.filter((el) => {
    const s = getComputedStyle(el);
    return s.overflowY === "auto" || s.overflowY === "scroll";
  });
  const overflowing = scrollEls.filter((el) => el.scrollHeight > el.clientHeight + 1);
  const unguttered = scrollEls.filter(
    (el) => getComputedStyle(el).scrollbarGutter.indexOf("stable") < 0
  );
  for (const el of unguttered.slice(0, 4)) faults.push({ el, why: "no gutter" });

  /* --- Silent clipping ---------------------------------------------------
     A box cutting its own content with no ellipsis to say so. An ellipsised card
     name is an honest trade and is only counted; a `nowrap` strip 20px too long
     for its own box looks exactly like one that fits. */
  /* ASKED ONLY OF ELEMENTS THAT OWN TEXT, and the first version of this gate is
     why. `scrollWidth` counts absolutely positioned descendants, so every card
     frame reported as clipping -- a `.face` is `overflow: hidden` with a staged
     badge hanging off it at -4px, which is the card working. Fourteen failures
     on a file with nothing wrong. Restricting to text owners asks the question
     the gate is actually for: is a WORD being cut with nothing to say so. */
  const clipCandidates = textOwners.filter((el) => {
    const s = getComputedStyle(el);
    if (s.overflowX === "visible") return false;
    return el.scrollWidth > el.clientWidth + 1;
  });
  const ellipsised = clipCandidates.filter((el) => getComputedStyle(el).textOverflow === "ellipsis");
  const silent = clipCandidates.filter((el) => getComputedStyle(el).textOverflow !== "ellipsis");
  for (const el of silent.slice(0, 4)) faults.push({ el, why: "silent clip" });

  /* --- Escape ------------------------------------------------------------
     Measured against THE DECK rather than against each region, and that is
     deliberate in both directions.

     A staged-attacker badge is `top: -4px; right: -4px` on purpose -- the mark
     hangs off its card, which is what makes it read as attached to one card
     rather than as a thing in the lane -- so measuring it against its lane
     reports four failures that are the design working.

     What is still a failure is leaving the SCREEN, and `overflow: hidden` on the
     deck hides that completely: the page reports `scrollHeight ===
     clientHeight` while content visibly runs under the next region, which is the
     lesson the board round drew. `getBoundingClientRect` still reports the true
     position of a clipped box, so this catches it.

     Rows scrolled below the fold of `.list` are excluded on the scroll axis --
     being outside the visible box there is the entire point of a scroll
     container -- but a row WIDER than its scroller is still content nothing can
     reach, because `.list` scrolls vertically only.

     Hover labels are absolutely positioned outside their control on purpose and
     are invisible at rest, so `vis()` has already excluded them. */
  const deckBox = DECK.getBoundingClientRect();
  let escaped = 0;
  for (const el of all) {
    const scroller = el.parentElement && el.parentElement.closest(".list, .reader__rules");
    const b = el.getBoundingClientRect();
    const box = scroller ? scroller.getBoundingClientRect() : deckBox;
    const out =
      b.left < box.left - 1 || b.right > box.right + 1 ||
      (!scroller && (b.top < box.top - 1 || b.bottom > box.bottom + 1));
    if (out) {
      escaped += 1;
      if (escaped <= 4) faults.push({ el, why: "escapes" });
    }
  }

  /* A region that flattened to nothing. `e2e/layout.spec.ts` measures this on
     the shipped panel because at 950px the action list silently went to 2px
     while every assertion about the buttons still passed. */
  const collapsed = all.filter((el) => {
    const r = el.getBoundingClientRect();
    return r.height < 1 || r.width < 1;
  }).length;

  /* --- The rail's share, kept from `../rail/` ---------------------------- */
  const rail = DECK.querySelector(".rail");
  const list = DECK.querySelector(".list");
  const reader = DECK.querySelector(".rail .reader");
  const railPx = rail ? px(rail.getBoundingClientRect().height) : 0;
  const listPx = list ? px(list.getBoundingClientRect().height) : 0;
  const readerPx = reader ? px(reader.getBoundingClientRect().height) : 0;
  /* Rows, not pixels, is what a player experiences. 44 + the 6px gutter. */
  const rowsVisible = Math.floor((listPx + 6) / (HIT_FLOOR + 6));

  const out = {
    screen: innerWidth + "x" + innerHeight,
    scalePct: Math.round(scale * 100),

    railPx,
    railWidthPx: rail ? px(rail.getBoundingClientRect().width) : 0,
    readerPx,
    listPx,
    listShare: railPx ? Math.round((listPx / railPx) * 100) + "%" : "0%",
    rowsVisible,
    /* The shipped board's own figure, for the comparison this round is for.
       `handheld.css:1540-1554`: a 514px rail whose action list holds 172. */
    shippedListPx: 172,

    seatsAgree,
    seats: seatCheck.map((s) => ({ pid: s.pid, want: s.want.join(" "), got: s.got.join(" "), ok: s.ok })),

    cards: faces.length,
    reachableCards: reachable.length,
    minCardPx: reachable.length ? Math.min(...reachable.map((f) => f.w)) : null,
    smallCards: smallCards.length,

    fans: fans.length,
    fanOverflow: fanOver.length,

    scrollers: scrollEls.length,
    overflowing: overflowing.length,
    unguttered: unguttered.length,

    minFontPx: sizes.length ? Math.min(...sizes.map((s) => s.px)) : null,
    textNodes: sizes.length,
    belowFloor: belowFloor.length,
    belowFloorWorst: belowFloor.slice(0, 6).map((s) => ({ px: s.px, text: s.text })),

    stops: stops.length,
    minHitPx: hits.length ? Math.min(...hits.map((h) => Math.min(h.w, h.h))) : null,
    smallHits: smallHits.length,
    smallHitsWorst: smallHits.slice(0, 6).map((h) => ({ w: h.w, h: h.h })),

    ellipsised: ellipsised.length,
    ellipsisedWorst: ellipsised.slice(0, 6).map((el) => el.textContent.trim().slice(0, 24)),
    silentClips: silent.length,

    escaped,
    collapsedRegions: collapsed,

    /* A native tooltip opens on hover and on nothing else, so on a controller it
       is information that cannot be reached at all. The shipped client had 45 and
       has none left; a mockup that grows one has moved a channel out of reach
       without saying so. Every hover label in this round is `aria-label` +
       `::after`, which the ring reaches too. */
    titleAttrs: DECK.querySelectorAll("[title]").length,

    faults,
  };

  out.PASS =
    out.belowFloor === 0 &&
    out.smallHits === 0 &&
    out.smallCards === 0 &&
    out.escaped === 0 &&
    out.collapsedRegions === 0 &&
    out.titleAttrs === 0 &&
    out.unguttered === 0 &&
    out.fanOverflow === 0 &&
    out.silentClips === 0 &&
    out.seatsAgree &&
    /*
     * THE ROUND'S BAR, AND IT IS NOT `../rail/`'s.
     *
     * That round gated on `listShare >= 50%` because its rail had one tenant and
     * a share was therefore the same statement as an absolute. This rail has two
     * ON PURPOSE -- the card reader came back off a hold when the column grew to
     * 748px -- so a share gate here would fail a design for spending room on the
     * thing the room was found for. `listShare` is still reported, for
     * continuity, and it is no longer what passes a file.
     *
     * What passes a file is what a player experiences: SEVEN ROWS WITHOUT
     * SCROLLING, and at least double the 172px `handheld.css:1540-1554` measures
     * the shipped action list at. A direction that does not clear both has not
     * moved the thing the complaint was about however good the fraction looks.
     */
    out.rowsVisible >= 7 &&
    listPx >= 2 * out.shippedListPx;

  return out;
}

if (typeof window !== "undefined") window.BOARD_ASSERT = BOARD_ASSERT;
