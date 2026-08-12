"""The value-expression DSL.

Any numeric field in a card definition may be a plain integer or one of these
forms::

    {"const": 3}                      a literal
    {"x": true}                       the X chosen when the spell was cast
    {"count": {selector}}             how many objects match
    {"power_of": {"target": "t1"}}    a characteristic of an object or snapshot
    {"life_of": "you"}                a player quantity
    {"cards_drawn_this_turn": "you"}  a per-turn tally of an event
    {"creatures_died_this_turn": "all"}   the rest of that ledger: morbid,
    {"attacked_this_turn": "you"}          raid, bloodthirst, spectacle,
    {"spells_cast_this_turn": "all"}       storm and gravestorm
    {"min_life_of": "each_opponent"}  the lowest of them, one player at a time
    {"sum": [a, b, ...]}              arithmetic
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..characteristics import chars, min_life
from ..errors import DslError
from ..objects import PLUS_ONE
from .context import EffectContext

#: Every key that may appear at the top level of a value expression.
VALUE_KEYS = frozenset(
    {
        "const",
        "x",
        "count",
        "power_of",
        "toughness_of",
        "mana_value_of",
        "life_of",
        # "…unless an opponent has 10 or less life."  `life_of` SUMS over its
        # player spec, which is the printed card in a duel and a different card
        # at a pod: three opponents at 4 life sum to 12, so a summing test would
        # say nobody is low against a table that is nearly dead.  These two ask
        # about ONE player -- `min_life_of` is the existential ("an opponent
        # has…"), `max_life_of` the universal ("each opponent has…").
        "min_life_of",
        "max_life_of",
        "cards_in_hand",
        # "…for each card you've drawn this turn."  A tally of an event, not a
        # count of objects, and the two stop agreeing the moment anything is
        # played, discarded, or drawn on somebody else's turn.
        "cards_drawn_this_turn",
        # The rest of the per-turn ledger (`structs.TurnLedger`).  All six are
        # values rather than condition leaves, so morbid is an ordinary `cmp`
        # against 1 and nothing new had to be added to the condition language:
        # "did it happen" and "how many times" are the same question asked with
        # a different threshold, and storm needs the number anyway.
        "creatures_died_this_turn",
        "attacked_this_turn",
        "damage_taken_this_turn",
        "life_lost_this_turn",
        "spells_cast_this_turn",
        "cards_to_graveyard_this_turn",
        "creatures_you_control",
        "lands_you_control",
        "sum",
        "minus",
        "times",
        "max",
        "min",
        "loop_value",
        "binding",
        "counters_on",
    }
)


def evaluate_value(ctx: EffectContext, expr: Any) -> int:
    """Evaluate a value expression to an integer."""
    if expr is None:
        return 0
    if isinstance(expr, bool):
        return int(expr)
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        # "x" and "all" are accepted as bare strings for readability in card files.
        if expr == "x":
            return ctx.x
        raise DslError(f"unparsable value expression {expr!r}")
    if not isinstance(expr, Mapping):
        raise DslError(f"unparsable value expression {expr!r}")

    if "const" in expr:
        return int(expr["const"])
    if "x" in expr:
        return ctx.x
    if "loop_value" in expr:
        return int(ctx.loop_value or 0)
    if "binding" in expr:
        value = ctx.bindings.get(str(expr["binding"]))
        return int(value) if isinstance(value, int) else 0
    if "count" in expr:
        from .selectors import resolve_pool

        return len(resolve_pool(ctx, expr["count"]))
    if "counters_on" in expr:
        # How many counters of a kind sit on an object -- which is what "double
        # the number of +1/+1 counters on this creature" needs, and the one
        # quantity the value language could not previously reach.
        spec = expr["counters_on"]
        kind = str(spec.get("counter", PLUS_ONE))
        from .selectors import resolve_pool

        pool = resolve_pool(ctx, spec.get("objects") or {"self_only": True})
        return sum(ctx.state.objects[oid].counter(kind) for oid in pool if oid in ctx.state.objects)
    if "creatures_you_control" in expr:
        return len(ctx.state.creatures(ctx.controller))
    if "lands_you_control" in expr:
        return sum(
            1
            for o in ctx.state.battlefield_objects(ctx.controller)
            if "Land" in chars(ctx.state, o.oid).types
        )
    if "power_of" in expr:
        return _characteristic(ctx, expr["power_of"], "power")
    if "toughness_of" in expr:
        return _characteristic(ctx, expr["toughness_of"], "toughness")
    if "mana_value_of" in expr:
        return _characteristic(ctx, expr["mana_value_of"], "mana_value")
    if "life_of" in expr:
        pids = _players(ctx, expr["life_of"])
        return sum(ctx.state.players[p].life for p in pids)
    if "min_life_of" in expr:
        pids = _players(ctx, expr["min_life_of"])
        return min_life([ctx.state.players[p].life for p in pids])
    if "max_life_of" in expr:
        pids = _players(ctx, expr["max_life_of"])
        return max([ctx.state.players[p].life for p in pids], default=0)
    if "cards_in_hand" in expr:
        pids = _players(ctx, expr["cards_in_hand"])
        return sum(len(ctx.state.players[p].hand) for p in pids)
    if "cards_drawn_this_turn" in expr:
        pids = _players(ctx, expr["cards_drawn_this_turn"])
        return sum(ctx.state.cards_drawn_this_turn.get(p, 0) for p in pids)
    ledger = ctx.state.turn_ledger
    if "creatures_died_this_turn" in expr:
        # Keyed by who controlled the creature, so `"all"` is morbid's "a
        # creature died this turn" and `"you"` is "a creature you controlled".
        pids = _players(ctx, expr["creatures_died_this_turn"])
        return sum(ledger.creatures_died.get(p, 0) for p in pids)
    if "attacked_this_turn" in expr:
        # How many of the named players attacked, which is 0 or 1 for raid's
        # `"you"` and a headcount for "if two opponents attacked this turn".
        pids = _players(ctx, expr["attacked_this_turn"])
        return sum(1 for p in pids if p in ledger.attacked)
    if "damage_taken_this_turn" in expr:
        pids = _players(ctx, expr["damage_taken_this_turn"])
        return sum(ledger.damage_taken.get(p, 0) for p in pids)
    if "life_lost_this_turn" in expr:
        pids = _players(ctx, expr["life_lost_this_turn"])
        return sum(ledger.life_lost.get(p, 0) for p in pids)
    if "spells_cast_this_turn" in expr:
        pids = _players(ctx, expr["spells_cast_this_turn"])
        return sum(ledger.spells_cast.get(p, 0) for p in pids)
    if "cards_to_graveyard_this_turn" in expr:
        # Every graveyard, so it takes no player spec: gravestorm counts cards
        # put into *a* graveyard, not into yours.
        return ledger.cards_to_graveyard
    if "sum" in expr:
        return sum(evaluate_value(ctx, e) for e in expr["sum"])
    if "minus" in expr:
        parts = [evaluate_value(ctx, e) for e in expr["minus"]]
        result = parts[0] if parts else 0
        for p in parts[1:]:
            result -= p
        return result
    if "times" in expr:
        result = 1
        for e in expr["times"]:
            result *= evaluate_value(ctx, e)
        return result
    if "max" in expr:
        return max((evaluate_value(ctx, e) for e in expr["max"]), default=0)
    if "min" in expr:
        return min((evaluate_value(ctx, e) for e in expr["min"]), default=0)

    raise DslError(f"unknown value expression {sorted(expr)}")


def _players(ctx: EffectContext, spec: Any) -> list[int]:
    from .selectors import select_players

    return select_players(ctx, spec)


def _characteristic(ctx: EffectContext, ref: Any, which: str) -> int:
    """Read power/toughness/mana value from a target, binding or snapshot."""
    if isinstance(ref, Mapping) and "var" in ref:
        snap = ctx.bindings.get(str(ref["var"]))
        if isinstance(snap, Mapping):
            return int(snap.get(which, 0))
        if isinstance(snap, int):
            return _from_oid(ctx, snap, which)
        return 0
    if isinstance(ref, Mapping) and "target" in ref:
        oids = ctx.target_oids(str(ref["target"]))
        return sum(_from_oid(ctx, oid, which) for oid in oids)
    if isinstance(ref, Mapping) and "binding" in ref:
        value = ctx.bindings.get(str(ref["binding"]))
        if isinstance(value, Mapping):
            return int(value.get(which, 0))
        if isinstance(value, int):
            return _from_oid(ctx, value, which)
        return 0
    if isinstance(ref, Mapping) and "self" in ref:
        return _from_oid(ctx, ctx.source_oid, which) if ctx.source_oid else 0
    if isinstance(ref, int):
        return _from_oid(ctx, ref, which)
    raise DslError(f"unparsable characteristic reference {ref!r}")


def _from_oid(ctx: EffectContext, oid: int | None, which: str) -> int:
    if oid is None:
        return 0
    obj = ctx.state.objects.get(oid)
    if obj is None:
        return 0
    if which == "mana_value":
        # "…except it's a white Zombie Angel with **no mana cost**." An embalm
        # token's def_id is the original card's, so without this it would still
        # report the printed cost's mana value.
        if obj.copy_overrides and obj.copy_overrides.get("no_mana_cost"):
            return 0
        return ctx.state.card_of(obj).mana_value
    c = chars(ctx.state, oid)
    return c.power if which == "power" else c.toughness


def validate_value(expr: Any, where: str) -> None:
    """Load-time check that a value expression uses only known forms."""
    if expr is None or isinstance(expr, (int, bool)):
        return
    if isinstance(expr, str):
        if expr != "x":
            raise DslError(f"{where}: unparsable value {expr!r}")
        return
    if not isinstance(expr, Mapping):
        raise DslError(f"{where}: value must be an int or object, got {type(expr).__name__}")
    unknown = set(expr) - VALUE_KEYS
    if unknown:
        raise DslError(f"{where}: unknown value keys {sorted(unknown)}")
    for key in ("sum", "minus", "times", "max", "min"):
        if key in expr:
            if not isinstance(expr[key], list):
                raise DslError(f"{where}: {key} takes a list")
            for i, sub in enumerate(expr[key]):
                validate_value(sub, f"{where}.{key}[{i}]")
    if "count" in expr:
        from .selectors import validate_selector

        validate_selector(expr["count"], f"{where}.count")
