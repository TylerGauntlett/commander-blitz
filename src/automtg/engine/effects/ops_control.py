"""Control-flow ops: conditionals, loops, optional effects, modes, snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..carddef import Cost
from ..costs import can_pay, pay
from ..zones import snapshot as capture_snapshot
from . import execute, register
from .conditions import evaluate
from .context import EffectContext, ask_mode, ask_player, ask_yes_no
from .selectors import resolve_pool, select_players
from .values import evaluate_value

if TYPE_CHECKING:  # pragma: no cover
    from ..state import GameState

cost_from_spec = Cost.from_spec


@register("if")
def op_if(ctx: EffectContext, spec: Mapping[str, Any]):
    branch = "then" if evaluate(ctx, spec.get("condition")) else "else"
    effects = spec.get(branch) or []
    yield from execute(ctx, effects)


@register("may")
def op_may(ctx: EffectContext, spec: Mapping[str, Any]):
    """An optional effect -- "you may draw a card".

    ``else`` is what turns it into "sacrifice it **unless** you return an
    untapped Island you control": declining is not always free, and without a
    branch for the refusal those cards read as pure upside.

    ``repeat`` is "…if you do, draw a card and **repeat this process**": ask
    again after each yes, and stop at the first no.  It is a loop rather than a
    ``repeat`` op with a count because the number of iterations is not knowable
    up front -- Cultivator Colossus draws into the lands it is putting down --
    and because a counted version would let a player decline and then accept,
    which the printed card does not.

    ``condition`` gates the question itself: with nothing to do, the card does
    not ask, which is what stops the loop when the hand runs dry.

    ``pay`` is what makes the option cost something -- Seer's Sundial's "you may
    pay {2}. **If you do**, draw a card".  It is an ordinary ``Cost``, paid out
    of the pool mid-resolution with mana abilities activatable to make it, and
    the wrapped ``effects`` are the "if you do" branch: they run only when the
    payment actually completed.  Without it the only way to write that card is
    to drop the cost, which turns a card that draws for {2} a land into one that
    draws free.

    A cost the player cannot afford is not offered at all rather than offered
    and then failing -- 601.2 in spirit, and it keeps the yes/no honest.
    """
    players = select_players(ctx, spec.get("player", "you"))
    chooser = players[0] if players else ctx.controller
    prompt = str(spec.get("prompt") or ctx.source_name or "Optional effect")
    condition = spec.get("condition")
    pay_spec = spec.get("pay")
    cost = cost_from_spec(pay_spec)
    if cost is not None and pay_spec is not None and pay_spec.get("times") is not None:
        # Cumulative upkeep: "pay its upkeep cost for each age counter on it".
        # Scaled here and nowhere else, because this is the one place a cost is
        # charged with an `EffectContext` in hand -- an activated ability's cost
        # is settled by legality before any effect has run, so a value
        # expression there would have nothing to read.
        cost = replace(cost, mana=cost.mana.scaled(evaluate_value(ctx, pay_spec["times"])))

    if not evaluate(ctx, condition):
        yield from execute(ctx, spec.get("else") or [])
        return

    # The same guard `repeat` uses: one pathological board must not hang a game.
    for _ in range(100):
        if cost is not None and not can_pay(ctx.state, chooser, cost, ctx.source_oid):
            yield from execute(ctx, spec.get("else") or [])
            return
        if not (yield from ask_yes_no(ctx, prompt, chooser)):
            yield from execute(ctx, spec.get("else") or [])
            return
        if cost is not None:
            paid = yield from pay(ctx.state, chooser, cost, ctx.source_oid)
            if not paid:
                # `can_pay` said yes a moment ago, so this is the board having
                # changed underneath us. "If you do" is false, so the effects
                # must not run -- the same contract `else` has for a refusal.
                yield from execute(ctx, spec.get("else") or [])
                return
        yield from execute(ctx, spec.get("effects") or [])
        if not spec.get("repeat") or not evaluate(ctx, condition):
            return


#: How many creature types a "choose a creature type" prompt will offer.
#:
#: The rules say *any* creature type. The pool's own subtypes are the finite,
#: honest version of that: a type no card in the game has is a choice with no
#: consequence, and enumerating the full Comprehensive Rules list would make the
#: prompt unusable without making any card play differently.
MAX_TYPE_CHOICES = 400


@register("choose_type")
def op_choose_type(ctx: EffectContext, spec: Mapping[str, Any]):
    """"As this artifact enters, choose a creature type." Vanquisher's Banner.

    Stored on the permanent, read back by its own abilities through
    ``{"chosen_type_of": "self"}``.

    **No new `DecisionKind`.** `ask_mode` already asks "pick one of these
    labels" and hands back the index, which is exactly this question -- so
    legality's `_choice_actions`, `game.apply` and the authoring verifier's
    auto-answer table all work unchanged. A `CHOOSE_TYPE` kind would have been
    the same decision wearing a different name.

    *Divergence, recorded in `rules-coverage.md`*: the printed line is "**as**
    this enters", a replacement that cannot be responded to. `zones` applies
    enter-replacements synchronously and cannot stop to ask, so this is a
    `self_enters` trigger instead and the type is chosen a moment after the
    permanent arrives rather than as it does.
    """
    types = sorted(_creature_types(ctx))
    if not types:
        return
    prompt = str(spec.get("prompt") or "Choose a creature type")
    picked = yield from ask_mode(ctx, prompt, types[:MAX_TYPE_CHOICES], ctx.controller)
    if not picked:
        return
    obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    if obj is not None:
        obj.chosen_type = types[picked[0]]
        ctx.state.bump_chars()


#: The five colours a "choose a color" prompt offers: ``(letter, label)`` in
#: WUBRG order.
#:
#: A fixed list, not a survey of the pool the way `_creature_types` is. There
#: are exactly five colours and every one of them is always a legal answer, so
#: there is nothing for the board to narrow -- and the order is the printed one,
#: which keeps a replay picking the same colour from the same index.
COLOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("W", "White"),
    ("U", "Blue"),
    ("B", "Black"),
    ("R", "Red"),
    ("G", "Green"),
)


@register("choose_color")
def op_choose_color(ctx: EffectContext, spec: Mapping[str, Any]):
    """"As this artifact enters, choose a color." Heraldic Banner.

    The colour twin of :func:`op_choose_type`, and deliberately the same shape
    down to the two decisions below. Stored on the permanent as a colour letter
    and read back by its own abilities through ``{"chosen_color_of": "self"}``,
    which stands wherever a literal colour letter does: a static filter's
    ``colors``, an ``add_mana``'s ``mana``, and ``grant_protection``'s
    ``from_colors``.

    **No new `DecisionKind`.** `ask_mode` already asks "pick one of these
    labels" and hands back the index, which is exactly this question -- so
    legality's `_choice_actions`, `game.apply` and the authoring verifier's
    auto-answer table all keep working unchanged. A `CHOOSE_COLOR` kind would
    have been the same decision wearing a different name, and it would have had
    to be taught to every seat that can already answer a modal spell.

    *Divergence, recorded in `rules-coverage.md` beside `choose_type`'s*: the
    printed line is "**as** this enters", a replacement that cannot be responded
    to. `zones` applies enter-replacements synchronously and cannot stop to ask,
    so this is a `self_enters` trigger instead and the colour is chosen a moment
    after the permanent arrives rather than as it does.
    """
    prompt = str(spec.get("prompt") or "Choose a color")
    picked = yield from ask_mode(
        ctx, prompt, [label for _, label in COLOR_CHOICES], ctx.controller
    )
    if not picked:
        return
    obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    if obj is not None:
        obj.chosen_color = COLOR_CHOICES[picked[0]][0]
        ctx.state.bump_chars()


@register("choose_player")
def op_choose_player(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Choose an opponent." Demonstrate, and the untargeted way to name a seat.

    The player twin of :func:`op_choose_type` and :func:`op_choose_color`: it
    asks a question and records the answer under ``as``, and every later spec
    reads it back with ``{"binding": …}`` -- the player spec `select_players`
    already had and which, until now, only a **trigger** could fill.

    That is the gap it closes. `select_players` resolves ``"opponent"`` and
    ``"each_opponent"`` to the whole set, and every spelling that names *one*
    seat -- ``target``, ``controller_of_target``, ``controller_of``,
    ``owner_of`` -- reads something a target or a trigger already produced.
    Demonstrate's copy is explicitly **not** targeted, so none of them apply,
    and at a pod ``"each_opponent"`` would hand a copy to every opponent
    instead of the one the card says to choose.

    **No new `DecisionKind`.** `ask_player` and `CHOOSE_PLAYER` have been here
    since clash, which asks the same question ("which opponent?") and hands
    back a player id -- so legality's `_choice_actions`, `game.apply` and the
    authoring verifier's auto-answer table all work unchanged. What was missing
    was never the decision; it was somewhere to *put* the answer.

    ``players`` is the pool to choose from, a player spec, defaulting to the
    opponents. It asks nobody when the pool is a single seat -- `ask_player`'s
    own short-circuit, and the reading that makes a two-player game skip a
    prompt whose answer was never in doubt.

    Nothing is bound when there is no one to choose, so ``{"binding": …}``
    resolves to no players and whatever depended on the choice does not happen.
    A card that means "and if you did not, …" says so with `if`.
    """
    pool = select_players(ctx, spec.get("players", "each_opponent"))
    pool = [pid for pid in pool if ctx.state.is_alive(pid)]
    if not pool:
        return
    prompt = str(spec.get("prompt") or "Choose a player")
    chosen = yield from ask_player(ctx, prompt, pool, ctx.controller)
    if chosen is None:
        return
    ctx.bindings[str(spec["as"])] = int(chosen)


