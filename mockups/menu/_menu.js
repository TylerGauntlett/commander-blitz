/*
 * The content every menu mockup renders: four precons, one custom-deck slot,
 * and the difficulty ladder.
 *
 * NOT LOADED BY THE MOCKUPS. Each .html file is required to open standalone from
 * file://, so this file is inlined into each one rather than linked. It is kept
 * here as the single readable copy: edit this, then re-inline. Same contract as
 * ../_state.js and ../cards/_cards.js.
 *
 * Everything here is real where real exists. Aesi and Edgar are read out of
 * data/decks/*.deck.json and data/cards/*.cards.json -- the blurbs are the deck
 * files' own `notes`, the curves were counted from the real card lists, and the
 * substitution notes are the real `reason` strings. The two new precons are real
 * Scryfall cards with real oracle text, but they have no deck list in this repo
 * yet, which is what `engine: "preview"` means and why their `curve` is null.
 * A dossier that invented a curve for them would be the one lie on the screen.
 */

// Card-face shorthand, unchanged from ../_state.js:
// n=name cost tl=type line t=type tone f=frame tone pt kw=keywords rules
// art=slug in ../art/  artist

// ---------------------------------------------------------------------------
// Difficulty
//
// Four tiers. Tier 1 is today's `random` agent and tier 3 is today's
// `heuristic`; tiers 2 and 4 are the roadmap's CPU work (roadmap.md:48-63) and
// do not exist in the engine yet. Each tier lights a cumulative prefix of three
// capability lamps, drawn filled/hollow -- so the ladder says what it turns on
// rather than asking you to trust an adjective, and is a count rather than a
// shade you have to interpret.

const CAPS = [
  { id: "combat", n: "Combat math" },
  { id: "removal", n: "Removal & targeting" },
  { id: "seq", n: "Mana & sequencing" },
];

const DIFFICULTY = [
  {
    id: "goldfish", n: "Goldfish", tag: "Plays solitaire", caps: [], agent: "random",
    line: "Takes legal actions at random. It will not block you, race you, or notice you exist.",
  },
  {
    id: "apprentice", n: "Apprentice", tag: "Knows the basics", caps: ["combat"], rec: true,
    line: "Blocks when the trade is safe, attacks when the attack is free, and plays to its curve.",
  },
  {
    id: "duelist", n: "Duelist", tag: "Plays to win", caps: ["combat", "removal"], agent: "heuristic",
    line: "Spends removal on your best threat, keeps a blocker home, and counts to lethal.",
  },
  {
    id: "archmage", n: "Archmage", tag: "Plays around you", caps: ["combat", "removal", "seq"],
    line: "Sequences its mana, holds up interaction, and plays around the cards you left mana open for.",
  },
];

// The five ratings under every deck, 1-4, drawn as four segments. `pilot` is how
// much the deck asks of whoever is holding it -- deliberately NOT named with the
// difficulty ladder's words, because one word meaning two things on one screen
// is worse than two words.
const BAR_LABELS = [
  ["speed", "Speed"],
  ["complexity", "Complexity"],
  ["interaction", "Interaction"],
  ["resilience", "Resilience"],
  ["pilot", "Demands on you"],
];

// ---------------------------------------------------------------------------
// The precons

