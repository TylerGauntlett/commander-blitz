"""Effect ops for life totals and damage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..characteristics import chars
from ..enums import Keyword
from ..errors import DslError
from ..player import PLAYER_COUNTER_KINDS
from ..primitives import (
    add_energy,
    add_poison,
    damage_permanent,
    damage_player,
    gain_life,
    lose_life,
    remove_player_counters,
)
from ..structs import (
    DAMAGE_SHIELD_DURATIONS,
    LIFE_FLOOR_DURATIONS,
    LIFE_LOCK_DURATIONS,
    OUTCOME_LOCK_DURATIONS,
    PERMANENT_SHIELD_DIRECTIONS,
    PERMANENT_SHIELD_DURATIONS,
)
from ..temp_effects import (
    fog_combat_damage,
    lock_game_outcome,
    lock_life_total,
    redirect_damage_to,
    set_life_floor,
    shield_permanent,
    shield_player,
)
from .context import EffectContext
from .registry import register
from .selectors import resolve_pool, select_players
from .values import evaluate_value


@register("gain_life")
def op_gain_life(ctx: EffectContext, spec: Mapping[str, Any]):
    amount = evaluate_value(ctx, spec.get("amount", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        gain_life(ctx.state, pid, amount, source=ctx.source_oid)


@register("lose_life")
def op_lose_life(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Each opponent loses X life. You gain life equal to the life lost this way."

    ``as`` binds **the life actually lost**, summed over every player this one
    op touched, as an int read back with ``{"binding": …}`` (Gray Merchant of
    Asphodel, Malakir Bloodwitch, extort's "that much life"). Actually lost, not
    asked for: `primitives.lose_life` returns the loss after replacements, so a
    Bloodletter-doubled drain gains the doubled amount and a locked life total
    gains nothing. Recomputing
    ``amount`` in the gain would agree with the printed card only while nothing
    replaces the loss, which is exactly when nobody checks.

    The binding is written by this op alone and overwrites any earlier value of
    the same name: "the life lost *this way*" is this sentence's loss.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    total = 0
    for pid in select_players(ctx, spec.get("player", "you")):
        total += lose_life(ctx.state, pid, amount, source=ctx.source_oid)
    if name := spec.get("as"):
        ctx.bindings[str(name)] = total


@register("add_poison")
def op_add_poison(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "That player gets N poison counters." Poisonous, and infect's other half.

    A counter on the *player*, not a second life total. Ten of them is lethal
    (704.5c) and the loss has its own reason, because a player eliminated at 40
    life did not run out of life and a log saying so would be lying about how
    the game ended.

    It comes off with every other player counter through
    `lose_all_player_counters`.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    if amount <= 0:
        return
    for pid in select_players(ctx, spec.get("player", "opponent")):
        # Through the funnel, so a counter replacement that reaches players
        # (Innkeeper's Talent) applies. The effect's controller puts them.
        add_poison(ctx.state, pid, amount, source=ctx.source_oid, by=ctx.controller)


@register("add_energy")
def op_add_energy(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You get {E}{E} (two energy counters)." (107.14)

    `add_poison`'s shape with the other default: energy is something a card
    gives its own controller, so ``player`` defaults to ``you``. Spent by a
    ``pay_energy`` cost, and taken away by `lose_all_player_counters`.
    """
    amount = evaluate_value(ctx, spec.get("amount", 1))
    if amount <= 0:
        return
    for pid in select_players(ctx, spec.get("player", "you")):
        add_energy(ctx.state, pid, amount, source=ctx.source_oid, by=ctx.controller)


