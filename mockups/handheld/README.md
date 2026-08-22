# Handheld exploration

Six interactive mockups of a **Steam Deck-sized board and deck picker**, driven
by a **real gamepad**, for picking a direction before `Table.tsx` grows a pad
loop. Five are the argument; **06 is the answer**. Open any `.html` directly — no build, no server, no network.

```
01-focus-ring.html      noun first    · the stick walks the board
02-verb-wheel.html      verb first    · eight verbs, the same eight places
03-one-zone.html        context first · bumpers swap who owns the screen
04-the-reel.html        queue first   · one question at a time, readable
05-glass-pointer.html   the control   · trackpad, touch and finger, one path
06-one-thumb.html   ►   THE SYNTHESIS · the best of all five, nothing missing
_handheld.css           the shared skin; inlined per file
_handheld.js            the shared content, card face, symbols and the Pad layer
_table.js               the whole application's fixtures; 06 only
assert.js               the gates, as numbers; inlined per file
inline.py               splices the masters into each file; --check for CI
shots/                  1280x800 PNGs — 06 has home, pod, catalogue, mulligan,
                        board, stack, targeting, blockers, manual mana, coach,
                        between-turns, question, zones, tools, game over,
                        and a 1920 wide shot
```

**Start with [`06-one-thumb.html`](06-one-thumb.html).** 01-05 are the arguments;
06 is the answer, and it is the only one held to the standard of *reaching
everything the web client reaches* and *playing as smoothly as it does*.

Every file boots into deck select, deals into the same board — **turn 8 at
declare-attackers, the same thirty permanents as [`../_state.js`](../_state.js)**
— and can cast a spell that needs a target. Same content, same skin, same card
face. **The only thing that differs between 01-05 is how the pad drives it**,
which is the only thing those five were trying to compare.

Every file is **exactly one Steam Deck screen — 1280x800, scaled to fit whatever
window you open it in, with the scale printed on the bezel.** That is not
decoration: a 1280x800 design opened in a 2560px window is being judged at half
the angular size a Deck would show it at, and every legibility call made that way
is wrong in the direction that flatters the design.

These are about the **pad**. [`../`](../README.md) is the board exploration,
[`../cards/`](../cards/README.md) the card face, [`../orb/`](../orb/README.md)
the player panel, [`../menu/`](../menu/README.md) the main menu and
[`../flow/`](../flow/README.md) the lobby flow. All six share `../art/`.

---

## What the earlier rounds assumed

A mouse. Every one of them, without ever saying so — and
[`docs/roadmap.md`](../../docs/roadmap.md)'s very first backlog line is
"Controller support for Windows with XBox controller". Four holes, in cost order.
All four are numbers rather than opinions.

**1. The text is not small, it is absent.** Measured on the shipped board —
`mockups/boards/05-planar-art.html`, the direction that shipped — resized to
1280x800, which is Steam Deck native:

```
444 of 635 rendered elements below 12px      the smallest was 2.11px
```

A Deck is a 7-inch panel held at roughly 40–50cm. 2.11px is not a small font,
it is a decoration in the shape of a word. This is the round's reason to exist,
and the number every direction here is measured against.

**2. 41.9% of the screen is rail.** `.table__body` in
[board.css:27](../../frontend/src/styles/board.css#L27) is
`grid-template-columns: 232px minmax(0,1fr) 304px` — 536 hard pixels of 1280, no
media query anywhere near it. There are exactly **three** `@media` rules in the
whole client: one for tall displays, one `prefers-reduced-motion`, and one
`max-width: 560px` that only touches the front door.

**3. Hover is the only route to five things.** A card's full text (the preview
rail is driven purely by `onMouseEnter`), the reason a hand card is dim, what an
activated ability does (`.card--ability:hover .ability-pop`, CSS-only, no JS
route at all), fanning a stack of duplicates open, and **45 native `title=`
tooltips** carrying real information — the tool strip's three modes, the mana
row, commander damage, every zone pile. A pad cannot hover. On a Deck today
every one of those is simply gone.

**4. There is no cursor.** `board.css`, `cards.css` and `ui.css` contain **zero**
`:focus-visible` rules, while every board card is `tabIndex={0}` — so tabbing
through forty permanents is invisible. No roving tabindex, no focus trap, no
programmatic `.focus()` anywhere in the client. And targeting has no non-pointer
route whatsoever.

### The good news, and it is most of the work

**[ADR 0002](../../docs/adr/0002-flat-action-space.md) means a controller UI
loses no capability.** Every legal action is already a control carrying
`data-action-id`, exactly once in the document; `ActionPanel.tsx` documents that
when a gesture and the panel disagree, **the panel is right**; dragging is
explicitly a shortcut, not a rule. And every question the engine asks is one
shape — `PendingDecision { kind, prompt, options[], min_count, max_count,
allow_done }` — with one action emitted **per legal target tuple**.

So a pad-driven client is a re-skin of a surface that already exists. That is
what makes this a design round rather than an engine project.

---

## What every file does, identically

Ten items, so the comparison is about layout and not capability. Divergences are
called out where they happen.

1. **Boot to deck select** and move over twelve decks with the stick or d-pad.
2. **Filter or sort from the pad** — the two-axis navigation problem, shown
   solved. *(01 and 05 use a facet row; 02 makes colour identity a wheel; 03 and
   04 page one deck at a time and have no facets at all — see the table.)*
3. **Read a deck's dossier** without a mouse: five ratings, tags, and the deck's
   own `notes` out of `data/decks/*.deck.json`. *(In 03 and 04 the dossier is
   never opened, because you are always already inside it.)*
4. **Deal**, and arrive at the board: turn 8, declare-attackers, thirty
   permanents, three attackers already staged.
5. **Read any card's full oracle text** at 19px, from the pad alone.
   *(Closes the hover-only preview rail.)*
