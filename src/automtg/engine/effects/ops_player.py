"""Effect ops that write a **player-level designation**.

Its own module rather than a corner of one of the others, because none of them
describes this. `ops_removal`, `ops_counters`, `ops_characteristics` and `ops_combat_flags` act on permanents, `ops_life` on life totals and
damage, `ops_mana` on the pool, `ops_control` on control flow -- and a
designation is none of those: nothing on the board changes, no number moves, and
the thing written outlives every permanent that granted it.

`set_flag` is the op every gap record named as the nearest existing thing, and
the comparison is exact enough to be worth keeping in mind: this is `set_flag`
for a *player*. The difference is that a flag is an adjective on one permanent,
cleared by `reset_permanent_state` the moment that permanent changes zones, while
a designation belongs to the table and is exclusive across it.

`win_game` joined it later and widens the module by one word: these are the ops
whose subject is a **seat** rather than anything on the board. It is the same
argument -- nothing on the battlefield changes, no number moves, and what is
written outlives every permanent involved -- carried as far as it goes, to the
one thing about a player that outlives the game itself.
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
    """ "You become the monarch", or "target player becomes the monarch" (721.2).

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


@register("win_game")
def op_win_game(ctx: EffectContext, spec: Mapping[str, Any]) -> None:
    """ "You win the game." Halo Fountain and Luck Bobblehead.

    The only op that ends the game on purpose, and the first thing to reach a
    game *result* at all. Everything else that has ever produced a winner did it
    by accident of arithmetic: `damage` and `lose_life` take a seat to zero,
    `add_poison` takes it to ten, and `sba` notices. Neither card here is about a
    life total -- Halo Fountain untaps fifteen creatures at 40 life against 40
    life, and Luck Bobblehead counts sixes -- so there was no approximation to
    make, only a missing sentence.

    Takes the usual **player spec**, defaulting to ``"you"``, which is what both
    cards print. The spec is here rather than hardcoded for the reason
    `become_monarch`'s is: a player is a first-class thing to name in this DSL,
    and every op that names one spells it the same way and validates through the
    same `loader.effects._validate_player_spec`.

    A spec naming more than one seat is not refused, and does not need to be:
    :func:`~automtg.engine.sba.declare_win` is a no-op once the game is over, so
    the first player named wins and the rest are ignored. No printed card says
    "each player wins the game" -- the one shape that would matter is a *team*
    win, and teams are not modelled.

    The work is all in `sba.declare_win`, which is where the argument about
    *where a result may be written* lives. Read it before changing this.

    Two things this deliberately does not do:

    - **There is no `lose_game` op.** Losing is the mechanism here rather than a
      second op -- "you win the game" *is* every opponent losing -- so the engine
      half already exists and the op is two lines whenever a card wants it. Door
      to Nothingness and Demonic Pact are the family, and neither is in the pool;
      registering the name now would be a vocabulary item with no card behind it,
      which is the thing this repo's load-time checks exist to keep out.
    - **It does not check "can't win the game".** Platinum Angel and Abyssal
      Persecutor are a continuous prohibition over this whole subsystem, not a
      clause of this op, and nothing in the pool has one.

    Anything sequenced *after* this in the same effect list still runs -- the
    interpreter has no game-over guard mid-resolution -- but the game is already
    over, so nothing it does is offered to anybody. Both cards put the win last,
    which is where every printed "you win the game" puts it.
    """
    # Local, for `sba._monarch_left`'s reason: `sba` reaches the effect layer
    # through `zones`, and this module is imported from `effects/__init__`, so a
    # module-level import binds a half-initialised `sba` when the engine happens
    # to be imported from that end first.
    from ..sba import declare_win

    for pid in select_players(ctx, spec.get("player", "you")):
        declare_win(ctx.state, pid)
