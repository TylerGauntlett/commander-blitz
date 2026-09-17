"""Low-level mutations shared by the effect ops, combat and the turn machine.

Each function here does exactly one rules-relevant thing and fires the events
that go with it.  Nothing in this module makes decisions or asks questions --
that is the effect layer's job.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from . import sagas
from .characteristics import (
    chars,
    life_gain_multiplier,
    life_loss_multiplier,
    player_cant_gain_life,
    player_protected_from,
    printed_token_matches,
    token_creation_replacements,
)
from .enums import Keyword, Step, Zone
from .events import EventType
from .objects import MINUS_ONE, PLUS_ONE, SHIELD, GameObject
from .state import new_object
from .triggers import fire
from .zones import move_object

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState
    from .structs import TempEffect
from .temp_effects import (  # noqa: F401
    _expired,
    clear_attack_restrictions,
    clear_block_prohibitions,
    clear_damage_shields,
    clear_goad,
    clear_life_locks,
    clear_player_protections,
    clear_sacrifice_restrictions,
    clear_unblockables,
    forbid_block,
    forbid_sacrifice,
    goad_creature,
    grant_player_protection,
    lock_life_total,
    make_unblockable,
    restrict_attack,
    sacrifice_forbidden,
    shield_player,
    shielded,
)

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
        nth = state.cards_drawn_this_turn.get(pid, 0) + 1
        state.cards_drawn_this_turn[pid] = nth
        # "…except the first one you draw in each of your draw steps." A card,
        # not an attempt: counted here, after the move, so a dredged draw (which
        # never reaches this function) leaves the next draw still the first.
        if state.step is Step.DRAW:
            state.cards_drawn_this_draw_step[pid] = (
                state.cards_drawn_this_draw_step.get(pid, 0) + 1
            )
        # "Whenever you draw your **second** card each turn." The ordinal of
        # *this* draw, put on the event so the answer is fixed where the ability
        # queues. The tally itself cannot be asked later: it keeps moving, and a
        # trigger's `condition` is re-evaluated on resolution (603.4), so the
        # same draw-two spell that queued the trigger has already carried the
        # tally past 2 by the time anything re-reads it.
        fire(state, EventType.DRAW, player=pid, source=oid, oid=oid, nth=nth)
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
# designations
# ----------------------------------------------------------------------


def give_emblem(state: GameState, def_id: str, index: int, pid: int) -> int:
    """Put ``emblems[index]`` of card ``def_id`` into ``pid``'s command zone (114).

    114.2: an emblem is created in the command zone by an effect, and the player
    who gets it **owns** it -- which is who "you" is on the emblem, and so the
    difference between Ob Nixilis Reignited's ultimate draining the opponent and
    draining its own controller.

    Placed directly rather than through `move_object`: an emblem comes from
    nowhere and does not *enter* the command zone from anywhere, so no zone
    change happens and nothing that listens for one should hear it. It is not a
    token (111.1) and not a card, so no state-based action removes it, and no
    effect in the DSL moves an object out of the command zone that is not a
    commander. It lasts the rest of the game.
    """
    obj = new_object(state, def_id, owner=pid, zone=Zone.COMMAND)
    obj.emblem = index
    state.players[pid].command.append(obj.oid)
    state.emit(EventType.EMBLEM_CREATED, player=pid, source=obj.oid, card=def_id, emblem=index)
    return obj.oid


def become_monarch(state: GameState, pid: int, source: int | None = None) -> bool:
    """Make a player the monarch (721.2), taking it off whoever held it (721.4).

    One assignment, because the designation is one field: giving it away removes
    it from the previous holder with nothing written to do so, which is what
    makes exclusivity a property of the representation rather than a rule every
    caller has to remember. That matters most for the card that hands it to an
    *opponent* on purpose -- Éomer's "target player becomes the monarch" -- where
    the giving-away is the whole of the drawback.

    Returns whether the designation actually moved, and **fires nothing when it
    did not**. Becoming the monarch while already the monarch is not an event:
    "until an opponent becomes the monarch" (Palace Jailer) is a question about
    the designation changing hands, and a re-designation that changed nothing
    would end that exile while the Jailer's controller still held the crown.

    Both routes in go through here -- this and the combat-damage transfer in
    :func:`damage_player` -- so the event and the state cannot disagree about who
    the monarch is.
    """
    if not state.is_alive(pid) or state.monarch == pid:
        return False
    previous = state.monarch
    state.monarch = pid
    fire(
        state,
        EventType.BECAME_MONARCH,
        player=pid,
        source=source,
        previous=previous,
    )
    return True


# ----------------------------------------------------------------------
# life and damage
# ----------------------------------------------------------------------


def life_locked(state: GameState, pid: int) -> bool:
    """Is ``pid``'s life total unable to change right now?  Usually false.

    "Until your next turn, your life total can't change" (Teferi's Protection).
    Read by the three places a life total moves -- `gain_life`, `lose_life` and
    the loss half of `damage_player` -- and by `costs.can_pay`, because 118.4
    makes paying life a loss of life and a loss that cannot happen is a cost
    that cannot be paid.

    Three readers and not one, because there is no single choke point: the
    engine subtracts life in `damage_player` directly rather than routing damage
    through `lose_life`, on purpose (only the loss is multiplied, never the
    damage). A lock installed in two of the three would be a life total that
    holds still until somebody attacks.
    """
    if not state.life_locks:
        return False
    return any(lock.player == pid for lock in state.life_locks)


def gain_life(state: GameState, pid: int, amount: int, source: int | None = None) -> int:
    """Put life on a player, applying any replacement of the gain.

    Returns **what was actually gained**, and `LIFE_GAINED` carries the same
    number: under Alhammarret's Archive a "gain 3" is a gain of 6, and a
    "whenever you gain life, put that many +1/+1 counters" trigger that read
    the unreplaced 3 would disagree with the life total it is reacting to.

    The one place a life total goes up -- `op_gain_life` and lifelink both
    arrive here -- so it is the one place the replacement is read.
    """
    if amount <= 0:
        return 0
    # "Your life total can't change" (118.5). Nothing gained, and **no event**:
    # `LIFE_GAINED` is what Marauding Blight-Priest and its kin trigger off, and
    # a gain that fired the event while moving no life would pay out for a gain
    # that did not happen.
    if life_locked(state, pid):
        return 0
    # "Your opponents can't gain life" (Erebos). The same refusal as the lock
    # and for the same reason no event fires: a life-gain trigger paying out
    # for a gain that was forbidden is the card's opponent getting the payoff
    # anyway. Asked before the multiplier, so an Archive cannot double a
    # forbidden gain into a permitted one -- "can't" wins (101.2).
    if player_cant_gain_life(state, pid):
        return 0
    # "You gain twice that much life instead" (614.1a). After the lock for the
    # reason `lose_life` reads its multiplier after it: twice nothing is nothing.
    amount *= life_gain_multiplier(state, pid)
    state.players[pid].life += amount
    fire(state, EventType.LIFE_GAINED, player=pid, source=source, amount=amount)
    return amount


def lose_life(state: GameState, pid: int, amount: int, source: int | None = None) -> int:
    """Take life off a player, applying any replacement of the loss.

    Returns **what was actually lost**, not what was asked for, and the
    difference is load-bearing: "each opponent loses life equal to the number of
    Vampires you control. You gain life equal to the life lost this way"
    (Malakir Bloodwitch) reads this number back, so a doubled loss has to gain
    the doubled amount or the two halves of one sentence disagree.

    The multiplier applies to life paid as a *cost* too (`costs.pay_life`),
    which is right: 118.4 makes paying life a loss of life like any other, and
    Bloodletter of Aclazotz says "would lose life" without naming a source.
    """
    if amount <= 0:
        return 0
    # The lock is checked before the multiplier, not after: a doubled loss of
    # nothing is still nothing, and reading `life_loss_multiplier` first would
    # be a walk of the battlefield for an answer that cannot matter.
    if life_locked(state, pid):
        return 0
    amount *= life_loss_multiplier(state, pid)
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
    # "Prevent all damage that would be dealt to you this turn" (615.1). Checked
    # *first*, above everything, because prevented damage was never dealt: no
    # life lost, no poison counters, no lifelink for the attacker, no
    # commander-damage tally and no `DAMAGE_DEALT` for the turn ledger to count.
    # Every one of those is a separate way the shield would leak if this sat
    # further down, and the infect branch is the sharpest -- a shielded player
    # who still took the poison would lose to a fog.
    #
    # This is the point the gap record said did not exist: the function went
    # straight from the infect check to `life -= amount`, so there was nowhere in
    # the player-damage path for a prevention to be consulted at all. The
    # permanent path has had one since absorb (`damage_permanent`, twenty lines
    # down); this is its player-side counterpart.
    if shielded(state, pid):
        # `fire`, not `emit`: emit only writes the log, which is what both
        # existing DAMAGE_PREVENTED sites did and is why `damage_prevented`
        # could not be a trigger. Selfless Squire's second line reads `amount`
        # off this event, so a prevention nothing announces is a shield that
        # eats the damage and pays nothing back.
        #
        # `to="player"`, matching `DAMAGE_DEALT`'s key of the same name: the
        # event covers both shapes and the trigger has to tell them apart, or a
        # blocked creature's absorb would give the Squire counters too.
        fire(
            state,
            EventType.DAMAGE_PREVENTED,
            player=pid,
            source=source_oid,
            oid=None,
            amount=amount,
            to="player",
            reason="damage_shield",
        )
        return 0
    # Protection over a seat (702.16d): "any damage that would be dealt to it is
    # prevented". Beside the shield rather than below it, because it prevents in
    # exactly the same way and for exactly the same reasons -- no life, no
    # poison, no lifelink, no commander tally -- and the infect branch two lines
    # down is again the sharpest: a protected player who still took the poison
    # would lose through Teferi's Protection.
    #
    # A separate branch and not a widening of `shielded`, because the two are
    # different questions: a shield stops *all* damage this turn whatever dealt
    # it, and protection is parameterised by the source. Only the second needs
    # `source_oid`.
    if player_protected_from(state, pid, source_oid):
        fire(
            state,
            EventType.DAMAGE_PREVENTED,
            player=pid,
            source=source_oid,
            oid=None,
            amount=amount,
            to="player",
            reason="protection",
        )
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
        # "Damage causes loss of life", so a replacement of the *loss* reaches
        # damage too -- Bloodletter of Aclazotz prints that reminder precisely
        # because it is not obvious.
        #
        # **Only the life loss is multiplied, never the damage.** The damage
        # dealt is still `amount`, and everything below this branch reads that
        # unchanged: lifelink gains what was dealt (702.15b), `DAMAGE_DEALT`
        # carries what was dealt, and the commander-damage tally counts what was
        # dealt. This is the same separation the wither and infect rows make --
        # it is still damage, and only where the number lands changes -- and
        # getting it wrong would make a doubled hit from a lifelinking commander
        # gain double life and kill on half the commander damage.
        lost = 0 if life_locked(state, pid) else amount * life_loss_multiplier(state, pid)
        state.players[pid].life -= lost
        # "Whenever an opponent loses life… (Damage causes loss of life.)"
        # Bloodthirsty Conqueror. Damage really is a loss of life, so it fires
        # the same event a `lose_life` does rather than a second one a card
        # would have to listen for separately.
        #
        # Inside the else on purpose: infect damage becomes poison counters and
        # no life is lost at all, so an infect hit must not fire this.
        # Not fired when the life total is locked: the damage was dealt and
        # `DAMAGE_DEALT` below still says so, but no life was lost, and
        # Bloodthirsty Conqueror paying out for a loss that did not happen is
        # the failure this branch exists to avoid. The lock stops the *change*,
        # not the damage -- protection is the effect that stops the damage, and
        # Teferi's Protection prints both sentences because they differ.
        if lost:
            fire(state, EventType.LIFE_LOST, player=pid, source=source_oid, amount=lost)
    src = state.objects.get(source_oid) if source_oid is not None else None
    fire(
        state,
        EventType.DAMAGE_DEALT,
        player=pid,
        source=source_oid,
        amount=amount,
        to="player",
        combat=is_combat,
        # The two keys `deals_damage_to_player` needs, and neither is a second
        # way of saying `player`. `player` on this event is *whom the damage
        # landed on*, which the trigger layer reads as the actor for every event
        # whose subject is a player -- so a trigger asking "damage **I** dealt"
        # would compare against the victim and mean the opposite of itself.
        # `controller` is the dealing permanent's, matching the key
        # COMBAT_DAMAGE_TO_PLAYER below has carried for the same reason, and
        # `defender` is what a `defending` clause compares against so
        # "…deals damage to **an opponent**" can be said in a pod, where the
        # difference between "an opponent" and "a player" is visible.
        #
        # Written on the player half only. `damage_permanent` fires its own
        # DAMAGE_DEALT with `to="permanent"`, and neither key means anything
        # there -- there is no defending player when a Shock hits a Bear.
        controller=None if src is None else src.controller,
        defender=pid,
    )
    _apply_lifelink(state, source_oid, amount)

    # `src is not None` implies `source_oid is not None`, which the lookup above
    # is the only source of.
    if is_combat and src is not None:
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
        # `fire`, not `emit`, and `to="permanent"`: see the player-side site in
        # `damage_player`. This one has always been a log line with nothing
        # subscribed; putting it on the bus costs nothing and makes the two
        # halves of the event answerable by the same trigger name.
        fire(
            state,
            EventType.DAMAGE_PREVENTED,
            player=obj.controller,
            source=source_oid,
            oid=oid,
            amount=amount,
            to="permanent",
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
        fire(
            state,
            EventType.DAMAGE_PREVENTED,
            player=obj.controller,
            source=source_oid,
            oid=oid,
            amount=blocked,
            to="permanent",
            reason="prevent_damage",
        )
        if amount <= 0:
            return 0
    # Shield counter (122.1c): "if it would be dealt damage ... remove a shield
    # counter from it instead". A **replacement, not a reduction** -- one counter
    # answers the whole event however big it is, so lethal damage to a shielded
    # creature costs exactly one counter and marks nothing. Written as an early
    # return for the same reason protection is: what was replaced was never
    # dealt, so no deathtouch mark, no lifelink, no damage ledger, no
    # `DAMAGE_DEALT`, and a `damaged_this_turn` that still reads no.
    #
    # After absorb, and that ordering is the one judgement call. Both are
    # replacement-ish shields over the same event and 616.1 would let the
    # affected player pick; checked this way round the counter is spent only on
    # damage that would otherwise land, so a 2-damage ping into "prevent the next
    # 3" leaves the shield counter on the permanent, which is what its controller
    # would have chosen. Before the planeswalker and wither branches, because
    # each of those is a *different place to put the damage* rather than a reason
    # it is not dealt -- a shielded planeswalker must not lose loyalty and a
    # shielded creature must not take -1/-1 counters from a withering source.
    if spend_shield_counter(state, oid, source=source_oid):
        fire(
            state,
            EventType.DAMAGE_PREVENTED,
            player=obj.controller,
            source=source_oid,
            oid=oid,
            amount=amount,
            to="permanent",
            reason="shield_counter",
        )
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
    # 306.8: damage dealt to a planeswalker removes that many loyalty counters.
    # Read here, beside wither, for the same reason wither is read here: this is
    # the one point every damage source already passes through, and marking
    # `obj.damage` on a planeswalker instead would be invisible -- nothing
    # compares a planeswalker's damage to anything, so it would take no damage
    # at all and never die.
    from .characteristics import chars as _chars

    if "Planeswalker" in _chars(state, oid).types:
        remove_counters(state, oid, "loyalty", amount)
    elif withers:
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
    # Read before the write. A Saga's chapter ability triggers on the count
    # *becoming* its number (714.2c), so the comparison needs both sides and
    # this is the only moment both exist.
    before = obj.counter(kind)
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
        if kind == sagas.LORE:
            # Here rather than at each caller, because every way a lore counter
            # can arrive comes through this function -- the turn-based action,
            # `add_counters`, `move_counters` and `proliferate` -- and a Saga
            # whose chapter fired for only some of them would be wrong in
            # whichever direction nobody tested. Guarded on the kind first so
            # every other counter in the game pays one string comparison.
            #
            # After COUNTER_PLACED, so a trigger watching the counter and the
            # chapter it caused queue in that order.
            sagas.chapters_reached(state, oid, before, before + amount)
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


def spend_shield_counter(state: GameState, oid: int, *, source: int | None = None) -> bool:
    """Try to spend one shield counter (122.1c).  True if one was there.

    The single consumer behind both halves of the shield counter, and the reason
    there is a function rather than two `if obj.counter(SHIELD)` lines: the two
    hook points are in different modules -- `zones.destroy` and
    `damage_permanent` above -- and the rule is that *one* counter is removed per
    event, whatever the event was and however large it was. Written twice, the
    two sites would drift on the one thing the card is bought for.

    It removes the counter and says so, and it does nothing else. What replaced
    what is the caller's sentence to say, because the two are not the same
    announcement -- prevented damage is a `DAMAGE_PREVENTED` the trigger bus
    already carries, and a replaced destruction is a log line beside
    `regenerated` and `totem_armor`.

    Note what it deliberately does **not** copy from regeneration (701.15a): the
    permanent is not tapped, it is not removed from combat, and its marked damage
    is not removed. A shield counter is not a regeneration shield, and a shielded
    creature that already has lethal damage marked on it therefore loses one
    counter per state-based-action check until it has none and dies -- which is
    the printed behaviour, and the reason the counter is worth spending *before*
    the damage is ever marked.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or obj.counter(SHIELD) <= 0:
        return False
    remove_counters(state, oid, SHIELD, 1)
    # `emit`, not `fire`: a log line, in the same shape and for the same reason
    # as `regenerated` and `totem_armor` in `zones`. Nothing subscribes to a
    # replacement that stopped something happening, and inventing an `EventType`
    # for it would need narrating in the frontend to earn its keep.
    state.emit("shield_counter", player=obj.controller, source=source, oid=oid)
    return True


def _token_creation_plan(
    state: GameState, def_id: str, controller: int, count: int
) -> list[tuple[str, int, bool]] | None:
    """What this token creation actually creates, after the `replace_token_creation`
    statics that reach ``controller`` have had their say.

    Each entry is ``(token id, how many, substituted)``.  ``substituted`` is
    whether the entry is a *different* token from the one the creating effect
    asked for -- which is what decides whether that effect's ``overrides`` still
    describe it (see `create_token`).

    The static has two axes, and a card uses exactly one of them:

    - **``create_instead`` -- identity.**  Academy Manufactor ("if you would
      create a Clue, Food, or Treasure token, instead create one of each") and
      Divine Visitation ("if one or more creature tokens would be created under
      your control, that many 4/4 Angels are created instead") are two printed
      sentences and one mechanism: *each token that was about to be made becomes
      one of each id in ``create_instead``*.  Manufactor lists three ids, so one
      Treasure becomes a Clue, a Food and a Treasure; Divine Visitation lists
      one, so N Soldiers become N Angels and the count is preserved for free.
    - **``token_multiplier`` -- count.**  Doubling Season, Parallel Lives,
      Anointed Procession, Bard, King of Dale: "twice that many **of those
      tokens** are created instead".  The pending entry keeps its id -- and so
      its ``overrides``, which is what makes a doubled copy token two copies
      rather than a copy and a plain card -- and its count is multiplied.  The
      card names no token, so no id could be written in ``create_instead``, and
      listing one there would convert every other token into it.

    **What this is not.** It is not rule 616 and it is not a general replacement
    system.  There is no event object, nothing else in the engine can be
    replaced, and nothing outside `create_token` consults these statics.
    ``docs/rules-coverage.md`` records the general system as engine work that
    has not been done.

    Three rules the shape of the loop is entirely about:

    - **614.5, a replacement applies at most once to a given event.**  One pass
      over a fixed list of statics, each one seeing the plan as the statics
      before it left it.  So a Divine Visitation does not re-apply to the Angels
      it just made -- which is not an optimisation, it is the difference between
      this card and an infinite loop -- two Academy Manufactors turn one
      Treasure into three of each rather than into nothing terminating, and a
      Parallel Lives doubles a creation once, not its own doubled output again.
    - **Several doublers compound.**  Each is a separate replacement of the one
      event, each applied once, each to the event as the last one modified it:
      one token under two doublers is 2 then 4, under three is 8.  The product
      is the same in whatever order they apply, which is why 616.1's "the
      affected player chooses the order" -- which this engine does not ask,
      applying in battlefield order instead -- is invisible between doublers,
      and between a doubler and an unfiltered substitution.  It is *not*
      invisible between a filtered doubler and a substitution that changes
      whether the filter matches (a Treasure-only doubler and a Manufactor); no
      printed doubler filters that way today, and the divergence is recorded in
      ``docs/rules-coverage.md``.
    - **The replacement belongs to the *token's controller*.**  Every printed
      card says "under your control" or "you", so the list is gathered for
      ``controller`` -- the player the token arrives under -- rather than for
      whoever controls the effect that is creating it: a Bard doubles the Elk an
      opponent's Beast Within gives you, and not the token you give them.
      ``affects_player: "any"`` is Primal Vigor, whose sentence names nobody.

    ``None`` means nothing applied, which is every token creation in a game
    where none of these cards is on the battlefield: the caller then takes the
    original path unchanged, ``overrides`` and all.
    """
    if count <= 0:
        return None
    statics = token_creation_replacements(state, controller)
    if not statics:
        return None
    plan: list[tuple[str, int, bool]] = [(def_id, count, False)]
    replaced = False
    for static in statics:
        selector = static.get("affects_token") or {}
        substitutes = static.get("create_instead") or ()
        multiplier = int(static.get("token_multiplier") or 1)
        after: list[tuple[str, int, bool]] = []
        matched = False
        for pending_id, pending_count, substituted in plan:
            if not printed_token_matches(state, pending_id, selector):
                after.append((pending_id, pending_count, substituted))
                continue
            matched = True
            if substitutes:
                after.extend((str(sub), pending_count, True) for sub in substitutes)
            else:
                after.append((pending_id, pending_count * multiplier, substituted))
        if matched:
            plan = after
            replaced = True
    return plan if replaced else None


def create_token(
    state: GameState,
    def_id: str,
    controller: int,
    count: int = 1,
    *,
    tapped: bool = False,
    attacking: int | None = None,
    overrides: dict[str, Any] | None = None,
    source: int | None = None,
) -> list[int]:
    """Put ``count`` copies of a token onto the battlefield under ``controller``.

    ``attacking`` is the player the token joins combat against.  A token put onto
    the battlefield attacking was **never declared** as an attacker, so it does
    not trigger anything that fires on attacking -- that is the actual rule, and
    it is also what stops a mobilize token making another mobilize token forever.

    ``overrides`` is embalm's "except it's a white Zombie Angel with no mana
    cost".  Set *before* the token enters, so its enters-trigger and every
    characteristic read afterwards see the token it actually is.

    What is created is not always what was asked for: `_token_creation_plan`
    gives the `replace_token_creation` statics their say first, and this is the
    one place in the engine that consults them, because it is the one place a
    token creation can still be intercepted.  Everything the *creating effect*
    said about the token still applies to whatever is created instead -- tapped,
    and attacking, which is the printed ruling -- but ``overrides`` do not
    survive a *substitution*: they describe the token that was replaced and
    never made, so a substituted entry drops them rather than painting somebody
    else's exception onto an Angel.  A *multiplied* entry keeps them, because
    "twice that many of those tokens" are still those tokens: a doubled embalm
    copy is two white Zombie copies.

    ``source`` is the object whose effect is creating the tokens, and each one
    is recorded in its `created_tokens` -- "tokens created with this creature"
    (Faerie Artisans). A substituted token is recorded too: it is still the
    token that effect created.
    """
    plan = _token_creation_plan(state, def_id, controller, count)
    if plan is None:
        plan = [(def_id, count, False)]
    made: list[int] = []
    for token_id, token_count, substituted in plan:
        for _ in range(max(0, token_count)):
            obj = new_object(
                state,
                token_id,
                owner=controller,
                zone=Zone.EXILE,
                controller=controller,
                is_token=True,
            )
            if overrides and not substituted:
                obj.copy_overrides = dict(overrides)
            # Before the move, so the token's own enters-triggers already see
            # which object created it.
            creator = state.objects.get(source) if source is not None else None
            if creator is not None:
                creator.created_tokens.add(obj.oid)
            # The token is created "nowhere" and then enters the battlefield, so
            # ETB triggers and enters-tapped replacements run through the normal
            # path.
            state.players[controller].exile.append(obj.oid)
            move_object(state, obj.oid, Zone.BATTLEFIELD, tapped=tapped, cause="token")
            if attacking is not None and state.combat is not None:
                state.combat.attackers[obj.oid] = attacking
            # `fire`, not `emit`: the event has always been recorded in the log
            # and nothing subscribed to it, so "whenever you create a token"
            # could not be said. Fired *after* the move, so the token is on the
            # battlefield by the time anything listening resolves.
            fire(
                state,
                EventType.TOKEN_CREATED,
                player=controller,
                source=obj.oid,
                card=token_id,
            )
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
    aura.attached_timestamp = state.alloc_timestamp()
    # A fresh attachment supersedes the remembered one, so an Equipment moved to
    # a second creature cannot still answer for the first.
    aura.last_attached_to = None
    # An Aura is attached to exactly one thing (303.4), so moving one onto a
    # permanent takes it off whatever player it was on. Nothing prints that
    # today -- no card moves an Aura between a player and a permanent -- and it
    # is written anyway because the alternative is a permanent carrying two
    # hosts, where every reader would get a different answer.
    aura.attached_to_player = None
    state.bump_chars()
    fire(state, EventType.ATTACHED, player=aura.controller, source=aura_oid, oid=target_oid)
    return True


def attach_to_player(state: GameState, aura_oid: int, player: int) -> bool:
    """ "Enchant opponent" -- attach an Aura to a **player** (303.4a, 702.5b).

    `attach` above with a seat where the permanent goes, and it is a separate
    function rather than a widened one for the reason `GameObject`'s two fields
    are separate: a player id and an oid are both `int`, so a single entry point
    taking either could not tell them apart, and the failure would be an Aura
    silently enchanting an unrelated permanent.

    The two restrictions `attach` enforces have no counterpart here, and both
    absences are rules rather than omissions. 301.5c is about a permanent
    attaching to *itself*, which a seat cannot be. And protection is a property
    of objects and players alike, but the enchant restriction it blocks is
    "can't be enchanted by" -- a player has no protection in any card the engine
    can be handed, and inventing one here would be a rule nothing asked for.

    Liveness is checked, unlike `attach`'s battlefield test, and it is the same
    check: a player who has lost the game is no more a legal host than a
    permanent in a graveyard, and `sba` bins the Aura either way.

    The ATTACHED event carries the seat in ``player_attached`` rather than in
    ``oid``: that key is an object id everywhere else in the log, and a seat
    number arriving in it would read as some unrelated permanent to anything
    that subscribes.
    """
    aura = state.objects.get(aura_oid)
    if aura is None or not aura.on_battlefield or not state.is_alive(player):
        return False
    aura.attached_to_player = player
    aura.attached_to = None
    aura.last_attached_to = None
    state.bump_chars()
    fire(
        state,
        EventType.ATTACHED,
        player=aura.controller,
        source=aura_oid,
        player_attached=player,
    )
    return True


def add_subtypes(state: GameState, oid: int, subtypes: Sequence[str]) -> tuple[str, ...]:
    """ "It becomes a Vampire in addition to its other types." Captivating Vampire.

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
    """ "Transform this creature." Rule 701.28.

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


def change_control(
    state: GameState,
    oid: int,
    pid: int,
    source: int | None = None,
    duration: str = "permanent",
) -> bool:
    """ "Gain control of target creature." Rule 800.4a.

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

    ``duration`` is ``"permanent"`` (Captivating Vampire) or
    ``"until_end_of_turn"`` (Act of Treason).  The temporary form is this same
    call plus one ``TempEffect`` recording the seat it came from, and the
    handback in ``clear_until_eot`` is this same function pointed the other way
    -- which is the whole reason it is written as a re-entry rather than as an
    assignment to ``controller``.  All three rules above apply on the way *back*
    too, and none of them is symmetric with itself:

    - the permanent has not been under its original controller since **their**
      turn began either -- somebody else had it in between -- so ``entered_turn``
      is stamped with the handback rather than restored to what it was before
      the steal (302.6);
    - the handback is a second control change and removes it from combat
      (506.4).  Structural rather than observable: ``state.combat`` is ``None``
      by the cleanup step, so it is one branch inside a call being made anyway,
      and the alternative is a rule that holds only until somebody adds a phase;
    - and every ``controller``-filtered static reads differently a second time,
      so the characteristics cache is dropped in both directions.

    The tidy wrong version is to save the controller and ``entered_turn``
    together and put both back -- "as it was" -- which hands somebody a creature
    that is not newly under their control, and loses the cache drop outright.
    """
    from .structs import CONTROL_DURATIONS

    if duration not in CONTROL_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown control duration {duration!r}")
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield or obj.controller == pid:
        # Including the no-op: "gain control of a permanent you control" changes
        # nothing, so there is nothing to hand back either.  Recording one would
        # invent a control change at cleanup that no card asked for.
        return False
    previous = obj.controller
    obj.controller = pid
    obj.entered_turn = state.turn
    if state.combat is not None:
        state.combat.remove(oid)
    if duration == "until_end_of_turn":
        from .structs import TempEffect

        obj.until_eot.append(
            TempEffect(
                kind="control",
                source=source,
                previous_controller=previous,
                new_controller=pid,
            )
        )
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


def pump(state: GameState, oid: int, power: int, toughness: int, source: int | None = None) -> None:
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(TempEffect(kind="pump", power=power, toughness=toughness, source=source))
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
    keywords: Sequence[str] = (),
    your_turn_keywords: Sequence[str] = (),
    source: int | None = None,
) -> None:
    """ "It becomes a 4/4 Elemental creature until end of turn. It's still a land."

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
    # Keywords the animated body carries. `your_turn_keywords` is the quoted
    # half of the Restless cycle -- "with \"During your turn, this creature has
    # first strike\"" -- and it has to ride the animation rather than be a
    # separate ability on the card: a static written beside the animation would
    # have no printed line of its own to claim, which is the residual gate's
    # objection and the reason Raging Ravine still fails.
    for word in keywords:
        obj.until_eot.append(TempEffect(kind="keyword", keyword=word, source=source))
    for word in your_turn_keywords:
        obj.until_eot.append(
            TempEffect(kind="keyword", keyword=word, source=source, only_your_turn=True)
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


def grant_ability(
    state: GameState,
    oid: int,
    ability_index: int,
    source: int,
    *,
    permanent: bool = False,
) -> None:
    """Hand one of ``source``'s grantable abilities to ``oid``.

    Stored as a pointer -- source oid plus index -- rather than a copy of the
    ability, so there is exactly one definition of what was granted and it stays
    the card file's.

    ``permanent`` is the distinction `grant_keyword` already draws, and it
    matters here for the same reason: Clavileño's "It gains 'when this creature
    dies, …'" prints no duration, and a grant swept at cleanup would be a
    strictly weaker card that looks identical on the turn it was made. The two
    durations live in different lists because only one of them is swept.
    """
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    effect = TempEffect(kind="ability", ability_index=ability_index, source=source)
    if permanent:
        obj.granted_abilities_permanent.append(effect)
    else:
        obj.until_eot.append(effect)
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
    for temp in (*obj.until_eot, *obj.granted_abilities_permanent, *obj.left_with):
        if temp.kind != "ability" or temp.ability_index is None or temp.source is None:
            continue
        source = state.objects.get(temp.source)
        if source is None:
            continue
        card = state.card_of(source)
        if temp.ability_index < len(card.grantable_abilities):
            yield source, card.grantable_abilities[temp.ability_index]


def lock_abilities(state: GameState, oid: int, source: int | None = None) -> None:
    """ "Its activated abilities can't be activated this turn."

    Recorded as an until-end-of-turn effect like a pump, so the cleanup step
    already knows to remove it and no new lifetime has to be tracked.
    """
    from .structs import TempEffect

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    obj.until_eot.append(TempEffect(kind="lock_abilities", source=source))


def clear_until_eot(state: GameState) -> None:
    """Cleanup step: remove damage and every until-end-of-turn effect.

    Every kind but one ends by being dropped.  ``control`` ends by being *run*:
    the steal already happened, and what expires is the permanent sitting on the
    wrong side of the board, so the entries are collected on the way past and
    handed back below.
    """
    handbacks: list[tuple[int, TempEffect]] = []
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
        # "…would die **this turn**." The redirect expires with the turn, like
        # a regeneration shield and for the same reason: one that survived would
        # make every creature Gallifrey Falls ever touched permanently
        # un-buriable.
        obj.dies_to = None
        # "…become a copy of another target creature **until end of turn**."
        # Only the timed form is cleared here; a permanent copying something
        # indefinitely -- Clone's shape -- carries `copying_until_eot` false and
        # keeps its borrowed face, which is what makes the duration a real
        # distinction rather than a comment.
        if obj.copying_until_eot:
            obj.copying = None
            obj.copying_name = None
            obj.copying_until_eot = False
        handbacks.extend((oid, temp) for temp in obj.until_eot if temp.kind == "control")
        obj.until_eot.clear()
    state.bump_chars()
    _hand_back_control(state, handbacks)


def _hand_back_control(state: GameState, handbacks: list[tuple[int, TempEffect]]) -> None:
    """ "…until end of turn" for a control change: give the permanents back.

    Three things decide who gets what, and each of them is a way of being wrong
    that a bare ``obj.controller = previous`` would be:

    * **Only permanents still on the battlefield.**  Free, and deliberately so:
      the entries were read out of ``state.battlefield``, and a permanent that
      died or was exiled during the turn had ``until_eot`` emptied by
      ``reset_permanent_state`` on the way out.  A stolen creature sacrificed
      for value is gone, not returned -- which is the whole reason the Act of
      Treason plus sacrifice-outlet line is a real line.
    * **Newest first.**  Two steals stack: A takes it from its owner, then B
      takes it from A, and both effects end in this same step.  Undone in the
      order they were made, the first handback would find the wrong controller
      and stop; undone newest-first, B gives it to A and A gives it to its
      owner, which is where it started.
    * **Only if the steal is still the reason.**  ``new_controller`` is checked
      against the current controller rather than trusted, because a *permanent*
      control change made afterwards outlives this one (a later continuous
      effect in the same layer still applies).  Mind Control on a creature
      somebody Act of Treason'd does not evaporate at end of turn, and handing
      it to the original controller would undo a card that never ended.

    A seat that has left the game is skipped for the same reason: 800.4 takes a
    departed player's permanents with them, so there is nobody to hand it to and
    the current controller keeps it rather than the permanent falling into a
    seat that is not playing.
    """
    for oid, temp in reversed(handbacks):
        obj = state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        previous, gained = temp.previous_controller, temp.new_controller
        if previous is None or (gained is not None and obj.controller != gained):
            continue
        if not state.is_alive(previous):
            continue
        # The reverse steal goes through `change_control` and not through the
        # field, so 302.6, 506.4 and the characteristics bump all apply coming
        # home as well.  `permanent` because this handback is the end of the
        # duration, not a new one to unwind next turn.
        change_control(state, oid, previous, source=temp.source, duration="permanent")


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
