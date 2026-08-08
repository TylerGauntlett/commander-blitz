# Main menu exploration

Five interactive mockups of a redesigned new-game screen, for picking a direction
before `NewGameScreen.tsx` is touched. Open any `.html` directly — no build, no
server, no network.

```
01-command-table.html   board anatomy      · the seat strip
02-deck-rack.html       physical objects   · the empty slot, expand-in-place
03-pod-lobby.html       who is at the table· difficulty as opponents
04-ink-dossier.html     the best form      · the comparison matrix
05-planar-gate.html     atmosphere         · the screen takes the deck's colour
_menu.js                the shared content; kept readable, inlined per file
shots/                  colour, greyscale twin, dossier and room state of each
```

These five are about the **menu**. [`../`](../README.md) is the earlier board
exploration and [`../cards/`](../cards/README.md) the card face; all three share
`../art/` and its one `manifest.json`.

Unlike the board five, **these are interactive**. Every file does the same
things, so the comparison is about layout and not about capability:

- pick a deck, precon or imported
- open and close a dossier — ✕, outside click, and **Escape**
- change difficulty, and change it per seat
- add and empty chairs; open a chair to a player and watch them join
- paste a Moxfield link and watch it fail, then succeed
- press Play, which commits visibly and does nothing else
- press **`g`** for greyscale — a key, not a control, because the viewport *is*
  the design and dev chrome would contaminate the screenshot

---

## What is wrong with the menu today

Four things, in the order they cost the most.

