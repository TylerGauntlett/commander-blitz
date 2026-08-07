"""The event bus and triggered-ability matching.

Every mutating primitive calls :func:`fire`, which records a :class:`GameEvent`
and collects any triggered abilities that match it.  Collected triggers wait in
``state.pending_triggers`` and are put on the stack the next time a player would
receive priority, in APNAP order and auto-ordered within a player (a documented
simplification -- real Magic lets the controller choose the order).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .carddef import Ability, TriggerSpec
from .enums import Zone
from .errors import RulesLoopError
from .events import EventType, GameEvent
from .objects import GameObject
from .state import MAX_TRIGGERS_PER_STEP
from .structs import TriggerInstance

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


#: DSL trigger name -> the engine event type it listens for.
TRIGGER_EVENTS: dict[str, str] = {
    "self_enters": EventType.ENTERS_BATTLEFIELD,
    "permanent_enters": EventType.ENTERS_BATTLEFIELD,
    "dies": EventType.DIES,
    "leaves_battlefield": EventType.LEAVES_BATTLEFIELD,
    "land_played": EventType.LAND_PLAYED,
    "spell_cast": EventType.SPELL_CAST,
    "attacks": EventType.ATTACKS,
    "blocks": EventType.BLOCKS,
    "deals_combat_damage_to_player": EventType.COMBAT_DAMAGE_TO_PLAYER,
    "upkeep": EventType.UPKEEP,
    "draw_step": EventType.DRAW_STEP,
    "begin_combat": EventType.BEGIN_COMBAT,
    "end_step": EventType.END_STEP,
    "you_gain_life": EventType.LIFE_GAINED,
    "counter_placed": EventType.COUNTER_PLACED,
    "creature_dies": EventType.DIES,
    "draw": EventType.DRAW,
}

#: Triggers whose subject is an object rather than a player.
OBJECT_SUBJECT_TRIGGERS = frozenset(
    {
        "self_enters",
        "permanent_enters",
        "dies",
        "creature_dies",
        "leaves_battlefield",
        "spell_cast",
        "attacks",
        "blocks",
        "deals_combat_damage_to_player",
        "counter_placed",
        "land_played",
    }
)

#: Triggers that keep working while their source is in the graveyard, because the
#: source has just left the battlefield.
LEAVE_TRIGGERS = frozenset({"dies", "creature_dies", "leaves_battlefield"})


def fire(
    state: GameState,
    event_type: str,
    *,
    player: int | None = None,
    source: int | None = None,
    **data: Any,
) -> GameEvent:
    """Record an event and queue every triggered ability that matches it."""
    event = state.emit(event_type, player=player, source=source, **data)
    collect(state, event)
    return event


def collect(state: GameState, event: GameEvent) -> None:
    """Scan for triggered abilities matching ``event`` and queue them."""
    for obj, ability in _candidate_abilities(state, event):
        spec = ability.trigger
        if spec is None:
            continue
        if not _matches(state, obj, spec, event):
            continue
        _queue(state, obj, ability, event)


def _candidate_abilities(state: GameState, event: GameEvent):
    """Every (object, triggered ability) pair that could be listening.

    Objects on the battlefield are always scanned.  Abilities that declare extra
    ``active_zones`` (Edgar Markov's eminence, which works from the command zone)
    are scanned there too.  Finally, an object that has just left the battlefield
    is scanned for its own leave-triggers using last-known information.
    """
    seen: set[int] = set()

    def emit_from(obj: GameObject, zone: Zone):
        card = state.card_of(obj)
        for ability in card.abilities:
            if not ability.is_triggered or ability.trigger is None:
                continue
            if zone not in ability.active_zones:
                continue
            yield obj, ability

    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        seen.add(oid)
        yield from emit_from(obj, Zone.BATTLEFIELD)

    for p in state.players:
        for zone in (Zone.COMMAND, Zone.GRAVEYARD, Zone.HAND, Zone.EXILE):
            for oid in list(p.zone_list(zone)):
                obj = state.objects.get(oid)
                if obj is None or oid in seen:
                    continue
                yield from emit_from(obj, zone)

    # Leave-the-battlefield triggers on the object that just left.
    subject = event.data.get("oid") if event.type in (EventType.DIES, EventType.LEAVES_BATTLEFIELD) else None
    if subject is not None and subject not in seen:
        obj = state.objects.get(subject)
        if obj is not None:
            card = state.card_of(obj)
            for ability in card.abilities:
                if not ability.is_triggered or ability.trigger is None:
                    continue
                if ability.trigger.event in LEAVE_TRIGGERS and ability.trigger.source == "self":
                    yield obj, ability


def _matches(
    state: GameState, obj: GameObject, spec: TriggerSpec, event: GameEvent
) -> bool:
    expected = TRIGGER_EVENTS.get(spec.event)
    if expected is None or expected != event.type:
        return False

    subject_oid = _subject_oid(spec.event, event)

    if spec.source == "self" and subject_oid != obj.oid and event.source != obj.oid:
        return False

    # "creature_dies" is sugar for a dies trigger filtered to creatures.
    if spec.event == "creature_dies" and not event.data.get("was_creature", False):
        return False

    actor = _actor(state, spec.event, event, subject_oid)
    if actor is not None:
        if spec.controller == "you" and actor != obj.controller:
            return False
        if spec.controller == "opponent" and actor == obj.controller:
            return False

    if spec.filter is not None:
        if subject_oid is None:
            return False
        if not matches_card_filter(state, subject_oid, spec.filter, obj):
            return False

    if spec.condition is not None:
        from .effects.conditions import evaluate_condition

        if not evaluate_condition(state, spec.condition, controller=obj.controller, source=obj.oid):
            return False

    return True


def _subject_oid(dsl_event: str, event: GameEvent) -> int | None:
    if dsl_event not in OBJECT_SUBJECT_TRIGGERS:
        return None
    for key in ("oid", "spell_oid", "attacker", "blocker", "land_oid"):
        value = event.data.get(key)
        if value is not None:
            return int(value)
    return event.source


def _actor(
    state: GameState, dsl_event: str, event: GameEvent, subject_oid: int | None
) -> int | None:
    """The player the ``controller`` clause is compared against."""
    if dsl_event in ("land_played", "spell_cast", "upkeep", "draw_step", "end_step", "you_gain_life", "draw", "begin_combat"):
        return event.player
    if dsl_event == "deals_combat_damage_to_player":
        controller = event.data.get("controller")
        return int(controller) if controller is not None else None
    if subject_oid is not None:
        obj = state.objects.get(subject_oid)
        if obj is not None:
            return obj.controller
        return event.player
    return event.player


def matches_card_filter(
    state: GameState,
    oid: int,
    filt: Mapping[str, Any],
    ability_source: GameObject,
) -> bool:
    """Match a trigger filter against an object's *printed* card characteristics.

    Trigger subjects are frequently gone by the time we look (a creature that
    died, a spell that resolved), so this deliberately reads the card face plus
    the object's last-known controller rather than derived characteristics.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    card = state.card_of(obj)

    if filt.get("exclude_self") and oid == ability_source.oid:
        return False
    if filt.get("self_only") and oid != ability_source.oid:
        return False

    controller = filt.get("controller")
    if controller == "you" and obj.controller != ability_source.controller:
        return False
    if controller == "opponent" and obj.controller == ability_source.controller:
        return False

    types = filt.get("types")
    if types and not set(types).issubset(card.types):
        return False
    not_types = filt.get("not_types")
    if not_types and set(not_types) & card.types:
        return False
    subtypes = filt.get("subtypes")
    if subtypes and not (set(subtypes) & card.subtypes):
        return False
    supertypes = filt.get("supertypes")
    if supertypes and not set(supertypes).issubset(card.supertypes):
        return False
    colors = filt.get("colors")
    if colors and not (set(colors) & card.colors):
        return False
    keywords = filt.get("keywords")
    if keywords and not set(keywords).issubset(card.keywords):
        return False
    if "is_token" in filt and bool(obj.is_token) != bool(filt["is_token"]):
        return False
    if "is_commander" in filt and bool(obj.is_commander) != bool(filt["is_commander"]):
        return False
    mv = filt.get("mana_value")
    if mv is not None and not _compare(card.mana_value, mv):
        return False
    power = filt.get("power")
    if power is not None and not _compare(card.power or 0, power):
        return False
    toughness = filt.get("toughness")
    return not (toughness is not None and not _compare(card.toughness or 0, toughness))


def _compare(value: int, spec: Mapping[str, Any]) -> bool:
    op = spec.get("op", ">=")
    other = spec.get("value", 0)
    if isinstance(other, Mapping):
        other = int(other.get("const", 0))
    if op == ">=":
        return value >= other
    if op == "<=":
        return value <= other
    if op == ">":
        return value > other
    if op == "<":
        return value < other
    return value == other


def _queue(state: GameState, obj: GameObject, ability: Ability, event: GameEvent) -> None:
    state.triggers_this_step += 1
    if state.triggers_this_step > MAX_TRIGGERS_PER_STEP:
        raise RulesLoopError(
            f"more than {MAX_TRIGGERS_PER_STEP} triggers in one step "
            f"(last: {state.card_of(obj).name})"
        )
    spec = ability.trigger
    assert spec is not None
    bindings: dict[str, Any] = {
        "self": obj.oid,
        "event_player": event.player,
        "event_type": event.type,
        # Carried through so "enters with X counters" can read the X that was paid.
        "x": obj.cast_x,
    }
    subject = _subject_oid(spec.event, event)
    if subject is not None:
        bindings["subject"] = subject
    for key in ("amount", "damage", "life", "sid", "defender"):
        if key in event.data:
            bindings[key] = event.data[key]

    card = state.card_of(obj)
    state.pending_triggers.append(
        TriggerInstance(
            source_oid=obj.oid,
            ability_index=ability.index,
            controller=obj.controller,
            bindings=bindings,
            description=f"{card.name}: {ability.text or spec.event}",
        )
    )
    state.emit(
        EventType.ABILITY_TRIGGERED,
        player=obj.controller,
        source=obj.oid,
        ability=ability.index,
        trigger=spec.event,
    )


def drain_to_stack(state: GameState) -> int:
    """Put every pending trigger on the stack in APNAP order.

    Returns how many were put on the stack.  Within a single player's triggers
    the order is the order they were collected (stable and deterministic).
    """
    if not state.pending_triggers:
        return 0
    from .stack import push_triggered_ability

    pending = state.pending_triggers
    state.pending_triggers = []
    count = 0
    for pid in state.turn_order():
        for trig in pending:
            if trig.controller != pid:
                continue
            push_triggered_ability(state, trig)
            count += 1
    # Triggers controlled by players who have left the game simply vanish.
    return count
