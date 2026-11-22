"""A continuous block requirement: "…or blocks each combat if able".

Khârn the Betrayer is the witness: "Berzerker -- Khârn the Betrayer attacks or
blocks each combat if able." A creature can attack only on its controller's
turn and block only on somebody else's, so the sentence is two requirements
that never bind the same combat: on Khârn's turn it is `attacks_if_able`
(508.1d), and on an opponent's turn, when it could block, it is this one
(509.1c). The card spells the line as those two statics side by side, and that
is exact rather than an approximation, because no combat ever offers both.

The blocking half had only one-shot forms. `must_block` (provoke) names one
attacker for one combat, and `must_block_any` (Peema Aether-Seer, "blocks this
turn if able") records a turn on the object. A printed line binds *every*
combat for as long as it applies and stops the moment it does not, so it is a
static read live (`player_statics.block_compelled`), and it joins
`must_block_any` at that op's enforcement point, `combat.block_any_required`:
no attacker is named, so any block obeys it, and "…if able" is the same
`can_block` with ``ignore_existing``, no block tax and the menace exception.

Without it, Khârn blocks when its controller likes, which is a strictly better
card than the printed one: the Berzerker line is a drawback that hands
opponents a way to take it (its third line gives it away when it is dealt
damage, and a forced block is how that damage arrives).
"""

from __future__ import annotations

from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.combat import (
    add_attacker,
    add_blocker,
    attack_required,
    block_any_required,
    start_combat,
)
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.legality import _blocker_actions
from commanderblitz.engine.player_statics import block_compelled
from tests.conftest import only_oid

BERZERKER = "t_berzerker"  # attacks or blocks each combat if able
BANNER = "t_blocking_banner"  # creatures your opponents control block if able
BEAR = "t_bear"  # 2/2
MENACER = "t_menacer"  # 3/3 menace


def position(builder, mine, theirs, players: int = 2):
    """Player 0's ``mine`` attacking into player 1's ``theirs``; combat open.

    Player 0 is active, so player 1 -- the Berzerker's controller in most of
    these -- is the defending player.
    """
    game = (
        builder(players=players)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    start_combat(game.state)
    return game


def can_finish(game, defender: int = 1) -> bool:
    return any(
        a.kind is ActionKind.FINISH_DECLARATION for a in _blocker_actions(game.state, defender)
    )


class TestItMustBlock:
    def test_done_is_withheld_until_it_blocks(self, builder):
        game = position(builder, [BEAR], [BERZERKER])
        attacker, kharn = only_oid(game, BEAR, 0), only_oid(game, BERZERKER, 1)
        add_attacker(game.state, attacker, 1)
        assert not can_finish(game), (
            "rule 509.1c: a declaration that leaves out an able required "
            "blocker is not a legal declaration"
        )
        assert combat_mod.unmet_block_requirements(game.state, 1) == [kharn]
        assert add_blocker(game.state, kharn, attacker, 1)
        assert can_finish(game)

    def test_any_attacker_obeys_it(self, builder):
        """No attacker is named, so every one is offered -- unlike provoke."""
        game = position(builder, [BEAR, MENACER], [BERZERKER, BEAR])
        bear, kharn = only_oid(game, BEAR, 0), only_oid(game, BERZERKER, 1)
        add_attacker(game.state, bear, 1)
        assert {
            a.targets[0].id
            for a in _blocker_actions(game.state, 1)
            if a.kind is ActionKind.ADD_BLOCKER and a.source == kharn
        } == {bear}
        add_blocker(game.state, kharn, bear, 1)
        assert can_finish(game)

    def test_it_binds_every_combat_not_one(self, builder):
        """Read live: nothing on the object is spent when blockers lock in."""
        game = position(builder, [BEAR], [BERZERKER])
        kharn = only_oid(game, BERZERKER, 1)
        combat_mod.discharge_block_requirements(game.state)
        game.state.turn += 1
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert block_any_required(game.state, kharn, 1)

    def test_it_reaches_another_player_s_creatures(self, builder):
        """`affects` is a filter, so the static's controller need not control
        the creature it compels."""
        game = position(builder, [BEAR, BANNER], [BEAR])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert block_compelled(game.state, only_oid(game, BEAR, 1))
        assert not can_finish(game)


class TestIfAble:
    def test_with_no_attackers_it_owes_nothing(self, builder):
        game = position(builder, [BEAR], [BERZERKER])
        assert can_finish(game)

    def test_a_tapped_creature_owes_nothing(self, builder):
        game = position(builder, [BEAR], [BERZERKER])
        game.state.objects[only_oid(game, BERZERKER, 1)].tapped = True
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert can_finish(game)

    def test_a_creature_not_under_attack_owes_nothing(self, builder):
        """Multiplayer: it can block only creatures attacking its controller."""
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .battlefield(1, [BERZERKER])
            .battlefield(2, [BEAR])
            .build(advance=False)
        )
        start_combat(game.state)
        add_attacker(game.state, only_oid(game, BEAR, 0), 2)
        assert combat_mod.unmet_block_requirements(game.state, 1) == []

    def test_alone_against_menace_it_owes_nothing(self, builder):
        game = position(builder, [MENACER], [BERZERKER])
        add_attacker(game.state, only_oid(game, MENACER, 0), 1)
        assert can_finish(game)

    def test_against_menace_with_a_partner_it_must_block(self, builder):
        game = position(builder, [MENACER], [BERZERKER, BEAR])
        add_attacker(game.state, only_oid(game, MENACER, 0), 1)
        assert not can_finish(game)


class TestAttacksOrBlocks:
    def test_on_its_own_turn_it_must_attack(self, builder):
        """The other half of the printed line, the `attacks_if_able` beside it."""
        game = builder(players=2).battlefield(0, [BERZERKER]).build(advance=False)
        kharn = only_oid(game, BERZERKER, 0)
        assert attack_required(game.state, kharn)

    def test_and_attacking_is_not_blocking(self, builder):
        """Its controller is never the defending player on its own turn, so
        the blocking half has nothing to say there."""
        game = position(builder, [BERZERKER], [BEAR])
        kharn = only_oid(game, BERZERKER, 0)
        add_attacker(game.state, kharn, 1)
        assert not block_any_required(game.state, kharn, 0)
        assert combat_mod.unmet_attack_requirements(game.state) == []

    def test_on_an_opponent_s_turn_it_need_not_attack(self, builder):
        game = position(builder, [BEAR], [BERZERKER])
        assert not attack_required(game.state, only_oid(game, BERZERKER, 1))

    def test_a_plain_creature_is_free_to_block(self, builder):
        game = position(builder, [BEAR], [BEAR])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert not block_compelled(game.state, only_oid(game, BEAR, 1))
        assert can_finish(game)
