""""If a source would deal damage to you or a planeswalker you control, prevent
all but 1 of that damage." -- 615.1, a cap on each damage event.

Ajani Steadfast's -7 emblem is the witness. It is the inverse of absorb N
(702.63a, the `prevent_damage` static), which prevents N and lets the rest
through; this lets N through and prevents the rest. Writing it as absorb with a
large N would be a different card -- a 1-damage ping would be prevented
entirely, where the emblem lets it land -- and the `prevent_damage` static could
never protect a **player** at all.

The `prevent_all_but` static caps each event at ``amount``, for recipients named
by ``affects_player`` (seats) and/or ``affects`` (permanents), read as a union.
What is pinned below:

1. The cap: a big hit is reduced to 1; a hit already at or below it is untouched.
2. Both recipients -- the player and their planeswalkers -- and nobody else:
   an opponent and an opponent's planeswalker, and your own creature, take full
   damage.
3. The surplus fires `DAMAGE_PREVENTED`; what lands is ordinary damage.
4. Doubling happens first (616.1, the protected player's choice): a doubled hit
   still lands as 1.
5. It works from the command zone, which is where an emblem lives.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_permanent, damage_player, give_emblem
from tests.conftest import only_oid

EMBLEM = "t_all_but_emblem"  # sorcery carrying Ajani Steadfast's emblem
WALKER = "elspeth_sun_s_champion"  # a planeswalker with 4 loyalty
BEAR = "t_bear"
DOUBLER = "t_damage_doubler"  # Furnace of Rath's shape


def position(builder, *, emblem_for: int | None = 0):
    """Each player has a bear and Elspeth; ``emblem_for`` has Ajani's emblem."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR, WALKER])
        .battlefield(1, [BEAR, WALKER])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .step(Step.UNTAP)
        .build()
    )
    if emblem_for is not None:
        give_emblem(game.state, EMBLEM, 0, emblem_for)
    return game


def loyalty(game, oid: int) -> int:
    return game.state.objects[oid].counters.get("loyalty", 0)


class TestTheCap:
    def test_a_big_hit_to_you_lands_as_one(self, builder):
        game = position(builder)
        attacker = only_oid(game, BEAR, 1)
        life = game.state.players[0].life
        assert damage_player(game.state, 0, 7, attacker) == 1
        assert game.state.players[0].life == life - 1

    def test_a_hit_of_one_is_untouched(self, builder):
        """The difference from a large absorb: the one point still lands."""
        game = position(builder)
        attacker = only_oid(game, BEAR, 1)
        life = game.state.players[0].life
        damage_player(game.state, 0, 1, attacker)
        assert game.state.players[0].life == life - 1

    def test_each_event_is_capped_separately(self, builder):
        """"A source would deal damage" -- per event, not a pool for the turn."""
        game = position(builder)
        attacker = only_oid(game, BEAR, 1)
        life = game.state.players[0].life
        damage_player(game.state, 0, 5, attacker)
        damage_player(game.state, 0, 5, attacker)
        assert game.state.players[0].life == life - 2

    def test_without_the_emblem_nothing_is_capped(self, builder):
        game = position(builder, emblem_for=None)
        attacker = only_oid(game, BEAR, 1)
        life = game.state.players[0].life
        damage_player(game.state, 0, 5, attacker)
        assert game.state.players[0].life == life - 5


class TestTheRecipients:
    def test_your_planeswalker_loses_one_loyalty(self, builder):
        game = position(builder)
        walker = only_oid(game, WALKER, 0)
        before = loyalty(game, walker)
        damage_permanent(game.state, walker, 3, only_oid(game, BEAR, 1))
        assert loyalty(game, walker) == before - 1

    def test_your_creature_is_not_covered(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        assert damage_permanent(game.state, mine, 2, only_oid(game, BEAR, 1)) == 2

    def test_the_opponent_is_not_covered(self, builder):
        game = position(builder)
        life = game.state.players[1].life
        damage_player(game.state, 1, 4, only_oid(game, BEAR, 0))
        assert game.state.players[1].life == life - 4

    def test_the_opponents_planeswalker_is_not_covered(self, builder):
        game = position(builder)
        walker = only_oid(game, WALKER, 1)
        before = loyalty(game, walker)
        damage_permanent(game.state, walker, 3, only_oid(game, BEAR, 0))
        assert loyalty(game, walker) == before - 3


class TestTheSurplusWasNeverDealt:
    def test_a_prevention_event_carries_the_surplus(self, builder):
        game = position(builder)
        mark = len(game.state.events)
        damage_player(game.state, 0, 5, only_oid(game, BEAR, 1))
        prevented = [
            e
            for e in game.state.events[mark:]
            if e.type == "damage_prevented" and e.data.get("reason") == "prevent_all_but"
        ]
        assert [e.data["amount"] for e in prevented] == [4]
        dealt = [e for e in game.state.events[mark:] if e.type == "damage_dealt"]
        assert [e.data["amount"] for e in dealt] == [1]


class TestDoublingComesFirst:
    def test_a_doubled_hit_still_lands_as_one(self, builder):
        """616.1 lets the protected player order the two, and they would cap
        last: capping 3 to 1 and then doubling would let 2 through."""
        doubler = (
            builder(players=2)
            .battlefield(0, [BEAR, WALKER])
            .battlefield(1, [BEAR, WALKER, DOUBLER])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .active(0)
            .step(Step.UNTAP)
            .build()
        )
        give_emblem(doubler.state, EMBLEM, 0, 0)
        life = doubler.state.players[0].life
        damage_player(doubler.state, 0, 3, only_oid(doubler, BEAR, 1))
        assert doubler.state.players[0].life == life - 1

    def test_the_doubler_alone_doubles(self, builder):
        """The baseline, so the test above cannot pass on a doubler that did nothing."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [BEAR, DOUBLER])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .active(0)
            .step(Step.UNTAP)
            .build()
        )
        life = game.state.players[0].life
        damage_player(game.state, 0, 3, only_oid(game, BEAR, 1))
        assert game.state.players[0].life == life - 6


class TestTheLoaderRefusesAGuess:
    @staticmethod
    def _card(static: dict) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Probe.",
            "mana_cost": "{W}",
            "types": ["Enchantment"],
            "abilities": [{"kind": "static", "text": "Probe.", **static}],
        }

    def test_the_emblem_line_loads(self):
        compile_card(
            CardModel.model_validate(
                self._card(
                    {
                        "effect": "prevent_all_but",
                        "amount": 1,
                        "affects_player": "you",
                        "affects": {"controller": "you", "types": ["Planeswalker"]},
                    }
                )
            )
        )

    def test_an_amount_is_required(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(
                CardModel.model_validate(
                    self._card({"effect": "prevent_all_but", "affects_player": "you"})
                )
            )

    def test_all_but_zero_is_refused(self):
        with pytest.raises(DslError, match="must be 1 or more"):
            compile_card(
                CardModel.model_validate(
                    self._card(
                        {"effect": "prevent_all_but", "amount": 0, "affects_player": "you"}
                    )
                )
            )

    def test_a_recipient_is_required(self):
        with pytest.raises(DslError, match="whose damage is capped"):
            compile_card(
                CardModel.model_validate(self._card({"effect": "prevent_all_but", "amount": 1}))
            )
