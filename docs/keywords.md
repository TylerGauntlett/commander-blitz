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
| Ward | blocked | needs `unless_pays` — the same missing capability as Rhystic Study | — |

Ward is the interesting absence. It is evergreen, it has largely replaced
hexproof on new creatures, and it is blocked on a capability that already has
gap records filed against it under a different name. It routes a cost to a
player who does not control the ability and inverts the outcome, and `may` — the
only optional-effect op — asks the controller and attaches no cost.

## Keyword actions

Not abilities: instructions naming something a player or the game does.

| Keyword | Status | Mechanism | Engine name |
|---|---|---|---|
| Attach | shipped | op | `attach` |
| Clash | routed | `reveal` exists; needs a cross-player comparison of the revealed cards | — |
| Counter | shipped | op, and it honours `uncounterable` | `counter` |
| Mill † | shipped | op | `mill` |
| Reconfigure | routed | needs *unattach*, which the attach model has no notion of — equipment may only move | — |
| Regeneration | refused | a destruction-replacement shield; see rules-coverage.md | — |
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
| Amplify | routed | `self_enters_with_counters` takes a fixed integer, not a value expression | — |
| Annihilator | routed | `attacks` trigger; needs a sacrifice chosen by the defending player | — |
| Aura swap | blocked | swapping an attached aura with one in hand; one card in the game | — |
| Banding | refused | see rules-coverage.md | — |
| Battle cry | free | `attacks` trigger, then `pump` the other attackers | — |
| Bestow | blocked | a creature cast as an aura — one card in two zones' worth of types | — |
| Blitz | routed | an alternative cost like `evoke`, plus haste and a delayed sacrifice | — |
| Bloodrush | routed | an activated ability from hand whose cost discards — the cycling shape, with a pump | — |
| Bloodthirst | blocked | "an opponent was dealt damage this turn" — a per-turn ledger the engine does not keep | — |
| Bolster | routed | needs "the creature with the lowest toughness", and no selector picks an extremum | — |
| Bushido | routed | `blocks` trigger exists; "or is blocked" has no matching event | — |
| Buyback | routed | an additional cost like `kicker`, plus a return-to-hand instead of the graveyard | — |
| Cascade | blocked | cast a card from exile without paying its cost, chosen by a library scan | — |
| Casualty | routed | an additional cost that copies the spell; spell copying does not exist | — |
| Champion | blocked | exile-and-return tied to the championing permanent leaving | — |
| Changeling | free | `add_subtype` static — confirmed in card-authoring.md | — |
| Channel | routed | the cycling shape again: an activated ability from hand costing a discard | — |
| Cipher | blocked | encoding a spell onto a creature and recasting it from exile | — |
| Connive | routed | draw-then-discard with a counter conditional on what was discarded; needs to read the discarded card | — |
| Conspire | routed | a cost tapping creatures, plus spell copying | — |
| Convoke | routed | a cost paid by tapping creatures — a cost kind, not an op | — |
| Coven | blocked | "three creatures with different powers" — no distinct-value count exists | — |
| Crew | routed | vehicles are not a supported type; the tap-for-power cost is the smaller half | — |
| Cumulative upkeep | routed | `upkeep` trigger and `add_counters` exist; the escalating cost needs `may` `pay` to scale off a counter count | — |
| Cycling | shipped | `activated` + `active_zones: ["hand"]` + a `discard_self` cost | — |
| Dash | routed | an alternative cost, plus haste and a delayed return | — |
| Daybound / nightbound | refused | day/night is a designated-game-state mechanic; see rules-coverage.md | — |
| Delve | routed | a cost exiling from the graveyard to pay generic mana | — |
| Detain | routed | `lock_abilities` and `cant_attack` exist separately; needs them bundled until a player's next turn | — |
| Devour | routed | `self_enters` + sacrifice + `for_each`; the scaling counters are the awkward half | — |
| Disturb | blocked | transforming cards | — |
| Dredge | blocked | replaces a draw, and the replacement whitelist has no draw form | — |
| Echo | routed | `upkeep` trigger with a `may` `pay` and a sacrifice `else` — close to the Karoo idiom | — |
| Embalm | routed | activated from the graveyard, creating a token copy; `copy_permanent` exists | — |
| Emerge | shipped | card-level field; one cast line per sacrificeable creature | `emerge` |
| Entwine | routed | an additional cost that takes *both* modes; `choose_mode` picks exactly `count` | — |
| Epic | blocked | a lasting restriction on casting, plus a copy each upkeep | — |
| Escape | routed | casting from the graveyard, like `retrace`, with an exile cost instead of a discard | — |
| Evoke | shipped | card-level field, and the `evoked` condition its sacrifice trigger reads | `evoke` |
| Evolve | routed | `permanent_enters` + a comparison against *this* creature's derived power | — |
| Exalted | free | `attacks` trigger, condition `cmp` on `count` of attacking creatures you control equals 1 | — |
| Exert | routed | `attacks` trigger plus a `may`; `skip_untap` already exists for the cost | — |
| Exploit | routed | `self_enters` + an optional sacrifice; the "if you do" is an ordinary `may` `else` | — |
| Explore | routed | `reveal` and `add_counters` exist; needs the revealed card routed by type | — |
| Extort | routed | `spell_cast` trigger and `may` `pay` exist; the drain is `lose_life` plus `gain_life` | — |
| Fabricate | free | `self_enters` trigger, then `choose_mode` between `add_counters` and `create_token` | — |
| Fading | routed | `upkeep` + `remove_counters` + a sacrifice; needs "if you can't" to be askable | — |
| Fateseal | routed | `scry` on another player's library — the op is hard-wired to the controller | — |
| Fear | shipped | `Keyword`, read in `combat.can_block` against the blocker's **derived** types and colors | `fear` |
| Flanking | routed | needs "whenever this becomes blocked", which no event covers | — |
| Flashback | routed | casting from the graveyard, like `retrace`, then exiling instead of returning | — |
| Flip | refused | flip cards; see rules-coverage.md | — |
| Forecast | routed | an activated ability from hand that reveals rather than discarding — and so cannot use the cycling guard | — |
| Foretell | blocked | a special action putting a card in exile to be cast later; suspend is the nearest shape | — |
| Frenzy | routed | needs "attacks and isn't blocked", which no event covers | — |
| Graft | routed | enters with counters, then moves them on another creature entering | — |
| Gravestorm | routed | spell copying, counted off a per-turn ledger | — |
| Haunt | blocked | exile attached to a creature, with a second trigger on its death | — |
| Hideaway | blocked | exiling a card face down and casting it later from under a permanent | — |
| Horsemanship | shipped | `Keyword`, read in `combat.can_block`: the blocker must carry it too | `horsemanship` |
| Imprint | blocked | exile attached to a permanent, with abilities reading the exiled card | — |
| Indestructible | shipped | `Keyword`, read by the lethal-damage state-based action | `indestructible` |
| Infect † | routed | poison counters, plus damage-as-counters — the wither half is the same replacement | — |
| Inspired | routed | needs a "becomes untapped" event | — |
| Intimidate † | shipped | `Keyword`, comparing the two creatures' **derived** colors in `combat.can_block`, with an artifact escape | `intimidate` |
| Investigate | routed | `create_token` exists; the Clue needs a token with an activated ability | — |
| Jump-start | routed | casting from the graveyard with a discard cost — retrace, discarding any card rather than a land | — |
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
| Mentor | routed | `attacks` trigger; the target filter must compare against this creature's derived power | — |
| Miracle | blocked | replaces the first draw of a turn, and needs the draw's ordinality | — |
| Modular | routed | enters with counters, then moves them all on death | — |
| Monstrosity | shipped | op, plus the one-way flag and the `becomes_monstrous` trigger | `monstrosity` |
| Morph / megamorph | blocked | face-down creatures | — |
| Mutate | blocked | stacked permanents with merged abilities | — |
| Ninjutsu | blocked | returning an unblocked attacker and putting a creature in attacking, without casting | — |
| Offering | routed | an alternative cost reduced by a sacrificed creature — this is `emerge`, restricted by type | — |
| Overload | routed | a cost that swaps a targeted selector for a global one | — |
| Partner † | shipped | an **inert** `Keyword` — deck construction only, and the engine is handed a finished deck | `partner` |
| Persist | routed | a dies-trigger return with a counter; the "if it had none" gate is `counters_on` | — |
| Phasing | refused | phasing; see rules-coverage.md | — |
| Poisonous | routed | poison counters are not a loss condition the engine checks | — |
| Populate | free | `copy_permanent` over a selector filtered to `is_token` | — |
| Proliferate | routed | needs "every object with any counter", and counter kinds are not enumerable off an object | — |
| Provoke | routed | `must_attack` exists for requirements; this is the block-requirement mirror, which does not | — |
| Prowl | blocked | an alternative cost gated on a per-turn damage ledger | — |
| Rampage | routed | needs "becomes blocked" and the count of blockers | — |
| Rebound | routed | `delay` already schedules the recast; the exile-instead-of-graveyard half is a replacement | — |
| Recover | routed | `creature_dies` trigger plus `may` `pay`, with an exile `else` | — |
| Reinforce | free | activated from hand with a `discard_self` cost, then `add_counters` — the cycling shape | — |
| Renown | routed | `deals_combat_damage_to_player` trigger plus a one-way flag, exactly like `monstrous` | — |
| Replicate | routed | an additional cost paid repeatedly, plus spell copying | — |
| Retrace | shipped | card-level field; casting from the graveyard, discarding a land | `retrace` |
| Riot | routed | `self_enters` + `choose_mode`, but a `choose_mode` inside a trigger resolves late | — |
| Ripple | blocked | free casts off a library scan, retriggering itself | — |
| Scavenge | free | activated from the graveyard with an exile cost, then `add_counters` | — |
| Shadow | shipped | `Keyword`, compared **symmetrically** in `combat.can_block` — it restricts blocking as well as being blocked | `shadow` |
| Shroud | shipped | `Keyword`, read by `targeting.can_be_targeted` only — stops the controller too | `shroud` |
| Skulk † | shipped | `Keyword`, compared on **derived** power inside `combat.can_block` | `skulk` |
| Soulbond | blocked | a paired-permanent relationship with no representation | — |
| Soulshift | free | `dies` trigger, then `return_from_graveyard` filtered by subtype and `mana_value` | — |
| Spectacle | blocked | an alternative cost gated on a per-turn damage ledger | — |
| Splice | blocked | adding one card's effects to another spell as it is cast | — |
| Split second | routed | a flag suppressing priority while the spell is on the stack | — |
| Storm | routed | spell copying, counted off a per-turn spell ledger | — |
| Sunburst | routed | enters with counters scaled by the colours actually spent, which payment does not report | — |
| Support | free | `add_counters` over a target spec with `count` and `optional` | — |
| Suspend | shipped | card-level field, its own module, and haste on what arrives | `suspend` |
| Totem armor | routed | a destruction replacement on the enchanted creature | — |
| Transfigure | free | activated, sorcery speed, cost sacrifices self, then `search_library` on `mana_value` | — |
| Transform | refused | transforming cards; see rules-coverage.md | — |
| Transmute | free | activated from hand with a `discard_self` cost, then `search_library` | — |
| Tribute | routed | `self_enters` with a choice belonging to an opponent; `two_piles` proves the shape is reachable | — |
| Undying | routed | a dies-trigger return with a counter; the mirror of persist | — |
| Unearth | routed | activated from the graveyard, returning to play with haste and a delayed exile | — |
| Unleash | routed | enters with a counter is whitelisted, but there is no `cant_block` static to pair with it | — |
| Wither | blocked | a damage replacement, and the whitelist has no damage form | — |

