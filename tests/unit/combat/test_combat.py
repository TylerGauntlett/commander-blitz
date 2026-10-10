"""Combat: declaration, evasion, damage, keywords and commander damage."""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.structs import TargetRef, TempEffect
from tests.conftest import _default_answer, attack_with, find_action, oids_of, only_oid, pass_until


def to_attackers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)


def to_blockers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)


def block_with(game, blocker_oid: int, attacker_oid: int):
    game.apply(
        find_action(
            game,
            ActionKind.ADD_BLOCKER,
            source=blocker_oid,
            targets=(TargetRef.obj(attacker_oid),),
        )
    )


def done(game):
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def resolve_combat(game):
    """Advance until this turn's combat damage has been dealt.

    Nothing usually stops at the end-of-combat step -- with no responses
    available the engine auto-passes straight through it -- so the exit condition
    is "past the damage step, or into another turn".
    """
    start = game.state.turn
    for _ in range(60):
        if game.over:
            return
        if game.state.turn != start or int(game.state.step) > int(Step.COMBAT_DAMAGE):
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("combat did not resolve")


class TestDeclaringAttackers:
    def test_unblocked_attacker_damages_the_defending_player(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build()
        to_attackers(game)
        attack_with(game, only_oid(game, "t_bear", 0))
        done(game)
        resolve_combat(game)
        assert game.state.players[1].life == 38

    def test_attacking_taps_the_creature(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build()
        to_attackers(game)
        bear = only_oid(game, "t_bear", 0)
        attack_with(game, bear)
        done(game)
        assert game.state.objects[bear].tapped

    def test_vigilance_attacks_untapped(self, builder):
        game = builder().battlefield(0, ["t_vigilant"]).build()
        to_attackers(game)
        oid = only_oid(game, "t_vigilant", 0)
        attack_with(game, oid)
        done(game)
        assert not game.state.objects[oid].tapped

    def test_summoning_sick_creatures_cannot_attack(self, builder):
        from commanderblitz.engine.combat import can_attack

        game = builder().battlefield(0, ["t_bear"], sick=True).build()
        bear = only_oid(game, "t_bear", 0)
        assert not can_attack(game.state, bear)
        # With no legal attackers the engine never even asks.
        assert game.pending().kind is not DecisionKind.DECLARE_ATTACKERS

    def test_haste_ignores_summoning_sickness(self, builder):
        game = builder().battlefield(0, ["t_hasty"], sick=True).build()
        to_attackers(game)
        attack_with(game, only_oid(game, "t_hasty", 0))
        done(game)
        resolve_combat(game)
        assert game.state.players[1].life == 38

    def test_defender_keyword_cannot_attack(self, builder):
        game = builder().battlefield(0, ["t_wall", "t_bear"]).build()
        to_attackers(game)
        sources = {a.source for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER}
        assert only_oid(game, "t_wall", 0) not in sources
        assert only_oid(game, "t_bear", 0) in sources

    def test_tapped_creatures_cannot_attack(self, builder):
        from commanderblitz.engine.combat import can_attack

        game = builder().battlefield(0, ["t_bear"], tapped=True).build()
        # The untap step has not run for a battlefield placed mid-turn.
        assert not can_attack(game.state, only_oid(game, "t_bear", 0))


class TestBlocking:
    def test_a_block_stops_the_damage(self, builder):
        game = builder().battlefield(0, ["t_bear"]).battlefield(1, ["t_bear"]).build()
        to_attackers(game)
        attacker = oids_of(game, "t_bear", 0)[0]
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, oids_of(game, "t_bear", 1)[0], attacker)
        done(game)
        resolve_combat(game)
        assert game.state.players[1].life == 40

    def test_mutual_destruction(self, builder):
        game = builder().battlefield(0, ["t_bear"]).battlefield(1, ["t_bear"]).build()
        to_attackers(game)
        attacker = oids_of(game, "t_bear", 0)[0]
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, oids_of(game, "t_bear", 1)[0], attacker)
        done(game)
        resolve_combat(game)
        assert not oids_of(game, "t_bear")

    def test_flying_cannot_be_blocked_by_ground_creatures(self, builder):
        game = builder().battlefield(0, ["t_flyer"]).battlefield(1, ["t_bear"]).build()
        to_attackers(game)
        attack_with(game, only_oid(game, "t_flyer", 0))
        done(game)
        to_blockers(game)
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER]

    def test_reach_blocks_flying(self, builder):
        game = builder().battlefield(0, ["t_flyer"]).battlefield(1, ["t_reacher"]).build()
        to_attackers(game)
        attacker = only_oid(game, "t_flyer", 0)
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        assert [a for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER]

    def test_menace_requires_two_blockers(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_menacer"])
            .battlefield(1, ["t_bear", "t_flyer"])
            .build()
        )
        to_attackers(game)
        attacker = only_oid(game, "t_menacer", 0)
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, oids_of(game, "t_bear", 1)[0], attacker)
        # One blocker on a menacing attacker is an illegal declaration.
        assert not [
            a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION
        ]
        block_with(game, oids_of(game, "t_flyer", 1)[0], attacker)
        assert [a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION]

    def test_tapped_creatures_cannot_block(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_bear"])
            .battlefield(1, ["t_flyer"], tapped=True)
            .build()
        )
        to_attackers(game)
        attack_with(game, only_oid(game, "t_bear", 0))
        done(game)
        to_blockers(game)
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER]


