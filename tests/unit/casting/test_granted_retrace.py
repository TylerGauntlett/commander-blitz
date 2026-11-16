"""Granted retrace: a land discard a permission hands to cards in your graveyard.

    Merfolk and Druid cards in your graveyard have retrace. (You may cast cards
    with retrace from your graveyard by discarding a land card in addition to
    paying their other costs.)                         -- Deeproot Historian

702.81a: retrace is a static ability that functions while the card is in a
graveyard, and means "you may cast this card from your graveyard by discarding
a land card as an additional cost to cast it". When another card grants the
ability, the covered card is castable from the graveyard **with that discard
only** -- the Historian is not an Edgar, and a Merfolk under it does not come
back for its mana cost alone. Without the rider, the permission the engine had
(`cast_from_graveyard`) would let it out at the printed cost and discard
nothing, which is a much stronger card than the printed one.

What the rider has to get right, each a class below:

- **The filter is the printed subtypes, either of them.** A Kindred instant
  that is a Merfolk is covered; a Bear is not; a land is never cast.
- **No per-turn cap.** The discarded lands are the brake; the Historian prints
  no limit and an invented one would be the approximation.
- **It goes where it normally would.** Retrace does not exile the spell (unlike
  flashback): an instant comes back to be retraced again, and the spell was
  cast from a graveyard.
- **Its own price, beside the others.** An Edgar-shaped permission over the
  same card is a second line at a second price, and a card whose own graveyard
  cost discards any card keeps that line beside the land-discard one.

Witness: Deeproot Historian (`t_historian`, its static on a test creature).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import settle_to_priority

HISTORIAN = "t_historian"
MERFOLK = "t_retrace_merfolk"  # {1}{G} Merfolk creature
DRUID = "t_retrace_druid"  # {G} Elf Druid creature
RITE = "t_retrace_rite"  # {G} Kindred instant -- Merfolk, gain 2 life
ROBOT = "t_retrace_dragon"  # {1}{G} Merfolk, "by discarding a card"
GOLEM = "t_retrace_golem"  # {2} Merfolk artifact creature
PRINTED = "t_retrace_printed"  # {G} Merfolk instant with its own retrace
EDGAR = "t_untapped_machinist"  # once a turn, an artifact spell from your graveyard
BEAR = "t_bear"  # {1}{G} Bear


def position(builder, *, graveyard, hand=("forest",), historian=True, extra=()):
    """Player 0 in their main phase with five Forests untapped and ``hand``."""
    battlefield = ["forest"] * 5 + list(extra)
    if historian:
        battlefield.append(HISTORIAN)
    return (
        builder(players=2)
        .battlefield(0, battlefield)
        .battlefield(1, ["plains"])
        .graveyard(0, list(graveyard))
        .hand(0, list(hand))
        .hand(1, ["forest"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def in_graveyard(game, card_id: str) -> int:
    (oid,) = [o for o in game.state.players[0].graveyard if game.state.objects[o].def_id == card_id]
    return oid


def casts(game, oid: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def hand_ids(game) -> list[str]:
    return sorted(game.state.objects[o].def_id for o in game.state.players[0].hand)


def retrace(game, oid: int) -> None:
    """Cast ``oid`` on its granted-retrace line and resolve it."""
    game.apply(next(a for a in casts(game, oid) if a.retrace))
    settle_to_priority(game)


class TestTheHistorianGrantsRetrace:
    def test_the_only_line_is_the_retrace_line(self, builder):
        game = position(builder, graveyard=[MERFOLK])
        lines = casts(game, in_graveyard(game, MERFOLK))
        assert [a.retrace for a in lines] == [True]
        assert lines[0].label.endswith("(retrace)")

    def test_without_the_historian_nothing_is_offered(self, builder):
        game = position(builder, graveyard=[MERFOLK], historian=False)
        assert casts(game, in_graveyard(game, MERFOLK)) == []

    def test_without_a_land_in_hand_nothing_is_offered(self, builder):
        game = position(builder, graveyard=[MERFOLK], hand=[BEAR])
        assert casts(game, in_graveyard(game, MERFOLK)) == []

    def test_casting_pays_the_mana_and_discards_the_land(self, builder):
        game = position(builder, graveyard=[MERFOLK], hand=["forest", BEAR])
        merfolk = in_graveyard(game, MERFOLK)
        retrace(game, merfolk)
        assert game.state.objects[merfolk].zone is Zone.BATTLEFIELD
        assert hand_ids(game) == [BEAR]
        assert [game.state.objects[o].def_id for o in game.state.players[0].graveyard] == [
            "forest"
        ]
        untapped = [
            o
            for o in game.state.battlefield_objects(0)
            if o.def_id == "forest" and not o.tapped
        ]
        assert len(untapped) == 3


class TestTheFilterIsEitherPrintedSubtype:
    @pytest.mark.parametrize("card_id", [MERFOLK, DRUID, RITE])
    def test_covered(self, builder, card_id):
        game = position(builder, graveyard=[card_id])
        assert [a.retrace for a in casts(game, in_graveyard(game, card_id))] == [True]

    def test_a_bear_is_not(self, builder):
        game = position(builder, graveyard=[BEAR])
        assert casts(game, in_graveyard(game, BEAR)) == []

    def test_an_opponents_merfolk_is_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 5 + [HISTORIAN])
            .graveyard(1, [MERFOLK])
            .hand(0, ["forest"])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        (merfolk,) = game.state.players[1].graveyard
        assert casts(game, merfolk) == []


class TestItGoesWhereItNormallyWould:
    def test_a_retraced_instant_returns_to_the_graveyard(self, builder):
        game = position(builder, graveyard=[RITE], hand=["forest", "forest"])
        rite = in_graveyard(game, RITE)
        life = game.state.players[0].life
        retrace(game, rite)
        obj = game.state.objects[rite]
        assert obj.zone is Zone.GRAVEYARD
        assert obj.cast_from_graveyard
        assert game.state.players[0].life == life + 2

    def test_no_per_turn_cap(self, builder):
        game = position(builder, graveyard=[RITE], hand=["forest", "forest"])
        rite = in_graveyard(game, RITE)
        life = game.state.players[0].life
        retrace(game, rite)
        retrace(game, rite)
        assert game.state.players[0].life == life + 4
        # No land left to discard: the brake, and the only one.
        assert hand_ids(game) == []
        assert casts(game, rite) == []


class TestItsOwnPriceBesideTheOthers:
    def test_beside_an_edgar_each_price_is_its_own_line(self, builder):
        game = position(builder, graveyard=[GOLEM], extra=[EDGAR])
        golem = in_graveyard(game, GOLEM)
        lines = casts(game, golem)
        assert sorted(a.retrace for a in lines) == [False, True]
        retrace(game, golem)
        assert game.state.objects[golem].zone is Zone.BATTLEFIELD
        assert hand_ids(game) == []

    def test_the_edgar_line_discards_nothing(self, builder):
        game = position(builder, graveyard=[GOLEM], extra=[EDGAR])
        golem = in_graveyard(game, GOLEM)
        game.apply(next(a for a in casts(game, golem) if not a.retrace))
        settle_to_priority(game)
        assert game.state.objects[golem].zone is Zone.BATTLEFIELD
        assert hand_ids(game) == ["forest"]

    def test_a_card_discard_of_its_own_stays_beside_it(self, builder):
        # Dragon Man's "discarding a card" is the card's own line; the
        # granted one charges a land, and both are offered.
        game = position(builder, graveyard=[ROBOT], hand=["forest", BEAR])
        robot = in_graveyard(game, ROBOT)
        assert sorted(a.retrace for a in casts(game, robot)) == [False, True]
        retrace(game, robot)
        assert hand_ids(game) == [BEAR]

    def test_printed_retrace_is_not_offered_twice(self, builder):
        # The same land discard at the same price: one line, the card's own.
        game = position(builder, graveyard=[PRINTED], hand=["forest", BEAR])
        printed = in_graveyard(game, PRINTED)
        assert [a.retrace for a in casts(game, printed)] == [False]
        game.apply(casts(game, printed)[0])
        settle_to_priority(game)
        assert hand_ids(game) == [BEAR]
        assert game.state.objects[printed].zone is Zone.GRAVEYARD


def _static(**fields):
    return {
        "id": "t_bad_historian",
        "name": "Bad Historian",
        "oracle_text": "",
        "mana_cost": "{4}{G}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": "x",
                "effect": "cast_from_graveyard",
                "affects_player": "you",
                "affects_spells": {"subtypes": ["Merfolk"]},
                "grants_retrace": True,
                **fields,
            }
        ],
    }


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "rider",
        [
            {"grants_flashback": True},
            {"pay_life_instead": True},
            {"escape": {"exile_from_graveyard": 3}},
        ],
    )
    def test_a_second_price(self, rider):
        with pytest.raises(DslError, match="second price"):
            compile_card(CardModel.model_validate(_static(**rider)))

    def test_retrace_on_another_static(self):
        card = _static()
        card["abilities"][0]["effect"] = "cast_from_library_top"
        with pytest.raises(DslError, match="grants_retrace"):
            compile_card(CardModel.model_validate(card))

    def test_on_a_cards_own_permission(self):
        card = _static()
        del card["abilities"][0]["affects_spells"]
        card["abilities"][0]["active_zones"] = ["graveyard"]
        with pytest.raises(DslError, match="grants_retrace"):
            compile_card(CardModel.model_validate(card))

    def test_without_a_cap_it_is_accepted(self):
        compiled = compile_card(CardModel.model_validate(_static()))
        static = compiled.abilities[0].static
        assert static["grants_retrace"] is True
        assert static["max_per_turn"] is None
