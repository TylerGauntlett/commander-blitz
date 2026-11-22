"""Casting from the graveyard at the printed price plus any additional cost.

    Dragon Man, Reformed Robot -- "You may cast this card from your graveyard
    by discarding a card in addition to paying its other costs."

Retrace (702.81a) with the card's own cost: 601.2b lets the card be cast from
the graveyard, 601.2f adds the discard to the printed mana cost, and 601.2g
pays it after the mana. `graveyard_additional_cost` compiles onto retrace's
slot (`CardDef.retrace` and `retrace_cost`), so the line, the payment and the
"no cost, no line" rule are retrace's. Two near misses would load: retrace
itself refuses a nonland discard the card allows, and `graveyard_cost` is an
*alternative* cost that replaces the mana -- a different cast, which no other
alternative cost could join. Retrace stays exact: its default cost is still a
land card (`test_retrace.py`).

    Helbrute -- "Sarcophagus — You may cast this card from your graveyard by
    exiling another creature card from your graveyard in addition to paying
    its other costs."

The same slot with an `exile_from_graveyard` cost. The residual gate reads the
printed payment into the one `Cost` it means and claims the line only when that
is the cost charged: a claim that matched the wording alone would let a card
exiling any card wear a line that demands a creature card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.verify import claimed_lines
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

ROBOT = "t_gac_robot"  # {2}{U} 2/2; from the graveyard by discarding a card


def board(builder, hand: list[str], *, lands: int = 3):
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * lands)
        .hand(0, hand)
        .graveyard(0, [ROBOT])
        .library(0, ["island"] * 20)
        .build()
    )
    return game


def cast_line(game):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == ROBOT
        ),
        None,
    )


def settle(game):
    for _ in range(200):
        decision = game.pending()
        if decision is None or (decision.kind is DecisionKind.PRIORITY and not game.state.stack):
            return
        game.apply(_default_answer(game, decision))


class TestTheLine:
    def test_any_card_in_hand_offers_it(self, builder):
        assert cast_line(board(builder, ["grizzly_bears"])) is not None

    def test_a_land_will_do_too(self, builder):
        assert cast_line(board(builder, ["island"])) is not None

    def test_an_empty_hand_does_not(self, builder):
        assert cast_line(board(builder, [])) is None

    def test_the_mana_is_still_owed(self, builder):
        assert cast_line(board(builder, ["grizzly_bears"], lands=2)) is None


class TestThePayment:
    def test_it_takes_the_card_and_the_mana_and_enters(self, builder):
        game = board(builder, ["grizzly_bears"])
        robot = cast_line(game).source
        game.apply(cast_line(game))
        settle(game)

        assert game.state.players[0].hand == []
        assert any(
            game.state.objects[oid].def_id == "grizzly_bears"
            for oid in game.state.players[0].graveyard
        ), "the discarded card"
        assert sum(1 for o in game.state.battlefield_objects(0) if o.tapped) == 3
        assert game.state.objects[robot].zone is Zone.BATTLEFIELD


class TestTheLoader:
    def _card(self, **extra) -> CardModel:
        card = {
            "id": "t_gac_probe",
            "name": "Graveyard Probe",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "graveyard_additional_cost": {"discard": 1},
        }
        card.update(extra)
        return CardModel.model_validate(card)

    def test_it_is_retraces_slot(self):
        card = compile_card(self._card())
        assert card.retrace and card.retrace_cost == Cost(discard=1)

    def test_retrace_keeps_its_land(self):
        card = compile_card(self._card(graveyard_additional_cost=None, retrace=True))
        assert card.retrace_cost == Cost(discard=1, discard_selector={"types": ["Land"]})

    def test_beside_retrace_it_is_refused(self):
        with pytest.raises(DslError, match="retrace"):
            compile_card(self._card(retrace=True))

    def test_beside_a_graveyard_cost_it_is_refused(self):
        with pytest.raises(DslError, match="graveyard"):
            compile_card(self._card(graveyard_cost={"mana": "{2}"}))

    def test_a_free_cost_is_refused(self):
        with pytest.raises(DslError, match="graveyard_additional_cost"):
            compile_card(self._card(graveyard_additional_cost={}))


class TestTheResidualGate:
    LINE = (
        "You may cast this card from your graveyard by discarding a card in "
        "addition to paying its other costs."
    )

    def test_the_printed_discard_is_claimed(self, registry):
        card = registry.get(ROBOT)
        assert self.LINE in claimed_lines(card, self.LINE)

    def test_a_land_discard_cannot_claim_any_card(self):
        card = compile_card(
            CardModel.model_validate(
                {
                    "id": "t_gac_land",
                    "name": "Land Probe",
                    "mana_cost": "{1}",
                    "types": ["Artifact"],
                    "retrace": True,
                }
            )
        )
        assert self.LINE not in claimed_lines(card, self.LINE)


BRUTE = "t_gac_brute"  # {2}{B} 2/2; from the graveyard by exiling another creature card
SARCOPHAGUS = (
    "Sarcophagus — You may cast this card from your graveyard by exiling another "
    "creature card from your graveyard in addition to paying its other costs."
)


def brute_board(builder, graveyard: list[str]):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 3)
        .graveyard(0, [BRUTE, *graveyard])
        .library(0, ["swamp"] * 20)
        .build()
    )


def brute_line(game):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BRUTE
        ),
        None,
    )


class TestTheExileCost:
    def test_another_creature_card_offers_it(self, builder):
        assert brute_line(brute_board(builder, ["grizzly_bears"])) is not None

    def test_the_card_itself_does_not_count(self, builder):
        assert brute_line(brute_board(builder, [])) is None

    def test_a_noncreature_card_does_not(self, builder):
        assert brute_line(brute_board(builder, ["island"])) is None

    def test_it_exiles_the_other_card_and_enters(self, builder):
        game = brute_board(builder, ["grizzly_bears"])
        brute = brute_line(game).source
        game.apply(brute_line(game))
        settle(game)

        assert game.state.objects[brute].zone is Zone.BATTLEFIELD
        exiled = [o.def_id for o in game.state.objects.values() if o.zone is Zone.EXILE]
        assert exiled == ["grizzly_bears"]

    def test_the_payment_never_offers_the_card_itself(self, builder):
        # Legality priced "another" with the card as the cost's source; the
        # payment has to as well, or the card could exile itself and resolve.
        game = brute_board(builder, ["grizzly_bears", "grizzly_bears"])
        brute = brute_line(game).source
        game.apply(brute_line(game))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        offered = {ref.id for a in game.legal_actions() for ref in a.targets}
        assert offered and brute not in offered


def _probe(cost: dict):
    return compile_card(
        CardModel.model_validate(
            {
                "id": "t_gac_exile_probe",
                "name": "Exile Probe",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "graveyard_additional_cost": cost,
            }
        )
    )


class TestTheExileClaim:
    def test_the_printed_exile_is_claimed(self, registry):
        assert SARCOPHAGUS in claimed_lines(registry.get(BRUTE), SARCOPHAGUS)

    def test_the_defaults_are_the_same_payment(self):
        card = _probe({"exile_from_graveyard": {"types": ["Creature"], "exclude_self": True}})
        assert SARCOPHAGUS in claimed_lines(card, SARCOPHAGUS)

    def test_an_exile_of_any_card_cannot_claim_a_creature_card(self):
        card = _probe({"exile_from_graveyard": {"count": 1, "exclude_self": True}})
        assert SARCOPHAGUS not in claimed_lines(card, SARCOPHAGUS)

    def test_two_cards_cannot_claim_one(self):
        card = _probe(
            {"exile_from_graveyard": {"count": 2, "types": ["Creature"], "exclude_self": True}}
        )
        assert SARCOPHAGUS not in claimed_lines(card, SARCOPHAGUS)

    def test_a_discard_cannot_claim_the_exile(self):
        assert SARCOPHAGUS not in claimed_lines(_probe({"discard": 1}), SARCOPHAGUS)

    def test_the_exile_cannot_claim_a_discard(self, registry):
        line = TestTheResidualGate.LINE
        assert line not in claimed_lines(registry.get(BRUTE), line)
