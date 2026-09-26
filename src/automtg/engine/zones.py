"""Zone changes -- the one place objects move between zones.

Everything that removes a card from one zone and puts it in another goes through
:func:`move_object`, so enters/leaves/dies triggers, permanent-state resetting,
the commander zone-change replacement and characteristic-cache invalidation all
happen in exactly one place.
"""

from __future__ import annotations

from collections.abc import Mapping
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
    as_face: str | None = None,
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

    ``as_face`` is ``"front"`` or ``"back"`` and says which face a double-faced
    permanent **arrives** as -- "return it to the battlefield transformed"
    (Joshua, Phoenix's Dominant) and "return it to the battlefield (front face
    up)" on the other side of the same card. It has to be a parameter here and
    cannot be set by the caller afterwards, twice over: `reset_permanent_state`
    clears `transformed` on the way in, and the arriving face is what every
    enters-replacement and enters-trigger must see -- a Saga's lore counter is a
    replacement on the back face, so a permanent that turned over one line later
    would already have entered as something else.
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

    # -- "if this artifact would enter … instead" (614.1a) ------------------
    # Mox Diamond. The only replacement in the DSL that replaces the **arrival
    # itself** rather than decorating a permanent that is already arriving, so
    # it is the only one that cannot live in `_enter_battlefield`: by the time
    # that function runs the object is on the battlefield, every enters trigger
    # is about to see it, and the card says it was never there.
    #
    # The question was asked a moment ago by `offer_enters_replacement`, which
    # left its answer on the object; this reads it. An arrival that got here
    # without being asked counts as unpaid -- see the field's note.
    #
    # Before the commander replacement below on purpose: 903.9a replaces the
    # *new* destination, so a commander Mox that was not paid for is redirected
    # to a graveyard here and then to the command zone there, which is the two
    # replacements applied in the order the rules apply them.
    if to_zone is Zone.BATTLEFIELD and from_zone is not Zone.BATTLEFIELD:
        replaced = _arrival_replacement(card)
        paid = obj.enters_replacement_paid
        obj.enters_replacement_paid = False
        # 707.2: a permanent put onto the battlefield face down has no
        # abilities at all, so it has no replacement either. `face_down` is
        # written *after* the move by both routes -- `stack._place_after_resolution`
        # for a morph and `ops_counters.op_manifest` for a manifest -- so the
        # flag cannot be read here and the two are named instead.
        face_down = obj.pending_face_down or cause == "manifest"
        if replaced is not None and not paid and not face_down:
            to_zone = Zone(str(replaced.get("instead_zone", "graveyard")))
            target_player = owner
            # Overwritten rather than defaulted: "resolved" is how the card got
            # here and no longer how it is leaving, and the log line a player
            # needs is the one saying the arrival was replaced.
            cause = "enters_replaced"

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
        # And for the same reason, into any record a cost made of this
        # permanent: Station reads "the tapped creature's power" at resolution,
        # as the creature last existed on the battlefield if it has gone. See
        # `costs.bind_paid_object`. A record already filled in belongs to an
        # earlier departure -- the creature left, came back as a new object
        # (400.7) and is leaving again -- and keeps the answer it had.
        for record in state.paid_objects.values():
            if record["oid"] == oid and record["power"] is None:
                record["power"], record["toughness"] = had_power, had_toughness
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
    # "If that mana is spent on a creature spell, **it gains haste until end of
    # turn**" (Arena of Glory). Snapshotted for `left_with`'s reason and carried
    # the other way: `reset_permanent_state` empties it a few lines below, and
    # the promise is owed to the permanent the spell is *becoming*. Restored
    # only for a battlefield destination, so a countered creature spell does not
    # sit in its graveyard holding a haste to cash on a later cast.
    mana_granted_keywords = obj.mana_granted_keywords

    _remove_from_zone(state, obj)

    if was_on_battlefield:
        _detach_all(state, oid)

    obj.zone = to_zone
    if to_zone is not Zone.BATTLEFIELD or from_zone is not Zone.BATTLEFIELD:
        obj.reset_permanent_state()

    if as_face is not None:
        # After the reset, which clears `transformed`, and before anything reads
        # the arriving object: `card` is recomputed below so the replacements
        # and the enters event see the face that is actually arriving.
        obj.transformed = as_face == "back"
        card = state.card_of(obj)

    obj.left_with = left_with
    if to_zone is Zone.BATTLEFIELD:
        obj.mana_granted_keywords = mana_granted_keywords
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

    # "…put there from anywhere other than the battlefield **this turn**" --
    # Banon. Recorded per card as it arrives, because the turn ledger's count is
    # a bare integer over every graveyard and cannot say which card or whence.
    if to_zone is Zone.GRAVEYARD and from_zone is not Zone.GRAVEYARD:
        obj.graveyard_turn = state.turn
        obj.graveyard_from = from_zone.value

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
        _enter_battlefield(
            state, obj, card, forced_tapped=tapped, cause=cause, from_zone=from_zone
        )

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



