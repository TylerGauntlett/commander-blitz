"""Paying costs.

Mana payment is automatic (see :mod:`automtg.engine.mana`): an action never
carries a payment, and legality only offers a cast or activation when the solver
can find a set of sources to tap.  Non-mana costs (sacrifice, discard, pay life)
may need a choice, so :func:`pay` is a generator.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import TYPE_CHECKING, Any

from .carddef import Cost
from .characteristics import chars
from .effects.context import EffectContext, ask_objects
from .enums import Keyword, Zone
from .events import EventType
from .mana import (
    SYMBOL_INDEX,
    SYMBOLS,
    ManaCost,
    ManaSource,
    Requirement,
    format_symbols,
    solve_payment,
)
from .primitives import discard_cards, lose_life, tap_permanent
from .zones import exile as exile_object
from .zones import sacrifice as sacrifice_object

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def mana_sources(state: GameState, pid: int) -> list[ManaSource]:
    """Every mana ability this player could activate right now.

    Only tap-only mana abilities are considered.  A mana ability with an extra
    cost (pay life, sacrifice) is left for the player to activate explicitly.
    """
    out: list[ManaSource] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.controller != pid or obj.tapped:
            continue
        card = state.card_of(obj)
        c = chars(state, oid)
        is_creature = "Creature" in c.types
        if (
            is_creature
            and obj.summoning_sick(state.turn)
            and Keyword.HASTE.value not in c.keywords
        ):
            continue
        is_land = "Land" in c.types
        for ability in card.abilities:
            if not ability.is_mana_ability or not ability.mana_options:
                continue
            if ability.cost is None or not ability.cost.is_tap_only():
                continue
            out.append(
                ManaSource(
                    oid=oid,
                    ability_index=ability.index,
                    options=ability.mana_options,
                    is_land=is_land,
                    sort_key=(0 if is_land else 1, card.id, oid),
                )
            )
    return out


def available_mana(state: GameState, pid: int) -> int:
    """Upper bound on mana this player could produce, for heuristics and encoding."""
    pool = state.players[pid].mana_pool.total()
    return pool + sum(source.max_output() for source in mana_sources(state, pid))


def mana_availability(state: GameState, pid: int) -> dict[str, Any]:
    """What this player could produce right now, for the client's mana row.

    Deliberately *not* a single colour histogram.  A dual land reading "Add {G}
    or {U}" is one mana that could be either, so a histogram claiming one {G}
    and one {U} would overstate the board by a mana per dual.  Instead every
    untapped source keeps its own list of the symbols it might make, and the UI
    renders an ambiguous source as one split pip rather than two solid ones.

    ``total`` is still an upper bound rather than a promise: two sources that
    each make "{G} or {U}" can produce two mana, but never two {U} *and* two
    {G}.  Only :func:`can_pay_mana` answers affordability, and the client uses
    the action list for that.
    """
    pool = state.players[pid].mana_pool
    sources = mana_sources(state, pid)
    return {
        "pool": pool.to_dict(),
        "sources": [
            {
                "oid": source.oid,
                # Every yield the ability could choose, each as the symbols it
                # actually makes.  "{T}: Add {G} or {U}" is [["G"], ["U"]];
                # "{T}: Add {G}{U}" is [["G", "U"]].  The union alone cannot
                # tell those apart, and the difference is a whole mana.
                "options": [_option_symbols(option) for option in source.options],
                # Sorted by SYMBOLS order so {G}{U} and {U}{G} render alike.
                "symbols": sorted(
                    (SYMBOLS[i] for i in source.producible()), key=SYMBOL_INDEX.get
                ),
                "amount": source.max_output(),
            }
            for source in sources
        ],
        "total": pool.total() + sum(source.max_output() for source in sources),
    }


def _option_symbols(option: Sequence[int]) -> list[str]:
    """One mana-ability yield as repeated symbols: (0,1,0,0,1,0) -> ["U", "G"]."""
    return [SYMBOLS[i] for i, count in enumerate(option) for _ in range(count)]


def can_pay_mana(
    state: GameState, pid: int, cost: ManaCost, *, x: int = 0, extra_generic: int = 0
) -> bool:
    req = cost.with_x(x)
    if extra_generic:
        req = Requirement(colored=req.colored, generic=req.generic + extra_generic)
    return (
        solve_payment(req, state.players[pid].mana_pool, mana_sources(state, pid)) is not None
    )


def can_pay(
    state: GameState, pid: int, cost: Cost | None, source_oid: int | None, *, x: int = 0
) -> bool:
    """Can this player pay every part of ``cost`` right now?"""
    if cost is None:
        return True
    player = state.players[pid]

    if cost.tap:
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or obj.tapped or not obj.on_battlefield:
            return False
        c = chars(state, source_oid)
        if (
            "Creature" in c.types
            and obj.summoning_sick(state.turn)
            and Keyword.HASTE.value not in c.keywords
        ):
            return False
    if cost.untap:
        obj = state.objects.get(source_oid) if source_oid is not None else None
        if obj is None or not obj.tapped:
            return False
    if cost.pay_life and player.life <= cost.pay_life:
        return False
    if cost.discard and len(player.hand) < cost.discard:
        return False
    if cost.sacrifice is not None and not _sacrifice_pool(state, pid, cost, source_oid):
        return False
    if cost.remove_counters is not None:
        obj = state.objects.get(source_oid) if source_oid is not None else None
        kind = str(cost.remove_counters.get("counter", "+1/+1"))
        amount = int(cost.remove_counters.get("amount", 1))
        if obj is None or obj.counter(kind) < amount:
            return False
    if cost.exile_from_graveyard is not None and not _graveyard_pool(
        state, pid, cost, source_oid
    ):
        return False

    # Mana last: it is the most expensive check.
    if not cost.mana.is_free() or cost.mana.x_count:
        sources = mana_sources(state, pid)
        # A source that is about to be tapped for this cost cannot also pay for it.
        if cost.tap and source_oid is not None:
            sources = [s for s in sources if s.oid != source_oid]
        if solve_payment(cost.mana.with_x(x), player.mana_pool, sources) is None:
            return False
    return True


def _sacrifice_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    from .effects.selectors import resolve_pool

    spec = dict(cost.sacrifice or {})
    spec.setdefault("controller", "you")
    spec.setdefault("zone", "battlefield")
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    return pool if len(pool) >= count else []


def _graveyard_pool(
    state: GameState, pid: int, cost: Cost, source_oid: int | None
) -> list[int]:
    from .effects.selectors import resolve_pool

    spec = dict(cost.exile_from_graveyard or {})
    spec.setdefault("controller", "you")
    spec["zone"] = "graveyard"
    count = int(spec.pop("count", 1) or 1)
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)
    pool = resolve_pool(ctx, spec)
    return pool if len(pool) >= count else []


def pay(
    state: GameState,
    pid: int,
    cost: Cost | None,
    source_oid: int | None,
    *,
    x: int = 0,
    extra_generic: int = 0,
) -> Generator[Any, list[int], bool]:
    """Pay a cost, asking the player for any choices it requires.

    Returns ``True`` on success.  Callers only invoke this after :func:`can_pay`,
    so a ``False`` return means the game state changed underneath them.
    """
    if cost is None and not extra_generic:
        return True
    cost = cost or Cost()
    player = state.players[pid]
    ctx = EffectContext(state=state, controller=pid, source_oid=source_oid)

    if cost.tap and source_oid is not None:
        tap_permanent(state, source_oid)
    if cost.untap and source_oid is not None:
        obj = state.objects.get(source_oid)
        if obj is not None:
            obj.tapped = False
            state.bump_chars()

    # Mana is paid first: activating mana abilities happens before other costs
    # are paid (rule 601.2g), so sacrificing a mana creature as part of the cost
    # cannot strand the payment.
    req = cost.mana.with_x(x)
    if extra_generic:
        req = Requirement(colored=req.colored, generic=req.generic + extra_generic)
    if req.total and not pay_mana(
        state, pid, req, exclude_oid=source_oid if cost.tap else None
    ):
        return False

    if cost.pay_life:
        lose_life(state, pid, cost.pay_life, source=source_oid)

    if cost.discard:
        picked = yield from ask_objects(
            ctx, "Discard", list(player.hand), cost.discard, cost.discard, pid, "discard"
        )
        discard_cards(state, pid, picked)

    if cost.sacrifice is not None:
        spec = dict(cost.sacrifice)
        count = int(spec.pop("count", 1) or 1)
        pool = _sacrifice_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(ctx, "Sacrifice", pool, count, count, pid, "sacrifice")
        for oid in picked:
            sacrifice_object(state, oid)

    if cost.remove_counters is not None and source_oid is not None:
        from .primitives import remove_counters

        remove_counters(
            state,
            source_oid,
            str(cost.remove_counters.get("counter", "+1/+1")),
            int(cost.remove_counters.get("amount", 1)),
        )

    if cost.exile_from_graveyard is not None:
        spec = dict(cost.exile_from_graveyard)
        count = int(spec.pop("count", 1) or 1)
        pool = _graveyard_pool(state, pid, cost, source_oid)
        picked = yield from ask_objects(ctx, "Exile from your graveyard", pool, count, count, pid, "exile_cost")
        for oid in picked:
            exile_object(state, oid, cause="cost")

    return True


def pay_mana(
    state: GameState, pid: int, req: Requirement, *, exclude_oid: int | None = None
) -> bool:
    """Tap sources and deduct ``req`` from the pool."""
    player = state.players[pid]
    sources = mana_sources(state, pid)
    if exclude_oid is not None:
        sources = [s for s in sources if s.oid != exclude_oid]
    payment = solve_payment(req, player.mana_pool, sources)
    if payment is None:
        return False
    for oid, ability_index, option_index in payment.taps:
        activate_mana_ability(state, oid, ability_index, pid, option_index)
    player.mana_pool.spend(req)
    state.emit(EventType.MANA_SPENT, player=pid, amount=req.total)
    return True


def activate_mana_ability(
    state: GameState, oid: int, ability_index: int, pid: int, option_index: int = 0
) -> None:
    """Tap a permanent for mana.  Mana abilities never use the stack.

    The produced mana comes straight from the ability's precomputed
    ``mana_options`` rather than from running its effects.  A modal mana ability
    ("Add {G} or {U}") would otherwise ask its controller to pick a mode, and a
    mana ability must never stop to ask anything.
    """
    card = state.card(oid)
    ability = card.abilities[ability_index]
    if ability.cost is not None and ability.cost.tap:
        tap_permanent(state, oid)
    produced = ability.mana_options[option_index]
    state.players[pid].mana_pool.add_tuple(produced)
    state.emit(
        EventType.MANA_ADDED, player=pid, source=oid, mana=format_symbols(produced)
    )


def land_drops_available(state: GameState, pid: int) -> int:
    """How many more lands this player may play this turn."""
    from .characteristics import player_extra_land_drops

    player = state.players[pid]
    return 1 + player.extra_land_drops + player_extra_land_drops(state, pid) - player.lands_played


def commander_cost(state: GameState, oid: int) -> int:
    """Extra generic mana owed for casting a commander from the command zone."""
    obj = state.objects.get(oid)
    if obj is None:
        return 0
    return 2 * state.players[obj.owner].commander_tax.get(oid, 0)


def zone_of(state: GameState, oid: int) -> Zone:
    return state.objects[oid].zone
