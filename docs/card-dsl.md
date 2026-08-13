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
    ctx --> ops["op registry<br/>73 ops"]
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

73 of them. Each takes a spec dict; the common fields are `objects` (a selector),
`player` (a player spec) and `amount` (a value expression).

| Group | Ops |
|---|---|
| Cards | `draw` `discard` `mill` `search_library` `search_zones` `look_at_top` `look_at_hand` `return_to_hand` `return_from_graveyard` `reveal` `scry` `surveil` `shuffle` `put_on_top` `two_piles` `explore` `connive` `clash` `cascade` `ripple` |

`scry` takes `player` (whose library) and `chooser` (who decides) separately.
They are the same person for scry and different people for **fateseal** —
`{"op": "scry", "player": {"target": "t1"}, "chooser": "you"}` — and that is
the entire difference between the two keywords. Omitting `chooser` asks the
library's owner, which is what every scry card in the pool wants.
`look_at_hand` is the one op that moves **private** information:

```jsonc
{ "op": "look_at_hand", "player": { "target": "t1" } }
```

"Look at target player's hand" (Glasses of Urza). `reveal` cannot stand in — it
emits a public event, so at a pod it would tell the victim's *other* opponents
everything too, which is a different card. The seats entitled to see a card are
recorded on it as `GameObject.revealed_to`, and `player_view` sends those cards
to that seat alone under `hand_revealed`; every other seat still sees
`hand: null` and a count. It is written on the card rather than emitted because
the view is rebuilt on every request and has to answer "may this seat see this?"
long after the ability resolved. The entitlement is cleared by
`reset_permanent_state`, so a card that leaves and returns is hidden again.

`search_zones` searches more than one of your own zones as a **single** pool:

```jsonc
{ "op": "search_zones", "zones": ["library", "graveyard"], "count": 1,
  "destination": "battlefield",
  "selector": { "types": ["Creature"],
                "mana_value": { "op": "<=", "value": { "x": true } } } }
```

That is Finale of Devastation's "search your library **and/or** graveyard for a
creature card". A `search_library` followed by a `return_from_graveyard` is a
different card: each carries its own count, so it would fetch up to *two*
creatures. The count here is over the union, which is what "and/or" means — you
look through both and take one. `choose_mode` is the near miss: it gets the
count right, but a mode is chosen blind and locks out the other zone.

`zones` needs at least two of `library`, `graveyard`, `hand`, `exile` — one zone
is `search_library` spelled the long way. A `zone` in the `selector` is refused,
because each half is matched in the zone it actually came from and a `zone`
written there would be overridden rather than honoured. `search_library` is now
this op with `zones: ["library"]`, so the two cannot drift apart.

The shuffle is **not** conditional. Finale prints "If you search your library
this way, shuffle", and that `if` exists because a player may announce they are
searching only the graveyard; this op always offers both zones, so it has always
searched the library and always shuffles. See
[rules-coverage.md](rules-coverage.md).

`look_at_top` is `search_library` with the pool bounded to the top `amount`
cards, and the bound is the card:

```jsonc
{ "op": "look_at_top", "amount": { "const": 20 },
  "objects": { "types": ["Land"], "count": "any" },
  "destination": "battlefield", "tapped": true, "shuffle": true }
```

That is Through the Forest Gate. Written as a `search_library` it would find
every land in the deck rather than whatever the top twenty happened to hold,
which is a different and much better card. Two things follow from *look* rather
than *search*: nothing shuffles unless the card says `"shuffle": true` (701.19c's
mandatory shuffle belongs to searching a hidden zone, and the cards you declined
stay on top in order), and the count is the ordinary selector `count` on
`objects`, because `pick_from_pool` is shared with `choose_objects`. `amount` is
required — defaulted it would look at one card and say nothing about it.

| Board | `destroy` `exile` `sacrifice` `put_onto_battlefield` `create_token` `add_counters` `remove_counters` `tap` `untap` `attach` `unattach` `lock_abilities` `monstrosity` `freeze` `copy_permanent` `grant_ability` `skip_untap` `must_attack` `must_block` `move_counters` `set_flag` `proliferate` `detain` `gain_control` `haunt` `pair` `aura_swap` |
| Modify | `pump` `grant_keyword` `set_pt` `animate` `add_subtype` `transform` |
| Life & damage | `gain_life` `lose_life` `damage` `add_poison` |
| Mana | `add_mana` `add_mana_per` `extra_land_drop` |
| Stack | `counter` `copy_spell` |
| Control flow | `if` `for_each` `may` `choose_mode` `repeat` `snapshot` `noop` `delay` `join_forces` |

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
  "blocked": false,               // ninjutsu -- is anything blocking *this attacker*
  "is_commander": false, "is_token": false, "damaged": true,
  "power":      { "op": ">=", "value": { "const": 3 } },
  "toughness":  { "op": "<=", "value": { "const": 2 } },
  "mana_value": { "op": "<=", "value": { "const": 3 } },
  "exclude_self": true,           // "other ... you control"
  "exclude_binding": "subject",   // "each OTHER attacking creature"
  "shares_a_type_with": "subject",// "...that shares a creature type with it"
  "shares_a_color_with": "it",   // radiance -- "...that shares a color with it"
  "self_only": true,              // this permanent only
  "extreme": { "of": "toughness", "pick": "least" },  // "...with the least toughness"
  "count": 1,                     // an int, or "all", or "any" -- see below
  "chooser": "controller",        // controller|owner|none
  "random": false,
  "name": "Forest"
}
```

`extreme` is bolster's "a creature with the **least toughness** among creatures
you control", and it is the one clause that is not a test on a candidate. Every
other key here can be answered by looking at one object; an extremum is a fact
about the *pool*, so it is applied last, after everything else has filtered.
`of` is `power`, `toughness` or `mana_value` and is read off derived
characteristics; `pick` is `greatest` or `least`.

Ties are all kept. Rule 701.36a has the player choose among equals and
`choose_objects` is already what asks, so narrowing to one here would take that
choice away — and breaking the tie by oid would make the answer depend on the
order permanents happened to arrive in.

`count` has three spellings and they are three different cards. `"all"` takes
every match and asks nothing — mandatory. A **value expression** forces exactly
that many, because the one number becomes both the minimum and the maximum of
the question. `"any"` is the free subset: the chooser may take none of them, all
of them, or anything between.

```jsonc
{ "op": "put_onto_battlefield",
  "objects": { "zone": "hand", "controller": "you",
               "types": ["Creature"], "count": "any" } }
```

That is Last March of the Ents, and neither of the other two says it — `"all"`
empties your hand whether you wanted that or not, and any fixed number is
decided when the card is written rather than when it resolves. Nothing under the
decision layer needed building: `ask_objects` always took distinct `min_count`
and `max_count` bounds and `PendingDecision.min_count` was always honoured, so
`"any"` is only the spelling that reaches them.

`"any"` is refused at load time alongside `random` or `chooser: "none"`. Both
would resolve the whole pool without asking, which is `"all"` under another name;
a card that means "all" should say "all".

The comparison keys (`power`, `toughness`, `mana_value`) take a full **value
expression** on the right, which is how mentor says "target attacking creature
with lesser power" without any extremum at all:

```jsonc
"power": { "op": "<", "value": { "power_of": { "self": true } } }
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
| `shares_a_color_with` | the same clause on colours — radiance. `colors` cannot stand in for the same reason `subtypes` cannot: it takes a literal list, and which colour matters is decided by what was targeted |
| `exclude_binding` | drops the bound object from the pool |

`subtypes` cannot stand in for the first: it takes a literal list, fixed when
the card is written. Reaching for `{"count": {"attacking": true}}` instead
counts *every* attacker regardless of type, which is a different card that
loads and resolves without complaint.

`exclude_self` cannot stand in for the second, and this is the subtle one:
`exclude_self` compares against the **ability's source**, which for Shared
Animosity is the enchantment — not a creature, never attacking. It removes
nothing from a set of attackers, so every pump would be over by exactly one.

