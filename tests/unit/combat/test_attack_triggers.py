"""Two combat primitives the shipped decks did not need.

Both exist for the precons on the roadmap, and both are the kind of thing a
two-player game hides:

`defending` — *"whenever a creature attacks **you**"*. `controller` already says
whose creature is swinging, which is a different question. In a duel the two are
indistinguishable; in a pod, a trigger written with `controller: "opponent"`
fires when one opponent attacks another, and its owner draws a card for a combat
they were not in.

`attacking` on `create_token` — a token put onto the battlefield already
attacking. It is *not* a declared attacker, which is both the real rule and what
stops a token that makes tokens from doing so forever.
"""

from __future__ import annotations

import pytest

from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until


def to_attackers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)


def attack_with(game, oid: int, defender: int):
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(defender),))
    )


def done(game):
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


class TestAttacksYou:
    def test_it_fires_when_the_attack_is_aimed_at_you(self, builder):
        game = (
            builder(players=2)
            .battlefield(1, ["t_judge"])
            .battlefield(0, ["t_bear"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        before = len(game.state.players[1].hand)
        to_attackers(game)
        attack_with(game, only_oid(game, "t_bear", 0), defender=1)
        done(game)
        assert len(game.state.players[1].hand) == before + 1

    def test_it_does_not_fire_when_somebody_else_is_attacked(self, builder):
        """The case a duel cannot show.

        Seat 0 swings at seat 2. Seat 1's judge is not in that combat and must
        not draw -- and `controller: "opponent"` alone would have let it.
        """
        game = (
            builder(players=3)
            .battlefield(1, ["t_judge"])
            .battlefield(0, ["t_bear"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        before = len(game.state.players[1].hand)
        to_attackers(game)
        attack_with(game, only_oid(game, "t_bear", 0), defender=2)
        done(game)
        assert len(game.state.players[1].hand) == before

    def test_it_fires_once_per_attacking_creature(self, builder):
        game = (
            builder(players=2)
            .battlefield(1, ["t_judge"])
            .battlefield(0, ["t_bear", "t_flyer"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        before = len(game.state.players[1].hand)
        to_attackers(game)
        for card_id in ("t_bear", "t_flyer"):
            attack_with(game, only_oid(game, card_id, 0), defender=1)
        done(game)
        assert len(game.state.players[1].hand) == before + 2

    def test_your_own_attack_does_not_trigger_it(self, builder):
        # The judge's controller attacking somebody is not a creature attacking
        # the judge's controller.
        game = (
            builder(players=2)
            .battlefield(0, ["t_judge", "t_bear"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        before = len(game.state.players[0].hand)
        to_attackers(game)
        attack_with(game, only_oid(game, "t_bear", 0), defender=1)
        done(game)
        assert len(game.state.players[0].hand) == before


class TestDefendingIsRejectedWhereItWouldMeanNothing:
    def test_on_a_trigger_that_has_no_defender(self, registry):
        """Accepting it silently is the failure mode the DSL exists to prevent.

        A card reading "whenever a creature you control dies, if it was attacking
        you..." would load, look implemented, and fire on everything.
        """
        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel

        model = CardModel.model_validate(
            {
                "id": "t_bad_defending",
                "name": "Test Bad Defending",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "trigger": {"event": "dies", "defending": "you"},
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="defending"):
            compile_card(model)


class TestATokenCreatedAttacking:
    def test_it_arrives_tapped_and_in_combat(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["t_mobilizer"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        to_attackers(game)
        attack_with(game, only_oid(game, "t_mobilizer", 0), defender=1)
        done(game)

        token = only_oid(game, "t_warrior_token", 0)
        assert game.state.objects[token].tapped
        assert game.state.combat.attacking(token)

    def test_it_attacks_the_player_its_maker_is_attacking(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, ["t_mobilizer"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        to_attackers(game)
        attack_with(game, only_oid(game, "t_mobilizer", 0), defender=2)
        done(game)
        assert game.state.combat.attackers[only_oid(game, "t_warrior_token", 0)] == 2

    def test_it_deals_its_damage(self, builder):
        # The whole point of arriving attacking rather than merely tapped.
        game = (
            builder(players=2)
            .battlefield(0, ["t_mobilizer"])
            .life(1, 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        to_attackers(game)
        attack_with(game, only_oid(game, "t_mobilizer", 0), defender=1)
        done(game)
        pass_until(game, lambda g: int(g.state.step) > int(Step.COMBAT_DAMAGE) or g.over)
        # 2 from the mobilizer, 1 from the token it brought.
        assert game.state.players[1].life == 17

    def test_a_token_that_dies_attacking_is_remembered_as_attacking(self, builder):
        """`was_attacking` is last-known information, and it has to be.

        By the time a leaves-battlefield trigger resolves, the object is out of
        combat and there is nothing left to ask -- so the fact is snapshotted at
        the moment it leaves, the same way `was_creature` already is. This is
        Zurgo's second ability: draw if the token was attacking, drain if not.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["t_stormrender", "t_mobilizer"])
            .battlefield(1, ["t_big"])  # big enough to eat a 1/1 token
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        before_hand = len(game.state.players[0].hand)

        to_attackers(game)
        attack_with(game, only_oid(game, "t_mobilizer", 0), defender=1)
        done(game)
        token = only_oid(game, "t_warrior_token", 0)
        assert game.state.combat.attacking(token)

        # Block the token specifically, so it dies for a reason this test chose
        # rather than one the default answers happened to produce.
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        game.apply(
            find_action(
                game,
                ActionKind.ADD_BLOCKER,
                source=only_oid(game, "t_big", 1),
                targets=(TargetRef.obj(token),),
            )
        )
        done(game)
        pass_until(game, lambda g: int(g.state.step) > int(Step.COMBAT_DAMAGE) or g.over)

        assert token not in game.state.battlefield
        # It died while attacking, so this is the draw half. Getting the two
        # halves the wrong way round is the bug this test exists for.
        assert len(game.state.players[0].hand) == before_hand + 1

    def test_a_token_that_leaves_outside_combat_is_not(self, builder):
        from automtg.engine.enums import Zone
        from automtg.engine.primitives import create_token
        from automtg.engine.zones import move_object

        game = (
            builder(players=2).battlefield(0, ["t_stormrender"]).step(Step.PRECOMBAT_MAIN).build()
        )
        before_hand = len(game.state.players[0].hand)
        before_life = game.state.players[1].life

        # `create_token` rather than `builder.battlefield`: the builder makes an
        # ordinary object, and the trigger filters on `is_token`, so a
        # hand-placed copy would fail to trigger and the test would pass for the
        # wrong reason.
        (token,) = create_token(game.state, "t_warrior_token", 0)
        # Moved directly rather than through a sacrifice outlet: this is a unit
        # test of the snapshot, and a sac cost with two legal creatures on the
        # board would put a choice between the test and what it measures.
        move_object(game.state, token, Zone.GRAVEYARD)
        pass_until(game, lambda g: (not g.state.pending_triggers and not g.state.stack) or g.over)

        # Not attacking, so the other half: each opponent loses a life and
        # nobody draws.
        assert game.state.players[1].life == before_life - 1
        assert len(game.state.players[0].hand) == before_hand

    def test_it_does_not_make_another_token(self, builder):
        """A token created attacking was never *declared* as an attacker.

        That is the real rule, and it is also what keeps this from being an
        infinite loop: each token would otherwise see its own arrival as an
        attack and make another.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["t_mobilizer"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        to_attackers(game)
        attack_with(game, only_oid(game, "t_mobilizer", 0), defender=1)
        done(game)
        tokens = [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == "t_warrior_token"
        ]
        assert len(tokens) == 1

    def test_it_is_sacrificed_at_the_next_end_step(self, builder):
        """Mobilize's second sentence: "Sacrifice it at the beginning of the next
        end step." Unblocked, the token survives combat and deals its damage;
        nothing else removes it, so its absence once the turn is over is the
        sacrifice."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_mobilizer"])
            .life(1, 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        turn = game.state.turn
        to_attackers(game)
        attack_with(game, only_oid(game, "t_mobilizer", 0), defender=1)
        done(game)
        token = only_oid(game, "t_warrior_token", 0)

        pass_until(game, lambda g: g.state.turn != turn or g.over)
        assert game.state.players[1].life == 17, "the token connected first"
        assert token not in game.state.battlefield
        sacrificed = [
            e for e in game.state.events if e.type is EventType.SACRIFICED and e.data.get("oid") == token
        ]
        assert sacrificed
