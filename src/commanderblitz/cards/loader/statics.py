"""Validation of static abilities' conditions, values and cost reductions.

Static filters may only read printed characteristics; these are the checks
that hold the line.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from commanderblitz.engine.effects.conditions import validate_condition
from commanderblitz.engine.effects.selectors import (
    validate_colorless_key,
    validate_enchanted_by_key,
)
from commanderblitz.engine.effects.values import (
    PER_PLAYER_COUNT_KEYS,
    validate_counters_on,
    validate_entered_filter,
    validate_mana_symbols,
    validate_per_player_count,
)
from commanderblitz.engine.errors import DslError

from .vocabulary import (
    COST_CONDITION_HEADS,
    COST_REDUCTION_FILTER_KEYS,
    COST_REDUCTION_KEYS,
    COST_REDUCTION_REFUSED_FILTER_KEYS,
    COST_REDUCTION_ZONES,
    KNOWN_SUPERTYPES,
    KNOWN_TYPES,
    STATIC_CONDITION_HEADS,
    STATIC_CONDITION_OPS,
    STATIC_COUNT_FILTER_KEYS,
    STATIC_COUNT_ZONES,
    STATIC_DEATHS_KEYS,
    STATIC_FILTER_KEYS,
    STATIC_LIFE_KEYS,
    STATIC_LIFE_PLAYERS,
    STATIC_MANA_POOL_KEYS,
    STATIC_MONARCH_PLAYERS,
    STATIC_POISON_KEYS,
    STATIC_SPELLS_CAST_KEYS,
    STATIC_VALUE_KEYS,
    STATIC_ZONE_FILTER_KEYS,
)
from .walk import (
    _check_counter_kind,
    _check_mana_cost_key,
    _check_owner_key,
    _check_pt_keys,
)


def _validate_cost_condition(cond: Any, where: str) -> None:
    """A cost reduction's condition: the shared condition DSL, narrowed."""
    validate_condition(cond, where)
    if not isinstance(cond, Mapping):
        return
    unusable = set(cond) - COST_CONDITION_HEADS
    if unusable:
        raise DslError(
            f"{where}: {sorted(unusable)} cannot be answered while a cost is being "
            f"priced -- nothing is on the stack yet (usable: "
            f"{sorted(COST_CONDITION_HEADS)})"
        )
    for key in ("all", "any"):
        for i, sub in enumerate(cond.get(key) or ()):
            _validate_cost_condition(sub, f"{where}.{key}[{i}]")
    if "not" in cond:
        _validate_cost_condition(cond["not"], f"{where}.not")


def _validate_reduction_zones(filt: Mapping[str, Any], key: str, where: str) -> None:
    """Which zones one reduction filter is allowed to count.

    A string or a list of strings, drawn from `COST_REDUCTION_ZONES`: the
    battlefield and the command zone are the two `costs._reduction_matches`
    walks, and a filter naming any other would load clean and match nothing --
    the silent failure this validator exists for.

    ``total_power`` is battlefield-only however the list is written. Power is a
    characteristic of a permanent; a card in the command zone has none, and
    summing the printed face there would be answering a question the pipeline
    was never asked.
    """
    if "zone" not in filt:
        return
    raw = filt["zone"]
    zones = [raw] if isinstance(raw, str) else list(raw)
    if not zones:
        raise DslError(f"{where}.zone: names no zone at all")
    bad = [z for z in zones if z not in COST_REDUCTION_ZONES]
    if bad:
        raise DslError(
            f"{where}.zone: a cost reduction counts "
            f"{sorted(COST_REDUCTION_ZONES)} only, got {bad!r}"
        )
    if key == "total_power" and set(zones) != {"battlefield"}:
        raise DslError(
            f"{where}.zone: 'total_power' sums a characteristic only permanents "
            f"have, so it counts the battlefield only, got {raw!r}"
        )


