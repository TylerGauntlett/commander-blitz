/*
 * The cards every card-face prototype draws.
 *
 * NOT LOADED BY index.html. Like mockups/_state.js, this is the readable master
 * and is inlined into the page rather than linked, because the page must open
 * standalone from file://. Edit this, then re-inline.
 *
 * Field shorthand is _state.js's, unchanged, so the two files stay comparable:
 *
 *   n=name  cost=mana cost, braceless  tl=type line  t=type tone  f=frame tone
 *   land=produced-colour tone  produces=symbols  pt=power/toughness  kw=keywords
 *   rules=oracle text  tapped sick cmd token  art=slug in ../art/  dmg=damage
 *   counters=counter badge  why=what this card is here to break
 *
 * These are real cards from data/cards/*.json -- costs, type lines, P/T and
 * oracle text are the shipped ones. The set is picked to *break* layouts rather
 * than to flatter them; `why` is shown on the page under the card picker.
 *
 * `art: null` means the card has no printing anywhere and must draw the
 * text-frame fallback. Five of the 138 non-token cards across both decks are
 * like this -- see mockups/README.md.
 */

const CARDS = [
  {
    key: "aesi",
    why: "Longest name in the pool, against a 3-symbol cost. This is the collision the redesign exists for.",
    n: "Aesi, Tyrant of Gyre Strait", cost: "4GU",
    tl: "Legendary Creature — Serpent", t: "creature", f: "gold",
    pt: "5/5", kw: "Trample", cmd: true, art: "aesi-tyrant-of-gyre-strait",
    rules: "Trample\nWhenever you play a land, draw a card.\nYou may play an additional land on each of your turns.",
  },
  {
    key: "leviathan",
    why: "No printing anywhere — the text-frame fallback. Also the widest cost in the pool at 7 pips.",
    n: "Gyre Strait Leviathan", cost: "5UU",
    tl: "Creature — Leviathan", t: "creature", f: "U",
    pt: "7/7", kw: "Trample", art: null,
    rules: "Trample",
  },
  {
    key: "slime",
    why: "Everything a battlefield creature can be wearing at once: keyword, counters, damage marked, summoning sick.",
    n: "Acidic Slime", cost: "3GG",
    tl: "Creature — Ooze", t: "creature", f: "G",
    pt: "2/2", kw: "Deathtouch", sick: true, art: "acidic-slime",
    dmg: 1, counters: "+1/+1 ×2",
    rules: "Deathtouch\nWhen Acidic Slime enters, destroy target artifact, enchantment, or land.",
  },
  {
    key: "forest",
    why: "The basic land. Forty percent of a board is these, and today they are the least designed card on screen.",
    n: "Forest", cost: "",
    tl: "Basic Land — Forest", t: "land", f: "land",
    land: "G", produces: "G", art: "forest",
    rules: "({T}: Add {G}.)",
  },
  {
    key: "thornwood",
    why: "A dual: two produced colours, and it enters tapped, so it is usually seen sideways.",
    n: "Thornwood Falls", cost: "",
    tl: "Land", t: "land", f: "land",
    land: "multi", produces: "GU", tapped: true, art: "thornwood-falls",
    rules: "Thornwood Falls enters tapped.\nWhen it enters, you gain 1 life.\n{T}: Add {G} or {U}.",
  },
  {
    key: "terramorphic",
    why: "A land that produces no colour at all and has a real activated ability. Every colour-watermark land design has to answer this one.",
    n: "Terramorphic Expanse", cost: "",
    tl: "Land", t: "land", f: "land",
    land: null, produces: "", art: null,
    rules: "{T}, Sacrifice Terramorphic Expanse: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
  },
  {
    key: "vegetation",
    why: "Longest rules text, no P/T. Whatever height the textbox has, this is what has to fit in it.",
    n: "Explosive Vegetation", cost: "3G",
    tl: "Sorcery", t: "sorcery", f: "G", art: "explosive-vegetation",
    rules: "Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
  },
  {
    key: "beast",
    why: "An instant — the one type tone whose whole point is that it is played at a moment, not kept on the board.",
    n: "Beast Within", cost: "2G",
    tl: "Instant", t: "instant", f: "G", art: "beast-within",
    rules: "Destroy target permanent. Its controller creates a 3/3 green Beast creature token.",
  },
  {
    key: "roil",
    why: "An enchantment with a keyword-ability line. Sits on the board for turns and is never re-read, so it has to say what it is at a glance.",
    n: "Zendikar's Roil", cost: "4G",
    tl: "Enchantment", t: "enchantment", f: "G", art: "zendikar-s-roil",
    rules: "Landfall — Whenever a land you control enters, create a 2/2 green Elemental creature token.",
  },
  {
    key: "solring",
    why: "Colourless artifact with a mana ability — no frame colour to lean on, and the cost is a single generic pip.",
    n: "Sol Ring", cost: "1",
    tl: "Artifact", t: "artifact", f: "C", art: "sol-ring",
    rules: "{T}: Add {C}{C}.",
  },
  {
    key: "token",
    why: "A token: no cost, no rules, and it exists in stacks of identical copies.",
    n: "Elemental", cost: "",
    tl: "Token Creature — Elemental", t: "creature", f: "G",
    pt: "2/2", token: true, art: "token-elemental",
    rules: "",
  },
];