def _creature_types(ctx: EffectContext) -> set[str]:
    """Every creature subtype the card pool actually contains."""
    found: set[str] = set()
    for card in ctx.state.registry:
        if "Creature" in card.types:
            found.update(card.subtypes)
    return found


def modal_bounds(ctx: EffectContext, spec: Mapping[str, Any]) -> tuple[int, int | None]:
    """How many modes this ``choose_mode`` asks for: ``(floor, ceiling)``.

    Four clauses, and each one is a different printed sentence:

    * ``count`` -- "choose two", the plain number, and the floor when nothing
      widens it.
    * ``all_if`` -- **entwine**: "choose both if you pay the entwine cost". A
      floor raised to every mode, because the price has already been paid.
    * ``up_to_if`` -- "if you control a commander as you cast this spell, you
      **may** choose both instead". A ceiling, not a floor: the difference is
      the word "may", and it is the whole card whenever taking one mode is the
      better line.
    * ``up_to`` -- "choose up to two", an unconditional ceiling with **no
      floor**. Taking none is a real line: Call Damage Control with an empty
      graveyard is cast for its other half, and a floor of one would force a
      mode that does nothing.

    ``None`` for the ceiling means "exactly the floor".  Lives here, beside the
    op, because three callers need the same answer -- this op for a triggered or
    nested modal, `Game._ask_modes` for the ordinary cast (601.2b), and
    `stack.free_cast_modes` for a spell cast with nobody to ask.
    """
    count = evaluate_value(ctx, spec.get("count", 1))
    modes = list(spec.get("modes") or [])
    if (gate := spec.get("all_if")) is not None and evaluate(ctx, gate):
        count = len(modes)
    up_to = None
    if (more := spec.get("up_to_if")) is not None and evaluate(ctx, more.get("condition")):
        up_to = evaluate_value(ctx, more.get("count", len(modes)))
    if spec.get("up_to"):
        up_to = count if up_to is None else max(up_to, count)
        return 0, up_to
    return max(1, count), up_to


