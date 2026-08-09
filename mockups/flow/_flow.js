/*
 * SNAP KEEP -- the content every flow mockup renders.
 *
 * NOT LOADED BY THE MOCKUPS. Each .html file is required to open standalone from
 * file://, so this file is inlined into each one rather than linked. It is kept
 * here as the single readable copy: edit this, then re-inline. Same contract as
 * ../_state.js, ../menu/_menu.js and ../cards/_cards.js.
 *
 * WHAT CHANGED FROM ../menu/_menu.js, and why
 *
 * 1. PRECONS (4) became DECKS (25). The menu round showed the catalogue the repo
 *    ships. A browse surface is only a design problem above about a dozen decks
 *    -- below that it is a list and there is nothing to decide -- so the flow
 *    round draws the catalogue at its post-"All Card Support" size (roadmap.md
 *    :6-16). Twenty commanders were added for COLOUR SPREAD rather than power,
 *    because colour identity is the one filter a Commander player reaches for
 *    and it needs a mono, a pair, a wedge and a five-colour deck to bite on.
 *
 * 2. A deck has a `source`. The menu README's fifth complaint was that "the
 *    screen has no vocabulary for where a deck came from"; `precon` vs `yours`
 *    is that vocabulary, and it is the catalogue's second filter.
 *
 * 3. ROOM became POD, and READINESS IS SYMMETRIC. In 03-pod-lobby.html only the
 *    remote guest locked in; you pressed Play whenever you liked. Here you lock
 *    in too, and Start is the pod completing rather than a button you were
 *    always allowed to press. That is the whole point of "lock in your seat",
 *    and it is also what makes the host not privileged over the guests in
 *    anything except who presses the last button.
 *
 * WHAT IS REAL, AND WHAT IS AUTHORED. Every commander here is a real card: name,
 * mana cost, type line, oracle text, power/toughness, art and artist all come
 * from Scryfall via ../fetch_art.py. Aesi and Edgar carry real deck data out of
 * data/decks/*.deck.json -- their blurbs are those files' own `notes`, their
 * curves were counted from the real lists, their swap notes are the real
 * `reason` strings. The other twenty-three have NO deck list in this repo, so:
 *
 *   - `bars`, `tags`, `blurb` and `strategy` are authored editorial judgement.
 *     Legitimate: these are opinions about an archetype, not measurements.
 *   - `curve` and `lands` are null. A curve is a count of a list that does not
 *     exist, and inventing one would be the single lie on the screen. The
 *     dossier draws the honest hole instead.
 */

// Card-face shorthand, unchanged from ../_state.js:
// n=name cost tl=type line t=type tone f=frame tone pt kw=keywords rules
// art=slug in ../art/  artist

// ---------------------------------------------------------------------------
// Difficulty -- carried over from ../menu/_menu.js unchanged.
//
// Four tiers. Tier 1 is today's `random` agent and tier 3 is today's
// `heuristic`; tiers 2 and 4 are the roadmap's CPU work (roadmap.md:30-45) and
// do not exist in the engine yet. Each tier lights a cumulative prefix of three
// capability lamps, drawn filled/hollow -- so the ladder says what it turns on
// rather than asking you to trust an adjective, and reads without colour.

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

// The catalogue's own facets. Colour identity first, because it is the filter a
// Commander player actually reaches for; source second, because "is this mine or
// did it ship with the game" is the axis the old menu could not express at all.
const COLOURS = [
  ["W", "White"], ["U", "Blue"], ["B", "Black"], ["R", "Red"], ["G", "Green"],
];

const SORTS = [
  { id: "name", n: "Name" },
  { id: "speed", n: "Fastest" },
  { id: "complexity", n: "Most complex" },
  { id: "pilot", n: "Easiest to pilot", invert: true },
];

// ---------------------------------------------------------------------------
// The catalogue
//
// ENGINE HONESTY, restated for twenty-five decks. The menu round's rule was "a
// preview deck can be chosen but not dealt, and never sits in an opponent's
// chair". Applied literally to a catalogue this size it makes twenty-three decks
// un-startable and the flow undemonstrable, which would be a mockup that is
// honest about the engine by being useless about the design.
//
// So the catalogue is drawn at its post-"All Card Support" size, every file says
// so on screen, and the three engine states stay visible where they matter:
//
//   playable  the engine can deal it. Aesi and Edgar are true today; the rest
//             are true the day roadmap.md:6-16 lands.
//   preview   in the catalogue, not dealable. Two decks keep this, and they are
//             the two whose commanders need rules the engine cannot express --
//             Gishath's reveal-and-put-onto-the-battlefield and Yuriko's
//             commander ninjutsu. Chosen on mechanics, not at random.
//   partial   an import whose unsupported cards were dropped. See CUSTOM.

