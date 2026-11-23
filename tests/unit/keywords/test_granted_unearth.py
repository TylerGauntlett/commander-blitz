"""Unearth granted to cards in a graveyard: `grant_ability` onto a graveyard card.

    "Repair Barge -- Whenever this Vehicle becomes crewed, each artifact
    creature card in your graveyard gains unearth {3} until end of turn."
                                                            -- Ghost Ark

Unearth (702.84a) is an activated ability that works from the graveyard, so a
card that *gains* it gains exactly that: the printed unearth's expanded ability
(`test_unearth.py`), written once in the granter's ``grantable_abilities`` with
``active_zones: ["graveyard"]`` and handed over by the same `grant_ability` op a
battlefield grant uses. Three rules make the grant right, and each one is a
different card without it:

* **611.2c: the cards there as it resolves.** "Each artifact creature card in
  your graveyard gains" is a one-shot effect that changes characteristics, so it
  reaches the cards in the graveyard at that moment and nothing that arrives
  later the same turn. A standing static would be a stronger card.
* **514.2: until end of turn.** Cleanup ends the grant on a graveyard card as it
  does on a permanent; a grant that stood would hand out unearth forever.
* **400.7: a card that leaves the graveyard is a new object.** One that comes
  back the same turn does not still have unearth.

And the granted ability is the printed one in every respect: sorcery speed, the
granter's mana cost, haste, the end-step exile and "exile it instead if it would
leave the battlefield" -- and it sits after the card's own abilities, so a card
with a printed unearth (Chronomancer) offers both, each at its own price.

`t_gu_barge` in `tests/data/granted_unearth.cards.json` is the Repair Barge on a
{T} ability, so the grant can be made at will. Ghost Ark is the shipped witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import abilities_of, chars
from commanderblitz.engine.enums import ActionKind, Keyword, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, advance_to_step, only_oid, pass_until, settle

BARGE = "t_gu_barge"
GOLEM = "t_gu_golem"  # an artifact creature card: matches
BEAR = "t_gu_bear"  # a creature card, not an artifact
RELIC = "t_gu_relic"  # an artifact card, not a creature
CHRONOMANCER = "chronomancer"  # an artifact creature with its own Unearth {2}{B}
SWAMP = "swamp"


def card(game, card_id: str) -> int:
    """The one object of ``card_id``, in whatever zone it is."""
    [oid] = [o.oid for o in game.state.objects.values() if o.def_id == card_id]
    return oid


def position(builder, graveyard=(GOLEM, BEAR, RELIC), *, lands: int = 6, hand=(), land=SWAMP):
    """Player 0 with the barge and lands; ``graveyard`` in their graveyard.

    Returns ``(game, barge)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, [BARGE, *[land] * lands])
        .graveyard(0, list(graveyard))
        .hand(0, list(hand))
        .build()
    )
    return game, only_oid(game, BARGE, 0)


def repair(game, barge: int) -> None:
    """Tap the barge and let the grant resolve."""
    [action] = activations(game, barge, 0)
    game.apply(action)
    settle(game)


def unearth_offers(game, oid: int) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid
    ]


def unearth(game, oid: int) -> None:
    [action] = unearth_offers(game, oid)
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)


class TestWhoGainsIt:
    def test_nothing_has_unearth_before_the_grant(self, builder):
        game, _barge = position(builder)
        assert unearth_offers(game, card(game, GOLEM)) == []

    def test_an_artifact_creature_card_in_your_graveyard_gains_it(self, builder):
        game, barge = position(builder)
        repair(game, barge)
        golem = card(game, GOLEM)
        assert len(unearth_offers(game, golem)) == 1
        [granted] = abilities_of(game.state, golem)
        assert granted.text.startswith("Unearth {3}")

    def test_a_card_that_is_not_an_artifact_creature_does_not(self, builder):
        game, barge = position(builder)
        repair(game, barge)
        assert unearth_offers(game, card(game, BEAR)) == []
        assert unearth_offers(game, card(game, RELIC)) == []

    def test_an_opponents_graveyard_is_not_yours(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BARGE, *[SWAMP] * 6])
            .graveyard(1, [GOLEM])
            .build()
        )
        repair(game, only_oid(game, BARGE, 0))
        assert abilities_of(game.state, card(game, GOLEM)) == ()

    def test_a_card_that_arrives_afterwards_does_not(self, builder):
        """611.2c: the effect reached the cards there as it resolved."""
        game, barge = position(builder, graveyard=(BEAR,), hand=(GOLEM,))
        repair(game, barge)
        golem = card(game, GOLEM)
        move_object(game.state, golem, Zone.GRAVEYARD, to_player=0, cause="discard")
        assert unearth_offers(game, golem) == []


