"""Low-level mutations shared by the effect ops, combat and the turn machine.

Each function here does exactly one rules-relevant thing and fires the events
that go with it.  Nothing in this module makes decisions or asks questions --
that is the effect layer's job.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

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
        # "…for each card you've drawn this turn." Counted here rather than off
        # the DRAW event, so that every draw counts however it was caused and a
        # card can never be drawn without the tally seeing it.
        state.cards_drawn_this_turn[pid] = state.cards_drawn_this_turn.get(pid, 0) + 1
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
    # Protection prevents the damage entirely -- so nothing is marked, no
    # deathtouch is recorded, and the source's lifelink gains nothing, which is
    # why this returns before all three rather than zeroing `amount` later.
    from .characteristics import protected_from

    if protected_from(state, oid, source_oid):
        state.emit(
            EventType.DAMAGE_PREVENTED,
            player=obj.controller,
            source=source_oid,
            oid=oid,
            amount=amount,
            reason="protection",
        )
        return 0
    obj.damage += amount
    if source_oid is not None:
        # Recorded here rather than on the object: Sengir Vampire asks the
        # question about a creature that has already died, and anything stored
        # on the victim is wiped by `reset_permanent_state` on the way out.
        state.damage_ledger.setdefault(oid, set()).add(source_oid)
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
    overrides: dict[str, Any] | None = None,
) -> list[int]:
    """Put ``count`` copies of a token onto the battlefield under ``controller``.

    ``attacking`` is the player the token joins combat against.  A token put onto
    the battlefield attacking was **never declared** as an attacker, so it does
    not trigger anything that fires on attacking -- that is the actual rule, and
    it is also what stops a mobilize token making another mobilize token forever.

    ``overrides`` is embalm's "except it's a white Zombie Angel with no mana
    cost".  Set *before* the token enters, so its enters-trigger and every
    characteristic read afterwards see the token it actually is.
    """
    made: list[int] = []
    for _ in range(max(0, count)):
        obj = new_object(
            state, def_id, owner=controller, zone=Zone.EXILE, controller=controller, is_token=True
        )
        if overrides:
            obj.copy_overrides = dict(overrides)
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
    from .characteristics import protected_from

    aura = state.objects.get(aura_oid)
    target = state.objects.get(target_oid)
    if aura is None or target is None or not target.on_battlefield:
        return False
    # "Protection from Wizards" cannot be enchanted or equipped by one. The Aura
    # is left where it is; state-based actions bin an Aura attached to nothing.
    if protected_from(state, target_oid, aura_oid):
        return False
    aura.attached_to = target_oid
    state.bump_chars()
    fire(state, EventType.ATTACHED, player=aura.controller, source=aura_oid, oid=target_oid)
    return True


def add_subtypes(state: GameState, oid: int, subtypes: Sequence[str]) -> tuple[str, ...]:
    """"It becomes a Vampire in addition to its other types." Captivating Vampire.

    A one-shot with no duration, written onto the object.  The `add_subtype`
    *static* reads the same in English and is a different mechanism: a static
    applies continuously to whatever currently matches its filter and stops the
    moment its source leaves, while this stays on the one permanent it was
    pointed at until that permanent changes zones.

    "In addition to its other types" is the only reading offered, because it is
    what every printed line of this shape says.  Wholesale type *replacement* is
    what `animate` and the `set_types` static are for.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return ()
    added = tuple(t for t in subtypes if t not in obj.added_subtypes)
    if not added:
        return ()
    obj.added_subtypes = obj.added_subtypes + added
    state.bump_chars()
    return added


