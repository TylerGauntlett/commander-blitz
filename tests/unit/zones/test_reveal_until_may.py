"""`reveal_until`'s ``may_destination``: "you may put that card onto the
battlefield. If you don't, put it into your hand."

    Songbirds' Blessing — "Whenever enchanted creature attacks, reveal cards
    from the top of your library until you reveal an Aura card. You may put
    that card onto the battlefield. If you don't, put it into your hand. Put
    the rest on the bottom of your library in a random order."

The choice is about the card **in the library**. The near miss -- a
`reveal_until` to the hand followed by a `may` `put_onto_battlefield` -- moves
the card twice, through the hand (two zone changes, two sets of "leaves your
hand" and "enters" events), and bottoms the rest before the choice is made. So
the yes/no is asked inside the walk, after the reveal and before the rest goes
to the bottom.

"If you don't" is any outcome in which the card was not put onto the
battlefield. A yes for an Aura with nothing it could enchant stays in the
library under 303.4g -- and then the card was not put onto the battlefield, so
it goes to the fallback with a declined one rather than being bottomed among
"the rest".
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

AURA = "t_eb_aura"  # "Enchant creature"
BEAR = "t_bear"
ISLAND = "island"
FOREST = "forest"

SONGBIRDS = {
    "op": "reveal_until",
    "objects": {"subtypes": ["Aura"]},
    "may_destination": "battlefield",
    "destination": "hand",
    "as": "found",
}


def position(builder, *, mine=(), library=()):
    """Player 0's ``mine`` on the battlefield and exact ``library``, top first."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .library(0, list(library))
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, effects, *, yes: bool):
    """Resolve ``effects`` for player 0, answering the may with ``yes``.

    Any other question takes its first option. Returns the decisions asked and
    the context, whose bindings a test can read.
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


class TestYouMay:
    def test_yes_puts_it_onto_the_battlefield_from_the_library(self, builder):
        game = position(builder, mine=[BEAR], library=[ISLAND, AURA, FOREST])
        bear = only_oid(game, BEAR, 0)

        asked, _ = run(game, [SONGBIRDS], yes=True)

        assert len(mays(asked)) == 1
        assert AURA in battlefield_ids(game, 0)
        aura = only_oid(game, AURA, 0)
        assert game.state.objects[aura].attached_to == bear, "303.4f: it chose its host"
        assert AURA not in hand_ids(game, 0)

    def test_no_puts_it_into_your_hand(self, builder):
        game = position(builder, mine=[BEAR], library=[ISLAND, AURA, FOREST])

        asked, _ = run(game, [SONGBIRDS], yes=False)

        assert len(mays(asked)) == 1
        assert AURA in hand_ids(game, 0)
        assert AURA not in battlefield_ids(game, 0)

    def test_the_question_names_the_card(self, builder):
        game = position(builder, mine=[BEAR], library=[AURA])

        asked, _ = run(game, [SONGBIRDS], yes=False)

        name = game.state.card_of(game.state.objects[game.state.players[0].hand[0]]).name
        assert name in mays(asked)[0].prompt

    @pytest.mark.parametrize("yes", [True, False])
    def test_as_binds_the_card_either_way(self, builder, yes):
        game = position(builder, mine=[BEAR], library=[ISLAND, AURA])

        _, ctx = run(game, [SONGBIRDS], yes=yes)

        (found,) = ctx.bindings["found"]
        assert game.state.objects[found].def_id == AURA


class TestTheRest:
    @pytest.mark.parametrize("yes", [True, False])
    def test_the_rest_goes_to_the_bottom_and_the_card_is_not_among_it(self, builder, yes):
        game = position(builder, mine=[BEAR], library=[ISLAND, FOREST, AURA, BEAR])

        run(game, [SONGBIRDS], yes=yes)

        assert library_ids(game, 0)[0] == BEAR, "the scan stopped at the Aura"
        assert sorted(library_ids(game, 0)[1:]) == sorted([ISLAND, FOREST])
        assert AURA not in library_ids(game, 0)

    def test_no_match_asks_nothing_and_bottoms_everything(self, builder):
        game = position(builder, mine=[BEAR], library=[ISLAND, FOREST])

        asked, ctx = run(game, [SONGBIRDS], yes=True)

        assert mays(asked) == []
        assert sorted(library_ids(game, 0)) == sorted([ISLAND, FOREST])
        assert ctx.bindings["found"] == []


class TestIfYouDont:
    def test_an_aura_with_no_host_goes_to_your_hand(self, builder):
        """303.4g keeps it out of play; "if you don't" sends it to the hand."""
        game = position(builder, mine=[ISLAND], library=[FOREST, AURA])

        run(game, [SONGBIRDS], yes=True)

        assert AURA in hand_ids(game, 0)
        assert AURA not in library_ids(game, 0), "not left behind among the rest"
        assert AURA not in battlefield_ids(game)

    def test_tapped_is_the_battlefield_arrival(self, builder):
        game = position(builder, library=[FOREST])
        lands = {**SONGBIRDS, "objects": {"types": ["Land"]}, "tapped": True}

        run(game, [lands], yes=True)

        assert game.state.objects[only_oid(game, FOREST, 0)].tapped


class TestTheLoaderRefuses:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_reveal_until_may_probe",
                "name": "Reveal Until May Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_printed_shape_loads(self):
        compile_card(self._card(SONGBIRDS))
        compile_card(self._card({**SONGBIRDS, "tapped": True, "controller": "you"}))

    def test_a_may_to_anywhere_but_the_battlefield(self):
        with pytest.raises(DslError, match="unknown reveal_until may_destination"):
            compile_card(self._card({**SONGBIRDS, "may_destination": "graveyard"}))

    def test_a_may_to_where_it_goes_anyway(self):
        with pytest.raises(DslError, match="other than 'battlefield'"):
            compile_card(self._card({**SONGBIRDS, "destination": "battlefield"}))

    def test_an_amount(self):
        with pytest.raises(DslError, match="takes no 'amount'"):
            compile_card(self._card({**SONGBIRDS, "amount": {"const": 2}}))
