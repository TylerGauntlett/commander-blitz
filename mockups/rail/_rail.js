/*
 * The shell every rail mockup is mounted into, and the two holds all three share.
 *
 * NOT LINKED. `inline.py` splices this between each file's BEGIN and END
 * `_rail.js` markers. Same contract as `../seat/_seat.js` and for the same
 * reason: a mockup has to open standalone from file://, file:// blocks the fetch
 * a module import would need, and three hand-inlined copies of one file quietly
 * stop being the same file.
 *
 * WHAT IS IN HERE: the ghosted board, the ghosted foot, the phase ribbon, the
 * card and stack holds, the review keys, the deck fit, and `RAIL.mount()`.
 *
 * WHAT IS NOT: any list. A file supplies its own `list` markup and its own
 * `wire`, and that is the only thing the three differ by -- which is the round's
 * claim, so it had better be the only thing.
 *
 * NOTHING HERE RUNS ON LOAD. `render()` needs the file's list, so the file calls
 * `RAIL.mount({...})` at the end of its own script.
 */

/* The board under the rail ------------------------------------------------
   Turn 8 of the reference screenshot at 1280x800, same as every other round in
   this folder: one opponent, three lanes, five in hand. Ghosted, because none of
   it is the design -- it is the room the design is spending. */

const GHOST_LANES = [4, 2, 6];

/*
 * All thirteen, because all thirteen are in the document.
 *
 * `e2e/smoke.spec.ts` counts them and the marker's `layoutId` animation runs
 * across them, so a ribbon that draws five is not the ribbon this rail sits
 * under -- and the height of the real one is what leaves the rail its 514px.
 */
const STEPS = [
  "Untap", "Upkeep", "Draw", "Main 1", "Begin combat", "Attackers", "Blockers",
  "First strike", "Damage", "End combat", "Main 2", "End step", "Cleanup",
];

const ribbon = (now) =>
  '<span class="track__turn">Turn <b>8</b> · <b>You</b></span>' +
  STEPS.map(
    (s) => '<span class="step' + (s === now ? " step--now" : "") + '">' + esc(s) + "</span>"
  ).join("");

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const ghostBoard = () =>
  '<div class="ghost" aria-hidden="true">' +
    '<div class="gseat">' +
      '<div class="gseat__art"></div>' +
      '<div class="gseat__col">' +
        '<div class="gbar" style="width:40%"></div>' +
        '<div class="gbar" style="width:72%"></div>' +
      "</div>" +
    "</div>" +
    '<div class="gmat">' +
      GHOST_LANES.map(
        (n) => '<div class="glane">' + '<div class="gcard"></div>'.repeat(n) + "</div>"
      ).join("") +
    "</div>" +
  "</div>";

/* Areas, not source order: the hand is drawn above the strip (a raised card
   rises out of `.hand` and would otherwise draw over the hints), but the ring
   walks the strip first, which is the order a thumb wants. Same reasoning as
   `handheld.css:299-340`. */
const ghostFoot = (hints) =>
  '<div class="gfoot">' +
    '<div class="tools">' +
      '<button class="tool" type="button" aria-label="Sound">&#128266;</button>' +
      '<button class="tool" type="button" aria-label="Undo">&#8634;</button>' +
      '<button class="tool" type="button" aria-label="Quit">&#10005;</button>' +
    "</div>" +
    '<div class="gfan" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>' +
    '<div class="hints">' + hints + "</div>" +
  "</div>";

const hint = (glyph, verb, live) =>
  '<span class="hint"><b class="glyph' + (live ? " glyph--live" : "") + '">' + glyph +
  '</b> <span class="hint__verb">' + esc(verb) + "</span></span>";

/* The two holds -----------------------------------------------------------
   Both are `.oppboard`'s family: fixed over the whole screen, owning it while
   they are up, outside the zoom solver. `o` and `k` stand in for Y and X. */

const CARD = {
  name: "Vampire Nighthawk",
  type: "Creature — Vampire Shaman",
  rules: "Flying, deathtouch, lifelink",
  pt: "2/3",
  cost: [["1", "generic"], ["B", "B"], ["B", "B"]],
};

/* The letter is decoration; the cost is `costHTML`'s `aria-label`. See the note
   on `.pip` in `_rail.css` for why that is the honest line and not a way round
   the type gate. */
const pipHTML = ([label, tone]) =>
  '<span class="pip pip--' + tone + '" aria-hidden="true">' + esc(label) + "</span>";

const costHTML = (cost) =>
  '<span class="cost" aria-label="' + cost.map(([l]) => "{" + l + "}").join("") + '">' +
  cost.map(pipHTML).join("") + "</span>";