`shares_a_color_with` has one boundary of its own, and it is intimidate's
rather than landwalk's: a **colorless** object shares a colour with nothing,
itself included. So radiance cast on an artifact creature hits only the target,
and reading the clause as "is not a different colour" inverts exactly that case
while looking identical on a board of coloured creatures.

An unbound name matches **nothing** rather than everything. A trigger that did
not bind what the card thought it did is a bug, and the failure should be a card
that does nothing rather than one that pumps the whole board.

Two shorthands name a pool directly instead of searching a zone:

```jsonc
{ "target": "t1" }       // whatever was chosen for target spec t1
{ "binding": "subject" } // the object a trigger bound (the land that was played, ...)
{ "binding": "eaten" }   // …or the whole *set* an op recorded with `as`
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

### Recording what an op consumed — amplify and devour

```jsonc
// Amplify 2 — "…for each Beast card you reveal in your hand."
{ "op": "reveal", "as": "shown",
  "objects": { "zone": "hand", "controller": "you",
               "subtypes": ["Beast"], "count": "any" } },
{ "op": "add_counters", "counter": "+1/+1",
  "objects": { "zone": "battlefield", "self_only": true },
  "amount": { "times": [ { "const": 2 }, { "count": { "binding": "shown" } } ] } }

// Devour 2 — "…you may sacrifice any number of creatures."
{ "op": "sacrifice", "as": "eaten",
  "objects": { "zone": "battlefield", "controller": "you",
               "types": ["Creature"], "exclude_self": true, "count": "any" } }
```

Both keywords are "twice **that** many", and *that* is a set the player chose a
moment ago in this same resolution. Nothing can name it afterwards, and the two
fail differently — which is why one `as` covers both:

| | why it cannot be recovered |
|---|---|
| amplify | the revealed cards are back in a hand full of other Beasts; no filter tells them apart |
| devour | the eaten creatures are in a graveyard, and `creatures_died_this_turn` also counts combat and removal — a plausible number, and the wrong one |

`as` writes the chosen oids into the binding, and `{"binding": …}` now seeds a
**list** as readily as a single object. Every trigger binding before this held
exactly one, so nothing else changed.

`reveal` also goes through `choose_objects` now, which is what makes "reveal
**any number**" sayable at all: it used to resolve its pool and show the whole
hand without asking. `count` still defaults to `"all"`, so every reveal already
in the pool is unchanged.

*Divergence*: both keywords print "**as** this creature enters", a replacement.
They are `self_enters` triggers here, for the reason
["as this enters, choose a creature type"](rules-coverage.md) is one.

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
{ "creatures_died_this_turn": "all" }           // morbid; "you" for "a creature you controlled"
{ "attacked_this_turn": "you" }                 // raid; 1 if they attacked, else 0
{ "damage_taken_this_turn": "each_opponent" }   // bloodthirst
{ "life_lost_this_turn": "each_opponent" }      // spectacle; damage counts towards it
{ "spells_cast_this_turn": "all" }              // storm
{ "cards_to_graveyard_this_turn": true }        // gravestorm; every graveyard, so no spec
{ "resolutions_this_turn": "self" }             // …times THIS ability has resolved
{ "binding": "amount" }                         // a value the trigger carried
{ "counters_on": { "counter": "+1/+1", "objects": { "self_only": true } } }
{ "counters_had": "-1/-1" }                     // what a creature that just died had
{ "distinct": { "of": "basic_land_type",        // domain; "power" is coven
                "objects": { "controller": "you", "types": ["Land"] } } }
{ "mana_symbols": { "of": "G",                  // chroma -- pips, not colours
                    "objects": { "controller": "you" } } }
{ "colors_of_mana_spent": true }                // sunburst, converge
{ "sum": [a, b] } { "minus": [a, b] } { "times": [a, b] } { "max": [...] } { "min": [...] }
```

### Counting the mana that was actually spent

`{"colors_of_mana_spent": true}` is sunburst and converge, and it is the first
thing in the engine that reads how a spell was **paid for** rather than what it
costs. The answer used to be thrown away: `ManaPool.spend` decremented six
integers in place and returned nothing, so a moment later one blue mana was
indistinguishable from another.

Every near miss reads the cost, and the ordinary card separates them — a
Sunburst artifact costs `{5}` and has no coloured pip at all. `{"x": true}`
reads an X these cards do not have; `mana_symbols` reads printed pips, which is
zero here; a `count` over lands counts permanents rather than what they made.

Two details are the keyword rather than plumbing. **Mana spent on the generic
part counts** — that is the whole of sunburst. And the record survives the move
onto the battlefield, because the enters trigger is what reads it: it follows
`cast_x`'s contract rather than the battlefield state `reset_permanent_state`
wipes.

A **hybrid** pip reports the half actually paid, which is not what `colors` on
the cost says: that reports both, because both decide colour identity. Only one
of them was ever spent.

### Counting mana symbols

`{"mana_symbols": {"of": "G", "objects": …}}` is chroma, and it is the first
thing in the engine that looks **inside** a mana cost. Every other reader wants
the total (`mana_value`) or the set of colours (`colors`); this wants how many
times one symbol appears, so `{G}{G}{G}{G}` is four where `colors` says green
once.

A **hybrid** pip counts for each of its colours (rule 107.4f) — a Kitchen Finks
adds one to a green count and one to a white one. `ManaCost` stores `hybrid`
apart from `colored`, deliberately and for unrelated reasons, so this is the case
that would otherwise count for neither.

It reads the **printed** cost, which is what the keyword says and also what makes
it legal in a `set_pt` **static**: a printed cost is a pipeline input, so no
layer can change one. Primalcrux is a static, so the leaf lives in both value
languages — added to only one, the card would have loaded and read 0.

### Counting different values rather than objects

`{"distinct": …}` is domain and coven, and they are one leaf rather than two
because `count` fails them in **opposite** directions:

| | `count` says | the card means |
|---|---|---|
| five Forests, domain | 5 | 1 basic land type |
| three 2/2s, coven | 3 | 1 power |

No selector, however filtered, reaches either number — `count` counts matches,
and these count the distinct values those matches hold. `of` is `power` or
`basic_land_type`, and nothing else: both have a printed card behind them, and a
misspelling is a load error rather than a silent fall back to powers.

`objects` is required. An empty selector is every permanent in the game, so
domain would count an opponent's basics and coven their creatures — and both
would look plausible.

Coven is then an ordinary comparison and needs nothing else:

```jsonc
{ "cmp": ">=", "right": { "const": 3 },
  "left": { "distinct": { "of": "power",
                          "objects": { "controller": "you", "types": ["Creature"] } } } }
```

Both readings are of **derived** characteristics, which is why this leaf is in
the `if`-effect language and deliberately **not** in a static's `condition`. An
anthem changes who has coven and "all lands are Islands" changes what counts for
domain, so a static reading it would be switched on and off by another static's
output — the one dependency [layers-lite](adr/0001-layers-lite.md) forbids. The
static value whitelist already refuses it, and a test pins that it stays refused.

### Counting an event rather than the board

Most leaves above are a question about the position: how many Vampires, how many
counters, how much life. Seven are not, and they are the reason the engine keeps
per-turn state at all rather than adding another selector.

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

The other six live together in `GameState.turn_ledger` (`structs.TurnLedger`),
and every one is unanswerable from the board for the same kind of reason. A
creature in a graveyard may have been discarded or milled rather than having
died; a creature that died last turn is still lying in the same place. Nothing
whatsoever records that a player attacked once combat is over.

Two things about that ledger are load-bearing:

- **It is folded in `GameState.emit`, not counted at six primitives.** Each
  tally counts an event that is already being logged, and `emit` is the single
  function every event passes through, so a new way to kill a creature or deal
  damage is counted without anybody remembering to count it. No emitter needed
  changing, and the fold runs while the object is still in `state.objects`,
  which is how it can ask a dying creature who controlled it.
