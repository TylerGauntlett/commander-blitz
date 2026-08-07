"""Effect ops for life totals and damage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
