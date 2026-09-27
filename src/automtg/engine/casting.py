"""What a player may cast and how: the cast actions, their variants (kicker,
additional costs, alternative costs), and the ceilings on each. Split from
``legality`` so the priority-window logic and the casting grammar can be
read apart.
"""

from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

from . import suspend as suspend_mod
from .actions import Action
from .carddef import BESTOW_TARGET, MUTATE_TARGET, CardDef, Cost
from .characteristics import chars, player_cant_cast_spells
from .costs import (
    can_pay,
    commander_cost,
    zone_of,
)
from .enums import ActionKind, Keyword, Step, Zone
from .mana import ManaCost, max_affordable_x, solve_payment
from .player_statics import (
    free_cast_permission,
    granted_warp_cost,
    player_casts_as_though_flash,
    player_pays_life_for_black,
    player_spends_mana_as_any_color,
    spell_life_tax,
    spell_life_tax_on_board,
)
from .primitives import cast_locked_zones, life_locked, sacrifice_forbidden
from .targeting import describe_ref, enumerate_target_tuples, kicked_targets

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def _cast_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    out: list[Action] = []
    if state.players[pid].epic_source is not None:
        # Epic: "spend the rest of the game casting no spells" (702.50a). A
        # legality gate rather than a cost or a condition, because it is not
        # about any one card -- and lands are unaffected, which is why it is
        # here rather than in `legal_actions`.
        return out
    if player_cant_cast_spells(state, pid):
        # "Your opponents can't cast spells during your turn" -- Voice of
        # Victory. Here, at the top, rather than per zone below, because the
        # prohibition is about the player and not about where the card is: a
        # flashback, a foretold card, a Citadel top, a commander and a prepared
        # copy are all casts, and a gate written into any one block would leave
        # the rest open. Lands and suspend are not offered from this function,
        # so they stay, which is 116.2's line between a cast and a special
        # action.
        return out

    # Per object, not per card name -- see the note on _land_actions.
    for oid in state.players[pid].hand:
        card = state.card(oid)
        if card.is_land:
            continue
        # The two faces are offered independently and their timings are asked
        # separately, because they are two different spells: Brazen Borrower is
        # a flash creature whose Adventure is an *instant*, and a card whose
        # Adventure was gated on the front face's type line would be castable at
        # the wrong speed in one direction or the other.
        out.extend(_second_face_actions(state, pid, oid, card, Zone.HAND, sorcery_speed))
        if not _timing_ok(state, pid, card, sorcery_speed):
            continue
        out.extend(_cast_options(state, pid, oid, card, extra_generic=0))

    # "While it's prepared, you may cast a copy of its spell." The battlefield
    # is not one of the zones above and must not be: every zone in that list is
    # one the spell then *leaves*, and a prepared permanent stays where it is.
    out.extend(_prepared_actions(state, pid, sorcery_speed))

    # "You may play lands and cast spells from the top of your library" --
    # Bolas's Citadel. A fifth zone a spell may be cast from, and the only one
    # that is *hidden*: the top card and nothing below it, which is what the
    # card says and the only part of a library anybody is entitled to see.
    # Lands are the neighbouring `play_lands_from_library_top` permission and
    # are offered by `_land_actions`, so this covers only what that one cannot.
    from .characteristics import library_top_cast_permission

    top_permission = library_top_cast_permission(state, pid)
    if top_permission is not None and state.players[pid].library:
        oid = state.players[pid].library[0]
        card = state.card(oid)
        # 118.4: a player may pay life down to exactly 0, so the test is on
        # having that much and not on surviving it. A line offered and then
        # unpayable would be an action the engine could not honour.
        affordable = state.players[pid].life >= card.mana_value
        if not card.is_land and affordable and _timing_ok(state, pid, card, sorcery_speed):
            out.extend(
                _cast_variant(
                    state,
                    pid,
                    oid,
                    card,
                    enumerate_target_tuples(state, pid, card.targets, oid),
                    extra_generic=0,
                    from_library_top=True,
                )
            )

    # Adventure (715.3d): the card is in exile having gone on one, and its
    # *front* face may be cast from there. A fourth zone a card may be cast
    # from, widened the way retrace widens the graveyard -- and it is the front
    # face, so nothing about the offer is special except where it is offered.
    for oid in state.players[pid].exile:
        obj = state.objects[oid]
        if not obj.on_adventure or obj.owner != pid:
            continue
        card = state.card(oid)
        if not _timing_ok(state, pid, card, sorcery_speed):
            continue
        out.extend(_cast_options(state, pid, oid, card, extra_generic=0))

    # "You may play the exiled card this turn." The same widening the Adventure
    # block above makes, with a turn on it: the permission expires, and a card
    # left in exile with a bare flag would stay castable for the rest of the
    # game. The price is the printed one -- this grants permission, not a
    # discount, which is the whole difference from `play_exiled`.
    # Every graveyard as well as your own exile: Locke, Treasure Hunter mills
    # one card from **each** player and then lets you cast one of them, so the
    # permission has to reach an opponent's yard. The flag is the permission, so
    # walking a wider set of zones offers nothing extra -- nothing carries it
    # that was not granted it.
    permitted: list[int] = []
    for player in state.players:
        # Both zones, and every seat's copy of them. Exile is kept per owner, so
        # a card taken out of an *opponent's* graveyard sits in that opponent's
        # exile -- Valigarmanda exiles "an instant or sorcery card from each
        # graveyard" and then offers you one of them. The flag is the
        # permission, so walking a wider set of zones offers nothing extra:
        # nothing carries it that was not granted it.
        permitted.extend(player.exile)
        permitted.extend(player.graveyard)
    for oid in permitted:
        obj = state.objects[oid]
        if obj.playable_by != pid or not obj.playable_live(state.turn):
            continue
        # "…you may cast **a spell** from among those cards", singular out of
        # however many were milled. Counted per granting permanent, so two
        # Lockes are two spells and one Locke milling three cards is still one.
        if obj.playable_group is not None and state.turn_ledger.activations(
            obj.playable_group, GRAVEYARD_CAST_SLOT
        ):
            continue
        card = state.card(oid)
        # "…as a sorcery." A restriction the *permission* carries, not the card:
        # a plotted instant is still an instant, and `_timing_ok` would happily
        # offer it with something on the stack.
        if obj.playable_sorcery_only and not sorcery_speed:
            continue
        if card.is_land or not _timing_ok(state, pid, card, sorcery_speed):
            continue
        out.extend(
            _cast_options(
                state,
                pid,
                oid,
                card,
                extra_generic=0,
                free=obj.playable_free,
                # "…its owner may cast it **for {2} rather than its mana
                # cost**" -- airbend. Read off the same permission that made
                # the card castable at all, beside `playable_free`, because it
                # is the same kind of fact: what this line costs. `Game._cast`
                # reads the identical field off the identical card.
                alt_cost=obj.playable_alt_cost,
            )
        )

    # Foretold cards are cast from **exile**, at the foretell price, and only on
    # a turn after the one they were foretold on -- `foretold_cards` is what
    # enforces the "later", because a card foretold and cast the same turn is
    # the printed cost paid in two instalments with the discount thrown in.
    for oid in suspend_mod.foretold_cards(state, pid):
        card = state.card(oid)
        if not _timing_ok(state, pid, card, sorcery_speed):
            continue
        ft_tuples = enumerate_target_tuples(state, pid, card.targets, oid)
        out.extend(
            _charge_additional_cost(
                state,
                pid,
                oid,
                card,
                _cast_variant(
                    state,
                    pid,
                    oid,
                    card,
                    ft_tuples,
                    extra_generic=0,
                    foretold=True,
                ),
                lambda times, choice, oid=oid, card=card, tuples=ft_tuples: _cast_variant(
                    state,
                    pid,
                    oid,
                    card,
                    tuples,
                    extra_generic=0,
                    foretold=True,
                    additional_times=times,
                    additional_choice=choice,
                ),
            )
        )

    # Retrace: the graveyard is a third place a card can be cast from, widened
    # here the same way `_land_actions` widens where a land may be played from.
    from .costs import can_pay

    for oid in _castable_graveyards(state, pid):
        card = state.card(oid)
        # Aftermath (702.127a): "cast this half only from your graveyard". The
        # same widening retrace makes, and the restriction is where the second
        # face is *offered* rather than a condition on the cast -- there is no
        # hand line to refuse.
        out.extend(_second_face_actions(state, pid, oid, card, Zone.GRAVEYARD, sorcery_speed))
        if not _timing_ok(state, pid, card, sorcery_speed):
            continue
        # "Once during each of your turns, you may cast an artifact spell from
        # your graveyard" -- Edgar. A permission granted by a *permanent*, so
        # unlike flashback and retrace it is not a property of the card being
        # cast and legality has to ask the board. Offered at the **printed**
        # price, which is what separates it from flashback's alternative cost.
        if _graveyard_cast_permission(state, pid, card, oid) is not None:
            out.extend(_cast_options(state, pid, oid, card, extra_generic=0))
        if card.retrace and can_pay(state, pid, card.retrace_cost, oid):
            out.extend(_cast_options(state, pid, oid, card, extra_generic=0))
        # Flashback is the same widening with a different price: an alternative
        # cost that *replaces* the printed one, so it is offered as its own
        # variant rather than folded into the ordinary cast.
        if card.flashback is not None and can_pay(state, pid, card.flashback.without_mana(), oid):
            fb_tuples = enumerate_target_tuples(
                state,
                pid,
                card.targets,
                oid,
                exclude_sid=state.objects[oid].stack_id,
            )
            # "…for its flashback cost **and any additional costs**" is printed
            # in flashback's own reminder text, and 601.2f says it anyway.
            out.extend(
                _charge_additional_cost(
                    state,
                    pid,
                    oid,
                    card,
                    _cast_variant(
                        state,
                        pid,
                        oid,
                        card,
                        fb_tuples,
                        extra_generic=0,
                        flashback=True,
                    ),
                    lambda times, choice, oid=oid, card=card, tuples=fb_tuples: _cast_variant(
                        state,
                        pid,
                        oid,
                        card,
                        tuples,
                        extra_generic=0,
                        flashback=True,
                        additional_times=times,
                        additional_choice=choice,
                    ),
                )
            )

    for oid in state.players[pid].command:
        obj = state.objects[oid]
        if not obj.is_commander:
            continue
        card = state.card(oid)
        if not _timing_ok(state, pid, card, sorcery_speed):
            continue
        out.extend(_cast_options(state, pid, oid, card, extra_generic=commander_cost(state, oid)))
    # "…can't cast spells from anywhere other than their hands." (Avatar's
    # Wrath.) Applied to the finished list rather than written into each block
    # above, and that is the whole point of doing it here: this function offers
    # casts out of the hand, the top of the library, exile, both graveyards,
    # the command zone and the battlefield, in eight separate walks, and a gate
    # written into one of them would leave the other seven open. One filter on
    # `zone_of` closes all of them, and closes the ninth the next lane adds.
    #
    # Distinct from `player_cant_cast_spells` at the top, which returns early
    # and needs no zone: that one is a claim about the player, and this one is
    # a claim about where a card is.
    if shut := cast_locked_zones(state, pid):
        out = [a for a in out if zone_of(state, a.source) not in shut]
    return out