const PRECONS = [
  {
    id: "aesi",
    name: "Aesi, Tyrant of Gyre Strait",
    short: "Aesi",
    ci: ["G", "U"], guild: "Simic", cards: 100, lands: 37,
    cmd: {
      n: "Aesi, Tyrant of Gyre Strait", cost: "4GU", tl: "Legendary Creature — Serpent",
      t: "creature", f: "gold", pt: "5/5", kw: "Trample",
      rules: "Trample. Whenever you play a land, draw a card. You may play an additional land on each of your turns.",
      art: "aesi-tyrant-of-gyre-strait", artist: "Viktor Titov",
    },
    tags: ["Ramp", "Landfall", "Card draw"],
    blurb: "Simic ramp and landfall. Plays extra lands, turns each one into cards off Aesi and Tatyova, and closes with large trampling threats.",
    strategy:
      "The first four turns are spent almost entirely on mana: a dork, a rock, a land-search sorcery, a second land drop. " +
      "Aesi lands on turn five or six and converts the whole plan into cards — every land after that draws one, and Aesi lets you play two. " +
      "By turn eight the deck is drawing three or four cards a turn off lands alone, and the payoffs stop being incremental: Avenger of Zendikar turns a board of lands into a board of bodies, Rampaging Baloths turns each new land into a 4/4. " +
      "It wins by having more of everything than the table and swinging with trample.",
    bars: { speed: 2, complexity: 3, interaction: 2, resilience: 3, pilot: 2 },
    curve: [9, 13, 18, 7, 7, 3, 5],
    signature: [
      { n: "Tatyova, Benthic Druid", art: "tatyova-benthic-druid", why: "A second Aesi. Every land is a card and a life." },
      { n: "Avenger of Zendikar", art: "avenger-of-zendikar", why: "Turns thirty-seven lands into a board in one cast." },
      { n: "Rampaging Baloths", art: "rampaging-baloths", why: "Every land after this one is a 4/4." },
      { n: "Explosive Vegetation", art: "explosive-vegetation", why: "Two lands at once, and lands are the engine." },
    ],
    engine: "playable",
    swaps: 5,
    swapNote:
      "5 cards swapped for engine-supported equivalents — Scute Swarm, Rhystic Study, Cyclonic Rift, Ancient Greenwarden and Oracle of Mul Daya each need a rules feature the engine does not implement yet.",
  },

  {
    id: "edgar",
    name: "Edgar Markov",
    short: "Edgar",
    ci: ["W", "B", "R"], guild: "Mardu", cards: 100, lands: 37,
    cmd: {
      n: "Edgar Markov", cost: "3RWB", tl: "Legendary Creature — Vampire Knight",
      t: "creature", f: "gold", pt: "4/4", kw: "First strike",
      rules: "First strike. Eminence — Whenever you cast another Vampire spell, if Edgar Markov is in the command zone or on the battlefield, create a 1/1 black Vampire creature token. Whenever Edgar Markov attacks, put a +1/+1 counter on each Vampire you control.",
      art: "edgar-markov", artist: "Volkan Baǵa",
    },
    tags: ["Aggro", "Tokens", "Drain"],
    blurb: "Mardu vampire aggro. Eminence makes a token every time a Vampire is cast, lords make the swarm lethal, and drain effects convert every death and life gain into damage.",
    strategy:
      "Eminence works from the command zone, so the deck is attacking before Edgar is ever cast — every one- and two-drop Vampire brings a token with it. " +
      "Twenty-one two-drops is not an accident; the curve is built to empty a hand by turn four and then find lords. " +
      "Legion Lieutenant and Sanctum Seeker turn a wide board into a lethal one, and Blood Artist means chump blocks do not save anybody. " +
      "It is the fastest clock of the four and the least able to recover if the board is swept.",
    bars: { speed: 4, complexity: 2, interaction: 3, resilience: 2, pilot: 2 },
    curve: [15, 21, 11, 3, 9, 2, 1],
    signature: [
      { n: "Sanctum Seeker", art: "sanctum-seeker", why: "Every attacking Vampire drains, whether or not it connects." },
      { n: "Legion Lieutenant", art: "legion-lieutenant", why: "The lord that makes a board of 1/1 tokens lethal." },
      { n: "Blood Artist", art: "blood-artist", why: "Turns a board wipe into the winning turn." },
      { n: "Falkenrath Noble", art: "falkenrath-noble", why: "A second Blood Artist, in the air." },
    ],
    engine: "playable",
    swaps: 7,
    swapNote:
      "7 cards swapped for engine-supported equivalents — Captivating Vampire, Vampire Nocturnus, Bloodline Keeper and Shared Animosity need unimplemented rules features; Anguished Unmaking, Mortify and Bedevil need target selectors the engine cannot express yet.",
  },

  {
    id: "first-flight",
    name: "First Flight",
    short: "First Flight",
    ci: ["W", "U"], guild: "Azorius", cards: 100, lands: null,
    cmd: {
      n: "Isperia, Supreme Judge", cost: "2WWUU", tl: "Legendary Creature — Sphinx",
      t: "creature", f: "gold", pt: "6/4", kw: "Flying",
      rules: "Flying. Whenever a creature attacks you or a planeswalker you control, you may draw a card.",
      art: "isperia-supreme-judge", artist: "Scott M. Fischer",
    },
    tags: ["Flyers", "Anthems", "Card draw"],
    blurb: "Azorius skies. A low, evasive board that anthems itself upward, and a commander who charges the table for attacking into it.",
    strategy:
      "The deck goes wide in the air with cheap flyers and then makes them all bigger at once — Empyrean Eagle and Favorable Winds are two of several anthems that only read on things with flying. " +
      "Isperia is the punishment half: once she is down, attacking you costs a card, so the pod's aggro deck goes and hits somebody else. " +
      "It plays a longer, more defensive game than Edgar and wins in two or three swings from a board the ground cannot block.",
    bars: { speed: 2, complexity: 2, interaction: 3, resilience: 3, pilot: 2 },
    curve: null,
    signature: [
      { n: "Empyrean Eagle", art: "empyrean-eagle", why: "An anthem attached to a flyer — the deck's whole shape in one card." },
      { n: "Watcher of the Spheres", art: "watcher-of-the-spheres", why: "Makes the rest of the curve a mana cheaper." },
      { n: "Favorable Winds", art: "favorable-winds", why: "Two mana, and every creature in the deck gets bigger." },
    ],
    engine: "preview",
    swaps: 0,
    swapNote: null,
  },

  {
    id: "zurgo",
    name: "Zurgo Stormrender",
    short: "Zurgo",
    ci: ["B", "R", "W"], guild: "Mardu", cards: 100, lands: null,
    cmd: {
      n: "Zurgo Stormrender", cost: "RWB", tl: "Legendary Creature — Orc Warrior",
      t: "creature", f: "gold", pt: "3/3", kw: "Mobilize 1",
      rules: "Mobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.) Whenever a creature token you control leaves the battlefield, draw a card if it was attacking. Otherwise, each opponent loses 1 life.",
      art: "zurgo-stormrender", artist: "Lie Setiawan",
    },
    tags: ["Tokens", "Attacking", "Sacrifice"],
    blurb: "Mardu mobilize. Attacking makes tokens, the tokens are meant to die, and Zurgo turns each death into a card or a point of drain.",
    strategy:
      "Zurgo costs three and wants to attack immediately — mobilize means every attack is wider than the board looks, and the tokens are built to be sacrificed at end of turn anyway. " +
      "The second half of his text is the engine: an attacking token that dies draws a card, and any other token that dies drains the table. " +
      "So the deck is happy to trade tokens into blockers, and happier to have a free sacrifice outlet like Goblin Bombardment that converts a whole attack step into damage and cards. " +
      "It plays like Edgar with a rate-limiter removed, at the cost of needing an attack every turn to do anything.",
    bars: { speed: 3, complexity: 3, interaction: 2, resilience: 2, pilot: 3 },
    curve: null,
    signature: [
      { n: "Mardu Ascendancy", art: "mardu-ascendancy", why: "A second mobilize, on every nontoken attacker." },
      { n: "Mardu Hordechief", art: "mardu-hordechief", why: "Raid rewards the attack the deck was making anyway." },
      { n: "Goblin Bombardment", art: "goblin-bombardment", why: "The free outlet. Every token becomes damage and a card." },
    ],
    engine: "preview",
    swaps: 0,
    swapNote: null,
  },
];

