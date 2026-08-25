/* ===========================================================================
   The mulligan round: the state, the pad, and the stage.
   ---------------------------------------------------------------------------
   Everything here is shared BECAUSE it must not vary. All five directions draw
   the same seven cards, the same pod and the same commander, so a difference on
   screen is a difference in design and not a difference in content -- the rule
   `../README.md` states for the board five and every round since.

   Loaded as a plain `<script src>`, which works from `file://`: a classic
   script and a stylesheet are not CORS-gated the way `fetch` and ES modules
   are. So there is no `inline.py` step in this folder and no build; open any
   `.html` directly.
   =========================================================================== */

/* ===========================================================================
   1. THE POSITION
   ---------------------------------------------------------------------------
   `src/automtg/engine/game.py:1145-1189` is what is actually being drawn. The
   first decision of every game is

       PendingDecision(kind=MULLIGAN, prompt="Mulligan? (0 taken)",
                       options=(Mulligan, Keep), context={"hand": [...]})

   -- two options, and a hand attached to the decision that the shipped dialog
   does not draw, because `PromptDialog.rowsFor` only draws a face when an
   option REFERS to an object and neither of these two does. So the client
   renders the one decision whose whole subject is a set of cards as a title and
   two labels, and the hand it is about is behind the backdrop.

   The hand below is a real Simic opener: three lands, one of them a tapland,
   Sol Ring, and a two-drop that ramps. It is keepable, deliberately -- a
   position whose answer is obvious is the one that shows whether the design is
   carrying the decision or just decorating it.
   =========================================================================== */

const HAND = [
  { id: "sol-ring", name: "Sol Ring", art: "sol-ring.jpg", frame: "C",
    cost: ["1"], cmc: 1, line: "Artifact", short: "Artifact", kind: "ramp",
    oracle: "{T}: Add {C}{C}.",
    note: "Turn one, off any land." },
  { id: "forest", name: "Forest", art: "forest.jpg", frame: "land",
    cost: [], cmc: 0, line: "Basic Land — Forest", short: "Land", kind: "land",
    produces: ["G"], oracle: "({T}: Add {G}.)",
    note: "Untapped. Green." },
  { id: "sakura-tribe-elder", name: "Sakura-Tribe Elder", art: "sakura-tribe-elder.jpg",
    frame: "G", cost: ["1", "G"], cmc: 2, line: "Creature — Snake Shaman",
    short: "Creature", pt: "1/1", kind: "ramp",
    oracle: "Sacrifice this creature: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
    note: "Blocks, then fetches a land." },
  { id: "island", name: "Island", art: "island.jpg", frame: "land",
    cost: [], cmc: 0, line: "Basic Land — Island", short: "Land", kind: "land",
    produces: ["U"], oracle: "({T}: Add {U}.)",
    note: "Untapped. Blue." },
  { id: "tatyova", name: "Tatyova, Benthic Druid", art: "tatyova-benthic-druid.jpg",
    frame: "gold", cost: ["3", "G", "U"], cmc: 5, line: "Legendary Creature — Merfolk Druid",
    short: "Creature", pt: "3/3", kind: "payoff",
    oracle: "Landfall — Whenever a land you control enters, you gain 1 life and draw a card.",
    note: "Every land after this draws you a card." },
  { id: "thornwood-falls", name: "Thornwood Falls", art: "thornwood-falls.jpg",
    frame: "land", cost: [], cmc: 0, line: "Land", short: "Land", kind: "land",
    produces: ["G", "U"], tapland: true,
    oracle: "This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {U}.",
    note: "Enters tapped. Both colours." },
  { id: "explosive-vegetation", name: "Explosive Vegetation", art: "explosive-vegetation.jpg",
    frame: "G", cost: ["3", "G"], cmc: 4, line: "Sorcery", short: "Sorcery", kind: "ramp",
    oracle: "Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
    note: "Two basics, onto the battlefield." },
];

