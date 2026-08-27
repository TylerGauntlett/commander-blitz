"""The ``Game`` facade -- the seam every driver goes through.

Three methods make up the entire interface::

    game.pending()         who must decide, and what kind of decision it is
    game.legal_actions()   every legal answer, in deterministic order
    game.apply(action)     validate, mutate, then advance until the next decision

A human clicking in the browser and a PPO policy sampling an index both end up
calling ``apply`` with the same :class:`~automtg.engine.actions.Action`, so there
is exactly one code path for "a player did something".
"""

from __future__ import annotations

from collections.abc import Generator, Iterable, Sequence
from typing import TYPE_CHECKING, Any

from . import legality, sba, stack, triggers, turn
from .actions import GENERATOR_DECISIONS, Action, DecisionOption, PendingDecision
from .carddef import Cost
from .characteristics import abilities_of
from .combat import add_attacker, add_blocker, finish_attackers
from .costs import ability_purpose, pay
from .enums import ActionKind, DecisionKind, Step, Zone
from .errors import IllegalActionError, RulesLoopError
from .events import EventType, GameEvent
from .player import MAX_HAND_SIZE, PlayerState
from .primitives import draw_cards
from .rng import Rng
from .state import GameState, new_object
from .structs import TargetRef
from .targeting import selectable_modes
from .turn import _next_blocker_decision
from .zones import move_object
from .zones import sacrifice as sacrifice_object

if TYPE_CHECKING:  # pragma: no cover
    from automtg.cards.registry import CardRegistry, DeckList, GameData

