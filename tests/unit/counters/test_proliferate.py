"""Proliferate (701.27a): "Choose any number of permanents and/or players, then
give each another counter of each kind already there."

Two things make it not an `add_counters` with a filter, and each would be
wrong quietly without it.

**The kinds are read per chosen thing, at resolution.** One proliferate adds a
+1/+1 counter to one creature, a loyalty counter to a planeswalker and a poison
counter to a player; nothing names those kinds in advance, only reading each
object's own dict (and each player's poison) does. It never starts a kind, and a
kind pruned to zero is not a kind.

**It is a choice, and declining is half of it.** The op used to proliferate
every permanent its controller had with a counter and never touched a player or
an opponent's permanent -- so Viral Drake, an infect card, could not grow the
poison it deals, and nothing could grow the -1/-1 counters on an opponent's
creature, while a -1/-1 counter on your own creature grew whether you wanted it
or not. Now the controller picks any subset of every permanent (any controller)
and every player with a counter, in one `ask_targets` decision tagged
``"proliferate"``. It does not target, so hexproof does not stop it.

The witnesses are Atraxa, Praetors' Voice and Viral Drake.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from tests.conftest import action_for_card, oids_of, only_oid

BEAR = "t_bear"
WALL = "t_wall"
BIG = "t_big"
HEXPROOF = "t_hexproof"
PROLIFERATOR = "t_proliferator"

Answer = Callable[[object], list[int]]


def everything(decision) -> list[int]:
    return list(range(len(decision.options)))


def nothing(decision) -> list[int]:
    return []


def only(*refs: tuple[str, int]) -> Answer:
    """Choose exactly the options whose ref is one of ``(kind, id)``."""

    def pick(decision) -> list[int]:
        return [
            i
            for i, option in enumerate(decision.options)
            if (option.ref.kind, option.ref.id) in refs
        ]

    return pick


def proliferate(game, answer: Answer = everything, controller: int = 0) -> list:
    """Resolve one proliferate outside the stack; return the decisions it asked."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [{"op": "proliferate"}])
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send(answer(decision))
    except StopIteration:
        pass
    return asked


def counters_of(game, oid: int) -> dict:
    return dict(game.state.objects[oid].counters)


def position(builder, **counters_by_seat):
    """A bear for each seat with the given counters (``p0=``, ``p1=``)."""
    b = builder(players=2)
    for seat in (0, 1):
        b = b.battlefield(seat, [BEAR], counters=counters_by_seat.get(f"p{seat}") or {})
    game = b.build()
    return game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)


class TestItAddsOneOfEachKindAlreadyThere:
    def test_a_single_kind_grows_by_one(self, builder):
        game, mine, _ = position(builder, p0={"+1/+1": 1})
        proliferate(game)
        assert counters_of(game, mine) == {"+1/+1": 2}

    def test_every_kind_grows_together(self, builder):
        game, mine, _ = position(builder, p0={"+1/+1": 1, "charge": 2})
        proliferate(game)
        assert counters_of(game, mine) == {"+1/+1": 2, "charge": 3}

    def test_different_permanents_grow_different_kinds(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(0, [BIG], counters={"loyalty": 4})
            .build()
        )
        bear, big = only_oid(game, BEAR, 0), only_oid(game, BIG, 0)
        proliferate(game)
        assert counters_of(game, bear) == {"+1/+1": 2}
        assert counters_of(game, big) == {"loyalty": 5}

    def test_one_counter_each_however_many_are_there(self, builder):
        """"**Another** counter", singular, not a doubling."""
        game, mine, _ = position(builder, p0={"+1/+1": 6})
        proliferate(game)
        assert counters_of(game, mine) == {"+1/+1": 7}


class TestItStartsNothing:
    def test_a_permanent_with_no_counters_is_not_offered(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WALL])
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .build()
        )
        wall = only_oid(game, WALL, 0)
        [decision] = proliferate(game)
        assert wall not in [o.ref.id for o in decision.options if o.ref.kind == "object"]
        assert counters_of(game, wall) == {}

    def test_nothing_with_a_counter_asks_nothing(self, builder):
        game = builder(players=2).battlefield(0, [WALL]).build()
        assert proliferate(game) == []

    def test_a_kind_pruned_to_zero_is_not_a_kind(self, builder):
        """`add_counter` removes the entry at zero; a stale key would make a
        permanent proliferable for a counter it no longer has."""
        game, mine, _ = position(builder, p0={"+1/+1": 1})
        game.state.objects[mine].add_counter("+1/+1", -1)
        assert proliferate(game) == []
        assert counters_of(game, mine) == {}

    def test_a_player_with_no_poison_is_not_offered(self, builder):
        game, _, _ = position(builder, p0={"+1/+1": 1})
        [decision] = proliferate(game)
        assert all(o.ref.kind == "object" for o in decision.options)


