""""Creatures with power 2 or less can't attack you": the player, and only the player.

Rule 508.1c makes a declaration illegal if any restriction is disobeyed, and
506.2 is what the restriction names: a creature attacks a player, a planeswalker
or a battle, and attacking somebody's planeswalker is not attacking *them*. The
witness is **Queen Mother Ramonda** -- "As long as you're the monarch, creatures
with power 2 or less can't attack you." Its sentence says "you" and nothing
else.

`cant_attack_you` was built for Combat Calligrapher, whose sentence goes on "or
planeswalkers you control", so it walls off the seat *and* everything a
defender may be attacked through. Written on Ramonda that is a strictly
stronger card: her controller's planeswalkers and battles would be out of
reach of every small creature as well, with no line on the card saying so.
That counterfactual is `t_ramonda_walkers`, asserted against below. The
`player_only` key takes the permanents back out.

The other half is *which* creatures: "power 2 or less" is the creature's power
**as it now is**. A prohibition on declaring attackers is no layer (613), so an
anthem that lifts a 2/2 to 3/3 lifts it over the wall. Read off the printed
card instead, a pumped Bear would still be stopped and the line would be a
different card again.

And "as long as you're the monarch" is the static condition `is_monarch`, read
live: the wall stands while the crown is on its controller's head and falls the
moment it moves.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import become_monarch
from tests.conftest import _default_answer, only_oid, static_probe

BEAR = "t_bear"  # 2/2 -- under the ceiling
GIANT = "t_big"  # 6/6 -- over it
ANTHEM = "t_anthem"  # "Creatures you control get +1/+1."
WALL = "t_ramonda_wall"  # the printed line: player_only
OVERREACH = "t_ramonda_walkers"  # the near miss: the same line reaching walkers
WALKER = "t_walker"
BATTLE = "t_battle_wall"


def position(builder, *, mine=(BEAR, GIANT), theirs=(WALL, WALKER), monarch=1):
    """Player 0 attacks; player 1 holds the wall; player 2 is an open seat."""
    b = builder(players=3)
    b.battlefield(0, list(mine))
    b.battlefield(1, list(theirs))
    game = b.active(0).step(Step.UNTAP).build()
    if monarch is not None:
        become_monarch(game.state, monarch)
    for _ in range(60):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def players_offered(game, oid: int) -> list[int]:
    return sorted(
        t.id
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
        for t in a.targets
        if t.kind == "player"
    )


def permanents_offered(game, oid: int) -> list[int]:
    return sorted(
        t.id
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
        for t in a.targets
        if t.kind == "object"
    )


class TestItWallsOffThePlayer:
    def test_a_small_creature_cannot_attack_the_monarch(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        assert players_offered(game, bear) == [2]
        assert not combat_mod.add_attacker(game.state, bear, 1)

    def test_a_large_creature_is_untouched(self, builder):
        game = position(builder)
        giant = only_oid(game, GIANT, 0)
        assert players_offered(game, giant) == [1, 2]


class TestItLeavesTheirPermanentsOpen:
    def test_the_planeswalker_is_still_offered(self, builder):
        """506.2: attacking a planeswalker is not attacking its controller, and
        the sentence names only "you"."""
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER, 1)
        assert permanents_offered(game, bear) == [walker]
        assert combat_mod.add_attacker(game.state, bear, 1, permanent=walker)

    def test_the_battle_is_still_offered(self, builder):
        game = position(builder, theirs=(WALL, BATTLE))
        bear = only_oid(game, BEAR, 0)
        battle = only_oid(game, BATTLE, 1)
        assert permanents_offered(game, bear) == [battle]

    def test_the_near_miss_closes_the_walker_too(self, builder):
        """`t_ramonda_walkers` is the card the DSL could already write, and it
        is a strictly stronger one."""
        game = position(builder, theirs=(OVERREACH, WALKER))
        bear = only_oid(game, BEAR, 0)
        assert players_offered(game, bear) == [2]
        assert permanents_offered(game, bear) == []


class TestPowerIsReadAsItNowIs:
    def test_an_anthem_lifts_a_bear_over_the_wall(self, builder):
        game = position(builder, mine=(BEAR, ANTHEM))
        bear = only_oid(game, BEAR, 0)
        assert players_offered(game, bear) == [1, 2]

    def test_the_boundary_is_inclusive(self, builder):
        """"2 or less": a 2/2 is stopped, and the anthem's 3/3 is the first
        power that is not."""
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        assert players_offered(game, bear) == [2]


class TestOnlyWhileTheMonarch:
    def test_no_monarch_no_wall(self, builder):
        game = position(builder, monarch=None)
        bear = only_oid(game, BEAR, 0)
        assert players_offered(game, bear) == [1, 2]

    def test_someone_else_wearing_the_crown_is_no_wall(self, builder):
        game = position(builder, monarch=2)
        bear = only_oid(game, BEAR, 0)
        assert players_offered(game, bear) == [1, 2]

    def test_the_wall_falls_the_moment_the_crown_moves(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR, 0)
        assert players_offered(game, bear) == [2]
        become_monarch(game.state, 0)
        assert players_offered(game, bear) == [1, 2]


class TestTheLoaderGuardsIt:
    def test_player_only_on_any_other_static_is_refused(self):
        """On a tax the player is already the default reach, and on anything
        else the key would load, print and change nothing."""
        probe = static_probe(
            {
                "effect": "attack_tax",
                "cost": {"mana": "{2}"},
                "affects": {"controller": "any", "types": ["Creature"]},
                "player_only": True,
            }
        )
        with pytest.raises(DslError, match="player_only"):
            compile_card(CardModel.model_validate(probe))

    def test_the_witness_compiles_with_the_key(self, registry):
        static = registry.get(WALL).abilities[0].static
        assert static["effect"] == "cant_attack_you"
        assert static["player_only"] is True

    def test_the_key_is_absent_unless_written(self, registry):
        assert "player_only" not in registry.get(OVERREACH).abilities[0].static
