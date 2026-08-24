/* ===========================================================================
   The board, the seats, the hand and the rail's shell -- everything the three
   files share.

   NOT LOADED. `inline.py` splices this between each file's BEGIN and END
   `_board.js` markers. Same contract as `../seat/_seat.js` and `../rail/_rail.js`
   and for the same reason: a mockup has to open standalone from file://, file://
   blocks the fetch a module import would need, and three hand-inlined copies of
   one file quietly stop being the same file.

   WHAT IS IN HERE: the fixture, the card face, the opponent seat, the player
   orb, the lanes, the hand, the game-information strip, the reader, the two
   holds, the review keys, the deck fit, and `BOARD.mount()`.

   WHAT IS NOT: any list, and any commit bar. A file supplies its own `list`, its
   own `commit` and its own `wire`, and that is the only thing the three differ
   by -- which is the round's claim, so it had better be the only thing.

   NOTHING HERE RUNS ON LOAD. `render()` needs the file's list, so the file calls
   `BOARD.mount({...})` at the end of its own script.
   =========================================================================== */

/* ===========================================================================
   1. THE FIXTURE
   ---------------------------------------------------------------------------
   `../handheld/_handheld.js` and `../handheld/_table.js`, copied rather than
   adapted, so this round and the pad round are looking at the same game. Turn 8
   of the reference screenshot, four seats, and every number the opponent strip
   prints is derived from the permanents below it rather than typed in beside
   them -- which is the thing `../seat/` could not do, because the board under
   its strip was a dashed sketch.

   Card shorthand, unchanged from `../_state.js` so the two stay diffable:
   n=name cost tl=type line t=type f=frame tone pt kw=keywords rules
   land=produces  tapped sick cmd token  count=stack size  art=name in ../art/
   ability=available activated ability   playable=castable right now
   why=why it is NOT playable
   ======================================================================== */

const VIEWER = {
  pid: 0,
  name: "You",
  life: 34,
  start: 40,
  cmdrName: "Aesi, Tyrant of Gyre Strait",
  /* The portrait button's own three facts. `cmd: 0` puts Aesi on the
     battlefield, which is what makes the button read "In play" and carry no
     price -- see `cmdrState` below. */
  art: "aesi-tyrant-of-gyre-strait.jpg",
  cost: ["4", "G", "U"],
  tax: 2,
  lib: 72, hand: 6, gy: 3, exile: 1, cmd: 0,
  /* One entry per SOURCE, never per symbol: Thornwood Falls makes G or U, and
     counting it twice would claim mana that does not exist. logic/mana.ts. */
  mana: [{ sym: "G", open: 7 }, { sym: "U", open: 3 }, { sym: "G/U", open: 1 }, { sym: "C", open: 1 }],
  /* What a hovered Beast Within `{2}{G}` would take, as the ENGINE solves it --
     one green for the coloured pip and two of anything for the generic. Never
     arithmetic here; `logic/mana.ts` owns the payment and the orb only draws it.
     `../self/` reaches this through its `spending` review state; this round has
     no `s` walk, so the field is carried and `f.spending` is never set. */
  spend: { G: 1, U: 1, C: 1 },
  spendOn: "Beast Within",
  lands: [
    { n: "Forest", tl: "Basic Land — Forest", t: "land", f: "land", land: "G", art: "Forest", count: 7 },
    { n: "Island", tl: "Basic Land — Island", t: "land", f: "land", land: "U", art: "Island", count: 3 },
    { n: "Thornwood Falls", tl: "Land", t: "land", f: "land", land: "G/U", art: "Thornwood Falls",
      rules: "Thornwood Falls enters the battlefield tapped. When it enters, you gain 1 life." },
    { n: "Terramorphic Expanse", tl: "Land", t: "land", f: "land",
      ability: "{T}, Sacrifice: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle." },
  ],
  creatures: [
    { n: "Gyre Strait Leviathan", cost: "5UU", tl: "Creature — Leviathan", t: "creature", f: "U", pt: "7/7", kw: "Trample",
      rules: "Trample." },
    { n: "Aesi, Tyrant of Gyre Strait", cost: "4GU", tl: "Legendary Creature — Serpent", t: "creature", f: "gold", pt: "5/5", kw: "Trample", cmd: true,
      rules: "Trample. Whenever you play a land, draw a card. You may play an additional land on each of your turns.",
      art: "Aesi, Tyrant of Gyre Strait" },
    { n: "Elvish Visionary", cost: "1G", tl: "Creature — Elf Shaman", t: "creature", f: "G", pt: "1/1",
      rules: "When Elvish Visionary enters the battlefield, draw a card.", art: "Elvish Visionary" },
    { n: "Elemental", tl: "Token Creature — Elemental", t: "creature", f: "token", pt: "2/2", token: true, count: 2,
      art: "token:Elemental" },
    { n: "Acidic Slime", cost: "3GG", tl: "Creature — Ooze", t: "creature", f: "G", pt: "2/2", kw: "Deathtouch", sick: true,
      rules: "Deathtouch. When Acidic Slime enters the battlefield, destroy target artifact, enchantment or land.",
      art: "Acidic Slime" },
    { n: "Yavimaya Elder", cost: "1G", tl: "Creature — Human Druid", t: "creature", f: "G", pt: "1/2", sick: true,
      rules: "When Yavimaya Elder dies, you may search your library for up to two basic land cards.", art: "Yavimaya Elder" },
    { n: "Gyre Sage", cost: "1G", tl: "Creature — Elf Druid", t: "creature", f: "G", pt: "0/2", kw: "Evolve",
      rules: "Evolve. {T}: Add {G} for each +1/+1 counter on Gyre Sage.", art: "Gyre Sage" },
  ],
  other: [
    { n: "Zendikar's Roil", cost: "4G", tl: "Enchantment", t: "enchantment", f: "G",
      rules: "Whenever a land enters the battlefield under your control, create a 2/2 green Elemental creature token.",
      art: "Zendikar's Roil" },
  ],
};

/*
 * THE HAND, AT DECLARE-ATTACKERS, WITH THE RULES ACTUALLY APPLIED.
 *
 * Five of these six are sorcery-speed and the combat files are in combat, so
 * exactly ONE card in hand is castable there -- the instant. That is not a
 * convenience for the demo, it is what the engine's `unplayable_reason` would
 * really say, and it is worth getting right for two reasons. It makes the green
 * `--playable` rim mean something rather than being decoration on everything.
 * And it puts the round's two hardest items on the same six cards: the one live
 * card is the one that needs a target, and the five dim ones carry the
 * hover-only "why can't I play this" hint that has no home on a pad today.
 *
 * `03-abilities.html` is a main phase, so it re-flags them -- see that file.
 */
