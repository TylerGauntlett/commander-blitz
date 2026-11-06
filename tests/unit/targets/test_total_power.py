"""Reunion of the House -- "any number of target creature cards **with total
power 10 or less**".

    Return any number of target creature cards with total power 10 or less
    from your graveyard to the battlefield. Exile Reunion of the House.

A cap on the picks **together**, checked as the targets are chosen (601.2c):
every subset whose powers add up past the cap is never offered. No selector
clause can say it -- `power: {"op": "<=", "value": 10}` is evaluated one
candidate at a time and says "each of these has power 10 or less", a far wider
card that returns a graveyard of 6/6s at once. `t_each_ten` is exactly that
card.

`total_mana_value`'s sibling, in the same slot (`targeting._spec_options`) for
the same reason: a fact about a set of chosen objects rather than any one of
them.

**Which power.** A card in a graveyard has the power it has *in that zone*: the
printed number, with its own characteristic-defining ability applied, because
604.3 has a CDA function in every zone. `t_spf_counted` prints 0 and defines its
power as the number of creatures its owner controls; read as its printed 0 it
would let a 6/6 come back beside it on any board.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.targeting import enumerate_target_tuples
from tests.conftest import settle

REUNION = "t_reunion"
EACH = "t_each_ten"
DORK = "t_dork"  # 1/1
BEAR = "t_bear"  # 2/2
BIG = "t_big"  # 6/6
COUNTED = "t_spf_counted"  # 0/4 printed; power = creatures you control


def board(builder, buried=(BIG, BIG, BEAR, DORK), creatures=()):
    return (
        builder(players=2)
        .graveyard(0, list(buried))
        .battlefield(0, ["mountain"] * 2 + list(creatures))
        .hand(0, [REUNION])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )


def buried(game) -> list[int]:
    return list(game.state.players[0].graveyard)


def choices(game, card: str):
    """Every combination offered, as sorted tuples of card ids."""
    state = game.state
    spec = state.registry.get(card).targets
    return sorted(
        tuple(sorted(state.card(ref.id).id for ref in combo))
        for combo in enumerate_target_tuples(state, 0, spec, None)
    )


class TestTheCapIsOnThePicksTogether:
    def test_three_creatures_under_the_cap_are_offered(self, builder):
        """6 + 2 + 1 = 9."""
        assert (BEAR, BIG, DORK) in choices(board(builder), REUNION)

    def test_two_six_drops_are_not(self, builder):
        """6 + 6 = 12, and this is the whole clause."""
        offered = choices(board(builder), REUNION)
        assert (BIG, BIG) not in offered
        assert not any(combo.count(BIG) == 2 for combo in offered)

    def test_exactly_at_the_cap_is_offered(self, builder):
        """"Or less" includes ten: 6 + 2 + 2."""
        game = board(builder, buried=(BIG, BEAR, BEAR))
        assert (BEAR, BEAR, BIG) in choices(game, REUNION)

    def test_declining_is_still_offered(self, builder):
        assert () in choices(board(builder), REUNION)


class TestTheCounterfactual:
    def test_a_per_card_cap_offers_both_six_drops(self, builder):
        assert (BEAR, BIG, BIG, DORK) in choices(board(builder), EACH)


class TestTheCardsPowerInItsZone:
    """604.3: a characteristic-defining ability works in the graveyard too."""

    def test_the_cda_is_read_not_the_printed_zero(self, builder):
        """Five creatures on the battlefield: the card's power is 5, and 5 + 6
        is over the cap -- its printed 0 would have let the pair through."""
        game = board(builder, buried=(BIG, COUNTED), creatures=[BEAR] * 5)
        offered = choices(game, REUNION)
        assert (BIG, COUNTED) not in offered
        assert (COUNTED,) in offered

    def test_the_same_pair_fits_with_four(self, builder):
        game = board(builder, buried=(BIG, COUNTED), creatures=[BEAR] * 4)
        assert (BIG, COUNTED) in choices(game, REUNION)


class TestTheSpellResolves:
    def test_the_chosen_cards_come_back(self, builder):
        game = board(builder)
        big, other_big, bear, dork = buried(game)
        wanted = {big, bear, dork}
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == REUNION
            and {t.id for t in a.targets} == wanted
        )
        game.apply(cast)
        settle(game)
        assert wanted <= set(game.state.battlefield)
        assert other_big in buried(game)
        assert other_big not in game.state.battlefield

    def test_no_cast_line_carries_both_six_drops(self, builder):
        game = board(builder)
        bigs = set(buried(game)[:2])
        for action in game.legal_actions():
            if action.kind is ActionKind.CAST and action.targets:
                assert not bigs <= {t.id for t in action.targets}


def _spec(**overrides):
    target = {
        "id": "t1",
        "kind": "card_in_graveyard",
        "count": "any",
        "total_power": 10,
        "selector": {"zone": "graveyard", "types": ["Creature"]},
    }
    target.update(overrides)
    return CardModel.model_validate(
        {
            "id": "t_bad_total_power",
            "name": "Test Bad Total Power",
            "oracle_text": "Return them.",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "targets": [target],
            "spell_effects": [
                {
                    "op": "return_from_graveyard",
                    "destination": "battlefield",
                    "controller": "you",
                    "objects": {"target": "t1"},
                }
            ],
        }
    )


class TestTheLoaderChecksIt:
    def test_a_real_cap_loads(self):
        assert compile_card(_spec(), source="test").targets[0].total_power == 10

    def test_zero_is_a_real_cap(self):
        """A 0/1 Wall's card passes it."""
        compile_card(_spec(total_power=0), source="test")

    def test_a_negative_cap_is_refused(self):
        with pytest.raises(DslError, match="total_power"):
            compile_card(_spec(total_power=-1), source="test")

    def test_a_player_target_is_refused(self):
        with pytest.raises(DslError, match="does not have"):
            compile_card(
                _spec(kind="player", selector={"controller": "opponent"}), source="test"
            )
