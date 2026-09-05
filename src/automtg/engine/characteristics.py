"""Derived characteristics -- "layers-lite".

Real Magic resolves continuous effects through seven numbered layers with
timestamps and dependency analysis.  This engine applies a *fixed order* instead:

    printed -> subtype grants -> keyword grants (statics, then keyword counters)
    -> P/T setting -> P/T modifying -> +1/+1 and -1/-1 counters
    -> until-end-of-turn pumps

Counters are read in **two** places, and deliberately: a +1/+1 counter is a
size, so it belongs beside the anthems, and a keyword counter is an ability, so
it belongs beside the keyword grants.  The real layer system splits them the
same way -- 613.1f applies keyword counters with the ability-adding effects and
613.1d applies +1/+1 counters four layers later.

To make that safe there is one hard constraint, enforced by
:func:`automtg.cards.loader.check_static_constraints`:

    **A static ability's filter may not read another static ability's output.**

Static filters are therefore matched against *printed* characteristics (plus the
object's own board state: controller, tapped, attacking, counters).  That removes
all recursion and all dependency ordering, at the cost of not supporting cards
whose anthem depends on another anthem's result.  The curated decks respect this.

A static's "as long as…" `condition` obeys the same constraint from the other
side.  It is evaluated in :func:`_static_active`, which runs in
:func:`_battlefield_statics` -- *before* layer -1, so before any layer has
applied.  Everything it may read is therefore an **input** to the pipeline rather
than an output: printed characteristics, an object's own board state, counters,
whose turn it is, and how many cards sit in a zone.  No layer can change whether
another static is switched on, so the gate is computed once and the fixed order
stays acyclic.  That is the whole reason the condition language is a mirror of
:mod:`automtg.engine.effects.conditions` rather than that module itself: `if`'s
conditions go through the selector engine, which calls :func:`chars`.

The **player-wide** statics -- the ones that take `affects_player` and describe a
player rather than a characteristic -- are not read by this pipeline at all, and
they are gated by the same function anyway, through
:func:`_active_player_statics`.  They have to be: a `condition` the loader
validates and no reader ever asks is a card that loads clean, prints its "as long
as" clause and grants the permission unconditionally.  Running the gate outside
the pipeline is strictly safer than running it inside -- legality, payment,
serialization and the cleanup step have no layers for a condition to depend on.

Results are cached against ``state.char_version``, which every mutating primitive
bumps.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from .carddef import Ability, CardDef, ward_ability
from .enums import KEYWORD_COUNTERS, SUBTYPE_CLASS, Keyword, Zone
from .errors import DslError
from .objects import MINUS_ONE, PLUS_ONE, GameObject
from .structs import PROTECTION_EVERYTHING, Characteristics

#: What ``min_life_of`` reports when its player spec selects nobody.
#:
#: Not zero, and the direction matters. "An opponent has 10 or less life" with
#: no opponents left must be **false**, and a minimum of 0 would make it
#: vacuously true -- turning Vampire Lacerator's drawback off at the exact
#: moment the last opponent died. So the minimum over an empty set is a life
#: total nothing reaches. ``max_life_of`` has the opposite bias and uses a plain
#: 0, because "each opponent has 10 or less" over nobody *is* vacuously true and
#: that is the correct reading.
#:
#: It lives here rather than next to the rest of the value language because
#: ``effects/values.py`` already imports this module, and both languages need
#: the same answer.
NO_PLAYERS_LIFE = 1_000_000


def min_life(lives: list[int]) -> int:
    """The lowest of several life totals, biased away from vacuous truth."""
    return min(lives, default=NO_PLAYERS_LIFE)


#: What ``min_count_of`` reports when its player spec selects nobody.
#:
#: The same bias ``NO_PLAYERS_LIFE`` has, for the same reason and in the same
#: direction. ``min_count_of`` is the *universal* -- "each opponent controls more
#: lands than you" -- so over nobody it must read as unreachably large: a minimum
#: of 0 would say every opponent is ahead of you at the moment the last one died.
#: ``max_count_of`` is the existential and takes a plain 0, because "an opponent
#: controls more lands than you" over nobody is correctly false and no land count
#: of yours is below zero.
NO_PLAYERS_COUNT = 1_000_000


def min_count(counts: list[int]) -> int:
    """The lowest of several per-player counts, biased away from vacuous truth."""
    return min(counts, default=NO_PLAYERS_COUNT)

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def chars(state: GameState, oid: int) -> Characteristics:
    """Derived characteristics of an object, cached per ``char_version``."""
    if state.char_cache_version != state.char_version:
        state.char_cache = {}
        state.char_cache_version = state.char_version
    cached = state.char_cache.get(oid)
    if cached is not None:
        return cached
    result = _compute(state, oid)
    state.char_cache[oid] = result
    return result


#: What a face-down permanent is, whatever is underneath it (707.2).
FACE_DOWN_CHARS = Characteristics(
    power=2,
    toughness=2,
    types=frozenset({"Creature"}),
    subtypes=frozenset(),
    supertypes=frozenset(),
    keywords=frozenset(),
    colors=frozenset(),
)


def _compute(state: GameState, oid: int) -> Characteristics:
    obj = state.objects.get(oid)
    if obj is None:
        return Characteristics()
    if obj.face_down and obj.on_battlefield:
        # Rule 707.2: a face-down permanent is a 2/2 creature with no name, no
        # mana cost, no types beyond Creature, no subtypes and no abilities --
        # whatever card is underneath it.
        #
        # Returned *before* any layer, so nothing about the hidden card reaches
        # the pipeline. It is the one place in this module that does not build
        # on the printed face, and it has to be: `card_of` still answers with
        # the real card, because turning it face up has to find it again.
        #
        # Anthems and counters therefore do not apply either, which is a
        # documented simplification -- a real face-down creature is still
        # affected by them, and modelling that means layering over the shell
        # rather than replacing with it.
        return FACE_DOWN_CHARS
    card = state.card_of(obj)
    power = card.power or 0
    toughness = card.toughness or 0
    types = set(card.types)
    subtypes = set(card.subtypes)
    supertypes = set(card.supertypes)
    keywords = set(card.keywords)
    colors = set(card.colors)

    # "…a copy of it, except it's a white Zombie Angel with no mana cost."
    # Applied to the *printed* face, before any layer: the exception is part of
    # what this object is, not an effect on it, so an anthem or an animate
    # afterwards should layer on top exactly as it would on a printed card.
    if obj.copy_overrides:
        if (added := obj.copy_overrides.get("add_subtypes")):
            subtypes.update(added)
        if (repaint := obj.copy_overrides.get("colors")) is not None:
            colors = set(repaint)
        if (retyped := obj.copy_overrides.get("types")) is not None:
            # "…except it's an artifact and it **loses all other card types**."
            # A replacement, where `add_subtypes` above is an addition, and the
            # printed clause is what decides which: Espers to Magicite's token
            # is an Artifact and nothing else, so a union would leave it a
            # creature that could attack and die -- a strictly better card.
            #
            # Card types only. The subtypes are the copied card's and stay,
            # which is also what the printing says: it loses its card types and
            # is not told to lose its creature types.
            types = set(retyped)

    # Bestow (702.103b): "it's an Aura spell with enchant creature... it becomes
    # a creature again if it's not attached to a creature". Applied to the
    # printed face, before any layer, for `copy_overrides`' reason -- it is part
    # of what this permanent *is* while it is attached, not an effect on it, so
    # an anthem or an animate afterwards layers on top exactly as it would on a
    # printed Aura.
    #
    # `attached_to` is a field the `attach` primitive writes and no layer can
    # change, so switching on it is reading a pipeline **input**, which is the
    # same argument `is_attached` made for reconfigure. Nothing here can come to
    # depend on another static's output.
    #
    # The condition is the whole keyword: it stops being a creature when it is
    # attached and starts again the moment it is not, and `_detach_all` clearing
    # `attached_to` as the enchanted creature leaves is what makes that happen
    # with nothing to remember.
    if obj.cast_bestowed and obj.attached_to is not None and obj.on_battlefield:
        types.discard("Creature")
        types.add("Enchantment")
        subtypes.add("Aura")
        power = toughness = 0

    if obj.on_battlefield:
        statics = _battlefield_statics(state)

        # -1. animation -- "becomes a 4/4 creature until end of turn. It's still
        #     a land."  It runs *before* everything else because it replaces the
        #     printed base P/T rather than modifying it: put after the statics
        #     and it would erase an anthem, put after the counters and it would
        #     erase them too.  Here, everything below layers on top, which is
        #     what the real layer system does with a 7b effect.
        for temp in obj.until_eot:
            if temp.kind != "animate":
                continue
            types.update(temp.types)
            subtypes.update(temp.subtypes)
            colors.update(temp.colors)
            power = temp.power
            toughness = temp.toughness

        # 0. type replacement -- "as long as it has a slumber counter, it's a
        #    land (it's not a creature)". Before the grants, so a card that both
        #    replaces and adds ends up with the addition.
        #
        #    205.1b and 613.1d: the subtypes of a card type it no longer has go
        #    with it. Without that an Imprisoned in the Moon on a Goblin
        #    Warchief reads "Land -- Goblin", is still pumped by a Goblin
        #    anthem and still answers a Goblin fetch -- a permanent that is
        #    visibly a land and secretly still a Goblin. Applied inside this
        #    layer and before the `add_subtype` grants union on top, which
        #    preserves what that ordering already promises: a card that both
        #    replaces and adds ends up with the addition.
        for source_obj, static in statics:
            if static.get("effect") != "set_types":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                types = set(static.get("types", ()))
                subtypes = {
                    sub for sub in subtypes if SUBTYPE_CLASS.get(sub, "Creature") in types
                }

        # 0b. colour replacement -- "enchanted permanent is a **colorless**
        #     land". Real layer 5, and it sits here for the reason `set_types`
        #     does: it replaces rather than modifies, and nothing below reads
        #     colour, so this is simply where the replacement belongs relative
        #     to `animate` (which is above it, and whose `colors` it therefore
        #     overwrites -- an animated permanent that is then imprisoned is
        #     colourless, which is the later effect winning).
        #
        #     `colors` is not decoration once something can set it: the selector
        #     language reads `colors`, `not_colors` and `shares_a_color_with`,
        #     and `protection` reads `from_colors`. A moon-imprisoned Sheoldred
        #     stops being a legal target for "destroy target black permanent".
        for source_obj, static in statics:
            if static.get("effect") != "set_colors":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                colors = set(static.get("colors", ()))

        # 1. subtype / type grants.  The object's own recorded subtypes come
        #    first -- "it becomes a Vampire in addition to its other types" is
        #    written onto the permanent, so it is an input to this pipeline
        #    rather than a product of it, and a static's `add_subtype` layering
        #    on top of it is the ordinary case.
        subtypes.update(obj.added_subtypes)

        for source_obj, static in statics:
            if static.get("effect") != "add_subtype":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                subtypes.update(static.get("subtypes", ()))
                types.update(static.get("types", ()))

        # 1b. "…and loses all other card types and abilities." A keyword *is*
        #     an ability (113.1a), so losing them all takes the printed
        #     keywords with it -- an imprisoned Sheoldred that kept deathtouch
        #     would be the clearest possible half-implementation.
        #
        #     Placed before the grants below rather than after, which is
        #     613.1b's own ordering: what is added *after* the removal survives
        #     it. So an Imprisoned in the Moon plus a Levitation leaves the
        #     permanent flying, and a vigilance counter (layer 2b) still gives
        #     vigilance -- 613.1f puts keyword counters with the ability-adders,
        #     which is on this side of the line.
        #
        #     What it does **not** do is empty `obj.granted_keywords` (layer 8)
        #     or the until-end-of-turn grants (layer 6). Those are later
        #     timestamps by construction, and the same rule keeps them.
        if _loses_abilities(state, obj):
            keywords = set()

        # 2. keyword grants
        for source_obj, static in statics:
            if static.get("effect") != "grant_keyword":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                keywords.update(static.get("keywords", ()))

        # 2b. Keyword counters (122.1c): "a permanent with a keyword counter on
        #     it has that keyword ability".  A vigilance counter is not
        #     bookkeeping about a keyword, it *is* the keyword.
        #
        #     Here rather than beside the +1/+1 counters at layer 5, which is
        #     where the other half of "read the counters" lives. The real layer
        #     system makes the same split for the same reason -- 613.1f puts
        #     keyword counters with the ability-adding effects and 613.1d puts
        #     +1/+1 counters four layers later -- and it is what the two
        #     counters *do* that separates them: one is an ability and one is a
        #     size. Nothing here would break at layer 5, because keywords only
        #     ever accumulate into a set and no layer removes one, so the
        #     position is a statement about what this is rather than about what
        #     it would otherwise collide with. `animate` had to be first because
        #     it *replaces* base P/T; this replaces nothing.
        #
        #     Counters are a pipeline **input** -- no layer can place or remove
        #     one -- so reading them here cannot make a static depend on another
        #     static's output, which is the constraint the whole fixed order
        #     rests on.
        #
        #     What a static's *filter* sees is unchanged: `keywords: ["flying"]`
        #     in an `affects` still reads the printed face, so Favorable Winds
        #     does not pump a creature wearing a flying counter. That is not a
        #     hole this opens, it is the documented no-layers simplification
        #     applying to keyword counters exactly as it already applies to
        #     every `grant_keyword` -- a creature granted flying by Levitation
        #     is invisible to the same filter. Making counters the one visible
        #     kind of grant would be the inconsistency. Effect selectors
        #     (`selectors.matches`) read *derived* characteristics on the
        #     battlefield and so see them for free, which is the split that
        #     already existed.
        for kind, amount in obj.counters.items():
            if amount > 0 and kind in KEYWORD_COUNTERS:
                keywords.add(kind)

        # 3. P/T setting
        for source_obj, static in statics:
            if static.get("effect") != "set_pt":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                power = _static_value(state, static.get("power"), source_obj)
                toughness = _static_value(state, static.get("toughness"), source_obj)

        # 4. P/T modification (anthems)
        for source_obj, static in statics:
            if static.get("effect") != "buff":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                power += _static_value(state, static.get("power"), source_obj)
                toughness += _static_value(state, static.get("toughness"), source_obj)

        # 5. +1/+1 and -1/-1 counters -- the *size* half of reading the
        #    counters. The ability half is layer 2b, and the two are apart on
        #    purpose; see the note there.
        plus = obj.counter(PLUS_ONE)
        minus = obj.counter(MINUS_ONE)
        power += plus - minus
        toughness += plus - minus

        # 6. until end of turn
        for temp in obj.until_eot:
            if temp.kind == "pump":
                power += temp.power
                toughness += temp.toughness
            elif temp.kind == "keyword" and temp.keyword:
                keywords.add(temp.keyword)

        # 7. haste from suspend, which is *not* an until-end-of-turn effect: it
        #    lasts as long as the permanent does. Without it a suspended creature
        #    arrives summoning sick and suspend is never worth doing.
        if obj.hasted_by_suspend:
            keywords.add(Keyword.HASTE.value)

        # 8. Keywords granted for as long as the permanent lasts -- riot's "or
        #    with haste", which is not a pump that wears off but part of what
        #    the creature is from the moment it arrives. `hasted_by_suspend`
        #    above is the same idea for one specific keyword; this is the
        #    general form, and the two stay separate because suspend's is set
        #    while the card is still in exile.
        keywords.update(obj.granted_keywords)

    return Characteristics(
        power=power,
        toughness=toughness,
        types=frozenset(types),
        subtypes=frozenset(subtypes),
        supertypes=frozenset(supertypes),
        keywords=frozenset(keywords),
        colors=frozenset(colors),
    )


#: The two static effects that change *which abilities* a permanent has.
#:
#: Collected apart from every other static, off the **printed** face, and that
#: separation is what keeps the pipeline acyclic: `_battlefield_statics` reads
#: `abilities_of`, and `abilities_of` reads these -- so if these were gathered
#: the same way the two would call each other for ever.
#:
#: The cost is one recorded divergence from 613.8: an Imprisoned in the Moon
#: enchanting *another* Imprisoned in the Moon does not switch the second one
#: off. Real Magic resolves that with dependency analysis, which is the thing
#: layers-lite exists not to have.
ABILITY_STATICS = ("lose_all_abilities", "grant_ability")


def _ability_statics(state: GameState) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """The `ABILITY_STATICS` on the battlefield, read off printed faces.

    Cached against ``char_version`` like `chars` is, and that is not an
    optimisation to be tidied away later. `_battlefield_statics` asks
    `abilities_of` about every permanent and `abilities_of` asks this, so an
    uncached scan makes one characteristics computation quadratic in the size of
    the battlefield and the whole pipeline cubic -- which on a real Commander
    board is the difference between a test suite that runs and one that does
    not. Almost every game has no such static at all, and then this is one walk
    per version that finds nothing.
    """
    if state.ability_static_version != state.char_version:
        out: list[tuple[GameObject, Mapping[str, Any]]] = []
        for oid in state.battlefield:
            obj = state.objects.get(oid)
            if obj is None:
                continue
            for ability in state.card_of(obj).abilities:
                static = ability.static if ability.is_static else None
                if not static or static.get("effect") not in ABILITY_STATICS:
                    continue
                if _static_active(state, obj, static):
                    out.append((obj, static))
        state.ability_static_cache = out
        state.ability_static_version = state.char_version
    return state.ability_static_cache


def _loses_abilities(state: GameState, obj: GameObject) -> bool:
    """Is something stripping every ability from this permanent right now?"""
    if not obj.on_battlefield:
        return False
    return any(
        static.get("effect") == "lose_all_abilities"
        and _matches(state, obj, source_obj, static.get("affects"))
        for source_obj, static in _ability_statics(state)
    )


def abilities_of(state: GameState, oid: int) -> tuple[Ability, ...]:
    """The abilities a permanent **actually has**, printed ones included.

    The engine had no such notion: every reader -- `legality`, `costs`,
    `triggers`, `_battlefield_statics`, `game._activate` -- walked
    ``state.card_of(obj).abilities`` and got the printed list. That is fine
    until a card says "loses all abilities", at which point each of those
    readers is a separate place for the clause to be forgotten, and forgetting
    it in any one of them is a permanent that visibly does nothing and quietly
    still does something.

    So this is the one function that answers the question, and every one of
    those readers now asks it. Off the battlefield it is the printed list
    unchanged, which is every card in hand, on the stack and in a graveyard.

    **Indices are stable and meaningful.** `Action.ability_index`,
    `StackItem.ability_index` and the RL action space all address an ability by
    position, so a granted ability is *appended* -- printed indices never move
    -- and the abilities are renumbered so `Ability.index` agrees with where it
    now sits. Legality and resolution both read this list, so the two cannot
    disagree about what index 0 means.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return ()
    if obj.face_down and obj.on_battlefield:
        # 707.2, and the same early return `_compute` makes: a face-down
        # permanent is a 2/2 with no abilities, whatever is underneath it.
        return ()
    printed = state.card_of(obj).abilities
    if not obj.on_battlefield:
        return printed
    statics = _ability_statics(state)
    if not statics:
        return printed
    out = [ability for ability, _origin in _derived_abilities(state, obj, statics)]
    if out == list(printed):
        return printed
    import dataclasses

    return tuple(
        dataclasses.replace(ability, index=i) for i, ability in enumerate(out)
    )


