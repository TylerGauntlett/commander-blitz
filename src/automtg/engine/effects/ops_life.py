"""Effect ops for life totals and damage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..events import EventType
from ..primitives import damage_permanent, damage_player, gain_life, lose_life
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
