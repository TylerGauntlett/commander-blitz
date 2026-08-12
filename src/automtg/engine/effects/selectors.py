"""The selector DSL -- how card JSON describes "which objects".

A selector is a dict.  Every key is optional and all present keys must match::

    {"zone": "battlefield", "controller": "you", "types": ["Creature"],
     "power": {"op": ">=", "value": {"const": 3}}, "count": 1, "chooser": "controller"}

Two shorthand forms bypass matching entirely:

    {"target": "t1"}     the refs chosen for target spec ``t1`` at cast time
    {"binding": "subject"}  the object a trigger bound (the land that was played, ...)
"""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..characteristics import chars
from ..enums import CardType, Zone
from ..errors import DslError
from .context import EffectContext, ask_objects

if TYPE_CHECKING:  # pragma: no cover
    from ..state import GameState

#: Card types a selector may name.  Derived from the enum rather than imported
#: from ``cards.loader``, which imports this module.
KNOWN_TYPES = frozenset(t.value for t in CardType)

#: Every key a selector may contain.  The loader validates against this set, so a
#: misspelled key is a load-time error rather than a silently ignored filter.
SELECTOR_KEYS = frozenset(
    {
        "zone",
        "controller",
        "types",
        #: "target artifact **or** enchantment".  ``types`` is a conjunction --
        #: ``["Artifact", "Enchantment"]`` means a permanent that is both -- and
        #: the any-of form already existed for ``subtypes`` and ``colors`` and
        #: simply had no type equivalent.  ``not_types`` cannot stand in: the
        #: complement is only equal for single-typed permanents, so it would
        #: refuse artifact creatures, which the printed line accepts.
        "any_types",
        #: A union of whole sub-selectors: matches when *any* of them does.
        #: "…among it and any number of commanders" is not a filter that can
        #: be narrowed into -- `self_only` and `is_commander` are both true
        #: of neither object -- so it needs an or across two descriptions
        #: rather than an or inside one key.
        "any_of",
        "not_types",
        "subtypes",
        "not_subtypes",
        "supertypes",
        "colors",
        "not_colors",
        "keywords",
        "not_keywords",
        "tapped",
        "attacking",
        "blocking",
        "is_commander",
        "is_token",
        "power",
        "toughness",
        "mana_value",
        "exclude_self",
        #: "each **other** attacking creature" -- exclude whichever object a
        #: trigger bound under this name.  `exclude_self` cannot do it: it
        #: compares against the *ability source*, which for Shared Animosity is
        #: the enchantment, so it removes nothing from a set of attackers and
        #: the count is over by exactly one.
        "exclude_binding",
        #: "…that shares a creature type with it".  Matches when the candidate's
        #: subtypes intersect those of the object bound under this name, read
        #: from *derived* characteristics on both sides so changelings and
        #: granted types count.  Not expressible with `subtypes`, which takes a
        #: literal list fixed when the card is written.
        "shares_a_type_with",
        "self_only",
        "count",
        "chooser",
        "random",
        "target",
        "binding",
        "object_kind",
        "name",
        "damaged",
        # "…until this permanent leaves the battlefield." Cards in exile that
        # *this* source put there, read back by its own leaves-trigger.
        "exiled_with",
        # "…dealt damage by this creature this turn." A trigger filter rather
        # than an object filter: answered from the per-turn damage ledger,
        # because the creature it asks about has usually just died.
        "damaged_by",
    }
)

ZONE_NAMES = {z.value: z for z in Zone}


