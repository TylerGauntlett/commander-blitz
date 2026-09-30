"""Suspend -- paying a card out of your hand now to cast it for free later.

    Suspend 2—{G} (Rather than cast this card from your hand, you may pay {G}
    and exile it with two time counters on it. At the beginning of your upkeep,
    remove a time counter. When the last is removed, you may cast it without
    paying its mana cost.)

Three things make this unlike everything else the engine plays:

1. **Suspending is not casting.** Nothing goes on the stack, nobody gets
   priority, and the spell cannot be countered -- so it is a special action
   (`ActionKind.SUSPEND`) rather than a variant of `CAST`.
2. **The ticking is a rule, not an ability.** A suspended card is in exile with
   no abilities of its own; the upkeep counter removal belongs to the game, the
   way the untap step does, which is why it lives here and is called from
   `turn.py` rather than being written on any card.
3. **The free cast is still a cast.** It goes on the stack, it can be
   countered, and its targets are chosen then -- it simply costs nothing.

A creature cast this way has haste, which is the only reason suspend is ever
better than waiting. Recorded as `hasted_by_suspend` on the object and read by
`characteristics`, because it must survive until the creature leaves rather than
expiring at end of turn.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

from .carddef import Cost
from .enums import Zone
from .events import EventType
from .mana import ManaCost

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState

#: The counter suspended cards carry.  Named like the printed one so a UI that
#: shows counters shows the right word.
TIME_COUNTER = "time"


def suspend_card(state: GameState, pid: int, oid: int) -> Generator[Any, list[int], bool]:
    """Pay the suspend cost and exile the card with its time counters."""
    from .costs import pay

    obj = state.objects[oid]
    card = state.card_of(obj)
    if card.suspend is None:
        return False
    cost, counters = card.suspend

    ok = yield from pay(state, pid, Cost(mana=cost), None)
    if not ok:  # pragma: no cover - legality already proved payability
        return False

    from .zones import move_object

    move_object(state, oid, Zone.EXILE, cause="suspended")
    obj.add_counter(TIME_COUNTER, counters)
    obj.suspended_by = pid
    state.emit(
        EventType.SUSPENDED, player=pid, source=oid, card=card.id, counters=counters
    )
    return True


#: What foretelling costs, fixed by rule 702.143a rather than by the card. The
#: card names only the *later* price.
FORETELL_COST = "{2}"


def foretell_card(state: GameState, pid: int, oid: int) -> Generator[Any, list[int], bool]:
    """Pay {2} and exile this card face down, to be cast on a later turn.

    Suspend's special action with a different ticking rule, which is why it
    lives here and shares `ActionKind.SUSPEND`: both exile a card from hand to
    be cast later, neither uses the stack, and neither can be countered.

    "Face down" is `revealed_to`, the engine's existing channel for information
    one seat holds -- the card is in exile and nobody else may look at it. That
    is the whole of what face-down means for a card *nobody can interact with*;
    it is a much smaller claim than a face-down **permanent**, which is a
    characteristics problem and remains unimplemented.
    """
    from .costs import pay

    obj = state.objects[oid]
    card = state.card_of(obj)
    if card.foretell is None:
        return False

    ok = yield from pay(state, pid, Cost(mana=ManaCost.parse(FORETELL_COST)), None)
    if not ok:  # pragma: no cover - legality already proved payability
        return False

    from .zones import move_object

    move_object(state, oid, Zone.EXILE, cause="foretold")
    obj.foretold_by = pid
    obj.foretold_turn = state.turn
    # Only its own controller may see what it is. Written after the move, since
    # `reset_permanent_state` clears `revealed_to` on the way.
    obj.revealed_to.add(pid)
    state.emit("foretold", player=pid, source=oid, card=card.id)
    return True


def foretold_cards(state: GameState, pid: int) -> list[int]:
    """This player's foretold cards that may be cast **now** -- a later turn."""
    return [
        oid
        for oid in state.players[pid].exile
        if (obj := state.objects.get(oid)) is not None
        and obj.foretold_by == pid
        and obj.foretold_turn < state.turn
    ]


def suspended_cards(state: GameState, pid: int) -> list[int]:
    """This player's suspended cards, oldest first for a stable tick order."""
    return [
        oid
        for oid in state.players[pid].exile
        if state.objects[oid].suspended_by == pid
        and state.objects[oid].counter(TIME_COUNTER) > 0
    ]


