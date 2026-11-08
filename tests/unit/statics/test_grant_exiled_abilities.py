"""Hazel's Brewmaster -- abilities lent off the cards exiled with a permanent.

    Foods you control have all activated abilities of all creature cards
    exiled with this creature.

The `grant_exiled_abilities` static. The abilities are the **Food's** once lent
(113.6, 602.1): its controller activates them, a `{T}` in their cost taps the
Food, and "this creature" in their text is the Food. Three rules make the card:

* **607.2a, linked abilities.** "Exiled with this creature" is the cards the
  source's own exiles linked to *this object* (`exiled_cards`), not every card
  in exile; a card some other permanent exiled lends nothing, and a source that
  leaves the battlefield takes the link -- and the grant, which is its static --
  with it (400.7).
* **"Creature cards".** The card's printed type in exile: an artifact card
  exiled the same way lends nothing, mana abilities or not.
* **608.2.** An activated ability resolves independently of its source, so an
  ability borrowed off a card that has since left exile still resolves -- the
  definition rides the stack item (`StackItem.granted_ability`), because it is
  in no ``grantable_abilities`` pool for a ``(granter, index)`` pair to name.

`t_gx_brewmaster` in `tests/data/grant_exiled_abilities.cards.json` is the
static line of Hazel's Brewmaster; Hazel's Brewmaster itself is the shipped
witness.
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
from commanderblitz.engine.zones import exile, link_exiled, move_object
from tests.conftest import activations, only_oid, settle, static_probe

BREWMASTER = "t_gx_brewmaster"
TINKERER = "t_gx_tinkerer"
ELVES = "llanowar_elves"
SOL_RING = "sol_ring"
FOOD = "food_token"
TINKER_TEXT = "{1}, {T}: Put a +1/+1 counter on this creature."
ANCHOR = "lightning_bolt"  # keeps player 0 holding priority in the main phase
PRINTED = 1  # the Food's own "{2}, {T}, Sacrifice this artifact: You gain 3 life."


def card(game, card_id: str) -> int:
    """The one object of ``card_id``, in whatever zone it is."""
    [oid] = [o.oid for o in game.state.objects.values() if o.def_id == card_id]
    return oid


def position(builder, *, exiled=(TINKERER,), by_brewmaster=True):
    """Player 0 with the Brewmaster and a Food; ``exiled`` cards moved from
    their graveyard to exile, linked to the Brewmaster or to nothing. The Bolt
    is an anchor: an instant to cast keeps player 0 from being auto-passed
    out of the phase while an ability waits on the stack.

    Returns ``(game, brewmaster, food)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, [BREWMASTER, FOOD, "forest", "forest", "mountain"])
        .hand(0, [ANCHOR])
        .graveyard(0, list(exiled))
        .build()
    )
    brewmaster = only_oid(game, BREWMASTER, 0)
    for card_id in exiled:
        oid = card(game, card_id)
        exile(game.state, oid, by=brewmaster if by_brewmaster else None)
        if by_brewmaster:
            link_exiled(game.state, oid, brewmaster)
    game.state.bump_chars()
    return game, brewmaster, only_oid(game, FOOD, 0)


def lent(game, food: int) -> list[str]:
    return [a.text for a in abilities_of(game.state, food)[PRINTED:]]


class TestTheFoodHasTheAbility:
    def test_the_exiled_creature_cards_ability_is_appended(self, builder):
        game, _, food = position(builder)

        assert lent(game, food) == [TINKER_TEXT]
        assert abilities_of(game.state, food)[PRINTED].index == PRINTED

    def test_its_controller_may_activate_it(self, builder):
        game, _, food = position(builder)

        assert activations(game, food, PRINTED)

    def test_activating_it_taps_the_food_and_this_creature_is_the_food(self, builder):
        """113.6 / 602.1: the ability is the Food's, so its `{T}` taps the
        Food and its "this creature" is the Food."""
        game, _, food = position(builder)
        tinkerer = card(game, TINKERER)
        game.apply(activations(game, food, PRINTED)[0])

        item = game.state.stack[-1]
        assert item.source_oid == food
        assert item.granted_ability is not None
        assert ability_of(game.state, item).text == TINKER_TEXT
        assert game.state.objects[food].tapped
        settle(game)

        assert game.state.objects[food].counter(PLUS_ONE) == 1
        assert game.state.objects[tinkerer].counter(PLUS_ONE) == 0
        assert game.state.objects[tinkerer].zone is Zone.EXILE

    def test_it_resolves_after_the_card_has_left_exile(self, builder):
        """608.2: once activated, the ability no longer needs the card."""
        game, _, food = position(builder)
        tinkerer = card(game, TINKERER)
        game.apply(activations(game, food, PRINTED)[0])
        move_object(game.state, tinkerer, Zone.GRAVEYARD, to_player=0)
        settle(game)

        assert game.state.objects[food].counter(PLUS_ONE) == 1

    def test_the_brewmaster_itself_does_not_have_it(self, builder):
        game, brewmaster, _ = position(builder)

        assert not activations(game, brewmaster)