def _arrival_replacement(card: CardDef) -> Mapping[str, Any] | None:
    """The card's ``self_enters_replaced`` replacement, if it has one.

    One per card: two clauses each replacing the same arrival would have to be
    applied in some order, and no printed card asks that question. The first
    written wins, which is the answer the loader's ordering already gives every
    other replacement.
    """
    for replacement in card.replacements:
        if replacement.get("event") == "self_enters_replaced":
            return replacement
    return None


def offer_enters_replacement(state: GameState, oid: int, controller: int):
    """"If this artifact would enter, you may discard a land card instead."

    Mox Diamond. Asked here, beside `offer_enters_costs` and `offer_enters_copy`
    and for their stated reason -- `move_object` is not a generator and cannot
    stop for a decision, and making it one would put a suspend point inside
    every zone change in the engine. Asking a moment early is not an
    approximation: 614 applies the replacements during the zone change and
    nobody receives priority in between.

    **Called from every arrival path that can stop to ask**, not only from the
    cast line, and that is the whole of this function's design. A version wired
    into `stack._place_after_resolution` alone would be right for a Mox Diamond
    cast out of hand and wrong for every blink and every reanimation in the
    format -- the card says "if this artifact **would enter**", which is any
    arrival from any zone, and a permanent returned by Animate Dead is arriving
    exactly as hard as one that was cast.

    The answer is left on `obj.enters_replacement_paid`, which
    `reset_permanent_state` deliberately does not clear and `move_object` reads
    and clears as it decides where the card is actually going. Unlike its two
    neighbours this answer is *not* read by `_enter_battlefield`: that runs
    after the object is on the battlefield, and an unpaid Mox never gets there.

    An unaffordable price is not offered, exactly as `offer_enters_costs` does
    not offer one: a player with no land in hand is not asked a question whose
    "yes" cannot be honoured, and the permanent goes to `instead_zone`.
    """
    from .carddef import Cost
    from .costs import can_pay, pay
    from .effects.context import ask_yes_no

    obj = state.objects.get(oid)
    if obj is None:
        return
    card = state.card_of(obj)
    replacement = _arrival_replacement(card)
    if replacement is None:
        return
    cost = Cost.from_spec(replacement.get("instead_cost"))
    # `source_oid` is the arriving card itself, which is what keeps a Mox
    # Diamond in hand from being its own discard: `costs._discard_pool` drops
    # the source from the pool for 601.2a's reason, and the same exclusion is
    # the right one here for 614's -- the object being replaced is the one on
    # its way to the battlefield, not fodder sitting in a hand.
    if not can_pay(state, controller, cost, oid):
        return
    ctx = EffectContext(
        state=state, controller=controller, source_oid=oid, source_name=card.name
    )
    prompt = f"Pay {card.name}'s cost to have it enter?"
    if not (yield from ask_yes_no(ctx, prompt, controller)):
        return
    if (yield from pay(state, controller, cost, oid)):
        obj.enters_replacement_paid = True


