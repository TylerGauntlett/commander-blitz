"""The effect interpreter.

Card JSON is *data*; this package is the interpreter for it.  There is no
``eval`` and no embedded Python in card files -- every effect is a dict with an
``op`` key naming a function in :data:`OPS`, and the loader validates every op
name at load time so a typo fails the test suite instead of a game.

Effects are **generators**.  An op that needs a choice from a player yields a
:class:`~commanderblitz.engine.actions.PendingDecision` and receives the answer back.
That is what lets resolution pause mid-effect for "sacrifice a creature" without
the engine needing continuations or state cloning.
"""

from __future__ import annotations

import inspect
from collections.abc import Generator, Iterable, Mapping
from typing import Any

from ..errors import DslError
from . import registry
from .registry import RECORDING_OPS, register


def known_ops() -> frozenset[str]:
    load_ops()
    return frozenset(registry.OPS)


def execute(ctx, effects: Iterable[Mapping[str, Any]]) -> Generator[Any, Any]:
    """Run a list of effect dicts in order.

    Non-generator ops are called and their result discarded; generator ops are
    delegated to with ``yield from`` so their decision requests reach the driver.
    """
    for spec in effects:
        yield from execute_one(ctx, spec)


def execute_one(ctx, spec: Mapping[str, Any]) -> Generator[Any, Any]:
    load_ops()
    op_name = spec.get("op")
    fn = registry.OPS.get(op_name)
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


def __getattr__(name: str) -> Any:
    """``OPS``, served after `load_ops` has filled it."""
    if name == "OPS":
        load_ops()
        return registry.OPS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_ops_loaded = False


def load_ops() -> None:
    """Import every op module, which populates ``OPS``.

    Run on first use -- `known_ops`, `execute_one`, or reading ``OPS`` off this
    package -- rather than at package import. The op modules import the engine
    core (`primitives`, `zones`, `costs`, ...), and the core imports
    `effects.values`, `selectors` and `conditions`, which runs this package
    first: importing the ops at the top here made the core unimportable on its
    own.
    """
    global _ops_loaded
    if _ops_loaded:
        return
    # Lazy by design: this is the registry's import of its own plug-ins, which
    # import the engine core that imports this package.
    from . import (
        ops_cards,  # noqa: F401
        ops_characteristics,  # noqa: F401
        ops_combat_flags,  # noqa: F401
        ops_control,  # noqa: F401
        ops_counters,  # noqa: F401
        ops_life,  # noqa: F401
        ops_mana,  # noqa: F401
        ops_player,  # noqa: F401
        ops_removal,  # noqa: F401
        ops_stack,  # noqa: F401
    )

    _ops_loaded = True


__all__ = [
    "OPS",
    "RECORDING_OPS",
    "execute",
    "execute_one",
    "known_ops",
    "load_ops",
    "register",
]
