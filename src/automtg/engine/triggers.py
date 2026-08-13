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
    "becomes_monstrous": EventType.BECAME_MONSTROUS,
    "counter_placed": EventType.COUNTER_PLACED,
    "creature_dies": EventType.DIES,
    "draw": EventType.DRAW,
    "discard": EventType.DISCARD,
    "cycle": EventType.CYCLED,
    #: Enrage (702.131): "Whenever this creature is dealt damage, …".  No new
    #: event -- `DAMAGE_DEALT` has always been fired through the trigger bus and
    #: nothing subscribed to it.  Sugar in the same sense `creature_dies` is:
    #: the event covers damage to players as well, and this half of it is the
    #: half with an object to hang a trigger on.
    "dealt_damage": EventType.DAMAGE_DEALT,
    #: Heroic (702.109) and ward (702.21): "whenever this becomes the target of
    #: a spell…".  Fired as the spell goes on the stack (603.2d), which is the
    #: timing that makes ward mean anything.
    "becomes_target": EventType.BECAME_TARGET,
    #: Flanking (702.25), rampage (702.23), bushido (702.45) and frenzy
    #: (702.35), which between them are every combat keyword the engine had no
    #: event for. Both fire when blockers are declared, because that is the
    #: instant either becomes knowable.
    "becomes_blocked": EventType.BECAME_BLOCKED,
    "attacks_unblocked": EventType.ATTACKED_UNBLOCKED,
    #: Inspired (702.117): "Whenever this creature becomes untapped, …". The
    #: event existed; what did not was the untap *step* saying which permanents
    #: it untapped, which is where inspired fires nearly every time.
    "becomes_untapped": EventType.UNTAPPED,
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
        "becomes_monstrous",
        # The cycled card itself, so `source: "self"` scopes the trigger to the
        # card that was cycled rather than to every cycling anywhere.
        "cycle",
        # The discarded card, so a filter may ask what it was -- "whenever an
        # opponent discards a *creature* card". It is in the graveyard by the
        # time the event fires and `matches_card_filter` reads the printed face,
        # so the subject is still there to be asked about.
        "discard",
        # The permanent that was dealt the damage, not the source dealing it:
        # enrage is a fact about the creature being hurt, and `source: "self"`
        # has to scope it to that creature rather than to everything it hits.
        "dealt_damage",
        # The permanent that was targeted, for the same reason: `source: "self"`
        # on heroic means "a spell targeting *me*", and the event's `source` is
        # the spell doing the targeting.
        "becomes_target",
        # The attacker. Both of these are told from the attacking creature's
        # side -- `blocks` already covers the blocker's -- so `source: "self"`
        # scopes them to the creature that was, or was not, blocked.
        "becomes_blocked",
        "attacks_unblocked",
        # The permanent that untapped.
        "becomes_untapped",
    }
)

#: Triggers that keep working while their source is in the graveyard, because the
#: source has just left the battlefield.
#:
#: ``cycle`` is deliberately absent. This set drives one special path, keyed on
#: DIES/LEAVES_BATTLEFIELD, for an object no zone list holds any more. A cycled
#: card *is* in a zone list -- the graveyard, which `_candidate_abilities`
#: already walks -- so it is found by declaring `active_zones: ["graveyard"]`
#: like any other graveyard trigger.
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
    doubled = _land_trigger_doublers(state, event)
    for obj, ability in _candidate_abilities(state, event):
        spec = ability.trigger
        if spec is None:
            continue
        if not _matches(state, obj, spec, event):
            continue
        _queue(state, obj, ability, event)
        if obj.controller in doubled:
            # Ancient Greenwarden: "that ability triggers an additional time".
            # Queued twice rather than resolved twice, because the two copies are
            # separate abilities on the stack and anything in between -- another
            # landfall trigger, a response -- goes between them.
            _queue(state, obj, ability, event)


def _land_trigger_doublers(state: GameState, event: GameEvent) -> frozenset[int]:
    """Players whose triggers this event should fire twice for.

    Only lands entering, which is what the one card that does this says. A
    general "double every trigger" would be a different and much larger claim.
    """
    if event.type is not EventType.ENTERS_BATTLEFIELD:
        return frozenset()
    entered = state.objects.get(event.data.get("oid"))
    if entered is None or "Land" not in state.card_of(entered).types:
        return frozenset()

    out: set[int] = set()
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        for ability in state.card_of(obj).abilities:
            if ability.is_static and (ability.static or {}).get("effect") == "double_land_triggers":
                out.add(obj.controller)
    return frozenset(out)


