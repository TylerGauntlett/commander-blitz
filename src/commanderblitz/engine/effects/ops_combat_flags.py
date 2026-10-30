"""Effect ops that restrict, compel or rearrange combat and sacrifice: detain,
goad, must-attack/-block, can't-attack/-block/-sacrifice, unblockable,
reselecting an attack, and flags."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..characteristics import chars
from ..enums import Step
from ..errors import DslError
from ..objects import PLUS_ONE
from ..player_statics import proliferate_times
from ..primitives import add_counters, add_energy, add_poison, remove_counters
from ..structs import (
    ATTACK_MARK_DURATIONS,
    ATTACK_RESTRICTION_DURATIONS,
    BLOCK_PROHIBITION_DURATIONS,
    CANT_SACRIFICE_DURATIONS,
    UNBLOCKABLE_DURATIONS,
    TargetRef,
)
from ..temp_effects import (
    forbid_block,
    forbid_sacrifice,
    goad_creature,
    grant_cant_be_sacrificed,
    make_unblockable,
    require_attack_on,
    require_attack_player,
    restrict_attack,
)
from .board_helpers import (
    _offer_blocks_to,
    _players,
)
from .context import EffectContext, ask_targets
from .registry import register
from .selectors import (
    choose_objects,
    resolve_pool,
)
from .values import evaluate_value


@register("detain")
def op_detain(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until your next turn, that permanent can't attack or block and its
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
    """ "Choose any number of permanents and/or players, then give each another
    counter of each kind already there." (701.27a)

    Not an `add_counters` with a filter: the kinds are read **per chosen thing,
    at resolution**, and differ between them -- one proliferate adds a +1/+1
    here, a loyalty counter there and a poison counter to an opponent.

    **The choice is the card.** The controller picks any subset of every
    permanent (any controller) and every player with a counter, in one
    `ask_targets` decision with mixed object and player refs. Only things that
    already carry a counter are offered, because choosing anything else adds
    nothing (it "never starts a kind"). A choice, not a sweep, because what you
    decline is the point as often as what you pick: an infect deck grows an
    opponent's poison and their -1/-1 counters and never their planeswalker's
    loyalty, and nobody grows the -1/-1 counters on their own creature.

    Proliferate is not targeting (the word "target" is absent), so hexproof and
    shroud do not stop it -- which is why the decision's purpose is
    ``"proliferate"`` and not ``"target"``.

    A player's counters are `PlayerState.poison` and `PlayerState.energy`, and
    a chosen player gets one more of each kind they already have, the way a
    permanent does. Experience would join here when a card first needs it.

    "If you would proliferate, proliferate twice instead" (Tekuthal, the
    `replace_proliferate` static) is read here, once, before the first: each
    repetition is a whole proliferate with its own choice, asked after the one
    before it resolved. See `player_statics.proliferate_times`.
    """
    for _ in range(proliferate_times(ctx.state, ctx.controller)):
        yield from _proliferate_once(ctx)


def _proliferate_once(ctx: EffectContext):
    """One 701.27a proliferate: the choice, then one of each kind on each."""
    state = ctx.state
    refs: list[tuple[str, TargetRef]] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is not None and obj.on_battlefield and any(n > 0 for n in obj.counters.values()):
            refs.append((ctx.name_of(oid), TargetRef.obj(oid)))
    for player in state.players:
        kinds = [k for k, n in (("poison", player.poison), ("energy", player.energy)) if n > 0]
        if not player.has_lost and kinds:
            seat = player.name or f"Player {player.pid}"
            refs.append((f"{seat} ({', '.join(kinds)})", TargetRef.player(player.pid)))
    picked = yield from ask_targets(
        ctx,
        "Proliferate: choose any number of permanents and/or players",
        refs,
        0,
        len(refs),
        ctx.controller,
        purpose="proliferate",
    )
    # Snapshotted before anything is added: the kinds are the ones "already
    # there" as proliferate resolves, and `add_counters` mutates the dict.
    plan = [
        (
            ref,
            list(state.objects[ref.id].counters.items())
            if ref.kind == "object"
            else [("poison", state.players[ref.id].poison), ("energy", state.players[ref.id].energy)],
        )
        for ref in picked
    ]
    for ref, kinds in plan:
        if ref.kind == "player":
            # Through `add_poison` and `add_energy`, the funnels for a player's
            # counters, so a counter replacement that reaches players
            # (Innkeeper's Talent's "...on a permanent or player") applies --
            # writing the field directly skipped it.
            for kind, amount in kinds:
                if amount <= 0:
                    continue
                funnel = add_poison if kind == "poison" else add_energy
                funnel(state, ref.id, 1, source=ctx.source_oid, by=ctx.controller)
            continue
        obj = state.objects.get(ref.id)
        if obj is None or not obj.on_battlefield:
            continue
        for kind, amount in kinds:
            if amount > 0:
                add_counters(state, ref.id, kind, 1, source=ctx.source_oid)


@register("set_flag")
def op_set_flag(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "…and it becomes renowned." A one-way word written onto a permanent.

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
    # A static's `has_flag` condition reads the word, and `chars` is cached
    # per `char_version`.
    ctx.state.bump_chars()
    yield from ()


@register("set_turn_flag")
def op_set_turn_flag(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "…and it has been exerted." A word that wears off at the turn boundary.

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


def _move_every_kind(ctx: EffectContext, spec: Mapping[str, Any]):
    """Move the whole multiset of counters, not one named kind.

    Two sources, and the second is why this is not just a loop over
    `source.counters`:

    - An ordinary permanent -- The Ozolith's "move all counters from The Ozolith
      onto target creature" -- reads its live counters.
    - A permanent that has **already left** -- The Ozolith's own trigger,
      "whenever a creature you control leaves the battlefield, if it had
      counters on it, put those counters on The Ozolith". By the time that
      resolves the creature is gone and `reset_permanent_state` has emptied it,
      so the counts come from the leave event's `had_counters` snapshot, which
      is the same place `counters_had` reads and the same explicit-LKI pattern
      `snapshot` established.
    """
    from_had = bool(spec.get("from_had_counters"))
    if from_had:
        snapshot = ctx.bindings.get("had_counters")
        counts = dict(snapshot) if isinstance(snapshot, Mapping) else {}
        sources: list[int] = []
    else:
        if "from" in spec:
            sources = resolve_pool(ctx, spec["from"])
        else:
            sources = [ctx.source_oid] if ctx.source_oid is not None else []
        counts = {}
        for source_oid in sources:
            source = ctx.state.objects.get(source_oid)
            if source is None:
                continue
            for counter_kind, amount in source.counters.items():
                if amount > 0:
                    counts[counter_kind] = counts.get(counter_kind, 0) + amount
    if not counts:
        # Nothing to move is not nothing to do wrong: asking for a destination
        # anyway would put a prompt in front of a player for a trigger whose
        # intervening-if already said no.
        return
    destinations = yield from choose_objects(ctx, spec.get("objects"), "Move counters to")
    if not destinations:
        return
    for source_oid in sources:
        source = ctx.state.objects.get(source_oid)
        if source is None or not source.on_battlefield:
            continue
        for counter_kind, amount in list(counts.items()):
            remove_counters(ctx.state, source_oid, counter_kind, min(amount, source.counter(counter_kind)))
    for dest_oid in destinations:
        for counter_kind, amount in counts.items():
            add_counters(ctx.state, dest_oid, counter_kind, amount, source=ctx.source_oid)


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
    # "…put **those counters** on The Ozolith", and "move **all counters** from
    # The Ozolith onto target creature". Both mean the whole multiset -- every
    # kind, with its own amount -- where every other card in this family names
    # one kind. Naming `+1/+1` for The Ozolith would silently drop loyalty,
    # charge, oil and the rest, which is a card that looks implemented and is
    # quietly smaller than printed.
    if spec.get("all_kinds"):
        yield from _move_every_kind(ctx, spec)
        return
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
    """ "Target creature attacks during its controller's next combat phase if able."

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
    """ "Goad those creatures." (701.38a)

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

    ``duration: "permanent"`` is "they're goaded **for the rest of the game**"
    (Dack Fayden, Helping Hand), the one other clock a printed goad has: the
    goader's untap step leaves the mark alone, and the goader leaving the game
    still ends it (800.4a). The mark is the goader's whoever controls the
    creature, so a creature goaded this way and then handed to an opponent
    must attack a player other than the goader -- which is why Dack's goad
    comes before his control change and must be written in that order.
    """
    goaders = _players(ctx, spec["player"]) if "player" in spec else [ctx.controller]
    permanent = spec.get("duration") == "permanent"
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        for player in goaders:
            # Battlefield and liveness are checked in the primitive, which is
            # also what makes a creature that left in response get nothing.
            goad_creature(ctx.state, oid, player, permanent=permanent)
    yield from ()


