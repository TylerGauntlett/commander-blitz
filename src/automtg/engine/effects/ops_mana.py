"""Effect ops for mana and land drops."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..events import EventType
from ..mana import (
    N_SYMBOLS,
    SYMBOL_INDEX,
    SYMBOLS,
    ManaRestriction,
    compile_restriction,
    parse_mana_production,
)
from . import register
from .context import EffectContext, ask_mode
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


def _restriction_of(spec: Mapping[str, Any]) -> ManaRestriction | None:
    """"Spend this mana only to cast spells" on the mana this effect makes.

    Compiled here, as the effect resolves, rather than at load time: an
    `add_mana` **effect** is still card JSON when it reaches the stack, and
    `Ability.mana_restriction` -- the load-time compilation -- exists only on a
    mana ability, which this is not. The loader validates the same spec through
    the same function (`loader.effects._validate_effect`), so a malformed
    restriction still fails at load rather than mid-game.
    """
    spec_restriction = spec.get("mana_restriction")
    if spec_restriction is None:
        return None
    return compile_restriction(spec_restriction, "add_mana.mana_restriction")


def _give_mana(ctx: EffectContext, spec: Mapping[str, Any], pid: int, produced) -> None:
    """Put one bundle of mana in one player's pool and say so."""
    # Imported here rather than at module scope: `characteristics` is reached
    # through `primitives` -> `zones` -> `effects`, so a top-level import turns
    # that existing chain into a cycle.
    from ..characteristics import mana_source_traits

    ctx.state.players[pid].mana_pool.add_tuple(
        produced,
        source=ctx.source_oid,
        persists_through_turn=_persists_through(ctx, spec),
        restriction=_restriction_of(spec),
        # What the source was, for "if mana from a Treasure was spent" -- see
        # `characteristics.mana_source_traits`. Inside this helper rather than
        # at its one old call site, so the split branch below records
        # provenance too: a Treasure sacrificed for Klauth's ritual is still a
        # Treasure the mana came from.
        source_traits=mana_source_traits(ctx.state, ctx.source_oid),
    )


@register("add_mana")
def op_add_mana(ctx: EffectContext, spec: Mapping[str, Any]):
    if spec.get("split"):
        # A generator, and only on this branch: `execute_one` delegates to a
        # returned generator, so the ordinary `add_mana` stays a plain call that
        # asks nothing. Written as one function with a `yield` in it, *every*
        # add_mana would become a generator.
        return _add_split_mana(ctx, spec)
    symbols = mana_string(ctx, spec)
    if not symbols:
        return None
    produced = parse_mana_production(symbols)
    for pid in select_players(ctx, spec.get("player", "you")):
        _give_mana(ctx, spec, pid, produced)
        ctx.state.emit(EventType.MANA_ADDED, player=pid, source=ctx.source_oid, mana=symbols)
    return None


def _add_split_mana(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Add X mana in **any combination of colors**", from a triggered ability.

    Klauth, Unrivaled Ancient. The same two keys a *mana ability* carries --
    `split` names the colours and `amount` is X -- read at resolution instead of
    at activation, because this is an ability that uses the stack.

    A mana ability answers the combination by **offering every composition** as
    an option and letting the payment solver pick (`costs._split_options`): it
    may not stop to ask, so the choice has to be folded into the price. A
    trigger has no payment to fold into and every right to ask, so it asks --
    one mana at a time, `ask_mode` over the colours, which is a genuinely free
    division of X and not X of one colour. The near miss is a `choose_mode` of
    five `add_mana`s wrapped in a `repeat`: that re-asks per iteration only by
    accident of nesting, and no shipped card spells it that way.

    X is read **once**, here, when the trigger resolves -- "the total power of
    attacking creatures" is a fact about the board at that moment, and a
    creature that dies to a blocker before the trigger resolves was still
    attacking when it was put on the stack but is not counted by a reader that
    waits. One read also means the loop cannot walk past the number it started
    with.

    X of zero asks nothing and adds nothing, exactly as a split mana ability
    with zero power taps for nothing.
    """
    colors = [str(c).upper() for c in spec.get("split") or ()]
    amount = spec.get("amount")
    total = max(0, int(evaluate_value(ctx, amount))) if amount is not None else 0
    if total <= 0 or not colors:
        return
    labels = [f"{{{c}}}" for c in colors]
    for pid in select_players(ctx, spec.get("player", "you")):
        produced = [0] * N_SYMBOLS
        for left in range(total, 0, -1):
            picked = yield from ask_mode(
                ctx, f"Add one mana ({left} to divide)", labels, pid
            )
            produced[SYMBOL_INDEX[colors[picked[0] if picked else 0]]] += 1
        symbols = "".join(f"{{{SYMBOLS[i]}}}" * produced[i] for i in range(N_SYMBOLS))
        _give_mana(ctx, spec, pid, produced)
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
