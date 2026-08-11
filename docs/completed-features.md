## Cycling — the first ability played from outside the battlefield

### Overview

`/author-cards` filed three precon cards as blocked on cycling — Savai Triome,
Reconnaissance Mission and Krosan Tusker — and the wider catalog had ~71 waiting
on it. The gap records were unusually precise about why, and they were right:
two separate things were missing, and either one alone is a broken card.

**Activation from hand.** `Ability.active_zones` had existed all along and was
read only inside the *triggered* branch of `loader._compile_ability`, so every
activated ability was pinned to `(Zone.BATTLEFIELD,)` and the schema's own
`"hand"` value was silently discarded. `legality._activate_actions` then walked
`state.battlefield` alone. A land sitting in hand was never offered anything.

**A cost that discards the card itself.** `Cost.discard` is the near-miss and is
a different cost: `_discard_pool` returns the whole hand and `ask_objects` lets
the player choose what goes. A Krosan Tusker could therefore be "cycled" by
pitching a spare land and staying in hand — strictly better than the printed
card, and invisible on screen. `Cost.discard_self` names *this* card and asks
nothing.

### The pairing is the safety property

An ability activated from hand whose cost does not remove it from hand can be
activated forever. Cycling pays for itself by leaving, which is exactly what
makes it safe — so the loader refuses the combination outright rather than
trusting each card file to be sensible:

> an activated ability outside the battlefield needs a cost that removes its
> source from that zone

`discard: 1` deliberately does not satisfy it, for the reason above.

### What it refuses

Typecycling (`Landcycling {1}{G}`) fetches instead of drawing, and basic
landcycling narrows what may be fetched — both are different abilities wearing a
similar word. "When you cycle this card…" needs a trigger event the engine does
not have. All three fail the template rather than being quietly turned into
plain cyclers, so those cards stay honestly unimplemented. Krosan Tusker's gap
record was narrowed to that trigger alone rather than retired.

### Harvest

44 cards in one `--tier templates` run, 0 rejected by a gate — every cycling
land in the catalog, from the Triomes and the Ice Age cycling lands to the
Amonkhet deserts.

That run also surfaced a hazard the change had just armed: `run_templates` had
no idea about *fidelity* entries — cards already in the pool doing less than
they print — and translating one mints a duplicate under a deduped id
(`savai_triome_748e6a`), which `CardRegistry.by_name` then loses to the
incomplete incumbent. It also overwrote the `fidelity` gate that is the only
thing making such a card workable. Those entries are now skipped by the template
tier; repairing one means replacing it under its own id via `--tier agent` plus
`--collect --supersede`.

## Variable cost cards — saying which one you meant

### Overview

The ask was "there is no way to select which effect you'd like to trigger
(example: Commander's Sphere)". Reading the code turned one complaint into four
separate things, and the headline example was not the one it looked like.

**Commander's Sphere was never a disambiguation problem.** It has two abilities;
`legality._activate_actions` skipped every mana ability, so it emitted exactly
one action and clicking it fired immediately. What the player could not do was
pick a colour.

**Twenty-seven cards could not be activated at all.** `costs.mana_sources`
collects only tap-only abilities and legality skipped all mana abilities, so
anything in between — every Signet, Cabal Coffers, Prophetic Prism, the filter
and Vivid lands — had no code path that could reach it. Only `arcane_signet` is
tap-only, which is why the four precons never noticed and no test did either.
`costs.offerable_mana_ability` is now the exact complement of the solver's own
test, so the two cannot drift apart, and those abilities are offered
unconditionally because nothing else can play them.

**The kicked cast was unreachable by any gesture.** Legality emits unkicked
first and `Table.onBoardCard` took the first match, so clicking a target with
Into the Roil selected always cast it unkicked — spending the player's decision
for them. Clicking now narrows the selection and hands what is left to the
panel.

**X was never chosen.** Legality stamped `max_affordable_x` onto the action, so
every Fireball was cast for everything the board had.

### What shipped

- `manual_mana`, a per-seat preference beside `full_control`. On, every tap-only
  mana ability becomes an action and a modal one becomes an action per colour —
  every land included. Off for AI seats, so `ACTION_SPACE_SIZE` stays 825 and the
  golden replays are untouched. Mana abilities route through
  `Game._activate_mana`, never the stack (rule 605.3a), so priority is retained.

  *Superseded in part.* Commander's Sphere reading as five colour chips plus its
  sacrifice ability no longer needs the toggle: `offer_all_abilities` covers the
  permanents that have more than one thing to do, which was the case this section
  was really about. See "Mind Stone showed one option" in
  [bugs.md](bugs.md) — hiding the mana ability left the artifact with a single
  action, and a single action is one the board click submits.
- `DecisionKind.CHOOSE_X`, raised by `_cast`/`_activate` before the cost is
  paid. The rail draws a stepper rather than up to 21 buttons — the one
  deliberate exception to "every legal action is a button", recorded in
  `ActionPanel`'s header doc. Four independent auto-answerers (the authoring
  verifier, two test drivers, the heuristic agent) had to learn that the first
  choice is X = 0, or every X card would have silently shipped doing nothing.