@register("choose_mode")
def op_choose_mode(ctx: EffectContext, spec: Mapping[str, Any]):
    """A modal spell or ability: "choose one -- ...".

    Usually already answered.  Rule 601.2b picks modes as the spell is cast, and
    :meth:`Game._cast` does exactly that when the card asks a single top-level
    modal question -- the answer arrives here on ``ctx.modes``.

    The fallback still asks, and two shapes rely on it: a *triggered* ability,
    which has no cast to be asked at, and a nested ``choose_mode``, which is a
    second question that genuinely belongs to resolution.  The answer is
    consumed rather than read, so an inner one asks rather than silently reusing
    the outer one's modes.

    ``all_if`` is **entwine**: "choose both if you pay the entwine cost". The
    entwine price is an ordinary `kicker`, so legality already offers the spell
    twice and taking the second line *is* the choice rule 702.42a describes --
    which is why this forces every mode rather than offering them. Written as a
    wider `count` it would ask which two of two, a question with one answer;
    written as a `may` it would let a player pay the entwine cost and then
    decline half of what they bought.
    """
    modes = list(spec.get("modes") or [])
    if not modes:
        return
    # `Game._ask_modes` answers this for a spell whose whole effect tree is one
    # top-level `choose_mode`; this call serves a triggered ability and a nested
    # `choose_mode`, which have no cast to be asked at.
    floor, up_to = modal_bounds(ctx, spec)

    labels = [str(m.get("label") or f"Mode {i + 1}") for i, m in enumerate(modes)]

    # "Choose one **that hasn't been chosen** --" (Henrika Domnathi). The spent
    # modes are struck off the list rather than offered and then ignored: an
    # ability that offered a spent mode and did nothing would read on screen as
    # a mode that fizzled, and the whole point of the clause is that the card
    # runs out.
    #
    # Recorded as ordinary `flags` on the source, which gives the right lifetime
    # for free: `reset_permanent_state` clears them on a zone change, and 712.13a
    # says a permanent that left and came back is a new object that may choose
    # again -- the same rule flip and transform already lean on.
    once_each = bool(spec.get("once_each"))
    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    offered = list(range(len(modes)))
    if once_each and source is not None:
        offered = [i for i in offered if _mode_flag(labels[i]) not in source.flags]
        if not offered:
            # Every mode is spent. The ability still triggered and still
            # resolved; there is simply nothing left to choose.
            return

    chosen = list(ctx.modes)
    # `modes_answered` and not `chosen`: "choose up to two" is allowed to choose
    # none, and reading the empty tuple as "nobody asked yet" would ask the
    # player a second time -- on resolution, where the modes' own targets can no
    # longer be declared. Consumed alongside `modes` so a *nested* `choose_mode`
    # still asks its own question rather than inheriting this answer.
    if chosen or ctx.modes_answered:
        ctx.modes = ()
        ctx.modes_answered = False
    elif once_each:
        picked = yield from ask_mode(
            ctx,
            "Choose",
            [labels[i] for i in offered],
            ctx.controller,
            floor,
            up_to,
        )
        chosen = [offered[i] for i in picked]
    else:
        chosen = yield from ask_mode(
            ctx, "Choose", labels, ctx.controller, floor, up_to
        )

    # 700.2e: "the modes are executed in the order written on the card", not the
    # order they were clicked in -- which matters the moment one mode's effect
    # depends on another's having happened.
    for index in sorted(chosen):
        if once_each and source is not None:
            source.flags.add(_mode_flag(labels[index]))
        yield from execute(ctx, modes[index].get("effects") or [])


