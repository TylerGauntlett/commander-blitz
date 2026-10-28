"""Sagas (rule 714) -- the lore counter, the tick, and the sacrifice.

A Saga is an enchantment whose text is a numbered list, and **none of the three
things that make the list advance are printed on the card**. The reminder line
says them out loud precisely because they are not abilities:

    (As this Saga enters and after your draw step, add a lore counter.
     Sacrifice after III.)

So this module is where they live, in the same sense that the monarch's end-step
draw lives in :mod:`turn` and the legend rule lives in :mod:`sba` -- three
behaviours the *game* supplies, hung off one counter kind and one number on the
card (``CardDef.final_chapter``).

There is no state on :class:`~commanderblitz.engine.state.GameState` for any of it, and
that is the difference from the monarch: the crown belongs to the table, while a
Saga's progress belongs to the permanent. Lore counters are ordinary counters on
an ordinary ``GameObject``, so `counters_on`, `proliferate`, `move_counters`,
`remove_counters` and the client's counter badge all read a Saga for free -- and
each of them can move a Saga's chapter along, which is why the trigger is written
as a comparison rather than as a hook on one caller.

The four pieces, and where each one had to go:

``LORE`` as it enters (714.2b)
    A ``self_enters_with_counters`` replacement compiled by the loader, exactly
    as a planeswalker's starting loyalty is. It has to be part of *entering*
    rather than a `self_enters` trigger: 614.1c-style, the permanent is never
    seen without it, so every other enters trigger on the board looks at a Saga
    that already has its first lore counter, and chapter I is on the stack
    beside them rather than a whole round of priority later. A Saga with read
    ahead (702.155) enters with the number its controller chose instead, asked
    by `zones.offer_read_ahead` on the same arrival paths riot is.

The chapter trigger (714.2c)
    :func:`chapters_reached`, called from the two places lore counters can
    appear: `primitives.add_counters` and the entering replacement. It compares
    the count *before* against the count *after*, because the rule is about the
    number **becoming** N and not about a counter being placed.

The tick (714.2d)
    :func:`turn_based_lore`, a turn-based action at the start of the precombat
    main phase, called from `turn.begin_step`. Not a `draw_step` trigger: a
    turn-based action happens automatically as the phase begins, with nobody
    holding priority in between and nothing to respond to, and it is the active
    player's Sagas only.

The sacrifice (704.5s)
    :func:`finished`, asked by the state-based-action pass. Not an effect
    appended to the last chapter, which would sacrifice the Saga in the middle
    of its own final chapter resolving.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .characteristics import chars
from .events import EventType
from .triggers import fire

if TYPE_CHECKING:  # pragma: no cover
    from .carddef import CardDef
    from .objects import GameObject
    from .state import GameState

#: The counter kind a Saga counts its chapters in (714.2a).
LORE = "lore"

#: The subtype that makes an enchantment a Saga.
SAGA = "Saga"


def is_saga(state: GameState, oid: int) -> bool:
    """Whether this permanent is a Saga with chapters to advance.

    Both halves are required and neither implies the other. The **subtype** is
    read off `chars` rather than off the printed card, because it is a
    characteristic and `add_subtype` can hand it to something else; the
    **chapters** are read off the card, because an ability is not a
    characteristic and 704.5s asks for "one or more chapter abilities" in so many
    words.

    So an animated Saga is still a Saga, and a permanent given the subtype by an
    effect is not one: it has no chapter ability, so there is nothing for a lore
    counter to advance and no final chapter to be sacrificed for reaching.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    if state.card_of(obj).final_chapter is None:
        return False
    return SAGA in chars(state, oid).subtypes


def chapter_numbers(card: CardDef) -> frozenset[int]:
    """Every chapter number this card prints an ability for."""
    return frozenset(
        ability.chapter for ability in card.abilities if ability.chapter is not None
    )


