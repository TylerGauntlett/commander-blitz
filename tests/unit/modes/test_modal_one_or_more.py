""""Choose one or more --": a floor and a ceiling at the same time.

    Black Market Connections — "At the beginning of your first main phase,
    choose one or more — • … • … • …"

Four modal spellings existed and none of them said this between them. `count` is
exact, so "choose one or more" written as `count: 1` deletes the words "or
more" and the card becomes a one-mode spell. `all_if` is entwine and forces
every mode. `up_to` is the ceiling with **no floor**, so it would let the
trigger resolve having chosen nothing -- which for Black Market Connections is a
strictly better card, since every mode costs life. `up_to_if` has the right
shape and demands a `condition`, and "one or more" is not conditional on
anything; a filled-in always-true condition would be a lie in the card file.

So `or_more` is the fifth clause of `modal_bounds`: the floor stays whatever
`count` says and the ceiling opens to every mode.

Both copies of the modal question are covered here, because they are answered in
different places: a spell whose whole effect tree is one top-level `choose_mode`
is answered at cast time by `Game._ask_modes` (601.2b), and a *triggered*
ability's modes are picked as it goes on the stack (603.3d). The bound has to be
the same number in both, which is why `modal_bounds` is one function.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card

SPELL = "t_choose_one_or_more"  # gain 3 life / draw a card / lose 1 life


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .hand(0, [SPELL])
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_and_choose(game, picks):
    """Cast the spell and take the modes at indices ``picks``."""
    game.apply(action_for_card(game, ActionKind.CAST, SPELL))
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.CHOOSE_MODE:
            for want in picks:
                choose = next(
                    (
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE and a.choice == want
                    ),
                    None,
                )
                if choose is None:
                    break
                game.apply(choose)
            done = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.FINISH_DECLARATION
                ),
                None,
            )
            if done is not None:
                game.apply(done)
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))


def mode_decision(game):
    game.apply(action_for_card(game, ActionKind.CAST, SPELL))
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.CHOOSE_MODE:
            return decision
        game.apply(_default_answer(game, decision))
    raise AssertionError("the modes were never asked for")


class TestTheBounds:
    def test_the_floor_is_one_and_the_ceiling_is_every_mode(self, builder):
        decision = mode_decision(board(builder))
        assert decision.min_count == 1, "'one or more' still means at least one"
        assert decision.max_count == 3, "…and there is no ceiling below all of them"

    def test_every_mode_is_offered(self, builder):
        assert len(mode_decision(board(builder)).options) == 3


class TestTakingThem:
    def test_one_mode_is_enough(self, builder):
        game = board(builder)
        life = game.state.players[0].life
        cast_and_choose(game, [0])
        assert game.state.players[0].life == life + 3

    def test_two_modes_both_happen(self, builder):
        game = board(builder)
        life, library = (
            game.state.players[0].life,
            len(game.state.players[0].library),
        )
        cast_and_choose(game, [0, 1])
        assert game.state.players[0].life == life + 3
        assert len(game.state.players[0].library) == library - 1

    def test_all_three_are_reachable(self, builder):
        """The ceiling `count` alone would have imposed, and the whole point."""
        game = board(builder)
        life, library = (
            game.state.players[0].life,
            len(game.state.players[0].library),
        )
        cast_and_choose(game, [0, 1, 2])
        assert game.state.players[0].life == life + 3 - 1
        assert len(game.state.players[0].library) == library - 1

    def test_choosing_none_is_not_offered(self, builder):
        """`up_to`'s line, and the one this spelling exists to refuse."""
        decision = mode_decision(board(builder))
        assert decision.min_count >= 1


class TestTheLoaderRefusesNonsense:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_or_more",
                "name": "Bad Or More",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Sorcery"],
                "colors": ["W"],
                "color_identity": ["W"],
                "spell_effects": [effect],
            }
        )

    def _modes(self, n):
        return [{"label": chr(65 + i), "effects": [{"op": "noop"}]} for i in range(n)]

    def test_or_more_on_another_op_is_a_load_error(self):
        with pytest.raises(DslError, match="or_more"):
            compile_card(
                self._card({"op": "draw", "amount": {"const": 1}, "or_more": True})
            )

    def test_it_cannot_be_combined_with_up_to(self):
        """One keeps a floor and the other removes it."""
        with pytest.raises(DslError, match="contradict"):
            compile_card(
                self._card(
                    {
                        "op": "choose_mode",
                        "count": 1,
                        "or_more": True,
                        "up_to": True,
                        "modes": self._modes(3),
                    }
                )
            )

    def test_a_count_that_reaches_every_mode_is_a_load_error(self):
        """"Choose two or more" of two modes is "choose both", written long."""
        with pytest.raises(DslError, match="below the number of modes"):
            compile_card(
                self._card(
                    {
                        "op": "choose_mode",
                        "count": 2,
                        "or_more": True,
                        "modes": self._modes(2),
                    }
                )
            )
