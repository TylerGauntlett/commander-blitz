"""Helpers shared by the permanent-facing op modules: who is attacking whom,
which blocks to offer, and the players an op's spec names."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Step
from ..errors import DslError
from .context import EffectContext
from .selectors import (
    select_players,
)


def _attacking_player(ctx: EffectContext, spec: Mapping[str, Any], fallback) -> int | None:
    """Whom a permanent arriving attacking should be attacking.

    ``attacking: true`` is the original spelling and still means "wherever the
    source is already pointed" -- ``fallback`` is `_attack_target` or
    `_attack_defender`, whichever this op has always used. Every shipped card
    uses that form and none of them change.

    Anything else is a **player spec**, which is the case the boolean cannot
    say. Ainok Strike Leader's "for each opponent, create a token attacking
    **that player**" names the seat a `for_each_player` loop is on
    (``{"binding": "each_player"}``); Combat Calligrapher's "attacking that
    opponent" names the trigger's ``defender`` binding, on a source that is
    never itself attacking. Under the boolean both would resolve to the one
    player the *source* attacks -- the same seat for all three tokens at a pod,
    and nobody at all when the source is not an attacker, which arrives tapped
    and attacking no-one while looking implemented.

    A creature attacks exactly one player, so a spec that names several is an
    authoring error rather than something to pick from. The plural *names* are
    refused at load time (`loader.effects._validate_effect`); this catches the one shape
    load time cannot see, a multi-ref target. Naming nobody -- an unbound
    binding, a player who has left -- is the boolean's own "nobody to join": the
    permanent simply arrives.
    """
    who = spec.get("attacking")
    if who is None or who is False:
        return None
    if who is True:
        return fallback(ctx)
    named = select_players(ctx, who)
    if len(named) > 1:
        raise DslError(
            f"attacking: {who!r} names {len(named)} players; a creature attacks exactly one"
        )
    if not named or not ctx.state.is_alive(named[0]):
        return None
    return named[0]


def _offer_blocks_to(ctx: EffectContext, defender: int) -> None:
    """Make sure a newly attacked player still gets to declare blockers.

    `combat.finish_attackers` fills `pending_blockers` from the declaration, so
    it lists only the players who were attacked *then*. A token created
    attacking a player nobody declared against -- Ainok Strike Leader's third
    opponent, who was not part of the swing -- would otherwise be attacked by a
    creature it is never asked to block (509.1).

    Only **before** the declare blockers step, which is the window every card
    that says this resolves in: attack triggers go on the stack during the
    declare attackers step. Once the step has started the queue is being walked
    -- `game.apply` pops its head as each declaration is answered -- so writing
    into it would ask the wrong seat to block; and a permanent that arrives
    attacking after blocks are declared is simply unblocked, which is 509.1 read
    the other way and what stops this from becoming a second declaration.
    """
    combat = ctx.state.combat
    if combat is None or defender in combat.pending_blockers:
        return
    if ctx.state.step >= Step.DECLARE_BLOCKERS:
        return
    order = ctx.state.turn_order()
    if defender not in order:
        return
    seat = order.index(defender)
    at = len(combat.pending_blockers)
    for i, pid in enumerate(combat.pending_blockers):
        if pid in order and order.index(pid) > seat:
            at = i
            break
    combat.pending_blockers.insert(at, defender)


def _attack_defender(ctx: EffectContext) -> int | None:
    """Whom a permanent put onto the battlefield attacking should be attacking.

    Ninjutsu returns an attacker to hand and puts the ninja in its place, so the
    defender is whoever *that* attacker was hitting. With no combat, or nothing
    left attacking, there is nobody to join and the permanent simply arrives.
    """
    combat = ctx.state.combat
    if combat is None or not combat.attackers:
        return None
    if ctx.source_oid is not None and ctx.source_oid in combat.attackers:
        return combat.attackers[ctx.source_oid]
    return next(iter(combat.attackers.values()))


def _attack_target(ctx: EffectContext) -> int | None:
    """Whom a token created attacking should be attacking.

    The same player the source is already attacking -- which is what "create a
    tapped and attacking token" means on a card whose trigger is "whenever this
    creature attacks".  Outside combat, or from a source that is not itself
    attacking, there is nobody to join, and the token simply arrives tapped.
    """
    combat = ctx.state.combat
    if combat is None or ctx.source_oid is None:
        return None
    return combat.attackers.get(ctx.source_oid)


def _players(ctx: EffectContext, spec: Any) -> list[int]:
    from .selectors import select_players

    return select_players(ctx, spec)