def _prepared_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    """ "While it's prepared, you may cast a copy of its spell."

    A cast offered from the **battlefield**, which no other cast line is: every
    zone `_cast_actions` walks is a zone the spell then leaves, and a prepared
    permanent stays exactly where it is. So this is its own walk rather than
    another entry in `zones` -- putting the battlefield in that list would offer
    every permanent on it as a spell.

    Priced, timed and targeted off the **spell face**, the way
    `_second_face_actions` prices the Adventure half: `_cast_variant` never
    assumed the card it was pricing was the one the object is printed as. The
    permanent's own oid is what the action names, because that is what
    `Game._cast` has to find again to unprepare it.

    "Doing so unprepares it" is why no rate limit is needed here and none is
    written: the permission is spent by using it, which is the state itself.
    """
    out: list[Action] = []
    for obj in state.battlefield_objects(pid):
        if not obj.prepared:
            continue
        card = state.card_of(obj)
        if card.prepared_face is None:
            continue
        face = state.registry.get(card.prepared_face)
        if not _timing_ok(state, pid, face, sorcery_speed):
            continue
        tuples = enumerate_target_tuples(state, pid, face.targets, obj.oid)
        if not tuples:
            continue
        out.extend(_cast_variant(state, pid, obj.oid, face, tuples, extra_generic=0, prepared=True))
    return out


def _second_face_actions(
    state: GameState,
    pid: int,
    oid: int,
    card: CardDef,
    zone: Zone,
    sorcery_speed: bool,
) -> list[Action]:
    """The lines for casting this card as its second face, if there are any.

    One card, two spells. Everything the variant needs -- the price, the name,
    the targets, the timing -- is read off the *second face's* ``CardDef``, so
    this is a two-line function with a long argument: `_cast_variant` never
    assumed the card it was pricing was the one the object is printed as.

    The only thing that stays the front face's is the **object**, which is the
    point: it is still one card, in one zone, and casting either half takes it
    out of that zone.
    """
    if card.second_face is None:
        return []
    if SECOND_FACE_ZONES.get(card.second_face_zone) is not zone:
        return []
    face = state.registry.get(card.second_face)
    # A land half is **played**, not cast, and `_land_actions` offers it. Without
    # this, a modal DFC's land face was offered both ways -- and the cast line
    # would put a land on the stack, which is not a thing that can happen.
    if face.is_land:
        return []
    if not _timing_ok(state, pid, face, sorcery_speed):
        return []
    tuples = enumerate_target_tuples(
        state, pid, face.targets, oid, exclude_sid=state.objects[oid].stack_id
    )
    if not tuples:
        return []
    out = _cast_variant(state, pid, oid, face, tuples, extra_generic=0, second_face=True)
    # Fuse (702.102a): a third line that is **both** halves -- both costs paid
    # together, both target lists chosen together. Priced and enumerated off a
    # card built from the two, so `_cast_variant` needs no notion of fusion: it
    # is pricing one spell, as it always is.
    if card.fuse and zone is Zone.HAND:
        import dataclasses

        both = dataclasses.replace(
            card,
            name=f"{card.name} // {face.name}",
            mana_cost=card.mana_cost.plus(face.mana_cost),
            targets=tuple(card.targets) + tuple(face.targets),
        )
        fused_tuples = enumerate_target_tuples(
            state, pid, both.targets, oid, exclude_sid=state.objects[oid].stack_id
        )
        if fused_tuples:
            out = out + _cast_variant(
                state, pid, oid, both, fused_tuples, extra_generic=0, fused=True
            )
    return out


#: Where a second castable face may be cast from, as the zone the loop that
#: offers it is walking. Split halves and Adventures are cast from hand, an
#: Aftermath half only from the graveyard.
SECOND_FACE_ZONES = {"hand": Zone.HAND, "graveyard": Zone.GRAVEYARD}


#: Where a `cast_before_step` bound really closes the window.
#:
#: 510.4: with first strike on the board a combat phase has **two** combat
#: damage steps, and both of them are combat damage steps. "Only before the
#: combat damage step" therefore closes at the earlier one -- so a card may say
#: what it prints and the engine reads the rule.
_WINDOW_CLOSES: dict[Step, Step] = {Step.COMBAT_DAMAGE: Step.FIRST_STRIKE_DAMAGE}


def _window_closes_at(named: Step) -> Step:
    return _WINDOW_CLOSES.get(named, named)