class TestTheGrantedAbilityIsUnearth:
    def test_it_returns_the_card_with_haste(self, builder):
        game, barge = position(builder)
        repair(game, barge)
        golem = card(game, GOLEM)
        unearth(game, golem)

        assert game.state.objects[golem].zone is Zone.BATTLEFIELD
        assert game.state.objects[golem].controller == 0
        assert Keyword.HASTE.value in chars(game.state, golem).keywords

    def test_it_costs_three(self, builder):
        """Two Swamps do not pay unearth {3}."""
        game, barge = position(builder, lands=2)
        repair(game, barge)
        assert unearth_offers(game, card(game, GOLEM)) == []

    def test_it_is_exiled_at_the_next_end_step(self, builder):
        game, barge = position(builder)
        repair(game, barge)
        golem = card(game, GOLEM)
        unearth(game, golem)

        advance_to_step(game, Step.END_STEP)
        pass_until(game, lambda g: g.state.objects[golem].zone is not Zone.BATTLEFIELD)
        assert game.state.objects[golem].zone is Zone.EXILE

    @pytest.mark.parametrize("to", [Zone.HAND, Zone.GRAVEYARD, Zone.LIBRARY])
    def test_it_is_exiled_instead_however_it_leaves(self, builder, to):
        game, barge = position(builder)
        repair(game, barge)
        golem = card(game, GOLEM)
        unearth(game, golem)

        move_object(game.state, golem, to, to_player=0, cause="test")
        assert game.state.objects[golem].zone is Zone.EXILE

    def test_only_as_a_sorcery(self, builder):
        """Still this turn, so the grant stands -- but combat is no main phase."""
        game, barge = position(builder)
        repair(game, barge)
        golem = card(game, GOLEM)
        advance_to_step(game, Step.BEGIN_COMBAT)
        assert game.state.objects[golem].zone is Zone.GRAVEYARD
        assert unearth_offers(game, golem) == []

    def test_the_grant_outlives_the_granter(self, builder):
        """A resolved effect, not a static: the barge leaving takes nothing."""
        game, barge = position(builder)
        repair(game, barge)
        move_object(game.state, barge, Zone.EXILE, to_player=0, cause="test")
        golem = card(game, GOLEM)
        unearth(game, golem)
        assert game.state.objects[golem].zone is Zone.BATTLEFIELD


class TestHowLongItLasts:
    def test_it_ends_at_cleanup(self, builder):
        game, barge = position(builder)
        repair(game, barge)
        golem = card(game, GOLEM)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert abilities_of(game.state, golem) == ()

    def test_a_card_that_leaves_the_graveyard_loses_it(self, builder):
        """400.7: the card back in the graveyard is a new object."""
        game, barge = position(builder)
        repair(game, barge)
        golem = card(game, GOLEM)
        move_object(game.state, golem, Zone.HAND, to_player=0, cause="test")
        move_object(game.state, golem, Zone.GRAVEYARD, to_player=0, cause="discard")
        assert unearth_offers(game, golem) == []


class TestBesideAPrintedUnearth:
    def test_both_are_offered_each_at_its_own_price(self, builder):
        game, barge = position(builder, graveyard=(CHRONOMANCER,))
        repair(game, barge)
        chrono = card(game, CHRONOMANCER)
        _transmute, printed, granted = abilities_of(game.state, chrono)
        assert printed.text.startswith("Unearth {2}{B}")
        assert granted.text.startswith("Unearth {3}")
        assert {a.ability_index for a in unearth_offers(game, chrono)} == {1, 2}

    def test_the_granted_one_resolves_as_itself(self, builder):
        """Forests pay {3} and not {2}{B}: the appended index is the barge's
        ability, and resolves as it."""
        game, barge = position(builder, graveyard=(CHRONOMANCER,), land="forest")
        repair(game, barge)
        chrono = card(game, CHRONOMANCER)
        assert [a.ability_index for a in unearth_offers(game, chrono)] == [2]
        unearth(game, chrono)
        assert game.state.objects[chrono].zone is Zone.BATTLEFIELD
        assert Keyword.HASTE.value in chars(game.state, chrono).keywords


def granting(grantable: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_gu_probe",
            "name": "Granted Unearth Probe",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "cost": {"tap": True},
                    "effects": [
                        {
                            "op": "grant_ability",
                            "ability": 0,
                            "objects": {"zone": "graveyard", "types": ["Creature"]},
                        }
                    ],
                }
            ],
            "grantable_abilities": [grantable],
        }
    )


class TestTheLoaderRefuses:
    def test_a_battlefield_ability_granted_to_a_graveyard_card(self):
        """It would sit on the card and never be offered."""
        with pytest.raises(DslError, match="graveyard"):
            compile_card(
                granting(
                    {
                        "kind": "activated",
                        "cost": {"mana": "{1}"},
                        "effects": [{"op": "draw", "player": "you"}],
                    }
                )
            )

    def test_a_triggered_ability_granted_to_a_graveyard_card(self):
        with pytest.raises(DslError, match="graveyard"):
            compile_card(
                granting(
                    {
                        "kind": "triggered",
                        "active_zones": ["graveyard"],
                        "trigger": {"event": "self_enters"},
                        "effects": [{"op": "draw", "player": "you"}],
                    }
                )
            )
