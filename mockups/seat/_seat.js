/* ===========================================================================
   The opponent seat -- the shared fixture, the icon set and the review shell.

   NOT LOADED. `inline.py` splices this between each file's BEGIN and END
   `_seat.js` markers, because a <script src> does not load from file:// and
   every mockup in this repo opens standalone. (The markers are not spelled out
   in this comment: a master that names its own marker gets a second copy of it
   spliced into every file, and the splicer refuses the file next time.)

   WHAT IS SHARED AND WHY. These five are five STRUCTURES for one component, so
   the content, the icons, the review chrome and the ghosted board they sit on
   are identical in all five and only `seatHTML()` differs. Each file defines
   that one function and its own CSS; everything else on screen is this file.
   A difference between two of these mockups is therefore a difference in how
   the seat is laid out, which is the only thing the round is trying to compare.

   ---------------------------------------------------------------------------
   THE TWO WIDTHS, MEASURED RATHER THAN GUESSED

   `handheld.css` re-values the rails inside `@media (max-width: 1366px)`, so at
   1280x800 the board column is:

       1280 - 12 (deck padding) - 8 (gap) - 243 (--rail-r at 19vw) = 1017px

   and `.play__opponents` is a flex row with a 10px gap. So a seat gets:

       one opponent      1017 x 96      (--pod-seat-h, handheld.css:160)
       two opponents       503 x 96
       three opponents     332 x 84      (the shorter cap, handheld.css:1041)

   332 x 84 is the design problem. 1017 x 96 is the one the shipped strip was
   drawn for, which is why it stretches rather than compacts -- the same mistake
   the desktop round found in `.orb--compact`, arriving one layout later.

   AND THE SHIPPED SEAT DOES NOT ACTUALLY FIT 332 x 84 EITHER. From the SECOND
   opponent onwards, `handheld.css:1097-1100` sets `.orb__mana` and `.orb__cmd`
   to `display: none` -- so commander damage and the open-mana plate are not
   drawn on an opponent's seat at all in a three- or four-player game, and are
   reachable only by holding R2 for the full mat. The file argues the case and
   the argument is a fair one, but it means the screenshot this round was opened
   on -- the one with `P0 0` and `P2 0` on it -- is the ONE-opponent seat, and
   the pod seat is the one with the channel missing.

   Every direction here draws commander damage at every density. That is the
   thing they are all buying with their layout, and it is why the arithmetic
   below is harder than the shipped layout's.
   =========================================================================== */

/* --- The pod ---------------------------------------------------------------
   Three opponents from `../handheld/_table.js`, so this round and the pad round
   are looking at the same game. Two numbers are deliberately not that file's:
   seat 3 has taken 16 commander damage rather than 12, which is the only way to
   put a seat past the warn threshold (15) and see what a direction does about
   it, and seat 2 has taken 3 rather than 0 so the plate has a middling value as
   well as a zero and a near-lethal one.
-------------------------------------------------------------------------- */

const VIEWER = { pid: 0, name: "You", life: 34, cmdr: "Aesi, Tyrant of Gyre Strait" };

