/**
 * The handheld gates, as numbers.
 *
 * Ported from `mockups/handheld/assert.js`, whose founding principle is the one
 * this file exists for:
 *
 * > Where a visual property reduces to a number, assert the number.
 *
 * That was learned the hard way twice. `body { overflow: hidden }` makes a page
 * report `scrollHeight === clientHeight` while content visibly runs off the
 * bottom, so a naive overflow check passes straight through the failure it was
 * written for. And 2.11px text looked fine in every screenshot for months --
 * nobody reviewing a picture of a board notices that a type line is unreadable,
 * because they already know what it says.
 *
 * The rule the design round states, and the reason this is not optional:
 *
 * > Do not ship a controller mode without the 16px floor asserted in CI.
 *
 * ## It runs in the page
 *
 * `page.evaluate` serialises this function, so it may close over nothing and
 * import nothing. Everything it needs is inlined, and the app publishes its own
 * ring state on `window.__AUTOMTG_RING` rather than having this re-derive it --
 * a gate that reimplements the thing it is checking is a gate that can agree
 * with itself while disagreeing with the app.
 */

export interface HandheldReport {
  /** Smallest font size on anything that owns a text node and is not hidden. */
  minFontPx: number;
  belowFloor: { text: string; px: number; selector: string }[];
  /** Smallest card the ring can land on. */
  minCardPx: number;
  /** Cards exempted from the card floor because they sit beside their own name. */
  thumbsExempted: number;
  /** Focusable or tappable boxes under the 44px hit floor. */
  smallHits: { selector: string; w: number; h: number }[];
  stops: number;
  cursors: number;
  /** The state names a stop, the stop is on screen, and it is not wearing the ring. */
  ringLost: boolean;
  ringWidthPx: number;
  ringStyle: string;
  /** Stops no press from any other stop can reach. */
  unreachable: string[];
  /** Elements whose box runs outside the surface that should contain them. */
  spilled: string[];
  /** Regions that have collapsed to nothing. */
  collapsed: string[];
  /**
   * Regions holding more than they can show.
   *
   * The check `spilled` should have been and was not. It looks only at
   * `.play__mine .card`, and measures them against `.play__mine` -- which is
   * itself the scroll container, so a card clipped by the *grid row* is inside
   * its limit by definition. Everything that actually went missing at 1200x800
   * was something else: band labels, the orb, the pile counts, whole rows of the
   * action list.
   *
   * `scrollHeight > clientHeight` asks the question directly and does not care
   * what kind of element it is. It is allowed to be non-zero only where
   * scrolling is the design -- see `SCROLLERS`.
   */
  overflowing: { selector: string; by: number }[];
  /**
   * Fans holding more cards than they have room for.
   *
   * A lane and the hand lay cards along one axis, and both are inside boxes
   * that clip. `overflowing` asks the vertical question of named containers;
   * this asks the horizontal one of every `[data-fan]`, which is the shape
   * that goes wrong when a card grows or a seventh card is drawn.
   *
   * It is here because the mockup round hit it: six cards at 176px is 1056px
   * in the 947 the foot had, so the hand ran 79px past the foot and sat on top
   * of the commit panel's first control. The deck was `overflow: hidden`, so
   * the page reported no overflow anywhere and the only symptom was **a button
   * that had quietly stopped being clickable**.
   */
  fanOverflow: { selector: string; by: number }[];
  /**
   * Seats whose counts disagree with the board they summarise.
   *
   * THE FAILURE MODE THIS WHOLE FAMILY OF COMPONENTS HAS.
   * `mockups/seat/README.md` records five of its six directions as unable to be
   * WRONG about the board -- lands were never in the payload, so nothing could
   * contradict them, and "how many lands has that seat got" was unanswerable
   * from the strip at any density.
   *
   * So the numbers are re-derived here from a DIFFERENT source: the rendered
   * `.perm` cells against a walk over that seat's own lanes. `musterOf` is not
   * imported and could not be -- `page.evaluate` sends this function alone --
   * which is exactly what makes the two independent. Two derivations that
   * agreed by construction would be a gate agreeing with itself.
   *
   * On a handheld an opponent's lanes are clipped to zero height and their
   * cards are still in the document, so the walk works there too; that is the
   * same property `FxLayer` depends on.
   */
  seatsDisagree: { pid: string; field: string; said: number; counted: number }[];
  /**
   * Scrollers that have not reserved their scrollbar's width.
   *
   * A styled `::-webkit-scrollbar` is a classic bar, not an overlay, so it
   * takes its 8px the instant it appears -- and re-wraps every line under it.
   * On a rules box that means the text you are reading reflows as it grows,
   * which is the one surface where that is least acceptable.
   *
   * `scrollbar-gutter: stable` reserves it up front. Anything that scrolls and
   * has not is a line-shift waiting for its first long card.
   */
  unguttered: string[];
  /**
   * Regions taller than the budget the layout gives them.
   *
   * An opponent's seat measured 220px of an 800px screen while holding an empty
   * board, and no gate noticed, because nothing was overflowing and nothing had
   * collapsed -- the height was simply being taken from somewhere else. A
   * budget is the only shape of assertion that catches "this fits, and it
   * should not have been allowed to".
   */
  overBudget: { selector: string; h: number; cap: number }[];
  /** Native tooltips, which a controller can never open. */
  titleAttrs: number;
  /** `data-testid` values appearing more than once -- Playwright fails on these. */
  duplicateTestIds: string[];
  brokenImages: number;
  pass: boolean;
  failures: string[];
}