const HAND = [
  { n: "Vorel of the Hull Clade", cost: "1GU", tl: "Legendary Creature — Human Merfolk", t: "creature", f: "gold", pt: "1/4",
    rules: "{1}{G}{U}, {T}: Double the number of each kind of counter on target artifact, creature or land.",
    art: "Vorel of the Hull Clade",
    why: "Creatures are sorcery speed. You get this back in your second main phase." },
  { n: "Explosive Vegetation", cost: "3G", tl: "Sorcery", t: "sorcery", f: "G",
    rules: "Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
    art: "Explosive Vegetation",
    why: "A sorcery, and you are past your first main phase." },
  { n: "Garruk's Packleader", cost: "4G", tl: "Creature — Beast", t: "creature", f: "G", pt: "3/3",
    rules: "Whenever another creature with power 3 or greater enters the battlefield under your control, draw a card.",
    art: "Garruk's Packleader",
    why: "Creatures are sorcery speed. You get this back in your second main phase." },
  { n: "Nimble Mongoose", cost: "G", tl: "Creature — Mongoose", t: "creature", f: "G", pt: "1/1", kw: "Hexproof",
    rules: "Hexproof. Threshold — Nimble Mongoose gets +2/+2 as long as seven or more cards are in your graveyard.",
    art: "Nimble Mongoose",
    why: "Creatures are sorcery speed. You get this back in your second main phase." },
  { n: "Explore", cost: "1G", tl: "Sorcery", t: "sorcery", f: "G",
    rules: "You may play an additional land this turn. Draw a card.", art: "Explore",
    why: "A sorcery, and you are past your first main phase." },
  { n: "Beast Within", cost: "2G", tl: "Instant", t: "instant", f: "G",
    rules: "Destroy target permanent. Its controller creates a 3/3 green Beast creature token.",
    art: "Beast Within", playable: true },
];

/*
 * The three opponents, AS BOARDS rather than as summary numbers.
 *
 * `../seat/_seat.js` carried a `threat` object with the counts already worked
 * out, because there was nothing under the strip to work them out from. Here the
 * permanents are the fixture and `musterOf()` counts them, so the seat cannot
 * disagree with the board it is describing -- and `assert.js` re-derives the
 * same numbers a third way and fails the file if any of the three differ.
 */
const OPPS = [
  {
    pid: 1, name: "AI 1", who: "Apprentice", human: false,
    cmdrName: "Edgar Markov", art: "edgar-markov.jpg",
    life: 25, lib: 84, hand: 4, gy: 6, exile: 0, cmd: 1, tax: 0,
    lands: [
      { n: "Mountain", t: "land", land: "R", count: 2 },
      { n: "Scoured Barrens", t: "land", land: "W/B", tapped: true },
    ],
    creatures: [
      { n: "Vampire", t: "creature", pt: "1/1", power: 1, token: true, tapped: true, count: 2 },
      { n: "Vampire Neonate", t: "creature", pt: "0/3", power: 0 },
      { n: "Falkenrath Noble", t: "creature", pt: "2/2", power: 2, flying: true },
    ],
    other: [],
  },
  {
    pid: 2, name: "Marco", who: "Human", human: true,
    cmdrName: "Isperia, Supreme Judge", art: "isperia-supreme-judge.jpg",
    life: 31, lib: 79, hand: 5, gy: 2, exile: 0, cmd: 1, tax: 0,
    /* You cast a "look at target player's hand" at Marco two turns ago, so two
       of his five cards are in `hand_revealed` and his hand mark IS a control on
       the seat sheet. The other two seats' hands are not. */
    revealed: 2,
    lands: [
      { n: "Plains", t: "land", land: "W", count: 3 },
      { n: "Island", t: "land", land: "U", count: 2 },
    ],
    creatures: [
      { n: "Empyrean Eagle", t: "creature", pt: "2/3", power: 2, flying: true },
      { n: "Watcher of the Spheres", t: "creature", pt: "2/2", power: 2, flying: true },
    ],
    other: [{ n: "Favorable Winds", t: "enchantment" }],
  },
  {
    pid: 3, name: "Duelist", who: "Duelist", human: false,
    cmdrName: "Krenko, Mob Boss", art: "krenko-mob-boss.jpg",
    life: 18, lib: 88, hand: 3, gy: 9, exile: 2, cmd: 1, tax: 2,
    lands: [{ n: "Mountain", t: "land", land: "R", count: 4 }],
    creatures: [{ n: "Skirk Prospector", t: "creature", pt: "1/1", power: 1 }],
    other: [{ n: "Impact Tremors", t: "enchantment" }],
  },
];

/*
 * Commander damage TAKEN, per seat, per source. A matrix and not a list, because
 * the sources a seat has depend on how many seats are at the table.
 *
 * Two numbers are `../seat/_seat.js`'s deliberate departures from
 * `../handheld/_table.js` and they are kept: seat 3 has taken 16 from Edgar
 * rather than 12, which is the only way to put a seat past the warn threshold
 * (15) and see what the gauge does about it, and seat 2 has taken 3 rather than
 * 0 so the plate has a middling value as well as a zero and a near-lethal one.
 */
const DMG = {
  0: { 1: 8, 2: 0, 3: 0 },
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

/* The five phases, and the step the turn is actually sitting on.
   `../handheld/_handheld.js`'s collapse of the client's thirteen equal ticks;
   only the live one expands. See the note on `.info` in `_board.css` for why the
   thirteen do not fit here. */
const PHASES = [
  { id: "beginning", n: "Beginning", steps: ["Untap", "Upkeep", "Draw"] },
  { id: "main1", n: "Main 1", steps: [] },
  { id: "combat", n: "Combat", steps: ["Begin", "Attackers", "Blockers", "Damage", "End"] },
  { id: "main2", n: "Main 2", steps: [] },
  { id: "end", n: "End", steps: ["End", "Cleanup"] },
];

/* ===========================================================================
   2. HELPERS
   ======================================================================== */

const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* The slug `../art/manifest.json` actually uses. An apostrophe is a SEPARATOR,
   not a character to delete: the file is `garruk-s-packleader.jpg`, so stripping
   the apostrophe first yields `garruks-packleader` and a silently broken image.
   Four cards on this board state hit that, and a missing crop looks exactly like
   a card that genuinely has no printing. */
const ART = (name) => {
  if (!name) return null;
  const slug = String(name)
    .replace(/^token:/, "token-")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return "../art/" + slug + ".jpg";
};

const SYM_DIR = "../cards/symbols";

/** Tokenise a cost. Accepts the shorthand this round uses (`4GU`), Scryfall's
    braces (`{4}{G}{U}`), and hybrids either way (`W/U`, `{2/B}`). */
function tokens(cost) {
  if (!cost) return [];
  if (Array.isArray(cost)) return cost;
  const s = String(cost).replace(/[{}]/g, "");
  const out = [];
  let num = "";
  for (let i = 0; i < s.length; i += 1) {
    const ch = s[i];
    if (/[0-9]/.test(ch)) { num += ch; continue; }
    if (num && s[i] !== "/") { out.push(num); num = ""; }
    if (s[i + 1] === "/") {
      const a = num || ch;
      num = "";
      out.push(a + "/" + s[i + 2]);
      i += 2;
      continue;
    }
    out.push(ch);
  }
  if (num) out.push(num);
  return out;
}

/*
 * One published symbol.
 *
 * `../cards/symbols/` holds the 54 real Scryfall SVGs that `fetch_symbols.py`
 * pulled and that the shipped client now vendors to `frontend/public/symbols/`.
 * Using them rather than letters on coloured discs matters for two reasons
 * beyond looking right. A LETTER ON A DISC IS TEXT, AND TEXT HAS A FLOOR -- at
 * the sizes a mana cost wants to be a letter lands under 16px and `assert.js`
 * fails the file, correctly, because a 13px letter really is unreadable on a
 * 7-inch screen. And hybrids have no letter form at all: `{G/U}` as "GU" on one
 * disc is an invention, `G-U.svg` is the actual symbol.
 *
 * `alt` is empty and the element is `aria-hidden` because every cost that uses
 * this also carries a text form for anything reading.
 */
const symHTML = (tok) =>
  '<img class="sym" src="' + SYM_DIR + "/" + String(tok).replace("/", "-").toUpperCase() +
  '.svg" alt="" aria-hidden="true">';

/* A COST IS ONE WORD, wrapped in its own inline-flex so `{3}{B}` can never break
   across two lines the way it did in the rail -- a mana cost split down the
   middle reads as two different costs. The braces form is the accessible name. */
function costHTML(cost) {
  const t = tokens(cost);
  if (!t.length) return "";
  return '<span class="cost" aria-label="' + esc(t.map((x) => "{" + x + "}").join("")) + '">' +
    t.map(symHTML).join("") + "</span>";
}

/** The mana a single source can make, which is NOT the same shape as a cost:
    Thornwood Falls makes G *or* U, so it is one hybrid symbol rather than two
    pips claiming two mana that do not both exist. */
function producesHTML(str) {
  if (!str) return "";
  const inner = str.includes("/") ? symHTML(str) : tokens(str).map(symHTML).join("");
  return '<span class="cost" aria-label="' + esc("{" + str + "}") + '">' + inner + "</span>";
}

/* `SymbolText.tsx` swaps `{G}` inside oracle text for the published pip. Doing
   the same here is not decoration -- "{1}{G}{U}, {T}:" rendered as literal braces
   was the single worst-looking thing in the first board round, and an activated
   ability is exactly where it appears. */
function textHTML(s) {
  if (!s) return "";
  return esc(s).replace(/\{([^}]+)\}/g, (_, t) => symHTML(t));
}

