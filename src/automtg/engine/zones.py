"""Zone changes -- the one place objects move between zones.

Everything that removes a card from one zone and puts it in another goes through
:func:`move_object`, so enters/leaves/dies triggers, permanent-state resetting,
the commander zone-change replacement and characteristic-cache invalidation all
happen in exactly one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import sagas
from .carddef import CardDef
from .characteristics import chars
from .effects.conditions import evaluate_condition
from .effects.context import EffectContext
from .effects.values import evaluate_value
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
    to_index: int | None = None,
    tapped: bool = False,
    cause: str = "",
    by: int | None = None,
) -> GameObject:
    """Move an object to another zone, firing every consequent event.

    ``to_player`` defaults to the object's *owner*, which is where cards always
    go in Commander (a card put into "its owner's graveyard" never lands in
    someone else's).

    ``to_index`` is a **library position**, counted from the top with 0 meaning
    the top card -- "into its owner's library second from the top" (Hinder) and
    "fourth from the top" (Lost to Legend).  It outranks ``to_top``, which is
    the same thing said as a boolean and is kept because thirty-odd callers say
    it.  Ignored for every zone but a library: a graveyard and an exile are
    unordered piles as far as any rule the engine models is concerned.

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

    # -- "if it would die this turn, exile it instead" ----------------------
    # Gallifrey Falls, Anger of the Gods, the whole exile-wrath family. Applied
    # here rather than in `destroy` because the printed word is **die**, which
    # is broader than "be destroyed": a creature sacrificed, or one whose
    # toughness went to zero, has also died, and neither of those routes through
    # `destroy` at all. This is the single funnel every one of them shares.
    #
    # After the commander replacement above, which outranks it: a commander that
    # would be exiled instead of dying still goes to the command zone if its
    # owner says so (903.9a replaces the *new* destination, not the old one).
    if (
        obj.dies_to
        and from_zone is Zone.BATTLEFIELD
        and to_zone is Zone.GRAVEYARD
    ):
        to_zone = Zone(obj.dies_to)
        target_player = owner

    # "…or **if it would leave the battlefield**" -- unearth. The whole
    # departure and not just the death: bounced, exiled, shuffled away, sent to
    # the command zone. After `dies_to` so the wider clause wins when a card
    # carries both, which changes nothing when they name the same zone and is
    # the right way round when they do not -- this one is what the card printed
    # about *leaving*, and dying is one way of leaving.
    if obj.leaves_to and from_zone is Zone.BATTLEFIELD:
        to_zone = Zone(obj.leaves_to)
        target_player = owner

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
    # "…create a number of Treasure tokens equal to **its power**" (Goldvein
    # Hydra), asked about a creature that has just died. `power_of {"self":
    # true}` reads `chars()`, and by the time the trigger resolves the object is
    # a graveyard card: `reset_permanent_state` has cleared its counters and no
    # anthem applies to it any more, so it answers with the printed line -- 0
    # for a Hydra. `counters_had` recovers only the +1/+1 counters, which is a
    # different number the moment a pump spell, an anthem or a -1/-1 counter is
    # involved.
    #
    # Snapshotted here, beside `had_counters`, for exactly its reason and at
    # exactly its moment: this is the engine's explicit-LKI pattern in the one
    # place a card cannot reach with a `snapshot` op of its own, because that op
    # runs at resolution and the creature is already gone. Deliberately *not* a
    # global last-known-information system; see docs/rules-coverage.md.
    if was_on_battlefield:
        _seen = chars(state, oid)
        had_power, had_toughness = _seen.power, _seen.toughness
    else:
        had_power = had_toughness = 0
    # Who sacrificed it, snapshotted with the rest: `reset_permanent_state` puts
    # control back to the owner on the way out, and "whenever **you** sacrifice"
    # is about the player who did it -- a different answer for a stolen
    # permanent.
    controller_before = obj.controller

    # Mutate: the pile goes where the permanent goes (702.140f). Read *before*
    # anything else, because `reset_permanent_state` below clears the list a
    # moment later -- the same snapshot `had_counters` needs and for the same
    # reason.
    merged = tuple(obj.merged_under) if was_on_battlefield else ()
    # The until-end-of-turn effects this object was carrying, snapshotted for
    # the same reason `had_counters` is: `reset_permanent_state` empties
    # `until_eot` a few lines below and the leave-the-battlefield events fire
    # *after* that. A triggered ability granted until end of turn -- Malakir
    # Rebirth's "that creature gains 'when this creature dies, return it'" --
    # would otherwise be gone before its own death event went out, every time.
    left_with = (
        (*obj.until_eot, *obj.granted_abilities_permanent) if was_on_battlefield else ()
    )

    _remove_from_zone(state, obj)

    if was_on_battlefield:
        _detach_all(state, oid)

    obj.zone = to_zone
    if to_zone is not Zone.BATTLEFIELD or from_zone is not Zone.BATTLEFIELD:
        obj.reset_permanent_state()

    obj.left_with = left_with
    _add_to_zone(state, obj, to_zone, target_player, to_top=to_top, to_index=to_index)
    state.bump_chars()

    # The cards that were underneath follow, each to its own owner's copy of the
    # zone. They were in no zone list while merged, so this is the first move
    # any of them has made since resolving -- and it goes through this same
    # function, so each fires its own zone-change event and each ends up
    # somewhere a card can legally be.
    for merged_oid in merged:
        merged_obj = state.objects.get(merged_oid)
        if merged_obj is None:
            continue
        merged_obj.merged_into = None
        # Straight to the destination rather than recursing through the
        # battlefield: a card under a pile was never *on* the battlefield in the
        # sense that matters here, so it has no leaves-the-battlefield trigger
        # of its own to fire.
        merged_obj.zone = to_zone
        merged_obj.reset_permanent_state()
        _add_to_zone(
            state, merged_obj, to_zone, merged_obj.owner, to_top=to_top, to_index=to_index
        )

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

    # "Whenever one or more cards leave your graveyard" -- Spirit Mascot, Cyan.
    # Narrow on purpose: `ZONE_CHANGE` above records *every* move and stays off
    # the trigger bus, because routing it through `fire` would run the trigger
    # scan on every draw, discard and shuffle in the game.
    #
    # Tokens are excluded for the reason the ledger excludes them: a token in a
    # graveyard ceases to exist as a state-based action, and that is not a card
    # leaving. `player` is the graveyard's **owner** (400.3), so "your
    # graveyard" is answered about the yard rather than about whoever moved the
    # card -- an opponent's graveyard hate still fires your Mascot.
    if (
        from_zone is Zone.GRAVEYARD
        and to_zone is not Zone.GRAVEYARD
        and not obj.is_token
    ):
        fire(
            state,
            EventType.LEAVES_GRAVEYARD,
            player=owner,
            source=oid,
            oid=oid,
            card=card.id,
            batch=state.event_batch,
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
            had_power=had_power,
            had_toughness=had_toughness,
        )
        # "Whenever you sacrifice a token…" -- fired beside DIES rather than
        # instead of it, because a sacrificed permanent really does die and
        # everything listening for that must still hear it. `controller` is the
        # player who sacrificed, which is what "whenever **you** sacrifice"
        # asks; `owner` would be the wrong question for a stolen permanent.
        if cause == "sacrificed":
            fire(
                state,
                EventType.SACRIFICED,
                player=controller_before,
                source=oid,
                oid=oid,
                card=card.id,
                was_creature=was_creature,
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
                had_power=had_power,
                had_toughness=had_toughness,
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
    state: GameState,
    obj: GameObject,
    zone: Zone,
    pid: int,
    *,
    to_top: bool = False,
    to_index: int | None = None,
) -> None:
    if zone is Zone.BATTLEFIELD:
        state.battlefield.append(obj.oid)
        return
    if zone is Zone.STACK:
        # Stack membership is managed by stack.py, which owns the StackItem list.
        return
    lst = state.players[pid].zone_list(zone)
    if to_index is not None and zone is Zone.LIBRARY:
        # Clamped by hand rather than left to `list.insert`, which is forgiving
        # in one direction and actively wrong in the other: an index past the
        # end already appends, but a **negative** one counts back from the
        # bottom, so a card asked for "first from the top" with a depth read off
        # an empty board would land second from the *bottom* and nothing would
        # ever say so. The upper clamp is the printed rule for a short library:
        # a card put fourth from the top of a two-card library goes as deep as
        # it can, which is the bottom.
        lst.insert(max(0, min(int(to_index), len(lst))), obj.oid)
    elif to_top and zone is Zone.LIBRARY:
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
            # Remembered, because this runs *before* LEAVES_BATTLEFIELD and DIES
            # fire: a "whenever equipped creature dies" trigger asked about
            # `attached_to` here would find nothing, every time.
            other.last_attached_to = oid
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
    # "…**if it was cast**" (603.6e). Written here, before the replacements and
    # long before the ENTERS_BATTLEFIELD event below, because the trigger's own
    # intervening-if is evaluated as the ability queues off that event.
    #
    # Written on *every* arrival, so it describes this trip and no other:
    # `cast_step` and the other `cast_*` stamps are set once by
    # `stack.push_spell` and never cleared, and a permanent that was cast, died
    # and came back would still answer to them.
    #
    # `cause == "resolved"` alone is not the clause either. A **copy** of a
    # permanent spell resolves the same way and was never cast (707.10), and it
    # is a fresh object with no cast stamp on it -- so the two halves together
    # are what the sentence says, and each one alone is a wider card.
    obj.entered_by_cast = cause == "resolved" and obj.cast_step is not None
    # A fresh arrival answers for nothing that happened before it.
    obj.left_with = ()

    for replacement in card.replacements:
        event = replacement.get("event")
        # "…unless you control a Mountain or a Plains" (614.12). Evaluated here
        # rather than by a static, because the answer is only ever asked once
        # and the board it is asked about is the one the permanent is arriving
        # on -- `_add_to_zone` has already run, so `exclude_self` is what makes
        # "two or more *other* lands" count the right number.
        if not evaluate_condition(
            state, replacement.get("condition"), controller=obj.controller, source=obj.oid
        ):
            continue
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
            # "…for each other Human you control" (Éomer, King of Rohan). The
            # amount is a value expression, evaluated on the board the permanent
            # is arriving on with the arrival as the source -- the same context
            # the condition above is judged in, so `exclude_self` means "other"
            # and the count is the one 614.1c says the permanent is never seen
            # without.  A trigger running `add_counters` could not do this: it
            # would put the permanent on the battlefield at its printed size
            # first, and on Éomer, whose other enters trigger deals damage equal
            # to his power, the whole payload would turn on trigger ordering.
            # "This creature enters with **X** +1/+1 counters on it" (Goldvein
            # Hydra). `cast_x` is written by `stack.resolve` before the move and
            # is one of the few fields `reset_permanent_state` deliberately does
            # not clear, so the X the player announced is still readable here --
            # it simply was never passed in, and `{"x": true}` quietly evaluated
            # to 0. A printed 0/0 Hydra then arrived as a 0/0 and was binned by
            # state-based actions before anything could grow it.
            #
            # This is why 614.1c wants a replacement rather than a `self_enters`
            # trigger running `add_counters`: the permanent is never seen at its
            # printed size, so it is never seen dead.
            ctx = EffectContext(
                state=state,
                controller=obj.controller,
                source_oid=obj.oid,
                x=obj.cast_x,
            )
            counters = (replacement.get("modify") or {}).get("counters") or {}
            if counters:
                for kind, amount in counters.items():
                    obj.add_counter(str(kind), evaluate_value(ctx, amount))
            else:
                obj.add_counter(
                    str(replacement.get("counter", "+1/+1")),
                    evaluate_value(ctx, replacement.get("amount", 1)),
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
    # A Saga entered with its first lore counter (714.2b), so chapter I triggers
    # (714.2c). The counter itself was put on by the replacement loop above, which
    # writes to the object directly and fires nothing -- so unlike every other
    # route to a lore counter there is no `add_counters` call to reach the chapter
    # comparison through, and this is the one place that says so.
    sagas.entered(state, obj)


# ----------------------------------------------------------------------
# convenience wrappers
# ----------------------------------------------------------------------


def destroy(
    state: GameState,
    oid: int,
    *,
    cause: str = "destroyed",
    by: int | None = None,
    no_regeneration: bool = False,
) -> bool:
    """Destroy a permanent unless something replaces the destruction.

    Four things can stop it, and they are four different mechanisms rather
    than one with a parameter:

    | | |
    |---|---|
    | `indestructible` | the destruction simply does not happen |
    | a **shield counter** (122.1c) | one counter is removed and nothing else changes |
    | a **regeneration** shield (701.15) | it is tapped, removed from combat and its damage removed, and one shield is spent |
    | **totem armor** (702.88a) | its damage is removed and the *Aura* is destroyed instead |

    A shield counter is checked **after** indestructible and **before**
    regeneration, and both halves of that are deliberate. Indestructible is not
    a replacement that consumes anything -- the destruction never happens -- so
    a permanent that survives on it must not be charged a counter, exactly as it
    is not charged a regeneration shield. Against regeneration, 616.1 would let
    the affected player choose between two replacements of the same event and
    the engine does not model that choice; the counter goes first because it is
    strictly the cheaper one, costing no tap, no removal from combat and no
    marked damage, so it is the one its controller would pick.

    It is **not indestructible**: a shielded permanent whose counters have run
    out falls straight through to the destruction. `no_regeneration` does not
    touch it either -- "it can't be regenerated" names regeneration, and a
    shield counter is a different replacement, the same way indestructible and
    totem armor are. Nor does a shield counter save anything from **sacrifice**
    (701.16b) or from 0 toughness, which is the absence of a rule rather than
    one: neither destroys, so neither reaches this function.

    Regeneration and totem armor are checked here rather than as `replacements`
    entries because that whitelist is about a permanent *entering the
    battlefield*, and this is the moment one leaves. Everything that destroys --
    the lethal-damage state-based action, the `destroy` op, deathtouch -- already
    routes through this function, which is what makes one check enough.

    Regeneration is checked **before** totem armor: a regenerating creature does
    not leave the battlefield at all, so nothing has happened for the Aura to
    replace. Ordered the other way, a Rancor-style shield would be eaten by a
    creature that was going to survive anyway.

    ``no_regeneration`` is the printed "It can't be regenerated." -- 701.15c:
    regeneration shields are simply **not applied** to this destruction. Note
    what it does *not* touch, because each is a card that would otherwise read
    wrong: the shield is not spent (the effect stops it applying, it does not
    consume it, so a creature that survives on indestructible keeps it);
    indestructible still saves the permanent, because that is a different
    replacement and Terminate has never beaten it; and totem armor still
    applies, for the same reason.

    A parameter rather than a mark on the object, and that is the whole reading
    of the sentence: "it can't be regenerated" belongs to *this* destruction.
    Marked on the permanent for the turn it would also cover the destruction
    that never happened -- an indestructible creature Terminated would go on
    being unregeneratable afterwards, which the printed card does not say. The
    turn-long form ("a creature dealt damage this way can't be regenerated this
    turn") is a different sentence and is not implemented.

    Returns True only if the permanent actually died.
    """
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return False
    if "indestructible" in chars(state, oid).keywords:
        return False
    # A shield counter (122.1c). Imported here rather than at the top because
    # `primitives` imports *this* module for `move_object`; the cycle is real and
    # the function is the natural home for a counter mutation.
    from .primitives import spend_shield_counter

    if spend_shield_counter(state, oid, source=by):
        return False
    if obj.regeneration_shields > 0 and not no_regeneration:
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
