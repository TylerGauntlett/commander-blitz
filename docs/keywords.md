# Keywords, and where each one lands

The engine implements 27 keywords. Every one arrived the same way: a card in the
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
| Absorb | blocked | damage prevention, which the engine models only as protection | — |
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
| Casualty | routed | `copy_spell` ships; what is left is an additional cost that sacrifices a creature of a chosen power | — |
| Champion | blocked | exile-and-return tied to the championing permanent leaving | — |
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
| Disturb | routed | `transform` and `flashback` both ship; needs the graveyard cast to arrive on the **back** face | — |
| Dredge | blocked | replaces a draw, and the replacement whitelist has no draw form | — |
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
| Forecast | routed | an activated ability from hand that reveals rather than discarding — and so cannot use the cycling guard | — |
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
| Madness | blocked | replaces a discard, and the replacement whitelist has no discard form | — |
| Manifest | blocked | face-down creatures | — |
| Meld | refused | melding; see rules-coverage.md | — |
| Mentor | free | `attacks` trigger, target filter `power` `{"op": "<", "value": {"power_of": {"self": true}}}` | — |
| Miracle | blocked | replaces the first draw of a turn, and needs the draw's ordinality | — |
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
| Replicate | routed | `copy_spell` ships; what is left is an additional cost paid *any number of times*, which no cost kind repeats | — |
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
| Join forces | routed | mana contributed by several players; every cost is paid by one | — |
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

**The largest single finding is that ability words are nearly free.** Twelve of
the twenty-one above need no engine work at all, and neither do a dozen entries
in the expansion table — adapt, affinity, afterlife, alliance, battle cry,
extort, fabricate, investigate, living weapon, populate, recover, reinforce,
scavenge, soulshift, support, transfigure, transmute. Those are `/author-cards`
jobs, not `/extend-dsl` jobs,
and nothing in the demand-driven report would ever have surfaced them: a
capability with no gap record does not appear there, and a capability that is
already expressible never gets a gap record written for it.

**The evasion family is now closed.** Fear, intimidate, horsemanship, shadow and
nonbasic landwalk shipped together, because they are one capability and not five
— every one is a question `combat.can_block` asks of `chars` on both creatures,
and the rest of `can_block` was already the answer. What is left of combat is
not evasion at all: flanking, rampage, bushido, frenzy and provoke each wanted a
*trigger event* the engine did not have ("becomes blocked", "attacks and isn't
blocked"), which is a different tier of work with frontend consequences. Four of
those five have since shipped as `becomes_blocked` and `attacks_unblocked` —
one capability rather than four, because both events are decided at the same
instant and neither is knowable a moment earlier. Provoke is the one left, and
it is not a trigger at all: it is a block *requirement*, the mirror of
`must_attack`.

**The unshipped entries cluster, and the clusters are small.** Nearly everything
still outstanding waits on one of six things:

| Blocker | Waiting on it |
|---|---|
| ~~A **per-turn ledger**~~ — shipped as `GameState.turn_ledger`. Morbid, raid and bloodthirst are now `free`; the other four turned out to want a *second* thing each | ~~morbid, raid, bloodthirst~~, spectacle and prowl (a cost gated on a condition), storm and gravestorm (spell copying) |
| ~~**Casting from the graveyard**~~ — generalised as `graveyard_cost` plus a `graveyard_cast` destination. Escape needed one bit; jump-start needed nothing | ~~escape, jump-start~~, unearth (an *activated* ability, not a cast), disturb (arrives on its back face) |
| ~~**Spell copying**~~ — shipped as the `copy_spell` op | ~~conspire, storm, gravestorm~~; casualty and replicate want an additional cost, ripple a library scan |
| **More replacement forms** — draw, discard, damage, destruction | dredge, madness, wither, miracle, totem armor, regeneration |
| **Face-down and multi-faced cards** | morph, manifest, adventure, aftermath, bestow, mutate, meld |
| ~~A **"becomes the target of" trigger**~~ — shipped as `becomes_target`, and it cleared the cluster outright | ~~heroic, ward~~ |

A per-turn ledger is one piece of state and unblocks seven mechanics. That is
the shape of argument this page exists to make available, and it is not visible
one gap record at a time.

Two of those six have since had their first member shipped, and the shipping
moved the rest of the cluster from `blocked` to `routed` rather than clearing
it: `flashback` and `embalm` proved casting from the graveyard for one cost each,
and `transform` proved two faces behind one `GameObject`. A cluster whose
foundation exists is a vocabulary gap; that is the whole difference between the
two statuses.

## Suggested build order

Cheapness first, breadth second. Cross-check each against
[unsupported-cards.md](unsupported-cards.md) before starting — where a
capability already has gap records, those cards are the real specification, and
`/extend-dsl` rule 1 still applies: **one capability per run**.

1. **Harvest the free rows.** No engine work. Each is an `/author-cards` run
   that will either produce a card or produce a gap record correcting this page,
   and both outcomes are useful.
2. **A per-turn ledger.** One piece of state, cleared at cleanup, exposed as
   conditions. Seven mechanics, and it is the prerequisite most others assume.
   Damage history and the draw tally are the two shapes to copy, and they differ
   in *when they clear* — read why before adding a third.
3. **The missing trigger events.** "Becomes blocked", "becomes untapped",
   "becomes the target of", and the block-requirement mirror of `must_attack`.
   The only tier of the six here with frontend consequences.
4. **Costs and casting.** Starting with **`unless_pays`** — ward is evergreen,
   so it compounds with every future set, and the demand side already has
   records for it — then the graveyard-cast and from-hand generalisations, the
   mana-paying cost kinds, and the alternative costs with delayed halves.
5. **Counters.** ETB counts from a value expression, counter movement, the
   dies-and-return pair, and the derived-power comparisons.
6. **More replacement forms.** The whitelist is deliberate and widening it is a
   design decision, not just work — read [adr/0001-layers-lite.md](adr/0001-layers-lite.md)
   first.
7. **Spell copying**, and then the long tail of one-off ops.

Face-down and multi-faced cards are last on purpose: they are the only cluster
that is a genuine rules subsystem rather than a missing vocabulary item, and
`/extend-dsl` rule 4 says to stop and report rather than start one inside a
card-unblocking run. `transform` shipping does not change that — it built the
`card_of` choke point the rest of the cluster needs, which is the foundation and
not the subsystem.

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