def _timing_ok(state: GameState, pid: int, card: CardDef, sorcery_speed: bool) -> bool:
    """May ``pid`` cast this card at the present moment?

    Printed characteristics first, then the sorcery-speed window -- and between
    them, the one thing on the board that can widen the window: "you may cast
    spells as though they had flash" (Tidal Barracuda, Leyline of Anticipation,
    Vedalken Orrery).

    `state` and `pid` are here for that permission alone. Without them this read
    printed characteristics off the `CardDef` and nothing a permanent did could
    reach it, which is the block three gap records recorded. Every zone a spell
    can be cast from asks this same question, so widening it here reaches all of
    them at once rather than one cast path at a time.

    A permission, not a compulsion: it can only turn a "no" into a "yes" for the
    *timing* question. Anything that forbids the cast outright -- 101.2's rule
    that "can't" beats "can", `player_cant_cast_spells`, epic -- is asked
    elsewhere and is unaffected.

    `cast_before_step` is the one thing here that **narrows**, so it is asked
    first. "Cast this spell only before the combat damage step" (Berserk) is
    printed on an instant, and every other branch below returns True for an
    instant before anything could reach it -- a restriction written after them
    would load, read as the printed card and never once refuse a cast.
    """
    if card.cast_before_step is not None and state.step >= _window_closes_at(
        card.cast_before_step
    ):
        return False
    if card.is_instant or Keyword.FLASH.value in card.keywords:
        return True
    if sorcery_speed:
        return True
    return player_casts_as_though_flash(state, pid)


def warp_cost(state: GameState, pid: int, card: CardDef) -> str | None:
    """The warp price this player may cast this card for, printed or granted.

    Two sources for one mechanic, and the second is the whole reason this is a
    function rather than a field read. "Warp {1}{R}" is printed on the card;
    "artifact cards and red creature cards in your hand have warp {2}{R}" is
    Tannuk, Steadfast Second saying it about *somebody else's* cards, and a
    card in a hand has no abilities for a grant to hang on -- so the grant is a
    static on the granting permanent and is asked here, where the cast lines
    are built, every time they are built.

    The printed cost wins when a card has both. No printing collides yet, but
    the card's own price is the one its designer set, and a grant that silently
    re-priced a warp card would be a strictly different card.

    Read by `_cast_options` and by `Game._cast`, which must agree: a line
    offered at one price and charged at another strands the cast half-paid.
    """
    if card.warp is not None:
        return card.warp.text
    return granted_warp_cost(state, pid, card)


def _cast_options(
    state: GameState,
    pid: int,
    oid: int,
    card: CardDef,
    *,
    extra_generic: int,
    free: bool = False,
    alt_cost: str | None = None,
) -> list[Action]:
    """Every distinct way to cast this card right now.

    Kicker makes that plural for one card: paying the extra cost and not paying
    it are two different actions with the same source, offered side by side, and
    the player picks.  Unkicked is listed first so the cheap line stays the
    obvious one.

    Evoke is the same shape pointing the other way -- an *alternative* cost that
    replaces the printed one -- so it is a third variant rather than a flag on
    the first.  A card is never offered as both: kicker adds to a cost evoke has
    already replaced, and no printed card asks for that.
    """
    exclude_sid = state.objects[oid].stack_id
    tuples = enumerate_target_tuples(state, pid, card.targets, oid, exclude_sid=exclude_sid)
    if not tuples:
        return []

    out = _cast_variant(
        state,
        pid,
        oid,
        card,
        tuples,
        extra_generic=extra_generic,
        kicked=False,
        free=free,
        # The airbend price rides on **this** line alone and is deliberately
        # not handed to the variants below. Each of those already chose its own
        # price -- evoke, bestow, the alternative cost -- and a flat {2} laid
        # over one of them would be a third price nobody printed. The plain
        # line is the one the permission is offering, and `Game._cast` charges
        # {2} on exactly the branch that has no other flag set.
        alt_cost=alt_cost,
    )
    # "You may cast Dragon spells without paying their mana costs" --
    # Dracogenesis. A standing board permission rather than a price on this
    # card, so it is asked here, where every cast line for this object is
    # built, and asked *afresh* each time: a Dragon drawn after the permanent
    # arrived is covered, and the permission does not spend itself.
    #
    # An **extra line beside the printed one**, which is the whole of "you
    # may": 601.2b's alternative is a choice, and a player who wants the mana
    # spent -- for Aetherflux Reservoir, for a "spend mana on a creature spell"
    # trigger, or to leave a smaller Dragon uncast -- must still be able to pay
    # normally. A version that replaced the printed line would take that away
    # silently. Listed second for the reason the unkicked line is listed first:
    # the printed way to cast a card stays the default one.
    #
    # Skipped when the caller already priced this line free -- a plotted Dragon
    # is offered free once, not twice.
    if not free and free_cast_permission(state, pid, card):
        out += _cast_variant(
            state, pid, oid, card, tuples, extra_generic=extra_generic, kicked=False, free=True
        )
    if card.kicker is not None:
        # "If this spell was kicked, **instead choose any number of** target
        # creatures you own" -- The Eagles Are Coming!. The kicked line gets its
        # own enumeration, because the size of its target list is not the
        # unkicked one: `tuples` above was built from the printed counts and is
        # shared by every other line on this object.
        #
        # Legal at 601.2c precisely because kicker is announced at 601.2b, one
        # step earlier -- the choice is already made when the targets are
        # declared. Payment (601.2h) is later and is not what this reads.
        kicked_specs = kicked_targets(card.targets)
        kicked_tuples = (
            tuples
            if kicked_specs is None
            else enumerate_target_tuples(state, pid, kicked_specs, oid)
        )
        out += _cast_variant(
            state, pid, oid, card, kicked_tuples, extra_generic=extra_generic, kicked=True
        )
    # Gift (702.164a): "you may promise an opponent a gift as you cast this
    # spell". Kicker's slot -- an optional cast-time choice offered as extra
    # lines beside the plain one -- with two differences that are the whole
    # mechanic.
    #
    # It is **free**. 702.164a makes the promise a choice, not a cost (601.2b,
    # with the modes and X), so every line here is priced at the printed cost
    # and no payment is taken anywhere. That is precisely why it could not be
    # written as a kicker: the loader refuses a kicker that costs nothing,
    # correctly, because a kicker that costs nothing is one cast offered twice.
    #
    # And it names a **seat**. One line per opponent, the shape emerge uses for
    # its victim rather than the bool kicker uses for its price: at a pod the
    # promise goes to one chosen player (not to each of them), and which one is
    # a real choice with the game on it. Not asked as a decision after the fact,
    # because 702.164a puts the promise *as the spell is cast* -- a question
    # asked later would be answered after opponents had already responded to it.
    #
    # Unpromised stays first, the way unkicked does: the line that hands an
    # opponent a creature should never be the one taken by default.
    if card.gift is not None:
        for promisee in state.opponents(pid):
            out += _cast_variant(
                state, pid, oid, card, tuples, extra_generic=extra_generic, gift_to=promisee
            )
    # Only from hand: an alternative cost is permission to cast the card *this
    # way*, and nothing extends it to the graveyard or the command zone the way
    # `retrace` and commander casting do.
    if card.evoke is not None and state.objects[oid].zone is Zone.HAND:
        out += _cast_variant(
            state, pid, oid, card, tuples, extra_generic=extra_generic, evoked=True
        )
    # Warp: evoke's shape with the riders supplied by the rule, and the only
    # alternative cost here that a *different permanent* may hand this card --
    # "artifact cards and red creature cards in your hand have warp {2}{R}".
    # So the price is asked for rather than read off the card, and it is asked
    # afresh at every cast: a card drawn after Tannuk arrived has warp too.
    #
    # Hand-only, like evoke and for its reason -- and here it is the loop guard
    # as well: the warped permanent is exiled at the next end step and cast
    # again *from exile*, so a warp line offered there would let it warp itself
    # for ever and never leave.
    if state.objects[oid].zone is Zone.HAND and (warp := warp_cost(state, pid, card)) is not None:
        out += _cast_variant(state, pid, oid, card, tuples, extra_generic=extra_generic, warp=warp)
    # Bestow (702.103a): the same alternative-cost shape as evoke, and the only
    # one that changes what the spell *points at*. "Enchant creature" is fixed
    # by the rule, so the target comes from `BESTOW_TARGET` rather than from the
    # card -- which is also why the tuples are enumerated here instead of reused
    # from above: a bestow creature declares no targets of its own.
    if card.bestow is not None and state.objects[oid].zone is Zone.HAND:
        bestow_tuples = enumerate_target_tuples(
            state, pid, (BESTOW_TARGET,), oid, exclude_sid=exclude_sid
        )
        out += _cast_variant(
            state, pid, oid, card, bestow_tuples, extra_generic=extra_generic, bestowed=True
        )
    # Mutate (702.140a): bestow's shape again -- an alternative cost whose
    # target the *rule* supplies. "Target non-Human creature you own" is
    # `MUTATE_TARGET`, and a card with no legal one is simply not offered the
    # line, which is why the ordinary creature cast above is enumerated first
    # and separately.
    if card.mutate is not None and state.objects[oid].zone is Zone.HAND:
        mutate_tuples = enumerate_target_tuples(
            state, pid, (MUTATE_TARGET,), oid, exclude_sid=exclude_sid
        )
        out += _cast_variant(
            state, pid, oid, card, mutate_tuples, extra_generic=extra_generic, mutated=True
        )
    # Prowl and spectacle: the same alternative-cost shape, offered only while
    # its condition holds. Checked here rather than at payment because the
    # condition is *permission to cast this way at all* -- offering the line and
    # then refusing it would show a price the player can never pay.
    if card.alternative_cost is not None and state.objects[oid].zone is Zone.HAND:
        from .effects.conditions import evaluate_condition

        # The non-mana half -- Force of Will's "pay 1 life and exile a blue
        # card from your hand" -- is priced here alongside the condition, and
        # for the same reason: a pitch spell held with no other blue card is
        # not castable this way at all, and offering the line and then failing
        # the payment would show a price the player can never pay. `oid` is
        # passed as the source so `_hand_exile_pool` excludes the spell itself
        # (601.2a) -- Force of Will is a blue card in hand and must not pitch
        # itself.
        payable = can_pay(state, pid, card.alternative_cost.without_mana(), oid)
        if payable and evaluate_condition(
            state, card.alternative_condition, controller=pid, source=oid
        ):
            out += _cast_variant(
                state, pid, oid, card, tuples, extra_generic=extra_generic, alternative=True
            )
    # An additional cost -- casualty, replicate, "sacrifice an artifact". No
    # zone gate: 601.2f charges it on every cast, so a retrace line out of the
    # graveyard and a commander cast out of the command zone owe it too. The
    # blocks below stay hand-only because morph, overload, emerge and convoke
    # genuinely are.
    out = _charge_additional_cost(
        state,
        pid,
        oid,
        card,
        out,
        lambda times, choice: _cast_variant(
            state,
            pid,
            oid,
            card,
            tuples,
            extra_generic=extra_generic,
            additional_times=times,
            additional_choice=choice,
        ),
    )
    # Spree (702.166a): "Choose one or more additional costs." One line per
    # non-empty subset of the priced modes, which is the mechanic: a player
    # buying Smuggler's Surprise's mill *and* its hexproof pays both prices and
    # gets both effects, and a version offering one mode at a time would be a
    # strictly weaker card at the same rate.
    out = _spree_lines(
        state,
        card,
        out,
        lambda subset: _cast_variant(
            state,
            pid,
            oid,
            card,
            tuples,
            extra_generic=extra_generic,
            spree_modes=subset,
        ),
    )
    # Morph: "you may cast this card face down as a 2/2 creature for {3}"
    # (702.37a). A cast variant with **no targets** -- a face-down spell is a
    # nameless 2/2 with no text, so there is nothing on it to target with -- and
    # the {3} is fixed by the rule rather than by the card.
    if card.morph is not None and state.objects[oid].zone is Zone.HAND:
        out += _cast_variant(
            state, pid, oid, card, [()], extra_generic=extra_generic, face_down=True
        )
    # Overload. A third variant, and the only one that changes what the spell
    # *points at* rather than what it costs: an overloaded spell is cast with no
    # targets at all (702.96a replaces every "target" with "each"), so it is
    # given the empty tuple rather than `tuples`.
    if card.overload is not None and state.objects[oid].zone is Zone.HAND:
        out += _cast_variant(
            state, pid, oid, card, [()], extra_generic=extra_generic, overloaded=True
        )
    # Emerge offers one line *per sacrificeable creature*, because the price
    # depends on which one goes: the cost is reduced by that creature's mana
    # value. Same reason kicked and unkicked are two actions rather than one
    # with a flag -- the player is choosing, and the choice changes the cost.
    if card.emerge is not None and state.objects[oid].zone is Zone.HAND:
        for victim in _emerge_fodder(state, pid, oid):
            out += _cast_variant(
                state,
                pid,
                oid,
                card,
                tuples,
                extra_generic=extra_generic,
                emerge_oid=victim,
            )
    # Convoke and delve. One line per *number* spent, for the reason emerge
    # offers one per victim: the number changes the price, and it is the
    # player's to choose. Zero is the printed line already offered above.
    if card.pay_generic_with is not None and state.objects[oid].zone is Zone.HAND:
        for spend in range(1, _pay_generic_ceiling(state, pid, oid, card) + 1):
            out += _cast_variant(
                state,
                pid,
                oid,
                card,
                tuples,
                extra_generic=extra_generic,
                pay_generic=spend,
            )
    return out