def resolve_pool(ctx: EffectContext, selector: Mapping[str, Any] | None) -> list[int]:
    """Every object matching ``selector``, before ``count``/``chooser`` narrowing."""
    if selector is None:
        return []
    # `target` and `binding` name a pool directly rather than searching a zone.
    # On their own they are the whole selector; combined with other keys they are
    # the *source* and the rest still filters, which is what lets a card ask "is
    # the card I just bound a land?" without a condition language of its own.
    if "target" in selector or "binding" in selector:
        if "target" in selector:
            seeded = ctx.target_oids(str(selector["target"]))
        else:
            bound = _bound_oid(ctx, str(selector["binding"]))
            seeded = [bound] if bound is not None else []
        if set(selector) <= {"target", "binding"}:
            return seeded
        return [oid for oid in seeded if matches(ctx, oid, selector)]

    state = ctx.state
    zone_name = selector.get("zone", "battlefield")
    zone = ZONE_NAMES.get(zone_name)
    if zone is None:
        raise DslError(f"unknown zone {zone_name!r} in selector")

    candidates: list[int] = []
    if zone is Zone.BATTLEFIELD:
        candidates = list(state.battlefield)
    elif zone is Zone.STACK:
        candidates = [item.oid for item in state.stack if item.oid is not None]
    else:
        for pid in _zone_owners(ctx, selector):
            candidates.extend(state.players[pid].zone_list(zone))

    return [oid for oid in candidates if matches(ctx, oid, selector)]


def _bound_oid(ctx: EffectContext, name: str) -> int | None:
    """The oid a trigger bound under ``name``, if it bound an object at all.

    A binding is sometimes an oid and sometimes a snapshot dict (see the
    ``snapshot`` op), so both spellings are read here rather than at each of the
    three call sites that need them.
    """
    value = ctx.bindings.get(name)
    if isinstance(value, Mapping):
        value = value.get("oid")
    return int(value) if isinstance(value, int) else None


def _zone_owners(ctx: EffectContext, selector: Mapping[str, Any]) -> list[int]:
    controller = selector.get("controller", "you")
    if controller == "you":
        return [ctx.controller]
    if controller == "opponent":
        return ctx.opponents()
    return ctx.state.alive()


