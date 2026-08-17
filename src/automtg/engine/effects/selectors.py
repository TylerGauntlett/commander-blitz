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
        #: Whose hand/graveyard/library/exile to walk, as a full player spec
        #: rather than the three words ``controller`` allows -- so
        #: ``{"target": "t1"}`` scopes a zone to the one player a trigger
        #: targeted.  Bojuka Bog: "exile **target player's** graveyard", which
        #: `controller: "any"` would turn into Relic of Progenitus.
        #:
        #: Battlefield selectors ignore it, and correctly: a permanent's
        #: controller is a property of the object, so `controller` is a filter
        #: there rather than a choice of which list to read.
        "player",
        #: "Equipped creature", "enchanted creature" -- the permanent this Aura
        #: or Equipment is attached to, read off the ability's source.  Already
        #: in ``STATIC_FILTER_KEYS``; this is the same word on the effect side.
        "attached",
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
        #: "…a creature spell that shares a creature type with **your
        #: commander**." Path of Ancestry. Takes a *player* rather than a
        #: binding name, which is why it is not a spelling of the clause above:
        #: nothing binds the commander, the commander is not what the trigger is
        #: about, and it is usually in the command zone rather than on the
        #: battlefield, so `_bound_oid` has nothing to find and `is_commander`
        #: asks the wrong question -- it is a predicate on the object being
        #: tested, not a reference to compare a different object against.
        #: A literal `subtypes` list cannot stand in either: which type matters
        #: is a property of the deck the card is played in.
        "shares_a_type_with_commander",
        #: "When **that mana** is spent to cast a spell…" -- Path of Ancestry,
        #: Opal Palace. A trigger filter only, matched against the spell: the
        #: permanents whose mana abilities paid for it are recorded on the spell
        #: by `pay_mana`, which is the only instant they are knowable.
        "paid_by",
        #: "…and each other creature that shares a color with it" -- radiance.
        #: The colour twin of the clause above, and it needs its own key for the
        #: same reason: `colors` takes a literal list written into the card, and
        #: which colour matters is decided by whatever was targeted. Read from
        #: **derived** colours on both sides, so a creature made black by
        #: another spell is caught. A colorless object shares a colour with
        #: nothing, itself included.
        "shares_a_color_with",
        "self_only",
        #: "…with the least toughness among creatures you control" -- bolster.
        #: Narrows the pool to whatever is tied for the extreme *after* every
        #: other clause has filtered it, because an extremum is a fact about the
        #: pool and not about any one candidate.
        "extreme",
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
        #: "…an unblocked attacking creature you control" -- ninjutsu. Asks
        #: whether anything is blocking *this attacker*, which is not the
        #: negation of `blocking`: that key is about a blocker, and these are
        #: two different creatures.
        "blocked",
        # "When the creature this card haunts dies…" -- a trigger filter only,
        # answered off the ability's source, which is the card sitting in exile
        # with the link on it. The haunted creature carries no record of it.
        "haunted_by",
        # "…the creature this card is encoded on" -- cipher, the same shape as
        # `haunted_by` and answered the same way, off the ability source.
        "encoded_by",
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
            seeded = _bound_oids(ctx, str(selector["binding"]))
        if set(selector) <= {"target", "binding"}:
            return seeded
        return _narrow_to_extreme(ctx, [oid for oid in seeded if matches(ctx, oid, selector)], selector)

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

    return _narrow_to_extreme(ctx, [oid for oid in candidates if matches(ctx, oid, selector)], selector)


#: What `extreme` may rank on. Derived characteristics only, and read through
#: `chars` -- "the creature with the least toughness" means the toughness it
#: actually has, counters and anthems included.
EXTREME_KEYS = frozenset({"power", "toughness", "mana_value"})


def _narrow_to_extreme(
    ctx: EffectContext, pool: list[int], selector: Mapping[str, Any]
) -> list[int]:
    """Keep only the objects tied for the highest or lowest of some quantity.

    "Choose a creature with the **least toughness** among creatures you
    control" -- bolster, and the shape every "greatest/least" line on a card
    wants. It cannot be a `_compare` clause: those test each candidate against a
    value known in advance, and an extremum is only knowable once the whole pool
    is in hand.

    Ties are all kept rather than broken here. Rule 701.36a has the *player*
    choose among equals, and `choose_objects` is already the thing that asks --
    so narrowing to one would silently take that choice away, and picking by oid
    would make it depend on the order permanents happened to arrive in.
    """
    spec = selector.get("extreme")
    if spec is None or not pool:
        return pool
    if not isinstance(spec, Mapping):
        raise DslError(f"bad extreme spec {spec!r}")
    of = str(spec.get("of", "power"))
    if of not in EXTREME_KEYS:
        raise DslError(f"cannot rank on {of!r}; extreme allows {sorted(EXTREME_KEYS)}")
    pick = str(spec.get("pick", "greatest"))
    if pick not in ("greatest", "least"):
        raise DslError(f"unknown extreme pick {pick!r}; use 'greatest' or 'least'")

    def rank(oid: int) -> int:
        if of == "mana_value":
            obj = ctx.state.objects.get(oid)
            return ctx.state.card_of(obj).mana_value if obj is not None else 0
        c = chars(ctx.state, oid)
        return c.power if of == "power" else c.toughness

    best = (max if pick == "greatest" else min)(rank(oid) for oid in pool)
    return [oid for oid in pool if rank(oid) == best]


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


