"""Walkers and predicates over effect trees.

Shared by the compilers and the validators: "does any effect in this tree
mention X", "does this ability move its own source", and the two grant-target
checks that run before compilation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from commanderblitz.engine.effects.selectors import (
    validate_attached_to_key,
    validate_colorless_key,
    validate_enchanted_by_key,
)
from commanderblitz.engine.effects.values import (
    validate_counter_kind,
)
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import validate_printed_cost_list

from ..schema import CardModel
from .vocabulary import (
    _CHOSEN_QUALITY_KEYS,
    _FILTER_PLAYERS,
    SOURCE_MOVING_OPS,
    STATIC_CONDITION_OPS,
    STATIC_FILTER_KEYS,
)


def _check_owner_key(filt: Mapping[str, Any], where: str) -> None:
    """``owner`` names a player, and a misspelling of one matches nobody.

    There is no ``"any"``: a filter that does not care who owns a permanent says
    nothing, and an ``owner: "any"`` written beside a defaulted ``controller``
    would *also* silently switch that default off -- which is the one thing this
    key does besides testing ownership.
    """
    owner = filt.get("owner")
    if owner is not None and owner not in _FILTER_PLAYERS:
        raise DslError(f"{where}.owner: must be one of {list(_FILTER_PLAYERS)}, got {owner!r}")


def _check_mana_cost_key(filt: Any, where: str) -> None:
    """``mana_cost`` in a static or spell filter is a list of printed costs.

    The effect-side `validate_selector` makes the same check; static filters
    are validated by key set alone, so without this a bare ``"{1}"`` would load
    and be iterated as three characters, matching nothing.
    """
    if isinstance(filt, Mapping) and "mana_cost" in filt:
        validate_printed_cost_list(filt["mana_cost"], where)


def _check_pt_keys(filt: Any, where: str) -> None:
    """``power``/``toughness`` in a static filter is a comparison, not a size.

    ``{"op": ">=", "value": 4}``, or a bare integer meaning equality -- the
    spelling `selectors._compare` and `triggers._compare` already take, so the
    clause reads the same wherever it is written.

    Static filters are validated by key set alone, which is why this check has
    to exist: ``"power": 4`` is fine, but ``"power": {"amount": 4}`` would load,
    default its ``value`` to 0 and match **every** creature on the board -- the
    silently-wider filter this pass exists to refuse -- and ``"power": ">=4"``
    would load and blow up at match time instead of at load time.

    The compared-against value is a plain integer, because a static filter tests
    one object and has no source permanent to measure an expression against.
    """
    if not isinstance(filt, Mapping):
        return
    for key in ("power", "toughness"):
        if key not in filt:
            continue
        spec = filt[key]
        if isinstance(spec, bool) or not isinstance(spec, (int, Mapping)):
            raise DslError(
                f"{where}.{key}: a comparison -- {{'op': '>=', 'value': 4}} -- "
                f"or a bare integer, got {spec!r}"
            )
        if not isinstance(spec, Mapping):
            continue
        unknown = set(spec) - {"op", "value"}
        if unknown:
            raise DslError(
                f"{where}.{key}: unknown comparison keys {sorted(unknown)} "
                f"(a comparison is 'op' and 'value')"
            )
        op = spec.get("op", ">=")
        if op not in STATIC_CONDITION_OPS:
            raise DslError(
                f"{where}.{key}.op: unknown comparison {op!r} "
                f"(implemented: {sorted(STATIC_CONDITION_OPS)})"
            )
        value = spec.get("value", 0)
        if not isinstance(value, int) or isinstance(value, bool):
            raise DslError(
                f"{where}.{key}.value: a static compares against a plain integer, "
                f"got {value!r}"
            )


def _check_attached_to_key(filt: Any, where: str) -> None:
    """``attached_to`` in a static filter: a static filter on the host.

    `validate_attached_to_key` checks the shape every language shares; this
    holds the host filter to the static language's own keys and value checks,
    since `characteristics._matches_wherever` reads it as one. A host filter
    nested inside it is refused: no printed card asks it.
    """
    validate_attached_to_key(filt, where)
    if not isinstance(filt, Mapping) or "attached_to" not in filt:
        return
    host_filter = filt["attached_to"]
    here = f"{where}.attached_to"
    unknown = set(host_filter) - (STATIC_FILTER_KEYS - {"attached_to"})
    if unknown:
        raise DslError(
            f"{here}: static filters may only read printed characteristics; "
            f"unsupported keys {sorted(unknown)}"
        )
    _check_owner_key(host_filter, here)
    _check_mana_cost_key(host_filter, here)
    _check_pt_keys(host_filter, here)
    validate_colorless_key(host_filter, here)
    validate_enchanted_by_key(host_filter, here)


def _refuse_granted_chosen_qualities(filt: Any, where: str) -> None:
    """ "…of the chosen type" cannot survive being handed to another permanent.

    `characteristics.resolve_chosen_subtypes` and its colour twin substitute the
    choice made by the **source**, and a granted static's source is its
    *recipient*. So an author writing "of the chosen type" means the granter and
    the engine would read the recipient -- which has chosen nothing, so the
    filter matches nobody and the card loads clean and does nothing.

    The two readings differ and no printed card asks for either, so this is
    refused rather than picked between.

    Called on a granted static's **filters** and on the static mapping itself,
    because `add_subtype` carries the same entry on its *grant* side -- "this
    creature is the chosen type in addition to its other types" -- outside any
    filter, and the ambiguity there is the same one word for word.
    """
    if not isinstance(filt, Mapping):
        return
    # "Protection from the chosen card type" (or colour) on the static itself:
    # the same source-is-the-recipient trap, one key over.
    for key, chosen in (("from_types", "chosen_card_type_of"), ("from_colors", "chosen_color_of")):
        for entry in filt.get(key) or ():
            if isinstance(entry, Mapping) and chosen in entry:
                raise DslError(
                    f"{where}.{key}: {chosen!r} names the choice made by the "
                    f"source, and a granted static's source is the permanent "
                    f"it was granted to -- which has chosen nothing"
                )
    for key in ("subtypes", "not_subtypes", "colors"):
        for entry in filt.get(key) or ():
            if not isinstance(entry, Mapping):
                continue
            for chosen in _CHOSEN_QUALITY_KEYS:
                if chosen in entry:
                    raise DslError(
                        f"{where}.{key}: {chosen!r} names the choice made by the "
                        f"source, and a granted static's source is the permanent "
                        f"it was granted to -- which has chosen nothing"
                    )


def _walk_effect_specs(effects: Any):
    """Every effect spec in a tree, branches and modes included."""
    for effect in effects or ():
        if not isinstance(effect, Mapping):
            continue
        yield effect
        for key in ("then", "else", "effects"):
            yield from _walk_effect_specs(effect.get(key))
        for mode in effect.get("modes") or ():
            if isinstance(mode, Mapping):
                yield from _walk_effect_specs(mode.get("effects"))


def _mentions_kicked(model: CardModel) -> bool:
    """Does anything on this card read ``{"kicked": ...}``?"""
    return _mentions_condition(model, "kicked")


def _mentions_gift(model: CardModel) -> bool:
    """Does anything on this card read the gift promise?

    Both spellings, because the printed mechanic has two halves and a card may
    write either: the ``{"gift_promised": …}`` condition ("if the gift wasn't
    promised…"), and the ``"gift_recipient"`` player spec, which is what aims
    the promised reward at the seat that was promised it.

    The player spec is matched as a **value** anywhere in a mapping rather than
    under a fixed key, because the seat is named through half a dozen different
    keys depending on the op -- `create_token`'s ``controller``, `draw`'s
    ``player``, a selector's ``controller``. Checking one of them would let the
    others load a promise that nothing reads.
    """
    if _mentions_condition(model, "gift_promised"):
        return True
    return _mentions(model, lambda node: "gift_recipient" in node.values())


def _effects_move_source(effects: Any) -> bool:
    """Does this ability *unconditionally* move its own source out of its zone?

    The third way to satisfy the outside-the-battlefield guard, after cycling's
    self-discard and embalm's self-exile. Unearth pays neither: its cost is
    plain mana and the card leaves because the effect returns it to the
    battlefield.

    Only the **top level** counts. An effect nested inside an `if` or a `may`
    might not run, and an ability whose only exit is a branch the player can
    decline is activatable again from the same zone -- which is the shape the
    guard exists to refuse. `self_only` is likewise required: an ability that
    moves *some other* card out of a graveyard has not moved itself.
    """
    for effect in effects or ():
        if not isinstance(effect, Mapping):
            continue
        if effect.get("op") not in SOURCE_MOVING_OPS:
            continue
        objects = effect.get("objects")
        if isinstance(objects, Mapping) and objects.get("self_only"):
            return True
    return False


def reads_placed_kind(effects: Any) -> bool:
    """Does any effect in this tree put "the same kind" a placement put?

    That is an ``add_counters`` whose ``counter`` is the ``{"binding":
    "counter"}`` mapping. `_validate_effect` holds the mapping to that one op
    and that one shape; whether the binding will exist is a question about the
    trigger, which only the ability compiler can see.
    """
    if isinstance(effects, Mapping):
        if effects.get("op") == "add_counters" and isinstance(effects.get("counter"), Mapping):
            return True
        return any(reads_placed_kind(v) for v in effects.values())
    if isinstance(effects, (list, tuple)):
        return any(reads_placed_kind(v) for v in effects)
    return False


def _mentions_condition(model: CardModel, key: str) -> bool:
    """Does anything on this card read the ``key`` condition?"""
    return _mentions(model, lambda node: key in node)


def _mentions_key_anywhere(model: CardModel, key: str) -> bool:
    """Does ``key`` appear anywhere on this card, replacements and statics included?

    `_mentions_condition` searches effects, targets and trigger conditions only.
    A condition that is read mostly by a **replacement** -- `escaped`, whose
    printed home is "escapes with" -- needs the whole card searched, which is
    safe only for a key no other part of the schema spells.
    """

    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return key in node or any(walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(walk(v) for v in node)
        return False

    return walk(model.model_dump(exclude_none=True))


def _mentions_pair(model: CardModel, key: str, value: str) -> bool:
    """Does anything on this card carry ``{key: value}``?

    The ``key in node`` test `_mentions_condition` uses is too coarse for
    ``{"op": "clash"}`` and ``{"binding": "clash_won"}`` — every effect has an
    ``op`` and dozens have a ``binding``, so the key alone matches everything.
    """
    return _mentions(model, lambda node: node.get(key) == value)


def _mentions(model: CardModel, predicate: Any) -> bool:
    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return bool(predicate(node)) or any(walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(walk(v) for v in node)
        return False

    # Targets are searched as well as effects, because a *count* is one of the
    # places a card reads the game: "return up to X target creature cards, where
    # X is the number of times this was kicked" spends `additional_paid` in its
    # target spec and nowhere else, and the multikicker guard below -- "a cost no
    # effect reads" -- would otherwise refuse the one card the mechanic is for.
    #
    # `exclude_none`, so a key a spec leaves unset is not a key it carries:
    # `gift_promised` is a target field as well as a condition, and with every
    # dump spelling `"gift_promised": None` each targeted card would read as
    # reading the gift. Set, it is a read -- the promise decides what the spell
    # points at.
    def targets_of(models: Any) -> list[Any]:
        return [t.model_dump(exclude_none=True) for t in models]

    if walk(model.spell_effects) or walk(targets_of(model.targets)):
        return True
    return any(
        walk(a.effects)
        or walk(targets_of(a.targets))
        or walk(a.trigger.condition if a.trigger else None)
        for a in model.abilities
    )


def _before(models: Sequence[Any], target_id: str) -> set[str]:
    """The ids declared ahead of ``target_id`` in one target list."""
    out: set[str] = set()
    for model in models:
        if model.id == target_id:
            break
        out.add(model.id)
    return out


#: Refuse a counter kind that *nearly* names a keyword (122.1c).  Lives in
#: ``effects/values.py`` because ``counters_on`` reads a kind in both value
#: languages and one copy of the near-miss rule is the point; aliased here for
#: the trigger, replacement and ``add_counters`` call sites that predate it.
_check_counter_kind = validate_counter_kind