def _check_reduction_type_names(filt: Mapping[str, Any], where: str) -> None:
    """A misspelled type or supertype in a reduction filter matches nothing.

    The same guard `effects.selectors.validate_selector` applies to every
    selector, and it is needed here for a sharper reason: a selector that matches
    nothing fails visibly the first time a card is played, while a *reduction*
    that matches nothing is simply a discount of zero -- a card that is quietly
    priced at the number it prints, on a board where nothing looks wrong.

    ``subtypes`` is not checked, here or in the selector language: creature and
    land types are open-ended and there is no closed set to check against.
    """
    for key, known in (("types", KNOWN_TYPES), ("supertypes", KNOWN_SUPERTYPES)):
        for name in filt.get(key) or ():
            if name not in known:
                raise DslError(
                    f"{where}.{key}: unknown {key[:-1]} {name!r} would count nothing "
                    f"and read as a discount of zero (known: {sorted(known)})"
                )


def _validate_reduction_any_of(filt: Mapping[str, Any], where: str) -> None:
    """Check the branches of a reduction filter's ``any_of``, if it has one.

    Each branch is the same filter language asked about the same object, so
    each is held to the same keys -- recursively, because a branch may carry a
    branch.

    A branch may **not** name a ``zone``. The zones are chosen once, outside
    the per-object walk, so a branch that named its own would be read by
    nobody: the filter would load, look like it counted two zones and count
    one.
    """
    branches = filt.get("any_of")
    if branches is None:
        return
    if not isinstance(branches, list) or not branches:
        raise DslError(f"{where}.any_of: takes a non-empty list of filters")
    for i, branch in enumerate(branches):
        if not isinstance(branch, Mapping):
            raise DslError(f"{where}.any_of[{i}]: must be a filter object")
        if "zone" in branch:
            raise DslError(
                f"{where}.any_of[{i}]: a branch may not name a 'zone' -- the zones "
                f"are chosen once for the whole filter, so this one would be read "
                f"by nobody"
            )
        unknown = set(branch) - STATIC_FILTER_KEYS - COST_REDUCTION_FILTER_KEYS - {"zone"}
        if unknown:
            raise DslError(
                f"{where}.any_of[{i}]: unsupported filter keys {sorted(unknown)}"
            )
        _validate_reduction_any_of(branch, f"{where}.any_of[{i}]")


