"""`search_library`'s ``may_destination`` and ``may_destination_if``: a
conditional "you may put that card onto the battlefield" asked about the card a
search found.

    Scholar of New Horizons — "{T}, Remove a counter from a permanent you
    control: Search your library for a Plains card and reveal it. If an
    opponent controls more lands than you, you may put that card onto the
    battlefield tapped. If you don't put the card onto the battlefield, put it
    into your hand. Then shuffle."

The choice is about the card **already found** (701.19): the player picks the
Plains, reveals it and then decides. Both near misses are different cards.
Wrapping the search in `if` + `may` asks battlefield-or-hand before anything is
found, and searching to the hand and then `put_onto_battlefield` moves the card
twice, through the hand. `destination_if` cannot say it either: its branches
match the found card's printed face and never ask the player.

The condition gates the offer. While no opponent controls more lands than you
the "you may" never arises: nothing is asked and the card goes to the hand. And
"then shuffle" comes last, after the card has left the library.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import battlefield_ids, hand_ids, library_ids, only_oid

PLAINS = "plains"
ISLAND = "island"
FOREST = "forest"

MORE_LANDS = {
    "cmp": ">",
    "left": {
        "max_count_of": {
            "player": "each_opponent",
            "objects": {"types": ["Land"], "zone": "battlefield"},
        }
    },
    "right": {"lands_you_control": True},
}

SCHOLAR = {
    "op": "search_library",
    "selector": {"subtypes": ["Plains"]},
    "reveal": True,
    "may_destination": "battlefield",
    "may_destination_if": MORE_LANDS,
    "tapped": True,
    "destination": "hand",
    "as": "found",
}


def position(builder, *, mine=(), theirs=(), library=()):
    """Player 0 with ``mine`` and an exact ``library``; player 1 with ``theirs``."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, list(library))
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, effects, *, yes: bool):
    """Resolve ``effects`` for player 0, answering the may with ``yes``.

    The search takes its first offered card. Returns the decisions asked and
    the context.
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    gen = execute(ctx, effects)
    asked = []
    answer = None
    while True:
        try:
            decision = gen.send(answer)
        except StopIteration:
            break
        asked.append(decision)
        answer = [0 if yes else 1] if decision.kind is DecisionKind.MAY else [0]
    sba.run(game.state)
    return asked, ctx


def mays(asked) -> list:
    return [d for d in asked if d.kind is DecisionKind.MAY]


def behind(builder, *, library=(ISLAND, PLAINS, FOREST)):
    """An opponent with more lands than player 0, so the offer is made."""
    return position(builder, mine=[ISLAND], theirs=[FOREST, FOREST], library=library)


class TestWhenAnOpponentHasMoreLands:
    def test_yes_puts_it_onto_the_battlefield_tapped(self, builder):
        game = behind(builder)

        asked, _ = run(game, [SCHOLAR], yes=True)

        assert len(mays(asked)) == 1
        assert PLAINS in battlefield_ids(game, 0)
        assert game.state.objects[only_oid(game, PLAINS, 0)].tapped
        assert PLAINS not in hand_ids(game, 0)

    def test_no_puts_it_into_your_hand(self, builder):
        game = behind(builder)

        asked, _ = run(game, [SCHOLAR], yes=False)

        assert len(mays(asked)) == 1
        assert PLAINS in hand_ids(game, 0)
        assert PLAINS not in battlefield_ids(game, 0)

    def test_the_question_comes_after_the_card_is_found(self, builder):
        game = behind(builder)

        asked, _ = run(game, [SCHOLAR], yes=False)

        kinds = [d.kind for d in asked]
        assert kinds.index(DecisionKind.MAY) > 0, "the search is chosen first"
        assert "Plains" in mays(asked)[0].prompt

    @pytest.mark.parametrize("yes", [True, False])
    def test_as_binds_the_card_either_way(self, builder, yes):
        game = behind(builder)

        _, ctx = run(game, [SCHOLAR], yes=yes)

        (found,) = ctx.bindings["found"]
        assert game.state.objects[found].def_id == PLAINS


class TestWhenNoOpponentHasMoreLands:
    @pytest.mark.parametrize("theirs", [[], [FOREST]])
    def test_nothing_is_asked_and_it_goes_to_your_hand(self, builder, theirs):
        """Equal is not more: one land each still sends the Plains to hand."""
        game = position(builder, mine=[ISLAND], theirs=theirs, library=[PLAINS, FOREST])

        asked, _ = run(game, [SCHOLAR], yes=True)

        assert mays(asked) == []
        assert PLAINS in hand_ids(game, 0)
        assert PLAINS not in battlefield_ids(game, 0)


class TestThenShuffle:
    @pytest.mark.parametrize("yes", [True, False])
    def test_the_card_has_left_the_library(self, builder, yes):
        game = behind(builder)

        run(game, [SCHOLAR], yes=yes)

        assert sorted(library_ids(game, 0)) == sorted([ISLAND, FOREST])

    def test_no_plains_asks_nothing(self, builder):
        game = behind(builder, library=[ISLAND, FOREST])

        asked, ctx = run(game, [SCHOLAR], yes=True)

        assert mays(asked) == []
        assert ctx.bindings["found"] == []


class TestUngated:
    def test_without_a_condition_the_offer_is_always_made(self, builder):
        game = position(builder, mine=[ISLAND], library=[PLAINS])
        always = {k: v for k, v in SCHOLAR.items() if k != "may_destination_if"}

        asked, _ = run(game, [always], yes=True)

        assert len(mays(asked)) == 1
        assert PLAINS in battlefield_ids(game, 0)


class TestTheLoaderRefuses:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_search_may_probe",
                "name": "Search May Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_printed_shape_loads(self):
        compile_card(self._card(SCHOLAR))

    def test_a_may_to_anywhere_but_the_battlefield(self):
        with pytest.raises(DslError, match="unknown search_library may_destination"):
            compile_card(self._card({**SCHOLAR, "may_destination": "graveyard"}))

    def test_a_may_to_where_it_goes_anyway(self):
        with pytest.raises(DslError, match="other than 'battlefield'"):
            compile_card(self._card({**SCHOLAR, "destination": "battlefield"}))

    def test_more_than_one_card(self):
        with pytest.raises(DslError, match="asks about one card"):
            compile_card(self._card({**SCHOLAR, "count": 2}))

    def test_beside_destination_if(self):
        branch = [{"selector": {"types": ["Land"]}, "to": "graveyard"}]
        with pytest.raises(DslError, match="not both"):
            compile_card(self._card({**SCHOLAR, "destination_if": branch}))

    def test_a_gate_without_an_offer(self):
        bare = {k: v for k, v in SCHOLAR.items() if k != "may_destination"}
        with pytest.raises(DslError, match="gates a 'may_destination'"):
            compile_card(self._card(bare))

    def test_a_malformed_gate(self):
        with pytest.raises(DslError, match="unknown condition keys"):
            compile_card(self._card({**SCHOLAR, "may_destination_if": {"bogus": 1}}))

    def test_on_an_op_that_never_asks(self):
        with pytest.raises(DslError, match="read only by reveal_until"):
            compile_card(
                self._card({"op": "draw", "amount": 1, "may_destination": "battlefield"})
            )
