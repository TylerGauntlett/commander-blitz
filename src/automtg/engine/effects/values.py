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
        # "…if this is the second time this ability has resolved this turn."
        # Keyed by ability rather than by player, and counting the resolution in
        # progress, so it is the one ledger tally read off the effect context
        # rather than off the ledger -- see `structs.TurnLedger`.
        "resolutions_this_turn",
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
        # "…if it had no -1/-1 counters on it" -- persist and undying. Not
        # `counters_on`, which reads a live object: this asks about a creature
        # that has just died, and `reset_permanent_state` emptied its counters
        # on the way to the graveyard. Answered from the dies trigger's
        # `had_counters` binding, snapshotted before the wipe.
        "counters_had",
        # "…for each basic land type among lands you control" (domain), and
        # "three or more creatures with different powers" (coven). A count of
        # *distinct values* over a pool, which no other leaf can be: `count`
        # counts objects, so five Forests are five and not one.
        "distinct",
        # "…the number of green mana symbols in the mana costs of permanents you
        # control" -- chroma. The one question nothing else asks: every other
        # reader of a cost wants its total or the set of colours in it, and this
        # wants how many times one symbol appears.
        "mana_symbols",
        # "…where X is the number of colors of mana spent to cast this spell" --
        # sunburst and converge. A fact about the *payment*, not the cost: a
        # Sunburst artifact cast for {4} off five different lands enters with
        # five counters, and its printed cost has no coloured pip at all.
        "colors_of_mana_spent",
        # "…for each creature sacrificed this way" / "copy it for each time you
        # paid" -- casualty and replicate. How many times the card's additional
        # cost was paid, which nothing else records: the sacrificed creatures are
        # in a graveyard among everything else that died, and the mana is gone.
        "additional_paid",
    }
)

#: What ``{"distinct": {"of": …}}`` may count. Two entries, and both have a card
#: behind them: domain counts basic land types, coven counts powers. A third
#: would be vocabulary with nothing printed asking for it, and a misspelling has
#: to be a load error rather than a silent zero.
DISTINCT_OF = ("power", "basic_land_type")

#: Rule 305.6. The five basic land types, which are the whole of domain.
BASIC_LAND_TYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})


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
    if "additional_paid" in expr:
        # Casualty and replicate. Read off the object being cast, which is what
        # a "when you cast this spell" trigger is sourced to.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
        return obj.cast_additional if obj is not None else 0
    if "colors_of_mana_spent" in expr:
        # Sunburst and converge. Read off the object that was cast, which for a
        # spell's own `spell_effects` is `source_oid` and for an artifact's
        # enters trigger is the permanent -- the same object either way, because
        # an oid survives the zone change onto the battlefield.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
        return len(obj.colors_spent) if obj is not None else 0
    if "mana_symbols" in expr:
        # Chroma. Read off the **printed** cost, which is what the keyword says
        # and also what makes it safe inside a static: a mana cost is a pipeline
        # input, and no layer can change one.
        spec = expr["mana_symbols"]
        from .selectors import resolve_pool

        color = str(spec.get("of", ""))
        return sum(
            ctx.state.card_of(obj).mana_cost.symbols_of(color)
            for oid in resolve_pool(ctx, spec.get("objects") or {})
            if (obj := ctx.state.objects.get(oid)) is not None
        )
    if "distinct" in expr:
        # Domain and coven: how many *different* values a pool holds, not how
        # many objects are in it. `count` cannot say it in either direction --
        # five Forests are one basic land type and five objects, and three
        # creatures that are all 2/2 are three objects and one power.
        #
        # Both readings are of **derived** characteristics, deliberately: an
        # anthem changes who counts for coven, and "all lands are Islands"
        # changes what counts for domain. That is also why this leaf is not in
        # the static condition language -- a static reading it would depend on
        # another static's output, which is the one thing layers-lite forbids.
        spec = expr["distinct"]
        from .selectors import resolve_pool

        pool = resolve_pool(ctx, spec.get("objects") or {})
        of = str(spec.get("of", "power"))
        if of == "power":
            return len({chars(ctx.state, oid).power for oid in pool})
        found: set[str] = set()
        for oid in pool:
            found |= BASIC_LAND_TYPES & chars(ctx.state, oid).subtypes
        return len(found)
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
    if "counters_had" in expr:
        # The kind, as a bare string: {"counters_had": "-1/-1"}.
        kind = str(expr["counters_had"])
        had = ctx.bindings.get("had_counters")
        return int(had.get(kind, 0)) if isinstance(had, Mapping) else 0
    if "cards_drawn_this_turn" in expr:
        pids = _players(ctx, expr["cards_drawn_this_turn"])
        return sum(ctx.state.cards_drawn_this_turn.get(p, 0) for p in pids)
    if "resolutions_this_turn" in expr:
        # "If this is the second time this ability has resolved this turn."
        # Read off the context rather than the ledger: only `resolve_top` knows
        # which ability is resolving, and the count has to include this one.
        return ctx.resolutions
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


def validate_mana_symbols(spec: Any, where: str, *, validate_objects: Any = None) -> None:
    """Shared by the effect-side and static-side value validators.

    Both languages accept ``mana_symbols`` -- Primalcrux reads it in a `set_pt`
    static and the ability-word cards read it as an amount -- and a leaf added to
    one and not the other loads in a card that then quietly reads 0. They differ
    only in which filter language checks ``objects``, so that is the parameter.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    unknown = set(spec) - {"of", "objects"}
    if unknown:
        raise DslError(f"{where}: unsupported keys {sorted(unknown)}")
    of = spec.get("of")
    if not isinstance(of, str) or of.upper() not in ("W", "U", "B", "R", "G"):
        # Defaulted or misspelled it would count nothing and read 0, which on
        # Primalcrux is a 0/0 that dies to state-based actions on arrival.
        raise DslError(f"{where}.of: must name a colour (W/U/B/R/G), got {of!r}")
    if not spec.get("objects"):
        # An empty selector is every permanent in the game, so chroma would
        # count an opponent's board as well as yours.
        raise DslError(f"{where}: needs 'objects' -- an empty selector is every permanent")
    if validate_objects is None:
        from .selectors import validate_selector as validate_objects
    validate_objects(spec["objects"], f"{where}.objects")


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
    if "mana_symbols" in expr:
        validate_mana_symbols(expr["mana_symbols"], f"{where}.mana_symbols")
    if "distinct" in expr:
        from .selectors import validate_selector

        spec = expr["distinct"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.distinct: must be an object")
        unknown = set(spec) - {"of", "objects"}
        if unknown:
            raise DslError(f"{where}.distinct: unsupported keys {sorted(unknown)}")
        of = spec.get("of")
        if of not in DISTINCT_OF:
            # Defaulted or misspelled it would count powers when the card meant
            # land types, which is a plausible-looking number on every board.
            raise DslError(
                f"{where}.distinct: 'of' must be one of {list(DISTINCT_OF)}, got {of!r}"
            )
        if not spec.get("objects"):
            # An empty selector is the whole battlefield, so domain would count
            # an opponent's basics and coven would count their creatures.
            raise DslError(
                f"{where}.distinct: needs 'objects' -- an empty selector is "
                f"every permanent in the game, including your opponents'"
            )
        validate_selector(spec["objects"], f"{where}.distinct.objects")