const COMMANDER = {
  id: "aesi", name: "Aesi, Tyrant of Gyre Strait", art: "aesi-tyrant-of-gyre-strait.jpg",
  frame: "gold", cost: ["4", "G", "U"], cmc: 6, line: "Legendary Creature — Serpent",
  short: "Commander", pt: "5/5", colours: ["G", "U"],
  oracle: "Whenever a land you control enters, draw a card.\nWhenever Aesi deals combat damage to a player, you may put a land card from your hand onto the battlefield.",
};

/*
 * THE OTHER THREE SEATS, and the fact that they have a state at all.
 *
 * A Commander game deals four opening hands and asks four people the same
 * question. The engine runs them in seat order (`_opening_sequence` loops over
 * `state.players`), so by the time the question reaches you some seats have
 * answered and some have not -- and `serialize` carries `mulligans_taken` and
 * `has_kept_hand` per player, so the client already has every number below.
 * Nothing on the shipped screen shows any of it. 03 is the direction that asks
 * what the screen looks like if it does.
 */
const POD = [
  { seat: 1, name: "Vessa", commander: "Edgar Markov", art: "edgar-markov.jpg",
    colours: ["W", "B", "R"], state: "kept", cards: 7 },
  { seat: 2, name: "Ord", commander: "Krenko, Mob Boss", art: "krenko-mob-boss.jpg",
    colours: ["R"], state: "mulled", cards: 6, taken: 1 },
  { seat: 3, name: "Nim", commander: "Muldrotha, the Gravetide", art: "muldrotha-the-gravetide.jpg",
    colours: ["B", "G", "U"], state: "thinking", cards: 7 },
];

/** Library size after the opening seven, off a 99-card deck. */
const LIBRARY = 99 - 1 - HAND.length; // commander is in the command zone
const MAX_MULLIGANS = 6;              // engine/game.py:43

/* ===========================================================================
   2. DRAWING ONE
   =========================================================================== */

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/** A real Scryfall symbol from `../cards/symbols/`. */
const sym = (code) =>
  '<img class="sym" src="../cards/symbols/' + encodeURIComponent(code) + '.svg" alt="' + esc(code) + '">';

const cost = (list) => (list || []).map(sym).join("");

/**
 * The face.
 *
 * `opts.fs` sets `--face-fs`, which is the ONE thing that has to be passed
 * rather than derived: type does not scale with the card here, because the
 * floor is 16px and a card small enough to want 12px type is a card this round
 * is not allowed to draw. Any face narrower than about 150px therefore shows a
 * name that ellipsises, and that is the honest reading of the constraint rather
 * than a bug -- see the width table in `README.md`.
 */
function faceHTML(card, opts) {
  const o = opts || {};
  const cls = ["face", "face--" + card.frame].concat(o.cls || []).join(" ");
  const style =
    (o.w ? "--card-w:" + o.w + "px;" : "") + (o.fs ? "--face-fs:" + o.fs + "px;" : "");
  return (
    '<div class="' + cls + '" style="' + style + '" data-card="' + card.id + '">' +
    '<img class="face__art" src="../art/' + card.art + '" alt="">' +
    '<div class="face__head">' +
    '<span class="face__name">' + esc(card.name) + "</span>" +
    '<span class="face__cost">' + cost(card.cost) + "</span>" +
    "</div>" +
    '<div class="face__foot">' +
    '<span class="face__line">' + esc(card.short || card.line) + "</span>" +
    /* A land has no power and toughness, and what a land's foot is FOR is what
       it taps for -- the one fact the mulligan decision turns on. The shipped
       face has nowhere to put it, which is `../README.md`'s "lands are all one
       tan rectangle" a second time. */
    (card.produces ? '<span class="face__cost">' + cost(card.produces) + "</span>" : "") +
    (card.pt ? '<span class="face__pt">' + esc(card.pt) + "</span>" : "") +
    "</div>" +
    (o.extra || "") +
    "</div>"
  );
}