def offer_enters_costs(state: GameState, oid: int, controller: int):
    """"As this enters, you may pay 3 life." Ask, and pay if the answer is yes.

    Called **just before** `move_object` by whichever path is putting the
    permanent onto the battlefield -- `game._play_land` for a land drop,
    `stack._place_after_resolution` for a permanent spell. Both are generators
    already; `move_object` is not, and making it one would put a suspend point
    inside every zone change in the engine.

    Asking a moment early is not an approximation. 614 applies the replacements
    during the zone change and nobody receives priority in between, so there is
    no window in which the permanent exists with the question unanswered -- the
    same argument `_play_land` already makes for setting `showing_second_face`
    before the move.

    The answer is left on `obj.enters_cost_paid`, which
    `reset_permanent_state` deliberately does not clear and
    `_enter_battlefield` clears once the replacements have read it.

    An unaffordable price is not offered: `can_pay` is asked first, so a player
    at 2 life is never shown a question whose yes would kill them and whose
    payment would fail anyway.
    """
    from .carddef import Cost
    from .costs import can_pay, pay
    from .effects.context import ask_yes_no

    obj = state.objects.get(oid)
    if obj is None:
        return
    card = state.card_of(obj)
    for replacement in card.replacements:
        node = replacement.get("unless_cost")
        if not node:
            continue
        cost = Cost(**node) if not isinstance(node, Cost) else node
        if not can_pay(state, controller, cost, oid):
            continue
        ctx = EffectContext(
            state=state, controller=controller, source_oid=oid, source_name=card.name
        )
        if not (yield from ask_yes_no(ctx, f"Pay {card.name}'s cost as it enters?", controller)):
            continue
        if (yield from pay(state, controller, cost, oid)):
            obj.enters_cost_paid = True


def offer_enters_copy(state: GameState, oid: int, controller: int):
    """"You may have this enter **as a copy** of any Equipment on the battlefield."

    Masterwork of Ingenuity, Vesuva, Phyrexian Metamorph. Asked here, beside
    `offer_enters_costs` and from the same two call sites, for that function's
    stated reason: `move_object` is not a generator and cannot stop for a
    decision, and making it one would put a suspend point inside every zone
    change in the engine.

    Asking a moment early is not an approximation, and the argument is the one
    `offer_enters_costs` makes: 614 applies the replacements *during* the zone
    change and nobody receives priority in between, so there is no window in
    which the permanent exists with the question unanswered. That is the whole
    point of the clause -- 614.1b means the permanent is **never seen as
    itself**, which is the difference between this and a `self_enters` trigger
    running `become_copy`. Written that way, Masterwork would arrive as a blank
    Equipment, everything watching an Equipment enter would see the blank, and
    anything that answered the trigger would answer it before the copy existed.

    `copy_permanent` is not the mechanism either: it calls `create_token` and
    makes a *new* permanent, where Masterwork has to enter as the real card --
    it stays a card, it can be equipped and returned, and its copy is set as it
    arrives.

    Always an offer: every printed card in this family says "you may", and a
    copy nobody was asked about would be a different card. An empty pool asks
    nothing, which is the printed answer with no Equipment on the table.

    The answer is left on `obj.enters_copy_of`, which `reset_permanent_state`
    deliberately does not clear and `_enter_battlefield` clears once it has
    turned it into `copying`.
    """
    from .effects.context import EffectContext, ask_objects, ask_yes_no

    obj = state.objects.get(oid)
    if obj is None:
        return
    card = state.card_of(obj)
    for replacement in card.replacements:
        if replacement.get("event") != "self_enters_as_copy":
            continue
        selector = replacement.get("copying") or {}
        ctx = EffectContext(
            state=state, controller=controller, source_oid=oid, source_name=card.name
        )
        from .effects.selectors import resolve_pool

        # `exclude_self` is implicit and structural rather than written: the
        # permanent is still on its way in and is not on the battlefield, so a
        # battlefield selector cannot find it. 706.2's "it copies nothing else"
        # needs no help here.
        pool = resolve_pool(ctx, selector)
        if not pool:
            continue
        if not (
            yield from ask_yes_no(
                ctx, f"Have {card.name} enter as a copy of another permanent?", controller
            )
        ):
            continue
        chosen = yield from ask_objects(
            ctx,
            f"Copy which permanent for {card.name}?",
            pool,
            1,
            1,
            controller,
            purpose="enters_as_copy",
        )
        if not chosen:
            continue
        model = state.objects.get(chosen[0])
        if model is not None:
            obj.enters_copy_of = state.card_of(model).id
        return