- Cast-time modes, using `StackItem.modes` and `EffectContext.modes` — two
  fields that had been declared and never assigned by anything. Only when the
  card's whole effect tree holds exactly one top-level `choose_mode`, so nested
  ones and triggered abilities keep resolving late.
- A window whose only actions are Pass and mana abilities now auto-passes.
  Without it, a board with two Signets stopped at all thirteen steps of every
  turn — and the authoring verifier, which relies on "only Pass is legal" to
  resolve a spell, broke on 27 cards at once.

### Notes

Two things deliberately did **not** change. Kicker stays two cast actions rather
than becoming a decision: legality only offers the kicked variant when it is
affordable, and folding it into a question would lose that gate. And targets are
still enumerated as part of the action, so they are chosen before modes — the
reverse of rule 601.2b, which is why the shared `optional: true` idiom in
`docs/card-dsl.md` is still required.

See `docs/rules-coverage.md`, `docs/card-dsl.md`, `docs/api.md` and
`docs/bugs.md`.

---


## Systematic card support — the deck finished

### Overview

Deck import shipped and immediately exposed the real problem: a real imported
deck had **41 of its 100 cards doing nothing**. The proxy generator gives every
card its name, art, cost, types and keywords, but the rules text is inert. That
is honest, and it is not a game.

MTG has tens of thousands of cards. Hand-writing them does not scale, so this is
a repeatable batch: read a card's oracle text, emit a structured DSL object, and
**refuse to ship any that cannot prove it works**.

Full design in [card-authoring.md](card-authoring.md).

### What shipped

**Playable cards: 230 → 732.** Written by the pipeline, committed to
`data/cards/auto/`, re-verified on every test run.

- **A verifier with six gates**, which is the centre of the design rather than
  the generator. `compile_card` validates *vocabulary*, not *meaning* — a card
  can say "draw two cards", do `gain_life`, and compile, cast and resolve without
  raising. So every candidate must come with an assertion about the board and
  demonstrate it. `tests/cards/test_authoring.py` has that exact case.
- **A priority queue**: cards from a deck somebody imported first, then EDHREC
  rank. It records *why* each card failed, so the tail is a roadmap rather than a
  mystery — `--report` prints it.
- **A deterministic template tier**, free and exact, covering the sentence shapes
  common enough to be worth a rule.

**Auras and Equipment** — the largest block in the catalog, ~1,700 cards. Most of
the object model already existed; what was missing was an Aura *attaching to what
its spell targeted* (after placement, because `reset_permanent_state` clears
`attached_to` on the way in — so an Aura attaching itself during `spell_effects`
arrives enchanting nothing and is silently binned), and a static that reads
`{"attached": true}`. Equipment needed no engine work at all: `Equip {2}` is a
sorcery-speed activated ability whose effect is the existing `attach` op.

**Devoid, Changeling and Prowess** turned out to need none either — the first is
self-implementing, the second is `add_subtype`, the third is a `spell_cast`
trigger the DSL has always been able to say.

**The agent loop** — self-contained work packets on disk, so a Claude Code
session and an unattended API worker read the identical file and write the
identical answer.

### The imported deck, card by card

The headline metric for this work is the deck that started it
(`moxfield.com/decks/brDuu9c6_0yuaoHLijLFHw`). It began at **41 of 100 cards
doing nothing**. It is now at **zero**: all 72 distinct cards play.

Each of the following was a *mechanic* rather than effort, and each shipped with
its own unit tests and a `card-dsl.md` entry:

