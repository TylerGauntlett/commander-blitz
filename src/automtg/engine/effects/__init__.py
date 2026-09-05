"""The effect interpreter.

Card JSON is *data*; this package is the interpreter for it.  There is no
``eval`` and no embedded Python in card files -- every effect is a dict with an
``op`` key naming a function in :data:`OPS`, and the loader validates every op
name at load time so a typo fails the test suite instead of a game.

Effects are **generators**.  An op that needs a choice from a player yields a
:class:`~automtg.engine.actions.PendingDecision` and receives the answer back.
That is what lets resolution pause mid-effect for "sacrifice a creature" without
the engine needing continuations or state cloning.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Generator, Iterable, Mapping
from typing import Any

from ..errors import DslError

#: op name -> implementation.  Populated by the ``@register`` decorator.
OPS: dict[str, Callable[..., Any]] = {}

#: The ops that write ``ctx.bindings`` when given an ``as`` name -- "the cards
#: revealed this way", "the number of creature cards exiled this way", "exile
#: **the token**".  Every other op ignores an ``as`` entirely, and an `as` that
#: nothing writes reads back as 0 rather than as an error, so the loader refuses
#: it (see `loader.effects._validate_effect`).  Listed here, beside `OPS`, so the guard
#: and the implementations cannot drift apart.
RECORDING_OPS = frozenset(
    {
        #: The one recorder whose binding is a **player**: `choose_player`
        #: writes the seat that was chosen, read back by the `{"binding": …}`
        #: player spec rather than as a pool of objects. It is also the only
        #: one for which `as` is *required* -- the answer is unreachable
        #: otherwise. See `ops_control.op_choose_player`.
        "choose_player",
        #: The one recorder that does **nothing** to what it picked. Tragic
        #: Arrogance marks the survivors before the mass sacrifice; every other
        #: recorder acts on its pick, and marking-without-acting had no
        #: spelling. Accumulates, so four per-type choices share one name and a
        #: single `exclude_binding` spares them all.
        "choose_permanents",
        "copy_permanent",
        "create_token",
        #: "…then draw that many cards" -- Joshua; "draw that many cards **plus
        #: one**" -- Celes; "if a **creature card** was discarded this way" --
        #: Mog. The binding **accumulates** across the players a single discard
        #: touches, because Mog asks one card of each player in one resolution
        #: and then asks what was discarded at all, not what the last player
        #: pitched. See `ops_cards.op_discard`.
        "discard",
        "exile",
        "gain_control",
        "join_forces",
        #: The only recorder whose binding is a **set of seats**: `may` writes
        #: the players who said yes, read back with the `{"binding": …}` player
        #: spec. Snort's "each opponent who discarded their hand this way" is
        #: the acceptance and not anything the effects moved -- a player with an
        #: empty hand who takes the free draw-five has discarded their hand, of
        #: nothing, and is still burned.
        "may",
        #: The cards actually milled, across every player one op touched --
        #: Locke, Treasure Hunter's "if a land card was milled **this way**".
        #: An `exists` over a graveyard is a different card: it matches a land
        #: that was already lying there.
        "mill",
        #: The cards actually **cast**, which is neither the cards offered nor
        #: the cards exiled -- one with no legal target is never cast at all.
        #: Kefka turns on that distinction: "each player who owns a spell you
        #: cast this way loses life equal to its mana value".
        "play_exiled",
        "reveal",
        #: The one recorder whose binding is not a set of objects: `roll_dice`
        #: writes the faces it threw, read back by `{"rolled": …}` rather than
        #: by `{"count": {"binding": …}}`. See `ops_cards.op_roll_dice`.
        "roll_dice",
        "sacrifice",
        "search_library",
        "search_zones",
        "snapshot",
    }
)


def register(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register an effect op under ``name``."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if name in OPS:
            raise DslError(f"duplicate effect op {name!r}")
        OPS[name] = fn
        return fn

    return decorate


def known_ops() -> frozenset[str]:
    return frozenset(OPS)


def execute(ctx, effects: Iterable[Mapping[str, Any]]) -> Generator[Any, Any, None]:
    """Run a list of effect dicts in order.

    Non-generator ops are called and their result discarded; generator ops are
    delegated to with ``yield from`` so their decision requests reach the driver.
    """
    for spec in effects:
        yield from execute_one(ctx, spec)


def execute_one(ctx, spec: Mapping[str, Any]) -> Generator[Any, Any, None]:
    op_name = spec.get("op")
    fn = OPS.get(op_name)
    if fn is None:
        raise DslError(f"unknown effect op {op_name!r}")
    # One op is one "simultaneous" group: an `exile` over a whole graveyard
    # moves every card at once, and "whenever one or more cards leave your
    # graveyard" has to fire once for it rather than once per card. See
    # `triggers._queue` and `state.event_batch`.
    ctx.state.event_batch += 1
    result = fn(ctx, spec)
    if inspect.isgenerator(result):
        yield from result


# Importing the op modules populates OPS.  Kept at the bottom so ``register`` and
# ``OPS`` exist before the modules that use them are imported.
from . import (
    ops_board,  # noqa: F401
    ops_cards,  # noqa: F401
    ops_control,  # noqa: F401
    ops_life,  # noqa: F401
    ops_mana,  # noqa: F401
    ops_player,  # noqa: F401
    ops_stack,  # noqa: F401
)

__all__ = ["OPS", "RECORDING_OPS", "execute", "execute_one", "known_ops", "register"]