#: How many times a repeatable additional cost is offered. Capped for the reason
#: convoke's ceiling is: every count is a separate cast action multiplied by
#: every legal target tuple.
MAX_ADDITIONAL_TIMES = 6



def _castable_graveyards(state: GameState, pid: int) -> list[int]:
    """Which graveyard cards ``pid`` might cast from -- usually just their own.

    Every permission the engine had reaches its controller's own graveyard, so
    that is the whole list until something says otherwise. "You may cast instant
    and sorcery spells from **any** graveyard" (Urabrask, and Yawgmoth's Will
    before it) is the exception, and it widens *where the card may be*, not what
    may be cast -- `_graveyard_cast_permission` still asks, per card, whether a
    permission covers it, and refuses a card in somebody else's graveyard to any
    permission that did not say `any_graveyard`.

    Both halves are needed. Widening here alone would offer a card no permission
    covers; asking there alone would never see the card, because this loop is
    where the candidates come from.
    """
    own = list(state.players[pid].graveyard)
    if not any(
        static.get("any_graveyard") for _source, static in _permissions_for(state, pid)
    ):
        return own
    return own + [
        oid
        for other in state.players
        if other.pid != pid
        for oid in other.graveyard
    ]


def _permissions_for(state: GameState, pid: int):
    from .player_statics import graveyard_cast_permissions

    return graveyard_cast_permissions(state, pid)


def _graveyard_cast_permission(state: GameState, pid: int, card: CardDef, oid: int | None = None):
    """The permission that would let ``card`` be cast from a graveyard, if any.

    Returns the granting permanent, or ``None``. Both `legality` and
    `Game._cast` go through here, so the permission a line was offered under is
    the one its use is billed to -- the same agreement `chosen_additional` keeps
    for a modal cost.

    The first unspent one wins. Which of two identical Edgars is billed is not a
    choice any card asks the player to make, and they are interchangeable.
    """
    from .characteristics import (
        graveyard_cast_allows,
        graveyard_cast_arrival_ok,
        graveyard_cast_permissions,
    )

    subject = state.objects.get(oid) if oid is not None else None
    for source_obj, static in graveyard_cast_permissions(state, pid):
        if not graveyard_cast_allows(state, source_obj, static, card):
            continue
        # "…put there from anywhere other than the battlefield this turn" is a
        # fact about *this copy* of the card, so it is asked of the object.
        if subject is not None and not graveyard_cast_arrival_ok(state, static, subject):
            continue
        # "…from **any** graveyard". A permission that does not say so reaches
        # only the caster's own, which is every permission the engine had --
        # so the check is here rather than in the widening, and a card sitting
        # in an opponent's graveyard is invisible to Edgar and to flashback.
        if (
            subject is not None
            and subject.owner != pid
            and not static.get("any_graveyard")
        ):
            continue
        cap = int(static.get("max_per_turn") or 1)
        # Billed against the granting permanent through the ordinary activation
        # ledger, keyed on a sentinel index no real ability can occupy, so a
        # permanent that also has activated abilities does not share a counter
        # with them.
        if state.turn_ledger.activations(source_obj.oid, GRAVEYARD_CAST_SLOT) >= cap:
            continue
        return source_obj
    return None


#: The `ability_index` a graveyard-cast permission's per-turn count is filed
#: under. Negative, so it can never collide with a real ability's index.
GRAVEYARD_CAST_SLOT = -1