def matches(ctx: EffectContext, oid: int, selector: Mapping[str, Any]) -> bool:
    """Does one object satisfy every clause of ``selector``?"""
    state = ctx.state
    obj = state.objects.get(oid)
    if obj is None:
        return False

    zone_name = selector.get("zone", "battlefield")
    zone = ZONE_NAMES.get(zone_name)
    if zone is not None and obj.zone is not zone:
        return False

    card = state.card_of(obj)
    use_derived = obj.on_battlefield
    c = chars(state, oid) if use_derived else None
    types = c.types if c else card.types
    subtypes = c.subtypes if c else card.subtypes
    supertypes = c.supertypes if c else card.supertypes
    colors = c.colors if c else card.colors
    keywords = c.keywords if c else card.keywords

    if selector.get("exclude_self") and oid == ctx.source_oid:
        return False
    if selector.get("self_only") and oid != ctx.source_oid:
        return False
    if (name := selector.get("exclude_binding")) is not None and oid == _bound_oid(
        ctx, str(name)
    ):
        return False
    if (name := selector.get("shares_a_type_with")) is not None:
        other = _bound_oid(ctx, str(name))
        if other is None:
            return False
        theirs = chars(state, other).subtypes if state.objects.get(other) else frozenset()
        if not (subtypes & theirs):
            return False

    controller = selector.get("controller")
    if controller == "you" and obj.controller != ctx.controller:
        return False
    if controller == "opponent" and obj.controller == ctx.controller:
        return False

    if (want := selector.get("types")) and not set(want).issubset(types):
        return False
    # any-of, matching `subtypes` and `colors` above rather than `types`.
    if (want := selector.get("any_types")) and not (set(want) & types):
        return False
    # Checked here, alongside the other keys, so it composes with them: the
    # union narrows nothing on its own and everything outside it still filters.
    if (branches := selector.get("any_of")) and not any(
        matches(ctx, oid, branch) for branch in branches
    ):
        return False
    if (want := selector.get("not_types")) and set(want) & types:
        return False
    if (want := selector.get("subtypes")) and not (set(want) & subtypes):
        return False
    if (want := selector.get("not_subtypes")) and set(want) & subtypes:
        return False
    if (want := selector.get("supertypes")) and not set(want).issubset(supertypes):
        return False
    if (want := selector.get("colors")) and not (set(want) & colors):
        return False
    if (want := selector.get("not_colors")) and set(want) & colors:
        return False
    if (want := selector.get("keywords")) and not set(want).issubset(keywords):
        return False
    if (want := selector.get("not_keywords")) and set(want) & keywords:
        return False
    if (want := selector.get("name")) and card.name != want:
        return False

    if "tapped" in selector and bool(obj.tapped) != bool(selector["tapped"]):
        return False
    if "is_commander" in selector and bool(obj.is_commander) != bool(selector["is_commander"]):
        return False
    if "is_token" in selector and bool(obj.is_token) != bool(selector["is_token"]):
        return False
    if "damaged" in selector and bool(obj.damage > 0) != bool(selector["damaged"]):
        return False
    if "exiled_with" in selector:
        # "Return the exiled card" -- the cards *this* permanent exiled, and no
        # others. A plain `{"zone": "exile"}` filter matches every card in exile
        # from every source, so returning over it would hand back cards this
        # card never touched, which is a different card rather than an
        # approximation of this one.
        who = selector["exiled_with"]
        want = ctx.source_oid if who == "self" else who
        if obj.exiled_by is None or obj.exiled_by != want:
            return False

    combat = state.combat
    if "attacking" in selector and bool(combat and combat.attacking(oid)) != bool(
        selector["attacking"]
    ):
        return False
    if "blocking" in selector and bool(combat and combat.blocking(oid)) != bool(
        selector["blocking"]
    ):
        return False

    if (spec := selector.get("power")) is not None:
        value = c.power if c else (card.power or 0)
        if not _compare(value, spec, ctx):
            return False
    if (spec := selector.get("toughness")) is not None:
        value = c.toughness if c else (card.toughness or 0)
        if not _compare(value, spec, ctx):
            return False
    if (spec := selector.get("mana_value")) is not None and not _compare(
        card.mana_value, spec, ctx
    ):
        return False

    return True


def _compare(value: int, spec: Any, ctx: EffectContext) -> bool:
    from .values import evaluate_value

    if isinstance(spec, int):
        return value == spec
    if not isinstance(spec, Mapping):
        raise DslError(f"bad comparison spec {spec!r}")
    op = spec.get("op", ">=")
    other = evaluate_value(ctx, spec.get("value", 0))
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
    raise DslError(f"unknown comparison operator {op!r}")


def choose_objects(
    ctx: EffectContext,
    selector: Mapping[str, Any] | None,
    prompt: str = "Choose",
    purpose: str = "choose",
) -> Generator[Any, list[int], list[int]]:
    """Resolve a selector all the way to a concrete list of oids.

    Honours ``count`` (an integer or ``"all"``), ``chooser`` (``controller``,
    ``owner`` or ``none``) and ``random``.  When a choice is genuinely required
    this suspends and asks; otherwise it returns immediately.
    """
    pool = resolve_pool(ctx, selector)
    if not pool or selector is None:
        return []

    count_spec = selector.get("count", "all")
    if count_spec == "all":
        return pool

    from .values import evaluate_value

    count = evaluate_value(ctx, count_spec)
    count = max(0, min(int(count), len(pool)))
    if count == 0:
        return []
    if count >= len(pool):
        return pool

    if selector.get("random"):
        return ctx.state.rng.shuffled(pool)[:count]

    chooser_spec = selector.get("chooser", "controller")
    if chooser_spec == "none":
        return pool[:count]
    chooser = ctx.controller
    if chooser_spec == "owner" and pool:
        chooser = ctx.state.objects[pool[0]].owner

    picked = yield from ask_objects(ctx, prompt, pool, count, count, chooser, purpose)
    return picked