def _candidate_abilities(state: GameState, event: GameEvent):
    """Every (object, triggered ability) pair that could be listening.

    Objects on the battlefield are always scanned.  Abilities that declare extra
    ``active_zones`` (Edgar Markov's eminence, which works from the command zone)
    are scanned there too.  Finally, an object that has just left the battlefield
    is scanned for its own leave-triggers using last-known information.
    """
    seen: set[int] = set()

    def emit_from(obj: GameObject, zone: Zone):
        if obj.face_down and zone is Zone.BATTLEFIELD:
            # A face-down permanent has no abilities (707.2), so the hidden
            # card's triggers do not listen. Checked here rather than at each
            # trigger, because this is the one place that walks a card's
            # abilities on behalf of an object.
            return
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
        # Abilities granted by something else. Yielded with `obj` as the source,
        # so "whenever *this creature* deals combat damage" means the creature
        # that was granted the ability, not the permanent that granted it.
        from .primitives import granted_abilities

        for _granter, ability in granted_abilities(state, oid):
            if ability.is_triggered and ability.trigger is not None:
                yield obj, ability

    # The stack, for "When you cast this spell, …" -- an ability that fires
    # while its own card is the spell being cast, and is therefore never on the
    # battlefield when it matters. Scanned separately because the stack is not a
    # player zone: it is shared, ordered, and holds the spell under its own
    # trigger.
    for item in list(state.stack):
        if item.oid is None or item.oid in seen:
            continue
        obj = state.objects.get(item.oid)
        if obj is None:
            continue
        seen.add(item.oid)
        yield from emit_from(obj, Zone.STACK)

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

    if spec.event == "dealt_damage":
        # `DAMAGE_DEALT` covers both shapes and says which it is. Damage to a
        # player has no permanent for the trigger to be about, and `player` on
        # that event is the one being hit rather than a controller, so letting
        # it through would fire every enrage on the board off a Lightning Bolt
        # to the face.
        if event.data.get("to") != "permanent":
            return False
        # `source: "self"` here means *this creature was dealt damage*, never
        # "this creature dealt it". The generic check above accepts either,
        # because for most events the subject and the source are the same
        # object -- for this one they are the victim and the attacker, so a
        # bear would trigger its own enrage every time it hit something.
        if spec.source == "self" and subject_oid != obj.oid:
            return False

    # "…if it wasn't put onto the battlefield with this ability." The loop guard,
    # and it has to be checked here rather than as a condition, because by the
    # time the ability resolves the cause is no longer anywhere to be read.
    if spec.not_cause is not None and event.data.get("cause") == spec.not_cause:
        return False

    # "Whenever a +1/+1 counter is put on this creature". `add_counters` has
    # always put the kind on the event and nothing read it, so an unfiltered
    # trigger fires on charge and slumber counters too -- both of which the
    # shipped pool places.
    if spec.counter is not None and event.data.get("counter") != spec.counter:
        return False

    actor = _actor(state, spec.event, event, subject_oid)
    if actor is not None:
        if spec.controller == "you" and actor != obj.controller:
            return False
        if spec.controller == "opponent" and actor == obj.controller:
            return False

    if spec.defending is not None and not _defender_matches(spec.defending, obj, event):
        return False

    if spec.filter is not None:
        if subject_oid is None:
            return False
        if not matches_card_filter(state, subject_oid, spec.filter, obj):
            return False

    if spec.condition is not None:
        from .effects.conditions import evaluate_condition

        if not evaluate_condition(
            state,
            spec.condition,
            controller=obj.controller,
            source=obj.oid,
            bindings=event_bindings(obj, spec, event),
        ):
            return False

    return True


def event_bindings(obj: GameObject, spec: TriggerSpec, event: GameEvent) -> dict[str, Any]:
    """What the event carried, for a condition or a queued trigger to read.

    Shared by `_matches` and `_queue` so an intervening-if and the ability it
    gates cannot disagree about what "that creature" means. They used to: the
    condition was evaluated with no bindings at all, so evolve's comparison
    against the creature that entered read zero and the ability never fired --
    quietly, and only for the conditions that ask about the event rather than
    about the board.
    """
    bindings: dict[str, Any] = {
        "self": obj.oid,
        "event_player": event.player,
        "event_type": event.type,
        "x": obj.cast_x,
    }
    subject = _subject_oid(spec.event, event)
    if subject is not None:
        bindings["subject"] = subject
    for key in EVENT_BINDING_KEYS:
        if key in event.data:
            bindings[key] = event.data[key]
    return bindings


#: Event payload keys carried into a trigger's bindings.
EVENT_BINDING_KEYS = (
    "amount",
    "damage",
    "life",
    "sid",
    "defender",
    "was_attacking",
    "counter",
    "blockers",
    # Persist and undying: what was on the creature before it died, which
    # nothing can read off the object afterwards.
    "had_counters",
)


