# Keywords, and where each one lands

The engine implements 30 keywords. Every one arrived the same way: a card in the
authoring queue could not be expressed, a worker wrote a gap record,
`/extend-dsl` built it. That loop works, and [card-authoring.md](card-authoring.md)
is the argument for it.

But it re-asks one question from scratch every time — *given a printed keyword,
which of the engine's mechanisms should carry it?* — and the answer has been
worked out at least five times in five unconnected places:

| in [card-dsl.md](card-dsl.md) | the argument made there |
|---|---|
| "Its activated abilities can't be activated" | `lock_abilities` is **not** a keyword: a keyword is a characteristic, and this is a permission |
| Landwalk | five `Keyword`s rather than one parameterised ability, because a static cannot be *filtered on* |
| Block restrictions | `block_restriction` is a static, **not** a keyword, because the quality it names is a parameter |
| Skulk | a `Keyword`, because it must read **derived** power, which a static filter may never do |
| Protection / shroud | protection is a static (parameterised); shroud is a `Keyword` (one rule, no parameter) |

Each is right, and each was discovered independently. None of them is stated as
a rule, so none of them helps with the twenty-third keyword. This page is the
rule, and the census it applies to.

**This is the supply side.** [unsupported-cards.md](unsupported-cards.md) is
generated from `data/authoring/gaps/` and is *demand*-driven: it says what the
queued cards happened to ask for, ranked by how many each blocks. It is the
right thing to read when choosing what to build next for a deck. It cannot tell
you what is missing that nobody has asked for yet, because a capability with no
gap record is invisible to it. This page is the whole keyword surface, asked for
or not. Neither replaces the other, and
[rules-coverage.md](rules-coverage.md) remains the honest one-line status.

## The four families

The census below keeps the source document's own division, because it is a
useful one — but the family a keyword belongs to predicts its *mechanism* only
loosely, and the exceptions are where the work is.

**Keyword actions** — attach, scry, sacrifice, counter — are ops by
construction. They name a thing the effect layer already does to the game, and
the effect layer is a registry of exactly such things. When one is missing it is
a Tier A `/extend-dsl` job and nothing more.

**Ability words** — landfall, threshold, metalcraft, battalion — are italic
flavour with no rules meaning of their own. Rule 207.2c is explicit that they do
nothing; the ability after the word is an ordinary triggered or static ability.
So they are *usually free*: the DSL can already say them and only a card is
missing. That is the largest and least obvious finding on this page, and the
reason it exists. The ones that are not free fail for a specific, nameable
reason — almost always that the condition wants a per-turn ledger the engine
does not keep.

**Keyword abilities** — evergreen and expansion alike — are the hard family.
They scatter across five different mechanisms with no surface signal telling you
which, which is what the next section is for.

## The routing rule

Given a printed keyword, work down this table and take the first row that
matches. The right-hand column is the mistake that row exists to prevent.

| If the printed quality… | it is | witness | why not the neighbour |
|---|---|---|---|
| is deck-construction only | an **inert** `Keyword` | partner | it must still be listed, or the residual gate has an unclaimed line |
| takes a parameter — a colour, a type, a cost | a **static** with fields | protection, `block_restriction` | `Keyword` is a bare string; a parameter has nowhere to live on it |
| must read **derived** characteristics | a `Keyword`, compared inside the rule | skulk | static filters read *printed* characteristics only, which is what keeps the characteristics pipeline acyclic — so a static cannot ask this at all |
| takes no parameter, and some rule reads it | a `Keyword` enum member | flying, shroud | — |
| is a permission, not a characteristic | an until-end-of-turn effect | `lock_abilities` | a keyword would show up in the card's keyword list, and this is not something the card *is* |
| changes where or how the card is **cast** | a card-level field | kicker, evoke, emerge, retrace, suspend | the card does not have the ability where it is sitting — a spell in the graveyard has no abilities to activate |
| is an activated ability usable outside the battlefield | `activated` + `active_zones` + a cost that removes the source from that zone | cycling | the loader refuses one without the other, because an ability activated from hand that does not leave hand is an infinite engine |
| triggers on an event, with a filter | an ordinary `triggered` ability — **usually free** | prowess, landfall | no engine work at all; reaching for a new event here is the common over-build |
| is a game action the effect layer performs | an **op** | scry, surveil, mill | — |
| replaces an event as it happens | a `replacements` entry — **whitelist only** | wither, persist, undying | the whitelist is three declared forms (`cards/schema.py`); a fourth is engine work, not card work |

