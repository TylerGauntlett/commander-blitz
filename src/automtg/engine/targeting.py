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
from .effects.values import evaluate_value
from .enums import Keyword, Zone
from .structs import StackItem, TargetRef

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
            if item.is_spell
            and item.sid != exclude_sid
            and _spell_matches(ctx, item, spec)
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


def _spell_matches(ctx: EffectContext, item: StackItem, spec: TargetSpec) -> bool:
    """Does one spell on the stack satisfy its target spec's `selector`?

    A `kind: "spell"` spec used to ignore its selector outright, in both
    `candidates` and `still_legal` -- so "Counter target **noncreature** spell"
    was Counterspell, and Essence Scatter, Exclude and Negate were all one card.
    Nothing announced it: the selector loaded, validated and was simply never
    consulted, which is exactly the silently-inert clause `validate_selector`
    exists to prevent one layer up.

    The default zone has to be the **stack**, not `matches`'s battlefield: the
    object being asked about is a spell, so a battlefield default would reject
    every candidate and turn every counterspell in the pool into a dead card.

    Characteristics come off the printed face rather than the derived layer,
    because `matches` reads derived only for permanents (`obj.on_battlefield`)
    -- which is what a spell on the stack should get anyway: no static is
    applying to it.
    """
    if not spec.selector:
        return True
    if item.oid is None:
        return False
    return matches(ctx, item.oid, spec.selector, default_zone="stack")


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


def _one_each(state: GameState, refs: Sequence[TargetRef]) -> bool:
    """Are these objects controlled by pairwise different players?

    "For each player, exile up to one target nonland permanent that player
    controls" is the same set of legal choices as "any number of target nonland
    permanents, no two controlled by the same player" -- so it is a constraint
    on the combination rather than one target spec per seat.

    Written this way on purpose. One spec per seat would have to be `optional`,
    and `filter_legal` splits the stored refs by *position*: a declined optional
    contributes nothing to the flat tuple, so every spec after it would read the
    wrong refs back. That is a bug no board would show, and this shape cannot
    have it -- there is one spec, and it swallows whatever was chosen.
    """
    seen: set[int] = set()
    for ref in refs:
        obj = state.objects.get(ref.id)
        if obj is None:
            continue
        if obj.controller in seen:
            return False
        seen.add(obj.controller)
    return True


def _room(limit: int, empty: list[tuple[TargetRef, ...]]) -> int:
    """How many real candidates fit under ``limit`` beside the decline option."""
    return max(1, limit - len(empty))


def target_count(
    state: GameState, controller: int, spec: TargetSpec, source_oid: int | None
) -> int | str:
    """How many targets this spec asks for **right now** -- 601.2c's number.

    A literal or ``"any"`` answers itself.  Anything else is a value expression:
    "return up to **X** target creature cards…, where X is the number of times
    this enchantment was kicked" is ``{"additional_paid": true}``, and the only
    honest moment to read it is the one this function is called from -- when the
    targets are declared.

    Where the number comes from is the whole design question, and the answer is
    ``source_oid``.  For Marshal's Anthem the targets belong to a *triggered*
    ability, so they are declared when the trigger is put on the stack (603.3d)
    -- by which time the enchantment is already on the battlefield and
    ``obj.cast_additional``, written by `game._cast` and carried across the zone
    change on the same oid, says how many times it was kicked.  That is the same
    read `values.additional_paid` does for casualty and replicate, from the same
    place, and it is why this capability needed no new bookkeeping.

    A **spell's own** targets are a different moment and a different answer:
    601.2c fixes them while the spell is being cast, before it has been paid
    for, and legality enumerates them before the player has chosen X or how many
    times to kick.  There is nothing to read there, so `loader._compile_targets`
    refuses a value-expression count on a card's own `targets` outright rather
    than letting it quietly evaluate to zero.
    """
    if isinstance(spec.count, int) or spec.count == "any":
        return spec.count
    ctx = EffectContext(state=state, controller=controller, source_oid=source_oid)
    return max(0, evaluate_value(ctx, spec.count))


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
        count = target_count(state, controller, spec, source_oid)
        if count == "any" or spec.up_to:
            # "Any number of target creatures", and "up to X target creature
            # cards". A size the caster picks, so every subset up to the
            # ceiling is a legal choice -- ordered **largest first**, for the
            # reason above: whatever takes a tuple without asking takes the
            # first, and "any number" defaulting to none is a spell that does
            # nothing. The empty subset comes last and always exists, because
            # both readings include zero whether or not the spec is `optional`.
            #
            # The two differ only in where the ceiling comes from: "any number"
            # has none beyond the board, and "up to X" is capped by the value --
            # which is the whole of the difference between Marshal's Anthem cast
            # with no kicks and a {2}{W}{W} full-graveyard reanimation.
            ceiling = len(options) if count == "any" else min(int(count), len(options))
            subsets = [
                tuple(c)
                for size in range(ceiling, 0, -1)
                for c in itertools.combinations(options, size)
                if not spec.one_per_player or _one_each(state, c)
            ]
            per_spec.append(list(dict.fromkeys([*subsets[: _room(limit, [()])], ()])))
        elif count <= 0:
            # A computed count of zero -- "one target for each time this was
            # kicked", kicked no times. Not the same as no legal choice: the
            # ability asks for nothing and resolves, where `[]` would say it
            # cannot be put on the stack at all.
            per_spec.append([()])
        elif count > 1:
            combos = [tuple(c) for c in itertools.combinations(options, min(count, len(options)))]
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
        if item is None or not item.is_spell:
            return False
        # 608.2b re-checks every target as the spell resolves, and the selector
        # is half of what makes a target legal. Without this an Essence Scatter
        # held against a creature spell would still counter it after the spell
        # stopped being a creature spell.
        ctx = EffectContext(state=state, controller=controller, source_oid=source_oid)
        return _spell_matches(ctx, item, spec)
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
        # A variable-size spec swallows whatever is left. The loader guarantees
        # there is at most one and that it comes last, which is what makes this
        # unambiguous -- a variable-size spec in the middle would leave no way
        # to say where its refs end and the next spec's begin.
        #
        # Re-evaluating a computed count here would be worse than using the
        # stored length, not better: the number is fixed when the targets are
        # declared (601.2c), and anything that moved in between would re-slice
        # refs that were chosen under the old one.
        take = len(refs) - index if spec.variable_size else max(1, spec.count)
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