def _derived_abilities(
    state: GameState, obj: GameObject, statics: list[tuple[GameObject, Mapping[str, Any]]]
) -> list[tuple[Ability, tuple[int, int] | None]]:
    """Every ability this permanent has, each with **where it came from**.

    ``None`` for a printed one; ``(granter oid, index into that card's
    ``grantable_abilities``)`` for one a static handed over. The provenance is
    not decoration: a granted ability does not live on the card of the permanent
    that has it, so `stack.ability_of` looks it up in the granter's pool, and
    the two index spaces are different -- Tandem Lookout's granted trigger sits
    at position 2 on the creature that has it and at position 0 in the pool it
    came from. Resolving the recipient's position against the granter's pool
    reads whatever happens to be there, which is another ability or nothing at
    all.

    Shared with `abilities_of` above rather than walked twice, because the two
    answers have to agree about which ability is at which position.
    """
    printed = state.card_of(obj).abilities
    out: list[tuple[Ability, tuple[int, int] | None]] = []
    if not any(
        static.get("effect") == "lose_all_abilities"
        and _matches(state, obj, source_obj, static.get("affects"))
        for source_obj, static in statics
    ):
        out.extend((ability, None) for ability in printed)
    for source_obj, static in statics:
        if static.get("effect") != "grant_ability":
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        granted = state.card_of(source_obj).grantable_abilities
        index = int(static.get("ability", 0))
        if 0 <= index < len(granted):
            out.append((granted[index], (source_obj.oid, index)))
    return out