def _mode_flag(label: str) -> str:
    """The flag marking one mode as already taken.

    Keyed by the printed label rather than the index, so a card whose modes are
    reordered does not silently re-open a spent one.
    """
    return f"mode_chosen:{label}"


#: Guard on the "pay again?" loop, matching `may`'s and `repeat`'s. One
#: pathological seat must not hang a game.
MAX_JOIN_FORCES = 100


@register("join_forces")
def op_join_forces(ctx: EffectContext, spec: Mapping[str, Any]):
    """"Join forces — Starting with you, each player may pay any amount of mana."

    The one effect in the pool whose cost is paid by **everybody**. Every other
    cost in the engine hangs off one player: `may`'s `pay` grew a `player` for
    Rhystic Study, but it asks that player once, and join forces asks the whole
    table repeatedly and adds the answers up.

    Asked one unit at a time, in turn order starting with the controller, which
    is what the printed line says and is also the only shape the decision system
    can carry: "any amount" has no ceiling to offer as a `choose_x`, and a seat
    that stops paying is a seat that answered no.

    Order matters and is not cosmetic. Later players see what earlier ones paid,
    which is the whole politics of the card -- an implementation that asked
    simultaneously, or in seat order regardless of who cast it, would be a
    different card at a table.

    ``as`` names the binding the total lands in; the card reads it back with
    ``{"binding": …}``, the way clash reads `clash_won`.
    """
    unit = cost_from_spec(spec.get("pay") or {"mana": "{1}"})
    prompt = str(spec.get("prompt") or "Pay one more into the pool?")
    total = 0
    for pid in ctx.state.turn_order(ctx.controller):
        for _ in range(MAX_JOIN_FORCES):
            if unit is None or not can_pay(ctx.state, pid, unit, ctx.source_oid):
                break
            if not (yield from ask_yes_no(ctx, prompt, pid)):
                break
            paid = yield from pay(ctx.state, pid, unit, ctx.source_oid)
            if not paid:
                break
            total += 1
    ctx.bindings[str(spec.get("as", "joined"))] = total
    ctx.state.emit("join_forces", player=ctx.controller, source=ctx.source_oid, total=total)


@register("for_each")
def op_for_each(ctx: EffectContext, spec: Mapping[str, Any]):
    """Run a body once per matching object, binding it as ``each``."""
    oids = resolve_pool(ctx, spec.get("objects"))
    body = spec.get("effects") or []
    previous_each = ctx.bindings.get("each")
    previous_loop = ctx.loop_value
    try:
        for oid in oids:
            ctx.bindings["each"] = oid
            ctx.loop_value = oid
            yield from execute(ctx, body)
    finally:
        ctx.loop_value = previous_loop
        if previous_each is None:
            ctx.bindings.pop("each", None)
        else:
            ctx.bindings["each"] = previous_each


