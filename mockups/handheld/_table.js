/*
 * The rest of the application. 06 only.
 *
 * NOT LOADED -- `inline.py` splices it into `06-one-thumb.html`, and skips any
 * file that does not declare the markers. Companion to `_handheld.js`, which
 * carries the board state, the card face and the Pad layer that all six share.
 *
 * WHY THIS FILE EXISTS. 01-05 each argued about one control scheme and drew
 * only as much of the app as that argument needed. The round's own verdict on
 * them was that they are "heavily compromised ways of what's shown in the UI
 * today" -- choosing a CPU's deck, importing from Moxfield, looking in a
 * graveyard, answering a modal question -- and that is a fair hit. 06 has to
 * reach EVERY surface the shipped client has, so the fixtures for those
 * surfaces live here.
 *
 * Cross-checked against the components that actually exist:
 *
 *   lobby/  HomeScreen · PodLobby · PodSeat · DeckCatalog · DeckDossier
 *           InviteDialog · ReadyTrack · CommanderCard · CardBack · Mark
 *   menu/   DeckImport
 *   game/   Table · ActionPanel · PlayerOrb · CommandZone · StackPanel
 *           EventTicker · ZonePeek · PromptDialog · CardPreview · PhaseTrack
 *           CombatArrows · GameOverScreen · HandFan · Lane · CardStack
 *
 * Every decision kind in `engine/enums.py` has a fixture here, so 06 can prove
 * it answers all eleven rather than the three the earlier five happened to hit.
 */

/* --- The other two seats --------------------------------------------------
   Commander is four-handed. A two-player board was the easy case, and it hid
   the hard one: three opponents plus you, on 800px of height.
------------------------------------------------------------------------- */

const OPP2 = {
  name: "Marco", seat: 2, life: 31, human: true,
  lib: 79, hand: 5, gy: 2, exile: 0, cmd: 1, tax: 0,
  cmdr: {
    n: "Isperia, Supreme Judge", cost: "4WU", tl: "Legendary Creature — Sphinx",
    t: "creature", f: "gold", pt: "6/6", kw: "Flying",
    rules: "Flying. Whenever a creature deals combat damage to you, draw a card.",
    art: "Isperia, Supreme Judge",
  },
  mana: [{ sym: "W", open: 2 }, { sym: "U", open: 2 }, { sym: "W/U", open: 1 }],
  lands: [
    { n: "Plains", tl: "Basic Land — Plains", t: "land", f: "land", land: "W", count: 3 },
    { n: "Island", tl: "Basic Land — Island", t: "land", f: "land", land: "U", art: "Island", count: 2 },
  ],
  creatures: [
    { n: "Empyrean Eagle", cost: "1WU", tl: "Creature — Bird Spirit", t: "creature", f: "gold", pt: "2/3", kw: "Flying",
      rules: "Flying. Other creatures you control with flying get +1/+1.", art: "Empyrean Eagle" },
    { n: "Watcher of the Spheres", cost: "WU", tl: "Creature — Bird Wizard", t: "creature", f: "gold", pt: "2/2", kw: "Flying",
      rules: "Flying. Whenever another creature with flying enters the battlefield under your control, scry 1.", art: "Watcher of the Spheres" },
  ],
  other: [
    { n: "Favorable Winds", cost: "1U", tl: "Enchantment", t: "enchantment", f: "U",
      rules: "Creatures you control with flying get +1/+0.", art: "Favorable Winds" },
  ],
};

const OPP3 = {
  name: "Duelist", seat: 3, life: 18, cpu: "Duelist",
  lib: 88, hand: 3, gy: 9, exile: 2, cmd: 1, tax: 2,
  cmdr: {
    n: "Krenko, Mob Boss", cost: "2RR", tl: "Legendary Creature — Goblin Warrior",
    t: "creature", f: "gold", pt: "3/3",
    rules: "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
    art: "Krenko, Mob Boss",
  },
  mana: [{ sym: "R", open: 4 }],
  lands: [{ n: "Mountain", tl: "Basic Land — Mountain", t: "land", f: "land", land: "R", art: "Mountain", count: 4 }],
  creatures: [
    { n: "Skirk Prospector", cost: "R", tl: "Creature — Goblin", t: "creature", f: "R", pt: "1/1",
      rules: "Sacrifice a Goblin: Add {R}.", art: "Skirk Prospector",
      ability: "Sacrifice a Goblin: Add {R}." },
  ],
  other: [
    { n: "Impact Tremors", cost: "1R", tl: "Enchantment", t: "enchantment", f: "R",
      rules: "Whenever a creature enters the battlefield under your control, Impact Tremors deals 1 damage to each opponent.",
      art: "Impact Tremors" },
  ],
};

