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
from .combat import add_attacker, add_blocker, finish_attackers
from .costs import pay
from .enums import ActionKind, DecisionKind, Step, Zone
from .errors import IllegalActionError, RulesLoopError
from .events import EventType, GameEvent
from .player import MAX_HAND_SIZE, PlayerState
from .primitives import draw_cards
from .rng import Rng
from .state import GameState, new_object
from .structs import TargetRef
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

            self._run(suspend.suspend_card(state, pid, action.source))
        elif action.kind is ActionKind.ACTIVATE:
            # A mana ability does not use the stack (rule 605.3a), so it takes a
            # different path entirely: nothing to respond to, and the player
            # keeps priority afterwards.
            ability = state.card(action.source).abilities[action.ability_index]
            if ability.is_mana_ability:
                self._run(self._activate_mana(pid, action))
            else:
                self._run(self._activate(pid, action))
        else:  # pragma: no cover
            raise IllegalActionError(f"{action.kind} is not a priority action")

    def _dispatch_attackers(self, action: Action, decision: PendingDecision) -> None:
        state = self.state
        if action.kind is ActionKind.ADD_ATTACKER:
            defender = action.targets[0].id
            add_attacker(state, action.source, defender)
            return  # the decision stays open for more attackers
        state.pending_decision = None
        finish_attackers(state)

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
        from_command = obj.zone is Zone.COMMAND
        from .costs import commander_cost, cost_reduction, spell_purpose

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
        elif action.evoked and card.evoke is not None:
            cost = card.evoke
        elif action.alternative and card.alternative_cost is not None:
            # Prowl and spectacle. The condition that let this line be offered
            # is not re-checked: legality asked it a moment ago, and a spell
            # whose price changed between being offered and being paid is the
            # bug `spell_purpose` exists to prevent elsewhere.
            cost = card.alternative_cost
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
            pid, card.name, card.cast_time_modes, kicked=action.kicked
        )

        ok = yield from pay(
            state,
            pid,
            Cost(mana=cost),
            None,
            x=x,
            extra_generic=extra,
            purpose=spell_purpose(card),
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

        if from_command:
            player = state.players[obj.owner]
            player.commander_tax[oid] = player.commander_tax.get(oid, 0) + 1

        item = stack.push_spell(
            state,
            oid,
            pid,
            action.targets,
            x=x,
            kicked=action.kicked,
            evoked=action.evoked,
            flashback=action.flashback,
            modes=modes,
        )
        triggers.fire(
            state,
            EventType.SPELL_CAST,
            player=pid,
            source=oid,
            oid=oid,
            spell_oid=oid,
            sid=item.sid,
            card=card.id,
            kicked=1 if action.kicked else 0,
        )

    def _activate(self, pid: int, action: Action) -> Generator[Any, list[int], None]:
        state = self.state
        oid = action.source
        card = state.card(oid)
        ability = card.abilities[action.ability_index]

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
                None,
                exclude_oid=oid if ability.cost.tap else None,
            )

        modes = yield from self._ask_modes(pid, card.name, ability.cast_time_modes)

        ok = yield from pay(state, pid, ability.cost, oid, x=x)
        if not ok:  # pragma: no cover
            return

        item = stack.push_activated_ability(
            state, oid, action.ability_index, pid, action.targets, x=x, modes=modes
        )
        state.emit(
            EventType.ABILITY_ACTIVATED,
            player=pid,
            source=oid,
            ability=action.ability_index,
            sid=item.sid,
            card=card.id,
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
    ) -> Generator[Any, list[int], int]:
        """How big is X, if this cost has one at all?

        The ceiling is recomputed here rather than taken from the action,
        because the board can have moved between legality offering the spell and
        this running -- a mana ability activated in response, most obviously.
        Using the same ``purpose`` and ``extra_generic`` the payment is about to
        use is what guarantees the largest offered X is payable.
        """
        if not cost.x_count:
            return 0
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

    def _ask_modes(
        self, pid: int, name: str, spec, *, kicked: bool = False
    ) -> Generator[Any, list[int], tuple[int, ...]]:
        """Which mode, asked as the spell or ability is put on the stack.

        ``spec`` is ``None`` for everything that is not a single top-level
        ``choose_mode`` -- see :attr:`CardDef.cast_time_modes` -- and those keep
        choosing as they resolve.

        Returns the chosen indices for :attr:`StackItem.modes`. Note the
        residual divergence from rule 601.2: targets are enumerated as part of
        the *action*, so they are already fixed by the time this runs, which is
        the reverse of the printed order. That is why the shared
        ``optional: true`` target idiom in docs/card-dsl.md is still required.
        """
        if not spec:
            return ()
        from .effects.context import EffectContext, ask_mode
        from .effects.values import evaluate_value

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
        count = evaluate_value(ctx, spec.get("count", 1))
        from .effects.conditions import evaluate as evaluate_condition

        if (gate := spec.get("all_if")) is not None and evaluate_condition(ctx, gate):
            count = len(modes)
        labels = [str(m.get("label") or f"Mode {i + 1}") for i, m in enumerate(modes)]
        chosen = yield from ask_mode(ctx, "Choose", labels, pid, max(1, count))
        return tuple(chosen)

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
        ability = card.abilities[action.ability_index]

        ok = yield from pay(state, pid, ability.cost, oid)
        if not ok:  # pragma: no cover - legality already proved payability
            return

        from .costs import activate_mana_ability

        activate_mana_ability(state, oid, action.ability_index, pid, action.mana_option or 0)
        state.emit(
            EventType.ABILITY_ACTIVATED,
            player=pid,
            source=oid,
            ability=action.ability_index,
            card=card.id,
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

            if state.pending_triggers:
                triggers.drain_to_stack(state)
                state.passes_in_row = 0
                state.priority_idx = state.active_idx
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
        ability = state.card(action.source).abilities[action.ability_index]
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
