"""Looking at more cards each time you surveil -- the `replace_surveil` static.

    Enhanced Surveillance -- "You may look at an additional two cards each time
    you surveil."

Surveil (701.25a) is a keyword action with no primitive beneath it, so the
`surveil` op is the one place its number lives, and the static is read there.
What would be wrong without each piece:

- **The extra cards are the same surveil.** A `surveils` trigger that surveils
  2 is the near miss: it is a second surveil after the first, so "whenever you
  surveil" would fire twice and the two looks could not be binned by one
  choice. Here one SURVEILLED fires and its `looked` counts the extra cards.
- **"You may" is asked before looking**, one yes/no per static, of the
  surveiller. Declined, the surveil is the printed number.
- **Two statics add up**: each is its own choice of two more cards.
- **Surveil 0 is no surveil** (701.25c) and is not enlarged into one.

Enhanced Surveillance is the witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.player_statics import surveil_additions
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

SURVEILLANCE = "enhanced_surveillance"
BEAR = "t_bear"


def position(builder, *, mine=(SURVEILLANCE,), theirs=(), library=10):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs) or [BEAR])
        .library(0, [BEAR] * library)
        .library(1, [BEAR] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def surveil(game, *, amount=1, player="you", take=True, bin_all=False):
    """Resolve one surveil outside any spell; returns the decisions it asked.

    Every "may" is answered ``take``; the surveil itself keeps every card on
    top unless ``bin_all``.
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    spec = {"op": "surveil", "amount": {"const": amount}, "player": player}
    gen = OPS["surveil"](ctx, spec)
    asked = []
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        if decision.kind is DecisionKind.MAY:
            send = [0 if take else 1]
        else:
            send = list(range(decision.max_count)) if bin_all else []


def surveils(game) -> list:
    return [e for e in game.state.events if e.type == EventType.SURVEILLED]


class TestTheSurveilIsEnlarged:
    def test_taking_the_extra_cards_looks_at_two_more(self, builder):
        game = position(builder)
        asked = surveil(game, amount=1)
        may, look = asked
        assert may.kind is DecisionKind.MAY and may.player == 0
        assert look.max_count == 3, "surveil 1 plus two should offer three cards"
        (event,) = surveils(game)
        assert event.data["looked"] == 3

    def test_the_extra_cards_take_the_same_choice(self, builder):
        """701.25a: one surveil -- the extra cards can be binned with the rest."""
        game = position(builder)
        surveil(game, amount=1, bin_all=True)
        assert len(game.state.players[0].graveyard) == 3
        (event,) = surveils(game)
        assert (event.data["looked"], event.data["binned"]) == (3, 3)

    def test_declining_is_the_printed_number(self, builder):
        game = position(builder)
        may, look = surveil(game, amount=2, take=False)
        assert may.kind is DecisionKind.MAY
        assert look.max_count == 2
        (event,) = surveils(game)
        assert event.data["looked"] == 2

    def test_without_the_static_nothing_is_asked(self, builder):
        """The pair that makes the tests above mean anything."""
        game = position(builder, mine=(BEAR,))
        (look,) = surveil(game, amount=1)
        assert look.max_count == 1


class TestWhoseSurveil:
    def test_an_opponents_surveil_is_untouched(self, builder):
        """"Each time **you** surveil."""
        game = position(builder)
        (look,) = surveil(game, amount=1, player="each_opponent")
        assert look.player == 1 and look.max_count == 1

    def test_the_opponents_copy_enlarges_their_surveil_not_mine(self, builder):
        game = position(builder, mine=(BEAR,), theirs=(SURVEILLANCE,))
        (look,) = surveil(game, amount=1)
        assert look.max_count == 1
        may, look = surveil(game, amount=1, player="each_opponent")
        assert may.player == 1, "the surveiller is the one asked"
        assert look.max_count == 3


class TestSeveralAddUp:
    def test_two_statics_are_two_choices_of_two(self, builder):
        game = position(builder, mine=(SURVEILLANCE, SURVEILLANCE))
        asked = surveil(game, amount=1)
        assert [d.kind for d in asked[:2]] == [DecisionKind.MAY, DecisionKind.MAY]
        assert asked[2].max_count == 5
        (event,) = surveils(game)
        assert event.data["looked"] == 5
        assert len(surveils(game)) == 1, "still one surveil"


class TestTheBoundaries:
    def test_surveil_zero_is_not_enlarged(self, builder):
        """701.25c: surveil 0 is no surveil, so there is nothing to add to."""
        game = position(builder)
        assert surveil(game, amount=0) == []
        assert surveils(game) == []

    def test_a_short_library_asks_nothing_it_cannot_change(self, builder):
        game = position(builder, library=1)
        (look,) = surveil(game, amount=1)
        assert look.max_count == 1
        assert surveils(game)[0].data["looked"] == 1

    def test_a_library_between_looks_at_what_there_is(self, builder):
        game = position(builder, library=2)
        may, look = surveil(game, amount=1)
        assert may.kind is DecisionKind.MAY, "a third card to see is worth asking about"
        assert look.max_count == 2
        assert surveils(game)[0].data["looked"] == 2

    def test_the_static_ends_when_its_source_leaves(self, builder):
        game = position(builder)
        assert len(surveil_additions(game.state, 0)) == 1
        move_object(game.state, only_oid(game, SURVEILLANCE), Zone.GRAVEYARD)
        assert surveil_additions(game.state, 0) == []


def _model(**ability):
    base = {
        "kind": "static",
        "text": "You may look at an additional two cards each time you surveil.",
        "effect": "replace_surveil",
        "affects_player": "you",
        "surveil_addend": 2,
        "surveil_optional": True,
    }
    base.update(ability)
    return CardModel.model_validate(
        {
            "id": "t_probe",
            "name": "Probe",
            "oracle_text": base["text"],
            "mana_cost": "{1}{U}",
            "types": ["Enchantment"],
            "abilities": [base],
        }
    )


class TestLoadTimeGuards:
    def test_an_addend_is_required(self):
        with pytest.raises(DslError, match="needs 'surveil_addend'"):
            compile_card(_model(surveil_addend=None))

    @pytest.mark.parametrize("value", [0, -1])
    def test_an_addend_below_one_is_refused(self, value):
        with pytest.raises(DslError, match="must be 1 or more"):
            compile_card(_model(surveil_addend=value))

    def test_affects_is_refused(self):
        with pytest.raises(DslError, match="no 'affects' or 'amount'"):
            compile_card(_model(affects={"types": ["Creature"]}))

    @pytest.mark.parametrize("key", [{"surveil_addend": 2}, {"surveil_optional": True}])
    def test_the_keys_are_refused_on_another_static(self, key):
        with pytest.raises(DslError, match="only mean anything on a replace_surveil"):
            compile_card(
                _model(
                    **{
                        "effect": "no_hand_limit",
                        "text": "You have no maximum hand size.",
                        "surveil_addend": None,
                        "surveil_optional": False,
                        **key,
                    }
                )
            )

    def test_the_card_loads(self):
        static = compile_card(_model()).abilities[0].static
        assert (static["surveil_addend"], static["surveil_optional"]) == (2, True)
