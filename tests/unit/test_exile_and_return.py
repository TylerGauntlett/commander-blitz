"""Joshua, Phoenix's Dominant — "Exile Joshua, then return it to the battlefield
**transformed under its owner's control**."

    {3}{R}{W}, {T}: Exile Joshua, then return it to the battlefield transformed
    under its owner's control. Activate only as a sorcery.

The Final Fantasy "Dominant" cycle prints this line on both faces, and the back
prints it the other way round — "Exile Phoenix, then return it to the
battlefield **(front face up)**". So `face` is written out rather than inferred:
an op that only ever flipped would say the same thing twice, and be silently
wrong on one of them.

**Not `transform`.** That turns the permanent over *in place*: it never changes
zones, so it keeps its counters, its Auras and its summoning sickness, fires no
leaves-the-battlefield trigger and no enters trigger, and stays under whoever
controls it. Every one of those is a difference this card prints the other way,
and together they make a materially stronger and differently-timed permanent.
`t_turner` is that card, and the assertions here are measured against it.

What comes back is a **new object** (400.7): summoning sick, no counters, no
attachments, and under its **owner's** control — the clause that makes this a
removal answer for a permanent somebody has stolen.

The face is passed **into** the move rather than set after it, twice over:
`reset_permanent_state` clears `transformed` on the way in, and the arriving
face is what every enters-replacement and enters-trigger must see. The back of
Joshua is a Saga whose lore counter is a replacement, so a permanent that turned
over one line later would already have entered as something else.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from tests.conftest import only_oid

FLIPPER = "t_dominant"
FLIPPED = "t_dominant_back"
TURNER = "t_inplace"


def board(builder, card: str = FLIPPER):
    return (
        builder(players=2)
        .battlefield(0, [card])
        .battlefield(0, ["mountain"] * 4)
        .hand(0, ["forest"])
        .library(0, ["forest"] * 10)
        .build(advance=False)
    )


def activate(game, card: str, index: int = 0, *, oid: int | None = None):
    """Run the permanent's ability directly, then settle the triggers.

    ``oid`` names the permanent when its face has already turned: `only_oid`
    finds a permanent by its `def_id`, which stays the front face's id whichever
    way up the card is.
    """
    state = game.state
    if oid is None:
        oid = only_oid(game, card)
    ctx = EffectContext(state=state, controller=0, source_oid=oid)
    gen = execute(ctx, state.card_of(state.objects[oid]).abilities[index].effects)
    try:
        while True:
            next(gen)
    except StopIteration:
        pass
    game._advance()
    for _ in range(20):
        if not state.stack and game.pending() is None:
            break
        actions = game.legal_actions()
        if not actions:
            break
        game.apply(actions[0])
    return game, oid


def face(game, oid: int) -> str:
    return game.state.card_of(game.state.objects[oid]).id


class TestItComesBackTransformed:
    def test_the_permanent_shows_the_back_face(self, builder):
        game, oid = activate(board(builder), FLIPPER)
        assert face(game, oid) == FLIPPED

    def test_it_is_on_the_battlefield(self, builder):
        game, oid = activate(board(builder), FLIPPER)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_the_back_face_is_a_four_four(self, builder):
        from automtg.engine.characteristics import chars

        game, oid = activate(board(builder), FLIPPER)
        assert (chars(game.state, oid).power, chars(game.state, oid).toughness) == (4, 4)

    def test_the_other_direction_turns_it_back(self, builder):
        """"…(front face up)", the same op on the other face."""
        game, oid = activate(board(builder), FLIPPER)
        activate(game, FLIPPED, index=1, oid=oid)
        assert face(game, oid) == FLIPPER


class TestItIsANewObject:
    def test_its_enters_trigger_fires(self, builder):
        """A `transform` in place fires nothing -- the permanent never left."""
        game = board(builder)
        before = game.state.players[0].life
        activate(game, FLIPPER)
        assert game.state.players[0].life == before + 3

    def test_the_counterfactual_fires_nothing(self, builder):
        game = board(builder, TURNER)
        before = game.state.players[0].life
        activate(game, TURNER)
        assert game.state.players[0].life == before

    def test_its_counters_are_gone(self, builder):
        game = board(builder)
        oid = only_oid(game, FLIPPER)
        game.state.objects[oid].add_counter("+1/+1", 2)
        activate(game, FLIPPER)
        assert game.state.objects[oid].counter("+1/+1") == 0

    def test_the_counterfactual_keeps_them(self, builder):
        game = board(builder, TURNER)
        oid = only_oid(game, TURNER)
        game.state.objects[oid].add_counter("+1/+1", 2)
        activate(game, TURNER)
        assert game.state.objects[oid].counter("+1/+1") == 2

    def test_it_is_summoning_sick_again(self, builder):
        game = board(builder)
        oid = only_oid(game, FLIPPER)
        game.state.objects[oid].entered_turn = game.state.turn - 5
        turn = game.state.turn
        activate(game, FLIPPER)
        assert game.state.objects[oid].entered_turn == turn


class TestUnderItsOwnersControl:
    def test_a_stolen_permanent_goes_home(self, builder):
        """The clause that makes this a removal answer, and the one `transform`
        cannot say at all: it never changes zones, so control never resets."""
        game = board(builder)
        oid = only_oid(game, FLIPPER)
        game.state.objects[oid].controller = 1
        activate(game, FLIPPER)
        assert game.state.objects[oid].controller == 0
        assert game.state.objects[oid].owner == 0

    def test_the_counterfactual_leaves_it_stolen(self, builder):
        game = board(builder, TURNER)
        oid = only_oid(game, TURNER)
        game.state.objects[oid].controller = 1
        activate(game, TURNER)
        assert game.state.objects[oid].controller == 1


class TestTheLoaderRequiresTheFace:
    def _card(self, **effect):
        from automtg.cards.schema import CardModel

        return CardModel.model_validate(
            {
                "id": "t_bad_flip",
                "name": "Test Bad Flip",
                "oracle_text": "Exile it, then return it.",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "exile_and_return", **effect}],
            }
        )

    def test_a_missing_face_is_refused(self):
        """Defaulted to "turn it over" it reads correctly on a card's front and
        silently wrongly on its back, where the sentence turns it the other
        way -- and both faces of the cycle print one."""
        from automtg.cards.loader import compile_card
        from automtg.engine.errors import DslError

        with pytest.raises(DslError, match="'front' or 'back'"):
            compile_card(self._card(objects={"self_only": True}), source="test")

    def test_a_misspelled_face_is_refused(self):
        from automtg.cards.loader import compile_card
        from automtg.engine.errors import DslError

        with pytest.raises(DslError, match="'front' or 'back'"):
            compile_card(
                self._card(objects={"self_only": True}, face="transformed"),
                source="test",
            )

    def test_nothing_to_exile_is_refused(self):
        from automtg.cards.loader import compile_card
        from automtg.engine.errors import DslError

        with pytest.raises(DslError, match="nothing to exile"):
            compile_card(self._card(face="back"), source="test")