/**
 * Oracle text, with `{T}` and `{G}` drawn as the real symbols and reminder text
 * in italic. `SymbolText.tsx` is the client's version of this and does the same
 * two things.
 */
function symbolText(text) {
  return esc(text)
    .split("\n")
    .map((line) => {
      const body = line.replace(/\{([^}]+)\}/g, (_, code) => sym(code));
      /* A whole line in brackets is reminder text -- `({T}: Add {G}.)` is the
         entire rules box of a basic land, and drawing it in the same weight as
         a real ability makes a Forest look like it does something. */
      return /^\(.*\)$/.test(line) ? "<p><i>" + body + "</i></p>" : "<p>" + body + "</p>";
    })
    .join("");
}

/**
 * The full card: name, cost, art, type line, RULES, and power/toughness.
 *
 * Same parts and same order as the desktop preview's `variant="big"`
 * (`CardPreview.FullBody`), re-cut at the 16px floor -- see `.face--full` in
 * `_mull.css` for why that is a re-cut rather than a resize.
 */
function fullFaceHTML(card, opts) {
  const o = opts || {};
  const cls = ["face", "face--full", "face--" + card.frame].concat(o.cls || []).join(" ");
  const style =
    (o.w ? "--card-w:" + o.w + "px;" : "") + (o.fs ? "--face-fs:" + o.fs + "px;" : "");
  return (
    '<div class="' + cls + '" style="' + style + '" data-card="' + card.id + '" data-full>' +
    '<div class="face__head">' +
    '<span class="face__name">' + esc(card.name) + "</span>" +
    '<span class="face__cost">' + cost(card.cost) + "</span>" +
    "</div>" +
    '<div class="ffull__art"><img src="../art/' + card.art + '" alt=""></div>' +
    '<div class="ffull__type">' + esc(card.line) + "</div>" +
    '<div class="ffull__rules">' + symbolText(card.oracle || "") + "</div>" +
    /*
     * THE FOOT DOES NOT REPEAT THE TYPE, and the small face's does.
     *
     * On a small face the foot IS the type line -- it is the only place there
     * is for it. Here `.ffull__type` already printed the whole printed line
     * above the rules box, so putting `card.short` in the foot as well gave Sol
     * Ring a card that said "Artifact", then its rules, then "Artifact" again.
     * `cards.css:523-526` makes the same call on `.face--big`: its footer holds
     * the stats and the keyword chip and no type.
     *
     * The row is kept even when it has nothing in it, for that rule's stated
     * reason -- a land has no power, and a collapsing footer made every land
     * come out a row shorter than every creature.
     */
    '<div class="face__foot">' +
    (card.produces ? '<span class="face__cost">' + cost(card.produces) + "</span>" : "") +
    (card.pt ? '<span class="face__pt">' + esc(card.pt) + "</span>" : "") +
    "</div>" +
    (o.extra || "") +
    "</div>"
  );
}

/* ===========================================================================
   3. THE READ
   ---------------------------------------------------------------------------
   Derived, never written down twice. Every number 02 prints comes out of here,
   so a change to `HAND` cannot leave a stat panel quietly lying -- which is the
   failure mode `../handheld-board/README.md` built its `seatsAgree` gate for.
   =========================================================================== */

const READ = (() => {
  const lands = HAND.filter((c) => c.kind === "land");
  const spells = HAND.filter((c) => c.kind !== "land");
  const sources = {};
  for (const l of lands) for (const p of l.produces || []) sources[p] = (sources[p] || 0) + 1;
  const curve = {};
  for (const s of spells) curve[s.cmc] = (curve[s.cmc] || 0) + 1;
  return {
    lands: lands.length,
    spells: spells.length,
    taplands: lands.filter((l) => l.tapland).length,
    sources,
    curve,
    /** Cheapest thing you can actually cast, and on which turn. */
    firstPlay: spells.slice().sort((a, b) => a.cmc - b.cmc)[0],
    /** Every colour the commander needs, and whether the hand has it. */
    identity: COMMANDER.colours.map((c) => ({ colour: c, have: (sources[c] || 0) > 0 })),
  };
})();