Three corollaries worth stating, because each has already cost a rebuild:

**A parameter that is the whole content is not a parameter.** Landwalk looks
parameterised — "islandwalk" is walk-over-Islands — but the quality has no
meaning apart from which land type, and there are exactly five. Five keywords
beat one static, because a keyword can be *filtered on* and a static cannot.
Skulk is the same shape: "greater power" reads like a parameter and is not.

**Derived versus printed decides the mechanism on its own.** It is the one
criterion that can overrule every row above it. If the quality must compare
things that an anthem, a pump spell or a `+1/+1` counter can change, a static
filter is not merely awkward — it is forbidden, and the comparison has to live
in the rule that asks it.

**An exemption is not a prohibition with a different filter.** "Can't be blocked
by Humans" and "can't be blocked *except* by artifact creatures and/or black
creatures" look like the same sentence twice, and the static filter language can
say only the first: `blockers` is a positive conjunction, and negating it is not
a matter of adding `not_colors`. Fear, intimidate, horsemanship and shadow are
all exemption-shaped, which is a second, independent reason none of them could
be a `block_restriction` — and it is the one that still applies to keywords
whose quality happens to be printed rather than derived.

## How to read the census

| Status | Means |
|---|---|
| **shipped** | Implemented and tested. Guarded by the drift test below |
| **free** | The DSL can already say it. The Mechanism column names the construction; what is missing is a *card*, not engine work |
| **routed** | The mechanism is decided and the gap is small and named. A cheap `/extend-dsl` job |
| **blocked** | Needs a subsystem the engine does not have. The blocker is named |
| **refused** | A decision already recorded in [rules-coverage.md](rules-coverage.md) |

**Only `shipped` is machine-checked.** `tests/cards/test_keyword_census.py`
asserts that every value in `Keyword` appears here exactly once as a shipped
row, and that every engine name a shipped row claims is real. The other four
statuses are editorial judgements made by reading the DSL, and they can be
wrong — a `free` row is a *claim* that `/author-cards` will either cash or
refuse with a gap record, which is the honest way for it to be settled.

The bar for `free` is deliberately mechanical: the Mechanism column must name
the actual construction in a few words. Anything that needs a paragraph to
justify is `routed`, however likely it looks, because a row marked `free` that
is not free produces exactly the card this repo exists to refuse — one that
looks implemented and does nothing.

Rows marked **†** are not in the source document. They are here because the
engine implements them, or because the family would otherwise have a hole.

## Evergreen keywords

Keywords that appear in almost every set and carry no reminder text.

| Keyword | Status | Mechanism | Engine name |
|---|---|---|---|
| Deathtouch | shipped | `Keyword`, read by `primitives` for lethality | `deathtouch` |
| Defender | shipped | `Keyword`, read by `combat.can_attack` | `defender` |
| Double strike | shipped | `Keyword`, a separate combat damage sub-step | `double_strike` |
| Enchant | shipped | not an ability — a spell-level `target`, attached on resolution | `targets` |
| Equip | shipped | ordinary `sorcery_speed_only` activated ability whose effect is `attach` | `attach` |
| First strike | shipped | `Keyword`, a separate combat damage sub-step | `first_strike` |
| Flash | shipped | `Keyword`, read by `legality` for timing | `flash` |
| Flying | shipped | `Keyword`, read by `combat.can_block` | `flying` |
| Haste | shipped | `Keyword`, read by `combat` and `costs` | `haste` |
| Hexproof † | shipped | `Keyword`, read by `targeting.can_be_targeted` only | `hexproof` |
| Lifelink | shipped | `Keyword`, applied with the damage rather than on the stack | `lifelink` |
| Menace | shipped | `Keyword`, a whole-declaration check in `combat.blocks_valid` | `menace` |
| Protection | shipped | static — parameterised, and read by four separate rules | `protection` |
| Prowess | free | `spell_cast` trigger, filter `not_types: ["Creature"]`, then `pump` | — |
| Reach | shipped | `Keyword`, read by `combat.can_block` | `reach` |
| Trample | shipped | `Keyword`, read by combat damage assignment | `trample` |
| Vigilance | shipped | `Keyword`, suppresses the tap on attack | `vigilance` |
| Ward | free | `becomes_target` trigger with `controller: "opponent"`, then `may` with `player` the caster, a `pay` cost and a `counter` `sid` in the `else` | — |

