"""Promise of Loyalty, past what the behaviour gate can see.

    "Each player puts a vow counter on a creature they control and sacrifices
    the rest. Each of those creatures can't attack you or planeswalkers you
    control for as long as it has a vow counter on it."

The gate counts the creatures left; it never declares an attack. Asserted
here: the vowed opponent's creature may not attack the caster or the caster's
planeswalker but may attack anyone else, and the caster's own vowed creature
is free.
"""

from __future__ import annotations

from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind
from tests.conftest import action_for_card, oids_of, only_oid, settle_completely

PROMISE = "promise_of_loyalty"
BEAR = "t_bear"
WALKER = "t_walker"


def cast(builder):
    game = (
        builder(players=3)
        .battlefield(0, [BEAR, WALKER] + ["plains"] * 5)
        .battlefield(1, [BEAR, BEAR])
        .battlefield(2, [BEAR])
        .hand(0, [PROMISE])
        .build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, PROMISE))
    settle_completely(game)
    return game


def test_each_player_keeps_one_vowed_creature(builder):
    game = cast(builder)
    for pid in (0, 1, 2):
        (kept,) = oids_of(game, BEAR, pid)
        assert game.state.objects[kept].counter("vow") == 1


def test_the_vowed_creature_may_not_attack_the_caster_or_their_walker(builder):
    game = cast(builder)
    bear = only_oid(game, BEAR, 1)
    walker = only_oid(game, WALKER, 0)
    assert combat_mod.attack_target_forbidden(game.state, bear, 0)
    assert combat_mod.attack_target_forbidden(game.state, bear, 0, permanent=walker)
    assert not combat_mod.attack_target_forbidden(game.state, bear, 2)


def test_the_casters_own_creature_is_free(builder):
    game = cast(builder)
    bear = only_oid(game, BEAR, 0)
    assert not combat_mod.attack_target_forbidden(game.state, bear, 1)
