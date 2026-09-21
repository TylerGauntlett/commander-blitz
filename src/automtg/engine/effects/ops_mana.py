"""Effect ops for mana and land drops."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..events import EventType
from ..mana import parse_mana_production
from . import register
from .context import EffectContext
from .selectors import resolve_pool, select_players
from .values import evaluate_value


def mana_string(ctx: EffectContext, spec: Mapping[str, Any]) -> str:
    """The symbols this ``add_mana`` produces, as a production string.

    Almost always the literal the card printed. The one exception is
    ``{"mana": {"chosen_color_of": "self"}}`` -- Heraldic Banner's "add one mana
    of the chosen color" -- where the symbol is a question about the source
    permanent and cannot be known until it has been asked.

    A source that has chosen no colour yet produces **nothing**, the same
    match-nothing default the chosen colour has everywhere else. It only looks:
    no decision is asked here, which is what keeps an ``add_mana`` legal inside
    a mana ability (605.1a).

    Note that a real *mana ability* never reaches this function at all --
    `costs.activate_mana_ability` adds the mana from `costs.mana_options_of`
    rather than by running the effect. This is the path for the other
    ``add_mana``s: a triggered ability, or a spell.
    """
    mana = spec.get("mana", "")
    if not isinstance(mana, Mapping):
        return str(mana)
    from ..characteristics import resolve_chosen_color_list

    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    return "".join(f"{{{c}}}" for c in resolve_chosen_color_list([mana], source))



def _persists_through(ctx: EffectContext, spec: Mapping[str, Any]) -> int:
    """The turn this mana survives to the end of, or ``-1`` for ordinary mana.

    "Until end of turn, you don't lose this mana as steps and phases end"
    (Tanuki Transplanter). The turn is read here, as the mana is added, because
    that is the only moment the effect exists: afterwards there is nothing but
    mana in a pool, and a pool cannot say which turn made a promise about it.
    """
    return ctx.state.turn if spec.get("persists_until_end_of_turn") else -1

@register("add_mana")
def op_add_mana(ctx: EffectContext, spec: Mapping[str, Any]):
    # Imported here rather than at module scope: `characteristics` is reached
    # through `primitives` -> `zones` -> `effects`, so a top-level import turns
    # that existing chain into a cycle.
    from ..characteristics import mana_source_traits

    symbols = mana_string(ctx, spec)
    if not symbols:
        return
    produced = parse_mana_production(symbols)
    for pid in select_players(ctx, spec.get("player", "you")):
        ctx.state.players[pid].mana_pool.add_tuple(
            produced,
            source=ctx.source_oid,
            persists_through_turn=_persists_through(ctx, spec),
            # What the source was, for "if mana from a Treasure was spent"
            # -- see `characteristics.mana_source_traits`. Taken beside the oid
            # on every path that adds mana, so provenance does not depend on
            # which of the two ways a permanent made it.
            source_traits=mana_source_traits(ctx.state, ctx.source_oid),
        )
        ctx.state.emit(EventType.MANA_ADDED, player=pid, source=ctx.source_oid, mana=symbols)


@register("add_mana_per")
def op_add_mana_per(ctx: EffectContext, spec: Mapping[str, Any]):
    """Add one unit of mana for each object matching a selector.

    e.g. "Add {G} for each Forest you control".
    """
    from ..characteristics import mana_source_traits

    unit = parse_mana_production(str(spec.get("mana", "")))
    count = len(resolve_pool(ctx, spec.get("per")))
    if count <= 0:
        return
    scaled = tuple(v * count for v in unit)
    for pid in select_players(ctx, spec.get("player", "you")):
        ctx.state.players[pid].mana_pool.add_tuple(
            scaled,
            source=ctx.source_oid,
            persists_through_turn=_persists_through(ctx, spec),
            source_traits=mana_source_traits(ctx.state, ctx.source_oid),
        )
        ctx.state.emit(
            EventType.MANA_ADDED,
            player=pid,
            source=ctx.source_oid,
            mana=spec.get("mana", ""),
            times=count,
        )


@register("extra_land_drop")
def op_extra_land_drop(ctx: EffectContext, spec: Mapping[str, Any]):
    """Grant additional land drops for the rest of this turn."""
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        ctx.state.players[pid].extra_land_drops += amount
