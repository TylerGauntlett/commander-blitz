"""`exile_until` — the library walk that leaves what it exiled in exile.

Breaching Dragonstorm: "When this enchantment enters, exile cards from the top
of your library until you exile a nonland card. You may cast it without paying
its mana cost if that spell's mana value is 8 or less. If you don't, put that
card into your hand."

Three neighbours, and each makes a different card. `cascade` stops only at a
card cheaper than its own spell and bottoms everything, a declined hit
included, so the hand never sees it. `discover` bounds the hit itself (a
nine-drop is walked past rather than handed over) and bottoms the rest.
`reveal_until` never exiles at all, so the lands walked past would go back
into the library. The printed sentence never moves the walked-past cards
anywhere, so they stay in exile; the mana value is a condition on the *cast*,
not on the stop, so a nine-drop still stops the walk and goes to hand.
"""

from __future__ import annotations

import inspect

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import hand_ids, library_ids

FOREST = "forest"
BEAR = "t_bear"           # {1}{G}, mana value 2
EIGHT = "t_tide_lock"     # {5}{U}{U}{U}, mana value 8
SOURCE = "t_cascader"     # only somewhere for the effect to come from


def breaching(ceiling: int = 8, **extra) -> dict:
    """Breaching Dragonstorm's trigger, with the ceiling as a parameter."""
    return {
        "op": "exile_until",
        "objects": {"not_types": ["Land"]},
        "cast_free": True,
        "cast_free_if": {"mana_value": {"op": "<=", "value": {"const": ceiling}}},
        "else_destination": "hand",
        "as": "hit",
        **extra,
    }


def board(builder, library: list[str]):
    game = builder(players=2).battlefield(0, [SOURCE]).library(0, library).build(advance=False)
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, spec: dict, source: int, *, cast: bool = True) -> tuple[EffectContext, int]:
    """Run one op, answering every yes/no; returns the context and the questions asked."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = OPS[spec["op"]](ctx, spec)
    asked = 0
    if inspect.isgenerator(gen):
        send = None
        while True:
            try:
                gen.send(send)
            except StopIteration:
                break
            asked += 1
            send = [0] if cast else [1]
    return ctx, asked


def exile_ids(game) -> list[str]:
    return sorted(game.state.objects[o].def_id for o in game.state.players[0].exile)


class TestTheWalk:
    def test_lands_walked_past_stay_in_exile(self, builder):
        """Neither bottomed (cascade, discover) nor left in the library (reveal_until)."""
        game, src = board(builder, [FOREST, FOREST, BEAR, EIGHT])

        run(game, breaching(), src, cast=True)

        assert [item.def_id for item in game.state.stack] == [BEAR]
        assert exile_ids(game) == [FOREST, FOREST]
        assert library_ids(game) == [EIGHT], "the walk stopped at the Bear"

    def test_mana_value_does_not_stop_the_walk(self, builder):
        """The 8 is a condition on the cast. The first nonland card is the hit."""
        game, src = board(builder, [EIGHT, BEAR])

        ctx, _ = run(game, breaching(ceiling=7), src, cast=True)

        assert game.state.objects[ctx.bindings["hit"][0]].def_id == EIGHT
        assert library_ids(game) == [BEAR]

    def test_an_exhausted_library_finds_nothing(self, builder):
        game, src = board(builder, [FOREST, FOREST])

        ctx, asked = run(game, breaching(), src)

        assert ctx.bindings["hit"] == []
        assert asked == 0
        assert exile_ids(game) == [FOREST, FOREST]
        assert hand_ids(game) == []


class TestTheCastCondition:
    def test_mana_value_equal_to_the_ceiling_may_be_cast(self, builder):
        """"8 or less" -- the boundary."""
        game, src = board(builder, [FOREST, EIGHT])

        run(game, breaching(ceiling=8), src, cast=True)

        assert [item.def_id for item in game.state.stack] == [EIGHT]
        assert hand_ids(game) == []

    def test_over_the_ceiling_goes_to_hand_unasked(self, builder):
        game, src = board(builder, [FOREST, EIGHT])

        _, asked = run(game, breaching(ceiling=7), src, cast=True)

        assert asked == 0, "a 'you may' whose yes is forbidden is not offered"
        assert game.state.stack == []
        assert hand_ids(game) == [EIGHT]
        assert exile_ids(game) == [FOREST]


class TestIfYouDont:
    def test_declining_puts_it_into_hand(self, builder):
        game, src = board(builder, [FOREST, BEAR])

        _, asked = run(game, breaching(), src, cast=False)

        assert asked == 1
        assert game.state.stack == []
        assert hand_ids(game) == [BEAR]
        assert exile_ids(game) == [FOREST]

    def test_without_else_destination_a_declined_hit_stays_in_exile(self, builder):
        """Wanda's Vision's shape: "You may cast that card without paying its mana cost."""
        game, src = board(builder, [FOREST, BEAR])
        spec = {"op": "exile_until", "objects": {"not_types": ["Land"]}, "cast_free": True}

        run(game, spec, src, cast=False)

        assert hand_ids(game) == []
        assert exile_ids(game) == sorted([BEAR, FOREST])
        assert all(game.state.objects[o].zone is Zone.EXILE for o in game.state.players[0].exile)

    def test_the_binding_names_the_hit_either_way(self, builder):
        game, src = board(builder, [FOREST, BEAR])

        ctx, _ = run(game, breaching(), src, cast=False)

        (oid,) = ctx.bindings["hit"]
        assert oid in game.state.players[0].hand


class TestTheLoaderGuard:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_exile_until_probe",
                "name": "Exile Until Probe",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_breaching_dragonstorm_loads(self):
        compile_card(self._card(breaching()))

    @pytest.mark.parametrize(
        ("effect", "message"),
        [
            ({"op": "exile_until"}, "needs a non-empty 'objects'"),
            ({"op": "exile_until", "objects": {}}, "needs a non-empty 'objects'"),
            (
                {"op": "exile_until", "objects": {"not_types": ["Land"]}, "amount": {"const": 3}},
                "takes no 'amount'",
            ),
            (
                {
                    "op": "exile_until",
                    "objects": {"not_types": ["Land"]},
                    "cast_free_if": {"mana_value": {"op": "<=", "value": 8}},
                },
                "'cast_free_if' needs 'cast_free'",
            ),
            (
                {"op": "exile_until", "objects": {"not_types": ["Land"]}, "else_destination": "hand"},
                "'else_destination' needs 'cast_free'",
            ),
            (
                {
                    "op": "exile_until",
                    "objects": {"not_types": ["Land"]},
                    "cast_free": True,
                    "else_destination": "battlefield",
                },
                "unknown exile_until else_destination",
            ),
        ],
    )
    def test_refusals(self, effect, message):
        with pytest.raises(DslError, match=message):
            compile_card(self._card(effect))
