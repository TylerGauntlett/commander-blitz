# Backlog
- Multiplayer online support using a basic system of rooms and room codes

# Features

## All Card Support — done

### Overview
- The application was written to support just 2 precon decks
- Because of this, only cards in these 2 pre-cons are supported to display
- The import command needs to be extended to include all possible cards (art work and basic information)
- This information will be used to support the 2 additional precons planned in the new redesign
- In addition, this should offer general support for moxfield deck looking up so that users can choose their own custom deck when starting a game

### Task
- Add support for all cards, 2 additional precons (Isperia, Supreme Judge and zurgo stormrender), and custom decks via Moxfield deck import

### What shipped

**Custom decks via Moxfield, end to end.** Paste a public deck link and play it.
The whole loop is documented in [deck-import.md](deck-import.md); the short
version is that `api2.moxfield.com/v3/decks/all/{publicId}` is open to a scripted
client (the 403 recorded in `mockups/README.md` was a *different* endpoint), and
every card characteristic comes from our own catalog rather than from the payload.

**"All cards" was mostly a catalog problem, and it split in two.** `cards.sqlite`
already held every English card; what was limited to the precons was the *engine
registry*, the ~149 hand-written cards. So the work was:

- Three columns on the catalog — `oracle_text`, `keywords`, `produced_mana`.
  Without the last, a generated land taps for nothing and a deck of inert lands
  is not a deck. The index grew 7.3 MB → 14.4 MB.
- A **key fix that mattered more than it looks**: the table was keyed on `name`
  alone, so 87 real cards printed with a same-named token — Tarmogoyf, Champion
  of Wits, Adorned Pouncer — had been evicted by it and were unreachable. Now
  keyed on `(name, is_token)`.
- `cards/proxy.py`, which generates a playable definition for a card nobody
  wrote: real name, art, cost, types, stats, keywords and mana abilities, with
  the rest of the rules text inert *and listed*. All 32,827 catalog rows
  generate and compile.
- A **two-layer registry**. `default_registry()` is the authored pool and is what
  every test and the trainer see; `server_registry()` adds `data/generated/`.
  Without the split, `pytest` would answer differently depending on what somebody
  imported last week.

### The two precons

**Isperia, Supreme Judge** and **Zurgo Stormrender** ship, hand-written, at the
Aesi/Edgar bar: every card in both is implemented and covered by
`test_every_card_works`. 81 new card definitions, 230 in the registry, and the
artless set is still exactly five. See [decks.md](decks.md).

Neither commander's own text was expressible before, and none of the three
engine additions is visible in a two-player game — which is why the original two
decks never wanted them:

- `defending` on an `attacks` trigger — *"whenever a creature attacks **you**"*.
  `controller` answers whose creature is swinging, a different question; written
  with `controller: "opponent"` Isperia draws a card when one opponent attacks
  another.
- `attacking` on `create_token` — a token put onto the battlefield already in
  combat, against whoever its maker is attacking. That is mobilize. It is not a
  *declared* attacker, which is the real rule and also what stops it making
  another token forever.
- `was_attacking` on `leaves_battlefield` — last-known information, snapshotted
  where `was_creature` already was, because by the time the trigger resolves the
  object is out of combat and there is nothing left to ask. That is Zurgo's
  second ability.

All three have tests in `tests/unit/test_attack_triggers.py`, several of which
need a three-player pod to mean anything.

**Three cards were dropped rather than shipped wrong**, and the reasons are worth
keeping: Isperia's pillowfort (Propaganda, Ghostly Prison) needs a cost-to-attack
mechanic the engine does not have; Condemn's only legal target is an attacking
creature, which the `test_every_card_works` sandbox has no way to produce; and
Village Rites puts a sacrifice in its casting cost, which the DSL only models on
an activated ability. Each would have been an inert card that looked implemented.

---

## Progressive Zoom — done

### Overview
- The game typically starts with very few cards and ends with very many
- This leads to poor use of screen real estate early in the game as the benifit of being able to show the game state end game
- Instead, the board zooms (both user and CPU) + cards in hand could use a more intelligent zoom system that tries to maximize readability at all stages of the game

### What shipped

**A measured fit solver, not a lookup table.** `frontend/src/logic/zoomFit.ts` is a
pure module that shelf-packs each lane's real footprints — a tapped permanent is
landscape, a stack of basics is one box, a host carries its auras — and returns the
largest card width whose wrapped rows still fit a given height.
`frontend/src/state/useZoomFit.ts` supplies the measurements and applies the
answer through the `cardScale` prop that already ran `Table` → `PlayerMat` → `Lane`.

A count→ratio table was the obvious alternative and it cannot work: it has no idea
whether slack exists. There is 580px of lane budget at 2560×1278 and 160px at
1600×700, and no function of card count knows the difference.

