"""Call Damage Control: "Choose up to two --", with no floor.

Three spellings of a modal count existed and none of them said it. `count` is
exact, so "choose up to two" written as `count: 2` becomes "choose two" and the
word "up to" is silently deleted. `all_if` is entwine and forces *every* mode.
`up_to_if` is Akroma's Will — a ceiling, but it needs a `condition` and still
keeps a floor of one.

Taking **none** is a real line on these cards, which is why the floor matters
rather than being a technicality: Call Damage Control returns cards from a
graveyard, and cast with an empty graveyard every mode is dead. A floor of one
would force a mode that does nothing and read on screen as a fizzle.

The name is `TargetSpec`'s, where `up_to` has meant exactly this since "up to X
target creatures" — one word for one idea, rather than a second spelling of it.

Both copies of the modal question are covered here. A spell whose whole effect
tree is one top-level `choose_mode` is answered at cast time by
`Game._ask_modes` (601.2b) and never reaches `op_choose_mode` at all — the trap
that made `up_to_if` dead code for the card it was built for.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind
from tests.conftest import _default_answer, action_for_card

SPELL = "t_choose_up_to_two"  # gain 3 life / draw a card / lose 1 life


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .hand(0, [SPELL])
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_and_choose(game, picks):
    """Cast the spell and take the modes at indices `picks` (possibly none)."""
    game.apply(action_for_card(game, ActionKind.CAST, SPELL))
    decision = None
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.CHOOSE_MODE:
            for want in picks:
                # Deliberately tolerant: once the ceiling is reached the engine
                # stops offering CHOOSE at all, which is how
                # `test_a_third_mode_cannot_be_taken` observes the bound.
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
    """Cast the spell and hand back the modal decision itself."""
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
    def test_the_floor_is_zero_and_the_ceiling_is_the_count(self, builder):
        decision = mode_decision(board(builder))
        assert decision.min_count == 0, "'up to' means taking none is legal"
        assert decision.max_count == 2, "…and two is the most"

    def test_every_mode_is_offered(self, builder):
        decision = mode_decision(board(builder))
        assert len(decision.options) == 3


class TestTakingThem:
    def test_two_modes_both_happen(self, builder):
        game = board(builder)
        life, cards = game.state.players[0].life, len(game.state.players[0].hand)
        cast_and_choose(game, [0, 1])
        assert game.state.players[0].life == life + 3
        assert len(game.state.players[0].hand) == cards  # spell left, card drawn

    def test_one_mode_is_allowed(self, builder):
        game = board(builder)
        life = game.state.players[0].life
        cast_and_choose(game, [0])
        assert game.state.players[0].life == life + 3

    def test_none_at_all_is_allowed(self, builder):
        """The whole reason the floor matters. Nothing happens, and that is legal."""
        game = board(builder)
        life, library = (
            game.state.players[0].life,
            len(game.state.players[0].library),
        )
        cast_and_choose(game, [])
        assert game.state.players[0].life == life, "no mode was taken"
        assert len(game.state.players[0].library) == library

    def test_a_third_mode_cannot_be_taken(self, builder):
        """The ceiling is real: two is the most, out of three."""
        game = board(builder)
        life = game.state.players[0].life
        cast_and_choose(game, [0, 1, 2])
        # Only the first two were legal to take, so the life loss never ran.
        assert game.state.players[0].life == life + 3


class TestTheLoaderRefusesNonsense:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_up_to",
                "name": "Bad Up To",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Sorcery"],
                "colors": ["W"],
                "color_identity": ["W"],
                "spell_effects": [effect],
            }
        )

    def test_up_to_on_another_op_is_a_load_error(self):
        with pytest.raises(DslError, match="up_to"):
            compile_card(
                self._card({"op": "draw", "amount": {"const": 1}, "up_to": True})
            )

    def test_up_to_zero_is_a_load_error(self):
        """A card that may choose up to nothing is a card that does nothing."""
        with pytest.raises(DslError, match="count"):
            compile_card(
                self._card(
                    {
                        "op": "choose_mode",
                        "count": 0,
                        "up_to": True,
                        "modes": [
                            {"label": "A", "effects": [{"op": "noop"}]},
                            {"label": "B", "effects": [{"op": "noop"}]},
                        ],
                    }
                )
            )
