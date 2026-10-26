"""Energy counters (107.14): "you get {E}{E} (two energy counters)."

Nissa, Worldsoul Speaker is the witness: her landfall gives energy and her
static spends it. Rule 122.1 makes energy a **counter on a player**, the same
kind of thing poison is, so it is held the way poison is held
(`PlayerState.energy`) and given through one funnel (`primitives.add_energy`).
Without the funnel, three things a counter must do would each be missed:

- A replacement that reaches players -- Innkeeper's Talent's "…on a permanent
  **or player**" -- doubles energy as it doubles poison.
- Proliferate (701.27a) gives a chosen player one more of **each kind**
  already there, so a player with energy is offered, and one with poison and
  energy gets one of each.
- Nothing about energy ends the game. It is a resource, not a clock, and a
  player with a hundred of it is as alive as one with none.

The client draws it from `player_view`, which is pinned here too: a number a
player spends has to be one they can read.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import add_energy
from commanderblitz.engine.serialize import player_view

TALENT = "t_pb_talent"  # Innkeeper's Talent level 3: counters you put are doubled
BEAR = "t_bear"


def board(builder, mine=()):
    return builder(players=2).battlefield(0, list(mine)).build()


def run(game, effects, controller: int = 0, answer=None) -> None:
    """Resolve effects outside the stack, answering any question with ``answer``."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, effects)
    try:
        decision = next(gen)
        while True:
            decision = gen.send(answer(decision))
    except StopIteration:
        pass


def everything(decision) -> list[int]:
    return list(range(len(decision.options)))


class TestGettingEnergy:
    def test_you_get_the_printed_amount(self, builder):
        game = board(builder)
        run(game, [{"op": "add_energy", "amount": {"const": 2}}])
        assert game.state.players[0].energy == 2
        assert game.state.players[1].energy == 0, "'you get', so only the controller"

    def test_it_accumulates(self, builder):
        game = board(builder)
        run(game, [{"op": "add_energy", "amount": {"const": 2}}])
        run(game, [{"op": "add_energy", "amount": {"const": 3}}])
        assert game.state.players[0].energy == 5

    def test_the_amount_defaults_to_one(self, builder):
        game = board(builder)
        run(game, [{"op": "add_energy"}])
        assert game.state.players[0].energy == 1

    def test_a_player_key_reaches_other_seats(self, builder):
        game = board(builder)
        run(game, [{"op": "add_energy", "player": "each_opponent", "amount": {"const": 1}}])
        assert game.state.players[1].energy == 1
        assert game.state.players[0].energy == 0

    def test_zero_gives_nothing_and_says_nothing(self, builder):
        game = board(builder)
        game.state.events.clear()
        run(game, [{"op": "add_energy", "amount": {"const": 0}}])
        assert game.state.players[0].energy == 0
        assert not [e for e in game.state.events if e.type is EventType.ENERGY_ADDED]

    def test_the_event_carries_the_amount_and_the_total(self, builder):
        game = board(builder)
        game.state.players[0].energy = 4
        game.state.events.clear()
        run(game, [{"op": "add_energy", "amount": {"const": 2}}])
        (event,) = [e for e in game.state.events if e.type is EventType.ENERGY_ADDED]
        assert event.player == 0
        assert event.data["amount"] == 2
        assert event.data["total"] == 6


class TestItIsACounter:
    def test_a_replacement_that_reaches_players_doubles_it(self, builder):
        game = board(builder, mine=[TALENT])
        assert add_energy(game.state, 0, 2, by=0) == 4
        assert game.state.players[0].energy == 4

    def test_the_replacement_reads_who_put_them(self, builder):
        """The Talent doubles counters *you* put; an opponent's energy is theirs."""
        game = board(builder, mine=[TALENT])
        assert add_energy(game.state, 1, 2, by=1) == 2

    def test_proliferate_offers_a_player_with_energy(self, builder):
        game = board(builder)
        game.state.players[0].energy = 3
        asked = []

        def pick(decision):
            asked.append([o.label for o in decision.options])
            return everything(decision)

        run(game, [{"op": "proliferate"}], answer=pick)
        assert any("energy" in label for label in asked[0])
        assert game.state.players[0].energy == 4

    def test_proliferate_gives_one_of_each_kind(self, builder):
        game = board(builder)
        game.state.players[1].energy = 2
        game.state.players[1].poison = 1
        run(game, [{"op": "proliferate"}], answer=everything)
        assert game.state.players[1].energy == 3
        assert game.state.players[1].poison == 2

    def test_proliferate_never_starts_energy(self, builder):
        game = board(builder)
        game.state.players[1].poison = 1
        run(game, [{"op": "proliferate"}], answer=everything)
        assert game.state.players[1].energy == 0, "it never starts a kind"

    def test_no_amount_of_energy_ends_the_game(self, builder):
        game = board(builder)
        game.state.players[1].energy = 100
        sba.check(game.state)
        assert not game.state.players[1].has_lost


class TestTheView:
    def test_every_seat_sees_every_seats_energy(self, builder):
        game = board(builder)
        game.state.players[1].energy = 7
        view = player_view(game.state, 0)
        assert [p["energy"] for p in view["players"]] == [0, 7]

    def test_the_raw_state_carries_it(self, builder):
        game = board(builder)
        game.state.players[0].energy = 2
        assert game.state.players[0].to_dict()["energy"] == 2


class TestTheLoader:
    def _card(self, amount):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "You get {E}{E} (two energy counters).",
                "mana_cost": "{R}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "add_energy", "amount": amount}],
            }
        )

    def test_a_value_amount_loads(self):
        compile_card(self._card({"const": 2}))

    def test_a_malformed_amount_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self._card({"nonsense": 2}))