#: Opening hand size.
STARTING_HAND = 7
#: Most mulligans a player may take before being forced to keep.
MAX_MULLIGANS = 6
#: Safety valve on the internal advance loop.
MAX_ADVANCE_STEPS = 20_000
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
            self._play_land(pid, action)
        elif action.kind is ActionKind.CAST:
            self._run(self._cast(pid, action))
        elif action.kind is ActionKind.SUSPEND:
            from . import suspend

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
                if not self._pay_attack_tax(action.source, ref.id):
                    return
                add_attacker(state, action.source, ref.id)
            else:
                # A planeswalker. Its controller is the defending player
                # (506.2), so `attackers[oid]` still records a player and every
                # existing read of it stays true.
                walker = state.objects.get(ref.id)
                if walker is not None:
                    add_attacker(
                        state, action.source, walker.controller, planeswalker=ref.id
                    )
            return  # the decision stays open for more attackers
        state.pending_decision = None
        self._run(finish_attackers(state))

    def _pay_attack_tax(self, oid: int, defender: int) -> bool:
        """Charge any attack tax for declaring ``oid`` against ``defender``.

        Returns whether the attack may proceed. Legality only offers an
        ADD_ATTACKER it has already found payable, so a False here means the
        board moved underneath the action -- the same contract `op_may` has
        after its own `can_pay`.
        """
        from .combat import attack_tax_cost
        from .costs import pay

        cost = attack_tax_cost(self.state, oid, defender)
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
        gen = pay(self.state, obj.controller, cost, None)
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
            add_blocker(state, action.source, action.targets[0].id, decision.player)
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

    def _play_land(self, pid: int, action: Action) -> None:
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
        move_object(state, oid, Zone.BATTLEFIELD, cause="land_drop")
        triggers.fire(
            state,
            EventType.LAND_PLAYED,
            player=pid,
            source=oid,
            oid=oid,
            land_oid=oid,
            card=card.id,
        )

    def _cast(self, pid: int, action: Action) -> Generator[Any, list[int], None]:
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
        if action.second_face and card.second_face is not None:
            card = state.registry.get(card.second_face)
        # Fused: one spell whose cost, targets and effects are both halves'.
        # Built here the same way legality built it to price the line, so the
        # two cannot disagree about what is being cast.
        elif action.fused and card.second_face is not None:
            import dataclasses

            face = state.registry.get(card.second_face)
            card = dataclasses.replace(
                card,
                name=f"{card.name} // {face.name}",
                mana_cost=card.mana_cost.plus(face.mana_cost),
                targets=tuple(card.targets) + tuple(face.targets),
            )
        from_command = obj.zone is Zone.COMMAND
        from .costs import (
            commander_cost,
            cost_reduction,
            spell_purpose,
            variant_reduction,
        )

        extra = commander_cost(state, oid) if from_command else 0
        # Netted against the tax rather than applied separately, so a commander
        # that also reduces its own cost is charged once. `pay` clamps at zero.
        extra -= cost_reduction(state, pid, card)

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
            extra -= state.card(action.emerge_oid).mana_cost.mana_value()
        elif action.flashback and card.flashback is not None:
            cost = card.flashback.mana
            # "…costs {X} less to cast **this way**". Netted into `extra` on this
            # branch alone, mirroring `legality._cast_variant`: the spell has to
            # be charged at the price it was offered at, and a rider read on
            # every branch would discount the printed hand cast as well.
            extra -= variant_reduction(state, pid, card.flashback, oid)
        elif action.evoked and card.evoke is not None:
            cost = card.evoke
        elif action.bestowed and card.bestow is not None:
            cost = card.bestow
        elif action.mutated and card.mutate is not None:
            cost = card.mutate
        elif action.alternative and card.alternative_cost is not None:
            # Prowl and spectacle. The condition that let this line be offered
            # is not re-checked: legality asked it a moment ago, and a spell
            # whose price changed between being offered and being paid is the
            # bug `spell_purpose` exists to prevent elsewhere.
            cost = card.alternative_cost
        elif action.face_down:
            from .legality import MORPH_COST

            cost = MORPH_COST
        elif action.foretold and card.foretell is not None:
            cost = card.foretell
        elif action.overloaded and card.overload is not None:
            cost = card.overload
        elif action.kicked:
            cost = card.mana_cost.plus(card.kicker)
        else:
            cost = card.mana_cost

        # Convoke and delve. Netted into `extra` alongside the commander tax
        # and emerge's sacrifice, so it goes through the same clamp: `pay`
        # floors the generic part at zero, and no amount of convoking makes a
        # spell free of its coloured pips.
        if action.pay_generic and card.pay_generic_with is not None:
            extra -= action.pay_generic

        # How big is X? Asked here rather than settled in legality, because the
        # answer is the player's: the action carries X = 0 and this is where it
        # becomes a real number. The ceiling is computed with the same `extra`
        # the payment below will use, so the largest offered X is always one the
        # player can actually pay for.
        x = yield from self._ask_x(pid, card.name, cost, extra, spell_purpose(card))

        # Which mode, also before paying (rule 601.2b). Recorded on the stack
        # item so `op_choose_mode` finds it already answered on resolution.
        modes = yield from self._ask_modes(
            pid,
            card.name,
            card.cast_time_modes,
            kicked=action.kicked,
            selectable=selectable_modes(state, pid, card, oid),
        )
        # 601.2c, and the printed order: a mode-owned target is declared only
        # once its mode has been taken. Appended to the action's own refs, which
        # `CardDef.specs_for_modes` re-derives the spec list for on resolution.
        mode_refs = yield from self._ask_mode_targets(pid, card, oid, modes)

        ok = yield from pay(
            state,
            pid,
            Cost(mana=cost),
            None,
            x=x,
            extra_generic=extra,
            purpose=spell_purpose(card),
            # Sunburst and converge. The spell is what the colours are recorded
            # on, and this is the only moment they exist: `spend` decrements the
            # pool and one blue mana is then indistinguishable from another.
            record_colors_on=oid,
        )
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

        # Rule 601.2g: additional costs are paid after the mana. Sacrificing
        # here rather than before means a creature that taps for mana can still
        # help pay for the spell it is about to be eaten by.
        if action.emerge_oid is not None:
            sacrifice_object(state, action.emerge_oid)

        # Convoke and delve, for the same reason and at the same moment: the
        # creature that tapped for mana above may still be convoked, which is
        # wrong, so the tap is charged *after* payment and only untapped
        # creatures are eligible. Expressed as an ordinary `Cost` so the player
        # picks which ones, through the machinery every other selector cost
        # already uses.
        if action.pay_generic and card.pay_generic_with is not None:
            if card.pay_generic_with == "tap_creatures":
                spend = Cost(
                    tap_permanents={
                        "controller": "you",
                        "types": ["Creature"],
                        "tapped": False,
                        "count": action.pay_generic,
                    }
                )
            else:
                spend = Cost(
                    exile_from_graveyard={
                        "controller": "you",
                        "count": action.pay_generic,
                        "exclude_self": True,
                    }
                )
            ok = yield from pay(state, pid, spend, oid)
            if not ok:  # pragma: no cover - legality already proved payability
                return

        # The non-mana half of an additional cost -- casualty's sacrifice,
        # Deadly Dispute's artifact. Paid after the mana (rule 601.2g), the same
        # order emerge's sacrifice and retrace's discard use, so a creature that
        # tapped for mana can still be the one that is eaten.
        if action.additional_times and card.additional_cost is not None:
            for _ in range(action.additional_times):
                ok = yield from pay(
                    state, pid, card.additional_cost.without_mana(), oid
                )
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

        item = stack.push_spell(
            state,
            oid,
            pid,
            tuple(action.targets) + mode_refs,
            x=x,
            kicked=action.kicked,
            evoked=action.evoked,
            flashback=action.flashback,
            overloaded=action.overloaded,
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
        )

    def _activate(self, pid: int, action: Action) -> Generator[Any, list[int], None]:
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

        # "…or activate an ability of a creature source of the chosen type."
        # What this activation pays *for*, so Cavern of Souls mana is available
        # here exactly as it is on the cast path -- and read now, before the cost
        # is paid, because a cost that sacrifices its own source would leave
        # nothing to ask about its types. This is the same value
        # `legality._ability_aims` used to decide the ability was payable, which
        # is the agreement restricted mana depends on.
        purpose = ability_purpose(state, oid)

        x = 0
        if ability.cost is not None and ability.cost.mana.x_count:
            # The tapped source cannot help pay for itself, so the ceiling has
            # to exclude it -- the same exclusion `costs.can_pay` and
            # `costs.pay` make.
            x = yield from self._ask_x(
                pid,
                card.name,
                ability.cost.mana,
                0,
                purpose,
                exclude_oid=oid if ability.cost.tap else None,
                # The whole cost node, not just its mana half: an ability that
                # defines its own X ("X is the mana value of that card") reads
                # the answer off `cost.x_value` and never asks.
                cost_node=ability.cost,
                cost_source=oid,
            )

        modes = yield from self._ask_modes(pid, card.name, ability.cast_time_modes)

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

        ok = yield from pay(state, pid, ability.cost, oid, x=x, purpose=purpose)
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
            triggers.fire(state, EventType.CYCLED, player=pid, source=oid, card=card.id)

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
    ) -> Generator[Any, list[int], int]:
        """How big is X, if this cost has one at all?

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
        from .costs import defined_x

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
        from .costs import mana_sources
        from .effects.context import EffectContext, ask_x
        from .mana import max_affordable_x

        state = self.state
        sources = mana_sources(state, pid, purpose=purpose)
        if exclude_oid is not None:
            sources = [s for s in sources if s.oid != exclude_oid]
        ceiling = max_affordable_x(
            cost, state.players[pid].mana_pool, sources, extra_generic=extra_generic
        )
        ctx = EffectContext(state=state, controller=pid, source_oid=None)
        return (
            yield from ask_x(
                ctx, f"Choose X for {name}", ceiling, pid, per_point=cost.x_count
            )
        )

    def _turn_face_up(self, pid: int, obj) -> Generator[Any, list[int], None]:
        """Pay the price and reveal what was underneath (707.9a, 701.34c).

        Which price is *how it got there*: a card cast face down for morph turns
        up for its morph cost, and a manifested creature card for its printed
        one. The characteristics cache is dropped because everything about the
        permanent changes at once -- it stops being a 2/2 with no abilities and
        becomes whatever the card says.
        """
        from .costs import pay
        from .objects import PLUS_ONE
        from .primitives import add_counters

        state = self.state
        card = state.card_of(obj)
        cost = card.morph if card.morph is not None else card.mana_cost
        ok = yield from pay(state, pid, Cost(mana=cost), obj.oid)
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
        from .costs import can_pay, pay
        from .effects.context import EffectContext, ask_yes_no

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
        from .effects.context import EffectContext, ask_mode
        from .effects.ops_control import modal_bounds

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
        offered = list(range(len(modes))) if selectable is None else list(selectable)
        # A floor that outruns what is on offer is not a spell that chooses
        # fewer modes -- it is one that cannot be cast, and `legality` already
        # declined to offer it. Clamped rather than asserted because a free cast
        # reaches a modal spell without going through that check, and hanging
        # the game would be the worse failure.
        floor = min(floor, len(offered))
        labels = [str(m.get("label") or f"Mode {i + 1}") for i, m in enumerate(modes)]
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
        from .effects.context import EffectContext, ask_targets
        from .targeting import candidates, describe_ref, target_count

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
                # An int by construction: `loader._check_mode_targets` refuses a
                # caster-chosen or computed size on a mode-owned spec, because
                # `filter_legal` splits the stored refs by position.
                want = int(target_count(state, pid, spec, oid))
                chosen = yield from ask_targets(
                    ctx, f"Target for {card.name}", options, want, want, pid
                )
                out.extend(chosen)
        return tuple(out)

    def _activate_mana(self, pid: int, action: Action) -> Generator[Any, list[int], None]:
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

        # A mana ability is an activated ability, so restricted mana may fund its
        # cost on the same terms as any other -- and it is read here rather than
        # left `None` because `legality._ability_aims` gates this path through
        # the same `can_pay`, and a cost found payable there and refused here
        # would strand the payment.
        ok = yield from pay(
            state, pid, ability.cost, oid, purpose=ability_purpose(state, oid)
        )
        if not ok:  # pragma: no cover - legality already proved payability
            return

        from .costs import activate_mana_ability

        activate_mana_ability(state, oid, action.ability_index, pid, action.mana_option or 0)

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
        return True

    if pid is None or player is None:
        return False
    if not player.auto_pass or player.full_control:
        return False
    if state.stack:
        return False
    if state.step in ALWAYS_STOP_STEPS:
        return False
    if state.active_player == pid and state.step in (
        Step.PRECOMBAT_MAIN,
        Step.POSTCOMBAT_MAIN,
    ):
        return False
    return True


# ----------------------------------------------------------------------
# game construction
# ----------------------------------------------------------------------


def _opening_sequence(state: GameState) -> Generator[Any, list[int], None]:
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
        bottom = min(player.mulligans_taken, len(player.hand))
        if bottom > 0:
            from .effects.context import EffectContext, ask_objects

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
    from automtg.cards.registry import default_registry

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


def hand_size_limit() -> int:
    return MAX_HAND_SIZE


def target_ref(kind: str, ident: int) -> TargetRef:  # pragma: no cover - convenience
    return TargetRef(kind, ident)  # type: ignore[arg-type]