/* ===========================================================================
   4. THE PAD
   ---------------------------------------------------------------------------
   `../door/_door.js:143-403`, carried across unchanged in behaviour. It is the
   same input contract -- a Steam Deck reporting itself as a Standard Gamepad,
   sticks standing in for the d-pad with hysteresis, an analog repeat rate, and
   a COUNTED rather than latched keyboard fallback so a tap faster than a frame
   is still a tap. That file carries the full argument for each of those; this
   one carries only what it takes to read the code.

       0 A   1 B   2 X   3 Y   4 L1  5 R1  6 L2  7 R2
       8 View  9 Menu  10 L3  11 R3  12 Up  13 Down  14 Left  15 Right

   The four back grips are deliberately unused: Steam Input may have rebound
   them, so a design that needs them is a design that breaks on somebody's
   machine.

   Keyboard:  arrows / WASD move    Enter or J = A    Backspace / K / Esc = B
              U = X    I = Y    Q = L1    E = R1
   =========================================================================== */

const PAD = (() => {
  const BTN = {
    a: 0, b: 1, x: 2, y: 3, l1: 4, r1: 5, l2: 6, r2: 7,
    view: 8, menu: 9, l3: 10, r3: 11, up: 12, down: 13, left: 14, right: 15,
  };
  const KEYS = {
    ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
    w: "up", s: "down", a: "left", d: "right",
    Enter: "a", j: "a", Backspace: "b", k: "b", Escape: "b", u: "x", i: "y",
    q: "l1", e: "r1",
  };
  const FIRE = 0.55;     // a stick direction is meant once it crosses this
  const RELEASE = 0.35;  // ...and is not meant again until it drops below this
  const REPEAT_FIRST_SLOW = 360;
  const REPEAT_FIRST_FAST = 180;
  const REPEAT_SLOW = 155;
  const REPEAT_FAST = 46;
  const REPEAT_FLOOR = 38;
  const KEY_T = 0.5;     // a digital press means "one step" and skips the sweep
  const ACCEL_OVER = 7;
  const ACCEL_FLOOR = 0.72;

  let handlers = {};
  const prev = {};
  const held = {};
  const run = {};
  let latched = null;
  let connected = false;
  let raf = 0;
  const keyDown = new Set();
  /* COUNTED, NOT LATCHED. A poll cannot see a key tapped inside one frame, and
     a Set cannot tell one press from two. Every keydown increments; every frame
     fires exactly that many and resets. `../door/_door.js:207-238` is the bug
     report. */
  const keyTaps = Object.create(null);
  const listeners = new Set();
  const REPEATS = new Set(["up", "down", "left", "right"]);
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp01 = (n) => (n < 0 ? 0 : n > 1 ? 1 : n);

  const pads = () =>
    navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  const axis = (p, i) => (p.axes.length > i ? p.axes[i] : 0);

  function padDown(name) {
    const p = pads()[0];
    if (!p) return false;
    const i = BTN[name];
    if (i === undefined) return false;
    const b = p.buttons[i];
    if (b && (b.pressed || b.value > 0.5)) return true;
    return latched === name;
  }
  const down = (name) => keyDown.has(name) || padDown(name);

  /* Which sector the left stick is in, with hysteresis -- without it a stick
     held toward a corner chatters between two sectors. */
  function sector(p) {
    const x = axis(p, 0);
    const y = axis(p, 1);
    const m = Math.hypot(x, y);
    if (m < RELEASE) return null;
    if (latched && m < FIRE) return latched;
    if (m < FIRE) return null;
    return Math.abs(x) > Math.abs(y) ? (x < 0 ? "left" : "right") : (y < 0 ? "up" : "down");
  }
  /* Only a direction coming FROM the stick is analog. With a pad plugged in and
     the keyboard driving, reading the stick here would measure a stick at rest
     and hand every key press the slowest rate on the ramp. */
  function pushOf(name) {
    if (keyDown.has(name) || keyTaps[name]) return KEY_T;
    const p = pads()[0];
    if (!p || latched !== name) return KEY_T;
    const m = Math.hypot(axis(p, 0), axis(p, 1));
    if (m < RELEASE) return KEY_T;
    return clamp01((m - FIRE) / (1 - FIRE));
  }
  function repeatMs(name, first) {
    const t = pushOf(name);
    if (first) return lerp(REPEAT_FIRST_SLOW, REPEAT_FIRST_FAST, t);
    const accel = Math.max(ACCEL_FLOOR, 1 - ((run[name] || 0) / ACCEL_OVER) * (1 - ACCEL_FLOOR));
    return Math.max(REPEAT_FLOOR, lerp(REPEAT_SLOW, REPEAT_FAST, t) * accel);
  }
  function fire(name) {
    if (handlers[name]) handlers[name]();
    if (handlers.any) handlers.any(name);
  }

  function frame(now) {
    /* getGamepads() hands back a SNAPSHOT. Caching the Gamepad object gives you
       buttons frozen at the moment you cached it. */
    const live = pads();
    const isLive = live.length > 0;
    if (isLive !== connected) {
      connected = isLive;
      listeners.forEach((f) => f(connected));
    }
    latched = live[0] ? sector(live[0]) : null;
    if (!latched) for (const d of REPEATS) if (keyDown.has(d) || keyTaps[d]) latched = d;

    for (const name of Object.keys(BTN)) {
      const taps = keyTaps[name] || 0;
      const isDown = down(name);
      const was = prev[name];
      if (taps > 0) {
        for (let n = 0; n < taps; n += 1) fire(name);
        if (REPEATS.has(name)) { run[name] = 0; held[name] = now + repeatMs(name, true); }
      } else if (isDown && !was) {
        fire(name);
        if (REPEATS.has(name)) { run[name] = 0; held[name] = now + repeatMs(name, true); }
      } else if (isDown && was && REPEATS.has(name) && now >= held[name]) {
        fire(name);
        run[name] = (run[name] || 0) + 1;
        held[name] = now + repeatMs(name, false);
      } else if (!isDown) {
        delete held[name];
        delete run[name];
      }
      prev[name] = isDown || taps > 0;
    }
    for (const name of Object.keys(keyTaps)) delete keyTaps[name];
    raf = requestAnimationFrame(frame);
  }

  /* Rumble, for one thing only: a refusal. THE RULE IS THAT RUMBLE IS ALWAYS
     REDUNDANT WITH SOMETHING VISIBLE -- Firefox in the Deck's desktop mode has
     no `vibrationActuator`, so haptics can never be the only channel. */
  function rumble(ms, strong) {
    const p = pads()[0];
    const act = p && p.vibrationActuator;
    if (!act || !act.playEffect) return;
    try {
      act.playEffect("dual-rumble", {
        duration: ms || 90,
        strongMagnitude: strong || 0.4,
        weakMagnitude: (strong || 0.4) * 0.6,
      });
    } catch { /* a pad that does not do haptics is not an error */ }
  }

  return {
    BTN,
    rumble,
    start(h) {
      handlers = h || {};
      addEventListener("keydown", (ev) => {
        const name = KEYS[ev.key];
        if (!name) return;
        const t = ev.target;
        if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA") && ev.key !== "Escape") return;
        // Backspace on file:// is a history step you cannot get back from.
        ev.preventDefault();
        if (ev.repeat) return; // the OS autorepeat would race our own DAS/ARR
        keyDown.add(name);
        keyTaps[name] = (keyTaps[name] || 0) + 1;
      });
      addEventListener("keyup", (ev) => {
        const name = KEYS[ev.key];
        if (name) keyDown.delete(name);
      });
      raf = requestAnimationFrame(frame);
      return this;
    },
    onConnection(f) { listeners.add(f); f(connected); },
    connected() { return connected; },
  };
})();

