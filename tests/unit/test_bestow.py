"""Bestow — an alternative cost that changes what the spell *points at*.

    "Bestow {5}{W} (If you cast this card for its bestow cost, it's an Aura
    spell with enchant creature. It becomes a creature again if it's not
    attached to a creature.)
     Enchanted creature gets +2/+2."

The census filed bestow beside adventure and aftermath under "a second castable
face", and it is not one. A second face is two spells; bestow is **one** spell
that lands as two different permanents depending on what happens to the thing it
enchanted. So the mechanism is not `card_of` at all — it is `chars`.

Bestow is the seventh alternative cost in the engine and the first that is not
only a price. Every other one — evoke, prowl, spectacle, emerge, flashback,
foretell, morph — changes what the spell costs and leaves what it targets alone.
702.103a makes a bestowed creature "an Aura spell with **enchant creature**", so
the target comes from the rule: `BESTOW_TARGET`, and no bestow card writes one.

The type change is a **pipeline input**, not a layer over another layer.
`attached_to` is a field the `attach` primitive writes and no static can change,
which is the same argument `is_attached` made for reconfigure — so switching the
type line on it cannot make one static depend on another's output.

And the state-based action that bins an Aura enchanting nothing reads the
**printed** card, which is a Creature, so it never sees a bestowed permanent.
That is not luck: 702.103e is exactly "it becomes a creature again" rather than
"it is put into the graveyard", and reading the printed face is what makes the
two agree.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.zones import destroy
from tests.conftest import only_oid, pass_until

PLAINS = "plains"
SPIRIT = "t_bestower"  # {2}{W} 2/2, bestow {5}{W}, enchanted creature +2/+2
BEAR = "t_bear"


def position(builder, lands: int = 8, creatures: int = 1):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .battlefield(0, [BEAR] * creatures)
        .hand(0, [SPIRIT])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )


def cast_lines(game) -> list[str]:
    return [a.base_label or "" for a in game.legal_actions() if a.kind is ActionKind.CAST]


def bestow_onto(game, bear: int) -> int:
    """Cast the Spirit for its bestow cost, enchanting `bear`. Returns its oid."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.bestowed
        and any(ref.id == bear for ref in a.targets)
    )
    spirit = action.source
    game.apply(action)
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)
    return spirit


class TestTheTwoLines:
    def test_both_are_offered_with_the_mana_for_both(self, builder):
        game = position(builder)
        assert sorted(set(cast_lines(game))) == [
            "Cast Test Bestower",
            "Cast Test Bestower (bestowed)",
        ]

    def test_only_the_creature_line_appears_without_the_bestow_cost(self, builder):
        game = position(builder, lands=3)
        assert set(cast_lines(game)) == {"Cast Test Bestower"}

    def test_the_creature_line_carries_no_target(self, builder):
        """A creature spell targets nothing; the bestowed one has to."""
        game = position(builder)
        plain = next(
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and not a.bestowed
        )
        assert plain.targets == ()

    def test_the_bestowed_line_targets_a_creature(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        bestowed = [
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.bestowed
        ]
        assert [ref.id for a in bestowed for ref in a.targets] == [bear]

    def test_one_line_per_creature_on_the_board(self, builder):
        """`BESTOW_TARGET` goes through the ordinary target enumeration."""
        game = position(builder, creatures=3)
        bestowed = [
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.bestowed
        ]
        assert len(bestowed) == 3


class TestWhatItLandsAs:
    def test_it_arrives_attached(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        spirit = bestow_onto(game, bear)

        assert game.state.objects[spirit].zone is Zone.BATTLEFIELD
        assert game.state.objects[spirit].attached_to == bear

    def test_it_is_an_aura_and_not_a_creature(self, builder):
        """702.103b, and everything that reads `chars` gets it at once."""
        game = position(builder)
        bear = only_oid(game, BEAR)
        spirit = bestow_onto(game, bear)

        c = chars(game.state, spirit)
        assert "Creature" not in c.types
        assert "Enchantment" in c.types
        assert "Aura" in c.subtypes

    def test_the_buff_reaches_the_enchanted_creature(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        bestow_onto(game, bear)

        c = chars(game.state, bear)
        assert (c.power, c.toughness) == (4, 4), "a 2/2 Bear with +2/+2"

    def test_cast_as_a_creature_it_is_an_ordinary_creature(self, builder):
        game = position(builder)
        action = next(
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and not a.bestowed
        )
        spirit = action.source
        game.apply(action)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        c = chars(game.state, spirit)
        assert "Creature" in c.types
        assert "Aura" not in c.subtypes
        assert (c.power, c.toughness) == (2, 2)
        assert game.state.objects[spirit].attached_to is None


class TestItBecomesACreatureAgain:
    def test_the_enchanted_creature_dying_leaves_it_on_the_battlefield(self, builder):
        """702.103e. An ordinary Aura would be in the graveyard here."""
        game = position(builder)
        bear = only_oid(game, BEAR)
        spirit = bestow_onto(game, bear)

        destroy(game.state, bear)

        assert game.state.objects[spirit].zone is Zone.BATTLEFIELD

    def test_and_it_is_a_creature_once_more(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        spirit = bestow_onto(game, bear)

        destroy(game.state, bear)

        c = chars(game.state, spirit)
        assert "Creature" in c.types
        assert "Aura" not in c.subtypes
        assert (c.power, c.toughness) == (2, 2)

    def test_the_link_is_gone_with_it(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        spirit = bestow_onto(game, bear)

        destroy(game.state, bear)

        assert game.state.objects[spirit].attached_to is None


class TestTheLoaderGuards:
    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_bestow_probe",
            "name": "Bestow Probe",
            "mana_cost": "{2}{W}",
            "types": ["Creature"],
            "power": 2,
            "toughness": 2,
            "bestow": "{5}{W}",
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_a_creature_with_bestow_loads(self):
        compile_card(self._card())

    def test_a_noncreature_with_bestow_is_refused(self):
        """There would be nothing for it to "become a creature again" as."""
        with pytest.raises(DslError, match="only on creature cards"):
            compile_card(
                self._card(types=["Enchantment"], power=None, toughness=None)
            )

    def test_a_card_that_is_already_an_aura_is_refused(self):
        with pytest.raises(DslError, match="already an Aura"):
            compile_card(self._card(types=["Creature", "Enchantment"], subtypes=["Aura"]))
