"""Game-outcome prohibitions — "you can't lose", "your opponents can't win".

    Angel's Grace — "Split second. You can't lose the game this turn and your
    opponents can't win the game this turn. Until end of turn, damage that would
    reduce your life total to less than 1 reduces it to 1 instead."

This is the subsystem `sba.declare_win`'s own docstring listed as **deliberately
not modelled**, "because no card in the pool needs it yet", adding that it "is
replacement-shaped and belongs beside the other continuous prohibitions".
`docs/rules-coverage.md` recorded the same thing. Angel's Grace is the first card
in the pool to need it, and the same pass unblocks the Platinum Angel and Abyssal
Persecutor family those notes name.

### Two flags, because they are two sentences

Angel's Grace prints both halves and most cards print one. Platinum Angel says
"you can't lose the game **and** your opponents can't win the game"; Abyssal
Persecutor says only "you can't win the game". A single symmetric flag would make
every card in the family read like Platinum Angel, so `OutcomeLock` carries
`cant_lose` and `cant_win` independently and Angel's Grace writes them about
*different seats*. `TestTheTwoHalvesAreIndependent` is that claim.

### The floor is not a Fog, and 104.3b is why it matters

`prevent_damage` the op is the near miss: it installs a `DamageShield`, the total
never moves, and a player at 40 ends the turn at **40**. Angel's Grace lets the
damage through and stops the total passing 1 — you survive *at* 1 or less, which
is the whole point of the card and the reason it pairs the floor with the
prohibition. Surviving at 1 is worth nothing if the next point kills you, and
being unable to lose is worth nothing if you are at -40 when it wears off.

`TestItSurvivesAtOrBelowOne` and `TestTheLockEndsAndThenYouLose` are the pair that
pins that reading: the player really is at negative life, really is still in the
game, and really does lose the moment the lock clears — rather than the total
being quietly rewritten to 1.

### What it floors, and what it does not

**Damage only**, which is the printed word. An ordinary `lose_life` walks past it,
so a Phyrexian cost or a Bitterblossom still takes you below 1 under Angel's
Grace. That is correct, and it is why the floor is read in `damage_player` and
nowhere else — `TestItFloorsDamageAndNotEveryLoss` measures the difference.

Witness: Angel's Grace (`angel_s_grace` in `data/cards/auto/`).
"""

from __future__ import annotations

from commanderblitz.engine import sba
from commanderblitz.engine.primitives import damage_player, lose_life
from commanderblitz.engine.sba import player_cant_lose, player_cant_win
from commanderblitz.engine.temp_effects import (
    clear_life_floors,
    clear_outcome_locks,
    life_floor,
    lock_game_outcome,
    set_life_floor,
)

PLAINS = "plains"


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS])
        .battlefield(1, ["forest"])
        .hand(0, [PLAINS])
        .hand(1, [PLAINS])
        .build(advance=False)
    )


class TestTheFloorHoldsTheTotal:
    def test_a_huge_hit_lands_on_one(self, builder):
        game = board(builder)
        set_life_floor(game.state, 0, 1)

        damage_player(game.state, 0, 100, None)

        assert game.state.players[0].life == 1

    def test_a_small_hit_is_unchanged(self, builder):
        """The floor is a floor, not a fog: ordinary damage lands normally."""
        game = board(builder)
        set_life_floor(game.state, 0, 1)

        damage_player(game.state, 0, 5, None)

        assert game.state.players[0].life == 35

    def test_without_the_floor_the_hit_goes_through(self, builder):
        """Pins that the flooring is the record's and not the position's."""
        game = board(builder)
        damage_player(game.state, 0, 100, None)
        assert game.state.players[0].life == -60

    def test_it_protects_only_the_named_seat(self, builder):
        game = board(builder)
        set_life_floor(game.state, 0, 1)

        damage_player(game.state, 1, 100, None)

        assert game.state.players[1].life == -60

    def test_the_stricter_of_two_floors_wins(self, builder):
        """Two floors are two prohibitions, so the higher one bites."""
        game = board(builder)
        set_life_floor(game.state, 0, 1)
        set_life_floor(game.state, 0, 3)
        assert life_floor(game.state, 0) == 3

        damage_player(game.state, 0, 100, None)

        assert game.state.players[0].life == 3


class TestItFloorsDamageAndNotEveryLoss:
    """"**Damage** that would reduce your life total" -- the printed word.

    An ordinary life payment is not damage, so it walks past the floor. A version
    that floored every loss would make Angel's Grace stop you paying Phyrexian
    costs, which it does not.
    """

    def test_plain_life_loss_ignores_the_floor(self, builder):
        game = board(builder)
        set_life_floor(game.state, 0, 1)

        lose_life(game.state, 0, 100)

        assert game.state.players[0].life == -60

    def test_and_damage_on_the_same_board_is_still_floored(self, builder):
        game = board(builder)
        set_life_floor(game.state, 0, 1)

        damage_player(game.state, 0, 100, None)

        assert game.state.players[0].life == 1


