/*
 * The content and the input layer every handheld mockup shares.
 *
 * NOT LOADED BY THE MOCKUPS. Each .html must open standalone from file://, so
 * this file is inlined into each one rather than linked. Same contract as
 * ../_state.js, ../menu/_menu.js and ../flow/_flow.js -- with one improvement:
 * `inline.py` does the inlining, between the BEGIN/END markers each file
 * carries, so the master and the five cannot drift by hand.
 *
 *     python inline.py          # re-inline this into all five
 *     python inline.py --check  # fail if any file is stale (CI-shaped)
 *
 * Three things live here:
 *
 *   1. BOARD    -- turn 8 at declare-attackers, the same state every earlier
 *                  round renders, so a difference on screen is a difference in
 *                  design and not in content.
 *   2. DECKS    -- twelve decks with their real ratings, read out of
 *                  data/decks/*.deck.json where a real one exists.
 *   3. PAD      -- the gamepad layer. This is the part that is actually new.
 *
 * ---------------------------------------------------------------------------
 * WHY THE GAMEPAD LAYER CAN LIVE HERE AT ALL
 *
 * `navigator.getGamepads()` is [SecureContext], and the whole round is built on
 * file:// URLs. Measured in Chrome before any of this was written:
 *
 *     window.isSecureContext  -> true
 *     navigator.getGamepads() -> a 4-slot array
 *
 * file:// is a potentially-trustworthy origin, so the API is there. What is NOT
 * there until the player presses something is the pad itself: Chrome hides
 * gamepads behind a user gesture, so `getGamepads()` returns four nulls until
 * the first button press. That is not a bug to work around -- it is why every
 * mockup opens on a "press any button" state rather than pretending to be
 * connected.
 */

/* ===========================================================================
   1. THE BOARD
   ---------------------------------------------------------------------------
   Card shorthand, unchanged from ../_state.js so the two stay diffable:
   n=name cost tl=type line t=type f=frame tone pt kw=keywords rules
   land=produces  tapped sick cmd token  count=stack size  art=name in ../art/
   ability=available activated ability   playable=castable right now
   why=why it is NOT playable (the hover-only hand hint, given a real home)
   ======================================================================== */

const OPP = {
  name: "Edgar Markov",
  life: 25,
  seat: 1,
  lib: 84, hand: 4, gy: 6, exile: 0, cmd: 1,
  cmdr: { n: "Edgar Markov", cost: "3WBR", tl: "Legendary Creature — Vampire Knight", t: "creature", f: "gold", pt: "4/4", art: "Edgar Markov" },
  // One entry per SOURCE, not per symbol: Scoured Barrens makes W or B, and
  // counting it twice would claim mana that does not exist.
  mana: [{ sym: "R", open: 2 }, { sym: "W/B", open: 0, tapped: 1 }],
  lands: [
    { n: "Mountain", tl: "Basic Land — Mountain", t: "land", f: "land", land: "R", art: "Mountain", count: 2 },
    { n: "Scoured Barrens", tl: "Land", t: "land", f: "land", land: "W/B", tapped: true, art: "Scoured Barrens" },
  ],
  creatures: [
    { n: "Vampire", tl: "Token Creature — Vampire", t: "creature", f: "B", pt: "1/1", token: true, tapped: true, art: "token:Vampire", count: 2 },
    { n: "Vampire Neonate", cost: "1B", tl: "Creature — Vampire", t: "creature", f: "B", pt: "0/3", art: "Vampire Neonate" },
    { n: "Falkenrath Noble", cost: "3B", tl: "Creature — Vampire Noble", t: "creature", f: "B", pt: "2/2", kw: "Flying",
      rules: "Whenever another creature dies, target opponent loses 1 life and you gain 1 life.", art: "Falkenrath Noble" },
  ],
  other: [],
};

const ME = {
  name: "You",
  life: 34,
  seat: 0,
  lib: 72, hand: 6, gy: 3, exile: 1, cmd: 0,
  cmdr: { n: "Aesi, Tyrant of Gyre Strait", cost: "4GU", tl: "Legendary Creature — Serpent", t: "creature", f: "gold", pt: "5/5", kw: "Trample", art: "Aesi, Tyrant of Gyre Strait" },
  mana: [{ sym: "G", open: 7 }, { sym: "U", open: 3 }, { sym: "G/U", open: 1 }, { sym: "C", open: 1 }],
  lands: [
    { n: "Forest", tl: "Basic Land — Forest", t: "land", f: "land", land: "G", art: "Forest", count: 7 },
    { n: "Island", tl: "Basic Land — Island", t: "land", f: "land", land: "U", art: "Island", count: 3 },
    { n: "Thornwood Falls", tl: "Land", t: "land", f: "land", land: "G/U", art: "Thornwood Falls" },
    { n: "Terramorphic Expanse", tl: "Land", t: "land", f: "land", land: "",
      ability: "{T}, Sacrifice: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle." },
  ],
  creatures: [
    { n: "Gyre Strait Leviathan", cost: "5UU", tl: "Creature — Leviathan", t: "creature", f: "U", pt: "7/7", kw: "Trample", attacker: true },
    { n: "Aesi, Tyrant of Gyre Strait", cost: "4GU", tl: "Legendary Creature — Serpent", t: "creature", f: "gold", pt: "5/5", kw: "Trample", cmd: true, attacker: true,
      rules: "Trample. Whenever you play a land, draw a card. You may play an additional land on each of your turns.", art: "Aesi, Tyrant of Gyre Strait" },
    { n: "Elvish Visionary", cost: "1G", tl: "Creature — Elf Shaman", t: "creature", f: "G", pt: "1/1", attacker: true, art: "Elvish Visionary" },
    { n: "Elemental", tl: "Token Creature — Elemental", t: "creature", f: "G", pt: "2/2", token: true, attacker: true, art: "token:Elemental", count: 2 },
    { n: "Acidic Slime", cost: "3GG", tl: "Creature — Ooze", t: "creature", f: "G", pt: "2/2", kw: "Deathtouch", sick: true, art: "Acidic Slime" },
    { n: "Yavimaya Elder", cost: "1G", tl: "Creature — Human Druid", t: "creature", f: "G", pt: "1/2", sick: true, art: "Yavimaya Elder" },
    { n: "Gyre Sage", cost: "1G", tl: "Creature — Elf Druid", t: "creature", f: "G", pt: "0/2", kw: "Evolve", art: "Gyre Sage" },
  ],
  other: [
    { n: "Zendikar's Roil", cost: "4G", tl: "Enchantment", t: "enchantment", f: "G",
      rules: "Whenever a land enters the battlefield under your control, create a 2/2 green Elemental creature token.", art: "Zendikar's Roil" },
  ],
};

