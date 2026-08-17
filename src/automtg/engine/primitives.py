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
from .objects import MINUS_ONE, PLUS_ONE, GameObject
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
    # Infect (702.90c): damage to a *player* is poison counters instead of life
    # loss. Wither is deliberately not here -- 702.90b is about damage to
    # permanents only, so a wither creature that gets through hits for life in
    # the ordinary way, and that asymmetry is the whole difference between the
    # two keywords.
    poisons = source_oid is not None and _has(state, source_oid, Keyword.INFECT)
    if poisons:
        state.players[pid].poison += amount
        state.emit(
            EventType.POISON_ADDED,
            player=pid,
            source=source_oid,
            amount=amount,
            total=state.players[pid].poison,
        )
    else:
        state.players[pid].life -= amount
        # "Whenever an opponent loses life… (Damage causes loss of life.)"
        # Bloodthirsty Conqueror. Damage really is a loss of life, so it fires
        # the same event a `lose_life` does rather than a second one a card
        # would have to listen for separately.
        #
        # Inside the else on purpose: infect damage becomes poison counters and
        # no life is lost at all, so an infect hit must not fire this.
        fire(state, EventType.LIFE_LOST, player=pid, source=source_oid, amount=amount)
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
    from .characteristics import prevented_damage, protected_from

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
    # Absorb (702.63a): "prevent N of that damage", per source and per instance.
    # After protection, which prevents all of it, and before everything else --
    # what is prevented was never dealt, so nothing below should see it: no
    # deathtouch mark, no lifelink, no ledger entry, and a `DAMAGE_DEALT` event
    # carrying the reduced number rather than the printed one.
    if (shield := prevented_damage(state, oid)) > 0:
        blocked = min(shield, amount)
        amount -= blocked
        state.emit(
            EventType.DAMAGE_PREVENTED,
            player=obj.controller,
            source=source_oid,
            oid=oid,
            amount=blocked,
            reason="prevent_damage",
        )
        if amount <= 0:
            return 0
    # Wither and infect (702.90b/c): the damage is dealt "in the form of -1/-1
    # counters" instead of being marked. Not a `replacements` entry -- that
    # whitelist is about permanents *entering the battlefield* -- but a keyword
    # read at the one point every damage source already passes through, exactly
    # as deathtouch and lifelink are three lines below.
    #
    # It is still damage. Deathtouch still marks the victim, lifelink still
    # gains, the damage ledger still records who did it, and `DAMAGE_DEALT`
    # still fires with the same amount -- so enrage, Sengir and "damaged this
    # turn" all read a withering creature the way they read any other. Only
    # where the number lands changes.
    withers = source_oid is not None and (
        _has(state, source_oid, Keyword.WITHER) or _has(state, source_oid, Keyword.INFECT)
    )
    if withers:
        add_counters(state, oid, MINUS_ONE, amount, source=source_oid)
    else:
        obj.damage += amount
    if source_oid is not None:
        # Recorded here rather than on the object: Sengir Vampire asks the
        # question about a creature that has already died, and anything stored
        # on the victim is wiped by `reset_permanent_state` on the way out.
        state.damage_ledger.setdefault(oid, set()).add(source_oid)
        # The same fact, ordered, for the UI's "Killed by X" caption. See
        # `GameState.last_damager` for why it is not folded into the ledger.
        state.last_damager[oid] = source_oid
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
        # `fire`, not `emit`: the event has always been recorded in the log and
        # nothing subscribed to it, so "whenever you create a token" could not be
        # said. Fired *after* the move, so the token is on the battlefield by the
        # time anything listening resolves.
        fire(state, EventType.TOKEN_CREATED, player=controller, source=obj.oid, card=def_id)
        made.append(obj.oid)
    return made


def attach(state: GameState, aura_oid: int, target_oid: int) -> bool:
    from .characteristics import protected_from

    aura = state.objects.get(aura_oid)
    target = state.objects.get(target_oid)
    if aura is None or target is None or not target.on_battlefield:
        return False
    if aura_oid == target_oid:
        # Rule 301.5c -- an Equipment can't equip itself. Unreachable until
        # reconfigure, which prints the first Equipment that is also a creature
        # and so the first one its own "target creature you control" can find.
        # The card says `exclude_self` and this is the backstop, because an
        # Equipment attached to itself is a permanent no rule can ever detach.
        return False
    # "Protection from Wizards" cannot be enchanted or equipped by one. The Aura
    # is left where it is; state-based actions bin an Aura attached to nothing.
    if protected_from(state, target_oid, aura_oid):
        return False
    aura.attached_to = target_oid
    # A fresh attachment supersedes the remembered one, so an Equipment moved to
    # a second creature cannot still answer for the first.
    aura.last_attached_to = None
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


