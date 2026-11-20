"""A graveyard alternative cost that sacrifices: "by paying {B}{B} and sacrificing two creatures".

    Flying
    You may cast this creature from your graveyard by paying {B}{B} and
    sacrificing two creatures rather than paying its mana cost.

118.9: the whole of "{B}{B} and sacrificing two creatures" is one alternative
cost, and 601.2b-f make it the price of a cast from the graveyard; 601.2h pays
the sacrifice with the mana, so both halves are owed or the cast is not
offered. It is Raffine's Guidance's slot (`graveyard_cost` with
`"graveyard_cast": "graveyard"`) with a `sacrifice` beside the mana, and the
general payer charges it: without the sacrifice the card is a 6/6 flier
returned for two mana, a far cheaper card than the printed one. The card goes
where it normally would, so Scourge of Nel Toth that dies is back in the
graveyard to be cast again. From the hand it costs its {5}{B}{B} and nothing
is sacrificed.

Gate 3's claimant read only a mana-only payment and failed this line closed.
It reads the sacrifice clause against `cost.sacrifice` in both directions: the
printed count word must be the declared count and the printed noun the
declared type, and a sacrifice the line does not print, or a selector it does
not state, fails closed.

Witness: Scourge of Nel Toth, whose test twin is `t_scourge_of_nel_toth`.
"""

from __future__ import annotations

from commanderblitz.cards.authoring.verify import residual_text
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.zones import destroy
from tests.conftest import _default_answer

SCOURGE = "t_scourge_of_nel_toth"  # {5}{B}{B} 6/6 flier; {B}{B} + two creatures from the graveyard
LINE = (
    "You may cast this creature from your graveyard by paying {B}{B} and "
    "sacrificing two creatures rather than paying its mana cost."
)


def board(builder, *, where: str = "graveyard", bears: int = 3, swamps: int = 2):
    """Player 0 with the Scourge in ``where``, ``bears`` creatures and ``swamps``."""
    b = builder(players=2)
    b = b.graveyard(0, [SCOURGE]) if where == "graveyard" else b.hand(0, [SCOURGE])
    game = (
        b.battlefield(0, ["t_bear"] * bears + ["swamp"] * swamps)
        .library(0, ["swamp"] * 30)
        .library(1, ["swamp"] * 30)
        .build()
    )
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == SCOURGE]
    return game, oid


