"""Offering (702.47): emerge with the fodder narrowed to one creature type.

The census routes it exactly right — "this is `emerge`, restricted by type" —
and the restriction was the only missing piece. Everything else offering needs
already shipped: `emerge` offers one cast line per sacrificeable creature and
reduces the price by that creature's mana value, and "any time you could cast
an instant" is the `flash` keyword.

So `emerge_subtype` is a qualifier on the emerge field rather than a field of
its own, because offering is not a second mechanism — it is the same one with a
narrower mouth.

The subtype is read off **derived** characteristics, not the printed line. A
changeling is every creature type, and a creature granted a type by an anthem
is legal fodder for the matching offering card. Reading the printed face would
refuse both, quietly, and those interactions are the only reason anyone plays
these cards together.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.primitives import add_subtypes
from tests.conftest import _default_answer, only_oid

OFFERING = "t_offering"  # {4}{R} 4/4 Goblin, Goblin offering, flash
GOBLIN = "t_goblin"  # {1}{R} 1/1 Goblin
BEAR = "t_bear"  # {1}{G} 2/2, not a Goblin


def position(builder, board=(GOBLIN,), lands=5):
    return (
        builder(players=2)
        .hand(0, [OFFERING])
        .battlefield(0, list(board))
        .battlefield(0, ["mountain"] * lands)
        .build()
    )


def offering_lines(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.emerge_oid is not None
    ]


def settle(game, limit: int = 40) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


class TestTheFodderIsNarrowed:
    def test_a_matching_creature_is_offered(self, builder):
        game = position(builder)
        (line,) = offering_lines(game)
        assert line.emerge_oid == only_oid(game, GOBLIN, 0)

    def test_a_creature_of_another_type_is_not(self, builder):
        """The whole of the restriction, and what emerge alone gets wrong."""
        game = position(builder, board=(BEAR,))
        assert offering_lines(game) == []

    def test_only_the_matching_one_is_offered(self, builder):
        game = position(builder, board=(GOBLIN, BEAR))
        (line,) = offering_lines(game)
        assert line.emerge_oid == only_oid(game, GOBLIN, 0)

    def test_the_printed_cost_is_still_offered(self, builder):
        game = position(builder, board=(BEAR,), lands=6)
        assert [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.emerge_oid is None
        ]


class TestItReadsDerivedSubtypes:
    def test_a_creature_given_the_type_becomes_legal_fodder(self, builder):
        """A bear made a Goblin is a Goblin. Reading the printed face would
        refuse it, and quietly."""
        game = position(builder, board=(BEAR,))
        assert offering_lines(game) == []
        add_subtypes(game.state, only_oid(game, BEAR, 0), ["Goblin"])
        game.state.bump_chars()
        (line,) = offering_lines(game)
        assert line.emerge_oid == only_oid(game, BEAR, 0)


class TestItStillEmerges:
    def test_the_sacrifice_pays_part_of_the_cost(self, builder):
        """Offering keeps emerge's arithmetic: the price drops by the
        sacrificed creature's mana value."""
        game = position(builder, lands=5)
        untapped = lambda: sum(  # noqa: E731
            1
            for o in game.state.battlefield_objects(0)
            if not o.tapped and "Land" in game.state.card_of(o).types
        )
        before = untapped()
        game.apply(offering_lines(game)[0])
        settle(game)
        # {4}{R} less the Goblin's mana value of 2 -> three mana.
        assert before - untapped() == 3

    def test_the_fodder_is_sacrificed(self, builder):
        game = position(builder)
        goblin = only_oid(game, GOBLIN, 0)
        game.apply(offering_lines(game)[0])
        settle(game)
        assert not game.state.objects[goblin].on_battlefield


class TestTheLoaderGuardsIt:
    def test_a_subtype_with_no_emerge_is_refused(self):
        """A narrowing with nothing to narrow: the card would look like an
        offering card and have no alternative cast line at all."""
        with pytest.raises(DslError, match="needs an 'emerge' cost"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{4}{R}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "emerge_subtype": "Goblin",
                    }
                )
            )

    def test_the_offering_card_compiles(self, registry):
        card = registry.get(OFFERING)
        assert card.emerge is not None
        assert card.emerge_subtype == "Goblin"

    def test_plain_emerge_still_takes_anything(self, registry):
        card = registry.get("t_emerger")
        assert card.emerge is not None
        assert card.emerge_subtype is None