class TestAManaAbilityIsLent:
    def test_the_food_taps_for_green(self, builder):
        game, _, food = position(builder, exiled=(ELVES,))

        assert lent(game, food) == ["{T}: Add {G}."]
        assert abilities_of(game.state, food)[PRINTED].is_mana_ability
        source = next(s for s in mana_sources(game.state, 0) if s.oid == food)
        assert source.options == ((0, 0, 0, 0, 1, 0),)


class TestOnlyLinkedCreatureCards:
    def test_a_noncreature_card_lends_nothing(self, builder):
        """An artifact card exiled with it, mana ability and all."""
        game, _, food = position(builder, exiled=(SOL_RING,))

        assert lent(game, food) == []
        assert not any(s.oid == food for s in mana_sources(game.state, 0))

    def test_a_card_exiled_by_something_else_lends_nothing(self, builder):
        game, _, food = position(builder, by_brewmaster=False)

        assert lent(game, food) == []
        assert not activations(game, food, PRINTED)

    def test_a_card_that_left_exile_lends_nothing(self, builder):
        game, _, food = position(builder)
        move_object(game.state, card(game, TINKERER), Zone.GRAVEYARD, to_player=0)

        assert lent(game, food) == []

    def test_each_linked_card_lends_its_abilities(self, builder):
        game, _, food = position(builder, exiled=(TINKERER, ELVES, SOL_RING))

        assert lent(game, food) == [TINKER_TEXT, "{T}: Add {G}."]

    def test_an_opponents_food_gets_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BREWMASTER])
            .battlefield(1, [FOOD])
            .graveyard(0, [TINKERER])
            .build()
        )
        brewmaster = only_oid(game, BREWMASTER, 0)
        tinkerer = card(game, TINKERER)
        exile(game.state, tinkerer, by=brewmaster)
        link_exiled(game.state, tinkerer, brewmaster)

        assert len(abilities_of(game.state, only_oid(game, FOOD, 1))) == PRINTED


class TestTheGrantEndsWithTheSource:
    def test_it_ends_when_the_brewmaster_leaves(self, builder):
        game, brewmaster, food = position(builder)
        move_object(game.state, brewmaster, Zone.GRAVEYARD, to_player=0)

        assert lent(game, food) == []
        assert not activations(game, food, PRINTED)

    def test_a_brewmaster_that_returns_is_a_new_object(self, builder):
        """400.7 and 607.2a: the card is still in exile, but it was exiled
        with the old object, so the new one lends nothing."""
        game, brewmaster, food = position(builder)
        move_object(game.state, brewmaster, Zone.GRAVEYARD, to_player=0)
        move_object(game.state, brewmaster, Zone.BATTLEFIELD, to_player=0)

        assert game.state.objects[card(game, TINKERER)].zone is Zone.EXILE
        assert lent(game, food) == []


class TestTheLoader:
    def compile(self, **static) -> None:
        compile_card(
            CardModel.model_validate(
                static_probe({"effect": "grant_exiled_abilities", **static})
            )
        )

    def test_the_printed_shape_loads(self):
        self.compile(affects={"subtypes": ["Food"], "controller": "you"}, types=["Creature"])

    def test_types_is_required(self):
        with pytest.raises(DslError, match="needs 'types'"):
            self.compile(affects={"subtypes": ["Food"], "controller": "you"})

    def test_affects_is_required(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            self.compile(types=["Creature"])

    def test_an_unknown_card_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            self.compile(affects={"controller": "you"}, types=["Creatures"])

    def test_a_grantable_index_is_refused(self):
        with pytest.raises(DslError, match="takes no 'ability'"):
            self.compile(affects={"controller": "you"}, types=["Creature"], ability=0)

    def test_it_cannot_itself_be_granted(self):
        """Collected off printed faces with `grant_ability`, so a granted copy
        would be inert -- refused rather than loaded."""
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
                                "effect": "grant_exiled_abilities",
                                "affects": {"controller": "you"},
                                "types": ["Creature"],
                            }
                        ],
                    }
                )
            )
