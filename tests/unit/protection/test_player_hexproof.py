""""You have hexproof." -- 702.11d, hexproof on a player.

    Metropolis Reformer -- "Flying, vigilance. You have hexproof. Whenever
    this creature is dealt damage, you gain that much life."

A player with hexproof can't be the target of spells or abilities their
**opponents** control. That one word is the difference from the two near
misses: shroud would stop the player's own spells too, and protection
(`test_player_protection.py`) stops everyone *and* prevents damage. So it is
its own player-wide static, `player_hexproof`, read by
`targeting._player_allowed` beside the protection check, and asked of the
spell's controller.

The rules points, each with a test:

- An opponent's spell cannot target the player.
- The player's own spell still can.
- It lasts as long as the permanent: without it, the player is a target again.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind

REFORMER = "t_ph_reformer"
BOLT = "t_bolt"  # deals 3 damage to any target


def board(builder, *, caster: int, hexproof_for: int | None):
    game = (
        builder(players=2)
        .battlefield(caster, ["mountain"] * 4)
        .battlefield(hexproof_for if hexproof_for is not None else 1 - caster,
                     [REFORMER] if hexproof_for is not None else ["t_bear"])
        .hand(caster, [BOLT])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(caster)
        .build()
    )
    return game


def player_targets(game, caster: int) -> set[int]:
    return {
        ref.id
        for action in game.legal_actions()
        if action.kind is ActionKind.CAST
        and action.source is not None
        and game.state.objects[action.source].def_id == BOLT
        and game.state.objects[action.source].controller == caster
        for ref in action.targets
        if ref.kind == "player"
    }


class TestOpponentsCannotTarget:
    def test_an_opponents_spell_cannot_target_the_player(self, builder):
        game = board(builder, caster=0, hexproof_for=1)
        assert 1 not in player_targets(game, 0)
        assert 0 in player_targets(game, 0)

    def test_without_the_static_the_player_is_a_target(self, builder):
        game = board(builder, caster=0, hexproof_for=None)
        assert 1 in player_targets(game, 0)


class TestTheirOwnSpellsStillCan:
    def test_the_player_may_target_themself(self, builder):
        """The line between hexproof and shroud or protection."""
        game = board(builder, caster=1, hexproof_for=1)
        assert 1 in player_targets(game, 1)