class TestTheControllerChooses:
    def test_it_is_one_decision_for_any_number(self, builder):
        game, _, _ = position(builder, p0={"+1/+1": 1}, p1={"+1/+1": 1})
        game.state.players[1].poison = 2
        [decision] = proliferate(game)
        assert decision.player == 0
        assert decision.context["purpose"] == "proliferate"
        assert (decision.min_count, decision.max_count) == (0, 3)

    def test_choosing_nothing_grows_nothing(self, builder):
        game, mine, theirs = position(builder, p0={"+1/+1": 1}, p1={"-1/-1": 1})
        game.state.players[1].poison = 2
        proliferate(game, nothing)
        assert counters_of(game, mine) == {"+1/+1": 1}
        assert counters_of(game, theirs) == {"-1/-1": 1}
        assert game.state.players[1].poison == 2

    def test_only_what_was_chosen_grows(self, builder):
        game, mine, theirs = position(builder, p0={"-1/-1": 1}, p1={"-1/-1": 1})
        proliferate(game, only(("object", theirs)))
        assert counters_of(game, mine) == {"-1/-1": 1}
        assert counters_of(game, theirs) == {"-1/-1": 2}

    def test_an_opponents_permanent_can_be_chosen(self, builder):
        game, _, theirs = position(builder, p1={"+1/+1": 1})
        proliferate(game)
        assert counters_of(game, theirs) == {"+1/+1": 2}

    def test_hexproof_does_not_stop_it(self, builder):
        """No "target" in 701.27a."""
        game = builder(players=2).battlefield(1, [HEXPROOF], counters={"-1/-1": 1}).build()
        oid = only_oid(game, HEXPROOF, 1)
        proliferate(game)
        assert counters_of(game, oid) == {"-1/-1": 2}


class TestPlayersToo:
    def test_an_opponents_poison_grows(self, builder):
        game, _, _ = position(builder)
        game.state.players[1].poison = 3
        proliferate(game, only(("player", 1)))
        assert game.state.players[1].poison == 4

    def test_it_is_a_poison_event(self, builder):
        game, _, _ = position(builder)
        game.state.players[1].poison = 3
        proliferate(game)
        added = [e for e in game.state.events if e.type is EventType.POISON_ADDED]
        assert added and added[-1].data["total"] == 4

    def test_the_tenth_counter_is_lethal(self, builder):
        game, _, _ = position(builder)
        game.state.players[1].poison = 9
        proliferate(game)
        sba._player_losses(game.state)
        assert game.state.players[1].has_lost


class TestTheCardLoads:
    def test_the_proliferate_card_compiles(self, registry):
        card = registry.get(PROLIFERATOR)
        assert [e["op"] for e in card.spell_effects] == ["proliferate"]

    def test_the_retired_objects_key_is_refused(self):
        """A selector would decide for the player what 701.27a lets them choose."""
        with pytest.raises(DslError, match="proliferate takes no 'objects'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "types": ["Sorcery"],
                        "spell_effects": [
                            {"op": "proliferate", "objects": {"controller": "you"}}
                        ],
                    }
                )
            )


class TestTheHeuristicAgent:
    def cast(self, builder, poison=(0, 0), **counters_by_seat):
        b = builder(players=2).hand(0, [PROLIFERATOR]).battlefield(0, ["island"] * 2)
        b = b.battlefield(0, [BEAR], counters=counters_by_seat.get("p0") or {})
        b = b.battlefield(1, [BEAR], counters=counters_by_seat.get("p1") or {})
        game = b.build()
        for seat, n in enumerate(poison):
            game.state.players[seat].poison = n
        game.apply(action_for_card(game, ActionKind.CAST, PROLIFERATOR))
        return game

    def answer(self, game) -> None:
        from automtg.ai.agents.heuristic_agent import HeuristicAgent

        agent = HeuristicAgent(seed=0)
        for _ in range(200):
            decision = game.pending()
            if decision.context.get("purpose") == "proliferate":
                while (game.pending().context or {}).get("purpose") == "proliferate":
                    game.apply(agent.act(game, 0, game.legal_actions()))
                return
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        raise AssertionError("proliferate was never asked")

    def test_it_grows_what_helps_and_declines_what_hurts(self, builder):
        game = self.cast(builder, poison=(1, 1), p0={"+1/+1": 1}, p1={"+1/+1": 1})
        self.answer(game)
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        assert counters_of(game, mine) == {"+1/+1": 2}
        assert counters_of(game, theirs) == {"+1/+1": 1}
        assert game.state.players[0].poison == 1
        assert game.state.players[1].poison == 2

    def test_it_grows_their_minus_counters_and_never_ours(self, builder):
        game = self.cast(builder, p0={"-1/-1": 1}, p1={"-1/-1": 1})
        mine = only_oid(game, BEAR, 0)
        self.answer(game)
        assert counters_of(game, mine) == {"-1/-1": 1}
        # Their 2/2 took its second -1/-1 counter and died of it.
        assert oids_of(game, BEAR, 1) == []
