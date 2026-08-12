# Writing a card

Cards are JSON. There is no Python in a card file, no `eval`, and no escape hatch —
which means a card either uses vocabulary the engine implements, or it fails to load.

```mermaid
flowchart LR
    json["cards/*.cards.json"] --> pydantic["schema.py<br/>shape validation"]
    pydantic --> vocab["loader.py<br/>vocabulary validation"]
    vocab --> constraints["loader.py<br/>constraint checks"]
    constraints --> carddef["CardDef<br/>immutable"]
    carddef --> ability["Ability"]
    ability --> ctx["EffectContext<br/>targets, bindings, x"]
    ctx --> ops["op registry<br/>48 ops"]
    ops --> events["GameEvent log"]

    style vocab fill:#2d5a8c,color:#fff
    style constraints fill:#2d5a8c,color:#fff
```

The two blue steps are the point: **an unknown op name, selector key, keyword, type or
trigger event is an error at load time**, so a typo fails the test suite rather than
silently producing a card that looks implemented and does nothing.

## The shape of a card

```jsonc
{
  "id": "snake_case_id",          // required, unique
  "name": "Display Name",         // required, unique among non-tokens
  "oracle_text": "...",           // the printed text, verbatim - see below
  "mana_cost": "{4}{G}{U}",       // omit for lands
  "supertypes": ["Legendary"],
  "types": ["Creature"],          // required
  "subtypes": ["Serpent"],
  "power": 5, "toughness": 5,     // required for creatures
  "keywords": ["trample"],       // the `Keyword` enum in engine/enums.py; see keywords.md
  "colors": ["G"],                // defaults to the colours in the cost
  "color_identity": ["G", "U"],   // defaults to derived; override for Command Tower etc.
  "targets": [ ... ],             // spell-level targets
  "spell_effects": [ ... ],       // what an instant/sorcery does on resolution
  "replacements": [ ... ],        // whitelist only
  "abilities": [ ... ],           // activated | triggered | static
  "is_token": false
}
```

### `oracle_text` is a contract, not a caption

It used to be described here as "display only", and it was written that way: a
human summary of what the card had been made to do. That quietly disabled the one
gate that asks whether a card implements everything it prints, because the gate
compares the implementation to `oracle_text` — and a summary written *after* the
shortcut agrees with the shortcut. Krosan Tusker recorded `"A large boar."`, and
against that text a vanilla 6/5 is a faithful implementation. It shipped for
months with no cycling and nothing to notice.

So `oracle_text` is now **the printed text, verbatim**, and each ability's `text`
is **the printed line that ability implements** — that is what the residual gate
matches on. Two checks keep it honest, both in
`tests/cards/test_hand_written_cards.py`: one compares every card's `oracle_text`
to `data/catalog/cards.sqlite`, and one runs all six authoring gates over it.

`python scripts/audit_cards.py` reports where the pool still falls short;
`--fix-oracle` and `--fix-text` record the printing and re-point ability text.

## Effect ops

50 of them. Each takes a spec dict; the common fields are `objects` (a selector),
`player` (a player spec) and `amount` (a value expression).

| Group | Ops |
|---|---|
| Cards | `draw` `discard` `mill` `search_library` `return_to_hand` `return_from_graveyard` `reveal` `scry` `surveil` `shuffle` `put_on_top` `two_piles` |
| Board | `destroy` `exile` `sacrifice` `put_onto_battlefield` `create_token` `add_counters` `remove_counters` `tap` `untap` `attach` `lock_abilities` `monstrosity` `freeze` `copy_permanent` `grant_ability` `skip_untap` `must_attack` `gain_control` |
| Modify | `pump` `grant_keyword` `set_pt` `animate` `add_subtype` |
| Life & damage | `gain_life` `lose_life` `damage` |
| Mana | `add_mana` `add_mana_per` `extra_land_drop` |
| Stack | `counter` |
| Control flow | `if` `for_each` `may` `choose_mode` `repeat` `snapshot` `noop` `delay` |

## Selectors — "which objects"

Every key is optional; all present keys must match.

```jsonc
{
  "zone": "battlefield",          // library|hand|battlefield|graveyard|exile|stack|command
  "controller": "you",            // you|opponent|any
  "types": ["Creature"],          // all must be present
  "any_types": ["Artifact", "Enchantment"],   // any one is enough -- "artifact or enchantment"
  "any_of": [{"self_only": true}, {"is_commander": true}],  // a union of whole selectors
  "not_types": ["Artifact"],
  "subtypes": ["Vampire"],        // any one is enough
  "supertypes": ["Basic"],
  "colors": ["B"], "keywords": ["flying"],
  "tapped": false, "attacking": true, "blocking": false,
  "is_commander": false, "is_token": false, "damaged": true,
  "power":      { "op": ">=", "value": { "const": 3 } },
  "toughness":  { "op": "<=", "value": { "const": 2 } },
  "mana_value": { "op": "<=", "value": { "const": 3 } },
  "exclude_self": true,           // "other ... you control"
  "exclude_binding": "subject",   // "each OTHER attacking creature"
  "shares_a_type_with": "subject",// "...that shares a creature type with it"
  "self_only": true,              // this permanent only
  "count": 1,                     // an int, or "all"
  "chooser": "controller",        // controller|owner|none
  "random": false,
  "name": "Forest"
}
```

`types` and `any_types` are the two halves of the same question and the
difference is load-bearing. `types` is *and* — `["Artifact", "Enchantment"]`
selects a permanent that is both at once, which on most boards is nothing.
`any_types` is *or*, matching how `subtypes` and `colors` have always behaved,
and it is what "destroy target artifact or enchantment" needs.

Neither `not_types` nor a second target spec substitutes for it. The complement
spelling is only equal for permanents with a single type, so it refuses Solemn
Simulacrum — an Artifact Creature, and a legal target for that line; and two
optional target specs destroy *up to two* permanents rather than one.

Both keys are validated against the card types the engine knows, because a typo
narrows a selector silently rather than failing: "artifact or enchantmnet" would
quietly become "artifact". `any_types` with a single entry is also refused —
`types` already says that, and two spellings of one filter is how they drift.

`any_of` is the same idea one level up, for where there is no single clause to
widen. Stumpsquall Hydra distributes counters "among **it and any number of
commanders**", and neither `self_only` nor `is_commander` is true of both
objects — they are two different descriptions, so the union has to be across
selectors rather than inside a key.

A union narrows nothing on its own and every key beside it still filters, so
`{"types": ["Creature"], "any_of": [...]}` reads "a creature that is either of
these", not "either a creature or these". A branch may not name a `zone` — that
would read as "or anything over there" and is not what it does — and a union of
one is refused, since that is a filter written the long way.

### Describing objects relative to *another* object

Every key above compares a candidate against something written into the card.
Shared Animosity cannot be said that way — "Whenever a creature you control
attacks, it gets +1/+0 until end of turn **for each other attacking creature
that shares a creature type with it**". Both halves of that clause point at
whatever attacked, which is different on every trigger.

| | |
|---|---|
| `shares_a_type_with` | matches when the candidate's subtypes intersect those of the object bound under this name. **Derived** subtypes on both sides, so a changeling or a granted type counts — which is most of what anybody plays this alongside |
| `exclude_binding` | drops the bound object from the pool |

`subtypes` cannot stand in for the first: it takes a literal list, fixed when
the card is written. Reaching for `{"count": {"attacking": true}}` instead
counts *every* attacker regardless of type, which is a different card that
loads and resolves without complaint.

`exclude_self` cannot stand in for the second, and this is the subtle one:
`exclude_self` compares against the **ability's source**, which for Shared
Animosity is the enchantment — not a creature, never attacking. It removes
nothing from a set of attackers, so every pump would be over by exactly one.

An unbound name matches **nothing** rather than everything. A trigger that did
not bind what the card thought it did is a bug, and the failure should be a card
that does nothing rather than one that pumps the whole board.

Two shorthands name a pool directly instead of searching a zone:

```jsonc
{ "target": "t1" }       // whatever was chosen for target spec t1
{ "binding": "subject" } // the object a trigger bound (the land that was played, ...)
```

On their own they *are* the whole selector. Combined with other keys they are the
**source** and the rest still filters, which is how a card asks a question about
one particular card rather than about a zone:

```jsonc
// Coiling Oracle: is the card I just bound a land?
{ "op": "snapshot", "as": "top_card", "objects": { "zone": "library", "controller": "you" } },
{ "op": "if",
  "condition": { "exists": { "binding": "top_card", "zone": "library", "types": ["Land"] } },
  "then": [ { "op": "put_onto_battlefield", "objects": { "binding": "top_card" } } ],
  "else": [ { "op": "return_to_hand",       "objects": { "binding": "top_card" } } ] }
```

Without that, the nearest thing a card could ask was "is there a land *somewhere*
in my library", which is true almost always and would have made the branch a
formality. Note the explicit `"zone": "library"` — filtering defaults to the
battlefield, and a card being asked about anywhere else has to say so.

## Value expressions

Anywhere a number is expected:

```jsonc
{ "const": 3 }
{ "x": true }                                   // the X paid when cast
{ "count": { "controller": "you", "subtypes": ["Vampire"] } }
{ "power_of": { "var": "victim" } }             // from a snapshot
{ "toughness_of": { "target": "t1" } }
{ "mana_value_of": { "target": "t1" } }
{ "life_of": "you" }                            // SUMS over its player spec
{ "min_life_of": "each_opponent" }              // the lowest, one player at a time
{ "max_life_of": "each_opponent" }              // the highest
{ "cards_in_hand": "each_opponent" }
{ "cards_drawn_this_turn": "you" }              // a tally of an event, not of objects
{ "binding": "amount" }                         // a value the trigger carried
{ "counters_on": { "counter": "+1/+1", "objects": { "self_only": true } } }
{ "sum": [a, b] } { "minus": [a, b] } { "times": [a, b] } { "max": [...] } { "min": [...] }
```

### Counting an event rather than the board

Every leaf above except one is a question about the position: how many Vampires,
how many counters, how much life. `cards_drawn_this_turn` is the exception, and
it is the reason it needed engine state rather than a new selector.

"Cards you've drawn this turn" cannot be recovered from the board. A card drawn
this turn may since have been played, discarded, bounced or drawn again, so
`{"cards_in_hand": "you"}` is a different number — and different in the
direction that matters, because the cards that make Kydele, Chosen of Kruphix
worth playing are the ones you drew *and spent*.

So `GameState.cards_drawn_this_turn` is a tally: player id -> draws, incremented
in `primitives.draw_cards` so that no route from a library to a hand can miss
it, and **cleared by the untap step**. Two things force that timing, and both
produce a wrong number rather than an error:

- The opening hand is drawn before turn 1 exists (rule 103), through the same
  `draw_cards`. Clearing at cleanup — where `damage_ledger` clears — would leave
  seven draws, or fourteen after a mulligan, sitting in the tally for the whole
  first turn.
- Cleanup is still this turn. Rule 514.3a hands priority back when cleanup
  triggers something, and a tally cleared there would read 0 while the turn was
  still running.

It is keyed by player but lives on the state and not on `PlayerState`, next to
`damage_ledger`, because it is cleared **once per turn and not once per seat**.
`lands_played` is the engine's other per-turn counter and it resets in the
active player's own untap, which is right for a land drop and wrong here: you
draw on other players' turns too.

## Costs

What an activated ability charges, and what `may`'s `pay` spends:

```jsonc
{ "mana": "{1}{U}", "tap": true, "untap": true,
  "pay_life": 3,
  "sacrifice":      { "types": ["Creature"] },   // a selector; the permanent dies
  "return_to_hand": { "types": ["Land"] },       // a selector; the permanent comes back
  "tap_permanents": { "subtypes": ["Vampire"], "count": 5 },  // taps *others*; they stay
  "discard": 1, "discard_selector": { "types": ["Land"] },
  "discard_self": true,                           // cycling: *this* card, no choice
  "remove_counters": { "counter": "-1/-1", "amount": 1 },
  "exile_from_graveyard": { "types": ["Creature"] } }
```

`return_to_hand` is not `sacrifice` with a nicer ending, and the two cards that
need it are built entirely on the difference. Meloku the Clouded Mirror and
Trench Behemoth both *replay* what they return — every bounce is another land
drop, and in a landfall deck another trigger. Written as a sacrifice they are not
worse cards or better ones, they are a different engine, and nothing on screen
would say so.

`tap_permanents` is the third of that family — "Tap five untapped Vampires you
control", Captivating Vampire — and the one thing that separates it from the
other two is that the permanents **stay**. They untap on the next untap step, so
a cost of this shape is repeatable in a way a sacrifice is not.

It is not `tap`. `tap` is the `{T}` symbol and only ever taps the source. Nor is
it the `tap` **op**: paying with the op would put the taps on resolution rather
than on activation, and would let the ability be activated with no untapped
Vampires at all — which makes it free.

`tapped: false` is forced on the pool and the loader **refuses** a card that
spells `tapped` itself, because "untapped" is in every printed line of this
shape and a cost that could re-tap something already tapped costs nothing.

Summoning sickness deliberately does not apply: rule 302.6 restricts the `{T}`
symbol in a permanent's *own* cost, and Captivating Vampire's ruling is explicit
that a Vampire which just arrived may be tapped for it — the source included.

All three take a selector over the battlefield defaulting to `controller: "you"`,
and all three make the ability **unavailable** when too little matches rather
than cheaper: an ability whose bounce cost has nothing to bounce would cost only
its mana, and a cost of five that settled for four would be a different card.

## Player specs

`"you"` · `"opponent"` / `"each_opponent"` · `"each_player"` · `"active_player"` ·
`{ "target": "t1" }` · `{ "controller_of": "snapshot_name" }` ·
`{ "owner_of": "snapshot_name" }`

## Conditions

```jsonc
{ "cmp": ">=", "left": {...}, "right": {...} }
{ "all": [...] }  { "any": [...] }  { "not": {...} }
{ "exists": { selector } }
{ "zone_is": "battlefield" }
{ "is_your_turn": true }
```

## Triggers

```jsonc
{
  "kind": "triggered",
  "active_zones": ["battlefield"],   // add "command" for eminence-style abilities
  "trigger": {
    "event": "permanent_enters",
    "controller": "you",             // whose action must it be
    "source": "self",                // restrict to this permanent
    "filter": { "types": ["Land"] }, // a selector applied to the event's subject
    "condition": { ... },            // intervening "if", re-checked on resolution
    "defending": "you",              // `attacks` only: whom it is attacking
    "not_cause": "kodama_of_the_east_tree", // enters triggers only: a loop guard
    "counter": "+1/+1"               // `counter_placed` only: which kind
  },
  "effects": [ ... ]
}
```

`not_cause` is "…**if it wasn't put onto the battlefield with this ability**".
Zone changes carry a `cause`, and `put_onto_battlefield` can set its own, so an
ability that puts permanents down can refuse to trigger on its own output.
Checked on the trigger rather than as a condition because by the time the ability
resolves the cause is no longer anywhere to be read. Without it Kodama of the
East Tree triggers on the permanent it just put down, and again on that one's,
until the loop guard kills the game.

`self_enters` and `permanent_enters` are the *same* engine event, separated only
by `source: "self"` — so the loader supplies it for `self_enters` rather than
trusting each card file to remember. Omitting it once produced cards that fired
on every permanent entering, silently, and invisibly until a second permanent
showed up.

`defending` is **not** a synonym for `controller`. `controller` says whose
creature is swinging; `defending` says who is being swung at. "Whenever a
creature attacks you" needs the second, and in a duel the two are
indistinguishable — which is exactly why writing it with `controller:
"opponent"` looks right until a pod draws you a card for a combat you were not
in. The loader rejects `defending` on any other event rather than ignoring it.

`counter` names which kind a `counter_placed` trigger cares about. The event has
always carried the kind and nothing read it, so the only trigger that could be
written fired on *every* kind — and the shipped pool places `charge` and
`slumber` counters, so Fathom Mage's "whenever a +1/+1 counter is put on this
creature" would also draw off Arixmethes waking up. The kind is also copied into
`bindings` beside `amount`, so effects can read what fired them. Rejected on any
other event, for the same reason as `defending`.

One placement is one trigger, however many counters it puts: `add_counters`
fires a single event with `amount` on it. That is correct for "a +1/+1 counter"
and for Sharktocrab's "one or more +1/+1 counters" alike, so neither needs
batching work.

Events: `self_enters` · `permanent_enters` · `dies` · `creature_dies` ·
`leaves_battlefield` · `land_played` · `spell_cast` · `attacks` · `blocks` ·
`deals_combat_damage_to_player` · `upkeep` · `draw_step` · `begin_combat` ·
`end_step` · `you_gain_life` · `counter_placed` · `draw` · `discard` · `cycle`

**`discard` names the player who discarded**, through the ordinary `controller`
clause — which defaults to `"you"`, so Sangromancer's "whenever an *opponent*
discards a card" must say so or it watches the wrong seat and never fires. One
trigger per card, because `discard_cards` fires per card, so an effect taking
two is two triggers. It fires for every discard there is: a discard effect, the
cleanup step's trim to hand size (rule 514.1), and a cycling cost (rule
702.29a) — a version that missed the last two would be quiet in almost every
real game. The discarded card is the trigger's subject, so a `filter` may ask
what it was, and it reads the printed face out of the graveyard.

**Landfall is not `land_played`.** "Whenever a land you control enters" is
`permanent_enters` with a `{"types": ["Land"]}` filter, and it fires however the
land arrived — played, or put there by Cultivate. `land_played` is the narrower
"whenever you *play* a land", which Cultivate does not do; only Horn of Greed
wants it. Reading the first as the second is a silent defect, because the card
still works on your own land drops and only goes quiet on ramp — it is exactly
what was wrong with Aesi (see [bugs.md](bugs.md)).

Triggers carry bindings the effects can read: `subject` (the object the event was
about), `amount` (damage dealt, life gained), `self`, `x`, `defender` (the player
attacked), and `was_attacking` on `leaves_battlefield`.

`was_attacking` is 1 or 0 rather than a boolean, so it reads with the ordinary
`{"binding": "was_attacking"}` value expression and needs no new condition
vocabulary:

```jsonc
{ "op": "if",
  "condition": { "cmp": ">=", "left": { "binding": "was_attacking" },
                 "right": { "const": 1 } },
  "then": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ],
  "else": [ { "op": "lose_life", "player": "each_opponent", "amount": { "const": 1 } } ] }
```

It is last-known information and has to be: by the time the trigger resolves the
object is out of combat and there is nothing left to ask. It is snapshotted where
`was_creature` already was — the one LKI case a card cannot reach with a
`snapshot` op of its own, because the object has already gone.

## Static abilities