/* ===========================================================================
   5. THE STAGE
   ---------------------------------------------------------------------------
   Fit, the cold caption, the footer tag, and the commitment overlay. Four
   things every file needs and none of them an argument any file is making.
   =========================================================================== */

const STAGE = {
  title: "",
  scale: 1,

  mount(title, html, handlers) {
    STAGE.title = title;
    document.body.innerHTML =
      '<div class="bezel"><div class="deck" data-testid="mulligan">' +
      html +
      '<div class="cold" id="cold"><span class="cold__dot"></span>' +
      "<span>Press any button, or use the arrow keys</span></div>" +
      '<div class="verdict" id="verdict"><div><div class="verdict__word" id="verdict-word"></div>' +
      '<div class="verdict__sub" id="verdict-sub"></div></div></div>' +
      '<div class="raise" id="raise"></div>' +
      '</div><div class="bezel__tag" id="tag"></div></div>';

    STAGE.fit();
    addEventListener("resize", STAGE.fit);
    const wrapped = Object.assign({}, handlers, {
      any: (name) => {
        STAGE.warm();
        if (handlers && handlers.any) handlers.any(name);
      },
    });
    PAD.start(wrapped);
    /* `onConnection` calls its listener immediately with the current state, so
       warming from it unconditionally would retire the caption on the frame it
       mounted -- the cold state would be in the markup, in the shots, and never
       once on screen. Only an actual connection warms. */
    PAD.onConnection((on) => { if (on) STAGE.warm(); });
    addEventListener("mousedown", () => STAGE.warm());
  },

  warm() {
    const el = document.getElementById("cold");
    if (el && !el.hidden) el.hidden = true;
  },

  fit() {
    const el = document.querySelector(".deck");
    if (!el) return;
    STAGE.scale = Math.max(
      0.3,
      Math.min(2, Math.min((innerWidth - 26) / 1280, (innerHeight - 40) / 800))
    );
    el.style.transform = "scale(" + STAGE.scale + ")";
    STAGE.tag();
  },

  tag(extra) {
    const el = document.getElementById("tag");
    if (!el) return;
    el.innerHTML =
      "<b>" + esc(STAGE.title) + "</b> · 1280×800 @ " +
      Math.round(STAGE.scale * 100) + "%" +
      (extra ? " · " + extra : "") +
      " · <b>MULL_ASSERT()</b> in the console";
  },

  /* A brief, visible commitment and nothing else -- `../menu/README.md`'s rule
     for every interactive mockup in this folder. */
  commit(word, sub, mull) {
    const box = document.getElementById("verdict");
    const w = document.getElementById("verdict-word");
    const s = document.getElementById("verdict-sub");
    if (!box || !w || !s) return;
    w.textContent = word;
    w.className = "verdict__word" + (mull ? " verdict__word--mull" : "");
    s.textContent = sub || "";
    box.setAttribute("data-on", "");
    clearTimeout(STAGE._t);
    STAGE._t = setTimeout(() => box.removeAttribute("data-on"), 1100);
  },

  /*
   * ONE CARD, UP, AT THE WIDTH `probe.mjs` SAYS IT TAKES.
   *
   * 296 is not a taste; it is the widest of the seven minimums the probe found,
   * and using the widest rather than each card's own is deliberate -- a reader
   * that resized per card would jump between Sol Ring and Tatyova every time
   * you walked the row, which is the same defect `CardPreview`'s fixed height
   * exists to stop on a desktop.
   */
  RAISE_W: 296,
  raised: null,

  raise(card) {
    const box = document.getElementById("raise");
    if (!box) return;
    STAGE.raised = card;
    /* The hint goes ABOVE the card, which is not where a hint usually goes. It
       is where the room is quietest: the foot of every one of these five is
       holding a commitment tier, so a chip under a 413px card lands on top of
       "Keep" -- and a hint drawn over the button it is not talking about is
       worse than no hint. */
    box.innerHTML =
      '<div class="raise__hint"><span class="glyph glyph--y">Y</span>Put it back</div>' +
      '<div class="raise__card">' + fullFaceHTML(card, { w: STAGE.RAISE_W, fs: 16 }) + "</div>";
    box.setAttribute("data-on", "");
  },

  drop() {
    const box = document.getElementById("raise");
    if (!box) return;
    STAGE.raised = null;
    box.removeAttribute("data-on");
  },

  /*
   * Up if it is down, down if it is up.
   *
   * BOUND TO Y IN ALL FOUR, and the button is chosen by the one file that
   * cannot have X. 05's second question needs a confirm alongside a toggle and
   * a re-mulligan, so its X is spoken for -- and four directions that raise a
   * card on X plus one that does it on Y is worse than five that agree, because
   * the whole point of putting five of these side by side is that a reviewer
   * carries one set of thumbs between them.
   */
  toggleRaise(card) {
    if (STAGE.raised) STAGE.drop();
    else STAGE.raise(card);
  },

  /** A refusal: the thing you pushed leans and comes back, and the pad buzzes. */
  refuse(el, dir) {
    if (!el) return;
    PAD.rumble(90, 0.4);
    const cls = dir < 0 ? "nudge--l" : "nudge--r";
    el.classList.remove(cls);
    void el.offsetWidth; // restart the animation
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), 220);
  },
};

