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
:func:`commanderblitz.cards.loader.check_static_constraints`:

    **A static ability's filter may not read another static ability's output.**

Static filters are therefore matched against *printed* characteristics (plus the
object's own board state: controller, tapped, attacking, counters).  That removes
all recursion and all dependency ordering, at the cost of not supporting cards
whose anthem depends on another anthem's result.  The curated decks respect this.

``power`` and ``toughness`` are the one *derived* characteristic a static filter
may name, and they are admitted under a restriction rather than as an exception.
What such a filter reads is :func:`_base_pt` -- the size an object **starts**
this pipeline with: its printed P/T, a copy exception's replacement of it
(707.9b), bestow's 0/0 while attached, and the 2/2 shell of a face-down
permanent (707.2).  Nothing any layer below writes is visible: not an
``animate``, not a ``set_pt``, not an anthem, not a +1/+1 counter, not a pump.
Reading :func:`chars` instead is not a near miss but an unbounded recursion --
:func:`_matches` is called *from* :func:`_compute`, and from
:func:`_static_active` before :func:`_compute` has applied a single layer.

The line sits at base P/T rather than at the looser "everything no static
wrote", which would have been acyclic too: counters and until-end-of-turn pumps
are pipeline inputs like any other, and a filter could have read them safely.
It is the stricter line because it is the one this module already takes for
keywords, and layer 2b spells out why -- a static's ``keywords`` filter does not
see a flying counter either, and "making counters the one visible kind of grant
would be the inconsistency".  Base P/T is that same rule pointed at size, and it
costs nothing to keep true: :func:`_compute` *begins* by calling the very
function the filter calls, so the two cannot drift.

Two readers of the static filter language sit **outside** this pipeline and so
read the real, fully derived power: :func:`commanderblitz.engine.triggers.matches_card_filter`
(Welcoming Vampire's "creatures you control with power 2 or less enter" must see
the anthem, and has since it was written) and
:func:`commanderblitz.engine.cost_reduction._object_matches` (which already reads derived types
and keywords, for the same reason).  Only the reader inside the pipeline is
restricted, because only it can be asked the question halfway through.  The
same goes for the rule-modifying statics the static filter language describes
but no layer applies -- an attack requirement and a block restriction -- which
match with ``derived=True`` (see :func:`_matches`).

A static's "as long as…" `condition` obeys the same constraint from the other
side.  It is evaluated in :func:`_static_active`, which runs in
:func:`_battlefield_statics` -- *before* layer -1, so before any layer has
applied.  Everything it may read is therefore an **input** to the pipeline rather
than an output: printed characteristics, an object's own board state, counters,
whose turn it is, and how many cards sit in a zone.  No layer can change whether
another static is switched on, so the gate is computed once and the fixed order
stays acyclic.  That is the whole reason the condition language is a mirror of
:mod:`commanderblitz.engine.effects.conditions` rather than that module itself: `if`'s
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

import dataclasses
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from .carddef import Ability, CardDef, ward_ability
from .enums import KEYWORD_COUNTERS, SUBTYPE_CLASS, Keyword, Zone
from .errors import DslError
from .mana import ManaOrigin, printed_cost_is
from .objects import MINUS_ONE, PLUS_ONE, TIME_COUNTER, GameObject
from .structs import PROTECTION_COLORLESS, PROTECTION_EVERYTHING, Characteristics
from .text_change import apply_to_ability
from .text_change import apply_to_subtypes as apply_text_changes

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


def subtype_survives(sub: str, types: set[str] | frozenset[str]) -> bool:
    """Whether an object of card ``types`` may keep subtype ``sub`` (205.1b, 205.3d).

    A subtype goes with its card type, and a creature type belongs to Creature
    **or** Kindred (205.3m, 308.3): a type change that leaves a Kindred
    enchantment a Kindred enchantment leaves its Eldrazi too.
    """
    owner = SUBTYPE_CLASS.get(sub, "Creature")
    return owner in types or (owner == "Creature" and "Kindred" in types)


def creature_types_of(state: GameState, oid: int | None) -> frozenset[str]:
    """The **creature types** an object currently has -- 205.3m, not its subtypes.

    "…a spell that shares a creature type with this creature" -- Folk Hero. The
    distinction is the whole point: subtypes are one flat set here, and a
    Background, an Aura, an Equipment, an Arcane or an Adventure is a subtype
    and *not* a creature type, so intersecting raw subtypes would let a
    Background cast beside a Background commander "share a creature type".

    Read off :func:`chars`, so a changeling's printed list and a granted type
    count, and filtered through `SUBTYPE_CLASS` with Creature as the default --
    the same default the type-replacement layer uses, which is how a Kindred
    instant's Goblin counts (205.3m gives Kindred objects creature types) while
    an ordinary instant, whose only subtypes are spell types, shares none. A
    missing object has none.
    """
    if oid is None or state.objects.get(oid) is None:
        return frozenset()
    return frozenset(
        sub
        for sub in chars(state, oid).subtypes
        if SUBTYPE_CLASS.get(sub, "Creature") == "Creature"
    )


def mana_source_traits(state: GameState, oid: int | None) -> ManaOrigin | None:
    """What the permanent at ``oid`` **is**, frozen for a pip of mana to carry.

    "Whenever you cast a spell, if mana from a **Treasure** was spent to cast
    it…" -- Smaug, Wicked Worm. The oid alone cannot answer that question later:
    a Treasure is sacrificed to make its mana, and `sba._tokens_and_attachments`
    removes a token from ``state.objects`` the moment it leaves the battlefield,
    so by the time the spell is on the stack there is nothing left to ask. The
    answer therefore has to be taken here, while the source is still on the
    battlefield and still itself.

    Read from :func:`chars` rather than the printed card, so grants count both
    ways: a land animated into a creature made that mana as a creature, and a
    Treasure is still a Treasure whatever else has been layered onto it.

    ``None`` for mana no permanent made -- an effect's ``add_mana``, or a source
    that has already left. A pip whose traits are ``None`` matches no filter,
    which is the right default: "mana from a Treasure" is a claim, and unknown
    provenance does not establish it.
    """
    if oid is None:
        return None
    obj = state.objects.get(oid)
    if obj is None:
        return None
    derived = chars(state, oid)
    return ManaOrigin(
        oid=oid,
        name=state.card_of(obj).name,
        types=derived.types,
        subtypes=derived.subtypes,
        supertypes=derived.supertypes,
        controller=obj.controller,
    )


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


def last_exiled_creature_card(state: GameState, source: GameObject) -> GameObject | None:
    """The last creature card exiled with ``source`` that is still there.

    "As long as a card exiled with this creature is a creature card, this
    creature has the power, toughness, and creature types of **the last
    creature card exiled with it**" -- Duplicant. Walks the source's own
    `exiled_cards` newest first, so a card the previous incarnation exiled is
    not found (607.2a, 400.7), and keeps only a card still in exile whose
    `exiled_by` is still this source: one that left exile is no longer exiled
    with anything, even if some other effect exiled it again.

    "Creature card" is the card's characteristics in exile, so an animated
    land Duplicant took is a land card and does not count. None when nothing
    qualifies, which is the "as long as" clause being false.
    """
    for oid in reversed(source.exiled_cards):
        card = state.objects.get(oid)
        if card is None or card.zone is not Zone.EXILE or card.exiled_by != source.oid:
            continue
        if "Creature" in chars(state, oid).types:
            return card
    return None


def printed_creature_types(card: CardDef) -> frozenset[str]:
    """The creature types a card **face** has wherever it is -- 205.3m and 604.3.

    `creature_types_of` asks an object and reads the layer pipeline, whose
    statics work on the battlefield only. A card being cast is asked about as a
    `CardDef` (`casting._timing_ok` never sees the object), so this is the
    printed line plus the face's own characteristic-defining abilities, which
    604.3 says function in every zone: changeling is an unconditional
    `add_subtype` static whose `affects` is the card alone, and it makes the
    card every creature type in a hand exactly as on the battlefield. A
    ``{"chosen_type_of": "self"}`` entry is skipped -- a card in a hand has
    chosen nothing.

    Filtered through `SUBTYPE_CLASS` as `creature_types_of` is, so a Kindred
    instant's Goblin counts and an Equipment's "Equipment" does not.
    """
    types = {sub for sub in card.subtypes if SUBTYPE_CLASS.get(sub, "Creature") == "Creature"}
    for ability in card.abilities:
        static = ability.static if ability.is_static else None
        if not static or static.get("condition") or static.get("effect") != "add_subtype":
            continue
        if dict(static.get("affects") or {}) != {"self_only": True}:
            continue
        types.update(
            sub
            for sub in static.get("subtypes", ())
            if isinstance(sub, str) and SUBTYPE_CLASS.get(sub, "Creature") == "Creature"
        )
    return frozenset(types)


def card_in_exile_characteristics(
    state: GameState, card: GameObject
) -> tuple[int, int, frozenset[str]]:
    """A card's power, toughness and creature types where it sits in exile.

    The printed ones, with the card's own characteristic-defining abilities
    applied: 604.3 has a CDA function in every zone, so a `*/*` is a number in
    exile and a changeling card is every creature type there, not the 0 and the
    one printed type the layer pipeline's battlefield-only statics would leave.
    A CDA is the shape the DSL writes one in -- an unconditional `set_pt` or
    `add_subtype` whose `affects` is the card alone (`self_only`); a
    conditional one is an ordinary static that works only on the battlefield.
    """
    c = chars(state, card.oid)
    power, toughness = c.power, c.toughness
    types = set(creature_types_of(state, card.oid))
    # A card in exile has no controller; "you" in its CDA is its owner (108.4a),
    # not whoever controlled the permanent it was before Duplicant took it.
    if card.controller != card.owner:
        card = dataclasses.replace(card, controller=card.owner)
    for ability in state.card_of(card).abilities:
        static = ability.static if ability.is_static else None
        if not static or static.get("condition"):
            continue
        if dict(static.get("affects") or {}) != {"self_only": True}:
            continue
        if static.get("effect") == "set_pt":
            power = _static_value(state, static.get("power"), card)
            toughness = _static_value(state, static.get("toughness"), card)
        elif static.get("effect") == "add_subtype":
            types.update(
                sub
                for sub in resolve_chosen_subtype_list(static.get("subtypes", ()), card)
                if SUBTYPE_CLASS.get(sub, "Creature") == "Creature"
            )
    return power, toughness, frozenset(types)

def _base_pt(state: GameState, obj: GameObject) -> tuple[int, int]:
    """The size an object *starts* the pipeline with, before any layer applies.

    Printed P/T, plus the three things that change what the object **is** rather
    than what has been done to it: a copy exception's base size (707.9b),
    bestow's 0/0 while the Aura is attached (702.103b), and the 2/2 shell of a
    face-down permanent (707.2).  The face-down case is here and not only in
    `_compute` because a static filter asking "power 4 or greater" about a
    manifested card must read the shell, not the hidden card -- anything else is
    a filter that answers off information no player can see.

    Called from exactly two places, and that is the reason it exists. `_compute`
    starts here and then layers animation, `set_pt`, anthems, counters and pumps
    on top of it; `_matches` stops here, because a static filter that could see
    any of those layers could see another static's output, and the fixed order
    has no way to resolve that.  One function, so the filter's idea of where a
    creature's size begins cannot drift from the pipeline's.
    """
    if obj.face_down and obj.on_battlefield:
        return FACE_DOWN_CHARS.power, FACE_DOWN_CHARS.toughness
    card = state.card_of(obj)
    power = card.power or 0
    toughness = card.toughness or 0
    if obj.copy_overrides:
        # "…except it's a **4/4** black Zombie" (eternalize, 702.129a). The base
        # size, before every layer, so counters and anthems land on top of the
        # 4/4 exactly as they would on a printed one (707.9b: the exception
        # becomes the copiable value).
        if (base_power := obj.copy_overrides.get("power")) is not None:
            power = int(base_power)
        if (base_toughness := obj.copy_overrides.get("toughness")) is not None:
            toughness = int(base_toughness)
    if obj.cast_bestowed and obj.attached_to is not None and obj.on_battlefield:
        # Bestow (702.103b): while it is attached it is not a creature, so it
        # has no P/T of its own. The other half of the keyword -- the type line
        # it takes on -- stays in `_compute`, which is the reader that has types
        # to change; the conditions are written identically in both so that they
        # cannot part company.
        power = toughness = 0
    return power, toughness


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
    # The base size, and the same call a static filter makes -- see `_base_pt`.
    # Everything below layers on top of it.
    power, toughness = _base_pt(state, obj)
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
        if added := obj.copy_overrides.get("add_subtypes"):
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
        if added_types := obj.copy_overrides.get("add_types"):
            # "…except it's an artifact **in addition to its other types**."
            # Faerie Artisans. The addition beside `types`' replacement, and the
            # printing decides again: a copied Enchantment Creature stays both.
            types.update(added_types)
        if added_supers := obj.copy_overrides.get("add_supertypes"):
            # "…except it's legendary." Adagia, Windswept Bastion. Unioned onto
            # the copied card's supertypes, so the legend rule -- which reads
            # this, not the printed card -- applies to the token.
            supertypes.update(added_supers)
        if dropped_supers := obj.copy_overrides.get("remove_supertypes"):
            # "…except the token isn't legendary." Miirym, Sentinel Wyrm; Helm
            # of the Host; Kindred Charge. The set difference beside the union
            # above, and the *only* subtraction any printing asks for -- and the
            # one the card is played for: without it the token copies the
            # original's Legendary, `_legend_rule` reads these derived
            # supertypes and sees two legendary permanents of one name under one
            # controller, and the ability that was meant to double a legendary
            # Dragon destroys one instead.
            supertypes.difference_update(dropped_supers)
        # The base size an exception replaces -- "…except it's a **4/4** black
        # Zombie" -- is applied by `_base_pt` above, beside the printed P/T it
        # overrides and where a static filter can read the same answer.

    # Layer 3, text-changing effects (613.1c): "replacing all instances of one
    # creature type with Vampire". New Blood.
    #
    # Here, which is *before* every static below: layer 3 runs ahead of layer 4,
    # so the type-granting statics -- `add_subtype`, `set_types`, `animate` --
    # layer on top of the rewritten line exactly as they would on a printed one.
    # Applied after `copy_overrides` for the same ordering reason: a copy's
    # exception is part of what the object is, and the text change rewrites what
    # it ended up being.
    #
    # This is only half of "all instances". The other half is the word inside
    # the object's own rules text, which `abilities_of` rewrites; and a third
    # reader, `_matches`, needs it too, because a *static filter belonging to
    # another card* asks about printed subtypes without coming through here.
    if obj.text_changes:
        subtypes = apply_text_changes(subtypes, obj.text_changes)

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
        # Its 0/0 is `_base_pt`'s, under the identical condition, so a static
        # filter reads the same non-creature size this line does.

    # Impending (702.176a): "as long as this permanent's impending cost was paid
    # and it has a time counter on it, it's not a creature". A layer-4 type
    # change, placed beside bestow's and for its reason: the rule makes it a
    # static ability of the permanent itself, timestamped with its arrival, so
    # an animation or a `set_types` that began later layers on top of the
    # non-creature exactly as it would on a printed enchantment.
    #
    # Both halves of the condition are pipeline **inputs** -- `cast_impending`
    # is a cast stamp and `counters` is the object's own board state, which ADR
    # 0001 lets a filter read -- so nothing here can come to depend on another
    # static's output. The creature types go with the card type, as they do
    # under `set_types` (205.1b, 613.1d): an impending Overlord is a bare
    # Enchantment until it is a creature again. The printed P/T stays: a
    # non-creature's size is read by nothing, and the last time counter coming
    # off is all it takes to be a 6/6 again.
    #
    # Ahead of the statics for the layer order too: the effect is applied in
    # layer 4, so an ability-removing static (layer 6) does not undo it.
    if obj.cast_impending and obj.on_battlefield and obj.counter(TIME_COUNTER) > 0:
        types.discard("Creature")
        subtypes = {sub for sub in subtypes if subtype_survives(sub, types)}

    if obj.on_battlefield:
        statics = _battlefield_statics(state)

        # -2. "…this creature has the power, toughness, and creature types of
        #     the last creature card exiled with it. It's still a Shapeshifter."
        #     Duplicant. A 7b size and a layer-4 creature-type replacement, both
        #     read off the card in exile, and placed *first* -- before
        #     `animate`, `set_types` and every grant -- because its timestamp is
        #     the permanent's own arrival: the effects that usually meet it
        #     (an animation, an Imprisoned in the Moon, a "becomes a Vampire in
        #     addition") began later and layer on top, and the anthems,
        #     counters and pumps below add to the copied size as they add to a
        #     printed one. The other creature types are replaced, not kept;
        #     non-creature subtypes stay, and so does the named type.
        for source_obj, static in statics:
            if static.get("effect") != "imprint_characteristics":
                continue
            if not _matches(state, obj, source_obj, static.get("affects")):
                continue
            imprinted = last_exiled_creature_card(state, source_obj)
            if imprinted is None:
                continue
            power, toughness, copied = card_in_exile_characteristics(state, imprinted)
            subtypes = {
                sub for sub in subtypes if SUBTYPE_CLASS.get(sub, "Creature") != "Creature"
            }
            subtypes.update(copied)
            subtypes.update(static.get("subtypes", ()))

        # -1. animation -- "becomes a 4/4 creature until end of turn. It's still
        #     a land."  It runs *before* everything else because it replaces the
        #     printed base P/T rather than modifying it: put after the statics
        #     and it would erase an anthem, put after the counters and it would
        #     erase them too.  Here, everything below layers on top, which is
        #     what the real layer system does with a 7b effect.
        #
        #     Timed and indefinite animations (Oko's Elk, `obj.animations`) are
        #     read together in timestamp order, so whichever began later sets
        #     the base size -- a creature-land animated and then Oko'd is a 3/3
        #     Elk for the turn, and one Oko'd and then animated is the 4/4.
        #
        #     An `exact` animation replaces rather than adds: its colours become
        #     exactly these, its card types exactly these, and its creature
        #     types exactly these ("becomes a green Elk creature"). Subtypes of
        #     a card type it no longer has go with that type (205.1b, the rule
        #     `set_types` below applies too); supertypes are untouched.
        animations = sorted(
            (*obj.animations, *(t for t in obj.until_eot if t.kind == "animate")),
            key=lambda t: t.timestamp,
        )
        for temp in animations:
            if temp.exact:
                types = set(temp.types)
                subtypes = {
                    sub
                    for sub in subtypes
                    if SUBTYPE_CLASS.get(sub, "Creature") in types
                    and SUBTYPE_CLASS.get(sub, "Creature") != "Creature"
                }
                colors = set(temp.colors)
            else:
                types.update(temp.types)
                colors.update(temp.colors)
            subtypes.update(temp.subtypes)
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
                subtypes = {sub for sub in subtypes if subtype_survives(sub, types)}

        # 0a. creature-type replacement -- "…is a Dragon with base power and
        #     toughness 4/4 … (It loses all other creature types.)" Goddric,
        #     Cloaked Reveler; Kenrith's Transformation's "is a green Elk
        #     creature". Layer 4 like `set_types` above, and after it, so an
        #     Aura that makes a creature exactly a Creature *and* exactly an Elk
        #     ends with both whichever order its lines are printed in.
        #
        #     Only the creature types go (205.3m): an Equipment or a Vehicle
        #     stays one, and card types and supertypes are not touched -- a
        #     legendary Goddric is still legendary. The named types arrive only
        #     on a creature, because 205.3d forbids a subtype whose card type
        #     the object lacks; a permanent something has made a land is not a
        #     "Land -- Dragon". Before the grants below, for the same promise
        #     `set_types` keeps: what is added in addition survives.
        for source_obj, static in statics:
            if static.get("effect") != "set_creature_types":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                subtypes = {
                    sub for sub in subtypes if SUBTYPE_CLASS.get(sub, "Creature") != "Creature"
                }
                if "Creature" in types:
                    subtypes.update(static.get("subtypes", ()))

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
        #    "Until end of turn, Sarkhan becomes a Dragon in addition to its
        #    other types" is the same input with a clock (`recorded_subtypes`).
        subtypes.update(recorded_subtypes(obj))

        #    The grant is resolved per source rather than read off the compiled
        #    static, because one entry in that list is not a literal name:
        #    `{"chosen_type_of": "self"}` is "this creature is **the chosen
        #    type** in addition to its other types" -- Roaming Throne, Arcane
        #    Adaptation, Xenograft. It reads the type *this static's own source*
        #    named, which is why the substitution happens here, inside the loop
        #    that already knows which permanent the static came from, and not at
        #    load time: the choice does not exist until the permanent arrives,
        #    and a second `choose_type` or a `change_text` moves it afterwards.
        #
        #    A source that has chosen nothing yet grants **nothing** -- not
        #    every type, and not a literal placeholder. Layer 4 runs on every
        #    recompute, so the type appears the moment the choice is made.
        for source_obj, static in statics:
            if static.get("effect") != "add_subtype":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                subtypes.update(
                    resolve_chosen_subtype_list(static.get("subtypes", ()), source_obj)
                )
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
                # "**During your turn**, this creature has first strike."
                # Read off the active player, which is a pipeline input, so no
                # static is reading another static here.
                if temp.only_your_turn and state.active_player != obj.controller:
                    continue
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

        # 9. "Creatures your opponents control **lose first strike and can't
        #    have or gain first strike**" -- Archetype of Courage, and the rest
        #    of that cycle.
        #
        #    Last, and that is the whole design of it. `lose_all_abilities` at
        #    layer 1 is deliberately *early*, because 613.1b keeps whatever is
        #    added after a removal -- an Imprisoned in the Moon plus a
        #    Levitation leaves the permanent flying. This sentence is the other
        #    kind: "can't have or gain" is a standing prohibition, not a
        #    one-time subtraction, so it has to outrank every adder above it --
        #    the grants at 2, keyword counters at 2b, the until-end-of-turn
        #    grants at 6, suspend's haste at 7 and `granted_keywords` at 8.
        #    Placed anywhere earlier, an opponent's anthem or a first_strike
        #    counter would hand the keyword straight back and the card would
        #    read as working while doing nothing on the only boards it matters.
        #    Moving this block above layer 2 fails exactly the two tests in
        #    `test_lose_keyword.py` that assert the prohibition, and nothing
        #    else -- which is why those two are there.
        #
        #    It subtracts named keywords only, which is what separates it from
        #    `lose_all_abilities`: that one would also take the opponents'
        #    flying, their triggered abilities and their activated abilities,
        #    turning a first-strike hoser into half a Humility.
        for source_obj, static in statics:
            if static.get("effect") != "lose_keyword":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                keywords -= set(static.get("keywords", ()))

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
                # A Class's level-3 "loses all abilities" or "have …" is not
                # there at level 2 (716.2b). Read off the printed face for the
                # regress this function's callers document, so the level gate
                # `present_printed_abilities` applies has to be applied here too.
                if not ability.present_at(obj.class_level):
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
    if obj.lost_all_abilities:
        return True
    return any(
        static.get("effect") == "lose_all_abilities"
        and _matches(state, obj, source_obj, static.get("affects"))
        for source_obj, static in _ability_statics(state)
    )


def printed_abilities(state: GameState, obj: GameObject) -> tuple[Ability, ...]:
    """This object's printed abilities, with any text change applied (613.1c).

    "Replacing all instances of one creature type with Vampire" rewrites the
    words *inside* the abilities, not only the subtype line -- a stolen "other
    Goblins you control get +1/+0" has to become a Vampire lord, which is the
    half of New Blood worth casting it for.

    One function because there are two readers and they must not disagree:
    `abilities_of` returns this list directly when nothing grants or removes an
    ability, and `_derived_abilities` folds it in with the granted ones when
    something does. Substituting in only the first would leave a text-changed
    permanent reverting to its old tribe the moment any `grant_ability` static
    appeared anywhere on the battlefield -- a bug that needs two cards on the
    table at once to show up.

    Pure and uncached: `text_changes` is a pipeline input, and the gate on it
    being non-empty means every card that has never been text-changed pays one
    attribute check.
    """
    printed = state.card_of(obj).abilities
    if not obj.text_changes:
        return printed
    return tuple(apply_to_ability(ability, obj.text_changes) for ability in printed)


def threshold_met(obj: GameObject, ability: Ability) -> bool:
    """Has this object the counters a station symbol asks for? (721)

    "As long as this permanent has N or more charge counters on it, it has
    [abilities]." Anywhere but the battlefield nothing is a permanent and a
    card carries no counters, so the answer there is no -- a Planet in hand
    has only its unstriated abilities, which is also what it prints.
    """
    if ability.threshold is None:
        return True
    if not obj.on_battlefield:
        return False
    counter, at_least = ability.threshold
    return obj.counter(counter) >= at_least


def present_printed_abilities(
    obj: GameObject, printed: tuple[Ability, ...]
) -> tuple[Ability, ...]:
    """The printed abilities this object actually has, with both gates applied.

    Two printed conditions on *having* an ability rather than on using it, and
    one function for both because every reader of `abilities_of` has to agree
    about them. The ability that fails either is **absent**, not refused: it is
    not offered, not a mana source for the payment solver, not collected as a
    trigger, not applied as a static, not listed for the client and not the
    AI's to consider. Refusing it in `legality` alone -- `condition`'s shape --
    would leave it a mana source, since the solver never asks legality.

    Indices must keep meaning what they printed (`Action.ability_index`,
    `StackItem.ability_index`, the per-turn trigger cap and the once-each-turn
    ledger all address an ability by position), and the two gates keep that
    promise in two ways:

    - **A Class level (716.2b-c)** swaps each ability printed above the
      object's level for its :meth:`Ability.latent` stand-in *at the same
      seat*. A Class interleaves its level lines with its gated abilities, so
      nothing could be dropped without renumbering the lines after it. Applied
      in every zone: a leaves-the-battlefield trigger is collected off the
      object after it has left (603.10a), and `GameObject.class_level` still
      holds the level it left at.
    - **A station threshold (721)** drops the ability. The loader holds those to
      the end of the list and to rising order, so below its number the list only
      ever loses a tail.

    The seat-keeping pass runs first, so it never changes the length the
    tail-dropping pass relies on.

    **Not** `stack.ability_of`'s list, and that is deliberate: an ability on the
    stack resolves whatever happens to its source (113.7a), so resolution reads
    `printed_abilities`.

    The same tuple back, untouched, for a card with neither -- every card but a
    Class or a Planet -- at the cost of one level check per ability and one
    attribute read.
    """
    level = obj.class_level
    if not all(ability.present_at(level) for ability in printed):
        printed = tuple(
            ability if ability.present_at(level) else ability.latent() for ability in printed
        )
    if not printed or printed[-1].threshold is None:
        return printed
    present = tuple(ability for ability in printed if threshold_met(obj, ability))
    return printed if len(present) == len(printed) else present


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
    those readers now asks it. Off the battlefield it is the printed list with
    only the gates of `present_printed_abilities` applied, which for every card
    in hand, on the stack and in a graveyard is the printed list.

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
    printed = present_printed_abilities(obj, printed_abilities(state, obj))
    if not obj.on_battlefield:
        return printed
    statics = _ability_statics(state)
    if not statics and not _has_op_grants(obj) and not obj.lost_all_abilities:
        return printed
    out = [ability for ability, _origin in _derived_abilities(state, obj, statics)]
    if out == list(printed):
        return printed

    return tuple(dataclasses.replace(ability, index=i) for i, ability in enumerate(out))


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
    printed = present_printed_abilities(obj, printed_abilities(state, obj))
    out: list[tuple[Ability, tuple[int, int] | None]] = []
    # `obj.lost_all_abilities` beside the static, and both mean the same thing
    # about the printed list: one is somebody else saying it continuously
    # ("enchanted creature loses all abilities"), the other is a resolving
    # effect having said it once, to this permanent, for as long as it stays
    # (The Irencrag). Either way the printed abilities are not here -- and the
    # grants below still are, which is what "loses all **other** abilities and
    # gains …" says.
    if not obj.lost_all_abilities and not any(
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
    out.extend(_op_granted_abilities(state, obj))
    return out


def _has_op_grants(obj: GameObject) -> bool:
    """Is anything on this permanent a one-shot ``grant_ability`` record?

    The cheap half of `_op_granted_abilities`, asked on `abilities_of`'s fast
    path: almost no permanent carries one, and those that do must not be
    answered with the printed list.
    """
    return any(
        temp.kind == "ability" for temp in (*obj.until_eot, *obj.granted_abilities_permanent)
    )


def granted_abilities(state: GameState, oid: int):
    """Every ability currently granted to this object, as ``(source, ability)``.

    The *granted-to* object is what triggers and legality treat as the source,
    which is what makes "whenever **this creature** deals combat damage" mean
    the creature that was granted the ability rather than the thing that granted
    it.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return
    # `left_with` is the departure snapshot: an object that has just left the
    # battlefield has had `until_eot` emptied by `reset_permanent_state`, and
    # its own leave-the-battlefield triggers have not fired yet. Empty for
    # everything else, so this reads as plain `until_eot` in every other case.
    for temp in (*obj.until_eot, *obj.granted_abilities_permanent, *obj.left_with):
        if temp.kind != "ability" or temp.ability_index is None or temp.source is None:
            continue
        source = state.objects.get(temp.source)
        if source is None:
            continue
        card = state.card_of(source)
        if temp.ability_index < len(card.grantable_abilities):
            yield source, card.grantable_abilities[temp.ability_index]


def _op_granted_abilities(
    state: GameState, obj: GameObject
) -> list[tuple[Ability, tuple[int, int]]]:
    """The abilities the `grant_ability` *op* has handed this permanent.

    Urza's Saga: "I — This Saga gains "{T}: Add {C}."" and "II — This Saga gains
    "{2}, {T}: Create a … Construct …"". A chapter resolves once and the gain
    outlives it, so the grant is a record on the permanent (`primitives.
    grant_ability`), not a static recomputed from a granter's "as long as".

    Until this, that record was read by exactly one reader -- `triggers`, through
    `granted_abilities` -- so an op-granted *activated* ability was
    held and never offered: legality, the payment solver and `game._activate`
    all read `abilities_of`, and `abilities_of` only knew the static grants.
    Appended here with the same provenance a static grant carries, so an
    activation can tell `stack.ability_of` where the definition lives (608.2).

    **Activated and static, never triggered.** An op-granted *triggered* ability
    is already yielded by `triggers.collect` off the record itself; listing it
    here too would fire it twice.

    A **static** belongs here, and the loader used to refuse one on the grounds
    that "a static handed over that way never reaches `_battlefield_statics`,
    because that walk finds statics on the derived list rather than in the grant
    record". That is exactly the list this function feeds: `abilities_of`
    appends what comes back here, `_battlefield_statics` reads `abilities_of`,
    and so a granted static joins the characteristics pipeline with no new walk
    at all. The Irencrag is the card that wanted it -- "it gains equip {3} and
    **"Equipped creature gets +3/+3"**" -- and a `grant_ability` *static* cannot
    say that line, because a static on The Irencrag is on from turn one.

    Read off the two live lists and never off ``left_with``: that is a departure
    snapshot for leave-the-battlefield triggers, and the whole point of 400.7 is
    that the object which comes back has none of it.
    """
    out: list[tuple[Ability, tuple[int, int]]] = []
    for temp in (*obj.until_eot, *obj.granted_abilities_permanent):
        if temp.kind != "ability" or temp.ability_index is None or temp.source is None:
            continue
        granter = state.objects.get(temp.source)
        if granter is None:
            continue
        pool = state.card_of(granter).grantable_abilities
        if not 0 <= temp.ability_index < len(pool):
            continue
        ability = pool[temp.ability_index]
        if not (ability.is_activated or ability.is_static):
            continue
        out.append((ability, (granter.oid, temp.ability_index)))
    return out


def granted_ability_origin(state: GameState, oid: int, index: int) -> tuple[int, int] | None:
    """Who granted the ability now sitting at ``index``, and where it lives.

    ``(granter oid, index into that granter's ``grantable_abilities``)``, or
    ``None`` when the position holds an ordinary printed ability.

    The continuous counterpart of `granted_abilities`, which answers
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
    if not statics and not _has_op_grants(obj):
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
    out.extend(_command_zone_statics(state))
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


def _command_zone_statics(state: GameState) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """Statics that work from the command zone -- eminence (702.106), and emblems.

    "As long as The Ur-Dragon is in the command zone **or on the battlefield**,
    other Dragon spells you cast cost {1} less to cast." The zone half of that
    sentence is *this function*, on `_graveyard_statics`' argument exactly: being
    gathered while the card sits there **is** the "as long as", so the clause
    needs no condition of its own, and "or on the battlefield" is then one
    static with ``active_zones: ["battlefield", "command"]`` rather than two
    abilities that would have to be kept in step.

    Without this walk the zone was unsayable and the tempting near miss was a
    battlefield-only discount, which for a nine-mana commander drops the half of
    eminence that is live for most of the game -- and drops it *silently*, since
    no authoring expectation key can observe a price.

    Read off the **printed** face for `_graveyard_statics`' reason: `abilities_of`
    resolves grants and losses against the battlefield and has nothing to say
    about an object that is not there. An emblem (114.3) is abilities and
    nothing else, so the printed face is all it ever had.

    Appended last, after the battlefield and graveyard walks, because this list's
    order is the order effects apply in and an object here has no battlefield
    timestamp to sort against.

    **The source may be the spell being priced.** A commander is cast *out of*
    this zone, and `Game._cast` reads `cost_reduction` while `obj.zone` is still
    `COMMAND` -- so the eminence static is collected against its own card. That
    is what "other" is for, and `spell_cost_reduction` spends it.
    """
    out: list[tuple[GameObject, Mapping[str, Any]]] = []
    for player in state.players:
        for oid in player.command:
            obj = state.objects.get(oid)
            if obj is None:
                continue
            for ability in state.card_of(obj).abilities:
                if not (ability.is_static and ability.static):
                    continue
                if Zone.COMMAND not in ability.active_zones:
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


#: The player spec in a static condition that names the controller of **the
#: permanent the static is being applied to**, not the static's source.
#:
#: Fall from Favor: "Enchanted creature doesn't untap during its controller's
#: untap step unless *that player* is the monarch." Every other spec is measured
#: from the source's controller, and on an Aura that is whoever cast it -- the
#: Aura's controller made themselves the monarch on arrival, so
#: `{"is_monarch": "you"}` would read as "the hold lifts while the *caster* is the
#: monarch", which is the opposite card: the creature stays frozen exactly while
#: its own controller has stolen the crown back.
#:
#: Asked per affected permanent, so only a reader that walks them one at a time
#: can answer it -- `player_statics.untap_held`. The loader admits it only on
#: the effects in `STATIC_AFFECTED_CONDITION_EFFECTS`, and `_static_active`
#: defers a condition naming it when no permanent is in hand.
AFFECTED_CONTROLLER = "affected_controller"


def static_condition_names_affected(cond: Any) -> bool:
    """Does this static condition tree name `AFFECTED_CONTROLLER` anywhere?"""
    if not isinstance(cond, Mapping):
        return False
    if cond.get("is_monarch") == AFFECTED_CONTROLLER:
        return True
    if "not" in cond:
        return static_condition_names_affected(cond["not"])
    for head in ("all", "any"):
        if head in cond:
            return any(static_condition_names_affected(c) for c in cond[head] or ())
    return False


def static_condition_reads_derived(cond: Any) -> bool:
    """Does this static condition tree read derived characteristics anywhere?

    `exists_derived` -- see `loader.vocabulary.STATIC_DERIVED_CONDITION_EFFECTS`.
    """
    if not isinstance(cond, Mapping):
        return False
    if "exists_derived" in cond:
        return True
    if "not" in cond:
        return static_condition_reads_derived(cond["not"])
    for head in ("all", "any"):
        if head in cond:
            return any(static_condition_reads_derived(c) for c in cond[head] or ())
    return False


def _static_active(
    state: GameState,
    source: GameObject,
    static: Mapping[str, Any],
    affected: GameObject | None = None,
) -> bool:
    """Is this static's "as long as..." clause currently true?

    ``affected`` is the permanent the static is being applied to, for the one
    spec that needs it (`AFFECTED_CONTROLLER`). Without one, a condition naming
    that spec is **deferred** -- reported active -- because the static-wide walks
    (`_battlefield_statics` and its twins) have no permanent to ask about, and
    the per-permanent reader asks again with each. The whole tree is deferred,
    not just the leaf, so a ``not`` or an ``all`` around it is evaluated once,
    correctly, by that reader.
    """
    condition = static.get("condition")
    if not condition:
        return True
    # A condition reading derived characteristics is deferred on the same
    # terms, and it is what keeps the pipeline acyclic: every walk inside
    # `chars` asks with no permanent, so `exists_derived` is only ever
    # evaluated by `attack_forbidden` and `block_forbidden`, outside it.
    if affected is None and (
        static_condition_names_affected(condition) or static_condition_reads_derived(condition)
    ):
        return True
    return _condition_met(state, source, condition, affected)


def _condition_met(
    state: GameState, source: GameObject, cond: Any, affected: GameObject | None = None
) -> bool:
    """Evaluate a static's condition tree.

    A deliberately smaller language than :func:`commanderblitz.engine.effects.conditions.evaluate`
    -- see the module docstring.  Every leaf here reads a pipeline *input*, so
    nothing it can ask depends on a static's output:

    ``counters``      how many counters of a kind sit on the static's own source
    ``exists``/``cmp`` over ``{"count": filter}``, matched on printed
                      characteristics and, off the battlefield, on zone contents
    ``is_your_turn``  whose turn it is
    ``has_flag``      a word `set_flag` wrote on the static's own source
    ``is_monstrous``  whether the static's own source is monstrous (701.37b)
    ``is_monarch``    who holds the crown -- the only leaf that may name the
                      ``affected`` permanent's controller (`AFFECTED_CONTROLLER`)
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
        return all(_condition_met(state, source, c, affected) for c in cond["all"])
    if "any" in cond:
        return any(_condition_met(state, source, c, affected) for c in cond["any"])
    if "not" in cond:
        return not _condition_met(state, source, cond["not"], affected)
    if "exists" in cond:
        return _count_matching(state, cond["exists"], source) > 0
    if "exists_derived" in cond:
        # Rhonas's "unless you control another creature with power 4 or
        # greater": current power, pumps and counters included. Only reached
        # with a permanent in hand -- `_static_active` defers it otherwise --
        # which is to say only outside the pipeline.
        if affected is None:
            raise DslError("static condition 'exists_derived' asked inside the pipeline")
        spec = cond["exists_derived"] or {}
        return any(
            (obj := state.objects.get(oid)) is not None
            and _matches(state, obj, source, spec, derived=True)
            for oid in state.battlefield
        )
    if "is_your_turn" in cond:
        return (state.active_player == source.controller) == bool(cond["is_your_turn"])
    if "has_flag" in cond:
        # A Siege's "as this enters, choose Mardu or Jeskai" switching on the
        # chosen mode's static. `flags` is written only by `set_flag` (which
        # bumps `char_version`) and cleared only by a zone change, so it is a
        # pipeline *input* as counters are, and reading it keeps ADR 0001's
        # fixed order acyclic. Not a copiable value (707.2), so a copy of the
        # source has made no choice and has no mode on.
        return str(cond["has_flag"]) in source.flags
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
    if "is_monstrous" in cond:
        # "As long as this creature is monstrous, it has hexproof and
        # indestructible" (Fleecemane Lion). `GameObject.monstrous` is written
        # only by the `monstrosity` op, which bumps `char_version`, and cleared
        # only by a zone change (400.7), so it is a pipeline *input* exactly as
        # a counter is. Not the +1/+1 counter it arrives with: that counter can
        # come from anywhere and be removed, and being monstrous survives both
        # (701.37b). Not a copiable value (707.2), so a copy is not monstrous.
        return source.monstrous == bool(cond["is_monstrous"])
    if "has_city_s_blessing" in cond:
        # Player state, so a pipeline *input* exactly as a zone count is:
        # nothing in the fixed-order characteristics pipeline can change whether
        # a player has the blessing, so no static can come to depend on another
        # static's output through it.
        pids = _static_players(state, source, cond["has_city_s_blessing"])
        return any(state.players[p].has_city_s_blessing for p in pids)
    if "is_monarch" in cond:
        # Player state, a pipeline input on `has_city_s_blessing`'s terms, and
        # the two routes that move the crown bump `char_version`. `any`, as on
        # the effect side: the monarchy is never true of two players at once.
        who = cond["is_monarch"]
        if who == AFFECTED_CONTROLLER:
            if affected is None:
                raise DslError(
                    f"static condition {{'is_monarch': {AFFECTED_CONTROLLER!r}}} asked "
                    "with no affected permanent"
                )
            return state.monarch == affected.controller
        return state.monarch is not None and state.monarch in _static_players(state, source, who)
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


def compare_pt(value: int, spec: Any) -> bool:
    """A filter's ``power``/``toughness`` clause: ``{"op": ">=", "value": 4}``.

    The same spelling `selectors._compare` and `triggers._compare` already take,
    down to the defaulted ``">="`` and the bare-integer shorthand for equality,
    because the three are one printed clause asked in three places and a static
    filter with a dialect of its own is one more thing to remember wrongly.

    ``value`` is a plain integer rather than a value expression: the static
    value language needs a source permanent to measure against, and this is a
    per-object test that has only the object.  The loader enforces that, so a
    non-integer reaching here means the two languages have drifted.

    Exported unmangled because `cost_reduction._object_matches` -- the reader of
    this key that runs *outside* the pipeline, against derived characteristics
    -- has to spell the comparison the same way this one does.
    """
    if isinstance(spec, bool):
        raise DslError(f"bad power/toughness comparison {spec!r}")
    if isinstance(spec, int):
        return value == spec
    if not isinstance(spec, Mapping):
        raise DslError(f"bad power/toughness comparison {spec!r}")
    return _compare(str(spec.get("op", ">=")), value, int(spec.get("value", 0)))


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
    :func:`commanderblitz.cards.loader.statics._validate_static_value`, so an unknown leaf means
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
    if "times" in expr:
        # "+2/+2 for each Equipment you control" -- Swordsman's Steel. A count
        # with a step bigger than one, which the language could not say: every
        # other leaf here *measures* something and nothing combined two.
        #
        # Splitting the doubling across two `buff` statics is not the
        # alternative it looks like. A static may carry no `effects`, so it
        # would have to be two abilities, and the residual gate asks which
        # printed line each ability claims -- two abilities claiming one
        # sentence is exactly what that gate exists to catch.
        #
        # Deliberately the same spelling and the same shape as the effect-side
        # `times`: a list of factors, multiplied. Safe here for `count`'s
        # reason, since every factor it can contain is a pipeline input.
        result = 1
        for factor in expr["times"]:
            result *= _static_value(state, factor, source)
        return result
    if "sum" in expr:
        # "At least 7 life more than your starting life total" (Righteous
        # Valkyrie) -- a threshold offset from a measured number. The effect-side
        # `sum`, with every term held to this language by the loader.
        return sum(_static_value(state, term, source) for term in expr["sum"])
    if "starting_life_of" in expr:
        # Rule 103.4, recorded on the seat when the game began. A pipeline
        # input on the strongest terms there are: nothing writes it after that.
        pids = _static_players(state, source, expr["starting_life_of"])
        return sum(state.players[p].starting_life for p in pids)
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
    if "greatest_commander_mana_value" in expr:
        # Tangleweave Armor: "+X/+X, where X is the greatest mana value among
        # your commanders." Read off the commander's printed card wherever it is
        # -- the command zone most of the game -- which no selector reaches, and
        # 0 for a seat with no commander. A printed mana cost is a pipeline
        # input on `mana_symbols`' terms, so the anthem cannot come to depend on
        # another static's output.
        pids = _static_players(state, source, expr["greatest_commander_mana_value"])
        return max(
            (
                state.card_of(obj).mana_value
                for pid in pids
                for oid in state.commanders_of(pid)
                if (obj := state.objects.get(oid)) is not None
            ),
            default=0,
        )
    if "extreme_value" in expr:
        # Dragon Man, Reformed Robot: "power is equal to the greatest mana value
        # among noncreature permanents you control and noncreature cards in your
        # graveyard." The printed mana value off each object a counting filter
        # finds, `union` joining a filter per zone -- an object in two branches
        # counts once, and an empty pool is 0. A printed mana cost is a pipeline
        # input on `mana_symbols`' terms.
        spec = expr["extreme_value"]
        objects = spec.get("objects") or {}
        branches = objects.get("union", [objects])
        pool = {
            obj.oid: obj for branch in branches for obj in _matching_objects(state, branch, source)
        }
        values = [state.card_of(obj).mana_value for obj in pool.values()]
        if not values:
            return 0
        return max(values) if spec.get("pick", "greatest") == "greatest" else min(values)
    if "min_life_of" in expr:
        pids = _static_players(state, source, expr["min_life_of"])
        return min_life([state.players[p].life for p in pids])
    if "max_life_of" in expr:
        pids = _static_players(state, source, expr["max_life_of"])
        return max([state.players[p].life for p in pids], default=0)
    if "max_poison_of" in expr:
        # Corrupted. A poison count is a pipeline input on a life total's terms:
        # only `primitives.add_poison` writes one, nothing in this pipeline can,
        # and that funnel bumps `char_version` so the condition is re-read.
        pids = _static_players(state, source, expr["max_poison_of"])
        return max((state.players[p].poison for p in pids), default=0)
    if "unspent_mana_count" in expr:
        # Omnath, Locus of the Void: "+1/+1 for each unspent mana you have."
        # Every mana in the pool, restricted pips included -- unspent is not
        # "spendable on this". The pool is player state, a pipeline input on a
        # poison count's terms: no layer writes it, and every funnel that does
        # (`costs.pay_mana`, `costs.activate_mana_ability`, the `add_mana` ops,
        # `GameState.empty_all_mana_pools`, a player leaving) bumps
        # `char_version`, so the anthem is re-read as the pool moves.
        pids = _static_players(state, source, expr["unspent_mana_count"])
        return sum(state.players[p].mana_pool.total() for p in pids)
    if "spells_cast_this_turn" in expr:
        # Captain Mar-Vell, Space-Born: "As long as an opponent has cast a spell
        # this turn, you may cast spells as though they had flash." The turn
        # ledger's per-seat cast count, the effect side's storm leaf in its
        # bare player-spec form. A pipeline input: `GameState._tally` writes it
        # off SPELL_CAST and the cleanup step empties it, no layer touches it,
        # and both bump `char_version`, so a cached answer cannot outlive the
        # cast that changed it or the turn that ended it.
        pids = _static_players(state, source, expr["spells_cast_this_turn"])
        return sum(state.turn_ledger.spells_cast.get(p, 0) for p in pids)
    if "creatures_died_this_turn" in expr:
        # Gorma, the Gullet: "...for each creature that died under your control
        # this turn." The effect side's morbid leaf, keyed by the creature's
        # controller as it died, so "you" is the source's controller's dead.
        # A pipeline input on `spells_cast_this_turn`'s terms: `_tally` writes
        # it off DIES, the cleanup step empties it, and no layer touches it.
        pids = _static_players(state, source, expr["creatures_died_this_turn"])
        return sum(state.turn_ledger.creatures_died.get(p, 0) for p in pids)
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
                not_types=spec.get("not_types") or (),
                subtypes=spec.get("subtypes") or (),
                colors=spec.get("colors") or (),
                is_token=spec.get("is_token"),
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
            for obj in _matching_objects(state, spec.get("objects") or {"self_only": True}, source)
        )
    raise DslError(f"unknown static value {sorted(expr)}")


def _counts_per_player(state: GameState, spec: Mapping[str, Any], source: GameObject) -> list[int]:
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


def resolve_chosen_subtype_list(entries: Any, source: GameObject | None) -> list[str]:
    """Literal subtype names, with ``{"chosen_type_of": "self"}`` substituted.

    The leaf-level half of :func:`resolve_chosen_subtypes`, split out for the
    reason its colour twin was: one reader wants the plain list and not a
    selector. That reader is the layer-4 ``add_subtype`` grant -- "this creature
    is **the chosen type** in addition to its other types" (Roaming Throne,
    Arcane Adaptation, Xenograft) -- where the entry is the thing being *given*
    rather than a test something has to pass.

    A source that has chosen nothing yet contributes **nothing** -- the entry is
    dropped, so the Throne is of no extra type until its controller names one,
    and becomes that type the moment they do. The selector wrapper turns the
    same emptiness into a match-nothing sentinel instead, because a filter's
    ``subtypes`` is an any-of and an empty one would match everything.
    """
    out: list[str] = []
    for entry in entries or ():
        if not isinstance(entry, Mapping):
            out.append(entry)
            continue
        if entry.get("chosen_type_of") != "self":
            continue
        chosen = source.chosen_type if source is not None else None
        if chosen is not None:
            out.append(chosen)
    return out


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
    everybody. The sentinel replaces the *whole* list rather than just the
    unresolved entry, because ``subtypes`` is an any-of: "Goblins and the chosen
    type" with no choice made yet must not quietly fall back to "Goblins".

    ``not_subtypes`` takes the same entry -- "destroy all creatures that
    **aren't** of the chosen type" (Kindred Judgment) -- and fails the same
    way: with no choice made the filter matches nothing. Dropping the entry
    instead would make "aren't of the chosen type" read "every creature".
    """
    unresolved = False
    for key in ("subtypes", "not_subtypes"):
        wanted = selector.get(key)
        if not wanted or not any(isinstance(s, Mapping) for s in wanted):
            continue
        out = resolve_chosen_subtype_list(wanted, source)
        if len(out) != len(wanted):
            unresolved = True
        selector = {**selector, key: out}
    if unresolved:
        return {**selector, "subtypes": ["\0none"]}
    return selector


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


def resolve_chosen_card_type_list(entries: Any, source: GameObject | None) -> list[str]:
    """Literal card types, with ``{"chosen_card_type_of": "self"}`` substituted.

    The card-type twin of :func:`resolve_chosen_color_list`, for the readers
    whose ``from_types`` is a list of protection qualities rather than a
    filter -- "protection from **the chosen card type**" (Serra's Emissary).
    The choice is the source's `chosen_card_type`, written by `choose_type`'s
    ``permanent_type`` and ``card_type`` axes and never by its creature-type
    one, so a creature type can never leak in as a card type.

    A source that has chosen nothing yet contributes **nothing**: protection
    from the chosen card type before a type is named is protection from
    nothing, which is the only reading in which the window between the
    permanent arriving and its choice resolving grants nobody anything.
    """
    out: list[str] = []
    for entry in entries or ():
        if not isinstance(entry, Mapping):
            out.append(entry)
            continue
        if entry.get("chosen_card_type_of") != "self":
            continue
        chosen = source.chosen_card_type if source is not None else None
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


def recorded_subtypes(obj: GameObject) -> tuple[str, ...]:
    """The subtypes written onto ``obj`` "in addition to its other types".

    `GameObject.added_subtypes` -- the one-shot with no clock -- and every
    ``subtype`` `TempEffect` still standing: "until end of turn, Sarkhan becomes
    a Dragon in addition to its other types". Both are pipeline *inputs*, so
    `_compute` and a static's filter read them alike; a Dragon lord's anthem
    reaches a Sarkhan that is a Dragon for the turn, as it reaches a Vampire
    Captivating Vampire converted.
    """
    timed = tuple(
        sub for temp in obj.until_eot if temp.kind == "subtype" for sub in temp.subtypes
    )
    return obj.added_subtypes + timed if timed else obj.added_subtypes


def _matches_printed(
    card: CardDef,
    selector: Mapping[str, Any],
    added_subtypes: tuple[str, ...] = (),
    text_changes: tuple[tuple[str, str], ...] = (),
    x: int = 0,
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

    ``text_changes`` is the second, admitted on the same argument and for the
    same kind of card.  It is layer 3 (613.1c) and it *rewrites* the printed
    line rather than adding to it, so it is applied to `card.subtypes` before
    the added ones are unioned in -- a Goblin changed to Vampire is no longer a
    Goblin here, which is the whole difference between New Blood and Captivating
    Vampire.  Without it `chars()` would report the new type line and every
    static filter in the game would still see the old one, so New Blood would
    convert a creature that no Vampire lord could find: the card would look
    implemented and do almost nothing.
    """
    # "**Artifact cards and red creature cards** in your hand have warp {2}{R}"
    # -- Tannuk, Steadfast Second. A disjunction, and the only way to say one
    # here: every other key below is ANDed, so the two printed shapes written
    # as one filter collapse to "red artifact creature" and the sentence is
    # unsayable. `any_types` is an or over *types* alone and would let a blue
    # creature card through.
    #
    # A branch is the same filter language asked about the same card, exactly
    # as `cost_reduction._object_matches` recurses for its own `any_of` and as
    # the effect-side selector does. `grant_warp` writes the word here, and so
    # may a static's `affects` (`STATIC_AFFECTS_FILTER_KEYS`) when a reader
    # matches it against a face alone; on the battlefield `_matches_wherever`
    # answers the union first, with board state, and never reaches this.
    # `SPELL_FILTER_KEYS` does not carry it.
    if (branches := selector.get("any_of")) is not None and not any(
        _matches_printed(card, branch, added_subtypes, text_changes) for branch in branches
    ):
        return False
    types = selector.get("types")
    if types and not set(types).issubset(card.types):
        return False
    # `types` is a conjunction -- `issubset` above -- which is right for
    # "artifact creature" and useless for "instant or sorcery": no card is both,
    # so ["Instant", "Sorcery"] loads clean and matches nothing at all. The
    # selector language has always had `any_types` for the or-of-types question
    # and the *static* filters did not, so Archmage of Runes' "instant and
    # sorcery spells you cast cost {1} less" was unsayable -- and the tempting
    # spelling of it, a `not_types` complement, silently widens to every
    # noncreature spell.
    any_types = selector.get("any_types")
    if any_types and not (set(any_types) & card.types):
        return False
    not_types = selector.get("not_types")
    if not_types and set(not_types) & card.types:
        return False
    subtypes = selector.get("subtypes")
    if subtypes:
        printed = apply_text_changes(set(card.subtypes), text_changes)
        if not (set(subtypes) & (printed | set(added_subtypes))):
            return False
    supertypes = selector.get("supertypes")
    if supertypes and not set(supertypes).issubset(card.supertypes):
        return False
    # "**Nonbasic** lands don't untap during their controllers' untap steps"
    # (Back to Basics). The negated form, which the effect-side selector
    # language always had and the static one did not -- the same asymmetry
    # `not_keywords` above was added to close. A complement over `types` is not
    # a spelling of it: `not_types: ["Land"]` is every permanent that is not a
    # land, which is the opposite set.
    not_supertypes = selector.get("not_supertypes")
    if not_supertypes and set(not_supertypes) & set(card.supertypes):
        return False
    colors = selector.get("colors")
    if colors and not (set(colors) & card.colors):
        return False
    # "…a **multicolored** instant or sorcery spell" (202.2b: a card with two
    # or more colors). `colors` is a membership test and says something else
    # entirely -- `["U", "R"]` matches a mono-blue spell -- so this is its own
    # clause rather than a spelling of that one.
    if (least := selector.get("min_colors")) is not None and len(card.colors) < int(least):
        return False
    # "**Colorless** creatures you control get +2/+2" (Forsaken Monument):
    # zero colours, 105.2c. Printed, like `colors` one clause up -- a static
    # filter may not read a colour another static writes.
    if selector.get("colorless") and card.colors:
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
    # "…with mana cost {0} or {1}." The printed cost, symbol for symbol -- see
    # `mana.printed_cost_is`. As printed as a name, so no layer can move it.
    wanted_cost = selector.get("mana_cost")
    if wanted_cost is not None and not printed_cost_is(card.mana_cost, wanted_cost):
        return False
    # "Your opponents can't cast spells with **mana value 3 or less**" --
    # Brisela, Voice of Nightmares. The selector language's comparison shape,
    # `{"op": "<=", "value": 3}`, with a literal number, because a printed face
    # has no context to evaluate anything richer against. Only a
    # `cant_cast_spells` filter may write it (`CAST_LOCK_FILTER_KEYS`), and
    # that reader passes ``x``: 202.3e counts the X a spell on the stack was
    # cast with, so a Fireball cast for X = 3 has mana value 4.
    if (wanted_mv := selector.get("mana_value")) is not None and not _compare_printed(
        card.mana_value + x * card.mana_cost.x_count, wanted_mv
    ):
        return False
    return True


def _compare_printed(value: int, spec: Any) -> bool:
    """The static twin of `effects.selectors._compare`, over literal numbers only."""
    if isinstance(spec, int):
        return value == spec
    other = int(spec.get("value", 0))
    op = spec.get("op", ">=")
    if op == ">=":
        return value >= other
    if op == "<=":
        return value <= other
    if op == ">":
        return value > other
    if op == "<":
        return value < other
    if op in ("=", "=="):
        return value == other
    if op == "!=":
        return value != other
    raise ValueError(f"unknown comparison operator {op!r}")


def has_any_counter(obj: GameObject) -> bool:
    """Does ``obj`` have one or more counters of any kind on it (122.1)?"""
    return any(n > 0 for n in obj.counters.values())


def enchanted_by(state: GameState, oid: int, spec: Any, controller: int) -> bool:
    """The ``enchanted_by`` filter key: is ``oid`` enchanted, by whose Aura?

    "Destroy all creatures that **aren't enchanted**" (Winds of Rath),
    "each creature that's **enchanted by an Aura you control**" (Eriette of the
    Charmed Apple). A permanent is enchanted when an Aura is attached to it
    (303.4); ``spec`` is ``true`` (one or more Auras, anybody's), ``false``
    (none at all) or ``{"controller": "you" | "opponent" | "any"}``, which asks
    for one or more Auras whose controller stands that way to ``controller`` --
    the player the filter is read for. A player's Curse is attached to a seat,
    not to a permanent, and enchants no permanent.

    Answered by walking the battlefield for attachments, because attachment is
    stored one way -- on the Aura, as `attached_to` -- the walk `modified`
    makes in `selectors._is_modified`. An Aura is told by its printed face or by
    being cast bestowed (702.103b), the test `stack` attaches by and `sba` bins
    by, rather than by `chars`: every part of the answer -- `attached_to`, the
    Aura's controller, its printed type line, the bestow stamp -- is a pipeline
    **input**, so a static's filter can read it without depending on another
    static's output (ADR 0001).
    """
    return enchanted_by_answer(aura_controllers(state, oid), spec, controller)


def aura_controllers(state: GameState, oid: int) -> list[int]:
    """Who controls each Aura attached to ``oid`` right now, one seat per Aura.

    The one place an Aura is told from any other attachment, for both readers of
    "enchanted": `enchanted_by` asks it of a permanent on the battlefield, and
    `zones.move_object` asks it of a permanent that is leaving, before
    `_detach_all` unattaches everything, and puts the answer on the departure
    event as ``had_auras`` -- the last-known information (603.10a) that "whenever
    an enchanted creature dies" and "for each Aura you controlled that was
    attached to it" (Hateful Eidolon) read once the Auras have fallen off.
    """
    seats: list[int] = []
    for aura_oid in state.battlefield:
        aura = state.objects.get(aura_oid)
        if aura is None or aura.attached_to != oid:
            continue
        if not (state.card_of(aura).is_aura or aura.cast_bestowed):
            continue
        seats.append(aura.controller)
    return seats


def auras_matching(seats: Any, spec: Any, controller: int) -> int:
    """How many of ``seats`` (one per Aura) a `enchanted_by`-shaped ``spec`` names.

    ``spec`` is ``true`` or ``{"controller": "you" | "opponent" | "any"}``,
    relative to ``controller``. Shared by the live answer and the departure
    snapshot so the two readings of "an Aura you control" cannot drift.
    """
    want = spec.get("controller", "any") if isinstance(spec, Mapping) else "any"
    if want == "you":
        return sum(1 for seat in seats if seat == controller)
    if want == "opponent":
        return sum(1 for seat in seats if seat != controller)
    return len(seats)


def enchanted_by_answer(seats: Any, spec: Any, controller: int) -> bool:
    """The ``enchanted_by`` verdict for a host whose Auras' controllers are ``seats``."""
    found = auras_matching(seats, spec, controller) > 0
    return found if spec is not False else not found


def _matches(
    state: GameState,
    obj: GameObject,
    source: GameObject,
    selector: Mapping[str, Any] | None,
    *,
    derived: bool = False,
) -> bool:
    """Match ``obj`` against a static ability's filter, using printed characteristics.

    A deliberately smaller language than the full selector DSL in
    :mod:`commanderblitz.engine.effects.selectors` -- see the module docstring for why.

    ``derived`` reads the object's characteristics off :func:`chars` instead --
    its types, subtypes, supertypes, keywords, colours and power/toughness after
    every layer. Only a reader **outside** the layer pipeline may ask for it,
    because :func:`chars` is what the pipeline computes; the readers that do are
    the rule-modifying statics, which no layer applies: an attack requirement
    (`attacks_if_able`) and a block restriction (`block_restriction`, both its
    `affects` and its `blockers`). "Juggernauts you control attack each combat if
    able" (Graaz, Unstoppable Juggernaut) has to see the creatures Graaz's own
    third line makes Juggernauts, and rule 613 has nothing to order there --
    neither effect is a layer, so reading layer 4's output is no loop.
    """
    if selector is None:
        return False
    if not obj.on_battlefield:
        return False
    return _matches_wherever(state, obj, source, selector, derived=derived)


def _matches_wherever(
    state: GameState,
    obj: GameObject,
    source: GameObject,
    selector: Mapping[str, Any],
    *,
    derived: bool = False,
) -> bool:
    """`_matches` without the battlefield gate -- for an object that is *arriving*.

    Split off rather than given a flag, because the gate is not a detail of the
    match: every caller in the layer pipeline walks `state.battlefield` and so
    could never see anything else, and the one caller that needs this is asking
    a different question -- "would this static describe the permanent that is
    about to exist?" -- a moment before the zone change makes it answerable the
    ordinary way.  `keyword_as_it_enters` is that caller and says why.

    The board-state clauses below (`tapped`, `attacking`, `entered_this_turn`)
    read a permanent that is not one yet, so they answer with the arrival's
    blank slate.  That is right for a creature on its way in -- it is untapped,
    unblocking and has entered nothing -- and it is why this is not a public
    door onto the filter language: it is exact only for the questions asked
    *during* an arrival.
    """
    # "Skeletons you control and **other** Zombies you control get +1/+1"
    # (Death Baron). A union of whole filters, and the reason it is answered
    # here rather than left to `_matches_printed`'s own `any_of`: that one sees
    # the printed face alone, and this sentence's two halves differ in
    # `exclude_self`, which is a relation to the source. Each branch is the
    # outer filter with the branch's keys added -- the loader refuses a branch
    # that repeats an outer key, so adding never replaces -- and the object
    # matches the union once however many branches describe it, which is the
    # whole difference from two statics: a Skeleton Zombie gets +1/+1, not +2/+2.
    if (branches := selector.get("any_of")) is not None:
        outer = {k: v for k, v in selector.items() if k != "any_of"}
        return any(
            _matches_wherever(state, obj, source, {**outer, **branch}, derived=derived)
            for branch in branches
        )

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
    # "…as long as two or more Equipment are **attached to it**" (Brass
    # Knuckles); "+2/+2 for each Aura and Equipment **attached to it**" (Strong
    # Back). `attached` is the host and this is its other attachments -- the two
    # halves of one relationship, read from opposite ends.
    #
    # It does **not** short-circuit, because every card that prints it also
    # narrows by subtype: matching every attachment would count the Aura that
    # says so beside the Equipment it is asking about. It does suppress the
    # default `controller: "you"` the way `attached` does, and for the same
    # reason: the equipped creature may be an opponent's, and the printed line
    # asks what is attached to it rather than who controls what.
    #
    # The source counts itself when it qualifies, which is the printed reading:
    # Brass Knuckles is one of the Equipment attached to the creature, so "two
    # or more" is itself plus one.
    attached_to_host = bool(selector.get("attached_to_host"))
    if attached_to_host and (
        source.attached_to is None or obj.attached_to != source.attached_to
    ):
        return False
    # "…for each Aura you control **that's attached to a creature**" (Sage's
    # Reverie); "+2/+2 for each Aura **attached to it**" (Kor Spiritdancer).
    # `enchanted_by` read from the attachment's end: the permanent this one is
    # attached to is matched by a filter of its own, in this same language, so
    # `self_only` there is the static's own source. Its controller defaults to
    # anybody's -- the printed line names the host by what it is -- and so does
    # the attachment's, for `attached_to_host`'s reason: Kor Spiritdancer counts
    # the opponent's Pacifism on it. Both ends are pipeline inputs: `attached_to`
    # is written by `attach` alone, and the host filter reads what this one does.
    host_filter = selector.get("attached_to")
    if host_filter is not None:
        host = state.objects.get(obj.attached_to) if obj.attached_to is not None else None
        if host is None or not _matches(
            state, host, source, {"controller": "any", **host_filter}, derived=derived
        ):
            return False
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
    controller = selector.get(
        "controller", None if owner or attached_to_host or host_filter is not None else "you"
    )
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

    if derived:
        # The face the filter reads becomes the derived one: `chars` has
        # already applied the text changes and every subtype grant, so neither
        # is passed again.
        c = chars(state, obj.oid)
        face = dataclasses.replace(
            card,
            types=c.types,
            subtypes=c.subtypes,
            supertypes=c.supertypes,
            keywords=c.keywords,
            colors=c.colors,
        )
        if not _matches_printed(face, selector):
            return False
        size = (c.power, c.toughness)
    else:
        if obj.cast_bestowed and obj.attached_to is not None and obj.on_battlefield:
            # Bestow (702.103b): while attached it is an Aura enchantment and no
            # creature. `_compute` makes the same change under the identical
            # condition, and every half of it is a pipeline input, so the face
            # this filter reads may make it too: "each Aura attached to it"
            # counts a bestowed Spirit, and "creatures you control" does not.
            card = dataclasses.replace(
                card,
                types=(card.types - {"Creature"}) | {"Enchantment"},
                subtypes=card.subtypes | {"Aura"},
            )
        if not _matches_printed(card, selector, recorded_subtypes(obj), obj.text_changes):
            return False
        size = None

    # "…each creature you control **with power 4 or greater**" (Temur
    # Battlecrier), and the rest of the ferocious family. The one derived
    # characteristic this filter language may name, read at `_base_pt` -- the
    # size before any layer -- and never through `chars`, which this function is
    # called from and would recurse into. The module docstring argues the
    # restriction; `_base_pt` is the whole of it.
    # A `derived` reader is outside the pipeline and reads the real size.
    if (spec := selector.get("power")) is not None and not compare_pt(
        (size or _base_pt(state, obj))[0], spec
    ):
        return False
    if (spec := selector.get("toughness")) is not None and not compare_pt(
        (size or _base_pt(state, obj))[1], spec
    ):
        return False

    if "tapped" in selector and bool(obj.tapped) != bool(selector["tapped"]):
        return False
    # "Permanents you control **with counters on them** have ward {1}"
    # (Innkeeper's Talent). Counters are board state no layer writes -- a
    # static never puts one on -- so this is a pipeline input for `tapped`'s
    # reason, and the answer moves the moment a counter arrives or leaves.
    if "has_counters" in selector and has_any_counter(obj) != bool(selector["has_counters"]):
        return False
    # "Each creature that's **enchanted by an Aura you control**" (Eriette of
    # the Charmed Apple). Attachment is board state no layer writes, so it is a
    # pipeline input for `has_counters`' reason; `enchanted_by` says why every
    # half of it is. "You" is the static's controller.
    if "enchanted_by" in selector and not enchanted_by(
        state, obj.oid, selector["enchanted_by"], source.controller
    ):
        return False
    if "is_commander" in selector and bool(obj.is_commander) != bool(selector["is_commander"]):
        return False
    if "is_token" in selector and bool(obj.is_token) != bool(selector["is_token"]):
        return False

    # "…a creature you control **that entered this turn**" (Neriv, Heart of the
    # Storm); "as long as **it** entered this turn" (Zurgo and Ojutai). Read off
    # the turn ledger rather than off `obj.entered_turn`, and the two are not the
    # same question: `entered_turn` is what `summoning_sick` reads and
    # `change_control` stamps it, because 302.6 makes a stolen permanent sick
    # without its having entered anything. `TurnLedger.entered_this_turn` says
    # why at length.
    #
    # A pipeline *input* -- an arrival snapshot is written once, by `emit`, and
    # no layer can write to it -- so it sits here beside `tapped` and `is_token`
    # rather than outside the static filter language.
    if "entered_this_turn" in selector and bool(
        state.turn_ledger.entered_this_turn(obj.oid)
    ) != bool(selector["entered_this_turn"]):
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


def keyword_as_it_enters(state: GameState, oid: int, keyword: str) -> bool:
    """Would the permanent now *arriving* have ``keyword`` once it is there?

    Riot (702.113) is the only caller and the reason this exists. `chars` cannot
    answer it: the object is still on the stack (or in a graveyard, or in a
    hand), so the layer pipeline sees a card rather than a permanent and no
    battlefield static reaches it. Waiting until it *is* a permanent is not an
    option either -- by then `zones._enter_battlefield` has run, and the whole
    content of riot is that the choice was made **as** the creature entered.

    So the two halves of "has riot" are asked here, a moment before the move:

    * the **printed** keyword, off the face that is actually arriving --
      Zegana, Utopian Speaker and the rest of the cycle; and
    * a `grant_keyword` static on the battlefield whose `affects` describes the
      arriving object -- Rhythm of the Wild's "nontoken creatures you control
      have riot", which is riot's commonest printing and the reason it had to
      be a grantable keyword rather than a replacement.

    The granters are read through `_battlefield_statics`, so a granter that has
    lost its abilities, or whose own `condition` is unmet, grants nothing --
    the same walk every layer uses. What is *matched* goes through
    `_matches_wherever`, which is `_matches` minus the battlefield gate the
    arriving object cannot pass yet.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    # 707.2: a permanent arriving face down has no abilities at all, so it has
    # no printed riot -- and nothing on the board can see a keyword on it
    # either. The same exemption `move_object` makes for Mox Diamond, written
    # the same way, because `face_down` is only set after the move.
    if obj.pending_face_down:
        return False
    if keyword in state.card_of(obj).keywords:
        return True
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "grant_keyword":
            continue
        if keyword not in static.get("keywords", ()):
            continue
        affects = static.get("affects")
        # `None` matches nothing, exactly as `_matches` decides: the loader
        # requires `affects` on a `grant_keyword`, so this is the same
        # fail-closed answer rather than a filter that quietly means "everyone".
        if affects is not None and _matches_wherever(state, obj, source_obj, affects):
            return True
    return False


def prevented_damage(state: GameState, oid: int, *, is_combat: bool = False) -> int:
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
        if static.get("combat_only") and not is_combat:
            continue
        if static.get("prevent_all"):
            # A total shield is answered by `prevents_all_damage` below, not by
            # a number here. Skipped rather than summed as 0, so the two never
            # meet: `amount` is absent on such a static and `_static_value`
            # would read it as 0 and contribute nothing anyway.
            continue
        total += _static_value(state, static.get("amount"), source_obj)
    return total


def prevents_all_damage(state: GameState, oid: int, *, is_combat: bool = False) -> bool:
    """Whether **all** damage to this permanent is prevented.

    "Prevent all damage that would be dealt to other attacking Soldiers you
    control" -- Rescue Retriever. Its own question rather than a very large
    :func:`prevented_damage`, because absorb and a total shield are different
    rules and the difference is not a number: 702.63a's absorb is per source and
    per instance, so any finite N is a per-source cap the card never printed --
    three 1/1 attackers get through an absorb 2 and do nothing at all to a total
    shield.

    Shaped after `protected_from` rather than after absorb, for the reason that
    one is a bool: it answers the whole damage event however big it is. What it
    deliberately is *not* is protection, which also stops the creature being
    blocked, enchanted and targeted -- reusing that would make every shielded
    Soldier unblockable, which is three extra cards' worth of text.

    A static carrying ``combat_only`` -- "prevent all **combat** damage that
    would be dealt to this creature" (Seraph of the Sword) -- answers only when
    ``is_combat``, so burn and a fight still reach the creature.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    return any(
        static.get("prevent_all")
        and (is_combat or not static.get("combat_only"))
        and _matches(state, obj, source_obj, static.get("affects"))
        for source_obj, static in _battlefield_statics(state)
        if static.get("effect") == "prevent_damage"
    )


def damage_into_counters(
    state: GameState, oid: int, *, is_combat: bool = False
) -> tuple[GameObject, str] | None:
    """The total shield that turns this permanent's damage into counters, if any.

    "If equipped creature would be dealt damage, prevent that damage and put
    that many +1/+1 counters on it" -- Panther Habit. A `prevent_damage` static
    with ``prevent_all`` and a ``counter`` kind: one replacement (615) whose
    one event both prevents the damage and puts the counters, so there is no
    trigger and nothing on the stack between the two halves.

    Returns the first such static's source and its counter kind, or ``None``.
    *First* and not summed: once one of them has prevented all of the damage
    there is none left for a second one to replace (616.1), so two Habits on
    one creature put the counters once.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return None
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "prevent_damage" or not static.get("counter"):
            continue
        if static.get("combat_only") and not is_combat:
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return source_obj, static["counter"]
    return None


def crew_power_bonus(state: GameState, oid: int) -> int:
    """How much greater this creature's power counts **while crewing** -- 702.122.

    "This token crews Vehicles as though its power were 2 greater." Not a
    characteristic, and that is the whole design: a `buff` would make the Pilot
    a 3/1 that attacks for three, and the printed token is a 1/1 everywhere
    except inside the one sum a crew cost takes. So this sits beside
    `prevented_damage` -- a static whose output one *other* rule asks for, read
    off the battlefield at the moment that rule runs -- and its one reader is
    `costs._crew_power`.

    Summed over every applicable static, so a creature granted a second one
    counts both.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return 0
    total = 0
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "crew_power_bonus":
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        total += _static_value(state, static.get("amount"), source_obj)
    return total


#: The five colours as `from_colors` spells them.
COLOR_LETTERS = frozenset({"W", "U", "B", "R", "G"})


def commander_color_identity(state: GameState, pid: int) -> frozenset[str]:
    """The colours in ``pid``'s commanders' color identity, as colour letters.

    The union across partners, read off each commander's **printed**
    `color_identity` wherever the commander is: identity is a deck-construction
    fact (903.4), the same set in the command zone as on the battlefield or in a
    graveyard, and `chars()` would answer a different question.

    A player with no commander has an empty identity here, which is what 903.4
    makes of a card asking about a commander that does not exist: its identity
    has no colours -- so Commander's Plate protects from all five.
    """
    colors: set[str] = set()
    for commander in state.commanders_of(pid):
        obj = state.objects.get(commander)
        if obj is not None:
            colors |= set(state.card_of(obj).color_identity)
    return frozenset(colors & COLOR_LETTERS)


def _static_protection_qualities(
    state: GameState, source_obj: GameObject, static: Mapping[str, Any]
) -> set[str]:
    """The qualities one protection static names, flattened.

    Shared by the object-side `protection` static and the seat-side
    `player_protection` static, which spell their qualities with the same keys:
    "you and creatures you control have protection from the chosen card type"
    (Serra's Emissary) is one quality reaching two kinds of thing, and two
    readers of the keys would be two places for "from colorless" to drift.
    """
    out: set[str] = set()
    # "Protection from the chosen card type" is read off the static's own
    # source at the moment a rule asks, so it follows a later choice and
    # matches nothing before one is made.
    out.update(resolve_chosen_card_type_list(static.get("from_types"), source_obj))
    out.update(static.get("from_subtypes", ()))
    # "Protection from the chosen color" -- the colour twin, read the same way.
    out.update(resolve_chosen_color_list(static.get("from_colors"), source_obj))
    if static.get("from_colorless"):
        out.add(PROTECTION_COLORLESS)
    if static.get("from_colors_outside_commander_identity"):
        # "Your commander" is the static's controller's -- the Plate's, not
        # the equipped creature's, and it follows the Equipment when it
        # changes hands. Asked at read time for that reason.
        out.update(COLOR_LETTERS - commander_color_identity(state, source_obj.controller))
    return out


def protection_from(
    state: GameState, oid: int, *, attaching: int | None = None
) -> frozenset[str]:
    """The qualities this permanent has protection from.

    Protection is parameterised -- "from Wizards", "from black", "from
    planeswalkers" -- so it cannot be a `Keyword`, which is a bare string.  It is
    a static whose `from_types`/`from_subtypes`/`from_colors` name the qualities,
    and this returns them flattened into one set of strings to test a source
    against.

    Four rules read it (damage, enchant/equip, block, target).  Returning a set
    rather than answering a question keeps all four asking it the same way.

    ``attaching`` is the enchant/equip rule asking on behalf of one Aura or
    Equipment, and it is the only one of the four that can be told "this
    effect doesn't remove this Aura" (Flickering Ward): a static carrying
    ``spares: "self"`` whose source *is* that attachment is left out, so the
    Ward that chose white stays on -- and goes back on -- a creature it gives
    protection from white. Another white Aura is still refused, and damage,
    blocks and targets from the Ward itself still meet the protection.
    """
    if not state.objects.get(oid) or not state.objects[oid].on_battlefield:
        return frozenset()
    out: set[str] = set()
    obj = state.objects[oid]
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "protection":
            continue
        if (
            attaching is not None
            and source_obj.oid == attaching
            and static.get("spares") == "self"
        ):
            continue
        if not _matches(state, obj, source_obj, static.get("affects")):
            continue
        out |= _static_protection_qualities(state, source_obj, static)
    # "Creatures you control gain protection from each color until end of turn"
    # -- Akroma's Will. Granted protection is one `TempEffect` per quality, so it
    # joins the printed statics' qualities in the same flat set, and the four
    # rules that read this -- damage, enchant/equip, block, target -- all see it
    # without knowing where it came from.
    out.update(
        str(temp.keyword) for temp in obj.until_eot if temp.kind == "protection" and temp.keyword
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


def annihilator_instances(state: GameState, oid: int) -> tuple[int, ...]:
    """The N of every annihilator instance this permanent has, one per instance.

    One entry per instance because each triggers separately (702.86b): an
    Ulamog's Crusher wearing an Eldrazi Conscription has ``(2, 2)`` and its
    attack makes the defending player sacrifice four permanents, in two goes.

    Gated on the **derived** keyword first, so whatever removes the word --
    `lose_all_abilities`, a `lose_keyword` static, a face-down shell -- removes
    every instance with it. Then the two places an N can come from, and the only
    two the loader lets the word arrive by (`enums.NUMBERED_KEYWORDS`):

    * the printed instance, `CardDef.annihilator`, unless the permanent has
      lost its abilities (the layer-1b removal `_compute` makes); and
    * each `grant_keyword` static on the battlefield naming annihilator whose
      `affects` reaches this permanent, with the N it carries. Matched the way
      `_compute`'s keyword-grant layer matches, so the instance list and the
      keyword can never disagree about who was granted it.
    """
    word = Keyword.ANNIHILATOR.value
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or obj.face_down:
        return ()
    if not has_keyword(state, oid, word):
        return ()
    out: list[int] = []
    card = state.card_of(obj)
    if card.annihilator and word in card.keywords and not _loses_abilities(state, obj):
        out.append(card.annihilator)
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "grant_keyword" or word not in static.get("keywords", ()):
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            out.append(int(static["annihilator"]))
    return tuple(out)


def matches_static(
    state: GameState,
    obj: GameObject,
    source: GameObject,
    selector: Mapping[str, Any] | None,
    *,
    derived: bool = False,
) -> bool:
    """Public name for the static-filter matcher, for rules outside this module.

    ``derived`` is `_matches`' own: a rule-modifying static, read outside the
    layer pipeline, matches the object's characteristics after every layer.
    """
    return _matches(state, obj, source, selector, derived=derived)


def block_restrictions(state: GameState, oid: int) -> list[tuple[GameObject, Mapping[str, Any]]]:
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
        # Not a layer (613): a restriction reads the attacker as it now is.
        if not _matches(state, obj, source_obj, static.get("affects"), derived=True):
            continue
        out.append((source_obj, static))
    return out


def protected_from(
    state: GameState, oid: int, source_oid: int | None, *, attaching: bool = False
) -> bool:
    """Does ``oid`` have protection from ``source_oid``?

    ``source_oid`` is the *source* of the damage, spell or block -- a permanent
    on the battlefield or a spell on the stack.  A quality it does not have
    cannot be protected against, so a missing source is never protection.

    ``attaching`` says the question is whether ``source_oid`` can enchant or
    equip ``oid``, the one rule a ``spares: "self"`` static exempts its own
    source from (:func:`protection_from`).
    """
    qualities = protection_from(
        state, oid, attaching=source_oid if attaching else None
    )
    return _matches_protection(state, qualities, source_oid)


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
        colors = set(c.colors)
        have = set(c.types) | set(c.subtypes) | colors
    else:
        colors = set(card.colors)
        have = set(card.types) | set(card.subtypes) | colors
    # "Protection from colorless" (Giver of Runes). Colorless is not a colour
    # (105.2c), so it is the one quality matched on what the source *lacks*:
    # a source with no colours at all, read off the same derived-or-printed
    # characteristics as everything else, so a permanent a `set_colors` static
    # has made colourless is matched and one given a colour is not.
    if PROTECTION_COLORLESS in qualities and not colors:
        return True
    return bool(have & qualities)


def player_protection_from(state: GameState, pid: int) -> frozenset[str]:
    """The qualities this **player** has protection from.

    The seat-side twin of :func:`protection_from`, and it returns the same flat
    set of strings so the rules that read protection ask one kind of question.
    Two sources feed it, and every reader sees both without knowing which:

    * `GameState.player_protections` -- the timed grant (Teferi's Protection,
      The One Ring), which outlives whatever installed it.
    * the `player_protection` static -- "**you** have protection from the
      chosen card type" (Serra's Emissary), a player-wide static walked by
      `player_statics._active_player_statics` like every other one, so its
      "as long as" condition is honoured, and spelling its qualities with the
      object-side static's keys.

    Three rules read this, against the four that read the object side: damage
    (`primitives.damage_player`), targeting (`targeting._player_allowed`), and
    "can't be enchanted" (`primitives.attach_to_player`, for an Aura put onto
    a seat without being cast -- one that is cast targets the seat as it is
    cast, 303.4a, so the target check refuses it first). A player cannot be
    blocked.
    """
    # Imported here: `player_statics` is built on this module, and the walk
    # belongs to it -- a second walk of player-wide statics here would be the
    # copy that forgets the `condition` gate.
    from .player_statics import _active_player_statics, _reaches_player

    out = {entry.quality for entry in state.player_protections if entry.player == pid}
    for source_obj, static in _active_player_statics(state, "player_protection"):
        if _reaches_player(source_obj, static, pid):
            out |= _static_protection_qualities(state, source_obj, static)
    return frozenset(out)


def player_protected_from(state: GameState, pid: int, source_oid: int | None) -> bool:
    """Does ``pid`` have protection from ``source_oid``?

    Protection stops **anyone**, its controller included: Teferi's Protection
    means your own Lightning Bolt cannot be pointed at you either. That is the
    same rule `can_be_targeted` already applies on the object side, and the half
    a hexproof-shaped implementation would silently get wrong.
    """
    return _matches_protection(state, player_protection_from(state, pid), source_oid)


def loyalty_activation_timing_waived(state: GameState, oid: int) -> bool:
    """May this permanent's loyalty abilities be activated at instant speed?

    "You may activate loyalty abilities of Teferi on any player's turn any time
    you could cast an instant" -- Teferi, Master of Time. The
    `activate_loyalty_as_though_instant` static, whose `affects` says whose
    loyalty abilities are freed (``{"self_only": true}`` on this card, which is
    the printed "of Teferi").

    Read in `legality._ability_aims`, which refuses an ability outright when
    `ability.sorcery_speed_only and not sorcery_speed`. Sorcery speed is forced
    on for every loyalty ability by the loader -- ``sorcery_speed_only =
    model.sorcery_speed_only or cost.loyalty is not None`` -- so writing
    ``sorcery_speed_only: false`` on the card is swallowed by the `or` and there
    was no authorable way to reach the flag at all. The permission had to arrive
    from the board instead.

    **Only the window moves.** 606.3 is two rules, and this line lifts one of
    them: a loyalty ability is still one per permanent per turn, which
    `_ability_aims` checks separately and which is not waived here. A waiver
    that took both would be three cards' worth of Teferi every turn.

    Named for loyalty rather than for abilities in general, because that is the
    half that can be answered exactly. Leonin Shikari's "you may activate equip
    abilities any time you could cast an instant" wants the same seam pointed at
    equip, and nothing on `Ability` marks an equip ability yet -- so it stays a
    gap rather than becoming a word that half means it.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    return any(
        static.get("effect") == "activate_loyalty_as_though_instant"
        and _matches(state, obj, source_obj, static.get("affects"))
        for source_obj, static in _battlefield_statics(state)
    )
