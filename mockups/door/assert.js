/*
 * The gates, as numbers.
 *
 * Inlined into every file by `inline.py`, so opening any mockup and typing
 * `DOOR_ASSERT()` in the console works with no server and no paste -- `fetch()`
 * is blocked on file://, so a page cannot load its own checker off disk.
 *
 *     copy(JSON.stringify(DOOR_ASSERT(), null, 2))
 *
 * ---------------------------------------------------------------------------
 * IT DRIVES THE SCREEN RATHER THAN LOOKING AT IT.
 *
 * Every earlier round in this folder measured one pose. This one cannot: the
 * whole subject is what happens when the selection moves, and the two failures
 * that matter both live at the ENDS of the row, which is a state you never see
 * unless you go there. So the gate walks all three selections through
 * `DOOR.select(i, true)`, measures each, and puts the row back where it found
 * it. A screenshot of the default state is a screenshot of the one state where
 * nothing is stacked.
 *
 * ---------------------------------------------------------------------------
 * FOUR ARE INHERITED. The 16px type floor, the 44px target floor, the 96px card
 * floor and the escape check come from `../handheld/assert.js` and
 * `../handheld-board/assert.js` unchanged, and are asked of the whole 1280x800
 * stage rather than of a component. `../handheld/` measured 444 of 635 elements
 * below 12px on the shipped board, the smallest at 2.11px, which is where the
 * type floor came from and why it is a number and not a preference.
 *
 * THREE ARE THIS ROUND'S OWN.
 *
 * `labelClear` -- THE THESIS GATE. The brief asks the two unselected cards to
 * overlap, and overlap's failure mode is a card covering the one thing that
 * says what the card under it is. A menu item nobody can name is not a menu
 * item, and this is invisible to every other check here: the covered card is
 * the right size, at the right place, in the right font, fully inside the
 * stage, and unreadable. It is also what found the label-side rule -- see
 * `poseOf` in `_door.js`.
 *
 * `inkClear` -- the same question asked of everything else on the card, and it
 * exists because `labelClear` passed 04 while the plate's live state line was
 * being sliced in half beside the name it had just protected. A sentence
 * running under a covering card reads as truncated rather than as hidden, which
 * is worse: a truncated line looks like a bug in the copy. Its answer is not to
 * un-stack but to stop printing what cannot be read -- see `.ink`.
 *
 * `rowFits` -- the overlap arithmetic, as a number. The row is laid out by
 * `poseOf` rather than declared, and its widest state is not the one it opens
 * on. `.deck` is `overflow: hidden`, so a row that runs off the stage reports
 * no page overflow at all and the only symptom is a card that is quietly not
 * there. That is the board round's own lesson -- WHERE A VISUAL PROPERTY
 * REDUCES TO A NUMBER, ASSERT THE NUMBER -- pointed at the one piece of layout
 * here that is computed.
 *
 * `slideReads` -- THE ANIMATION HAS A FLOOR AS WELL AS A CEILING, and it has
 * one because the first version of this gate did not.
 *
 * That version asked a single question: is a hop permanently within 2px of its
 * target inside 180ms, the moment a held direction fires again. The spring that
 * passed it crossed the entire row in FOUR FRAMES and then rang for fourteen
 * more, 21px each way. `0.85 0.55 0.27 0.07 -0.04 -0.08 ...`, sampled per
 * frame: a cut followed by a wobble, which is what the screen was reported as
 * -- jerky -- while every number in this file said the file was fine.
 *
 * A one-sided ceiling on a duration is satisfied most cheaply by making the
 * animation violent, so it rewards the failure it exists to prevent. Three
 * numbers now, from `DOOR.springProfile()`:
 *
 *   traverseMs   >= 100   fewer than six frames is a cut, not a move
 *   settleMs     <= 320   past a third of a second a menu is making you wait
 *   overshootPx  <= 8     a big overshoot after a fast traverse IS the jitter
 *
 * All three are simulated from the same closed-form step the row runs rather
 * than timed off the DOM, so they are properties of the spring and not of the
 * reviewer's monitor.
 */

