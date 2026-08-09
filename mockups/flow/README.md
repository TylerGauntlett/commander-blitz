# Snap Keep — the setup flow

Five interactive mockups of the whole path from launch to shuffle, for picking a
direction before `NewGameScreen.tsx` is touched. Open any `.html` directly — no
build, no server, no network.

```
01-front-door.html      one surface        · the readiness strip
02-face-up.html         commitment         · lock-in is a physical act
03-command-rail.html    app shell          · the pod never leaves the screen
04-three-steps.html     the control        · the comparison matrix
05-the-room.html        atmosphere         · the tint that carries nothing
_flow.js                the shared content; kept readable, inlined per file
shots/                  home, pod, greyscale twin and catalogue of each
```

The application is called **Snap Keep** in this round only. The shipped
frontend, `docs/` and the earlier mockup rounds still say "Auto MTG"; the rename
travels with whichever direction gets ported, not before.

These five are about the **flow**. [`../menu/`](../menu/README.md) is the earlier
one-screen menu exploration, [`../`](../README.md) the board and
[`../cards/`](../cards/README.md) the card face; all four share `../art/` and its
one `manifest.json`.

---

## What the menu round left out

`../menu/` designed **one screen**: pick a deck, set a difficulty, press Play. Its
direction 03 won the argument that *a seat is the unit* — a seat has a `kind`
(`cpu` / `open` / `human`), so single-player, multiplayer and mixed pods are one
screen instead of two menus. That idea survives here unchanged.

What it never covered is the flow around that screen, and there are four holes:

**1. There is no front door.** The app boots into a form. Nothing names the
product, nothing offers "join with a code" a home, and there is no moment where
you decide *what kind of game this is* before configuring one.

**2. Creating a pod is not an act.** In the menu round the room code simply
exists. Nobody creates anything, so "invite a friend" has no before and after.

**3. A catalogue of four is a list; a catalogue of twenty-four is a problem.**
The roadmap's [All Card Support](../../docs/roadmap.md) item ships general
Moxfield import and more precons. Four tiles in a drawer is the right shape for
four decks and the wrong shape for what comes after, and no amount of restyling
a drawer turns it into a browser.

**4. Only the *other* player locked in.** In `../menu/03-pod-lobby.html` the
scripted guest commits and the host does not — you press Play whenever you like.
That makes the host's own deck the single commitment on the screen that can be
silently changed after everybody else has committed. The brief's central verb is
"lock in your seat", and in every direction here **readiness is symmetric**.

---

## What every file does

Identical in all five, so the comparison is about layout and not capability:

1. Land on **home**; create a pod, or paste a code and join.
2. Fill a chair two ways, offered together and never behind a mode switch —
   **add a CPU**, or **invite a player**.
3. A scripted guest joins an open chair and locks in a moment later.
4. **Copy the pod code and the invite link**, each with a visible confirmation.
5. **Browse the catalogue**: free-text search, colour identity, source
   (precon / yours), and four sorts, over twenty-four decks.
6. Open a **dossier** — ratings, playstyle, strategy, curve or its honest hole,
   signature cards, engine note. Closes on ✕, outside click, and **Escape**.
7. **Import from Moxfield**: paste garbage, get the error; paste a link, get the
   deck under *Yours*.
8. **Lock in your seat**, and unlock again.
9. Change a CPU seat's persona; empty a chair; leave the pod.
10. **Start**, which refuses until every seat is resolved *and* you are locked
    in, commits visibly, and does nothing else.
11. Press **`g`** for greyscale — a key, not a control, because the viewport
    *is* the design and dev chrome would contaminate the screenshot.

---

## The five, compared

