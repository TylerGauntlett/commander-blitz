/* ===========================================================================
   The viewer's own orb -- the shared fixture, the marks, the cell vocabulary,
   the three opponents and the review shell.

   NOT LOADED. `inline.py` splices this between each file's BEGIN and END
   `_self.js` markers, because a <script src> does not load from file:// and
   every mockup in this repo opens standalone.

   WHAT EACH FILE OWNS: `orbHTML(v, f)`, `FILE_ID`, `FILE_LINE`, `ORB_W`, its
   own CSS, and optionally `ORB_SHAPE` ("column" -- the default -- or "banner").
   That is all. Everything else on screen is this file, so a difference between
   two of these mockups is a difference in how the ORB is laid out, which is the
   only thing the round is trying to compare.

   `orbHTML` RETURNS THE ORB'S ROOT ELEMENT, class `orb` and all, and the shell
   drops it straight into the mat. It used to return the INSIDE of an `.orb` the
   shell supplied, which put an `.orb` inside an `.orb` -- so `ORB_ASSERT`
   matched both, counted every cell twice, and reported the inner one as
   escaping the outer. A wrapper the shell owns and the file also draws is a
   wrapper neither of them owns.

   ---------------------------------------------------------------------------
   THE SUBTRACTION THIS ROUND IS ACTUALLY ABOUT

   The first pass drew everything the shipped orb draws, in muster's cells. It
   passed every gate and it was still busy, because passing a uniformity gate
   only proves the noise is evenly spaced. Two channels came out, and they are
   the two largest:

   1. THE VIEWER'S COMMANDER DAMAGE. The pod already carries commander damage on
      the opponents' seats, and a second copy of the same subject on the panel
      six pixels below them is the reader doing the deduplicating. In the first
      pass this was three named rows, a 21-notch track and a gauge full of
      hatching -- about 70px of a 518px column and, visually, the loudest thing
      on the panel by a wide margin.

      WHAT THAT COSTS, SAID PLAINLY RATHER THAN BURIED. An opponent's seat draws
      `worstSource(seat)` -- the worst damage THAT SEAT has taken, from anyone --
      so what YOU have taken is not on any of them. `DMG[0]` is still in this
      fixture, still says 16 from the Duelist, and no direction in this round
      draws it. If it turns out to be wanted, the cheap fix is not to put it back
      on the orb: it is to flip the SEAT's chip from "worst damage they have
      taken" to "damage they have dealt to you", which is the more
      decision-changing number on an opponent's card anyway and puts the fact
      where the reader is already looking.

   2. THE BOARD COUNTS. Lands, creatures, other permanents, total power and the
      creature pip run -- muster's whole battlefield row, which exists because an
      opponent's board is NOT drawn anywhere else. Yours is. It is 841 x 518 of
      the same screen, at 66x92 a card, in three labelled lanes, with a green rim
      on what you can use. A count of it on the panel beside it is the client
      re-stating its own default view.

   WHAT SURVIVES IS FIVE THINGS, and every one of them is either something the
   board cannot show or something you press:

       who you are, whose turn it is, and whether you may act
       your commander -- the portrait, WHICH IS THE BUTTON THAT CASTS IT
       your life
       your mana, by kind, and what a hovered spell would take
       the five zones, as 44px+ targets

   A CONSEQUENCE WORTH NAMING: the reduced orb does not vary with how many
   opponents are at the table. Commander damage was the only channel that did.
   Press 1 2 3 -- the opponents' row changes and the panel does not move a pixel,
   which removes the last reason `.orb--compact` and its `:has()` branches exist.

   `perms`, `detailCell`, `pipsCell`, `powerCell` and `gaugeTicks` are still in
   this file and still used -- by `seatHTML`, for the OPPONENTS, where muster's
   argument for them holds exactly as it did. They are not dead code; they are
   the other half of the point.

   ---------------------------------------------------------------------------
   THE PORTRAIT IS A CONTROL AND STAYS ONE

   `CommandZone.tsx` renders the commander's portrait as the thing you press to
   cast it, with the cost beside it and the tax beside the cost. Every direction
   here keeps that: `.win` is a `<button>`, at 44px or more in both dimensions in
   all five, and when the commander is castable AND you can afford it the button
   takes the `--playable` rim and says so in green -- the same rim every castable
   card in the client takes, which is the point of using it.

   TWO THINGS THE DESKTOP ROUND LEARNED THE HARD WAY AND THIS ONE INHERITS:

     * IT IS `aria-disabled`, NEVER `disabled`. A disabled control dispatches no
       mouse events, so "the full card is one hover away in the preview rail" was
       false for a commander you could not currently cast -- which is most of the
       game. `../orb/README.md` records the fix: `aria-disabled`, with the click
       gated in the handler.
     * THE COST BELONGS ON THE BUTTON. It moved off its own row and onto the
       portrait's caption strip, which is a cell this panel was drawing anyway.
       A price is part of the control it is a price for, and a commander's mana
       cost while it sits on the battlefield is not a number anybody acts on --
       so the strip says where it is instead, and only shows a price when there
       is something to buy.

   ---------------------------------------------------------------------------
   WHY THIS ROUND EXISTS

   `../seat/06-muster.html` settled a grammar for an opponent: one cell kind at
   three heights, 3px of padding and 3px of gutter everywhere, a lethal gauge
   with life filling from the left and per-source commander damage closing from
   the right, `untapped/total` counts with a 3px meter on the cell's bottom
   edge, a shape-bearing mark on every chip, and the commander's art used twice
   -- once as a crisp window somebody can recognise, once as a heavily veiled
   ground carrying colour identity.

   The viewer's own orb got none of it. It is still `PlayerOrb.tsx` and
   `CommandZone.tsx` as shipped: the plinth, the `.orb__foot` plates and the
   wrapped `.piles` row, with the seven paddings and four gutters
   `../seat/README.md` counted. So the moment a muster seat lands on the board
   there are two visual languages on the table at once, three seats in one and
   the player in the other, six pixels apart.

   THE THREE OPPONENTS IN THIS ROUND ARE THEREFORE REAL MUSTER SEATS AND NOT
   GHOSTS. The question is not "is this orb good"; it is "does this orb belong
   on the same table as that seat", and a dashed rectangle cannot answer it.

   ---------------------------------------------------------------------------
   THE BOX, MEASURED RATHER THAN GUESSED

   `handheld.css` re-values the rails inside `@media (max-width: 1366px)`, so at
   1280x800:

       play column   1280 - 12 (deck padding) - 8 (gap) - 243 (--rail-r) = 1017
       viewer's mat  634 (shell) - 96 (--pod-seat-h) - 4 (gap)           = 534
       .mat padding  8px, kept -- `logic/zoomFit.ts` reads it as VIEWER_MAT.padY
       --mat-side    clamp(132px, 12vw, 190px) at 1280                   = 154

   THE ORB IS 154 x 518 AND THE LANES BESIDE IT ARE 841 x 518.

   That is 79,772 square pixels for a panel whose opponent-facing twin gets
   31,872 -- and the shipped orb spends the difference on being the same panel
   with more air in it. What the extra room is FOR is the question each of these
   five answers differently.
   =========================================================================== */

