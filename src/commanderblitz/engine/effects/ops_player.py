"""Effect ops that write a **player-level designation**.

Its own module rather than a corner of one of the others, because none of them
describes this. `ops_removal`, `ops_counters`, `ops_characteristics` and `ops_combat_flags` act on permanents, `ops_life` on life totals and
damage, `ops_mana` on the pool, `ops_control` on control flow -- and a
designation is none of those: nothing on the board changes, no number moves, and
the thing written outlives every permanent that granted it.

`set_flag` is the op every gap record named as the nearest existing thing, and
the comparison is exact enough to be worth keeping in mind: this is `set_flag`
for a *player*. The difference is that a flag is an adjective on one permanent,
cleared by `reset_permanent_state` the moment that permanent changes zones, while
a designation belongs to the table and is exclusive across it.

`win_game` joined it later and widens the module by one word: these are the ops
whose subject is a **seat** rather than anything on the board. It is the same
argument -- nothing on the battlefield changes, no number moves, and what is
written outlives every permanent involved -- carried as far as it goes, to the
one thing about a player that outlives the game itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import DslError
from ..primitives import become_monarch, give_emblem
from ..sba import declare_loss, declare_win
from ..structs import CAST_LOCK_DURATIONS, CASTABLE_ZONES
from ..temp_effects import grant_flash_permission, lock_casting_zones
from .context import EffectContext
from .registry import register
from .selectors import resolve_pool, select_players


@register("become_monarch")
def op_become_monarch(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You become the monarch", or "target player becomes the monarch" (721.2).

    Takes a **player spec**, defaulting to ``"you"`` -- which is what seven of the
    eight cards that asked for this op print. The eighth is Éomer, King of Rohan's
    "target player becomes the monarch", and it is the reason the selector is here
    from the start rather than added later: written with an implicit controller the
    op reads perfectly and gives the crown to the wrong player, which on a card
    whose whole drawback is handing an opponent a card every turn is most of the
    card.

    Every player named is offered it in turn, and the last one keeps it (721.4).
    That is not a shape any printed card has -- there is no "each player becomes
    the monarch" -- but it is what `select_players` returning a list means, and
    silently taking the first would be a different answer with nothing to say so.

    A player who is already the monarch is left alone rather than re-designated,
    so nothing fires. See :func:`~commanderblitz.engine.primitives.become_monarch`.
    """
    for pid in select_players(ctx, spec.get("player", "you")):
        become_monarch(ctx.state, pid, source=ctx.source_oid)
    yield from ()


def shut_cast_zones(zones: Any = None, except_zones: Any = None) -> list[str]:
    """The zones a cast lock shuts, from either of its two spellings.

    ``zones`` names the shut ones; ``except_zones`` names the open ones and is
    subtracted from :data:`CASTABLE_ZONES`. Shared by the timed one-shot below
    (Avatar's Wrath) and the loader's compile of the
    `cant_cast_spells_from_zones` static (Drannith Magistrate), so "anywhere
    other than their hands" is one list of zones whichever card printed it. The
    loader requires exactly one of the two, so there is no branch here where
    both are absent and everything locks by accident.
    """
    if zones is not None:
        return [str(z) for z in zones]
    opened = {str(z) for z in (except_zones or ())}
    return [z for z in CASTABLE_ZONES if z not in opened]