/* THE HAND, AT DECLARE-ATTACKERS, WITH THE RULES ACTUALLY APPLIED.
   Five of these six are sorcery-speed and the step is combat, so exactly ONE
   card in hand is castable -- the instant. That is not a convenience for the
   demo, it is what the engine's `unplayable_reason` would really say here, and
   it is worth getting right for two reasons. It makes the green `--playable`
   rim mean something rather than being decoration on everything. And it puts
   the round's two hardest items on the same six cards: the one live card is the
   one that needs a target, and the five dim ones are the hover-only "why can't
   I play this" hint that has no home on a pad today. */
const HAND = [
  { n: "Vorel of the Hull Clade", cost: "1GU", tl: "Legendary Creature — Human Merfolk", t: "creature", f: "gold", pt: "1/4",
    rules: "{1}{G}{U}, {T}: Double the number of each kind of counter on target artifact, creature or land.", art: "Vorel of the Hull Clade",
    playable: false, why: "Creatures are sorcery speed. You get this back in your second main phase." },
  { n: "Explosive Vegetation", cost: "3G", tl: "Sorcery", t: "sorcery", f: "G",
    rules: "Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.", art: "Explosive Vegetation",
    playable: false, why: "A sorcery, and you are past your first main phase." },
  { n: "Garruk's Packleader", cost: "4G", tl: "Creature — Beast", t: "creature", f: "G", pt: "3/3",
    rules: "Whenever another creature with power 3 or greater enters under your control, draw a card.", art: "Garruk's Packleader",
    playable: false, why: "Creatures are sorcery speed. You get this back in your second main phase." },
  { n: "Nimble Mongoose", cost: "G", tl: "Creature — Mongoose", t: "creature", f: "G", pt: "1/1", kw: "Hexproof",
    rules: "Threshold — gets +2/+2 as long as seven or more cards are in your graveyard.", art: "Nimble Mongoose",
    playable: false, why: "Creatures are sorcery speed. You get this back in your second main phase." },
  { n: "Explore", cost: "1G", tl: "Sorcery", t: "sorcery", f: "G",
    rules: "You may play an additional land this turn. Draw a card.", art: "Explore",
    playable: false, why: "A sorcery, and you are past your first main phase." },
  { n: "Beast Within", cost: "2G", tl: "Instant", t: "instant", f: "G",
    rules: "Destroy target permanent. Its controller creates a 3/3 green Beast creature token.", art: "Beast Within",
    playable: true },
];

/* The five phases, and the step the turn is actually sitting on. The client's
   thirteen equal ticks collapse to five; only the live one expands. */
const PHASES = [
  { id: "beginning", n: "Beginning", steps: ["Untap", "Upkeep", "Draw"] },
  { id: "main1", n: "Main 1", steps: [] },
  { id: "combat", n: "Combat", steps: ["Begin", "Attackers", "Blockers", "Damage", "End"], live: true, step: 1 },
  { id: "main2", n: "Main 2", steps: [] },
  { id: "end", n: "End", steps: ["End", "Cleanup"] },
];

const LOG = [
  "You play Forest",
  "Zendikar's Roil creates a 2/2 Elemental",
  "Aesi, Tyrant of Gyre Strait draws you a card",
  "You cast Acidic Slime",
  "Acidic Slime destroys Bloodcrypt Vault",
];

/* ---------------------------------------------------------------------------
   The action list.
   The shipped client's invariant is that every legal action is a control
   carrying `data-action-id`, exactly once in the document, and that when a
   gesture and the panel disagree the panel is right. Every direction here is
   built on that list rather than around it -- which is the whole reason a
   controller port is possible at all. `src` names the permanent the action
   comes off, so a direction that wants to group by source can.
------------------------------------------------------------------------- */
const ACTIONS = [
  { id: "a-attack-commit", kind: "finish_declaration", label: "Attack with 3", primary: true },
  { id: "a-attack-all", kind: "add_attacker", label: "All attack (2 more)" },
  { id: "a-attack-none", kind: "finish_declaration", label: "No attacks" },
  { id: "a-atk-lev", kind: "add_attacker", label: "Call back Gyre Strait Leviathan", src: "Gyre Strait Leviathan", staged: true },
  { id: "a-atk-aesi", kind: "add_attacker", label: "Call back Aesi", src: "Aesi, Tyrant of Gyre Strait", staged: true },
  { id: "a-atk-elv", kind: "add_attacker", label: "Call back Elvish Visionary", src: "Elvish Visionary", staged: true },
  { id: "a-atk-el1", kind: "add_attacker", label: "Send Elemental at Edgar Markov", src: "Elemental" },
  { id: "a-atk-el2", kind: "add_attacker", label: "Send Elemental at Edgar Markov", src: "Elemental" },
  { id: "a-terra", kind: "activate", label: "Terramorphic Expanse — sacrifice for a land", src: "Terramorphic Expanse" },
];

/* The decision fixture. One shape covers every question the engine asks:
   PendingDecision { kind, prompt, options[], min_count, max_count, allow_done }.
   This one is `choose_objects` at min 1 / max 1 -- a target for Beast Within --
   because targeting is the interaction most likely to break a control scheme,
   and a round that skips it has not been tested. */