## Ability words

Italic flavour with no rules meaning — rule 207.2c. The ability after the word
is ordinary, which is why most of this table is `free`.

| Keyword | Status | Mechanism | Engine name |
|---|---|---|---|
| Addendum | free | condition `is_your_turn`, which is as close as the engine gets and is right for a sorcery-speed clause | — |
| Battalion | free | `attacks` trigger, condition `cmp` on `count` of attacking creatures you control | — |
| Chroma | routed | counting mana symbols in a zone; nothing reads a card's pips | — |
| Domain | blocked | counts basic land *types*, not lands; no distinct-subtype count exists | — |
| Enrage | routed | needs a "this was dealt damage" trigger event | — |
| Fateful hour | free | condition `cmp` on `life_of` `"you"` | — |
| Ferocious | free | condition `exists` with `power` `>=` 4 | — |
| Grandeur | free | activated from hand, cost `discard_selector` by `name` | — |
| Hellbent | free | condition `cmp` on `cards_in_hand` equals 0 | — |
| Heroic | routed | needs a "becomes the target of a spell" trigger event | — |
| Join forces | routed | mana contributed by several players; every cost is paid by one | — |
| Kinship | routed | `upkeep` trigger; needs to look at the library top and read its subtypes | — |
| Landfall | free | `permanent_enters` with `types: ["Land"]` — **not** `land_played`, which is narrower | — |
| Metalcraft | free | condition `cmp` on `count` of artifacts you control | — |
| Morbid | blocked | "a creature died this turn" — a per-turn ledger the engine does not keep | — |
| Radiance | routed | widens a target to everything sharing a colour with it | — |
| Raid | blocked | "you attacked this turn" — a per-turn ledger | — |
| Rally | free | `permanent_enters` with `subtypes: ["Ally"]` | — |
| Sweep | free | cost `return_to_hand` over a selector by `subtypes`, then a value off `count` | — |
| Threshold | free | condition `cmp` on `count` of `zone: "graveyard"`, `controller: "you"` | — |
| Undergrowth | free | value `count` of creatures in your graveyard | — |

