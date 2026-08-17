"""Effect ops that move cards around: draw, discard, mill, search, recursion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..events import EventType
from ..objects import PLUS_ONE
from ..primitives import add_counters, mill_cards, shuffle_library
from ..zones import move_object
from . import register
from .context import EffectContext, ask_objects, ask_player, ask_yes_no
from .selectors import (
    ZONE_NAMES,
    choose_objects,
    pick_from_pool,
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


def _replacements():
    """Imported lazily: `replacements` needs `costs`, which needs this package."""
    from .. import replacements

    return replacements


@register("draw")
def op_draw(ctx: EffectContext, spec: Mapping[str, Any]):
    draw_with_replacements = _replacements().draw

    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        # Dredge replaces *a* draw, whatever caused it, and miracle asks about
        # the first card drawn this turn however it arrived -- so every draw in
        # the engine goes through here except the opening hand.
        yield from draw_with_replacements(ctx.state, pid, amount)


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
        yield from _replacements().discard(ctx.state, pid, picked)


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
        picked: list[int] = []
        if pool:
            take = min(count, len(pool))
            prompt = "Search your library" if zones == ("library",) else "Search"
            picked = yield from ask_objects(ctx, prompt, pool, 0, take, pid, "search")
            if spec.get("reveal") and picked:
                # "…search your library for a Vampire card, **reveal it**, then
                # shuffle and put that card on top." Revealed on the way out, so
                # the table sees it whatever happens to it next.
                ctx.state.emit(
                    "reveal",
                    player=pid,
                    source=ctx.source_oid,
                    cards=[
                        ctx.state.objects[o].def_id
                        for o in picked
                        if o in ctx.state.objects
                    ],
                )

        # "…then shuffle **and** put that card on top" (Forerunner of the
        # Legion). The shuffle comes first when the card is going back to the
        # top of the same library, or it lands there and is immediately shuffled
        # into a random position -- which is a tutor that finds nothing.
        #
        # This is also the printed order: 701.19c's shuffle happens, and *then*
        # the card is put on top. Every other destination is unaffected, because
        # a card already in a hand or on the battlefield does not care.
        to_top = spec.get("destination") == "library_top"
        if shuffles and to_top:
            shuffle_library(ctx.state, pid)
        if picked:
            _move_found(ctx, picked, pid, destination, spec, tapped, "search")
        if shuffles and not to_top:
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
        # "Exile one of those cards … You may play the exiled card this turn."
        # Florian exiles from inside `look_at_top`, not from a separate `exile`
        # op, so the permission has to be grantable here too -- otherwise the
        # key only works on the cards that spell the exile out as its own step.
        # Written after the move, like `exile` writes it, because
        # `reset_permanent_state` runs on the way and would wipe the pair.
        if destination is Zone.EXILE and spec.get("playable_this_turn"):
            obj = ctx.state.objects.get(oid)
            if obj is not None:
                obj.playable_by = pid
                obj.playable_turn = ctx.state.turn


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
        # "…and put the rest on the bottom of your library in a random order."
        # Florian. Shuffling instead is a different game action: it reorders the
        # *whole* deck, and everything under the cards you looked at was already
        # in an order somebody may be counting on.
        #
        # "The rest" means what was looked at and not taken -- including cards
        # the selector filtered out of the pool, which were still looked at.
        if spec.get("rest_to_bottom", False):
            taken = set(picked) if pool else set()
            _bottom_in_random_order(ctx, pid, [oid for oid in top if oid not in taken])
        if spec.get("shuffle", False):
            shuffle_library(ctx.state, pid)


def _bottom_in_random_order(ctx: EffectContext, pid: int, oids: list[int]) -> None:
    """Move these cards to the bottom of their owner's library, shuffled.

    Only these: the rest of the library keeps the order it had, which is the
    whole difference between this and `shuffle_library`.
    """
    if not oids:
        return
    moving = set(oids)
    player = ctx.state.players[pid]
    remaining = [oid for oid in player.library if oid not in moving]
    player.library = remaining + ctx.state.rng.shuffled(list(oids))


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
        move_object(
            ctx.state, oid, Zone.HAND, to_player=obj.owner, cause="returned", by=ctx.source_oid
        )


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
    """Show cards to the table.

    Goes through ``choose_objects`` rather than ``resolve_pool`` so a selector's
    ``count`` means here what it means everywhere else. That is amplify: "reveal
    **any number** of Beast cards from your hand" is `count: "any"`, and with a
    bare pool resolution the card would reveal the whole hand and ask nothing.
    The default is still ``"all"``, so every existing reveal is unchanged.

    ``as`` records what was shown, because the count is the card: "this creature
    enters with X +1/+1 counters, where X is the number of cards revealed this
    way". Nothing can name that set afterwards -- the revealed cards are back
    among a hand full of others the moment the op returns.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Reveal", "reveal")
    if name := spec.get("as"):
        ctx.bindings[str(name)] = list(oids)
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


