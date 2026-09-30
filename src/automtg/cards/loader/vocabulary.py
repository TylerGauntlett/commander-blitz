"""The DSL's vocabulary: every name a card file may use, as sets.

Membership in these is what ``compile_card`` checks a card against. They are
imported by the authoring packet (so a worker sees the same words the loader
accepts) and pinned by ``tests/cards/test_golden_pool.py``.
"""

from __future__ import annotations

from automtg.engine.characteristics import ABILITY_STATICS
from automtg.engine.costs import REDUCTION_ZONES
from automtg.engine.effects.values import (
    PER_PLAYER_COUNT_KEYS,
)
from automtg.engine.enums import (
    CardType,
    Color,
    Keyword,
    Supertype,
)

#: Trigger events whose payload carries a defending player, and therefore the
#: only ones a ``defending`` clause can be asked of. The per-creature `attacks`
#: and the per-declaration-per-seat `creatures_attack_player`; `you_attack` is
#: deliberately absent, because it is fired once for the whole declaration and
#: has no one player to compare against.
#:
#: `deals_damage_to_player` is the third, and it is the one that is not about
#: combat: "whenever enchanted creature deals damage to **an opponent**"
#: (Curiosity) asks who took the damage, and `controller` cannot answer it --
#: that clause is about whose *creature* dealt it. `damage_player` carries the
#: damaged seat as `defender` for exactly this comparison. Two-player play hides
#: the difference; a pod does not, and neither does a creature you control that
#: somehow damages you.
DEFENDING_TRIGGERS = frozenset({"attacks", "creatures_attack_player", "deals_damage_to_player"})

#: Cost keys that charge the **source permanent**, and so may not appear on a
#: card-level `alternative_cost`.
#:
#: The source of a cast-time cost is the spell itself, on its way from hand to
#: stack -- there is no permanent to tap, no loyalty to spend, and the card the
#: self-costs would take is the one being cast. `costs.can_pay` refuses every
#: one of them in that position, so a card written this way loads clean and is
#: never once offered the line: the silently inert card, which is worse than a
#: load error. `x_value` is here for the neighbouring reason -- only
#: `costs.ability_mana` reads it, and a cast variant is never priced through it.
NOT_A_CAST_TIME_COST = frozenset(
    {
        "tap",
        "untap",
        "loyalty",
        "remove_counters",
        "exile_self",
        "exile_self_from_hand",
        "discard_self",
        "pay_life_x",
        "x_value",
    }
)

KNOWN_TYPES = frozenset(t.value for t in CardType)
KNOWN_SUPERTYPES = frozenset(s.value for s in Supertype)
KNOWN_KEYWORDS = frozenset(k.value for k in Keyword)
KNOWN_COLORS = frozenset(c.value for c in Color)

#: Printed spellings of a keyword the engine already has under another word.
#:
#: Rule 702.88 is *totem armor*, and the Rise of the Eldrazi Umbra cycle prints
#: the identical ability as "Umbra armor" -- one mechanic with two names on real
#: cardboard, and Scryfall's ``keywords`` array repeats the printed one. Without
#: this the replacement is fully implemented (``zones.destroy`` reads
#: ``Keyword.TOTEM_ARMOR``) and yet no Umbra can ship, because the printed line
#: folds to a word that is in no vocabulary and the residual gate reports it
#: unclaimed.
#:
#: An alias, deliberately, rather than a second ``Keyword`` member: two enum
#: values for one ability would need every reader to check both, and the one
#: that forgot would be a card that quietly loses its totem armor.
KEYWORD_ALIASES = {"umbra_armor": Keyword.TOTEM_ARMOR.value}


def normalize_keyword(word: str) -> str:
    """A printed keyword folded to the word the engine knows it by.

    Applied wherever printed text or Scryfall's array becomes a keyword, so the
    two spellings of one ability meet before anything compares them.
    """
    return KEYWORD_ALIASES.get(word, word)

#: The keys `add_mana_on_tap`'s `tapped_permanent` may carry: what the tapped
#: permanent *is*. Crypt Ghast's "a Swamp", Leyline of Abundance's "a creature",
#: Vernal Bloom's "a Forest". Read against the permanent's current
#: characteristics, so a land Urborg makes a Swamp counts.
#:
#: `attached` is the one key that is not a characteristic: it names *the* permanent
#: this static's source is attached to, rather than a class of permanent. Wild
#: Growth and Utopia Sprawl print the Vernal Bloom sentence about one enchanted
#: land, and every other key here is a description that would also match the
#: thirty other lands on the table.
TAPPED_PERMANENT_KEYS = frozenset({"types", "subtypes", "supertypes", "attached"})

