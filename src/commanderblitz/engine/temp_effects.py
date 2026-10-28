"""Until-end-of-turn restrictions on permanents and players: attack and block
prohibitions, goad, unblockability, sacrifice restrictions, damage shields
and life locks. Each has a set/clear/query triple over one shared expiry
rule, ``_expired``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from .characteristics import _matches
from .player_statics import _battlefield_statics, static_life_floor
from .structs import (
    ATTACK_RESTRICTION_DURATIONS,
    BLOCK_PROHIBITION_DURATIONS,
    CAST_LOCK_DURATIONS,
    COMBAT_FOG_DURATIONS,
    DAMAGE_SHIELD_DURATIONS,
    PERMANENT_SHIELD_DIRECTIONS,
    PERMANENT_SHIELD_DURATIONS,
    SACRIFICE_RESTRICTION_DURATIONS,
    UNBLOCKABLE_DURATIONS,
    AttackRestriction,
    BlockProhibition,
    CastLock,
    CombatFog,
    DamageShield,
    FlashPermission,
    LifeFloor,
    LifeLock,
    OutcomeLock,
    PermanentShield,
    PlayerProtection,
    SacrificeRestriction,
    Unblockable,
)

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def restrict_attack(
    state: GameState,
    attacker: int,
    defender: int,
    duration: str = "this_turn",
    source: int | None = None,
    planeswalkers: bool = False,
    walker_subtypes: tuple[str, ...] = (),
) -> bool:
    """ "``attacker`` can't attack ``defender``" for ``duration``.

    Returns whether anything was recorded, so the op above can log the ones that
    mattered rather than claiming a restriction it silently dropped.

    Two pairs are refused, and both are the same argument -- a restriction that
    can never bite would read in the log as one that did:

    * A player cannot attack themselves, so ``attacker == defender`` is not a
      prohibition, it is a no-op wearing one's clothes.
    * A player already out of the game is not going to declare attackers.

    Deduplicated on the whole tuple. Two Champions of Minas Tirith taxing the
    same opponent in the same combat impose one restriction, not two, and
    "can't attack" does not stack -- so a second copy would only make the
    eventual clear-up quadratic.

    ``planeswalkers`` widens the pair to the defender's **planeswalkers** as
    well as their seat, and it is part of the deduplication key on purpose: a
    narrow restriction and a wide one over the same pair are not the same
    prohibition, and folding them together would let a Ghostly-Prison-shaped
    entry swallow "creatures can't attack this combat". See
    :class:`structs.AttackRestriction`.

    ``walker_subtypes`` narrows the other way: the seat stays open and only the
    defender's planeswalkers of those subtypes are closed ("can't attack Jaces
    you control"). It is part of the key for the same reason, and the two are
    never set together -- one widens a seat to its walkers, the other replaces
    the seat with some of them.
    """

    if duration not in ATTACK_RESTRICTION_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown attack restriction duration {duration!r}")
    if attacker == defender:
        return False
    if not state.is_alive(attacker) or not state.is_alive(defender):
        return False
    entry = AttackRestriction(
        attacker=attacker,
        defender=defender,
        duration=duration,
        planeswalkers=planeswalkers,
        walker_subtypes=tuple(walker_subtypes),
        source=source,
    )
    if entry in state.attack_restrictions:
        return False
    state.attack_restrictions.append(entry)
    return True


def clear_attack_restrictions(state: GameState, duration: str) -> None:
    """Drop every attack restriction of one duration -- its wearing-off.

    Called from two places, one per duration: `turn._cleanup_step` for
    ``this_turn`` and `combat.end_combat` for ``this_combat``.  Split by duration
    rather than cleared wholesale at either point, because a turn-scoped
    restriction has to survive the combat it was cast before -- Call for Aid is
    cast in a precombat main phase and means the *whole* turn, extra combats
    included.
    """
    if not state.attack_restrictions:
        return
    state.attack_restrictions = [r for r in state.attack_restrictions if r.duration != duration]


def goad_creature(state: GameState, oid: int, player: int) -> bool:
    """ "Goad that creature" (701.38a) -- ``player`` is the one it must attack around.

    One rules-relevant thing, said in one word: the creature is written down as
    goaded **by this player**, and everything goad means is read back off that
    mark. `combat.attack_required` makes it attack each combat while the mark is
    there, and `combat.attack_target_forbidden` keeps it off the marked player
    while anybody else is available.

    The datum is *who*, never *when*. "Until your next turn" is not a turn
    number -- eliminate a player and it moves -- so the clock is
    `turn._untap_step` asking which marks belong to whoever is untapping, exactly
    as detain does one line above it.

    A **set** rather than detain's single pid, because two opponents goading the
    same creature is two live obligations: the second one's clock runs from the
    second one's untap step, and the creature has to attack around both of them.
    Adding a mark that is already there changes nothing and returns ``False``, so
    a second copy of the same goad neither stacks nor extends.

    Returns whether anything was recorded. Refused, as `restrict_attack` refuses
    its own dead cases, when the mark could never bite:

    * a creature that is not on the battlefield -- it left in response, and a
      mark on a card in a graveyard would ride back onto the battlefield with it
      if `reset_permanent_state` ever stopped clearing it;
    * a player who is out of the game, whose untap step is never coming, so the
      goad would last for the rest of the game;
    * goading your own creature *for yourself* -- a creature cannot attack its
      own controller, so "attacks a player other than you" would be vacuous and
      the compulsion would be a one-sided Bident with no author. (Goading a
      creature you do not control is the normal case and is not this.)
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    if not state.is_alive(player):
        return False
    if obj.controller == player:
        return False
    if player in obj.goaded_by:
        return False
    obj.goaded_by.add(player)
    return True