@register("for_each_player")
def op_for_each_player(ctx: EffectContext, spec: Mapping[str, Any]):
    """Run a body once per player, binding that player as ``each_player``.

    "**Each opponent** sacrifices a creature with the greatest mana value among
    creatures **they** control" -- Soul Shatter. `for_each` iterates objects and
    there was no player-shaped loop, so the only way to write this was one
    `sacrifice` over `{"controller": "opponent"}`, which removes *one* permanent
    across the union of every opponent's board rather than one each.

    The binding is what makes the body's selectors right: a nested selector says
    `{"controller": {"binding": "each_player"}}` and is scoped to that one
    player, so `extreme` takes their own maximum and `chooser` asks them. With
    `"opponent"` instead, `extreme` computes a single global maximum over the
    merged pool and at a pod spares whoever's best creature is smaller.

    In APNAP order, which is what `select_players` already returns.
    """
    players = select_players(ctx, spec.get("players", "each_opponent"))
    body = spec.get("effects") or []
    previous = ctx.bindings.get("each_player")
    try:
        for pid in players:
            # Elimination mid-loop: a player who has left is not still asked.
            if not ctx.state.is_alive(pid):
                continue
            ctx.bindings["each_player"] = pid
            yield from execute(ctx, body)
    finally:
        if previous is None:
            ctx.bindings.pop("each_player", None)
        else:
            ctx.bindings["each_player"] = previous


@register("repeat")
def op_repeat(ctx: EffectContext, spec: Mapping[str, Any]):
    """Run a body ``amount`` times, binding the 0-based iteration as ``iteration``."""
    times = evaluate_value(ctx, spec.get("amount", 1))
    body = spec.get("effects") or []
    previous = ctx.loop_value
    try:
        for i in range(max(0, min(times, 100))):
            ctx.loop_value = i
            yield from execute(ctx, body)
    finally:
        ctx.loop_value = previous


@register("snapshot")
def op_snapshot(ctx: EffectContext, spec: Mapping[str, Any]):
    """Capture last-known information about an object under a name.

    This is the engine's answer to LKI: rather than tracking every object's last
    known state globally, a card that needs a value *after* its target has left
    the battlefield declares the snapshot explicitly.  See ``docs/card-dsl.md``.
    """
    name = str(spec.get("as", "snapshot"))
    if "target" in spec:
        oids = ctx.target_oids(str(spec["target"]))
    else:
        oids = resolve_pool(ctx, spec.get("objects"))
    if oids:
        ctx.bindings[name] = capture_snapshot(ctx.state, oids[0])
    else:
        ctx.bindings[name] = {}


@register("noop")
def op_noop(ctx: EffectContext, spec: Mapping[str, Any]):
    """Explicitly do nothing.  Useful as an ``else`` branch."""
    return


@register("delay")
def op_delay(ctx: EffectContext, spec: Mapping[str, Any]):
    """Arrange for effects to happen at a later step.

    "At the beginning of the next end step, return it to the battlefield." The
    ordinary triggers all fire *from* an event that just happened; this is the
    other shape -- an effect that has already resolved scheduling something for
    later, with no object left to hang a trigger on.

    The bindings are captured *now*, which is the point: by the time it fires,
    the object it was about may be in another zone or gone.

    ``end_of_combat`` captures one more thing, for the same reason and at the
    same moment: *which* combat. See :func:`_scheduled_combat`.
    """
    from ..structs import DelayedTrigger

    state = ctx.state
    step = str(spec.get("step", "end_step"))
    state.delayed_triggers.append(
        DelayedTrigger(
            step=step,
            controller=ctx.controller,
            effects=tuple(spec.get("effects") or []),
            bindings=dict(ctx.bindings),
            source_oid=ctx.source_oid,
            description=str(spec.get("text") or ctx.source_name),
            turn=state.turn,
            combat=_scheduled_combat(state) if step == "end_of_combat" else None,
        )
    )