#: Static ability effects the characteristics pipeline understands.
STATIC_EFFECTS = frozenset(
    {
        "buff",
        "grant_keyword",
        # Archetype of Courage and its cycle: "Creatures your opponents control
        # lose first strike and **can't have or gain** first strike."  The
        # subtractive twin of `grant_keyword`, and the *last* step of the
        # keyword pipeline rather than an early one -- "can't have or gain" is a
        # standing prohibition, so it has to outrank every adder, where
        # `lose_all_abilities` at layer 1 is deliberately early because 613.1b
        # keeps whatever is added after a removal. Named keywords only, which is
        # what separates it from `lose_all_abilities`: that one would also take
        # the opponents' flying and their triggered and activated abilities.
        "lose_keyword",
        # Authority of the Consuls; Imposing Sovereign; Kismet; Frozen
        # Aether; Loxodon Gatekeeper; Root Maze; Orb of Dreams; Thalia,
        # Heretic Cathar.  "<permanents> your opponents control enter
        # tapped."  The one thing a card's own `replacements` can never say:
        # that list is a closed `self_*` Literal read off the ARRIVING card,
        # so `self_enters_tapped` on Authority taps the enchantment and
        # leaves the opponents alone. Read in `zones._enter_battlefield`,
        # where `obj.tapped` is decided, so it catches every arrival --
        # cast, put onto the battlefield, a token, or returned from a
        # graveyard. `affects` is required: the filter is the printed clause
        # and it defaults to your own side.
        "enters_tapped",
        # Winter Orb: "As long as this artifact is untapped, players can't
        # untap more than one land during their untap steps."  A **count**,
        # which is the whole difference from `skip_untap_step` next door: that
        # one marks each matching permanent and skips every one of them, an
        # all-or-nothing hold with no number and nobody choosing, so Winter
        # Orb written with it is Rising Waters. Read by
        # `player_statics.untap_caps`, and the untapping player picks which
        # permanents untap -- asked in `turn._untap_step`, the first question
        # the untap step has ever put to anybody.
        "untap_limit",
        # Rest in Peace; Leyline of the Void; Planar Void.  "If a card or
        # token would be put into a graveyard from anywhere, exile it
        # instead."  The FIFTH named hook on the enters/leaves replacement
        # whitelist, and not the start of a rule-616 system -- see
        # docs/rules-coverage.md. Read in `zones.move_object`, gated on the
        # destination alone so the printed "from anywhere" really is
        # anywhere, and ordered after the commander replacement so a
        # commander still reaches its command zone.
        "replace_graveyard",
        "set_pt",
        "add_subtype",
        # "As long as Arixmethes has a slumber counter on it, it's a land."
        # Replaces the printed types rather than adding to them, which is the
        # whole point: the parenthetical says "it's not a creature".
        "set_types",
        # "Enchanted permanent is a **colorless** land..." Replaces the printed
        # colours, and it is `set_types`' other half: a card that changes what a
        # permanent *is* almost always changes both.
        "set_colors",
        # "...and loses all other card types and abilities." The only effect in
        # the engine that takes an ability away rather than adding one, which is
        # why `characteristics.abilities_of` exists at all -- before it, every
        # reader walked the printed list and there was nowhere for this to bite.
        "lose_all_abilities",
        # "...is a colorless land **with \"{T}: Add {C}\"**." The continuous
        # counterpart of the `grant_ability` op: that one is a one-shot whose
        # grants only `triggers` reads, and this one has to reach `legality` and
        # the payment solver, because a granted mana ability nobody can tap is
        # not a mana ability.
        "grant_ability",
        "extra_land_drops",
        # Player-wide, like `extra_land_drops`: a fact about the player rather
        # than a characteristic, with no object for it to attach to.
        "no_hand_limit",
        # "Skip your draw step." Necropotence, and the fourteen other cards that
        # print exactly this sentence. Player-wide for `no_hand_limit`'s reason,
        # and read by `turn._draw_step`, which is the only place a turn-based
        # draw happens.
        #
        # Named for the one printed sentence rather than parameterised on a step
        # name, which is the house call every static here makes: the catalogue
        # prints "skip your draw step" 15 times and every other step-skip once
        # or twice apiece, across three different steps *and* two different
        # durations -- "skip your **next** untap step" is a one-shot like
        # `skip_untap`, not a continuous effect, so a shared `step:` parameter
        # would still not have carried it.
        "skip_draw_step",
        # "If an opponent would begin an extra turn, that player skips that turn
        # instead." Trouble in Pairs. Player-wide, and a *replacement*: read by
        # `turn._take_extra_turn` as a scheduled extra turn would begin (614.10),
        # never at scheduling time, so a turn queued before the permanent arrived
        # is still skipped. Only extra turns -- the ordinary order has no reader.
        "skip_extra_turn",
        "play_lands_from_graveyard",
        # "Once during each of your turns, you may cast an artifact spell from
        # your graveyard." Edgar, Master Machinist. Player-wide like
        # `play_lands_from_graveyard` and strictly wider than it: that one is
        # read only by the land drop, cannot be narrowed by card type and
        # carries no per-turn count. Filters the spells it permits with
        # `affects_spells`, the same filter `spell_cost_reduction` matches a
        # card in hand with, and counts its uses per granting permanent.
        "cast_from_graveyard",
        # "You may play lands and **cast spells** from the top of your library.
        # If you cast a spell this way, pay life equal to its mana value rather
        # than pay its mana cost." Bolas's Citadel. The casting twin of
        # `play_lands_from_library_top`, which is lands only and grants nothing
        # for a nonland spell.
        #
        # The life price belongs to the same static rather than a second one:
        # the permission without it is every spell in the deck castable off the
        # top at its printed cost, which is a different and much stronger card.
        "cast_from_library_top",
        # "You may cast Dragon spells without paying their mana costs."
        # Dracogenesis; Omniscience narrowed by a filter. The third casting
        # permission beside the two above and the only one that changes the
        # **price** rather than the zone: those two say where a spell may be
        # cast from and leave the cost alone, and `spell_cost_reduction` is
        # clamped to the generic part so it can never reach a coloured pip.
        # 601.2b's "without paying its mana cost" is not a reduction to zero --
        # the difference shows on an X spell, where X is 0 (107.3b) -- so this
        # prices the cast on `casting.FREE_COST` instead. `affects_spells`, the
        # same printed-face filter `spell_cost_reduction` and
        # `cast_from_graveyard` take, is what carries "Dragon"; the permission
        # is optional, so the printed line is still offered beside it.
        "free_cast_permission",
        # "Artifact cards and red creature cards in your hand have warp
        # {2}{R}." Tannuk, Steadfast Second. The fourth casting permission, and
        # the only one that hands over a **price** somebody else's card did not
        # print: the three above say where a spell may be cast from or that it
        # costs nothing, and this one adds a second, separate cost beside the
        # printed one.
        #
        # Not `grant_keyword`, which knows only the ability keywords and of
        # which warp is not one -- and warp is a cost rather than an ability
        # even if the word existed. Not `grant_ability` either: a cost is not a
        # triggered, activated or static ability, and a granted ability reaches
        # the battlefield while this grant must be live on cards sitting in a
        # hand. `spell_cost_reduction` is the only other static that touches
        # what a spell costs and it can only discount the printed price.
        #
        # `affects_spells` carries the filter and `warp_cost` the price. Read
        # by `player_statics.granted_warp_cost` at every cast, so a card drawn
        # after the granter arrived is covered.
        "grant_warp",
        # "For each {B} in a cost, you may pay 2 life rather than pay that
        # mana." K'rrik, Son of Yawgmoth. Player-wide: it changes how the
        # player *pays*, in every cost, so there is no object to attach it to.
        # Read by the cast line and by `costs.can_pay` / `costs.pay`, each of
        # which reads a black pip as a Phyrexian one while it is on.
        "black_mana_as_phyrexian",
        # "You may spend mana as though it were mana of any color." Chromatic
        # Orrery. Player-wide for `black_mana_as_phyrexian`'s reason and read in
        # the same places: it loosens which mana pays a coloured pip in *every*
        # cost the player pays, spells and activated abilities alike, so there
        # is no object for it to attach to. Distinct from the `any_color` flag
        # on `exile` / `grant_playable`, which is the same waiver granted for
        # one named card.
        "spend_mana_as_any_color",
        "play_lands_from_library_top",
        # "Play with the top card of your library revealed." Player-wide, and
        # the only static here that changes nothing about the rules: it grants
        # no permission and moves no card, it makes one card public. Read by
        # `serialize`, and by nothing else.
        "reveal_library_top",
        # "You may look at the top card of your library any time." The private
        # counterpart of the line above, and the difference is the whole of it:
        # revealed is public and goes to every seat, looked-at goes to the one
        # seat entitled to it. Read by `serialize`, and by nothing else.
        "look_at_library_top",
        # Parameterised, so it cannot be a keyword: "protection from Wizards"
        # names a quality, and four separate rules (damage, enchant/equip,
        # block, target) ask about it.
        "protection",
        # Absorb (702.63a): "If a source would deal damage to this creature,
        # prevent N of that damage." Parameterised on N, so a static and not a
        # keyword -- and *not* protection, which prevents all of it and three
        # other things besides. Read by `damage_permanent` alone.
        "prevent_damage",
        # "This creature crews Vehicles as though its power were 2 greater." --
        # Hotshot Mechanic, and the Pilot token Shorikai, Reckoner Bankbuster
        # and a dozen others make. Parameterised on N, so a static and not a
        # keyword -- and *not* `buff`, which changes the creature's real power:
        # the Pilot stays a 1/1 in combat, for `power_of`, and for every other
        # sum on the board. Read by `costs._crew_power` alone, the one sum a
        # crew cost takes, and by nothing in the characteristics pipeline.
        "crew_power_bonus",
        # Ancient Greenwarden.  A fact about the *player*, like the two above:
        # it is read by `triggers.collect` rather than by the characteristics
        # pipeline, and there is no object for it to attach to.
        "double_land_triggers",
        # "That ability triggers an additional time" scoped to a permanent
        # (Harmonic Prodigy) or to a cause (Veyran). Distinct from
        # `double_land_triggers`, which is player-wide and land-only.
        "double_triggers",
        # "Spells can't be countered" -- Lier. A claim about EVERY spell every
        # player casts, which the card-level `uncounterable` flag cannot make:
        # that one is a card saying it about itself.
        "spells_cant_be_countered",
        # Vorinclex's two halves.  Both are read at the mana choke point rather
        # than as triggers, because tapping for mana happens inside payment
        # where nothing can go on the stack.
        "double_land_mana",
        # Kinnan, Bonder Prodigy: "Whenever you tap a **nonland** permanent for
        # mana, add one mana of any type that permanent produced." The line
        # above with one printed word changed, and read at the same choke point
        # for the same reason. Two effect names rather than one with an
        # author-written filter: the printed class is what names the card, and
        # no permanent is both, so they can never both apply to one tap.
        "double_nonland_mana",
        "freeze_opponent_lands",
        # Crypt Ghast: "Whenever you tap a Swamp for mana, add an additional
        # {B}." A triggered mana ability (605.1b), which resolves immediately,
        # so it is read at the mana choke point beside `double_land_mana` rather
        # than queued: `tapped_permanent` says what was tapped, `add_mana` the
        # fixed mana added.
        "add_mana_on_tap",
        # "This creature can't be blocked by Humans", and Tromokratis'
        # "can't be blocked unless all creatures defending player controls
        # block it".  Read by `combat`, not by the characteristics pipeline.
        "block_restriction",
        # Murkfiend Liege.  Read by `turn._untap_step`, not by the
        # characteristics pipeline: it is a fact about when a set of
        # permanents untaps, which no characteristic can carry.
        "untap_during_each_untap_step",
        # Mana Vault ("This artifact doesn't untap during your untap step"),
        # Back to Basics, Intruder Alarm, Winter Orb.  The exact inverse of the
        # line above and read in the same place, `primitives.untap_all`, for the
        # same reason.  Its `affects` routinely names permanents its controller
        # does not control -- both printed sentences say "their controllers'
        # untap steps" -- so like `cant_attack` it is not a fact about one side.
        "skip_untap_step",
        # Stormtide Leviathan.  Read by `combat.can_attack`.  A global
        # prohibition, so unlike every other static here its `affects`
        # routinely names creatures its own controller does not control.
        "cant_attack",
        # Unleash, and the "can't block" printed on aggressive commons. The
        # mirror of `cant_attack`, read by `combat.can_block`, and a static
        # rather than a keyword for the same reason `block_restriction` is: a
        # keyword is a characteristic and this is a permission.
        "cant_block",
        # "This creature can't attack or block alone" -- Toby's Beast token, and
        # the two halves it is spelled from, each of which is also printed on
        # its own. Separate effects from `cant_attack`/`cant_block` rather than
        # a flag on them, because they answer a different question: those two
        # are absolute per-creature prohibitions read by `can_attack`/
        # `can_block`, and these are restrictions on the *declaration as a
        # whole* (508.1c, 509.1b), read by `combat.attacks_valid` and
        # `combat.blocks_valid` beside menace. Written into `cant_attack` as a
        # flag, every existing caller would have read the flagless `True` and
        # stopped the creature attacking at all -- strictly stronger than the
        # printed card, and invisible on screen.
        "cant_attack_alone",
        "cant_block_alone",
        # Marauding Maulhorn.  The obligation to `cant_attack`'s prohibition,
        # read by `combat.attack_required` at the same enforcement point the
        # `must_attack` op uses.  A static rather than that op because a
        # printed "attacks each combat if able" is true again every turn, where
        # the op writes a one-shot flag that is spent on declaration.
        "attacks_if_able",
        # Propaganda, and the pillowfort family behind it. Parameterised on a
        # `cost` like `ward`, and for the same reason it cannot be a keyword.
        # Read by `characteristics.attack_tax` at declare-attackers, where it
        # prices an attack against the permanent's own controller rather than
        # forbidding one: `cant_attack` and the `cant_attack_player` op are both
        # absolute, so a card built on either is a lock rather than a tax --
        # strictly stronger than what is printed.
        "attack_tax",
        # Combat Calligrapher: "Inklings can't attack you or planeswalkers you
        # control."  `attack_tax` with the price taken out, and read at the same
        # moment by `characteristics.attack_defender_forbidden` through
        # `combat.attack_target_forbidden`: `affects` says which creatures are
        # stopped and the permanent's own controller is the seat they may not
        # attack.  Neither absolute cousin will do -- `cant_attack` takes no
        # defender, so an Inkling under it could not attack anybody, and the
        # `cant_attack_player` op is a resolving one-shot keyed on a pair of
        # seats with no creature filter.  Unlike that op, this one **does** reach
        # the defender's planeswalkers, because this sentence names them.
        "cant_attack_you",
        # "Equipped creature ... can't be sacrificed" (Assault Suit, 701.17b).
        # The continuous half of the `cant_sacrifice` op, and it has to be a
        # second mechanism for the reason `cant_attack_you` is not the
        # `cant_attack_player` op: that one records a *set* of permanents named
        # when a spell resolved, and an Equipment's prohibition must end when it
        # is unequipped and move when it is equipped elsewhere -- neither of
        # which a recorded set can do. Read at `temp_effects.sacrifice_forbidden`,
        # the one seam both roads to a sacrifice already go through.
        "cant_sacrifice",
        # Ward. Parameterised on a *cost*, so it cannot be a keyword for the
        # reason `protection` cannot: `KNOWN_KEYWORDS` is a set of bare strings
        # and there is nowhere in one to put the `{1}`. Read by
        # `triggers._candidate_abilities` rather than by the characteristics
        # pipeline, because what it hands out is a triggered ability -- and it
        # hands it to the *warded* permanent, so killing the granter in response
        # does not escape the tax.
        "ward",
        # Warden of Evos Isle.  Read by `costs.cost_reduction`, not by the
        # characteristics pipeline: it prices a card that is still in hand, so
        # its filter (`affects_spells`) matches a printed face rather than a
        # permanent, and is a different list from `affects`.
        "spell_cost_reduction",
        # Terror of the Peaks. "Spells your opponents cast that target this
        # creature cost an additional 3 life to cast." An additional cost
        # (601.2f) imposed on somebody *else's* spell, and it is not the line
        # above pointing the other way: `spell_cost_reduction` is mana
        # arithmetic, subtracted and clamped at zero by `costs.cost_reduction`,
        # so a negative `amount` there could only round away to "costs nothing
        # extra" -- which is why the loader now refuses one. This carries a
        # `cost` node instead, the way `ward` and `attack_tax` do, and the
        # loader holds it to `pay_life`: life is the one resource a caster can
        # be made to spend on a stranger's terms without the payment solver
        # having anything to say about it.
        "spell_cost_increase",
        # Strong Back. "Equip abilities you activate … cost {3} less to
        # activate." The mirror of the line above, for activated abilities
        # instead of spells, and read by `costs.ability_mana` -- the one
        # function `can_pay` and `pay` both reach, so an ability offered at the
        # reduced price is charged at it.
        #
        # `Cost.mana_reduction` is the near miss and is a different sentence: it
        # lives inside the ability's own cost node, so only the card printing
        # the ability could discount it. Strong Back is an Aura discounting
        # somebody else's Equipment.
        "ability_cost_reduction",
        # Academy Manufactor, Divine Visitation.  "If you would create a Clue,
        # Food, or Treasure token, instead create one of each."  Read by
        # `primitives.create_token`, which is the only moment a token creation
        # can still be intercepted -- a `replacements` entry could not, because
        # every one of those modifies a permanent that is already arriving, and
        # a `token_created` trigger fires after the token exists and would add
        # tokens alongside rather than instead.  Narrow on purpose: see
        # `docs/rules-coverage.md`, which records that there is no general
        # rule-616 replacement system and that this is not the start of one.
        "replace_token_creation",
        # High Score, Hardened Scales, Doubling Season, Corpsejack Menace. "If
        # one or more +1/+1 counters would be put on a creature you control,
        # that many plus one +1/+1 counters are put on it instead." Read by
        # `primitives.add_counters`, which is the single funnel every placement
        # comes through -- the `add_counters` op, `move_counters`, `proliferate`,
        # the `counters` key on `put_onto_battlefield` and entering with
        # counters -- so the replacement applies once per batch and before the
        # `counter_placed` event or any Saga chapter comparison reads the new
        # total.
        #
        # Unlike the five replacements above it, this one is about an *object*
        # rather than a player, so it takes `affects` and no `affects_player`:
        # every printed card names what the counters would be put on.
        #
        # A `counter_placed` trigger is the wrong sentence twice over: it uses
        # the stack, so the extra counter arrives after state-based actions and
        # after anything else that read the count, and its own `add_counters`
        # fires `counter_placed` again, so it retriggers itself.
        "replace_counters",
        # Inquisitor's Flail, Furnace of Rath, Gratuitous Violence, Fiery
        # Emancipation. "If equipped creature would deal combat damage, it deals
        # double that damage instead." Read by `primitives.damage_permanent` and
        # `primitives.damage_player`, the two points every damage in the game
        # passes through, after prevention and before the number is marked -- so
        # deathtouch, lifelink, infect, the damage ledger, the commander tally
        # and `DAMAGE_DEALT` all see the doubled figure, which is what makes it
        # a replacement rather than a second helping of damage.
        #
        # Filtered on **both ends**, which is why it is not one of the five
        # player-wide multipliers above: `damage_source` is "if <this> would
        # deal", `affects` is "…to <this>". The Flail prints one line of each.
        # `replace_life_loss` is the near miss and is genuinely a different
        # sentence: damage is not life loss -- it is marked on creatures, feeds
        # deathtouch and infect, and only incidentally reduces a life total --
        # so doubling the loss leaves a doubled hit on a creature undoubled.
        "replace_damage",
        # Ajani Steadfast's emblem: "If a source would deal damage to you or a
        # planeswalker you control, prevent all but 1 of that damage." A cap on
        # each damage event, the inverse of absorb N (which prevents N and lets
        # the rest through). Recipient named by `affects` (permanents) and/or
        # `affects_player` (seats), read as a union like `replace_damage`'s.
        # Read by `primitives.damage_permanent` and `primitives.damage_player`
        # through `player_statics.damage_cap`.
        "prevent_all_but",
        # Bloodletter of Aclazotz.  "If an opponent would lose life during your
        # turn, they lose twice that much life instead."  The engine's *second*
        # replacement hook and, like the first, a named one rather than the
        # start of a rule-616 system: `docs/rules-coverage.md` records that a
        # replacement of anything but a token creation is engine work, and this
        # is that work done once, for life loss.  Read by `primitives.lose_life`
        # and by the life-loss half of `primitives.damage_player`, which are
        # the two places a player's life goes down.
        "replace_life_loss",
        # Alhammarret's Archive.  "If you would gain life, you gain twice that
        # much life instead."  The mirror of `replace_life_loss`, read by
        # `primitives.gain_life` -- the one place a life total goes up, which
        # lifelink reaches too.  Not a `you_gain_life` trigger that gains again:
        # that is a second gain on the stack, visible to every life-gain trigger
        # as its own event, and it re-triggers itself.
        "replace_life_gain",
        # Erebos, God of the Dead.  "Your opponents can't gain life."  A
        # prohibition on a *player*, read by `primitives.gain_life` before any
        # replacement of the gain, so an Alhammarret's Archive cannot double a
        # forbidden gain.  Not `lock_life_total`, which is a one-shot op with a
        # duration and forbids a loss as well.
        "cant_gain_life",
        # Thought Reflection, Bard, King of Dale, Alhammarret's Archive.  "If you
        # would draw a card, draw two cards instead", optionally "except the
        # first one you draw in each of your draw steps".  Read by
        # `replacements.draw`, which every draw after the opening hand goes
        # through one card at a time -- the only place a draw can still be
        # replaced; a `draw` trigger fires after the card is in hand and would
        # add a card alongside rather than instead.
        "replace_draw",
        # Bruvac the Grandiloquent, Fraying Sanity.  "If an opponent would mill
        # one or more cards, they mill twice that many cards instead."  The mill
        # member of the family above, and the shape differs from `replace_draw`
        # in one rules-relevant way: 701.13a makes milling N cards **one** event,
        # not N of them, so this multiplies a count once rather than recursing
        # per card the way `replacements._draw_one` must for 121.2.  Read in
        # `primitives.mill_cards`, the single choke point every mill goes
        # through -- a `mill` op, a `mill` cost and dredge (702.52a) alike --
        # which is what makes it apply to mills the *opponent's* own cards cause.
        # A `mill` trigger could not do it: there is no such trigger event, and
        # one would fire after the cards were already in the graveyard and mill
        # again alongside rather than instead.
        "replace_mill",
        # Jace, Wielder of Mysteries; Laboratory Maniac.  "If you would draw a
        # card while your library has no cards in it, you win the game instead."
        # The one draw-replacement branch `replace_draw` can never reach, since
        # there is no card to multiply -- and it substitutes a different
        # *outcome* rather than a size, which is why it could not be a key on
        # that static, whose only parameter is a number refused below 2.  Read
        # in `replacements._draw_one`, before the doublers, so an empty library
        # wins on the first of a doubled pair rather than after both have failed.
        "replace_empty_draw",
        # Voice of Victory.  "Your opponents can't cast spells during your
        # turn."  A prohibition on a *player*, so it takes `affects_player` and
        # no `affects`, and it is read wherever a spell can be cast rather than
        # by the characteristics pipeline: `casting._cast_actions` withholds the
        # actions, and `suspend.cast_for_free`, `replacements._offer_cast` and
        # `op_cast_copy` refuse the casts a resolving effect would make (101.2).
        # Not `split_second`, which lives on the stack and binds every player,
        # and not `epic`, which is a card-level rider with no seat or duration.
        "cant_cast_spells",
        # Grand Abolisher; Myrel, Shield of Argive.  "…or activate abilities of
        # artifacts, creatures, or enchantments."  The *other half* of the
        # sentence above, and a separate static because it prohibits a different
        # action: `cant_cast_spells`'s own docstring lists "activating abilities"
        # among the things it deliberately does not stop.
        #
        # Unlike its twin, `affects` is **required** rather than refused. Every
        # printed card in this family names permanent types, so a filterless
        # version would stop opponents' lands and planeswalkers too -- a
        # strictly stronger lock than anything printed. Read in
        # `legality._activate_actions` and in `costs._sources_of`, because 605.1a
        # makes a mana ability an activated ability and a locked permanent that
        # still taps for mana makes the lock worthless.
        "cant_activate_abilities",
        # Tidal Barracuda; Leyline of Anticipation; Vedalken Orrery.  "Any
        # player may cast spells as though they had flash."  The permissive twin
        # of the prohibition above, and the only static that widens a *timing*
        # window rather than a zone one -- read in `casting._timing_ok`, the one
        # seam every cast path asks, whichever zone the spell is coming from.
        # Granting `flash` cannot stand in: `_timing_ok` reads the CardDef's
        # printed keywords and never an object's granted ones, a static's filter
        # has no `zone` with which to name the cards in hand, and the permission
        # has to cover cards drawn after the source arrived.
        "cast_as_though_flash",
        # Teferi, Time Raveler.  "Each opponent can cast spells only any time
        # they could cast a sorcery."  The narrowing twin of the permission
        # above: 307.1's window for every spell those players cast.  Read in
        # `casting._timing_ok` *before* the flash branches (101.2: the "only"
        # beats every "may"), and at each resolution-time cast, which happens
        # with the stack non-empty and so is never sorcery timing.
        "cast_only_at_sorcery_speed",
        # Teferi, Master of Time.  "You may activate loyalty abilities of Teferi
        # on any player's turn any time you could cast an instant."  `affects`
        # says whose loyalty abilities are freed -- `{"self_only": true}` is the
        # printed "of Teferi".  Read in `legality._ability_aims`, which is where
        # `sorcery_speed_only` refuses an ability; the loader forces that flag on
        # for every loyalty ability (`model.sorcery_speed_only or cost.loyalty is
        # not None`), so no card could reach it and the permission had to come
        # from the board.  It lifts the *window* only: 606.3's one-loyalty-
        # ability-per-permanent-per-turn limit is checked separately and stands.
        #
        # Named for loyalty because that is the half that can be answered
        # exactly.  Leonin Shikari's "you may activate equip abilities any time
        # you could cast an instant" wants this seam pointed at equip, and
        # nothing on `Ability` marks an equip ability yet.
        "activate_loyalty_as_though_instant",
    }
)

