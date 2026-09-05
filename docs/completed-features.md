## A cost reduction that counts a supertype — the Kamigawa channel legends

### Overview

Boseiju, Who Endures and Otawara, Soaring City: *"Channel — {1}{G}, Discard this
card: … This ability costs {1} less to activate for each legendary creature you
control."* Two gap records, both naming `cost_reduction_supertype_filter`, and
between them the whole Kamigawa channel-legend cycle — Boseiju, Otawara, Takenuma
and Eiganjo all print the same clause on a `discard_self` ability activated from
hand.

`Legendary` is a **supertype** (205.4a), and 205.4b makes it an independent part
of the type line rather than a kind of type. So "legendary creature" is two
clauses ANDed, and no arrangement of `types` and `subtypes` says it.

### Where the fix lives now

The missing branch was one of fourteen: the loader validated a reduction filter
against `STATIC_FILTER_KEYS` and `costs._reduction_matches` read six of those
keys. That whole story, and the fix for it, is
**"A cost reduction's filter reads every key it accepts"** below — it landed
first, with the Markov Chains deck, because Takenuma needed it too. This section
is what is left once that is in place: the cards, and two smaller things.

**A subset test, not an intersection.** `supertypes` is `issubset` where
`subtypes` is `&`, the same split `effects.selectors.matches` makes: a permanent
has one supertype line a filter names part of, while "for each Vampire" means any
of the named creature types. Written as an *alternative* to the type check rather
than an addition, a legendary planeswalker would count.

**A misspelled name is a load error.** `{"supertypes": ["Legendarry"]}` would
count nothing and read as a discount of zero — a card priced at exactly what it
prints, which is invisible. That is the same failure shape as the dropped key,
one layer down, so it gets the same answer. `subtypes` is not checked, here or in
the selector language, because creature and land types are open-ended and there
is no closed set to check against.

### One import cycle, broken

Reaching `costs.REDUCTION_ZONES` from the loader meant breaking a cycle.
`effects/ops_control.py` imported `can_pay` and `pay` from `..costs` at module
level while `costs` imports `effects.context`, so `costs` could only ever be
imported *after* `effects` — anything reaching for it first got a partially
initialised module. The two ops that charge a cost import them in the function
body now, which is what `combat`, `game`, `legality` and `replacements` already
do.

### The packet learned the distinction

The authoring packet showed workers `static_filter_keys` and nothing else, so a
worker reading it wrote `supertypes` into a reduction because the list said the
word was legal — and had no way to know that `zone` is available there, or that
the relational keys are refused. `cost_reduction_keys` and
`cost_reduction_filter_keys` travel with every packet now.

### One test helper changed

`_provide_the_attacker` read `attacking` at the top level only, and Eiganjo's
"attacking or blocking" is one `any_of` over two branches — so the harness
declared no attacker and a correct card reported as unusable. The assertion is
untouched; the alternative was narrowing Eiganjo to plain "attacking", which is a
weaker card written to suit the harness.

## `{W/P}` — phyrexian mana, and the cast line that carries the choice

### Overview

Gitaxian Probe: *"({U/P} can be paid with either {U} or 2 life.) / Look at target
player's hand. / Draw a card."* A one-mana cantrip that, in practice, is cast for
no mana at all.

Three gap records named `phyrexian_mana` — Mental Misstep, Gitaxian Probe, Gut
Shot — and the report's template-simplified queue named five more creatures for
the same reason. All eight ship now.

Two things were wrong and they pulled in opposite directions.

**`ManaCost.parse` refused the symbol.** `_parse_hybrid` raised on any half of a
hybrid that was not a digit or a colour, and its docstring said so on purpose:
`HybridPip` modelled a *colour choice*, and reading the `P` as a colour would
have made every card in the cycle castable off mana nobody has.

**`cards/proxy.py` silently narrowed it.** `{U/P} -> {U}`, recorded as a "mana
cost simplified" note, which is how the three cards' work packets arrived
carrying a `starting_point` that had already deleted the clause the card is
played for. A hard `{U}` makes Gitaxian Probe a strictly worse Peek and Gut Shot
a strictly worse Shock — and unlike the parse failure, nothing about it was
visible. It is the more instructive of the two bugs: rewriting a symbol to keep
the loader quiet is only a simplification when what is dropped is decoration.

### The shape

`HybridPip` grew a third field, `life`, alongside `symbols` and `generic`. Three
shapes of "either/or" inside a cost, one representation:

| | alternative to the colour |
|---|---|
| `{W/U}` | another colour |
| `{2/W}` | a number of generic mana |
| `{W/P}` | **2 life** |

A separate field rather than a reuse of `generic`, because life is not mana: no
source produces it, no pool holds it, and the payment solver must never be able
to spend it as though a land had made it. `_parse_hybrid` also splits on *every*
slash now rather than partitioning at the first, which reads `{W/U/P}` exactly
and closes a pre-existing hole where `{2/W/P}` raised out of the proxy generator.

Everything that merely *reads* a cost is unchanged and correct by construction:
`value` is 1, `colors` contributes the colour, `symbols_of` counts the chroma. A
Gitaxian Probe cast for 2 life is still a blue, mana-value-1 spell — load-bearing,
because Mental Misstep counters spells of mana value 1.

### The decision this turned on: who chooses which half

The first implementation made it a solver preference — pay with mana when mana is
available, with life when it is not — on the argument that
[ADR 0003](adr/0003-auto-mana-payment.md) already gives up the player's control
over *which* mana pays. It was measured and it was wrong, in both directions at
once:

- `solve_payment` short-circuits on `satisfies(pool, req)` before it taps
  anything, so with an empty pool the life branch always won. Vault Skirge cost
  2 life with six Swamps untapped — a strictly worse card, quietly.
- Even with that fixed, "life only when you must" never offers the play the card
  is famous for: Gitaxian Probe for 2 life *with the Island still up*.

So it is a **cast line**, the way kicker, evoke and overload are.
`_cast_variant` loops over how many Phyrexian pips this line buys with life and
emits one action each — two for the printed cycle, three for Thundering Tanadon's
`{4}{G/P}{G/P}` — labelled *(paying 2 life)*. `Action.phyrexian` carries the
number, exactly parallel to `Action.pay_generic` for convoke and delve, and it is
in `key()` and `to_dict()` for the same reason: two lines at two prices are two
different things to do with one card.

Rule 118.4 bounds the offer, and it is the same boundary `test_pay_life.py`
already pinned for Adanto Vanguard: life may be paid down to exactly 0 and no
further. A player at 2 life is offered the line; a player at 1 is not. Thundering
Tanadon off no green sources needs 4, not 3.

### `paying_phyrexian` — the pip leaves the cost

The mechanism is one method, and it is what kept the change small:

```python
remaining, owed = cost.paying_phyrexian(n)   # ({2}{U/P}, 1) -> ({2}, 2)
```

The bought pips are removed from the cost and the life is returned separately, so
`satisfies`, `assign_hybrid`, `ManaPool.spend`, `solve_payment` and every cost
reduction go on seeing a cost made only of mana. Nothing in the solver learned a
third currency; `Requirement` gained no field. `Game._cast` charges the life in
the *same* `pay` call as the mana — `Cost(mana=remaining, pay_life=owed)` — which
is one payment and one event batch, because 107.4f makes this one symbol of the
spell's own mana cost paid a different way.

Removing the pip rather than replacing the cost is also the difference between
this and the `alternative_cost` the gap records ruled out at length. `{2}{U/P}`
paid the life way is still a `{2}`: Trinisphere taxes it, a cost reduction
shrinks it, and "cast without paying its mana cost" means the same thing it
always did. An alternative cost would have exempted all of that.

`text` and `mana_value` are read off the printed cost and never off the
remainder, so how one casting was paid changes neither.

### The proxy, and the five cards behind it

`_simplify_symbol` no longer rewrites `{X/P}` at all — the branch is gone, not
guarded — and `--tier templates --retry` then harvested five creatures whose only
block had been that note: Vault Skirge, Porcelain Legionnaire, Spined Thopter,
Thundering Tanadon and Slash Panther, each now at its printed cost. The three gap
cards were written by hand.

### The sandbox needed a prop, not a smaller gate

Mental Misstep's "with mana value 1" had nothing to point at: the authoring
harness pushes three dummy spells for a `kind: "spell"` target and they are mana
value 5, 2 and 3, so gate 4 reported "not playable in the sandbox". The role was
added, as `add_dummy_spell`'s own docstring instructs — but **conditionally**,
which is new. Every mana-value-1 spell in the pool is a cantrip, and appending
one unconditionally folded a card drawn by the opponent into the measured outcome
of every card that counters or bounces a spell: Reprieve's `hand_size` for the
opponent moved from 2 to 3, an assertion about Opt sitting inside Reprieve's
verdict. That is precisely what the `legendary_creature` prop's docstring warns
about at length.

So `DUMMY_ROLES` is what every spell-targeting card gets and `EXTRA_DUMMY_ROLES`
is added only for a card none of them satisfies — asked with the very selector
the target spec carries, through the same `matches` legality uses. Every card
measured before this change sees the position it was measured in.

### Frontend: nothing

`{W/P}` through `{G/P}` were already in `manaSymbols.ts`'s `KNOWN` and their SVGs
were already vendored — deck import made phyrexian notation reachable in *oracle
text* long before a cost could carry one — so the symbol renders in the cost row
the day the engine parses it. The cast lines are ordinary `LegalActionDTO`s that
differ only by label.

### One narrowing, recorded

A Phyrexian pip in an **activated ability's** cost must be paid with mana. The
choice is offered as a cast line and an activation is not one. No shipped card
prints such an ability — Birthing Pod's `{1}{G/P}` is the first that would — and
the direction is the safe one: the engine asks for more than the card does, never
less. In `docs/rules-coverage.md`.

## `exile_from_hand` — the free-spell pitch cost, and the alternative cost that could hold it

### Overview

Force of Will: *"**You may pay 1 life and exile a blue card from your hand rather
than pay this spell's mana cost.** / Counter target spell."*

Five cards in `docs/unsupported-cards.md` named `exile_from_hand`, and every one
of them needed the same two things. Neither is useful without the other, which is
why they shipped together.

**1. A cost that exiles a card out of hand.** `cost_keys` already had
`discard_selector`, which picks a hand card by exactly this kind of filter — and
sends it to the **graveyard**, where delirium, threshold, Tarmogoyf and every
reanimation spell can still see it. The printed pitch exiles, and that difference
is the entire reason these spells are priced at nothing. The only exile costs
were `exile_self` (the source, which here is the spell being cast) and
`exile_from_graveyard` (the wrong zone).

**2. Somewhere on the card for a payment that is not mana.** `alternative_cost`
was validated to exactly `{mana, condition}`, parsed straight into a `ManaCost`,
and raised `needs 'mana'` when mana was absent. Force of Will's alternative cost
is a life and a card; Pyrokinesis's has no mana component at all. There was no
node to hang either on.

### Two keys, mirroring `discard` and `discard_self`

```jsonc
"exile_from_hand": { "colors": ["U"] }   // "a blue card": a selector, optional "count"
"exile_self_from_hand": true             // "Exile this card from your hand": no choice
```

`exile_self_from_hand` is kept apart from `exile_self` deliberately. That one is
Phoenix Down's "Exile this artifact", and `costs.can_pay` requires *its* source
to be on the battlefield — so a Simian Spirit Guide written with it loaded clean
and could never be activated. A silently inert card is worse than no card.
Merging them would have meant loosening Phoenix Down's check to any zone; the
sibling flag checks the hand instead, the same check `discard_self` makes.

And it is not `exile_from_hand` narrowed by a selector, for the reason cycling is
not `discard: 1`: the pool would offer the whole hand, and the player could
"activate" the Guide by exiling something else and keeping it in hand.

The pool is the payer's own hand and nothing else — `costs._hand_exile_pool`
walks that list rather than resolving a `zone: "hand"` selector, because the hand
is hidden and an opponent's card must never be fodder or leak into a count the
client can read. Writing `zone` on the selector is a load error rather than a
value overwritten in silence.

**The source is never its own fodder.** 601.2a moves a spell to the stack before
any of its costs are paid, and Force of Will is itself a blue card sitting in the
hand it pitches from — so without the exclusion it pays for itself, is exiled by
its own cost, and never resolves. `_discard_pool` had already learned this on
Bitter Triumph; the new pool learns it in the same place, because legality prices
the line while the card is still in hand.

### `alternative_cost` becomes a full `Cost`

The second alternative cost modelled that way, after `graveyard_cost`, and the
two are now charged in the same halves in the same order: the mana replaces the
printed cost in `legality._cast_variant` and `game._cast`, and everything else on
the node is paid after it (601.2g), with the spell's own oid as the source so the
pool excludes it.

Legality prices the non-mana half through `can_pay` as well as the condition,
because both answer the same question — permission to cast the card this way at
all. A Force of Will held beside nothing blue is not castable that way, and
offering the line and then failing the payment would show a price the player can
never pay.

Two guards, and only the second moved:

- A node that charges **nothing** is refused: it replaces the printed cost, so an
  empty one is a free spell.
- A node that charges **only mana** still needs a `condition`, because that is
  exactly `evoke` and a card spelling it that way is offered twice at two prices
  with nothing to choose between. A node charging something else is exempt —
  Force of Will's line is unconditional and printed, and what it takes instead of
  mana is the reason it is a fair card.

`mana_reduction` is refused on it. "Costs {X} less to cast **this way**" is the
graveyard cost's rider and only `costs.variant_reduction` reads it, off the
flashback branch alone; written here it would load clean and never apply.

### Simian Spirit Guide is invisible to the payment solver, on purpose

`costs.mana_sources` collects only `Cost.is_tap_only()` abilities on the
battlefield, so the Guide's mana ability reaches the player through
`legality._activate_zones`, which already walks their own hand. That is the right
answer as well as the only one available: a solver that exiled cards out of a
hand it was never asked about would spend the card to help pay for a spell.

### Harvest

Force of Will, Daze and Simian Spirit Guide ship. Daze was filed under
`alternative_cost_nonmana` — the same blocker seen from a card whose pitch is a
returned Island rather than an exiled card — and the widened node answers it
whole.

Force of Negation, Misdirection and Pyrokinesis stay blocked, each on a *second*
capability their gap records already name: `counter_to_exile`,
`choose_new_targets` (plus a "spell with a single target" restriction) and
`divided_damage`. Their records keep only those needs.

`tests/unit/test_exile_from_hand.py`: 26 tests.
## "Your life total can't change" -- a two-way lock on a life total -- 118.5

### Overview

Teferi's Protection: *"Until your next turn, **your life total can't change**
and you gain protection from everything."*

The gap record named the closest thing and its three misses, and all three held.
`replace_life_loss` is a `static_effect`, so only a permanent can carry one and
an Instant's `spell_effects` cannot install it; it multiplies the magnitude of a
loss rather than forbidding a change, and a multiplier of zero would still be a
downward-only rewrite; and it is wired into `primitives.lose_life` and the loss
half of `primitives.damage_player` only, so `gain_life` moves the total straight
past it. The `prevent_damage` op is player-scoped and stops damage alone.

### Four doors, because there is no fifth place and no first one

`gain_life`, `lose_life`, the loss half of `damage_player`, and `costs.can_pay`.

The third is the one a single choke point would have implied and does not exist:
`damage_player` subtracts life itself rather than calling `lose_life`, and that
is deliberate -- only the loss is multiplied, never the damage, so a lifelinking
doubled hit gains what was dealt. A lock in two of the three is a life total that
holds still until somebody attacks.

The fourth is not a call at all. 118.4 makes paying life a loss of life, so a
lock makes the cost unpayable; refusing it in `can_pay` means the action is never
offered, which is the difference between a War Room that cannot be activated and
one that draws for nothing.

### No event for a change that did not happen

`LIFE_GAINED` and `LIFE_LOST` are what Marauding Blight-Priest and Bloodthirsty
Conqueror listen for. A lock that moved no life but fired the event would pay out
for a gain nobody made -- the same class of silent-wrong as the change itself.

### What it deliberately leaves alone

The damage. `DAMAGE_DEALT` still fires and commander damage is still tallied;
only the life total holds still. Protection is the effect that stops damage, and
Teferi's Protection prints both sentences precisely because they are different
things. Implementing the lock as a prevention would have been one sentence doing
both jobs and the other one doing nothing.

## Protection over a **player** -- 702.16b/d/i

### Overview

Teferi's Protection: *"Until your next turn, your life total can't change and
**you gain protection from everything**. All permanents you control phase out."*
The One Ring: *"…**you gain protection from everything until your next turn**."*

The gap record named three limits and all three were real. `grant_protection`
resolved its recipients through `choose_objects` and skipped every oid that was
not `on_battlefield`, so a seat could never receive it. Its qualities were built
only from `from_colors` (each entry validated against `KNOWN_COLORS`),
`from_types` and `from_subtypes`, none of which can express "everything". And it
wrote an `until_eot` `TempEffect`, which the cleanup step ends this turn -- so
the "until your next turn" clock did not exist for it. `protection_from` was
object-keyed throughout, so there was no player-side reader either.

### Three decisions

**"Everything" is a quality, not a flag.** It goes into the same flat set of
strings every other protection quality lives in, as `PROTECTION_EVERYTHING`.
Four rules read that set; a boolean beside it would be a second question asked
in four places, which is how one of them comes to be forgotten. The comparison
short-circuits on it before the source is read at all -- which is the whole
content of 702.16i, since no set built from types, subtypes and colours can hold
a colourless source.

**A table, not a player field.** `GameState.player_protections`, beside
`damage_shields`, for that record's reason: Teferi's Protection is an Instant
and leaves nothing behind to own the effect. One entry per quality, so the
readers get the same flat set the object side already hands them.

**Two readers, and knowing it is two.** Targeting and damage. A player cannot be
blocked; the "can't be enchanted" half comes through targeting, because an Aura
that enchants a player targets it as it is cast. Writing four readers to match
the object side would have been two of them dead.

### The half that a hexproof shape gets wrong

Protection stops **anyone**, its controller included: your own Bolt cannot be
pointed at you. So the check in `_player_allowed` sits *above* the
"you"/"opponent" clause rather than beside it -- the same line `can_be_targeted`
already draws, and the test pins it directly.

## "At the beginning of your first main phase" — the precombat main event — 505.1b

### Overview

Black Market Connections: *"**At the beginning of your first main phase**,
choose one or more — …"*

Five phase boundaries were in `TRIGGER_EVENTS` — `upkeep`, `draw_step`,
`begin_combat`, `postcombat_main`, `end_step` — and the precombat main was not
one of them. `Step.PRECOMBAT_MAIN` already had a branch in `turn.begin_step` for
714.2d's Saga lore counters and emitted no event beside it.

### Why not `upkeep`

It is a step too early, and on the wrong side of the draw. A Black Market
Connections hung on the upkeep hands its controller the turn's Treasure and
charges the life *before* they have seen the card they drew, which changes which
mode a player takes. The test pins the ordering rather than only the firing, for
that reason.

### Why "first" needs no ordinal

505.1b makes every main phase after a combat a **postcombat** main, inserted
ones included — the same rule that makes `postcombat_main` fire per phase and
print the word "each". So PRECOMBAT_MAIN can happen at most once in a turn and
the printed word "first" is already exact. No turn flag, no counter.

### Frontend: nothing, deliberately

A new `EventType` is the change that normally forces `describeEvent` and
`beatsFor` work. Not this one: its four siblings have no case in either, because
a log line saying "a phase began" adds nothing to a log that already shows the
step. Checked rather than skipped.

## "Choose one or more --" — the fifth modal count — 700.2

### Overview

Black Market Connections: *"At the beginning of your first main phase, **choose
one or more** — • Sell Contraband — Create a Treasure token, and you lose 1
life. • Sell Rare Pets — Create a 3/2 black Demon creature token with flying,
and you lose 2 life. • Sell Your Soul — Draw a card and you lose 2 life."*

`modal_bounds` knew four clauses and none of them is this sentence:

| written | says | why not |
|---|---|---|
| `count: 1` | choose exactly one | deletes the words "or more" |
| `all_if` | choose every mode | entwine — a floor, and it is paid for |
| `up_to: true` | choose up to N, **none allowed** | every mode here costs life, so "none" is a better card |
| `up_to_if` | a conditional ceiling, floor of one | needs a `condition`, and this sentence has none |

`or_more: true` keeps `count` as the floor and opens the ceiling to every mode.

### Why the floor is the load-bearing half

Each of Black Market Connections' modes costs life. Written with `up_to`, the
trigger would be free to choose nothing every turn, which is a strictly better
enchantment than the one printed and would look entirely normal on screen. This
is the same asymmetry the `up_to` section already records, pointing the other
way: a missing floor and a missing ceiling are both silent, and each favours a
different card.

### The guards

`or_more` and `up_to` on one op are refused: one keeps a floor, the other
removes it, and `modal_bounds` would silently let `up_to` win. A `count` that
already reaches every mode is refused too — "choose two or more" of two modes is
"choose both", written the long way, and it would load as a question with one
answer.

## A cost reduction's filter reads every key it accepts — 601.2f

### Overview

Takenuma, Abandoned Mire: *"Channel — {3}{B}, Discard this card: Mill three
cards, then return a creature or planeswalker card from your graveyard to your
hand. **This ability costs {1} less to activate for each legendary creature you
control.**"*

`loader._validate_cost_reduction` checked a reduction's filter against the whole
of `STATIC_FILTER_KEYS`; `costs._reduction_matches` read six of those keys and
dropped the other fourteen without a word. So Takenuma's `supertypes` validated
at load time and vanished at pricing time, and the ability counted every creature
its controller had.

### Why it had to be the filter and not the card

There was no way to write the sentence around it. "Legendary" is not a subtype,
so `subtypes` cannot approximate it; a `condition` is a gate rather than a count,
and gating the whole reduction on "you control a legend" would have made one
legend worth the same as four. Splitting the ability in two is the shape the
Crown of Gondor record already refused: nothing switches the cheap copy off.

### The failure direction is what makes it worth a section

An ignored **narrowing** key always widens the filter, so the ability is cheaper
than it prints. Nothing fails: not the loader, not a gate, not a game. The card
simply costs less than the card. That is the same class of silent-wrong the
authoring pipeline's six gates exist to catch, arriving from underneath them.

### What is deliberately still absent

`attached`, `paired` and `paired_with_source` are refused at load time rather
than implemented. Each names a relation to one particular permanent — the thing
the source is attached to, its soulbond partner — and a reduction counts a board;
in a `count` they ask how many permanents are *the* permanent. Refusing is the
half of the fix that stops the silent drop returning under a different key.

`tests/unit/test_reduction_filter_keys.py` is the witness, and it pins the
regression directly: a lone non-legendary creature must take nothing off.

## `gift` — a cast-time promise that costs nothing and names a seat — 702.164a

### Overview

Parting Gust: *"**Gift a tapped Fish** (You may promise an opponent a gift as you
cast this spell. If you do, they create a tapped 1/1 blue Fish creature token
before its other effects.) / Exile target nontoken creature. If the gift wasn't
promised, return that card to the battlefield under its owner's control with a
+1/+1 counter on it at the beginning of the next end step."*

The gap record (`data/authoring/gaps/parting_gust.json`) had already run the
experiment and the finding is the whole argument for this change. `kicker` was
the only free-standing optional cast-time flag an effect could read back, and it
is wrong here twice:

- **it is mana-only, and a gift is free.** `loader` refuses a kicker whose mana
  value is 0 — verified, `kicker: "{0}"` raises `kicker '{0}' costs nothing` —
  and the refusal is right: a kicker that costs nothing is one cast offered
  twice. But 702.164a makes the promise a **601.2b choice**, made with the modes
  and X, paid for with nothing;
- **it is a bool, and a gift names a player.** Every key of `additional_cost`'s
  `CostModel` is a payment the *caster* makes from their own side of the board,
  and nothing in the cost language names a recipient at all.

### What was measured, and why it mattered

The near miss was not hypothetical. `additional_cost: {}` with
`additional_optional: true` and a `cmp` on `additional_paid` **loads, and passes
all six authoring gates, while the gift branch never runs once**:
`_additional_ceiling` offers times 0 and 1 at the same price, and
`verify._play_and_check` picks its cast line with `kicked=card.kicker is not
None`, which is `False` for such a card — so the harness always took the times=0
line and measured the half of the card that was going to work anyway.

That is the shape of the requirement, not a footnote to it: **whatever flag
legality can offer, the authoring harness has to be able to ask for**, or the
mechanic inherits the same hole. `find_play` grew a `gifted` argument beside
`kicked` and `multikicked`, and `_play_and_check` passes `card.gift is not None`
— the identical argument kicker's line makes, because promised is the strictly
larger claim. Gate 4 still casts it unpromised, so both branches are exercised.

Proven rather than asserted: with the real Parting Gust and the expectation
`{"opponent_battlefield_count": 6}`, the unpromised line leaves the opponent's
board at 5 and the promised line at 6, so a gift that shipped inert fails gate 5.
Aiming its `create_token` at `"you"` instead of at the promisee — the exact way
this ships wrong — was run and does fail, with *"opponent battlefield is 5,
expected 6"*.

### The shape

`gift` is a **string**: what is promised, as the printed noun phrase, because the
residual gate compares it against the printed "Gift …" line and a card declaring
`gift: "a card"` must not be able to claim a printed "Gift a tapped Fish".

Legality offers one promised cast line **per opponent** at the printed price —
emerge's shape ("one line per victim"), not kicker's bool — because
"*an* opponent" is one seat and which one is a real choice with the game on it.
`Action.gift_to` carries it, `StackItem.gift_to` carries it onto the stack, and
`GameObject.cast_gift_to` is written before `spell_effects` run so it outlives
the spell, the way `cast_kicked` and `cast_overloaded` do.

`each_opponent` is the near miss and is wrong in the way that is hardest to
notice: it is three times the printed card at a pod and *identical* to it in a
two-player game.

The card reads it two ways, and the two are different questions:

| | |
|---|---|
| `{"gift_promised": true/false}` | "**if the gift wasn't promised**, return that card…" — a condition beside `kicked`, `evoked` and `overloaded` |
| `"gift_recipient"` | "**they** create a tapped 1/1 blue Fish" — a player spec, resolving to **nobody** when no promise was made |

The second is what makes the reward conditional with no `if` around it:
`op_create_token` loops `select_players` over its `controller`, and an empty list
creates nothing. It is also why the loader's half-a-gift guard accepts *either*
spelling as a reader — a card whose whole gift line is "gift a card (they draw a
card)" branches on nothing and writes only the player spec, and refusing it would
refuse the simplest printed shape the mechanic has.

### No new decision, no new event, no server or frontend change

The promise is a **cast variant**, so it rides on the action legality already
builds; there is no `DecisionKind` and nothing to auto-answer in `verify._answer`.
Game state is serialized generically and `LegalActionDTO.kind` is a bare string,
so the extra cast line reaches the client as data it already renders.

### Also fixed on the way

`create_token`'s `controller` was never validated as a player spec, although
`op_create_token` resolves it through `select_players`. A misspelling was the
quietest error the op had: a bad *string* raises `DslError` mid-resolution, in
the middle of a game rather than at load, and every mapping form fails silently
by resolving to nobody — a card that prints "they create a token" and creates
none. It is checked at load time now, with the guards for `token` and
`attacking`.

### Coverage

`tests/unit/test_gift.py`, and `t_gift` / `t_gift_creature` in
`tests/data/testing.cards.json`. The boundaries it holds down are: both lines are
offered and the unpromised one is first; the promised line costs exactly the
printed cost; one line per opponent at a three-player pod and only the promised
seat receives; the token arrives **tapped** (measured on the opponent's turn,
because the caster's own turn rolls through an untap step before priority comes
back); the unpromised line creates nothing and schedules an `end_step` return
that arrives with its `+1/+1` counter under its owner's control; the promised
line schedules nothing at all and the exiled creature never comes back; a gift
permanent still knows who was promised after the `StackItem` is gone; `find_play`
can ask for either line; and the loader refuses half a gift in four directions.

## An Aura that enchants a **player** — 303.4a / 702.5b / 704.5n

### Overview

Overencumbered: *"Enchant opponent / When this Aura enters, enchanted opponent
creates a Clue token, a Food token, and a Junk token. / At the beginning of
combat on enchanted opponent's turn, that player may pay {1} for each artifact
they control. If they don't, creatures can't attack this combat."*

The gap record (`data/authoring/gaps/overencumbered.json`) had already run the
experiment, and its finding is the whole argument for this change: the only
expectation that passed about the shipped card was `zone: "graveyard"`. Rule
303.4a lets the enchant ability name a **player**; the engine could only attach
to an object, so the Aura resolved, enchanted nobody, and `sba._tokens_and_
attachments` moved it to the graveyard with cause `aura_unattached` before its
own enters trigger could resolve. Three printed sentences, a mana cost, and no
game effect at all.

Four things were missing, and the record names all four:

| in the card | what the engine had |
|---|---|
| "Enchant opponent" | `attached_to`, an oid; `_attach_aura` attaching only on `ref.kind == "object"`; an SBA that bins anything else |
| "enchanted opponent", "that player" | player specs for you / opponents / everyone / the active player — none of them "the one this Aura is on" |
| "on enchanted opponent's turn" | `TriggerModel.controller` of you / opponent / any, where "opponent" is *every* opponent at a pod |
| "creatures can't attack this combat" | `cant_attack_player`, which deliberately exempts planeswalkers, and the `cant_attack` static, which has no duration |

### Tier: A — a field, a spec, and one key on an existing op

No `TempEffect.kind`, no layer in `_compute`, no `DecisionKind`, no `EventType`
and no API field. The host is a plain field on `GameObject`, written by one new
primitive and read by four callers; `enchanted_player` is a name in
`PLAYER_SPEC_NAMES`; the combat lock is a boolean on the op that already
installs attack restrictions. Nothing reaches the server or the frontend.

**Three of the four needs cost nothing beyond the first.** The trigger clause
needed no new vocabulary at all — `is_active_player` already takes a player
spec, so *"at the beginning of combat on enchanted opponent's turn"* is
`controller: "any"` plus `{"is_active_player": "enchanted_player"}`, and the
`may` + `pay` + `times` half already worked.

### What was built

- `engine/objects.py` — `GameObject.attached_to_player`, cleared by
  `reset_permanent_state` beside `attached_to`, and in `to_dict`. **A second
  field, not a second meaning for the first**: a player id and an oid are both
  `int`, so one field holding either could not be read without a discriminator
  at each of seven readers that all mean "the permanent I am on" — the
  characteristics layer, the `attached` selector, trigger filters,
  `_detach_all`, phasing, bestow and the state-based action. A seat number in
  that field is an oid pointing at an unrelated object.
- `engine/primitives.py` — `attach_to_player`, and `attach` clearing the seat
  link so an Aura is attached to exactly one thing (303.4). `restrict_attack`
  takes `planeswalkers`, part of the dedup key so a narrow entry cannot swallow
  a wide one.
- `engine/stack.py` — `_attach_aura` takes the spell's first target of **either**
  kind. No Aura has two enchant clauses, so one loop is the printed reading.
- `engine/sba.py` — 704.5n as written: attached to an illegal object *or player*,
  or to nothing. A player still in the game is a legal host; one who has lost is
  not, and the Aura falls through to the graveyard with them.
- `engine/effects/selectors.py` — `"enchanted_player"`, read off the ability's
  own source. Also accepted as a selector's `controller` (*"for each artifact
  **they** control"*), in `matches` and `_zone_owners`.
- `engine/characteristics.py` — the same word in the static filter `_matches`,
  and `is_attached` reading either host. Both were required rather than
  optional: an unrecognised controller word matches **every** permanent, so a
  static naming one player would silently name the table.
- `engine/structs.py` / `engine/combat.py` — `AttackRestriction.planeswalkers`,
  and the clause in `attack_target_forbidden` that reads it.
- `engine/effects/ops_board.py` — `planeswalkers` on `cant_attack_player`.
- `cards/loader.py` — `_validate_enchanted_player` (the spec only on an Aura,
  walking the whole card so a static's `affects` is covered) and a bool guard on
  `planeswalkers`.

### Planeswalkers: the third divergence, and the same rule for deciding it

`cant_attack_player` exempts walkers, `cant_attack_you` includes them, goad
includes them — and this line includes them. The answer follows **what the
printed sentence names**, never a house rule:

- *"You can't attack that player this turn"* names a seat, and attacking
  somebody's planeswalker is not attacking them (506.2 — the Ghostly Prison
  ruling).
- *"Creatures can't attack this combat"* names **no defender at all**, so there
  is no seat to read narrowly and all three of 506.2's attack targets are
  forbidden.

Written as `each_player` against `each_player` with the flag, rather than as a
third spelling of the sentence: `restrict_attack` drops the self-pairs nobody
could declare, so the cross-product is exactly "nobody attacks anybody". The two
near misses are both statics — `cant_attack` is read off `_battlefield_statics`
for as long as its source sits there, and this lock is bought and lost by a
payment every combat while the Aura never moves.

### What the test proves

`tests/unit/test_enchant_player.py`, over three cards in
`tests/data/enchant_player.cards.json` — a minimal "Enchant player" Robe, the
Overencumbered prototype, and `t_creature_aura`, deliberately the **wrong**
card: the same `enchanted_player` clause on an Aura that enchants a creature:

- the Aura **cast at a seat** arrives on the battlefield with
  `attached_to_player` set and `attached_to` empty, and is not binned — the
  regression the capability exists for;
- the counterfactual: an Aura attached to nothing is **still** binned, and one
  whose enchanted player leaves the game goes with them;
- the enters trigger pays out to the **enchanted** seat, and at a three-player
  pod to that seat only — where `each_opponent` would pay two;
- the Aura on a *creature* names nobody, and makes no token: `[]` rather than a
  fallback to the controller, which would point the card at its own caster;
- the toll is billed to the enchanted player, and scales with **their** artifacts
  — a third player's three artifacts do not raise it, which
  `controller: "opponent"` would;
- the upkeep trigger fires on the enchanted player's turn and on neither of the
  other two, asserted at turn one so "it fired eventually" cannot pass;
- **no ADD_ATTACKER is offered at all** when the toll goes unpaid — the step is
  skipped, which is what "creatures can't attack" looks like from legality — and
  paying leaves both the seat and the planeswalker on offer;
- the planeswalker boundary from both sides: the wide restriction empties
  `legal_planeswalker_defenders`, the narrow one still leaves the walker
  attackable, and the two are separate entries in the table;
- the **wearing-off**: the next turn's combat is free, asserted as an offered
  attack rather than as an empty list, because an empty list is also what
  "nothing was ever installed" looks like;
- the loader refuses `enchanted_player` off an Aura, including inside a static's
  `affects`, and a non-boolean `planeswalkers`.

### Guarded by

`.venv/Scripts/python.exe -m pytest tests/unit tests/cards -q -p no:warnings`,
and `ruff check src scripts tests`.

## An attack prohibition that names a subtype and a seat — 508.1c

### Overview

Combat Calligrapher: *"Inklings can't attack you or planeswalkers you control."*

The gap record (`data/authoring/gaps/combat_calligrapher.json`) had already done
the analysis, and it was right: the sentence carries **three** things at once,
and the engine had each of them separately.

| in the sentence | what the engine had |
|---|---|
| a filter on the *attacking* creature | `cant_attack`, which takes no defender |
| a *defending* seat | the `cant_attack_player` op, which takes no filter |
| "for as long as this permanent is here" | a static — but no defender-scoped one that forbids |

Every substitution is a different card, and each is a card the log would narrate
as if it were right:

- **`cant_attack`** would stop Inklings attacking *anybody*. That is strictly
  stronger than the printed line, and it would switch off Combat Calligrapher's
  own third line, which hands each opponent a tapped, attacking Inkling
  expressly so that they keep swinging at each other.
- **the `cant_attack_player` op** is keyed on the pair of seats in
  `state.attack_restrictions` and carries no creature filter at all. Its
  `duration` is required precisely because it is a resolving one-shot with no
  permanent to hang off — so it cannot be a creature's continuous ability, and
  there is no third duration that would make it one.
- **`attack_tax`** is defender-scoped *and* filtered, and it prices the attack.
  An unpayable tax is a prohibition; a payable one is Propaganda.

### Tier: B — a continuous effect, and no new layer

A new `STATIC_EFFECTS` entry read by two new predicates in `characteristics`.
No `TempEffect.kind`, no primitive and no place in `_compute`, for the reason
`cant_attack`, `cant_block` and `attack_tax` have none either: this is a
**permission**, not a characteristic. A keyword or a layer would be a lie about
what the card says, and `chars` has nowhere to put "…but not at that player".
Nothing reaches the server or the frontend: `LegalActionDTO.kind` is a bare
string and the ADD_ATTACKER actions are simply not offered.

### What was built

- `engine/characteristics.py` — `attack_defender_forbidden(state, oid,
  defender)`, written as `attack_tax`'s twin with the price taken out: the same
  `_battlefield_statics` walk, the same `source_obj.controller != defender`
  seat test, the same `_matches` filter. And
  `any_defender_attack_prohibition(state)`, the cheap half of the guard below.
- `engine/combat.py` — one clause in `attack_target_forbidden`, the
  per-attacker/per-defender seam `cant_attack_player` built and goad reused, so
  legality, `add_attacker` and the RL action mask cannot disagree. And the
  static joins `attack_restrictions` in `can_attack`'s guard against a creature
  with nowhere left to swing.
- `cards/loader.py` — `cant_attack_you` in `STATIC_EFFECTS`, and a guard
  requiring `affects`.

### Planeswalkers: the opposite answer from the op, and not a house rule

`attack_target_forbidden` exempts `attack_restrictions` at a planeswalker
(506.2, the Ghostly Prison reading) and does **not** exempt this static. The two
answers differ because the two printed sentences differ:

- *"You can't attack that player this turn"* is a sentence about being attacked,
  and attacking somebody's planeswalker is not attacking them.
- *"Inklings can't attack you **or planeswalkers you control**"* names the
  walkers out loud, so nothing has to be inferred in either direction.

Goad made the same divergence, in the same predicate, on the same argument, and
it is why that argument was taken as a parameter rather than assumed. Because a
planeswalker's controller **is** the defending player and
`legal_planeswalker_defenders` passes it, one seat test covers both attack kinds.

This half is only sayable because **attacking planeswalkers is implemented** —
`tests/unit/test_planeswalkers.py` holds it. `docs/rules-coverage.md` still
listed it under *Not implemented → Combat*; that line was stale and is corrected
in the same change, because the card's second clause rests on it. A vacuous
reading — "no planeswalker can be attacked, so the clause is satisfied by
nothing" — was available and is not what shipped.

### What the test proves

`tests/unit/test_attack_prohibition_by_subtype.py`, over three cards in
`tests/data/cant_attack_you.cards.json` (an Inkling, the wall, and `t_ink_lock`,
which is deliberately the **wrong** card — the `cant_attack` version of the same
sentence, kept as the counterfactual the way `t_naive_foundry` is):

- it **narrows** rather than removes: the walled seat is withheld and every
  other opponent is still offered, where the counterfactual grounds the Inkling
  entirely;
- the filter is real — a Bear attacks the walled seat as normal — and two walls
  close two seats;
- **planeswalkers**: the walker behind the wall is not offered to an Inkling, is
  offered to a Bear, and a walker with no wall in front of it is offered to
  both; and the `cant_attack_player` op still exempts walkers, pinned from the
  other side so the widening cannot have leaked;
- it points **one way**: the wall's own controller's Inklings attack everyone
  else, and it says nothing about attacks in the other direction;
- `add_attacker` refuses what legality withheld — the two halves of the seam;
- the **boundary**, one opponent and one wall: the Inkling is not a legal
  attacker, a creature *compelled* to attack owes nothing it cannot legally do,
  and the declare-attackers step is skipped rather than offered with no legal
  action in it;
- the **wearing-off**: the seat reopens the moment the source leaves, mid
  declaration, and the compelled creature's requirement comes back with it;
- the loader refuses a wall with no filter, a filter key that is not a printed
  characteristic, and a `cost` (which would be a second, silent spelling of
  `attack_tax` that nothing charges).

### Guarded by

`.venv/Scripts/python.exe -m pytest tests/unit tests/cards -q -p no:warnings`,
and `ruff check src scripts tests`.

## A granted *static* ability, and an `owner`-scoped static filter — 903.3

### Overview

Inspiring Leader: *"Commander creatures you own have "Creature tokens you control
get +2/+2.""*

The gap record (`data/authoring/gaps/inspiring_leader.json`) named **two** needs
and both blocked the card on their own.

`grantable_abilities` refused a static outright — `loader._compile_card` raised
*"only triggered and mana abilities can be granted, not static"* — so the honest
wording was a hard load error rather than a silent no-op. And
`STATIC_FILTER_KEYS` had `controller` and no `owner`, so "creatures you **own**"
could not be said at all; `owner` existed in exactly one place,
`COST_REDUCTION_FILTER_KEYS`, which a static's `affects` cannot reach.

### Tier: B — a continuous effect, and no new layer

The widening needed **no new code in the characteristics pipeline**, which is
both the design and the reason it is safe. `characteristics.abilities_of`
appends a granted ability to the **recipient's** list, and
`_battlefield_statics` walks that list rather than the printed face — so a
granted static arrives already sourced on the recipient and is applied in the
same fixed layer as a printed one. No `TempEffect.kind`, no primitive, no
reordering of `_compute`. Nothing reaches the server or the frontend.

Everything source-relative inside the granted ability then means the right thing
for free: the quoted anthem's `controller: "you"` is the commander creature's
controller rather than the Background's, and two commander creatures put two
entries in that walk, so the tokens get +4/+4 without anything counting them.

### Why this cannot break layers-lite

The constraint of [ADR 0001](adr/0001-layers-lite.md) is that a static's filter
may not read another static's output. Three facts keep it:

1. *Who receives* a grant is decided by `_ability_statics` plus `_matches` on the
   granter's `affects` — printed characteristics and board state only.
2. *What the granted static affects* is decided by `_matches` too, by the same
   rule.
3. `_ability_statics` collects **only** off printed faces, so a granted
   `grant_ability` or `lose_all_abilities` is never collected at all. That
   severed edge is not new — it is the divergence from 613.8 that shipped with
   `lose_all_abilities` — and it is exactly what stops static-grants-static
   recursion.

So a grant changes only *which permanent a static is sourced on*. The fixed
order is over effect **kinds**, and is untouched.

### What was built

- `engine/characteristics.py` — `_matches` reads `owner`, mirroring the reading
  `costs._reduction_matches` has taken since Visions of Glory: writing `owner`
  **suppresses** the defaulted `controller: "you"`, because a filter that named
  ownership and not control is asking the other question, and a defaulted
  control clause on top of it drops exactly the stolen-commander case the key
  exists for. `_battlefield_statics` grew the argument above as its docstring,
  since it is the function the whole design rests on.
- `cards/loader.py` — `owner` in `STATIC_FILTER_KEYS` and out of
  `COST_REDUCTION_FILTER_KEYS` (one spelling, not two dialects), with
  `_check_owner_key` shared by `affects`, `blockers`, counting filters and cost
  reductions. `PLAYER_WIDE_STATIC_EFFECTS` hoisted out of the `affects_player`
  check site so it has one definition, and `GRANTABLE_STATIC_EFFECTS` **derived**
  from it as `STATIC_EFFECTS - UNGRANTABLE_STATIC_EFFECTS` — every static read
  through `_battlefield_statics`, which is the honest boundary rather than a
  hand-picked list.
- `cards/loader.py` — `_check_grant_targets`, and two bugs it caught that the
  widening would have made ordinary. The compiled `grant_ability` static never
  carried its `ability` index at all, so `abilities_of`'s
  `static.get("ability", 0)` read `0` for every card — invisible until a card had
  two grantable abilities, which the quoted static makes normal. And an
  out-of-range index in either form was a silent no-op.

### What it refuses, and why each refusal is not fussiness

- **The ability statics and the player-wide ones** cannot be granted: their
  readers walk printed faces, so a granted one would load clean, print a line of
  quoted text and never apply.
- **The one-shot `grant_ability` op** may not hand a static over. Its grants are
  pointers `_battlefield_statics` never walks; the continuous form is a
  different key.
- **`{"chosen_type_of": "self"}`** inside a granted filter is refused rather than
  picked between: the substitution reads the filter's *source*, an author means
  the granter, and the engine would read the recipient — which has chosen
  nothing, so the filter matches nobody.

### What the test proves

`tests/unit/test_granted_static_ability.py`, over an Inspiring Leader compiled in
the test rather than added to `data/cards/`:

- nought, one and two commander creatures give the tokens +0, +2 and **+4** — the
  stacking the near-miss `{"exists": {"is_commander": true}}` condition cannot
  do;
- a non-commander creature is not granted it, and the Background does not gain
  it;
- an opponent's tokens are untouched, and a **stolen** commander creature pumps
  its thief's tokens and stops pumping yours — the grant follows ownership, the
  anthem follows the recipient's controller, and no anthem on the granter can
  split those two;
- a commander you merely *control* is not granted it, while the same board read
  with `controller: "you"` is (3, 3) — both directions of the near miss, in one
  place;
- the wearing-off: clearing `is_commander` takes the anthem away the same turn;
- the loader refuses a granted ability static, a granted player-wide static, an
  out-of-range grant, the op pointing at a static, `chosen_type_of`, and an
  `owner` that names nobody.

### Guarded by

`.venv/Scripts/python.exe -m pytest tests/unit tests/cards -q -p no:warnings`,
and `ruff check src scripts tests`.

## A triggered ability that chooses its modes on the stack — 603.3d

### Overview

Oltec Matterweaver: *"Whenever you cast a creature spell, choose one — • Create
a 1/1 colorless Gnome artifact creature token. • Create a token that's a copy of
**target** artifact token you control."*

The gap record (`data/authoring/gaps/oltec_matterweaver.json`) had verified that
everything else on the card compiles: `copy_permanent` takes `objects`, the
`is_token` selector key exists, `gnome_1_1_c` is in the token pool, and
`retreat_to_kazandu` shows a modal `choose_mode` inside a triggered ability
already works. What was missing was a **moment** for the second bullet's target
to be declared in.

Mode-owned targets shipped for spells (`TargetSpec.mode`, `CardDef.mode_targets`),
and the loader refused them on an ability outright — *"'mode' only works on a
card's own 'targets' — an ability's modes are chosen as it resolves, which is
after the moment its targets were declared."* That was true of the engine and
not of the rules. **603.3d** puts a triggered ability's modes *and* its targets
at the one instant it is put on the stack, applying 601.2b then 601.2c exactly
as a cast does; the engine only had the second half.

### The three ways of writing it without `mode`, all measured

Each is a different card, and the second bullet is not the half that breaks:

- **A plain ability-level target.** It is declared for *every* trigger, so
  `filter_legal` answers `any_legal` False and the **whole trigger fizzles**
  whenever you control no artifact token — which is the state of the board on
  the first creature you cast in every game, because the Gnome is itself the
  first artifact token. It also fizzles the trigger when the token is removed in
  response even though the controller meant to take the Gnome bullet.
- **The same spec with `optional: true`.** It survives that
  (`filter_legal` returns `remains or not had_targets`), but it lets the copy
  bullet be taken having declined the target — a mode that silently does nothing
  — and it still forces the target to be named before the mode is known.
- **A `chooser: "controller"` selector inside the mode.** The
  `retreat_to_kazandu` shape. It resolves at the right time and **is not
  targeting**: no `became_target` event, no ward or shroud check on your own
  token, and no 608.2b fizzle when the chosen token is gone.

### Tier: A — no new decision kind, no new event, no new op

`ask_mode` and `ask_targets` already compose, and both questions already had a
generator to be asked from: `push_triggered_ability` became one when Bojuka Bog
was fixed. Nothing reaches the server or the frontend — `StackItem.modes` is
already serialized and `DecisionKind.CHOOSE_MODE` is already answered by every
seat, the RL encoder and the authoring verifier.

### What was built

- `engine/carddef.py` — `Ability.mode_targets`, the ability-level twin of
  `CardDef.mode_targets`; `Ability.cast_time_modes` now answers for a
  **triggered** ability as well as an activated one (a static never reaches the
  stack); `Ability.specs_for_modes`, and `CardDef.specs_for_modes` rewritten to
  share one `_specs_for_modes` with it — the ordering *is* the content, and two
  copies of it are two chances to disagree about which mode a stored ref belongs
  to.
- `engine/stack.py` — `push_triggered_ability` asks `_choose_trigger_modes`
  first and then the chosen modes' targets, recording both on the item
  (`modes`, `modes_answered`) so `op_choose_mode` finds the question answered
  rather than asking again on resolution. `_choose_trigger_targets` takes a
  **spec list** rather than the ability, because a modal trigger's target list
  is not the printed one. `_resolve_ability` splits the stored refs with
  `ability.specs_for_modes(item.modes)`, which is how 608.2b's re-check knows
  which mode was chosen.
- `cards/loader.py` — `_compile_ability` splits its target list into card-level
  and mode-owned the way `compile_card` does, and `_check_mode_targets` gained
  `on_trigger`. An **activated** ability is still refused, and the message now
  says why it is the one that cannot: legality enumerates one activation per
  legal target tuple, so its targets are fixed before `Game._activate` asks
  which mode.

### 601.2b: a mode with no legal target is not offered

This is the whole card, and it is what `_choose_trigger_modes` gates on. A mode
with no `mode_targets` enumerates as `[()]` — one legal way to take it — so the
Gnome bullet is always on offer without a special case, and with nothing else to
copy it is the *only* offer, taken without a prompt.

`targeting.selectable_modes` asks the same question for a spell and is
deliberately not reused: it has no bindings to pass, and a trigger's target line
may name what the trigger found. Asked without them, the offer would be computed
against a different board than the declaration a line later.

"Choose one **that hasn't been chosen**" (Henrika Domnathi) is filtered here
too. `op_choose_mode` strikes spent modes off only on the branch that asks, and
it no longer asks — so without this an unfiltered offer would put a spent mode
back on the table.

### What the test proves

`tests/unit/test_modal_triggered_targets.py`, over a test-only
`t_matterweaver` in `tests/data/modal_trigger.cards.json`:

- with **no** artifact token, the Gnome bullet is the only mode offered, is
  taken without a question, and **still makes its Gnome** — the case all three
  workarounds get wrong;
- a Treasure an *opponent* controls does not open the copy bullet, because
  "you control" is half of "no legal target";
- one artifact token is the boundary: both bullets are then offered, to the
  trigger's controller;
- the copy bullet declares its own target as the ability goes on the stack and
  fires `became_target` there (603.2d); the Gnome bullet declares **no** target
  at all;
- with two artifact tokens the target is a real second question, asked after the
  mode and never before it;
- 608.2b: removing the targeted token fizzles the copy bullet and creates
  nothing, while the same removal on the same board leaves the Gnome bullet
  untouched — the split an unconditional ability-level target cannot make;
- the loader still refuses `mode` on an activated ability, without a single
  top-level `choose_mode`, out of range, `optional`, or with a caster-chosen
  size.

### Guarded by

`.venv/Scripts/python.exe -m pytest tests/unit tests/cards -q`, and
`ruff check src scripts tests`.

## `was_cast` and `is_active_player` — two loop guards on one card

### Overview

Wedding Ring: *"When this artifact enters, **if it was cast**, target opponent
creates a token that's a copy of it. / Whenever an opponent who controls an
artifact named Wedding Ring draws a card **during their turn**, you draw a card. /
Whenever an opponent who controls an artifact named Wedding Ring gains life
**during their turn**, you gain that much life."*

The gap record (`data/authoring/gaps/wedding_ring.json`) had verified that
everything *else* on the card already compiles — the `player` target plus
`copy_permanent` with `controller: {"target": "t1"}`, the `draw` / `you_gain_life`
triggers with `controller: "opponent"`, the `exists` filter scoped by
`{"binding": "event_player"}`, and `gain_life` off `{"binding": "amount"}`. Two
condition leaves were missing, and both are **loop guards rather than flavour**:
this card's payload is a copy of itself under an opponent's control, and its two
watchers read every draw and every life gain at the table.

Both had a near miss that compiles, which is why neither could be skipped.

### "If it was cast" — 603.6e

The clause is about *this* arrival on the battlefield. Without it, the copy
Wedding Ring makes has an enters trigger of its own, and copies again — per
opponent, without bound.

`{"any": [{"cast_during": "beginning"}, …]}` over every phase is the reduction
the gap record proved compiles, and it is exactly `obj.cast_step is not None`.
That stamp is written once by `stack.push_spell` and cleared by **nothing**:
`reset_permanent_state` leaves the `cast_*` flags alone on purpose, so an enters
trigger can still ask whether its permanent was kicked or evoked, and oids
survive every zone change. A Ring that was cast, died and was reanimated answers
`True` and hands out a second free copy. `not_cause: "token"` is the other near
miss and names one cause to refuse: it stops the self-copy and does nothing about
a blink, a reanimation, or Show and Tell.

### "During their turn"

`is_your_turn` compares `state.active_player` to `ctx.controller`, and
`triggers._matches` evaluates every trigger condition with
`controller=obj.controller` hardcoded — so it can only ever ask about the
ability's own controller. `{"is_your_turn": false}` compiles and reads "not your
turn", which coincides with the printed clause **only in a duel**. This engine
plays pods, and at three seats it is a strictly wider card: it fires when one
opponent draws during a *third* player's turn.

Nothing bridged it. No `value_keys` leaf evaluates to a player id, so `cmp`
cannot compare two; `validate_selector` refuses any `controller` string outside
`you`/`opponent`/`any`, so `{"count": {…, "controller": "active_player"}}` does
not load; `has_turn_flag` is keyed to the source. `"active_player"` was already
in `PLAYER_SPEC_NAMES` — what was missing was any way to *ask* about it.

### What was built

- **`GameObject.entered_by_cast`**, stamped by `zones._enter_battlefield` on
  **every** arrival, before the enters replacements and long before the
  `ENTERS_BATTLEFIELD` event the trigger queues off. Two facts joined, because
  each alone is a wider card: the arrival `cause` says the object got here as a
  *resolving spell*, and `cast_step` says a player actually cast it — which a
  **copy** of a permanent spell fails (707.10) even though it resolves.
- Deliberately **not** cleared by `reset_permanent_state`. Nothing off the
  battlefield may read it except the 603.4 re-check of the very trigger it
  gates, after the permanent has already left — and there 603.6e wants the
  last-known answer.
- **`{"was_cast": true}`** and **`{"is_active_player": <player spec>}`** in
  `CONDITION_KEYS`. The second takes the full spec `select_players` resolves, the
  way `is_monarch` does, so a trigger writes `{"binding": "event_player"}` and
  `triggers.event_bindings` already carries it.
- **Load-time guards.** `was_cast` must be a literal boolean (`"false"` is a
  non-empty string and would read as `true`, which on this card is the
  difference between one copy and one per reanimation), and the loader confines
  it to a `self_enters` trigger: the condition reads the ability's **own**
  source, so on `permanent_enters` it answers about the wrong object and
  anywhere else it reads a flat `False` for ever. `is_active_player` refuses a
  bare `true`, a misspelled seat, and `"active_player"` — a tautology, and
  therefore a "during their turn" clause with no clause in it.

### What it does not do

Neither leaf is in the static condition language or in a cost reduction's
whitelist. A static is evaluated with no event and no bindings; a cost is priced
before anything reaches the stack, which is the same line `cast_during` sits
behind.

### Test

`tests/unit/test_was_cast_and_their_turn.py` — 20 cases. The two that carry the
argument are `TestOnlyThisArrivalCounts`, which puts `was_cast` and the
`cast_during` reduction to the *same object* after a reanimation and pins them
apart, and `TestTheThirdPlayersTurn`, which is a three-player pod asserting that
`{"is_your_turn": false}` gets that seat wrong in the same position.

Wedding Ring is expressible whole: cast, an opponent gets one token copy;
reanimated, nobody gets anything; and at three seats the draw and life-gain
watchers fire on the drawing opponent's own turn and on no other.

## `cant_attack_alone` / `cant_block_alone` — a restriction on the declaration

### Overview

Toby, Beastie Befriender: *"When Toby enters, create a 4/4 white Beast creature
token with **'This token can't attack or block alone.'**"*

The gap record (`data/authoring/gaps/toby_beastie_befriender.json`) had proved
both halves of the failure. Every prohibition the engine owned was
per-creature — `characteristics.attack_forbidden` takes one oid and sees nothing
else in the declaration — so writing the token with `cant_attack`/`cant_block`
would have printed a Beast that can never attack or block: strictly stronger
than the card, and invisible on the board. And the token itself did not exist;
substituting `beast_4_4_g` *passed the text gates*, which would have shipped a
green abilityless 4/4 under Toby's printed white Beast line.

*Alone* is a restriction on the **declaration as a whole** (508.1c, 509.1b). The
same creature is legal beside a second attacker and illegal by itself, so there
is nothing to refuse when it is picked — it is judged when the declaration is
finished, which is where menace and Tromokratis' `require_all` already lived.

### What was built

- **Two static effects**, not one flag on `cant_attack`. A flag would have been
  read by every existing caller of the absolute prohibition; two names also let
  a card print the half it prints, and the queue holds all three wordings.
- **`combat.attacks_valid(state, player)`** — the counterpart `blocks_valid` had
  never had. `finish_attackers` performed no whole-declaration validation at
  all, so a correctly shaped static would have had nowhere to be enforced.
- **`combat.drop_illegal_attacks`**, the mirror of `drop_illegal_blocks`, called
  first thing in `finish_attackers`: a creature dropped there never taps and
  never fires `ATTACKS`, because it did not attack.
- **The alone clause in `blocks_valid`/`drop_illegal_blocks`**, counting the
  defending player's whole declaration rather than one attacker's — the second
  blocker does not have to be blocking the same creature.
- **`legality._attacker_actions` withholds "Done attacking"** while the
  declaration is illegal, and hands it back when there is no `ADD_ATTACKER` left
  to offer, exactly as the blocking side does. Withholding without that escape
  is a step with no legal action in it.
- **The token**: `beast_4_4_w_alone`, 4/4 white Beast, both statics, each ability
  carrying the printed sentence.

Two of them declared together are legal — each is the other's company — and the
count is read live, so a companion that dies mid-declaration was never company
(506.4) and the creature left behind is dropped.

Toby is expressible whole: his second line ("As long as you control four or more
creature tokens, creature tokens you control have flying") needed nothing new,
being a `grant_keyword` static over `{"controller": "you", "types": ["Creature"],
"is_token": true}` under a `cmp` condition counting the same.

## `cast_free` — a free cast out of a looked-at window

### Overview

Perception Bobblehead: *"{3}, {T}: Look at the top X cards of your library, where
X is the number of Bobbleheads you control. **You may cast a spell with mana
value 3 or less from among them without paying its mana cost.** Put the rest on
the bottom of your library in a random order."*

The gap record (`data/authoring/gaps/perception_bobblehead.json`) had already
probed every spelling the DSL offered, and the finding is the reason this is
worth a run: the natural one **loads and silently does nothing**.

`play_exiled` is the only selector-driven free cast in the language. It defaults
its selector to `exiled_with: "self"`, which is answered by `obj.exiled_by` — and
`exiled_by` is written in exactly two places, `op_exile` under `until_leaves`
and `op_hideaway`. `look_at_top`'s exile destination goes through `_move_found`
→ `move_object` → `reset_permanent_state`, which never sets that field and
actively clears it. So `look_at_top {"destination": "exile"}` followed by
`play_exiled` hands the second op an empty pool. The card loads, resolves, logs
an exile, and does nothing else. Nothing fails; it is just a blank ability.

The other three are each a different card:

- `playable_this_turn` is the **impulse** permission — play it later, at its
  printed cost, expiring with the turn. `docs/card-dsl.md` keeps that distinct
  from `play_exiled` on purpose, and "without paying its mana cost" is the other
  side of that table.
- `hideaway` has the right *shape* — bounded top-N, take one, bottom the rest at
  random — and it sets `exiled_by`, so `play_exiled` can follow it. But its
  exile is mandatory and unfiltered: it forces a card out of the window when
  nothing there is castable, and a card exiled and not cast is gone from the
  library for good instead of going to the bottom with the rest. Strictly worse
  than the printing, and observable.
- `cascade` and `ripple` free-cast off a library already, but their tests are
  hardcoded — "nonland card with lesser mana value than this spell", "the same
  name as this spell" — and neither takes a parameter a card can substitute a
  selector into. Cascade's depth is also unknowable, where this card looks at
  exactly X.

### Tier: A — one key on an existing op

No new op: `look_at_top` already had the bounded window, the selector, the
`count`/`optional` vocabulary through `pick_from_pool`, and `rest_to_bottom`.
No new `DecisionKind`: `_offer_free_cast` composes `ask_yes_no`, which cascade
and ripple have used since they shipped. No `EventType` — `cast_for_free` fires
`SPELL_CAST` with `free=1`, which the log and "whenever you cast" triggers
already read. No server or frontend change.

### The design question: where the free cast is bolted on

Three places it could have gone, and the choice is forced by *where the declined
card ends up*.

1. **A key on `look_at_top`** — chosen. `op_look_at_top` branches: with
   `cast_free`, what `pick_from_pool` narrowed goes to `_cast_from_window`
   instead of `_move_found`, and that helper returns the oids that actually
   reached the stack. Everything else — refused, unpickable, filtered out by the
   selector, a land — is still "the rest", and the existing `rest_to_bottom`
   branch bottoms it unchanged. One op owns the window and the remainder, which
   is the only arrangement where those two cannot disagree.
2. **Record `exiled_by` in `_move_found`.** One line, and it would make
   `look_at_top {"destination": "exile"}` + `play_exiled` work. It also changes
   the card: it exiles cards the printing only ever *looks at*, and a declined
   card sits in exile permanently rather than going to the bottom. That is
   hideaway's bargain, and refusing it is rule 3 of the brief — a
   half-implemented mechanic makes a cheaper card than the printed one.
3. **A binding the free cast reads.** `look_at_top` stores the window under
   `as`, a later `play_exiled` reads it. It costs a new selector key, an
   implicit contract between two ops, and it *still* leaves the "put the rest on
   the bottom" bookkeeping split across the pair — the second op would have to
   hand the first one back its refusals.

### What shipped

- `src/automtg/engine/effects/ops_cards.py` — `cast_free` on `op_look_at_top`,
  and `_cast_from_window`, which offers each picked card through the existing
  `_offer_free_cast` and returns what reached the stack. `taken` is now computed
  on both branches so `rest_to_bottom` reads one variable either way.
- **Lands are filtered out of the pool** under `cast_free`. "Cast **a spell**" —
  a land is played, never cast (601.2), and `cast_for_free` would put one on the
  stack without complaining. The filter cannot live in the card's selector,
  because "mana value 3 or less" is true of every land ever printed, so the
  selector that spells Perception Bobblehead would otherwise offer a free
  Forest-on-the-stack. Filtered lands are still bottomed: they were looked at.
- `src/automtg/cards/loader.py` — two guards. `cast_free` on any op but
  `look_at_top` is refused (`exile`, `search_library` and friends ignore unknown
  keys, so the card would load and charge full price for a spell the printing
  gives away). And beside `cast_free`, the keys `destination`, `tapped` and
  `playable_this_turn` are refused: each is read only on the branch `cast_free`
  replaces, so written together one half is silently dropped — and
  `playable_this_turn` is the *opposite* card besides.
- `tests/unit/test_free_cast_from_window.py` — 23 tests.
- `docs/card-dsl.md` — "Casting for free out of the window", a third column on
  the impulse-draw comparison table, and a pointer from the `look_at_top`
  paragraph. `docs/rules-coverage.md` — a row under Implemented.

### 601.2b, in both directions

Casting without paying is still casting. `_offer_free_cast` shares
`suspend.cast_for_free`, so the spell goes on the **stack**: its "whenever you
cast" triggers fire, it can be countered, and its targets are chosen now. It
gets **no haste** — that flag belongs to suspend, and a creature cast this way
that could attack immediately would be a strictly better card.

And "you **may** cast" is optional twice over: the pick itself is declinable
(`optional: true` on the selector), and the offer is a yes/no. A refusal — or a
cast that cannot happen because nothing is a legal target — folds the card back
into the rest rather than losing it.

### Determinism

"In a random order" goes through the shared `_bottom_in_random_order`, which
uses `state.rng.shuffled` and never `random`.
`tests/unit/test_determinism_hygiene.py` scans the source for the latter;
`TestTheOrderComesFromTheGameRng` pins the former from the outside, asserting
that the game's own stream advanced and that a fixed seed reproduces the order.

### What the test proves

The naive implementation silently does nothing, so "the spell resolved" is not a
test. Three claims carry it:

- **Free.** The controller has no lands and an empty mana pool, so a `{1}{G}`
  creature on the stack could not have been paid for from that board at all —
  and the `SPELL_CAST` event carries `free=1`, which is what a cast trigger and
  the log read.
- **The rest reached the bottom.** The cast card is *not* among them (bottoming
  it would drag it off the stack); a declined one *is*; the card below the
  window is untouched and still on top; and `player.exile` is empty in every
  case, which is where every alternative spelling would have stranded them.
- **The selector bounds it.** An overpriced card and a land are never offered at
  all — no decision is asked — and a castable card one deeper than `amount` was
  never looked at.

### Guarded by

`tests/unit/test_free_cast_from_window.py`,
`tests/unit/test_cascade_and_ripple.py` (the shared `_offer_free_cast` and
`_bottom_in_random_order`), `tests/unit/test_determinism_hygiene.py`, and
`tests/cards` re-running all six authoring gates over every machine-authored
card.

## Shield counters — a replacement effect that lives on a counter

### Overview

Diamond City: *"This land enters with a shield counter on it. (**If it would be
dealt damage or destroyed, remove a shield counter from it instead.**) / {T}: Add
{C}. / {T}: Move a shield counter from this land onto target creature. Activate
only if two or more creatures entered the battlefield under your control this
turn."*

The gap record (`data/authoring/gaps/diamond_city.json`) is unusual, and its
warning is the reason this was filed rather than shipped. Counter kinds are free
strings, so the worker **built the would-be answer** — a
`self_enters_with_counters` replacement naming `"shield"`, plus the
`move_counters` ability for line three — and it **passed all six gates**, with
the expectation `{"zone": "battlefield", "counters": {"kind": "shield", "amount":
1}}` satisfied exactly. No gate can see this gap: placing the counter is
genuine, showing it is genuine, moving it is genuine, and only its *meaning* is
missing. The land entered with an inert tally, died to the first removal spell it
is printed to survive, and spent a tap moving a token of nothing onto a creature.

So the unit test is the only thing that can prove the counter does anything, and
that is what `tests/unit/test_shield_counter.py` is for.

### What was missing, exactly

Three near misses, all of them checked and none of them usable:

- `enums.KEYWORD_COUNTERS` is `frozenset(k.value for k in Keyword) -
  INERT_KEYWORDS`, and "shield" is not a `Keyword`. The characteristics pipeline
  therefore applies nothing for it, and `values.validate_counter_kind` documents
  that a kind normalising onto no keyword "is somebody's charge counter" and is
  deliberately left as an inert tally.
- `zones.destroy` replaced a destruction from exactly three places — the
  `indestructible` keyword, the integer `obj.regeneration_shields`, and totem
  armor read off the Aura. None counter-driven, and none transferable.
- `prevent_damage` is refused an `objects` clause outright ("`prevent_damage`
  shields a *player* and takes no objects"), so it cannot cover a permanent at
  all.

The `regenerate` op is the nearest miss and is wrong four ways: it does not touch
damage, it taps the permanent and removes its damage (701.15a) where a shield
counter does neither, its shields are wiped at cleanup, and they live in an
integer field rather than in `obj.counters` — so `move_counters` could not carry
one onto the target creature, which is the third line of the card.

### The shape

**No new op, no new keyword, no new `EventType`, no new `DecisionKind`, no API
field.** The DSL already had every word Diamond City needs. What it needed is
that two existing code paths read the counter.

Two shipped paths were the right precedents, and this is exactly those two keyed
on a counter kind instead of on a field or a keyword:

| | |
|---|---|
| `obj.regeneration_shields` | a spent-once replacement of a **destruction** |
| absorb / `prevented_damage` | a per-permanent prevention of **damage** |

`objects.SHIELD` names the kind, so the two hooks and the loader's guard cannot
drift; `primitives.spend_shield_counter` is the single consumer, because the rule
is *one counter per event* whatever the event was, and written twice the two
sites would disagree about the one thing the card is bought for. It removes the
counter and says so, and nothing else — what replaced what is the caller's
sentence, since prevented damage is a `DAMAGE_PREVENTED` the trigger bus already
carries and a replaced destruction is a log line beside `regenerated` and
`totem_armor`.

**It lives on the counter rather than on the card**, which is load-bearing rather
than tidy: Diamond City's third ability moves the shield onto a creature the land
never mentions, and it has to go on working there.

### The four properties, and the boundary each one is

```
it replaces damage AND destruction   one counter per event, not per point
a replacement, not a reduction       5 damage costs one counter, marks nothing
not indestructible                   with no counters left, it dies
not regeneration                     no tap, no un-combat, damage stays marked
```

The last row has a visible consequence. Because the marked damage stays, a
shielded creature standing in lethal damage is destroyed, replaced, and then
checked **again** (704.3) — so it sheds one counter per state-based-action check
until it has none. Regeneration and totem armor both remove the damage and stop
after one; the shield counter does not, and that asymmetry is printed. It also
took the one line outside the two hooks: `sba._creature_deaths` reports `changed`
when a counter was spent, because `destroy` returning False was previously the
only way it knew the board had not moved. Without it the loop stops after one
counter and the creature survives on the rest until somebody next gets priority.

### Two orderings, neither of which shows on a board

**`indestructible` is checked first and spends nothing.** It is not a replacement
that consumes anything — the destruction simply never happens — so a permanent
that survives on it keeps its counter, exactly as it keeps its regeneration
shield.

**The counter goes after absorb and before a regeneration shield.** Both pairs
are two replacements of one event, which 616.1 hands to the affected player and
the engine does not model. Both orderings are the choice its controller would
make: after absorb, the counter is spent only on damage that would otherwise
land, so a 2-damage ping into "prevent the next 3" leaves it alone; before
regeneration, it is the cheaper of the two ways to survive, costing no tap, no
removal from combat and no damage.

On the damage side it also has to sit **before** the planeswalker and wither
branches, because each of those is a different *place to put* the damage rather
than a reason it was not dealt — a shielded planeswalker must not lose loyalty
and a shielded creature must not take -1/-1 counters from a withering source.

### What it does not stop

**Sacrifice** (701.16b) and **0 toughness** both go through, and that is the
absence of a rule rather than an extra one: neither destroys, so neither reaches
`zones.destroy`. Regeneration and totem armor fail against both for the same
reason.

### The guard

`values.validate_counter_kind` grew a second near-miss branch beside the keyword
one, so `"Shield"`, `"shield counter"` and `"shield counters"` are refused at
load while `"shielding"` and `"charge"` stay free. Every path already routed
through it — `_validate_effect`'s single `counter` check covers `add_counters`,
`remove_counters` and `move_counters`, and the replacement validator checks
`self_enters_with_counters` explicitly — so the guard reaches the card without a
new call site.

It matters more here than for a keyword counter, and the reason is the gap
record's warning again: a mis-spelled shield counter is **visible on the board**.
It is placed, shown, moved by `move_counters` and added to by `proliferate` — and
the permanent still dies.

### Files

- `src/automtg/engine/objects.py` — `SHIELD`, beside `PLUS_ONE` and `MINUS_ONE`
- `src/automtg/engine/primitives.py` — `spend_shield_counter`, and the damage hook
- `src/automtg/engine/zones.py` — the destruction hook, second in the ladder
- `src/automtg/engine/sba.py` — the state-based-action loop keeps going
- `src/automtg/engine/effects/values.py` — the near-miss guard
- `tests/unit/test_shield_counter.py` — 36 tests

Diamond City itself is not in `data/` — the prototype lives in the test file, as
`TestDiamondCity`, because the point is the engine: that exact card definition
loaded and passed every gate before this change, and the land still died.

## `demonstrate` — a copy that belongs to somebody else

### Overview

Excavation Technique: *"Demonstrate (When you cast this spell, you may copy it.
If you do, **choose an opponent to also copy it.** Players may choose new targets
for their copies.)"* — and Silverquill Lecturer, which grants it to your creature
spells.

The first half was already there: `copy_spell` has copied a spell on the stack
since storm. The second half was unsayable in two separate ways, and both gap
records (`data/authoring/gaps/excavation_technique.json`,
`silverquill_lecturer.json`) found the same two independently.

`op_copy_spell` read only `sid`, `amount` and `new_targets`, and ended
`put_copy_on_stack(state, ctx.controller, original, chosen)`. The controller was
an argument that only ever got one value, so **every copy the engine could make
was yours** — and since `_validate_effect` has no effect-key whitelist, a card
written with `"controller": "opponent"` on the op loaded clean, was ignored, and
played as a card with no downside. `for_each_player` is not a way round it: it
binds `each_player` and never reassigns `ctx.controller`.

And nothing could name **one** opponent. `select_players` resolves `"opponent"`
and `"each_opponent"` to the whole set; `target`, `controller_of_target`,
`controller_of` and `owner_of` each read something a target or a trigger already
produced, and demonstrate's copy is explicitly untargeted. At a pod
`"each_opponent"` gives a copy to *every* opponent, which is a different card.

Dropping the opponent's copy would not have been a smaller version of either
card. It is the half that balances the keyword: without it the Lecturer is a
one-sided Cackling Counterpart engine and Excavation Technique is unconditional
removal with no rider.

### Tier: A — one key on an existing op, and one new op composing existing primitives

No new `DecisionKind`: `ask_player` and `CHOOSE_PLAYER` have existed since clash,
which asks the same question and hands back a player id, so legality's
`_choice_actions`, `game.apply` and `verify.py`'s auto-answer table all work
unchanged. What was missing was never the decision — it was somewhere to *put*
the answer. No `EventType` (`SPELL_COPIED` already carries the copy's controller
as its `player`), no continuous effect, no server and no frontend change.

### What was built

- **`engine/effects/ops_stack.py::op_copy_spell`** — a `controller` player spec,
  resolved through `select_players` and filtered to the living. It reads
  *plurally*, exactly as `copy_permanent`'s identically named key already does:
  one copy per named seat, per `amount`. Absent, it is the resolving player, so
  storm, replicate, conspire, casualty, gravestorm and epic are untouched.
- **`engine/effects/ops_stack.py::_choose_new_targets`** — takes the **copy's**
  controller as `chooser`, and uses it for `enumerate_target_tuples` as well as
  for `ask_mode`.
- **`engine/effects/ops_control.py::op_choose_player`** — asks one seat out of a
  `players` pool (default: the opponents) and records it under `as`, beside
  `choose_type` and `choose_color`, whose shape it copies.
- **`engine/effects/__init__.py::RECORDING_OPS`** — `choose_player` added, so the
  loader's `as` guard knows it writes a binding.
- **`cards/loader.py::_validate_effect`** — `copy_spell`'s `controller` is
  checked as a full player spec, and `choose_player` requires an `as` and
  validates its `players`.

### The chooser decides the legal set, not only who is asked

115.7b says "players may choose new targets for **their** copies", and reading
that as "who gets the prompt" is only half of it. "Target creature you control"
names a different pool for each seat, so a redirected copy asked from the
resolving player's side is wrong in both directions at once: it lets you aim a
copy that is not yours, at creatures its controller could never have chosen.

### "Leave it alone" had to be added to the menu

`_choose_new_targets` skipped the question when there was one legal tuple, on the
argument that the only legal choice is what the copy already targets. That
argument holds only while the copy's controller is the original's. A demonstrate
copy usually holds a tuple that is **not** legal for its new controller, so the
old test skipped the prompt in exactly the case where it decides the card — and
would then have auto-taken the one legal target, forcing an opponent to point a
spell they did not want at their own board.

The current tuple is now appended to the options when it is not already among
them, so declining stays available: a copy nobody retargets is countered on
resolution (608.2b), which is the answer an opponent gives to a copy of something
they do not want. Behaviour for a same-controller copy is unchanged, because
there the current tuple is already in the list.

### `as` is required on `choose_player` alone

Every other recording op defaults its binding name or does without one. Here the
chosen seat is unreachable except through the binding — nothing on the card can
find it otherwise — so an omitted `as` is a prompt whose answer is discarded, and
two `choose_player`s sharing a defaulted name would silently overwrite each
other on a card that chose twice.

### The granted shape, and what it is not

"Creature spells you cast have demonstrate" is written as the same cast trigger
on the Lecturer, filtered to creature spells you cast. There is **no vocabulary
for granting an ability to a spell on the stack**, and this is not a workaround
that loses something: the trigger fires on exactly the casts the grant would have
covered, and "each copy becomes a token" is 706.10's own rule rather than a
rider, since `put_copy_on_stack` backs every copy with a token object already.
A copy is put on the stack and not cast, so the grant does not re-trigger on its
own copies.

### Tests

`tests/unit/test_demonstrate.py`, with test-only cards in
`tests/data/testing.cards.json`: `t_demo_draw` (untargeted, so the draw itself
proves whose copy resolved), `t_demo_pump` ("target creature you control", which
is what makes the chooser's pool differ from mine) and `t_lecturer` (the granted
shape). It covers the pod boundary — one chosen seat out of two opponents, not
`each_opponent` — declining the `may`, declining the retarget so the copy is
countered, and `t_stormcat` as the regression that an unqualified copy is still
the resolving player's.

## `x_value` — an X the ability defines, instead of the player announcing it

### Overview

Soul Foundry: *"Imprint — When this artifact enters, you may exile a creature
card from your hand. **{X}, {T}: Create a token that's a copy of the exiled card.
X is the mana value of that card.**"*

Every X in the engine was an announcement. Rule 601.2b has the caster choose X,
`game._ask_x` raised a `CHOOSE_X` decision with a ceiling of
`mana.max_affordable_x`, and `legality` offered the line at its floor of X = 0
because the choice is the player's to make later. That is right for Fireball and
it is the whole bug for Soul Foundry: the second sentence *is* X, so the card
written as `{"mana": "{X}"}` lets the player announce zero and copy an imprinted
Griselbrand for nothing.

That version is not an approximation of the printed card, it is a strictly better
one — and it **passes all six authoring gates**, because the verifier's sandbox
never activates an activated ability. The gap record
(`data/authoring/gaps/soul_foundry.json`) exists because the gates cannot catch
this class of error, and `tests/unit/test_defined_x_cost.py` is the only thing
that does.

### Tier: A — a new field on `Cost`, no new op

No new op (`copy_permanent` already copies a card sitting in exile, because an
oid survives a zone change), no `DecisionKind` — the point of the change is that
one is no longer *asked* — no `EventType`, no continuous effect, no server and no
frontend change.

### What was built

- **`cards/schema.py::CostModel.x_value` / `engine/carddef.py::Cost.x_value`** —
  a value expression evaluated at activation time, `None` for "X is announced".
- **`engine/costs.py::defined_x`** — evaluates it (clamped at zero) and returns
  `None` when the cost does not define X.
- **`engine/costs.py::ability_mana`** — reads it and *overrides* the `x` its
  caller passed. This is the whole design: `can_pay` and `pay` both price an
  ability's mana through this one function, so the X legality tests is the X the
  payment charges, with no second place to keep them in step.
- **`engine/game.py::_ask_x`** — returns the defined number instead of asking.
- **`engine/legality.py::_ability_aims`** — skips the "is there **any**
  affordable X" gate when the ability defines its own, and lets `can_pay` price
  it. So the row is absent from the action list until the mana is really there.
- **`engine/effects/values.py::_characteristic`** — an `{"objects": selector}`
  form beside `target`, `binding`, `var` and `self`, summed over the pool the
  same way the `target` form is.
- **`cards/loader.py`** — `x_value` is refused on every cost node that is not an
  activated ability's, and beside a `mana` with no `{X}` to fill in.

### Why a cost needed a value expression that reads a *pool*

The four characteristic references that existed all name an object the resolution
already has in hand — a target, a binding, a snapshot, the source itself. An
activated ability's cost has none of them: it is priced before any effect runs,
so the only way it can name a card is to go and find it. Soul Foundry's imprint
is a card in exile linked back by `exiled_by`, which the `exiled_with` selector
already reads, and `{"mana_value_of": {"objects": …}}` is that selector asked for
a number.

### Why not `times`

`times` is the only other part of a cost that is not fixed when the card is
written, and its own schema comment scopes it out: it is read where an
`EffectContext` exists to evaluate it — by `may`'s `pay`, not by an activated
ability's cost. `ManaCost.scaled` is called from exactly one place,
`ops_control.py`'s `pay` op; `engine/costs.py` never reads it. So `times` on an
activated cost is silently ignored and the ability charges its unscaled printed
mana. It also multiplies the *whole* cost rather than filling in one symbol.
`mana_reduction` only subtracts generic and clamps at zero, so it cannot raise a
`{0}` base up to a card's mana value, and `pay_life` is the one computed cost
that already existed — and it is life, not mana.

### Zero is an answer, not an absence

`x_value` is `None` for "X is announced" rather than `0`, because 0 is a
perfectly good defined X: an imprinted Ornithopter makes the ability free, and a
Soul Foundry with nothing imprinted is activatable for `{0}` and copies nothing —
an empty pool sums to zero, which is what a table would say too.

### Tests

`tests/unit/test_defined_x_cost.py`, with test-only cards in
`tests/data/defined_x.cards.json`: `t_imprint_foundry` (Soul Foundry's shape),
`t_free_thopter` (the X = 0 boundary), and `t_naive_foundry` — deliberately the
*wrong* card, the `{"mana": "{X}"}` version, asserted against so the difference
the field makes is a fact in the suite rather than a claim in a comment.

## `attachment` — attaching a permanent that is not the ability's source

### Overview

Vault 101: Birthday Party, a Saga: *"II, III — You may put an Aura or Equipment
card from your hand or graveyard onto the battlefield. **If an Equipment is put
onto the battlefield this way, you may attach it to a creature you control.**"*

Every attach the engine had ever done was a permanent attaching **itself**.
`op_attach` read `objects` as the *host* and hardcoded the mover to
`ctx.source_oid`, which is exactly right for the only two abilities that had ever
needed it: Equip and Reconfigure are printed on the Equipment, so "attach to
target creature you control" can only mean *me*, and naming the mover would have
been noise.

Here the source is the **Saga** — an Enchantment that is neither Aura nor
Equipment. Written with a plain `attach`, the engine attaches the Saga to a
creature and leaves the Equipment that just arrived lying on the battlefield
equipping nobody.

`put_onto_battlefield` was the other near miss and the reason the loader guard
exists: it carries `tapped`, `attacking` and `counters` for the arrival but has
no `attached_to`, so the Equipment cannot enter already equipped — and
`attachment` written there, which is the first place anybody will try it, would
have been accepted and ignored.

### Tier: A — a new sub-key on an existing op

Not even a new op: `attach` already existed, already took a selector, and the
only thing missing was a second one. No `DecisionKind` (both questions are
`choose_objects` over ordinary selectors), no `EventType` (`ATTACHED` already
fires from the primitive), no continuous effect, no server or frontend change.

### What was built

- **`effects/ops_board.py::op_attach`** — an optional `attachment` selector
  naming what moves. Absent, the source is the mover and nothing about Equip or
  Reconfigure changes.
- **`cards/loader.py::_validate_effect`** — `attachment` is refused on every op
  but `attach`, its selector is validated, and a `target` inside it must be one
  the card declares.

### The two things that are not obvious

**The attachment is resolved before the host, and that order carries the
conditional.** *"If an Equipment* is put onto the battlefield this way" is not a
separate `if` op: a `subtypes: ["Equipment"]` filter over a binding that holds an
*Aura* matches nothing, the pool is empty, and the op returns without asking
which creature. Resolving the host first would show the player a decision that
cannot change the game. `optional` on `objects` is then the printed "you **may**
attach it".

**The binding is what makes "it" mean one card.** `attachment` is written
`{"binding": "gear"}`, naming the `as` of the `search_zones` that just put the
card down. A fresh filter — "an Equipment you control" — is a legal reading of
the pool and the wrong reading of the card: it would also pick up the Equipment
that has been sitting there since turn three.

### The Aura half is the same op

An Aura put onto the battlefield without being cast targeted nothing, so
`stack._attach_aura` — which reads the *spell's* targets — never runs, and
`sba` bins it (704.5m). The same op with the `subtypes` filter dropped attaches
it and it survives. Which host is legal for a given Aura is the card's own
selector to state; the engine models no standing "Enchant creature" restriction
off the stack, which is now recorded in `docs/rules-coverage.md` under
**Simplified**.

### Why the test had to assert on characteristics

The gap record's own observation: this failure is invisible to all six authoring
gates. The card loads, the chapter resolves, the Equipment really is on the
battlefield, and a zone expectation sees exactly what it expected. So
`tests/unit/test_attach_another_permanent.py` asserts on `attached_to` and on
`chars(state, oid).power` — the `+2/+0` that never appears is the only evidence
there is. Run against the previous `op_attach`, ten of its eighteen tests fail;
the Equip regression test passes under both, which is the point of it.

### Tests

`tests/unit/test_attach_another_permanent.py`, with test-only cards in
`tests/data/attach_another.cards.json` (a Saga in Vault 101's exact shape, two
stand-in rites that drive the same effects at a chosen moment, an Equipment, an
Aura and a vanilla bear).

## `deals_damage_to_player` — damage to a player, combat or not

### Overview

Curiosity: *"Enchant creature / Whenever enchanted creature deals damage to an
opponent, you may draw a card."* Ophidian Eye is the same card with flash, and
Tandem Lookout is the same trigger handed to two paired creatures. Three cards,
the top entry in `docs/unsupported-cards.md`, all waiting on one trigger.

The engine could say "deals **combat** damage to a player" and nothing else.
`primitives.damage_player` fires `COMBAT_DAMAGE_TO_PLAYER` inside `if is_combat`,
so under Curiosity a pinger, a Fireball, a fight and every triggered burn spell
drew nothing at all — and the pinger is what all three cards are played with, so
the substitution is a different card rather than a weaker one.

### No new event type

`DAMAGE_DEALT` has been fired through the trigger bus by `damage_player` since
damage existed, with `to="player"` telling it apart from the permanent half.
Every route by which damage reaches a player goes through that one function, so
the event was already complete and already correct; what it had never had was a
name in `TRIGGER_EVENTS`.

This is the same shape `dealt_damage` (enrage) took over the *other* half, and
the two are now scoped by one table rather than two open-coded comparisons:

```python
EVENT_HALVES = {
    "dealt_damage": "permanent",        # enrage: the victim is the subject
    "deals_damage_to_player": "player", # Curiosity: the dealer is the subject
    "damage_prevented": "player",       # Selfless Squire
}
```

`_matches` and `_delayed_matches` both read it. The delayed matcher never had the
scoping at all, so a delayed subscription was silently wider than a hosted
trigger of the same name — it would have woken a `deals_damage_to_player` watcher
on a Shock aimed at a creature.

### The subject is the dealer, which is the whole of the Aura

`dealt_damage` takes the **victim** as its subject, because enrage is a fact
about the creature being hurt. This takes the **dealer**, because "enchanted
creature deals damage" is a fact about the creature doing the hurting — and the
subject is what `filter: {"attached": true}` and `source: "self"` are compared
against. The player half of the event carries no `oid`, so `_subject_oid` reaches
it through the `event.source` fallthrough, and a hit with no source object at all
matches nothing rather than matching everything.

Two keys joined the payload, on the player half only:

- `controller` — the dealing permanent's controller, so `controller: "you"` reads
  "a creature **you control** deals damage". Without it the `controller` clause
  falls through to `event.player`, which on a damage event is the seat that was
  **hit**: the clause would mean the opposite of itself.
- `defender` — the seat that was hit, which is what a `defending` clause compares
  against. `deals_damage_to_player` is the third entry in `DEFENDING_TRIGGERS`
  and the first that is not about combat. Two-player play hides the difference
  between "a player" and "an opponent"; a pod does not.

### The granted path, and a resolution bug it uncovered

Tandem Lookout reaches the trigger through a **static** `grant_ability`, and that
path had never carried a triggered ability before — the two shipped cards that
grant one use the one-shot op. It queued and then resolved as nothing.

`stack.ability_of` looks a granted ability up in the granter's
`grantable_abilities` and needs `granted_by` to know where to look, and
`triggers._granter_of` could only see op-granted abilities: those leave a
`TempEffect` on the recipient, while a static grant leaves nothing behind and is
recomputed from the granter's "as long as…" every time anybody asks. So
`characteristics.granted_ability_origin` answers the same question for the
continuous half, off the very list `abilities_of` builds.

It returns **both** halves of the answer, because the two lists are indexed
differently: `abilities_of` appends a granted ability to the recipient's own list
and renumbers it, so Tandem Lookout's granted trigger is number 2 on the creature
that has it and number 0 in the pool it came from. Recording the recipient's
number would resolve a different ability, or — as here — none at all, with no
error anywhere.

### Test

`tests/unit/test_deals_damage_to_player.py`: 20 tests. The noncombat half through
both the primitive and a real activated ability; combat damage firing it too;
the combat-only trigger asserted *not* to fire on a ping, so the difference
between the two events is measured rather than argued; infect (damage that costs
no life, which is why this is not `life_lost`); prevention, zero damage, damage
to a permanent and damage to yourself all firing nothing; a three-player position
where "an opponent" is the Aura controller's opponent and not the enchanted
creature's controller's; and the granted copy on both halves of a pair, plus its
wearing off when the pair breaks.

## `tapped` in a trigger filter — reading how a permanent arrived

### Overview

Charismatic Conqueror: *"Whenever an artifact or creature an opponent controls
enters **untapped**, they may tap that permanent. If they don't, you create a
1/1 white Vampire creature token with lifelink."*

The third member of the family `zone` and `any_types` already belong to, and the
same trap all three sprang. `tapped` is in `SELECTOR_KEYS`, so
`validate_selector` accepted it on a trigger filter and the card loaded clean —
and `matches_card_filter` read controller, zone, types, colors, keywords, power,
toughness and several relationships, and never looked at it.

So the clause vanished. The card printed "enters untapped", and triggered on
permanents entering tapped as well: **strictly wider than the printed line**.
Wider is the dangerous direction, and no authoring gate can see it — the card
compiles, resolves, does something, and does slightly too much of it.

### Why object state is legitimate here

This is the one clause in `matches_card_filter` answered from an object's state
rather than its printed face, which the function's own docstring warns against —
trigger subjects are frequently gone by the time it looks.

It holds because a trigger filter is asked **once, as the ability is collected**,
and `zones._enter_battlefield` writes `obj.tapped` before it fires
ENTERS_BATTLEFIELD. At match time the flag is the permanent's arrival state,
which is exactly the question. It is therefore only meaningful on an arrival: a
`dies` filter writing it reads a permanent whose state `reset_permanent_state`
has already cleared.

### Why not a trigger `condition`

The near miss, and it makes a different card. A condition reads the right state
at queue time, but 603.4 **re-checks it on resolution** — so an opponent who taps
the fresh artifact in response makes the ability do nothing.

That inverts the printed ruling exactly: Charismatic Conqueror pays you the
token precisely *because* they could not or would not tap it. Under the
condition spelling the ability resolves as skipped and makes nothing, and the
case is not a corner — it is what an opponent gets for free by tapping the
artifact for mana in response.

## `until_leaves` on `phase_out` — phasing tied to a permanent, not to a clock

### Overview

Oubliette: *"When this enchantment enters, target creature phases out **until
this enchantment leaves the battlefield**. Tap that creature as it phases in
this way."*

`phase_out` already shipped as a printed one-shot. Two things were missing, and
they fail in opposite directions — which is why neither could be skipped.

### The duration

`turn.phase_out` recorded nothing about its cause, and the untap walk phased
every phased-out permanent back in at its controller's **next** untap step,
unconditionally. Written with the plain op, Oubliette returns the creature with
the enchantment still on the battlefield.

That is the worst shape a bug can take: the card is right for a whole turn and
then quietly wrong, and nothing on the board says so. `phased_out_by` is the
fix, and `turn._phasing` skips a permanent that has one — it is waiting on a
source, not on a clock.

### Naming it again

702.26c takes a phased-out permanent *out of* `state.battlefield` — that list
membership **is** "treated as though it does not exist", and it is what makes
phasing cheap to implement, since targeting, the state-based actions, combat and
the serializer all walk that list and miss it for free.

It is also what made this card impossible: the enchantment's own
`leaves_battlefield` trigger had no way to find the creature it had sent away.
`phased_out_with` draws its candidate pool from `state.objects` instead, and is
narrow for the reason `exiled_with` is narrow — a filter matching every
phased-out permanent would hand back creatures this card never touched,
including any phasing on its own keyword.

### "As it phases in"

`tapped` is a parameter on the new `phase_in` op rather than a `tap` op run
afterwards, because "as it phases in this way" is **one event**. A separate tap
happens to a creature that has already returned untapped: a "becomes tapped"
trigger would see it, and a replacement could stop it.

### Why not exile

`until_leaves` is exactly the O-Ring shape and the temptation is to reuse the
exile machinery whole. It is the wrong zone: exiling loses counters,
attachments and continuous effects, and fires the zone-change triggers phasing
deliberately does not. `test_phase_out_until_leaves.py` re-asserts all three
across the round trip for that reason.

### Two details that show on no board

The link is **inherited** by whatever phased out attached to the victim
(702.26e) — without that the Aura comes back a turn early on its own clock,
leaving the creature phased out and naked. And it is **cleared on the way in**,
or the permanent is invisible to the untap walk forever and a second phase-out
strands it permanently.

## `replace_life_loss` — doubling a life loss, but not the damage that caused it

### Overview

Bloodletter of Aclazotz: *"If an opponent would lose life during your turn, they
lose **twice that much life instead**. (Damage causes loss of life.)"*

The gap record had it exactly right: `static_effects` held nothing that touched
life totals at all. The only replacement-shaped members of the vocabulary were
`prevent_damage` (a *reduction*, of damage only, and so blind to a drain or to
paid life) and the `replace_deaths` / `replace_leaves_battlefield` ops, which
replace zone changes for permanents rather than events on players.

The near miss is the `life_lost` **trigger**, and naming why it is wrong is most
of the argument for building anything. It fires *after* the loss has been
applied, so a `lose_life` op hung off it deals the second half as a separate,
later event: visible to every other life-loss trigger on the board as a second
drain, ordered on the stack where the printed card has no stack at all, and
re-triggering itself into a loop, since nothing in the trigger vocabulary can
tell a loss it caused from one it did not.

### The two call sites, both required

A player's life goes down in exactly two places, and they are unrelated:
`primitives.lose_life`, which every drain and every life paid as a cost reaches
(118.4 — paying life *is* losing life), and the life-loss half of
`primitives.damage_player`, which 120.3c reaches. The card prints "(Damage
causes loss of life.)" precisely because the second one is not obvious.

Wired into only one of them, the result is a card that works against Village
Rites and does nothing against a Lightning Bolt — or the reverse — and neither
half looks wrong on a board. That is the whole reason
`tests/unit/test_life_loss_replacement.py` covers both routes twice: once
against the primitive directly and once through a real cast spell.

### Only the loss is multiplied, never the damage

The property that is easiest to get wrong. Lifelink gains life equal to the
damage **dealt** (702.15b), which the replacement never touched, and the same
goes for `DAMAGE_DEALT` and the commander-damage tally. A lifelinking source
dealing 3 to a doubled opponent takes 6 life off them and gains its controller
3.

This is the separation the wither and infect keywords already make — it is still
damage, and only where the number lands changes. Doubling `amount` at the top of
`damage_player` would have been one line shorter and would pass every
life-total assertion in the suite except that one, while quietly turning every
lifelinking attacker in every game into twice the lifegain it prints.

### What is refused, and why

`loss_multiplier` is required and must be 2 or more. A multiplier of 1 replaces
a loss with an identical loss; 0 is "they lose no life", which is a *prevention*
— a different printed sentence and a much stronger card. Both would load clean
and neither is anything a card says, so both are refused at load, the same
refusal `ward` makes about ward {0} and `replace_token_creation` about an empty
`create_instead`.

### Divergences

Two doublers **multiply**: each replacement applies once (614.5), so a loss
doubled twice is quadrupled. 616.1 lets the affected player order two applicable
replacements and this engine does not ask — the same divergence
`_token_creation_plan` records, and for a product the order cannot show. There
is no replacement of life *gain*, so Rhox Faithmender and Alhammarret's Archive
stay blocked.

This is the engine's **second** named replacement hook and, like the first, it
is deliberately not the start of a rule-616 system — see
[rules-coverage.md](rules-coverage.md).

## `replace_token_creation` — rewriting a token creation before the token exists

### Overview

Academy Manufactor: *"If you would create a Clue, Food, or Treasure token,
**instead create one of each**."*
Divine Visitation: *"If one or more creature tokens would be created under your
control, **that many 4/4 white Angel creature tokens with flying and vigilance
are created instead**."*

Both gap records landed on the same wall. `ReplacementModel.event` is a closed
`Literal` of three enters-the-battlefield forms, every one of which modifies a
permanent that is *already arriving*; and `primitives.create_token` took a fixed
`def_id`, put the token straight onto the battlefield, and fired `TOKEN_CREATED`
afterwards — so there was no moment at which the pending creation could be seen,
let alone altered.

The near miss is a `token_created` trigger, and naming why it is wrong is most of
the argument for building anything: it adds tokens **alongside** rather than
instead, so the 1/1 Soldiers still exist and the Angels are extra — a strictly
stronger card than the printed one; it uses the stack, so the extra tokens arrive
later and can be responded to, which changes every "whenever one or more tokens
enter" count on the board; and a Manufactor written that way re-triggers on the
Treasure it just made, with nothing in the trigger vocabulary able to tell a
token it made from one it did not.

### Tier: B — a new continuous effect

A static (`STATIC_EFFECTS`, a `condition` gate, a battlefield reader), not a new
op, decision or event. It is the only tier that fits: the sentence is a standing
fact about a player's board that is true again every time a token would be made,
and there is nothing for a one-shot to be spent on. No layer, though — a token
that does not exist yet has no characteristics to compute — so the reader lives
beside the player-wide statics rather than in `_compute`, and the one consumer is
`primitives.create_token`.

### What was built

- **`primitives._token_creation_plan`** — the whole mechanism. Returns what the
  creation actually creates, or `None` for "nothing applied", which is every
  token creation in a game where neither card is out.
- **`characteristics.token_creation_replacements` / `printed_token_matches`** —
  which statics are switched on and whose, and whether a token definition matches
  a printed-face filter. The second is `_matches_printed` and only
  `_matches_printed`, so the filter language cannot drift into a second spelling.
- **`AbilityModel.affects_token` / `create_instead`**, `TOKEN_FILTER_KEYS`, and
  the loader guards — including `validate_token_references` now checking
  `create_instead` ids, so a missing or non-token id fails at load rather than
  three turns into a game.

**One field for two shapes.** The two sentences read as different mechanisms — a
substitution *set* keyed on what was about to be made, and a substitution of
identity that preserves a count — and they are one: *each token that would have
been created becomes one of each id in `create_instead`*. Manufactor lists three
ids, so one Treasure becomes three tokens and two Treasures become two of each;
Divine Visitation lists one, so N Soldiers become N Angels and "that many" is
preserved without a count ever being written down.

### The rules it turns on

- **614.5 — a replacement applies at most once to a given event.** One pass over
  a fixed list of statics. This is not a nicety: the Angels a Divine Visitation
  creates are creature tokens under your control, so an implementation that
  re-read its own output would hang rather than play slowly. It is also what
  fixes the numbers when there are two of something — two Divine Visitations
  still make N Angels, and two Academy Manufactors turn one Treasure into
  **three of each**, which is the printed ruling.
- **The replacement is the token's controller's**, because both cards say "you" —
  not the controller of whatever effect is creating the token. A Manufactor's
  controller handing an opponent a Treasure hands them one Treasure.
- **Only the identity is replaced.** `tapped` and `attacking` survive onto the
  substitute (the printed Divine Visitation ruling); embalm-style `overrides` do
  not, because they describe the token that was replaced and never made.
- **Manufactor + Divine Visitation** has a defined answer and it is that they
  never feed each other: a Manufactor makes three *noncreature artifacts*, which
  "creature tokens" never names, and a Visitation makes an Angel, which is no
  kind of Clue, Food or Treasure. So the one divergence below cannot bite here.

### Deliberately not built

Not rule 616. There is no event object, no "replaced by" chain, and nothing
outside `create_token` consults a replacement — 616.1's "the affected player
chooses which applicable replacement to apply first" is answered by battlefield
order instead of by asking, which is invisible for the pair above and is recorded
in `docs/rules-coverage.md`. There is no count *multiplier* either, so Doubling
Season, Parallel Lives, Anointed Procession and Ojer Taq remain blocked; that is
a second capability, not a second key in a card file. A fourth entry on the
enters-the-battlefield whitelist is still engine work.

### Tests

`tests/unit/test_token_creation_replacement.py` — 29 tests in six classes, one
per claim: what is created instead, 614.5's once-per-event (including both
two-copy numbers), whose replacement it is, the Manufactor/Visitation
interaction and its order-independence, what the creating effect still says, and
when it stops applying (source leaves, `condition` false). Plus the loader's
refusals, since a card that loads clean and replaces nothing is the failure the
validation pass exists to stop. Both cards are compiled through `compile_card`
inside the test rather than added to `data/cards/`.

## `return_spell_to_hand` — taking a spell off the stack without countering it

### Overview

Reprieve: *"**Return target spell to its owner's hand.** Draw a card."*

Rule 701.5a makes **countering** one specific action, and the whole of this
capability is that returning a spell is not it. Three things are true of a
counter and of nothing else — "this spell can't be countered" stops it, the card
lands in its owner's *graveyard*, and it is what "whenever a spell is countered"
watches — and Reprieve has none of them. It answers Carnage Tyrant, it puts the
card in a hand, and nothing hears about a countering that did not happen.

### Tier: A — a new op composing existing primitives

No new decision, event, continuous effect or API field. `counter` already proved
an op can consume a `kind: "spell"` target via `ctx.target_sids`, and
`zones.move_object` already moves a card off the stack; the op is the two of them
with the destination changed.

### Why neither near miss would do

- **`counter` with a destination key.** Its destination is hardwired to the
  graveyard, it refuses `uncounterable` spells, and it emits `SPELL_COUNTERED`.
  Adding a key would leave the other two, and they are observable: the card
  would decline to answer an uncounterable spell, and it would set off triggers
  the printed card never sets off.
- **`return_to_hand`.** It reaches the right zone but cannot *see* a spell. A
  `kind: "spell"` target is a `TargetRef.stack(sid)`, and `resolve_pool`'s
  `{"target": …}` branch keeps only `kind == "object"` refs — so the pool comes
  back empty and the op is a **silent no-op**. A card written that way passes
  all six authoring gates with the targeted spell resolving onto the battlefield
  untouched, which is the exact quiet wrong-card failure the gap record existed
  to prevent. Teaching `resolve_pool` to yield stack refs was rejected for the
  same reason: it would silently let `destroy` and `exile` be aimed at a spell.
- **`objects: {"zone": "stack"}`.** It does move the spell, and it is a
  different card: untargeted, so it sweeps the whole stack, and ward, hexproof
  and "can't be the target of spells" all stop applying to a line that prints
  the word "target".

### `stack.pull_spell_off_stack` — the counterpart of `push_spell`

The op is three lines because the rules live in one helper in `stack.py`, beside
the function that puts a spell there in the first place. It unlinks the object
from the stack item, forgets the face the spell was cast as, and then:

- an ordinary spell's card moves to `to_zone` in its **owner's** hand — 400.7,
  not its controller's, so a spell cast by someone who does not own it goes
  home;
- a **copy** of a spell is not a card (706.10). There is nothing to put in a
  hand, so 704.5e removes it and it ceases to exist. Routing it to a hand first
  and letting the token state-based action clean it up would be observably
  wrong in the log — a card arriving in a hand its owner never had — and the
  token SBA deliberately exempts the stack, so it would never have seen it.

`to_zone` is a parameter rather than a constant because *where the card goes* is
the only thing that varies between the effects that do this; everything above it
is the same however far it travels.

A missing sid returns `None` rather than raising: targets are re-checked on
resolution (608.2b), and a spell that has already left is simply not there. Two
Reprieves at one spell is the natural case — the second to resolve returns it,
the first fizzles, and 608.2b takes its "Draw a card" with it.

### The loader guard

`return_spell_to_hand` insists its `target` is declared `kind: "spell"`, and
refuses an `objects` key outright. Both are the shapes of the silent failure
above: aimed at a permanent target the op returns nothing, and `objects` is what
`return_to_hand` takes, so it is the copy-paste mistake.

### What it unblocks

`data/authoring/gaps/reprieve.json`. Reprieve is now expressible in the DSL; no
importer template was added, so the card is harvested by the next agent-tier
`/author-cards` run rather than by `--tier templates`.

### Tests

`tests/unit/test_return_spell_to_hand.py`. Every behavioural test asserts on
where the **other** spell ended up rather than on Reprieve having resolved,
because the failure being guarded against is one where Reprieve resolves
perfectly and nothing happens. Verified by stubbing the op out to a no-op: the
first test fails on `count_on_battlefield(game, "t_bear") == 0`.

## `untap_permanents` — the untap twin of `tap_permanents`

### Overview

Halo Fountain, all three of its lines: *"{W}, {T}, **Untap a tapped creature you
control**: Create a 1/1 green and white Citizen creature token."* / *"{W}{W},
{T}, **Untap two tapped creatures you control**: Draw a card."* /
*"{W}{W}{W}{W}{W}, {T}, **Untap fifteen tapped creatures you control**: You win
the game."*

`cost_keys` had `untap`, and it is the `{Q}` symbol: a bare bool that
`costs.can_pay` and `costs.pay` resolve against `source_oid` alone. It cannot
reach another object, cannot carry a selector, and cannot carry a count. On this
card it is also the **wrong permanent twice over**, which is the part worth
saying out loud: the printed cost taps the Fountain *and* untaps other
creatures, so `"tap": true, "untap": true` on one cost taps the Fountain,
untaps the Fountain, and touches no creature at all. It loads, it plays, and it
is free.

The other near miss is worse. Paying with the effect-side `untap` **op** moves
the payment to resolution, so the ability becomes activatable with nothing
tapped anywhere — and the third line of this card is *"you win the game"*. Halo
Fountain is a combo engine whose only constraint is that the board must be bent
before it can be unbent; an approximation that drops the constraint is not a
lossy version of the card, it is a five-mana "I win".

`CostModel` is `extra="forbid"`, so inventing the key was a load error rather
than a silent no-op — the gap record's own verification, and the reason this
arrived as a gap instead of as a broken card.

### Tier: A — a new cost composing existing primitives

The cost analogue of a new op. `untap_permanent` already exists in
`primitives.py` and already fires `UNTAPPED`, `resolve_pool` already answers the
selector, and `ask_objects` already asks which ones. No new decision kind, no
new event, no continuous effect, no API field — `Cost.describe()` is a string
and `LegalActionDTO.kind` is a bare string, so nothing in `server/` or
`frontend/` changed.

`legality.py` needed nothing either, and that is a finding rather than an
omission: `tap_permanents` has no legality code of its own. Activation legality
runs through `legality._ability_aims`'s single `can_pay`, so the pool check
placed there gates the ability for free — which is the requirement the gap
record cared most about.

### The mirror is exact, and the one place it is not

`_untap_cost_pool` is `_tap_cost_pool` with the sign flipped, deliberately line
for line:

- **`tapped: True` is forced**, exactly as its twin forces `tapped: False`, and
  a card that spells `tapped` itself is refused at load rather than overridden
  in silence. Same argument, same consequence: "tapped" is in every printed line
  of this shape, and a cost that could untap an already-untapped creature costs
  nothing.
- **The permanents stay.** Not sacrificed, not bounced — which is what makes a
  cost of this shape repeatable, and on this card what makes vigilance and any
  untapper a combo piece.
- **Summoning sickness does not apply**, per rule 302.6: that rule restricts the
  `{T}` symbol in a permanent's *own* cost, and this reaches other permanents.
  Here it is load-bearing rather than incidental — the first line makes a
  Citizen, and a Citizen that arrived tapped is fodder for the second.
- **Charged at activation**, before the ability resolves, unrescindable. The
  whole point.

The one asymmetry is `total_power`. Crew rides on `tap_permanents` because
"total power 3 or greater" is a printed sum; nothing printed unbends a board by
power, so `total_power` on this key is a `DslError` rather than a silently
ignored knob — which would otherwise quietly read as "untap one".

### What it unblocks

Halo Fountain, completely. It was waiting on two capabilities and `win_game`
landed first, so with this the card's cost half and effect half are both
expressible: `create_token` with `citizen_1_1_gw`, `draw`, and `win_game` were
all already there.

### Tests

`tests/unit/test_untap_permanents_cost.py`. The boundary in both directions
(one short refuses, exactly the count pays), the pool's forced `tapped: True`
(an untapped board does not pay, a half-tapped board counts only the tapped
half), the selector and `controller` narrowing, summoning sickness, that the
source ends **tapped** while the creatures end **untapped** on one activation,
that it takes exactly the count and leaves the rest, that the ability is not
offered when the board cannot pay, and that it wears off — activated once, the
Bears are standing up and it is not offered again. Plus the four load-time
guards.

---

## `attacking` names a player — "a token that's attacking **that player**"

### Overview

Ainok Strike Leader: *"Whenever you attack with this creature and/or your
commander, **for each opponent**, create a 1/1 red Goblin creature token that's
tapped and **attacking that player**."* Combat Calligrapher: *"Whenever a player
attacks one of your opponents, that attacking player creates a tapped 2/1 white
and black Inkling creature token with flying that's **attacking that
opponent**."*

Two gap records, filed independently, with the same diagnosis: `attacking` was a
bare boolean, resolved by `ops_board._attack_target` as
`combat.attackers.get(ctx.source_oid)` — the one player the *source* is already
attacking. That is exactly right for the mobilize-shaped cards it was written
for, and silently wrong for both of these:

- Inside `for_each_player` the boolean has no idea the loop moved. At a pod all
  three of Ainok's tokens would be declared against the single seat the Ainok
  itself is swinging at, so "for each opponent" would degenerate into "three
  tokens at one player" — a different and better card.
- Combat Calligrapher never attacks. Its trigger fires off somebody else's
  declaration, so the lookup returns `None` and the token arrives tapped and
  attacking **nobody**, dropping the whole clause while still looking
  implemented.

There was no lossy approximation to refuse, because there was no way to write
the sentence at all: `primitives.create_token` has always taken
`attacking: int | None`, and there was simply no key on the op to pass a player
through.

### Tier: A — one key widened, no new op

`attacking` now also takes a **player spec**, resolved through
`select_players` like every other one, so the loop's `each_player`, a trigger's
`defender`, `controller_of` and a target all work with no new vocabulary. The
boolean spelling is untouched: every shipped card uses it, and `docs/card-dsl.md`
documents its contract.

No new decision kind, event, continuous effect or API field. `copy_permanent`
and `put_onto_battlefield` take the same key through the same helper and were
widened with it.

### What had to be refused

A creature attacks exactly one player, so a spec naming several has no answer
and picking one would ship a card that reads like a pod sweep and hits one seat.
The plural **names** are a load error — `"opponent"` and `"each_opponent"`
included, because a pod is what makes them plural and a two-player game hides it
— and the one shape load time cannot see, a target that chose two players,
raises when it resolves. A bare seat number is refused as well: no printed card
names a seat, and `0` is indistinguishable from `false`.

Naming **nobody** is not an error. An unbound binding or a player who has left
is the boolean's own "there is nobody to join", and the permanent simply arrives
(tapped, if asked).

### The half that was not in either gap record

Being attacked is what makes a player a defending player, and `finish_attackers`
fills `pending_blockers` from the *declaration*. Ainok's third opponent — a seat
nobody declared against — would have been attacked by a creature it was never
asked to block (509.1). `_offer_blocks_to` inserts that seat into the queue in
turn order, and only **before** the declare blockers step, which is the window
every card that says this resolves in: attack triggers go on the stack during
the declare attackers step. Once the step is walking its queue, `game.apply`
pops the head as each declaration is answered, so writing into it would ask the
wrong seat; and a permanent that arrives attacking after blocks are declared is
simply unblocked. That is 509.1 read the other way, and it is what stops this
from becoming a second block declaration.

508.4 is unchanged and asserted: a permanent put onto the battlefield attacking
was never *declared* an attacker, so it triggers nothing that fires on
attacking — which is the real rule and also what keeps "whenever this attacks,
make a token that is attacking" finite.

### Evidence

`tests/unit/test_token_attacking_player.py` — 30 tests. Both printed sentences
run as real cards (`t_pod_marshal`, `t_ink_scribe`) through a four-player
combat: one token per opponent, each at its own seat; the Marshal makes them
while staying home; the Scribe points its token at a defender while attacking
nothing; every newly attacked seat is asked to declare blockers; and the damage
lands on the seats that were named.

## `win_game` — the first op that reaches a game result

### Overview

Halo Fountain: *"{W}{W}{W}{W}{W}, {T}, Untap fifteen tapped creatures you
control: **You win the game.**"* Luck Bobblehead: *"…If you rolled 6 exactly
seven times, **you win the game.**"*

Two gap records, one sentence, and the same diagnosis in both: `sba.py` is the
only writer of `state.winners`, and it derives them from who is still `alive()`
after state-based actions. Winning was a *consequence* of everybody else dying,
and there was no entry point for a card that declares a winner while both seats
sit at 40 life.

Unusually for a gap, there was no approximation to refuse. `damage` and
`lose_life` reach a game over through the life total — preventable, replaceable,
and nowhere near 40 points from one activation of a Fountain — and `add_poison`
is the same route with a different track. `set_flag` writes a boolean that only a
`has_flag` condition reads and changes nothing about the outcome. So the third
line of Halo Fountain had no expressible version at all, not merely a lossy one.

### Tier: A, and the whole design is one question

A new op composing existing primitives. No decision, no continuous effect, no
event, no API field — `GAME_OVER` already existed and the frontend already
narrates it.

The only real question is **where the result is written**, and the answer is
"not here". `Game.over`, `Game.winners`, `state.result`, the `GAME_OVER` event
and both serializers in `serialize.py` all read what `check_game_over` wrote. An
op that assigned `state.winners` itself would produce a game that was over, with
a winner, and:

- no `PLAYER_LOST` event for the seat that lost, so the log would never say how
  the game ended;
- that seat's permanents still on the battlefield, still counted by every
  selector;
- `priority_idx` still pointing at somebody, and a `pending_decision` still
  hanging off a game nobody can act in.

All three serialize perfectly and replay perfectly. They are just wrong.

### The shape: 104.2a, which the pod already had

`sba.declare_win(state, pid)` eliminates every **other** player — the same
`_eliminate` a lethal life total reaches — and then calls `check_game_over`,
which finds one seat alive and concludes for itself. That is rule 104.2a, *"a
player still in the game wins the game if that player's opponents have all left
the game"*, and it is why the multiplayer case needs no second branch: at four
players the sentence removes three seats rather than one, which is the shape the
rule was already written in. In a duel it is the same statement read the other
way round — the player who wins is the other one losing.

Two no-ops, both deliberate:

- **A game already over is not re-decided.** Two simultaneous wins leave the
  first one standing rather than eliminating everybody and ending in a draw.
- **A player who has already left cannot win.** There is nobody to eliminate on
  their behalf, and doing it anyway would empty the table — `check_game_over`
  finding nobody alive calls that a `draw`, which is a *worse* answer than
  ignoring the sentence.

### `opponent_won` is its own `LossReason`

The argument `poison` made, one rung further out: a seat eliminated at 40 life
did not run out of life, did not deck itself and did not concede, and
`labels.ts` prints the reason to that player. The frontend needed no change —
`lossReason` falls back to the raw string with underscores stripped, so the new
value reads "opponent won" until somebody writes a nicer phrase for it.

### The loader guard, which is the one that matters

`{"op": "win_game", "condition": …}` is a load error. A top-level `condition` is
read by `if` and by `may` and by nobody else, so written on this op it would be
accepted, ignored, and the card would win the game every time it resolved.

That is not a hypothetical mis-authoring: it is the *first* way anybody will try
to write Luck Bobblehead's line, because the condition is where the card's entire
cost lives. Of all the silent misreads the load-time checks exist to catch, this
is the most expensive one available, and the fix the error points at is one more
line of JSON.

### What was deliberately left out

- **No `lose_game` op.** Losing is the mechanism here rather than a second op —
  "you win the game" *is* every opponent losing — so the engine half already
  exists and registering the op is two lines whenever a card wants it. Door to
  Nothingness and Demonic Pact are the family; neither is in the pool, and a
  vocabulary item with no card behind it is the thing these checks exist to keep
  out.
- **No "can't win the game" / "can't lose the game."** Platinum Angel and Abyssal
  Persecutor are a continuous prohibition over this whole subsystem, not a clause
  of this op.
- **The pod's real ending.** By 800.4 a player who wins a multiplayer game leaves
  it and the survivors play on; here the game ends for everybody. Recorded in
  `docs/rules-coverage.md`.

### Test

`tests/unit/test_win_game.py`. The claim under test is not "the game ends" but
*how* — that the result and the board still agree afterwards. Twenty-five cases
across five claims: the win happens without a point of life moving; it goes
through `check_game_over` (the `PLAYER_LOST`, the swept permanents, cleared
priority, exactly one `GAME_OVER`, the serialized view, no legal actions); it is
not re-decided by a later state-based pass or a second win; the pod boundary,
where three players is two eliminations; and the loader guard, including the
`if`-wrapped shape the error message points at.

### What it unblocks

Halo Fountain's third line and Luck Bobblehead's, plus the alternate-win family
waiting on the same subsystem: Thassa's Oracle, Approach of the Second Sun,
Laboratory Maniac, Coalition Victory, Test of Endurance, Felidar Sovereign,
Mechanized Production. Both witness cards need a second capability each — an
`untap_permanents` cost and a dice-rolling op — so neither is authored by this
change alone.

---

## `abilities_of` — what a permanent actually has

### Overview

Imprisoned in the Moon: *"Enchant creature, land, or planeswalker. Enchanted
permanent is a colorless land with "{T}: Add {C}" and loses all other card types
and abilities."*

One printed sentence, four continuous effects, four layers. `set_types` already
said "is a land … and loses all other card types". The other three are new, and
one of them needed a subsystem the engine had never had.

### The subsystem: nothing could take an ability away

Every effect on abilities up to now *added* one — `grant_keyword`, the
`grant_ability` op, keyword counters. So nothing had ever needed to ask what
abilities a permanent **has**: five readers each walked
`state.card_of(obj).abilities` and got the printed list.

| reader | what it would otherwise miss |
|---|---|
| `legality._activate_actions` | an imprisoned Sol Ring still offered its `{T}` |
| `costs.mana_sources` | …and still tapped for two by the payment solver |
| `triggers.collect` | an imprisoned Bloodghast still seeing landfall |
| `characteristics._battlefield_statics` | an imprisoned anthem still pumping |
| `game._activate` | indexing a different list from the one legality offered |

With a printed list, each of those is a separate place for the clause to be
forgotten, and forgetting it in any one is the worst failure this codebase has a
name for: a permanent that visibly does nothing and quietly still does
something. The last row is worse than the others — legality offering from one
list while resolution indexes another is not a missing effect, it is the wrong
ability resolving.

`characteristics.abilities_of` is the one function that answers the question and
all five ask it. Off the battlefield it returns the printed list unchanged, which
is every card in hand, on the stack and in a graveyard, so nothing outside the
battlefield changed at all.

### Indices had to stay meaningful

`Action.ability_index`, `StackItem.ability_index` and the RL action space all
address an ability by **position**. So a granted ability is *appended* — printed
indices never move — and the list is renumbered so `Ability.index` agrees with
where it now sits. Legality and resolution both read this list, so the two cannot
disagree about what index 0 means, and no trained checkpoint is invalidated.

### The line `grant_ability` stops at

`grantable_abilities` used to refuse anything but a triggered ability, and the
comment said why: a granted activated one "would need `Action` to carry where it
came from before legality could offer it — so it would be accepted here and then
never appear". `abilities_of` answers exactly that objection, so the refusal is
narrowed to precisely the width that is still true: **a granted activated ability
must be a mana ability.**

605.3a is what makes that safe. A mana ability never uses the stack, so
`stack.ability_of` — which resolves an ability off its source's *printed* list,
and must, because an ability on the stack outlives its source (608.2) — is never
asked about one. A granted activated ability that *did* use the stack would reach
it with an index into a list that no longer exists and resolve as some other
ability of that permanent. A granted static is still refused outright.

### Two orderings, neither visible on a board

**A keyword is an ability** (113.1a), so losing them all takes the printed
keywords with it — an imprisoned Sheoldred that kept deathtouch would be the
clearest possible half-implementation. The removal runs **before** the grant
layers, which is 613.1b: what is added afterwards survives it, so a Levitation
played later still grants flying and a vigilance counter (613.1f) still gives
vigilance.

**The ability statics are collected off printed faces**, apart from every other
static, in `_ability_statics`. They have to be: `_battlefield_statics` reads
`abilities_of`, and `abilities_of` reads these, so gathering both the same way is
an infinite regress. The cost is one recorded divergence from 613.8's dependency
analysis — which is the thing layers-lite exists not to have — and it is narrow:
an Imprisoned in the Moon enchanting *another* Imprisoned in the Moon does not
switch the second one off.

### `set_colors`

Nothing in the engine could set a colour. `animate` overwrote them, as a side
effect of an until-end-of-turn P/T replacement, and that was the whole of it.

It is load-bearing the moment it exists rather than a cosmetic field: the
selector language reads `colors`, `not_colors` and `shares_a_color_with`, and
`protection` reads `from_colors`. A moon-imprisoned Sheoldred stops being a legal
target for "destroy target black permanent" and stops answering a
`shares_a_color_with` fetch.

`[]` is colourless and is the *point* of the effect, so the loader checks for the
field being absent rather than empty — a `set_colors` that said nothing would
silently repaint everything it touched.

### `set_types` learned 205.1b

The subtypes of a card type a permanent no longer has go with it (613.1d).
Without that, an imprisoned Goblin Warchief reads "Land — Goblin", is still
pumped by a Goblin anthem and still answers a Goblin fetch — visibly a land and
secretly still a Goblin. That was a pre-existing shortfall in `set_types` rather
than something this card introduced; Arixmethes had it too.

`SUBTYPE_CLASS` in `engine/enums.py` is the table, derived from
`data/catalog/cards.sqlite` over every printed type line whose left half names
exactly one card type — Kindred faces excluded, since "Tribal Instant — Goblin"
would file Goblin under Instant. That derivation is reproduced as a test, so a
catalog refresh that adds a land or artifact type says so rather than silently
stripping it.

**Creature types are deliberately absent.** There are 321 of them against 149 of
everything else, the list grows with every set, and the default has to fail in
the safe direction: an unknown subtype read as a creature type is dropped when
Creature is, which is right for every new creature type and wrong only for a new
artifact or enchantment type on a permanent that stopped being a creature it
never was.

### Test

`tests/unit/test_lose_all_abilities.py` — one claim per reader, both orderings,
the loader refusals, and the catalog derivation of `SUBTYPE_CLASS`.

The card's own expectation is the weak `{"zone": "battlefield"}` fallback on
purpose: the expectation vocabulary describes *your* board by counting, and every
one of this card's effects is a characteristic of a permanent it does not count.
Gate 5 cannot witness this card, and the unit test is what does.

## `no_regeneration` — a clause three shipped cards were dropping

### Overview

Pongify: *"Destroy target creature. **It can't be regenerated.** Its controller
creates a 3/3 green Ape creature token."*

`op_destroy` read one key — `objects` — and called `zones.destroy`, which spends
a regeneration shield unconditionally. So the second sentence had nowhere to be
written, and every card in the pool that printed it shipped without it:

| card | printed | shipped as |
|---|---|---|
| Terminate | "Destroy target creature. It can't be regenerated." | Doom Blade with two colours |
| Wrath of God | "Destroy all creatures. They can't be regenerated." | a wrath every regenerator survives |
| Rapid Hybridization | "Destroy target creature. It can't be regenerated. …" | the same, plus a Frog Lizard |

Nothing announced it. The clause is not an ability, so the residual gate has no
`text` to attribute and no printed line went unclaimed — which is why the gap
record filed against Pongify is what surfaced it rather than the gates. It is
also the exact failure mode the pipeline's "do not approximate" rule exists to
prevent, arriving through the one door that predates the pipeline.

### The shape

```jsonc
{"op": "destroy", "objects": {"target": "t1"}, "no_regeneration": true}
```

`zones.destroy` grows a `no_regeneration` keyword argument and one word in one
condition:

```python
if obj.regeneration_shields > 0 and not no_regeneration:
```

### The three things it deliberately does not do

Each is a card that would read wrong otherwise, and all three come from 701.15c
saying the shield is not **applied** rather than saying it is removed.

- **The shield is not spent.** A creature that survives on indestructible still
  has it afterwards.
- **Indestructible still wins.** A different replacement, checked first, and
  Terminate has never beaten it.
- **Totem armor still applies**, for the same reason.

### A parameter, not a mark

The gap record proposed marking the victim unregeneratable for the turn, on the
grounds that one mark covers both printed readings — "it can't be regenerated"
and "a creature dealt damage this way can't be regenerated this turn".

It covers them at the price of being wrong about the first. "It can't be
regenerated" belongs to *this* destruction: an indestructible creature Terminated
is not destroyed at all, and a turn-long mark would leave it unregeneratable for
the rest of the turn — a rule the card does not print, and one a player would
discover only by losing a creature to it.

So the flag is a parameter on the destruction. The turn-long form is a different
sentence, has no `destroy` to hang off, and is not implemented.

### The loader guard

`no_regeneration` on any op other than `destroy` is a load error. Nothing else in
the engine replaces a destruction, so written on a `damage` that will kill, on a
`sacrifice`, or on `replace_deaths`, it would be read by nobody — which is
precisely how the clause came to be dropped in the first place.

### The Ape

`create_token` names a token by id and `loader.validate_token_references` refuses
an unknown one, so Pongify also needed `ape_3_3_g` in
`data/cards/tokens.cards.json`. The pool already held four 3/3 green bodies and
no Ape; substituting one would change the token's printed subtype, which is a
different card rather than a smaller one.

### Test

`tests/unit/test_cant_be_regenerated.py`, including the negative control (the
same creature, the same shield, no flag, survives) and an assertion over the
three shipped cards that print the clause — they are the witnesses, so they are
what the test watches.

## `mode` — a target that belongs to one mode

### Overview

Call Damage Control: *"Choose up to two. Return those cards from your graveyard
to your hand. • Target artifact card. • Target creature card. • Target
enchantment card. • Target land card."*

Four modes, four **different** targets, and two of them live at once. Nothing in
the engine could say that. `targets` is a flat card-level list compiled by
`loader._compile_targets` and fixed as part of the cast **action**, which
`legality` enumerates before `Game._ask_modes` runs — the reverse of the printed
order, and a divergence `_ask_modes`'s own docstring recorded.

Three near-misses, each of which loads and reads as a card that does not exist:

- **One shared `optional` spec** (the Simic Charm idiom) works only because
  Simic Charm's modes point at the same object. These four point at four
  different card types, so one spec cannot supply two distinct targets.
- **Four independent optional specs** leave the mode-to-target pairing
  unenforced — the artifact mode could be taken having targeted a creature card
  — and multiply out past `MAX_TARGET_OPTIONS`, which truncates silently, so
  most legal lines would simply never be offered.
- **One `card_in_graveyard` spec with `count: 2, up_to`** gets the ceiling right
  and drops the at-most-one-per-type restriction, so it returns two creature
  cards.

### What the gap record asked for, and why it is not what shipped

The record filed against this said the real fix was to choose targets as a
*decision* after modes rather than as part of action enumeration — "which
changes casting for every card, both AI seats and the action API" — and stopped
rather than starting that inside a card-unblocking run. That reading is right
about the order and wrong about the blast radius, and the difference is one
sentence:

> `card.targets` stays exactly what it was, and a spec carrying `mode` is simply
> **not in it**.

`legality` enumerates cast actions from the card-level list. It never sees a
mode-owned spec, so no existing card changes, no action changes, and the RL
action space is byte-identical. The new question is asked inside the cast, by
`Game._ask_mode_targets`, between 601.2b and 601.2h — which is where 601.2c puts
it in the first place.

### The shape

```jsonc
"targets": [
  {"id": "artifact", "kind": "card_in_graveyard", "mode": 0,
   "selector": {"zone": "graveyard", "controller": "you", "types": ["Artifact"]}},
  {"id": "creature", "kind": "card_in_graveyard", "mode": 1,
   "selector": {"zone": "graveyard", "controller": "you", "types": ["Creature"]}}
],
"spell_effects": [
  {"op": "choose_mode", "count": 2, "up_to": true, "modes": [
    {"label": "Target artifact card.",
     "effects": [{"op": "return_to_hand", "objects": {"target": "artifact"}}]},
    {"label": "Target creature card.",
     "effects": [{"op": "return_to_hand", "objects": {"target": "creature"}}]}
  ]}
]
```

`mode` is the index into the card's single top-level `choose_mode`. `compile_card`
partitions the compiled specs: `CardDef.targets` keeps the card-level ones,
`CardDef.mode_targets` keys the rest by mode.

### The four rules that came with it

**A mode with no legal target is not offered.** 601.2b — you cannot choose a
mode that would be illegal. `targeting.selectable_modes` asks
`enumerate_target_tuples` with `limit=1` per mode, and `_ask_modes` offers only
those, mapping the answer back through the filtered list. Cast over a graveyard
of creature cards, Call Damage Control shows one bullet, not four ways to spend a
mode on nothing.

**A spell that cannot meet its floor cannot be cast.** "Choose one" with no legal
mode is not offered as a cast line at all. `stack.modal_cast_ok` is asked in
`legality._cast_variant` rather than `_cast_options`, because flashback, foretell
and the second face all reach a card without passing through the latter.

**Refs are stored in printed mode order.** `_ask_mode_targets` walks
`sorted(modes)` and `CardDef.specs_for_modes` rebuilds the same list on
resolution, because `targeting.filter_legal` splits stored refs by *position* —
two orders for one answer is exactly how a ref lands in another mode's bucket and
the spell returns the wrong card while looking completely normal. `_ask_modes`
now sorts what it records for the same reason, which is also 700.2e ("the modes
are executed in the order written on the card") rather than the order they were
clicked.

**Two modes may target the same card.** 601.2c forbids repeating a target within
one instance of the word "target", and two modes are two instances. Striking off
what an earlier mode took would leave a mode offered with nothing to point at,
which is the silently-inert half of a spell this whole capability exists to
prevent.

### No new decision kind

`ask_targets` builds a `CHOOSE_OBJECTS` decision with `purpose: "target"`. The
answer is an ordinal into `options` either way, so the RL encoder, the heuristic
agent, the client's `PromptDialog` and `verify.py`'s auto-answer table all handle
it with no change — the same argument `op_two_piles` made for reusing
`ask_objects` when Fact or Fiction needed an *opponent* to split a pile.

It takes `(label, ref)` pairs rather than refs, because naming a target is
`targeting.describe_ref`'s job and `targeting` imports `effects.context`, not the
other way round.

### A live bug it closed

`StackItem.modes` could not tell "chose none" from "nobody asked". That became
reachable the moment `choose_mode` grew `up_to`: a "choose up to two" cast for
zero modes recorded `()`, `op_choose_mode` read that as unanswered and asked the
whole question again as the spell resolved — a second question the player had
already answered, offering modes whose targets could no longer be declared.
`StackItem.modes_answered` (and `EffectContext.modes_answered`, consumed with
`modes` so a *nested* `choose_mode` still asks its own) says which it is.

### Free casts

Cascade, suspend and "cast it without paying its mana cost" push a spell with no
decision loop to hang 601.2b on, and both already recorded the same
simplification for targets: take the first legal tuple. `stack.free_cast_modes`
extends it to modes — the first legal modes up to the **floor**, and the first
legal targets for each — so a cascaded modal spell resolves having chosen
something rather than nothing.

### What the loader refuses

Six refusals, each a card that would otherwise load and read wrong: `mode` on an
ability's targets (an ability's modes are chosen as it resolves, after targets
would have been declared); `mode` without a single top-level `choose_mode`;
`mode` out of range; a caster-chosen or computed size on a mode-owned spec (the
positional split); `optional` on one (declining the target is declining the mode);
and a variable-size *card-level* spec on the same card (its refs sit in front of
the mode's).

A seventh landed beside them and is not about modes at all: two target specs
sharing an `id`. `filter_legal` buckets by id and every effect names one, so a
duplicate is one target silently swallowing another's refs — never visible on a
board, and a real hazard the moment a card carries four sibling specs.

### Test

`tests/unit/test_modal_targets.py`, over two test-only cards: a four-bullet
"choose up to two" and a two-bullet "choose one" for the floor cases.

## `exile_until_event` — the other duration a delayed ability can have

### Overview

Palace Jailer: *"When this creature enters, you become the monarch. When this
creature enters, exile target creature an opponent controls **until an opponent
becomes the monarch**."*

`exile` had one duration, `until_leaves`, and it is the Oblivion Ring link — the
op records `exiled_by` and the *return* is a separate `leaves_battlefield`
trigger on the same card reading `exiled_with: self`. That is wrong for this card
twice over, and the two are in **opposite directions**:

- it returns the creature on an event that must not return it. Rule 610.3: the
  exile is a one-shot effect with a duration, not an effect the permanent
  maintains, so killing the Jailer leaves the creature exiled;
- and it cannot return it on the event that must, because nothing links a
  `leaves_battlefield` trigger to a monarchy change.

Written with `until_leaves`, Palace Jailer hands the creature back for the price
of killing a 2/2 — a materially weaker card that on the board reads exactly like
the printed one.

### Almost all of it had already shipped, in the other direction

This capability was originally built as a second, competing mechanism — an
`event` key on the `delay` op — and that work was **dropped**. The
`delayed_triggered_ability` run landed first with `delayed_trigger`, which is the
same mechanism arrived at from Forth Eorlingas' end: a subscription with no
permanent, installed by a resolving effect, bindings and controller captured at
that instant, woken by `triggers.collect`, armed onto `state.armed_delays` and
resolved by `game._advance`. Every one of those is what Palace Jailer needs, and
having two of them would have been the worst outcome available.

What was genuinely missing is one field, because the two cards' printed sentences
disagree about **how long the subscription lasts** — and disagree on both counts
at once:

| | fires | lives until |
|---|---|---|
| `this_turn` *(default)* | every time | `turn._cleanup_step` |
| `until_it_fires` | once | it fires, however many turns that takes |

"**Whenever** … **this turn**" is a subscription with a stated lifetime. "Exile
it **until** an opponent becomes the monarch" is not a trigger with a duration at
all: it is the *end* of a duration written on a different effect, so the first
crossing is the whole of it, and it names no turn because the crown may not move
for six of them.

### The silent failure, and the witness for it

`turn._cleanup_step` dropped every event-watching subscription, keyed on the delay
*being* event-watching. That is exactly right for the shape it was written
for — every printed one of those says "this turn" — and it silently retimes
Palace Jailer to an **"until end of turn" exile**. Nothing on the board says
which card shipped: the creature is in exile either way, and the difference only
shows up a turn later.

So the clear is keyed on the subscription's own `duration` instead, which is the
field that actually carries the printed sentence.
`test_the_exile_outlives_the_turn_it_was_made_in` walks three turn boundaries and
fails against the blanket clear; `test_and_still_ends_when_the_crown_moves_turns_later`
is the other half, because surviving cleanup is worth nothing if the subscription
has stopped working.

### How one-shot and repeating coexist

`triggers._arm_delayed`'s docstring already argued against a "fired" flag, and it
was right on its own terms: an extra combat this turn is a second damage batch
and a second trigger, so the one-per-batch guarantee belongs to the **event**.
The one-shot discharge is not that flag. It is a different claim — that this
subscription is spent because the duration it was ending is over — and the two
now sit side by side in the same loop, chosen by `duration`.

It discharges **as it arms**, before the copy on `state.armed_delays` resolves,
so the exile ends exactly once even if the same crossing were to arm it again
before the advance loop got round to the copy. `_delayed_bindings` has already
snapshotted everything the copy needs, so striking the original off costs it
nothing. The strike is by **identity**: two Palace Jailers each holding a creature
differ only in their captured bindings, and one that exiled nothing would compare
equal to another that did.

### One field, not two booleans

The bet is stated where the constant lives. Repeating-or-once and
turn-scoped-or-not are two axes, they are correlated in *both* printed cards, and
they are **not** the same question. A card that separated them — "the first time
a creature dies this turn" — needs a third entry in `structs.DELAYED_DURATIONS`
rather than a different reading of these two. No such card is in the pool, and
naming the gap is cheaper than shipping a second boolean nothing sets.

**Unblocked one card: Palace Jailer**, at the agent tier — the template tier
harvests nothing here (`--tier templates --retry`: `wrote 0 | no template 200`).
It needed two capabilities: `monarch` shipped the designation, 721.3's two
inherent abilities and the `becomes_monarch` event, and this is the duration that
was the last blocker. Its expectation is a real observation —
`opponent_battlefield_count: 5`, the opponent's board one creature lighter — and
the rest of the coverage is `tests/unit/test_exile_until_event.py`, where the
Jailer dies and the creature stays exiled, and then comes back anyway.

## `variable_target_count` — a number of targets the game works out, and "up to"

### Overview

Marshal's Anthem: *"When this enchantment enters, return **up to X** target
creature cards from your graveyard to the battlefield, where X is the number of
times this enchantment was kicked."* One gap record, one card, and it was the
card's **last** blocker — `multikicker` shipped the other half a batch ago and
explicitly left this one standing.

`TargetModel.count` was `int | Literal["any"]`. Both spellings are a different
card, and the gap record had already checked each:

| spelling | what the Anthem becomes |
|---|---|
| `count: "any"` | "any number of target creature cards" — the count comes off the kicker entirely, so the {2}{W}{W} cast reanimates the whole graveyard |
| `count: N` | a card with a number printed on it |
| `count: N, optional: true` | "exactly N, or none" — every size between 1 and N-1 forbidden |
| untargeted `return_from_graveyard` with `count: {"additional_paid": true}` | the right *number*, but no targeting: no legality check at announcement, no fizzle, no `becomes_target`, and `min_count == max_count` forces exactly X |

### Tier: A, and not even an op

No new op, no continuous effect, no decision kind, no event, no API field — and
no new *state* either. The number was already recorded and already readable:
`game._cast` writes `Action.additional_times` to `obj.cast_additional`, and
`{"additional_paid": true}` has read it back since casualty and replicate. What
was missing was only that a **target count** could not be a value at all.

Two changes, deliberately independent:

```jsonc
"count": {"additional_paid": true},   // the count is a value expression
"up_to": true                          // and the value is a ceiling, not an exact number
```

### Where the number is read, which is the whole design question

601.2c fixes a target count when the targets are *declared*, and for this card
that moment is **603.3d, not 601.2c**: the targets belong to a triggered
ability, so they are chosen as the trigger goes on the stack — after the
enchantment has entered. `stack._choose_trigger_targets` calls
`enumerate_target_tuples` with `trig.source_oid`, which is the enchantment on the
battlefield, wearing the `cast_additional` written at cast time and carried
across the zone change on the same oid. That is the same read `colors_of_mana_spent`
makes for a Sunburst artifact's enters trigger, from the same place.

A **spell's own** targets are the other moment and there is nothing to read
there: 601.2c happens while `legality` is enumerating cast lines, before X has
been announced and before any additional cost has been paid. The expression would
evaluate to 0 — or, on a card cast twice in one game, to the *previous* cast's
number, which is worse. So `_compile_targets` refuses a computed count on a
card's own `targets` outright, and says why. Comet Storm ("for each time this
spell was kicked, it deals X damage to another target") is the card that wants
it; giving it one means teaching legality to enumerate its target tuples once per
payment count, which is a separate change and is not smuggled in here.

### Keeping four spellings of "or fewer" from becoming three of the same thing

`optional` already existed twice — `TargetModel.optional` for declared targets
and the `optional` selector key `pick_from_pool` honours as `min_count = 0` — and
both mean **"exactly N, or none"**. "Up to X" is min 0 / max X, which neither can
say, so the word had to be a third one rather than a redefinition of either:
redefining `count: {value}, optional: true` to mean 0..X would have made the
same flag mean different things depending on whether the count was literal.

| spelling | means |
|---|---|
| `count: N` | exactly N |
| `count: N, optional: true` | exactly N, or none |
| `count: "any"` | zero to the whole board |
| `count: N or a value, up_to: true` | zero to N |

Each overlapping pair is refused at load time, because each is a card that would
otherwise read as a printing that does not exist: `up_to` with `count: 1` (that
is `optional`, and is how Oath of Eorl and every other "up to one" already ships),
`up_to` with `"any"` (no ceiling to cap), and `up_to` beside `optional` (two
answers to one question).

`"any"` and "up to X" then share one code path, differing only in where the
ceiling comes from — `len(options)` against the evaluated value — which is what
keeps the ordering rules the same for both: subsets largest first, because
whatever takes a tuple without asking takes `options[0]`, and the empty tuple
always present and always last, because both readings include zero without
needing `optional`.

### Three places had to learn that a spec's size is not a constant

- `enumerate_target_tuples` evaluates the count, and offers `0..X` under `up_to`.
  A computed count of **zero** contributes `[()]` rather than `[]` — "no targets
  asked for" is not "no legal target", and the difference is a trigger that
  resolves against one that cannot go on the stack.
- `filter_legal` slices stored refs by position, so a variable-size spec takes
  "whatever is left". It does **not** re-evaluate: the number is fixed when the
  targets were declared, and re-reading it at resolution would re-slice refs that
  were chosen under the old one. `TargetSpec.variable_size` now names all three
  variable shapes, so the existing "at most one, and it comes last" rule covers
  the new ones for free.
- `loader._mentions` walks **target specs** as well as effects. Multikicker's own
  guard refuses "a cost no effect reads via `additional_paid`", and on this card
  the only reader is the target count — so the one card the mechanic exists for
  was about to be refused by the mechanic's own guard.

### The behaviour gate had to cast it kicked

`_play_and_check` already measured a kicker card **kicked**, on the argument that
kicked is the strictly larger claim. Multikicker gets the same treatment, because
without it the gate is worthless here: legality offers cast lines ascending from
the free one, `find_play` took the first, and X = 0 returns nothing at all — a
card that did nothing would have passed exactly as one that worked. Gate 4 still
casts it unkicked, so the zero path is exercised too.

That is what makes Marshal's Anthem's expectation a real observation rather than
the weak `{"zone": "battlefield"}` fallback: in the sandbox it is cast with the
most kicks the board can pay, and the assertion is that **both** creature cards
have left the graveyard (`graveyard_size: {"0": 0}`) and the battlefield is three
permanents larger than the lands and props it started with.

### Cards this unblocked

`marshal_s_anthem`, and no others — no other gap record names this capability.
`--tier templates --retry` harvested nothing, which is correct: no template reads
"Multikicker {1}{W}" or "up to X target …", so the card came through the agent
tier. Coverage beyond the card is `tests/unit/test_variable_target_count.py`.

---
## `counter_unless_pays` — billing a seat that only a target names

### Overview

Frontline Medic: *"Sacrifice this creature: Counter target spell with {X} in its
mana cost **unless its controller pays {3}**."* The other half of the sentence
the previous run left open, and the last thing between the Medic and the pool.
**It is now authored** — `data/cards/auto/`, all six gates.

The unless-pays *shape* already shipped. `may` + `pay` + `else` is exactly
"unless", and Rhystic Study is the working card: pay and the `else` branch does
not run, which is what buying the absence of a thing looks like. What could not
be said is **who is being billed**. Every payer in the pool arrives as a trigger
binding — Rhystic Study's off `spell_cast`, ward's off `becomes_target` — and
`select_players`' `controller_of` reads `ctx.bindings` and nothing else. An
activated ability's `StackItem` carries its targets and its bindings as separate
things and binds nothing for what it was activated at, which is precisely why
ward could be written and a targeted counterspell could not.

### Tier: A, and not even an op

No new op, no continuous effect, no decision kind, no event, no API field. One
**player spec** — `{"controller_of_target": "t1"}` — and one load-time refusal.
The whole clause then writes itself out of vocabulary that already existed:

```jsonc
{ "op": "may", "player": { "controller_of_target": "t1" },
  "pay": { "mana": "{3}" },
  "else": [ { "op": "counter", "target": "t1" } ] }
```

### The rules argument: 109.5, and the seat that pays

"Its controller" on a spell means the controller of *that spell*. The key is
resolved when the effect runs rather than when the ability was activated, which
is 608.2 rather than a shortcut: control of a spell can change while the ability
sits on the stack, and the seat that gets the bill is the one holding it when
the bill arrives. It answers for **stack refs and object refs alike** — a spell
has a controller and so does a permanent — so "unless that permanent's
controller pays" is the same key, and the result is de-duplicated in target
order, because "counter each of them unless their controllers pay" is one bill
per seat.

### The silent misfire, and why it is now a load error

`{"player": {"target": "t1"}}` is the obvious thing to write and it played the
card's own opposite. `ctx.target_players` keeps only refs of kind `"player"`; a
spell's ref is kind `"stack"`, so it returned `[]` — and `op_may` reads an empty
player list as `chooser = ctx.controller`. "Counter target spell unless its
controller pays {3}" resolved as "unless **you** pay {3}": the Medic asking its
own controller to pay for countering the spell they had just chosen to counter.
Nothing raised and nothing logged.

**A load error rather than a correct answer**, and deliberately. Making
`{"target": ...}` quietly fall through to the controller would leave one key
meaning two different things depending on the target's kind, which is the same
invisibility one layer down — the author would still not know which card they
had written. So the loader refuses the combination and names the key that works:
a `player` spec may say `target` only of a target that can *be* a player
(`kind: "player"`, or the player half of `kind: "any"`), and
`controller_of_target` only of one that has a controller. Exactly one of the two
is right for any given spec, which is what makes the pair checkable instead of
being two ways to be wrong.

The check is written once, in `_validate_effect`, for **every** op that takes a
`player` — the way `counter` is checked once for every op that names a counter
kind. `become_monarch`, `goad` and `cant_attack_player` had each grown a private
copy of half of it; they now call the shared validator, and the next op to take
a player is covered before it is written.

### It caught a shipped card on the way in

Hellrider — *"Whenever a creature you control attacks, this creature deals 1
damage to the player or planeswalker it's attacking"* — was written
`{"player": {"target": "defender"}}`. `defender` is a **trigger binding**, not a
declared target, so `ctx.targets` had no such key, `select_players` returned
`[]`, and the card dealt no damage at all. It had shipped that way, with a
`{"zone": "battlefield"}` expectation that could never have noticed, since the
verifier declines combat. `{"binding": "defender"}` is the correct spelling and
was one word away the whole time.

That is the argument for the load error stated as evidence rather than as
principle: the first thing a general check found was a card nobody knew was
broken.

### Verification

The behaviour gate legitimately asserts only `{"zone": "battlefield"}` for the
Medic. The verifier **declines combat**, so battalion cannot fire, and it never
activates activated abilities, so the counter line cannot fire either — the
weak expectation is the honest one and no gate was weakened to get it.
`tests/unit/test_counter_unless_pays.py` is where the real coverage lives, on
the shipped card rather than a fixture: which seat is asked, paying countering
nothing, declining countering the spell, a controller who cannot pay never being
asked, and **the pod** — three seats, where "the spell's controller" and "an
opponent" finally differ and `player: "opponent"` would bill an arbitrary one.

`verify.py` gained one dummy role, `x_spell`, exactly as `add_dummy_spell`'s
docstring asked the next run to do rather than relaxing the gate. It is not
reached by the Medic — a permanent's ability targets are not in the sandbox's
stack, and could not be: dummy spells on the stack make a *creature* uncastable
by 117.1a, which is what its own gate 4 measures — but the "Counter target spell
with {X} in its mana cost" instants behind it in the queue reach it directly.

### What it unblocks

Frontline Medic today. Behind it, the plain
*"Counter target spell unless its controller pays {N}"* family — Mana Leak,
Daze, Condescend, Rethink, and the dozens of printings the authoring queue holds
on this one clause — plus every non-counter line that bills a targeted object's
controller: "unless that spell's controller pays", "that spell's controller
discards a card".
## `look_at_library_top` — the same card, sent to one seat instead of every seat

### Overview

Verge Rangers: *"First strike. **You may look at the top card of your library any
time.** As long as an opponent controls more lands than you, you may play lands
from the top of your library."*

The middle line was the card's last blocker. Its other two needs —
`per_opponent_count` and `conditional_player_static` — shipped in earlier runs,
and both of those runs ended with "**no card**", because this line was still
standing. It ships now, so does the card, and Verge Rangers becomes the first
card in the pool to carry a `condition` on a player-wide static.

### The rules argument: 701.16a, looking is not revealing

Rule 400.2 makes a library a hidden zone. Rule 701.16a then splits the two verbs
that open it: a card **looked at** is seen by the player looking and by nobody
else, while a card **revealed** is shown to every player. The engine had the
second verb only.

`reveal_library_top` is Vampire Nocturnus' "play with the top card of your library
revealed", and `serialize` writes its `library_top` into **every** seat's view
deliberately — that decision is written down in the code, in the docs and in
`test_top_of_library.py::TestTheReveal::test_the_opponent_sees_it_too`, on the
argument that an opponent who cannot see a revealed card is playing against
information they are entitled to.

Verge Rangers reveals nothing. Authoring it on the public static would hand every
opponent the top of a deck whose *other* ability plays lands off that same card —
a strictly different card, and a worse leak than it first looks, since the top
card is the thing the third line is about.

### What could not stand in

| candidate | why not |
|---|---|
| `reveal_library_top` | public by construction; the whole gap is who receives it |
| the `look_at_top` **op** | looks once, at resolution, and is spent. "Any time" is a standing permission, and there is no moment for a trigger to fire at |
| a trigger on some event | same problem from the other end: no event means "any time" |
| a `top_of_library` condition | reads the card's printed face for the rules. It answers questions; it shows nobody anything |

### Tier: E, and only for one boolean

Routed as **E** — a new API field — and it is worth saying exactly which half of
the change earned that, because most of it did not.

The card itself needs **no** new field. `serialize._player` has had both `pid`
and `seat` all along (`own = pid == seat` is what hides a hand), so the private
half is *scoping* an existing field rather than adding one: `library_top` is
already the right payload in the right shape, and both the frontend's `PlayerOrb`
pile and `findCard`'s zone-of-one lookup already consume it. Adding
`library_top_private` beside it would have been two fields that can disagree
about one card.

What does not survive scoping is the **distinction**. The two statics produce a
byte-identical payload, so a seat holding one cannot tell which it is — and the
pile said `Top of library, revealed: X`. Under a private look that sentence is
false in the direction that matters: it tells the one player who can see the card
that the whole table can. So one boolean, `library_top_public`, and the Tier E
file list for it. `schemas.py` needed nothing, because `StateResponse.state` is a
bare `dict[str, Any]` and the view is serialized generically.

That makes the skill's Tier A note — "the server needs no change for a new op,
keyword, counter type, decision kind or action kind" — inapplicable rather than
wrong: this capability *is* a serialization question, and nothing else.

### How it is kept private

```python
def _library_top(state, pid, seat) -> tuple[dict | None, bool]:
    public = player_reveals_library_top(state, pid)
    if not public and not (pid == seat and player_looks_at_library_top(state, pid)):
        return None, False
    top = top_of_library(state, pid)
    if top is None:
        return None, False
    return card_view(state, top.oid), public
```

One function, and the seat test is in it rather than at the call site, so there is
no second path to `library_top` that could forget it. Three consequences worth
pinning:

- **A reveal beside a look is still a reveal.** `public` is computed first and
  wins; the weaker permission cannot make a shown card private again.
- **`library_top_public` is false whenever no card is sent**, including when the
  library is empty under an active reveal. A stale `true` next to a `null` face
  is a claim about a card that does not exist.
- **The permission is continuous.** It ends when its source leaves, and it is
  gated by `_active_player_statics` like the other eight, so an "as long as…"
  clause on it is asked rather than ignored.

### The static itself

The ninth player-wide effect, `affects_player` like the rest, read by
`characteristics.player_looks_at_library_top` and — like its public twin — by
`serialize` and by nothing else. It changes no rule: it grants no permission to
play or move the card, and no rules code asks about it.

`t_all_player_statics` carries it, so `TestEveryPlayerWideStatic` walks nine
readers rather than eight; `test_the_table_covers_every_gated_effect_on_the_card`
is what would have caught it being added to the loader and forgotten there.

### What it unblocked

**Verge Rangers**, through all six gates, and it was its own last blocker. The
card is the whole harvest — `--tier templates --retry` produced nothing, since no
template reads the printed sentence, so it was authored at the agent tier.

Its expectation is `zone: battlefield` plus `granted: first_strike`, which is
deliberately weak about the line this run built: the verifier's expectation
language has no key for *what a given player can see*, so the visibility is not
assertable as a card expectation and the gate was not weakened to pretend
otherwise. That coverage lives where it can be written honestly —
`tests/unit/test_look_at_library_top.py` for the engine and
`tests/server/test_multiplayer_game.py::TestTopCardVisibility` for the wire.

The two-humans server test is the one that matters, because it is the only place
the claim is made against a real second token: seat 0 fetches `/state` and is
sent the card, seat 1 fetches `/state` and is not.

### Retired with it

`TestTheUngatedStaticsAreUntouched::test_no_shipped_card_gates_a_player_wide_static`
asserted `gated == []` over the real pool, and its docstring said to retire it
naming the card that eventually gated one. That card is Verge Rangers. The
successor asserts the opposite — the pair is *in* the pool — because the useful
half of the guard survives: a gated player-wide static is only correct if
something reads the gate.

### Guarded by

`tests/unit/test_look_at_library_top.py` (21 cases), and its shape is the point:
every claim is asserted **from both seats**, because a version that sent the card
to everybody passes every controller-side assertion there is. The opponent class
includes a four-player pod, since "not the opponent" and "not any of the three
other seats" are different claims.

Then `tests/server/test_multiplayer_game.py::TestTopCardVisibility` over HTTP,
`tests/unit/test_conditional_player_static.py` for the ninth reader through the
gate, and `frontend/tests/playerOrb.test.tsx` for the wording — the pile must not
call a private look "revealed".
## `delayed_triggered_ability` — 603.7's other half, and the batch it has to watch

### Overview

Forth Eorlingas!: *"Create X 2/2 red Human Knight creature tokens with trample and
haste. Whenever one or more creatures you control deal combat damage to one or
more players this turn, you become the monarch."*

The first line was already a single `create_token` with `amount: {"x": true}`,
once `token_pool` registered `human_knight_2_2_r_trample_haste`, and `monarch`
had already shipped `become_monarch`. The second line was two capabilities
neither of them touched: a delayed ability keyed on an **event** rather than a
step, and a combat-damage event that fires **once for the batch**.

The card is now playable and was the last blocker on it. Writing only the token
half would have been a card that makes twenty Knights and never gives the
monarchy to anybody, which the residual gate rejects and a player could not tell
from the real thing until the crown failed to move.

### Tier: A and D

A new op (`delayed_trigger`) and a new `EventType`. No continuous effect, no
decision kind, no API field — the delayed ability's payload is ordinary DSL and
the state it lives in is serialized generically.

Tier D is the half that forces frontend work, and both files got a deliberate
entry rather than the `default` fallthrough. See "The frontend" below.

### Why the sentence cannot be a triggered ability on the card

Because the card is a **Sorcery**. It is in a graveyard before the first creature
swings, so an ability printed on it would be watching from there: with the
default `active_zones` it never fires at all, and with `["graveyard"]` it fires
for the rest of the game. Neither is "this turn", and the difference between them
is the whole card.

`delay` is the op that exists for effects with no permanent to hang on, and it
could not say this either. Its only timing knob is a step name checked against
`turn.DELAY_STEPS` — five names, five moments — so it can say "at the beginning
of the next end step" and cannot say "whenever a creature connects".

`combat_damage_by` in `condition_keys` reads the turn ledger *backwards* (prowl:
"was a player dealt combat damage this turn by a Faerie"). It can be asked at
cast time and cannot make anything happen later, and this card's whole point is
that the damage comes after the sorcery has resolved.

### Where the three pieces went

**Storage: `state.delayed_triggers`**, the list `delay` already writes to, as a
`DelayedTrigger` carrying a `trigger` spec instead of a `step`. The same struct
because everything else about the two halves of 603.7 is identical — bindings
captured when it is created, controller captured with them, no source object when
it fires. The controller matters more here than it ever did for `delay`: "you"
cannot be read back off a card sitting in a graveyard, where
`reset_permanent_state` has been through it. `turn._delay_due` refuses an
event-watching entry explicitly rather than relying on `DELAY_STEPS.get("")`
returning `None`.

**Dispatch: `triggers.collect`**, the one funnel every fired event goes through,
in a second walk beside the one over permanents. It **arms** rather than
resolves, and that is the design decision worth the words: `collect` is reached
from inside `damage_player`, several frames below anything that can suspend, so
resolving there would forbid a delayed payload from ever asking a question —
which the step-scoped half has always been allowed to do. So a copy of the
subscription, with the event's payload folded into the captured bindings, goes on
`state.armed_delays`, and `game._advance` resolves it at the next safe moment.
That is exactly the arrangement `pending_triggers` has had since triggers
existed, and it is why the new branch in `_advance` sits immediately above the
drain: both halves of 603.7 resolve off the stack, so the delayed half of an
event runs before the ordinary triggers of that same event are put on it.

A **copy**, not the subscription itself. The subscription stays armed for the
rest of the turn, because the printed line is "one or more creatures" and a
second combat fires it again.

**Clear-down: `turn._cleanup_step`**, beside `clear_attack_restrictions`,
`clear_block_prohibitions`, `clear_unblockables`, `clear_damage_shields` and
`clear_sacrifice_restrictions` — the five other "this turn" clauses owned by no
permanent, for exactly the same reason this one is: the sorcery that said it has
been in a graveyard since it resolved and `clear_until_eot`'s walk of the
battlefield has nothing to find. Keyed on the *kind* of delay rather than
emptying the list, because "at the beginning of the next upkeep" is scheduled
**across** this boundary and a blanket clear would throw Arcane Denial's draw
away.

Not "after it fires once". A per-firing expiry and a `max_per_turn` cap are the
same mistake: `extra_combat` gives a turn a second combat, and the printed
ability triggers in it.

### Once per damage batch, not once per creature

`EventType.CREATURES_DEALT_COMBAT_DAMAGE`, fired by `combat.deal_combat_damage`
once per damage step per **damaging player**, carrying `damagers` and `damaged`.

`deals_combat_damage_to_player` is the near miss and is per *connection*. Twenty
Knights getting through fire it twenty times, so a card built on it hands out the
monarchy twenty times over — which is not merely noisy, since each firing is a
fresh `become_monarch` and every one of them is an event other cards listen to.
`max_per_turn: 1` on top of it survives that and fails one step out, in the extra
combat.

Read off the same `assignments` list `_monarch_transfer` reads, immediately after
it, and for the same reason: rule 510.2 makes combat damage simultaneous and
`deal_combat_damage` collects every assignment before applying any, so the batch
is knowable there and nowhere else. `damage_player` sees the hits one at a time
and cannot tell the first of a batch from the third.

Per damaging **player** rather than per (player, defender) pair, which is where
this stops being the shape `creatures_attack_player` has one phase earlier. That
event is per defending seat because its printed clause is "one of your
opponents"; this one says "to one or more **players**", so a seat whose creatures
connect with two opponents in one step gets one event with both seats on
`damaged`. Grouping by the damaging player is also what gives `controller: "you"`
an actor to compare against — fired once for the whole step there would be none.

Creatures by **derived** type, and damage to players only: an animated Equipment
that got through is a creature, and damage to a blocker or a planeswalker is
combat damage that is not this.

Two batches per turn's combat, not one: first strike and regular damage are
separate steps (510.4) and a double-striker that connects in both triggers twice,
which is what the per-creature event has always done.

### Where it is refused

`trigger` takes `event`, `controller` and `condition` and nothing else.

The omissions are not laziness in two different ways. `source: "self"`, `filter`
and `max_per_turn` are all answered off the `GameObject` hosting the ability —
`matches_card_filter` takes it as `ability_source`, and `_queue` counts the cap
per `(permanent, ability index)` — and a delayed ability has no such object.
Accepting any of them would load a card whose printed restriction silently does
nothing, which is the precise failure `_validate_effect` exists to stop. The pure
event filters (`counter`, `nth`, `not_cause`, `mana_ability`, `defending`) are
left out because no card asks for them here; `_delayed_matches` gains a line each
when one does.

An unknown `trigger.event` is a load error, for the reason a misspelled `delay`
step is: the subscription installs, nothing ever satisfies it, and the card reads
as printed while doing nothing at all.

`{"target": …}` inside the payload is a load error, sharing
`_refuse_targets_inside_a_delay` with `delay` — 603.7 says the *resolving ability*
creates the delayed one, so what it creates never chose a target, and
`run_armed_delays` builds its context with `targets={}` exactly as
`turn._run_delayed` does.

### The frontend

Deliberately silent in both `labels.ts` and `events.ts`, listed in both rather
than left to their `default` fallthroughs so the decision is visible where the
next person looks for it. The batch accompanies hits that are already narrated
one by one as life losses and already animated by `damage_dealt`; a line and a
beat for the summary would sound the combat a second time. It is the same
arrangement `creatures_attacked_player` got one phase earlier, and
`combat_damage_to_player` — the event this one batches — has been in `SILENT`
since that set existed.

### What it unblocks

Forth Eorlingas!, which was waiting on this and on `monarch`, and is now
authored: `{X}{R}{W}`, twenty Knights in the verifier's sandbox (X is capped at
`mana.max_affordable_x`'s 20, not by the thirty lands), and the crown installed
for the rest of the turn.

The verifier **declines combat**, so the delayed half cannot be demonstrated
there — the expectation is honest about that and asserts the token half plus the
graveyard. What proves the second line is `tests/unit/test_delayed_triggered_ability.py`,
which swings in a three-player position and checks the crown moves, that it moves
once for three attackers, once for two defending seats, again in an extra combat,
and not at all the next turn.

## `x_in_mana_cost` — a symbol, not a number, and the selector nobody was reading

### Overview

Frontline Medic: *"Sacrifice this creature: Counter target spell **with {X} in
its mana cost** unless its controller pays {3}."* Two capabilities in one
sentence. This run built the first; `counter_unless_pays` — billing the
*targeted spell's controller* — is a separate gap record and a separate run, and
it is still open.

So **no card was authored**, and that is the honest outcome rather than a
shortfall. The Medic is one clause away and the clause is not this one.
`tests/unit/test_x_in_mana_cost.py` is therefore the whole of this change's
coverage: there is no authored card being re-verified through six gates on every
run, which is exactly the case §3 of the skill is written about.

### Tier: A, and barely

No new op, no continuous effect, no decision kind, no event, no API field. The
underlying datum already existed and was already parsed — `ManaCost.x_count`,
incremented once per `{X}` token by `ManaCost.parse` — and had never been read
back by anything. What shipped is a selector key over it, plus the plumbing that
turned out to be missing underneath (below), plus a load-time guard.

### The rules argument: 107.3 against 202.3b

Rule 107.3 makes the {X} in a mana cost a **mana symbol**. 601.2b has the caster
announce a value for it as the spell is cast. 202.3b says X counts as 0 for mana
value anywhere the object is not on the stack. None of that removes the symbol
from the card, and "with {X} in its mana cost" asks about the symbol.

So the filter reads `card_of(obj).mana_cost.x_count` — the printed cost of the
**face being cast**, so a split half or an adventure answers for the half on the
stack — and never `StackItem.x`. A Fireball announced for X = 0 is still a legal
target for the Medic.

### Why `mana_value` could not stand in, in either direction

| | |
|---|---|
| `mana_value` as it is | Scores X as 0, so Fireball `{X}{R}` and Shock `{R}` are **both mana value 1**. One comparison catches both or neither. `test_fireball_and_shock_have_the_same_mana_value` states it as data and `test_a_mana_value_clause_catches_both` plays it out on a stack |
| `mana_value` made 202.3b-correct on the stack | Would not rescue it, which is the argument that decides the design. 601.2b lets the caster announce **X = 0**, and there a Fireball's mana value is Shock's exactly while it remains a legal target. The two readings disagree precisely at the boundary, which is why `TestTheAnnouncedXIsNotTheQuestion` parametrizes over X = 0, 1 and 3 |
| `mana_symbols` | The only other symbol-level cost reader, and it cannot filter a pool at all: it is a value expression, not a selector key. `validate_mana_symbols` also restricts `of` to W/U/B/R/G, by design — it was built for chroma, and there is no spelling for X |
| A condition on the ability | `TargetModel` carries `selector`, `count`, `one_per_player` and `optional` and no condition slot; an activated ability's own `condition` is checked by legality *before* targets are chosen, so it cannot see the spell |

### The plumbing that was missing, and three shipped cards it was wrong for

A `kind: "spell"` target spec **ignored its `selector` outright**.
`targeting.candidates` returned every spell on the stack; `still_legal` answered
`item.is_spell` and stopped. The clause loaded, validated against
`SELECTOR_KEYS`, and was never consulted — the silently-inert filter that
`validate_selector` exists one layer up to prevent.

That meant Negate, Essence Scatter and Exclude were all Counterspell, and
nothing said so. The probe that found it is one line: with `negate` in hand and
a creature spell on the stack, the engine offered the cast.

Both call sites now run the selector through `matches` with the default zone set
to the **stack** rather than `matches`'s battlefield — a battlefield default
would reject every candidate and turn every counterspell in the pool into a dead
card, which is why `test_an_empty_selector_still_takes_everything` is a
regression guard rather than a tautology. The re-check half is 608.2b: a
selector that held when the counter was cast has to still hold when it resolves.

Characteristics come off the printed face, because `matches` reads the derived
layer only for permanents — and that is what a spell on the stack should get
anyway, since no static is applying to it.

### The gate caught it, which is the system working

Making the selector real failed **Negate** at gate 4 (playable) in
`tests/cards`, and failed the baseline-honesty test alongside it. Both
`add_dummy_spell` helpers — `verify.py`'s and
`tests/cards/test_every_card_works.py`'s — pushed a single *creature* spell onto
the stack, so "counter target noncreature spell" had nothing to point at and the
card was correctly reported as uncastable.

The fix is in the harness, not the gate: each now pushes **one spell of each
broad shape**, the same argument the opponent's board already makes by carrying
one of each type. Both dummies target nothing of their own, since the sandbox
may let whichever survives resolve. The next card whose spell-selector no dummy
satisfies — "target spell with {X} in its mana cost", once one is authored —
will fail here the same way, and the answer is another role rather than a
relaxed check.

### The guard

`{"x_in_mana_cost": {"op": ">=", "value": 1}}` is the natural thing to write,
because the key sits beside `mana_value`, which *is* a comparison. It is also a
truthy dict, so it would have meant `true` by accident, and `0` would have
quietly meant `false`. Non-booleans are a load error. There is nothing to widen
this into later: "two or more X symbols" is not a printing.

### What was deliberately left out

Not in `STATIC_FILTER_KEYS`, and not in `SPELL_FILTER_KEYS` either. A static
filter matches **permanents**, where 202.3b makes X 0 and the question is not
asked; every printed line that reads {X} out of a cost points at the stack.
`mana_value` is not in that set either, so no static in the engine reads a cost
at all. The same call `attacked_this_turn` and `is_monarch` got: vocabulary with
no card asking for it is vocabulary that invites a card to be written wrongly.

### What it unblocks

Nothing on its own — see the overview. `data/authoring/gaps/frontline_medic.json`
keeps its `counter_unless_pays` need and loses this one, so the report now ranks
the Medic by the one clause that is genuinely still missing. The two shipped
counterspells the plumbing repaired are the change's only immediate effect on a
real game.
## "You can't sacrifice those creatures" — a prohibition on a game action

### Overview

Call for Aid: *"Gain control of all creatures target opponent controls until end
of turn. Untap those creatures. They gain haste until end of turn. You can't
attack that player this turn. You can't sacrifice those creatures this turn."*
Four of those five clauses were already expressible — `gain_control` with a
duration, `untap`, `grant_keyword`, and `cant_attack_player`, which shipped one
run ago and was this card's other blocker. The fifth had nothing at all behind
it: **the engine could not refuse a sacrifice**, in any shape, from any source.

The last sentence is not decoration. Without it the spell borrows an opponent's
whole board and the caster is free to feed it to a sacrifice outlet before
control reverts — a strictly better card than the printed one, and one that
would look completely normal on screen. That is why the gap record refused to
write a partial answer.

`cant_sacrifice` is the fourth op in a family that now has a settled shape:
`cant_attack_player`, `cant_block`, `unblockable` and this one are each a frozen
record on `GameState` with a required `duration`, one predicate reading it, and
a clearing hook in `turn._cleanup_step`. It is there for their reason — a
resolving sorcery leaves no permanent for a static to live on, and the set it
names is chosen when it resolves rather than matched by a filter over printed
characteristics.

### The three near relatives, and why each is a different game action

| | |
|---|---|
| `lock_abilities` | stops a permanent's **own** activated abilities being activated. A sacrifice outlet is somebody else's ability — an Altar, a Bloodthrone Vampire, a Viscera Seer — and the fodder's own abilities have nothing to do with the cost that eats it. It also says nothing about the `sacrifice` op or an edict |
| `replace_deaths` | redirects a permanent's death **after** the sacrifice. The creature still left the battlefield and the outlet still got paid, which is not what "can't" means — and on Call for Aid it would leave the borrowed creatures gone from the board when control was due to revert |
| `indestructible` | explicitly does not prevent a sacrifice (701.17a). Neither does protection nor any prevention effect: a sacrifice is neither damage nor destruction, so none of them reaches the question |

### Two roads to a sacrifice, and the rule does not distinguish them

A sacrifice is demanded either as a **cost** or as an **effect**, and 701.17b
closes both without saying so — you simply cannot sacrifice the permanent, so a
cost that requires it becomes unpayable and an effect that would take it must
take something else.

**Cost.** `costs._sacrifice_pool` drops the protected permanents. `can_pay` and
`pay` both build the pool through that one helper, so they cannot disagree: an
outlet with nothing else to eat is an *unpayable* cost and `legality` never
offers the activation at all. It covers the activated-ability cost and the
additional cost to cast in the same line, because `carddef.additional_cost` is
an ordinary `Cost`. Emerge and offering are the one sacrifice cost that is not:
the fodder is chosen as part of the cast action, since how much the spell costs
depends on which creature it is, so `legality._emerge_fodder` asks the same
question a second time and a protected creature is simply not a line on offer.

**Effect.** `op_sacrifice` narrows its **pool** before asking, rather than
skipping in the loop afterwards. That ordering is the whole of the rule: an
edict against a board of one protected creature and one ordinary one must take
the ordinary one. Filtering after the choice would let a protected creature
answer the edict and then fizzle it, which is a better answer than the printed
card allows. Only when nothing legal remains does the effect do nothing to that
player, which is the same rule read from the other end. The op is assembled out
of `resolve_pool` + `pick_from_pool` — the two halves `choose_objects` calls in
sequence — because "not under a sacrifice restriction" is a fact about the table
and not a selector key any card writes.

### Why not one guard in `zones.sacrifice`

The single funnel is the tempting shape and it is wrong twice. It is wrong by
the rules, because 701.17b makes the *choice* illegal rather than making the
action silently fail — a cost that is paid and sacrifices nobody is a free
outlet. And it is wrong mechanically: `zones.sacrifice` is also how the *game*
sacrifices a permanent with no player choosing, when 704.5s finishes a Saga, and
`sba._finished_sagas` sets its "something changed" flag on the call. A
`sacrifice` that quietly returned `False` under a restriction would make
`sba.check` report a change for ever and the state-based-action loop would never
settle. `TestTheGameStillSacrificesForItself` pins it.

### What is deliberately not shared with the three before it

`this_turn` is the only duration, because it is the only one printed on a
one-shot sacrifice prohibition. `BlockProhibition` and `Unblockable` also carry
`until_your_next_turn`, and everything downstream of that word follows from it:
a `player` field to hold the clock, a hook in `turn._untap_step`, and a prune in
`sba._eliminate` for a seat whose next turn is never coming. With one turn-long
duration none of those exists — the cleanup step clears the entry whoever has
left the game — so the record is `objects`, `duration`, `source`, and nothing
else. The precedent is `DamageShield`'s one-word `DAMAGE_SHIELD_DURATIONS`: a
second word is added there when a card prints one, rather than smuggled in as a
default nobody clears.

It is keyed on the **objects** and not on a player, even though the printed
sentence says "*you* can't sacrifice those creatures". Only a permanent's
controller ever sacrifices it (701.17a), and the same spell has just handed that
controller-ship to its own caster, so "you" and "whoever could sacrifice these"
name the same seat. A prohibition a later control change could slip out of would
be a strictly better card.

### The clause that had nowhere to point: `gain_control`'s `as`

"Those creatures" is the set the same spell has just taken, and no selector can
name it once the op has run — by the next sentence the opponent controls none of
them, and "creatures you control" catches everything that was already yours. So
`gain_control` grew the `as` binding four ops already had, written after the
loop like `create_token`'s: it records what control actually *moved*, so a
permanent that left in response, or one that was already yours (which
`change_control` refuses as a no-op), is not one of "those creatures".

### What the sandbox can and cannot see

The authoring verifier never activates an activated ability and declines combat,
so the prohibition itself cannot be demonstrated there — it is pinned in
`tests/unit/test_cant_sacrifice.py` instead, on all three hooks. Call for Aid's
own until-end-of-turn half is unobservable in that sandbox too, and for a reason
worth writing down: the card's `cant_attack_player` clause empties
`combat.legal_attackers`, so `turn._declare_attackers_step` finishes without a
decision, and the declare-attackers stop is exactly what holds `verify.drive`
inside the turn for every other card that grants something until end of turn.
The sandbox therefore rolls through cleanup, and the expectation is measured
after the handback. What it pins is that handback: 32 permanents and 6, not 34
and 4 — a `gain_control` written with the `permanent` duration fails it.
## The batch attack trigger — the declaration, told once per seat it was aimed at

### Overview

Frontier Warmonger: *"Whenever one or more creatures attack one of your opponents
or a planeswalker they control, those creatures gain menace until end of turn."*
Four mana, a 4/4, and that line is the whole card.

Everything after the comma was already sayable — `grant_keyword` with
`keywords: ["menace"]` and its default until-end-of-turn duration. Everything
before it was blocked twice, and the two halves failed for unrelated reasons.

### The trigger: the right shape, with nothing to compare

Two attack triggers existed. `attacks` is per creature and carries `defender`;
`you_attack` is per declaration and carries nothing but the attacker list.

`you_attack` is the right shape. `ATTACKERS_DECLARED` is fired once after the
declaration closes, however many creatures were declared, which is exactly what
"one or more creatures attack" means — and the comment above it in `triggers.py`
says so, having been written to refuse the `attacks` reading: it "is per creature
and would fire three times on a three-creature swing".

But `defending` compares against a key the event has never carried, and
`_defender_matches` returns False the moment it is absent. So the printed card,
written the obvious way, is not approximated — it is **inert**, silently and
forever. And the obvious repair is worse than inert: drop the clause, and plain
`you_attack` with `controller: "any"` fires when an opponent swings at *you*,
handing menace to the creatures you were about to block. That is not a rougher
Frontier Warmonger, it is a card that helps the wrong player in ordinary
two-player play.

### A new event, not a second copy of an old one

`EventType.CREATURES_ATTACKED_PLAYER` is fired by `finish_attackers` once per
distinct value of `combat.attackers`, between the single `ATTACKERS_DECLARED` and
the per-creature `ATTACKS` — coarser than a creature, finer than a declaration.
It carries `defender` and the **subset** of attackers declared against that seat.

The tempting cheaper move is to fire `ATTACKERS_DECLARED` itself per defender and
give it a `defender` key. It is wrong in two places at once: that event means "the
declaration closed" and there is exactly one of those per combat, so Clavileño's
"whenever you attack" would pay twice on an attack split between two opponents,
and the client would be told the attack was declared twice — `attackers_declared`
carries the "Attack!" banner and the surge animation. The pair is instead the
same shape as `BECAME_BLOCKED` and `ATTACKED_UNBLOCKED`: one instant, two facts,
told separately because cards ask for them separately.

`controller` stays the **attacking** side and `defending` is the seat attacked;
Frontier Warmonger asks both, and `controller: "any"` is load-bearing rather than
lazy — the creatures attacking an opponent need not be its controller's.

"…or a planeswalker they control" needed nothing. `add_attacker` refuses a
planeswalker whose controller disagrees with the declared defender, so
`combat.attackers[oid]` is the defending *player* in both cases and one
`defending: "opponent"` covers both halves of the printed line.

### "Those creatures": one line of plumbing, and one that mattered

The set was already on the event and already had somewhere to go.
`resolve_pool` sends `{"binding": "attackers"}` through `_bound_oids`, which has
accepted a **list** of oids since devour. What was missing was `attackers` in
`EVENT_BINDING_KEYS`, so `event_bindings` dropped it on the floor and no effect
could see it.

The half that is not plumbing is *which* set. It is the per-defender subset, not
the whole declaration: a pod attack split between two seats is one declaration and
two abilities, and the whole list would grant menace to the creatures attacking
the Warmonger's own controller.

`{"zone": "battlefield", "attacking": true}` is the near miss and says something
strictly larger — `attacking` is a bare boolean with no notion of whom, and
`selector_keys` has no defending-player key at all. `{"binding": "subject"}` is
the other and is a single oid, which is the per-creature reading this card does
not have.

### Where it is refused

`loader.py` accepts `defending` on `attacks` and on `creatures_attack_player` and
nowhere else. The guard already existed in one direction (silently ignoring the
clause would ship a card that reads "attacks you" and fires on everything); the
list makes it work in the other, which is the failure this capability is named
after — a card that reads "attacks one of your opponents" and fires never.

### The frontend

Deliberately silent in both `labels.ts` and `events.ts`, and listed in both rather
than left to their `default` fallthroughs so the decision is visible. The
declaration it accompanies already narrates "You attack" and already plays the
banner; a line and a beat per defending seat would say the same thing again, once
per opponent swung at. Listing it in `SILENT` is also what stops it closing the
declaration run in `planCombat`, which would split one swing into two animations.

### What it unblocks

Frontier Warmonger is one card. The family behind it cannot be faked per-creature
at all, because each member counts or sweeps the batch: "you gain 1 life for each
attacking creature", "deals damage to each of those creatures", "each defending
player divides".
## "That card" — what a delayed trigger is allowed to be about

### Overview

Gilraen, Dúnedain Protector: *"{2}, {T}: Exile another target creature you
control. You may return that card to the battlefield under its owner's control.
If you don't, at the beginning of the next end step, return **that card** to the
battlefield under its owner's control with a vigilance counter and a lifelink
counter on it."*

Rule 603.7: a resolving ability creates a delayed triggered ability, and what it
creates is a *new* ability with no targets of its own. "That card" is therefore
not a target — it is a reference fixed at the moment the delay was created, and
by the time the delay fires the object has changed zones (400.7). The reference
has to be written down, not looked up.

Most of the writing-down had already shipped by the time this run started, which
is worth saying plainly rather than re-deriving:

- `op_delay` has always snapshotted `ctx.bindings` into the `DelayedTrigger`, and
  `turn._run_delayed` has always handed them back to the delayed context. That
  half was never the hole;
- `effect_result_binding` gave `exile` an `as`, so there is now something to
  snapshot — and split `resolve_pool`'s zone default so that a `{"binding": …}`
  keeps *record* semantics with no default zone, which is exactly what a
  reference to an object that has just changed zones needs. The delayed path gets
  that for free: it goes through the same `resolve_pool`.

So the reference itself works, and the run's job was the two things around it.

### What a permanent arrives with

`put_onto_battlefield` had no `counters`. "…with a vigilance counter and a
lifelink counter on it" is one clause about one arrival, and the only op carrying
that clause was `return_from_graveyard` (persist, undying, since forever) — which
does `selector.setdefault("zone", "graveyard")` and therefore cannot reach a card
sitting in exile at all. So the printed sentence had no op that could say it.

Two `add_counters` ops after the move is the near miss, and it is a different
card. The clause is about the *arrival*: if the return reached nothing — the card
left exile in between, so 400.7 makes it a new object the delay is not about —
then no counters go anywhere. A separate op naming the same binding has no such
tie, and would counter a permanent that got back to the battlefield some other
way. `put_onto_battlefield` therefore gained the identical kind-keyed map,
immediately after the move, which is the same enters-with trade
`op_return_from_graveyard` already documents.

The loader half of that was the worse bug. `counters` was validated for *kind*
anywhere it appeared and read by exactly one op, so writing it on any other op
loaded clean, resolved clean, and dropped it. On a keyword counter that is
invisible: nothing is missing on the board, the creature simply does not have
vigilance. `COUNTERS_ON_ARRIVAL_OPS` now names the two ops that read it and the
rest are a load error.

### The trap that is now a load error

The obvious way to write the second half of Gilraen is to point it at the same
target the first half used:

```jsonc
{ "op": "delay", "step": "end_step",
  "effects": [ { "op": "put_onto_battlefield", "objects": { "target": "t1" } } ] }
```

It reads correctly and it does nothing at all, because `_run_delayed` builds its
context with `targets={}`. Nothing is malformed, so nothing said so — the card
returned no creature.

Filling the targets in would be the wrong repair twice over. It invents a
legality re-check no rule asks for on an ability that never targeted; and it
would not even reach this card, since a `target` selector keeps the battlefield
zone default *because* a target really is re-checked (608.2b), and the object a
delay is about has by construction just left the battlefield. So
`_refuse_targets_inside_a_delay` walks a delay's scheduled effects at load time —
however deeply the `target` is buried, since a `may` inside a delay is an ordinary
shape — and refuses it with the working idiom in the message.

### The substitutes, and why each is wrong

`{"zone": "exile", "exiled_with": "self"}` is the one thing that was reachable
before this, and it is **source**-scoped rather than resolution-scoped: it names
every card the permanent ever exiled, so a second activation drags back a card
the first activation already declined. It also needs `until_leaves`, which
declares an O-Ring return this card does not have. `snapshot` binds a dict of
characteristics, not an object anything can move.

A card that means "only if it is still in exile" writes `zone` itself, which is
what stops the delayed return yanking the card back out of a graveyard it reached
in between. The A/B is in the test file: without the clause, it comes back.

**Unblocked one card: Gilraen, Dúnedain Protector**, at the agent tier — the
template tier harvests nothing here (`no template for: {2}, {T}: Exile another
target creature you control…`). She needed two capabilities and this was the
second; `keyword_counters` shipped the half that makes a vigilance counter mean
vigilance, and neither half is worth anything without the other. The verifier
never activates an activated ability, so her expectation is the weak
`{"zone": "battlefield"}` and the real coverage is
`tests/unit/test_delayed_object_reference.py`.
## `multikicker` — the payment already worked; the word was missing

### Overview

Marshal's Anthem: *"Multikicker {1}{W} (You may pay an additional {1}{W} any
number of times as you cast this spell.)"* One gap record asked for it, and the
queue prints the line in eight different costs — {1}, {2}, {B}, {R}, {1}{U},
{1}{G}, {1}{W}.

The interesting part is how little of it was missing. Every moving piece already
shipped, under replicate's name:

| the mechanic | the field that already did it |
|---|---|
| "an additional {1}{W}" | `additional_cost: { "mana": "{1}{W}" }` |
| "you **may**" | `additional_optional` |
| "any number of times" | `additional_repeatable` |
| how many times you did | `Action.additional_times` → `obj.cast_additional` |
| the card reading it back | `{"additional_paid": true}` |

Legality offers one cast line per number of kicks (convoke's shape — the count
changes the price and is the player's), the count is stamped onto the object in
`game._cast`, and an oid survives the zone change onto the battlefield, so a
`self_enters` trigger on a *permanent* reads how many times the **spell** was
kicked. Marshal's Anthem needs exactly that and it worked before this change.

`kicker` is the field with the right name and it cannot do it. Its cast variant
is `mana_cost.plus(kicker)` selected by a **bool** on the action, so it is paid
once, and `{"kicked": true}` answers yes or no and never *how many*.

### So the change is a desugaring, and the point of it is the gate

```jsonc
"multikicker": "{1}{W}"
```

compiles to the three fields above and to nothing else. `CardDef.multikicker`
is read by no engine code at all — it records the *name the cost was declared
under*.

That name is what was actually blocking. `verify.py`'s residual gate asks
whether every printed line is accounted for by something the card really has,
and its list of card-level costs that no ability can claim covered `kicker`,
`ascend`, `emerge`, `evoke`, `cost_reduction`, `devoid` and "as an additional
cost" — none of which match "Multikicker {1}{W}". So a card spelling the
mechanic through the replicate slot **loaded, and played correctly, and was then
rejected on its own first line**. The available workaround was a `noop` ability
whose `text` was the Multikicker line, which is precisely the laundering the
gate exists to catch.

### Extending the gate's claimants is not weakening it

The distinction the rule cares about is between *forgiving a line because a
declared cost claims it* and *forgiving a line because it is inconvenient*. This
is the first, and it is held to a higher bar than the exemptions already there:

- it fires only when `card.multikicker` is set, which the loader does **only
  after** desugaring the cost into working machinery — the word cannot be
  declared without the mechanic;
- the loader refuses a `multikicker` no effect reads via `additional_paid`. That
  is `kicker`'s half-a-cost guard, which `additional_cost` deliberately does not
  have ("sacrifice an artifact" is the whole of Deadly Dispute's cost) — but
  "any number of times" only means something to a card that counts the times;
- the printed symbols must be the symbols charged, compared on the *parsed*
  cost. `multikicker: "{1}"` cannot claim a printed "Multikicker {2}{R}", and a
  cost that will not parse fails closed and stays residual. No existing cost
  exemption checks this;
- and it claims one line. The following sentence is tested on its own and stays
  residual if nothing implements it.

`multikicker` is also added to `fidelity.unimplemented_mechanics`' declared set,
for the symmetric reason: `_MECHANIC_LINE` matches "Multikicker {1}" like any
other declaration, so without it an instant that really has the cost — Comet
Storm — would be reported as missing it.

Two further refusals, both the loader's: a card carrying `multikicker` *and*
`additional_cost` (or either modifier) is refused, because whichever won would be
the card and the other would silently never be charged; and a `{0}` or `{X}`
multikicker is refused, because free-and-repeatable is six kicks for nothing and
X would have to be asked per payment.

### No card was authored

Marshal's Anthem is still blocked, on a capability that is not this one:
`variable_target_count`. Its enters trigger returns "up to **X** target creature
cards", and `TargetModel.count` is `int | Literal["any"]` — `"any"` unbinds the
count from the kicker entirely (an unkicked Anthem would reanimate the whole
graveyard for {2}{W}{W}), and a literal `N` with `optional` means "exactly N or
none", forbidding every size in between. That gap record's other `need` is left
standing.

So `tests/unit/test_multikicker.py` is the only coverage this change has, and it
is written to be: zero, one and several payments; the count read back off a
permanent that has entered; and the residual gate held to both halves of its job
— accepting the multikicker line, and still rejecting a line nothing implements.

---
## A `condition` on a player-wide static was validated, stored, and never asked

### Overview

Verge Rangers: *"As long as an opponent controls more lands than you, you may
play lands from the top of your library."* One gap record, one card — and not a
missing feature. Every piece of that sentence already existed. `condition` is a
static's "as long as…" clause, shipped with Arixmethes and widened with Nimble
Mongoose. `play_lands_from_library_top` is Oracle of Mul Daya's permission.
`max_count_of` is the "an opponent controls more lands than you" comparison, and
`per_opponent_count` had already shipped its static-side twin in `_static_value`
specifically so this clause could be written.

Written, the card would have loaded clean, printed its clause, and passed all six
authoring gates — while granting the permission **unconditionally**.

### One call site is not "the" call site

`_static_active` is the function that asks a static's condition. It had exactly
one caller, `_battlefield_statics`, which feeds only the object-characteristics
pipeline. The eight **player-wide** statics — the `affects_player` ones, which
describe a player and have no object to attach to — were read by four
hand-rolled walks of the battlefield instead, none of which asked:

| reader | effects |
|---|---|
| `characteristics._player_static` | `no_hand_limit`, `play_lands_from_graveyard`, `play_lands_from_library_top`, `reveal_library_top`, `double_land_mana` (and, since `look_at_library_top` shipped, that one too) |
| `characteristics.player_extra_land_drops` | `extra_land_drops` |
| `characteristics.players_freezing_opponent_lands` | `freeze_opponent_lands` |
| `triggers._land_trigger_doublers` | `double_land_triggers` |

The loader was never the problem: `_validate_static_condition` runs on every
static and `condition` is copied onto the compiled ability regardless of effect.
The clause was present in the data the whole time. Nothing read it.

That is the specific failure this codebase refuses everywhere else — an anthem
whose magnitude silently reads 0, a filter key that loads and matches nothing, a
`reveal_library_top` that never reaches a seat. This one runs in the other
direction, which is worse: the card is not weaker than printed, it is *stronger*,
and a permission that is always on looks like a working card from every angle a
gate can see it from.

### The fix is one gate, in one place

`_active_player_statics(state, effect)` — the player-wide twin of
`_battlefield_statics`, yielding `(source, static)` for the active ones only. All
four readers go through it, so the four walks collapse into one and the gate
cannot be added to three of them and forgotten on the fourth.
`_reaches_player` carries the `affects_player` scoping that two of the readers
need; `players_doubling_land_triggers` is new and public purely so `triggers.py`
stops walking the battlefield itself.

The source is yielded beside the static because a condition is relative to the
permanent carrying it: `is_your_turn` and `"you"` mean its controller, and the
`counters` head reads its own counters.

**Gating outside the pipeline is safer, not riskier.** The acyclicity constraint
in `characteristics`'s module docstring — a static may read pipeline inputs,
never pipeline outputs — is what limits the condition language, and it binds
because object statics are gated *inside* `chars`. These readers sit at legality,
payment, trigger collection, serialization and the cleanup step, outside the
fixed order entirely. There is no layer output for a condition to depend on, so
no new leaf and no new constraint were needed; the mirror language is reused
exactly as it stands.

### Nothing was playing wrong

Checked before building: of the fifteen player-wide statics across every shipped
card — Oracle of Mul Daya, Ancient Greenwarden, Vorinclex, Reliquary Tower,
Thought Vessel, Nezahal, Ramunap Excavator, Dryad of the Ilysian Grove, Vampire
Nocturnus, Azusa, Exploration, Aesi — **none carries a `condition`**. So this
changed no card's behaviour; it opened a door that had been painted on.
`TestTheUngatedStaticsAreUntouched::test_no_shipped_card_gates_a_player_wide_static`
asserts that over the real registry, and says in its docstring what to do when
it eventually fails: retire it, naming the card that gated one.

### What it unblocked

**No card.** Verge Rangers is the only card in the queue that needs this, and it
has a third blocker that is a different capability: "You may look at the top card
of your library any time" needs `look_at_library_top`, a *private* continuous
top-card visibility, where the only existing static (`reveal_library_top`) is
deliberately public — `serialize` writes `library_top` into every seat's view, on
the argument that an opponent who cannot see a revealed card is playing against
information they are entitled to. Authoring Verge Rangers without that line would
be the fetchland-template refusal: a cheaper card than the printed one.

So the `conditional_player_static` need is struck from
`data/authoring/gaps/verge_rangers.json` and `look_at_library_top` is left
standing. The engine change ships on its unit test alone.

> `look_at_library_top` has since shipped — see the top of this file. Verge
> Rangers is authored, and it is the first card to carry a `condition` on a
> player-wide static, so `TestTheUngatedStaticsAreUntouched::test_no_shipped_card_gates_a_player_wide_static`
> was retired with it.

### Guarded by

`tests/unit/test_conditional_player_static.py`, and the shape of it is the point:
every claim is asserted in **both** directions, because before the fix the
"granted" half passed for the wrong reason and the "withheld" half was the only
thing that could have caught it. Three test-only cards carry the conditions —
`t_verge_scout` and `t_conditional_ramp` with Verge Rangers' own board-reading
clause, and `t_all_player_statics` with all eight effects gated on
`is_your_turn`, so `TestEveryPlayerWideStatic` walks one reader per effect rather
than trusting that fixing two of them reached the other six. With the gate
removed, seventeen of the thirty-nine fail, including all eight of the
per-effect withhold cases.

## `nth` — "your second card each turn", settled where the trigger queues

### Overview

Prince Imrahil the Fair: *"Whenever you draw your second card each turn, create a
1/1 white Human Soldier creature token."* One printed line, and the whole card.
Forty-seven queue entries print that clause, in all three polarities — "you draw
your second card", "an opponent draws their second card" (Faerie Mastermind,
Black Widow), "a player draws their second card" (Ian Malcolm).

The vocabulary for it looked complete. A `draw` trigger has existed since
Isperia, and `{"cards_drawn_this_turn": "you"}` has existed since Kydele, so the
clause reads as an intervening-if:

```jsonc
{ "event": "draw", "controller": "you",
  "condition": { "cmp": "==", "left": { "cards_drawn_this_turn": "you" },
                 "right": { "const": 2 } } }
```

And the value is *exactly right where it queues*. `primitives.draw_cards` bumps
the tally on the line immediately before it fires the event, so what
`triggers._matches` reads is precisely the ordinal of the draw that just
happened. The card fails at the other end.

### 603.4 asks the question a second time

`stack.resolve_top` re-evaluates a trigger's `condition` on resolution, which is
rule 603.4 and is correct for every intervening-if there has ever been. It is
fatal here, because the thing being asked about keeps moving:

| | tally | |
|---|---:|---|
| draw step | 1 | |
| Divination's first card | 2 | the trigger queues |
| Divination's second card | 3 | matches nothing |
| the trigger resolves | 3 | re-check reads 3 → `skipped="condition"` |

So Prince Imrahil plus Divination, Brainstorm, or any multi-card draw — the
card's *ordinary* line of play, not an edge — produces nothing at all. No error,
no log line saying a token was owed.

Written as `>=` with `max_per_turn: 1` the ability survives the re-check, and
that encoding is right everywhere except one place: a permanent that enters
**after** its controller has already drawn two cards fires on the next draw,
where the printed card is silent for the rest of that turn. That is a real
divergence on a card that is nothing but this trigger, and no gate would catch
it, which is why the gap record filed the capability rather than shipping a
near miss.

Both failures are asserted in the test file rather than described:
`test_the_condition_encoding_makes_nothing` and
`test_the_at_least_form_fires_and_is_wrong`, against `t_nth_draw_condition` and
`t_nth_draw_atleast`, which are the two rejected encodings kept as test cards.

### An ordinal is a fact about the event

The fix is not a value and not a condition. `draw_cards` writes the ordinal onto
the DRAW event as `data["nth"]`, and `TriggerSpec.nth` compares against it in
`_matches` — beside `not_cause`, `counter` and `mana_ability`, all of which have
exactly this standing: asked once, where the ability queues, and never re-asked.
Nothing that runs at resolution reads it, so 603.4 has nothing to re-evaluate.

`nth` is not in `EVENT_BINDING_KEYS`, so the new payload key does not reach a
card's trigger bindings — the collision `zones.move_object` is annotated about.
`serialize._PRIVATE_EVENTS` already redacts a draw's `oid` for other seats and
the ordinal is a count, so nothing new leaks.

The loader refuses `nth` on any event but `draw`, and refuses an ordinal below 1.
The first is the precedent `counter` and `mana_ability` set, and it matters more
on a trigger than on a selector: a restriction that can never apply does not make
an ability that never fires, it makes one that fires on **every** event of its
kind, which is a strictly better card than the printed one. The second is the
same argument from the other side — no draw is the zeroth card of a turn.

### All three polarities came free

`_actor` has always returned `event.player` for `draw`, so `controller` already
named the drawing player. `you`, `opponent` and `any` therefore needed no work
beyond a test each, and `any` counts per player: two seats drawing two cards
apiece queue the watcher twice, because each has a second card of their own.

### Tier A, and nothing below it

No new op, no new `EventType` (the payload key rides on `draw`, which the
frontend already narrates), no new `DecisionKind`, no continuous effect, no API
field. `fire` calls `emit`, so the log gains no new type and nothing under
`frontend/` changed. Five files: the event's documentation, the primitive that
writes the ordinal, the field on `TriggerSpec` and its schema twin, the loader
guard, and the comparison in `_matches`.

### Guarded by

`tests/unit/test_draw_nth.py` — twenty-four tests over seven claims: only the
second card fires it, a draw-two spell fires it exactly once (the reader's
failure), a permanent entering after two draws stays silent, both rejected
encodings fail in the two opposite ways, all three polarities, the ordinal is an
ordinal (`nth: 1` works), the turn boundary, and the load-time guards.

The authoring verifier casts a card and stops — nothing draws a second card in
the fixed position — so this trigger cannot fire there and Prince Imrahil
legitimately asserts `{"zone": "battlefield"}`. No gate was weakened; the
behaviour lives in the unit test, which is where the gap record predicted it
would have to.

**Unblocked one card: Prince Imrahil the Fair**, whose last need this was
(`human_soldier_token` was closed by the `token_pool` run before it). Agent
tier; `--tier templates --retry` harvested nothing (`no template 200`).

**No template was added, and that was measured rather than assumed.** A prefix
template wrapping the existing `SENTENCES` over "Whenever you draw your second
card each turn, …" produces **zero** of the 46 remaining cards: every one of
their remainders is a sentence the template tier cannot say — *create a 2/2 blue
Drake creature token*, *put a +1/+1 counter on this creature*, *this creature
gets +1/+1 and gains first strike*. The prefix would consume its half and then
fail the card anyway, on the all-or-nothing rule, which is dead code wearing a
template's clothes. The 46 stay in the agent tier, where the next
`/author-cards` will now be able to write them.
## Goad — two rules in one word, and both of them "if able"

### Overview

Rule 701.38a: "until your next turn, that creature attacks each combat if able and
attacks a player other than you if able". One printed word, two rules, and the
engine had a wrong version of the first and nothing at all for the second.

The witness is **Taunt from the Rampart** — "Goad all creatures your opponents
control. Until your next turn, those creatures can't block." Its second sentence
shipped with the `cant_block` op; goad was the card's last blocker, and no partial
answer was written, because a Taunt that compelled the attacks without steering
them is a symmetrical Overrun rather than a political card.

### Why neither existing shape could carry it

| | |
|---|---|
| `must_attack` (op) | **One-shot.** `combat.discharge_attack_requirements` clears the flag when attackers lock in — deliberately, because an obligation the creature could not meet is still spent. So its `this_turn` and `next_combat` each compel exactly one combat, where goad compels *every* combat until its goader untaps. It also carries no notion of who goaded, which is precisely the datum the second half needs |
| `attacks_if_able` (static) | The live, unspent form — and a continuous ability on a battlefield permanent, read off `_battlefield_statics`. A sorcery leaves no source to own it; a static's `affects` filter reads only printed characteristics, so it can say neither "those creatures" (the set chosen at resolution) nor "until your next turn" |
| `detain` | Forbids attacking, which is the thing this card demands. The near-miss that would have printed a card contradicting itself |
| nothing | restricted **which** defender a given attacker may pick. `cant_attack`/`attack_forbidden` is all-or-nothing; `block_restriction` restricts blockers |

### Where the mark lives

`GameObject.goaded_by`, a `set[int]` of the players who goaded it. Detain's field,
for detain's reason plus one more.

"Until your next turn" is not a turn *number* — eliminate a player and it moves —
so what is recorded is the player, and `turn._untap_step` clears the marks
belonging to whoever is untapping, in the same breath as detain and the
`until_your_next_turn` block prohibitions. And the second half of goad *needs* to
know who: the restriction is a fact about a pair, not about a creature.

It is a **set** where detain is a single pid, and that is forced by the rule
rather than by tidiness: two opponents may goad the same creature, each clock runs
from its own untap step, and the creature must attack around both. A single pid
would silently drop one of the two obligations and would end both clocks at
whichever untap step came first.

Cleared in three places, and only one of them is hygiene:

- `turn._untap_step` — the clock itself.
- `objects.reset_permanent_state` — 400.7, a permanent that left and came back is
  a new object and is not the creature anybody goaded.
- `sba._eliminate` — and this one is a **fix**. A player who has left never untaps
  again, so an uncleared goad would compel every combat for the rest of the game,
  pointing its restriction at a seat `alive()` no longer offers — an "if able"
  escape that could never fire. (The `detained_by` hole beside it is still a
  different capability's bug.)

Not a `TempEffect`, for the reason `must_attack` is not: `until_eot` is wiped at
cleanup, and a goad is placed on *your* turn and owed on *theirs*, so an
until-end-of-turn goad would be a card that does nothing at all.

### The two readers

Both halves are read **live**, and nothing spends them:

`combat.attack_required` gained a third source beside `attack_compelled` (the
static) and `obj.must_attack` (the op). `discharge_attack_requirements` touches
`must_attack` and nothing else, which is exactly what makes the next combat
compelled too — the property `tests/unit/test_goad.py` pins by granting an extra
combat phase and watching the goaded creature stay compelled while a `must_attack`
creature beside it goes free.

`combat.attack_target_forbidden` gained goad's clause, inside the predicate
`cant_attack_player` built and left open. The three callers — `legal_defenders`,
`legal_planeswalker_defenders`, `add_attacker` — were **not touched again**, which
was the whole point of building the seam that way.

### Goad reaches planeswalkers, and that is the opposite answer

`cant_attack_player` exempts them; goad does not. The two sentences differ in what
they are about:

- "Creatures can't attack **you**" is about being attacked, and attacking somebody's
  planeswalker is not attacking them (506.2) — the Ghostly Prison ruling.
- "Attacks a player **other than you** if able" is about where the attack is
  aimed, and the goader's planeswalker is the goader (701.38b: the requirement is
  discharged by attacking another player *or a planeswalker another player
  controls*).

Read the Ghostly Prison way, every goad on a board with a planeswalker could be
dodged while the log said the requirement had been met. This is why
`attack_target_forbidden` takes `planeswalker` as a parameter rather than
inferring it: the two capabilities want opposite answers from the same predicate.

Because a planeswalker's controller is the defending player and
`legal_planeswalker_defenders` passes it, one membership test in `goaded_by`
covers the seat and the walker together.

### Both "if able" escapes

Goad is two requirements and both are "if able", so neither may ever make a
declaration impossible. There are two escapes and each closes a different hole:

1. **A creature that cannot attack owes nothing.** `attack_required` is the
   requirement AND `can_attack`, so tapped, summoning-sick, detained and
   `cant_attack` creatures are all excused — and so is *every goaded creature on
   somebody else's turn*, which matters more than it looks: without it the goading
   player could never finish their own declaration while an opponent held an
   untapped goaded creature.
2. **With only the goader left, it attacks the goader.** The restriction fires
   only while some other defender is legally attackable, and "other defender"
   counts both attack kinds — another player, or a planeswalker a third party
   controls. `_has_non_goader_defender` asks that question, and it re-enters
   `attack_target_forbidden` on candidates already filtered to non-goaders, so the
   goad clause cannot fire on them and cannot call back: two levels deep, always.
   Asked the other way round — "is any defender legal", through `legal_defenders`
   — it would be a plain infinite recursion.

A consequence worth stating, because it is what keeps `can_attack` untouched: a
goad can never empty the defender list. The restriction only exists while an
alternative does, so `can_attack`'s "has this creature anybody left to attack"
guard stays gated on `attack_restrictions` alone, and the attack mask's hot path
is unchanged in every game that plays neither card.

### The op

```jsonc
{ "op": "goad",
  "objects": { "zone": "battlefield", "controller": "opponent",
               "types": ["Creature"] } }
```

`objects` is required — a goad with no selector goads nobody, and the card would
resolve, log nothing and change no combat (detain's guard, for detain's reason).
`player` is the goader and defaults to the effect's controller, which is every
printed goad.

**There is no `duration` key, and the loader refuses one.** 701.38a has exactly one
clock and it is a player, not a number. Accepting a duration would invite
`this_turn` — which is `must_attack`, a strictly weaker card that looks identical
in a one-combat test and is wrong from the second combat onwards.

### Test

`tests/unit/test_goad.py`, forty cases: the compulsion biting ("Done attacking"
withheld), the mark surviving a declaration that spends a `must_attack` beside it,
the next combat being compelled too, the defender restriction biting per pair, the
planeswalker answer in both directions, both "if able" escapes, the clock ending in
the goader's untap step and not in anybody else's, an eliminated goader's mark
going with them, two goaders as two independent obligations, and the loader guards.

The card's own behaviour gate cannot see any of this: the authoring verifier
**declines combat**, so Taunt from the Rampart legitimately asserts
`{"zone": "graveyard"}` — it is a sorcery, and that is where it ends up. No gate
was weakened; the coverage lives in the unit test, which is where a mechanic's
coverage belongs.

### Server and frontend: nothing

A new op needs neither. Game state is serialized generically by
`engine/serialize.py`, and `GameObject.to_dict` gained a sorted `goaded_by` list
that the client is free to ignore. No new event type, no new decision kind.

### Cards unblocked

**Taunt from the Rampart** — its last blocker. `cant_block` had already closed the
other half.
## Addendum — the phase a spell was cast in, remembered after it has passed

### Overview

**Unbreakable Formation** — "Creatures you control gain indestructible until end
of turn. **Addendum** — If you cast this spell during your main phase, put a
+1/+1 counter on each of those creatures and they gain vigilance until end of
turn." The first line was never blocked; it is an ordinary `grant_keyword` over
`creatures you control`. The second line asked a question the condition language
could not put into words at all: **there was no notion of a phase or a step in
it.** Not a missing key on a known subject — the subject was missing.

`is_your_turn` was the closest thing, and it is wrong twice over, which is why
this is a new key and not a widening of that one.

**It says nothing about the phase.** It compares `state.active_player` to the
source's controller and stops there. A Formation flashed in during your own
combat — the moment people actually hold it for — or in your own end step would
have collected the addendum it is not owed. That is not an edge case; it is the
common case for an instant, and it makes the card strictly better than printed.

**It is evaluated when it is read, not when the spell was cast.** "If you
**cast** this spell during your main phase" is a fact about rule 601: it is
settled the moment the spell is put on the stack, before anybody responded to it
and long before the resolution that asks. A condition that reads `state.step`
answers a different question, and the gap between the two is exactly what the
stack is for.

`has_flag` cannot stand in — it is written by `set_flag` on a permanent's own
object and there is no effect that runs at cast time to write one — and
`zone_is` reports the source's *current* zone, which for any resolving instant is
the stack.

### The stamp

`stack.push_spell` is the single funnel every cast goes through — the hand cast,
the flashback cast, cascade's free cast and suspend's — and it already wrote
`cast_from_hand` there for rebound, for the same reason: that is the only moment
the fact is knowable. Two fields joined it on `GameObject`, beside the
`cast_kicked` / `cast_evoked` / `cast_overloaded` / `cast_from_graveyard` stamps
that record the other cast-time facts:

- `cast_step`, the step the spell was put on the stack in. A `Step`, not a
  `Phase`, because the step is what the state has and the phase falls out of it
  through `STEP_PHASE` — storing the derived half would throw away the ability to
  ask "cast in your end step" later for nothing gained.
- `cast_on_own_turn`, whether the caster was the active player at that moment.
  The **relation**, not a player id: the sentence is about who cast it, that is
  settled at cast time, and a later change of control must not be able to rewrite
  it.

They survive `reset_permanent_state` the way the other `cast_*` flags do, so a
creature spell's own enters trigger can read them after the StackItem is gone.
Nothing ever cast — a token, a permanent an effect put onto the battlefield —
has `cast_step is None`, and every `cast_during` question about it is `False`,
which is the honest reading of a clause about how the card was *cast*.

### The key

```jsonc
{ "op": "if", "condition": { "cast_during": "your_main" },
  "then": [ … ] }
```

The vocabulary is **generated**, not hand-kept: every `Phase` value, plus `main`
for "either main phase", each optionally prefixed `your_` to also require
`cast_on_own_turn`. So `your_main` is addendum, `main` is the same question
without the turn (an opponent flashing something in during your main phase), and
a card cannot name a phase the engine's turn structure does not have. A name
outside the set is a `DslError` at load — `"main phase"` and `"precombat"` are
the tempting misses, and either would match nothing, leaving a card that prints
an addendum with a clause that can never fire.

It is refused in a **cost reduction's** condition, with the four cast-variant
flags `conditional_cost_reduction` already refused there, and it is the worst of
the five. Those read a harmless `False` at pricing time; this one would read a
stale `True`, because a card being priced for its second cast still carries the
stamp from its first.

It is also absent from the static-ability condition mirror, which reads pipeline
inputs for every permanent on every cache miss and has no business asking how a
card was cast.

### Cards unblocked

1 — **Unbreakable Formation**, the only card on the gap record, authored at the
agent tier and its record retired. No template: the residual reader shows even
its *first* line ("Creatures you control gain indestructible until end of turn")
has no template today — Tortoise Formation is queued behind the same sentence —
so a template here would have had to read two general effect clauses and a
back-reference ("each of **those** creatures") to finish one card. Templates are
all-or-nothing and a half-read sentence makes a cheaper card than the printed
one, so the card went through the agent tier instead.

Gate 5 measures the addendum rather than assuming it: the authoring sandbox casts
in the controller's **precombat main phase**, and the expectation asserts that
two permanents of yours carry *both* `indestructible` and `vigilance`. Vigilance
is only reachable through the `if`, so an addendum that failed to fire fails the
gate — the +1/+1 counters land on your creatures rather than on the card itself,
which is the one thing the `counters` expectation key can see, so the keyword the
same branch grants is what carries the claim.
## Damage prevention over a player — a shield with a clock, and the event that was emitted at nobody

### Overview

Selfless Squire: *"Flash. When this creature enters, prevent all damage that
would be dealt to you this turn. Whenever damage that would be dealt to you is
prevented, put that many +1/+1 counters on this creature."*

Two printed lines that only work together, which is why they are one capability
rather than two runs: the shield prevents, the event carries how much it ate, the
trigger reads it back. Either half alone is a card that does nothing — a shield
nothing announces pays no counters, and a trigger with nothing to listen to never
fires.

### The op is not the static of the same name

`prevent_damage` already existed as a **static** — absorb N (702.63a) — and it is
inverted on all three axes this card needs. It is keyed to an **object**:
`characteristics.prevented_damage(state, oid)` takes an object id, walks
`_battlefield_statics` and matches each entry's `affects` against that permanent,
and `static_filter_keys` has no way to name a *seat* at all. It is per source and
per instance **by design** — that clause is what makes absorb 1 printable, since
a creature with it blocked by three 1/1s takes nothing from any of them — which
is not "prevent all damage this turn". And it cannot be spelled `"all"`
regardless, because the loader refuses it without an `amount`.

Worst of all it is a *static*, so it is continuous while its source stands on the
battlefield. A Squire carrying one would prevent all damage to its controller on
every future turn as well, which is Worship-grade rather than a one-turn fog.
`protection` is the engine's other prevention and is likewise per-permanent and
quality-parameterised, and it stops blocking, targeting and enchanting besides.

This is exactly the relationship `cant_block` the op has with `cant_block` the
static, and the same three inversions: the subject, the clock, and who owns it.
So the op installs a `structs.DamageShield` on `GameState.damage_shields`, beside
`block_prohibitions` and `unblockables` and cleared by the same cleanup hook. It
belongs to no permanent, which is the point — the Squire has **flash** and is
flashed in as a surprise blocker, so it may die to the very combat its shield was
for, and Fog leaves no permanent behind at all.

The op modifies nothing when it resolves. It cannot: the damage does not exist
yet. The whole of its behaviour is the record it leaves for `damage_player`.

### The hook it needed did not exist

`damage_player` went straight from the infect branch to
`state.players[pid].life -= amount`. There was no point anywhere in the
player-damage path where a prevention could be consulted — the permanent path has
had one since absorb, and this was its missing counterpart.

The check goes in at the very **top**, above everything, because prevented damage
was *never dealt*:

- no life lost, and no `LIFE_LOST` for "whenever an opponent loses life";
- **no poison** — the sharpest one, and the reason the check is above the infect
  branch rather than inside the `else` beside the life subtraction. A shielded
  player who still took the counters would lose to a fog;
- no lifelink for the attacker;
- no commander-damage tally;
- no `DAMAGE_DEALT`, so the turn ledger's `damage_taken` stays at zero.

Each of those is a separate leak, and each would be a wrong *number* rather than
an error. `tests/unit/test_damage_prevention.py` asserts all five separately.

There is deliberately **no `amount`** on the op, and the loader refuses the key
rather than reading it. Absorb-N over a player — "prevent the next 3 damage that
would be dealt to any target this turn" (Healing Salve) — is a different effect
with a pool that drains and a target that may be a creature instead. Written as a
shield with a number it would load clean and prevent *everything*: a strictly
better card, silently, which is the exact failure the validation pass exists to
catch. `duration` is required for the reason `cant_block`'s is.

### The event had been emitted at nobody

`EventType.DAMAGE_PREVENTED` has existed since absorb and was already emitted at
two sites — and it was unreachable twice over, the same way `ability_activated`
was. Both sites called `state.emit`, which only writes the log and leaves the
trigger bus to the caller, and no name in `TRIGGER_EVENTS` mapped to it, so
`loader.py` rejected `damage_prevented` outright and no card could have
subscribed even if something had fired.

**Adding the mapping alone would have produced a trigger that silently never
fires.** All three sites now `fire` — the same one-word fix the cycling trigger's
"`fire`, not `emit`: emit only writes the log" comment was written for.

One event, two shapes, and it now says which in a `to` key exactly as
`DAMAGE_DEALT` does. Without that scoping the Squire would be paid every time one
of its controller's creatures shrugged off a blocker with absorb, or protection
turned aside a Shock. The subject of the player half is a **player**, so
`damage_prevented` is absent from `OBJECT_SUBJECT_TRIGGERS` and `_actor` returns
`event.player` — which is what makes `controller: "you"` read "damage that would
be dealt to *you*".

The near misses are wrong rather than merely absent. `dealt_damage` is exactly
inverted: prevented damage is damage that was never dealt, so `DAMAGE_DEALT` does
not fire for it and a Squire built on it grows only on the turns its own shield is
**down**. `life_lost` fails the same way and is doubly wrong, since prevented
damage costs no life. And `damage_taken_this_turn` reads zero underneath a working
shield by construction, so the value-key route could not carry "that many" either.

### Not Tier D, but the frontend was still changed

A new `EventType` is the one change that forces frontend work and this is not one
— the type already existed, and `fire` calls `emit`, so switching the two existing
sites adds no new line to the log. Both silent-swallow sites were checked
deliberately anyway, and the **new** site is the one that mattered.

`damage_prevented` had never been narrated in either `labels.ts::describeEvent` or
`events.ts::beatsFor`; both default to silence. That was harmless while prevention
only ever meant absorb, because absorb's residue still prints a `damage_dealt`
line with the reduced number. A shield over a player prints nothing at all: no
life lost, no damage dealt, no board change, so a fogged alpha strike was a turn
in which the log said nothing happened. Both files now narrate the **player**
shape only — the permanent shape carries an `oid` rather than a card id, so there
is no name to put in the sentence, and "a permanent" would be a worse line than
none.

`bun run build`, `bun run lint` and `bun run test` were run: the build is clean,
the 720 unit tests pass, and lint reports the same 183 pre-existing formatting
errors across the same 21 files as on a clean tree, none of them under
`src/logic/`.

### What the gate can and cannot see

The authoring verifier declines combat, so nothing in the fixed sandbox ever
damages a player: the Squire's shield goes up on its ETB and is never tested, and
the card honestly asserts the weak `{"zone": "battlefield"}`. No gate was
weakened to get it there. `tests/unit/test_damage_prevention.py` is where the real
coverage lives — the shield actually preventing, the five things prevented damage
must not do, the counters matching the prevented amount, the shield surviving its
own source's death, the wearing-off at cleanup played through the real turn
structure, and the boundary where the damage is zero and no prevention event is
manufactured out of a hit that was never going to land.

## Ward — the keyword that had to carry a price, and then had to be given away

### Overview

Ward already worked, twice, and neither copy generalised. Vein Ripper's
"Ward — Sacrifice a creature" and `carddef.CLOAK_WARD` (rule 701.61a's cloaked
2/2) are both the same hand-written `becomes_target` trigger, sitting on the
permanent that has it: a `may` routed to `{"binding": "event_player"}` — the
*caster*, not the ability's controller — with a `pay` and a `counter` of
`{"binding": "sid"}` in the `else`. Rhystic Study shipped that shape years ago
and heroic shipped the event.

What could not be written was **Coppercoat Vanguard**: "Each other Human you
control gets +1/+0 and has ward {1}." Two things were missing, and the second is
the interesting one.

**A keyword that can hold a cost.** `KNOWN_KEYWORDS` is
`frozenset(k.value for k in Keyword)`, validated by exact string match, so there
is nowhere in a keyword to put the `{1}` — `proxy.py` says so outright, listing
"Ward {2}", "Protection from red" and "Annihilator 2" as deliberately outside
`Keyword`. Protection had already answered this: it is a **static**, because it is
parameterised, and four unrelated rules ask it a question. Ward is the same
shape, so `{"effect": "ward", "cost": {…}, "affects": {…}}` — one static covering
the printed form (`affects: {"self_only": true}`) and the granted one, differing
only in the filter, exactly as `cant_attack` and `attacks_if_able` already do.

The `cost` is a full `pay` spec rather than a mana string, run through the same
`CostModel` an activated ability's cost is. That is not generality for its own
sake: it is what makes Vein Ripper's sacrifice ward and ward {1} one mechanism at
two prices. A ward with **no** cost is a load error, on `prevent_damage`'s
reasoning about absorb 0 — ward {0} taxes nothing, can never be declined, and
would print on the card while doing nothing.

The trigger is not written by any card, because the reminder text is the *rules*
speaking. `carddef.ward_ability(cost)` builds it, interned one per distinct cost,
so two Humans with ward {1} share one ability object the way two creatures with
flying share one keyword. `CLOAK_WARD` is now `ward_ability({"mana": "{2}"})` —
the twin existed only while the keyword had nowhere to put a price.

### Where the layer sits, which is the design question and has a negative answer

Ward is a continuous effect, so the obvious move is a layer in
`characteristics._compute`, between the keyword grants and the keyword counters,
where 613.1f puts ability-adding effects.

That would be wrong, and not marginally. `_compute`'s fixed order exists to
sequence effects that **feed each other** — `animate` replaces the base P/T an
anthem then adds to, `add_subtype` decides which creatures the next anthem's
filter can see — and it is safe only because every layer reads a pipeline
*input*. Ward reads none of them (its `affects` is matched on printed
characteristics like every static) and produces something no layer can consume: a
**triggered ability**, not a characteristic value. Giving it a position would
assert a dependency that does not exist and would put an `Ability` object inside
`Characteristics`, which is a frozen record of what a permanent *is*.

So it goes where the other statics of its kind already are — beside
`protection_from`, `prevent_damage`, `block_restrictions` and `attack_forbidden`:
read off the battlefield at the moment the rule that wants it runs.
`characteristics.granted_wards` answers for the whole battlefield in one pass,
because its single reader is `triggers._candidate_abilities`, which runs on every
event; with no ward static anywhere — the ordinary board — it walks the statics
once and returns `{}`.

### The claim the whole design turns on

The cheap version is one `becomes_target` trigger on the Vanguard, filtered to
`{"controller": "you", "subtypes": ["Human"], "exclude_self": true}`. It loads
today, with no engine work at all. In a duel it is nearly indistinguishable —
same prompt, same payer, same counter.

It is a different and weaker card. 603.2d fires ward as the removal spell goes on
the stack, which is the entire point of the keyword: the opponent holds priority
with the ward trigger sitting there. If the trigger's **source** is the Vanguard,
killing the Vanguard in that window is an answer to the tax. The printed ability
belongs to the creature being targeted, so it is not.

`_candidate_abilities` therefore yields the ward with the **warded** permanent as
its source, next to the line that does the same for `granted_abilities` and for
the same stated reason. And resolution had to stop asking the board: an ability
looked up through "who has ward right now" would fizzle at exactly the moment the
opponent removed the granter. So rules-supplied abilities are interned under a
**negative `ability_index`**, and `stack.ability_of` answers those first and
without reading any object. That subsumed the cloak special case, which was the
same problem solved once by hand.

`grant_ability` is the other tempting escape and is not one, as `card-dsl.md`
already says: it is an `ops` entry, a one-shot, so from an enters-the-battlefield
trigger it would miss every Human that arrived later and would keep granting
after the Vanguard died.

### Divergence

A face-down permanent is never granted ward. The rules would grant it — 707.2
removes the abilities of the *card*, not ones an effect hands over — but a
static's filter reads the printed face, so "each other Human you control" would
reach through the shell and the ward trigger would announce that the hidden card
is a Human. `_compute` already makes exactly this trade, returning
`FACE_DOWN_CHARS` before any static runs. Cloak's own ward {2} is unaffected: it
comes from the cloak rule rather than from a static.

### What was left alone

Vein Ripper keeps its hand-written trigger. Its ward is already hosted on the
right object, which is the whole defect the new mechanism exists to remove, and
`ward_ability` would build the byte-identical `may`/`pay`/`counter` body — so
re-expressing it swaps one correct spelling for another on a shipped card, inside
a commit about a different one. `t_warded` in the test pool keeps its by hand for
a better reason: it is the control that says the two paths behave the same.

### Test

`tests/unit/test_ward.py` — 28 tests. The scope of the filter and its wearing-off
read through `characteristics.ward_abilities`; the tax, the refusal and the
payment are played on a real stack; `TestTheGranterIsNotTheSource` casts a second
removal spell at the Vanguard while the ward trigger is on the stack and asserts
the tax is still collected afterwards. `tests/unit/test_cloak.py` is unchanged and
still passes, which is the check that re-expressing `CLOAK_WARD` changed nothing.

### Cards unblocked

Coppercoat Vanguard. The template tier harvests none of them —
`templates._keywords_in` refuses any parameterised keyword by design, and teaching
it "Ward {N}" would still only reach cards whose *every* other line a template
already reads.
## "Can't be blocked" — the same wire, read from the attacker's end

### Overview

`cant_block` shipped as an op one run ago: a one-shot, table-stored "that creature
can't block", aimed at a would-be **blocker**. Rogue's Passage prints the opposite
sentence — "{4}, {T}: Target creature can't be blocked this turn" — which names an
**attacker** and refuses every blocker against it. The two meet in
`combat.can_block(state, blocker, attacker)` and nowhere else, so this is the same
storage shape keyed on the other creature: `GameState.unblockables`, a list of
`structs.Unblockable`, read by `combat.unblockable`.

Neither predicate consults the other, which is the whole of how they compose. A
creature that is prohibited from blocking still cannot block an ordinary attacker;
an unblockable attacker is still unblockable by creatures under no prohibition;
and a creature that is both is refused by whichever early-out `can_block` reaches
first, which is the same answer. `tests/unit/test_unblockable.py` pins all three,
including the lift-one-and-the-other-still-bites case that a merged implementation
would fail.

### Why the existing machinery could not say it

The engine's other "can't be blocked" is the `block_restriction` **static**
("this creature can't be blocked by Humans", `characteristics.block_restrictions`
off `_battlefield_statics`). It is wrong three ways over, and each one alone would
have been survivable:

| | |
|---|---|
| it needs a permanent | a static is on while its source is on the battlefield. Rogue's Passage can be sacrificed or destroyed in response to its own ability, and the creature stays unblockable — `TestItOutlivesItsSource` |
| it has no clock | "this turn" is not expressible as "while I am here" |
| its filters read printed characteristics | `static_filter_keys` has no key meaning "the creature this ability targeted", and Rogue's Passage may target *any* creature, including an opponent's |

`grant_ability` cannot smuggle one onto the target either: granted abilities are
pointers read by `triggers.py` alone, and `_battlefield_statics` never consults
them, so a granted `block_restriction` loads clean and does nothing at all. And
every available evasion **keyword** — menace, fear, intimidate, skulk, shadow,
horsemanship, the landwalks — is a condition on *which* creatures may block.
Granting one is an approximation of a printed line, which is a different card, so
the brief refused them and so does this.

### One form, not two

`cant_block` takes exactly one of `objects` and `all_creatures: true`. This op
takes `objects` only, and the asymmetry is deliberate rather than unfinished
work: no printed one-shot makes an unrestricted *everything* unblockable. The
plural forms that come close are controller-scoped — "creatures you control can't
be blocked this turn" (Keeper of Keys, Glaring Spotlight) — and a global sentinel
would read those as making the opponent's creatures unblockable too, which is a
strictly better card. So the loader refuses an `unblockable` with no `objects`
rather than guessing, and those cards stay unexpressible until somebody stores the
*filter* instead of the oids. `make_unblockable` refuses an empty set for the same
reason `forbid_block` does: a declined "up to one target" makes nobody
unblockable.

### The clocks, and the shared expiry

The same pair `cant_block` takes, cleared by the same two hooks in the same
breath: `this_turn` in `turn._cleanup_step`, `until_your_next_turn` in
`turn._untap_step`, keyed by **who** granted it because eliminating a player moves
everybody else's "next turn". `sba._eliminate` drops a departed seat's entries for
the reason it drops their block prohibitions — they never untap again.
`until_your_next_turn` is not speculative: Sly Instigator prints it.

The two clear-ups now share one helper, `primitives._expired`, because they are
the same rule over two lists shaped alike. `test_the_block_prohibition_clock_does_not_clear_this_one`
is what catches a future merge of the two tables.

### The card, and where its coverage actually lives

**Rogue's Passage** (agent tier — `--tier templates --retry` harvests nothing:
0 written, 200 no template). Its interesting line is an *activated* ability, and
the authoring verifier never activates one and never declares a combat, so the
card honestly asserts the weak `{"zone": "battlefield"}` expectation and the real
coverage is in `tests/unit/test_unblockable.py`: the ability is activated for
{4} and its target is then offered no blockers at all, the source is recorded and
is not the target, an opponent's creature is a legal target, and the grant is gone
next turn.

### Server and frontend: nothing

No new event, decision kind or API field. Unblockability shows up as an
`ADD_BLOCKER` action that is not offered, and `LegalActionDTO.kind` is a bare
string the client echoes back.
## At end of combat — the one delay step that is not once a turn

### Overview

Flamerush Rider — "Whenever this creature attacks, create a token that's a copy
of another target attacking creature and that's tapped and attacking. **Exile the
token at end of combat.**"

`Step.END_OF_COMBAT` has existed since the turn structure was written and the
turn has always walked through it. Nothing could ever be attached to it:
`turn.DELAY_STEPS` named `upkeep`, `draw_step`, `begin_combat` and `end_step`,
and `delay`'s step is matched against that table alone, so
`{"step": "end_of_combat"}` was a load error. One entry in one dict fixes the
first half.

Substituting the nearest reachable step is not an option, and this is the card
that shows why. A token exiled at the **end step** survives the whole postcombat
main phase: it can be sacrificed for value, tapped for an ability, or — since
`extra_combat` shipped — attack again in a second combat. The printed line exists
to stop exactly that, and a card that stopped none of it would play like a
different, better card, with nothing on screen saying so.

### Which combat, and why the question is new

The other four delay steps happen once a turn, so naming the step is the whole of
naming the moment. A combat phase does not, and that changed the week
`extra_combat` landed: Relentless Assault, Combat Celebrant, Aggravated Assault
and Seize the Day all give a turn two or three combat phases, and
`Step.END_OF_COMBAT` is re-entered by every one of them.

So the semantics are decided rather than inherited. "At end of combat" means
**the end of the combat the delay was created in** (603.7), and — for one created
in a main phase, an upkeep, or the end of combat step itself, where there is no
combat to belong to — the end of the next combat to begin.

`CombatState` cannot say which combat that is: `combat.end_combat` throws it away
as the END_OF_COMBAT step begins, and that runs *before* `_run_delayed` reads
anything. So the identity is a number that outlives the phase —
`GameState.combat_number`, incremented by `combat.start_combat`, the one place a
combat begins. `op_delay` stamps it onto the `DelayedTrigger`:

```python
return state.combat_number if state.combat is not None else state.combat_number + 1
```

and `turn._delay_due` compares it against the combat that is ending now. Only
`end_of_combat` carries a stamp; the four older steps compare on the name alone
and are byte-for-byte unchanged.

Monotonic for the whole game rather than reset per turn, so a number is never
reused. A delay scheduled in a postcombat main names "the combat after this one",
which may be an extra combat later this turn or the first one next turn — and
either way is the same integer, with no second field saying which turn it meant.

### What the stamp changes today: nothing observable

Worth saying plainly, because the diff invites the question. In the turn machine
as it stands, "the combat it was created in" and "the next END_OF_COMBAT step to
come round" are the same step, always. Every combat that begins reaches its own
end of combat step before any later one begins — including a combat nobody
attacked in, which `turn.next_step` routes straight from declare-attackers to
END_OF_COMBAT — and `_run_delayed` runs after `begin_step` for the current step,
so a delay created during a combat cannot be seen by a step that has already gone
by. A bare step-name match would pick the same moment in every reachable line of
play.

The stamp is what makes that a *statement* instead of a coincidence. It is the
difference between an exile timed to a combat and one timed to whichever end of
combat step arrives next, and only the first stays right if anything ever ends a
combat phase early. `TestTheStampIsAGuard` in `tests/unit/test_end_of_combat.py`
is that invariant, asserted on `_delay_due` directly, because it is the half no
card can demonstrate.

### The card

**Unblocked one card: Flamerush Rider.** Its other need,
`effect_result_binding`, was closed by an earlier run — `copy_permanent` takes an
`as` that records the oids it made, so "the token" is nameable and `delay`
snapshots `dict(ctx.bindings)` when it schedules, which carries the record to
whatever step the exile is scheduled for. Everything else was already shipped
vocabulary: "another target attacking creature" is a `permanent` target with
`{"attacking": true, "exclude_self": true}`, `copy_permanent` already took
`tapped` and `attacking`, and dash is the `evoke` + `evoke_label` mechanism whose
price guard a sibling run had already relaxed for dash costs that exceed the
printed line.

Authored in the **agent tier**. `--tier templates --retry` harvested nothing:
`templates.py` has no reader for "create a token that's a copy of another target
attacking creature", and writing one for a single card would be a template that
half-reads a sentence.

The behaviour gate declines combat in its fixed sandbox, so the attack trigger
never fires there and the card honestly asserts the weak `{"zone": "battlefield"}`
fallback that Combat Celebrant and every other attack-triggered creature asserts.
The real coverage is `tests/unit/test_end_of_combat.py`, which plays the card
through a turn with two combats and checks each copy against the end of the
combat that made it.
## `ability_activated` — the event that was already being emitted at nobody

### Overview

Harsh Mentor: *"Whenever an opponent activates an ability of an artifact,
creature, or land on the battlefield, if it isn't a mana ability, this creature
deals 2 damage to that player."* One printed line, and the whole card.

`EventType.ABILITY_ACTIVATED` has existed since activations did, and `game.py`
emitted it from **both** activation paths. It was still unreachable, twice over:
both sites called `state.emit`, whose own docstring says it *only records* and
leaves the trigger bus to the caller, and no name in `TRIGGER_EVENTS` mapped to
it, so no card could have subscribed even if something had fired. A log line with
zero listeners — the same silent no-op the cycling trigger's `fire`, not `emit`
comment was written for, three lines further down the same method.

**Not Tier D.** A new `EventType` is the one change that forces frontend work,
and this is not one: the type already exists and the frontend already narrates
it. `labels.ts::describeEvent` has `case "ability_activated"` and `events.ts::
beatsFor` gives it a 320ms beat with a neutral flash on the source. Firing rather
than emitting adds no *new* event type to the log either — `fire` calls `emit` —
so both silent-swallow sites were checked deliberately and nothing under
`frontend/` was touched.

### "if it isn't a mana ability" had no vocabulary at all

The clause is an intervening `if`, and `condition` cannot express it. Every
condition key — `cmp`, `exists`, `zone_is`, `has_flag`, the rest — asks about the
board or about the trigger's own card. None can ask a property of *the ability
that fired*.

`TriggerSpec.filter` cannot substitute either, and this is the part worth being
precise about: it runs through `matches_card_filter` against the **source
permanent's printed face**. The permanents the clause exists for are exactly the
ones carrying both kinds of ability:

| | |
|---|---|
| Bant Panorama | `{T}: Add {C}` and `{1}, {T}, Sacrifice this land: Search…` |
| Azorius Signet | `{1}, {T}: Add {W}{U}` |

An Artifact and a Land, both squarely inside "an artifact, creature, or land",
and the right answers are opposite. Dropping the clause does not approximate
Harsh Mentor, it replaces it: every land in a real game taps many times a turn,
and a 2/2 that pings each one is Manabarbs.

So the flag rides on the event. Both activation paths set `mana_ability`
(`_activate` false, `_activate_mana` true) and `TriggerSpec.mana_ability`
compares against it in `_matches`, beside `not_cause` and `counter`. The loader
refuses it on any other event for the same reason it refuses `defending` there:
a restriction that can never apply looks like the printed clause and is not one.

**Firing on the mana path was the call.** The alternative the gap record allowed
— keep emitting there, never fire — passes every test in this file for the wrong
reason: with nothing listening, `mana_ability: false` would be a guard that never
runs, and a card author writing `ability_activated` with no restriction would get
non-mana-only behaviour by accident. `test_and_the_event_still_fired` is the test
that pins the difference: the event must be in the log *and* the trigger must be
absent.

The remaining incompleteness is pre-existing and documented rather than fixed:
the mana abilities the payment solver taps for itself go straight through
`costs.pay_mana` → `activate_mana_ability` and emit nothing at all, so
`mana_ability: true` sees only mana abilities activated by hand. Moving the
emission into the primitive would put an animated log beat on every land
auto-tapped to cast a spell, which is a UI change, not this capability.

### Before the cost, not after

The emission used to sit after `stack.push_activated_ability`. Moving it to
before `pay` is not cosmetic and it is what makes the printed sentence true: a
cost that **sacrifices the source** — a Panorama, a fetchland, Mind Stone — has
already moved it to a graveyard by the time the ability is on the stack, so a
listener asking "was it on the battlefield?" would be told no about precisely the
activations Harsh Mentor is printed to punish. Rule 602.2b puts the announcement
before the payment anyway, and `turn_ledger.activated` at the top of the same
method already takes that reading out loud.

The ordering that matters is unchanged: triggers queue and go on the stack at the
next priority (603.3), which is after the push either way, so a trigger this
wakes still lands on top of the ability that woke it. The `sid` field is gone
from the payload — it does not exist yet at that point — and nothing read it.

### Two filter keys that loaded and did nothing

`zone` and `any_types` were already legal `SELECTOR_KEYS`, so `validate_selector`
accepted them on a trigger filter and `matches_card_filter` then ignored them —
the silently-wider filter that the `not_supertypes` comment in the same function
is annotated about. Harsh Mentor needs both, in the narrowing direction:

- `types` is a **conjunction**, so "an artifact, creature, or land" written with
  it asks for a permanent that is all three and matches nothing. `any_types` is
  the any-of form `selectors.matches` has had since Acidic Slime.
- Without `zone`, the card fires when an opponent **cycles** a land card out of
  hand: an activated ability of a Land card, so every printed characteristic the
  filter reads says yes and only the zone says no.

No shipped card used either key on a trigger, so nothing changed underneath.

### The effect half needed nothing

`event_bindings` has always seeded `event_player` from `event.player`, and
`select_players` has always accepted `{"binding": …}`. So "that player" is one
`damage` op, and it is multiplayer-correct rather than collapsing to
"each opponent" — `test_the_damage_follows_the_activating_player_in_a_pod` is a
four-player board where exactly one seat loses life.

`_actor` returns `event.player` for this event rather than the subject's
controller, and the two really do come apart: an opponent activating an equip on
a creature **you** control is their activation of their ability on your
permanent, and the printed line says that triggers.

### Guarded by

`tests/unit/test_ability_activated_trigger.py` — fourteen tests over four claims:
the event reaches the bus at all (including a land's ability, which is why
`spell_cast` could never stand in), mana abilities are excluded while still
firing the event, the `controller` clause reads the activating player, and the
filter's two halves. The authoring verifier never activates anything — it casts a
card and stops — so this trigger cannot fire in the fixed sandbox and Harsh
Mentor legitimately asserts `{"zone": "battlefield", "battlefield_count": 33}`.
No gate was weakened; the behaviour lives in the unit test, which is where the
gap record predicted it would have to.

**Unblocked one card: Harsh Mentor**, whose only need this was. Agent tier;
`--tier templates --retry` harvested nothing (`no template 200`), as expected —
no template reads this sentence.
## Commander mana value — the number that lives in the zone nothing looked at

### Overview

**Visions of Glory** — "Flashback {8}{W}{W}. This spell costs {X} less to cast
this way, where X is the greatest mana value of a commander you own on the
battlefield **or in the command zone**." `conditional_cost_reduction` had already
built the rider's slot: a `mana_reduction` on the flashback cost node, read by
`costs.variant_reduction` so the printed hand cast keeps its price. What was
missing was the number, and it was missing three times over.

**It was a maximum, and every shape was a sum.** `costs.reduction_amount` took
`{"amount": N}`, `{"count": filter}` and `{"total_power": filter}`. The two that
read a board add over their matches, so "the *greatest* mana value of a
commander you own" written as either gives a player with two partner commanders
their mana values **added together** — a different and larger discount, on a card
that reads as though it were right. Max and sum are not the same operation and no
filter turns one into the other, so `greatest_mana_value` is a fourth arithmetic
key rather than a filter on an existing one.

**It could not see the command zone.** `costs._reduction_matches` walked
`state.battlefield` and nothing else, and read `controller`, `types` and
`subtypes` — `is_commander` was not even one of the keys it honoured. So a
reduction written about a commander read zero for most of a normal game, because
the command zone is where a commander sits for most of a normal game. Silently:
a nine-mana sorcery that should have cost four, offered at nine, with nothing on
screen to say why.

**And none of it could go through the effect language.** `value_keys`' `max`
takes a fixed list of expressions written into the card, not a maximum over a
selected pool; `mana_value_of` resolves a ref rather than a selector; and
`selectors.resolve_pool` builds its pool from exactly one `zone`, so no selector
spans the battlefield and the command zone even with `any_of`, which narrows
candidates and never widens where they were drawn from. All moot anyway: a
reduction is priced by `legality`/`game` before the spell is on the stack, where
there is no `EffectContext` to evaluate a value expression in. This is a
pricing-time value and it belongs in `costs.py` beside the other three.

### The shape

```jsonc
"flashback": {
  "mana": "{8}{W}{W}",
  "mana_reduction": {
    "greatest_mana_value": {
      "is_commander": true, "owner": "you",
      "zone": ["battlefield", "command"]
    }
  }
}
```

Three things widened, all inside `costs._reduction_matches` and its validator:

- **`zone` may name a list.** One pool with one maximum over it, rather than two
  filters producing two maxima that something then has to combine. The zones it
  may name are the battlefield and the command zone — the two
  `_reduction_zone_oids` walks — because both are public and both are readable
  before anything is on the stack. Anything else is a load error rather than a
  filter that matches nothing for ever. The command zone is per-player, so every
  seat's is concatenated and the ownership keys narrow it.
- **`is_commander` is honoured.** It was already a legal key to *write* — it is in
  `STATIC_FILTER_KEYS` — and it was silently ignored, which is the worst of the
  three states. It is also the only thing separating a general from the identical
  legend somebody else cast.
- **`owner` joins `controller`.** The printed word is "own", and the two part
  company on exactly the boards commanders are played on: in the command zone
  they agree, and on the battlefield a commander an opponent has stolen is still
  one you own and still counts. `controller` therefore defaults to `"you"` only
  while the filter has said nothing about ownership — a defaulted control check
  on top of an `owner` filter would drop precisely the case `owner` was written
  for — so every reduction written before this change still means what it meant.
  `owner` is deliberately **not** a static-filter key: a static applies to
  permanents, where control is the question.

The mana value is read off the **printed card** through `state.card(oid)`, because
a commander in the command zone has no board state to read it from; `max(...,
default=0)` makes "no commander" a real answer rather than a missing one, and the
player who has none pays the price the card prints. Types and subtypes come from
`chars` on the battlefield and from the printed face anywhere else, since no
continuous effect applies to a card in the command zone.

`total_power` stays battlefield-only however the zone list is written: power is a
characteristic of a permanent, a card in the command zone has none, and summing
its printed face would answer a question the characteristics pipeline was never
asked.

### What it unblocked

**Visions of Glory**, both lines and the last card of its gap record. Sentence one
is `create_token` with a `{"creatures_you_control": true}` amount; sentence two is
the flashback node above.

Its flashback cast cannot be observed in the authoring sandbox — that position
designates no commander for player 0, so the reduction there is honestly 0 and the
expectation is what the card does on a plain hand cast (two creatures, two Human
tokens, `battlefield_count` 34, `zone` `"graveyard"`). Not a weakened gate: the
sandbox has no commander to be greatest, and asserting one would be asserting a
position that does not exist. The pricing coverage lives in
`tests/unit/test_commander_mana_value.py` instead — the command zone, the
battlefield, the maximum against the sum, ownership against control, the
`is_commander` gate, and the offer-and-charge agreement across
`legality._cast_variant` and `game._cast`.

## Dash — the alternative cost that is allowed to cost more

### Overview

Dash needed no engine work and still needs none. `docs/keywords.md` has called it
*free* since the census and `tests/unit/test_dash.py` cashes that claim rather
than asserting it: `evoke` is not "the evoke keyword", it is the mechanism evoke,
dash and blitz share — an alternative mana cost that replaces the printed one,
offered from hand only, plus a flag the card reads back with `{"evoked": true}`.
`evoke_label` is what the card calls that cost on screen; `grant_keyword` gives
the haste; `delay` with `step: "end_step"` schedules the return.

What had no home was a **price**. The loader refused any `evoke` cost that was
not strictly cheaper than the printed one:

```
DslError: riders_of_rohan: evoke '{4}{R}{W}' is not cheaper than the printed cost
```

Riders of Rohan is printed `{3}{R}{W}` and dashes for `{4}{R}{W}` — one mana
*more*. So the card did not load at all, and the whole of the gap was that one
comparison.

### The guard was right, about evoke

Its stated reason is sound and worth keeping: *an alternative nobody would take is
dead weight that reads as a mechanic*. That argument is about the discount. Evoke
buys nothing else with the price — a Mulldrifter evoked is a Mulldrifter that
dies — so an evoke cost above the printed one is a line no player ever takes, and
a card offering it looks implemented while being one line short.

Dash buys something. The extra mana buys haste, and the enters trigger for a turn,
before the body goes back to hand: two Human Knights this turn and a 4/4 that
attacks immediately, for one more mana than the 4/4 alone. That is a trade
players take, and Riders of Rohan is printed on the assumption that they do.

### What the guard reads now

Two comparisons where there was one, split on `evoke_label`:

| | |
|---|---|
| **equal** to the printed cost | refused under *every* label. Two lines at one price is the same cast offered twice, and the second is dead weight however it is worded — this is the shape the original guard existed for that no keyword can excuse |
| **more** than the printed cost | refused only when `evoke_label` is its default `"evoked"`. Evoke keeps its discount-only invariant exactly as before, with the original message |
| **more**, under a renamed label | allowed. The card has said out loud, in the action list and on screen, that it is not evoke |

`evoke_label` was cosmetic until now, and making a display string load-bearing was
the deliberate part of the call. It is the honest discriminator available: the
label is the card's own statement of which keyword it prints, it is the same
string the player reads on the cast line, and a card that renames the cost to dodge
the guard has to lie visibly to do it. `src/automtg/cards/schema.py` records that
the field is no longer only for the screen.

### The three shapes that were rejected before this one

| | |
|---|---|
| A blanket relax to `>` | The gap record's first suggestion, and a regression dressed as a fix: a typo'd evoke cost — the actual authoring error, printed `{2}{U}` and evoke `{5}{U}` — would then load clean and offer a line nobody takes. A guard that permits anything is not a relaxed guard |
| A `dash:` field of its own | Duplicates the entire `evoke` machinery to write the same `cast_evoked` flag, then needs mutual-exclusion guards against `evoke`, `emerge` and `bestow`, and blitz would want a third copy tomorrow. `evoke_label` already exists precisely because these are one mechanism under three words |
| `alternative_cost` | Closed twice over. The loader refuses it without a `condition`, and dash has no condition to invent; and it deliberately sets `Action.alternative` rather than `cast_evoked`, which nothing reads back — so "If you do, it gains haste…" could not be gated at all and would fire on every cast, which is a different card |

`kicker` points the wrong way (additive: a kicked cast would be `{3}{R}{W}` *plus*
the dash price), and `emerge` may not coexist with `evoke` and has no fixed price.

### Guarded by

`tests/unit/test_dash.py`, which already held the mechanism down and now holds the
price too. `t_dear_dasher` in `tests/data/testing.cards.json` is Riders' shape at
test scale — printed `{2}{R}`, dash `{3}{R}` — and the tests assert the dearer line
is *offered*, costs four lands rather than three, and still reaches the same
`evoked` flag the cheap one does, because loading is not the claim. Alongside it
`TestThePriceGuardStillCatchesDeadWeight` pins both errors the guard must keep
catching: a dearer evoke proper, with and without the label written out, and an
equal price under either label. `tests/unit/test_evoke.py`'s existing
`test_an_evoke_cost_that_is_not_cheaper_is_refused` is unchanged and still passes
on the original message.

**Unblocked one card: Riders of Rohan**, whose only remaining need this was.
Agent tier, all six gates; `--tier templates --retry` harvested nothing
(`no template 200`), as expected — no template reads a Dash line. The sandbox
casts the printed cost, so `cast_evoked` is never set there and the card
legitimately asserts the ETB half only: `{"zone": "battlefield", "tokens":
{"id": "human_knight_2_2_r_trample_haste", "count": 2}, "battlefield_count": 35}`,
the same three numbers Grave Titan asserts for the same shape. The dash half is
witnessed by the unit test instead.
## A counter for each — widening one field, not adding a mechanism

### Overview

"Éomer enters with a +1/+1 counter on it for each other Human you control."

The mechanism this needs already existed and was already the right home.
`self_enters_with_counters` is a `replacements` entry; it is what Mossborn Hydra
uses for its fixed "enters with a +1/+1 counter on it", and what
`loader._replacements_with_loyalty` compiles a planeswalker's starting loyalty
into. What was missing was one type: `ReplacementModel.amount` was `int = 1`
under a `Strict` model config, so a value expression was a validation error and
**only a constant could be printed**.

There is no honest constant for "for each other Human you control" — it is 0 on
an empty board and unbounded in play — so the clause could not be written at all.
Three edits close it:

- `cards/schema.py`: `amount: int | dict[str, Any] = 1`.
- `cards/loader.py`: a `validate_value` pass beside the existing
  `validate_condition`, on both spellings of the clause.
- `engine/zones.py`: `evaluate_value` instead of `int(...)` at the two
  `add_counter` calls.

### The evaluation context was already sitting there

`zones._enter_battlefield` evaluates each entry's `condition` with
`controller=obj.controller, source=obj.oid`, on the board the permanent is
arriving on — that is what makes a slowland's "unless you control two or more
**other** lands" count the right number. The amount wants exactly that context
and nothing else, so it is one `EffectContext` built from the same two fields:

- `_add_to_zone` runs before `_enter_battlefield`, so the permanent is already on
  the battlefield when its own amount is counted. `exclude_self` is therefore
  load-bearing rather than tidy — without it a lone Éomer counts himself and
  enters as a 3/3.
- An oid survives the zone change onto the battlefield, so Converge works from
  here with no further change: `colors_of_mana_spent` reads `obj.colors_spent`
  off `source_oid`, which is the same object that was on the stack.
- A zero count leaves *no* counter, because `GameObject.add_counter` pops a kind
  whose total is not positive. An inert `{"+1/+1": 0}` tally would be visible to
  `counters_on` and to proliferate.

### Why not a trigger, which is the obvious substitute

An enters trigger running `add_counters` compiles today and needs nothing. It is
a different card three ways, and on Éomer the difference is load-bearing rather
than academic:

1. **614.1c.** It is a replacement, so the permanent is never on the battlefield
   without the counters. The trigger form lands a 2/2 and grows it later, and
   anything that looks in between — another enters trigger, a static, a
   state-based action — sees a creature the printed card never is.
2. **Trigger order is the controller's.** Éomer's third printed line deals damage
   *equal to its power*. With the counters arriving from a second simultaneous
   enters trigger, the card's whole payload would depend on which of the two its
   controller happened to order first: 2 damage, or 2 + N, from printed text
   containing no such choice.
3. **The event.** `add_counters` fires `COUNTER_PLACED`; the replacement route
   calls `add_counter` directly and fires nothing. The substitute would wake every
   `counter_placed` watcher on the board.

`tests/unit/test_variable_enters_with_counters.py` carries `t_marshal_trigger` —
the substitute written out as a card — so claims 1 and 2 are observed rather than
argued. `move_object` is driven directly there, because the game loop resolves
straight through the moment the difference exists in.

### Both spellings, or neither

`zones._enter_battlefield` reads whichever of two shapes is present: the
top-level `counter`/`amount` pair, and `modify: {"counters": {kind: amount}}`.
Widening only the first would leave half the DSL taking constants with nothing
to say so, so both are validated and evaluated as values. That is one mechanism
with two syntaxes, not two capabilities.

### What it unblocks

One card authored now: **Éomer, King of Rohan** — his last blocker, since the
monarch run shipped `become_monarch` with a player selector and his "target
player becomes the monarch" needed exactly that.

`data/authoring/queue.json` defers thirty-nine more on "enters with a … counter
on it for each …" — Diregraf Colossus, Gatekeeper Gargoyle, Golgari Grave-Troll,
Kinsbaile Borderguard, Squad Captain, Ulasht, Verazol and the whole Converge
cycle. **No template was added**, so they stay in the agent tier rather than
being harvested here. Three reasons, and the third is the real one:

- The printed sentence is not one phrase family but four — a board count, a
  graveyard count, a per-turn tally ("for each creature that died this turn") and
  Converge — under three different ability-word prefixes and a counter-word
  multiplier ("two +1/+1 counters ... for each"). That is an importer capability,
  and this run has one.
- The near misses are the subtle part and a loose regex half-reads them into
  cheaper cards. Giada's "**Each other Angel you control** enters with an
  additional +1/+1 counter on it" is a replacement applying to permanents other
  than its source, which the `replacements` whitelist cannot express at all;
  Ulasht's sentence is two clauses joined by "and". Both must be *refused*, not
  approximated.
- A template card gets `_fallback_expectation`, which for a permanent is
  `{"zone": "battlefield"}` — "it resolved". On exactly the cards where the
  counter count *is* the card, that asserts nothing, and the sandbox board is not
  knowable at template time. The agent tier writes an expectation per card and
  can assert the count, so it produces a strictly better card here. Éomer's does:
  `counters: {"kind": "+1/+1", "amount": 0}` is the honest number in the fixed
  position, and dropping `exclude_self`, dropping the subtype filter, or writing
  the old constant `1` each fail it.
## An anthem with a size — "+1/+1 for each charge counter on this artifact"

### Overview

**Door of Destinies** — "As this artifact enters, choose a creature type. Whenever
you cast a spell of the chosen type, put a charge counter on this artifact.
Creatures you control of the chosen type get +1/+1 for each charge counter on this
artifact."

Two of those three lines already worked, in the shapes Vanquisher's Banner ships:
`choose_type` on a `self_enters` trigger, and a `spell_cast` trigger filtered by
`{"subtypes": [{"chosen_type_of": "self"}]}` adding a `charge` counter to
`self_only`. The third was blocked, and not on the anthem — on its **magnitude**.

It has to be a static. The buff applies continuously to whatever creatures of the
chosen type are on the battlefield at any moment, *including ones that arrive after
the counters do*, so no op reaches it: `pump` wears off at end of turn, and
`add_counters` putting +1/+1 counters onto the creatures themselves is a different
card twice over — the creatures already out would not grow when a later charge
counter landed, and creatures cast afterwards would arrive unsized.

But a static's magnitude is a **fourth** language, deliberately narrower than the
effect-side `VALUE_KEYS`, and `counters_on` was not in it: the loader refused the
leaf and `characteristics._static_value` would have read 0 for it anyway.

### What shipped

`counters_on` in `STATIC_VALUE_KEYS` and in `characteristics._static_value`,
validated by one shared `validate_counters_on` that both languages call — the
third member of that family after `validate_mana_symbols` and
`validate_per_player_count`, and shared for the reason they are: the same leaf
validated in one language only loads in a card that then quietly reads 0. Tier A,
and no op.

Legal inside a static for the reason the `counters` **condition** head has been
since Arixmethes: a counter is a pipeline *input*: primitives place and remove
them and no layer can touch one, so an anthem's magnitude reading one cannot come
to depend on another static's output and the fixed order of layers-lite stays
acyclic. What that head could not do is the point — it compares the count against
a fixed amount and yields on or off, so it can switch a fixed anthem on and off
and never size one. A ladder of threshold-conditioned +1/+1 statics is the kludge
it invites, and it is unbounded, and each rung's `text` would be a sentence the
card does not print, which the residual gate reads.

`count` is the other near miss and fails on a category: it counts *objects*
matching a filter, and counters are not objects, so no combination of
`STATIC_FILTER_KEYS` expresses "the number of charge counters on this artifact".

The magnitude needs no invalidation machinery of its own. `chars` is cached
against `state.char_version`, which `add_counters` and `remove_counters` both
bump, so the anthem grows the instant a counter lands and shrinks again when one
leaves — and a creature cast on turn nine is sized by the counters that landed on
turns four through eight, which is the whole card.

### The silent zero, which was the actual bug

`_static_value` ended in `return 0`. So a leaf the loader had not been taught —
or, worse, one taught to the loader and misspelled in the engine — was an anthem
that loaded clean, printed as the card does and gave +0/+0 for ever, with nothing
anywhere raising. That is the exact failure the whole validation pass exists to
refuse, and it was sitting inside the pass.

It raises now. Three things make that safe rather than a new crash surface:
statics reach the pipeline only through `_battlefield_statics`, which reads
`ability.static` off cards the loader compiled; every magnitude on that path has
been through `_validate_static_value`; and `None` is still 0, because a `buff`
with no `toughness` is a real card. An unknown leaf reaching the engine now means
the two languages have drifted, which is a bug in the loader and should read like
one.

The load-time half was tightened to match. `{}` is refused explicitly — it passes
a set-difference check and would have fallen off the end of the evaluator — and
`counters_on` requires **both** its keys in both languages: `counter` defaults to
`+1/+1` in the evaluator, so a Door of Destinies that omitted `charge` would be
sized by a counter kind the artifact never receives; and `objects` is not
`{"self_only": true}` when omitted, it is every permanent the filter language
defaults to, which on the static side is everything its controller has. The kind
goes through the 122.1c near-miss check `add_counters` already used, which moved
beside the shared validator so both languages get the same one.

### What the packet was not showing

The gap existed partly because a worker could not see the language it needed.
`static_value_keys` was absent from the authoring packet entirely, so a worker
shown `value_keys` alone read the effect-side list as the whole vocabulary — and
a worker shown nothing assumed an anthem's `power` is a `const` and filed a gap
for a sentence that, with this leaf, is now writable. It is in the packet now,
with a note, beside `static_condition_keys` which was added for Vampire Nocturnus
for exactly the same reason.

### What it unblocked

Door of Destinies, verified through all six gates. Its expectation is the
permanent landing with **zero** charge counters: the verifier's sandbox casts the
card under test and nothing else, so no spell of the chosen type is ever cast and
the anthem is correctly +0/+0 there. Asserting a number that position cannot
produce would have been asserting a fiction; the scaling itself is pinned in
`tests/unit/test_counter_scaled_anthem.py`, which is where behaviour that needs a
board belongs.
## "You may reveal **a** … card from among them" — an optional pool choice

### Overview

Boromir, Gondor's Hope looks at the top six cards of your library, offers you at
most one Human or artifact card from among them, and puts the rest on the bottom
in a random order. The middle sentence is a **declinable bounded pick** — "exactly
one of these, or none" — and the selector language had no spelling for it. Every
"look at the top N, you may take one" impulse card says the same thing.

`count` had three spellings and each of the three is a different, wrong card:

- a **value** makes the one number both the minimum and the maximum, so `count: 1`
  silently deletes the printed "You may". Sharper still, `pick_from_pool`
  short-circuits on `count >= len(pool)` and returns the pool without asking at
  all — so a top six holding exactly one Human put it in hand with no decision
  ever offered;
- **`"any"`** is min 0 / max *pool*, which is "any number of them": it would put
  **every** Human and artifact among the six into hand, a strictly better card;
- **`"all"`** is mandatory by definition.

Wrapping the whole `look_at_top` in `may` is not equivalent in either branch.
`op_may` gates the entire effects list, so declining also skips the mandatory
look and the mandatory `rest_to_bottom` — a real, distinct game action, since
`_bottom_in_random_order` reorders only the six looked at and is deliberately not
`shuffle_library`. And it asks the yes/no *before* anything has been seen, which
turns the one informed decision on the card into a blind one. Approximating the
decline branch with a second `look_at_top` in `may.else` cannot work either: the
depth is a literal `amount`, so it would bottom six cards from a position where
only five remain.

### What shipped

`optional: true` beside an integer `count`, honoured in
`selectors.pick_from_pool` as `min_count = 0` with `max_count` left at N. Only
the **floor** moves; the ceiling stays at the printed number, which is the entire
difference from `"any"`.

The name is `TargetModel.optional`'s, deliberately rather than a new word: that
field is this exact shape ("exactly N, or none") on the declared-target side, and
its own docstring already spelled out the distinction from `count: "any"`. What
it could not reach is a pool nothing targeted — `look_at_top` bounds its own from
the top of a library — so the word had to be said a second time on the selector
side rather than reused.

Nothing below the decision layer was missing. `ask_objects` has always taken
distinct `min_count`/`max_count` bounds and `PendingDecision.min_count` has
always been honoured, so this is a spelling and not a mechanism — the same shape
of change `count: "any"` was. **No new op, no new `DecisionKind`, no server or
frontend work**: `CHOOSE_OBJECTS` with a floor of zero already renders, and
`_choice_actions` already offers the `Done` action that a zero minimum makes
legal.

### The shortcut that had to learn about it

`if count >= len(pool): return pool` is right for a mandatory pick — there is
nothing left to decide — and is the deletion of "You may" here, because
**declining is the decision**. It is guarded rather than removed, so a bare
`count: N` over a pool of N still resolves without a pointless question.

### The load-time guards

`optional` on `"all"` or `"any"` is refused: the first is mandatory by
definition, the second already reaches zero, so on either the key would be
silently inert — and a card whose whole point is "you may" quietly losing the
word is the failure the key-set validation exists to prevent. Refused alongside
`random` and `chooser: "none"` too, for `"any"`'s reason: both resolve the pool
without asking anybody, and with nobody asked there is nobody to decline.

### An `any_of` branch inherits the outer zone

Boromir is the first card to ask a union about cards that are **not on the
battlefield**, and it found a bug that had been silent because every shipped
`any_of` is a battlefield selector. `matches` passed the *caller's* `default_zone`
down into each branch instead of the zone the outer selector had settled on, so
"a Human **or** artifact card" from a library look tested every branch against
the battlefield, matched nothing, and the op simply never asked — which on screen
is indistinguishable from a top six that happened to hold neither.

The fix is the other half of a rule `validate_selector` already enforces: a
branch may not name a `zone`, because "a branch filters the pool it already
chose". It now inherits that pool's zone. No shipped card changes behaviour.

### What it unblocked

**Boromir, Gondor's Hope**, verified through all six gates, and it was the only
gap record naming the capability. "Enters or attacks" splits into two triggered
abilities sharing the printed line, as Grave Titan already does.

**Gate 5 cannot exercise the pick, and the expectation says so honestly.** The
authoring sandbox deals player 0 a library of forty basic lands, so the top six
hold no Human and no artifact: the pool is empty, nothing is revealed, and the
six go to the bottom. The expectation asserts exactly that — hand unchanged at
zero, library unchanged at forty, the creature on the battlefield — which is what
the printed card does in that position. Asserting a revealed card would be
asserting something the board cannot show. The discriminating evidence is
`tests/unit/test_optional_pool_choice.py`, which is where §3 of the skill puts it:
engine work gets exactly the coverage its unit test writes.

**No template.** The shape is high-frequency, but `templates.py` matches one
whole printed *line* against `^…$` sentence patterns that are each a single op
with a countable outcome. Boromir's line is three sentences behind a two-event
trigger introducer that does not exist, and the three printed forms the gap
record collected — "put it into your hand", "put one of them onto the
battlefield", "exile up to one card from among them" — are three different
sentences, not one with a parameter. A template read off this one card would be a
guess, and rule 3 says refuse what cannot be read exactly. The cards stay in the
agent tier, where the next `/author-cards` picks them up now that the DSL can say
the sentence.

### Guarded by

`tests/unit/test_optional_pool_choice.py` — the range it asks for (floor zero,
ceiling N), the pool-of-one boundary where the old shortcut fired, both answers
coming back, the three spellings it is *not*, Boromir's trigger end to end
(including that declining still bottoms the rest, and that the question comes
after the look), the `any_of`-in-a-library fix with the battlefield case pinned
beside it, and every load-time guard.
## `reveal_until` — the third walk down a library, and the first whose stop test is the card's

### Overview

**Heirloom Blade** — "Whenever equipped creature dies, you may reveal cards from
the top of your library until you reveal a creature card that shares a creature
type with it. Put that card into your hand and the rest on the bottom of your
library in a random order."

Two thirds of that card were already sayable and are Skullclamp's, line for line:
"+3/+1" is a `buff` static with `affects: {"attached": true}`, and "Equip {1}" is
the sorcery-speed `attach` activated ability. The trigger was sayable too —
`dies` filtered on `attached`, wrapped in `may`, with `shares_a_type_with:
"subject"` reading the creature that just died. What was missing is one op: the
**scan**.

### Why none of the three near misses could be asked

The engine reaches a library four ways, and this sentence fits none of them.

| | |
|---|---|
| `look_at_top` | Bounds the pool to `amount` cards off the top — a constant known when the card is written — and then hands the player **every** match in that window to pick the best of. Two different cards in one: an amount large enough to fake "until" reveals and randomizes the whole library on every resolution, and best-of-all-matches is strictly better than first-hit |
| `search_library` | Looks at the whole library at once and shuffles afterwards (701.19). A chooser, not a scan, and it never walks down from the top |
| `cascade` | The right unbounded top-down shape, and the *only* one. But its test is hardcoded to "nonland card with lesser mana value than this spell", it **exiles** rather than reveals, and it offers a free cast rather than a card to hand. Nothing in it takes a selector |
| `ripple` | Fixed depth, and a hardcoded same-name-as-the-source test |

So the op is cascade's walk with `objects` where cascade's condition was, and
`_bottom_in_random_order` is shared rather than rewritten — the third
implementation of "put the rest on the bottom" is the thing this run most wanted
to avoid.

### The two outcomes that carry the rules argument

**It stops at the first hit, and there is no choice.** "Until you reveal" names
the card it takes, so `reveal_until` asks nothing and is not even a generator.
That is a structural claim rather than a stylistic one, and
`tests/unit/test_reveal_until.py`'s runner asserts it: it fails the test if the
op ever yields a decision.

**Running the library out with no match is an outcome, not an error.** Every
card revealed goes to the bottom, nothing reaches the destination, and nothing
crashes. This is the case an Equipment sees most — a trigger that fires late in
a game against a thin library — and it is also why "the rest" comes back in a
*random* order rather than the revealed one: after a failed scan the controller
has seen their entire library, and leaving it in order would hand them a fully
known deck for the rest of the game.

### `rest_to_bottom` defaults the opposite way to `look_at_top`'s

On `look_at_top` it defaults to **false**, and that is what "look at" means: the
cards you did not take stay on top, in order. Here it defaults to **true**,
because there is no printed "reveal until" that leaves the revealed cards where
they were — an omitted key defaulting the other way would silently make a card
that keeps the top of its own library face up and in order.

### The bottoming helper had two definitions, and now has one

`ops_cards.py` carried two functions named `_bottom_in_random_order`, a leftover
from reconciling parallel merges: an earlier one that spliced the list directly
and a later one that went through `move_object`, with the later one shadowing the
earlier for every caller. Both were random; the difference was the route.

Neither route is right for everything, so the surviving one has a branch per
card. Cascade's cards are in **exile** and must travel through `move_object` —
an object whose `zone` and whose containing list disagree is a card every other
reader in the engine sees differently. `look_at_top`'s, hideaway's and
`reveal_until`'s never left the library, and for those `move_object` announces a
zone change that did not happen, once per card: for a `reveal_until` that ran the
library out, once for the whole deck. Those are spliced within the list. Both
branches append in one shuffled order, so ripple's mixed set — a declined match
sitting in exile, its misses never moved — still lands in a single random order
rather than two.

### The loader refuses two cards that would otherwise be silently wrong

- **an empty `objects`**. The selector *is* the "until". An empty one matches
  the first card revealed, quietly turning the card into "put the top card of
  your library into your hand".
- **an `amount`**. The depth belongs to the library, not the card. A card that
  wrote one would believe its scan was bounded, and nothing would read it.
  `look_at_top` is where a bounded window lives.

An unknown `destination` is refused the same way `look_at_top`'s is.

### Server and frontend: nothing

A new op, and the scan emits the existing `reveal` event rather than a new one —
game state serializes generically and `describeEvent` already narrates a reveal,
so there was no Tier D work to skip.

### What it unblocked

**Heirloom Blade**, the whole card, through the **agent tier**. There is no
template for the sentence and `--tier templates --retry` harvests nothing, which
is the right outcome rather than a template that half-reads it.

The authoring gate proves the Equipment resolves onto the battlefield and no
more: `drive()` returns at `PRIORITY` with a non-empty stack and never activates
an activated ability, and nothing in the fixed position kills an equipped
creature, so the card honestly asserts `{"zone": "battlefield"}` with a board
count and nothing about the scan. `tests/unit/test_reveal_until.py` is where the
real coverage lives — the first-hit stop, the exhausted library, the match as the
very last card, `shares_a_type_with` walking past creatures of the wrong type,
and the randomness of the bottomed order asserted over seeds.

## "Can't block", with a clock and no permanent behind it

### Overview

`cant_block` already existed, as a **static**: an ability on a permanent, read by
`characteristics.block_forbidden` off `_battlefield_statics`. It is a fact about a
permanent that is currently on the battlefield, and that gives it three properties
which are exactly the three these two cards need inverted — it needs a source
standing there, it ends when that source leaves, and its `affects` filter may read
only *printed* characteristics.

- **Aragorn, King of Gondor** — "Whenever Aragorn attacks, up to one target
  creature can't block this turn. If you're the monarch, creatures can't block this
  turn." The first half names a creature chosen when the *trigger resolves*, which
  no printed-characteristics filter can pick out. The second is global and
  turn-scoped, and must catch creatures that enter later in the turn.
- **Taunt from the Rampart** — "Until your next turn, those creatures can't block."
  A sorcery, so nothing is left behind for a static to live on, and the clock runs
  past end of turn.

So `cant_block` is now **also an op**. The two are told apart by the key they sit
under: `"effect": "cant_block"` in a static ability, `"op": "cant_block"` in an
effect list. Same printed sentence, different mechanism, and neither is a weaker
version of the other.

### Where the prohibition lives

`GameState.block_prohibitions`, a list of `structs.BlockProhibition` — the
creatures (or `None` for "every creature"), a duration, the player whose next turn
ends it, and the source. Beside `attack_restrictions` and on the table for the same
reason a sibling run put that there: the effect belongs to no permanent, and a
resolving sorcery leaves none to own it. `TempEffect` is the near miss and fails on
the container — `until_eot` is a list on each `GameObject`, so an effect about a set
of creatures chosen at resolution, or about *all* creatures including ones not yet
in play, has nowhere to be written.

Named "prohibition" rather than "restriction" only to keep it apart from
`block_restriction`, which is the *attacker*-side static ("can't be blocked by
Humans"). That one narrows who may block a given attacker; this one stops a given
creature blocking at all.

### The two forms, and why the loader refuses a card with neither

| | |
|---|---|
| `objects` | the set chosen **at resolution** — "those creatures", "up to one target creature". Fixed; a creature that enters afterwards was not one of them |
| `all_creatures: true` | *every* creature, live. "Creatures can't block this turn" is a turn-scoped continuous effect, so a creature that enters later in the turn is caught too |

Exactly one of the two, enforced at load time, because neither guess for a
`cant_block` carrying neither is safe. "Nobody" makes the ability do nothing;
"everybody" turns Aragorn's *targeted* half into a one-sided Falter the moment its
optional target is declined. For the same reason `forbid_block` refuses an **empty**
`objects` rather than collapsing it into the global form — a declined "up to one
target" restricts nobody.

### The two clocks

`this_turn` is cleared by `turn._cleanup_step`, beside `clear_until_eot` but not
inside it: `until_eot` walks the battlefield, and this belongs to no permanent on
it. `until_your_next_turn` is cleared in `turn._untap_step`, in the same breath as
detain and keyed the same way — by **who** imposed it, never by a turn number,
because eliminating a player moves everybody else's "next turn".

That last point is also why `sba._eliminate` drops the entries belonging to a seat
that has left. Unlike the attack-restriction prune beside it, this one is not
hygiene: an eliminated player never has another untap step, so the prohibition
would outlive them for the rest of the game.

`cant_attack_player`'s `this_combat` has deliberately no counterpart here. Blockers
are declared *inside* the combat that would clear it, so a combat-scoped "can't
block" would be indistinguishable from one that never existed.

### Why not `detain`

`detain` has exactly the right clock and storage shape, and is the documented
precedent — but it also forbids attacking and activating abilities, and Taunt from
the Rampart's *other* sentence goads the same creatures into attacking. Detaining
them would print a card that contradicts its own first line. `grant_ability` cannot
carry a temporary static either: `loader.py` refuses any grantable ability that is
not triggered.

### The legality seam

`combat.block_prohibited(state, oid)`, called from `can_block` beside
`block_forbidden` and the `detained_by` check, and guarded on the list being
non-empty so the block mask's hot path is untouched in every game that plays none
of these cards. Kept out of the characteristics layer on purpose: that layer reads
permanents, and this is table state.

Because `can_block` is also what `unmet_block_requirements` asks, a creature under
this prohibition is excused from a provoke rather than compelled into an illegal
block — "…if able" for free, at the one place both questions already met.

### Server and frontend: nothing

No new event, decision kind or API field. The prohibition shows up as an
`ADD_BLOCKER` action that is not offered, and `LegalActionDTO.kind` is a bare string
the client echoes back.
## "Nonbasic" — the negation the supertype filter never had

### Overview

`selector_keys` carried `supertypes` and it was a positive subset test only —
`set(want).issubset(supertypes)` — so it could *require* Basic and could never
forbid it. The negated family (`not_types`, `not_subtypes`, `not_colors`,
`not_keywords`) simply had no supertype member, and "destroy target **nonbasic**
land" is unsayable without one. Field of Ruin is the witness; Wasteland,
Demolition Field, Tectonic Edge, Dust Bowl, Ruination, Encroaching Wastes and
Dwarven Miner are the same clause behind it.

`not_supertypes` is one key, four lines and a load-time guard.

### The approximation that had to be refused

`not_subtypes: ["Plains", "Island", "Swamp", "Mountain", "Forest"]` reads as the
same English and is a materially different card, wrong in **both** directions:

- It spares every nonbasic land that carries a basic land type — Hallowed
  Fountain, Murmuring Bosk, Dryad Arbor, every shockland, every Triome. That is
  precisely the mana base these cards are printed to answer, so the substitution
  removes most of the card's reason to exist while still reading correctly.
- It destroys Wastes, which is Basic with no subtype at all and which the printed
  card protects. Snow-Covered Forest is excluded only by the coincidence of being
  a Forest, not by being basic.

`mana_value` is the other near miss and separates nothing: basic and nonbasic
lands are both 0.

### Both paths, because the card targets

`objects` and target legality are different entry points, and a key honoured in
only the first makes a spell that can be aimed at a Mountain and then does
nothing on resolution. Both route through `selectors.matches`, so
`targeting.candidates` (what legality offers) and `targeting.still_legal` (the
re-check as the ability resolves) were covered by the same four lines —
`test_not_supertypes.py` asserts all three call sites anyway, because "they
happen to share a function today" is not a property a test can rely on.

`triggers.matches_card_filter` is the third place, and it needed its own line:
trigger filters are validated against the same `SELECTOR_KEYS`, so a key that
loaded and then did nothing would be exactly the silently-wider filter this key
exists to prevent.

### Supertypes are validated, and the negation is why

The `types`/`any_types`/`not_types` guard exists because a typo narrows a
selector silently. For a negation the failure is worse and quieter: a misspelled
positive supertype selects nothing and is obvious on the first board, where
`not_supertypes: ["basic"]` forbids nothing at all and looks like it worked — a
Field of Ruin that destroys Mountains. Both keys are now checked against the
three supertypes the engine knows.

### Not in the static filter language

`STATIC_FILTER_KEYS` did not get it, and that is a decision rather than an
omission. Every printed "nonbasic lands …" static is blocked on a missing static
*effect*, not on the filter: Blood Moon and Magus of the Moon want a
type-changing continuous effect, Back to Basics and Winter Moon an untap
restriction, Archon of Emeria and Zhao a filtered enters-tapped replacement. The
key would have nothing to attach to and no card to demonstrate itself on, and the
list is deliberately a curated subset — it has no `not_subtypes` or `not_colors`
either. It is one line to add on the day a card needs it.

### Server and frontend: nothing

A selector key is card vocabulary. Targets already serialize as refs and
`LegalActionDTO.kind` is a bare string.
## Library depth placement — the zone layer had two positions, and a card asked for a fourth

### Overview

One gap record named `library_depth_placement`: **Lost to Legend**, "Put target
nonland historic permanent into its owner's library **fourth from the top**."

Everything else on the line was already sayable. "Nonland historic permanent" is
`not_types: ["Land"]` beside an `any_of` over Artifact, the Legendary supertype
and the Saga subtype — `any_of` unions whole sub-selectors, so it ORs the three
readings of *historic* correctly, artifact creatures and all. The single blocker
was the depth, and it was missing further down than the op layer: `move_object`
took `to_top: bool`, which is `list.insert(0)` or `list.append`, so **top and
bottom were the only positions a library had**. There was no insert index
anywhere in the zone layer.

Neither rounding is an approximation of the printed card; each is a different
card, in opposite directions. On **top**, the owner draws the permanent back on
their very next draw step — the reverse of what paying two white mana for the
depth buys. On the **bottom** of a 99-card Commander deck, it is exile with
extra steps. `scry`, `surveil` and `look_at_top` cannot stand in either: all
three reorder or relocate cards that are *already* in a library and none can
admit a permanent from the battlefield.

### The shape

`move_object` grew `to_index`, a library position counted from the top, and
`put_on_top` grew `from_top`, the **printed ordinal** counted from 1. Extending
the existing op rather than adding a `put_into_library` beside it keeps every
tuck in one place, so a future Hinder and this card cannot drift apart on the
owner question or the clamp — and it costs the op count nothing, since the whole
family already routed through `put_on_top`.

An ordinal rather than a raw index because that is the sentence on the card:
`1` is the top, `2` is Hinder and Condemn, `4` is this. It is a value expression
like every other numeric field, so a card can compute a depth off the board.
`to_index` is optional, defaults to `None`, and is ignored outside a library, so
the thirty-odd existing `move_object` callers — draw, mill, discard, dies,
fizzle, mulligan, the merged-under pile — pass nothing and behave exactly as
before.

### The three things that are only visible when they are wrong

- **The ordinal.** Fourth from the top is index 3. A card tucked third is drawn a
  turn early, which is most of what the depth is for.
- **The clamp**, in both directions. A library shorter than the depth takes the
  card as deep as it goes, which is the printed rule. The *floor* is the half
  that would have been silent: `list.insert` already appends an index past the
  end, but a **negative** index counts back from the bottom, so an ordinal that
  computed to zero on an empty board would bury a card second-from-bottom and
  nothing would ever say so. Hence an explicit `max(0, min(i, len))` rather than
  trusting the list.
- **The owner.** `to_player=obj.owner`, never the controller — rule 400.3 read
  forwards. Only a stolen permanent can tell the difference, and there a
  controller's-library tuck hands the thief the victim's card for good.

The loader refuses two shapes that would otherwise load clean and play as a
better card than the one printed: `from_top` on any op that does not read it
(`draw` and friends take `amount` and ignore the rest), and a zero or negative
ordinal (the op floors it, but a card that needed correcting was authored wrong).

### What it unblocked

**Lost to Legend**, the whole card, through the **agent tier** — there is no
template for "fourth from the top", and `--tier templates --retry` harvests
nothing, which is the right outcome rather than a half-reading template that
would make a cheaper card than the printed one.

The authoring gate can prove the permanent left the battlefield and landed in
its **owner's** library (the sandbox's target is the opponent's artifact, so
`opponent_battlefield_count` and the opponent's `library_size` both move, and a
caster's-library tuck would fail on player 0's count). It cannot prove the
*depth*: no expectation key reads a library's order. That is why
`tests/unit/test_library_depth.py` carries the ordinal, the clamp and the
owner-vs-controller claim directly.

## "That player can't attack you" — the first prohibition with two sides

### Overview

Two cards asked for it from opposite directions, and the readers of both said so:
Call for Aid's "You can't attack that player this turn" and Champions of Minas
Tirith's "If they don't, they can't attack you this combat". Each is the other with
the attacking and defending players swapped, so one op carries both rather than two
near-duplicates being built.

The engine had one related thing, the `cant_attack` static, and it was the wrong
*shape* rather than a weaker version. `characteristics.attack_forbidden` matches
its `affects` filter against the **attacking creature** and takes no defending
player at all, so what it can express is "these creatures can't attack", never
"can't attack this player". Blanking an opponent's whole attack step is a strictly
stronger card than taxing attacks on one seat, and nothing about the substitution
would have looked wrong.

Two more reasons a static could not have carried it, either, and they are the ones
that generalise past this card: a static must live in `abilities` on a battlefield
permanent, and a resolving sorcery leaves none — no op installs a static; and a
static's filter may read only printed characteristics, so it could never name a
player identified when the spell resolved.

### Where the restriction lives

`GameState.attack_restrictions`, a list of `structs.AttackRestriction` — an
attacking player, a defending player, a duration and the source. On the table
beside `monarch` and `day_night`, and that is forced rather than aesthetic: this is
a fact about a pair of **seats**, and neither of them need own a permanent for it
to be true.

`TempEffect` was the near miss, and it fails on the container rather than on the
clock: `until_eot` is a list on each `GameObject`, so a restriction that belongs to
no object has nowhere to be written. Detain's `detained_by`-plus-untap-step pattern
is the other precedent and fails the same way for the same reason — it is a field
on the one permanent it restricts.

A list rather than a set of pairs, because two effects may impose the same pair
with different durations and the shorter one wearing off must not take the longer
one with it. Deduplicated on the whole tuple: "can't attack" does not stack, so a
second Champions taxing the same opponent in the same combat records nothing.

### The legality seam, and the shape left for goad

`combat.legal_defenders` was `[pid for pid in state.alive() if pid !=
state.active_player]` — no attacker argument at all, so the choice of defender was
per-declaration and global. It, `legal_planeswalker_defenders` and `add_attacker`
now all take the attacking oid and route through one predicate,
`attack_target_forbidden(state, oid, defender, planeswalker=…)`.

One predicate and not a filter in each of the three, because an action legality
offers and `add_attacker` then refuses is a declaration that cannot be completed.

`can_attack` also asks whether the creature has **any** defender left, guarded on
the restriction list being non-empty so the attack mask's hot path is untouched in
every game that plays none of these cards. That is not redundant with the above:
`attack_required` is a requirement AND `can_attack`, so a creature compelled to
attack with every defender forbidden would otherwise have "Done attacking"
withheld by legality with no `ADD_ATTACKER` left to offer — a step with no legal
action in it.

`planeswalker` is a parameter of the predicate rather than something it infers,
and that is the seam `goad` was recorded needing. **This** restriction exempts
planeswalkers: "creatures can't attack you" restricts attacking the *player*, and
506.2 makes a planeswalker a third thing that can be attacked with its controller
merely the defending player — which is why a Ghostly Prison charges nothing when
the attack goes at a planeswalker. Goad's "attacks a player other than you if
able" is the opposite answer, since attacking your planeswalker does not discharge
that requirement. A future goad run adds its clause inside
`attack_target_forbidden` and touches none of the three callers.

**That run happened, and the seam held**: goad's clause went inside
`attack_target_forbidden` and the three callers were not touched again. See "Goad
— two rules in one word" at the top of this file.

### Why `duration` is required rather than defaulted

`this_turn` is cleared at cleanup beside `clear_until_eot`; `this_combat` is
cleared by `combat.end_combat`. Neither is the safe default, which is the whole
argument for refusing a card that omits the word:

- `this_combat` read as `this_turn` blanks the extra combat a Relentless Assault
  bought, taxing it with a toll that was already paid.
- `this_turn` read as `this_combat` expires before the combat Call for Aid was
  cast in even begins to matter — the spell resolves in a main phase and means the
  whole turn.

Champions' trigger fires at the beginning of *each* combat, so the combat-scoped
duration is not merely shorter: it is what makes the tax re-asked rather than
paid once.

### Server and frontend: nothing

No new event, decision kind or API field. A restriction shows up as an
`ADD_ATTACKER` action that is not offered, and `LegalActionDTO.kind` is a bare
string the client echoes back, so the UI is consistent without knowing why.
## "This way", and "the token" — naming what an earlier effect just did

### Overview

Two gap records named `effect_result_binding`, and they are the same missing
thing in two ops:

- **Grey Host Reinforcements** — "exile target player's graveyard. Put a number
  of +1/+1 counters on this creature equal to the number of creature cards exiled
  **this way**." So `exile` has to publish what it exiled.
- **Flamerush Rider** — "create a token that's a copy of another target attacking
  creature… Exile **the token** at end of combat." So `create_token` and
  `copy_permanent` have to publish what they made.

Rule 608.2 resolves a one-shot effect's instructions in order, and the later
instruction on both cards is about the objects the earlier one touched. The
engine already had the idiom under this exact name: `as` on `sacrifice` (devour's
"it enters with twice that many +1/+1 counters") and on `reveal` ("X is the number
of cards revealed this way"), read back through `{"count": {"binding": …}}`. The
**read** side was live. Only the write side was missing, on the three ops that
never got it.

### The write side, and where the line is written

`op_exile` gained the three lines `op_sacrifice` has directly below it, in the
same place — *before* the move loop, so the binding records what this op exiled
rather than whatever happens to be in exile once it is done.

The two token-making ops are the mirror image and write *after*, because the oids
did not exist until the op ran: `create_token` has always **returned** the oids it
made and both callers discarded them. `copy_permanent` records the copies, never
the thing copied — `{"target": …}` already names that.

Nothing else in the language reaches either set:

| | why it cannot be recovered |
|---|---|
| the exiled cards | they land in the shared exile zone among everything ever exiled there. `exiled_with: "self"` reads `GameObject.exiled_by`, which `op_exile` only writes when `until_leaves` is set — and that is the Oblivion Ring *link*, so borrowing it declares a return this card does not have |
| the token | `is_token` matches every token you control, and `{"is_token": true, "attacking": true}` also catches tokens another attack trigger made this turn, so a second copy of the same card exiles the wrong permanent |

Counting the graveyard *before* the exile is the near miss on the first card: it
is numerically equal only because this particular card empties the whole zone, it
needs the two printed sentences in the opposite order from the one printed, and it
does not generalise to "this way".

### The read side had a silent hole in it

`resolve_pool`'s `binding` branch does apply the rest of the selector — that is
what lets Coiling Oracle ask "is the card I just bound a land?". But `matches`
defaults an absent `zone` clause to the battlefield, and an object recorded by
`as` has, by construction, just changed zones. So the selector Grey Host
Reinforcements needs, `{"binding": "exiled", "types": ["Creature"]}`, matched
nothing at all: not narrowed, **emptied**. Counted 0, put no counters on, and
complained about nothing, because nothing was malformed. Devour and amplify never
noticed because they read the bare `{"binding": …}`, which short-circuits before
`matches` is reached.

So an absent `zone` now means different things on the two shorthands, which is
the honest reading of what each one is:

- `binding` — no default zone. A binding is a **record** of the past.
- `target` — the battlefield, unchanged. A target really is re-checked as the
  spell resolves (608.2b), so "destroy target creature" whose creature is already
  in a graveyard has no legal target left, and that default is the check.

A `zone` the card *writes* still filters on either, so "…the exiled cards that are
still in exile" remains sayable. The alternative — making `binding` plus a filter
clause a load error — was rejected: it would refuse the printed sentence rather
than express it, and Coiling Oracle already relies on the combination.

### The loader guard

`RECORDING_OPS` lives beside `OPS` in `engine/effects/__init__.py`, so the guard
and the implementations cannot drift. Seven ops record; an `as` on any other is
now a load error. That failure mode is exactly the one this capability exists to
fix, and it looks right on the page: "destroy the creatures, then draw a card for
each destroyed this way" would load, resolve, and draw nothing.

**Unblocked one card: Grey Host Reinforcements.** Its "Flying, ward {3}" line is
the shipped ward idiom (`CLOAK_WARD`'s shape, as printed on Vein Ripper) and
needed nothing new. Flamerush Rider loses this need and keeps its other one:
`Step.END_OF_COMBAT` exists and the turn walks through it, but `turn.DELAY_STEPS`
maps only four steps, so `{"op": "delay", "step": "end_of_combat"}` never becomes
due. `delay` already snapshots `ctx.bindings` when it schedules, so the recorded
token will survive to that step the moment the step is reachable. *(That step is
now reachable — see "At end of combat" above, which is the run that shipped the
card.)*
## Conditional cost reduction — the discount that can be switched off, and the one that belongs to a variant

### Overview

Two gap records named `conditional_cost_reduction` from opposite directions, and
between them they specified it better than either did alone.

**Crown of Gondor** — "Equip {4}. This ability costs {3} less to activate **if
you're the monarch**." `Cost.mana_reduction` existed and was the wrong
arithmetic: it took only `{"count": {filter}}`, a per-object multiplier, so a flat
"{3} less if X" would have needed a filter matching exactly three permanents while
the crown was yours and none otherwise, which no filter over a board can express.
The two card-level reductions were no help either — both are read from the cast
path and never reach the activation path an equip cost is charged on — and
splitting the printed line into two equip abilities leaves nothing able to switch
the cheap one off. So the card was either always {4} or always {1}: a card that
plays like a different card, at a price nothing on screen would question.

**Visions of Glory** — "Flashback {8}{W}{W}. This spell costs {X} less to cast
**this way**." `legality._cast_variant` picks a price per cast variant and then
applies `cost_reduction` to whatever it picked, because Ghalta costs less however
it is cast; `game._cast` mirrors that. So a card-level reduction is
**variant-blind**, and the rider written there would have taken {X} off the
printed hand cast too. That is the more dangerous of the two omissions, because
the card still loads, still plays, and is simply cheaper than it says — from a
zone the reader was not looking at.

### One mechanism, not two

The two faces are the same question asked of different cost nodes: *how much less
does **this** cost node cost right now*. So there is one reduction language,
`costs.reduction_amount`, and three readers of it.

The language gained two things. `{"amount": N}` is a **flat** reduction, a
different shape from `count` rather than a special case of it, for the reason
above. And `condition` gates the whole thing — the ordinary condition DSL, so
`is_monarch`, `is_your_turn`, `exists` and `cmp` came for free the moment the gate
existed.

The variant scoping then turned out not to be a mechanism at all, but *where the
node is read from*. `flashback`/`graveyard_cost` is already a full `Cost`, so it
already had a `mana_reduction` slot; nothing read it. `costs.variant_reduction`
reads it from the flashback branch of `_cast_variant` **and** the matching branch
of `game._cast` — both, because a spell offered at one price and charged another
strands the payment. Reusing `mana_reduction` rather than adding the `reduction`
key the gap record suggested is deliberate: a second key meaning the same thing on
the same model is a key that gets written in the wrong slot and ignored in
silence.

`ability_mana` also grew a `source_oid`, threaded from `can_pay` and `pay` alike,
so a reduction whose condition asks about its own permanent answers identically in
both.

### What the loader refuses, and why each would otherwise be silent

Every one of these loads clean and does the wrong thing quietly, which is what
makes them load errors:

- **A flat `amount` with no `condition`.** That is a cheaper printed cost written
  the long way.
- **A `condition` with no arithmetic**, or two kinds of arithmetic at once —
  whichever the code read first would win, and no printed line says both.
- **`kicked`, `evoked`, `overloaded`, `cast_from_graveyard`** in the condition. A
  reduction is priced *before* the spell reaches the stack, so all four read
  `False` every time: a discount clause that can never fire, on a card that reads
  as though it has one. Checked recursively through `all`/`any`/`not`.
- **A `mana_reduction` with no `mana` to reduce.** Clamped at zero, so it would do
  nothing at all.
- **A filter naming a zone `_reduction_matches` does not walk.** The battlefield
  then, and the battlefield or the command zone since `commander_mana_value`;
  anything else would load clean and match nothing.
- **`mana_reduction` on `additional_cost`.** Its mana is folded into the spell's
  price with `additional_cost.mana.scaled(...)`, so nothing prices that node on
  its own and the player would be charged the full amount.

Only `flashback`/`graveyard_cost` can carry the variant rider, and that is a fact
about the schema rather than about the mechanism: `evoke`, `emerge`, `overload`,
`bestow`, `foretell`, `mutate` and `alternative_cost` are bare mana strings with
no cost node to hang one on. Each would gain the rider for free the day it becomes
a `Cost`.

### What it unblocked

**Crown of Gondor**, all three lines: the `buff` static whose value is a
`{"count": …}` over creatures you control, the `permanent_enters` trigger filtered
to legendary creatures with `{"no_monarch": true}` as its intervening-if, and the
equip whose cost carries `{"amount": 3, "condition": {"is_monarch": "you"}}`. Its
equip cost cannot be observed in the authoring sandbox — the verifier never
activates activated abilities — so `tests/unit/test_conditional_cost_reduction.py`
is where that coverage lives, including both halves of the offer-and-charge
agreement.

**Visions of Glory** was left blocked here on `commander_mana_value` alone — a
maximum over the battlefield *and* the command zone — with its rider's *slot*
built and only the number it takes missing. That number shipped next; see
"Commander mana value" above, and the card is playable.

## The monarch — a designation whose word is worth nothing

### Overview

Eight cards in the pool print "you become the monarch" and `docs/rules-coverage.md`
listed the mechanic under **Not implemented**, on the line grouping it with the
initiative as a designated-player mechanic with nowhere to live. That was a
decision, and it was already stale: day/night had answered the same objection —
"a game-wide designated state the engine has no place to keep" — with one field on
`GameState`. So `state.monarch` is an optional player id sitting beside
`day_night`, because the crown belongs to the **table** rather than to a player or
a permanent.

One field is also the whole of rule 721.4. "Only one player can be the monarch at
a time; if a player becomes the monarch, the current monarch ceases to be" is
arithmetic when the designation *is* the field: giving the crown away takes it off
the previous holder with nothing written to do so. `has_city_s_blessing` is the
right shape for player-level state and the wrong semantics — one-way and
non-exclusive by design, which is the opposite of a designation exactly one player
holds and that moves between them, and every write site would have had to remember
to clear the others.

### The interesting part is that the op is not the feature

`become_monarch` is four lines. A card carrying only that would load, resolve,
change one integer and never do anything again — and it would read exactly like a
working card. What makes the crown a card-a-turn engine, and a five-mana 2/2 body
a fair rate, is rule 721.3's pair of **inherent triggered abilities**. They have
no source and are controlled by the game, so neither is written on a card:

- **The end-step draw** is `turn._monarch_draw`, beside the day/night switch. It
  is the monarch's *own* end step, which is one comparison because `END_STEP` only
  fires on the active player's turn — and a version that drew on every end step
  would hand out one card per opponent per round, which at a pod is three or four
  cards a turn cycle. It goes through `replacements.draw` rather than
  `primitives.draw_cards`, so it can be dredged, madnessed or miracled like any
  other draw, which is also why it is a generator.
- **The combat-damage transfer** is `combat._monarch_transfer`: "whenever a
  creature deals combat damage to the monarch, that creature's controller becomes
  the monarch". This is the half the printed cards are *priced against* — on most
  boards it is the only ordinary way the crown ever moves, and it is the only
  thing that can ever end Palace Jailer's exile.

### Why the transfer is not inside `damage_player`

`damage_player` is the single funnel for combat damage to a player and looks like
the obvious home. It is the wrong one, and the reason is the batch. Combat damage
is dealt simultaneously (510.2), and `deal_combat_damage` already collects every
assignment before applying any — so the monarch can be read **once, before the
batch**, which is the one true answer to "who was the monarch" for the whole step.
Read one hit at a time instead, a second creature connecting in the same step
would find the crown already moved by the first and transfer nothing.

With every attacker belonging to the active player that mistake is invisible,
because the answer comes out right anyway. It is the snapshot being right that
keeps it right, so `test_monarch.py` pins the snapshot rather than the outcome.
Ties go to the APNAP-earliest damager, since the active player puts their trigger
on the stack first and first on is last off.

### `None` is a third state, not the absence of one

Crown of Gondor reads "when a legendary creature you control enters, **if there is
no monarch**, you become the monarch", and that is not `{"not": {"is_monarch":
"you"}}`. The negation is true in two situations — nobody holds the crown, and an
*opponent* holds it — and the second is precisely the case the card must not fire
in. Written as the negation it stops being a way to claim a vacancy and becomes a
repeatable steal. So there are two condition keys, `is_monarch` (taking a player
spec) and `no_monarch` (a literal boolean, because `"false"` is a non-empty string
and would read as `true` in exactly that case).

### One event, both routes

`BECAME_MONARCH` is fired by `primitives.become_monarch`, which is the only writer
— the op calls it and so does the combat transfer. That is what lets
`becomes_monarch` be a single trigger event covering both, and it is why Palace
Jailer's "until an opponent becomes the monarch" can be one clause. The near miss
is `deals_combat_damage_to_player`, which fires on the damage rather than on the
designation: every watcher would have to re-derive "and that player was the
monarch, so the crown just moved", and would still miss the route where an
opponent's own card crowns them with no damage anywhere.

Re-designating the player who already holds it is a **no-op that fires nothing**.
The event means the crown *moved*; a version that fired anyway would hand the
creature back the moment Palace Jailer's own controller re-crowned themselves.

`becomes_monarch` is the first trigger event this repo has added whose subject is
a **player**, so it is absent from `OBJECT_SUBJECT_TRIGGERS` and `_actor` names the
*new* monarch. Reading the crown's previous holder instead would end the Jailer's
exile at the moment it must not.

### The frontend work a new event forces

`describeEvent` and `beatsFor` both have a `default` fallthrough, so an unnarrated
event is dropped in silence and no test says so. Both were given a case, and the
argument for the second is that the consequence of the crown moving is *invisible*
on the board: nothing changes zones, nothing changes stats, and the monarch simply
starts drawing an extra card at every end step. A player who did not notice losing
it sees a stream of unexplained draws. A banner, toned from the viewer's side,
since gaining and losing the crown are one event told two ways.

Nothing on the server or in the API changed, which is the general rule for a new
event: `day_night` and `has_city_s_blessing` are not serialized either.

### 721.5, which no duel can reach

A monarch who leaves the game hands the crown to the active player. It is three
lines in `sba._eliminate`, unreachable at two players — the monarch losing ends
the game — and it is the boundary that is silent in all three directions when it
is missing: the crown sits on a seat that has gone, the end-step draw finds nobody
to draw for, and every "there is no monarch" reads False for the rest of the game.

### What it unblocked

**Faramir, Steward of Gondor**, whose two lines are a `permanent_enters` trigger
filtered to legendary creatures of mana value 4 or greater and an `end_step`
trigger with `is_monarch` as its intervening-if. The other seven monarch cards
stay blocked on capabilities that are not the monarch — `cant_block`,
`cant_attack_player`, `conditional_cost_reduction`,
`variable_enters_with_counters`, `delayed_triggered_ability`, `saga` plus
`keyword_counters`, and `exile_until_event` — and their gap records were trimmed
rather than retired, so the report now says what each is actually waiting for.
## Sagas — the card whose whole mechanic is printed in brackets

### Overview

`docs/rules-coverage.md` listed sagas under **Not implemented**, on the line
grouping them with planeswalkers and battles as rules subsystems rather than
cards. That was a decision, and the thing it was waiting for had just arrived:
the monarch had shown where a behaviour with no card to live on goes — a
turn-based action in `turn`, a state-based action in `sba`, and nothing written
on any card at all.

Read a Saga's reminder line back and notice that it is entirely in brackets:

> (As this Saga enters and after your draw step, add a lore counter.
> Sacrifice after III.)

Parenthetical reminder text tells you a rule you would otherwise have to look
up. It is not an ability, it is not something the card *does*, and it is the same
sentence on every Saga ever printed — which is why `engine/sagas.py` exists and
why nothing in a Saga's card file mentions lore counters. What a Saga's card file
says is three numbered lines and nothing else.

### The three rules, and where each had to go

The gap record for Oath of Eorl enumerated the kludge available before this — a
`self_enters` trigger, a `draw_step` trigger, three `counter_placed` triggers
gated on `counters_on`, and a self-`sacrifice` on III — and then refused it,
naming four ways it diverges. Each of the four is a different rule and each lands
somewhere different.

- **The counter it enters with** (714.2b) is a `self_enters_with_counters`
  **replacement**, compiled by the loader exactly as a planeswalker's starting
  loyalty is: both are a number printed on the card that the rules turn into
  counters as the permanent enters. Written as a `self_enters` trigger the counter
  lands *after* the Saga is already on the battlefield and after every other
  enters trigger has looked at a Saga with none — so chapter I would be a round of
  priority late, an opponent could answer the Saga before it had started, and
  anything counting lore counters on arrival would read zero.
- **The tick** (714.2d) is a **turn-based action** at the precombat main phase,
  the first branch that step in `turn.begin_step` has ever had. Three things
  separate it from a `draw_step` trigger and all three are visible: nobody holds
  priority between the counter and the chapter, so there is nothing to respond to;
  it is the *active player's* Sagas, where DRAW_STEP fires on everybody's draw
  step unless each card in the pool remembers `is_your_turn`; and it is the phase
  the current rule puts it in rather than the step the 2018 wording named, so a
  chapter resolves where its controller can act.
- **The chapter itself** (714.2c) fires when the count **becomes** the chapter
  number, which is a before/after comparison and not a reaction to a placement.
  This is the one that looks like a distinction without a difference and is not.
  Proliferate is a *single* placement that can cross two chapters; a placement of
  two counters at once crosses two and must fire both, in ascending order, because
  a Saga jumped from I to III still resolves II first; and a lore counter removed
  and put back crosses the same number twice and re-triggers, which no high-water
  mark can express. So `primitives.add_counters` reads the count before it writes
  and hands both numbers to `sagas.chapters_reached`, which fires one
  CHAPTER_REACHED per number crossed.
- **The sacrifice** (704.5s) is a **state-based action** that waits until no
  chapter ability of that Saga has triggered-but-not-yet-left-the-stack. Appended
  to the last chapter's effects instead — which is the obvious shape — the Saga
  would be sacrificed part-way through its own chapter III resolving, and on Oath
  of Eorl, whose III puts a counter on a creature and *then* grants the crown, the
  monarchy would be handed out by a permanent already in a graveyard.

### "Not yet left the stack" starts before it gets there

The clause 704.5s spends its length on is the one an implementation is most
likely to read as `state.stack`, and that is wrong in the direction that eats the
card: state-based actions run **before** a player would receive priority, which
is the same moment `drain_to_stack` is about to use, so a freshly triggered
chapter spends that entire window in `pending_triggers` and not on the stack at
all. Checking the stack alone sacrifices every Saga at the instant its final
chapter triggers and throws that chapter away with it — a three-chapter Saga that
silently only has two.

### A fourth `AbilityKind` that is still a triggered ability

714.1b says "chapter abilities are triggered abilities", and taking it literally
is what keeps this small: `Ability.is_triggered` is True for a chapter, every
call site already pairs that property with `ability.trigger is not None`, and the
loader gives a chapter a real `TriggerSpec`. So collection, the APNAP queue, the
stack, target choice on the way on and `ability_of` on the way off are the code
that already existed, unchanged.

What the new kind buys is the three things `triggered` could not say. The chapter
**number**, which becomes the trigger's filter — one CHAPTER_REACHED event
carries the number reached and every chapter ability on that Saga is a candidate
for it, so without the comparison a three-chapter Saga would put all three on the
stack off its first lore counter. The card-level `final_chapter` derived from
those numbers. And a load-time refusal of a chapter on a card that is not a Saga,
where no lore counter would ever arrive and every chapter would be dead text.

**No card writes the trigger, and none may.** There is no word in "II — Create
two 2/2 red Human Knight creature tokens" that says when it happens; the whole of
the timing is 714.2c. The loader supplies it for the reason it supplies
`source: "self"` on `self_enters`, and with a stronger argument — here there is
nothing an author could even leave out, only something they could get wrong.

### `final_chapter`, and the failure that is an *upgrade*

704.5s compares the lore counters against the Saga's final chapter number, and
that number is the one fact about a Saga not derivable from what it implements. A
Saga whose last chapter the DSL cannot yet express would, derived, be sacrificed
a chapter early — which is not a card that does less, it is a card that ends
sooner and is therefore quietly *better* than the one printed. That direction is
the one nothing complains about, so `final_chapter` may be declared and outranks
the derivation; the Saga then sits out its last chapter doing nothing, which is
the printed card minus a line and is visible to anyone who plays it.

The mirror case is a `Saga` subtype with **no** chapter abilities, which is
accepted and inert. That is what an unimplemented Saga in `data/generated/` is —
seven of them are in the catalog — and refusing the shape would make those cards
unrepresentable rather than unimplemented. Such a card gets `final_chapter is
None`, which is what every rule in `engine/sagas.py` actually tests: no lore
counter, nothing to advance, nothing to be sacrificed for reaching. 704.5s agrees,
asking for "a Saga permanent **with one or more chapter abilities**". An
*authored* Saga cannot use the same hole, because its printed chapter lines would
go unclaimed and the residual gate would reject the card.

### Nothing on `GameState`, and that is the difference from the monarch

The monarch is a field on `GameState` because the crown belongs to the **table**.
A Saga's progress belongs to the permanent, so it is lore counters on an ordinary
`GameObject` and there is no new state anywhere. That is not tidiness: it is why
`counters_on`, `proliferate`, `move_counters`, `remove_counters` and the client's
counter badge all read a Saga for free — and it is also why the chapter trigger
had to be a comparison rather than a hook on one caller, since every one of those
can move a Saga's story along.

### The frontend work a new event forces

`describeEvent` and `beatsFor` both have a `default` fallthrough, so an
unnarrated event is dropped in silence and no test says so. Both were given a
case. The `counter_placed` beside it already floats "+1 lore", which is the
bookkeeping; what a player needs is *which chapter*, since the three do different
things and only one of them is about to end the card — and when a Saga enters,
the chapter line is the only line there is, because the counter it enters with is
placed by a replacement and emits nothing at all. Numbered in Roman, as the card
is. A float off the Saga rather than a banner, because unlike the crown there
*is* a permanent and it is the one the eye should go to.

### What it unblocked

**Oath of Eorl**, the only Saga in the pool and the last card of the Riders of
Rohan deck: `{3}{R}{W}`, two Human Soldiers, two Human Knights with trample and
haste, then an indestructible counter on up to one target Human and the monarchy.
Its three other capabilities — `monarch`, `keyword_counters` and both token
definitions — had all shipped ahead of it, so sagas were its last blocker.

The authoring sandbox measures immediately after the cast, so it can only ever
observe **chapter I**: one lore counter, two Soldiers, 35 permanents. Chapters II
and III need later turns the fixed position never reaches, and they are covered in
`tests/unit/test_saga.py` instead — including the turn-based tick, the
proliferate boundary, the re-trigger, and the sacrifice that waits for its own
last chapter.

## Keyword counters — the counter that was already sayable and meant nothing

### Overview

"Return that card to the battlefield under its owner's control **with a vigilance
counter and a lifelink counter on it**" (Gilraen, Dúnedain Protector). "**Put an
indestructible counter** on up to one target Human" (Oath of Eorl). Two gap
records named the same capability, and one of their readers counted roughly ten
more queued cards waiting on it.

The gap was the quietest kind. `add_counters` has always accepted any `counter`
string, so the clause **loaded, cast and resolved**; `characteristics._compute`
read exactly two kinds, `+1/+1` and `-1/-1`, for power and toughness, and nothing
anywhere consulted counters when computing keywords. So the card printed as
written and handed back a creature that tapped when it attacked and gained nobody
any life — an inert tally behind a sentence that every gate passed. Rule 122.1c
says a permanent with a keyword counter on it *has* that keyword ability; the
engine agreed on paper and nowhere else.

### Tier B, and the whole of Tier B was where the layer sits

No new op — `add_counters`, `remove_counters`, `move_counters` and `proliferate`
were already generic over the kind. No new `TempEffect` and no new primitive
either, which is the part of Tier B that did not apply: a counter is already
first-class state on `GameObject`, already bumps `char_version`, already
serializes, already survives the turn. What was missing was a **reader**, so the
one Tier B question that mattered was the one Tier B says is the whole design
question — where in the fixed order it goes.

It goes in the **keyword-grant layer** (2b), beside the `grant_keyword` statics,
not beside the `+1/+1` counters at layer 5. Three reasons, in order of how much
they decide:

1. It is what the real layer system does. 613.1f applies keyword counters
   together with the ability-adding effects; 613.1d applies `+1/+1` counters four
   layers later. The engine's fixed order now splits the two halves of "read the
   counters" the same way, and the split is the point rather than an accident.
2. What separates them is what they *are*: one counter is an ability, the other
   is a size. Grouping by which dict they came out of would put an ability in the
   P/T layer.
3. No outcome can tell. Keywords only ever accumulate into a set and no layer
   removes one — there is no "loses all abilities" static — so unlike `animate`,
   which had to run first because it **replaces** base P/T, this collides with
   nothing. That makes the position a statement about what the thing is, and the
   argument above is all there is to go on.

The set of kinds is derived from `Keyword` (`enums.KEYWORD_COUNTERS`) rather than
listed, because 122.1c names no subset: the next card to print a menace counter
should need no engine change. `INERT_KEYWORDS` is subtracted, since partner is a
deck-construction word and a counter granting it could not mean anything.

### The load-time guard, which is most of the value

The lookup is exact, so `"Vigilance"`, `"vigilance counter"` and `"first strike"`
would each write a tally nobody consults on a card that reads as printed — the
same silent failure, now reachable by a typo instead of by a missing layer. A
counter kind is an open vocabulary (charge, quest, slumber, lore, age) with
nothing to validate against, but this particular mistake is *detectable*: it
normalises onto a keyword the engine implements. So `_check_counter_kind` refuses
it, at every point a card names a counter kind — an effect's `counter` or
`counters`, an enters-with-counters replacement, a static's `counters` condition,
and a `counter_placed` trigger filter. A kind that normalises onto nothing is
left alone; guessing at typos in an open vocabulary would refuse correct cards.

### Refused: making a static's filter see it

`added_subtypes` is let into `_matches_printed` because Captivating Vampire's own
anthem would otherwise ignore the creature it had just converted. Keyword
counters are a pipeline input in exactly the same sense and could have been let
in on exactly the same argument — and were not.

A static's `affects` filter reads the printed face, so `keywords: ["flying"]`
does not match a creature wearing a flying counter. It also does not match one
granted flying by Levitation, which is the documented no-layers simplification
working as designed. Admitting counters alone would make a keyword counter the
one *visible* kind of keyword grant, which is a new inconsistency rather than a
closed hole — and no card in the pool needs it, where Captivating Vampire needed
its half. Effect selectors (`selectors.matches`) read derived characteristics on
the battlefield and see keyword counters for free, which is a split that already
existed for every other grant.

### What it unblocked: nothing, and that is the honest answer

Neither witness can be authored, and neither is blocked on this any more:

- **Gilraen, Dúnedain Protector** also needs `delayed_object_reference` — "return
  *that card*" from inside a `delay` has no expressible subject, because
  `turn.py` builds the delayed-trigger context with `targets={}` and `exile`
  writes no binding.
- **Oath of Eorl** also needs `saga`, which `rules-coverage.md` lists under **Not
  implemented**: `AbilityKind` is exactly {activated, triggered, static} and there
  is no chapter ability for its printed lines to hang on.

Both gap records were trimmed to their remaining needs rather than retired. So
`tests/unit/test_keyword_counters.py` is the only thing holding this mechanic —
no authored card is re-verified through the six gates on its behalf — and it is
weighted accordingly: placement, parity with the printed keyword, three separate
rules (combat declaration, `destroy`, `can_block`) reading it, outlasting both the
cleanup step and the permanent that placed it, the boundary where the last
counter comes off, every other counter op reaching it, and the zone change that
takes it away.

That last one is worth stating, because it looks like a limitation and is the
rule: counters cease to exist when a permanent changes zones (121.2), so a
creature that dies and returns is the printed one again. It is precisely why
Gilraen's card says to return the card *with* the counters on it rather than
trusting them to travel.
## Per-opponent counts — "an opponent controls more lands than you"

### Overview

One printed clause, three cards, and three different places it has to be
askable: Knight of the White Orchid asks it as a trigger's intervening-`if`,
Weathered Wayfarer as an activation restriction, Verge Rangers as a static's "as
long as". Eight more queued cards say the same sentence about lands (Loyal
Warhound, Claim Jumper, Scouting Hawk, Space Marine Scout, Beza the Bounding
Spring, Aerial Surveyor, Boreas Charger, Cartographer's Hawk), and two say it
about creatures (Avatar of Might, Advice from the Fae).

The engine could already count objects, and that was the trap rather than the
solution. `count` resolves **one** pool, and `controller: "opponent"` means every
opponent at once -- `selectors._zone_owners` says so in a comment -- so
`{"count": {"types": ["Land"], "controller": "opponent"}}` is the *sum* across the
table. In a duel that is the printed card exactly. At a four-player pod it is a
different card and inverted: three opponents holding two lands each total six and
beat your five, so a Knight built on `count` is an unconditional two-mana 2/2
that ramps and a Wayfarer built on it is an unconditional repeatable land tutor,
while both printed cards are blank precisely when you are ahead. This repo is
Commander-first, so that is a divergence rather than a rounding error.

### What shipped

`max_count_of` and `min_count_of` -- the existential and the universal -- in
`VALUE_KEYS`, in `characteristics._static_value`, and validated by one shared
`validate_per_player_count` that both languages call, the way
`validate_mana_symbols` is already shared. Tier A, and no op: `cmp`/`left`/`right`
already reach every one of the four call sites, so the trigger condition, the
activation condition, an `if` in a body and a static's `condition` all came free
with the leaf.

It is the same split as `min_life_of` / `max_life_of` and for the same recorded
reason, which is why it is a *pair*: "an opponent controls more X than you" is the
maximum over the per-player counts, and "each opponent controls more" is the
minimum. `min`/`max` already existed as value expressions and cannot stand in --
they take a literal list written into the card, and no player spec enumerates
opponents one at a time to feed them. `extreme` ranks only power, toughness and
mana value, and `distinct` counts values over a single pool.

`for_each_player` is the only other per-player mechanism in the engine and is the
near miss worth recording. It is an **op**, so it cannot appear in a condition at
all; moving the test into the effects body would run the search once per
qualifying opponent -- up to three Plains onto the battlefield off a card that
fetches one -- and would drop the on-trigger half of the intervening-`if`
entirely.

### The scope is injected, not asked for

`for_each_player` scopes its body by binding `each_player` and having nested
selectors name it. A condition is not inside a loop, so there is no binding for
the card to name: the evaluator sets one per player itself and merges the clause
into a copy of the filter.

Which clause depends on the zone, and it is the split `validate_selector` already
spells out. The battlefield and the stack are **shared**, so a player is a
`controller` filter over the one pool; a hand, library, graveyard or exile
**belongs** to somebody, so a player chooses whose list to walk. Writing either
word inside `objects` is a load error rather than a clause silently overwritten,
and that guard earns its keep in one direction in particular: `controller:
"opponent"` written there is exactly the summing filter this leaf exists to
replace, so a card carrying it would look like it had asked for the pooled total
and quietly get something else.

`player` is not defaulted either. `each_opponent` and `each_player` are different
cards, and a default reads identically in the card file.

### The empty set has a right answer and a wrong one

`NO_PLAYERS_COUNT`, beside `NO_PLAYERS_LIFE` and biased the same way.
`max_count_of` over nobody is a plain 0, because "an opponent controls more lands
than you" has to be **false** at a table with no opponents and no land count of
yours is below zero. `min_count_of` returns something unreachably large, because
"each opponent controls more lands than you" over nobody *is* vacuously true and a
minimum of 0 would claim the opposite -- that every opponent is behind you -- at
the instant the last one died.

### What it unblocked, and what it did not

Knight of the White Orchid and Weathered Wayfarer both ship, verified through all
six gates. The Knight's expectation asserts the card landing and the library
**unchanged**: the verifier's fixed position gives you 30 lands to the opponent's
2, so the intervening-`if` is correctly false and nothing is fetched. Asserting a
fetched Plains there would have been asserting the bug.

Verge Rangers stays blocked, on two capabilities that are not this one:
`conditional_player_static` (player-wide statics are read by
`characteristics._player_static`, which never calls `_static_active`, so a
`condition` beside one loads clean and is then silently ignored) and
`look_at_library_top` (the only top-card static, `reveal_library_top`, is
deliberately public -- `serialize` writes `library_top` into every seat's view).
Its `per_opponent_count` need is closed; the record now carries only the other
two.

> `conditional_player_static` has since shipped -- see "A `condition` on a
> player-wide static was validated, stored, and never asked" at the top of this
> file. Verge Rangers is down to one blocker, `look_at_library_top`.

### Guarded by

`tests/unit/test_per_opponent_count.py`. The load-time guards, the two
aggregations and both empty-set biases, plus one position per call site: the
Knight's trigger fetching when an opponent is ahead and doing nothing when it is
level or when only the *pooled* total is ahead; the Wayfarer's ability offered and
withheld on the same three boards; and a test-only static (`t_land_watcher`) whose
"as long as" clause switches a keyword on and off, since no shipped card can carry
that half until Verge Rangers is unblocked. The pod case -- your five lands against
three opponents on two each -- is asserted at all four sites, because it is the one
board where the summing implementation and the printed card disagree.
## An additional combat phase — a repeated phase in a turn that only counts upward

### Overview

"After this main phase, there is an additional combat phase followed by an
additional main phase" (Relentless Assault, Resurgence, Savage Beating, Waves of
Aggression); "after this phase, there is an additional combat phase" (Combat
Celebrant, Aggravated Assault, Hellkite Charger). Three gap records named
`extra_combat`, and all three named the same blocker: `Step` is an ordered
`IntEnum` of exactly thirteen values that `turn.next_step` walks one integer at a
time, so a *repeated* phase had no representation at all. `state.cleanup_repeat`
was the only precedent for re-entering a step, and it is a bool hardwired to
CLEANUP; `delay` only defers an effect to one of four fixed steps.

### An extra phase is not a new representation, it is a bookmark

A repeated phase needs no enum value, because it is the same steps entered again.
What has to be remembered is that the phase the turn was *about to* enter is
still owed. So two fields:

- `GameState.extra_phases` — a queue of phase **kinds** (`"combat"`, `"main"`),
  not a combat counter, because Relentless Assault grants a main phase explicitly
  while Combat Celebrant grants none, and a counter could not tell them apart.
- `GameState.resume_step` — one bookmark, set on the first diversion and spent
  when the queue runs dry.

`turn._after_phase` is the whole mechanism, read only when a main or combat phase
ends. Three consequences, each of which the obvious implementation gets wrong in
a way that looks right in a one-line test:

- An extra combat granted in a **precombat** main is inserted in front of the
  combat the turn already had, and that combat still happens. Re-entering
  `BEGIN_COMBAT` and walking on from there would silently eat the ordinary combat
  phase and its postcombat main.
- An extra combat is **not** an extra main phase. The step order puts a
  postcombat main after every combat, so Combat Celebrant's extra combat returns
  to the bookmark instead of falling through into a main phase it never granted.
- "After this main phase" is not "right now". Aggravated Assault can be activated
  during an upkeep, and its extra combat waits for the precombat main to end
  rather than jumping in front of it — which is why the queue is read at phase
  *ends* rather than at every step boundary.

Two things then needed no code. The additional main phase is a `POSTCOMBAT_MAIN`
step by 505.1b, so the `postcombat_main` trigger fires for it — the firing site in
`begin_step` was already written per phase, with a comment saying "an extra combat
gives an extra postcombat main", in anticipation of a phase that did not exist.
And it is not an extra land drop: `lands_played` is reset by the untap step, so
rule 305.2 holds by itself.

`combat.start_combat` was already re-enterable (`end_combat` nulls
`state.combat`), and the once-per-combat attack bookkeeping is
`oid not in combat.attackers` on a fresh `CombatState`, so a creature untapped
between combats can attack again with nothing added.

### The op, and the seat it deliberately does not have

`extra_combat` takes `amount` (Fury of the Horde's two) and `extra_main`, and no
player. A phase belongs to the **turn**: Seize the Day is an instant, and cast on
an opponent's turn the extra combat is theirs. The loader refuses a `player`
rather than accepting one and ignoring it, and refuses a non-boolean
`extra_main`, because a dropped flag turns a four-mana sorcery into a lesser card
that loads and plays perfectly.

One divergence, recorded in [rules-coverage.md](rules-coverage.md): a turn takes
at most `MAX_EXTRA_PHASES_PER_TURN` extra phases. "Untap all creatures you
control; there is an additional combat phase" plus enough mana is a real printed
infinite combo and the rules let it run for ever; a self-play run cannot, and an
unbounded turn is a hung process rather than a loss.

### What it unblocked

**Response // Resurgence**, whose only blocked sentence this was — a split card,
so two entries and one object through the machinery `second_face` already had.
The other two records are still blocked on capabilities of their own and had this
need trimmed out rather than closed: Combat Celebrant on `exert`'s "hasn't been
exerted this turn" guard, Relentless Assault on a per-object
`attacked_this_turn` record.

## A mandatory additional cost — the half that "mandatory" did not deliver

### Overview

`additional_cost` had shipped with casualty and replicate, and its docstring
said a mandatory cost withdraws the free cast line. It did not. `legality`
built the plain cast variant first and only cleared it **when the cost was
unpayable** -- which is the same thing as never charging it. A player holding a
creature was offered both Village Rites lines side by side, and every automatic
driver (the verifier's `find_play`, the arena, the RL agent) took the first.
Village Rites was a one-mana draw-two that sacrificed nothing.

No shipped card was affected, because none carried a mandatory additional cost
yet. `tests/unit/test_additional_cost.py::TestAMandatoryCost` had the right
docstring and tested only loading, so nothing said otherwise. Found by an
authoring worker that refused to write the card and ran the gate to find out
why -- the pipeline catching an engine bug rather than a card one.

### The fix is a smaller statement, not a bigger one

The free line is withdrawn whenever the cost is mandatory. An unpayable cost
then falls out of the same statement: the loop adds nothing when the ceiling is
zero, and the spell is simply not castable. Everything is dropped rather than
just the plain variant, because 601.2f owes the cost on *every* way of casting
the spell -- an evoke or kicker line that skipped it would be the same bug
wearing a different name.

### The residual gate had to learn a new kind of claim

A card-level cost has no ability to carry its printed text, and gate 3 asks
each ability which sentence it implements. This never surfaced while the only
cards carrying one were instants and sorceries: `claimed_lines` treats
`spell_effects` as accounting for every line of a spell. Demon of Catastrophes
is a *creature* with an additional cost and no `spell_effects` at all, so its
printed cost went unclaimed and the card was rejected.

`_covered` already had this exact shape for `kicker`, `emerge`, `evoke`,
`ascend`, `uncounterable` and `cost_reduction`; `additional_cost` joins them,
and so does `Devoid`, which had the same hole (and is checked rather than
skipped -- a card printing Devoid while carrying colours has not implemented
it).

### What it unblocked

A template for the four printed shapes that carry the mechanic -- "sacrifice a
creature", "sacrifice an artifact or creature", "discard a card", and the
two-type variants -- reading only the *mandatory* form, since "you may
sacrifice" almost always drags a "When you do..." reflexive trigger along with
it, which is a separate capability.

The sweep that followed also collected everything waves 1a and 1b had freed
beyond the top of the queue, which an earlier `--limit` had been capping:
**994 -> 2,318 playable cards, coverage 3.1% -> 7.2%**.

## A mana ability with a rider — the painland, and the two wrong ways to say it

### Overview

`_sum_mana` rejected any effect in a mana ability that was not `add_mana`, so
the painland and Talisman families were unsayable — six of them in one deck.
Both obvious workarounds make a *different card* rather than an incomplete one,
which is why the gap records refused them:

- **Drop `is_mana_ability`** and the damage goes in as an ordinary activated
  ability — which uses the stack and is not offerable inside cost payment. The
  land could then never be tapped to help cast a spell, the only thing it is
  played for.
- **Use `pay_life`** and it is no longer damage from a source: unaffected by
  prevention, redirection, lifelink and every `dealt_damage` trigger, and moved
  from resolution to activation.

### The rider is held apart from the mana

`_split_mana_rider` splits the effects at the first non-mana op and puts the
tail on `Ability.mana_rider`. The two halves answer to different code:
`mana_options` is a constant tuple the payment solver reads while *planning*,
before anything is tapped, and the rider is a real effect that must not run
until the ability resolves. Mixed, either the solver believes a painland
produces damage or the damage never happens.

### One home, both paths

The failure worth designing against is a rider that fires only on manual
activation: the auto-payment solver taps lands for you without asking, so the
land would be painless exactly when the engine used it. `pay_mana` and
`Game.apply` both funnel through `activate_mana_ability`, so the rider lives
there and nowhere else — and the test taps a painland by paying a mana cost
rather than by activating anything.

### The whitelist is a hang, not a taste

`loader.MANA_RIDER_OPS` allows six ops that change a number and return. A mana
ability is activated inside cost payment: no stack to put a decision on, no
priority window to answer it in. An op that yields would hang the solver
mid-tap, so refusing at load turns a locked-up game into a card that will not
compile.

### The regression this nearly shipped

Reading the rider meant reading the sentence *after* the mana, and a basic
land's entire text is the reminder "({T}: Add {G}.)". The first version read
its closing bracket as a drawback it could not parse, refused the line, and
generated Forest with no mana ability at all — the single most deck-breaking
thing this generator can do, to every basic land in the format. The tail is now
unwrapped exactly as `_find_mana_lines` unwraps it, and a tail with no letters
left in it is not a rider.

### Two mana lines, not one

`_find_mana_line` returned the *first* tap-for-mana line. A painland prints
two, so Battlefield Forge generated as a Wastes with its real ability sitting
in the residual text. `_find_mana_lines` returns all of them and each becomes
its own ability, which is also what makes the painless `{T}: Add {C}` half a
real choice at the table.

### What it unblocked

54 cards authored. The Markov Chains deck goes 34 → 28 simplified.
Witness: `tests/unit/test_mana_rider.py`.

## Conditional taplands — a replacement that stops to look at the board

### Overview

Seven lands in a single imported deck, and 67 across the catalog, were marked
`unexpressible` on one missing word. `self_enters_tapped` had no `condition`,
and `zones._enter_battlefield` applied it unconditionally — so Clifftop Retreat
shipped as the worst dual in the format wearing the right name. The whole reason
that card is played over a Guildgate is that on turn three it is usually
untapped.

### Nothing new evaluates it

`evaluate_condition` in `effects/conditions.py` was already the standalone
evaluator for trigger intervening-if clauses. It had no caller on the
enters-the-battlefield path, and that was the entire gap: one field on
`ReplacementModel`, one guard in `compile_card`, one call in
`_enter_battlefield`. The condition is stored as the clause the permanent enters
*tapped* under — the negation of what is printed — so `condition` means here
what it means everywhere else in the DSL: when this applies.

### The ordering, which is the only real trap

`move_object` calls `_add_to_zone` before `_enter_battlefield`, so the land is
already on the battlefield when its own condition runs. "Two or more **other**
lands" therefore needs `exclude_self`, and a version without it counts the
arriving land and enters untapped a full turn early — every time, silently, in
the deck's favour.

### The fallback has a direction, and it is not symmetric

`proxy._unless_condition` reads three printed shapes: a basic-land subtype test,
a count of other lands, and a count of basic lands. Between them they carry the
checkland, slowland, fastland and battle-land cycles. Anything else returns
`None` and the land enters tapped **unconditionally**.

That asymmetry is deliberate and predates this change: the generator always
chose too-weak over too-strong, because a free untapped dual is a strict upgrade
over the printed card and distorts a game far more than a slow one does. So the
bug being closed here was always a card that was too weak, never one that was
too strong — and refusing to guess keeps it that way. "Unless you have two or
more opponents" is still a note, not a wrong condition.

### What it unblocked

37 cards authored on the next `--tier templates --retry`, including all seven in
the deck that prompted it. Witness: `tests/unit/test_conditional_enters_tapped.py`.

### A pipeline bug found on the way

`Queue.next_batch` excluded `unexpressible` from `--retry`, so `/extend-dsl`'s
documented harvest step could never harvest the cards its capability had just
freed — the one category that step exists to serve. Shipping the mechanic is
exactly the moment those cards should come back, and `--retry` is how that
moment is announced, so it now includes them. Automatic runs still skip them.

## Mutate — the subsystem that was a single choke point all along

### Overview

The census listed twenty-five `blocked` keywords and mutate was the last one
standing. Its entry read:

> the only genuine subsystem left: a `GameObject` is one card, and every choke
> point the other reversals leaned on — `card_of`, `chars`,
> `zones.move_object` — assumes exactly that.

The premise is true. The conclusion is backwards, and inverting it is the whole
implementation.

### One `CardDef`, synthesised once

**Because** `card_of` is a single choke point, a merged permanent can *be* one
`CardDef` — the card on top, with `abilities` set to the top's followed by
everything under it — built at merge time and written onto the object. Every
reader in the engine then gets the union for free:

| reader | asks for | gets |
|---|---|---|
| `chars` | name, types, P/T, colours | the **top** card's |
| `legality._activate_actions` | `card.abilities[i]` | the union, in one index space |
| `triggers.fire` | the same list | the same list |
| `stack.ability_of` | the same list | the same list |
| the serializer | `card_of(obj).id` | the top card |

Not one of those five changed. The subsystem the census was afraid of is the
*other* implementation — a list of cards per permanent, and each of those
readers taught to walk it and to invent an index space across it.

It composes, which is the test that it is the right shape: mutating onto an
already-merged pile reads `card_of(host)`, which is the previous union, so a
third card adds to it rather than replacing it.

### The pile is the genuinely new part

The cards underneath stay in `state.objects` and in **no zone list**. That is
not an invention — it is exactly where a card on the stack already lives — so
nothing that walks `state.battlefield` sees them twice, and no state-based
action, targeting selector or characteristics pass needed a special case.

`zones.move_object`, the single zone-change path, sends the whole pile wherever
the permanent goes. It reads `merged_under` **before** `reset_permanent_state`
clears it, which is the same snapshot-before-the-wipe that `had_counters` needed
for persist and undying.

### What needed no code

Counters, damage, auras, equipment, tapped status and summoning sickness all
survive a mutation. That is rule 702.140c, and it is also simply what happens
when the object is never touched: the host `GameObject` is the same object
before and after, and only its `merged_card` changed.

### Two timing decisions

- **"Over or under" is asked at resolution**, not as the spell is cast. 702.140b
  puts it there, and a choice made at cast time would be one made before anybody
  could respond to the spell — a different card.
- The target is `MUTATE_TARGET`, supplied by the rule the way `BESTOW_TARGET`
  is. It excludes tokens: a merged permanent is a pile of *cards*, and a token
  would have nothing to come back as when the pile breaks up.

### The census is empty

Twenty-five `blocked` rows, none left, and the finding held to the last one:
**`blocked` was a routing error rather than a size estimate.** Wither and infect
belonged at `damage_permanent`; regeneration and totem armor at `zones.destroy`;
dredge, madness and miracle needed a call-graph change rather than the
replacement whitelist; cascade and ripple only wanted a library scan; foretell
*is* suspend; champion and imprint are one exile link read from each end; level
up is `set_pt` plus a band; hideaway needed a permission, not a face-down
subsystem; bestow is `chars`, not `card_of`; and mutate is `card_of` being a
single choke point rather than an obstacle.

## Bestow — one spell, two permanents, and the wrong cluster

### Overview

The census filed bestow under "a second castable face", beside adventure and
aftermath, and it does not belong there. A second face is **two spells**. Bestow
is one spell that lands as two different permanents depending on what happens to
the thing it enchanted — so the mechanism is `chars`, not `card_of`, and none of
the second-face machinery is touched.

### The first alternative cost that is not only a price

The engine had six before this one, and every one of them changes what a spell
costs and leaves what it points at alone:

| cost | what it changes |
|---|---|
| evoke, prowl, spectacle, emerge, flashback, foretell, morph | the price |
| **bestow** | the price **and the target** |

702.103a makes a bestowed creature "an Aura spell with **enchant creature**", so
the target list is the *rules'*: `carddef.BESTOW_TARGET`, enumerated through the
ordinary targeting machinery so one line is offered per creature on the board.
No bestow card writes a target, and the loader has no need to refuse one —
`_cast_options` never looks at the card's list for that variant.

It lives in `carddef` rather than beside `MORPH_COST` in `legality` because both
`legality` and `stack` need it, and `stack` may not import `legality`.

### The type change is a pipeline input

While `attached_to` is set, `chars` drops `Creature`, adds `Enchantment` and the
`Aura` subtype, and zeroes the P/T. The moment it is not attached, the printed
creature is back.

`attached_to` is a field the `attach` primitive writes, and no layer can change
it — so switching a type line on it is reading an **input**, exactly as
`is_attached` does for reconfigure and `has_city_s_blessing` does for ascend.
Nothing here can come to depend on another static's output.

It is applied to the printed face *before* any layer, for `copy_overrides`'
reason: it is part of what the permanent **is** while attached, not an effect on
it, so an anthem or an animate afterwards layers on top exactly as it would on a
printed Aura.

### Two things that needed no code at all

- The state-based action that puts an Aura enchanting nothing into its owner's
  graveyard reads `state.card_of(obj).is_aura` — the **printed** card, which is
  a Creature. So it never sees a bestowed permanent. That is not luck: 702.103e
  says "it becomes a creature again" rather than "it is put into the graveyard",
  and reading the printed face is what makes the rule and the code agree.
- `_detach_all` already clears `attached_to` on everything attached to a
  permanent that is leaving, so the Spirit turns back into a creature the
  instant its host dies, with nothing to remember and nothing to clean up.

### What is left of the cluster

Mutate, alone, and it is the only genuine subsystem the census still names: two
permanents that are **one object**, when a `GameObject` is one card and every
choke point the other reversals leaned on — `card_of`, `chars`,
`zones.move_object` — assumes exactly that.

## A second castable face — adventure, aftermath, and the halves of a split card

### Overview

The census grouped four keywords under "a second castable face" — adventure,
aftermath, bestow, mutate — and called it the last cluster of buildable work.
Two of those four are one mechanism. The other two are a different problem, and
saying so is half the value of building this one.

| printed line | what it needs |
|---|---|
| "Cast this as its Adventure, then exile it; cast the creature later from exile" | a second face that is **cast**, plus a destination rider |
| "Aftermath — cast this spell only from your graveyard. Then exile it" | the same second face, offered from a different zone |
| "Bestow {5}{W} — cast this as an Aura" | one spell that **lands as two different permanents** |
| "Mutate {1}{G} — merge with target non-Human creature" | two permanents that are **one object** |

The first two are about which spell you cast. The last two are about what the
permanent turns out to be, and neither is reachable from here.

### The engine already had half of it

`back_face` is two `CardDef`s over one `GameObject`, and `card_of` is the single
place that picks between them — the choke point `transform` built. What was
missing is a second face that is *cast*:

| | back face | second face |
|---|---|---|
| how you get it | you **turn the permanent over** | you **cast the card as it** |
| when it is showing | while the permanent is transformed | only while it is a spell |
| may it be in a deck | no | no — and it is castable alone, so it matters more |

`card_of` asks the second-face question **first**, because "currently being cast
as this" is narrower than "the permanent is transformed". Nothing prints both,
and if anything ever did, the spell on the stack is the more specific claim.

### Only while it is a spell

`showing_second_face` is set inside `push_spell` and cleared in all three places
a spell can stop being one: it resolves, it fizzles, or it is countered. A card
that showed one face on the stack and another wherever it landed would be two
different cards to everyone watching.

`Game._cast` deliberately does **not** set it. It rebinds the face *locally*,
because every `return` between announcing a spell and putting it on the stack is
a cast that did not happen — and a card left showing the wrong face in hand
would be wrong for the rest of the game.

### Two words separate three keywords

| | cast from | after it resolves |
|---|---|---|
| a split half | hand | graveyard, like any spell |
| **adventure** | hand | exile — *and the front face may be cast from there* |
| **aftermath** | graveyard, and nowhere else | exile, finished |

Aftermath's "only from your graveyard" is expressed as **where the half is
offered**, not as a condition on the cast. There is no hand line to refuse: the
loop that walks the graveyard offers it and the loop that walks the hand does
not, and that is the whole restriction.

Adventure's exile is the **fifth rider** on the destination a resolving spell
goes to, beside flashback's exile, buyback's hand, rebound's exile and cipher's.
It is the only one of the five that has to read the **printed** card rather than
the one that just resolved, because `card_of` is answering with the half and the
flags belong to the card as a whole.

### Where the boundaries are

Each of these is a card that would otherwise be exiled for free:

- 715.3c exiles an Adventure **as it resolves**. Countered, it goes to the
  graveyard. Fizzled, it goes to the graveyard.
- The creature comes off its adventure onto the battlefield with `on_adventure`
  cleared by `reset_permanent_state`, so it cannot be cast out of exile twice.
- An Aftermath half is exiled with no flag at all, so nothing is offered out of
  that exile ever again.

### Timing is asked per face

Both faces' timings are read off their own type lines. Brazen Borrower is a
flash creature whose Adventure is an **instant**; a card gated on one face's
types would be castable at the wrong speed in one direction or the other.

### What this did not fix

The authoring pipeline still emits one card entry per answer file, so a
two-faced card is two hand-written entries linked by id — the same way
`bloodline_keeper` / `lord_of_lineage` already are. That is a pipeline change,
not an engine one, and the `split-cards-fuse` gap record is still open on it.

**Fuse** is also still open and is a different shape: "you may cast one or both
halves" is *one spell made of two faces*, and `card_of` answers with exactly
one.

## Hideaway — a permission, and a link read from the end that offers it

### Overview

The census filed hideaway as the one row waiting on **two** clusters at once:
face-down exile, and playing a card from exile. That is why it was ranked after
morph rather than beside the other one-offs — and it turned out to need neither
of them whole.

| printed half | what the census said it needed | what it needed |
|---|---|---|
| "look at the top four, exile one **face down**" | the face-down permanent shell | `revealed_to`, which foretell shipped |
| "put the rest on the bottom in a **random** order" | — | `move_object`, like every other zone change |
| "You may **play the exiled card** without paying its mana cost" | play-from-exile | the `play_exiled` op — the only genuinely missing piece |

### "Face down" is two different claims

A card hidden **in exile** and a permanent hidden **on the battlefield** are not
the same problem, and the census collapsed them.

Nothing may interact with a hideaway card while it sits there: it cannot be
targeted, it is not counted by anything, and the only question the rules ever
ask about it is whether its owner may play it. Hiding it is therefore just *not
showing it* — `revealed_to`, the private-information channel foretell already
uses.

A face-down **permanent** is on the battlefield where opponents can point at it,
so it needs derived characteristics of its own: a 2/2 colourless creature with
no name and no abilities, over a real card that is still there. That is the
`chars` shell morph and manifest built, and hideaway never touches it.

### The missing half was a permission, not a movement

The engine could already exile a card, and could already cast one for free
(`suspend.cast_for_free`, shared by suspend, foretell, cascade, ripple and
rebound). What it had no way to say was **"that one, from there"**.

`play_exiled` is that sentence. Its selector defaults to

```jsonc
{ "zone": "exile", "controller": "any", "exiled_with": "self" }
```

so the ordinary hideaway card writes no selector at all, and the default is
exactly the O-Ring link read back — the same read imprint makes.

### Why the link points that way

The engine now writes three exile links, all on the exiled card, each naming
whatever the ability that reads it needs to ask about:

| field | names | read by |
|---|---|---|
| `exiled_by` | the **exiler** | O-Ring's leaves-trigger, imprint's abilities, and hideaway |
| `haunting` | a creature whose **death** matters | a `creature_dies` trigger in exile |
| `encoded_on` | a creature whose **combat damage** matters | a `deals_combat_damage_to_player` trigger in exile |

Hideaway takes `exiled_by` and it has to. The *permanent* is what later says
"you may play the exiled card", so the permanent is what has to find it — and
the permanent is the exiler. That is imprint's direction, not haunt's, and the
Vault is still the one asking after it has been sacrificed to its own cost,
because the link is an oid and an oid outlives the zone change.

### The bottom of the library

Putting the unchosen cards back is the kind of step that looks like list
surgery, and doing it as list surgery leaves cards whose `zone` still reads
`EXILE` sitting inside a library — a corruption nothing else in the engine would
have noticed, because everything downstream trusts the zone field. It goes
through `move_object`, which is the single zone-change path for the same reason
`zones.destroy` is the single destruction path.

## Reconfigure — three abilities, and the one nobody counts

### Overview

The census filed reconfigure as "needs *unattach*, which the attach model has no
notion of — equipment may only move". That is exactly right about the op, and it
is one of three abilities the keyword actually is.

| printed half | mechanism | was it there? |
|---|---|---|
| "{1}: Attach to target creature you control" | the Equip ability | yes, unchanged |
| "{1}: Unattach this permanent" | the `unattach` op | no route at all |
| 702.151d — attached ones aren't creatures | `set_types` + `is_attached` | no leaf for it |

The third is the one that gets forgotten, and it is not cosmetic. These cards
are printed **Artifact Creature — Equipment**. Without 702.151d a reconfigured
blade pumps the creature it is on *and* attacks beside it — a strictly better
card, on a board where nothing looks wrong.

### `is_attached`, and why it is legal in a static

`GameObject.attached_to` is a field the `attach` primitive writes. No layer can
change it, so it is a pipeline **input** exactly as a counter is, and a static
switched by it cannot come to depend on another static's output. That is the
whole argument, and it is the same one `has_city_s_blessing` and
`top_of_library` made.

It is deliberately *not* the `{"attached": true}` filter key, which points the
other way — at the permanent this one is attached **to**. Both appear on the
same card, one on the buff and one on the type-changer, meaning opposite things.

### What reconfigure made reachable

Reconfigure prints the first Equipment that is **also a creature**, so it is the
first one whose own "target creature you control" can find itself. Rule 301.5c
says an Equipment can't equip itself, and until now nothing could ask.

An Equipment attached to itself is worse than illegal — it is a permanent
nothing detaches, because the buff reads `attached` and would feed itself for
ever. So it is refused in two places: the card's target selector says
`exclude_self`, and `attach` returns false on `aura_oid == target_oid` regardless
of what any card says.

### What `unattach` deliberately will not do

Auras. A state-based action puts an Aura attached to nothing into its owner's
graveyard, so an op that unattached one would be a destroy written in a way that
does not say so. No printed card unattaches an Aura, and the op has no business
inventing the one that does.

## Domain and coven — one leaf, because `count` fails them opposite ways

### Overview

The census filed both as `blocked`, separately, with almost the same sentence:
domain "counts basic land *types*, not lands", coven wants "three creatures with
different powers" and "no distinct-value count exists". They are one capability,
and the thing that shows it is *how* `count` gets each of them wrong.

| board | `count` | the card |
|---|---|---|
| five Forests | 5 | 1 basic land type |
| three 2/2s | 3 | 1 power |

Domain over-counts and coven over-counts, and neither is fixable by filtering:
`count` counts the objects that matched, and both cards want the number of
distinct *values* those objects carry. So one leaf, `{"distinct": {"of": …,
"objects": …}}`, with two `of` values — and exactly two, because those are the
two printed cards. A third would be vocabulary with nothing asking for it, and a
misspelling has to be a load error rather than a quiet fall back to powers.

### Coven needed nothing else

"If you control three or more creatures with different powers" is an ordinary
`cmp` against `{"const": 3}` once the left side exists. That is worth stating
because the census's phrasing — "no distinct-value count exists" — reads like a
condition-language gap and is a *value*-language gap; adding a condition leaf
would have been the over-build, and it would not compose into the "for each"
form domain needs.

### Why it may never be a static

Both readings are of **derived** characteristics, and deliberately so: an anthem
changes who has coven, and "all lands are Islands" changes what counts for
domain. That makes the leaf illegal in a static's `condition` for the reason
[layers-lite](adr/0001-layers-lite.md) gives — a static switched on by another
static's output is the dependency the fixed-order pipeline cannot have.

The static value language is a whitelist, so it already refused it and no code
changed. There is a test pinning that it stays refused, because the thing that
would break it is somebody widening the whitelist for an unrelated reason.

## Clash — a comparison across two libraries, and a binding to carry it

### Overview

The census filed clash as "`reveal` exists; needs a cross-player comparison of
the revealed cards". The reveal really was already there, and it was never the
obstacle. The obstacle is that **the value language reads one board.**

`mana_value_of` takes a target or a snapshot. Neither can name the top card of
an opponent's library: a target must be legal and visible, and a snapshot binds
what a selector found, while selectors have no notion of "the first one" in an
ordered hidden zone. `top_of_library` is the one leaf that reaches a library
top at all, and it answers a *filter* with a boolean — so it cannot produce a
number to compare against, and this needs two numbers at once.

### Why the result is a binding

The printed card is two sentences: "Clash with an opponent. If you win, draw a
card." Giving the op a `won:` block would collapse them into one, which reads
worse and, more importantly, takes the branch away from `if` — the op the DSL
already has for exactly that.

So `clash` writes `clash_won` into `EffectContext.bindings` and an ordinary
`{"binding": "clash_won"}` reads it. That made a **half-a-feature guard**
necessary, and it is kicker's guard word for word in a different place: a
`clash` nothing reads reveals two cards and does nothing, and a `clash_won` with
no clash behind it evaluates to 0 for ever. Both load cleanly and neither shows
on a board, so both are load errors.

`_mentions_condition` could not express either check. It tests `key in node`,
which is right for `{"kicked": true}` and useless for `{"op": "clash"}` — every
effect has an `op`, and dozens of nodes have a `binding`. So the walker was
split: `_mentions_pair(model, key, value)` matches the pair, and
`_mentions_condition` is now one line on top of the shared walk.

### The boundary that decides a sentinel

"A player wins if their card had a higher mana value **than each other card
revealed this way**" is vacuously true when no other card was revealed. So a
card beats an empty library, and an empty library beats nothing — including
another empty library, since neither is higher than the other.

That makes the no-card sentinel `-1` rather than `0`, and the case that
separates them is a card costing `{0}`. With a `0` sentinel, revealing a Forest
against an empty deck is a tie and the clash is lost. It is one character, and
the test for it is the only thing that would ever have found it.

## Connive — the same argument as explore, one clause further along

### Overview

Connive looks like three ops the engine already has: `draw`, `discard`,
`add_counters`. Writing it that way fails on the last one, and it fails
quietly — the counter has to count **the cards just discarded**, and there is no
expression for that set.

Every candidate is wrong in a way that resolves cleanly:

| spelling | what it actually counts |
|---|---|
| `{"count": {"zone": "graveyard", "controller": "you"}}` | everything already lying in the graveyard |
| `{"cards_to_graveyard_this_turn": true}` | every graveyard at the table, plus every earlier discard this turn |
| the op's own `amount` | the discards, not the *nonland* discards |

The third is the interesting one, because it is the version somebody writes and
ships. "Nonland" is the drawback the whole mechanic is priced around — conniving
away two lands is meant to cost you the counters — so counting the discards
instead is a strictly better card, and the difference only appears on the turn
your hand happened to be all lands.

### What was already right

Nothing under the op needed building. `ask_objects` already takes matched
min/max bounds, so "discard N" is mandatory by construction; `draw_cards`
already handles an empty library; and looping the pool per permanent gives "each
creature you control connives" its own draw and its own hand for free.

### The divergence, stated

701.47b keeps the draw and the discard when the conniving permanent has left the
battlefield and drops only the counter. Here an empty pool does nothing at all,
so killing a creature in response to its own connive trigger denies the draw as
well as the counter. Recorded in rules-coverage.md rather than papered over: the
pool is resolved at resolution, and a departed permanent leaves nothing to read
a controller off.

## Explore — the branch that names a card the condition language cannot

### Overview

The census filed explore as "`reveal` and `add_counters` exist; needs the
revealed card routed by type", which is the right diagnosis and understates why
routing it is a new op rather than an arrangement of old ones.

Every other conditional in the DSL is an `if` over the condition language, and
that language addresses objects through selectors, bindings and targets. The
card explore has to ask about exists in none of those: it is the top card of a
library, chosen by position, and it has to be tested *after* being revealed and
*before* going anywhere. `snapshot` cannot reach it either — it binds what a
selector already found, and the selector that would find it (`{"zone":
"library"}`) has no notion of "the first one".

So the nearest expressible spelling is `{"exists": {"zone": "library", "types":
["Land"]}}`: **is there a land anywhere in my deck**. In a deck that plays
Merfolk Branchwalker that is true essentially always, so the card would take the
land branch every time and draw instead of growing. It loads, it resolves, it
looks correct on the board, and it is a different card.

### `objects` is required, and that is the whole guard

Half the printed explore cards are sorceries. A defaulted `{"self_only": true}`
resolves to the ability's source, which for a sorcery is the spell on the stack
— not a permanent, so nothing is revealed and no counter is placed. The default
would have been tested on Merfolk Branchwalker, where it is correct, and would
have failed silently on the first instant or sorcery written with it. Requiring
the key costs three words on the creature cards and removes the trap.

### What fell out for free

Both of the other rule-text details needed no argument, only not being smoothed
over. Each permanent in the pool explores **separately**, because the loop walks
the library once per permanent rather than once — two exploring creatures reveal
two cards. And only the non-land branch asks a question, because 701.40a puts
the choice after "otherwise"; a yes/no on the land branch would let a player
decline a free card.

## Cards leaving the battlefield — an exit animation, and a reason

### Overview

A destroyed permanent used to stop being drawn, with no motion and no
explanation. On a board wipe half the table disappeared between two frames.

This was a broken feature rather than a missing one, and the failure is worth
recording because nothing reported it. `logic/events.ts` already produced a
`dies` beat carrying a `toll` and a danger flash. **The flash never once drew
anything.** `FxLayer` resolves anchors by looking up `[data-oid]` in the live DOM
at the moment a beat plays, `useGame.absorb` commits the new state and *then*
pushes the beats, and a card being destroyed is by definition a card the board
has stopped rendering — so the lookup returned null every single time and the
layer drew nothing. The code read as though the feature existed.

### Why the ghost is an overlay and not an `AnimatePresence` exit

The idiomatic answer is to wrap `Lane` in an `AnimatePresence` and give `Card` a
real exit animation. It is the wrong tool here, and the reason is timing rather
than taste.

React commits the new battlefield the instant a response lands, while the
narration queue may still be several beats behind — one response can carry an
AI's whole turn. An `AnimatePresence` exit fires on commit, so the card would fly
to the graveyard *before* the narration said what killed it. Syncing the two
means rendering a lagged battlefield, which contradicts "the engine is
authoritative, there are no optimistic updates" and desyncs every `data-oid`
anchor, drop target and legality check in the app. Not a local change.

Three smaller reasons, any one of which would still have decided it:
`CardStack` is an in-flow flex item, so a deferred unmount holds its slot and the
lane reflows *after* the animation instead of during it; `narration.skip()`
cancels an overlay in one line and cannot cancel a framer exit mid-layout; and a
dying commander goes to the command zone, which *does* render a card, so a
deferred `layoutId` for that oid would collide.

`FxLayer` already exists to draw what the board no longer knows about — the
spotlight resolves and draws cards that are in no rendered zone.

### Remembering where the card was

`logic/cardRects.ts` is oid → last known viewport box. `Card` posts its own in a
`useLayoutEffect` **cleanup with empty deps**: React runs that cleanup before it
detaches the node, so the element is still measurable. That is the entire
mechanism.

Cleanup-only rather than also-on-commit, which was the first design. Measuring
every mounted card on every render is roughly forty forced synchronous reflows
per server response, continuously, for the whole time the AI pump is running — to
refresh a number that exactly one card per departure ever reads.

Zero-sized rects are rejected. jsdom reports every box as 0x0, so without the
guard any unit test that mounted a board would fill the registry with
origin-anchored positions and ghosts would fly out of the top-left corner.

### Naming the culprit

`ZONE_CHANGE` had carried a `cause` since the beginning; what it had never
carried was *who*. `source` on a zone change is the object that moved, not the
thing that moved it, so no consumer could build a sentence of the form "X
destroys Y" — which is why the log said only "Grizzly Bears dies".

`move_object` now takes `by`, and the three removal ops pass `ctx.source_oid`,
which `EffectContext` had held all along and `op_destroy` simply threw away.
`by_card` is resolved *before* the move, because a creature that traded in combat
is out of `state.objects` by the time the event goes out.

Two decisions worth keeping:

**A gang block names nobody.** `state.last_damager` is a second map rather than
an ordering imposed on `damage_ledger`, which is rules-facing — the `damaged_by`
filter reads it, and it must not change shape for the sake of a caption. It
holds whichever source wrote last, which in a multi-block is an arbitrary one of
three, so `sba._creature_deaths` only attributes when the ledger has exactly one
damager. The caption degrades to a plain "Lethal damage", which is true.

**`by` and `cause` are on `ZONE_CHANGE` only**, not on `DIES` or
`LEAVES_BATTLEFIELD`. Nothing reads them there, and a new key in a *fired*
event's data can collide with a card's trigger bindings. `not_cause` being
loader-rejected on non-`enters` triggers protects matching but not bindings.

### One beat per wrath

A board wipe emits one `zone_change` per permanent, and a beat each at a readable
single-death pace is six seconds of stalled board. `beatsFor` groups each
**consecutive run** into one beat carrying several `exits`, and the FX layer
staggers the ghosts inside it — which is exactly what that layer's overlapping
short-lived effect lists were built for.

Consecutive, not global. "A creature dies, a trigger resolves, another creature
dies" is two moments, and merging them would put the second death on screen
before the trigger that caused it. A run survives only the events that produce no
beat of their own, which is what lets a wrath — whose every death also fires a
silent `dies` and `leaves_battlefield` — still read as one sweep.

`Beat.hold` is sublinear and capped: 420ms for one departure, never more than
820ms however wide the board. The ghosts keep flying after the queue has moved
on, exactly as damage numerals already do.

### Details that are not details

- **The destination comes from `data.to`, never from the cause.** Rule 903.9a
  redirects a commander to the command zone while leaving `cause` as
  "destroyed", so a destroyed commander is `to=command, cause=destroyed`. Routing
  by cause sends the ghost to a graveyard the card is not in. The caption carries
  both halves.
- **Tokens are the fallback, not an edge case.** They cease to exist the instant
  they leave the battlefield, so by the time the beat plays there is no card
  anywhere in the view. Face resolution is `findCard` by oid, then
  `findCardByDefId`, then a name plate — without the middle step a large share of
  every Commander game would animate nothing.
- **`CardFace` directly, not `StaticCard`**, whose own `initial`/`animate` pair
  fades it *in* on mount — the opposite of a death, on a node that would then
  fight the flight.
- **A card with no recorded position draws nothing.** Inventing one means the
  board's centre, which puts an opponent's creature in the middle of the viewer's
  own board on its way out.
- **The flight duration is divided by `SPEED_MULTIPLIER`.** The other effects get
  away with fixed durations because each is shorter than its (already divided)
  expiry timer; a 900ms flight is cut off mid-air at `fast` without it.
- **Only `from === "battlefield"` is narrated.** Two jobs at once: otherwise
  every draw, mill, discard and resolution earns a second log line, and a
  library-origin zone change carries a card id to *every* seat, so narrating one
  would put an opponent's tutor target in the log.

### The reason outlives the animation

`describeEvent` gained a `zone_change` case and **lost its `dies` case**. The
zone change strictly dominates it — `move_object` emits the two together and only
one of them knows the destination *and* the cause — so keeping both put two lines
in the log for one departure, the less informative of which could not tell a
removal spell from a legend rule and said nothing at all about exile.

`logic/removals.ts` folds the same log into oid → phrase for the notes under each
card in the graveyard and exile modal. Derived rather than stored: the server's
view of a graveyard is a flat list with no history, and giving it one means
persisting a cause per object for the whole game. Undo replaces the client's log
wholesale, which is exactly right here — the map rebuilds, and a rewound death
stops being reported without anything having to forget it.

### Where it is tested, and where it deliberately is not

The suites split by what they can see, and that line decided the coverage.

`tests/unit/test_zone_change_cause.py` pins the payload — the culprit named
through a real cast, a sacrifice cost naming what it paid for, the gang block
declining, the commander landing `to=command, cause=destroyed`, and
`last_damager` clearing at cleanup with the ledger it shadows.

`tests/events.test.ts` and `tests/labels.test.ts` own the grouping and the words,
including the load-bearing negative: a library-origin zone change returns null.
`tests/cardRects.test.ts` is safe in jsdom precisely because the registry never
touches the DOM.

The geometry lives in stories, because jsdom cannot see it.
`FxLayer.FliesToTheGraveyard` seeds the registry from the real cards on a real
board and asserts the ghost ends closer to the pile than it started — with
`motion: "real"`, since `reducedMotion` removes the transform under test and the
story would otherwise measure a ghost already parked on its destination and
assert nothing. `Card.RemembersItsRectOnUnmount` is the only tier that can prove
the layout-effect-cleanup contract at all: a unit test would assert against a
registry that had correctly refused to store a 0x0 box.

**e2e covers the log line and not the ghost.** `e2e/helpers.ts` pins the speed to
`instant`, and `narration.ts` short-circuits on that and drops beats rather than
holding them, so an e2e run cannot see a ghost without changing the harness lock
that keeps the suite fast. The Log is not speed-gated, so that is where a real
engine's real deaths are checked.

## Bolster, mentor, evolve — and the condition that could not see the event

### Overview

The census groups these three as wanting "derived-power comparisons in filters,
plus an extremum selector". Building them split the group in an unexpected
place: two were already expressible, one needed a genuine addition, and a
*fourth* thing was broken underneath all of them.

**Mentor was already expressible.** `_compare` in the selector language has
always evaluated a full value expression on the right, so "target attacking
creature with lesser power" is
`{"power": {"op": "<", "value": {"power_of": {"self": true}}}}`, read off
derived characteristics on both sides. The census row described the *shape* of
the question and was never checked against the comparison vocabulary that
existed.

**Bolster needed `extreme`.** "The creature with the least toughness among
creatures you control" cannot be a `_compare` clause: those test a candidate
against a value known in advance, and an extremum is only knowable once the
whole pool is in hand. So it narrows the pool after every other clause, and it
keeps ties — rule 701.36a has the player choose among equals, `choose_objects`
is already what asks, and breaking the tie by oid would make the answer depend
on the order permanents happened to arrive in.

### The bug under all of it

**Evolve did not work, and could not have.** A trigger's intervening-`if` was
evaluated with an `EffectContext` carrying no bindings at all, so
`{"power_of": {"binding": "subject"}}` — "that creature" — read **zero**. Evolve
compares the creature that entered against itself; with one side stuck at zero
the condition was false for anything with positive power, and the ability
silently never fired.

Nothing would have reported it. The card loads, the trigger matches, the
condition evaluates without error and returns the wrong answer.

`evaluate_condition` now takes the event's bindings, and `_matches` and `_queue`
build them from **one function**, so an intervening-`if` and the ability it
gates cannot disagree about what "that creature" refers to. That shared
construction is the actual fix; passing bindings to one of the two callers would
have been a subtler version of the same bug.

## Casting from the graveyard, generalised — escape and jump-start

### Overview

`keywords.md` names "casting from the graveyard, generalised past `retrace`" as
one of its six clusters, with six members. Three had already shipped separately
— retrace, flashback, embalm — and the useful result of finally looking at the
rest as a group is how little was left.

**Jump-start needed nothing at all.** "Cast this from your graveyard by
discarding a card in addition to paying its other costs, then exile it" is a
graveyard cost whose mana half happens to equal the printed cost, plus a
discard, plus the exile rider flashback already had. It has been expressible
since the day flashback shipped, and stayed on the census as `routed` because it
was filed under its own keyword rather than against the capability.

**Escape needed exactly one bit.** Same alternative cost, same legality
widening, same `exile_from_graveyard` cost kind — and one difference, which is
the entire distinction between the two keywords: flashback exiles the card and
escape does not, so escape is reusable and flashback is not.

### What shipped

`graveyard_cost`, which is the field's real name, and `graveyard_cast`, which
says where the card goes when it finishes — `"exile"` (flashback, jump-start) or
`"graveyard"` (escape). `flashback` stays as an accepted spelling, meaning
exactly the same slot, so no shipped card file changed and no card with escape
on it has to claim to have flashback.

Two guards, both refusing rather than resolving. Both names at once is a card
with two prices from the graveyard and no answer to what it costs from there. A
`graveyard_cast` with no cost is a card that claims to escape and is never
castable at all — the silently-inert card this pass exists to catch.

The rider applies on fizzling as well as on resolution, and so does the escape
exemption: an escape spell whose targets all left is back in the graveyard to be
escaped again.

### What is still in the cluster

Unearth and disturb, and neither is really "casting from the graveyard" any
more. Unearth is an *activated ability* from the graveyard that returns the
creature to the battlefield with haste and exiles it at end of turn — closer to
embalm than to flashback. Disturb is a cast that has to arrive on the card's
**back** face, which is `transform`'s choke point rather than this one.

## Block requirements — the mirror that is not quite a mirror

### Overview

Provoke, and the last of the five combat keywords `keywords.md` grouped as
needing work the evasion family did not. It routes it precisely: "`must_attack`
exists for requirements; this is the block-requirement mirror, which does not".

The engine had exactly one shape for compelling a player in combat, and it
compelled the attacking one. `must_block` is the other, and it is a separate op
rather than the same one with a flag, because a block requirement always names
*what* to block — "blocks this creature this combat if able" — where an attack
requirement names nothing. So it records an oid on the blocker rather than a
duration, and the two expire on different clocks: `must_attack` can outlive a
turn, since Trench Behemoth binds an opponent's *next* combat, while a block
requirement belongs to the combat that placed it.

### Where the mirror breaks, and why it matters

Attacking is not exclusive. A creature that must attack can always be added to a
declaration that already has others in it, so withholding "Done attacking" is a
complete enforcement.

**Blocking is exclusive**, and that changes the answer. A provoked creature that
blocks something else first cannot be retracted — declarations are built one
block at a time here — so `legal_blocks` then offers nothing, and the deadlock
escape in `legality._blocker_actions` hands out "Done blocking" anyway. That
escape is right and predates this (a four-player rollout found the Tromokratis
deadlock it exists for on turn 47), but it means enforcement at the finish alone
is *evadable by ignoring the requirement early*. So a block requirement narrows
what is **offered**: while a provoked creature is able to block the creature
that provoked it, that is the only block it is offered.

### "…if able", and the one subtlety in it

The same second half as attacking: a requirement never makes an illegal block
legal, so a tapped creature owes nothing. That is not decoration — provoke
*untaps* its victim first, precisely because the creature you most want to
provoke has just attacked and would otherwise be excused. The untap and the
requirement are two clauses and two ops, which is also what leaves room for the
lure family, which requires without untapping.

The subtlety is that "able" must be asked *ignoring the block it already made*.
Plain `can_block` returns false for a creature already blocking something, so
asking it there would let any provoked creature excuse itself by blocking
anything at all. `can_block` grew an `ignore_existing` flag for this, and rule
509.1c is the argument: the declaration must satisfy the maximum number of
requirements it can, and a creature that chose a different block was able to
make this one.

## Becoming untapped — a keyword that would have shipped never firing

### Overview

Inspired looked like the cheapest row in the census: "needs a 'becomes
untapped' event", and `UNTAPPED` had existed since combat was written.
`untap_permanent` has always fired it. One row in `TRIGGER_EVENTS` and done.

It was not, and the way it was not is the interesting part. **Inspired fires in
the untap step, and the untap step did not say what it untapped.** `untap_all`
emitted a single aggregate carrying a `count` and no `oid`, through
`state.emit` rather than `triggers.fire` — so it never reached the trigger bus,
and even if it had there was no permanent named for `source: "self"` to match.

Every other route to becoming untapped goes through `untap_permanent`, one event
per permanent. The untap step was the single exception, and it is the one that
matters: a creature that attacked untaps in its controller's next untap step and
almost nowhere else. Shipping the one-line version would have produced a keyword
that loads clean, reads as printed, and never triggers in a real game — which is
the exact failure this repo's gates exist to refuse, arriving through the one
door they do not watch.

### What changed

`untap_all` now fires per permanent, exactly as `untap_permanent` does. Nothing
on the frontend needed touching, which is worth stating because a new event
usually would: `untapped` is in the `SILENT` set in `logic/events.ts` and
`describeEvent` has never had a case for it, so the aggregate's `count` had no
consumer to lose.

### The sandbox detail the test needed

`GameBuilder.build` leaves `step_started` true — a position built at a step is
described as already *being* in it, turn-based actions notionally done. For
every other step that is invisible. For the untap step it means the untap does
not happen, so every position in `test_becomes_untapped.py` would have read
"nothing untapped" and the tests would have failed for a reason that has nothing
to do with the change. The file arms each position explicitly and says why.

## Becoming blocked — the four combat keywords with no event

### Overview

`keywords.md` grouped flanking, rampage, bushido and frenzy and said why: each
"wants a *trigger event* the engine does not have ('becomes blocked', 'attacks
and isn't blocked'), which is a different tier of work with frontend
consequences". They are one capability and not four, for the same reason the
evasion family was one and not five: both events are decided at the same
instant, when the block declaration closes, and neither is knowable a moment
earlier. "Isn't blocked" in particular is not an event that happens — it is the
absence of one, and it only becomes a fact once the declaration is over.

### Why `BLOCKS` could not stand in

It fires once per *blocker*, and it is about the blocker. An attacker blocked by
three creatures sees three unrelated events concerning somebody else; an
attacker blocked by nobody sees nothing at all. Everything these four keywords
ask is about the attacker, so the new pair is fired per attacker, from
`finish_blockers`, deliberately **outside** the `if combat.blockers` guard — the
unblocked half is precisely the case where that guard is false.

### Flanking needed one thing more

"Blocked by a creature without flanking" asks *which* creatures are blocking
this attacker. The `blocking` selector was a bare boolean, true of every
creature blocking anything — so on a board with two attackers flanking would
shrink the creature blocking somebody else. It now also takes a binding naming
the attacker, the shape `shares_a_type_with` and `exclude_binding` established.

That failure is worth naming because of how it hides: on a one-attacker board —
which is the obvious test to write, and the one that would have been written —
the boolean form is indistinguishable from the correct one. The test that
catches it needs two attackers and two blockers, one block each.

### The test harness, twice

Both rounds of failures in this run were the test lying, not the engine, and
both were the same lie in different clothes. Everything these keywords do is
"until end of turn", and the engine auto-passes out of combat into the next turn
when nobody has a response — so an assertion made after `apply` returns reads a
board `clear_until_eot` has correctly wiped. Rampage then looks like it did
nothing, which is exactly what a *broken* rampage looks like.

The fix is the one `test_turn_ledger.py` arrived at independently: assert the
turn boundary rather than hoping for it, and give the position an instant and a
land so priority genuinely stops. The second round was smaller and more
embarrassing: with no creatures to block with, the test skipped the block
declaration entirely — but the defending player is still *asked*, and
`finish_blockers` runs only once that declaration closes. No event fired, and it
read as the engine refusing to say "unblocked".

## Becoming a target — heroic, and ward, which was never the hard one

### Overview

The census had ward marked `blocked`, on this reasoning: *"it routes a cost to a
player who does not control the ability and inverts the outcome, and `may` — the
only optional-effect op — asks the controller and attaches no cost."* Every
clause of that was true when it was written and none of it was true any more.
`may` grew a `player` for Fact or Fiction and a `pay` cost for Seer's Sundial,
and Rhystic Study shipped the two together as `unless_pays`.

So the whole of ward's supposed blocker had already been built for a different
card, and what both it and heroic were actually waiting on was much smaller: an
event for *becoming a target*.

That is the census earning its keep in the direction it was written for — it
routes a keyword to a mechanism, and the routing was re-checked against an
engine that had moved. It is also the census being wrong, which is exactly what
its own "only `shipped` is machine-checked" caveat predicts.

### The timing is the mechanic

Rule 603.2d: these fire as the spell or ability is **put on the stack**, not as
it resolves. Ward exists to tax the opponent *before* the removal spell does
anything; a version firing on resolution is a refund, not a tax, and it would
still pass a test that only checked a counter appeared. So `announce_targets`
is called from all three push sites in `stack.py` — spells, activated abilities
and triggered abilities — rather than from `resolve`. Triggered abilities pick
their targets after the item is built, so that one calls it itself once they are
set.

### Two things `_matches` had to be told

Both are silent when wrong, and both are wrong in the direction that looks
plausible:

| | |
|---|---|
| **`player` on the event is the caster** | Every `controller` clause on this trigger asks *whose spell it is*. Read off the subject as most triggers are, the actor would be the controller of the creature being targeted — which is nearly always the trigger's own controller. Heroic would fire on the opponent's removal spell, and ward would never fire at all |
| **`source: "self"` is the target, not the spell** | For almost every other trigger the event's subject and its source are one object, so `_matches` accepts either. Here they are the thing being aimed at and the thing aiming |

### `counter` by `sid`

"Counter **it** unless that player pays" is not a targeted ability, and writing
it as one would let the ward creature's controller point it at a different
spell. The `becomes_target` trigger already carried the spell's `sid` in its
bindings — `_queue` has copied `sid` across for a long time — so `counter` grew
a `sid` form beside its `target` form, and the loader refuses a card carrying
both. Ward is then four lines of ordinary DSL with no new op behind it.

### The frontend half

The only tier of `/extend-dsl` work that genuinely forces it, and the only one
that fails no test if skipped. `describeEvent` gains "Alice targets Test
Warded", carrying the name of the *targeted* card rather than the spell, since
the cast line above already named the spell. `beatsFor` flashes the targeted
permanent in the `danger` tone. Without both, a ward payment dialog appears with
nothing on screen saying which creature it is about — the prompt arrives before
anything has visibly happened, which is precisely what the 603.2d timing
guarantees.

The player-targeting form of the event returns `null` from one and returns early
from the other: "targets a permanent" would be a lie, and the cast line covers
it.

## The per-turn ledger — six tallies the board cannot answer

### Overview

The first entry in the build order in [keywords.md](keywords.md), and it was
chosen the way that page argues for: not because one card asked for it, but
because *seven* keywords were waiting on the same missing piece of state, and no
demand-driven report could have shown that. Morbid, raid, bloodthirst,
spectacle, prowl, storm and gravestorm each want to know whether something
happened during this turn, and the board keeps no record that it did.

That is the whole justification. A creature in a graveyard may have been
discarded or milled rather than having died, and one that died last turn is
lying in exactly the same place. Once combat is over, a player who attacked
looks precisely like one who did not. These are counts of *events*, which is the
standing `cards_drawn_this_turn` already had, and adding a seventh selector
would not have reached any of them.

### The design decision: one fold, not six increments

`GameState.turn_ledger` (`structs.TurnLedger`) holds six tallies — creatures
died keyed by controller, the set of players who attacked, damage taken, life
lost, spells cast per caster, and cards put into graveyards. They are folded in
**`GameState.emit`**, in one method, rather than incremented at the six
primitives that cause them.

The draw tally makes the argument for the other placement — *"incremented in
`draw_cards` so nothing routes around it"* — and `emit` is that argument taken
one level further. Every tally here counts something that was already being
logged as an event, and `emit` is the single function all of them pass through.
So no emitter changed: not `combat.py`, not `primitives.py`, not `zones.py`. A
future effect that kills a creature or deals damage by some new route is counted
without anybody remembering to count it, and the ledger cannot drift from the
event log the player is reading, because it *is* that log folded up.

It also runs synchronously, while the object the event is about is still in
`state.objects`. That is why a dying creature can still be asked who controlled
it, and a card reaching a graveyard can still be asked whether it is a token —
neither fact had to be added to an event payload.

### Two boundaries that would have been silently wrong

| | |
|---|---|
| **Damage to a player is life loss** | Rule 118.2. Spectacle is printed on cards you cast *after* hitting somebody with a burn spell, and `damage_player` does not call `lose_life` — it decrements life and fires `DAMAGE_DEALT` itself. A `life_lost_this_turn` that watched only `LIFE_LOST` would read false in the one case the mechanic exists for. Damage to a player now counts towards both tallies; damage to a *permanent* counts towards neither, and the two are told apart by the event's own `to` field rather than by guessing from `oid` |
| **Cleared at cleanup, not at untap** | The opposite of `cards_drawn_this_turn`, and for the reason that one is the exception: the opening hand is drawn before turn 1 exists, so a draw tally cleared at cleanup would sit at seven all of turn 1. Nothing counted here can happen before the game starts, so it clears with `damage_ledger` — and it must, because "a creature died this turn" has to survive into the second main phase that reads it |

### The read side

Six value expressions rather than six condition leaves:
`creatures_died_this_turn`, `attacked_this_turn`, `damage_taken_this_turn`,
`life_lost_this_turn`, `spells_cast_this_turn` and
`cards_to_graveyard_this_turn`. Morbid is then an ordinary `cmp` against 1, so
the condition language needed nothing added to it at all — "did it happen" and
"how many times" are one question at two thresholds, and storm needs the number
anyway. Five take a player spec; `cards_to_graveyard_this_turn` does not,
because gravestorm counts cards put into *a* graveyard rather than into yours.

### What it unblocked

Three keywords moved straight to `free` in the census — morbid, raid and
bloodthirst are now a condition and a card, with no engine work left. The other
four turned out to want a *second* thing each, which the census now says
plainly: spectacle and prowl need an alternative cost that can be gated on a
condition, and storm and gravestorm need spell copying. Their counting halves
are done.

### A note on the test

`tests/unit/test_turn_ledger.py` could not use `pass_until` for any of its
"this lasts the whole turn" claims. It returns silently when no decision is
pending, and with nothing to respond to the engine auto-passes from combat
damage into the following turn — so a test waiting for the postcombat main
arrives two turns later, reads a ledger cleanup has correctly emptied, and
reports the clearing as a failure to count. `test_combat.resolve_combat` carries
a comment about the same problem. The fix is in two halves: a local helper that
asserts the turn boundary instead of hoping for it, and positions that hold an
instant and a land, so a legal cast exists and priority genuinely stops in each
step.

## Which creatures attacked this turn — the per-object half of the same record

### Overview

The ledger above recorded the **seat**: `attacked` was a `set[int]` of player
ids, and its own comment said why — *"a set rather than a count because raid asks
only whether it happened."* That is exactly right for raid, and it is the whole
of six mechanics. Two printed cards ask which *creatures*, and neither can be
written from it:

| | |
|---|---|
| **Relentless Assault** | "Untap all creatures that attacked this turn." A sorcery, so it resolves in a main phase, after the combat whose attackers it wants |
| **Windbrisk Heights** | "{W}, {T}: You may play the exiled card without paying its mana cost **if you attacked with three or more creatures this turn**." Activated in a postcombat main phase, which is the point of the card |

### Every near miss, and why each is a different card

| | |
|---|---|
| `attacking` | The closest selector key, and strictly **live** combat state: `selectors.matches` answers it with `state.combat and combat.attacking(oid)`, and `combat.end_combat` sets `state.combat = None`. In the phase where either card is used it is false for every creature, so Relentless Assault would untap nothing and Windbrisk Heights would read 0 — a card that looks implemented and does nothing, which is the failure the whole format exists to refuse |
| `tapped` | The tempting approximation, and wrong in **both** directions at once: it catches a creature tapped for mana or by a tapper, and misses a vigilant attacker — the creature Relentless Assault most wants to untap. Both halves are covered by tests, because an approximation wrong in only one direction is at least visible |
| `{"attacked_this_turn": "you"}` | The per-**player** value. It is 1 whether you swung with one creature or ten, so `>= 3` can never be true. Relaxing the comparison to `>= 1` is the trap: it loads, it passes every gate, and it ships Windbrisk Heights as a raid land that unlocks off a single attacker |
| `damaged_by` | The only other per-object turn ledger in the filter language, and it records damage *dealt* — so it misses an attacker that was blocked without connecting, and one removed before the damage step |
| `set_flag` / `has_flag` | Could record the fact, but only from an ability neither card prints, and the residual gate requires every ability's `text` to be a printed line. It is also one-way and never cleared, so the flag would mean "this game" rather than "this turn" |

### The design: one field, two readers, no new condition vocabulary

`TurnLedger.creatures_attacked` maps player id → the set of oids that player
declared. It is folded in `GameState.emit` from `ATTACKERS_DECLARED`'s own
`attackers` payload, which `combat.finish_attackers` fills from the **locked-in**
declaration — after attack requirements discharge and after banding — so no
emitter changed and none can route around it. Exactly the argument the six
tallies above make.

**`attacked` is now derived rather than stored.** It is `set(creatures_attacked)`,
so "did you attack" and "which creatures did you attack with" are one fact read
two ways and no write can leave them disagreeing. Every existing reader — raid's
value, the ledger tests — kept working unchanged, which is the point of keeping
the name.

The two readers are both ordinary vocabulary:

- the selector key **`attacked_this_turn`**, deliberately placed *outside* the
  `combat = state.combat` block in `matches` because it is the one attack
  question that is not about combat;
- the value **`attackers_this_turn`**, beside the other five ledger values.

So Windbrisk Heights' unlock is an ordinary `cmp` and the condition language
needed nothing added to it — the same claim the original ledger made.

### The boundary that makes oids the right thing to store

Rule 506.4: **removal from combat does not undo a declaration.** A creature that
attacked and then died, was bounced, or was removed from combat still attacked
this turn, so nothing is ever taken out of the record — it is cleared only with
the rest of the ledger at cleanup.

That is why `attackers_this_turn` is not spelled
`{"count": {"attacked_this_turn": true}}`. A count is over the *board*, and three
attackers one of which traded leaves the board count at 2 — Windbrisk Heights
locked in the very turn it was supposed to open, in the most ordinary line of
play the card has. `tests/unit/test_attacked_this_turn_objects.py` asserts both
numbers in the same position, 3 against 2, so the divergence is pinned rather
than described.

### What was deliberately left out

`attacked_this_turn` is **not** in `STATIC_FILTER_KEYS`. It would be safe there —
the ledger is not a derived characteristic, so no static could depend on another
static's output through it — but no printed card asks, and vocabulary with
nothing asking for it is vocabulary that invites a card to be written wrongly.
The same call `is_monarch` got in the static condition language.

### What it unblocked

Both cards, immediately: **Relentless Assault** (its `extra_combat` half having
landed in the previous run) and **Windbrisk Heights**, the first hideaway land in
the pool. Aggravated Assault, Seize the Day and Waves of Aggression print the
same untap clause and are now expressible with no further engine work.

## A word that wears off — "hasn't been exerted this turn"

### Overview

Exert needed no engine support and still does not. `docs/keywords.md` has called
it *free* since the census — an `attacks` trigger with `source: "self"`, a `may`,
and `skip_untap` for the price — and `tests/unit/test_exert.py` cashes that claim
rather than asserting it. Combat Celebrant is the one exert card that can attack
twice in a turn, because it grants itself the second combat, so it is the one
that prints a guard:

> **If this creature hasn't been exerted this turn**, you may exert it as it
> attacks. When you do, untap all other creatures you control and after this
> phase, there is an additional combat phase.

The guard is the whole of what was missing: a **turn-scoped record of the
choice**, per object. Without one the ability is offered again in the combat it
just made, exerts again, and the turn runs until `MAX_EXTRA_PHASES_PER_TURN`
stops it — a printed once-per-turn card playing as an unbounded loop.

### Every near miss, and why each is a different card

| | |
|---|---|
| `set_flag` / `has_flag` | The right shape with the wrong lifetime, and the one that looks right. `op_set_flag`'s own docstring calls it *"a one-way word written onto a permanent"*: `obj.flags` is a plain `set`, nothing in `src/automtg/engine/` ever removes from it, and `clear_until_eot` does not touch it. Renown depends on exactly that — it must never be re-earned. A guard written there reads "hasn't been exerted this **game**", which passes every one-turn test and makes a once-per-turn card work once per game |
| `once_each_turn` | An **activation** restriction. `loader.py` refuses it on anything that is not an activated ability — *"'activate_steps' and 'once_each_turn' restrict activating"* — and the exert choice hangs off a triggered ability |
| `max_per_turn` on the trigger | The nearest thing that is turn-scoped, and counted where the ability **queues**. A player who is offered the exert and declines has spent the turn's one trigger without exerting anything, so the second attack is denied a choice the card gives it |
| `resolutions_this_turn` | The same mistake one layer down: the ability resolves whether the `may` is taken or not, so a declined offer counts as an exert |
| `attacked_this_turn` | Per object and turn-scoped, and about **attacking** — which the creature did either way |

### The design: `set_flag`'s twin, not `set_flag` with a switch

`TurnLedger.object_flags` maps object id → the words it was given this turn,
written by the `set_turn_flag` op and read by the `{"has_turn_flag": …}`
condition. Cleared in `TurnLedger.clear` with morbid, storm, raid and the rest,
so the lifetime needs no sweep of its own and cannot be got wrong by a future
caller.

Two ops and two condition keys rather than one of each carrying a `duration`.
That is the call `skip_untap` and `freeze` already made — *"using either for the
other would be wrong in both directions, so they are two ops over two fields
rather than one with a flag"* — and it is worth more here than there, because
this mistake is **invisible on the turn it is made**. A card that reached for
`set_flag` behaves identically for a whole turn and is wrong only on the next
one.

The read is deliberately narrow: a condition on the ability's own source, exactly
as `has_flag` is. No selector key and no value expression, because no printed
card asks "each creature exerted this turn" — the same call the
`attacked_this_turn` work made about `STATIC_FILTER_KEYS`, for the same reason.

### The write goes inside the `may`

```jsonc
"trigger": {"event": "attacks", "source": "self",
            "condition": {"not": {"has_turn_flag": "exerted"}}},
"effects": [{"op": "may", "prompt": "Exert Combat Celebrant?", "effects": [
  {"op": "set_turn_flag", "flag": "exerted", "objects": {"self_only": true}},
  {"op": "skip_untap",    "objects": {"self_only": true}},
  {"op": "untap", "objects": {"controller": "you", "types": ["Creature"],
                              "exclude_self": true, "count": "all"}},
  {"op": "extra_combat"}]}]
```

Beside `skip_untap` and not around the `may`, because **declining exerts
nothing** — which is the one behaviour that separates this from every rejected
alternative above, and the test that pins it is the one that would have caught
each of them.

`skip_untap` is not the write site either, and could not be: it is the generic
"doesn't untap during its controller's next untap step", printed by cards that
freeze somebody else's creature. Exerting is a *choice its controller makes*
(701.40a), so a record folded into `skip_untap` would report a creature an
opponent tapped down as having been exerted.

### The loader's share

`set_turn_flag` with no `flag` is refused, the way `set_flag` is — it writes
nothing, so the guard reading it back never bites and the card plays as though
its once-per-turn clause were not printed. A `duration` on it is refused rather
than ignored: there is one duration and it is in the name, and a card asking for
another one is asking for `set_flag`. And `has_turn_flag` must be a flag *name* —
`true` stringifies to `"True"`, which nothing ever wrote, so the guard would
silently never fire.

### What it unblocked

**Combat Celebrant**, whose last blocked need this was: `extra_combat` landed two
runs earlier and closed the second half of its sentence. Authored at the agent
tier — no template, because the printed sentence is one of a kind in the pool and
a template that half-read it would make a cheaper card than the printed one.

The authoring verifier declines combat, so an `attacks` trigger cannot fire in
its sandbox and the card legitimately asserts the weak `{"zone": "battlefield"}`
expectation. The behaviour is covered where it can be driven:
`tests/unit/test_turn_flags.py` attacks, exerts, takes the extra combat, attacks
again, and asserts the second attack is offered nothing — then plays the greedy
line to the end of the turn and asserts the turn contains exactly two combat
phases rather than the twenty the cap would allow.

## Which permanents entered this turn — a ledger entry that outlives its object

### Overview

> **At the beginning of combat on your turn, if another Human entered the
> battlefield under your control this turn**, create two 2/2 red Human Knight
> creature tokens with trample and haste. Then if you control six or more
> Humans, draw a card.

Éowyn, Shieldmaiden — the **commander** of the Riders of Rohan deck, and the last
card in it still waiting on the engine. Everything on that line already loaded:
the Lieutenant-shaped `begin_combat` trigger, the token (`token_pool` added it
the run before), and the "six or more Humans" `if`. The intervening-if had
nothing to read. `TurnLedger` counted seven things and *entering the
battlefield* was not one of them, so `VALUE_KEYS` had no tally to `cmp` against.

### Every near miss, and why each is a different card

| | |
|---|---|
| `{"exists": {"subtypes": ["Human"], …}}` | The obvious one, and wrong in **both** directions. It is a query about the *board*: true when a Human has stood there since turn three and nothing entered — the trigger fires every combat, forever — and false when a Human entered this turn and died before combat, which is the ordinary line the card is printed for. Both halves are asserted, on one position each |
| `set_flag` / `has_flag` | Wrong lifetime *and* wrong shape. Flags are cleared only by `reset_permanent_state` on a zone change and never at cleanup, so the first Human to enter would leave the gate open for the rest of the game. And writing the flag needs a second `permanent_enters` ability that no printed line asks for, which the residual gate rejects — every ability's `text` must be a printed sentence |
| A per-player count of arrivals | The tally the other six ledger entries are shaped like, and it cannot say **Human**: a land drop, a Treasure token or an opponent's creature would all satisfy "something entered under your control this turn". The filter is not decoration on this card — it is most of the sentence |
| `permanent_enters` as a trigger | The right event, the wrong *tense*. A trigger fires when the arrival happens; the printed clause is checked at the beginning of combat and asks about the whole turn behind it, including arrivals that have since died |

### The design: snapshots, not oids

`TurnLedger.permanents_entered` is a list of `EnteredPermanent` records — oid,
controller, types, subtypes and colors, taken **as the permanent entered** —
folded in `GameState.emit` from `ENTERS_BATTLEFIELD` like every other tally, and
cleared in `TurnLedger.clear` with morbid, storm and raid.

A snapshot rather than the oid `creatures_attacked` stores, and the difference is
what can still be *asked* of a departed object. Its readers only count attackers
and reach for the ones still on the battlefield; this one is asked **which**
permanents entered, filtered by subtype — and once a permanent has left there is
nothing to filter: a token is popped out of `state.objects` entirely by the token
state-based action, a card in a graveyard reports printed characteristics rather
than derived ones, and `reset_permanent_state` has emptied whatever a static had
granted it. Characteristics are read **derived**, at the moment of entry, so a
changeling and a creature a static had made a Human both entered as Humans — the
call `combat_damage_types` makes for prowl, for the same reason.

`controller` is likewise controller-at-entry. "Under your control" is a fact
about the arrival: a creature that entered under an opponent and was stolen
afterwards did not enter under yours, and one that entered under yours and was
stolen away still did.

A **list** rather than a map, because both keys lose something printed. Keyed by
player it could not answer "another *Human*". Keyed by oid it would collapse a
flicker into one arrival, and rule 400.7 says that is two objects — a card
counting arrivals has to see both.

### One reader, and it takes a filter

```jsonc
// Éowyn's intervening-if, as the card writes it.
"condition": {
  "cmp": ">=",
  "left": {"permanents_entered_this_turn": {
             "controller": "you", "subtypes": ["Human"], "exclude_self": true}},
  "right": {"const": 1}}
```

The only ledger value that takes a filter rather than a player spec, and the
clauses are spelled exactly as `selectors.matches` spells them — `types` all-of,
`subtypes` and `colors` any-of — so an author who knows one knows the other.

`exclude_self` is the word **another**. Éowyn is herself a Human and may well
have entered this turn, which is exactly the case the word exists to exclude; it
matches on the *oid* of the recorded arrival, so it drops her own entry rather
than anything that merely looks like her.

No selector key and no `STATIC_FILTER_KEYS` entry: nothing printed asks to
*reach* the permanents that entered, only to count them — the call the
`attacked_this_turn` and exert runs both made, and for the reason they gave.

### The loader's share

`controller` is **required**, which is stricter than the selector language it is
spelled after. An omitted clause in a selector usually still resolves the printed
pool; omitted here it silently counts the opponents' arrivals too, and a card
that fired off an opponent's Human is a strictly better card that looks right.
`"all"` is how a future card says it really does mean anybody's. An empty
`subtypes` list is refused rather than read as "no filter", and `exclude_self`
must be a real boolean — `"false"` is a non-empty string, and truthiness would
turn "a Human entered" into "another Human did".

### What it unblocked

**Éowyn, Shieldmaiden**, the Riders of Rohan commander, whose last blocked need
this was. Authored at the agent tier through all six gates; no template, because
the sentence is one of a kind in the pool and `--tier templates --retry`
harvested nothing, as expected.

The authoring verifier declines combat, so a `begin_combat` trigger cannot fire
in its sandbox and the card legitimately asserts the weak
`{"zone": "battlefield"}` expectation. The behaviour lives in
`tests/unit/test_permanents_entered_this_turn.py`, which plays the two positions
`exists` gets wrong — a Human that has stood there since before the turn, and a
Human that entered and died — and asserts the trigger stays silent for the first
and fires for the second. It also pins the "Then" clause counting the tokens the
same resolution just created: six Humans draws, five does not.

## Transforming double-faced cards

### Overview

Bloodline Keeper // Lord of Lineage — the last of the seven cards the Edgar
Markov precon shipped a substitution for, and the one `rules-coverage.md` listed
under **Not implemented** in its own right rather than as a missing op.

It turned out to be far smaller than its reputation, for one structural reason:
`GameState.card_of` is a **single choke point**. Every reader of a card's
characteristics — the layers, legality, combat, the serializer — goes through
it. So a permanent showing its other face is one boolean on the object and one
branch in one function, and the rest of the engine followed with no changes at
all.

### The model

Two `CardDef`s, one `GameObject`. The back face is an ordinary entry in the same
card pool; `GameObject.transformed` decides which one `card_of` returns.

The three things that would each have been silently wrong:

| | |
|---|---|
| **712.13a** | a permanent that leaves and comes back enters **front face up**, so `transformed` is reset with the rest of the battlefield state. Otherwise a blink is a free upgrade to the 5/5 |
| **A back face is not a card** | no mana cost, never in a hand, a library or a deck. `validate_deck` refuses one and `test_every_card_works` skips casting it — "it cannot be cast" is not a defect for a thing nobody casts |
| **The link is derived** | the front names the back; the registry writes `front_face` on the back. Every guard asks `front_face is not None`, so a link authored in one direction only would quietly make a free 5/5 castable |

### The art, which is a face and not a card

Both faces share one Scryfall id — the id names the card. `image_url` had taken
a `back` flag since it was written and nothing had ever passed it; `CardArt.back`
is what does now, and it is the difference between Lord of Lineage showing its
own illustration and showing the one it just turned away from.

The catalog stores the card under its joined name, "Bloodline Keeper // Lord of
Lineage", which neither face matches on its own, so `CardIndex.lookup` grew a
`joined=True` mode anchored on either side of the `//`.

### Activation restrictions, which came with it

"Activate only if you control five or more Vampires." A `condition` on an
activated ability, checked by `legality` before the ability is offered and
nowhere else — rule 602.5c makes it a legality question, so an ability that was
legal when activated still resolves if the board changes underneath it.

It shares the `condition` field with a static's "as long as…" clause, since an
ability is static or activated and never both. The languages differ: a static
gets the narrow one so that no static can depend on another's output, and this
gets the full `if`-effect language, because nothing computed here is something
another condition could depend on.

### Two more sandbox gaps

`_satisfy_the_activation_condition` joins `_provide_the_tap_fodder` and the four
helpers before it. The sandbox's job is that "not activatable" only ever means
the ability is broken, and an activation condition nothing satisfies breaks that
the same way an unpayable cost did. It reads exactly one condition shape and
refuses to be clever: a helper general enough to solve an arbitrary condition
would be a second `evaluate` living in the tests, and the first thing it would
hide is a bug in the first one.

Separately, restoring the precon exposed a real bug in `deck_summary`. The
coverage map is written by an *import* and describes the proxies that import
generated; a card authored afterwards is played from the authored pool and its
proxy is dropped. Nothing said so here, so three cards of a **precon** reported
as "simplified" the moment they were implemented.

## The top card of a library, read and shown

### Overview

"Play with the top card of your library revealed. As long as the top card of
your library is black, this creature and other Vampire creatures you control get
+2/+1 and have flying." Vampire Nocturnus — two sentences, two separate
absences, and neither is worth anything without the other.

### The condition, and the near miss that would have shipped

A static may ask about pipeline *inputs* only, so that no static can come to
depend on another's output. The top card of a library is such an input: nothing
in the characteristics pipeline can change what is on top of a library.

The nearest thing the condition language already had was `exists` over
`{"zone": "library", "colors": ["B"]}`. That asks whether **any** black card is
anywhere in ninety-nine, which in a mono-black deck is true essentially always.
Written that way, Vampire Nocturnus is a permanent +2/+1 and flying — a strictly
better card than the printed one, and one that compiles, resolves, and passes
every gate looking exactly right.

`top_of_library` reads the one card. Its filter is a printed face and an owner
and nothing else, the same rule every off-battlefield filter follows; `zone` is
refused, since the zone is the whole of what the leaf names. An empty library
matches nothing, so the static is off.

### The reveal, which is not flavour

`reveal_library_top` is the only static in the table that changes **nothing**
about the rules. It grants no permission and moves no card — that is the whole
of what separates it from `play_lands_from_library_top`. It makes one card
public.

It is still load-bearing. Whether your team has flying is a fact you are meant
to know *before* declaring attackers, and the condition that decides it is
otherwise invisible: the card would work perfectly and be unpilotable.

So this is the rare static read by `serialize` and by nothing else, and the rare
engine change whose whole point is the UI:

- `library_top` on every player, `null` unless something reveals it, so the
  client needs no separate flag;
- sent to **every** seat rather than its controller's, because "revealed" means
  revealed and an opponent who cannot see it is playing against information they
  are entitled to;
- `findCard` searches it — a zone of one — or the preview rail blanks on the
  single card the whole mechanic exists to show;
- the library pile, normally the one inert pile on the orb, gets a gold rim, the
  card's name, and a hover that fills the preview rail.

### A harness gap found on the way

`tests/cards/test_every_card_works.py` reported Captivating Vampire's ability as
unusable. It was not: the sandbox had no way to pay a `tap_permanents` cost, so
"could not pay for it" had become indistinguishable from "the ability is
broken". `_provide_the_tap_fodder` joins `_provide_the_sacrifice`,
`_pay_the_counters`, `_stock_the_hand` and `_provide_the_target` — the same
family, added for the same reason each time.

## Selectors that describe one object in terms of another

### Overview

"Whenever a creature you control attacks, it gets +1/+0 until end of turn **for
each other attacking creature that shares a creature type with it**." Shared
Animosity, the third of the four Edgar Markov gaps, and the highest-ranked of
them on EDHREC by a wide margin.

The trigger was already sayable. `pump` on `{"binding": "subject"}` was already
the way to say "it". What was missing was the *amount*, and the reason it was
missing is structural: every selector key the DSL had compares a candidate
against something written into the card at authoring time. Both halves of this
clause point at whatever happened to attack, which is different every trigger.

### The two keys

| | |
|---|---|
| `shares_a_type_with` | the candidate's subtypes intersect those of the bound object. Derived on both sides, so changelings and granted types count |
| `exclude_binding` | drop the bound object from the pool |

### Why neither had a substitute

`subtypes` takes a literal list. The nearest reachable expression was
`{"count": {"attacking": true}}`, which counts every attacker regardless of type
— a materially different card that would have loaded, resolved, and looked
right.

`exclude_self` is the subtler trap, and it is why "each **other**" needed a key
of its own. It compares a candidate against the **ability's source**. For Shared
Animosity that source is the enchantment: not a creature, never attacking. It
would have removed nothing from a set of attackers, and every pump would have
been over by exactly one — the kind of wrongness nobody notices until a game is
decided by it.

### An unbound name matches nothing

Not everything. A trigger that did not bind what the card thought it did is a
bug either way, and the two failure modes are not equivalent: a card that pumps
nobody gets investigated, and a card that pumps the entire board wins a game
first.

### Tested end to end

`t_animosity` in the test pool carries Shared Animosity's printed text verbatim.
The unit tests hand `resolve_pool` a binding directly; the card test attacks
with three Bears and a Bird and reads the board, which is the only way to check
that the binding actually arrives from a real `attacks` trigger.

## Tapping other permanents as a cost

### Overview

"**Tap five untapped Vampires you control**: Gain control of target creature."
The first half of Captivating Vampire, and the last of its three gaps.

`tap` already existed and is a different thing: it is the `{T}` symbol, and it
taps the source. Nothing could charge a player for tapping *other* permanents.

### Why the `tap` op is not a substitute

It is the obvious workaround and it fails twice over:

- the taps would land on **resolution** rather than on activation, so they could
  be responded to and could fizzle while the ability still resolved;
- `can_pay` would never consult them, so the ability would be offered with no
  untapped Vampires on the board at all — which is the same as it being free.

### The shape it copied, and the one way it differs

`sacrifice` and `return_to_hand` are the same design: a selector over the
battlefield with a `count`, defaulting to `controller: "you"`, pooled by one
function that both `can_pay` and `pay` call so they cannot disagree about
whether the cost is affordable.

The difference is that the permanents **stay**. They untap on the next untap
step, which makes a cost of this shape repeatable in a way neither of the other
two is — and is exactly why it has to be charged at activation.

### Two rules that had to be got right

- **`tapped: false` is forced**, and the loader refuses a card that spells
  `tapped` itself rather than overriding it in silence. "Untapped" is in every
  printed line of this shape, and a cost that could re-tap an already-tapped
  Vampire costs nothing.
- **Summoning sickness does not apply.** Rule 302.6 restricts the `{T}` symbol
  in a permanent's *own* cost; this taps other permanents, and Captivating
  Vampire's ruling says explicitly that a Vampire which just arrived may be
  tapped for it. Getting this backwards would make the card unplayable on the
  turn it matters.

`is_tap_only` grew a clause with it, which is what keeps the mana solver from
treating a Springleaf Drum as a source it can tap without paying the rest.

## `add_subtype`, the op — one printed noun, two mechanisms

### Overview

"Gain control of target creature. **It becomes a Vampire in addition to its
other types.**" The second half of Captivating Vampire, and the half that makes
the first half worth doing: the stolen creature joins the swarm the deck is
already buffing.

`add_subtype` already existed — as a **static effect**. That is why the gap
record for this card called it "add_subtype exists only in `static_effects`",
and the distinction is the whole feature:

| | |
|---|---|
| the static | "Creatures you control are Vampires" — continuous, applies to whatever currently matches its filter, and ends the instant its source leaves |
| the op | "It becomes a Vampire" — written onto one object, and it stays there after the permanent that converted it is dead |

### The interesting part: a static that reads it

`characteristics._matches` matches a static's `affects` filter against the
**printed** card face, on purpose — it is what guarantees that no static can
come to depend on another static's output and reintroduce recursion into a
fixed-order pipeline.

That rule would have made this card do nothing visible. Captivating Vampire's
own anthem is "other Vampire creatures you control get +1/+1", so a creature
converted by the op has to be seen by the filter, or the conversion buys
nothing.

The resolution is that `added_subtypes` is object state, not a static's output.
Nothing in the pipeline can change it, so it is a pipeline *input* in exactly
the sense a counter or a tapped flag is — safe to read, for the same reason
`counters` has always been readable there. `_matches_printed` takes it as an
explicit argument so the battlefield path and the zone-counting path cannot
drift into disagreeing about it.

### Refused

`types` on the op raises rather than being dropped. "Becomes an artifact in
addition to its other types" is a different sentence, and a card that asked for
it and silently got only its subtypes would load clean and be wrong.

## Gaining control of a permanent

### Overview

"Gain control of target creature." Captivating Vampire, and one of the seven
slots the Edgar Markov precon shipped with a substitution in. `rules-coverage.md`
had listed control change under **Not implemented** since the beginning.

It turned out to be the smallest of the four Edgar gaps by a wide margin, and for
a structural reason: `GameObject.controller` is already a field, and
`state.battlefield` is **one shared list** rather than a list per player. Nothing
had to move. The whole change is that field plus the three rules that read it.

### What actually needed building

| | |
|---|---|
| Rule 302.6 | the creature has not been under its new controller since their most recent turn began, so `entered_turn` is reset — which is simultaneously the record of when control changed and the summoning sickness itself |
| Rule 506.4 | changing control removes a permanent from combat, or a creature stolen mid-combat goes on dealing damage for the player who no longer controls it |
| Rule 400.3 | **no code at all** — `move_object` was always owner-based, so a stolen creature that dies already goes to its owner's graveyard |

Plus the characteristics cache, because every static filtered on `controller`
now reads differently.

### The event, and why it needed one

`control_changed` is the first `EventType` added in a while, and it is the only
part of this that reached the frontend. Every other way a permanent arrives on
somebody's side of the board is a zone change; this one is not, so a log built
from zone changes alone would show a creature silently swapping sides. The card
slides between battlefield rows with nothing behind it, which reads as a
rendering glitch rather than a play.

### What was deliberately refused, and then built

**There was no until-end-of-turn form**, and `loader` raised on a `duration` key
rather than ignoring one. A `duration` that loads and does nothing turns Act of
Treason into a permanent steal — a strictly better card than the printed one,
and one that would pass every gate. That refusal was right for as long as the
alternative was a silent one; it is not an argument that the card should not
exist, and Zealous Conscripts is the card that came asking.

## Gaining control until end of turn

### Overview

"When this creature enters, gain control of target permanent until end of turn.
Untap that permanent. It gains haste until end of turn." Zealous Conscripts, and
behind it Act of Treason, Threaten, Harness by Force, Mark of Mutiny, Kari Zev's
Expertise and Insurrection. The other two clauses were already expressible; this
op was the whole blocker for the family.

`duration` on `gain_control`, spelled `permanent` (the default, so nothing
already shipped moved) or `until_end_of_turn`. The loader guard is **kept** and
narrowed rather than removed: every other spelling is still a load error, for the
same reason it always was.

### The handback is the feature

The steal was already written. What is new is one `TempEffect(kind="control")`
holding the two seats, and a pass in `clear_until_eot` that re-enters
`change_control` pointed the other way. It is a re-entry and not an assignment to
`controller` because a control change is three rules, and none of them is
symmetric with itself:

| | |
|---|---|
| **302.6** | it has not been under its *original* controller continuously since their turn began either — somebody else had it in between. The tidy wrong version saves `entered_turn` with the controller and restores both, which hands back a creature that is not newly under its controller's control |
| **506.4** | structural rather than observable: `state.combat` is `None` by the cleanup step, so no turn structure this engine has reaches a handback mid-combat. It is one branch inside a call being made anyway, and the alternative is a rule that holds only until somebody adds a phase |
| the cache | fully observable, and the one a hand-rolled handback loses outright: a creature stolen under an anthem is 3/3 going out and has to be 2/2 coming back |

### Which handback, which seat

Three ways to give the wrong permanent to the wrong player, and the store answers
each:

- **A permanent that left the battlefield is not resurrected.** Free:
  `clear_until_eot` walks `state.battlefield`, and `reset_permanent_state` empties
  `until_eot` on the way out. Act of Treason plus a sacrifice outlet depends on it.
- **Two steals unwind newest-first.** Both effects end in the same step; undone
  oldest-first the first handback finds the wrong controller and stops, leaving
  the permanent one seat from home.
- **A later *permanent* steal outlives this one.** The stored seat is validated
  against the current controller rather than trusted, so Mind Control cast on a
  creature somebody already Act of Treason'd does not evaporate at end of turn.

### Ordering inside the cleanup step

Rule 514.2 wipes damage and ends "until end of turn" effects in one turn-based
action, so the handback happens in the same pass that zeroes damage, and the
`control_changed` it fires is a trigger like any other — which is 514.3a, the
rule that makes the cleanup step repeat.

## The discard trigger — an event that was fired but never listened to

### Overview

"Whenever an opponent discards a card, you may gain 3 life." Sangromancer, and
the last entry in `precon_deficits.json`.

Nothing was missing from the rules engine. Discarding has always been modelled —
rule 701.8, `primitives.discard_cards`, an `EventType.DISCARD` fired once per
card since the beginning, narrated in the frontend log. What was missing was a
name for it in `TRIGGER_EVENTS`, so no card could listen: the event was emitted
into a log that only the UI read.

One row in `TRIGGER_EVENTS`, one entry in `OBJECT_SUBJECT_TRIGGERS`, one name in
`_actor`'s list. The card was then expressible with no new op, no new effect and
no new event.

### Which player the clause is about

`controller` names the player who **discarded**, and it defaults to `"you"` —
the trap the Sengir Vampire run wrote down, where an unqualified trigger loads,
looks implemented and watches the wrong seat forever. Sangromancer needs
`"opponent"`, and the test asserts both directions, because a trigger that fires
on everything passes a one-sided test by accident.

The actor is read off the *event* rather than off the discarded card, which is
why `discard` appears in `_actor`'s explicit list even though it also has an
object subject. By the time the trigger is collected the card is in a graveyard
and its controller has been through `reset_permanent_state`; `discard_cards`
puts the discarding player on the event, so that is the copy to trust.

### Every discard is a discard

The two that matter and are easy to miss, because a version that missed them
would still pass a test written around a discard *spell*:

- The cleanup step's trim to hand size (rule 514.1) — the commonest discard
  there is at a real table.
- A cycling cost (rule 702.29a), which pays by discarding the card.

Both run through `discard_cards`, so both fire it, and both are pinned. And one
trigger per **card**: `discard_cards` fires per oid, so an effect that takes two
cards is two triggers and six life.

### Ships

Sangromancer's second printed line. `precon_deficits.json` is now **empty** —
every hand-written card in the pool clears all six authoring gates, which is the
first time that has been true since the audit started running over
`data/cards/`.

## Cards drawn this turn — counting an event instead of the board

### Overview

"{T}: Add {C} for each card you've drawn this turn." Kydele, Chosen of Kruphix,
and the last card in `unsupported-cards.md`.

The mana half of it already worked. Variable mana abilities shipped one run
earlier — an `add_mana` may carry an `amount`, evaluated at activation and
threaded through `costs.mana_produced` so the offer and the payment cannot
disagree. Kydele was the one card that change did not reach, for a reason that
had nothing to do with mana: every multiplier the value language could express
was a question about the **position**, and hers is not.

### Why no existing leaf could stand in

`{"count": …}` walks a zone and counts objects. `cards_in_hand` counts a hand.
Both are the same number as "cards you've drawn this turn" only until something
is played, discarded, bounced or drawn on an opponent's turn — and the
divergence runs the wrong way, because the cards that make Kydele worth playing
are precisely the ones you drew *and spent*. A Kydele built on `cards_in_hand`
taps for less exactly when the deck is working.

So it needed state that nothing on `PlayerState` had: life, zones, mana, land
drops, commander tax and damage, the city's blessing — none of them a tally of
an event.

### Where it lives, and when it resets

`GameState.cards_drawn_this_turn`: player id → draws this turn. Incremented in
`primitives.draw_cards` rather than off the `draw` event, so there is no path by
which a card travels from a library to a hand without the tally seeing it.

Cleared by the **untap step**, which is the interesting decision. The obvious
move was to copy `damage_ledger`, the per-turn ledger that shipped immediately
before this one, and clear at cleanup. Two things make that wrong, and both
produce a wrong number rather than an error:

- **The opening hand is not drawn during a turn.** Rule 103 sets the game up
  before turn 1 begins, and `_opening_sequence` draws seven cards — fourteen
  after a mulligan — through the same `draw_cards`. Clearing at cleanup would
  leave all of it in the tally for the whole first turn, so a Kydele in an
  opening hand would tap for seven the moment she landed.
- **Cleanup is still this turn.** Rule 514.3a hands priority back when cleanup
  triggers something, and a Kydele activated in that window has still drawn what
  she drew.

And it is keyed by player but lives on the state rather than on `PlayerState`,
because it clears **once per turn, not once per seat**. `lands_played` is the
engine's other per-turn counter and it resets in the active player's own untap,
which is right for a land drop and wrong here: you draw on other players' turns
too, and a Kydele that forgot an instant-speed draw from an opponent's end step
would be quietly the wrong size on your own turn.

### The one way it differs from a board count

Rule 605 says a mana ability never stops to ask, and this asks nothing — it only
looks, which is the same standing `counters_on` has, so `MANA_AMOUNT_FORBIDDEN`
lets it through where `x`, `binding` and `loop_value` are refused.

But unlike a board count, this multiplier can *move at instant speed*: drawing a
card is something a player can do with a payment already open. That makes "read
the amount at activation, before the tap" load-bearing rather than merely tidy,
and `test_cards_drawn_this_turn.py` pins it — the offer changes when a card is
drawn between the two, and the tap pays what the tally says at that moment.

### Ships

Kydele, Chosen of Kruphix, into the hand-written pool with the rest of the
Simic cards, through all six authoring gates. `unsupported-cards.md` is now
empty: nothing in the queue is blocked on a capability the DSL cannot express.

## Ascend — the first per-player designation, and the last entry in the report

### Overview

"Ascend (If you control ten or more permanents, you get the city's blessing for
the rest of the game.)" plus "This creature has flying as long as you have the
city's blessing." Skymarcher Aspirant, and both printed lines were blocked: one
because there was nothing to grant, the other because there was nothing to ask.

This reverses a documented decision. `rules-coverage.md` listed "the monarch,
initiative, day/night, and other designated-player mechanics" under Not
implemented, and the city's blessing is exactly one of those. It is the only run
in this sequence built against the plan's own advice — the recommendation was to
refuse it, and the instruction was to build it.

### A state trigger, not a triggered ability

Rule 702.131a, and it is the whole design. Ascend is not an *event*: a player at
nine permanents who plays a land gets the blessing at the instant of the tenth,
with nothing having fired, and gets it on an opponent's turn just as readily.
State triggers are checked whenever state-based actions are, use no stack and
cannot be responded to — so `_ascend` lives in the SBA pass beside the legend
rule. A trigger-plus-counter version would be a different card in the direction
that matters, because a re-checked trigger would come and go and the blessing
never does.

### Player state, not object state

`PlayerState.has_city_s_blessing` is the engine's first genuinely per-player
designation. `monstrous` is the closest existing one-way flag and is wrong in
all three respects that matter: it lives on a `GameObject`, so
`reset_permanent_state` clears it on any zone change; it is set by an op
resolving from the stack rather than by a continuous check; and it cannot be
shared between two cards.

The blessing has to survive the permanents leaving, survive the Ascend card
leaving, and be visible to every card the player controls — so a second Ascend
card printed later reads the blessing a first one granted. All three are tests.

`ascend` is a card-level field rather than a `Keyword`, because the enum's
members are read off *derived characteristics* by `grant_keyword` and the
evasion checks, and Ascend is neither granted nor evasive.

### The residual gate needed telling

"Ascend" is a printed line no ability carries, exactly like "Kicker {1}{U}" — the
mechanic is a state trigger, so there is nothing for an ability's `text` to hang
on. `verify._covered` has one clause per card-level field of that shape, and now
has one more.

## Flashback — three pieces, and the third does not fall out of the other two

### Overview

"Flashback—{1}{U}, Pay 3 life. (You may cast this card from your graveyard for
its flashback cost. Then exile it.)" Deep Analysis and Increasing Devotion are
the witnesses, and between them they need every piece.

This reverses a documented decision: `rules-coverage.md` listed "flashback and
other graveyard casting" under Not implemented. That line is retired.

`retrace` is the near miss and is wrong in every particular. It is the only
field that widens legality to the graveyard, but it is a bare boolean whose cost
is hardcoded to a discarded land and charged *in addition* to the printed cost,
so it can name no alternative price at all — Increasing Devotion would cost
`{3}{W}{W}` plus a land instead of `{7}{W}{W}`. It is also deliberately
reusable, which is the opposite of flashback. A card may now not have both.

### The three pieces

**The cost.** `CardDef.flashback` is a full `Cost`, not a `ManaCost` like
`evoke`, because Deep Analysis charges life too. The mana half replaces the
printed cost and everything else is an additional cost paid after it, in the
order rule 601.2g gives — the same two-step `retrace` already used, and
`Cost.without_mana()` is what splits them so legality can test the halves
separately.

**The once-only rider.** A spell cast this way is exiled rather than put into a
graveyard, on resolution *and* on fizzling. Without it the card is flashed back
forever, which is a different card and one that wins the game.

**`cast_from_graveyard`.** An engine could implement flashback casting perfectly
and Increasing Devotion would still be wrong, making five tokens where it prints
ten. `zone_is` cannot answer it: it reports the source's *current* zone, which
for any resolving sorcery is the stack, identically whether it was cast from
hand or from a graveyard. So it is a flag on the object, following the `cast_x`
/ `cast_kicked` / `cast_evoked` precedent exactly.

### The ordering that had to be right

The flag is written **before** `spell_effects` run, not after. Every sibling
flag (`cast_x`, `cast_kicked`, `cast_evoked`) is set after resolution, because
they are read by *enters-the-battlefield* triggers on the permanent that arrives
— by which time the spell is done. `cast_from_graveyard` is read by the spell's
own effects while they run, so copying the sibling placement would have made the
condition always false and Increasing Devotion always make five.

### Also repaired

Deep Analysis printed "Target player draws two cards" and the pool had it
drawing for its controller unconditionally. It now has the target.

## The chosen creature type — a Tier C run that was Tier A

### Overview

Vanquisher's Banner, EDHREC rank 369 and the second-best-ranked card the report
ever carried. It asks the same question from both filter languages:
"Creatures you control **of the chosen type** get +1/+1" is a static filter,
"whenever you cast a creature spell **of the chosen type**" is a trigger filter.

### The part that did not need building

The gap record asked for a new `DecisionKind.CHOOSE_TYPE` and the whole Tier C
chain behind it — `enums`, `actions.GENERATOR_DECISIONS`,
`legality._choice_actions`, `game.apply`, a new `ask_*`, and the authoring
verifier's auto-answer table, which the skill warns is not optional because an
unanswerable kind hangs the verifier for every card.

None of it was needed. `ask_mode` already asks "pick one of these labels" and
returns the index, which is exactly this question — so `_choice_actions` (generic
over `decision.options`) and the verifier's `_answer` (which falls through to
"take a real choice") both worked untouched. A `CHOOSE_TYPE` kind would have
been the same decision wearing a different name.

That is the Fact-or-Fiction lesson the skill opens with, and this is the second
time in the sequence it turned a run into a much smaller one — the first was
Rhystic Study.

### What shipped

`GameObject.chosen_type`, a `choose_type` op, and
`characteristics.resolve_chosen_subtypes` — one substitution applied wherever a
filter is about to be matched, in the static path and the trigger path both.

Not at load time: the choice does not exist until the permanent is on the
battlefield. And **before a type is chosen the filter matches nothing**, which
is the half that matters — falling back to "match everything" would make the
Banner a global anthem while the choice was pending, the same failure the
spell-cost-reduction run hit for real.

The choice lives on the object rather than the card, so two Banners choose
independently and a Banner that leaves and returns chooses again.

The prompt offers every creature subtype the card pool contains (119 of them),
sorted. The rules say any creature type; a type no card in the game has is a
choice with no consequence, and the full Comprehensive Rules list would make the
prompt unusable without changing how any card plays.

### A deadlock this run happened to find

`tests/ai` went red, and not for any reason to do with chosen types: a
four-player rollout reached turn 47 with **zero legal actions** at a
declare-blockers decision.

The cause is `require_all` — Tromokratis' "can't be blocked unless all
creatures defending player controls block it". Declarations are made all at once
in the rules and one block at a time here, so a player who blocks it with one
creature and then finds no second legal block is stuck forever: no
`ADD_BLOCKER` left to offer, and `blocks_valid` withholding "Done blocking".

Pre-existing and latent; the Banner only changed the random trajectory enough to
walk into it. Fixed at the escape rather than at the rule: when nothing can be
added and the declaration is still invalid, "Done" is offered, and
`finish_blockers` retracts the blocks that were never legal. "No creature blocks
Tromokratis" is exactly what the rules would have produced, so nothing is
conceded — and `blocks_valid` keeps its meaning, which is what let the existing
`TestRequireAll` tests stand unchanged.

A first attempt refused the uncompletable block up front instead, in
`legal_blocks`. It broke two passing tests and was reverted: it changed what is
*legal*, where the bug is only about what is *reachable*.

### The divergence

The printed line is "**as** this artifact enters" — a replacement effect that
cannot be responded to. `zones._enter_battlefield` applies enter-replacements
synchronously and cannot stop to ask, so this is a `self_enters` trigger and the
type is chosen a moment after the permanent arrives. Recorded in
`rules-coverage.md` rather than papered over; the window is observable only by
another trigger ordered between the two.

## Embalm — the graveyard as a place you activate from

### Overview

Angel of Sanctions, and the last card in the report that two earlier runs had
already half-built. Cycling made `active_zones` real for activated abilities and
gave `legality` a walk over zones other than the battlefield; the
exile-until-leaves run three commits ago shipped the card's other printed line.
What was left was the graveyard itself, and the copy.

### The zone half

`legality._activate_zones` now walks the player's graveyard as well as their
hand. The safety rule is the same one cycling introduced and now has two ways to
be satisfied: an activated ability offered outside the battlefield **must** have
a cost that removes its source from that zone, or it is an infinite engine —
a card whose ability costs only mana could be activated forever without leaving.
Cycling discards itself; embalm exiles itself from the graveyard. The loader
checks both and accepts either.

`Cost.exile_from_graveyard` and `sorcery_speed_only` already existed, which is
why this was one zone rather than a mechanic.

### The copy half

A token copy is a token whose `def_id` is the original's — right, because a copy
copies the printed card and not the counters and damage piled on it, but it
leaves "except it's a white Zombie Angel with no mana cost" nowhere to live: the
token has no card of its own.

So the exception rides on the **object**, as `copy_overrides`, deliberately
small: replacement `colors`, *added* `add_subtypes`, and `no_mana_cost`. Applied
to the printed face before any layer, because the exception is part of what the
token is rather than an effect on it — an anthem afterwards layers on top
exactly as it would on a real card. Anything richer belongs in a real
copiable-values layer, which this engine does not have and did not need here.

`no_mana_cost` is not decoration: the token's `def_id` is the Angel's, so
without it a mana-value query reports 5 for a token that has no cost at all.

### A test helper that had aged

`tests/cards/test_every_card_works.py` places a card in "the zone the ability is
offered from", and was written when that was battlefield-or-hand — so it put the
embalm card in *hand*, found no activation, and failed. It now uses
`zone_list(zone)` and puts the card wherever the ability actually says. That is
the pool-wide gate doing its job: the change was fine, the harness's assumption
about how many zones exist was not.

## A damage ledger — remembering who hurt what

### Overview

"Whenever a creature dealt damage by this creature this turn dies, put a +1/+1
counter on this creature." Sengir Vampire, and the clause is a *relationship*
between two objects across a span of time rather than a characteristic of
either. Nothing recorded one: `damage` applied damage and remembered nothing
about who dealt it.

### Where it had to live

The awkward part is **when** the question is asked — about a creature that has
already died. So anything stored on the victim is wrong by construction, because
`reset_permanent_state` wipes it on the way to the graveyard, which is the exact
moment the trigger needs it.

Hence `GameState.damage_ledger`: victim oid → the oids of everything that has
damaged it this turn. Written by `damage_permanent`, cleared during cleanup
next to rule 514.2's "remove all damage from permanents" — a ledger that
outlived the turn would let Sengir grow off a creature it hurt yesterday.

This is the second of the two ledger-shaped capabilities in this sequence, and
they were deliberately kept as separate runs. The other, `exiled_by`, sits on
the *object* because the thing that goes away there is the source, not the
victim; here it is the victim that goes away, so the storage had to invert. Two
different lifetimes, two different survivors, and merging them would have hidden
that.

### Read back through a filter

`{"damaged_by": "self"}` on the trigger. Bare `creature_dies` fires on **every**
creature death anywhere, which is a strictly stronger card — and one that looks
right in almost every game where Sengir is the one doing the killing.

### Two traps the test now pins

`TriggerModel.controller` defaults to `"you"`, so an unqualified `creature_dies`
only sees your *own* creatures dying. Sengir's victims are usually an
opponent's, so the default made the ability load, look implemented, and never
fire. That cost a debugging cycle and is now written down in card-dsl.md.

And the blocker has to be able to block: Sengir flies, a ground bear never
blocks it, nothing dies, and a test built that way passes for the wrong reason.
The first version of this test did exactly that.

## Exile until it leaves — a link that outlives the thing that made it

### Overview

Oblivion Ring, and behind it the whole Banishing Light / Fiend Hunter / Angel of
Sanctions family. All of them wait on one thing: a record, written when a
permanent exiles something, readable by a *later and separate* resolution of
that permanent's own leaves-trigger.

The gap record was right that `snapshot` cannot do it — it writes into
`EffectContext.bindings`, which lives for exactly one resolution, and the
enters-trigger that exiles and the leaves-trigger that returns are two abilities
with two contexts. It was wrong about how much machinery the answer needs.

### What shipped

`GameObject.exiled_by`, one integer, plus `until_leaves` on the `exile` op to
write it and an `exiled_with` selector key to read it back.

**The link lives on the exiled card, not on the exiler**, and that is the whole
design. The exiler is the thing that goes away: the Ring is in a graveyard by
the time the return happens. Its victim is sitting in exile, untouched. And an
oid survives every zone change in this engine, so a leaves-trigger's
`source_oid` still names the departed permanent — which means no snapshot is
needed at all, just a comparison. The gap record had assumed the trigger would
have to carry the link in its bindings the way `was_attacking` does; it does
not.

Written *after* the move, because `move_object` runs `reset_permanent_state` on
the way and would wipe it, and cleared by that same reset when the card comes
back — correct, since the link is spent once followed.

### What the test pins

That it returns **only its own victim**. A plain `{"zone": "exile"}` filter
matches every card in exile from every source, so a return over it would hand
back cards this permanent never touched — a different card, and a strictly
better one. The test exiles a second creature by other means and checks it stays
put.

Also that the card comes back under its **owner's** control rather than the
Ring controller's, which would be a small theft nobody would notice.

### A detail worth knowing

`controller: "any"` is required on the return selector. An exiled card keeps its
last controller — for O-Ring's victim, an opponent — and the selector language
defaults `controller` to `"you"`, so without it the filter silently matches
nothing and the card never returns. That cost a debugging cycle.

### Also repaired

The incumbent restricted its target to `controller: "opponent"`, where the
printing says "another target nonland permanent" — any controller. Now
`controller: "any"` with `exclude_self`, matching the printed line.

Angel of Sanctions is now blocked on **embalm alone**; its gap record has been
narrowed rather than retired.

## Spell cost reduction — discounting somebody else's card

### Overview

"Creature spells with flying you cast cost {1} less to cast." Warden of Evos
Isle and Watcher of the Spheres print the same line, and the near miss made it
worse rather than better: the card-level `cost_reduction` field points the other
way. It discounts the card that *carries* it, choosing by counting permanents —
Ghalta's "this spell costs {X} less". Writing it on Warden would have made
Warden cheaper, a different card that would have looked implemented.

### What shipped

A `spell_cost_reduction` static with its own filter, `affects_spells`, matched
against the printed face of the card being cast plus who is casting it —
`characteristics._matches_printed`, the same helper the counting filters use.

`affects` could not be reused: it names permanents and carries board state
(`tapped`, `attacking`, `attached`), and a spell being priced is still in hand
and has none of it. The loader refuses those keys in `affects_spells` and
refuses `affects` on this effect entirely.

**Where it is applied is the whole design.** It goes inside
`costs.cost_reduction` — the one function both `legality` (deciding what is
castable, and what the client shows) and `game.cast` (actually charging) already
call. So a spell offered at the reduced price is paid at the reduced price by
construction, which is the same argument the variable-mana run made about
`mana_produced` two commits earlier. A `spell_cast` trigger could not stand in:
it fires after the spell is paid for, so at best it refunds mana into the pool,
which is not the same as being able to afford the spell.

### The bug, and why the guard is shaped as it is

The first implementation compiled cleanly and discounted **every spell in the
game**. `_compile_static` assembles the static into a plain dict field by field,
and `affects_spells` was not among the fields it copied — so the filter arrived
empty, and an empty filter matches everything.

Two changes came out of that. The loader now requires `affects_spells` and an
`amount`, and `spell_cost_reduction` skips a static whose filter is missing
rather than defaulting to `{}`: a compile bug should discount nothing, not the
whole game. `test_it_does_not_discount_everything` is that failure, kept.

### Also repaired

Warden's mana cost was `{3}{U}` where the printing says `{2}{U}`, and Watcher
was missing the Wizard subtype and its third printed line ("Whenever another
creature you control with flying enters, this creature gets +1/+1 until end of
turn"), which needed nothing new.

## The cycle trigger — an event, and two orderings

### Overview

"When you cycle this card, you may search your library for a basic land card …
**(Do this before you draw.)**" Krosan Tusker is the witness, and plain cycling
had already shipped, so the cost half was expressible and only the event was
not.

The first Tier D change in this sequence — a new `EventType` — and so the only
one that touched `frontend/`.

### Why it needed its own event

Both near misses already exist and both are wrong rather than merely absent.
`draw` fires on every draw, including the draw step and every other draw spell,
so a Tusker sitting in the graveyard would fetch a land each time its controller
drew anything — and it fires *after* the draw, which the parenthetical
explicitly forbids. `discard` fires on hand-size discards and on every discard
cost, so a Tusker pitched to a Wheel would fetch.

So `EventType.CYCLED`, and cycling is **declared** rather than inferred:
`is_cycling` on the ability, refused by the loader unless the cost actually
discards the card. "Discard this card:" is a shape other cards print without
being cycling, and inferring from `discard_self` would make those a different
card.

### Two orderings, both load-bearing

The event fires **after** the cycling ability is pushed onto the stack, so the
trigger drains on top of it and resolves first. That is the whole of "(Do this
before you draw.)", and it falls out of the stack's ordinary
last-on-first-off behaviour rather than any special case. Firing it a few lines
earlier — before the push — reverses it silently, and the card still looks like
it works.

And the card is **already in the graveyard** when it fires, because paying the
cost discarded it. The trigger declares `active_zones: ["graveyard"]` and is
collected by the walk `_candidate_abilities` already does over that zone, so the
zone machinery needed nothing.

### The bug in the middle of it

The first implementation used `state.emit`, which only writes the log — the
`cycled` event appeared in the event stream, the ticker would have narrated it,
and no trigger ever fired. `triggers.fire` is the one that queues abilities. An
event nothing listens for is exactly the silent no-op this run exists to remove,
and it took the ordering test to notice.

### Frontend

`labels.ts::describeEvent` and `events.ts::beatsFor`, both of which have `default`
fallthroughs — an unnarrated event is dropped with nothing reporting it, which
is why the skill calls this the only tier that genuinely forces UI work.

## "Attacks each combat if able" — the continuous half of a requirement

### Overview

The `attack-requirement` entry opened with two cards and closed with one. Bident
of Thassa was already expressible the day the report was regenerated — the
`must_attack` op names it as its own `this_turn` witness — and was repaired at
the start of this sequence. Marauding Maulhorn is what actually needed building.

`must_attack` writes a one-shot flag that `discharge_attack_requirements` spends
once attackers are locked in. Right for "attacks this turn if able", wrong for a
printed line: that is true again next turn, true for a creature that entered
after any op would have resolved, and false the moment its source leaves. So the
continuous form is a static, read live off the battlefield.

### What shipped

`attacks_if_able` in `STATIC_EFFECTS`, read by `characteristics.attack_compelled`
— written as the exact mirror of `attack_forbidden` (Stormtide Leviathan's
`cant_attack`), down to the `affects` filter routinely naming creatures the
source's controller does not control.

Both forms meet at `combat.attack_required`, so there is still exactly one place
deciding whether "Done attacking" is offered. Tier B in shape but small in
practice, because the enforcement half — the part the gap record called an
engine need — shipped with `must_attack` and needed nothing.

One effect covers every printed variant, since they differ only in `affects`:
`self_only` for "This creature…", `controller: opponent` for the goad-shaped
"Creatures your opponents control…", `attached` for "Enchanted creature…".

### `name` in a condition, not in a filter

The "unless" clause needed a static condition able to ask whether a card with a
particular name is on the battlefield. `name` was already in `SELECTOR_KEYS` and
absent from the static ones; it is now allowed in the **counting** filters
(`exists`, `count`, and their off-battlefield form) and still refused in
`affects`. "Unless you control a creature named Advocate of the Beast" is a
question about the board; "each creature named X gets +1/+1" is not a card, and
allowing it in `affects` would only invite one. A name is as printed as a type
and nothing in the pipeline can change one, so it is safe where a type is.

### What the test corrected

Two claims written first and found wrong by the engine, both kept as tests
because the real behaviour is the more interesting one: a goaded creature owes
nothing on its goader's turn (it cannot attack then, so "if able" excuses it —
otherwise the goading player could never finish a declaration), and a lone
summoning-sick compelled creature does not deadlock the step because the engine
skips declare-attackers entirely when nothing is able.

## Variable mana abilities — nine cards that were tapping for one

### Overview

"{T}: Add {G} for each +1/+1 counter on this creature." Gyre Sage was the card
in the gap report; the run's real weight was elsewhere. Gaea's Cradle, Cabal
Coffers, Serra's Sanctum, Priest of Titania, Circle of Dreams Druid, Overgrown
Battlement, Magus of the Coffers and Cloudpost were all already **shipped**,
each tapping for exactly one mana, each recorded in the queue as
`template:proxy:complete` — marked correct while being wrong.

Everything else about a mana ability is a constant folded at load time, for a
good reason: rule 605 says a mana ability resolves immediately without the
stack, so it may never stop to ask. `loader._sum_mana` folds the symbols into a
fixed 6-tuple and `costs.activate_mana_ability` pays that tuple out without ever
running the ability's effects. A count of counters cannot be folded — but it
also asks nothing. It only looks.

### What shipped

`Ability.mana_amount`: an optional value expression on the single `add_mana`
inside a mana ability, evaluated at activation. `costs.mana_amount` reads it
through the ordinary value language, which already computes exactly this.

The multiplier is threaded through `costs.mana_produced` — the one function both
the solver's `_sources_of` and `activate_mana_ability` already call, and whose
docstring already said the two must not be able to disagree. That is the whole
design: the price a spell is **offered** at and the mana a tap actually **makes**
come from the same arithmetic, so they cannot drift. A spell offered on mana
that does not materialise strands the payment mid-cast, and nothing on screen
would say why. `activate_mana_ability` was also reordered to measure *before*
tapping, because the solver enumerates sources while they are still untapped.

Three load-time constraints, each with a failure behind it: one `add_mana` per
amount (nothing else is single enough to scale); no `x` / `binding` /
`loop_value` (a mana ability is activated during payment, so each reads 0 and
makes a card that silently taps for nothing); and the amount is read before the
tap.

### The nine, and the one that got away

`proxy._mana_effects` read `Add {C}{C}` correctly and fell through to
one-of-each-symbol for anything else — **with no note**, which is why nine cards
shipped as `complete`. It now parses "for each &lt;noun&gt; you control / on the
battlefield", optionally with a trailing keyword ("creature you control with
defender"), into a counting selector. Eight of the nine were re-authored through
the ordinary template tier and are now correct.

Kydele, Chosen of Kruphix is the ninth and does not fall out of this. Its
multiplier is "for each card you've drawn this turn" — not a board count at all,
but a per-turn tally of an *event*, which nothing in the engine keeps. Per rule
3 it now **refuses** rather than shipping a strictly worse card, so it has left
the pool and gained a gap record under a new `cards-drawn-this-turn` capability.
That is a card fewer in the registry and a card more in the report, and it is
the honest direction: it was previously in the pool tapping for a sixth of what
it prints, with nothing recorded to say so.

An unreadable "for each" clause now emits a note rather than falling through
silently, so the next one cannot repeat this.

## Per-opponent life — the leaf that makes a pod question answerable

### Overview

Two cards, one printed clause: "an opponent has 10 or less life". Vampire
Lacerator asks it from an `if` inside a triggered ability, Guul Draz Vampire
from a static's "as long as" clause — so the leaf had to land in both condition
languages, which are deliberately separate.

The engine could already read a life total, and that was the trap rather than
the solution. `life_of` **sums** over its player spec, and `"opponent"` and
`"each_opponent"` are the same set, so the obvious spelling asks whether the
opponents' *combined* life is 10 or less. In a duel that is the printed card
exactly. At a Commander table it is a different card and the wrong way round:
three opponents at 4 life sum to 12, so a summing Lacerator drains its
controller against a table that is nearly dead, and a summing Guul Draz stays a
1/1 while every opponent is in burn range. This repo is Commander-first, so that
is a divergence, not a rounding error.

### What shipped

`min_life_of` and `max_life_of` — the existential and the universal — in
`VALUE_KEYS`, in `characteristics._static_value`, and mirrored in
`loader._validate_static_value` with their own player-spec whitelist.

Tier A, and the narrow form on purpose. The gap record also proposed the general
shape, `{"any_player": {"players": …, "condition": …}}`, and named the min/max
leaves as its special case. The narrow one expresses both printed cards exactly
— "an opponent has" is `min <= 10`, "each opponent has" is `max <= 10` — and a
quantifier over players inside the *static* condition language would be new
machinery in the one place the repo guards hardest. `min`/`max` already existed
as value expressions and could not stand in: they take a literal list written
into the card, and no player spec enumerates opponents one at a time.

A life total is safe inside a static for the same reason a zone count is: it is
a pipeline **input**. Nothing in the fixed-order characteristics pipeline can
change one, so no static can come to depend on another's output through it.

### The empty set has a right answer and a wrong one

With no opponents left, "an opponent has 10 or less life" must be **false**. A
minimum over nothing that returned 0 would make it vacuously true and switch
Lacerator's drawback off at the instant the last opponent died — so
`NO_PLAYERS_LIFE` is a life total nothing reaches. `max_life_of` takes the
opposite bias deliberately: "each opponent has 10 or less" over nobody *is*
vacuously true, and 0 is the correct reading there. Statics are evaluated during
state-based-action passes, so this is observable rather than theoretical.

### A latent bug fixed on the way

`characteristics._static_players` spelled `"opponent"` but not
`"each_opponent"`, so the latter fell through to *every* player including the
static's own controller. Nothing reached it today — the loader restricts
`controller` on zone filters to `you`/`opponent`/`any` — but the new leaf takes
a full player spec, and the effect-side `select_players` has always treated the
two as synonyms. Now both do.

### Also repaired

Vampire Lacerator's printed subtypes are "Vampire Warrior"; the pool had it as a
Vampire only. Checked against `data/catalog/cards.sqlite`, like every printed
characteristic touched in this sequence.

## "Unless that player pays" — the best-ranked card in the report, for one guard

### Overview

Rhystic Study is EDHREC rank 44, the best-ranked card the gap report has ever
carried, and it was blocked by a single load-time check.

Its gap record is the oldest in the repo and asked for three things: a decision
routed to another player, a cost payable mid-resolution by someone who does not
control the ability, and a `spell_cast` trigger that can name the caster. All
three had shipped in the meantime, and the record says "reference" throughout —
it was written against a design document rather than the engine. `op_may`
already resolves an arbitrary `player` through `select_players` (which has taken
`{"controller_of": ...}` all along), already pays a `Cost` out of the pool
mid-resolution on behalf of whoever is asked, and already branches to `else` on
a refusal.

This is the same lesson as the Bident repair one commit earlier, and the reason
the re-triage step exists: a gap record is a snapshot, nothing retires one
automatically, and the report drifts in exactly one direction.

### What shipped

One guard, narrowed. `loader._validate_effect` refused a `may` carrying `pay`
without `effects`, on the grounds that "paying for nothing is not a card". That
is right when there is no `else` and exactly backwards when there is: what
Rhystic Study's opponent buys for their {1} is the *absence* of the else branch.
They get nothing, and that is the mechanic. The guard now asks for `effects`
**or** `else`, so a payment that buys nothing at all is still refused — with a
test pinning each of the three shapes.

Tier: below A. No new op, no new decision kind, no engine change. The skill
warns that the common way to over-build is reaching for a new `DecisionKind`
when an existing `ask_*` composes, and this is that warning's sharpest case so
far — the card reads like it needs a bespoke subsystem and needed one word of
validation.

### What the test pins

That the *opponent* is asked to pay and the *controller* is asked to draw. A
Rhystic Study whose controller decided whether the opponent paid would be
unbeatable and would look entirely normal on screen — the same property
`test_two_piles.py` pins for Fact or Fiction, and free for the same reason.

Also that an opponent who cannot afford the {1} is not prompted at all (rule
118.4) and the draw simply happens; that "you may draw" stays optional after
they decline; and that your own spells do not trigger it.

The turn cap in that test is load-bearing rather than decoration. With nothing
left to do the engine runs on into the next turn, and player 0's draw *step*
would be counted as the trigger's card — every branch would read one card too
high, and the "they paid, so no draw" case would pass while being wrong.

### A gate regression caught on the way

`--collect` re-verifies every answer on disk and rewrites `expectations.json`
from them, which silently weakened two unrelated cards: `coiling_oracle` and
`search_for_tomorrow` had `battlefield_count` and `library_size` assertions
committed that their answer files did not carry, so collecting dropped them back
to a bare `zone` check.

Fixed at the source — the stronger expectations now live in the answer files,
where the next `--collect` will preserve rather than clobber them, and both
cards re-verified against them. Worth knowing before the next run: strengthening
`data/cards/auto/expectations.json` by hand does not survive.

## Investigate — a keyword action that was one missing token

### Overview

The cheapest capability in the report, and the only one so far whose gap record
asked for no vocabulary whatsoever. Investigate's reminder text is its whole
specification — *(Create a Clue token. It's an artifact with "{2}, Sacrifice
this token: Draw a card.")* — and every piece of that was already expressible:
`create_token` names any token in the pool, `Cost` carries mana and a
`self_only` sacrifice together (Mind Stone pays exactly that shape), and `draw`
is an op. The only thing missing was a Clue for `create_token` to point at.

That is a real constraint rather than an oversight. `validate_token_references`
refuses to load a card naming a token nobody defined, so Bygone Bishop could not
be written half; and `data/cards/` is off-limits to authoring workers, so the
token had to come from an `/extend-dsl` run even though no engine change was
behind it. Adding it unblocks every investigate card at once.

### What shipped

`clue_token` in `data/cards/tokens.cards.json` — an artifact with the Clue
subtype and one activated ability costing `{2}` plus a `self_only` sacrifice.
Bygone Bishop repaired in `data/cards/isperia.cards.json`: it had been a vanilla
2/3 flier, and its mana cost had been `{2}{W}{W}` where the printing (and
`data/catalog/cards.sqlite`) say `{2}{W}`.

### The bug the test found

The gap record predicted "a data addition with no engine change behind it", and
that was wrong — but only findably wrong. `stack.ability_of` resolved an
ability by looking it up *through the source object*, returning `None` when the
object was gone. A permanent that sacrifices itself as a cost still has an
object, in the graveyard, so every self-sacrificing card in the pool worked. A
**token** does not: the token state-based action pops it out of `state.objects`
entirely. So the Clue's ability went on the stack, found no source, and resolved
as a silent no-op — the token vanished and no card was drawn.

`_resolve_ability` already carried the comment *"the ability resolves even if
its source has left the battlefield"*; `ability_of` was the one place that
contradicted it. It now falls back to the stack item's `def_id`.

Nothing in the pool had caught this because the only other artifact token,
`treasure_token`, is itself an approximation: its printed cost is "{T},
Sacrifice this artifact" and it is implemented with `{"tap": true}` alone, so it
never sacrifices and never took the broken path. That approximation is still
there and is a separate repair.

This is the argument for §3 of the skill in one case: the behaviour gate could
not have found it either, because nothing casts a spell after the card under
test in the verification sandbox, so Bygone Bishop's trigger never fires there.
`tests/unit/test_investigate.py` is the only coverage the Clue has, and the
claim that earned its keep was "it draws a card", not "the token appears".

## Evasion — the five questions `can_block` could not ask

### Overview

Five keywords in one run, which reads like a violation of "one capability per
run" and is the opposite of one. Fear, intimidate, horsemanship, shadow and
nonbasic landwalk are not five mechanics; they are five instances of a mechanism
`can_block` already had, and skulk had already paid for. That is the landwalk
precedent exactly — five keywords, one rule, one test file — and the argument is
in [keywords.md](keywords.md), which is what made this sizeable in the first
place.

The demand-driven report could not have surfaced this. Only intimidate had a gap
record (Guul Draz Vampire's, filed against `blocking-restriction`, which the
skulk run had already narrowed to this one card). The census is what showed that
the *other four* were sitting behind the same rule with 108 pending cards
between them, and that once they shipped the evasion family would be closed —
everything left in combat (flanking, rampage, bushido, frenzy, provoke) wants a
trigger event rather than a block rule, which is a different tier of work.

### What shipped

Five `Keyword` members and five checks in `combat.can_block`, plus one helper.
Each is two or three lines:

```python
if Keyword.HORSEMANSHIP.value in ac.keywords and (
    Keyword.HORSEMANSHIP.value not in bc.keywords
):
    return False

if (Keyword.SHADOW.value in ac.keywords) != (Keyword.SHADOW.value in bc.keywords):
    return False

if "Artifact" not in bc.types:
    if Keyword.FEAR.value in ac.keywords and "B" not in bc.colors:
        return False
    if Keyword.INTIMIDATE.value in ac.keywords and not (ac.colors & bc.colors):
        return False
```

Keywords rather than `block_restriction` statics, and this run added a **second**
reason to the one skulk established. The derived-versus-printed argument covers
fear and intimidate — a land animated into a black creature may block a fear
creature, and a static filter reads printed characteristics by design. But
horsemanship's quality is printed, so that argument alone would not have settled
it. The one that does is structural: a `blockers` filter is a **prohibition**
("can't be blocked by Humans") and all four of these are **exemptions** ("can't
be blocked *except* by …"). The filter language is a positive conjunction and
its negation is not another key. That corollary is now written down in
`keywords.md` beside the other two.

Three of the five are their own shape and each has a boundary that a plausible
implementation gets wrong:

- **intimidate** compares the two creatures, on colors. A **colorless** creature
  with intimidate shares a color with nothing, so only an artifact creature may
  block it. Read as "is not a different color" it inverts into nearly the
  opposite card.
- **shadow** is the only evasion that is not an attacker-side rule at all.
  702.28b is "can block **or** be blocked by only creatures with shadow", so the
  check asks whether the two creatures *agree*. Hung on the attacker it would be
  half a mechanic, and the missing half is the one that stops a Dauthi
  Voidwalker from blocking.
- **nonbasic landwalk** is 702.14 with the test inverted: a supertype the
  defending player's land must *lack*. So it could not be a sixth
  `LANDWALK_SUBTYPE` row, and "the defender controls eight Forests" is the case
  that separates it from a naive "controls a land".

One importer change, because Portal Three Kingdoms prints horsemanship as
"Haste; horsemanship" and `proxy.lift_keywords` split on commas only. It now
splits on semicolons too, which widens nothing: the check is still all-or-nothing
over every part, so "Trample; rampage 2" and "First strike; banding" still fail
on their second part exactly as they did when the line was unsplittable.

Nothing else. `KNOWN_KEYWORDS` derives from the enum, so the loader, the
residual gate and the importer picked all five up unprompted; `grant_keyword`
carries them because the checks read the characteristic layer. Server and
frontend: no change.

### Harvested

**28 cards**, across all five keywords — thirteen horsemanship, six fear, five
intimidate, three shadow, and Dryad Sophisticate. Three of those (Lu Bu, Shu
General, Zhang Fei) exist only because of the semicolon fix.

The other 94 pending cards printing one of these keywords have no template,
because they print something else as well; they stay in the agent tier for the
next `/author-cards`, which is the ordinary outcome.

`blocking-restriction` is retired from `unsupported-cards.md` entirely. Guul
Draz Vampire's record survives with **one** need instead of three — the `+2/+1`
and the `intimidate` halves are both expressible now, and what is left is a
condition leaf that can ask about *one* opponent's life total rather than the
sum. That is `player-quantifier`, which two cards now share.

### Guarded by

`tests/unit/test_evasion_keywords.py`. One class per keyword, plus a class for
the claim they share. Every class carries its pair — a creature *without* the
keyword being blocked normally — because a rule that refused every block would
otherwise look identical from the refusals alone. The boundaries are tested in
preference to the happy paths: the colorless intimidator against three different
blockers, shadow refused in **both** directions, and nonbasic landwalk against a
board of basics and against a dual on the *attacker's* side. The derived half is
pinned with `animate`, which is the only way to change a creature's colour — a
Forest cannot block a fear creature until it is animated into a black one, and
then it can.

## Static conditions — "as long as", widened past its own counters

### Overview

`static-condition` was the top entry in `unsupported-cards.md` with three cards,
and reading all three is what decided the shape. They ask for three different
leaves — a life total (Guul Draz Vampire), a count of cards in a zone (Nimble
Mongoose), and a player-level designation (Skymarcher Aspirant) — and *none* of
them asks for a bespoke flag. Three different questions with one grammar between
them is a condition language, not a `threshold: true`.

Two of the three are blocked elsewhere as well, so only one card could land here:
Guul Draz Vampire also needs `intimidate` and a per-opponent life quantifier,
and Skymarcher Aspirant needs the city's blessing to exist before anything can
read it. That was clear before any code was written and is the honest size of
the job — the value is the grammar, and the two remaining cards each now wait on
exactly one leaf instead of a leaf *and* a language.

The constraint this had to survive is the one that makes the whole "layers-lite"
pipeline work: **a static may not read another static's output.** A condition
that reached the effect language's `evaluate` would go through the selector
engine, which calls `chars`, which builds the static list, which evaluates
conditions — an unbounded recursion, not a subtle ordering bug.

### What shipped

The resolution of that is where the condition is *evaluated*, and it needed no
new machinery at all. `_static_active` runs inside `_battlefield_statics`,
before layer -1, so everything reachable from it is a pipeline **input**:
counters on the source, printed characteristics of the board, the contents of a
zone, whose turn it is. No layer can change whether another static is switched
on, so the gate is computed once and the fixed order stays acyclic. The language
is therefore a deliberate *mirror* of `effects/conditions.py` rather than that
module — `all` / `any` / `not` / `exists` / `is_your_turn` / `cmp`, over the
static value language that already existed (`{"const": n}`, `{"count": filter}`)
and the `counters` form kept verbatim.

One new key: a filter in a **counting** position may name a `zone`.

```jsonc
{ "cmp": ">=",
  "left":  { "count": { "zone": "graveyard", "controller": "you" } },
  "right": { "const": 7 } }
```

`affects` and `blockers` deliberately did *not* get it, and that asymmetry is
the design. They pick out the permanents a static applies to, and there are no
permanents outside the battlefield — a zone there would load clean and match
nothing, which is the one failure this format exists to refuse. For the same
reason the loader rejects `tapped`, `attacking`, `attached`, `self_only` and the
rest once a filter names a non-battlefield zone: a card in a graveyard has a
printed face and an owner and nothing else. `_matches` was split so the two
counting paths share one definition of "the printed face matches" rather than
drifting.

`life_of` was deliberately left out. It sums over its player spec, so
`{"life_of": "opponent"} <= 10` reads "my opponents' *combined* life", which is
the printed card in a duel and a different card in a pod — precisely the
divergence the separate `player-quantifier` gap was filed over. Adding it here
would have let Guul Draz Vampire load while being wrong at four seats.

Server and frontend: no change. Statics are card data, and the condition never
leaves the engine.

### Harvested

**Nimble Mongoose**, which was already in the hand-written pool as a 1/1 with no
threshold and — worse — `hexproof` where it prints Shroud, a strictly better
card than the one printed. Both printed lines now work, it clears all six
authoring gates, and it is off `tests/cards/precon_deficits.json`, which drops
from 23 cards to 22.

No template was added. Zero cards in the authoring queue print the threshold
sentence, so a template would have had nothing to read; the remaining
threshold-shaped work is agent-tier.

Gap records: `nimble_mongoose.json` retired. The `static_condition` need was
struck from the other two and folded into the leaf each still waits on — a
per-opponent life value for Guul Draz Vampire, the blessing itself for
Skymarcher Aspirant — so the build order re-ranks honestly instead of sending
the next run back here. `attack-requirement` is now the top entry.

### Guarded by

`tests/unit/test_static_condition.py`. The claim that needed the most care is
not that the bonus turns on but that it turns *off*: a trigger-plus-pump
substitute passes every "it is a 3/3 at seven cards" test and fails the moment
the graveyard shrinks, so the boundary is tested from both sides at six, seven
and back down. `TestItStaysAcyclic` pins the invariant directly by standing an
anthem next to a conditional static and asserting the count still reads printed
faces. `TestTheLoaderRefusesWhatCannotWork` is the other half — every rejection
above is asserted, including that `affects` still cannot name a zone and that
Arixmethes' original `counters` spelling is untouched.

## Skulk — the first evasion that compares the two creatures

### Overview

`blocking-restriction` was the top entry in `unsupported-cards.md` with three
cards, and reading all three rather than the first one is what sized the job.
Stromkirk Noble's half — "can't be blocked by Humans", a fixed quality of the
would-be blocker — had already shipped as the `block_restriction` static; its
gap record was simply stale. Guul Draz Vampire wants `intimidate` and is blocked
twice more besides, by `static-condition` and `player-quantifier`, so nothing
here can reach it. What was actually left was Vampire Cutthroat's half, and its
own gap record named the thing that makes it different: the filter is not a
quality at all but a **relative comparison between two objects**.

Every evasion the engine had asks a fixed question of one side. Flying and
menace read a quality of one creature. Landwalk reads the defending player's
board. A `block_restriction` reads a printed characteristic of the blocker.
Skulk reads *both* creatures and compares them.

### What shipped

One enum member and one check. `Keyword.SKULK`, and three lines in
`combat.can_block`:

```python
if Keyword.SKULK.value in ac.keywords and bc.power > ac.power:
    return False
```

A keyword rather than a fourth `block_restriction` form, on the landwalk
precedent — skulk takes no parameter, so there is nothing for a static to carry.
And it could not have been a `blockers` filter even with a `power` key added:
`blockers` is a static filter, static filters are matched against **printed**
characteristics, and that restriction is the entire reason the fixed-order
characteristics pipeline is acyclic. Skulk must read *derived* power on both
sides. Putting the comparison in `can_block` — which already holds `chars` for
both creatures, and which landwalk reads `chars` from for the same reason —
costs the invariant nothing.

Nothing else. `KNOWN_KEYWORDS` derives from the enum, so the loader, the
residual gate and the importer's `_keywords_in` picked it up unprompted;
`grant_keyword` carries "creatures you control have skulk" for free, because the
check reads the characteristic layer rather than the printed card. Server and
frontend: no change, keywords being rendered generically.

### Harvested

Vampire Cutthroat now translates with **both** printed lines consumed and no
residual — verified against the template tier and the gates. It did not land in
the pool on this run because it is a `fidelity` entry: a card already present as
a vanilla in `data/cards/edgar.cards.json`, which the template tier deliberately
refuses to touch (translating it would mint a second id and leave the incomplete
incumbent as the one dealt into games). Repairing an incumbent is
`--tier agent` plus `--collect --supersede`, i.e. the next `/author-cards`.
Stromkirk Noble is in the same position and has been expressible since
`block_restriction` shipped; it has no *template*, so it too is agent-tier work.

Both gap records were retired. `blocking-restriction` now blocks one card, Guul
Draz Vampire, on `intimidate` — which is a colour relation rather than a
comparison and is a separate build.

### Guarded by

`tests/unit/test_skulk.py`. Two claims, two classes. The refusal is tested
against its boundary rather than only its happy path: an equal-power creature
must block, because an engine written with `>=` passes every test that only
tries a bigger blocker. The derived-power half is tested from three directions —
an anthem on the blocker, a +1/+1 counter on the blocker (a different layer of
`chars`), and an anthem on the *attacker*, which gives back a block its own size
had forbidden. The granted-skulk test is what pins the design choice: it works
only because skulk is a real keyword.

## Shroud — the keyword whose whole content is who it stops

### Overview

Two gap records asked for it independently, Nimble Mongoose and Simic Sky
Swallower, and both spent most of their length arguing that the two obvious
substitutions are wrong in opposite directions. They were right, which is why
this is worth a page for a five-line diff.

`hexproof` is the near miss and stops opponents only. Written that way, Simic
Sky Swallower becomes a **strictly better** card than the one printed: a 6/6
flying trampler its own controller can still pump, blink or equip by targeting.
That is the failure this pipeline exists to prevent — nothing on screen would
look wrong.

`protection` is wrong the other way. Four rules read it — damage, enchant/equip,
block, target — so a shroud faked as protection would also make the creature
undamageable and unblockable, and the loader rejects a `protection` static that
names no quality, so "from everything" cannot be spelled at all.

### What shipped

One enum member and one reordered check. `Keyword.SHROUD`, and in
`targeting.can_be_targeted` the shroud test moved *above* the
`obj.controller == controller` early return that hexproof sits behind — that
ordering is the entire semantic difference between the two keywords.

Nothing else. `KNOWN_KEYWORDS` derives from the enum, so the loader, the
residual gate and `proxy.lift_keywords` all picked it up; `grant_keyword` as op
and as static carries the whole "equipped creature has shroud" family for free,
because the check reads the characteristic layer rather than the printed card.
Server and frontend: no change, keywords being rendered generically.

### Guarded by

`tests/unit/test_shroud.py`, in pairs. Every claim about shroud is asserted
beside the same claim about hexproof on the same board, so that a regression
collapsing the two keywords into one fails rather than passes quietly. The
"only the target rule" half is pinned by asserting `protected_from` stays False
for a shrouded creature, which covers damage, blocking and enchant/equip in one
assertion, since all three ask that question.

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


## `roll_dice` — one roll, read two ways

### Overview

Rule 705.1. Luck Bobblehead: "{1}, {T}: Roll X six-sided dice, where X is the
number of Bobbleheads you control. Create a tapped Treasure token **for each
even result**. If you rolled **6 exactly seven times**, you win the game."

Nothing in `ops` produced a *number* at all. `clash` is the only other
randomness-consuming op and yields a win/lose boolean; the `random` selector key
picks objects and evaluates to a set; `for_each` and `repeat` iterate over things
that already exist. So two pieces were missing: an op that rolls, and a value
leaf that reads the roll back.

### Tier: A, plus one value leaf and one event

A new op composing existing primitives — `state.rng`, `evaluate_value` and the
`as`-binding convention `create_token`, `sacrifice`, `exile` and `reveal` already
share. No new decision kind (the op asks nobody anything and is not even a
generator), and no server or API change. The one Tier D piece is
`EventType.DICE_ROLLED`, with its two frontend halves.

### The design question: why the results are a binding

The card is two sentences about **one** roll. The Treasures count the even
results; the win condition counts the sixes; and the sixes are a *subset* of the
evens the card just paid out for. Two `roll_dice` ops — one per sentence — would
decorrelate the halves, giving a card that is right on average and wrong every
game: a hand that rolled seven 6s would create its Treasures off some other roll
entirely.

So the op records what it threw, and the reads are pure functions of that record:

```jsonc
{ "op": "roll_dice", "count": { "count": { …Bobbleheads… } }, "sides": 6, "as": "roll" },
{ "op": "create_token", "token": "treasure_token", "tapped": true,
  "amount": { "rolled": { "binding": "roll", "parity": "even" } } },
{ "op": "if",
  "condition": { "cmp": "=", "right": { "const": 7 },
                 "left": { "rolled": { "binding": "roll", "face": 6 } } },
  "then": [ { "op": "win_game", "player": "you" } ] }
```

`{"rolled": …}` bare is how many dice were thrown; `parity` and `face` narrow it
to how many results satisfy that predicate. At most one predicate per read, which
is a load error rather than a silent drop.

### A mapping, not a list of faces

The binding is `{"results": [...], "sides": N}`. Every other recording op writes
a list of **oids**, and `selectors._bound_oids` reads any bound list as exactly
that — so a bare `[6, 3, 2]` would have made `{"count": {"binding": "roll"}}`
answer 3 by luck and `{"objects": {"binding": "roll"}}` name objects 6, 3 and 2:
three real permanents with nothing to do with the roll, destroyed by the next op
along. A mapping with no `oid` key reads back through the same path as *no
objects at all*, which is the truth — rolling a die creates nothing to point at.

### `count` is a value, `sides` is a literal

X is a board count that moves between activations, so it is an ordinary value
expression. The die is printed on the card and never varies; written as a value
expression it would be accepted, stringified and rolled as a d0, so the loader
requires a plain integer of at least 2.

### Zero dice

"X is the number of Bobbleheads you control" is 0 on an empty board. The op still
writes the (empty) binding — without that, the reads after it would answer off
whatever the *previous* resolution left behind. No event is emitted for a roll of
nothing, because nothing was rolled.

### Determinism

Every face comes from `state.rng.randint(1, sides)`, the engine's one seeded
source. `tests/unit/test_determinism_hygiene.py` scans the source for direct
`random` use and would fail otherwise; the test file asserts that the faces match
a reference `Rng` advanced the same number of times, so the roll is pinned to the
stream rather than merely to "some RNG".

### What the loader refuses

| | |
|---|---|
| `roll_dice` with no `as` | the faces land in a binding nothing can name, and every `{"rolled": …}` on the card reads 0 |
| `sides` that is not an integer ≥ 2 | a d0, silently |
| a `roll_dice` no `{"rolled": …}` reads | a roll is never the effect |
| a `{"rolled": …}` with no roll behind it | reads 0 for ever |
| `{"rolled": …}` with no `binding` | the same silent zero |
| an unknown key, e.g. `{"even": true}` | falls through to the count of *dice*, so a Bobblehead would hand out a Treasure per die |
| a `parity` that is not `even`/`odd` | same |
| `face` and `parity` together | `face` wins in the evaluator and the other half is dropped |

Both card-level checks are the shape `clash` already had — two halves, each of
which loads cleanly and does nothing on its own.

### What it does not do

"Whenever you roll one or more dice" triggers (Barbarian Class, the Fallout and
AFR roll-a-die block): the `dice_rolled` event exists and carries `results` and
`sides`, and nothing subscribes to it — a name in `TRIGGER_EVENTS` away, plus a
decision about which bindings a trigger's effects can read. And the AFR d20
outcome tables ("1—9 … 10—19 … 20"), which are a banding construct on top of a
roll and their own capability.

### Test

`tests/unit/test_dice_rolling.py` — 39 tests. The claim classes are
`TestOneRollReadTwoWays` (the evens and the sixes come off the same faces; a read
draws no randomness; every face is counted exactly once),
`TestTheBindingIsFacesNotObjects` (the trap above, asserted from both directions),
`TestZeroDice`, `TestRerolling`, `TestDeterminism`, `TestTheEvent`,
`TestThroughARealCard` (`t_bobblehead`, the ability activated with the RNG pinned,
so the Treasures are checked against the faces that actually came up) and
`TestTheLoaderGuards`.

See `docs/card-dsl.md` ("Rolling dice") and `docs/rules-coverage.md`.

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
| Restricted mana naming the *chosen* type, and reaching ability costs | Secluded Courtyard |
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

  Extended twice since, both for Secluded Courtyard's one printed line. The
  restriction can name **the type its own permanent chose**, so it is resolved
  per permanent when the mana is offered instead of frozen at load — every fixed
  value would be a different card, and `"creature"` in particular would be
  strictly better than printed. And it can permit **activating an ability** and
  not only casting, which needed a second purpose (`costs.ability_purpose`)
  threaded through `legality._ability_aims` and `game._activate` the way
  `spell_purpose` was already threaded through the four cast sites. The purpose
  carries *which action* it is, and that is the load-bearing half: an activate
  permission matched on names alone would have silently rewritten Herd Heirloom
  and Master of Dark Rites, both of which print "only to **cast**".
- **Vorinclex's doubling** had to be computed in two places — `_sources_of` so
  legality counts it, `activate_mana_ability` so payment adds it — and a
  disagreement would strand a spell mid-cast. One `mana_produced` helper, called
  from both, plus a test that casts an 8-drop off four doubled Forests.

Two things were deliberately **not** done, and fail loudly instead of silently:
granting a *static* or *activated* ability (the loader rejects it rather than
compiling something legality would never offer), and phyrexian mana (a life
payment, not a colour choice). *Phyrexian mana has since shipped — see the
`{W/P}` section at the top of this file.*

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
client (the 403 recorded in the design record (`docs/design-record.md#board-themes`) was a *different* endpoint), and
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

- Mockups were made for a new main page, in [the menu round (`docs/design-record.md#menu`)](../the menu round (`docs/design-record.md#menu`)).
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

The board is built against the board-themes round's 05 'Planar Art' (`docs/design-record.md#board-themes`). The phase ribbon, the card
layout, the enlarged rail card and the unified action panel have landed. What is
still outstanding is enumerated, with severity and a fix direction, in
[design-record.md](design-record.md#open-fidelity-findings) — read its "Deliberate divergences"
section before changing anything to match a mockup.

The two worth doing first are both the same failure, and neither is cosmetic: the
"you can play this" rim and the combat arrows are thin strokes over a board of
full-bleed illustrations, so the two most urgent facts on screen are carried by
its two quietest marks.

Using: mockups\flow\02-face-up.html