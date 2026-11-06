""""Can attack as though it didn't have defender" -- and keeps defender.

Rule 702.3b: a creature with defender can't attack. Felothar the Steadfast,
Assault Formation, Walking Bulwark and Wakestone Gargoyle let it attack anyway
while it keeps the keyword for every other reader; `lose_keyword` would take the
keyword away, and a "creature with defender" filter or an anthem for walls would
stop seeing it -- a different card that reads the same on the board.

Weathered Sentinels waives defender only against "players who attacked you
during their last turn", read off `GameState.attacked_last_turn`: other players,
and every planeswalker, stay off limits, and with nobody to attack it can't
attack at all.

`player_statics.defender_waived` answers all of them; `combat.can_attack` asks it
of a creature with defender and `combat.attack_target_forbidden` per defender.
Pinned below: the static on your creatures only, the keyword kept, the
per-player form, the targeted op and the group op locked in at resolution
(611.2c), and both ops wearing off at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import ALL_DEFENDERS, defender_waived
from commanderblitz.engine.temp_effects import grant_combat_rule
from tests.conftest import keywords, oids_of, only_oid, pass_until, static_probe
from tests.unit.combat.test_goad import defenders_offered, to_declare_attackers, walkers_offered

FELOTHAR = "t_add_felothar"  # creatures you control: attack despite defender
SENTINELS = "t_add_sentinels"  # 2/4 defender; may attack players who attacked you
FORMATION = "t_add_formation"  # {T}: target creature with defender, this turn
GARGOYLE = "t_add_gargoyle"  # {T}: creatures you control with defender, this turn
WALL = "t_wall"  # 0/4 defender
BEAR = "t_bear"
WALKER = "t_walker"


def position(builder, mine=(), theirs=(), *, players=2, step=Step.UNTAP):
    b = builder(players=players)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    return b.active(0).step(step).build()


class TestTheStatic:
    def test_a_wall_may_attack(self, builder):
        game = position(builder, mine=(FELOTHAR, WALL))
        wall = only_oid(game, WALL, 0)
        assert combat_mod.can_attack(game.state, wall)
        to_declare_attackers(game)
        assert defenders_offered(game, wall) == [1]

    def test_the_baseline_wall_may_not(self, builder):
        game = position(builder, mine=(WALL, BEAR))
        assert not combat_mod.can_attack(game.state, only_oid(game, WALL, 0))

    def test_it_keeps_defender(self, builder):
        game = position(builder, mine=(FELOTHAR, WALL))
        assert "defender" in keywords(game, only_oid(game, WALL, 0))

    def test_only_your_creatures(self, builder):
        game = position(builder, mine=(FELOTHAR,), theirs=(WALL,))
        assert defender_waived(game.state, only_oid(game, WALL, 1)) is None

    def test_it_may_attack_a_planeswalker_too(self, builder):
        game = position(builder, mine=(FELOTHAR, WALL), theirs=(WALKER,))
        wall = only_oid(game, WALL, 0)
        to_declare_attackers(game)
        assert walkers_offered(game, wall) == [only_oid(game, WALKER, 1)]

    def test_summoning_sickness_still_applies(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FELOTHAR])
            .battlefield(0, [WALL], sick=True)
            .build()
        )
        assert not combat_mod.can_attack(game.state, only_oid(game, WALL, 0))


class TestOnlyPlayersWhoAttackedYou:
    def board(self, builder, attacked_by=()):
        game = (
            builder(players=3)
            .battlefield(0, [SENTINELS])
            .battlefield(1, [WALKER])
            .active(0)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        for seat in (1, 2):
            seats = frozenset({0}) if seat in attacked_by else frozenset()
            game.state.attacked_last_turn[seat] = (0, seats)
        game._advance()
        return game, only_oid(game, SENTINELS, 0)

    def test_it_may_attack_the_player_who_attacked_you(self, builder):
        game, sentinels = self.board(builder, attacked_by=(1,))
        assert defender_waived(game.state, sentinels) == frozenset({1})
        to_declare_attackers(game)
        assert defenders_offered(game, sentinels) == [1]

    def test_not_that_players_planeswalker(self, builder):
        game, sentinels = self.board(builder, attacked_by=(1,))
        to_declare_attackers(game)
        assert walkers_offered(game, sentinels) == []

    def test_both_when_both_attacked_you(self, builder):
        game, sentinels = self.board(builder, attacked_by=(1, 2))
        to_declare_attackers(game)
        assert defenders_offered(game, sentinels) == [1, 2]

    def test_nobody_attacked_you_so_it_cannot_attack(self, builder):
        game, sentinels = self.board(builder)
        assert defender_waived(game.state, sentinels) == frozenset()
        assert not combat_mod.can_attack(game.state, sentinels)

    def test_an_unrestricted_waiver_beats_it(self, builder):
        game, sentinels = self.board(builder)
        grant_combat_rule(game.state, [sentinels], "attack_despite_defender")
        assert defender_waived(game.state, sentinels) is ALL_DEFENDERS
        assert combat_mod.can_attack(game.state, sentinels)

    def test_the_real_record(self, builder):
        """Player 1 attacks player 0 with a Bear on their turn; on player 0's
        next turn the Sentinels may attack player 1."""
        game = (
            builder(players=2)
            .battlefield(0, [SENTINELS])
            .battlefield(1, [BEAR])
            .active(1)
            .step(Step.UNTAP)
            .build()
        )
        to_declare_attackers(game)
        bear = only_oid(game, BEAR, 1)
        game.apply(
            next(
                a for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == bear
            )
        )
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN)
        assert combat_mod.can_attack(game.state, only_oid(game, SENTINELS, 0))


class TestTheTimedOps:
    def activate(self, game, card_id, target=None):
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and game.state.objects[a.source].def_id == card_id
            and (target is None or any(t.id == target for t in a.targets))
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

    def test_the_target_may_attack(self, builder):
        game = position(builder, mine=(FORMATION, WALL, WALL), step=Step.PRECOMBAT_MAIN)
        wall, other = oids_of(game, WALL, 0)
        self.activate(game, FORMATION, wall)
        assert combat_mod.can_attack(game.state, wall)
        assert not combat_mod.can_attack(game.state, other)
        assert "defender" in keywords(game, wall)

    def test_the_group_is_every_wall_you_control_now(self, builder):
        game = position(builder, mine=(GARGOYLE, WALL, WALL), theirs=(WALL,), step=Step.PRECOMBAT_MAIN)
        self.activate(game, GARGOYLE)
        assert all(combat_mod.can_attack(game.state, w) for w in oids_of(game, WALL, 0))
        assert defender_waived(game.state, only_oid(game, WALL, 1)) is None

    def test_it_ends_at_cleanup(self, builder):
        game = position(builder, mine=(FORMATION, WALL), step=Step.PRECOMBAT_MAIN)
        wall = only_oid(game, WALL, 0)
        self.activate(game, FORMATION, wall)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert defender_waived(game.state, wall) is None


class TestTheLoader:
    def test_the_static_needs_affects(self):
        probe = static_probe({"effect": "attack_despite_defender"})
        with pytest.raises(DslError, match="attack_despite_defender needs an 'affects'"):
            compile_card(CardModel.model_validate(probe))

    def test_the_word_belongs_to_this_effect(self):
        probe = static_probe(
            {"effect": "attacks_if_able", "affects": {"self_only": True},
             "defending": "attacked_you_last_turn"}
        )
        with pytest.raises(DslError, match="only means anything on an attack_despite_defender"):
            compile_card(CardModel.model_validate(probe))

    def test_the_other_word_does_not(self):
        probe = static_probe(
            {"effect": "attack_despite_defender", "affects": {"self_only": True},
             "defending": "opponent_most_life"}
        )
        with pytest.raises(DslError, match="only means anything on an attacks_if_able"):
            compile_card(CardModel.model_validate(probe))

    def test_the_op_needs_objects(self):
        card = CardModel.model_validate(
            {
                "id": "x", "name": "X", "oracle_text": "X.", "mana_cost": "{1}",
                "types": ["Artifact"],
                "abilities": [
                    {"kind": "activated", "text": "X.", "cost": {"tap": True},
                     "effects": [{"op": "attack_despite_defender"}]}
                ],
            }
        )
        with pytest.raises(DslError, match="attack_despite_defender needs 'objects'"):
            compile_card(card)
