"""Effect ops for mana and land drops."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..events import EventType
from ..mana import parse_mana_production
from . import register
from .context import EffectContext
from .selectors import resolve_pool, select_players
from .values import evaluate_value


@register("add_mana")
def op_add_mana(ctx: EffectContext, spec: Mapping[str, Any]):
    produced = parse_mana_production(str(spec.get("mana", "")))
    for pid in select_players(ctx, spec.get("player", "you")):
        ctx.state.players[pid].mana_pool.add_tuple(produced, source=ctx.source_oid)
        ctx.state.emit(
            EventType.MANA_ADDED, player=pid, source=ctx.source_oid, mana=spec.get("mana", "")
        )


@register("add_mana_per")
def op_add_mana_per(ctx: EffectContext, spec: Mapping[str, Any]):
    """Add one unit of mana for each object matching a selector.

    e.g. "Add {G} for each Forest you control".
    """
    unit = parse_mana_production(str(spec.get("mana", "")))
    count = len(resolve_pool(ctx, spec.get("per")))
    if count <= 0:
        return
    scaled = tuple(v * count for v in unit)
    for pid in select_players(ctx, spec.get("player", "you")):
        ctx.state.players[pid].mana_pool.add_tuple(scaled, source=ctx.source_oid)
        ctx.state.emit(
            EventType.MANA_ADDED,
            player=pid,
            source=ctx.source_oid,
            mana=spec.get("mana", ""),
            times=count,
        )


@register("extra_land_drop")
def op_extra_land_drop(ctx: EffectContext, spec: Mapping[str, Any]):
    """Grant additional land drops for the rest of this turn."""
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        ctx.state.players[pid].extra_land_drops += amount