const DECISION = {
  kind: "choose_objects",
  prompt: "Choose target permanent",
  source: "Beast Within",
  min: 1, max: 1,
  options: [
    { id: "t-noble", label: "Falkenrath Noble", sub: "Edgar Markov's — 2/2 flier, drains on every death", card: OPP.creatures[2], threat: 3 },
    { id: "t-neonate", label: "Vampire Neonate", sub: "Edgar Markov's — 0/3 wall", card: OPP.creatures[1], threat: 1 },
    { id: "t-vamp", label: "Vampire", sub: "Edgar Markov's — 1/1 token, tapped and attacking", card: OPP.creatures[0], threat: 1 },
    { id: "t-barrens", label: "Scoured Barrens", sub: "Edgar Markov's — his only source of white", card: OPP.lands[1], threat: 2 },
    { id: "t-mountain", label: "Mountain", sub: "Edgar Markov's — one of two", card: OPP.lands[0], threat: 1 },
    { id: "t-slime", label: "Acidic Slime", sub: "Yours — 2/2 deathtouch, summoning sick", card: ME.creatures[4], threat: 0, mine: true },
  ],
};

/* ===========================================================================
   2. THE DECKS
   ---------------------------------------------------------------------------
   Ratings are the real `ratings` block out of data/decks/*.deck.json where the
   deck exists there (aesi, edgar, isperia, zurgo). The rest are real Scryfall
   commanders with no list in this repo yet -- `preview: true` is what says so,
   and it is why their card counts are absent rather than invented.
   Scale is 1-4 and drawn as four segments, not a number: speed, complexity,
   interaction, resilience, and `pilot`, which is how much the deck asks of
   whoever is holding it.
   ======================================================================== */

const DECKS = [
  { id: "aesi", n: "Aesi, Tyrant of Gyre Strait", short: "Aesi", ci: ["G", "U"], guild: "Simic", cards: 100, lands: 37,
    art: "Aesi, Tyrant of Gyre Strait", cost: "4GU", tl: "Legendary Creature — Serpent", pt: "5/5", src: "precon",
    tags: ["Ramp", "Landfall", "Card draw"],
    notes: "Lands are the engine. Every one you play draws a card and grows the board, and the extra land drop means the turn you untap with Aesi is the turn it snowballs.",
    ratings: { speed: 2, complexity: 3, interaction: 2, resilience: 3, pilot: 2 } },
  { id: "edgar", n: "Edgar Markov", short: "Edgar", ci: ["W", "B", "R"], guild: "Mardu", cards: 100, lands: 36,
    art: "Edgar Markov", cost: "3WBR", tl: "Legendary Creature — Vampire Knight", pt: "4/4", src: "precon",
    tags: ["Aggro", "Tokens", "Drain"],
    notes: "Mardu vampire aggro. Eminence makes a token every time a Vampire is cast, lords make the swarm lethal, and drain turns every death into damage.",
    ratings: { speed: 4, complexity: 2, interaction: 3, resilience: 2, pilot: 2 } },
  { id: "isperia", n: "Isperia, Supreme Judge", short: "Isperia", ci: ["W", "U"], guild: "Azorius", cards: 100, lands: 37,
    art: "Isperia, Supreme Judge", cost: "4WU", tl: "Legendary Creature — Sphinx", pt: "6/6", src: "precon",
    tags: ["Fliers", "Control", "Card draw"],
    notes: "A wide sky and a long game. Anthem effects make one-power fliers lethal, and everything that attacks you draws you a card.",
    ratings: { speed: 2, complexity: 3, interaction: 4, resilience: 3, pilot: 3 } },
  { id: "zurgo", n: "Zurgo Stormrender", short: "Zurgo", ci: ["W", "B", "R"], guild: "Mardu", cards: 100, lands: 36,
    art: "Zurgo Stormrender", cost: "1WBR", tl: "Legendary Creature — Orc Warrior", pt: "3/3", src: "precon",
    tags: ["Tokens", "Sacrifice", "Aggro"],
    notes: "Every end step makes a body or drains a life, and the deck is built to spend both. Wide, cheap and relentless rather than explosive.",
    ratings: { speed: 3, complexity: 3, interaction: 3, resilience: 2, pilot: 3 } },
  { id: "atraxa", n: "Atraxa, Praetors' Voice", short: "Atraxa", ci: ["W", "U", "B", "G"], guild: "Witch", art: "Atraxa, Praetors' Voice",
    cost: "GWUB", tl: "Legendary Creature — Phyrexian Angel Horror", pt: "4/4", src: "precon", preview: true,
    tags: ["Counters", "Proliferate", "Value"],
    notes: "Proliferate at every end step. Whatever counter you care about, this deck adds another one to it — and it plays four colours to find all of them.",
    ratings: { speed: 2, complexity: 4, interaction: 3, resilience: 4, pilot: 4 } },
  { id: "krenko", n: "Krenko, Mob Boss", short: "Krenko", ci: ["R"], guild: "Mono-red", art: "Krenko, Mob Boss",
    cost: "2RR", tl: "Legendary Creature — Goblin Warrior", pt: "3/3", src: "precon", preview: true,
    tags: ["Tokens", "Aggro", "Combo"],
    notes: "Tap Krenko, double your goblins. Untap Krenko, do it again. The whole deck is haste, untappers and one very large attack step.",
    ratings: { speed: 4, complexity: 1, interaction: 1, resilience: 1, pilot: 1 } },
  { id: "muldrotha", n: "Muldrotha, the Gravetide", short: "Muldrotha", ci: ["B", "G", "U"], guild: "Sultai", art: "Muldrotha, the Gravetide",
    cost: "4BGU", tl: "Legendary Creature — Elemental Avatar", pt: "6/6", src: "precon", preview: true,
    tags: ["Graveyard", "Value", "Grind"],
    notes: "One permanent of each type out of your graveyard, every turn. Nothing you lose is gone, which is why it wins games that go long.",
    ratings: { speed: 1, complexity: 4, interaction: 3, resilience: 4, pilot: 4 } },
  { id: "urdragon", n: "The Ur-Dragon", short: "Ur-Dragon", ci: ["W", "U", "B", "R", "G"], guild: "Five-colour", art: "The Ur-Dragon",
    cost: "4WUBRG", tl: "Legendary Creature — Dragon Avatar", pt: "10/10", src: "precon", preview: true,
    tags: ["Big creatures", "Ramp", "Tribal"],
    notes: "Dragons cost one less, and every dragon that connects draws a card and puts a permanent onto the battlefield free.",
    ratings: { speed: 2, complexity: 2, interaction: 2, resilience: 3, pilot: 2 } },
  { id: "meren", n: "Meren of Clan Nel Toth", short: "Meren", ci: ["B", "G"], guild: "Golgari", art: "Meren of Clan Nel Toth",
    cost: "2BG", tl: "Legendary Creature — Human Shaman", pt: "3/4", src: "precon", preview: true,
    tags: ["Sacrifice", "Graveyard", "Grind"],
    notes: "Sacrifice things on purpose. Experience counters make Meren return them for free, and the deck never runs out of things worth killing.",
    ratings: { speed: 2, complexity: 4, interaction: 4, resilience: 4, pilot: 4 } },
  { id: "talrand", n: "Talrand, Sky Summoner", short: "Talrand", ci: ["U"], guild: "Mono-blue", art: "Talrand, Sky Summoner",
    cost: "2UU", tl: "Legendary Creature — Merfolk Wizard", pt: "2/2", src: "moxfield", preview: true,
    tags: ["Control", "Tokens", "Counterspells"],
    notes: "Every instant and sorcery makes a 2/2 flier. Counter their spells and you build an army out of saying no.",
    ratings: { speed: 2, complexity: 3, interaction: 4, resilience: 2, pilot: 3 } },
  { id: "purphoros", n: "Purphoros, God of the Forge", short: "Purphoros", ci: ["R"], guild: "Mono-red", art: "Purphoros, God of the Forge",
    cost: "2R", tl: "Legendary Enchantment Creature — God", pt: "6/5", src: "moxfield", preview: true,
    tags: ["Tokens", "Burn", "Aggro"],
    notes: "Two damage to the table every time a creature turns up, and it is indestructible until you want it to attack. You do not need to attack at all.",
    ratings: { speed: 4, complexity: 2, interaction: 1, resilience: 3, pilot: 1 } },
  { id: "chulane", n: "Chulane, Teller of Tales", short: "Chulane", ci: ["G", "W", "U"], guild: "Bant", art: "Chulane, Teller of Tales",
    cost: "2GWU", tl: "Legendary Creature — Human Advisor", pt: "2/4", src: "moxfield", preview: true,
    tags: ["Value", "Bounce", "Combo"],
    notes: "Draw a card and put a land into play every time a creature enters. The deck is a chain of enters-the-battlefield triggers looking for its own end.",
    ratings: { speed: 3, complexity: 4, interaction: 2, resilience: 3, pilot: 4 } },
];

