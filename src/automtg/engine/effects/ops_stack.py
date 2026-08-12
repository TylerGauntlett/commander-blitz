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

    ``sid`` names the victim by value rather than by target, which is what ward
    needs: "counter **it** unless that player pays" is not a targeted ability,
    and the spell it means is the one that just targeted this permanent. The
    `becomes_target` trigger carries that spell's `sid` in its bindings, so
    ``{"sid": {"binding": "sid"}}`` says it without inventing a target the
    printed card does not have -- which would also let the ward creature's
    controller point it somewhere else.
    """
    state = ctx.state
    target_id = str(spec.get("target", "t1"))
    if "sid" in spec:
        from .values import evaluate_value

        sids = [evaluate_value(ctx, spec["sid"])]
    else:
        sids = list(ctx.target_sids(target_id))
    for sid in sids:
        item = state.stack_item(sid)
        if item is None:
            continue
        # "This spell can't be countered." Printed on the card rather than
        # granted, so it is read off the definition and needs no static: the
        # spell is on the stack, where statics do not reach it anyway.
        if item.is_spell and state.registry.get(item.def_id).uncounterable:
            state.emit(
                EventType.SPELL_COUNTERED,
                player=item.controller,
                source=ctx.source_oid,
                sid=sid,
                card=item.def_id,
                failed="cannot be countered",
            )
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
