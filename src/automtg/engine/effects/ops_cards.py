"""Effect ops that move cards around: draw, discard, mill, search, recursion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..characteristics import chars
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
    """Discard cards, optionally letting the player choose how many.

    ``up_to`` makes ``amount`` a **ceiling** rather than an exact count, so the
    floor is zero and the player may decline entirely: "discard up to two cards"
    (Joshua) and, with ``amount`` reading the hand size, "discard any number of
    cards" (Celes). Without it the count is exact, which is the ordinary
    "discard a card" and stays the default -- an exact discard offered as a
    range would let a player keep the card a cost was meant to take.

    ``as`` records what actually went, the way `exile`, `sacrifice` and
    `reveal` already do. Three cards need it and none of them can be written
    without it:

    - "then draw that many cards" -- Joshua -- reads
      ``{"count": {"binding": ...}}``;
    - "draw that many cards plus one" -- Celes -- the same, plus one;
    - "If a **creature card** was discarded this way" -- Mog -- an `exists`
      over the binding with a `types` filter.

    Every near-miss is wrong in a way nobody would spot on the board:
    `cards_to_graveyard_this_turn` is a turn-wide integer over every graveyard
    at the table, and counting your own graveyard counts what was already in it.

    The binding **accumulates** across players rather than being overwritten,
    because Mog discards one card per player in a single resolution and then
    asks what was discarded *at all*, not what the last player pitched.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    random = bool(spec.get("random"))
    up_to = bool(spec.get("up_to"))
    # "Each player **discards their hand**" -- Windfall, Wheel of Fortune. Not
    # expressible as an `amount`: the amount is evaluated once, above this
    # loop, so it cannot be a different number for each player. Every near-miss
    # spelling gets it wrong quietly -- a `cards_in_hand` amount reads the
    # *resolving* player's hand and then takes that many from everyone, so a
    # Windfall cast with three in hand rips three from an opponent holding
    # seven and leaves four.
    whole_hand = bool(spec.get("whole_hand"))
    name = spec.get("as")
    taken: list[int] = []
    for pid in select_players(ctx, spec.get("player", "you")):
        hand = list(ctx.state.players[pid].hand)
        if not hand:
            continue
        take = len(hand) if whole_hand else min(amount, len(hand))
        if random:
            # A random discard has no floor to relax: nobody is choosing, so
            # "up to" and "exactly" pick the same cards.
            picked = ctx.state.rng.shuffled(hand)[:take]
        elif whole_hand:
            # No choice to make: the whole hand goes, so asking would be a
            # prompt with exactly one legal answer.
            picked = hand
        else:
            floor = 0 if up_to else take
            picked = yield from ask_objects(ctx, "Discard", hand, floor, take, pid, "discard")
        taken.extend(picked)
        yield from _replacements().discard(ctx.state, pid, picked)
    if name:
        ctx.bindings[str(name)] = taken