def granted_ability_origin(state: GameState, oid: int, index: int) -> tuple[int, int] | None:
    """Who granted the ability now sitting at ``index``, and where it lives.

    ``(granter oid, index into that granter's ``grantable_abilities``)``, or
    ``None`` when the position holds an ordinary printed ability.

    The continuous counterpart of `primitives.granted_abilities`, which answers
    the same question for the one-shot `grant_ability` **op** and cannot answer
    it here: that one reads `TempEffect`s off the recipient, and a static grant
    leaves nothing on the recipient to read -- it is recomputed from the
    granter's "as long as…" every time anybody asks. Without this a statically
    granted *triggered* ability queued and then resolved as nothing at all,
    silently, because resolution could not find its definition.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return None
    if obj.face_down:
        return None
    statics = _ability_statics(state)
    if not statics:
        return None
    derived = _derived_abilities(state, obj, statics)
    if 0 <= index < len(derived):
        return derived[index][1]
    return None


def _battlefield_statics(state: GameState) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """Every *active* ``static`` ability on the battlefield, in arrival order.

    Reads `abilities_of` rather than the printed face, so a permanent that has
    lost its abilities stops applying its anthem -- which is the half of "loses
    all abilities" that no amount of work at the offer sites would have caught.

    It is also where a **granted static** joins the pipeline, and there is no
    code here for it: `abilities_of` appends the granted ability to the
    *recipient's* list, so this walk finds it with ``obj`` -- the recipient --
    as its source, and every layer below reads it as an ordinary static of that
    permanent. That is the whole of Inspiring Leader's "Commander creatures you
    own have "Creature tokens you control get +2/+2."": the quoted anthem's
    "you" is the commander creature's controller because the commander creature
    is what the pipeline thinks said it, and two commander creatures put two
    entries in this list, so the tokens get +4/+4 without anything counting.

    **Why that cannot break the fixed order.** Three facts, and the argument
    needs all three:

    1. *Who receives* a granted static is decided by `_ability_statics` plus
       `_matches` on the granter's `affects` -- printed characteristics and
       board state, never a layer's output.
    2. *What it affects* is decided by `_matches` too, and by the same rule.
    3. `_ability_statics` collects **only** off printed faces, so a granted
       `grant_ability` or `lose_all_abilities` is never collected at all. That
       severed edge -- already there, and already paid for as the one recorded
       divergence from 613.8 -- is what stops static-grants-static recursion,
       and `loader.vocabulary.GRANTABLE_STATIC_EFFECTS` refuses the two by name rather
       than letting a card load clean and do nothing.

    So the only thing a grant changes is *which permanent a static is sourced
    on*, which is what `controller: "you"` and `self_only` are measured against.
    The layer order is over effect *kinds* -- a granted `buff` is applied at
    layer 4 beside every printed one -- so it is untouched.
    """
    out: list[tuple[GameObject, Mapping[str, Any]]] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        for ability in abilities_of(state, oid):
            if not (ability.is_static and ability.static):
                continue
            if Zone.BATTLEFIELD not in ability.active_zones:
                # A graveyard-only static on a permanent that has somehow
                # reached the battlefield -- Anger itself, as a 2/2. It is not
                # active here, and letting it through is precisely the inverse
                # of the printed card.
                continue
            if _static_active(state, obj, ability.static):
                out.append((obj, ability.static))
    out.extend(_graveyard_statics(state))
    return out


def _graveyard_statics(state: GameState) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """Statics that work from a graveyard -- Anger, and the Incarnation cycle.

    "As long as this card is in your graveyard and you control a Mountain,
    creatures you control have haste." The zone half of that sentence is *this
    function*: an ability is collected only while its card sits in a graveyard,
    so the clause needs no condition of its own.

    Read off the **printed** face rather than through `abilities_of`, which
    resolves granted and lost abilities against the battlefield and has nothing
    to say about a card in a graveyard. Nothing grants an ability to a card in a
    graveyard, so there is no case being missed.

    Appended after the battlefield walk rather than interleaved, because the
    order of this list is the order effects apply in and a graveyard card has no
    battlefield timestamp to sort against.
    """
    out: list[tuple[GameObject, Mapping[str, Any]]] = []
    for player in state.players:
        for oid in player.graveyard:
            obj = state.objects.get(oid)
            if obj is None:
                continue
            for ability in state.card_of(obj).abilities:
                if not (ability.is_static and ability.static):
                    continue
                if Zone.GRAVEYARD not in ability.active_zones:
                    continue
                if _static_active(state, obj, ability.static):
                    out.append((obj, ability.static))
    return out


#: The comparisons a static's condition may use.  Mirrors the loader's copy.
_COMPARISONS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "=": lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _static_active(state: GameState, source: GameObject, static: Mapping[str, Any]) -> bool:
    """Is this static's "as long as..." clause currently true?"""
    condition = static.get("condition")
    if not condition:
        return True
    return _condition_met(state, source, condition)


def _condition_met(state: GameState, source: GameObject, cond: Any) -> bool:
    """Evaluate a static's condition tree.

    A deliberately smaller language than :func:`automtg.engine.effects.conditions.evaluate`
    -- see the module docstring.  Every leaf here reads a pipeline *input*, so
    nothing it can ask depends on a static's output:

    ``counters``      how many counters of a kind sit on the static's own source
    ``exists``/``cmp`` over ``{"count": filter}``, matched on printed
                      characteristics and, off the battlefield, on zone contents
    ``is_your_turn``  whose turn it is
    """
    if isinstance(cond, bool):
        return cond
    if not isinstance(cond, Mapping):
        raise DslError(f"unparsable static condition {cond!r}")

    if "counters" in cond:
        spec = cond["counters"] or {}
        have = source.counter(str(spec.get("counter", PLUS_ONE)))
        return _compare(str(spec.get("op", ">=")), have, int(spec.get("amount", 1)))
    if "all" in cond:
        return all(_condition_met(state, source, c) for c in cond["all"])
    if "any" in cond:
        return any(_condition_met(state, source, c) for c in cond["any"])
    if "not" in cond:
        return not _condition_met(state, source, cond["not"])
    if "exists" in cond:
        return _count_matching(state, cond["exists"], source) > 0
    if "is_your_turn" in cond:
        return (state.active_player == source.controller) == bool(cond["is_your_turn"])
    if "is_attached" in cond:
        # "Attached permanents with reconfigure aren't creatures" (702.151d) --
        # a `set_types` static switched by this. `GameObject.attached_to` is a
        # field written by the `attach` primitive, so it is a pipeline *input*
        # exactly as counters are: no layer can change it, and no static can
        # come to depend on another static's output through it.
        #
        # Not the `{"attached": true}` filter key, which is the opposite
        # direction -- that names the permanent this one is attached *to*, and
        # is how "equipped creature gets +1/+1" is written.
        #
        # Either host counts. An Aura enchanting a **player** is attached
        # (303.4a), and both fields are pipeline inputs on the same terms, so
        # reading only the object one would answer "no" for a permanent the
        # rules and the state-based actions both call attached.
        attached = source.attached_to is not None or source.attached_to_player is not None
        return attached == bool(cond["is_attached"])
    if "has_city_s_blessing" in cond:
        # Player state, so a pipeline *input* exactly as a zone count is:
        # nothing in the fixed-order characteristics pipeline can change whether
        # a player has the blessing, so no static can come to depend on another
        # static's output through it.
        pids = _static_players(state, source, cond["has_city_s_blessing"])
        return any(state.players[p].has_city_s_blessing for p in pids)
    if "top_of_library" in cond:
        # "As long as the top card of your library is black." A pipeline input
        # exactly as a zone count is -- nothing in the fixed-order pipeline can
        # change what is on top of a library -- and a sharper question than
        # `exists` over the library, which asks whether *any* black card is
        # anywhere in ninety-nine and is nearly always true.
        spec = cond["top_of_library"] or {}
        for pid in _static_players(state, source, spec.get("controller", "you")):
            top = top_of_library(state, pid)
            if top is not None and _matches_printed(state.card_of(top), spec):
                return True
        return False
    if "cmp" in cond:
        left = _static_value(state, cond.get("left"), source)
        right = _static_value(state, cond.get("right"), source)
        return _compare(str(cond["cmp"]), left, right)

    raise DslError(f"unknown static condition {sorted(cond)}")


def _compare(op: str, left: int, right: int) -> bool:
    try:
        return _COMPARISONS[op](left, right)
    except KeyError:
        raise DslError(f"unknown comparison operator {op!r}") from None