def select_players(ctx: EffectContext, spec: Any) -> list[int]:
    """Resolve a player specification to a list of player ids."""
    state: GameState = ctx.state
    if spec is None:
        return [ctx.controller]
    if isinstance(spec, int):
        return [spec] if state.is_alive(spec) else []
    if isinstance(spec, str):
        if spec == "you" or spec == "controller":
            return [ctx.controller]
        if spec == "each_opponent" or spec == "opponent":
            return ctx.opponents()
        if spec == "each_player" or spec == "all":
            return state.alive()
        if spec == "active_player":
            return [state.active_player]
        raise DslError(f"unknown player spec {spec!r}")
    if isinstance(spec, Mapping):
        if "target" in spec:
            return ctx.target_players(str(spec["target"]))
        if "controller_of" in spec:
            binding = ctx.bindings.get(str(spec["controller_of"]))
            if isinstance(binding, Mapping):
                pid = binding.get("controller")
                return [int(pid)] if pid is not None else []
            obj = state.objects.get(int(binding)) if binding is not None else None
            return [obj.controller] if obj else []
        if "owner_of" in spec:
            binding = ctx.bindings.get(str(spec["owner_of"]))
            if isinstance(binding, Mapping):
                pid = binding.get("owner")
                return [int(pid)] if pid is not None else []
            obj = state.objects.get(int(binding)) if binding is not None else None
            return [obj.owner] if obj else []
        if "binding" in spec:
            value = ctx.bindings.get(str(spec["binding"]))
            return [int(value)] if isinstance(value, int) else []
    raise DslError(f"unparsable player spec {spec!r}")


def validate_selector(selector: Any, where: str) -> None:
    """Load-time check that a selector uses only known keys."""
    if selector is None:
        return
    if not isinstance(selector, Mapping):
        raise DslError(f"{where}: selector must be an object, got {type(selector).__name__}")
    unknown = set(selector) - SELECTOR_KEYS
    if unknown:
        raise DslError(f"{where}: unknown selector keys {sorted(unknown)}")
    zone = selector.get("zone")
    if zone is not None and zone not in ZONE_NAMES:
        raise DslError(f"{where}: unknown zone {zone!r}")
    chooser = selector.get("chooser")
    if chooser is not None and chooser not in ("controller", "owner", "none"):
        raise DslError(f"{where}: unknown chooser {chooser!r}")
    controller = selector.get("controller")
    if controller is not None and controller not in ("you", "opponent", "any"):
        raise DslError(f"{where}: unknown controller clause {controller!r}")
    # A misspelled type in an any-of clause matches nothing and narrows the
    # selector silently -- "target artifact or enchantmnet" would quietly become
    # "target artifact".  Checked here rather than in the loader's per-op guards
    # because every selector, on every op and every target spec, comes through.
    for key in ("types", "any_types", "not_types"):
        for name in selector.get(key) or ():
            if name not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown card type {name!r} in {key!r}")
    branches = selector.get("any_of")
    if branches is not None:
        if not isinstance(branches, (list, tuple)) or len(branches) < 2:
            raise DslError(f"{where}: any_of takes a list of at least two selectors")
        for i, branch in enumerate(branches):
            # A branch naming a zone would be read as a filter on the pool the
            # outer selector already chose, which is not what it looks like.
            if isinstance(branch, Mapping) and "zone" in branch:
                raise DslError(
                    f"{where}.any_of[{i}]: put 'zone' on the outer selector; a "
                    f"branch filters the pool it already chose"
                )
            validate_selector(branch, f"{where}.any_of[{i}]")
    if "any_types" in selector and len(selector.get("any_types") or ()) < 2:
        raise DslError(f"{where}: any_types needs at least two types; use 'types' for one")


def sorted_candidates(state: GameState, oids: Sequence[int]) -> list[int]:
    """Deterministic ordering for target enumeration."""
    return sorted(oids, key=lambda oid: (state.objects[oid].def_id, oid))
