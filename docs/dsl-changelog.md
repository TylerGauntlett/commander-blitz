# Card DSL changelog

How the vocabulary in [card-dsl.md](card-dsl.md) came to be: what an op, key, cost,
trigger or condition used to do, the bugs that were fixed in it, what was renamed or
removed, and which card a capability was built for. [card-dsl.md](card-dsl.md) says
what the vocabulary *is*; this file says how it got there.

The sections mirror `card-dsl.md`'s headings, so the history of a reference section
sits under the same heading here. Within a section, entries are in the order the
reference used to carry them. For dates, see
`git log -- docs/card-dsl.md`.

When you change a capability, write the current behaviour into `card-dsl.md` in the
present tense, replacing what was there, and put what it used to do, and why it
changed, under the matching heading here.

## The shape of a card

### `oracle_text` is a contract, not a caption

`oracle_text`: It used to be described here as "display only", and it was written that way: a human summary of what the card had been made to do. That quietly disabled the one gate that asks whether a card implements everything it prints, because the gate compares the implementation to `oracle_text` — and a summary written *after* the shortcut agrees with the shortcut. Krosan Tusker recorded `"A large boar."`, and against that text a vanilla 6/5 is a faithful implementation. It shipped for months with no cycling and nothing to notice.

So `oracle_text` is now **the printed text, verbatim**, and each ability's `text` is **the printed line that ability implements** — that is what the residual gate matches on.

## Effect ops

`cast_from_hand`: The engine could already cast for free from the library top (`look_at_top`'s `cast_free`, cascade, Bolas's Citadel) and from exile (`play_exiled`, foretell); the one zone it could not reach was the one every card of this shape names.

`search_zones`: `search_library` is now this op with `zones: ["library"]`, so the two cannot drift apart.

`put_on_top`'s `from_top`: It reaches the zone layer as `move_object`'s `to_index`, a library position; nothing else in the engine had one, since `to_top: bool` made top and bottom the only reachable places.

Both roundings the boolean forced are a different card, in opposite directions: on **top**, the owner draws the permanent back on their next draw step, which is the reverse of what the depth buys; on the **bottom** of a 99-card deck it is exile with extra steps.

### Proliferate — a choice over permanents and players

`proliferate`: The op used to proliferate every permanent its controller had with a counter and took an `objects` selector to narrow that. Both are gone, and the loader refuses `objects`: a selector decides for the player what the printed word lets them choose, and an infect card's proliferate is worthless if it cannot reach an opponent's poison.

## Selectors — "which objects"

`count: "any"`: Nothing under the decision layer needed building: `ask_objects` always took distinct `min_count` and `max_count` bounds and `PendingDecision.min_count` was always honoured, so `"any"` is only the spelling that reaches them.

`mana_cost` selector: The nearest older spelling — `mana_value <= 1` with `not_colors` and `x_in_mana_cost: false` — fetches Seat of the Synod, which the Saga cannot.

`not_supertypes`: `supertypes` cannot say it: it is a positive subset test, so it can *require* Basic and never forbid it, and the negated family it joins (`not_types`, `not_subtypes`, `not_colors`, `not_keywords`) had no supertype member.

`any_of`: A branch is matched in whatever zone the **outer** selector settled on, which is the other half of that rule: Boromir's "a Human **or** artifact card" is asked about cards in a library, and matching the branches against the battlefield instead made every one of them fail — so the op saw an empty pool and quietly never asked, which on screen is indistinguishable from a top six that happened to hold neither.

### Describing objects relative to *another* object

Binding as a selector source: Without that, the nearest thing a card could ask was "is there a land *somewhere* in my library", which is true almost always and would have made the branch a formality.

### Recording what an op consumed or produced — "this way", "the token"

`as` on `reveal`/`sacrifice`: `as` writes the chosen oids into the binding, and `{"binding": …}` now seeds a **list** as readily as a single object. Every trigger binding before this held exactly one, so nothing else changed.

`reveal` also goes through `choose_objects` now, which is what makes "reveal **any number**" sayable at all: it used to resolve its pool and show the whole hand without asking. `count` still defaults to `"all"`, so every reveal already in the pool is unchanged.

### `sacrifice`'s `snapshot` — what the creature *had*

Search ops' `as`: The closest expressible card without it was "untap a tapped basic land you control", which also frees a Forest tapped for mana earlier in the turn — a strictly better land than the printed one, and one that looks entirely ordinary on screen.

### Selectors on a `kind: "spell"` target

Spell-target selectors: This did not always work. The spell branch used to return every spell on the stack and never look at `spec.selector` at all, so Negate, Essence Scatter and Exclude were all Counterspell — the clause loaded, validated, and was simply never asked. `tests/unit/costs/test_x_in_mana_cost.py` pins the repair on those two shipped cards as well as on the key it was built for.

### Doing something to a spell that is not countering it

`return_spell_to_hand`: The loader now refuses the two ways of writing that: `return_spell_to_hand` insists its `target` is declared `kind: "spell"`, and refuses an `objects` key outright.

### "Target spell or nonland permanent"

`spell_or_permanent`: One instance of the word "target" whose legal choices live in two zones at once — `"spell"` walks the stack, `"permanent"` and `"any"` walk the battlefield, and nothing pooled the two.

`spell_or_permanent`: `still_legal` needed no change at all, because it already re-checks a stored ref by `ref.kind` rather than by the spec's — so every ref this pool offers is one it will accept.

### "As this enters, you may pay …"

`unless_cost` on `self_enters_tapped`: Steam Vents ships today with the sentence dropped — a strictly worse card, and a silent one.)

### "Each of X targets"

X-sized spell targets: The engine already ran them in that order.

X-sized spell targets: Legality is untouched and stays a **gate**, which it already was for the cost: "X is a gate here, not a value… `game._cast` then asks the player which one." It sizes the spec at zero, offers one line, and the refs are chosen where X is a number.

X-sized spell targets: `filter_legal` needed nothing. `variable_size` already makes the last spec swallow the remaining refs, and its comment already argues that re-evaluating a computed count on resolution would be worse than using the stored length — "the number is fixed when the targets are declared (601.2c)".

X-sized spell targets: Two refusals: `{"x": true}` on a card with no `{X}` in its mana cost (the spec would size to zero for ever — a spell that says it targets and never does), and every other computed count on a spell, unchanged.

### Granting rebound to a spell that does not print it

`grant_rebound`: Rebound itself is not new and never was: `rebound` has been a card-level rider since the field existed, with the exile-on-resolution in `_place_after_resolution`, `rebound_by` on the exiled card and the free cast in `suspend.rebound_tick`. The whole mechanic was reachable only by a card that printed the keyword, because the rider read the flag off the **card**.

## Value expressions

### A static magnitude that counts in twos

`buff` with a `count` magnitude has shipped since Crown of Gondor and always stepped by exactly one: every leaf in the static value language *measures* something and nothing combined two.

### Which creatures attacked this turn, and how many

Which creatures attacked this turn: Two spellings of one record, and they are not interchangeable with anything that was already there.

The player-level `attacked` is now *derived* from its keys, so raid and this read one fact and cannot disagree.

### Which permanents entered the battlefield this turn

#### `power` / `toughness` — a *derived* characteristic, read at a fixed layer

The two readers of this filter language that run **outside** the characteristics pipeline are not restricted and must not be, because nothing is half-computed where they run: a trigger filter (`matches_card_filter`) has read derived power since Welcoming Vampire's "creatures you control with power 2 or less enter", and a `cost_reduction` counts derived power too, as it already counts derived types and keywords.

### Counting the mana that was actually spent

`{"colors_of_mana_spent": true}` is sunburst and converge, and it is the first thing in the engine that reads how a spell was **paid for** rather than what it costs. The answer used to be thrown away: `ManaPool.spend` decremented six integers in place and returned nothing, so a moment later one blue mana was indistinguishable from another.

### Counting mana symbols

`{"mana_symbols": {"of": "G", "objects": …}}` is chroma, and it is the first thing in the engine that looks **inside** a mana cost.

### Granting a static ability with the one-shot op