6. **See a stack of duplicates** — the ×7 Forests — as one object with its count,
   and open it. *(Closes `CardStack`'s `onMouseEnter`, which has no other route.)*
7. **Learn why a hand card is dim.** At declare-attackers five of the six cards
   in hand are sorcery-speed, so this is a real answer and not a demo string.
   *(Closes the hover-only `hand__hint`.)*
8. **See and activate an ability** — Terramorphic Expanse's `{T}, Sacrifice:`,
   the same card the board round used for the same reason.
   *(Closes `.card--ability:hover .ability-pop`.)*
9. **Cast a spell that needs a target.** Beast Within, six legal targets, and
   **B backs out without losing the spell** — cancel is the part that is always
   missing.
10. **Stage attackers and commit.** Three are staged at boot; add, remove, send.

Three things are decided once and are identical in all five, so the comparison is
never about who bound cancel where:

- **B is back everywhere**, and never quits from the top level.
- **View (⧉)** is the log, zones and scoreboard. **Menu (☰)** is the system.
- **The commit control is one shaped slab**, always saying the one thing the turn
  is waiting on.

---

## The five, compared

The structural axis is **what you choose first**.

| | 01 Focus Ring | 02 Verb Wheel | 03 One Zone | 04 The Reel | 05 Glass Pointer |
|---|---|---|---|---|---|
| **Chooses first** | the noun | the verb | the context | the queue | nothing (hardware) |
| **Board topology** | shipped, densified | full-bleed, wheel on top | one zone on stage | no board at rest | shipped, both rails |
| **Board px of 1280** | **1130** | **1280** | **1252** | 1280 *(held)* | 898 |
| **Card width** | 96px | 96px | **158px** | **300px** | 96px |
| **Name on a board card** | no — on the ring | no — on the ring | **yes, 5 of 7** | **yes** | no — in the rail |
| **Resting cursor** | yes | **no** | yes | yes | yes (snapped) |
| **Deck picker** | facet grid | wheel filters a grid | one deck + pod spine | one deck, dossier open | facet grid, pointed at |
| **Targeting** | ring locked to candidates | wheel collapses onto the card | its own stage | just the next question | point and click |
| **Inputs to cast-with-target** | 8 | **3** ⚠ | 9 | 6 | 4 ⚠ |
| **Reads at arm's length** | adequate | adequate | **yes** | **yes** | adequate |
| **Also answers the phone** | no | no | partly | **yes** | **yes** |
| **Port cost to React** | **low** | medium | high | high | **lowest** |

⚠ **Both starred numbers are flattered by this board state and the README should
say so rather than let them stand.** 02 scores 3 because exactly one card in hand
is castable, so its shortlist has one entry and is skipped — with five castable
cards it is 3 + N. 05 scores 4 because a *steer* counts as one input the way a
*press* does, which is exactly the arithmetic that hides how long steering takes.
This is why the metric is defined three ways below and why no direction should be
picked on the press column alone.

### 01 — Focus Ring *(the conservative one — its ring is 06's ring)*

*You point at a thing, then say what to do to it.* The conservative one: nothing
about the information architecture changes, so it lands as a focus ring plus a
roving tabindex rather than a rewrite. `Card.tsx` is **already** `tabIndex={0}`
on every board card; what is missing is a ring to draw and a cursor to drive.

Its bet is that **focus can do hover's job** — and all five hover-only routes
above hang off the ring here, which is most of the port for free.

Its hard part is real: **spatial navigation over ragged rows**. Lanes hold 2, 3,
4 and 7 objects, so "down" from the fourth land has no honest answer, and the
failure — press down, end up two lanes over — reads as the cursor being broken.
`nav()` scores candidates by distance along the pressed axis plus a punished
perpendicular drift (`PERP = 2.4`), which is the standard answer and is what
makes the walk feel deliberate.

### 02 — Verb Wheel

*Eight verbs, in the same eight places, forever.* **Not a context menu** — a
radial whose contents change is a radial you have to read, which costs you the
only thing a radial was good for. A spoke with nothing behind it is drawn dead
rather than removed.

Its best moment is **targeting**: the wheel does not close and reopen as a list,
it collapses onto the source card and the legal targets become the spokes. The
gesture that chose the verb and the gesture that chooses the target are one
flick.

What it actually costs is **a layer**. A Commander priority window can hold forty
actions and a wheel holds eight, so after the verb you are always in a shortlist.
The file draws that shortlist honestly, including the line "…and N more. A wheel
holds eight; a priority window does not."

Also the one place a wheel is genuinely the *better* control: **colour identity
is radial.** WUBRG in canonical order is a five-pointed star every Commander
player already has in their head.

### 03 — One Zone

*Refuse to show everything, and show what you do show properly.* Bumpers swap
which zone owns the screen; everything else compresses to a **spine** carrying a
summary you can read — `8 creatures · 8 untapped · 20 power · 1 flier` — rather
than a thumbnail you cannot. That summary is board round 03's mana meter applied
to combat, and **it is worth stealing whichever direction wins**.

It is the only direction where an opponent's oracle text is legible **where the
card is**, with no overlay to open or close. 158px is the width at which a card
renders its own name at the 16px floor; measured, 5 of 7 creature names fit in
full and the two that clip are 21 and 27 characters long.

Two honest costs. **A stage is what fits**: twelve permanents at 158px is 1896px,
so the viewer's board is two stages rather than one, and nothing may scroll
sideways — a stage that scrolls has things on it you cannot see, which would have
swapped unreadable cards for invisible ones. And **you cannot see both boards at
once**, which is where a lot of Commander lives. **Its acid test is
declare-blockers, and this file does not draw that step** — that is the argument
the round should actually have.

### 04 — The Reel

*Draw what the engine actually is.* The server does not hand the client a board
to manipulate; it hands it a `PendingDecision` with a flat option list, and it
emits one action **per legal target tuple**. So "Beast Within aimed at Falkenrath
Noble" is not two decisions to compose — it is one entry in a list the server
already wrote. Every other direction here rebuilds a pointing gesture that the
engine then decomposes back into that list.

**The prediction, written down before measuring: this should win the press count
outright.** It came second at 6 against 02's flattered 3, and it beats every
direction whose count is not an artifact. Its fixtures use the engine's real
field names, so porting it is a rename.

Its bet is the biggest here: **it gives up the board.** Magic is a game of
reading a table, and this direction says you may read it when you ask (hold ⧉).
It also cannot show you a decision you were not asked — no idle browsing.

It is also, by some distance, the closest of the five to a phone.

### 05 — Glass Pointer *(the control)*

*Do not design a controller UI. The Deck already has a mouse.* Here to be the
control the way `../menu/04-ink-dossier.html` and `../flow/04-three-steps.html`
were: the option that always works, costs almost nothing, and that the other four
have to beat on the merits. **If a scheme cannot beat a trackpad, it is not worth
the rewrite**, and this file is what makes that a fair fight.

What makes it tolerable is **magnetism** — the pointer snaps to the nearest
interactive thing within 40px and draws a line to what it caught, because
magnetism without that line reads as the pointer being broken. ABXY stay bound to
the four commonest actions so frequent things never need aiming.

Its weakness is structural: **it wins on presses and loses on seconds.** Every
other direction moves in discrete steps that arrive where they promised; this one
asks you to steer, on a device people use on trains.

It is also **the phone answer already**, and that is not a side effect — see
below.

## 06 — One Thumb: the synthesis

01-05 are five arguments. **06 is the answer**, and it is held to a standard none
of them were: it must reach *everything the web client reaches*, play as
smoothly, and look like a game rather than a website somebody bound a pad to.

### What it takes from each

| From | What | Why it survived |
|---|---|---|
| **01** | the focus ring, drawn from state | Focus can do hover's job. All five hover-only routes hang off the ring. |
| **02** | the wheel — **demoted to a shortcut** | Eight fixed places for the things that are *not on the board*: zones, log, tools, concede. Never the primary control, which is where 02 overreached. |
| **03** | the spine, and the summary | Opponents compress to `4 creatures · 2 untapped · 4 power · 1 flier` — a count you can read beats a thumbnail you cannot. |
| **04** | the reel | Every `PendingDecision` becomes one question with big answers. All eleven decision kinds, including the seven that are modal-only. |
| **05** | the pointer | `pointermove`/`pointerdown` are live on every screen, so trackpad, touchscreen and finger need no second code path. |

### The thesis the name is about

**You can play the whole game with the left thumb and A.** The bumpers, the
wheel, the triggers and the pointer are all *shortcuts to something the thumb
could already reach*. That is the property a console game has and a website bound
to a pad does not — and it is what "no compromises" has to mean here: not that
every surface exists, but that every surface is reachable without changing how
you are holding it.

### Everything reachable

Checked against the components that exist, not against memory:

**Lobby** — home · create a pod · join by code · four chairs · your seat, a
person's seat, a CPU's seat, an empty chair · **choose any seat's deck, including
a CPU's** · **the four-tier difficulty ladder with its capability lamps** · open a
chair · empty a chair · add a CPU · invite code and shareable link · seed · lock
in and unlock · the ready track and its "why not" line · deal.

**Catalogue** — search · colour identity (AND) · source (all / precon / yours) ·
four sorts · twelve decks with real ratings · dossier · **Moxfield import with
its dry-run coverage report** — 88 playable, 9 simplified, 3 inert, itemised
before you agree to play it.

**Board** — five-phase ribbon with live steps · three opponent seats with life,
commander, commander damage, tax, mana meter and zone counts · your three lanes ·
stacks of duplicates · the hand · **the stack, non-empty** · the log · **every
zone of every player, with how each card got there** · the card reader · the tool
strip *and what each tool means* · undo · concede · game over with a per-player
loss reason · **R2 zooms any seat's board to full size**.

**Decisions** — all eleven kinds. `priority`, `declare_attackers`,
`declare_blockers` and `choose_objects` on the board; `choose_mode`, `choose_x`
(a stepper, not eleven buttons), `may`, `choose_player`, `mulligan`,
`discard_to_hand_size` and `commander_zone_change` in the reel. The switch is a
**denylist**, like `PromptDialog.tsx`'s — so a decision kind nobody has thought
about yet arrives *working* rather than blank.

### The friction log — what driving it actually found

Every one of these came out of playing the prototype, not looking at it. They
are recorded because they are the argument for building one at all.

| # | Found | Fix |
|---|---|---|
| 1 | **Five of six legal targets were unreachable.** With opponents compressed to summaries, Beast Within's targets on *their* boards had nowhere to be. The ring could reach the one candidate on my own board and nothing else. | The spine **opens into a candidate band** while targeting. A summary is what an opponent's board is worth when nothing is asking about it; the moment something is, the cards the question is about take its place. |
| 2 | **The foot was a frame behind.** It names whatever the ring is on, but the cursor was resolved *after* the markup was built — so the first render of every screen named nothing. | Build, resolve, and if resolving moved the cursor, build once more. One extra pass, never a loop. |
| 3 | **The ring could walk out of a modal.** Game-over opened with the ring on an opponent's seat, because the resolver took the first `[data-stop]` in document order and the board comes first in the markup. | A real focus trap: `stopRoot()` returns the topmost overlay, and `nav`, the pointer and the resolver all ask it. *The shipped client has this same hole — five `aria-modal` dialogs, no trap, a backdrop that blocks only clicks.* |
| 4 | **`A` offered "Send at Edgar" on a land.** The code assumed a permanent with an action is a creature with an attack. | The verb comes from `LegalAction.kind`, which is what the engine already sends. |
| 5 | **Two amber rings at once.** The "has priority" tint was `--staged` amber sitting next to the `--focus` amber cursor — the one failure a controller UI may never have. | Priority is the dot, and only the dot. |
| 6 | **`<small>` broke the type floor eight times on one screen.** The browser renders it at 0.83em, so every `<small>` inside 16px copy lands at 13.3px — invisibly, in markup that reads as perfectly reasonable. | `small { font-size: inherit }`. It was being used to mean *secondary*, not *smaller*. |
| 7 | **A `var(--face-fs, 13px)` fallback below the floor.** Any card face drawn without an explicit size silently violated the rule the round is built on. It did, in three files, on a screen nobody had gated. | **The fallback is now the floor.** |
| 8 | **A focus ring with `outline-width: 3px` and `outline-style: none`.** A bare `:focus { outline: none }` matched the cursor at equal specificity and won on source order; anything measuring only the width read it as healthy. | `:focus:not([data-cursor])`, and the gate now reads the style too. |
| 9 | The catalogue opened with the ring on the **search box** — the one control nobody reaches for first. | A screen opens on the thing it is for. |
| 10 | The mana cost **wrapped across two lines** in the rail. A cost split down the middle reads as two costs. | A cost is one word: `display: inline-flex; white-space: nowrap`. |
| 11 | A seat was a card floating in **300px of nothing**. | Filled with what a seat is *for*: the deck's tags and two of its ratings. |
| 12 | The zone browser left **600px empty** with three cards in a graveyard. | Same shape as the board — a list you walk, and the thing under the ring drawn large beside it. |

### Pass two — fifteen things a play-through found

The friction log above came from making 06 work. This came from **using it**:
opening it cold in a browser and walking home → pod → catalogue → dossier →
import → board → targeting → zones → tools → game over, looking at each screen
as a player rather than as its author. Fifteen problems, worst first.

| # | What was wrong | What it is now |
|---|---|---|
| 1 | **The front door was a title on black.** No mark, no art, no atmosphere — and it is the screen a player judges the whole thing by before they have played a card. | A fan of the four commanders you could be dealt, a wordmark, and a lit table behind them. `HomeScreen.tsx` already had the idea; this is it drawn. |
| 2 | **The gate was a wall of keyboard bindings** — a debug affordance dressed as the front door, ten glyph chips before you have pressed anything. | One line. The map is behind **?** for whoever is reviewing without a pad. |
| 3 | **Two things claimed to be "where you are" on every screen.** A gold *Create a pod* and a green *Lock in* are filled, bright and large; the actual cursor was an amber outline somewhere else entirely. | **FILL IS FOCUS.** A control is an outline until the ring is on it, then it fills. Tier lives on the *edge* — gold commit, green confirm, red danger — and never on the fill. Nothing on screen is filled except the thing you are pointing at. |
| 4 | **A locked seat painted itself `--playable` green**, the hue the client uses for "you can cast this". Three locked seats shouted the wrong word. | A `✓ locked in` mark, and the border stays quiet. |
| 5 | **Each opponent carried ten facts** — life, commander damage, creature count, untapped, power, fliers, every mana source, library, hand, graveyard — in 330px. That is a paragraph, and a paragraph is not something you glance at. | The three that decide an attack: **can they block it** (untapped, power, fliers), **can they answer it** (open mana, cards in hand), **is it worth it** (life, commander damage). Library and graveyard decide nothing mid-combat and moved to the zone browser, which now has a reason to exist. |
| 6 | **`5/21 cmd`** needed decoding. | `⚔ 5 of 21`, on their seat, meaning your commander's progress toward killing them; `☠ 8 of 21 · Edgar` on yours, meaning the countdown to losing. |
| 7 | **The phase ribbon spent the top of the screen on ten words**, nine of which answer a question nobody asked — with two adjacent "End"s. | Five segments that fill as the turn advances, and one label naming the live step. Everything else is a shape, not a word. |
| 8 | **The board never said what it was waiting for.** The single most important fact — the game is waiting on *you*, for *this* — was implied by a slab in the corner and stated nowhere. | **The ask leads**, on the line directly above your own board, where you are already looking: `Declare attackers — 3 staged, 3 more can go`. One function computes it; the ask line, the commit slab and the foot's verb all read it. |
| 9 | **The rail was 60% empty** for any permanent without rules text — a vanilla 7/7, a basic land — which reads as a panel that failed to load. | Status chips (`▲ attacking Edgar`, `Trample`, `summoning sick`) and **combat math**: *"Unblocked it deals 7 to Edgar Markov — that is 18 life left. 2 of his creatures can block it."* That is the entire question at declare-attackers and it was nowhere on the board. |
| 10 | **The focused card's name and P/T appeared three times** — on the card, in the rail, in the foot — inside 400px. | The rail owns identity. The foot went back to being a hint bar: verbs, nothing else. |
| 11 | **"Attack with 3" never said which three, or at whom.** | `Attack with 3 → Edgar`, and every staged creature carries a chip in the rail when you land on it. |
| 12 | **The empty chair was 400px of dashed nothing.** | A ghost seat glyph, a line, and two buttons, centred. |
| 13 | **Seven Forests looked like one Forest with a small badge.** `CardStack`'s whole job, invisible. | Stack edges are drawn **always**, and fan properly when the ring lands on them. |
| 14 | **A 2560px monitor got a scaled-up 1280 layout** — the same seven creatures and three summarised opponents, just larger. Scale buys nothing. | Two stage modes, and the difference is the argument. See below. |
| 15 | **Review instruments sat inside the game.** A `kbd · 3` lamp in the board's corner, and *"L3 — every prompt kind"* on the home screen of a game. | Both moved to the bezel, outside the 1280×800 the design is actually claiming — which is also why the gates stop measuring them, correctly. |

Two smaller ones caught on the way: a **stale dossier leaked** a deck name into
the pod's foot (`S.dossier` outliving its overlay), and the **fan of commanders
overlapped the title** because a card rotated 12° has a bounding box 30px taller
than the card.

---

### Pass three — it plays a turn, and it telegraphs

Everything before this was a **tableau**: one frozen state, carefully drawn,
that never changed. You cannot judge a control scheme from a still. What you
need to know is whether the *next* thing the game asks arrives somewhere your
thumb already is, and whether you can tell what just happened.

**So it plays a real loop.** Press `A` on the commit slab and keep going:

```
declare attackers → damage → your second main → end turn
   → Edgar's turn → DECLARE BLOCKERS → damage → your turn, turn 9
```

Life totals move, creatures tap, the log fills, and the phase track *tracks*.
Getting a player to zero ends the game and fills in the result screen from what
actually happened rather than from a fixture.

**That loop is also how `declare_blockers` finally got designed** — the one
thing the README admitted the round had not answered. It is the hardest surface
in the game, and for a reason worth naming: *this decision is about their cards,
not yours.* So their attackers lead, each one a row, and your creatures are what
you assign **into** those rows. Falkenrath Noble flies and you own nothing with
flying or reach, so its row is marked unblockable and carries **no slots at
all** — a row you cannot fill is a row the ring should not accept. The rail
answers the question you actually have: *"Blocks Vampire — 1/1 against your 2/2.
Vampire dies. Elemental survives."*

### Feedback, the way a card game does it

Hearthstone, Slay the Spire and Balatro all spend real time on the same four
beats, and they spend it because **a player who did not see a thing happen does
not believe it happened**:

| Beat | What it is here |
|---|---|
| **Anticipation** | The target braces — a red pulse, one beat *before* anything hits it. This is Slay the Spire's intent system in miniature, and it is most of why its combat reads. |
| **Strike** | A ghost of the attacker winds *back* away from its target, then drives in. The real card never moves, so the layout underneath is untouched and the ring stays where you left it. |
| **Impact** | A ring-burst and a shockwave at the point of contact, a **screen shake** scaled to the hit, a pad rumble, and the damage numeral — Balatro's entire feel is this one beat, done loudly and on time. |
| **Settle** | Everything returns; the life total is the last thing still moving. |

Attackers are staggered **110ms apart**, so three attacks read as three rather
than as one blur, and each carries its *own* numeral so you can see which
creature contributed what. Casting flies the card from your hand to the thing it
is aimed at and the target **perishes** — blanches, shrinks, goes out. The whole
budget is under a second.

Three rules keep it honest:

- **State changes first; the animation only reports it.** A player on
  `prefers-reduced-motion`, or one mashing `A`, gets exactly the same game.
  `REDUCED` collapses every effect to a no-op.
- **Effects live in `#fxlayer`, a sibling of `#app`** — because `render()`
  rebuilds `innerHTML`, and an animation inside it would be deleted half way
  through a strike.
- **The shake composes with the stage scale** via a `--deck-t` custom property.
  Without that, a shake at 103% snapped the stage back to 100% and the "hit"
  read as the layout breaking.

And the **cursor travels** rather than teleporting. A ring that jumps is a ring
you re-find on every press; a ring that moves is one your eye follows for free.
One absolutely-positioned div and a 150ms transition — the cheapest thing that
separates a website with a focus outline from a game.

### Nothing makes you wait

The loudest complaint about every digital card game is being held hostage by its
own animations. Hearthstone shipped a skip gesture years late; Slay the Spire
lets you click through every beat; Balatro puts a speed setting on the main menu
because it knows.

So **every timed beat goes through `beat()`, and any button does it now.** The
attack settle collapses from ~900ms to whenever you pressed. The opponent's
recap skips straight to the blockers step. Measured: 131ms instead of 900.

This is the shipped client's own rule, incidentally — `Table.gateInput` treats a
press during narration as *both* "skip ahead" and the gesture itself, so an
impatient player never loses an input. Same contract, and it is safe for the
same reason: the state change already happened before the animation started, so
skipping cannot desync anything.

### The game opens on the opening hand

Dealing used to drop you straight onto a turn-8 board, skipping the first
decision anyone actually makes. `mulligan` is one of the eleven kinds and the
reel already rendered it — so the deal opens on it, with the seven cards drawn
as **seven cards** above the two answers.

Two things it taught, both small and both real:

- **The answers are deliberately not cards.** Drawing "keep" and "mulligan" as
  two cards out of the hand implies you are choosing *between those two cards*,
  which is the opposite of the question. The hand above is the subject; the
  answers are yes and no.
- **The blurb has to describe *this* hand.** It said "seven cards, three lands"
  over a hand of six with no lands — and *no lands* is the single most
  interesting thing that could be true about an opening hand, so getting it
  wrong threw away the only argument on the screen.

### The stack resolves, and that is how it teaches

It was a list. A list is what a stack *looks* like; it is not what a stack **is**.
The rule that makes Magic hard to learn is **last in, first out**, and no amount
of labelling teaches it as well as watching the top item leave first.

So the stack is a place the ring can go. `A` on the top item resolves it — it
flies to whatever it is aimed at, bursts, and the one underneath becomes the
top. `A` on any *other* item refuses, and says why: *"Only the top of the stack
can resolve — that is what a stack is."* The rail reads a stack item like any
other card, because it is the one you most want to read: it is about to happen.

This is `priority` wearing different clothes. "Let it resolve" **is** the `pass`
action, and this is what that action looks like when it is not a row in a list.

It also caught a real rules bug. `_table.js` stores the stack **top-first**,
matching `StackPanel.tsx` which draws it that way — and taking `STACK[length-1]`
resolved the *bottom*, so Beast Within resolved before the Impact Tremors trigger
that had been put on top of it. Backwards, and backwards in exactly the way the
surface exists to prevent.

### The frame rate claim was wrong, and fixing it is the round's best finding

This README had been asserting **"≥58fps while holding a direction"** as a gate.
It was measured on a desktop, where it is true and meaningless. Re-measured
under **4× CPU throttling — a fair proxy for a Deck APU** — the real numbers
were:

```
full render        28.2ms p50        (4.5ms unthrottled)
holding a direction  18.5 fps        longest frame 118ms
```

**18.5fps.** The gate had been passing because it was pointed at the wrong
machine.

The cause is structural and worth naming, because any direct-DOM port will hit
it and the React port will hit its mirror image: `render()` rebuilds `#app`
wholesale, and **a cursor move is not a board change.** Only four things depend
on where the ring is — the attribute itself, the rail, the foot and the halo.
The thirty permanents, the three seats, the hand and the stack do not.

Two fixes, both small:

1. **`renderCursor()`** swaps the attribute and rebuilds only the rail and the
   foot. Arrows are anchored to permanents, and a cursor move does not move a
   permanent, so rebuilding that SVG every press was pure cost.
2. **The rail is keyed on what it would draw.** It builds a 152px card face with
   an image in it; walking a lane of seven Forests shows the *same card* seven
   times, so keying skips six of those rebuilds outright.

| Under 4× throttle | before | after |
|---|---|---|
| Cursor move | 28.2ms | **10.5ms** |
| Walking a lane | 18.5 fps | **59.7 fps** |
| Worst case (flicking between two different cards every frame) | 18.5 fps | **47.6 fps** |
| Longest frame | 118ms | **28ms** |

**For whoever ports this:** the temptation in React is the exact mirror — put
the cursor in a context that every card subscribes to, and all thirty re-render
on every press, arriving at the same 18fps by a different route. **The cursor
wants to live as an attribute on one element, not as state thirty components
read.** That is the whole lesson, and it cost 3× the frame rate to find.

### Which seat are you attacking?

The biggest gameplay gap left, and it was invisible because two-player is the
shape everything gets built in: **this is a four-player game and every attack
went to Edgar Markov.** In Commander "who do I attack" is not a detail of
declaring attackers — it is most of the decision. Sending a 7/7 at the player on
18 is a different game from sending it at the player on 31.

The pad problem is that choosing a target must not *cost* a press, because the
common case is "all of them, at the obvious one". So:

- **`A` stages the creature at the default seat.**
- **`X` re-aims that creature** through the other seats.
- **The default is the seat closest to dying** — not seat one. Life dominates,
  and commander damage breaks ties, because that is a second clock and only one
  of them counts.

Getting the default right is what makes the extra control *optional* rather than
mandatory. On this board it opens aimed at **Duelist on 18**, not Edgar on 25.

Everything downstream follows the aim: each attacker's **arrow goes to its own
seat**, so three arrows to three opponents read as three decisions; the rail's
combat maths is computed against the seat that creature is actually pointed at;
and the commit control names them — `→ Edgar 5, Duelist 8` rather than the
confident lie `→ Edgar · 13 dmg`. Damage lands per seat, and any seat reaching
zero ends the game.

### Manual mana, because a switch that switches nothing is worse than no switch

`manual_mana` is a real flag on the real `GameView`, and the tool strip had been
offering it since this round began while doing **nothing at all** — which teaches
a player that the settings screen is decorative.

What it actually changes: with **auto mana** the payment solver picks the lands
and you never see it happen. With **manual mana** you tap them yourself, and the
reason anyone would want that is the reason it earns a surface — *the solver
optimises for paying **this** spell, and you may be holding a dual land because
of the spell you intend to cast **next**.*

It reuses the targeting machinery exactly and introduces no new vocabulary: the
lands become the only reachable stops, a `×7` Forest is **seven taps rather than
one**, each tap puts a count badge on the stack, the ask line counts down
(`{4}{G} · 3 more to pay`), the hand and the commit stand down, and `B` backs out
without losing the spell.

### Sound, as a specification

These files cannot ship audio — they open from `file://` with no network and no
assets. But *"add sound later"* is how a game ends up with sound that lines up
with nothing, so **the cues are placed now, at the exact beats they belong to**,
and the palette is a contract rather than a wishlist.

`cue()` records instead of playing, and **the bezel shows the last cue that
fired** — so the sound design can be reviewed by watching it rather than by
reading a table. Wiring it to real audio is one function body:

```js
function cue(name) {
  if (!CUES[name]) return;              // typo guard: a cue must exist
  LAST_CUE = name;
  // if (!S.tools.muted) audio.play(name);   <- the whole of the port
}
```

Seventeen cues, placed at twenty call sites:

| Cue | What it is | Fires on |
|---|---|---|
| `ui.move` | soft tick, 30ms | the ring moving — **the most-played cue in the game**, so also the quietest and shortest |
| `ui.confirm` | warm click | A on anything that does something |
| `ui.back` | reverse of confirm, quieter | B |
| `ui.deny` | dull thud + rumble | an illegal or impossible press |
| `ui.open` | sheet slide | an overlay opening |
| `card.cast` | paper lift and settle | a card leaving your hand |
| `card.enters` | soft thump | a permanent landing on the battlefield |
| `card.perish` | brittle crack, short tail | something dying or exiled |
| `combat.declare` | low brass swell | attackers committed |
| `combat.strike` | whoosh, pitched by power | one attacker moving |
| `combat.impact` | body hit, layered with the shake | contact |
| `life.loss` | descending tone under the numeral | a life total dropping |
| `stack.resolve` | chime | an item leaving the stack |
| `phase.change` | quiet marker | the phase track advancing |
| `turn.pass` | page turn | the turn changing hands |
| `game.win` | **the only long cue in the game** | you won |
| `game.lose` | its inversion, shorter | you did not |

The five rules behind the palette — every one of them something card games
converge on independently:

1. **Every input answers.** A press with no sound feels dropped even when the
   screen changed.
2. **Denial is distinct.** `ui.deny` must not be a quieter `ui.confirm` — it is
   the one cue a player needs to recognise without looking, and it is paired
   with the rumble for exactly that reason.
3. **Weight matches stakes.** `card.cast` is small. `combat.impact` is big.
4. **One voice per beat.** Three attackers striking 110ms apart get three cues,
   not one blur — the stagger that makes the animation readable makes the audio
   readable too.
5. **Mute means mute**, and never changes what happens.

### The game teaches itself, once

A console player never reads a manual and cannot right-click to find out. So the
controls that are not obvious introduce themselves, and then get out of the way
permanently. Four marks, and the rules they follow are the ones games get wrong:

- **One at a time.** A screen of six callouts is a screen nobody reads.
- **Only the non-obvious.** Nobody needs telling that the stick moves. They need
  telling that `L2` exists, because *nothing on screen implies a hidden wheel*.
- **Tied to the moment.** The blocking hint appears the first time you are asked
  to block, not in a tutorial three screens earlier.
- **Dismissed by doing.** It goes when you use the thing, not when you
  acknowledge a popup — pressing the button *is* the acknowledgement, and an OK
  button would be a second thing to learn.
- **Never again.** Session-only here; `localStorage` in a shipped build.

Two bugs came out of building it, and both are the same bug in different
clothes. The callout **queried the previous render's DOM**, because it was built
inside the template string that had not been inserted yet — so the very first
hint a new player should ever see was the one that never showed. And a callout
clamped to stay on screen kept its arrow at a fixed offset, so it **pointed
confidently at the wrong thing**, which is worse than not pointing at all.

Measure *after* the render, not during. That is the third time this round has
learned it — the cursor, the coach mark, and the foot that named the card.

### Undo, for real

The tool strip had promised "takes back your last action" since the round began
and did nothing, which is worse than not offering it: **a player who believes
undo exists plays differently.**

One snapshot per action, capped at twenty, sharing the implementation the
rematch already needed. `ActionPanel.tsx` documents the real constraint and it
is worth honouring — **undo stops being available once an opponent has acted**,
because the engine cannot un-ring that bell. So the stack is cleared when the
turn passes, and both the tool row and the wheel spoke go dead and *say* they
have nothing to take back rather than failing silently.

It immediately earned its keep by catching a bug nothing else would have:
casting a permanent **put two copies on the battlefield and paid for one** —
`fxFly` already invokes its `onArrive` on the reduced path, and the caller
invoked it again. Invisible at full motion, reproducible every time at reduced.
That is the shape of bug a testable motion setting exists to find.

### Animation is a setting, and the OS preference is its default

`prefers-reduced-motion` is the right default and the wrong ceiling. Balatro
ships a speed control on its main menu; Hearthstone and Slay the Spire both grew
one. The reason is not accessibility and is just as real: **on the tenth game
you already know what an attack looks like**, and on a handheld you are often
playing in ten-minute pieces.

So the tool strip carries three settings on one knob:

| | |
|---|---|
| **full** | every beat, at the timings the sequences were tuned at |
| **swift** | the same choreography at 55% — still readable, half the wait |
| **reduced** | no animation at all; effects are no-ops, beats fire immediately |

Measured, driving the same attack to the same state:

```
full     reached main2 in 1030ms   Edgar on 12
swift    reached main2 in  578ms   Edgar on 12
reduced  reached main2 in    5ms   Edgar on 12
```

Making it a real toggle is also **the only way the reduced path ever gets run**.
A media query nobody can flip is a code path nobody has tested — and this round
had been claiming reduced-motion support in this very README without ever having
executed it once.

### A rematch has to put everything back

The moment the board became playable, the fixtures became **mutable state**: the
hand gets spliced, creatures get pushed onto lanes, life moves, mana drains, the
log grows. That is what makes it a game rather than a picture — and it is also
why *Rematch* was a button that could not work, and why a second game in one
session would have started from wherever the first one ended.

The board is snapshotted at boot and restored **in place**, and in-place is the
whole trick: `TABLE`, `byOidAny` and every `data-stop` in the document hold
references to those exact objects and arrays, so swapping them for fresh ones
would leave the cursor pointing at cards no longer on the board. `splice` and
field assignment keep identity; only the contents go back. Rematch drops you on
a fresh mulligan with 12 mana, seven creatures and Edgar on 25.

### Lane order is the client's, and the client's is the table's

`logic/zoneGrouping.ts` declares `LANES = ["Creatures", "Artifacts &
Enchantments", "Lands"]` — top to bottom for the viewer, hand underneath. That
is not a filing order, it is the geometry of playing: **lands sit next to the
hand you play them from, and creatures sit forward, on the line combat is
declared across.** Opponents are mirrored, so the two creature rows face each
other across the middle.

06 had it upside down — my creatures against my own hand, my lands facing the
enemy. Fixed, and the opponents' zoomed board mirrors properly.

### What else the loop caught

- **The rail offered "Send at Edgar" on one of your creatures during *their*
  combat** — not merely the wrong word, an illegal action offered as the primary
  one. Verbs are per-step now.
- **The hand knows what step it is.** One castable card at declare-attackers
  (the instant), six in your second main, one again on Edgar's turn. The hand
  turning green as the phase advances is the clearest demonstration that the
  client knows the rules.
- **A player on zero kept playing.** Now the game ends.

---

### Big screens: spend the room on content, not on scale

**Press `F`.** The stage has two modes and the difference is the whole answer.

**Deck mode** is the reference — a fixed 1280×800 scaled to the window, with the
scale printed on the bezel. It is what a handheld design must be reviewed in,
and it is what every number in this README was measured at.

**Window mode** is what the app should do on a monitor, and the point is that
*scaling a 1280 layout up to 2560 buys nothing.* More room should buy **more
game**:

| Threshold | What the room is spent on |
|---|---|
| ≥ 1500 wide | **The opponent seats stop being summaries and draw their actual creatures.** The summary line becomes a caption for something you can look at. |
| ≥ 1500 wide | The rail widens 262 → 336px, so oracle text stops wrapping every line, and the rail's card grows with it. |
| ≥ 1800 wide | Board cards step 104 → 124px, and the hand with them. |
| ≥ 1100 tall | Lanes get their own rows back instead of sharing. |

Two custom properties carry all of it — `--card-w-board` and `--rail-w`, set by
`fitDeck()` — so nothing downstream needs a media query, and a direction can be
re-tuned by changing two numbers. That is deliberately the same shape as
`useZoomFit` in the client, which already solves for the largest card that
fits; this points the same instinct at the other end of the range.

**The floor does not move.** The opponent mini-boards are held to the same 96px
card minimum as everything else — drawing them at 62px would have been the
original mistake in a new place, showing more by showing it too small. A width
that cannot afford 96px cards does not get the mode, which is what the 1500px
threshold is for. `HANDHELD_ASSERT()` passes on all 24 states **in both modes**.

---

### Polish, specifically

- **Real mana symbols.** The 54 published Scryfall SVGs `fetch_symbols.py`
  already vendored, used everywhere a cost, a produced mana or a colour identity
  appears — including hybrids (`{W/B}`) and the tap symbol, neither of which has
  a letter form at all. This *fixes* a floor problem rather than dodging it: a
  letter on a disc is text and has to clear 16px, where a published symbol is a
  shape and reads at 14 the way a suit pip on a playing card does.
- **Activated abilities are formatted as abilities** — split on the colon into
  what you **pay** and what you **get**, the cost in real symbols in a violet
  pill. `{1}{G}{U}, {T}:` rendered as literal braces was the worst-looking thing
  in 01-05, and an ability card is exactly where it turned up.
- **Rules text renders its symbols inline**, the way `SymbolText.tsx` does.
- **A commander is how you recognise a seat**, so `choose_player` draws three
  commanders rather than three name plates.
- **Four seats, not two.** A two-player board was the easy case and it hid the
  hard one.
- **A land shows what it taps for**, as one hybrid symbol per source rather than
  two pips claiming mana that does not exist.

### Measured

`HANDHELD_ASSERT()` passes on **all 36 reachable states of 06, in both stage
modes** — home, pod, invite, catalogue, dossier, import, board, board-with-
ability, the combat-math rail, reader, zone peek, log, tools, wheel, zoomed
seat, game over, targeting, and all seven modal decision kinds.

```
smallest text 16px   ·   smallest card the ring lands on 103px
0 below the floor    ·   0 undersized hit targets   ·   0 spill   ·   0 tooltips
never more than one cursor   ·   focus ring 3px solid
```

---

### Two bets 01-05 considered and rejected

**Direct-bind** — your first four hand cards *are* A/B/X/Y. Fighting-game elegant,
collapses the moment you have five cards. **Dual-cursor** — left stick picks the
source while the right picks the target. Sounds great; sources and targets live
in different zones at different scales, and it needs both thumbs for one atomic
act, which loses cancel.

---

## Where the hardware actually stops

Measured, not assumed. This is the difference between a plan and a fantasy.

**`file://` is a secure context, so the whole round needs no server.**
`navigator.getGamepads()` is `[SecureContext]`, and every one of these files is
opened off disk. In Chrome:

```
location.origin -> "file://"      window.isSecureContext -> true
navigator.getGamepads() -> a 4-slot array, no throw
```

**A pad must announce itself first.** Chrome hides gamepads behind a user
gesture, so `getGamepads()` returns four nulls until the first button press.
That is why every file opens on *Press any button* rather than pretending to be
connected, and why the lamp in the corner tells you whether you are on a real pad
or the keyboard fallback.

**The Gamepad API sees a 17-button XInput pad, and that is all.** The Deck
reports itself as a Standard Gamepad, so the W3C indices hold. But:

- **The back grips L4/R4/L5/R5 are not exposed.** Steam Input maps them to other
  outputs before the page sees anything, and a player may have rebound them. No
  direction here uses them. Each would ship a Steam Input default instead —
  recommended: **L4 = back, R4 = commit**, both under fingers not holding a stick.
- **The trackpads and gyro arrive as ordinary mouse events**, via Steam Input's
  pad-as-mouse and gyro-as-mouse. This is not a compromise, it is the whole of
  direction 05's argument.
- **Rumble is Chrome-only** (`vibrationActuator`); Firefox in the Deck's desktop
  mode has none. So the rule in `_handheld.js` is that **rumble is always
  redundant with something visible** — it can never be the only channel carrying
  a fact.

**The open product question this round does not answer:** how a Vite web app
reaches a Deck at all. Desktop-mode browser, or a wrapper added to Steam as a
non-Steam game — where Game Mode's Steam Input may not pass the pad to the page
at all. Worth settling before any of this is built.

---

## The numbers

Every gate below is read off the rendered page by `HANDHELD_ASSERT()`, which is
inlined into all five — open any file and type it in the console. The board round
learned that `overflow: hidden` hides layout failure completely: the page reports
`scrollHeight === clientHeight` while content visibly runs under the foot. So
**where a visual property reduces to a number, assert the number.**

Measured at 1280x800, DPR 1, on every reachable screen of every file:

| Gate | Shipped client | All five here |
|---|---|---|
| Smallest text carrying information | **2.11px** | **16px** |
| Elements below 12px | **444 of 635** | 0 |
| Elements below the 16px floor | not measured | **0** |
| Width of a card the cursor can land on | **73.6px** | **96 / 158 / 300px** |
| Focusable or tappable box below 44x44 | not measured | **0** |
| Focus ring width (and `outline-style`) | **none exists** | **3px solid** |
| Cursors on screen at once | n/a | **never more than 1** |
| Elements spilling past the foot | — | 0 |
| Regions collapsed to zero height | — | 0 |
| `[title]` tooltips | **45** | **0** |
| Art drawn above art_crop's ~780px ceiling | — | 0 |
| Broken images | — | 0 |

### The headline metric, defined three ways

**"Cast a spell with a target"**: from the board as dealt, cast **Beast Within**
(6th in hand) at **Falkenrath Noble** (the opponent's flier). Reported three
ways, because a single number would quietly hand the win to 05:

- **presses** — discrete button and direction inputs. In the table above, counted
  from each implemented flow. Every file also carries a **live press counter** in
  the corner, so a reviewer with a real pad checks it rather than trusts it.
- **seconds** — the only way the pointer direction is honestly evaluated, and the
  column that is **not yet filled**: it needs a human with a real Deck, and
  writing a number here from a keyboard would be a fiction.
- **mode switches** — how many times the screen's meaning changes. Cheap to
  count, and it predicts learnability better than either of the others.

**The seconds column is the round's one open measurement.** A keyboard makes
every direction feel equally fine, which is precisely the failure mode this round
exists to avoid.

### What the gates caught that no screenshot would have

Eight of the twelve entries in **06's friction log** above were found by
`HANDHELD_ASSERT()` rather than by eye, and two of them are worth repeating here
because they are the kind that ship: a focus ring with `outline-width: 3px` and
`outline-style: none`, and a `var(--face-fs, 13px)` default that put card faces
under the floor in three files on a screen nobody had thought to check.

Both looked completely fine in a screenshot. That is the whole argument for
making the floor a number a machine reads back.

---

## The phone, and why it is not in this folder

The brief was Deck-first, and this folder is Deck-only. But the down payment is
real and it is worth naming:

**The trackpad, the Deck's touchscreen, a phone's finger and a real mouse are one
`pointermove`/`pointerdown` code path.** Direction 05 is built on exactly that
path and gets all four for the price of one. And the **44px hit floor** every
file holds is the touch minimum, so nothing here has to be re-sized for a finger.

What a phone still needs, and what this round deliberately did not do: portrait,
one-handed reach, and 390px of width — where even 03's spine of five does not
fit and 04's reel is the only direction that survives unchanged. That is a
separate round.

---

## Recommendation

**Build 06.** The five were the argument and it is settled: 06 is the base, and
01-05 are now the record of why it is shaped the way it is.

What 06 proved, and what it costs, in porting order:

1. **A focus ring bound to state, not to `:focus`.** `board.css`, `cards.css`
   and `ui.css` have no `:focus-visible` at all, and `Table.tsx` re-renders on
   every engine push — so a ring hanging off DOM focus blinks out each time the
   server answers. Stamp a `[data-cursor]` attribute from state and draw the ring
   from that. **Biggest win per line changed, and it is most of hover's job.**
2. **A focus trap on the five `aria-modal` dialogs.** They have the attribute and
   no trap; the backdrop blocks clicks and nothing else. 06 hit this as bug #3
   and it is nine lines: whatever is on top owns the ring.
3. **Kill the 45 `title=` tooltips.** Greppable, mechanical, and it is four of
   the five hover-only holes. What replaces them is the rail, which already
   exists — it just needs driving from focus instead of from `onMouseEnter`.
4. **Real symbols everywhere a cost appears.** `frontend/public/symbols/` is
   already vendored and `ManaSymbol.tsx` already draws them; the gap is the
   places that still spell a cost as text.
5. **Fluid rails.** `.table__body`'s `232px … 304px` and `.mat`'s `190px` are the
   whole of the 1280x800 problem. `--card-w-base` is already keyed to `vh`; the
   rails are what is not.
6. **The reel for `PendingDecision`.** `PromptDialog.tsx` is already the decision
   surface and already renders `DecisionOption.card`. Making it a readable reel
   is contained, and it makes every modal decision in the game pad-playable at
   once — including the seven kinds no earlier mockup drew.
7. **The spine summary.** `4 creatures · 2 untapped · 4 power · 1 flier` is worth
   doing on any screen size, and the combat view and `produces` already ship the
   data.

**Do not ship a controller mode without the 16px floor asserted in CI.** It is
the one thing here that cannot be eyeballed — 2.11px text looked fine in every
screenshot anyone had taken of this board for months, and three of the six files
in this folder broke the floor in ways only the gate found.

### What 06 does not answer

- **Seconds.** Every press count here is counted from the implemented flow, and
  every file carries a live press counter — but **nobody has held a Deck**. A
  keyboard makes every scheme feel equally fine, which is exactly the failure
  this round exists to avoid.
- **How a Vite app reaches a Deck at all** — desktop-mode browser, or a wrapper
  added to Steam as a non-Steam game, where Game Mode's Steam Input may not pass
  the pad to the page. Worth settling before any of this is built.
- **Portrait.** See below.

---

## Notes on fidelity

- Same board state as every earlier round, from `data/cards/*.json` and
  `data/decks/*.deck.json` — names, costs, P/T and the decks' own `notes`,
  `tags` and five `ratings` are the real ones.
- **Two cards have no art and are drawn with the fallback plate rather than
  hidden**: `Gyre Strait Leviathan`, which is one of this repo's custom cards
  with no Scryfall printing (the documented ~4% case), and `Terramorphic
  Expanse`, which simply was never fetched into `../art/`.
- **Edit the masters, never the inlined copy.** `inline.py` overwrites whatever
  sits between the markers, so a change made inside a `.html` file's inlined
  block is silently reverted on the next run. This bit twice during the build —
  once on `.fxlayer`, once on a `TOOLS` entry — and both times the symptom was a
  feature that worked, then vanished. The rule: shared behaviour goes in
  `_handheld.*`, 06's fixtures in `_table.js`, and only 06's own structure in
  the `.html`.
- `inline.py` splices `_handheld.css`, `_handheld.js`, `assert.js` and (for 06)
  `_table.js` into each file between markers, so the shared block **cannot**
  drift by hand — which is
  how five copies of one file quietly stop being the same file. `python
  inline.py --check` fails if any file is stale, and is CI-shaped.
- Unlike every earlier round, **the skin is shared and only the structure is per
  file**. Those rounds were five skins; these are five control schemes, and if
  the card face differed between them a difference on screen would be a
  difference in styling rather than in how the pad drives it.
- Verified per file at 1280x800: `HANDHELD_ASSERT().PASS === true` on every
  reachable screen, no console errors, no external network requests, no broken
  images. 06 is checked across all 22 of its states, 01-05 across all of theirs.
- **All six carry the same Deck frame.** `fitDeck()` scales the fixed 1280x800
  stage to whatever window it is opened in and prints the scale on the bezel;
  `deckPoint()` converts window pixels back into Deck pixels, which is what any
  direction with a pointer needs or its cursor drifts further from the pointer
  the further you get from the centre.
- **Mana symbols are the published Scryfall SVGs** from `../cards/symbols/`,
  loaded as `<img>` because `fetch()` is blocked on file:// and these are not.
  They are `aria-hidden`, and every cost that uses one also exists as text.
- No colour-blindness or WCAG-contrast findings appear anywhere in this round.
  [`docs/adr/0006`](../../docs/adr/0006-no-colour-accessibility-requirement.md)
  is accepted and settles it. The 16px floor is a **legibility** gate, which that
  ADR explicitly keeps in scope.
