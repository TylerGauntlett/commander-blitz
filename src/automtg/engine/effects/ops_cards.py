"""Effect ops that move cards around: draw, discard, mill, search, recursion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..events import EventType
from ..primitives import discard_cards, draw_cards, mill_cards, shuffle_library
from ..zones import move_object
from . import register
from .context import EffectContext, ask_objects, ask_yes_no
from .selectors import choose_objects, resolve_pool, select_players
from .values import evaluate_value

DESTINATIONS = {
    "hand": Zone.HAND,
    "battlefield": Zone.BATTLEFIELD,
    "graveyard": Zone.GRAVEYARD,
    "exile": Zone.EXILE,
    "library_top": Zone.LIBRARY,
    "library_bottom": Zone.LIBRARY,
}


@register("draw")
def op_draw(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        draw_cards(ctx.state, pid, amount)


@register("discard")
def op_discard(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    random = bool(spec.get("random"))
    for pid in select_players(ctx, spec.get("player", "you")):
        hand = list(ctx.state.players[pid].hand)
        if not hand:
            continue
        take = min(amount, len(hand))
        if random:
            picked = ctx.state.rng.shuffled(hand)[:take]
        else:
            picked = yield from ask_objects(ctx, "Discard", hand, take, take, pid, "discard")
        discard_cards(ctx.state, pid, picked)


@register("mill")
def op_mill(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        mill_cards(ctx.state, pid, amount)


@register("shuffle")
def op_shuffle(ctx: EffectContext, spec: Mapping[str, Any]):
    for pid in select_players(ctx, spec.get("player", "you")):
        shuffle_library(ctx.state, pid)


@register("search_library")
def op_search_library(ctx: EffectContext, spec: Mapping[str, Any]):
    """Search a library for cards matching a selector and move them somewhere.

    Always shuffles afterwards unless ``"shuffle": false`` is given.
    """
    count = evaluate_value(ctx, spec.get("count", 1))
    destination = DESTINATIONS[spec.get("destination", "hand")]
    tapped = bool(spec.get("tapped"))
    for pid in select_players(ctx, spec.get("player", "you")):
        pool = [
            oid
            for oid in ctx.state.players[pid].library
            if _matches_library(ctx, oid, spec.get("selector") or {})
        ]
        if not pool:
            if spec.get("shuffle", True):
                shuffle_library(ctx.state, pid)
            continue
        take = min(count, len(pool))
        picked = yield from ask_objects(ctx, "Search your library", pool, 0, take, pid, "search")
        for oid in picked:
            if destination is Zone.BATTLEFIELD:
                # to_player only picks the destination zone list; the battlefield
                # is global, so controller has to be set explicitly or the
                # `controller: "you"` clause on landfall reads the owner.
                obj = ctx.state.objects.get(oid)
                if obj is not None:
                    obj.controller = pid
            move_object(
                ctx.state,
                oid,
                destination,
                to_player=pid,
                to_top=spec.get("destination") == "library_top",
                tapped=tapped,
                cause="search",
            )
        if spec.get("shuffle", True):
            shuffle_library(ctx.state, pid)


def _matches_library(ctx: EffectContext, oid: int, selector: Mapping[str, Any]) -> bool:
    from .selectors import matches

    probe = dict(selector)
    probe["zone"] = "library"
    probe.pop("controller", None)
    probe.pop("count", None)
    probe.pop("chooser", None)
    return matches(ctx, oid, probe)


@register("return_to_hand")
def op_return_to_hand(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Return to hand")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        move_object(ctx.state, oid, Zone.HAND, to_player=obj.owner, cause="returned")


@register("return_from_graveyard")
def op_return_from_graveyard(ctx: EffectContext, spec: Mapping[str, Any]):
    selector = dict(spec.get("objects") or {})
    selector.setdefault("zone", "graveyard")
    destination = DESTINATIONS[spec.get("destination", "hand")]
    oids = yield from choose_objects(ctx, selector, "Return from graveyard")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        if destination is Zone.BATTLEFIELD:
            # Same reason as op_search_library: the battlefield is one global
            # list, so nothing else sets controller. Mirrors put_onto_battlefield.
            obj.controller = ctx.controller if spec.get("controller") == "you" else obj.owner
        move_object(
            ctx.state,
            oid,
            destination,
            to_player=obj.owner,
            tapped=bool(spec.get("tapped")),
            cause="recursion",
        )


@register("reveal")
def op_reveal(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = resolve_pool(ctx, spec.get("objects"))
    if oids:
        ctx.state.emit(
            "reveal",
            player=ctx.controller,
            source=ctx.source_oid,
            cards=[ctx.state.objects[o].def_id for o in oids if o in ctx.state.objects],
        )


@register("scry")
def op_scry(ctx: EffectContext, spec: Mapping[str, Any]):
    """Look at the top N cards; put any number on the bottom in the chosen order."""
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        library = ctx.state.players[pid].library
        top = list(library[:amount])
        if not top:
            continue
        to_bottom = yield from ask_objects(ctx, "Put on the bottom", top, 0, len(top), pid, "scry_bottom")
        for oid in to_bottom:
            library.remove(oid)
            library.append(oid)
        ctx.state.emit("scry", player=pid, looked=len(top), bottomed=len(to_bottom))


@register("surveil")
def op_surveil(ctx: EffectContext, spec: Mapping[str, Any]):
    """Look at the top N cards; put any number into the graveyard."""
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        top = list(ctx.state.players[pid].library[:amount])
        if not top:
            continue
        to_bin = yield from ask_objects(ctx, "Put into your graveyard", top, 0, len(top), pid, "surveil")
        for oid in to_bin:
            move_object(ctx.state, oid, Zone.GRAVEYARD, to_player=pid, cause="surveil")
        ctx.state.emit("surveil", player=pid, looked=len(top), binned=len(to_bin))


@register("two_piles")
def op_two_piles(ctx: EffectContext, spec: Mapping[str, Any]):
    """"An opponent separates those cards into two piles. Put one pile into your
    hand and the other into your graveyard."

    The only effect in the pool whose first decision belongs to somebody else,
    and that is the whole card: the splitter wants both piles to be bad and the
    chooser gets the better one. An implementation that let the caster do the
    splitting would be a strictly better card.

    Two decisions, deliberately: the opponent picks which cards form the first
    pile, then the controller says whether to take it. Modelled as a subset plus
    a yes/no rather than as "choose a pile", because the piles do not exist as
    objects until the split is made.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    pid = ctx.controller
    library = ctx.state.players[pid].library
    revealed = list(library[:amount])
    if not revealed:
        return

    ctx.state.emit(
        "reveal",
        player=pid,
        source=ctx.source_oid,
        cards=[ctx.state.objects[o].def_id for o in revealed],
    )

    opponents = ctx.opponents()
    splitter = opponents[0] if opponents else pid
    first = yield from ask_objects(
        ctx, "Separate into two piles", revealed, 0, len(revealed), splitter, "split_piles"
    )
    first_set = set(first)
    second = [oid for oid in revealed if oid not in first_set]

    take_first = yield from ask_yes_no(
        ctx,
        f"Take the pile of {len(first)}? (the other has {len(second)})",
        pid,
    )
    taken, discarded = (first, second) if take_first else (second, first)

    to_taken = DESTINATIONS[str(spec.get("to", "hand"))]
    to_rest = DESTINATIONS[str(spec.get("other", "graveyard"))]
    for oid in taken:
        move_object(ctx.state, oid, to_taken, to_player=pid, cause="two_piles")
    for oid in discarded:
        move_object(ctx.state, oid, to_rest, to_player=pid, cause="two_piles")


@register("put_on_top")
def op_put_on_top(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put on top of library")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        move_object(ctx.state, oid, Zone.LIBRARY, to_player=obj.owner, to_top=True, cause="tuck")
        ctx.state.emit(EventType.ZONE_CHANGE, source=oid, to="library_top")
