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
| Adventure | blocked | split cards — one card, two castable halves | — |
| Affinity | free | `cost_reduction` already takes `{"count": filter}`; generic-only, clamped at zero, which is exactly affinity | — |
| Afterlife | free | `dies` trigger, then `create_token` | — |
| Aftermath | blocked | split cards | — |
| Alliance | free | `permanent_enters`, `types: ["Creature"]`, `exclude_self` | — |
| Amplify | free | `self_enters` trigger: `reveal` with `count: "any"` and `as`, then `add_counters` off `{"count": {"binding": …}}` | `as` |
| Annihilator | free | `attacks` trigger, then `sacrifice` over `controller: "opponent"` with `chooser: "owner"` — they pick their own | — |
| Aura swap | blocked | swapping an attached aura with one in hand; one card in the game | — |
| Banding | refused | see rules-coverage.md | — |
| Battle cry | free | `attacks` trigger, then `pump` the other attackers | — |
| Bestow | blocked | a creature cast as an aura — one card in two zones' worth of types | — |
| Blitz | free | dash's shape with a `sacrifice` in the `delay` and a `dies` trigger that draws | — |
| Bloodrush | free | `activated` + `active_zones: ["hand"]` + a `discard_self` cost, then `pump` — the cycling shape | — |
| Bloodthirst | free | `self_enters` trigger, `if` on `cmp` of `damage_taken_this_turn` over `each_opponent`, then `add_counters` | — |
| Bolster | free | `add_counters` over a selector with `extreme: {"of": "toughness", "pick": "least"}` | — |
| Bushido | free | two abilities: the existing `blocks` trigger, and `becomes_blocked` for the other half | — |
| Buyback | free | `kicker` plus `buyback: true` — the rider returns it to hand instead of the graveyard; `kicker_label` names the cost | `buyback` |
| Cascade | blocked | cast a card from exile without paying its cost, chosen by a library scan | — |
| Casualty | shipped | `additional_cost` with `additional_optional`, then a cast trigger reading `additional_paid` | `additional_cost` |
| Champion | free | `exile` with `until_leaves` (the O-Ring family), an `exists` guard, a `may` with a sacrificing `else`, and a `leaves_battlefield` trigger reading `exiled_with: "self"` | — |
| Changeling | free | `add_subtype` static — confirmed in card-authoring.md | — |
| Channel | free | the cycling shape: `active_zones: ["hand"]` with a `discard_self` cost — identical to bloodrush | — |
| Cipher | blocked | encoding a spell onto a creature and recasting it from exile | — |
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
| Epic | blocked | a lasting restriction on casting, plus a copy each upkeep | — |
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
| Flip | refused | flip cards; see rules-coverage.md | — |
| Forecast | shipped | `active_zones: ["hand"]` plus `activate_steps` and `once_each_turn`, which is the fourth way to satisfy the guard | — |
| Foretell | blocked | a special action putting a card in exile to be cast later; suspend is the nearest shape | — |
| Frenzy | free | `attacks_unblocked` trigger, then `pump` | — |
| Graft | free | `self_enters_with_counters`, then `permanent_enters` + `may` + `move_counters` onto the binding | `move_counters` |
| Gravestorm | free | storm's shape, counting `cards_to_graveyard_this_turn` instead | `copy_spell` |
| Haunt | blocked | exile attached to a creature, with a second trigger on its death | — |
| Hideaway | blocked | exiling a card face down and casting it later from under a permanent | — |
| Horsemanship | shipped | `Keyword`, read in `combat.can_block`: the blocker must carry it too | `horsemanship` |
| Imprint | blocked | exile attached to a permanent, with abilities reading the exiled card | — |
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
| Level up | blocked | levels are a characteristic-defining subsystem, not counters with a static | — |
| Living weapon | free | `self_enters` trigger, `create_token`, then `attach` | — |
| Madness | shipped | the `madness` card field: the discard exiles instead, and the cast is offered from there | `madness` |
| Manifest | blocked | face-down creatures | — |
| Meld | refused | melding; see rules-coverage.md | — |
| Mentor | free | `attacks` trigger, target filter `power` `{"op": "<", "value": {"power_of": {"self": true}}}` | — |
| Miracle | shipped | the `miracle` card field, read off `cards_drawn_this_turn` *before* the draw bumps it | `miracle` |
| Modular | free | `self_enters_with_counters`, then a `dies` trigger with `move_counters` and `{"counters_had": "+1/+1"}` | `move_counters` |
| Monstrosity | shipped | op, plus the one-way flag and the `becomes_monstrous` trigger | `monstrosity` |
| Morph / megamorph | blocked | face-down creatures | — |
| Mutate | blocked | stacked permanents with merged abilities | — |
| Ninjutsu | blocked | returning an unblocked attacker and putting a creature in attacking, without casting | — |
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
| Ripple | blocked | free casts off a library scan, retriggering itself | — |
| Scavenge | free | activated from the graveyard with an exile cost, then `add_counters` | — |
| Shadow | shipped | `Keyword`, compared **symmetrically** in `combat.can_block` — it restricts blocking as well as being blocked | `shadow` |
| Shroud | shipped | `Keyword`, read by `targeting.can_be_targeted` only — stops the controller too | `shroud` |
| Skulk † | shipped | `Keyword`, compared on **derived** power inside `combat.can_block` | `skulk` |
| Soulbond | blocked | a paired-permanent relationship with no representation | — |
| Soulshift | free | `dies` trigger, then `return_from_graveyard` filtered by subtype and `mana_value` | — |
| Spectacle | free | `alternative_cost` with a condition on `life_lost_this_turn` over `each_opponent` | — |
| Splice | blocked | adding one card's effects to another spell as it is cast | — |
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

