/*
 * The content, the input layer and the row every door mockup shares.
 *
 * NOT LOADED BY THE MOCKUPS. Each .html must open standalone from file://, so
 * this file is inlined into each one rather than linked. Same contract as
 * `../handheld-board/_board.js` and the same tooling: `inline.py` splices it
 * between the BEGIN/END markers each file carries, so the master and the five
 * cannot drift by hand.
 *
 *     python inline.py          # re-inline the masters into all five
 *     python inline.py --check  # fail if any file is stale (CI-shaped)
 *
 * Five things live here:
 *
 *   1. CARDS   -- the three menu cards, their copy and their real destinations.
 *   2. PAD     -- the gamepad layer, lifted from `../handheld/_handheld.js`.
 *   3. SPRING  -- the closed-form damped oscillator the row is moved by.
 *   4. ROW     -- the arithmetic that turns one number into three transforms.
 *   5. DOOR    -- mount, render, select, press, fit; and the two seams
 *                 `measure.mjs` drives, `DOOR.select(i, true)` and
 *                 `DOOR.travelMs()`.
 *
 * A file supplies its own `face()` and its own `chrome()` and nothing else.
 */

/* ===========================================================================
   1. THE THREE CARDS
   ---------------------------------------------------------------------------
   WHY PLAY IS IN THE MIDDLE, because the brief has two constraints that only
   agree one way.

   It asks for "Play, Join, Decks" and it asks that "the middle card should be
   placed and selected by default". A menu whose default selection is not its
   default action is a menu that has picked the wrong default, so Play is the
   middle card and the list order is the one thing that gives.

   Which of the other two goes left is then a real choice and this is the
   argument for it. The shipped door already reads Play, then Join -- "Create a
   pod", OR, a code field -- with "Browse them" demoted to an 11px link in the
   footer. Keeping Join to Play's right preserves that adjacency and that
   reading order; Decks comes up out of the footer to the left, which is also
   where the least-committing thing on the screen belongs. Looking at your decks
   costs nothing and starts nothing.

   Flipping the row is one constant, `CARDS.reverse()`, and nothing else in the
   round depends on the order.
   ======================================================================== */

/*
 * THE COPY IS ONE LINE AND THE SAME SHAPE THREE TIMES.
 *
 * These were sentences -- "Six precons and anything you have imported. Read a
 * list before you sit down with it." -- written for a panel with room. Put on a
 * 200px card they came to six lines, ran out of the bottom of it, and
 * `cardSpill` failed the file seven times over.
 *
 * The right fix is not a smaller font or a taller card. A menu item explains
 * itself in a phrase or it is not a menu item, and three items that describe
 * themselves in three different shapes read as three unrelated things. So: one
 * clause each, a noun and a promise, no marketing.
 */
const CARDS = [
  {
    id: "decks",
    label: "Decks",
    verb: "Browse the catalogue",
    /* The real number `useDecks()` hands `HomeScreen` today, and the real split
       the catalogue draws. `/decks`. */
    line: "Six decks, and anything you import.",
    stat: "6 decks · 2 yours",
    glyph: "▤",
    testid: "browse-decks",
    to: "/decks",
    /* The colour identity the screen takes when this card is selected. 05 is
       the direction that spends it; the others carry it unused, so the tint is
       one direction's idea and not four files' worth of dead tokens. */
    hue: ["#3f9e93", "#2b5a86"],
    art: "chulane-teller-of-tales",
  },
  {
    id: "play",
    label: "Play",
    verb: "Create a pod",
    line: "Four seats. Deal a new table.",
    stat: "Four seats · one is yours",
    glyph: "◆",
    /* `HomeScreen.tsx:106`. One of the four test ids that has to survive the
       port, and it moves from a `.big` button onto this card. */
    testid: "create-pod",
    to: "/pods/:code",
    hue: ["#d8a63c", "#8a3a2e"],
    art: "edgar-markov",
  },
  {
    id: "join",
    label: "Join",
    verb: "Enter a pod code",
    line: "Take a chair somebody held open.",
    stat: "BRAMBLE-123456",
    glyph: "◎",
    testid: "join-pod",
    to: "/pods/:code",
    hue: ["#7d6bd8", "#2b5a86"],
    art: "aesi-tyrant-of-gyre-strait",
  },
];

/** The card the row opens on. Asserted rather than eyeballed -- see
    `defaultCentre` in `assert.js`. */
const DEFAULT_INDEX = 1;

const BRAND = "Commander Blitz";

/* The logo, byte-for-byte `frontend/src/components/lobby/Mark.tsx` -- a bolt on
   a card back, taking `currentColor` so a gold header tints it and the two can
   never disagree. Inlined rather than fetched because file:// has no network,
   which happens to be the same reason the component inlines it too. */
const MARK =
  '<svg class="brand__badge" viewBox="0 0 64 64" aria-hidden="true" focusable="false">' +
  '<rect width="64" height="64" rx="10" fill="var(--void-0)"/>' +
  '<rect x="5.8" y="5.8" width="52.4" height="52.4" rx="5" fill="none" stroke="currentColor" stroke-opacity="0.22" stroke-width="1.4"/>' +
  '<path d="M37.2 11.2 L20.4 34 H29.2 L26.8 52.8 L43.6 29.6 H34.8 Z" fill="currentColor"/>' +
  "</svg>";

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* The slug `../art/manifest.json` uses. Only 05 reads art, but the helper is
   shared so a second direction that wants a crop cannot invent a second naming
   rule. */
const ART = (slug) => "../art/" + slug + ".jpg";