// ---------------------------------------------------------------------------
// The custom slot
//
// Every mockup fakes the whole Moxfield round trip: paste -> 700ms "fetching"
// -> one canned result. Pasting something that is not a moxfield.com/decks URL
// gives the error instead. The error state matters more than the happy path,
// because it is the state the real feature will spend its life in.

const CUSTOM = {
  placeholder: "https://moxfield.com/decks/...",
  hint: "Paste a public Moxfield deck link.",
  fake: {
    id: "custom-vorel",
    name: "Vorel of the Hull Clade",
    short: "Vorel",
    ci: ["G", "U"], guild: "Simic", cards: 100, lands: 36,
    cmd: {
      n: "Vorel of the Hull Clade", cost: "1GU", tl: "Legendary Creature — Human Merfolk",
      t: "creature", f: "gold", pt: "1/4",
      rules: "{1}{G}{U}, {T}: Double the number of each kind of counter on target artifact, creature, or land you control.",
      art: "vorel-of-the-hull-clade", artist: "Mike Bierek",
    },
    tags: ["Counters", "Ramp", "Combo"],
    blurb: "Imported from Moxfield. Simic +1/+1 counters, doubled.",
    strategy: "Imported decks have no editorial write-up — this is whatever you built.",
    bars: { speed: 2, complexity: 4, interaction: 2, resilience: 2, pilot: 4 },
    curve: [8, 15, 16, 12, 6, 4, 3],
    signature: [],
    engine: "partial",
    unsupported: 12,
    swaps: 0,
    swapNote: null,
  },
  errors: {
    badUrl: "That is not a Moxfield deck link.",
    private: "That deck is private. Set it to public and try again.",
  },
};