Ward is the interesting absence. It is evergreen and it has largely replaced
hexproof on new creatures, and the half of it that looked hardest turned out to
be free: routing a cost to a player who does not control the ability and
inverting the outcome is exactly what `may` does with `player`, `pay` and
`else`, which Rhystic Study shipped. What ward still waits on is much smaller
and shared with heroic — a trigger for *becoming the target of* a spell, which
no event covers.

## Keyword actions

Not abilities: instructions naming something a player or the game does.

| Keyword | Status | Mechanism | Engine name |
|---|---|---|---|
| Attach | shipped | op | `attach` |
| Clash | shipped | op, plus a `clash_won` binding an ordinary `if` reads back | `clash` |
| Counter | shipped | op, and it honours `uncounterable` | `counter` |
| Mill † | shipped | op | `mill` |
| Reconfigure | shipped | the equip ability, plus the `unattach` op and an `is_attached` static condition for 702.151d | `unattach` |
| Regeneration | shipped | the `regenerate` op puts a spent-once shield on the permanent; `zones.destroy` spends it | `regenerate` |
| Sacrifice | shipped | op, and also a cost | `sacrifice` |
| Scry | shipped | op | `scry` |
| Surveil † | shipped | op — the source lists it under expansion, but it is a keyword action | `surveil` |
| Tap / untap | shipped | two ops | `tap` |

## Expansion keywords

Keyword abilities that appear in one set, one block, or in expert-level sets.
This is the long tail, and where the build order comes from.