const RATING_ROWS = [
  ["speed", "Speed"],
  ["complexity", "Complexity"],
  ["interaction", "Interaction"],
  ["resilience", "Resilience"],
  ["pilot", "Demands on you"],
];

/* The four seats of the pod being assembled, for the directions whose deck
   picker sits inside a lobby rather than standing alone. */
const SEATS = [
  { who: "You", deck: "aesi", locked: false, you: true },
  { who: "Marco", deck: "edgar", locked: true },
  { who: "Duelist", deck: "isperia", locked: true, cpu: "Duelist" },
  { who: null, deck: null, locked: false },
];

/* ===========================================================================
   3. THE PAD
   ---------------------------------------------------------------------------
   One input layer, five consumers. Every mockup calls Pad.start({...}) with
   named intents -- `up`, `confirm`, `cancel`, `zoneNext` -- and never touches a
   button index, because the whole point of the round is to compare what the
   intents are WIRED TO, and a direction that spelt its own polling loop would
   be comparing loop bugs instead.

   STEAM DECK -> STANDARD GAMEPAD. The Deck reports itself as a Standard
   Gamepad, so the W3C indices hold and are what this maps:

       0 A     1 B     2 X     3 Y
       4 L1    5 R1    6 L2    7 R2      (6 and 7 are ANALOG -- .value 0..1)
       8 View  9 Menu  10 L3   11 R3
       12 Up   13 Down 14 Left 15 Right
       axes 0,1 left stick   axes 2,3 right stick

   The four back grips (L4/R4/L5/R5) are DELIBERATELY UNUSED. Steam Input maps
   them to other buttons by default and a player may have rebound them, so a
   design that needs them is a design that breaks on somebody's machine. The
   trackpads arrive as mouse input, which is why the pointer still works
   everywhere and 04 can be built on it at all. Gyro is not exposed to the
   browser at all -- no direction here may depend on it.

   KEYBOARD FALLBACK exists so these can be reviewed without a controller, and
   is chosen to sit under one hand on a laptop:

       arrows / WASD   d-pad          Enter or J    A (confirm)
       Backspace / K   B (cancel)     U             X
       I               Y              Q / E         L1 / R1
       1 / 3           L2 / R2        Tab           View     \  Menu
   ======================================================================== */

