# Rules coverage

This is the honest artifact. It says what the engine does, where it takes a shortcut,
and what it refuses to model at all. If you want to know whether this engine can
handle your card, read this page: what is implemented, simplified, absent, and how
that is enforced.

The short version: **everything the shipped decks need is implemented and tested.**
The simplifications below were chosen so that removing them later is additive work,
not a rewrite.

Each row names the rule, what is modelled, and the op, static, field or module that
carries it. Where a mechanism diverges from the printed rule, the divergence is a row
under [Simplified](#simplified); what is missing outright is under
[Not implemented](#not-implemented).

## Implemented

### Turn and priority

| Area | Detail |
|---|---|
| **Turn structure** | Every step and turn-based action, cleanup repeating per 514.3a, and priority windows, walked by `turn` over the `Step` enum; the `step_is` condition leaf reads the step the game is in |
| **Additional combat and main phases** | 506.1, 505.1b: `GameState.extra_phases` queues granted phases and `resume_step` is the bookmark the turn returns to; an extra combat is inserted before the combat already owed, the additional main is a `POSTCOMBAT_MAIN` step and not an extra land drop, and an unspent grant expires with the turn |
| **"At end of combat"** | The `delay` step keyed to `GameState.combat_number` (603.7), so a delay created in one combat of a multi-combat turn fires at that combat's end |
| **Priority** | APNAP order, retaining priority after acting, auto-pass when passing is the only option, except for a human facing an opponent's removal, sweeper or targeted effect |
| **The stack** | LIFO resolution, responses, countering, fizzling when every target is illegal (608.2b); "unless its controller pays {N}" bills the targeted spell's controller via the `controller_of_target` player spec (109.5, 608.2); `return_spell_to_hand` removes a spell without countering it (701.5a, 706.10) |
| **Split second** | 702.61a: priority is kept, casting and non-mana activations are withheld while the spell is on the stack, mana abilities and special actions survive |
| **State-based actions** | Every action listed in [engine-rules.md](engine-rules.md), plus ten poison counters (704.5c) and the Role rule (704.5y, 303.7a, `attached_timestamp`) |
| **Phasing** | 702.26: a phased-out permanent leaves `state.battlefield` and stays in `state.objects`, attachments phase with their host (702.26e, `phased_out_indirectly`); `phase_out` with `until_leaves` and `phase_in` with `tapped` (Oubliette), the link `phased_out_by` read by `phased_out_with` |
| **Daybound / nightbound** | 726: `GameState.day_night`, switched as a turn-based action from `TurnLedger.spells_cast`, neither day nor night until a daybound permanent exists |
| **The monarch** | 721: `GameState.monarch`, the end-step draw as a turn-based action, the combat-damage transfer read before the damage batch (510.2), the crown handed on when its holder leaves (721.5); `is_monarch` and `no_monarch` condition leaves, and `is_monarch` as a static condition, naming the held permanent's controller on `skip_untap_step` (Fall from Favor) |
| **State triggers** | 603.8: the `state` trigger event, its condition in `TriggerSpec.state`, checked by `triggers.check_state_triggers` after each state-based-action pass; not retriggered while pending or on the stack, and not re-asked on resolution |
| **Ascend / the city's blessing** | A state trigger in the state-based-action pass setting one-way player state, read by `has_city_s_blessing` |
| **Skipping a turn-based action** | 500.1, 504.1: `skip_draw_step` player-wide static removes the draw and leaves the step, its event and its triggers in place |
| **Extra turns** | 500.7: `extra_turn` op onto the `GameState.extra_turns` stack, `turn_order_idx` so the table resumes at the right seat, `previous_active` for 726.2; `skip_extra_turn` static replaces the turn as it would begin (614.1b, 614.10) |
| **Delayed triggers** | 603.7 both ways: `delay` fires at a named step (`your_turn` for "your next"), `delayed_trigger` watches an event with `duration` in `structs.DELAYED_DURATIONS` (`this_turn`, `until_it_fires`, `once_this_turn`, `until_your_next_turn` per 611.2b), scoped by `subject` and `recipient` (`triggers.RECIPIENT_KEYS`) and released when the object leaves (400.7) |
| **Multiplayer and mulligans** | N players, turn order that skips eliminated seats, elimination mid-combat and mid-resolution, per-source commander damage; the London mulligan with the bottoming step |

### Casting and costs

| Area | Detail |
|---|---|
| **Casting** | Timing restrictions (sorcery speed, instant, flash), targets chosen at cast time (601.2c) and re-checked on resolution (608.2b); `stack.push_spell` stamps `cast_step` (read by `cast_during` for addendum), `cast_kicked`, `cast_evoked`, `cast_overloaded`, `cast_from_graveyard` and `cast_additional` onto the object before `spell_effects` run |
| **Costs** | Mana, tap, untap, sacrifice, discard (including this card), pay life (inside `may`, a value expression read with the resolving effect's bindings, 119.4), remove counters, put counters on the source (`put_counters`, a placement that raises `counter_placed`), exile from graveyard, `tap_permanents` (with `count`, `total_power` for crew, or `as` for station), `sacrifice` with `as` (a snapshot of the sacrificed permanent's last-known characteristics, activated abilities only), `untap_permanents`, `remove_counters_from_among`, `exile_from_hand`, `exile_self_from_hand`, and `exert` (702.121a); the non-mana half is paid after the mana (601.2g) |
| **X costs** | X is a `choose_x` decision before payment (601.2b); `Cost.x_value` prices a defined X without asking; `x` on `may`'s `pay` announces X at resolution under `max`; `any_amount` on `may` counts one coloured symbol paid N ≥ 1 times, capped by what that symbol can be paid with (107.1c, Leyline Tyrant); `cost.loyalty_x` for −X loyalty (606.4, 107.3) |
| **Kicker, multikicker, escalate and buyback** | `kicker` with the `kicked` condition readable from the battlefield; `multikicker` (702.32b) and `escalate` (702.120a) desugar to `additional_cost` + `additional_optional` + `additional_repeatable`, escalate's count fixing how many modes the cast chooses; the mana half is charged by `Game._cast` as `_cast_variant` priced it; `buyback: true` is a hand rider on the resolving spell |
| **Additional costs that are not mana** | `additional_cost` as a full `Cost` (casualty, replicate, "sacrifice an artifact"), one cast line per number of times paid, read back with `additional_paid`; `additional_cost_options` for one of several prices; `spell_cost_increase` static taxes somebody else's spell in life or generic mana (`player_statics.spell_life_tax`, `spell_mana_tax`), unpayable meaning uncastable (118.4) |
| **Spree, strive, gift and entwine** | `spree` (702.166a) offers one cast line per non-empty subset of priced modes with `spree_mode` as the membership test; `strive` prices every target count as its own line (601.2f, `casting.strive_surcharge`); gift (702.164a) is a free 601.2b choice naming a seat (`Action.gift_to`, `gift_promised`, `gift_recipient`), and a target spec's `gift_promised` declares it on one side of the promise only (601.2c, `CardDef.gift_targets`); entwine is `all_if` on `choose_mode` beside a `kicker` (702.42a) |
| **Evoke, dash, blitz and warp** | One slot: an alternative mana cost offered from hand, `evoke_label` for what the action calls it, `evoked` read back; warp adds the rules-supplied end-step exile and `playable: "later_turns"` in `stack._place_after_resolution`, and `grant_warp` is the player-wide static that hands the cost to other cards |
| **Conditional and non-mana alternative costs** | `alternative_cost` is a full `Cost` plus optional condition: spectacle, Force of Will, Daze, Sephara's tap clause (302.6 restricts only the source's own {T}) |
| **Casting from the graveyard** | `graveyard_cost` (flashback, jump-start, escape) with `graveyard_cast` for where the card ends, retrace by discarding a land, `cast_from_graveyard` readable inside `if`; the `cast_from_graveyard` static and the turn-long any-graveyard form (Yawgmoth's Will) read by `graveyard_cast_permissions`; the same static with `active_zones: ["graveyard"]` is a permanent card's own conditional permission (Gravecrawler), read by `own_graveyard_cast_permission` as the cast is offered (601.3) |
| **Disturb and bestow** | Disturb is `graveyard_cost` plus `cast_transformed`, the back face shown from cast time and re-applied after the move (712.13a); bestow (702.103) is an alternative cost whose `BESTOW_TARGET` supplies "enchant creature", with `chars` making the permanent an Aura while `attached_to` is set and a creature when it is not (702.103e) |
| **Impending** | 702.176a: `impending` is an alternative cost offered from hand (`Action.impending`); paid, an implied replacement gated on `{"impending": true}` puts the time counters on, `chars` drops `Creature` (and its subtypes) while `cast_impending` holds and a time counter remains, and the loader appends the end-step trigger that removes one; any arrival but its own resolution clears the stamp (400.7) |
| **Emerge and offering** | One cast line per sacrificed creature reduced by its mana value, `emerge_subtype` read off derived characteristics |
| **Convoke, improvise and delve** | 702.51, 702.126, 702.66: creatures tapped, artifacts tapped or cards exiled pay generic mana, one cast line asking which permanents or cards as it is paid ([ADR 0020](adr/0020-convoke-is-one-line.md)), tapped before the mana so a permanent cannot pay twice, netted into the same `extra` the commander tax uses |
| **Overload** | 702.96a: the card writes both halves and branches on `overloaded`; the overload line is cast with no targets, so every target spec must be `optional` |
| **Mutate** | 702.140: a merged permanent is one `CardDef` synthesised through `card_of`, the pile in `merged_under`, over-or-under asked at resolution (702.140b) |
| **Prowl, splice and fuse** | Prowl is gated on `TurnLedger`'s record of who dealt combat damage this turn; a spliced card is revealed, not spent, and its effects run in the host's `EffectContext`; fuse (702.102a) is a third cast line built from both halves as one `CardDef` |
| **Cost reduction** | Card-level reductions and the `spell_cost_reduction` static through one function (`costs.reduction_amount`): `amount`, `count`, `total_power`, `greatest_mana_value` (903.3's `owner`), `greatest_count` (per-controller maximum), `supertypes` counts, a `condition`, and `Cost.mana_reduction` on an activated ability or graveyard cast |
| **Cast triggers** | "When you cast this spell" via `active_zones: ["stack"]` |
| **Cast locks** | `cant_cast_spells` static with `affects_spells` (including a mana-value floor, `cast_lock_min_x`, 202.3e) enforced at every cast lane including resolution-time casts (101.2); `cant_cast_spells_from_zones` as a timed `CastLock` op and as a static (903.8 reaches commander casts); `cast_only_at_sorcery_speed`; epic's lock in `_cast_actions` (702.50a) |
| **"You can't cast this during your first turns"** | `cant_cast_first_turns` on the card, read by `player_cant_cast_spells` against `PlayerState.turns_begun` (each seat's own turns, extra turns included) on the caster's own turns only |
| **Cast permissions** | `cast_as_though_flash` static, narrowed by an optional `affects_spells` (Shimmer Myr), and the `grant_flash_permission` op (`FlashPermission`, `casting._timing_ok`); `free_cast_permission` static priced on `casting.FREE_COST` with `from_zone` (Omniscience, Dracogenesis) and recorded on `Action.cast_free`; `granted_alternative_cost` static (118.9) offering an energy or life price beside the printed line, mana half free, additional costs still owed (118.9d), price recorded on `Action.granted_cost` (Nissa, Worldsoul Speaker); `airbend` op holding a flat `playable_alt_cost` (108.3 owner); `cast_from_library_top` off the top card, priced in life (Bolas's Citadel, `Action.from_library_top`) or narrowed by an object-matched `affects_spells` at the printed cost with a `cast_gains_keywords` rider (Thundermane Dragon) |
| **Playable permissions on a card** | `playable_by` with durations `this_turn`, `until_your_next_end_step`, `until_end_of_your_next_turn`, `later_turns` (plot, 702.171a) and `while_exiled`, ended by `turn._expire_permissions` or `reset_permanent_state` (400.7); `playable_free`, `playable_sorcery_only`, `any_color`, `min_colors`; `grant_playable` with `any_type` (609.4b); `play_exiled` for hideaway; `cast_from_hand` over a `zones` union or a named `objects` pool, `per_owner` for one cast per owner; `look_at_top`'s `cast_free` |
| **Suspend, foretell, rebound and plot** | Suspend's special action, upkeep tick, free cast and haste; foretell (702.143a) shares its `ActionKind` with `revealed_to` and `foretold_turn`; rebound (702.87a) is an exile rider plus the free cast gated on `cast_from_hand`, with `grant_rebound` for a spell on the stack; plot exiles in `_place_after_resolution` and grants `playable: "later_turns"` |
| **Free casts at resolution** | `suspend.cast_for_free` is shared by suspend, rebound, cascade, discover, `exile_until`, ripple, `cast_from_hand` and `play_exiled`; it uses the stack and can be countered; haste belongs to suspend alone |
| **Prepared** | `obj.prepared`, `prepared_face`, the `self_enters_prepared` replacement and `become_prepared`; the copy is cast from the battlefield as a token (111.7) and `Game._cast` unprepares |
| **Deck-construction sentences** | 903.3: `CardDef.can_be_commander` read off the card's own text, required by `validate_deck` beside a legendary creature; 903.5b: `CardDef.any_number_in_deck` and `deck_copy_limit` matched against the card's own name |

### Mana

| Area | Detail |
|---|---|
| **Mana** | Cost parsing, pools emptying per step (500.4) except the symbols a `mana_retention` player-wide static keeps across every boundary, the end of the turn included (Leyline Tyrant, Upwelling), and mana a `mana_becomes_colorless` static turns into {C} instead of losing (Kruphix, Horizon Stone); the pool is a static input through `unspent_mana_count`, re-read because every pool funnel bumps `char_version`; automatic payment with a backtracking solver, X; a seat may opt into manual mana (`PlayerState.manual_mana`, `offer_all_abilities`) |
| **Hybrid and Phyrexian mana** | `{W/U}` and `{2/W}` parsed, paid and counted towards colour identity; `{W/P}` (107.4f) is a hybrid pip whose other half is 2 life, one cast line per pip bought with life (118.4), every other cost asking while paying; `black_mana_as_phyrexian` (K'rrik) reads each `{B}` as `{B/P}` |
| **How a mana ability names its colours** | Six spellings on `add_mana`, all narrowed in `costs.mana_options_of` without asking (605.1a): fixed symbols; `reflecting` asks named permanents what they could produce, `any_type` widening it to colorless (106.1b); `colors_of` offers named cards' printed colours (Chrome Mox, 105.1); `each_color_among` returns one bundle of one mana per distinct colour (Bloom Tender); `any_one_color` plus `mana_amount` (Helga); the supersets stay out of colour identity (903.4) |
| **A trigger that rituals X mana in any combination of colors** | `split` on a non-mana `add_mana` asks one `ask_mode` per mana; the restriction rides the pip (`Pip.restriction`, `ManaPool.spendable`, `engine.mana.compile_restriction`) |
| **Variable mana abilities** | `amount` on `add_mana`, evaluated at activation where the solver and the payout share one point (605) |
| **Restricted mana** | `mana_restriction` with `cast` and `activate` halves and an `other` half for every payment that is neither (ward, taxes, "you may pay", special actions; `mana.OTHER_PAYMENT`), groups as any-of of all-ofs, `{"not": …}` for "noncreature", `"any"` for "only to activate abilities", `mana_value` and `x_in_mana_cost` predicates (107.3), and `{"chosen_type_of": "self"}` substituted per permanent |
| **Spending mana as though it were any colour** | `spend_mana_as_any_color` player-wide static (Chromatic Orrery; `affects_spells` for Oath of Nissa) and the per-spell `any_color` flag, priced by `ManaCost.as_any_color`; `{C}` is never loosened and colourless may be spent as a colour |
| **The colours of mana actually spent** | `colors_of_mana_spent` read off `ManaPool.spend`'s record, surviving onto the battlefield (sunburst, converge) |
| **A rider on mana that outlives the spell** | `mana_grant` on the pip, snapshotted past `reset_permanent_state` for a battlefield destination only (Arena of Glory); `mana_uncounterable` (Cavern of Souls) is read while the spell is on the stack |
| **Triggered mana abilities on tapping** | 605.1b: `add_mana_on_tap` player-wide static read inline at the mana choke point (Crypt Ghast), matched on what was tapped or, with `produced`, on the mana the tap made, per option and once per tap (Forsaken Monument) |

### Combat

| Area | Detail |
|---|---|
| **Combat** | Attacker and blocker declaration, evasion, damage assignment order, simultaneous damage (510.2), first and double strike as separate sub-steps (510.4) |
| **Declaration-wide restrictions** | 508.1c, 509.1b: menace, `require_all`, "can't attack or block alone", enforced by withholding "Done" and by `combat.drop_illegal_attacks` / `drop_illegal_blocks` |
| **Banding** | 702.21: two `ask_objects` questions for the band, `CombatState.band_of`, and `_divide` walking 510.1c for whichever player orders the damage |
| **Attack requirements** | `must_attack` op, `attacks_if_able` static and the `goad` mark (701.38a, `GameObject.goaded_by`; "for the rest of the game" in `goaded_permanently_by`, spared by the goader's untap step and ended when the goader leaves, 800.4a), all read by `combat.attack_required` and always "if able"; `must_attack_planeswalker` (508.1d, `must_be_attacked_by`) |
| **Attack restrictions** | `cant_attack` and `cant_attack_you` statics (the latter reaching its controller's walkers and battles unless `player_only`, its filter read off the attacker's current characteristics), the `cant_attack_player` op on `GameState.attack_restrictions` (a seat, a seat and its walkers, or only walkers of named subtypes), and `attack_tax` with `or_planeswalkers`, all through `combat.attack_target_forbidden`; attacking a planeswalker is not attacking its controller (506.2) |
| **Block requirements and restrictions** | `must_block` (provoke), the `cant_block` static and op (`GameState.block_prohibitions`), the `unblockable` op (`GameState.unblockables`, with an `except_blockers` exemption read off the blocker's derived characteristics), `block_restriction` (a filter on the blocker, `require_all`, or `max_blockers` per 509.1b), and `block_tax` charged per blocker (509.1d–e); detain (701.30a) as one op recording the detaining player |
| **Defenders other than the player** | 506.2's third defender kind for planeswalkers and battles (`combat.attacking_permanent`, `attackers[oid]` still the defending player); the `attacking_player` selector key (508.1b); `attacking` taking a player spec and `or_planeswalker` asking the controller (508.4) on `create_token`, `copy_permanent` and `put_onto_battlefield`; `damage`'s `defender_of` hits the player or planeswalker a creature is attacking, read at resolution |
| **Reselecting an attack** | `redirect_attack` moves a creature already attacking to another of 506.2's attack targets, chosen by the effect's controller, never its own controller or their permanents; nothing is declared, so declaration restrictions and attack triggers are not consulted (508.4's reading), and blocks follow the new defender |
| **Ninjutsu** | The `blocked` selector key and `attacking` on `put_onto_battlefield`; the ninja was never declared (508.4) |
| **Batched combat events** | `EventType.CREATURES_DEALT_COMBAT_DAMAGE` once per damaging player per damage step with `damagers`, `damaged`, a `filter` over the damagers and `or_battle` (310.6), or once per damaged seat with `per_player`, binding that seat as `defender`; `creatures_attack_player` fired by `finish_attackers` per defending seat with `defending` and the `attackers` binding |
| **"One or more" triggers** | 603.2c: `batched` queues a trigger once per simultaneous group, after its `filter`, on the events in `triggers.BATCHED_EVENTS` -- `permanent_enters` and `leaves_graveyard` grouped by the effect op or cost payment (`state.event_batch`), `token_created` by the `primitives.create_token` call, doubled and substituted tokens included, `attacks_unblocked` by the block declaration (509.1h, `combat.finish_blockers`); refused by the loader elsewhere |
| **Combat damage by a permanent** | `deals_combat_damage` (any recipient, once per dealer per step, 510.2), `deals_damage_to_player` (combat or not, off `DAMAGE_DEALT`), `dealt_damage` from the victim's side, sharing `EVENT_HALVES` |
| **Fight** | 701.12: simultaneous, all-or-nothing, each blow dealt by the creature |
| **Crew and station** | `total_power` on `tap_permanents` read off derived power; `crew_power_bonus` static read by `costs._crew_power` alone; station (702.184) written out with `as` and `power_of {"binding": …}`, power read as the ability resolves or as the creature last existed (`GameState.paid_objects`); station symbols as `threshold` on an activated ability, absent from `abilities_of` below the number (113.7a) |

### Keywords

| Area | Detail |
|---|---|
| **Keywords** | flying, reach, trample, deathtouch, lifelink, vigilance, haste, menace, first strike, double strike, defender, hexproof, shroud, indestructible, flash, the six landwalks, skulk, fear, intimidate, horsemanship, shadow, wither, infect, toxic, totem armor; `partner` and `choose_a_background` are `INERT_KEYWORDS` (deck-construction rules, 702.124); every keyword's status is censused in [keywords.md](keywords.md) |
| **Protection** | From a type, subtype or colour across damage, enchant/equip, block and target; `from_colors_outside_commander_identity` (Commander's Plate, 903.4), `from_colorless` (105.2c) and the chosen card type (`chosen_card_type_of` in `from_types`, read at each check); a player's protection — the timed grant (Teferi's Protection) and the `player_protection` static — read by `player_protection_from` across damage, target and enchant |
| **Ward, including granted ward** | A `ward` static with a full `pay` cost and `affects`, `carddef.ward_ability` interning one trigger per cost, fired as the spell goes on the stack (603.2d) with the warded permanent as source and a negative `ability_index` |
| **Energy** | 107.14, 122.1: `PlayerState.energy`, given by `add_energy` through the `primitives.add_energy` funnel (counter replacements that reach players apply), proliferated like poison, never a loss condition; spent by the `pay_energy` cost, payable only with at least that many and never by the mana solver |
| **Wither, infect, toxic and poison** | 702.90b, 702.90c: keywords read by `damage_permanent` and `damage_player`, still damage for deathtouch, lifelink and the ledger; toxic (702.164) adds `CardDef.toxic` poison on top of a combat hit to a player, read on derived keywords, never granted; `add_poison` with its own `LossReason` at ten (704.5c); corrupted reads the most poison on one player through `max_poison_of`, re-read by statics because the `add_poison` funnel bumps `char_version` |
| **Regeneration and totem armor** | 701.15, 702.88a: both at `zones.destroy`, regeneration a spent-once shield cleared at cleanup, totem armor a `Keyword` on the Aura; `no_regeneration` on `destroy` (701.15c); `KEYWORD_ALIASES` folds "Umbra armor" |
| **Shield counters** | 122.1c: `spend_shield_counter` at `zones.destroy` and `primitives.damage_permanent`, one counter per event, not indestructible and not regeneration |
| **Stun counters** | 122.1d: `primitives.untap_or_stun` at the untap step, `untap_permanent` and an {Q} cost, one counter removed instead of each untap; an untapped permanent keeps its counter |
| **Finality counters** | 122.1g: read, never spent, by `zones.move_object` on a battlefield-to-graveyard move, which becomes exile; after the commander replacement and before `replace_dies` (616.1), so a finality-countered creature never dies and makes no Kalitas Zombie |
| **Absorb** | 702.63a: the `prevent_damage` static, per source and per instance |
| **Riot** | 702.113: a `Keyword` whose content is a 614.1c replacement, `zones.offer_riot_choice` asked on every arrival that can stop; grantable |
| **Exalted** | 702.83: a `Keyword` whose content is the rules-supplied `carddef.EXALTED_TRIGGER`, one per permanent with it; grantable; a permanent holding it twice triggers once |
| **Dethrone** | 702.105: a `Keyword` whose content is the rules-supplied `carddef.DETHRONE_TRIGGER`, the `defending: "most_life"` clause on `attacks` (a player, not a planeswalker or battle, whose life is at least every living player's, asked as part of the event and not re-checked); grantable; a permanent holding it twice triggers once |
| **Abilities that work from hand or graveyard** | Cycling (702.29) as an activated ability from hand whose cost discards the card, with the `cycle` event fired before the draw and carrying the X paid in the cycling cost; embalm and eternalize from the graveyard paying by self-exile, a token copy with `except_` (702.129a); unearth, whose unconditional top-level self-move satisfies the outside-the-battlefield guard, with `replace_leaves_battlefield` for "or if it would leave"; forecast under `activate_steps` plus `once_each_turn` |
| **Epic** | 702.50a: a one-way cast lock and a rules-supplied upkeep copy through `put_copy_on_stack`, `epic_source` guarded by `not obj.is_token` |
| **Cascade, ripple and `reveal_until`** | Library scans sharing `_bottom_in_random_order`: cascade exiles and free-casts, ripple compares the source's name, `reveal_until` takes the card's own `objects` as stop test, an `amount` of matches moved as one arrival (`triggers.entering_together`, 603.6a) under the scanned seat or `controller: "you"` (110.2), and bottoms or `shuffle_rest`s the rest |
| **Discover (701.57)** | `discover` walks like cascade with a bound of N or less, puts a card it does not cast into hand, and records the discovered card under `as` (empty when nothing was found) |
| **Exile until a card matches** | `exile_until` walks with a selector stop test and leaves the walked-past cards in exile; the hit is offered free behind an optional `cast_free_if` selector, and an uncast hit goes to `else_destination` or stays exiled |
| **Behold** | The `behold` op and the `behold` cost share `effects.behold.behold_pool`: a matching permanent you control or a matching card from your own hand, the hand card revealed to the table; the op's "if you do" runs only after a behold, and a spell paying the cost never beholds itself (601.2a). "Behold … and exile it" is not modelled |
| **Hideaway, haunt and cipher** | Exile links read from either end: hideaway's `play_exiled` reads `exiled_by` back with `revealed_to` hiding the card; haunt's `haunting` is read by the `haunted_by` filter from `active_zones: ["exile"]`; cipher's `encoded_on` is a rider on the resolving spell with `cast_copy` (702.97b) |
| **Explore, connive, clash, fateseal, proliferate** | `explore` (701.40a), `connive` counting the nonland cards it discarded (701.47a), `clash` binding `clash_won` (701.23a), `scry` with a `chooser` for fateseal, `proliferate` as one `ask_targets` over every countered permanent and every player with poison or energy (701.27a) |
| **Keywords built from bindings** | Devour and amplify read `as` on `sacrifice` and `reveal`; graft and modular are `move_counters`; persist and undying read `counters_had` snapshotted onto the dies event; evolve reads the event's bindings in its intervening-if; bolster is the `extreme` selector clause keeping ties (701.36a); kinship is a `snapshot` of the top card plus `shares_a_type_with` |
| **Keywords built from flags and costs** | Renown is `set_flag` / `has_flag`; exert is `set_turn_flag` / `has_turn_flag` on `TurnLedger.object_flags` (701.40b) and the `exert` cost; monstrosity has its own field, event and trigger, and the `is_monstrous` static condition reads the field (701.37b); echo is `set_flag` written by the ability that reads it (400.7 resets it); an "as this enters, choose X or Y" mode is `choose_mode` + `set_flag` on the source, read by `has_flag` in a trigger's or a static's condition; cumulative upkeep is `times` on `may`'s `pay`; level up is a counter plus `set_pt` and `grant_keyword` statics gated on an interval |
| **Soulbond, aura swap and reconfigure** | A symmetric `paired_with` with `paired` and `paired_with_source` filters; aura swap as one atomic op attaching after the move; reconfigure as `attach` (Equip), `unattach`, and `set_types` under `is_attached` (702.151d); `attach`'s `attachment` sub-key moves something other than the source (701.3), and `attach` refuses self-attachment (301.5c) |
| **Extort and demonstrate** | Extort (702.101) written out by `templates.extort_ability`; demonstrate as `copy_spell` with a `controller` player spec and `choose_player` binding one seat, each copy's controller answering `new_targets` (115.7b) |
| **Compleated** | 702.150a: `GameObject.cast_phyrexian_life` removes two loyalty per symbol in `zones._enter_battlefield`, on that arrival only |
| **Empower** | The `empower` op: loyalty counters on one Jace token you control, the blue 0-loyalty Jace planeswalker token (`EMPOWER_TOKEN`) created first only when you control none, both in one effect so 704.5i looks only afterwards |
| **Amass** | The `amass` op (701.47): +1/+1 counters on one Army creature you control, the 0/0 black Army token of the named subtype (`AMASS_TOKENS`) created first only when you control none, both in one effect so 704.5f looks only afterwards; the Army gains the subtype permanently and `as` records it ("the amassed Army") |
| **Incubate** | The `incubate` op (701.53): the double-faced Incubator artifact token (`INCUBATOR_TOKEN`, back face a 0/0 colorless Phyrexian artifact creature) created with N +1/+1 counters as one placement (122.6), so only an artifact-applicable counter replacement modifies them; "{2}: Transform this artifact" is the ordinary `transform` |

### Triggers

| Area | Detail |
|---|---|
| **Triggers** | ETB, dies, leaves-the-battlefield, landfall, land-played, spell-cast, attacks, blocks, combat damage to a player, upkeep, draw step, begin combat, end step, life gain, counters placed (with `put_by`, 122.6a), draws, discards (effect, cleanup trim, cycling cost), damage dealt to a permanent (enrage, scoped to the victim), becoming the target (heroic and ward, 603.2d), becoming blocked or unblocked (flanking, rampage, bushido, frenzy), becoming untapped (inspired, one event per permanent); intervening-if clauses re-checked on resolution (603.4), a "while" clause (`recheck: false`) checked only as it triggers |
| **Trigger filters** | Validated against `TRIGGER_FILTER_KEYS`, exactly the keys `matches_card_filter` answers: `tapped` reads the arrival state (Charismatic Conqueror), `owner` is 903.3's "your commander" (Tome of Legends), `zone` and `not_supertypes` likewise; `any_of`, a union of whole trigger filters matched once per event (Firespitter Whelp); `to_zones` on `leaves_battlefield` for "dies or is put into exile" |
| **Reflexive triggered abilities** | 603.11: `AbilityKind.REFLEXIVE` carries no `TriggerSpec` and is fired by name by the `reflexive_trigger` op, then goes on the stack as an ordinary `TriggerInstance` with modes and targets chosen as it is put there (603.3d); `_check_reflexive_wiring` makes the two halves name each other |
| **Trigger doubling** | `double_triggers` with a `cause_filter` (Ancient Greenwarden) |
| **Triggering on an activation** | `ability_activated` over `EventType.ABILITY_ACTIVATED`, fired before costs are paid (602.2b), with `TriggerSpec.mana_ability` for "if it isn't a mana ability" |
| **The ordinal of a draw, a cast or a life gain** | `TriggerSpec.nth` compared against the ordinal `draw_cards` and `GameState._tally` write onto the event, per drawing player, caster or gaining player (`TurnLedger.life_gains`), with `triggers._spell_ordinal` for a filtered cast |
| **What targeted, and who caused it** | `targeted_by` on `becomes_target` reads the `is_spell` flag on `BECAME_TARGET` (Goldspan Dragon); `cause_controller` on a `discard` trigger reads `caused_by`, scanned on the discarded card itself; the `spell_targets` event binding on `SPELL_CAST` serves an intervening-if and the effect alike (Orvar) |
| **"Whenever an opponent searches their library"** | `searches_library` over `EventType.LIBRARY_SEARCHED`, fired by `ops_cards._search` once per player per search (701.19) |

### Abilities and layers

| Area | Detail |
|---|---|
| **Static abilities** | Anthems, keyword grants, `set_pt` (including `*/*` read off the board), `add_subtype`, `set_types` (dropping a type drops its subtypes, 205.1b, 613.1d), `set_creature_types` (creature types replaced, other subtypes kept, 205.3d), `set_colors`, `imprint_characteristics` (the last creature card exiled with the source, 7b size and layer-4 creature types, its CDAs read in exile per 604.3), "can't block" (unleash), "as long as" conditions, and a filter `owner` that is not `controller` (903.3) |
| **Conditional statics** | A boolean tree (`STATIC_CONDITION_HEADS`: `all`/`any`/`not`/`exists`/`cmp`/`is_your_turn`) over counters, printed characteristics, zone counts and whose turn it is (Threshold), asked for player-wide statics too through `_static_active` |
| **Losing all abilities, and the derived ability list** | `characteristics.abilities_of` is the one answer legality, `costs.mana_sources`, `triggers.collect`, `_battlefield_statics` and `game._activate` all read; `lose_all_abilities` runs before the grant layers (613.1b) and takes keywords with it (113.1a); granted abilities are appended so indices stay printed |
| **Granted abilities** | The `grant_ability` static may carry a static, which arrives sourced on the recipient (Inspiring Leader), with `grantable_abilities` derived from `_battlefield_statics`; the op and the static may hand over an activated ability, mana or not, `push_activated_ability` recording `granted_by` so it resolves after the grant has left (608.2, 400.7); the op grants triggered abilities until end of turn; `grant_keyword` takes a `duration` of end of turn or `permanent` (riot's haste) |
| **Keyword counters** | 122.1c: any `Keyword` outside `INERT_KEYWORDS` as a counter kind, read in the keyword-grant layer (613.1f), separately visible to `counters_on`, `proliferate` and `move_counters` |
| **An animation with no duration that sets what it becomes** | `animate` with `duration: "permanent"` (611.2a) on `GameObject.animations` and `exact` replacing colours, card types and creature types (Oko); timed and indefinite animations applied in `timestamp` order (613.7); the `lose_all_abilities` op removes only grants older than itself |
| **"Until your next turn" on a permanent's characteristics** | 611.2b: `pump`, `lock_abilities`, `animate` and `grant_keyword` take `duration: "until_your_next_turn"` as a `TempEffect` with `until_player`, cleared by `clear_until_next_turn` in that player's untap step |
| **Text-changing effects (layer 3)** | `change_text` rewrites every `subtypes` list in the object's text and abilities (612.1), applied in timestamp order (612.4), read by `_compute`, `_matches_printed`, `abilities_of` and `stack.ability_of`; creature types only |
| **Type changes** | `{"chosen_type_of": "self"}` on the granting side of an `add_subtype` static, re-read from the static's own source on every recompute (Roaming Throne, Xenograft); the `add_subtype` op writes `added_subtypes` onto the object, or with a `duration` a `subtype` `TempEffect` that ends at cleanup or the controller's next turn (611.2a, Sarkhan, Dragon Ascendant); a static filter may read both |
| **Static filter and value keys** | `counters_on` in a static's magnitude (`STATIC_VALUE_KEYS`, Door of Destinies) with `_static_value` raising on unknown vocabulary; `power` and `toughness` in `STATIC_FILTER_KEYS` read off `characteristics._base_pt` (ferocious); `has_counters`; `entered_this_turn`; `any_of` in `affects` (`STATIC_AFFECTS_FILTER_KEYS`), a union applied once per object with `exclude_self` scoped to its branch (611.3a) |
| **Activation restrictions and locks** | `condition` on an activated ability checked by `legality` before it is offered (602.5c); `sorcery_speed_only`; `activate_steps`; `once_each_turn`; `lock_abilities` ("its activated abilities can't be activated this turn"), covering mana abilities |
| **"Creature spells you control can't be countered"** | `spells_cant_be_countered` with an optional `affects_spells`, omitted meaning any controller (Lier) |
| **Sacrifice prohibitions** | 701.17b: the `cant_sacrifice` op on `GameState.sacrifice_restrictions`, narrowing cost pools (`costs._sacrifice_pool`, `legality._emerge_fodder`) and the `sacrifice` op's pool, never guarding `zones.sacrifice` |

### Targets and selectors

| Area | Detail |
|---|---|
| **Mode-owned targets** | A target spec carrying `mode` is declared inside the cast by `Game._ask_mode_targets` (601.2b then 601.2c), stored in printed mode order (`CardDef.specs_for_modes`), a mode with no legal target withheld; a triggered ability asks modes then targets as it is put on the stack (603.3d, `Ability.mode_targets`); a top-level `choose_mode` is recorded on `StackItem.modes` (`modes_answered` for "up to"); "that hasn't been chosen" is `once_each` on `choose_mode`, `true` for the object's life (flags on the source) and `"turn"` for the turn (`TurnLedger.modes_chosen`, spent as the trigger goes on the stack per 603.3c, dropped at a zone change per 400.7, refused on an activated ability) |
| **A target count the game computes, and "up to X"** | `TargetModel.count` takes a value expression evaluated at declaration (601.2c) and `up_to` makes it a ceiling; `_ask_x_targets` for "each of X targets" after X is announced (601.2b) |
| **Linked targets** | `{"controller": {"target": "who"}}` on a target spec, enumerated per partial combination so the pair is what is legal (601.2c); a target set reads as a selector's `controller` through `ctx.target_players` ("those opponents") |
| **Target kinds and shapes** | A player spec on a target resolved through `select_players`, including `{"not": …}` over `alive()`; the `card_in_exile` kind (110.1) re-checked with its selector (608.2b); one spec spanning the stack and the battlefield ("target spell or nonland permanent"), re-checked by `ref.kind`, with an optional `permanent_selector` narrowing only the permanent half ("target spell or creature"); `total_mana_value` applied where combinations are built beside `one_per_player` |
| **Selector counts** | `count: "any"` for a free subset, `optional: true` beside an integer for "exactly N or none", `destinations` steps on `look_at_top` for typed picks from one look (Kiora), `distinct_names` staging (Tiamat), the `union` key assembling one pool from several zones |
| **Relative selectors** | `shares_a_type_with`, `shares_a_color_with` (radiance), `shares_a_creature_type_with: "self"` (205.3m, `creature_types_of`), `shares_permanent_type_with` (110.4a), `shares_a_name_with`, `exclude_binding` reading set bindings, `created_with: "self"` (`GameObject.created_tokens`), `attacked_this_turn` |
| **Negated and cost-shaped characteristics** | `not_types`, `not_subtypes`, `not_colors`, `not_keywords`, `not_supertypes` ("nonbasic"), `not_name`; `colorless` (105.2c, zero colours) in the selector, static, trigger and cost-reduction filters; `x_in_mana_cost` over `ManaCost.x_count` (107.3), `mana_cost` compared symbol for symbol (202.1b); a `kind: "spell"` target honours its selector in `candidates` and `still_legal` |
| **"A permanent you own" on the effect side** | The `owner` selector key off `GameObject.owner`, filtering rather than defaulting and choosing whose zone list to walk (400.3) |
| **"Choose a card name"** | `choose_card_name` binds a name under `as` from the distinct names the chooser owns plus "another card name"; a selector's `name` reads a binding |
| **Recording what an op consumed or produced** | `as` on `reveal`, `sacrifice`, `exile`, `create_token`, `copy_permanent`, `draw` (seats that actually drew, 121.4), `lose_life` (the loss actually taken), `mill` and `put_on_top`; a `binding` selector has no default zone, a `target` selector keeps the battlefield one (608.2b) |
| **Value leaves** | `mana_symbols` (chroma, hybrid counting for each colour, 107.4f), `distinct` (domain, coven), `max_count_of` / `min_count_of` (per-opponent counts aggregated per seat), `half` with a required `round` (107.1a), `starting_life_of` (103.4, 903.7), `two_share_a_color`, `top_of_library`, `rolled`, `counters_on`, `cards_drawn_this_turn`, `resolutions_this_turn`, `permanents_entered_this_turn` |
| **"Repeat this process"** | `repeat_while`, a mandatory do-while with `reset` of per-pass bindings and the shared hundred-iteration guard |
| **Rolling dice** | 705.1: `roll_dice` with a value-expression `count`, results under `as` from `state.rng`, the `dice_rolled` event |
| **Private and public information** | `look_at_hand` entitles one seat through `GameObject.revealed_to` (`hand_revealed`); `reveal_library_top` (public) and `look_at_library_top` (controller only) statics with the `top_of_library` condition leaf (701.16a); Fact or Fiction's piles, split by an opponent and chosen by the caster |

### Zones and the command zone

| Area | Detail |
|---|---|
| **Command zone** | Abilities that work from the command zone, commander tax, commander damage, the zone-change replacement, `exclude_self` on an eminence `spell_cost_reduction`; emblems (114) as objects of abilities only; `active_zones: ["command"]` statics gathered by `_command_zone_statics` and `_active_player_statics` ("in the command zone or on the battlefield") |
| **Counting commander casts** | `commander_casts_this_game` reads the tally commander tax keeps (903.8), summed over a player's commanders, so "for each time you've cast your commander from the command zone this game" counts partners and nothing cast from another zone |
| **Returning a permanent to the command zone** | `return_to_command_zone`, a bare `objects` op; the command zone is not in `COMMANDER_REPLACED_ZONES`, so it never doubles up with 903.9a |
| **Exile until it leaves** | `until_leaves` writes `exiled_by` on the exiled card and the exiler's leaves-trigger returns its own victims (O-Ring, champion); imprint reads the same link with `exiled_with: "self"`; `zones.link_exiled` also records it in order on the exiler's `exiled_cards`, emptied as the exiler leaves (607.2a, 400.7) |
| **Exile records** | `return_to_origin` reads the `exiled_from` stamp `zones.exile` writes on every route, returning to the owner (400.3); `hidden_in_exile` drops a card from every seat's `exile` list outside `revealed_to` (`as` and `face_down` on `look_at_top`, Necropotence); `exile_and_return` with a required `face` passed as `move_object`'s `as_face` (400.7) |
| **Library positions and order** | `put_on_top`'s `from_top` plumbed to `move_object`'s `to_index`, clamped, owner's library; `any_order` asks the owner one card at a time (401.4); `as` on `put_on_top` records what arrived ("then draws that many"); `search_zones` matches each half in the zone it came from, `search_library` being the one-zone case |
| **Tokens and copies** | Token copies copy the printed card plus what the token's creating effect set (707.2); an X/X token (`variable_pt`) gets its base size from `create_token`'s `power`/`toughness`, fixed as it is created (111.4); `copy_permanent`'s `except_` rewrites copiable values (707.9b): `colors`, `add_subtypes`, `add_types`, `types` replacement, `add_supertypes`, `remove_supertypes`, `power`/`toughness`, `no_mana_cost`; the legend rule reads derived supertypes (704.5j); 614.1b as the `self_enters_as_copy` replacement (Phyrexian Metamorph), with an `except_` adding keywords to the copiable values and an `end_of_turn` `duration` (Dack's Duplicate, Cursed Mirror), and `become_copy` for a permanent already on the battlefield |
| **Spell copying** | 706.10: `copy_spell` backed by a token object, copies on top of the stack emitting `SPELL_COPIED`, `new_targets` opt-in (storm, gravestorm, conspire, replicate, casualty) |
| **Object departure records** | `move_object` snapshots last-known power and toughness (`power_had`, `toughness_had`), `had_counters`, `was_creature`, `was_attacking` and the `left_with` snapshot onto the departure event; `sacrifice` takes a `snapshot` of the chosen permanent |

### Multi-face and multi-card

| Area | Detail |
|---|---|
| **Transforming double-faced cards** | Two `CardDef`s over one `GameObject`, `transformed` picking which face `GameState.card_of` returns; enters front face up (712.13a) |
| **Modal double-faced lands** | The land half is a land drop with `second_face=True` (`legality._second_face_land`), `showing_second_face` set before the move so the land's enters-replacements apply (Malakir Rebirth) |
| **A second castable face — adventure, aftermath, split cards** | `second_face` with `second_face_zone` and `adventure`; `showing_second_face` set as the spell goes on the stack, the exile rider firing only as the Adventure resolves (715.3c, 702.127a) |
| **Flip cards** | 711: `back_face` plus `transform`; a flipped permanent that leaves comes back unflipped (712.13a) |
| **Meld** | 701.37: `melds_with` and `melds_into`, the pair exiled and re-entered as a new permanent with `melded_mana_value` |
| **Face-down permanents — morph, megamorph, manifest** | `chars` returns a 2/2 colourless shell (`FACE_DOWN_CHARS`) while `card_of` keeps the real card; morph casts for `{3}` (702.37a), manifest turns up only a creature card (701.34c); turning up is `ActionKind.ACTIVATE` with `ability_index` 0 |

### Library walks

| Area | Detail |
|---|---|
| **Looking at the top N** | `look_at_top` with a required `amount`, no shuffle unless asked, `rest_to_bottom`, `destination`, `counters` and `counters_if` joining the arrival's own enters-with counters as one placement (122.6) |
| **A free cast out of the looked-at window** | `cast_free` on `look_at_top`, lands filtered out, through `_offer_free_cast` and `suspend.cast_for_free` (601.2b) |
| **Replacing a draw, and the draws that are not draws** | `replacements.draw` wraps every draw but the opening hand (103): dredge replaces the draw (702.52a), madness exiles either way, miracle reads the tally before the draw; `replace_draw` per card (121.2) with the draw-step exemption counted by `cards_drawn_this_draw_step`; `draw_limit` is a "can't" asked first (101.2); `replace_empty_draw` wins instead of decking (104.3c) |

### Prevention and replacements

| Area | Detail |
|---|---|
| **Enters-the-battlefield replacements** | The `replacements` whitelist applied synchronously in `zones._enter_battlefield`: enters tapped with `unless_cost` ("as this enters, you may pay", asked by `offer_enters_costs` a moment early), `self_enters_with_counters` with a value-expression `amount` (614.1c, Éomer), `enters_with_additional_counters` static (Oath of Gideon, Giada per 614.12), `self_enters_as_copy`, `self_enters_prepared`, riot; counters a permanent enters with are one placement ordered as the controller would choose (122.6, 616.1e–f, `zones._entering_counters`) |
| **"If this would enter ... instead"** | 614.1a on the zone change itself: `instead_cost` and `instead_zone` read by `move_object` before the move, offered by every arrival path that can ask (Mox Diamond) |
| **Death and departure replacements** | `replace_deaths` and `replace_leaves_battlefield` redirect a permanent's departure; `replace_graveyard` exiles anything bound for a graveyard from anywhere, read in `zones.move_object` after the commander replacement (Rest in Peace, Leyline of the Void); `replace_dies` exiles a dying permanent its `affects` names and creates its `and_create` tokens for the static's controller (614.6, no dies trigger), read before the commander replacement so a commander is exiled and then goes home, after the affected player's own replacements (616.1), and still applied by a source leaving in the same simultaneous event (Kalitas, Traitor of Ghet) |
| **Narrow-replacement hooks** | Each is a narrow-replacement hook: one named static read at the one primitive that owns the number, with 614.5 kept (each applies once to the event as the last left it) and no event object behind it. `replace_token_creation` with `create_instead` and `token_multiplier` (`primitives.create_token`), `replace_life_loss` (`lose_life` and the loss half of `damage_player`, 118.4, 120.3c), `replace_life_gain` with `gain_multiplier` or `gain_addend` (`gain_life`), `replace_draw`, `replace_mill` (`mill_cards`, 701.13a), `replace_counters` with `counter_addend` or `counter_multiplier`, `effects_only` (118.1) and `put_by` (`add_counters`, the funnel every placement and every "enters with" comes through), `replace_damage` with `damage_source`, `affects`/`affects_player` as a union and `combat_only` (`damage_permanent`, `damage_player`), `replace_proliferate` (the action performed again), `replace_graveyard` and `replace_dies` |
| **Prevention over a player** | The `prevent_damage` op installs a turn-scoped `DamageShield` on the table, checked at the top of `damage_player` so no life, poison, lifelink or `DAMAGE_DEALT` follows; `EventType.DAMAGE_PREVENTED` fires with `to` for the `damage_prevented` trigger (Selfless Squire) |
| **Fog keyed to the source** | `prevent_combat_damage` records a `CombatFog` (615.1): combat damage this turn from sources matching `by`, read on the dealer's current characteristics as the damage would be dealt, in `damage_player` and `damage_permanent`; cleared at cleanup |
| **Prevention over a permanent, either way, with a clock** | `prevent_damage_permanent` puts a `PermanentShield` on the object (`to` and `by`) with `this_turn` or `until_your_next_turn` (615.1), cleared by `reset_permanent_state` (400.7); `prevent_all_but` static (615.1) caps per event after the damage multiplier, smallest cap biting |
| **Prevention over a permanent, static** | The `prevent_damage` static: absorb N per source (702.63a) or `prevent_all`, either narrowed to combat damage by `combat_only`, read in `damage_permanent` beside protection (615.1) |
| **Prevention over a player, static** | The `prevent_damage` static with `affects_player`: absorb N per damage event to the seat (615.1), narrowed by `damage_source` on the dealer's current characteristics (a controller-only filter reaches a spell) and by `combat_only`, read in `damage_player` after the all-or-nothing preventions and before the damage multiplier (Orbs of Warding, Heart-Shaped Herb) |
| **Life totals that cannot move** | `lock_life_total` (118.5) checked before any gain or loss replacement; `cant_gain_life` player-wide static read by `gain_life`, beating `replace_life_gain` (101.2) and firing no `LIFE_GAINED` |

### Counters

| Area | Detail |
|---|---|
| **Proliferate** | 701.27a: one `ask_targets` decision (purpose `proliferate`) over every permanent with a counter and every player with poison or energy, not targeting |
| **Moving and doubling counters** | `move_counters` (graft, modular) clamped to the source; `double_counters` puts the extra on through `add_counters` so counter replacements apply (122.1) |
| **Distributing counters** | `distribute_counters` on an activated ability, the division announced at activation (601.2d, 602.2b) and stored on the stack item, an illegal target's share lost (608.2b) |
| **Counters on an arrival** | `counters` on `put_onto_battlefield` and `return_from_graveyard` (placed after the move), `counters` / `counters_if` on `look_at_top` (one placement with the arrival, 122.6); `replace_counters` applies before `counter_placed` fires or a Saga reads its lore (714.2c) |
| **Counters that can't be put on** | The `cant_have_counters` static (101.2): a placement of the named kind onto a matching permanent does not happen, asked before every counter replacement in `add_counters`, `zones._entering_counters` and `costs.can_pay` (a cost that would put one on can't be paid) |
| **Removing counters as a cost** | `remove_counters_from_among` over several permanents, any kinds, asked one counter at a time (602.2b) |

### Ledgers and history

| Area | Detail |
|---|---|
| **The per-turn ledger** | `GameState.turn_ledger`, folded in `GameState.emit`: creatures died by controller, creatures each player attacked with, damage taken (summed over a spec, or the greatest one player took with `max_damage_taken_this_turn`), life lost (118.2 counts damage), life gained, spells cast, cards put into graveyards, who dealt combat damage (prowl) and to which players, a victim → sources damage ledger read by the `damaged_by` filter; cleared at cleanup with `damage_ledger` |
| **Which creatures attacked this turn** | `TurnLedger.creatures_attacked` holds oids per player (506.4: a dead attacker still attacked); `attacked` is derived from it; `attacked_this_turn` selector key and `attackers_this_turn` value |
| **Attackers' power this combat** | `TurnLedger.attack_power_this_combat` sums each player's attackers' derived power at `ATTACKERS_DECLARED`, before any ATTACKS trigger, and holds it however the attackers change afterwards; reset by `combat.start_combat`; creatures put onto the battlefield attacking add nothing; read by the `attack_power_this_combat` value (pack tactics) |
| **How many times a creature attacked this turn** | `TurnLedger.attacks_by_creature`, folded off each ATTACKS event and written onto it as `nth`, so `attacks` with `nth: 1` is "attacks for the first time each turn" whether or not an earlier attack triggered anything; planeswalker and battle attacks count; dropped when the creature leaves the battlefield (400.7) |
| **Which players a creature attacked** | `TurnLedger.players_attacked_by` read by the `attacked_by` player spec; a planeswalker or battle attack records no player (506.2); creatures put onto the battlefield attacking record nothing (508.4) |
| **Which players a creature dealt combat damage to** | `TurnLedger.players_dealt_combat_damage_by` read by the `dealt_combat_damage_by` player spec; folded off `combat_damage_to_player`, so prevented damage records nothing; dropped when the oid re-enters the battlefield (400.7) and kept when it leaves, for last-known information |
| **Which permanents entered this turn** | `TurnLedger.permanents_entered` as `EnteredPermanent` snapshots (derived characteristics at entry, controller at entry, a flicker is two arrivals), read by the `permanents_entered_this_turn` value in both value languages and the `entered_this_turn` static filter key |
| **Draw history** | `cards_drawn_this_turn` incremented in `draw_cards`, cleared by the untap step rather than cleanup (the opening hand precedes turn 1) |
| **Per-ability and per-walker tallies** | `resolutions_this_turn` keyed by (object, ability index), bumped in `resolve_top` past the fizzle and intervening-if returns; `TurnLedger.loyalty_activations` per player counted in `Game._activate` (602.2) and `extra_loyalty_activations` for The Chain Veil (606.3) |
| **"If it was cast" and "during their turn"** | `was_cast` reads `entered_by_cast` stamped by `zones._enter_battlefield` (603.6e; a copy fails under 707.10); `is_active_player` takes a full player spec |

### Player-wide statics

| Area | Detail |
|---|---|
| **Player-wide statics** | Read through `player_statics._active_player_statics` with their "as long as" conditions: extra land drops, `no_hand_limit`, playing lands from the graveyard or the top of the library, doubling land triggers, doubling the mana a land or a nonland permanent is tapped for (Vorinclex, Kinnan), freezing the lands an opponent taps; `player_hexproof` (702.11d) read by `targeting._player_allowed` against the spell's controller |
| **"No maximum hand size for the rest of the game"** | The `no_maximum_hand_size` op sets `PlayerState.has_no_maximum_hand_size`, and `player_has_no_hand_limit` reads the flag or the statics (514.1) |
| **What an opponent's effects may not do to you** | `draw_limit` with a required `amount` counted against `cards_drawn_this_turn` (`player_statics.draw_cap`); `cant_search_library` read by `ops_cards._search` through `search_forbidden`, the library dropping out of the pool and the shuffle still happening; `opponents_cant_force_discard_or_sacrifice` keyed on the controller of the cause (`caused_by`), narrowing `discard`, `sacrifice` and a `may`'s `pay` |
| **"Doesn't untap during their controllers' untap steps"** | `skip_untap_step` and its inverse `untap_during_each_untap_step`, read by `primitives.untap_all` through `untap_held` at the untap step alone (Winter Orb, Intruder Alarm) |

### Control

| Area | Detail |
|---|---|
| **Gaining control** | `gain_control` with `permanent` or `until_end_of_turn`: `controller` plus summoning sickness (302.6), removal from combat (506.4) and owner-bound zone destinations (400.3), the `control_changed` event; the handback is a `TempEffect(kind="control")` re-entering `change_control` the other way |
| **Exchanging and rotating control** | `exchange_control` with `first` and `second`, one act (701.12a), nothing happening unless both resolve to one permanent each with different controllers (701.12b); `rotate_control` reads every controller before any moves, skipping eliminated seats (Aminatou); `distribute_control_among_opponents` pairs each permanent with a different opponent chosen by the controller, every choice before any move (Dack Fayden, Helping Hand) |
| **Join forces** | `may`'s `pay` with a `player` spec asked one unit at a time per seat in turn order, the total bound under `as` |

### Planeswalkers, sagas, battles, classes

| Area | Detail |
|---|---|
| **Planeswalkers** | Starting loyalty as a `self_enters_with_counters` replacement, loyalty abilities once per permanent per turn at sorcery timing (606.3), damage removing loyalty, death at zero (704.5i), attackable (506.2); `activate_loyalty_as_though_instant` lifts the timing half of 606.3 only; `extra_loyalty_activation` adds to the per-turn limit; `cost.loyalty_x` for −X |
| **Sagas** | 714: the three reminder-line rules live in `engine/sagas.py` — the lore counter as an enters replacement (714.2b), the tick as a turn-based action in the precombat main (714.2d), chapters as `AbilityKind.CHAPTER` firing on the count reaching the number (714.2c), the sacrifice as a state-based action after the last chapter leaves the stack (704.5s, `final_chapter`) |
| **Battles** | 310: `engine/battles.py` compiles `defense` into counters (310.4), being attacked is 506.2's third defender kind, damage removes defense (310.6), zero defense is 704.5x and not destruction; a missing `defense` is a load error |
| **Classes: levels and level-gated abilities** | 716: `GameObject.class_level`, level lines compiled to the activated ability 716.2a spells out (`become_level`, `Ability.becomes_level`), `"level": N` on an ability meaning present only at that level or higher (716.2b, `AbilityKind.LATENT` keeping indices), the `becomes_level` trigger (716.4), not copiable (707.2) |

### Game end

| Area | Detail |
|---|---|
| **"You win the game" and "that player loses the game"** | `win_game` eliminates every other seat through `sba.declare_win` (104.2a, loss reason `opponent_won`); `lose_game` eliminates the named seats through `sba.declare_loss` (104.3a), all of them before the check so "each player loses" is a draw (104.4a) |
| **"You can't lose the game" and "can't win the game"** | 104.3b: the timed `OutcomeLock` op (Angel's Grace, `state.outcome_locks`) and the continuous `cant_lose_the_game` / `cant_win_the_game` statics (Gideon of the Trials' emblem), both read by `sba._player_losses` and `sba.declare_win`; a locked seat keeps its negative total and is eliminated when the lock clears |
| **"Damage can't take you below 1"** | 614: the timed `LifeFloor` op (`state.life_floors`) and the `damage_life_floor` static (Worship), read only in `damage_player` — paid life and `lose_life` walk past it |
| **"You win the game instead" of decking** | `replace_empty_draw` replaces the attempted draw before any doubler and wins through `sba.declare_win` (104.3c) |

## Simplified

Each of these is a deliberate trade. The rationale matters more than the rule.

| Simplification | What it means | Why |
|---|---|---|
| **Fixed layer order, no timestamps or dependencies (ADR 0001)** | Continuous effects apply in a fixed order ([ADR 0001](adr/0001-layers-lite.md)); static filters and conditions read pipeline inputs only — printed characteristics, board state, counters, zone counts — never another static's output, enforced at load time against `STATIC_FILTER_KEYS`. The rule-modifying `attacks_if_able` and `block_restriction` (`affects` and `blockers`) sit outside the pipeline and match against derived characteristics, as does the `exists_derived` condition on `cant_attack` and `cant_block` (Rhonas), so Graaz's Juggernauts include the creatures its `add_subtype` static made Juggernauts. Consequences: `lose_all_abilities` and the `grant_ability` static are collected off printed faces, so an Imprisoned in the Moon on another one does not switch it off (no 613.8 dependency analysis); a `set_types`, `set_creature_types`, `set_colors` or `set_pt` static overrides an `animate` whatever its timestamp, and a subtype grant (a changeling's included) survives `set_types` and `set_creature_types` whatever its timestamp; a granted or replaced type (`chosen_type_of`, the `add_subtype` and `set_creature_types` statics) is in `chars()` and not in another static's filter, so a Xenograft naming Goblin does not put Bears under a Goblin lord; a static filter sees base power while `cost_reduction._object_matches` and trigger filters see derived power; keyword counters apply after the `lose_all_abilities` op whenever placed; `_matches_printed` sees a copied card's printed cost, not a copy's `no_mana_cost` | The full layer system with timestamps and dependency analysis is a large subsystem that would change no outcome for any card in these decks |
| **Automatic mana payment, by default** | The solver picks which land to tap, preferring abundant colours. A land doubled by Vorinclex, or a nonland permanent doubled by Kinnan, adds one mana of a type it produced — the first symbol in WUBRGC order it made — with no free choice of which, because a mana ability may never stop to ask; a Sol Ring under Kinnan is `{C}{C}{C}`. A seat can opt out with manual mana (`PlayerState.manual_mana`, the rail's toggle), which offers every tap-only mana ability and one action per colour a dual could make; off for AI seats. A permanent with something besides its tap-only mana ability offers both to a human seat (`PlayerState.offer_all_abilities`) | Removes an enormous branching factor for the RL agent and the worst tedium from the UI, without making "tap this land for blue" impossible to say |
| **"Enchant creature" is a targeting clause, not a standing restriction** | 702.5b is read as the Aura spell's target selector and nowhere else; an `attach` op naming a host with `attachment` is trusted, and nothing re-tests an Aura moved later. The same reading covers "Enchant player" (303.4a): `attach_to_player` checks only that the seat is still in the game and not protected from the Aura | Every Aura arrives cast (the target line is re-checked on resolution, 608.2b) or by an effect whose selector states the host; `attach` still refuses self-attachment (301.5c) and protection |
| **Which same-coloured mana gets spent** | The pool records which permanent made each pip (`Pip.source_traits`, a `ManaOrigin` snapshot); `ManaPool._take` pops newest-first rather than asking | Payment taps what it needs immediately before spending, so the newest pip is the one made for this spell; asking would put a decision inside cost payment |
| **A mana source's characteristics are frozen when it makes the mana** | `mana_source_traits` snapshots name, types, subtypes, supertypes and controller at production, and every "mana from a …" question reads the snapshot | The source is routinely gone (a Treasure sacrifices itself); a permanent whose type line changes between making and spending is answered as of production |
| **A reflexive trigger fires unconditionally** | A `reflexive` ability is a real triggered ability on the stack, but the `reflexive_trigger` op fires it whether or not the instruction before it did anything; a card may also still be written as a `may` with a `pay` whose payload runs inline, which trades away the response window between the cost and the payload | No card in the pool prints a "when you do" whose instruction can fail outright; the ones that can do nothing say so in the reflexive half |
| **Gate 5 cannot witness a loyalty ability** | The authoring harness casts a card and stops at the first priority window; a planeswalker's abilities are checked by the vocabulary and text-attribution gates alone | Teaching the harness to activate abilities is separate work; `tests/unit/planeswalkers/test_planeswalkers.py` holds the chassis |
| **Automatic damage assignment order** | With no banding involved, blockers are ordered by effective toughness ascending and the attacker is never asked (510.1c) | One more decision point per combat for a choice that is nearly always forced |
| **`search_zones` always searches every zone it names** | Finale of Devastation's "if you search your library this way, shuffle": the op always offers both zones as one pool, so it always searches the library and always shuffles | Asking which zones first would be a second decision on a card with none and would undo the union the op exists for |
| **Automatic trigger ordering** | Simultaneous triggers one player controls resolve in a fixed order (`triggers.drain_to_stack`), as do two Sagas' chapters advancing in one phase | Matters only for a handful of interactions, none in these decks |
| **Card-level targets chosen before modes** | A card-level target is enumerated as part of the cast action, so it is chosen before the mode (the reverse of 601.2b); a mode-owned target and a triggered ability's targets are asked in the printed order; a nested `choose_mode` resolves late | Closing it means moving all target enumeration behind a decision, which changes casting for every card and both AI seats; the shared `optional: true` idiom in [card-dsl.md](card-dsl.md) papers over it |
| **X capped for the policy** | A human is offered every X the board can pay; the RL policy sees X in 0..9 (`CHOICE_CAP` in `ai/action_space.py`) | Raising the cap invalidates trained checkpoints for a ceiling that only bites above ten spare mana |
| **`choose_type` and `choose_color` are triggers, not replacements** | "As this enters, choose a creature type" (Vanquisher's Banner) and "choose a color" are `self_enters` triggers, so the choice is made a moment after the permanent arrives; until then the filters it feeds match nothing. Amplify and devour are `self_enters` triggers for the same reason; `become_level` and `monstrosity` land on the source oid at resolution; a token attacking a planeswalker chooses its target a moment after it arrives | `zones._enter_battlefield` applies enter-replacements synchronously and cannot yield a decision; the window is observable only to a trigger ordered between the two |
| **Object identity survives zone changes** | The `oid` is preserved where the rules would create a new object; permanent state is reset instead (`reset_permanent_state`) | Simpler and equivalent for everything except effects that track "the new object" |
| **Last-known information is explicit** | A card that needs a value after its subject has left declares a `snapshot` op; `zones.move_object` snapshots `power_had`, `toughness_had` and `had_counters` onto the departure event for a `dies` trigger about itself, and `sacrifice` takes a `snapshot` of what somebody else chose | A global LKI system is not worth it for the cards that need one, and the explicit form is easier to read |
| **Commander replacement is automatic** | The owner always chooses the command zone (903.9a) rather than being asked, and `replace_graveyard` is ordered after it so a commander dying under Rest in Peace still reaches the command zone | It is what players choose in practice, and it keeps zone changes out of the decision system |
| **Legend rule keeps the newest** | Duplicated legends are resolved without asking the controller (`sba._legend_rule`) | The choice is nearly always irrelevant |
| **Target options capped at 12** | A spell offers at most `MAX_TARGET_OPTIONS` target combinations, except one asking for a single target, which offers every legal one | Only bites on very wide boards and on combinations, where the count grows faster than the board |
| **Turn cap, trigger loop guard, extra-phase cap** | 30 turns per player then a draw; more than 200 triggers in one step raises `RulesLoopError`, scored as a draw; grants past `MAX_EXTRA_PHASES_PER_TURN` are dropped | Self-play must terminate, one pathological board must not abort a long run, and Aggravated Assault is a printed infinite; draws are counted and reported |
| **Delayed triggers resolve off the stack** | `delay` and `delayed_trigger` resolve as their moment arrives (`turn._run_delayed`, `triggers.run_armed_delays`) rather than being put on the stack, and so do the monarch's two inherent abilities | Observable only when somebody would respond differently to the delayed half than to the spell that scheduled it |
| **Replacement order is not asked** | 616.1 lets the affected player order two applicable replacements; the engine applies them in battlefield order. Visible for Hardened Scales beside Doubling Season ((1+1)×2 rather than 1×2+1), for a gain addend beside a doubler (`gain_life` applies addends before multipliers, the larger gain), for a prevention beside a doubling (prevention first, the order the protected player would choose), and for an absorb beside a `prevent_all_but` cap (absorb first, where the protected player would cap first); invisible between multipliers. Two cases are asked or searched: dredge against a draw doubler, and the counters a permanent enters with (`zones._entering_counters` takes the order leaving the most) | `gain_life` and `add_counters` are reached from inside combat damage and zone changes, where nothing can ask |
| **Free casts at resolution choose for themselves** | `suspend.cast_for_free` (suspend, rebound, cascade, discover, `exile_until`, ripple, `cast_from_hand`, `play_exiled`) is mandatory rather than "you may", takes the first legal target tuple, takes at most one target, and collects no `strive` surcharge or `spell_cost_increase` (narrower than 601.2f) | The upkeep tick and the scan run from the turn structure, which cannot stop to ask |
| **Face-down permanents are a bare shell** | Anthems, counters and a granted `ward` do not apply to a face-down permanent, since `chars` returns `FACE_DOWN_CHARS` before any static runs; turning face up is an ordinary activation rather than a special action | The shell is returned rather than layered over, and nothing can respond to the turn in any case |
| **The block tax is paid per blocker** | 509.1d–f total and pay once the declaration is legal; here each blocker pays as it is added, so a block later retracted by `drop_illegal_blocks` keeps the mana it was charged | Declaration is incremental here and all-at-once in the rules |
| **Load-time refusals in place of an ordering** | A target spec naming a sibling declared after it is refused rather than sorted; a spliced card may not declare its own targets (they would collide with the host's); disturb's targets are enumerated off the front face, since legality decides castability before the face is turned | One rule each, checked when the card loads |
| **Per-keyword edges** | Connive on a permanent that has left does nothing, where 701.47b keeps the draw and the discard; mutate's target excludes tokens, since a pile of cards needs cards to come back; a copied Class level line resolves as a literal "becomes N"; `mana_grant` is granted once per payment | No card in the pool hinges on any of them |
| **Exile links that lose their object** | `exile_and_return` skips the return when the exile was replaced (a commander sent home); `return_to_origin` leaves a card whose origin is missing in exile; `return_to_command_zone` leaves an object already there alone, moves a token there to cease to exist (111.7), and parks a non-commander inert | 400.7's answer for an object the effect is no longer tracking |
| **Enters costs on routes that cannot ask** | An `instead_cost` arrival on a route with no decision point (a tutor straight onto the battlefield, manifest, meld) counts as unpaid and takes the worst branch; an unaffordable `unless_cost` or `instead_cost` is never offered (118.4) | Entering for free would be the strictly better card |
| **Some condition leaves are language-bound** | `was_cast` and `is_active_player` are absent from the static condition language and a cost reduction's whitelist | A static has no event bindings and a cost is priced before anything is on the stack |
| **What a hook does not see** | A `prevent_damage_permanent` `by` shield leaves with its object, so damage a leaves-the-battlefield trigger deals afterwards is not prevented; `ability_activated` with `mana_ability: true` misses the mana abilities the payment solver taps for itself (they go straight through `costs.pay_mana`); epic's lock is read by `_cast_actions` alone, so an epic player's cascade is not refused; `triggers._spell_ordinal` matches earlier spells on their printed faces (a bestowed Aura counts as the face recorded, 702.103b) | No shipped card hinges on any of them |
| **Payment order the engine picks** | Two life-payable pips in one cost (`{2/B}` beside `{B/R}`, `{W/P}` beside `{B}` under K'rrik) are bought single-symbol first and then in printed order, and the `{B}` in a strive surcharge is paid with mana; `spend_mana_as_any_color` is applied before convoke and delve are netted, so a loosened pip can be absorbed by the discount; `add_mana_on_tap` adds the extra mana to the tapped source's option, carrying that source's restriction | No shipped card prints such a cost; legality and payment agree in every case |
| **The pod's ending** | A player who wins a multiplayer game ends it for everybody, where 800.4 has them leave and the survivors play on | One `GAME_OVER` is what self-play and the client are built around |

Hand-written cards carry no simplifications of their own: every one clears all six
authoring gates in `tests/cards/test_hand_written_cards.py`, and the generated
`tests/cards/precon_deficits.json` that would list exceptions is empty and may only
shrink.

## Imported cards, which are simplified further

Everything above describes a hand-written card. A deck imported from Moxfield is
mostly cards generated by `src/commanderblitz/cards/proxy.py`, which keep their name,
cost, types, stats, keywords and mana abilities and lose the rest. Each simplification
is recorded on the card and shown at import; the list is owned by
[deck-import.md](deck-import.md#what-the-generator-does-and-does-not-do).

## Not implemented

These are absent, and the shipped decks avoid them. Adding any one is additive.

- Companions (702.139).
- The initiative and the Undercity (722); `Undercity` is known only as a Dungeon subtype.
- Voting — will of the council, council's dilemma (701, vote).
- Sideboards and wishes (100.4); the import keeps a Moxfield sideboard only as a list.
- Range of influence (801); every table is one limited-range-free game.
- Experience counters (122.1).
- Manual combat damage division in the ordinary case (510.1c); banding is the one case that asks.
- Damage redirection effects.
- "Prevent the next N damage" over a player or any target (615.6); the `prevent_damage` op refuses an `amount`.
- A general replacement system (616): no event object and no "replaced by" chain — every replacement is one of the named hooks above, and a replacement of anything else is engine work rather than a card key; replacements that do something other than draw more (Notion Thief, "exile the top card instead") are the reachable example.
- Attacking with creatures you do not control (508.1a); `combat.can_attack` requires the active player's own.
- A copy effect applied to a permanent already on the battlefield by anything other than `become_copy` (707); a copy of a copy does not inherit the first copy's exception (707.9b).
- Battle protectors (310.7, 506.2b) and casting a defeated Siege's back face; a battle here is attacked by its controller's opponents.
- Read ahead (702.155) and double-lore effects on Sagas.
- Saddle (702.171); a Pilot that also saddles is not defined.
- Station variants: stationing with toughness (Tapestry Warden), Spacecraft becoming artifact creatures at their number, and a `threshold` on anything but an activated ability.
- Typecycling (702.29) in the template tier; the cycling template reads plain cycling only.
- Granting a static ability with the one-shot `grant_ability` op, and a granted activated ability that works off the battlefield (granted cycling); both refused at load.
- An emblem or command-zone activated ability; refused at load, since nothing offers an activation from that zone.
- A tax on an activated ability (no `ability_cost_increase`), and a `spell_cost_increase` sized by anything but a literal.
- A warp cost with X, and airbend on a kicked or bestowed cast.
- An impending cost with X, or offered from anywhere but the hand (evoke's zone gate).
- Dice-roll triggers and the AFR d20 outcome tables, and a mill trigger: `EventType.DICE_ROLLED` and `EventType.MILL` have no `TRIGGER_EVENTS` name.
- Granting extort to other creatures (Pontiff of Blight).
- A chosen card name stored on a permanent for a later reader (Pithing Needle, Meddling Mage); `choose_card_name` binds for one resolution.
- `distribute_counters` on a spell or a triggered ability, and dividing damage among targets.
- 508.4's unspecified "tapped and attacking" with no player named.
- Timed forms with no home yet: a delayed trigger scoped to the extra turn an effect created (Final Fortune), "skip your next turn" for ordinary turns, the turn-long "can't be regenerated this turn", and "no maximum hand size until your next turn" (Enter the Infinite).
- Per-turn cast caps (Deafening Silence) and the ability half of Grand Abolisher; `affects` beside `cant_cast_spells` is refused.
- Equip abilities at instant speed (Leonin Shikari); nothing on `Ability` marks an equip ability.
- A player-wide "spend mana as though it were mana of any type" (Mycosynth Lattice); `as_any_type` exists as a cost reading and the `playable_any_type` permission only.
- `add_mana_on_tap`'s "enchanted land" form and any-colour additions.
- A `filter` on a `delayed_trigger`; a `condition` over the `subject` binding says the same thing.
- A modal double-faced card whose back face is a spell (712); the land-backed form is implemented and nothing refuses the other, but no shipped card exercises it.

## How this is enforced

None of the above is a promise in prose — it is checked:

- The card loader validates every op name, selector key, value form, keyword, type and
  trigger event against the registries in `cards/loader/vocabulary.py`. An unknown one
  raises `DslError` at load time, which fails `pytest`, not a game.
- The "statics may not read statics" constraint is a load-time check of every static
  ability's filter against `STATIC_FILTER_KEYS`.
- `tests/cards/test_every_card_works.py` plays every shipped card in a rigged sandbox
  and asserts it resolves into the right zone, with per-card outcome expectations from
  `tests/cards/expectations.json`.
- `tests/cards/test_hand_written_cards.py` runs all six authoring gates over every
  hand-written card, and separately checks that each card's `oracle_text` is what the
  catalog says it prints — the check that stops a card from being verified against a
  summary of itself. The generated `tests/cards/precon_deficits.json` lists cards
  that do not pass, with reasons; it is empty, and it can only shrink.
- `tests/cards/test_auto_cards.py` does the same for every machine-authored card.
- Deck legality, colour identity and singleton rules are tested per deck.

If a card in this repo does not work, one of those tests fails.
