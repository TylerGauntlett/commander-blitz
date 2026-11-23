"""Trazyn the Infinite -- abilities lent off the artifact cards in a graveyard.

    Prismatic Gallery -- As long as Trazyn is on the battlefield, it has all
    activated abilities of all artifact cards in your graveyard.

The `grant_graveyard_abilities` static. The lending is `grant_exiled_abilities`'s
(113.6, 602.1: the abilities are Trazyn's, a `{T}` taps Trazyn, "this permanent"
is Trazyn), and what differs is which cards lend:

* **"Your graveyard."** The graveyard of the source's *controller*, read every
  time it is asked: an artifact card lends from the moment it arrives and stops
  the moment it leaves, and an opponent's artifact cards lend nothing.
* **"Artifact cards."** The card's printed type in the graveyard -- the
  characteristics a card has there, and a pipeline input, so no layer-6
  dependency arises. A creature card beside it lends nothing.
* **608.2.** An activated ability resolves independently of its source, so an
  ability borrowed off a card that has since left the graveyard still resolves:
  the definition rides the stack item (`StackItem.granted_ability`).

Without it Trazyn is a vanilla deathtouch body. `t_gg_trazyn` in
`tests/data/grant_graveyard_abilities.cards.json` is the static line; Trazyn the
Infinite itself is the shipped witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import abilities_of
from commanderblitz.engine.costs import mana_sources
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.stack import ability_of
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, only_oid, settle, static_probe

TRAZYN = "t_gg_trazyn"
RELIC = "t_gg_relic"
SOL_RING = "sol_ring"
ELVES = "llanowar_elves"
RELIC_TEXT = "{1}, {T}: Put a +1/+1 counter on this permanent."
ANCHOR = "lightning_bolt"  # keeps player 0 holding priority in the main phase
LANDS = ["forest", "forest", "mountain"]


def card(game, card_id: str) -> int:
    """The one object of ``card_id``, in whatever zone it is."""
    [oid] = [o.oid for o in game.state.objects.values() if o.def_id == card_id]
    return oid


def position(builder, *, graveyard=(RELIC,), opponent_graveyard=()):
    """Player 0 with Trazyn and lands, ``graveyard`` in their graveyard.

    Returns ``(game, trazyn)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, [TRAZYN, *LANDS])
        .hand(0, [ANCHOR])
        .graveyard(0, list(graveyard))
        .graveyard(1, list(opponent_graveyard))
        .build()
    )
    return game, only_oid(game, TRAZYN, 0)


def lent(game, trazyn: int) -> list[str]:
    return [a.text for a in abilities_of(game.state, trazyn)[1:]]


class TestTrazynHasTheAbility:
    def test_the_artifact_cards_ability_is_appended(self, builder):
        game, trazyn = position(builder)

        assert lent(game, trazyn) == [RELIC_TEXT]
        assert abilities_of(game.state, trazyn)[1].index == 1

    def test_activating_it_taps_trazyn_and_this_permanent_is_trazyn(self, builder):
        game, trazyn = position(builder)
        relic = card(game, RELIC)
        game.apply(activations(game, trazyn, 1)[0])

        item = game.state.stack[-1]
        assert item.source_oid == trazyn
        assert item.granted_ability is not None
        assert ability_of(game.state, item).text == RELIC_TEXT
        assert game.state.objects[trazyn].tapped
        settle(game)

        assert game.state.objects[trazyn].counter(PLUS_ONE) == 1
        assert game.state.objects[relic].zone is Zone.GRAVEYARD

    def test_it_resolves_after_the_card_has_left_the_graveyard(self, builder):
        """608.2: once activated, the ability no longer needs the card."""
        game, trazyn = position(builder)
        game.apply(activations(game, trazyn, 1)[0])
        move_object(game.state, card(game, RELIC), Zone.EXILE)
        settle(game)

        assert game.state.objects[trazyn].counter(PLUS_ONE) == 1

    def test_a_mana_ability_is_lent(self, builder):
        game, trazyn = position(builder, graveyard=(SOL_RING,))

        assert abilities_of(game.state, trazyn)[1].is_mana_ability
        source = next(s for s in mana_sources(game.state, 0) if s.oid == trazyn)
        assert source.options == ((0, 0, 0, 0, 0, 2),)


class TestOnlyArtifactCardsInYourGraveyard:
    def test_a_creature_card_lends_nothing(self, builder):
        game, trazyn = position(builder, graveyard=(ELVES,))

        assert lent(game, trazyn) == []
        assert not activations(game, trazyn)

    def test_each_artifact_card_lends_its_abilities(self, builder):
        game, trazyn = position(builder, graveyard=(RELIC, ELVES, SOL_RING))

        assert lent(game, trazyn) == [RELIC_TEXT, "{T}: Add {C}{C}."]

    def test_an_opponents_graveyard_lends_nothing(self, builder):
        game, trazyn = position(builder, graveyard=(), opponent_graveyard=(RELIC,))

        assert lent(game, trazyn) == []

    def test_a_card_that_arrives_lends_at_once(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [TRAZYN, RELIC, *LANDS])
            .build()
        )
        trazyn = only_oid(game, TRAZYN, 0)
        assert lent(game, trazyn) == []
        move_object(game.state, card(game, RELIC), Zone.GRAVEYARD, to_player=0)

        assert lent(game, trazyn) == [RELIC_TEXT]

    def test_a_card_that_leaves_stops_lending(self, builder):
        game, trazyn = position(builder)
        move_object(game.state, card(game, RELIC), Zone.EXILE)

        assert lent(game, trazyn) == []
        assert not activations(game, trazyn, 1)


class TestTheGrantEndsWithTrazyn:
    def test_trazyn_in_the_graveyard_has_only_its_printed_ability(self, builder):
        game, trazyn = position(builder)
        move_object(game.state, trazyn, Zone.GRAVEYARD, to_player=0)

        assert lent(game, trazyn) == []


class TestTheLoader:
    def compile(self, **static) -> None:
        compile_card(
            CardModel.model_validate(
                static_probe({"effect": "grant_graveyard_abilities", **static})
            )
        )

    def test_the_printed_shape_loads(self):
        self.compile(affects={"self_only": True}, types=["Artifact"])

    def test_types_is_required(self):
        with pytest.raises(DslError, match="needs 'types'"):
            self.compile(affects={"self_only": True})

    def test_affects_is_required(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            self.compile(types=["Artifact"])

    def test_an_unknown_card_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            self.compile(affects={"self_only": True}, types=["Artifacts"])

    def test_a_grantable_index_is_refused(self):
        with pytest.raises(DslError, match="takes no 'ability'"):
            self.compile(affects={"self_only": True}, types=["Artifact"], ability=0)

    def test_it_cannot_itself_be_granted(self):
        with pytest.raises(DslError, match="read off printed faces"):
            compile_card(
                CardModel.model_validate(
                    {
                        **static_probe(
                            {"effect": "grant_ability", "affects": {"controller": "you"}, "ability": 0}
                        ),
                        "grantable_abilities": [
                            {
                                "kind": "static",
                                "text": "Probe.",
                                "effect": "grant_graveyard_abilities",
                                "affects": {"self_only": True},
                                "types": ["Artifact"],
                            }
                        ],
                    }
                )
            )
