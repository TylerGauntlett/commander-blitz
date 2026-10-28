"""Effect ops on counters, tapping, attachment and transformation."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from ..characteristics import chars
from ..effects.ops_stack import put_copy_on_stack
from ..enums import Zone
from ..errors import DslError
from ..player_statics import player_cant_cast_while_resolving
from ..primitives import (
    add_counters,
    add_subtypes,
    attach,
    change_control,
    create_token,
    remove_counters,
    tap_permanent,
    transform,
    untap_permanent,
)
from ..structs import StackItem
from ..zones import exile, move_object
from .board_helpers import (
    _players,
)
from .context import EffectContext, ask_yes_no
from .registry import register
from .selectors import (
    choose_objects,
    pick_from_pool,
    resolve_pool,
)
from .values import evaluate_value


@register("add_counters")
def op_add_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    # Rule 107.1b: a calculation that comes out negative uses zero. "Put
    # counters equal to its power" with a -1/-1 creature puts none -- Station's
    # release notes say so outright -- where the primitive, handed -1, would
    # *remove* one, because a negative `add_counter` is how removal is spelled
    # underneath.
    amount = max(0, evaluate_value(ctx, spec.get("amount", 1)))
    kind = str(spec.get("counter", "+1/+1"))
    oids = yield from choose_objects(ctx, spec.get("objects"), "Put counters on")
    for oid in oids:
        add_counters(ctx.state, oid, kind, amount, source=ctx.source_oid)


#: The token "empower Jace" creates when you control no Jace token: the blue
#: Jace planeswalker with "[-1]: Surveil 1" and "[-3]: Draw a card." and no
#: printed loyalty (the catalog's tfra token row prints 0).
EMPOWER_TOKEN = "jace_planeswalker_u"

#: "A Jace token you control" -- read off the characteristics, so it is any
#: token with the Jace subtype, not only the one `EMPOWER_TOKEN` names.
_JACE_TOKENS = {"zone": "battlefield", "controller": "you", "subtypes": ["Jace"], "is_token": True}


@register("empower")
def op_empower(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Empower Jace N." -- Reality Fracture's keyword action, whose reminder
    text is the whole rule: *(Put N loyalty counters on a Jace token you
    control. If you don't control one, first create a blue Jace planeswalker
    token with "[-1]: Surveil 1" and "[-3]: Draw a card.")*

    Two primitives in one op, because the order is the card. The token is
    created only when you control no Jace token, and the counters go on **one**
    Jace token, chosen by the empowering player when there is more than one --
    so a doubled creation (Parallel Lives) still empowers one Jace, and the
    other, at zero loyalty, is binned by 704.5i once the effect is done. Both
    halves happen inside the same effect, so the new token is never looked at by
    a state-based action before its counters arrive.

    Not `create_token` then `add_counters`: that pair creates a second Jace
    beside the one you already control, and with no condition between them it
    cannot say "if you don't control one". X below zero is zero (107.1b), and
    zero creates the token and puts nothing on it, which the zero-loyalty
    state-based action then puts into the graveyard -- the printed outcome.
    """
    amount = max(0, evaluate_value(ctx, spec.get("amount", 1)))
    pool = resolve_pool(ctx, _JACE_TOKENS)
    if not pool:
        create_token(ctx.state, EMPOWER_TOKEN, ctx.controller, source=ctx.source_oid)
        pool = resolve_pool(ctx, _JACE_TOKENS)
    # The plain "choose" purpose, as `add_counters` asks: one permanent off the
    # board, which the client's existing board picker already answers.
    picked = yield from pick_from_pool(ctx, pool, {"count": 1}, "Empower which Jace?")
    for oid in picked:
        add_counters(ctx.state, oid, "loyalty", amount, source=ctx.source_oid)


#: The token "amass [subtype] N" creates when you control no Army creature,
#: one per subtype a printed card amasses: the catalog's 0/0 black
#: "[subtype] Army" token rows (tfrc, tltr, thob, tcmm). The keys are the
#: values the op's ``subtype`` takes, and the loader refuses any other.
AMASS_TOKENS = {
    "Zombie": "zombie_army_0_0_b",
    "Orc": "orc_army_0_0_b",
    "Goblin": "goblin_army_0_0_b",
    "Sliver": "sliver_army_0_0_b",
}

