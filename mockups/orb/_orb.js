/* ===========================================================================
   The player orb's content -- the readable master for the five orb mockups.

   This file is NOT loaded. A <script src> does not load from file://, and every
   mockup in this repo opens standalone, so the block below is inlined verbatim
   into all five 0N-*.html files. Edit here, then re-inline. It is byte-identical
   across the five, which is what makes the comparison about layout and nothing
   else.

   One player, one moment, chosen so that every conditional channel the shipped
   orb can draw is on screen at once. A state that hid the commander-damage row
   or the exile pile would not prove a direction preserves them:

     - it is your turn AND you hold priority (two different things, both drawn)
     - the commander sits in the command zone, castable, with tax owed
     - two of three opponents have connected with their commanders, one of them
       past the warn threshold
     - exile is not empty, so its pile exists
     - a hovered spell would tap two of your lands
     - the library has been drawn down while the graveyard has grown, so the
       piles' comparative height has something to say
   =========================================================================== */

const ME = { pid: 0, name: "You", life: 27, active: true, priority: true, lost: false, loss: null };

const CMD = {
  oid: 101,
  name: "Aesi, Tyrant of Gyre Strait",
  art: "aesi-tyrant-of-gyre-strait.jpg",
  cost: ["4", "G", "U"],
  zone: "command",
  castable: true,
  tax: 2,
  identity: ["G", "U"],
};

/* Word + glyph. The third channel is the portrait's luminance and lives in CSS.
   None of the three is hue -- CommandZone.tsx:57-76, and the reason is
   docs/mockup-fidelity.md's top-ranked open defect. */
const CMD_STATE = {
  ready: { word: "Ready", glyph: "▶" },
  waiting: { word: "In command", glyph: "·" },
  stack: { word: "On the stack", glyph: "✦" },
  deployed: { word: "On the battlefield", glyph: "✦" },
  dead: { word: "In the graveyard", glyph: "✕" },
  exiled: { word: "Exiled", glyph: "✕" },
};
const STATE = CMD_STATE.ready;

const LETHAL = 21;
const WARN = LETHAL - 6;

const FOES = [
  { pid: 1, name: "Edgar Markov", dmg: 16 },
  { pid: 2, name: "Atraxa, Praetors' Voice", dmg: 7 },
  { pid: 3, name: "Chulane, Teller of Tales", dmg: 0 },
];
const DMG = FOES.filter((f) => f.dmg > 0);

/* markSpent(manaRow(...)) already applied -- logic/mana.ts. An ambiguous source
   ("Add {G} or {U}") is ONE split pip and never two solid ones, because two
   would claim a mana that does not exist. `spent` is the engine's own solved
   payment for a hovered spell, never arithmetic done here. */
const MANA = [
  { k: "pool-U-0", tone: "U", symbols: ["U"], floating: true, spent: false },
  { k: "src-31-0", tone: "G", symbols: ["G"], floating: false, spent: false },
  { k: "src-32-0", tone: "G", symbols: ["G"], floating: false, spent: false },
  { k: "src-33-0", tone: "any", symbols: ["G", "U"], floating: false, spent: true },
  { k: "src-34-0", tone: "U", symbols: ["U"], floating: false, spent: true },
  { k: "src-35-0", tone: "C", symbols: ["C"], floating: false, spent: false },
];
const SPENT = MANA.filter((m) => m.spent).length;

/* `peek: false` is the library, and it is deliberate: hidden information, and a
   control that does nothing when clicked is worse than no control. The other
   four are the only route into ZonePeek, so a direction that draws them
   decoratively makes the graveyard unreachable. */
const ZONES = [
  { name: "library", label: "Lib", kind: "lib", count: 41, peek: false, title: "Cards in library" },
  { name: "hand", label: "Hand", kind: "lib", count: 5, peek: true, title: "Your hand" },
  { name: "graveyard", label: "GY", kind: "gy", count: 12, peek: true, title: "GY: 12" },
  { name: "exile", label: "Exile", kind: "ex", count: 3, peek: true, title: "Exile: 3" },
  { name: "command", label: "CMD", kind: "cmd", count: 1, peek: true, title: "Command zone" },
];

/* Helpers ---------------------------------------------------------------- */

const root = document.getElementById("root");
const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const artUrl = (file) => "../art/" + file;

/* zones.ts: one leaf per nine cards, nine leaves and then it stops. The top
   leaf still carries the exact number, so the cap costs resolution and never
   information. */
const LEAF = 9;
const MAX_LEAVES = 9;
const leaves = (n) => (n <= 0 ? 0 : Math.min(MAX_LEAVES, Math.ceil(n / LEAF)));

const manaTitle = (p) =>
  p.spent
    ? p.symbols.join(" or ") + " — this spell would tap it"
    : p.symbols.length > 1
      ? "Either " + p.symbols.join(" or ")
      : p.floating
        ? p.symbols[0] + " in pool"
        : p.symbols[0];

const manaRowTitle =
  SPENT > 0 ? MANA.length + " available; this spell taps " + SPENT : MANA.length + " available";

const costPips = (cost) =>
  cost
    .map((s) => '<i class="pip pip--' + (/^\d+$/.test(s) ? "gen" : s) + '">' + s + "</i>")
    .join("");