def _static_value(state: GameState, expr: Any, source: GameObject) -> int:
    """Evaluate the restricted value language allowed inside static abilities.

    ``{"const": n}``, ``{"count": <filter>}`` and the per-player life and count
    leaves are permitted here -- the full value language would need the selector
    engine, which needs derived characteristics, which would reintroduce
    recursion.

    A life total is safe for the same reason a zone count is: it is a *pipeline
    input*. Nothing in the fixed-order characteristics pipeline can change what
    a player's life is, so reading one cannot make a static depend on another
    static's output.

    Vocabulary this does not know is a :class:`DslError`, not a 0. A static's
    magnitude that silently reads 0 is an anthem that loads clean, prints as the
    card does and does nothing -- the exact failure the whole validation pass
    exists to refuse -- and every expression reaching here has been through
    :func:`automtg.cards.loader.statics._validate_static_value`, so an unknown leaf means
    the two languages have drifted and the loader is the thing to fix. ``None``
    is still 0, because a `buff` with no `toughness` is a real card.
    """
    if expr is None:
        return 0
    if isinstance(expr, int):
        return expr
    if not isinstance(expr, Mapping):
        raise DslError(f"unparsable static value {expr!r}")
    if "const" in expr:
        return int(expr["const"])
    if "count" in expr:
        return _count_matching(state, expr["count"], source)
    if "mana_symbols" in expr:
        # Chroma -- Primalcrux's "power and toughness are each equal to the
        # number of green mana symbols in the mana costs of permanents you
        # control". A *printed* mana cost is a pipeline input like a zone count,
        # so reading it here cannot make one static depend on another's output.
        spec = expr["mana_symbols"]
        color = str(spec.get("of", ""))
        return sum(
            state.card_of(obj).mana_cost.symbols_of(color)
            for obj in _matching_objects(state, spec.get("objects") or {}, source)
        )
    if "min_life_of" in expr:
        pids = _static_players(state, source, expr["min_life_of"])
        return min_life([state.players[p].life for p in pids])
    if "max_life_of" in expr:
        pids = _static_players(state, source, expr["max_life_of"])
        return max([state.players[p].life for p in pids], default=0)
    if "max_count_of" in expr:
        # "As long as an opponent controls more lands than you." A count per
        # player rather than over the merged pool -- `count` with
        # `controller: "opponent"` is the *sum*, which crosses your land total at
        # a pod long before any single opponent does.
        #
        # Safe inside a static for the same reason `count` is: it reads printed
        # characteristics and board state, both pipeline inputs, so no layer can
        # change the answer and the fixed order stays acyclic.
        return max(_counts_per_player(state, expr["max_count_of"], source), default=0)
    if "min_count_of" in expr:
        return min_count(_counts_per_player(state, expr["min_count_of"], source))
    if "permanents_entered_this_turn" in expr:
        # Kinbinding: "Creatures you control get +X/+X, where X is the number of
        # creatures that entered the battlefield under your control this turn."
        #
        # Safe here for the reason `counters_on` is, one step further removed:
        # an `EnteredPermanent` is a snapshot the ledger wrote *once*, when the
        # permanent arrived, and no layer of this pipeline can write to it. So
        # the magnitude reads a pipeline input and the fixed order stays acyclic.
        #
        # The recomputation story is the same too -- `chars` is cached against
        # `state.char_version`, which the enters path bumps -- so the anthem
        # grows the moment a creature lands and, unlike a board count, does not
        # shrink again when it dies. That asymmetry *is* the printed card.
        spec = expr["permanents_entered_this_turn"]
        controllers = _static_players(state, source, spec.get("controller"))
        excluded = source.oid if spec.get("exclude_self") else None
        return sum(
            1
            for entry in state.turn_ledger.permanents_entered
            if entry.oid != excluded
            and entry.matches(
                controllers=controllers,
                types=spec.get("types") or (),
                subtypes=spec.get("subtypes") or (),
                colors=spec.get("colors") or (),
            )
        )
    if "counters_on" in expr:
        # "Creatures you control of the chosen type get +1/+1 for each charge
        # counter on this artifact" -- Door of Destinies. The `counters`
        # *condition* head has read the same number since Arixmethes, but as a
        # threshold: it can switch a fixed anthem on and off and never size one.
        #
        # Safe here for the reason that head is safe. A counter is a pipeline
        # **input** -- primitives place and remove them, no layer can -- so an
        # anthem's magnitude reading one cannot come to depend on another
        # static's output, and the fixed order stays acyclic. The pool is walked
        # with the same printed-characteristics filter `count` uses, which is an
        # input too.
        #
        # The magnitude is recomputed like every other static value: `chars` is
        # cached against `state.char_version`, which `add_counters` bumps, so
        # the anthem grows the instant the counter lands and shrinks again when
        # it leaves.
        spec = expr["counters_on"] or {}
        kind = str(spec.get("counter", PLUS_ONE))
        return sum(
            obj.counter(kind)
            for obj in _matching_objects(
                state, spec.get("objects") or {"self_only": True}, source
            )
        )
    raise DslError(f"unknown static value {sorted(expr)}")


def _counts_per_player(
    state: GameState, spec: Mapping[str, Any], source: GameObject
) -> list[int]:
    """How many objects a static's filter matches, once per named player.

    The static-side twin of ``values._counts_per_player``, and it splits the two
    zone families the same way for the same reason: the battlefield is shared, so
    a player is a filter over it, while a hand or a graveyard belongs to somebody
    and a player chooses whose list to walk.

    The pool is scoped here rather than by a ``controller`` clause on the filter,
    because that clause has only three words -- and "not you" is the pooled
    question this leaf exists to take apart.
    """
    objects = spec.get("objects") or {}
    zone = str(objects.get("zone", Zone.BATTLEFIELD.value))
    counts: list[int] = []
    for pid in _static_players(state, source, spec.get("player")):
        if zone == Zone.BATTLEFIELD.value:
            counts.append(
                sum(
                    1
                    for oid in state.battlefield
                    if (obj := state.objects.get(oid)) is not None
                    and obj.controller == pid
                    # `"any"`, so `_matches` applies no controller clause of its
                    # own on top of the scoping already done here.
                    and _matches(state, obj, source, {**objects, "controller": "any"})
                )
            )
            continue
        counts.append(
            sum(
                1
                for oid in state.players[pid].zone_list(Zone(zone))
                if (obj := state.objects.get(oid)) is not None
                and _matches_printed(state.card_of(obj), objects)
            )
        )
    return counts


def _count_matching(state: GameState, selector: Mapping[str, Any], source: GameObject) -> int:
    """How many objects a static's *counting* filter matches.

    Two paths, because a filter that names a zone other than the battlefield is
    asking a different question.  On the battlefield it is a filter over
    permanents and reads their board state as well as their printed face; in a
    graveyard, hand, exile, library or command zone there is no board state to
    read, so it is the printed face alone.  The loader refuses the board-state
    keys on the second path rather than letting them load and match nothing.
    """
    return sum(1 for _ in _matching_objects(state, selector, source))


def _matching_objects(
    state: GameState, selector: Mapping[str, Any], source: GameObject
) -> Iterator[GameObject]:
    """The objects a static's counting filter matches.

    Split out of :func:`_count_matching` when chroma arrived: `mana_symbols`
    wants to *sum something over* the same pool rather than measure it, and two
    copies of this walk would be two places for the two zone paths to drift.
    """
    zone = str(selector.get("zone", "battlefield"))
    if zone == Zone.BATTLEFIELD.value:
        for oid in state.battlefield:
            obj = state.objects.get(oid)
            if obj is not None and _matches(state, obj, source, selector):
                yield obj
        return

    for pid in _static_players(state, source, selector.get("controller", "you")):
        for oid in state.players[pid].zone_list(Zone(zone)):
            obj = state.objects.get(oid)
            if obj is not None and _matches_printed(state.card_of(obj), selector):
                yield obj


def top_of_library(state: GameState, pid: int) -> GameObject | None:
    """The card on top of a player's library, or None for an empty one.

    Index 0 is the top -- `draw_cards` and `mill_cards` both take from there,
    so this reads the same end they do and cannot drift from them.
    """
    library = state.players[pid].library
    return state.objects.get(library[0]) if library else None


def _static_players(state: GameState, source: GameObject, spec: Any) -> list[int]:
    """Whose zones a static's counting filter reaches.

    "Your graveyard" is the source's controller, not its owner: a stolen
    Nimble Mongoose counts the graveyard of whoever controls it, which is what
    "your" means on a permanent.
    """
    who = str(spec or "you")
    if who == "you":
        return [source.controller]
    # "opponent" and "each_opponent" are the same set, as they are in the
    # effect-side `select_players`. Spelling only one of them here meant
    # "each_opponent" fell through to *every* player including yourself.
    if who in ("opponent", "each_opponent"):
        return state.opponents(source.controller)
    return state.alive()


def resolve_chosen_subtypes(
    selector: Mapping[str, Any], source: GameObject | None
) -> Mapping[str, Any]:
    """Turn ``[{"chosen_type_of": "self"}]`` into the type that was chosen.

    Vanquisher's Banner's anthem and its draw trigger both say "of the chosen
    type", and a filter is a plain list of literal names everywhere else. This
    is the one substitution, done wherever a filter is about to be matched
    rather than at load time -- the choice does not exist until the permanent is
    on the battlefield.

    A source that has chosen nothing yet matches **nothing**, which is right: an
    anthem for "the chosen type" before a type is chosen should pump nobody, not
    everybody.
    """
    wanted = selector.get("subtypes")
    if not wanted or not any(isinstance(s, Mapping) for s in wanted):
        return selector
    out: list[str] = []
    for entry in wanted:
        if not isinstance(entry, Mapping):
            out.append(entry)
            continue
        if entry.get("chosen_type_of") == "self":
            chosen = source.chosen_type if source is not None else None
            if chosen is None:
                return {**selector, "subtypes": ["\0none"]}
            out.append(chosen)
    return {**selector, "subtypes": out}


def resolve_chosen_color_list(entries: Any, source: GameObject | None) -> list[str]:
    """Literal colour letters, with ``{"chosen_color_of": "self"}`` substituted.

    The leaf-level half of :func:`resolve_chosen_colors`, split out because two
    readers want the plain list and not a selector: ``op_add_mana``, which turns
    it into a production string, and ``op_grant_protection``, whose
    ``from_colors`` is a list of qualities rather than a filter.

    A source that has chosen nothing yet contributes **nothing** -- the entry is
    dropped, so "protection from the chosen color" before a colour is named is
    protection from nothing. The selector wrapper turns that emptiness into a
    match-nothing sentinel instead, because an empty ``colors`` key in a filter
    means "no colour test" and would match everything.
    """
    out: list[str] = []
    for entry in entries or ():
        if not isinstance(entry, Mapping):
            out.append(entry)
            continue
        if entry.get("chosen_color_of") != "self":
            continue
        chosen = source.chosen_color if source is not None else None
        if chosen is not None:
            out.append(chosen)
    return out


