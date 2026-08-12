"""Effect ops that move cards around: draw, discard, mill, search, recursion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..events import EventType
from ..primitives import add_counters, discard_cards, draw_cards, mill_cards, shuffle_library
from ..zones import move_object
from . import register
from .context import EffectContext, ask_objects, ask_yes_no
from .selectors import (
    ZONE_NAMES,
    choose_objects,
    pick_from_pool,
    resolve_pool,
    select_players,
)
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


#: Zones a card may be searched out of.  The battlefield and the stack are not
#: hidden, so "searching" them is just a selector; these are the four a card
#: means when it says "search".
SEARCHABLE = ("library", "graveyard", "hand", "exile")


@register("search_library")
def op_search_library(ctx: EffectContext, spec: Mapping[str, Any]):
    """Search a library for cards matching a selector and move them somewhere.

    Always shuffles afterwards unless ``"shuffle": false`` is given.
    """
    yield from _search(ctx, spec, ("library",))


@register("search_zones")
def op_search_zones(ctx: EffectContext, spec: Mapping[str, Any]):
    """Search more than one of your own zones as a **single** pool.

    "Search your library and/or graveyard for a creature card" (Finale of
    Devastation). Running a `search_library` and a `return_from_graveyard` in
    sequence is a different card: each carries its own count, so Finale would
    fetch up to two creatures instead of one. The count here is over the union,
    which is what "and/or" means -- you look through both and take one.

    The shuffle is not conditional. Finale prints "If you search your library
    this way, shuffle", and the `if` exists because a player at a table may
    announce they are searching only the graveyard. This implementation always
    offers both zones, so it has always searched the library and always shuffles.
    The only reachable difference is a player who wanted to decline the search to
    preserve a stacked top of library, which is recorded in rules-coverage.md.
    """
    zones = tuple(spec.get("zones") or ("library",))
    yield from _search(ctx, spec, zones)


def _search(ctx: EffectContext, spec: Mapping[str, Any], zones: tuple[str, ...]):
    count = evaluate_value(ctx, spec.get("count", 1))
    destination = DESTINATIONS[spec.get("destination", "hand")]
    tapped = bool(spec.get("tapped"))
    selector = spec.get("selector") or {}
    # A search of a hidden zone ends in a shuffle (701.19c), and the library is
    # the only zone here that is ordered enough for it to matter.
    shuffles = "library" in zones and spec.get("shuffle", True)
    for pid in select_players(ctx, spec.get("player", "you")):
        pool: list[int] = []
        for zone_name in zones:
            zone = ZONE_NAMES[zone_name]
            pool.extend(
                oid
                for oid in ctx.state.players[pid].zone_list(zone)
                if _matches_in_zone(ctx, oid, selector, zone_name)
            )
        if pool:
            take = min(count, len(pool))
            prompt = "Search your library" if zones == ("library",) else "Search"
            picked = yield from ask_objects(ctx, prompt, pool, 0, take, pid, "search")
            _move_found(ctx, picked, pid, destination, spec, tapped, "search")
        if shuffles:
            shuffle_library(ctx.state, pid)


def _move_found(
    ctx: EffectContext,
    picked: list[int],
    pid: int,
    destination: Zone,
    spec: Mapping[str, Any],
    tapped: bool,
    cause: str,
) -> None:
    """Send the cards a library lookup turned up to their destination."""
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
            cause=cause,
        )


@register("look_at_top")
def op_look_at_top(ctx: EffectContext, spec: Mapping[str, Any]):
    """Look at the top N cards of a library and take some of what is there.

    Not a narrower ``search_library``: the pool is bounded to ``amount`` cards
    off the top, which is the whole of what makes Through the Forest Gate a
    gamble rather than a tutor.  Written with ``search_library`` it would find
    every land in the deck.

    Two other differences follow from the same distinction. Nothing is shuffled
    unless the card says so -- the cards you did not take stay on top, in order,
    which is what "look at" means and the opposite of rule 701.19's mandatory
    shuffle after a search. And ``objects`` carries the count, so "any number of
    land cards from among them" is the ordinary ``count: "any"`` rather than a
    second spelling that only this op understands.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    destination = DESTINATIONS[spec.get("destination", "hand")]
    tapped = bool(spec.get("tapped"))
    selector = spec.get("objects") or spec.get("selector") or {}
    for pid in select_players(ctx, spec.get("player", "you")):
        top = list(ctx.state.players[pid].library[: max(0, int(amount))])
        pool = [oid for oid in top if _matches_library(ctx, oid, selector)]
        if pool:
            picked = yield from pick_from_pool(
                ctx, pool, selector, "Look at the top of your library", "look_at_top", pid
            )
            _move_found(ctx, picked, pid, destination, spec, tapped, "look_at_top")
        if spec.get("shuffle", False):
            shuffle_library(ctx.state, pid)