const cardHold = () =>
  '<div class="over over--card" id="hold-card" hidden>' +
    '<p class="over__head">B to close</p>' +
    '<div class="big">' +
      '<div class="face face--B">' +
        '<div class="face__art" aria-hidden="true"></div>' +
        '<div class="face__head">' +
          '<div class="face__title">' +
            '<span class="face__glyph" aria-hidden="true">◆</span>' +
            '<span class="face__name">' + esc(CARD.name) + "</span>" +
          "</div>" +
          costHTML(CARD.cost) +
        "</div>" +
        '<div class="face__foot">' +
          '<div class="face__type">' + esc(CARD.type) + "</div>" +
          '<div class="face__rules">' + esc(CARD.rules) + "</div>" +
          '<div class="face__footer"><span class="face__stats">' + CARD.pt + "</span></div>" +
        "</div>" +
      "</div>" +
    "</div>" +
  "</div>";

const STACK = [
  { name: "Lightning Bolt", note: "→ you", top: true },
  { name: "Sol Ring", note: "ability", top: false },
];

const stackHold = () =>
  '<div class="over over--stack" id="hold-stack" hidden>' +
    '<p class="over__head">B to close</p>' +
    '<div class="stacklist">' +
      STACK.map(
        (s) =>
          '<div class="sitem' + (s.top ? " sitem--top" : "") + '"><b>' +
          esc(s.name) + "</b> <span>" + esc(s.note) + "</span></div>"
      ).join("") +
    "</div>" +
  "</div>";

/* The mount ---------------------------------------------------------------
   A file hands over four things: the phase the ribbon is lit on, its list, its
   commit bar, and the wiring for both. */

const RAIL = {
  spec: null,

  mount(spec) {
    RAIL.spec = spec;
    RAIL.render();
    addEventListener("resize", RAIL.fit);
    addEventListener("keydown", RAIL.key);
  },

  render() {
    const spec = RAIL.spec;
    document.getElementById("root").innerHTML =
      '<div class="bezel">' +
        '<div class="deck">' +
          '<div class="shell">' +
            '<div class="track">' + ribbon(spec.phase) + "</div>" +
            '<div class="body">' +
              ghostBoard() +
              '<div class="rail" data-testid="rail">' +
                '<div class="acts"><div class="list" data-testid="action-list">' + spec.list + "</div></div>" +
                '<div class="commit">' + spec.commit + "</div>" +
              "</div>" +
            "</div>" +
            ghostFoot(spec.hints) +
          "</div>" +
          cardHold() +
          stackHold() +
        "</div>" +
        '<div class="bezel__tag" id="tag"></div>' +
      "</div>";

    if (spec.wire) spec.wire(document.querySelector(".rail"));
    RAIL.tag();
    RAIL.fit();
  },

  /*
   * The deck is 1280x800 whatever window is open.
   *
   * Scaled rather than resized, so every number `assert.js` reads is a real
   * device pixel. A mockup that reflows to the reviewer's monitor is being
   * reviewed at the wrong density, and it is always wrong in the direction that
   * flatters the design.
   */
  scale: 1,
  fit() {
    const el = document.querySelector(".deck");
    if (!el) return;
    RAIL.scale = Math.max(0.3, Math.min(2, Math.min((innerWidth - 26) / 1280, (innerHeight - 84) / 800)));
    el.style.transform = "scale(" + RAIL.scale + ")";
    const bezel = document.querySelector(".bezel");
    if (bezel) {
      bezel.style.width = 1280 * RAIL.scale + 20 + "px";
      bezel.style.height = 800 * RAIL.scale + 44 + "px";
    }
  },

  tag(extra) {
    const tag = document.getElementById("tag");
    if (!tag) return;
    tag.innerHTML =
      "<b>" + esc(RAIL.spec.title) + "</b> · 1280×800 @ " +
      Math.round(RAIL.scale * 100) + "% · keys: <b>o</b> card hold · " +
      "<b>k</b> stack hold · <b>r</b> reset · <b>m</b> measure" +
      (extra || "");
  },

  hold(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const other = document.getElementById(id === "hold-card" ? "hold-stack" : "hold-card");
    if (other) other.hidden = true;
    el.hidden = !el.hidden;
  },

  key(e) {
    const k = e.key.toLowerCase();
    if (k === "o") RAIL.hold("hold-card");
    else if (k === "k") RAIL.hold("hold-stack");
    else if (k === "escape" || k === "b") {
      document.getElementById("hold-card").hidden = true;
      document.getElementById("hold-stack").hidden = true;
    } else if (k === "r") RAIL.render();
    else if (k === "m") RAIL.measure();
  },

  /* The gate, drawn on the elements that failed. */
  measure() {
    for (const el of document.querySelectorAll("[data-bad]")) el.removeAttribute("data-bad");
    const out = RAIL_ASSERT();
    for (const bad of out.faults) bad.el.setAttribute("data-bad", bad.why);
    RAIL.tag(
      " — " + (out.PASS ? "<b>PASS</b>" : "<i>FAIL</i>") +
      " · rail " + out.railPx + "px, list " + out.listPx + "px (" + out.listShare + ")" +
      " · surfaces " + out.surfaces +
      " · scrollers " + out.scrollers + (out.overflowing ? " (" + out.overflowing + " overflowing)" : "") +
      " · min type " + out.minFontPx + "px · min hit " + out.minHitPx + "px"
    );
    console.log(out);
    return out;
  },
};
