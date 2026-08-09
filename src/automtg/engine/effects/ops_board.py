"""Effect ops that act on permanents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..primitives import (
    add_counters,
    attach,
    create_token,
    grant_keyword,
    pump,
    remove_counters,
    tap_permanent,
    untap_permanent,
)
from ..zones import destroy, exile, move_object, sacrifice
from . import register
from .context import EffectContext
from .selectors import choose_objects
from .values import evaluate_value


@register("destroy")
def op_destroy(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Destroy", "destroy")
    for oid in oids:
        destroy(ctx.state, oid)


@register("exile")
def op_exile(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Exile", "destroy")
    for oid in oids:
        exile(ctx.state, oid)


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
        move_object(ctx.state, oid, Zone.BATTLEFIELD, tapped=tapped, cause="put_onto_battlefield")


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
