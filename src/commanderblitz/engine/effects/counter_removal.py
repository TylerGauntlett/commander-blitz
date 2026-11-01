"""Taking counters of any kind off permanents, one counter at a time.

The one question behind every sentence that removes or moves counters without
naming their kind: the `remove_counters_from_among` cost (Tekuthal), the
`remove_counters_from_among` op (Eventide's Shadow), `remove_counters` with
`any_kind` (Glissa Sunslayer) and `move_counters` with `any_kind` (Nesting
Grounds). 122.1 lets a permanent carry any number of kinds, and "remove three
counters" lets the chooser take them in any mix -- two -1/-1 and a loyalty, or
all three off one permanent -- so the counters are asked for one at a time:
which permanent, then which kind when it carries more than one. That single
question can say every split without a distribution decision the engine does
not have.

A leaf the costs module and the op modules both import: a cost that asked the
question one way and an effect that asked it another would drift on the
default answer, which is the one the verifier and a timed-out player get.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Sequence
from typing import Any

from ..primitives import remove_counters
from .context import EffectContext, ask_mode, ask_objects

#: Counter kinds that hurt the permanent they are on, offered first when the
#: chooser is asked which kind to remove -- so the default answer is the kind
#: the permanent would most like gone.
HARMFUL_COUNTERS = ("-1/-1", "stun")


def counters_on(ctx: EffectContext, oid: int) -> int:
    """How many counters of every kind ``oid`` carries -- 0 off the battlefield.

    A target that left before the effect got to it (or a planeswalker the last
    removal killed) has nothing left to give, and asking about it would remove
    counters from a card in a graveyard.
    """
    obj = ctx.state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return 0
    return sum(n for n in obj.counters.values() if n > 0)


def kinds_held(ctx: EffectContext, oid: int) -> dict[str, int]:
    """The kinds ``oid`` carries, harmful first, then the most numerous."""
    obj = ctx.state.objects.get(oid)
    if obj is None:
        return {}
    held = {k: n for k, n in obj.counters.items() if n > 0}
    order = sorted(held, key=lambda k: (k not in HARMFUL_COUNTERS, -held[k], k))
    return {k: held[k] for k in order}


def ask_counter_kind(
    ctx: EffectContext, oid: int, chooser: int, verb: str = "Remove"
) -> Generator[Any, Any, str | None]:
    """Which kind of counter on ``oid`` -- asked only when it carries two or more."""
    held = kinds_held(ctx, oid)
    kinds = list(held)
    if not kinds:
        return None
    if len(kinds) == 1:
        return kinds[0]
    [index] = yield from ask_mode(
        ctx,
        f"{verb} which counter from {ctx.name_of(oid)}?",
        [f"{k} counter ({held[k]})" for k in kinds],
        chooser,
    )
    return kinds[index]


def remove_counters_one_at_a_time(
    ctx: EffectContext,
    pool: Callable[[], Sequence[int]],
    *,
    most: int | None,
    least: int,
    chooser: int,
    purpose: str,
) -> Generator[Any, Any, int]:
    """Remove between ``least`` and ``most`` counters off ``pool()``; the number removed.

    ``pool`` is re-read before every counter, because the last removal may have
    emptied a permanent (or killed it: a planeswalker at no loyalty). ``most``
    of ``None`` is "any number". Up to ``least`` the chooser must pick a
    permanent -- a forced pick is not asked -- and past it the question may be
    declined, which ends the removal. Stops early when nothing is left to
    remove, which is 609.3's "as much as possible" for an effect; a cost checks
    it can be paid in full before it starts.
    """
    removed = 0
    while most is None or removed < most:
        candidates = [oid for oid in pool() if counters_on(ctx, oid) > 0]
        if not candidates:
            break
        prompt = (
            f"Remove a counter ({most - removed} more)"
            if most is not None
            else "Remove a counter (or stop)"
        )
        picked = yield from ask_objects(
            ctx, prompt, candidates, 1 if removed < least else 0, 1, chooser, purpose
        )
        if not picked:
            break
        kind = yield from ask_counter_kind(ctx, picked[0], chooser)
        if kind is None:
            break
        removed += remove_counters(ctx.state, picked[0], kind, 1)
    return removed
