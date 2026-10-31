"""Control-flow ops: conditionals, loops, optional effects, modes, snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..carddef import Cost, TriggerSpec
from ..costs import can_pay, mana_sources, pay
from ..mana import OTHER_PAYMENT, max_affordable_times, max_affordable_x
from ..player_statics import forced_discard_or_sacrifice_barred
from ..primitives import change_control
from ..structs import DelayedTrigger
from ..turn import grant_extra_phases
from ..zones import snapshot as capture_snapshot
from . import execute
from .conditions import evaluate
from .context import EffectContext, ask_mode, ask_player, ask_x, ask_yes_no
from .modes import (
    _mode_flag,
    chosen_at_random,
    modal_bounds,
    mode_labels,
    per_turn,
    pick_at_random,
    record_per_turn,
    unspent,
)
from .registry import register
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

    ``x`` is "you may pay {X}, **where X is less than or equal to** the amount
    of life you gained. If you do, draw X cards" -- Well of Lost Dreams. The
    ``pay`` carries ``{X}``; ``x.max`` is the printed ceiling, a value
    expression; ``x.as`` binds the announced X for the effects to read back
    with ``{"binding": …}``. After the yes, the player announces X from 0 up to
    the smaller of the ceiling and what they can actually pay -- `ask_x`, the
    same question a spell's X is, so no new decision kind -- and exactly that
    much is charged. See :func:`_announce_x`.

    ``any_amount`` is "you may pay **any amount of {R}**. When you do, …" --
    Leyline Tyrant. The ``pay`` is one coloured symbol; after the yes the
    player announces how many times to pay it, from 1 up to what they can
    actually pay *in that symbol*, and ``any_amount.as`` binds the count for
    the effects (typically a ``reflexive_trigger``) to read. Paying none is not
    paying, so 0 is the no and is never offered after the yes. See
    :func:`_announce_amount`.

    A ``pay_life`` value expression is "you may pay **that much** life. If you
    do, draw that many cards" -- Niv-Mizzet, Ghost Counsel. It is read here, in
    this effect's context, so ``{"binding": "amount"}`` is the life the trigger
    saw gained, and fixed to an integer before the affordability check: 119.4
    refuses more life than the player has, and 0 life is always payable.
    """

    players = select_players(ctx, spec.get("player", "you"))
    chooser = players[0] if players else ctx.controller
    prompt = str(spec.get("prompt") or ctx.source_name or "Optional effect")
    condition = spec.get("condition")
    pay_spec = spec.get("pay")
    x_spec = spec.get("x")
    amount_spec = spec.get("any_amount")
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

    life_spec = cost.pay_life if cost is not None and isinstance(cost.pay_life, Mapping) else None

    # The same guard `repeat` uses: one pathological board must not hang a game.
    for _ in range(100):
        if cost is not None and life_spec is not None:
            # "You may pay **that much** life" -- Niv-Mizzet, Ghost Counsel. A
            # value-expression life price is read here, in the resolving
            # effect's context, because that is where the trigger's bindings
            # live: `costs.life_cost` builds a bare context of its own and would
            # read `{"binding": "amount"}` as 0, a free draw. Fixed to an
            # integer before `can_pay`, so the check and the charge see one
            # price (118.4, 119.4: no more than you have; 0 is always paid).
            # Inside the loop, so a `repeat` re-reads it each time.
            cost = replace(cost, pay_life=max(0, int(evaluate_value(ctx, life_spec))))
        # A resolving ability's price is neither a cast nor an activation, so
        # restricted mana pays it only when its `other` half says so (ward and
        # the Vibranium token, against "spend this only to cast" mana).
        if cost is not None and not can_pay(
            ctx.state, chooser, cost, ctx.source_oid, purpose=OTHER_PAYMENT
        ):
            yield from execute(ctx, spec.get("else") or [])
            return
        if (
            cost is not None
            and (cost.sacrifice or cost.discard or cost.discard_self)
            and forced_discard_or_sacrifice_barred(ctx.state, chooser, ctx.controller)
        ):
            # Tamiyo, Collector of Tales: "…can't cause you to discard cards or
            # sacrifice permanents." An opponent's "unless you sacrifice" (Torment
            # of Hailfire) would be that opponent's ability causing the
            # sacrifice, so it is not offered and the punishment lands.
            yield from execute(ctx, spec.get("else") or [])
            return
        if not (yield from ask_yes_no(ctx, prompt, chooser)):
            yield from execute(ctx, spec.get("else") or [])
            return
        x = 0
        if cost is not None and x_spec is not None:
            x = yield from _announce_x(ctx, chooser, cost, x_spec)
        charged = cost
        count = 0
        if cost is not None and amount_spec is not None:
            count = yield from _announce_amount(ctx, chooser, cost, amount_spec)
            if count <= 0:
                # The board changed between `can_pay` and the question: not
                # even one is payable now, and paying none is not paying.
                yield from execute(ctx, spec.get("else") or [])
                return
            charged = replace(cost, mana=cost.mana.scaled(count))
        if charged is not None:
            paid = yield from pay(
                ctx.state, chooser, charged, ctx.source_oid, x=x, purpose=OTHER_PAYMENT
            )
            if not paid:
                # `can_pay` said yes a moment ago, so this is the board having
                # changed underneath us. "If you do" is false, so the effects
                # must not run -- the same contract `else` has for a refusal.
                yield from execute(ctx, spec.get("else") or [])
                return
        if name := spec.get("as"):
            # "Then Snort deals 5 damage to each opponent **who discarded their
            # hand this way**." The set of players who said yes, accumulated
            # across a `for_each_player` loop and read back with the
            # `{"binding": …}` player spec.
            #
            # Recorded here, after the cost is paid and before the effects run,
            # so it means "accepted" and not "was asked". And it is the
            # *acceptance* rather than anything the effects moved, which is the
            # whole point on this card: a player with an empty hand who takes
            # the free draw-five has discarded their hand -- of nothing -- and
            # is still one of the opponents Snort burns. Deriving the set from
            # the cards discarded would quietly spare exactly the player the
            # card is aimed at.
            previous = ctx.bindings.get(str(name))
            seats = list(previous) if isinstance(previous, list) else []
            if chooser not in seats:
                seats.append(chooser)
            ctx.bindings[str(name)] = seats
        if x_spec is not None:
            # After the payment, so it is the X that was *paid*: "if you do,
            # draw X cards" never sees a number nobody paid for.
            ctx.bindings[str(x_spec["as"])] = x
        if amount_spec is not None:
            ctx.bindings[str(amount_spec["as"])] = count
        yield from execute(ctx, spec.get("effects") or [])
        if not spec.get("repeat") or not evaluate(ctx, condition):
            return