class TestItSurvivesAtOrBelowOne:
    """104.3b: the player keeps playing at zero or less and loses when the lock
    ends. That is what the card buys -- a turn to find an answer."""

    def test_a_locked_player_at_negative_life_stays_in_the_game(self, builder):
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_lose=True)
        game.state.players[0].life = -4

        sba._player_losses(game.state)

        assert player_cant_lose(game.state, 0) is True
        assert game.state.players[0].has_lost is False
        assert game.state.players[0].life == -4, "the total is not rewritten"

    def test_an_unlocked_player_at_negative_life_loses(self, builder):
        """Pins that the survival is the lock's doing."""
        game = board(builder)
        game.state.players[0].life = -4

        sba._player_losses(game.state)

        assert game.state.players[0].has_lost is True

    def test_it_holds_off_every_loss_reason(self, builder):
        """"You can't lose the game", full stop -- so an empty library is held off
        as well as a life total."""
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_lose=True)
        game.state.players[0].attempted_draw_from_empty = True

        sba._player_losses(game.state)

        assert game.state.players[0].has_lost is False

    def test_the_other_seat_is_unprotected(self, builder):
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_lose=True)
        game.state.players[1].life = -1

        sba._player_losses(game.state)

        assert game.state.players[1].has_lost is True


class TestTheLockEndsAndThenYouLose:
    def test_the_cleanup_sweep_drops_it(self, builder):
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_lose=True)

        clear_outcome_locks(game.state, "this_turn")

        assert player_cant_lose(game.state, 0) is False

    def test_and_the_next_sweep_eliminates(self, builder):
        """The whole arc of the card, in one test: saved at negative life, then
        lost when the turn ends."""
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_lose=True)
        game.state.players[0].life = -4
        sba._player_losses(game.state)
        assert game.state.players[0].has_lost is False

        clear_outcome_locks(game.state, "this_turn")
        sba._player_losses(game.state)

        assert game.state.players[0].has_lost is True

    def test_the_floor_is_swept_too(self, builder):
        game = board(builder)
        set_life_floor(game.state, 0, 1)

        clear_life_floors(game.state, "this_turn")

        assert life_floor(game.state, 0) is None


class TestTheTwoHalvesAreIndependent:
    """Platinum Angel says both, Abyssal Persecutor says only "you can't win".

    A single symmetric flag would make every card in the family read like the
    Angel, so the two are separate fields written about separate seats.
    """

    def test_cant_lose_does_not_imply_cant_win(self, builder):
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_lose=True)

        assert player_cant_lose(game.state, 0) is True
        assert player_cant_win(game.state, 0) is False

    def test_cant_win_does_not_imply_cant_lose(self, builder):
        """The Abyssal Persecutor shape: you cannot win, and you can still die."""
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_win=True)

        assert player_cant_win(game.state, 0) is True
        assert player_cant_lose(game.state, 0) is False

    def test_angels_grace_writes_them_about_different_seats(self, builder):
        """The printed card: *you* can't lose, *your opponents* can't win."""
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_lose=True)
        lock_game_outcome(game.state, 1, cant_win=True)

        assert player_cant_lose(game.state, 0) and not player_cant_win(game.state, 0)
        assert player_cant_win(game.state, 1) and not player_cant_lose(game.state, 1)


class TestAWinIsRefusedWhole:
    """`declare_win` implements a win by eliminating everybody else, so the check
    belongs there and not in `_eliminate`.

    Checked one layer down it would eliminate some opponents and then stop,
    leaving a half-dismantled board with no declared result.
    """

    def test_a_locked_player_cannot_win(self, builder):
        game = board(builder)
        lock_game_outcome(game.state, 0, cant_win=True)

        sba.declare_win(game.state, 0)

        assert game.state.game_over is False
        assert game.state.players[1].has_lost is False, "nobody was eliminated"

    def test_an_unlocked_player_can(self, builder):
        """Pins that the refusal is the lock's doing."""
        game = board(builder)

        sba.declare_win(game.state, 0)

        assert game.state.game_over is True
        assert game.state.winners == [0]

    def test_angels_grace_stops_an_opponents_win(self, builder):
        """The printed half that matters most: an opponent's Approach of the
        Second Sun resolves and does not end the game."""
        game = board(builder)
        lock_game_outcome(game.state, 1, cant_win=True)

        sba.declare_win(game.state, 1)

        assert game.state.game_over is False
        assert game.state.players[0].has_lost is False