| Keyword | Status | Mechanism | Engine name |
|---|---|---|---|
| Absorb | shipped | the `prevent_damage` static -- parameterised on N, applied per source in `damage_permanent` | `prevent_damage` |
| Adapt | free | activated ability: `if` `counters_on` is 0, then `add_counters` | — |
| Adventure | shipped | `second_face` plus `adventure`: `card_of`'s second branch while it is a spell, then a fifth destination rider that exiles it and a fourth zone it may be cast from | `second_face` |
| Affinity | free | `cost_reduction` already takes `{"count": filter}`; generic-only, clamped at zero, which is exactly affinity | — |
| Afterlife | free | `dies` trigger, then `create_token` | — |
| Aftermath | shipped | the same `second_face`, with `second_face_zone: "graveyard"` — the restriction is *where the half is offered*, and the exile is the same rider adventure uses | `second_face_zone` |
| Alliance | free | `permanent_enters`, `types: ["Creature"]`, `exclude_self` | — |
| Amplify | free | `self_enters` trigger: `reveal` with `count: "any"` and `as`, then `add_counters` off `{"count": {"binding": …}}` | `as` |
| Annihilator | free | `attacks` trigger, then `sacrifice` over `controller: "opponent"` with `chooser: "owner"` — they pick their own | — |
| Aura swap | shipped | the `aura_swap` op -- one op because the incoming Aura has no targeting clause to carry the creature | `aura_swap` |
| Banding | refused | see rules-coverage.md | — |
| Battle cry | free | `attacks` trigger, then `pump` the other attackers | — |
| Bestow | shipped | an alternative cost like evoke, plus the one target list the *rules* supply (`BESTOW_TARGET`), plus a type change in `chars` switched on `attached_to` | `bestow` |
| Blitz | free | dash's shape with a `sacrifice` in the `delay` and a `dies` trigger that draws | — |
| Bloodrush | free | `activated` + `active_zones: ["hand"]` + a `discard_self` cost, then `pump` — the cycling shape | — |
| Bloodthirst | free | `self_enters` trigger, `if` on `cmp` of `damage_taken_this_turn` over `each_opponent`, then `add_counters` | — |
| Bolster | free | `add_counters` over a selector with `extreme: {"of": "toughness", "pick": "least"}` | — |
| Bushido | free | two abilities: the existing `blocks` trigger, and `becomes_blocked` for the other half | — |
| Buyback | free | `kicker` plus `buyback: true` — the rider returns it to hand instead of the graveyard; `kicker_label` names the cost | `buyback` |
| Cascade | shipped | the `cascade` op -- the scan was the missing half; `suspend.cast_for_free` was already the other | `cascade` |
| Casualty | shipped | `additional_cost` with `additional_optional`, then a cast trigger reading `additional_paid` | `additional_cost` |
| Champion | free | `exile` with `until_leaves` (the O-Ring family), an `exists` guard, a `may` with a sacrificing `else`, and a `leaves_battlefield` trigger reading `exiled_with: "self"` | — |
| Changeling | free | `add_subtype` static — confirmed in card-authoring.md | — |
| Channel | free | the cycling shape: `active_zones: ["hand"]` with a `discard_self` cost — identical to bloodrush | — |
| Cipher | shipped | the `encode` op (a fourth destination rider) and `cast_copy`, read back by an `encoded_by` trigger filter | `encode` |
| Connive | shipped | op — the counter counts the cards just discarded, which nothing else can name | `connive` |
| Conspire | free | `tap_permanents` as an additional cost, then `copy_spell` | `copy_spell` |
| Convoke | free | `pay_generic_with: "tap_creatures"` — one cast line per number convoked. Generic only; the colour half is a documented simplification | `pay_generic_with` |
| Coven | free | condition `cmp` on `{"distinct": {"of": "power"}}` over creatures you control | `distinct` |
| Crew | shipped | `tap_permanents` with a `total_power`, summed off **derived** power; *Vehicle* is free text | — |
| Cumulative upkeep | shipped | `upkeep` trigger, `add_counters`, then `may` `pay` with a `times` multiplier off the counter count | — |
| Cycling | shipped | `activated` + `active_zones: ["hand"]` + a `discard_self` cost | — |
| Dash | free | `evoke` with an `evoke_label`, then a `self_enters` trigger on `evoked`: `grant_keyword` haste and a `delay`ed `return_to_hand` | — |
| Daybound / nightbound | refused | day/night is a designated-game-state mechanic; see rules-coverage.md | — |
| Delve | free | `pay_generic_with: "exile_from_graveyard"` — convoke's shape with a different currency | `pay_generic_with` |
| Detain | free | the `detain` op — one word, three restrictions, cleared by the *detaining* player's untap step | `detain` |
| Devour | free | `self_enters` trigger: `sacrifice` with `count: "any"` and `as`, then `add_counters` off the recorded set | `as` |
| Disturb | shipped | `graveyard_cost` plus `graveyard_cast_transformed` -- the card is the back face from the moment it is cast | `graveyard_cast_transformed` |
| Dredge | shipped | the `dredge` card field, offered by `replacements.draw` -- it replaces the draw rather than adding to it | `dredge` |
| Echo | free | `upkeep` trigger with an intervening-if `{"not": {"has_flag": …}}`, `set_flag`, then `may` `pay` with a sacrifice `else` | `set_flag` |
| Embalm | shipped | activated from the **graveyard**, paying by exiling its own card, producing a token copy with an "except" clause | — |
| Emerge | shipped | card-level field; one cast line per sacrificeable creature | `emerge` |
| Entwine | shipped | `kicker` for the price, plus `all_if` on `choose_mode` for the both | `kicker` |
| Epic | shipped | `PlayerState.epic_source` gates `_cast_actions`, and the upkeep copies through `put_copy_on_stack` | `epic` |
| Escape | free | `graveyard_cost` with an `exile_from_graveyard` cost, and `graveyard_cast: "graveyard"` so it comes back | — |
| Evoke | shipped | card-level field, and the `evoked` condition its sacrifice trigger reads | `evoke` |
| Evolve | free | `permanent_enters` with a condition comparing `{"binding": "subject"}` against `{"self": true}` | — |
| Exalted | free | `attacks` trigger, condition `cmp` on `count` of attacking creatures you control equals 1 | — |
| Exert | free | `attacks` trigger, `may`, then `skip_untap` and whatever the card does — cashed by `test_exert.py` | — |
| Exploit | free | `self_enters` trigger, `may`, then `sacrifice` and whatever the card does — cashed by `test_exploit_and_bloodrush.py` | — |
| Explore | shipped | op — the branch reads the card just revealed, which no condition can name | `explore` |
| Extort | free | `spell_cast` trigger, then `may` with `pay`, then `lose_life` on each opponent and `gain_life` | — |
| Fabricate | free | `self_enters` trigger, then `choose_mode` between `add_counters` and `create_token` | — |
| Fading | free | `upkeep` trigger with an `if` on `counters_on` — "if you can't" is an ordinary comparison, and the sacrifice is the `else` | — |
| Fateseal | free | `scry` with `player` naming whose library and `chooser` naming who decides | — |
| Fear | shipped | `Keyword`, read in `combat.can_block` against the blocker's **derived** types and colors | `fear` |
| Flanking | free | `becomes_blocked` trigger, then `pump` over `{"blocking": {"binding": "self"}}` filtered `not_keywords` | — |
| Flashback | shipped | card-level field; an alternative cost offered only from the owner's graveyard, exiling instead of returning | `flashback` |
| Flip | free | `back_face` plus the `transform` op, both shipped for Bloodline Keeper — 711 is a DFC whose difference is which way the cardboard turns | `back_face` |
| Forecast | shipped | `active_zones: ["hand"]` plus `activate_steps` and `once_each_turn`, which is the fourth way to satisfy the guard | — |
| Foretell | shipped | suspend's special action, shared: `{2}` to exile it, then a cast from exile at the `foretell` price on a later turn | `foretell` |
| Frenzy | free | `attacks_unblocked` trigger, then `pump` | — |
| Graft | free | `self_enters_with_counters`, then `permanent_enters` + `may` + `move_counters` onto the binding | `move_counters` |
| Gravestorm | free | storm's shape, counting `cards_to_graveyard_this_turn` instead | `copy_spell` |
| Haunt | shipped | the `haunt` op and a `haunted_by: "self"` trigger filter -- the exile link reversed, read off the ability source | `haunt` |
| Hideaway | shipped | the `hideaway` op writes the `exiled_by` link and `revealed_to`; `play_exiled` is the permission, reading it back | `hideaway` |
| Horsemanship | shipped | `Keyword`, read in `combat.can_block`: the blocker must carry it too | `horsemanship` |
| Imprint | free | `exile` with `until_leaves` writes the link; `{"zone": "exile", "controller": "any", "exiled_with": "self"}` reads it back | — |
| Indestructible | shipped | `Keyword`, read by the lethal-damage state-based action | `indestructible` |
| Infect † | shipped | `Keyword`, read by `damage_permanent` and `damage_player` -- wither's counters, plus poison to players | `infect` |
| Inspired | free | `becomes_untapped` trigger — the event existed; the untap *step* now says which permanents it untapped | — |
| Intimidate † | shipped | `Keyword`, comparing the two creatures' **derived** colors in `combat.can_block`, with an artifact escape | `intimidate` |
| Investigate | free | `create_token` naming a Clue — a token whose own ability is `{2}`, sacrifice self, `draw`. Bygone Bishop is the witness | — |
| Jump-start | free | `graveyard_cost` repeating the printed mana plus `discard: 1`; the exile rider is the default | — |
| Kicker | shipped | card-level field, and the `kicked` condition, readable on the object after resolution | `kicker` |
| Landwalk — plainswalk | shipped | `Keyword`, read by `combat.can_block` against the defender's board | `plainswalk` |
| Landwalk — islandwalk | shipped | `Keyword` | `islandwalk` |
| Landwalk — swampwalk | shipped | `Keyword` | `swampwalk` |
| Landwalk — mountainwalk | shipped | `Keyword` | `mountainwalk` |
| Landwalk — forestwalk | shipped | `Keyword` | `forestwalk` |
| Landwalk — nonbasic † | shipped | `Keyword`, and **not** a sixth `LANDWALK_SUBTYPE` row: the test is a supertype the land must lack | `nonbasic_landwalk` |
| Level up | free | a level counter, plus `set_pt` / `grant_keyword` statics whose `condition` is an `all` of two `counters` comparisons -- a band | `set_pt` |
| Living weapon | free | `self_enters` trigger, `create_token`, then `attach` | — |
| Madness | shipped | the `madness` card field: the discard exiles instead, and the cast is offered from there | `madness` |
| Manifest | shipped | the `manifest` op, plus the face-down shell in `chars` and the turn-face-up activation | `manifest` |
| Meld | shipped | the `meld` op: mutate's merged permanent with the pair fixed by `melds_with` and the result a third card entry, `melds_into` | `meld` |
| Mentor | free | `attacks` trigger, target filter `power` `{"op": "<", "value": {"power_of": {"self": true}}}` | — |
| Miracle | shipped | the `miracle` card field, read off `cards_drawn_this_turn` *before* the draw bumps it | `miracle` |
| Modular | free | `self_enters_with_counters`, then a `dies` trigger with `move_counters` and `{"counters_had": "+1/+1"}` | `move_counters` |
| Monstrosity | shipped | op, plus the one-way flag and the `becomes_monstrous` trigger | `monstrosity` |
| Morph / megamorph | shipped | a face-down cast line at a fixed `{3}`, and `morph` / `morph_counter` for turning up | `morph` |
| Mutate | shipped | an alternative cost with `MUTATE_TARGET`, and a **synthesised `CardDef`** written onto the host at `card_of` — the top card carrying the abilities of everything under it | `mutate` |
| Ninjutsu | shipped | a `blocked` selector key on the bounce cost, and `attacking` on `put_onto_battlefield` | — |
| Offering | free | `emerge` plus `emerge_subtype`, and the `flash` keyword for "any time you could cast an instant" | `emerge_subtype` |
| Overload | shipped | card-level field: a third cast line with **no targets**, and an `{"overloaded": true}` branch | `overload` |
| Partner † | shipped | an **inert** `Keyword` — deck construction only, and the engine is handed a finished deck | `partner` |
| Persist | free | `dies` trigger with a `counters_had` condition, then `return_from_graveyard` with `counters` | — |
| Phasing | refused | phasing; see rules-coverage.md | — |
| Poisonous | free | `deals_combat_damage_to_player` trigger, then `add_poison`; ten is lethal in the state-based pass | `add_poison` |
| Populate | free | `copy_permanent` over a selector filtered to `is_token` | — |
| Proliferate | free | the `proliferate` op — the kinds were always enumerable; `GameObject.counters` is a dict keyed by kind | `proliferate` |
| Provoke | free | `attacks` trigger, then `untap` and the `must_block` op — the block-requirement mirror of `must_attack` | `must_block` |
| Prowl | free | `alternative_cost` with a `{"combat_damage_by": [...]}` condition, off a seventh ledger tally | — |
| Rampage | free | `becomes_blocked` trigger, then `pump` by `times` of N and `blockers` minus one | — |
| Rebound | shipped | card-level field: the exile rider on resolution, then suspend's free cast at your next upkeep | `rebound` |
| Recover | free | `creature_dies` trigger, `may` with `pay`, `return_from_graveyard` on yes and `exile` in the `else` | — |
| Reinforce | free | activated from hand with a `discard_self` cost, then `add_counters` — the cycling shape | — |
| Renown | free | `deals_combat_damage_to_player` trigger, gated on `not has_flag`, then `add_counters` and `set_flag` | `set_flag` |
| Replicate | shipped | `additional_cost` with both modifiers -- one cast line per number of times paid | `additional_cost` |
| Retrace | shipped | card-level field; casting from the graveyard, discarding a land | `retrace` |
| Riot | free | `self_enters` + `choose_mode`; the haste half needs `grant_keyword` with `duration: "permanent"` | — |
| Ripple | shipped | the `ripple` op -- cascade's shape at a fixed depth, matched on the source's own name | `ripple` |
| Scavenge | free | activated from the graveyard with an exile cost, then `add_counters` | — |
| Shadow | shipped | `Keyword`, compared **symmetrically** in `combat.can_block` — it restricts blocking as well as being blocked | `shadow` |
| Shroud | shipped | `Keyword`, read by `targeting.can_be_targeted` only — stops the controller too | `shroud` |
| Skulk † | shipped | `Keyword`, compared on **derived** power inside `combat.can_block` | `skulk` |
| Soulbond | shipped | a symmetric `paired_with` field, the `pair` op, and the `paired` / `paired_with_source` static filters | `pair` |
| Soulshift | free | `dies` trigger, then `return_from_graveyard` filtered by subtype and `mana_value` | — |
| Spectacle | free | `alternative_cost` with a condition on `life_lost_this_turn` over `each_opponent` | — |
| Splice | shipped | a card-level `splice` cost offered in `_cast`, recorded on the `StackItem` and run after the host's effects | `splice` |
| Split second | free | the `split_second` card field — priority is *not* suppressed; casting and non-mana activations are withheld while it is on the stack | `split_second` |
| Storm | free | `spell_cast` trigger on the stack, then `copy_spell` with `spells_cast_this_turn` minus one | `copy_spell` |
| Sunburst | free | `self_enters` trigger, then `add_counters` off `{"colors_of_mana_spent": true}` | — |
| Support | free | `add_counters` over a target spec with `count` and `optional` | — |
| Suspend | shipped | card-level field, its own module, and haste on what arrives | `suspend` |
| Totem armor | shipped | `Keyword` on the **Aura**, read by `zones.destroy` -- the Aura is destroyed instead | `totem_armor` |
| Transfigure | free | activated, sorcery speed, cost sacrifices self, then `search_library` on `mana_value` | — |
| Transform | shipped | op — two `CardDef`s behind one `GameObject`, and `card_of` picks the face | `transform` |
| Transmute | free | activated from hand with a `discard_self` cost, then `search_library` | — |
| Tribute | free | one `may` with `player: "opponent"` and an `else` — the shape was not merely reachable, it was already spelled | — |
| Undying | free | the mirror of persist: the same shape reading `+1/+1` instead | — |
| Unearth | free | activated from the graveyard: `put_onto_battlefield` self, `grant_keyword` haste `permanent`, then a `delay`ed `exile` | — |
| Unleash | free | `self_enters_with_counters`, plus a `cant_block` static conditioned on `counters` | `cant_block` |
| Wither | shipped | `Keyword`, read by `damage_permanent` -- the counters land instead of the damage mark | `wither` |