- **Damage to a player counts as life lost** (rule 118.2), as well as as damage.
  Spectacle is printed on cards you cast after hitting somebody with a burn
  spell, so a `life_lost_this_turn` that only saw `lose_life` would read false
  in exactly the case the mechanic exists for.

It clears at **cleanup**, with `damage_ledger` and unlike `cards_drawn_this_turn`
— nothing it counts can happen before turn 1, so it has no opening hand to
survive, and "a creature died this turn" has to stay true through the end step
that reads it.

`resolutions_this_turn` joined the ledger later and breaks both of those rules,
for reasons worth stating. Scythecat Cub's "if this is the second time this
ability has resolved this turn" is not a fact about a *seat*, so it is keyed by
`(object, ability index)` — two Cats count separately. And it is **not** folded
in `emit`: `ABILITY_RESOLVED` is emitted after the effects have run, which is one
resolution too late for the effect that has to read it, so `stack.resolve_top`
bumps it on the way in. That placement is past the fizzle and intervening-if
returns and before the effects, which is the only spot that counts a real
resolution, counts the one in progress, and counts neither of the two ways an
ability leaves the stack without resolving (608.2b, 603.4).

A flag cannot stand in for it. `set_flag` is one-way — there is no `clear_flag`
and nothing empties `obj.flags` at end of turn — so a mark written on the first
landfall would still be there next turn and would double the *third* resolution
as well as the second.

## Costs

What an activated ability charges, and what `may`'s `pay` spends:

```jsonc
{ "mana": "{1}{U}", "tap": true, "untap": true,
  "pay_life": 3,
  "sacrifice":      { "types": ["Creature"] },   // a selector; the permanent dies
  "return_to_hand": { "types": ["Land"] },       // a selector; the permanent comes back
  "tap_permanents": { "subtypes": ["Vampire"], "count": 5 },  // taps *others*; they stay
  "tap_permanents": { "types": ["Creature"], "total_power": 3 },  // crew 3
  "discard": 1, "discard_selector": { "types": ["Land"] },
  "discard_self": true,                           // cycling: *this* card, no choice
  "remove_counters": { "counter": "-1/-1", "amount": 1 },
  "exile_from_graveyard": { "types": ["Creature"] },
  "times": { "counters_on": { "counter": "age",            // cumulative upkeep:
                              "objects": { "self_only": true } } } }  // …for each
```

`times` multiplies the **mana** half and is the only part of a cost that is not
fixed when the card is written — cumulative upkeep's "pay its upkeep cost for
each age counter on it". It is read only by `may`'s `pay`, and that location is
forced rather than convenient: an activated ability's cost is settled by
legality *before* any effect has run, so a value expression there would have
nothing to read.

It multiplies **every** part of the cost. `{1}{U}` at three age counters is
`{3}{U}{U}{U}`, and scaling only the generic half gives `{3}{U}` — a card that
gets relatively cheaper the longer it lives. Hybrid pips are repeated rather
than summed, since each is its own choice of which half to pay. A `times` beside
a cost with no mana is refused: it would multiply nothing and charge flat.

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

### Crew — a tap cost measured in power

```jsonc
{ "kind": "activated", "text": "Crew 3 (…)",
  "cost": { "tap_permanents": { "controller": "you", "types": ["Creature"],
                                "total_power": 3 } },
  "effects": [ { "op": "animate", "power": { "const": 4 }, "toughness": { "const": 4 },
                 "types": ["Creature"],
                 "objects": { "zone": "battlefield", "self_only": true } } ] }
```

*Vehicle* needed nothing — `subtypes` is free text. `total_power` is the whole
capability, and a sum is not a count with a different number: **one 4/4 crews a
Vehicle that four 0/1s cannot.** Written as a count, crew is unpayable on a wide
small board or free on a tall one, and both look plausible.

**Derived** power, for skulk's reason: an anthem, a pump spell or a `+1/+1`
counter all change who can crew, and the printed face would refuse a crew the
board plainly supports.

It asks **one creature at a time**, which is forced rather than stylistic:
`ask_objects` takes counts, not sums, so a single subset question could be
answered with a set that does not reach the number — and a cost cannot fail
halfway through being paid. It also stops the moment the Vehicle is crewed,
rather than taking every creature that could have helped.

`count` and `total_power` together are refused: they are two different questions,
and a card giving both would be paid by whichever was checked first.

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
{ "combat_damage_by": ["Faerie", "Rogue"] }   // prowl
```

`combat_damage_by` is prowl: "…if a player was dealt combat damage this turn by
a Faerie or a Rogue". A seventh entry in the per-turn ledger, and the only one
that is not a number — the other six say how much and to whom, and none says
**who dealt it**.

The board cannot stand in, which is the argument the whole ledger rests on: by
the time a prowl spell is cast the Faerie that got through may be dead, bounced,
or no longer a Faerie, and none of those undo the damage. `exists` over Faeries
you control is the near miss and is a different card — true with one sitting at
home that never attacked, false after the one that connected traded in combat.

Read off **derived** subtypes at the moment the damage lands, so a changeling
and a creature granted the type both count. Combat damage only, and cleared at
cleanup with the rest of the ledger.

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
`deals_combat_damage_to_player` · `dealt_damage` · `becomes_target` ·
`becomes_blocked` · `attacks_unblocked` · `becomes_untapped` · `upkeep` ·
`draw_step` · `begin_combat` · `end_step` · `you_gain_life` · `counter_placed` ·
`draw` · `discard` · `cycle`

**`becomes_untapped`** is inspired, and it is nearly all untap step. The event
had always existed — `untap_permanent` fires it — but `untap_all` emitted one
aggregate carrying a `count` and no `oid`, through `emit` rather than `fire`, so
it never reached the trigger bus and named no permanent for `source: "self"` to
match. The untap step now fires one event per permanent like every other path
does. A permanent that was already untapped does not *become* untapped, and one
held down by `skip_untap` never untapped at all.

**`becomes_blocked` and `attacks_unblocked` are told from the attacker's side**,
and they are a pair rather than two features: both are decided when the block
declaration closes, and "isn't blocked" is not an event that happens but the
absence of one, which only becomes a fact once the declaration is over. Flanking,
rampage, bushido and frenzy.

`blocks` cannot stand in for either. It fires once per *blocker* and is about
the blocker, so an attacker blocked by three creatures sees three unrelated
events concerning somebody else, and an attacker blocked by nobody sees none at
all.

`blockers` on the event is the count — rampage is "+N/+N for each creature
blocking it **beyond the first**", so the card does that arithmetic:

```jsonc
{ "op": "pump", "objects": { "self_only": true },
  "power": { "times": [ { "const": 2 },
                        { "minus": [ { "binding": "blockers" }, { "const": 1 } ] } ] } }
```

Flanking needs *which* creatures are blocking, not how many, so the `blocking`
selector takes a binding as well as a boolean:

```jsonc
{ "blocking": true }                      // blocking anything
{ "blocking": { "binding": "self" } }     // blocking the creature bound here
```

The boolean form cannot say flanking: on a board with two attackers it matches
every blocker in both combats, so flanking would shrink creatures blocking
somebody else — and on a one-attacker board, which is the obvious test to write,
it looks perfect.

**`becomes_target` fires as the spell goes on the stack**, not as it resolves
(rule 603.2d) — heroic and ward. That timing is the whole of ward: the point is
to tax the opponent *before* the removal spell does anything, and a version
firing on resolution would be a refund. One event per target, so a spell hitting
two creatures wakes both.

Its `controller` clause asks **whose spell it is**, not who controls the thing
being targeted — heroic is "whenever *you* cast a spell that targets this", ward
is "whenever an *opponent* does". The two are easy to confuse and the confusion
is silent: read the other way round, heroic would grow off the removal aimed at
killing it. `source: "self"` likewise means the permanent *being* targeted; the
event's `source` is the spell.

Ward needs nothing else. `may` has taken an arbitrary `player` since Fact or
Fiction and a `pay` cost since Rhystic Study, `{"binding": "event_player"}` is
the caster, and `counter` takes a `sid`:

```jsonc
{ "op": "may", "player": { "binding": "event_player" },
  "pay": { "mana": "{2}" },
  "else": [ { "op": "counter", "sid": { "binding": "sid" } } ] }