/* Commander damage and tax, both rules the client draws and 01-05 never did.
   21 from any one commander kills, which is why it is a per-source count and
   not a total. */
ME.cmdDamage = [{ from: "Edgar Markov", n: 8 }];
ME.tax = 2;
OPP.cmdDamage = [{ from: "Aesi, Tyrant of Gyre Strait", n: 5 }];
OPP.tax = 0;
OPP.human = false;
OPP.cpu = "Apprentice";
OPP2.cmdDamage = [];
OPP3.cmdDamage = [{ from: "Edgar Markov", n: 12 }];

/* Viewer first, then clockwise -- the order `logic/zoneGrouping.ts` seats them
   in, so the pod on screen matches the pod in the engine. */
const TABLE = [ME, OPP, OPP2, OPP3];

/* --- Zones you can look into ---------------------------------------------
   `ZonePeek.tsx` opens graveyard, exile, command and hand, each row carrying a
   "how it got here" note. The note is the part worth keeping: a graveyard is a
   history, not a pile.
------------------------------------------------------------------------- */
ME.graveyard = [
  { n: "Sakura-Tribe Elder", cost: "1G", tl: "Creature — Snake Shaman", t: "creature", f: "G", pt: "1/1",
    art: "Sakura-Tribe Elder", note: "Sacrificed for a land, turn 4" },
  { n: "Beast Within", cost: "2G", tl: "Instant", t: "instant", f: "G",
    art: "Beast Within", note: "Resolved on Bloodcrypt Vault, turn 6" },
  { n: "Explore", cost: "1G", tl: "Sorcery", t: "sorcery", f: "G",
    art: "Explore", note: "Resolved, turn 3" },
];
ME.exileZone = [
  { n: "World Shaper", cost: "3G", tl: "Creature — Merfolk Shaman", t: "creature", f: "G", pt: "3/3",
    art: "World Shaper", note: "Exiled by Bloodcrypt Vault, turn 7" },
];
OPP.graveyard = [
  { n: "Mardu Hordechief", cost: "3W", tl: "Creature — Human Warrior", t: "creature", f: "W", pt: "2/3",
    art: "Mardu Hordechief", note: "Died blocking Aesi, turn 6" },
  { n: "Legion Lieutenant", cost: "WB", tl: "Creature — Vampire Cleric", t: "creature", f: "gold", pt: "2/2",
    art: "Legion Lieutenant", note: "Destroyed by Acidic Slime, turn 7" },
];
OPP.exileZone = [];
OPP2.graveyard = [];
OPP2.exileZone = [];
OPP3.graveyard = [];
OPP3.exileZone = [];

/* --- The stack, non-empty ------------------------------------------------
   `StackPanel.tsx` draws real overlapping faces, top first. Every one of the
   first five stubbed this surface as the word "empty", which is the state it is
   in least often and the only state that needs no design.
------------------------------------------------------------------------- */
const STACK = [
  { sid: 2, kind: "trigger", name: "Impact Tremors", controller: "Duelist",
    description: "Deals 1 damage to each opponent.", card: OPP3.other[0], targets: "each opponent" },
  { sid: 1, kind: "spell", name: "Beast Within", controller: "You",
    description: "Destroy target permanent. Its controller creates a 3/3 green Beast creature token.",
    card: HAND[5], targets: "Falkenrath Noble" },
];

/* --- The difficulty ladder -----------------------------------------------
   Tier 1 is today's `random` agent and tier 3 today's `heuristic`; 2 and 4 are
   `docs/roadmap.md`'s CPU work and do not exist in the engine yet. Each tier
   lights a cumulative prefix of three capability lamps, so the ladder says what
   it turns ON rather than asking you to trust an adjective -- and a count is
   something you read, where "Hard" is something you have to interpret. Lifted
   from ../menu/_menu.js so the two rounds agree.
------------------------------------------------------------------------- */
const CAPS = [
  { id: "combat", n: "Combat math" },
  { id: "removal", n: "Removal & targeting" },
  { id: "seq", n: "Mana & sequencing" },
];

const DIFFICULTY = [
  { id: "goldfish", n: "Goldfish", tag: "Plays solitaire", caps: [], agent: "random",
    line: "Takes legal actions at random. It will not block you, race you, or notice you exist." },
  { id: "apprentice", n: "Apprentice", tag: "Knows the basics", caps: ["combat"], rec: true,
    line: "Blocks when the trade is safe, attacks when the attack is free, and plays to its curve." },
  { id: "duelist", n: "Duelist", tag: "Plays to win", caps: ["combat", "removal"], agent: "heuristic",
    line: "Spends removal on your best threat, keeps a blocker home, and counts to lethal." },
  { id: "archmage", n: "Archmage", tag: "Plays around you", caps: ["combat", "removal", "seq"],
    line: "Sequences its mana, holds up interaction, and plays around the cards you left mana open for." },
];