## Ability words

Italic flavour with no rules meaning — rule 207.2c. The ability after the word
is ordinary, which is why most of this table is `free`.

| Keyword | Status | Mechanism | Engine name |
|---|---|---|---|
| Addendum | free | condition `is_your_turn`, which is as close as the engine gets and is right for a sorcery-speed clause | — |
| Battalion | free | `attacks` trigger, condition `cmp` on `count` of attacking creatures you control | — |
| Chroma | free | value `{"mana_symbols": {"of": …}}`, in both the effect and static languages | `mana_symbols` |
| Domain | free | value `{"distinct": {"of": "basic_land_type"}}` over lands you control | `distinct` |
| Enrage | free | the `dealt_damage` trigger, with `{"binding": "amount"}` for "that much" | — |
| Fateful hour | free | condition `cmp` on `life_of` `"you"` | — |
| Ferocious | free | condition `exists` with `power` `>=` 4 | — |
| Grandeur | free | activated from hand, cost `discard_selector` by `name` | — |
| Hellbent | free | condition `cmp` on `cards_in_hand` equals 0 | — |
| Heroic | free | `becomes_target` trigger with `controller: "you"`, then whatever the card does | — |
| Join forces | shipped | the `join_forces` op -- one unit at a time, in turn order from the caster | `join_forces` |
| Kinship | free | `upkeep` trigger, `snapshot` over `{"zone": "library"}` (which binds the top card), then `exists` with `shares_a_type_with: "self"` | `snapshot` |
| Landfall | free | `permanent_enters` with `types: ["Land"]` — **not** `land_played`, which is narrower | — |
| Metalcraft | free | condition `cmp` on `count` of artifacts you control | — |
| Morbid | free | condition `cmp` on `creatures_died_this_turn` over `all` — the per-turn ledger shipped | — |
| Radiance | free | `snapshot` the target, then a selector with `shares_a_color_with` and `exclude_binding` | `shares_a_color_with` |
| Raid | free | condition `cmp` on `attacked_this_turn` over `you` — the per-turn ledger shipped | — |
| Rally | free | `permanent_enters` with `subtypes: ["Ally"]` | — |
| Sweep | free | cost `return_to_hand` over a selector by `subtypes`, then a value off `count` | — |
| Threshold | free | condition `cmp` on `count` of `zone: "graveyard"`, `controller: "you"` | — |
| Undergrowth | free | value `count` of creatures in your graveyard | — |