/* ===========================================================================
   2. THE PAD
   ---------------------------------------------------------------------------
   Lifted from `../handheld/_handheld.js:282-594`, which is where the round that
   designed this input layer left it. Trimmed to what a menu uses -- the four
   directions, the four face buttons, rumble -- and otherwise unchanged, because
   a second implementation of a DAS/ARR ramp is a second set of ramp bugs.

   STEAM DECK -> STANDARD GAMEPAD. The Deck reports itself as a Standard
   Gamepad, so the W3C indices hold and are what this maps:

       0 A     1 B     2 X     3 Y
       4 L1    5 R1    6 L2    7 R2
       8 View  9 Menu  10 L3   11 R3
       12 Up   13 Down 14 Left 15 Right
       axes 0,1 left stick   axes 2,3 right stick

   The four back grips are DELIBERATELY UNUSED: Steam Input maps them to other
   buttons by default and a player may have rebound them, so a design that needs
   them is a design that breaks on somebody's machine.

   `navigator.getGamepads()` is [SecureContext] and file:// is a
   potentially-trustworthy origin, so the API is there -- but Chrome hides pads
   behind a user gesture, so it returns four nulls until the first button press.
   That is why every file opens on the cold state rather than pretending to be
   connected.

   KEYBOARD FALLBACK so these can be reviewed without a controller:

       arrows / AD     left and right      Enter or J    A
       Backspace / K   B                   U / I         X / Y
   ======================================================================== */