def resolve_chosen_colors(
    selector: Mapping[str, Any], source: GameObject | None
) -> Mapping[str, Any]:
    """Turn ``[{"chosen_color_of": "self"}]`` into the colour that was chosen.

    The exact counterpart of :func:`resolve_chosen_subtypes`, one key over.
    Heraldic Banner's "creatures you control **of the chosen color** get +1/+0"
    is a static filter whose ``colors`` is a plain list of literal letters
    everywhere else, so the substitution happens wherever a filter is about to
    be matched rather than at load time -- the choice does not exist until the
    permanent is on the battlefield.

    Kept as a second function rather than folded into its subtype twin so that
    the four callers of that one keep their name honest, and because the two
    substitutions are independent: a card may name a type, a colour, or both.

    A source that has chosen nothing yet matches **nothing**, which is right for
    the same reason it is right there: an anthem for "the chosen color" before a
    colour is chosen should pump nobody, not everybody.
    """
    wanted = selector.get("colors")
    if not wanted or not any(isinstance(c, Mapping) for c in wanted):
        return selector
    out = resolve_chosen_color_list(wanted, source)
    return {**selector, "colors": out or ["\0none"]}


def _matches_printed(
    card: CardDef, selector: Mapping[str, Any], added_subtypes: tuple[str, ...] = ()
) -> bool:
    """The half of a static filter that reads the printed card face.

    Split out so the two counting paths cannot drift: a permanent on the
    battlefield is matched on this *plus* its board state, and a card in a
    graveyard or hand -- which has no board state -- on this alone.

    ``added_subtypes`` is the one non-printed thing allowed in, and only on the
    battlefield path.  "It becomes a Vampire in addition to its other types" is
    recorded on the object, so it is a pipeline *input* exactly as a counter or
    a tapped flag is -- reading it cannot make one static depend on another's
    output.  Without it, Captivating Vampire's own anthem would not see the
    creature it had just converted, which is most of the card.
    """
    types = selector.get("types")
    if types and not set(types).issubset(card.types):
        return False
    not_types = selector.get("not_types")
    if not_types and set(not_types) & card.types:
        return False
    subtypes = selector.get("subtypes")
    if subtypes and not (set(subtypes) & (card.subtypes | set(added_subtypes))):
        return False
    supertypes = selector.get("supertypes")
    if supertypes and not set(supertypes).issubset(card.supertypes):
        return False
    colors = selector.get("colors")
    if colors and not (set(colors) & card.colors):
        return False
    keywords = selector.get("keywords")
    if keywords and not set(keywords).issubset(card.keywords):
        return False
    not_keywords = selector.get("not_keywords")
    if not_keywords and set(not_keywords) & card.keywords:
        return False
    # "…unless you control a creature named Advocate of the Beast." A name is
    # the most printed characteristic there is and nothing in the pipeline can
    # change one, so it is safe here for the same reason `types` is. Allowed
    # only in a *counting* filter, never in `affects`: "each creature named X
    # gets +1/+1" is not a card, and the name test belongs in the condition.
    name = selector.get("name")
    if name is not None and card.name != name:
        return False
    return True


def _matches(
    state: GameState,
    obj: GameObject,
    source: GameObject,
    selector: Mapping[str, Any] | None,
) -> bool:
    """Match ``obj`` against a static ability's filter, using printed characteristics.

    A deliberately smaller language than the full selector DSL in
    :mod:`automtg.engine.effects.selectors` -- see the module docstring for why.
    """
    if selector is None:
        return False
    if not obj.on_battlefield:
        return False
    selector = resolve_chosen_colors(resolve_chosen_subtypes(selector, source), source)
    card = state.card_of(obj)

    if selector.get("exclude_self") and obj.oid == source.oid:
        return False
    if selector.get("self_only") and obj.oid != source.oid:
        return False

    # "Enchanted creature gets +2/+2", "Equipped creature has flying".  Checked
    # before `controller`, and short-circuits it: an Aura stapled to an
    # opponent's creature still buffs (or shrinks) that creature, and the default
    # `controller: "you"` would quietly stop it.
    if selector.get("attached"):
        return obj.oid == source.attached_to
    # Soulbond. Two keys because the printed line applies to two creatures and
    # the static is written once: `paired` is "this creature, while it has a
    # partner" and `paired_with_source` is "the partner". Both short-circuit
    # `controller` the way `attached` does -- a pair is a pair whoever ends up
    # controlling either half.
    if selector.get("paired"):
        return obj.oid == source.oid and source.paired_with is not None
    if selector.get("paired_with_source"):
        return source.paired_with is not None and obj.oid == source.paired_with

    # "Commander creatures you **own**." Ownership is board state that no layer
    # can change -- `GameObject.owner` is written once, when the object is made,
    # and `change_control` deliberately leaves it alone -- so it is a pipeline
    # *input* exactly as `controller` and `tapped` are, and reading it here
    # cannot make one static depend on another's output.
    #
    # `owner` present suppresses the default `controller: "you"`, which is the
    # reading `costs._reduction_matches` already takes for the same word: a
    # filter that named ownership and not control is asking the other question,
    # and a defaulted control clause on top of it would silently re-impose the
    # answer the card went out of its way not to ask for -- dropping exactly the
    # case `owner` exists for, a commander an opponent has stolen. 903.3 is why
    # that case is not a curiosity: on a commander card, ownership *is* the
    # relation the rules use, and "you own" and "you control" part company on
    # precisely the boards commanders are played on.
    #
    # "You" is the source's **controller**, not its owner, which is what
    # `_static_players` already decided the word means on a permanent: a stolen
    # anthem pumps for whoever is holding it.
    owner = selector.get("owner")
    controller = selector.get("controller", None if owner else "you")
    if controller == "you" and obj.controller != source.controller:
        return False
    if controller == "opponent" and obj.controller == source.controller:
        return False
    # "Creatures **enchanted player** controls…" -- an Aura on a seat (303.4a),
    # read off its own link. Answered here rather than left to fall through,
    # because an unrecognised controller word matches *everything*: a static
    # naming one player would be a static naming the table, and nothing on the
    # board would say so. `None` -- an Aura on a permanent, or on nobody --
    # matches no permanent, since no seat has that id.
    if controller == "enchanted_player" and obj.controller != source.attached_to_player:
        return False
    if owner == "you" and obj.owner != source.controller:
        return False
    if owner == "opponent" and obj.owner == source.controller:
        return False

    if not _matches_printed(card, selector, obj.added_subtypes):
        return False

    if "tapped" in selector and bool(obj.tapped) != bool(selector["tapped"]):
        return False
    if "is_commander" in selector and bool(obj.is_commander) != bool(selector["is_commander"]):
        return False
    if "is_token" in selector and bool(obj.is_token) != bool(selector["is_token"]):
        return False

    combat = state.combat
    if "attacking" in selector:
        attacking = bool(combat and combat.attacking(obj.oid))
        if attacking != bool(selector["attacking"]):
            return False
    if "blocking" in selector:
        blocking = bool(combat and combat.blocking(obj.oid))
        if blocking != bool(selector["blocking"]):
            return False

    return True


# ----------------------------------------------------------------------
# convenience predicates used throughout the engine
# ----------------------------------------------------------------------


def is_creature(state: GameState, oid: int) -> bool:
    return "Creature" in chars(state, oid).types


def is_land(state: GameState, oid: int) -> bool:
    return "Land" in chars(state, oid).types


def has_keyword(state: GameState, oid: int, keyword: str) -> bool:
    return keyword in chars(state, oid).keywords


