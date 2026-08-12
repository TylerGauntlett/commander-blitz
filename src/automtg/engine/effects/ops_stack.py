"""Effect ops that act on the stack."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..events import EventType
from ..zones import move_object
from . import register
from .context import EffectContext


@register("copy_spell")
def op_copy_spell(ctx: EffectContext, spec: Mapping[str, Any]):
    """Copy a spell on the stack (rule 706.10).

    Storm, replicate, conspire, casualty and gravestorm are one capability, and
    this is it. Every one of them says "copy this spell" and differs only in how
    many times and what it costs.

    **A copy is not a card.** Rule 706.10 puts a copy on the stack without it
    being cast and without it existing anywhere else, so the copy is backed by a
    *token* object. That is not a trick: it is what makes the copy disappear
    correctly. An instant's copy resolves, goes to a graveyard, and the
    token state-based action removes it -- so the original card is still the
    only one that ends up in the graveyard, which is what the printed rules say
    and what a naive second `GameObject` would get wrong.

    ``sid`` names the spell, as a value expression. Storm and replicate copy
    *themselves*, so it defaults to the spell this ability belongs to -- the
    `sid` a `spell_cast` trigger already carries in its bindings.

    ``amount`` is how many copies. Storm's is a count of the turn's spells,
    which is why it is a value expression and not an integer.

    The copies go on top of the stack, so they resolve **before** the original:
    706.10 again, and it is the whole reason a storm copy can be countered
    separately from the spell that made it.

    Not implemented, and deliberately: "you may choose new targets for the
    copy". Every copy here keeps the original's targets. Adding the choice
    means a decision per copy, and a storm count of nine would ask nine times
    -- worth doing when a card in the pool needs it, and misleading to
    half-implement before then.
    """
    from ..stack import StackItem, announce_targets
    from ..state import new_object
    from .values import evaluate_value

    state = ctx.state
    if "sid" in spec:
        sid = evaluate_value(ctx, spec["sid"])
    else:
        sid = ctx.bindings.get("sid")
    original = state.stack_item(int(sid)) if isinstance(sid, int) else None
    if original is None or not original.is_spell:
        return
    times = evaluate_value(ctx, spec.get("amount", 1)) if "amount" in spec else 1
    controller = ctx.controller
    card = state.registry.get(original.def_id)
    for _ in range(max(0, times)):
        obj = new_object(
            state,
            original.def_id,
            owner=controller,
            zone=Zone.STACK,
            controller=controller,
            is_token=True,
        )
        copy = StackItem(
            sid=state.alloc_sid(),
            kind="spell",
            controller=controller,
            def_id=original.def_id,
            oid=obj.oid,
            targets=original.targets,
            x=original.x,
            modes=original.modes,
            kicked=original.kicked,
            bindings=dict(original.bindings),
            description=f"{card.name} (copy)",
        )
        obj.stack_id = copy.sid
        state.stack.append(copy)
        state.emit(
            EventType.SPELL_COPIED,
            player=controller,
            source=original.oid,
            sid=copy.sid,
            of=original.sid,
            card=original.def_id,
        )
        # A copy targets what the original targeted, and "becomes the target
        # of a spell" does not ask whether that spell was cast -- so ward and
        # heroic see the copy too.
        announce_targets(state, copy)


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