def _commander_subtypes(ctx: EffectContext, who: str) -> frozenset[str]:
    """Every creature type the named players' commanders currently have.

    A separate clause from `shares_a_type_with` rather than a reserved binding
    name, because it takes a **player** and not an object: nothing binds the
    commander, the commander is not what the effect is about, and it is usually
    in the command zone rather than on the battlefield, so `_bound_oid` has
    nothing to find.

    The set itself comes from `characteristics.commander_subtypes`, shared with
    `triggers.matches_card_filter` so the two halves of the filter language
    cannot disagree about what a commander's types are.
    """
    from ..characteristics import commander_subtypes

    out: set[str] = set()
    for pid in select_players(ctx, who):
        out |= commander_subtypes(ctx.state, pid)
    return frozenset(out)


def _bound_oids(ctx: EffectContext, name: str) -> list[int]:
    """Every object bound under ``name`` -- one, or a whole set of them.

    A binding is one oid for the trigger bindings and snapshots that have always
    existed, and a **list** for an op that recorded what it chose (``as``).
    Amplify and devour both need the list form: "X is the number of cards
    revealed this way" and "for each creature devoured" are counts of a set that
    a player picked a moment ago, and no selector can name it afterwards -- the
    revealed cards are still in a hand full of others, and the devoured
    creatures are gone.
    """
    value = ctx.bindings.get(name)
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value if isinstance(v, int)]
    bound = _bound_oid(ctx, name)
    return [bound] if bound is not None else []