```

`counter`'s `sid` form exists because "counter **it**" is not a targeted
ability. The spell it means is the one that just targeted this permanent, which
the trigger's bindings already carried; written as a `target` instead, the ward
creature's controller would get to point it at a different spell. The loader
refuses a card carrying both.

**`dealt_damage` is about the creature being hurt** — enrage, "whenever this
creature is dealt damage". Sugar over `DAMAGE_DEALT` in the sense `creature_dies`
is sugar over `DIES`: the engine fires one event for damage to a permanent and
for damage to a player, and only the first has an object for a trigger to be
about. Two things it does not do, both of which would be a wrong number rather
than an error:

- it does not fire on damage to a **player**, so a burn spell to the face does
  not wake every enrage creature on the board;
- `source: "self"` means *this creature was dealt damage*, never "this creature
  dealt it". For every other trigger the event's subject and its source are one
  object; here they are the victim and the attacker, so this is the one event
  where the two have to be told apart.

"…deals **that much** damage" needs nothing extra: `amount` was always copied
into the trigger's bindings, so `{"binding": "amount"}` reads it.

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
`block_restriction` · `prevent_damage` ·
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
| `{"is_attached": true}` | whether the source is attached to something — reconfigure |
| `{"top_of_library": filter}` | matches the **one** card on top of a library, on its printed face |

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

#### "The top card of your library is black"

```jsonc
// Vampire Nocturnus
{ "kind": "static", "effect": "grant_keyword",
  "affects": { "controller": "you", "types": ["Creature"], "subtypes": ["Vampire"] },
  "keywords": ["flying"],
  "condition": { "top_of_library": { "controller": "you", "colors": ["B"] } } }
```

Safe here for the same reason a zone count is: nothing in the characteristics
pipeline can change what is on top of a library, so it is an input.

`exists` over `{"zone": "library", "colors": ["B"]}` is the near miss, and it is
a different card. It asks whether *any* black card is anywhere in ninety-nine,
which in a mono-black deck is true essentially always — so Vampire Nocturnus
would have read as a permanent +2/+1 and flying, and it would have passed every
gate looking correct.

The filter reads a printed face and an owner and nothing else, the same rule
every off-battlefield filter follows: a library card is not tapped, attacking or
attached to anything, and a key that loads and matches nothing is how a card
comes to do less than it prints. `zone` is refused too — the zone is the whole
of what the leaf names.

An empty library matches nothing, so the static is simply off.

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

### Reconfigure — taking it off again

```jsonc
// "Reconfigure {1}" — two abilities, and the attach half is the equip ability.
{ "kind": "activated", "text": "Reconfigure {1}", "sorcery_speed_only": true,
  "cost": { "mana": "{1}" },
  "targets": [ { "id": "t1", "kind": "permanent", "count": 1,
    "selector": { "zone": "battlefield", "controller": "you",
                  "types": ["Creature"], "exclude_self": true } } ],
  "effects": [ { "op": "attach", "objects": { "target": "t1" } } ] },

{ "kind": "activated", "text": "Reconfigure {1}", "sorcery_speed_only": true,
  "cost": { "mana": "{1}" },
  "effects": [ { "op": "unattach",
                 "objects": { "zone": "battlefield", "self_only": true } } ] },

// "Attached permanents with reconfigure aren't creatures." (702.151d)
{ "kind": "static", "effect": "set_types", "affects": { "self_only": true },
  "types": ["Artifact"], "condition": { "is_attached": true } }
```

The attach half needed nothing — it is Equip, which shipped long ago. `unattach`
is the new op, and there was no route to it at all: the attach model only ever
*moved* an Equipment, and moving one onto a creature you do not want it on is a
different game action from taking it off.

The third ability is the half that is easy to miss and expensive to miss. These
cards are printed **Artifact Creature — Equipment**, so without 702.151d a
reconfigured blade pumps the creature it is on *and* attacks beside it. That is
a strictly better card, and nothing on the board would say so. `is_attached` is
the leaf that switches it, and it is legal in a static's condition for the
reason a counter is: `attached_to` is a field the attach primitive writes, so no
layer can change it.

Not to be confused with the `{"attached": true}` **filter** key, which points
the other way — at the permanent this one is attached *to*, and is how "equipped
creature gets +2/+2" is written. The two sit on the same card and mean opposite
things.

`unattach` deliberately does not touch **Auras**: state-based actions bin an
Aura attached to nothing, so unattaching one is a destroy written in a way that
does not say so.

Reconfigure is also the first Equipment that is *also a creature*, which makes
rule 301.5c reachable for the first time — an Equipment may not equip itself.
The card says `exclude_self`, and `attach` refuses it anyway, because an
Equipment attached to itself is a permanent no rule can ever detach.

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

Eight static effects describe the *player* rather than a characteristic, so they
take `affects_player` instead of `affects`:

```jsonc
{ "kind": "static", "effect": "extra_land_drops",
  "affects_player": "you", "amount": { "const": 1 } }
{ "kind": "static", "effect": "no_hand_limit", "affects_player": "you" }
{ "kind": "static", "effect": "play_lands_from_graveyard", "affects_player": "you" }
{ "kind": "static", "effect": "play_lands_from_library_top", "affects_player": "you" }
{ "kind": "static", "effect": "reveal_library_top", "affects_player": "you" }
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

`reveal_library_top` is "play with the top card of your library revealed", and
it is the only static here that changes **nothing** about the rules: it grants no
permission and moves no card. It makes one card public, and is read by
`serialize` and by nothing else.

It is still load-bearing rather than flavour. Vampire Nocturnus cannot be piloted
without it — whether your team has flying is a fact you are meant to know before
declaring attackers, and the condition that decides it is otherwise invisible. So
`library_top` goes to **every** seat rather than its controller's: the card is
public, and an opponent who cannot see it is playing against information they are
entitled to. It is `null` whenever nothing reveals it, so the client needs no
separate flag, and `findCard` searches it — a zone of one — or the preview rail
blanks on the single card the whole mechanic exists to show.

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

## Join forces — the one cost the whole table pays

```jsonc
{ "op": "join_forces", "as": "joined", "pay": { "mana": "{1}" },
  "prompt": "Pay {1} into the shared pool?" },
{ "op": "draw", "player": "you", "amount": { "binding": "joined" } }
```

Every other cost in the engine hangs off **one** player. `may`'s `pay` grew a
`player` spec for Rhystic Study, which is as close as the vocabulary gets, and
it asks that player once. This asks the whole table, repeatedly, and adds the
answers up.

One unit at a time, and that is forced: "any amount" has no ceiling to offer as
a `choose_x`, and a seat that stops paying is a seat that answered no.

**Order is the card.** Starting with the controller, in turn order, so later
players see what earlier ones have already put in — the whole politics of a
join-forces spell at a pod. Asked simultaneously, or in seat order regardless of
who cast it, it would be a different card.

The total lands in the binding named by `as`, read back with `{"binding": …}`
the way clash's `clash_won` is. An effect that collects it and names no binding
has taxed the table for nothing, so the loader refuses one.

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

### Entwine — "choose both if you pay the entwine cost"

```jsonc
"kicker": "{2}", "kicker_label": "entwine",
"spell_effects": [
  { "op": "choose_mode", "count": 1, "all_if": { "kicked": true },
    "modes": [ … ] }
]
```

The price needed nothing: entwine is an additional cost paid as the spell is
cast, which is `kicker`, and legality already offers a kickable card twice. What
was missing is that the two lines must ask **different questions** — the plain
one asks which mode, the entwined one asks nothing.

`all_if` forces every mode rather than offering them, and both near misses load
cleanly. A wider `count` when kicked asks "which two of these two", a question
with one answer, and puts a decision on screen that is not one. A `may` would
let a player pay the entwine cost and then decline half of what they bought.
Rule 702.42a puts the choice at the moment of casting, and choosing the entwine
cast line *is* that choice.

