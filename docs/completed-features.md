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
token will survive to that step the moment the step is reachable.
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
- **A filter naming a zone other than the battlefield.** `_reduction_matches`
  walks `state.battlefield` and nothing else.
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

**Visions of Glory** remains blocked, on `commander_mana_value` alone: a maximum
over the battlefield *and* the command zone, which no reduction shape and no value
expression can produce, and which cannot be evaluated at pricing time where no
`EffectContext` exists. Its gap record was trimmed rather than retired, so the
report now says what it is actually waiting for. Its rider's *slot* now exists;
only the number it takes does not.

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