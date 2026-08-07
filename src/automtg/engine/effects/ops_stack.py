"""Effect ops that act on the stack."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..events import EventType
from ..zones import move_object
from . import register
from .context import EffectContext


@register("counter")
def op_counter(ctx: EffectContext, spec: Mapping[str, Any]):
    """Counter target spell.

    A countered spell is removed from the stack and put into its owner's
    graveyard; abilities on the stack simply cease to exist.
    """
    state = ctx.state
    target_id = str(spec.get("target", "t1"))
    for sid in ctx.target_sids(target_id):
        item = state.stack_item(sid)
        if item is None:
            continue
        state.stack = [it for it in state.stack if it.sid != sid]
        state.emit(
            EventType.SPELL_COUNTERED,
            player=item.controller,
            source=ctx.source_oid,
            sid=sid,
            card=item.def_id,
        )
        if item.is_spell and item.oid is not None:
            obj = state.objects.get(item.oid)
            if obj is not None:
                obj.stack_id = None
                move_object(state, item.oid, Zone.GRAVEYARD, to_player=obj.owner, cause="countered")
