"""`from_zone` on `free_cast_permission`: "from your hand" is a real limit.

    Tamiyo, Field Researcher — "-7: … You get an emblem with 'You may cast
    spells from your hand without paying their mana costs.'"

`free_cast_permission` is asked by every cast lane -- hand, command zone,
graveyard and exile permissions -- so written without a zone the emblem would
also cast a commander and every flashback-style spell for free, a strictly
better card than the one printed. `from_zone: "hand"` in its `affects_spells`
restricts the free line to spells cast from their caster's hand, with the zone
handed in by the cast-line builder.

The claims: a spell in hand gets the free line; the same spell cast from any
other zone does not; a caller that names no zone is refused (fails closed); and
the unrestricted form (Dracogenesis) still frees every zone, as before.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.player_statics import free_cast_permission

HOLDER = "t_hand_omniscience"
WYRM = "t_cinder_wyrm"  # {4}{R}{R} Dragon 4/4
AMNESTY = "t_dragon_amnesty"  # "You may cast Dragon spells without paying their mana costs."


def board(builder, permission=HOLDER, hand=(WYRM,)):
    return (
        builder(players=2)
        .battlefield(0, [permission])
        .hand(0, list(hand))
        .library(0, ["forest"] * 10)
        .build()
    )


def wyrm_card(game):
    return game.state.card_of(
        next(game.state.objects[o] for o in game.state.players[0].hand)
    )


class TestTheHandIsFreed:
    def test_a_spell_in_hand_gets_the_free_line(self, builder):
        game = board(builder)
        oid = game.state.players[0].hand[0]
        assert any(
            a.cast_free
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.source == oid
        )

    def test_the_permission_reads_true_from_hand(self, builder):
        game = board(builder)
        assert free_cast_permission(game.state, 0, wyrm_card(game), zone="hand")


class TestNoOtherZoneIs:
    @pytest.mark.parametrize("zone", ["graveyard", "exile", "command", "library"])
    def test_another_zone_is_refused(self, builder, zone):
        game = board(builder)
        assert not free_cast_permission(game.state, 0, wyrm_card(game), zone=zone)

    def test_a_caller_naming_no_zone_is_refused(self, builder):
        game = board(builder)
        assert not free_cast_permission(game.state, 0, wyrm_card(game))


class TestTheUnrestrictedFormIsUnchanged:
    @pytest.mark.parametrize("zone", [None, "hand", "graveyard", "command"])
    def test_dracogenesis_still_frees_every_zone(self, builder, zone):
        game = board(builder, permission=AMNESTY)
        assert free_cast_permission(game.state, 0, wyrm_card(game), zone=zone)


class TestTheLoaderGuard:
    def _card(self, affects_spells):
        return CardModel.model_validate(
            {
                "id": "t_bad_omniscience",
                "name": "Test Bad Omniscience",
                "oracle_text": "You may cast spells without paying their mana costs.",
                "mana_cost": "{U}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "You may cast spells without paying their mana costs.",
                        "effect": "free_cast_permission",
                        "affects_player": "you",
                        "affects_spells": affects_spells,
                    }
                ],
            }
        )

    def test_hand_loads(self):
        compile_card(self._card({"from_zone": "hand"}))

    def test_an_unprinted_zone_is_refused(self):
        with pytest.raises(DslError, match="from_zone"):
            compile_card(self._card({"from_zone": "graveyard"}))
