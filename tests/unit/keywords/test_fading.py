"""Fading (702.32): "remove a fade counter. **If you can't**, sacrifice it."

The census routes it as "`upkeep` + `remove_counters` + a sacrifice; needs 'if
you can't' to be askable" — and it already was. `counters_on` is a value
expression, so "if you can't" is an ordinary `cmp` against 1 inside an `if`,
with the sacrifice in the `else`. Nothing needed adding.

The clause is the whole keyword and it is easy to get subtly wrong. Fading
counts **one more turn than the number printed**: a creature with fading 2
survives two upkeeps removing counters and dies on the third, because the turn
it dies is the turn it *cannot* remove one. An implementation that sacrificed
when the last counter came off would be a fading 1 wearing a fading 2's text,
and every test that only checked "it eventually dies" would pass.

That off-by-one is why the test walks three upkeeps and asserts at each.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step, Zone
from tests.conftest import only_oid, pass_until

FADER = "t_fader"  # 3/3, fading 2


def position(builder, *, fade: int = 2):
    game = (
        builder(players=2).battlefield(0, [FADER], counters={"fade": fade}).build()
    )
    return game, only_oid(game, FADER, 0)


def to_turn(game, turn: int) -> None:
    pass_until(game, lambda g: g.state.turn >= turn and g.state.step >= Step.PRECOMBAT_MAIN)


def fade_counters(game, oid: int) -> int:
    return game.state.objects[oid].counter("fade")


class TestItCountsDown:
    def test_it_enters_with_its_counters(self, builder):
        game, oid = position(builder)
        assert fade_counters(game, oid) == 2

    def test_the_first_upkeep_removes_one(self, builder):
        game, oid = position(builder)
        to_turn(game, 3)
        assert fade_counters(game, oid) == 1
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_the_second_upkeep_removes_the_last(self, builder):
        game, oid = position(builder)
        to_turn(game, 5)
        assert fade_counters(game, oid) == 0
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD, (
            "it is still here: the counter came off, which is not failing to "
            "remove one"
        )


class TestTheOffByOne:
    def test_it_dies_on_the_upkeep_it_cannot_pay(self, builder):
        """Fading 2 survives *two* removals and dies on the third upkeep.

        Sacrificing when the last counter comes off would be a fading 1 wearing
        a fading 2's text, and "it eventually dies" passes either way.
        """
        game, oid = position(builder)
        to_turn(game, 7)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_fading_one_dies_a_turn_earlier(self, builder):
        game, oid = position(builder, fade=1)
        to_turn(game, 3)
        assert fade_counters(game, oid) == 0
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        to_turn(game, 5)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_with_no_counters_it_dies_at_once(self, builder):
        """The boundary the `if` exists for: nothing to remove, first upkeep."""
        game, oid = position(builder, fade=0)
        to_turn(game, 3)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestItIsTheControllersUpkeepOnly:
    def test_the_opponents_upkeep_does_nothing(self, builder):
        game, oid = position(builder)
        pass_until(
            game,
            lambda g: g.state.turn >= 2
            and g.state.active_player == 1
            and g.state.step >= Step.PRECOMBAT_MAIN,
        )
        assert fade_counters(game, oid) == 2


class TestTheCardUsesOnlyShippedVocabulary:
    def test_if_you_cant_is_an_ordinary_comparison(self, registry):
        card = registry.get(FADER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        (branch,) = ability.effects
        assert branch["op"] == "if"
        assert branch["condition"]["cmp"] == ">="
        assert "counters_on" in branch["condition"]["left"]
        assert [e["op"] for e in branch["then"]] == ["remove_counters"]
        assert [e["op"] for e in branch["else"]] == ["sacrifice"]