#: "An Army creature you control" -- read off the characteristics, so any
#: creature with the Army subtype counts, token or not.
_ARMY_CREATURES = {
    "zone": "battlefield",
    "controller": "you",
    "types": ["Creature"],
    "subtypes": ["Army"],
}


@register("amass")
def op_amass(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Amass [subtype] N." -- rule 701.47a: *If you don't control an Army
    creature, create a 0/0 black [subtype] Army creature token. Choose an Army
    creature you control. Put N +1/+1 counters on that creature. If it isn't a
    [subtype], it becomes a [subtype] in addition to its other types.*

    `empower`'s shape with a creature: the token is created only when you
    control no Army creature, the counters go on **one** Army, chosen by the
    amassing player when there is more than one (a doubled creation leaves the
    other at 0/0 for 704.5f), and both halves happen inside the same effect so
    the new 0/0 is never looked at by a state-based action before its counters
    land ("amass 0" still creates it, and it then dies).

    The subtype is a parameter because the printed word changes: Zombie (War
    of the Spark, whose "amass N" Oracle now reads "amass Zombies N"), Orc,
    Goblin, Sliver. It picks the token and is the type the chosen Army gains,
    written onto the object for as long as it stays on the battlefield --
    an Orc Army that later amasses Zombies is an Orc Zombie Army.

    ``as`` records the amassed Army ("the amassed Army's power"),
    a list of zero or one oids.
    """
    subtype = str(spec["subtype"])
    amount = max(0, evaluate_value(ctx, spec.get("amount", 1)))
    pool = resolve_pool(ctx, _ARMY_CREATURES)
    if not pool:
        create_token(ctx.state, AMASS_TOKENS[subtype], ctx.controller, source=ctx.source_oid)
        pool = resolve_pool(ctx, _ARMY_CREATURES)
    picked = yield from pick_from_pool(ctx, pool, {"count": 1}, "Amass onto which Army?")
    for oid in picked:
        add_counters(ctx.state, oid, "+1/+1", amount, source=ctx.source_oid)
        if subtype not in chars(ctx.state, oid).subtypes:
            add_subtypes(ctx.state, oid, [subtype], source=ctx.source_oid)
    if name := spec.get("as"):
        ctx.bindings[str(name)] = list(picked)


#: The token "incubate N" creates: the catalog's double-faced Incubator //
#: Phyrexian token row (tfrc). The front is a colorless Incubator artifact with
#: "{2}: Transform this artifact."; its `back_face` is the 0/0 colorless
#: Phyrexian artifact creature it transforms into.
INCUBATOR_TOKEN = "incubator_token"


@register("incubate")
def op_incubate(ctx: EffectContext, spec: Mapping[str, Any]) -> None:
    """ "Incubate N." -- rule 701.53a: *Create an Incubator token with N +1/+1
    counters on it and "{2}: Transform this artifact." It transforms into a 0/0
    Phyrexian artifact creature.*

    The counters are on the token as it is created (`create_token`'s
    ``enters_with``), so they are one placement with every other "enters with"
    (122.6), and the counter replacements look at the Incubator as it is:
    an artifact, not a creature. Doubling Season ("a permanent you control")
    makes incubate 3 two Incubators with six each; Hardened Scales ("a
    creature you control") does nothing to it. Not `create_token` then
    `add_counters`, which places them on a token already on the battlefield --
    a second event that "whenever a token enters" sees without them, and that
    an `add_counters` on "the token" would have to name by binding.

    The token is a transforming double-faced token, so turning it over is the
    ordinary `transform` op on its own activated ability; the counters stay on
    the permanent, and the back face is a 0/0 that is N/N with them. Incubate
    0 still creates the Incubator (an artifact, not a creature, so nothing
    dies), and transforming it then makes a 0/0 that 704.5f bins.

    ``amount`` is any value expression, below zero read as zero (107.1b):
    Sunfall's "the number of creatures exiled this way" is
    ``{"count": {"binding": ...}}`` over the `exile` op's ``as``. ``as``
    records the Incubators made.
    """
    amount = max(0, evaluate_value(ctx, spec.get("amount", 1)))
    made = create_token(
        ctx.state,
        INCUBATOR_TOKEN,
        ctx.controller,
        source=ctx.source_oid,
        enters_with={"+1/+1": amount} if amount else None,
    )
    if name := spec.get("as"):
        ctx.bindings[str(name)] = list(made)


@register("distribute_counters")
def op_distribute_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Distribute three +1/+1 counters among up to three target creatures."
    -- Ajani, Sleeper Agent.

    The division was announced as the ability was activated (601.2d, 602.2b)
    and travels on the stack item as ``bindings["distribution"]``: one
    ``[oid, n]`` pair per declared target, each ``n`` at least one --
    `game.Game._ask_distribution` asked it. Here each target that is still
    legal gets its share; a target that became illegal takes its share with it
    (608.2b), and the rest are **not** redistributed -- asking again now would
    let the split follow whatever happened in response, a strictly better card.
    """
    kind = str(spec.get("counter", "+1/+1"))
    target_id = str((spec.get("objects") or {}).get("target"))
    legal = set(ctx.target_oids(target_id))
    division = (ctx.bindings.get("distribution") or {}).get(target_id)
    if division is None:
        # The loader keeps this op to activated abilities, whose activation
        # always announces the division; with no announcement there is no
        # division to honour, and inventing one would be a different card.
        raise DslError(
            f"distribute_counters for {target_id!r} resolved without an announced division"
        )
    for oid, share in division:
        if int(oid) in legal and int(share) > 0:
            add_counters(ctx.state, int(oid), kind, int(share), source=ctx.source_oid)
    yield from ()


@register("double_counters")
def op_double_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Double the number of each kind of counter on any number of target
    permanents." -- Deepglow Skate.

    122.1 lets a permanent carry any number of kinds, and the card names none,
    so the kinds are read off each permanent at resolution: for every kind
    already there, put that many more on. That is a *placement* -- Deepglow's
    ruling says so, and it is why this goes through `add_counters` rather than
    writing the dict: a Doubling Season sees an effect putting N counters and
    doubles that, so 2 becomes 6, and "whenever a counter is put on" triggers.

    Snapshotted per permanent before any placement, so a replacement that adds
    a kind (none printed yet) cannot be doubled in the same pass, and a kind
    with zero counters is nothing to double. Not `proliferate`, which adds one
    of each kind, and not `move_counters`, which takes from somewhere else.
    """
    oids = yield from choose_objects(ctx, spec.get("objects"), "Double the counters on")
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None or not obj.on_battlefield:
            continue
        for kind, amount in list(obj.counters.items()):
            if amount > 0:
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
    """ "Exile them, then meld them into <name>." Bruna and Gisela (701.37).

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
    #
    # Synthesised rather than the pool entry itself, for one field: a melded
    # permanent's mana value is the total of its front faces' (Brisela's is
    # 11), and the melded card prints no mana cost to carry it.
    partner_card = state.registry.get(state.objects[partner].def_id)
    melded.merged_card = dataclasses.replace(
        state.registry.get(card.melds_into),
        melded_mana_value=card.mana_value + partner_card.mana_value,
    )
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
    """ "Transform this creature." Bloodline Keeper.

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
    """ "Gain control of target creature." Captivating Vampire, Act of Treason.

    ``player`` says who gains it and defaults to the ability's controller, which
    is what every "*you* gain control" line means; the spec exists because "target
    opponent gains control of" is the same effect pointed elsewhere.

    ``duration`` is ``"permanent"`` or ``"until_end_of_turn"``.  The default is
    ``"permanent"`` because that is what every card written before this meant,
    not because it is the safer reading -- it is the *stronger* one, and it is
    the loader rather than this default that keeps a misspelling from silently
    becoming it.  The two are different cards and not degrees of one, which is
    why neither is ever inferred from the rest of the effect.  See
    :func:`commanderblitz.engine.primitives.change_control` for the handback.

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
        if change_control(ctx.state, oid, players[0], source=ctx.source_oid, duration=duration)
    ]
    if name := spec.get("as"):
        ctx.bindings[str(name)] = taken


@register("exchange_control")
def op_exchange_control(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Exchange control of target artifact or creature you control and target
    creature an opponent controls with power 3 or less." Oko, Thief of Crowns.

    701.12a: each permanent's controller gains control of the other one, and it
    lasts indefinitely. Two `gain_control` ops cannot say it. The second one
    would need "the player who controlled the first target" as its player, and
    no player spec names that. It would also run alone when the other target had
    gone, and 701.12b forbids that: "if the entire exchange can't be completed,
    no part of the exchange occurs." So this is one op over two selectors,
    ``first`` and ``second``.

    Nothing happens unless each selector comes to exactly one permanent still on
    the battlefield, and the two are under different controllers. Targets that
    became illegal were already dropped on resolution (608.2b), so a missing
    target is an empty pool here. Two permanents under one controller are 701.12b
    too, because the exchange would change nothing.

    Both control changes go through `change_control`, so each permanent is
    summoning sick for its new controller (302.6), leaves combat (506.4) and
    announces itself.
    """
    firsts = yield from choose_objects(ctx, spec.get("first"), "Exchange control of")
    seconds = yield from choose_objects(ctx, spec.get("second"), "Exchange control with")
    if len(firsts) != 1 or len(seconds) != 1 or firsts[0] == seconds[0]:
        return
    a = ctx.state.objects.get(firsts[0])
    b = ctx.state.objects.get(seconds[0])
    if a is None or b is None or not a.on_battlefield or not b.on_battlefield:
        return
    if a.controller == b.controller:
        return
    a_controller, b_controller = a.controller, b.controller
    change_control(ctx.state, a.oid, b_controller, source=ctx.source_oid)
    change_control(ctx.state, b.oid, a_controller, source=ctx.source_oid)


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
    ctx.state.emit("aura_swap", player=ctx.controller, source=ctx.source_oid, oid=incoming)


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
    picked = yield from pick_from_pool(ctx, pool, {**selector, "count": 1}, "Pair with", "pair")
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
    ctx.state.emit("encoded", player=source.controller, source=ctx.source_oid, oid=oids[0])


@register("cast_copy")
def op_cast_copy(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "…may cast a copy of the encoded card without paying its mana cost."

    A copy of *this ability's own card*, which is what separates it from
    `copy_spell`: that op copies something on the stack, and the encoded card is
    in exile with nothing on the stack to point at. Built through the same
    `put_copy_on_stack`, so a cipher copy is a token and announces its targets
    exactly as a storm copy does.

    The original stays where it is -- it is copied, not cast -- which is the
    whole of why cipher keeps paying, and the same reason Mizzix's Mastery and
    Arcane Bombardment accumulate rather than spend their exiles.

    ``objects`` names **which** cards to copy, and defaults to this ability's
    own card, which is cipher. Mizzix's Mastery copies a card it has just exiled
    from a graveyard; Arcane Bombardment copies "each card exiled with this
    enchantment", a pile that grows every turn. `copy_spell` cannot serve
    either: it copies something on the *stack*, and these cards are in exile
    with nothing on the stack to point at.

    ``optional`` is the printed "you **may** cast the copy", asked once per
    card. Cipher does not set it -- its own "may" is the reflexive trigger that
    got here -- so nothing gained a prompt.
    """

    if "objects" in spec:
        oids = resolve_pool(ctx, spec["objects"])
    else:
        oids = [ctx.source_oid] if ctx.source_oid is not None else []
    optional = bool(spec.get("optional"))
    if player_cant_cast_while_resolving(ctx.state, ctx.controller):
        # 707.12: casting a copy of a card *is* casting a spell, even though
        # this engine builds it as a copy -- so Voice of Victory stops it, where
        # `copy_spell` (a copy that was never cast, 707.10) is untouched.
        return
    for oid in oids:
        obj = ctx.state.objects.get(oid)
        if obj is None:
            continue
        name = ctx.state.card_of(obj).name
        if player_cant_cast_while_resolving(ctx.state, ctx.controller, ctx.state.card_of(obj)):
            # A filtered lock (Narset Transcendent's emblem) stops this copy
            # alone; the total one was answered above.
            continue
        if optional and not (
            yield from ask_yes_no(
                ctx,
                f"Cast a copy of {name} without paying its mana cost?",
                ctx.controller,
            )
        ):
            continue
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
    ctx.state.emit("haunt", player=source.controller, source=ctx.source_oid, oid=oids[0])


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