def prevented_damage(state: GameState, oid: int) -> int:
    """How much damage from **each source** this permanent prevents -- absorb.

    Per source and per instance, which is what 702.63a says and is the whole of
    why absorb 1 is playable at all: a creature with absorb 1 blocked by three
    1/1s takes nothing from any of them, and the same creature hit by one 3/3
    takes two. Summed over every applicable static, so two Absorb auras stack.

    Not protection with a number. Protection prevents *all* the damage and three
    other things besides -- it also stops the creature being blocked, enchanted
    and targeted -- so reusing it would make an absorb creature unblockable.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return 0
    total = 0
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "prevent_damage":
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        total += _static_value(state, static.get("amount"), source_obj)
    return total


def protection_from(state: GameState, oid: int) -> frozenset[str]:
    """The qualities this permanent has protection from.

    Protection is parameterised -- "from Wizards", "from black", "from
    planeswalkers" -- so it cannot be a `Keyword`, which is a bare string.  It is
    a static whose `from_types`/`from_subtypes`/`from_colors` name the qualities,
    and this returns them flattened into one set of strings to test a source
    against.

    Four rules read it (damage, enchant/equip, block, target).  Returning a set
    rather than answering a question keeps all four asking it the same way.
    """
    if not state.objects.get(oid) or not state.objects[oid].on_battlefield:
        return frozenset()
    out: set[str] = set()
    obj = state.objects[oid]
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "protection":
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        out.update(static.get("from_types", ()))
        out.update(static.get("from_subtypes", ()))
        out.update(static.get("from_colors", ()))
    # "Creatures you control gain protection from each color until end of turn"
    # -- Akroma's Will. Granted protection is one `TempEffect` per quality, so it
    # joins the printed statics' qualities in the same flat set, and the four
    # rules that read this -- damage, enchant/equip, block, target -- all see it
    # without knowing where it came from.
    out.update(
        str(temp.keyword)
        for temp in obj.until_eot
        if temp.kind == "protection" and temp.keyword
    )
    return frozenset(out)


def granted_wards(state: GameState) -> dict[int, tuple[Ability, ...]]:
    """Which permanents have ward right now, and the ward abilities they have.

    "Each other Human you control gets +1/+0 and **has ward {1}**." A `ward`
    static hands out a *triggered ability*, so unlike every other continuous
    effect here its product is not a characteristic value -- and that is what
    decides where it sits.

    **It has no place in the fixed order of `_compute`, and giving it one would
    be a claim about a dependency that does not exist.** The order exists because
    those layers feed each other: `animate` replaces the base P/T an anthem then
    adds to, `add_subtype` decides which creatures the next anthem's filter can
    even see. Ward reads none of them (its `affects` is matched on printed
    characteristics like every static) and none of them reads it, so it joins
    `protection_from`, `prevent_damage`, `block_restrictions` and
    `attack_forbidden` -- the statics whose output some *other* rule asks for,
    read off the battlefield at the moment that rule runs. Real Magic agrees:
    ward is an ability-adding effect (613.1f, where this module already puts
    keyword counters), and layer position only matters between effects that can
    collide. Nothing collides with a trigger.

    Its one reader is `triggers._candidate_abilities`, which runs on **every**
    event, so this answers for the whole battlefield in one pass rather than
    per object: with no ward static anywhere -- the ordinary board -- it walks
    the statics once and returns ``{}``.

    *Divergence*: a face-down permanent is skipped. The rules would grant it ward
    (707.2 removes the abilities of the *card*, not ones an effect hands over),
    but a static's filter is matched against the printed face, so
    "each other Human you control" would reach through the shell and a ward
    trigger would announce that the hidden card is a Human. `_compute` already
    makes exactly this trade, returning `FACE_DOWN_CHARS` before any static runs.
    Cloak's own ward is unaffected -- it is supplied by the cloak rule rather
    than by a static, and is the one ward a face-down permanent should have.
    """
    statics: list[tuple[GameObject, Mapping[str, Any], Mapping[str, Any]]] = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "ward":
            continue
        cost = static.get("cost")
        if not cost:
            # Defaulting to a free ward here is the failure `_static_value`
            # refuses in the other direction: a keyword that prints on the card,
            # taxes nothing and says nothing about it. The loader already makes
            # this impossible, so reaching here means the two have drifted.
            raise DslError("a ward static has no cost; ward {0} is not a card")
        statics.append((source_obj, static.get("affects") or {}, cost))
    if not statics:
        return {}
    out: dict[int, tuple[Ability, ...]] = {}
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.face_down:
            continue
        found = tuple(
            ward_ability(cost)
            for source_obj, affects, cost in statics
            if _matches(state, obj, source_obj, affects)
        )
        if found:
            out[oid] = found
    return out


def ward_abilities(state: GameState, oid: int) -> tuple[Ability, ...]:
    """The ward abilities one permanent has -- the single-object read.

    Every ward a permanent has, not one: two Coppercoat Vanguards really do tax
    the same Human twice, as two instances of a keyword ability always do.
    """
    return granted_wards(state).get(oid, ())


def matches_static(
    state: GameState, obj: GameObject, source: GameObject, selector: Mapping[str, Any] | None
) -> bool:
    """Public name for the static-filter matcher, for rules outside this module."""
    return _matches(state, obj, source, selector)


def block_restrictions(
    state: GameState, oid: int
) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """The "can't be blocked …" statics that apply to this attacker.

    Returned as ``(source, static)`` pairs rather than answered here, for the
    same reason :func:`protection_from` returns a set: two rules read them at two
    different moments and must ask the same question.  A per-blocker filter is
    checked in ``combat.can_block``, one pair at a time; ``require_all`` can only
    be judged once the whole declaration exists, so it is checked in
    ``combat.blocks_valid`` beside menace, which has exactly that shape.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return []
    out: list[tuple[GameObject, Mapping[str, Any]]] = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "block_restriction":
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        out.append((source_obj, static))
    return out


def protected_from(state: GameState, oid: int, source_oid: int | None) -> bool:
    """Does ``oid`` have protection from ``source_oid``?

    ``source_oid`` is the *source* of the damage, spell or block -- a permanent
    on the battlefield or a spell on the stack.  A quality it does not have
    cannot be protected against, so a missing source is never protection.
    """
    return _matches_protection(state, protection_from(state, oid), source_oid)


def _matches_protection(
    state: GameState, qualities: frozenset[str], source_oid: int | None
) -> bool:
    """Is ``source_oid`` one of the ``qualities`` something has protection from?

    Split out of :func:`protected_from` when protection learned to cover a
    *player* as well as a permanent: the two differ only in where the set of
    qualities comes from, and the comparison against the source is the half that
    must not drift -- "protection from everything" has to mean the same thing on
    a seat as it does on Progenitus.
    """
    if source_oid is None:
        return False
    if not qualities:
        return False
    source = state.objects.get(source_oid)
    if source is None:
        return False
    # "Protection from everything" (702.16i). Answered before the source's
    # characteristics are read at all, because the whole point is that they do
    # not matter -- a colourless artifact spell with no subtypes is stopped by
    # it, and no set of qualities built from types, subtypes and colours could
    # contain one.
    if PROTECTION_EVERYTHING in qualities:
        return True
    c = chars(state, source_oid)
    card = state.card_of(source)
    # Derived characteristics on the battlefield, printed ones anywhere else --
    # the same rule `selectors.matches` follows, so "protection from Wizards"
    # sees a creature that was *granted* the Wizard subtype.
    if source.on_battlefield:
        have = set(c.types) | set(c.subtypes) | set(c.colors)
    else:
        have = set(card.types) | set(card.subtypes) | set(card.colors)
    return bool(have & qualities)


def player_protection_from(state: GameState, pid: int) -> frozenset[str]:
    """The qualities this **player** has protection from.

    The seat-side twin of :func:`protection_from`, and it returns the same flat
    set of strings so the rules that read protection ask one kind of question.
    Its entries come from `GameState.player_protections` rather than from
    `_battlefield_statics`: no static can name a seat, and the effect outlives
    whatever installed it.

    Only two rules read this, against the four that read the object side. A
    player cannot be blocked, and the "can't be enchanted" half is reached
    through targeting -- an Aura that enchants a player targets it as it is cast
    (303.4a), so the target check already refuses it.
    """
    if not state.player_protections:
        return frozenset()
    return frozenset(
        entry.quality for entry in state.player_protections if entry.player == pid
    )


def player_protected_from(state: GameState, pid: int, source_oid: int | None) -> bool:
    """Does ``pid`` have protection from ``source_oid``?

    Protection stops **anyone**, its controller included: Teferi's Protection
    means your own Lightning Bolt cannot be pointed at you either. That is the
    same rule `can_be_targeted` already applies on the object side, and the half
    a hexproof-shaped implementation would silently get wrong.
    """
    return _matches_protection(state, player_protection_from(state, pid), source_oid)


def _active_player_statics(
    state: GameState, effect: str
) -> Iterator[tuple[GameObject, Mapping[str, Any]]]:
    """Every *active* player-wide ``effect`` static on the battlefield, with its source.

    The player-wide twin of :func:`_battlefield_statics`, and the reason it
    exists is the one thing the two used to disagree about. That function gates
    each static on :func:`_static_active`; the four hand-rolled walks that read
    the `affects_player` effects did not, so a `condition` written beside
    `play_lands_from_library_top` was validated by the loader, stored on the
    ability, and then never asked. The card loaded clean, printed its "as long
    as" clause and granted the permission unconditionally -- a silent
    over-grant, which is worse than refusing the card.

    Verge Rangers is the witness: "**as long as an opponent controls more lands
    than you**, you may play lands from the top of your library" would otherwise
    have been Oracle of Mul Daya's unconditional permission on a 3/2 first
    striker.

    The condition reads pipeline *inputs* here exactly as it does in
    `_battlefield_statics`, and the acyclicity argument is easier rather than
    harder: these readers run at legality, payment, trigger collection,
    serialization and the cleanup step -- outside the characteristics pipeline
    entirely -- so there is no layer whose output one could come to depend on.

    The source is yielded beside the static because two of the callers need it:
    `affects_player` is resolved against its controller, and a `condition`'s
    "you" and its `counters` head are both relative to the permanent carrying it.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        for ability in state.card_of(obj).abilities:
            static = ability.static
            if not ability.is_static or not static:
                continue
            if static.get("effect") != effect:
                continue
            if not _static_active(state, obj, static):
                continue
            yield obj, static


def _reaches_player(source: GameObject, static: Mapping[str, Any], pid: int) -> bool:
    """Does a player-wide static's ``affects_player`` name ``pid``?

    Defaulting to ``"you"`` matches the loader, which requires the key on every
    effect that reaches here -- so the default is unreachable from an authored
    card and is only a floor under hand-built states.
    """
    who = static.get("affects_player", "you")
    if who == "you":
        return source.controller == pid
    if who == "opponent":
        return source.controller != pid
    return True


def life_loss_multiplier(state: GameState, pid: int) -> int:
    """What a life loss by ``pid`` is multiplied by right now.  Usually 1.

    Bloodletter of Aclazotz: "If an opponent would lose life during your turn,
    they lose twice that much life instead."  The "during your turn" half is an
    ordinary ``condition`` on the static and is honoured by
    `_active_player_statics`, which is the whole reason this reads through that
    function rather than walking the battlefield itself -- a condition written
    beside a player-wide static and never asked is the silent over-grant that
    function exists to stop.

    **Multiplied, not summed.**  Two Bloodletters are two separate replacements
    of one event, each applying once (614.5), and a loss doubled twice is
    quadrupled -- which is also why the empty case has to return 1 rather than
    0.  616.1 lets the affected player order two applicable replacements and
    this engine does not ask, the same divergence `_token_creation_plan`
    records; for a product the order cannot show, so here it costs nothing.

    Short-circuits on an empty battlefield walk, because this is asked on every
    point of life any player loses -- every damage to a player, every paid life,
    every drain -- so the games playing none of these cards must pay nothing.
    """
    multiplier = 1
    for obj, static in _active_player_statics(state, "replace_life_loss"):
        if _reaches_player(obj, static, pid):
            multiplier *= int(static.get("loss_multiplier", 1))
    return multiplier


def player_doubles_land_mana(state: GameState, pid: int) -> bool:
    """Vorinclex: "whenever you tap a land for mana, add one mana of any type
    that land produced"."""
    return _player_static(state, pid, "double_land_mana")


def players_freezing_opponent_lands(state: GameState) -> frozenset[int]:
    """Everyone whose ``freeze_opponent_lands`` static is on the battlefield.

    Returned as a set of players rather than asked per-player, because the
    question at the mana choke point is "does *anybody but this land's
    controller* have it", and asking once is cheaper than asking per opponent
    inside a payment.
    """
    return frozenset(
        obj.controller for obj, _ in _active_player_statics(state, "freeze_opponent_lands")
    )


