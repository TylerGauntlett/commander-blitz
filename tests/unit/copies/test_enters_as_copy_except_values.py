"""The as-enters copy's exception, widened to the rest of 707.9b.

    "You may have this creature enter as a copy of a creature or planeswalker
    you control, except it enters with an additional +1/+1 counter on it if
    it's a creature, it enters with an additional loyalty counter on it if it's
    a planeswalker, and it isn't legendary."                  -- Spark Double

    "You may have Chameleon enter as a copy of a creature you control, except
    his name is Chameleon, Master of Disguise."
                                          -- Chameleon, Master of Disguise

Three things `self_enters_as_copy`'s ``except_`` could not say before, and each
has a near miss that is a different card:

**The counters are part of the replacement (614.1c), judged against the copy.**
`enters_with` puts them on in the same placement as everything else the
permanent enters with. Written as a `self_enters` trigger running
`add_counters`, Spark Double copying a 0/0-plus-counters creature would be seen
at its copied size first, and copying a planeswalker it would enter with its
copied loyalty and only later the extra one -- a window in which it could be
attacked down or `_planeswalker_deaths` could see the wrong number. The
condition reads the *copy*: a +1/+1 counter on a planeswalker copy, or a loyalty
counter on a creature copy, would be the wrong card.

**A planeswalker copy enters with the copied loyalty (306.5b, 614.12).** The
loyalty is the copied face's intrinsic "enters with", compiled by the loader as
a replacement on that face; without reading it the copy would enter with one
loyalty counter and die to the first activation that removed it.

**"…isn't legendary" and "…his name is…" are copiable values.** Both are written
into the copied face by `GameState.card_of`, so the legend rule (704.5j) sees a
nonlegendary Spark Double, and a Chameleon copying a legendary creature answers
to his own name and survives beside it. Renaming Spark Double instead, or
stripping Legendary from Chameleon, would dodge the legend rule for the wrong
reason.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, plus_one_counters
from tests.unit.copies.test_enters_as_copy import cast, name_of

SPARK = "t_eacx_spark"  # 0/0, the copy clause above
CHAMELEON = "t_eacx_chameleon"  # legendary 2/3, copy except his own name
BEAR = "t_bear"  # 2/2 vanilla
LEGEND = "t_legend"  # legendary 2/2
WALKER = "t_walker"  # legendary planeswalker, loyalty 4
OATH = "t_oath"  # each planeswalker you control enters with an additional loyalty


def position(builder, spell: str, mine=(), theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, [spell])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def supertypes(game, oid: int) -> set[str]:
    return {str(s) for s in chars(game.state, oid).supertypes}


def types(game, oid: int) -> set[str]:
    return {str(t) for t in chars(game.state, oid).types}


class TestSparkDoubleCopyingACreature:
    def test_it_is_the_copy_with_one_more_counter(self, builder):
        game = position(builder, SPARK, mine=[BEAR])
        cast(game, SPARK, copy_id=BEAR)
        oid = only_oid(game, SPARK, 0)
        assert name_of(game, oid) == "Test Bear"
        assert plus_one_counters(game, oid) == 1
        assert game.state.objects[oid].counter("loyalty") == 0
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (3, 3)

    def test_a_copied_legend_survives_beside_its_original(self, builder):
        """The legend rule reads the copy's supertypes, and there are none."""
        game = position(builder, SPARK, mine=[LEGEND])
        cast(game, SPARK, copy_id=LEGEND)
        oid = only_oid(game, SPARK, 0)
        legend = only_oid(game, LEGEND, 0)
        assert name_of(game, oid) == name_of(game, legend) == "Test Legend"
        assert "Legendary" not in supertypes(game, oid)
        assert "Legendary" in supertypes(game, legend), "the original keeps it"

    def test_the_pool_is_only_what_you_control(self, builder):
        """"…a creature or planeswalker **you control**": the opponent's Bear
        is no choice, so nothing is asked and the 0/0 dies (704.5f)."""
        game = position(builder, SPARK, theirs=[BEAR])
        cast(game, SPARK)
        assert not any(
            game.state.objects[o].def_id == SPARK for o in game.state.battlefield
        )

    def test_declined_it_is_a_dead_0_0(self, builder):
        game = position(builder, SPARK, mine=[BEAR])
        cast(game, SPARK, say_yes=False)
        assert not any(
            game.state.objects[o].def_id == SPARK for o in game.state.battlefield
        )

    def test_the_exception_does_not_outlive_the_object(self, builder):
        game = position(builder, SPARK, mine=[LEGEND])
        cast(game, SPARK, copy_id=LEGEND)
        oid = only_oid(game, SPARK, 0)
        move_object(game.state, oid, Zone.HAND)
        obj = game.state.objects[oid]
        assert obj.copying is None and obj.copying_remove_supertypes is None