def _validate_cost_reduction(spec: Any, where: str) -> None:
    """One validator for every "costs {N} less", wherever it is written.

    A card's own `cost_reduction`, an activated ability's
    `cost.mana_reduction` and a graveyard cast's `mana_reduction` are three
    readers of one language -- `costs.reduction_amount` -- so they get one
    validator, or they drift about what "for each" and "if" mean.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must name exactly one of {sorted(COST_REDUCTION_KEYS)}")
    arithmetic = set(spec) & COST_REDUCTION_KEYS
    unknown = set(spec) - COST_REDUCTION_KEYS - {"condition"}
    if unknown:
        raise DslError(
            f"{where}: unknown reduction keys {sorted(unknown)} "
            f"(implemented: {sorted(COST_REDUCTION_KEYS)} plus an optional 'condition')"
        )
    if len(arithmetic) != 1:
        # Two would be paid at whichever the code read first, which is not
        # something a printed line ever says; none is a condition with nothing
        # to reduce.
        raise DslError(f"{where}: must name exactly one of {sorted(COST_REDUCTION_KEYS)}")
    key = next(iter(arithmetic))
    if key == "amount":
        amount = spec["amount"]
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            raise DslError(
                f"{where}.amount: a flat reduction is a positive integer, got {amount!r}"
            )
        if "condition" not in spec:
            # "Costs {3} less" with nothing to gate it is a card with a smaller
            # printed cost, written the long way -- and it would load clean.
            raise DslError(
                f"{where}: a flat 'amount' needs a 'condition' -- an unconditional "
                f"flat reduction is just a cheaper printed cost"
            )
    else:
        filt = spec[key]
        if not isinstance(filt, Mapping):
            raise DslError(f"{where}.{key}: needs a filter")
        # Same restriction as a static filter, for the same reason: this is
        # evaluated while deciding what is castable, before anything is on the
        # stack, so it may only read printed characteristics of the board.
        unknown = set(filt) - STATIC_FILTER_KEYS - COST_REDUCTION_FILTER_KEYS
        if unknown:
            raise DslError(f"{where}.{key}: unsupported filter keys {sorted(unknown)}")
        _validate_reduction_any_of(filt, f"{where}.{key}")
        refused = set(filt) & COST_REDUCTION_REFUSED_FILTER_KEYS
        if refused:
            raise DslError(
                f"{where}.{key}: {sorted(refused)} name a relation to one "
                f"permanent, and a reduction counts a board"
            )
        _check_owner_key(filt, f"{where}.{key}")
        _check_mana_cost_key(filt, f"{where}.{key}")
        _check_pt_keys(filt, f"{where}.{key}")
        validate_colorless_key(filt, f"{where}.{key}")
        validate_enchanted_by_key(filt, f"{where}.{key}")
        _check_reduction_type_names(filt, f"{where}.{key}")
        _validate_reduction_zones(filt, key, f"{where}.{key}")
    if "condition" in spec:
        _validate_cost_condition(spec["condition"], f"{where}.condition")


def _validate_static_count_filter(spec: Any, where: str) -> None:
    """A filter in a *counting* position -- ``{"count": ...}`` or ``exists``."""
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    _check_mana_cost_key(spec, where)
    _check_pt_keys(spec, where)
    validate_colorless_key(spec, where)
    validate_enchanted_by_key(spec, where)
    zone = str(spec.get("zone", "battlefield"))
    if zone not in STATIC_COUNT_ZONES:
        raise DslError(
            f"{where}.zone: unknown zone {zone!r} (countable: {sorted(STATIC_COUNT_ZONES)})"
        )
    if zone == "battlefield":
        unknown = set(spec) - STATIC_COUNT_FILTER_KEYS
        if unknown:
            raise DslError(f"{where}: unsupported filter keys {sorted(unknown)}")
        _check_owner_key(spec, where)
        return
    unknown = set(spec) - STATIC_ZONE_FILTER_KEYS
    if unknown:
        raise DslError(
            f"{where}: a card in {zone} has a printed face and an owner and nothing else; "
            f"unsupported keys {sorted(unknown)}"
        )
    controller = spec.get("controller", "you")
    if controller not in ("you", "opponent", "any"):
        raise DslError(
            f"{where}.controller: must be 'you', 'opponent' or 'any', got {controller!r}"
        )


def _validate_static_condition(condition: Any, where: str) -> None:
    """A static may ask about pipeline *inputs* only.

    Much smaller than the ``if``-effect condition language, and for the same
    reason ``affects`` filters are: anything that reads a *derived*
    characteristic would let one static depend on another's output, and the
    fixed-order pipeline has no way to resolve that.  Counters on the source,
    printed characteristics of the board, the contents of a zone and whose turn
    it is are all inputs, so all four are safe; every one of them is settled
    before the first layer applies.
    """
    if condition is None or isinstance(condition, bool):
        return
    if not isinstance(condition, Mapping):
        raise DslError(f"{where}: a static condition must be an object")
    heads = [k for k in STATIC_CONDITION_HEADS if k in condition]
    if len(heads) != 1:
        raise DslError(
            f"{where}: a static condition names exactly one of "
            f"{list(STATIC_CONDITION_HEADS)}, got {sorted(condition)}"
        )
    head = heads[0]
    extra = set(condition) - {head} - ({"left", "right"} if head == "cmp" else set())
    if extra:
        raise DslError(f"{where}: unsupported keys {sorted(extra)} beside {head!r}")

    if head == "counters":
        spec = condition["counters"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.counters: must be an object")
        unknown = set(spec) - {"counter", "amount", "op"}
        if unknown:
            raise DslError(f"{where}.counters: unsupported keys {sorted(unknown)}")
        op = str(spec.get("op", ">="))
        if op not in STATIC_CONDITION_OPS:
            raise DslError(f"{where}.counters: unknown comparison {op!r}")
        if "counter" in spec:
            # "As long as it has an indestructible counter on it…" -- read off
            # the source's own `counters` dict by exact key, so a near-miss
            # spelling switches the static off for ever.
            _check_counter_kind(spec["counter"], f"{where}.counters.counter")
    elif head in ("all", "any"):
        if not isinstance(condition[head], list) or not condition[head]:
            raise DslError(f"{where}.{head}: takes a non-empty list of conditions")
        for i, sub in enumerate(condition[head]):
            _validate_static_condition(sub, f"{where}.{head}[{i}]")
    elif head == "not":
        _validate_static_condition(condition["not"], f"{where}.not")
    elif head == "exists":
        _validate_static_count_filter(condition["exists"], f"{where}.exists")
    elif head == "exists_derived":
        spec = condition["exists_derived"]
        # The battlefield only: derived characteristics are a permanent's, and
        # a card in a graveyard has nothing but its printed face.
        if isinstance(spec, Mapping) and spec.get("zone", "battlefield") != "battlefield":
            raise DslError(
                f"{where}.exists_derived: reads permanents on the battlefield; "
                f"got zone {spec.get('zone')!r}"
            )
        _validate_static_count_filter(spec, f"{where}.exists_derived")
    elif head == "is_your_turn":
        if not isinstance(condition["is_your_turn"], bool):
            raise DslError(f"{where}.is_your_turn: must be true or false")
    elif head == "has_flag":
        # Read by exact string off the source's `flags`, so an empty or
        # non-string flag would switch the static off for ever.
        flag = condition["has_flag"]
        if not isinstance(flag, str) or not flag:
            raise DslError(f"{where}.has_flag: must be a non-empty flag name")
    elif head == "is_attached":
        # Not defaulted: `{"is_attached": false}` is the other half of
        # reconfigure ("it is a creature while unattached"), and a bare
        # truthiness test would read a typo'd string as `true`.
        if not isinstance(condition["is_attached"], bool):
            raise DslError(f"{where}.is_attached: must be true or false")
    elif head == "is_monstrous":
        # Not defaulted, on `is_attached`'s terms: a typo'd string read for
        # truthiness would switch the static on before monstrosity ever ran.
        if not isinstance(condition["is_monstrous"], bool):
            raise DslError(f"{where}.is_monstrous: must be true or false")
    elif head == "top_of_library":
        spec = condition["top_of_library"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.top_of_library: must be an object")
        # The same printed-face-and-owner rule every off-battlefield filter
        # follows: the top card of a library is not tapped, attacking or
        # attached to anything, and a key that loads and matches nothing is
        # how a card comes to do less than it prints.
        unknown = set(spec) - (STATIC_ZONE_FILTER_KEYS - {"zone"})
        if unknown:
            raise DslError(
                f"{where}.top_of_library: a card in a library has a printed face and "
                f"an owner and nothing else; unsupported keys {sorted(unknown)}"
            )
        controller = spec.get("controller", "you")
        if controller not in ("you", "opponent", "any"):
            raise DslError(
                f"{where}.top_of_library.controller: must be 'you', 'opponent' or "
                f"'any', got {controller!r}"
            )
    elif head == "has_city_s_blessing":
        who = condition["has_city_s_blessing"]
        if not isinstance(who, str) or who not in STATIC_LIFE_PLAYERS:
            raise DslError(
                f"{where}.has_city_s_blessing: must name one of "
                f"{sorted(STATIC_LIFE_PLAYERS)}, got {who!r}"
            )
    elif head == "is_monarch":
        who = condition["is_monarch"]
        if not isinstance(who, str) or who not in STATIC_MONARCH_PLAYERS:
            raise DslError(
                f"{where}.is_monarch: must name one of "
                f"{sorted(STATIC_MONARCH_PLAYERS)}, got {who!r}"
            )
    elif head == "cmp":
        op = str(condition["cmp"])
        if op not in STATIC_CONDITION_OPS:
            raise DslError(f"{where}.cmp: unknown comparison {op!r}")
        for side in ("left", "right"):
            if side not in condition:
                raise DslError(f"{where}: a 'cmp' condition needs both 'left' and 'right'")
            _validate_static_value(condition[side], f"{where}.{side}")


def _validate_static_extreme_value(spec: Any, where: str) -> None:
    """Dragon Man, Reformed Robot: "power is equal to the greatest mana value
    among noncreature permanents you control and noncreature cards in your
    graveyard."

    The effect side's `extreme_value`, narrowed to what a static may read. A
    printed mana value is a pipeline input on `mana_symbols`' terms, so ``of`` is
    ``mana_value`` and nothing else: a power or toughness is a layer's output,
    and an anthem sized by one would depend on another static. ``objects`` is a
    static counting filter, or a ``union`` of them for a pool that spans zones.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    if unknown := set(spec) - {"of", "pick", "objects"}:
        raise DslError(f"{where}: unsupported keys {sorted(unknown)}")
    if spec.get("of", "mana_value") != "mana_value":
        raise DslError(
            f"{where}.of: a static can only read 'mana_value' -- a printed number; "
            f"power and toughness are layer outputs, got {spec.get('of')!r}"
        )
    if spec.get("pick", "greatest") not in ("greatest", "least"):
        raise DslError(f"{where}.pick: 'greatest' or 'least', got {spec.get('pick')!r}")
    objects = spec.get("objects")
    if not isinstance(objects, Mapping) or not objects:
        # An empty filter is every permanent on the table, opponents' included.
        raise DslError(f"{where}: needs 'objects', a counting filter or a 'union' of them")
    if "union" in objects:
        branches = objects["union"]
        if set(objects) != {"union"} or not isinstance(branches, list) or len(branches) < 2:
            raise DslError(
                f"{where}.objects.union: a list of at least two counting filters "
                f"and nothing beside it"
            )
        for i, branch in enumerate(branches):
            _validate_static_count_filter(branch, f"{where}.objects.union[{i}]")
        return
    _validate_static_count_filter(objects, f"{where}.objects")


