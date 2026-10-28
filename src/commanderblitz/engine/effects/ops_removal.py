"""Effect ops that move permanents off or onto the battlefield: destroy, exile,
sacrifice, phase, copy, tokens."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..errors import DslError
from ..objects import playable_duration_of
from ..player_statics import forced_discard_or_sacrifice_barred
from ..primitives import add_counters, attach, create_token
from ..temp_effects import sacrifice_forbidden
from ..turn import phase_in, phase_out
from ..zones import (
    destroy,
    exile,
    link_exiled,
    move_object,
    offer_enters_replacement,
    offer_riot_choice,
    sacrifice,
)
from ..zones import snapshot as capture_snapshot
from .board_helpers import (
    _aim_at_planeswalker,
    _attack_defender,
    _attack_target,
    _attacking_player,
    _offer_blocks_to,
    _players,
)
from .context import EffectContext
from .registry import register
from .selectors import (
    ZONE_NAMES,
    choose_objects,
    pick_from_pool,
    resolve_pool,
)
from .values import evaluate_value


@register("destroy")
def op_destroy(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Destroy target creature", and optionally "It can't be regenerated."

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
    """ "If [these creatures] would die this turn, exile them instead."

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
    """ "…become a copy of another target creature you control." Rule 706.

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
        # A new copy effect replaces the old one whole, exception and all.
        obj.copying_keywords = None
        obj.copying_until_eot = until_eot
    ctx.state.bump_chars()


@register("replace_leaves_battlefield")
def op_replace_leaves_battlefield(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Exile it ... if it would **leave the battlefield**." Unearth (702.83a).

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
        raise DslError(f"replace_leaves_battlefield: unknown destination {destination!r}")
    oids = yield from choose_objects(ctx, spec.get("objects"), "Redirect on leaving", "replace")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            obj.leaves_to = destination


@register("phase_out")
def op_phase_out(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Target creature phases out." (702.26)

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

    # `until_leaves` is the O-Ring name for the link and `link` is the neutral
    # one, exactly as on `exile`, and the same two halves: this op records the
    # link and nothing else, and the *return* is an ordinary
    # `leaves_battlefield` trigger on the same card reading the link back
    # through a `{"phased_out_with": "self"}` selector. Two abilities because
    # the card really is two, and a player can respond between them.
    #
    # Without a link the permanent comes back at its controller's next untap
    # step, which is what the plain printed one-shot says. With one it waits on
    # this permanent, and `turn._phasing` skips it.
    link = bool(spec.get("until_leaves")) or bool(spec.get("link"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Phase out", "phase_out")
    for oid in oids:
        phase_out(ctx.state, oid, by=ctx.source_oid if link else None)
    ctx.state.bump_chars()


@register("phase_in")
def op_phase_in(ctx: EffectContext, spec: Mapping[str, Any]):
    """Phase a permanent back in -- the return half of a linked `phase_out`.

    Oubliette: "target creature phases out until this enchantment leaves the
    battlefield. Tap that creature as it phases in this way." The second
    sentence is ``tapped``, and it is a parameter here rather than a `tap` op
    afterwards because "as it phases in" is one event -- a separate tap happens
    to a creature that has already returned untapped.

    Its `objects` selector is normally `{"phased_out_with": "self"}`, which is
    the only way to name a phased-out permanent: one is out of
    `state.battlefield` entirely, so no ordinary battlefield selector reaches
    it.
    """

    tapped = bool(spec.get("tapped"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Phase in", "phase_in")
    for oid in oids:
        phase_in(ctx.state, oid, tapped=tapped)
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
    # `playable_this_turn` is the boolean this started as; `playable` is the
    # same permission with a duration, and the two are one key with two
    # spellings rather than two keys -- writing both is a load error.
    playable_duration = playable_duration_of(spec)
    playable = playable_duration is not None
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
                obj.playable_duration = playable_duration
                # Elder Brain's "you may spend mana as though it were mana of
                # any color to cast it" -- printed beside the permission, and
                # read only while it is live.
                obj.playable_any_color = bool(spec.get("any_color"))
        if link and ctx.source_oid is not None:
            # After the move: `move_object` runs `reset_permanent_state` on the
            # way, which would wipe this if it were set first.
            link_exiled(ctx.state, oid, ctx.source_oid)


@register("airbend")
def op_airbend(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "**Airbend** all other creatures." -- Avatar's Wrath.

    The reminder text is the whole mechanic: "Exile them. While each one is
    exiled, its owner may cast it for {2} rather than its mana cost." So it is
    `exile` with a permission riding on it, and both halves of that permission
    are ones `exile` could not say.

    **The owner, not the caster.** `exile`'s `playable` writes
    ``obj.playable_by = ctx.controller`` -- one seat, the resolving spell's --
    which is right for the impulse-draw family it was written for and exactly
    wrong here: airbend sweeps the whole board, so most of what it exiles
    belongs to somebody else, and granting the permission to `ctx.controller`
    would hand me my opponents' creatures. The owner is read off the object,
    and `owner` is the one identity a card never loses (108.3), so it is the
    same seat however the permanent got where it was -- a creature I stole with
    `gain_control` goes back to the player who brought it.

    **A flat {2}, replacing the price.** `playable_alt_cost` rather than any of
    the reduction machinery, because `cost_reduction.cost_reduction` clamps a reduction
    to the generic part of a cost and no subtraction is right for two creatures
    of different mana values anyway. {2} is {2} whether the card printed {G} or
    {7}{U}{U}, and a {G} creature "reduced" by anything still owes its green
    pip.

    The permission lasts "while each one is exiled", so it carries no clock of
    its own: `reset_permanent_state` wipes every `playable_*` field as the card
    leaves exile (400.7 makes it a new object anyway), which is precisely the
    moment the printed sentence ends. That is the ``"while_exiled"`` duration,
    the same one `exile`'s own `playable: "while_exiled"` spells.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Airbend", "destroy")
    if name := spec.get("as"):
        # Written before the move, for `op_exile`'s reason: the binding records
        # what this op airbent rather than whatever is in exile once it is done.
        previous = ctx.bindings.get(str(name))
        earlier = list(previous) if isinstance(previous, list) else []
        ctx.bindings[str(name)] = earlier + list(oids)
    for oid in oids:
        exile(ctx.state, oid, by=ctx.source_oid)
        # After the move, for `op_exile`'s reason: `move_object` runs
        # `reset_permanent_state` on the way and would wipe all of this.
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        obj.playable_by = obj.owner
        obj.playable_turn = ctx.state.turn
        obj.playable_duration = "while_exiled"
        obj.playable_alt_cost = str(spec.get("cost", "{2}"))


@register("become_prepared")
def op_become_prepared(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "This creature **becomes prepared**." Emeritus of Woe // Demonic Tutor.

    The turning-on half of the state; the turning-off is the rules' own -- "you
    may cast a copy of its spell. **Doing so unprepares it**" is reminder text,
    so `Game._cast` clears it and no card ever writes that.

    **Not `set_flag`.** A flag is inert bookkeeping -- renown is stored that way
    -- and nothing in the casting-permission path reads `obj.flags`, so a
    permanent flagged "prepared" would gain no ability to cast anything and the
    card would silently do nothing. `set_flag` also has no counterpart that
    clears one, and `set_turn_flag` expires at the turn boundary rather than on
    use, which is a different card again: prepared survives until it is spent.

    **Not a counter**, either. The reminder text is the whole of the mechanic
    and says nothing about a number: a permanent is prepared or it is not, and
    preparing an already-prepared one changes nothing.
    """
    for oid in resolve_pool(ctx, spec.get("objects")):
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        obj.prepared = True
    ctx.state.bump_chars()