/** The floors. Every one of them comes from a 7-inch panel at 40-50cm. */
export const FLOORS = {
  /** Nothing carrying information may be smaller. */
  font: 16,
  /** Any card the ring can land on. */
  card: 96,
  /** Any focusable or tappable box. */
  hit: 44,
  /** The focus outline. */
  ring: 3,
} as const;

/**
 * The gate, as one self-contained function.
 *
 * Deliberately not split into helpers: `page.evaluate` sends the source of this
 * function alone, so anything it calls has to be declared inside it.
 */
export function handheldAssert(): HandheldReport {
  const FONT = 16;
  const CARD = 96;
  const HIT = 44;
  const RING = 3;

  const root =
    document.querySelector<HTMLElement>(".table") ??
    document.querySelector<HTMLElement>(".screen") ??
    document.body;

  const path = (el: Element): string => {
    const tag = el.tagName.toLowerCase();
    const cls = (el.className || "").toString().trim().split(/\s+/).slice(0, 2).join(".");
    const id = el.getAttribute("data-testid") ?? el.getAttribute("data-stop");
    return `${tag}${cls ? `.${cls}` : ""}${id ? `[${id}]` : ""}`;
  };

  /*
   * On screen, not merely laid out.
   *
   * `getBoundingClientRect` reports an element's own box even when an ancestor
   * has clipped it out of existence -- and the handheld layout does exactly
   * that: an opponent's lanes are `height: 0; overflow: hidden`, because their
   * cards must stay in the document for `FxLayer` to anchor damage numerals and
   * exit ghosts to. Without this walk the gate reported 22 cards below the card
   * floor and a pile of text below the font floor, all of it inside a box with
   * no height, none of it visible to anybody.
   *
   * That is the worst kind of gate failure: it sends you fixing something that
   * is not wrong, and the "fix" would have been to stop clipping the lanes,
   * which would have broken the effects anchoring instead.
   */
  const visible = (el: Element): boolean => {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (Number.parseFloat(style.opacity) === 0) return false;
    const box = el.getBoundingClientRect();
    if (box.width <= 0 || box.height <= 0) return false;
    for (let a = el.parentElement; a; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.overflow === "visible" && s.overflowX === "visible" && s.overflowY === "visible") {
        continue;
      }
      const clip = a.getBoundingClientRect();
      if (clip.width <= 0 || clip.height <= 0) return false;
      const intersects =
        box.right > clip.left &&
        box.left < clip.right &&
        box.bottom > clip.top &&
        box.top < clip.bottom;
      if (!intersects) return false;
    }
    return true;
  };

  /*
   * Only elements that OWN a text node are measured, and `aria-hidden` is
   * skipped. That is the honest line between a font-size floor and a font-size
   * ban: a wrapper inherits a size it never renders, and counting it would
   * report failures at elements with nothing in them.
   *
   * A mana pip is NOT exempt, even though it is a symbol: its letter is the
   * only thing identifying it.
   */
  const belowFloor: { text: string; px: number; selector: string }[] = [];
  let minFontPx = Number.POSITIVE_INFINITY;
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (el.closest("[aria-hidden='true']")) continue;
    const ownsText = [...el.childNodes].some(
      (n) => n.nodeType === 3 && (n.textContent ?? "").trim().length > 0,
    );
    if (!ownsText || !visible(el)) continue;
    const px = Number.parseFloat(getComputedStyle(el).fontSize);
    if (!Number.isFinite(px)) continue;
    minFontPx = Math.min(minFontPx, px);
    if (px < FONT) {
      belowFloor.push({
        text: (el.textContent ?? "").trim().slice(0, 40),
        px: Math.round(px * 100) / 100,
        selector: path(el),
      });
    }
  }
  if (!Number.isFinite(minFontPx)) minFontPx = FONT;

  /*
   * Card floor. `.face--thumb` is an explicit, COUNTED exemption -- a thumbnail
   * beside its own name in real type is legible at any size, and counting the
   * exemptions is what stops the exemption quietly becoming the rule.
   */
  let minCardPx = Number.POSITIVE_INFINITY;
  let maxCardPx = 0;
  let thumbsExempted = 0;
  for (const face of root.querySelectorAll<HTMLElement>(".face")) {
    if (!visible(face)) continue;
    if (face.classList.contains("face--thumb")) {
      thumbsExempted += 1;
      continue;
    }
    // Only cards the ring can land on: a card inside a stop is one you can be
    // asked to read, and one that is purely decorative is not.
    if (!face.closest("[data-stop]")) continue;
    const w = face.getBoundingClientRect().width;
    minCardPx = Math.min(minCardPx, w);
    maxCardPx = Math.max(maxCardPx, w);
  }
  if (!Number.isFinite(minCardPx)) minCardPx = CARD;

  /* Hit floor, on real controls only. */
  const smallHits: { selector: string; w: number; h: number }[] = [];
  for (const el of root.querySelectorAll<HTMLElement>("button, a[href], input, select")) {
    if (!visible(el) || (el as HTMLButtonElement).disabled) continue;
    const box = el.getBoundingClientRect();
    // Rounded, like the card floor: a 43.5px box is a 44px box that CSS and the
    // device pixel ratio disagreed about by half a pixel, and reporting it is
    // reporting rounding as a design failure.
    if (Math.round(box.width) < HIT || Math.round(box.height) < HIT) {
      smallHits.push({
        selector: path(el),
        w: Math.round(box.width),
        h: Math.round(box.height),
      });
    }
  }

  /*
   * The ring.
   *
   * `cursors: 0` cannot be failed on its own -- a screen with nothing to point
   * at legitimately has no ring. What CAN be failed is the disagreement: the
   * state names a stop, that stop is on screen, and it is not wearing the ring.
   */
  const ring = (
    window as unknown as {
      __AUTOMTG_RING?: {
        cursor: () => string | null;
        stops: () => string[];
        unreachable: () => string[];
      };
    }
  ).__AUTOMTG_RING;
  const named = ring?.cursor() ?? null;
  const stops = ring?.stops() ?? [];
  const marked = document.querySelectorAll<HTMLElement>("[data-cursor]");
  const ringLost = named !== null && stops.includes(named) && marked.length === 0;
  const cursorStyle = marked[0] ? getComputedStyle(marked[0]) : null;
  const ringWidthPx = cursorStyle ? Number.parseFloat(cursorStyle.outlineWidth) : 0;
  const ringStyle = cursorStyle?.outlineStyle ?? "none";

  /*
   * Spill. Measured against the surface that should contain the element, never
   * against the page: `body { overflow: hidden }` makes the page lie.
   */
  const spilled: string[] = [];
  const foot = document.querySelector<HTMLElement>(".table__foot");
  const footTop = foot ? foot.getBoundingClientRect().top : Number.POSITIVE_INFINITY;
  for (const card of root.querySelectorAll<HTMLElement>(".play__mine .card")) {
    if (!visible(card)) continue;
    const box = card.getBoundingClientRect();
    // A scroll container clipping its own content is not spill.
    const scroller = card.closest<HTMLElement>(".play__mine");
    const limit = scroller ? scroller.getBoundingClientRect().bottom : footTop;
    if (box.top > limit + 2) spilled.push(path(card));
    if (box.right > window.innerWidth + 2 || box.left < -2) spilled.push(path(card));
  }

  /* Regions that must never flatten to nothing. */
  const collapsed: string[] = [];
  for (const selector of [".acts__list", ".preview", ".table__foot", ".play__mine"]) {
    const el = document.querySelector<HTMLElement>(selector);
    if (!el) continue;
    const box = el.getBoundingClientRect();
    if (box.height < 8 || box.width < 8) collapsed.push(selector);
  }

  /*
   * Regions holding more than they can show.
   *
   * This is the check whose absence let a board that did not fit pass every
   * gate in the suite. `overflow: hidden` and `overflow-y: auto` both make a
   * layout failure look like a design decision from the outside: the page
   * reports no scroll, nothing has collapsed, and the content is simply not
   * there. Asking `scrollHeight > clientHeight` of the containers themselves is
   * the question, and it does not depend on guessing which child went missing.
   *
   * Two tolerances, both earned rather than chosen. `SLACK` of 2px is the
   * sub-pixel disagreement `4.2` already documents for the card and hit floors:
   * a `calc()` over a `clamp()` lands on fractions and `scrollHeight` is an
   * integer. `SCROLLERS` is the list of places where scrolling IS the design --
   * a long action list and a deep zone view are meant to scroll, and a gate that
   * forbade it would be demanding a different feature.
   */
  const SLACK = 2;
  const SCROLLERS = new Set([
    ".acts__list",
    ".stackpanel",
    ".peek__grid",
    ".logover",
    // The reader's rules box: a card with more text than 78px is the ordinary
    // case, not the failure. It reserves its gutter, which `unguttered` checks.
    ".reader__rules",
  ]);
  const overflowing: { selector: string; by: number }[] = [];
  for (const selector of [
    ".play__mine",
    ".play__mine .mat__side",
    ".play__mine .mat__lanes",
    ".play__opponents",
    ".mat--compact",
    ".mat--compact .orb__body",
    ".rail--right",
    ".acts",
    ".table__foot",
    ".track",
  ]) {
    if (SCROLLERS.has(selector)) continue;
    for (const el of document.querySelectorAll<HTMLElement>(selector)) {
      if (!visible(el)) continue;
      const by = el.scrollHeight - el.clientHeight;
      if (by > SLACK) overflowing.push({ selector, by });
    }
  }

  /*
   * The same question asked sideways, of every fan.
   *
   * `[data-fan]` is carried by `.lane__cards` and `.hand__rail` -- the two
   * places cards are laid along an axis with no wrapping to save them. Marked
   * on the CONTAINER rather than matched by class name so that a third fan
   * (a rail row of staged attackers, say) is covered the day it is written
   * rather than the day somebody remembers to add it here.
   */
  const fanOverflow: { selector: string; by: number }[] = [];
  for (const el of document.querySelectorAll<HTMLElement>("[data-fan]")) {
    if (!visible(el)) continue;
    /*
     * MEASURED IN LAYOUT, NOT IN PAINTED BOXES.
     *
     * `scrollWidth` was the obvious question and it is the wrong one: scroll
     * overflow counts a child's TRANSFORMED box, and the hand is an arc -- the
     * outermost cards are rotated about 8 degrees, so a 103px card reports a
     * 122px rect and every hand of six or more looked 26-30px over. The arc is
     * the feature; `docs/roadmap.md` asks for it by name.
     *
     * `offsetLeft` and `offsetWidth` are untransformed layout values, which is
     * the same distinction `mockups/handheld-board/_board.js` records about its
     * own `BOARD.lay()` -- and the same trap `mockups/seat/assert.js` fell into
     * when it divided a font size by a scale.
     */
    const kids = [...el.children] as HTMLElement[];
    if (kids.length === 0) continue;
    let reach = 0;
    for (const kid of kids) reach = Math.max(reach, kid.offsetLeft + kid.offsetWidth);
    const by = Math.round(reach - el.clientWidth);
    if (by <= SLACK) continue;
    // The room it had comes with it: "26px over" is not actionable on its own,
    // and the useful question is always whether the fan or its box is wrong.
    const room = el.parentElement ? Math.round(el.parentElement.clientWidth) : 0;
    fanOverflow.push({
      selector: `${path(el)} (${Math.round(reach)} laid out in ${Math.round(
        el.clientWidth,
      )}, parent ${room}, n=${kids.length})`,
      by,
    });
  }

  /*
   * THE SEAT AND THE BOARD IT SUMMARISES, CHECKED AGAINST EACH OTHER.
   *
   * A summary that cannot be checked against the thing it summarises is the
   * failure `mockups/seat/` names. Here it can be: every seat carries
   * `data-perm` cells with `data-total`/`data-open`, and that seat's own
   * permanents are in the document under `lane-<pid>-<Lane>` whether or not
   * they are drawn at a size anybody can see.
   *
   * `data-stack-count` and not a node count, because the board COLLAPSES
   * duplicates -- seven Forests are one card with a x7 on it -- and a gate that
   * counted boxes would report six missing lands on every developed board.
   */
  const seatsDisagree: { pid: string; field: string; said: number; counted: number }[] = [];
  for (const seat of document.querySelectorAll<HTMLElement>(".seat[data-player]")) {
    const pid = seat.dataset.player ?? "?";
    const lanes = document.querySelectorAll<HTMLElement>(`[data-testid^="lane-${pid}-"]`);
    if (lanes.length === 0) continue;

    const walk = (laneName: string) => {
      let total = 0;
      let open = 0;
      for (const lane of lanes) {
        if (!(lane.getAttribute("data-testid") ?? "").endsWith(laneName)) continue;
        for (const stack of lane.querySelectorAll<HTMLElement>("[data-stack-count]")) {
          const count = Number(stack.getAttribute("data-stack-count") ?? "1") || 1;
          total += count;
          // A group is either all tapped or all untapped -- `stackKey` includes
          // it -- so one card's class covers the whole stack.
          if (!stack.querySelector(".card--tapped")) open += count;
        }
      }
      return { total, open };
    };

    const said = (kind: string, attr: string) => {
      const cell = seat.querySelector<HTMLElement>(`[data-perm="${kind}"]`);
      const raw = cell?.getAttribute(attr) ?? "";
      return raw === "" ? null : Number(raw);
    };

    const lands = walk("Lands");
    const creatures = walk("Creatures");
    const other = walk("Artifacts-Enchantments");

    const checks: [string, number | null, number][] = [
      ["lands", said("land", "data-total"), lands.total],
      ["landsUntapped", said("land", "data-open"), lands.open],
      ["creatures", said("creature", "data-total"), creatures.total],
      ["creaturesUntapped", said("creature", "data-open"), creatures.open],
      ["other", said("other", "data-total"), other.total],
    ];
    for (const [field, saidValue, counted] of checks) {
      if (saidValue === null || saidValue === counted) continue;
      seatsDisagree.push({ pid, field, said: saidValue, counted });
    }
  }

  /*
   * Scrollers without a reserved gutter.
   *
   * Only elements that actually scroll on the axis they declare -- an
   * `overflow-y: auto` box whose content fits has no bar and needs no gutter
   * today, but it is one long card away from having one, so the check is on the
   * declaration and not on the current content.
   */
  const unguttered: string[] = [];
  for (const el of root.querySelectorAll<HTMLElement>("*")) {
    if (!visible(el)) continue;
    const style = getComputedStyle(el);
    const scrolls = style.overflowY === "auto" || style.overflowY === "scroll";
    if (!scrolls) continue;
    if (style.scrollbarGutter && style.scrollbarGutter !== "auto") continue;
    // `scrollbar-width: none` hides the bar outright, which reserves nothing
    // but also takes nothing -- a different, and equally stable, answer.
    if (style.scrollbarWidth === "none") continue;
    unguttered.push(path(el));
  }

  /*
   * Region budgets, in fractions of the viewport rather than in pixels.
   *
   * The numbers are what the compact layout is designed around and they are
   * stated here so a change to any of them has to be deliberate. An opponent's
   * seat is the one that matters: `--pod-seat-h` caps it at 96px, and before
   * that cap existed it drew 220px against an empty board -- 28% of the screen
   * for a player with nothing in play, taken straight out of the viewer's own
   * mat, which then clipped its graveyard off the bottom.
   *
   * Fractions rather than literals so this says the same thing at 1200x800 and
   * at 1280x800, which is the pair of sizes this layout has to hold.
   */
  const vh = window.innerHeight;
  const BUDGET: [string, number][] = [
    // One opponent's whole seat, and its lanes if it has any.
    [".mat--compact", 0.14],
    // The seat itself, which is a stated 96px design: `mockups/seat/` measured
    // every one of its directions inside 332x96, and a seat drawn at some other
    // height is a different design wearing the same name.
    [".seat", 0.13],
    // Every opponent together. They share a row, so this is the row.
    [".play__opponents", 0.14],
    // The phase ribbon is a strip, not a panel.
    [".track", 0.08],
    // The foot: the hand, the hints, the tools and the slab.
    [".table__foot", 0.33],
  ];
  const overBudget: { selector: string; h: number; cap: number }[] = [];
  for (const [selector, share] of BUDGET) {
    const cap = Math.round(vh * share);
    for (const el of document.querySelectorAll<HTMLElement>(selector)) {
      if (!visible(el)) continue;
      const h = Math.round(el.getBoundingClientRect().height);
      if (h > cap + SLACK) overBudget.push({ selector, h, cap });
    }
  }

  /*
   * Native tooltips. A `title` opens on hover and on nothing else, so on a
   * controller it is information that cannot be reached at all.
   */
  const titleAttrs = document.querySelectorAll("[title]").length;

  /*
   * Duplicate test ids are REPORTED, not failed.
   *
   * This was a hard failure, on the reasoning that Playwright's strict mode
   * fails a query matching more than one element -- and it does. But the rule
   * it implies is wrong for this codebase: `e2e/pod.spec.ts` writes
   * `getByTestId("seat-1").getByTestId("card-back")`, which is correct practice
   * and makes a shared id on a repeated component entirely legitimate. Failing
   * on it forced three components to number ids that nothing wanted numbered.
   *
   * So it is kept as a number worth seeing -- a sudden jump is still a signal --
   * and left out of `failures`.
   */
  const seenIds = new Map<string, number>();
  for (const el of document.querySelectorAll("[data-testid]")) {
    const id = el.getAttribute("data-testid") ?? "";
    seenIds.set(id, (seenIds.get(id) ?? 0) + 1);
  }
  const duplicateTestIds = [...seenIds.entries()].filter(([, n]) => n > 1).map(([id]) => id);

  let brokenImages = 0;
  for (const img of document.querySelectorAll("img")) {
    if (img.complete && img.naturalWidth === 0) brokenImages += 1;
  }

  const unreachable = ring?.unreachable() ?? [];

  const failures: string[] = [];
  if (belowFloor.length > 0) {
    failures.push(
      `${belowFloor.length} element(s) under ${FONT}px: ${belowFloor
        .slice(0, 6)
        .map((b) => `${b.selector} "${b.text}" ${b.px}px`)
        .join("; ")}`,
    );
  }
  /*
   * Rounded, because the solver legitimately lands a hair under.
   *
   * `--card-w` is a `calc()` over a `clamp()`, so the fit solver's answer at the
   * floor comes out as 95.9744px -- which is the floor, and reporting it as a
   * violation is reporting floating-point arithmetic as a design failure.
   */
  if (Math.round(minCardPx) < CARD) {
    failures.push(`smallest focusable card is ${Math.round(minCardPx * 100) / 100}px`);
  }
  if (smallHits.length > 0) {
    failures.push(
      `${smallHits.length} control(s) under ${HIT}px: ${smallHits
        .slice(0, 6)
        .map((h) => `${h.selector} ${h.w}x${h.h}`)
        .join("; ")}`,
    );
  }
  if (marked.length > 1) failures.push(`${marked.length} cursors`);
  if (ringLost) failures.push(`the cursor names ${named} but nothing wears the ring`);
  /*
   * The ring is only required where a ring is meant to exist.
   *
   * A mouse player has a pointer to say where they are and gets no ring at all --
   * that is the design, and `html[data-input="mouse"]` suppresses it
   * deliberately. Demanding one here would fail the gate for the input method
   * the whole feature is careful not to change.
   */
  const inputMode = document.documentElement.getAttribute("data-input");
  const ringExpected = inputMode === "pad" || inputMode === "keyboard";
  if (ringExpected && marked.length === 1 && (ringWidthPx < RING || ringStyle === "none")) {
    failures.push(`ring is ${ringWidthPx}px ${ringStyle}`);
  }
  if (unreachable.length > 0) failures.push(`unreachable stops: ${unreachable.join(", ")}`);
  if (spilled.length > 0) failures.push(`spilled: ${spilled.slice(0, 5).join(", ")}`);
  if (collapsed.length > 0) failures.push(`collapsed: ${collapsed.join(", ")}`);
  if (overflowing.length > 0) {
    failures.push(
      `overflowing: ${overflowing.map((o) => `${o.selector} by ${o.by}px`).join(", ")}`,
    );
  }
  if (overBudget.length > 0) {
    failures.push(
      `over budget: ${overBudget.map((o) => `${o.selector} ${o.h}px > ${o.cap}px`).join(", ")}`,
    );
  }
  if (fanOverflow.length > 0) {
    failures.push(
      `fans overflowing: ${fanOverflow.map((f) => `${f.selector} by ${f.by}px`).join(", ")}`,
    );
  }
  if (seatsDisagree.length > 0) {
    failures.push(
      `seats disagree with the board: ${seatsDisagree
        .map((d) => `P${d.pid} ${d.field} says ${d.said}, board has ${d.counted}`)
        .join("; ")}`,
    );
  }
  if (unguttered.length > 0) {
    failures.push(`scrollers with no reserved gutter: ${unguttered.join(", ")}`);
  }
  if (titleAttrs > 0) failures.push(`${titleAttrs} native title tooltip(s)`);
  if (brokenImages > 0) failures.push(`${brokenImages} broken image(s)`);

  return {
    minFontPx: Math.round(minFontPx * 100) / 100,
    belowFloor,
    minCardPx: Math.round(minCardPx),
    thumbsExempted,
    smallHits,
    stops: stops.length,
    cursors: marked.length,
    ringLost,
    ringWidthPx,
    ringStyle,
    unreachable,
    spilled,
    collapsed,
    overflowing,
    fanOverflow,
    seatsDisagree,
    unguttered,
    overBudget,
    titleAttrs,
    duplicateTestIds,
    brokenImages,
    pass: failures.length === 0,
    failures,
  };
}
