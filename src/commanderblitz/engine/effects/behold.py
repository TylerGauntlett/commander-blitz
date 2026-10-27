"""Behold (Tarkir: Dragonstorm, Lorwyn Eclipsed): the pool and the reveal.

"To behold a Dragon, choose a Dragon you control or reveal a Dragon card from
your hand." One action with two sources, used in two places: the ``behold`` op
("When Sarkhan enters, you may behold a Dragon. If you do, …") and the
``behold`` cost ("As an additional cost to cast this spell, behold a Dragon or
pay {1}"). Both build the pool and announce the choice here, so the op and the
cost cannot disagree about what may be beheld.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..errors import DslError
from .context import EffectContext
from .selectors import matches, resolve_pool, validate_selector

if TYPE_CHECKING:  # pragma: no cover
    from ..state import GameState

#: Keys a behold selector may not carry, because the action fixes them: the
#: battlefield half is always "you control", and the hand half is always the
#: beholder's own hand. ``count`` is how many are beheld, not a filter.
IMPLIED_KEYS = frozenset({"zone", "controller", "count"})


def behold_pool(
    state: GameState,
    pid: int,
    selector: Mapping[str, Any],
    source_oid: int | None,
    *,
    exclude_source: bool = False,
) -> list[int]:
    """Every object ``pid`` could behold: matching permanents they control, then
    matching cards in their own hand.

    Only the beholder's own hand is walked, rather than a ``zone: "hand"``
    selector resolved over every player, for `costs._hand_exile_pool`'s reason:
    the hand is hidden, and an opponent's card must never become a choice.

    ``exclude_source`` is the cost's rule (601.2a): a spell is on the stack
    before its costs are paid, so a Kinsbaile Aspirant still in hand while
    legality prices the cast cannot behold itself. The op leaves it off,
    because a permanent beholding "a Dragon you control" may choose itself.
    """
    spec = {k: v for k, v in selector.items() if k not in IMPLIED_KEYS}
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    permanents = resolve_pool(ctx, {**spec, "zone": "battlefield", "controller": "you"})
    hand_spec = {**spec, "zone": "hand"}
    in_hand = [oid for oid in state.players[pid].hand if matches(ctx, oid, hand_spec)]
    pool = permanents + [oid for oid in in_hand if oid not in permanents]
    if exclude_source and source_oid is not None:
        pool = [oid for oid in pool if oid != source_oid]
    return pool


def behold_count(selector: Mapping[str, Any]) -> int:
    """How many objects the action beholds -- "behold **three** Elementals"."""
    return max(1, int(selector.get("count", 1) or 1))


def announce_beheld(
    state: GameState, pid: int, oids: Sequence[int], source_oid: int | None
) -> None:
    """Reveal the beheld cards that came from hand; a chosen permanent is
    already public and shows nothing new.

    A real reveal, so it is the same ``reveal`` event the ``reveal``
    op emits: every seat learns the card, which is the information the action
    costs the beholder.
    """
    hand = state.players[pid].hand
    shown = [state.objects[o].def_id for o in oids if o in hand and o in state.objects]
    if shown:
        state.emit("reveal", player=pid, source=source_oid, cards=shown)


def validate_behold_selector(selector: Any, where: str) -> None:
    """Load-time refusals for a behold selector, shared by the op and the cost.

    It must say *what* is beheld -- a behold of anything is no printed card --
    and may not carry ``zone`` or ``controller``, which the action fixes (a
    written one would read as a knob and be overwritten in silence). ``count``
    is a positive integer.
    """
    if not isinstance(selector, Mapping) or not selector:
        raise DslError(
            f"{where}: behold needs a selector naming what is beheld, "
            f'e.g. {{"subtypes": ["Dragon"]}}'
        )
    for key in ("zone", "controller"):
        if key in selector:
            raise DslError(
                f"{where}: '{key}' is implied -- behold is always a permanent you "
                f"control or a card in your own hand"
            )
    count = selector.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise DslError(f"{where}.count: a positive integer, got {count!r}")
    validate_selector({k: v for k, v in selector.items() if k != "count"}, where)