The half that bites: modes are answered as the spell goes on the stack (601.2b),
and the `kicked` flag does not reach the object until resolution — so
`Game._ask_modes` is handed the action's own flag. Without that, every entwined
spell quietly picks one mode and the extra mana buys nothing.

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

## Transforming double-faced cards

```jsonc
// data/cards/edgar.cards.json -- the front face
{ "id": "bloodline_keeper", "name": "Bloodline Keeper",
  "back_face": "lord_of_lineage",
  "abilities": [{
    "kind": "activated",
    "text": "{B}: Transform this creature. Activate only if you control five or more Vampires.",
    "cost": { "mana": "{B}" },
    "condition": { "cmp": ">=",
                   "left":  { "count": { "controller": "you", "types": ["Creature"],
                                         "subtypes": ["Vampire"] } },
                   "right": { "const": 5 } },
    "effects": [{ "op": "transform" }] }] }
```

**Two `CardDef`s, one `GameObject`.** The back face is an ordinary card entry in
the same pool, and `GameObject.transformed` decides which one
`GameState.card_of` returns. That is the whole mechanic, because `card_of` is a
single choke point: the characteristics layers, legality, combat and the
serializer all go through it, so a transformed permanent shows its back face
everywhere at once and none of them needed changing.

`transform` defaults its `objects` to the ability's own source — "transform
**this**" — and takes `to_back` for the rare card that says "turn it face up"
rather than "turn it over". A permanent with no back face does nothing rather
than raising (rule 701.28d), which keeps a blanket "transform each creature"
honest on a board of ordinary cards.

**A back face is not a card.** It has no mana cost, is never in a hand, a
library or a deck, and exists only as the face a permanent already in play
turned over to. `validate_deck` refuses one, and `test_every_card_works` skips
casting it — "it cannot be cast" is not a defect for something nobody casts.

The link is written on the **front** face only; the registry derives
`front_face` on the back. A hand-written back-pointer could name a different
card than the front names, and every guard here asks `front_face is not None`,
so a half-written link would quietly make a free 5/5 castable.

**It enters front face up.** Rule 712.13a — `transformed` is reset with the
rest of the battlefield state, so a permanent that leaves and comes back is the
front face again. Without it, blinking a Bloodline Keeper is a free upgrade.