const DECKS = [
  // -- The four the menu round wrote by hand. Real deck data; unchanged. ------
  {
    id: "aesi",
    name: "Aesi, Tyrant of Gyre Strait",
    short: "Aesi",
    ci: ["G", "U"], guild: "Simic", cards: 100, lands: 37, source: "precon",
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
    engine: "playable", swaps: 5,
    swapNote:
      "5 cards swapped for engine-supported equivalents — Scute Swarm, Rhystic Study, Cyclonic Rift, Ancient Greenwarden and Oracle of Mul Daya each need a rules feature the engine does not implement yet.",
  },

  {
    id: "edgar",
    name: "Edgar Markov",
    short: "Edgar",
    ci: ["W", "B", "R"], guild: "Mardu", cards: 100, lands: 37, source: "precon",
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
    engine: "playable", swaps: 7,
    swapNote:
      "7 cards swapped for engine-supported equivalents — Captivating Vampire, Vampire Nocturnus, Bloodline Keeper and Shared Animosity need unimplemented rules features; Anguished Unmaking, Mortify and Bedevil need target selectors the engine cannot express yet.",
  },

  {
    id: "first-flight",
    name: "First Flight",
    short: "First Flight",
    ci: ["W", "U"], guild: "Azorius", cards: 100, lands: null, source: "precon",
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
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "zurgo",
    name: "Zurgo Stormrender",
    short: "Zurgo",
    ci: ["W", "B", "R"], guild: "Mardu", cards: 100, lands: null, source: "precon",
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
    engine: "playable", swaps: 0, swapNote: null,
  },

  // -- Five colours ---------------------------------------------------------
  {
    id: "ur-dragon",
    name: "The Ur-Dragon",
    short: "Ur-Dragon",
    ci: ["W", "U", "B", "R", "G"], guild: "Five-colour", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "The Ur-Dragon", cost: "4WUBRG", tl: "Legendary Creature — Dragon Avatar",
      t: "creature", f: "gold", pt: "10/10", kw: "Flying",
      rules: "Eminence — As long as The Ur-Dragon is in the command zone or on the battlefield, other Dragon spells you cast cost {1} less to cast. Flying. Whenever one or more Dragons you control attack, draw that many cards, then you may put a permanent card from your hand onto the battlefield.",
      art: "the-ur-dragon", artist: "Jaime Jones",
    },
    tags: ["Tribal", "Big mana", "Flyers"],
    blurb: "Every Dragon ever printed, in one deck. Eminence discounts them from the command zone, and an attack refills your hand and puts a free permanent onto the battlefield.",
    strategy:
      "This is the most expensive deck in the catalogue and it does not pretend otherwise — the first six turns are ramp, fixing and one discounted Dragon. " +
      "What it buys is a board where every attack draws cards equal to the number of Dragons swinging and then deploys a permanent for free, so one connected attack step usually ends the game's competitive phase. " +
      "It is slow, it is obvious, and every table will point removal at it, which is exactly what makes it the pod's best lightning rod.",
    bars: { speed: 1, complexity: 3, interaction: 2, resilience: 3, pilot: 2 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  // -- Four colours ---------------------------------------------------------
  {
    id: "atraxa",
    name: "Atraxa, Praetors' Voice",
    short: "Atraxa",
    ci: ["W", "U", "B", "G"], guild: "Witch-Maw", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Atraxa, Praetors' Voice", cost: "GWUB", tl: "Legendary Creature — Phyrexian Angel Horror",
      t: "creature", f: "gold", pt: "4/4", kw: "Flying, vigilance, deathtouch, lifelink",
      rules: "Flying, vigilance, deathtouch, lifelink. At the beginning of your end step, proliferate.",
      art: "atraxa-praetors-voice", artist: "Victor Adame Minguez",
    },
    tags: ["Counters", "Proliferate", "Value"],
    blurb: "Four colours of counters. Every +1/+1, loyalty and charge counter on the board grows again at the end of every one of your turns, for free, forever.",
    strategy:
      "Atraxa's body would be a fine commander on its own — four keywords for four mana — and the proliferate trigger is the actual deck. " +
      "Anything that enters with counters becomes an engine: planeswalkers ultimate two turns early, creatures outgrow the table, and Doubling Season turns a single trigger into a doubling. " +
      "The weakness is the obvious one: it is a four-colour deck that wants to untap with a four-drop, so the first six turns are lands and the game is decided by whether Atraxa survives one rotation.",
    bars: { speed: 2, complexity: 4, interaction: 2, resilience: 3, pilot: 3 },
    curve: null,
    signature: [
      { n: "Doubling Season", art: "doubling-season", why: "Every counter and every token arrives twice." },
      { n: "Deepglow Skate", art: "deepglow-skate", why: "One cast doubles every counter on the board at once." },
      { n: "Vorinclex, Monstrous Raider", art: "vorinclex-monstrous-raider", why: "Doubles yours and halves theirs — a proliferate deck's best and rudest card." },
    ],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "omnath",
    name: "Omnath, Locus of Creation",
    short: "Omnath",
    ci: ["W", "U", "R", "G"], guild: "Ink-Treader", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Omnath, Locus of Creation", cost: "RGWU", tl: "Legendary Creature — Elemental",
      t: "creature", f: "gold", pt: "4/4",
      rules: "When Omnath enters, draw a card. Landfall — Whenever a land you control enters, you gain 4 life if this is the first time this ability has resolved this turn. If it's the second time, add {R}{G}{W}{U}. If it's the third time, Omnath deals 4 damage to each opponent and each planeswalker you don't control.",
      art: "omnath-locus-of-creation", artist: "Chris Rahn",
    },
    tags: ["Landfall", "Ramp", "Reach"],
    blurb: "Landfall that counts to three. The first land gains you life, the second refunds four mana, the third burns the table — and the deck exists to hit all three every turn.",
    strategy:
      "Everything here is a land or a way to play an extra one. The third landfall trigger is the win condition and the second is how you pay for it: four mana back on the second land drop means the turn you go off is not the turn you stop. " +
      "It is a genuinely hard deck to sequence, because the order you play lands in decides whether the burn trigger happens this turn or next. " +
      "Play the fetch-effects before the untapped ones, and count before you commit.",
    bars: { speed: 3, complexity: 4, interaction: 2, resilience: 2, pilot: 4 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  // -- Three colours --------------------------------------------------------
  {
    id: "kaalia",
    name: "Kaalia of the Vast",
    short: "Kaalia",
    ci: ["W", "B", "R"], guild: "Mardu", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Kaalia of the Vast", cost: "1RWB", tl: "Legendary Creature — Human Cleric",
      t: "creature", f: "gold", pt: "2/2", kw: "Flying",
      rules: "Flying. Whenever Kaalia attacks an opponent, you may put an Angel, Demon, or Dragon creature card from your hand onto the battlefield tapped and attacking that opponent.",
      art: "kaalia-of-the-vast", artist: "Justyna Dura",
    },
    tags: ["Cheat", "Flyers", "Aggro"],
    blurb: "A four-mana 2/2 that puts a nine-mana Angel into play attacking. The whole deck is the biggest things in Mardu and one creature who does not pay for them.",
    strategy:
      "Kaalia costs four and the deck's average creature costs eight, which is the joke and the plan. Attack, trigger, drop a Demon, and the maths of the game changes in one step. " +
      "It is the most explosive opening in the catalogue and the most fragile: Kaalia is a 2/2, everybody at the table knows what she does, and a single removal spell on the attack trigger costs you the turn and the card. " +
      "Hold a protection spell before you commit, or accept that you are drawing removal off the top for the rest of the game.",
    bars: { speed: 4, complexity: 2, interaction: 2, resilience: 1, pilot: 3 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "muldrotha",
    name: "Muldrotha, the Gravetide",
    short: "Muldrotha",
    ci: ["U", "B", "G"], guild: "Sultai", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Muldrotha, the Gravetide", cost: "3BGU", tl: "Legendary Creature — Elemental Avatar",
      t: "creature", f: "gold", pt: "6/6",
      rules: "During each of your turns, you may play a land and cast a permanent spell of each permanent type from your graveyard.",
      art: "muldrotha-the-gravetide", artist: "Jason Rainville",
    },
    tags: ["Graveyard", "Value", "Grind"],
    blurb: "Your graveyard is a second hand. One land, one creature, one artifact, one enchantment out of the yard every single turn, and self-mill is card advantage.",
    strategy:
      "Muldrotha turns the two things every deck hates — milling yourself and losing permanents — into the resource the deck runs on. Sakura-Tribe Elder is a land every turn; a sacrificed artifact comes straight back. " +
      "The correct way to play it is not to hold cards but to spend them, because a card in the graveyard is a card you get to use again and a card in hand is not. " +
      "It never wins fast. It wins by being the only player at the table with resources on turn fourteen.",
    bars: { speed: 1, complexity: 4, interaction: 3, resilience: 4, pilot: 4 },
    curve: null,
    signature: [
      { n: "World Shaper", art: "world-shaper", why: "Mills you on attack, then returns every land you milled." },
      { n: "Ramunap Excavator", art: "ramunap-excavator", why: "Makes Muldrotha's land clause matter every single turn." },
      { n: "Sakura-Tribe Elder", art: "sakura-tribe-elder", why: "A land, a blocker and a recursion target, over and over." },
    ],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "chulane",
    name: "Chulane, Teller of Tales",
    short: "Chulane",
    ci: ["W", "U", "G"], guild: "Bant", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Chulane, Teller of Tales", cost: "2GWU", tl: "Legendary Creature — Human Druid",
      t: "creature", f: "gold", pt: "2/4", kw: "Vigilance",
      rules: "Vigilance. Whenever you cast a creature spell, draw a card, then you may put a land card from your hand onto the battlefield. {3}, {T}: Return target creature you control to its owner's hand.",
      art: "chulane-teller-of-tales", artist: "Victor Adame Minguez",
    },
    tags: ["Card draw", "Ramp", "Blink"],
    blurb: "Every creature you cast draws a card and puts a land into play. A deck of cheap creatures with enter-the-battlefield triggers, and a commander who never runs out of either.",
    strategy:
      "Chulane makes creature spells free in the only sense that matters: you get the card back and a land besides. So the deck is full of two-mana bodies that do something on the way in, and the turn Chulane resolves is the turn your hand stops shrinking. " +
      "His own activated ability is the second half — bouncing your own creature is how you reuse an enter-the-battlefield trigger, and there are twenty of them in here. " +
      "The deck is a slow, wide, endlessly renewing board that eventually finds something unfair to loop.",
    bars: { speed: 2, complexity: 3, interaction: 2, resilience: 3, pilot: 3 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "kykar",
    name: "Kykar, Wind's Fury",
    short: "Kykar",
    ci: ["W", "U", "R"], guild: "Jeskai", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Kykar, Wind's Fury", cost: "1URW", tl: "Legendary Creature — Bird Wizard",
      t: "creature", f: "gold", pt: "3/3", kw: "Flying",
      rules: "Flying. Whenever you cast a noncreature spell, create a 1/1 white Spirit creature token with flying. Sacrifice a Spirit: Add {R}.",
      art: "kykar-wind-s-fury", artist: "G-host Lee",
    },
    tags: ["Spells", "Tokens", "Combo"],
    blurb: "A spellslinger who leaves a board behind. Every instant and sorcery makes a flying blocker, and every blocker is a red mana when you need one.",
    strategy:
      "The usual problem with a deck of instants and sorceries is that you have nothing on the battlefield when the counterspells run out. Kykar fixes it in one line: cast anything, get a body. " +
      "Those bodies are simultaneously a clock in the air, insurance against the table's aggro deck, and a ritual — sacrificing three Spirits is three red mana toward the turn you go off. " +
      "Play it as a control deck that happens to be attacking for four in the air by turn seven.",
    bars: { speed: 3, complexity: 4, interaction: 4, resilience: 2, pilot: 4 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "gishath",
    name: "Gishath, Sun's Avatar",
    short: "Gishath",
    ci: ["W", "R", "G"], guild: "Naya", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Gishath, Sun's Avatar", cost: "5RGW", tl: "Legendary Creature — Dinosaur Avatar",
      t: "creature", f: "gold", pt: "7/6", kw: "Vigilance, trample, haste",
      rules: "Vigilance, trample, haste. Whenever Gishath deals combat damage to a player, reveal that many cards from the top of your library. Put any number of Dinosaur creature cards from among them onto the battlefield and the rest on the bottom of your library in a random order.",
      art: "gishath-sun-s-avatar", artist: "Zack Stella",
    },
    tags: ["Tribal", "Big creatures", "Snowball"],
    blurb: "Dinosaurs. Gishath has haste, hits for seven, and turns those seven damage into seven cards off the top — every Dinosaur among them arriving for free.",
    strategy:
      "Eight mana is a lot and Gishath is worth it, because he does not need a second turn: haste means the trigger happens the moment he lands, and seven cards deep into a deck that is half Dinosaurs is usually two or three free bodies. " +
      "The deck's whole job before that is ramping to eight and surviving, so it runs more mana creatures than a Naya deck normally would. " +
      "Once he connects, the game is not close.",
    bars: { speed: 2, complexity: 2, interaction: 2, resilience: 2, pilot: 2 },
    curve: null, signature: [],
    engine: "preview", swaps: 0, swapNote: null,
  },

  {
    id: "marchesa",
    name: "Marchesa, the Black Rose",
    short: "Marchesa",
    ci: ["U", "B", "R"], guild: "Grixis", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Marchesa, the Black Rose", cost: "1UBR", tl: "Legendary Creature — Human Wizard",
      t: "creature", f: "gold", pt: "3/3", kw: "Dethrone",
      rules: "Dethrone. Other creatures you control have dethrone. Whenever a creature you control with a +1/+1 counter on it dies, return that card to the battlefield under your control at the beginning of the next end step.",
      art: "marchesa-the-black-rose", artist: "Matt Stewart",
    },
    tags: ["Sacrifice", "Counters", "Recursion"],
    blurb: "Your creatures do not die, they leave and come back. Attack the player who is ahead, collect a counter, and every death from then on is a free recursion.",
    strategy:
      "Dethrone puts a counter on anything that attacks the life leader, and Marchesa's third line turns every creature carrying a counter into a permanent fixture. " +
      "That makes sacrifice outlets into engines and combat into a free roll: trade anything, get it back at end of turn, keep the enter-the-battlefield trigger you got on the way in. " +
      "It is the most politically active deck here — dethrone literally reads 'attack whoever is winning', and a table quickly learns not to be.",
    bars: { speed: 3, complexity: 4, interaction: 3, resilience: 4, pilot: 4 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "prossh",
    name: "Prossh, Skyraider of Kher",
    short: "Prossh",
    ci: ["B", "R", "G"], guild: "Jund", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Prossh, Skyraider of Kher", cost: "3BRG", tl: "Legendary Creature — Dragon",
      t: "creature", f: "gold", pt: "5/5", kw: "Flying",
      rules: "When you cast this spell, create X 0/1 red Kobold creature tokens named Kobolds of Kher Keep, where X is the amount of mana spent to cast it. Flying. Sacrifice another creature: Prossh gets +1/+0 until end of turn.",
      art: "prossh-skyraider-of-kher", artist: "Todd Lockwood",
    },
    tags: ["Tokens", "Sacrifice", "Combo"],
    blurb: "Casting Prossh makes six bodies. Eating them makes him lethal. Every commander tax you pay makes the deck better, which is a sentence no other deck can say.",
    strategy:
      "Prossh is the rare commander who wants to be re-cast: X is the mana spent, so the second cast makes eight Kobolds and the third makes ten. " +
      "Those tokens are food for every sacrifice payoff in Jund and for Prossh himself, who can eat six bodies and swing for eleven in the air out of nowhere. " +
      "The line to watch for is the one where a free sacrifice outlet and a token doubler make the Kobold count arbitrarily large — this deck's ceiling is a genuine combo kill, not just a big attack.",
    bars: { speed: 3, complexity: 3, interaction: 2, resilience: 3, pilot: 3 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  // -- Two colours ----------------------------------------------------------
  {
    id: "yuriko",
    name: "Yuriko, the Tiger's Shadow",
    short: "Yuriko",
    ci: ["U", "B"], guild: "Dimir", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Yuriko, the Tiger's Shadow", cost: "1UB", tl: "Legendary Creature — Human Ninja",
      t: "creature", f: "gold", pt: "1/3",
      rules: "Commander ninjutsu {U}{B}. Whenever a Ninja you control deals combat damage to a player, reveal the top card of your library and put that card into your hand. Each opponent loses life equal to that card's mana value.",
      art: "yuriko-the-tiger-s-shadow", artist: "Yongjae Choi",
    },
    tags: ["Evasion", "Ninjas", "Drain"],
    blurb: "Attack with something nobody can block, swap it for Yuriko, flip an expensive card off the top and drain the whole table for its mana value.",
    strategy:
      "Commander ninjutsu means Yuriko does not have to be cast — a one-mana unblockable creature attacks, and she replaces it already attacking for two black mana. " +
      "The trigger hits every opponent, so the deck is built upside down: expensive cards you never intend to cast are the best cards in it, because the flip drains for their mana value. " +
      "It is the fastest deck in this catalogue and by far the most hated, which is a fair trade for a 1/3.",
    bars: { speed: 4, complexity: 4, interaction: 3, resilience: 2, pilot: 4 },
    curve: null, signature: [],
    engine: "preview", swaps: 0, swapNote: null,
  },

  {
    id: "meren",
    name: "Meren of Clan Nel Toth",
    short: "Meren",
    ci: ["B", "G"], guild: "Golgari", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Meren of Clan Nel Toth", cost: "2BG", tl: "Legendary Creature — Human Shaman",
      t: "creature", f: "gold", pt: "3/4",
      rules: "Whenever another creature you control dies, you get an experience counter. At the beginning of your end step, choose target creature card in your graveyard. If that card's mana value is less than or equal to the number of experience counters you have, return it to the battlefield. Otherwise, put it into your hand.",
      art: "meren-of-clan-nel-toth", artist: "Mark Winters",
    },
    tags: ["Sacrifice", "Graveyard", "Value"],
    blurb: "Death is a resource with a receipt. Every creature that dies grows an experience counter that never goes away, and every end step brings something back.",
    strategy:
      "Experience counters survive Meren dying, which is the detail that makes the deck resilient in a way most graveyard decks are not — killing the commander does not reset the engine, it delays it. " +
      "Early on the end-step trigger returns things to hand; by the time you have five counters it is returning them straight to the battlefield, for free, every turn. " +
      "Feed it cheap creatures with death triggers and a free sacrifice outlet, and it becomes very hard to interact with.",
    bars: { speed: 2, complexity: 3, interaction: 3, resilience: 4, pilot: 3 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "emmara",
    name: "Emmara, Soul of the Accord",
    short: "Emmara",
    ci: ["W", "G"], guild: "Selesnya", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Emmara, Soul of the Accord", cost: "GW", tl: "Legendary Creature — Elf Cleric",
      t: "creature", f: "gold", pt: "2/2",
      rules: "Whenever Emmara becomes tapped, create a 1/1 white Soldier creature token with lifelink.",
      art: "emmara-soul-of-the-accord", artist: "Mark Winters",
    },
    tags: ["Tokens", "Go wide", "Lifegain"],
    blurb: "A two-mana commander that makes a lifelinking body every time she taps — and a deck full of reasons to tap her that have nothing to do with attacking.",
    strategy:
      "Emmara reads 'becomes tapped', not 'attacks', which is the entire deck: convoke, crew, and any tap ability turns her into a token generator that never has to leave the safety of your side of the board. " +
      "From there it is the most straightforward plan in the catalogue — go wide, then play an anthem. " +
      "It is the deck to hand somebody who has never played Commander before, because every card does what it says and none of the decisions are traps.",
    bars: { speed: 3, complexity: 1, interaction: 2, resilience: 3, pilot: 1 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "rakdos-riots",
    name: "Rakdos, Lord of Riots",
    short: "Rakdos",
    ci: ["B", "R"], guild: "Rakdos", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Rakdos, Lord of Riots", cost: "BBRR", tl: "Legendary Creature — Demon",
      t: "creature", f: "gold", pt: "6/6", kw: "Flying, trample",
      rules: "You can't cast Rakdos, Lord of Riots unless an opponent lost life this turn. Flying, trample. Creature spells you cast cost {1} less to cast for each 1 life your opponents have lost this turn.",
      art: "rakdos-lord-of-riots", artist: "Yigit Koroglu",
    },
    tags: ["Big creatures", "Burn", "Cost reduction"],
    blurb: "Deal damage first, then cast everything. One burn spell to the face turns a hand of eight-drops into a hand of free spells.",
    strategy:
      "The restriction is real — you cannot cast Rakdos at all until somebody has lost life — so the deck opens with cheap reach and pingers whose only job is to unlock him. " +
      "After that the discount is per point of life lost across all opponents, which in a four-player pod is enormous: a three-damage sweep is nine mana off the next creature. " +
      "It is a deck that does nothing for five turns and then empties its hand in one, and the skill is entirely in choosing which turn that is.",
    bars: { speed: 3, complexity: 3, interaction: 3, resilience: 2, pilot: 3 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "neyith",
    name: "Neyith of the Dire Hunt",
    short: "Neyith",
    ci: ["R", "G"], guild: "Gruul", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Neyith of the Dire Hunt", cost: "2GG", tl: "Legendary Creature — Human Warrior",
      t: "creature", f: "gold", pt: "3/3",
      rules: "Whenever one or more creatures you control fight or become blocked, draw a card. At the beginning of combat on your turn, you may pay {2}{R/G}. If you do, double target creature's power until end of turn. That creature must be blocked this combat if able.",
      art: "neyith-of-the-dire-hunt", artist: "Magali Villeneuve",
    },
    tags: ["Fight", "Combat", "Card draw"],
    blurb: "Green removal is a fight spell, and Gruul does not normally draw cards. Neyith fixes both: every fight and every block is a card.",
    strategy:
      "The lure half of Neyith's text is the one that wins games — doubling a trampler's power and forcing it to be blocked is removal, damage and a card in one activation. " +
      "The rest of the deck is fight effects, which are simultaneously the colour's removal and this commander's draw engine, so the deck never faces the usual Gruul choice between interacting and keeping cards. " +
      "Straightforward, aggressive, and much better at grinding than red-green usually gets to be.",
    bars: { speed: 3, complexity: 2, interaction: 4, resilience: 2, pilot: 2 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  // -- Mono -----------------------------------------------------------------
  {
    id: "sram",
    name: "Sram, Senior Edificer",
    short: "Sram",
    ci: ["W"], guild: "Mono-white", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Sram, Senior Edificer", cost: "1W", tl: "Legendary Creature — Dwarf Advisor",
      t: "creature", f: "W", pt: "2/2",
      rules: "Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card.",
      art: "sram-senior-edificer", artist: "Chris Rahn",
    },
    tags: ["Voltron", "Equipment", "Card draw"],
    blurb: "One creature, wearing everything. Sram costs two, replaces every Aura and Equipment you cast, and mono-white's job is to make sure the target cannot be answered.",
    strategy:
      "Voltron decks lose to a single removal spell and win when they do not, so this one spends its slots on protection rather than on more Equipment. " +
      "Sram's draw trigger is what makes that affordable: suiting up a creature normally costs you cards, and here it does not cost you any. " +
      "Commander damage is twenty-one, which a well-equipped creature reaches in three swings — the deck is a race between your protection and the table's removal, and it is a fair one.",
    bars: { speed: 3, complexity: 2, interaction: 2, resilience: 1, pilot: 2 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "talrand",
    name: "Talrand, Sky Summoner",
    short: "Talrand",
    ci: ["U"], guild: "Mono-blue", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Talrand, Sky Summoner", cost: "2UU", tl: "Legendary Creature — Merfolk Wizard",
      t: "creature", f: "U", pt: "2/2",
      rules: "Whenever you cast an instant or sorcery spell, create a 2/2 blue Drake creature token with flying.",
      art: "talrand-sky-summoner", artist: "Svetlin Velinov",
    },
    tags: ["Spells", "Control", "Flyers"],
    blurb: "A control deck with a clock. Every counterspell and every cantrip leaves a 2/2 flyer behind, so saying no to the table also builds the board that beats it.",
    strategy:
      "Mono-blue's classic problem is that it can stop everything and kill nothing. Talrand is the answer, and he does not ask you to change a single card in the deck: keep countering, keep drawing, and the Drakes accumulate by themselves. " +
      "Four Drakes is a twenty-turn clock that flies over almost everything the pod can build. " +
      "The deck's difficulty is entirely in knowing which of three opponents' spells is the one worth the counter.",
    bars: { speed: 2, complexity: 3, interaction: 4, resilience: 3, pilot: 3 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "syr-konrad",
    name: "Syr Konrad, the Grim",
    short: "Konrad",
    ci: ["B"], guild: "Mono-black", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Syr Konrad, the Grim", cost: "3BB", tl: "Legendary Creature — Human Knight",
      t: "creature", f: "B", pt: "5/4",
      rules: "Whenever another creature dies, or a creature card is put into a graveyard from anywhere other than the battlefield, or a creature card leaves your graveyard, Syr Konrad deals 1 damage to each opponent. {1}{B}: Each player mills a card.",
      art: "syr-konrad-the-grim", artist: "Anna Steinbauer",
    },
    tags: ["Mill", "Drain", "Graveyard"],
    blurb: "Three separate triggers, all of them common, all of them hitting every opponent. Konrad turns any graveyard on the table — including theirs — into damage.",
    strategy:
      "Read the trigger carefully: any creature dying anywhere, any creature card being milled or discarded by anyone, and any creature leaving your own graveyard. In a four-player game those events happen constantly without you doing anything. " +
      "His own activated ability mills every player, so he is his own engine — with enough mana the ability alone deals damage in a loop. " +
      "The deck wins by attrition against three opponents at once, which is a thing very few commanders can honestly claim.",
    bars: { speed: 2, complexity: 2, interaction: 3, resilience: 3, pilot: 2 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "krenko",
    name: "Krenko, Mob Boss",
    short: "Krenko",
    ci: ["R"], guild: "Mono-red", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Krenko, Mob Boss", cost: "2RR", tl: "Legendary Creature — Goblin Warrior",
      t: "creature", f: "R", pt: "3/3",
      rules: "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
      art: "krenko-mob-boss", artist: "Lie Setiawan",
    },
    tags: ["Tokens", "Go wide", "Aggro"],
    blurb: "Goblins, doubling. Tap Krenko for as many Goblins as you have Goblins, untap him somehow, and do it again — the numbers stop being reasonable on the second activation.",
    strategy:
      "Krenko doubles your Goblin count every time he taps, which means the deck's real cards are the ones that untap him and the ones that give him haste. " +
      "Two activations is usually twelve or more bodies, and mono-red is full of ways to turn a board that wide into damage without attacking at all — Purphoros deals two per token the moment it enters. " +
      "It is the least subtle deck in the catalogue, it folds completely to one board wipe, and it will absolutely kill a table that ignores it for two turns.",
    bars: { speed: 4, complexity: 1, interaction: 1, resilience: 1, pilot: 1 },
    curve: null,
    signature: [
      { n: "Purphoros, God of the Forge", art: "purphoros-god-of-the-forge", why: "Two damage per Goblin, without ever attacking." },
      { n: "Skirk Prospector", art: "skirk-prospector", why: "Turns the swarm into the mana that makes more of it." },
      { n: "Impact Tremors", art: "impact-tremors", why: "Twelve tokens is twelve damage, spread across the table." },
    ],
    engine: "playable", swaps: 0, swapNote: null,
  },

  {
    id: "ezuri",
    name: "Ezuri, Renegade Leader",
    short: "Ezuri",
    ci: ["G"], guild: "Mono-green", cards: 100, lands: null, source: "precon",
    cmd: {
      n: "Ezuri, Renegade Leader", cost: "1GG", tl: "Legendary Creature — Elf Warrior",
      t: "creature", f: "G", pt: "2/2",
      rules: "{G}: Regenerate another target Elf. {2}{G}{G}{G}: Elf creatures you control get +3/+3 and gain trample until end of turn.",
      art: "ezuri-renegade-leader", artist: "Victor Adame Minguez",
    },
    tags: ["Tribal", "Go wide", "Overrun"],
    blurb: "Elves make mana, mana makes more Elves, and Ezuri turns the whole board into a lethal attack for six — repeatably, in one turn, more than once.",
    strategy:
      "Half the creatures here tap for mana, so the deck's mana curve is a lie: a board of six Elves produces enough to cast three more and still activate Ezuri. " +
      "The overrun is what makes it a kill rather than a board — plus three and trample across eight bodies ends a player, and there is nothing stopping you activating it twice. " +
      "It is fast, it is resilient thanks to the regenerate ability, and a single sweeper still undoes the whole thing.",
    bars: { speed: 4, complexity: 2, interaction: 1, resilience: 2, pilot: 2 },
    curve: null, signature: [],
    engine: "playable", swaps: 0, swapNote: null,
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
    ci: ["G", "U"], guild: "Simic", cards: 100, lands: 36, source: "yours",
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
    signature: [], engine: "partial", unsupported: 12, swaps: 0, swapNote: null,
  },
  errors: {
    badUrl: "That is not a Moxfield deck link.",
    private: "That deck is private. Set it to public and try again.",
  },
};