#: The statics that describe a **player** rather than a characteristic, and so
#: take ``affects_player`` instead of ``affects``.
#:
#: One list rather than a tuple written out at the check site, because two
#: readers now need it: the requirement that they carry `affects_player`, and
#: `GRANTABLE_STATIC_EFFECTS` below, which excludes them. Two copies would be two
#: places to disagree about whether a new player-wide static may be granted.
PLAYER_WIDE_STATIC_EFFECTS = frozenset(
    {
        "extra_land_drops",
        "no_hand_limit",
        "skip_draw_step",
        "skip_extra_turn",
        "play_lands_from_graveyard",
        "cast_from_graveyard",
        "cast_from_library_top",
        "free_cast_permission",
        "grant_warp",
        "black_mana_as_phyrexian",
        "spend_mana_as_any_color",
        "play_lands_from_library_top",
        "reveal_library_top",
        "look_at_library_top",
        "double_land_triggers",
        "double_land_mana",
        "double_nonland_mana",
        "add_mana_on_tap",
        "freeze_opponent_lands",
        "replace_life_loss",
        "replace_life_gain",
        "replace_draw",
        # Bruvac the Grandiloquent, Fraying Sanity. The mill member of the
        # `replace_*` family above, applied in `primitives.mill_cards` -- the
        # one choke point every mill goes through, so a `mill` op, a `mill`
        # cost and dredge are all replaced, whoever caused them.
        "replace_mill",
        "replace_empty_draw",
        "cant_cast_spells",
        "cant_activate_abilities",
        "untap_limit",
        "cast_as_though_flash",
        "cast_only_at_sorcery_speed",
        "cant_gain_life",
    }
)