#: Riot's two halves, in the order the reminder text prints them.
RIOT_COUNTER, RIOT_HASTE = "counter", "haste"


def offer_riot_choice(state: GameState, oid: int, controller: int):
    """Riot (702.113): "with your choice of a +1/+1 counter or haste."

    Rhythm of the Wild's "nontoken creatures you control have riot", and the
    printed cycle that carries the word itself. Asked here, beside
    `offer_enters_costs`, `offer_enters_copy` and `offer_enters_replacement`,
    and for their stated reason: `move_object` is not a generator and cannot
    stop for a decision, and making it one would put a suspend point inside
    every zone change in the engine.

    Asking a moment early is not an approximation, and it is the whole of the
    keyword. 614.1c applies the replacement **during** the zone change and
    nobody receives priority in between, so there is no window in which the
    creature exists with the question unanswered -- which is exactly what a
    `self_enters` trigger running `choose_mode` over `add_counters` and
    `grant_keyword` could not promise. Written that way the creature arrives at
    its printed size first: a 0/0 that is only alive because of the counter is
    binned by state-based actions before the trigger resolves, every other
    enters trigger reads a size riot says was never on the board, and an
    opponent holds priority with a creature that should never have been seen
    without its counter.

    **Per creature, and the controller's.** Two riot creatures entering
    together are two questions, because the choice is part of each arrival
    rather than a mode of the effect that made them.

    The answer is left on `obj.riot_choice`, which `reset_permanent_state`
    deliberately does not clear and `_enter_battlefield` reads and clears as
    the permanent arrives. An arrival that reached `move_object` without being
    asked -- a token, whose creation is not a generator -- records no choice and
    gets neither half, which is the printed card this unblocks anyway: Rhythm of
    the Wild says **nontoken**.
    """
    from .characteristics import keyword_as_it_enters
    from .effects.context import ask_mode

    obj = state.objects.get(oid)
    if obj is None:
        return
    if not keyword_as_it_enters(state, oid, Keyword.RIOT.value):
        return
    card = state.card_of(obj)
    # "…**creatures** you control have riot." Riot on a noncreature permanent is
    # a keyword with nothing to do: a +1/+1 counter on an enchantment changes no
    # characteristic anything reads, and haste is a fact about attacking and
    # tapping a *creature*. Read off the printed face, because the object is not
    # a permanent yet and the layer pipeline has nothing to say about it -- the
    # same face `keyword_as_it_enters` matched the granting static against.
    if "Creature" not in card.types:
        return
    ctx = EffectContext(
        state=state, controller=controller, source_oid=oid, source_name=card.name
    )
    chosen = yield from ask_mode(
        ctx,
        f"{card.name} enters with a +1/+1 counter, or with haste?",
        ["A +1/+1 counter", "Haste"],
        controller,
    )
    obj.riot_choice = RIOT_HASTE if chosen and chosen[0] == 1 else RIOT_COUNTER


