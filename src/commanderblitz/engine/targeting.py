"""Target legality and enumeration.

Targets are chosen when a spell or ability is put on the stack, and re-checked
when it resolves.  Legality enumerates one action per legal target *tuple*, which
is why this module caps the number of options it will produce: on a wide board
"target creature" could otherwise generate dozens of actions and swamp both the
UI and the RL action space.
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .carddef import TargetSpec
from .characteristics import chars, player_protected_from, protected_from, protection_from
from .effects.context import EffectContext
from .effects.selectors import matches, resolve_pool, select_players
from .effects.values import evaluate_value
from .enums import Keyword, Zone
from .player_statics import player_has_hexproof
from .structs import StackItem, TargetRef

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState

#: Most target combinations legality will enumerate for a single spell/ability.
#: Only ever binding on very wide boards; documented in docs/rules-coverage.md.
#: A lone single-target spec is exempt -- see `enumerate_target_tuples`.
MAX_TARGET_OPTIONS = 12


def candidates(
    state: GameState,
    controller: int,
    spec: TargetSpec,
    source_oid: int | None,
    *,
    exclude_sid: int | None = None,
    bindings: Mapping[str, Any] | None = None,
    chosen: Mapping[str, Sequence[TargetRef]] | None = None,
    x: int = 0,
) -> list[TargetRef]:
    """Every legal choice for one target spec, in deterministic order.

    ``chosen`` is the **sibling targets already picked for this same spell or
    ability** -- "choose target opponent and up to one target creature **they**
    control" (Cloak and Dagger, Entwined). 601.2c chooses every target at once,
    which is what makes the pair legal or not *together*; enumerated one spec at
    a time, the second one's `{"controller": {"target": "t1"}}` would resolve
    against nobody and offer nothing. `enumerate_target_tuples` fills this in
    per partial combination, and only for the specs that actually name a
    sibling.

    ``bindings`` is what the *event* carried, for a triggered ability whose
    target line names something the trigger found -- "target player other than
    **its** controller", where "it" is the token bound as ``subject``.  Passed
    in rather than read off anything reachable from here because a target spec
    is declared before there is a `StackItem` to read it from (603.3d), so the
    only holder is the `TriggerInstance` legality is enumerating for.  Empty for
    a spell, which binds nothing at all.

    ``x`` is the value announced for the source's own ``{X}``, for "target
    nontoken artifact you control **with mana value X**" -- The Mycosynth
    Gardens. 601.2b chooses X before 601.2c declares targets, so the pool only
    exists once X is known; left at its 0 default, a selector's ``{"x": true}``
    leaf reads zero and the card offers a pool nobody asked for.
    """
    ctx = EffectContext(
        state=state,
        controller=controller,
        source_oid=source_oid,
        bindings=dict(bindings or {}),
        targets={k: tuple(v) for k, v in (chosen or {}).items()},
        x=x,
    )

    if spec.kind == "player":
        return [
            TargetRef.player(pid)
            for pid in state.alive()
            if _player_allowed(ctx, pid, spec)
        ]

    if spec.kind == "spell":
        return [
            TargetRef.stack(item.sid)
            for item in state.stack
            if item.is_spell
            and item.sid != exclude_sid
            and _spell_matches(ctx, item, spec)
        ]

    if spec.kind == "ability_on_stack":
        # "Copy target activated or triggered ability you control" -- Peter
        # Parker's Camera. The complement of the `spell` branch above, and it has
        # to be its own kind rather than a looser `spell`: 113.7a makes an ability
        # on the stack a different object from a spell, with no card behind it,
        # and `item.is_spell` is exactly `kind == "spell"`.
        #
        # `_spell_matches` is deliberately **not** reused. Every clause it reads
        # -- types, colours, mana value, "creature spell" -- is a characteristic
        # of a card, and an ability has none; asking it would answer about the
        # source permanent instead, quietly making "target activated ability" mean
        # "target ability of a creature". Whose ability it is, is the one clause
        # printed cards in this family actually carry, and `controller` answers it.
        return [
            TargetRef.stack(item.sid)
            for item in state.stack
            if not item.is_spell
            and item.sid != exclude_sid
            and _ability_matches(ctx, item, spec)
        ]

    if spec.kind == "spell_or_permanent":
        # "Target spell or nonland permanent an opponent controls." One
        # instance of the word "target" whose legal choices live in two zones,
        # so the pool is the two halves concatenated rather than two specs --
        # two specs would be a card that targets twice and fizzles unless both
        # are still legal.
        #
        # Spells first, matching the printed word order, and both halves reuse
        # the matcher their single-kind branch uses: nothing here decides
        # legality of its own, so every ref this offers is one `still_legal`
        # will accept when it re-checks it -- and it re-checks by `ref.kind`,
        # which is why that function needed no change at all.
        #
        # The permanent half reads `spec.permanent_half`: "target spell or
        # **creature**" (Fatehold Charm) narrows only the permanent, and one
        # selector over both would make it "target creature spell or creature".
        pool: list[TargetRef] = [
            TargetRef.stack(item.sid)
            for item in state.stack
            if item.is_spell and item.sid != exclude_sid and _spell_matches(ctx, item, spec)
        ]
        pool.extend(
            TargetRef.obj(oid)
            for oid in resolve_pool(ctx, {**dict(spec.permanent_half), "zone": "battlefield"})
            if can_be_targeted(state, controller, oid, source_oid=source_oid)
        )
        return pool
    if spec.kind == "card_in_exile":
        # Exile is kept per owner, so the selector says whose pile to walk the
        # same way a graveyard spec does; the zone is supplied, because the kind
        # already said it and a card writing something else would mean a target
        # line whose name and whose pool disagree.
        return [
            TargetRef.obj(oid)
            for oid in resolve_pool(ctx, {**dict(spec.selector), "zone": "exile"})
            if can_be_targeted(state, controller, oid, source_oid=source_oid)
        ]

    if spec.kind == "any":
        refs: list[TargetRef] = [
            TargetRef.obj(oid)
            for oid in resolve_pool(ctx, {**dict(spec.selector), "zone": "battlefield"})
            if can_be_targeted(state, controller, oid, source_oid=source_oid)
        ]
        # The player half of "any target" is filtered by the same clause the
        # `kind: "player"` branch uses, and has to be: `still_legal` re-checks a
        # player ref through `_player_allowed` whatever the spec's kind, so a
        # seat offered here and refused there would be an action a player can
        # take that then fizzles on resolution. No shipped card writes a
        # `controller` clause on an `any` spec, so today this changes nothing --
        # it is the two halves agreeing rather than a new restriction.
        refs.extend(
            TargetRef.player(pid) for pid in state.alive() if _player_allowed(ctx, pid, spec)
        )
        return refs

    pool = resolve_pool(ctx, spec.selector)
    return [
        TargetRef.obj(oid)
        for oid in pool
        if can_be_targeted(state, controller, oid, source_oid=source_oid)
    ]


def _ability_matches(ctx: EffectContext, item: StackItem, spec: TargetSpec) -> bool:
    """Does one **ability** on the stack satisfy its target spec's `selector`?

    Deliberately narrow, and the narrowness is the point. `_spell_matches` below
    reads types, colours, subtypes and mana value off a printed face; an ability
    on the stack has no face (113.7a) and only a source, an index and its
    bindings. Reusing that matcher would silently answer about the *source
    permanent* instead, so "target activated ability you control" would come to
    mean "target ability of a creature you control" the moment anybody wrote a
    `types` clause -- the same class of silently-inert selector `_spell_matches`
    was itself written to stop.

    So exactly two clauses are honoured, the two this family of printed cards
    carries: ``controller`` -- "an ability **you control**" (Peter Parker's
    Camera, Lithoform Engine, Strionic Resonator) -- and ``ability_kind`` --
    "target **triggered** ability" (Strionic Resonator, Mister Fantastic),
    read off `StackItem.ability_kind`, which is recorded as the ability goes on
    the stack. Guessing it from `bindings` would be wrong, since an activated
    ability's cost writes bindings too (`costs.bind_paid_object`). The loader
    refuses every other key on such a spec, so a clause that cannot be
    answered here is a load error rather than a restriction the card does not
    have. Both `candidates` and `still_legal` ask this, so an ability that no
    longer matches on resolution is an illegal target there too.
    """
    selector = dict(spec.selector)
    who = selector.get("controller")
    if who == "you" and item.controller != ctx.controller:
        return False
    if who == "opponent" and item.controller == ctx.controller:
        return False
    wanted = selector.get("ability_kind")
    return wanted is None or item.ability_kind == wanted


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


def _player_allowed(ctx: EffectContext, pid: int, spec: TargetSpec) -> bool:
    """May this seat be chosen for a ``kind: "player"`` (or ``"any"``) spec?

    The whole of player-target legality, and it used to read exactly one key in
    exactly three ways: ``"you"``, ``"opponent"``, and a ``return True``
    fallthrough for everything else.  The fallthrough was the bug.
    `selectors.validate_selector` has always accepted a **Mapping** here --
    `matches` honours one on the object side, scoping "creatures **they**
    control" to one seat -- so ``{"controller": {"controller_of": "subject"}}``
    compiled cleanly, was dropped on the floor, and left a card that reads
    "target player other than its controller" playing as "target any player".
    A strictly wider card than the printed one, with nothing anywhere to say so.

    So the clause is a full **player spec** now, resolved by the same
    `select_players` every effect's ``player`` key uses -- which is where the
    negated form lives (``{"not": {...}}``) and why this function needs a
    context rather than a bare controller: ``controller_of``, ``owner_of`` and
    ``binding`` all read `ctx.bindings`.

    ``"any"`` is answered before `select_players` sees it, because it is a
    *target* word rather than a player spec: `select_players` has no name for
    "everyone including the dead-but-not-yet" and would raise on it.  The two
    surviving strings are left to `select_players` rather than compared here,
    so the one definition of "opponent" serves both -- at a pod that is three
    seats, and this function is asked about one at a time.

    Both `candidates` and `still_legal` come through here, so the clause is
    honoured when the targets are declared *and* re-checked as the ability
    resolves (608.2b) -- which matters for a spec that names a player off a
    binding, since control of the bound permanent can change in between.
    """
    # Protection over a *seat* (702.16b), checked before the controller clause
    # and not after: it stops **anyone** targeting, its own controller included,
    # so folding it in beside a "you"/"opponent" test would let a protected
    # player still be the target of their own spell. The object side draws the
    # same line, in `can_be_targeted`, and for the same reason.
    if player_protected_from(ctx.state, pid, ctx.source_oid):
        return False
    # Hexproof over a seat (702.11d): only an opponent of that player is
    # stopped, so the check reads who controls the spell or ability.
    if ctx.controller in ctx.state.opponents(pid) and player_has_hexproof(ctx.state, pid):
        return False
    clause = spec.selector.get("controller", "any")
    if clause == "any":
        return True
    return pid in select_players(ctx, clause)


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
    if oid not in state.objects:
        return False
    return target_refusal(state, controller, oid, source_oid=source_oid) is None


def target_refusal(
    state: GameState, controller: int, oid: int, *, source_oid: int | None = None
) -> str | None:
    """Why ``controller`` may not target ``oid`` from ``source_oid`` at all, or None.

    The half of target legality that is about the *object* rather than the
    spell: hexproof, shroud and protection refuse it whatever the target line
    says. `can_be_targeted` is this function's ``is None``, so the reason a
    player is shown and the rule the engine applies cannot drift apart.

    The other half -- "target creature" does not reach a land -- is the spec's,
    and has no single reason to give; the client says it from the printed text.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return None
    if protected_from(state, oid, source_oid):
        qualities = sorted(protection_from(state, oid))
        return f"Protection from {' and '.join(qualities)}" if qualities else "Protection"
    keywords = chars(state, oid).keywords
    if Keyword.SHROUD.value in keywords:
        return "Shroud"
    if obj.controller != controller and Keyword.HEXPROOF.value in keywords:
        return "Hexproof"
    return None


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
    for. There is nothing on the object to read there, so
    `loader.targets._compile_targets` refuses a value-expression count on a
    card's own `targets` outright rather than letting it quietly evaluate to
    zero -- except the two counts 601.2b has already announced: X
    (`TargetSpec.x_sized`) and the times the additional cost is paid
    (`TargetSpec.additional_sized`), which each cast line substitutes through
    `additional_sized_targets` before it gets here.
    """
    if isinstance(spec.count, int) or spec.count == "any":
        return spec.count
    ctx = EffectContext(state=state, controller=controller, source_oid=source_oid)
    return max(0, evaluate_value(ctx, spec.count))


def _names_a_sibling(node: Any, ids: set[str]) -> bool:
    """Does this selector name one of ``ids`` as a target?

    "…up to one target creature **they** control" is
    ``{"controller": {"target": "t1"}}``, and that clause is the whole of what
    makes the second spec depend on the first. Walked rather than read off one
    key, because a player spec may sit anywhere a selector accepts one --
    inside `any_of`, inside a nested `objects`.
    """
    if isinstance(node, Mapping):
        if isinstance(node.get("target"), str) and node["target"] in ids:
            return True
        return any(_names_a_sibling(v, ids) for v in node.values())
    if isinstance(node, Sequence) and not isinstance(node, str):
        return any(_names_a_sibling(v, ids) for v in node)
    return False



def _within_total(
    state: GameState, refs: Sequence[TargetRef], cap: int | None
) -> bool:
    """Do these picks add up to ``cap`` or less? -- "with **total** mana value 6
    or less" (Phoenix, Warden of Fire).

    A constraint **between** the picks, which is why it lives here and not in
    the selector: every selector clause is evaluated against one candidate in
    isolation, so `mana_value: {"op": "<=", "value": 6}` says "each of these
    costs six or less" and is a far wider card -- six one-drops pass it and are
    six mana of creatures.

    The same slot `one_per_player` occupies, and for the same reason: both are
    facts about a *set* of chosen objects rather than about any one of them.

    Read off the printed cost, which is what a card in a graveyard has: nothing
    is applying to it, and `mana_value()` with no X is the number the card
    prints (202.3b -- an X in a mana cost is 0 anywhere but on the stack).

    Not re-checked on resolution. 608.2b asks whether each target is *still
    legal* one at a time; the total was a condition on the choice, and a spell
    whose targets have partly gone does not have its arithmetic redone.
    """
    if cap is None:
        return True
    total = 0
    for ref in refs:
        if ref.kind != "object":
            continue
        obj = state.objects.get(ref.id)
        if obj is None:
            continue
        total += state.card_of(obj).mana_value
    return total <= cap

def _spec_options(
    state: GameState,
    controller: int,
    spec: TargetSpec,
    source_oid: int | None,
    *,
    exclude_sid: int | None,
    limit: int,
    bindings: Mapping[str, Any] | None,
    chosen: Mapping[str, Sequence[TargetRef]] | None,
    size_cap: int | None = None,
    x: int = 0,
) -> list[tuple[TargetRef, ...]]:
    """Every choice one spec offers, including declining where that is allowed.

    An empty list means this spec cannot be satisfied at all, which kills the
    partial combination it was asked for.
    """
    options = candidates(
        state,
        controller,
        spec,
        source_oid,
        exclude_sid=exclude_sid,
        bindings=bindings,
        chosen=chosen,
        x=x,
    )
    # Declining comes *last*, and that is load-bearing rather than cosmetic:
    # whatever picks a tuple without asking -- an AI seat, a trigger resolving
    # on its own -- takes the first, and a Shipbreaker Kraken whose "tap up to
    # four target creatures" defaulted to tapping none would be a different
    # card.
    empty: list[tuple[TargetRef, ...]] = [()] if spec.optional else []
    count = target_count(state, controller, spec, source_oid)
    if count == "any" or spec.up_to:
        # "Any number of target creatures", and "up to X target creature
        # cards". A size the caster picks, so every subset up to the ceiling is
        # a legal choice -- ordered **largest first**, for the reason above:
        # whatever takes a tuple without asking takes the first, and "any
        # number" defaulting to none is a spell that does nothing. The empty
        # subset comes last and always exists, because both readings include
        # zero whether or not the spec is `optional`.
        #
        # The two differ only in where the ceiling comes from: "any number" has
        # none beyond the board, and "up to X" is capped by the value -- which
        # is the whole of the difference between Marshal's Anthem cast with no
        # kicks and a {2}{W}{W} full-graveyard reanimation.
        ceiling = len(options) if count == "any" else min(int(count), len(options))
        if size_cap is not None:
            ceiling = min(ceiling, size_cap)
        # "One, two, or three target creature cards" (Aberrant Return): a floor
        # under the ceiling, so neither the empty subset nor any smaller one is
        # a choice -- and with fewer legal targets than the floor the spec
        # cannot be satisfied at all, which is 601.2c's "can't be cast".
        floor = spec.min_count
        tail: list[tuple[TargetRef, ...]] = [] if floor else [()]
        if ceiling < floor:
            return []
        # Lazily, and stopped at the limit: every subset of a 38-permanent
        # board is 2**38 of them, and Deepglow Skate's "any number of target
        # permanents" -- any controller, any type -- asked for exactly that
        # list before slicing it, which hung the verifier. Same order, same
        # filters; it just never builds what it is about to throw away.
        subsets = itertools.islice(
            (
                tuple(c)
                for size in range(ceiling, max(floor, 1) - 1, -1)
                for c in itertools.combinations(options, size)
                if (not spec.one_per_player or _one_each(state, c))
                and _within_total(state, c, spec.total_mana_value)
            ),
            _room(limit, tail),
        )
        return list(dict.fromkeys([*subsets, *tail]))
    if count <= 0:
        # A computed count of zero -- "one target for each time this was
        # kicked", kicked no times. Not the same as no legal choice: the ability
        # asks for nothing and resolves, where an empty list would say it cannot
        # be put on the stack at all.
        return [()]
    if count > 1:
        combos = [
            tuple(c)
            for c in itertools.combinations(options, min(count, len(options)))
            if _within_total(state, c, spec.total_mana_value)
        ]
        if not combos and not spec.optional:
            return []
        # `combinations(x, 0)` is `[()]`, so an optional spec with nothing to
        # choose would otherwise offer the empty choice twice -- and two
        # identical actions is the very thing this list must not produce. The
        # cap eats candidates, never the choice to decline -- but it never eats
        # the last candidate either: `stack.push_trigger` and `suspend` ask with
        # `limit=1` and take `options[0]`, so trading the one real choice for
        # "no targets" would silently fizzle every triggered ability with an
        # optional target.
        return list(dict.fromkeys(combos[: _room(limit, empty)] + empty))
    if not options and not spec.optional:
        return []
    return [(o,) for o in options][: _room(limit, empty)] + empty


def enumerate_target_tuples(
    state: GameState,
    controller: int,
    specs: Sequence[TargetSpec],
    source_oid: int | None,
    *,
    exclude_sid: int | None = None,
    limit: int | None = None,
    bindings: Mapping[str, Any] | None = None,
    size_cap: int | None = None,
    x: int = 0,
    defer: TargetSpec | None = None,
) -> list[tuple[TargetRef, ...]]:
    """Every legal combination of targets, capped at ``limit``.

    ``defer`` is a spec this enumeration leaves **empty**, because the cast
    asks for it instead -- `casting.deferred_target_spec` says which, and
    `Game._ask_deferred_targets` asks. "Any number of target nonland
    permanents you control" is every subset of a board, and with the cap below
    a six-permanent Clever Concealment offered eleven of its sixty-three: the
    set the player wanted was usually not on the list at all.

    With no ``limit`` given, ``MAX_TARGET_OPTIONS`` -- except for one spec
    asking for one target, which is uncapped. The cap is there for the
    combinations, and one target has none: the list is one entry per legal
    object, so cutting it only hides legal targets. Generous Gift's "target
    permanent" offered the first twelve permanents on the battlefield, so a
    Sphinx of Uthuun thirteenth in line could never be chosen.

    ``size_cap`` bounds how many refs a **variable-size** spec may take -- the
    most targets a strive spell can pay for. It has to bound the enumeration
    rather than filter its result: subsets come largest first and ``limit``
    cuts the list, so with five creatures on the board the twelve options kept
    are all four- and five-target picks, and filtering those for an affordable
    size afterwards would leave nothing but the empty one.

    Returns ``[()]`` for a spell with no targets and ``[]`` when a required
    target has no legal choice (i.e. the spell cannot be cast at all).

    An ``optional`` spec always contributes the empty choice, whether or not it
    has candidates.  It used to contribute one only when there were none, which
    made declining impossible the moment anything legal was on the battlefield
    -- so Simic Charm's "permanents you control gain hexproof" mode, whose
    target is optional, could not be reached in any game with a creature in it.

    **A spec may name a sibling.** "Choose target opponent and up to one target
    creature **they** control" (Cloak and Dagger, Entwined) is one selector
    reading another spec's answer, and 601.2c is why it can: every target is
    chosen at once, so what is legal is the *pair*. The combinations are
    therefore grown one spec at a time rather than multiplied at the end, and a
    linked spec is enumerated **per partial combination** -- against the
    opponent that branch actually picked, rather than against a spec with no
    answer yet, which offers nothing at all.

    Only a linked spec pays for that. An independent one is enumerated once and
    reused across every partial, which is what the old product did and is the
    shape of every card in the pool but this one.

    A partial whose next required spec has nothing legal is dropped -- 601.2c
    read the other way round: a target you cannot complete is not a legal choice
    of the ones before it. With no linked spec in sight that is exactly the old
    "return []", since every partial saw the same options and so dies together.
    """
    if not specs:
        return [()]
    if limit is None:
        single = len(specs) == 1 and target_count(state, controller, specs[0], source_oid) == 1
        limit = sys.maxsize if single else MAX_TARGET_OPTIONS

    prior: set[str] = set()
    partials: list[
        tuple[dict[str, tuple[TargetRef, ...]], tuple[TargetRef, ...]]
    ] = [({}, ())]
    for spec in specs:
        linked = bool(prior) and _names_a_sibling(spec.selector, prior)
        # A deferred spec with a floor is still a 601.2c condition on the line:
        # "one, two, or three target creature cards" with none in any graveyard
        # is a spell that cannot be cast, so the line is offered only while the
        # floor can be met by objects the earlier specs have not taken.
        floor_pool = (
            candidates(state, controller, spec, source_oid, exclude_sid=exclude_sid,
                       bindings=bindings, x=x)
            if spec is defer and spec.min_count
            else None
        )
        shared = (
            [()]
            if spec is defer
            else None
            if linked
            else _spec_options(
                state,
                controller,
                spec,
                source_oid,
                exclude_sid=exclude_sid,
                limit=limit,
                bindings=bindings,
                chosen=None,
                size_cap=size_cap,
                x=x,
            )
        )
        grown: list[
            tuple[dict[str, tuple[TargetRef, ...]], tuple[TargetRef, ...]]
        ] = []
        for chosen, flat in partials:
            options = (
                shared
                if shared is not None
                else _spec_options(
                    state,
                    controller,
                    spec,
                    source_oid,
                    exclude_sid=exclude_sid,
                    limit=limit,
                    bindings=bindings,
                    chosen=chosen,
                    size_cap=size_cap,
                    x=x,
                )
            )
            if floor_pool is not None and (
                sum(1 for ref in floor_pool if ref not in flat) < spec.min_count
            ):
                continue
            for option in options:
                if set(option) & set(flat):
                    continue  # the same object cannot fill two targets
                grown.append(({**chosen, spec.id: option}, flat + option))
            if len(grown) >= limit:
                break
        partials = grown
        if not partials:
            return []
        prior.add(spec.id)

    return [flat for _, flat in partials][:limit]


def selectable_modes(
    state: GameState, controller: int, card, source_oid: int | None
) -> list[int] | None:
    """Which modes 601.2b lets this spell choose from, or ``None`` for "all".

    "You can't choose a mode that would be illegal" -- and a mode whose target
    has no legal choice is exactly that.  A Call Damage Control cast with only
    creature cards in the graveyard offers one bullet, not four, and offering
    the other three would be three ways to spend a mode on nothing.

    ``None`` rather than ``range(...)`` for a card with no mode-owned targets,
    so the caller can tell "every mode, as always" from "these three" without
    the loader having to know how many modes a card prints.
    """
    if not getattr(card, "mode_targets", None):
        return None
    modal = card.cast_time_modes
    total = len(modal.get("modes") or ()) if modal else 0
    return [
        index
        for index in range(total)
        if enumerate_target_tuples(
            state, controller, card.mode_targets.get(index, ()), source_oid, limit=1
        )
    ]


def still_legal(
    state: GameState,
    controller: int,
    spec: TargetSpec,
    ref: TargetRef,
    source_oid: int | None,
    *,
    bindings: Mapping[str, Any] | None = None,
    chosen: Mapping[str, Sequence[TargetRef]] | None = None,
    x: int = 0,
) -> bool:
    """Re-check a chosen target as the spell or ability resolves.

    ``chosen`` is the sibling targets, for a spec that names one: 608.2b asks
    "is this still a creature **that player** controls", and the player is the
    other target. `filter_legal` accumulates the buckets as it goes and hands
    over the ones already settled, which is the same order they were declared
    in.

    ``x`` is the value that was actually **paid**, carried on the `StackItem`.
    608.2b re-checks the target against the same question 601.2c asked, and for
    "with mana value X" that question has an X in it -- re-checked at 0 the
    Mycosynth Gardens would fizzle every time it was paid for.
    """
    ctx = EffectContext(
        state=state,
        controller=controller,
        source_oid=source_oid,
        bindings=dict(bindings or {}),
        targets={k: tuple(v) for k, v in (chosen or {}).items()},
        x=x,
    )
    if ref.kind == "player":
        return state.is_alive(ref.id) and _player_allowed(ctx, ref.id, spec)
    if ref.kind == "stack":
        item = state.stack_item(ref.id)
        if item is None:
            return False
        if spec.kind == "ability_on_stack":
            # 608.2b re-checks every target as the copy resolves, and for an
            # ability the whole of legality is that it is still an ability on the
            # stack and still the right controller's. An ability that has already
            # resolved is gone from `state.stack`, so `stack_item` returning None
            # above is the fizzle -- which is the printed behaviour: a Camera
            # activation whose target ability resolved first does nothing.
            return not item.is_spell and _ability_matches(ctx, item, spec)
        if not item.is_spell:
            return False
        # 608.2b re-checks every target as the spell resolves, and the selector
        # is half of what makes a target legal. Without this an Essence Scatter
        # held against a creature spell would still counter it after the spell
        # stopped being a creature spell.
        return _spell_matches(ctx, item, spec)
    obj = state.objects.get(ref.id)
    if obj is None:
        return False
    if not can_be_targeted(state, controller, ref.id, source_oid=source_oid):
        return False
    if spec.kind == "card_in_graveyard":
        return obj.zone is Zone.GRAVEYARD
    if spec.kind == "card_in_exile":
        # The zone **and** the selector, where `card_in_graveyard` above checks
        # only the zone. Re-resolved rather than matched, because the clause
        # this kind exists for is a *binding* -- "exiled this way" -- and
        # `matches` has no answer for one: a binding names a pool rather than
        # describing an object, so it is `resolve_pool` that knows. Running the
        # same call `candidates` runs also makes the two agree by construction,
        # which is the property that keeps a target from being offered here and
        # refused there. The difference is what the two kinds are used for: a
        # graveyard spec names a card by its printed face, which cannot change
        # while it lies there, and an exile spec names one by where it came from
        # -- "…a creature card **exiled this way**" -- which is a binding, and a
        # binding is exactly the sort of clause 608.2b exists to re-ask.
        return obj.zone is Zone.EXILE and ref.id in resolve_pool(
            ctx, {**dict(spec.selector), "zone": "exile"}
        )
    if spec.kind == "spell_or_permanent":
        # An object ref is the permanent half, re-checked against the selector
        # that half was offered from -- `candidates` reads the same accessor.
        return matches(ctx, ref.id, {**dict(spec.permanent_half), "zone": "battlefield"})
    selector = dict(spec.selector)
    if spec.kind == "any" and "zone" not in selector:
        selector["zone"] = "battlefield"
    return matches(ctx, ref.id, selector)


def declared_by_spec(
    specs: Sequence[TargetSpec], refs: Sequence[TargetRef]
) -> dict[str, tuple[TargetRef, ...]]:
    """The stored refs split per spec, with no legality check.

    `filter_legal`'s positional split without the 608.2b re-check -- for a
    question asked the moment the targets are declared, when every one of them
    is legal by construction. `game.Game._ask_distribution` reads it.
    """
    out: dict[str, tuple[TargetRef, ...]] = {}
    index = 0
    for spec in specs:
        take = len(refs) - index if spec.variable_size else max(1, spec.count)
        out[spec.id] = tuple(refs[index : index + take])
        index += take
    return out


def filter_legal(
    state: GameState,
    controller: int,
    specs: Sequence[TargetSpec],
    refs: Sequence[TargetRef],
    source_oid: int | None,
    *,
    bindings: Mapping[str, Any] | None = None,
    x: int = 0,
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
        # The buckets settled so far, for a spec whose selector names a sibling
        # -- "up to one target creature **they** control". The declaration order
        # is the spec order, so by the time a linked spec is re-checked the
        # target it depends on is already in `buckets`, dropped or not.
        settled = {k: tuple(v) for k, v in buckets.items()}
        kept = [
            r
            for r in chunk
            if still_legal(
                state,
                controller,
                spec,
                r,
                source_oid,
                bindings=bindings,
                chosen=settled,
                x=x,
            )
        ]
        if chunk:
            had_targets = True
        buckets[spec.id] = kept
    remains = any(bool(v) for v in buckets.values())
    return {k: tuple(v) for k, v in buckets.items()}, (remains or not had_targets)


def kicked_targets(specs):
    """The same target specs with their kicked counts in place, or ``None``.

    "If this spell was kicked, **instead choose any number of** target creatures
    you own" -- The Eagles Are Coming!. Legal at 601.2c because kicker is
    announced one step earlier at 601.2b, so the choice is already made when the
    targets are declared; payment (601.2h) is later and is not what this reads.

    ``None`` when no spec carries a `count_if_kicked`, which is every card but the
    handful printing that clause -- the caller then uses the specs it already had,
    so an ordinary kicker card costs nothing and behaves exactly as before.

    **Both the declaration and the resolution have to call this**, and that is the
    whole reason it lives here rather than in `casting`. `casting._cast_actions`
    enumerates the kicked line's targets from these specs, and
    `stack._resolve_spell` splits the stored refs back into per-spec buckets with
    `filter_legal`, which reads `TargetSpec.variable_size` -- false for the
    printed `count: 1`. Substituted in only one of the two places, a kicked
    Eagles stores two refs and then buckets one, so the card silently ships as
    its small half. Bestow's own note in `_resolve_spell` makes the same point
    for the same reason: the two ends must agree about what the specs are.

    `dataclasses.replace` rather than mutation, because the specs hang off the
    CardDef and are shared by every cast line and every future cast of every copy
    of the card.
    """

    if not any(spec.count_if_kicked is not None for spec in specs):
        return None
    return tuple(
        spec if spec.count_if_kicked is None else replace(spec, count=spec.count_if_kicked)
        for spec in specs
    )


def additional_sized_targets(specs, times: int):
    """The same target specs with ``times`` as every additional-sized count.

    "As an additional cost to cast this spell, sacrifice X creatures. Destroy
    X target nonland permanents." -- Immoral Bargain. 601.2b announces how many
    times the additional cost is paid, one step before 601.2c declares the
    targets, so each cast line already knows the number and declares exactly
    that many: sacrificing two offers two targets, sacrificing none offers none.

    Returns the specs unchanged when none is `TargetSpec.additional_sized`,
    which is every card but the handful printing the clause.

    Only the **declaration** substitutes. `stack._resolve_spell` keeps the
    printed expression, which is `TargetSpec.variable_size`, so `filter_legal`
    hands the last spec every remaining ref -- the number the line declared,
    and the number a copy keeps (707.10) without the copy having paid anything.
    The loader keeps such a spec last for exactly that split.

    `dataclasses.replace` for `kicked_targets`' reason: the specs are shared by
    every line and every copy of the card.
    """
    if not any(spec.additional_sized for spec in specs):
        return specs
    return tuple(
        replace(spec, count=max(0, int(times))) if spec.additional_sized else spec
        for spec in specs
    )


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