def chapters_reached(state: GameState, oid: int, before: int, after: int) -> None:
    """Fire the chapter abilities whose number the lore count has just reached.

    Rule 714.2c: a chapter ability triggers "when one or more lore counters are
    put on the Saga such that the number of lore counters on it becomes greater
    than or equal to the ability's chapter number, and the number of lore
    counters on it was less than the ability's chapter number before".

    That sentence is a **before/after comparison**, and writing it as anything
    else ships a different card in a way nothing would report:

    - fired on the *placement*, a `proliferate` on a Saga sitting at two
      counters would fire chapter III and also, on some readings, everything
      below it; and one placement of two counters would fire one chapter instead
      of two.
    - fired on the *total*, a Saga at three counters would fire chapter III again
      every time any counter of any kind arrived.

    One event per number crossed, in ascending order, and only for numbers the
    card actually prints an ability for. Ascending because 714.2c's abilities go
    on the stack in the order they triggered and a Saga jumped from I to III must
    resolve II first; only-for-printed-numbers because CHAPTER_REACHED exists to
    wake abilities, and a number with none is a gap in the card rather than a
    thing that happened.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or after <= before:
        return
    card = state.card_of(obj)
    if card.final_chapter is None or SAGA not in chars(state, oid).subtypes:
        return
    numbers = chapter_numbers(card)
    for chapter in range(before + 1, after + 1):
        if chapter not in numbers:
            continue
        fire(
            state,
            EventType.CHAPTER_REACHED,
            player=obj.controller,
            source=oid,
            oid=oid,
            card=card.id,
            chapter=chapter,
        )


def entered(state: GameState, obj: GameObject, skipped: int = 0) -> None:
    """Chapter I, off the lore counter the Saga entered with (714.2b).

    Called by `zones._enter_battlefield` right after the ETB event, because the
    counter was put on by a *replacement* -- `obj.add_counter` is written to
    directly, so there is no `add_counters` call for :func:`chapters_reached`
    to be reached through. The arrival's COUNTER_PLACED for that counter
    (122.6, `zones._fire_entered_with_counters`) reaches no chapter comparison,
    so this is the only route to chapter I and it triggers once. Counted from
    zero, which is what "enters with" means.

    After the ETB event rather than before it, so a Saga's own chapter I queues
    behind whatever else that permanent entering woke up -- the order the rules
    give, since both are triggers put on the stack from the same event window.

    ``skipped`` is read ahead's (702.155): "chapter abilities whose chapter
    number is less than the chosen number don't trigger." So the count is from
    the chosen chapter less one, not from zero, and the chosen chapter -- and
    any above it that a Doubling Season's extra counters reach -- triggers.
    """
    if state.card_of(obj).final_chapter is None:
        return
    chapters_reached(state, obj.oid, skipped, obj.counter(LORE))


def turn_based_lore(state: GameState) -> None:
    """714.2d: as the precombat main phase begins, the active player puts a lore
    counter on each Saga they control.

    A **turn-based action**, which is why it is here and not a `draw_step`
    trigger on the card. Three differences, and all three are visible:

    - it happens automatically as the phase begins, with no priority in between
      and nothing on the stack to respond to. A trigger could be countered, and
      would let an opponent act between the counter and the chapter.
    - it is the active player's Sagas. A `draw_step` trigger fires on every
      player's draw step unless hand-gated with `is_your_turn`, so every Saga in
      the pool would have to remember the gate.
    - it is the **precombat main phase**, which is where the rule has put it
      since the 2018 wording ("after your draw step") was replaced. A Saga's
      chapter therefore resolves in the phase its controller can act in, rather
      than one step earlier while a draw trigger is still on the stack.

    Through `primitives.add_counters` rather than `obj.add_counter`, so the
    placement emits COUNTER_PLACED like every other -- a card reading "whenever a
    counter is put on a permanent you control" sees a Saga ticking -- and so the
    chapter comparison happens in the one funnel instead of twice.
    """
    # Local: `primitives` imports `sagas`.
    from .primitives import add_counters

    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None or obj.controller != state.active_player:
            continue
        if not is_saga(state, oid):
            continue
        add_counters(state, oid, LORE, 1)


def chapter_on_stack(state: GameState, oid: int) -> bool:
    """Whether a chapter ability of this Saga "has triggered but not yet left the
    stack" (704.5s).

    Both halves of "not yet left" are checked: an ability already on the stack,
    and one that fired and is still in `pending_triggers` waiting to be put
    there. The queue matters more than the stack does, because it is where the
    trigger spends the window the state-based actions actually run in -- the SBA
    pass happens *before* a player would receive priority, which is the same
    moment `drain_to_stack` is about to use. Checking only `state.stack` would
    sacrifice every Saga at the instant its final chapter triggered and throw the
    chapter away with it.
    """
    # Local: `stack` reaches `sagas` through `primitives`.
    from .stack import ability_of

    waiting = (*state.stack, *state.pending_triggers)
    return any(
        item.source_oid == oid
        and (ability := ability_of(state, item)) is not None
        and ability.is_chapter
        for item in waiting
    )


def finished(state: GameState, oid: int) -> bool:
    """Whether 704.5s says this Saga's controller sacrifices it.

    "If the number of lore counters on a Saga permanent with one or more chapter
    abilities is greater than or equal to its final chapter number and it isn't
    the source of a chapter ability that has triggered but hasn't left the stack,
    that Saga's controller sacrifices it."

    Greater than *or equal*, not equal: a proliferated Saga can overshoot its
    last chapter, and an equality test would leave it on the battlefield for
    ever.
    """
    obj = state.objects.get(oid)
    if obj is None or not is_saga(state, oid):
        return False
    final = state.card_of(obj).final_chapter
    assert final is not None  # `is_saga` just said so
    if obj.counter(LORE) < final:
        return False
    return not chapter_on_stack(state, oid)
