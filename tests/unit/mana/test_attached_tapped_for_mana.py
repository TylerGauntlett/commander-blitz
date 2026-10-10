"""The Aura form of a triggered mana ability: Wild Growth, Utopia Sprawl.

    "Whenever enchanted land is tapped for mana, its controller adds an
    additional {G}."

The mechanism was already right. `add_mana_on_tap` (Crypt Ghast) is read at the
mana choke point rather than queued, because 605.1b makes a triggered mana
ability resolve immediately without using the stack -- and that is exactly what
these Auras need too, since mana arriving one priority later cannot pay for the
spell it was tapped for.

What was missing was a way to say **which** permanent. `tapped_permanent` could
only carry `types`/`subtypes`/`supertypes`, which describe a *class*: written as
Vernal Bloom's `{"subtypes": ["Forest"]}` Wild Growth becomes a card that pays
out for every Forest its controller taps. On a board of eight Forests that is
seven extra green mana a turn that the real card does not make -- a strictly
better card, silently, which is the failure the authoring gates exist to catch.

So `attached` names the one permanent the static's source is attached to. It is
checked against `source.attached_to` rather than against the tapped permanent's
characteristics, because it is a fact about the Aura, not a description of the
land -- the same argument `test_attached.py` makes for reading attachment off
the ability's source.

The tests below assert the near miss in both directions: the *other* land must
make only its own mana, and the Aura must follow when it moves.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX
from commanderblitz.engine.primitives import attach
from tests.conftest import oids_of

GROWTH = "t_wild_growth"  # the Aura: "whenever enchanted land is tapped for mana"
BLOOM = "t_vernal_bloom"  # the class spelling: "whenever a Forest is tapped"
SPRAWL = "t_utopia_sprawl"  # the same, adding "one mana of the chosen color"

G = SYMBOL_INDEX["G"]
U = SYMBOL_INDEX["U"]


def board(builder, *, lands=("forest", "forest"), enchantment=GROWTH):
    """``(game, aura_oid, [land oids])`` -- the Aura down but attached to nothing."""
    game = (
        builder(players=2)
        .battlefield(0, [enchantment, *lands])
        .build(advance=False)
    )
    aura = oids_of(game, enchantment, 0)[0]
    return game, aura, [oid for land in set(lands) for oid in oids_of(game, land, 0)]


def tap_for_mana(game, oid: int, pid: int = 0) -> list[int]:
    """Tap one permanent for mana and return the pool it filled."""
    activate_mana_ability(game.state, oid, 0, pid)
    return list(game.state.players[pid].mana_pool.amounts)


class TestTheEnchantedLandMakesTheExtraMana:
    def test_the_enchanted_forest_makes_two_green(self, builder):
        game, aura, lands = board(builder)
        attach(game.state, aura, lands[0])
        pool = tap_for_mana(game, lands[0])
        assert pool[G] == 2
        assert sum(pool) == 2

    def test_the_other_forest_makes_only_its_own(self, builder):
        """The near miss, and the whole reason `attached` exists.

        Spelled as Vernal Bloom this land would also make two, which is a
        different and much larger card.
        """
        game, aura, lands = board(builder)
        attach(game.state, aura, lands[0])
        pool = tap_for_mana(game, lands[1])
        assert pool[G] == 1

    def test_the_class_spelling_really_does_hit_both(self, builder):
        """Kept live so the contrast above is measured, not assumed."""
        game, _, lands = board(builder, enchantment=BLOOM)
        assert tap_for_mana(game, lands[1])[G] == 2


class TestTheLinkIsFollowed:
    def test_an_aura_attached_to_nothing_adds_nothing(self, builder):
        """A state-based action is about to bin it; until then it pays out for
        no one, rather than for every land on the table."""
        game, _aura, lands = board(builder)
        pool = tap_for_mana(game, lands[0])
        assert pool[G] == 1

    def test_moving_the_aura_moves_the_mana(self, builder):
        game, aura, lands = board(builder)
        attach(game.state, aura, lands[0])
        attach(game.state, aura, lands[1])
        assert tap_for_mana(game, lands[1])[G] == 2

    def test_the_land_it_left_is_ordinary_again(self, builder):
        game, aura, lands = board(builder)
        attach(game.state, aura, lands[0])
        attach(game.state, aura, lands[1])
        assert tap_for_mana(game, lands[0])[G] == 1


class TestTheControllerIsWhoeverTapped:
    def test_an_opponents_enchanted_land_fills_the_opponents_pool(self, builder):
        """"its controller adds" -- the mana follows the tap, not the Aura.

        Wild Growth is not usually pointed at somebody else's land, but the
        printed sentence says whose mana it is and `affects_player: "any"` is
        what makes that true rather than incidental.
        """
        game = (
            builder(players=2)
            .battlefield(0, [GROWTH])
            .battlefield(1, ["forest"])
            .build(advance=False)
        )
        aura = oids_of(game, GROWTH, 0)[0]
        theirs = oids_of(game, "forest", 1)[0]
        attach(game.state, aura, theirs)
        assert tap_for_mana(game, theirs, pid=1)[G] == 2
        assert sum(game.state.players[0].mana_pool.amounts) == 0


class TestTheChosenColourRider:
    """Utopia Sprawl: "its controller adds one mana of the chosen color".

    Deliberately the same ``{"chosen_color_of": "self"}`` spelling the ``add_mana``
    *op* takes, so one card cannot mean two different things by one key.
    """

    def test_it_adds_the_chosen_colour(self, builder):
        game, aura, lands = board(builder, enchantment=SPRAWL)
        game.state.objects[aura].chosen_color = "U"
        attach(game.state, aura, lands[0])
        pool = tap_for_mana(game, lands[0])
        assert pool[U] == 1
        assert pool[G] == 1, "the Forest still makes its own green"

    def test_a_different_choice_makes_different_mana(self, builder):
        """The colour is really read, rather than a green constant that happens
        to match the land."""
        game, aura, lands = board(builder, enchantment=SPRAWL)
        game.state.objects[aura].chosen_color = "G"
        attach(game.state, aura, lands[0])
        assert tap_for_mana(game, lands[0])[G] == 2

    def test_no_colour_chosen_yet_adds_nothing(self, builder):
        """This runs inside cost payment, where nothing may stop to ask (605.1a).

        So an unanswered choice adds nothing -- the match-nothing default the
        chosen colour has everywhere else -- rather than guessing a colour.
        """
        game, aura, lands = board(builder, enchantment=SPRAWL)
        attach(game.state, aura, lands[0])
        pool = tap_for_mana(game, lands[0])
        assert sum(pool) == 1
        assert pool[G] == 1

    def test_it_still_only_pays_out_for_the_enchanted_land(self, builder):
        game, aura, lands = board(builder, enchantment=SPRAWL)
        game.state.objects[aura].chosen_color = "U"
        attach(game.state, aura, lands[0])
        assert tap_for_mana(game, lands[1])[U] == 0


class TestTheLoaderRefusesTheAmbiguousSpellings:
    def _card(self, tapped: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Whenever enchanted land is tapped for mana, add {G}.",
                "mana_cost": "{G}",
                "types": ["Enchantment"],
                "subtypes": ["Aura"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Whenever enchanted land is tapped for mana, add {G}.",
                        "effect": "add_mana_on_tap",
                        "affects_player": "any",
                        "tapped_permanent": tapped,
                        "add_mana": "{G}",
                    }
                ],
            }
        )

    def test_attached_true_loads(self):
        compile_card(self._card({"attached": True}))

    def test_attached_false_is_refused(self):
        """`false` would have to mean "any permanent", which is what leaving the
        key out already says. An author who writes it means something else."""
        with pytest.raises(DslError, match="attached"):
            compile_card(self._card({"attached": False}))

    def test_an_empty_tapped_permanent_is_still_refused(self):
        with pytest.raises(DslError, match="tapped_permanent"):
            compile_card(self._card({}))

    def test_the_only_dynamic_add_mana_is_the_chosen_colour(self):
        """A dict that is not that one spelling is refused rather than ignored.

        Ignored, it would be a static that silently adds nothing -- an inert
        ability on a card that looks implemented.
        """
        card = self._card({"attached": True})
        card.abilities[0].add_mana = {"chosen_color_of": "enchanted"}
        with pytest.raises(DslError, match="chosen_color_of"):
            compile_card(card)
