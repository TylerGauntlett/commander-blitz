"""Paying costs.

Mana payment is automatic (see :mod:`automtg.engine.mana`): an action never
carries a payment, and legality only offers a cast or activation when the solver
can find a set of sources to tap.  Non-mana costs (sacrifice, discard, pay life)
may need a choice, so :func:`pay` is a generator.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import TYPE_CHECKING, Any

from .carddef import CardDef, Cost
from .characteristics import chars, player_doubles_land_mana
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


def mana_sources(
    state: GameState, pid: int, *, purpose: frozenset[str] | None = None
) -> list[ManaSource]:
    """Every mana ability this player could activate right now.

    Only tap-only mana abilities are considered.  A mana ability with an extra
    cost (pay life, sacrifice) is left for the player to activate explicitly.

    ``purpose`` describes what the mana would be spent on -- the lowercased card
    types of the spell being cast.  Restricted sources ("spend this mana only to
    cast a creature spell") are dropped unless the purpose matches, so the
    solver never has to know restrictions exist.  ``None`` means "no particular
    spell", and offers only unrestricted mana: an under-count rather than an
    over-count, which is the safe direction for a number the AI reads.
    """
    out: list[ManaSource] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.controller != pid or obj.tapped:
            continue
        out.extend(
            source
            for source in _sources_of(state, oid, obj)
            if source.restriction is None
            or (purpose is not None and source.restriction in purpose)
        )
    return out


def spell_purpose(card: CardDef) -> frozenset[str]:
    """What restricted mana would have to allow, to pay for this card."""
    return frozenset(t.lower() for t in card.types)


def available_mana(state: GameState, pid: int) -> int:
    """Upper bound on mana this player could produce, for heuristics and encoding."""
    pool = state.players[pid].mana_pool.total()
    return pool + sum(source.max_output() for source in mana_sources(state, pid))


def sources_by_controller(state: GameState) -> dict[int, list[ManaSource]]:
    """Every player's mana sources, from a single walk of the battlefield.

    :func:`mana_sources` filters the whole battlefield per player, so serializing
    a four-player pod walked it four times over.  The per-object work is
    identical either way; this just partitions instead of re-scanning.  Pass the
    result to :func:`mana_availability` as ``sources``.
    """
    out: dict[int, list[ManaSource]] = {p.pid: [] for p in state.players}
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.tapped:
            continue
        bucket = out.get(obj.controller)
        if bucket is None:
            continue
        bucket.extend(_sources_of(state, oid, obj))
    return out


def _sources_of(state: GameState, oid: int, obj: Any) -> list[ManaSource]:
    """The tap-only mana abilities of one untapped permanent."""
    # A mana ability is an activated ability, so "its activated abilities can't
    # be activated this turn" stops it here as well as in `legality`. Filtered in
    # this one helper because both entry points above go through it.
    if obj.abilities_locked:
        return []
    card = state.card_of(obj)
    c = chars(state, oid)
    is_creature = "Creature" in c.types
    if is_creature and obj.summoning_sick(state.turn) and Keyword.HASTE.value not in c.keywords:
        return []
    is_land = "Land" in c.types
    doubled = is_land and player_doubles_land_mana(state, obj.controller)
    out: list[ManaSource] = []
    for ability in card.abilities:
        if not ability.is_mana_ability or not ability.mana_options:
            continue
        if ability.cost is None or not ability.cost.is_tap_only():
            continue
        out.append(
            ManaSource(
                oid=oid,
                ability_index=ability.index,
                options=(
                    tuple(mana_produced(option, doubled=doubled) for option in ability.mana_options)
                ),
                is_land=is_land,
                sort_key=(0 if is_land else 1, card.id, oid),
                restriction=ability.mana_restriction,
            )
        )
    return out


def mana_produced(option: Sequence[int], *, doubled: bool) -> tuple[int, ...]:
    """What tapping for ``option`` actually yields.

    Vorinclex's "whenever you tap a land for mana, add one mana of any type that
    land produced" is not a trigger: a mana ability must never use the stack or
    stop to ask, so it is folded in here instead.

    This one helper is called from **both** ``_sources_of`` (so legality counts
    the extra mana when deciding what is castable) and ``activate_mana_ability``
    (so payment actually adds it).  The two must not be able to disagree -- a
    spell offered on doubled mana and then paid for on single mana would strand
    the payment mid-cast.

    *Simplification*: a dual land doubles whatever it produced rather than
    offering a free choice of type, because a mana ability cannot ask.  Recorded
    in ``docs/rules-coverage.md`` alongside the other automatic-mana trades.
    """
    if not doubled:
        return tuple(option)
    return tuple(v * 2 for v in option)


def produced_symbols(card: CardDef) -> list[str]:
    """Every mana symbol this card's mana abilities could make, deduplicated.

    The client colours lands by what they tap for, and this is the only honest
    source for that: "Island" is inferable from a subtype, but a nonbasic dual is
    not, and re-deriving it by parsing ``oracle_text`` in the browser is exactly
    the guess :mod:`frontend/src/logic/mana.ts` refuses to make.
    """
    found: set[str] = set()
    for ability in card.mana_abilities():
        for option in ability.mana_options:
            found.update(_option_symbols(option))
    return sorted(found, key=SYMBOL_INDEX.get)


def mana_availability(
    state: GameState, pid: int, sources: Sequence[ManaSource] | None = None
) -> dict[str, Any]:
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

    ``sources`` lets a caller serializing every seat share one battlefield walk;
    see :func:`sources_by_controller`.  Omitted, it is computed here as before.
    """
    pool = state.players[pid].mana_pool
    if sources is None:
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
    state: GameState,
    pid: int,
    cost: ManaCost,
    *,
    x: int = 0,
    extra_generic: int = 0,
    purpose: frozenset[str] | None = None,
) -> bool:
    req = cost.with_x(x)
    if extra_generic:
        req = Requirement(
            colored=req.colored,
            generic=max(0, req.generic + extra_generic),
            hybrid=req.hybrid,
        )
    return (
        solve_payment(
            req, state.players[pid].mana_pool, mana_sources(state, pid, purpose=purpose)
        )
        is not None
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
    if cost.discard and len(_discard_pool(state, pid, cost)) < cost.discard:
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


def _discard_pool(state: GameState, pid: int, cost: Cost) -> list[int]:
    """Which cards in hand this cost is allowed to throw away.

    The whole hand unless the cost narrows it -- "by discarding a **land**
    card".  Kept as a pool rather than a count so `can_pay` and `pay` cannot
    disagree about whether the cost is payable.
    """
    hand = list(state.players[pid].hand)
    if cost.discard_selector is None:
        return hand
    from .effects.selectors import matches

    spec = {**dict(cost.discard_selector), "zone": "hand"}
    ctx = EffectContext(state=state, controller=pid)
    return [oid for oid in hand if matches(ctx, oid, spec)]


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
    purpose: frozenset[str] | None = None,
) -> Generator[Any, list[int], bool]:
    """Pay a cost, asking the player for any choices it requires.

    Returns ``True`` on success.  Callers only invoke this after :func:`can_pay`,
    so a ``False`` return means the game state changed underneath them.

    ``purpose`` is what the mana is being spent on, and must be the same value
    legality used when it decided this was payable -- restricted mana is offered
    or withheld by that alone.
    """
    if cost is None and not extra_generic:
        return True
    cost = cost or Cost()
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
        # Clamped at zero: `extra_generic` is negative for a cost *reduction*,
        # and "costs {X} less" never reaches through the generic part into the
        # coloured pips however large X gets.
        req = Requirement(
            colored=req.colored,
            generic=max(0, req.generic + extra_generic),
            hybrid=req.hybrid,
        )
    if req.total and not pay_mana(
        state, pid, req, exclude_oid=source_oid if cost.tap else None, purpose=purpose
    ):
        return False

    if cost.pay_life:
        lose_life(state, pid, cost.pay_life, source=source_oid)

    if cost.discard:
        pool = _discard_pool(state, pid, cost)
        picked = yield from ask_objects(
            ctx, "Discard", pool, cost.discard, cost.discard, pid, "discard"
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
    state: GameState,
    pid: int,
    req: Requirement,
    *,
    exclude_oid: int | None = None,
    purpose: frozenset[str] | None = None,
) -> bool:
    """Tap sources and deduct ``req`` from the pool."""
    player = state.players[pid]
    sources = mana_sources(state, pid, purpose=purpose)
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

    obj = state.objects.get(oid)
    is_land = obj is not None and "Land" in chars(state, oid).types
    doubled = is_land and obj is not None and player_doubles_land_mana(state, obj.controller)
    produced = mana_produced(ability.mana_options[option_index], doubled=doubled)

    state.players[pid].mana_pool.add_tuple(produced)
    state.emit(
        EventType.MANA_ADDED, player=pid, source=oid, mana=format_symbols(produced)
    )
    if is_land and obj is not None:
        _lands_tapped_for_mana(state, obj)