#: Statics whose readers walk **printed** faces, so a granted one would be inert.
#:
#: Two families, and both read the printed list for the same acyclicity reason:
#:
#: * `characteristics.ABILITY_STATICS` -- `grant_ability` and
#:   `lose_all_abilities` are gathered by `_ability_statics`, which *must* read
#:   printed faces, because `_battlefield_statics` reads `abilities_of` and
#:   `abilities_of` reads them. Granting one is therefore both the recursion the
#:   fixed order exists to avoid and, as the code stands, a silent no-op.
#: * the player-wide ones, plus `replace_token_creation` -- all read through
#:   `characteristics._active_player_statics`, which walks printed faces and
#:   never sees an appended granted ability.
#:
#: Refused by name rather than left to load, because every one of them would
#: produce a card that loads clean, prints a line of quoted text and does
#: nothing -- which is the exact failure the whole validation pass exists to
#: stop.
UNGRANTABLE_STATIC_EFFECTS = (
    PLAYER_WIDE_STATIC_EFFECTS | {"replace_token_creation"} | frozenset(ABILITY_STATICS)
)

#: Statics a `grant_ability` static may hand to another permanent.
#:
#: Derived rather than listed, and the subtraction is the definition: everything
#: read through `characteristics._battlefield_statics`, which walks `abilities_of`
#: and so finds a granted static sourced on its **recipient**. Nothing else in
#: this file needs to know which layer a given effect lands in.
#:
#: Inspiring Leader is the card: "Commander creatures you own have "Creature
#: tokens you control get +2/+2."" -- a `buff` in `grantable_abilities`, handed
#: over by a `grant_ability` static whose `affects` reads
#: ``{"types": ["Creature"], "is_commander": true, "owner": "you"}``.
GRANTABLE_STATIC_EFFECTS = STATIC_EFFECTS - UNGRANTABLE_STATIC_EFFECTS