class TestSparkDoubleCopyingAPlaneswalker:
    def test_it_enters_with_the_copied_loyalty_plus_one(self, builder):
        game = position(builder, SPARK, mine=[WALKER])
        cast(game, SPARK, copy_id=WALKER)
        oid = only_oid(game, SPARK, 0)
        assert name_of(game, oid) == "Test Walker"
        assert "Planeswalker" in types(game, oid)
        assert game.state.objects[oid].counter("loyalty") == 5
        assert plus_one_counters(game, oid) == 0, "not a creature, so no +1/+1"

    def test_two_walkers_of_one_name_both_stay(self, builder):
        game = position(builder, SPARK, mine=[WALKER])
        cast(game, SPARK, copy_id=WALKER)
        oid = only_oid(game, SPARK, 0)
        assert "Legendary" not in supertypes(game, oid)
        assert game.state.objects[only_oid(game, WALKER, 0)].counter("loyalty") == 4

    def test_the_extra_loyalty_is_one_placement_with_the_rest(self, builder):
        """Oath of Gideon's additional counter joins the copied four and the
        exception's one: 4 + 1 + 1, put on together (122.6)."""
        game = position(builder, SPARK, mine=[WALKER, OATH])
        cast(game, SPARK, copy_id=WALKER)
        assert game.state.objects[only_oid(game, SPARK, 0)].counter("loyalty") == 6


class TestChameleonKeepsHisName:
    def test_he_copies_everything_but_the_name(self, builder):
        game = position(builder, CHAMELEON, mine=[BEAR])
        cast(game, CHAMELEON, copy_id=BEAR)
        oid = only_oid(game, CHAMELEON, 0)
        assert name_of(game, oid) == "Test Chameleon, Master of Disguise"
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 2)
        assert "Legendary" not in supertypes(game, oid), "the Bear's supertypes"

    def test_copying_a_legend_he_survives_beside_it(self, builder):
        """Legendary, copied from the Legend -- but with another name, so the
        legend rule pairs nothing."""
        game = position(builder, CHAMELEON, mine=[LEGEND])
        cast(game, CHAMELEON, copy_id=LEGEND)
        oid = only_oid(game, CHAMELEON, 0)
        assert "Legendary" in supertypes(game, oid)
        assert name_of(game, oid) == "Test Chameleon, Master of Disguise"
        assert only_oid(game, LEGEND, 0)

    def test_declined_he_is_himself(self, builder):
        game = position(builder, CHAMELEON, mine=[BEAR])
        cast(game, CHAMELEON, say_yes=False)
        oid = only_oid(game, CHAMELEON, 0)
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 3)
        assert game.state.objects[oid].copying_name is None


class TestTheLoaderChecksIt:
    def _card(self, except_):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "You may have this enter as a copy of a creature.",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 0,
                "toughness": 0,
                "replacements": [
                    {
                        "event": "self_enters_as_copy",
                        "copying": {"zone": "battlefield", "types": ["Creature"]},
                        "except_": except_,
                    }
                ],
            }
        )

    def test_the_whole_exception_loads(self):
        compile_card(
            self._card(
                {
                    "name": "X",
                    "remove_supertypes": ["Legendary"],
                    "enters_with": [
                        {
                            "counter": "+1/+1",
                            "condition": {"exists": {"self_only": True, "types": ["Creature"]}},
                        }
                    ],
                }
            )
        )

    @pytest.mark.parametrize(
        ("except_", "match"),
        [
            ({"name": ""}, "non-empty string"),
            ({"remove_supertypes": ["Legend"]}, "unknown supertype"),
            ({"remove_supertypes": []}, "non-empty list"),
            ({"enters_with": []}, "non-empty list"),
            ({"enters_with": [{"amount": 1}]}, "needs a 'counter'"),
            ({"enters_with": [{"counter": "+1/+1", "if_type": "Creature"}]}, "unsupported keys"),
            ({"enters_with": [{"counter": "+1/+1", "condition": {"nope": 1}}]}, "condition"),
            ({}, "empty exception"),
        ],
    )
    def test_a_malformed_exception_is_refused(self, except_, match):
        with pytest.raises(DslError, match=match):
            compile_card(self._card(except_))