def _announce_x(ctx: EffectContext, chooser: int, cost: Cost, x_spec: Mapping[str, Any]):
    """Ask how big X is for an optional ``{X}`` payment made mid-resolution.

    The ceiling is the **smaller** of two numbers, and each alone is a wrong
    card. The printed one (``x.max``) is the rule the card makes -- "less than
    or equal to the amount of life you gained" -- and without it a Well pays
    for ten cards off a one-life gain. What the player can pay is the rule
    118.3 makes, and without it a prompt offers an X the payment then fails.

    **A card may print no ceiling**, and then 118.3 is the only bound there is:
    Decree of Justice's "you may pay {X}. If you do, create X 1/1 white Soldier
    creature tokens" names no maximum, and inventing one would be writing a rule
    the card does not have -- a number that then rides into `max_affordable_x`
    as the probe `cap` and silently becomes the card's real ceiling. With `max`
    absent the affordability probe runs under its own default cap instead, which
    is the engine's guard against a pathological board rather than anything the
    card claims.

    Read when the question is asked, after the yes, because mana abilities
    activated in between are exactly what change the second number. A ceiling
    of 0 asks nothing (`ask_x`'s own short-circuit) and charges {0}.
    """

    printed = x_spec.get("max")
    pool = ctx.state.players[chooser].mana_pool.spendable(OTHER_PAYMENT)
    sources = mana_sources(ctx.state, chooser, purpose=OTHER_PAYMENT)
    if printed is None:
        ceiling = None
        affordable = max_affordable_x(cost.mana, pool, sources)
    else:
        ceiling = max(0, evaluate_value(ctx, printed))
        affordable = max_affordable_x(cost.mana, pool, sources, cap=ceiling)
    prompt = str(x_spec.get("prompt") or f"Choose X for {ctx.source_name or 'the payment'}")
    offered = affordable if ceiling is None else min(ceiling, affordable)
    return (
        yield from ask_x(
            ctx, prompt, max(0, offered), chooser, per_point=cost.mana.x_count
        )
    )


