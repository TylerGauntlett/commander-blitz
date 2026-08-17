"""Effect ops that act on permanents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import Zone
from ..errors import DslError
from ..objects import PLUS_ONE
from ..primitives import (
    add_counters,
    add_subtypes,
    animate,
    attach,
    change_control,
    create_token,
    grant_ability,
    grant_keyword,
    lock_abilities,
    pump,
    remove_counters,
    tap_permanent,
    transform,
    untap_permanent,
)
from ..structs import TempEffect
from ..zones import destroy, exile, move_object, sacrifice
from . import register
from .context import EffectContext
from .selectors import choose_objects, pick_from_pool, resolve_pool
from .values import evaluate_value


@register("destroy")
def op_destroy(ctx: EffectContext, spec: Mapping[str, Any]):
    oids = yield from choose_objects(ctx, spec.get("objects"), "Destroy", "destroy")
    for oid in oids:
        # `by` is what makes the log and the exit animation able to say
        # "Destroyed by Vandalblast" rather than just "Destroyed".
        destroy(ctx.state, oid, by=ctx.source_oid)


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
    """
    link = bool(spec.get("until_leaves"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Exile", "destroy")
    for oid in oids:
        exile(ctx.state, oid, by=ctx.source_oid)
        if link and ctx.source_oid is not None:
            # After the move: `move_object` runs `reset_permanent_state` on the
            # way, which would wipe this if it were set first.
            obj = ctx.state.objects.get(oid)
            if obj is not None:
                obj.exiled_by = ctx.source_oid


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
    """
    selector = dict(spec.get("objects") or {})
    selector.setdefault("controller", "you")
    oids = yield from choose_objects(ctx, selector, "Sacrifice", "sacrifice")
    if name := spec.get("as"):
        # Written before the sacrifice, so the binding is a record of the choice
        # rather than of what survived it.
        ctx.bindings[str(name)] = list(oids)
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
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put onto the battlefield")
    tapped = bool(spec.get("tapped"))
    attacking = _attack_defender(ctx) if spec.get("attacking") else None
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
        if attacking is not None and ctx.state.combat is not None:
            ctx.state.combat.attackers[oid] = attacking


@register("create_token")
def op_create_token(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    token = str(spec["token"])
    attacking = _attack_target(ctx) if spec.get("attacking") else None
    for pid in _players(ctx, spec.get("controller", "you")):
        create_token(
            ctx.state,
            token,
            pid,
            amount,
            tapped=bool(spec.get("tapped")),
            attacking=attacking,
        )


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
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    oids = resolve_pool(ctx, spec.get("objects"))
    if not oids:
        return
    controllers = _players(ctx, spec.get("controller", "you"))
    overrides = spec.get("except_") or spec.get("except")
    for oid in oids:
        source = ctx.state.objects.get(oid)
        if source is None:
            continue
        for pid in controllers:
            create_token(
                ctx.state,
                source.def_id,
                pid,
                amount,
                tapped=bool(spec.get("tapped")),
                attacking=_attack_target(ctx) if spec.get("attacking") else None,
                overrides=dict(overrides) if overrides else None,
            )


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
    oids = yield from choose_objects(ctx, spec.get("objects"), "Attach to")
    aura = ctx.source_oid
    if aura is not None:
        for oid in oids[:1]:
            attach(ctx.state, aura, oid)


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
    """"Gain control of target creature." Captivating Vampire.

    ``player`` says who gains it and defaults to the ability's controller, which
    is what every "*you* gain control" line means; the spec exists because "target
    opponent gains control of" is the same effect pointed elsewhere.

    Permanent only -- see :func:`automtg.engine.primitives.change_control` for
    why there is no until-end-of-turn form and why the loader refuses to let a
    card ask for one silently.
    """
    players = _players(ctx, spec.get("player", "you"))
    if not players:
        return
    oids = yield from choose_objects(ctx, spec.get("objects"), "Gain control of")
    for oid in oids:
        change_control(ctx.state, oid, players[0], source=ctx.source_oid)


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
    """
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
            obj.revealed_to.add(pid)
            ctx.state.bump_chars()
            ctx.state.emit("manifested", player=pid, source=oid)


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
    qualities = [
        *(spec.get("from_colors") or ()),
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