const SEATS = [
  {
    pid: 1,
    name: "AI 1",
    who: "Apprentice",
    human: false,
    cmdr: "Edgar Markov",
    art: "edgar-markov.jpg",
    cost: ["3", "W", "B", "R"],
    /* One entry per SOURCE, never per symbol -- Scoured Barrens makes W or B
       and counting it twice claims mana that does not exist. logic/mana.ts. */
    mana: ["R", "R", "W/B"],
    manaOpen: 2,
    /* THE CHANNEL NO DIRECTION IN THIS ROUND DRAWS. Two Mountains and a Scoured
       Barrens, one of them tapped -- `_handheld.js`'s OPP.lands, counted. It is
       a seat-level fact and not a `threatOf()` one, which is exactly why it has
       been invisible: `threat.ts` never had it and `types.ts` never sent it. */
    lands: 3,
    life: 25,
    lib: 84, hand: 4, gy: 6, exile: 0, cmd: 1, tax: 0,
    /* threatOf(): four creatures (two tapped Vampire tokens), one flier. */
    threat: { creatures: 4, untapped: 2, power: 4, fliers: 1, other: 0 },
  },
  {
    pid: 2,
    name: "Marco",
    who: "Human",
    human: true,
    cmdr: "Isperia, Supreme Judge",
    art: "isperia-supreme-judge.jpg",
    cost: ["4", "W", "U"],
    mana: ["W", "W", "U", "U", "W/U"],
    manaOpen: 5,
    /* Three Plains and two Islands, all untapped -- `_table.js`'s OPP2.lands. */
    lands: 5,
    life: 31,
    lib: 79, hand: 5, gy: 2, exile: 0, cmd: 1, tax: 0,
    /* You cast a "look at target player's hand" at Marco two turns ago, so two
       of his five cards are in `hand_revealed` and his hand mark IS a control.
       The other two seats' hands are not, and the round draws both. */
    revealed: 2,
    threat: { creatures: 2, untapped: 2, power: 4, fliers: 2, other: 1 },
  },
  {
    pid: 3,
    name: "Duelist",
    who: "Duelist",
    human: false,
    cmdr: "Krenko, Mob Boss",
    art: "krenko-mob-boss.jpg",
    cost: ["2", "R", "R"],
    mana: ["R", "R", "R", "R"],
    manaOpen: 4,
    /* Four Mountains -- `_table.js`'s OPP3.lands. */
    lands: 4,
    life: 18,
    lib: 88, hand: 3, gy: 9, exile: 2, cmd: 1, tax: 2,
    threat: { creatures: 1, untapped: 1, power: 1, fliers: 0, other: 1 },
  },
];

/* Commander damage TAKEN, per seat, per source. A matrix and not a list,
   because the sources a seat has depend on how many seats are at the table --
   which is the whole reason this plate is the hardest thing on the strip. */
const DMG = {
  1: { 0: 5, 2: 0, 3: 0 },
  2: { 0: 0, 1: 3, 3: 0 },
  3: { 0: 0, 1: 16, 2: 0 },
};

const LETHAL = 21;
const WARN = LETHAL - 6;

const NAMES = { 0: "You", 1: "AI 1", 2: "Marco", 3: "Duelist" };
const CMDRS = {
  0: "Aesi, Tyrant of Gyre Strait",
  1: "Edgar Markov",
  2: "Isperia, Supreme Judge",
  3: "Krenko, Mob Boss",
};

/* --- Helpers -------------------------------------------------------------- */

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const artUrl = (file) => "../art/" + file;
const symUrl = (tok) => "../cards/symbols/" + String(tok).replace("/", "-").toUpperCase() + ".svg";
const symHTML = (tok) => '<img class="sym" src="' + symUrl(tok) + '" alt="" aria-hidden="true">';

/** The seats at the table right now, viewer first -- `logic/zoneGrouping.ts`. */
const pod = () => SEATS.slice(0, S.density);

/** Who could have hit this seat with a commander, in seating order from you. */
function sources(seat) {
  return [0].concat(pod().map((s) => s.pid))
    .filter((pid) => pid !== seat.pid)
    .map((pid) => ({
      pid,
      n: (DMG[seat.pid] || {})[pid] || 0,
      who: NAMES[pid],
      cmdr: CMDRS[pid],
    }));
}

/**
 * The summary line as clauses, in `logic/threat.ts`'s order and with its rule:
 * EMPTY CLAUSES ARE DROPPED. A seat with no fliers must not spend a fifth of a
 * 332px strip saying "0 fliers"; a seat with one absolutely must say so.
 * `creatures` is the exception and is always drawn -- "nothing on board" is the
 * most useful thing the line can say.
 */