## What the census says

**Nine rows are blocked and five refused. The other 169 are shipped or free.**

The single most useful finding, made over and over, is that **`blocked` was
usually a routing error rather than a size estimate**. Eleven keywords filed
against a subsystem turned out to need something that already existed, or
something small in a place nobody had looked:

| filed as | what it actually was |
|---|---|
| wither, infect — "the whitelist has no damage form" | a keyword read by `damage_permanent`, where deathtouch already sits |
| regeneration, totem armor — "a destruction replacement" | a check in `zones.destroy`, the one function every destruction goes through |
| dredge, madness, miracle — "the whitelist has no draw/discard form" | a **call-graph** change: `turn.begin_step` already ran through `Game._run`, so only `_draw_step` beneath it could not suspend |
| cascade, ripple — "free casts off a library scan" | the free cast was `suspend.cast_for_free`; only the scan was missing |
| foretell — "suspend is the nearest shape" | suspend is the *same* shape, down to the `ActionKind` |
| champion, imprint — "exile tied to a permanent" | `exile` with `until_leaves`, shipped for Oblivion Ring, read from each end |
| level up — "a characteristic-defining subsystem" | `set_pt` (which *replaces* P/T) plus a band written as `all` over two `counters` comparisons |

**Before building a subsystem for a keyword, re-derive the keyword from its
printed text.** Twice the census named a subsystem that the printed line did not
actually require, and once (dredge) it named the right cluster for the wrong
reason — the obstacle was not the replacement whitelist but the call graph
above it.