## What the census says

**The largest single finding is that ability words are nearly free.** Twelve of
the twenty-two above need no engine work at all, and neither do a dozen entries
in the expansion table — adapt, affinity, afterlife, alliance, battle cry,
fabricate, living weapon, populate, reinforce, scavenge, soulshift, support,
transfigure, transmute. Those are `/author-cards` jobs, not `/extend-dsl` jobs,
and nothing in the demand-driven report would ever have surfaced them: a
capability with no gap record does not appear there, and a capability that is
already expressible never gets a gap record written for it.

**The evasion family is now closed.** Fear, intimidate, horsemanship, shadow and
nonbasic landwalk shipped together, because they are one capability and not five
— every one is a question `combat.can_block` asks of `chars` on both creatures,
and the rest of `can_block` was already the answer. What is left of combat is
not evasion at all: flanking, rampage, bushido, frenzy and provoke each want a
*trigger event* the engine does not have ("becomes blocked", "attacks and isn't
blocked"), which is a different tier of work with frontend consequences.

**The blocked entries cluster, and the clusters are small.** Nearly everything
marked `blocked` above waits on one of six things:

| Blocker | Waiting on it |
|---|---|
| A **per-turn ledger** — did a player attack, take damage, lose a creature | morbid, raid, bloodthirst, spectacle, prowl, storm, gravestorm |
| **Casting from the graveyard**, generalised past `retrace` | flashback, escape, jump-start, embalm, unearth, disturb |
| **Spell copying** | casualty, conspire, replicate, storm, gravestorm, ripple |
| **More replacement forms** — draw, discard, damage, destruction | dredge, madness, wither, miracle, totem armor, regeneration |
| **Face-down and multi-faced cards** | morph, manifest, adventure, aftermath, transform, disturb, meld |
| **`unless_pays`** | ward, and Rhystic Study, which already has gap records |

A per-turn ledger is one piece of state and unblocks seven mechanics. That is
the shape of argument this page exists to make available, and it is not visible
one gap record at a time.

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
3. **Casting from the graveyard, generalised.** `retrace` already proved the
   legality scan; flashback and escape differ only in the cost and where the
   card goes afterwards.
4. **`unless_pays`.** Ward is evergreen, so this compounds with every future
   set, and the demand side already has records for it.
5. **Spell copying.** A cluster of six, and the object model already copies
   permanents.
6. **More replacement forms.** The whitelist is deliberate and widening it is a
   design decision, not just work — read [adr/0001-layers-lite.md](adr/0001-layers-lite.md)
   first.

Face-down and multi-faced cards are last on purpose: they are the only cluster
that is a genuine rules subsystem rather than a missing vocabulary item, and
`/extend-dsl` rule 4 says to stop and report rather than start one inside a
card-unblocking run.

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