**The routed column is empty.** Every keyword whose mechanism was decided and
whose gap was small and named has been built. What is left is 22 `blocked` rows
and 5 `refused` ones, and the useful thing to say about them is that they are
**four subsystems and a short tail**, not twenty-seven jobs.

### The four subsystems

Each is a genuine rules capability the engine does not have. None is reachable
inside a card-unblocking run, and `/extend-dsl` rule 4 says to stop and report
rather than start one — which is what this section is.

| Subsystem | Keywords waiting on it | What it actually needs |
|---|---|---|
| **Face-down permanents** | morph / megamorph, manifest, (and cloak, from the demand side) | a permanent whose characteristics are a 2/2 shell over a real card, a special action to turn it up at any priority, and a `card_of` that answers the shell rather than the card. `transform` built the `card_of` choke point; this is the second thing to go through it |
| **A second castable face** | adventure, aftermath, bestow, mutate, meld, flip | one card, two things you may cast, differing in cost, type line and where the card goes afterwards. `back_face` is a *face you turn over*, not a second castable card, and the authoring pipeline emits one card entry per answer file |
| **Replacing a draw or a discard** | dredge, madness, miracle | the decision has to be asked **inside** `draw_cards` / `discard_cards`, which are called from the turn structure and are not generators. That is the whole of it: the replacement whitelist is not the obstacle, the call graph is |
| **Levels** | level up | a characteristic-defining subsystem, not counters plus a static: a level creature's P/T and abilities are read off a band, and the bands are part of the card |

The third is the one worth arguing about, because it looks like a whitelist
entry and is not. `replacements` covers what happens as a permanent **enters the
battlefield**, and every one of its members is applied synchronously with nothing
to ask. Dredge and madness both ask a player a question at the moment of the
replacement, so the primitives that draw and discard would have to become
generators — and so would `turn._draw_step` and the cleanup discard above them.

That the whitelist was the *wrong* diagnosis for four keywords is now on record:
wither, infect, regeneration and totem armor were all filed against it, and all
four turned out to belong at a choke point that already existed
(`damage_permanent`, `zones.destroy`).

### The short tail

Seven keywords that are neither a subsystem nor small. Each needs one named
thing, and none of them shares it with another:

| Keyword | The one thing |
|---|---|
| Cascade, Ripple | cast a card from **exile** chosen by a library scan. `suspend.cast_for_free` is most of it; the scan and the "rest on the bottom" are not |
| Foretell | a special action putting a card in exile face down, plus a cast from there at a different cost. Suspend is the nearest shape and `ActionKind.SUSPEND` the nearest action |
| Haunt, Imprint | an exile link pointing at *another* object, read back by a trigger filter. `exiled_with` points the other way -- at the exiler -- and champion showed that direction is already enough for a whole family |
| Hideaway | face-down exile **plus** play-from-exile, so it waits on two things rather than one |
| Cipher, Splice, Epic, Ninjutsu, Aura swap, Soulbond | one bespoke mechanism each, with one or two printed cards behind them |

### The five refused

`refused` is a recorded decision rather than a difficulty, and one of them has
since been reversed: **regeneration** was refused as "a destruction-replacement
shield" and is now shipped, because `zones.destroy` is a single choke point and
the shield is six lines through it.

The remaining five are refused for reasons that still hold, and all five are
*designated-game-state* or *combat-structure* mechanics rather than card
vocabulary: banding and phasing change how combat and the untap step work for
every permanent in the game; daybound / nightbound, flip and meld each need a
game-wide or card-wide state the engine has no place to keep. They are recorded
in [rules-coverage.md](rules-coverage.md) and should be re-argued there rather
than reclassified here.

## Suggested build order

Cheapness first, breadth second — and after this sequence the cheap work is
done, so what is left is ordered by **how many keywords one subsystem unblocks**.

1. **Replacing a draw and a discard.** Three keywords (dredge, madness,
   miracle), and the smallest of the four subsystems: it is a call-graph change,
   not a new rules concept. Do it first because the other three are much larger
   and this one is bounded.
2. **Face-down permanents.** Three keywords plus a demand-side card, and it goes
   through the `card_of` choke point `transform` already built.
3. **A second castable face.** Six keywords, and the only one that also needs
   the *authoring pipeline* to emit two card entries from one answer.
4. **The short tail**, in whatever order the demand side asks for it. Cascade
   and ripple share a library scan; haunt and imprint share a reversed exile
   link; the rest are one-offs.
5. **Levels**, last, for the reason face-down cards used to be last: it is a
   characteristic-defining subsystem and nothing else needs it.

Before starting any of them, cross-check
[unsupported-cards.md](unsupported-cards.md) — where a capability already has
gap records, those cards are the real specification. `/extend-dsl` rule 1 still
applies: **one capability per run.**

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