const TYPE_GLYPH = {
  creature: "❖", land: "◈", sorcery: "✦", instant: "⚡",
  enchantment: "❋", artifact: "⬢", planeswalker: "✧",
};

const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
const pct = (n, d) => (d > 0 ? (n / d) * 100 : 0) + "%";

/* --- The marks -------------------------------------------------------------
   WHY THESE EXIST. It is a legibility argument, not a colour one -- ADR 0006.

   The shipped strip drops `.pile__label` at 16px: "Lib", "Hand", "GY" and "CMD"
   all go (`handheld.css:1758`), and what is left of a zone is a coloured chip
   with a number in it. A fixed order only helps somebody who has already learned
   the order, and the colour code has to be learned too. A shape can say it
   without being taught: a headstone is a graveyard, a fan of three cards is a
   hand, a face-down card is a library.

   They are SVG and not text characters on purpose -- a glyph in a font is a
   different picture on every machine, and three of these had no reliable
   character at all -- and they are pictures rather than words, so they are
   `aria-hidden` with the real name carried by the cell's `aria-label`.
-------------------------------------------------------------------------- */

const ICON = {
  creature: '<circle cx="8" cy="4.4" r="2.7"/><path d="M2.6 14.6c0-4.3 2.3-6.2 5.4-6.2s5.4 1.9 5.4 6.2z"/>',
  power: '<path d="M8 .6l2.9 4.8v5.4H5.1V5.4z"/><rect x="2.2" y="10.6" width="11.6" height="2.3" rx="1.15"/>',
  /* A land: a plot of ground, in perspective. A trapezoid because every other
     rectangle on the seat is a card, and orientation is the one difference this
     family of mockups has already ruled out. */
  land: '<path d="M1.4 13.8L4.4 5.4h7.2l3 8.4z"/>',
  /* Everything on the battlefield that is not a creature and not a land -- the
     artifacts and enchantments. A cut gem, which is neither the star nor the
     crown at 14px. */
  other: '<path d="M8 1.1l6.2 5.1-6.2 8.7-6.2-8.7z"/>',
  /* Commander damage: a crown. Twenty-one of these kills you and nothing else in
     the game does, so it gets a mark of its own. */
  crown: '<path d="M1.6 13.2L2.9 4.4 6 8.2 8 2.8l2 5.4 3.1-3.8 1.3 8.8z"/>',
  /* The commander tax: a coin. */
  tax: '<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8 4.2v7.6M6 6.1h4M6 9.9h4" stroke="currentColor" stroke-width="1.5" fill="none"/>',
  lib: '<rect x="3.2" y="1.6" width="9.6" height="12.8" rx="1.5"/><path d="M8 4.4l1.7 3.6L8 11.6 6.3 8z" fill="var(--chip-ink)"/>',
  hand: '<g transform="rotate(-22 8 13)"><rect x="1.9" y="4.2" width="4.8" height="9.2" rx="1.1"/></g><g transform="rotate(22 8 13)"><rect x="9.3" y="4.2" width="4.8" height="9.2" rx="1.1"/></g><rect x="5.6" y="2.6" width="4.8" height="10.8" rx="1.1"/>',
  gy: '<path d="M3.4 15V7.2a4.6 4.6 0 019.2 0V15z"/>',
  ex: '<rect x="3.2" y="1.8" width="9.6" height="12.4" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="3.4 2.6"/>',
  cmd: '<path d="M8 1l2.1 4.5L15 6.2l-3.6 3.4.9 4.9L8 12.2 3.7 14.5l.9-4.9L1 6.2l4.9-.7z"/>',
};

const ico = (name) =>
  '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false" fill="currentColor">' +
  ICON[name] + "</svg>";

/* ===========================================================================
   3. THE CARD FACE
   ---------------------------------------------------------------------------
   One face, three scales. See `.face--board` in `_board.css` for what a board
   card drops and why.
   ======================================================================== */

function faceHTML(c, opts) {
  opts = opts || {};
  const art = ART(c.art);
  const cls = [
    "face",
    "face--" + (c.f || "default"),
    opts.board ? "face--board" : "",
    c.tapped ? "face--tapped" : "",
    c.sick ? "face--sick" : "",
    c.ability || opts.badge ? "face--marked" : "",
    c.count > 1 ? "face--counted" : "",
    opts.rim ? "face--" + opts.rim : "",
    opts.cls || "",
  ].filter(Boolean).join(" ");

  const badge = opts.badge
    ? '<span class="face__badge face__badge--' + opts.badge.kind + '" data-name aria-label="' +
      esc(opts.badge.label) + '">' + opts.badge.mark + "</span>"
    : "";

  return (
    '<div class="' + cls + '" data-nm="' + esc(c.n) + '">' +
      (art
        ? '<img class="face__art" src="' + art + '" alt="" loading="lazy">'
        /* A crop this repo has not fetched and a printing that genuinely has no
           art look identical, which is `logic/cardArt.ts`'s own problem: it
           returns `undefined` for the first and `null` for the second. Three
           cards on this board are in the first case -- see README.md. */
        : '<div class="face__noart" aria-hidden="true">' + (TYPE_GLYPH[c.t] || "◇") + "</div>") +
      '<div class="face__head">' +
        '<span class="face__glyph" aria-hidden="true">' + (TYPE_GLYPH[c.t] || "◇") + "</span>" +
        '<span class="face__name">' + (c.cmd ? "♛ " : "") + esc(c.n) + "</span>" +
        (c.cost ? '<span class="face__cost">' + costHTML(c.cost) + "</span>" : "") +
      "</div>" +
      '<div class="face__foot">' +
        (c.land ? '<span class="face__land">' + producesHTML(c.land) + "</span>" : "") +
        (c.pt ? '<span class="face__pt">' + esc(c.pt) + "</span>" : "") +
      "</div>" +
      (c.count > 1 ? '<span class="face__count" data-name aria-label="' + esc(c.count + " of them") + '">×' + c.count + "</span>" : "") +
      (c.ability ? '<span class="face__rune" data-name aria-label="Has an activated ability">↻</span>' : "") +
      badge +
    "</div>"
  );
}