@register("must_attack_player")
def op_must_attack_player(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until the end of your next turn, target creature attacks **that player**
    each combat if able." (Silver Surfer, Galactus's Herald.)

    A requirement naming the **defending player**, written on each creature in
    ``objects`` as a `structs.AttackMark` and read live by
    `combat.required_attack_defenders` -- the same reader as the
    `attacks_if_able` static's ``defending``, so the one-shot and the
    continuous form are one requirement to 508.1d. It is obeyed only by
    attacking that player, not a planeswalker or battle they control (506.2),
    and while that seat cannot be attacked it compels nothing at all ("if
    able"): the creature is not sent at somebody else instead.

    ``objects``   the creatures, chosen at resolution (required).
    ``defender``  the player to attack -- ``{"binding": "defender"}`` for
                  "that player" on a combat-damage trigger (required). Several
                  players are several requirements.
    ``duration``  ``end_of_your_next_turn`` (required): the effect
                  controller's next turn's cleanup ends it, `TempEffect`'s
                  clock for the same words.

    Why not the near misses: `must_attack` names no defender and is spent
    after one combat; goad points *away* from a player and ends at the
    goader's next turn rather than its end; `must_attack_planeswalker` names a
    walker and binds a player's creatures, not a creature.
    """
    duration = str(spec.get("duration", ""))
    if duration not in ATTACK_MARK_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown must_attack_player duration {duration!r}")
    defenders = _players(ctx, spec.get("defender"))
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        for defender in defenders:
            require_attack_player(
                ctx.state, oid, defender, ctx.controller, source=ctx.source_oid
            )
    yield from ()


@register("must_attack_planeswalker")
def op_must_attack_planeswalker(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "During target opponent's next turn, creatures that player controls
    attack Gideon Jura if able." (Gideon Jura +2.)

    A requirement naming **one attack target**, which nothing else could say:
    `must_attack` flags the creatures on the battlefield at resolution, lasts
    `this_turn`/`next_combat` and names no defender; the `attacks_if_able`
    static and goad name no planeswalker either (goad points *away* from a
    player). The creatures are the player's *during that turn*, arrivals
    included, so the mark goes on the planeswalker and is read live by
    `combat.required_attack_walkers`.

    ``player`` is the compelled player (normally ``{"target": "t1"}``);
    ``objects`` names the planeswalker to be attacked -- ``{"self_only": true}``
    for Gideon Jura. Both required by the loader. The mark is pending until
    that player's next untap step and ends in that turn's cleanup; it ends early
    if the planeswalker leaves (400.7).
    """

    walkers = [
        oid
        for oid in resolve_pool(ctx, spec.get("objects") or {})
        if (obj := ctx.state.objects.get(oid)) is not None and obj.on_battlefield
    ]
    for pid in _players(ctx, spec["player"]):
        for walker in walkers:
            require_attack_on(ctx.state, walker, pid)
    yield from ()


@register("cant_attack_player")
def op_cant_attack_player(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You can't attack that player this turn." "They can't attack you this combat."

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

    ``planeswalkers_matching``  optional, ``{"subtypes": [...]}``. The narrow
    mirror of the flag: the defender's **seat stays open** and so does every
    other permanent of theirs, and only their planeswalkers with one of those
    subtypes are closed -- Jace, Multiverse Architect's "creatures they control
    can't attack Jaces you control this turn". Read off the walker's current
    subtypes when attackers are declared, so a Jace that arrives later in the
    turn is covered as well. Never beside ``planeswalkers: true``; the loader
    refuses the pair.

    Nothing is written on any permanent, and that is the point: a resolving
    sorcery leaves no source on the battlefield to hang a static off, which is
    the first of the three reasons the `cant_attack` static could not do this job.
    """

    duration = str(spec.get("duration", "this_turn"))
    if duration not in ATTACK_RESTRICTION_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_attack_player duration {duration!r}")
    planeswalkers = bool(spec.get("planeswalkers", False))
    walker_subtypes = tuple((spec.get("planeswalkers_matching") or {}).get("subtypes") or ())
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
                walker_subtypes=walker_subtypes,
            )
    yield from ()


@register("cant_block")
def op_cant_block(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "That creature can't block this turn." "Until your next turn, those
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
    either: the loader refuses any grantable ability that is not triggered.)

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
    forbid_block(ctx.state, oids, duration, player=ctx.controller, source=ctx.source_oid)
    yield from ()


@register("unblockable")
def op_unblockable(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Target creature can't be blocked this turn." (Rogue's Passage.)

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

    ``except_blockers`` is "…except by creatures with haste" (Gingerbrute): a
    static filter, ``{"keywords": ["haste"]}``, that a would-be blocker matching
    is exempt from the restriction. It is read off the blocker as it is when
    blocks are declared (`combat.unblockable`), not when this resolves, so a
    creature that gains haste afterwards may still block. Absent, every blocker
    is refused -- which is why it may never be dropped from a card that prints
    the exception: the creature would be strictly harder to block than printed.
    """

    duration = str(spec.get("duration", "this_turn"))
    if duration not in UNBLOCKABLE_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown unblockable duration {duration!r}")
    oids = [
        oid
        for oid in resolve_pool(ctx, spec.get("objects") or {})
        if (obj := ctx.state.objects.get(oid)) is not None and obj.on_battlefield
    ]
    make_unblockable(
        ctx.state,
        oids,
        duration,
        player=ctx.controller,
        source=ctx.source_oid,
        except_blockers=spec.get("except_blockers"),
    )
    yield from ()


@register("cant_sacrifice")
def op_cant_sacrifice(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You can't sacrifice those creatures this turn." (Call for Aid, 701.17b.)

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
    would read a one-sided sentence as a two-sided one. ``duration`` is required:
    ``this_turn``, or ``end_of_your_next_turn`` for Stilt-Man, Towering
    Terror's "It gains \"This permanent can't be sacrificed\" until the end of
    your next turn" -- "your" being this effect's controller. That second word is
    a granted ability riding the permanent rather than a table row, so it ends
    with the object as well as with the clock; see
    `temp_effects.grant_cant_be_sacrificed` and `structs.CANT_SACRIFICE_DURATIONS`.

    Unlike `cant_block` and `unblockable` the pool is **not** filtered to the
    battlefield here. Those two record creatures for a combat that has not
    happened yet, where a dead oid would look like an entry that bit somebody;
    this one is read by pools that already contain nothing but permanents on the
    battlefield, and dropping a creature that flickered out in response would
    mean it comes back sacrificeable -- a distinction the printed card does not
    draw. See `primitives.forbid_sacrifice`.
    """

    duration = str(spec.get("duration", "this_turn"))
    if duration not in CANT_SACRIFICE_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_sacrifice duration {duration!r}")
    if duration == "end_of_your_next_turn":
        grant_cant_be_sacrificed(
            ctx.state,
            resolve_pool(ctx, spec.get("objects") or {}),
            ctx.controller,
            source=ctx.source_oid,
        )
        yield from ()
        return
    forbid_sacrifice(
        ctx.state,
        resolve_pool(ctx, spec.get("objects") or {}),
        duration,
        source=ctx.source_oid,
    )
    yield from ()


@register("choose_blockers")
def op_choose_blockers(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You choose which creatures block this combat and how those creatures
    block." -- Odric, Master Tactician.

    Not a restriction on any one creature, which is what makes it a different
    thing from every other op in this file. `must_block` and `cant_block` each
    constrain one blocker and leave the defender free everywhere else, so no
    combination of them can say this: the defender could still add blockers the
    effect never named, and "and **how** those creatures block" -- which attacker
    each one is assigned to -- has no spelling at all in a per-creature
    requirement.

    So what moves is the *decision*, not the creatures. `CombatState.blocker_chooser`
    records the seat that will answer DECLARE_BLOCKERS for every defender this
    combat, and `turn._next_blocker_decision` reads it when it hands the prompt
    out. Every legality check is untouched and still asks about the defender:
    `legal_blocks` offers the defender's creatures, `add_blocker` validates
    against them, and `blocks_valid` / `unmet_block_requirements` still hold the
    defender to their own lures and menace. A stolen declaration is therefore
    exactly as legal as the defender's own would have been, which is the printed
    card -- Odric may choose badly but may not choose illegally.

    Recorded on the combat rather than on a player, because "this combat" is the
    printed duration: it dies with `state.combat` and needs no clock of its own,
    and a second combat granted the same turn correctly begins free of it. That
    is also why it needs no entry in the until-end-of-turn machinery.

    ``player`` names who chooses and defaults to the ability's controller, which
    is every printed card of this shape.
    """
    combat = ctx.state.combat
    if combat is None:
        return
    chooser = _players(ctx, spec.get("player", "you"))
    combat.blocker_chooser = chooser[0] if chooser else ctx.controller
    yield from ()


@register("redirect_attack")
def op_redirect_attack(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You may reselect which player or permanent target attacking creature is
    attacking. (It can't attack its controller or their permanents.)" --
    Misleading Signpost, Portal Mage.

    ``objects`` names the attacking creatures, normally ``{"target": "t1"}``.
    For each one still attacking, the **effect's controller** -- not the
    creature's -- picks its new attack target from 506.2's three kinds: a
    player other than the creature's controller, or a planeswalker or battle one
    of those players controls (a battle is attacked by its controller's
    opponents here, as `combat.legal_permanent_defenders` reads it). The
    current target is among the options, so "reselect" may land where it was;
    the printed "you may" is a `may` around the op.

    **Nothing is declared**, and three things follow from that, each the
    reading `board_helpers` gives a creature put onto the battlefield attacking
    (508.4). Restrictions, requirements and costs on *declaring* (508.1c,
    508.1d, 508.1g) are not consulted -- Ghostly Prison is not paid again, a
    goaded creature may be sent at its goader -- which is why the printed
    reminder names only the controller and their permanents. No attack trigger
    fires. And the turn ledger keeps the declaration: `players_attacked_by`
    and `creatures_attacked` record what was declared, not where a creature was
    moved.

    The new defending player is offered blocks if nobody else was attacking
    them, and a player nobody attacks any more is dropped from the blocker
    queue -- both only before the declare blockers step, which is the window
    the printed cards resolve in. Once blockers are declared the op does
    nothing: a blocked creature's block is with the defender it was blocked by.
    """
    from ..combat import ATTACKABLE_TYPES

    state = ctx.state
    combat = state.combat
    if combat is None or combat.blockers_declared:
        return
    for oid in resolve_pool(ctx, spec.get("objects") or {}):
        obj = state.objects.get(oid)
        if obj is None or not obj.on_battlefield or not combat.attacking(oid):
            continue
        seats = [pid for pid in state.turn_order() if pid != obj.controller]
        refs = [
            (state.players[pid].name or f"Player {pid}", TargetRef.player(pid)) for pid in seats
        ]
        refs.extend(
            (ctx.name_of(perm), TargetRef.obj(perm))
            for perm in state.battlefield
            if perm != oid
            and (perm_obj := state.objects.get(perm)) is not None
            and perm_obj.controller in seats
            and any(t in chars(state, perm).types for t in ATTACKABLE_TYPES)
        )
        if not refs:
            continue
        picked = yield from ask_targets(
            ctx,
            f"Choose what {ctx.name_of(oid)} attacks",
            refs,
            1,
            1,
            ctx.controller,
            purpose="attack",
        )
        if not picked:
            continue
        old = combat.attackers[oid]
        choice = picked[0]
        if choice.kind == "object":
            combat.attackers[oid] = state.objects[choice.id].controller
            combat.attacking_permanent[oid] = choice.id
        else:
            combat.attackers[oid] = choice.id
            combat.attacking_permanent.pop(oid, None)
        _offer_blocks_to(ctx, combat.attackers[oid])
        still_attacked = any(
            combat.attacking(a) and pid == old for a, pid in combat.attackers.items()
        )
        if not still_attacked and state.step < Step.DECLARE_BLOCKERS:
            combat.pending_blockers = [p for p in combat.pending_blockers if p != old]
