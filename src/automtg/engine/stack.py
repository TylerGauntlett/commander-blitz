"""The stack: putting spells and abilities on it, and resolving them.

Resolution is a generator so an effect can pause mid-resolution to ask its
controller a question ("sacrifice a creature", "choose a mode") without the
engine needing continuations or state snapshots.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import TYPE_CHECKING, Any

from .carddef import BESTOW_TARGET, MUTATE_TARGET, Ability, CardDef, rules_ability
from .effects import execute
from .effects.conditions import evaluate
from .effects.context import EffectContext
from .enums import Zone
from .events import EventType
from .primitives import attach
from .structs import StackItem, TargetRef, TriggerInstance
from .targeting import filter_legal
from .zones import move_object

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def push_spell(
    state: GameState,
    oid: int,
    controller: int,
    targets: Sequence[TargetRef] = (),
    *,
    x: int = 0,
    kicked: bool = False,
    evoked: bool = False,
    flashback: bool = False,
    overloaded: bool = False,
    spliced: tuple[str, ...] = (),
    face_down: bool = False,
    second_face: bool = False,
    fused: bool = False,
    bestowed: bool = False,
    mutated: bool = False,
    modes: tuple[int, ...] = (),
    modes_answered: bool = False,
) -> StackItem:
    """Move a card from hand (or the command zone) onto the stack as a spell."""
    obj = state.objects[oid]
    card = state.card_of(obj)

    # Removed by hand rather than via move_object: a spell going on the stack must
    # not fire leave-the-zone triggers or reset the state we are about to set.
    source_list = state.players[obj.owner].zone_list(obj.zone)
    if oid in source_list:
        source_list.remove(oid)
    # Rebound reads this on resolution, and this is the only moment it is
    # knowable: by then the card is on the stack and every spell looks alike.
    obj.cast_from_hand = obj.zone is Zone.HAND
    # Addendum (Ravnica Allegiance): "if you cast this spell during your main
    # phase". Stamped here, with `cast_from_hand`, because this is the moment
    # the sentence is about and the only moment it is knowable -- the spell can
    # be cast in a main phase and resolve after a response has carried the game
    # into combat, so a phase read at resolution answers a different question.
    # Both halves are recorded: which step, and whether the caster was the
    # active player, because "your main phase" is both.
    obj.cast_step = state.step
    obj.cast_on_own_turn = state.active_player == controller
    # Bestow (702.103a). Recorded on the object as well as the stack item,
    # because it outlives the spell: it is what makes the resolved permanent an
    # Aura, and `chars` asks the object rather than the stack.
    obj.cast_bestowed = bestowed
    # A second castable face -- an Adventure, an Aftermath half, one half of a
    # split card. Set before `card_of` is asked anything, for the reason
    # disturb's transform below is: everything from here on names the card, and
    # a spell that showed one face on the stack and another wherever it landed
    # would be two different cards to everyone watching.
    if second_face and card.second_face is not None:
        obj.showing_second_face = True
        card = state.card_of(obj)
    # Disturb: the card is cast **transformed**, so it is the back face from
    # here on -- name, types and effects included. Set before `card_of` is asked
    # anything, since a spell that showed its front face on the stack and its
    # back face on the battlefield would be two different cards.
    if flashback and card.graveyard_cast_transformed and card.back_face:
        obj.transformed = True
        obj.cast_transformed = True
        # Re-read: everything below names the card, and a spell that showed its
        # front face on the stack and its back face on the battlefield would be
        # two different cards to everyone watching.
        card = state.card_of(obj)
    obj.zone = Zone.STACK
    obj.controller = controller

    item = StackItem(
        sid=state.alloc_sid(),
        kind="spell",
        controller=controller,
        def_id=card.id,
        oid=oid,
        targets=tuple(targets),
        x=x,
        kicked=kicked,
        evoked=evoked,
        fused=fused,
        bestowed=bestowed,
        mutated=mutated,
        flashback=flashback,
        overloaded=overloaded,
        spliced=spliced,
        face_down=face_down,
        modes=modes,
        modes_answered=modes_answered,
        description="a face-down creature" if face_down else card.name,
    )
    obj.stack_id = item.sid
    state.stack.append(item)
    state.bump_chars()
    announce_targets(state, item)
    return item


def announce_targets(state: GameState, item: StackItem) -> None:
    """Fire `BECAME_TARGET` for everything this stack item targets.

    Rule 603.2d: "becomes the target of" triggers fire as the spell or ability
    is *put on the stack*, not as it resolves. That timing is the whole of ward
    -- the point is to make the opponent pay before the removal spell does
    anything -- and it is why this is here rather than in `resolve`.

    Called from all three push sites, so nothing that reaches the stack with
    targets can miss it. `push_triggered_ability` chooses its targets after
    building the item, so it calls this itself once they are set.
    """
    from .triggers import fire

    source = item.oid if item.is_spell else item.source_oid
    for ref in item.targets:
        if ref.kind == "object":
            target = state.objects.get(ref.id)
            fire(
                state,
                EventType.BECAME_TARGET,
                # The caster. See `EventType.BECAME_TARGET`.
                player=item.controller,
                source=source,
                oid=ref.id,
                # The card *being targeted*, not the spell doing it: the log
                # line is "Alice targets Test Warded", and the spell already
                # named itself on the cast line above.
                card=state.card_of(target).id if target is not None else None,
                sid=item.sid,
                is_spell=1 if item.is_spell else 0,
            )
        elif ref.kind == "player":
            # No object, so no permanent's trigger can be about it -- but the
            # event is still worth logging, and a future "whenever you become
            # the target" reads the same shape.
            fire(
                state,
                EventType.BECAME_TARGET,
                player=item.controller,
                source=source,
                target_player=ref.id,
                sid=item.sid,
                is_spell=1 if item.is_spell else 0,
            )


def pull_spell_off_stack(
    state: GameState,
    sid: int,
    to_zone: Zone,
    *,
    cause: str = "",
    by: int | None = None,
) -> StackItem | None:
    """Take a spell off the stack **without countering it**, and move its card.

    The counterpart of :func:`push_spell`, and deliberately not a counter.
    Countering is one specific action (701.5a) with three observable
    consequences the rules attach to it and to nothing else: it is stopped by
    "this spell can't be countered", it puts the card into its owner's
    graveyard, and it is the thing "whenever a spell is countered" watches.
    "Return target spell to its owner's hand" (Reprieve) shares none of them --
    it is a plain zone change of the card the spell is, so an uncounterable
    spell is returned like any other and nothing that watches for a countered
    spell sees anything happen.

    ``to_zone`` is a parameter rather than a constant because *where the card
    goes* is the only thing that varies between the effects that do this;
    everything above it -- unlinking the object, forgetting the face it was cast
    as, and a copy ceasing to exist -- is the same however far it travels.

    Returns the removed :class:`StackItem`, or ``None`` when that ``sid`` is not
    a spell on the stack any more. That is not an error: targets are re-checked
    on resolution (608.2b), and a spell that has already left is simply no
    longer there to move.
    """
    item = state.stack_item(sid)
    if item is None or not item.is_spell:
        return None
    state.stack = [it for it in state.stack if it.sid != sid]
    obj = state.objects.get(item.oid) if item.oid is not None else None
    if obj is None:
        return item
    obj.stack_id = None
    # It has stopped being a spell, so it stops showing the face it was cast as
    # -- 715.3c and 702.127b exile an Adventure or a disturbed face *as it
    # resolves*, and this one never did.
    obj.showing_second_face = False
    if obj.is_token:
        # Rule 706.10: a copy of a spell is not a card, so there is no card to
        # put anywhere -- 704.5e removes it the moment it is no longer on the
        # stack. Bouncing a storm copy therefore puts nothing into anybody's
        # hand, and moving it to `to_zone` first would emit a zone change
        # saying a card arrived there, which is a card the owner never had.
        # Removed here rather than left to the token state-based action, which
        # deliberately exempts the stack (see `sba`) and so would never see it.
        state.objects.pop(obj.oid, None)
        state.bump_chars()
        return item
    move_object(state, obj.oid, to_zone, to_player=obj.owner, cause=cause, by=by)
    return item


def push_activated_ability(
    state: GameState,
    source_oid: int,
    ability_index: int,
    controller: int,
    targets: Sequence[TargetRef] = (),
    *,
    x: int = 0,
    modes: tuple[int, ...] = (),
    modes_answered: bool = False,
) -> StackItem:
    card = state.card(source_oid)
    ability = card.abilities[ability_index]
    item = StackItem(
        sid=state.alloc_sid(),
        kind="ability",
        controller=controller,
        def_id=card.id,
        source_oid=source_oid,
        ability_index=ability_index,
        targets=tuple(targets),
        x=x,
        modes=modes,
        modes_answered=modes_answered,
        description=f"{card.name}: {ability.text or 'activated ability'}",
    )
    state.stack.append(item)
    announce_targets(state, item)
    return item


def ability_of(state: GameState, item_or_trig) -> Ability | None:
    """The ability a stack item or pending trigger refers to.

    A *granted* ability does not live on the card of the permanent that has it
    -- it lives in the granter's ``grantable_abilities`` -- so the lookup has to
    ask where it came from. One helper, because getting this wrong in one of the
    two places would resolve the wrong ability entirely.
    """
    index = item_or_trig.ability_index
    if index is None:
        return None
    # A **negative** index is an ability the rules supplied rather than one any
    # card prints -- every ward, cloak's included. Answered first and without
    # reading the board, which is the property that makes granted ward hold: by
    # the time the trigger resolves the static that granted it may be gone, and
    # a lookup that asked "who has ward right now" would fizzle exactly when the
    # opponent killed the granter in response. Resolved by index off
    # `card.abilities` it would instead run whatever that card prints first --
    # a different ability on a different object, and silently so.
    if index < 0:
        return rules_ability(index)
    granted_by = getattr(item_or_trig, "granted_by", None)
    if granted_by is not None:
        granter = state.objects.get(granted_by)
        if granter is None:
            return None
        pool = state.card_of(granter).grantable_abilities
    else:
        source = state.objects.get(item_or_trig.source_oid)
        if source is not None:
            pool = state.card_of(source).abilities
        else:
            # A token that paid for its own ability by sacrificing itself is
            # *gone*: the token state-based action pops it out of
            # `state.objects` rather than moving it to a graveyard, so unlike
            # every other self-sacrificing permanent there is no object left to
            # read the ability off. `_resolve_ability` already says resolution
            # outlives the source; this is the one place that contradicted it.
            # Without the fallback every "{cost}, Sacrifice this token: ..."
            # ability -- a Clue's whole text -- resolves as a silent no-op.
            def_id = getattr(item_or_trig, "def_id", None)
            if def_id is None or def_id not in state.registry:
                return None
            pool = state.registry.get(def_id).abilities
    return pool[index] if index < len(pool) else None


def push_triggered_ability(
    state: GameState, trig: TriggerInstance
) -> Generator[Any, list[int], StackItem]:
    """Put one triggered ability on the stack, asking for its targets.

    Rule 603.3d: the controller chooses the targets **as the ability is put on
    the stack**, not as it resolves. This used to take `options[0]` off a
    `limit=1` enumeration, which is not a weaker choice but a fixed one -- and
    for a `kind: "player"` target the enumeration order is `state.alive()`, so
    the ability always named seat 0. Bojuka Bog exiled its own controller's
    graveyard in every game it was ever played in, and nothing on the board
    said so, because the ability did resolve and did exile a graveyard.

    A generator, so the choice can become a real decision. That is why
    `drain_to_stack` is one too, and why `_advance` drives it through `_run`.
    """
    obj = state.objects.get(trig.source_oid)
    # The trigger's own snapshot first: a token that triggers on its own death
    # is out of `state.objects` by now, and `"?"` is not a card id -- it reaches
    # `state.registry.get` in `_resolve_ability` and raises.
    def_id = obj.def_id if obj else (trig.def_id or "?")
    item = StackItem(
        sid=state.alloc_sid(),
        kind="ability",
        controller=trig.controller,
        def_id=def_id,
        source_oid=trig.source_oid,
        ability_index=trig.ability_index,
        bindings=dict(trig.bindings),
        x=int(trig.bindings.get("x", 0) or 0),
        description=trig.description,
        granted_by=trig.granted_by,
    )
    ability = ability_of(state, item)
    if ability is not None and ability.targets:
        item.targets = yield from _choose_trigger_targets(state, trig, ability)
    state.stack.append(item)
    announce_targets(state, item)
    return item


def _choose_trigger_targets(
    state: GameState, trig: TriggerInstance, ability: Ability
) -> Generator[Any, list[int], tuple[TargetRef, ...]]:
    """Ask the trigger's controller which of the legal target tuples it takes.

    Enumerated at the ordinary cap, the same one casting uses -- a trigger is
    not entitled to fewer choices than a spell with the same targeting line.

    Nothing is asked when there is one option or none, which is most triggers:
    "when this dies, it deals damage to *its controller*" has one legal tuple
    and asking would be a decision with a single button.
    """
    from .actions import DecisionOption, PendingDecision
    from .enums import DecisionKind
    from .targeting import describe_ref, enumerate_target_tuples

    options = enumerate_target_tuples(
        state, trig.controller, ability.targets, trig.source_oid
    )
    if not options:
        return ()
    if len(options) == 1:
        return options[0]
    decision = PendingDecision(
        kind=DecisionKind.CHOOSE_OBJECTS,
        player=trig.controller,
        prompt=f"Choose targets for {trig.description}" if trig.description else "Choose targets",
        options=tuple(
            DecisionOption(
                label=", ".join(describe_ref(state, ref) for ref in combo) or "no targets",
                ref=combo[0] if len(combo) == 1 else None,
                value=index,
            )
            for index, combo in enumerate(options)
        ),
        min_count=1,
        max_count=1,
        context={"source": trig.source_oid, "source_name": trig.description},
    )
    answer = yield decision
    # An empty answer is not "decline": the targets are not optional at this
    # level -- `enumerate_target_tuples` already folded any optional spec in as
    # its own tuple. Falling back to the first keeps a seat that answers
    # nothing from silently fizzling its own trigger.
    return options[answer[0]] if answer else options[0]


def modal_cast_ok(state: GameState, pid: int, card, oid: int) -> bool:
    """Can this spell choose as many modes as it is required to? -- 601.2b.

    "Choose one -- * Target artifact card; * Target creature card" with an
    empty graveyard has no legal mode, and a spell that cannot choose its modes
    cannot be cast at all.  Asked by `legality._cast_variant` so the line is
    never offered, rather than left to fail inside the cast: an action a player
    can take and that then does nothing is the shape this whole capability
    exists to remove.

    Always ``True`` for a card with no mode-owned targets -- every mode of an
    ordinary modal spell is always choosable, which is why nothing asked this
    before.
    """
    if not getattr(card, "mode_targets", None):
        return True
    from .effects.context import EffectContext
    from .effects.ops_control import modal_bounds
    from .targeting import selectable_modes

    spec = card.cast_time_modes
    if not spec:  # pragma: no cover - the loader refuses `mode` without one
        return True
    ctx = EffectContext(state=state, controller=pid, source_oid=oid, source_name=card.name)
    floor, _ = modal_bounds(ctx, spec)
    return len(selectable_modes(state, pid, card, oid) or []) >= floor


def free_cast_modes(
    state: GameState, pid: int, card, oid: int
) -> tuple[tuple[int, ...], tuple[TargetRef, ...]]:
    """Modes and their targets for a spell nobody is being asked about.

    Cascade, suspend and "cast it without paying its mana cost" put a spell on
    the stack from inside another effect, with no decision loop of their own to
    hang 601.2b on -- and both callers already record the same simplification
    for targets: take the first legal tuple.  Modes get that rule too, so a
    cascaded modal spell resolves having chosen something rather than nothing.

    "The first legal modes up to the floor" is deliberately the *floor* and not
    the ceiling: an unasked seat should take what the card makes it take, and
    "choose up to two" cast for free chooses none, exactly as declining is the
    last option in :func:`targeting.enumerate_target_tuples`'s optional list.

    Returns ``((), ())`` for the ordinary case -- a card with no mode-owned
    targets, whose modes are answered by `op_choose_mode` on resolution as they
    always were.
    """
    from .effects.context import EffectContext
    from .effects.ops_control import modal_bounds
    from .targeting import enumerate_target_tuples, selectable_modes

    if not getattr(card, "mode_targets", None):
        return (), ()
    spec = card.cast_time_modes
    if not spec:  # pragma: no cover - the loader refuses `mode` without one
        return (), ()
    ctx = EffectContext(state=state, controller=pid, source_oid=oid, source_name=card.name)
    floor, _ = modal_bounds(ctx, spec)
    offered = selectable_modes(state, pid, card, oid) or []
    modes = tuple(offered[:floor])
    refs: list[TargetRef] = []
    for index in modes:
        options = enumerate_target_tuples(
            state, pid, card.mode_targets.get(index, ()), oid, limit=1
        )
        refs.extend(options[0] if options else ())
    return modes, tuple(refs)


def resolve_top(state: GameState) -> Generator[Any, list[int], None]:
    """Resolve the top object of the stack.  Yields decisions its effects need."""
    if not state.stack:
        return
    item = state.stack.pop()
    if item.is_spell:
        yield from _resolve_spell(state, item)
    else:
        yield from _resolve_ability(state, item)


def _resolve_spell(state: GameState, item: StackItem) -> Generator[Any, list[int], None]:
    assert item.oid is not None
    obj = state.objects.get(item.oid)
    if obj is None:
        return
    card = state.card_of(obj)

    # Bestow (702.103a) is the one cast variant that changes what the spell
    # targets: the card declares none and the *rule* supplies "enchant
    # creature". Asked here as well as in legality so the two agree about what
    # is still legal -- a bestow spell whose creature died in response is
    # countered on resolution like any Aura spell, which is 608.2b and not a
    # special case at all.
    # Mode-owned specs come back in the same order `Game._ask_mode_targets`
    # declared them, which is what makes `filter_legal`'s positional split line
    # up with the refs the cast stored. For every card without them this is
    # `card.targets` unchanged.
    specs = card.specs_for_modes(item.modes)
    if item.fused and card.second_face is not None:
        # Both halves' targets, in the order legality offered them.
        specs = tuple(card.targets) + tuple(state.registry.get(card.second_face).targets)
    if item.bestowed:
        specs = (BESTOW_TARGET,)
    elif item.mutated:
        specs = (MUTATE_TARGET,)
    targets, any_legal = filter_legal(
        state, item.controller, specs, item.targets, item.oid
    )
    if not any_legal:
        state.emit(
            EventType.SPELL_FIZZLED, player=item.controller, source=item.oid, card=card.id
        )
        obj.stack_id = None
        obj.cast_from_graveyard = item.flashback
        # 715.3c and 702.127b both exile the card **as it resolves**, so a
        # second face that never resolves does not get the rider: an Adventure
        # whose target vanished is a card in the graveyard, not one in exile
        # waiting to be cast for free.
        obj.showing_second_face = False
        # A fizzled spell is still a spell that was cast, so the same rider
        # applies -- and the same exemption: an escape spell whose targets all
        # left is back in the graveyard to be escaped again.
        destination = (
            Zone.EXILE if item.flashback and card.graveyard_cast_exiles else Zone.GRAVEYARD
        )
        move_object(state, item.oid, destination, to_player=obj.owner, cause="fizzled")
        return

    # Set before the effects run, not after: "if this spell was cast from a
    # graveyard, create ten of those tokens instead" is read *during*
    # `spell_effects`, so a flag written afterwards would always read False.
    obj.cast_from_graveyard = item.flashback
    # Same reason, same moment: "destroy each artifact instead of target
    # artifact" is an `if` inside `spell_effects`, so a flag written after them
    # would always read False and every overloaded spell would resolve as the
    # targeted half -- with no targets, which is nothing at all.
    obj.cast_overloaded = item.overloaded
    obj.pending_face_down = item.face_down

    ctx = EffectContext(
        state=state,
        controller=item.controller,
        source_oid=item.oid,
        targets=targets,
        bindings=dict(item.bindings),
        x=item.x,
        kicked=item.kicked,
        modes=item.modes,
        modes_answered=item.modes_answered,
        source_name=card.name if card else item.description,
    )
    yield from execute(ctx, card.spell_effects)
    # "…add this card's effects to that spell." After the host's own, in the
    # order they were spliced on, and through the *same* context -- which is
    # what makes them one spell rather than several, and is why a spliced card
    # may not declare targets of its own.
    for spliced_id in item.spliced:
        yield from execute(ctx, state.registry.get(spliced_id).spell_effects)
    # Fuse (702.102a): the second half's effects, after the first's and through
    # the **same** context -- which is what makes it one spell rather than two,
    # and is exactly the argument splice makes a line above. Countering the
    # fused spell stops all of it.
    if item.fused and card.second_face is not None:
        yield from execute(ctx, state.registry.get(card.second_face).spell_effects)

    if card.epic and not obj.is_token:
        # 702.50a. Recorded on the *player*, one-way and for the rest of the
        # game, like `has_city_s_blessing`: the card is in a graveyard a moment
        # later while the restriction and the copies go on, so there is no
        # object for it to live on.
        #
        # `not obj.is_token` **is** "except for its epic ability". A copy of a
        # spell is a token here, and it resolves through this same function --
        # so without the test each upkeep's copy would re-point `epic_source`
        # at itself, and the copy is removed by a state-based action a moment
        # later, which silently ends the copying after exactly one turn.
        state.players[item.controller].epic_source = item.oid
        state.emit("epic", player=item.controller, source=item.oid, card=card.id)
    state.emit(EventType.SPELL_RESOLVED, player=item.controller, source=item.oid, card=card.id)
    obj.stack_id = None
    obj.cast_x = item.x
    obj.cast_kicked = item.kicked
    obj.cast_evoked = item.evoked
    obj.cast_overloaded = item.overloaded
    # Mutate (702.140b): the spell does not become a permanent of its own, so
    # it never reaches `_place_after_resolution` -- it is merged into the one it
    # targeted instead, and which way round is the caster's choice.
    if item.mutated:
        yield from _merge_mutation(state, item, targets)
        return
    _place_after_resolution(state, obj, card)
    _attach_aura(state, obj, card, targets, specs)


def _merge_mutation(
    state: GameState, item: StackItem, targets
) -> Generator[Any, list[int], None]:
    """Put a mutating creature over or under the permanent it targeted.

    "Over or under" is the caster's, and it is asked *here* rather than as the
    spell is cast because 702.140b puts it at resolution -- and because a choice
    made at cast time would be a choice made before anyone could respond to the
    spell, which is a different card.

    The host is re-read from the filtered targets rather than from the action:
    `filter_legal` has already run above, so a spell whose creature is gone has
    fizzled and never reaches here.
    """
    from .effects.context import EffectContext, ask_yes_no
    from .primitives import merge_permanents

    host_oid = next(
        (
            ref.id
            for ref in targets.get(MUTATE_TARGET.id) or []
            if ref.kind == "object" and ref.id in state.objects
        ),
        None,
    )
    if host_oid is None:  # pragma: no cover - filter_legal proved one is there
        return
    obj = state.objects[item.oid]
    ctx = EffectContext(
        state=state,
        controller=item.controller,
        source_oid=item.oid,
        source_name=state.card_of(obj).name,
    )
    on_top = yield from ask_yes_no(
        ctx,
        f"Put {state.card_of(obj).name} on top of {state.card(host_oid).name}?",
        item.controller,
    )
    merge_permanents(state, host_oid, item.oid, on_top=on_top)


def _place_after_resolution(state: GameState, obj, card: CardDef) -> None:
    """A resolved permanent enters the battlefield; anything else goes to the graveyard.

    The object's zone is still ``STACK``; ``move_object`` handles that case by
    filtering the (already popped) stack list, so no cleanup is needed here.
    """
    destination = Zone.BATTLEFIELD if card.is_permanent else Zone.GRAVEYARD
    # "Then exile it." Flashback and jump-start are once-only, and this is what
    # makes them so: a spell cast from a graveyard goes to exile instead of back
    # to the graveyard it came from. A permanent still enters the battlefield --
    # the rider only replaces the graveyard.
    #
    # **Escape does not.** It is the same alternative cost with the same
    # legality widening, and the one thing that separates it is that the card
    # comes back for another go, so `graveyard_cast_exiles` is the whole
    # difference between the two keywords.
    if obj.cast_from_graveyard and destination is Zone.GRAVEYARD and card.graveyard_cast_exiles:
        destination = Zone.EXILE
    # Buyback: "put it into your hand instead of your graveyard as it
    # resolves". The same shape as the flashback rider pointing the other way,
    # and it only ever replaces the *graveyard* -- a buyback permanent spell
    # still enters the battlefield.
    if card.buyback and obj.cast_kicked and destination is Zone.GRAVEYARD:
        destination = Zone.HAND
    # Rebound (702.87a): "If you cast this spell from your hand, exile it as it
    # resolves." The third rider on the same slot, and like the other two it only
    # ever replaces the *graveyard*.
    #
    # "From your hand" is the loop guard, not flavour: the free cast at the next
    # upkeep happens from **exile**, so without the clause the card would rebound
    # again every upkeep for the rest of the game.
    # Cipher: "exile this spell card encoded on a creature you control". The
    # fourth rider on this slot, and like the others it only ever replaces the
    # *graveyard* -- the encoding is written by the `encode` op during
    # `spell_effects`, which is the only moment a creature is there to name.
    if obj.encoded_on is not None and destination is Zone.GRAVEYARD:
        destination = Zone.EXILE
    rebounds = card.rebound and obj.cast_from_hand and destination is Zone.GRAVEYARD
    if rebounds:
        destination = Zone.EXILE
    # Adventure (715.3c) and aftermath (702.127b): the fifth rider on this slot,
    # and the only one that has to read the **printed** card rather than the one
    # that just resolved -- `card` here is the second face, and the flags that
    # say what happens to it belong to the card as a whole.
    #
    # The two keywords differ in one word afterwards, which `on_adventure`
    # below is: an Adventure may still be cast out of that exile, an Aftermath
    # half is finished with. A split half is neither and keeps the graveyard.
    printed = state.registry.get(obj.def_id)
    adventuring = (
        obj.showing_second_face
        and destination is Zone.GRAVEYARD
        and (printed.adventure or printed.second_face_zone == "graveyard")
    )
    if adventuring:
        destination = Zone.EXILE
    # It stops being a spell here, whatever it turned out to be, so it stops
    # showing the face it was cast as.
    obj.showing_second_face = False
    controller = obj.controller
    move_object(state, obj.oid, destination, to_player=obj.owner, cause="resolved")
    if obj.pending_face_down and destination is Zone.BATTLEFIELD:
        # Morph. Marked after the move for `cast_transformed`'s reason:
        # `reset_permanent_state` clears it on the way onto the battlefield,
        # which is right for every permanent except one arriving face down.
        obj.face_down = True
        obj.pending_face_down = False
        obj.revealed_to.add(obj.controller)
        state.bump_chars()
    if obj.cast_transformed and destination is Zone.BATTLEFIELD:
        # `reset_permanent_state` cleared it on the way in -- 712.13a, "enters
        # front face up" -- which is right for every permanent except this one.
        # Disturb's whole content is that it arrives on the back face.
        obj.transformed = True
        state.bump_chars()
    if rebounds:
        # After the move: `move_object` runs `reset_permanent_state` on the way,
        # which would wipe this if it were set first -- the same ordering
        # `exiled_by` needs.
        obj.rebound_by = controller
    if adventuring and printed.adventure:
        # After the move for `rebound_by`'s reason, and this one really is
        # cleared on the way back: the creature that comes off its adventure
        # onto the battlefield has finished adventuring, which is what
        # `reset_permanent_state` says.
        obj.on_adventure = True
        state.emit("adventure", player=controller, source=obj.oid, card=printed.id)


def _attach_aura(state: GameState, obj, card: CardDef, targets, specs) -> None:
    """An Aura enters attached to what its spell targeted.

    It has to happen *after* the permanent is placed, not during its
    ``spell_effects``: ``move_object`` calls ``reset_permanent_state`` on the way
    onto the battlefield, and that clears ``attached_to``.  An Aura attaching
    itself with the ``attach`` op would therefore arrive enchanting nothing and
    be put into the graveyard by state-based actions a moment later.

    The convention is that an Aura's *first object target* is what it enchants,
    which is exactly how the card is written: "Enchant creature" is the targeting
    clause of the spell.
    """
    # A **bestowed** creature is an Aura the printed card says nothing about, so
    # `is_aura` cannot be the whole test: 702.103a makes it one for as long as it
    # is attached, and the attaching is what this does.
    if not (card.is_aura or obj.cast_bestowed) or not obj.on_battlefield:
        return
    for spec in specs:
        for ref in targets.get(spec.id) or []:
            if ref.kind == "object" and ref.id in state.objects:
                attach(state, obj.oid, ref.id)
                return


def _resolve_ability(state: GameState, item: StackItem) -> Generator[Any, list[int], None]:
    source = state.objects.get(item.source_oid) if item.source_oid is not None else None
    # The ability first, and the card only once there is something to resolve.
    # `ability_of` already copes with a source that is gone -- a token that
    # sacrificed itself to pay for its own ability -- but the card lookup did
    # not: `push_triggered_ability` writes `"?"` when it cannot name the card,
    # and `registry.get("?")` raises rather than returning nothing. So a trigger
    # whose source vanished took the game down instead of resolving to a no-op.
    ability = ability_of(state, item)
    if ability is None:
        return
    card = state.registry.get(item.def_id) if item.def_id in state.registry else None

    targets, any_legal = filter_legal(
        state, item.controller, ability.targets, item.targets, item.source_oid
    )
    if not any_legal:
        state.emit(
            EventType.SPELL_FIZZLED,
            player=item.controller,
            source=item.source_oid,
            card=card.id if card else None,
            ability=item.ability_index,
        )
        return

    ctx = EffectContext(
        state=state,
        controller=item.controller,
        source_oid=item.source_oid,
        targets=targets,
        bindings=dict(item.bindings),
        x=item.x,
        modes=item.modes,
        modes_answered=item.modes_answered,
        source_name=card.name if card else item.description,
    )

    # Intervening-if clauses are checked again on resolution (rule 603.4).
    condition = ability.trigger.condition if ability.trigger is not None else None
    if condition is not None and not evaluate(ctx, condition):
        state.emit(
            EventType.ABILITY_RESOLVED,
            player=item.controller,
            source=item.source_oid,
            card=card.id if card else None,
            ability=item.ability_index,
            skipped="condition",
        )
        return

    del source  # the ability resolves even if its source has left the battlefield
    # Counted here, on the way in, and not in the `ABILITY_RESOLVED` fold: that
    # event is emitted below, after the effects have run, and a card asking "is
    # this the second time this ability has resolved" has to count the one it is
    # in.  Both early returns above are past -- a fizzled trigger and one whose
    # intervening-if failed (603.4) never resolve, so neither may advance it.
    ctx.resolutions = state.turn_ledger.resolving(item.source_oid, item.ability_index)
    yield from execute(ctx, ability.effects)
    state.emit(
        EventType.ABILITY_RESOLVED,
        player=item.controller,
        source=item.source_oid,
        card=card.id if card else None,
        ability=item.ability_index,
    )