**The measurements say the win is asymmetric, and it is a win in both directions:**

| | 1600×950 | 2560×1278 | 1600×700 |
|---|---|---|---|
| board card, before | 87.4px | 110px | 68px |
| board card, after | 88.9px | **150px** | **52px** |
| lane budget | 305px | 584px | 160px |

At 2560×1278 the board grows 36% into space that was simply being wasted. At
1600×700 it *shrinks* 24%, because the honest answer on a cramped screen is smaller
cards rather than a board you have to scroll. At 1600×950 it barely moves, and the
reason is worth writing down: the empty board already needs 304px of a 305px budget.

**Opponents scale with the viewer, never past it.** Their ceiling is the viewer's
solved width times the existing seat ratio, so the designed proportion holds and a
one-opponent pod with two lands cannot render cards bigger than your own. Each mat
is solved for its own fullness and the fullest sets the size for the row.

### The real ceiling on this, and it is not the solver

**The orb columns own the vertical space.** At 1600×950 the viewer's `.mat__side` is
330px — taller than its own lanes at 299px — and the compact orb is 297px. Together
the two consume 627px of a 649px play area, and the cards get the remainder. That is
why the gain at the most common viewport is ~2%: there is nothing to give.

Worse, the orb's mana row grows as lands are played, so mid-game the viewer's mat
can hide 150px of itself and no card size fixes it, because the overflow is not the
cards. Making that column fluid — or moving the piles out of it — is the change that
would unlock 1600×950, and it is a separate piece of work.

### Deliberate divergence from the plan

The plan called for a binary search. `boardHeight` turns out **not** to be monotone
in card width: a tapped permanent is shorter but wider, so growing the cards can push
a tall card onto the next row and leave a short row behind it, making the lane
briefly *shorter*. Bisection over that returns a size that overflows, silently. It is
a descending scan instead, and `tests/zoomFit.test.ts` pins the counter-example.

The plan also called for rewriting `CardStack`'s container and `HandFan`'s slot pitch
as `calc()` so they could animate. Neither was needed: `--card-w` is a registered
`<length>`, so transitioning it animates every declaration that reads it, and a plain
CSS transition on the two JS-set properties covers the rest.

### Guarded by
Four cases in `frontend/e2e/layout.spec.ts` — the zoom responds on a big display, no
card leaves the 52–150px legibility band, the zoom never grows the board under the
hand at any point in a game, and an opponent's board filling up does not move yours.
`tests/zoomFit.test.ts` holds the wrap model to the *real rendered lane heights* at
three viewports, which is the assertion that caught the model being wrong by 19px per
front lane.

The pre-existing "the viewer's bands do not move" case now pins the zoom
(`startGame(page, { zoomLock: true })`). Progressive zoom moves those bands on
purpose, so with it live that assertion would have had to be loosened past the point
of catching the collapsing lane it exists for.

## CPU Improvements

### Overview
- The AI had minmal training data and preforms very poorly
- This results in almost entirely random decisions that almost always lose the game without it being challenging
- Via this method, that app can offer difficulty levels for the CPU at the main menu that acutally influence the play style
- This is a uniquely hard problem as there are so many different ways to play MTG and variables involved
- Instead of trying to teach the model optimal play through pure machine learning, there is likely more deterministic the system could include at the various skill levels
- Basic concepts like blocking when safe to do so or attacking when safe to do so can be applied at the easiest levels
- From there, more complex decisions can be made to better stear the CPU into the correct choices based on the selected difficulty
- These could be written in the form of subagents writing persona documents for each supported difficulty
- These personas should document general strategies, expected behavior, etc
- This can then be turned into requirements and ultimately code

### Task
- Make the CPU opponents better at various levels using a combination of ML and deterministic conditoinals

---

## Standardize Card Placement — done

### Overview
- The board used to render four full-width rows in the same order on every mat,
  with the lands furthest from the player who controls them
- That is the opposite of how the game is physically played: your mana sits in
  the row nearest you, and creatures go out front
- Creatures and enchantments were also split into separate rows, when on a table
  they sit side by side

### What shipped
- **Two bands per mat.** Creatures (with planeswalkers) beside the global
  artifacts and enchantments across the front, split 2:1 because that is where
  the cards accumulate; lands in the band behind them. They remain two separate
  drop targets — only the row is shared.
- **Lands nearest their controller.** `LANES` in
  `frontend/src/logic/zoneGrouping.ts` is now declared front to back, so the
  array is the layout.