`grant_ability` op granting a static: The `grant_ability` op could hand over an activated ability (Urza's Saga) or a triggered one (Clavileño), and the loader refused it a **static** outright, with its reason written down: the op's grants "are pointers that the characteristics pipeline never reads, so granting the static … with it would do nothing". The premise was true and is no longer. The function simply had to stop filtering statics out. The continuous `grant_ability` **static** is not a substitute, which is why this had to be the op: a static on The Irencrag applies from the moment the artifact enters, handing out +3/+3 on turn one with no transformation. An op-granted **triggered** ability is still kept off the derived list — and that is a fact about `_op_granted_abilities`, not a refusal at load, because `triggers.collect` already yields one off the grant record itself.

### Losing all abilities because an effect said so

`lose_all_abilities` op: `lose_all_abilities` existed only as a **static**, and a static is the wrong shape for this line twice over. And no `condition` can gate it, because the transformation it waits for was not a fact the engine had a flag for.

Two other readers had to learn it: `abilities_of`'s fast path, which returns the printed list outright when no static and no op grant is in sight, and `_loses_abilities`, which answers the same question for callers outside the walk.

### Changing a permanent's name

`rename` op: Nothing in the engine could change a name.

### A discount that asks what the spell or ability is aimed at

`targeting` on a cost reduction: Every filter a reduction could read described the **board** — `affects_spells` is the spell's printed face, `affects` the permanents around it — so "that target enchanted creature" could only be softened into "every Aura you cast", which is a different and stronger card.

That makes the price a question about **which** permanent is being aimed at, and the plumbing follows from it: `costs.ability_mana` and `costs.cost_reduction` both take the chosen targets, `legality._ability_aims` prices each aim separately, and `casting._priced_tuples` — which already existed for strive, the other case where the targets change the price — solves each tuple on its own when such a static is on the board.

### A static that discounts another permanent's activated ability

`ability_cost_reduction`: `spell_cost_reduction` was the only cost-lowering static, and it prices **spells**: it is handed a `CardDef` being cast. The one reduction that reached an activated ability was `Cost.mana_reduction`, and it is a different sentence — it lives *inside the ability's own cost node*, so only the card printing the ability could discount it.

### A delayed trigger scoped to one chosen object

`delayed_trigger` `subject`: `delayed_trigger` could say *when* ("this turn") and *whose* (`controller`), and could not say *which*. Forth Eorlingas!, the card it was built for, watches any creature you control and needs no scope — so written without one, Hunter's Insight is that card with a target line stapled on, and every creature you control draws off it.

### "…deals combat damage to a player or planeswalker"

`deals_combat_damage_to_planeswalker`: 306.8's damage has always worked — `damage_permanent` takes the loyalty counters off — and nothing could trigger on it: `deals_combat_damage_to_player` is fired from `damage_player`, which a planeswalker hit never reaches, and `dealt_damage` is about the permanent *being* hurt rather than the one connecting.

### A target pool that only exists once X is known

X announced before targets (The Mycosynth Gardens): 601.2b announces X **before** 601.2c declares targets, and the engine had that order backwards for an activated ability: `_ability_aims` enumerated one activation per target tuple with `x = 0`, `_activate_ability` asked for X afterwards, and every `EffectContext` targeting built left `x` at its default. The selector's `{"x": true}` leaf therefore read zero twice — once listing the candidates and again when 608.2b re-checked them on resolution.

It **loads and fails silently**, which is why this needed building rather than noticing: `validate_selector` has no guard against a value expression on `mana_value`, so the card compiles, offers the artifacts of mana value 0, and fizzles.

The fix is the shape `ability_modes` already took, for the same rule. A modal ability whose bullets own their targets has the same problem — 601.2b picks the mode before 601.2c declares its targets — and it was answered by making the mode part of the *action*. X gets the same answer: legality offers **one activation per payable X**, each carrying the targets legal at that value, the label says `(X=n)`, and `_activate_ability` takes the number off the action rather than asking again.

Every other activation in the pool pays one attribute check and keeps its old shape.

### A permanent that enters as a copy

`self_enters_as_copy`: 614.1b, and the fifth entry on the enters-the-battlefield replacement whitelist — `self_enters`, `self_enters_tapped`, `self_enters_with_counters`, `self_enters_prepared` and now this. None of the first four could change the arriving object's *identity*.

### A permanent whose arrival is itself replaced

`self_enters_replaced`: 614.1a, and the sixth entry on the whitelist — and the first that is not a decoration. The five before it (`self_enters`, `self_enters_tapped`, `self_enters_with_counters`, `self_enters_prepared`, `self_enters_as_copy`) all modify a permanent that is **already arriving**, which is why they can live in `zones._enter_battlefield`: that function runs with the object on the battlefield, and it reads nothing but `tapped`, `counters`, `prepared` and `copying`.

### Damage multiplied on the way out

`replace_damage`: No damage-modifying static existed at all. The five multiplier replacements were life and card economy — `replace_life_gain`, `replace_life_loss`, `replace_draw`, `replace_mill`, `replace_token_creation` — every one **player-wide** and keyed by player id, so none could be attached to a permanent or filtered by who was dealing to whom; and the only damage-facing statics, `prevent_damage` and `protection`, subtract or forbid and have no way to add.

### Counters replaced on the way in

`replace_counters`: The sixth named replacement, and the first about an **object** rather than a player — tokens, draws, life gain, life loss and milling all take `affects_player`; every printed counter replacement names what the counters would be put on, so this one takes `affects` and the filter is **required**. Not one of the five could have been borrowed, either: every one of them is a *multiplier* refused below 2 by the loader, and "plus one" is not a multiplier at any size.

### "Whenever this creature mutates…"

`mutates`: The moment has been in the log since mutation existed — `merge_permanents` ended with an `emit` — but `emit` only writes the log ("the caller is responsible for handing the event to the trigger bus"), so the printed line had nothing to hear it. `fire` instead, plus the `EventType` and the `trigger_events` row.

`mutates`: Writing it found a bug in the merge itself: the two ability lists were concatenated without renumbering, so an ability from underneath kept its old `index` and resolution — which reads `Ability.index` back as a *position* in `abilities_of` — looked up whatever the top card had at that number. Fixed in the same commit; see `TestTheMergedAbilitiesAreRenumbered`.

### Mana that doesn't empty as steps and phases end

`persists_until_end_of_turn`: 500.4 empties every mana pool as each step and phase ends, and `turn.advance` did that unconditionally. Mana added by an attack trigger therefore lived until the end of the declare-attackers step and no longer — one boundary short of ever reaching the main phase the card is for.

`Pip` grows a `persists_through_turn`, `ManaPool.clear` takes a `keep_for_turn`, and `empty_all_mana_pools` passes the current turn at every boundary but the cleanup step's — which is the `advance` that ends the turn, and so is exactly where "until end of turn" runs out.

### Cards in a hand drawn this turn

`drawn_this_turn`: `GameState.cards_drawn_this_turn` has existed as long as the draw tally, and it is a per-player **integer**: it says how many, and no selector can ask which.

### A search whose destination depends on what it found

`destination_if`: `_search` resolved one `DESTINATIONS[…]` and one `tapped` **before** it saw what was picked, and `_move_found` sent everything there — so "put it onto the battlefield tapped if it's a land card, otherwise put it into your hand" could not be written.

### Narrowing when a spell may be cast

`cast_before_step`: `casting._timing_ok` is the one gate on casting speed and it could only **widen**. Nothing on a card could say no.

### Choosing a permanent type, and reading it back

`choose_type` `of: "permanent_type"`: `choose_type` already asked "pick one of these labels" and recorded the answer; what it could only ask about was **creature** types, because its options come from `CardRegistry.creature_types()` and its answer lands in `GameObject.chosen_type`, whose one reader substitutes into a filter's `subtypes`. A card naming a *card* type had no way to say either half.

### Counting an event rather than the board

`TurnLedger`: No emitter needed changing, and the fold runs while the object is still in `state.objects`, which is how it can ask a dying creature who controlled it.

`resolutions_this_turn` joined the ledger later and breaks both of those rules, for reasons worth stating.

## Costs

### Crew — a tap cost measured in power

Crew: *Vehicle* needed nothing — `subtypes` is free text.

### Station — a tap cost that names what it tapped

Station: And `add_counters` now clamps a negative amount to zero (107.1b): a creature with negative power stations nothing rather than removing counters.

## Player specs

### `not` — the player a card *excludes*

A `controller` clause on a player target is a full player spec. It did not used to be: the clause was read in three ways — `"you"`, `"opponent"`, and a `return True` fallthrough — so a mapping compiled cleanly, was dropped on the floor, and left a card printed "other than its controller" playing as "target any player". Wider than the printing, with nothing to say so.

### `target` versus `controller_of_target`

`target` versus `controller_of_target`: Written the wrong way round the clause resolves to *nobody*, and `op_may` reads an empty player list as `ctx.controller`: "unless its controller pays {3}" silently became "unless **you** pay {3}", which is the card's own opposite and raises nothing. The same check caught Hellrider naming the trigger binding `defender` as if it were a declared target, which made a shipped card deal no damage at all.

## Triggers

Trigger filters: **A trigger `filter` is a subset of the selector language.** It is matched against the event's subject by `triggers.matches_card_filter`, which answers `TRIGGER_FILTER_KEYS` (the packet's `trigger_filter_keys`) and nothing else, and the loader refuses any other selector key there -- `name`, `attacking`, `not_colors` and the rest used to load and be silently dropped, a trigger strictly wider than the printed line.