### What is genuinely left

**Nothing.** The `blocked` column is empty.

Every one of the twenty-five rows that started there has shipped, and the
pattern held to the last one: **`blocked` was a routing error, not a size
estimate.** The final four were the cluster the census called "a second castable
face", and it was three different problems wearing one name:

| keyword | what the census said | what it was |
|---|---|---|
| adventure, aftermath | one cluster, needing the authoring pipeline | one cluster, needing `card_of` — which `back_face` had already built |
| bestow | the same cluster | not a second *spell* at all: one spell landing as two different permanents, so `chars` rather than `card_of` |
| mutate | "the only genuine subsystem left" | one `CardDef` **synthesised at merge time**, precisely *because* `card_of` is a single choke point |

Mutate is the sharpest version of the finding. The census's argument was "a
`GameObject` is one card, and every choke point the other reversals leaned on
assumes that" — and the first half is true while the conclusion is backwards. A
merged permanent is one `CardDef`: the card on top, carrying the abilities of
everything under it, built once and stored on the object. `chars`, legality,
triggers, the stack's ability lookup and the serializer all read it through
`card_of` and none of them changed. The subsystem the census feared was the
*alternative* implementation — a list of cards per permanent, and every reader
taught to walk it.

What remains genuinely open is the **authoring pipeline**, not the engine: it
emits one card entry per answer file, so a two-faced card is two hand-written
entries linked by id, the way `bloodline_keeper` / `lord_of_lineage` already
are. That is the `split-cards-fuse` gap record, and **fuse** itself is a
different shape again — one spell made of two faces, where `card_of` answers
with exactly one.

