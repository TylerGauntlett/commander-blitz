"""The three replacements that stop to ask -- dredge, madness and miracle.

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

from .carddef import Cost
from .enums import Zone
from .events import EventType
from .primitives import discard_cards, draw_cards, mill_cards

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def draw(state: GameState, pid: int, count: int) -> Generator[Any, list[int], list[int]]:
    """Draw ``count`` cards, one at a time, offering dredge and miracle.

    One at a time is forced rather than tidy: dredge replaces **a** draw, so a
    player drawing three may dredge the first and draw the other two, and
    miracle asks about the *first card drawn this turn*, which stops being true
    after the first one.
    """
    drawn: list[int] = []
    for _ in range(max(0, count)):
        replaced = yield from _dredge(state, pid)
        if replaced:
            continue
        # Read before the draw: `draw_cards` bumps the tally, and miracle's
        # whole content is that this was the first.
        was_first = state.cards_drawn_this_turn.get(pid, 0) == 0
        got = draw_cards(state, pid, 1)
        drawn.extend(got)
        if got and was_first:
            yield from _miracle(state, pid, got[0])
    return drawn


def discard(
    state: GameState, pid: int, oids: Sequence[int]
) -> Generator[Any, list[int], list[int]]:
    """Discard these cards, sending any with madness to exile and offering the cast."""
    ordinary: list[int] = []
    for oid in oids:
        obj = state.objects.get(oid)
        if obj is None or obj.zone is not Zone.HAND:
            continue
        card = state.card_of(obj)
        if card.madness is None:
            ordinary.append(oid)
            continue
        yield from _madness(state, pid, oid)
    return discard_cards(state, pid, ordinary)


# ----------------------------------------------------------------------
# one replacement each
# ----------------------------------------------------------------------


def _dredge(state: GameState, pid: int) -> Generator[Any, list[int], bool]:
    """Offer to replace this draw by dredging. Returns whether it was replaced."""
    from .effects.context import EffectContext, ask_objects

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
    from .zones import move_object

    move_object(state, oid, Zone.HAND, to_player=pid, cause="dredge")
    state.emit("dredge", player=pid, source=oid, card=card.id, milled=card.dredge)
    return True


def _miracle(state: GameState, pid: int, oid: int) -> Generator[Any, list[int], None]:
    """"…when you draw it, if it's the first card you drew this turn."

    The card is revealed either way: 702.94a makes the reveal the trigger's
    price, and a player who reveals and then declines has still shown the table
    what they drew.
    """
    card = state.card_of(state.objects[oid])
    if card.miracle is None:
        return
    state.emit("reveal", player=pid, source=oid, cards=[card.id])
    yield from _offer_cast(state, pid, oid, card.miracle, "miracle")


def _madness(state: GameState, pid: int, oid: int) -> Generator[Any, list[int], None]:
    """"If you would discard this card, exile it instead."

    The exile happens whether or not the cast is taken, and that is the half a
    naive version drops: a madness card the player declines to cast is in
    **exile**, not in the graveyard, so nothing that reads graveyards ever sees
    it. Written the other way round, every madness card would be a free
    graveyard-filler.
    """
    from .zones import move_object

    obj = state.objects[oid]
    card = state.card_of(obj)
    move_object(state, oid, Zone.EXILE, to_player=obj.owner, cause="madness")
    state.emit(EventType.DISCARD, player=pid, source=oid, oid=oid, madness=True)
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
    from . import stack, triggers
    from .costs import can_pay, pay
    from .effects.context import EffectContext, ask_yes_no
    from .targeting import enumerate_target_tuples

    obj = state.objects.get(oid)
    if obj is None:
        return False
    card = state.card_of(obj)
    price = Cost(mana=cost)
    if not can_pay(state, pid, price, oid):
        return False
    options = enumerate_target_tuples(state, pid, card.targets, oid, limit=1)
    if not options:
        return False

    ctx = EffectContext(state=state, controller=pid, source_name=card.name)
    if not (yield from ask_yes_no(ctx, f"Cast {card.name} for its {label} cost?", pid)):
        return False
    paid = yield from pay(state, pid, price, oid)
    if not paid:  # pragma: no cover - `can_pay` said yes a moment ago
        return False

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
        **{label: 1},
    )
    return True