/* `t.other` IS NOT IN THIS LIST AND NEITHER IS `seat.lands`. That is not an
 * oversight of this fixture -- it is the shipped strip's own content, copied
 * faithfully. "How many lands, artifacts and enchantments has that seat got"
 * is not answerable from an opponent's seat today at any density, and 01-05
 * all inherit the hole because they all render `threatParts()`. 06 does not
 * call this function; see its own file. */
function threatParts(seat) {
  const t = seat.threat;
  const out = [{ key: "creatures", icon: "creature", value: t.creatures, label: "creature" }];
  if (t.untapped > 0) out.push({ key: "untapped", icon: "untapped", value: t.untapped, label: "untapped" });
  if (t.power > 0) out.push({ key: "power", icon: "power", value: t.power, label: "power" });
  if (t.fliers > 0) out.push({ key: "fliers", icon: "flier", value: t.fliers, label: "flier" });
  if (seat.manaOpen > 0) out.push({ key: "mana", icon: "mana", value: seat.manaOpen, label: "open" });
  return out;
}

const UNCOUNTABLE = { untapped: 1, power: 1, open: 1 };
const clause = (p) =>
  p.value + " " + (p.value === 1 || UNCOUNTABLE[p.label] ? p.label : p.label + "s");

/**
 * The zones, in the shipped order.
 *
 * TWO OF THE FIVE ARE NOT CONTROLS ON AN OPPONENT'S SEAT, AND ONLY ONE OF THEM
 * KNOWS IT. This is the round's second finding and it is worth more than any
 * layout in it, because it is 88px of a 332px strip.
 *
 * `PlayerOrb.tsx` already argues the case for the library: "hidden information,
 * and a control that does nothing when clicked is worse than no control", so
 * the library is a plain element and not a button. An opponent's HAND is the
 * same fact -- `types.ts` sends `hand: null` for every seat but the viewer and
 * `ZonePeek.tsx` renders "Hidden — 4 cards" -- and it is a button anyway, at
 * 44x44, on the strip where 44x44 is the scarcest thing there is.
 *
 * The exception is the one the library already has: `hand_revealed` carries the
 * cards this seat has been SHOWN, by "look at target player's hand" and nothing
 * else, and when it is non-empty the peek has something to open. So the rule is
 * the library's own rule, applied to the zone next to it -- a button when there
 * is something behind it, a mark when there is not.
 *
 * Five 44px targets is 220px of a 332px seat. Three is 132. That difference is
 * why the seats in this round fit at all.
 */
function zones(seat) {
  const z = [
    { name: "library", label: "Library", icon: "lib", kind: "lib", count: seat.lib, peek: false },
    { name: "hand", label: "Hand", icon: "hand", kind: "hand", count: seat.hand, peek: !!seat.revealed },
    { name: "graveyard", label: "Graveyard", icon: "gy", kind: "gy", count: seat.gy, peek: true },
  ];
  /* Exile appears the moment anything is exiled and is NOT a fixed slot -- a
     seat can therefore show four marks or five, which is the reflow every
     direction here has to survive. Seat 3 has two cards in exile. */
  if (seat.exile > 0) {
    z.push({ name: "exile", label: "Exile", icon: "ex", kind: "ex", count: seat.exile, peek: true });
  }
  z.push({ name: "command", label: "Command zone", icon: "cmd", kind: "cmd", count: seat.cmd, peek: true });
  return z;
}