#: Keys a ``replace_token_creation`` static's ``affects_token`` filter may use.
#:
#: The printed face of a token definition, and nothing else.  Not
#: `SPELL_FILTER_KEYS`, which carries `controller`: the token being asked about
#: has not been created, so it has no controller of its own, and *whose* token
#: it is has already been decided before the filter is asked -- these
#: replacements are their controller's own ("if you would create…", "under your
#: control"), so a `controller` key here could only restate that or contradict
#: it.
TOKEN_FILTER_KEYS = frozenset(
    {
        "types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        "not_keywords",
        "name",
    }
)

#: Keys a ``spell_cost_reduction`` static's ``affects_spells`` filter may use.
#:
#: Deliberately not `STATIC_FILTER_KEYS`: that list describes *permanents* and
#: carries board state (`tapped`, `attacking`, `attached`) which a card in hand
#: does not have.  These are the printed face plus who is casting it, which is
#: all `characteristics._matches_printed` reads.
SPELL_FILTER_KEYS = frozenset(
    {
        "controller",
        "types",
        # The or-of-types question. `types` is a conjunction, so "instant and
        # sorcery spells you cast cost {1} less" cannot be said with it -- a
        # spell is never both at once.
        "any_types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        # "Whenever you cast a **multicolored** instant or sorcery spell" --
        # Lilah, Undefeated Slickshot. Two or more colors, any two, which
        # `colors` cannot say: it is a membership test, so `["U","R"]` matches a
        # mono-blue spell, and `require_all` would mean exactly those colours
        # and no others. Written as a number rather than a `multicolored`
        # boolean because the number is what the rules say (202.2b) and reads
        # the same on the rarer "three or more colors".
        "min_colors",
        "keywords",
        "not_keywords",
        "name",
        # "…spells with mana cost {X}". Printed, so `_matches_printed` reads it.
        "mana_cost",
    }
)

#: `SPELL_FILTER_KEYS` plus the one word only a *price* can act on.
#:
#: "**Other** Dragon spells you cast cost {1} less" -- The Ur-Dragon. Read by
#: `player_statics.spell_cost_reduction` itself rather than by
#: `_matches_printed`, which is handed a card face and has no source to compare
#: it against, and kept out of the shared set so `cast_from_graveyard` -- whose
#: permission is offered from a zone its own source is never in -- still refuses
#: a word that would do nothing there.
#:
#: Unsayable before eminence, and unnecessary too: a permanent's own spell is
#: never on the stack while that permanent is on the battlefield. A commander's
#: is, because the command zone its eminence static is gathered from is the very
#: zone it is cast out of.
SPELL_COST_REDUCTION_FILTER_KEYS = SPELL_FILTER_KEYS | {"exclude_self"}