@register("mill")
def op_mill(ctx: EffectContext, spec: Mapping[str, Any]):
    """Put cards from the top of a library into its owner's graveyard.

    ``as`` records the cards this op actually milled, accumulating across the
    players it touched -- Locke, Treasure Hunter: "each player mills a card. If
    a **land card was milled this way**, create a Treasure token."

    The binding is what makes that sentence sayable at all. `exists` over a
    graveyard selector is a different card: it matches a land that was already
    sitting in somebody's graveyard, so Locke would make a Treasure every attack
    whatever the mill turned up. Milling less than asked is not an error either
    (701.13b), so the record is what was moved rather than what was requested.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    milled: list[int] = []
    for pid in select_players(ctx, spec.get("player", "you")):
        milled.extend(mill_cards(ctx.state, pid, amount))
    if name := spec.get("as"):
        previous = ctx.bindings.get(str(name))
        earlier = list(previous) if isinstance(previous, list) else []
        ctx.bindings[str(name)] = earlier + milled


@register("grant_playable")
def op_grant_playable(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until end of turn, you may cast a spell from among those cards."

    Locke, Treasure Hunter. A **standing permission** left on cards where they
    already are, which is what separates it from every neighbouring op:
    `play_exiled` casts one card there and then, for free, out of exile;
    `exile`'s `playable_this_turn` grants the same permission but only to cards
    it has just exiled. Locke's cards stay in their owners' graveyards --
    including an opponent's -- and are paid for at their printed price.

    ``any_type`` is the clause Valigarmanda prints beside the permission --
    "and mana of any type can be spent to cast that spell" -- and belongs to
    the same grant rather than to the player or the turn.

    ``limit`` is "a spell", singular. Counted per granting permanent in the turn
    ledger, the way a `cast_from_graveyard` permission is, so two Lockes are two
    spells and one Locke milling three cards is still one.
    """
    oids = resolve_pool(ctx, spec.get("objects"))
    limit = int(spec.get("limit", 0) or 0)
    any_type = bool(spec.get("any_type"))
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        obj.playable_by = ctx.controller
        obj.playable_turn = ctx.state.turn
        obj.playable_group = ctx.source_oid if limit else None
        # "…and mana of any type can be spent to cast that spell" travels with
        # the permission it is printed beside, and expires with it: the flag is
        # read only where `playable_turn` already gates the offer.
        obj.playable_any_type = any_type


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
    # "…then if you control four or more lands, untap **that land**" (Fabled
    # Passage). The referent is the card this very search turned up, and nothing
    # else can name it: a fresh filter for a tapped basic would also match a land
    # tapped for mana three turns ago, which is a different card. Accumulated
    # across `player`, because one binding names everything the op found.
    found: list[int] = []
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
            if spec.get("share_subtype") and take > 1:
                picked = yield from _search_sharing(ctx, prompt, pool, take, pid)
            else:
                picked = yield from ask_objects(ctx, prompt, pool, 0, take, pid, "search")
            if spec.get("reveal") and picked:
                # "…search your library for a Vampire card, **reveal it**, then
                # shuffle and put that card on top." Revealed on the way out, so
                # the table sees it whatever happens to it next.
                ctx.state.emit(
                    "reveal",
                    player=pid,
                    source=ctx.source_oid,
                    cards=[ctx.state.objects[o].def_id for o in picked if o in ctx.state.objects],
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
        found.extend(picked)

    # After the moves, unlike `exile` and `sacrifice`, which write before theirs.
    # A search's cards are *going somewhere usable* -- onto the battlefield, into
    # a hand -- and the next effect wants them where they landed. The oid is
    # stable across the zone change, so this is a note about intent rather than a
    # correctness difference. An empty search binds an empty list, so a following
    # `if` sees no objects rather than a stale name.
    if name := spec.get("as"):
        ctx.bindings[str(name)] = found


def _search_sharing(ctx: EffectContext, prompt: str, pool: list[int], take: int, pid: int):
    """ "…for up to two basic land cards **that share a land type**" (Myriad Landscape).

    A constraint between the picks, which no selector can state: every clause in
    `_matches_in_zone` is evaluated against one candidate in isolation, so
    `subtypes` can say "each is a basic land" and never "these two match". The
    nearest clause, `shares_a_type_with`, compares against an object already in
    `ctx.bindings`, and nothing binds a card the same search is still choosing.

    So the choice is staged rather than the filter widened: pick one from the
    whole pool, then offer only the cards sharing a subtype with it. Still one
    search of one zone and one shuffle -- two `search_library` ops in sequence
    would be a different card, shuffling twice and carrying two independent "up
    to" counts, which leaves the second pick unconstrained.

    Declining the first pick takes nothing, because "up to two" includes zero.
    Hardcoding `subtypes: ["Forest"]` was the other tempting shortcut and it
    takes a choice the printed card gives the player.
    """
    first = yield from ask_objects(ctx, prompt, pool, 0, 1, pid, "search")
    if not first:
        return []
    lead = first[0]
    shared = chars(ctx.state, lead).subtypes
    rest = [oid for oid in pool if oid != lead and (chars(ctx.state, oid).subtypes & shared)]
    if not rest:
        return list(first)
    more = yield from ask_objects(
        ctx, f"{prompt} (sharing a type)", rest, 0, take - 1, pid, "search"
    )
    return list(first) + list(more)


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
        # "Exile the top card of your library **face down**." Necropotence.
        # Face-down here is *privacy*, not the 707 morph identity `face_down`
        # carries: a card in exile has no characteristics to hide behind. What
        # the printed words buy is that nobody has been shown it -- its own
        # controller included -- so `revealed_to` stays empty and
        # `hidden_in_exile` says that the emptiness is deliberate. The flag is
        # needed because exile is otherwise a **public** zone that `player_view`
        # sends in full, so an empty `revealed_to` alone is the default every
        # ordinary exile already has and would leave these words inert.
        # `hideaway` writes `revealed_to.add(pid)` instead, because 702.75a says
        # its controller may look; Necropotence does not.
        #
        # Written after the move for `playable_this_turn`'s reason:
        # `reset_permanent_state` runs on the way and clears `revealed_to`.
        if destination is Zone.EXILE and spec.get("face_down"):
            obj = ctx.state.objects.get(oid)
            if obj is not None:
                obj.hidden_in_exile = True
                obj.revealed_to = set()


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

    ``cast_free`` sends what was picked to the **stack** instead of to a
    destination zone -- see :func:`_cast_from_window`.

    ``as`` records the cards this op actually took, and is what lets a *later*
    effect name them. Necropotence is the card: "exile the top card of your
    library face down. Put **that card** into your hand at the beginning of your
    next end step" -- a `delay` copies `ctx.bindings` when it is created, so
    `{"binding": …}` in the scheduled effects moves exactly the card this
    activation exiled.

    `exiled_with: "self"` cannot do that job and is the trap worth naming.
    `_move_found` deliberately writes no `exiled_by` -- see
    :func:`_cast_from_window` for why that would break Florian -- so the
    selector matches nothing and the delayed return silently hands back no card
    at all. Even with the link written it would be *source-wide* rather than
    per-activation, so a second activation's return would sweep up the first
    one's card too. The binding is per-resolution, which is what the printed
    "that card" means.

    ``face_down`` is exile without showing it to anybody, and only exile: see
    :func:`_move_found`.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    destination = DESTINATIONS[spec.get("destination", "hand")]
    tapped = bool(spec.get("tapped"))
    cast_free = bool(spec.get("cast_free"))
    selector = spec.get("objects") or spec.get("selector") or {}
    binding = spec.get("as")
    bound: list[int] = []
    for pid in select_players(ctx, spec.get("player", "you")):
        top = list(ctx.state.players[pid].library[: max(0, int(amount))])
        pool = [oid for oid in top if _matches_library(ctx, oid, selector)]
        if cast_free:
            # "…cast **a spell**…" -- a land is played, never cast (601.2), and
            # `cast_for_free` would put one on the stack without complaint. The
            # filter belongs here rather than in the card's selector because
            # "mana value 3 or less" is true of every land ever printed, so the
            # selector that spells Perception Bobblehead would otherwise offer a
            # free Forest-on-the-stack.
            pool = [oid for oid in pool if not ctx.state.card_of(ctx.state.objects[oid]).is_land]
        taken: set[int] = set()
        if pool:
            picked = yield from pick_from_pool(
                ctx, pool, selector, "Look at the top of your library", "look_at_top", pid
            )
            if cast_free:
                taken = set((yield from _cast_from_window(ctx, pid, picked)))
            else:
                _move_found(ctx, picked, pid, destination, spec, tapped, "look_at_top")
                taken = set(picked)
            # Accumulated across seats rather than assigned, for the reason
            # `exile`'s own `as` accumulates: a `player: "each_player"` look
            # would otherwise bind only the last seat's cards and strand the
            # rest, findable by nothing.
            bound.extend(taken)
        # "…and put the rest on the bottom of your library in a random order."
        # Florian. Shuffling instead is a different game action: it reorders the
        # *whole* deck, and everything under the cards you looked at was already
        # in an order somebody may be counting on.
        #
        # "The rest" means what was looked at and not taken -- including cards
        # the selector filtered out of the pool, which were still looked at.
        if spec.get("rest_to_bottom", False):
            _bottom_in_random_order(ctx, pid, [oid for oid in top if oid not in taken])
        if spec.get("shuffle", False):
            shuffle_library(ctx.state, pid)
    if binding:
        # Set even when nothing was taken -- an empty library is a real outcome,
        # and a later `{"binding": …}` reading a *missing* key is a different
        # failure from one reading an empty list.
        ctx.bindings[str(binding)] = bound


def _cast_from_window(ctx: EffectContext, pid: int, picked: list[int]):
    """ "You may cast a spell … from among them without paying its mana cost."

    Perception Bobblehead. Ripple's shape -- offer, cast, fold the refusals back
    into "the rest" -- with ripple's hardcoded "same name as this spell" test
    replaced by the selector `look_at_top` already accepts, which is what lets a
    card say "with mana value 3 or less".

    Returns the oids that actually reached the stack, so the caller's
    `rest_to_bottom` bottoms everything else. That is the whole reason this is a
    key on `look_at_top` rather than an `exile` + `play_exiled` pair:

    - **`play_exiled` cannot see these cards.** Its selector defaults to
      `exiled_with: "self"`, answered by `obj.exiled_by`, which `move_object`'s
      `reset_permanent_state` clears on the way into exile. `look_at_top`'s
      exile destination therefore hands `play_exiled` an empty pool and the
      whole ability silently does nothing.
    - **Writing `exiled_by` in `_move_found` would fix the plumbing and break
      the card.** A declined card would sit in exile for the rest of the game
      instead of going to the bottom with the rest, which is a strictly worse
      card than the printed one and an observable rules difference; and it would
      exile cards the printed card only ever *looks at*.
    - **A binding read by a later op** buys the same thing for two ops, a new
      selector key and an implicit contract between them, and still leaves the
      "the rest" bookkeeping split across the pair.

    Rule 601.2b: this is a real cast. `_offer_free_cast` shares
    `suspend.cast_for_free`, so the spell uses the stack, its "when you cast"
    triggers fire and it can be countered -- and it is offered rather than
    forced, because the printed word is "may". A cast that cannot happen (no
    legal target) is a refusal, not a crash, and folds back into the rest too.
    """
    cast: list[int] = []
    for oid in picked:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        name = ctx.state.card_of(obj).name
        if (
            yield from _offer_free_cast(ctx, pid, oid, f"Cast {name} without paying its mana cost?")
        ):
            cast.append(oid)
    return cast


def _bottom_in_random_order(ctx: EffectContext, pid: int, oids: list[int]) -> None:
    """ "…put the rest on the bottom of your library in a random order."

    Cascade, ripple, hideaway, `reveal_until`, and every "look at the top N"
    card that does not simply leave them there. Not a shuffle: shuffling
    reorders the *whole* library and would destroy a stacked top somebody else
    set up, which is a different game action with a different cost. The
    randomness is over these cards only.

    The cards arrive in two states and each needs its own move. Cascade's are in
    **exile**, and those have to travel through `move_object` -- an object whose
    `zone` and whose containing list disagree is a card every other reader in
    the engine sees differently. `look_at_top`'s and `reveal_until`'s never left
    the library, and for those `move_object` would announce a zone change that
    did not happen, once per card -- which for a `reveal_until` that ran the
    library out is once for the whole deck. Those are spliced within the list
    instead. Both branches append in the same shuffled order, so a mixed set --
    ripple's, whose declined match is in exile and whose misses never moved --
    still lands in one random order rather than two.
    """
    if not oids:
        return
    order = ctx.state.rng.shuffled(list(oids))
    staying = {
        oid
        for oid in order
        if (obj := ctx.state.objects.get(oid)) is not None and obj.zone is Zone.LIBRARY
    }
    player = ctx.state.players[pid]
    player.library = [oid for oid in player.library if oid not in staying]
    for oid in order:
        if oid in staying:
            ctx.state.players[pid].library.append(oid)
        else:
            move_object(ctx.state, oid, Zone.LIBRARY, to_player=pid, cause="bottomed")


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


@register("return_to_origin")
def op_return_to_origin(ctx: EffectContext, spec: Mapping[str, Any]):
    """Return exiled cards to the zone each of them came from.

    Cloak and Dagger, Entwined -- "exile a nonland card from their hand **or**
    the chosen creature until Cloak and Dagger leave the battlefield". One
    exile, two possible origins, and the return has to undo whichever happened:
    the card taken out of a hand goes back to that hand, the permanent taken off
    the battlefield goes back to the battlefield.

    **Every neighbouring op hardwires its destination**, which is why none of
    them can say this: `return_to_hand` is the hand, `put_onto_battlefield` is
    the battlefield, `return_from_graveyard` takes a `destination` but reads its
    pool out of a graveyard. Writing the card as two ops filtered by origin
    would be two sentences where the printing has one -- and there was nothing
    to filter on either, since only the graveyard kept an arrival record.

    So `zones.exile` now stamps `exiled_from` on the way out and this reads it
    back. Owner rather than controller, and the same on both branches: a card
    leaving exile goes to its owner's hand, and 400.7's exceptions do not
    reach a permanent returning from an exile-until effect.

    A card whose `exiled_from` is missing is left where it is. That is not a
    silent failure but the same answer 400.7 gives: an object with no recorded
    origin has nowhere to be returned to, and the alternative -- guessing the
    battlefield -- would put a card in a hand onto the board.
    """
    from ..enums import Zone as _Zone

    zones = {z.value: z for z in _Zone}
    oids = yield from choose_objects(ctx, spec.get("objects"), "Return")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or obj.zone is not _Zone.EXILE:
            continue
        origin = zones.get(obj.exiled_from or "")
        if origin is None or origin is _Zone.EXILE:
            continue
        move_object(
            ctx.state,
            oid,
            origin,
            to_player=obj.owner,
            cause="returned",
            by=ctx.source_oid,
        )


@register("return_spell_to_hand")
def op_return_spell_to_hand(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Return target spell to its owner's hand." Reprieve is the witness.

    **Not a counter, and not `return_to_hand` either.** Both near misses are
    wrong in ways that look right:

    - `counter` is the only other op that consumes a spell target, and its
      destination is hardwired to the graveyard. It also refuses a spell with
      "this spell can't be countered" and emits `SPELL_COUNTERED`, and neither
      belongs here: rule 701.5a makes countering one specific action, and
      returning a spell to a hand is not it. Reprieve answers an uncounterable
      spell perfectly well, and nothing that triggers on countering fires.
    - `return_to_hand` reaches the right zone but cannot see a spell. A
      `kind: "spell"` target is a `TargetRef.stack(sid)`, and `resolve_pool`'s
      `{"target": …}` branch keeps only `kind == "object"` refs -- so the pool
      comes back empty and the op is a *silent* no-op: the targeted spell
      resolves onto the battlefield untouched and the card still looks like it
      worked. That is why this reads `ctx.target_sids`, the way `counter` does.

    Selecting the spell by zone instead (`objects: {"zone": "stack"}`) does move
    it, but it is untargeted -- it would sweep every spell on the stack, and
    ward, hexproof and "can't be the target of spells" would all stop applying
    to a card whose printed line says "target".

    Where the card lands is its **owner's** hand, not the controller's: a stolen
    or an opponent's spell goes home. `pull_spell_off_stack` does that, and the
    706.10 case where the "spell" is a copy and there is no card at all.
    """
    from ..stack import pull_spell_off_stack

    target_id = str(spec.get("target", "t1"))
    for sid in ctx.target_sids(target_id):
        pull_spell_off_stack(ctx.state, sid, Zone.HAND, cause="returned", by=ctx.source_oid)


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
    """ "Look at target player's hand." Private information, to one seat.

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
        to_bottom = yield from ask_objects(
            ctx, "Put on the bottom", top, 0, len(top), who, "scry_bottom"
        )
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
        to_bin = yield from ask_objects(
            ctx, "Put into your graveyard", top, 0, len(top), pid, "surveil"
        )
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


#: What `roll_dice` writes under its ``as`` name, and what `{"rolled": …}` reads
#: back: ``{"results": [face, …], "sides": 6}``.
#:
#: A **mapping** rather than the bare list of faces every other recording op
#: writes, and the reason is not taste. `selectors._bound_oids` reads any bound
#: list as a list of **oids**, so `[6, 3, 2]` would make
#: `{"count": {"binding": "roll"}}` answer 3 by luck and
#: `{"objects": {"binding": "roll"}}` name objects 6, 3 and 2 -- three
#: permanents that have nothing to do with the roll, silently destroyed by the
#: next op along. A mapping with no ``oid`` key reads back through the same path
#: as *no objects at all*, which is the truth: rolling a die creates nothing to
#: point at.
ROLL_RESULTS = "results"
ROLL_SIDES = "sides"

#: The default die. Rule 705.1 does not privilege one, but every card in the
#: pool that rolls says "six-sided", so a missing ``sides`` is that and not a
#: guess.
DEFAULT_SIDES = 6


@register("roll_dice")
def op_roll_dice(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 705.1 -- roll dice, and write down every face that came up.

    "Roll X six-sided dice, where X is the number of Bobbleheads you control.
    Create a tapped Treasure token for each even result. If you rolled 6 exactly
    seven times, you win the game." -- Luck Bobblehead.

    The op is the roll and **only** the roll. What makes it usable is that it
    records its results under an ``as`` name, the way `create_token` records the
    oids it made and `sacrifice` records what it consumed, so the two sentences
    after it are two *reads of one roll* rather than two rolls::

        {"op": "roll_dice", "count": {"count": {...Bobbleheads...}}, "as": "roll"}
        {"op": "create_token", "token": "treasure_token", "tapped": true,
         "amount": {"rolled": {"binding": "roll", "parity": "even"}}}
        {"op": "if",
         "condition": {"cmp": "=", "right": {"const": 7},
                       "left": {"rolled": {"binding": "roll", "face": 6}}},
         "then": [...]}

    Rolling twice -- once to count the evens and once to count the sixes --
    would be a different and much worse card: on six dice the printed one makes
    a Treasure for every even *it actually rolled*, and the sixes it counts are
    a subset of them. Two rolls decorrelate the halves, so a hand that rolled
    seven 6s would create Treasures off some other roll entirely. That is the
    whole reason the binding exists rather than a `clash`-style boolean.

    ``count`` is a value expression and not a literal, because X here is a board
    count that changes between activations; ``sides`` is a literal, because no
    printed card rolls a die whose size it does not name.

    Determinism: the faces come from ``state.rng``, the engine's single seeded
    source, so a replay of the same seed and action tape rolls the same dice.
    Nothing in the package may call :mod:`random` directly.

    **Zero dice is a real case**, not an edge one: "X is the number of
    Bobbleheads you control" is 0 on an empty board, and the op must still write
    an (empty) binding so the reads after it answer 0 rather than reading
    whatever a previous resolution left behind. No event is emitted for it --
    nothing was rolled.
    """
    sides = int(spec.get(ROLL_SIDES, DEFAULT_SIDES))
    # `max(0, …)` rather than a refusal: "X is the number of Bobbleheads you
    # control" can only be negative through arithmetic a card should not be
    # writing, and rolling a negative number of dice has no reading at all.
    count = max(0, evaluate_value(ctx, spec.get("count", 1)))
    results = [ctx.state.rng.randint(1, sides) for _ in range(count)]
    # Written whatever the count, including zero -- see the docstring. The
    # loader requires the `as`; the default is here so a direct call cannot
    # raise instead of rolling.
    ctx.bindings[str(spec.get("as") or "roll")] = {
        ROLL_RESULTS: results,
        ROLL_SIDES: sides,
    }
    if results:
        ctx.state.emit(
            EventType.DICE_ROLLED,
            player=ctx.controller,
            source=ctx.source_oid,
            results=list(results),
            sides=sides,
        )


def _offer_free_cast(ctx: EffectContext, pid: int, oid: int, prompt: str):
    """ "You may cast it without paying its mana cost."  Returns whether it was.

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


@register("cast_from_hand")
def op_cast_from_hand(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You may cast a spell from your hand without paying its mana cost."

    Electrodominance ("…with mana value X or less"), Glamdring ("…with mana
    value less than or equal to that damage"), Bolas's Citadel's cousins. The
    engine could already cast for free from the **library top** (`look_at_top`'s
    `cast_free`, cascade, Bolas's Citadel) and from **exile** (`play_exiled`,
    foretell, plot), and the one zone it could not reach was the one every card
    of this shape names.

    `grant_playable` is the near miss and is a different sentence: it *permits a
    play* from a zone that normally forbids one, at the card's printed cost. A
    card already in hand needs no permission to be cast -- what it needs is the
    price waived -- so that op is a no-op here rather than an approximation.

    ``selector`` is what may be picked, tested as a card in hand, so "an instant
    or sorcery spell with mana value 4 or less" is the printed restriction and
    not a widening. Omitted, any card in hand qualifies, which is
    Electrodominance's "a spell".

    Optional by construction: `ask_objects` with a minimum of zero is the "you
    may", so no `may` wrapper is needed and declining costs no second question.
    A player with nothing matching is not asked at all.
    """
    from ..suspend import cast_for_free
    from .selectors import select_players

    selector = spec.get("selector") or {}
    prompt = "Cast a spell without paying its mana cost"
    for pid in select_players(ctx, spec.get("player", "you")):
        pool = [
            oid
            for oid in list(ctx.state.players[pid].hand)
            # A land is not a spell and is never cast (305.9) -- it is *played*,
            # and only during your main phase with the stack empty. Excluded
            # here rather than left to each card's selector, because every
            # printed card of this shape says "cast a spell" and none of them
            # says "nonland": Electrodominance's own restriction is a mana
            # value, and a Forest has mana value 0, so the bare printed filter
            # matches it. Found by gate 5 -- the spare Forest in the sandbox
            # hand vanished, which is the whole reason that Forest is there.
            if "Land" not in ctx.state.card_of(ctx.state.objects[oid]).types
            and _matches_in_zone(ctx, oid, selector, "hand")
        ]
        if not pool:
            continue
        picked = yield from ask_objects(ctx, prompt, pool, 0, 1, pid, "cast_from_hand")
        if picked:
            cast_for_free(ctx.state, pid, picked[0])


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
    picked = yield from ask_objects(ctx, "Exile one face down", top, 1, 1, pid, "hideaway")
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
    """ "You may play the exiled card without paying its mana cost."

    The permission half of hideaway, and the one thing the keyword genuinely
    needed: the engine could exile a card and could cast one for free, and had
    no way to say "that one, from there".

    Shares `suspend.cast_for_free`, so it is a real cast -- it uses the stack
    and can be countered -- and shares its documented simplification: the
    targets are the first legal tuple rather than a choice.

    ``as`` records the cards that were actually **cast**, which is a different
    set from the ones offered and from the ones exiled. Kefka needs exactly that
    distinction: "each player who owns a spell you cast this way loses life
    equal to its mana value". `exiled_with: "self"` is wrong in both directions
    at once -- a card that was cast has left exile and stops matching, and a
    card the player declined still matches -- so it names "exiled this way" and
    never "cast this way". A card with no legal target is not cast at all, which
    is why the binding is built from `cast_for_free`'s answer rather than from
    the chosen list.
    """
    from ..suspend import cast_for_free

    selector = dict(spec.get("objects") or {})
    selector.setdefault("zone", "exile")
    selector.setdefault("controller", "any")
    if "binding" not in selector:
        # "The exiled card" is `exiled_with: "self"` by default -- hideaway, and
        # every card that exiles and then offers back what it exiled. A pool
        # named by a **binding** has already said which cards those are, and the
        # default would then narrow it to nothing: only `until_leaves` sets the
        # `exiled_by` link that `exiled_with` reads, so a plain `exile` followed
        # by a `play_exiled` over its own `as` matched no card at all.
        selector.setdefault("exiled_with", "self")
    oids = yield from choose_objects(ctx, selector, "Play the exiled card", "play_exiled")
    cast: list[int] = []
    for oid in oids:
        if cast_for_free(ctx.state, ctx.controller, oid):
            cast.append(oid)
    if name := spec.get("as"):
        ctx.bindings[str(name)] = cast


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


@register("reveal_until")
def op_reveal_until(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Reveal cards from the top of your library until you reveal a creature
    card that shares a creature type with it. Put that card into your hand and
    the rest on the bottom of your library in a random order." — Heirloom Blade.

    Cascade's walk with the stop test lifted out into an ordinary selector,
    which is the one thing cascade and ripple could not be asked for: cascade's
    test is hardcoded to "nonland card with lesser mana value than this spell"
    and ripple's to "the same name as this spell", and there is no parameter on
    either that a card could substitute a selector into.

    Three things separate it from `look_at_top`, and every one of them is the
    card rather than a preference:

    - the depth is **unbounded** and decided by the library, so there is no
      ``amount``. An amount large enough to fake "until" would reveal the whole
      deck and randomize all of it every time the trigger resolved.
    - there is **no choice**: the scan stops at the first match and that match
      is what moves, so nothing here is a decision and the op is not a
      generator. `look_at_top` offers every match inside its window and lets the
      player take the best one, which is a strictly better card.
    - the cards walked past are **public**. That is the difference between a
      reveal and a look, and it is information the whole table paid for.

    Running the library out with no match is an outcome, not an error: everything
    revealed goes to the bottom in a random order and nothing reaches the
    destination. It is the line's worst case rather than its edge case — an
    Equipment on an empty-ish library sees it every game — and it is also the
    reason "the rest" is bottomed in a *random* order and not left in place:
    otherwise a failed scan would hand its controller a known deck.
    """
    selector = spec.get("objects") or spec.get("selector") or {}
    destination = DESTINATIONS[str(spec.get("destination", "hand"))]
    # Defaulted **on**, unlike `look_at_top`'s. "Look at" leaves what you did not
    # take on top in order, and that is what looking means; there is no printed
    # "reveal until" that leaves the revealed cards where they were, so an
    # omitted key here would silently make a card that keeps the top of its
    # library face up and in order.
    rest_to_bottom = bool(spec.get("rest_to_bottom", True))

    for pid in select_players(ctx, spec.get("player", "you")):
        # A snapshot taken up front, because a reveal changes no zone: unlike
        # cascade, which exiles as it walks and so can keep reading `library[0]`,
        # nothing moves here until the scan is over.
        revealed: list[int] = []
        hit: int | None = None
        for oid in list(ctx.state.players[pid].library):
            revealed.append(oid)
            if _matches_library(ctx, oid, selector):
                hit = oid
                break
        if not revealed:
            continue

        ctx.state.emit(
            "reveal",
            player=pid,
            source=ctx.source_oid,
            cards=[ctx.state.objects[o].def_id for o in revealed],
        )
        # The match moves first. Bottoming first would put it among "the rest"
        # and there would be nothing left on top to take.
        if hit is not None:
            _move_found(ctx, [hit], pid, destination, spec, False, "reveal_until")
        if rest_to_bottom:
            _bottom_in_random_order(ctx, pid, [oid for oid in revealed if oid != hit])


@register("two_piles")
def op_two_piles(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "An opponent separates those cards into two piles. Put one pile into your
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
    # "…puts it on the **bottom** of their library", and Ice Magic's "on their
    # choice of the top or bottom". `from_top` cannot say either: it counts from
    # the top, and a depth big enough to reach the bottom of *this* library is a
    # number the card does not print and that a shuffle would invalidate.
    bottom = bool(spec.get("bottom"))
    owner_chooses = bool(spec.get("owner_chooses"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put on top of library")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        to_bottom = bottom
        if owner_chooses:
            # **The owner** decides, not the resolving player -- "its owner puts
            # it on their choice of the top or bottom" is the printed line, and
            # asking the caster would hand them a tempo decision the card gives
            # away.
            to_bottom = not (
                yield from ask_yes_no(ctx, "Put it on top of your library?", obj.owner)
            )
        move_object(
            ctx.state,
            oid,
            Zone.LIBRARY,
            to_player=obj.owner,
            # `None` appends, which is the bottom -- and it has to be None
            # rather than a computed length, because the length is read before
            # the card has left its old zone.
            to_index=None if to_bottom else depth - 1,
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