def _zone_owners(ctx: EffectContext, selector: Mapping[str, Any]) -> list[int]:
    """Whose hand/graveyard/library/exile this selector walks.

    ``player`` is the full player spec and takes precedence, because it can say
    things ``controller`` cannot: "target player's graveyard" is Bojuka Bog, and
    the nearest `controller` value -- `"any"` with `count: "all"` -- exiles every
    graveyard at the table, which is Relic of Progenitus. `select_players`
    already understood `{"target": ...}`; it simply had no caller here.
    """
    if "player" in selector:
        return select_players(ctx, selector["player"])
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

    # "…if it's a creature card **of the chosen type**." Herald's Horn asks this
    # about the top card of a library, where no trigger has bound an object and
    # no static is being computed -- so the substitution the characteristics
    # layer already does for `affects` and for trigger filters has to happen on
    # the effect side too. Resolved against the ability's own source, which is
    # the permanent that made the choice.
    if selector.get("subtypes"):
        from ..characteristics import resolve_chosen_subtypes

        selector = resolve_chosen_subtypes(
            selector, state.objects.get(ctx.source_oid) if ctx.source_oid else None
        )

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
    # "…put a +1/+1 counter on **equipped creature**." Blade of the Bloodchief.
    # `attached` had existed only in `STATIC_FILTER_KEYS`, where
    # `characteristics` reads it while applying a continuous effect -- which is
    # why "Equipped creature gets +1/-1" always worked and no *op* could reach
    # the same creature. Read off the ability's source, and off its remembered
    # attachment too, so a trigger that fires as the creature leaves can still
    # find it.
    if selector.get("attached"):
        source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        if source is None or oid not in (source.attached_to, source.last_attached_to):
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
    if (who := selector.get("shares_a_type_with_commander")) is not None and not (
        subtypes & _commander_subtypes(ctx, str(who))
    ):
        return False
    if (name := selector.get("shares_a_color_with")) is not None:
        # Radiance. The colour twin of the clause above, and the boundary is the
        # same one intimidate has: a **colorless** object shares a colour with
        # nothing, itself included, so an intersection is the right test and
        # "is not a different colour" would be its opposite.
        other = _bound_oid(ctx, str(name))
        if other is None:
            return False
        theirs = chars(state, other).colors if state.objects.get(other) else frozenset()
        if not (colors & theirs):
            return False

    controller = selector.get("controller")
    if controller == "you" and obj.controller != ctx.controller:
        return False
    if controller == "opponent" and obj.controller == ctx.controller:
        return False
    # A player spec rather than one of the three words -- "…among creatures
    # **they** control", scoped to the one opponent a `for_each_player` loop is
    # currently on. `"opponent"` cannot say it: it means every opponent at once,
    # so `extreme` would take one global maximum over the merged pool and, at a
    # pod, spare the opponent whose best creature is smaller.
    if isinstance(controller, Mapping) and obj.controller not in select_players(
        ctx, controller
    ):
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
    if "blocked" in selector:
        # "…an **unblocked** attacking creature you control" -- ninjutsu. Not
        # the negation of `blocking`, which is about a *blocker*: this asks
        # whether anything is blocking **this attacker**, and the two are
        # different creatures. A creature that is not attacking at all is not
        # blocked either, which is why `blocked: false` is paired with
        # `attacking: true` on every printed line of this shape.
        is_blocked = bool(combat and any(v == oid for v in combat.blockers.values()))
        if is_blocked != bool(selector["blocked"]):
            return False
    if (blocking := selector.get("blocking")) is not None:
        if isinstance(blocking, Mapping) and "binding" in blocking:
            # "…blocked by a creature without flanking": *which* attacker it is
            # blocking, not merely that it is blocking something. The plain
            # boolean cannot say it -- on a board with two combats it matches
            # every blocker in both -- so this names a trigger binding, the way
            # `shares_a_type_with` and `exclude_binding` do.
            bound = ctx.bindings.get(str(blocking["binding"]))
            attacker = bound if isinstance(bound, int) else None
            if attacker is None or combat is None or combat.blockers.get(oid) != attacker:
                return False
        elif bool(combat and combat.blocking(oid)) != bool(blocking):
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

    Honours ``count`` (an integer, ``"all"`` or ``"any"``), ``chooser``
    (``controller``, ``owner`` or ``none``) and ``random``.  When a choice is
    genuinely required this suspends and asks; otherwise it returns immediately.
    """
    pool = resolve_pool(ctx, selector)
    if not pool or selector is None:
        return []
    return (yield from pick_from_pool(ctx, pool, selector, prompt, purpose))


def pick_from_pool(
    ctx: EffectContext,
    pool: list[int],
    selector: Mapping[str, Any],
    prompt: str = "Choose",
    purpose: str = "choose",
    chooser: int | None = None,
) -> Generator[Any, list[int], list[int]]:
    """Apply a selector's ``count``/``chooser``/``random`` to a pool already built.

    Split out of ``choose_objects`` because not every pool comes from a zone.
    ``look_at_top`` bounds its own pool to the top N cards of a library and then
    wants exactly this narrowing, so the two share the ``count`` vocabulary
    rather than each inventing one -- which is what keeps ``"any"`` meaning the
    same thing wherever it is written.  ``chooser`` overrides the selector's own
    clause, for an op that already knows whose decision it is.
    """
    if not pool:
        return []

    count_spec = selector.get("count", "all")
    if count_spec == "all":
        return pool

    # "…put **any number of** creature cards from your hand onto the
    # battlefield."  A free subset: none of them, all of them, or anything
    # between, and the chooser decides.  Neither existing form says it --
    # `"all"` makes it mandatory, and a fixed number forces exactly that many --
    # so Last March of the Ents could not let you keep a creature in hand.
    # `ask_objects` always took distinct min/max bounds; only the spelling that
    # reaches them was missing, which is why this is a `count` form and not an op.
    if count_spec == "any":
        min_count, max_count = 0, len(pool)
    else:
        from .values import evaluate_value

        count = evaluate_value(ctx, count_spec)
        count = max(0, min(int(count), len(pool)))
        if count == 0:
            return []
        if count >= len(pool):
            return pool
        min_count = max_count = count

    if selector.get("random"):
        return ctx.state.rng.shuffled(pool)[:max_count]

    chooser_spec = selector.get("chooser", "controller")
    if chooser_spec == "none":
        return pool[:max_count]
    if chooser is None:
        chooser = ctx.controller
        if chooser_spec == "owner" and pool:
            chooser = ctx.state.objects[pool[0]].owner

    picked = yield from ask_objects(ctx, prompt, pool, min_count, max_count, chooser, purpose)
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
    if (
        controller is not None
        and not isinstance(controller, Mapping)
        and controller not in ("you", "opponent", "any")
    ):
        raise DslError(f"{where}: unknown controller clause {controller!r}")
    if "player" in selector:
        # Only zones that *belong* to a player have an owner to choose. On the
        # battlefield and the stack the list is shared, so `player` would be
        # silently ignored -- and a card that says "target player's" and quietly
        # means "everyone's" is the failure this validation exists to prevent.
        zone_name = selector.get("zone", "battlefield")
        if zone_name in ("battlefield", "stack"):
            raise DslError(
                f"{where}: 'player' scopes a zone somebody owns; the {zone_name} "
                f"is shared -- use 'controller' to filter it"
            )
    count = selector.get("count")
    if isinstance(count, str) and count not in ("all", "any"):
        raise DslError(f"{where}: unknown count {count!r}; use 'all', 'any' or a value")
    # "Any number" is a choice by definition, and both of these take the choice
    # away -- they would silently resolve the whole pool, which is `count: "all"`
    # wearing the wrong name.  A card that means "all" should say so.
    if count == "any":
        if selector.get("random"):
            raise DslError(f"{where}: count 'any' is a free choice; it cannot be random")
        if selector.get("chooser") == "none":
            raise DslError(f"{where}: count 'any' needs a chooser; use 'all' for no choice")
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