// ---------------------------------------------------------------------------
// The pod
//
// docs/roadmap.md's backlog asks for "multiplayer online support using a basic
// system of rooms and room codes". It does not need a second screen, and giving
// it one is how products end up with two menus. It needs one idea, which the
// menu round established and this one keeps: a SEAT HAS A KIND.
//
//   you    seat 1, always. `ready` is whether you have locked in.
//   cpu    an engine opponent, at `tier`. Ready by construction.
//   open   an empty chair holding the pod code, waiting for a person.
//   human  somebody joined; `ready` is whether they have locked their deck in.
//   empty  no chair at all -- a two- or three-player pod is a legal pod.
//
// All-CPU, all-human and mixed pods are then the same screen with different
// seats in it, and "fill empty chairs with CPU" -- one toggle -- is both the
// partial-pod case and the backfill-on-disconnect case.
//
// TWO RULES worth stating because they are decisions, not oversights:
//
// 1. A human's deck is SEALED until they lock in. Reading a list before the
//    game is scouting, and scouting before mulligans is exactly what a lobby
//    hides. A CPU's dossier is always readable -- it has nothing to protect.
//
// 2. READINESS IS SYMMETRIC. You lock in like everybody else, and Start is the
//    pod completing rather than a button the host may press at any time. The
//    menu round got this wrong: its guest locked in and its host did not, which
//    made the host's own deck choice the one commitment on the screen that
//    could be silently changed after everybody else had committed.

