""""Whenever you attack", and a granted ability with no printed duration.

    Clavileño, First of the Blessed — "Whenever you attack, target attacking
    Vampire that isn't a Demon becomes a Demon in addition to its other types.
    It gains 'When this creature dies, draw a card and create a tapped 4/3
    white and black Vampire Demon creature token with flying.'"

**`you_attack`.** The only attack triggers were `attacks` and
`attacks_unblocked`, both per *creature* and both in `OBJECT_SUBJECT_TRIGGERS`.
"Whenever you attack" is one trigger per combat in which its controller declared
one or more attackers, whatever the number — written as `attacks` it would fire
three times on a three-creature swing, and Clavileño would make three Demons.

No new event: `EventType.ATTACKERS_DECLARED` was already emitted once by
`combat.py` after the declaration closes, and nothing had ever listened to it.

**`duration: "permanent"` on `grant_ability`.** `grant_keyword` already drew
this distinction — riot's "or with haste" — and `grant_ability` did not, so
every granted ability went into `until_eot` and was swept at cleanup. Clavileño's
grant prints no duration, so a swept one is a strictly weaker card that looks
identical on the turn it was made.

The two durations live in different lists, because only one of them is swept;
`granted_abilities` reads both alike, so nothing downstream had to learn the
difference.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.zones import destroy, move_object
from tests.conftest import oids_of, settle

ATTACKER_TRIGGER = "t_you_attack"  # "whenever you attack, you gain 1 life"
GRANTER = "t_granter_permanent"  # grants a dies-trigger with no duration
BEAR = "t_bear"


class TestWheneverYouAttack:
    def board(self, builder, attackers: int):
        return (
            builder(players=2)
            .battlefield(0, [ATTACKER_TRIGGER, *([BEAR] * attackers)])
            .library(0, ["swamp"] * 20)
            .active(0)
            .step(Step.BEGIN_COMBAT)
            .max_turns(2)
            .build()
        )

    def swing(self, game) -> int:
        """Declare every legal attacker, and return the life gained."""
        before = game.state.players[0].life
        for _ in range(40):
            decision = game.pending()
            if decision is None:
                break
            actions = game.legal_actions()
            add = [a for a in actions if a.kind is ActionKind.ADD_ATTACKER]
            if add:
                game.apply(add[0])
                continue
            finish = [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            if finish:
                game.apply(finish[0])
                break
            passes = [a for a in actions if a.kind is ActionKind.PASS]
            if not passes:
                break
            game.apply(passes[0])
        settle(game)
        return game.state.players[0].life - before

    def test_one_attacker_triggers_once(self, builder):
        game = self.board(builder, attackers=1)
        assert self.swing(game) == 1

    def test_three_attackers_still_trigger_once(self, builder):
        """The whole difference from `attacks`, which is per creature."""
        game = self.board(builder, attackers=3)
        assert self.swing(game) == 1

    def test_no_attackers_does_not_trigger(self, builder):
        """"Whenever you attack" needs somebody to have attacked."""
        game = self.board(builder, attackers=0)
        before = game.state.players[0].life
        for _ in range(40):
            decision = game.pending()
            if decision is None:
                break
            actions = game.legal_actions()
            finish = [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            if finish:
                game.apply(finish[0])
                break
            passes = [a for a in actions if a.kind is ActionKind.PASS]
            if not passes:
                break
            game.apply(passes[0])
        settle(game)
        assert game.state.players[0].life == before


class TestAGrantWithNoPrintedDuration:
    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .hand(0, [GRANTER])
            .library(0, ["swamp"] * 20)
            .active(0)
            .max_turns(3)
            .build()
        )
        bear = oids_of(game, BEAR)[0]
        granter = next(
            o.oid
            for o in game.state.objects.values()
            if o.zone is Zone.HAND and o.def_id == GRANTER
        )
        move_object(game.state, granter, Zone.BATTLEFIELD)
        settle(game)
        return game, bear

    def test_the_grant_lands_outside_until_eot(self, builder):
        game, bear = self.board(builder)
        obj = game.state.objects[bear]
        assert obj.granted_abilities_permanent, "kept where cleanup does not reach"
        assert not obj.until_eot, "and not in the list that is swept"

    def test_it_survives_the_cleanup_step(self, builder):
        from automtg.engine.turn import clear_until_eot

        game, bear = self.board(builder)
        clear_until_eot(game.state)

        assert game.state.objects[bear].granted_abilities_permanent

    def test_the_granted_trigger_still_fires_afterwards(self, builder):
        from automtg.engine.turn import clear_until_eot

        game, bear = self.board(builder)
        clear_until_eot(game.state)
        hand = len(game.state.players[0].hand)

        destroy(game.state, bear)
        settle(game)

        assert len(game.state.players[0].hand) == hand + 1

    def test_it_is_gone_once_the_creature_leaves(self, builder):
        """712.13a -- a permanent that comes back is a new object."""
        game, bear = self.board(builder)
        destroy(game.state, bear)
        settle(game)

        assert game.state.objects[bear].granted_abilities_permanent == []
