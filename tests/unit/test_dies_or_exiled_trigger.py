"""A leaves-the-battlefield trigger that cares where the permanent went.

Kaya the Inexorable's +1 gives a creature "When this creature **dies or is put
into exile**, return it to its owner's hand and create a 1/1 white Spirit
creature token with flying." `dies` alone misses the exile half, and bare
`leaves_battlefield` is wider than the card: a bounce or a tuck would also
return it (to a hand it is already in, or out of the library) and make a Spirit
for free. So `leaves_battlefield` takes `to_zones`, compared against the
destination `move_object` now stamps on every departure.

The effect half needs nothing new. The trigger's source is the card, which has
kept its oid in its new zone, and a `union` selector finds it in whichever of the
graveyard or exile it reached. The granted ability is still heard as the
creature leaves, because `left_with` snapshots the permanent grants.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import grant_ability
from automtg.engine.zones import bounce, destroy, move_object
from tests.conftest import count_on_battlefield, only_oid, pass_until

SPIRIT = "spirit_1_1_w_flying"


def a_ghostformed_bear(builder):
    """Player 0's Test Bear carrying the granted ghostform trigger; the game and its oid."""
    game = builder(players=2).battlefield(0, ["t_bear", "t_ghostform_source"]).build()
    bear = only_oid(game, "t_bear")
    grant_ability(game.state, bear, 0, only_oid(game, "t_ghostform_source"), permanent=True)
    return game, bear


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestItFires:
    def test_when_it_dies(self, builder):
        game, bear = a_ghostformed_bear(builder)
        destroy(game.state, bear)
        settle(game)
        assert game.state.objects[bear].zone is Zone.HAND
        assert count_on_battlefield(game, SPIRIT, 0) == 1

    def test_when_it_is_exiled(self, builder):
        game, bear = a_ghostformed_bear(builder)
        move_object(game.state, bear, Zone.EXILE)
        settle(game)
        assert game.state.objects[bear].zone is Zone.HAND
        assert count_on_battlefield(game, SPIRIT, 0) == 1


class TestItDoesNotFire:
    def test_when_it_is_bounced(self, builder):
        game, bear = a_ghostformed_bear(builder)
        bounce(game.state, bear)
        settle(game)
        assert count_on_battlefield(game, SPIRIT, 0) == 0

    def test_when_it_is_tucked(self, builder):
        game, bear = a_ghostformed_bear(builder)
        move_object(game.state, bear, Zone.LIBRARY)
        settle(game)
        assert game.state.objects[bear].zone is Zone.LIBRARY
        assert count_on_battlefield(game, SPIRIT, 0) == 0

    def test_after_it_came_back_as_a_new_object(self, builder):
        """400.7: the returned card has no ghostform; dying again does nothing."""
        game, bear = a_ghostformed_bear(builder)
        destroy(game.state, bear)
        settle(game)
        move_object(game.state, bear, Zone.BATTLEFIELD)
        destroy(game.state, bear)
        settle(game)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert count_on_battlefield(game, SPIRIT, 0) == 1


class TestTheLoaderGuards:
    def _card(self, trigger: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_departing",
                "name": "Test Departing",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "oracle_text": "When this creature dies or is put into exile, draw a card.",
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "When this creature dies or is put into exile, draw a card.",
                        "trigger": trigger,
                        "effects": [{"op": "draw", "amount": {"const": 1}}],
                    }
                ],
            }
        )

    def test_it_loads_on_leaves_battlefield(self):
        card = compile_card(
            self._card(
                {"event": "leaves_battlefield", "source": "self", "to_zones": ["graveyard", "exile"]}
            )
        )
        assert card.abilities[0].trigger.to_zones == ("graveyard", "exile")

    def test_it_is_refused_on_another_event(self):
        with pytest.raises(DslError, match="to_zones"):
            compile_card(self._card({"event": "dies", "source": "self", "to_zones": ["exile"]}))

    def test_a_zone_nothing_leaves_to_is_refused(self):
        with pytest.raises(DslError, match="to_zones"):
            compile_card(
                self._card(
                    {"event": "leaves_battlefield", "source": "self", "to_zones": ["battlefield"]}
                )
            )