/* ===========================================================================
   4. THE OPPONENT SEAT -- `../seat/06-muster.html`
   ======================================================================== */

/** How many actual objects a lane holds, counting a x7 stack as seven. This is
    what a "12 lands" readout means, and getting it from `count` rather than
    `length` is the difference between the readout and the row agreeing. */
const countOf = (cards) => cards.reduce((n, c) => n + (c.count || 1), 0);
const countIf = (cards, f) => cards.reduce((n, c) => n + (f(c) ? (c.count || 1) : 0), 0);

/*
 * THE FIVE FACTS THE SEAT IS ORGANISED AROUND, derived rather than declared.
 *
 *     how many lands       how many of them are untapped
 *     how many creatures   how many of them are untapped
 *     how many other permanents
 *
 * Read against the shipped strip that list is almost entirely missing: lands are
 * not in the model at all and `manaOpen` has been standing in for them, which
 * counts UNTAPPED SOURCES and is silent about how many exist -- so a seat at five
 * lands with none open and a seat at one land read identically.
 */
function musterOf(seat) {
  return {
    lands: countOf(seat.lands),
    landsUp: countIf(seat.lands, (c) => !c.tapped),
    creatures: countOf(seat.creatures),
    creaturesUp: countIf(seat.creatures, (c) => !c.tapped),
    power: seat.creatures.reduce((n, c) => n + (c.power || 0) * (c.count || 1), 0),
    fliers: countIf(seat.creatures, (c) => c.flying),
    other: countOf(seat.other),
  };
}

/** Who could have hit this seat with a commander, in seating order from you. */
function sources(pid) {
  return [0, 1, 2, 3]
    .filter((p) => p !== pid)
    .map((p) => ({ pid: p, n: (DMG[pid] || {})[p] || 0, who: NAMES[p], cmdr: CMDRS[p] }));
}

/**
 * The zones, in the shipped order.
 *
 * `PlayerOrb.tsx` already argues the case for the library: "hidden information,
 * and a control that does nothing when clicked is worse than no control". An
 * opponent's HAND is the same fact -- `types.ts` sends `hand: null` for every
 * seat but the viewer -- unless `hand_revealed` is non-empty, which is Marco's
 * case here. Exile appears the moment anything is exiled and is NOT a fixed
 * slot, so a seat shows four marks or five, which is the reflow the row has to
 * survive.
 */
function zonesOf(seat) {
  const z = [
    { name: "library", label: "Library", icon: "lib", kind: "lib", count: seat.lib, peek: false },
    { name: "hand", label: "Hand", icon: "hand", kind: "hand", count: seat.hand, peek: !!seat.revealed },
    { name: "graveyard", label: "Graveyard", icon: "gy", kind: "gy", count: seat.gy, peek: true },
  ];
  if (seat.exile > 0) z.push({ name: "exile", label: "Exile", icon: "ex", kind: "ex", count: seat.exile, peek: true });
  z.push({ name: "command", label: "Command zone", icon: "cmd", kind: "cmd", count: seat.cmd, peek: true });
  return z;
}

/* One function for all three counts, because they are one object drawn three
   times: an icon, `untapped/total`, and a ground filled to that fraction. `open`
   is null for the cell that has no tapped state to draw. */
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

/* Eight pips and then a count: past eight the extra pips say nothing a reader
   can use, and the cap costs resolution and never information because the COUNT
   is on the creature cell beside them. */
const MAX_PIPS = 8;

function detailCell(m) {
  const n = Math.min(m.creatures, MAX_PIPS);
  let up = m.creaturesUp;
  let fly = m.fliers;
  const out = [];
  for (let i = 0; i < n; i += 1) {
    /* Untapped first and fliers first, so the pips a player cares about are the
       ones that survive the cap. */
    const isUp = up-- > 0;
    const isFly = fly-- > 0;
    out.push('<span class="tpip' + (isUp ? " tpip--up" : "") + (isFly ? " tpip--fly" : "") + '"></span>');
  }
  const more = m.creatures > MAX_PIPS ? '<span class="pips__more">+' + (m.creatures - MAX_PIPS) + "</span>" : "";
  const label = (m.fliers ? plural(m.fliers, "flier") + ", " : "") + m.power + " power on board";
  return (
    '<span class="perm perm--detail" data-cell data-name aria-label="' + esc(label) + '">' +
      '<span class="pips">' + (out.join("") || '<span class="pips__more">none</span>') + more + "</span>" +
      '<span class="perm__pow">' + ico("power") + "<span>" + m.power + "</span></span>" +
    "</span>"
  );
}