def tick(state: GameState, pid: int) -> None:
    """Upkeep: remove one time counter from each of this player's suspends.

    Anything that reaches zero is cast for free, in order.  The list is taken
    first because casting one can exile another -- otherwise a card suspended
    during this very upkeep would tick on the turn it arrived.
    """
    for oid in suspended_cards(state, pid):
        obj = state.objects.get(oid)
        if obj is None or obj.zone is not Zone.EXILE:
            continue
        obj.remove_counter(TIME_COUNTER, 1)
        state.emit(
            EventType.TIME_COUNTER_REMOVED,
            player=pid,
            source=oid,
            card=obj.def_id,
            remaining=obj.counter(TIME_COUNTER),
        )
        if obj.counter(TIME_COUNTER) == 0:
            cast_for_free(state, pid, oid, haste=True)


def rebound_tick(state: GameState, pid: int) -> None:
    """Rebound (702.87a): the free cast a rebounded spell is owed.

    Lives beside suspend because it *is* suspend's second half -- "you may cast
    this card from exile without paying its mana cost" is the same sentence, and
    :func:`cast_for_free` is the same code. What differs is only how the card got
    to exile and how long it waits: a time counter each upkeep, or exactly one.

    The mark is cleared **before** the cast rather than after, and that is the
    loop guard's second half: the free cast is itself a cast, so a spell that
    resolved again with the flag still set would owe another one next upkeep.
    (The first half is `cast_from_hand`, checked when the rider fires.)

    A rebounded spell with no legal target stays in exile, unmarked -- the same
    outcome suspend has, and what 702.87b says: the cast is optional and simply
    does not happen.
    """
    for oid in [o for o in state.players[pid].exile if state.objects[o].rebound_by == pid]:
        obj = state.objects.get(oid)
        if obj is None or obj.zone is not Zone.EXILE:
            continue
        obj.rebound_by = None
        state.emit(EventType.TIME_COUNTER_REMOVED, player=pid, source=oid, card=obj.def_id, remaining=0)
        cast_for_free(state, pid, oid)


def cast_for_free(state: GameState, pid: int, oid: int, *, haste: bool = False) -> bool:
    """Put a suspended card on the stack having paid nothing for it.

    Still a cast: it uses the stack, it can be countered, and its targets are
    chosen now.  A card with no legal target simply stays in exile with no time
    counters, which is what the rules say happens to it.

    Returns whether the card actually reached the stack. Every caller but one
    ignores it; `ops_cards.op_play_exiled` needs it, because "each player who
    owns a spell **you cast this way**" (Kefka) has to name the cards that were
    really cast and not the ones that were merely offered.
    """
    from . import stack, triggers
    from .costs import zone_of
    from .player_statics import player_cant_cast_spells
    from .primitives import cast_locked_zones
    from .targeting import enumerate_target_tuples

    obj = state.objects.get(oid)
    if obj is None:
        return False
    if zone_of(state, oid) in cast_locked_zones(state, pid):
        # "…can't cast spells from anywhere other than their hands."
        # (Avatar's Wrath.) A free cast is still a cast (601.2b), and this is
        # the road cascade, suspend and rebound take -- every one of them out
        # of **exile**, which is exactly a zone this lock shuts. Asked beside
        # `player_cant_cast_spells` and for its reason: the floor under every
        # free cast, so an op that forgets to ask first still cannot cast
        # through the lock. The card stays where it is, the same outcome the
        # total prohibition below produces.
        return False
    if player_cant_cast_spells(state, pid, state.card_of(obj)):
        # Voice of Victory (101.2): a "may cast" meets a "can't cast" and the
        # "can't" wins. The card stays exactly where it is -- in exile for a
        # suspend or a rebound, which is the no-legal-target outcome below, and
        # wherever the calling op left it otherwise, so cascade still bottoms
        # it with the rest. The floor under every free cast, so an op that
        # forgets to ask first still cannot cast through the lock.
        return False
    card = state.card_of(obj)

    # Strive's surcharge is not charged here -- nothing on this path pays mana
    # -- so the spell takes at most one target, the most it can have for free.
    # Taking every target the board offered would be the printed card with its
    # cost increase deleted.
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
    # And its modes, on the one card shape whose targets belong to them. Same
    # simplification, same reason: there is no seat to ask here.
    modes, mode_refs = stack.free_cast_modes(state, pid, card, oid)
    obj.suspended_by = None
    # Haste belongs to **suspend** and to nothing else that casts for free.
    # Cascade and ripple both put a creature onto the battlefield the ordinary
    # way, and one that could attack immediately would be a strictly better
    # card -- so the flag is opt-in rather than a property of casting free.
    obj.hasted_by_suspend = haste and card.is_creature

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
        free=1,
    )
    return True
