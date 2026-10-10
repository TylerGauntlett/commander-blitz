"""Compleated: two fewer loyalty per Phyrexian symbol paid with life (702.150a).

    Tamiyo, Compleated Sage: "Compleated ({G/U/P} can be paid with {G}, {U},
    or 2 life. If life was paid, this planeswalker enters with two fewer
    loyalty counters.)"

The rule is a replacement on the arrival: "If this permanent would enter with
one or more loyalty counters on it, it enters with two fewer loyalty counters
on it for each Phyrexian mana symbol life was paid for." Casting already let a
Phyrexian pip be bought with 2 life (107.4f, `action.phyrexian`), but nothing
remembered it past the payment and nothing reduced the starting loyalty -- so a
Tamiyo cast for 2 life arrived at the full 5, a strictly better card than the
printed one.

What had to be built: `game._cast` writes the count of **printed** Phyrexian
symbols paid with life onto the object (`cast_phyrexian_life`), and
`zones._enter_battlefield` takes two loyalty per symbol straight after the
starting-loyalty replacement, before the walker is ever seen. It reads the
count only on the arrival that was that cast (`entered_by_cast`), so the same
walker blinked later enters at full loyalty.

Witnesses: Tamiyo, Compleated Sage and Ajani, Sleeper Agent.
`t_compleated_walker` is Tamiyo's cost and loyalty; `t_phyrexian_walker` the
same card without the keyword.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until

WALKER = "t_compleated_walker"  # {2}{G}{G/U/P}{U}, loyalty 5, compleated
CONTROL = "t_phyrexian_walker"  # the same without the keyword
TWICE = "t_twice_compleated"  # {1}{W/P}{W/P}, loyalty 3, compleated


def position(builder, card: str = WALKER):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + ["island"] * 2 + ["plains"] * 3)
        .hand(0, [card])
        .library(0, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game


def cast(game, card: str, phyrexian: int) -> int:
    """Cast `card` paying `phyrexian` of its Phyrexian pips with life; return its oid."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card
        and a.phyrexian == phyrexian
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return action.source  # an oid survives the move onto the battlefield


class TestLifePaidTakesLoyalty:
    def test_paid_with_mana_it_enters_at_full_loyalty(self, builder):
        game = position(builder)
        oid = cast(game, WALKER, 0)
        assert game.state.objects[oid].counter("loyalty") == 5

    def test_paid_with_life_it_enters_with_two_fewer(self, builder):
        game = position(builder)
        life = game.state.players[0].life
        oid = cast(game, WALKER, 1)
        assert game.state.players[0].life == life - 2
        assert game.state.objects[oid].counter("loyalty") == 3

    def test_it_is_the_keyword_and_not_the_payment(self, builder):
        """The control: the same cost paid the same way, no keyword, no loss."""
        game = position(builder, CONTROL)
        oid = cast(game, CONTROL, 1)
        assert game.state.objects[oid].counter("loyalty") == 5

    def test_it_never_arrives_at_full_size(self, builder):
        """614.1c: a replacement, not a trigger -- nothing is queued, and the
        walker is at 3 the moment it is on the battlefield."""
        game = position(builder)
        action = next(
            a for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.phyrexian == 1
            and game.state.objects[a.source].def_id == WALKER
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)
        oid = only_oid(game, WALKER, 0)
        assert game.state.objects[oid].counter("loyalty") == 3


class TestEachSymbolCounts:
    @pytest.mark.parametrize("paid,loyalty", [(0, 3), (1, 1)])
    def test_two_per_symbol(self, builder, paid, loyalty):
        game = position(builder, TWICE)
        oid = cast(game, TWICE, paid)
        assert game.state.objects[oid].counter("loyalty") == loyalty

    def test_it_floors_at_zero_and_the_walker_dies(self, builder):
        """3 - 2 - 2 is not -1: it enters with none, and 704.5i bins it."""
        game = position(builder, TWICE)
        oid = cast(game, TWICE, 2)
        assert game.state.objects[oid].counter("loyalty") == 0
        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestOnlyTheCastArrival:
    def test_a_later_arrival_is_at_full_loyalty(self, builder):
        """The count describes one casting. Blinked, the walker is a new object
        that nobody paid life for."""
        game = position(builder)
        oid = cast(game, WALKER, 1)
        move_object(game.state, oid, Zone.EXILE)
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0)
        assert game.state.objects[oid].counter("loyalty") == 5

    def test_put_onto_the_battlefield_it_is_never_reduced(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WALKER])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        oid = only_oid(game, WALKER, 0)
        assert game.state.objects[oid].counter("loyalty") == 5


class TestTheLoaderChecksIt:
    def _card(self, **overrides) -> CardModel:
        body = {
            "id": "t_bad_compleated",
            "name": "Test Bad Compleated",
            "mana_cost": "{2}{G}{G/U/P}{U}",
            "types": ["Planeswalker"],
            "loyalty": 5,
            "keywords": ["compleated"],
            "oracle_text": "Compleated",
        }
        body.update(overrides)
        return CardModel.model_validate(body)

    def test_the_keyword_is_the_form(self):
        compile_card(self._card())

    def test_refused_without_a_phyrexian_symbol(self):
        with pytest.raises(DslError, match="Phyrexian"):
            compile_card(self._card(mana_cost="{2}{G}{G}{U}"))

    def test_refused_without_loyalty(self):
        with pytest.raises(DslError, match="loyalty"):
            compile_card(self._card(types=["Creature"], loyalty=None, power=2, toughness=2))
