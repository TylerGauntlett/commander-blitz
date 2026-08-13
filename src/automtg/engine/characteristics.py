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

Results are cached against ``state.char_version``, which every mutating primitive
bumps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .carddef import CardDef
from .enums import Keyword, Zone
from .errors import DslError
from .objects import MINUS_ONE, PLUS_ONE, GameObject
from .structs import Characteristics

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

    # "…a copy of it, except it's a white Zombie Angel with no mana cost."
    # Applied to the *printed* face, before any layer: the exception is part of
    # what this object is, not an effect on it, so an anthem or an animate
    # afterwards should layer on top exactly as it would on a printed card.
    if obj.copy_overrides:
        if (added := obj.copy_overrides.get("add_subtypes")):
            subtypes.update(added)
        if (repaint := obj.copy_overrides.get("colors")) is not None:
            colors = set(repaint)

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


def _battlefield_statics(state: GameState) -> list[tuple[GameObject, Mapping[str, Any]]]:
    """Every *active* ``static`` ability on the battlefield, in arrival order."""
    out: list[tuple[GameObject, Mapping[str, Any]]] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        card = state.card_of(obj)
        for ability in card.abilities:
            if ability.is_static and ability.static and _static_active(state, obj, ability.static):
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
        return (source.attached_to is not None) == bool(cond["is_attached"])
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

    ``{"const": n}``, ``{"count": <filter>}`` and the two per-player life leaves
    are permitted here -- the full value language would need the selector
    engine, which needs derived characteristics, which would reintroduce
    recursion.

    A life total is safe for the same reason a zone count is: it is a *pipeline
    input*. Nothing in the fixed-order characteristics pipeline can change what
    a player's life is, so reading one cannot make a static depend on another
    static's output.
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
    if "min_life_of" in expr:
        pids = _static_players(state, source, expr["min_life_of"])
        return min_life([state.players[p].life for p in pids])
    if "max_life_of" in expr:
        pids = _static_players(state, source, expr["max_life_of"])
        return max([state.players[p].life for p in pids], default=0)
    return 0


def _count_matching(state: GameState, selector: Mapping[str, Any], source: GameObject) -> int:
    """How many objects a static's *counting* filter matches.

    Two paths, because a filter that names a zone other than the battlefield is
    asking a different question.  On the battlefield it is a filter over
    permanents and reads their board state as well as their printed face; in a
    graveyard, hand, exile, library or command zone there is no board state to
    read, so it is the printed face alone.  The loader refuses the board-state
    keys on the second path rather than letting them load and match nothing.
    """
    zone = str(selector.get("zone", "battlefield"))
    if zone == Zone.BATTLEFIELD.value:
        count = 0
        for oid in state.battlefield:
            obj = state.objects.get(oid)
            if obj is None:
                continue
            if _matches(state, obj, source, selector):
                count += 1
        return count

    count = 0
    for pid in _static_players(state, source, selector.get("controller", "you")):
        for oid in state.players[pid].zone_list(Zone(zone)):
            obj = state.objects.get(oid)
            if obj is not None and _matches_printed(state.card_of(obj), selector):
                count += 1
    return count


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
    selector = resolve_chosen_subtypes(selector, source)
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
        if not _matches_printed(card, filt):
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
