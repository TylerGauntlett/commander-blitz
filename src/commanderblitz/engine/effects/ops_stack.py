"""Effect ops that act on the stack."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..characteristics import (
    _battlefield_statics,
    _matches_printed,
    resolve_chosen_colors,
    resolve_chosen_subtypes,
)
from ..enums import Zone
from ..events import EventType
from ..stack import StackItem, ability_of, announce_targets
from ..state import new_object
from ..structs import TriggerInstance
from ..targeting import describe_ref, enumerate_target_tuples
from ..triggers import fire
from ..zones import move_object
from .context import EffectContext, ask_mode
from .registry import register
from .selectors import select_players
from .values import evaluate_value


def _spell_named_by(ctx: EffectContext, spec: Mapping[str, Any]):
    """The spell on the stack a spec is talking about, or None.

    Three spellings, because three kinds of card ask the question. ``sid`` is a
    value expression; ``target`` is "**target** instant or sorcery spell"
    (Expansion, Kitsa, Mizzix's Mastery, and Fork before all of them); and with
    neither, the spell that fired the trigger -- the `sid` a `spell_cast`
    trigger already carries in its bindings, which is storm, replicate,
    conspire, casualty and demonstrate.

    Extracted rather than written twice. `copy_spell` reads a declared target
    through `ctx.target_sids` exactly the way `counter` reads its own, on the
    stated grounds that they are the same question about the same kind of
    object and a second spelling would be a second bug -- and `grant_rebound`
    asking it a third time is where that stops being hypothetical.

    Returns None for a `sid` that names nothing and for a stack item that is an
    ability rather than a spell, so every caller can treat "no spell here" as
    one case.
    """

    if "sid" in spec:
        sid = evaluate_value(ctx, spec["sid"])
    elif "target" in spec:
        sids = ctx.target_sids(str(spec["target"]))
        sid = sids[0] if sids else None
    else:
        sid = ctx.bindings.get("sid")
    item = ctx.state.stack_item(int(sid)) if isinstance(sid, int) else None
    if item is None or not item.is_spell:
        return None
    return item


@register("copy_spell")
def op_copy_spell(ctx: EffectContext, spec: Mapping[str, Any]):
    """Copy a spell on the stack (rule 706.10).

    Storm, replicate, conspire, casualty and gravestorm are one capability, and
    this is it. Every one of them says "copy this spell" and differs only in how
    many times and what it costs.

    **A copy is not a card.** Rule 706.10 puts a copy on the stack without it
    being cast and without it existing anywhere else, so the copy is backed by a
    *token* object. That is not a trick: it is what makes the copy disappear
    correctly. An instant's copy resolves, goes to a graveyard, and the
    token state-based action removes it -- so the original card is still the
    only one that ends up in the graveyard, which is what the printed rules say
    and what a naive second `GameObject` would get wrong.

    ``sid`` names the spell, as a value expression. Storm and replicate copy
    *themselves*, so it defaults to the spell this ability belongs to -- the
    `sid` a `spell_cast` trigger already carries in its bindings.

    ``amount`` is how many copies. Storm's is a count of the turn's spells,
    which is why it is a value expression and not an integer.

    The copies go on top of the stack, so they resolve **before** the original:
    706.10 again, and it is the whole reason a storm copy can be countered
    separately from the spell that made it.

    ``new_targets`` is "you may choose new targets for the copy" (Jin-Gitaxias,
    Progress Tyrant), and it is **opt-in** for the reason this was left out
    until a card needed it: the choice is a decision *per copy*, and a storm
    count of nine would ask nine times. Storm, replicate, conspire, casualty,
    gravestorm and epic do not set it, so none of them gained a prompt -- the
    objection was to asking unconditionally, not to the capability.

    The question is only put when there is something to decide: a spell with no
    targets, or one whose targets cannot legally be moved, is not asked.

    ``controller`` is a **player spec** naming whose copy it is, and it is
    **demonstrate**: "choose an opponent to also copy it." Every copy this op
    could make used to be the resolving player's, because the controller was
    the one argument `put_copy_on_stack` was never given -- so the half of
    demonstrate that balances it was unsayable, and a card written with
    ``"controller"`` on it loaded clean and handed the copy to the wrong seat.
    It reads plurally, exactly as `copy_permanent`'s does: one copy per named
    player, per ``amount``. `choose_player` is what narrows it to the one
    opponent demonstrate means, via ``{"binding": …}``.

    Each copy's *own* controller answers ``new_targets`` for it -- 706.10 says
    "players may choose new targets for **their** copies", and asking the
    resolving player about a copy that is not theirs would be a different card
    in both directions: it would let you point an opponent's copy and would
    stop them pointing it themselves.
    """

    state = ctx.state
    original = _spell_named_by(ctx, spec)
    if original is None:
        return
    times = evaluate_value(ctx, spec.get("amount", 1)) if "amount" in spec else 1
    if "controller" in spec:
        # A named seat that has already lost the game is not handed a copy, and
        # an unfilled binding names nobody -- which is how "choose an opponent"
        # makes no second copy at a table where there is no opponent left to
        # choose, rather than falling back to the resolving player's own.
        controllers = [
            pid for pid in select_players(ctx, spec["controller"]) if state.is_alive(pid)
        ]
    else:
        controllers = [ctx.controller]
    for _ in range(max(0, times)):
        for pid in controllers:
            chosen = None
            if spec.get("new_targets"):
                chosen = yield from _choose_new_targets(ctx, original, pid)
            put_copy_on_stack(state, pid, original, chosen)


def _choose_new_targets(ctx: EffectContext, original, chooser: int | None = None):
    """ "You may choose new targets for the copy" (706.10, via 115.7b).

    Offered as one pick from every legal target tuple, which is exactly the set
    the caster chose from -- so "change any number of them" and "each new target
    must be legal" both fall out rather than being enforced separately, and the
    original tuple is on the list as the "change nothing" answer.

    No new `DecisionKind`: `ask_mode` already asks "pick one of these labels"
    and hands back an index, which is this question. The same argument
    `choose_type` makes.

    Returns ``None`` when there was nothing to ask -- no target specs, or only
    one legal tuple -- and the copy then keeps what the original had.

    ``chooser`` is the **copy's** controller, not the resolving player's: a
    demonstrate copy belongs to the chosen opponent, and 706.10's "their
    copies" is that word. It decides the legal set as well as the seat asked,
    because "target creature you control" means a different pool for each of
    them -- so an opponent's copy is offered the targets an opponent could have
    chosen, which is what stops a redirected copy being pointed somewhere its
    own controller never could.
    """

    if chooser is None:
        chooser = ctx.controller
    card = ctx.state.registry.get(original.def_id)
    specs = getattr(card, "targets", ()) or ()
    if original.gift_to is not None:
        # The copy keeps the promise (707.10), so it re-chooses among the
        # promised specs -- the list its stored refs were declared under.
        specs = card.targets_for(gift_promised=True)
    if not specs:
        return None
    options = enumerate_target_tuples(
        ctx.state,
        chooser,
        specs,
        original.oid,
        exclude_sid=original.sid,
    )
    current = tuple(original.targets)
    if current not in options:
        # "You **may** choose new targets", and declining stays on the table
        # even when what the copy holds is no longer legal for its controller
        # -- a copy nobody retargets is simply countered on resolution
        # (608.2b), and for a spell the copy's controller does not *want*, that
        # is the answer they would give.
        #
        # Unreachable until a copy could belong to somebody else. It is the
        # ordinary case for demonstrate: "target creature you control" names
        # the copy's controller's creatures, so the tuple the original chose is
        # usually not among the ones offered to them, and without this the
        # option list would not contain "leave it".
        options = [*options, current]
    # One option means the only legal choice is what it already targets, so
    # there is no question -- and asking anyway would be a prompt that cannot
    # change anything, which is the cost this whole feature was held back over.
    if len(options) <= 1:
        return None
    labels = [
        ", ".join(describe_ref(ctx.state, ref) for ref in tup) or "no targets" for tup in options
    ]
    picked = yield from ask_mode(ctx, f"New targets for {card.name} (copy)?", labels, chooser)
    if not picked:
        return None
    return options[picked[0]]


def put_copy_on_stack(state, controller: int, original, targets=None):
    """Rule 706.10 -- one copy of a spell, on top of the stack.

    Split out of :func:`op_copy_spell` for **epic**, which makes a copy each
    upkeep from the turn structure rather than from an effect. The two must not
    drift: a copy is a token object (which is what makes it vanish correctly),
    it keeps the original's targets, and it announces them so ward and heroic
    see it -- and none of that is obvious enough to write twice.
    """

    card = state.registry.get(original.def_id)
    obj = new_object(
        state,
        original.def_id,
        owner=controller,
        zone=Zone.STACK,
        controller=controller,
        is_token=True,
    )
    copy = StackItem(
        sid=state.alloc_sid(),
        kind="spell",
        controller=controller,
        def_id=original.def_id,
        oid=obj.oid,
        # `targets` overrides only when "you may choose new targets" was taken
        # and the player actually chose. `None` is not "no targets": it is "the
        # copy keeps the original's", which is 706.10's default and what storm,
        # replicate, conspire and epic all rely on.
        targets=original.targets if targets is None else tuple(targets),
        x=original.x,
        modes=original.modes,
        kicked=original.kicked,
        # 707.10: a copy copies "additional or alternative costs" paid for the
        # original. A copied Baleful Mastery cast for {1}{B} still hands an
        # opponent a card; without this the copy was the rider-free half.
        evoked=original.evoked,
        # Impending, for the same 707.10 reason: a copy of an Overlord spell
        # cast for its impending cost enters with the time counters too.
        impending=original.impending,
        # And the gift promise, which is a 601.2b choice like the kicker: a
        # copy of a promised spell was promised too, and its refs were
        # declared under the promised target list, so `stack._resolve_spell`
        # has to split them by that list rather than the unpromised one.
        gift_to=original.gift_to,
        bindings=dict(original.bindings),
        description=f"{card.name} (copy)",
    )
    obj.stack_id = copy.sid
    state.stack.append(copy)
    # `fire` rather than `state.emit`: magecraft ("whenever you cast **or copy**
    # an instant or sorcery spell") listens for this, and `emit` only records
    # the event -- it never scans for triggered abilities, so the event was
    # written into the log and heard by nobody. Every other trigger-bearing
    # event in the engine goes through `fire`; this one was emitted before
    # anything could listen and was never moved over.
    fire(
        state,
        EventType.SPELL_COPIED,
        player=controller,
        source=original.oid,
        sid=copy.sid,
        of=original.sid,
        card=original.def_id,
    )
    # A copy targets what the original targeted, and "becomes the target
    # of a spell" does not ask whether that spell was cast -- so ward and
    # heroic see the copy too.
    announce_targets(state, copy)
    return copy


def _paid_with_uncounterable_mana(state, item) -> bool:
    """Was this spell paid for with mana carrying Cavern of Souls' rider?

    Answered off the spell's own object, where `costs.pay_mana` wrote it as the
    cost was paid. It cannot be asked any later: the rider travels on the pip
    (`mana.Pip.uncounterable`) and the pip is gone the instant it is spent.

    An ability on the stack has no such object and needs none -- no printed card
    makes an *ability* uncounterable by paying for it a particular way.
    """
    oid = getattr(item, "oid", None)
    if oid is None:
        return False
    obj = state.objects.get(oid)
    return bool(obj is not None and obj.uncounterable_mana_spent)


def _shielded_by_a_static(state, item) -> bool:
    """Is a `spells_cant_be_countered` static covering this spell?

    Lier, Disciple of the Drowned: "Spells can't be countered." Everyone's,
    including the opponents' -- the card is symmetrical and famously so, which is
    why this asks nothing about who controls the static or the spell unless the
    card's own `affects_spells` filter does.

    The card-level `uncounterable` flag beside this one is a *different claim*:
    it is one card saying it about itself, and could never cover a spell the
    static's controller does not own.
    """

    card = state.registry.get(item.def_id)
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "spells_cant_be_countered":
            continue
        filt = static.get("affects_spells")
        if filt:
            # "Creature spells **you control** can't be countered" -- Rhythm of
            # the Wild. Read here rather than left to `_matches_printed`, which
            # sees a printed card and no caster: the word is about who controls
            # the *spell*, measured against whoever controls the static, exactly
            # as `player_statics.cost_reduction` reads the same key.
            #
            # Absent, it means **any** controller, which is the opposite default
            # to `spell_cost_reduction`'s and is what this effect has always
            # said: Lier's unfiltered line covers the whole table, so a filter
            # that merely narrows the *type* must not quietly narrow the seat
            # too. The card writes the word when it means it.
            who = str(filt.get("controller", "any"))
            if who == "you" and source_obj.controller != item.controller:
                continue
            if who == "opponent" and source_obj.controller == item.controller:
                continue
            resolved = resolve_chosen_colors(
                resolve_chosen_subtypes(filt, source_obj), source_obj
            )
            if not _matches_printed(card, resolved):
                continue
        if source_obj is not None:
            return True
    return False


@register("grant_rebound")
def op_grant_rebound(ctx: EffectContext, spec: Mapping[str, Any]):
    """"It gains rebound." -- Ojer Pakpatiq, Deepest Epoch.

    Rebound itself was never missing. `CardDef.rebound` has had the full
    mechanic behind it for as long as the field has existed: the resolution
    rider in `_place_after_resolution` that exiles the spell instead of binning
    it, `rebound_by` recorded on the exiled card, and `suspend.rebound_tick`
    offering the free cast at its controller's next upkeep. What could not be
    said was somebody else granting it -- the flag is read off the **card**, so
    only a card that prints rebound could ever have it.

    So this op writes the same fact about a spell that does not print it, on
    the spell's object while it is still on the stack, and the rider reads the
    two together. Nothing else is needed and nothing else is added: a granted
    rebound and a printed one are the same rebound, and giving the grant its
    own exile-and-recast path would be a second mechanism for one behaviour.

    **Which spell** comes from `_spell_named_by` -- the trigger's own `sid` by
    default, which is what "whenever you cast an instant spell, **it** gains
    rebound" means, or a declared ``target``.

    The from-hand half of the printed line lives in the trigger's filter, not
    here, and 702.87a's own "if you cast this spell from your hand" is enforced
    by the rider regardless. A grant made to a spell cast from anywhere else is
    therefore inert rather than wrong -- which is also what stops the free cast
    at the next upkeep, itself made from exile, rebounding a second time.
    """
    item = _spell_named_by(ctx, spec)
    if item is None:
        return
    obj = ctx.state.objects.get(item.oid)
    if obj is None:
        return
    obj.granted_rebound = True


@register("grant_plot")
def op_grant_plot(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Exile that spell instead of putting it into your graveyard as it resolves.
    If you do, it becomes plotted." -- Lilah, Undefeated Slickshot.

    The same shape as `grant_rebound` and deliberately so: both are riders on
    where a resolving spell goes, both are written on the spell's object while
    it is still on the stack, and both are read by `_place_after_resolution`.
    Plot differs in what it leaves behind -- rebound owes one free cast at the
    next upkeep, plot leaves a standing permission with no end.

    "If you do" needs no separate expression. The exile and the plotting are one
    rider, so there is no state in which the first happened and the second did
    not -- which is exactly what the printed conditional says.

    Not an `exile` op written into the ability's effects: the stack list is
    already popped by the time those run, so it would reach nothing and the
    printed line would silently do nothing. The same argument `encode` and
    `exiles_itself` both make.
    """
    item = _spell_named_by(ctx, spec)
    if item is None:
        return
    obj = ctx.state.objects.get(item.oid)
    if obj is None:
        return
    obj.granted_plot = True


@register("counter")
def op_counter(ctx: EffectContext, spec: Mapping[str, Any]):
    """Counter target spell.

    A countered spell is removed from the stack and put into its owner's
    graveyard; abilities on the stack simply cease to exist.

    ``sid`` names the victim by value rather than by target, which is what ward
    needs: "counter **it** unless that player pays" is not a targeted ability,
    and the spell it means is the one that just targeted this permanent. The
    `becomes_target` trigger carries that spell's `sid` in its bindings, so
    ``{"sid": {"binding": "sid"}}`` says it without inventing a target the
    printed card does not have -- which would also let the ward creature's
    controller point it somewhere else.
    """
    state = ctx.state
    target_id = str(spec.get("target", "t1"))
    if "sid" in spec:
        sids = [evaluate_value(ctx, spec["sid"])]
    else:
        sids = list(ctx.target_sids(target_id))
    for sid in sids:
        item = state.stack_item(sid)
        if item is None:
            continue
        # "This spell can't be countered." Three sources, and each is a
        # different thing said by a different card at a different moment:
        #
        # * the **printed** rider, read off the definition -- the spell saying it
        #   about itself, needing no static since the spell is on the stack where
        #   statics do not reach it anyway;
        # * a **static** on the battlefield, somebody else saying it about a
        #   class of spell;
        # * the **mana** it was paid with -- Cavern of Souls, Delighted Halfling.
        #   Recorded on the spell's object by `costs.pay_mana` at the instant it
        #   was paid for, because a pip's rider is unrecoverable the moment the
        #   pip is spent.
        #
        # The third cannot be either of the others. As a card-level flag it would
        # make every copy of the card uncounterable however it was cast; as a
        # static it would protect every creature spell of the chosen type on the
        # table, whoever cast it and whatever paid for it.
        if item.is_spell and (
            state.registry.get(item.def_id).uncounterable
            or _paid_with_uncounterable_mana(state, item)
            or _shielded_by_a_static(state, item)
        ):
            state.emit(
                EventType.SPELL_COUNTERED,
                player=item.controller,
                source=ctx.source_oid,
                sid=sid,
                card=item.def_id,
                failed="cannot be countered",
            )
            continue
        state.stack = [it for it in state.stack if it.sid != sid]
        state.emit(
            EventType.SPELL_COUNTERED,
            player=item.controller,
            source=ctx.source_oid,
            sid=sid,
            card=item.def_id,
        )
        if item.is_spell and item.oid is not None:
            obj = state.objects.get(item.oid)
            if obj is not None:
                obj.stack_id = None
                # It has stopped being a spell, so it stops showing the face it
                # was cast as -- and a countered Adventure is a card in the
                # graveyard, since 715.3c exiles it only *as it resolves*.
                obj.showing_second_face = False
                # "If that spell would be put into your graveyard, exile it
                # instead" is a replacement on the spell, not a resolution
                # rider, so a countered one is exiled too (`cast_card`'s
                # ``exiles``).
                destination = Zone.EXILE if item.exiles_instead else Zone.GRAVEYARD
                move_object(state, item.oid, destination, to_player=obj.owner, cause="countered")


@register("reflexive_trigger")
def op_reflexive_trigger(ctx: EffectContext, spec: Mapping[str, Any]):
    """Fire a reflexive triggered ability (603.11) -- "**When you do**, …".

    Espers to Magicite: "Exile each opponent's graveyard. When you do, choose up
    to one target creature card exiled this way. Create a token that's a copy of
    that card…"

    The rest of that sentence is a real ability on the card
    (``kind: "reflexive"``) and this queues it, which is the whole of the op.
    Everything that matters about 603.11 then comes from the pipeline the card's
    other triggers already use: it goes on the stack when a player would next
    receive priority -- so **after** the spell that fired it has finished
    resolving -- it chooses its targets as it is put there (603.3d), and the
    other players get a window to respond before it resolves.

    **Not more effects inline.** Written that way the choice would be made
    mid-resolution and would not be a *target* at all: nothing would be
    announced, nothing could respond, and 608.2b would never re-check it. The
    difference is visible on this very card, whose reflexive half targets a card
    an opponent may still be able to reach.

    **Not `delayed_trigger`.** That watches an `EventType`, and "when you do"
    has none: what it means is "when the instruction immediately above this one
    is carried out", which is a fact about *this* resolution and not about
    anything the board could be watched for. It is also fired unconditionally
    here, because the effect above it did happen -- an exiled-nothing case is
    the reflexive ability's own business, not this op's.

    The bindings are copied at this instant, so "…exiled **this way**" still
    names the cards the earlier op recorded once the ability is on the stack.
    """

    state = ctx.state
    source_oid = ctx.source_oid
    if source_oid is None:
        return
    obj = state.objects.get(source_oid)
    if obj is None:
        return
    card = state.card_of(obj)
    wanted = str(spec.get("ability", ""))
    ability = next((a for a in card.abilities if a.reflex_id and a.reflex_id == wanted), None)
    if ability is None:  # pragma: no cover -- the loader refuses this
        return
    state.pending_triggers.append(
        TriggerInstance(
            source_oid=source_oid,
            ability_index=ability.index,
            controller=ctx.controller,
            bindings=dict(ctx.bindings),
            description=f"{card.name}: {ability.text or wanted}",
            # The same snapshot every other trigger keeps, and it earns its keep
            # here: the source is usually a *spell*, which is in a graveyard by
            # the time this reaches the stack.
            def_id=obj.def_id,
        )
    )
    state.emit(
        EventType.ABILITY_TRIGGERED,
        player=ctx.controller,
        source=source_oid,
        card=card.id,
        ability=ability.index,
        trigger="reflexive",
    )


@register("copy_ability")
def op_copy_ability(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Copy target activated or triggered ability you control. You may choose
    new targets for the copy." -- Peter Parker's Camera, Lithoform Engine,
    Strionic Resonator.

    706.10 for an **ability**, and it is a different op from `copy_spell` rather
    than a flag on it, because the two copy different kinds of object.
    `_spell_named_by` returns None for an ability on purpose, and
    `put_copy_on_stack` builds `kind="spell"` around a `new_object` card token
    with an `oid` -- which an ability StackItem does not have. It is
    `source_oid` + `ability_index` + `granted_by` + `bindings`, and nothing else.
    A `copy_spell` written on this card would load clean and silently do nothing,
    which is why the gap record refused it.

    So the copy is `dataclasses.replace` with a fresh sid: every field of the
    original is kept, which is what 706.10's "copiable values" means here --
    including the ``bindings`` the trigger captured, so a copied "whenever a land
    enters" ability still knows which land, and the ``x`` that was announced.

    The copy goes **on top** of the stack (706.10) and so resolves first, which is
    the whole reason the card is worth playing.

    ``new_targets`` is offered from the **ability's** own specs, not the card's.
    `_choose_new_targets` reads `card.targets` and would hand an ability copy the
    wrong pool -- usually empty, since the card that grants an activated ability
    rarely targets at its own level -- so this asks `ability_of` for the specs the
    ability actually declared.
    """

    refs = ctx.targets.get(str(spec.get("target", "t1")), ())
    sids = [ref.id for ref in refs if getattr(ref, "kind", None) == "stack"]
    for sid in sids:
        original = ctx.state.stack_item(sid)
        if original is None or original.is_spell:
            # Already resolved, or never an ability. 608.2b's fizzle, and the
            # printed behaviour: a Camera activation whose target resolved first
            # does nothing.
            continue
        copy = replace(original, sid=ctx.state.alloc_sid())
        if spec.get("new_targets"):
            ability = ability_of(ctx.state, original)
            specs = getattr(ability, "targets", ()) or ()
            if specs:
                chosen = yield from _choose_new_targets_for(
                    ctx, original, specs, original.controller
                )
                if chosen is not None:
                    copy = replace(copy, targets=tuple(chosen))
        ctx.state.stack.append(copy)
        announce_targets(ctx.state, copy)


def _choose_new_targets_for(ctx: EffectContext, original, specs, chooser: int):
    """`_choose_new_targets`, but for target specs handed in rather than read off
    a card.

    Split out instead of parameterising the original, because the original's whole
    contract is "the specs of the card this spell was cast from" and an ability's
    live somewhere else entirely -- on the `Ability`, reachable only through
    `ability_of`, which has to account for a *granted* ability living in the
    granter's list. One caller each, and the two cannot drift into disagreeing
    about which specs a copy is offered.
    """

    options = enumerate_target_tuples(
        ctx.state,
        chooser,
        specs,
        original.source_oid,
        exclude_sid=original.sid,
        bindings=dict(original.bindings or {}),
        x=original.x,
    )
    if len(options) <= 1:
        return None
    labels = [
        ", ".join(describe_ref(ctx.state, ref) for ref in tuple_) or "no targets"
        for tuple_ in options
    ]
    # `ask_mode` hands back a *list* of chosen indices even for one pick, which is
    # what lets it serve "choose two modes" as well; one pick is a list of one.
    picked = yield from ask_mode(ctx, "Choose new targets for the copy", labels, chooser)
    if not picked:
        return None
    return options[picked[0]]