@register("cant_cast_spells_from_zones")
def op_cant_cast_spells_from_zones(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until your next turn, your opponents can't cast spells from anywhere
    other than their hands." -- Avatar's Wrath.

    A **zone-filtered** casting prohibition with a clock, installed by a
    *sorcery*. Three things at once, and the two nearest existing pieces each
    have exactly one of them.

    `cant_cast_spells`, the player-wide static, is total: the loader refuses an
    `affects` beside it on purpose, so a narrower printed line cannot load as a
    strictly stronger lock. Written bare here it would forbid the opponents'
    **hand** casts too -- a far harsher card than the one printed, and silently
    so. It is also a `static_effect`, which only a permanent can carry, and
    this card exiles itself on resolution.

    `set_turn_flag` is the other near miss and is inert: no legality path reads
    `has_turn_flag`, so a player "flagged" locked goes on casting, and the flag
    dies at the turn boundary rather than at the caster's next turn -- one turn
    too soon at a table of four.

    So it is a **row in a timed table**, `structs.CastLock`, beside the life
    lock and the player protection the same kind of one-shot installs. Like
    them it modifies nothing and resolves before there is anything to modify:
    the whole of its behaviour is the record it leaves for
    `primitives.cast_locked_zones` to answer from, and the three cast roads
    all ask that.

    ``player`` is the usual player spec and says **who is locked**; it defaults
    to ``"each_opponent"``, which is what the printed sentence says. The *clock* is
    always the resolving controller -- "until **your** next turn" -- and is not
    spellable, because no printed card times a prohibition off a seat other
    than the one that imposed it.

    ``zones`` names the shut zones; ``except_zones`` names the open ones and is
    subtracted from :data:`CASTABLE_ZONES`. Two spellings because printed cards
    use both -- "from anywhere other than their hands" is the inverse form and
    would otherwise be six zones typed out by hand, which is six chances to
    leave one off. The loader refuses both on one effect, and refuses neither.
    """

    duration = str(spec.get("duration", "until_your_next_turn"))
    if duration not in CAST_LOCK_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_cast_spells_from_zones duration {duration!r}")
    zones = shut_cast_zones(spec.get("zones"), spec.get("except_zones"))
    lock_casting_zones(
        ctx.state,
        # The clock: whoever is resolving this. "Until **your** next turn."
        ctx.controller,
        select_players(ctx, spec.get("player", "each_opponent")),
        zones,
        duration,
        source=ctx.source_oid,
    )


@register("cant_cast_spells")
def op_cant_cast_spells(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "If you do, you can't cast additional spells this turn." -- Conduit of
    Worlds.

    The **timed, one-shot** form of the `cant_cast_spells` static: a player-wide,
    total casting prohibition installed by a resolving ability rather than
    carried by a permanent. The static cannot say it -- it lasts exactly as long
    as its permanent and has no clock -- and `cant_cast_spells_from_zones` is the
    zone-filtered lock: a "can't cast spells" written as that op would leave the
    cast of a copy (707.12) open, because a copy has no zone to compare.

    So it is the same `structs.CastLock` row with **every** zone in
    `CASTABLE_ZONES` shut, which `player_statics.player_cant_cast_spells` reads
    as total. Every cast road already asks one of those two readers, and the row
    shares the timed table's clock and its cleanup.

    ``player`` is who can't cast and ``duration`` how long; both are required,
    because the two printed shapes differ in both ("**you** can't cast
    additional spells **this turn**", "**your opponents** can't cast spells
    **this turn**") and a default would silently pick one of them for the other.
    The clock is the resolving controller, as it is for the zone lock. A spell
    already on the stack is unaffected: the lock stops casting, not spells.
    """

    duration = str(spec["duration"])
    if duration not in CAST_LOCK_DURATIONS:  # pragma: no cover - loader guards
        raise DslError(f"unknown cant_cast_spells duration {duration!r}")
    lock_casting_zones(
        ctx.state,
        ctx.controller,
        select_players(ctx, spec["player"]),
        CASTABLE_ZONES,
        duration,
        source=ctx.source_oid,
    )


@register("grant_flash_permission")
def op_grant_flash_permission(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "Until your next turn, you may cast sorcery spells as though they had
    flash." -- Teferi, Time Raveler's +1.

    The one-shot, timed form of the `cast_as_though_flash` static: a loyalty
    ability leaves no permanent to carry a static, the permission ends at a fixed
    moment, and it covers cards drawn after it resolved -- so it is written to
    the player's timed table and read by `casting._timing_ok`. ``types`` narrows
    it to spells of those card types; ``duration`` is required.
    """

    types = tuple(str(t) for t in spec.get("types") or ())
    duration = str(spec["duration"])
    for pid in select_players(ctx, spec.get("player", "you")):
        grant_flash_permission(
            ctx.state, pid, types=types, duration=duration, source=ctx.source_oid
        )
    yield from ()


@register("extra_loyalty_activation")
def op_extra_loyalty_activation(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "For each planeswalker you control, you may activate one of its loyalty
    abilities once this turn as though none of its loyalty abilities have been
    activated this turn." -- The Chain Veil.

    606.3 allows one loyalty activation per permanent per turn; this raises that
    ceiling by one for each walker the selector names *as it resolves* (the
    default is planeswalkers you control). Additional, not a reset: a walker
    that has not activated yet may now activate twice, which is the card's
    ruling, and a second Veil activation is a second extra. The timing half of
    606.3 is untouched -- still your main phase with an empty stack.
    """

    selector = dict(spec.get("objects") or {"controller": "you", "types": ["Planeswalker"]})
    extra = ctx.state.turn_ledger.extra_loyalty_activations
    for oid in resolve_pool(ctx, selector):
        obj = ctx.state.objects.get(oid)
        if obj is not None and obj.on_battlefield:
            extra[oid] = extra.get(oid, 0) + 1
    yield from ()


@register("win_game")
def op_win_game(ctx: EffectContext, spec: Mapping[str, Any]) -> None:
    """ "You win the game." Halo Fountain and Luck Bobblehead.

    The only op that ends the game on purpose, and the first thing to reach a
    game *result* at all. Everything else that has ever produced a winner did it
    by accident of arithmetic: `damage` and `lose_life` take a seat to zero,
    `add_poison` takes it to ten, and `sba` notices. Neither card here is about a
    life total -- Halo Fountain untaps fifteen creatures at 40 life against 40
    life, and Luck Bobblehead counts sixes -- so there was no approximation to
    make, only a missing sentence.

    Takes the usual **player spec**, defaulting to ``"you"``, which is what both
    cards print. The spec is here rather than hardcoded for the reason
    `become_monarch`'s is: a player is a first-class thing to name in this DSL,
    and every op that names one spells it the same way and validates through the
    same `loader.effects._validate_player_spec`.

    A spec naming more than one seat is not refused, and does not need to be:
    :func:`~commanderblitz.engine.sba.declare_win` is a no-op once the game is over, so
    the first player named wins and the rest are ignored. No printed card says
    "each player wins the game" -- the one shape that would matter is a *team*
    win, and teams are not modelled.

    The work is all in `sba.declare_win`, which is where the argument about
    *where a result may be written* lives. Read it before changing this.

    Two things this deliberately does not do:

    - **It is not `lose_game` on everybody else.** The effect is the same in a
      duel, but `lose_game` names one seat and eliminates only that one (104.3a);
      this eliminates every opponent (104.2a).
    - **It does not check "can't win the game".** Platinum Angel and Abyssal
      Persecutor are a continuous prohibition over this whole subsystem, not a
      clause of this op, and nothing in the pool has one.

    Anything sequenced *after* this in the same effect list still runs -- the
    interpreter has no game-over guard mid-resolution -- but the game is already
    over, so nothing it does is offered to anybody. Both cards put the win last,
    which is where every printed "you win the game" puts it.
    """

    for pid in select_players(ctx, spec.get("player", "you")):
        declare_win(ctx.state, pid)


@register("lose_game")
def op_lose_game(ctx: EffectContext, spec: Mapping[str, Any]) -> None:
    """ "That player loses the game." Vraska the Unseen's Assassin tokens.

    104.3a: only the named player leaves. The Assassin writes it
    ``{"op": "lose_game", "player": {"binding": "event_player"}}`` -- the seat
    its combat damage hit -- and in a pod the other opponents play on, which is
    the whole difference from `win_game` on the controller. Also the unpaid
    branch of the Pact cycle (``"player": "you"``, the default).

    Every seat the spec names loses at once: `sba.declare_loss` eliminates them
    all before it asks whether the game is over, so "each player loses the
    game" is a draw (104.4a).
    """

    declare_loss(ctx.state, select_players(ctx, spec.get("player", "you")))


@register("extra_turn")
def op_extra_turn(ctx: EffectContext, spec: Mapping[str, Any]) -> None:
    """ "Take an extra turn after this one" (500.7). Time Warp, Perch Protection.

    Takes the usual **player spec**, defaulting to ``"you"``. The spec is not a
    nicety: Perch Protection's gift is "they take an extra turn after this one",
    written ``{"op": "extra_turn", "player": "gift_recipient"}`` -- which, like
    Parting Gust's Fish, schedules nothing at all when no promise was made,
    because the spec resolves to nobody.

    Only schedules. The turn is pushed onto `GameState.extra_turns` and
    `turn._begin_next_turn` takes it when the current turn ends, so the op is
    correct from wherever it resolves -- a sorcery in your main phase, or an
    instant on somebody else's turn, whose extra turn still comes directly after
    *that* turn. Whether the turn then happens at all is decided there, not here:
    a skip is a replacement on the turn beginning (614.10), and Trouble in Pairs
    arriving between the two must still catch it.

    Several players named are added one at a time in APNAP order, the most
    recently added taken first -- 500.7 word for word, so in a pod "each player
    takes an extra turn" runs in reverse turn order from the active player.
    """
    state = ctx.state
    named = set(select_players(ctx, spec.get("player", "you")))
    for pid in state.turn_order():
        if pid in named:
            state.extra_turns.append(pid)


@register("no_maximum_hand_size")
def op_no_maximum_hand_size(ctx: EffectContext, spec: Mapping[str, Any]) -> None:
    """ "You have no maximum hand size for the rest of the game." (402.2)

    Sea Gate Restoration, Finale of Revelation's X-is-10 branch, Ancient Silver
    Dragon. The printed static ``no_hand_limit`` already says the same words,
    and could not carry these cards: it exists only while a permanent printing
    it is on the battlefield, and a sorcery never is. This is the one-shot
    that outlives its source -- it sets `PlayerState.has_no_maximum_hand_size`,
    one-way, and `player_statics.player_has_no_hand_limit` reads that flag
    beside the statics, so the cleanup step (514.1) asks one question either
    way.

    Takes the usual **player spec**, defaulting to ``"you"``. Named for the
    lifetime it has, which is the whole game: "until your next turn" (Enter the
    Infinite) is a different, *ending* effect and the loader refuses a
    ``duration`` here rather than reading it as this.
    """
    for pid in select_players(ctx, spec.get("player", "you")):
        ctx.state.players[pid].has_no_maximum_hand_size = True


@register("emblem")
def op_emblem(ctx: EffectContext, spec: Mapping[str, Any]):
    """ "You get an emblem with …" / "Target opponent gets an emblem with …" (114).

    ``emblem`` is an index into this card's own ``emblems``, where the quoted
    abilities are written out -- the same shape `grant_ability` uses for quoted
    abilities it hands to a permanent. ``player`` is the usual **player spec**,
    and it is required rather than defaulted: most emblems go to "you", but Ob
    Nixilis Reignited's and Garruk, Apex Predator's go to a *target opponent*, and
    a defaulted spec on either reads fine and hands the drawback to its own
    controller.

    The card is read off `EffectContext.source_def_id` -- the id snapshotted as
    the ability went on the stack -- rather than off the source object, because
    an ultimate usually spends the planeswalker's last loyalty and it is gone
    before this resolves.
    """
    def_id = ctx.source_def_id
    if not def_id and ctx.source_oid is not None and ctx.source_oid in ctx.state.objects:
        def_id = ctx.state.card(ctx.source_oid).id
    if not def_id or def_id not in ctx.state.registry:
        return
    index = int(spec["emblem"])
    if not 0 <= index < len(ctx.state.registry.get(def_id).emblems):
        return
    for pid in select_players(ctx, spec["player"]):
        give_emblem(ctx.state, def_id, index, pid)
    yield from ()