| Mechanic | Card that needed it |
|---|---|
| Delayed triggers (`delay`) | Arcane Denial, Nezahal |
| Kicker | Into the Roil |
| Modal spells with a shared optional target | Simic Charm, Koma |
| "Its activated abilities can't be activated" (`lock_abilities`) | Koma |
| `else`/`condition`/`repeat` on `may` | Coral Atoll, Jungle Basin, Cultivator Colossus |
| Filtering a `binding` — "is the card I revealed a land?" | Coiling Oracle |
| `*/*` via a static `set_pt` reading the board | Cultivator Colossus |
| `set_types` plus "as long as" conditions on counters | Arixmethes |
| `double_land_triggers` | Ancient Greenwarden |
| `cost_reduction` | Ghalta |
| Monstrosity and `freeze` | Shipbreaker Kraken |
| Token copies (`copy_permanent`) | Scute Swarm, Spitting Image |
| Protection, across damage / enchant / block / target | Greensleeves |
| `not_cause` loop guard, and Partner as an inert keyword | Kodama of the East Tree |
| `double_land_mana`, `freeze_opponent_lands`, `skip_next_untap` | Vorinclex |
| Hybrid mana in the payment solver | Spitting Image |
| Restricted mana and granted abilities | Herd Heirloom |
| Retrace — casting from the graveyard | Spitting Image |
| Suspend — a special action, an upkeep rule, and a free cast | Search for Tomorrow |
| `two_piles` — the one decision an opponent makes | Fact or Fiction |

One of those found a real bug rather than a gap: `self_enters` and
`permanent_enters` are the same engine event, separated only by `source: "self"`,
so a card omitting it fired on *every* permanent entering. Every hand-written
card had it; three new ones did not. The loader now supplies it, because the name
can only mean one thing.

### What the last eight cost

The three that reached into `mana.py` were the risk, and each was landed on its
own with the 160-game arena run in between rather than all at once:

- **Hybrid mana** (625 catalog cards) is additive to `Requirement`, with the
  no-hybrid fast path left exactly as it was — it runs in the solver's inner loop
  on every priority window. Assignment is exhaustive and shared by `satisfies`
  and `ManaPool.spend`, because with one white and one blue, `{W/U}{W/U}` is
  payable only if the two pips take different symbols. The proxy stopped
  narrowing hybrid costs as a result, so imported decks keep their real ones.
- **Restricted mana** (162) never touches the solver at all: sources that may not
  pay for this spell are filtered out before it runs. That works only because
  mana here is tapped at the moment it is spent.
- **Vorinclex's doubling** had to be computed in two places — `_sources_of` so
  legality counts it, `activate_mana_ability` so payment adds it — and a
  disagreement would strand a spell mid-cast. One `mana_produced` helper, called
  from both, plus a test that casts an 8-drop off four doubled Forests.

Two things were deliberately **not** done, and fail loudly instead of silently:
granting a *static* or *activated* ability (the loader rejects it rather than
compiling something legality would never offer), and phyrexian mana (a life
payment, not a colour choice).

### What is left, beyond this deck

Across the whole catalog `--report` ranks **Flashback** (234), **Crew** (74),
**Cycling** (71), **Ward** (41) and **Convoke** (39) as the biggest remaining
blocks by card count. Flashback in particular is now nearly free: it is retrace's
machinery — casting from the graveyard — with a different additional cost.

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

## Build redesigned main page - Done

### Overview

- Mockups were made for a new main page, in [mockups/menu/](../mockups/menu/README.md).
  All five are interactive: pick a deck, open a dossier, set difficulty, import
  from Moxfield, open a chair to another player.
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
      mana, so nothing on the screen competes with the decks for attention.
    - Mock 5 — **Planar Gate**: the screen takes the selected deck's colour.
      Beautiful, and the tint is the only thing telling the four decks apart.

### Task

### Remaining gaps

The board is built against `mockups/05-planar-art.html`. The phase ribbon, the card
layout, the enlarged rail card and the unified action panel have landed. What is
still outstanding is enumerated, with severity and a fix direction, in
[mockup-fidelity.md](mockup-fidelity.md) — read its "Deliberate divergences"
section before changing anything to match a mockup.

The two worth doing first are both the same failure, and neither is cosmetic: the
"you can play this" rim and the combat arrows are thin strokes over a board of
full-bleed illustrations, so the two most urgent facts on screen are carried by
its two quietest marks.

Using: mockups\flow\02-face-up.html