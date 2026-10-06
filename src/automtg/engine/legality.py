"""Legal action enumeration -- the single source of truth for "what can I do?".

Both the HTTP action list and the RL action mask are built from this function, so
the two can never disagree about what is legal.  The ordering is deterministic:
the same state always produces the same list in the same order.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from . import combat as combat_mod
from . import suspend as suspend_mod
from .actions import Action, PendingDecision
from .carddef import CardDef, Cost
from .characteristics import (
    abilities_of,
    loyalty_activation_timing_waived,
    threshold_met,
)
from .cost_reduction import cost_reduction
from .costs import (
    ability_purpose,
    can_pay,
    can_pay_mana,
    land_drops_available,
    mana_added_total,
    mana_amount,
    mana_options_of,
    mana_produced,
    mana_sources,
    most_life_for_mana,
    offerable_mana_ability,
    plus_mana,
    spell_purpose,
)
from .effects.conditions import evaluate
from .effects.context import EffectContext
from .enums import ActionKind, DecisionKind, Step, Zone
from .mana import ManaCost, format_symbols, max_affordable_x
from .player_statics import (
    player_cant_activate,
    player_doubles_mana_from,
    player_plays_lands_from_graveyard,
    player_plays_lands_from_library_top,
)
from .structs import TargetRef
from .targeting import describe_ref, enumerate_target_tuples

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState
from .casting import (  # noqa: F401
    GRAVEYARD_CAST_SLOT,
    MAX_ADDITIONAL_TIMES,
    MAX_PAY_GENERIC,
    MORPH_COST,
    SECOND_FACE_ZONES,
    _additional_ceiling,
    _cast_actions,
    _cast_options,
    _cast_variant,
    _charge_additional_cost,
    _emerge_fodder,
    _graveyard_cast_permission,
    _pay_generic_ceiling,
    _prepared_actions,
    _repeatable_payments,
    _second_face_actions,
    _timing_ok,
    chosen_additional,
)


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
        # `subject`, not `player`: when Odric has taken the declaration over, the
        # attacker holds the prompt but the blocks offered are still the
        # *defender's* legal ones.
        return _blocker_actions(state, decision.subject)
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
        walkers = combat_mod.legal_permanent_defenders(state, oid)
        for defender in defenders:
            # Propaganda: "creatures can't attack you **unless** their
            # controller pays {2}". An unpayable tax is a prohibition (508.1g),
            # so the action is withheld rather than offered and rewound -- and
            # the price goes in the label, because a player choosing between
            # defenders is choosing between prices.
            tax = combat_mod.attack_tax_cost(state, oid, defender)
            if tax is not None and not combat_mod.attack_tax_payable(state, oid, defender, tax):
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
            # Archangel of Tithes: "creatures can't attack you **or
            # planeswalkers you control** unless ...". Only a tax that says so
            # reaches a walker, and it is withheld and labelled exactly as the
            # player branch above is.
            owner = state.objects[walker].controller
            tax = combat_mod.attack_tax_cost(state, oid, owner, planeswalker=True)
            if tax is not None and not combat_mod.combat_tax_payable(state, oid, tax):
                continue
            price = f" (pay {tax.mana})" if tax is not None else ""
            out.append(
                Action(
                    kind=ActionKind.ADD_ATTACKER,
                    source=oid,
                    targets=(TargetRef.obj(walker),),
                    label=f"Attack {state.card(walker).name} with {name}{price}",
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
    if not combat_mod.unmet_attack_requirements(state) and combat_mod.attacks_valid(state, pid):
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
    # Archangel of Tithes: "creatures can't block unless their controller pays
    # {1} for each of those creatures". Priced once per blocker rather than per
    # pair, since one creature offered against three attackers is one price;
    # an unpayable tax is a prohibition (509.1e), so the block is withheld, and
    # the price goes in the label as it does for an attack tax.
    taxes: dict[int, object] = {}
    for blocker_oid, attacker_oid in combat_mod.legal_blocks(state, pid):
        if blocker_oid not in taxes:
            taxes[blocker_oid] = combat_mod.block_tax_cost(state, blocker_oid)
        tax = taxes[blocker_oid]
        if tax is not None and not combat_mod.combat_tax_payable(state, blocker_oid, tax):
            continue
        price = f" (pay {tax.mana})" if tax is not None else ""
        out.append(
            Action(
                kind=ActionKind.ADD_BLOCKER,
                source=blocker_oid,
                targets=(TargetRef.obj(attacker_oid),),
                label=(
                    f"Block {state.card(attacker_oid).name} with "
                    f"{state.card(blocker_oid).name}{price}"
                ),
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
    """ "Rather than cast this card from your hand, you may pay {G}…"

    A special action rather than a variant of casting: nothing goes on the
    stack, so it is offered under the same timing the card itself would need
    (rule 702.62a) but produces its own `ActionKind`.
    """

    out: list[Action] = []
    for oid in state.players[pid].hand:
        card = state.card(oid)
        if card.suspend is None:
            continue
        if not _timing_ok(state, pid, card, sorcery_speed):
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
    #
    # Every seat's exile, not only your own: exile is kept per owner, and Elder
    # Brain exiles an *opponent's* hand and lets you play the lands in it. The
    # cast side (`casting._cast_actions`) already walks every seat for the same
    # reason; the flag is the permission, so the wider walk offers nothing that
    # was not granted.
    exiled = [
        oid
        for player in state.players
        for oid in player.exile
        if state.objects[oid].playable_by == pid and state.objects[oid].playable_live(state.turn)
    ]
    if exiled:
        zones.append(exiled)
    if player_plays_lands_from_library_top(state, pid) and state.players[pid].library:
        # The top card only -- which is what the cards say, and the only part
        # of a hidden zone anybody is entitled to see.
        zones.append(state.players[pid].library[:1])

    out: list[Action] = []
    for zone in zones:
        for oid in zone:
            card = state.card(oid)
            if card.is_land:
                out.append(Action(kind=ActionKind.PLAY_LAND, source=oid, label=f"Play {card.name}"))
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
    ``tests/unit/engine/test_legality_reasons.py`` pins the two together.
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

    if not _timing_ok(state, pid, card, sorcery_speed):
        return "timing"

    # Hand cards never owe commander tax -- that is a command-zone cost only.
    discount = cost_reduction(state, pid, card)
    purpose = spell_purpose(card)
    x = 0
    # The same gate `_cast_variant` applies, and it must stay X = 0
    # afterwards for the same reason: this diagnostic has to agree with the
    # action list, and that list now offers the spell at its floor.
    if (
        card.mana_cost.x_count
        and max_affordable_x(
            card.mana_cost,
            state.players[pid].mana_pool.spendable(purpose),
            mana_sources(state, pid, purpose=purpose),
            extra_generic=-discount,
        )
        < 0
    ):
        return "mana"
    if not can_pay_mana(state, pid, card.mana_cost, x=x, extra_generic=-discount, purpose=purpose):
        return "mana"

    exclude_sid = state.objects[oid].stack_id
    if not enumerate_target_tuples(state, pid, card.targets, oid, exclude_sid=exclude_sid):
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
        # Grand Abolisher, Myrel. The board's standing prohibition, beside the
        # object's own until-end-of-turn one: `abilities_locked` is a fact
        # recorded on the permanent, this is a static somebody else controls,
        # and either is enough to withhold the action.
        if player_cant_activate(state, pid, oid):
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
                        and _offers_something_else(state, pid, oid, card, zone, sorcery_speed)
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
            # which X the player wants, *except* when the targets depend on it:
            # `_ability_aims` then announces X itself, one activation per value,
            # and the number below comes off the aim.
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
                for x, ability_modes, targets in aims:
                    label = label_base
                    if option_label:
                        label += f" ({option_label})"
                    if x:
                        label += f" (X={x})"
                    if targets:
                        label += " -> " + ", ".join(describe_ref(state, ref) for ref in targets)
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
    if ability.threshold is not None:
        # A station striation below its number is not on the permanent (721).
        # `_activate_actions` never reaches one -- it walks `abilities_of`,
        # which has already left it out -- but `_offers_something_else` walks
        # the printed face, and a 12+ ability counted there would surface a
        # Planet's tap-only mana ability on a Planet with nothing else to do.
        obj = state.objects.get(oid)
        if obj is None or not threshold_met(obj, ability):
            return None
    if ability.level is not None:
        # A Class's ability above its level is not on the permanent (716.2b),
        # and `_offers_something_else` walks the printed face for the reason the
        # threshold check above gives.
        obj = state.objects.get(oid)
        if obj is None or not ability.present_at(obj.class_level):
            return None
    # "You may activate loyalty abilities of Teferi on any player's turn any time
    # you could cast an instant." The one permission that reaches this refusal,
    # and it reaches only the loyalty half: the 606.3 once-per-turn limit below is
    # the other half of that rule and is **not** waived, or the card would be
    # three cards' worth of itself every turn.
    if (
        ability.sorcery_speed_only
        and not sorcery_speed
        and not (
            ability.cost is not None
            and ability.cost.loyalty is not None
            and loyalty_activation_timing_waived(state, oid)
        )
    ):
        return None
    # 716.2a: "{W}: Level 2" -- "Activate only if this Class is level 1". The
    # restriction is what makes a level a ladder rather than a price list: level
    # 2 cannot be bought twice, and level 3 cannot be bought before level 2.
    if ability.becomes_level is not None:
        source = state.objects.get(oid)
        if source is None or source.class_level != ability.becomes_level - 1:
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
    #
    # Counted rather than tested for any: The Chain Veil grants a walker one
    # more loyalty activation this turn, so the ceiling is one plus whatever
    # `extra_loyalty_activations` holds for this permanent.
    if ability.cost is not None and ability.cost.loyalty is not None:
        siblings = abilities_of(state, oid)
        used = sum(
            state.turn_ledger.activations(oid, other.index)
            for other in siblings
            if other.cost is not None and other.cost.loyalty is not None
        )
        if used >= 1 + state.turn_ledger.extra_loyalty_activations.get(oid, 0):
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
        and max_affordable_x(
            most_life_for_mana(state, pid, ability.cost, oid),
            state.players[pid].mana_pool.spendable(purpose),
            mana_sources(state, pid, purpose=purpose),
        )
        < 0
    ):
        return None
    # ``x=0`` is the floor for an announced X and is ignored outright for a
    # defined one -- `costs.ability_mana` is the single place either is priced,
    # so the number legality tests is the number `costs.pay` charges.
    if not can_pay(state, pid, ability.cost, oid, x=0, purpose=purpose, ability=ability):
        return None
    # `mode_targets`, not `targets`: the loader lifts a mode-owned spec out of
    # the flat list into the per-mode map, so `ability.targets` holds only the
    # card-level ones and is empty on a card whose every target belongs to a
    # bullet.
    if not ability.mode_targets:
        if _targets_read_x(ability):
            # One activation per payable X, each carrying the targets legal at
            # *that* X. 601.2b's order in the shape of an action: the number is
            # announced when the activation is chosen, exactly as a modal
            # ability's bullet is below, because the alternative -- asking for X
            # afterwards -- would declare the targets before the X they depend
            # on existed.
            if ability.cost.loyalty_x:
                # The ceiling of a -X is the loyalty there is to remove (606.4).
                source_obj = state.objects.get(oid)
                loyalty = source_obj.counter("loyalty") if source_obj is not None else 0
                out_loyalty: list[tuple] = []
                for value in range(max(0, loyalty) + 1):
                    tuples = enumerate_target_tuples(
                        state, pid, ability.targets, oid, x=value
                    )
                    out_loyalty.extend((value, (), targets) for targets in tuples)
                return out_loyalty or None
            sources = mana_sources(state, pid, purpose=purpose)
            if ability.cost.tap:
                # The tapped source cannot help pay for itself -- the same
                # exclusion `_ask_x`, `can_pay` and `pay` all make. The gate
                # above can be generous because it only asks whether *any* X is
                # payable; these are the numbers actually offered, so an X the
                # payment would refuse must not be among them.
                sources = [s for s in sources if s.oid != oid]
            ceiling = max_affordable_x(
                most_life_for_mana(state, pid, ability.cost, oid),
                state.players[pid].mana_pool.spendable(purpose),
                sources,
            )
            out_x: list[tuple] = []
            for value in range(max(0, ceiling) + 1):
                tuples = enumerate_target_tuples(
                    state, pid, ability.targets, oid, x=value
                )
                out_x.extend((value, (), targets) for targets in tuples)
            return out_x or None
        tuples = enumerate_target_tuples(state, pid, ability.targets, oid)
        if not tuples:
            return None
        # Priced again, per tuple, because a discount may read what the
        # activation is aiming at -- "equip abilities you activate **that target
        # enchanted creature** cost {3} less". The gate above asked only whether
        # *any* activation was payable, and read such a clause generously, so
        # this is where an aim that cannot actually be paid for is dropped.
        return [
            (0, (), targets)
            for targets in tuples
            if can_pay(
                state, pid, ability.cost, oid, x=0, purpose=purpose, ability=ability,
                targets=targets,
            )
        ] or None

    # A **modal** activated ability whose bullets own their targets -- Phoenix
    # Down. 601.2b picks the mode before 601.2c declares its targets, and the
    # reverse was the whole reason `loader.targets._check_mode_targets` refused `mode`
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
        out.extend((0, (mode,), targets) for targets in tuples)
    return out or None


def _mentions_x(node: Any) -> bool:
    """Does this selector read the announced ``{X}`` anywhere inside it?

    A cheap structural walk rather than a compiled flag, and it is only ever
    asked about an ability that already has an ``{X}`` in its cost -- so every
    other ability in the pool pays one attribute check and nothing else.
    """
    if isinstance(node, Mapping):
        return any(k == "x" or _mentions_x(v) for k, v in node.items())
    if isinstance(node, (list, tuple)):
        return any(_mentions_x(v) for v in node)
    return node == "x"


def _targets_read_x(ability) -> bool:
    """"target nontoken artifact you control **with mana value X**".

    601.2b announces X before 601.2c declares targets, so an ability whose
    target pool depends on X has to be offered once per payable X -- the same
    shape `_ability_aims` already uses for a modal ability whose bullets own
    their targets, and for the same rule.

    Gated on the ability having an announced X at all: a defined one
    (`cost.x_value`, "X is the mana value of that card") is not announced and
    `costs.ability_mana` fills it in, so there is nothing to enumerate.
    """
    cost = ability.cost
    if cost is None:
        return False
    # "-X: Exile target nonland permanent card with mana value X" -- Tamiyo. A
    # loyalty X is announced as surely as a mana one.
    if not cost.loyalty_x and (not cost.mana.x_count or cost.x_value is not None):
        return False
    specs = list(ability.targets) + [
        spec for specs in (ability.mode_targets or {}).values() for spec in specs
    ]
    return any(_mentions_x(spec.selector) for spec in specs)


def _activation_allowed(state: GameState, pid: int, oid: int, ability) -> bool:
    """ "Activate only if you control five or more Vampires." Rule 602.5c.

    A *legality* question and nothing more: an ability that was legal when
    activated still resolves if the board changes while it is on the stack, so
    this is asked here and nowhere else.
    """

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

    options = mana_options_of(state, oid, ability)
    if mana_option is None or len(options) <= 1:
        return ""

    doubled = player_doubles_mana_from(state, state.objects[oid].controller, oid)
    produced = mana_produced(
        options[mana_option],
        doubled=doubled,
        times=mana_amount(state, oid, ability),
    )
    if ability.cost is not None and ability.cost.tap:
        produced = plus_mana(produced, mana_added_total(state, state.objects[oid].controller, oid))
    return format_symbols(produced)


def summarize(state: GameState) -> list[str]:  # pragma: no cover - debug helper
    return [a.label or a.kind.value for a in legal_actions(state)]


def zone_name(state: GameState, oid: int) -> str:
    obj = state.objects.get(oid)
    return obj.zone.value if obj else Zone.EXILE.value