def casts(game, oid: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def cast(game, oid: int) -> None:
    """Cast the Scourge by its one offered line, pay, and resolve it."""
    (action,) = casts(game, oid)
    game.apply(action)
    for _ in range(50):
        decision = game.pending()
        if decision is None or (decision.kind is DecisionKind.PRIORITY and not game.state.stack):
            return
        game.apply(_default_answer(game, decision))


def bears_on_battlefield(game) -> int:
    return sum(1 for o in game.state.battlefield_objects(0) if o.def_id == "t_bear")


def untapped_swamps(game) -> int:
    return sum(
        1 for o in game.state.battlefield_objects(0) if o.def_id == "swamp" and not o.tapped
    )


class TestTheGraveyardCastChargesBothHalves:
    def test_it_is_offered_once_from_the_graveyard(self, builder):
        game, oid = board(builder)
        (action,) = casts(game, oid)
        assert action.flashback

    def test_it_sacrifices_two_creatures_and_pays_black_black(self, builder):
        game, oid = board(builder)
        cast(game, oid)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert bears_on_battlefield(game) == 1
        bears_in_yard = [
            o for o in game.state.players[0].graveyard if game.state.objects[o].def_id == "t_bear"
        ]
        assert len(bears_in_yard) == 2
        assert untapped_swamps(game) == 0

    def test_one_creature_is_not_enough(self, builder):
        # The boundary: the sacrifice is owed in full, or there is no cast.
        game, oid = board(builder, bears=1)
        assert casts(game, oid) == []

    def test_the_mana_is_still_owed(self, builder):
        game, oid = board(builder, swamps=1)
        assert casts(game, oid) == []


class TestItIsNotExiled:
    def test_when_it_dies_it_returns_to_the_graveyard(self, builder):
        game, oid = board(builder)
        cast(game, oid)
        destroy(game.state, oid)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert game.state.players[0].exile == []


class TestTheHandCastIsUnchanged:
    def test_from_the_hand_it_costs_its_mana_cost_and_sacrifices_nothing(self, builder):
        game, oid = board(builder, where="hand", swamps=7)
        (action,) = casts(game, oid)
        assert not action.flashback
        cast(game, oid)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert bears_on_battlefield(game) == 3
        assert untapped_swamps(game) == 0

    def test_two_black_alone_does_not_cast_it_from_the_hand(self, builder):
        game, oid = board(builder, where="hand")
        assert casts(game, oid) == []


TWO_CREATURES = {"types": ["Creature"], "controller": "you", "zone": "battlefield", "count": 2}


class TestThePrintedLineIsClaimed:
    """Gate 3's bookkeeping, where a correct card used to die."""

    def _residual(self, **extra) -> str:
        base = {
            "id": "t_graveyard_sacrifice_residual",
            "name": "Graveyard Sacrifice Residual",
            "mana_cost": "{5}{B}{B}",
            "oracle_text": f"Flying\n{LINE}",
            "types": ["Creature"],
            "power": 6,
            "toughness": 6,
            "keywords": ["flying"],
            "graveyard_cost": {"mana": "{B}{B}", "sacrifice": TWO_CREATURES},
            "graveyard_cast": "graveyard",
        }
        base.update(extra)
        card = compile_card(CardModel.model_validate(base))
        return residual_text(card, card.oracle_text)

    def _line(self, clause: str) -> str:
        return LINE.replace("sacrificing two creatures", clause)

    def test_the_exact_card_is_claimed(self):
        assert self._residual() == ""

    def test_the_selector_defaults_are_the_same_sacrifice(self):
        bare = {"mana": "{B}{B}", "sacrifice": {"types": ["Creature"], "count": 2}}
        assert self._residual(graveyard_cost=bare) == ""

    def test_a_single_sacrifice_reads_its_article(self):
        one = {"mana": "{B}{B}", "sacrifice": {"types": ["Creature"], "count": 1}}
        line = self._line("sacrificing a creature")
        assert self._residual(graveyard_cost=one, oracle_text=line) == ""

    def test_a_missing_sacrifice_cannot_claim_it(self):
        assert "graveyard" in self._residual(graveyard_cost={"mana": "{B}{B}"})

    def test_fewer_sacrifices_cannot_claim_two(self):
        one = {"mana": "{B}{B}", "sacrifice": {**TWO_CREATURES, "count": 1}}
        assert "graveyard" in self._residual(graveyard_cost=one)

    def test_another_type_cannot_claim_creatures(self):
        artifacts = {"mana": "{B}{B}", "sacrifice": {**TWO_CREATURES, "types": ["Artifact"]}}
        assert "graveyard" in self._residual(graveyard_cost=artifacts)

    def test_a_cheaper_mana_price_cannot_claim_it(self):
        cheaper = {"mana": "{B}", "sacrifice": TWO_CREATURES}
        assert "graveyard" in self._residual(graveyard_cost=cheaper)

    def test_a_narrower_printed_noun_is_not_read(self):
        for clause in (
            "sacrificing two other creatures",
            "sacrificing two creature tokens",
            "sacrificing two nonblack creatures",
        ):
            assert "graveyard" in self._residual(oracle_text=self._line(clause)), clause

    def test_a_narrower_selector_cannot_claim_the_bare_noun(self):
        tokens = {"mana": "{B}{B}", "sacrifice": {**TWO_CREATURES, "token": True}}
        assert "graveyard" in self._residual(graveyard_cost=tokens)

    def test_an_opponents_creatures_are_not_sacrificing(self):
        theirs = {"mana": "{B}{B}", "sacrifice": {**TWO_CREATURES, "controller": "opponent"}}
        assert "graveyard" in self._residual(graveyard_cost=theirs)

    def test_another_payment_beside_it_fails_closed(self):
        dearer = {"mana": "{B}{B}", "sacrifice": TWO_CREATURES, "pay_life": 2}
        assert "graveyard" in self._residual(graveyard_cost=dearer)

    def test_the_exile_destination_cannot_claim_it(self):
        assert "graveyard" in self._residual(graveyard_cast="exile")