def chosen_additional(card: CardDef, choice: int | None) -> Cost | None:
    """The additional cost this cast line pays -- the branch, or the only one.

    "Discard a card **or** pay 3 life" is `additional_cost_options`; everything
    else is the single `additional_cost`. Both `legality` and `Game._cast` price
    a line through here, so the branch offered is the branch charged.
    """
    if card.additional_cost_options:
        if choice is None or not (0 <= choice < len(card.additional_cost_options)):
            return None
        return card.additional_cost_options[choice]
    return card.additional_cost


def _charge_additional_cost(
    state: GameState,
    pid: int,
    oid: int,
    card: CardDef,
    out: list[Action],
    build,
) -> list[Action]:
    """601.2f: **every** way of casting a spell owes its additional cost.

    ``build(times)`` makes the same cast line again with the cost charged
    ``times`` over; ``out`` is the free line or lines the caller already built.

    One line per number of times paid, for the reason convoke offers one per
    number convoked: the count changes the price and is the player's to choose.

    A *mandatory* cost withdraws the free lines entirely -- not merely when it
    happens to be unpayable. Clearing it only in the unpayable case is the same
    thing as never charging it: a player holding a creature was offered both
    Village Rites lines and `find_play` took the first, so the card was a
    one-mana draw-two that sacrificed nothing. An unpayable cost then falls out
    of the same statement, because the loop adds nothing when the ceiling is 0
    and the spell is simply not castable.

    Everything is dropped, not just the plain variant: an evoke or kicker line
    that skipped the cost would be the same bug wearing a different name -- and
    so is a **flashback** line, which is why this is a helper rather than a
    block inside `_cast_options`. Laughing Mad is the witness: "As an additional
    cost to cast this spell, discard a card" plus "Flashback {3}{R}", whose own
    reminder text spells out "for its flashback cost *and any additional
    costs*". Flashback, foretell and retrace all reach the stack by paths that
    used to skip this, so a flashed-back Laughing Mad drew two and discarded
    nothing.
    """
    branches = (
        list(range(len(card.additional_cost_options)))
        if card.additional_cost_options
        else ([None] if card.additional_cost is not None else [])
    )
    if not branches:
        return out
    if not card.additional_optional:
        out = []
    for choice in branches:
        # One line per **payable** branch, exactly as emerge offers one per
        # sacrificeable creature: a branch nobody can pay is not a price on
        # offer, and with a mandatory cost a card whose every branch is
        # unpayable is simply not castable.
        for times in range(1, _additional_ceiling(state, pid, oid, card, choice) + 1):
            out = out + build(times, choice)
    return out


def _spree_lines(
    state: GameState,
    card: CardDef,
    out: list[Action],
    build,
) -> list[Action]:
    """702.166a: "Choose **one or more** additional costs."

    ``build(subset)`` makes the cast line that buys exactly those modes; ``out``
    is whatever the caller has already built.

    One line per **non-empty subset**, which is the whole of spree and the one
    thing `additional_cost_options` cannot say: that list sells exactly one
    branch, so three modes written there would be three cast lines instead of
    seven, and Smuggler's Surprise would be a card that can never do two things
    at once however much mana its caster has.

    The lines already built are **withdrawn**, for the reason a mandatory
    `additional_cost` withdraws them: "one or more" means the unmodified spell
    is not a legal cast at all, and leaving the plain line in place would make
    every spree card castable for its printed cost with none of its text.
    Withdrawn wholesale rather than only when a mode is unaffordable, because
    clearing it in the unpayable case alone is the same thing as never charging
    it -- `find_play` and the heuristic agent both take the first line offered.

    Payability is left entirely to the mana solver, which `_cast_variant` runs
    over the *subset's* folded price. That is why the loader refuses a non-mana
    spree mode: a per-mode check would say yes twice to a player who can only
    afford once.
    """
    if not card.spree:
        return out
    lines: list[Action] = []
    indices = range(len(card.spree))
    # Cheapest-shaped first -- one mode before two, and in printed order inside
    # each size. The client lists them in this order and `verify.find_play`
    # deliberately reaches past it for the largest, so nothing downstream reads
    # "the first line" as "the whole card".
    for size in range(1, len(card.spree) + 1):
        for subset in combinations(indices, size):
            lines = lines + build(subset)
    return lines


def _additional_ceiling(
    state: GameState, pid: int, oid: int, card: CardDef, choice: int | None = None
) -> int:
    """How many times this card's additional cost may be paid on this cast.

    One unless the card says ``additional_repeatable`` -- replicate is the only
    printed shape that repeats, and offering a second sacrifice on a casualty
    card would be a strictly better card than the one printed.

    Payability of the *non-mana* half is left to `can_pay`, which the caller
    already runs; this only bounds how many lines are worth building.
    """
    from .costs import can_pay

    # The non-mana half has to be *payable*, and legality is where that is
    # decided: a casualty line offered with no creature big enough to sacrifice
    # would be an action the player could take and the engine could not honour.
    # The mana half is folded into the price and answered by the solver.
    branch = chosen_additional(card, choice)
    if branch is not None and not can_pay(state, pid, branch.without_mana(), oid):
        return 0
    if not card.additional_repeatable:
        return 1
    # A repeatable cost is paid once *per line*, so the ceiling has to know how
    # many payments the board can actually stand. Replicate never needed it: its
    # cost is mana, each line is priced `mana.scaled(times)`, and the solver
    # drops the ones that cannot be paid.
    #
    # A repeatable **non-mana** cost has an empty `mana`, so every line was
    # priced at the printed cost and all six were offered whatever the board
    # held -- and `pay` does not fail closed, because sacrificing an empty pool
    # succeeds. Plumb the Forbidden with one creature was seven cards for
    # {1}{B}. The single `can_pay` above proved *one* payment, not six.
    return min(MAX_ADDITIONAL_TIMES, _repeatable_payments(state, pid, oid, card))


