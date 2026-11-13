"""The question a token creation can ask before it happens.

`primitives.create_token` is not a generator, so it cannot stop for a decision,
and the one token replacement that asks one -- Esix, Fractal Bloom's "you may
instead choose a creature other than Esix and create that many tokens that are
copies of that creature" -- is asked here, by every op that creates tokens, a
moment before the call. `zones.offer_enters_copy` makes the same move for the
same reason: 614 applies the replacement during the event and nobody receives
priority in between, so asking first leaves no window in which the answer is
missing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..player_statics import token_copy_replacements
from .context import EffectContext, ask_objects
from .selectors import resolve_pool


def ask_token_copies(ctx: EffectContext, pid: int, count: int):
    """Ask each ``copy_instead`` static reaching ``pid`` whether to copy a creature.

    Returns the ``copies`` `create_token` takes: one ``(def_id, overrides)``
    per static whose controller chose a creature, in battlefield order. The
    pool is the static's ``copy_instead`` selector resolved for its own source,
    so ``exclude_self`` is "other than Esix" and "a creature" is anybody's.
    An empty pool, or a creation of no tokens, asks nothing. The plain
    "choose" purpose, as `add_counters` asks: one permanent off the board,
    which the client's board picker already answers.

    The chosen creature's copiable values are read now, as `copy_permanent`
    reads them: its ``def_id`` and the ``copy_overrides`` its own creating
    effect set (707.2).
    """
    if count <= 0:
        return []
    copies: list[tuple[str, Mapping[str, Any] | None]] = []
    state = ctx.state
    for source, static in token_copy_replacements(state, pid):
        name = state.card_of(source).name
        own = EffectContext(
            state=state,
            controller=source.controller,
            source_oid=source.oid,
            source_name=name,
        )
        pool = resolve_pool(own, static["copy_instead"])
        picked = yield from ask_objects(
            own,
            f"{name}: create copies of a creature instead? (choose none to decline)",
            pool,
            0,
            1,
            source.controller,
        )
        for oid in picked:
            chosen = state.objects.get(oid)
            if chosen is None:
                continue
            copies.append(
                (chosen.def_id, dict(chosen.copy_overrides) if chosen.copy_overrides else None)
            )
    return copies
