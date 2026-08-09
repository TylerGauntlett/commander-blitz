"""Low-level mutations shared by the effect ops, combat and the turn machine.

Each function here does exactly one rules-relevant thing and fires the events
that go with it.  Nothing in this module makes decisions or asks questions --
that is the effect layer's job.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from .characteristics import chars
from .enums import Keyword, Zone
from .events import EventType
from .objects import PLUS_ONE, GameObject
from .state import new_object
from .triggers import fire
from .zones import move_object

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


# ----------------------------------------------------------------------
# cards
# ----------------------------------------------------------------------


def draw_cards(state: GameState, pid: int, count: int) -> list[int]:
    """Draw ``count`` cards.  An empty library sets the "will lose" flag (104.3c)."""
    player = state.players[pid]
    drawn: list[int] = []
    for _ in range(max(0, count)):
        if not player.library:
            player.attempted_draw_from_empty = True
            break
        oid = player.library[0]
        move_object(state, oid, Zone.HAND, to_player=pid, cause="draw")
        drawn.append(oid)
        fire(state, EventType.DRAW, player=pid, source=oid, oid=oid)
    return drawn


def discard_cards(state: GameState, pid: int, oids: Sequence[int]) -> list[int]:
    out = []
    for oid in oids:
        obj = state.objects.get(oid)
        if obj is None or obj.zone is not Zone.HAND:
            continue
        move_object(state, oid, Zone.GRAVEYARD, to_player=pid, cause="discard")
        fire(state, EventType.DISCARD, player=pid, source=oid, oid=oid)
        out.append(oid)
    return out


def mill_cards(state: GameState, pid: int, count: int) -> list[int]:
    player = state.players[pid]
    out = []
    for _ in range(max(0, count)):
        if not player.library:
            break
        oid = player.library[0]
        move_object(state, oid, Zone.GRAVEYARD, to_player=pid, cause="mill")
        out.append(oid)
    if out:
        fire(state, EventType.MILL, player=pid, count=len(out))
    return out


def shuffle_library(state: GameState, pid: int) -> None:
    state.rng.shuffle(state.players[pid].library)


# ----------------------------------------------------------------------
# life and damage
# ----------------------------------------------------------------------


def gain_life(state: GameState, pid: int, amount: int, source: int | None = None) -> int:
    if amount <= 0:
        return 0
    state.players[pid].life += amount
    fire(state, EventType.LIFE_GAINED, player=pid, source=source, amount=amount)
    return amount


def lose_life(state: GameState, pid: int, amount: int, source: int | None = None) -> int:
    if amount <= 0:
        return 0
    state.players[pid].life -= amount
    fire(state, EventType.LIFE_LOST, player=pid, source=source, amount=amount)
    return amount


def damage_player(
    state: GameState,
    pid: int,
    amount: int,
    source_oid: int | None,
    *,
    is_combat: bool = False,
) -> int:
    """Deal damage to a player, applying lifelink and commander damage tracking."""
    if amount <= 0:
        return 0
    state.players[pid].life -= amount
    fire(
        state,
        EventType.DAMAGE_DEALT,
        player=pid,
        source=source_oid,
        amount=amount,
        to="player",
        combat=is_combat,
    )
    _apply_lifelink(state, source_oid, amount)

    if is_combat and source_oid is not None:
        src = state.objects.get(source_oid)
        if src is not None:
            if src.is_commander:
                taken = state.players[pid].commander_damage_taken
                taken[src.controller] = taken.get(src.controller, 0) + amount
            fire(
                state,
                EventType.COMBAT_DAMAGE_TO_PLAYER,
                player=pid,
                source=source_oid,
                amount=amount,
                controller=src.controller,
                defender=pid,
            )
    return amount


def damage_permanent(
    state: GameState,
    oid: int,
    amount: int,
    source_oid: int | None,
    *,
    is_combat: bool = False,
) -> int:
    """Mark damage on a permanent.  State-based actions destroy it later."""
    if amount <= 0:
        return 0
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return 0
    obj.damage += amount
    if source_oid is not None and _has(state, source_oid, Keyword.DEATHTOUCH):
        obj.deathtouched = True
    fire(
        state,
        EventType.DAMAGE_DEALT,
        player=obj.controller,
        source=source_oid,
        oid=oid,
        amount=amount,
        to="permanent",
        combat=is_combat,
    )
    _apply_lifelink(state, source_oid, amount)
    return amount


def _apply_lifelink(state: GameState, source_oid: int | None, amount: int) -> None:
    if source_oid is None or amount <= 0:
        return
    src = state.objects.get(source_oid)
    if src is None or not src.on_battlefield:
        return
    if _has(state, source_oid, Keyword.LIFELINK):
        gain_life(state, src.controller, amount, source=source_oid)


def _has(state: GameState, oid: int, keyword: Keyword) -> bool:
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    return keyword.value in chars(state, oid).keywords


# ----------------------------------------------------------------------
# permanents
# ----------------------------------------------------------------------


def tap_permanent(state: GameState, oid: int) -> bool:
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or obj.tapped:
        return False
    obj.tapped = True
    state.bump_chars()
    fire(state, EventType.TAPPED, player=obj.controller, source=oid, oid=oid)
    return True


def untap_permanent(state: GameState, oid: int) -> bool:
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or not obj.tapped:
        return False
    obj.tapped = False
    state.bump_chars()
    fire(state, EventType.UNTAPPED, player=obj.controller, source=oid, oid=oid)
    return True


def add_counters(
    state: GameState, oid: int, kind: str, amount: int, source: int | None = None
) -> int:
    obj = state.objects.get(oid)
    if obj is None or amount == 0:
        return 0
    obj.add_counter(kind, amount)
    state.bump_chars()
    if amount > 0:
        fire(
            state,
            EventType.COUNTER_PLACED,
            player=obj.controller,
            source=source,
            oid=oid,
            counter=kind,
            amount=amount,
        )
    return amount


def remove_counters(state: GameState, oid: int, kind: str, amount: int) -> int:
    obj = state.objects.get(oid)
    if obj is None:
        return 0
    taken = obj.remove_counter(kind, amount)
    if taken:
        state.bump_chars()
        state.emit(EventType.COUNTER_REMOVED, source=oid, counter=kind, amount=taken)
    return taken


def create_token(
    state: GameState,
    def_id: str,
    controller: int,
    count: int = 1,
    *,
    tapped: bool = False,
    attacking: int | None = None,
) -> list[int]:
    """Put ``count`` copies of a token onto the battlefield under ``controller``.

    ``attacking`` is the player the token joins combat against.  A token put onto
    the battlefield attacking was **never declared** as an attacker, so it does
    not trigger anything that fires on attacking -- that is the actual rule, and
    it is also what stops a mobilize token making another mobilize token forever.
    """
    made: list[int] = []
    for _ in range(max(0, count)):
        obj = new_object(
            state, def_id, owner=controller, zone=Zone.EXILE, controller=controller, is_token=True
        )
        # The token is created "nowhere" and then enters the battlefield, so ETB
        # triggers and enters-tapped replacements run through the normal path.
        state.players[controller].exile.append(obj.oid)
        move_object(state, obj.oid, Zone.BATTLEFIELD, tapped=tapped, cause="token")
        if attacking is not None and state.combat is not None:
            state.combat.attackers[obj.oid] = attacking
        state.emit(EventType.TOKEN_CREATED, player=controller, source=obj.oid, card=def_id)
        made.append(obj.oid)
    return made


def attach(state: GameState, aura_oid: int, target_oid: int) -> bool:
    aura = state.objects.get(aura_oid)
    target = state.objects.get(target_oid)
    if aura is None or target is None or not target.on_battlefield:
        return False
    aura.attached_to = target_oid
    state.bump_chars()
    fire(state, EventType.ATTACHED, player=aura.controller, source=aura_oid, oid=target_oid)
    return True


def pump(
    state: GameState, oid: int, power: int, toughness: int, source: int | None = None
) -> None:
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(
        TempEffect(kind="pump", power=power, toughness=toughness, source=source)
    )
    state.bump_chars()


def grant_keyword(state: GameState, oid: int, keyword: str, source: int | None = None) -> None:
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(TempEffect(kind="keyword", keyword=keyword, source=source))
    state.bump_chars()


def clear_until_eot(state: GameState) -> None:
    """Cleanup step: remove damage and every until-end-of-turn effect."""
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        obj.damage = 0
        obj.deathtouched = False
        obj.until_eot.clear()
    state.bump_chars()


def untap_all(state: GameState, pid: int) -> list[int]:
    """Untap step: untap every permanent this player controls."""
    untapped = []
    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is not None and obj.controller == pid and obj.tapped:
            obj.tapped = False
            untapped.append(oid)
    if untapped:
        state.bump_chars()
        state.emit(EventType.UNTAPPED, player=pid, count=len(untapped))
    return untapped


def counters_of(state: GameState, oids: Iterable[int], kind: str = PLUS_ONE) -> int:
    return sum(state.objects[oid].counter(kind) for oid in oids if oid in state.objects)


def controlled_by(state: GameState, oids: Iterable[int], pid: int) -> list[GameObject]:
    return [state.objects[o] for o in oids if o in state.objects and state.objects[o].controller == pid]
