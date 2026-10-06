# Playtest feedback — cycle 3

Written after playing games through the browser at 1600×950, two-player and
four-player, at all three narration speeds. `frontend/e2e/cycle3.spec.ts` is new
and pins the surfaces this cycle added; `clarity.spec.ts`, `full-game.spec.ts`,
`smoke.spec.ts` and `stacking.spec.ts` still guard everything before it.

Cycle 3 closed every item in [cycle 2's list](playtest-feedback-02.md), including
both of the structural refactors it flagged. The `NewGameScreen` deck picker is
still deferred — it has been deferred since cycle 1, and for the same reason:
there are two decks.

---

## What cycle 3 delivered

Ordered as the cycle-2 doc ranked them.

1. **Combat has one surface.** `CombatPanel` now renders one option button per
   legal pair carrying the server's real `data-action-id`, so the action bar
   stands down for combat exactly as it does for a modal. The doc's note that
   standing it down "deadlocked three e2e specs immediately" was right about the
   naive version and wrong about the conclusion: the bar was load-bearing only
   because the panel carried no ids. Moving the ids rather than deleting them
   keeps every invariant — `clarity.spec.ts` still sees no duplicate id across
   260 decisions, `full-game.spec.ts` still finds a button for every decision,
   and `smoke.spec.ts` still clicks `add_attacker` to reach combat.

   The confirm button stays a composite with no id, because a staged set is not
   one action; the skip button keeps `finish.id`. That was the piece of design
   work the doc identified, and the answer turned out to be that the composite
   does not need an identity — the *parts* do.

2. **The type palette has a lightness range, and the check is automated.** The
   seven fills sat at L≈88% by design; they now climb in even steps of relative
   luminance from land (0.58) to the neutral stock (0.92).

   The doc said twice that the palette check "has no automated form — a
   screenshot has to be read by someone". That is true of layout and false of the
   palette: separability at pod size is relative luminance, which is arithmetic.
   `frontend/tests/palette.test.ts` parses `cards.css`, computes luminance for
   every tone, and asserts a minimum pairwise gap — plus the constraint the doc
   itself set, that the whole dimmed band stays below the whole live band so a
   dark land never reads as disabled. The bound is min/max > 0.556 (the scrim
   multiplies luminance by that); the shipped spread is 0.63. A screenshot still
   has to be looked at, but a hex can no longer quietly collapse the encoding.

3. **A four-player pod stops scrolling.** `OPPONENT_CARD_W` scales with the pod
   (82 / 72 / 60), the compact mat's side column went 132 → 96px, and compact
   lanes tightened their gaps. Together those took a lane's card area from 161px
   to 211px, which is the difference between two cards per row and three. Measured
   in the browser: a mid-game pod went from 192px of hidden content to none.

4. **The mana row says what a spell will cost.** `_cast_options` already proved
   payability by running `solve_payment` and throwing the solution away; it now
   keeps the tapped source oids and ships them as `LegalAction.pays`. Hovering a
   castable card hollows out the pips it would spend.

   Every pip of a tapped source is marked, not one per mana owed: tapping is what
   costs, and a land that makes {G}{U} is gone for the step whether the spell
   needed one of them or both. Pool mana is never marked, because `Payment` does
   not itemise pool spend and claiming one would be the guess the `options`
   payload exists to avoid.

5. **The spotlight draws the card.** `Beat.spotlight` has carried `cardId` since
   cycle 1; `FxLayer` now resolves it through a new `findCardByDefId` and renders
   a `StaticCard`. Events name cards by *definition* id, so the lookup searches
   the stack first (where a spell being cast still is) and then wherever it
   landed. The name plate stays as the fallback — a countered spell has already
   left every zone the viewer can see.

6. **One switch owns the words.** `beatsFor` no longer writes prose; `push` fills
   `Beat.text` from `describeEvent`, which gained a `lookup` parameter so the log
   shows printed names rather than prettified ids. Deleting the duplication fixed
   three things at once that were separately on the list: `mana_spent` narrating
   "You pays {2}{G}", the log and the narration disagreeing about a card's name,
   and the class of bug that put triggers in neither.

7. **Smaller things.** The card preview caps at 52vh instead of taking 460px of
   the rail. Sounds detune ±45 cents per voice, so five lands stop sounding like
   one land five times. `isWounded` is used by `CardFace` and `CardPreview`
   instead of being exported and re-derived inline in both. `mana_availability`
   takes a shared source index built in one battlefield walk rather than
   re-filtering per seat.

### The hand-written items

8. **A turn is a lap of the table.** New `state.round`, parallel to `state.turn`
   rather than replacing it: `turn` counts player-turns and is load-bearing for
   summoning sickness, the first-draw skip, the `max_turns` cap and the RL
   encoding. The track shows the round and keeps the rules counter in its
   tooltip.

   It is engine state rather than `turn // players` on the client for two
   reasons, both of which the first implementation got wrong and the tests
   caught. Eliminations make the division drift permanently. And the starting
   seat is random, so a round boundary anchored on "the index wrapped to 0" puts
   the first boundary in the middle of the opening lap — which is how the e2e
   test failed with turn 4 reading round 3. It is anchored on `starting_player`.

9. **"All attack" and "All defend".** One button each. Attacking is exhaustive —
   every candidate at its first legal defender. Blocking is not, because "block
   everything" is a way to lose a board: `logic/autoBlock.ts` ranks each legal
   pairing survive-and-kill → wall → trade → chump, assigns one blocker per
   attacker best-first, and **excludes chump blocks entirely**. Giving a creature
   away for nothing is a decision a player makes when they are dying, not a
   default; it stays one click away on the card.

   The ranking is deliberately naive about deathtouch, first strike and trample.
   That is stated in the module rather than hidden, because the button is a
   shortcut for a player looking at the same cards — it is not an opponent, and
   it only has to be reasonable and reversible. Both stage locally, so nothing
   reaches the server until Confirm.

10. **The game moves at half the speed.** `SPEED_MULTIPLIER` went
    `{fast: 2, cinematic: 1}` → `{fast: 1, cinematic: 0.5}`, so the default now
    plays at what used to be the slowest setting and there is a slower one below
    it. The labels changed to `0.5x / 1x / ≫`, since they previously read "1x"
    for the slowest thing on offer. The per-beat holds in `logic/events.ts` were
    deliberately not touched: they encode the *relative* weight of events, and
    rescaling twenty judgements by hand to change one is how a palette drifts.

11. **The commander is on screen, always.** A `CommandZone` dock renders the
    commander as a real card wherever it currently is — command zone,
    battlefield, graveyard, exile, or the stack — with the tax as a chip on the
    card rather than on the orb, beside the cost it modifies.

    It is a *gesture* surface like the hand: no `data-action-id`, clicks routed
    through the same `playFromHand` path, so the action bar keeps sole ownership
    of the id and the one-button-per-action invariant holds.

    The viewer's dock sits beside the hand, not in their mat. It was in the mat
    first, and the screenshot showed it clipped in half — orb plus card overflows
    the row. Beside the hand it has the height of the foot, and it sits next to
    the cards it competes with for the turn, which is the truer place for it
    anyway. Opponents keep a small reference dock on their mat.

12. **Lands say what they make.** `card_view` gained `produces` — the union of
    symbols across the card's real mana abilities — and `supertypes`. Lands take
    a body tint from what they tap for and a large mana watermark where the art
    would be, and a basic's rules box is dropped entirely, since its only text
    was the mana ability the watermark now shows.

    `produces` comes from the engine because subtypes cover the five basics and
    nothing else; a nonbasic dual is not inferable, and parsing oracle text in
    the browser is exactly the guess `logic/mana.ts` refuses to make.

    All seven land tones sit at the *same* luminance as each other and as the
    land type tone. Lightness is already spoken for by card type, so varying it
    here would say "this Island is a different kind of card from that Mountain".
    At pod size the tint collapses and the watermark letter carries it — which
    is the check, run, and it holds.

13. **Card-selection modals show cards.** The root cause was not in the dialog:
    `DecisionOption` carries a label and a bare oid, and `findCard` can only
    search the zones `player_view` sends — which excludes libraries. So search,
    scry, surveil and mulligan-bottoming all degraded to name-only buttons.
    `serialize._pending` now attaches a `card_view` to every option that names an
    object, **only for the seat being asked**. That seat guard is the whole
    safety argument: the chooser is entitled to see what they are choosing
    between, and `_choice_actions` only generates buttons for them anyway.

14. **Mana notation is drawn everywhere, not just in a cost row.** A card's
    casting cost had been coloured pips since cycle 1, but rules text and action
    labels still spelled the same notation out — `{T}: Add {G}.` on a land,
    `Wayfarer's Bauble: {2}, {T}, Sacrifice: …` in the bar. Two renderings of one
    notation on one screen, one of which needs decoding.

    `symbolTokens` splits a string into runs and symbols and `SymbolText` hands
    them to the same `.pip` classes, so `{G}` is one thing everywhere. Tap and
    untap get glyphs (↷, ↶) and a grey pill rather than a mana colour, because
    they are costs you pay with the permanent. Notation the engine does not
    support is left as text: inventing a pip for `{G/U}` would be worse than
    showing something the player can look up.

### Found while playing, not on the list

- **The log called you "You's".** Every possessive was built by appending `'s` to
  the player's name, and the viewer's name is literally "You" — so every turn
  boundary read `-- You's turn 2 --`, and the banner said "You's Turn". Fixed
  with the same viewer check the verb agreement uses.
- **The commander vanished while being cast.** `commandersOf` searched the
  command zone, battlefield, graveyard and exile — but between clicking the card
  and the spell resolving it is on the *stack* and in none of those. The dock
  blinked empty at exactly the moment the player was watching it. Caught by the
  e2e test, which is the argument for writing the assertion before believing the
  feature.
- **A tapped card measures as its own height.** `.card--tapped` takes a landscape
  footprint, so `getBoundingClientRect().width` on a lane's first card reports
  60 or 84 depending on what happened to be tapped. Any test measuring card size
  has to read `--card-w`.
- **Every inline mana pip rendered as a full-width bar.** `.face__rules` is a
  flex column and `.pip` sizes itself off `--card-w`, so putting the rules class
  on `SymbolText`'s own span made each pip a flex *item* as wide as the card. The
  text was right, the classes were right, and three assertions passed — it was
  found by looking at a screenshot. `cycle3.spec.ts` now checks a pip's aspect
  ratio, which is the assertion that would have caught it.

---

## Cycle 4 — ranked by impact

### 1. Your own creatures are half-visible during combat

The viewer's mat gets `1fr` of a two-row grid, and at 950px that is about 250px.
A board with two rows of lands pushes the creature lane below the fold, so the
step where you most need to see your creatures is the step where you can see
least of them. `.play__mine` scrolls, so nothing is lost, but the combat panel
sits at the foot and the creatures it is talking about are off-screen above it.

**Try:** collapse the viewer's *land* lane during a combat declaration — lands
are not part of the decision, and they are the lane taking the room. `CardStack`
already proves permanents can collapse without losing addressability.

### 2. A pod board still outgrows its mat eventually

Cycle 3 took a mid-game pod from 192px of hidden content to zero, but there is no
card size that fits twelve permanents into a 333px-wide mat. Late games still
scroll. The new affordance (a CSS `background-attachment: local` shadow pair)
shows when it happens, which is what cycle 2 asked for, but the underlying limit
is real.

**Try:** collapse an opponent's *lands* to a mana-symbol tally rather than cards.
Nobody reads an opponent's individual Forests; what matters is "four green, two
blue, one untapped". `produces` already ships the data. This is the same
observation as item 1 from the other side.

### 3. `pays` is a forecast the client cannot verify

`LegalAction.pays` is solved when the action list is built, and `costs.pay_mana`
re-solves at resolution time. The two run the same solver over the same state, so
they agree today — but nothing pins that, and a future change to the greedy
phase could make the row hollow one land and the engine tap another. The player
would never notice; a test would.

**Try:** assert in `tests/unit/mana/test_action_payment.py` that applying the action
taps exactly the permanents `pays` named. That is a stronger contract than the
current "agrees with `solve_payment`" and it is what the UI actually promises.

### 4. Prompt options caption the card they already show

`.opt--card` renders a face and then repeats `action.label` underneath, so a
search prompt reads "Forest" twice per card. Harmless, but it was written when
the label was the only thing there.

**Try:** show the caption only when it differs from the card's name, which is
also the case where it carries real information ("Put on the bottom").

### 5. "All defend" does not know what its creatures do

The ranking reads power and toughness and nothing else. A deathtouch blocker
trades with anything and is currently ranked as a chump against a 5/5; a first
striker survives fights it is scored as losing; trample makes a chump block worth
less than it looks. `CardView.keywords` is already on the wire.

**Try:** fold deathtouch and first strike into `blockTier` — those two change the
answer most often and are the cheapest to model. Trample is harder, because it
changes how much a chump block is *worth* rather than whether the creatures die,
and that is a judgement the button probably should not be making.

### 6. The combat panel gets crowded in a pod

One button per legal *pair* means one attacker × three opponents is three
buttons, and a five-creature attack is fifteen. It is correct and it is what the
action bar showed before, but the panel scrolls at four players. The card-click
path is unaffected — this is only the keyboard/fallback surface.

**Try:** group by attacker with the defender as a segmented control. The
constraint is that every legal pair must keep its own `data-action-id`, which is
what makes the bar's stand-down safe.

### 7. `Beat.hold` is now the only pacing knob, and it is uncalibrated

Halving `SPEED_MULTIPLIER` was the right immediate fix, but the per-beat holds
were chosen individually against the old multiplier and never revisited as a set.
A `draw` at 110ms and a `tapped` at 90ms are both under the ~120ms it takes to
notice a change at the new default; a `player_lost` at 1100ms is now 1.1s.

**Try:** normalise the holds against a stated floor, and let
`tests/uiStore.test.ts`'s "slow enough to read a beat" assertion cover all of
them rather than one representative value.

### 8. Smaller things

- The mana row's spent pips do not account for floating mana, because `Payment`
  does not itemise it. Adding a `pool_used` vector to `Payment` would close the
  one honest gap in the forecast.
- Opponent commander docks render at 56px, where the card is decorative rather
  than legible. A hover-to-preview would make them useful; right now they say
  "this player has a commander and it is not out yet", which is most of the
  value but not all of it.
- `turnLabel` in `labels.ts` is still exported and still mounted nowhere. It was
  updated to use the round this cycle, which means it is now *correct* dead code.
- `describeEvent` returns `null` for `spell_resolved`, `tapped` and
  `zone_change`, so the log silently skips them while the narration holds a beat
  for each. That is deliberate, but it is now the only place the two consumers
  diverge and it is not written down anywhere but here.
- The `data-spending` attribute on the mana row is read by one e2e test and
  nothing else. It is a test seam, which is fine, but it should be named like one.

---

## What the tests will and will not catch

The suite went from 144 frontend unit tests to 251, from 18 e2e tests to 31, and
gained five Python files (525 passing, unchanged skips).

`cycle3.spec.ts` asserts that the round advances at half the player-turn rate and
that the number on screen is the round; that the commander dock renders a face,
casts from a click, and carries no action id; that lands are tinted and
watermarked and that no land shows a bare tap-for-mana line; that a prompt renders
card faces; that during a declaration every combat action id is in the panel and
none is in the bar; that "All attack" stages every candidate and "All defend"
pairs one blocker to one attacker; that no mana notation is still spelled out and
that a rules-text pip is round rather than a bar; that hovering a castable card
hollows pips and un-hovering restores them; and that a pod's cards shrink and its
mats never hide more than one row.

Two of the new unit files are worth naming. `palette.test.ts` is the automated
form of the palette check both previous docs asked for and could not find, and
it reads the shipped stylesheet rather than a copy of its values, so it fails on
the change rather than on a stale duplicate. `autoBlock.test.ts` pins the block
ranking including its boundaries — exactly-lethal power, damage already marked —
because that is a heuristic and heuristics drift silently.

What none of it catches is still the same thing: whether any of it *looks* right.
The commander dock was clipped in half and every test passed. The log called the
player "You's" through a full green suite. Every inline mana pip rendered as a
full-width bar while three assertions about it passed, because the text and the
classes were both correct and only the geometry was wrong. All three were found
by taking a screenshot and looking at it, which is why `playtest.spec.ts` now
captures twelve surfaces plus a four-player pod — the two
previous cycles only ever got three shots out of it, because the capture loop
stalled on a hover behind a modal backdrop.

The lesson the pip bug teaches is worth keeping: an assertion about *content*
("the right text, the right class") passes happily through a layout failure.
Where a visual property can be reduced to a number — an aspect ratio, a
luminance gap, a scroll overflow — it is worth asserting the number.

Two process notes, both of which cost real time this cycle:

- **The API server does not reload, and killing it is harder than it looks.** The
  cycle-2 doc already warned about the first half. The second half is that
  Playwright's `reuseExistingServer` will happily reuse a server left over from a
  previous run, a manually started replacement will fail to bind and die
  silently, and `/health`'s `games` count is the only quick way to tell: a fresh
  server reports `0`. An hour went into a round-counter "bug" that was a stale
  process serving the previous implementation.
- **Do not strip a property from an object literal with a regex.** Removing
  `text:` from `beatsFor` also removed it from every `banner: { text, tone }`
  nested inside, and the resulting file typechecked.