def players_doubling_land_triggers(state: GameState) -> frozenset[int]:
    """Everyone whose ``double_land_triggers`` static is on the battlefield.

    Ancient Greenwarden. Shaped like `players_freezing_opponent_lands` and read
    by `triggers._land_trigger_doublers`, which owns the much narrower question
    of *which* event doubles; this owns only who is switched on, so the
    "as long as…" gate lives in one place with the other six.
    """
    return frozenset(
        obj.controller for obj, _ in _active_player_statics(state, "double_land_triggers")
    )


def player_has_no_hand_limit(state: GameState, pid: int) -> bool:
    """Whether any ``no_hand_limit`` static frees this player from discarding.

    Reliquary Tower, Thought Vessel, Nezahal. Written as a player-wide static
    like ``extra_land_drops`` rather than as a characteristic, because it is a
    fact about the *player* and there is no object for it to attach to.
    """
    return _player_static(state, pid, "no_hand_limit")


def attack_forbidden(state: GameState, oid: int) -> bool:
    """Is this creature under a global "can't attack" static?

    Stormtide Leviathan's "creatures without flying or islandwalk can't
    attack". Unlike every other static, its filter routinely names creatures its
    controller does not control -- the card is a lock on the whole table -- so
    `affects` here is written with an explicit ``controller: "any"``.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "cant_attack":
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def attack_defender_forbidden(state: GameState, oid: int, defender: int) -> bool:
    """May this creature **not** attack ``defender``, or a planeswalker they control?

    Combat Calligrapher -- "Inklings can't attack you or planeswalkers you
    control." A prohibition that is a *continuous ability of a permanent*,
    scoped to one seat and filtered on the attacking creature's printed
    characteristics. None of the three near misses is that shape.

    Written as `attack_tax`'s twin, with the price taken out: `affects` says
    which creatures are stopped and the static's own controller is the seat they
    are stopped from attacking -- "creatures can't attack **you**" is the same
    sentence in both, once as a toll and once as a wall.
    `cant_attack`/`attack_forbidden` is the wrong one because no defender is in
    the question at all, so an Inkling under it could not attack *anybody* --
    strictly stronger than the printed line, and it would switch off
    Calligrapher's own second ability, which hands opponents Inklings expressly
    to keep them swinging at each other. The `cant_attack_player` op has the
    right scope and carries no creature filter at all, and its `duration` is
    required precisely because it is a resolving one-shot with no permanent to
    hang off, so it cannot be a creature's continuous ability.

    **Planeswalkers are included here**, which is the opposite answer from that
    op, and it is opposite for the reason goad's is opposite to Ghostly
    Prison's: the answer follows the printed sentence rather than a house rule.
    "You can't attack that player" is 506.2's reading -- attacking somebody's
    planeswalker is not attacking them -- and the sentence *this* effect exists
    for says "or planeswalkers you control" out loud, so neither half is
    inferred. A planeswalker's controller **is** the defending player (506.2)
    and `combat.legal_planeswalker_defenders` passes it, so the one seat test
    below covers the walker as well as the chair, exactly as goad's does.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "cant_attack_you":
            continue
        # The wall protects the seat the permanent is under -- the line
        # `attack_tax` already draws, and the whole shape of the family.
        if source_obj.controller != defender:
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def any_defender_attack_prohibition(state: GameState) -> bool:
    """Is there a ``cant_attack_you`` static on the battlefield at all?

    The cheap half of `combat.can_attack`'s guard against a creature with
    nowhere left to attack, beside the `attack_restrictions` list test that
    guard already had. The expensive half -- "has this creature any legal
    defender left" -- walks every seat and every planeswalker through
    `attack_target_forbidden`, and is worth asking only in a game that plays one
    of these cards.
    """
    return any(
        static.get("effect") == "cant_attack_you"
        for _, static in _battlefield_statics(state)
    )


def attack_tax(state: GameState, oid: int, defender: int) -> str:
    """The mana a creature's controller must pay to declare it against ``defender``.

    "Creatures can't attack you unless their controller pays {2} for each
    creature they control that's attacking you" -- Propaganda, and the whole
    pillowfort family behind it (Ghostly Prison, Norn's Annex, Sphere of
    Safety).

    Neither near miss can say it. `cant_attack` and the `cant_attack_player` op
    are absolute prohibitions with no cost to them, so a card built on either is
    a *lock* rather than a tax -- strictly stronger than what is printed, and it
    would look entirely normal on screen. `ward` is the only other
    cost-parameterised static and it prices *targeting*, paying out as a
    triggered counter that never reaches the declare-attackers step.

    Returned as a mana string rather than a `Cost`, so this module stays free of
    `costs`, which imports it. Taxes from several permanents add up, which is
    what two Propagandas do.

    The per-creature scaling in the printed text falls out of *where* this is
    charged: the price is settled once per attacker as it is declared, so a
    three-creature attack pays {2} three times, exactly as 508.1g totals it.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return ""
    generic = 0
    parts: list[str] = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "attack_tax":
            continue
        # The tax protects the seat the permanent is under, which is the whole
        # shape of the card: "creatures can't attack **you**".
        if source_obj.controller != defender:
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        # The same `cost` mapping ward stores, so the two go through one
        # validator and there is one place for a price to be written.
        spec = static.get("cost")
        inner = str((spec or {}).get("mana") or "").strip() if isinstance(spec, Mapping) else ""
        # Summed rather than concatenated where they are plain generic, so two
        # Propagandas read as {4} instead of an unpayable "{2}{2}".
        if inner.startswith("{") and inner.endswith("}") and inner[1:-1].isdigit():
            generic += int(inner[1:-1])
        elif inner:
            parts.append(inner)
    if generic:
        parts.insert(0, "{" + str(generic) + "}")
    return "".join(parts)


def block_forbidden(state: GameState, oid: int) -> bool:
    """Is this creature under a "can't block" static?

    Unleash's "this creature can't block as long as it has a +1/+1 counter on
    it", and the plain "can't block" printed on a hundred aggressive commons.
    The exact mirror of `attack_forbidden`, down to reusing `_matches`, and a
    static rather than a `Keyword` for the reason `block_restriction` is one:
    a keyword is a characteristic and this is a permission.

    Unlike `attack_forbidden` this is nearly always self-referential -- the
    static sits on the creature it stops -- but the filter is the same one, so
    a global "creatures your opponents control can't block" costs nothing extra.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "cant_block":
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def _alone_forbidden(state: GameState, oid: int, effect: str) -> bool:
    """Is this creature under a "…alone" static of this kind?

    The shared body of the two below, which differ only in the effect name they
    look for. Deliberately **not** folded into `attack_forbidden` and
    `block_forbidden` with a flag: those two answer "may this creature do it at
    all", and every caller of them treats a `True` as an absolute prohibition.
    A creature that can't attack alone can attack, so it must not be visible to
    that question at all -- which is why this is a separate effect name rather
    than an extra key on `cant_attack`.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != effect:
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def attack_alone_forbidden(state: GameState, oid: int) -> bool:
    """"This creature can't attack alone" -- may it be the *only* attacker?

    A restriction on the declaration as a whole (508.1c), not on the creature,
    so the answer here is only half of it: this says the creature carries the
    restriction, and `combat.attacks_valid` decides whether the declaration
    being built breaks it.
    """
    return _alone_forbidden(state, oid, "cant_attack_alone")


def block_alone_forbidden(state: GameState, oid: int) -> bool:
    """"This creature can't block alone" -- may it be its controller's only blocker?

    The mirror of `attack_alone_forbidden`, read by `combat.blocks_valid`
    (509.1b) beside menace and `require_all`, which have the same shape: a
    legality that only exists once the whole declaration does.
    """
    return _alone_forbidden(state, oid, "cant_block_alone")


def spell_cost_reduction(state: GameState, pid: int, card: CardDef) -> int:
    """How much less ``pid`` pays for ``card`` because of statics on the board.

    "Creature spells with flying you cast cost {1} less to cast." The card-level
    `cost_reduction` field points the other way -- it discounts the card that
    *carries* it, by counting permanents -- so Warden of Evos Isle cannot be
    written with it. This discounts a **different** card, picked out by that
    card's own printed characteristics.

    The filter is matched against the printed face rather than a permanent,
    which is why it reuses `_matches_printed` and nothing else: the spell is
    still in hand while legality prices it, so there is no board state to read
    and no derived characteristics to recurse into.

    Returns a total, clamped and applied by `costs.cost_reduction` -- the one
    function both legality and payment already call, so a spell offered at the
    reduced price is also paid at it.
    """
    total = 0
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "spell_cost_reduction":
            continue
        filt = static.get("affects_spells")
        if not filt:
            # The loader requires one. Defaulting to `{}` here would make an
            # empty filter match *every* spell, so a compile bug would silently
            # discount the whole game rather than nothing.
            continue
        who = str(filt.get("controller", "you"))
        if who == "you" and source_obj.controller != pid:
            continue
        if who == "opponent" and source_obj.controller == pid:
            continue
        # "Creature spells you cast **of the chosen type** cost {1} less."
        # Herald's Horn. The substitution needs the permanent that made the
        # choice, and this loop has had it all along -- `_battlefield_statics`
        # yields the source beside the static, and only `_matches_printed`'s
        # signature (a printed card, no object) suggested otherwise.
        resolved = resolve_chosen_colors(resolve_chosen_subtypes(filt, source_obj), source_obj)
        if not _matches_printed(card, resolved):
            continue
        total += _static_value(state, static.get("amount"), source_obj)
    return total


def attack_compelled(state: GameState, oid: int) -> bool:
    """Is this creature under a continuous "attacks each combat if able"?

    The permanent counterpart of the `must_attack` op. That op writes a
    one-shot flag on the object -- Bident of Thassa's "this turn", Trench
    Behemoth's "next combat" -- and is spent once the declaration is locked in.
    A printed "This creature attacks each combat if able" is not spent: it is
    true again next turn, and it stops being true the moment its source leaves
    or its condition turns off. That is a static, so it is read live off the
    battlefield rather than stored.

    One effect covers all the printed variants -- "This creature…", "Creatures
    your opponents control…", "Enchanted creature…" -- because they differ only
    in `affects`. Like `cant_attack`, that filter routinely names creatures the
    static's own controller does not control.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "attacks_if_able":
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def untap_also(state: GameState, active_pid: int) -> list[int]:
    """Permanents that untap during *someone else's* untap step.

    Murkfiend Liege: "Untap all green and/or blue creatures you control during
    each other player's untap step." A fact about a set of permanents rather
    than a characteristic of any one of them, so it is read here at the untap
    step rather than layered into `chars` -- the same shape as the player-wide
    statics below, which is what `extra_land_drops` and `no_hand_limit` already
    are.

    "each *other* player's" is the whole of it: on your own untap step these
    creatures untap anyway, so a version that ignored whose turn it is would
    look identical every time you tested it.
    """
    out: list[int] = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "untap_during_each_untap_step":
            continue
        if source_obj.controller == active_pid:
            continue
        for oid in state.battlefield:
            obj = state.objects.get(oid)
            if obj is None or obj.controller != source_obj.controller:
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                out.append(oid)
    return out