Parameters are flattened onto the ability, and the filter may only read **printed**
characteristics — the loader rejects anything else. See
[engine-rules.md](engine-rules.md#derived-characteristics-layers-lite) for why.

```jsonc
{ "kind": "static", "effect": "buff",
  "affects": { "controller": "you", "subtypes": ["Vampire"], "exclude_self": true },
  "power": { "const": 1 }, "toughness": { "const": 1 } }
```

Effects: `buff` · `grant_keyword` · `set_pt` · `add_subtype` · `set_types` ·
`block_restriction` ·
`extra_land_drops`, plus the player-wide ones below.
Values inside a static may only be `{"const": n}` or `{"count": filter}`.

`set_types` **replaces** the printed types rather than adding to them —
Arixmethes is "a land (it's not a creature)", which `add_subtype` cannot say. A
`{"count": filter}` value is also how a creature printed `*/*` works:

```jsonc
{ "kind": "static", "effect": "set_pt", "affects": { "self_only": true },
  "power":     { "count": { "controller": "you", "types": ["Land"] } },
  "toughness": { "count": { "controller": "you", "types": ["Land"] } } }
```

### "As long as…"

A static may carry a `condition`: a small boolean tree that switches the whole
static on and off as the board moves. There is no trigger and nothing goes on
the stack — the effect simply exists whenever the condition holds, and stops
existing the instant it does not, including mid-combat and on someone else's
turn.

```jsonc
// Arixmethes — "as long as it has a slumber counter on it, it's a land"
{ "kind": "static", "effect": "set_types",
  "affects": { "self_only": true }, "types": ["Land"],
  "condition": { "counters": { "counter": "slumber", "op": ">=", "amount": 1 } } }

// Nimble Mongoose — "Threshold — gets +2/+2 as long as there are seven or
// more cards in your graveyard"
{ "kind": "static", "effect": "buff", "affects": { "self_only": true },
  "power": { "const": 2 }, "toughness": { "const": 2 },
  "condition": { "cmp": ">=",
                 "left":  { "count": { "zone": "graveyard", "controller": "you" } },
                 "right": { "const": 7 } } }
```

Each node names **exactly one** form:

| form | asks |
|---|---|
| `{"counters": {"counter": …, "op": …, "amount": …}}` | how many counters of a kind sit on the static's own source |
| `{"cmp": op, "left": …, "right": …}` | compares two static values (`{"const": n}` or `{"count": filter}`) |
| `{"exists": filter}` | does anything match — `count > 0`, spelled the way it reads |
| `{"all": [ … ]}` / `{"any": [ … ]}` / `{"not": …}` | combine the above |
| `{"is_your_turn": true}` | whether it is the source's controller's turn |

This is a **mirror** of the `if`-effect condition language in
`engine/effects/conditions.py`, not that language. The keys it does not have —
`zone_is`, `kicked`, `evoked` — are not oversights: they read a resolving
object's state, and a static is evaluated for every permanent on every cache
miss. Borrowing one is a `DslError` at load.

The line that decides what may be in this table is the same one that shapes
`affects` filters: **a static may read pipeline inputs, never pipeline outputs.**
A condition is evaluated in `_battlefield_statics`, *before* the first layer
applies, so counters, printed characteristics, zone contents and whose turn it
is are all safe — no layer can change whether another static is switched on, and
the fixed order stays acyclic. A **life total** is safe for exactly that reason
too, and `min_life_of` / `max_life_of` are in the table: nothing in the pipeline
can change what a player's life is.

`life_of` itself is deliberately *not*, and the difference is the whole point.

#### "An opponent has 10 or less life"

`life_of` **sums** over its player spec, and `"opponent"` and `"each_opponent"`
name the same set — so `{"life_of": "opponent"} <= 10` asks whether your
opponents' *combined* life is 10 or less. In a duel that is the printed card. At
a Commander table it is a different card and backwards: three opponents at 4
life sum to 12, so Guul Draz Vampire would stay a 1/1 against a table in burn
range, and Vampire Lacerator would drain its controller at the same moment.

So the leaves ask about one player at a time:

```jsonc
{ "cmp": "<=", "left": { "min_life_of": "each_opponent" }, "right": { "const": 10 } }
// "an opponent has 10 or less life"   -- the existential

{ "cmp": "<=", "left": { "max_life_of": "each_opponent" }, "right": { "const": 10 } }
// "each opponent has 10 or less life" -- the universal
```

`min` and `max` already existed and cannot stand in: they take a literal list of
value expressions written into the card, and no player spec enumerates opponents
one at a time to feed them.

With nobody selected, `min_life_of` reports a life total nothing reaches rather
than 0 — "an opponent has 10 or less life" has to be **false** when there are no
opponents, and a minimum of 0 would make it vacuously true. `max_life_of`
returns 0 there, because "each opponent has…" over nobody is vacuously true and
that reading is correct.

Both work in the `if`-effect language and in a static's `condition`; the two are
validated separately, so a leaf added to one and not the other would load in a
card that then quietly read 0.

#### Counting filters, and the `zone` key

A filter in a *counting* position — `{"count": …}` in a static value, or
`exists` — may name a `zone`: `battlefield` (the default), `graveyard`, `hand`,
`exile`, `library` or `command`, scoped by `controller` (`you`, `opponent`,
`any`). That is what makes Threshold, Delirium and Hellbent expressible.

Off the battlefield only the printed face and the owner are readable. A card in
a graveyard is not tapped, not attacking and attached to nothing, so `tapped`,
`attacking`, `blocking`, `attached`, `self_only`, `exclude_self`, `is_token` and
`is_commander` are rejected there at load time rather than loading and matching
nothing.

`affects` and `blockers` do **not** take `zone`, and that asymmetry is the
point: they pick out the permanents a static applies to, and there are no
permanents outside the battlefield. A zone there would load clean and do
nothing, which is the one failure this format exists to refuse.

## Worked examples

A basic land:

```json
{
  "id": "island", "name": "Island",
  "supertypes": ["Basic"], "types": ["Land"], "subtypes": ["Island"],
  "abilities": [
    { "kind": "activated", "is_mana_ability": true,
      "cost": { "tap": true },
      "effects": [{ "op": "add_mana", "mana": "{U}" }] }
  ]
}
```

A commander with a trigger and a static, plus a command-zone ability:

```json
{
  "id": "aesi_tyrant_of_gyre_strait", "name": "Aesi, Tyrant of Gyre Strait",
  "mana_cost": "{4}{G}{U}",
  "supertypes": ["Legendary"], "types": ["Creature"], "subtypes": ["Serpent"],
  "power": 5, "toughness": 5,
  "abilities": [
    { "kind": "triggered",
      "trigger": { "event": "permanent_enters", "controller": "you",
                   "filter": { "types": ["Land"] } },
      "effects": [
        { "op": "may", "prompt": "Draw a card?",
          "effects": [{ "op": "draw", "player": "you", "amount": { "const": 1 } }] }] },
    { "kind": "static", "effect": "extra_land_drops",
      "affects_player": "you", "amount": { "const": 1 } }
  ]
}
```

Last-known information, made explicit:

```json
{
  "id": "swords_to_plowshares", "name": "Swords to Plowshares",
  "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
  "mana_cost": "{W}", "types": ["Instant"],
  "targets": [
    { "id": "t1", "kind": "permanent",
      "selector": { "zone": "battlefield", "types": ["Creature"] }, "count": 1 }
  ],
  "spell_effects": [
    { "op": "snapshot", "target": "t1", "as": "victim" },
    { "op": "exile", "objects": { "target": "t1" } },
    { "op": "gain_life",
      "player": { "controller_of": "victim" },
      "amount": { "power_of": { "var": "victim" } } }
  ]
}
```

Without the `snapshot`, the creature would already be gone by the time the life gain
is computed. Declaring it is the engine's substitute for a general LKI system.

## Making a token that is already attacking

```jsonc
{ "op": "create_token", "token": "warrior_1_1_r",
  "amount": { "const": 1 }, "tapped": true, "attacking": true }
```

`attacking` puts the token into combat against **whoever the source is already
attacking**, which is what a mobilize-style trigger means. Outside combat, or
from a source that is not itself attacking, there is nobody to join and the
token simply arrives (tapped, if asked).

A token created this way was never *declared* as an attacker, so it triggers
nothing that fires on attacking. That is the real rule, and it is also what keeps
"whenever this attacks, make a token that is attacking" from making tokens
forever.

## Mana abilities

A mana ability must contain only `add_mana`, or a single `choose_mode` whose modes each
contain only `add_mana`. The loader enforces this, and it is why a dual land never stops
to ask which colour: the payment solver picks the mode, records the option index, and
the engine adds exactly that mana without running the effect interpreter at all.

### "Add {G} for each …"

The one part of a mana ability that is not a constant. `add_mana` takes an
optional `amount`, an ordinary value expression evaluated **when the ability is
activated**, multiplying the symbols it produces:

```jsonc
// Gyre Sage: {T}: Add {G} for each +1/+1 counter on this creature.
{ "op": "add_mana", "mana": "{G}",
  "amount": { "counters_on": { "counter": "+1/+1",
                               "objects": { "self_only": true } } } }

// Gaea's Cradle: {T}: Add {G} for each creature you control.
{ "op": "add_mana", "mana": "{G}",
  "amount": { "count": { "controller": "you", "types": ["Creature"] } } }

// Kydele, Chosen of Kruphix: {T}: Add {C} for each card you've drawn this turn.
{ "op": "add_mana", "mana": "{C}",
  "amount": { "cards_drawn_this_turn": "you" } }
```

This does not break rule 605's "a mana ability never stops to ask": evaluating
the amount asks nothing, it only looks at the board.

Kydele is the one whose multiplier can move at instant speed — drawing a card is
something a player can do with a payment open — which makes "read it at
activation" load-bearing rather than merely convenient. A board count settles
between the offer and the tap; this one need not.

Three constraints, each with a failure behind it:

- **One `add_mana`, or no amount.** An amount scales one symbol tuple, so a
  card that also summed several `add_mana`s or offered modes would have nothing
  single to scale.
- **No `x`, `binding` or `loop_value`.** A mana ability is activated inside cost
  payment: there is no X, no trigger binding and no enclosing loop, so each
  would read 0 and make a card that silently taps for nothing. Refused at load.
- **It is read before the tap.** The payment solver enumerates sources while
  they are still untapped; measuring after tapping would let the offer and the
  payment see two different boards.

That last one is the property the whole feature is shaped around. The multiplier
is threaded through `costs.mana_produced`, which is the single function both the
solver's `_sources_of` and `activate_mana_ability` already call — so the price a
spell is *offered* at and the mana a tap actually *makes* cannot be given
different numbers. A spell offered on mana that does not materialise strands the
payment mid-cast, and nothing on screen would say why.

### Hybrid costs

`{W/U}` and `{2/W}` are parsed and paid properly. A hybrid pip is kept *apart*
from the fixed `colored` pips, because it is not a fixed demand — folding
`{G/U}` into a `{G}` would make it uncastable off Islands, which is the whole
point of the symbol. Both colours count towards the card's colour identity, and
`{2/W}` has mana value 2 while `{W/U}` has 1.

Assignment is exhaustive rather than greedy, and shared by `satisfies` (can this
be paid?) and `ManaPool.spend` (pay it). The choices interact: with one white and
one blue, `{W/U}{W/U}` is payable only if the two pips take different symbols,
and any "most plentiful first" rule gets that wrong. **Phyrexian** (`{W/P}`) is
still rejected — it is a life payment, not a colour choice.

### Restricted mana

```jsonc
{ "kind": "activated", "is_mana_ability": true, "mana_restriction": "creature",
  "cost": { "tap": true }, "effects": [ ... ] }
```

"Spend this mana only to cast a creature spell." Enforced by *filtering sources*
before the solver sees them, never by tagging the pool — which works only because
mana here is tapped at the moment it is spent, so the question has an answer
exactly when it is asked. The solver's inner loop never learns restrictions
exist.

Legality and payment must ask that question identically; both derive it from
`costs.spell_purpose`. With no spell in mind, restricted mana is not counted at
all: an under-count, which is the safe direction for a number the AI reads.

## Adding an op

1. Write the function in the right `effects/ops_*.py` and decorate it with
   `@register("name")`. Make it a generator if it needs a decision.
2. Add a unit test.
3. That is all — the loader now accepts it, and card files can use it.

## Generated cards, and promoting one

Deck import writes card files too. `src/automtg/cards/proxy.py` turns a catalog
row into a `CardModel` for a card nobody wrote rules for: real name, cost, types,
stats, colours, the keywords the engine implements, and a `{T}: Add` mana ability
where there is one. **Everything else its printed text claims does nothing**, and
every such simplification is recorded and shown at import.

Those land in `data/generated/cards/pool.cards.json`, which is gitignored and is
**not** loaded by `default_registry()` — see [deck-import.md](deck-import.md) for
why that separation is load-bearing.

The generator emits a `CardModel` and runs it through the same `compile_card`
above, so it gets the identical vocabulary and constraint validation, and a
generator bug is a `DslError` at import time rather than a card that looks
implemented and does nothing.

That also gives a **promotion path**, which is how the proxy backlog gets burnt
down one card at a time:

1. Find the card in `data/generated/cards/pool.cards.json`. It is already in
   this file format.
2. Move the object into an authored file in `data/cards/`.
3. Fill in its `abilities` / `spell_effects` by hand, using everything above.
4. Delete it from the pool.

It is now a first-class card with the full test suite behind it, and every deck
that references that id picks up the real rules on the next import.

## Auras and Equipment

An Aura's "Enchant creature" line is not an ability — it is the spell's
targeting clause, so it is written as a `target` and the engine attaches the
permanent to what it targeted once it is on the battlefield:

```jsonc
{
  "id": "pacifism", "name": "Pacifism", "mana_cost": "{1}{W}",
  "types": ["Enchantment"], "subtypes": ["Aura"],
  "targets": [
    { "id": "t1", "kind": "permanent",
      "selector": { "zone": "battlefield", "types": ["Creature"] }, "count": 1 }
  ],
  "abilities": [
    { "kind": "static", "text": "Enchanted creature gets -2/-0.",
      "effect": "buff", "affects": { "attached": true },
      "power": { "const": -2 }, "toughness": { "const": 0 } }
  ]
}
```

`{"attached": true}` means "the permanent this is attached to". It is checked
before `controller` and short-circuits it, because an Aura on an opponent's
creature still affects that creature and the default `controller: "you"` would
quietly stop it.

Equipment needs nothing new — `Equip {2}` is an ordinary sorcery-speed activated
ability whose effect is `attach`:

```jsonc
{ "kind": "activated", "text": "Equip {1}", "sorcery_speed_only": true,
  "cost": { "mana": "{1}" },
  "targets": [ { "id": "t1", "kind": "permanent",
    "selector": { "zone": "battlefield", "controller": "you", "types": ["Creature"] },
    "count": 1 } ],
  "effects": [ { "op": "attach", "objects": { "target": "t1" } } ] }
```

Attaching during an Aura's `spell_effects` does **not** work, and the failure is
silent: `move_object` calls `reset_permanent_state` on the way onto the
battlefield, which clears `attached_to`, so the Aura arrives enchanting nothing
and state-based actions put it in the graveyard.

## Untapping on somebody else's turn

    Murkfiend Liege — "Untap all green and/or blue creatures you control during
    each other player's untap step."

```jsonc
{ "kind": "static", "effect": "untap_during_each_untap_step",
  "affects": { "controller": "you", "types": ["Creature"], "colors": ["G"] } }
```

Read by `turn._untap_step`, not by the characteristics pipeline — it is a fact
about *when a set of permanents untaps*, which no characteristic can carry, and
it sits beside the player-wide statics below for that reason.

A trigger cannot do this, and the gap record checked all three routes: there is
no untap-step entry in `TRIGGER_EVENTS`; `_untap_step` uses `state.emit` rather
than `fire`, so no ability is scanned there at all; and the untap step grants no
priority, so a trigger would resolve a step late and be respondable when the
printed static is not.

`skip_next_untap` still wins — a prohibition beats a permission — and the
"**each other** player's" clause is load-bearing in a way that is easy to lose:
on your own untap step these creatures untap regardless, so a version that
ignored whose turn it is looks identical on every board you would think to try.

## Player-wide statics

Seven static effects describe the *player* rather than a characteristic, so they
take `affects_player` instead of `affects`:

```jsonc
{ "kind": "static", "effect": "extra_land_drops",
  "affects_player": "you", "amount": { "const": 1 } }
{ "kind": "static", "effect": "no_hand_limit", "affects_player": "you" }
{ "kind": "static", "effect": "play_lands_from_graveyard", "affects_player": "you" }
{ "kind": "static", "effect": "play_lands_from_library_top", "affects_player": "you" }
{ "kind": "static", "effect": "double_land_triggers", "affects_player": "you" }
{ "kind": "static", "effect": "double_land_mana", "affects_player": "you" }
{ "kind": "static", "effect": "freeze_opponent_lands", "affects_player": "opponent" }
```

`double_land_triggers` is Ancient Greenwarden: a land entering makes each of your
permanents' triggers fire an additional time. Read by `triggers.collect`, which
queues the ability **twice** rather than resolving it twice — the two copies are
separate abilities on the stack and anything in between still goes between them.

The last two are Vorinclex's halves, and neither can be a triggered ability:
tapping for mana happens *inside* payment, where nothing may go on the stack and
nothing may stop to ask. Both are read at `costs.activate_mana_ability` instead.
`double_land_mana` is also read by `_sources_of`, so legality counts the extra
mana — a spell offered on doubled mana and then paid for on single mana would
strand the payment mid-cast, which is why both go through one `mana_produced`
helper.

`freeze_opponent_lands` sets a **one-shot** `skip_next_untap`, cleared by the
untap step it skips. That is deliberately not the `frozen_by` lock used by
`freeze`, which holds for as long as its source is on the battlefield: two
different lifetimes, so two different fields.

The two land permissions widen *where* a land may be played from, never how
many — `lands_played` still enforces one drop a turn, so Ramunap Excavator plus
Dryad of the Ilysian Grove is two drops from anywhere, which is correct.

`play_lands_from_library_top` offers the top card only. That is what the cards
say, and it is also the only part of a hidden zone anybody is entitled to see.

## "Sacrifice it unless you…"

`may` takes an `else`, and that is what turns an optional effect into a cost:

```jsonc
{ "op": "if",
  "condition": { "exists": { "zone": "battlefield", "controller": "you",
                             "subtypes": ["Island"], "tapped": false } },
  "then": [ { "op": "may",
              "prompt": "Return an untapped Island you control to its owner's hand?",
              "effects": [ { "op": "return_to_hand", "objects": { ... } } ],
              "else":    [ { "op": "sacrifice", "objects": { "self_only": true } } ] } ],
  "else": [ { "op": "sacrifice", "objects": { "self_only": true } } ] }
```

The outer `exists` guard is not optional bookkeeping. Without it the card offers
a "may" that can be accepted when there is nothing to return, and a Karoo land
that never costs anything is simply a better card than the one printed — the
failure this whole format exists to refuse.

`may` also takes `condition` (ask only while it holds) and `repeat` (ask again
after each yes, stop at the first no), which together are "…if you do, draw a
card and **repeat this process**":

```jsonc
{ "op": "may", "repeat": true,
  "prompt": "Put a land card from your hand onto the battlefield tapped?",
  "condition": { "exists": { "zone": "hand", "controller": "you", "types": ["Land"] } },
  "effects": [ { "op": "put_onto_battlefield", "objects": { ... }, "tapped": true },
               { "op": "draw", "player": "you", "amount": { "const": 1 } } ] }
```

A loop rather than a counted `repeat` because the number of iterations is not
knowable up front — Cultivator Colossus draws into the lands it is putting down —
and because a counted version would let a player decline and then accept, which
the printed card does not. Bounded at 100 iterations, like `repeat`.

### "You may pay {2}. If you do…"

`pay` puts a price on the option. It is an ordinary activated-ability `Cost`,
paid out of the pool while the ability resolves, and `effects` become the "if you
do" branch — they run only when the payment completed:

```jsonc
// Seer's Sundial: Landfall — whenever a land you control enters,
//                 you may pay {2}. If you do, draw a card.
{ "op": "may", "pay": { "mana": "{2}" },
  "effects": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ] }
```

Every other cost in the engine hangs off the object being cast or activated and
is read once, at that moment. A triggered ability fires on its own, so before
this the only way to write that card was to drop the {2} — and a Sundial that
draws free is a better card than the printed one.

A cost the player cannot afford is not offered at all, rather than asked and
then failed. The full `Cost` shape is accepted, not just mana, and it is
validated at load time through the same model an ability's cost uses, so a
misspelled key is a load error rather than a cost silently dropped.

### "…unless that player pays {1}"

The same op, with two things moved. `player` says *who is asked* — it has always
taken a full player spec, so `{"controller_of": "subject"}` on a `spell_cast`
trigger names the opponent who cast the spell — and the consequence goes in
`else` rather than `effects`, because what the payer buys is the **absence** of
the other branch:

```jsonc
// Rhystic Study: whenever an opponent casts a spell,
//                you may draw a card unless that player pays {1}.
{ "op": "may",
  "player": { "controller_of": "subject" },
  "prompt": "Pay {1} to stop Rhystic Study's draw?",
  "pay": { "mana": "{1}" },
  "else": [ { "op": "may", "player": "you",
              "effects": [ { "op": "draw", "player": "you",
                             "amount": { "const": 1 } } ] } ] }
```

Note the nesting: the outer `may` is the opponent's payment, the inner one is
your own "you *may* draw". Two players, two questions, one op.

Because the payer gets nothing when they pay, `effects` is empty here — so the
guard is that a `pay` needs **`effects` or `else`**. Paying for nothing at all
is still refused; paying to stop something is the card.

"A cost they cannot afford is not offered" matters more in this direction than
the other (rule 118.4): an opponent tapped out is not asked, and the draw simply
happens.

## Modal spells with a target

`choose_mode` picks its mode as the spell is **cast** (rule 601.2b), but a
spell's *targets* are enumerated as part of the action, so they are chosen
first — the reverse of the printed order, and a
[documented simplification](rules-coverage.md). Where the modes point at
different things, that gap is closed by declaring one **optional** target that
the modes that need it share:

```jsonc
"targets": [
  { "id": "t1", "kind": "permanent", "count": 1, "optional": true,
    "selector": { "zone": "battlefield", "types": ["Creature"] } }
],
"spell_effects": [
  { "op": "choose_mode", "count": 1, "modes": [
    { "label": "Target creature gets +3/+3 until end of turn",
      "effects": [ { "op": "pump", "objects": { "target": "t1" }, ... } ] },
    { "label": "Permanents you control gain hexproof until end of turn",
      "effects": [ { "op": "grant_keyword", ... } ] },
    { "label": "Return target creature to its owner's hand",
      "effects": [ { "op": "return_to_hand", "objects": { "target": "t1" } } ] }
  ] }
]
```

`optional: true` is what makes Simic Charm castable with no creature anywhere —
its second mode needs no target, and without the flag the card would vanish from
the hand's legal actions exactly when that mode is the one you want. **Moving
modes to cast time did not retire this idiom**: targets are still picked before
modes, so the flag is as necessary as it ever was. The one new wrinkle is that a
player can now choose a target-needing mode having declined the optional target,
and it fizzles to nothing.

Cast-time selection only applies when the card's whole effect tree holds
**exactly one** `choose_mode` and it sits at the top level (`CardDef
.cast_time_modes`). A nested one is a second question and keeps resolving late,
as does any `choose_mode` inside a *triggered* ability — a trigger has no moment
of casting to be asked at. Mana abilities are a third exception and a stricter
one: their modes are compiled into `mana_options` and never reach the
interpreter at all.

Gate 5 of the authoring verifier drives the **first** mode only, so a modal card
wants a unit test per mode; `tests/unit/test_modal_spells.py` is the pattern and
`tests/unit/test_cast_time_modes.py` pins the timing.

## Creature-lands

"Until end of turn, this land becomes a 4/4 white and blue Elemental creature
with flying and vigilance. It's still a land."

```jsonc
{ "op": "animate",
  "power": { "const": 4 }, "toughness": { "const": 4 },
  "types": ["Creature"],            // added, never replacing what is printed
  "subtypes": ["Elemental"],
  "colors": ["W", "U"],
  "keywords": ["flying", "vigilance"],
  "objects": { "zone": "battlefield", "self_only": true } }
```

One op for the whole sentence, keywords included, because the residual gate asks
each *ability* which printed line it implements and this is one line.

**Not `set_pt`.** That op is a compensating pump over whatever the permanent's
power happens to be at that moment; `animate` names the **base** value, so
`+1/+1` counters and anthems add to it rather than being cancelled by it. In
`characteristics._compute` the animation runs before every static, which is what
makes that true.

Nothing else is needed for the card to behave: `summoning_sick` is
`entered_turn >= turn`, so a land that has been down since last turn attacks and
one played this turn does not, and the mana solver reads derived types, so an
animated land played this turn correctly stops making mana too.

`{T}` is *not* part of the cost — a manland that is tapped for mana cannot then
attack, and that falls out of the tap rather than being written down.

## Monstrosity, and holding creatures down

```jsonc
{ "op": "monstrosity", "amount": { "const": 4 } }
```

Puts the counters on and sets a one-way `monstrous` flag. The flag *is* the
mechanic: without it the ability is a repeatable pump and the
`becomes_monstrous` trigger fires every time instead of once.

```jsonc
{ "op": "freeze", "objects": { "target": "t1" } }
```

"…don't untap during their controllers' untap steps for as long as you control
this creature." The frozen permanent records the **oid of the source** rather
than a flag with a lifetime of its own, because the hold has to end when the
source leaves and pointing at it is the only way the untap step can tell.

## "It becomes a Vampire in addition to its other types"

```jsonc
{ "op": "add_subtype", "subtypes": ["Vampire"], "objects": { "target": "t1" } }
```

The **op** and the `add_subtype` **static effect** share a name and read alike
in English. They are different mechanisms and the printed lines differ the same
way:

| | |
|---|---|
| static | "Creatures you control are Vampires" — continuous, applies to whatever currently matches the filter, ends when its source leaves |
| op | "It becomes a Vampire" — written onto **one object**, and it stays there after the permanent that converted it is dead |

The subtype lives on `GameObject.added_subtypes` and is cleared by
`reset_permanent_state`, so a permanent that leaves and comes back arrives with
its printed type line — the same contract counters and `chosen_type` have.

**A static's `affects` filter can see it**, which is unusual and deliberate.
`_matches` reads the *printed* face precisely so that no static can depend on
another static's output; a subtype recorded on the object is a pipeline **input**
rather than an output, so letting it through introduces no such dependency. It
has to be let through, because Captivating Vampire's own "other Vampire
creatures you control get +1/+1" is the reason to convert the creature at all.

Subtypes only. `types` is refused rather than dropped — "becomes an artifact in
addition to its other types" is a different sentence, and `animate` and the
`set_types` static are what change a card type.

## Gaining control of a permanent

```jsonc
{ "op": "gain_control", "objects": { "target": "t1" } }
```

"Gain control of target creature." `player` says who gains it and defaults to
the ability's controller, which is what every "*you* gain control" line means.

The object does not move. `controller` is a field on `GameObject` and
`state.battlefield` is one shared list, so the change is that field plus the
three rules that hang off it:

| | |
|---|---|
| **302.6** | it has not been under the new controller since their turn began, so it is summoning sick for them — `entered_turn` is reset, which is both the record and the sickness |
| **506.4** | changing control removes a permanent from combat, or a creature stolen mid-combat goes on dealing damage for the player who no longer controls it |
| **400.3** | zone destinations still follow the **owner**, so a stolen creature that dies goes to its owner's graveyard. This needed no code — `move_object` was always owner-based |

Every static filtered on `controller` reads differently afterwards, so the
characteristics cache is dropped with it.

**There is no until-end-of-turn form**, and the loader *refuses* a `duration`
key rather than ignoring one. Act of Treason written as a permanent steal is a
strictly better card than the printed one, and it would load clean.

`control_changed` is its own event for the same reason: every other way a
permanent arrives on somebody's side of the board is a zone change, and a log
built from zone changes alone would show a creature silently swapping sides.

## "Its activated abilities can't be activated this turn"

```jsonc
{ "op": "lock_abilities", "objects": { "target": "t1" } }
```

An until-end-of-turn effect, so the cleanup step already removes it. It is
deliberately *not* a keyword: a keyword is a characteristic and would show in the
card's keyword list, and this is a permission. It is read by `legality` and by
the mana solver — mana abilities are activated abilities too, and a locked land
that still tapped for mana would make the effect worth nothing.

## Cost reduction

```jsonc
{ "id": "ghalta_primal_hunger", "mana_cost": "{10}{G}{G}",
  "cost_reduction": { "total_power": { "controller": "you", "types": ["Creature"] } } }
```

Also `{"count": filter}`, for "costs {1} less for each…". Generic only, clamped
at zero: "costs {X} less" never reaches through the generic part into the
coloured pips, which is both the rule and the only thing the payment solver could
act on. Mana value stays what is printed.

Read off the board every time it is asked for, never stored — Ghalta is a
twelve-drop or a two-drop depending on what is already in play. Legality and
payment both call `costs.cost_reduction`, because a reduction one of them knows
about and the other does not is the difference between an uncastable card and a
free one.

The filter may only read printed characteristics, like a static's: it is
evaluated while deciding what is castable, before anything is on the stack.

### Making *other* spells cheaper

`cost_reduction` discounts the card that carries it. Warden of Evos Isle
discounts a different card, chosen by *that* card's printed face — a different
question, so a different mechanism:

```jsonc
// Warden of Evos Isle — "Creature spells with flying you cast cost {1} less."
{ "kind": "static", "effect": "spell_cost_reduction",
  "affects_spells": { "controller": "you",
                      "types": ["Creature"], "keywords": ["flying"] },
  "amount": { "const": 1 } }
```

**`affects_spells`, not `affects`.** `affects` names permanents and carries
board state — `tapped`, `attacking`, `attached` — and a spell being priced is
still in hand and has none of it. This filter reads the printed face plus who is
casting, and the loader refuses the board-state keys there rather than letting
them load and match nothing.

Both halves are required. A `spell_cost_reduction` with no filter or no amount
would load clean and discount either everything or nothing, and both look
identical on a board.

It is applied inside `costs.cost_reduction`, the same function the card-level
field goes through — so legality and payment cannot disagree about it, for the
same reason and by the same route. A `spell_cast` trigger cannot substitute: it
fires after the spell is paid for, so the best it could do is refund mana, which
is not the same as being able to afford the spell.

## Kicker

An additional cost the caster may choose to pay. Two fields, and they only mean
anything together:

```jsonc
{
  "id": "into_the_roil",
  "mana_cost": "{1}{U}",
  "kicker": "{1}{U}",
  "spell_effects": [
    { "op": "return_to_hand", "objects": { "target": "t1" } },
    { "op": "if", "condition": { "kicked": true },
      "then": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ] }
  ]
}
```

Legality offers a kickable card **twice** — unkicked first, then kicked, when the
extra mana is there — and the two are different actions, not one action with a
flag the client sets. `kicker` is deliberately not folded into `mana_cost`: mana
value stays what is printed, and the choice is the mechanic.

The loader rejects **half** a kicker in either direction: a `kicker` cost that no
effect reads via `kicked`, and a `kicked` condition on a card with no `kicker`.
One is a spell that charges more and does the same thing; the other is a clause
that can never fire. Both load cleanly and neither shows on the board, which is
why they are caught at load time.

Gate 5 of the authoring verifier measures a kicker card **kicked**, because that
is the strictly larger claim; gate 4 still casts it unkicked, so neither line
goes unexercised.

### A permanent's own enters trigger can read it

Slinn Voda's "When this creature enters, **if it was kicked**, return all
creatures…" is not a `spell_effects` clause — it is an ETB trigger, and by the
time it resolves the `StackItem` carrying the flag is gone.

So the flag is written onto the object at resolution and survives onto the
battlefield, exactly as `cast_x` already did for "enters with X counters":

```jsonc
{ "kind": "triggered",
  "trigger": { "event": "self_enters", "condition": { "kicked": true } },
  "effects": [ ... ] }
```

Worth knowing because of how this failed before: the card **loaded cleanly** —
the half-a-kicker guard is satisfied, since something does read `kicked` — and
the clause was then silently unreachable. You paid the extra {1}{U} and nothing
happened. `{"kicked": ...}` now reads the resolution context *or* the object,
which are the flag's two lifetimes and never overlap.

## Delayed triggers — "at the beginning of the next …"

Every other trigger in the engine fires *from* an event that has just happened.
This is the other shape: an effect that has already resolved arranging for
something to happen later, with no object left to hang a trigger on. Arcane
Denial is the whole argument for it — without the delayed draws it is a strictly
worse Counterspell, and nothing on screen would say so.

```jsonc
{ "op": "delay", "step": "upkeep",
  "text": "At the beginning of the next turn's upkeep, draw a card.",
  "effects": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ] }
```

`step` is one of `upkeep` · `draw_step` · `begin_combat` · `end_step`, checked at
load time like every other piece of vocabulary: a misspelled step would schedule
something that never comes due.

Two things are worth knowing before writing one:

- **Bindings are captured when it is scheduled**, not when it fires. That is the
  point — by the time it fires, the object it was about may be in another zone.
  `{"binding": "how_many"}` inside the scheduled effects reads the value the
  scheduling effect had.
- **It waits for the step's *next* occurrence.** `begin_step` for the current
  step has already run by the time any effect resolves, so scheduling `upkeep`
  during an upkeep means the following turn's, which is what the cards say.

The scheduled effects resolve directly rather than going on the stack. That is a
divergence — a delayed trigger is a real triggered ability and should be
respondable — recorded with the other simplifications in
[rules-coverage.md](rules-coverage.md).

## "Choose a creature type"

Vanquisher's Banner, which asks the question twice — once as a static filter and
once as a trigger filter:

```jsonc
// As this artifact enters, choose a creature type.
{ "kind": "triggered", "trigger": { "event": "self_enters", "source": "self" },
  "effects": [ { "op": "choose_type", "prompt": "Choose a creature type" } ] },

// Creatures you control of the chosen type get +1/+1.
{ "kind": "static", "effect": "buff",
  "affects": { "controller": "you", "types": ["Creature"],
               "subtypes": [ { "chosen_type_of": "self" } ] },
  "power": { "const": 1 }, "toughness": { "const": 1 } },

// Whenever you cast a creature spell of the chosen type, draw a card.
{ "kind": "triggered",
  "trigger": { "event": "spell_cast", "controller": "you",
               "filter": { "types": ["Creature"],
                           "subtypes": [ { "chosen_type_of": "self" } ] } },
  "effects": [ … ] }
```

`{"chosen_type_of": "self"}` may stand anywhere a literal subtype name does, and
is substituted wherever the filter is matched rather than at load time — the
choice does not exist until the permanent is on the battlefield.

**Before a type is chosen the filter matches nothing**, which is the important
half: falling back to "match everything" would make the Banner a global anthem
for as long as the choice was pending.

`choose_type` needs **no new `DecisionKind`**. `ask_mode` already asks "pick one
of these labels" and returns the index, so legality, `game.apply` and the
authoring verifier's auto-answer table all work unchanged. Reach for an existing
`ask_*` before adding a kind; this is the same lesson `two_piles` teaches.

The prompt offers every creature subtype the **card pool** contains, sorted. The
rules say any creature type; a type no card in the game has is a choice with no
consequence, and the full Comprehensive Rules list would make the prompt
unusable without making any card play differently.

*Divergence*: the printed line is "**as** this artifact enters", a replacement
that cannot be responded to. `zones._enter_battlefield` applies enter-
replacements synchronously and cannot stop to ask, so this is a `self_enters`
trigger and the choice happens a moment after the permanent arrives.
[Recorded in rules-coverage.md](rules-coverage.md).

## Embalm — an ability activated from the graveyard

```jsonc
{ "kind": "activated",
  "text": "Embalm {5}{W} (…)",
  "active_zones": ["graveyard"],
  "sorcery_speed_only": true,
  "cost": { "mana": "{5}{W}",
            "exile_from_graveyard": { "self_only": true, "count": 1 } },
  "effects": [
    { "op": "copy_permanent",
      "objects": { "zone": "exile", "controller": "any", "self_only": true },
      "controller": "you",
      "except_": { "colors": ["W"], "add_subtypes": ["Zombie"],
                   "no_mana_cost": true } } ] }
```

Cycling paid for most of the zone half; the graveyard joins the hand in
`legality._activate_zones`. The safety rule is the same one and now has two ways
to be satisfied: an activated ability offered outside the battlefield **must**
have a cost that removes its source from that zone. Cycling discards itself,
embalm exiles itself. Without it the ability is an infinite engine.

Note the effect's selector says `"zone": "exile"`: the cost has already exiled
the card by the time the ability resolves, and an oid survives the move.

### `except_` — a copy that is not quite a copy

A token copy is a token whose `def_id` is the original's, which is right — a
copy copies the printed card, not the counters and damage on it — but it leaves
the printed "except" clause nowhere to live, because the token has no card of
its own. So the exception rides on the **object**, as `copy_overrides`:

| key | meaning |
|---|---|
| `colors` | replaces the printed colours outright |
| `add_subtypes` | *adds* to the printed subtypes — an embalm token is a Zombie **Angel** |
| `no_mana_cost` | mana value reads 0 rather than the printed card's |

Applied to the printed face *before* any layer, because the exception is part of
what the token is rather than an effect on it — so an anthem afterwards layers
on top exactly as it would on a real card. The loader rejects unknown keys: a
misspelled one dropped silently gives a plain copy, which looks identical until
somebody reads its colour.

## "…dealt damage by this creature this turn"

Sengir Vampire. A trigger filter, because the clause is a *relationship* between
two objects over a span of time rather than a characteristic of either:

```jsonc
{ "kind": "triggered",
  "text": "Whenever a creature dealt damage by this creature this turn dies, …",
  "trigger": { "event": "creature_dies", "controller": "any",
               "filter": { "controller": "any", "damaged_by": "self" } },
  "effects": [ … ] }
```

Answered from a per-turn ledger on the state — victim oid → who has damaged it —
written by `damage_permanent` and cleared during cleanup alongside rule 514.2's
"remove all damage from permanents". A ledger that outlived the turn would let
Sengir grow off a creature it hurt yesterday.

**It is on the state rather than on the damaged creature**, and that is forced:
the question is asked *about a creature that has just died*, and anything stored
on the victim is wiped by `reset_permanent_state` on the way to the graveyard —
the exact moment the trigger needs it.

Two traps, both of which produce a card that loads and looks implemented:

- **`controller: "any"` on the trigger.** `TriggerModel.controller` defaults to
  `"you"`, so an unqualified `creature_dies` only sees *your own* creatures
  dying. Sengir's victims are usually an opponent's, so the default silently
  makes the ability never fire.
- Bare `creature_dies` without the filter fires on **every** creature death
  anywhere, which is a strictly stronger card and looks right in most games
  where Sengir is doing the killing.

## "Exile it until this permanent leaves the battlefield"

Oblivion Ring, and the whole Banishing Light / Fiend Hunter family. Two
abilities, and a link between them:

```jsonc
// When this enchantment enters, exile another target nonland permanent.
{ "op": "exile", "objects": { "target": "t1" }, "until_leaves": true }

// When this enchantment leaves the battlefield, return the exiled card
// to the battlefield under its owner's control.
{ "op": "put_onto_battlefield",
  "objects": { "zone": "exile", "controller": "any", "exiled_with": "self" },
  "controller": "owner" }
```

`snapshot` is the documented answer to last-known information and cannot do
this: it writes into `EffectContext.bindings`, which lives for exactly one
resolution, and these are two separate abilities with two separate contexts.

**The link lives on the exiled card, not on the exiler.** That is the whole
trick, because the exiler is the thing that goes away — the Ring is in a
graveyard by the time the return happens, while its victim is sitting in exile
untouched. And an oid survives every zone change here, so a leaves-trigger's
`source_oid` still names the departed permanent and `exiled_with: "self"` is
just a comparison.

Two details that bite:

- `controller: "any"` is required. An exiled card keeps its last controller,
  which for O-Ring's victim is an opponent, and the selector language defaults
  `controller` to `"you"`.
- A plain `{"zone": "exile"}` would match every card in exile from every source,
  so the return would hand back cards this permanent never touched — a
  different card, and a better one.

The link is written *after* the move (`move_object` runs
`reset_permanent_state` on the way, which would wipe it) and cleared by that
same reset when the card returns, which is right: it is spent once followed.

## Token copies

```jsonc
{ "op": "copy_permanent", "objects": { "target": "t1" } }
{ "op": "copy_permanent", "objects": { "self_only": true } }   // Scute Swarm
```

The object model already *is* a copy model: identity is `def_id` pointing at a
`CardDef`, and `is_token` is a separate flag — so a token copy is a token whose
`def_id` is the original's. That is not a shortcut. A copy copies the **printed
card**, so the counters, damage and Auras piled onto the original are exactly
what must not come with it.

Unlike `create_token` it names no token id, so nothing has to be pre-declared and
`validate_token_references` does not apply: what is being copied is only known
while the spell resolves.

## Keyword actions that are only a token

Some printed keywords add no vocabulary at all. **Investigate** is the clearest
case: the reminder text on Bygone Bishop *(Create a Clue token. It's an artifact
with "{2}, Sacrifice this token: Draw a card.")* is the entire specification, so
it is spelled with the ops that already exist —

```jsonc
{ "op": "create_token", "token": "clue_token", "amount": { "const": 1 } }
```

— and the work is adding `clue_token` to `data/cards/tokens.cards.json`. Reach
for this shape before writing an op. A keyword action that names a token, and
whose token's text is all cost-and-effect the DSL can already say, is a data
change.

The catch is what the token's ability *costs*. A Clue pays for itself by
sacrificing itself, and a token that leaves the battlefield does not go to a
graveyard — it **ceases to exist**, as a state-based action, and is dropped from
`state.objects` outright. So by the time the ability resolves its source is not
merely somewhere else, it is gone. `stack.ability_of` looks the ability up
through the source object and now falls back to the stack item's `def_id` when
there is no object left; without that fallback every `"Sacrifice this token:
…"` ability resolves as a silent no-op, which is precisely the failure a token
with an approximated cost will never reveal.

If you add a token whose ability sacrifices it, assert that the effect actually
happened — not just that the token went away.

## Which mechanism a printed keyword lands on

The next several sections each answer one instance of a single question: a
keyword takes no parameter and a rule reads it, so it is a `Keyword`; it takes a
parameter, so it is a static; it must read *derived* characteristics, so it
cannot be a static filter at all. The rule those instances share, and a census
of every Magic keyword routed through it, is [keywords.md](keywords.md).

Read it before adding a keyword. The sections below are the worked examples —
they say why *this* card is shaped the way it is, which is what the residual
gate needs, but they were each discovered separately and none of them
generalises on its own.

## Landwalk, and global attack prohibitions

    Stormtide Leviathan — "Islandwalk. All lands are Islands in addition to
    their other types. Creatures without flying or islandwalk can't attack."

The three lines only work together, and each needed something different.

**Landwalk** is an ordinary `keywords` entry — `plainswalk`, `islandwalk`,
`swampwalk`, `mountainwalk`, `forestwalk`. Five keywords rather than one
parameterised ability because `Keyword` is a bare string and the whole content
of the quality is *which* land type. It is the first evasion whose condition is
neither creature's: `can_block` asks what the **defending player's board**
contains, reading `chars` rather than the printed card so line two above is
visible to line one.

**`cant_attack`** is a static read by `combat.can_attack`:

```jsonc
{ "kind": "static", "effect": "cant_attack",
  "affects": { "controller": "any", "types": ["Creature"],
               "not_keywords": ["flying", "islandwalk"] } }
```

It is the one static whose filter routinely names creatures its own controller
does not control, so `controller: "any"` is explicit — that clause is the whole
difference between a lock on the table and a drawback on yourself.

`not_keywords` existed in the effect-side selector language and not in the
static one until this card needed it. And it is why landwalk had to be a real
keyword rather than another static: a static cannot be *filtered on*.

## Attack requirements

    Trench Behemoth — "Landfall — Whenever a land you control enters, target
    creature an opponent controls attacks during its controller's next combat
    phase if able."

```jsonc
{ "op": "must_attack", "objects": { "target": "t1" }, "duration": "next_combat" }
```

The first thing on a card that removes an *option* rather than an ability.
Everything else that touches combat is a prohibition — `tap`, `freeze`,
`skip_untap`, `defender`, protection — and a requirement cannot be written as
the negation of any of them.

Enforced by withholding **Done attacking** while an able creature that must
attack is not attacking, because there is no action for "refuse to attack" for
legality to remove. That is safe precisely because "if able" is honoured: a
tapped, summoning-sick or `defender` creature owes nothing, so the declaration
can never deadlock.

Two durations, and picking the wrong one silently misses the combat it names:

| | |
|---|---|
| `this_turn` | Bident of Thassa — the combat in the turn it was used, and nothing later |
| `next_combat` | Trench Behemoth — that creature's **controller's** next combat, which for an opponent's creature is a later turn |

`next_combat` is why this is not a `TempEffect`: the trigger fires on *your*
landfall and binds *their* combat, and the cleanup step would wipe an
until-end-of-turn effect long before it arrived. It is one-shot, discharged at
its controller's declare-attackers whether or not it was met — an obligation the
creature could not meet is still spent, or it would compel the following combat
too.

### The continuous form

"This creature attacks each combat if able" is the same obligation and a
*different mechanism*: it is true again next turn, true for a creature that
entered after any op would have resolved, and false the moment its source leaves.
A one-shot flag cannot say that, so it is a static:

```jsonc
// Marauding Maulhorn — "…unless you control a creature named
//                       Advocate of the Beast."
{ "kind": "static", "effect": "attacks_if_able",
  "affects": { "self_only": true },
  "condition": { "not": { "exists": { "controller": "you",
                                      "types": ["Creature"],
                                      "name": "Advocate of the Beast" } } } }
```

One effect covers every printed variant, because they differ only in `affects`:
`{"self_only": true}` for "This creature…", `{"controller": "opponent", "types":
["Creature"]}` for the goad-shaped "Creatures your opponents control…", and
`{"attached": true}` for "Enchanted creature…". Like `cant_attack` — its exact
mirror image — that filter routinely names creatures the source's controller
does not control.

Both forms meet at one enforcement point, `combat.attack_required`, so there is
still only one place that decides whether "Done attacking" is offered. A goad
is owed only on the compelled creature's **own** turn: a creature cannot attack
on somebody else's, so "if able" excuses it, and without that the goading
player could never finish a declaration while an opponent held an untapped
creature.

`name` is readable in a static's **condition** — inside `exists` or `count` —
but deliberately not in `affects`. "Unless you control a creature named X" is a
question about the board; "each creature named X gets +1/+1" is not a card.

## Block restrictions

"This creature can't be blocked by …" is a static, not a keyword, because the
quality it names is a parameter:

```jsonc
// Stromkirk Noble: can't be blocked by Humans
{ "kind": "static", "effect": "block_restriction", "affects": { "self_only": true },
  "blockers": { "subtypes": ["Human"] } }

// Tromokratis: can't be blocked unless all creatures defending player controls block it
{ "kind": "static", "effect": "block_restriction", "affects": { "self_only": true },
  "require_all": true }
```

The two forms are evaluated at different moments and neither is the other with a
parameter. `blockers` is a **per-pair** question — is *this* creature allowed to
block? — and is asked in `combat.can_block`, beside flying and protection.
`require_all` cannot be answered per pair at all, because whether one block is
legal depends on what every other creature is doing, so it is asked in
`combat.blocks_valid`, which is the shape menace already needed.

`blockers` is a static filter and may read printed characteristics only, with
one difference from every other static filter: `controller` defaults to **any**
rather than `you`. A blocker belongs to the defending player by definition, so
the usual default would match nothing and the restriction would silently never
fire.

`require_all` is literal about "controls": a *tapped* creature that cannot block
still makes the block illegal, which is why Tromokratis is close to unblockable
and is the entire point of the card.

A `block_restriction` carrying neither field is refused at load time — an
evasion ability that evades nothing, which would load perfectly cleanly.

### Skulk

    Vampire Cutthroat — "Skulk (This creature can't be blocked by creatures with
    greater power.)"