### The refused

`refused` is a recorded decision rather than a difficulty, and **three have been
reversed**:

- **Regeneration** was refused as "a destruction-replacement shield" and now
  ships, because `zones.destroy` is a single choke point.
- **Meld** was refused for the same words as flip — "a card-wide designated
  state the engine has no place to keep" — and by the time mutate shipped, the
  place existed. It is the merged permanent again, with the pair fixed by the
  card rather than chosen by the caster, and one thing genuinely harder: 701.37c
  exiles both cards and returns them melded, so the melded permanent *enters*.
- **Flip** was refused as needing "a card-wide designated state the engine has
  no place to keep", and needed *nothing*. Rule 711 is `back_face` plus the
  `transform` op, both of which shipped for Bloodline Keeper, and every
  difference between a flip card and a transforming double-faced one is a
  difference about **cardboard** — which way you turn it. It is now `free`, with
  `tests/unit/test_flip.py` as the witness, because a status nobody checked is a
  status nobody should trust.

The remaining three hold for reasons the reversals did not have. Banding and
phasing change how combat and the untap step work for *every* permanent in the
game; daybound / nightbound needs a game-wide designated state. They belong in
[rules-coverage.md](rules-coverage.md) and should be re-argued there rather than
reclassified here.

## Suggested build order

There is no engine work left in this census. The next thing worth building is
the **authoring pipeline's** two-entries-from-one-answer, which is what
`split-cards-fuse` is really asking for, and after that **fuse** — the one
printed shape `card_of` cannot answer, because it is a single spell made of two
faces at once.

Cross-check [unsupported-cards.md](unsupported-cards.md) first: where a
capability already has gap records, those cards are the real specification.
`/extend-dsl` rule 1 still applies: **one capability per run.**

## Provenance

The census is the supplied source document, entry for entry, plus the rows
marked **†**: hexproof, skulk, intimidate and partner, which the engine
implements and the source omits; mill and surveil, which are keyword actions the
engine already has as ops; and infect, which the source discusses inside the
poisonous entry rather than as one of its own. Landwalk is expanded into its six
keywords — the five basic types plus nonbasic — because that is how the engine
models it, and the reason why is the first corollary above.

Statuses were assigned by reading `reference()` in
`src/automtg/cards/authoring/packet.py`, which derives every vocabulary list
from the enums rather than restating them, and is the single best oracle for
what the DSL currently accepts.
