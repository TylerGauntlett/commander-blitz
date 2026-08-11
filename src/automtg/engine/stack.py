"""The stack: putting spells and abilities on it, and resolving them.

Resolution is a generator so an effect can pause mid-resolution to ask its
controller a question ("sacrifice a creature", "choose a mode") without the
engine needing continuations or state snapshots.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from typing import TYPE_CHECKING, Any

from .carddef import Ability, CardDef
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
    modes: tuple[int, ...] = (),
) -> StackItem:
    """Move a card from hand (or the command zone) onto the stack as a spell."""
    obj = state.objects[oid]
    card = state.card_of(obj)

    # Removed by hand rather than via move_object: a spell going on the stack must
    # not fire leave-the-zone triggers or reset the state we are about to set.
    source_list = state.players[obj.owner].zone_list(obj.zone)
    if oid in source_list:
        source_list.remove(oid)
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
        modes=modes,
        description=card.name,
    )
    obj.stack_id = item.sid
    state.stack.append(item)
    state.bump_chars()
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
        description=f"{card.name}: {ability.text or 'activated ability'}",
    )
    state.stack.append(item)
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


def push_triggered_ability(state: GameState, trig: TriggerInstance) -> StackItem:
    obj = state.objects.get(trig.source_oid)
    def_id = obj.def_id if obj else "?"
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
    # A triggered ability with targets chooses them as it goes on the stack.
    ability = ability_of(state, item)
    if ability is not None and ability.targets:
        from .targeting import enumerate_target_tuples

        options = enumerate_target_tuples(
            state, trig.controller, ability.targets, trig.source_oid, limit=1
        )
        item.targets = options[0] if options else ()
    state.stack.append(item)
    return item


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

    targets, any_legal = filter_legal(
        state, item.controller, card.targets, item.targets, item.oid
    )
    if not any_legal:
        state.emit(
            EventType.SPELL_FIZZLED, player=item.controller, source=item.oid, card=card.id
        )
        obj.stack_id = None
        move_object(state, item.oid, Zone.GRAVEYARD, to_player=obj.owner, cause="fizzled")
        return

    ctx = EffectContext(
        state=state,
        controller=item.controller,
        source_oid=item.oid,
        targets=targets,
        bindings=dict(item.bindings),
        x=item.x,
        kicked=item.kicked,
        modes=item.modes,
        source_name=card.name,
    )
    yield from execute(ctx, card.spell_effects)

    state.emit(EventType.SPELL_RESOLVED, player=item.controller, source=item.oid, card=card.id)
    obj.stack_id = None
    obj.cast_x = item.x
    obj.cast_kicked = item.kicked
    obj.cast_evoked = item.evoked
    _place_after_resolution(state, obj, card)
    _attach_aura(state, obj, card, targets)


def _place_after_resolution(state: GameState, obj, card: CardDef) -> None:
    """A resolved permanent enters the battlefield; anything else goes to the graveyard.

    The object's zone is still ``STACK``; ``move_object`` handles that case by
    filtering the (already popped) stack list, so no cleanup is needed here.
    """
    destination = Zone.BATTLEFIELD if card.is_permanent else Zone.GRAVEYARD
    move_object(state, obj.oid, destination, to_player=obj.owner, cause="resolved")


def _attach_aura(state: GameState, obj, card: CardDef, targets) -> None:
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
    if not card.is_aura or not obj.on_battlefield:
        return
    for spec in card.targets:
        for ref in targets.get(spec.id) or []:
            if ref.kind == "object" and ref.id in state.objects:
                attach(state, obj.oid, ref.id)
                return


def _resolve_ability(state: GameState, item: StackItem) -> Generator[Any, list[int], None]:
    source = state.objects.get(item.source_oid) if item.source_oid is not None else None
    card = state.registry.get(item.def_id)
    ability = ability_of(state, item)
    if ability is None:
        return

    targets, any_legal = filter_legal(
        state, item.controller, ability.targets, item.targets, item.source_oid
    )
    if not any_legal:
        state.emit(
            EventType.SPELL_FIZZLED,
            player=item.controller,
            source=item.source_oid,
            card=card.id,
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
        source_name=card.name,
    )

    # Intervening-if clauses are checked again on resolution (rule 603.4).
    condition = ability.trigger.condition if ability.trigger is not None else None
    if condition is not None and not evaluate(ctx, condition):
        state.emit(
            EventType.ABILITY_RESOLVED,
            player=item.controller,
            source=item.source_oid,
            card=card.id,
            ability=item.ability_index,
            skipped="condition",
        )
        return

    del source  # the ability resolves even if its source has left the battlefield
    yield from execute(ctx, ability.effects)
    state.emit(
        EventType.ABILITY_RESOLVED,
        player=item.controller,
        source=item.source_oid,
        card=card.id,
        ability=item.ability_index,
    )
