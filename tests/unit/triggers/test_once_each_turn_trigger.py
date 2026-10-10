""""This ability triggers only once each turn", and what it makes free.

    Welcoming Vampire — "Whenever one or more other creatures you control with
    power 2 or less enter, draw a card. This ability triggers only once each
    turn."

`once_each_turn` already existed and is an **activation** restriction — the
loader raises if it appears on anything but an activated ability, so a triggered
ability had no limiter at all. The two near misses each say something else:
`set_flag`/`has_flag` is once *ever*, since flags clear only on a zone change,
and `resolutions_this_turn` gates resolving rather than triggering.

**Counted where the ability queues, not where it resolves.** The printed word is
"triggers": an ability that triggered and was then countered, or whose target
vanished, has still used its one for the turn. Keyed by
`(permanent, ability index)` so two Welcoming Vampires each get their own draw.

**It also buys "whenever one or more … enter" for free**, which was filed as a
separate capability. Two creatures entering simultaneously queue the ability
twice, and the cap drops the second — the same answer batching the events would
have given. Every printed card that asked for the batch also printed the
per-turn clause, so nothing is left approximated here. A card printing "one or
more" *without* a cap would still be wrong, and is still a gap.

**Power is read off the board, not off the card.** Everything else in a trigger
filter is a characteristic no layer can change, which is what lets
`matches_card_filter` read the printed face and still be right about a creature
that has already died. P/T is the exception: a printed 2/2 entering under an
anthem is a 3/3 and must not trigger "power 2 or less", and reading `card.power`
says it does.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

WELCOMER = "t_welcomer"
SMALL = "vampire_1_1_b"  # a 1/1 token -- power 2 or less
BIG = "kraken_8_8_u"  # an 8/8 token -- power far above 2
TWO_TWO = "elemental_2_2_g"  # exactly on the boundary, so an anthem moves it off
ANTHEM = "t_anthem"  # creatures you control get +1/+1


def board(builder, extra=()):
    return (
        builder(players=2)
        .battlefield(0, [WELCOMER, *extra])
        .library(0, ["swamp"] * 30)
        .build()
    )


def settle(game):
    """Resolve what is pending, and assert the turn did not move.

    `pass_until` passes priority, which can roll into the next turn -- and the
    untap step clears `triggers_this_turn`. A cap test that let that happen
    would pass because the allowance had been refilled, which is the opposite of
    what it claims to show. So the turn is pinned rather than hoped for.
    """
    turn = game.state.turn
    pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)
    assert game.state.turn == turn, "the turn rolled over; the cap was refilled"


def drew(game, fn) -> int:
    before = len(game.state.players[0].hand)
    fn()
    settle(game)
    return len(game.state.players[0].hand) - before


class TestTheCap:
    def test_the_first_entry_triggers(self, builder):
        game = board(builder)
        assert drew(game, lambda: create_token(game.state, SMALL, 0, 1)) == 1

    def test_the_second_entry_in_the_same_turn_does_not(self, builder):
        game = board(builder)
        drew(game, lambda: create_token(game.state, SMALL, 0, 1))
        assert drew(game, lambda: create_token(game.state, SMALL, 0, 1)) == 0

    def test_two_entering_together_draw_once(self, builder):
        """"One or more", bought by the cap rather than by batching events."""
        game = board(builder)
        assert drew(game, lambda: create_token(game.state, SMALL, 0, 2)) == 1

    def test_the_cap_is_per_permanent(self, builder):
        """Two Welcoming Vampires are two separate draws."""
        game = board(builder, extra=(WELCOMER,))
        assert drew(game, lambda: create_token(game.state, SMALL, 0, 1)) == 2

    def test_it_resets_next_turn(self, builder):
        game = board(builder)
        drew(game, lambda: create_token(game.state, SMALL, 0, 1))

        game.state.triggers_this_turn.clear()  # what the untap step does

        assert drew(game, lambda: create_token(game.state, SMALL, 0, 1)) == 1


class TestThePowerFilterReadsTheBoard:
    def test_a_small_creature_triggers_it(self, builder):
        game = board(builder)
        assert drew(game, lambda: create_token(game.state, SMALL, 0, 1)) == 1

    def test_a_big_creature_does_not(self, builder):
        game = board(builder)
        assert drew(game, lambda: create_token(game.state, BIG, 0, 1)) == 0

    def test_an_anthem_can_lift_a_creature_out_of_range(self, builder):
        """The case printed power gets wrong, and the reason this changed.

        A 2/2 token is "power 2 or less" on the card and a 3/3 on a board with
        an anthem. Reading `card.power` would trigger; reading the board does
        not, which is the rule.
        """
        game = board(builder, extra=(ANTHEM,))
        assert drew(game, lambda: create_token(game.state, TWO_TWO, 0, 1)) == 0

    def test_the_same_creature_triggers_it_without_the_anthem(self, builder):
        """The control for the test above -- otherwise it proves nothing."""
        game = board(builder)
        assert drew(game, lambda: create_token(game.state, TWO_TWO, 0, 1)) == 1

    def test_a_lone_welcomer_entering_does_not_trigger_itself(self, builder):
        """"…**other** creatures you control." `exclude_self` on the filter.

        Measured on the library, not the hand: the entering card leaves hand and
        a draw puts one back, so a hand count of zero would be the same number
        whether it drew or not.
        """
        game = (
            builder(players=2)
            .battlefield(0, [])
            .hand(0, [WELCOMER])
            .library(0, ["swamp"] * 30)
            .build()
        )
        welcomer = next(
            o.oid
            for o in game.state.objects.values()
            if o.zone is Zone.HAND and game.state.card_of(o).id == WELCOMER
        )
        library = len(game.state.players[0].library)

        move_object(game.state, welcomer, Zone.BATTLEFIELD)
        settle(game)

        assert len(game.state.players[0].library) == library, "it drew nothing"

    def test_a_second_welcomer_does_trigger_the_first(self, builder):
        """The other half of the same clause: each is "another" to the other."""
        game = (
            builder(players=2)
            .battlefield(0, [WELCOMER])
            .hand(0, [WELCOMER])
            .library(0, ["swamp"] * 30)
            .build()
        )
        second = next(
            o.oid
            for o in game.state.objects.values()
            if o.zone is Zone.HAND and game.state.card_of(o).id == WELCOMER
        )
        library = len(game.state.players[0].library)

        move_object(game.state, second, Zone.BATTLEFIELD)
        settle(game)

        assert len(game.state.players[0].library) == library - 1


class TestTheLoaderRefusesANonsenseCap:
    def test_zero_is_refused(self):
        with pytest.raises(DslError, match="at least 1"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_cap",
                        "name": "Bad Cap",
                        "mana_cost": "{1}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {
                                "kind": "triggered",
                                "text": "x",
                                "trigger": {"event": "upkeep", "max_per_turn": 0},
                                "effects": [{"op": "draw", "player": "you"}],
                            }
                        ],
                    }
                )
            )