| | 01 Front Door | 02 Face Up | 03 Command Rail | 04 Three Steps | 05 The Room |
|---|---|---|---|---|---|
| **Home is** | a door | four card backs | the shell, empty | the three decisions, named | a cover |
| **Topology** | one surface, overlays | a hand of four cards | rail + swapping stage | a wizard | a room with a table |
| **Catalogue** | inset panel, tile grid | full takeover, wall of card faces | **full stage, rated rows** | **step 1, the matrix** | full takeover, art frames |
| **Compare 24 decks at rest** | 3 ratings a tile | 3 ratings a card | 5 ratings a row | **all five, all decks** | 3 ratings a frame |
| **Lock-in reads as** | a strip completing | **a stamp on the card** | a rail control | the last step | a near-edge control |
| **Pod visible while browsing** | no | no | **yes** | no | no |
| **Survives greyscale** | yes | yes | yes | **it is the design** | mood no, facts yes |
| **Port cost to React** | low | medium | medium | low | high |

### 01 — Front Door *(recommended base)*

*Home is a door, not a place.* It holds a name, one primary action, and a way in
for somebody who was handed a code. You are meant to leave it in two seconds.
Everything after it happens on **one surface**: the catalogue, the invite and the
dossier arrive as overlays over the pod, never as navigations, so the table you
are assembling stays visible behind whatever you are doing to it.

**The readiness strip** is the stealable idea. Four segments in the footer, one
per seat, filling as each locks in. Start is not a button somebody may press when
they feel like it — it is that strip completing. That is what fixes the menu
round's asymmetry, and it costs one row of four rectangles.

The conservative one, deliberately: it keeps the information architecture the app
already has, so it lands as markup around surviving structure.

### 02 — Face Up

*Setting a game up is not configuration, it is four people committing one after
another.* So it is drawn as the thing it physically is: four cards on a table,
face-down until somebody chooses, face-up once they have, stamped once they
cannot take it back. When all four are up and stamped, the game starts, because
there is nothing left to decide.

**Lock-in is a physical act** — the loudest object on the screen, with an unlock
deliberately quieter than the lock. That asymmetry *is* the design: committing
should feel heavier than reconsidering, because three other people are waiting.

Second idea worth stealing on its own: **face-down is one picture for three
facts.** An empty chair, a player who has not chosen, and a player whose list is
sealed are all "you do not get to know this yet", and one card back says it
better than a dashed box, a hatch plate and an italic caption did.

It leans harder on one idea than anything else here, and it spends its vertical
budget on card faces — the persona copy under a CPU seat is two lines where 01
gives it five. More beautiful, slightly less informative.

### 03 — Command Rail

*The flow state is always on screen; only the stage swaps.* The pod is a rail
that never leaves — code, four seat chips, readiness, Start — and home, the
table and the catalogue are stages inside it.

**You can be three clicks deep in the catalogue and still see that Marco has not
locked in.** In a single-player lobby that is a nicety. In a four-player one it
is the whole problem: the moment somebody else's readiness can change while you
are looking at something else, hiding the pod behind an overlay means the state
you are acting on is the state you last saw.

Second: **the catalogue gets the whole stage**, which is the only reason it can
afford rated *rows* — five ratings side by side, readable straight down a column.
That is 04's matrix arriving for free, and it is the strongest argument for this
direction after the rail itself.

The rail costs ~300px permanently, and this is the direction furthest from the
board's own anatomy: pressing Start swaps the entire application rather than the
contents of a stage, which is precisely what 01 is built to avoid.

### 04 — Three Steps

*Accept that this is a form and make it an excellent one.* Here to be the
control, the way `../menu/04-ink-dossier.html` was. Somebody opening Snap Keep
for the first time has never seen a Commander pod and does not know that "four
seats" is a rule rather than a setting. For that person a dashboard is a room
full of controls with no stated order.

**The comparison matrix at catalogue scale** is the round's most portable object.
Twenty-four decks over shared columns — speed, complexity, interaction,
resilience, what the deck asks of you — as filled and hollow segments you read
straight down. Every other direction makes you open twenty-four dossiers to learn
what this shows at rest, and a player choosing a first deck is doing a
comparison, not twenty-four readings. **Steal this whichever direction wins.**

**The rule: hue is spent on mana and on nothing else.** There is no gold button
on this screen; the commit control is a near-white slab, the one filled object on
a page of outlines. Compare `shots/04-three-steps.png` with its `-grey` twin —
they are the same screen apart from the pips, and that is the whole claim.