class TestKeywordDamage:
    def test_deathtouch_kills_a_big_blocker(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_deathtoucher"])
            .battlefield(1, ["t_big"])
            .build()
        )
        to_attackers(game)
        attacker = only_oid(game, "t_deathtoucher", 0)
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, only_oid(game, "t_big", 1), attacker)
        done(game)
        resolve_combat(game)
        assert not oids_of(game, "t_big", 1)

    def test_trample_carries_excess_damage_to_the_player(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_trampler"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        to_attackers(game)
        attacker = only_oid(game, "t_trampler", 0)
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, only_oid(game, "t_bear", 1), attacker)
        done(game)
        resolve_combat(game)
        # 5 power, 2 assigned as lethal to the 2/2, 3 tramples over.
        assert game.state.players[1].life == 37

    def test_deathtouch_and_trample_assign_only_one_to_each_blocker(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_trampler"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        trampler = only_oid(game, "t_trampler", 0)
        game.state.objects[trampler].until_eot.append(
            TempEffect(kind="keyword", keyword="deathtouch")
        )
        game.state.bump_chars()
        to_attackers(game)
        attack_with(game, trampler)
        done(game)
        to_blockers(game)
        block_with(game, only_oid(game, "t_bear", 1), trampler)
        done(game)
        resolve_combat(game)
        # Deathtouch makes 1 damage lethal, so 4 trample through.
        assert game.state.players[1].life == 36

    def test_first_strike_kills_before_the_blocker_hits_back(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_first_striker"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        to_attackers(game)
        attacker = only_oid(game, "t_first_striker", 0)
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, only_oid(game, "t_bear", 1), attacker)
        done(game)
        resolve_combat(game)
        assert oids_of(game, "t_first_striker", 0)
        assert not oids_of(game, "t_bear", 1)

    def test_double_strike_deals_damage_twice(self, builder):
        game = builder().battlefield(0, ["t_double_striker"]).build()
        to_attackers(game)
        attack_with(game, only_oid(game, "t_double_striker", 0))
        done(game)
        resolve_combat(game)
        assert game.state.players[1].life == 36

    def test_lifelink_gains_life(self, builder):
        game = builder().battlefield(0, ["t_lifelinker"]).build()
        to_attackers(game)
        attack_with(game, only_oid(game, "t_lifelinker", 0))
        done(game)
        resolve_combat(game)
        assert game.state.players[0].life == 42
        assert game.state.players[1].life == 38

    def test_indestructible_survives_lethal_damage(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_indestructible"])
            .battlefield(1, ["t_big"])
            .build()
        )
        to_attackers(game)
        attacker = only_oid(game, "t_indestructible", 0)
        attack_with(game, attacker)
        done(game)
        to_blockers(game)
        block_with(game, only_oid(game, "t_big", 1), attacker)
        done(game)
        resolve_combat(game)
        assert oids_of(game, "t_indestructible", 0)


class TestCommanderDamage:
    def test_commander_damage_accumulates_and_kills(self, builder):
        game = builder().battlefield(0, ["t_commander"]).life(1, 100).build()
        commander = only_oid(game, "t_commander", 0)
        game.state.objects[commander].is_commander = True

        # 4 power per swing: six attacks take the defender past 21.
        for _ in range(6):
            if game.over:
                break
            pass_until(
                game,
                lambda g: (
                    g.pending() is not None
                    and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
                    and g.state.active_player == 0
                )
                or g.over,
                limit=800,
            )
            if game.over:
                break
            attack_with(game, commander)
            done(game)
            resolve_combat(game)

        assert game.state.players[1].commander_damage_taken.get(0, 0) >= 21
        assert game.over
        assert game.winners == [0]
