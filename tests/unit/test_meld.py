"""Meld — mutate's merged permanent with the pair fixed by the card.

    "At the beginning of your end step, if you both own and control Test Bruna
    and Test Gisela, exile them, then meld them into Test Brisela." (701.37)

Meld was one of five `refused` rows, filed as needing "a card-wide designated
state the engine has no place to keep". By the time mutate shipped, the engine
had the place: a permanent whose identity is a **synthesised `CardDef`** read
through `card_of`, with the other card recorded in `merged_under` so
`zones.move_object` sends the pair wherever it goes.

Meld is that mechanism with two things changed, and both are simplifications:

| | mutate | meld |
|---|---|---|
| which two cards | the caster targets one | fixed by the card (`melds_with`) |
| what the result is | the top card plus the abilities under it | a **third** card entry (`melds_into`) |

The one place it is genuinely *harder* is that meld makes a **new** permanent.
701.37c exiles both cards and returns them melded, so the melded permanent
enters the battlefield: its enter triggers fire and it is summoning sick. That
is why this exiles and re-enters rather than writing the identity onto a
permanent already standing, which is what mutate does.

The "if you both own and control" clause is not implemented here at all — it is
the card's own intervening-if `condition`, checked twice by `triggers` as rule
603.4 requires. A third check inside the effect would be a different rule
wearing the same words.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import Keyword, Zone
from automtg.engine.zones import destroy
from tests.conftest import only_oid

PLAINS = "plains"
BRUNA = "t_meld_a"        # 5/7 flier, carries the meld trigger
GISELA = "t_meld_b"       # 4/6 first striker, the partner
BRISELA = "t_meld_result"  # 9/10 legendary, all three keywords


def position(builder, *, partner: bool = True):
    board = [BRUNA] + ([GISELA] if partner else [])
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * 4)
        .battlefield(0, board)
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build(advance=False)
    )
    return game, only_oid(game, BRUNA)


def meld(game, bruna: int):
    """Run the meld op directly — the trigger's timing is not what is under test."""
    from automtg.engine.effects.context import EffectContext
    from automtg.engine.effects.ops_counters import op_meld

    ctx = EffectContext(state=game.state, controller=0, source_oid=bruna)
    list(op_meld(ctx, {"op": "meld"}))


class TestTheMeldedPermanent:
    def test_it_is_the_third_card(self, builder):
        game, bruna = position(builder)
        meld(game, bruna)

        assert game.state.card_of(game.state.objects[bruna]).id == BRISELA

    def test_it_has_that_cards_body(self, builder):
        game, bruna = position(builder)
        meld(game, bruna)

        c = chars(game.state, bruna)
        assert (c.power, c.toughness) == (9, 10)
        assert "Legendary" in c.supertypes

    def test_it_has_that_cards_keywords_and_not_the_halves(self, builder):
        """The result is a printed card, not a union: `melds_into` says it all."""
        game, bruna = position(builder)
        meld(game, bruna)

        c = chars(game.state, bruna)
        assert {Keyword.FLYING.value, Keyword.FIRST_STRIKE.value, Keyword.VIGILANCE.value} <= c.keywords

    def test_there_is_one_permanent(self, builder):
        game, bruna = position(builder)
        gisela = only_oid(game, GISELA)
        meld(game, bruna)

        assert bruna in game.state.battlefield
        assert gisela not in game.state.battlefield
        assert game.state.objects[gisela].merged_into == bruna


class TestItsManaValue:
    """The total of its front faces' -- the Brisela ruling: "Brisela's mana value is 11".

    The melded card prints no mana cost, so read off the pool entry it would be
    0, and every "mana value N or less" removal spell would reach a 9/10.
    """

    def test_it_is_the_sum_of_the_halves(self, builder):
        game, bruna = position(builder)
        meld(game, bruna)

        # Test Bruna {5}{W}{W} is 7, Test Gisela {4}{W}{W} is 6.
        assert game.state.card_of(game.state.objects[bruna]).mana_value == 13

    def test_it_prints_no_mana_cost_all_the_same(self, builder):
        game, bruna = position(builder)
        meld(game, bruna)

        melded = game.state.card_of(game.state.objects[bruna])
        assert melded.mana_cost == game.state.registry.get(BRISELA).mana_cost

    def test_the_pool_entry_is_untouched(self, builder):
        """Synthesised per permanent, the way mutate's merged card is."""
        game, bruna = position(builder)
        meld(game, bruna)

        assert game.state.registry.get(BRISELA).mana_value == 0

    def test_apart_again_each_half_has_its_own(self, builder):
        game, bruna = position(builder)
        gisela = only_oid(game, GISELA)
        meld(game, bruna)
        destroy(game.state, bruna)

        assert game.state.card_of(game.state.objects[bruna]).mana_value == 7
        assert game.state.card_of(game.state.objects[gisela]).mana_value == 6