function DOOR_ASSERT() {
  const DECK = document.querySelector(".deck");
  if (!DECK) return { PASS: false, why: "no .deck" };
  if (typeof DOOR === "undefined") return { PASS: false, why: "no DOOR" };

  const FS_FLOOR = 16;
  const HIT_FLOOR = 44;
  const CARD_FLOOR = 96;

  const round = (n) => Math.round(n * 100) / 100;

  /*
   * On screen, not merely laid out -- AND IT HAS TO LOOK UP THE TREE.
   *
   * `visibility` is inherited so the computed value on the element is already
   * the whole answer; `opacity` is NOT. A `<span>` inside a faded parent
   * computes `opacity: 1` and reports a full-size box, which is how `inkClear`
   * came back at 31% on 04 for a state line that had already been faded out
   * with the card -- the wrapper was invisible and the words inside it were
   * not, as far as the gate could see.
   *
   * The same walk is in the shipped `e2e/handheldAssert.ts:183-204`, for the
   * clipping version of the same trap, and its comment is the reason to bother:
   * a gate that reports something that is not wrong sends you fixing it, and
   * the fix is always worse than the thing.
   */
  const vis = (el) => {
    for (let a = el; a; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.display === "none" || s.visibility === "hidden") return false;
      if (+s.opacity === 0) return false;
      if (a.classList && a.classList.contains("deck")) break;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  /* The bezel caption is a note to whoever is reviewing. It is not on the
     Deck's screen and holding it to the Deck's floors is measuring the wrong
     thing -- which is why the scope is `.deck` and not `body`. */
  const scale = DECK.getBoundingClientRect().width / (DECK.offsetWidth || 1) || 1;
  const px = (n) => Math.round(n / scale);

  const faults = [];

  /* =======================================================================
     Walk all three selections
     =======================================================================

     `select(i, true)` snaps the spring and repaints in the same tick, so this
     measures three settled layouts rather than three moments of one animation.
     The row is restored at the end, because a gate that leaves the screen
     somewhere else has changed the thing the next reviewer looks at.
     ==================================================================== */

  const wasOn = DOOR.target;
  const deckBox = DECK.getBoundingClientRect();

  const states = [];
  for (let sel = 0; sel < CARDS.length; sel += 1) {
    DOOR.select(sel, true);

    const slots = [...DECK.querySelectorAll(".slot")].filter(vis);

    /* --- The thesis gate: is every label readable in this state? --------
       Each label against every card drawn ON TOP of it, by z-index. The
       rectangles are axis-aligned bounding boxes of rotated elements, so this
       OVER-reports slightly -- a tilted card's box is wider than the card. That
       is the right direction for a gate to be wrong in, and the 2% floor below
       is what keeps a tilt from failing a file on its own bounding box. */
    let worstPct = 0;
    let worstOn = null;
    for (const slot of slots) {
      const label = slot.querySelector(".mcard__label");
      if (!label || !vis(label)) continue;
      const lb = label.getBoundingClientRect();
      const area = lb.width * lb.height;
      if (area <= 0) continue;
      const z = +getComputedStyle(slot).zIndex || 0;
      let covered = 0;
      for (const other of slots) {
        if (other === slot) continue;
        if ((+getComputedStyle(other).zIndex || 0) <= z) continue;
        const ob = other.querySelector(".mcard").getBoundingClientRect();
        const w = Math.max(0, Math.min(lb.right, ob.right) - Math.max(lb.left, ob.left));
        const h = Math.max(0, Math.min(lb.bottom, ob.bottom) - Math.max(lb.top, ob.top));
        covered += w * h;
      }
      const pct = Math.round((covered / area) * 100);
      if (pct > worstPct) {
        worstPct = pct;
        worstOn = slot.querySelector(".mcard").dataset.card;
      }
    }

    /* --- `inkClear`: is anything else on a card being CUT rather than hidden?
       `labelClear` guards the name and only the name, which is enough for a
       card that carries nothing else. It is not enough for a direction whose
       idea lives in the body of the card: 04 passed `labelClear` with its live
       state line sliced down the middle by the plate on top of it, and a
       sentence that runs under a covering card reads as truncated -- like a bug
       in the copy -- rather than as hidden.

       So every visible piece of text inside a card is measured the same way the
       label is. The design answer is not to un-stack, it is to STOP PRINTING
       what cannot be read: `.ink` in `_door.css` fades it out with the card, and
       an element at zero opacity is not visible, so it leaves this count. */
    let inkWorst = 0;
    let inkWorstOn = null;
    for (const slot of slots) {
      const z = +getComputedStyle(slot).zIndex || 0;
      const covering = slots.filter(
        (o) => o !== slot && (+getComputedStyle(o).zIndex || 0) > z
      );
      if (!covering.length) continue;
      const inks = [...slot.querySelectorAll(".mcard *")].filter(
        (el) =>
          !el.closest('[aria-hidden="true"]') &&
          vis(el) &&
          [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
      );
      for (const el of inks) {
        const eb = el.getBoundingClientRect();
        const area = eb.width * eb.height;
        if (area <= 0) continue;
        let covered = 0;
        for (const o of covering) {
          const ob = o.querySelector(".mcard").getBoundingClientRect();
          const w = Math.max(0, Math.min(eb.right, ob.right) - Math.max(eb.left, ob.left));
          const h = Math.max(0, Math.min(eb.bottom, ob.bottom) - Math.max(eb.top, ob.top));
          covered += w * h;
        }
        const pct = Math.round((covered / area) * 100);
        if (pct > inkWorst) {
          inkWorst = pct;
          inkWorstOn = slot.querySelector(".mcard").dataset.card;
        }
      }
    }

    /* --- `cardSpill`: text falling off its own card ----------------------
       The escape check measures against the DECK and skips the row, because a
       tilted card's bounding box grazes the stage edge and failing a file on
       that is the check crying wolf. That left a hole one level down, and 04
       fell straight into it: a specificity collision let the shared centring
       rule survive an override, the selected plate's title moved half its own
       width off the left edge, and `overflow: hidden` on the card ate it. The
       screen read "ECKS". Nothing else here could see it -- `silentClips` asks
       whether an element clips ITSELF, and this element was being clipped by
       its parent.

       Two pixels of tolerance, for the sub-pixel rounding a scaled stage and a
       rotated box both introduce. */
    let spill = 0;
    for (const slot of slots) {
      const card = slot.querySelector(".mcard");
      const cb = card.getBoundingClientRect();
      const inside = [...card.querySelectorAll("*")].filter(
        (el) => vis(el) && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
      );
      for (const el of inside) {
        const eb = el.getBoundingClientRect();
        if (eb.left < cb.left - 2 || eb.right > cb.right + 2 ||
            eb.top < cb.top - 2 || eb.bottom > cb.bottom + 2) {
          spill += 1;
          if (spill <= 4) faults.push({ el, why: "spills its card on " + CARDS[sel].id });
        }
      }
    }

    /* --- The sliver: how much of a stacked card is left showing? --------
       THE STACK DEPTH IS SET BY THE LONGEST LABEL, and this is the measurement
       that says so. Of two cards on the same side of the selection the nearer
       is drawn on top, so what is left of the further one is the strip between
       their right edges -- `STEP - BUNCH` in `poseOf`'s terms. A label wider
       than that strip cannot be read however it is aligned, which is the same
       fact `labelClear` reports as a percentage and this reports as the two
       numbers a designer can act on. */
    let sliver = Infinity;
    let widestLabel = 0;
    const byX = slots
      .map((el) => ({ el, b: el.querySelector(".mcard").getBoundingClientRect() }))
      .sort((a, b) => a.b.left - b.b.left);
    for (let k = 0; k < byX.length - 1; k += 1) {
      const gap = byX[k + 1].b.left - byX[k].b.left;
      if (gap < byX[k].b.width) sliver = Math.min(sliver, px(gap));
    }
    for (const slot of slots) {
      const label = slot.querySelector(".mcard__label");
      if (label && vis(label)) widestLabel = Math.max(widestLabel, px(label.getBoundingClientRect().width));
    }

    /* --- The arithmetic gate: does the row stay on the stage? -----------
       Measured off the CARDS and not off `.row`, which is a full-width box that
       always fits by construction and would report every file as passing. */
    let left = Infinity;
    let right = -Infinity;
    for (const slot of slots) {
      const b = slot.querySelector(".mcard").getBoundingClientRect();
      left = Math.min(left, b.left);
      right = Math.max(right, b.right);
    }

    states.push({
      sel,
      on: CARDS[sel].id,
      labelWorstPct: worstPct,
      labelWorstOn: worstOn,
      cardSpill: spill,
      inkWorstPct: inkWorst,
      inkWorstOn,
      sliverPx: Number.isFinite(sliver) ? sliver : null,
      widestLabelPx: widestLabel,
      rowLeftPx: px(left - deckBox.left),
      rowRightPx: px(deckBox.right - right),
      rowWidthPx: px(right - left),
    });
  }

  DOOR.select(wasOn, true);

  /* 2% rather than 0: see the bounding-box note above. Anything a reader would
     actually call covered is tens of percent, and the two states that failed
     while this was being built came in at 41% and 46%. */
  const labelClear = states.every((s) => s.labelWorstPct <= 2);
  /* 25 rather than 2. A name has to be wholly readable or it is not a name; a
     line of body copy has a paragraph's tolerance and its own left edge to
     start from, and holding it to the label's bar would fail a card whose
     descender happens to graze the neighbour's rounded corner. What this is
     for is a line being CUT, and a cut line is half gone. */
  const inkClear = states.every((s) => s.inkWorstPct <= 25);
  const rowFits = states.every((s) => s.rowLeftPx >= 0 && s.rowRightPx >= 0);
  for (const s of states) {
    if (s.inkWorstPct > 25) {
      faults.push({
        el: document.getElementById("slot-" + s.inkWorstOn),
        why: "body " + s.inkWorstPct + "% cut on " + s.on,
      });
    }
    if (s.labelWorstPct > 2) {
      faults.push({
        el: document.getElementById("slot-" + s.labelWorstOn),
        why: "label " + s.labelWorstPct + "% covered on " + s.on,
      });
    }
  }

  /* =======================================================================
     The standing floors, in the state the reviewer left the screen in
     ==================================================================== */

  const all = [...DECK.querySelectorAll("*")].filter(vis);

  /* --- The type floor ---------------------------------------------------
     Only elements that OWN text: walking every element counts a wrapper at its
     inherited size and reports failures that are not on screen. `aria-hidden`
     is skipped, which is the honest line between a font-size floor and a
     font-size ban -- the gate is about TEXT SOMEBODY READS. The mark repeated
     across a card back is a pattern rather than a label and is hidden for that
     reason, which `CardBack.tsx:35-46` already argues in the shipped app. */
  const textOwners = all.filter(
    (el) =>
      !el.closest('[aria-hidden="true"]') &&
      [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
  );
  const sizes = textOwners.map((el) => ({
    el,
    /* A font size is a CSS pixel and the bezel's `transform: scale()` does not
       change it -- only boxes are read through the scale. Dividing here reports
       a 16px floor as 17.9 and passes type that fails on the device.
       `../seat/assert.js` learned this the hard way. */
    px: round(parseFloat(getComputedStyle(el).fontSize)),
    text: el.textContent.trim().slice(0, 32),
  }));
  const belowFloor = sizes.filter((s) => s.px < FS_FLOOR).sort((a, b) => a.px - b.px);
  for (const s of belowFloor.slice(0, 8)) faults.push({ el: s.el, why: s.px + "px" });

  /* --- The target floor -------------------------------------------------
     Every real control. A Steam Deck has a touchscreen and these are the
     controls a finger goes for -- which is the same argument
     `handheld.css:2118-2139` makes when it raises twelve of the shipped
     lobby's, the smallest a 25px name field. */
  const stops = [...DECK.querySelectorAll("button, input, [data-stop]")].filter(vis);
  /*
   * `offsetWidth`, NOT `getBoundingClientRect`, and this round is the first one
   * in the folder where the difference decides anything.
   *
   * Every card here carries a rotation, and a rect is the AXIS-ALIGNED BOUNDING
   * BOX of a rotated element -- a 200x280 card at 7 degrees measures 233 wide.
   * That is a number about the tilt and not about the target, and it flatters
   * every direction by up to 16%. `offsetWidth` is the untransformed layout box
   * and is the conservative reading, which is the direction a floor should be
   * wrong in. The same trap in reverse is `../seat/assert.js`'s, which divided a
   * FONT size by the bezel scale and reported a 16px floor as 17.9.
   */
  const hits = stops.map((el) => ({ el, w: el.offsetWidth, h: el.offsetHeight }));
  const smallHits = hits.filter((h) => h.w < HIT_FLOOR || h.h < HIT_FLOOR);
  for (const h of smallHits.slice(0, 8)) faults.push({ el: h.el, why: h.w + "x" + h.h });

  /* --- The card floor ----------------------------------------------------
     Read off the rendered card rather than off the token, because the token is
     what the design INTENDED and the box is what the player got. The floor is
     `../handheld/assert.js`'s 96px; the shipped board's own figure at this size
     is 73.6px, which is where the floor came from. The layout box again, for the
     reason above -- and it is the right reading twice over here, because a
     selected card is scaled to 1.10 and a floor that counted the raise would
     pass a card that is only wide enough while you are already on it. */
  const cards = [...DECK.querySelectorAll(".mcard")].filter(vis);
  const cardW = cards.map((el) => ({ el, w: el.offsetWidth }));
  const smallCards = cardW.filter((c) => c.w < CARD_FLOOR);
  for (const c of smallCards.slice(0, 4)) faults.push({ el: c.el, why: c.w + "px card" });

  /* --- Escape ------------------------------------------------------------
     Measured against THE DECK. `overflow: hidden` on it hides this completely:
     the page reports `scrollHeight === clientHeight` while content visibly runs
     off the screen, which is the lesson the board round drew.
     `getBoundingClientRect` still reports the true position of a clipped box.

     The row's own slots are excluded and `rowFits` covers them instead, because
     a slot is a full-height box carrying a rotation and its bounding box grazes
     the stage edge in the wide states by a pixel or two of tilt. Failing a file
     on the AABB of a card that is entirely on screen is the check crying wolf;
     `rowFits` measures the CARDS, which is the fact anybody cares about. */
  let escaped = 0;
  for (const el of all) {
    if (el.closest(".row")) continue;
    const b = el.getBoundingClientRect();
    if (
      b.left < deckBox.left - 1 || b.right > deckBox.right + 1 ||
      b.top < deckBox.top - 1 || b.bottom > deckBox.bottom + 1
    ) {
      escaped += 1;
      if (escaped <= 4) faults.push({ el, why: "escapes" });
    }
  }

  /* --- Silent clipping ---------------------------------------------------
     A box cutting its own content with no ellipsis to say so. An ellipsised
     name is an honest trade and is only counted; a `nowrap` strip 20px too long
     for its own box looks exactly like one that fits, which is how a control
     legend loses its last item with nothing on screen saying so.

     Asked only of elements that OWN text: `scrollWidth` counts absolutely
     positioned descendants, so every card would report as clipping -- a
     `.mcard` is `overflow: hidden` with a label pinned inside it, which is the
     card working. `../handheld-board/assert.js` records the same correction. */
  const clipCandidates = textOwners.filter((el) => {
    if (getComputedStyle(el).overflowX === "visible") return false;
    return el.scrollWidth > el.clientWidth + 1;
  });
  const ellipsised = clipCandidates.filter(
    (el) => getComputedStyle(el).textOverflow === "ellipsis"
  );
  const silent = clipCandidates.filter(
    (el) => getComputedStyle(el).textOverflow !== "ellipsis"
  );
  for (const el of silent.slice(0, 4)) faults.push({ el, why: "silent clip" });

  /* A region that flattened to nothing. `e2e/layout.spec.ts` measures this on
     the shipped panel because at 950px the action list silently went to 2px
     while every assertion about the buttons still passed. */
  const collapsed = all.filter((el) => {
    const r = el.getBoundingClientRect();
    return r.height < 1 || r.width < 1;
  }).length;

  /* Scrollers with no reserved gutter: the reflow-on-hover bug waiting to
     happen, invisible until content crosses the line. */
  const scrollEls = all.filter((el) => {
    const s = getComputedStyle(el);
    return s.overflowY === "auto" || s.overflowY === "scroll";
  });
  const unguttered = scrollEls.filter(
    (el) => getComputedStyle(el).scrollbarGutter.indexOf("stable") < 0
  );
  for (const el of unguttered.slice(0, 4)) faults.push({ el, why: "no gutter" });

  /* Duplicate test ids: Playwright fails on these, and the four this round has
     to carry are the reason the check is here rather than in a spec. */
  const ids = [...DECK.querySelectorAll("[data-testid]")].map((el) => el.dataset.testid);
  const dupes = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];

  const imgs = [...DECK.querySelectorAll("img")];
  const brokenImages = imgs.filter((im) => im.complete && im.naturalWidth === 0).length;

  /* The four ids that have to survive the port. Every direction puts them on
     the node a click lands on, which is what makes the port mechanical --
     `../menu/README.md:316-324` sets the rule and this is it, checked. */
  const REQUIRED = ["home", "create-pod", "join-pod", "browse-decks"];
  const missingIds = REQUIRED.filter(
    (id) => !document.querySelector('[data-testid="' + id + '"]')
  );

  /* The brief's own item, asserted rather than eyeballed. */
  const defaultCentre = DEFAULT_INDEX === 1 && CARDS.length === 3;

  const spring = DOOR.springProfile();
  const slideReads =
    spring.traverseMs >= 100 && spring.settleMs <= 320 && spring.overshootPx <= 8;
  const tune = DOOR.spec ? DOOR.spec.tune : TUNE;

  const out = {
    screen: innerWidth + "x" + innerHeight,
    scalePct: Math.round(scale * 100),

    /* The round's own three */
    labelClear,
    labelWorstPct: Math.max(...states.map((s) => s.labelWorstPct)),
    inkClear,
    inkWorstPct: Math.max(...states.map((s) => s.inkWorstPct)),
    cardSpill: states.reduce((n, s) => n + s.cardSpill, 0),
    /* The narrowest strip of a stacked card left showing, anywhere, and the
       widest label that has to fit in one. The first must exceed the second
       plus the label's own inset or `labelClear` fails, which is the round's
       one derived constraint rather than a taste. */
    sliverPx: Math.min(...states.map((s) => s.sliverPx).filter((n) => n !== null)),
    widestLabelPx: Math.max(...states.map((s) => s.widestLabelPx)),
    rowFits,
    rowWidthPx: Math.max(...states.map((s) => s.rowWidthPx)),
    rowMarginPx: Math.min(...states.flatMap((s) => [s.rowLeftPx, s.rowRightPx])),
    slideReads,
    traverseMs: spring.traverseMs,
    traverseFrames: spring.frames,
    settleMs: spring.settleMs,
    overshootPx: spring.overshootPx,
    defaultCentre,
    defaultOn: CARDS[DEFAULT_INDEX].label,

    /* What the row is tuned to, so the README table is measured and a direction
       that moved a constant cannot do it quietly. */
    tune: {
      step: tune.STEP, push: tune.PUSH, bunch: tune.BUNCH,
      arc: tune.ARC, lift: tune.LIFT, raise: tune.RAISE,
    },
    states,

    /* The standing floors */
    cards: cards.length,
    minCardPx: cardW.length ? Math.min(...cardW.map((c) => c.w)) : null,
    smallCards: smallCards.length,

    minFontPx: sizes.length ? Math.min(...sizes.map((s) => s.px)) : null,
    textNodes: sizes.length,
    belowFloor: belowFloor.length,
    belowFloorWorst: belowFloor.slice(0, 6).map((s) => ({ px: s.px, text: s.text })),

    stops: stops.length,
    minHitPx: hits.length ? Math.min(...hits.map((h) => Math.min(h.w, h.h))) : null,
    smallHits: smallHits.length,
    smallHitsWorst: smallHits.slice(0, 6).map((h) => ({ w: h.w, h: h.h })),

    escaped,
    collapsedRegions: collapsed,
    scrollers: scrollEls.length,
    unguttered: unguttered.length,
    ellipsised: ellipsised.length,
    silentClips: silent.length,

    /* A native tooltip opens on hover and on nothing else, so on a controller it
       is information that cannot be reached at all. The shipped client had 45
       and has none left; a mockup that grows one has moved a channel out of
       reach without saying so. */
    titleAttrs: DECK.querySelectorAll("[title]").length,
    duplicateTestIds: dupes,
    missingTestIds: missingIds,
    brokenImages,

    faults,
  };

  out.PASS =
    out.labelClear &&
    out.inkClear &&
    out.cardSpill === 0 &&
    out.rowFits &&
    out.slideReads &&
    out.defaultCentre &&
    out.belowFloor === 0 &&
    out.smallHits === 0 &&
    out.smallCards === 0 &&
    out.escaped === 0 &&
    out.collapsedRegions === 0 &&
    out.titleAttrs === 0 &&
    out.unguttered === 0 &&
    out.silentClips === 0 &&
    out.duplicateTestIds.length === 0 &&
    out.missingTestIds.length === 0 &&
    out.brokenImages === 0;

  return out;
}

if (typeof window !== "undefined") window.DOOR_ASSERT = DOOR_ASSERT;