const OPPONENTS = [1, 2, 3];

// ---------------------------------------------------------------------------
// Rooms
//
// docs/roadmap.md's backlog asks for "multiplayer online support using a basic
// system of rooms and room codes". It does not need a second screen, and giving
// it one is how products end up with two menus. It needs one new idea: a SEAT
// has a kind.
//
//   cpu    an engine opponent, at `tier`
//   open   an empty chair holding the room code, waiting for a person
//   human  somebody joined; `ready` is whether they have locked their deck in
//
// All-CPU, all-human and mixed pods are then the same screen with different
// seats in it, and "fill empty chairs with CPU" -- one toggle -- is both the
// partial-pod case and the backfill-on-disconnect case.
//
// One rule worth stating because it is a design decision and not an oversight:
// a human's dossier is sealed until they lock in. Reading a list before the
// game is scouting, and scouting before mulligans is exactly what a competitive
// lobby hides. A CPU's dossier is always readable -- it has nothing to protect.

const ROOM = {
  code: "GYRE-8412",
  // Canned. Opening a chair "invites" one scripted player who arrives and then
  // locks in; there is no network in a mockup and there never will be.
  guest: { name: "Priya", deckId: "edgar" },
  joinMs: 1200,
  readyMs: 2600,
};

// The seat shape every mockup keeps in `state.seats`, one entry per opponent:
//
//   { kind: "cpu",   tier?: "duelist" }      tier omitted = follow the pod tier
//   { kind: "open" }                         holding the code, nobody in it yet
//   { kind: "human", name, deckId, ready }   ready gates whether the deck reads
//
// plus `state.fillCpu`, the one toggle that decides whether an open chair
// blocks the start or gets a CPU dropped into it.

// ---------------------------------------------------------------------------
// Art resolution is a hard ceiling, and it is a layout constraint, not a
// fetching problem.
//
// Scryfall's `art_crop` is 626x457 and it is the only art-ONLY asset published.
// `large` (672x936) and `png` (745x1040) are bigger but they are whole cards;
// the art band inside them measures ~655px. Measured, not assumed -- every
// variant the API returns was downloaded and sized while building these.
//
// So no importer can make the art sharper, and the rule the mockups follow is:
//
//   never render a crop above ~1.25x native (about 780px wide);
//   any field bigger than that is blurred ON PURPOSE and carries no detail;
//   something crisp -- a card face, or an art band at its own aspect -- is
//   layered on top at or below 1x.
//
// The first drafts of 01, 02 and 05 all broke this. 02 was the worst: a
// portrait deck box covered with a landscape crop scaled by height, 2.56x.

const ART_NATIVE = { w: 626, h: 457 };