/* --- The viewer ------------------------------------------------------------
   `../handheld/_handheld.js`'s `ME`, so this round, the seat round and the pad
   round are all looking at the same game -- turn 8, declare-attackers.

   TWO NUMBERS ARE DELIBERATELY NOT THAT FILE'S. `manaOpen` is 10 rather than
   12, because two Forests were spent this turn and a meter that is always full
   has never been seen doing anything; and the viewer has taken commander damage
   from two of three seats, one of them past the warn threshold, because the
   shipped orb draws that plate at every density and it is the channel this
   round has the most room to improve.
-------------------------------------------------------------------------- */

const VIEWER = {
  pid: 0,
  name: "You",
  cmdr: "Aesi, Tyrant of Gyre Strait",
  art: "aesi-tyrant-of-gyre-strait.jpg",
  cost: ["4", "G", "U"],
  life: 34,

  /* Seven Forests, three Islands, Thornwood Falls and Terramorphic Expanse.
     Two of the Forests are tapped, so the land meter reads 10 of 12. */
  lands: 12,
  manaOpen: 10,

  /* One entry per SOURCE and never per symbol -- Thornwood Falls makes G or U
     and counting it twice claims mana that does not exist. `logic/mana.ts`. */
  mana: [
    { sym: "G", n: 5 },
    { sym: "U", n: 3 },
    { sym: "G/U", n: 1 },
    { sym: "C", n: 1 },
  ],

  /* What a hovered Beast Within `{2}{G}` would take, as the ENGINE solves it --
     one green for the coloured pip and two of anything for the generic. Never
     arithmetic here; `logic/mana.ts` owns the payment and the orb only draws
     it. Three mana across three groups, which is the case a single hollowed
     pip run cannot show. */
  spend: { G: 1, U: 1, C: 1 },
  spendOn: "Beast Within",

  lib: 72, hand: 6, gy: 3, exile: 1, cmd: 0, tax: 0,

  /* Eight creatures, five of them attacking and therefore tapped; twenty power
     on board; no fliers, which is honest for this deck.

     NO DIRECTION IN THIS ROUND DRAWS ANY OF IT, and the numbers stay in the
     fixture on purpose: the panel is choosing not to draw a channel it has,
     which is a design decision, rather than being unable to draw one it lacks,
     which is a payload bug. `../seat/06-muster.html` exists because of the
     second kind. This is the first kind. */
  threat: { creatures: 8, untapped: 3, power: 20, fliers: 0, other: 1 },
};

/* The `cmdzone` state: Aesi shuffled back into the command zone, castable, with
   two casts already paid for. This is the branch `CommandZone.tsx` exists for
   and the one the battlefield state cannot show -- and it is a real state rather
   than a stress test, because a commander that has died twice is an ordinary
   turn eight. Aesi leaves the battlefield with it: seven creatures, fifteen
   power.

   {4}{G}{U} is six, plus two of tax is EIGHT, against ten open. So the portrait
   is castable AND affordable here, which is the green `Ready` state. */
const CMDZONE = {
  cmd: 1,
  tax: 2,
  threat: { creatures: 7, untapped: 3, power: 15, fliers: 0, other: 1 },
};

/* The `unpaid` state: the same commander, the same eight to pay, and three mana
   open instead of ten. It exists because "castable" and "affordable" are two
   different things and a panel that only ever draws them together has not been
   tested against the case a player is actually in most of the time.

   IT IS ALSO THE ROUND'S MANA REFLOW. Four groups become two, which is the
   thing that breaks a direction laying one group per row -- the block shrinks by
   66px mid-game and everything under it has to not move. */
const UNPAID = {
  cmd: 1,
  tax: 2,
  threat: { creatures: 7, untapped: 3, power: 15, fliers: 0, other: 1 },
  lands: 12,
  manaOpen: 3,
  mana: [{ sym: "G", n: 2 }, { sym: "U", n: 1 }],
  spend: { G: 1, U: 1, C: 1 },
};

