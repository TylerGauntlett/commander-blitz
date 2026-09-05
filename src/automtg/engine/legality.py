"""Legal action enumeration -- the single source of truth for "what can I do?".

Both the HTTP action list and the RL action mask are built from this function, so
the two can never disagree about what is legal.  The ordering is deterministic:
the same state always produces the same list in the same order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import combat as combat_mod
from . import suspend as suspend_mod
from .actions import Action, PendingDecision
from .carddef import BESTOW_TARGET, MUTATE_TARGET, CardDef, Cost
from .characteristics import abilities_of, chars
from .costs import (
    can_pay,
    can_pay_mana,
    commander_cost,
    land_drops_available,
    offerable_mana_ability,
)
from .enums import ActionKind, DecisionKind, Keyword, Step, Zone
from .mana import ManaCost, max_affordable_x, solve_payment
from .primitives import sacrifice_forbidden
from .structs import TargetRef
from .targeting import describe_ref, enumerate_target_tuples

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def legal_actions(state: GameState) -> list[Action]:
    """Every action the player with the pending decision may take."""
    if state.game_over:
        return []
    decision = state.pending_decision
    if decision is None:
        return []

    kind = decision.kind
    if kind is DecisionKind.PRIORITY:
        return _priority_actions(state, decision.player)
    if kind is DecisionKind.DECLARE_ATTACKERS:
        return _attacker_actions(state, decision.player)
    if kind is DecisionKind.DECLARE_BLOCKERS:
        return _blocker_actions(state, decision.player)
    if kind is DecisionKind.MULLIGAN:
        return [
            Action(kind=ActionKind.MULLIGAN, label="Mulligan"),
            Action(kind=ActionKind.KEEP, label="Keep"),
        ]
    if kind is DecisionKind.MAY:
        return [
            Action(kind=ActionKind.YES, label="Yes"),
            Action(kind=ActionKind.NO, label="No"),
        ]
    return _choice_actions(decision)


# ----------------------------------------------------------------------
# choices
# ----------------------------------------------------------------------


def _choice_actions(decision: PendingDecision) -> list[Action]:
    out = [
        Action(
            kind=ActionKind.CHOOSE,
            choice=i,
            label=decision.options[i].label,
            targets=(decision.options[i].ref,) if decision.options[i].ref else (),
        )
        for i in decision.remaining_options
    ]
    if decision.allow_done and not decision.is_complete:
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done"))
    if not out:
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done"))
    return out


# ----------------------------------------------------------------------
# combat declarations
# ----------------------------------------------------------------------


def _attacker_actions(state: GameState, pid: int) -> list[Action]:
    out: list[Action] = []
    for oid in combat_mod.legal_attackers(state):
        name = state.card(oid).name
        # Per attacker, not once for the whole declaration: "that player can't
        # attack you" is a restriction on a *pair*, so two creatures the same
        # player controls can have different defender lists in the same combat
        # once one of them was borrowed from somebody else.
        defenders = combat_mod.legal_defenders(state, oid)
        walkers = combat_mod.legal_planeswalker_defenders(state, oid)
        for defender in defenders:
            # Propaganda: "creatures can't attack you **unless** their
            # controller pays {2}". An unpayable tax is a prohibition (508.1g),
            # so the action is withheld rather than offered and rewound -- and
            # the price goes in the label, because a player choosing between
            # defenders is choosing between prices.
            tax = combat_mod.attack_tax_cost(state, oid, defender)
            if tax is not None and not combat_mod.attack_tax_payable(
                state, oid, defender, tax
            ):
                continue
            price = f" (pay {tax.mana})" if tax is not None else ""
            out.append(
                Action(
                    kind=ActionKind.ADD_ATTACKER,
                    source=oid,
                    targets=(TargetRef.player(defender),),
                    label=f"Attack p{defender} with {name}{price}",
                )
            )
        # 506.2: a planeswalker is a *third* thing a creature may attack, beside
        # its controller. Offered as its own action carrying the planeswalker's
        # oid, so the choice is made once at declaration and nothing downstream
        # has to re-derive it.
        for walker in walkers:
            out.append(
                Action(
                    kind=ActionKind.ADD_ATTACKER,
                    source=oid,
                    targets=(TargetRef.obj(walker),),
                    label=f"Attack {state.card(walker).name} with {name}",
                )
            )
    # "…attacks this combat if able" is enforced by withholding the way out of
    # the declaration, which is the only lever legality has: there is no action
    # for "refuse to attack". A creature that cannot attack owes nothing, which
    # `attack_required` has already accounted for, so this can never deadlock.
    #
    # `attacks_valid` is withheld for the same reason and by the same lever, but
    # it is a restriction rather than a requirement: "this creature can't attack
    # alone" is judged on the finished declaration, so a lone attacker under it
    # has to add a second one before the step can end -- the mirror of menace
    # withholding "Done blocking" below.
    if not combat_mod.unmet_attack_requirements(state) and combat_mod.attacks_valid(
        state, pid
    ):
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done attacking"))
    elif not out:
        # Nothing left to add and the declaration is still invalid: the
        # can't-attack-alone creature is the only thing that could attack at
        # all. Offering nothing is a game that cannot continue, so "Done" comes
        # back and `finish_attackers` retracts the attack that was never legal
        # -- exactly what `_blocker_actions` does with `drop_illegal_blocks`.
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done attacking"))
    return out


def _blocker_actions(state: GameState, pid: int) -> list[Action]:
    out: list[Action] = []
    for blocker_oid, attacker_oid in combat_mod.legal_blocks(state, pid):
        out.append(
            Action(
                kind=ActionKind.ADD_BLOCKER,
                source=blocker_oid,
                targets=(TargetRef.obj(attacker_oid),),
                label=f"Block {state.card(attacker_oid).name} with {state.card(blocker_oid).name}",
            )
        )
    if combat_mod.blocks_valid(state, pid):
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done blocking"))
    elif not out:
        # Nothing left to add and the declaration is still invalid: a
        # `require_all` block the player can no longer complete. Offering
        # nothing at all is a game that cannot continue, so "Done" is offered
        # and `finish_blockers` retracts the blocks that were never legal.
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done blocking"))
    return out


# ----------------------------------------------------------------------
# priority
# ----------------------------------------------------------------------


def _priority_actions(state: GameState, pid: int) -> list[Action]:
    out: list[Action] = [Action(kind=ActionKind.PASS, label="Pass")]
    sorcery_speed = _can_act_at_sorcery_speed(state, pid)

    if sorcery_speed and land_drops_available(state, pid) > 0:
        out.extend(_land_actions(state, pid))

    # Split second (702.61a): while such a spell is on the stack, players may
    # not cast spells or activate abilities that aren't mana abilities.
    #
    # Enforced by *withholding the actions*, which is the only lever legality
    # has and is also the honest one: there is no "you may not respond" action
    # to offer. Special actions -- playing a land, suspending -- are neither
    # casting nor activating, so 702.61a leaves them alone and so does this.
    if split_second_active(state):
        out.extend(_mana_ability_actions(state, pid))
        return out

    out.extend(_cast_actions(state, pid, sorcery_speed))
    out.extend(_suspend_actions(state, pid, sorcery_speed))
    out.extend(_activate_actions(state, pid, sorcery_speed))
    return out


def split_second_active(state: GameState) -> bool:
    """Is a spell with split second waiting on the stack?

    Read off the stack rather than written as a flag somewhere, so it ends
    exactly when the spell leaves -- countered, resolved or fizzled alike --
    with nothing to remember to clear.
    """
    for item in state.stack:
        if not item.is_spell:
            continue
        if state.registry.get(item.def_id).split_second:
            return True
    return False


def _mana_ability_actions(state: GameState, pid: int) -> list[Action]:
    """Only the mana abilities out of the full activated list.

    Filtered from `_activate_actions` rather than re-derived, so the two can
    never disagree about what a mana ability is or what it costs.
    """
    return [
        action
        for action in _activate_actions(state, pid, sorcery_speed=False)
        if _is_mana_ability(state, action)
    ]


def _is_mana_ability(state: GameState, action: Action) -> bool:
    if action.kind is not ActionKind.ACTIVATE or action.source is None:
        return False
    abilities = abilities_of(state, action.source)
    if action.ability_index is None or action.ability_index >= len(abilities):
        return False
    return bool(abilities[action.ability_index].is_mana_ability)


def _suspend_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    """"Rather than cast this card from your hand, you may pay {G}…"

    A special action rather than a variant of casting: nothing goes on the
    stack, so it is offered under the same timing the card itself would need
    (rule 702.62a) but produces its own `ActionKind`.
    """
    from .costs import can_pay_mana

    out: list[Action] = []
    for oid in state.players[pid].hand:
        card = state.card(oid)
        if card.suspend is None:
            continue
        if not _timing_ok(card, sorcery_speed):
            continue
        cost, counters = card.suspend
        if not can_pay_mana(state, pid, cost):
            continue
        out.append(
            Action(
                kind=ActionKind.SUSPEND,
                source=oid,
                label=f"Suspend {card.name} ({counters} counters)",
            )
        )
    # Foretell shares the action kind, and the sharing is the argument: both are
    # "exile this from hand now, cast it later", neither uses the stack, and
    # neither can be countered. The {2} is fixed by rule 702.143a; the card names
    # only the later price.
    #
    # Timing is *your turn at sorcery speed*, which is stricter than the card's
    # own -- an instant with foretell may still only be foretold on your turn.
    if sorcery_speed:
        for oid in state.players[pid].hand:
            card = state.card(oid)
            if card.foretell is None:
                continue
            if not can_pay_mana(state, pid, ManaCost.parse(suspend_mod.FORETELL_COST)):
                continue
            out.append(
                Action(
                    kind=ActionKind.SUSPEND,
                    source=oid,
                    label=f"Foretell {card.name}",
                )
            )
    return out


def _can_act_at_sorcery_speed(state: GameState, pid: int) -> bool:
    return (
        state.active_player == pid
        and state.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN)
        and not state.stack
    )


def _land_actions(state: GameState, pid: int) -> list[Action]:
    """One action per land *object* in hand, not per land name.

    Two Forests are the same play in rules terms, but the UI keys everything by
    object id: it dims any hand card no action names.  Deduplicating by
    ``card.id`` here made the second and third Forest unclickable and
    undraggable, which is a much worse trade than a slightly wider action list.
    """
    from .characteristics import (
        player_plays_lands_from_graveyard,
        player_plays_lands_from_library_top,
    )

    zones = [state.players[pid].hand]
    if player_plays_lands_from_graveyard(state, pid):
        # Ramunap Excavator, Crucible of Worlds, Ancient Greenwarden. Still one
        # land drop -- this widens *where* a land may be played from, not how
        # many, which `lands_played` already governs.
        zones.append(state.players[pid].graveyard)
    # "You may **play** the exiled card this turn" covers a land, which is
    # played rather than cast -- so the permission has to reach both halves or
    # Florian's land half silently does nothing. Filtered per object below,
    # because only the flagged cards in exile are offered.
    if any(
        state.objects[oid].playable_by == pid
        and state.objects[oid].playable_turn == state.turn
        for oid in state.players[pid].exile
    ):
        zones.append(
            [
                oid
                for oid in state.players[pid].exile
                if state.objects[oid].playable_by == pid
                and state.objects[oid].playable_turn == state.turn
            ]
        )
    if player_plays_lands_from_library_top(state, pid) and state.players[pid].library:
        # The top card only -- which is what the cards say, and the only part
        # of a hidden zone anybody is entitled to see.
        zones.append(state.players[pid].library[:1])

    out: list[Action] = []
    for zone in zones:
        for oid in zone:
            card = state.card(oid)
            if card.is_land:
                out.append(
                    Action(kind=ActionKind.PLAY_LAND, source=oid, label=f"Play {card.name}")
                )
            # A **modal** double-faced card whose other half is a land -- Malakir
            # Rebirth // Malakir Mire. The front is cast and the back is
            # *played*, which is the whole difference from every other second
            # face the engine has: it uses no stack, consumes the land drop, and
            # is offered here rather than beside the cast lines.
            #
            # Offered only from hand: `second_face_zone` is about where a half
            # may be *cast* from, and no printed MDFC plays its land half out of
            # a graveyard.
            face = _second_face_land(state, card)
            if face is not None and zone is state.players[pid].hand:
                out.append(
                    Action(
                        kind=ActionKind.PLAY_LAND,
                        source=oid,
                        second_face=True,
                        label=f"Play {face.name}",
                    )
                )
    return out


def _second_face_land(state: GameState, card: CardDef) -> CardDef | None:
    """The card's other half, when that half is a land."""
    if card.second_face is None:
        return None
    face = state.registry.get(card.second_face)
    return face if face.is_land else None


