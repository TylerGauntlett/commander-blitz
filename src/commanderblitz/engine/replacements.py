"""The three replacements that stop to ask -- dredge, madness and miracle --
and the draw doublers that have to be applied between them.

Every replacement effect the engine had before this is applied *synchronously*
and asks nothing: enters tapped, enters with counters, the commander zone change,
tokens ceasing to exist. That is why they live in a whitelist on the card and are
applied inline by ``zones._enter_battlefield``.

These three cannot be. Each one puts a question to a player at the exact moment
of the replacement:

    Dredge   -- "If you would draw a card, you **may** instead return this card
                from your graveyard to your hand and mill N."
    Madness  -- "If you would discard this card, exile it instead. Then you
                **may** cast it for its madness cost."
    Miracle  -- "You **may** cast this card for its miracle cost when you draw
                it, if it's the first card you drew this turn."

So they are not whitelist entries; they are the reason drawing and discarding
had to become things that can suspend. The primitives in :mod:`primitives` still
do not ask -- that module's contract is intact -- and these generators wrap them.

Why a module of its own, beside :mod:`suspend`: all three are *casts or moves
from somewhere unusual*, all three need :func:`costs.pay` and the stack, and
putting any of them in ``primitives`` would break the one rule that module has.

**The opening hand is deliberately not routed through here.** Rule 103 draws it
before the game begins, with an empty graveyard and no turn to have drawn a
first card in -- so there is nothing for dredge to replace and nothing for
miracle to be the first of. ``game.start`` still calls ``draw_cards`` directly.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import TYPE_CHECKING, Any

from . import stack, triggers
from .carddef import Cost
from .effects.context import EffectContext, ask_objects, ask_yes_no
from .enums import Zone
from .events import EventType
from .mana import ManaCost
from .player_statics import (
    draw_cap,
    draw_replacements,
    granted_miracle_cost,
    player_cant_cast_while_resolving,
    wins_on_empty_draw,
)
from .primitives import cast_locked_zones, discard_cards, draw_cards, mill_cards
from .sba import declare_win
from .targeting import enumerate_target_tuples
from .zones import move_object

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def draw(state: GameState, pid: int, count: int) -> Generator[Any, list[int], list[int]]:
    """Draw ``count`` cards, one at a time, offering dredge and miracle.

    One at a time is forced rather than tidy: dredge replaces **a** draw, so a
    player drawing three may dredge the first and draw the other two, and
    miracle asks about the *first card drawn this turn*, which stops being true
    after the first one. A `replace_draw` doubler is per draw for the same
    reason (121.2): its exemption for "the first one you draw in each of your
    draw steps" is true of one card and false of the next.
    """
    drawn: list[int] = []
    for _ in range(max(0, count)):
        drawn.extend((yield from _draw_one(state, pid, frozenset())))
    return drawn


def _draw_one(
    state: GameState, pid: int, applied: frozenset[int]
) -> Generator[Any, list[int], list[int]]:
    """One draw, after every replacement that applies to it has had its say.

    ``applied`` is the `replace_draw` sources that already replaced the draw
    this one came from. 614.5: a replacement applies to an event once, so
    Thought Reflection's two draws are not each doubled by Thought Reflection
    again -- without the set this recursion never ends -- but a second doubler
    is a different replacement, applies to *each* of them, and the two compound
    to four.

    **Ordering (616.1).** The affected player chooses which replacement applies
    first, and the only order that can change an outcome here is dredge against
    a doubler. It is offered by asking dredge first at every level: taking it
    replaces this draw outright (it is no longer a draw, so no doubler sees it),
    and declining lets the doubler turn it into draws that are each offered
    dredge again. Every ordering the player could choose is one of those paths.
    Two doublers commute, so their order is not asked.
    """
    # "Each opponent can't draw more than one card each turn" (Narset, Parter
    # of Veils). A draw past the cap does not happen, and asked **first**
    # because an event that cannot happen cannot be replaced either: no dredge,
    # no empty-library win, no doubler turning it into two draws that would
    # each be refused anyway. Nothing is attempted, so an empty library under
    # the cap is not the 104.3c "will lose" attempt either.
    cap = draw_cap(state, pid)
    if cap is not None and state.cards_drawn_this_turn.get(pid, 0) >= cap:
        return []
    replaced = yield from _dredge(state, pid)
    if replaced:
        return []
    # "If you would draw a card while your library has no cards in it, you win
    # the game instead" (Jace, Wielder of Mysteries; Laboratory Maniac). The one
    # branch `replace_draw` can never reach, because there is no card to
    # multiply. Checked **before** the doublers deliberately: a doubler turns
    # one draw into two draws and each is offered this replacement in turn, so
    # an empty library wins on the first of them rather than after both have
    # tried and failed.
    #
    # Replacing the draw is the whole of it -- `draw_cards` is never called, so
    # the 104.3c "will lose" flag it sets is never set and the state-based
    # action that would eliminate this player never fires. An implementation
    # that let the draw happen and won afterwards would lose the race: `sba`
    # checks the flag at the next opportunity, which is before anything a
    # trigger could do.
    if not state.players[pid].library and wins_on_empty_draw(state, pid):
        declare_win(state, pid)
        return []
    for source, multiplier in draw_replacements(state, pid):
        if source in applied:
            continue
        out: list[int] = []
        for _ in range(multiplier):
            out.extend((yield from _draw_one(state, pid, applied | {source})))
        return out
    # Read before the draw: `draw_cards` bumps the tally, and miracle's
    # whole content is that this was the first.
    was_first = state.cards_drawn_this_turn.get(pid, 0) == 0
    got = draw_cards(state, pid, 1)
    if got and was_first:
        yield from _miracle(state, pid, got[0])
    return got


def discard(
    state: GameState, pid: int, oids: Sequence[int], *, caused_by: int | None = None
) -> Generator[Any, list[int], list[int]]:
    """Discard these cards, sending any with madness to exile and offering the cast.

    ``caused_by`` is passed through to `discard_cards`: the controller of the
    spell or ability that caused the discard, or ``None`` for the cleanup step
    and for a discard paid as a cost. See that function.

    One call is one discard event, however many cards it takes (603.2c), so it
    opens its own `state.event_batch` and every DISCARD it fires -- the madness
    exiles and the ordinary cards alike -- carries that batch. Its own rather
    than the enclosing op's: the cleanup-step discard has no op around it and
    would otherwise share the batch of whatever resolved last, and an op that
    discards twice (once per player, or once per conniving creature) discards
    twice. Taken once, up front, because a madness cast offered mid-discard
    pays a cost, and a payment bumps the counter.
    """
    state.event_batch += 1
    batch = state.event_batch
    ordinary: list[int] = []
    for oid in oids:
        obj = state.objects.get(oid)
        if obj is None or obj.zone is not Zone.HAND:
            continue
        card = state.card_of(obj)
        if card.madness is None:
            ordinary.append(oid)
            continue
        yield from _madness(state, pid, oid, batch)
    return discard_cards(state, pid, ordinary, caused_by=caused_by, batch=batch)


# ----------------------------------------------------------------------
# one replacement each
# ----------------------------------------------------------------------


def _dredge(state: GameState, pid: int) -> Generator[Any, list[int], bool]:
    """Offer to replace this draw by dredging. Returns whether it was replaced."""

    player = state.players[pid]
    options = [
        oid
        for oid in player.graveyard
        if (card := state.card_of(state.objects[oid])).dredge
        and len(player.library) >= card.dredge
    ]
    if not options:
        return False

    ctx = EffectContext(state=state, controller=pid, source_name="Dredge")
    picked = yield from ask_objects(
        ctx, "Dredge instead of drawing?", options, 0, 1, pid, "dredge"
    )
    if not picked:
        return False

    oid = picked[0]
    card = state.card_of(state.objects[oid])
    # The mill happens as part of the replacement, so a player who cannot mill
    # that many was never offered the option -- which is the `len(library) >=`
    # test above, and is rule 702.51a rather than a convenience.
    mill_cards(state, pid, card.dredge)

    move_object(state, oid, Zone.HAND, to_player=pid, cause="dredge")
    state.emit("dredge", player=pid, source=oid, card=card.id, milled=card.dredge)
    return True


def _miracle(state: GameState, pid: int, oid: int) -> Generator[Any, list[int]]:
    """"…when you draw it, if it's the first card you drew this turn."

    The card is revealed either way: 702.94a makes the reveal the trigger's
    price, and a player who reveals and then declines has still shown the table
    what they drew.
    """
    card = state.card_of(state.objects[oid])
    # Read with the card in hand: "Nonland cards in your hand have miracle {0}"
    # (Molecule Man) gives the card the ability only there, and only while the
    # granting static is active as the card is drawn.
    granted = granted_miracle_cost(state, pid, card)
    costs = [] if card.miracle is None else [card.miracle]
    if granted is not None:
        extra = ManaCost.parse(granted)
        if extra not in costs:
            costs.append(extra)
    if not costs:
        return
    state.emit("reveal", player=pid, source=oid, cards=[card.id])
    # A printed miracle beside a granted one is two miracle abilities (702.94a),
    # each its own "you may cast it for [cost]" -- offered in turn, printed
    # first, so declining one leaves the other; one cast ends it, since the
    # card has left the hand. An identical price is one offer, not two.
    for cost in costs:
        if (yield from _offer_cast(state, pid, oid, cost, "miracle")):
            return


def _madness(state: GameState, pid: int, oid: int, batch: int) -> Generator[Any, list[int]]:
    """"If you would discard this card, exile it instead."

    The exile happens whether or not the cast is taken, and that is the half a
    naive version drops: a madness card the player declines to cast is in
    **exile**, not in the graveyard, so nothing that reads graveyards ever sees
    it. Written the other way round, every madness card would be a free
    graveyard-filler.
    """

    obj = state.objects[oid]
    card = state.card_of(obj)
    move_object(state, oid, Zone.EXILE, to_player=obj.owner, cause="madness")
    state.emit(EventType.DISCARD, player=pid, source=oid, oid=oid, madness=True, batch=batch)
    yield from _offer_cast(state, pid, oid, card.madness, "madness")


def _offer_cast(
    state: GameState, pid: int, oid: int, cost, label: str
) -> Generator[Any, list[int], bool]:
    """"You may cast it for its <label> cost."  A real cast, at a real price.

    Shares suspend's shape and not its code, because suspend's cast is *free*
    and these two have a cost to pay first -- and a cost that cannot be paid is
    not offered at all (rule 118.4), rather than asked and then failed.

    Still a cast: it uses the stack, it can be countered, and its targets are
    chosen now. Targets are the first legal tuple, which is the same
    simplification `suspend.cast_for_free` documents.
    """
    # Local: `costs` imports `replacements` to discard.
    from .costs import can_pay, pay, zone_of

    obj = state.objects.get(oid)
    if obj is None:
        return False
    if zone_of(state, oid) in cast_locked_zones(state, pid):
        # "…can't cast spells from anywhere other than their hands."
        # (Avatar's Wrath.) Madness casts from **exile** and the impulse family
        # from a graveyard, both of which this lock shuts, and both of them
        # reach the stack without passing through `casting._cast_actions`.
        # Checked before the question, for the reason the total prohibition
        # below is: a prompt the player cannot act on is an offer the engine
        # does not honour.
        return False
    if player_cant_cast_while_resolving(state, pid, state.card_of(obj)):
        # Voice of Victory (101.2): the "can't" beats the "may", and it is
        # checked before the question rather than after, because a prompt the
        # player cannot act on is an offer the engine does not honour. A madness
        # card stays in exile, the outcome declining already has.
        return False
    card = state.card_of(obj)
    price = Cost(mana=cost)
    if not can_pay(state, pid, price, oid):
        return False
    # Strive's surcharge is not part of `price`, so the spell takes at most one
    # target -- the count that owes none -- rather than every target on offer
    # with its cost increase unpaid.
    options = enumerate_target_tuples(
        state,
        pid,
        card.targets,
        oid,
        limit=1,
        size_cap=1 if card.strive is not None else None,
    )
    if not options:
        return False
    # And its modes, for the one card shape whose targets belong to them --
    # `stack.free_cast_modes` makes the same "first legal" choice this line
    # already makes for targets.
    modes, mode_refs = stack.free_cast_modes(state, pid, card, oid)

    ctx = EffectContext(state=state, controller=pid, source_name=card.name)
    if not (yield from ask_yes_no(ctx, f"Cast {card.name} for its {label} cost?", pid)):
        return False
    paid = yield from pay(state, pid, price, oid)
    if not paid:  # pragma: no cover - `can_pay` said yes a moment ago
        return False

    item = stack.push_spell(state, oid, pid, options[0] + mode_refs, modes=modes)
    triggers.fire(
        state,
        EventType.SPELL_CAST,
        player=pid,
        source=oid,
        oid=oid,
        spell_oid=oid,
        sid=item.sid,
        card=card.id,
        **{label: 1},
    )
    return True