def transform(state: GameState, oid: int, *, to_back: bool | None = None) -> bool:
    """"Transform this creature." Rule 701.28.

    Turning the permanent over is one boolean, because ``GameState.card_of`` is
    a single choke point: every reader of a card's characteristics goes through
    it, so the layers, legality, combat and the serializer all see the other
    face at once and none of them needed changing.

    ``to_back`` forces a direction; the default is "turn it over", which is what
    every printed "transform this" says. A card with no back face does nothing
    rather than raising -- rule 701.28d, and it keeps a blanket "transform each
    creature" effect honest on a board of ordinary cards.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    if state.registry.get(obj.def_id).back_face is None:
        return False
    want = (not obj.transformed) if to_back is None else bool(to_back)
    if want == obj.transformed:
        return False
    obj.transformed = want
    state.bump_chars()
    fire(
        state,
        EventType.TRANSFORMED,
        player=obj.controller,
        source=oid,
        card=state.card_of(obj).id,
        face="back" if want else "front",
    )
    return True


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


def _stats_changed(
    state: GameState,
    obj: GameObject,
    *,
    power: int | None = None,
    toughness: int | None = None,
    keyword: str | None = None,
) -> None:
    """Announce a change to what a permanent *is*, short of a counter or a move.

    ``pump``, ``animate`` and ``grant_keyword`` all mutate ``until_eot`` and call
    ``bump_chars()``, and all three used to do it in complete silence.  Nothing
    downstream could see them: a combat trick left no line in the play-by-play
    and the client had no event to animate, so "target creature gets +3/+3 until
    end of turn" happened entirely off screen and a creature simply survived
    damage that should have killed it.

    ``state.emit`` and not ``triggers.fire`` -- deliberately.  ``zones.py`` warns
    that keys added to a *fired* event's ``data`` become bindings a card's
    triggered ability can read, so firing this would quietly change what an
    ability matches against.  Nothing is meant to trigger off it; it exists to
    be watched.
    """
    data: dict[str, Any] = {"card": obj.def_id}
    if power is not None:
        data["power"] = power
    if toughness is not None:
        data["toughness"] = toughness
    if keyword is not None:
        data["keyword"] = keyword
    state.emit(
        EventType.STATS_CHANGED,
        player=obj.controller,
        source=obj.oid,
        **data,
    )


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
    _stats_changed(state, obj, power=power, toughness=toughness)


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
    _stats_changed(state, obj, power=power, toughness=toughness)


def grant_keyword(
    state: GameState,
    oid: int,
    keyword: str,
    source: int | None = None,
    *,
    permanent: bool = False,
) -> None:
    """Give a permanent a keyword, until end of turn or for as long as it lasts.

    ``permanent`` is riot's "or with **haste**", and the distinction is not
    cosmetic: an until-end-of-turn haste on a creature that entered this turn
    does the same thing today and nothing ever after, so a riot creature that
    took haste would be indistinguishable from one that took the counter by the
    following turn. The two durations are stored in different places because
    only one of them is swept by `clear_until_eot`.
    """
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    if permanent:
        obj.granted_keywords.add(keyword)
    else:
        obj.until_eot.append(TempEffect(kind="keyword", keyword=keyword, source=source))
    state.bump_chars()
    _stats_changed(state, obj, keyword=keyword)


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


def merge_permanents(state: GameState, host_oid: int, card_oid: int, *, on_top: bool) -> None:
    """Mutate: put one card over or under a permanent, making them one.

    702.140b -- "they mutate into the creature on top plus all abilities from
    under it" -- is implemented as a **synthesised `CardDef`** written onto the
    host, because `card_of` is the single place derived card identity is
    decided. Building the union once here means legality, triggers, `chars`, the
    stack's ability lookup and the serializer all see one ability list with one
    set of indices, and not one of them needed changing.

    It composes: mutating onto an already-mutated pile reads `card_of(host)`,
    which is the previous union, so a third card adds to it rather than
    replacing it.

    Nothing else about the permanent moves. Counters, damage, auras, tapped
    status and summoning sickness all stay, which is 702.140c and is also simply
    what happens when the object is never touched.

    The merged card goes to `Zone.BATTLEFIELD` and into **no zone list** -- the
    same place a card on the stack lives -- so nothing that walks the
    battlefield sees it twice.
    """
    import dataclasses

    host = state.objects.get(host_oid)
    newcomer = state.objects.get(card_oid)
    if host is None or newcomer is None:
        return
    arriving = state.card_of(newcomer)
    standing = state.card_of(host)
    top, under = (arriving, standing) if on_top else (standing, arriving)
    host.merged_card = dataclasses.replace(
        top, abilities=tuple(top.abilities) + tuple(under.abilities)
    )
    host.merged_under = (*host.merged_under, card_oid)
    newcomer.zone = Zone.BATTLEFIELD
    newcomer.merged_into = host_oid
    newcomer.stack_id = None
    state.bump_chars()
    state.emit(
        "mutated",
        player=host.controller,
        source=host_oid,
        oid=host_oid,
        card=host.merged_card.id,
    )


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
    # `left_with` is the departure snapshot: an object that has just left the
    # battlefield has had `until_eot` emptied by `reset_permanent_state`, and
    # its own leave-the-battlefield triggers have not fired yet. Empty for
    # everything else, so this reads as plain `until_eot` in every other case.
    for temp in (*obj.until_eot, *obj.left_with):
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
        # "The **next** time this permanent would be destroyed **this turn**."
        # Expiring is most of what a regeneration shield is worth paying for; one
        # that survived the turn would make every regenerator indestructible
        # from the first time its ability was used.
        obj.regeneration_shields = 0
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
        # One event per permanent, through the trigger bus, exactly as
        # `untap_permanent` has always done for the single case. It used to be
        # one aggregate `emit` carrying a `count` -- which meant the untap step
        # was the only way a permanent could become untapped without saying
        # which permanent it was, and it went through `emit` rather than `fire`
        # so nothing could have heard it anyway. Inspired ("whenever this
        # creature becomes untapped") fires almost exclusively here, so a
        # subscription to the aggregate would have been a keyword that never
        # triggered in a real game.
        for oid in untapped:
            obj = state.objects.get(oid)
            fire(
                state,
                EventType.UNTAPPED,
                player=obj.controller if obj else pid,
                source=oid,
                oid=oid,
            )
    return untapped


def counters_of(state: GameState, oids: Iterable[int], kind: str = PLUS_ONE) -> int:
    return sum(state.objects[oid].counter(kind) for oid in oids if oid in state.objects)


def controlled_by(state: GameState, oids: Iterable[int], pid: int) -> list[GameObject]:
    return [state.objects[o] for o in oids if o in state.objects and state.objects[o].controller == pid]