/* --- The pod ---------------------------------------------------------------
   `../seat/_seat.js`'s three opponents, unchanged, because they are drawn here
   as real muster seats and a fixture that drifted would make the comparison
   this round is for meaningless.
-------------------------------------------------------------------------- */

const SEATS = [
  {
    pid: 1,
    name: "AI 1",
    cmdr: "Edgar Markov",
    art: "edgar-markov.jpg",
    manaOpen: 2,
    lands: 3,
    life: 25,
    lib: 84, hand: 4, gy: 6, exile: 0, cmd: 1,
    threat: { creatures: 4, untapped: 2, power: 4, fliers: 1, other: 0 },
  },
  {
    pid: 2,
    name: "Marco",
    cmdr: "Isperia, Supreme Judge",
    art: "isperia-supreme-judge.jpg",
    manaOpen: 5,
    lands: 5,
    life: 31,
    lib: 79, hand: 5, gy: 2, exile: 0, cmd: 1,
    revealed: 2,
    threat: { creatures: 2, untapped: 2, power: 4, fliers: 2, other: 1 },
  },
  {
    pid: 3,
    name: "Duelist",
    cmdr: "Krenko, Mob Boss",
    art: "krenko-mob-boss.jpg",
    manaOpen: 4,
    lands: 4,
    life: 18,
    lib: 88, hand: 3, gy: 9, exile: 2, cmd: 1,
    threat: { creatures: 1, untapped: 1, power: 1, fliers: 0, other: 1 },
  },
];

/* Commander damage TAKEN, per seat, per source. A matrix and not a list,
   because the sources a seat has depend on how many seats are at the table.

   ROW 0 IS KEPT AND DRAWN BY NOTHING. It says the viewer has taken 16 from the
   Duelist -- one connection from lethal -- and no direction in this round puts
   that on the panel; see the note at the top of this file for why, and for the
   one-line change to the SEATS that would make the fact reachable again without
   it. Rows 1-3 are `../seat/_seat.js`'s and are drawn, on the opponents. */
const DMG = {
  0: { 1: 4, 2: 0, 3: 16 },
  1: { 0: 5, 2: 0, 3: 0 },
  2: { 0: 0, 1: 3, 3: 0 },
  3: { 0: 0, 1: 16, 2: 0 },
};

const LETHAL = 21;
const WARN = LETHAL - 6;
const START_LIFE = 40;

const NAMES = { 0: "You", 1: "AI 1", 2: "Marco", 3: "Duelist" };
const CMDRS = {
  0: "Aesi, Tyrant of Gyre Strait",
  1: "Edgar Markov",
  2: "Isperia, Supreme Judge",
  3: "Krenko, Mob Boss",
};

const LOSS = "Lost — 21 commander damage";

/* Eight pips and then a count, for `pileLeaves`'s reason: past eight the extra
   pips say nothing a reader can use. The cap costs resolution and never
   information, because the COUNT is on the creature cell beside them. */
const MAX_PIPS = 8;

/* --- Helpers -------------------------------------------------------------- */

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const artUrl = (file) => "../art/" + file;
const symUrl = (tok) => "../cards/symbols/" + String(tok).replace("/", "-").toUpperCase() + ".svg";
const symHTML = (tok) => '<img class="sym" src="' + symUrl(tok) + '" alt="" aria-hidden="true">';

const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
const pct = (n, d) => (d > 0 ? (n / d) * 100 : 0) + "%";

/** The opponents at the table right now -- `logic/zoneGrouping.ts`. */
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

/** The viewer, with whichever state `s` is on folded in. */
function viewerNow(f) {
  if (f.unpaid) return Object.assign({}, VIEWER, UNPAID);
  if (f.cmdzone) return Object.assign({}, VIEWER, CMDZONE);
  return VIEWER;
}

/* --- The marks -------------------------------------------------------------
   `../seat/_seat.js`'s icon set, verbatim. It is a legibility argument and not
   a colour one -- ADR 0006: the shipped strip drops every zone label at 16px
   and what is left is a coloured chip with a number in it, so nothing on the
   chip says which zone it is. A shape can say it without being taught.

   They are pictures, not words -- `aria-hidden`, with the real name carried by
   the cell's `aria-label` and surfaced by hover and by the cursor. That is the
   line `assert.js` draws between "a decoration" and "text somebody reads", and
   it is why the font floor does not apply to them.

   NOTHING WAS ADDED FOR THE VIEWER. Two states this round has to draw and the
   seat round did not -- whose turn it is, and who holds priority -- are marks
   on the orb's EDGE rather than icons in it, which is `06-muster.html`'s own
   answer (`.card--active` is a ring, `.card__pri` is a tick) and keeps two
   facts that are about the whole panel from becoming two more chips in it.
-------------------------------------------------------------------------- */