const Pad = (() => {
  const BTN = {
    a: 0, b: 1, x: 2, y: 3, l1: 4, r1: 5, l2: 6, r2: 7,
    view: 8, menu: 9, l3: 10, r3: 11, up: 12, down: 13, left: 14, right: 15,
  };
  const KEYS = {
    ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
    w: "up", s: "down", a: "left", d: "right",
    Enter: "a", j: "a", Backspace: "b", k: "b", u: "x", i: "y",
    q: "l1", e: "r1", 1: "l2", 3: "r2", Tab: "view", "\\": "menu",
    ",": "l3", ".": "r3",
  };
  const DEAD = 0.30;          // Deck sticks rest noisily; 0.30 is past the noise
  const FIRE = 0.55;          // a direction is meant once the stick crosses this
  const RELEASE = 0.35;       // ...and is not meant again until it drops below this
  const REPEAT_FIRST = 400;   // ms a direction must be held before it repeats
  const REPEAT_NEXT = 95;     // ms between repeats after that

  let handlers = {};
  let prev = {};              // button name -> was down last frame
  let held = {};              // direction -> ms the next repeat is due
  let latched = null;         // the stick's current sector, or null while centred
  let connected = false;
  let raf = 0;
  let presses = 0;            // every discrete input, for the press-count metric
  const keyDown = new Set();
  /* A key tapped faster than a frame is a key the poll never sees: keydown and
     keyup can both land inside one 16ms gap, `down()` reads false at poll time,
     and the press is silently dropped. A pad cannot do this to you because it
     IS the poll, which is why the bug only ever shows up on the fallback -- and
     why it would have been blamed on the keyboard map rather than found. So a
     key press is latched until exactly one frame has observed it. */
  const keyLatch = new Set();
  const listeners = new Set();

  // A keyboard press and a pad press arrive at the same place, so nothing
  // downstream can tell them apart and no mockup has two code paths.
  function down(name) {
    return keyDown.has(name) || keyLatch.has(name) || padDown(name);
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
    // Over 30 permanents in ragged rows that reads as "the cursor is broken",
    // and the reviewer blames the DIRECTION rather than this loop.
    return latched === name;
  }
  /** Which of the four sectors the left stick is in, with hysteresis: a new
      direction is only latched past FIRE, and nothing new latches until the
      stick falls back inside RELEASE. */
  function sector(p) {
    const x = axis(p, 0);
    const y = axis(p, 1);
    const m = Math.hypot(x, y);
    if (m < RELEASE) return null;
    if (latched && m < FIRE) return latched;
    if (m < FIRE) return null;
    return Math.abs(x) > Math.abs(y)
      ? (x < 0 ? "left" : "right")
      : (y < 0 ? "up" : "down");
  }
  function pads() {
    return navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  }
  function axis(p, i) {
    return p.axes.length > i ? p.axes[i] : 0;
  }
  /** Analog trigger position, 0..1. Falls back to the digital press so the
      keyboard can still reach the ends of the range. */
  function trigger(name) {
    const p = pads()[0];
    if (p) {
      const b = p.buttons[BTN[name]];
      if (b) return keyDown.has(name) ? 1 : b.value;
    }
    return keyDown.has(name) ? 1 : 0;
  }
  /** Right stick, deadzoned and rescaled so it leaves 0 cleanly. */
  function rstick() {
    const p = pads()[0];
    if (!p) return { x: 0, y: 0 };
    const raw = { x: axis(p, 2), y: axis(p, 3) };
    const m = Math.hypot(raw.x, raw.y);
    if (m < DEAD) return { x: 0, y: 0 };
    const k = (m - DEAD) / (1 - DEAD) / m;
    return { x: raw.x * k, y: raw.y * k };
  }
  function lstick() {
    const p = pads()[0];
    if (!p) {
      const x = (keyDown.has("right") ? 1 : 0) - (keyDown.has("left") ? 1 : 0);
      const y = (keyDown.has("down") ? 1 : 0) - (keyDown.has("up") ? 1 : 0);
      return { x, y };
    }
    const raw = { x: axis(p, 0), y: axis(p, 1) };
    const m = Math.hypot(raw.x, raw.y);
    if (m < DEAD) return { x: 0, y: 0 };
    const k = (m - DEAD) / (1 - DEAD) / m;
    return { x: raw.x * k, y: raw.y * k };
  }

  const REPEATS = new Set(["up", "down", "left", "right"]);

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
      for (const d of REPEATS) if (keyDown.has(d) || keyLatch.has(d)) latched = d;
    }
    for (const name of Object.keys(BTN)) {
      const isDown = down(name);
      const was = prev[name];
      if (isDown && !was) {
        fire(name);
        if (REPEATS.has(name)) held[name] = now + REPEAT_FIRST;
      } else if (isDown && was && REPEATS.has(name) && now >= held[name]) {
        fire(name);
        held[name] = now + REPEAT_NEXT;
      } else if (!isDown) {
        delete held[name];
      }
      prev[name] = isDown;
    }
    if (handlers.frame) handlers.frame({ lstick: lstick(), rstick: rstick(), l2: trigger("l2"), r2: trigger("r2"), connected });
    // One frame has now seen every latched key, so a key still physically held
    // survives in keyDown and a tapped one is released here.
    for (const name of [...keyLatch]) if (!keyDown.has(name)) keyLatch.delete(name);
    raf = requestAnimationFrame(frame);
  }
  /* Every discrete input is counted, and the count is on screen in every file.
     "How many presses to cast a spell with a target" is this round's headline
     number, and a number the prototype reports itself is a number nobody has to
     argue about afterwards. */
  function fire(name) {
    presses += 1;
    const h = handlers[name];
    if (h) h();
    if (handlers.any) handlers.any(name);
  }

  /* Rumble, for exactly one thing: the illegal-move buzz. THE RULE IS THAT
     RUMBLE IS ALWAYS REDUNDANT WITH SOMETHING VISIBLE -- Firefox in the Deck's
     desktop mode has no `vibrationActuator`, so haptics can never be the only
     channel carrying a fact. */
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
    presses: () => presses,
    resetPresses: () => { presses = 0; },
    start(h) {
      handlers = h || {};
      addEventListener("keydown", (ev) => {
        const name = KEYS[ev.key];
        if (!name) return;
        // Tab and Backspace both navigate the page otherwise, and Backspace on
        // file:// is a history step you cannot get back from.
        ev.preventDefault();
        if (ev.repeat) return;   // the OS autorepeat would race our own DAS/ARR
        keyDown.add(name);
        keyLatch.add(name);
      });
      addEventListener("keyup", (ev) => {
        const name = KEYS[ev.key];
        if (name) keyDown.delete(name);
      });
      // Chrome hides pads until a gesture, so this is the moment they appear.
      addEventListener("gamepadconnected", () => { });
      raf = requestAnimationFrame(frame);
      return this;
    },
    stop() { cancelAnimationFrame(raf); },
    onConnection(f) { listeners.add(f); f(connected); },
    connected() { return connected; },
    trigger, rstick, lstick,
  };
})();