def _announce_amount(
    ctx: EffectContext, chooser: int, cost: Cost, amount_spec: Mapping[str, Any]
):
    """Ask how many times to pay the one symbol of a "pay any amount of {R}".

    The ceiling is 118.3's and nothing else: what the player can pay in *that
    symbol*, read by `max_affordable_times` off the pool -- red mana a
    `mana_retention` static kept counts, which is how Leyline Tyrant is played
    -- and the sources that can still make it. No card prints a maximum.

    The floor is 1, because the yes was already the "pay" and paying none is
    not paying: a "when you do" must not fire off {0}. With exactly one
    payable, `ask_x` does not ask. Read after the yes, as `_announce_x` is,
    because mana abilities activated in between change the ceiling.
    """

    pool = ctx.state.players[chooser].mana_pool.spendable(OTHER_PAYMENT)
    sources = mana_sources(ctx.state, chooser, purpose=OTHER_PAYMENT)
    affordable = max_affordable_times(cost.mana, pool, sources)
    if affordable <= 0:
        return 0
    prompt = str(
        amount_spec.get("prompt")
        or f"How much {cost.mana.text or 'mana'} to pay for {ctx.source_name or 'the effect'}?"
    )
    return (yield from ask_x(ctx, prompt, affordable, chooser, min_x=1))


#: How many creature types a "choose a creature type" prompt will offer.
#:
#: The rules say *any* creature type. The pool's own subtypes are the finite,
#: honest version of that: a type no card in the game has is a choice with no
#: consequence, and enumerating the full Comprehensive Rules list would make the
#: prompt unusable without making any card play differently.
MAX_TYPE_CHOICES = 400

#: The six card types rule 110.4a calls **permanent types**, in the printed
#: order a card lists them.
#:
#: A fixed list, not a survey of the pool the way `_creature_types` is, and for
#: `COLOR_CHOICES`' reason: there are exactly six and every one is always a
#: legal answer, so there is nothing for the board to narrow -- and a fixed
#: order keeps a replay picking the same type from the same index.
#:
#: Battle and Planeswalker are listed even though neither is modelled: they are
#: legal answers at a real table, the rule names six, and a list that quietly
#: held four would make a card that offers the wrong choices rather than one
#: that refuses.
PERMANENT_TYPE_CHOICES: tuple[str, ...] = (
    "Artifact",
    "Battle",
    "Creature",
    "Enchantment",
    "Land",
    "Planeswalker",
)

#: Every card type rule 205.2a lists, in its printed (alphabetical) order --
#: "choose a **card** type" (Serra's Emissary), the wider axis beside
#: `PERMANENT_TYPE_CHOICES`.
#:
#: Instant, Sorcery and Kindred are the three it adds, and they are the reason
#: the axis exists: "protection from instants" is the commonest answer on the
#: card that motivated it, and a list without them offers the wrong choices.
#: Naming Kindred protects from the Kindred cards (308), Eldrazi Conscription
#: among them.
CARD_TYPE_CHOICES: tuple[str, ...] = (
    "Artifact",
    "Battle",
    "Creature",
    "Enchantment",
    "Instant",
    "Kindred",
    "Land",
    "Planeswalker",
    "Sorcery",
)

#: The fixed-list axes of `choose_type`: ``of`` -> (options, default prompt).
#: Both write `GameObject.chosen_card_type`; only the creature-type axis is
#: surveyed from the pool and writes `chosen_type`.
_CARD_TYPE_AXES: dict[str, tuple[tuple[str, ...], str]] = {
    "permanent_type": (PERMANENT_TYPE_CHOICES, "Choose a permanent type"),
    "card_type": (CARD_TYPE_CHOICES, "Choose a card type"),
}