class TestItIsANewPermanent:
    def test_it_entered_this_turn(self, builder):
        """701.37c exiles both and returns them melded, so it *enters*."""
        game, bruna = position(builder)
        meld(game, bruna)

        assert game.state.objects[bruna].entered_turn == game.state.turn

    def test_the_zone_change_is_in_the_log(self, builder):
        game, bruna = position(builder)
        before = len(game.state.events)
        meld(game, bruna)

        moves = [
            e
            for e in game.state.events[before:]
            if e.type == "zone_change" and e.data.get("to") == "exile"
        ]
        assert len(moves) == 2, "both cards were exiled"

    def test_neither_card_is_left_in_exile(self, builder):
        game, bruna = position(builder)
        gisela = only_oid(game, GISELA)
        meld(game, bruna)

        assert game.state.players[0].exile == []
        assert game.state.objects[gisela].zone is Zone.BATTLEFIELD


class TestWithoutThePartner:
    def test_nothing_happens(self, builder):
        game, bruna = position(builder, partner=False)
        meld(game, bruna)

        assert game.state.card_of(game.state.objects[bruna]).id == BRUNA
        assert game.state.objects[bruna].merged_card is None

    def test_a_partner_someone_else_controls_does_not_count(self, builder):
        """"if you both **own and control**" -- and this checks the engine half."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 4)
            .battlefield(0, [BRUNA])
            .battlefield(1, [GISELA])
            .library(0, [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build(advance=False)
        )
        bruna = only_oid(game, BRUNA)
        meld(game, bruna)

        assert game.state.objects[bruna].merged_card is None


class TestComingApart:
    def test_both_cards_go_to_the_graveyard(self, builder):
        game, bruna = position(builder)
        gisela = only_oid(game, GISELA)
        meld(game, bruna)

        destroy(game.state, bruna)

        assert game.state.objects[bruna].zone is Zone.GRAVEYARD
        assert game.state.objects[gisela].zone is Zone.GRAVEYARD
        assert set(game.state.players[0].graveyard) == {bruna, gisela}

    def test_and_each_is_itself_again(self, builder):
        game, bruna = position(builder)
        gisela = only_oid(game, GISELA)
        meld(game, bruna)

        destroy(game.state, bruna)

        assert game.state.card_of(game.state.objects[bruna]).id == BRUNA
        assert game.state.card_of(game.state.objects[gisela]).id == GISELA


class TestTheGuards:
    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_meld_probe",
            "name": "Meld Probe",
            "mana_cost": "{5}{W}",
            "types": ["Creature"],
            "power": 5,
            "toughness": 5,
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_both_halves_of_the_pair_load(self):
        compile_card(self._card(melds_with="t_meld_b", melds_into="t_meld_result"))

    def test_a_partner_with_no_result_is_refused(self):
        with pytest.raises(DslError, match="come as a pair"):
            compile_card(self._card(melds_with="t_meld_b"))

    def test_a_result_with_no_partner_is_refused(self):
        with pytest.raises(DslError, match="come as a pair"):
            compile_card(self._card(melds_into="t_meld_result"))

    def test_the_melded_card_may_not_be_in_a_deck(self):
        """`parent_face`, the same back-link a back face and a second face use."""
        from pathlib import Path

        from automtg.cards.registry import CardRegistry, authored_card_paths

        registry = CardRegistry.from_paths(
            authored_card_paths(Path("data/cards"))
            + sorted(Path("tests/data").glob("*.cards.json"))
        )
        assert registry.get(BRISELA).parent_face == BRUNA