def _apply_board_enters_tapped(state: GameState, obj: GameObject) -> None:
    """"Creatures your opponents control enter tapped." Authority of the Consuls.

    The whole family -- Imposing Sovereign, Kismet, Frozen Aether, Loxodon
    Gatekeeper, Root Maze, Orb of Dreams, Thalia Heretic Cathar -- and the one
    thing a card's own ``replacements`` can never say. That list is a closed
    ``self_*`` Literal read off the **arriving** card, so every branch of it
    speaks about itself; `self_enters_tapped` on Authority taps the enchantment
    and leaves the opponents alone. This is the other direction: a static on one
    permanent, about somebody else's arrivals, however they arrive -- cast, put
    onto the battlefield, created as a token, returned from a graveyard -- since
    they all funnel through here.

    Read before the printed loop below, not after, and it does not matter which:
    both only ever set ``tapped`` to True, and neither reads the other. Before,
    so the printed "…unless you pay 3 life" branch keeps the last word on its own
    card.

    **The arriving permanent is excluded as a source.** Orb of Dreams says
    "Permanents enter tapped" and does not tap itself: a permanent's own static
    is not applying to its own entrance, and by this point in `_enter_battlefield`
    the object is already in ``state.battlefield`` -- which is what makes the
    ordinary `_matches` filter language work here at all, and would otherwise
    make every symmetric card in the family tap itself on arrival. That is the
    same defect, reached from the other side, that `self_enters_tapped` gave ten
    of these cards.
    """
    from .characteristics import _battlefield_statics, _matches

    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "enters_tapped":
            continue
        if source_obj.oid == obj.oid:
            continue
        if _matches(state, obj, source_obj, static.get("affects")):
            obj.tapped = True
            return