def _cast_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    out: list[Action] = []
    if state.players[pid].epic_source is not None:
        # Epic: "spend the rest of the game casting no spells" (702.50a). A
        # legality gate rather than a cost or a condition, because it is not
        # about any one card -- and lands are unaffected, which is why it is
        # here rather than in `legal_actions`.
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
        if not _timing_ok(card, sorcery_speed):
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
        if not card.is_land and affordable and _timing_ok(card, sorcery_speed):
            out.extend(
                _cast_variant(
                    state, pid, oid, card,
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
        if not _timing_ok(card, sorcery_speed):
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
        if obj.playable_by != pid or obj.playable_turn != state.turn:
            continue
        # "…you may cast **a spell** from among those cards", singular out of
        # however many were milled. Counted per granting permanent, so two
        # Lockes are two spells and one Locke milling three cards is still one.
        if obj.playable_group is not None and state.turn_ledger.activations(
            obj.playable_group, GRAVEYARD_CAST_SLOT
        ):
            continue
        card = state.card(oid)
        if card.is_land or not _timing_ok(card, sorcery_speed):
            continue
        out.extend(_cast_options(state, pid, oid, card, extra_generic=0))

    # Foretold cards are cast from **exile**, at the foretell price, and only on
    # a turn after the one they were foretold on -- `foretold_cards` is what
    # enforces the "later", because a card foretold and cast the same turn is
    # the printed cost paid in two instalments with the discount thrown in.
    for oid in suspend_mod.foretold_cards(state, pid):
        card = state.card(oid)
        if not _timing_ok(card, sorcery_speed):
            continue
        ft_tuples = enumerate_target_tuples(state, pid, card.targets, oid)
        out.extend(
            _charge_additional_cost(
                state, pid, oid, card,
                _cast_variant(
                    state, pid, oid, card, ft_tuples,
                    extra_generic=0, foretold=True,
                ),
                lambda times, choice, oid=oid, card=card, tuples=ft_tuples: (
                    _cast_variant(
                        state, pid, oid, card, tuples,
                        extra_generic=0, foretold=True,
                        additional_times=times, additional_choice=choice,
                    )
                ),
            )
        )

    # Retrace: the graveyard is a third place a card can be cast from, widened
    # here the same way `_land_actions` widens where a land may be played from.
    from .costs import can_pay

    for oid in state.players[pid].graveyard:
        card = state.card(oid)
        # Aftermath (702.127a): "cast this half only from your graveyard". The
        # same widening retrace makes, and the restriction is where the second
        # face is *offered* rather than a condition on the cast -- there is no
        # hand line to refuse.
        out.extend(_second_face_actions(state, pid, oid, card, Zone.GRAVEYARD, sorcery_speed))
        if not _timing_ok(card, sorcery_speed):
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
        if card.flashback is not None and can_pay(
            state, pid, card.flashback.without_mana(), oid
        ):
            fb_tuples = enumerate_target_tuples(
                state, pid, card.targets, oid,
                exclude_sid=state.objects[oid].stack_id,
            )
            # "…for its flashback cost **and any additional costs**" is printed
            # in flashback's own reminder text, and 601.2f says it anyway.
            out.extend(
                _charge_additional_cost(
                    state, pid, oid, card,
                    _cast_variant(
                        state, pid, oid, card, fb_tuples,
                        extra_generic=0, flashback=True,
                    ),
                    lambda times, choice, oid=oid, card=card, tuples=fb_tuples: (
                        _cast_variant(
                            state, pid, oid, card, tuples,
                            extra_generic=0, flashback=True,
                            additional_times=times, additional_choice=choice,
                        )
                    ),
                )
            )

    for oid in state.players[pid].command:
        obj = state.objects[oid]
        if not obj.is_commander:
            continue
        card = state.card(oid)
        if not _timing_ok(card, sorcery_speed):
            continue
        out.extend(
            _cast_options(state, pid, oid, card, extra_generic=commander_cost(state, oid))
        )
    return out


def _prepared_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    """"While it's prepared, you may cast a copy of its spell."

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
        if not _timing_ok(face, sorcery_speed):
            continue
        tuples = enumerate_target_tuples(state, pid, face.targets, obj.oid)
        if not tuples:
            continue
        out.extend(
            _cast_variant(state, pid, obj.oid, face, tuples, extra_generic=0, prepared=True)
        )
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
    if not _timing_ok(face, sorcery_speed):
        return []
    tuples = enumerate_target_tuples(
        state, pid, face.targets, oid, exclude_sid=state.objects[oid].stack_id
    )
    if not tuples:
        return []
    out = _cast_variant(
        state, pid, oid, face, tuples, extra_generic=0, second_face=True
    )
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


def _timing_ok(card: CardDef, sorcery_speed: bool) -> bool:
    if card.is_instant or Keyword.FLASH.value in card.keywords:
        return True
    return sorcery_speed


def _cast_options(
    state: GameState, pid: int, oid: int, card: CardDef, *, extra_generic: int
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
    tuples = enumerate_target_tuples(
        state, pid, card.targets, oid, exclude_sid=exclude_sid
    )
    if not tuples:
        return []

    out = _cast_variant(state, pid, oid, card, tuples, extra_generic=extra_generic, kicked=False)
    if card.kicker is not None:
        out += _cast_variant(state, pid, oid, card, tuples, extra_generic=extra_generic, kicked=True)
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
        state, pid, oid, card, out,
        lambda times, choice: _cast_variant(
            state, pid, oid, card, tuples, extra_generic=extra_generic,
            additional_times=times, additional_choice=choice,
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


def _graveyard_cast_permission(
    state: GameState, pid: int, card: CardDef, oid: int | None = None
):
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
    emerge_oid: int | None = None,
    flashback: bool = False,
    alternative: bool = False,
    overloaded: bool = False,
    additional_times: int = 0,
    additional_choice: int | None = None,
    from_library_top: bool = False,
    foretold: bool = False,
    face_down: bool = False,
    second_face: bool = False,
    prepared: bool = False,
    fused: bool = False,
    bestowed: bool = False,
    mutated: bool = False,
    pay_generic: int = 0,
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
    sources = mana_sources(state, pid, purpose=spell_purpose(card))
    pool = state.players[pid].mana_pool

    # "This spell costs {X} less to cast **this way**": a discount belonging to
    # the variant rather than to the card, so it is read on the branch that
    # selected the price and nowhere else. Card-level `cost_reduction` below is
    # variant-blind by design -- Ghalta costs less however you cast it -- and a
    # rider written there would discount the printed hand cast too.
    variant_less = 0

    if flashback and card.flashback is not None:
        cost = card.flashback.mana
        variant_less = variant_reduction(state, pid, card.flashback, oid)
    elif emerge_oid is not None and card.emerge is not None:
        cost = card.emerge
    elif evoked and card.evoke is not None:
        cost = card.evoke
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
    out: list[Action] = []
    for phyrexian in range(printed.phyrexian_count + 1):
        cost, phyrexian_life = printed.paying_phyrexian(phyrexian)
        # 118.4: life may be paid down to exactly 0 and no further, so a player
        # at 1 is not offered the line a player at 2 is.
        if phyrexian_life > state.players[pid].life:
            continue
        permission = state.objects[oid]
        if permission.playable_any_type and permission.playable_turn == state.turn:
            # "…and mana of any type can be spent to cast that spell." The colours
            # are relaxed once the price has been chosen, so it is the price this
            # line is actually offering that gets relaxed rather than the printed
            # cost -- and the discounts below still only touch the generic part,
            # which by now is all there is.
            cost = cost.as_any_type()
        branch = chosen_additional(card, additional_choice)
        if additional_times and branch is not None:
            # The mana half of the additional cost, charged `additional_times` over.
            # Folded into the price *here* rather than paid separately, so legality
            # and the solver price the line the player is actually being offered.
            # `branch` rather than `card.additional_cost`, so a modal cost prices
            # the option this line is offering and not some other one.
            cost = cost.plus(branch.mana.scaled(additional_times))
        discount = cost_reduction(state, pid, card) + variant_less
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
        if cost.x_count and max_affordable_x(
            cost, pool, sources, extra_generic=extra_generic - discount
        ) < 0:
            continue
        x = 0

        # Solve rather than merely test: the solution names the permanents that
        # would tap, which is what lets the client show a hovered spell eating into
        # the mana row.  `can_pay_mana` would run the same solver and discard it.
        req = cost.with_x(x)
        req = req.with_generic(req.generic + extra_generic - discount)
        payment = solve_payment(req, pool, sources)
        if payment is None:
            continue
        # Sources only.  `Payment` does not itemise which floating mana it spent, so
        # claiming a pool pip here would be a guess; the client dims source pips and
        # says nothing about the pool.
        pays = tuple(dict.fromkeys(tap[0] for tap in payment.taps))

        label_base = f"Cast {card.name}"
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
        for targets in tuples:
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
                    alternative=alternative,
                    overloaded=overloaded,
                    additional_times=additional_times,
                    additional_choice=additional_choice,
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


#: The gates :func:`unplayable_reason` can name, in the order it checks them.
UNPLAYABLE_REASONS = ("priority", "timing", "land_drop", "mana", "targets")


def unplayable_reason(state: GameState, pid: int, oid: int) -> str | None:
    """Why this card in ``pid``'s hand cannot be played right now, for the UI.

    The client dims any hand card that no action names, which tells the player
    "no" without ever telling them why -- "not enough mana", "sorcery, and it
    is not your main phase" and "no legal target" all look identical.  This
    walks the same gates :func:`_priority_actions` walks, in the same order,
    and names the first one that closes.

    Returns ``None`` exactly when a legal action for ``oid`` exists.  That is an
    invariant worth stating out loud, because this function necessarily
    restates logic owned by the generators above: it is a diagnostic, never an
    authority, and :func:`legal_actions` remains the only source of truth.
    ``tests/unit/test_legality_reasons.py`` pins the two together.
    """
    decision = state.pending_decision
    if (
        state.game_over
        or decision is None
        or decision.kind is not DecisionKind.PRIORITY
        or decision.player != pid
    ):
        return "priority"

    card = state.card(oid)
    sorcery_speed = _can_act_at_sorcery_speed(state, pid)

    if card.is_land:
        if not sorcery_speed:
            return "timing"
        if land_drops_available(state, pid) <= 0:
            return "land_drop"
        return None

    if not _timing_ok(card, sorcery_speed):
        return "timing"

    # Hand cards never owe commander tax -- that is a command-zone cost only.
    from .costs import cost_reduction, spell_purpose

    discount = cost_reduction(state, pid, card)
    purpose = spell_purpose(card)
    x = 0
    if card.mana_cost.x_count:
        from .costs import mana_sources

        # The same gate `_cast_variant` applies, and it must stay X = 0
        # afterwards for the same reason: this diagnostic has to agree with the
        # action list, and that list now offers the spell at its floor.
        if (
            max_affordable_x(
                card.mana_cost,
                state.players[pid].mana_pool,
                mana_sources(state, pid, purpose=purpose),
                extra_generic=-discount,
            )
            < 0
        ):
            return "mana"
    if not can_pay_mana(
        state, pid, card.mana_cost, x=x, extra_generic=-discount, purpose=purpose
    ):
        return "mana"

    exclude_sid = state.objects[oid].stack_id
    if not enumerate_target_tuples(
        state, pid, card.targets, oid, exclude_sid=exclude_sid
    ):
        return "targets"
    return None


def _activate_zones(state: GameState, pid: int) -> list[tuple[int, Zone]]:
    """Every object whose activated abilities this player might be offered.

    The battlefield, plus this player's hand for cycling and its relatives.
    `Ability.active_zones` is what decides per ability -- being *in* hand is not
    the permission, saying so on the ability is -- so the hand is walked here
    and filtered below rather than the two being conflated.

    Only this player's hand: it is a hidden zone, and offering actions from an
    opponent's would leak it into `legal_actions`.
    """
    pairs: list[tuple[int, Zone]] = [(oid, Zone.BATTLEFIELD) for oid in state.battlefield]
    pairs += [(oid, Zone.HAND) for oid in state.players[pid].hand]
    # …and this player's graveyard, for embalm and its relatives. Public, unlike
    # the hand, but still only this player's: the ability belongs to the card's
    # owner and nobody else may activate it.
    pairs += [(oid, Zone.GRAVEYARD) for oid in state.players[pid].graveyard]
    return pairs


def _activate_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    out: list[Action] = []
    manual_mana = state.players[pid].manual_mana
    offer_all = state.players[pid].offer_all_abilities
    for oid, zone in _activate_zones(state, pid):
        obj = state.objects.get(oid)
        if obj is None or obj.abilities_locked:
            continue
        # A card in hand has no controller in the battlefield sense of the word;
        # its owner is the one who may activate it.
        whose = obj.controller if zone is Zone.BATTLEFIELD else obj.owner
        if whose != pid:
            continue
        if obj.face_down and zone is Zone.BATTLEFIELD:
            # A face-down permanent has **no abilities** (707.2), so the hidden
            # card's are not offered. What it does have is exactly one thing:
            # turning face up, which is why that reuses `ability_index` 0 rather
            # than needing an `ActionKind` of its own -- and so the RL action
            # space is unchanged.
            out.extend(_turn_face_up_actions(state, pid, obj))
            continue
        card = state.card_of(obj)
        # Resolved at most once per object, and only for an object that actually
        # has a suppressed tap-only mana ability to decide about -- so a board of
        # lands never pays for the second scan.
        show_tap_only: bool | None = None
        # Derived, not printed: a permanent that has lost its abilities must
        # not be offered them, and one granted "{T}: Add {C}" must be.
        for ability in abilities_of(state, oid):
            if ability.is_mana_ability and not offerable_mana_ability(ability):
                if show_tap_only is None:
                    show_tap_only = manual_mana or (
                        offer_all
                        and _offers_something_else(
                            state, pid, oid, card, zone, sorcery_speed
                        )
                    )
                if not (show_tap_only and ability.mana_options):
                    # A tap-only mana ability is activated automatically by the
                    # payment solver, so offering it here would add noise and a
                    # second way to spend the same permanent. Two things buy it
                    # back. `manual_mana` is the request to choose which land to
                    # tap and which colour a dual makes. `offer_all_abilities` is
                    # narrower and needs no toggle: a permanent that offers
                    # something *else* is one the player is going to click, and
                    # then it must show everything it can do -- otherwise Mind
                    # Stone's single visible row is its sacrifice ability, and
                    # one click spends the artifact.
                    #
                    # Anything else is *not* the solver's -- `mana_sources`
                    # collects only `Cost.is_tap_only()` abilities -- so a
                    # Signet's "{1}, {T}: Add {W}{U}" has no automatic path at
                    # all. Skipping every mana ability, as this used to, left 27
                    # shipped cards (every Signet, Cabal Coffers, Prophetic
                    # Prism, the filter and Vivid lands) with no path in the
                    # engine that could activate them.
                    # `costs.offerable_mana_ability` is the complement of the
                    # solver's own test so the two cannot drift apart.
                    continue
            # A gate, not a value -- see `_cast_variant`. `game._activate` asks
            # which X the player wants; this only decides whether any is payable.
            x = 0
            tuples = _ability_aims(state, pid, oid, ability, zone, sorcery_speed)
            if tuples is None:
                continue
            aims = tuples
            # "Add one mana of any colour" is five different things to do, and
            # which one is the player's call -- the solver is not making it,
            # because it never sees this ability at all. One action per yield,
            # each naming what it produces so the panel reads as five colour
            # chips rather than five copies of one line.
            label_base = f"{card.name}: {ability.text or 'activate'}"
            for mana_option in _mana_option_indices(state, oid, ability):
                option_label = _mana_option_label(state, oid, ability, mana_option)
                for ability_modes, targets in aims:
                    label = label_base
                    if option_label:
                        label += f" ({option_label})"
                    if targets:
                        label += " -> " + ", ".join(
                            describe_ref(state, ref) for ref in targets
                        )
                    out.append(
                        Action(
                            kind=ActionKind.ACTIVATE,
                            source=oid,
                            ability_index=ability.index,
                            targets=targets,
                            x=x,
                            ability_modes=ability_modes,
                            mana_option=mana_option,
                            label=label,
                            # Shared across the yields on purpose: it is the row
                            # identity, so the five colours of Commander's Sphere
                            # collapse into one row wearing five chips.
                            base_label=label_base,
                            option_label=option_label,
                        )
                    )
    return out


def _turn_face_up_actions(state: GameState, pid: int, obj) -> list[Action]:
    """The one thing a face-down permanent can do (707.9a, 701.34c).

    Two prices, and which one applies is *how the permanent got there*: a card
    cast face down for morph turns up for its **morph cost**, and a manifested
    creature card turns up for its **printed mana cost**. A manifested
    non-creature card can never be turned up at all, which is the whole reason
    manifest is not simply morph for free.

    A special action in the rules: no stack, nothing to respond to. Here it is
    an ordinary activation, because the engine's activations already resolve
    without asking anything when they cost only mana -- and modelling it as its
    own `ActionKind` would change the RL action space for one row.
    """
    from .costs import can_pay

    card = state.card_of(obj)
    if card.morph is not None:
        cost = card.morph
        label = f"Turn {card.name} face up (morph)"
    elif card.is_creature:
        cost = card.mana_cost
        label = f"Turn {card.name} face up"
    else:
        # 701.34c: only a creature card may be turned face up this way.
        return []
    if not can_pay(state, pid, Cost(mana=cost), obj.oid):
        return []
    return [
        Action(
            kind=ActionKind.ACTIVATE,
            source=obj.oid,
            ability_index=0,
            label=label,
            base_label=label,
        )
    ]


def _ability_aims(
    state: GameState, pid: int, oid: int, ability, zone: Zone, sorcery_speed: bool
) -> list[tuple] | None:
    """How this ability could be activated: ``(modes, targets)`` pairs, or ``None``.

    ``modes`` is empty for everything except a modal ability whose bullets own
    their targets, where it names the one bullet this activation takes -- see
    the per-mode enumeration at the end.

    Every condition an offer depends on *except* the mana gate: being activated
    at all, the zone saying so, timing, X being payable, the cost being payable,
    and there being a legal target. ``None`` rather than ``[]`` because an
    untargeted ability legitimately returns ``[((), ())]`` -- one way to aim it,
    naming nothing.

    Split out of :func:`_activate_actions` so :func:`_offers_something_else` can
    ask the identical question. If the two drifted, a Mind Stone would show its
    mana ability beside a sacrifice ability it cannot actually pay for.
    """
    if not ability.is_activated:
        return None
    if zone not in ability.active_zones:
        return None
    if ability.sorcery_speed_only and not sorcery_speed:
        return None
    # Forecast: "activate only during your upkeep, and only once each turn".
    # Both are checked here rather than at payment, because they are permission
    # to activate at all (602.5c) -- an ability offered and then refused shows a
    # row the player can never use.
    if ability.activate_steps and state.step.name.lower() not in ability.activate_steps:
        return None
    if ability.once_each_turn and state.turn_ledger.activations(oid, ability.index):
        return None
    # 606.3: a loyalty ability may be activated only during your own main phase
    # when the stack is empty (which `sorcery_speed_only` already covers), and
    # only if **no** loyalty ability of this permanent has been activated this
    # turn. The second half is a limit on the *permanent*: Sorin has three, and
    # `once_each_turn` -- which counts one ability -- would let him plus twice
    # and then minus, three cards' worth of a card.
    if ability.cost is not None and ability.cost.loyalty is not None:
        siblings = abilities_of(state, oid)
        if any(
            state.turn_ledger.activations(oid, other.index)
            for other in siblings
            if other.cost is not None and other.cost.loyalty is not None
        ):
            return None
    if ability.activation_condition is not None and not _activation_allowed(
        state, pid, oid, ability
    ):
        return None
    # "…or activate an ability of a creature source of the chosen type." What
    # this activation would be paying *for*, so a restricted mana source that
    # names this permanent's types is offered here exactly as `spell_purpose` is
    # offered on the cast path. Computed once and used by both mana questions
    # below: an X ceiling measured without restricted mana and a cost then found
    # payable with it would offer an X this ability cannot pay.
    from .costs import ability_purpose

    purpose = ability_purpose(state, oid)
    if (
        ability.cost is not None
        and ability.cost.mana.x_count
        # "X is the mana value of that card": an ability that defines its own X
        # is not offered at a floor of zero the way a Fireball is, because there
        # is no announcement to make. `can_pay` below prices it -- through
        # `ability_mana`, which fills in the defined X -- so a Soul Foundry with
        # a Griselbrand imprinted disappears from the list until eight mana is
        # available, instead of being offered at X = 0 and copying it for free.
        and ability.cost.x_value is None
    ):
        from .costs import mana_sources

        if (
            max_affordable_x(
                ability.cost.mana,
                state.players[pid].mana_pool,
                mana_sources(state, pid, purpose=purpose),
            )
            < 0
        ):
            return None
    # ``x=0`` is the floor for an announced X and is ignored outright for a
    # defined one -- `costs.ability_mana` is the single place either is priced,
    # so the number legality tests is the number `costs.pay` charges.
    if not can_pay(state, pid, ability.cost, oid, x=0, purpose=purpose):
        return None
    # `mode_targets`, not `targets`: the loader lifts a mode-owned spec out of
    # the flat list into the per-mode map, so `ability.targets` holds only the
    # card-level ones and is empty on a card whose every target belongs to a
    # bullet.
    if not ability.mode_targets:
        tuples = enumerate_target_tuples(state, pid, ability.targets, oid)
        return [((), targets) for targets in tuples] if tuples else None

    # A **modal** activated ability whose bullets own their targets -- Phoenix
    # Down. 601.2b picks the mode before 601.2c declares its targets, and the
    # reverse was the whole reason `loader._check_mode_targets` refused `mode`
    # here: legality enumerated one activation per target tuple, so the targets
    # were fixed before `Game._activate` could ask which bullet.
    #
    # So the mode becomes part of the *action*, the way `kicked` is on a cast,
    # and each mode is offered only with the targets it owns. A bullet with no
    # legal target is not offered at all, which is 601.2b's other half: a mode
    # that cannot be chosen is not among the choices, and Phoenix Down with an
    # empty graveyard offers only its second bullet rather than being
    # unactivatable.
    out: list[tuple] = []
    spec = ability.cast_time_modes
    modes = list((spec or {}).get("modes") or ())
    for mode in range(len(modes)):
        specs = ability.specs_for_modes((mode,))
        tuples = enumerate_target_tuples(state, pid, specs, oid)
        if not tuples:
            continue
        out.extend(((mode,), targets) for targets in tuples)
    return out or None


def _activation_allowed(state: GameState, pid: int, oid: int, ability) -> bool:
    """"Activate only if you control five or more Vampires." Rule 602.5c.

    A *legality* question and nothing more: an ability that was legal when
    activated still resolves if the board changes while it is on the stack, so
    this is asked here and nowhere else.
    """
    from .effects.conditions import evaluate
    from .effects.context import EffectContext

    ctx = EffectContext(state=state, controller=pid, source_oid=oid)
    return bool(evaluate(ctx, ability.activation_condition))


def _offers_something_else(
    state: GameState, pid: int, oid: int, card, zone: Zone, sorcery_speed: bool
) -> bool:
    """Has this permanent an activated ability that is not a mana ability?

    Only counting ones that are actually offerable right now, which is the point:
    a Mind Stone whose ``{1}`` is unaffordable has nothing to choose between, so
    its mana ability stays the solver's and no row appears. The non-mana filter
    comes first so a land -- one ability, and that one a mana ability -- costs a
    single comparison here rather than a `can_pay` and a target enumeration.
    """
    return any(
        _ability_aims(state, pid, oid, ability, zone, sorcery_speed) is not None
        for ability in card.abilities
        if ability.is_activated and not ability.is_mana_ability
    )


def _mana_option_indices(state: GameState, oid: int, ability) -> list[int | None]:
    """Which yields of this ability to offer, or ``[None]`` for a non-mana one.

    The **current** options, not the printed superset. Exotic Orchard and
    Command Tower both carry all five colours at load time and narrow at
    activation, and `activate_mana_ability` indexes the narrowed list -- so
    offering an index into the raw one would either name a colour the board
    cannot make or, past the end, refuse the activation the panel just offered.
    """
    if not ability.is_mana_ability:
        return [None]
    from .costs import mana_options_of

    return list(range(len(mana_options_of(state, oid, ability))))


def _mana_option_label(state: GameState, oid: int, ability, mana_option: int | None) -> str:
    """What this yield of a modal mana ability produces, for its chip.

    "Add one mana of any colour" is the same printed text on all five actions,
    so it cannot tell them apart; the symbols each would actually make can.
    Empty when there is nothing to choose between, which is what leaves the
    client's target-based chip labelling alone.

    Doubling is applied, because a Vivid land under Vorinclex really does add
    two and the chip would otherwise promise one.
    """
    from .characteristics import player_doubles_land_mana
    from .costs import mana_amount, mana_options_of, mana_produced
    from .mana import format_symbols

    options = mana_options_of(state, oid, ability)
    if mana_option is None or len(options) <= 1:
        return ""

    doubled = "Land" in chars(state, oid).types and player_doubles_land_mana(
        state, state.objects[oid].controller
    )
    return format_symbols(
        mana_produced(
            options[mana_option],
            doubled=doubled,
            times=mana_amount(state, oid, ability),
        )
    )


def summarize(state: GameState) -> list[str]:  # pragma: no cover - debug helper
    return [a.label or a.kind.value for a in legal_actions(state)]


def zone_name(state: GameState, oid: int) -> str:
    obj = state.objects.get(oid)
    return obj.zone.value if obj else Zone.EXILE.value
