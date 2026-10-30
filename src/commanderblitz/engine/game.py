"""The ``Game`` facade -- the seam every driver goes through.

Three methods make up the entire interface::

    game.pending()         who must decide, and what kind of decision it is
    game.legal_actions()   every legal answer, in deterministic order
    game.apply(action)     validate, mutate, then advance until the next decision

A human clicking in the browser and a PPO policy sampling an index both end up
calling ``apply`` with the same :class:`~commanderblitz.engine.actions.Action`, so there
is exactly one code path for "a player did something".
"""

from __future__ import annotations

import dataclasses
from collections.abc import Generator, Iterable, Mapping, Sequence
from itertools import combinations, islice
from typing import TYPE_CHECKING, Any

from commanderblitz.cards.registry import default_registry

from . import legality, sba, stack, suspend, triggers, turn
from .actions import GENERATOR_DECISIONS, Action, DecisionOption, PendingDecision
from .carddef import Cost
from .casting import (
    GRAVEYARD_CAST_SLOT,
    MORPH_COST,
    PAY_GENERIC_TAP_TYPES,
    _graveyard_cast_permission,
    _spell_as_cast,
    chosen_additional,
    convoke_colors,
    convoke_payments,
    convoke_pips,
    deferred_target_spec,
    pay_generic_tappers,
    strive_surcharge,
)
from .characteristics import abilities_of, chars, mana_source_traits
from .combat import add_attacker, add_blocker, attack_tax_cost, block_tax_cost, finish_attackers
from .cost_reduction import cost_reduction, variant_reduction
from .costs import (
    ability_purpose,
    activate_mana_ability,
    can_pay,
    can_pay_mana,
    commander_cost,
    defined_x,
    mana_sources,
    most_life_for_mana,
    pay,
    spell_purpose,
)
from .division import divided_damage, division_amount, division_caps
from .effects.context import EffectContext, ask_mode, ask_objects, ask_targets, ask_x, ask_yes_no
from .effects.modes import chosen_at_random, modal_bounds, mode_labels, pick_at_random
from .enums import ActionKind, DecisionKind, Step, Zone
from .errors import IllegalActionError, RulesLoopError
from .events import EventType, GameEvent
from .legality import _targets_read_x
from .mana import OTHER_PAYMENT, ManaCost, max_affordable_x
from .objects import PLUS_ONE
from .player import PlayerState
from .player_statics import (
    cast_lock_min_x,
    graveyard_cast_permissions,
    library_top_cast_permissions,
    own_graveyard_cast_permission,
    player_pays_life_for_black,
    player_spends_mana_as_any_color,
    spell_life_tax,
)
from .primitives import add_counters, draw_cards, tap_permanent
from .rng import Rng
from .state import GameState, new_object
from .structs import ACTIVATION_CHOSEN_TYPE, CONVOKED_BINDING, TargetRef
from .targeting import (
    candidates,
    declared_by_spec,
    describe_ref,
    kicked_targets,
    selectable_modes,
    target_count,
)
from .turn import _next_blocker_decision
from .zones import exile as exile_object
from .zones import (
    move_object,
    offer_enters_copy,
    offer_enters_costs,
    offer_enters_replacement,
    offer_read_ahead,
    offer_riot_choice,
)
from .zones import sacrifice as sacrifice_object

if TYPE_CHECKING:  # pragma: no cover
    from commanderblitz.cards.registry import CardRegistry, DeckList, GameData

#: Opening hand size.
STARTING_HAND = 7
#: Most mulligans a player may take before being forced to keep.
MAX_MULLIGANS = 6
#: Mulligans that cost nothing: the first one, as in multiplayer and Commander.
FREE_MULLIGANS = 1
#: Safety valve on the internal advance loop.
MAX_ADVANCE_STEPS = 20_000
#: How many times a convoke pick that leaves the rest of the mana unpayable is
#: asked again before `Game._ask_pay_generic` picks for the player.
MAX_PAY_GENERIC_ASKS = 3
#: How many picks of one size `Game._ask_pay_generic` tries once it is picking
#: for the player, so a board of thirty creatures is not searched exhaustively.
MAX_PAY_GENERIC_PICKS = 256
#: Default turn cap, per player in the game.
TURNS_PER_PLAYER = 30