def clear_goad(state: GameState, player: int) -> None:
    """Drop every goad ``player`` placed -- goad's wearing-off.

    Called from `turn._untap_step`, in the same breath as detain and the
    ``until_your_next_turn`` block prohibitions and for the same reason: 701.38a
    ends a goad "until your next turn", and the only moment that phrase can be
    resolved is the start of the goading player's own turn.

    Note what this does *not* do: a creature goaded by two players loses one mark
    here and keeps the other. That is why the field is a set and why the clear-up
    takes a player rather than emptying it.
    """
    for obj in state.objects.values():
        obj.goaded_by.discard(player)


def forbid_block(
    state: GameState,
    objects: Iterable[int] | None,
    duration: str = "this_turn",
    player: int | None = None,
    source: int | None = None,
) -> bool:
    """ ""Can't block" for ``duration``, on ``objects`` or on every creature.

    ``objects`` is a fixed set of oids chosen when the effect resolved, or
    ``None`` for the global form -- "creatures can't block this turn" -- which is
    a continuous effect and not a snapshot, so a creature that enters later in
    the turn is caught by it too.  Passing an empty iterable is *not* the global
    form: "up to one target creature can't block" with no target chosen restricts
    nobody, and collapsing that into "all creatures" would be the worst possible
    misreading.

    Returns whether anything was recorded, so the op above can distinguish a
    restriction it imposed from one it silently dropped.  Two cases are refused,
    and both are a restriction that could never bite:

    * an empty ``objects`` -- see above;
    * ``until_your_next_turn`` with no ``player``, which has no clock at all and
      would therefore last forever.

    Deduplicated on the whole entry, because "can't block" does not stack: two
    copies would only make the eventual clear-up quadratic.  Note that a global
    entry never merges with one naming a set, and rightly so -- they expire the
    same way but mean different things while they live.
    """

    if duration not in BLOCK_PROHIBITION_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown block prohibition duration {duration!r}")
    oids = None if objects is None else tuple(dict.fromkeys(objects))
    if oids is not None and not oids:
        return False
    if duration == "until_your_next_turn" and player is None:
        return False
    entry = BlockProhibition(objects=oids, duration=duration, player=player, source=source)
    if entry in state.block_prohibitions:
        return False
    state.block_prohibitions.append(entry)
    return True