@register("lose_all_player_counters")
def op_lose_all_player_counters(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Each opponent loses all counters." (Final Act)

    Every counter of every kind on each named player (122.1): poison and
    energy, and any kind `player.PLAYER_COUNTER_KINDS` comes to list. Not
    `remove_counters`, which takes one named kind off *objects* -- a player is
    not one -- and not a kind-by-kind removal the author spells out, because a
    card that listed poison and energy would stop being "all counters" the day
    the player model carried a third kind.

    ``player`` is required: the printed sentence always names who, and a
    default would be a guess about whose counters an author forgot to name.
    Each kind goes through `primitives.remove_player_counters`, so the poison
    removal re-reads a corrupted static and the log hears each kind once.
    """
    state = ctx.state
    for pid in select_players(ctx, spec["player"]):
        player = state.players[pid]
        for kind in PLAYER_COUNTER_KINDS:
            remove_player_counters(
                state, pid, kind, getattr(player, kind), source=ctx.source_oid
            )


@register("prevent_damage")
def op_prevent_damage(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Prevent all damage that would be dealt to you this turn." (Selfless
    Squire, Fog, Holy Day.)

    The same two words the `prevent_damage` **static** prints, and a different
    thing -- exactly the relationship `cant_block` the op has with `cant_block`
    the static, and for the same three reasons. The static is absorb N
    (702.63a): `characteristics.prevented_damage(state, oid)` reads it off
    `_battlefield_statics` and matches each entry's `affects` filter against a
    **permanent**, it is per source and per instance rather than a blanket, and
    it is continuous while its source stands on the battlefield. So it can say
    "prevent 1 damage to this creature, while I am here" and it can say nothing
    about a *seat*, nothing about "all", and nothing about "this turn" -- a
    Squire carrying one would fog its controller on every future turn too, which
    is a Worship. `static_filter_keys` has no way to name a player at all.

    This op is that sentence with the subject and the clock swapped round, which
    is why it is an op and not a fourth static key. It installs a
    `structs.DamageShield` and modifies nothing: it resolves *before* the damage
    exists, so the whole of its behaviour is the record it leaves behind for
    `primitives.damage_player` to consult.

    ``player`` is the usual player spec and defaults to ``"you"`` -- the printed
    sentence is nearly always about the controller, and the ones that are not
    ("prevent all damage that would be dealt to target player") name a target.

    ``duration`` is required and the only implemented word is ``this_turn``,
    cleared by the cleanup step. Required rather than defaulted for the reason
    `cant_block`'s is: a prevention read as lasting longer than it does is a
    different and much better card, and there is no reading of an omitted
    duration that is safe to guess.

    There is deliberately no ``amount``. See `structs.DamageShield`: absorb-N
    over a player is a different effect with a pool that drains, and the loader
    refuses the key rather than reading it and preventing everything anyway.
    """

    duration = str(spec.get("duration", "this_turn"))
    if duration not in DAMAGE_SHIELD_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown prevent_damage duration {duration!r}")
    for pid in select_players(ctx, spec.get("player", "you")):
        shield_player(ctx.state, pid, duration, source=ctx.source_oid)


@register("prevent_damage_permanent")
def op_prevent_damage_permanent(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Prevent all damage that would be dealt to him this turn." (Gideon Jura,
    Gideon, Champion of Justice.) "Until your next turn, prevent all damage
    target permanent would deal." (Gideon of the Trials.) "…dealt to and dealt
    by target permanent an opponent controls." (Kiora, the Crashing Wave.)

    `prevent_damage` the op with the subject swapped from a seat to a
    permanent, and able to face both ways. The `prevent_damage` *static* is the
    near miss and cannot say any of these: it lives on a printed permanent and is
    continuous while that permanent stands, so it has no "this turn" and no
    "until your next turn", it cannot be installed by a resolving ability, and it
    only ever stops damage dealt *to* what it matches.

    ``objects`` is a selector resolved **now** -- ``{"self_only": true}`` for
    Gideon, ``{"target": "t1"}`` for the targeted forms -- battlefield-filtered,
    so a permanent that left in response gets nothing.

    ``dealt`` is required: ``"to"``, ``"by"`` or ``"to_and_by"``. Required
    rather than defaulted because the two readings are different cards and
    neither is safe to guess -- a Fog on a creature versus a Pacifism on its
    damage.

    ``duration`` is required: ``this_turn`` (cleanup) or ``until_your_next_turn``
    (the controller's next untap step). A prevention read as lasting longer than
    it does is a strictly better card, silently.

    Installs a `structs.PermanentShield` on each object and modifies nothing
    else; `primitives.damage_permanent` and `primitives.damage_player` read it.
    """

    duration = str(spec.get("duration", "this_turn"))
    if duration not in PERMANENT_SHIELD_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown prevent_damage_permanent duration {duration!r}")
    dealt = str(spec.get("dealt", "to"))
    if dealt not in PERMANENT_SHIELD_DIRECTIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown prevent_damage_permanent direction {dealt!r}")
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        shield_permanent(
            ctx.state,
            oid,
            dealt,
            duration,
            player=ctx.controller,
            source=ctx.source_oid,
        )


@register("prevent_combat_damage")
def op_prevent_combat_damage(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Prevent all combat damage that would be dealt this turn by non-Spider
    creatures." (Arachnogenesis.)

    Keyed to the damage's source, where `prevent_damage` is keyed to a seat and
    stops burn too, and `prevent_damage_permanent` shields objects chosen now.
    ``by`` is a static filter over the creature dealing the damage, read on its
    current characteristics each time combat damage would be dealt, so a
    creature entering later in the turn is covered; omitted, it is every source
    (Fog). ``duration`` is ``this_turn``, required for `prevent_damage`'s reason.
    Installs a `structs.CombatFog` and modifies nothing else.
    """
    duration = str(spec.get("duration", "this_turn"))
    fog_combat_damage(
        ctx.state, ctx.controller, spec.get("by"), duration, source=ctx.source_oid
    )


@register("redirect_damage")
def op_redirect_damage(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until end of turn, all damage that would be dealt to you and creatures
    you control is dealt to the chosen creature instead (if it's still on the
    battlefield)." (Heroic Sacrifice.)

    A replacement of the damage's recipient (614.9), where every prevention
    only answers how much lands. ``to`` names the one permanent that receives
    it, resolved now -- usually ``{"target": "t1"}``. ``player`` is the seat
    whose damage is redirected and ``permanents`` a static filter over the
    permanents whose damage is, read on their current characteristics as the
    damage would be dealt; at least one is required. ``duration`` is
    ``this_turn``, required for `prevent_damage`'s reason. Installs a
    `structs.DamageRedirect` and modifies nothing else; with ``to`` already
    gone it installs nothing.
    """
    duration = str(spec.get("duration", "this_turn"))
    chosen = resolve_pool(ctx, spec["to"])
    if not chosen:
        return
    pids = select_players(ctx, spec["player"]) if "player" in spec else [None]
    for pid in pids:
        redirect_damage_to(
            ctx.state,
            chosen[0],
            ctx.controller,
            player=pid,
            permanents=spec.get("permanents"),
            duration=duration,
            source=ctx.source_oid,
        )


@register("lock_life_total")
def op_lock_life_total(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until your next turn, your life total can't change." (Teferi's Protection.)

    A prohibition on the *change*, both ways, which is what nothing else in the
    engine could say. `replace_life_loss` is the near miss and misses three
    ways: it is a `static_effect`, so an Instant cannot install one; it
    multiplies a loss rather than forbidding a change, and a multiplier of zero
    would still be a downward-only rewrite; and it is wired into `lose_life` and
    the loss half of `damage_player` only, so `gain_life` moves the total
    straight past it. `prevent_damage` the op is player-scoped and stops damage
    alone, leaving every ordinary loss and all gain free.

    Like `prevent_damage`, it modifies nothing and resolves before there is
    anything to modify: the whole of its behaviour is the `structs.LifeLock` it
    leaves behind for `primitives.life_locked` to answer from.

    ``player`` is the usual player spec and defaults to ``"you"``, which is what
    both printed sentences say. ``duration`` defaults to ``until_your_next_turn``
    for the same reason -- there is no printed life lock that ends at cleanup --
    and the cleanup word is implemented so that this table is not the one
    exception among the timed tables.
    """

    duration = str(spec.get("duration", "until_your_next_turn"))
    if duration not in LIFE_LOCK_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown lock_life_total duration {duration!r}")
    for pid in select_players(ctx, spec.get("player", "you")):
        lock_life_total(ctx.state, pid, duration, source=ctx.source_oid)


@register("damage")
def op_damage(ctx: EffectContext, spec: Mapping[str, Any]):
    """Deal damage to objects, players, or both.

    ``objects`` and ``player`` are independent: a card that reads "deal 3 damage
    to target creature and 3 damage to its controller" declares both.

    ``divided`` names a target spec whose objects **share** the amount -- "4
    damage divided as you choose among any number of target creatures". The
    split was announced as the spell was cast (601.2d, `Game._ask_damage_division`)
    and travels as ``bindings["distribution"]``, so the amount is not read again
    here: each still-legal target is dealt its share, and one made illegal in
    response takes its share with it rather than passing it on (608.2b).
    """
    if "divided" in spec:
        _damage_divided(ctx, str(spec["divided"]))
        return
    amount = evaluate_value(ctx, spec.get("amount", 1))
    if amount <= 0:
        return

    # "**Target creature you control** deals damage equal to its power to each
    # other creature and each opponent" -- Chandra's Ignition. The damage is
    # dealt BY that creature, not by the spell, and the difference is the whole
    # card: lifelink on it gains its controller life, deathtouch on it kills
    # what it hits, and "damage dealt by a source you control" triggers read it.
    # Left as the resolving source when absent, which is every other card.
    dealer = ctx.source_oid
    if "source_object" in spec:
        named = resolve_pool(ctx, spec["source_object"])
        if not named:
            # The named creature has gone -- countered target, or removed in
            # response. Nothing deals the damage, rather than the spell dealing
            # it in the creature's place.
            return
        dealer = named[0]

    if "objects" in spec:
        for oid in resolve_pool(ctx, spec["objects"]):
            damage_permanent(ctx.state, oid, amount, dealer)

    if "player" in spec:
        for pid in select_players(ctx, spec["player"]):
            damage_player(ctx.state, pid, amount, dealer)

    if "defender_of" in spec:
        _damage_what_it_attacks(ctx, spec["defender_of"], amount, dealer)

    if "target" in spec:
        # A single target that may be either a creature or a player ("any target").
        for ref in ctx.target_refs(str(spec["target"])):
            if ref.kind == "object":
                if spec.get("excess_to"):
                    _damage_with_excess(ctx, ref.id, amount, str(spec["excess_to"]))
                else:
                    damage_permanent(ctx.state, ref.id, amount, dealer)
            elif ref.kind == "player":
                damage_player(ctx.state, ref.id, amount, dealer)


@register("fight")
def op_fight(ctx: EffectContext, spec: Mapping[str, Any]):
    """Two creatures each deal damage equal to their power to the other (701.12a).

    "Target creature you control fights another target creature" -- Ulvenwald
    Tracker; Bridgeworks Battle's second sentence is the same keyword action.

    Two sequential ``damage`` ops are the near miss, and they are a different
    effect three ways over. **The exchange is simultaneous**: powers are read
    before either blow lands, so a creature that dies to the first still deals
    its damage, where the sequential spelling lets the bigger creature kill the
    smaller one and walk away untouched. **It is all-or-nothing** (701.12c): if
    either creature has left the battlefield by the time the fight happens,
    *neither* deals damage, where the sequential spelling would still fire the
    surviving half. And each blow is dealt **by the creature**, not by the
    spell, which is what makes lifelink gain its controller life and deathtouch
    kill -- ``source_object`` on ``damage`` can say that, but only one dealer at
    a time.

    701.12d: a creature cannot fight itself. If both halves resolve to the same
    permanent nothing happens at all, rather than it dealing itself damage
    twice.

    Zero power is not a special case -- ``damage_permanent`` ignores a
    non-positive amount -- but a 0/1 fighting a 3/3 must still *take* its three,
    so the guard is per-blow and never abandons the exchange.
    """

    state = ctx.state
    left = resolve_pool(ctx, spec.get("objects"))
    right = resolve_pool(ctx, spec.get("other"))
    if not left or not right:
        return
    a, b = left[0], right[0]
    if a == b:
        # 701.12d. Reachable whenever one selector could pick what the other
        # already named; `exclude_binding` is how a card says "another", and a
        # card that omits it should do nothing rather than hit itself twice.
        return

    both = [state.objects.get(a), state.objects.get(b)]
    if any(o is None or not o.on_battlefield for o in both):
        return  # 701.12c -- neither deals damage.

    # Read both powers before either blow lands. This is the whole of what makes
    # it a fight rather than two damages: the loser of the exchange has already
    # had its power read by the time it dies.
    power_a = chars(state, a).power or 0
    power_b = chars(state, b).power or 0
    damage_permanent(state, b, power_a, a)
    damage_permanent(state, a, power_b, b)


def _damage_what_it_attacks(
    ctx: EffectContext, selector: Mapping[str, Any], amount: int, dealer: int | None
) -> None:
    """ "…deals X damage to **the player or planeswalker it's attacking**." --
    Myr Battlesphere.

    ``defender_of`` names the attacking creature (``{"zone": "battlefield",
    "self_only": true}`` for "it"), and the recipient is read off the combat at
    resolution: the planeswalker in `combat.attacking_permanent` when it is
    attacking one, otherwise the player in `combat.attackers` (506.2). A
    creature that is no longer attacking -- removed from combat, or gone --
    attacks nothing, so nothing is dealt. Nor is a **battle**: the printed
    sentence names a player or a planeswalker, and a battle is neither.

    The near miss is ``"player": {"binding": "defender"}`` off the `attacks`
    trigger, and it is wrong twice: the binding is the defending *player* even
    when the attack is at a planeswalker, so the walker's controller would take
    the damage the card deals to the walker; and it is fixed as the trigger
    fires, so an attack reselected in between (`redirect_attack`) would not be
    followed.
    """

    state = ctx.state
    combat = state.combat
    if combat is None:
        return
    for oid in resolve_pool(ctx, selector)[:1]:
        if not combat.attacking(oid):
            continue
        permanent = combat.attacking_permanent.get(oid)
        if permanent is None:
            damage_player(state, combat.attackers[oid], amount, dealer)
        elif "Planeswalker" in chars(state, permanent).types:
            damage_permanent(state, permanent, amount, dealer)


def _damage_divided(ctx: EffectContext, target_id: str) -> None:
    """Each target its announced share, and nothing for one that left (608.2b).

    A copy of the spell carries the same bindings, so it keeps the division
    (707.10). No announcement with targets declared is a spell cast some way
    that skipped 601.2d, and inventing a split now would be a different card.
    """
    legal = set(ctx.target_oids(target_id))
    division = (ctx.bindings.get("distribution") or {}).get(target_id)
    if division is None:
        if ctx.target_refs(target_id):
            raise DslError(
                f"divided damage for {target_id!r} resolved without an announced division"
            )
        return
    for oid, share in division:
        if int(oid) in legal and int(share) > 0:
            damage_permanent(ctx.state, int(oid), int(share), ctx.source_oid)


def _damage_with_excess(ctx: EffectContext, oid: int, amount: int, excess_to: str) -> None:
    """ "Excess damage is dealt to that creature's controller instead."

    Gandalf's Sanction. **One damage event split in two**, not two events: the
    creature is dealt exactly lethal and the remainder goes to a player, so a
    card that would have overkilled a 2/2 by nine points sends nine at its
    controller.

    Lethal is read the way `sba` reads it -- toughness minus damage already
    marked, or 1 from a deathtouch source -- because those two must agree or
    this leaves a creature one point short of the death the rules say it took.

    `trample` is the near miss and is combat-only, so it could not be reused;
    this is the noncombat spelling of the same idea.
    """

    state = ctx.state
    obj = state.objects.get(oid)
    if obj is None or not obj.on_battlefield:
        return
    c = chars(state, oid)
    source = state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    deathtouch = bool(
        source is not None
        and Keyword.DEATHTOUCH.value in chars(state, source.oid).keywords
    )
    lethal = 1 if deathtouch else max(0, (c.toughness or 0) - obj.damage)
    to_creature = min(amount, lethal)
    if to_creature > 0:
        damage_permanent(state, oid, to_creature, ctx.source_oid)
    spill = amount - to_creature
    if spill <= 0:
        return
    # "that creature's controller" is the only spelling any printed card uses,
    # and it is read off the object rather than through `select_players` because
    # the creature is the subject: a control-changing effect has to move the
    # excess with it.
    if excess_to == "controller":
        damage_player(state, obj.controller, spill, ctx.source_oid)


@register("cant_lose_the_game")
def op_cant_lose_the_game(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You can't lose the game this turn and your opponents can't win the game
    this turn." -- Angel's Grace.  Rules 104.3b and 614.

    `sba.declare_win`'s own docstring listed this among the things "deliberately
    not modelled, because no card in the pool needs it yet", adding that it "is
    replacement-shaped and belongs beside the other continuous prohibitions".
    Angel's Grace is the first card in the pool to need it.

    **Two independent flags, because they are two sentences.** Angel's Grace
    prints both and most cards print one: Platinum Angel says both, Abyssal
    Persecutor says only "you can't win the game". A single symmetric flag would
    make every card in the family read like Platinum Angel.

    So the op takes `cant_lose` and `cant_win`, each with its own player spec, and
    Angel's Grace writes them about different seats -- itself and its opponents.

    `lock_life_total` is the near miss and is a different card three times over:
    it forbids the total *changing*, so it blocks life gain too; Angel's Grace is
    routinely cast at 40 and leaves you at 1, which that would prevent; and it
    says nothing at all about the other three ways to lose or about an opponent
    winning. `prevent_damage` the op is the other near miss and is a Fog -- the
    total never moves, so you end the turn at 40 rather than at 1, and 104.3b's
    point is that you survive *at* 1 or less.
    """

    duration = str(spec.get("duration", "this_turn"))
    if duration not in OUTCOME_LOCK_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_lose_the_game duration {duration!r}")
    for pid in select_players(ctx, spec.get("cant_lose") or ()):
        lock_game_outcome(
            ctx.state, pid, cant_lose=True, duration=duration, source=ctx.source_oid
        )
    for pid in select_players(ctx, spec.get("cant_win") or ()):
        lock_game_outcome(
            ctx.state, pid, cant_win=True, duration=duration, source=ctx.source_oid
        )


@register("damage_life_floor")
def op_damage_life_floor(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until end of turn, damage that would reduce your life total to less than
    1 reduces it to 1 instead." -- Angel's Grace.  Rule 614.

    A **floor on the total**, not a prevention, and that is the card. The near
    miss is `prevent_damage` the op, which is a Fog: it installs a `DamageShield`
    and the total never moves, so a player at 40 ends the turn at 40 rather than
    at 1. Angel's Grace lets the damage through and stops the total passing 1,
    which is why it is cast *to survive at 1 life* -- and why the printed card
    pairs it with `cant_lose_the_game`, since surviving at 1 is worth nothing if
    the next point kills you.

    `replace_damage` is the other near miss and is a multiplier with no floor and
    no cap, and a static besides -- an Instant cannot install one. `lock_life_total`
    freezes the total in both directions, so it would also stop you paying life
    and stop you gaining any.

    It floors **damage only**, which is the printed word: an ordinary `lose_life`
    walks past it, so a Phyrexian cost still takes you below 1 under Angel's
    Grace. That is correct, and it is why the floor is read in `damage_player` and
    nowhere else.
    """

    duration = str(spec.get("duration", "this_turn"))
    if duration not in LIFE_FLOOR_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown damage_life_floor duration {duration!r}")
    floor = evaluate_value(ctx, spec.get("floor", 1))
    for pid in select_players(ctx, spec.get("player", "you")):
        set_life_floor(ctx.state, pid, floor, duration, source=ctx.source_oid)