`self_enters`: Omitting it once produced cards that fired on every permanent entering, silently, and invisibly until a second permanent showed up.

`counter` on `counter_placed`: The event has always carried the kind and nothing read it, so the only trigger that could be written fired on *every* kind — and the shipped pool places `charge` and `slumber` counters, so Fathom Mage's "whenever a +1/+1 counter is put on this creature" would also draw off Arixmethes waking up.

### Tiered, and reading back which price was paid

Tiered: The cost half already shipped. `additional_cost_options` has existed since Bitter Triumph's "discard a card **or** pay 3 life" and does the hard part: one price chosen at cast, paid as part of casting, offered as its own cast line per option. What was missing is reading the choice back, because Bitter Triumph never needed to — both of its prices lead to the same "destroy target creature".

### Discarding a whole hand, and reading the greatest that went

Windfall: Two halves, and each was unsayable for the same underlying reason -- a per-player quantity in an op whose `amount` is evaluated once.

`greatest_discarded_by_a_player`: Nothing new is recorded to make that work -- `as` already accumulates oids across players, and an oid knows its owner.

### A mana ability that splits colours

Split mana (Vivi Ornitier): Two things at once, and the engine had each separately:

### The same split, off a trigger

Triggered split mana: X independent one-mana choices *is* a free division of X, and no new `DecisionKind` was needed for it.

### A mana ability that makes X of **one** colour

`any_one_color`: The sixth member of the family above, and the only one that needs no branch in `costs.mana_options_of` at all: the five one-symbol options really *are* what the ability offers, and `mana_amount` — which has scaled a single option since Gyre Sage — turns whichever one the payer picks into X of that colour.

### `spell_copied`, and why magecraft is two abilities

`spell_copied`: Nothing here was new except the listener. `EventType.SPELL_COPIED` had been emitted by `put_copy_on_stack` since copying existed — but through `state.emit`, which only *records* an event, where every other trigger-bearing event in the engine goes through `triggers.fire`. So the event was written into the log and heard by nobody, and no amount of card vocabulary would have reached it.

`ability_activated`: The event existed and both activation paths emitted it; what it had never had was a listener, because both used `emit` (which only writes the log) rather than `fire`.

`ability_activated` (Harsh Mentor): `zone` and `any_types` in a **trigger filter** are honoured as of this event. Both were already legal `SELECTOR_KEYS`, so a trigger carrying either loaded and then ignored it — the silently-wider filter that `not_supertypes` is annotated about. Nothing shipped used them on a trigger, so no card changed; Harsh Mentor needs both, and needs them in the narrowing direction: `types` is a conjunction, so "an artifact, creature, or land" written with it matches nothing, and without `zone` the card fires when an opponent *cycles* a land card out of hand.

Trigger filter `tapped`: **`tapped`** in a trigger filter is the third of that family and the same trap: legal to write, and read by nothing until now.

`becomes_untapped`: The event had always existed — `untap_permanent` fires it — but `untap_all` emitted one aggregate carrying a `count` and no `oid`, through `emit` rather than `fire`, so it never reached the trigger bus and named no permanent for `source: "self"` to match. The untap step now fires one event per permanent like every other path does.

`becomes_tapped`: **`becomes_tapped`** is the other half, and unlike its twin it really was the one-line job that one looked like: every route to tapping a permanent already goes through `tap_permanent`, which has always fired the event — including tapping for mana and being declared as an attacker, which are the two cases the printed cards (City of Brass, the painlands, Legolas's Quick Reflexes' granted trigger) are played for. All it lacked was a name here.

Ward: `may` has taken an arbitrary `player` since Fact or Fiction and a `pay` cost since Rhystic Study, `{"binding": "event_player"}` is the caster, and `counter` takes a `sid`:

`targeted_by`: So the only trigger a card could write was the wide one, and a Dragon written with it mints a Treasure off an opponent's tapper, off a fight ability, and off its own controller's equip.

`targeted_by`: `announce_targets` has tagged every `BECAME_TARGET` with the answer since the event existed, on both the object and the player half and at all four push sites.

`dealt_damage`: "…deals **that much** damage" needs nothing extra: `amount` was always copied into the trigger's bindings, so `{"binding": "amount"}` reads it.

Landfall: Reading the first as the second is a silent defect, because the card still works on your own land drops and only goes quiet on ramp — it is exactly what was wrong with Aesi.

## Static abilities

#### `owner` — "creatures you **own**"

Static `owner`: `costs`' cost-reduction filter has read the word this way since Visions of Glory, and this is the same spelling rather than a second dialect.

Static `permanents_entered_this_turn`: `permanents_entered_this_turn` is the newest, and the one whose near miss is worst.

Static `permanents_entered_this_turn`: It reads the same `TurnLedger.permanents_entered` snapshots the effect side has read since Éowyn, through the same `validate_entered_filter`, so `controller` stays required here too: an omitted clause would silently count the opponents' arrivals, and every printed sentence of this shape says whose battlefield it means.

### "As long as…"

#### "An opponent has 10 or less life"

`min_life_of` / `max_life_of`: `min` and `max` already existed and cannot stand in: they take a literal list of value expressions written into the card, and no player spec enumerates opponents one at a time to feed them.

### "As long as…"

#### "At least 7 life more than your starting life total"

`starting_life_of`: `sum` joined the static language with it, because every printed threshold on a starting life total is an offset from it; its terms are held to the static list exactly as `times`' factors are.

## "You gain life equal to the life lost this way"

Malakir Bloodwitch was written that way and now uses the binding.

## Mana abilities

### `spend_mana_as_any_color` — Chromatic Orrery's colour waiver

`spend_mana_as_any_color`: The mechanism was already here. `ManaCost.as_any_color` was written for Elder Brain — *"you may spend mana as though it were mana of any color **to cast it**"* — and reached only through `permission.playable_any_color`, the `any_color` flag on `exile` / `grant_playable` / `look_at_top` / `search_library`, which rides on one card that effect made playable.

### `free_cast_permission` — Dracogenesis' standing free cast

`free_cast_permission`: **It is not `grant_playable` either.** That op's docstring says its cards "are paid for at their printed price", and it marks only the objects it can see as it resolves — the snapshot problem `grant_graveyard_cast` was added to fix.

### Restricted mana

Restricted mana, `activate` half: **A bare string or list is the `cast` half alone.** Every card printed before this one says "only to cast", and an `activate` permission handed out by name alone would have quietly rewritten Herd Heirloom, Ancient Ziggurat and Master of Dark Rites without a line of their JSON changing. `costs.SpendPurpose` carries the kind for that reason; `costs.ability_purpose` is the activation half, threaded through `legality._ability_aims` and `game._activate` exactly as `spell_purpose` is threaded through the four cast sites.

### Restricted mana

#### A restriction that is not a name — `mana_value`, `x_in_mana_cost`

`mana_value` / `x_in_mana_cost` restrictions: **A bare `["creature"]`** — Ancient Ziggurat's spelling, and the closest thing the language had — drops both clauses and funds every creature spell there is.

### Restricted mana an *effect* made

`compile_restriction`: It lives beside `ManaRestriction` rather than in the loader (where it used to) because an effect's spec is still JSON when it resolves: a mana ability's restriction is compiled once at load, and an effect's is compiled again as it runs.

### Mana that makes the spell uncounterable

Supertypes as restriction names: They were the quiet omission: `_restriction_name` accepts any alphabetic word, so "legendary" loaded clean and matched nothing on any card in the game — mana that could never be spent, which reads on the board as a land that taps for nothing.

### Casting out of every graveyard, until end of turn