function seatHTML(seat, flags) {
  flags = flags || {};
  const m = musterOf(seat);
  const cls = [
    "seat",
    flags.active ? "seat--active" : "",
    flags.targetable ? "seat--targetable" : "",
  ].filter(Boolean).join(" ");

  /* The ticks close from the right, stacked and each offset by the ones outside
     it, so the track reads as one bar eaten from both ends. */
  let offset = 0;
  const all = sources(seat.pid);
  const ticks = all
    .filter((s) => s.n > 0)
    .map((s) => {
      const w = (Math.min(s.n, LETHAL) / LETHAL) * 100;
      const html =
        '<span class="tick' + (s.n >= WARN ? " tick--warn" : "") + '" data-name ' +
        'style="--w:' + w + "%; right:" + offset + '%" aria-label="' +
        esc(s.n + " of " + LETHAL + " from " + s.who + " — " + s.cmdr) + '"></span>';
      offset += w;
      return html;
    })
    .join("");

  const worst = all.slice().sort((a, b) => b.n - a.n)[0] || { n: 0, who: "nobody" };
  const gaugeLabel =
    seat.life + " life of 40 — " +
    (worst.n === 0 ? "no commander damage yet"
      : "worst commander damage " + worst.n + " of " + LETHAL + " from " + worst.who);

  const zone = zonesOf(seat).map((z) =>
    '<span class="zmark zmark--' + z.kind + (z.count > 0 ? "" : " zmark--empty") + '"' +
    ' data-cell data-name data-testid="pile-' + seat.pid + "-" + z.name + '"' +
    ' aria-label="' + esc(z.label + ": " + z.count + (z.peek ? " — opens in the seat sheet" : "")) + '">' +
    ico(z.icon) + z.count + "</span>"
  ).join("");

  /* THE SEAT IS THE TARGET. It takes the player-target action when one is legal
     and otherwise opens the seat sheet -- through `onSelect` and never a
     `data-action-id`, which `e2e/cycle3.spec.ts` asserts the action panel owns
     alone. 332x96 of target, which clears every floor in the round. */
  return (
    '<button class="' + cls + '" type="button" data-stop="seat-' + seat.pid + '"' +
      ' data-testid="player-' + seat.pid + '" data-seat="' + seat.pid + '">' +
      '<img class="seat__ground" src="../art/' + seat.art + '" alt="" aria-hidden="true">' +
      '<span class="seat__veil" aria-hidden="true"></span>' +
      (flags.active ? '<span class="seat__pri"></span>' : "") +

      '<span class="seat__win"><img src="../art/' + seat.art + '" alt="" aria-hidden="true"></span>' +

      '<span class="seat__head">' +
        '<span class="seat__name">' + esc(seat.name) + "</span>" +
        '<span class="seat__cmdr">' + esc(seat.cmdrName) + "</span>" +
      "</span>" +

      '<span class="gauge" data-cell data-name style="--fill:' +
        (Math.min(seat.life / 40, 1) * 100) + '%" aria-label="' + esc(gaugeLabel) + '">' +
        ticks +
        '<span class="seat__life tabular" data-testid="life-' + seat.pid + '">' + seat.life + "</span>" +
        '<span class="gauge__dmg' + (worst.n >= WARN ? " gauge__dmg--warn" : "") +
          (worst.n === 0 ? " gauge__dmg--zero" : "") + '">' + ico("crown") + worst.n + "</span>" +
      "</span>" +

      '<span class="seat__perms">' +
        permCell("land", "land", m.lands, m.landsUp,
          plural(m.lands, "land") + " — " + m.landsUp + " untapped, " + (m.lands - m.landsUp) + " tapped") +
        permCell("creature", "creature", m.creatures, m.creaturesUp,
          plural(m.creatures, "creature") + " — " + m.creaturesUp + " untapped, " + (m.creatures - m.creaturesUp) + " tapped") +
        permCell("other", "other", m.other, null,
          m.other === 0 ? "No artifacts or enchantments"
          : m.other === 1 ? "1 artifact or enchantment"
          : m.other + " artifacts or enchantments") +
        detailCell(m) +
      "</span>" +
      '<span class="seat__zones">' + zone + "</span>" +
    "</button>"
  );
}

/* ===========================================================================
   5. THE VIEWER'S HALF
   ======================================================================== */

/* ===========================================================================
   THE PLAYER ORB -- `../self/03-plinth.html`, carried over
   ---------------------------------------------------------------------------
   `../self/` drew five directions for exactly this panel, in exactly this
   palette, against three real muster seats and ghosted lanes. Plinth is the one
   picked, and it arrives here unchanged in idea: the commander's art as the
   panel's ground, the portrait as the button that casts them, and life as a dial
   stamped over the portrait's corner.

   THREE THINGS THIS SCREEN LETS IT BE CHECKED AGAINST, none of which its own
   round could:

     1. THE POD ARGUMENT. Plinth exists because "a pod today is three decks and a
        control panel". Here the three decks are drawn six pixels above it, so
        whether the fourth seat now reads as a seat is a thing you can look at.
     2. THE CHIP-SIZE ARGUMENT. `../self/` reasoned its way from 72px zone chips
        down to a seat's 21px by imagining them beside an opponent's. Both are on
        screen now.
     3. THE CROP. Its stated price was showing 40% of the painting's width. This
        layout's shorter column refunds most of that -- see `_board.css`.

   `f` is `{ active, priority, out, noart, spending }` and comes from the mount.
   ======================================================================== */

/** Converted mana cost. `{4}{G}{U}` is six: the generic is worth its number and
    every coloured pip is worth one. */
const cmv = (cost) => cost.reduce((n, tok) => n + (/^\d+$/.test(tok) ? +tok : 1), 0);

const manaTotal = (v) => v.mana.reduce((n, g) => n + g.open, 0);

/** The commander's cost, plus the tax if any is owed. The tax rides beside the
    cost it modifies, which is the only arrangement in which a surcharge means
    anything -- `PlayerOrb.tsx` puts it here for the same reason. */
const cmdrCost = (v) =>
  v.cost.map(symHTML).join("") + (v.tax > 0 ? '<span class="tax tabular">+' + v.tax + "</span>" : "");

/**
 * WHAT THE PORTRAIT BUTTON IS DOING, which is the one piece of state on this
 * panel that decides whether a control does anything.
 *
 *   board   on the battlefield                        -- not a cast, nothing to price
 *   ready   in the command zone, and you can pay      -- `--playable`, green
 *   short   in the command zone, and you cannot       -- priced, not lit
 *
 * CASTABLE AND AFFORDABLE ARE TWO DIFFERENT THINGS. The shipped orb lights the
 * plinth on `playableOids`, which already folds the payment in, so this computes
 * the same split from the fixture rather than inventing a third rule.
 *
 * ON ALL THREE FILES HERE THE STATE IS `board`: Aesi is on the battlefield in
 * this fixture, so the button is `aria-disabled`, carries no price, and says
 * "In play". That is worth naming rather than leaving as a coincidence -- it is
 * the state in which plinth's portrait is NOT a control, and it is the state a
 * board round is most often in. `../self/` reaches `ready` and `short` through
 * its `s` walk; this round has no `s` walk, so those two are unexercised here
 * and the code path is kept rather than trimmed so that stays visible.
 */
function cmdrState(v, f) {
  if (f.out) return { word: "Out", long: "Eliminated", cls: "out", cast: false };
  if (v.cmd > 0) {
    const need = cmv(v.cost) + v.tax;
    return manaTotal(v) >= need
      ? { word: "Ready", long: "Ready to cast", cls: "ready", cast: true }
      : { word: "Need " + need, long: "In the command zone — " + need + " mana to cast",
          cls: "short", cast: true };
  }
  return { word: "In play", long: "On the battlefield", cls: "board", cast: false };
}

/**
 * The portrait, as the control it is.
 *
 * NEVER `disabled`, always `aria-disabled`. A disabled control dispatches no
 * mouse events, so "the full card is one hover away in the reader" would be
 * false for a commander you cannot currently cast -- which is most of the game.
 * `../orb/README.md` records the fix; the click is gated in the handler instead.
 *
 * `data-card` rather than a special case: the portrait names the same card the
 * mat draws, so pointing at it fills the rail's reader like anything else. That
 * is a join `../self/` could not have -- it had no reader to fill.
 */
function winButton(v, f) {
  const st = cmdrState(v, f);
  const cls = ["win", "win--" + st.cls, f.noart ? "win--empty" : ""].filter(Boolean).join(" ");
  const label = v.cmdrName + " — " + st.long +
    (st.cast ? ", costs " + v.cost.join("") + (v.tax ? " plus " + v.tax + " commander tax" : "") : "");

  return (
    '<button type="button" class="' + cls + '"' +
      (st.cast ? "" : ' aria-disabled="true"') +
      ' data-card="' + esc(v.cmdrName) + '"' +
      /* `data-name` but NOT `data-cell`: the portrait is the picture, not one of
         the panel's uniform cells. Muster's own window carries `data-name`
         alone for the same reason. */
      ' data-name data-testid="commander-0" aria-label="' + esc(label) + '">' +
      (f.noart ? ico("cmd") : '<img src="../art/' + v.art + '" alt="" aria-hidden="true">') +
      /* NO `win__who` STRIP. `../self/03-plinth.html` draws the player's name
         across the top of the portrait for pod symmetry with a muster seat's
         head row; at 128px of picture rather than 250 that is 21px spent on a
         word the information strip already says twice about a panel nobody could
         mistake for somebody else's. See `.plinth` in `_board.css`. */
      '<span class="win__cap">' +
        (st.cast ? cmdrCost(v) : "") +
        '<span class="win__st">' + st.word + "</span>" +
      "</span>" +
    "</button>"
  );
}