def _player_static(state: GameState, pid: int, effect: str) -> bool:
    """Whether any *active* permanent grants ``effect`` to this player.

    "Active" is the whole of what `_active_player_statics` adds: an "as long
    as…" clause on a player-wide static is honoured here rather than dropped.
    """
    return any(
        _reaches_player(obj, static, pid)
        for obj, static in _active_player_statics(state, effect)
    )


def player_reveals_library_top(state: GameState, pid: int) -> bool:
    """"Play with the top card of your library revealed." Vampire Nocturnus.

    Purely a *visibility* change -- it grants no permission and moves no card,
    which is what separates it from `play_lands_from_library_top`. The whole of
    it is that the client is allowed to draw the card, so this is read by
    `serialize` and by nothing in the rules.

    It matters anyway, and not only as flavour: Vampire Nocturnus is a card you
    cannot pilot without it. Whether your team has flying is a fact you are
    supposed to know before declaring attackers, and the condition that decides
    it is otherwise invisible.
    """
    return _player_static(state, pid, "reveal_library_top")


def player_looks_at_library_top(state: GameState, pid: int) -> bool:
    """"You may look at the top card of your library any time." Verge Rangers.

    The *private* half of the pair. `reveal_library_top` above is "play with the
    top card revealed": the card becomes public and `serialize` sends it to
    every seat, because an opponent who cannot see a revealed card is playing
    against information they are entitled to. This one grants no such
    entitlement -- Verge Rangers never shows the card to anybody but its
    controller -- so `serialize` sends it to that player's seat and no other.
    Substituting the public static would have handed the opponent a card the
    printed card does not show them, which is a *different* card.

    It is not the `look_at_top` op either. That op looks once, at resolution,
    and is spent; this is a continuous permission, true again the next time you
    care and false the instant its source leaves. "Any time" is not a moment for
    a trigger to fire at.

    Like its public twin it changes no rule: it grants no permission to play or
    move the card, and it is read by `serialize` and by nothing else.
    """
    return _player_static(state, pid, "look_at_library_top")


def player_plays_lands_from_graveyard(state: GameState, pid: int) -> bool:
    """Whether this player may play lands from their graveyard.

    Ramunap Excavator, Crucible of Worlds, Ancient Greenwarden. Widens *where* a
    land may be played from; the one-land-per-turn rule is untouched and still
    enforced by `lands_played`.
    """
    return _player_static(state, pid, "play_lands_from_graveyard")


def graveyard_cast_permissions(
    state: GameState, pid: int
) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """"…you may cast an artifact spell from your graveyard." Edgar.

    The permissions currently reaching ``pid``, each with the permanent granting
    it -- the source matters because the rate limit is counted per granting
    permanent, so two Edgars are two casts a turn the way two Welcoming Vampires
    each draw.

    A list rather than a bool, which is the whole difference from
    `player_plays_lands_from_graveyard`: that one answers a yes/no the land drop
    asks, while this has to say *which* spells and *how many times*.
    """
    return [
        (obj, static)
        for obj, static in _active_player_statics(state, "cast_from_graveyard")
        if _reaches_player(obj, static, pid)
    ]


def graveyard_cast_allows(
    state: GameState, source_obj: GameObject, static: Mapping[str, Any], card: CardDef
) -> bool:
    """Does this permission let *this* card out of the graveyard?

    The same `affects_spells` filter `spell_cost_reduction` matches a card in
    hand with, and matched the same way -- `_matches_printed`, because a card in
    a graveyard has a printed face and an owner and no board state.
    """
    filt = static.get("affects_spells")
    if not filt:
        # The loader requires one. Defaulting to `{}` would make an empty filter
        # free the whole graveyard, so a compile bug would hand over everything
        # rather than nothing.
        return False
    resolved = resolve_chosen_colors(resolve_chosen_subtypes(filt, source_obj), source_obj)
    return _matches_printed(card, resolved)


def graveyard_cast_arrival_ok(
    state: GameState, static: Mapping[str, Any], obj: GameObject
) -> bool:
    """"…put there **from anywhere other than the battlefield this turn**".

    Banon, the Returners' Leader. Asked of the *object* rather than the printed
    card, because when a card reached a graveyard and from where are facts about
    this copy of it and not about the card -- which is why they could not go in
    `affects_spells` beside the type filter.

    Absent from the static, every card in the yard qualifies, which is Edgar.
    """
    arrival = static.get("arrived_this_turn_from")
    if arrival is None:
        return True
    if obj.graveyard_turn != state.turn:
        return False
    allowed = [str(z) for z in arrival]
    if allowed == ["any"]:
        return True
    forbidden = [z[1:] for z in allowed if z.startswith("!")]
    if forbidden:
        # "from anywhere **other than** the battlefield" -- a complement, and
        # written as one because the printed line is: listing the four zones a
        # card could otherwise have come from would silently miss the fifth.
        return obj.graveyard_from not in forbidden
    return obj.graveyard_from in allowed


def library_top_cast_permission(state: GameState, pid: int):
    """The permanent letting this player cast off the top of their library.

    Bolas's Citadel. The casting twin of
    `player_plays_lands_from_library_top`, which is documented as lands only and
    so grants nothing for a nonland spell -- and unlike it this returns the
    granting permanent rather than a bool, because the price rides on the same
    static and `Game._cast` has to read it.
    """
    for obj, static in _active_player_statics(state, "cast_from_library_top"):
        if _reaches_player(obj, static, pid):
            return obj, static
    return None


def player_plays_lands_from_library_top(state: GameState, pid: int) -> bool:
    """Whether this player may play the top card of their library, if it is a land.

    Oracle of Mul Daya, Courser of Kruphix. Only the *top* card, which is what
    the cards say and also the only part of a hidden zone anybody is allowed to
    know about.
    """
    return _player_static(state, pid, "play_lands_from_library_top")


def player_extra_land_drops(state: GameState, pid: int) -> int:
    """Sum of every *active* ``extra_land_drops`` static affecting this player.

    A switched-off one contributes nothing rather than its amount -- the one
    place among the player-wide statics where the gate changes a number instead
    of a permission.
    """
    return sum(
        _static_value(state, static.get("amount"), obj)
        for obj, static in _active_player_statics(state, "extra_land_drops")
        if _reaches_player(obj, static, pid)
    )


def token_creation_replacements(state: GameState, pid: int) -> list[Mapping[str, Any]]:
    """The active ``replace_token_creation`` statics ``pid`` controls, in battlefield order.

    Academy Manufactor and Divine Visitation. Read by
    `primitives._token_creation_plan` and by nothing else, the way
    `untap_during_each_untap_step` is read by the untap step alone: a token that
    is about to be created has no object for a characteristic to attach to, so
    this cannot be a layer -- it is a fact about what *will* be made.

    Filtered on the source's controller rather than on `affects_player`, because
    both printed cards say "you" and neither prints the opponent-facing half.
    Order is `state.battlefield` order, which is arrival order: rule 616.1 gives
    the choice of which replacement to apply first to the affected player, and
    this engine does not ask -- see `_token_creation_plan`, which owns that
    divergence and the once-per-event rule with it.
    """
    return [
        static
        for obj, static in _active_player_statics(state, "replace_token_creation")
        if obj.controller == pid
    ]


def printed_token_matches(state: GameState, def_id: str, selector: Mapping[str, Any]) -> bool:
    """Does the token about to be created match this filter?

    A token definition is nothing *but* a printed face -- there is no object yet,
    no controller on it and no board state -- so this is `_matches_printed` and
    only `_matches_printed`, shared with the counting filters rather than
    rewritten beside `create_token`, where the two spellings of "Artifact
    subtype Treasure" would drift.

    An empty selector matches everything, which is the one place the static
    filter language differs here on purpose: `_matches` refuses `None` because
    "every permanent gets +1/+1" is not a card, and "if you would create a
    token" with no filter at all is a shape a card really does print.
    """
    return _matches_printed(state.registry.get(def_id), selector)


def commander_subtypes(state: GameState, pid: int) -> frozenset[str]:
    """Every creature type this player's commanders currently have.

    The union across their commanders, so a partner pair contributes both
    halves' types -- "shares a creature type with your commander" is satisfied
    by either one.

    Read through `chars` where the commander is on the battlefield and off the
    printed card otherwise: an animated or type-changed general really does
    share its new type, and a commander sitting in the command zone -- where it
    is for most of the game -- has only what is printed on it.

    Lives here rather than in `selectors` because both halves of the filter
    language ask it: `selectors.matches` for effects, and
    `triggers.matches_card_filter` for trigger filters, which is the one Path of
    Ancestry actually reaches.
    """
    out: set[str] = set()
    for oid in state.commanders_of(pid):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.zone is Zone.BATTLEFIELD:
            out |= set(chars(state, oid).subtypes)
        else:
            out |= set(state.card_of(obj).subtypes)
    return frozenset(out)