An ordinary `keywords` entry — `"keywords": ["skulk", "lifelink"]` — not a third
`block_restriction` form, and the reason is the same one that made landwalk a
keyword: it takes no parameter, because the whole content of the quality *is*
the comparison.

It also could not have been a `blockers` filter even given a `power` key.
`blockers` is a static filter and static filters read **printed**
characteristics, which is what keeps the characteristics pipeline acyclic; skulk
must read *derived* power on both sides, so an anthem, a pump spell or a +1/+1
counter on either creature changes who may block. The comparison therefore sits
in `combat.can_block` beside landwalk, which reads `chars` for the same reason.

"Greater" is strictly greater: an equal-power creature blocks a skulker.

### Fear, intimidate, horsemanship, shadow and nonbasic landwalk

    Shriekmaw — "Fear."
    Guul Draz Vampire — "…has intimidate."
    Lu Bu, Master-at-Arms — "Horsemanship."
    Dauthi Voidwalker — "Shadow."
    Dryad Sophisticate — "Nonbasic landwalk."

Ordinary `keywords` entries, all five, and nothing else on the card:

```jsonc
"keywords": ["fear"]
"keywords": ["shadow"]
"keywords": ["nonbasic_landwalk"]
```

They are keywords for skulk's reason — the quality takes no parameter, because
"artifact and/or black" *is* fear rather than an argument to it — and they could
not have been `block_restriction`s for **two** independent reasons, either of
which is sufficient:

- A `blockers` filter is a **prohibition** and four of these are **exemptions**.
  "Can't be blocked by Humans" is a positive conjunction the filter language can
  state; "can't be blocked *except* by artifact creatures and/or black
  creatures" is its negation, and adding a `not_colors` key would not get there.
- A `blockers` filter reads **printed** characteristics. Fear and intimidate ask
  about derived colors and types, so a land animated into a black creature may
  block a fear creature and its printed card is not consulted.

Three of them are worth stating individually, because each is a distinct shape:

| | |
|---|---|
| `intimidate` | Compares the two creatures — skulk's shape, on colors. A **colorless** creature with intimidate shares a color with nothing, so only an artifact creature may block it; that is the boundary, and reading the clause as "is not a different color" would silently invert it |
| `shadow` | The only evasion that is not an attacker-side rule. 702.28b is "can block **or** be blocked by only creatures with shadow", so `can_block` asks whether the two creatures *agree*, and a shadow creature may not block a normal one either |
| `nonbasic_landwalk` | Landwalk with the test inverted — a **supertype the land must lack**, not a subtype it must have. That is why it is a sixth keyword and not a sixth `LANDWALK_SUBTYPE` row, and why "defending player controls eight Forests" is the case that separates it from "controls a land" |

`horsemanship` is the plain one: the blocker must carry the same keyword. It is
one-directional, unlike shadow — a creature with horsemanship may block
anything.