/**
 * The mana groups: one mark per KIND with a count, never one per mana.
 *
 * When a castable card is hovered the group shows what you would have LEFT and a
 * faint negative for what goes. Which lands those are comes from the engine's
 * solved payment, never from arithmetic here; see `logic/mana.ts`.
 */
function manaCells(v, f) {
  if (!v.mana.length) {
    return '<span class="mgrp mgrp--none" data-cell data-name aria-label="No mana available">—</span>';
  }
  return v.mana.map((g) => {
    const spend = f.spending ? (v.spend[g.sym] || 0) : 0;
    const left = g.open - spend;
    const hybrid = g.sym.indexOf("/") >= 0;
    const mark = hybrid ? '<span class="mgrp__any" aria-hidden="true"></span>' : symHTML(g.sym);
    const label = (hybrid ? g.open + " sources of green or blue" : g.open + " " + g.sym) +
      (spend ? " — " + v.spendOn + " taps " + spend : "");
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

/**
 * The five zones, as chips inside targets.
 *
 * THE LIBRARY IS NEVER A BUTTON, whoever is asking: it is hidden information,
 * and `PlayerOrb.tsx:96-101` argues that a control which does nothing when
 * clicked is worse than no control. The other four have something real behind
 * them -- your hand is your hand, your graveyard and exile are public, your
 * command zone is where you cast from -- which is where muster's trade stops
 * travelling. It demoted an OPPONENT's five marks to plain cells and argued it
 * properly: 96px will not hold a 44px row and the battlefield row both.
 *
 * `data-name` and the accessible name go on the BUTTON, because that is the
 * control; `data-cell` goes on the chip, because that is the geometry. On an
 * opponent's seat there is no button and the chip carries both -- the same
 * finding stated in markup, and both are on this screen at once.
 */
function viewerZones(v) {
  const z = [
    { name: "library", label: "Library", icon: "lib", kind: "lib", count: v.lib, peek: false },
    { name: "hand", label: "Hand", icon: "hand", kind: "hand", count: v.hand, peek: true },
    { name: "graveyard", label: "Graveyard", icon: "gy", kind: "gy", count: v.gy, peek: true },
  ];
  /* Exile appears the moment anything is exiled and is NOT a fixed slot -- yours
     has one card in it, so this row is five marks here and would be four on an
     empty exile. That is the reflow the row has to survive. */
  if (v.exile > 0) z.push({ name: "exile", label: "Exile", icon: "ex", kind: "ex", count: v.exile, peek: true });
  z.push({
    name: "command", label: "Command zone", icon: "cmd", kind: "cmd", count: v.cmd, peek: true,
    note: v.cmd === 0 ? " — Aesi is on the battlefield" : "",
  });
  return z;
}

function zoneMarks(v) {
  return viewerZones(v).map((z) => {
    const isBtn = z.peek;
    const cls = [
      "zmark", "zmark--" + z.kind,
      z.count > 0 ? "" : "zmark--empty",
      isBtn ? "" : "zmark--flat",
    ].filter(Boolean).join(" ");
    const label = z.label + ": " + z.count + (z.note || "") + (isBtn ? " — opens" : " — hidden information");
    const chip =
      '<span class="' + cls + '" data-cell' +
        (isBtn ? "" : ' data-name data-testid="pile-0-' + z.name + '" aria-label="' + esc(label) + '"') +
      ">" + ico(z.icon) + z.count + "</span>";
    if (!isBtn) return chip;
    return (
      '<button type="button" class="zhit" data-name data-testid="pile-0-' + z.name + '"' +
        ' aria-label="' + esc(label) + '">' + chip + "</button>"
    );
  });
}

/**
 * The viewer's life, said in full and said only about life.
 *
 * `../self/` keeps this separate from the opponents' gauge label, which still
 * names the commander damage on their gauges. A shared label that mentioned
 * damage would put the channel back on this panel through the accessible name --
 * the same channel arriving by a quieter door -- and an accessible name that
 * describes something the sighted reader cannot see is its own defect.
 */
const lifeLabel = (v, f) => (f.out ? "Eliminated" : v.life + " life of " + v.start);

function orbHTML(f) {
  const v = VIEWER;
  const cls = ["orb", f.active ? "orb--active" : "", f.out ? "orb--out" : ""]
    .filter(Boolean).join(" ");
  const marks = zoneMarks(v);

  return (
    '<div class="' + cls + '" data-testid="player-0">' +
      (f.noart ? "" : '<img class="orb__ground" src="../art/' + v.art + '" alt="" aria-hidden="true">') +
      '<span class="orb__veil' + (f.noart ? " orb__veil--flat" : "") + '" aria-hidden="true"></span>' +
      (f.priority ? '<span class="orb__pri" data-name aria-label="You hold priority"></span>' : "") +

      '<div class="plinth">' +
        winButton(v, f) +
        '<span class="dial" data-cell data-name style="--fill:' +
          pct(Math.min(v.life, v.start), v.start) + '" aria-label="' + esc(lifeLabel(v, f)) + '">' +
          '<span class="dial__hole" aria-hidden="true"></span>' +
          '<span class="dial__n tabular">' + (f.out ? "OUT" : v.life) + "</span>" +
        "</span>" +
      "</div>" +

      '<div class="name">' + esc(v.cmdrName) + "</div>" +

      '<div class="slack"></div>' +

      '<div class="mana">' + manaCells(v, f) + "</div>" +

      '<div class="zones">' +
        '<div class="zones__row">' + marks.slice(0, 3).join("") + "</div>" +
        '<div class="zones__row">' + marks.slice(3).join("") + "</div>" +
      "</div>" +
    "</div>"
  );
}

/*
 * The lanes.
 *
 * `opts.mark(card)` is how a file paints the board from its own list -- it
 * returns `{rim, badge}` or nothing, and it is the ONLY hook the three files
 * have into the board. That is deliberate: the round's claim is that one rail
 * grammar answers three decisions, and a file that could rebuild the board would
 * be able to hide a failure of that claim by redrawing around it.
 */
function laneHTML(cards, mark) {
  return (
    '<div class="lane__cards" data-fan>' +
    cards.map((c) => {
      const m = (mark && mark(c)) || {};
      return (
        '<button class="lane__stop" type="button" data-stop="perm-' + esc(c.n) + '"' +
          ' data-card="' + esc(c.n) + '" style="border:0;padding:0;background:none">' +
          faceHTML(c, { board: true, rim: m.rim, badge: m.badge }) +
        "</button>"
      );
    }).join("") +
    "</div>"
  );
}

function boardHTML(mark, flags) {
  return (
    '<div class="mine">' +
      orbHTML(flags) +
      '<div class="lanes">' +
        '<div class="lane lane--creatures">' + laneHTML(VIEWER.creatures, mark) + "</div>" +
        '<div class="lane lane--other">' + laneHTML(VIEWER.other, mark) + "</div>" +
        '<div class="lane lane--lands">' + laneHTML(VIEWER.lands, mark) + "</div>" +
      "</div>" +
    "</div>"
  );
}

/* The hand. `playable` is set per file, because whether a sorcery is castable is
   a fact about the STEP and the three files are in three different ones. */
function handHTML(playableOf) {
  return (
    '<div class="foot">' +
      '<div class="tools">' +
        '<button class="tool" type="button" data-name aria-label="Sound">&#128266;</button>' +
        '<button class="tool" type="button" data-name aria-label="Undo">&#8634;</button>' +
        '<button class="tool" type="button" data-name aria-label="Concede">&#10005;</button>' +
      "</div>" +
      '<div class="hand" data-fan>' +
        HAND.map((c) => {
          const ok = playableOf ? playableOf(c) : !!c.playable;
          return (
            '<button class="lane__stop" type="button" data-stop="hand-' + esc(c.n) + '"' +
              ' data-card="' + esc(c.n) + '" style="border:0;padding:0;background:none">' +
              faceHTML(c, { cls: ok ? "face--playable" : "face--unplayable" }) +
            "</button>"
          );
        }).join("") +
      "</div>" +
    "</div>"
  );
}

/* ===========================================================================
   6. THE GAME INFORMATION STRIP
   ======================================================================== */

function infoHTML(spec) {
  const phases = PHASES.map((p, i) => {
    const live = p.id === spec.phase;
    const steps = live && p.steps.length
      ? '<span class="ph__steps">' + p.steps.map((s, j) =>
          '<span class="ph__step' + (j === spec.step ? " ph__step--now" : "") + '">' + esc(s) + "</span>"
        ).join("") + "</span>"
      : "";
    return (
      (i ? '<span class="ph__sep" aria-hidden="true">·</span>' : "") +
      '<span class="ph' + (live ? " ph--live" : "") + '">' +
        '<span class="ph__n">' + esc(p.n) + "</span>" + steps +
      "</span>"
    );
  }).join("");

  return (
    '<div class="info" data-testid="game-info">' +
      '<span class="info__turn">Turn <b>' + spec.turn + "</b></span>" +
      '<span class="info__phases">' + phases + "</span>" +
      '<span class="info__who">' +
        '<span class="info__active">' + esc(NAMES[spec.active]) + "<b>&#8217;s turn</b></span>" +
        '<span class="info__pri">' + esc(NAMES[spec.priority]) + " has priority</span>" +
      "</span>" +
    "</div>"
  );
}

/* ===========================================================================
   7. THE READER, AND THE TWO HOLDS
   ======================================================================== */

/** Every card on the screen, by name, so a rail row can name one with a string
    and the reader can find it. Built once, from the same fixture the board is
    drawn from, so the two cannot drift. */
const CARDS = {};
for (const c of [].concat(VIEWER.lands, VIEWER.creatures, VIEWER.other, HAND)) CARDS[c.n] = c;

/*
 * The reader body: the card, its type line, its rules, and -- when it has one --
 * why you cannot cast it.
 *
 * `CardPreview`'s `preview__facts` list does not travel: the keywords are in the
 * rules text, the status is the tap state and the lane it is in, the controller
 * is whose mat it is on, and the artist is not why anyone opens this.
 */
function readerBody(c, big) {
  if (!c) {
    return '<span class="reader__hint">Point at a card to read it</span>';
  }
  const art = ART(c.art);
  /* The hold gets the whole card because it owns the screen while it is up. The
     rail gets the window, because at 227px a card frame would be smaller than the
     board card it is helping you read -- see `.reader__art` in `_board.css`. */
  const pt = c.pt ? '<span class="reader__pt">' + esc(c.pt) + "</span>" : "";
  const picture = big
    ? faceHTML(c, {})
    : art
      ? '<div class="reader__art"><img src="' + art + '" alt="" aria-hidden="true">' + pt + "</div>"
      : '<div class="reader__art reader__art--empty"><span aria-hidden="true">' +
        (TYPE_GLYPH[c.t] || "◇") + "</span>" + pt + "</div>";
  return (
    picture +
    '<div class="reader__body">' +
      '<div class="reader__nm">' + (c.cmd ? "♛ " : "") + esc(c.n) +
        (c.cost ? " " + costHTML(c.cost) : "") + "</div>" +
      '<div class="reader__tl">' + esc(c.tl || "") + "</div>" +
      (c.rules ? '<div class="reader__rules">' + textHTML(c.rules) + "</div>" : "") +
      (c.ability ? '<div class="reader__rules">' + textHTML(c.ability) + "</div>" : "") +
      (c.why ? '<div class="reader__why">' + esc(c.why) + "</div>" : "") +
    "</div>"
  );
}

const stackHold = (stack) =>
  '<div class="over over--stack" id="hold-stack" hidden>' +
    '<p class="over__head">B to close</p>' +
    (stack.length
      ? '<div class="stacklist">' +
        stack.map((s, i) =>
          '<div class="sitem' + (i === 0 ? " sitem--top" : "") + '"><b>' + esc(s.name) +
          "</b> <span>" + esc(s.note) + "</span></div>"
        ).join("") +
        "</div>"
      : '<p class="reader__hint">Nothing on the stack</p>') +
  "</div>";

/* ===========================================================================
   8. THE MOUNT
   ---------------------------------------------------------------------------
   A file hands over the state of the game, its list, its commit bar, and the
   wiring for both.
   ======================================================================== */

const BOARD = {
  spec: null,
  /* WHAT THE READER IS SHOWING, held as a name rather than as DOM, because every
     file re-renders by rebuilding markup and a reader pointing at a destroyed
     node is the same silent-failure shape `../handheld/assert.js` grew a gate
     for. */
  reading: null,

  mount(spec) {
    BOARD.spec = Object.assign({
      turn: 8, active: 0, priority: 0, phase: "combat", step: 1,
      stack: [], hints: "", mark: null, playable: null, read: null,
    }, spec);
    BOARD.reading = BOARD.spec.read || null;
    BOARD.render();
    addEventListener("resize", BOARD.fit);
    addEventListener("keydown", BOARD.key);
  },

  render() {
    const spec = BOARD.spec;
    document.getElementById("root").innerHTML =
      '<div class="bezel">' +
        '<div class="deck">' +
          infoHTML(spec) +
          '<div class="play">' +
            '<div class="opps" data-testid="opponents">' +
              OPPS.map((s) => '<div class="mat">' + seatHTML(s, {
                active: s.pid === spec.active,
                targetable: spec.targetSeats && spec.targetSeats.indexOf(s.pid) >= 0,
              }) + "</div>").join("") +
            "</div>" +
            /* WHOSE TURN IT IS AND WHO HOLDS PRIORITY ARE TWO DIFFERENT FACTS
               and the orb draws them two ways: `--active` is the astral inset
               ring, `priority` is the tick on the top edge. `02` is the file
               that proves they are separate -- it is Edgar's turn and yours is
               the decision, so the orb has the tick and not the ring. The
               shipped board runs the two together into one highlighted name. */
            boardHTML(spec.mark, {
              active: spec.active === 0,
              priority: spec.priority === 0,
              out: false,
              noart: false,
              spending: false,
            }) +
          "</div>" +
          '<div class="rail" data-testid="rail">' +
            '<div class="reader" data-testid="reader">' + readerBody(CARDS[BOARD.reading]) + "</div>" +
            '<div class="acts"><div class="list" data-testid="action-list">' + spec.list + "</div></div>" +
            '<div class="commit">' + spec.commit +
              (spec.hints ? '<div class="hints">' + spec.hints + "</div>" : "") +
            "</div>" +
          "</div>" +
          handHTML(spec.playable) +
          '<div class="over over--card" id="hold-card" hidden>' +
            '<p class="over__head">B to close</p>' +
            '<div class="reader">' + readerBody(CARDS[BOARD.reading], true) + "</div>" +
          "</div>" +
          stackHold(spec.stack) +
        "</div>" +
        '<div class="bezel__tag" id="tag"></div>' +
      "</div>";

    BOARD.wireReader();
    if (spec.wire) spec.wire(document.querySelector(".deck"));
    BOARD.tag();
    BOARD.fit();
  },

  /*
   * THE READER FOLLOWS THE POINTER AND THE RING, and that is the whole of the
   * interaction the extra 234px bought.
   *
   * Anything carrying `data-card` names a card: a board face, a hand card, or a
   * row in the rail. `../rail/` could not do this at all -- its board was a
   * sketch with no cards in it -- and it is the reason a board face here can
   * afford to ellipsise a name.
   */
  wireReader() {
    const deck = document.querySelector(".deck");
    deck.addEventListener("pointerover", (ev) => {
      const el = ev.target.closest("[data-card]");
      if (el && deck.contains(el)) BOARD.read(el.dataset.card);
    });
    deck.addEventListener("focusin", (ev) => {
      const el = ev.target.closest("[data-card]");
      if (el) BOARD.read(el.dataset.card);
    });
  },

  /** Repaint the reader in place. Not a re-render: rebuilding the rail under a
      pointer that is mid-hover is how a list loses the row it is on. */
  read(name) {
    if (!CARDS[name] || BOARD.reading === name) return;
    BOARD.reading = name;
    const el = document.querySelector(".rail .reader");
    if (el) el.innerHTML = readerBody(CARDS[name]);
    const hold = document.querySelector("#hold-card .reader");
    if (hold) hold.innerHTML = readerBody(CARDS[name], true);
  },

  /**
   * Paint one board card from the rail.
   *
   * `rim` is one of staged / blocking / aimed / incoming and is the SAME token
   * the matching rail row uses, which is the point: a creature staged to attack
   * is amber in the list and amber on the mat, and the player never has to work
   * out which row is which card.
   */
  rim(name, rim, badge) {
    /* THE BOARD, AND NOT THE READER. Scoped to `.play` and `.foot` because the
       card hold draws a `.face` with the same `data-nm` on it, so an unscoped
       selector painted the amber rim on the enlarged card as well -- which reads
       as "this card is staged" on a surface whose whole job is to show what a
       card IS. A rim is a fact about a permanent on the battlefield; a reader is
       a picture of one. */
    const board = document.querySelectorAll(
      '.play .face[data-nm="' + CSS.escape(name) + '"], .foot .face[data-nm="' + CSS.escape(name) + '"]'
    );
    for (const face of board) {
      for (const k of ["staged", "blocking", "aimed", "incoming"]) face.classList.remove("face--" + k);
      if (rim) face.classList.add("face--" + rim);
      const old = face.querySelector(".face__badge");
      if (old) old.remove();
      /* The head's left padding is a function of whether a mark is in that
         corner, so it has to be re-decided every time one arrives or leaves --
         and an `.face--ability` card keeps it either way. */
      face.classList.toggle("face--marked", !!badge || !!face.querySelector(".face__rune"));
      if (badge) {
        face.insertAdjacentHTML("beforeend",
          '<span class="face__badge face__badge--' + badge.kind + '" data-name aria-label="' +
          esc(badge.label) + '">' + badge.mark + "</span>");
      }
    }
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
    /* 26px across for the bezel's shadow rings, 40 down for the caption under
       them. The deck is centred by `.bezel` and scaled about its own centre, so
       nothing here has to know where it ended up. */
    BOARD.scale = Math.max(0.3, Math.min(2,
      Math.min((innerWidth - 26) / 1280, (innerHeight - 40) / 800)));
    el.style.transform = "scale(" + BOARD.scale + ")";
    BOARD.lay();
  },

  /*
   * THE LANE OVERLAP, MEASURED.
   *
   * `step = min(cardWidth + gap, (laneWidth - cardWidth) / (n - 1))`, written to
   * `--step` on the lane, and `_board.css` turns it into a margin. A lane that
   * fits its cards gets a plain 5px gutter; one that does not overlaps by exactly
   * as much as it has to and no more.
   *
   * `clientWidth` and `offsetWidth` are untransformed layout values, so the
   * bezel's `scale()` does not enter into this -- which is the same trap
   * `../seat/assert.js` fell into when it divided a font size by the scale.
   */
  lay() {
    const GAP = 5;
    for (const lane of document.querySelectorAll("[data-fan]")) {
      const kids = lane.children;
      if (kids.length < 2) continue;
      const w = kids[0].offsetWidth;
      const step = Math.min(w + GAP, (lane.clientWidth - w) / (kids.length - 1));
      lane.style.setProperty("--step", step + "px");
    }
  },

  tag(extra) {
    const tag = document.getElementById("tag");
    if (!tag) return;
    tag.innerHTML =
      "<b>" + esc(BOARD.spec.title) + "</b> · 1280×800 @ " + Math.round(BOARD.scale * 100) + "%" +
      " · keys: <b>o</b> card hold · <b>k</b> stack hold · <b>r</b> reset · <b>m</b> measure" +
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
    if (k === "o") BOARD.hold("hold-card");
    else if (k === "k") BOARD.hold("hold-stack");
    else if (k === "escape" || k === "b") {
      document.getElementById("hold-card").hidden = true;
      document.getElementById("hold-stack").hidden = true;
    } else if (k === "r") BOARD.render();
    else if (k === "m") BOARD.measure();
    else return;
    e.preventDefault();
  },

  /* The gate, drawn on the elements that failed. */
  measure() {
    for (const el of document.querySelectorAll("[data-bad]")) el.removeAttribute("data-bad");
    const out = BOARD_ASSERT();
    for (const bad of out.faults) bad.el.setAttribute("data-bad", bad.why);
    BOARD.tag(
      " — " + (out.PASS ? "<b>PASS</b>" : "<i>FAIL</i>") +
      " · rail " + out.railPx + "px, list " + out.listPx + "px (" + out.listShare + ", " +
      out.rowsVisible + " rows)" +
      " · min type " + out.minFontPx + "px · min hit " + out.minHitPx + "px" +
      " · min card " + out.minCardPx + "px" +
      " · seats " + (out.seatsAgree ? "agree" : "<i>DISAGREE</i>")
    );
    console.log(out);
    return out;
  },
};
