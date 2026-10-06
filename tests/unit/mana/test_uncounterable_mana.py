"""Mana that makes the spell it pays for uncounterable.

    "{T}: Add one mana of any color. Spend this mana only to cast a creature
    spell of the chosen type, **and that spell can't be countered**."
                                    -- Cavern of Souls, Delighted Halfling

The engine had two ways to say "can't be countered" and neither of them is this
one:

* the **card-level** `uncounterable` rider, which is a spell saying it about
  itself. Written that way, every copy of the creature would be uncounterable
  however it was cast -- the Cavern need not even be on the battlefield.
* the **`spells_cant_be_countered` static**, which is somebody else saying it
  about a *class* of spell. Written that way it would protect every creature
  spell of the chosen type on the table, whoever cast it and whatever paid for
  it.

The printed sentence is narrower than both: it is about *this* spell, because of
*this* mana. So the rider travels on the **pip**.

That is the design decision the whole change turns on, and the reason is Cavern
itself: it has **two** mana abilities and only the second one prints the clause.
Recorded against the permanent, tapping a Cavern for its plain `{C}` would make
the spell uncounterable too -- a strictly better card than the one printed, and
exactly the silent kind of wrong the authoring gates exist to catch. The test
pool keeps both abilities on one card so that case is measured rather than
argued.

`mana.Pip` carries it; `ManaPool.spend` reports whether **any** consumed pip did
(any, not all: the sentence is about the spell the mana was spent on and says
nothing about the rest of its cost); `costs.pay_mana` writes that onto the
spell's object at the one instant it is knowable, since a pip's rider is
unrecoverable the moment the pip is spent.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import activate_mana_ability
from automtg.engine.errors import DslError
from automtg.engine.mana import SYMBOL_INDEX, ManaPool, Pip, Requirement

CAVERN = "t_cavern"  # ability 0 is plain {C}; ability 1 carries the rider
PLAIN = "t_uc_plain_rock"  # the same any-colour mana, no rider

PLAIN_MANA = 0  # ability index of Cavern's "{T}: Add {C}."
RIDER_MANA = 1  # ability index of the restricted, uncounterable half


def green(n: int = 1) -> Requirement:
    """A requirement for ``n`` green pips and nothing else."""
    colored = [0] * 6
    colored[SYMBOL_INDEX["G"]] = n
    return Requirement(colored=tuple(colored))


class TestThePipCarriesIt:
    def test_a_pip_defaults_to_no_rider(self):
        assert Pip().uncounterable is False
        assert Pip(source=7).uncounterable is False

    def test_spending_a_plain_pool_reports_nothing(self):
        pool = ManaPool()
        pool.add("G", 1, source=1)
        assert pool.spend(green()).uncounterable is False

    def test_spending_a_rider_pip_reports_it(self):
        pool = ManaPool()
        pool.add("G", 1, source=1, uncounterable=True)
        assert pool.spend(green()).uncounterable is True

    def test_any_pip_is_enough(self):
        """"That spell can't be countered" is about the spell, not about every
        pip that paid for it -- a two-mana spell paid half with Cavern mana is
        still uncounterable."""
        pool = ManaPool()
        pool.add("G", 1, source=1, uncounterable=True)
        pool.add("G", 1, source=2)
        assert pool.spend(green(2)).uncounterable is True

    def test_the_rider_does_not_leak_to_the_next_payment(self):
        """The wearing-off. Each payment reports only the pips it consumed."""
        pool = ManaPool()
        pool.add("G", 1, source=1, uncounterable=True)
        pool.add("G", 1, source=2)
        assert pool.spend(green()).uncounterable is False, "newest first: the plain pip"
        assert pool.spend(green()).uncounterable is True, "then the Cavern's"


class TestOneCardTwoAbilities:
    """The case that makes a per-permanent flag wrong."""

    def board(self, builder):
        game = builder(players=2).battlefield(0, [CAVERN]).build(advance=False)
        from tests.conftest import only_oid

        return game, only_oid(game, CAVERN)

    def test_the_restricted_ability_makes_rider_mana(self, builder):
        game, cavern = self.board(builder)
        activate_mana_ability(game.state, cavern, RIDER_MANA, 0)
        pool = game.state.players[0].mana_pool
        assert any(pip.uncounterable for row in pool.tags for pip in row)

    def test_the_plain_ability_on_the_same_permanent_does_not(self, builder):
        """The whole argument for putting the rider on the pip.

        Same card, same permanent, other ability -- and the mana must be
        ordinary.
        """
        game, cavern = self.board(builder)
        activate_mana_ability(game.state, cavern, PLAIN_MANA, 0)
        pool = game.state.players[0].mana_pool
        assert not any(pip.uncounterable for row in pool.tags for pip in row)

    def test_both_pips_keep_their_own_answer(self, builder):
        """Tapped for one and then the other -- the pool holds one of each.

        Nothing about the permanent can tell them apart; only the pips can.
        """
        game, cavern = self.board(builder)
        activate_mana_ability(game.state, cavern, PLAIN_MANA, 0)
        game.state.objects[cavern].tapped = False
        activate_mana_ability(game.state, cavern, RIDER_MANA, 0)
        riders = [pip.uncounterable for row in game.state.players[0].mana_pool.tags for pip in row]
        assert sorted(riders) == [False, True]


class TestTheLoaderPlacesTheRider:
    def _ability(self, **extra) -> CardModel:
        ability = {
            "kind": "activated",
            "text": "{T}: Add {G}.",
            "cost": {"tap": True},
            "effects": [{"op": "add_mana", "mana": "{G}"}],
            **extra,
        }
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "{T}: Add {G}.",
                "types": ["Land"],
                "abilities": [ability],
            }
        )

    def test_it_loads_on_a_mana_ability(self):
        compile_card(self._ability(is_mana_ability=True, mana_uncounterable=True))

    def test_it_is_refused_on_anything_else(self):
        """It rides the mana, so on an ability that makes none it would load and
        never be read -- a card printing "that spell can't be countered" that
        does not."""
        with pytest.raises(DslError, match="mana_uncounterable"):
            compile_card(self._ability(mana_uncounterable=True))