`grant_graveyard_cast`: It means the `affects_spells` filter, `max_per_turn`, `grants_flashback` and the `cast_from_graveyard` mark that makes the spell exile as it resolves are all the code that already existed — so the second printed sentence needs nothing at all, and the loader asks for the same two guarantees the static's own loader does: a filter (an absent one would free the whole graveyard) and either a cap or `grants_flashback` (a permission that neither meters nor exiles is an engine, not a printed line). What is new is where the permission *lives*.

### How long "you may play it" lasts

`playable`: `playable_this_turn` is the impulse-draw permission and was the only one there was: a `playable_turn` on the object, compared against `state.turn` in seven places.

Generalising meant replacing all seven `playable_turn == state.turn` comparisons rather than adding an eighth, since that comparison *is* the this-turn duration.

## Auras and Equipment

### An Aura that enchants a player

Aura enchanting a player: Without the player branch Overencumbered resolved, attached to nothing, and `sba` moved it to the graveyard with cause `aura_unattached` before its own enters trigger could resolve — three printed sentences, a mana cost and no game effect at all. 704.5n is now read as it is written: an Aura attached to an illegal object **or player**, or to nothing, is binned.

`enchanted_player` as a selector controller: All three had to learn it: an unrecognised controller word matches **every** permanent rather than none, so a static naming one player would silently be a static naming the table.

"At the beginning of combat on enchanted opponent's turn" needed **no new trigger clause**.

### Reconfigure — taking it off again

Reconfigure / `unattach`: The attach half needed nothing — it is Equip, which shipped long ago. `unattach` is the new op, and there was no route to it at all: the attach model only ever *moved* an Equipment, and moving one onto a creature you do not want it on is a different game action from taking it off.

Reconfigure is also the first Equipment that is *also a creature*, which makes rule 301.5c reachable for the first time — an Equipment may not equip itself.

### `attachment` — attaching something that is not the source

`attach`'s `attachment`: `objects` is the **host** and always was. `attachment` is the thing that *moves*, and until it existed there was no way to say it: the mover was hardcoded to the ability's source, which is exactly right for Equip and Reconfigure — printed on the Equipment, so "attach to target creature you control" can only mean *me* — and wrong the moment a third party does the attaching. Here the source is a **Saga**, an Enchantment that is neither Aura nor Equipment, so the old op attached the Saga to a creature and left the Equipment lying on the battlefield equipping nobody.

## Not untapping at all

`not_supertypes` is the negation of `supertypes`, added here for `not_keywords`' reason: the effect-side selector language always had it and the static one did not.

## Player-wide statics

### `fight`

`cast_as_though_flash`: The only static that widens a **timing** window rather than a zone one, and the reason `casting._timing_ok` takes a `state` and a `pid` at all: it used to decide casting speed from printed characteristics alone (`card.is_instant or FLASH in card.keywords`), so nothing on the board could be consulted from it.

`look_at_library_top`: That is what `library_top_public` is for — the one API field this capability added.

### "As long as…" on a player-wide static

Player-wide static conditions: This was once a **silent over-grant**, which is worth knowing about because it is the failure shape the whole validation pass exists to refuse. The loader has always validated and stored a `condition` on any static, but `_static_active` had one call site — `_battlefield_statics`, which feeds only the characteristics pipeline — and the walks that read the player-wide effects never asked. A card like Verge Rangers therefore loaded clean, printed its clause, passed every gate, and granted the permission unconditionally: Oracle of Mul Daya on a 3/2 first striker. The gate now lives in `_active_player_statics`, which every reader of every player-wide effect goes through, including the two that answer with a *set of players* (`freeze_opponent_lands`, `double_land_triggers`) rather than per-player.

## "Sacrifice it unless you…"

### "You may pay {2}. If you do…"

`may`'s `pay`: A triggered ability fires on its own, so before this the only way to write that card was to drop the {2} — and a Sundial that draws free is a better card than the printed one.

### "You may pay {X}, where X is less than or equal to…"

`may`'s unbounded `x`: `_announce_x` hands `x.max` straight to `max_affordable_x` as the probe `cap`, so an invented 20 silently *becomes* the card's real maximum — which is why this was filed as a gap rather than approximated.

## Join forces — the one cost the whole table pays

`join_forces`: `may`'s `pay` grew a `player` spec for Rhystic Study, which is as close as the vocabulary gets, and it asks that player once.

## Modal spells with a target

Optional shared target on a modal spell: **Moving modes to cast time did not retire this idiom**: targets are still picked before modes, so the flag is as necessary as it ever was. The one new wrinkle is that a player can now choose a target-needing mode having declined the optional target, and it fizzles to nothing.

### `chooser` — when somebody else picks the mode

`choose_mode`'s `chooser`: It needed no new `DecisionKind`: `ask_mode` always took an arbitrary chooser, the same way `ask_objects` did for Fact or Fiction's pile-splitter.

### A static that works from the graveyard

`active_zones` on a static: `active_zones` was already read on activated and triggered abilities; a static reads it too, and only `battlefield` (the default), `graveyard` and `command` are accepted — those are the three zones the engine walks for statics, and one declaring `hand` would load clean and never be gathered. **The zone clause needs no condition.** Being collected only while the card sits in a graveyard *is* "as long as this card is in your graveyard", so `static_condition_keys` gained nothing.

### Eminence — a static that works from the command zone

`exclude_self` on `affects_spells`: On the battlefield the word is inert — a permanent's own spell is never on the stack while that permanent is in play — which is why it was not there before.

### Entwine — "choose both if you pay the entwine cost"

Entwine: The price needed nothing: entwine is an additional cost paid as the spell is cast, which is `kicker`, and legality already offers a kickable card twice. What was missing is that the two lines must ask **different questions** — the plain one asks which mode, the entwined one asks nothing.

## "You may choose both instead"

`up_to_if`: `ask_mode` grew a separate `max_count`. It had built every decision with `min_count == max_count` and short-circuited when `len(labels) <= count`, so "choose up to two of two" silently became "take both" without asking.

## "Choose up to two --"

`up_to`: A spell whose whole effect tree is one top-level `choose_mode` is answered at cast time by `Game._ask_modes` (601.2b) and never reaches `op_choose_mode` — the trap that once made `up_to_if` dead code for the card it was built for.

## Granting protection

`grant_protection`: The effect half of the `protection` static, which existed only as a printed ability on a permanent — `protection_from` collected from `_battlefield_statics` and never saw anything granted.

## Airbend — "exile them, and their owners may cast them for {2}"

`airbend`: The price lands on the new `ObjectState.playable_alt_cost` and is read by `casting._cast_options` beside `playable_free`, and by `Game._cast` off the same field: a card in exile under this permission has no printed-cost line beside it, so re-reading the board is safe here in a way it is not for `free_cast_permission`.

## Preventing all damage to a player for the turn

`damage_prevented` trigger: `EventType.DAMAGE_PREVENTED` had existed since absorb and was `emit`ted (logged) at two sites rather than `fire`d (put through the trigger bus) — the same shape `you_attack` and `token_created` had, and the reason the `TRIGGER_EVENTS` row alone would have produced a trigger that silently never fires. All three sites now `fire`, and each carries `to` (`"player"` or `"permanent"`) the way `DAMAGE_DEALT` does, so the trigger can take the player half without also paying out on a blocked absorb creature.

## "Whenever you attack"

`you_attack`: No new event: `ATTACKERS_DECLARED` was already produced once by `combat.py` after the declaration closes, and was `emit`ted (logged) rather than `fire`d (put through the trigger bus) — the same shape `token_created` had.

## "Whenever one or more creatures attack one of your opponents"

`creatures_attack_player`: `EventType.CREATURES_ATTACKED_PLAYER` is a **new** event fired beside `ATTACKERS_DECLARED` rather than a second copy of it.

## Granting an ability for as long as the permanent lasts

`grant_ability` `duration: "permanent"`: The option `grant_keyword` already carried. Without it every granted ability went into `until_eot` and was swept at cleanup — and a grant whose printed text names no duration is a strictly weaker card that way, identical on the turn it is made and gone by the next. `granted_abilities` reads both alike, so nothing downstream had to learn the difference — and `move_object` snapshots **both** into `left_with`, because a creature's death is exactly when a granted dies-trigger is asked about and neither list survives `reset_permanent_state`.

## An activated ability that gets cheaper

`Cost.mana_reduction`: Both card-level reductions discount *casting a spell* — a card's own `cost_reduction` and the `spell_cost_reduction` static — and both are read only from the cast path, so an activated ability's price was the literal string on the card at every board state.