/* ===========================================================================
   6. THE GATES
   ---------------------------------------------------------------------------
   Small, and the same three questions of every file, because the claims this
   round makes are claims about SIZE and the shipped dialog fails all three:
   `.prompt__hint` is 12.5px, `.opt__caption` is 11px, and neither the hand nor
   any card is on the screen at all while the question is up.

   `MULL_ASSERT()` in any file's console.
   =========================================================================== */

function MULL_ASSERT() {
  const fails = [];
  const deck = document.querySelector(".deck");
  if (!deck) return console.error("no deck");

  /* 1. THE TYPE FLOOR. Every rendered text node at or over 16px, measured
        through the deck's own scale rather than asserted from the stylesheet --
        a `calc()` off a card width is exactly the kind of thing that clears the
        floor in source and misses it on screen. */
  for (const el of deck.querySelectorAll("*")) {
    if (!el.firstChild || el.firstChild.nodeType !== 3) continue;
    if (!el.textContent.trim()) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs < 16) fails.push("type " + fs.toFixed(1) + "px: " + el.className + " — " + el.textContent.trim().slice(0, 40));
  }

  /* 2. THE TARGET FLOOR. Anything a press lands on is 44px in both axes. */
  for (const el of deck.querySelectorAll("[data-hit]")) {
    const r = el.getBoundingClientRect();
    const w = r.width / STAGE.scale;
    const h = r.height / STAGE.scale;
    if (w < 44 || h < 44) fails.push("target " + Math.round(w) + "×" + Math.round(h) + ": " + el.className);
  }

  /* 3. NOTHING LEAVES THE STAGE. `../door/assert.js`'s `rowFits`, generalised:
        the row's widest state is the one this file is currently in, so run it in
        each. A card that runs off must run off VISIBLY. */
  const box = deck.getBoundingClientRect();
  for (const el of deck.querySelectorAll(".face, .back, [data-hit]")) {
    const r = el.getBoundingClientRect();
    if (r.left < box.left - 1 || r.right > box.right + 1 || r.top < box.top - 1 || r.bottom > box.bottom + 1) {
      fails.push("overflows stage: " + el.className);
    }
  }

  if (fails.length === 0) console.log("%cMULL_ASSERT " + STAGE.title + ": pass", "color:#5ce08a");
  else {
    console.group("%cMULL_ASSERT " + STAGE.title + ": " + fails.length + " fail", "color:#ff5c5c");
    fails.forEach((f) => console.log(f));
    console.groupEnd();
  }
  return fails;
}