const ICON = {
  /* A creature: a bust. Head and shoulders, filled, unmistakable at 14px. */
  creature:
    '<circle cx="8" cy="4.4" r="2.7"/><path d="M2.6 14.6c0-4.3 2.3-6.2 5.4-6.2s5.4 1.9 5.4 6.2z"/>',
  /* Untapped: a card standing upright. The game's own idiom -- a tapped one is
     the same rectangle turned, which is what the player already reads on board. */
  untapped: '<rect x="4.6" y="1.8" width="6.8" height="12.4" rx="1.3"/>',
  /* Power: a sword, point up. Blade and guard only. */
  power:
    '<path d="M8 .6l2.9 4.8v5.4H5.1V5.4z"/><rect x="2.2" y="10.6" width="11.6" height="2.3" rx="1.15"/>',
  /* A flier: wings. Stroked, because a filled wing at 14px is a blob. */
  flier:
    '<path d="M1.4 10.8C4 4.6 6.2 4.9 8 9.4c1.8-4.5 4-4.8 6.6 1.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  /* Open mana: the untapped source, as a ring with a drop in it. */
  mana:
    '<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.7"/><circle cx="8" cy="8" r="2.6"/>',
  /* A land: a plot of ground, in perspective. A trapezoid because every other
     rectangle on the panel is a card. */
  land: '<path d="M1.4 13.8L4.4 5.4h7.2l3 8.4z"/>',
  /* Everything on the battlefield that is not a creature and not a land -- the
     artifacts and enchantments. A cut gem, which is neither the star nor the
     crown at 14px. */
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

/* --- The zones -------------------------------------------------------------
 * THE ROUND'S FIRST FINDING LIVES IN THIS FUNCTION.
 *
 * `06-muster.html` demoted an opponent's zone marks from 44px buttons to plain
 * marks, and argued the case properly: 96px will not hold four rows one of
 * which is 44 tall, two of the five were never controls anyway (a library is
 * hidden information; an unrevealed hand renders "Hidden — 4 cards", which is
 * the number on the chip you just pressed), and the route into any of them is
 * the seat sheet.
 *
 * NONE OF THAT APPLIES TO YOUR OWN ORB. A 518px column holds five 44px targets
 * with 298px left over, and four of the five have something real behind them:
 * your hand is your hand, your graveyard and exile are public, and your command
 * zone is where you cast your commander from. So they go back to being buttons,
 * and the seat's trade turns out to be a cost of 96px rather than a finding
 * about zones.
 *
 * THE LIBRARY STAYS A MARK. It is hidden information whoever owns it, and
 * `PlayerOrb.tsx:96-101` already argues that a control which does nothing when
 * clicked is worse than no control. It is the only one of the five that is
 * dimmed at the edge rather than in the fill, so its count still reads.
 */
function zones(v) {
  const z = [
    { name: "library", label: "Library", icon: "lib", kind: "lib", count: v.lib, peek: false },
    { name: "hand", label: "Hand", icon: "hand", kind: "hand", count: v.hand, peek: true },
    { name: "graveyard", label: "Graveyard", icon: "gy", kind: "gy", count: v.gy, peek: true },
  ];
  /* Exile appears the moment anything is exiled and is NOT a fixed slot -- the
     orb can therefore show four marks or five, which is the reflow every
     direction here has to survive. The viewer has one card in exile. */
  if (v.exile > 0) {
    z.push({ name: "exile", label: "Exile", icon: "ex", kind: "ex", count: v.exile, peek: true });
  }
  z.push({ name: "command", label: "Command zone", icon: "cmd", kind: "cmd", count: v.cmd, peek: true });
  return z;
}

/* --- The shared cell vocabulary --------------------------------------------
   Muster's cells, built once here so five files cannot quietly drift into five
   dialects of them. A direction chooses WHERE these go and how big a box they
   sit in; it does not get to re-invent what a permanent count looks like.
-------------------------------------------------------------------------- */

/**
 * One `untapped/total` cell. `open` is null for a cell with no tapped state to
 * draw: it prints one number and takes a flat ground, which is the honest thing
 * to do with a channel the payload does not carry -- better than a full bar it
 * cannot vouch for.
 */
function permCell(kind, icon, total, open, label) {
  const frac = open === null ? "" : ' style="--fill:' + pct(open, total) + '"';
  const text = open === null ? total : open + "/" + total;
  return (
    '<span class="perm perm--' + kind + (total === 0 ? " perm--zero" : "") + '"' + frac +
      ' data-cell data-name aria-label="' + esc(label) + '">' +
      ico(icon) + "<span>" + text + "</span>" +
    "</span>"
  );
}

/** The three counts: lands, creatures, everything else. */
function perms(v) {
  const t = v.threat;
  const landsTapped = v.lands - v.manaOpen;
  const creaturesTapped = t.creatures - t.untapped;
  return (
    permCell("land", "land", v.lands, v.manaOpen,
      plural(v.lands, "land") + " — " + v.manaOpen + " untapped, " + landsTapped + " tapped") +
    permCell("creature", "creature", t.creatures, t.untapped,
      plural(t.creatures, "creature") + " — " + t.untapped + " untapped, " + creaturesTapped + " tapped") +
    permCell("other", "other", t.other, null,
      t.other === 0 ? "No artifacts or enchantments"
      : t.other === 1 ? "1 artifact or enchantment"
      : t.other + " artifacts or enchantments")
  );
}

/**
 * The pips, as a run: one per creature, filled is untapped, a clipped corner
 * flies. Capped at eight for `pileLeaves`'s reason -- past eight the extra pips
 * say nothing a reader can use, and the cap costs resolution and never
 * information because the COUNT is on the creature cell.
 */
function pipRun(v) {
  const t = v.threat;
  const n = Math.min(t.creatures, MAX_PIPS);
  let up = t.untapped;
  let fly = t.fliers;
  const out = [];
  for (let i = 0; i < n; i += 1) {
    /* Untapped first and fliers first, so the pips a player cares about are the
       ones that survive the cap. */
    const isUp = up-- > 0;
    const isFly = fly-- > 0;
    out.push('<span class="pip' + (isUp ? " pip--up" : "") + (isFly ? " pip--fly" : "") + '"></span>');
  }
  const more = t.creatures > MAX_PIPS ? '<span class="pips__more">+' + (t.creatures - MAX_PIPS) + "</span>" : "";
  return '<span class="pips">' + (out.join("") || '<span class="pips__more">none</span>') + more + "</span>";
}

const pipLabel = (v) =>
  (v.threat.fliers ? plural(v.threat.fliers, "flier") + ", " : "") +
  v.threat.untapped + " of " + plural(v.threat.creatures, "creature") + " untapped";

/**
 * THE DETAIL CELL, AND ITS TWO HALVES, BECAUSE A NARROW COLUMN CANNOT HOLD IT
 * WHOLE.
 *
 * Muster's detail is one cell -- the pip run at one end and the total power at
 * the other -- and it works because a seat gives it 130px. A 154px column gives
 * it 98, and eight pips plus a power numeral is 128. So the two halves are
 * available separately as well, and a direction that has the width uses
 * `detailCell` while one that does not uses `pipsCell` and `powerCell` on two
 * rows. Same marks, same geometry, same tint; only the wrapping differs.
 */
function pipsCell(v) {
  return (
    '<span class="perm perm--detail" data-cell data-name aria-label="' + esc(pipLabel(v)) + '">' +
      pipRun(v) +
    "</span>"
  );
}

function powerCell(v) {
  return (
    '<span class="perm perm--detail perm--pow" data-cell data-name ' +
      'aria-label="' + esc(v.threat.power + " power on board") + '">' +
      ico("power") + "<span>" + v.threat.power + "</span>" +
    "</span>"
  );
}

/** Both halves in one cell -- muster's own, for the directions with the width. */
function detailCell(v) {
  const label = pipLabel(v) + ", " + v.threat.power + " power on board";
  return (
    '<span class="perm perm--detail" data-cell data-name aria-label="' + esc(label) + '">' +
      pipRun(v) +
      '<span class="perm__pow">' + ico("power") + "<span>" + v.threat.power + "</span></span>" +
    "</span>"
  );
}

/**
 * The mana groups: one mark per KIND with a count, never one per mana.
 *
 * As a 9px dot a pip per mana was honest and cheap; as the real symbol it is
 * twice as wide, and ten untapped lands wrapped a 190px column to three lines.
 * Grouping is also how players say it out loud.
 *
 * When a castable card is hovered the group shows what you would have LEFT and
 * a faint negative for what goes -- the same question the hollowed-out pips
 * answered, in the form a counted chip can answer it.
 */
function manaCells(v, f) {
  if (!v.mana.length) {
    return '<span class="mgrp mgrp--none" data-cell data-name aria-label="No mana available">—</span>';
  }
  return v.mana.map((g) => {
    const spend = f.spending ? v.spend[g.sym] || 0 : 0;
    const left = g.n - spend;
    const mark = g.sym.indexOf("/") >= 0
      ? '<span class="mgrp__any" aria-hidden="true"></span>'
      : symHTML(g.sym);
    const label = g.sym.indexOf("/") >= 0
      ? g.n + " sources of green or blue" + (spend ? " — " + v.spendOn + " taps " + spend : "")
      : g.n + " " + g.sym + (spend ? " — " + v.spendOn + " taps " + spend : "");
    return (
      '<span class="mgrp' + (spend ? " mgrp--spent" : "") + '" data-cell data-name ' +
        'aria-label="' + esc(label) + '">' +
        mark +
        '<span class="mgrp__n tabular">' + left + "</span>" +
        (spend ? '<span class="mgrp__spend tabular">−' + spend + "</span>" : "") +
      "</span>"
    );
  }).join("");
}

/** The bare count of open sources, for the directions that print a total
    beside the per-kind rows rather than instead of them. */
const manaTotal = (v) => v.mana.reduce((n, g) => n + g.n, 0);

/** How much mana is open, and what a hovered spell would leave. One string, so
    a direction that has room for a sentence and one that has room for a chip
    are saying the same thing. */
function manaLabel(v, f) {
  const total = v.mana.reduce((n, g) => n + g.n, 0);
  const spent = f.spending
    ? Object.keys(v.spend).reduce((n, k) => n + v.spend[k], 0)
    : 0;
  return spent
    ? total + " available; " + v.spendOn + " taps " + spent
    : total + " available";
}

/**
 * The zone row.
 *
 * THE TARGET IS BIGGER THAN THE INK, AND THAT IS THE WHOLE TRICK HERE.
 *
 * A first pass made the viewer's zones 44px buttons by making the CHIPS 44px --
 * then 68, then 72, because the room existed. Set beside the opponents' seats
 * six pixels above, whose chips are 20px, they read as bloated: the same five
 * facts, in the same colours, three times the size, on the panel that needed the
 * least emphasis. Size is a signal and it was saying something untrue.
 *
 * So the chip is 21px -- a seat's, to the pixel -- and it sits centred inside a
 * 44px `<button>`. The ink matches the opponents; the thumb still lands. The
 * button is transparent, so the panel spends 44px of HEIGHT on the row and none
 * of its INK, which is the difference between a target and a graphic.
 *
 * `data-name` and the accessible name go on the BUTTON, because that is the
 * control; `data-cell` goes on the chip, because that is the geometry
 * `boxKinds` is measuring. On an opponent's seat there is no button and the chip
 * carries both -- which is the round's first finding stated in markup.
 */
function zoneMarks(v, opts) {
  const o = opts || {};
  return zones(v).map((z) => {
    /* The library is never a button, whoever is asking. */
    const isBtn = o.as === "button" && z.peek;
    const cls = [
      "zmark",
      "zmark--" + z.kind,
      z.count > 0 ? "" : "zmark--empty",
      isBtn ? "" : "zmark--flat",
      o.cls || "",
    ].filter(Boolean).join(" ");
    const label = z.label + ": " + z.count + (isBtn ? " — opens" : z.peek ? "" : " — hidden information");
    const chip =
      '<span class="' + cls + '" data-cell' +
        (isBtn ? "" : ' data-name data-testid="pile-' + v.pid + "-" + z.name + '"' +
          ' aria-label="' + esc(label) + '"') + ">" +
        ico(z.icon) + z.count +
      "</span>";
    if (!isBtn) return chip;
    return (
      '<button type="button" class="zhit" data-name' +
        ' data-testid="pile-' + v.pid + "-" + z.name + '"' +
        ' aria-label="' + esc(label) + '">' + chip + "</button>"
    );
  });
}

/* The same marks as one string, for the directions that lay them out in a
   single run. A file that needs them split across rows takes the array. */
function zoneRow(v, opts) {
  return zoneMarks(v, opts).join("");
}

/** The commander's cost, plus the tax if any is owed. The tax rides beside the
    cost it modifies, which is the only arrangement in which a surcharge means
    anything -- `PlayerOrb.tsx` puts it here for the same reason. */
function costHTML(v) {
  return (
    v.cost.map(symHTML).join("") +
    (v.tax > 0 ? '<span class="tax tabular">+' + v.tax + "</span>" : "")
  );
}

/** Converted mana cost. `{4}{G}{U}` is six: the generic is worth its number and
    every coloured pip is worth one. */
const cmv = (v) =>
  v.cost.reduce((n, tok) => n + (/^\d+$/.test(tok) ? +tok : 1), 0);

/**
 * WHAT THE PORTRAIT BUTTON IS DOING, which is the one piece of state on this
 * panel that decides whether a control does anything.
 *
 * `CommandZone.tsx` distinguishes nine commander states; these are the four this
 * fixture can be in, and the split that matters is between the last two:
 *
 *   board   on the battlefield          -- not a cast, nothing to price
 *   ready   in the command zone, and you can pay      -- `--playable`, green
 *   short   in the command zone, and you cannot       -- priced, not lit
 *   out     eliminated
 *
 * CASTABLE AND AFFORDABLE ARE TWO DIFFERENT THINGS. The shipped orb lights the
 * plinth on `playableOids`, which already folds the payment in, so this mockup
 * computes the same split from the fixture rather than inventing a third rule --
 * and `unpaid` exists as a review state precisely so the unlit-but-priced case
 * is on screen rather than assumed.
 *
 * TWO STRINGS, NOT ONE, AND THE REASON IS ARITHMETIC RATHER THAN STYLE. "On the
 * battlefield" is 131px at 16px/700 -- it fits a 140px caption strip and does
 * not fit the 86px left beside three mana symbols and a tax. A direction takes
 * whichever it has room for; `long` goes in the control's `aria-label` either
 * way, so a panel printing the short form is naming the same state and not a
 * different one. `docs/mockup-fidelity.md` defect 5 is what happens when this is
 * left to a single string and an ellipsis.
 */
function cmdrState(v, f) {
  if (f.out) return { word: "Out", long: "Eliminated", cls: "out", cast: false, need: 0 };
  if (v.cmd > 0) {
    const need = cmv(v) + v.tax;
    const ready = manaTotal(v) >= need;
    return ready
      ? { word: "Ready", long: "Ready to cast", cls: "ready", cast: true, need }
      : { word: "Need " + need, long: "In the command zone — " + need + " mana to cast",
          cls: "short", cast: true, need };
  }
  return { word: "In play", long: "On the battlefield", cls: "board", cast: false, need: 0 };
}

/**
 * The portrait, as the control it is.
 *
 * ONE FUNCTION FOR ALL FIVE DIRECTIONS, because "is the commander castable and
 * can I afford it" is not a thing five mockups should each answer their own way
 * -- and because the `aria-disabled` rule below is the sort of thing that gets
 * quietly dropped when it is copied five times.
 *
 * `opts.caption` draws the strip under the picture (cost, tax and state); a
 * direction whose layout already carries those elsewhere passes `false`.
 */
function winButton(v, f, opts) {
  const o = opts || {};
  const st = cmdrState(v, f);
  const cls = ["win", "win--" + st.cls, f.noart ? "win--empty" : "", o.cls || ""]
    .filter(Boolean).join(" ");
  const label = v.cmdr + " — " + st.long +
    (st.cast ? ", costs " + v.cost.join("") + (v.tax ? " plus " + v.tax + " commander tax" : "") : "");

  return (
    '<button type="button" class="' + cls + '"' +
      /* NEVER `disabled`. See the note at the top of this file: a disabled
         control dispatches no mouse events, and the preview rail is driven by
         hover. The click is gated in the handler instead. */
      (st.cast ? "" : ' aria-disabled="true"') +
      /* `data-name` but NOT `data-cell`: the portrait is the picture, not one
         of the panel's uniform cells, and counting it in `boxKinds` would
         report every direction as one geometry worse for having a window.
         Muster's own window carries `data-name` alone for the same reason. */
      ' data-name data-testid="commander-0" aria-label="' + esc(label) + '">' +
      (f.noart ? ico("cmd") : '<img src="' + artUrl(v.art) + '" alt="" aria-hidden="true">') +
      (o.who === false ? "" :
        '<span class="win__who">' + esc(v.name) +
          (f.out ? '<span class="win__sub win__sub--out">' + esc(f.loss) + "</span>" : "") +
        "</span>") +
      (o.caption === false ? "" :
        '<span class="win__cap">' +
          (st.cast ? costHTML(v) : "") +
          '<span class="win__st">' + st.word + "</span>" +
        "</span>") +
    "</button>"
  );
}

/**
 * The lethal gauge, horizontal: life fills from the left against 40 and
 * commander damage closes from the right, one tick per SOURCE at its own
 * fraction of 21, offset by the ones outside it -- so two sources at 4 and 16
 * eat twenty twenty-firsts between them, which is not lethal and must not look
 * like it.
 *
 * A pseudo-element and not a child for the fill, so the numerals sit ON it and
 * the row's width is never a function of how full it is.
 */
function gaugeTicks(seat, base) {
  const cls = base || "tick";
  let offset = 0;
  return sources(seat)
    .filter((src) => src.n > 0)
    .map((src) => {
      const w = (Math.min(src.n, LETHAL) / LETHAL) * 100;
      const html =
        '<span class="' + cls + (src.n >= WARN ? " " + cls + "--warn" : "") + '" data-name ' +
        'style="--w:' + w + "%; right:" + offset + '%" ' +
        'aria-label="' + esc(src.n + " of " + LETHAL + " from " + src.who + " — " + src.cmdr) + '"></span>';
      offset += w;
      return html;
    })
    .join("");
}

/**
 * The VIEWER's life, said in full and said only about life.
 *
 * Separate from `gaugeLabel` below, which is the opponents' and still names the
 * commander damage on their gauges. A shared label that mentioned damage would
 * have put the channel back on the panel through the accessible name, which is
 * the same channel arriving by a quieter door -- and an accessible name that
 * describes something the sighted reader cannot see is its own defect.
 */
const lifeLabel = (v, f) =>
  f.out ? "Eliminated — " + LOSS : v.life + " life of " + START_LIFE;

/** The worst source, and the sentence that names it. */
function worstSource(seat) {
  return sources(seat).slice().sort((a, b) => b.n - a.n)[0] || { n: 0, who: "nobody", cmdr: "" };
}

function gaugeLabel(seat, f) {
  const worst = worstSource(seat);
  return (
    (f && f.out ? "Eliminated — " : "") +
    seat.life + " life of " + START_LIFE + " — " +
    (worst.n === 0
      ? "no commander damage taken"
      : "worst commander damage " + worst.n + " of " + LETHAL + " from " + worst.who)
  );
}

/* --- Review state ---------------------------------------------------------
   Three knobs, all keyboard, all printed on the bezel. They exist because the
   things that break an orb are the things a single screenshot cannot show: an
   opponent arriving, priority passing to you, a spell being hovered, the
   commander going back to the command zone, the seat dying, and the art not
   being there.
-------------------------------------------------------------------------- */

const S = {
  density: 3,
  /* rest | priority | spending | cmdzone | unpaid | out | noart.

     `rest` is NOT the empty state -- it is somebody else's turn, which is where
     an orb spends most of a four-player game and is the one a design that only
     looks right lit up will fail.

     `noart` is a real state and not a stress test: `logic/cardArt.ts` returns
     `undefined` when the image map has not been fetched and `null` when the
     printing has no art, and `CommandZone` renders nothing at all when the
     commander sits in a hidden zone. A direction that only works with a picture
     in it has to say so. */
  mark: "priority",
  measure: false,
};

const MARKS = ["rest", "priority", "spending", "cmdzone", "unpaid", "out", "noart"];

/** The state flags the shell hands `orbHTML`, so no file invents its own. */
function flags() {
  const m = S.mark;
  return {
    /* Two different things, drawn two ways -- `06-muster.html`'s own answer: a
       ring for whose turn it is, a tick at the top edge for who may act. On the
       shipped orb they are one dot between them. */
    active: m !== "rest" && m !== "out",
    priority: m !== "rest" && m !== "out",
    spending: m === "spending",
    cmdzone: m === "cmdzone" || m === "unpaid",
    unpaid: m === "unpaid",
    out: m === "out",
    noart: m === "noart",
    loss: LOSS,
  };
}

/* --- The three opponents, as they actually are ----------------------------
   `../seat/06-muster.html`'s `seatHTML`, namespaced to `.seat`. Nothing about
   it is a choice this round is making; it is the thing this round's five
   directions have to sit beside without looking like a different application.
-------------------------------------------------------------------------- */

function seatHTML(seat) {
  const worst = worstSource(seat);
  const zone = zones(seat).map((z) =>
    '<span class="zmark zmark--' + z.kind + (z.count > 0 ? "" : " zmark--empty") + '"' +
    ' aria-label="' + esc(z.label + ": " + z.count) + '">' +
    ico(z.icon) + z.count + "</span>"
  ).join("");

  return (
    '<article class="seat" data-testid="player-' + seat.pid + '">' +
      '<img class="seat__ground" src="' + artUrl(seat.art) + '" alt="" aria-hidden="true">' +
      '<span class="seat__veil" aria-hidden="true"></span>' +
      '<span class="seat__win"><img src="' + artUrl(seat.art) + '" alt="" aria-hidden="true"></span>' +
      '<div class="seat__head">' +
        '<span class="seat__name">' + esc(seat.name) + "</span>" +
        '<span class="seat__cmdr">' + esc(seat.cmdr) + "</span>" +
      "</div>" +
      '<div class="seat__gauge" style="--fill:' + (Math.min(seat.life / START_LIFE, 1) * 100) + '%" ' +
        'aria-label="' + esc(gaugeLabel(seat, null)) + '">' +
        gaugeTicks(seat, "seat__tick") +
        '<span class="seat__life tabular">' + seat.life + "</span>" +
        '<span class="seat__dmg' + (worst.n >= WARN ? " seat__dmg--warn" : "") +
          (worst.n === 0 ? " seat__dmg--zero" : "") + '">' + ico("crown") + worst.n + "</span>" +
      "</div>" +
      '<div class="seat__perms">' + perms(seat) + detailCell(seat) + "</div>" +
      '<div class="seat__zones">' + zone + "</div>" +
    "</article>"
  );
}

/* --- The board the orb is taking room from --------------------------------
   The lanes are ghosted at the real card proportions, and THE NUMBER OF CARDS
   IN THEM IS COMPUTED FROM WHAT THE ORB LEFT rather than typed in -- so a
   direction that hands the column back gets its extra cards drawn in
   `--playable` green and one that takes more width loses them in red. A claim
   about footprint should be visible, not asserted.
-------------------------------------------------------------------------- */

/* 841px of lanes at the 154px column is ten cards; that is the baseline every
   direction is measured against. */
const BASELINE_CARDS = 10;

function laneCards() {
  const banner = (typeof ORB_SHAPE !== "undefined" && ORB_SHAPE === "banner");
  /* `ORB_W` is declared by each file beside its own CSS, so the ghost and the
     stylesheet cannot disagree about how wide the column is. */
  const orbW = banner ? 0 : (typeof ORB_W !== "undefined" ? ORB_W : 154) + 6;
  /* 1017 play column - 16 mat padding - 2 border = 999 of lanes; then the
     ghost's own 12px of padding, its 74px tag column and one 5px gutter. */
  const laneW = 999 - orbW - 12 - 74 - 5;
  return Math.max(1, Math.floor(laneW / 71));
}

function ghostRow(tag, n) {
  const cards = [];
  for (let i = 0; i < n; i += 1) {
    const extra = i >= BASELINE_CARDS ? " gh__card--won" : "";
    cards.push('<span class="gh__card' + extra + '"></span>');
  }
  /* What a wider orb took, drawn in the same row so the trade is one picture. */
  for (let i = n; i < BASELINE_CARDS; i += 1) {
    cards.push('<span class="gh__card gh__card--lost"></span>');
  }
  return '<div class="gh__lane"><span class="gh__tag">' + tag + "</span>" + cards.join("") + "</div>";
}

function ghostLanes() {
  const n = laneCards();
  return (
    '<div class="gh gh--lanes" aria-hidden="true">' +
    ghostRow("Lands", n) +
    ghostRow("Creatures", n) +
    ghostRow("Other", n) +
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
  const f = flags();
  const v = viewerNow(f);

  const seats = pod()
    .map((seat) => '<div class="mat" data-seat="' + seat.pid + '">' + seatHTML(seat) + "</div>")
    .join("");

  const shape = typeof ORB_SHAPE !== "undefined" ? ORB_SHAPE : "column";

  root.innerHTML =
    '<div class="bezel">' +
      '<div class="deck" data-density="' + S.density + '"' +
        (S.measure ? ' data-measure="yes"' : "") + ">" +
        '<div class="shell">' +
          '<div class="play">' +
            '<div class="opps" data-testid="opponents">' + seats + "</div>" +
            '<div class="mine" data-shape="' + shape + '">' +
              orbHTML(v, f) +
              ghostLanes() +
            "</div>" +
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
   wrong in the direction that flatters the design. */
let SCALE = 1;
function fitDeck() {
  const el = document.querySelector(".deck");
  if (!el) return;
  SCALE = Math.max(0.3, Math.min(2, Math.min((innerWidth - 26) / 1280, (innerHeight - 84) / 800)));
  el.style.transform = "scale(" + SCALE + ")";

  const orb = document.querySelector(".orb");
  const box = orb ? orb.getBoundingClientRect() : null;
  const w = box ? Math.round(box.width / SCALE) : 0;
  const h = box ? Math.round(box.height / SCALE) : 0;

  const tag = document.getElementById("tag");
  if (!tag) return;
  tag.innerHTML =
    "<b>" + esc(FILE_ID) + "</b> · " + esc(FILE_LINE) +
    " · orb <b>" + w + "×" + h + "</b>" +
    " · lanes <b>" + laneCards() + "</b> cards" +
    " · Deck 1280×800 at <b>" + Math.round(SCALE * 100) + "%</b>" +
    " · <b>1 2 3</b> opponents · <b>s</b> " + S.mark + " · <b>m</b> measure";
}

addEventListener("resize", fitDeck);

addEventListener("keydown", (e) => {
  const k = e.key.toLowerCase();
  if (k === "1" || k === "2" || k === "3") { S.density = +k; render(); }
  else if (k === "s") {
    S.mark = MARKS[(MARKS.indexOf(S.mark) + 1) % MARKS.length];
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
  const out = ORB_ASSERT();
  for (const bad of out.faults) bad.el.setAttribute("data-bad", bad.why);
  const tag = document.getElementById("tag");
  if (!tag) return;
  tag.innerHTML +=
    ' · <b style="color:' + (out.PASS ? "#5ce08a" : "#ff6b5e") + '">' +
    (out.PASS ? "PASS" : "FAIL") + "</b> · " +
    out.cells + " cells · " + out.boxKinds + " box kinds · " + out.padKinds + " pads · min " +
    out.minFontPx + "px · min hit " + out.minHitPx + "px";
}
