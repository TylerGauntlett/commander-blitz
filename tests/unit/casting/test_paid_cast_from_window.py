"""A paid cast out of a bounded "look at the top N" window.

    Sanwell, Avenger Ace — "Whenever Sanwell becomes tapped, exile the top six
    cards of your library. **You may cast a Vehicle or artifact creature spell
    from among them.** Then put the rest on the bottom of your library in a
    random order."

`cast_free` is Herald of Amity's shape and makes the spell free, a strictly
better card. `cast_card` pays the printed price but offers every card of its
pool, so it would cast every artifact creature in the six. `cast_paying` is the
same window as `cast_free` -- one pick, the rest to the bottom -- with the
cast made at the card's own mana cost through `_cast_paying_mana_cost`, the
price `cast_card` charges (601.2f). The claims:

1. **It is paid for.** The pool is spent, and a card the caster cannot afford is
   never offered (118.4) and folds back into the rest.
2. **It is one spell**, and the rest reach the bottom.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import library_ids

FOREST = "forest"
BEAR = "t_bear"           # {1}{G}, mana value 2
BOLT = "t_bolt"           # {R}, mana value 1
GIANT = "t_big"           # {5}{G}, mana value 6
SOURCE = "t_dork"

#: Sanwell's middle sentence over a creature filter, so the shared test cards serve.
WINDOW = {
    "op": "look_at_top",
    "amount": {"const": 3},
    "objects": {"types": ["Creature"], "count": 1, "optional": True},
    "cast_paying": True,
    "rest_to_bottom": True,
}


def board(builder, library: list[str], *, lands: int = 2):
    game = (
        builder(players=2)
        .battlefield(0, [SOURCE] + ["forest"] * lands)
        .library(0, library)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == SOURCE)
    return game, src


def run(game, src, spec=None, *, want: str | None = BEAR, cast: bool = True):
    ctx = EffectContext(state=game.state, controller=0, source_oid=src)
    gen = OPS["look_at_top"](ctx, dict(spec or WINDOW))
    asked = []
    send = None
    for _ in range(80):
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        if decision.kind is DecisionKind.MAY:
            send = [0] if cast else [1]
            continue
        options = decision.options
        values = [getattr(option, "value", None) for option in options]
        ids = [
            game.state.objects[v].def_id if isinstance(v, int) and v in game.state.objects else None
            for v in values
        ]
        if want is not None and want in ids:
            send = [ids.index(want)]
        elif decision.kind is DecisionKind.CHOOSE_OBJECTS and want is None:
            send = []
        else:
            send = [0]
    raise AssertionError("the op never finished")


def stack_ids(game):
    return [item.def_id for item in game.state.stack]


def casts(game):
    return [e for e in game.state.events if e.type == EventType.SPELL_CAST]


class TestTheSpellIsPaidFor:
    def test_the_picked_card_reaches_the_stack(self, builder):
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])
        run(game, src)
        assert stack_ids(game) == [BEAR]

    def test_it_is_not_free(self, builder):
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])
        run(game, src)
        [event] = casts(game)
        assert not event.data.get("free")
        tapped = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "forest" and o.tapped
        ]
        assert len(tapped) == 2

    def test_a_card_the_caster_cannot_afford_is_not_cast(self, builder):
        """Two Forests do not pay {5}{G}: the Giant folds back into the rest."""
        game, src = board(builder, [GIANT, FOREST, FOREST, BOLT])
        run(game, src, want=GIANT)
        assert stack_ids(game) == []
        assert GIANT in library_ids(game)

    def test_with_no_mana_nothing_is_cast(self, builder):
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT], lands=0)
        run(game, src)
        assert stack_ids(game) == []


class TestOneSpellAndTheRestToTheBottom:
    def test_the_rest_go_to_the_bottom(self, builder):
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])
        run(game, src)
        assert library_ids(game)[0] == BOLT, "the fourth card was never looked at"
        assert sorted(library_ids(game)[1:]) == sorted([FOREST, GIANT])

    def test_declining_folds_the_card_back(self, builder):
        game, src = board(builder, [BEAR, FOREST, GIANT, BOLT])
        run(game, src, cast=False)
        assert stack_ids(game) == []
        assert sorted(library_ids(game)[1:]) == sorted([BEAR, FOREST, GIANT])

    def test_only_one_spell_is_cast(self, builder):
        game, src = board(builder, [BEAR, BEAR, GIANT, BOLT], lands=4)
        run(game, src)
        assert stack_ids(game) == [BEAR]
        assert library_ids(game).count(BEAR) == 1


class TestTheLoader:
    def _compile(self, effect):
        model = CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "types": ["Sorcery"],
                "mana_cost": "{1}",
                "spell_effects": [effect],
            }
        )
        return compile_card(model)

    def test_the_window_loads(self):
        self._compile(WINDOW)

    def test_both_prices_are_refused(self):
        with pytest.raises(DslError, match="not both"):
            self._compile({**WINDOW, "cast_free": True})

    def test_it_belongs_to_look_at_top(self):
        with pytest.raises(DslError, match="cast_paying"):
            self._compile({"op": "exile_until", "cast_paying": True, "until": {"types": ["Creature"]}})

    def test_a_destination_is_refused_beside_it(self):
        with pytest.raises(DslError, match="takes no"):
            self._compile({**WINDOW, "destination": "hand"})
