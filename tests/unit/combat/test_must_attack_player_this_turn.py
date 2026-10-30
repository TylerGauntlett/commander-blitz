"""`must_attack_player` with ``duration: "this_turn"`` -- "…tokens with flying
that attack that opponent this turn if able" (508.1d, 611.2a).

Furygale Flocking is the witness: for each opponent it makes two Elementals
that must attack *that* opponent this turn. The two near misses were both
wrong cards. `must_attack` with ``this_turn`` names no defender, so in a pod
the tokens could swing at anybody; `must_attack_player`'s one clock,
"until the end of your next turn", would compel them again a turn later.

What is pinned:

1. The mark names its player, exactly as the long clock's does: only an
   attack on that seat obeys it.
2. It ends in the cleanup of the turn it was made in, on anybody's turn --
   and carries no seat's clock, so a player leaving does not need to end it.
3. The op writes it, and the loader accepts the word.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.temp_effects import require_attack_player
from tests.conftest import only_oid, pass_until
from tests.unit.combat.test_attack_requirement_defender import (
    BEAR,
    _sorcery,
    position,
    run_op,
    targets_offered,
    to_declare_attackers,
)


def mark_this_turn(game, oid: int, defender: int) -> None:
    assert require_attack_player(game.state, oid, defender, 0, this_turn=True)


class TestTheMark:
    def test_it_names_that_player_and_no_other(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark_this_turn(game, bear, 2)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert targets_offered(game, bear) == ([2], [])

    def test_the_op_writes_a_mark_with_no_seats_clock(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        run_op(
            game,
            {
                "op": "must_attack_player",
                "objects": {"controller": "any", "types": ["Creature"]},
                "defender": {"binding": "defender"},
                "duration": "this_turn",
            },
            controller=0,
            defender=3,
        )
        (only,) = game.state.objects[bear].attack_marks
        assert only.defender == 3
        assert only.this_turn
        assert only.until_end_of_turn_of is None


class TestTheClock:
    def test_it_ends_in_this_turns_cleanup(self, builder):
        """The near miss is the long clock, which survives this cleanup."""
        game = position(builder, mine=(BEAR,), players=2, lives=(20, 20))
        bear = only_oid(game, BEAR, 0)
        mark_this_turn(game, bear, 1)
        assert game.state.objects[bear].attack_marks
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[bear].attack_marks == []

    def test_the_long_clock_beside_it_survives(self, builder):
        game = position(builder, mine=(BEAR,), players=2, lives=(20, 20))
        bear = only_oid(game, BEAR, 0)
        assert require_attack_player(game.state, bear, 1, 0)
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[bear].attack_marks

    def test_it_ends_on_an_opponents_turn_too(self, builder):
        """Made during somebody else's turn, it still ends that turn: "this
        turn" is the turn the effect resolved in, not the controller's next."""
        game = position(builder, mine=(BEAR,), players=2, lives=(20, 20))
        bear = only_oid(game, BEAR, 0)
        pass_until(game, lambda g: g.state.turn >= 2)
        mark_this_turn(game, bear, 1)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.objects[bear].attack_marks == []


class TestTheLoader:
    def test_this_turn_is_accepted(self):
        effect = {
            "op": "must_attack_player",
            "objects": {"types": ["Creature"]},
            "defender": "each_opponent",
            "duration": "this_turn",
        }
        assert compile_card(CardModel.model_validate(_sorcery(effect)))