def _enter_battlefield(
    state: GameState,
    obj: GameObject,
    card: CardDef,
    *,
    forced_tapped: bool = False,
    cause: str = "",
    from_zone: Zone | None = None,
) -> None:
    """Apply enter-the-battlefield replacements, then fire the ETB event."""
    obj.entered_turn = state.turn
    obj.tapped = forced_tapped
    # 716.3: a Class enters at level 1. Here and not in `reset_permanent_state`,
    # which runs on the way *out* and would take the level from the object a
    # leaves-the-battlefield trigger is about to be collected off -- see
    # `GameObject.class_level`.
    obj.class_level = 1
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

    # Cleared once the loop below has read it: the answer belongs to this one
    # arrival, and a permanent that leaves and comes back is a new object
    # (400.7) whose controller has not been asked anything.
    paid_on_arrival = obj.enters_cost_paid
    obj.enters_cost_paid = False
    # The same one-arrival answer, from `offer_enters_copy` a moment ago.
    copy_on_arrival = obj.enters_copy_of
    obj.enters_copy_of = None
    _apply_board_enters_tapped(state, obj)
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
        if event == "self_enters_as_copy":
            # 614.1b: applied *as* it enters, so the permanent is never seen as
            # itself -- which is exactly what a `self_enters` trigger running
            # `become_copy` could not promise.
            #
            # `copying_until_eot` is False: a copy applied as a permanent enters
            # lasts as long as the permanent does (706.2 has no duration), and
            # `clear_until_eot` only takes the timed form.
            #
            # The rest of this loop goes on reading the **printed** card's
            # replacements, which is what every card in this family wants:
            # Vesuva's "enter tapped" is printed on Vesuva, not on the land it
            # copies.
            if copy_on_arrival is not None:
                obj.copying = copy_on_arrival
                obj.copying_until_eot = False
            continue
        if event == "self_enters_prepared":
            # "This creature **enters prepared**." A characteristic of the
            # arrival, in the slot enters-tapped occupies, and not a trigger:
            # the permanent is never seen unprepared, so nothing can respond in
            # the window between its arriving and its state being set -- and
            # `self_enters` triggers reading `has_prepared` would answer
            # differently depending on which of them the controller ordered
            # first.
            obj.prepared = True
            continue
        if event == "self_enters_tapped" or (
            event == "self_enters" and replacement.get("modify", {}).get("tapped")
        ):
            # "…**unless** you pay 3 life." The offer was made and answered a
            # moment ago, just before the move, by whichever path is putting
            # this permanent onto the battlefield -- see `offer_enters_costs`.
            # Read here rather than asked here because `move_object` is not a
            # generator and cannot stop for a decision, and making it one would
            # put a suspend point inside every zone change in the engine.
            if replacement.get("unless_cost") and paid_on_arrival:
                continue
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

    # Riot (702.113), applied in the slot enters-with-counters occupies and for
    # its reason: 614.1c, so the creature is never on the battlefield without
    # whichever half its controller picked. The question was asked a moment ago,
    # just before the move, by `offer_riot_choice`.
    #
    # `granted_keywords` rather than an `until_eot` entry, which is the whole of
    # "or with haste": an until-end-of-turn haste on a creature that entered
    # this turn does the same thing today and nothing ever after, so from the
    # next turn a riot creature that took haste would be indistinguishable from
    # one that took the counter. `reset_permanent_state` emptied that set a few
    # lines ago, on this very move, so the grant is this arrival's and no
    # earlier one's.
    riot_choice = obj.riot_choice
    obj.riot_choice = None
    if riot_choice == RIOT_HASTE:
        obj.granted_keywords.add(Keyword.HASTE.value)
    elif riot_choice == RIOT_COUNTER:
        obj.add_counter("+1/+1", 1)

    # "…it gains haste until end of turn" (Arena of Glory), in the slot beside
    # riot and for a neighbouring reason: the creature is never on the
    # battlefield without it, so no attack declaration and no summoning-sickness
    # check can fall in between. Emptied as it is read, because the promise
    # belongs to this arrival -- a permanent that leaves and comes back is a new
    # object and nobody paid Arena of Glory for that one.
    #
    # `until_eot` and not `granted_keywords`, which is where riot's haste goes:
    # the printed clause says "until end of turn" and riot's says nothing, and
    # `clear_until_eot` sweeps only the one that asked to be swept.
    granted = obj.mana_granted_keywords
    obj.mana_granted_keywords = set()
    if granted:
        from .primitives import grant_keyword

        for keyword in sorted(granted):
            grant_keyword(state, obj.oid, keyword)

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
        # **Where** it came from, which `cause` does not say: that names the
        # mechanism (`put_onto_battlefield`, `manifest`, `meld`) and the same
        # mechanism reaches the battlefield from any zone. Celes, Rune Knight
        # asks "if one or more of them **entered from a graveyard**", which is a
        # question about the zone and covers every route out of it --
        # reanimation, `return_from_graveyard`, a cast from the yard.
        #
        # The origin was on the separate ZONE_CHANGE event all along, and no
        # trigger maps to that one, so nothing could reach it.
        from_zone=from_zone.value if from_zone is not None else None,
        # One firing per **simultaneous** batch, for "whenever one or more
        # creatures enter". `permanent_enters` fires once per permanent, so a
        # mass reanimation would put three counters where the card prints one.
        # See `triggers._queue`; without this the batched flag had nothing to
        # group by on this event.
        batch=state.event_batch,
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
    # Where it came from, for the exile-until effects that give it back: "return
    # it to the zone it came from" is one sentence covering a card taken out of
    # a hand and a permanent taken off the battlefield, and nothing else on the
    # object remembers which. Read before the move and written after, because
    # `move_object` runs `reset_permanent_state` in between -- the same order
    # `op_exile` writes `exiled_by` in, for the same reason.
    origin = obj.zone
    move_object(state, oid, Zone.EXILE, cause=cause, by=by)
    if (moved := state.objects.get(oid)) is not None:
        moved.exiled_from = origin.value
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