def change_control(state: GameState, oid: int, pid: int, source: int | None = None) -> bool:
    """"Gain control of target creature." Rule 800.4a, permanently.

    The object does not move: ``GameObject.controller`` is a field and
    ``state.battlefield`` is one shared list, so the whole change is that field
    plus the three things the rules hang off it.

    - **Rule 302.6.** It has not been under its new controller since their most
      recent turn began, so it is summoning sick.  ``entered_turn`` is what
      ``summoning_sick`` reads, so setting it to the current turn is both the
      record of when control changed and the sickness itself -- a stolen
      creature cannot attack or tap for its new controller this turn.
    - **Rule 506.4.** Changing control removes a permanent from combat.  Without
      this, a creature stolen mid-combat goes on dealing damage for the player
      who no longer controls it.
    - Every static filtered on ``controller`` now reads differently, so the
      characteristics cache has to be dropped.

    Zone destinations are unaffected on purpose: ``move_object`` sends a card to
    its **owner**, so a stolen creature that dies still goes to the graveyard of
    the player who brought it.

    There is deliberately no until-end-of-turn form. That would need a
    continuous-effect layer and a cleanup-step handback, and half of it -- a
    permanent steal wearing Act of Treason's text -- is a strictly better card
    than the printed one.  ``loader`` refuses a ``duration`` key rather than
    ignoring it.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or obj.controller == pid:
        return False
    previous = obj.controller
    obj.controller = pid
    obj.entered_turn = state.turn
    if state.combat is not None:
        state.combat.remove(oid)
    state.bump_chars()
    fire(
        state,
        EventType.CONTROL_CHANGED,
        player=pid,
        source=oid,
        card=obj.def_id,
        by=source,
        **{"from": previous, "to": pid},
    )
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


def animate(
    state: GameState,
    oid: int,
    power: int,
    toughness: int,
    *,
    types: Sequence[str] = ("Creature",),
    subtypes: Sequence[str] = (),
    colors: Sequence[str] = (),
    source: int | None = None,
) -> None:
    """"It becomes a 4/4 Elemental creature until end of turn. It's still a land."

    Stored as an until-end-of-turn effect like a pump, so the cleanup step
    already knows to remove it -- but unlike a pump it replaces the *base* power
    and toughness, which is what lets a +1/+1 counter and an anthem stack on top
    of an animated land the way they do on any other creature.

    Types and subtypes are added rather than replacing what is printed.  Every
    card that says this also says "it's still a land", so the additive reading is
    the ordinary case and there is nothing to opt into.
    """
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(
        TempEffect(
            kind="animate",
            power=power,
            toughness=toughness,
            types=tuple(types),
            subtypes=tuple(subtypes),
            colors=tuple(colors),
            source=source,
        )
    )
    state.bump_chars()


def grant_keyword(state: GameState, oid: int, keyword: str, source: int | None = None) -> None:
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(TempEffect(kind="keyword", keyword=keyword, source=source))
    state.bump_chars()


def grant_ability(state: GameState, oid: int, ability_index: int, source: int) -> None:
    """Hand one of ``source``'s grantable abilities to ``oid`` until end of turn.

    Stored as a pointer -- source oid plus index -- rather than a copy of the
    ability, so there is exactly one definition of what was granted and it stays
    the card file's.
    """
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(
        TempEffect(kind="ability", ability_index=ability_index, source=source)
    )
    state.bump_chars()


def granted_abilities(state: GameState, oid: int):
    """Every ability currently granted to this object, as ``(source, ability)``.

    The *granted-to* object is what triggers and legality treat as the source,
    which is what makes "whenever **this creature** deals combat damage" mean
    the creature that was granted the ability rather than the thing that granted
    it.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return
    for temp in obj.until_eot:
        if temp.kind != "ability" or temp.ability_index is None or temp.source is None:
            continue
        source = state.objects.get(temp.source)
        if source is None:
            continue
        card = state.card_of(source)
        if temp.ability_index < len(card.grantable_abilities):
            yield source, card.grantable_abilities[temp.ability_index]


def lock_abilities(state: GameState, oid: int, source: int | None = None) -> None:
    """"Its activated abilities can't be activated this turn."

    Recorded as an until-end-of-turn effect like a pump, so the cleanup step
    already knows to remove it and no new lifetime has to be tracked.
    """
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(TempEffect(kind="lock_abilities", source=source))


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
    """Untap step: untap every permanent this player controls.

    Except the ones something is holding down.  The hold ends when its source
    leaves the battlefield -- "for as long as you control this creature" -- and
    this is where that is noticed, because the untap step is the only moment the
    lock has any effect.
    """
    untapped = []
    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None or obj.controller != pid:
            continue
        if obj.skip_next_untap:
            # Spent by *this* untap step whether or not there was anything to
            # skip. A permanent that happens to be untapped already still uses
            # the effect up -- holding the flag back until it is next tapped
            # would skip some later, unrelated untap step instead.
            obj.skip_next_untap = False
            continue
        if not obj.tapped:
            continue
        if obj.frozen_by is not None:
            holder = state.objects.get(obj.frozen_by)
            if holder is not None and holder.on_battlefield:
                continue
            obj.frozen_by = None
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