/* --- The marks -------------------------------------------------------------
   WHY THESE EXIST. It is a legibility argument, not a colour one -- ADR 0006.

   The shipped strip drops `.pile__label` at 16px: "Lib", "Hand", "GY" and "CMD"
   all go (`handheld.css:1758`), and what is left of a zone is a coloured chip
   with a number in it. `docs/handheld-playtest.md` already records what that
   costs -- a fixed order only helps somebody who has already learned the order,
   and the colour code has to be learned too. Nothing on the chip says which
   zone it is.

   A shape can say it without being taught. A headstone is a graveyard, a fan of
   three cards is a hand, a face-down card is a library, a dashed outline is a
   card that is not here. That is `.pile__label`'s job, done in the space the
   label could not have.

   They are SVG and not text characters on purpose: a glyph in a font is a
   different picture on every machine, and three of these had no reliable
   character at all.

   They are pictures, not words -- `aria-hidden`, with the real name carried by
   the cell's `aria-label` and surfaced by hover and by the cursor. That is the
   line `../handheld/assert.js` draws between "a decoration" and "text somebody
   reads", and it is why the font floor does not apply to them.
-------------------------------------------------------------------------- */

const ICON = {
  /* A creature: a bust. Head and shoulders, filled, unmistakable at 14px. */
  creature:
    '<circle cx="8" cy="4.4" r="2.7"/><path d="M2.6 14.6c0-4.3 2.3-6.2 5.4-6.2s5.4 1.9 5.4 6.2z"/>',
  /* Untapped: a card standing upright. The game's own idiom -- a tapped one is
     the same rectangle turned, which is what the player already reads on board. */
  untapped: '<rect x="4.6" y="1.8" width="6.8" height="12.4" rx="1.3"/>',
  /* Power: a sword, point up. Blade and guard only -- a first draft had a hilt
     under the guard and at 14px the three stacked parts read as an arrow
     pointing down, which is the opposite of what this mark means. */
  power:
    '<path d="M8 .6l2.9 4.8v5.4H5.1V5.4z"/><rect x="2.2" y="10.6" width="11.6" height="2.3" rx="1.15"/>',
  /* A flier: wings. Stroked, because a filled wing at 14px is a blob. */
  flier:
    '<path d="M1.4 10.8C4 4.6 6.2 4.9 8 9.4c1.8-4.5 4-4.8 6.6 1.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  /* Open mana: the untapped source, as a ring with a drop in it. */
  mana:
    '<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="8" cy="8" r="2.6"/>',
  /* A land: a plot of ground, in perspective. THIS MARK HAS NO CHANNEL IN 01-05
     -- `threatOf()` never counted lands and `types.ts` never sent them, so on
     every seat in this round "how developed is that board" is answered only by
     `manaOpen`, which counts untapped SOURCES and says nothing about how many
     there are. A trapezoid because every other rectangle on the seat is a card
     and orientation is the one difference this round has already ruled out. */
  land: '<path d="M1.4 13.8L4.4 5.4h7.2l3 8.4z"/>',
  /* Everything on the battlefield that is not a creature and not a land -- the
     artifacts and enchantments. `seat.threat.other` HAS CARRIED THIS NUMBER ALL
     ALONG and not one of the five directions draws it: Marco's Favorable Winds
     and the Duelist's Impact Tremors are both on screen and both invisible. A
     cut gem, which is neither the star nor the crown at 14px. */
  other: '<path d="M8 1.1l6.2 5.1-6.2 8.7-6.2-8.7z"/>',
  /* Commander damage: a crown. Twenty-one of these kills you and nothing else
     in the game does, so it gets a mark of its own. */
  crown: '<path d="M1.6 13.2L2.9 4.4 6 8.2 8 2.8l2 5.4 3.1-3.8 1.3 8.8z"/>',
  /* Library: a face-down card. */
  lib:
    '<rect x="3.2" y="1.6" width="9.6" height="12.8" rx="1.5"/><path d="M8 4.4l1.7 3.6L8 11.6 6.3 8z" fill="var(--chip-ink)"/>',
  /* Hand: three cards, fanned. */
  hand:
    '<g transform="rotate(-22 8 13)"><rect x="1.9" y="4.2" width="4.8" height="9.2" rx="1.1"/></g><g transform="rotate(22 8 13)"><rect x="9.3" y="4.2" width="4.8" height="9.2" rx="1.1"/></g><rect x="5.6" y="2.6" width="4.8" height="10.8" rx="1.1"/>',
  /* Graveyard: a headstone. The one mark nobody has to be taught. */
  gy: '<path d="M3.4 15V7.2a4.6 4.6 0 019.2 0V15z"/>',
  /* Exile: a card leaving, drawn as an outline that is not all there. */
  ex:
    '<rect x="3.2" y="1.8" width="9.6" height="12.4" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="3.4 2.6"/>',
  /* The command zone: a star. */
  cmd: '<path d="M8 1l2.1 4.5L15 6.2l-3.6 3.4.9 4.9L8 12.2 3.7 14.5l.9-4.9L1 6.2l4.9-.7z"/>',
};