@register("exile_and_return")
def op_exile_and_return(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Exile it, then return it to the battlefield **transformed** under its
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
    pool = [oid for oid in resolve_pool(ctx, selector) if not sacrifice_forbidden(ctx.state, oid)]
    # Tamiyo, Collector of Tales: "Spells and abilities your opponents control
    # can't cause you to ... sacrifice permanents." Narrowed out of the pool for
    # the reason above -- the rest of an edict still reaches everybody else.
    pool = [
        oid
        for oid in pool
        if not forced_discard_or_sacrifice_barred(
            ctx.state, ctx.state.objects[oid].controller, ctx.controller
        )
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
    arrived: list[int] = []
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        controller = ctx.controller if spec.get("controller") == "you" else obj.owner
        obj.controller = controller
        # "If this artifact **would enter**, you may discard a land card
        # instead." Mox Diamond, reanimated or blinked rather than cast -- the
        # printed clause is about any arrival from any zone, so the offer has to
        # be made here and not only on the cast line. See
        # `zones.offer_enters_replacement`; `move_object` treats an unasked
        # arrival as unpaid, so this is what buys the permanent its entry.
        yield from offer_enters_replacement(ctx.state, oid, controller)
        # And riot, on the generic cheat-into-play route: "nontoken creatures
        # you control have riot" is about any arrival, not only a cast one --
        # see `zones.offer_riot_choice`.
        yield from offer_riot_choice(ctx.state, oid, controller)
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
        if not obj.on_battlefield:
            # The arrival was replaced -- Mox Diamond whose controller declined
            # the discard, and the card is in a graveyard rather than on the
            # battlefield. Everything below is about a permanent that is there:
            # counters would land on a graveyard card and the combat rider would
            # put a non-permanent into `combat.attackers`.
            continue
        # Placed immediately after the move rather than as an enters-with
        # replacement -- the same trade `op_return_from_graveyard` documents,
        # observable only by another trigger ordered between the two.
        for kind, amount in counters.items():
            add_counters(ctx.state, oid, str(kind), int(amount), source=ctx.source_oid)
        if attacking is not None and ctx.state.combat is not None:
            ctx.state.combat.attackers[oid] = attacking
            _offer_blocks_to(ctx, attacking)
            arrived.append(oid)
    # "…attacking that player or a planeswalker they control" -- asked once
    # every permanent has arrived, so no question interrupts the batch.
    yield from _aim_at_planeswalker(ctx, spec, arrived, attacking)


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
    See `_attacking_player`. ``or_planeswalker`` widens it to "…that player or a
    planeswalker they control", the token's controller choosing as it arrives;
    see `_aim_at_planeswalker`.

    ``attached_to`` is "create a Wicked Role token **attached to it**" (Not Dead
    After All): a selector naming the permanent the Aura token is created
    attached to. It is not `create_token` then `attach`, because the two differ
    exactly when the host is gone. The Role rulings say a Role token that would
    be created attached to a permanent no longer on the battlefield **is not
    created** -- whereas a created-then-attached token would arrive unattached,
    be put into the graveyard by 704.5m, and fire its own "when this is put into
    a graveyard" on the way out. So the host is resolved first and, with none on
    the battlefield, nothing is made.

    ``power`` and ``toughness`` are "create an **X/X** blue Shark creature
    token" (Shark Typhoon): value expressions, evaluated once as the op runs,
    that become the token's base size -- the copiable values its creating
    effect sets (111.4, 707.2), handed to `primitives.create_token` as the
    ``overrides`` eternalize's 4/4 already travels in. So counters and anthems
    land on top of the X/X exactly as on a printed one, the number does not
    move when what it was read from does, and a copy of the token is X/X too.
    Only an X/X token (`variable_pt`) takes the pair, and it always does; the
    loader holds both halves.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    token = str(spec["token"])
    size: dict[str, int] | None = None
    if "power" in spec:
        size = {
            "power": max(0, evaluate_value(ctx, spec["power"])),
            "toughness": max(0, evaluate_value(ctx, spec["toughness"])),
        }
    host: int | None = None
    if "attached_to" in spec:
        hosts = yield from choose_objects(ctx, spec["attached_to"], "Create it attached to")
        host = next((oid for oid in hosts if ctx.state.objects[oid].on_battlefield), None)
        if host is None:
            return
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
                overrides=dict(size) if size else None,
                source=ctx.source_oid,
            )
        )
    if host is not None:
        # In creation order, so a doubled Role's second token is the newer one
        # and the Role rule keeps it.
        for oid in made:
            if ctx.state.card(oid).is_aura:
                attach(ctx.state, oid, host)
    if made and attacking is not None:
        _offer_blocks_to(ctx, attacking)
    yield from _aim_at_planeswalker(ctx, spec, made, attacking)
    if name := spec.get("as"):
        # Written after the op, unlike `sacrifice`'s, which is written before:
        # that one records a *choice* the player made and this one records
        # objects that did not exist until the op ran.
        ctx.bindings[str(name)] = made