const POD = {
  code: "GYRE-8412",
  // Shown so the invite has something to copy. Never fetched; there is no
  // network in a mockup and there never will be.
  link: "snapkeep.app/j/GYRE-8412",
  // Canned. Opening a chair "invites" a scripted player who arrives and then
  // locks in. Two of them, so a pod can be watched filling from both sides.
  guests: [
    { name: "Priya", deckId: "edgar" },
    { name: "Marco", deckId: "krenko" },
  ],
  joinMs: 1200,
  readyMs: 2600,
};

// The seat shape every mockup keeps in `state.seats`, four entries, index 0 you:
//
//   { kind: "you",   deckId, ready }
//   { kind: "cpu",   tier, deckId }           tier omitted = follow the pod tier
//   { kind: "open" }                          holding the code, nobody in it yet
//   { kind: "human", name, deckId, ready }    ready gates whether the deck reads
//   { kind: "empty" }                         no chair here
//
// plus `state.fillCpu`, the one toggle that decides whether an open chair
// blocks the start or gets a CPU dropped into it.

// ---------------------------------------------------------------------------
// Art resolution is a hard ceiling, and it is a layout constraint, not a
// fetching problem.
//
// Scryfall's `art_crop` is 626x457 and it is the only art-ONLY asset published.
// `large` (672x936) and `png` (745x1040) are bigger but they are whole cards;
// the art band inside them measures ~655px. Measured, not assumed.
//
// So no importer can make the art sharper, and the rule the mockups follow is:
//
//   never render a crop above ~1.25x native (about 780px wide);
//   any field bigger than that is blurred ON PURPOSE and carries no detail;
//   something crisp -- a card face, or an art band at its own aspect -- is
//   layered on top at or below 1x.
//
// This matters more here than it did in the menu round, because a catalogue of
// twenty-five tiles is twenty-five chances to upscale a crop. The tile art box
// is deliberately small.

const ART_NATIVE = { w: 626, h: 457 };