/* The glyphs. Drawn as text on a disc rather than fetched, because the round
   has to open from file:// with no network -- and because the Deck's own face
   buttons are literally lettered A B X Y in that layout. */
const GLYPH = {
  a: "A", b: "B", x: "X", y: "Y",
  l1: "L1", r1: "R1", l2: "L2", r2: "R2",
  view: "⧉", menu: "☰", l3: "L3", r3: "R3",
  up: "▲", down: "▼", left: "◀", right: "▶",
  dpad: "✛", lstick: "◉", rstick: "◎",
};

/* ===========================================================================
   4. SHARED RENDER HELPERS
   ---------------------------------------------------------------------------
   Only the pieces that must look identical across all five so the comparison is
   about layout: the card face, mana pips and rating bars. Everything structural
   is each direction's own.
   ======================================================================== */

/* The slug ../art/manifest.json actually uses. An apostrophe is a SEPARATOR,
   not a character to delete: the file is `garruk-s-packleader.jpg`, so stripping
   the apostrophe first yields `garruks-packleader` and a silently broken image.
   Four cards on this board state hit that, and a missing crop looks exactly
   like a card that genuinely has no printing -- which is why it is worth
   getting right rather than eyeballing. */
const ART = (name) => {
  if (!name) return null;
  const slug = name
    .replace(/^token:/, "token-")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `../art/${slug}.jpg`;
};

/* ---------------------------------------------------------------------------
   MANA SYMBOLS -- the published ones, not letters on coloured discs.

   `../cards/symbols/` holds the 54 real Scryfall SVGs that `fetch_symbols.py`
   pulled and that the shipped client now vendors to `frontend/public/symbols/`.
   Using them here matters for two reasons beyond looking right:

   1. A LETTER ON A DISC IS TEXT, AND TEXT HAS A FLOOR. At the sizes a mana cost
      wants to be, a letter lands under 16px and `assert.js` fails the file --
      correctly, because a 13px letter really is unreadable on a 7-inch screen.
      The published symbols are SHAPES, so they read at 14px the way a suit pip
      on a playing card does, and they are `aria-hidden` with the cost given in
      text to anything that needs words.
   2. Hybrids and Phyrexian have no letter form at all. `{W/U}` as "WU" on one
      disc is an invention; `W-U.svg` is the actual symbol.

   `<img>` works from file:// where `fetch()` does not, which is the whole
   reason these are separate files rather than inlined data URIs.
------------------------------------------------------------------------- */

const SYM_DIR = "../cards/symbols";

/** Tokenise a cost. Accepts the shorthand this round uses (`4GU`), Scryfall's
    braces (`{4}{G}{U}`), and hybrids either way (`W/U`, `{2/B}`). */
function tokens(cost) {
  if (!cost) return [];
  if (Array.isArray(cost)) return cost;
  const s = String(cost).replace(/[{}]/g, "");
  const out = [];
  let num = "";
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (/[0-9]/.test(ch)) { num += ch; continue; }
    if (num && s[i] !== "/") { out.push(num); num = ""; }
    if (s[i + 1] === "/") {                       // hybrid: bind a/b as one
      const a = num || ch;
      num = "";
      out.push(`${a}/${s[i + 2]}`);
      i += 2;
      continue;
    }
    out.push(ch);
  }
  if (num) out.push(num);
  return out;
}

/** One published symbol. `alt` is empty and the element is aria-hidden because
    every cost that uses this also carries a text form for anything reading. */
function symHTML(tok) {
  const file = String(tok).replace("/", "-").toUpperCase();
  return `<img class="sym" src="${SYM_DIR}/${file}.svg" alt="" aria-hidden="true">`;
}

/* A COST IS ONE WORD. Wrapped in its own inline-flex so `{3}{B}` can never
   break across two lines the way it did in the rail -- a mana cost split down
   the middle reads as two different costs. */
function costHTML(cost) {
  const t = tokens(cost);
  if (!t.length) return "";
  return `<span class="cost">${t.map(symHTML).join("")}</span>`;
}

/** The mana a single source can make, which is NOT the same shape as a cost:
    Scoured Barrens makes W *or* B, so it is one hybrid symbol rather than two
    pips claiming two mana that do not both exist. Board round 03 got this wrong
    in the other direction and the note is still in `../README.md`. */
function producesHTML(str) {
  if (!str) return "";
  const inner = str.includes("/") ? symHTML(str) : tokens(str).map(symHTML).join("");
  return `<span class="cost">${inner}</span>`;
}

/* --- Rules text with its symbols in it ------------------------------------
   `SymbolText.tsx` swaps `{G}` inside oracle text for the published pip. Doing
   the same here is not decoration -- "{1}{G}{U}, {T}:" rendered as literal
   braces was the single worst-looking thing in 01-05, and an activated ability
   is exactly where it appears.
------------------------------------------------------------------------- */
function textHTML(s) {
  if (!s) return "";
  return String(s).replace(/\{([^}]+)\}/g, (_, t) => symHTML(t));
}

/* An activated ability, split into what you PAY and what you GET, because that
   is the order a player reads one in. Rendering it as a single run of prose is
   what made ability cards look broken in the first five. */