@register("copy_permanent")
def op_copy_permanent(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Create a token that's a copy of target creature."

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

    Both ops record what they made on the ability's source (`created_tokens`),
    which the `created_with` selector key reads: Faerie Artisans' "exile all
    other tokens created with this creature", with ``as`` plus
    `exclude_binding` sparing the copy this resolution just made.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    selector = spec.get("objects") or {}
    oids = resolve_pool(ctx, selector)
    if (
        not oids
        and isinstance(selector, Mapping)
        and selector.get("self_only")
        and "zone" not in selector
        and ctx.source_oid in ctx.state.objects
    ):
        # 608.2h: "create two tokens that are copies of Jace" from a -5 that
        # spent his last loyalty. He is in the graveyard by the time it
        # resolves (704.5i), and a battlefield-only pool finds nothing -- but
        # the copy uses his last known information, which is what he was.
        oids = [ctx.source_oid]
    if not oids:
        return
    controllers = _players(ctx, spec.get("controller", "you"))
    exception = spec.get("except_") or spec.get("except")
    attacking = _attacking_player(ctx, spec, _attack_target)
    made: list[int] = []
    for oid in oids:
        source = ctx.state.objects.get(oid)
        if source is None:
            continue
        # 707.2: a token's copiable values are the ones the effect that created
        # it set -- an X/X Shark's size, an eternalized token's 4/4 -- so they
        # come along, and this copy's own exception goes on top (707.9b).
        overrides = {**(source.copy_overrides or {}), **(exception or {})}
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
                    source=ctx.source_oid,
                )
            )
    if made and attacking is not None:
        _offer_blocks_to(ctx, attacking)
    yield from _aim_at_planeswalker(ctx, spec, made, attacking)
    if name := spec.get("as"):
        ctx.bindings[str(name)] = made
