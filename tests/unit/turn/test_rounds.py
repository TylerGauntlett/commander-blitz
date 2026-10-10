"""``state.round`` -- full cycles of the table, as a player counts them.

``state.turn`` counts player-turns because that is what the rules need: summoning
sickness, the first-draw skip and the ``max_turns`` cap all read it.  But a
player in a four-player pod who has taken two turns sees ``turn`` reading 5, and
means "round 2".  The two numbers are therefore kept side by side.

The reason this is engine state rather than ``turn // num_players`` on the
client: eliminations.  ``next_alive_index`` skips a dead seat, so once anyone is
out the division drifts by one round per elimination, permanently.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step
from commanderblitz.engine.serialize import player_view
from commanderblitz.engine.turn import _begin_next_turn


def cycle(game, times: int = 1) -> None:
    """Hand the turn on ``times`` times, without playing anything."""
    for _ in range(times):
        _begin_next_turn(game.state)


class TestCounting:
    def test_a_new_game_starts_on_round_one(self, builder):
        game = builder().build(advance=False)
        assert game.state.turn == 1
        assert game.state.round == 1

    def test_two_players_take_one_round_between_them(self, builder):
        game = builder(players=2).build(advance=False)

        cycle(game)  # seat 1's turn
        assert (game.state.turn, game.state.round) == (2, 1)

        cycle(game)  # back to seat 0 -- a new round
        assert (game.state.turn, game.state.round) == (3, 2)

    def test_four_players_take_one_round_between_them(self, builder):
        game = builder(players=4).build(advance=False)

        for expected_turn in (2, 3, 4):
            cycle(game)
            assert game.state.round == 1, f"turn {expected_turn} is still round 1"
            assert game.state.turn == expected_turn

        cycle(game)  # wraps to seat 0
        assert (game.state.turn, game.state.round) == (5, 2)

    def test_the_round_is_not_turn_divided_by_seats(self, builder):
        """The whole point: the two counters diverge, and both are right."""
        game = builder(players=4).build(advance=False)
        cycle(game, 9)
        assert game.state.turn == 10
        assert game.state.round == 3


class TestStartingPlayer:
    """Rounds are anchored on whoever went first, not on seat 0.

    The starting seat is chosen at random.  Counting a round as "the index
    wrapped to 0" would put the first boundary in the middle of the opening lap
    whenever anybody but seat 0 leads, and the display would then read turn 2
    for the second player's *first* turn -- the exact off-by-one this counter
    exists to remove.
    """

    def test_a_late_starting_seat_still_gets_a_full_first_round(self, builder):
        game = builder(players=2).build(advance=False)
        game.state.starting_player = 1
        game.state.active_idx = 1

        cycle(game)  # seat 1 -> seat 0, still the first lap
        assert (game.state.turn, game.state.round) == (2, 1)

        cycle(game)  # back to seat 1, a new lap
        assert (game.state.turn, game.state.round) == (3, 2)

    def test_a_four_player_pod_starting_at_seat_two(self, builder):
        game = builder(players=4).build(advance=False)
        game.state.starting_player = 2
        game.state.active_idx = 2

        for expected_turn in (2, 3, 4):  # seats 3, 0, 1
            cycle(game)
            assert game.state.round == 1, f"turn {expected_turn} is still round 1"
            assert game.state.turn == expected_turn

        cycle(game)  # back to seat 2
        assert (game.state.turn, game.state.round) == (5, 2)


class TestElimination:
    def test_a_dead_seat_is_skipped_without_losing_a_round(self, builder):
        """The case a client-side division cannot get right.

        Four seats, one dead.  Three turns now make a round, and ``turn`` and
        ``round`` stop being a fixed ratio for the rest of the game.
        """
        game = builder(players=4).build(advance=False)
        game.state.players[2].has_lost = True

        cycle(game)  # 0 -> 1
        assert game.state.round == 1
        cycle(game)  # 1 -> 3, skipping the dead seat 2
        assert game.state.active_idx == 3
        assert game.state.round == 1
        cycle(game)  # 3 -> 0, a wrap
        assert game.state.active_idx == 0
        assert game.state.round == 2

        # Three turns to the round now, so turn 7 is round 3 -- not 7 // 4.
        cycle(game, 3)
        assert (game.state.turn, game.state.round) == (7, 3)

    def test_a_lone_survivor_gets_a_round_per_turn(self, builder):
        game = builder(players=2).build(advance=False)
        game.state.players[1].has_lost = True

        cycle(game)
        assert game.state.active_idx == 0
        assert game.state.round == 2


class TestSerialized:
    def test_the_client_receives_both_numbers(self, builder):
        game = builder(players=2).step(Step.PRECOMBAT_MAIN).build(advance=False)
        cycle(game, 2)

        view = player_view(game.state, 0)
        assert view["turn"] == 3
        assert view["round"] == 2

    def test_turn_keeps_its_rules_meaning(self, builder):
        """Guard against anyone "fixing" the counter the UI complained about.

        ``turn`` feeds ``GameObject.summoning_sick``; a creature that entered on
        turn 3 is sick on turn 3 and not on turn 4, regardless of rounds.
        """
        game = builder(players=4).battlefield(0, ["t_bear"], sick=True).build(advance=False)
        oid = game.state.battlefield[0]
        assert game.state.objects[oid].summoning_sick(game.state.turn)

        cycle(game)  # still round 1, but a new turn
        assert game.state.round == 1
        assert not game.state.objects[oid].summoning_sick(game.state.turn)
