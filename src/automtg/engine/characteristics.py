"""Derived characteristics -- "layers-lite".

Real Magic resolves continuous effects through seven numbered layers with
timestamps and dependency analysis.  This engine applies a *fixed order* instead:

    printed -> subtype grants -> keyword grants -> P/T setting -> P/T modifying
    -> +1/+1 and -1/-1 counters -> until-end-of-turn pumps

To make that safe there is one hard constraint, enforced by
:func:`automtg.cards.loader.check_static_constraints`:

    **A static ability's filter may not read another static ability's output.**

Static filters are therefore matched against *printed* characteristics (plus the
object's own board state: controller, tapped, attacking, counters).  That removes
all recursion and all dependency ordering, at the cost of not supporting cards
whose anthem depends on another anthem's result.  The curated decks respect this.

Results are cached against ``state.char_version``, which every mutating primitive
bumps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .carddef import CardDef
from .enums import Keyword
from .objects import MINUS_ONE, PLUS_ONE, GameObject
from .structs import Characteristics

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def printed_chars(card: CardDef) -> Characteristics:
    """Characteristics with nothing applied -- straight off the card face."""
    return Characteristics(
        power=card.power or 0,
        toughness=card.toughness or 0,
        types=card.types,
        subtypes=card.subtypes,
        supertypes=card.supertypes,
        keywords=card.keywords,
        colors=card.colors,
    )


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


def _compute(state: GameState, oid: int) -> Characteristics:
    obj = state.objects.get(oid)
    if obj is None:
        return Characteristics()
    card = state.card_of(obj)
    power = card.power or 0
    toughness = card.toughness or 0
    types = set(card.types)
    subtypes = set(card.subtypes)
    supertypes = set(card.supertypes)
    keywords = set(card.keywords)
    colors = set(card.colors)

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
        for source_obj, static in statics:
            if static.get("effect") != "set_types":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                types = set(static.get("types", ()))

        # 1. subtype / type grants
        for source_obj, static in statics:
            if static.get("effect") != "add_subtype":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                subtypes.update(static.get("subtypes", ()))
                types.update(static.get("types", ()))

        # 2. keyword grants
        for source_obj, static in statics:
            if static.get("effect") != "grant_keyword":
                continue
            if _matches(state, obj, source_obj, static.get("affects")):
                keywords.update(static.get("keywords", ()))

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

        # 5. counters
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

    return Characteristics(
        power=power,
        toughness=toughness,
        types=frozenset(types),
        subtypes=frozenset(subtypes),
        supertypes=frozenset(supertypes),
        keywords=frozenset(keywords),
        colors=frozenset(colors),
    )


def _battlefield_statics(state: GameState) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """Every *active* ``static`` ability on the battlefield, in arrival order."""
    out: list[tuple[GameObject, Mapping[str, Any]]] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        card = state.card_of(obj)
        for ability in card.abilities:
            if ability.is_static and ability.static and _static_active(obj, ability.static):
                out.append((obj, ability.static))
    return out


def _static_active(source: GameObject, static: Mapping[str, Any]) -> bool:
    """Is this static's "as long as..." clause currently true?

    Deliberately tiny: the only question a static may ask is how many counters of
    a kind sit on its own source.  That is board state rather than a derived
    characteristic, so it cannot depend on another static's output and the fixed
    -order pipeline stays acyclic -- the same reason `affects` filters may only
    read printed characteristics.
    """
    condition = static.get("condition")
    if not condition:
        return True
    spec = condition.get("counters") or {}
    have = source.counter(str(spec.get("counter", PLUS_ONE)))
    amount = int(spec.get("amount", 1))
    op = str(spec.get("op", ">="))
    return {
        ">=": have >= amount,
        "<=": have <= amount,
        ">": have > amount,
        "<": have < amount,
        "=": have == amount,
        "==": have == amount,
        "!=": have != amount,
    }[op]


def _static_value(state: GameState, expr: Any, source: GameObject) -> int:
    """Evaluate the restricted value language allowed inside static abilities.

    Only ``{"const": n}`` and ``{"count": <filter>}`` are permitted here -- the
    full value language would need the selector engine, which needs derived
    characteristics, which would reintroduce recursion.
    """
    if expr is None:
        return 0
    if isinstance(expr, int):
        return expr
    if not isinstance(expr, Mapping):
        return 0
    if "const" in expr:
        return int(expr["const"])
    if "count" in expr:
        return _count_matching(state, expr["count"], source)
    return 0


def _count_matching(state: GameState, selector: Mapping[str, Any], source: GameObject) -> int:
    count = 0
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if _matches(state, obj, source, selector):
            count += 1
    return count


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

    controller = selector.get("controller", "you")
    if controller == "you" and obj.controller != source.controller:
        return False
    if controller == "opponent" and obj.controller == source.controller:
        return False

    types = selector.get("types")
    if types and not set(types).issubset(card.types):
        return False
    not_types = selector.get("not_types")
    if not_types and set(not_types) & card.types:
        return False
    subtypes = selector.get("subtypes")
    if subtypes and not (set(subtypes) & card.subtypes):
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


def effective_toughness(state: GameState, oid: int) -> int:
    """Toughness minus damage already marked -- how much more it can take."""
    obj = state.objects[oid]
    return chars(state, oid).toughness - obj.damage


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
    return frozenset(out)


def protected_from(state: GameState, oid: int, source_oid: int | None) -> bool:
    """Does ``oid`` have protection from ``source_oid``?

    ``source_oid`` is the *source* of the damage, spell or block -- a permanent
    on the battlefield or a spell on the stack.  A quality it does not have
    cannot be protected against, so a missing source is never protection.
    """
    if source_oid is None:
        return False
    qualities = protection_from(state, oid)
    if not qualities:
        return False
    source = state.objects.get(source_oid)
    if source is None:
        return False
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
    out: set[int] = set()
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        for ability in state.card_of(obj).abilities:
            static = ability.static
            if ability.is_static and static and static.get("effect") == "freeze_opponent_lands":
                out.add(obj.controller)
    return frozenset(out)


def player_has_no_hand_limit(state: GameState, pid: int) -> bool:
    """Whether any ``no_hand_limit`` static frees this player from discarding.

    Reliquary Tower, Thought Vessel, Nezahal. Written as a player-wide static
    like ``extra_land_drops`` rather than as a characteristic, because it is a
    fact about the *player* and there is no object for it to attach to.
    """
    return _player_static(state, pid, "no_hand_limit")


def _player_static(state: GameState, pid: int, effect: str) -> bool:
    """Whether any permanent grants ``effect`` to this player."""
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
            who = static.get("affects_player", "you")
            if who == "you" and obj.controller != pid:
                continue
            if who == "opponent" and obj.controller == pid:
                continue
            return True
    return False


def player_plays_lands_from_graveyard(state: GameState, pid: int) -> bool:
    """Whether this player may play lands from their graveyard.

    Ramunap Excavator, Crucible of Worlds, Ancient Greenwarden. Widens *where* a
    land may be played from; the one-land-per-turn rule is untouched and still
    enforced by `lands_played`.
    """
    return _player_static(state, pid, "play_lands_from_graveyard")


def player_plays_lands_from_library_top(state: GameState, pid: int) -> bool:
    """Whether this player may play the top card of their library, if it is a land.

    Oracle of Mul Daya, Courser of Kruphix. Only the *top* card, which is what
    the cards say and also the only part of a hidden zone anybody is allowed to
    know about.
    """
    return _player_static(state, pid, "play_lands_from_library_top")


def player_extra_land_drops(state: GameState, pid: int) -> int:
    """Sum of every ``extra_land_drops`` static affecting this player."""
    total = 0
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        for ability in state.card_of(obj).abilities:
            static = ability.static
            if not ability.is_static or not static:
                continue
            if static.get("effect") != "extra_land_drops":
                continue
            who = static.get("affects_player", "you")
            if who == "you" and obj.controller != pid:
                continue
            if who == "opponent" and obj.controller == pid:
                continue
            total += _static_value(state, static.get("amount"), obj)
    return total
