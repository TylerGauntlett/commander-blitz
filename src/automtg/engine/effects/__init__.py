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
#: it (see `loader._validate_effect`).  Listed here, beside `OPS`, so the guard
#: and the implementations cannot drift apart.
RECORDING_OPS = frozenset(
    {
        "copy_permanent",
        "create_token",
        "exile",
        "join_forces",
        "reveal",
        "sacrifice",
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