def _defender_matches(clause: str, obj: GameObject, event: GameEvent) -> bool:
    """Whether the player being attacked is the one the trigger asks about.

    ``defender`` is already on the ``attacks`` event -- combat records which
    player each attacker was declared against -- so this is a filter rather than
    new bookkeeping.  It exists because ``controller`` cannot answer the
    question: "whenever a creature attacks you" is about the *defending* player,
    and a two-player game hides the difference that a pod makes obvious.
    """
    defender = event.data.get("defender")
    if defender is None:
        return False
    if clause == "you":
        return int(defender) == obj.controller
    if clause == "opponent":
        return int(defender) != obj.controller
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
    # `discard` is listed here even though it also has an object subject. The
    # clause asks *who discarded*, and the discarded card is in a graveyard by
    # now -- reading the actor off the object would be reading a controller that
    # `reset_permanent_state` has already been through. `discard_cards` puts the
    # discarding player on the event, so take it from there.
    # `becomes_target` is listed here for the same reason `discard` is, and it
    # matters more: the clause asks *whose spell it is*. Heroic is "whenever you
    # cast a spell that targets this creature" and ward is "whenever an opponent
    # casts one", so reading the actor off the subject -- the creature being
    # targeted, whose controller is nearly always the trigger's own controller
    # -- would make heroic fire on everything and ward on nothing.
    if dsl_event in ("land_played", "spell_cast", "upkeep", "draw_step", "end_step", "you_gain_life", "draw", "discard", "begin_combat", "becomes_target"):
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

    # "…a creature spell of the chosen type." The same substitution the static
    # filters do, because Vanquisher's Banner asks the question from both.
    from .characteristics import resolve_chosen_subtypes

    filt = resolve_chosen_subtypes(filt, ability_source)

    if filt.get("exclude_self") and oid == ability_source.oid:
        return False
    if filt.get("self_only") and oid != ability_source.oid:
        return False

    # "Whenever a creature dealt damage by this creature this turn dies…"
    # Sengir Vampire. A relationship rather than a characteristic, so it is
    # answered from the per-turn ledger on the state rather than from the card
    # face -- and it has to be, because the subject has already died and
    # anything stored on it is gone.
    # "When the creature this card haunts dies…" -- the mirror of the clause
    # below, and answered off the *ability source* rather than off the subject:
    # the haunted creature has just died and carries no record of who was
    # haunting it, while the haunting card is sitting in exile with the link.
    haunted_by = filt.get("haunted_by")
    if haunted_by is not None and (
        haunted_by != "self" or ability_source.haunting != oid
    ):
        return False

    # "Whenever the creature this card is encoded on deals combat damage…" --
    # cipher, and the same shape as `haunted_by` one line up: answered off the
    # ability source, which is the card sitting in exile with the link.
    encoded_by = filt.get("encoded_by")
    if encoded_by is not None and (
        encoded_by != "self" or ability_source.encoded_on != oid
    ):
        return False

    damaged_by = filt.get("damaged_by")
    if damaged_by is not None:
        who = ability_source.oid if damaged_by == "self" else damaged_by
        if who not in state.damage_ledger.get(oid, ()):
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


def _granter_of(state: GameState, obj: GameObject, ability: Ability) -> int | None:
    """Which permanent granted ``obj`` this ability, if any.

    Identity, not equality: two grants of the same ability are the same object
    here, and that is fine -- resolution only needs somewhere to look the
    definition up.
    """
    from .primitives import granted_abilities

    for granter, granted in granted_abilities(state, obj.oid):
        if granted is ability:
            return granter.oid
    return None


def _queue(state: GameState, obj: GameObject, ability: Ability, event: GameEvent) -> None:
    state.triggers_this_step += 1
    if state.triggers_this_step > MAX_TRIGGERS_PER_STEP:
        raise RulesLoopError(
            f"more than {MAX_TRIGGERS_PER_STEP} triggers in one step "
            f"(last: {state.card_of(obj).name})"
        )
    spec = ability.trigger
    assert spec is not None
    # The same bindings the intervening-if was evaluated against, so a
    # condition and the ability it gates cannot read "that creature"
    # differently. `x` is carried through so "enters with X counters" can read
    # what was paid.
    bindings = event_bindings(obj, spec, event)

    card = state.card_of(obj)
    state.pending_triggers.append(
        TriggerInstance(
            source_oid=obj.oid,
            ability_index=ability.index,
            controller=obj.controller,
            bindings=bindings,
            description=f"{card.name}: {ability.text or spec.event}",
            granted_by=_granter_of(state, obj, ability),
        )
    )
    state.emit(
        EventType.ABILITY_TRIGGERED,
        player=obj.controller,
        source=obj.oid,
        # The client names the source from this; without it every trigger in
        # the log and the effects layer read "An ability triggers", which is
        # the least useful sentence available in a format made of triggers.
        card=card.id,
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
