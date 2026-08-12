"""Effect ops that act on permanents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..errors import DslError
from ..objects import PLUS_ONE
from ..primitives import (
    add_counters,
    add_subtypes,
    animate,
    attach,
    change_control,
    create_token,
    grant_ability,
    grant_keyword,
    lock_abilities,
    pump,
    remove_counters,
    tap_permanent,
    untap_permanent,
)
from ..zones import destroy, exile, move_object, sacrifice
from . import register
from .context import EffectContext
from .selectors import choose_objects, resolve_pool
from .values import evaluate_value


@register("destroy")
def op_destroy(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Destroy", "destroy")
    for oid in oids:
        destroy(ctx.state, oid)


@register("exile")
def op_exile(ctx: EffectContext, spec: Mapping[str, Any]):
    """Exile objects, optionally remembering which permanent did it.

    ``until_leaves`` is the O-Ring family -- "exile it until this permanent
    leaves the battlefield". It records the link and nothing else; the *return*
    is an ordinary `leaves_battlefield` trigger on the same card, reading the
    link back through a `{"zone": "exile", "exiled_with": "self"}` selector.

    Two halves rather than one op, because the card really is two abilities and
    a player can respond between them -- and because what comes back, and under
    whose control, differs between O-Ring and Fiend Hunter.
    """
    link = bool(spec.get("until_leaves"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Exile", "destroy")
    for oid in oids:
        exile(ctx.state, oid)
        if link and ctx.source_oid is not None:
            # After the move: `move_object` runs `reset_permanent_state` on the
            # way, which would wipe this if it were set first.
            obj = ctx.state.objects.get(oid)
            if obj is not None:
                obj.exiled_by = ctx.source_oid


@register("sacrifice")
def op_sacrifice(ctx: EffectContext, spec: Mapping[str, Any]):
    selector = dict(spec.get("objects") or {})
    selector.setdefault("controller", "you")
    oids = yield from choose_objects(ctx, selector, "Sacrifice", "sacrifice")
    for oid in oids:
        sacrifice(ctx.state, oid)


@register("put_onto_battlefield")
def op_put_onto_battlefield(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put onto the battlefield")
    tapped = bool(spec.get("tapped"))
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        controller = ctx.controller if spec.get("controller") == "you" else obj.owner
        obj.controller = controller
        # `cause` travels into the enters-the-battlefield event, so an ability
        # that puts permanents down can name itself here and then refuse to
        # trigger on its own output -- see `TriggerSpec.not_cause`.
        move_object(
            ctx.state,
            oid,
            Zone.BATTLEFIELD,
            tapped=tapped,
            cause=str(spec.get("cause") or "put_onto_battlefield"),
        )


@register("create_token")
def op_create_token(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    token = str(spec["token"])
    attacking = _attack_target(ctx) if spec.get("attacking") else None
    for pid in _players(ctx, spec.get("controller", "you")):
        create_token(
            ctx.state,
            token,
            pid,
            amount,
            tapped=bool(spec.get("tapped")),
            attacking=attacking,
        )


@register("copy_permanent")
def op_copy_permanent(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Create a token that's a copy of target creature."

    The object model already *is* a copy model: an object's identity is its
    ``def_id`` pointing at a `CardDef`, and `is_token` is a separate flag.  So a
    token copy is a token whose ``def_id`` is the copied permanent's -- which is
    also exactly right, because a copy copies the printed card and not the
    counters, damage or Auras that have accumulated on it.

    Unlike `create_token` this names no token id, so there is nothing for
    `validate_token_references` to check and nothing to pre-declare: the thing
    being copied is only known while the spell is resolving.

    ``except_`` is embalm's "…except it's a white Zombie Angel with no mana
    cost". It is stored on the token rather than on a card, because a copy has
    no card of its own -- its identity is the original's ``def_id``.

    The source need not be on the battlefield: embalm copies a card in the
    *graveyard*, and `self_only` reaches it there because an oid survives every
    zone change.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    oids = resolve_pool(ctx, spec.get("objects"))
    if not oids:
        return
    controllers = _players(ctx, spec.get("controller", "you"))
    overrides = spec.get("except_") or spec.get("except")
    for oid in oids:
        source = ctx.state.objects.get(oid)
        if source is None:
            continue
        for pid in controllers:
            create_token(
                ctx.state,
                source.def_id,
                pid,
                amount,
                tapped=bool(spec.get("tapped")),
                attacking=_attack_target(ctx) if spec.get("attacking") else None,
                overrides=dict(overrides) if overrides else None,
            )


def _attack_target(ctx: EffectContext) -> int | None:
    """Whom a token created attacking should be attacking.

    The same player the source is already attacking -- which is what "create a
    tapped and attacking token" means on a card whose trigger is "whenever this
    creature attacks".  Outside combat, or from a source that is not itself
    attacking, there is nobody to join, and the token simply arrives tapped.
    """
    combat = ctx.state.combat
    if combat is None or ctx.source_oid is None:
        return None
    return combat.attackers.get(ctx.source_oid)


@register("add_counters")
def op_add_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    kind = str(spec.get("counter", "+1/+1"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put counters on")
    for oid in oids:
        add_counters(ctx.state, oid, kind, amount, source=ctx.source_oid)


@register("remove_counters")
def op_remove_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    kind = str(spec.get("counter", "+1/+1"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Remove counters from")
    for oid in oids:
        remove_counters(ctx.state, oid, kind, amount)


@register("tap")
def op_tap(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Tap")
    for oid in oids:
        tap_permanent(ctx.state, oid)


@register("untap")
def op_untap(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Untap")
    for oid in oids:
        untap_permanent(ctx.state, oid)


@register("attach")
def op_attach(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Attach to")
    aura = ctx.source_oid
    if aura is not None:
        for oid in oids[:1]:
            attach(ctx.state, aura, oid)


@register("gain_control")
def op_gain_control(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Gain control of target creature." Captivating Vampire.

    ``player`` says who gains it and defaults to the ability's controller, which
    is what every "*you* gain control" line means; the spec exists because "target
    opponent gains control of" is the same effect pointed elsewhere.

    Permanent only -- see :func:`automtg.engine.primitives.change_control` for
    why there is no until-end-of-turn form and why the loader refuses to let a
    card ask for one silently.
    """
    players = _players(ctx, spec.get("player", "you"))
    if not players:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Gain control of")
    for oid in oids:
        change_control(ctx.state, oid, players[0], source=ctx.source_oid)


