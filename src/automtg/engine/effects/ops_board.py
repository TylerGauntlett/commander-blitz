"""Effect ops that act on permanents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Step, Zone
from ..errors import DslError
from ..objects import PLUS_ONE
from ..primitives import (
    add_counters,
    add_subtypes,
    animate,
    attach,
    change_control,
    create_token,
    forbid_block,
    forbid_sacrifice,
    goad_creature,
    grant_ability,
    grant_keyword,
    lock_abilities,
    make_unblockable,
    pump,
    remove_counters,
    restrict_attack,
    sacrifice_forbidden,
    tap_permanent,
    transform,
    untap_permanent,
)
from ..structs import TempEffect
from ..zones import destroy, exile, move_object, sacrifice
from ..zones import snapshot as capture_snapshot
from . import register
from .context import EffectContext
from .selectors import (
    ZONE_NAMES,
    choose_objects,
    pick_from_pool,
    resolve_pool,
    select_players,
)
from .values import evaluate_value


@register("destroy")
def op_destroy(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Destroy target creature", and optionally "It can't be regenerated."

    `no_regeneration` is the second sentence, and it had been *silently
    dropped* by every card that printed it: nothing read it, so Terminate,
    Wrath of God and Rapid Hybridization all shipped as spells a Drudge
    Skeletons walks away from. It is a flag on the destruction rather than a
    mark on the victim -- see `zones.destroy` for why the difference matters.
    """
    no_regeneration = bool(spec.get("no_regeneration"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Destroy", "destroy")
    for oid in oids:
        # `by` is what makes the log and the exit animation able to say
        # "Destroyed by Vandalblast" rather than just "Destroyed".
        destroy(ctx.state, oid, by=ctx.source_oid, no_regeneration=no_regeneration)


@register("replace_deaths")
def op_replace_deaths(ctx: EffectContext, spec: Mapping[str, Any]):
    """"If [these creatures] would die this turn, exile them instead."

    Gallifrey Falls, Anger of the Gods, the whole exile-wrath family.

    The set is **snapshotted now**, which is what the printed wording says: "a
    creature dealt damage this way" is decided as the spell resolves, and a
    creature that arrives afterwards was dealt no damage by it. Evaluated lazily
    at death time it would catch the whole board for the rest of the turn, which
    is a different and much stronger card.

    Marked per object rather than registered as a global replacement, because
    that is what the set-is-fixed reading makes it: a property of these
    permanents until the turn ends. `move_object` reads it, so **every** way of
    dying is covered -- the printed word is "die", which is broader than
    "destroyed", and a sacrificed creature or one whose toughness hit zero never
    goes near `destroy`.
    """
    destination = str(spec.get("destination", "exile"))
    if destination not in ZONE_NAMES:
        raise DslError(f"replace_deaths: unknown destination {destination!r}")
    oids = yield from choose_objects(ctx, spec.get("objects"), "Redirect deaths", "replace")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.dies_to = destination


@register("become_copy")
def op_become_copy(ctx: EffectContext, spec: Mapping[str, Any]):
    """"…become a copy of another target creature you control." Rule 706.

    A copy effect applied **in place**, which is a different thing from every
    copy the DSL could already make. `copy_permanent` calls `create_token` with
    the source's def id: it makes a *new* permanent and never alters the object
    it is pointed at, so it cannot turn Gogo into anything. `animate` overwrites
    power, toughness, colors, types and keywords with literals, so it cannot
    take another object's whole printed face. `transform` only flips a
    double-faced card to its own back.

    Implemented as a def id on the object, read by `state.card_of` -- the one
    place a permanent's current face is decided, and already the single funnel
    for transforming cards, so a copy shows up in the characteristics layers,
    legality, combat and the serializer at once without any of them changing.

    ``except_name`` is the "except its name is Gogo, Mysterious Mime" clause,
    which 706.2 allows a copy effect to override. ``duration`` defaults to
    ``end_of_turn``; ``permanent`` is Clone's shape, and only the timed form is
    cleared by `clear_until_eot`.
    """
    objects = spec.get("objects") or {"self_only": True}
    subjects = yield from choose_objects(ctx, objects, "Become a copy", "become_copy")
    if not subjects:
        return
    sources = yield from choose_objects(ctx, spec.get("copying"), "Copy which permanent")
    if not sources:
        # "you may have Gogo become a copy of **another target creature**" --
        # with nothing to copy the whole clause does nothing, and the "if you
        # do" rider that follows is false.
        return
    model = ctx.state.objects.get(sources[0])
    if model is None:
        return
    copied = ctx.state.card_of(model)
    until_eot = str(spec.get("duration", "end_of_turn")) != "permanent"
    for oid in subjects:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.copying = copied.id
        obj.copying_name = spec.get("except_name")
        obj.copying_until_eot = until_eot
    ctx.state.bump_chars()


@register("replace_leaves_battlefield")
def op_replace_leaves_battlefield(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Exile it ... if it would **leave the battlefield**." Unearth (702.83a).

    `replace_deaths` is the near miss and it is not a rounding error on the
    cards that want this. `move_object` gates that one on a battlefield ->
    graveyard move, so it catches a death and nothing else, while this clause is
    the *whole* departure: bounced to hand, exiled by removal, shuffled into a
    library, sent to the command zone. Priest of Fell Rites is the witness --
    its own ability sacrifices it, and the printed replacement is what makes
    that a one-way trip. Read as death-only, an opponent's bounce leaves a card
    that can be unearthed all over again, which is the loop the clause closes.

    The other half is the **lifetime**, and it is why this is a separate marker
    rather than a wider gate on the same one. `dies_to` says "would die *this
    turn*" and is cleared at cleanup; this lasts exactly as long as the
    permanent is on the battlefield, so only `reset_permanent_state` clears it
    -- on the very zone change it replaces.
    """
    destination = str(spec.get("destination", "exile"))
    if destination not in ZONE_NAMES:
        raise DslError(
            f"replace_leaves_battlefield: unknown destination {destination!r}"
        )
    oids = yield from choose_objects(
        ctx, spec.get("objects"), "Redirect on leaving", "replace"
    )
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.leaves_to = destination


@register("phase_out")
def op_phase_out(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Target creature phases out." (702.26)

    Phasing shipped as a keyword the untap step reads, and nothing else: the
    whole mechanism lived in `turn.py` behind two private functions whose only
    caller was the untap walk. This is the printed one-shot half, and it is that
    same mechanism -- attached permanents come along (702.26e), and the
    permanent phases back in before its controller's next untap step.

    Not `grant_keyword: phasing`, which is a different card: the keyword does
    nothing *now* and then flickers the creature out and back for the rest of
    the game. Not a blink either -- a phased-out permanent never leaves the
    battlefield, so it keeps its counters, its attachments and its continuous
    effects, and nothing that watches for a zone change sees anything.
    """
    from ..turn import phase_out

    oids = yield from choose_objects(ctx, spec.get("objects"), "Phase out", "phase_out")
    for oid in oids:
        phase_out(ctx.state, oid)
    ctx.state.bump_chars()


@register("exile")
def op_exile(ctx: EffectContext, spec: Mapping[str, Any]):
    """Exile objects, optionally remembering which permanent did it.

    ``until_leaves`` is the O-Ring family -- "exile it until this permanent
    leaves the battlefield". It records the link and nothing else; the *return*
    is an ordinary `leaves_battlefield` trigger on the same card, reading the
    link back through a `{"zone": "exile", "exiled_with": "self"}` selector.

    Two halves rather than one op, because the card really is two abilities and
    a player can respond between them -- and because what comes back, and under
    whose control, differs between O-Ring and Fiend Hunter.

    ``as`` is "…equal to the number of creature cards exiled **this way**" --
    Grey Host Reinforcements. The same record `sacrifice` and `reveal` keep, for
    the same reason: the exiled cards land in a shared exile zone among
    everything else that has ever been exiled, so no selector can name them
    afterwards. Not ``until_leaves``, which is the O-Ring *link* and declares a
    return; a card that only counts what it exiled hands nothing back.
    """
    # `until_leaves` is the O-Ring name for the link and `link` is the neutral
    # one. The same record either way -- `exiled_by`, which a later
    # `{"zone": "exile", "exiled_with": "self"}` selector reads back -- because
    # the *return* was always a separate `leaves_battlefield` trigger on the
    # card and never anything this op did. Valigarmanda exiles from every
    # graveyard at the table and is sacrificed after its last chapter; written
    # `until_leaves` it would read as promising those cards back to the
    # opponents they were taken from, which is a different card.
    link = bool(spec.get("until_leaves")) or bool(spec.get("link"))
    # "You may play the exiled card this turn." Florian, and the impulse-draw
    # family. Not `play_exiled`, which casts the card for *free* and does it
    # there and then: this is a permission the player may take later, at the
    # printed price, and it expires with the turn.
    playable = bool(spec.get("playable_this_turn"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Exile", "destroy")
    if name := spec.get("as"):
        # Written before the move, so the binding records what this op exiled
        # rather than whatever is in exile once it is done -- exactly where
        # `op_sacrifice` writes its own.
        #
        # **Extended, not replaced.** Kefka exiles "a card at random from each
        # opponent's graveyard", which is a `for_each_player` loop around this
        # op, and a plain assignment kept only the last opponent's card: the
        # other was exiled and then stranded, because the `play_exiled` that
        # follows could no longer name it. `discard` accumulates across the
        # seats one op touches for the same reason; this is the same fact one
        # loop out. Bindings live for a single resolution, so nothing carries
        # into the next.
        previous = ctx.bindings.get(str(name))
        earlier = list(previous) if isinstance(previous, list) else []
        ctx.bindings[str(name)] = earlier + list(oids)
    for oid in oids:
        exile(ctx.state, oid, by=ctx.source_oid)
        if playable:
            # After the move, for the same reason `exiled_by` below is:
            # `move_object` runs `reset_permanent_state` on the way and would
            # wipe this if it were set first.
            obj = ctx.state.objects.get(oid)
            if obj is not None:
                obj.playable_by = ctx.controller
                obj.playable_turn = ctx.state.turn
        if link and ctx.source_oid is not None:
            # After the move: `move_object` runs `reset_permanent_state` on the
            # way, which would wipe this if it were set first.
            obj = ctx.state.objects.get(oid)
            if obj is not None:
                obj.exiled_by = ctx.source_oid


@register("exile_and_return")
def op_exile_and_return(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Exile it, then return it to the battlefield **transformed** under its
    owner's control."

    Joshua, Phoenix's Dominant, and the Final Fantasy "Dominant" cycle, which
    prints this line on both faces -- the front returns it transformed and the
    back returns it "(front face up)". So ``face`` is written out rather than
    inferred from where it started: on the back the sentence turns it *back*,
    and an op that only ever flipped would say the same thing twice.

    **Not `transform`.** That turns the permanent over in place: it never
    changes zones, so it keeps its counters, its Auras and its summoning
    sickness, fires no leaves-the-battlefield trigger and no enters trigger, and
    stays under whoever controls it. Every one of those is a difference this
    card prints the other way, and together they make a materially stronger and
    differently-timed permanent.

    It is a **new object** (400.7): what comes back is summoning sick, has no
    counters, carries no attachments, and is under its **owner's** control --
    which is the clause that makes this a removal answer for a stolen permanent
    and is written on the card.

    ``face`` is required. Defaulted to "turn it over" the op would be right on
    Joshua's front and silently wrong on the Saga's third chapter, which is the
    same card and the reading a player would never see going wrong.

    The face is passed **into** the move rather than set afterwards: the
    arriving face is what every enters-replacement and enters-trigger must see,
    and the back of this very card is a Saga whose lore counter is a
    replacement.
    """
    face = str(spec.get("face", ""))
    for oid in resolve_pool(ctx, spec.get("objects")):
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        owner = obj.owner
        exile(ctx.state, oid, cause="exiled", by=ctx.source_oid)
        moved = ctx.state.objects.get(oid)
        if moved is None or moved.zone is not Zone.EXILE:
            # A commander its owner sent to the command zone instead, or
            # anything else that replaced the exile. It did not end up where the
            # return would read it from, so the second half simply does not
            # happen -- which is what 400.7 says about an object that is no
            # longer the one the effect was tracking.
            continue
        # Set before the move, the way `put_onto_battlefield` sets it: control
        # is not something `move_object` decides -- `to_player` says whose copy
        # of a zone the card joins, and the battlefield is shared -- and the
        # enters-the-battlefield event carries the controller, so an arrival
        # under the wrong seat would fire its own triggers for the wrong player.
        moved.controller = owner
        move_object(
            ctx.state,
            oid,
            Zone.BATTLEFIELD,
            to_player=owner,
            cause="returned",
            by=ctx.source_oid,
            as_face=face,
        )


@register("sacrifice")
def op_sacrifice(ctx: EffectContext, spec: Mapping[str, Any]):
    """Sacrifice permanents, optionally recording which ones.

    ``as`` is devour: "as this creature enters, you may sacrifice any number of
    creatures. It enters with twice that many +1/+1 counters on it." The number
    is not knowable when the card is written and is not recoverable afterwards
    either -- the creatures are in a graveyard among everything else that has
    died, and `creatures_died_this_turn` counts combat and removal too. So the
    list is written down as the op consumes it, and read back with
    ``{"count": {"binding": …}}``.

    ``snapshot`` is Entrapment Maneuver: the same window, but recording the
    chosen permanent's *characteristics* rather than its oid, because the oid
    stops answering for them the moment it reaches a graveyard.  See the comment
    at the write below.

    The **effect** road for "you can't sacrifice those creatures this turn"
    (701.17b) is the pool filter below, and it narrows the *pool* rather than
    skipping in the loop deliberately: 701.17b makes a protected permanent an
    illegal choice, so an edict must take something else if there is anything
    else -- "each player sacrifices a creature" against a board of one protected
    creature and one ordinary one takes the ordinary one. Filtering after the
    choice would let the edict be answered with the protected creature and then
    do nothing, which is a better answer than the printed card allows. Only when
    nothing legal is left does the effect do nothing to that player, which is
    the same rule read from the other end.

    Assembled out of `resolve_pool` + `pick_from_pool` -- the two halves
    `choose_objects` calls in sequence -- rather than by narrowing the selector,
    because "not under a sacrifice restriction" is a fact about the table and
    not a selector key any card writes.
    """
    selector = dict(spec.get("objects") or {})
    selector.setdefault("controller", "you")
    pool = [
        oid
        for oid in resolve_pool(ctx, selector)
        if not sacrifice_forbidden(ctx.state, oid)
    ]
    oids = yield from pick_from_pool(ctx, pool, selector, "Sacrifice", "sacrifice")
    if name := spec.get("as"):
        # Written before the sacrifice, so the binding is a record of the choice
        # rather than of what survived it.
        ctx.bindings[str(name)] = list(oids)
    if name := spec.get("snapshot"):
        # Entrapment Maneuver: "…**that creature's** toughness", where the
        # creature was picked a line ago by somebody else. `as` records *which*
        # permanent, and that is enough for a later selector -- but not for a
        # characteristic, because by the next op the oid names a graveyard card
        # and `chars()` gives it the printed line. A 5/5 wearing three +1/+1
        # counters reads back as toughness 5, off by every counter, anthem, Aura
        # and pump the combat trick was aimed at, while looking implemented.
        #
        # So the value is taken here, in the one window where the permanent has
        # been chosen and has not yet moved. Deliberately the same
        # `zones.snapshot` the `snapshot` op calls and the same binding shape it
        # writes -- one dict, or `{}` when nothing was chosen -- so
        # `{"toughness_of": {"binding": …}}` and `{"binding": …}` as a selector
        # read it without knowing which op wrote it. Explicit LKI stays the one
        # mechanism (`docs/rules-coverage.md`); this only moves *when* it may be
        # taken.
        #
        # The first chosen permanent, exactly as `op_snapshot` takes `oids[0]`
        # of its pool: a snapshot is one object's characteristics and there is
        # no printed sacrifice that needs a set of them. `as` is still the
        # record of the whole choice, and the two are written side by side.
        ctx.bindings[str(name)] = capture_snapshot(ctx.state, oids[0]) if oids else {}
    for oid in oids:
        sacrifice(ctx.state, oid, by=ctx.source_oid)


@register("put_onto_battlefield")
def op_put_onto_battlefield(ctx: EffectContext, spec: Mapping[str, Any]):
    """Put objects onto the battlefield, optionally tapped and attacking.

    ``attacking`` is **ninjutsu**: "put this card onto the battlefield from your
    hand tapped and attacking". It joins the combat the returned attacker just
    left, which is why the ninja arrives unblocked -- the blocker that was there
    was blocking a creature that is now in its owner's hand.

    Same contract `create_token`'s `attacking` has: a permanent put in this way
    was never *declared* as an attacker, so it triggers nothing that fires on
    attacking. That is the real rule (508.4) and it is also what keeps "when
    this attacks, put a creature onto the battlefield attacking" finite.

    ``counters`` is "return that card to the battlefield **with a vigilance
    counter and a lifelink counter on it**" -- Gilraen, Dúnedain Protector. The
    identical clause `op_return_from_graveyard` has carried since persist,
    spelled the same way and placed at the same moment, and it has to live on
    this op too: that one forces its selector's zone to the graveyard, so a card
    coming back out of *exile* cannot use it.

    Two `add_counters` ops after the move would put the same counters on, but
    they would not be the same card. The printed clause is about the *arrival* --
    if the object is no longer where the return could reach it, no counters go
    anywhere -- and a separate op naming the same binding would happily counter
    a permanent that got back to the battlefield some other way.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put onto the battlefield")
    tapped = bool(spec.get("tapped"))
    attacking = _attacking_player(ctx, spec, _attack_defender)
    counters = spec.get("counters") or {}
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        controller = ctx.controller if spec.get("controller") == "you" else obj.owner
        obj.controller = controller
        # `cause` travels into the enters-the-battlefield event, so an ability
        # that puts permanents down can name itself here and then refuse to
        # trigger on its own output -- see `TriggerSpec.not_cause`.
        move_object(
            ctx.state,
            oid,
            Zone.BATTLEFIELD,
            tapped=tapped,
            cause=str(spec.get("cause") or "put_onto_battlefield"),
        )
        # Placed immediately after the move rather than as an enters-with
        # replacement -- the same trade `op_return_from_graveyard` documents,
        # observable only by another trigger ordered between the two.
        for kind, amount in counters.items():
            add_counters(ctx.state, oid, str(kind), int(amount), source=ctx.source_oid)
        if attacking is not None and ctx.state.combat is not None:
            ctx.state.combat.attackers[oid] = attacking
            _offer_blocks_to(ctx, attacking)


@register("create_token")
def op_create_token(ctx: EffectContext, spec: Mapping[str, Any]):
    """Put tokens onto the battlefield, optionally remembering which ones.

    ``as`` is "Exile **the token** at end of combat" -- Flamerush Rider. A later
    effect has to name the object this one just made, and no selector can:
    `is_token` matches every token you control, and `{"is_token": true,
    "attacking": true}` also catches tokens some other attack trigger made this
    turn, so a second copy of the same card would exile the wrong permanent.
    The oids `create_token` returns are the only thing that identifies them, and
    they were being discarded.

    ``attacking`` is either ``true`` -- "wherever the source is already pointed"
    -- or a player spec naming the seat, which is "attacking **that player**".
    See `_attacking_player`.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    token = str(spec["token"])
    attacking = _attacking_player(ctx, spec, _attack_target)
    made: list[int] = []
    for pid in _players(ctx, spec.get("controller", "you")):
        made.extend(
            create_token(
                ctx.state,
                token,
                pid,
                amount,
                tapped=bool(spec.get("tapped")),
                attacking=attacking,
            )
        )
    if made and attacking is not None:
        _offer_blocks_to(ctx, attacking)
    if name := spec.get("as"):
        # Written after the op, unlike `sacrifice`'s, which is written before:
        # that one records a *choice* the player made and this one records
        # objects that did not exist until the op ran.
        ctx.bindings[str(name)] = made


@register("copy_permanent")
def op_copy_permanent(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Create a token that's a copy of target creature."

    The object model already *is* a copy model: an object's identity is its
    ``def_id`` pointing at a `CardDef`, and `is_token` is a separate flag.  So a
    token copy is a token whose ``def_id`` is the copied permanent's -- which is
    also exactly right, because a copy copies the printed card and not the
    counters, damage or Auras that have accumulated on it.

    Unlike `create_token` this names no token id, so there is nothing for
    `validate_token_references` to check and nothing to pre-declare: the thing
    being copied is only known while the spell is resolving.

    ``except_`` is embalm's "…except it's a white Zombie Angel with no mana
    cost". It is stored on the token rather than on a card, because a copy has
    no card of its own -- its identity is the original's ``def_id``.

    The source need not be on the battlefield: embalm copies a card in the
    *graveyard*, and `self_only` reaches it there because an oid survives every
    zone change.

    ``as`` records the copies, the same way `create_token`'s does and for the
    same card: Flamerush Rider's "create a token that's a copy of another target
    attacking creature… Exile **the token** at end of combat." The binding holds
    the copies, never the thing copied -- ``{"target": …}`` already names that.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    oids = resolve_pool(ctx, spec.get("objects"))
    if not oids:
        return
    controllers = _players(ctx, spec.get("controller", "you"))
    overrides = spec.get("except_") or spec.get("except")
    attacking = _attacking_player(ctx, spec, _attack_target)
    made: list[int] = []
    for oid in oids:
        source = ctx.state.objects.get(oid)
        if source is None:
            continue
        for pid in controllers:
            made.extend(
                create_token(
                    ctx.state,
                    source.def_id,
                    pid,
                    amount,
                    tapped=bool(spec.get("tapped")),
                    attacking=attacking,
                    overrides=dict(overrides) if overrides else None,
                )
            )
    if made and attacking is not None:
        _offer_blocks_to(ctx, attacking)
    if name := spec.get("as"):
        ctx.bindings[str(name)] = made


def _attacking_player(ctx: EffectContext, spec: Mapping[str, Any], fallback) -> int | None:
    """Whom a permanent arriving attacking should be attacking.

    ``attacking: true`` is the original spelling and still means "wherever the
    source is already pointed" -- ``fallback`` is `_attack_target` or
    `_attack_defender`, whichever this op has always used. Every shipped card
    uses that form and none of them change.

    Anything else is a **player spec**, which is the case the boolean cannot
    say. Ainok Strike Leader's "for each opponent, create a token attacking
    **that player**" names the seat a `for_each_player` loop is on
    (``{"binding": "each_player"}``); Combat Calligrapher's "attacking that
    opponent" names the trigger's ``defender`` binding, on a source that is
    never itself attacking. Under the boolean both would resolve to the one
    player the *source* attacks -- the same seat for all three tokens at a pod,
    and nobody at all when the source is not an attacker, which arrives tapped
    and attacking no-one while looking implemented.

    A creature attacks exactly one player, so a spec that names several is an
    authoring error rather than something to pick from. The plural *names* are
    refused at load time (`loader._validate_effect`); this catches the one shape
    load time cannot see, a multi-ref target. Naming nobody -- an unbound
    binding, a player who has left -- is the boolean's own "nobody to join": the
    permanent simply arrives.
    """
    who = spec.get("attacking")
    if who is None or who is False:
        return None
    if who is True:
        return fallback(ctx)
    named = select_players(ctx, who)
    if len(named) > 1:
        raise DslError(
            f"attacking: {who!r} names {len(named)} players; "
            f"a creature attacks exactly one"
        )
    if not named or not ctx.state.is_alive(named[0]):
        return None
    return named[0]


def _offer_blocks_to(ctx: EffectContext, defender: int) -> None:
    """Make sure a newly attacked player still gets to declare blockers.

    `combat.finish_attackers` fills `pending_blockers` from the declaration, so
    it lists only the players who were attacked *then*. A token created
    attacking a player nobody declared against -- Ainok Strike Leader's third
    opponent, who was not part of the swing -- would otherwise be attacked by a
    creature it is never asked to block (509.1).

    Only **before** the declare blockers step, which is the window every card
    that says this resolves in: attack triggers go on the stack during the
    declare attackers step. Once the step has started the queue is being walked
    -- `game.apply` pops its head as each declaration is answered -- so writing
    into it would ask the wrong seat to block; and a permanent that arrives
    attacking after blocks are declared is simply unblocked, which is 509.1 read
    the other way and what stops this from becoming a second declaration.
    """
    combat = ctx.state.combat
    if combat is None or defender in combat.pending_blockers:
        return
    if ctx.state.step >= Step.DECLARE_BLOCKERS:
        return
    order = ctx.state.turn_order()
    if defender not in order:
        return
    seat = order.index(defender)
    at = len(combat.pending_blockers)
    for i, pid in enumerate(combat.pending_blockers):
        if pid in order and order.index(pid) > seat:
            at = i
            break
    combat.pending_blockers.insert(at, defender)


def _attack_defender(ctx: EffectContext) -> int | None:
    """Whom a permanent put onto the battlefield attacking should be attacking.

    Ninjutsu returns an attacker to hand and puts the ninja in its place, so the
    defender is whoever *that* attacker was hitting. With no combat, or nothing
    left attacking, there is nobody to join and the permanent simply arrives.
    """
    combat = ctx.state.combat
    if combat is None or not combat.attackers:
        return None
    if ctx.source_oid is not None and ctx.source_oid in combat.attackers:
        return combat.attackers[ctx.source_oid]
    return next(iter(combat.attackers.values()))


def _attack_target(ctx: EffectContext) -> int | None:
    """Whom a token created attacking should be attacking.

    The same player the source is already attacking -- which is what "create a
    tapped and attacking token" means on a card whose trigger is "whenever this
    creature attacks".  Outside combat, or from a source that is not itself
    attacking, there is nobody to join, and the token simply arrives tapped.
    """
    combat = ctx.state.combat
    if combat is None or ctx.source_oid is None:
        return None
    return combat.attackers.get(ctx.source_oid)


@register("add_counters")
def op_add_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    kind = str(spec.get("counter", "+1/+1"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put counters on")
    for oid in oids:
        add_counters(ctx.state, oid, kind, amount, source=ctx.source_oid)


@register("remove_counters")
def op_remove_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    kind = str(spec.get("counter", "+1/+1"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Remove counters from")
    for oid in oids:
        remove_counters(ctx.state, oid, kind, amount)


@register("tap")
def op_tap(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Tap")
    for oid in oids:
        tap_permanent(ctx.state, oid)


@register("untap")
def op_untap(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Untap")
    for oid in oids:
        untap_permanent(ctx.state, oid)


@register("attach")
def op_attach(ctx: EffectContext, spec: Mapping[str, Any]):
    """Attach something to something (701.3). Equip, Reconfigure -- and Vault 101.

    ``objects`` is the **host**: the creature the Equipment ends up on, the
    permanent the Aura ends up enchanting. It has never been the thing that
    moves. What moves is ``attachment``, and until this key existed there was no
    way to say it: the attacher was hardcoded to ``ctx.source_oid``, which is
    exactly right for the two abilities that had ever needed the op. Equip and
    Reconfigure are printed *on the Equipment*, so "attach to target creature you
    control" means attach **me**, and naming the mover would be noise.

    Vault 101: Birthday Party is the card where the source is somebody else.
    "II, III -- You may put an Aura or Equipment card from your hand or graveyard
    onto the battlefield. If an Equipment is put onto the battlefield this way,
    you may attach it to a creature you control." The source of that ability is a
    **Saga** -- an Enchantment that is neither Aura nor Equipment -- so the old
    op would have attached the Saga itself to a creature and left the Equipment
    that just arrived sitting on the battlefield unattached, doing nothing. That
    failure is invisible: the card loads, the ability resolves, and the only
    evidence is a buff that never appears.

    ``attachment`` is an ordinary selector, so the usual spelling is
    ``{"binding": "gear"}`` -- the ``as`` name the op that just put the card onto
    the battlefield wrote. That is what "**it**" and "put onto the battlefield
    **this way**" mean, and no fresh filter can say it: "an Equipment you
    control" would also match the Equipment that has been sitting there since
    turn three.

    **The attachment is resolved first**, and the order carries the conditional.
    "*If an Equipment* is put onto the battlefield this way" is not a separate
    `if`: a selector that found an Aura instead matches nothing, the pool is
    empty, and the op returns without ever asking which creature -- rather than
    asking and then silently attaching nothing. With ``optional`` on ``objects``
    the remaining question is the printed "you **may** attach it".

    The Aura half is the same op with a wider ``attachment``. An Aura put onto
    the battlefield without being cast never targeted anything, so nothing
    attached it -- `stack._attach_aura` reads the *spell's* targets -- and
    `sba` bins an Aura enchanting nothing the moment it arrives. Which host is
    legal for it is the card's own selector to state; the engine models no
    "enchant creature" restriction off the stack (see `docs/rules-coverage.md`).
    """
    if "attachment" in spec:
        movers = yield from choose_objects(ctx, spec["attachment"], "Attach", "attach")
        # No pool, no question. See the docstring: this is the "if an Equipment
        # is put onto the battlefield this way" half, and asking for a host
        # before knowing there is anything to hang on it would show the player a
        # decision that cannot change the game.
        if not movers:
            return
    else:
        movers = [] if ctx.source_oid is None else [ctx.source_oid]
    oids = yield from choose_objects(ctx, spec.get("objects"), "Attach to")
    # One host, however many attachments -- 701.3d attaches each to a single
    # object, and no printed line hangs one Equipment on two creatures.
    for oid in oids[:1]:
        for mover in movers:
            attach(ctx.state, mover, oid)


@register("meld")
def op_meld(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Exile them, then meld them into <name>." Bruna and Gisela (701.37).

    Meld is `mutate`'s merged permanent with the pair fixed by the card instead
    of chosen by the caster, and it reuses the same mechanism: **one
    `CardDef`**, the melded card, written onto one object, with the partner
    recorded in `merged_under` so `move_object` sends both wherever it goes.

    What is genuinely different is that it is a *new* permanent. 701.37c has the
    two cards **exiled** and then returned melded, so the melded permanent
    enters the battlefield -- its enter triggers fire, and it is summoning sick.
    That is why this exiles and re-enters rather than writing `merged_card` onto
    a permanent that is already there, which is what mutate does.

    The whole "if you both own and control" clause is the card's own
    ``condition`` on the trigger. Nothing here re-checks it: an intervening-if
    is checked twice by `triggers`, and a third check inside the effect would be
    a different rule wearing the same words.
    """
    state = ctx.state
    source = state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    if source is None or not source.on_battlefield:
        return
    card = state.registry.get(source.def_id)
    if card.melds_with is None or card.melds_into is None:
        raise DslError(f"{card.id}: 'meld' needs 'melds_with' and 'melds_into'")
    partner = next(
        (
            oid
            for oid in state.battlefield
            if (other := state.objects.get(oid)) is not None
            and other.def_id == card.melds_with
            and other.controller == source.controller
            and other.owner == source.owner
        ),
        None,
    )
    if partner is None:
        return
    controller = source.controller
    # Exiled first, both of them, because that is what the printed line says and
    # because the melded permanent has to *enter* -- a card that never left
    # would have no enters-the-battlefield trigger to fire.
    exile(state, source.oid)
    exile(state, partner)
    move_object(state, source.oid, Zone.BATTLEFIELD, cause="meld")
    melded = state.objects[source.oid]
    melded.controller = controller
    # After the move, for `cast_transformed`'s reason: `reset_permanent_state`
    # clears both of these on the way onto the battlefield, which is right for
    # every permanent except one that arrives already melded.
    melded.merged_card = state.registry.get(card.melds_into)
    melded.merged_under = (partner,)
    partner_obj = state.objects[partner]
    partner_obj.zone = Zone.BATTLEFIELD
    partner_obj.merged_into = source.oid
    state.players[partner_obj.owner].exile.remove(partner)
    state.bump_chars()
    state.emit("melded", player=controller, source=source.oid, card=card.melds_into)
    yield from ()


@register("transform")
def op_transform(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Transform this creature." Bloodline Keeper.

    ``objects`` defaults to the ability's own source, which is what every
    printed line of this shape means -- "transform **this**". ``to_back``
    forces a direction for the rare card that says "turn it face up" rather
    than "turn it over".
    """
    to_back = spec.get("to_back")
    if "objects" in spec:
        oids = yield from choose_objects(ctx, spec.get("objects"), "Transform")
    else:
        oids = [ctx.source_oid] if ctx.source_oid is not None else []
    for oid in oids:
        transform(ctx.state, oid, to_back=None if to_back is None else bool(to_back))


@register("gain_control")
def op_gain_control(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Gain control of target creature." Captivating Vampire, Act of Treason.

    ``player`` says who gains it and defaults to the ability's controller, which
    is what every "*you* gain control" line means; the spec exists because "target
    opponent gains control of" is the same effect pointed elsewhere.

    ``duration`` is ``"permanent"`` or ``"until_end_of_turn"``.  The default is
    ``"permanent"`` because that is what every card written before this meant,
    not because it is the safer reading -- it is the *stronger* one, and it is
    the loader rather than this default that keeps a misspelling from silently
    becoming it.  The two are different cards and not degrees of one, which is
    why neither is ever inferred from the rest of the effect.  See
    :func:`automtg.engine.primitives.change_control` for the handback.

    ``as`` names the permanents taken, so a later clause of the same spell can
    say **"those creatures"** -- Call for Aid's "gain control of all creatures
    target opponent controls… untap *those creatures*… *they* gain haste… you
    can't sacrifice *those creatures*".  No selector can name them once the op
    has run: the set was "creatures target opponent controls" and by the next
    line the opponent controls none of them, while "creatures you control"
    catches everything that was already yours.  Written *after* the loop, like
    `create_token`'s and unlike `sacrifice`'s: this records what control
    actually moved, not what was asked for, so a permanent that left in response
    -- or that was already yours, which `change_control` refuses as a no-op --
    is not one of "those creatures".
    """
    players = _players(ctx, spec.get("player", "you"))
    if not players:
        return
    duration = str(spec.get("duration", "permanent"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Gain control of")
    taken = [
        oid
        for oid in oids
        if change_control(
            ctx.state, oid, players[0], source=ctx.source_oid, duration=duration
        )
    ]
    if name := spec.get("as"):
        ctx.bindings[str(name)] = taken


@register("choose_permanents")
def op_choose_permanents(ctx: EffectContext, spec: Mapping[str, Any]):
    """Pick permanents and remember them, without doing anything to them.

    Tragic Arrogance: "For each player, you choose from among the permanents
    that player controls an artifact, a creature, an enchantment, and a
    planeswalker. Then each player sacrifices all other nonland permanents they
    control."

    Every other op that writes a binding also *acts* on what it picked --
    `sacrifice`, `exile`, `gain_control`, `reveal`, `create_token`,
    `copy_permanent`, `search_zones`. `snapshot` records without acting but
    takes `oids[0]` of its pool with no `count` or `chooser`, so it can be
    neither a choice nor four picks. There was no way to mark the survivors
    *before* the mass sacrifice, and inverting the card into "choose the ones to
    sacrifice" is a different choice: the printed card names one survivor per
    type, not an all-but-one selection.

    The binding **accumulates**, which is what lets the four per-type choices be
    written as four ops sharing one name -- `count` is a single flat number over
    a uniformly filtered pool, so one choice cannot express "at most one of each
    of four types" and would happily take four creatures. The `sacrifice` that
    follows then spares all four with a single `exclude_binding`.
    """
    picked = yield from choose_objects(
        ctx, spec.get("objects"), str(spec.get("prompt") or "Choose"), "choose_permanents"
    )
    if name := spec.get("as"):
        previous = ctx.bindings.get(str(name))
        earlier = list(previous) if isinstance(previous, list) else []
        ctx.bindings[str(name)] = earlier + list(picked)


@register("regenerate")
def op_regenerate(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 701.15 — "Regenerate this creature."

    Puts a **shield** on the permanent rather than doing anything now, which is
    the whole of the keyword action: "the *next* time this permanent would be
    destroyed this turn, instead tap it, remove it from combat, and remove all
    damage from it." What it replaces has not happened yet, and usually never
    will.

    A count rather than a flag, because "regenerate it twice" is two shields and
    each is spent by one destruction. Cleared at cleanup with the rest of the
    until-end-of-turn state -- expiring is most of what the ability is worth
    paying for, and a shield that survived the turn would make every
    regenerator indestructible from the first time it was used.

    The shield is spent in `zones.destroy`, which is the one function every
    route to a destruction already goes through.
    """
    amount = max(1, evaluate_value(ctx, spec.get("amount", 1)))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Regenerate", "regenerate")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.regeneration_shields += amount
        ctx.state.emit(
            "regeneration_shield",
            player=obj.controller,
            source=ctx.source_oid,
            oid=oid,
            shields=obj.regeneration_shields,
        )


@register("aura_swap")
def op_aura_swap(ctx: EffectContext, spec: Mapping[str, Any]):
    """Aura swap — "Exchange this Aura with an Aura card in your hand."

    An **exchange**, which is why it is one op rather than a bounce beside a
    put-onto-the-battlefield. Two things follow from that and neither is
    reachable by composing the halves:

    - **The new Aura arrives attached to what the old one was on.** It is not
      cast, so there is no targeting clause to carry the creature, and
      `_attach_aura` -- which reads a spell's first target -- never runs.
    - **The exchange is atomic.** Written as two effects the old Aura is in hand
      and the new one is not yet down, and a state-based action in between would
      see the enchanted creature unenchanted; more to the point, the creature
      could have died to that gap on a card that stops it dying.

    A hand with no Aura to swap in does nothing, rather than bouncing the one on
    the battlefield for free.
    """
    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    if source is None or not source.on_battlefield:
        return
    host = source.attached_to
    selector = dict(spec.get("objects") or {})
    selector.setdefault("zone", "hand")
    selector.setdefault("controller", "you")
    selector.setdefault("subtypes", ["Aura"])
    pool = resolve_pool(ctx, selector)
    if not pool:
        return
    picked = yield from pick_from_pool(
        ctx, pool, {**selector, "count": 1}, "Swap in which Aura?", "aura_swap"
    )
    if not picked:
        return
    incoming = picked[0]

    move_object(ctx.state, ctx.source_oid, Zone.HAND, to_player=source.owner, cause="aura_swap")
    obj = ctx.state.objects[incoming]
    obj.controller = ctx.controller
    move_object(ctx.state, incoming, Zone.BATTLEFIELD, cause="aura_swap")
    if host is not None:
        # Attached *after* the move: `reset_permanent_state` clears
        # `attached_to` on the way onto the battlefield, which is the same trap
        # an Aura attaching itself during `spell_effects` falls into.
        attach(ctx.state, incoming, host)
    ctx.state.emit(
        "aura_swap", player=ctx.controller, source=ctx.source_oid, oid=incoming
    )


@register("pair")
def op_pair(ctx: EffectContext, spec: Mapping[str, Any]):
    """Soulbond — "you may pair this creature with another unpaired creature".

    The link is **symmetric**: both objects carry it. "As long as this creature
    is paired" is printed on the soulbond card and is read of the *partner* too
    -- both get the bonus -- so a one-way link in `attached_to`'s shape would
    buff exactly one of the two.

    It is also not `attached_to` for a second reason: an Aura attached to
    nothing is put into its owner's graveyard by a state-based action, and a
    creature whose partner died is simply unpaired. Two different lifetimes, so
    two different fields -- the argument `frozen_by` and `skip_next_untap`
    already made.

    Only *unpaired* creatures are offered, which is 702.94a and is also what
    stops one creature being paired with two.
    """
    selector = dict(spec.get("objects") or {})
    selector.setdefault("controller", "you")
    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    if source is None or source.paired_with is not None:
        return
    pool = [
        oid
        for oid in resolve_pool(ctx, selector)
        if oid != ctx.source_oid and ctx.state.objects[oid].paired_with is None
    ]
    if not pool:
        return
    picked = yield from pick_from_pool(
        ctx, pool, {**selector, "count": 1}, "Pair with", "pair"
    )
    if not picked:
        return
    partner = ctx.state.objects[picked[0]]
    source.paired_with = partner.oid
    partner.paired_with = source.oid
    ctx.state.bump_chars()
    ctx.state.emit("paired", player=source.controller, source=source.oid, oid=partner.oid)


@register("manifest")
def op_manifest(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 701.34a — "put the top card of your library onto the battlefield
    face down as a 2/2 creature".

    Manifest and morph are one mechanism seen from two sides: manifest puts a
    card there face down, morph *casts* one that way, and both produce the same
    2/2 shell that may be turned up later. Which is why the turn-face-up action
    is not morph's -- it is the face-down permanent's, and manifest's cards use
    the hidden card's own mana cost where morph's use the printed morph cost.

    Any card may be manifested, including a land: it is a 2/2 creature while it
    is face down whatever it really is, and only a *creature* card may be turned
    up (701.34c), which is checked where the action is offered.

    ``cloak`` (701.61a) is the third view of the same mechanism, and the whole
    difference is **ward {2}** on the shell. Everything else is identical --
    same 2/2, same "turn it face up any time for its mana cost if it's a
    creature card" -- so cloak is a flag on manifest rather than an op of its
    own. Written as a plain manifest, Unexplained Absence's cloaked permanents
    would be free to remove, which is most of what the keyword is worth.
    """
    cloak = bool(spec.get("cloak"))
    amount = max(1, evaluate_value(ctx, spec.get("amount", 1)))
    for pid in _players(ctx, spec.get("player", "you")):
        library = ctx.state.players[pid].library
        for _ in range(amount):
            if not library:
                break
            oid = library[0]
            obj = ctx.state.objects[oid]
            obj.controller = pid
            move_object(ctx.state, oid, Zone.BATTLEFIELD, cause="manifest")
            # After the move: `reset_permanent_state` clears it on the way in,
            # which is right for every other permanent and wrong for this one.
            obj.face_down = True
            obj.cloaked = cloak
            obj.revealed_to.add(pid)
            ctx.state.bump_chars()
            ctx.state.emit("cloaked" if cloak else "manifested", player=pid, source=oid)


@register("encode")
def op_encode(ctx: EffectContext, spec: Mapping[str, Any]):
    """Cipher — "exile this spell card encoded on a creature you control".

    Haunt's link pointed a third way. The card goes to exile and names a
    creature; the *card* is what has to notice that creature connecting, so the
    link points at the creature and the trigger reads it off the ability source.

    Distinct from `exiled_by` (which names the exiler, for O-Ring and imprint)
    and from `haunting` (which names a creature whose *death* matters). Three
    directions, three fields, and the triggers that read them ask three
    different questions.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Encode on", "encode")
    if not oids or ctx.source_oid is None:
        return
    source = ctx.state.objects.get(ctx.source_oid)
    if source is None or source.is_token:
        # A **copy** of a ciphered spell does not encode again (702.97b): a copy
        # is not a card, and there is nothing to exile. Epic's `not is_token`
        # guard for the same reason -- both keywords make copies that resolve
        # through the very code that armed them.
        return
    # The card is **not** moved here. A resolving sorcery is placed by
    # `_place_after_resolution` *after* its effects run, so an exile written
    # from inside `spell_effects` is immediately overwritten by the graveyard --
    # which is how this first failed, silently, with the card in the bin and the
    # link wiped by `reset_permanent_state` on the way.
    #
    # So encoding is a **rider on the destination**, the fourth on that slot
    # beside flashback's exile, buyback's hand and rebound's exile. `encoded_on`
    # survives the move because it is not battlefield state.
    source.encoded_on = oids[0]
    ctx.state.emit(
        "encoded", player=source.controller, source=ctx.source_oid, oid=oids[0]
    )


@register("cast_copy")
def op_cast_copy(ctx: EffectContext, spec: Mapping[str, Any]):
    """"…may cast a copy of the encoded card without paying its mana cost."

    A copy of *this ability's own card*, which is what separates it from
    `copy_spell`: that op copies something on the stack, and the encoded card is
    in exile with nothing on the stack to point at. Built through the same
    `put_copy_on_stack`, so a cipher copy is a token and announces its targets
    exactly as a storm copy does.

    The original stays in exile -- it is copied, not cast -- which is the whole
    of why cipher keeps paying.
    """
    from ..effects.ops_stack import put_copy_on_stack
    from ..structs import StackItem

    obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    if obj is None:
        return
    template = StackItem(
        sid=-1, kind="spell", controller=ctx.controller, def_id=obj.def_id, oid=obj.oid
    )
    put_copy_on_stack(ctx.state, ctx.controller, template)


@register("haunt")
def op_haunt(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 702.55a — "exile it haunting target creature".

    Two things at once, which is why it is one op: the source is exiled, and
    the exiled card is linked to the creature it haunts. `exile` cannot do the
    second half, because `exiled_by` points at the **exiler** -- the O-Ring
    direction, where the link is read back by the *exiler's* own trigger.

    Haunt needs the opposite. The card in exile is what survives, and it is what
    has to notice a creature dying somewhere else, so the link points from the
    haunting card at its victim and is read by a `haunted_by: "self"` trigger
    filter.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Haunt", "haunt")
    if not oids or ctx.source_oid is None:
        return
    source = ctx.state.objects.get(ctx.source_oid)
    if source is None:
        return
    exile(ctx.state, ctx.source_oid, cause="haunt")
    # After the move: `reset_permanent_state` runs on the way out and would wipe
    # this if it were set first -- the same ordering `exiled_by` needs.
    source.haunting = oids[0]
    ctx.state.emit(
        "haunt", player=source.controller, source=ctx.source_oid, oid=oids[0]
    )


@register("unattach")
def op_unattach(ctx: EffectContext, spec: Mapping[str, Any]):
    """Rule 701.3d — "Unattach this permanent." Reconfigure's second half.

    The attach model had no notion of coming *off*: `attach` moves an Equipment
    from wherever it is to a new creature, and every printed line before
    reconfigure only ever moved it. Nothing else can stand in — `attach` needs a
    destination, and detaching by moving to a creature you do not want it on is
    a different game action.

    Deliberately does **not** touch Auras. `sba` puts an Aura attached to
    nothing into its owner's graveyard, so unattaching one is a slow destroy
    written in a way that does not say so; the guard is on the card side, since
    no printed card unattaches an Aura and the op has no business inventing one.

    An already-unattached permanent is left alone rather than raising: "unattach
    this" on an Equipment sitting on the battlefield alone is a legal activation
    that does nothing, which is what the printed card says.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Unattach", "unattach")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or obj.attached_to is None:
            continue
        was = obj.attached_to
        obj.attached_to = None
        # Every static filtered on `attached` reads differently afterwards, and
        # so does the source's own type line while it is a reconfigure card.
        ctx.state.bump_chars()
        ctx.state.emit("unattached", player=obj.controller, source=oid, oid=was)


@register("add_subtype")
def op_add_subtype(ctx: EffectContext, spec: Mapping[str, Any]):
    """"It becomes a Vampire in addition to its other types." Captivating Vampire.

    The same two words as the `add_subtype` **static**, and a different
    mechanism: the static applies continuously to whatever currently matches its
    filter and stops when its source leaves, while this is written onto the one
    permanent it was pointed at and stays until that permanent changes zones.
    The printed lines differ the same way -- "creatures you control are
    Vampires" against "it becomes a Vampire".

    Types are always *added*.  Replacing a type line is `animate` or the
    `set_types` static.
    """
    subtypes = [str(t) for t in spec.get("subtypes", ())]
    if not subtypes:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Becomes")
    for oid in oids:
        add_subtypes(ctx.state, oid, subtypes)


@register("pump")
def op_pump(ctx: EffectContext, spec: Mapping[str, Any]):
    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Pump")
    for oid in oids:
        pump(ctx.state, oid, power, toughness, source=ctx.source_oid)


@register("grant_keyword")
def op_grant_keyword(ctx: EffectContext, spec: Mapping[str, Any]):
    """Grant keywords until end of turn, or -- with ``duration: "permanent"`` --
    for as long as the permanent lasts.

    Riot's "enters with haste" is the second: a haste that wore off at cleanup
    would let the creature attack the turn it arrived and be indistinguishable
    from the counter mode ever after, which is not a smaller version of the
    card, it is the wrong one half the time.
    """
    keywords = spec.get("keywords") or ([spec["keyword"]] if "keyword" in spec else [])
    permanent = str(spec.get("duration", "until_end_of_turn")) == "permanent"
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant")
    for oid in oids:
        for keyword in keywords:
            grant_keyword(
                ctx.state, oid, str(keyword), source=ctx.source_oid, permanent=permanent
            )


@register("grant_protection")
def op_grant_protection(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Creatures you control gain protection from each color until end of turn."

    The effect half of the `protection` static, which existed only as a printed
    ability on a permanent: `protection_from` collected candidates from
    `_battlefield_statics`, which walks `card.abilities` and never saw anything
    granted. Akroma's Will is the card, and there is no near miss --
    `grant_keyword` cannot carry a parameter, and protection is parameterised by
    definition ("from black", "from Wizards").

    One `TempEffect` per quality rather than one carrying a list, because
    `TempEffect.keyword` is already a single string and `protection_from`
    already returns a flat set of qualities: three colours is three entries and
    nothing had to learn a new shape.
    """
    from ..characteristics import resolve_chosen_color_list

    # "…protection from the color of your choice" -- Brave the Elements, whose
    # colour is named by a `choose_color` earlier in the same effect list and
    # read back off the spell's own object. The substitution is the leaf the
    # anthem and the mana ability use; an unmade choice drops out, so the
    # sentence grants protection from nothing rather than from everything.
    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    qualities = [
        *resolve_chosen_color_list(spec.get("from_colors"), source),
        *(spec.get("from_types") or ()),
        *(spec.get("from_subtypes") or ()),
    ]
    if not qualities:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant protection to")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        for quality in qualities:
            obj.until_eot.append(
                TempEffect(kind="protection", keyword=str(quality), source=ctx.source_oid)
            )
    ctx.state.bump_chars()


@register("animate")
def op_animate(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Becomes a 4/4 white and blue Elemental creature with vigilance until end
    of turn. It's still a land."

    One op for the whole sentence, keywords included, rather than an `animate`
    beside a `grant_keyword`: the authoring verifier's residual gate asks each
    *ability* which printed sentence it implements, and a creature-land's
    animation is one sentence.  Splitting it would work and would read as two
    claims on the same line.

    Distinct from `set_pt`, which is a compensating pump over whatever the
    permanent's power happens to be right now.  An animation names the base
    value, so counters and anthems add to it instead of being cancelled by it.
    """
    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    types = [str(t) for t in spec.get("types", ("Creature",))]
    subtypes = [str(t) for t in spec.get("subtypes", ())]
    colors = [str(c) for c in spec.get("colors", ())]
    keywords = [str(k) for k in spec.get("keywords", ())]
    oids = yield from choose_objects(ctx, spec.get("objects"), "Animate")
    for oid in oids:
        animate(
            ctx.state,
            oid,
            power,
            toughness,
            types=types,
            subtypes=subtypes,
            colors=colors,
            source=ctx.source_oid,
        )
        for keyword in keywords:
            grant_keyword(ctx.state, oid, keyword, source=ctx.source_oid)


@register("monstrosity")
def op_monstrosity(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Monstrosity N": counters and a one-way flag, in that order.

    The flag is the mechanic. Without it the ability is a repeatable pump, and
    the "when this becomes monstrous" trigger that usually accompanies it would
    fire every time rather than once.
    """
    from ..events import EventType
    from ..triggers import fire

    amount = evaluate_value(ctx, spec.get("amount", 1))
    oid = ctx.source_oid
    obj = ctx.state.objects.get(oid) if oid is not None else None
    if obj is None or not obj.on_battlefield or obj.monstrous:
        return
    add_counters(ctx.state, oid, PLUS_ONE, amount, source=oid)
    obj.monstrous = True
    ctx.state.bump_chars()
    fire(
        ctx.state,
        EventType.BECAME_MONSTROUS,
        player=obj.controller,
        source=oid,
        oid=oid,
        card=obj.def_id,
        amount=amount,
    )


@register("freeze")
def op_freeze(ctx: EffectContext, spec: Mapping[str, Any]):
    """"…don't untap during their controllers' untap steps for as long as you
    control this creature."

    Recorded on the frozen permanent as the *oid of the source*, rather than as
    a flag with a lifetime of its own: the hold has to end when the source does,
    and pointing at it is the only way the untap step can tell.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Freeze")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.frozen_by = ctx.source_oid


@register("grant_ability")
def op_grant_ability(ctx: EffectContext, spec: Mapping[str, Any]):
    """Give a permanent one of this card's ``grantable_abilities``.

    "…and 'Whenever this creature deals combat damage to a player, draw a
    card'." The quoted ability is written out on the granting card and referred
    to here by index, so there is one definition of it rather than a copy.

    Until end of turn by default, or ``duration: "permanent"`` for as long as
    the permanent lasts -- the same option `grant_keyword` already carries.
    Clavileño's "It gains 'when this creature dies, …'" prints no duration, and
    a grant swept at cleanup would be a strictly weaker card that looks
    identical on the turn it was made.
    """
    # Both spellings, because two shipped cards disagree and the disagreement is
    # invisible: `ability` and `ability_index` each defaulted to 0, so a card
    # using the other name worked by accident and would silently have granted
    # the wrong ability the first time a card carried two grantables. The loader
    # now insists on one of them being present.
    index = int(spec.get("ability", spec.get("ability_index", 0)))
    permanent = str(spec.get("duration", "until_end_of_turn")) == "permanent"
    oids = yield from choose_objects(ctx, spec.get("objects"), "Grant an ability to")
    if ctx.source_oid is None:
        return
    for oid in oids:
        grant_ability(ctx.state, oid, index, ctx.source_oid, permanent=permanent)


@register("skip_untap")
def op_skip_untap(ctx: EffectContext, spec: Mapping[str, Any]):
    """"It doesn't untap during its controller's next untap step."

    A *one-shot*, cleared by the untap step it skips -- which is what separates
    it from `freeze`, where the hold lasts as long as its source is on the
    battlefield. Using either for the other would be wrong in both directions,
    so they are two ops over two fields rather than one with a flag.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Keep tapped")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.skip_next_untap = True


@register("lock_abilities")
def op_lock_abilities(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Its activated abilities can't be activated this turn."

    Separate from `tap`, which usually accompanies it, because the two are
    different halves of the sentence and a card may want only one.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Lock")
    for oid in oids:
        lock_abilities(ctx.state, oid, source=ctx.source_oid)


@register("set_pt")
def op_set_pt(ctx: EffectContext, spec: Mapping[str, Any]):
    """Set base power/toughness until end of turn.

    Implemented as a pump that cancels the current values, which is equivalent
    under this engine's fixed-order characteristic pipeline for the cards in the
    curated decks (none of them combine ``set_pt`` with counters).
    """
    from ..characteristics import chars

    power = evaluate_value(ctx, spec.get("power", 0))
    toughness = evaluate_value(ctx, spec.get("toughness", 0))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Set power/toughness")
    for oid in oids:
        current = chars(ctx.state, oid)
        pump(
            ctx.state,
            oid,
            power - current.power,
            toughness - current.toughness,
            source=ctx.source_oid,
        )


def _players(ctx: EffectContext, spec: Any) -> list[int]:
    from .selectors import select_players

    return select_players(ctx, spec)


@register("detain")
def op_detain(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Until your next turn, that permanent can't attack or block and its
    activated abilities can't be activated." (701.30a)

    Three restrictions in one op rather than three, because detain is one
    printed word and the authoring verifier's residual gate asks each *ability*
    which sentence it implements. Splitting it would read as three claims on
    one line, and a card that got two of the three would look implemented.

    It records **who** detained rather than when it ends. "Your next turn" is
    not a fixed turn number: eliminate a player and it moves. `turn._untap_step`
    clears the detain belonging to whoever is untapping, which is that sentence
    said once, in the one place it can be right.

    Not a `TempEffect` for the reason `must_attack` is not: `until_eot` is wiped
    at cleanup, and detain has to survive the turn it was cast in -- usually a
    whole turn cycle. A detain that expired at end of turn would be a strictly
    worse card than the printed one, and nothing would say so.
    """
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.detained_by = ctx.controller
    ctx.state.bump_chars()
    yield from ()


@register("proliferate")
def op_proliferate(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Choose any number of permanents and/or players with a counter on them,
    then give each another counter of each kind already there." (701.27a)

    The census called this blocked because "counter kinds are not enumerable
    off an object". They always were -- `GameObject.counters` is a dict keyed by
    kind -- and what was actually missing is that proliferate is not an
    add-counters with a filter. It is *"of each kind already there"*, so the
    kinds are read per permanent at resolution and differ between them: the
    same proliferate adds a +1/+1 here and a loyalty counter there.

    Simplified in one way, and it is the documented kind. Rule 701.27a lets the
    player choose *any number*; this proliferates every permanent they control
    that has a counter. The choice only ever matters for counters you would
    rather not grow -- a -1/-1 counter on your own creature -- and offering a
    free multi-select over the whole board is a large decision for a rare
    downside. `objects` narrows it when a card wants that.
    """
    selector = dict(spec.get("objects") or {"controller": "you"})
    for oid in resolve_pool(ctx, selector):
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        # Snapshotted: `add_counters` mutates the dict being read, and the
        # kinds are "already there" as of the moment proliferate resolves.
        for kind, amount in list(obj.counters.items()):
            if amount > 0:
                add_counters(ctx.state, oid, kind, 1, source=ctx.source_oid)
    yield from ()


@register("set_flag")
def op_set_flag(ctx: EffectContext, spec: Mapping[str, Any]):
    """"…and it becomes renowned." A one-way word written onto a permanent.

    Renown's whole content is that it happens once: "if it isn't renowned, put
    N +1/+1 counters on it and it becomes renowned". Without somewhere to
    record the word, the trigger fires on every combat damage and the creature
    grows for ever -- and the counters alone cannot stand in for it, because
    anything else that removes them would make the creature renewably renowned.

    Generic rather than a `renowned` boolean beside `monstrous`, because the
    shape repeats: each new adjective would otherwise be a field, a condition
    leaf and an op to say one word. Read back with `{"has_flag": "renowned"}`.
    """
    flag = str(spec["flag"])
    for oid in resolve_pool(ctx, spec.get("objects") or {"self_only": True}):
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.flags.add(flag)
    yield from ()


@register("set_turn_flag")
def op_set_turn_flag(ctx: EffectContext, spec: Mapping[str, Any]):
    """"…and it has been exerted." A word that wears off at the turn boundary.

    `set_flag` above with the other lifetime, and a separate op for the reason
    `skip_untap` and `freeze` are separate: the two durations are different rules
    objects, and using either for the other is wrong in both directions and
    invisible in a one-turn test. `set_flag` is one-way *on purpose* -- renown
    must never be re-earned, so nothing ever removes from `obj.flags` -- while
    "if this creature hasn't been exerted **this turn**" (Combat Celebrant,
    701.40b) has to be false again next turn. Written there, the guard would read
    "hasn't been exerted this game" and the card would work exactly once.

    Written to `TurnLedger.object_flags` rather than to the permanent, so it is
    cleared by the same cleanup that clears morbid and storm and needs no sweep
    of its own -- and so the record survives the object leaving the battlefield,
    which is what a past-tense clause says. Read back with
    `{"has_turn_flag": "exerted"}`.

    Exert is its first customer and does not otherwise need it: the keyword is
    still an `attacks` trigger, a `may` and `skip_untap` (see `test_exert.py`).
    This op is the *record* of the choice, which is why it goes inside the `may`
    beside `skip_untap` and not around it -- a declined `may` exerts nothing.
    """
    flag = str(spec["flag"])
    for oid in resolve_pool(ctx, spec.get("objects") or {"self_only": True}):
        if oid in ctx.state.objects:
            ctx.state.turn_ledger.set_object_flag(oid, flag)
    yield from ()


@register("move_counters")
def op_move_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    """Take counters off one permanent and put them on another.

    Graft ("move a +1/+1 counter from this creature onto it") and modular
    ("put its +1/+1 counters on target artifact creature"). Not `remove_counters`
    beside `add_counters`, for one reason that matters and one that does not:

    - **The amount is whatever was there.** Modular moves *all* of them, and the
      number is not knowable when the card is written. Two ops would need the
      count threaded between them through a binding that nothing sets.
    - It is one printed sentence, so the authoring verifier's residual gate sees
      one ability implementing one clause.

    ``amount`` defaults to every counter of that kind on the source. It is
    clamped to what is actually there, so a graft creature with one counter left
    moves one and not the two the card asked for -- moving counters that do not
    exist would create them out of nothing.

    The source is `from`, defaulting to this permanent, and the destination is
    `objects`. A move to nowhere still takes nothing off the source: with no
    legal destination the counters stay put, which is what "move ... onto it"
    says when "it" is gone.
    """
    kind = str(spec.get("counter", PLUS_ONE))
    if "from" in spec:
        sources = resolve_pool(ctx, spec["from"])
    else:
        # This permanent, wherever it is -- deliberately *not* the selector
        # `{"self_only": true}`, which resolves through a battlefield scan and
        # therefore finds nothing for a modular creature that has just died.
        # "Its +1/+1 counters" is about the card the ability came from, and by
        # the time that ability resolves the card is in a graveyard.
        sources = [ctx.source_oid] if ctx.source_oid is not None else []
    destinations = yield from choose_objects(ctx, spec.get("objects"), "Move counters to")
    if not sources or not destinations:
        return
    for source_oid in sources:
        source = ctx.state.objects.get(source_oid)
        if source is None:
            continue
        available = source.counter(kind)
        wanted = evaluate_value(ctx, spec["amount"]) if "amount" in spec else available
        if source.on_battlefield:
            # Clamped: moving counters that are not there would create them.
            moving = max(0, min(available, wanted))
        else:
            # Modular. The source is in a graveyard and `reset_permanent_state`
            # emptied its counters on the way, so `available` is zero and the
            # clamp would move nothing -- the same trap persist fell into. The
            # count comes from the card's own `amount`, which says
            # `{"counters_had": "+1/+1"}` and reads the dies event's snapshot,
            # and there is nothing left on the source to remove.
            moving = max(0, wanted)
        if not moving:
            continue
        if source.on_battlefield:
            remove_counters(ctx.state, source_oid, kind, moving)
        for dest_oid in destinations:
            add_counters(ctx.state, dest_oid, kind, moving, source=ctx.source_oid)


@register("must_block")
def op_must_block(ctx: EffectContext, spec: Mapping[str, Any]):
    """Provoke: "target creature blocks this creature this combat if able."

    The mirror of `must_attack`, and deliberately not the same op with a flag.
    A block requirement always names *what* to block -- an attacker chosen when
    the requirement is placed -- where an attack requirement names nothing, so
    the two carry different data and expire on different clocks.

    ``attacker`` names which creature must be blocked, and defaults to the
    ability's own source, which is every printed provoke. It is recorded as an
    oid on the blocker rather than as a `TempEffect` for the same reason
    `must_attack` is: it is not a characteristic, nothing reads it through
    `chars`, and `combat.blocks_valid` is the one place it means anything.

    Scoped to one combat -- `finish_blockers` spends every requirement whether
    or not it was met, because "if able" excuses a creature that could not
    block and leaving the flag set would compel the next combat as well.

    This op does *not* untap its target. Provoke's own text untaps first and
    then requires the block, which is two clauses and two ops -- and keeping
    them apart is what lets the lure family, which requires without untapping,
    say what it means.
    """
    attacker_oids = resolve_pool(ctx, spec["attacker"]) if "attacker" in spec else []
    attacker = attacker_oids[0] if attacker_oids else ctx.source_oid
    if attacker is None:
        return
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.must_block = attacker
    yield from ()


@register("must_attack")
def op_must_attack(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Target creature attacks during its controller's next combat phase if able."

    A *requirement*, which is a shape the engine had none of: every other way a
    card touches combat removes an option (tap, freeze, skip_untap, defender)
    and this one removes the option not to. It is enforced in `legality` by
    withholding "Done attacking" while an able creature that must attack is not
    attacking.

    Two durations, and the difference is which combat is meant:

    ``this_turn``     Bident of Thassa -- the combat in the turn it was used,
                      and nothing later.
    ``next_combat``   Trench Behemoth -- the *controller's* next combat phase,
                      which for an opponent's creature is a later turn. It
                      cannot be "this turn": the trigger fires on your landfall,
                      and the affected player's combat has not happened yet.

    Not a `TempEffect`, for that reason -- those are wiped by the cleanup step,
    and this has to outlive it.
    """
    duration = str(spec.get("duration", "next_combat"))
    if duration not in ("this_turn", "next_combat"):  # pragma: no cover - loader guards
        raise DslError(f"unknown must_attack duration {duration!r}")
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.must_attack = duration
        obj.must_attack_turn = ctx.state.turn
    yield from ()


@register("goad")
def op_goad(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Goad those creatures." (701.38a)

    Two rules in one printed word, and both of them "if able":

    1. **The compulsion.** Until the goading player's next turn, the creature
       attacks each combat if able. Read live in `combat.attack_required`, which
       is where `must_attack` and the `attacks_if_able` static already meet.
    2. **The target restriction.** If it attacks, it must attack a player other
       than the goading player if able. Read in
       `combat.attack_target_forbidden`, the per-attacker/per-defender seam
       `cant_attack_player` built and left open for exactly this.

    The second half is why goad is not a compulsion with a longer clock: nothing
    in the engine restricted *which* defender a given attacker could pick, and
    without it a goaded creature swings straight back at the player who goaded
    it -- which is the whole political point of the word, and a symmetrical
    Overrun without it.

    The datum written down is the **player**, in `GameObject.goaded_by`, which is
    the shape detain uses and is forced twice over. "Until your next turn" is not
    a turn number -- eliminate a player and it moves -- so `turn._untap_step`
    clears the marks belonging to whoever is untapping, beside detain and the
    block prohibitions. And the target restriction *needs* to know who: a goad is
    a fact about a pair, not about a creature.

    A set, so two opponents may goad the same creature and each clock runs
    separately -- and so does each "other than you", which is why a creature
    goaded by both remaining opponents is free to attack either of them.

    Why not the two existing shapes:

    * `must_attack` is one-shot. `combat.discharge_attack_requirements` spends
      the flag when attackers lock in, so it compels one combat where goad
      compels every combat until the goader untaps -- and it carries no notion of
      who goaded, which is the datum half of goad is about.
    * the `attacks_if_able` **static** is the live, unspent form, but it is a
      continuous ability on a permanent read off `_battlefield_statics`. A
      resolving sorcery leaves nothing on the battlefield to own it, its
      `affects` filter reads only printed characteristics so it cannot mean
      "those creatures" (the set chosen at resolution), and it cannot end at a
      player's next turn.

    ``objects`` is required (the loader says so): a goad with no selector goads
    nobody, and the card would resolve, log nothing and change no combat.
    ``player`` is the goader and defaults to the effect's controller, which is
    every printed goad -- it is spelled out only so a "goaded by target
    opponent" line has somewhere to say it.
    """
    goaders = _players(ctx, spec["player"]) if "player" in spec else [ctx.controller]
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        for player in goaders:
            # Battlefield and liveness are checked in the primitive, which is
            # also what makes a creature that left in response get nothing.
            goad_creature(ctx.state, oid, player)
    yield from ()


@register("cant_attack_player")
def op_cant_attack_player(ctx: EffectContext, spec: Mapping[str, Any]):
    """"You can't attack that player this turn." "They can't attack you this combat."

    The first attack prohibition in the engine that names a **defending player**.
    Everything else that stops an attack is a fact about one creature -- the
    `cant_attack` static, `defender`, being tapped, being detained -- and
    `characteristics.attack_forbidden` matches its filter against the attacking
    creature with no defender in the question at all.  So "can't attack *this
    player*" was not a weaker version of any of them; it was a different sentence,
    and it needed `combat.attack_target_forbidden` to have somewhere to be asked.

    Three parameters, and every one of them is load-bearing on a printed card:

    ``attacker``  the player who may not attack. Call for Aid means the spell's
                  own controller (`"you"`); Champions of Minas Tirith means the
                  opponent whose combat it is (`{"binding": "event_player"}`).
    ``defender``  the player who may not be attacked -- the mirror image of the
                  above on those two cards, which is exactly why both had to be
                  spelled out rather than one inferred as "the other one".
    ``duration``  ``this_turn`` or ``this_combat``. Required, not defaulted: see
                  `structs.AttackRestriction`.

    Both selectors are full player specs and may name several players, in which
    case the cross-product is installed -- "creatures your opponents control
    can't attack you" is `each_opponent` against `you`, one sentence and one op.

    ``planeswalkers``  optional, default `false`. Does the prohibition also stop
    an attack on the defender's **planeswalkers**? Off on every line that names
    a seat, which is 506.2 -- attacking somebody's walker is not attacking them,
    and that is why Ghostly Prison taxes nothing when the attack goes at one. On
    for the sentence that names **no defender at all**, which is the whole of
    "creatures can't attack this combat" (Overencumbered): written as
    `each_player` against `each_player` with this flag, so every seat and every
    walker is closed and no creature has a legal declaration left.

    That whole-table form is why the flag lives here rather than becoming a
    fourth prohibition. `cant_attack` is the near miss and cannot be limited to
    one combat -- it is a continuous ability read off `_battlefield_statics` for
    as long as its source sits there, and Overencumbered's lock is bought and
    lost each combat by a payment. `cant_attack_you` is the other and is a
    static too, besides being scoped to the seat its permanent sits under.

    Nothing is written on any permanent, and that is the point: a resolving
    sorcery leaves no source on the battlefield to hang a static off, which is
    the first of the three reasons the `cant_attack` static could not do this job.
    """
    from ..structs import ATTACK_RESTRICTION_DURATIONS

    duration = str(spec.get("duration", "this_turn"))
    if duration not in ATTACK_RESTRICTION_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_attack_player duration {duration!r}")
    planeswalkers = bool(spec.get("planeswalkers", False))
    attackers = _players(ctx, spec.get("attacker"))
    defenders = _players(ctx, spec.get("defender"))
    for attacker in attackers:
        for defender in defenders:
            restrict_attack(
                ctx.state,
                attacker,
                defender,
                duration,
                source=ctx.source_oid,
                planeswalkers=planeswalkers,
            )
    yield from ()


@register("cant_block")
def op_cant_block(ctx: EffectContext, spec: Mapping[str, Any]):
    """"That creature can't block this turn." "Until your next turn, those
    creatures can't block."

    The same sentence the `cant_block` **static** prints, and a different thing.
    The static is an ability on a permanent: `characteristics.block_forbidden`
    reads it off `_battlefield_statics`, it lasts exactly as long as its source
    sits on the battlefield, and its `affects` filter may read only printed
    characteristics.  So it can say "creatures your opponents control can't
    block, while I am here" and it can say nothing else -- not the creature a
    trigger targeted, not "this turn", not "until your next turn".  This op is
    that sentence with the source and the clock swapped round, which is why it
    is an op and not a fourth filter key.  (`grant_ability` could not carry it
    either: `loader.py` refuses any grantable ability that is not triggered.)

    Two shapes, and both printed cards need both of them:

    ``objects``        the creatures chosen **at resolution**: Aragorn's "up to
                       one target creature can't block this turn", Taunt from
                       the Rampart's "those creatures".  A fixed set -- a
                       creature that enters afterwards was not one of "those".
    ``all_creatures``  *every* creature: Aragorn's "creatures can't block this
                       turn", the else-half of the same trigger.  A continuous
                       effect for the rest of the turn, so it catches creatures
                       that enter later too, which is exactly what a per-object
                       mark could not do.

    Exactly one of the two, enforced by the loader.  They are not a general and
    a special case of each other: writing the global form as a snapshot of the
    battlefield would be a strictly weaker card than the printed one, and
    letting a `cant_block` with no `objects` mean "everything" would turn a
    fizzled optional target into a one-sided Falter.

    ``duration`` is required, and the two are not interchangeable:
    ``this_turn`` is cleared by the cleanup step, ``until_your_next_turn`` in
    the controller's own untap step, beside detain and on detain's clock.  Note
    that detain is not a substitute for either -- it also forbids attacking and
    activating abilities, and Taunt from the Rampart's other half *demands* the
    attack it would forbid.
    """
    from ..structs import BLOCK_PROHIBITION_DURATIONS

    duration = str(spec.get("duration", "this_turn"))
    if duration not in BLOCK_PROHIBITION_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_block duration {duration!r}")
    if spec.get("all_creatures"):
        oids: list[int] | None = None
    else:
        # Battlefield-filtered here rather than in the primitive: a creature
        # already gone when the trigger resolves is not restricted, and keeping
        # the dead oid would make the entry look like it bit somebody.
        oids = [
            oid
            for oid in resolve_pool(ctx, spec.get("objects") or {})
            if (obj := ctx.state.objects.get(oid)) is not None and obj.on_battlefield
        ]
    forbid_block(
        ctx.state, oids, duration, player=ctx.controller, source=ctx.source_oid
    )
    yield from ()


@register("unblockable")
def op_unblockable(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Target creature can't be blocked this turn." (Rogue's Passage.)

    `cant_block` above with the creatures swapped round: that op names a would-be
    blocker, this one names an attacker and stops every block against it.  They
    meet in `combat.can_block`, where each is an independent early-out, and they
    are two ops rather than one with a side flag because they are two sentences
    that no card prints together.

    The engine's existing "can't be blocked" is the `block_restriction` static
    ("this creature can't be blocked by Humans"), and it cannot say this line for
    the three reasons the gap record gives: it must live on a permanent that is
    on the battlefield, it lasts exactly as long as that permanent does, and its
    filters read only printed characteristics -- so it cannot be aimed at the
    creature an activated ability targeted, and it cannot stop at end of turn.
    `grant_ability` cannot smuggle one across either: granted abilities are read
    by `triggers.py` alone and `characteristics._battlefield_statics` never
    consults them, so a granted static would load clean and do nothing.

    ``objects`` is a selector resolved **now** -- normally ``{"target": "t1"}``.
    Unlike `cant_block` there is no ``all_creatures`` counterpart: no printed
    one-shot makes everything unblockable, and the plural forms that come close
    are controller-scoped, which a global flag would read wrongly and in the
    card's favour.  Battlefield-filtered here for the reason `cant_block` filters
    there: a creature already gone when this resolves gets nothing, and keeping
    its oid would make the entry look like it bit somebody.

    ``duration`` is required and the two words are not interchangeable:
    ``this_turn`` ends at cleanup, ``until_your_next_turn`` in the granting
    player's own untap step.
    """
    from ..structs import UNBLOCKABLE_DURATIONS

    duration = str(spec.get("duration", "this_turn"))
    if duration not in UNBLOCKABLE_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown unblockable duration {duration!r}")
    oids = [
        oid
        for oid in resolve_pool(ctx, spec.get("objects") or {})
        if (obj := ctx.state.objects.get(oid)) is not None and obj.on_battlefield
    ]
    make_unblockable(
        ctx.state, oids, duration, player=ctx.controller, source=ctx.source_oid
    )
    yield from ()


@register("cant_sacrifice")
def op_cant_sacrifice(ctx: EffectContext, spec: Mapping[str, Any]):
    """"You can't sacrifice those creatures this turn." (Call for Aid, 701.17b.)

    The engine's first sacrifice prohibition of any kind, and the fourth op in
    this family to put a one-shot restriction on the table rather than on a
    permanent -- `cant_attack_player`, `cant_block` and `unblockable` are the
    other three, and it is the same shape for the same reason: a resolving
    sorcery leaves no source on the battlefield for a static to live on, and the
    set it names is chosen when it resolves rather than matched by a filter over
    printed characteristics.

    Nothing existing came close, which is why this is an op and not a parameter
    of one:

    * `lock_abilities` is the near relative the gap record names, and it gates
      the wrong thing. It stops *this permanent's own* activated abilities, so
      it says nothing about an Altar three permanents away whose cost eats this
      one, and nothing at all about the `sacrifice` op or an edict.
    * `replace_deaths` redirects a permanent's death after the sacrifice has
      already happened. The creature still leaves the battlefield and the outlet
      still got paid, which is not what "can't" means.
    * `grant_keyword` indestructible is explicitly not this (701.17a), and no
      prevention or protection is either: a sacrifice is neither damage nor
      destruction.

    Two roads reach a sacrifice and this op closes both of them, because the
    printed rule does not distinguish between them:

    **cost**    an outlet's activation cost, or an additional cost to cast. The
                pool the cost may be paid from drops the protected permanents
                (`costs._sacrifice_pool`, plus `legality._emerge_fodder` for
                emerge and offering, whose fodder is chosen as part of the cast
                action), so a cost that needs one becomes *unpayable* and is
                never offered.
    **effect**  the `sacrifice` op -- "each player sacrifices a creature". The
                pool it chooses from drops them too, so the edict takes
                something else, and does nothing only when there is nothing
                else.

    ``objects`` is required and resolved **now**: "those creatures" is the set
    the same spell just gained control of. There is deliberately no wildcard
    form -- no printed one-shot protects the whole board, and a global sentinel
    would read a one-sided sentence as a two-sided one. ``duration`` is required
    and ``this_turn`` is the only word implemented; see
    `structs.SACRIFICE_RESTRICTION_DURATIONS`.

    Unlike `cant_block` and `unblockable` the pool is **not** filtered to the
    battlefield here. Those two record creatures for a combat that has not
    happened yet, where a dead oid would look like an entry that bit somebody;
    this one is read by pools that already contain nothing but permanents on the
    battlefield, and dropping a creature that flickered out in response would
    mean it comes back sacrificeable -- a distinction the printed card does not
    draw. See `primitives.forbid_sacrifice`.
    """
    from ..structs import SACRIFICE_RESTRICTION_DURATIONS

    duration = str(spec.get("duration", "this_turn"))
    if duration not in SACRIFICE_RESTRICTION_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_sacrifice duration {duration!r}")
    forbid_sacrifice(
        ctx.state,
        resolve_pool(ctx, spec.get("objects") or {}),
        duration,
        source=ctx.source_oid,
    )
    yield from ()
