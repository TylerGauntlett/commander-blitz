""""Creatures you control gain protection from each color until end of turn."

    Akroma's Will — the second mode.

Protection existed only as a **printed static** on a permanent:
`protection_from` collected candidates from `_battlefield_statics`, which walks
`card.abilities` of battlefield objects and never saw anything granted or
temporary. So there was no way to hand protection to something.

`grant_keyword` is not the near miss it looks like. Protection is parameterised
by definition — "from black", "from Wizards", "from each color" — and a
`Keyword` is a bare string with nowhere to put the parameter. That is the same
argument the printed static made when it was built, and it applies again here.

**One `TempEffect` per quality**, rather than one carrying a list.
`TempEffect.keyword` is already a single string and `protection_from` already
returns a flat set of qualities, so five colours is five entries and nothing
downstream had to learn a new shape — the four rules that read protection
(damage, enchant/equip, block, target) see granted and printed alike.
"""

from __future__ import annotations

from automtg.engine.characteristics import protection_from
from automtg.engine.enums import ActionKind
from automtg.engine.primitives import damage_permanent
from automtg.engine.turn import clear_until_eot
from tests.conftest import oids_of, pass_until

PROTECTOR = "t_protector"  # instant: your creatures gain protection from each colour
BEAR = "t_bear"
PLAINS = "plains"


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, [BEAR, *([PLAINS] * 3)])
        .battlefield(1, [BEAR])
        .hand(0, [PROTECTOR])
        .library(0, [PLAINS] * 20)
        .active(0)
        .max_turns(2)
        .build()
    )


def cast_it(game):
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == PROTECTOR
        )
    )
    pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)


def mine(game) -> int:
    return next(
        o for o in oids_of(game, BEAR) if game.state.objects[o].controller == 0
    )


def theirs(game) -> int:
    return next(
        o for o in oids_of(game, BEAR) if game.state.objects[o].controller == 1
    )


class TestGrantedProtectionIsRead:
    def test_the_creature_has_every_colour(self, builder):
        game = board(builder)
        cast_it(game)
        assert protection_from(game.state, mine(game)) == frozenset("WUBRG")

    def test_it_is_not_given_to_the_opponent(self, builder):
        """"Creatures **you** control."""
        game = board(builder)
        cast_it(game)
        assert protection_from(game.state, theirs(game)) == frozenset()

    def test_nothing_has_it_beforehand(self, builder):
        game = board(builder)
        assert protection_from(game.state, mine(game)) == frozenset()


class TestItActuallyProtects:
    def test_damage_from_a_coloured_source_is_prevented(self, builder):
        """The point of the card, read through the rule rather than the field."""
        game = board(builder)
        cast_it(game)
        bear = mine(game)
        source = theirs(game)  # a green Bear

        dealt = damage_permanent(game.state, bear, 2, source)

        assert dealt == 0
        assert game.state.objects[bear].damage == 0

    def test_damage_lands_without_the_grant(self, builder):
        """The control -- otherwise the test above proves nothing."""
        game = board(builder)
        bear = mine(game)
        source = theirs(game)

        dealt = damage_permanent(game.state, bear, 2, source)

        assert dealt == 2


class TestItWearsOff:
    def test_cleanup_takes_it_away(self, builder):
        """"Until end of turn" -- it lives in `until_eot`, which is swept."""
        game = board(builder)
        cast_it(game)
        bear = mine(game)
        assert protection_from(game.state, bear)

        clear_until_eot(game.state)

        assert protection_from(game.state, bear) == frozenset()
