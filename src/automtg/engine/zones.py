"""Zone changes -- the one place objects move between zones.

Everything that removes a card from one zone and puts it in another goes through
:func:`move_object`, so enters/leaves/dies triggers, permanent-state resetting,
the commander zone-change replacement and characteristic-cache invalidation all
happen in exactly one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .carddef import CardDef
from .characteristics import chars
from .enums import Zone
from .events import EventType
from .objects import GameObject
from .triggers import fire

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState

#: Zones a commander may be redirected to the command zone from.
COMMANDER_REPLACED_ZONES = frozenset({Zone.GRAVEYARD, Zone.EXILE, Zone.HAND, Zone.LIBRARY})


def move_object(
    state: GameState,
    oid: int,
    to_zone: Zone,
    *,
    to_player: int | None = None,
    to_top: bool = False,
    tapped: bool = False,
    cause: str = "",
) -> GameObject:
    """Move an object to another zone, firing every consequent event.

    ``to_player`` defaults to the object's *owner*, which is where cards always
    go in Commander (a card put into "its owner's graveyard" never lands in
    someone else's).
    """
    obj = state.objects[oid]
    from_zone = obj.zone
    card = state.card_of(obj)
    owner = obj.owner
    target_player = owner if to_player is None else to_player

    # -- commander zone-change replacement (rule 903.9a) --------------------
    # Simplification: the owner always chooses the command zone.  Documented in
    # docs/rules-coverage.md; it is what a player picks in practice, and it keeps
    # zone changes out of the decision system entirely.
    if obj.is_commander and not obj.is_token and to_zone in COMMANDER_REPLACED_ZONES:
        to_zone = Zone.COMMAND
        target_player = owner
        cause = cause or "commander_replacement"

    was_creature = from_zone is Zone.BATTLEFIELD and "Creature" in chars(state, oid).types
    was_on_battlefield = from_zone is Zone.BATTLEFIELD
    # Snapshotted here for the same reason `was_creature` is: by the time a
    # leaves-battlefield trigger resolves, the object is out of combat and there
    # is nothing left to ask.  This is the engine's explicit-LKI pattern, in the
    # one place a card cannot reach with a `snapshot` op of its own.
    was_attacking = was_on_battlefield and state.combat is not None and state.combat.attacking(oid)

    _remove_from_zone(state, obj)

    if was_on_battlefield:
        _detach_all(state, oid)

    obj.zone = to_zone
    if to_zone is not Zone.BATTLEFIELD or from_zone is not Zone.BATTLEFIELD:
        obj.reset_permanent_state()

    _add_to_zone(state, obj, to_zone, target_player, to_top=to_top)
    state.bump_chars()

    state.emit(
        EventType.ZONE_CHANGE,
        player=owner,
        source=oid,
        oid=oid,
        card=card.id,
        **{"from": from_zone.value, "to": to_zone.value, "cause": cause},
    )

    if was_on_battlefield:
        fire(
            state,
            EventType.LEAVES_BATTLEFIELD,
            player=owner,
            source=oid,
            oid=oid,
            card=card.id,
            was_creature=was_creature,
            # 1/0 rather than a bool, so a card reads it with the ordinary
            # `{"binding": "was_attacking"}` value expression and no new
            # condition vocabulary has to exist for it.
            was_attacking=1 if was_attacking else 0,
        )
        if to_zone is Zone.GRAVEYARD:
            fire(
                state,
                EventType.DIES,
                player=owner,
                source=oid,
                oid=oid,
                card=card.id,
                was_creature=was_creature,
            )

    if to_zone is Zone.BATTLEFIELD:
        _enter_battlefield(state, obj, card, forced_tapped=tapped)

    return obj


def _remove_from_zone(state: GameState, obj: GameObject) -> None:
    if obj.zone is Zone.BATTLEFIELD:
        if obj.oid in state.battlefield:
            state.battlefield.remove(obj.oid)
        combat = state.combat
        if combat is not None:
            combat.remove(obj.oid)
        return
    if obj.zone is Zone.STACK:
        state.stack = [item for item in state.stack if item.oid != obj.oid]
        return
    lst = state.players[obj.owner].zone_list(obj.zone)
    if obj.oid in lst:
        lst.remove(obj.oid)


def _add_to_zone(
    state: GameState, obj: GameObject, zone: Zone, pid: int, *, to_top: bool = False
) -> None:
    if zone is Zone.BATTLEFIELD:
        state.battlefield.append(obj.oid)
        return
    if zone is Zone.STACK:
        # Stack membership is managed by stack.py, which owns the StackItem list.
        return
    lst = state.players[pid].zone_list(zone)
    if to_top and zone is Zone.LIBRARY:
        lst.insert(0, obj.oid)
    else:
        lst.append(obj.oid)


def _detach_all(state: GameState, oid: int) -> None:
    """Unattach anything attached to a permanent that is leaving."""
    for other_id in list(state.battlefield):
        other = state.objects.get(other_id)
        if other is not None and other.attached_to == oid:
            other.attached_to = None


def _enter_battlefield(
    state: GameState, obj: GameObject, card: CardDef, *, forced_tapped: bool = False
) -> None:
    """Apply enter-the-battlefield replacements, then fire the ETB event."""
    obj.entered_turn = state.turn
    obj.tapped = forced_tapped

    for replacement in card.replacements:
        event = replacement.get("event")
        if event == "self_enters_tapped" or (
            event == "self_enters" and replacement.get("modify", {}).get("tapped")
        ):
            obj.tapped = True
        elif event == "self_enters_with_counters" or (
            event == "self_enters" and "counters" in replacement.get("modify", {})
        ):
            # `modify` defaults to `{}` in the schema, so `get("modify", replacement)`
            # returned that empty dict rather than falling back -- and the
            # top-level `counter`/`amount` form was then silently dropped. A card
            # written that way entered with no counters at all and nothing said
            # so, which is the exact failure the DSL's load-time checks exist to
            # prevent. Fall back only when `modify` has nothing in it.
            counters = (replacement.get("modify") or {}).get("counters") or {}
            if counters:
                for kind, amount in counters.items():
                    obj.add_counter(str(kind), int(amount))
            else:
                obj.add_counter(
                    str(replacement.get("counter", "+1/+1")), int(replacement.get("amount", 1))
                )

    state.bump_chars()
    fire(
        state,
        EventType.ENTERS_BATTLEFIELD,
        player=obj.controller,
        source=obj.oid,
        oid=obj.oid,
        card=card.id,
        was_creature="Creature" in card.types,
    )


# ----------------------------------------------------------------------
# convenience wrappers
# ----------------------------------------------------------------------


def destroy(state: GameState, oid: int, *, cause: str = "destroyed") -> bool:
    """Destroy a permanent unless it is indestructible.  Returns True if it died."""
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    if "indestructible" in chars(state, oid).keywords:
        return False
    move_object(state, oid, Zone.GRAVEYARD, cause=cause)
    return True


def sacrifice(state: GameState, oid: int) -> bool:
    """Sacrifice ignores indestructible."""
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    move_object(state, oid, Zone.GRAVEYARD, cause="sacrificed")
    return True


def exile(state: GameState, oid: int, *, cause: str = "exiled") -> bool:
    obj = state.objects.get(oid)
    if obj is None:
        return False
    move_object(state, oid, Zone.EXILE, cause=cause)
    return True


def bounce(state: GameState, oid: int) -> bool:
    """Return a permanent to its owner's hand."""
    obj = state.objects.get(oid)
    if obj is None:
        return False
    move_object(state, oid, Zone.HAND, cause="returned")
    return True


def snapshot(state: GameState, oid: int) -> dict[str, Any]:
    """Capture last-known information about an object.

    The DSL's ``snapshot`` op uses this so a card like Swords to Plowshares can
    read the exiled creature's power *after* it has left the battlefield, without
    the engine needing a general LKI system.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return {}
    c = chars(state, oid)
    card = state.card_of(obj)
    return {
        "oid": oid,
        "def_id": obj.def_id,
        "name": card.name,
        "controller": obj.controller,
        "owner": obj.owner,
        "power": c.power,
        "toughness": c.toughness,
        "mana_value": card.mana_value,
        "types": sorted(c.types),
        "subtypes": sorted(c.subtypes),
        "colors": sorted(c.colors),
    }