const PAD = (() => {
  const BTN = {
    a: 0, b: 1, x: 2, y: 3, l1: 4, r1: 5, l2: 6, r2: 7,
    view: 8, menu: 9, l3: 10, r3: 11, up: 12, down: 13, left: 14, right: 15,
  };
  const KEYS = {
    ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
    w: "up", s: "down", a: "left", d: "right",
    Enter: "a", j: "a", Backspace: "b", k: "b", Escape: "b", u: "x", i: "y",
    q: "l1", e: "r1", Tab: "view", "\\": "menu",
  };
  const DEAD = 0.3;      // Deck sticks rest noisily; 0.30 is past the noise
  const FIRE = 0.55;     // a direction is meant once the stick crosses this
  const RELEASE = 0.35;  // ...and is not meant again until it drops below this

  /* THE THUMB IS AN ANALOG INPUT AND A FIXED REPEAT RATE THROWS THAT AWAY.
     `push` is how far past FIRE the stick is, rescaled to 0..1, and it picks
     the interval; `run` eases it down a further 28% over the first seven
     repeats. A d-pad and the keyboard have no analog to read and stand at
     KEY_T -- the middle of the range, because a digital press means "one step"
     and should not inherit the sweep.

     REPEAT_FIRST_FAST is the number `travelMs` is gated against: it is when a
     held direction fires for the SECOND time, and a row that has not arrived by
     then is a row you are steering blind. */
  const REPEAT_FIRST_SLOW = 360;
  const REPEAT_FIRST_FAST = 180;
  const REPEAT_SLOW = 155;
  const REPEAT_FAST = 46;
  const REPEAT_FLOOR = 38;
  const KEY_T = 0.5;
  const ACCEL_OVER = 7;
  const ACCEL_FLOOR = 0.72;

  let handlers = {};
  let prev = {};
  let held = {};
  let run = {};
  let latched = null;
  let connected = false;
  let raf = 0;
  const keyDown = new Set();
  /*
   * THE KEYBOARD IS COUNTED, NOT LATCHED, AND THE DIFFERENCE IS TWO BUGS.
   *
   * A poll cannot see a key tapped faster than a frame: keydown and keyup both
   * land inside one 16ms gap and `keyDown` is empty again by the time anything
   * looks. A pad cannot do this to you because it IS the poll, which is why
   * this only ever bites the fallback -- and why it would have been blamed on
   * the key map rather than found.
   *
   * The first fix was a latch: hold the name until exactly one frame has
   * observed it. That catches the fast tap and loses the fast SECOND tap, two
   * different ways. A Set cannot tell one press from two, so two taps inside a
   * frame fire once. And worse, a tap arriving after a frame has fired but
   * before the release is observed leaves the poll looking at an unbroken hold:
   * `isDown` is true, `prev` is true, no edge, and the press is gone. The row
   * moved one place when you asked for two, on two of five files, depending on
   * how long that file's frame took.
   *
   * A COUNTER HAS NEITHER PROBLEM. Every keydown increments; every frame fires
   * exactly that many and resets. A tap is a tap whether or not a frame saw the
   * key down, and two taps are two. The hold-and-repeat path below reads the
   * physical state instead, which is the thing it was always actually about.
   *
   * Found by a driver that had been RELYING on the drop -- it pressed left
   * twice, asserted the row had moved one place, and passed.
   */
  const keyTaps = Object.create(null);
  const listeners = new Set();

  const REPEATS = new Set(["up", "down", "left", "right"]);
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp01 = (n) => (n < 0 ? 0 : n > 1 ? 1 : n);

  function pads() {
    return navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  }
  function axis(p, i) {
    return p.axes.length > i ? p.axes[i] : 0;
  }
  /** Physically held right now. Taps are counted separately -- see `keyTaps`. */
  function down(name) {
    return keyDown.has(name) || padDown(name);
  }
  function padDown(name) {
    const p = pads()[0];
    if (!p) return false;
    const i = BTN[name];
    if (i === undefined) return false;
    const b = p.buttons[i];
    if (b && (b.pressed || b.value > 0.5)) return true;
    // Sticks stand in for the d-pad, so a direction is either. The latch is
    // what makes that bearable: a stick held toward a corner sits near the
    // boundary of two sectors and, without hysteresis, chatters between them.
    return latched === name;
  }
  /** Which of the four sectors the left stick is in, with hysteresis: a new
      direction only latches past FIRE, and nothing new latches until the stick
      falls back inside RELEASE. */
  function sector(p) {
    const x = axis(p, 0);
    const y = axis(p, 1);
    const m = Math.hypot(x, y);
    if (m < RELEASE) return null;
    if (latched && m < FIRE) return latched;
    if (m < FIRE) return null;
    return Math.abs(x) > Math.abs(y) ? (x < 0 ? "left" : "right") : (y < 0 ? "up" : "down");
  }
  /** ONLY A DIRECTION COMING FROM THE STICK IS ANALOG, and it takes three
      checks to be sure of that rather than one. `latched` is the direction
      whatever its source, because the keyboard fallback writes into it too --
      so with a pad plugged in and the keyboard driving, reading the stick's
      magnitude here would measure a stick at rest and hand every key press the
      slowest rate on the ramp. */
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

  function frame(now) {
    // The array getGamepads() hands back is a SNAPSHOT. Caching the Gamepad
    // object gives you buttons frozen at the moment you cached it, which is the
    // single most common way to write a gamepad loop that half-works.
    const live = pads();
    const isLive = live.length > 0;
    if (isLive !== connected) {
      connected = isLive;
      listeners.forEach((f) => f(connected));
    }
    latched = live[0] ? sector(live[0]) : null;
    if (!latched) {
      for (const d of REPEATS) if (keyDown.has(d) || keyTaps[d]) latched = d;
    }
    for (const name of Object.keys(BTN)) {
      const taps = keyTaps[name] || 0;
      const isDown = down(name);
      const was = prev[name];
      if (taps > 0) {
        /* Discrete presses, however many arrived and whatever the poll can see
           of the key now. This branch is the keyboard's and is not an edge. */
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
      /* A tapped key counts as down for one frame so a hold that begins with
         this frame does not fire twice. */
      prev[name] = isDown || taps > 0;
    }
    // Every tap this frame has now been fired.
    for (const name of Object.keys(keyTaps)) delete keyTaps[name];
    raf = requestAnimationFrame(frame);
  }

  function fire(name) {
    const h = handlers[name];
    if (h) h();
    if (handlers.any) handlers.any(name);
  }

  /* Rumble, for exactly one thing here: walking into the end of the row. THE
     RULE IS THAT RUMBLE IS ALWAYS REDUNDANT WITH SOMETHING VISIBLE -- Firefox
     in the Deck's desktop mode has no `vibrationActuator`, so haptics can never
     be the only channel carrying a fact. The visible half is `DOOR.nudge`. */
  function rumble(ms = 90, strong = 0.4) {
    const p = pads()[0];
    const act = p && p.vibrationActuator;
    if (!act || !act.playEffect) return;
    try {
      act.playEffect("dual-rumble", { duration: ms, strongMagnitude: strong, weakMagnitude: strong * 0.6 });
    } catch { /* a pad that does not do haptics is not an error */ }
  }

  return {
    BTN,
    rumble,
    REPEAT_FIRST_FAST,
    REPEAT_FLOOR,
    start(h) {
      handlers = h || {};
      addEventListener("keydown", (ev) => {
        const name = KEYS[ev.key];
        if (!name) return;
        /*
         * A code field is a text field and the keyboard fallback must not eat
         * its letters. `d` is "right" on the pad map and also the fourth letter
         * of BRAMBLE, so without this the fallback silently steers the menu
         * while somebody types a pod code.
         *
         * ESCAPE IS THE EXCEPTION, because Escape is never text. Swallowing it
         * here means a player who has opened the join dialog, put their cursor
         * in the field and changed their mind has no way out except the mouse:
         * B is Escape, Escape is going to the input, and the input does nothing
         * with it. A driver caught it -- the hold opened, would not close, and
         * every key after that landed on an invisible field.
         */
        const t = ev.target;
        const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA");
        if (typing && ev.key !== "Escape") return;
        // Tab and Backspace both navigate the page otherwise, and Backspace on
        // file:// is a history step you cannot get back from.
        ev.preventDefault();
        if (ev.repeat) return;  // the OS autorepeat would race our own DAS/ARR
        keyDown.add(name);
        keyTaps[name] = (keyTaps[name] || 0) + 1;
      });
      addEventListener("keyup", (ev) => {
        const name = KEYS[ev.key];
        if (name) keyDown.delete(name);
      });
      addEventListener("gamepadconnected", () => {});
      raf = requestAnimationFrame(frame);
      return this;
    },
    stop() { cancelAnimationFrame(raf); },
    onConnection(f) { listeners.add(f); f(connected); },
    connected() { return connected; },
  };
})();

/* ===========================================================================
   3. THE SPRING
   ---------------------------------------------------------------------------
   TUNED IN TIME, NOT IN STIFFNESS, because time is the thing being judged.
   `frontend/src/input/ring.ts:18-35` makes this argument for the focus ring and
   it is the same argument here: `w` is the natural frequency in rad/s and `z`
   the damping ratio, so the two numbers a review cares about fall straight out
   of them.

       settling time ~= 4 / (z*w)      overshoot = e^(-pi*z / sqrt(1 - z^2))

   `SLIDE` is w 22, z 0.82: the card covers 98% of the gap in 179ms -- eleven
   frames at 60Hz -- overshoots by 1.1%, which is 2.7px on a 248px hop, and is
   permanently inside 2px at 294ms. What you perceive is a 180ms move; the rest
   is a drift narrower than a hairline.

   ---------------------------------------------------------------------------
   IT WAS w 38, z 0.62, AND THE GATE THAT LET THAT THROUGH WAS THE PROBLEM.

   Those numbers are a 169ms settle and 8.4% of overshoot, which on paper reads
   fine -- 169 is comfortably inside the 180ms budget the gate asked for. What
   they actually did was cross the entire row IN FOUR FRAMES and then ring for
   fourteen more, 21px each way, decaying. Sampled per frame the sequence is

       0.85  0.55  0.27  0.07  -0.04  -0.08  -0.08  -0.05  -0.03  -0.01 ...

   a cut, followed by a wobble. That is what "jerky" was, and no still could
   have shown it.

   THE GATE REWARDED THE FAILURE IT EXISTED TO PREVENT. `travelMs <= 180` is
   one-sided, and the cheapest way to satisfy a ceiling on a duration is to make
   the animation violent. An animation needs a FLOOR as much as a ceiling, so
   `assert.js` asks for both now -- at least 100ms of traverse or it is not a
   move, no more than 320ms of settle or it is a wait -- and caps the overshoot,
   because a big one after a fast traverse is the ring that read as jitter.

   The 1.1% is still deliberate and is still the difference between this and the
   focus ring's 2%: a ring is an outline and should read as ARRIVING, a card has
   weight and should read as LANDING. 2.7px is a card settling onto a table.
   21px was a card being thrown at one.

   Closed form rather than `v += (k*dx - d*v) * dt`, and `ring.ts:71` records
   why: the naive integrator overshoots 1.6px at 60fps and 4.5px at 144fps and
   goes unstable at a large `dt`, so a mockup reviewed on a 144Hz monitor would
   not be the mockup that was tuned. This is exact at any `dt`.
   ======================================================================== */

const SLIDE = { w: 22, z: 0.82 };

function springStep(x, v, target, w, z, dt) {
  const A = x - target;
  const wd = w * Math.sqrt(Math.max(1e-6, 1 - z * z));
  const B = (v + z * w * A) / wd;
  const e = Math.exp(-z * w * dt);
  const c = Math.cos(wd * dt);
  const s = Math.sin(wd * dt);
  const pos = e * (A * c + B * s);
  return {
    x: target + pos,
    v: e * (-z * w * (A * c + B * s) + wd * (B * c - A * s)),
  };
}

/* ===========================================================================
   4. THE ROW
   ---------------------------------------------------------------------------
   One continuous number in, three transforms out. See the long note over
   `.row` in `_door.css` for what each term is and where it comes from.

   THE BUNCH TERM IS THE BRIEF'S STACKING. `PUSH` alone spreads the row evenly,
   which is a fan; subtracting `BUNCH` once a card is more than one place from
   the selection pulls the far card back OVER its neighbour, so selecting an end
   leaves one clear card and a pair.

   THE LABEL SIDE FLIPS, and it was `labelClear` that found it. With the row
   bunched, the nearer of the two stacked cards is drawn ON TOP of the further
   one -- `z` falls with distance -- so the further card loses the half of
   itself that faces the selection. A centred label is therefore half-covered in
   exactly the state the brief asks for. The fix is the thing a fanned hand does
   anyway: each card's label hugs the edge that faces AWAY from the selection,
   so what you read is the outer sliver, which is the only part guaranteed to be
   uncovered. `data-side` carries it and `_door.css` aligns off it.

   A direction may override any of these five and must say which and why in its
   own header; `assert.js` prints the tune, so the README table is measured
   rather than claimed. 02 is the only one that does.
   ======================================================================== */

const TUNE = {
  STEP: 248,    // px between neighbouring cards at rest
  PUSH: 36,     // px a neighbour slides away from the selected card
  /*
   * THE STACK DEPTH IS NOT A TASTE, IT IS BOUNDED BY THE LONGEST LABEL.
   *
   * Of two cards on the same side of the selection the nearer is drawn on top,
   * so what is left of the further one is a strip `STEP - BUNCH` wide. Its
   * label has to fit in that strip or it cannot be read at any alignment.
   *
   * 140 was the first number here and `labelClear` came back at 15% covered:
   * 248 - 140 leaves a 108px sliver, the widest label is 102px, and 16px of
   * inset plus 2 of border does not fit in the six that were left. 112 leaves
   * 136 and clears it with room for a tilt. `assert.js` reports both numbers so
   * a direction that lengthens a label finds out here rather than on a Deck.
   */
  BUNCH: 112,   // px the FAR card is pulled back over its neighbour
  ARC: 4.5,     // degrees of tilt per place from the selection
  LIFT: 26,     // px the selected card rises
  DROOP: 14,    // px an unselected card sits below it
  RAISE: 0.1,   // fraction the selected card grows
  TILT: 1.6,    // places at which the tilt stops growing
};

/*
 * WHERE THE NAME SLIDES TO ITS OUTER EDGE, AND WHY IT IS A RAMP.
 *
 * The first version of this was a switch: under half a place from the
 * selection the label centred, past that it jumped to the edge that was still
 * showing. Every measurement in the round passed, because every measurement in
 * the round looks at a SETTLED row -- and settled, both poses are correct.
 *
 * In motion it is a teleport. A driver sampling every frame across all six
 * moves measured the name jumping 20% of its own card's width in a single
 * frame on 01, 03 and 05, 35% on 02 and 50% on 04, four times per move. The
 * cards were sliding perfectly smoothly and the writing on them was snapping
 * about, which is exactly what "jerky" describes and what no still could show.
 *
 * So the label travels. It starts moving at 0.45 places out -- before anything
 * can cover it -- and is at the edge by 1.05, which is the first moment
 * anything does. Between those it is somewhere in between, every frame.
 */
const LEAN_IN = 0.45;
const LEAN_OUT = 1.05;

/** How close a name may come to the edge of its own card. */
const LAB_INSET = 16;

function poseOf(i, s, tune) {
  const t = tune;
  const d = i - s;
  const a = Math.abs(d);
  const sign = d < 0 ? -1 : d > 0 ? 1 : 0;
  const near = Math.min(a, 1);
  const far = Math.max(0, a - 1);
  const tilt = Math.max(-t.TILT, Math.min(t.TILT, d));
  return {
    /* Centred on index 1, so the middle card sits at x = 0 when it is the one
       selected and the arithmetic is written about a row rather than an edge. */
    x: (i - 1) * t.STEP + sign * (t.PUSH * near - t.BUNCH * far),
    y: t.DROOP * Math.min(a, t.TILT) - t.LIFT * Math.max(0, 1 - a),
    rot: tilt * t.ARC,
    scale: 1 + t.RAISE * Math.max(0, 1 - a),
    z: 100 - Math.round(a * 10),
    /* Which way the label leans, and it is a RAMP rather than a side.
       See `LEAN_IN` for why this stopped being `a < 0.5 ? "c" : ...`. */
    side: a < 0.5 ? "c" : d < 0 ? "l" : "r",
    lean: (d < 0 ? -1 : 1) * Math.max(0, Math.min(1, (a - LEAN_IN) / (LEAN_OUT - LEAN_IN))),
    /*
     * HOW MUCH OF THIS CARD IS WORTH PRINTING ON, and it is the round's second
     * finding rather than a nicety.
     *
     * One place from the selection a card is on top of everything and can carry
     * whatever it likes. TWO places and it is under its own neighbour, so
     * everything except the outer sliver is gone -- and a sentence that runs
     * into a covering card does not read as hidden, it reads as TRUNCATED,
     * which is worse, because a truncated line looks like a bug in the copy.
     *
     * `assert.js` found this on 04, whose whole idea is a live state line on the
     * plate: the name had already been moved to the outer edge and passed
     * `labelClear` while "6 in the catalogue - 2 yours" was being cut in half
     * beside it. So THE STACK COSTS A CARD EVERYTHING EXCEPT ITS NAME, and
     * anything a direction prints below the name fades out as the card goes
     * under. Elements opt in with `.ink`; `_door.css` does the rest.
     */
    ink: 1 - Math.max(0, Math.min(1, (a - 1) / 0.6)),
    /* Whether anything is actually drawn ON TOP of this card, which is a
       different question from which side of the selection it is on. At exactly
       one place away a card is the near half of a pile and covers rather than
       is covered, so it may keep its own grammar; past that it is underneath.
       `data-side` moves the NAME early because a name repositioning mid-slide is
       invisible at 169ms; this moves everything else, and only when it must. */
    covered: a > 1.45,
  };
}

/* ===========================================================================
   5. DOOR
   ======================================================================== */

const DOOR = {
  spec: null,
  /** Where the selection IS, continuously. The spring moves it; everything on
      screen is derived from it. */
  s: DEFAULT_INDEX,
  v: 0,
  /** Where the selection is GOING. An integer, always. */
  target: DEFAULT_INDEX,
  raf: 0,
  last: 0,
  scale: 1,

  mount(spec) {
    DOOR.spec = Object.assign(
      {
        title: "door",
        note: "",
        face: () => "",
        chrome: () => "",
        rowTop: 232,
        tune: TUNE,
        onSelect: null,
        onPress: null,
        /* Which test id goes on the CARD. Almost always the card's own, but a
           direction that puts a real control inside a card has to move the id
           onto that control -- see 04. `assert.js` checks the four ids exist
           somewhere, not that they are on a card. */
        testid: null,
        /* 0..1, how far this card's name has turned toward its spine, as a
           function of `|i - s|`. Only 02 supplies one. It is a fraction rather
           than a class for the reason `LEAN_IN` gives: a name that snapped
           through ninety degrees mid-slide measured a 35% jump in a frame. */
        spin: null,
      },
      spec
    );
    DOOR.s = DEFAULT_INDEX;
    DOOR.target = DEFAULT_INDEX;
    DOOR.v = 0;
    DOOR.render();
    addEventListener("resize", () => {
      DOOR.fit();
      /* The readings above are taken through the deck's scale, so a resized
         window invalidates every one of them. */
      DOOR.measureLabels();
      DOOR.prev = [];
      DOOR.paint();
    });
    PAD.start({
      left: () => DOOR.step(-1),
      right: () => DOOR.step(1),
      a: () => DOOR.press(),
      b: () => DOOR.back(),
      any: () => DOOR.warm(),
    });
    /* `onConnection` calls its listener IMMEDIATELY with the current state, so
       `() => DOOR.warm()` retired the caption on the frame it mounted -- the
       cold state was in the markup, in the shots, and never once on screen.
       Only an actual connection warms. */
    PAD.onConnection((on) => { if (on) DOOR.warm(); });
    /* Every label offset is derived from a measured width, so a reading taken
       against the fallback face is wrong by however much the real one differs.
       Cheap, once, and it repaints from the numbers it just took. */
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => {
        DOOR.measureLabels();
        DOOR.prev = [];
        DOOR.paint();
      });
    }
  },

  /* The cold state, retired. Retired by ANY input -- a pad button, a key, a
     click -- and not only by a gamepad connecting, because what the caption
     claims is "nothing has spoken to this yet" and a mouse speaks. */
  warm() {
    const el = document.getElementById("cold");
    if (el && !el.hidden) el.hidden = true;
  },

  render() {
    const spec = DOOR.spec;
    document.getElementById("root").innerHTML =
      '<div class="bezel">' +
      '<div class="deck" data-testid="home">' +
      spec.chrome(spec) +
      '<div class="row" id="row" style="top:' + spec.rowTop + 'px">' +
      CARDS.map(
        (c, i) =>
          '<div class="slot" id="slot-' + c.id + '" data-slot="' + i + '">' +
          '<button class="mcard" type="button" data-testid="' +
          (spec.testid ? spec.testid(c) : c.testid) + '" ' +
          'data-card="' + c.id + '" aria-label="' + esc(c.label + ". " + c.verb) + '">' +
          spec.face(c, i) +
          '<span class="sheen"></span>' +
          "</button>" +
          "</div>"
      ).join("") +
      "</div>" +
      '<div class="cold" id="cold">' +
      '<span class="cold__dot"></span>' +
      "<span>Press any button, or use the arrow keys</span>" +
      "</div>" +
      '<div class="hints">' +
      '<span class="hint"><span class="glyph">A</span>Select</span>' +
      '<span class="hint"><span class="glyph glyph--key">&#8592;</span>' +
      '<span class="glyph glyph--key">&#8594;</span>Move</span>' +
      "</div>" +
      "</div>" +
      '<div class="bezel__tag" id="tag"></div>' +
      "</div>";

    DOOR.wire();
    if (spec.wire) spec.wire(document.querySelector(".deck"));
    DOOR.measureLabels();
    /* `measureLabels` clears `--lab`, so anything the cache thinks it wrote is
       no longer on the element. */
    DOOR.prev = [];
    DOOR.paint();
    DOOR.tag();
    DOOR.fit();
  },

  wire() {
    for (const el of document.querySelectorAll(".slot")) {
      const i = +el.dataset.slot;
      /*
       * HOVER SELECTS, AND THE FEEDBACK LOOP IS CUT ON THE OTHER SIDE.
       *
       * `board.css:1816-1826` cuts it by keeping the hit box still while only
       * the picture moves, because in a hand the card is lifted BY the hover.
       * That is not available here: sliding is the design, so the box has to
       * move with it.
       *
       * Two rules make it safe instead. A hover is ignored while the row is
       * still moving, so a card arriving under a stationary pointer cannot
       * re-trigger anything; and a hover never DE-selects, so the selection
       * only ever moves toward the pointer and has nowhere to oscillate to.
       */
      el.addEventListener("mouseenter", () => {
        DOOR.warm();
        if (DOOR.hold || DOOR.moving()) return;
        DOOR.select(i);
      });
      el.querySelector(".mcard").addEventListener("click", () => {
        DOOR.warm();
        if (DOOR.hold) return;
        if (i !== DOOR.target) { DOOR.select(i); return; }
        DOOR.press();
      });
    }
  },

  /**
   * Where each card's name sits when nothing has moved it, and how big it is.
   *
   * Measured rather than declared, once, BEFORE the first paint -- which is the
   * only moment no pose has been applied and a label is therefore at its
   * natural place. That one reading is what lets the travel below be a single
   * formula for every direction: 01, 02, 03 and 05 centre their name and 04
   * puts it at the plate's top left, and neither has to say so.
   *
   * Re-run when the webfont lands. A label measured against the fallback face
   * is a few pixels out, and every offset here is derived from its width.
   */
  labels: [],
  measureLabels() {
    /*
     * PUT EVERY LABEL BACK BEFORE READING IT.
     *
     * "Before the first paint" was true of the call at mount and false of the
     * two that matter more -- the one after the webfont lands and the one after
     * a resize -- both of which run when `--lab` has already moved every label
     * to its edge. Those re-measured the MOVED position as the natural one, so
     * the travel compounded on itself and the second reading was junk: a name
     * whose natural centre is the middle of the card came back at 134 of 200.
     *
     * Clearing first makes the reading mean the same thing whenever it is
     * taken, which is what a measurement has to do to be worth caching.
     */
    for (const c of CARDS) {
      const lab = document.querySelector("#slot-" + c.id + " .mcard__label");
      if (lab) lab.style.removeProperty("--lab");
    }
    DOOR.labels = CARDS.map((c) => {
      const slot = document.getElementById("slot-" + c.id);
      const card = slot && slot.querySelector(".mcard");
      const lab = slot && slot.querySelector(".mcard__label");
      if (!card || !lab) return null;
      const cb = card.getBoundingClientRect();
      const lb = lab.getBoundingClientRect();
      /*
       * DIVIDED BY THE CARD'S OWN SCALE, and getting this wrong is instructive.
       *
       * The deck is a fixed 1280x800 scaled to whatever window is open, so a
       * rect is in SCREEN pixels and the offsets computed from it are written
       * back as CSS pixels. Measured at 95% and written at 100%, every label
       * landed 5% short of the edge it was travelling to -- which `labelClear`
       * caught at 4% covered on three files and 60% on the one whose title
       * starts at an edge rather than at the middle.
       *
       * The factor is read off the card itself rather than from `DOOR.scale`,
       * because it is the product of every transform above this element and
       * `fit()` has not necessarily run yet when this is called.
       */
      const k = cb.width / (card.offsetWidth || 1) || 1;
      return {
        cardW: cb.width / k,
        cardH: cb.height / k,
        w: lb.width / k,
        h: lb.height / k,
        /* Both relative to the card, so the slot's own position cancels. */
        cx: ((lb.left + lb.right) / 2 - cb.left) / k,
        cy: ((lb.top + lb.bottom) / 2 - cb.top) / k,
      };
    });
  },

  moving() {
    return Math.abs(DOOR.s - DOOR.target) > 0.004 || Math.abs(DOOR.v) > 0.02;
  },

  /*
   * ===========================================================================
   * HOLDS -- anything that opens over the row.
   * ===========================================================================
   *
   * `../handheld-board/` calls these holds and this is the same idea at menu
   * scale: one thing at a time is on top, and while it is, IT OWNS THE INPUT.
   * That is not politeness, it is the focus-trap rule `input/stops.ts` spends
   * its longest comment on -- with an overlay open, every stop behind it is
   * still in the document, so a resolver that does not exclude them puts the
   * ring on a control the player cannot see.
   *
   * A hold is `{ el, confirm }`. While one is set the row ignores directions and
   * A goes to the hold instead; B closes it. Nothing else in the round needs
   * one, but a direction that puts a control behind a card rather than on it
   * needs somewhere to put the control, and this is it.
   */
  hold: null,

  openHold(el, confirm) {
    DOOR.hold = { el, confirm };
    el.hidden = false;
    const first = el.querySelector("input, button");
    if (first) first.focus();
  },

  /*
   * CLOSING GIVES THE ROW ITS FOCUS BACK, and that is not a nicety.
   *
   * `PAD.start` ignores a keydown whose target is an input, because the
   * fallback maps `a`, `d`, `s` and `w` to directions and BRAMBLE has a `d` in
   * it. Hide a hold while its field still holds focus and every key after that
   * lands on an invisible input: the row stops responding to the keyboard
   * entirely and there is nothing on screen to say why.
   *
   * Found by a driver that opened the hold, closed it, and could not open it
   * again. Restoring focus to the card that opened it is also just what a dialog
   * owes the thing behind it -- `input/cursor.ts` puts the ring back for the
   * same reason.
   */
  closeHold() {
    if (!DOOR.hold) return;
    DOOR.hold.el.hidden = true;
    DOOR.hold = null;
    const card = document.querySelector('[data-slot="' + DOOR.target + '"] .mcard');
    if (card) card.focus({ preventScroll: true });
  },

  /** B, and Escape, which the key map sends here as the same intent. */
  back() {
    DOOR.warm();
    if (DOOR.hold) DOOR.closeHold();
  },

  /** Move one place, or refuse at the end of the row. */
  step(delta) {
    DOOR.warm();
    /* The row is not what the player is looking at. */
    if (DOOR.hold) return;
    const next = DOOR.target + delta;
    if (next < 0 || next >= CARDS.length) {
      DOOR.nudge(delta);
      PAD.rumble(55, 0.22);
      return;
    }
    DOOR.select(next);
  },

  /*
   * THE WALL, DRAWN. `ring.ts:549` gives the focus ring a 340px/s impulse into
   * a wall rather than doing nothing, and the reason generalises: a control
   * that ignores a press is indistinguishable from a control that is broken.
   * Here the impulse goes into the spring the row already has, so the row leans
   * into the end and comes back -- no second animation, no state.
   *
   * It is also the visible half of the rumble. Haptics may never be the only
   * channel carrying a fact, because the Deck's desktop-mode Firefox has no
   * `vibrationActuator` at all.
   */
  nudge(delta) {
    DOOR.v += delta * 2.4;
    DOOR.wake();
  },

  /**
   * Point the row at a card.
   *
   * `instant` snaps the spring and repaints in the same tick, which is the seam
   * `measure.mjs` drives: a gate that had to wait out an animation would be
   * timing the spring instead of measuring the layout, and a screenshot taken
   * mid-flight is a screenshot of no state at all.
   */
  select(i, instant) {
    const next = Math.max(0, Math.min(CARDS.length - 1, i | 0));
    DOOR.target = next;
    if (instant) {
      DOOR.s = next;
      DOOR.v = 0;
      cancelAnimationFrame(DOOR.raf);
      DOOR.raf = 0;
      DOOR.paint();
    } else {
      DOOR.wake();
    }
    if (DOOR.spec && DOOR.spec.onSelect) DOOR.spec.onSelect(CARDS[next], next);
    DOOR.tag();
  },

  press() {
    if (DOOR.hold) {
      if (DOOR.hold.confirm) DOOR.hold.confirm();
      return;
    }
    const card = CARDS[DOOR.target];
    const slot = document.querySelector('[data-slot="' + DOOR.target + '"]');
    if (slot) {
      slot.classList.remove("slot--press");
      // Reading `offsetWidth` is what restarts a CSS animation that is already
      // on the element: without it a second press inside the 90ms does nothing
      // and the control reads as having missed the input.
      void slot.offsetWidth;
      slot.classList.add("slot--press");
    }
    PAD.rumble(70, 0.3);
    if (DOOR.spec && DOOR.spec.onPress) DOOR.spec.onPress(card, DOOR.target);
  },

  wake() {
    if (DOOR.raf) return;
    DOOR.last = 0;
    DOOR.raf = requestAnimationFrame(DOOR.frame);
  },

  /*
   * THE LOOP STOPS WHEN IT SETTLES, which is `ring.ts:10-13`'s rule and is here
   * for its reason: this is a battery-powered seven-inch computer and a rAF
   * that never stops costs play time for nothing. A menu is also the screen a
   * Deck sits on longest -- somebody who opens the game and walks away leaves
   * it here, not on a board.
   */
  frame(now) {
    const dt = DOOR.last ? Math.min(0.05, (now - DOOR.last) / 1000) : 1 / 60;
    DOOR.last = now;
    const out = springStep(DOOR.s, DOOR.v, DOOR.target, SLIDE.w, SLIDE.z, dt);
    DOOR.s = out.x;
    DOOR.v = out.v;
    DOOR.paint();
    if (DOOR.moving()) {
      DOOR.raf = requestAnimationFrame(DOOR.frame);
    } else {
      DOOR.s = DOOR.target;
      DOOR.v = 0;
      DOOR.paint();
      DOOR.raf = 0;
    }
  },

  /*
   * ONE STRING PER MOVING THING, AND NOTHING WRITTEN THAT HAS NOT CHANGED.
   *
   * This used to set six custom properties per card per frame and let CSS
   * assemble `translate(calc(-50% + var(--x)), var(--y)) rotate(var(--rot))
   * scale(var(--scale))` out of them -- eighteen property writes a frame, each
   * one a custom-property invalidation, plus an attribute write and a class
   * toggle that invalidate the whole subtree's style. `z-index` was rewritten
   * sixty times a second to the same number it already held.
   *
   * The transform is now assembled here and written once. The discrete
   * things -- the stacking order, the classes, the attributes -- are compared
   * against what was last written and skipped when they match, so a frame in
   * the middle of a slide touches three transforms and nothing else.
   */
  prev: [],
  paint() {
    const tune = DOOR.spec ? DOOR.spec.tune : TUNE;
    const spinOf = DOOR.spec && DOOR.spec.spin;
    for (let i = 0; i < CARDS.length; i += 1) {
      const el = document.getElementById("slot-" + CARDS[i].id);
      if (!el) continue;
      const was = DOOR.prev[i] || (DOOR.prev[i] = {});
      const p = poseOf(i, DOOR.s, tune);

      const t =
        "translate(calc(-50% + " + p.x.toFixed(2) + "px), " + p.y.toFixed(2) + "px) " +
        "rotate(" + p.rot.toFixed(2) + "deg) scale(" + p.scale.toFixed(4) + ")";
      if (t !== was.t) { el.style.transform = t; was.t = t; }

      if (p.z !== was.z) { el.style.zIndex = String(p.z); was.z = p.z; }

      const ink = p.ink.toFixed(3);
      if (ink !== was.ink) { el.style.setProperty("--ink", ink); was.ink = ink; }

      /*
       * THE NAME TRAVELS TO ITS OUTER EDGE INSTEAD OF JUMPING THERE.
       *
       * `lean` is the ramp; the offset is the distance from where this label
       * naturally sits to where it has to end up, which is why the natural
       * place had to be measured. `spin` turns it toward a spine, and when it
       * is turned its effective half-width is its own HEIGHT -- which is the
       * whole reason a spine can live in a sliver a horizontal name cannot.
       */
      const m = DOOR.labels[i];
      if (m) {
        const lab = el.querySelector(".mcard__label");
        const spin = spinOf ? spinOf(Math.abs(i - DOOR.s)) : 0;
        const half = (m.w / 2) * (1 - spin) + (m.h / 2) * spin;
        const edge = p.lean < 0 ? LAB_INSET + half : m.cardW - LAB_INSET - half;
        const x = p.lean * (edge - m.cx) * (p.lean < 0 ? -1 : 1);
        /* Turned on its side, a name belongs up the middle of the strip it is
           in rather than along the foot of a card it no longer fits. */
        const y = spin * (m.cardH / 2 - m.cy);
        const lt =
          "translate(" + x.toFixed(2) + "px, " + y.toFixed(2) + "px) " +
          "rotate(" + (spin * 90).toFixed(2) + "deg)";
        if (lt !== was.lt) { lab.style.setProperty("--lab", lt); was.lt = lt; }
      }

      if (p.side !== was.side) { el.dataset.side = p.side; was.side = p.side; }
      if (p.covered !== was.covered) {
        if (p.covered) el.dataset.covered = "1";
        else delete el.dataset.covered;
        was.covered = p.covered;
      }
      const on = i === DOOR.target;
      if (on !== was.on) { el.classList.toggle("slot--on", on); was.on = on; }
    }
    if (DOOR.spec && DOOR.spec.paint) DOOR.spec.paint(CARDS[DOOR.target], DOOR.s);
  },

  /**
   * The three numbers that describe a one-card hop.
   *
   *   traverse   when the card has covered 98% of the gap -- what the eye calls
   *              the move, and the number a FLOOR is asked of
   *   settle     when it is permanently within 2px -- the tail, and the number a
   *              CEILING is asked of. "Permanently" and not "first": an
   *              underdamped spring passes through its target on the way to
   *              overshooting it, and the first crossing would report a card
   *              that has not arrived as having arrived
   *   overshoot  how far past it goes, in px
   *
   * Simulated rather than measured off the DOM, for the reason `ring.ts:18-35`
   * gives for tuning in time: a number read off a live animation is a number
   * about the reviewer's monitor. This is the same closed-form step the row
   * itself runs, walked at 1ms, so all three are properties of the spring and
   * of `STEP` -- which is what a README table should be reporting.
   *
   * All three and not only the settle, because the settle on its own is exactly
   * what let a four-frame cut through. See the note over `SLIDE`.
   */
  springProfile() {
    const tune = DOOR.spec ? DOOR.spec.tune : TUNE;
    const D = tune.STEP;
    let x = D;
    let v = 0;
    let traverse = 0;
    let settle = 0;
    let over = 0;
    for (let ms = 1; ms <= 2000; ms += 1) {
      const next = springStep(x, v, 0, SLIDE.w, SLIDE.z, 0.001);
      x = next.x;
      v = next.v;
      if (!traverse && Math.abs(x) <= D * 0.02) traverse = ms;
      if (Math.abs(x) > 2) settle = ms;
      if (x < 0) over = Math.max(over, -x);
    }
    return {
      traverseMs: traverse,
      settleMs: settle + 1,
      overshootPx: Math.round(over * 10) / 10,
      /* What the eye gets, at 60Hz. Four is a cut; eleven is a move. */
      frames: Math.round(traverse / 16.7),
    };
  },

  /*
   * The deck is 1280x800 whatever window is open.
   *
   * Scaled rather than resized, so every number `assert.js` reads is a real
   * device pixel. A mockup that reflows to the reviewer's monitor is being
   * reviewed at the wrong density, and it is always wrong in the direction that
   * flatters the design.
   */
  fit() {
    const el = document.querySelector(".deck");
    if (!el) return;
    DOOR.scale = Math.max(
      0.3,
      Math.min(2, Math.min((innerWidth - 26) / 1280, (innerHeight - 40) / 800))
    );
    el.style.transform = "scale(" + DOOR.scale + ")";
  },

  tag(extra) {
    const tag = document.getElementById("tag");
    if (!tag || !DOOR.spec) return;
    tag.innerHTML =
      "<b>" + esc(DOOR.spec.title) + "</b> · 1280×800 @ " +
      Math.round(DOOR.scale * 100) + "%" +
      " · on: <b>" + esc(CARDS[DOOR.target].label) + "</b>" +
      " · keys: <b>&#8592; &#8594;</b> move · <b>Enter</b> select · " +
      "<b>DOOR_ASSERT()</b> in the console" +
      (extra || "");
  },
};