## Protection

Parameterised, so it is a static rather than a `Keyword`:

```jsonc
{ "kind": "static", "effect": "protection", "affects": { "self_only": true },
  "from_types": ["Planeswalker"], "from_subtypes": ["Wizard"], "from_colors": ["B"] }
```

Four separate rules read it — **D**amage, **E**nchant/equip, **B**lock,
**T**arget — and a card that implements one of the four looks identical to one
that implements all four until the moment it matters.

Protection is not hexproof with a filter: hexproof stops *opponents*, protection
stops **everyone**, including the controller. Reusing the hexproof check would
let you target your own protected creature.

A `protection` static that names no quality is rejected at load time; it would
load, look implemented, and protect from nothing.

### Shroud, which is the third member of that family

`shroud` is an ordinary entry in `keywords`, so a card that prints it needs
nothing else:

```jsonc
"keywords": ["flying", "trample", "shroud"]
```

It shares protection's "everyone, including the controller" half and hexproof's
"target legality only" half, and it is the only one of the three that is exactly
one rule. `targeting.can_be_targeted` is the sole reader.

|  | stops the controller | rules that read it |
|---|---|---|
| hexproof | no | target |
| **shroud** | **yes** | **target** |
| protection | yes | damage, enchant/equip, block, target |

Both neighbours are wrong in a way that is invisible on screen. Written as
`hexproof`, Simic Sky Swallower is a strictly *better* card — its controller can
still pump, blink or equip it. Written as `protection`, it also stops taking
damage and stops being blocked, and the loader will not accept "from everything"
in any case.