Its escape is part of the design: *Skip to the last step* sits in the header from
step one. If that escape gets used every single time, this direction has lost and
the escape is the evidence.

### 05 — The Room

*The front door is a cover and the lobby is a place.* Not a screen with seats on
it — a room with a table in it, seen from your chair. The pod code is printed on
a placard standing on the felt, which is a thing three empty chairs are looking
at rather than a string you have to be told to share.

**The room takes your deck's colour, and the colour carries nothing.** This is
`../menu/05-planar-gate.html`'s idea with its verdict applied. That mockup let two
custom properties drive the wash, the accents, the lit seal *and* the selected
frame — and its greyscale twin was the honest argument against it, because the
one thing it spent itself on was the one thing a player who cannot use colour
does not receive.

Here the tint reaches the wall and the table glow and stops. Whose seat this is,
which colours a deck plays, locked or not, dealable or not — all carried by
shape, weight, a lettered pip or a word. Compare `shots/05-the-room.png` with
`shots/05-the-room-grey.png`: **the room loses its mood and loses nothing else.**

Highest port cost of the five, and text over uncontrolled art luminance is the
same bet `../05-planar-art.html` made on the board.

---

## The catalogue, and one honesty problem worth stating

Twenty-four precons plus the imported slot. Every commander is a real card —
name, mana cost, type line, oracle text, power/toughness, art and artist all
pulled from Scryfall by [`../fetch_art.py`](../fetch_art.py). Twenty of them were
added for this round and chosen for **colour spread rather than power**, because
colour identity is the filter a Commander player actually reaches for and it
needs a mono, a pair, a wedge and a five-colour deck to bite on.

The menu round's rule was *"a preview deck can be chosen but not dealt, and never
sits in an opponent's chair."* Applied literally to a catalogue this size it
makes twenty-two of twenty-four decks un-startable and the flow undemonstrable —
a mockup that is honest about the engine by being useless about the design.

So the catalogue is drawn at its **post–All Card Support size**, every file says
so, and the three engine states stay visible where they matter:

| state | what it means | who has it |
|---|---|---|
| `playable` | the engine can deal it | Aesi and Edgar today; the rest the day [All Card Support](../../docs/roadmap.md) lands |
| `preview` | in the catalogue, not dealable | Gishath and Yuriko — **chosen on mechanics, not at random**: reveal-and-put-onto-the-battlefield and commander ninjutsu are both rules the engine cannot express |
| `partial` | an import whose unsupported cards were dropped | the Moxfield deck, 12 cards short |

**What is authored and what is measured.** Aesi and Edgar carry real data out of
`data/decks/*.deck.json` — their blurbs are those files' own `notes`, their curves
were counted from the real lists, their swap notes are the real `reason` strings.
The other twenty-two have no deck list in this repo, so their ratings, tags,
blurbs and strategies are **authored editorial judgement** — legitimate, because
those are opinions about an archetype rather than measurements — and their
`curve` is **null**. A curve is a count of a list that does not exist. Inventing
one would be the single lie on the screen, so the dossier draws the hole instead.

---

## Readiness, and why it is symmetric

The seat model is the menu round's, with one seat kind added and one rule changed:

```
you     seat 1, always. `ready` IS locking in.
cpu     an engine opponent at `tier`. Ready by construction.
open    an empty chair holding the pod code, waiting for a person.
human   somebody joined; `ready` is whether they have locked their deck in.
empty   no chair at all -- a two- or three-player pod is a legal pod.
```

**A human's deck stays sealed until they lock in.** Reading a list before the
game is scouting, and scouting before mulligans is exactly what a lobby hides. A
CPU's dossier is always readable because it has nothing to protect. The sealed
seat draws the hatch plate `cards.css` uses for a card with no printing — an
unknown deck and an unprinted card are the same fact, so they look the same.

**You lock in like everybody else**, and Start is the pod completing rather than
a button the host may press at any time. The host is not privileged in readiness,
only in pressing the last button. `fillCpu` survives as the one toggle deciding
whether an open chair blocks the start or gets a CPU dropped into it.

