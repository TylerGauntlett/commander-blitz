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

    ``controller`` is a **player spec** naming whose copy it is, and it is
    **demonstrate**: "choose an opponent to also copy it." Every copy this op
    could make used to be the resolving player's, because the controller was
    the one argument `put_copy_on_stack` was never given -- so the half of
    demonstrate that balances it was unsayable, and a card written with
    ``"controller"`` on it loaded clean and handed the copy to the wrong seat.
    It reads plurally, exactly as `copy_permanent`'s does: one copy per named
    player, per ``amount``. `choose_player` is what narrows it to the one
    opponent demonstrate means, via ``{"binding": …}``.

    Each copy's *own* controller answers ``new_targets`` for it -- 706.10 says
    "players may choose new targets for **their** copies", and asking the
    resolving player about a copy that is not theirs would be a different card
    in both directions: it would let you point an opponent's copy and would
    stop them pointing it themselves.
    """
    from .selectors import select_players
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
    if "controller" in spec:
        # A named seat that has already lost the game is not handed a copy, and
        # an unfilled binding names nobody -- which is how "choose an opponent"
        # makes no second copy at a table where there is no opponent left to
        # choose, rather than falling back to the resolving player's own.
        controllers = [
            pid for pid in select_players(ctx, spec["controller"]) if state.is_alive(pid)
        ]
    else:
        controllers = [ctx.controller]
    for _ in range(max(0, times)):
        for pid in controllers:
            chosen = None
            if spec.get("new_targets"):
                chosen = yield from _choose_new_targets(ctx, original, pid)
            put_copy_on_stack(state, pid, original, chosen)


def _choose_new_targets(ctx: EffectContext, original, chooser: int | None = None):
    """ "You may choose new targets for the copy" (706.10, via 115.7b).

    Offered as one pick from every legal target tuple, which is exactly the set
    the caster chose from -- so "change any number of them" and "each new target
    must be legal" both fall out rather than being enforced separately, and the
    original tuple is on the list as the "change nothing" answer.

    No new `DecisionKind`: `ask_mode` already asks "pick one of these labels"
    and hands back an index, which is this question. The same argument
    `choose_type` makes.

    Returns ``None`` when there was nothing to ask -- no target specs, or only
    one legal tuple -- and the copy then keeps what the original had.

    ``chooser`` is the **copy's** controller, not the resolving player's: a
    demonstrate copy belongs to the chosen opponent, and 706.10's "their
    copies" is that word. It decides the legal set as well as the seat asked,
    because "target creature you control" means a different pool for each of
    them -- so an opponent's copy is offered the targets an opponent could have
    chosen, which is what stops a redirected copy being pointed somewhere its
    own controller never could.
    """
    from ..targeting import describe_ref, enumerate_target_tuples
    from .context import ask_mode

    if chooser is None:
        chooser = ctx.controller
    card = ctx.state.registry.get(original.def_id)
    specs = getattr(card, "targets", ()) or ()
    if not specs:
        return None
    options = enumerate_target_tuples(
        ctx.state,
        chooser,
        specs,
        original.oid,
        exclude_sid=original.sid,
    )
    current = tuple(original.targets)
    if current not in options:
        # "You **may** choose new targets", and declining stays on the table
        # even when what the copy holds is no longer legal for its controller
        # -- a copy nobody retargets is simply countered on resolution
        # (608.2b), and for a spell the copy's controller does not *want*, that
        # is the answer they would give.
        #
        # Unreachable until a copy could belong to somebody else. It is the
        # ordinary case for demonstrate: "target creature you control" names
        # the copy's controller's creatures, so the tuple the original chose is
        # usually not among the ones offered to them, and without this the
        # option list would not contain "leave it".
        options = [*options, current]
    # One option means the only legal choice is what it already targets, so
    # there is no question -- and asking anyway would be a prompt that cannot
    # change anything, which is the cost this whole feature was held back over.
    if len(options) <= 1:
        return None
    labels = [
        ", ".join(describe_ref(ctx.state, ref) for ref in tup) or "no targets" for tup in options
    ]
    picked = yield from ask_mode(ctx, f"New targets for {card.name} (copy)?", labels, chooser)
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
    # `fire` rather than `state.emit`: magecraft ("whenever you cast **or copy**
    # an instant or sorcery spell") listens for this, and `emit` only records
    # the event -- it never scans for triggered abilities, so the event was
    # written into the log and heard by nobody. Every other trigger-bearing
    # event in the engine goes through `fire`; this one was emitted before
    # anything could listen and was never moved over.
    from ..triggers import fire

    fire(
        state,
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


@register("reflexive_trigger")
def op_reflexive_trigger(ctx: EffectContext, spec: Mapping[str, Any]):
    """Fire a reflexive triggered ability (603.11) -- "**When you do**, …".

    Espers to Magicite: "Exile each opponent's graveyard. When you do, choose up
    to one target creature card exiled this way. Create a token that's a copy of
    that card…"

    The rest of that sentence is a real ability on the card
    (``kind: "reflexive"``) and this queues it, which is the whole of the op.
    Everything that matters about 603.11 then comes from the pipeline the card's
    other triggers already use: it goes on the stack when a player would next
    receive priority -- so **after** the spell that fired it has finished
    resolving -- it chooses its targets as it is put there (603.3d), and the
    other players get a window to respond before it resolves.

    **Not more effects inline.** Written that way the choice would be made
    mid-resolution and would not be a *target* at all: nothing would be
    announced, nothing could respond, and 608.2b would never re-check it. The
    difference is visible on this very card, whose reflexive half targets a card
    an opponent may still be able to reach.

    **Not `delayed_trigger`.** That watches an `EventType`, and "when you do"
    has none: what it means is "when the instruction immediately above this one
    is carried out", which is a fact about *this* resolution and not about
    anything the board could be watched for. It is also fired unconditionally
    here, because the effect above it did happen -- an exiled-nothing case is
    the reflexive ability's own business, not this op's.

    The bindings are copied at this instant, so "…exiled **this way**" still
    names the cards the earlier op recorded once the ability is on the stack.
    """
    from ..structs import TriggerInstance

    state = ctx.state
    source_oid = ctx.source_oid
    if source_oid is None:
        return
    obj = state.objects.get(source_oid)
    if obj is None:
        return
    card = state.card_of(obj)
    wanted = str(spec.get("ability", ""))
    ability = next((a for a in card.abilities if a.reflex_id and a.reflex_id == wanted), None)
    if ability is None:  # pragma: no cover -- the loader refuses this
        return
    state.pending_triggers.append(
        TriggerInstance(
            source_oid=source_oid,
            ability_index=ability.index,
            controller=ctx.controller,
            bindings=dict(ctx.bindings),
            description=f"{card.name}: {ability.text or wanted}",
            # The same snapshot every other trigger keeps, and it earns its keep
            # here: the source is usually a *spell*, which is in a graveyard by
            # the time this reaches the stack.
            def_id=obj.def_id,
        )
    )
    state.emit(
        EventType.ABILITY_TRIGGERED,
        player=ctx.controller,
        source=source_oid,
        card=card.id,
        ability=ability.index,
        trigger="reflexive",
    )