Granting it needs no extra work: `grant_keyword`, as an op or as a static,
already carries the whole "equipped creature has shroud" family, because the
check reads the characteristic layer rather than the printed card.

## Granting an ability

The quoted half of `gains trample and "Whenever this creature deals combat damage
to a player, draw a card"`. The granted ability is written on the granting card
under `grantable_abilities` and referred to by index, so there is one definition
of it rather than a copy:

```jsonc
"grantable_abilities": [
  { "kind": "triggered", "trigger": { "event": "deals_combat_damage_to_player",
                                      "source": "self" },
    "effects": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ] }
],
"effects": [ { "op": "grant_ability", "ability": 0, "objects": { "target": "t1" } } ]
```

It becomes the **recipient's** ability: "whenever *this creature* deals combat
damage" means the creature, not the artifact that lent it. Until end of turn.

Only **triggered** abilities may be granted, and the loader says so rather than
accepting the others silently. A granted static has no place in the fixed-order
characteristics pipeline, and a granted activated ability would need `Action` to
carry where it came from before legality could offer it — so it would compile and
then never appear.

## Two piles

```jsonc
{ "op": "two_piles", "amount": { "const": 5 }, "to": "hand", "other": "graveyard" }
```

Fact or Fiction, and the only effect in the pool whose first decision belongs to
**somebody else**. That tension is the card: the splitter wants both piles to be
bad and the caster takes the better one, so an implementation where the caster
splits is a strictly better spell than the one printed.

Two decisions — a subset chosen by an opponent, then a yes/no from the caster —
rather than "choose a pile", because the piles are not objects until the split is
made.

## Cycling

The first ability the engine offers from a zone that is not the battlefield:

```jsonc
{ "kind": "activated",
  "text": "Cycling {2} ({2}, Discard this card: Draw a card.)",
  "active_zones": ["hand"],
  "cost": { "mana": "{2}", "discard_self": true },
  "effects": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ] }
```