/* --- The pod --------------------------------------------------------------
   Four chairs and every state one can be in, because `PodSeat.tsx` has four
   kinds and the first five drew one. A chair is: you, another person, a CPU at
   a named tier, an open chair somebody can join, or empty.
------------------------------------------------------------------------- */
const POD = {
  code: "AESI-4417",
  link: "https://commanderblitz.com/?join=AESI-4417",
  seed: "",
  host: true,
  seats: [
    { kind: "you", who: "You", deck: "aesi", locked: false },
    { kind: "human", who: "Marco", deck: "isperia", locked: true },
    { kind: "cpu", who: "Duelist", deck: "krenko", difficulty: "duelist", locked: true },
    { kind: "empty", who: null, deck: null, locked: false },
  ],
};

/* --- Moxfield import ------------------------------------------------------
   `DeckImport.tsx` is paste-a-URL, then a DRY-RUN COVERAGE REPORT, then commit.
   The report is the part that matters and the part a smaller mockup would drop:
   this engine does not implement every card, so an imported deck arrives partly
   simplified, and the screen has to say so BEFORE you agree to play it.
------------------------------------------------------------------------- */
const IMPORT = {
  badUrl: "totally not a deck",
  badMsg: "That does not look like a Moxfield deck link.",
  url: "https://moxfield.com/decks/pQ3n-4Kx0EWv2b",
  report: {
    id: "talrand", name: "Talrand, Sky Summoner", commander: "Talrand, Sky Summoner",
    ci: ["U"], total: 100, playable: 88, simplified: 9, inert: 3,
    notes: [
      { n: "Cyclonic Rift", why: "Overload is not implemented — plays as the single-target half." },
      { n: "Murktide Regent", why: "Delve is not implemented — costs its printed {5}{U}{U}." },
      { n: "Mystic Sanctuary", why: "Enters tapped; its island-count trigger is inert." },
    ],
  },
};

/* --- Every question the engine can ask -----------------------------------
   `engine/enums.py`'s DecisionKind, in full. `PromptDialog.tsx` owns all of
   them except the four it names as handled elsewhere, and its switch is a
   DENYLIST -- so a kind nobody has thought about yet is modal by default. 06
   keeps that property: anything without a special surface falls into the reel,
   which means a new decision kind arrives working rather than arriving blank.
------------------------------------------------------------------------- */
const QUESTIONS = {
  priority: {
    kind: "priority", prompt: "Declare attackers",
    sub: "Three are staged. Add another, take one back, or send them.",
    min_count: 0, max_count: 5, allow_done: true, special: "board",
  },
  declare_blockers: {
    kind: "declare_blockers", prompt: "Declare blockers",
    sub: "Edgar Markov is attacking with three. Assign your untapped creatures.",
    min_count: 0, max_count: 4, allow_done: true, special: "board",
  },
  choose_objects: {
    kind: "choose_objects", prompt: "Choose target permanent",
    sub: "Beast Within destroys it. Its controller creates a 3/3 green Beast.",
    min_count: 1, max_count: 1, allow_done: false, special: "board",
  },
  choose_mode: {
    kind: "choose_mode", prompt: "Choose a mode",
    sub: "Simic Charm — choose one.",
    min_count: 1, max_count: 1, allow_done: false,
    options: [
      { id: "m1", label: "Target creature gets +3/+3 until end of turn", sub: "Aesi survives a Falkenrath Noble block" },
      { id: "m2", label: "Target creature gains hexproof until end of turn", sub: "Answers removal already on the stack" },
      { id: "m3", label: "Return target creature to its owner's hand", sub: "Bounce the Noble instead of killing it" },
    ],
  },
  choose_x: {
    kind: "choose_x", prompt: "How much X?",
    sub: "You can pay up to 11. Eleven buttons would satisfy the one-id-per-action rule and destroy the point of it, so this is a stepper and only the chosen value carries an id — the documented exception.",
    min_count: 0, max_count: 11, allow_done: true, x: 4, special: "stepper",
  },
  may: {
    kind: "may", prompt: "Draw a card?",
    sub: "Aesi, Tyrant of Gyre Strait triggered when you played a land.",
    min_count: 1, max_count: 1, allow_done: false,
    options: [
      { id: "yes", label: "Yes, draw", sub: "Library 72 → 71" },
      { id: "no", label: "No", sub: "Decline the trigger" },
    ],
  },
  choose_player: {
    kind: "choose_player", prompt: "Choose a player",
    sub: "Falkenrath Noble — target opponent loses 1 life and you gain 1.",
    min_count: 1, max_count: 1, allow_done: false,
    // You do not recognise a seat by its name, you recognise it by the thing
    // sitting in its command zone. Drawing the commander is what makes this
    // question answerable at a glance instead of readable in three seconds.
    options: [
      { id: "p1", label: "Edgar Markov", sub: "25 life · 4 creatures · the fastest clock at the table", card: OPP.cmdr },
      { id: "p2", label: "Marco", sub: "31 life · two fliers · holding up two mana", card: OPP2.cmdr },
      { id: "p3", label: "Duelist", sub: "18 life · lowest at the table", card: OPP3.cmdr },
    ],
  },
  mulligan: {
    kind: "mulligan", prompt: "Keep this hand?",
    sub: "Seven cards, three lands, and a two-drop. A mulligan draws seven and puts one on the bottom.",
    min_count: 1, max_count: 1, allow_done: false,
    options: [
      { id: "keep", label: "Keep", sub: "Seven cards" },
      { id: "mull", label: "Mulligan to six", sub: "Draw seven, bottom one" },
    ],
  },
  discard_to_hand_size: {
    kind: "discard_to_hand_size", prompt: "Discard down to seven",
    sub: "You have eight cards at your cleanup step. Choose one to discard.",
    min_count: 1, max_count: 1, allow_done: false, special: "hand",
  },
  commander_zone_change: {
    kind: "commander_zone_change", prompt: "Aesi died. Where does it go?",
    sub: "You may put your commander into the command zone instead of your graveyard.",
    min_count: 1, max_count: 1, allow_done: false,
    options: [
      { id: "cz", label: "Command zone", sub: "Recastable for {4}{G}{U} plus {4} commander tax" },
      { id: "gy", label: "Graveyard", sub: "Stays where your recursion can reach it" },
    ],
  },
};

