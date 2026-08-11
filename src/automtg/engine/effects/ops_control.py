"""Control-flow ops: conditionals, loops, optional effects, modes, snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..carddef import Cost
from ..costs import can_pay, pay
from ..zones import snapshot as capture_snapshot
from . import execute, register
from .conditions import evaluate
from .context import EffectContext, ask_mode, ask_yes_no
from .selectors import resolve_pool, select_players
from .values import evaluate_value

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
    cost = cost_from_spec(spec.get("pay"))

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
    """
    modes = list(spec.get("modes") or [])
    if not modes:
        return
    count = evaluate_value(ctx, spec.get("count", 1))
    chosen = list(ctx.modes)
    if chosen:
        ctx.modes = ()
    else:
        labels = [str(m.get("label") or f"Mode {i + 1}") for i, m in enumerate(modes)]
        chosen = yield from ask_mode(ctx, "Choose", labels, ctx.controller, max(1, count))
    for index in chosen:
        yield from execute(ctx, modes[index].get("effects") or [])


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
    """
    from ..structs import DelayedTrigger

    state = ctx.state
    state.delayed_triggers.append(
        DelayedTrigger(
            step=str(spec.get("step", "end_step")),
            controller=ctx.controller,
            effects=tuple(spec.get("effects") or []),
            bindings=dict(ctx.bindings),
            source_oid=ctx.source_oid,
            description=str(spec.get("text") or ctx.source_name),
            turn=state.turn,
        )
    )