class Game:
    """A game in progress."""

    def __init__(self, state: GameState) -> None:
        self.state = state

    # ------------------------------------------------------------------
    # interface
    # ------------------------------------------------------------------

    def pending(self) -> PendingDecision | None:
        return self.state.pending_decision

    def legal_actions(self) -> list[Action]:
        return legality.legal_actions(self.state)

    def apply(self, action: Action) -> list[GameEvent]:
        """Apply one action and advance to the next decision point."""
        state = self.state
        if state.game_over:
            raise IllegalActionError("the game is over")
        decision = state.pending_decision
        if decision is None:
            raise IllegalActionError("no decision is pending")

        legal = self.legal_actions()
        if action not in legal:
            raise IllegalActionError(
                f"{action.kind.value} is not legal here; "
                f"legal: {[a.label or a.kind.value for a in legal[:8]]}"
            )

        mark = len(state.events)
        self._dispatch(action, decision)
        self._advance()
        return state.events[mark:]

    @property
    def over(self) -> bool:
        return self.state.game_over

    @property
    def winners(self) -> list[int]:
        return list(self.state.winners)

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, action: Action, decision: PendingDecision) -> None:
        kind = decision.kind
        if kind is DecisionKind.PRIORITY:
            self._dispatch_priority(action, decision)
        elif kind is DecisionKind.DECLARE_ATTACKERS:
            self._dispatch_attackers(action, decision)
        elif kind is DecisionKind.DECLARE_BLOCKERS:
            self._dispatch_blockers(action, decision)
        elif kind in GENERATOR_DECISIONS or kind is DecisionKind.MULLIGAN:
            self._dispatch_choice(action, decision)
        else:  # pragma: no cover - every decision kind is handled above
            raise IllegalActionError(f"unhandled decision kind {kind}")

    def _dispatch_priority(self, action: Action, decision: PendingDecision) -> None:
        state = self.state
        pid = decision.player
        state.pending_decision = None

        if action.kind is ActionKind.PASS:
            self._pass_priority()
            return

        state.passes_in_row = 0
        if action.kind is ActionKind.PLAY_LAND:
            self._run(self._play_land(pid, action))
        elif action.kind is ActionKind.CAST:
            self._run(self._cast(pid, action))
        elif action.kind is ActionKind.SUSPEND:
            # One action kind, two mechanics: both exile a card from hand to
            # be cast later and neither uses the stack. Which one is decided by
            # the card, since no printing has both.
            if state.card(action.source).foretell is not None:
                self._run(suspend.foretell_card(state, pid, action.source))
            else:
                self._run(suspend.suspend_card(state, pid, action.source))
        elif action.kind is ActionKind.ACTIVATE:
            source = state.objects.get(action.source)
            if source is not None and source.face_down and source.on_battlefield:
                # Turning a permanent face up borrows `ability_index` 0 because
                # a face-down permanent has no abilities to collide with -- so
                # it must be routed *before* anything indexes into the hidden
                # card's ability list, which is usually empty.
                self._run(self._turn_face_up(pid, source))
                return
            # A mana ability does not use the stack (rule 605.3a), so it takes a
            # different path entirely: nothing to respond to, and the player
            # keeps priority afterwards.
            ability = abilities_of(state, action.source)[action.ability_index]
            if ability.is_mana_ability:
                self._run(self._activate_mana(pid, action))
            else:
                self._run(self._activate(pid, action))
        else:  # pragma: no cover
            raise IllegalActionError(f"{action.kind} is not a priority action")

    def _dispatch_attackers(self, action: Action, decision: PendingDecision) -> None:
        state = self.state
        if action.kind is ActionKind.ADD_ATTACKER:
            ref = action.targets[0]
            if ref.kind == "player":
                # Propaganda's {2}, charged as the attacker is declared. 508.1g
                # settles the whole declaration's costs at once; per-attacker
                # comes to the same total, because the printed price is "{2} for
                # each creature ... attacking you" -- and it means an unaffordable
                # third attacker cannot strand a declaration two were paid for.
                #
                # `_run` rather than a bare call: `pay` is a generator like every
                # other payment. A pure-mana cost never actually yields, since
                # `pay_mana` solves and taps on its own, so the declaration is
                # not interrupted.
                cost = attack_tax_cost(state, action.source, ref.id)
                if not self._pay_combat_tax(action.source, cost):
                    return
                add_attacker(state, action.source, ref.id)
            else:
                # A planeswalker. Its controller is the defending player
                # (506.2), so `attackers[oid]` still records a player and every
                # existing read of it stays true.
                walker = state.objects.get(ref.id)
                if walker is not None:
                    # Archangel of Tithes taxes an attack on "planeswalkers you
                    # control" too, charged here exactly as the player branch.
                    cost = attack_tax_cost(
                        state, action.source, walker.controller, planeswalker=True
                    )
                    if not self._pay_combat_tax(action.source, cost):
                        return
                    add_attacker(
                        state, action.source, walker.controller, permanent=ref.id
                    )
            return  # the decision stays open for more attackers
        state.pending_decision = None
        self._run(finish_attackers(state))

    def _pay_combat_tax(self, oid: int, cost) -> bool:
        """Charge an attack or block tax for declaring ``oid``.

        Returns whether the declaration may proceed. Legality only offers an
        ADD_ATTACKER or ADD_BLOCKER it has already found payable, so a False
        here means the board moved underneath the action -- the same contract
        `op_may` has after its own `can_pay`. The creature's controller pays:
        "unless **their controller** pays", for both taxes.
        """

        if cost is None:
            return True
        obj = self.state.objects.get(oid)
        if obj is None:
            return False
        # Driven here rather than through `_run`, which reports only whether a
        # generator finished and throws away what it returned -- and for `pay`
        # that value *is* the answer. An attack tax is mana-only (the loader
        # refuses any other component), and `pay_mana` solves and taps without
        # asking, so this never suspends mid-declaration.
        gen = pay(self.state, obj.controller, cost, None, purpose=OTHER_PAYMENT)
        try:
            gen.send(None)
        except StopIteration as done:
            return bool(done.value)
        # Unreachable while attack taxes stay mana-only. If one ever asked a
        # question, suspending here would strand the declare-attackers decision,
        # so refuse the attack rather than corrupt the declaration.
        gen.close()
        return False

    def _dispatch_blockers(self, action: Action, decision: PendingDecision) -> None:
        state = self.state
        if action.kind is ActionKind.ADD_BLOCKER:
            # Archangel of Tithes' {1}, charged as the blocker is declared --
            # the 509.1d twin of the attack tax above, with the same contract.
            if not self._pay_combat_tax(action.source, block_tax_cost(state, action.source)):
                return
            # `subject`, not `player`: the block belongs to the defender even when
            # Odric's controller is the one declaring it, so `add_blocker` keeps
            # validating against the defender's creatures and requirements.
            add_blocker(state, action.source, action.targets[0].id, decision.subject)
            return
        state.pending_decision = None
        combat = state.combat
        if combat is not None and combat.pending_blockers:
            combat.pending_blockers.pop(0)
        _next_blocker_decision(state)

    def _dispatch_choice(self, action: Action, decision: PendingDecision) -> None:
        """Answer a decision raised by a suspended generator."""
        if action.kind is ActionKind.CHOOSE:
            decision.selected.append(int(action.choice))
            if not decision.is_complete:
                return
            answer = list(decision.selected)
        elif action.kind is ActionKind.FINISH_DECLARATION:
            answer = list(decision.selected)
        elif action.kind in (ActionKind.YES, ActionKind.MULLIGAN):
            answer = [0]
        elif action.kind in (ActionKind.NO, ActionKind.KEEP):
            answer = [1]
        else:  # pragma: no cover
            raise IllegalActionError(f"{action.kind} cannot answer {decision.kind}")
        self._resume(answer)

    # ------------------------------------------------------------------
    # priority actions
    # ------------------------------------------------------------------

    def _play_land(self, pid: int, action: Action) -> Generator[Any, list[int]]:
        state = self.state
        oid = action.source
        card = state.card(oid)
        # Count the drop *before* the land moves: move_object fires the ETB, and
        # a landfall trigger with an intervening-if that counts land drops this
        # turn has to see the post-increment value.
        state.players[pid].lands_played += 1
        # A modal DFC played as its land half shows that face from the moment it
        # arrives, and the flag is set *before* the move so the enters-the-
        # battlefield replacements are read off the land rather than off the
        # spell -- Malakir Mire enters tapped, and Malakir Rebirth does not enter
        # at all. `reset_permanent_state` deliberately leaves this flag alone, so
        # unlike `transformed` it survives the arrival with no second write.
        if action.second_face:
            state.objects[oid].showing_second_face = True
            card = state.card_of(state.objects[oid])
        # "As this land enters, you may pay 3 life. If you don't, it enters
        # tapped." Asked before the move for the reason the `second_face` write
        # above is done before it: the enters replacements are applied inside
        # `move_object`, which cannot stop to ask, and nobody receives priority
        # between this question and the arrival.
        # The player making the land drop controls the land (110.2),
        # which is only news for a card they do not own -- one played out of an
        # opponent's exile under Elder Brain's permission. Set before the move,
        # so the enters replacements and the landfall event read the player
        # who actually played it, the way `stack.push_spell` sets a spell's.
        state.objects[oid].controller = pid
        # First of the three, because this one decides whether the permanent
        # arrives at all: asking a land whether it enters tapped, or what it is
        # a copy of, is a wasted question when the arrival itself is about to be
        # replaced.
        yield from offer_enters_replacement(state, oid, pid)
        # A shock land's answer rides on the drop itself (`Action.enters_paid`,
        # offered as two land drops by legality), so this asks nothing then.
        yield from offer_enters_costs(state, oid, pid, decided=action.enters_paid)
        yield from offer_enters_copy(state, oid, pid)
        # Riot, on a land drop: Dryad Arbor is a land *creature*, so a land put
        # onto the battlefield under a Rhythm of the Wild really does arrive
        # with the choice. Last of the four, because the copy above decides
        # what the arriving permanent is and riot asks about a creature.
        yield from offer_riot_choice(state, oid, pid)
        yield from offer_read_ahead(state, oid, pid)
        # Where the land was played from -- "whenever you play a card **from
        # exile**" (Klaw, Master of Sound). Read before the move, which is the
        # last moment the object still says.
        from_zone = state.objects[oid].zone.value
        # Its own simultaneous event, as a resolving spell's arrival is.
        state.event_batch += 1
        move_object(state, oid, Zone.BATTLEFIELD, cause="land_drop")
        triggers.fire(
            state,
            EventType.LAND_PLAYED,
            player=pid,
            source=oid,
            oid=oid,
            land_oid=oid,
            card=card.id,
            from_zone=from_zone,
        )

    def _cast(self, pid: int, action: Action) -> Generator[Any, list[int]]:
        state = self.state
        oid = action.source
        obj = state.objects[oid]
        card = state.card_of(obj)
        # Which face is being cast is chosen as the spell is announced (601.2a),
        # so it is settled here, before anything reads a cost or a target list.
        #
        # Rebound locally rather than flagging the object: everything below is
        # the second face's -- price, X, modes, splices, purpose -- and the
        # object must not start showing that face until the spell is actually on
        # the stack, because every `return` between here and `push_spell` is a
        # cast that did not happen.
        if action.prepared and card.prepared_face is not None:
            # "…you may cast **a copy of its spell**." The face is what is being
            # cast, so everything below -- price, X, modes, targets, purpose --
            # is read off it, exactly as it is for a second face. What differs
            # comes later, at `push_spell`: the permanent stays where it is.
            card = state.registry.get(card.prepared_face)
        elif action.second_face and card.second_face is not None:
            card = state.registry.get(card.second_face)
        # Fused: one spell whose cost, targets and effects are both halves'.
        # Built here the same way legality built it to price the line, so the
        # two cannot disagree about what is being cast.
        elif action.fused and card.second_face is not None:
            face = state.registry.get(card.second_face)
            card = dataclasses.replace(
                card,
                name=f"{card.name} // {face.name}",
                mana_cost=card.mana_cost.plus(face.mana_cost),
                targets=tuple(card.targets) + tuple(face.targets),
            )
        from_command = obj.zone is Zone.COMMAND
        # "If you cast a creature spell this way, it gains haste until end of
        # turn" -- Thundermane Dragon. Read now, as the spell is proposed
        # (601.2a), off the permissions of the lane this action took: the
        # Citadel's life line is `from_library_top`, every other line off the
        # top is the printed-price permission's. A cost paid below may take the
        # granting permanent with it, and the cast was still made "this way".
        # Where two permissions of one lane hold, the player would use the one
        # whose rider gives the most, so that one is read.
        cast_gains: frozenset[str] = frozenset()
        if obj.zone is Zone.LIBRARY:
            lane = [
                static
                for _, static in library_top_cast_permissions(state, pid, oid)
                if bool(static.get("pay_life_instead")) == action.from_library_top
            ]
            cast_gains = max(
                (frozenset(static.get("cast_gains_keywords") or ()) for static in lane),
                key=len,
                default=frozenset(),
            )

        # 601.2c for the one spec legality left empty: "any number of target
        # permanents" is declared here, as a set, rather than picked from a
        # capped list of subsets. See `casting.deferred_target_spec`, which
        # legality asked with these same specs. First, because everything
        # below that reads the targets -- discounts, taxes, the stored refs --
        # has to read the real ones.
        # A promised cast declares the promised list (601.2b, then 601.2c):
        # legality enumerated this line from it, and `stack._resolve_spell`
        # splits the stored refs by it.
        specs = card.targets_for(gift_promised=action.gift_to is not None)
        if action.kicked and (swapped := kicked_targets(specs)) is not None:
            specs = swapped
        deferred = (
            None
            if action.overloaded or action.bestowed or action.mutated
            else deferred_target_spec(state, card, specs)
        )
        late_refs: tuple[TargetRef, ...] = ()
        if deferred is not None:
            late_refs = yield from self._ask_deferred_targets(
                pid, card, oid, deferred, action.targets
            )
        targets = tuple(action.targets) + late_refs

        extra = commander_cost(state, oid) if from_command else 0
        # Netted against the tax rather than applied separately, so a commander
        # that also reduces its own cost is charged once. `pay` clamps at zero.
        # The targets the action actually carries, so a discount that reads
        # them charges the number legality offered -- `_priced_tuples` priced
        # this very tuple.
        extra -= cost_reduction(state, pid, card, targets)

        # Kicker is an additional cost, paid at the same time as the mana cost
        # and not separable from it: there is no state in which the spell is on
        # the stack having paid one half.
        # Evoke is the other direction and they are mutually exclusive by
        # construction: legality never offers a variant that is both, because
        # an alternative cost replaces the printed one and the kicker is an
        # addition to it.
        if action.emerge_oid is not None and card.emerge is not None:
            cost = card.emerge
            # The sacrificed creature pays for part of the spell, so it is netted
            # into `extra` alongside the commander tax rather than paid
            # separately -- `pay` clamps the generic part at zero.
            extra -= state.card(action.emerge_oid).mana_value
        elif action.flashback and card.flashback is not None:
            cost = card.flashback.mana
            # "…costs {X} less to cast **this way**". Netted into `extra` on this
            # branch alone, mirroring `legality._cast_variant`: the spell has to
            # be charged at the price it was offered at, and a rider read on
            # every branch would discount the printed hand cast as well.
            extra -= variant_reduction(state, pid, card.flashback, oid)
        elif action.evoked and card.evoke is not None:
            cost = card.evoke
        elif action.warp is not None:
            # The price legality offered, read off the **answer** and not
            # re-derived from the board. `Action.warp` is a string rather than
            # a flag because a `grant_warp` static may have supplied it, and
            # the granting permanent can leave between the line being offered
            # and this charge being made -- at which point a re-derived price
            # would be `None` and the spell would be charged its printed cost.
            cost = ManaCost.parse(action.warp)
        elif action.impending and card.impending is not None:
            cost = card.impending[0]
        elif action.bestowed and card.bestow is not None:
            cost = card.bestow
        elif action.mutated and card.mutate is not None:
            cost = card.mutate
        elif action.alternative and card.alternative_cost is not None:
            # Prowl and spectacle. The condition that let this line be offered
            # is not re-checked: legality asked it a moment ago, and a spell
            # whose price changed between being offered and being paid is the
            # bug `spell_purpose` exists to prevent elsewhere.
            #
            # The mana half only -- Force of Will's life and pitched card are
            # charged below, after the mana, the way flashback's rider is.
            cost = card.alternative_cost.mana
        elif action.face_down:
            cost = MORPH_COST
        elif action.foretold and card.foretell is not None:
            cost = card.foretell
        elif action.overloaded and card.overload is not None:
            cost = card.overload
        elif action.kicked:
            cost = card.mana_cost.plus(card.kicker)
        elif action.from_library_top:
            # "…pay life equal to its mana value **rather than** pay its mana
            # cost" -- Bolas's Citadel. The whole mana half is replaced, so it
            # is priced free here exactly as `_cast_variant` priced the line,
            # and the life is charged below. Without this the spell was offered
            # for free and then billed its printed cost, which `pay` refused
            # with no mana on the board: the cast simply did nothing.
            cost = ManaCost.parse("")
        elif action.granted_cost:
            # Nissa's "pay eight {E} rather than pay the mana cost". Priced free
            # exactly as `_cast_variant` priced the line, and the price -- read
            # off the action, for `warp`'s reason -- is charged below.
            cost = ManaCost.parse("")
        elif action.cast_free:
            # "…without paying its mana cost" (601.2b). Plot's "you may cast it
            # as a sorcery on a later turn without paying its mana cost", and
            # Dracogenesis' standing permission over a whole class of spell.
            # One branch, because 601.2b is one rule and the two cards differ
            # only in what granted it.
            #
            # Read off the **action** rather than off the board, which is what
            # changed when the permission became something a player may
            # decline: plot's `obj.playable_free` was safe to re-read because a
            # plotted card is *only* castable free, while the same board offers
            # Dracogenesis' free line and the printed line at once. A re-read
            # here would bill whichever the board happened to say, and a line
            # offered free and billed the printed cost is a cast that silently
            # does nothing -- the bug the `from_library_top` branch above
            # records. `_cast_variant` stamps the flag on the line it priced,
            # so the line offered is the line charged.
            #
            # X is 0 and is never asked, because this cost has no X in it to
            # announce (107.3b) -- the reason this is `FREE_COST` and not a
            # reduction to zero.
            cost = ManaCost.parse("")
        elif (
            (airbent := state.objects[oid]).playable_alt_cost is not None
            and airbent.playable_by == pid
            and airbent.playable_live(state.turn)
        ):
            # "…its owner may cast it **for {2} rather than its mana cost**" --
            # airbend. The paying half of the line `_cast_variant` priced, and
            # read off the **board** rather than off the action, which is safe
            # here for the reason it was safe for plot and is not for
            # Dracogenesis: an airbent card is castable *only* under this
            # permission, so there is no printed-cost line beside it for a
            # re-read to confuse this one with. It is the same read
            # `playable_any_type` and `playable_any_color` make three lines
            # below, off the same card, at the same moment.
            #
            # Last in the chain, immediately above the printed cost, because
            # `_cast_variant` hands `alt_cost` to the plain line alone: every
            # branch above this one chose a price of its own, and a line
            # offered at that price has to be charged at it.
            cost = ManaCost.parse(airbent.playable_alt_cost)
        else:
            cost = card.mana_cost

        # Strive (601.2f): "costs {1}{W} more to cast for each target beyond the
        # first". Added to whichever price the branch above chose, because a cost
        # increase applies to every way of casting the spell, and sized by the
        # targets this action announced (601.2c) -- the tuple legality priced the
        # line with, through the same `strive_surcharge`.

        # Compleated (702.150a) counts **Phyrexian mana symbols** life was paid
        # for, and K'rrik's widened {B} is not one. Counted before the widening
        # so the two can be told apart below.
        printed_phyrexian = cost.phyrexian_count
        if player_pays_life_for_black(state, pid):
            # K'rrik's black pips, read as Phyrexian ones exactly where
            # `_cast_variant` read them when it counted the lines -- on the
            # variant's price and before strive -- so `action.phyrexian` buys
            # the same pips here that it bought there.
            cost = cost.black_as_phyrexian()
        cost = cost.plus(strive_surcharge(card, targets))

        # 107.4f, and the paying half of the line `_cast_variant` offered. The
        # bought pips leave the cost here, before every relaxation and discount
        # below, exactly as legality priced them -- so a line offered as "paying
        # 2 life" is charged 2 life and one blue pip fewer, and a line offered
        # without it is charged the printed cost. `action.phyrexian` is the
        # player's answer, the way `action.x` is; nothing re-decides it.
        widened = cost.phyrexian_count - printed_phyrexian
        cost, phyrexian_life = cost.paying_phyrexian(action.phyrexian)
        # How many of the life payments bought a printed Phyrexian symbol. The
        # pips all cost the same 2 life, so under K'rrik the life is attributed
        # to his widened {B} first -- the reading the caster would choose, and
        # the one `paying_phyrexian`'s single-symbol-first order already takes.
        paid_phyrexian_symbols = max(0, action.phyrexian - widened)

        granted = state.objects[oid]
        if granted.playable_any_type and granted.playable_live(state.turn):
            # The paying half of the relaxation `_cast_variant` priced the line
            # with. Both sides read the same flag off the same card, so a line
            # that was offered is a line that can be paid.
            cost = cost.as_any_type()
        elif (
            granted.playable_any_color and granted.playable_live(state.turn)
        ) or player_spends_mana_as_any_color(state, pid, card):
            # Elder Brain's colour waiver, the paying half of the one
            # `_cast_variant` priced the line with -- or Chromatic Orrery's,
            # which says it about the player instead of about this card and so
            # is read here off the same static `_cast_variant` read.
            cost = cost.as_any_color()

        # The mana half of an additional cost paid `additional_times` over --
        # replicate, multikicker, escalate -- and every bought spree mode's
        # price (601.2f). Folded in at the point `_cast_variant` folds them
        # when it prices the line, after the relaxations above, so the line
        # offered and the mana charged are one number. Without it the line was
        # priced with the kicks and charged without them.
        additional_branch = chosen_additional(card, action.additional_choice)
        if action.additional_times and additional_branch is not None:
            cost = cost.plus(additional_branch.mana.scaled(action.additional_times))
        for mode in action.spree_modes:
            cost = cost.plus(card.spree[mode].mana)

        # Convoke and delve. Which creatures tap, or which cards are exiled, is
        # asked here -- the one line legality offered carries only the fewest
        # the player must spend. What pays for {1} is netted into `extra`
        # alongside the commander tax and emerge's sacrifice, so it goes
        # through the same clamp: `pay` floors the generic part at zero. A
        # creature that pays one mana of its colour instead (702.51a) takes
        # that pip out of `cost`. Before X, because X's ceiling is what the
        # mana has left once this is spent.
        convoked: list[int] = []
        if (
            card.pay_generic_with is not None
            and obj.zone is Zone.HAND
            and not action.cast_free
            and not action.from_library_top
            and not action.granted_cost
        ):
            cost, spent, picked = yield from self._ask_pay_generic(
                pid, card, oid, cost, extra, action.pay_generic
            )
            extra -= spent
            if card.pay_generic_with == "tap_creatures":
                convoked = picked

        # How big is X? Asked here rather than settled in legality, because the
        # answer is the player's: the action carries X = 0 and this is where it
        # becomes a real number. The ceiling is computed with the same `extra`
        # the payment below will use, so the largest offered X is always one the
        # player can actually pay for.
        #
        # Floored by a mana-value lock (Brisela), which this line escapes only
        # by announcing enough X -- asked of the same face legality asked it of.

        min_x = cast_lock_min_x(
            state, pid, _spell_as_cast(card, action.face_down, action.bestowed)
        )
        x = yield from self._ask_x(
            pid, card.name, cost, extra, spell_purpose(card), min_x=min_x or 0
        )

        # Which mode, also before paying (rule 601.2b). Recorded on the stack
        # item so `op_choose_mode` finds it already answered on resolution.
        modes = yield from self._ask_modes(
            pid,
            card.name,
            card.cast_time_modes,
            kicked=action.kicked,
            selectable=selectable_modes(state, pid, card, oid),
            # Escalate: the line paid for this many modes beyond the first, so
            # the cast chooses exactly that many (601.2b fixes the modes before
            # 601.2f totals the cost, and legality priced this line).
            exactly=action.additional_times + 1 if card.escalate is not None else None,
        )
        # 601.2c, and the printed order: a mode-owned target is declared only
        # once its mode has been taken. Appended to the action's own refs, which
        # `CardDef.specs_for_modes` re-derives the spec list for on resolution.
        mode_refs = yield from self._ask_mode_targets(pid, card, oid, modes)
        # 601.2c again, for the one target size a spell can only know now:
        # "deals 5 damage to each of **X** targets". Declared after `_ask_x`
        # above because 601.2b announces X first, which is the whole reason this
        # is the one computed count a spell's targets may carry.
        x_refs = yield from self._ask_x_targets(pid, card, oid, x)
        # 601.2d: "deals 4 damage divided as you choose" is divided now, over
        # the targets just declared and before the cost is paid.
        division = yield from self._ask_damage_division(
            pid, card, oid, modes, targets + x_refs + mode_refs
        )

        ok = yield from pay(
            state,
            pid,
            # The Phyrexian life rides in the *same* cost node as the mana, not
            # in a `pay` call of its own: 107.4f makes it one symbol of the
            # spell's mana cost paid a different way, so it is one payment and
            # one event batch. Contrast flashback's "Pay 3 life", which is a
            # genuinely separate additional cost and is paid below.
            Cost(mana=cost, pay_life=phyrexian_life) if phyrexian_life else Cost(mana=cost),
            None,
            x=x,
            extra_generic=extra,
            purpose=spell_purpose(card),
            # Sunburst and converge. The spell is what the colours are recorded
            # on, and this is the only moment they exist: `spend` decrements the
            # pool and one blue mana is then indistinguishable from another.
            record_colors_on=oid,
            # The line already chose which pips are bought with life
            # (`action.phyrexian`); every pip left in `cost` is paid with mana.
            life_for_mana=False,
        )
        if not ok:  # pragma: no cover - legality already proved payability
            return
        # Compleated's count, written onto the object now because the action is
        # the only record of it; see `GameObject.cast_phyrexian_life`.
        state.objects[oid].cast_phyrexian_life = paid_phyrexian_symbols

        # "Spells your opponents cast that target this creature cost an
        # additional 3 life to cast." Terror of the Peaks, and somebody *else's*
        # permanent is what imposed it. An additional cost (601.2f), so it is
        # paid here with the rest of them, after the mana (601.2g) and before
        # the spell is on the stack -- which is what makes it a price rather
        # than a ward: it is charged whether or not the spell ever resolves, and
        # there is no moment at which the caster could decline it.
        #
        # `targets` is the tuple legality priced the line with -- the same read
        # `cost_reduction` above takes, and for the same reason: a
        # surcharge sized off anything else would be a charge the offer never
        # showed. Legality proved this payable before offering the line, so a
        # failure here is a bug rather than a decision.
        life_tax = spell_life_tax(state, pid, card, targets)
        if life_tax:
            ok = yield from pay(state, pid, Cost(pay_life=life_tax), oid)
            if not ok:  # pragma: no cover - legality already proved payability
                return

        # Retrace's discarded land is an *additional* cost, so it is paid before
        # the spell goes on the stack -- and after the mana, which is the order
        # rule 601.2g gives and the order that lets a land be discarded to a
        # spell it just helped pay for.
        if card.retrace and obj.zone is Zone.GRAVEYARD:
            ok = yield from pay(state, pid, card.retrace_cost, None)
            if not ok:  # pragma: no cover - legality already proved payability
                return

        # Flashback's mana replaced the printed cost above; anything else on it
        # -- Deep Analysis' "Pay 3 life" -- is an additional cost, paid here for
        # the same reason and in the same order retrace's discard is.
        if action.flashback and card.flashback is not None:
            ok = yield from pay(state, pid, card.flashback.without_mana(), oid)
            if not ok:  # pragma: no cover - legality already proved payability
                return

        # The pitch costs. The alternative cost's mana replaced the printed one
        # above; "pay 1 life and exile a blue card from your hand" is the rest
        # of the node, paid here for the same reason and in the same order --
        # and with `oid` as the source, so `_hand_exile_pool` excludes the very
        # spell being cast (601.2a). Legality priced the same half through
        # `can_pay`, so a line that was offered is a line that can be paid.
        if action.alternative and card.alternative_cost is not None:
            ok = yield from pay(state, pid, card.alternative_cost.without_mana(), oid)
            if not ok:  # pragma: no cover - legality already proved payability
                return

        # Rule 601.2g: additional costs are paid after the mana. Sacrificing
        # here rather than before means a creature that taps for mana can still
        # help pay for the spell it is about to be eaten by.
        if action.emerge_oid is not None:
            sacrifice_object(state, action.emerge_oid)

        # The non-mana half of an additional cost -- casualty's sacrifice,
        # Deadly Dispute's artifact. Paid after the mana (rule 601.2g), the same
        # order emerge's sacrifice and retrace's discard use, so a creature that
        # tapped for mana can still be the one that is eaten.
        # `chosen_additional` rather than `card.additional_cost`, so a modal
        # cost -- "discard a card **or** pay 3 life" -- charges the branch the
        # player was offered. Legality prices the line through the same helper,
        # so the price shown and the price taken cannot disagree.
        additional = chosen_additional(card, action.additional_choice)
        if additional is not None and additional.pay_life_x:
            # "As an additional cost to cast this spell, pay X life" -- Toxic
            # Deluge. 601.2b puts the announcement here, with the rest of the
            # costs, and 118.4 lets a player pay life down to exactly 0, so the
            # ceiling is the whole life total. `x` is then carried on the stack
            # item, which is how the sweep reads `{"x": true}` on resolution.
            ctx = EffectContext(state=state, controller=pid, source_oid=oid)
            # Reassigns `x`, which is 0 for these cards: `_ask_x` above returns
            # early unless the *mana* cost has an {X}, and Toxic Deluge's is
            # {2}{B}. The one X a spell has is the one the player announced,
            # whichever half of the cost it belongs to, and `push_spell` carries
            # it below.
            x = yield from ask_x(
                ctx, f"Choose X for {card.name}", state.players[pid].life, pid
            )
            yield from pay(state, pid, Cost(pay_life=x), oid)
        if action.additional_times and additional is not None:
            for _ in range(action.additional_times):
                ok = yield from pay(state, pid, additional.without_mana(), oid)
                if not ok:  # pragma: no cover - legality already proved payability
                    return
            obj.cast_additional = action.additional_times

        if from_command:
            player = state.players[obj.owner]
            player.commander_tax[oid] = player.commander_tax.get(oid, 0) + 1

        # Splice (702.47a): "as you cast an Arcane spell, you may reveal this
        # card from your hand and pay its splice cost". Offered here, after the
        # host's own costs and before it goes on the stack, which is where the
        # printed line puts it -- and the cards are only *revealed*, so they
        # stay in hand and can be spliced again next turn.
        spliced = yield from self._ask_splices(pid, card, oid)

        # "Once during each of your turns, you may cast an artifact spell from
        # your graveyard" -- Edgar. Billed to the granting permanent, through
        # the same `_graveyard_cast_permission` legality offered the line with,
        # so the permission shown and the permission spent are the same one.
        # Nothing else in the engine knows this cast happened, which is why the
        # granting oid rides on the stack item.
        if action.from_library_top:
            # "…pay life equal to its mana value rather than pay its mana cost."
            # The mana half was already zeroed when the line was priced, so this
            # is the whole price. 118.4 lets a player pay down to exactly 0, and
            # legality withholds the line above that -- so this is charged
            # rather than offered and rewound.
            ok = yield from pay(state, pid, Cost(pay_life=card.mana_value), oid)
            if not ok:  # pragma: no cover - legality already proved payability
                return
        if action.granted_cost:
            # The granted alternative cost's own price, charged where Bolas's
            # Citadel charges its life and for its reason: the mana half was
            # zeroed when the line was priced, and legality offered the line
            # only while this was payable.
            granted = Cost.from_spec(dict(action.granted_cost))
            ok = yield from pay(state, pid, granted, oid)
            if not ok:  # pragma: no cover - legality already proved payability
                return

        if obj.playable_group is not None and obj.playable_live(state.turn):
            # "…you may cast **a spell** from among those cards." Billed to the
            # permanent that granted the permission, through the same ledger
            # slot a `cast_from_graveyard` permission uses, so legality's cap
            # and this agree about what has been spent.
            state.turn_ledger.activated(obj.playable_group, GRAVEYARD_CAST_SLOT)

        permission = None
        enters_tapped = False
        if obj.zone is Zone.GRAVEYARD and not action.flashback and not card.retrace:
            # Gravecrawler's own permission, when it holds, is the one used: it
            # costs nothing to spend, and billing an Edgar for a cast the card
            # could make by itself would take that turn's use away for nothing.
            # The card is its own grantor, so the stack item still says the
            # spell was cast from a graveyard.
            if own_graveyard_cast_permission(state, pid, oid):
                permission = oid
                granting = None
            else:
                granting = _graveyard_cast_permission(state, pid, card, oid)
            if granting is not None:
                permission = granting.oid
                state.turn_ledger.activated(granting.oid, GRAVEYARD_CAST_SLOT)

                for source_obj, static in graveyard_cast_permissions(state, pid):
                    if source_obj.oid != granting.oid:
                        continue
                    if static.get("enters_tapped"):
                        enters_tapped = True


        if action.prepared:
            # A **copy**, and the permanent stays on the battlefield -- the one
            # cast in the engine that does not move the object it names. So the
            # spell is a fresh token object of the spell face, which is also
            # what makes it vanish correctly on resolution (110.5g): a copy of a
            # sorcery goes to a graveyard that then empties itself of it, and
            # Emeritus is not the card that went there.
            #
            # "Doing so **unprepares it**" is the rules' own sentence, printed
            # as reminder text, so it happens here rather than on the card. It
            # happens *after* the cost is paid and everything is chosen: a cast
            # that was abandoned mid-payment has not been made, and the
            # permission is spent by using it.
            obj.prepared = False
            spell = new_object(
                state,
                card.id,
                owner=pid,
                zone=Zone.STACK,
                controller=pid,
                is_token=True,
            )
            oid = spell.oid
            state.bump_chars()

        item = stack.push_spell(
            state,
            oid,
            pid,
            targets + x_refs + mode_refs,
            x=x,
            kicked=action.kicked,
            graveyard_permission=permission,
            enters_tapped=enters_tapped,
            # Gift (702.164a). Carried onto the stack item and paid for with
            # nothing -- there is no `pay` call above for it, and that is the
            # mechanic rather than an omission: the promise is a 601.2b choice
            # made as the spell is cast, like the modes a line above, not a cost
            # under 601.2g. What the promise then *buys* the opponent is an
            # ordinary effect on the card, and it happens on resolution.
            gift_to=action.gift_to,
            evoked=action.evoked,
            warped=action.warp is not None,
            impending=action.impending,
            flashback=action.flashback,
            overloaded=action.overloaded,
            cost_option=action.additional_choice,
            # Spree (702.166a). The prices themselves were folded into the
            # spell's mana cost by `_cast_variant` and paid with the rest of it,
            # exactly as an additional cost's mana half is -- the loader refuses
            # a non-mana spree mode, so there is nothing left to charge here.
            # What the item carries is *which* modes were bought, because each
            # printed mode is an `if` on that and nothing else records it.
            spree_modes=action.spree_modes,
            spliced=spliced,
            face_down=action.face_down,
            second_face=action.second_face,
            fused=action.fused,
            bestowed=action.bestowed,
            mutated=action.mutated,
            modes=modes,
            # Asked, even when the answer was "no modes" -- see
            # `StackItem.modes_answered`.
            modes_answered=card.cast_time_modes is not None,
        )
        if division:
            item.bindings["distribution"] = division
        if card.pay_generic_with == "tap_creatures":
            # 702.51c: "a creature that convoked it" is one tapped to pay for
            # it, and only this cast knows which. Read by the `convoked`
            # selector key as the spell resolves; `zones.move_object` strikes
            # out a creature that leaves the battlefield in the meantime, since
            # the one that may come back is a new object (400.7).
            item.bindings[CONVOKED_BINDING] = [
                other for other in convoked if state.objects[other].zone is Zone.BATTLEFIELD
            ]
        if cast_gains:
            # Staged on the spell for the permanent it becomes, in the field
            # Arena of Glory's mana stages its haste in: `move_object` carries
            # it across the reset onto the battlefield and nowhere else, and
            # `_enter_battlefield` grants it until end of turn. After
            # `push_spell`, so a cast abandoned above leaves the card owing
            # nothing.
            state.objects[oid].mana_granted_keywords.update(cast_gains)
        triggers.fire(
            state,
            EventType.SPELL_CAST,
            player=pid,
            source=oid,
            oid=oid,
            spell_oid=oid,
            sid=item.sid,
            # `item.def_id`, not the `card` read at the top of this method: a
            # disturb cast turns the card over inside `push_spell`, and the log
            # has to name the face that was actually cast.
            card=item.def_id,
            kicked=1 if action.kicked else 0,
            # "…**if it targets** one or more other permanents you control"
            # (Orvar, the All-Form). The objects this spell chose, so a trigger
            # watching the cast can ask about them and then point an effect at
            # one. Nothing else on this payload can answer it: `oid` and
            # `spell_oid` are the spell itself, and the trigger's own `filter`
            # reads the spell card's characteristics.
            #
            # The **object** targets only. A spell aimed at a player or at
            # another spell has targets that are not permanents, and a list
            # mixing seat numbers with oids would be read as oids by every
            # consumer -- `_bound_oids` cannot tell them apart, since both are
            # `int`. Ordinary selector keys narrow it the rest of the way.
            spell_targets=[ref.id for ref in item.targets if ref.kind == "object"],
        )

    def _activate(self, pid: int, action: Action) -> Generator[Any, list[int]]:
        state = self.state
        oid = action.source
        card = state.card(oid)
        # Derived rather than printed, so the list legality offered from and the
        # list this indexes into are the same list.
        ability = abilities_of(state, oid)[action.ability_index]
        # Forecast's "only once each turn" counts *activations*, and this is the
        # moment one happens. Counted before the cost is paid, so an activation
        # that strands mid-payment still spends the turn's allowance -- the same
        # reading `resolutions_this_turn` takes of its own event.
        state.turn_ledger.activated(oid, action.ability_index)
        # "…if you didn't activate a loyalty ability of **a planeswalker** this
        # turn" (The Chain Veil). Counted per player at the same moment and for
        # the same reason as the line above, and only when the source is a
        # planeswalker as it is activated -- the printed sentence names the
        # permanent type, not just the cost.
        if (
            ability.cost is not None
            and ability.cost.loyalty is not None
            and "Planeswalker" in chars(state, oid).types
        ):
            tally = state.turn_ledger.loyalty_activations
            tally[pid] = tally.get(pid, 0) + 1

        # "…or activate an ability of a creature source of the chosen type."
        # What this activation pays *for*, so Cavern of Souls mana is available
        # here exactly as it is on the cast path -- and read now, before the cost
        # is paid, because a cost that sacrifices its own source would leave
        # nothing to ask about its types. This is the same value
        # `legality._ability_aims` used to decide the ability was payable, which
        # is the agreement restricted mana depends on.
        purpose = ability_purpose(state, oid)

        x = 0

        if _targets_read_x(ability):
            # The number was announced when the activation was chosen -- legality
            # offers one per payable X, each carrying the targets legal at that
            # value, which is the only order that satisfies 601.2b before
            # 601.2c. Asking again here would ask a question the player has
            # already answered and could contradict the targets already
            # declared. The same argument `ability_modes` makes below.
            x = action.x
        elif ability.cost is not None and ability.cost.loyalty_x:
            # "-X" (606.4, 107.3): announced now, before the cost is paid, and
            # bounded by the loyalty there is to remove -- `costs.pay` takes
            # exactly this many counters and the stack item carries it to the
            # effects that read X.
            source_obj = state.objects.get(oid)
            ceiling = source_obj.counter("loyalty") if source_obj is not None else 0
            x = yield from ask_x(
                EffectContext(state=state, controller=pid, source_oid=oid),
                f"Choose X for {card.name}",
                ceiling,
                pid,
                loyalty_cost=True,
            )
        elif ability.cost is not None and ability.cost.mana.x_count:
            # The tapped source cannot help pay for itself, so the ceiling has
            # to exclude it -- the same exclusion `costs.can_pay` and
            # `costs.pay` make.
            x = yield from self._ask_x(
                pid,
                card.name,
                # The ceiling is measured with every life-payable pip bought,
                # the cheapest this cost can get; `pay` then asks for at least
                # the pips the chosen X needs.
                most_life_for_mana(state, pid, ability.cost, oid),
                0,
                purpose,
                exclude_oid=oid if ability.cost.tap else None,
                # The whole cost node, not just its mana half: an ability that
                # defines its own X ("X is the mana value of that card") reads
                # the answer off `cost.x_value` and never asks.
                cost_node=ability.cost,
                cost_source=oid,
            )

        if action.ability_modes:
            # A modal ability whose bullets own their targets -- Phoenix Down.
            # The bullet was chosen when the action was: legality offers one
            # activation per mode, each carrying only that mode's targets, which
            # is the only way round that satisfies 601.2b before 601.2c. Asking
            # again here would ask a question the player has already answered
            # and could contradict the targets already declared.
            modes = action.ability_modes
        else:
            modes = yield from self._ask_modes(pid, card.name, ability.cast_time_modes)

        # 601.2d (602.2b applies it to abilities): "distribute …" is divided
        # now, over the targets just declared and before the cost is paid.
        distribution = yield from self._ask_distribution(
            pid, card.name, oid, ability, modes, action.targets
        )

        # `fire`, not `emit`: emit only writes the log, and an activation event
        # nothing listens for is the same silent no-op the cycling event below
        # was fixed for. This one had been a log line since activations existed.
        #
        # Fired **before the cost is paid**, which is both where 602.2b puts the
        # announcement and the only moment the source is still where it was: a
        # cost that sacrifices it -- a Panorama, a Mind Stone, a fetchland --
        # has already moved it to a graveyard by the time the ability is on the
        # stack, and "an ability of a land **on the battlefield**" has to be
        # able to see it there. The same reading `turn_ledger.activated` above
        # already takes of an activation that strands mid-payment.
        #
        # The ordering this does *not* change is the one that matters: triggers
        # queue here and go on the stack at the next priority (603.3), which is
        # after `push_activated_ability` below either way -- so a trigger this
        # wakes still lands on top of the ability that woke it.
        #
        # `mana_ability` is what separates this from `_activate_mana`'s
        # identical event type; without it a listener cannot tell a fetchland's
        # sacrifice ability from the same land's tap.
        triggers.fire(
            state,
            EventType.ABILITY_ACTIVATED,
            player=pid,
            source=oid,
            ability=action.ability_index,
            card=card.id,
            mana_ability=False,
        )

        # What the cost named -- Station's "the tapped creature", Gisa's "the
        # sacrificed creature" -- handed on to the stack item so the effects can
        # read it. Empty for every cost that names nothing, which is every cost
        # but `tap_permanents` or `sacrifice` with `as`.
        bindings: dict[str, Any] = {}
        if distribution:
            bindings["distribution"] = distribution
        # "Of the chosen type", as last-known information: read before the
        # cost is paid, because a cost that moves the source resets it.
        if (chosen := state.objects[oid].chosen_type) is not None:
            bindings[ACTIVATION_CHOSEN_TYPE] = chosen
        ok = yield from pay(
            state,
            pid,
            ability.cost,
            oid,
            x=x,
            purpose=purpose,
            bindings=bindings,
            # The same ability legality priced, so a discount written on another
            # permanent is charged at the number it was offered at -- and the
            # same targets, for a discount that reads them.
            ability=ability,
            targets=action.targets,
        )
        if not ok:  # pragma: no cover
            return

        stack.push_activated_ability(
            state,
            oid,
            action.ability_index,
            pid,
            action.targets,
            x=x,
            modes=modes,
            modes_answered=ability.cast_time_modes is not None,
            bindings=bindings,
        )
        if ability.is_cycling:
            # Fired *after* the cycling ability is on the stack, and the order
            # is the whole of "(Do this before you draw.)": a trigger queued now
            # drains on top of that ability, so it resolves first and Krosan
            # Tusker's land is fetched before the cycling draw.
            #
            # The card is already in the graveyard -- paying the cost discarded
            # it -- so the trigger is collected there, which is why it declares
            # `active_zones: ["graveyard"]`.
            # `fire`, not `emit`: emit only writes the log, and a cycle event
            # nothing listens to is the silent no-op this whole run exists to
            # add a listener for.
            #
            # ``x`` is the X paid in a cycling cost with one -- Shark Typhoon's
            # "Cycling {X}{1}{U}", whose "When you cycle this card, create an
            # X/X…" reads that number. The card was never cast, so its own
            # `cast_x` is 0; the event is the only place the payment survives.
            triggers.fire(
                state, EventType.CYCLED, player=pid, source=oid, card=card.id, x=x
            )

    def _ask_distribution(
        self,
        pid: int,
        name: str,
        source_oid: int,
        ability,
        modes,
        targets,
    ) -> Generator[Any, list[int], dict[str, list[list[int]]]]:
        """Divide each top-level ``distribute_counters`` among its declared targets.

        601.2d: every target gets at least one, and the rest are placed one at a
        time -- "which target gets another?" -- which reaches every legal
        division and asks nothing when the split is forced (as many targets as
        counters, or a single target). Composed from `ask_objects`, so there is
        no new decision kind; the purpose tag is ``distribute``.

        Returns ``{target_id: [[oid, n], ...]}``, JSON-shaped because it rides
        on the stack item's bindings.
        """

        wanted = [
            e
            for e in ability.effects
            if isinstance(e, Mapping) and e.get("op") == "distribute_counters"
        ]
        if not wanted:
            return {}
        declared = declared_by_spec(ability.specs_for_modes(modes), targets)
        ctx = EffectContext(
            state=self.state, controller=pid, source_oid=source_oid, source_name=name
        )
        out: dict[str, list[list[int]]] = {}
        for spec in wanted:
            target_id = str(spec["objects"]["target"])
            oids = [r.id for r in declared.get(target_id, ()) if r.kind == "object"]
            if not oids:
                continue
            amount = spec.get("amount", 1)
            total = int(amount["const"] if isinstance(amount, Mapping) else amount)
            kind = str(spec.get("counter", "+1/+1"))
            out[target_id] = yield from _divide(
                ctx,
                pid,
                oids,
                total,
                lambda left, kind=kind: (
                    f"Distribute: put another {kind} counter on which target? ({left} left)"
                ),
                "distribute",
            )
        return out

    def _ask_damage_division(
        self, pid: int, card, oid: int, modes, targets
    ) -> Generator[Any, list[int], dict[str, list[list[int]]]]:
        """Divide each divided damage effect's amount among its declared targets.

        601.2d, on the cast line: `_ask_distribution`'s walk -- every target
        dealt at least one, the rest placed one at a time, nothing asked when
        the split is forced -- over the amount `engine.division` reads now, as
        the spell is cast. Tagged ``divide_damage`` rather than ``distribute``,
        because which target deserves another point of damage is the opposite
        question to which deserves another +1/+1 counter.

        Returns the same ``{target_id: [[oid, n], ...]}`` shape, for the stack
        item's ``bindings["distribution"]``.
        """
        wanted = divided_damage(card)
        if not wanted:
            return {}
        state = self.state
        declared = declared_by_spec(card.specs_for_modes(modes), targets)
        ctx = EffectContext(state=state, controller=pid, source_oid=oid, source_name=card.name)
        out: dict[str, list[list[int]]] = {}
        for effect in wanted:
            target_id = str(effect["divided"])
            oids = [r.id for r in declared.get(target_id, ()) if r.kind == "object"]
            if not oids:
                continue
            total = division_amount(state, pid, oid, effect)
            out[target_id] = yield from _divide(
                ctx,
                pid,
                oids,
                total,
                lambda left: f"Divide {card.name}: 1 more damage to which target? ({left} left)",
                "divide_damage",
            )
        return out

    def _ask_pay_generic(
        self, pid: int, card, oid: int, cost: ManaCost, extra: int, fewest: int
    ) -> Generator[Any, list[int], tuple[ManaCost, int, list[int]]]:
        """Convoke, improvise and delve: ask what taps, or which cards go, and spend them.

        Between ``fewest`` -- what legality found the mana could not cover, the
        floor the line was offered at -- and the most the cost can absorb.
        Returns the cost left to pay with mana, how many of the picked paid
        for {1} (netted into ``extra`` by the caller), and the picked objects.

        Convoked creatures and improvised artifacts are tapped *here*, before
        any mana is paid, so the payment below cannot also tap one of them for
        mana (a permanent taps once; 702.126a's "after you're done activating
        mana abilities"). That makes a pick that taps the very Elf or Sol Ring
        the rest of the cost needed unpayable, so a pick is checked against the
        mana before it is spent and asked again if the rest could not then be
        paid.

        A convoking creature pays for {1} or for one mana of its colour
        (702.51a). Which symbol each one pays is not asked: the engine takes the
        first split (`casting.convoke_payments`) that leaves the rest payable,
        the way the mana solver picks which land pays which pip.
        """
        state = self.state
        taps = card.pay_generic_with in PAY_GENERIC_TAP_TYPES
        convokes = card.pay_generic_with == "tap_creatures"
        if taps:
            pool = pay_generic_tappers(state, pid, card)
        else:
            pool = [other for other in state.players[pid].graveyard if other != oid]
        room = max(0, cost.generic + extra)
        payable_symbols = room + (convoke_pips(cost) if convokes else 0)
        most = min(payable_symbols, len(pool))
        fewest = min(fewest, most)
        if most <= 0:
            return cost, 0, []
        purpose = spell_purpose(card)

        def price(picked: list[int]) -> tuple[ManaCost, int] | None:
            """What the rest costs once ``picked`` are spent, or ``None`` if unpayable."""
            if not taps:
                return cost, len(picked)
            if convokes:
                splits = convoke_payments(
                    cost, [convoke_colors(state, other) for other in picked], room
                )
            else:
                splits = [(cost, len(picked))] if len(picked) <= room else []
            # Tapped for the question only, with no event: nothing has happened yet.
            for other in picked:
                state.objects[other].tapped = True
            state.bump_chars()
            try:
                for left, generic in splits:
                    if can_pay_mana(
                        state, pid, left, extra_generic=extra - generic, purpose=purpose
                    ):
                        return left, generic
                return None
            finally:
                for other in picked:
                    state.objects[other].tapped = False
                state.bump_chars()

        ctx = EffectContext(state=state, controller=pid, source_oid=oid)
        purpose_tag, verb = {
            "tap_creatures": ("convoke", "Tap creatures to convoke"),
            "tap_artifacts": ("improvise", "Tap artifacts to improvise"),
        }.get(card.pay_generic_with, ("delve", "Exile cards to delve"))
        floor = f"at least {fewest}, " if fewest else ""
        prompt = f"{verb} for {card.name} ({floor}up to {most})"
        picked: list[int] = []
        paid: tuple[ManaCost, int] | None = None
        for _attempt in range(MAX_PAY_GENERIC_ASKS):
            picked = yield from ask_objects(
                ctx, prompt, pool, fewest, most, pid, purpose_tag
            )
            paid = price(picked)
            if paid is not None:
                break
            prompt = f"Not enough mana left for the rest. {verb} for {card.name} ({floor}up to {most})"
        else:
            # Nobody is asked forever. The permanents the mana does not need
            # first, as many as may go -- the pick most likely to leave the rest
            # payable -- and, when that is not payable either (a convoking
            # creature whose colour the cost does not want), the first pick of
            # the fewest that is.
            sources = {source.oid for source in mana_sources(state, pid, purpose=purpose)}
            ordered = sorted(pool, key=lambda other: other in sources)
            picked = ordered[:most]
            paid = price(picked)
            if paid is None:
                for size in range(fewest, most + 1):
                    for candidate in islice(combinations(ordered, size), MAX_PAY_GENERIC_PICKS):
                        if (paid := price(list(candidate))) is not None:
                            picked = list(candidate)
                            break
                    if paid is not None:
                        break
            if paid is None:  # pragma: no cover - legality proved some pick pays
                paid = (cost, min(len(picked), room))

        for other in picked:
            if taps:
                tap_permanent(state, other)
            else:
                exile_object(state, other, cause="cost")
        left, generic = paid
        return left, generic, list(picked)

    def _ask_x(
        self,
        pid: int,
        name: str,
        cost,
        extra_generic: int,
        purpose,
        *,
        exclude_oid: int | None = None,
        cost_node: Cost | None = None,
        cost_source: int | None = None,
        min_x: int = 0,
    ) -> Generator[Any, list[int], int]:
        """How big is X, if this cost has one at all?

        ``min_x`` is the floor a mana-value casting lock puts under it -- see
        `player_statics.cast_lock_min_x`. Legality offered the cast only when
        the ceiling reached it.

        The ceiling is recomputed here rather than taken from the action,
        because the board can have moved between legality offering the spell and
        this running -- a mana ability activated in response, most obviously.
        Using the same ``purpose`` and ``extra_generic`` the payment is about to
        use is what guarantees the largest offered X is payable.

        ``cost_node`` is the whole cost the mana half came from, and is given
        only by the activation path: an ability that **defines** X answers this
        question out of `cost.x_value` and never reaches the ceiling at all.
        """
        if not cost.x_count:
            return 0

        # "X is the mana value of that card." An ability that defines X does not
        # ask for one: 601.2b's announcement is the *player's* choice, and this
        # card has already made it. Answered before the ceiling below is
        # computed, because there is nothing to bound: `costs.ability_mana` prices the
        # cost at this same number, and legality only offered the ability
        # because that price was payable -- so there is no ceiling to compute
        # and no question to put.
        defined = defined_x(self.state, pid, cost_node, cost_source)
        if defined is not None:
            return defined

        state = self.state
        sources = mana_sources(state, pid, purpose=purpose)
        if exclude_oid is not None:
            sources = [s for s in sources if s.oid != exclude_oid]
        ceiling = max_affordable_x(
            cost,
            state.players[pid].mana_pool.spendable(purpose),
            sources,
            extra_generic=extra_generic,
        )
        ctx = EffectContext(state=state, controller=pid, source_oid=None)
        return (
            yield from ask_x(
                ctx,
                f"Choose X for {name}",
                ceiling,
                pid,
                per_point=cost.x_count,
                min_x=min_x,
            )
        )

    def _turn_face_up(self, pid: int, obj) -> Generator[Any, list[int]]:
        """Pay the price and reveal what was underneath (707.9a, 701.34c).

        Which price is *how it got there*: a card cast face down for morph turns
        up for its morph cost, and a manifested creature card for its printed
        one. The characteristics cache is dropped because everything about the
        permanent changes at once -- it stops being a 2/2 with no abilities and
        becomes whatever the card says.
        """

        state = self.state
        card = state.card_of(obj)
        cost = card.morph if card.morph is not None else card.mana_cost
        # A special action (116.2b), so neither a cast nor an activation.
        ok = yield from pay(state, pid, Cost(mana=cost), obj.oid, purpose=OTHER_PAYMENT)
        if not ok:  # pragma: no cover - legality already proved payability
            return
        obj.face_down = False
        # The shell is gone, and the ward went with it: the card underneath is
        # face up now and has whatever abilities it prints.
        obj.cloaked = False
        obj.revealed_to.clear()
        state.bump_chars()
        if card.morph_counter:
            # Megamorph (702.109a), and the only difference between the two
            # words.
            add_counters(state, obj.oid, PLUS_ONE, 1, source=obj.oid)
        state.emit("turned_face_up", player=pid, source=obj.oid, card=card.id)

    def _ask_splices(
        self, pid: int, card, oid: int
    ) -> Generator[Any, list[int], tuple[str, ...]]:
        """Offer every spliceable card in hand, one at a time.

        One at a time because each is its own "you may pay", and several may be
        spliced onto one spell -- so this is a loop of yes/no questions rather
        than a subset, and the order they are accepted in is the order their
        effects run.

        The cards are **revealed, not spent**: they stay in hand, which is the
        whole economy of the mechanic and the thing a naive implementation
        loses by discarding them.
        """

        state = self.state
        chosen: list[str] = []
        candidates = [
            other
            for other in list(state.players[pid].hand)
            if other != oid and state.card(other).splice is not None
        ]
        if not candidates:
            return ()
        ctx = EffectContext(state=state, controller=pid, source_oid=oid, source_name=card.name)
        for other in candidates:
            spliced_card = state.card(other)
            if spliced_card.splice_onto not in card.subtypes:
                continue
            price = Cost(mana=spliced_card.splice)
            if not can_pay(state, pid, price, other):
                continue
            if not (yield from ask_yes_no(
                ctx, f"Splice {spliced_card.name} onto {card.name}?", pid
            )):
                continue
            if not (yield from pay(state, pid, price, other)):
                continue
            state.emit("spliced", player=pid, source=other, card=spliced_card.id, onto=oid)
            chosen.append(spliced_card.id)
        return tuple(chosen)

    def _ask_modes(
        self,
        pid: int,
        name: str,
        spec,
        *,
        kicked: bool = False,
        selectable: Sequence[int] | None = None,
        exactly: int | None = None,
    ) -> Generator[Any, list[int], tuple[int, ...]]:
        """Which mode, asked as the spell or ability is put on the stack.

        ``spec`` is ``None`` for everything that is not a single top-level
        ``choose_mode`` -- see :attr:`CardDef.cast_time_modes` -- and those keep
        choosing as they resolve.

        Returns the chosen indices for :attr:`StackItem.modes`.

        ``selectable`` narrows the offer to the modes that can legally be
        chosen right now.  601.2b: a mode whose target has no legal choice
        cannot be chosen at all -- so a Call Damage Control with only creature
        cards in the graveyard offers one bullet, not four.  Only a card with
        mode-owned targets passes it; for every other modal card every mode is
        always available, which is why the default is ``None`` rather than
        ``range(len(modes))``.

        The residual divergence from 601.2 that used to be recorded here is
        gone for the cards that need it: :meth:`_ask_mode_targets` runs straight
        after this and declares the chosen modes' targets, in the printed order.
        A **card-level** target is still enumerated as part of the action and so
        is still fixed before this runs, which is what the shared ``optional:
        true`` idiom in docs/card-dsl.md is still for.
        """
        if not spec:
            return ()

        modes = list(spec.get("modes") or [])
        if not modes:
            return ()
        ctx = EffectContext(
            state=self.state,
            controller=pid,
            source_oid=None,
            source_name=name,
            # Entwine's `all_if` reads it, and this is the only place it can be
            # known: the flag reaches the object at resolution, and by then the
            # modes have been answered and recorded on the stack item.
            kicked=kicked,
        )
        # `up_to_if` is applied here as well as in `op_choose_mode`, and this is
        # the copy that matters: a spell whose whole effect tree is one
        # top-level `choose_mode` is answered *here* (601.2b) and never reaches
        # the op at all. Akroma's Will is exactly that shape, so the option
        # living only in the op was dead code for the card it was built for --
        # the spell compiled, played, cleared every gate, and silently chose
        # one mode.
        floor, up_to = modal_bounds(ctx, spec)
        if exactly is not None:
            # ``exactly`` is escalate's count, already paid for.
            floor = up_to = exactly
        offered = list(range(len(modes))) if selectable is None else list(selectable)
        # A floor that outruns what is on offer is not a spell that chooses
        # fewer modes -- it is one that cannot be cast, and `legality` already
        # declined to offer it. Clamped rather than asserted because a free cast
        # reaches a modal spell without going through that check, and hanging
        # the game would be the worse failure.
        floor = min(floor, len(offered))
        if chosen_at_random(ctx, spec):
            # "Choose one at random": the game answers 601.2b, from the modes
            # that could have been chosen, and nobody is asked.
            return tuple(pick_at_random(self.state, offered, floor))
        labels = mode_labels(modes)
        picked = yield from ask_mode(
            ctx, "Choose", [labels[i] for i in offered], pid, floor, up_to
        )
        # Sorted, so the recorded answer is in **printed** order however the
        # player clicked. 700.2e executes the modes in the order written, and
        # `_ask_mode_targets` and `CardDef.specs_for_modes` both walk them that
        # way -- a click order kept here would be a third order for the same
        # answer, which is exactly how a ref lands in the wrong bucket.
        return tuple(sorted(offered[i] for i in picked))

    def _ask_mode_targets(
        self, pid: int, card, oid: int, modes: Sequence[int]
    ) -> Generator[Any, list[int], tuple[TargetRef, ...]]:
        """Declare the chosen modes' own targets -- 601.2c, in the printed order.

        Runs immediately after :meth:`_ask_modes` and before the spell is paid
        for, which is exactly where 601.2 puts it.  Returns the refs to append
        to the cast action's own, in **ascending mode index**: resolution
        rebuilds the same list with `CardDef.specs_for_modes`, and
        `targeting.filter_legal` splits stored refs by position, so the two
        orders have to be one order.

        Every mode that reaches here had a legal target when :meth:`_ask_modes`
        offered it, and nothing can have changed since -- no player has had
        priority in between.
        """
        if not card.mode_targets:
            return ()

        state = self.state
        ctx = EffectContext(
            state=state, controller=pid, source_oid=oid, source_name=card.name
        )
        out: list[TargetRef] = []
        for index in sorted(modes):
            for spec in card.mode_targets.get(index, ()):
                # A ref already taken by an earlier mode is **not** struck off.
                # `enumerate_target_tuples` drops a tuple that reuses an object
                # because those are the targets of one instance of the word
                # "target"; two modes are two instances, and 601.2c only
                # forbids repeating within one. Striking it off would also let
                # `_ask_modes` offer a mode that then had nothing to point at,
                # which is the silently-inert half of a spell this whole
                # capability exists to prevent.
                options = [
                    (describe_ref(state, ref), ref)
                    for ref in candidates(state, pid, spec, oid)
                ]
                # An int by construction: `loader.targets._check_mode_targets` refuses a
                # caster-chosen or computed size on a mode-owned spec, because
                # `filter_legal` splits the stored refs by position.
                want = int(target_count(state, pid, spec, oid))
                chosen = yield from ask_targets(
                    ctx, f"Target for {card.name}", options, want, want, pid
                )
                out.extend(chosen)
        return tuple(out)

    def _ask_deferred_targets(
        self, pid: int, card, oid: int, spec, chosen
    ) -> Generator[Any, list[int], tuple[TargetRef, ...]]:
        """Declare a variable-size spec's refs as one set -- "any number of targets".

        The third sibling of :meth:`_ask_mode_targets` and :meth:`_ask_x_targets`:
        a 601.2c declaration legality left to the cast, here because the subsets
        of a board are too many to offer as lines. `casting.deferred_target_spec`
        has the argument and says which spec.

        Any size from zero to the ceiling, the two readings that reach here both
        including zero. ``chosen`` is the refs the line already carries for the
        specs before this one, struck off for the reason
        `enumerate_target_tuples` drops a tuple that reuses an object: one
        object cannot fill two targets of one spell.
        """
        state = self.state
        ctx = EffectContext(state=state, controller=pid, source_oid=oid, source_name=card.name)
        taken = set(chosen)
        options = [
            (describe_ref(state, ref), ref)
            for ref in candidates(state, pid, spec, oid)
            if ref not in taken
        ]
        count = target_count(state, pid, spec, oid)
        ceiling = len(options) if count == "any" else min(int(count), len(options))
        # Divided damage gives every target at least one (601.2d), so there are
        # never more targets than damage -- see `engine.division`.
        cap = division_caps(state, pid, oid, card).get(spec.id)
        if cap is not None:
            ceiling = min(ceiling, cap)
        picked = yield from ask_targets(
            ctx, f"Targets for {card.name}", options, 0, ceiling, pid
        )
        return tuple(picked)

    def _ask_x_targets(
        self, pid: int, card, oid: int, x: int
    ) -> Generator[Any, list[int], tuple[TargetRef, ...]]:
        """Declare an X-sized target spec's refs -- "each of X targets".

        The sibling of :meth:`_ask_mode_targets`, and it exists for the same
        reason and in the same window: 601.2 chooses modes and announces X
        (601.2b), *then* declares targets (601.2c), and both of those are
        choices legality could not have made on the player's behalf.

        Crackle with Power is the witness. Legality enumerates a spell's targets
        before the player has picked X, so it sizes the spec at zero and offers
        one line -- the gate the `x_count` check beside it already is for the
        cost. The refs are chosen here, where X is a number.

        Returns ``()`` for every card without such a spec, which is all but one
        of them.

        No `ask_targets` when X is 0: "each of zero targets" is a spell that
        targets nothing, which is legal and is not a question.
        """
        specs = [spec for spec in (card.targets or ()) if spec.x_sized]
        if not specs:
            return ()

        state = self.state
        ctx = EffectContext(state=state, controller=pid, source_oid=oid, source_name=card.name)
        out: list[TargetRef] = []
        for spec in specs:
            if x <= 0:
                continue
            options = [
                (describe_ref(state, ref), ref) for ref in candidates(state, pid, spec, oid)
            ]
            # Fewer legal targets than X is not an error and not a smaller X:
            # 601.2c requires as many *different* targets as the spell asks for,
            # and a spell that cannot choose them is simply not castable that
            # way. Legality cannot have caught this -- it did not know X -- so
            # the honest answer here is to take what there is, which `ask_targets`
            # does with a ceiling it can meet.
            want = min(x, len(options))
            chosen = yield from ask_targets(
                ctx, f"Targets for {card.name}", options, want, want, pid
            )
            out.extend(chosen)
        return tuple(out)

    def _activate_mana(self, pid: int, action: Action) -> Generator[Any, list[int]]:
        """Tap a permanent for mana by hand.

        Deliberately *not* :meth:`_activate`: a mana ability never uses the
        stack, so there is no :func:`stack.push_activated_ability` here and
        nothing for an opponent to respond to. It reaches this method at all
        only because the payment solver cannot use it -- see
        :func:`costs.offerable_mana_ability`.

        ``pay`` still runs, because these are exactly the mana abilities with a
        cost worth paying: a Signet's `{1}`, a Vivid land's counter. It also
        performs the `{T}`, which is why the ``tap`` below is
        :func:`activate_mana_ability`'s and not a second one.
        """
        state = self.state
        oid = action.source
        card = state.card(oid)
        ability = abilities_of(state, oid)[action.ability_index]
        # "Activate only during your turn and **only once each turn**" -- Vivi
        # Ornitier. Counted here for the reason `_activate` counts it, and in
        # the same place relative to the cost: this is the moment an activation
        # happens, and one that strands mid-payment still spends the allowance.
        #
        # It was missing, and only a mana ability could notice: `legality`
        # checks `once_each_turn` against this ledger for every activated
        # ability alike, but nothing on this path ever wrote to it -- so a
        # printed per-turn limit on a by-hand mana ability was inert. Vivi taps
        # for his own power, so the card was an arbitrary amount of mana per
        # turn rather than one activation's worth.
        state.turn_ledger.activated(oid, action.ability_index)

        # Fired rather than emitted, and tagged, so `TriggerSpec.mana_ability`
        # is a live restriction rather than a guard that never runs: a card
        # saying "if it isn't a mana ability" has to be *told* about the mana
        # ones to be excluding anything. A mana ability still uses no stack, so
        # nothing here is responded to -- the trigger it wakes drains at the
        # next priority like every other trigger.
        #
        # Before the cost, for the same reason `_activate` is: this path is the
        # one with `Cost.sacrifice` on it (Master of the Dark Rites, Krark-Clan
        # Ironworks), and a listener asking where the source was has to be asked
        # while it is still there.
        #
        # Known incompleteness, and pre-existing: the mana abilities the payment
        # solver taps for itself go through `costs.pay_mana` ->
        # `activate_mana_ability` directly and emit nothing at all, so they are
        # invisible to `mana_ability: true` as they were already invisible to
        # the log. Only the by-hand path is covered. Nothing shipped listens for
        # mana activations, and moving the emission into the primitive would put
        # an animated log beat on every land auto-tapped to cast a spell.
        triggers.fire(
            state,
            EventType.ABILITY_ACTIVATED,
            player=pid,
            source=oid,
            ability=action.ability_index,
            card=card.id,
            mana_ability=True,
        )

        # What the source **is**, taken before its own cost is paid -- "if mana
        # from a Treasure was spent to cast it" (Smaug, Wicked Worm). This is
        # the path with `Cost.sacrifice` on it, and every Treasure sacrifices
        # itself to make its mana: after `pay` the token has left the
        # battlefield and `sba._tokens_and_attachments` deletes it from
        # `state.objects` outright, so nothing downstream can still ask what it
        # was. `activate_mana_ability` takes its own snapshot when handed none,
        # which is right for the solver's path -- that one only ever taps.
        traits = mana_source_traits(state, oid)

        # A mana ability is an activated ability, so restricted mana may fund its
        # cost on the same terms as any other -- and it is read here rather than
        # left `None` because `legality._ability_aims` gates this path through
        # the same `can_pay`, and a cost found payable there and refused here
        # would strand the payment.
        ok = yield from pay(
            state, pid, ability.cost, oid, purpose=ability_purpose(state, oid), ability=ability
        )
        if not ok:  # pragma: no cover - legality already proved payability
            return

        activate_mana_ability(
            state,
            oid,
            action.ability_index,
            pid,
            action.mana_option or 0,
            source_traits=traits,
        )

    def _pass_priority(self) -> None:
        state = self.state
        state.passes_in_row += 1
        alive = len(state.alive())
        if state.passes_in_row < alive:
            state.priority_idx = state.next_alive_index(state.priority_idx or 0)
            return

        state.passes_in_row = 0
        if state.stack:
            state.priority_idx = state.active_idx
            state.just_resolved = True
            self._run(stack.resolve_top(state))
        else:
            state.priority_idx = None
            turn.advance(state)

    # ------------------------------------------------------------------
    # generator plumbing
    # ------------------------------------------------------------------

    def _run(self, gen: Generator[Any, list[int], Any]) -> bool:
        """Drive a generator until it finishes or asks a question.

        Returns True if it ran to completion.
        """
        state = self.state
        try:
            decision = gen.send(None)
        except StopIteration:
            return True
        state.pending_generator = gen
        state.pending_decision = decision
        return False

    def _resume(self, answer: list[int]) -> bool:
        state = self.state
        gen = state.pending_generator
        state.pending_decision = None
        state.pending_generator = None
        if gen is None:  # pragma: no cover
            return True
        try:
            decision = gen.send(answer)
        except StopIteration:
            return True
        state.pending_generator = gen
        state.pending_decision = decision
        return False

    # ------------------------------------------------------------------
    # the advance loop
    # ------------------------------------------------------------------

    def _advance(self) -> None:
        """Run the game forward until a player must decide, or it ends."""
        state = self.state
        for _ in range(MAX_ADVANCE_STEPS):
            if state.game_over or state.pending_decision is not None:
                return

            sba.run(state)
            if state.game_over or state.pending_decision is not None:
                return

            if state.armed_delays:
                # An event-watching delayed ability whose event just happened
                # (603.7). Here rather than in `triggers.collect`, which is
                # reached from inside a primitive that cannot suspend, and
                # *before* the drain below for the reason `turn._run_delayed`
                # resolves inline as a step begins: both halves of 603.7 happen
                # off the stack, so the delayed half of an event runs before the
                # ordinary triggers of that same event are put on it.
                state.passes_in_row = 0
                state.priority_idx = state.active_idx
                if not self._run(triggers.run_armed_delays(state)):
                    return
                continue

            if state.pending_triggers:
                # Set before the drain, not after: a trigger that stops to ask
                # for its targets suspends the loop here, and the resumption
                # comes back through `apply` rather than through this branch.
                state.passes_in_row = 0
                state.priority_idx = state.active_idx
                if not self._run(triggers.drain_to_stack(state)):
                    return
                continue

            if not state.step_started:
                if not self._run(turn.begin_step(state)):
                    return
                continue

            if state.priority_idx is None:
                if not turn.step_grants_priority(state):
                    turn.advance(state)
                    continue
                idx = state.active_idx
                if state.players[idx].has_lost:
                    idx = state.next_alive_index(idx)
                state.priority_idx = idx
                state.passes_in_row = 0
                continue

            state.pending_decision = PendingDecision(
                kind=DecisionKind.PRIORITY,
                player=state.priority_player,
                prompt="You have priority",
            )
            options = legality.legal_actions(state)
            if _should_auto_pass(state, options):
                state.pending_decision = None
                self._pass_priority()
                continue
            return

        raise RulesLoopError("advance loop did not settle")

    # ------------------------------------------------------------------
    # start of game
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Deal opening hands, run mulligans, and advance to the first decision."""
        state = self.state
        if state.started:
            return
        state.started = True
        self._run(_opening_sequence(state))
        self._advance()


# ----------------------------------------------------------------------
# priority stops
# ----------------------------------------------------------------------

#: Steps whose priority window is always worth stopping at when auto-pass is on.
#: Declare-blockers is the combat-trick window -- blocks are in and damage is
#: next, which is the one non-main step players reliably want.
ALWAYS_STOP_STEPS = frozenset({Step.DECLARE_BLOCKERS})


def _only_pass_or_mana(state: GameState, options: list[Action], player) -> bool:
    """Is passing the only thing this window can actually accomplish?

    True for a bare ``[Pass]``, and equally for ``Pass`` plus any number of mana
    activations -- adding mana is not a play, and nothing else here could spend
    it. False for a player who opted into ``manual_mana``, who wants those
    windows.
    """
    if player is not None and player.manual_mana:
        return len(options) == 1 and options[0].kind is ActionKind.PASS
    if not options:
        return False
    seen_pass = False
    for action in options:
        if action.kind is ActionKind.PASS:
            seen_pass = True
            continue
        if action.kind is not ActionKind.ACTIVATE or action.source is None:
            return False
        obj = state.objects.get(action.source)
        if obj is not None and obj.face_down:
            # Turning a permanent face up is not a mana ability, and it does not
            # index into the hidden card's abilities at all -- it borrows index
            # 0 because a face-down permanent has none. Auto-passing past it
            # would take the decision away, so this window is a real one.
            return False
        ability = abilities_of(state, action.source)[action.ability_index]
        if not ability.is_mana_ability:
            return False
    return seen_pass


def _should_auto_pass(state: GameState, options: list[Action]) -> bool:
    """Whether to pass this priority window without asking.

    Eleven of the thirteen steps grant priority to every player, and instants
    and activated abilities are legal in all of them.  A player holding one
    instant therefore faced ~11 forced Pass clicks per turn, on every player's
    turn.  The stops below are the windows where passing is actually a choice:
    something is on the stack to respond to, it is your own sorcery-speed
    window, or blockers are declared and damage is next.
    """
    pid = state.priority_player
    player = state.players[pid] if pid is not None else None

    # Somebody else's removal or sweeper is on the stack. Stopped at even with
    # nothing to answer it with, because without the stop it resolved the
    # instant it was cast and the player's permanents simply vanished -- both
    # cards gone before either could be read. Passing here is a read, not a
    # choice, and it is the one window worth spending a press on to see.
    if player is not None and player.auto_pass and _faces_disruption(state, player.pid):
        return False

    if _only_pass_or_mana(state, options, player):
        # Nothing else is legal: offering this would waste a step for the agent
        # and a click for the human, regardless of policy.
        #
        # "Nothing else" counts mana abilities as nothing, because on their own
        # they are: mana added to the pool empties at the end of the step and
        # cannot be spent on anything -- there is, by construction, nothing else
        # in this window to spend it on. Before non-tap-only mana abilities were
        # offered at all (see `legality._activate_actions`) this test was simply
        # `len(options) == 1`, and widening it is what keeps a board holding two
        # Signets from stopping at all thirteen steps of every turn.
        #
        # A player who asked for `manual_mana` is excluded: floating mana on
        # purpose is exactly what they turned it on for.
        #
        # The exception is below: "nothing else to spend it on" is only true of
        # the *offered* actions, and those price spells against the solver's
        # sources alone. A Treasure or Master of Dark Rites is not one, so the
        # spell that mana would pay for is withheld as unaffordable -- and the
        # window looked empty, and main phase went straight on to combat.
        return not _mana_would_unlock_a_spell(state, options, player)

    if pid is None or player is None:
        return False
    if not player.auto_pass or player.full_control:
        return False
    if state.stack:
        return False
    # The window right after a resolution. The stop above shows the creature
    # spell while it is on the stack, where removal cannot target it; this is
    # the one where it can, before the step moves on. Without it mana held up
    # on an opponent's turn could only ever answer their spells, never the
    # permanents those spells became.
    if state.just_resolved:
        return False
    if state.step in ALWAYS_STOP_STEPS:
        return False
    if _own_main_phase(state, pid):
        return False
    return True


#: Effect ops that take something away: a permanent, a spell, control of either.
#: An opponent's instant or sorcery carrying one of these is removal or a sweeper
#: whatever it targets, which is why the stop reads the effects and not the
#: targets alone -- a Wrath targets nothing.
DISRUPTIVE_OPS = frozenset(
    {
        "counter",
        "damage",
        "destroy",
        "exile",
        "fight",
        "gain_control",
        "put_on_top",
        "return_to_hand",
        "sacrifice",
    }
)


def _carries_op(node: Any, ops: frozenset[str]) -> bool:
    """Does an effect tree contain any of ``ops``, at any depth (modes, ifs)?"""
    if isinstance(node, Mapping):
        if node.get("op") in ops:
            return True
        return any(_carries_op(value, ops) for value in node.values())
    if isinstance(node, (list, tuple)):
        return any(_carries_op(value, ops) for value in node)
    return False


def _faces_disruption(state: GameState, pid: int) -> bool:
    """Is the top of the stack an opponent's removal, worth showing even unanswered?

    Their instant or sorcery whose effects take something away -- removal, a
    sweeper, a counterspell, a bounce -- or anything of theirs aimed at you or
    at something you control. Not their card draw, ramp or creature spells:
    those are most of the stack in a four-seat game, and stopping for each
    would bring back the forced Pass clicks auto-pass exists to remove.
    """
    if not state.stack:
        return False
    top = state.stack[-1]
    if top.controller == pid:
        return False
    for ref in top.targets:
        if ref.kind == "player" and ref.id == pid:
            return True
        if ref.kind == "object":
            target = state.objects.get(ref.id)
            if target is not None and target.controller == pid:
                return True
    if top.kind != "spell" or top.def_id not in state.registry:
        return False
    card = state.registry.get(top.def_id)
    if not (card.is_instant or card.is_sorcery):
        return False
    return _carries_op(card.spell_effects, DISRUPTIVE_OPS)


def _own_main_phase(state: GameState, pid: int) -> bool:
    return state.active_player == pid and state.step in (
        Step.PRECOMBAT_MAIN,
        Step.POSTCOMBAT_MAIN,
    )


def _mana_would_unlock_a_spell(state: GameState, options: list[Action], player) -> bool:
    """Is this a Pass-plus-mana window where the mana has somewhere to go?

    Asked only of a window `_only_pass_or_mana` has already called empty. It is
    not empty when the offered mana abilities -- Treasure, Master of Dark Rites,
    a Signet -- are not the payment solver's, and a card in hand is held back
    by its cost alone: activating them first is how that card gets cast.

    Narrowed to the stops a human with ``auto_pass`` already gets -- their own
    main phase, stack empty -- so a Treasure on the board does not bring back the
    eleven-stops-a-turn this policy exists to remove, and AI seats (``auto_pass``
    off) never see the window: ``heuristic_agent`` would sacrifice the Treasure
    for nothing. A hand card is the test because `legality.unplayable_reason`
    can name "mana" for it and for nothing else.
    """
    if player is None or not player.auto_pass or state.stack:
        return False
    pid = player.pid
    if not _own_main_phase(state, pid):
        return False
    if not any(action.kind is ActionKind.ACTIVATE for action in options):
        return False
    return any(
        legality.unplayable_reason(state, pid, oid) == "mana" for oid in player.hand
    )


# ----------------------------------------------------------------------
# game construction
# ----------------------------------------------------------------------


def _opening_sequence(state: GameState) -> Generator[Any, list[int]]:
    """London mulligans, then set up turn 1."""
    for pid in [p.pid for p in state.players]:
        draw_cards(state, pid, STARTING_HAND)

    for pid in [p.pid for p in state.players]:
        player = state.players[pid]
        while player.mulligans_taken < MAX_MULLIGANS:
            decision = PendingDecision(
                kind=DecisionKind.MULLIGAN,
                player=pid,
                prompt=f"Mulligan? ({player.mulligans_taken} taken)",
                options=(
                    DecisionOption(label="Mulligan", value=True),
                    DecisionOption(label="Keep", value=False),
                ),
                context={"hand": [state.objects[o].def_id for o in player.hand]},
            )
            answer = yield decision
            if answer and answer[0] == 1:
                break
            player.mulligans_taken += 1
            state.emit(EventType.MULLIGAN_TAKEN, player=pid, count=player.mulligans_taken)
            for oid in list(player.hand):
                move_object(state, oid, Zone.LIBRARY, to_player=pid, cause="mulligan")
            state.rng.shuffle(player.library)
            draw_cards(state, pid, STARTING_HAND)

        player.has_kept_hand = True
        # The first mulligan is free (103.5c, the multiplayer and Commander
        # rule): every seat redraws seven once without bottoming a card.
        bottom = min(max(0, player.mulligans_taken - FREE_MULLIGANS), len(player.hand))
        if bottom > 0:
            ctx = EffectContext(state=state, controller=pid, source_name="Mulligan")
            picked = yield from ask_objects(
                ctx,
                f"Put {bottom} card(s) on the bottom of your library",
                list(player.hand),
                bottom,
                bottom,
                pid,
                # A London mulligan is two questions, and this is the second.
                # `purpose` is the machine-readable tag `ask_objects` documents
                # itself as carrying so that "agents and the UI branch on it;
                # without it they would have to pattern-match on the
                # human-readable prompt" -- which is exactly what the client
                # needs here, to tell this apart from every other
                # `choose_objects` and answer it on the same screen that asked
                # the first half.
                purpose="mulligan_bottom",
            )
            for oid in picked:
                move_object(state, oid, Zone.LIBRARY, to_player=pid, cause="mulligan_bottom")
        state.emit(EventType.HAND_KEPT, player=pid, cards=len(player.hand))

    state.turn = 1
    state.round = 1
    state.active_idx = state.starting_player
    state.step = Step.UNTAP
    state.step_started = False
    state.priority_idx = None


def create_game(
    deck_ids: Sequence[str],
    *,
    data: GameData | None = None,
    seed: int = 0,
    names: Iterable[str] | None = None,
    max_turns: int | None = None,
    starting_player: int | None = None,
    auto_start: bool = True,
) -> Game:
    """Build a fresh game from deck ids.

    ``deck_ids`` determines the player count: two ids for a duel, four for a pod.
    The turn cap defaults to 30 turns *per player*, since a turn is one player's
    turn -- a 4-player pod legitimately takes twice as many turns as a duel.
    """
    if max_turns is None:
        max_turns = TURNS_PER_PLAYER * len(deck_ids)

    game_data = data if data is not None else default_registry()
    rng = Rng(seed)

    names = list(names) if names is not None else [f"Player {i}" for i in range(len(deck_ids))]
    players = [
        PlayerState(pid=i, name=names[i] if i < len(names) else f"Player {i}", deck_id=deck_ids[i])
        for i in range(len(deck_ids))
    ]
    state = GameState(registry=game_data.registry, players=players, rng=rng, max_turns=max_turns)
    state.starting_player = (
        rng.randint(0, len(deck_ids) - 1) if starting_player is None else starting_player
    )

    for pid, deck_id in enumerate(deck_ids):
        _deal_deck(state, pid, game_data.deck(deck_id), game_data.registry)

    game = Game(state)
    if auto_start:
        game.start()
    return game


def _deal_deck(state: GameState, pid: int, deck: DeckList, registry: CardRegistry) -> None:
    player = state.players[pid]
    player.deck_id = deck.id

    for card_id in deck.commanders:
        registry.get(card_id)  # raises DslError if the deck references a missing card
        obj = new_object(state, card_id, owner=pid, zone=Zone.COMMAND, is_commander=True)
        player.command.append(obj.oid)
        player.commanders.append(obj.oid)

    for card_id in deck.expanded():
        registry.get(card_id)
        obj = new_object(state, card_id, owner=pid, zone=Zone.LIBRARY)
        player.library.append(obj.oid)

    state.rng.shuffle(player.library)


def _divide(ctx: EffectContext, pid: int, oids, total: int, prompt, purpose: str):
    """601.2d's division: one each, then the rest one at a time.

    Reaches every legal division and asks nothing when the split is forced --
    as many targets as there is to divide, or a single target. ``prompt`` is
    given how many are left to place. Returns ``[[oid, n], ...]``.
    """
    shares = dict.fromkeys(oids, 1)
    for left in range(total - len(oids), 0, -1):
        picked = yield from ask_objects(ctx, prompt(left), list(oids), 1, 1, pid, purpose)
        shares[picked[0] if picked else oids[0]] += 1
    return [[oid, n] for oid, n in shares.items()]
