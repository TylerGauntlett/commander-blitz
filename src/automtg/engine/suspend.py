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
            cast_for_free(state, pid, oid)


def cast_for_free(state: GameState, pid: int, oid: int) -> None:
    """Put a suspended card on the stack having paid nothing for it.

    Still a cast: it uses the stack, it can be countered, and its targets are
    chosen now.  A card with no legal target simply stays in exile with no time
    counters, which is what the rules say happens to it.
    """
    from . import stack, triggers
    from .targeting import enumerate_target_tuples

    obj = state.objects.get(oid)
    if obj is None:
        return
    card = state.card_of(obj)

    options = enumerate_target_tuples(state, pid, card.targets, oid, limit=1)
    if not options:
        return
    obj.suspended_by = None
    obj.hasted_by_suspend = card.is_creature

    item = stack.push_spell(state, oid, pid, options[0])
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
