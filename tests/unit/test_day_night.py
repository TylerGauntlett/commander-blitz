"""Daybound and nightbound — the game-wide state the engine had no place for.

    "Daybound (If a player casts no spells during their own turn, it becomes
    night next turn.)"
    "Nightbound (If a player casts at least two spells during their own turn, it
    becomes day next turn.)" (726)

This was `refused` as needing "a game-wide designated state the engine has no
place to keep". That is an accurate description of the problem and the answer is
one field: `GameState.day_night`, which is the same shape `turn` and `step`
already are. Day and night belong to the **table**, not to a player and not to a
permanent, and the state object is where the table's facts live.

Everything else was already here:

| half | mechanism |
|---|---|
| "it becomes night" | `state.day_night`, and a turn-based action beside phasing |
| "cast no spells during their own turn" | `TurnLedger.spells_cast`, which storm folds in `emit` |
| the permanents turning over | `transform`, direction forced — daybound front, nightbound back |
| which way round a permanent is | `chars`, because the two keywords are printed one per face |

That last row is the piece worth naming. **Daybound is on the front face and
nightbound on the back**, so "is this permanent showing its night side?" is
already answered by the characteristics layer, and the switching code needs no
record of its own.

The boundaries are the two places a naive version gets it wrong, and both make
it night when it should not be:

- It starts as **neither**. A game with no daybound permanent in it never has a
  day, and a card reading "if it's day" has to say no.
- The very first untap step has no previous turn, so an empty ledger there reads
  as "cast no spells" and it would be night before anybody had played.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import Keyword
from automtg.engine.turn import _day_night
from tests.conftest import only_oid

MOUNTAIN = "mountain"
VILLAGER = "t_werewolf"        # {1}{R} 2/2 daybound
HOWLPACK = "t_werewolf_night"  # the back face: 4/4 trample, nightbound
BEAR = "t_bear"


def position(builder, board: list[str]):
    game = (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * 4)
        .battlefield(0, board)
        .library(0, [MOUNTAIN] * 20)
        .library(1, [MOUNTAIN] * 20)
        .build(advance=False)
    )
    return game


def settle(game, *, turn: int = 3, cast_by_previous: int = 0):
    """Run the turn-based action as though a turn had just ended."""
    game.state.turn = turn
    game.state.active_idx = 0
    game.state.turn_ledger.spells_cast.clear()
    # The previous seat, which `_day_night` reads: active_idx - 1.
    previous = game.state.players[-1].pid
    if cast_by_previous:
        game.state.turn_ledger.spells_cast[previous] = cast_by_previous
    _day_night(game.state, 0)


class TestItStartsAsNeither:
    def test_a_board_with_no_werewolf_never_becomes_day(self, builder):
        """726.2a needs a daybound permanent, and "if it's day" must say no."""
        game = position(builder, [BEAR])
        _day_night(game.state, 0)

        assert game.state.day_night is None

    def test_a_daybound_permanent_makes_it_day(self, builder):
        game = position(builder, [VILLAGER])
        _day_night(game.state, 0)

        assert game.state.day_night == "day"

    def test_becoming_day_does_not_also_turn_anything_over(self, builder):
        """726.2a only sets the designation; the card is already its day face."""
        game = position(builder, [VILLAGER])
        villager = only_oid(game, VILLAGER)
        _day_night(game.state, 0)

        assert game.state.card_of(game.state.objects[villager]).id == VILLAGER


class TestDayBecomesNight:
    def test_casting_no_spells_makes_it_night(self, builder):
        game = position(builder, [VILLAGER])
        _day_night(game.state, 0)
        settle(game, cast_by_previous=0)

        assert game.state.day_night == "night"

    def test_the_permanent_turns_over(self, builder):
        game = position(builder, [VILLAGER])
        villager = only_oid(game, VILLAGER)
        _day_night(game.state, 0)
        settle(game, cast_by_previous=0)

        assert game.state.card_of(game.state.objects[villager]).id == HOWLPACK
        c = chars(game.state, villager)
        assert (c.power, c.toughness) == (4, 4)
        assert Keyword.TRAMPLE.value in c.keywords

    def test_casting_one_spell_keeps_it_day(self, builder):
        game = position(builder, [VILLAGER])
        _day_night(game.state, 0)
        settle(game, cast_by_previous=1)

        assert game.state.day_night == "day"

    def test_the_first_turn_of_the_game_does_not_make_it_night(self, builder):
        """No previous turn, so the empty ledger is not "cast no spells"."""
        game = position(builder, [VILLAGER])
        _day_night(game.state, 0)
        game.state.turn = 1
        _day_night(game.state, 0)

        assert game.state.day_night == "day"


class TestNightBecomesDay:
    def _at_night(self, builder):
        game = position(builder, [VILLAGER])
        _day_night(game.state, 0)
        settle(game, cast_by_previous=0)
        return game, only_oid(game, VILLAGER)

    def test_two_spells_make_it_day(self, builder):
        game, _ = self._at_night(builder)
        settle(game, turn=5, cast_by_previous=2)

        assert game.state.day_night == "day"

    def test_one_spell_does_not(self, builder):
        game, _ = self._at_night(builder)
        settle(game, turn=5, cast_by_previous=1)

        assert game.state.day_night == "night"

    def test_no_spells_at_all_leaves_it_night(self, builder):
        """726.2c is the only way out of night, and it needs *two*."""
        game, _ = self._at_night(builder)
        settle(game, turn=5, cast_by_previous=0)

        assert game.state.day_night == "night"

    def test_the_permanent_turns_back(self, builder):
        game, villager = self._at_night(builder)
        settle(game, turn=5, cast_by_previous=2)

        assert game.state.card_of(game.state.objects[villager]).id == VILLAGER
        assert (chars(game.state, villager).power, chars(game.state, villager).toughness) == (2, 2)


class TestWhichFaceCarriesWhich:
    def test_daybound_is_the_front(self, builder):
        game = position(builder, [VILLAGER])
        villager = only_oid(game, VILLAGER)

        assert Keyword.DAYBOUND.value in chars(game.state, villager).keywords
        assert Keyword.NIGHTBOUND.value not in chars(game.state, villager).keywords

    def test_and_nightbound_is_the_back(self, builder):
        """Which is why the switching code keeps no record of its own."""
        game = position(builder, [VILLAGER])
        villager = only_oid(game, VILLAGER)
        _day_night(game.state, 0)
        settle(game, cast_by_previous=0)

        assert Keyword.NIGHTBOUND.value in chars(game.state, villager).keywords
        assert Keyword.DAYBOUND.value not in chars(game.state, villager).keywords
