""""…with \"**During your turn**, this creature has first strike.\""

The Restless cycle — Restless Spire in the deck this was built for. A
creature-land whose animated body carries a quoted ability that is live for half
the turn cycle: first strike while you attack, none while you block.

`animate` granted keywords unconditionally, and the two near misses are wrong in
opposite directions:

- A flat `keywords` entry keeps first strike **on the opponent's turn**, so the
  land blocks better than the printed card ever does. `TestTheFlatVersionIsWrong`
  keeps that spelling alive as a card and shows the difference.
- A separate static beside the animation would have no printed line of its own
  to claim, which is the residual gate's objection and the reason Raging Ravine
  is still refused by the fetchland templates.

So it rides the animation, as one op for one printed sentence.

The flag is named for the printed clause rather than being a general
`condition`, and that is deliberate: evaluating an arbitrary condition inside
the characteristics layer is how a static comes to read another static's output,
which the loader forbids everywhere else. "Is it my turn" is a pipeline *input*
the way a counter or a tapped flag is, so it can be read without opening that
door.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.primitives import animate
from tests.conftest import only_oid, pass_until

LAND = "t_restless"  # the quoted, your-turn-only version
FLAT = "t_restless_flat"  # the same animation with a plain keyword


def position(builder, land: str):
    game = (
        builder(players=2)
        .battlefield(0, [land, "island", "mountain"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 10)
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def pass_the_turn_to(game, pid: int) -> None:
    """Make ``pid`` the active player.

    `active_player` is derived from `active_idx` and has no setter, which is
    right -- whose turn it is belongs to the turn engine. Moving the index is
    the smallest honest way to ask `chars` the question this flag is about,
    without driving a whole turn cycle and testing the turn engine instead.
    """
    game.state.active_idx = next(
        i for i, p in enumerate(game.state.players) if p.pid == pid
    )
    game.state.bump_chars()


def keywords_of(game, oid) -> set[str]:
    return {str(k) for k in chars(game.state, oid).keywords}


def animate_it(game, land: str) -> int:
    """Activate the animation and return the land's oid."""
    oid = only_oid(game, land)
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)
    return oid


class TestOnYourTurn:
    def test_the_animated_land_has_first_strike(self, builder):
        game = position(builder, LAND)
        oid = animate_it(game, LAND)

        assert game.state.active_player == 0, "it is the controller's turn"
        assert "first_strike" in keywords_of(game, oid)

    def test_it_is_a_creature_and_still_a_land(self, builder):
        """The rest of the animation is unchanged by the new key."""
        game = position(builder, LAND)
        oid = animate_it(game, LAND)

        c = chars(game.state, oid)
        assert "Creature" in c.types
        assert "Land" in c.types
        assert (c.power, c.toughness) == (2, 1)


class TestOnSomebodyElsesTurn:
    def test_first_strike_is_gone(self, builder):
        """The half the printed card withholds, and a flat keyword would keep.

        `animate` is called directly rather than through the ability: the point
        is what `chars` reports once the active player changes, and driving a
        whole turn around to the opponent's combat would test the turn engine
        rather than this flag.
        """
        game = position(builder, LAND)
        oid = only_oid(game, LAND)
        animate(
            game.state, oid, 2, 1, subtypes=["Elemental"], your_turn_keywords=["first_strike"]
        )
        game.state.bump_chars()
        assert "first_strike" in keywords_of(game, oid)

        pass_the_turn_to(game, 1)

        assert "first_strike" not in keywords_of(game, oid)
        assert "Creature" in chars(game.state, oid).types, "still animated, just not first-striking"

    def test_it_comes_back_on_your_next_turn(self, builder):
        """Not spent -- withheld. The clause is a condition, not a one-shot."""
        game = position(builder, LAND)
        oid = only_oid(game, LAND)
        animate(
            game.state, oid, 2, 1, subtypes=["Elemental"], your_turn_keywords=["first_strike"]
        )

        pass_the_turn_to(game, 1)
        assert "first_strike" not in keywords_of(game, oid)

        pass_the_turn_to(game, 0)
        assert "first_strike" in keywords_of(game, oid)


class TestTheFlatVersionIsWrong:
    def test_a_plain_keyword_survives_into_the_opponents_turn(self, builder):
        """Kept as a live card because it is the mistake this key prevents.

        A Restless land written with `keywords` blocks with first strike on
        every opponent's turn, which is strictly better than the printed card.
        """
        game = position(builder, FLAT)
        oid = animate_it(game, FLAT)
        assert "first_strike" in keywords_of(game, oid)

        pass_the_turn_to(game, 1)

        assert "first_strike" in keywords_of(game, oid), "the wrong reading, pinned"
