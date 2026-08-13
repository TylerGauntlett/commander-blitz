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
from .enums import Keyword, Zone
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
    by: int | None = None,
) -> GameObject:
    """Move an object to another zone, firing every consequent event.

    ``to_player`` defaults to the object's *owner*, which is where cards always
    go in Commander (a card put into "its owner's graveyard" never lands in
    someone else's).

    ``cause`` says *how* the object moved and ``by`` says *what moved it* -- the
    resolving spell or ability, or the creature that dealt the killing blow.
    Both ride on the ``ZONE_CHANGE`` event and are for the log and the client's
    exit animation, which otherwise cannot say more than that a card vanished.
    Neither is on ``DIES`` or ``LEAVES_BATTLEFIELD``: nothing reads them there,
    and a new key in a *fired* event's data can collide with a card's trigger
    bindings.
    """
    obj = state.objects[oid]
    from_zone = obj.zone
    card = state.card_of(obj)
    owner = obj.owner
    target_player = owner if to_player is None else to_player
    # Resolved now rather than at emit time: a creature that traded in combat is
    # moved in the same state-based-actions pass as the thing it killed, so by
    # the time the event goes out the culprit may itself be out of `objects`.
    # The client needs a card id it can turn into a printed name either way.
    by_card = _card_id_of(state, by)

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
    # Snapshotted for the same reason, and it is the whole of persist and
    # undying: "if it had no -1/-1 counters on it" is asked *about a creature
    # that has just died*, and `reset_permanent_state` empties `counters` on the
    # way out. Read afterwards it is always zero, so both keywords would return
    # every creature for ever.
    had_counters = dict(obj.counters) if was_on_battlefield else {}

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
        **{
            "from": from_zone.value,
            "to": to_zone.value,
            "cause": cause,
            "by": by,
            "by_card": by_card,
        },
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
            had_counters=had_counters,
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
                had_counters=had_counters,
            )

    if to_zone is Zone.BATTLEFIELD:
        _enter_battlefield(state, obj, card, forced_tapped=tapped, cause=cause)

    return obj


def _card_id_of(state: GameState, oid: int | None) -> str | None:
    """The card id behind an oid, or None if there is no such object."""
    if oid is None:
        return None
    obj = state.objects.get(oid)
    return state.card_of(obj).id if obj is not None else None


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
    """Unattach anything attached to a permanent that is leaving, and unpair it.

    Soulbond's link is symmetric, so breaking it is two writes: the leaving
    object's own is cleared by `reset_permanent_state`, and the *partner's* has
    to be cleared here -- nothing else walks back along it, and a creature left
    pointing at a card in a graveyard would keep the bonus for ever.
    """
    for other_id in list(state.battlefield):
        other = state.objects.get(other_id)
        if other is None:
            continue
        if other.attached_to == oid:
            other.attached_to = None
        if other.paired_with == oid:
            other.paired_with = None


def _enter_battlefield(
    state: GameState,
    obj: GameObject,
    card: CardDef,
    *,
    forced_tapped: bool = False,
    cause: str = "",
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
        # How it got here.  Kodama of the East Tree reads "if it wasn't put onto
        # the battlefield with this ability", and without the cause it has no
        # way to tell its own output from anything else's -- it would trigger on
        # the permanent it just put down, and again on that one's, forever.
        cause=cause,
    )


# ----------------------------------------------------------------------
# convenience wrappers
# ----------------------------------------------------------------------


def destroy(state: GameState, oid: int, *, cause: str = "destroyed", by: int | None = None) -> bool:
    """Destroy a permanent unless something replaces the destruction.

    Three things can stop it, and they are three different mechanisms rather
    than one with a parameter:

    | | |
    |---|---|
    | `indestructible` | the destruction simply does not happen |
    | a **regeneration** shield (701.15) | it is tapped, removed from combat and its damage removed, and one shield is spent |
    | **totem armor** (702.88a) | its damage is removed and the *Aura* is destroyed instead |

    Regeneration and totem armor are checked here rather than as `replacements`
    entries because that whitelist is about a permanent *entering the
    battlefield*, and this is the moment one leaves. Everything that destroys --
    the lethal-damage state-based action, the `destroy` op, deathtouch -- already
    routes through this function, which is what makes one check enough.

    Regeneration is checked **before** totem armor: a regenerating creature does
    not leave the battlefield at all, so nothing has happened for the Aura to
    replace. Ordered the other way, a Rancor-style shield would be eaten by a
    creature that was going to survive anyway.

    Returns True only if the permanent actually died.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    if "indestructible" in chars(state, oid).keywords:
        return False
    if obj.regeneration_shields > 0:
        obj.regeneration_shields -= 1
        # 701.15a in order: tap it, remove it from combat, remove all damage.
        obj.tapped = True
        if state.combat is not None:
            state.combat.remove(oid)
        obj.damage = 0
        obj.deathtouched = False
        state.bump_chars()
        state.emit("regenerated", player=obj.controller, source=by, oid=oid)
        return False
    if (shield := _totem_armor(state, oid)) is not None:
        obj.damage = 0
        obj.deathtouched = False
        state.emit("totem_armor", player=obj.controller, source=by, oid=oid, aura=shield)
        # The Aura is *destroyed*, not sacrificed, so it goes through this same
        # function -- which is how an indestructible totem-armour Aura keeps
        # protecting, and how a second Aura on the same creature is not spent.
        destroy(state, shield, cause="totem_armor", by=by)
        return False
    move_object(state, oid, Zone.GRAVEYARD, cause=cause, by=by)
    return True


def _totem_armor(state: GameState, oid: int) -> int | None:
    """An Aura attached to ``oid`` whose controller printed totem armor, if any.

    Read off *derived* keywords, so an Aura granted totem armor by something
    else counts -- the same rule every other keyword check in the engine
    follows.
    """
    for other in state.battlefield:
        aura = state.objects.get(other)
        if aura is None or aura.attached_to != oid:
            continue
        if Keyword.TOTEM_ARMOR.value in chars(state, other).keywords:
            return other
    return None


def sacrifice(state: GameState, oid: int, *, by: int | None = None) -> bool:
    """Sacrifice ignores indestructible."""
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    move_object(state, oid, Zone.GRAVEYARD, cause="sacrificed", by=by)
    return True


def exile(state: GameState, oid: int, *, cause: str = "exiled", by: int | None = None) -> bool:
    obj = state.objects.get(oid)
    if obj is None:
        return False
    move_object(state, oid, Zone.EXILE, cause=cause, by=by)
    return True


def bounce(state: GameState, oid: int, *, by: int | None = None) -> bool:
    """Return a permanent to its owner's hand."""
    obj = state.objects.get(oid)
    if obj is None:
        return False
    move_object(state, oid, Zone.HAND, cause="returned", by=by)
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