def _matches_in_zone(
    ctx: EffectContext, oid: int, selector: Mapping[str, Any], zone: str = "library"
) -> bool:
    """Does this card match, tested as a card sitting in ``zone``?

    The zone is forced rather than read off the selector, because the op has
    already decided which zone it is looking in -- and a union search must test
    each half against the zone that half actually came from, or a graveyard
    creature would be judged as though it were in a library.
    """
    from .selectors import matches

    probe = dict(selector)
    probe["zone"] = zone
    probe.pop("controller", None)
    probe.pop("count", None)
    probe.pop("chooser", None)
    return matches(ctx, oid, probe)


def _matches_library(ctx: EffectContext, oid: int, selector: Mapping[str, Any]) -> bool:
    return _matches_in_zone(ctx, oid, selector, "library")


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
        # "…return it to the battlefield with a -1/-1 counter on it." Persist
        # and undying, and the counter is not decoration: it is the whole loop
        # guard, because the returned creature only persists again if it comes
        # back without one.
        #
        # Placed immediately after the move rather than as an enters-with
        # replacement, which is the same trade `zones._enter_battlefield`
        # already documents for "as this enters, choose a type": the window is
        # observable only by another trigger ordered between the two.
        for kind, amount in (spec.get("counters") or {}).items():
            add_counters(ctx.state, oid, str(kind), int(amount), source=ctx.source_oid)


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


@register("look_at_hand")
def op_look_at_hand(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Look at target player's hand." Private information, to one seat.

    Not ``reveal``, and the difference is the card. Revealing is public: a card
    that revealed an opponent's hand would tell that opponent's *other*
    opponents everything too, which Glasses of Urza does not do and which
    changes who is winning at a four-player table.

    Recorded on each card as an entitlement rather than emitted as an event,
    because ``player_view`` is rebuilt on every request and has to be able to
    answer "may this seat see this card?" long after the ability resolved.
    """
    for pid in select_players(ctx, spec.get("player", "opponent")):
        hand = ctx.state.players[pid].hand
        for oid in hand:
            obj = ctx.state.objects.get(oid)
            if obj is not None:
                obj.revealed_to.add(ctx.controller)
        ctx.state.emit(
            "hand_looked_at",
            player=ctx.controller,
            source=ctx.source_oid,
            target_player=pid,
            cards=len(hand),
        )


@register("scry")
def op_scry(ctx: EffectContext, spec: Mapping[str, Any]):
    """Look at the top N cards; put any number on the bottom in the chosen order.

    ``player`` names whose library, and ``chooser`` names who decides. They are
    the same person for scry and **different people for fateseal** — "look at
    the top card of target player's library. You may put that card on the
    bottom" — which is the whole of that keyword and the only reason it is not
    scry with a different player spec.

    The census said the op was "hard-wired to the controller"; it was the other
    way round. `player` had always been a spec, and it was the *asker* that was
    hard-wired — to the library's owner. So fateseal written without this would
    have let the opponent decide what to leave on top of their own deck, which
    is worse than not implementing it.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    chooser_spec = spec.get("chooser")
    for pid in select_players(ctx, spec.get("player", "you")):
        library = ctx.state.players[pid].library
        top = list(library[:amount])
        if not top:
            continue
        if chooser_spec is None:
            who = pid
        else:
            picked = select_players(ctx, chooser_spec)
            who = picked[0] if picked else ctx.controller
        to_bottom = yield from ask_objects(ctx, "Put on the bottom", top, 0, len(top), who, "scry_bottom")
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