#: `SPELL_FILTER_KEYS` plus the one word a **union of two printed shapes** needs.
#:
#: "**Artifact cards and red creature cards** in your hand have warp {2}{R}" --
#: Tannuk, Steadfast Second. Every other key in a printed-face filter is ANDed,
#: so the sentence is unsayable without a disjunction: ``{"types":
#: ["Artifact", "Creature"], "colors": ["R"]}`` matches only a red artifact
#: creature, and ``any_types`` is an or over *types* alone -- it would let a
#: blue creature card through, which is exactly the scope this grant must not
#: have.
#:
#: Spelled as the effect-side selector and `COST_REDUCTION_FILTER_KEYS` already
#: spell it, so one printed word has one spelling wherever it is written; read
#: by `characteristics._matches_printed`, which recurses into the branches.
#: Kept off `SPELL_FILTER_KEYS` itself rather than widened into it, because
#: that set is shared with three statics whose readers were written before the
#: word existed and would walk past it -- a silent over-grant.
WARP_GRANT_FILTER_KEYS = SPELL_FILTER_KEYS | {"any_of"}

#: Keys a *static* ability's filter may use.  Deliberately smaller than the full
#: selector language: static filters are matched against printed characteristics
#: so that no static can depend on another static's output.
STATIC_FILTER_KEYS = frozenset(
    {
        "exclude_self",
        "self_only",
        "controller",
        "types",
        "any_types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        # "Creatures **without** flying or islandwalk can't attack."  The
        # negated form, which the effect-side selector language always had
        # and the static one did not.
        "not_keywords",
        # "**Nonbasic** lands don't untap during their controllers' untap
        # steps" (Back to Basics). The negation of `supertypes` above, added
        # for `not_keywords`' reason: the effect-side selector language always
        # had it and the static one did not. Not the same as a `not_types`
        # complement, which would be every permanent that is not a land.
        "not_supertypes",
        # "…with mana cost {0} or {1}". The printed cost, which no layer moves,
        # so it is as safe here as `types` is. See `mana.printed_cost_is`.
        "mana_cost",
        "tapped",
        "is_commander",
        # "Commander creatures you **own**."  903.3 makes ownership the relation
        # the commander rules use, and it is the one place where the printed
        # word is "own" rather than "control" on a *permanent* filter: a
        # commander an opponent has stolen is still one you own, and one you
        # have stolen is not one you own. Board state that no layer can touch --
        # `owner` is written when the object is made and `change_control` leaves
        # it alone -- so it is safe here for exactly the reason `controller` is.
        #
        # Writing `owner` **replaces** the defaulted `controller: "you"` rather
        # than adding to it; `characteristics._matches` says why, and
        # `costs._reduction_matches` has read the word that way all along.
        "owner",
        "is_token",
        "attacking",
        "blocking",
        # "Enchanted creature gets +2/+2".  Reads `attached_to`, which is board
        # state rather than a derived characteristic, so it cannot depend on
        # another static's output and belongs in this list rather than outside it.
        "attached",
        # The other end of the same relationship: "…as long as two or more
        # Equipment are **attached to it**" (Brass Knuckles), "+2/+2 for each
        # Aura and Equipment **attached to it**" (Strong Back). `attached` names
        # the host; this names the host's *other* attachments. The same board
        # state read the other way round, so it is safe here for `attached`'s
        # reason.
        "attached_to_host",
        # Soulbond: "as long as this creature is paired, **both** creatures
        # have…". `paired: true` matches the source while it has a partner, and
        # `paired_with_source: true` matches the partner. Board state like
        # `attached`, and safe for the same reason.
        "paired",
        "paired_with_source",
        # "Zurgo and Ojutai has hexproof as long as **it entered this turn**";
        # "If a creature you control **that entered this turn** would deal
        # damage, it deals twice that much damage instead" (Neriv, Heart of the
        # Storm). The one clause in this list that is not a characteristic and
        # not a *current* relationship but a fact about the turn behind the
        # permanent -- and it is admissible here for the reason
        # `permanents_entered_this_turn` is admissible in `STATIC_VALUE_KEYS`,
        # one step more safely than `tapped` is. An arrival is written into
        # `TurnLedger.permanents_entered` once, by `GameState.emit` folding
        # ENTERS_BATTLEFIELD, and no layer of the characteristics pipeline can
        # write to it; so it is a pipeline **input** exactly as `owner` and
        # `controller` are, and reading it cannot make one static depend on
        # another's output. Power is the contrast: it is an *output*, rewritten
        # by four of the layers, so it could never be let in on these terms --
        # and the entry below lets it in on quite different ones.
        #
        # "Printed characteristics" was always shorthand for "printed
        # characteristics plus board state no layer touches" -- `tapped`,
        # `attacking`, `is_token`, `owner` are all already here on that footing.
        # This is that same licence pointed at the turn ledger.
        "entered_this_turn",
        # "…for each creature you control **with power 4 or greater**" (Temur
        # Battlecrier), and the whole ferocious family beside it -- "as long as
        # you control a creature with power 4 or greater", "creatures with
        # toughness 2 or less". The only **derived** characteristic in this
        # list, and it is here under a restriction rather than as an exception.
        #
        # `entered_this_turn` one entry up got in by being an *input* no layer
        # writes; power cannot get in on those terms, because four layers
        # rewrite it and a static that read another static's P/T output is
        # exactly the cycle `check_static_constraints` exists to forbid. The
        # answer is not to widen the rule but to name a **fixed, earlier**
        # reading of power that no static can move:
        # `characteristics._base_pt` -- printed P/T, a copy exception's
        # replacement of it (707.9b), bestow's 0/0, and a face-down permanent's
        # 2/2 (707.2). No `animate`, no `set_pt`, no anthem, no +1/+1 counter,
        # no pump. The fixed order stays exactly as acyclic as it was, and
        # `_compute` opens by calling the same function, so the filter's answer
        # cannot drift from the pipeline's starting point.
        #
        # The cost is one sentence, and it is a sentence `keywords` in this list
        # already carries: a 3/3 pumped to 4 power by an anthem is not "a
        # creature with power 4 or greater" to a static, exactly as a creature
        # granted flying by Levitation does not have flying to one. The two
        # readers of this language that run *outside* the pipeline --
        # `triggers.matches_card_filter` and `cost_reduction._object_matches` --
        # read the fully derived number, as they already do for types and
        # keywords.
        "power",
        # The twin. One reader, one restriction, one set of tests: splitting
        # them would be two spellings of one clause and one of them untested.
        "toughness",
    }
)

#: Who a filter's ``owner`` (or ``controller``) may name, relative to the source.
_FILTER_PLAYERS = ("you", "opponent")


#: The two "of the chosen …" substitutions a static filter may carry.
_CHOSEN_QUALITY_KEYS = ("chosen_type_of", "chosen_color_of")


#: Ops that take an object out of the zone an ability was activated from.
#: Unearth's `put_onto_battlefield`, and the three other destinations a card
#: could plausibly be sent to by its own ability.
SOURCE_MOVING_OPS = frozenset({"put_onto_battlefield", "exile", "return_to_hand", "put_on_top"})


#: Which trigger a ``{"was_cast": …}`` clause may hang from.
#:
#: 603.6e's "if it was cast" is a fact about the arrival of the permanent the
#: ability is *on*, and the condition is evaluated with the ability's own source
#: (`triggers._matches` passes ``source=obj.oid``). Every other home for it is a
#: card that loads clean and plays wrong, in one of two directions:
#:
#: * on ``permanent_enters`` -- "whenever **another** creature enters, if it was
#:   cast" -- it answers about the trigger's own permanent, not the one that
#:   entered, so the clause reads a fact about an unrelated object;
#: * anywhere else (a spell's own effects, an activated ability, a dies trigger)
#:   it asks a permanent that has not entered anything on this trip, and reads a
#:   flat ``False`` for ever.
WAS_CAST_TRIGGERS = frozenset({"self_enters"})