@register("add_subtype")
def op_add_subtype(ctx: EffectContext, spec: Mapping[str, Any]):
    """"It becomes a Vampire in addition to its other types." Captivating Vampire.

    The same two words as the `add_subtype` **static**, and a different
    mechanism: the static applies continuously to whatever currently matches its
    filter and stops when its source leaves, while this is written onto the one
    permanent it was pointed at and stays until that permanent changes zones.
    The printed lines differ the same way -- "creatures you control are
    Vampires" against "it becomes a Vampire".

    Types are always *added*.  Replacing a type line is `animate` or the
    `set_types` static.
    """
    subtypes = [str(t) for t in spec.get("subtypes", ())]
    if not subtypes:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Becomes")
    for oid in oids:
        add_subtypes(ctx.state, oid, subtypes)


@register("pump")
def op_pump(ctx: EffectContext, spec: Mapping[str, Any]):
    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Pump")
    for oid in oids:
        pump(ctx.state, oid, power, toughness, source=ctx.source_oid)


@register("grant_keyword")
def op_grant_keyword(ctx: EffectContext, spec: Mapping[str, Any]):
    keywords = spec.get("keywords") or ([spec["keyword"]] if "keyword" in spec else [])
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant")
    for oid in oids:
        for keyword in keywords:
            grant_keyword(ctx.state, oid, str(keyword), source=ctx.source_oid)


