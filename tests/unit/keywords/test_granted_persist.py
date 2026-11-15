"""Persist granted until end of turn (702.79a, 611.2c, 603.10a).

    Dusk Legion Sergeant: "{1}{B}, Sacrifice this creature: Each nontoken
    Vampire creature you control gains persist until end of turn."

Persist is a triggered ability, "When this creature dies, if it had no -1/-1
counters on it, return it to the battlefield under its owner's control with a
-1/-1 counter on it" (702.79a). Granting it is therefore the `grant_ability`
op handing over a grantable copy of the same `dies` trigger a printed persist
creature carries, and three things have to hold for that to be the printed
card rather than a near miss:

- The intervening-if reads the counters the creature had *as it died*
  (603.10a). `reset_permanent_state` empties `counters` on the way to the
  graveyard, so the condition reads `counters_had`, snapshotted onto the dies
  event; reading the graveyard card would return a creature that already had a
  -1/-1 counter and loop it until the trigger guard ends the game.
- The grant reaches the permanents matching *as it resolves* (611.2c): a
  Vampire that arrives later never has persist, and the Sergeant itself, gone
  as the cost was paid, never had it.
- The grant is swept at cleanup, so a creature that dies next turn stays dead,
  and a grant from a granter already in the graveyard still fires, because the
  record points at the granter's oid and its card, not at a live permanent.

`t_gp_sergeant` is the Sergeant without its menace; `t_gp_vampire` is a
nontoken Vampire for it to reach.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.state import new_object
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, only_oid, pass_until, settle

SERGEANT = "t_gp_sergeant"
VAMPIRE = "t_gp_vampire"  # a nontoken 3/3 Vampire


def position(builder, mine=(VAMPIRE,)):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 2 + [SERGEANT, *mine])
        .hand(0, ["swamp"])
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    return game, only_oid(game, SERGEANT, 0)


def activate(game, sergeant: int) -> None:
    (action,) = activations(game, sergeant)
    game.apply(action)
    settle(game)


def dies(game, oid: int) -> None:
    move_object(game.state, oid, Zone.GRAVEYARD)
    settle(game)


def zone(game, oid: int) -> Zone:
    return game.state.objects[oid].zone


class TestItPersists:
    def test_a_vampire_returns_with_a_counter(self, builder):
        game, sergeant = position(builder)
        game._advance()
        vampire = only_oid(game, VAMPIRE, 0)
        activate(game, sergeant)
        dies(game, vampire)
        assert zone(game, vampire) is Zone.BATTLEFIELD
        assert game.state.objects[vampire].counter("-1/-1") == 1

    def test_a_vampire_that_had_a_counter_stays_dead(self, builder):
        """603.10a: the condition reads the counters it had as it died."""
        game, sergeant = position(builder)
        game._advance()
        vampire = only_oid(game, VAMPIRE, 0)
        game.state.objects[vampire].add_counter("-1/-1", 1)
        activate(game, sergeant)
        dies(game, vampire)
        assert zone(game, vampire) is Zone.GRAVEYARD

    def test_it_returns_once_and_not_twice(self, builder):
        """The creature that returns is a new object (400.7) the grant does not
        follow, and the counter it returns with is the loop guard anyway."""
        game, sergeant = position(builder)
        game._advance()
        vampire = only_oid(game, VAMPIRE, 0)
        activate(game, sergeant)
        dies(game, vampire)
        dies(game, vampire)
        assert zone(game, vampire) is Zone.GRAVEYARD


class TestWhatTheGrantReaches:
    def test_the_sergeant_itself_was_gone_before_it_resolved(self, builder):
        """611.2c: it pays its own sacrifice, so it is not among the Vampires."""
        game, sergeant = position(builder)
        game._advance()
        activate(game, sergeant)
        assert zone(game, sergeant) is Zone.GRAVEYARD

    def test_a_non_vampire_does_not_persist(self, builder):
        game, sergeant = position(builder, mine=("grizzly_bears",))
        game._advance()
        bears = only_oid(game, "grizzly_bears", 0)
        activate(game, sergeant)
        dies(game, bears)
        assert zone(game, bears) is Zone.GRAVEYARD

    def test_a_vampire_token_is_not_granted_it(self, builder):
        game, sergeant = position(builder, mine=(VAMPIRE, "vampire_1_1_b"))
        token = only_oid(game, "vampire_1_1_b", 0)
        game.state.objects[token].is_token = True
        game._advance()
        vampire = only_oid(game, VAMPIRE, 0)
        activate(game, sergeant)
        granted = [t for t in game.state.objects[token].until_eot if t.kind == "ability"]
        assert granted == []
        assert [t for t in game.state.objects[vampire].until_eot if t.kind == "ability"]

    def test_a_vampire_arriving_afterwards_does_not_have_it(self, builder):
        """611.2c: the set is locked in as the ability resolves."""
        game, sergeant = position(builder, mine=())
        game.state.players[0].hand.append(
            new_object(game.state, VAMPIRE, owner=0, zone=Zone.HAND).oid
        )
        game._advance()
        activate(game, sergeant)
        (latecomer,) = [
            o.oid for o in game.state.objects.values() if o.def_id == VAMPIRE
        ]
        move_object(game.state, latecomer, Zone.BATTLEFIELD)
        dies(game, latecomer)
        assert zone(game, latecomer) is Zone.GRAVEYARD


class TestItWearsOff:
    def test_a_vampire_that_dies_next_turn_stays_dead(self, builder):
        game, sergeant = position(builder)
        game._advance()
        vampire = only_oid(game, VAMPIRE, 0)
        activate(game, sergeant)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        dies(game, vampire)
        assert zone(game, vampire) is Zone.GRAVEYARD