function ico(name) {
  return (
    '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false" fill="currentColor">' +
    ICON[name] +
    "</svg>"
  );
}

/* --- Review state ---------------------------------------------------------
   Three knobs, all keyboard, all printed on the bezel. They exist because the
   things that break a seat are the things a single screenshot cannot show:
   another seat arriving, the seat becoming a target, the seat dying, and the
   art not being there.
-------------------------------------------------------------------------- */

const S = {
  density: 3,
  /* rest | active | targetable | out | noart. Drawn on the FIRST seat only, so
     the other two stay the control.

     `noart` is a real state and not a stress test: `logic/cardArt.ts` returns
     `undefined` when the image map has not been fetched and `null` when the
     printing has no art, and `CommandZone` renders nothing at all when the
     commander sits in a hidden zone -- shuffled back into the library, say. A
     direction that only works with a picture in it has to say so, and 03 is
     entirely about the picture. */
  mark: "rest",
  measure: false,
};

const LOSS = "Lost — 21 commander damage";

/**
 * The line beside the seat's name: which commander, or why they are out.
 *
 * ONE SLOT, NOT TWO. An eliminated seat is the state that breaks strips --
 * every direction here first grew an extra row for the loss reason and every
 * one of them overflowed its own budget doing it, which the round's gate caught
 * as an escape rather than as a wrap. It does not need a row: the commander's
 * name is the least useful thing on a seat that has already lost, so the loss
 * reason takes its place and the seat does not change size at the exact moment
 * a player is looking at it.
 */
const subline = (seat, f) => (f.out ? f.loss : seat.cmdr);

/** The state flags the shell hands `seatHTML`, so no file invents its own. */
function flagsFor(seat, index) {
  const marked = index === 0;
  return {
    active: marked && S.mark === "active",
    targetable: marked && S.mark === "targetable",
    out: marked && S.mark === "out",
    noart: marked && S.mark === "noart",
    loss: LOSS,
  };
}

/* --- The board the seat is taking room from --------------------------------
   Ghosted, at the real proportions, for the same reason the desktop round drew
   a ghost mat beside every panel: a direction's claim about FOOTPRINT should be
   visible rather than asserted. Every pixel a seat takes here is a pixel off
   the viewer's own board, and at 800px of height that trade is the argument.
-------------------------------------------------------------------------- */

const ghostRow = (tag, n) =>
  '<div class="gh__lane"><span class="gh__tag">' +
  tag +
  "</span>" +
  Array.from({ length: n }, () => '<span class="gh__card"></span>').join("") +
  "</div>";

function ghostBoard() {
  return (
    '<div class="gh gh--mine" aria-hidden="true">' +
    '<div class="gh__side"><span class="gh__tag">Your orb</span></div>' +
    '<div class="gh__lanes">' +
    ghostRow("Lands", 12) +
    ghostRow("Creatures", 8) +
    ghostRow("Other", 1) +
    "</div>" +
    "</div>"
  );
}

function ghostRail() {
  return (
    '<div class="gh gh--rail" aria-hidden="true">' +
    '<span class="gh__tag">Stack · actions · preview</span>' +
    "</div>"
  );
}