- **Opponent mats are mirrored** (`PlayerMat`'s `mirrored` prop). Their lands sit
  against their own edge of the screen, which puts the two creature bands either
  side of the table's midline and makes combat read as a line.
- **Auras and equipment are tucked under their host**, not loose in the
  enchantment zone. `attachmentsFor` pulls anything attached to a permanent on
  the same mat out of the lanes and `CardStack` draws it peeking out from
  underneath, still individually hoverable and clickable. An attachment whose
  host is on somebody else's board stays a loose card rather than vanishing.
- **Your own board holds still.** All three of the viewer's lanes render at a
  full card's height whether or not they hold anything, and the orb's mana row
  has a reserved slot. Before this, playing your first creature shoved the land
  row down by a whole card, killing it shoved the row back up, and tapping mana
  did it again several times a turn. The cost is one card height of empty slot
  on a mat that fills anyway.

### Known limit — fixed by Progressive Zoom
Opponent mats used to be content-sized, so an opponent's board growing translated
your board down the screen. The fix was the one this section predicted: compact
mats now get a fixed lane height (`--pod-lanes-h`) and scroll inside it, using the
fade affordance on `.mat--compact .mat__lanes` that already existed for it, rather
than reserving width they do not have. Guarded by "an opponent's board filling up
does not move the viewer's board" in `frontend/e2e/layout.spec.ts`.

Reserving their *lanes* is still not done, and the measurement that argued against
it still stands — a compact mat has about 158px of lane width against a 51px card,
so an always-present global lane wrapped their creatures onto an extra row. What
has changed is that it is no longer a layout-stability question, only a width one:
hiding an empty lane cannot move the mat's box any more. `PlayerMat`'s `visible`
is a pure width optimisation now.

**Shipping Isperia and Zurgo made the remaining half of this measurable.** A pod
used to be one deck three times over, because opponent seats cycle whatever
`/api/decks` returns and there were only two. With four decks a pod is genuinely
four different boards, and Zurgo's is a token deck: an opponent mat then hides
about **two** card rows behind its scroll rather than the under-one the fixed
lane height was sized for (136px hidden against a 73px card, measured).

Nothing regressed — the layout code is untouched and the row still never clips.
What changed is that the worst realistic case got worse, and it is now
reproducible instead of hypothetical. `frontend/e2e/cycle3.spec.ts`'s "opponent
cards shrink with the pod" pins its pod to two decks so it keeps measuring card
*sizing*, which is what it was written for; the row-budget question wants its own
test and a taller `--pod-lanes-h` for four-player pods.

### Deliberate divergence from the reference layout
The reference diagram puts library / graveyard / exile in a strip beside the
lands. They stay in the orb column instead: graveyard and exile are consulted
rarely enough that the width is better spent on the board, and the orb already
gives each one a labelled pile.

Guarded by two cases in `frontend/e2e/layout.spec.ts`: "lands sit nearest the
player who controls them" and "the viewer's bands do not move as permanents
enter and leave play". Both band orders render perfectly well and a jumping
board renders perfectly well, so only a measurement notices a regression.

---

## Build redesigned main page

### Overview

- Mockups were made for a new main page, in [mockups/menu/](../mockups/menu/README.md).
  All five are interactive: pick a deck, open a dossier, set difficulty, import
  from Moxfield, open a chair to another player, press `g` for greyscale.
- Combine together elements of the mocks:
    - Mock 1 — **Command Table**: the board's own three-column anatomy, and the
      *seat strip* — opponents are chairs you fill, each showing the deck that AI
      holds and how well it plays. Recommended as the base.
    - Mock 2 — **Deck Rack**: precons as physical boxes with an art window and
      back-of-box copy; the custom deck is a *dashed gap in the rack*; the
      dossier *expands in place* instead of opening a modal; difficulty is the
      shipped brass life dial as a four-detent switch.
    - Mock 3 — **Pod Lobby**: *difficulty as opponents* — one named persona per
      seat with its capability lamps, so a pod can be one Apprentice and one
      Archmage. The direction multiplayer costs nothing to add to.
    - Mock 4 — **Ink & Dossier**: the *comparison matrix* — all decks rated on
      one scale so choosing is a comparison, not four readings. Hue spent only on
      mana; its greyscale twin is identical to the original.
    - Mock 5 — **Planar Gate**: the screen takes the selected deck's colour.
      Beautiful, and its greyscale twin is the honest argument against it.

### Task

### Remaining gaps

The board is built against `mockups/05-planar-art.html`. The phase ribbon, the card
layout, the enlarged rail card and the unified action panel have landed. What is
still outstanding is enumerated, with severity and a fix direction, in
[mockup-fidelity.md](mockup-fidelity.md) — read its "Deliberate divergences"
section before changing anything to match a mockup.

The two worth doing first are both greyscale failures, and neither is cosmetic:
the "you can play this" rim and the combat arrows each carry their whole meaning in
hue, so a player who cannot use colour loses the most urgent fact on screen.

---

## Controller support for Windows with XBox controller

### Overview
- 