@register("delayed_trigger")
def op_delayed_trigger(ctx: EffectContext, spec: Mapping[str, Any]):
    """Install a delayed triggered ability that watches an **event** (603.7).

    "Whenever one or more creatures you control deal combat damage to one or
    more players this turn, you become the monarch." -- Forth Eorlingas!, and
    the other shape of the same rule `delay` implements. `delay` names a
    *moment* and this names a *thing that happens*; both are created by a
    resolving effect, both have no permanent to hang themselves on, and both
    capture their bindings and their controller at the instant they are made.

    So it writes the same :class:`DelayedTrigger` onto the same list, with a
    ``trigger`` spec instead of a ``step``.

    The controller matters more here than anywhere else this op is used. The
    source is a **sorcery**, which is in a graveyard before the first creature
    swings -- so "you" cannot be read off the card when the ability fires, and
    `ctx.controller` captured now is the only answer that survives. A triggered
    ability written on the card instead of installed by it would be watching
    from the graveyard, where it would either never fire (no `active_zones`) or
    fire for the rest of the game (with one), and neither is "this turn".

    ``duration`` is how long the subscription is good for, and it defaults to
    ``this_turn`` because that is what Forth Eorlingas! and every card of its
    shape print. The other value is Palace Jailer's, whose delayed ability is the
    end of a duration written on a *different* effect -- "exile it **until** an
    opponent becomes the monarch" -- so it fires once and has to outlive the
    turn, since the crown may not move for six of them. See
    :data:`~automtg.engine.structs.DELAYED_DURATIONS`; the two values are read at
    exactly two places, `triggers._arm_delayed` and `turn._cleanup_step`.
    """
    from ..carddef import TriggerSpec
    from ..structs import DelayedTrigger

    trigger = spec.get("trigger") or {}
    state = ctx.state
    state.delayed_triggers.append(
        DelayedTrigger(
            step="",
            controller=ctx.controller,
            effects=tuple(spec.get("effects") or []),
            bindings=dict(ctx.bindings),
            source_oid=ctx.source_oid,
            description=str(spec.get("text") or ctx.source_name),
            turn=state.turn,
            trigger=TriggerSpec(
                event=str(trigger.get("event")),
                controller=str(trigger.get("controller", "you")),
                condition=dict(trigger["condition"]) if trigger.get("condition") else None,
            ),
            duration=str(spec.get("duration", "this_turn")),
        )
    )


def _scheduled_combat(state: GameState) -> int:
    """Which combat an "at end of combat" delay belongs to (rule 603.7).

    Every other delay step happens once a turn, so the step's *name* is enough
    to say when it is due. A combat phase is not: `extra_combat` gives a turn
    two or three of them, and Flamerush Rider's "exile the token at end of
    combat" has to end the token at the end of the combat it attacked in --
    otherwise the copy lives through the postcombat main and attacks again in
    the extra combat, which is the precise thing the printed line stops.

    Two cases, and they are the same sentence read at two moments:

    - **Inside a combat phase** -- the delay was created by something that
      happened in this combat, so it is this combat's end.
    - **Anywhere else** -- a main phase, an upkeep, or the end of combat step
      itself, where `combat` has already been cleared by `combat.end_combat`.
      There is no combat to end, so it is the *next* one's, whether that turns
      out to be an extra combat later this turn or the first combat of a later
      turn. Which is also the right answer for a delay scheduled during an
      end of combat step: that step's own firing has been and gone.
    """
    return state.combat_number if state.combat is not None else state.combat_number + 1


@register("extra_combat")
def op_extra_combat(ctx: EffectContext, spec: Mapping[str, Any]):
    """"After this phase, there is an additional combat phase" (506.1).

    ``amount`` is how many, for Fury of the Horde's "two additional combat
    phases"; ``extra_main`` adds the additional **main** phase that Relentless
    Assault, Resurgence and Savage Beating print after each combat, and Combat
    Celebrant does not.

    Queued rather than applied, because the printed timing is "after this phase"
    and this op resolves *inside* the phase it extends -- from a sorcery in a main
    phase, or from a trigger in the declare-attackers step. So it hands the
    phases to the turn and the step walk enters them at the boundary; see
    `turn._after_phase`.

    Deliberately takes **no player**: a phase belongs to the turn, not to a seat.
    Seize the Day is an instant, and cast on somebody else's turn its extra
    combat is that player's, which is both what the rules say and what falls out
    of a queue read by the turn. `loader` refuses a `player` here rather than
    accepting one and ignoring it.
    """
    from ..turn import grant_extra_phases

    times = max(0, min(evaluate_value(ctx, spec.get("amount", 1)), 10))
    kinds: list[str] = []
    for _ in range(times):
        kinds.append("combat")
        if spec.get("extra_main"):
            kinds.append("main")
    grant_extra_phases(ctx.state, kinds)