function splitAbility(text) {
  if (!text) return null;
  const i = text.indexOf(":");
  if (i < 0) return { cost: "", effect: text.trim() };
  return { cost: text.slice(0, i).trim(), effect: text.slice(i + 1).trim() };
}

const MANA_HUE = { W: "#fffbd5", U: "#aae0fa", B: "#cbc2bf", R: "#f9aa8f", G: "#9bd3ab", C: "#d0cbc4" };

/** Kept for the colour-identity dots, which are deliberately NOT mana symbols:
    a deck's identity is five slots that are on or off, and five full pips reads
    as a cost somebody has to pay. */
function pipHTML(sym) {
  return symHTML(sym);
}

/** Colour-identity dots for a deck, in WUBRG order, which is the order a
    Commander player says them in. */
function ciHTML(ci) {
  return ci.map((c) => `<i class="ci" style="background:${MANA_HUE[c]}"></i>`).join("");
}

/** A 1-4 rating as four segments. A number would be read as a score; segments
    are read as a quantity, which is what it is. */
function ratingHTML(v) {
  return [1, 2, 3, 4].map((i) => `<i class="seg${i <= v ? " seg--on" : ""}"></i>`).join("");
}

const TYPE_GLYPH = {
  creature: "❖", land: "◈", sorcery: "✦", instant: "⚡",
  enchantment: "❋", artifact: "⬢", planeswalker: "✧",
};

/** The one card face every direction draws, so a card is the same object on all
    five and the comparison is about what SURROUNDS it. Width comes from
    `--card-w` on the container -- each direction owns its own scale.
 *
 *  `opts.tile` DROPS THE NAME, and that is the round's first real finding
 *  rather than a shortcut. Hold the 16px floor and "Elvish Visionary" needs
 *  about 128px of card width to render its own name. A viewer's board here is
 *  twelve permanents; twelve at 128px is 1536px on a screen that has 1280. So
 *  at this floor the name cannot be on every board card at once, and each
 *  direction has to say what it does about that. 01 and 05 put the name on the
 *  ring (the focused card gets a plate, and the hint bar always says what you
 *  are on); 03 makes the cards big enough that the name fits; 04 never draws a
 *  board at all. Shrinking the type to fit is the one answer nobody may give,
 *  because that is what the shipped client already does -- 2.11px at the
 *  bottom -- and it is why this round exists. */
function faceHTML(c, opts = {}) {
  if (!c) return `<div class="face face--empty"></div>`;
  const art = ART(c.art);
  const cls = [
    "face", `face--${c.f || "default"}`,
    opts.tile ? "face--tile" : "",
    opts.nameless ? "face--nameless" : "",
    // A thumb sits BESIDE its own name in real type. It identifies a row rather
    // than being the only thing identifying an object, so the 96px card floor
    // does not apply to it -- and `assert.js` exempts exactly this class, so
    // the exemption is a decision written down rather than a hole in the check.
    // Using it on a card that carries no adjacent name is cheating the gate.
    opts.thumb ? "face--thumb" : "",
    c.tapped ? "face--tapped" : "",
    c.sick ? "face--sick" : "",
    opts.dim ? "face--dim" : "",
    opts.cls || "",
  ].filter(Boolean).join(" ");
  return `<div class="${cls}">
    ${art ? `<img class="face__art" src="${art}" alt="" loading="lazy">` : `<div class="face__noart" aria-hidden="true">${TYPE_GLYPH[c.t] || "◇"}</div>`}
    <div class="face__head">
      <span class="face__glyph" aria-hidden="true">${TYPE_GLYPH[c.t] || "◇"}</span>
      <span class="face__name">${c.cmd ? "♛ " : ""}${c.n}</span>
      ${c.cost ? `<span class="face__cost">${costHTML(c.cost)}</span>` : ""}
    </div>
    ${abilityBandHTML(c, opts)}
    <div class="face__foot">
      ${c.land ? `<span class="face__land">${producesHTML(c.land)}</span>` : ""}
      ${c.pt ? `<span class="face__pt">${c.pt}</span>` : ""}
    </div>
    ${c.count > 1 ? `<span class="face__count">×${c.count}</span>` : ""}
    ${c.ability ? `<span class="face__rune" aria-hidden="true">↻</span>` : ""}
    ${c.attacker ? `<span class="face__atk" aria-hidden="true">▲</span>` : ""}
  </div>`;
}

/* THE ABILITY BAND.
   The round's own feedback named "poorly formatted cards when containing an
   activated ability", and it was right: 01-05 drew a rune and dropped the text,
   or ran "{T}, Sacrifice: Search your library..." as one line of prose with
   literal braces in it.

   An activated ability is TWO things and a player reads them in order -- what
   you pay, then what you get -- so it is drawn as two, split on the colon, with
   the cost in real symbols. On a tile there is no room for either and the rune
   is all you get; at any size above that the band appears, because a card whose
   ability you cannot read is a card you cannot decide about. */
function abilityBandHTML(c, opts = {}) {
  if (!c.ability || opts.tile) return "";
  const a = splitAbility(c.ability);
  return `<div class="face__ab">
    ${a.cost ? `<span class="face__ab-cost">${textHTML(a.cost)}</span>` : ""}
    <span class="face__ab-effect">${textHTML(a.effect)}</span>
  </div>`;
}

/** Every permanent on one side, in the three lanes the client uses. */
function lanesOf(p) {
  return [
    { id: "lands", n: "Lands", cards: p.lands },
    { id: "creatures", n: "Creatures", cards: p.creatures },
    { id: "other", n: "Other", cards: p.other },
  ];
}

/** How many actual objects a lane holds, counting a ×7 stack as seven. This is
    what a "12 lands" readout means, and getting it from `count` rather than
    `length` is the difference between the readout and the row agreeing. */
function countOf(cards) {
  return cards.reduce((n, c) => n + (c.count || 1), 0);
}