def _lands_tapped_for_mana(state: GameState, land: Any) -> None:
    """Vorinclex's second half: an opponent's land does not untap next turn.

    Applied here rather than as a triggered ability because tapping for mana
    happens *inside* payment, where nothing can go on the stack -- the same
    reason the doubling above is inline.  One-shot, so it is
    ``skip_next_untap`` rather than the `frozen_by` lock, which lasts as long as
    its source is on the battlefield: these are different lifetimes and using
    either for the other would be wrong.
    """
    from .characteristics import players_freezing_opponent_lands

    freezers = players_freezing_opponent_lands(state)
    if any(pid != land.controller for pid in freezers):
        land.skip_next_untap = True


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


def cost_reduction(state: GameState, pid: int, card: CardDef) -> int:
    """How much less this card costs its controller right now.

    Generic only, and never below zero: "costs {X} less" does not touch coloured
    pips, which is both what the rules say and the only thing the payment solver
    could act on.  Read from the board rather than stored, because it changes
    every time a creature arrives -- Ghalta is a 12-drop or a 2-drop depending on
    what is already in play.
    """
    spec = card.cost_reduction
    if not spec:
        return 0
    if "count" in spec:
        return sum(1 for _ in _reduction_matches(state, pid, spec["count"]))
    if "total_power" in spec:
        return sum(
            max(0, chars(state, oid).power)
            for oid in _reduction_matches(state, pid, spec["total_power"])
        )
    return 0


def _reduction_matches(state: GameState, pid: int, filt: Any):
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        controller = filt.get("controller", "you")
        if controller == "you" and obj.controller != pid:
            continue
        if controller == "opponent" and obj.controller == pid:
            continue
        c = chars(state, oid)
        if (want := filt.get("types")) and not set(want).issubset(c.types):
            continue
        if (want := filt.get("subtypes")) and not set(want) & set(c.subtypes):
            continue
        yield oid


def zone_of(state: GameState, oid: int) -> Zone:
    return state.objects[oid].zone