### What the filter may say

Reduction filter keys: Takenuma's channel ability is the card that made that true: "{1} less for each **legendary** creature you control" wrote `supertypes` in a filter that read six keys and ignored the other fourteen, so it priced itself off every creature instead.

### …by the greatest mana value of a commander you own

`greatest_mana_value`: The filter widened with it, in three ways: It was always a legal key to *write* and was silently ignored, and it is the only thing separating your general from the identical legend somebody else cast. `controller` defaults to `"you"` only while the filter has said nothing about ownership, so every reduction written before this still means what it meant.

### …for each **legendary** creature you control

`supertypes` in a reduction filter: `supertypes` was one of the fourteen keys the reduction filter validated and then ignored — see [what the filter may say](#what-the-filter-may-say) above for the whole list and for why an ignored *narrowing* key always makes a card cheaper than it prints.

Channel legends: This is what the whole Kamigawa channel-legend cycle waited on: Boseiju, Otawara, Takenuma and Eiganjo all print the same clause on a `discard_self` ability activated from hand.

## A granted ability that fires on its own creature's death

Malakir Rebirth (granted dies-trigger): Granting a triggered ability worked, and until-end-of-turn worked. The one combination that did not was a granted ability firing on the *departure* of the creature it was granted to — Malakir Rebirth — and it failed twice over: - The leave-the-battlefield branch of `triggers._candidates` walked printed abilities only. Every other branch pairs that walk with `granted_abilities`; this one now does too. The tell that it was an engine problem rather than a card one: the byte-identical *printed* ability on the same creature always worked.

## A modal DFC whose other half is a land

Land MDFC: `second_face` already gave one card two independently playable halves; adventure, aftermath and split cards all use it.

## A transforming card is one answer, not two

Transforming DFC answers: The engine has shipped transforming DFCs for a long time — `card_of` picks a face, `back_face` links them, `bloodline_keeper` / `lord_of_lineage` is a shipped pair. Only the *authoring* path was missing: `collect_answers` read `answer["card"]` as a single dict, and a card that is two entries could not be written at all. An answer may now carry a `back` beside its `card`:

## Reflecting mana — "any color that a land an opponent controls could produce"

`reflecting`: The two abilities that carry the five-colour superset are `reflecting` and `in_commander_identity`, and reading that field off an opponent's Path of Ancestry told a Fellwar Stone it could produce all five colours instead of the one its controller's commander makes.

## Imprinted mana — "any of the exiled card's colors"

Chrome Mox: The card's other half needs nothing new.

## Classes

Classes: An `activation_condition` on `counters_on` is the near miss and was checked in full by the gap record: it cannot switch a static off, it does not stop level 2 being bought four times, and a `counter_placed` trigger on the invented counter fires again at level 3.

### "When this Class becomes level N"

`becomes_level`: The near misses, both named by the gap record: `ability_activated` fires when the level line is *activated*, a round of priority before the Class is level 2 and whether or not it ever gets there; `counter_placed` on an invented level counter fires again at level 3.

## Battles

cloak: Read against what the engine has, that is **manifest plus ward** and nothing else — the second sentence is 701.34c verbatim, which manifest already ships.

cloak: It is now literally `ward_ability({"mana": "{2}"})` — the same interned trigger every other [ward](#ward-with-a-cost) uses, since cloak's ward and a granted one are one ability at one price and were two only while the keyword had nowhere to put a cost.

cloak: Two readers had to learn about it, and missing either is silent: `triggers._candidate_abilities`, which skips a face-down permanent's abilities wholesale, and `stack.ability_of`, which resolves an ability *by index* off the source's card — index 0 on a cloaked permanent runs whatever the hidden card prints first. The second is no longer a cloak special case: every rules-supplied ability carries a negative index and `ability_of` answers all of them the same way, without reading the board.

## "…until this permanent leaves the battlefield" — giving it back

`return_to_origin`: Two ops filtered by origin would be two sentences where the printing has one — and there was nothing to filter on, since only the graveyard kept an arrival record (`graveyard_from`).

## "Return it to the command zone" — `return_to_command_zone`

`return_to_command_zone`: Every other zone already had a mover and the command zone had none. `DESTINATIONS` — the map the loader validates every written `destination` against — is hand, battlefield, graveyard, exile and the two ends of a library, and `"command"` is still deliberately absent from it: every op that reads that map pulls its pool out of a library or a graveyard, and no printed card puts the top of a library into a command zone. What was missing is a **battlefield departure**, so this is a bare op beside `return_to_hand` rather than a seventh entry in a table it would be wrong in.

## "Target opponent and up to one target creature they control"

Linked targets (Cloak and Dagger, Entwined): The *language* was already there — `{"target": "who"}` is an ordinary player spec and `select_players` has always understood it. Two things stopped it. - **The loader refused it by construction.** A target's own `controller` clause was validated with no siblings in scope, so a card that named one was told the target did not exist. It is now checked against the siblings declared **before** it — and against a Mapping clause on *any* kind, where the old gate only looked at `player` and `any` specs, which is why Cloak and Dagger's second spec (a `permanent`) slipped through unchecked. - **The enumeration could not have answered it.** Every spec's candidates were computed independently and multiplied at the end, so the linked spec resolved `{"target": "who"}` against a spec with no answer yet: no seats, no candidates, and a second target that could never be chosen. 601.2c is both the way out and the reason the clause is legal at all: every target is chosen at once, so what is legal is the **pair**.

Linked targets: An independent one is enumerated once and reused across every partial, which is what the old product did and is the shape of every card in the pool but this one. With no linked spec in sight that is exactly the old behaviour, since every partial saw the same options and so dies together.

## Targeting a card in exile

`card_in_exile`: The three zone-bearing kinds must now agree with their selector's `zone`, and each may leave it out because the kind already said it:

`card_in_exile`: No card in the pool wrote a mismatched one, so the refusals cost nothing.

## "Any number of target creatures"

`count: "any"`: `count` was an `int` baked into the card, and `enumerate_target_tuples` built subsets of exactly that size.

## "…the number of creatures those opponents control" — the players a spell targeted

Targeted players in a count: **No new vocabulary** — the spelling Cloak and Dagger uses for one seat reads a set of them unchanged.

`{"target": …}` player references: an undeclared id, or a `{"target": …}` naming a target whose kind is never a player (a `permanent`), is a load error. Both used to load and count nobody.

## A target that belongs to one mode

### On a triggered ability

Mode-owned targets on triggered abilities: An *activated* ability is still refused, and for the original reason: `legality` enumerates one activation per legal target tuple, so its targets are fixed before `Game._activate` asks which mode.

## "Target creature phases out"

`phase_out`: Phasing shipped as a keyword the untap step reads, and nothing else: the whole mechanism lived in `turn.py` behind two private functions whose only caller was the untap walk. This is the printed one-shot half, calling that same mechanism. Two things come free because they were already there — 702.26e takes whatever is attached along, and the untap walk brings the permanent back before its controller's next untap step.

## "…phases out until this enchantment leaves the battlefield"

`phased_out_with`: One is "treated as though it does not exist" (702.26c) and is **out of** `state.battlefield`, so an ordinary battlefield selector reaches nothing — which is precisely why this card could not be written before.

## "Enchanted permanent is a colorless land … and loses all other card types and abilities"

Imprisoned in the Moon: `set_types` already existed; the other three are new, and `lose_all_abilities` is the one that needed a subsystem.

### `lose_all_abilities`, and why `abilities_of` exists

`lose_all_abilities`: No effect could take an ability away before, so nothing had ever needed to ask what abilities a permanent *has* — five readers each walked `state.card_of(obj).abilities` and got the printed list:

### `grant_ability` as a static, and where the line now runs

`grantable_abilities`: `grantable_abilities` used to refuse anything but a triggered ability, on the grounds that a granted activated one "would be accepted here and then never appear". `abilities_of` is what changed that. For a while the line then stopped at mana abilities, because 605.3a kept them off `stack.ability_of`, which resolved an activated ability off its source's *printed* list. That line is gone too — see [A granted activated ability that uses the stack](#a-granted-activated-ability-that-uses-the-stack).

### A granted *static*

Granted statics: The line used to stop before this, and the widening needed **no new code in the pipeline at all** — which is the whole argument for it.

Granted statics: That severed edge is not new — it is the one recorded divergence from 613.8, already paid for — and it is exactly what stops static-grants-static recursion.

### `set_colors`

`set_colors`: Nothing in the engine could set a colour; `animate` overwrote them as a side-effect of an until-end-of-turn P/T replacement and that was all. It is load-bearing the moment it exists: the selector language reads `colors`, `not_colors` and `shares_a_color_with`, and `protection` reads `from_colors`, so a moon-imprisoned Sheoldred stops being a legal target for "destroy target black permanent".

## "It can't be regenerated."

`no_regeneration`: Terminate, Wrath of God, Rapid Hybridization and Pongify all print it, and until this key existed all four dropped it silently — the clause is not an ability, so no printed line went unclaimed and the residual gate had nothing to attribute.

`no_regeneration`: Refused on any op but `destroy`: nothing else replaces a destruction, so anywhere else it would be read by nobody — which is how the clause came to be dropped in the first place.

## "When that mana is spent to cast…"

`paid_by`: **Not a new event.** `paid_by` is a trigger filter matched against the *spell*, because `pay_mana` writes onto it which permanents' mana abilities made the mana that paid for it — the same seam `colors_spent` already used, at the same instant, for the same reason.

## "…then shuffle and put that card on top"

`search_library` to `library_top`: `destination: "library_top"` existed and did not work: `_search` moved the found card and *then* shuffled (701.19c), so it was placed on top and immediately shuffled back into a random position — a tutor that finds nothing, silently. The shuffle now happens first when the destination is the top of the same library, which is both the printed order and the rules order.

## "Whenever an opponent loses life"

`life_lost`: `LIFE_LOST` had existed since `lose_life` did and nothing subscribed to it.

`life_lost`: The turn ledger's `life_lost` fold moved to this event alone. It had been folded from `DAMAGE_DEALT` as well, which would now count a burn spell twice — and was already wrong for infect in the other direction.

## "If this creature hasn't been exerted this turn"

Exert / `set_turn_flag`: Exert needs no engine support and never did: it is an `attacks` trigger, a `may` and `skip_untap`. Combat Celebrant adds a guard, and the guard is the part that had no home — a **record of the choice** that is scoped to the turn.

## "Equipped creature" outside a static

`attached`: `attached` had lived only in `STATIC_FILTER_KEYS`, where `characteristics` reads it while applying a continuous effect — which is why "Equipped creature gets +1/-1" always worked and no *op* could reach the same creature. It is now also an effect-side selector key and a trigger-filter key:

## Sacrificing, and creating a token

`token_created`: `token_created` needed no new event: `TOKEN_CREATED` had existed since tokens did and was `emit`ted (logged) rather than `fire`d (put through the trigger bus).

## "Target player's graveyard" — scoping a zone to a chosen player

Selector `player`: `select_players` already understood `{"target": ...}`, `{"controller_of": ...}`, `"each_opponent"` and the rest; `_zone_owners` simply never asked it. The nearest thing before was `controller: "any"` with `count: "all"`, and it is not a near miss — it empties *every* graveyard at the table, which is Relic of Progenitus rather than Bojuka Bog.

## "It becomes a Vampire in addition to its other types"

`add_subtype` op, `{"chosen_type_of": "self"}`: It used to be accepted and coerced with `str()`, which put the subtype `"{'chosen_type_of': 'self'}"` on the permanent — a card that loaded, resolved, passed a zone assertion and was of no creature type at all.

## `change_text` — "replacing all instances of one creature type"

`change_text`: New Blood, and layer 3 (613.1c) — the layer the pipeline did not have, sitting between copy effects and the type-granting statics.

`change_text` (New Blood written as an `add_subtype` is a much weaker card): That is why the authoring worker refused it rather than approximating.

## Keyword counters — "with a vigilance counter on it"

Keyword counters: No new op. Rule 122.1c is "a keyword counter is a counter with a keyword ability's name, and a permanent with a keyword counter on it has that keyword ability", so the counter was always sayable — what was missing is that anything read it. `characteristics._compute` now folds every counter whose kind is a `Keyword` into the keyword set, in the **keyword-grant layer** rather than beside the `+1/+1` counters five layers later.

## Shield counters — the other counter kind the engine reads

Shield counters: **No new op, no new keyword, no new replacement entry.** A shield counter is rule 122.1c's other named kind, and like a keyword counter it was always *sayable* — what was missing is that anything read it. `zones.destroy` and `primitives.damage_permanent` now spend one, and `move_counters` was already enough for the rest of the card.

## Transforming double-faced cards

Transforming double-faced cards: That is the whole mechanic, because `card_of` is a single choke point: the characteristics layers, legality, combat and the serializer all go through it, so a transformed permanent shows its back face everywhere at once and none of them needed changing.

Transforming double-faced cards: The catalog stores the card under its joined name ("Bloodline Keeper // Lord of Lineage"), which neither face matches on its own, so `CardIndex.lookup` grew a `joined=True` mode.

## Gaining control of a permanent

`gain_control`, rule 400.3: This needed no code — `move_object` was always owner-based.

### …until end of turn

`gain_control` `duration`: `duration` is `"permanent"` (the default, and what every card written before this meant) or `"until_end_of_turn"`; **any other spelling is a load error**, which is the older refusal kept rather than removed.

## Cost reduction

### Making *other* spells cost more, in life

`spell_cost_increase`: `costs.cost_reduction` subtracts its total and clamps the result at zero, so `amount: -3` would load clean, print "costs 3 more" and charge the printed price — the loader now refuses a negative `amount` by name and points here.

## Kicker

### A permanent's own enters trigger can read it

Kicker on an enters trigger: So the flag is written onto the object at resolution and survives onto the battlefield, exactly as `cast_x` already did for "enters with X counters":

Kicker on an enters trigger (Slinn Voda): Worth knowing because of how this failed before: the card **loaded cleanly** — the half-a-kicker guard is satisfied, since something does read `kicked` — and the clause was then silently unreachable. You paid the extra {1}{U} and nothing happened. `{"kicked": ...}` now reads the resolution context *or* the object, which are the flag's two lifetimes and never overlap.

## Gift — a promise made to one opponent, for nothing

Gift: This is not decoration. The near miss that was measured before gift existed — `additional_cost: {}` with `additional_optional` and a `cmp` on `additional_paid` — *loaded and passed all six gates while its gift branch never ran once*, because `_additional_ceiling` offers times 0 and 1 at the same price and `verify.find_play` picks its line by `kicked`, which such a card never sets.

## Delayed triggers — "at the beginning of the next …"

`delay` `your_turn`: The two readings agree on your own turn, which is why the omission stayed invisible; the gap opens exactly where the word is printed, on an ability used at instant speed during an opponent's turn.

### "…return **that card** to the battlefield"

`counters` on `put_onto_battlefield`: **`counters` on `put_onto_battlefield`** is the "…with a vigilance counter and a lifelink counter on it" half, the same kind-keyed map `return_from_graveyard` has carried since persist.

### `duration` — "this turn", or "until it fires"

#### `until_your_next_turn`, and a subject of more than one object

`delayed_trigger` `subject`: `subject` now keeps **every** object it resolves to, and any one of them firing is a match — "whenever **either** of those creatures". It used to keep `chosen[0]` and silently watch one of two.

### `duration` — "this turn", or "until it fires"

#### Why this is a `delayed_trigger` and not a duration on `exile`

Palace Jailer's exile-until-event: Nothing was added to `exile`.

### "One or more creatures … one or more players"

`creatures_deal_combat_damage` is a new trigger event and the batched half of this card.

### "One or more creatures … one or more players"

#### "One or more **Dragons** … a player **or battle**"

`creatures_deal_combat_damage` (Zurgo and Ojutai): Three clauses, and each one was missing something: A `filter` written here used to be an ability that never fired, silently.

`or_battle`: It is a widening, so it is **off by default** -- "to one or more players" is printed on cards that say nothing about battles, and `_fire_damage_batch` now fires for a battle-only swing where it used to fire for nothing at all.

## "Choose a creature type"

### "…is the chosen type in addition to its other types"

`add_subtype` static with `chosen_type_of`: The other half of the family, and it took a change to say it: everything above **reads** the choice — "is that other object of the chosen type" — and Roaming Throne, Arcane Adaptation and Xenograft **grant** it.

So `{"chosen_type_of": "self"}` now stands on the **granting** side of an `add_subtype` static as well as inside a filter, and `AbilityModel.subtypes` is `list[str]` no longer for that one entry.

`add_subtype` op refusing `chosen_type_of`: Before the refusal existed it was worse than that — the op coerced the entry with `str()` and the permanent gained the literal subtype `"{'chosen_type_of': 'self'}"`: a card that loaded, resolved, passed a zone assertion and was of no creature type at all.

## "Choose a color"

`chosen_color_of` in `add_mana`: So `add_mana`'s `mana` had to accept the reference itself rather than the ability offering five modes; the loader refuses `{"chosen_color_of": …}` inside a `choose_mode` for that reason, and Heraldic Banner's proxy — which had been generating the five-mode version — is now the printed card instead.

## Embalm — an ability activated from the graveyard

Embalm: Cycling paid for most of the zone half; the graveyard joins the hand in `legality._activate_zones`. The safety rule is the same one and now has two ways to be satisfied: an activated ability offered outside the battlefield **must** have a cost that removes its source from that zone.

## A standing permission, and mana of any type

### `any_color`

`any_color`: Getting only one of them is the failure mode the `cast_from_library_top` work already hit once: the spell is offered, goes on the stack, and the payment quietly refuses.

## Ninjutsu — swapping into a combat already under way

Ninjutsu: Two missing words, one on each half. **`blocked`** is a new selector key and is *not* the negation of `blocking`. `Cost.return_to_hand` already existed, for Meloku.

Ninjutsu: **`attacking`** is `create_token`'s clause moved onto `put_onto_battlefield`.

## Banding — the engine was sorting a choice it could have asked for

Banding: Banding was the last `refused` row, and the recorded reason was that it "needs player-chosen combat damage assignment, which the engine automates for every creature". Half right, and the wrong half is the interesting one. The engine does not *lack* damage assignment order. It has had `CombatState.block_order` all along and has been **sorting it instead of asking** — by effective toughness, ascending. `ask_objects` records the order its options were taken in, which is exactly what a damage assignment order is, so the question needed no new `DecisionKind`.

Banding: `band_of` returns a band of one for anything not in a band, and `_ask_order` returns immediately when there is nothing to order, so **every combat without banding asks nothing** and behaves exactly as it did.

## Daybound and nightbound — one field for the whole table

Daybound and nightbound: This was `refused` as needing "a game-wide designated state the engine has no place to keep". That describes the problem exactly, and the answer is one field: `GameState.day_night`, the same shape `turn` and `step` already are. Everything else was already here:

## Phasing — "does not exist", said by not being in a list

Phasing: Phasing was `refused` as changing how the untap step works for every permanent in the game. It changes it for one permanent, once, and the reason it is cheap is the reason the merged pile was: the engine already has a place for an object that exists and is nowhere.

Phasing: The part that had to be written is **702.26e**: what is attached to a phasing permanent phases out *with* it and comes back with it, marked `phased_out_indirectly` so it follows its host rather than its controller's schedule.

## Meld — mutate's merged permanent, with the pair fixed by the card

Meld: Meld was `refused` as needing "a card-wide designated state the engine has no place to keep". By the time mutate shipped, the place existed: a permanent whose identity is a `CardDef` read through `card_of`, with the other card in `merged_under` so `move_object` sends the pair wherever it goes.

Meld: `CardDef.mana_value` reads that field first, and the engine's few direct `mana_cost.mana_value()` reads of a permanent were moved onto the property.

## Mutate — two cards, one permanent, and one synthesised `CardDef`

Mutate: The census called mutate the one genuine subsystem it had left: *"a `GameObject` is one card, and every choke point the other reversals leaned on — `card_of`, `chars`, `zones.move_object` — assumes exactly that."* The first half is true and the conclusion is backwards. **Because** `card_of` is a single choke point, a merged permanent can be one `CardDef` synthesised at merge time — the card on top, carrying the abilities of everything under it — and every reader gets the union with no changes at all: The subsystem the census feared is the *other* implementation — a list of cards per permanent, and every one of those readers taught to walk it.

Mutate: The pile itself is the one genuinely new thing.

## Bestow — the alternative cost that changes what the spell points at

Bestow is the seventh alternative cost in the engine and the first that is not only a price.

Bestow is **not** a second castable face, though the census filed it beside adventure.

## Fuse — the case where the answer is *both* faces

Fuse: `second_face` ships adventure, aftermath and the halves of a split card, and all three are one face **or** the other: `card_of` answers with exactly one, which is why fuse was left open when they landed. Fuse is the case where the answer is *both*, and the shape it needs already existed — it is **splice**.

## A second castable face — adventure, aftermath and split cards

Second castable face: The engine already had **two `CardDef`s over one `GameObject`**, because that is what `back_face` is. What it did not have is a second face that is *cast*, and that difference is the whole of the design:

## Face-down permanents — morph, megamorph and manifest

Face-down permanents: The census called this a subsystem, and it is — but a small one, because the engine already had the two things that make it hard elsewhere: `card_of` is a single choke point (built for `transform`), and `chars` is the single place derived characteristics are decided.

## Cipher — the third direction an exile link can point

Cipher: There are now three exile links, all written on the exiled card, and they name different things because the triggers reading them ask different questions:

Cipher: `encode` does **not** move the card, and that is the trap it fell into first.

Cipher: Epic needed the same `not is_token` guard, and both keywords make copies that resolve through the very code that armed them.

## Haunt — the exile link pointing the other way

Haunt: The engine already had an exile link — `exiled_by`, written on the exiled card and naming the permanent that exiled it.

Haunt: The haunting card is in exile with the link on it, which is why that ability carries `active_zones: ["exile"]` — the same widening the cycling trigger needed for the graveyard.

## Hideaway — "that one, from there"

Hideaway: The census listed hideaway as waiting on *two* things — face-down exile and play-from-exile — and it needed one. "Face down in exile" is `revealed_to`, which foretell already shipped. What was genuinely missing is that permission. The engine could exile a card, and could cast one for free, and had no way to say *"that one, from there"* — which is `play_exiled`, reading back the link the exile wrote.

Hideaway: Editing the library list in place is the obvious shortcut and it leaves cards whose `zone` still says `EXILE` sitting inside a library — caught here by a test, and worth stating because nothing else in the engine would have noticed.

## Keyword actions that are only a token

Token sacrifice costs: `stack.ability_of` looks the ability up through the source object and now falls back to the stack item's `def_id` when there is no object left; without that fallback every `"Sacrifice this token: …"` ability resolves as a silent no-op, which is precisely the failure a token with an approximated cost will never reveal.

### The near-miss token, and why it is silent

Near-miss tokens: Three pairs in the pool now differ by exactly one word:

Near-miss tokens: The five below the Eldrazi Angel came with the Atraxa superfriends deck, beside five with no neighbour at all (`wizard_2_2_u`, `fractal_0_0_gu`, `kor_ally_1_1_w`, `pirate_2_2_b_menace`, `tamiyos_notebook`); all ten are pinned in `tests/unit/tokens/test_atraxa_tokens.py`.

Near-miss tokens: The five above them arrived together, from one deck, and two of them show how the error compounds rather than staying cosmetic.

## Which mechanism a printed keyword lands on

Keyword routing: The sections below are the worked examples — they say why *this* card is shaped the way it is, which is what the residual gate needs, but they were each discovered separately and none of them generalises on its own.

## Landwalk, and global attack prohibitions

Landwalk: `not_keywords` existed in the effect-side selector language and not in the static one until this card needed it. And it is why landwalk had to be a real keyword rather than another static: a static cannot be *filtered on*.

### Can't attack or block **alone**

Can't attack or block alone: That put it where menace and `require_all` already live — the checks that only mean something once the declaration is complete:

Can't attack or block alone: `attacks_valid` is new, and its absence was half the gap: `blocks_valid` had existed since menace, and `finish_attackers` had no counterpart at all, so a correctly shaped static would have had nowhere to be enforced.

### The `cant_block` **op** — the same sentence with a clock

`cant_block` op: `grant_ability` cannot carry a *temporary* static either — a granted static is now allowed (see [A granted static](#a-granted-static)), and it is continuous: it lasts as long as the granter's filter matches and has no clock to end "until your next turn".

### The `unblockable` op — the same wire, read from the attacker's end

`unblockable` op: `grant_ability` cannot smuggle *this* static across either, and the reason is now the first two rows rather than the third.

### The `cant_sacrifice` op — a prohibition on a *game action*, not a zone change

`cant_sacrifice` op: Rule 701.17b, and the engine had nothing that could say it.

## Goad

Goad: Neither half was expressible, and the second half did not exist in the engine at all:

## Block restrictions

### Wither and infect

Wither and infect: `Keyword`s, not `replacements` entries, and the census routed them wrongly for a reason worth naming: the replacement whitelist is entirely about a permanent **entering the battlefield**, and neither of these is an entry event.

### Riot

Riot: So riot is a `Keyword`, and `grant_keyword` — which already existed — is the whole of the granted form.

Riot: `create_token` is not a generator and could not stop to ask, and the printed card this unblocks says nontoken anyway.

## Protection

### "Until your next turn" on a pump, a keyword, an animation or a lock

Until your next turn: Before this the key was read by none of the four ops, so a card that wrote it loaded and wore off at cleanup — before the only turns a planeswalker's +1 is printed for.

## Granting an ability

### A granted activated ability that uses the stack

Granted activated abilities: - **The op's grants are in `abilities_of`.** They were read only by `triggers`, so an op-granted activated ability was held and never offered: legality, the payment solver and `game._activate` all read `abilities_of`. The op's *activated* grants are now appended there with their provenance, like a static's; its triggered grants are not, because `triggers.collect` already yields those and would fire them twice.

## Cascade, ripple and `reveal_until` — walking a library

Cascade: The free cast was already there — `suspend.cast_for_free` — and the **scan** was not.

Cascade: **Haste is not shared.** It belongs to suspend, and a cascaded creature that could attack immediately would be a strictly better card, so `cast_for_free` grew an opt-in rather than granting it to everything that casts for nothing.

## Clash

Clash: `reveal` was never the missing piece — the **comparison** was.

## Rolling dice

Rolling dice: Reading a roll as objects now finds nothing, which is the truth: a die roll creates nothing to point at.

## Cycling

Cycling: **`active_zones` on an activated ability.** The field always existed and was read only on the *triggered* branch, so `_compile_ability` pinned every activated ability to the battlefield and silently dropped the schema's own `"hand"`. `legality._activate_actions` walks your hand as well now — **yours only**, because the hand is hidden and offering from an opponent's would leak its contents into `legal_actions`.

Cycling: Five things satisfy it, and the last two arrived with **unearth** and **forecast**:

Cycling: `resolutions_this_turn` already existed and is the wrong number: an ability whose first activation was countered has still had its go, and counting resolutions would hand it back.

Cycling: The guard was right about the property and too narrow about how to reach it: what matters is that the source cannot still be sitting there afterwards, however it left.

## Alternative ways to play a card

#### Casting from the graveyard

`flashback` is still accepted as the name the first keyword shipped under, and means exactly `graveyard_cost`.

#### An *alternative* cost that is not mana

`alternative_cost` is a full `Cost` plus an optional `condition` — the second alternative cost modelled that way, after `graveyard_cost`. It was a bare mana string until the pitch spells arrived, and there was simply nowhere on the card for a payment that is not mana to live: Force of Will's price is a life and a card, and Pyrokinesis's has no mana component at all.

`alternative_cost`: Two guards, and the second is the one that moved:

`alternative_cost`: `costs.can_pay` fails closed on all of them, so a card written that way would load clean and never once be offered the line — silently inert, which is the failure mode `exile_self` on a hand ability used to produce and the reason `exile_self_from_hand` exists at all.

#### An additional cost that is not mana

`additional_cost`: `kicker` was the only additional cost a hand-cast spell could carry, and it is wrong twice over here: it is **mana-only** — the cast variant is `mana_cost.plus(kicker)`, a `ManaCost`, which cannot sacrifice anything — and it is paid **once**.

Casualty's copy: **The copy needs nothing new.** "When you cast this spell" is a `spell_cast` trigger with `active_zones: ["stack"]`, so it goes on the stack *above* the spell and its copy resolves first — which is what 706.10 wants, and what a `copy_spell` written into `spell_effects` would get backwards.

#### "You may choose new targets for the copy"

`copy_spell` `new_targets`: **Opt-in, and that is the whole design.** The choice is a decision *per copy*, so a storm count of nine would ask nine times — which is why every copy kept the original's targets until a card needed otherwise. Storm, replicate, conspire, casualty, gravestorm and epic all go through the same `put_copy_on_stack` and none of them gained a prompt.

`copy_spell` `new_targets`: Retargeting is not a detail of the card that wanted it.

#### Demonstrate — "choose an opponent to **also** copy it"

Demonstrate: Two additions, and neither is a new `DecisionKind`.

`copy_spell` `controller`: Without it every copy the engine could make was yours: `put_copy_on_stack` took the controller as an argument and `op_copy_spell` only ever passed its own. A card written with the key anyway loaded clean and was ignored, because there is no effect-key whitelist — a copy silently under the wrong player.

`choose_player`: This is the piece that was missing, not the decision: `ask_player`/`CHOOSE_PLAYER` have been here since clash. What could not be said was *one* opponent.

#### Multikicker

`multikicker`: 702.32b, and **no new machinery at all** — it *desugars* to the three fields above: What the field buys is the **word**, and the word is not cosmetic: `verify.py`'s residual gate had no claimant for a printed line reading "Multikicker {1}{W}", so a card spelling the mechanic through the replicate slot loaded, played correctly, and was then rejected on its own first line.

#### Strive

Strive: Cast lines are one action per target tuple, and every tuple used to share one payment solved at the printed price; now `casting._priced_tuples` solves the price for zero, one, two extra targets and stops at the first it cannot pay, so a count the caster cannot afford is never offered, and the first line — the one an AI or auto-answer takes — is the largest affordable one.

#### Rebound

Rebound: Two halves, both nearly there.

Rebound: What is new is one clause, and it is the loop guard: **"if you cast this spell from your hand"**.

#### Foretell

Foretell: The census called suspend "the nearest shape". It is the *same* shape, and foretell shares its `ActionKind`: both exile a card from hand to be cast later, neither uses the stack, and neither can be countered. **"Face down" here is `revealed_to`**, the private-information channel Glasses of Urza built. Foretell needs only the first, which is why it ships and morph does not.

#### Dredge, madness and miracle — replacements that stop to ask

Dredge, madness and miracle: What they were really waiting on is that **drawing and discarding had to become things that can suspend** — and that turned out to be small, because `turn.begin_step` already ran through `Game._run`. The turn structure could carry a decision all along; only `_draw_step` beneath it could not.

#### Disturb

Disturb: Both halves shipped years apart and had never met: `graveyard_cost` is the cast, generalised for flashback, jump-start and escape, and `transformed` is the face, built for Bloodline Keeper.

### The monarch

The monarch: The mechanic is `state.monarch`, one optional player id — beside `day_night` and for its reason: it belongs to the **table**, not to a player or a permanent, and `rules-coverage.md` called it "a designated-player mechanic the engine has no place to keep". Day/night found the place, so this is the same field with rules hung off it.

### "You win the game"

`win_game`: It is the first op to reach a game **result** at all: everything that had ever produced a winner did it by arithmetic — `damage` and `lose_life` take a seat to zero, `add_poison` takes it to ten — and `sba.check_game_over` noticed afterwards. Neither card here is about a life total, so there was no approximation to make, only a missing sentence.

### Flashback

Evoke on an instant: The flag is written onto the object **before** `spell_effects` run as well as after, the moment `cast_overloaded` and `cast_cost_option` are written; written only afterwards, as it was while every reader was an enters trigger, the `if` read `False` on every instant and the card was a two-mana exile with no drawback.

Warp: This was the last card-level alternative cost without a claimant, and nothing had hit it because the only warp in the shipped pool was the `grant_warp` static above, whose line that static's own `text` already claims — so a correct warp card loaded, offered both cast lines, exiled and came back, and was still rejected as half-implemented.

### "When you cast this spell…"

"When you cast this spell": `_candidate_abilities` scanned the battlefield, the command zone, the graveyard, the hand and exile — every zone except the one place this card lives at the moment it speaks.

"When you cast this spell": The stack is scanned for triggers now — it is the one zone a card is in at the moment that line speaks, and `_candidate_abilities` had covered every other one.

Retrace: The additional cost reuses `Cost.discard_selector`, which already existed for "discard a land card".

## "During their turn" — whose turn a trigger means

`is_active_player`: `"active_player"` was already a member of `PLAYER_SPEC_NAMES` — what was missing was any way to *ask* about it.
