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
        elif action.kind is ActionKind.ACTIVATE:
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
        from .costs import commander_cost, cost_reduction

        extra = commander_cost(state, oid) if from_command else 0
        # Netted against the tax rather than applied separately, so a commander
        # that also reduces its own cost is charged once. `pay` clamps at zero.
        extra -= cost_reduction(state, pid, card)

        # Kicker is an additional cost, paid at the same time as the mana cost
        # and not separable from it: there is no state in which the spell is on
        # the stack having paid one half.
        cost = card.mana_cost.plus(card.kicker) if action.kicked else card.mana_cost
        ok = yield from pay(state, pid, Cost(mana=cost), None, x=action.x, extra_generic=extra)
        if not ok:  # pragma: no cover - legality already proved payability
            return

        if from_command:
            player = state.players[obj.owner]
            player.commander_tax[oid] = player.commander_tax.get(oid, 0) + 1

        item = stack.push_spell(state, oid, pid, action.targets, x=action.x, kicked=action.kicked)
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

        ok = yield from pay(state, pid, ability.cost, oid, x=action.x)
        if not ok:  # pragma: no cover
            return

        item = stack.push_activated_ability(
            state, oid, action.ability_index, pid, action.targets, x=action.x
        )
        state.emit(
            EventType.ABILITY_ACTIVATED,
            player=pid,
            source=oid,
            ability=action.ability_index,
            sid=item.sid,
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


def _should_auto_pass(state: GameState, options: list[Action]) -> bool:
    """Whether to pass this priority window without asking.

    Eleven of the thirteen steps grant priority to every player, and instants
    and activated abilities are legal in all of them.  A player holding one
    instant therefore faced ~11 forced Pass clicks per turn, on every player's
    turn.  The stops below are the windows where passing is actually a choice:
    something is on the stack to respond to, it is your own sorcery-speed
    window, or blockers are declared and damage is next.
    """
    if len(options) == 1 and options[0].kind is ActionKind.PASS:
        # Nothing else is legal: offering this would waste a step for the agent
        # and a click for the human, regardless of policy.
        return True

    pid = state.priority_player
    if pid is None:
        return False
    player = state.players[pid]
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
