"""Effect ops that write a **player-level designation**.

Its own module rather than a corner of one of the others, because none of them
describes this. `ops_board` acts on permanents, `ops_life` on life totals and
damage, `ops_mana` on the pool, `ops_control` on control flow -- and a
designation is none of those: nothing on the board changes, no number moves, and
the thing written outlives every permanent that granted it.

`set_flag` is the op every gap record named as the nearest existing thing, and
the comparison is exact enough to be worth keeping in mind: this is `set_flag`
for a *player*. The difference is that a flag is an adjective on one permanent,
cleared by `reset_permanent_state` the moment that permanent changes zones, while
a designation belongs to the table and is exclusive across it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..primitives import become_monarch
from . import register
from .context import EffectContext
from .selectors import select_players


@register("become_monarch")
def op_become_monarch(ctx: EffectContext, spec: Mapping[str, Any]):
    """"You become the monarch", or "target player becomes the monarch" (721.2).

    Takes a **player spec**, defaulting to ``"you"`` -- which is what seven of the
    eight cards that asked for this op print. The eighth is Éomer, King of Rohan's
    "target player becomes the monarch", and it is the reason the selector is here
    from the start rather than added later: written with an implicit controller the
    op reads perfectly and gives the crown to the wrong player, which on a card
    whose whole drawback is handing an opponent a card every turn is most of the
    card.

    Every player named is offered it in turn, and the last one keeps it (721.4).
    That is not a shape any printed card has -- there is no "each player becomes
    the monarch" -- but it is what `select_players` returning a list means, and
    silently taking the first would be a different answer with nothing to say so.

    A player who is already the monarch is left alone rather than re-designated,
    so nothing fires. See :func:`~automtg.engine.primitives.become_monarch`.
    """
    for pid in select_players(ctx, spec.get("player", "you")):
        become_monarch(ctx.state, pid, source=ctx.source_oid)
    yield from ()
