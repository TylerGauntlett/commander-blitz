""""One or two" targets owned by one mode -- 601.2b, 601.2c and 115.1.

    Yuna's Decision -- "Choose one --
    * Continue the Pilgrimage -- Sacrifice a creature. If you do, draw a card,
      then you may put a creature card and/or a land card from your hand onto
      the battlefield.
    * Find Another Way -- Return **one or two** target permanent cards from
      your graveyard to your hand."

The caster picks how many targets the second bullet has, from one through two
(601.2c), and only once that bullet is chosen (601.2b). Each nearer spelling is
a different card:

* a fixed ``count: 2`` mode target strikes the bullet whenever the graveyard
  holds one permanent card, and forbids returning just one when it holds more;
* a card-level ``up_to`` target is declared, and needs a legal choice, even
  when the caster takes the targetless first bullet.

The hazard is the one `optional` mode targets have: `filter_legal` splits the
stored refs spec by spec, and a caster-sized spec stores as many as were
picked. So the loader admits one only where it ends every declaration -- the
last spec of its mode, no later mode owning a target -- and these tests pin
that boundary (see also `TestTheLoaderRefusals` in test_modal_targets.py and
test_modal_triggered_targets.py) and the behaviour it buys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card

RECALL = "t_one_or_two_find"
DRAW = "Draw a card."
RETURN = "Return one or two target permanent cards from your graveyard to your hand."


def board(builder, graveyard: tuple[str, ...]):
    """Test Find Another Way in player 0's hand with ``graveyard`` in theirs.

    Returns ``(game, graveyard_oids)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 2)
        .hand(0, [RECALL])
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .build()
    )
    return game, list(game.state.players[0].graveyard)


def choose(game, label: str) -> None:
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.label == label)
    )


def pick_targets(game, oids: list[int]) -> None:
    """Answer the mode's target question with ``oids``, then finish if asked.

    One candidate under a floor of one is taken unasked, so nothing is pending.
    """
    if game.pending().kind is not DecisionKind.CHOOSE_OBJECTS:
        return
    for oid in oids:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.targets and a.targets[0].id == oid
            )
        )
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )


def resolve(game) -> None:
    for _ in range(20):
        if not game.state.stack:
            return
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    raise AssertionError("the spell never resolved")


def hand_ids(game) -> list[int]:
    return list(game.state.players[0].hand)


def cast(game) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, RECALL))


class TestTheCasterPicksTheSize:
    def test_the_question_runs_from_one_to_two(self, builder):
        game, _ = board(builder, ("t_bear", "t_bear", "forest"))
        cast(game)
        assert [o.label for o in game.pending().options] == [DRAW, RETURN]
        choose(game, RETURN)
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert (decision.min_count, decision.max_count) == (1, 2)
        assert len(decision.options) == 3

    @pytest.mark.parametrize("picked", [1, 2])
    def test_every_picked_card_comes_back(self, builder, picked):
        game, grave = board(builder, ("t_bear", "t_bear", "forest"))
        cast(game)
        choose(game, RETURN)
        pick_targets(game, grave[:picked])
        resolve(game)
        assert set(grave[:picked]) <= set(hand_ids(game))
        assert set(grave[picked:]) <= set(game.state.players[0].graveyard)

    def test_one_permanent_card_is_enough_for_the_bullet(self, builder):
        """A fixed ``count: 2`` would strike the bullet here."""
        game, (only,) = board(builder, ("t_bear",))
        cast(game)
        assert [o.label for o in game.pending().options] == [DRAW, RETURN]
        choose(game, RETURN)
        pick_targets(game, [only])
        resolve(game)
        assert only in hand_ids(game)


class TestTheTargetlessMode:
    def test_with_no_permanent_card_the_draw_is_still_castable(self, builder):
        """601.2b: below the floor the bullet cannot be chosen, so the draw is
        the only mode and is taken unasked -- where a card-level target with no
        legal choice would make the card uncastable."""
        game, _ = board(builder, ())
        library = len(game.state.players[0].library)
        cast(game)
        resolve(game)
        assert len(game.state.players[0].library) == library - 1
        assert [game.state.objects[o].def_id for o in game.state.players[0].graveyard] == [
            RECALL
        ]

    def test_the_draw_declares_no_target(self, builder):
        game, grave = board(builder, ("t_bear",))
        library = len(game.state.players[0].library)
        cast(game)
        choose(game, DRAW)
        resolve(game)
        assert len(game.state.players[0].library) == library - 1
        assert grave[0] in game.state.players[0].graveyard


class TestTheLoaderBoundary:
    def compile(self, card):
        compile_card(CardModel.model_validate(card))

    def test_the_last_target_declared_loads(self):
        self.compile(json_card(RECALL))

    def test_not_last_when_a_later_mode_owns_a_target(self):
        card = json_card(RECALL)
        card["targets"][0]["mode"] = 0
        card["targets"].append(
            {
                "id": "later",
                "kind": "card_in_graveyard",
                "mode": 1,
                "selector": {"zone": "graveyard", "controller": "you"},
            }
        )
        modes = card["spell_effects"][0]["modes"]
        modes[0]["effects"], modes[1]["effects"] = (
            modes[1]["effects"],
            [{"op": "return_from_graveyard", "destination": "hand",
              "objects": {"target": "later"}}],
        )
        with pytest.raises(DslError, match="must be the last target declared"):
            self.compile(card)

    def test_a_cross_pick_rule_is_refused(self):
        card = json_card(RECALL)
        card["targets"][0]["total_mana_value"] = 4
        with pytest.raises(DslError, match="total_mana_value"):
            self.compile(card)


def json_card(card_id: str) -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "variable_mode_target.cards.json"
    cards = json.loads(path.read_text(encoding="utf-8"))["cards"]
    return next(card for card in cards if card["id"] == card_id)