@register("explore")
def op_explore(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 701.40a — reveal the top card, and route it by whether it is a land.

    "Reveal the top card of your library. Put that card into your hand if it's a
    land. Otherwise, put a +1/+1 counter on this creature, then put that card
    back on top of your library or into your graveyard."

    One op rather than a `reveal` plus an `if`, and the reason is the branch
    itself: the test is on **the card that was revealed**, which no condition can
    name. `snapshot` binds an object a selector already found, and the nearest a
    card could otherwise get is `{"exists": {"zone": "library", "types":
    ["Land"]}}` — "is there a land somewhere in my deck", true in essentially
    every game, which would make Merfolk Branchwalker draw a card every time.

    Three details that are wrong in a way no board would show:

    - **The counter goes on the exploring permanent**, not on the ability's
      source. "Target creature you control explores" puts the counter on the
      target, and a version reading `self_only` would grow the wrong creature.
    - **Each permanent explores separately.** Two creatures exploring reveal two
      cards, so the library is walked once per permanent rather than once.
    - **The land half asks nothing.** Only the non-land branch is a choice
      (701.40a), and offering one for a land would let a player decline the card.

    ``objects`` is required rather than defaulted to this permanent, because the
    op is printed on sorceries as often as on creatures and a defaulted
    ``self_only`` on a sorcery resolves to the spell — which is on the stack, is
    not the exploring permanent, and would make the card reveal nothing at all.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Explore", "explore")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        pid = obj.controller
        library = ctx.state.players[pid].library
        if not library:
            # An empty library reveals nothing, so neither half happens -- not
            # even the counter, which 701.40b makes conditional on a card.
            continue
        top = library[0]
        revealed = ctx.state.objects.get(top)
        if revealed is None:
            continue
        card = ctx.state.card_of(revealed)
        ctx.state.emit("reveal", player=pid, source=ctx.source_oid, cards=[card.id])
        if card.is_land:
            move_object(ctx.state, top, Zone.HAND, to_player=pid, cause="explore")
            binned = False
        else:
            add_counters(ctx.state, oid, PLUS_ONE, 1, source=ctx.source_oid)
            binned = yield from ask_yes_no(
                ctx, f"Put {card.name} into your graveyard? (otherwise it stays on top)", pid
            )
            if binned:
                move_object(ctx.state, top, Zone.GRAVEYARD, to_player=pid, cause="explore")
        ctx.state.emit(
            "explore",
            player=pid,
            source=ctx.source_oid,
            oid=oid,
            card=card.id,
            land=card.is_land,
            binned=binned,
        )


@register("connive")
def op_connive(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 701.47a — draw, discard, and grow by what the discard was.

    "Connive N. (Draw N cards, then discard N cards. Put a +1/+1 counter on this
    creature for each nonland card discarded this way.)"

    Like `explore`, this is an op because of what the counter counts: **the cards
    that were just discarded**, which nothing in the condition or value language
    can name. `discard` puts them in a graveyard and returns nothing, so a card
    written as `draw` + `discard` + `add_counters` would have to count something
    else — and every available something else is wrong. `count` over the
    graveyard counts what was already there; `cards_to_graveyard_this_turn`
    counts every graveyard at the table and every earlier discard this turn. Both
    load, and both grow the creature by a number nobody would recognise as wrong.

    "Nonland", not "each card": conniving away two lands is the drawback, and an
    implementation that counted the discards rather than reading them would
    delete it.

    Each permanent in the pool connives on its own — its own controller draws,
    its own hand is discarded from, its own counters. That matters for "each
    creature you control connives" only at a pod, and is free here.

    *Divergence*: 701.47b keeps the draw and the discard when the conniving
    permanent has left the battlefield, and drops only the counter. Here an empty
    pool does nothing at all, so a creature killed in response to its own connive
    trigger draws nobody a card. Recorded in rules-coverage.md.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Connive", "connive")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        pid = obj.controller
        yield from _replacements().draw(ctx.state, pid, amount)
        hand = list(ctx.state.players[pid].hand)
        take = min(amount, len(hand))
        picked = yield from ask_objects(ctx, "Discard", hand, take, take, pid, "discard")
        # Read the faces before the move: a card in a graveyard is still
        # readable, but reading first means this does not depend on that.
        nonland = sum(
            1
            for o in picked
            if (card := ctx.state.objects.get(o)) is not None
            and not ctx.state.card_of(card).is_land
        )
        yield from _replacements().discard(ctx.state, pid, picked)
        add_counters(ctx.state, oid, PLUS_ONE, nonland, source=ctx.source_oid)
        ctx.state.emit(
            "connive",
            player=pid,
            source=ctx.source_oid,
            oid=oid,
            drawn=amount,
            discarded=len(picked),
            nonland=nonland,
        )


#: The binding `clash` writes and "if you win the clash" reads back.  A binding
#: rather than a `won:` block of effects, because the printed card really is two
#: sentences — "Clash with an opponent. If you win, draw a card." — and `if` is
#: already the op that says the second one.
CLASH_WON = "clash_won"


@register("clash")
def op_clash(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 701.23a — two players reveal, may bottom, and the bigger cost wins.

    "Clash with an opponent. (Each of you reveals the top card of your library,
    then puts that card on the top or bottom. A player wins if their card had a
    higher mana value.)"

    `reveal` cannot compose into this and the reason is not the reveal: it is
    that clash is a **comparison across two players' libraries**, and every
    comparison in the value language reads one board. `mana_value_of` takes a
    target or a snapshot, and neither can name a card sitting on top of an
    opponent's library — `top_of_library` is a static condition that tests a
    filter against one card and reports a boolean, so it cannot report a number
    to compare with, let alone two of them.

    The outcome is written into ``bindings`` under ``clash_won`` rather than
    carried in a ``won:`` block, because the printed card is two sentences and
    `if` is already the op that says the second one. The loader refuses either
    half without the other, the way it refuses half a kicker.

    Two boundaries, both of which a card would otherwise get quietly wrong:

    - **Each player decides about their own card**, and decides it *after* both
      are revealed. Asking the clasher about both would be a different and much
      better card, and asking before the reveal would remove the information the
      decision exists for.
    - **An empty library reveals nothing and cannot win.** "Higher than each
      other card revealed this way" is vacuously true against no card at all, so
      revealing something beats revealing nothing — and revealing nothing loses
      even to nothing.
    """
    you = ctx.controller
    opponents = ctx.opponents()
    other = yield from ask_player(ctx, "Clash with which opponent?", opponents, you)
    if other is None:
        ctx.bindings[CLASH_WON] = 0
        return

    revealed: dict[int, int | None] = {}
    for pid in (you, other):
        library = ctx.state.players[pid].library
        revealed[pid] = library[0] if library else None
    shown = [oid for oid in revealed.values() if oid is not None]
    if shown:
        ctx.state.emit(
            "reveal",
            player=you,
            source=ctx.source_oid,
            cards=[ctx.state.card_of(ctx.state.objects[oid]).id for oid in shown],
        )

    # Both cards are on the table before either player decides, which is the
    # whole of what makes the choice interesting.
    for pid in (you, other):
        oid = revealed[pid]
        if oid is None:
            continue
        name = ctx.state.card_of(ctx.state.objects[oid]).name
        to_bottom = yield from ask_yes_no(ctx, f"Put {name} on the bottom of your library?", pid)
        if to_bottom:
            library = ctx.state.players[pid].library
            library.remove(oid)
            library.append(oid)

    def value_of(oid: int | None) -> int:
        # -1 rather than 0: a card that costs {0} still beats no card at all,
        # and no card must never beat one.
        if oid is None:
            return -1
        return ctx.state.card_of(ctx.state.objects[oid]).mana_cost.mana_value()

    won = value_of(revealed[you]) > value_of(revealed[other])
    ctx.bindings[CLASH_WON] = 1 if won else 0
    ctx.state.emit(
        "clash",
        player=you,
        source=ctx.source_oid,
        opponent=other,
        won=won,
    )


def _bottom_in_random_order(ctx: EffectContext, pid: int, oids: list[int]) -> None:
    """"…put the rest on the bottom of your library in a random order."

    Cascade, ripple, and every "look at the top N" card that does not simply
    leave them there. Not a shuffle: shuffling reorders the *whole* library and
    would destroy a stacked top somebody else set up, which is a different game
    action with a different cost. The randomness is over these cards only.
    """
    for oid in ctx.state.rng.shuffled(list(oids)):
        # Through `move_object` rather than by editing the list: half of these
        # are in **exile** and half never left the library, and an object whose
        # `zone` and whose containing list disagree is a card every other reader
        # in the engine sees differently.
        move_object(ctx.state, oid, Zone.LIBRARY, to_player=pid, cause="bottomed")


def _offer_free_cast(ctx: EffectContext, pid: int, oid: int, prompt: str):
    """"You may cast it without paying its mana cost."  Returns whether it was.

    Shares `suspend.cast_for_free`, which is what makes the copy a real cast --
    it uses the stack and can be countered. Haste is **not** shared: that flag
    belongs to suspend, and a cascaded creature that could attack immediately
    would be a strictly better card.
    """
    from ..suspend import cast_for_free

    obj = ctx.state.objects.get(oid)
    if obj is None:
        return False
    if not (yield from ask_yes_no(ctx, prompt, pid)):
        return False
    before = len(ctx.state.stack)
    cast_for_free(ctx.state, pid, oid)
    return len(ctx.state.stack) > before


@register("hideaway")
def op_hideaway(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 702.75a — "look at the top N cards, exile one face down, and put the
    rest on the bottom of your library in a random order."

    Three things the engine already had, in an order nothing had needed before:
    `look_at_top`'s bounded pool, foretell's "face down in exile" (which is
    `revealed_to`, not a characteristics shell -- nobody may interact with it),
    and cascade's random bottoming.

    The link to the hideaway permanent is `exiled_by`, the O-Ring direction,
    because it is the *permanent* that later says "you may play the exiled
    card" and so the permanent is what has to find it.
    """
    amount = max(1, evaluate_value(ctx, spec.get("amount", 4)))
    pid = ctx.controller
    library = ctx.state.players[pid].library
    top = list(library[:amount])
    if not top:
        return
    picked = yield from ask_objects(
        ctx, "Exile one face down", top, 1, 1, pid, "hideaway"
    )
    if not picked:
        return
    chosen = picked[0]
    move_object(ctx.state, chosen, Zone.EXILE, to_player=pid, cause="hideaway")
    obj = ctx.state.objects[chosen]
    obj.exiled_by = ctx.source_oid
    obj.revealed_to.add(pid)
    ctx.state.emit("hideaway", player=pid, source=ctx.source_oid, oid=chosen)
    _bottom_in_random_order(ctx, pid, [oid for oid in top if oid != chosen])


@register("play_exiled")
def op_play_exiled(ctx: EffectContext, spec: Mapping[str, Any]):
    """"You may play the exiled card without paying its mana cost."

    The permission half of hideaway, and the one thing the keyword genuinely
    needed: the engine could exile a card and could cast one for free, and had
    no way to say "that one, from there".

    Shares `suspend.cast_for_free`, so it is a real cast -- it uses the stack
    and can be countered -- and shares its documented simplification: the
    targets are the first legal tuple rather than a choice.
    """
    from ..suspend import cast_for_free

    selector = dict(spec.get("objects") or {})
    selector.setdefault("zone", "exile")
    selector.setdefault("controller", "any")
    selector.setdefault("exiled_with", "self")
    oids = yield from choose_objects(ctx, selector, "Play the exiled card", "play_exiled")
    for oid in oids:
        cast_for_free(ctx.state, ctx.controller, oid)


@register("cascade")
def op_cascade(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 702.85a — exile from the top until something cheaper turns up.

    "When you cast this spell, exile cards from the top of your library until
    you exile a nonland card with lesser mana value. You may cast it without
    paying its mana cost. Put the exiled cards on the bottom of your library in
    a random order."

    An op rather than an arrangement of existing ones, and the reason is the
    **scan**: every other way the DSL reaches a library either takes the top N
    (`look_at_top`) or searches the whole of it (`search_library`), and cascade
    does neither -- it walks down until a condition is met and the depth is not
    knowable when the card is written.

    ``max_mana_value`` is the ceiling the exiled card must come in under, and it
    defaults to **this spell's own** mana value, which is what every printing
    says. It is read off the source rather than written into the card, because a
    cascade spell's own cost is the number.
    """
    pid = ctx.controller
    library = ctx.state.players[pid].library
    limit = spec.get("max_mana_value")
    if limit is None:
        source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
        ceiling = ctx.state.card_of(source).mana_value if source is not None else 0
    else:
        ceiling = evaluate_value(ctx, limit)

    exiled: list[int] = []
    hit: int | None = None
    while library:
        oid = library[0]
        card = ctx.state.card_of(ctx.state.objects[oid])
        move_object(ctx.state, oid, Zone.EXILE, to_player=pid, cause="cascade")
        exiled.append(oid)
        if not card.is_land and card.mana_value < ceiling:
            hit = oid
            break

    ctx.state.emit("cascade", player=pid, source=ctx.source_oid, exiled=len(exiled))
    if hit is not None:
        cast = yield from _offer_free_cast(
            ctx, pid, hit, f"Cast {ctx.state.card_of(ctx.state.objects[hit]).name} for free?"
        )
        if cast:
            exiled.remove(hit)
    # Whatever is still in exile goes back, including the card if it was not
    # cast -- 702.85a bottoms "the exiled cards", and the one that was cast is
    # on the stack rather than among them.
    _bottom_in_random_order(ctx, pid, exiled)


@register("ripple")
def op_ripple(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 702.20a — reveal the top N, cast the ones that match this card.

    "Ripple N — When you cast this spell, you may reveal the top N cards of your
    library. You may cast any revealed cards with the same name as this spell
    without paying their mana costs. Put the rest on the bottom of your library
    in a random order."

    Cascade's shape with a fixed depth and a different test, and the test is why
    it is its own op rather than a parameter: "the same name as this spell" is a
    comparison against the *source*, and no selector key names it. `name` takes
    a literal written into the card, which for ripple would have to be the
    card's own name repeated -- true, and wrong the moment anything copies it.
    """
    pid = ctx.controller
    amount = max(0, evaluate_value(ctx, spec.get("amount", 4)))
    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid else None
    if source is None:
        return
    name = ctx.state.card_of(source).name

    library = ctx.state.players[pid].library
    revealed = list(library[:amount])
    if not revealed:
        return
    ctx.state.emit(
        "reveal",
        player=pid,
        source=ctx.source_oid,
        cards=[ctx.state.card_of(ctx.state.objects[o]).id for o in revealed],
    )

    rest: list[int] = []
    for oid in revealed:
        if ctx.state.card_of(ctx.state.objects[oid]).name != name:
            rest.append(oid)
            continue
        move_object(ctx.state, oid, Zone.EXILE, to_player=pid, cause="ripple")
        cast = yield from _offer_free_cast(ctx, pid, oid, f"Cast {name} for free?")
        if not cast:
            rest.append(oid)
    _bottom_in_random_order(ctx, pid, rest)


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
    """Tuck an object into a library, optionally at a stated depth.

    ``from_top`` is the printed ordinal and counts from 1: absent or ``1`` is
    "on top", ``2`` is Hinder's "second from the top", ``4`` is Lost to
    Legend's "fourth from the top".  An ordinal rather than an insert index
    because that is the sentence on the card, and off-by-one is exactly the
    error nobody would see -- a card tucked third when it says fourth is drawn a
    turn early, which is the whole of what the depth buys.

    The library is always the object's **owner's**, never its controller's:
    "into its owner's library" is printed on every card in this family, and the
    difference is only visible on a stolen permanent -- where sending it to the
    thief's library would hand the victim's card to the thief for ever.
    """
    depth = max(1, evaluate_value(ctx, spec.get("from_top", 1)))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put on top of library")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        move_object(
            ctx.state,
            oid,
            Zone.LIBRARY,
            to_player=obj.owner,
            to_index=depth - 1,
            cause="tuck",
            by=ctx.source_oid,
        )
        # Only the top is announced as the top. The client renders both the same
        # way (`FxLayer` has no exit animation for either), but a card buried
        # four deep has not gone anywhere the opponent can see next turn, and the
        # log should not say it has.
        ctx.state.emit(
            EventType.ZONE_CHANGE,
            source=oid,
            to="library_top" if depth == 1 else "library",
        )