#: Ways a card may say how much less it costs.  ``count`` is "{1} less for each
#: X"; ``total_power`` is Ghalta's "the total power of creatures you control";
#: ``amount`` is a flat "{3} less", which only means anything gated on a
#: ``condition`` -- an ungated flat reduction is a smaller printed cost;
#: ``greatest_mana_value`` is Visions of Glory's "the greatest mana value of a
#: commander you own", a **maximum** rather than a sum and so its own key --
#: written as a `count` or a `total_power` it would add two partners' mana
#: values together and quietly hand out a bigger discount than the card says.
#: ``greatest_count`` is Cavern-Hoard Dragon's "the greatest number of artifacts
#: **an opponent** controls" -- what `count` is to `greatest_mana_value`'s
#: `total_mana_value`, one axis over: the tally is taken per player and
#: maximised, because a reduction filter's ``controller: "opponent"`` names
#: every opponent at once and so `count` is their **sum**. Its own key for the
#: sharpest reason on this list: at a pod of four, three opponents with two
#: artifacts each read {6} where the card says {2}, and in a two-player game
#: the two numbers are identical -- so the wrong key is invisible until a pod.
COST_REDUCTION_KEYS = frozenset(
    {
        "count",
        "greatest_count",
        "total_power",
        "amount",
        "greatest_mana_value",
        "total_mana_value",
    }
)

#: Zones a cost reduction's filter may count.  **Imported** from
#: `costs.REDUCTION_ZONES`, which is what actually walks them, rather than
#: restated here: this was a hand-copied mirror, and a mirror of a list is a list
#: that will one day disagree with the code it mirrors -- a zone this file
#: accepted and `_reduction_zone_oids` did not walk would load and match nothing.
#: `total_power` is battlefield-only whatever this says -- see below.
COST_REDUCTION_ZONES = REDUCTION_ZONES

#: Extra filter keys a cost reduction accepts on top of `STATIC_FILTER_KEYS`.
#:
#: ``zone`` is the only one left. ``owner`` was here alone, on the grounds that a
#: static applies to permanents "where control is the question" -- and Inspiring
#: Leader is the card that showed that reasoning was about *most* statics rather
#: than all of them. "Commander creatures you own have …" is a permanent filter
#: whose printed word is "own", and 903.3 is why: on a commander, ownership is
#: the relation the rules use. So ``owner`` moved into `STATIC_FILTER_KEYS` and
#: is listed here no longer; it is still spelled and read the same way, which is
#: what made the move a one-line change rather than a second dialect.
#:
#: What a reduction kept is the *reason* it wanted the word first: reading the
#: command zone, where "a commander you own on the battlefield or in the command
#: zone" still counts the commander an opponent stole from you.
#: ``any_of`` is the second, and it is a *disjunction* rather than a
#: characteristic: "the total mana value of **historic** permanents you control.
#: (Artifacts, legendaries, and Sagas are historic.)" -- Excalibur, Sword of
#: Eden. Every other key in a reduction filter is ANDed, so historic is
#: unsayable without it -- ``{"types": ["Artifact"], "supertypes":
#: ["Legendary"], "subtypes": ["Saga"]}`` matches only a permanent that is all
#: three at once, which nothing is. ``any_types`` is an or over *types* alone
#: and reaches neither a supertype nor a subtype.
#:
#: Spelled as the effect-side selector language already spells it (Lost to
#: Legend's target line is exactly this shape), so one printed word has one
#: spelling wherever it is written.
COST_REDUCTION_FILTER_KEYS = frozenset({"zone", "any_of"})

#: Filter keys a cost reduction *refuses*, though a static ability accepts them.
#:
#: Each names a relation to one particular permanent -- the thing the source is
#: attached to, or its soulbond partner -- and a reduction counts a board. On a
#: static's `affects` that relation is the whole point ("enchanted creature gets
#: +2/+2"); in a `count` it asks how many permanents are the one permanent, an
#: answer of nought or one that no printed reduction is about. They were
#: accepted and silently ignored before `costs._reduction_matches` learned to
#: read the rest of the list, and being refused is the safer half of that fix:
#: a key that means nothing here should say so at load time rather than price
#: an ability off a filter nobody honoured.
#:
#: `attached_to_host` joins them for the near reason rather than the same one:
#: counting a permanent's attachments *is* a number a reduction could price off,
#: but `costs._reduction_matches` does not read the key, so one written there
#: would load and be ignored -- the quiet failure this list exists to convert
#: into a load-time refusal. It belongs here until a printed card asks for it
#: and `_reduction_matches` is taught the word.
COST_REDUCTION_REFUSED_FILTER_KEYS = frozenset(
    {"attached", "attached_to_host", "paired", "paired_with_source"}
)

#: Condition heads a *cost* reduction may use.
#:
#: A reduction is evaluated while deciding what is castable or activatable --
#: before the spell is on the stack and before any cost is paid -- so the four
#: cast-variant flags (`kicked`, `evoked`, `overloaded`, `cast_from_graveyard`)
#: are not merely useless here, they read ``False`` every time and would give a
#: card a discount clause that can never fire.  Refused rather than allowed to
#: load, because nothing on a board would ever say so.
#:
#: `cast_during` is the fifth and the worst of them, so it is absent for both
#: reasons at once: the phase stamp is written as the spell goes on the stack,
#: which has not happened yet, and a card being priced for its *second* cast
#: still carries the stamp from its first -- so this one would not read a
#: harmless ``False``, it would read a stale ``True``.
COST_CONDITION_HEADS = frozenset(
    {
        "all",
        "any",
        "not",
        "cmp",
        "left",
        "right",
        "exists",
        "is_your_turn",
        "has_city_s_blessing",
        "is_monarch",
        "no_monarch",
        "combat_damage_by",
        # Both read the reduction's own source, which is a real object at
        # pricing time: the permanent whose ability is being activated, or the
        # card in the graveyard being cast.
        "zone_is",
        "has_flag",
    }
)


#: Comparisons a static's "as long as..." clause may use.
STATIC_CONDITION_OPS = frozenset({">=", "<=", ">", "<", "=", "==", "!="})

#: The forms a static's condition may take, one per node.
STATIC_CONDITION_HEADS = (
    "counters",
    "all",
    "any",
    "not",
    "exists",
    "is_your_turn",
    "has_city_s_blessing",
    "cmp",
    # "Attached permanents with reconfigure aren't creatures" (702.151d).
    # `attached_to` is a field the `attach` primitive writes, so it is a
    # pipeline input like a counter and no layer can change it. Distinct from
    # the `attached` *filter* key, which points the other way -- at the
    # permanent this one is attached to.
    "is_attached",
    # "As long as the top card of your library is black". A pipeline *input*
    # for the same reason a zone count is -- nothing in the characteristics
    # pipeline can change what is on top of a library -- but a strictly
    # sharper question than `exists` over the library, which asks whether any
    # black card is anywhere in ninety-nine and is nearly always true.
    "top_of_library",
)

#: Zones a static's *counting* filter may name.  The stack is absent: a static
#: is read while the pipeline computes characteristics, including for objects
#: that are themselves resolving, and "how many spells are on the stack" would
#: change under a card mid-resolution.
STATIC_COUNT_ZONES = frozenset({"battlefield", "graveyard", "hand", "exile", "library", "command"})