/* The order the question browser walks, so a reviewer can see all eleven
   without having to play a game that reaches each one. */
const QUESTION_ORDER = [
  "choose_mode", "choose_x", "may", "choose_player",
  "mulligan", "discard_to_hand_size", "commander_zone_change",
];

/* --- The tools ------------------------------------------------------------
   `ActionPanel.tsx`'s tool strip. Three of the five are MODES rather than
   actions, and all three explain themselves only through a `title=` tooltip
   today -- so on a pad they are unlabelled switches whose meaning is
   unreachable. Each carries its explanation as real text here.
------------------------------------------------------------------------- */
const TOOLS = [
  { id: "fullControl", n: "Priority", off: "Auto-pass", on: "Full control", mode: true,
    line: "Auto-pass skips the priority windows where you have nothing worth doing. Full control stops at every one of them." },
  { id: "manualMana", n: "Mana", off: "Auto mana", on: "Manual mana", mode: true,
    line: "Auto mana lets the payment solver choose which lands to tap. Manual mana hands you the choice, and the responsibility." },
  { id: "muted", n: "Sound", off: "Sound on", on: "Muted", mode: true,
    line: "Card and effect sounds." },
  /* Not a mode and not an action -- a CYCLE, because three settings is one more
     than a switch can hold. `prefers-reduced-motion` picks the default and this
     is the ceiling: Balatro ships a speed control on its main menu, and both
     Hearthstone and Slay the Spire grew one, for a reason that is not
     accessibility -- on the tenth game you already know what an attack looks
     like. Making it a real toggle is also the only way the reduced path ever
     gets run: a media query nobody can flip is a code path nobody has tested. */
  { id: "motion", n: "Animation", cycle: ["full", "swift", "reduced"],
    line: "Full plays every beat at the timing it was tuned at. Swift is the same choreography at 55%. Reduced skips animation entirely, which is what your system setting selects." },
  { id: "undo", n: "Undo", act: true,
    line: "Takes back your last action. Unavailable once an opponent has acted." },
  { id: "concede", n: "Concede", act: true, danger: true,
    line: "Leaves the game. The pod carries on without you." },
];

/* --- Game over ------------------------------------------------------------
   `GameOverScreen.tsx` gives a per-player loss reason, which is what makes a
   Commander game legible after the fact -- "you won" says nothing about how the
   other three went out.
------------------------------------------------------------------------- */
const RESULT = {
  winner: "You",
  line: "Aesi, Tyrant of Gyre Strait connected for lethal commander damage on turn 11.",
  players: [
    { who: "You", how: "Won — 34 life remaining" },
    { who: "Edgar Markov", how: "Lost — 21 commander damage from Aesi" },
    { who: "Marco", how: "Lost — life total reached 0, turn 10" },
    { who: "Duelist", how: "Lost — drew from an empty library, turn 9" },
  ],
};