@register("choose_type")
def op_choose_type(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "As this artifact enters, choose a creature type." Vanquisher's Banner.

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
    # "Choose a **permanent** type" (Creeping Renaissance) is the same question
    # on a different axis, so it is a parameter rather than a second op: the
    # decision, the prompt, the storage and the read-back all have the same
    # shape, and two ops would be two copies of them.
    #
    # It writes a **separate slot**, though. `chosen_type` holds a creature type
    # and `chosen_card_type` a card type; one field would make "of the chosen
    # type" ambiguous at every reader, and a reader that guessed wrong would
    # match nothing silently.
    #
    # "Choose a **card** type" (Serra's Emissary) is the same again over the
    # nine types of 205.2a, and writes the same slot: a permanent type *is* a
    # card type, so every reader of `chosen_card_type` reads either answer.
    axis = _CARD_TYPE_AXES.get(str(spec.get("of", "creature_type")))
    if axis is not None:
        choices = list(axis[0])
        prompt = str(spec.get("prompt") or axis[1])
        picked = yield from ask_mode(ctx, prompt, choices, ctx.controller)
        if not picked:
            return
        obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
        if obj is not None:
            obj.chosen_card_type = choices[picked[0]]
            ctx.state.bump_chars()
        return

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
    """ "As this artifact enters, choose a color." Heraldic Banner.

    The colour twin of :func:`op_choose_type`, and deliberately the same shape
    down to the two decisions below. Stored on the permanent as a colour letter
    and read back by its own abilities through ``{"chosen_color_of": "self"}``,
    which stands wherever a literal colour letter does: a static filter's
    ``colors``, an ``add_mana``'s ``mana``, and the ``from_colors`` of
    ``grant_protection`` and of the ``protection`` static.

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
    picked = yield from ask_mode(ctx, prompt, [label for _, label in COLOR_CHOICES], ctx.controller)
    if not picked:
        return
    obj = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    if obj is not None:
        obj.chosen_color = COLOR_CHOICES[picked[0]][0]
        ctx.state.bump_chars()


#: The label of the one answer that is not a card the chooser owns: "a name no
#: card in your library has". Bound as the empty string, which no selector matches.
OTHER_CARD_NAME = "Another card name"


@register("choose_card_name")
def op_choose_card_name(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Choose a nonland card name" -- Tamiyo, Collector of Tales.

    Binds the chosen name, a string, under ``as``; a later selector reads it as
    ``{"name": {"binding": …}}``. ``types`` / ``not_types`` narrow which names
    may be chosen ("a **nonland** card name" is ``not_types: ["Land"]``),
    judged on the printed card.

    **Which names are offered.** At a table any card name ever printed may be
    named, but the only thing a name can do here is match cards the chooser
    owns: the card it is compared against is in their own library, and a
    library holds only its owner's cards (400.3). So every distinct name among
    the cards the chooser owns, in every zone, is offered -- the chooser knows
    their own deck list, so this shows nothing hidden -- plus
    :data:`OTHER_CARD_NAME`, which stands for every other name ever printed:
    they all have the same outcome, matching nothing. That is a real choice
    (Tamiyo naming a card that is not there mills all four), and leaving it out
    would take it from the player whenever every name they own might be on top.

    **No new `DecisionKind`.** `ask_mode` already asks "pick one of these
    labels", exactly as `choose_type` and `choose_color` use it, tagged
    ``choose_card_name`` so a seat can tell a name from a mode.
    """
    state = ctx.state
    want = set(spec.get("types") or ())
    unwanted = set(spec.get("not_types") or ())
    names: set[str] = set()
    for obj in state.objects.values():
        if obj.owner != ctx.controller or obj.is_token:
            continue
        card = state.card_of(obj)
        types = set(card.types)
        if want and not (want & types):
            continue
        if unwanted & types:
            continue
        names.add(card.name)
    labels = [*sorted(names), OTHER_CARD_NAME]
    prompt = str(spec.get("prompt") or "Choose a card name")
    picked = yield from ask_mode(ctx, prompt, labels, ctx.controller, purpose="choose_card_name")
    chosen = labels[picked[0]] if picked else OTHER_CARD_NAME
    ctx.bindings[str(spec["as"])] = "" if chosen == OTHER_CARD_NAME else chosen


@register("choose_player")
def op_choose_player(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Choose an opponent." Demonstrate, and the untargeted way to name a seat.

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


#: "Choose left or right." The answer's labels, in the order `rotate_control`
#: asks them. Left is the next seat in turn order (play passes to the left).
DIRECTIONS = ("left", "right")


def neighbour(state: GameState, pid: int, direction: str) -> int:
    """The next living player to ``pid``'s left or right.

    Left is the seat that takes the next turn (`state.next_alive_index`); right
    is the one before. A player who has left the game is skipped (800.4a), and a
    lone survivor is their own neighbour.
    """
    n = state.num_players
    step = 1 if direction == "left" else -1
    for offset in range(1, n + 1):
        candidate = (pid + step * offset) % n
        if state.is_alive(candidate):
            return candidate
    return pid


@register("rotate_control")
def op_rotate_control(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Choose left or right. Each player gains control of all nonland
    permanents other than Aminatou controlled by the next player in the chosen
    direction." Aminatou, the Fateshifter's -6.

    One op rather than `for_each_player` around `gain_control`, because the
    exchange is **simultaneous**: written as a loop, the first player takes their
    neighbour's board, and the second player's `gain_control` then re-reads a
    neighbour who now controls *two* boards and takes both -- the rotation
    cascades round the table and the last seat ends up with everything. Here
    the pool is resolved once, every permanent's current controller is read
    before any control moves, and then each permanent passes to the player
    whose neighbour in the chosen direction controlled it.

    ``objects`` is the selector over what rotates (Aminatou: ``not_types:
    ["Land"]`` with ``exclude_self``); nothing outside it moves. ``direction``
    fixes the answer for a card that prints one; without it the controller is
    asked, with ``purpose: "choose_direction"`` and the seat each direction
    takes from, and a table where both directions name the same neighbour (a
    duel) is not asked at all.

    `change_control` is the one primitive, so every permanent that moves is
    summoning sick for its new controller (302.6) and leaves combat (506.4).
    The change is permanent -- the printed line has no duration.
    """
    state = ctx.state
    living = state.alive()
    pool = resolve_pool(ctx, spec.get("objects"))
    # Who controls what, read before anything moves.
    before = [(oid, state.objects[oid].controller) for oid in pool if oid in state.objects]
    direction = spec.get("direction")
    if direction is None:
        takes_from = {d: neighbour(state, ctx.controller, d) for d in DIRECTIONS}
        if len({takes_from[d] for d in DIRECTIONS}) == 1:
            direction = DIRECTIONS[0]
        else:
            picked = yield from ask_mode(
                ctx,
                str(spec.get("prompt") or "Choose left or right"),
                [d.capitalize() for d in DIRECTIONS],
                ctx.controller,
                extra={
                    "purpose": "choose_direction",
                    "takes_from": [takes_from[d] for d in DIRECTIONS],
                },
            )
            direction = DIRECTIONS[picked[0] if picked else 0]
    # Each player gains what their neighbour in that direction controlled, so a
    # permanent controlled by Q goes to the player whose neighbour is Q.
    receiver = {neighbour(state, pid, str(direction)): pid for pid in living}
    for oid, was in before:
        if was in receiver:
            change_control(state, oid, receiver[was], source=ctx.source_oid)


@register("distribute_control_among_opponents")
def op_distribute_control_among_opponents(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "For each of those permanents, choose a different opponent. Each opponent
    gains control of the permanent for which they were chosen." Dack Fayden,
    Helping Hand.

    A pairing, which neither existing control op can say: `gain_control` gives
    a whole pool to one player, so `for_each` around it hands every permanent
    to the same opponent or loops with no way to say "a *different* one"; and
    `rotate_control` passes boards one seat round the table, with no choice of
    who gets what.

    **No new `DecisionKind`.** One `ask_player` per permanent, asked of the
    controller (who makes every choice the sentence names) over the opponents
    not yet chosen. Asked in turn, that reaches every pairing: each permanent's
    question names the seats still free, and with fewer permanents than
    opponents the seats never picked are the opponents who get nothing. The
    last question is forced when one seat is left, `ask_player`'s own
    short-circuit. Once every opponent has been chosen, a further permanent
    has no different opponent to go to and stays where it is (609.3: do as
    much as possible).

    Every choice is made **before** any control moves, then each permanent
    passes through `change_control` -- permanently, the printed line has no
    duration -- so each is summoning sick for its new controller (302.6) and
    leaves combat (506.4). A permanent that left the battlefield in the
    meantime is skipped, and is not asked about.

    ``objects`` names the permanents, in the order asked -- Dack's is
    ``{"binding": …}`` over what `reveal_until` put onto the battlefield.
    """
    state = ctx.state
    pool = [
        oid
        for oid in resolve_pool(ctx, spec.get("objects"))
        if (obj := state.objects.get(oid)) is not None and obj.on_battlefield
    ]
    free = list(ctx.opponents())
    pairs: list[tuple[int, int]] = []
    for oid in pool:
        if not free:
            break
        chosen = yield from ask_player(
            ctx,
            f"Choose the opponent who gains control of {ctx.name_of(oid)}",
            free,
            ctx.controller,
        )
        if chosen is None:
            break
        free.remove(chosen)
        pairs.append((oid, chosen))
    for oid, pid in pairs:
        change_control(state, oid, pid, source=ctx.source_oid)


def _creature_types(ctx: EffectContext) -> frozenset[str]:
    """Every creature subtype the card pool actually contains.

    The survey lives on the registry, which is immutable and can therefore cache
    it: `text_change` asks the same question when it builds its candidate list,
    and two walks of 2,600 cards to reach the same answer is one too many.
    """
    return ctx.state.registry.creature_types()


@register("choose_mode")
def op_choose_mode(ctx: EffectContext, spec: Mapping[str, Any]):
    """A modal spell or ability: "choose one -- ...".

    Usually already answered.  Rule 601.2b picks modes as the spell is cast, and
    :meth:`Game._cast` does exactly that when the card asks a single top-level
    modal question -- the answer arrives here on ``ctx.modes``.

    A *triggered* ability is answered early too: 603.3d puts its modes at the
    moment it goes on the stack, which `stack.push_triggered_ability` does --
    and it has to, because that is the only moment a mode-owned target could be
    declared in.

    The fallback still asks, and one shape relies on it: a nested
    ``choose_mode``, which is a second question that genuinely belongs to
    resolution.  The answer is consumed rather than read, so an inner one asks
    rather than silently reusing the outer one's modes.

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

    labels = mode_labels(modes)

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
    # "**Target player** adds one mana of any color" -- The Warring Triad. The
    # player who adds the mana is the one who picks its colour, so the question
    # goes to them and not to us. `ask_mode` always took an arbitrary chooser,
    # the way `ask_objects` did for Fact or Fiction's pile-splitter, so this
    # costs nothing but the resolution. Absent, it is our own choice as before.
    #
    # `carddef.asks_another_player` keeps such a mode out of `cast_time_modes`,
    # so it is never pre-answered by the controller at 601.2b/602.2b time and
    # always reaches the ask below.
    chooser = ctx.controller
    if (who := spec.get("chooser")) is not None:
        picked_players = select_players(ctx, who)
        if not picked_players:
            # No player to ask -- the target is gone. Nothing is chosen and
            # nothing happens, rather than the controller quietly deciding.
            return
        chooser = picked_players[0]
    source = ctx.state.objects.get(ctx.source_oid) if ctx.source_oid is not None else None
    # "…that hasn't been chosen **this turn**" (Parapet Thrasher) is
    # `once_each: "turn"`: the same strike-off, against `TurnLedger.modes_chosen`
    # instead of the source's flags, so the modes come back next turn.
    per_turn_modes = per_turn(spec)
    offered = list(range(len(modes)))
    if once_each and source is not None:
        offered = unspent(ctx.state, ctx.source_oid, spec, labels, offered)
        # Only when there is still a question to ask. A trigger's modes were
        # answered as it went on the stack, and under "this turn" they were
        # spent there too, so the answer being resolved is itself struck off
        # by now -- returning here would drop the very mode that was chosen.
        if not offered and not (ctx.modes or ctx.modes_answered):
            # Every mode is spent. The ability still triggered and still
            # resolved; there is simply nothing left to choose.
            return

    # "Choose up to five {P} worth of modes. You may choose the same mode more
    # than once." -- Season of Weaving. A *budget*, not a count: each mode has a
    # price in paws and the selection is a multiset whose prices sum within it.
    #
    # `count`/`up_to` cannot say it and the near miss is far stronger than the
    # card: `{"up_to": true, "count": 5}` permits five copies of the three-paw
    # mode, which is a board wipe repeated five times for six mana.
    if spec.get("budget") is not None:
        yield from _choose_within_budget(ctx, spec, modes, labels, chooser)
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
    elif chosen_at_random(ctx, spec):
        # "Choose one at random" -- a nested one, or one nobody answered
        # earlier. Off the seeded `state.rng`, so a replay picks the same.
        chosen = pick_at_random(ctx.state, offered, min(floor, len(offered)))
        record_per_turn(ctx.state, ctx.source_oid, spec, labels, chosen)
    elif once_each:
        picked = yield from ask_mode(
            ctx,
            "Choose",
            [labels[i] for i in offered],
            chooser,
            floor,
            up_to,
        )
        chosen = [offered[i] for i in picked]
        # Spent as it is chosen. A pre-answered `ctx.modes` was spent where it
        # was asked, by `stack._choose_trigger_modes`.
        record_per_turn(ctx.state, ctx.source_oid, spec, labels, chosen)
    else:
        chosen = yield from ask_mode(ctx, "Choose", labels, chooser, floor, up_to)

    # 700.2e: "the modes are executed in the order written on the card", not the
    # order they were clicked in -- which matters the moment one mode's effect
    # depends on another's having happened.
    for index in sorted(chosen):
        if once_each and not per_turn_modes and source is not None:
            source.flags.add(_mode_flag(labels[index]))
        yield from execute(ctx, modes[index].get("effects") or [])


#: Guard on the budget loop, matching `join_forces`' and `may`'s. A mode priced
#: at zero would otherwise be choosable for ever.
MAX_BUDGET_PICKS = 32


def _choose_within_budget(ctx: EffectContext, spec, modes, labels, chooser: int):
    """Pick a multiset of modes whose prices fit inside a budget.

    Asked one mode at a time rather than as a single multi-select, because the
    set of *affordable* modes shrinks as the budget is spent: after three paws
    of a five-paw budget, only the one-paw and two-paw modes may still be taken,
    and offering the three-paw one would be offering a choice that cannot be
    paid for.

    Repeats are the point -- "you may choose the same mode more than once" -- so
    a taken mode stays on the list while it is still affordable.

    700.2e still applies at the end: the modes run in printed order, not the
    order they were picked, however many times each was taken.
    """
    budget = evaluate_value(ctx, spec.get("budget", 0))
    prices = [max(0, evaluate_value(ctx, m.get("cost", 1))) for m in modes]
    picked: list[int] = []
    for _ in range(MAX_BUDGET_PICKS):
        affordable = [i for i, price in enumerate(prices) if price <= budget]
        if not affordable:
            break
        # A floor of zero: "up to five paws worth" allows stopping at any point,
        # including immediately, and `ask_mode` returning nothing is that.
        answer = yield from ask_mode(
            ctx,
            f"Choose a mode ({budget} left)",
            [labels[i] for i in affordable],
            chooser,
            0,
            1,
        )
        if not answer:
            break
        index = affordable[answer[0]]
        picked.append(index)
        budget -= prices[index]

    for index in sorted(picked):
        yield from execute(ctx, modes[index].get("effects") or [])


#: Guard on the "pay again?" loop, matching `may`'s and `repeat`'s. One
#: pathological seat must not hang a game.
MAX_JOIN_FORCES = 100


@register("join_forces")
def op_join_forces(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Join forces — Starting with you, each player may pay any amount of mana."

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
            if unit is None or not can_pay(
                ctx.state, pid, unit, ctx.source_oid, purpose=OTHER_PAYMENT
            ):
                break
            if not (yield from ask_yes_no(ctx, prompt, pid)):
                break
            paid = yield from pay(ctx.state, pid, unit, ctx.source_oid, purpose=OTHER_PAYMENT)
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


@register("repeat_while")
def op_repeat_while(ctx: EffectContext, spec: Mapping[str, Any]):
    """Run a body, then run it again for as long as ``condition`` still holds.

    "Target opponent mills two cards. If two nonland cards that share a color
    were milled this way, **repeat this process**" -- Sphinx's Tutelage.

    A **do-while**: the condition is evaluated *after* each pass, because the
    printed sentence is a decision about repeating and not a guard on starting.
    The body always runs once, which on this card is the mill the trigger is
    about.

    `repeat` cannot express it. It evaluates `amount` once, above the loop, so
    the count has to be knowable before the body runs -- and here there is no
    number to write at all: how many times depends on what each mill turns up.

    `may` with `repeat: true` is the language's only other unbounded loop and is
    a **player-choice** loop: it asks the controller yes/no before every pass and
    stops at the first no, and its `condition` only gates whether the question is
    asked. Sphinx's Tutelage never asks anybody, so a `may` spelling is a
    different and strictly weaker card -- its controller could decline, and the
    opponent's mill would be optional.

    ``reset`` names the bindings cleared before each pass, and it is not a
    convenience. `mill`'s `as` binding deliberately **accumulates** (``earlier +
    milled``), so without it the second pass would ask the colour question over
    all four cards milled so far rather than over the two this pass produced --
    and "milled this way" is per repetition. Cleared before the first pass too,
    so a binding of the same name written earlier in the same resolution cannot
    leak in.

    The same 100-iteration guard `repeat` and `may` use: one pathological board
    must not hang a game.
    """
    condition = spec.get("condition")
    body = spec.get("effects") or []
    reset = [str(name) for name in (spec.get("reset") or ())]
    previous = ctx.loop_value
    try:
        for i in range(100):
            ctx.loop_value = i
            for name in reset:
                ctx.bindings.pop(name, None)
            yield from execute(ctx, body)
            if not evaluate(ctx, condition):
                return
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

    ``your_turn`` is "at the beginning of **your** next end step" as against "at
    the beginning of the next end step". Every seat has an end step, so the step
    name alone cannot tell the two apart, and the gap only opens when the delay
    is created on somebody else's turn -- which is the ordinary line of play for
    an instant-speed ability, and the reason the word is printed at all.
    """

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
            your_turn=bool(spec.get("your_turn", False)),
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
    :data:`~commanderblitz.engine.structs.DELAYED_DURATIONS`; the two values are read at
    exactly two places, `triggers._arm_delayed` and `turn._cleanup_step`.

    ``this_combat`` is Love on the Battlefield's "…deals combat damage to a
    player **this combat**", ended by `combat.end_combat`. Outside a combat
    phase there is no "this combat" for it to belong to, so it installs
    nothing rather than waiting for whichever combat comes next.
    """

    trigger = spec.get("trigger") or {}
    state = ctx.state
    duration = str(spec.get("duration", "this_turn"))
    if duration == "this_combat" and state.combat is None:
        return
    # "Choose target creature you control. Whenever **that creature** deals
    # combat damage…" -- resolved now, to an oid, because the spell that is
    # saying it will be in a graveyard before the first blow lands and there
    # would be nothing left to resolve it against. `choose_objects` is not
    # reached: the object is already chosen, as a target or a binding, and this
    # only reads which.
    subject_oids = None
    if (subject := trigger.get("subject")) is not None:
        chosen = resolve_pool(ctx, subject)
        if not chosen:
            # The target is gone by resolution (608.2b took it), so there is no
            # "that creature" to watch and the clause does nothing -- which is
            # what the printed card says rather than a reason to watch
            # everything.
            return
        # Every object it resolved to: "whenever **either** of those
        # creatures" (Tamiyo, Field Researcher) is scoped to the whole set, and
        # keeping only the first would silently watch one of two.
        subject_oids = tuple(dict.fromkeys(chosen))
    # "…deals combat damage **to Vraska**" -- the permanent being hit, named the
    # same way and resolved at the same moment, for the same reason.
    recipient_oids = None
    if (recipient := trigger.get("recipient")) is not None:
        hit = resolve_pool(ctx, recipient)
        if not hit:
            return
        recipient_oids = tuple(dict.fromkeys(hit))
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
            subject_oids=subject_oids,
            recipient_oids=recipient_oids,
            duration=duration,
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
    """ "After this phase, there is an additional combat phase" (506.1).

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

    times = max(0, min(evaluate_value(ctx, spec.get("amount", 1)), 10))
    kinds: list[str] = []
    for _ in range(times):
        kinds.append("combat")
        if spec.get("extra_main"):
            kinds.append("main")
    grant_extra_phases(ctx.state, kinds)