Two halves, and neither works without the other.

**`active_zones` on an activated ability.** The field always existed and was
read only on the *triggered* branch, so `_compile_ability` pinned every
activated ability to the battlefield and silently dropped the schema's own
`"hand"`. `legality._activate_actions` walks your hand as well now — **yours
only**, because the hand is hidden and offering from an opponent's would leak
its contents into `legal_actions`.

**`discard_self` on the cost.** Not `discard: 1`: that offers the whole hand and
`ask_objects` lets the player pick, so a Krosan Tusker could be "cycled" by
pitching a spare land and staying in hand — a strictly better card than the one
printed. `discard_self` names *this* card and asks nothing.

The pairing is also the safety property, and the loader enforces it: an
activated ability whose `active_zones` reach outside the battlefield **must**
have a cost that removes its source from that zone. Without that it is an
infinite engine — a card in hand whose ability costs only mana could be
activated forever without ever leaving.

Only plain cycling. Typecycling (`Landcycling {1}{G}`) fetches instead of
drawing and is a different ability, so it fails the template rather than being
turned into a plain cycler.

### "When you cycle this card…"

```jsonc
// Krosan Tusker — the two abilities together.
{ "kind": "activated", "text": "Cycling {2}{G} (…)",
  "active_zones": ["hand"], "is_cycling": true,
  "cost": { "mana": "{2}{G}", "discard_self": true },
  "effects": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ] },

{ "kind": "triggered",
  "text": "When you cycle this card, you may search your library …",
  "active_zones": ["graveyard"],
  "trigger": { "event": "cycle", "source": "self" },
  "effects": [ … ] }
```

**`is_cycling` is declared, not inferred.** "Discard this card:" is a shape
other cards print without being cycling, and a trigger firing on those would be
a different card. The loader refuses `is_cycling` on a cost that does not
discard the card.

**`active_zones: ["graveyard"]` on the trigger**, because paying the cycling
cost discards the card — by the time the event fires, its source is already in
the graveyard, which `_candidate_abilities` already walks.

**The ordering is free, and it is the card.** The event fires *after* the
cycling ability is on the stack, so the trigger drains on top of it and resolves
first. That is the whole of the printed "(Do this before you draw.)", out of the
stack's ordinary last-on-first-off behaviour rather than a special case.

`draw` and `discard` both exist and neither can stand in: `draw` fires on every
draw including the draw step, and *after* the draw, which the parenthetical
forbids; `discard` fires on hand-size discards and every discard cost, so a
Tusker pitched to a Wheel would fetch. The event is fired with `triggers.fire`,
not `state.emit` — `emit` only writes the log.

## Alternative ways to play a card

Each a card-level field rather than an ability, because the card does not have
them where it is sitting:

```jsonc
"kicker": "{1}{U}"                          // pay more as you cast it
"evoke": "{2}{U}"                           // pay less instead, and it dies on arrival
"emerge": "{5}{U}{U}"                       // pay less by eating a creature
"retrace": true                             // cast from the graveyard, discarding a land
"flashback": { "mana": "{1}{U}", "pay_life": 3 }  // cast from the graveyard, then exile
"suspend": { "cost": "{G}", "counters": 2 } // exile it now, cast it free later
```

### Ascend

```jsonc
"ascend": true                              // a card-level flag, not a keyword
```

```jsonc
// "This creature has flying as long as you have the city's blessing."
{ "kind": "static", "effect": "grant_keyword",
  "affects": { "self_only": true }, "keywords": ["flying"],
  "condition": { "has_city_s_blessing": "you" } }
```

The blessing is granted by a **state trigger** in the state-based-action pass
(rule 702.131a), not by a triggered ability. Ascend is not an *event*: a player
at nine permanents who plays a land gets it at the instant of the tenth, with
nothing having fired, and gets it on an opponent's turn just as readily. State
triggers use no stack and cannot be responded to, so the SBA pass — beside the
legend rule — is where they belong.

**Player state, not object state.** `PlayerState.has_city_s_blessing` is one-way
and lasts the rest of the game: it survives the permanents leaving, survives the
Ascend card leaving, and is shared by every card that player controls, so a
second Ascend card printed later reads the blessing a first one granted.
`monstrous` is the closest existing one-way flag and cannot be reused — it lives
on a `GameObject`, so `reset_permanent_state` clears it on any zone change.

**Not a `Keyword`.** The enum's members are read off *derived characteristics*
by `grant_keyword` and the evasion checks, and Ascend is neither granted nor
evasive.

`has_city_s_blessing` reads in both condition languages — a static's `condition`
and the `if`-effect one. It is safe in a static for the same reason a zone count
is: player state is a pipeline **input**, and nothing in the fixed-order
characteristics pipeline can change it.

### Flashback

A whole `Cost`, not a mana string like `evoke`, because Deep Analysis charges
life as well. The **mana half replaces** the printed cost; everything else is an
additional cost paid after it, in the order rule 601.2g gives — the same
two-step `retrace` already uses.

`retrace` cannot stand in even though it is the other graveyard-casting field:
its cost is hardcoded to a discarded land and charged *in addition* to the
printed one, so it can name no alternative price, and it deliberately returns
the card to the graveyard to be used again. A card may not have both.

Two riders come with it, and the second does not fall out of the first:

**"Then exile it."** A spell cast this way goes to exile rather than the
graveyard when it resolves *or* fizzles. Without that it could be flashed back
forever.

**`cast_from_graveyard`**, a condition readable inside `if`:

```jsonc
// Increasing Devotion — "…create ten of those tokens instead."
{ "op": "if", "condition": { "cast_from_graveyard": true },
  "then": [ { "op": "create_token", "token": "human_1_1_w",
              "amount": { "const": 10 } } ],
  "else": [ { "op": "create_token", "token": "human_1_1_w",
              "amount": { "const": 5 } } ] }
```

An engine could implement flashback casting perfectly and this card would still
be wrong. `zone_is` cannot answer it: it reports the source's *current* zone,
which for any resolving sorcery is the stack, identically either way. So it is a
flag on the object following the `cast_x` / `cast_kicked` / `cast_evoked`
precedent — and written **before** `spell_effects` run, because that is when it
is read. The loader refuses the condition on a card with no flashback cost,
since it could never be true.

**Evoke** is `kicker` pointing the other way: an *alternative* cost that
replaces the printed one rather than adding to it, offered only from hand, and
listed as a third cast variant beside the full-price line. Neither is folded
into `mana_cost`, for the same reason — mana value stays what is printed, so an
evoked Mulldrifter is still a five-drop to everything that counts one.

Its two halves are checked together like kicker's, and half of it fails the same
silent way: an evoke cost nothing reads is a cheaper cast that never dies, and an
`{"evoked": true}` clause with no cost can never fire. Both load cleanly, so both
are load errors. An evoke cost that is not actually cheaper is refused too — an
alternative nobody would take is dead weight that reads as a mechanic.

"It's sacrificed when it enters" is an ordinary `self_enters` trigger gated on
`{"evoked": true}`, which works because the flag is written onto the object at
resolution and outlives the spell — see the note under Kicker.

**Emerge** is the third alternative cost and the only one whose price is not
fixed: it is reduced by the mana value of the creature sacrificed, so legality
offers **one line per sacrificeable creature** rather than one line with a flag.
The list is capped, because each line multiplies by every legal target tuple —
the same swamping `MAX_TARGET_OPTIONS` exists to stop — and the biggest mana
values come first, since those are the lines a player is looking for.

The mana is paid before the sacrifice (rule 601.2g), so a creature that taps for
mana can help pay for the spell that is about to eat it. A card may not carry
both `evoke` and `emerge`: no printing does, and legality would have to decide
which replaces which.

### "When you cast this spell…"

An ability that fires while its own card *is* the spell, so it is never on the
battlefield when it matters:

```jsonc
{ "kind": "triggered", "active_zones": ["stack"],
  "trigger": { "event": "spell_cast", "source": "self", "controller": "you" },
  "effects": [ ... ] }
```

`_candidate_abilities` scanned the battlefield, the command zone, the graveyard,
the hand and exile — every zone except the one place this card lives at the
moment it speaks. The stack is scanned separately rather than added to that loop,
because it is not a player zone: it is shared, ordered, and holds the spell under
its own trigger.

**Emerge** is `evoke` with a price that is not fixed: it replaces the printed
cost *and* is reduced by the mana value of a creature you sacrifice. Because the
creature decides the number, legality offers **one line per sacrificeable
creature** rather than one line with a flag, capped at four so a wide board does
not swamp the action list. The sacrifice is taken after the mana (rule 601.2g),
so a creature that taps for mana can help pay for the spell that eats it. A card
may not carry both `evoke` and `emerge`; no printing does, and legality would
have to decide which replaces which.

`"When you cast this spell, …"` is an ordinary triggered ability with
`"active_zones": ["stack"]` and a `spell_cast` trigger sourced to `self`. The
stack is scanned for triggers now — it is the one zone a card is in at the
moment that line speaks, and `_candidate_abilities` had covered every other one.
What keeps ordinary abilities out of it is `active_zones`, which still defaults
to the battlefield.

**Retrace** widens *where* a card may be cast from, the same way
`play_lands_from_graveyard` widens where a land may be played from — legality
scans the graveyard alongside the hand. The additional cost reuses
`Cost.discard_selector`, which already existed for "discard a land card".

**Suspend** is the odd one, and gets its own module
([`engine/suspend.py`](../src/automtg/engine/suspend.py)) for three reasons:

- *Suspending is not casting.* Nothing goes on the stack and nobody gets
  priority, so it is `ActionKind.SUSPEND` rather than a variant of `CAST` — and
  therefore cannot be countered.
- *The ticking is a rule, not an ability.* A suspended card sits in exile with no
  abilities of its own, so removing a time counter each upkeep belongs to the
  game the way the untap step does. It is called from `turn.py`.
- *The free cast is still a cast.* It uses the stack, it can be countered, and
  its targets are chosen then — it simply costs nothing.

A creature cast off suspend has haste, recorded on the object rather than in
`until_eot`: it lasts as long as the permanent does, and it is the only reason
suspend is ever better than waiting.

## "This spell can't be countered"

A flag on the card, not an ability:

```jsonc
{ "id": "koma_cosmos_serpent", "uncounterable": true, ... }
```

It has to be, because a spell is on the stack and static abilities do not reach
it there. The `counter` op checks it and emits a `spell_countered` event carrying
`failed: "cannot be countered"`, so the log says what happened rather than the
spell silently surviving.
