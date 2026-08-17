"""The condition DSL -- boolean tests used by ``if`` effects, intervening-if
clauses on triggers, and static ability conditions.

    {"cmp": ">=", "left": {...}, "right": {...}}
    {"all": [...]}  {"any": [...]}  {"not": {...}}
    {"exists": {selector}}
    {"zone_is": "battlefield"}
    {"kicked": true}
    {"evoked": true}
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..errors import DslError
from .context import EffectContext

if TYPE_CHECKING:  # pragma: no cover
    from ..state import GameState

CONDITION_KEYS = frozenset(
    {
        "cmp",
        "left",
        "right",
        "all",
        "any",
        "not",
        "exists",
        "zone_is",
        "is_your_turn",
        "kicked",
        "evoked",
        "cast_from_graveyard",
        # Overload (702.96a): "change its text by replacing all instances of
        # 'target' with 'each'". There is no rewriting a printed sentence, and
        # the two halves really are two effects, so the card branches on this.
        "overloaded",
        "has_city_s_blessing",
        # "If you're the monarch…" (721). Takes a player spec, so a card can also
        # ask it of somebody else.
        "is_monarch",
        # "…if there is **no** monarch" -- Crown of Gondor. Deliberately its own
        # key and not `{"not": {"is_monarch": "you"}}`, which is a different
        # question: that negation is also true while an *opponent* holds the
        # crown, which is precisely the case the card must not fire in.
        "no_monarch",
        # "…if it isn't renowned". A one-way word written by `set_flag`.
        "has_flag",
        # Prowl: "…if a player was dealt combat damage this turn by a Faerie or
        # a Rogue". A list of creature subtypes, true when *any* of them dealt
        # combat damage to a player this turn.
        "combat_damage_by",
    }
)


def evaluate(ctx: EffectContext, cond: Any) -> bool:
    """Evaluate a condition in an existing effect context."""
    if cond is None:
        return True
    if isinstance(cond, bool):
        return cond
    if not isinstance(cond, Mapping):
        raise DslError(f"unparsable condition {cond!r}")

    from .values import evaluate_value

    if "all" in cond:
        return all(evaluate(ctx, c) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(ctx, c) for c in cond["any"])
    if "not" in cond:
        return not evaluate(ctx, cond["not"])
    if "exists" in cond:
        from .selectors import resolve_pool

        return bool(resolve_pool(ctx, cond["exists"]))
    if "zone_is" in cond:
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        return obj is not None and obj.zone.value == cond["zone_is"]
    if "kicked" in cond:
        # Two sources, because the flag has two lifetimes. While the spell
        # resolves the StackItem is authoritative and nothing is on the
        # object yet; once it is a permanent the StackItem is gone and the
        # object is. An ETB trigger only ever sees the second, which is why
        # "if it was kicked" read False on every permanent before this.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        was_kicked = ctx.kicked or (obj is not None and obj.cast_kicked)
        return was_kicked == bool(cond["kicked"])
    if "overloaded" in cond:
        # Written onto the object *before* `spell_effects` run, so this reads
        # the object in both lifetimes -- the same shape `kicked` has, and for
        # the same reason: an overloaded permanent's own enters trigger sees
        # only the object, the StackItem having gone.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        was_overloaded = obj is not None and obj.cast_overloaded
        return was_overloaded == bool(cond["overloaded"])
    if "evoked" in cond:
        # Only ever read on the battlefield -- "it's sacrificed when it
        # enters" is an ETB trigger -- but written the same way as `kicked`
        # so the two cannot drift.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        was_evoked = obj is not None and obj.cast_evoked
        return was_evoked == bool(cond["evoked"])
    if "cast_from_graveyard" in cond:
        # "If this spell was cast from a graveyard, create ten of those tokens
        # instead." Read while the spell is still resolving, so `ctx.source_oid`
        # is the spell itself.
        #
        # `zone_is` cannot answer this: it reports the source's *current* zone,
        # which for any resolving sorcery is the stack, identically whether it
        # was cast from hand or from the graveyard.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        from_graveyard = obj is not None and obj.cast_from_graveyard
        return from_graveyard == bool(cond["cast_from_graveyard"])
    if "combat_damage_by" in cond:
        # Prowl. Answered from the turn ledger rather than from the board,
        # because by the time the spell is cast the creature that got through
        # may be dead, bounced or no longer a Faerie -- and none of those undo
        # the damage the condition is about.
        wanted = cond["combat_damage_by"]
        names = {str(wanted)} if isinstance(wanted, str) else {str(w) for w in wanted}
        return bool(names & ctx.state.turn_ledger.combat_damage_types)
    if "has_flag" in cond:
        # Renown's "if it isn't renowned", written as `{"not": {"has_flag":
        # "renowned"}}`. Asked of the ability's own source, which is the only
        # thing that can have become the word.
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        return obj is not None and str(cond["has_flag"]) in obj.flags
    if "has_city_s_blessing" in cond:
        from .selectors import select_players

        pids = select_players(ctx, cond["has_city_s_blessing"])
        return any(ctx.state.players[p].has_city_s_blessing for p in pids)
    if "is_monarch" in cond:
        from .selectors import select_players

        # `any`, matching `has_city_s_blessing` above -- and unlike the blessing
        # it can never be true of two of them, so "if an opponent is the monarch"
        # over `each_opponent` is exact rather than approximate.
        pids = select_players(ctx, cond["is_monarch"])
        return any(ctx.state.monarch == p for p in pids)
    if "no_monarch" in cond:
        return (ctx.state.monarch is None) == bool(cond["no_monarch"])
    if "is_your_turn" in cond:
        return (ctx.state.active_player == ctx.controller) == bool(cond["is_your_turn"])
    if "cmp" in cond:
        op = cond["cmp"]
        left = evaluate_value(ctx, cond.get("left"))
        right = evaluate_value(ctx, cond.get("right"))
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op in ("=", "=="):
            return left == right
        if op == "!=":
            return left != right
        raise DslError(f"unknown comparison operator {op!r}")

    raise DslError(f"unknown condition {sorted(cond)}")


def evaluate_condition(
    state: GameState,
    cond: Any,
    *,
    controller: int,
    source: int | None = None,
    bindings: Any = None,
) -> bool:
    """Evaluate a condition without an effect already running.

    Used by trigger intervening-if clauses, which are checked both when the
    ability would trigger and again as it resolves.

    ``bindings`` are what the *event* carried -- the creature that entered, the
    land that was played, how many blockers there were. Without them a
    condition may only ask about the board and about its own source, which is
    enough for Threshold and not for evolve: "if that creature has greater
    power than this creature" is a comparison between the trigger's source and
    the object the event was about, and with no bindings the second half reads
    zero and the ability silently never fires.
    """
    ctx = EffectContext(
        state=state,
        controller=controller,
        source_oid=source,
        bindings=dict(bindings) if bindings else {},
    )
    return evaluate(ctx, cond)


def validate_condition(cond: Any, where: str) -> None:
    """Load-time validation of a condition tree."""
    if cond is None or isinstance(cond, bool):
        return
    if not isinstance(cond, Mapping):
        raise DslError(f"{where}: condition must be an object")
    unknown = set(cond) - CONDITION_KEYS
    if unknown:
        raise DslError(f"{where}: unknown condition keys {sorted(unknown)}")
    from .selectors import validate_selector
    from .values import validate_value

    for key in ("all", "any"):
        if key in cond:
            if not isinstance(cond[key], list):
                raise DslError(f"{where}: {key} takes a list")
            for i, sub in enumerate(cond[key]):
                validate_condition(sub, f"{where}.{key}[{i}]")
    if "not" in cond:
        validate_condition(cond["not"], f"{where}.not")
    if "exists" in cond:
        validate_selector(cond["exists"], f"{where}.exists")
    if "cmp" in cond:
        validate_value(cond.get("left"), f"{where}.left")
        validate_value(cond.get("right"), f"{where}.right")
    # Not defaulted and not truthiness-tested: `{"no_monarch": "false"}` is a
    # non-empty string and would read as `true`, which would make Crown of
    # Gondor's trigger fire in exactly the case it must not.
    if "no_monarch" in cond and not isinstance(cond["no_monarch"], bool):
        raise DslError(f"{where}.no_monarch: must be true or false")
    if "is_monarch" in cond:
        from .selectors import PLAYER_SPEC_NAMES

        who = cond["is_monarch"]
        if isinstance(who, str) and who not in PLAYER_SPEC_NAMES:
            raise DslError(
                f"{where}.is_monarch: must name one of {sorted(PLAYER_SPEC_NAMES)} "
                f"or a target/binding, got {who!r}"
            )
    if "combat_damage_by" in cond:
        wanted = cond["combat_damage_by"]
        names = [wanted] if isinstance(wanted, str) else wanted
        if not isinstance(names, (list, tuple)) or not names:
            raise DslError(
                f"{where}.combat_damage_by: needs a creature subtype, or a list of them"
            )
        if not all(isinstance(n, str) and n for n in names):
            # An empty or non-string entry would match nothing, and prowl's whole
            # content is which types got through -- so the alternative cost would
            # simply never be offered, on a card that reads as though it is.
            raise DslError(
                f"{where}.combat_damage_by: every entry must be a subtype name, got {names!r}"
            )
