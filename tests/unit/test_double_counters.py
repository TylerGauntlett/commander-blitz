"""Doubling every kind of counter on a permanent.

    "When this creature enters, double the number of each kind of counter on
    any number of target permanents."                    -- Deepglow Skate

Nothing could say it. `add_counters` names one kind and the card names none;
`proliferate` adds *one* of each kind; `move_counters`' ``all_kinds`` takes them
from somewhere else. `double_counters` reads the kinds off each permanent at
resolution (122.1: any number of kinds) and puts that many more of each on.

It is a **placement**, through `add_counters`, and that is visible: Doubling
Season sees an effect putting two counters and doubles that, so two become six
(the Skate's ruling), and "whenever a counter is put on" triggers. A permanent
with no counters has nothing to double.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Step
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from tests.conftest import only_oid

BEAR = "t_rc_bear"
ROCK = "t_rc_rock"
SEASON = "t_rc_season"  # "a permanent you control", twice that many


def position(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def double(game, *oids: int, controller: int = 0) -> None:
    """Resolve ``double_counters`` aimed at ``oids`` as ``controller``."""
    ctx = EffectContext(
        state=game.state,
        controller=controller,
        targets={"t1": tuple(TargetRef.obj(oid) for oid in oids)},
    )
    gen = execute(ctx, [{"op": "double_counters", "objects": {"target": "t1"}}])
    for _ in gen:
        raise AssertionError("double_counters asked a question")


def counters(game, oid: int) -> dict[str, int]:
    return {k: v for k, v in game.state.objects[oid].counters.items() if v}


class TestEachKindIsDoubled:
    def test_every_kind_on_the_permanent(self, builder):
        game = position(builder, mine=[ROCK])
        oid = only_oid(game, ROCK)
        game.state.objects[oid].add_counter("charge", 3)
        game.state.objects[oid].add_counter("oil", 1)
        double(game, oid)
        assert counters(game, oid) == {"charge": 6, "oil": 2}

    def test_several_targets_each_by_their_own_count(self, builder):
        game = position(builder, mine=[BEAR], theirs=[ROCK])
        bear, rock = only_oid(game, BEAR), only_oid(game, ROCK)
        game.state.objects[bear].add_counter("+1/+1", 2)
        game.state.objects[rock].add_counter("charge", 1)
        double(game, bear, rock)
        assert counters(game, bear) == {"+1/+1": 4}
        assert counters(game, rock) == {"charge": 2}

    def test_no_counters_is_nothing_to_double(self, builder):
        game = position(builder, mine=[BEAR])
        oid = only_oid(game, BEAR)
        double(game, oid)
        assert counters(game, oid) == {}


class TestItIsAPlacement:
    def test_doubling_season_doubles_what_it_puts(self, builder):
        """Two counters, an effect putting two more, doubled to four: six."""
        game = position(builder, mine=[SEASON, BEAR])
        oid = only_oid(game, BEAR)
        game.state.objects[oid].add_counter("+1/+1", 2)
        double(game, oid)
        assert counters(game, oid) == {"+1/+1": 6}

    def test_counter_placed_fires(self, builder):
        game = position(builder, mine=[BEAR])
        oid = only_oid(game, BEAR)
        game.state.objects[oid].add_counter("+1/+1", 2)
        mark = len(game.state.events)
        double(game, oid)
        placed = [e for e in game.state.events[mark:] if e.type == "counter_placed"]
        assert [e.data["amount"] for e in placed] == [2]


class TestTheLoader:
    def test_it_needs_objects(self):
        card = CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Double the number of each kind of counter on target permanent.",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "double_counters"}],
            }
        )
        with pytest.raises(DslError, match="double_counters needs 'objects'"):
            compile_card(card)