**1. It is the last green surface in an indigo app.** `theme.css` aliased
`--felt-*` onto the void tokens so the board went indigo without touching call
sites, but `.deck` in [ui.css:924](../../frontend/src/styles/ui.css#L924) still
carries a literal `linear-gradient(180deg, #16302599, #0a141066)` — the
pre-redesign felt green. The title is `--gold` at 46px with a 50px glow, the only
place in the app that treats gold as a display face rather than a control tier.

**2. A 100-card deck renders as about forty words.**
[NewGameScreen.tsx:87-101](../../frontend/src/components/menu/NewGameScreen.tsx#L87-L101)
emits name / commander / WUBRG letters / count / one-line note into a fixed 250px
box. The deck files already carry a `substitutions` array — five entries for
Aesi, seven for Edgar, each with a `reason` — that nothing displays. There is no
art on a screen whose entire job is choosing between pictures.

**3. Every control has the same weight.** Three identical `.segmented` fieldsets
give Opponents, AI and Seed equal priority, and one of the three is being deleted
outright.

**4. The AI toggle leaks an implementation detail.** `heuristic | random` are
agent class names.

And a fifth, which the redesign has to answer rather than restyle: **the screen
has no vocabulary for where a deck came from.** Precon versus imported is the
central new axis and nothing on the current menu can express it.

---

## The five, compared

| | 01 Command Table | 02 Deck Rack | 03 Pod Lobby | 04 Ink & Dossier | 05 Planar Gate |
|---|---|---|---|---|---|
| **Topology** | 3 columns, board anatomy | horizontal shelf | pod around a table | one dense sheet | full-bleed stage |
| **Detail surface** | centred modal | **expand-in-place** | right slide-over | text-first modal | codex over the art |
| **Difficulty** | rungs + per-seat override | **brass 4-detent dial** | **a persona per seat** | ladder, all lamps at once | vertical seal ladder |
| **Custom deck, un-imported** | dashed row in a group | **a gap in the rack** | field in the drawer | hollow matrix row | dashed filmstrip frame |
| **Compare four decks at rest** | no | partly (back of box) | no | **yes** | no |
| **Multiplayer cost** | small | small | **near zero** | small | small |
| **Survives greyscale** | yes | yes | yes | **it is the design** | controls yes, identity no |
| **Port cost to React** | low | medium | medium | low | high |

### 01 — Command Table *(recommended base)*

*The setup screen is the board before the board.* Left rail, play area, right
rail — the same anatomy as `.table__body`, so pressing Play changes the contents
and not the application.

**The seat strip** is the stealable idea. "Opponents: 1 2 3" is a number you
read; chairs you fill are a thing you see. It also makes the screen honest about
something it already does and hides:
[NewGameScreen.tsx:44-46](../../frontend/src/components/menu/NewGameScreen.tsx#L44-L46)
already cycles opponents through the other decks, so the pod is *already*
heterogeneous and the UI has never said so. Per-seat difficulty then falls out
for free, and so does multiplayer.

The conservative one, deliberately: it keeps "a list of decks plus a set of
options", so it lands as new markup around surviving structure. The cost is that
it is the least surprising of the five.

### 02 — The Deck Rack

*Precons are physical objects.* Four boxes on a shelf, faced with an art window,
edged in colour identity, named up the spine — and **one dashed gap** where a
fifth box should be. That gap is the whole custom-deck story, and it is the
repo's own convention doing real work: dashed already means "not real / not here"
for drop targets and fallen commanders, and a deck you have not imported is the
purest not-here there is.

Second idea: **expand in place.** There is no modal. Opening a box collapses the
others to their spines and unfolds the dossier in the gap they leave. The
question it is really asking is whether five things on a screen need a modal at
all — a modal exists to stop you losing your place, and you cannot lose your
place in a row of five. Third: **the brass dial**, the shipped life dial from
`board.css` reused as a four-detent rotary switch.

### 03 — Pod Lobby

*A pre-game screen is a lobby, and a lobby is about who is at the table.*

**Difficulty as opponents, not as a slider.** Each AI seat is a named persona
with a doctrine and its capability lamps; you do not set a difficulty, you choose
who you are playing against, per seat. This is
[roadmap.md:58-59](../../docs/roadmap.md#L58-L59) — "subagents writing persona
documents for each supported difficulty … general strategies, expected
behavior" — rendered. It is also the only direction where a **mixed pod** is
expressible without inventing a second control, and a mixed pod is the most
useful thing a solo playtest tool can offer: one opponent to practise against and
one to lose to.

It is the direction multiplayer costs nothing to add to, because the seat was
already the unit.

### 04 — Ink & Dossier

*A setup screen is a form; make it an excellent one.* Here to be the control.

**The comparison matrix**: four precons and the custom slot as five rows over
shared columns — speed, complexity, interaction, resilience, what the deck asks
of you, and whether the engine can deal it — as filled/hollow segments. Every
other direction makes you open four dossiers to learn what this shows at rest,
and a player picking a first deck is doing a comparison.

**The rule:** hue is spent on mana and on nothing else. Even the commit control
is luminance — a near-white slab, the one filled object on a page of outlines.
Compare `shots/04-ink-dossier.png` with its `-grey` twin: they are the same
screen apart from the pips, which is the whole claim.

It is the least game-like screen here, on purpose. If the brief's first sentence
is the binding one, it loses on it deliberately, and its ideas are meant to be
ported into whichever direction wins.

### 05 — Planar Gate

*The menu has no gameplay to carry it, so it can afford to be the most
atmospheric surface in the app.*

**The screen takes the deck's colour.** Two custom properties are set from the
selected deck's colour identity, and the wash, the accents, the lit seal and the
selected filmstrip frame all read from them. Picking Edgar makes the room warm;
picking First Flight makes it cold. One variable swap per selection, and it is
the entire mood.

**The greyscale twin is the verdict, and it is mixed.** The controls survive:
pips keep their letters, ratings and lamps are filled or hollow, the preview
badge is dashed and says "Preview". What does not survive is the tint — in
greyscale all four decks light the room identically, so the one thing this
direction spends itself on is the one thing a player who cannot use colour does
not receive. Compare `shots/05-planar-gate.png` with `shots/05-planar-gate-grey.png`.

---

## Art resolution is a hard ceiling, and it is a layout constraint

Worth reading before designing anything else against this art.

**Scryfall's `art_crop` is 626×457, and it is the only art-only asset published.**
Every variant the API returns was downloaded and measured while building these:

| variant | size | what it is |
|---|---|---|
| `art_crop` | **626×457** | the art alone — the ceiling |
| `art` | 626×457 | the same, WebP |
| `large` | 672×936 | whole card |
| `png` | 745×1040 | whole card; its art band measures ~655px |
| `border_crop` / `crop` | 480×680 | whole card |

So **no importer can make the art sharper.** The first drafts of 01, 02 and 05
all ignored that and looked it — 02 worst of all, covering a 290×660 portrait box
with a landscape crop scaled by height, a 2.56× upscale.

The rule the five now follow:

> Never render a crop above ~1.25× native (about 780px wide). Any field bigger
> than that is blurred **on purpose** and carries no detail. Something crisp — a
> card face, or an art band at its own aspect — sits on top at or below 1×.

Which is why 05 has a card on it: the wall gives you the mood at 22px of blur,
the card gives you the detail at 0.4×, and neither is upscaled. And why a deck
box in 02 is a printed panel with an art window rather than a photograph — which
is also what a deck box actually looks like.

---

## Difficulty: one design, five presentations

Identical copy in all five, so the comparison is about layout and not wording.
Four tiers, because tier 1 is today's `random` agent and tier 3 is today's
`heuristic`, which leaves 2 and 4 to state
[the roadmap's ambition](../../docs/roadmap.md#L48-L63) — and because a 4-step
ladder shares the 4-segment bar every deck rating already uses.

Honesty is structural rather than textual: each tier lights a cumulative prefix
of three **capability lamps** — combat math, removal & targeting, mana &
sequencing — drawn filled or hollow, so the ladder says what it turns on and
reads without colour.

| Tier | Tag | Lamps |
|---|---|---|
| **Goldfish** | Plays solitaire | ○○○ |
| **Apprentice** *(default)* | Knows the basics | ●○○ |
| **Duelist** | Plays to win | ●●○ |
| **Archmage** | Plays around you | ●●● |

"Goldfish" is both the clever name and the literally accurate one — it is
Magic's own word for an opponent that does not interact, and the honest name for
`agent: "random"`.

**Apprentice and Archmage do not exist in the engine today** and would map to
`heuristic` until the roadmap's CPU work lands. That is a build-time note, not a
mockup-time lie, and every file says so on screen.

---

## Rooms: multiplayer without a second menu

[roadmap.md](../../docs/roadmap.md) backlogs "multiplayer online support using a
basic system of rooms and room codes". All five mockups carry it, and it needed
exactly one new idea rather than a new screen: **a seat has a kind.**

```
cpu     an engine opponent, at its tier
open    an empty chair holding the room code, waiting for a person
human   somebody joined; `ready` is whether they have locked their deck in
```

All-CPU, all-human and mixed pods are then the same screen with different seats
in it. There is no "single player / multiplayer" fork, because that fork is
precisely how a product ends up with two menus. Opening a chair reveals the room
code; **"fill empty chairs with CPU"** is one toggle, and it is both the
partial-pod case and backfill-on-disconnect. Play becomes `Start · 3 of 4 seats`
and refuses while a chair is open unless CPUs are allowed to fill it.

**A human's dossier is sealed until they lock in.** Reading a list before the
game is scouting, and scouting before mulligans is what a lobby hides; a CPU's
dossier is always readable because it has nothing to protect. The sealed seat
draws the hatch plate `cards.css` uses for a card with no printing — an unknown
deck and an unprinted card are the same fact, so they look the same.

This re-ranks the five slightly, which is the point of having built it:
03 and 01 already had a seat as their unit and absorbed rooms almost for free;
02, 04 and 05 had an opponent *count* and had to grow one.

---

## Recommendation

**Take 01 as the base and port four things into it.**

01 is the direction that keeps the current information architecture, so it lands
as markup plus tokens rather than a rewrite, and its seat strip is already the
right shape for both per-seat difficulty and rooms.

Port order, cheapest and highest-confidence first:

1. **The comparison matrix's ratings** (from 04). Five 1–4 ratings per deck,
   drawn as filled/hollow segments, shown on the deck rows *and* in the dossier.
   Cheap, survives greyscale by construction, and it is the only thing here that
   helps somebody choose a first deck.
2. **The back of the box** (from 02). Blurb, playstyle chips and ratings on the
   deck tile itself, so a tile is worth looking at before it is clicked.
3. **The persona seat** (from 03). One named opponent per chair, with its lamps
   and its doctrine line — the difficulty control and the pod become one object.
4. **The tint** (from 05), but only on the hero panel, not the page. It buys most
   of 05's mood for none of its greyscale cost.

**Do not** take 05's full-bleed stage without also taking its blur rule and its
crisp card; and do not take any of them without re-running the two layout checks
below, which is how the three real bugs in this round were caught.

---

## Notes on fidelity

- Deck content is real. Aesi and Edgar are read out of `data/decks/*.deck.json`
  and `data/cards/*.cards.json` — the blurbs are those files' own `notes`, the
  curves were counted from the real lists, the substitution notes are the real
  `reason` strings. Isperia and Zurgo are real Scryfall cards with real oracle
  text, but they have **no deck list in this repo**, which is what
  `engine: "preview"` means and why their curve is a hole rather than a guess.
- **A preview deck can be chosen but not dealt**, and never appears in an
  opponent's chair. Showing one in a seat would be the screen lying about what
  the engine can do.
- Each file inlines its own copy of the content and renderer, because each must
  open standalone from `file://`. `_menu.js` is the readable master: edit it and
  re-inline.
- Verified per file at **2560×1278 and 1600×950**: no console errors, no external
  requests, no broken images, and two checks that a naive overflow test misses,
  because `overflow:hidden` on `body` hides both completely:
  - **escape** — a child wider or taller than the block it sits in does not
    scroll the page, it paints over the next grid column. That is what the ratings
    row under 01's hero did, and no viewport check catches it: the spill is into a
    sibling. A grid item defaults to `min-width:auto`, which is the cause.
  - **collapse** — assert a scrolling region still has a height. Measure the
    element, not the class name: a first pass matched `bar__track` on "rack" and
    reported inline spans as collapsed panels.
- Every interaction listed at the top is driven by script in all five files, plus
  the room flow: opening a chair reveals the code, the joiner's deck stays sealed
  until they lock in, and Play refuses while a chair is open with fill turned off.

## For whoever builds the real screen

- **Deleting the seed field breaks the e2e suite at a known line.**
  [helpers.ts:35-37](../../frontend/e2e/helpers.ts#L35-L37) does
  `page.getByPlaceholder("random").fill(...)`. Moving to `?seed=` means
  `startGame` navigates to `/?seed=N` and `App.tsx` reads it. That migration
  ships *with* the field's removal, not after it.
- **Four test ids must survive.** `new-game` on the root, plus `deck-<id>`,
  `opponents-<n>` and `start-game`. Every mockup here puts them on the node a
  click would land on, so the port is mechanical. In 04 that meant the name cell
  rather than the row, because the row is `display:contents` and has no box.
- **Showing four precons commits the roadmap's "All Card Support" item.** Today
  `/api/decks` serves two. `engine: "preview"` is what lets the menu ship first.
- **The engine takes one `agent` per seat** (`SeatConfig` in
  `frontend/src/api/types.ts`), so per-seat difficulty is already expressible.
  Per-seat *personas* are a promise the CPU work has to keep.