#: Keys a static's *counting* filter may use -- the selection keys, plus the
#: zone.  ``affects`` and ``blockers`` deliberately do not get ``zone``: they
#: pick out permanents the static applies to, and there are no permanents
#: outside the battlefield, so a zone there would load and match nothing.
#: ``name`` is here and deliberately *not* in ``STATIC_FILTER_KEYS``. "…unless
#: you control a creature named Advocate of the Beast" is a question the
#: condition asks about the board; "each creature named X gets +1/+1" is not a
#: card, so `affects` has no use for it and allowing it there would only invite
#: one.
STATIC_COUNT_FILTER_KEYS = STATIC_FILTER_KEYS | {"zone", "name"}

#: ...and once it names a zone other than the battlefield, only these.  A card
#: in a graveyard has a printed face and an owner; it is not tapped, attacking,
#: attached to anything or a token, so those keys are refused here rather than
#: loading and silently matching nothing.
STATIC_ZONE_FILTER_KEYS = frozenset(
    {
        "zone",
        "controller",
        # A card in a graveyard has no board state, but it does have a name.
        "name",
        "types",
        # The or-of-types question, for the same reason `SPELL_FILTER_KEYS` has
        # it: Glamdring's "+1/+0 for each instant **and** sorcery card in your
        # graveyard" counts two types, and `types` is a conjunction that would
        # have counted zero. Without this the card can only be written as two
        # statics summed, which is correct arithmetic (no card is both) and one
        # more ability than the printed line has.
        "any_types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        "not_keywords",
        # A card in a graveyard has a printed cost, too.
        "mana_cost",
    }
)


#: Player specs a static's per-player life leaf may name.  Smaller than the
#: effect-side list: `active_player` and the binding forms read something that
#: is not settled while characteristics are being computed.
STATIC_LIFE_PLAYERS = frozenset({"you", "opponent", "each_opponent", "each_player", "all"})

#: The per-player life leaves.  Safe inside a static for the same reason a zone
#: count is: a life total is a pipeline *input*, and nothing in the fixed-order
#: characteristics pipeline can change one.
STATIC_LIFE_KEYS = frozenset({"min_life_of", "max_life_of"})


#: Every leaf a static ability's magnitude may use -- a `buff`'s `power`, a
#: `set_pt`, a `spell_cost_reduction`'s `amount`, either side of a `cmp`.
#:
#: A **fourth** language, and much smaller than the effect-side `VALUE_KEYS`:
#: every leaf here reads a pipeline *input*, because anything reading a derived
#: characteristic would let one static depend on another's output and the fixed
#: order of layers-lite has no way to resolve that. Named rather than built
#: inline so the authoring packet can show it -- a worker shown `value_keys` and
#: not this one reads the effect-side list as the whole language, which is how
#: Door of Destinies came to be filed as a gap.
#: `times` is the one leaf here that does not *measure* anything: it multiplies
#: the others, for "+2/+2 for each Equipment you control" (Swordsman's Steel) --
#: a count with a step bigger than one. Two `buff` statics are not the
#: alternative they look like, since a static carries no `effects` and so it
#: would be two abilities claiming one printed line, which the residual gate
#: exists to refuse. Same spelling and shape as the effect-side `times`.
STATIC_VALUE_KEYS = (
    frozenset(
        {"const", "count", "times", "mana_symbols", "counters_on", "permanents_entered_this_turn"}
    )
    | STATIC_LIFE_KEYS
    | PER_PLAYER_COUNT_KEYS
)


#: Ops a mana ability's rider may use -- "this land deals 1 damage to you".
#:
#: A mana ability is activated inside cost payment and **must never stop to
#: ask**: there is no stack to put a decision on and no priority window to
#: answer it in, so an op that yields would hang the payment solver mid-tap.
#: These six change a number and return. Anything else is refused at load, which
#: is the difference between a card that will not compile and a game that locks
#: up the first time somebody taps a Talisman.
#: The classes of activated ability an `ability_cost_reduction` may name.
#:
#: One so far. Each is a question the engine can actually answer about a
#: compiled `Ability` -- `equip` reads `Ability.is_equip` -- and a class with no
#: marker behind it would load and match nothing, which is the printed line
#: silently not happening.
ABILITY_CLASS_KEYS = frozenset({"equip"})


MANA_RIDER_OPS = frozenset(
    {"damage", "lose_life", "gain_life", "add_poison", "add_counters", "remove_counters"}
)


#: Value forms a mana ability's ``amount`` may NOT use.
#:
#: A mana ability is activated inside cost payment, with nothing on the stack:
#: there is no X, no target, no trigger binding and no enclosing loop. Each of
#: these would evaluate to 0 and make a card that silently produces no mana, so
#: they are refused at load rather than at the table.
MANA_AMOUNT_FORBIDDEN = frozenset({"x", "target", "binding", "loop_value"})


#: The ops that read a ``counters`` map -- "return it to the battlefield **with a
#: -1/-1 counter on it**" (persist), "…**with a vigilance counter and a lifelink
#: counter on it**" (Gilraen).  Both are clauses about a permanent *arriving*,
#: which is why they belong to the two ops that put one there and to nothing else.
COUNTERS_ON_ARRIVAL_OPS = frozenset({"return_from_graveyard", "put_onto_battlefield"})


#: Target kinds whose chosen ref can be a **player**, so ``{"target": "t1"}``
#: means something as a player spec. ``"any"`` is here because "any target" is
#: creatures, planeswalkers *and* players (115.4) -- a damage op reads the ref
#: kind and does the right thing with either.
PLAYER_TARGET_KINDS = frozenset({"player", "any"})

#: Target kinds whose chosen ref always has a **controller**, so
#: ``{"controller_of_target": "t1"}`` means something. The complement of
#: :data:`PLAYER_TARGET_KINDS` rather than a list of its own, and deliberately
#: so: exactly one of the two keys is right for any given target spec, which is
#: what makes the pair a checkable choice instead of two ways to be wrong.
CONTROLLED_TARGET_KINDS = frozenset({"permanent", "spell", "card_in_graveyard", "card_in_exile"})


#: The ops that can put the permanent they make into combat.
ATTACKING_OPS = frozenset({"create_token", "copy_permanent", "put_onto_battlefield"})

#: Player specs that can name **more than one** seat. Fine for "each opponent
#: loses 1 life"; never right for ``attacking``, which is one creature pointed
#: at one player. ``"opponent"`` is here because a pod makes it three of them --
#: the reading that is invisible in a two-player game and wrong everywhere else.
PLURAL_PLAYER_SPEC_NAMES = frozenset({"opponent", "each_opponent", "each_player", "all"})


#: The clauses an *event-watching* delayed ability may carry (603.7).
#:
#: A subset of `TriggerSpec`, and the omissions are the point. Everything left
#: out is answered off the :class:`GameObject` hosting the ability, and a
#: delayed ability has none: `source: "self"` and `filter` are read off the
#: permanent that prints the trigger (`triggers.matches_card_filter` takes it as
#: `ability_source`), and `max_per_turn` is counted per `(permanent, ability
#: index)` by `triggers._queue`, which a delayed ability never reaches. Accepting
#: any of them would load a card whose printed restriction silently does nothing
#: -- the exact failure `_validate_effect` exists to stop.
#:
#: The pure event filters -- `counter`, `nth`, `not_cause`, `mana_ability`,
#: `defending` -- are left out because no card asks for them here, not because
#: they could not work. `_delayed_matches` gains a line each when one does.
DELAYED_TRIGGER_KEYS = frozenset({"event", "controller", "condition", "subject"})