/* ---------------------------------------------------------------------------
   STABLE IDENTITY, and why the cursor needs it.

   Every direction here re-renders by rebuilding markup, which destroys DOM
   focus. So the cursor cannot BE `document.activeElement` -- it has to be state
   (`{zone, oid}`) that the renderer draws a ring from, with real DOM focus
   restored once per render so the accessibility tree still agrees.

   That is not a mockup workaround. It is the finding the React client needs:
   `Table.tsx` has every board card at `tabIndex={0}` with no focus styling and
   no roving tabindex, and a roving tabindex driven by state is the fix.

   A ×7 stack of Forests keeps ONE oid and stays one cursor stop, which is also
   how the hover-only `CardStack` fan gets a controller route: focusing the
   stack is what fans it.
------------------------------------------------------------------------- */
let _oid = 100;
function tag(cards, zone) {
  cards.forEach((c) => {
    c.oid = ++_oid;
    c.zone = zone;
  });
  return cards;
}

tag(OPP.lands, "opp:lands");
tag(OPP.creatures, "opp:creatures");
tag(OPP.other, "opp:other");
tag(ME.lands, "my:lands");
tag(ME.creatures, "my:creatures");
tag(ME.other, "my:other");
tag(HAND, "hand");
tag([OPP.cmdr], "opp:cmd");
tag([ME.cmdr], "my:cmd");

/** Every permanent on the table, in one list, for the directions that want to
    treat the board as a flat graph rather than as three lanes a side. */
function allPermanents() {
  return [...lanesOf(OPP), ...lanesOf(ME)].flatMap((l) => l.cards);
}

const byOid = (oid) => allPermanents().concat(HAND).find((c) => c.oid === oid) || null;

/* ---------------------------------------------------------------------------
   FIT THE DECK TO THE WINDOW.

   The stage is always 1280x800; only its scale changes. Called once and on
   resize. Everything inside works in Deck pixels and never has to know.

   The one thing that must NOT be scaled is the pointer maths in 05 and 06:
   `clientX/clientY` arrive in window pixels, so a scaled stage needs them
   divided back. `deckPoint()` is that, in one place, so no direction has to
   remember -- getting this wrong makes the pointer drift further from the
   cursor the further you are from the centre, which reads as bad magnetism
   rather than as bad arithmetic.
------------------------------------------------------------------------- */
let DECK_SCALE = 1;
let DECK_W = 1280;
let DECK_H = 800;

/* ---------------------------------------------------------------------------
   TWO WAYS TO SIZE THE STAGE, AND THE DIFFERENCE IS THE WHOLE ARGUMENT ABOUT
   BIG SCREENS.

   DECK mode is the reference: a fixed 1280x800, scaled to fit the window, with
   the scale printed on the bezel. It is what you review a handheld design in,
   and it is what every measurement in the README was taken at.

   WINDOW mode is what the app should actually do on a monitor. And the point
   is that scaling a 1280 layout up to 2560 buys you NOTHING -- the same seven
   creatures, the same three summarised opponents, just larger. A desktop has
   more room, and more room should buy MORE GAME:

     >= 1500 wide   the opponent seats stop being summaries and draw their
                    actual boards, because there is finally space for cards
     >= 1500 wide   the rail widens, so oracle text stops wrapping every line
     >= 1800 wide   cards step up 104 -> 124px, and the hand with them
     >= 1100 tall   lanes get their own rows back instead of sharing

   That is the same instinct `useZoomFit` already has in the client -- solve
   for the largest card that still fits -- pointed at the opposite end of the
   range. `--card-w` and `--rail-w` are the two knobs, and everything else is
   already expressed in terms of them.
------------------------------------------------------------------------- */
function fitDeck() {
  const el = document.querySelector(".deck");
  if (!el) return;
  const windowed = typeof S !== "undefined" && S.fit === "window";

  if (windowed) {
    DECK_W = Math.max(1024, innerWidth - 24);
    DECK_H = Math.max(680, innerHeight - 58);
    DECK_SCALE = 1;
    el.style.width = DECK_W + "px";
    el.style.height = DECK_H + "px";
    el.style.transform = "none";
  } else {
    DECK_W = 1280;
    DECK_H = 800;
    el.style.width = "1280px";
    el.style.height = "800px";
    DECK_SCALE = Math.min((innerWidth - 26) / 1280, (innerHeight - 76) / 800);
    DECK_SCALE = Math.max(0.3, Math.min(DECK_SCALE, 2));
    el.style.transform = `scale(${DECK_SCALE})`;
  }

  // The two knobs every layout reads. Nothing downstream needs a media query.
  const cardW = DECK_W >= 1800 ? 124 : DECK_W >= 1500 ? 114 : 104;
  const railW = DECK_W >= 1500 ? 336 : 262;
  el.style.setProperty("--card-w-board", cardW + "px");
  el.style.setProperty("--rail-w", railW + "px");
  el.dataset.wide = DECK_W >= 1500 ? "yes" : "no";
  el.dataset.tall = DECK_H >= 1100 ? "yes" : "no";

  const tag = document.querySelector(".bezel__tag");
  if (tag) {
    tag.innerHTML = windowed
      ? `Window · <b>${DECK_W}×${DECK_H}</b> · ${el.dataset.wide === "yes" ? "opponents drawn in full" : "opponents summarised"} · <b>F</b> for Deck`
      : `Steam Deck · 1280×800 · shown at <b>${Math.round(DECK_SCALE * 100)}%</b> · <b>F</b> to fit window`;
  }
}

/** A window point in Deck coordinates. */
function deckPoint(clientX, clientY) {
  const el = document.querySelector(".deck");
  if (!el) return { x: clientX, y: clientY };
  const r = el.getBoundingClientRect();
  return { x: (clientX - r.left) / DECK_SCALE, y: (clientY - r.top) / DECK_SCALE };
}

addEventListener("resize", fitDeck);