def _validate_static_value(value: Any, where: str) -> None:
    """Static abilities allow ``const``, ``count`` and the per-player leaves."""
    if isinstance(value, int):
        return
    if not isinstance(value, Mapping):
        raise DslError(f"{where}: static values must be an int, 'const' or 'count'")
    if set(value) - STATIC_VALUE_KEYS:
        raise DslError(
            f"{where}: static values may only use {sorted(STATIC_VALUE_KEYS)}, got {sorted(value)}"
        )
    if not value:
        # `{}` passes the difference check above and then falls off the end of
        # `_static_value` -- which used to mean 0, and now means a crash. Named
        # here so it is a load error with a name on it instead.
        raise DslError(f"{where}: an empty object is not a static value")
    if "count" in value:
        _validate_static_count_filter(value["count"], f"{where}.count")
    if "times" in value:
        # Recursive, so the factors are held to this same list -- a `times`
        # holding an effect-side leaf would otherwise slip past the difference
        # check above, which only reads the outermost keys, and reach
        # `_static_value` as vocabulary it cannot evaluate.
        factors = value["times"]
        if not isinstance(factors, list) or len(factors) < 2:
            raise DslError(
                f"{where}.times: a list of at least two factors to multiply, "
                f'e.g. [{{"count": {{...}}}}, {{"const": 2}}]'
            )
        for i, factor in enumerate(factors):
            _validate_static_value(factor, f"{where}.times[{i}]")
    if "sum" in value:
        # "At least 7 life more than your starting life total" -- Righteous
        # Valkyrie, as `life >= starting + 7`. Recursive for the reason `times`
        # is: the terms are held to this same list, or an effect-side leaf
        # inside a `sum` would slip past the outermost-keys check above.
        terms = value["sum"]
        if not isinstance(terms, list) or len(terms) < 2:
            raise DslError(
                f"{where}.sum: a list of at least two terms to add, "
                f'e.g. [{{"starting_life_of": "you"}}, {{"const": 7}}]'
            )
        for i, term in enumerate(terms):
            _validate_static_value(term, f"{where}.sum[{i}]")
    if "starting_life_of" in value:
        # Rule 103.4: one seat's starting life total. A static's source has a
        # controller and nothing else to aim at, so the spec is "you" -- the
        # plural words would sum a number no printed sentence means.
        who = value["starting_life_of"]
        if who != "you":
            raise DslError(
                f"{where}.starting_life_of: a static can only ask about 'you' "
                f"(one seat's starting life total, rule 103.4), got {who!r}"
            )
    if "greatest_commander_mana_value" in value:
        # "Among your commanders": one seat's, for `starting_life_of`'s reason.
        who = value["greatest_commander_mana_value"]
        if who != "you":
            raise DslError(
                f"{where}.greatest_commander_mana_value: a static can only ask "
                f"about 'you' (your commanders), got {who!r}"
            )
    if "extreme_value" in value:
        _validate_static_extreme_value(value["extreme_value"], f"{where}.extreme_value")
    if "permanents_entered_this_turn" in value:
        # Kinbinding: "Creatures you control get +X/+X, where X is the number of
        # creatures that entered the battlefield under your control this turn."
        #
        # Safe inside a static for the reason `counters_on` is. The turn ledger
        # is a pipeline **input**: `EnteredPermanent` is a snapshot written once,
        # at the moment of entry, and nothing in the characteristics pipeline can
        # write to it -- so an anthem sized by it cannot come to depend on another
        # static's output and the fixed order of layers-lite stays acyclic.
        #
        # `count` is the near miss and is wrong in both directions, which is the
        # whole reason the ledger exists: a board count is true of a creature that
        # has sat there since turn three and false of one that entered this turn
        # and died.
        #
        # Validated by the *same* filter check the effect side uses, so
        # `controller` stays required -- an omitted clause would silently count
        # the opponents' arrivals too.
        validate_entered_filter(
            value["permanents_entered_this_turn"], f"{where}.permanents_entered_this_turn"
        )
    if "counters_on" in value:
        # "Creatures you control of the chosen type get +1/+1 for each charge
        # counter on this artifact" -- Door of Destinies. Safe inside a static
        # for exactly the reason the `counters` *condition* head already is: a
        # counter is a pipeline **input**, placed and removed by primitives, and
        # no layer can change one. So an anthem sized by a counter count cannot
        # come to depend on another static's output, and the fixed order stays
        # acyclic. The condition head could only switch a fixed anthem on and
        # off; this scales one.
        #
        # The filter goes through the *static* counting validator, so it obeys
        # the same printed-face-and-owner rule every static filter does.
        validate_counters_on(
            value["counters_on"],
            f"{where}.counters_on",
            validate_objects=_validate_static_count_filter,
        )
    if "mana_symbols" in value:
        # Chroma, and Primalcrux is the reason it is here as well as in the
        # effect language: "its power and toughness are each equal to the number
        # of green mana symbols in the mana costs of permanents you control" is
        # a `set_pt` static. Safe for the reason a zone count is -- a *printed*
        # mana cost is a pipeline input, and no layer can change one.
        validate_mana_symbols(
            value["mana_symbols"],
            f"{where}.mana_symbols",
            validate_objects=_validate_static_count_filter,
        )
    if isinstance(value.get("spells_cast_this_turn"), Mapping):
        # The effect side's typed form, `{"player": …, "filter": …}`. Refused by
        # name rather than by the generic message below, which would read as
        # though the leaf itself were unknown here.
        raise DslError(
            f"{where}.spells_cast_this_turn: a static takes the bare player spec "
            f"only, e.g. 'opponent' (an opponent has cast a spell this turn), "
            f"got {value['spells_cast_this_turn']!r}"
        )
    for key in (
        STATIC_LIFE_KEYS
        | STATIC_POISON_KEYS
        | STATIC_MANA_POOL_KEYS
        | STATIC_SPELLS_CAST_KEYS
        | STATIC_DEATHS_KEYS
    ) & set(value):
        who = value[key]
        if not isinstance(who, str) or who not in STATIC_LIFE_PLAYERS:
            raise DslError(
                f"{where}.{key}: must name one of {sorted(STATIC_LIFE_PLAYERS)}, got {who!r}"
            )
    for key in PER_PLAYER_COUNT_KEYS & set(value):
        # "As long as an opponent controls more lands than you" -- Verge Rangers.
        # Here as well as in the effect language, because the same printed clause
        # arrives as an intervening-`if` on one card and an "as long as" on the
        # next, and a leaf in one language only would load and read 0 in the
        # other. The filter is checked by the *static* counting validator, so it
        # obeys the same printed-face-and-owner rule every static filter does.
        validate_per_player_count(
            value[key],
            f"{where}.{key}",
            validate_objects=_validate_static_count_filter,
        )