---

## Recommendation

**Take 01 as the base and port four things into it**, which is the same shape of
answer the menu round reached and for the same reason: 01 keeps the information
architecture the application already has, so it lands as markup plus tokens.

Port order, cheapest and highest-confidence first:

1. **The comparison matrix** (from 04) as the catalogue's list view, with 01's
   tiles as the alternate. It is the only thing in this round that helps somebody
   choose a first deck out of twenty-four, it is cheap, and it survives greyscale
   by construction.
2. **The pod summary that does not leave** (from 03), but as a compact strip
   rather than a 300px rail — enough that opening the catalogue never hides who
   has locked in.
3. **The lock-in stamp** (from 02). 01's readiness strip is the correct system;
   02's stamp is the correct *feeling* for the individual act, and they compose.
4. **The tint** (from 05), on the pod's backdrop only, and only if it drives
   nothing but the wash. 05's greyscale twin is the standing proof that this is
   the version worth having.

**Do not** take 05's full-bleed room without also taking its blur rule and its
caps; and do not take any of them without re-running the two layout checks below,
which is how the four real bugs in this round were caught.

---

## Notes on fidelity

- Each file inlines its own copy of the content and the primitives, because each
  must open standalone from `file://`. [`_flow.js`](_flow.js) is the readable
  master: edit it, then re-inline. The inlined block is **byte-identical across
  all five** — verified, because if it drifts the comparison is measuring content
  instead of design.
- **Art resolution is a hard ceiling and it is a layout constraint.** Scryfall's
  `art_crop` is 626×457 and it is the only art-only asset published, so no
  importer can make it sharper. Never render a crop above ~1.25× native (about
  780px). Anything bigger is blurred **on purpose** and carries no detail, with
  something crisp layered on at or below 1×. This bit harder here than in the
  menu round: 03's seat panels are capped at a 1440px board because an uncapped
  half-stage panel at 2560 is 845px, which is a 1.35× upscale.
- Verified per file at **2560×1278 and 1600×950**: no console errors, no external
  requests, no broken images, plus two checks a naive overflow test misses because
  `overflow:hidden` on `body` hides both completely:
  - **escape** — a child wider than the block it sits in does not scroll the
    page, it paints over the next sibling. Three of the four real bugs were this:
    02's seat ✕ hanging 8px off its card, 02's selection ring drawn at
    `inset:-5px`, and 04's colours column being 104px when The Ur-Dragon is five
    pips and a card count. The shared card face was the fourth — a six-pip cost
    pushed `.face__head` past the card until `.face__name` got `min-width:0`.
  - **collapse** — assert a scrolling region still has a height. Measure the
    element, not the class name.
- The full eleven-point interaction contract above is script-driven and was
  walked end to end in all five, including the import failure path.

## For whoever builds the real screen

- **Seven test ids, and four of them already exist.** `new-game` on the pod root,
  `deck-<id>`, `opponents-<n>` and `start-game` survive from today's
  `NewGameScreen.tsx`; this round adds `create-pod`, `join-pod` and `lock-in`.
  Every mockup puts them on the node a click would land on.
- **`opponents-<n>` sits on the "Add a CPU" control** of an empty chair, where
  `n` is the opponent count that click produces. A seat model has no single
  "opponents" control, so the id goes on the thing that changes the number.
- **Deleting the seed field breaks the e2e suite at a known line.**
  [helpers.ts:35-37](../../frontend/e2e/helpers.ts#L35-L37) does
  `page.getByPlaceholder("random").fill(...)`. None of these five have a seed
  field; that migration ships *with* the removal, not after it.
- **The engine takes one `agent` per seat** (`SeatConfig` in
  `frontend/src/api/types.ts`), so per-seat difficulty is already expressible.
  Per-seat *personas* remain a promise the CPU work has to keep, and every file
  says so on screen.
- **Showing twenty-four decks commits the roadmap's All Card Support item.**
  Today `/api/decks` serves two. The `preview` and `partial` states are what let
  the catalogue ship before the engine catches up.
