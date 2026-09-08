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

#: Static ability effects the characteristics pipeline understands.
STATIC_EFFECTS = frozenset(
    {
        "buff",
        "grant_keyword",
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
        "freeze_opponent_lands",
        # "This creature can't be blocked by Humans", and Tromokratis'
        # "can't be blocked unless all creatures defending player controls
        # block it".  Read by `combat`, not by the characteristics pipeline.
        "block_restriction",
        # Murkfiend Liege.  Read by `turn._untap_step`, not by the
        # characteristics pipeline: it is a fact about when a set of
        # permanents untaps, which no characteristic can carry.
        "untap_during_each_untap_step",
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
        # Bloodletter of Aclazotz.  "If an opponent would lose life during your
        # turn, they lose twice that much life instead."  The engine's *second*
        # replacement hook and, like the first, a named one rather than the
        # start of a rule-616 system: `docs/rules-coverage.md` records that a
        # replacement of anything but a token creation is engine work, and this
        # is that work done once, for life loss.  Read by `primitives.lose_life`
        # and by the life-loss half of `primitives.damage_player`, which are
        # the two places a player's life goes down.
        "replace_life_loss",
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
        "play_lands_from_graveyard",
        "cast_from_graveyard",
        "cast_from_library_top",
        "play_lands_from_library_top",
        "reveal_library_top",
        "look_at_library_top",
        "double_land_triggers",
        "double_land_mana",
        "freeze_opponent_lands",
        "replace_life_loss",
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
        "keywords",
        "not_keywords",
        "name",
    }
)

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
        # Soulbond: "as long as this creature is paired, **both** creatures
        # have…". `paired: true` matches the source while it has a partner, and
        # `paired_with_source: true` matches the partner. Board state like
        # `attached`, and safe for the same reason.
        "paired",
        "paired_with_source",
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
COST_REDUCTION_KEYS = frozenset({"count", "total_power", "amount", "greatest_mana_value"})

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
COST_REDUCTION_FILTER_KEYS = frozenset({"zone"})

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
COST_REDUCTION_REFUSED_FILTER_KEYS = frozenset({"attached", "paired", "paired_with_source"})

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
STATIC_VALUE_KEYS = (
    frozenset({"const", "count", "mana_symbols", "counters_on", "permanents_entered_this_turn"})
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
DELAYED_TRIGGER_KEYS = frozenset({"event", "controller", "condition"})
