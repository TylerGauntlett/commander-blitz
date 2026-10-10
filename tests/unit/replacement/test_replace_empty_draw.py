"""Winning instead of drawing from an empty library.

    Jace, Wielder of Mysteries — "If you would draw a card while your library
    has no cards in it, you win the game instead."
    Laboratory Maniac prints the same sentence.

The draw-replacement family had exactly one member, `replace_draw`, and it is a
pure *multiplier*: the loader requires `draw_multiplier` and refuses anything
below 2, so there is no key on it that can name a different outcome. This is the
one branch that static can never reach either way — there is no card to multiply
when the library is empty.

Two things decide where it goes, and both are about a race:

- **It replaces the draw rather than reacting to it.** `primitives.draw_cards`
  treats an empty library as an *attempt*, setting the 104.3c "will lose" flag
  with no `DRAW` event fired at all. So a trigger could not carry this line
  twice over: nothing would fire, and the state-based action would eliminate the
  player at the next check regardless. Replacing the draw means `draw_cards` is
  never called and the flag is never set.
- **It is checked before the doublers.** A `replace_draw` turns one draw into
  two, each offered this replacement in turn. Checked first, an empty library
  wins on the first of them; checked after, the card would still work but for
  the wrong reason, and the ordering would matter the moment a doubler's own
  behaviour depended on the draw succeeding.

The win itself goes through `sba.declare_win`, which eliminates every *other*
player and lets `check_game_over` draw its own conclusion (104.2a) — the engine
has one writer of a game result and this is not a second one.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import wins_on_empty_draw
from commanderblitz.engine.replacements import draw as draw_with_replacements

MANIAC = "t_lab_maniac"


def _board(builder, *, maniac: bool, library: int):
    extra = [MANIAC] if maniac else []
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 3 + extra)
        .library(0, ["forest"] * library)
        .library(1, ["forest"] * 20)
        .build()
    )


def _draw(game, pid: int, count: int = 1):
    """Run a draw through the replacement seam, declining every question."""
    gen = draw_with_replacements(game.state, pid, count)
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration as stop:
            return stop.value
        send = []


class TestTheWin:
    def test_drawing_from_an_empty_library_wins(self, builder):
        game = _board(builder, maniac=True, library=0)
        _draw(game, 0)
        assert game.over, "the game did not end"
        assert game.winners == [0], f"expected player 0 to win, got {game.winners}"

    def test_without_the_static_it_is_the_ordinary_loss(self, builder):
        """The pair. 104.3c: the attempt sets a flag and an SBA eliminates."""
        game = _board(builder, maniac=False, library=0)
        _draw(game, 0)
        assert game.state.players[0].attempted_draw_from_empty, (
            "the empty draw was not recorded as an attempt"
        )
        assert game.winners != [0]

    def test_the_will_lose_flag_is_never_set(self, builder):
        """The whole point of replacing rather than reacting.

        If the draw were allowed to happen and the win came afterwards, `sba`
        would see the flag at the next check -- which comes before anything a
        trigger could do -- and eliminate the player who was supposed to win.
        """
        game = _board(builder, maniac=True, library=0)
        _draw(game, 0)
        assert not game.state.players[0].attempted_draw_from_empty

    def test_a_nonempty_library_draws_as_usual(self, builder):
        """The near miss: this must not replace an ordinary draw."""
        game = _board(builder, maniac=True, library=5)
        got = _draw(game, 0)
        assert len(got) == 1
        assert len(game.state.players[0].library) == 4
        assert not game.over

    def test_it_wins_on_the_draw_that_empties_the_library(self, builder):
        """One card left, drawing two: the first succeeds, the second wins."""
        game = _board(builder, maniac=True, library=1)
        _draw(game, 0, 2)
        assert game.over
        assert game.winners == [0]


class TestWhoItAppliesTo:
    def test_an_opponent_drawing_empty_is_unaffected(self, builder):
        """"If **you** would draw" -- the static names one seat.

        The near miss a player-agnostic implementation passes silently: it would
        read identically on its own controller and hand the game to whoever
        decked first.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3 + [MANIAC])
            .library(0, ["forest"] * 20)
            .library(1, [])
            .build()
        )
        _draw(game, 1)
        assert not game.over
        assert game.state.players[1].attempted_draw_from_empty

    def test_the_permission_ends_when_the_source_leaves(self, builder):
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.zones import move_object
        from tests.conftest import only_oid

        game = _board(builder, maniac=True, library=0)
        assert wins_on_empty_draw(game.state, 0)
        move_object(game.state, only_oid(game, MANIAC), Zone.GRAVEYARD)
        assert not wins_on_empty_draw(game.state, 0)


class TestLoadTimeGuards:
    def _model(self, **over):
        ability = {
            "kind": "static",
            "text": "If you would draw a card while your library has no cards in it, you win the game instead.",
            "effect": "replace_empty_draw",
            "affects_player": "you",
        }
        ability.update(over)
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "oracle_text": ability["text"],
                "mana_cost": "{2}{U}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def test_affects_player_is_required(self):
        with pytest.raises(DslError, match="needs 'affects_player'"):
            compile_card(self._model(affects_player=None))

    @pytest.mark.parametrize("key", ["affects", "amount"])
    def test_a_key_nothing_reads_is_refused(self, key):
        """The replacement has no size, so neither key could mean anything --
        and a key that loads clean and is ignored prints a line that lies."""
        with pytest.raises(DslError, match="no 'affects' or 'amount'"):
            compile_card(self._model(**{key: {"types": ["Creature"]} if key == "affects" else 2}))

    def test_the_ordinary_card_loads(self):
        card = compile_card(self._model())
        assert card.abilities[0].static["effect"] == "replace_empty_draw"