def clear_block_prohibitions(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the block prohibitions of one duration -- their wearing-off.

    Called from two places, one per duration, and the second one takes a player:
    `turn._cleanup_step` clears ``this_turn`` for everybody, and
    `turn._untap_step` clears the ``until_your_next_turn`` entries belonging to
    whoever is untapping -- beside detain, on detain's clock, and for detain's
    reason.  "Your next turn" is not a turn number: eliminate a player and it
    moves, so the entry names the player and the untap step asks.
    """
    state.block_prohibitions = _expired(state.block_prohibitions, duration, player)


def grant_player_protection(
    state: GameState,
    pid: int,
    qualities: Iterable[str],
    duration: str = "until_your_next_turn",
    source: int | None = None,
) -> bool:
    """Give ``pid`` protection from each of ``qualities``.  One entry each.

    One rules-relevant thing and it asks no questions -- which quality, which
    seat and how long are all the effect layer's business, the way
    `make_unblockable` and `shield_player` are arranged.

    Deduplicated on the whole entry: two copies of Teferi's Protection resolved
    in one turn are two identical records, and a second one changes nothing that
    can be observed. `protection_from` on the object side has the same property
    for free, being a set.
    """

    added = False
    for quality in qualities:
        entry = PlayerProtection(player=pid, quality=str(quality), duration=duration, source=source)
        if entry in state.player_protections:
            continue
        state.player_protections.append(entry)
        added = True
    if added:
        state.bump_chars()
    return added


def set_life_floor(
    state: GameState,
    pid: int,
    floor: int = 1,
    duration: str = "this_turn",
    source: int | None = None,
) -> bool:
    """Stop damage taking ``pid``'s life below ``floor`` for ``duration``.

    Deduplicated on the whole entry, like every table beside it: two Angel's
    Graces in a turn are two identical records and the second changes nothing.
    """

    record = LifeFloor(player=pid, floor=floor, duration=duration, source=source)
    if record in state.life_floors:
        return False
    state.life_floors.append(record)
    return True


def life_floor(state: GameState, pid: int) -> int | None:
    """The highest floor protecting ``pid``, or ``None``.

    The **highest**, because two floors are two prohibitions and the stricter one
    is the one that bites: a floor of 1 and a floor of 3 together mean damage may
    not take you below 3. Short-circuits on the empty list, which is what
    `state.life_floors` is in every game that plays none of these cards -- and it
    is read on every point of damage to a player, so that matters.

    The `damage_life_floor` **static** (Worship, Serra the Benevolent's emblem)
    is asked here too, so the one reader in `damage_player` sees both: the timed
    record an Angel's Grace leaves and the continuous floor a permanent or an
    emblem holds, the highest of all of them biting.
    """

    floors = [record.floor for record in state.life_floors if record.player == pid]
    static = static_life_floor(state, pid)
    if static is not None:
        floors.append(static)
    return max(floors) if floors else None


def clear_life_floors(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the life floors of one duration -- their wearing-off.

    Swept in the same breath as `clear_outcome_locks`, because Angel's Grace
    installs both and says "until end of turn" about both halves.
    """
    state.life_floors = _expired(state.life_floors, duration, player)


def lock_game_outcome(
    state: GameState,
    pid: int,
    *,
    cant_lose: bool = False,
    cant_win: bool = False,
    duration: str = "this_turn",
    source: int | None = None,
) -> bool:
    """Hold ``pid`` in the game, or out of winning it, for ``duration`` -- 104.3b.

    Angel's Grace prints both halves about different seats: "**you** can't lose
    the game this turn and **your opponents** can't win the game this turn", so
    the caller installs one record per seat with the flags that seat needs.

    Deduplicated on the whole entry the way `lock_life_total` is: two Angel's
    Graces in a turn are two identical records and the second changes nothing
    observable.
    """

    lock = OutcomeLock(
        player=pid,
        cant_lose=cant_lose,
        cant_win=cant_win,
        duration=duration,
        source=source,
    )
    if lock in state.outcome_locks:
        return False
    state.outcome_locks.append(lock)
    return True


def lock_life_total(
    state: GameState,
    pid: int,
    duration: str = "until_your_next_turn",
    source: int | None = None,
) -> bool:
    """Freeze ``pid``'s life total for ``duration``.  One rules-relevant thing.

    Deduplicated on the whole entry the way `grant_player_protection` is: two
    Teferi's Protections in a turn are two identical records and the second
    changes nothing observable.
    """

    entry = LifeLock(player=pid, duration=duration, source=source)
    if entry in state.life_locks:
        return False
    state.life_locks.append(entry)
    return True


def lock_casting_zones(
    state: GameState,
    player: int,
    affects: Iterable[int],
    zones: Iterable[str],
    duration: str = "until_your_next_turn",
    source: int | None = None,
) -> bool:
    """Forbid ``affects`` from casting out of ``zones`` for ``duration``.

    "Until your next turn, your opponents can't cast spells from anywhere other
    than their hands" (Avatar's Wrath). One rules-relevant thing: it writes the
    row. *Reading* it back is `primitives.cast_locked_zones`' job, and the four
    roads a cast can take all ask that.

    ``player`` is the clock -- whose next turn ends it -- and ``affects`` is
    who is locked; see :class:`structs.CastLock` on why this is the one timed
    table where those differ.

    An empty ``affects`` or an empty ``zones`` records nothing and returns
    False. Neither is a prohibition: a lock over nobody stops nothing, and a
    lock over no zone is a sentence with its object missing. Writing either
    would leave a row that no reader can act on and that the untap step still
    has to sweep.

    Deduplicated on the whole entry, the way `lock_life_total` is: two copies
    of one sentence say nothing a single one does not.
    """

    if duration not in CAST_LOCK_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown cast lock duration {duration!r}")
    seats = tuple(dict.fromkeys(affects))
    named = tuple(dict.fromkeys(zones))
    if not seats or not named:
        return False
    entry = CastLock(
        player=player, affects=seats, zones=named, duration=duration, source=source
    )
    if entry in state.cast_locks:
        return False
    state.cast_locks.append(entry)
    return True


def clear_cast_locks(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the cast locks of one duration -- their wearing-off.

    The two hooks and two clocks every timed table beside it uses:
    `turn._cleanup_step` for ``this_turn``, `turn._untap_step` for the
    ``until_your_next_turn`` entries belonging to whoever is untapping. The
    second is the one Avatar's Wrath needs, and it is the *caster's* untap step
    -- the row's ``player`` -- not the locked opponents', which is exactly what
    "until **your** next turn" says and why `_expired` is given that field.
    """
    state.cast_locks = _expired(state.cast_locks, duration, player)


def clear_life_locks(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the life locks of one duration -- their wearing-off.

    The two hooks and two clocks every timed table beside it uses, and it is
    swept in the same breath as `clear_player_protections` because one card
    installs both and says "until your next turn" about both halves.
    """
    state.life_locks = _expired(state.life_locks, duration, player)


def grant_flash_permission(
    state: GameState,
    pid: int,
    *,
    types: tuple[str, ...] = (),
    duration: str = "until_your_next_turn",
    source: int | None = None,
) -> None:
    """Let ``pid`` cast spells of ``types`` at instant speed for ``duration``."""

    state.flash_permissions.append(
        FlashPermission(player=pid, types=tuple(types), duration=duration, source=source)
    )


def clear_flash_permissions(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the flash permissions of one duration -- their wearing-off.

    ``until_your_next_turn`` goes in the granting player's untap step, the
    same clock as every other "until your next turn" table, and with them when
    they leave the game; ``this_turn`` goes at cleanup.
    """
    state.flash_permissions = _expired(state.flash_permissions, duration, player)


def clear_outcome_locks(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the outcome locks of one duration -- their wearing-off.

    This is the moment Angel's Grace stops working, and the moment a player it
    held in the game at zero life actually loses: `sba._player_losses` sweeps
    again on the next state-based-action pass and finds the lock gone. 104.3b's
    "you can't lose the game **this turn**" ends here, which is why the clock is
    the cleanup step's rather than an untap step's -- a player saved by it must
    not survive into the next turn.
    """
    state.outcome_locks = _expired(state.outcome_locks, duration, player)


def clear_player_protections(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the player protections of one duration -- their wearing-off.

    The same two hooks on the same two clocks the tables beside it use:
    `turn._cleanup_step` for ``this_turn``, `turn._untap_step` for the
    ``until_your_next_turn`` entries belonging to whoever is untapping. Both
    printed cards say "until your next turn", so the second is the one that
    matters, and it is keyed by the player rather than by a turn number for
    detain's reason: eliminate somebody and "your next turn" moves.
    """
    state.player_protections = _expired(state.player_protections, duration, player)
    state.bump_chars()


def make_unblockable(
    state: GameState,
    objects: Iterable[int],
    duration: str = "this_turn",
    player: int | None = None,
    source: int | None = None,
    except_blockers: Mapping[str, Any] | None = None,
) -> bool:
    """ ""Can't be blocked" for ``duration``, on the creatures named.

    The mirror of :func:`forbid_block`, and everything that function says about
    where the record lives applies here -- but pointing at the *attacker* rather
    than the blocker, so it is a second list and not a flag on the first.

    ``objects`` is fixed when the effect resolves and is never a wildcard: unlike
    "creatures can't block this turn", no printed one-shot grants unblockability
    to everything at once (see :class:`structs.Unblockable`).  An empty
    ``objects`` records nothing and returns ``False`` -- "up to one target
    creature" with no target taken makes nobody unblockable, and there is no
    reading of the empty set that could mean anything else here.

    ``until_your_next_turn`` with no ``player`` is refused for the reason
    :func:`forbid_block` refuses it: nothing would ever clear it, so a printed
    one-turn evasion would silently become a permanent one.

    ``except_blockers`` is the exemption of "can't be blocked this turn except
    by creatures with haste": a static filter the blocker must match, asked by
    `combat.unblockable` against the blocker as it is when blocks are declared.
    ``None`` refuses every blocker.

    Returns whether anything was recorded.  Deduplicated on the whole entry --
    two copies of "can't be blocked" say nothing a single one does not.
    """

    if duration not in UNBLOCKABLE_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown unblockable duration {duration!r}")
    oids = tuple(dict.fromkeys(objects))
    if not oids:
        return False
    if duration == "until_your_next_turn" and player is None:
        return False
    entry = Unblockable(
        objects=oids,
        duration=duration,
        player=player,
        source=source,
        except_blockers=dict(except_blockers) if except_blockers is not None else None,
    )
    if entry in state.unblockables:
        return False
    state.unblockables.append(entry)
    return True


def clear_unblockables(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the "can't be blocked" grants of one duration -- their wearing-off.

    Called from the two hooks `clear_block_prohibitions` is called from, in the
    same breath and on the same clocks: `turn._cleanup_step` for ``this_turn``,
    `turn._untap_step` for the ``until_your_next_turn`` entries belonging to
    whoever is untapping.  Rogue's Passage says "this turn", and the turn it
    means ends at cleanup like every other one.
    """
    state.unblockables = _expired(state.unblockables, duration, player)


def forbid_sacrifice(
    state: GameState,
    objects: Iterable[int],
    duration: str = "this_turn",
    source: int | None = None,
) -> bool:
    """ ""Can't be sacrificed" for ``duration``, on the permanents named.

    One rules-relevant thing and no questions asked: it records the prohibition.
    *Reading* it back is two other modules' job, because a sacrifice happens on
    two different roads and the prohibition has to close both -- see
    :func:`sacrifice_forbidden`.

    ``objects`` is fixed when the effect resolves and is never a wildcard, for
    the reason :func:`make_unblockable`'s is (see
    :class:`structs.SacrificeRestriction`).  An empty ``objects`` records
    nothing and returns ``False``: "you can't sacrifice those creatures" after
    gaining control of none of them protects nobody, and there is no reading of
    the empty set that could mean anything else here.

    Battlefield membership is deliberately **not** checked, unlike
    :func:`goad_creature`'s.  A goad is a mark written onto a permanent and a
    permanent in a graveyard cannot carry one; this is a row in a table, and the
    oid it names is compared against sacrifice pools that only ever contain
    permanents on the battlefield.  A stale oid is inert, and refusing one here
    would mean a creature that flickered out and back is protected or not
    depending on which side of the resolution it blinked -- a distinction the
    printed card does not draw.

    Returns whether anything was recorded.  Deduplicated on the whole entry --
    two copies of "can't be sacrificed" say nothing one does not, and a second
    row would only make the clear-up do the work twice.
    """

    if duration not in SACRIFICE_RESTRICTION_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown sacrifice restriction duration {duration!r}")
    oids = tuple(dict.fromkeys(objects))
    if not oids:
        return False
    entry = SacrificeRestriction(objects=oids, duration=duration, source=source)
    if entry in state.sacrifice_restrictions:
        return False
    state.sacrifice_restrictions.append(entry)
    return True


def sacrifice_forbidden(state: GameState, oid: int) -> bool:
    """Whether ``oid`` may not be sacrificed right now (701.17b).

    The seam the whole capability is read through, and it is asked at the two
    places a player *chooses* what to sacrifice rather than at
    `zones.sacrifice`, which is where a single funnel would have been:

    * `costs._sacrifice_pool` -- the **cost** road.  A sacrifice cost that
      cannot find enough legal fodder is unpayable, so `can_pay` refuses it and
      `legality` never offers the activation or the cast at all.  That is what
      701.17b actually says: the cost becomes unpayable, rather than being paid
      with nothing happening.  `legality._emerge_fodder` is the same road for
      emerge and offering, whose sacrifice is chosen as part of the cast action
      instead of out of a `Cost`.
    * `effects.ops_removal.op_sacrifice` -- the **effect** road.  "Each player
      sacrifices a creature" narrows the pool and the player picks something
      else; with nothing else to pick, the effect does nothing to that player.

    Not in `zones.sacrifice` itself, tempting though the funnel is: that
    function is also how the *game* sacrifices a permanent with no player
    choosing -- 704.5s finishes a Saga -- and `sba._finished_sagas` sets its
    "something changed" flag on the call, so a `sacrifice` that quietly returned
    ``False`` would spin the state-based-action loop for ever.  Making the
    choice illegal is both the rule and the safe reading; making the *action*
    silently fail is neither.

    Asked once per candidate in every sacrifice pool that is built, so the case
    that has to cost nothing is the game playing none of these cards. The
    one-shot table is empty then and `any` over it is free; the static walk
    behind it reads `_battlefield_statics`, which is cached against
    ``char_version`` and is an empty list in the same games.
    """
    if any(oid in entry.objects for entry in state.sacrifice_restrictions):
        return True
    return _forbidden_by_a_static(state, oid)


def _forbidden_by_a_static(state: GameState, oid: int) -> bool:
    """The continuous half: "equipped creature ... can't be sacrificed".

    Assault Suit. The one-shot above is a *table* of permanents named when a
    spell resolved; this is a filter on a permanent that is still on the
    battlefield, and the two cannot be one mechanism for the reason
    `cant_attack_player` and `cant_attack_you` are not one either: a resolving
    sorcery leaves no source for a static to live on, and a static's set is
    recomputed every time it is asked rather than chosen once.

    Which matters here twice over. An Equipment's prohibition has to *end* when
    it is unequipped or leaves, and it has to *move* when it is equipped to
    something else -- neither of which a recorded set can do.

    Read at this seam rather than at `zones.sacrifice`, for the reason the
    docstring above gives: making the choice illegal is the rule (701.17b), and
    making the action silently fail would spin the state-based-action loop.
    """

    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "cant_sacrifice":
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            return True
    return False


def clear_sacrifice_restrictions(state: GameState, duration: str) -> None:
    """Drop the sacrifice prohibitions of one duration -- their wearing-off.

    Called once, from `turn._cleanup_step`, beside `clear_block_prohibitions`,
    `clear_unblockables` and `clear_damage_shields` and on the same clock.  Like
    `clear_damage_shields` and unlike the two block tables it does **not** go
    through :func:`_expired`, and for a simpler reason than that one's: there is
    no ``player`` on the record to filter by, because ``this_turn`` is the only
    duration printed and only the controller of a permanent can sacrifice it
    anyway (see :class:`structs.SacrificeRestriction`).
    """
    if not state.sacrifice_restrictions:
        return
    state.sacrifice_restrictions = [
        r for r in state.sacrifice_restrictions if r.duration != duration
    ]


def shield_player(
    state: GameState,
    pid: int,
    duration: str = "this_turn",
    source: int | None = None,
) -> bool:
    """ "Prevent all damage that would be dealt to you this turn."

    One rules-relevant thing and no questions asked, like every primitive here:
    it records the shield.  *Which* seats are shielded is the effect layer's job,
    which is why this takes a single ``pid`` and the op loops -- "prevent all
    damage that would be dealt to you and to permanents you control" is a
    different sentence and would be a different record, not a wider version of
    this one.

    The record lives on :attr:`GameState.damage_shields` rather than on the
    `PlayerState`, beside the other two timed tables and for the same reason
    they are there: it is a turn-scoped continuous effect owned by no permanent.
    A `PlayerState` field would work for the one duration that exists today and
    would have to move the first time a shield outlived a turn or covered a seat
    that then left the game.

    Deduplicated on the whole entry.  Two copies of "prevent all damage to you
    this turn" say nothing one does not -- there is no pool to add to, since the
    shield is not consumed by use -- and a second entry would only make cleanup
    do the work twice.  A shield over a player who has already lost is refused:
    nothing can be dealt damage after that, so recording one would be a
    permanent no-op sitting in the table.

    Returns whether anything was recorded, so the op can distinguish a shield it
    installed from one it dropped.
    """

    if duration not in DAMAGE_SHIELD_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown damage shield duration {duration!r}")
    if not state.is_alive(pid):
        return False
    entry = DamageShield(player=pid, duration=duration, source=source)
    if entry in state.damage_shields:
        return False
    state.damage_shields.append(entry)
    return True


def shielded(state: GameState, pid: int) -> bool:
    """Whether all damage to ``pid`` is currently being prevented.

    Short-circuits on the empty table, which is every game that plays none of
    these cards -- and this is asked on every point of damage dealt to a player,
    so the empty case is the one that has to cost nothing.
    """
    return any(s.player == pid for s in state.damage_shields)


def shield_permanent(
    state: GameState,
    oid: int,
    dealt: str,
    duration: str = "this_turn",
    player: int | None = None,
    source: int | None = None,
) -> bool:
    """Prevent all damage dealt to and/or by the permanent ``oid`` for ``duration``.

    One rules-relevant thing: it writes a `structs.PermanentShield` onto the
    object.  Reading it back is `permanent_shielded`'s job, and the two damage
    primitives are its only readers.

    Refused, returning ``False``, for a permanent that is no longer on the
    battlefield (it left in response, and a shield on a card in a graveyard
    would ride back with it if `reset_permanent_state` ever stopped clearing
    it), for an ``until_your_next_turn`` shield keyed to nobody or to a seat
    that has left (its clock is never coming), and for an exact duplicate --
    a second copy of the same prevention changes nothing observable.
    """

    if duration not in PERMANENT_SHIELD_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown permanent shield duration {duration!r}")
    if dealt not in PERMANENT_SHIELD_DIRECTIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown permanent shield direction {dealt!r}")
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    if duration == "until_your_next_turn" and (player is None or not state.is_alive(player)):
        return False
    entry = PermanentShield(dealt=dealt, duration=duration, player=player, source=source)
    if entry in obj.damage_shields:
        return False
    obj.damage_shields.append(entry)
    return True


def permanent_shielded(state: GameState, oid: int | None, *, by: bool) -> bool:
    """Is damage dealt **to** (``by=False``) or **by** (``by=True``) ``oid`` prevented?

    Asked on every instance of damage, so the common case -- an object carrying
    no shield -- is one attribute read.  A spell or an object that is not on the
    battlefield never carries one (`reset_permanent_state` clears the list on
    every zone change), so no zone check is needed here.
    """
    if oid is None:
        return False
    obj = state.objects.get(oid)
    if obj is None or not obj.damage_shields:
        return False
    if by:
        return any(shield.stops_damage_by for shield in obj.damage_shields)
    return any(shield.stops_damage_to for shield in obj.damage_shields)


def clear_permanent_shields(state: GameState, duration: str, player: int | None = None) -> None:
    """Drop the permanent shields of one duration -- their wearing-off.

    The two hooks and two clocks of every timed table: `turn._cleanup_step` for
    ``this_turn``, `turn._untap_step` for the ``until_your_next_turn`` shields
    installed by whoever is untapping, and `sba._eliminate` for a seat that will
    never untap again.  Walks the battlefield because the shields live on the
    objects, and only a permanent can carry one.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or not obj.damage_shields:
            continue
        obj.damage_shields = _expired(obj.damage_shields, duration, player)


def fog_combat_damage(
    state: GameState,
    controller: int,
    by: Mapping[str, Any] | None = None,
    duration: str = "this_turn",
    source: int | None = None,
) -> None:
    """Prevent combat damage dealt this turn by sources matching ``by``.

    One rules-relevant thing: it records the `CombatFog`. Reading it is
    `combat_fogged`'s job, asked by both damage primitives.
    """
    if duration not in COMBAT_FOG_DURATIONS:  # pragma: no cover - loader guards
        raise ValueError(f"unknown combat fog duration {duration!r}")
    entry = CombatFog(
        by=dict(by) if by is not None else None,
        controller=controller,
        duration=duration,
        source=source,
    )
    if entry not in state.combat_fogs:
        state.combat_fogs.append(entry)


def combat_fogged(state: GameState, source_oid: int | None) -> bool:
    """Is combat damage dealt by ``source_oid`` being prevented right now?

    ``by`` is read off the source's **current** characteristics, as the damage
    would be dealt (615.1): a creature that became a Spider after the fog
    resolved is spared it, and one that stopped being one is not. Asked on
    every instance of combat damage, so the empty table costs nothing.
    """
    if not state.combat_fogs:
        return False
    # Deferred: the effect layer imports this module.
    from .effects.context import EffectContext
    from .effects.selectors import matches

    for fog in state.combat_fogs:
        if fog.by is None:
            return True
        if source_oid is None:
            continue
        # The effect-side selector, which reads derived characteristics and
        # says "non-Spider" (`not_subtypes`); "you" is the fog's controller.
        ctx = EffectContext(state=state, controller=fog.controller, source_oid=fog.source)
        if matches(ctx, source_oid, fog.by):
            return True
    return False


def clear_combat_fogs(state: GameState, duration: str) -> None:
    """Drop the combat fogs of one duration, at cleanup with the damage shields."""
    if state.combat_fogs:
        state.combat_fogs = [f for f in state.combat_fogs if f.duration != duration]


def clear_damage_shields(state: GameState, duration: str) -> None:
    """Drop the damage shields of one duration -- their wearing-off.

    Called once, from `turn._cleanup_step`, beside `clear_block_prohibitions`
    and `clear_unblockables` and on the same clock.  It does **not** go through
    :func:`_expired` despite the identical shape, and the difference is the
    ``player`` field: on the other two tables that field means "whose next turn
    ends this", while a `DamageShield`'s is the seat being protected.  Sharing
    the helper would read correctly today -- the only caller passes no player --
    and would silently mean the wrong thing the first time anybody passed one.
    """
    if not state.damage_shields:
        return
    state.damage_shields = [s for s in state.damage_shields if s.duration != duration]


def _expired(entries: list, duration: str, player: int | None):
    """The entries of a timed table that survive one wearing-off.

    Shared by the two clear-ups above because the rule is the same and the two
    lists are the same shape: an entry goes when its ``duration`` is the one
    being cleared, and -- when a ``player`` is named, which is only ever for
    ``until_your_next_turn`` -- when it is that player's.  Returns a new list
    rather than mutating, and short-circuits on the empty one, which is the
    normal case in a game that plays none of these cards.
    """
    if not entries:
        return entries
    return [
        e for e in entries if e.duration != duration or (player is not None and e.player != player)
    ]


#: A walker requirement recorded but not yet in force: "during target
#: opponent's **next** turn" starts when that player next untaps, not now.
ATTACK_REQUIREMENT_PENDING = -1


def require_attack_on(state: GameState, walker: int, player: int) -> bool:
    """ "During target opponent's next turn, creatures that player controls
    attack Gideon Jura if able." One rules-relevant thing: it writes the mark.

    The mark lives on the **planeswalker** (`GameObject.must_be_attacked_by`),
    keyed by the compelled player, for goad's reason: the effect names that
    object, and 400.7 ends it when the object leaves -- `reset_permanent_state`
    clears the field. It is **pending** until ``player``'s next untap step arms
    it with that turn's number (`arm_attack_requirements`), and it ends in that
    turn's cleanup (`clear_attack_requirements`).

    Refused, returning ``False``, for a walker no longer on the battlefield, a
    player out of the game (their turn is never coming), and the walker's own
    controller (a creature cannot attack its own controller's planeswalker).
    """
    obj = state.objects.get(walker)
    if obj is None or not obj.on_battlefield:
        return False
    if not state.is_alive(player) or obj.controller == player:
        return False
    obj.must_be_attacked_by[player] = ATTACK_REQUIREMENT_PENDING
    return True


def arm_attack_requirements(state: GameState, player: int) -> None:
    """Start every pending walker requirement on ``player`` -- their turn has come.

    Called from `turn._untap_step` for the untapping player. "Next turn" is
    whichever turn of theirs comes next, which a turn *number* could not say
    when somebody is eliminated in between -- so the mark waits, pending, for
    the player rather than for a number.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or not obj.must_be_attacked_by:
            continue
        if obj.must_be_attacked_by.get(player) == ATTACK_REQUIREMENT_PENDING:
            obj.must_be_attacked_by[player] = state.turn


def clear_attack_requirements(state: GameState) -> None:
    """End the walker requirements that were in force this turn -- cleanup.

    Only the armed ones whose turn is the one ending; a pending mark (installed
    this turn, for the opponent's *next* turn) survives.
    """
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or not obj.must_be_attacked_by:
            continue
        obj.must_be_attacked_by = {
            pid: turn
            for pid, turn in obj.must_be_attacked_by.items()
            if turn != state.turn
        }


def drop_attack_requirements(state: GameState, player: int) -> None:
    """Forget every walker requirement on ``player`` -- they have left the game."""
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is not None and player in obj.must_be_attacked_by:
            del obj.must_be_attacked_by[player]