/* A brief, visible commitment and nothing else. `../menu/README.md` sets the
   rule for every interactive mockup in this folder: "press Play, which commits
   visibly and does nothing else". A mockup that navigated would be claiming to
   be the application. */
function commitPlate(text) {
  const old = document.getElementById("commit");
  if (old) old.remove();
  const el = document.createElement("div");
  el.className = "commit";
  el.id = "commit";
  el.textContent = text;
  const deck = document.querySelector(".deck");
  if (deck) deck.appendChild(el);
  setTimeout(() => el.remove(), 1400);
}

/* The motes, as markup. Twelve, which is `fx/presets.ts:225`'s own count for
   the ambient preset -- not a number picked here. Positions and periods are
   fixed rather than random, because a mockup whose screenshot differs between
   runs cannot be compared with its own earlier shot. */
function motesHTML(n) {
  const count = n || 12;
  let out = '<div class="motes" aria-hidden="true">';
  for (let i = 0; i < count; i += 1) {
    const left = 6 + ((i * 79) % 88);
    const dur = 11 + ((i * 7) % 9);
    const delay = (i * 13) % 11;
    const drift = ((i % 5) - 2) * 22;
    out +=
      '<span class="mote" style="left:' + left + "%;animation-duration:" + dur +
      "s;animation-delay:-" + delay + "s;--drift:" + drift + 'px"></span>';
  }
  return out + "</div>";
}

if (typeof window !== "undefined") {
  window.DOOR = DOOR;
  window.CARDS = CARDS;
  window.TUNE = TUNE;
  window.poseOf = poseOf;
}