def _repeatable_payments(state: GameState, pid: int, oid: int, card: CardDef) -> int:
    """How many times the non-mana half of a repeatable cost could be paid.

    Counts the pool each consuming clause draws from and takes the smallest -- a
    cost that sacrifices *and* discards can be paid only as often as its scarcer
    half allows. A clause with no pool to count leaves the ceiling alone, since
    the mana price still bounds those.
    """
    from .costs import life_cost
    from .effects.context import EffectContext
    from .effects.selectors import resolve_pool

    cost = card.additional_cost
    if cost is None:
        return MAX_ADDITIONAL_TIMES
    ctx = EffectContext(state=state, controller=pid, source_oid=oid)
    limits: list[int] = []
    for selector in (cost.sacrifice, cost.return_to_hand, cost.exile_from_graveyard):
        if selector is not None:
            limits.append(len(resolve_pool(ctx, selector)))
    if cost.discard:
        limits.append(len(state.players[pid].hand) // max(1, cost.discard))
    if cost.pay_life:
        per = life_cost(state, pid, cost, oid)
        limits.append(state.players[pid].life // per if per else MAX_ADDITIONAL_TIMES)
    return min(limits, default=MAX_ADDITIONAL_TIMES)


#: What casting a creature face down costs, fixed by rule 702.37a rather than by
#: the card. The card names only the price of turning it back up.
MORPH_COST = ManaCost.parse("{3}")

#: "Without paying its mana cost." Plot's price, and not the same thing as a
#: cost reduced to zero -- on an X spell a discount still leaves X to pay.
FREE_COST = ManaCost.parse("")

#: How many creatures a convoke line may tap, or cards a delve line may exile.
#: Capped for the reason `_emerge_fodder` is capped: every one is a separate
#: cast action multiplied by every legal target tuple.
MAX_PAY_GENERIC = 6


def _pay_generic_ceiling(state: GameState, pid: int, oid: int, card: CardDef) -> int:
    """The most a convoke or delve line could usefully spend.

    Never more than the spell's own generic cost -- "pays for {1}" and a spell
    with two generic in it cannot absorb a third creature -- and never more
    than the player actually has to spend.
    """
    generic = card.mana_cost.generic
    if generic <= 0:
        return 0
    if card.pay_generic_with == "tap_creatures":
        available = sum(
            1
            for other in state.battlefield
            if (obj := state.objects.get(other)) is not None
            and obj.controller == pid
            and not obj.tapped
            and "Creature" in chars(state, other).types
        )
    else:
        # Delve exiles from the graveyard, and the spell being cast is not in
        # it -- it is on the stack by the time this is paid.
        available = sum(1 for other in state.players[pid].graveyard if other != oid)
    return min(generic, available, MAX_PAY_GENERIC)


def _emerge_fodder(state: GameState, pid: int, oid: int) -> list[int]:
    """Creatures this player could sacrifice to emerge, cheapest reduction last.

    Capped, because every one of them is a separate cast action multiplied by
    every legal target tuple -- the same swamping `MAX_TARGET_OPTIONS` exists to
    stop. The biggest mana values come first, since those are the lines a player
    is actually looking for.

    The second half of the **cost** road for "you can't sacrifice those
    creatures this turn" (701.17b). Emerge and offering are the one sacrifice
    cost that does not live in a `Cost` -- the fodder is chosen as part of the
    cast action, because how much the spell costs depends on which creature it
    is -- so `costs._sacrifice_pool`'s filter cannot see them and the same
    question has to be asked again here. A protected creature is simply not a
    line on offer; with no other fodder the emerge cast is not legal at all.
    """
    # "Sacrifice a **Goblin**" -- offering, which is emerge with the fodder
    # narrowed to one creature type. Read off *derived* subtypes, so a
    # changeling or a granted type is legal fodder, which is the rule and is
    # also the only reason anybody plays those two cards together.
    subtype = state.card(oid).emerge_subtype
    creatures = [
        other
        for other in state.battlefield
        if (obj := state.objects.get(other)) is not None
        and obj.controller == pid
        and other != oid
        and "Creature" in (c := chars(state, other)).types
        and (subtype is None or subtype in c.subtypes)
        and not sacrifice_forbidden(state, other)
    ]
    creatures.sort(key=lambda c: (-state.card(c).mana_cost.mana_value(), c))
    return creatures[:4]


def strive_surcharge(card: CardDef, targets) -> ManaCost | None:
    """Strive: what this spell costs **more** for the targets it was cast with.

    "This spell costs {1}{W} more to cast for each target beyond the first." A
    cost increase (601.2f), and its size is fixed by the targets announced at
    601.2c -- which is why it is a function of the target tuple and nothing
    else. `None` when there is nothing to add: a card without strive, one
    target, or none at all ("any number" includes zero, and zero targets is not
    a target beyond the first).

    Both sides price through here. Legality prices each target count as its own
    line in `_priced_tuples`, and `Game._cast` adds the same surcharge to the
    cost it charges, so the line offered and the mana taken cannot disagree.
    """
    if card.strive is None:
        return None
    extra = max(0, len(targets) - 1)
    return card.strive.scaled(extra) if extra else None


def _priced_tuples(
    state: GameState,
    pid: int,
    oid: int,
    card: CardDef,
    tuples,
    cost: ManaCost,
    net_generic: int,
    pool,
    sources,
    *,
    any_type: bool,
    any_color: bool = False,
    targeted_discount: bool = False,
    discount_for=None,
    life_tax_for=None,
    life_budget: int = 0,
) -> list[tuple[tuple, tuple[int, ...]]]:
    """Each target tuple this line may be cast with, and what paying for it taps.

    For almost every card that is one payment shared by every tuple, because the
    targets do not change the price -- `req` is solved once and an unpayable
    line offers nothing.

    **A targeted discount is the second exception**, beside strive below.
    "Aura spells you cast **that target enchanted creature** cost {3} less"
    (Strong Back) makes the price a question about *which* target was chosen, so
    when such a static is on the board each tuple is solved on its own. The gate
    that got this far read the clause generously -- it had no tuple to read --
    and this is where a tuple that cannot actually be paid for is dropped.

    **Strive** is the exception: a tuple's price grows with its length, so the
    same line is affordable with one target and not with three. Each count is
    solved separately, from zero upwards, stopping at the first that cannot be
    paid (more targets never cost less). A count past that is not offered at
    all -- the rule the rest of legality keeps: an action on offer is an action
    the engine can honour, and a three-target Call the Coppercoats on four lands
    would be a cast that fails at payment.

    And the tuples are **re-enumerated one size at a time** rather than
    filtered. `enumerate_target_tuples` lists "any number" subsets largest first
    and cuts the list at `MAX_TARGET_OPTIONS`, so with six creatures on the board
    every kept tuple has four or more of them in it -- filtering those for an
    affordable size would leave only the empty one. Capping the size alone is not
    enough either: fifteen two-creature pairs fill the list before any single
    target is reached, and one target is the line that costs nothing extra. Each
    size gets its own enumeration, largest first, then the empty tuple last, the
    order the rest of targeting keeps.

    **A life tax is the third**, and it is the cheap one: "spells your opponents
    cast that target this creature cost an additional 3 life to cast" (Terror of
    the Peaks) also makes the price a question about which target was chosen,
    but it is paid in a resource the mana solver knows nothing about. So it is
    settled before any solving happens -- the tuples the caster cannot afford
    the life for are simply not there -- and a tuple that survives is priced by
    exactly the code that priced it before. `life_tax_for` is `None` unless such
    a static is on the board, which is the common case and costs nothing.
    """
    if life_tax_for is not None:
        # 118.4: life may be paid down to exactly 0, so a tax of 3 is payable at
        # 3 life and not at 2. `life_budget` is what is left after the Phyrexian
        # pips this line already bought, since both come out of the same total.
        # A tax of zero is not a payment, so it survives a frozen life total
        # (`life_budget` is -1 then) as well as an empty one.
        tuples = [
            targets
            for targets in tuples
            if (tax := life_tax_for(targets)) == 0 or tax <= life_budget
        ]
        if not tuples:
            return []

    def solve(extra: int, aimed_at=None):
        total = cost
        if extra and card.strive is not None:
            surcharge = card.strive.scaled(extra)
            if any_type:
                surcharge = surcharge.as_any_type()
            elif any_color:
                surcharge = surcharge.as_any_color()
            total = cost.plus(surcharge)
        # Solve rather than merely test: the solution names the permanents that
        # would tap, which is what lets the client show a hovered spell eating
        # into the mana row.
        req = total.with_x(0)
        net = net_generic
        if targeted_discount and discount_for is not None and aimed_at is not None:
            # The generous discount the caller already netted out, put back and
            # replaced by the one *this* tuple earns.
            net = net_generic + discount_for(None) - discount_for(aimed_at)
        payment = solve_payment(req.with_generic(req.generic + net), pool, sources)
        if payment is None:
            return None
        # Sources only.  `Payment` does not itemise which floating mana it spent,
        # so claiming a pool pip here would be a guess; the client dims source
        # pips and says nothing about the pool.
        return tuple(dict.fromkeys(tap[0] for tap in payment.taps))

    if card.strive is None:
        if targeted_discount:
            priced_each: list[tuple[tuple, tuple[int, ...]]] = []
            for targets in tuples:
                pays = solve(0, targets)
                if pays is not None:
                    priced_each.append((targets, pays))
            return priced_each
        pays = solve(0)
        return [] if pays is None else [(targets, pays) for targets in tuples]

    largest = max((len(targets) for targets in tuples), default=0)
    by_extra: list[tuple[int, ...]] = []
    for extra in range(max(0, largest - 1) + 1):
        pays = solve(extra)
        if pays is None:
            break
        by_extra.append(pays)
    if not by_extra:
        return []
    priced: list[tuple[tuple, tuple[int, ...]]] = []
    for size in range(min(largest, len(by_extra)), 0, -1):
        exact = [
            targets
            for targets in enumerate_target_tuples(
                state,
                pid,
                card.targets,
                oid,
                exclude_sid=state.objects[oid].stack_id,
                size_cap=size,
            )
            if len(targets) == size
        ]
        priced.extend((targets, by_extra[size - 1]) for targets in exact)
    if () in tuples:
        priced.append(((), by_extra[0]))
    return priced


def _cast_variant(
    state: GameState,
    pid: int,
    oid: int,
    card: CardDef,
    tuples,
    *,
    extra_generic: int,
    kicked: bool = False,
    gift_to: int | None = None,
    evoked: bool = False,
    # The **price**, not a flag: warp may be handed to this card by a static on
    # another permanent, so there is nothing on the card to read it back off.
    # `Action.warp` carries the same string for the same reason.
    warp: str | None = None,
    emerge_oid: int | None = None,
    flashback: bool = False,
    alternative: bool = False,
    overloaded: bool = False,
    additional_times: int = 0,
    additional_choice: int | None = None,
    spree_modes: tuple[int, ...] = (),
    free: bool = False,
    from_library_top: bool = False,
    foretold: bool = False,
    face_down: bool = False,
    second_face: bool = False,
    prepared: bool = False,
    fused: bool = False,
    bestowed: bool = False,
    mutated: bool = False,
    pay_generic: int = 0,
    alt_cost: str | None = None,
) -> list[Action]:
    from .costs import cost_reduction, mana_sources, spell_purpose, variant_reduction
    from .stack import modal_cast_ok

    # 601.2b: a spell that cannot choose the modes it is required to choose
    # cannot be cast. Asked on every variant rather than in `_cast_options`
    # because flashback, foretell and the second face all reach a card without
    # passing through it -- and a mode-owned target is no more available to a
    # flashed-back spell than to a fresh one.
    if not modal_cast_ok(state, pid, card, oid):
        return []

    # Restricted mana ("spend only to cast a creature spell") is offered or
    # withheld here, and `game._cast` must ask the same question with the same
    # answer -- both go through `spell_purpose`.
    purpose = spell_purpose(card)
    sources = mana_sources(state, pid, purpose=purpose)
    # The pool asked the same question: a pip carrying "spend this mana only to
    # cast spells" is a restricted *source* that has already been made, and the
    # offer would otherwise plan on mana this cast is not allowed to take.
    pool = state.players[pid].mana_pool.spendable(purpose)

    # "This spell costs {X} less to cast **this way**": a discount belonging to
    # the variant rather than to the card, so it is read on the branch that
    # selected the price and nowhere else. Card-level `cost_reduction` below is
    # variant-blind by design -- Ghalta costs less however you cast it -- and a
    # rider written there would discount the printed hand cast too.
    variant_less = 0

    if free:
        # "…without paying its mana cost." Plot (702.171a). First in the chain
        # because it replaces the price outright rather than adjusting it, and
        # because a plotted card has no other variant to be confused with -- it
        # is offered from exile under its own permission and nowhere else.
        #
        # `FREE_COST`, not `card.mana_cost` with a discount: 601.2b's "without
        # paying its mana cost" is not a reduction to zero, and the difference
        # shows on an X spell, where a discount leaves X payable and this does
        # not.
        cost = FREE_COST
    elif alt_cost is not None:
        # "…its owner may cast it **for {2} rather than its mana cost**" --
        # airbend. Second in the chain, directly under the free line, because
        # it is the same shape: a price that *replaces* the printed one rather
        # than adjusting it. The discounts below still apply to it, which is
        # right -- a cost reduction reduces whatever cost is actually being
        # paid (601.2f) -- and they reach only its generic part, which is all
        # of it.
        cost = ManaCost.parse(alt_cost)
    elif flashback and card.flashback is not None:
        cost = card.flashback.mana
        variant_less = variant_reduction(state, pid, card.flashback, oid)
    elif emerge_oid is not None and card.emerge is not None:
        cost = card.emerge
    elif evoked and card.evoke is not None:
        cost = card.evoke
    elif warp is not None:
        # Parsed from the string rather than read off the card: the price may
        # have come from a `grant_warp` static, where there is no `ManaCost`
        # field to reach for. An **alternative** cost -- it replaces the
        # printed one outright -- so it sits in this chain beside evoke rather
        # than being netted into `extra_generic` like a discount.
        cost = ManaCost.parse(warp)
    elif bestowed and card.bestow is not None:
        cost = card.bestow
    elif mutated and card.mutate is not None:
        cost = card.mutate
    elif face_down:
        cost = MORPH_COST
    elif foretold and card.foretell is not None:
        cost = card.foretell
    elif overloaded and card.overload is not None:
        cost = card.overload
    elif alternative and card.alternative_cost is not None:
        # The mana half only. Everything else on the node -- the life and the
        # pitched card -- is charged by `game._cast` after the mana, the same
        # split flashback uses and the order 601.2g gives.
        cost = card.alternative_cost.mana
    elif kicked:
        cost = card.mana_cost.plus(card.kicker)
    else:
        cost = card.mana_cost
    if from_library_top:
        # "…pay life equal to its mana value **rather than** pay its mana cost."
        # A whole substitution rather than a reduction, which is what
        # `spell_cost_reduction` cannot do: the mana half becomes free here and
        # `Game._cast` charges the life. Priced before every discount below, so
        # nothing reduces a cost that is no longer being paid.
        cost = ManaCost.parse("")
    # 107.4f: a Phyrexian pip is one mana of its colour **or** 2 life, and the
    # choice is the caster's, made while the cost is being paid. So it is a
    # *line* -- the way kicker, overload and flashback are -- and not something
    # the payment solver decides on the player's behalf: casting Gitaxian Probe
    # off an Island and casting it for 2 life are two different things to do,
    # and a player at 3 life wants one of them and not the other.
    #
    # `paying_phyrexian` takes the bought pips out of the cost entirely, so
    # everything below prices a cost made only of mana and the life is charged
    # by `Game._cast` alongside it. One line per number of pips bought, which
    # is two for the whole printed cycle and three for Thundering Tanadon.
    printed = cost
    if player_pays_life_for_black(state, pid):
        # K'rrik: "For each {B} in a cost, you may pay 2 life rather than pay
        # that mana." The same choice the Phyrexian line already carries, so it
        # is made the same way -- each black pip becomes a `{B/P}` before the
        # lines are counted, and one line per number bought falls out below.
        # `Game._cast` makes the identical conversion before it charges.
        printed = printed.black_as_phyrexian()
    # Chromatic Orrery: "You may spend mana as though it were mana of any
    # color." A fact about the payer rather than about this card, so it is read
    # once for the whole variant and then folded in beside the permission a
    # `grant_playable` may also have left on the card. `Game._cast` reads the
    # same static at the same point.
    spends_any_color = player_spends_mana_as_any_color(state, pid)
    # Terror of the Peaks: "spells your opponents cast that target this creature
    # cost an additional 3 life to cast." An additional cost (601.2f) charged in
    # life, so it never reaches the payment solver -- it only narrows which
    # target tuples this player can afford to announce, which is what
    # `_priced_tuples` does with it. Asked once per cast line, and only when the
    # board actually has such a static on it.
    taxed = spell_life_tax_on_board(state)
    # "Your life total can't change" makes paying life impossible rather than
    # free (118.4 makes it a loss of life, and 601.2h makes an unpayable cost an
    # illegal cast), so a taxed line goes away entirely -- the same refusal
    # `costs.can_pay` already makes about a printed "pay 3 life". An *untaxed*
    # line is untouched by it, which is why this is a flag rather than a life
    # total of -1: a tax of zero is not a payment.
    life_frozen = taxed and life_locked(state, pid)
    out: list[Action] = []
    for phyrexian in range(printed.phyrexian_count + 1):
        cost, phyrexian_life = printed.paying_phyrexian(phyrexian)
        # 118.4: life may be paid down to exactly 0 and no further, so a player
        # at 1 is not offered the line a player at 2 is.
        if phyrexian_life > state.players[pid].life:
            continue
        if taxed:
            # The floor: the tax every tuple on this line pays whatever it aims
            # at. A `targeting` clause is left out of it (`targets=None` reads
            # such a static meanly), so this refuses only the lines that are
            # unaffordable however they are aimed.
            floor_tax = spell_life_tax(state, pid, card, None)
            if floor_tax and (
                life_frozen or phyrexian_life + floor_tax > state.players[pid].life
            ):
                continue
        permission = state.objects[oid]
        if permission.playable_any_type and permission.playable_live(state.turn):
            # "…and mana of any type can be spent to cast that spell." The colours
            # are relaxed once the price has been chosen, so it is the price this
            # line is actually offering that gets relaxed rather than the printed
            # cost -- and the discounts below still only touch the generic part,
            # which by now is all there is.
            cost = cost.as_any_type()
        elif (
            permission.playable_any_color and permission.playable_live(state.turn)
        ) or spends_any_color:
            # "…you may spend mana as though it were mana of any color to cast
            # it." Relaxed at the same moment and for the same reason as the
            # any-type waiver above, and read off the same card by `Game._cast`.
            # Either half does it: Elder Brain's permission on *this* card, or
            # Chromatic Orrery's static on the *player*, which says the same
            # thing about every cost and so also about this one.
            cost = cost.as_any_color()
        branch = chosen_additional(card, additional_choice)
        if additional_times and branch is not None:
            # The mana half of the additional cost, charged `additional_times` over.
            # Folded into the price *here* rather than paid separately, so legality
            # and the solver price the line the player is actually being offered.
            # `branch` rather than `card.additional_cost`, so a modal cost prices
            # the option this line is offering and not some other one.
            cost = cost.plus(branch.mana.scaled(additional_times))
        for mode in spree_modes:
            # Spree (702.166a): **every** chosen mode's price, folded in one at
            # a time. Summed rather than picked, which is the difference between
            # this and the branch above and the whole reason spree needed its
            # own slot: a player who chose two modes owes two prices.
            cost = cost.plus(card.spree[mode].mana)
        # `targets=None` is the generous reading a *gate* has to take: a
        # discount that asks what the spell is aiming at has no tuple to read
        # yet, and refusing here would drop a spell that is affordable once
        # discounted. `_priced_tuples` re-prices each tuple exactly.
        def _discount_for(aimed_at):
            return cost_reduction(state, pid, card, aimed_at) + variant_less

        discount = _discount_for(None)
        from .characteristics import _battlefield_statics

        targeted_discount = any(
            static.get("targeting") is not None
            for _, static in _battlefield_statics(state)
            if static.get("effect") == "spell_cost_reduction"
        )
        # Convoke and delve reduce the generic part, exactly as a cost reduction
        # does -- and go through the same clamp, so neither can make a spell free
        # of its coloured pips.
        discount += pay_generic
        if emerge_oid is not None:
            # The sacrifice pays for part of the spell. Generic-only and clamped by
            # `pay`, like every other reduction here.
            discount += state.card(emerge_oid).mana_cost.mana_value()

        # X is a *gate* here, not a value.  Legality asks only "is there any X this
        # is castable at", and `game._cast` then asks the player which one -- so the
        # action carries X = 0 and the forecast below is the floor.  Pinning it to
        # the maximum, as this used to, meant every Fireball was cast for everything
        # the player had and the choice was never offered at all.
        if (
            cost.x_count
            and max_affordable_x(cost, pool, sources, extra_generic=extra_generic - discount) < 0
        ):
            continue
        x = 0

        # Solved per target count for strive, once for everything else -- see
        # `_priced_tuples`. `x` is 0 here, as the gate above explains.
        priced = _priced_tuples(
            state,
            pid,
            oid,
            card,
            tuples,
            cost,
            extra_generic - discount,
            pool,
            sources,
            any_type=permission.playable_any_type and permission.playable_live(state.turn),
            any_color=(permission.playable_any_color and permission.playable_live(state.turn))
            or spends_any_color,
            targeted_discount=targeted_discount,
            discount_for=_discount_for,
            # Priced per tuple, exactly, because "that target this creature" is
            # a question about which target was chosen. The budget is what the
            # Phyrexian pips this line already bought have left over.
            life_tax_for=(
                (lambda aimed: spell_life_tax(state, pid, card, aimed)) if taxed else None
            ),
            life_budget=(-1 if life_frozen else state.players[pid].life - phyrexian_life),
        )
        if not priced:
            continue

        label_base = f"Cast {card.name}"
        if free:
            # The printed words, because this line is now offered *beside* the
            # paid one -- Dracogenesis. The client groups its rows by
            # `base_label`, so two identically-labelled lines for one card
            # would collapse into one row and the player would never see the
            # choice, which is the choice 601.2b gives them.
            label_base += " (without paying its mana cost)"
        if alt_cost is not None:
            # The price, in the label, for the reason the free line carries its
            # printed words: a card airbent out of a graveyard could also be
            # offered a flashback line, and two rows labelled "Cast Foo" would
            # collapse into one in the client and hide the choice.
            label_base += f" (for {alt_cost})"
        if kicked:
            # The card's own word: "kicked", "buyback".
            label_base += f" ({card.kicker_label})"
        if gift_to is not None:
            # The card's own words for what is promised, and the seat it is promised
            # to. Both belong on the chip: a player choosing this line is giving a
            # named opponent a named thing, and neither half is guessable from the
            # card name.
            promisee = state.players[gift_to].name or f"p{gift_to}"
            label_base += f" (gift {card.gift} to {promisee})"
        if evoked:
            # The card's own word for the cost: "evoked", "dash", "blitz". They are
            # one mechanism, and only the label tells the player which they are
            # buying.
            label_base += f" ({card.evoke_label})"
        if warp is not None:
            # The printed word plus the price, because the price is not on the
            # card: a player looking at an artifact in hand under Tannuk has no
            # other way to see what this line costs.
            label_base += f" (warp {warp})"
        if fused:
            label_base += " (fused)"
        if bestowed:
            label_base += " (bestowed)"
        if mutated:
            label_base += " (mutating)"
        if alternative:
            label_base += " (alternative cost)"
        if overloaded:
            label_base += " (overloaded)"
        if foretold:
            label_base += " (foretold)"
        if face_down:
            label_base = "Cast a face-down creature"
        if additional_times:
            label_base += f" (+{additional_times} additional)"
        if additional_choice is not None and branch is not None:
            # The branches are two prices for one spell, so the panel has to say
            # which one this row buys -- otherwise Bitter Triumph draws two
            # identical rows and the player picks blind.
            label_base += f" ({branch.describe()})"
        if spree_modes:
            # Which modes this row buys, in the card's own prices. The client
            # groups rows by `base_label`, so seven spree lines sharing one
            # label would collapse into a single row and the player would pick
            # blind between "mill four" and "all three at once".
            label_base += " (spree " + " ".join(
                card.spree[mode].describe() for mode in spree_modes
            ) + ")"
        if pay_generic:
            word = "convoking" if card.pay_generic_with == "tap_creatures" else "delving"
            label_base += f" ({word} {pay_generic})"
        if flashback:
            label_base += " (flashback)"
        if emerge_oid is not None:
            label_base += f" (emerge, sacrificing {state.card(emerge_oid).name})"
        if extra_generic:
            label_base += f" (+{extra_generic})"
        if phyrexian:
            # The price in life, in the label, because the client groups rows by
            # `base_label`: "Cast Gitaxian Probe" and "Cast Gitaxian Probe (paying
            # 2 life)" are two rows a player has to be able to tell apart before
            # clicking either, and they are otherwise identical.
            label_base += f" (paying {phyrexian_life} life)"
        actions: list[Action] = []
        for targets, pays in priced:
            label = label_base
            if targets:
                label += " -> " + ", ".join(describe_ref(state, ref) for ref in targets)
            actions.append(
                Action(
                    kind=ActionKind.CAST,
                    source=oid,
                    targets=targets,
                    x=x,
                    kicked=kicked,
                    gift_to=gift_to,
                    evoked=evoked,
                    warp=warp,
                    alternative=alternative,
                    overloaded=overloaded,
                    additional_times=additional_times,
                    additional_choice=additional_choice,
                    spree_modes=spree_modes,
                    cast_free=free,
                    from_library_top=from_library_top,
                    foretold=foretold,
                    face_down=face_down,
                    second_face=second_face,
                    prepared=prepared,
                    fused=fused,
                    bestowed=bestowed,
                    mutated=mutated,
                    pay_generic=pay_generic,
                    phyrexian=phyrexian,
                    flashback=flashback,
                    emerge_oid=emerge_oid,
                    label=label,
                    base_label=label_base,
                    pays=pays,
                )
            )
        out.extend(actions)
    return out
