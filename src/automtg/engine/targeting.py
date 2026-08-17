"""Target legality and enumeration.

Targets are chosen when a spell or ability is put on the stack, and re-checked
when it resolves.  Legality enumerates one action per legal target *tuple*, which
is why this module caps the number of options it will produce: on a wide board
"target creature" could otherwise generate dozens of actions and swamp both the
UI and the RL action space.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from typing import TYPE_CHECKING

from .carddef import TargetSpec
from .characteristics import chars, protected_from
from .effects.context import EffectContext
from .effects.selectors import matches, resolve_pool
from .enums import Keyword, Zone
from .structs import TargetRef

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState

#: Most target combinations legality will enumerate for a single spell/ability.
#: Only ever binding on very wide boards; documented in docs/rules-coverage.md.
MAX_TARGET_OPTIONS = 12


def candidates(
    state: GameState,
    controller: int,
    spec: TargetSpec,
    source_oid: int | None,
    *,
    exclude_sid: int | None = None,
) -> list[TargetRef]:
    """Every legal choice for one target spec, in deterministic order."""
    ctx = EffectContext(state=state, controller=controller, source_oid=source_oid)

    if spec.kind == "player":
        return [
            TargetRef.player(pid)
            for pid in state.alive()
            if _player_allowed(state, controller, pid, spec)
        ]

    if spec.kind == "spell":
        return [
            TargetRef.stack(item.sid)
            for item in state.stack
            if item.is_spell and item.sid != exclude_sid
        ]

    if spec.kind == "any":
        refs: list[TargetRef] = [
            TargetRef.obj(oid)
            for oid in resolve_pool(ctx, {**dict(spec.selector), "zone": "battlefield"})
            if can_be_targeted(state, controller, oid, source_oid=source_oid)
        ]
        refs.extend(TargetRef.player(pid) for pid in state.alive())
        return refs

    pool = resolve_pool(ctx, spec.selector)
    return [
        TargetRef.obj(oid)
        for oid in pool
        if can_be_targeted(state, controller, oid, source_oid=source_oid)
    ]


def _player_allowed(state: GameState, controller: int, pid: int, spec: TargetSpec) -> bool:
    clause = spec.selector.get("controller", "any")
    if clause == "opponent":
        return pid != controller
    if clause == "you":
        return pid == controller
    return True


def can_be_targeted(
    state: GameState, controller: int, oid: int, *, source_oid: int | None = None
) -> bool:
    """Hexproof stops opponents (but not the controller) from targeting.

    Protection stops *anyone*, including the controller: "protection from
    Wizards" means your own Wizard cannot target it either, which is the half of
    protection that a hexproof-shaped implementation would silently get wrong.

    Shroud (702.18a) stops everyone too, and that is the whole difference
    between it and hexproof -- so it has to be asked *before* the controller
    early return below, not folded in beside hexproof after it.  A Simic Sky
    Swallower its own controller could still pump or blink would be a strictly
    better card than the one printed.  Unlike protection it is read here and
    nowhere else: shroud says nothing about damage, blocking or enchant/equip.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    if not obj.on_battlefield:
        return True
    if protected_from(state, oid, source_oid):
        return False
    keywords = chars(state, oid).keywords
    if Keyword.SHROUD.value in keywords:
        return False
    if obj.controller == controller:
        return True
    return Keyword.HEXPROOF.value not in keywords


def _room(limit: int, empty: list[tuple[TargetRef, ...]]) -> int:
    """How many real candidates fit under ``limit`` beside the decline option."""
    return max(1, limit - len(empty))