@register("animate")
def op_animate(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Becomes a 4/4 white and blue Elemental creature with vigilance until end
    of turn. It's still a land."

    One op for the whole sentence, keywords included, rather than an `animate`
    beside a `grant_keyword`: the authoring verifier's residual gate asks each
    *ability* which printed sentence it implements, and a creature-land's
    animation is one sentence.  Splitting it would work and would read as two
    claims on the same line.

    Distinct from `set_pt`, which is a compensating pump over whatever the
    permanent's power happens to be right now.  An animation names the base
    value, so counters and anthems add to it instead of being cancelled by it.
    """
    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    types = [str(t) for t in spec.get("types", ("Creature",))]
    subtypes = [str(t) for t in spec.get("subtypes", ())]
    colors = [str(c) for c in spec.get("colors", ())]
    keywords = [str(k) for k in spec.get("keywords", ())]
    oids = yield from choose_objects(ctx, spec.get("objects"), "Animate")
    for oid in oids:
        animate(
            ctx.state,
            oid,
            power,
            toughness,
            types=types,
            subtypes=subtypes,
            colors=colors,
            source=ctx.source_oid,
        )
        for keyword in keywords:
            grant_keyword(ctx.state, oid, keyword, source=ctx.source_oid)


@register("monstrosity")
def op_monstrosity(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Monstrosity N": counters and a one-way flag, in that order.

    The flag is the mechanic. Without it the ability is a repeatable pump, and
    the "when this becomes monstrous" trigger that usually accompanies it would
    fire every time rather than once.
    """
    from ..events import EventType
    from ..triggers import fire

    amount = evaluate_value(ctx, spec.get("amount", 1))
    oid = ctx.source_oid
    obj = ctx.state.objects.get(oid) if oid is not None else None
    if obj is None or not obj.on_battlefield or obj.monstrous:
        return
    add_counters(ctx.state, oid, PLUS_ONE, amount, source=oid)
    obj.monstrous = True
    ctx.state.bump_chars()
    fire(
        ctx.state,
        EventType.BECAME_MONSTROUS,
        player=obj.controller,
        source=oid,
        oid=oid,
        card=obj.def_id,
        amount=amount,
    )


@register("freeze")
def op_freeze(ctx: EffectContext, spec: Mapping[str, Any]):
    """"…don't untap during their controllers' untap steps for as long as you
    control this creature."

    Recorded on the frozen permanent as the *oid of the source*, rather than as
    a flag with a lifetime of its own: the hold has to end when the source does,
    and pointing at it is the only way the untap step can tell.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Freeze")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.frozen_by = ctx.source_oid


@register("grant_ability")
def op_grant_ability(ctx: EffectContext, spec: Mapping[str, Any]):
    """Give a permanent one of this card's ``grantable_abilities`` until EOT.

    "…and 'Whenever this creature deals combat damage to a player, draw a
    card'." The quoted ability is written out on the granting card and referred
    to here by index, so there is one definition of it rather than a copy.
    """
    index = int(spec.get("ability", 0))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant an ability to")
    if ctx.source_oid is None:
        return
    for oid in oids:
        grant_ability(ctx.state, oid, index, ctx.source_oid)


@register("skip_untap")
def op_skip_untap(ctx: EffectContext, spec: Mapping[str, Any]):
    """"It doesn't untap during its controller's next untap step."

    A *one-shot*, cleared by the untap step it skips -- which is what separates
    it from `freeze`, where the hold lasts as long as its source is on the
    battlefield. Using either for the other would be wrong in both directions,
    so they are two ops over two fields rather than one with a flag.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Keep tapped")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.skip_next_untap = True


@register("lock_abilities")
def op_lock_abilities(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Its activated abilities can't be activated this turn."

    Separate from `tap`, which usually accompanies it, because the two are
    different halves of the sentence and a card may want only one.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Lock")
    for oid in oids:
        lock_abilities(ctx.state, oid, source=ctx.source_oid)


@register("set_pt")
def op_set_pt(ctx: EffectContext, spec: Mapping[str, Any]):
    """Set base power/toughness until end of turn.

    Implemented as a pump that cancels the current values, which is equivalent
    under this engine's fixed-order characteristic pipeline for the cards in the
    curated decks (none of them combine ``set_pt`` with counters).
    """
    from ..characteristics import chars

    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Set power/toughness")
    for oid in oids:
        current = chars(ctx.state, oid)
        pump(
            ctx.state,
            oid,
            power - current.power,
            toughness - current.toughness,
            source=ctx.source_oid,
        )


def _players(ctx: EffectContext, spec: Any) -> list[int]:
    from .selectors import select_players

    return select_players(ctx, spec)


@register("must_attack")
def op_must_attack(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Target creature attacks during its controller's next combat phase if able."

    A *requirement*, which is a shape the engine had none of: every other way a
    card touches combat removes an option (tap, freeze, skip_untap, defender)
    and this one removes the option not to. It is enforced in `legality` by
    withholding "Done attacking" while an able creature that must attack is not
    attacking.

    Two durations, and the difference is which combat is meant:

    ``this_turn``     Bident of Thassa -- the combat in the turn it was used,
                      and nothing later.
    ``next_combat``   Trench Behemoth -- the *controller's* next combat phase,
                      which for an opponent's creature is a later turn. It
                      cannot be "this turn": the trigger fires on your landfall,
                      and the affected player's combat has not happened yet.

    Not a `TempEffect`, for that reason -- those are wiped by the cleanup step,
    and this has to outlive it.
    """
    duration = str(spec.get("duration", "next_combat"))
    if duration not in ("this_turn", "next_combat"):  # pragma: no cover - loader guards
        raise DslError(f"unknown must_attack duration {duration!r}")
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.must_attack = duration
        obj.must_attack_turn = ctx.state.turn
    yield from ()