Both faces share one Scryfall id, because the id names the *card* and not the
face; `CardArt.back` is what makes the back download the back illustration. The
catalog stores the card under its joined name ("Bloodline Keeper // Lord of
Lineage"), which neither face matches on its own, so `CardIndex.lookup` grew a
`joined=True` mode.

## "Activate only if…"

```jsonc
{ "kind": "activated", "cost": { "mana": "{B}" },
  "condition": { "cmp": ">=", "left": { "count": { … } }, "right": { "const": 5 } },
  "effects": [ … ] }
```

An **activation restriction** (rule 602.5c), checked by `legality` before the
ability is offered and re-checked nowhere else — an ability that was legal when
activated still resolves if the board changes while it is on the stack.

It shares the `condition` field with a static's "as long as…" clause, which is
safe because an ability is static or activated and never both. The *languages*
differ, though: a static gets the narrow one, because anything reading a derived
characteristic would let one static depend on another's output. Nothing is being
computed here that another condition could depend on, so this gets the full
`if`-effect language.

It is deliberately not `sorcery_speed_only` with extra steps. That is a timing
restriction and this is a board one, and a card can print both.

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

## Aura swap — an exchange, not two moves

```jsonc
{ "kind": "activated", "text": "Aura swap {2}",
  "cost": { "mana": "{2}" }, "effects": [ { "op": "aura_swap" } ] }
```

Written as a bounce beside a put-onto-the-battlefield it loads, looks right, and
goes wrong twice where no board would show it:

- **The new Aura arrives enchanting nothing.** It is not cast, so it has no
  targeting clause to carry a creature, and `_attach_aura` — which reads a
  spell's first target — never runs. A state-based action then bins it, and the
  ability reads "exchange" while being a slow Naturalize on your own card.
- **The exchange is not atomic.** Between the two the enchanted creature is
  unenchanted, which matters on exactly the cards this is printed alongside.

The attach happens *after* the move, because `reset_permanent_state` clears
`attached_to` on the way onto the battlefield — the same trap an Aura attaching
itself during `spell_effects` falls into.

A hand with no Aura in it does nothing, rather than bouncing the one on the
battlefield for free.

## Soulbond — a relationship that is not attachment

```jsonc
// "…pair this creature with another unpaired creature when either enters."
{ "op": "pair", "objects": { "zone": "battlefield", "controller": "you",
                             "types": ["Creature"] } }

// "As long as this creature is paired, **both** creatures get +1/+1."
{ "kind": "static", "effect": "buff", "affects": { "paired": true },
  "power": { "const": 1 }, "toughness": { "const": 1 } },
{ "kind": "static", "effect": "buff", "affects": { "paired_with_source": true },
  "power": { "const": 1 }, "toughness": { "const": 1 } }
```

`attached_to` is the nearest existing thing and is wrong in two independent
ways, either of which is enough:

| | |
|---|---|
| it is **one-way** | "both creatures get +1/+1" is asked of the partner too, and a one-sided link buffs exactly one of them |
| an Aura attached to nothing **dies** | a state-based action bins it; a creature whose partner died is simply unpaired. Two lifetimes, two fields — `frozen_by` and `skip_next_untap` already made this argument |

So `paired_with` is symmetric, and breaking it is two writes: the leaving
object's own is cleared by `reset_permanent_state`, and the **partner's** in
`_detach_all` — nothing else walks back along the link, and a creature left
pointing at a card in a graveyard keeps the bonus for ever.

The static is written once and applies to two creatures, hence two filter keys.
Both are board state, so neither can make one static depend on another's output.

## Ninjutsu — swapping into a combat already under way

```jsonc
{ "kind": "activated", "text": "Ninjutsu {1}{U} (…)",
  "active_zones": ["hand"],
  "cost": { "mana": "{1}{U}",
            "return_to_hand": { "controller": "you", "types": ["Creature"],
                                "attacking": true, "blocked": false, "count": 1 } },
  "effects": [ { "op": "put_onto_battlefield",
                 "objects": { "zone": "hand", "self_only": true },
                 "controller": "you", "tapped": true, "attacking": true } ] }
```

Two missing words, one on each half.

**`blocked`** is a new selector key and is *not* the negation of `blocking`.
That key asks whether a creature is blocking something; this asks whether
anything is blocking **this attacker**, and the two are different creatures.
`Cost.return_to_hand` already existed, for Meloku.

**`attacking`** is `create_token`'s clause moved onto `put_onto_battlefield`.
The ninja joins the combat the returned attacker just left, which is why it
arrives unblocked — the blocker that was there was blocking a creature now
sitting in its owner's hand. Same contract as the token version: it was never
*declared* as an attacker (508.4), so it triggers nothing that fires on
attacking.

The ability is offered from **hand** and satisfies the outside-the-battlefield
guard through unearth's satisfier — an unconditional top-level effect moving
`self_only` out. Ninjutsu is the shape that makes that satisfier obviously
right: nothing in the *cost* removes the card, and it leaves hand because the
effect puts it onto the battlefield.

## Haunt — the exile link pointing the other way

```jsonc
// "When this creature dies, exile it haunting target creature."
{ "op": "haunt", "objects": { "target": "t1" } }

// "When the creature this card haunts dies, …"
{ "kind": "triggered", "active_zones": ["exile"],
  "trigger": { "event": "creature_dies", "controller": "any",
               "filter": { "controller": "any", "haunted_by": "self" } },
  "effects": [ … ] }
```

The engine already had an exile link — `exiled_by`, written on the exiled card
and naming the permanent that exiled it. That is the **O-Ring direction**, and
it is right there because the exiler is the thing that goes away and its own
leaves-trigger reads the link back.

Haunt is the mirror. The card in exile is what survives, and it is what has to
notice a creature dying somewhere else, so the link points from the haunting
card **at its victim**.

`haunted_by` is therefore a *trigger filter* answered off the **ability's
source**, not off the subject: by the time the second trigger fires, the haunted
creature has died and carries no record of who was haunting it. The haunting
card is in exile with the link on it, which is why that ability carries
`active_zones: ["exile"]` — the same widening the cycling trigger needed for the
graveyard.

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

**`cant_block`** is its mirror, read by `combat.can_block` — unleash, and the
"can't block" printed on a hundred aggressive commons:

```jsonc
{ "kind": "static", "effect": "cant_block",
  "affects": { "self_only": true },
  "condition": { "counters": { "counter": "+1/+1", "amount": 1, "op": ">=" } } }
```

Checked inside `can_block` rather than in `blocks_valid`, which is the whole
difference between it and menace: this is a fact about one creature, so a
creature under it is never offered as a blocker at all, where menace is a fact
about the shape of the finished declaration.

Both are statics rather than keywords for the reason `lock_abilities` is one: a
keyword is a *characteristic*, and these are permissions. Listing "can't block"
among a creature's keywords would be a lie about what the card says.

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

### Wither and infect

```jsonc
"keywords": ["wither"]
"keywords": ["infect"]
```

`Keyword`s, not `replacements` entries, and the census routed them wrongly for a
reason worth naming: the replacement whitelist is entirely about a permanent
**entering the battlefield**, and neither of these is an entry event. They are
facts about *damage*, and damage already has one choke point that reads
keywords — `damage_permanent`, where deathtouch and lifelink sit three lines
apart. By the routing rule at the top of [keywords.md](keywords.md) they qualify
on their own: no parameter, and a rule reads them.

**It is still damage**, which is the half a naive version loses. Deathtouch
still marks the victim, lifelink still gains, the damage ledger still records
who did it, and `DAMAGE_DEALT` still fires with the same amount — so enrage,
Sengir Vampire and every "damaged this turn" filter read a withering creature
the way they read any other. Only where the number lands changes.

They differ in exactly one place, and it is not the creature half: 702.90b says
nothing about damage to **players**, so a wither creature that gets through hits
for life in the ordinary way. Folding the two together would make every wither
creature a poison threat.

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

### Absorb, which is not protection with a number

```jsonc
{ "kind": "static", "effect": "prevent_damage",
  "affects": { "self_only": true }, "amount": { "const": 2 } }
```

"If a source would deal damage to this creature, prevent 2 of that damage."
Protection is the near miss and is a *bigger* card in four ways, only one of
which is about damage: it prevents all of it, and it also stops the creature
being blocked, enchanted and targeted. An absorb creature written as protection
is unblockable and untargetable.

Parameterised on N, so a static rather than a `Keyword` — the routing rule's
second row.

The clause that decides everything is "**a source**". Prevention is per source
and per instance, not a pool that drains: absorb 1 blocked by three 1/1s takes
nothing from any of them, and hit by one 3/3 takes two. That is the whole reason
absorb 1 is printable, and a running total would make it a one-shot.

Prevented damage was **never dealt**, so it is subtracted before anything the
damage pipeline does afterwards — no deathtouch mark, no lifelink, no entry in
the damage ledger, and a `DAMAGE_DEALT` carrying the reduced number. Only what
got through is damage, and it is ordinary damage: the excess from a deathtouch
source still marks the victim.

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

### How long a granted keyword lasts

```jsonc
{ "op": "grant_keyword", "keyword": "haste", "objects": { "target": "t1" } }
{ "op": "grant_keyword", "keyword": "haste", "duration": "permanent",
  "objects": { "self_only": true } }          // riot: for as long as it lasts
```

The default is until end of turn, which is what almost every pump spell wants.
`permanent` is riot's "enters with haste", and the difference is invisible on
the turn the creature arrives and total afterwards: an until-end-of-turn haste
evaporates at cleanup, so from the next turn a riot creature that chose haste
looks exactly like one that chose the counter. A misspelled duration is refused
rather than defaulted, because defaulting means shipping the wrong half.

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

## Explore

```jsonc
// Merfolk Branchwalker — "When this creature enters, it explores."
{ "op": "explore", "objects": { "zone": "battlefield", "self_only": true } }

// "Target creature you control explores."
{ "op": "explore", "objects": { "target": "t1" } }
```

Rule 701.40a in one op: reveal the top card, put it in your hand if it is a
land, and otherwise put a `+1/+1` counter on the exploring permanent and let its
controller send the card to the graveyard or leave it on top.

**The branch is why it is an op.** Every other conditional in the DSL is an `if`
over a condition, and the condition language has no way to name *the card that
was just revealed*. The nearest spelling is `{"exists": {"zone": "library",
"types": ["Land"]}}` — "is there a land somewhere in my deck" — which is true in
essentially every game, so a Branchwalker written that way takes the land branch
every time and draws a card instead of growing. It loads cleanly and looks right
on the board.

`objects` is **required**, and that is not bookkeeping. Half the printed explore
cards are sorceries, whose source is a spell on the stack; a defaulted
`self_only` would resolve to that spell, reveal nothing and place no counter —
while reading perfectly on the creature cards where the default was tested.

Two smaller things follow from the rule text rather than from convenience:
each permanent in the pool explores **separately**, so two exploring creatures
reveal two cards; and the land half asks **nothing**, because 701.40a offers the
choice only on the "otherwise" branch and a yes/no there would let a player
decline a free card.

## Cascade and ripple — walking a library

```jsonc
// "When you cast this spell…" -- an ordinary cast trigger.
{ "kind": "triggered", "active_zones": ["stack"],
  "trigger": { "event": "spell_cast", "source": "self", "controller": "you" },
  "effects": [ { "op": "cascade" } ] }

{ "op": "ripple", "amount": { "const": 4 } }
```

The free cast was already there — `suspend.cast_for_free` — and the **scan** was
not. Every other way the DSL reaches a library either takes the top N
(`look_at_top`) or searches the whole of it (`search_library`); cascade does
neither, walking down until a condition is met at a depth the card cannot know.

`max_mana_value` defaults to **this spell's own** mana value, read off the
source rather than written into the card, because a cascade spell's own cost is
the number.

"Put the rest on the bottom in a random order" is shared, and it is deliberately
**not** a shuffle: shuffling reorders the whole library and would destroy a
stacked top somebody else set up. It also goes through `move_object` rather than
editing the list, because half of those cards are in exile and half never left —
an object whose `zone` and whose containing list disagree is a card every other
reader in the engine sees differently.

**Haste is not shared.** It belongs to suspend, and a cascaded creature that
could attack immediately would be a strictly better card, so `cast_for_free`
grew an opt-in rather than granting it to everything that casts for nothing.

Ripple is not cascade with a parameter: "the same name as this spell" is a
comparison against the *source*, which no selector key names. `name` takes a
literal written into the card — true for ripple, and wrong the moment anything
copies it.

## Connive

```jsonc
// "Whenever this creature attacks, it connives."
{ "op": "connive", "objects": { "zone": "battlefield", "self_only": true } }

// Connive 2, on a target.
{ "op": "connive", "amount": { "const": 2 }, "objects": { "target": "t1" } }
```

Rule 701.47a: draw N, discard N, then a `+1/+1` counter for each **nonland**
card discarded that way.

Explore's argument again, in a different place. `draw` and `discard` both exist,
so the obvious spelling is those two plus `add_counters` — and the counter has
nothing correct to count. `discard` returns nothing, `count` over the graveyard
counts what was already lying in it, and `cards_to_graveyard_this_turn` counts
every graveyard at the table and every earlier discard this turn. All three
load, and all three grow the creature by a number that looks plausible.

"Nonland" is the clause doing the work: conniving away two lands is the drawback
the mechanic is priced around, and an op that counted the discards rather than
reading them would be a strictly better card whose difference shows up only on
the turn your hand was all lands.

`objects` is required for `explore`'s reason, and each permanent in the pool
connives on its own — its own controller draws, from its own hand, onto its own
counters.

## Clash

```jsonc
// "Clash with an opponent. If you win, draw a card."
{ "op": "clash" },
{ "op": "if",
  "condition": { "cmp": ">=", "left": { "binding": "clash_won" }, "right": { "const": 1 } },
  "then": [ { "op": "draw", "player": "you", "amount": { "const": 1 } } ] }
```

Rule 701.23a. Both players reveal the top card of their library, each may then
put their own card on the bottom, and the higher mana value wins.

`reveal` was never the missing piece — the **comparison** was. Every numeric
leaf in the value language reads one board: `mana_value_of` takes a target or a
snapshot, and neither can name a card sitting on top of an opponent's library.
`top_of_library` gets closest and answers a filter with a boolean, so it cannot
produce a number to compare against, let alone the two this needs at once.

The outcome is a **binding**, not a `won:` block, because the printed card is
two sentences and `if` already says the second one. The loader refuses either
half without the other, exactly as it refuses half a kicker: a `clash` nothing
reads reveals two cards and stops, and a `clash_won` with no clash behind it
reads 0 for ever. Both load cleanly.

Three things the op decides, each of which a card written around it would
otherwise get quietly wrong:

| | |
|---|---|
| **Each player answers for their own card** | asking the clasher about both would be a strictly better spell |
| **Both cards are revealed before either answer** | the information is the whole point of the decision |
| **An empty library cannot win, and loses to `{0}`** | "higher than each other card revealed" is vacuously true against nothing, so the no-card sentinel has to sit *below* zero rather than at it |

At a pod the op asks which opponent to clash with; in a duel there is one
opponent and `ask_player` does not stop to ask.

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
remove its source from that zone. Without that it is an infinite engine — a card
in hand whose ability costs only mana could be activated forever without ever
leaving.

Four things satisfy it, and the last two arrived with **unearth** and
**forecast**:

| | |
|---|---|
| `discard_self` on the cost | cycling |
| `exile_from_graveyard` on the cost | embalm |
| an **unconditional top-level effect** moving `self_only` out | unearth — "return this card from your graveyard to the battlefield" |
| `activate_steps` **and** `once_each_turn` together | forecast — "activate only during your upkeep and only once each turn" |

Forecast is the one that never moves the card at all, and it is safe because it
may be activated once. Both halves are required: `once_each_turn` alone is still
a free ability every turn for the whole game, which is exactly what forecast's
upkeep window prices. `activate_steps` is checked where `sorcery_speed_only` is,
since both are permission to activate at all (602.5c), and "**your** upkeep" is
the ordinary `condition: {"is_your_turn": true}` beside it — the two are
separable and one card prints only the timing half.

`once_each_turn` counts **activations**, not resolutions. `resolutions_this_turn`
already existed and is the wrong number: an ability whose first activation was
countered has still had its go, and counting resolutions would hand it back.

Unearth pays plain mana, so neither cost form could say it. The guard was right
about the property and too narrow about how to reach it: what matters is that
the source cannot still be sitting there afterwards, however it left.

*Unconditional* and *top-level* are both load-bearing. An exit nested inside an
`if` or a `may` might not run, and an ability whose only way out is a branch the
player can decline is activatable again from the same graveyard — which is
exactly the shape the guard exists to refuse. So is `self_only`: an ability that
returns *a* creature card has not moved itself.

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
"kicker": "{1}{U}", "kicker_label": "buyback"  // pay more as you cast it
"buyback": true                             // …and it returns to hand instead of the graveyard
"evoke": "{2}{U}", "evoke_label": "dash"    // an alternative cost, and its printed name
"alternative_cost": { "mana": "{R}", "condition": {...} }  // spectacle: only sometimes offered
"emerge": "{5}{U}{U}"                       // pay less by eating a creature
"emerge_subtype": "Goblin"                  // offering: only that type may be eaten
"pay_generic_with": "tap_creatures"         // convoke; "exile_from_graveyard" is delve
"retrace": true                             // cast from the graveyard, discarding a land
"graveyard_cost": { "mana": "{1}{U}", "pay_life": 3 }  // cast from the graveyard
"graveyard_cast": "exile"                   // …and where it goes afterwards
"graveyard_cast_transformed": true          // disturb: it comes back as its back face
"dredge": 3                                 // replace a draw: mill 3, take this back
"madness": "{R}"                            // discarded -> exiled, and castable for this
"miracle": "{W}"                            // cast it as the first card you draw
"foretell": "{R}"                           // pay {2} to exile it; cast it later for this
"epic": true                                // no more spells; a free copy each upkeep
"suspend": { "cost": "{G}", "counters": 2 } // exile it now, cast it free later
"split_second": true                        // nobody may respond while it is on the stack
"rebound": true                             // exile it as it resolves, cast it free next upkeep
"overload": "{3}{R}"                        // cast it with no targets, hitting each instead
"additional_cost": { "sacrifice": {...} }   // casualty, replicate, Deadly Dispute
"additional_optional": true                 // …"you may"
"additional_repeatable": true               // …"any number of times"
```

#### Casting from the graveyard

One capability, three keywords, and the only thing separating them is the price
and the destination:

```jsonc
\ Flashback -- once only.
"graveyard_cost": { "mana": "{1}{U}", "pay_life": 3 }

\ Jump-start -- the printed mana again, plus a discard. Also once only, so
\ `graveyard_cast` is left at its default.
"graveyard_cost": { "mana": "{2}{U}", "discard": 1 }

\ Escape -- and this is the whole of it: the card comes back.
"graveyard_cost": { "mana": "{1}{R}",
                    "exile_from_graveyard": { "count": 2, "exclude_self": true } },
"graveyard_cast": "graveyard"
```

The mana half **replaces** the printed cost and everything else is charged on
top, so a jump-start card repeats its own mana cost rather than leaving it out.
`exclude_self` matters on escape: the printed line says "exile N **other**
cards", and without it a card in an otherwise-empty graveyard pays with itself.

`flashback` is still accepted as the name the first keyword shipped under, and
means exactly `graveyard_cost`. A card giving both is refused rather than
resolved — two prices from the graveyard is no answer to what it costs from
there. `graveyard_cast` without a cost is refused for the mirror reason: it
would claim to be an escape card and never be castable at all.

#### An additional cost that is not mana

```jsonc
// Casualty 2
"additional_cost": { "sacrifice": { "controller": "you", "types": ["Creature"],
                                    "power": { "op": ">=", "value": { "const": 2 } } } },
"additional_optional": true,

// "When you do, copy this spell." -- an ordinary cast trigger.
{ "kind": "triggered", "active_zones": ["stack"],
  "trigger": { "event": "spell_cast", "source": "self", "controller": "you",
               "condition": { "cmp": ">=", "left": { "additional_paid": true },
                              "right": { "const": 1 } } },
  "effects": [ { "op": "copy_spell" } ] }
```

`kicker` was the only additional cost a hand-cast spell could carry, and it is
wrong twice over here: it is **mana-only** — the cast variant is
`mana_cost.plus(kicker)`, a `ManaCost`, which cannot sacrifice anything — and it
is paid **once**.

So `additional_cost` is a full `Cost`, and legality offers **one cast line per
number of times paid** — convoke's shape rather than kicker's, because the count
changes both the price and what the spell does. The two modifiers are three
different printed cards:

| | |
|---|---|
| neither | Deadly Dispute — mandatory, so the free line is withdrawn entirely |
| `additional_optional` | casualty — "you **may** sacrifice" |
| both | replicate — "any number of times", which includes none |

`additional_repeatable` without `additional_optional` is refused: "any number of
times" includes zero, and a mandatory repeatable cost would make every replicate
card unplayable without the extra mana.

Unlike kicker there is **no half-a-cost guard**, and that is deliberate:
"sacrifice an artifact" is the whole of Deadly Dispute's cost and no clause on
the card reads it back. What is guarded is reading `additional_paid` with no
cost behind it, which would always be zero.

The non-mana half is paid **after** the mana (601.2g), so a creature that tapped
for mana can still be the one that is eaten — the order emerge and retrace
already use. Legality checks it is payable before offering the line.

**The copy needs nothing new.** "When you cast this spell" is a `spell_cast`
trigger with `active_zones: ["stack"]`, so it goes on the stack *above* the
spell and its copy resolves first — which is what 706.10 wants, and what a
`copy_spell` written into `spell_effects` would get backwards.

#### Overload

```jsonc
"overload": "{3}{R}",
"targets": [ { "id": "t1", …, "optional": true } ],
"spell_effects": [
  { "op": "if", "condition": { "overloaded": true },
    "then": [ { "op": "damage", "objects": { … }, "amount": { "const": 2 } } ],
    "else": [ { "op": "damage", "target": "t1", "amount": { "const": 2 } } ] }
]
```

Kicker, evoke, emerge, flashback and prowl all change what a spell **costs**.
Overload changes what it *does* — by rewriting a printed sentence, which is not
something the engine can do to data it was handed. So the card writes both
halves and branches on `{"overloaded": true}`, the shape `kicked` already has.

That is not a workaround. "Destroy target artifact" and "destroy each artifact"
really are two effects, one targeted and one not, and the residual gate still
sees one printed line implemented by one `if`.

**Targets are the half that bites.** An overloaded spell is cast with none at
all, so legality gives that line the empty tuple, and every target the card
declares must be `optional` — otherwise the overload line is offered and then
never castable, silently, because the printed line still is. The loader refuses
it.

The flag is written onto the object *before* `spell_effects` run, for
`cast_from_graveyard`'s reason: written after, every overloaded spell resolves
as the targeted half, with no targets, which is nothing at all.

#### Rebound

```jsonc
"rebound": true
```

Two halves, both nearly there. The **exile** is the third rider on where a
resolving spell goes, beside flashback's exile and buyback's hand — and like
both it only ever replaces the *graveyard*, which is why `rebound` on a
permanent card is a load error: a permanent enters the battlefield and never
reaches the rider, so the card would look implemented and never rebound once.

The **free cast** is suspend's, word for word, and shares `cast_for_free`.

What is new is one clause, and it is the loop guard: **"if you cast this spell
from your hand"**. The free cast happens from *exile*, so without it a rebounded
spell rebounds again every upkeep for the rest of the game. It takes two things
to close — `cast_from_hand`, recorded by `push_spell` because that is the last
moment the zone is knowable, and clearing the mark *before* the free cast, since
that cast is itself a cast and would otherwise re-arm the card as it resolved.

*Divergences, shared with suspend*: the free cast is mandatory rather than "you
**may** cast", and its targets are the first legal tuple rather than a choice.
Both because the upkeep tick runs from the turn structure, which cannot stop to
ask.

#### Epic

```jsonc
"epic": true
```

Both halves are about *where the state lives*. An epic card is in a graveyard a
moment after it resolves, so neither can be written on it.

The **restriction** is on the player, one-way and for the rest of the game —
`has_city_s_blessing`'s shape — and is enforced in `_cast_actions` rather than
as a cost or a condition, because it is not about any one card. Lands are
unaffected, which is why it sits there and not in `legal_actions`.

The **copy** is a rule rather than an ability, for suspend's ticking reason: the
card has no abilities where it is, and "at the beginning of each of your
upkeeps" belongs to the game the way the untap step does. It goes through the
same `put_copy_on_stack` that `copy_spell` uses.

"Except for its epic ability" is **one condition**, `not obj.is_token`, and it
is the sort of thing only a test finds: a copy is a token and resolves through
the same function the original did, so without it each upkeep's copy re-points
`epic_source` at itself — and the copy is removed by a state-based action a
moment later, which silently ends the copying after exactly one turn. The board
shows a card that worked once.

#### Foretell

```jsonc
"foretell": "{R}"
```

The census called suspend "the nearest shape". It is the *same* shape, and
foretell shares its `ActionKind`: both exile a card from hand to be cast later,
neither uses the stack, and neither can be countered. What differs is only the
ticking rule and whether the later cast costs anything. The `{2}` to foretell is
fixed by rule 702.143a; the card names only the later price.

**"Face down" here is `revealed_to`**, the private-information channel Glasses
of Urza built. That is a far smaller claim than a face-down *permanent*: a card
in exile nobody may interact with is hidden by not being shown, where a
face-down creature is a 2/2 shell over a real card and a characteristics
problem. Foretell needs only the first, which is why it ships and morph does not.

**"On a later turn" is the whole price** — foretold and cast on the same turn is
the printed cost paid in two instalments with the discount thrown in — so
`foretold_turn` is recorded and compared.

#### Dredge, madness and miracle — replacements that stop to ask

```jsonc
"dredge": 3        // "…you may mill three cards instead. If you do, return this card"
"madness": "{R}"   // "…exile it instead. When you do, you may cast it for {R}"
"miracle": "{W}"   // "…when you draw it, if it's the first card you drew this turn"
```

Every replacement in the `replacements` whitelist is applied **synchronously and
asks nothing** — enters tapped, enters with counters, the commander zone change,
tokens ceasing to exist. That is why it is a whitelist on the card and is
applied inline by `zones._enter_battlefield`.

These three are not whitelist entries and never could be: each puts a question
to a player at the exact moment of the replacement. What they were really
waiting on is that **drawing and discarding had to become things that can
suspend** — and that turned out to be small, because `turn.begin_step` already
ran through `Game._run`. The turn structure could carry a decision all along;
only `_draw_step` beneath it could not.

`primitives.draw_cards` and `discard_cards` still ask nothing — that module's
contract is "no decisions" and it is intact — and
[`engine/replacements.py`](../src/automtg/engine/replacements.py) wraps them.
Every draw and discard in the engine goes through the wrapper except the
**opening hand**, which rule 103 deals before the game begins: no graveyard to
dredge from, and no turn to have drawn a first card in.

Three details are the keywords rather than plumbing:

| | |
|---|---|
| dredge **replaces** the draw | no card is drawn, so dredging into an empty library does not deck you |
| madness exiles **either way** | a declined madness card is in exile, not the graveyard; the other way round, every madness card is a free graveyard-filler |
| miracle reads the tally **before** the draw bumps it | "the first card you drew this turn", and it is offered however the card was drawn |

The cast in madness and miracle is a real cast — it uses the stack and can be
countered — at a real price, which is what separates it from
`suspend.cast_for_free`. A cost that cannot be paid is not offered at all
(118.4), rather than asked and then failed.

#### Disturb

```jsonc
"back_face": "spirits_memory",
"graveyard_cost": { "mana": "{1}{W}" },
"graveyard_cast_transformed": true
```

Both halves shipped years apart and had never met: `graveyard_cost` is the cast,
generalised for flashback, jump-start and escape, and `transformed` is the face,
built for Bloodline Keeper. Disturb is the word joining them, and everything
interesting is **when** the face is turned.

*At cast time*, so the spell's name, types and effects are the back face's from
the moment it goes on the stack. The disturb cards this matters most for have a
Creature front and an Enchantment back, where even `is_permanent` would
otherwise be answered off the wrong face — and a spell that showed one face on
the stack and another on the battlefield is two different cards to everyone
watching.

*And again after the move*, because `reset_permanent_state` clears `transformed`
on the way onto the battlefield — rule 712.13a, "enters front face up", which is
right for every permanent except this one. `cast_transformed` sits beside the
other `cast_*` flags and outlives the spell for the same reason `cast_x` does.

Both halves are required: without a `graveyard_cost` there is no cast to
transform, and without a `back_face` the card is cast for its disturb cost and
arrives as its front face — flashback wearing the wrong word.

*Divergence*: legality enumerates the cast's targets off the **front** face,
because it decides what is castable before anything is turned over.

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