def enumerate_target_tuples(
    state: GameState,
    controller: int,
    specs: Sequence[TargetSpec],
    source_oid: int | None,
    *,
    exclude_sid: int | None = None,
    limit: int = MAX_TARGET_OPTIONS,
) -> list[tuple[TargetRef, ...]]:
    """Every legal combination of targets, capped at ``limit``.

    Returns ``[()]`` for a spell with no targets and ``[]`` when a required
    target has no legal choice (i.e. the spell cannot be cast at all).

    An ``optional`` spec always contributes the empty choice, whether or not it
    has candidates.  It used to contribute one only when there were none, which
    made declining impossible the moment anything legal was on the battlefield
    -- so Simic Charm's "permanents you control gain hexproof" mode, whose
    target is optional, could not be reached in any game with a creature in it.
    """
    if not specs:
        return [()]

    per_spec: list[list[tuple[TargetRef, ...]]] = []
    for spec in specs:
        options = candidates(state, controller, spec, source_oid, exclude_sid=exclude_sid)
        # Declining comes *last*, and that is load-bearing rather than
        # cosmetic: whatever picks a tuple without asking -- an AI seat, a
        # trigger resolving on its own -- takes the first, and a Shipbreaker
        # Kraken whose "tap up to four target creatures" defaulted to tapping
        # none would be a different card.
        empty: list[tuple[TargetRef, ...]] = [()] if spec.optional else []
        if spec.count > 1:
            combos = [
                tuple(c) for c in itertools.combinations(options, min(spec.count, len(options)))
            ]
            if not combos and not spec.optional:
                return []
            # `combinations(x, 0)` is `[()]`, so an optional spec with nothing to
            # choose would otherwise offer the empty choice twice -- and two
            # identical actions is the very thing this list must not produce.
            # The cap eats candidates, never the choice to decline -- but it
            # never eats the last candidate either: `stack.push_trigger` and
            # `suspend` ask with `limit=1` and take `options[0]`, so trading the
            # one real choice for "no targets" would silently fizzle every
            # triggered ability with an optional target.
            per_spec.append(list(dict.fromkeys(combos[: _room(limit, empty)] + empty)))
        else:
            if not options and not spec.optional:
                return []
            per_spec.append([(o,) for o in options][: _room(limit, empty)] + empty)

    out: list[tuple[TargetRef, ...]] = []
    for combo in itertools.product(*per_spec):
        flat = tuple(ref for part in combo for ref in part)
        if len(set(flat)) != len(flat):
            continue  # the same object cannot fill two targets
        out.append(flat)
        if len(out) >= limit:
            break
    return out


def still_legal(
    state: GameState,
    controller: int,
    spec: TargetSpec,
    ref: TargetRef,
    source_oid: int | None,
) -> bool:
    """Re-check a chosen target as the spell or ability resolves."""
    if ref.kind == "player":
        return state.is_alive(ref.id) and _player_allowed(state, controller, ref.id, spec)
    if ref.kind == "stack":
        item = state.stack_item(ref.id)
        return item is not None and item.is_spell
    obj = state.objects.get(ref.id)
    if obj is None:
        return False
    if not can_be_targeted(state, controller, ref.id, source_oid=source_oid):
        return False
    if spec.kind == "card_in_graveyard":
        return obj.zone is Zone.GRAVEYARD
    ctx = EffectContext(state=state, controller=controller, source_oid=source_oid)
    selector = dict(spec.selector)
    if spec.kind == "any" and "zone" not in selector:
        selector["zone"] = "battlefield"
    return matches(ctx, ref.id, selector)


def filter_legal(
    state: GameState,
    controller: int,
    specs: Sequence[TargetSpec],
    refs: Sequence[TargetRef],
    source_oid: int | None,
) -> tuple[dict[str, tuple[TargetRef, ...]], bool]:
    """Split stored targets into per-spec buckets, dropping illegal ones.

    Returns ``(targets_by_spec_id, any_target_remains)``.  A spell whose targets
    have all become illegal is countered on resolution ("fizzles").
    """
    buckets: dict[str, list[TargetRef]] = {}
    index = 0
    had_targets = False
    for spec in specs:
        take = spec.count if spec.count > 1 else 1
        chunk = list(refs[index : index + take])
        index += take
        kept = [r for r in chunk if still_legal(state, controller, spec, r, source_oid)]
        if chunk:
            had_targets = True
        buckets[spec.id] = kept
    remains = any(bool(v) for v in buckets.values())
    return {k: tuple(v) for k, v in buckets.items()}, (remains or not had_targets)


def describe_ref(state: GameState, ref: TargetRef) -> str:
    """A player-facing name for one chosen target.

    Lives here rather than in `legality` because a *triggered* ability chooses
    its targets too, and `stack` cannot import `legality` -- legality imports
    stack.
    """
    if ref.kind == "player":
        return state.players[ref.id].name or f"p{ref.id}"
    if ref.kind == "stack":
        item = state.stack_item(ref.id)
        return item.description if item else f"stack#{ref.id}"
    obj = state.objects.get(ref.id)
    return state.card_of(obj).name if obj else f"#{ref.id}"