function ghostFoot() {
  return (
    '<div class="gh gh--foot" aria-hidden="true">' +
    '<span class="gh__tag">Hand</span>' +
    Array.from({ length: 6 }, () => '<span class="gh__card gh__card--hand"></span>').join("") +
    '<span class="gh__slab">Commit</span>' +
    "</div>"
  );
}

/* --- The shell ------------------------------------------------------------- */

const root = document.getElementById("root");

function render() {
  const seats = pod()
    .map((seat, i) => '<div class="mat" data-seat="' + seat.pid + '">' + seatHTML(seat, flagsFor(seat, i)) + "</div>")
    .join("");

  root.innerHTML =
    '<div class="bezel">' +
      '<div class="deck" data-density="' + S.density + '"' +
        (S.measure ? ' data-measure="yes"' : "") + ">" +
        '<div class="shell">' +
          '<div class="play">' +
            '<div class="opps" data-testid="opponents">' + seats + "</div>" +
            ghostBoard() +
          "</div>" +
          ghostRail() +
        "</div>" +
        ghostFoot() +
      "</div>" +
      '<div class="bezel__tag" id="tag"></div>' +
    "</div>";

  fitDeck();
  if (S.measure) paintMeasurements();
}

/* Exactly one Steam Deck screen, whatever the window is.
   A 1280x800 design opened in a 2560px window is being judged at half the
   angular size a Deck shows it at, and every legibility call made that way is
   wrong in the direction that flatters the design. `../handheld/_handheld.css`
   makes the same argument at more length. */
let SCALE = 1;
function fitDeck() {
  const el = document.querySelector(".deck");
  if (!el) return;
  SCALE = Math.max(0.3, Math.min(2, Math.min((innerWidth - 26) / 1280, (innerHeight - 84) / 800)));
  el.style.transform = "scale(" + SCALE + ")";

  const seat = document.querySelector(".mat");
  const box = seat ? seat.getBoundingClientRect() : null;
  const w = box ? Math.round(box.width / SCALE) : 0;
  const h = box ? Math.round(box.height / SCALE) : 0;

  const tag = document.getElementById("tag");
  if (!tag) return;
  tag.innerHTML =
    "<b>" + esc(FILE_ID) + "</b> · " + esc(FILE_LINE) +
    " · seat <b>" + w + "×" + h + "</b>" +
    " · Deck 1280×800 at <b>" + Math.round(SCALE * 100) + "%</b>" +
    " · <b>1 2 3</b> seats · <b>s</b> " + S.mark + " · <b>m</b> measure";
}

addEventListener("resize", fitDeck);

addEventListener("keydown", (e) => {
  const k = e.key.toLowerCase();
  if (k === "1" || k === "2" || k === "3") { S.density = +k; render(); }
  else if (k === "s") {
    const order = ["rest", "active", "targetable", "out", "noart"];
    S.mark = order[(order.indexOf(S.mark) + 1) % order.length];
    render();
  } else if (k === "m") { S.measure = !S.measure; render(); }
  else return;
  e.preventDefault();
});

/* `m` -- the numbers, on the page.
   Every cell is measured and any that misses a floor is outlined and labelled
   where it is. A gate whose only output is a console object gets read once; a
   gate that draws on the failing element gets read every time. */
function paintMeasurements() {
  const out = SEAT_ASSERT();
  for (const bad of out.faults) bad.el.setAttribute("data-bad", bad.why);
  const tag = document.getElementById("tag");
  if (!tag) return;
  tag.innerHTML +=
    ' · <b style="color:' + (out.PASS ? "#5ce08a" : "#ff6b5e") + '">' +
    (out.PASS ? "PASS" : "FAIL") + "</b> · " +
    out.cells + " cells · " + out.boxKinds + " box kinds · min " + out.minFontPx + "px" +
    " · min hit " + out.minHitPx + "px";
}
