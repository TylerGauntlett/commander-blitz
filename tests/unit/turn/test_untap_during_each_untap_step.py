"""Untapping outside your own untap step.

    Murkfiend Liege — "Untap all green and/or blue creatures you control during
    each other player's untap step."

`untap_all` hard-wires the active player: it walks the battlefield and skips
anything `obj.controller != pid`. Nothing else in the engine ever untaps on
somebody else's turn, and there is no trigger route either — `turn._untap_step`
uses `state.emit` rather than `fire`, so no ability is scanned there at all, and
the untap step grants no priority, so a trigger would resolve a step late and be
respondable when the printed static is not.

So it is read where it happens, like the other player-wide statics
(`extra_land_drops`, `no_hand_limit`) rather than layered into `chars`: it is a
fact about *when a set of permanents untaps*, which no characteristic carries.

The one thing worth being careful about is what makes this card good, and it is
easy to write a version that looks right and is not: on **your own** untap step
these creatures untap anyway. A test that only ever looks at your own turn
passes whether or not the static does anything at all.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind
from automtg.engine.player_statics import untap_also
from tests.conftest import only_oid


def board(builder, *, liege: bool, attacker: str = "t_dork"):
    """A tapped creature of each colour, and optionally the Liege."""
    extra = ["t_vigil_liege"] if liege else []
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + extra)
        .battlefield(0, [attacker, "t_lifelinker"], tapped=True)
        .battlefield(1, ["t_bear"])
        .build()
    )


def past_opponents_untap(game) -> None:
    """Advance to just *after* player 1's untap step.

    The untap step grants no priority, so it cannot be observed from inside --
    which is also why a trigger could not implement this card. The first moment
    anybody can look is once player 1 holds priority on their own turn.
    """
    for _ in range(400):
        if game.state.active_player == 1 and game.state.turn > 1:
            return
        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        ) or next(
            (
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.FINISH_DECLARATION
            ),
            None,
        )
        if action is None:
            raise AssertionError(f"stuck at {game.state.step} with no way to pass")
        game.apply(action)
    raise AssertionError("never reached the opponent's turn")


class TestOnAnotherPlayersUntapStep:
    def test_a_matching_creature_untaps(self, builder):
        game = board(builder, liege=True)
        dork = only_oid(game, "t_dork")
        assert game.state.objects[dork].tapped
        past_opponents_untap(game)
        assert not game.state.objects[dork].tapped, (
            "the green creature stayed tapped through the opponent's untap step"
        )

    def test_without_the_static_it_stays_tapped(self, builder):
        """The pair, and the one that makes the test above mean anything."""
        game = board(builder, liege=False)
        dork = only_oid(game, "t_dork")
        past_opponents_untap(game)
        assert game.state.objects[dork].tapped

    def test_a_creature_outside_the_filter_stays_tapped(self, builder):
        """`t_lifelinker` is white. The filter is the printed clause, not "all
        creatures you control"."""
        game = board(builder, liege=True)
        cleric = only_oid(game, "t_lifelinker")
        past_opponents_untap(game)
        assert game.state.objects[cleric].tapped

    def test_it_reaches_only_its_controllers_permanents(self, builder):
        """"…green creatures **you control**".

        Asserted on `untap_also` directly rather than through a turn, because on
        the only turn where the static is active -- the opponent's -- their own
        untap step untaps their creatures anyway, so a version that wrongly
        reached across would be invisible on the board.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_vigil_liege"])
            .battlefield(0, ["t_dork"], tapped=True)
            .battlefield(1, ["t_dork"], tapped=True)
            .build()
        )
        mine = only_oid(game, "t_dork", 0)
        theirs = only_oid(game, "t_dork", 1)
        also = untap_also(game.state, active_pid=1)
        assert mine in also
        assert theirs not in also

    def test_it_is_inactive_on_its_own_controllers_turn(self, builder):
        """"each **other** player's untap step". Doing it on your own turn too
        changes nothing observable -- they untap anyway -- but the static must
        still say what it says."""
        game = board(builder, liege=True)
        assert untap_also(game.state, active_pid=0) == []
        assert untap_also(game.state, active_pid=1) != []


class TestSkipNextUntapStillWins:
    def test_a_held_down_creature_is_not_freed_by_it(self, builder):
        """`skip_next_untap` is a prohibition and this is a permission; the
        prohibition wins, and it is spent by the step it skips either way."""
        game = board(builder, liege=True)
        dork = only_oid(game, "t_dork")
        game.state.objects[dork].skip_next_untap = True
        past_opponents_untap(game)
        assert game.state.objects[dork].tapped
