"""Effect ops for life totals and damage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import DslError
from ..events import EventType
from ..primitives import (
    damage_permanent,
    damage_player,
    gain_life,
    lose_life,
    shield_player,
)
from . import register
from .context import EffectContext
from .selectors import resolve_pool, select_players
from .values import evaluate_value


@register("gain_life")
def op_gain_life(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        gain_life(ctx.state, pid, amount, source=ctx.source_oid)


@register("lose_life")
def op_lose_life(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        lose_life(ctx.state, pid, amount, source=ctx.source_oid)


@register("add_poison")
def op_add_poison(ctx: EffectContext, spec: Mapping[str, Any]):
    """"That player gets N poison counters." Poisonous, and infect's other half.

    A counter on the *player*, not a second life total. Ten of them is lethal
    (704.5c) and the loss has its own reason, because a player eliminated at 40
    life did not run out of life and a log saying so would be lying about how
    the game ended.

    Poison only goes up in the cards this engine has, so there is no
    `remove_poison` yet -- and adding one speculatively would be a vocabulary
    item with no card behind it.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    if amount <= 0:
        return
    for pid in select_players(ctx, spec.get("player", "opponent")):
        ctx.state.players[pid].poison += amount
        ctx.state.emit(
            EventType.POISON_ADDED,
            player=pid,
            source=ctx.source_oid,
            amount=amount,
            total=ctx.state.players[pid].poison,
        )


@register("prevent_damage")
def op_prevent_damage(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Prevent all damage that would be dealt to you this turn." (Selfless
    Squire, Fog, Holy Day.)

    The same two words the `prevent_damage` **static** prints, and a different
    thing -- exactly the relationship `cant_block` the op has with `cant_block`
    the static, and for the same three reasons. The static is absorb N
    (702.63a): `characteristics.prevented_damage(state, oid)` reads it off
    `_battlefield_statics` and matches each entry's `affects` filter against a
    **permanent**, it is per source and per instance rather than a blanket, and
    it is continuous while its source stands on the battlefield. So it can say
    "prevent 1 damage to this creature, while I am here" and it can say nothing
    about a *seat*, nothing about "all", and nothing about "this turn" -- a
    Squire carrying one would fog its controller on every future turn too, which
    is a Worship. `static_filter_keys` has no way to name a player at all.

    This op is that sentence with the subject and the clock swapped round, which
    is why it is an op and not a fourth static key. It installs a
    `structs.DamageShield` and modifies nothing: it resolves *before* the damage
    exists, so the whole of its behaviour is the record it leaves behind for
    `primitives.damage_player` to consult.

    ``player`` is the usual player spec and defaults to ``"you"`` -- the printed
    sentence is nearly always about the controller, and the ones that are not
    ("prevent all damage that would be dealt to target player") name a target.

    ``duration`` is required and the only implemented word is ``this_turn``,
    cleared by the cleanup step. Required rather than defaulted for the reason
    `cant_block`'s is: a prevention read as lasting longer than it does is a
    different and much better card, and there is no reading of an omitted
    duration that is safe to guess.

    There is deliberately no ``amount``. See `structs.DamageShield`: absorb-N
    over a player is a different effect with a pool that drains, and the loader
    refuses the key rather than reading it and preventing everything anyway.
    """
    from ..structs import DAMAGE_SHIELD_DURATIONS

    duration = str(spec.get("duration", "this_turn"))
    if duration not in DAMAGE_SHIELD_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown prevent_damage duration {duration!r}")
    for pid in select_players(ctx, spec.get("player", "you")):
        shield_player(ctx.state, pid, duration, source=ctx.source_oid)


@register("damage")
def op_damage(ctx: EffectContext, spec: Mapping[str, Any]):
    """Deal damage to objects, players, or both.

    ``objects`` and ``player`` are independent: a card that reads "deal 3 damage
    to target creature and 3 damage to its controller" declares both.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    if amount <= 0:
        return

    if "objects" in spec:
        for oid in resolve_pool(ctx, spec["objects"]):
            damage_permanent(ctx.state, oid, amount, ctx.source_oid)

    if "player" in spec:
        for pid in select_players(ctx, spec["player"]):
            damage_player(ctx.state, pid, amount, ctx.source_oid)

    if "target" in spec:
        # A single target that may be either a creature or a player ("any target").
        for ref in ctx.target_refs(str(spec["target"])):
            if ref.kind == "object":
                damage_permanent(ctx.state, ref.id, amount, ctx.source_oid)
            elif ref.kind == "player":
                damage_player(ctx.state, ref.id, amount, ctx.source_oid)
