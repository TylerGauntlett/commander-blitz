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

    ``new_targets`` is "you may choose new targets for the copy" (Jin-Gitaxias,
    Progress Tyrant), and it is **opt-in** for the reason this was left out
    until a card needed it: the choice is a decision *per copy*, and a storm
    count of nine would ask nine times. Storm, replicate, conspire, casualty,
    gravestorm and epic do not set it, so none of them gained a prompt -- the
    objection was to asking unconditionally, not to the capability.

    The question is only put when there is something to decide: a spell with no
    targets, or one whose targets cannot legally be moved, is not asked.
    """
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
    for _ in range(max(0, times)):
        chosen = None
        if spec.get("new_targets"):
            chosen = yield from _choose_new_targets(ctx, original)
        put_copy_on_stack(state, ctx.controller, original, chosen)


def _choose_new_targets(ctx: EffectContext, original):
    """"You may choose new targets for the copy" (706.10, via 115.7b).

    Offered as one pick from every legal target tuple, which is exactly the set
    the caster chose from -- so "change any number of them" and "each new target
    must be legal" both fall out rather than being enforced separately, and the
    original tuple is on the list as the "change nothing" answer.

    No new `DecisionKind`: `ask_mode` already asks "pick one of these labels"
    and hands back an index, which is this question. The same argument
    `choose_type` makes.

    Returns ``None`` when there was nothing to ask -- no target specs, or only
    one legal tuple -- and the copy then keeps what the original had.
    """
    from ..targeting import describe_ref, enumerate_target_tuples
    from .context import ask_mode

    card = ctx.state.registry.get(original.def_id)
    specs = getattr(card, "targets", ()) or ()
    if not specs:
        return None
    options = enumerate_target_tuples(
        ctx.state,
        ctx.controller,
        specs,
        original.oid,
        exclude_sid=original.sid,
    )
    # One option means the only legal choice is what it already targets, so
    # there is no question -- and asking anyway would be a prompt that cannot
    # change anything, which is the cost this whole feature was held back over.
    if len(options) <= 1:
        return None
    labels = [
        ", ".join(describe_ref(ctx.state, ref) for ref in tup) or "no targets"
        for tup in options
    ]
    picked = yield from ask_mode(
        ctx, f"New targets for {card.name} (copy)?", labels, ctx.controller
    )
    if not picked:
        return None
    return options[picked[0]]


def put_copy_on_stack(state, controller: int, original, targets=None):
    """Rule 706.10 -- one copy of a spell, on top of the stack.

    Split out of :func:`op_copy_spell` for **epic**, which makes a copy each
    upkeep from the turn structure rather than from an effect. The two must not
    drift: a copy is a token object (which is what makes it vanish correctly),
    it keeps the original's targets, and it announces them so ward and heroic
    see it -- and none of that is obvious enough to write twice.
    """
    from ..stack import StackItem, announce_targets
    from ..state import new_object

    card = state.registry.get(original.def_id)
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
        # `targets` overrides only when "you may choose new targets" was taken
        # and the player actually chose. `None` is not "no targets": it is "the
        # copy keeps the original's", which is 706.10's default and what storm,
        # replicate, conspire and epic all rely on.
        targets=original.targets if targets is None else tuple(targets),
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
    return copy


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
                # It has stopped being a spell, so it stops showing the face it
                # was cast as -- and a countered Adventure is a card in the
                # graveyard, since 715.3c exiles it only *as it resolves*.
                obj.showing_second_face = False
                move_object(state, item.oid, Zone.GRAVEYARD, to_player=obj.owner, cause="countered")
