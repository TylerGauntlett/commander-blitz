"""A timing lock: "Each opponent can cast spells only any time they could cast a sorcery."

Teferi, Time Raveler is the witness. The line narrows a *timing* window, which no
existing static could say: `cant_cast_spells` forbids casting outright, and its
`condition` has no "empty stack" or "main phase" test, so it could not be scoped
to "outside sorcery timing"; `cast_as_though_flash` widens the window, the
opposite direction.

307.1 defines sorcery timing -- the player's own main phase, stack empty -- and
the lock makes every spell those players cast obey it: instants and flash
spells lose their speed, and a `cast_as_though_flash` permission loses its
point, because a "can't" beats a "can" (101.2). So the static is read in
`casting._timing_ok`, the one seam every cast path asks, *before* the flash
branches rather than after them.

It also refuses the casts a resolving effect makes -- cascade, suspend, rebound,
madness, miracle, `cast_copy`. Each happens while a spell or ability is
resolving, and so while the stack is not empty: a player who can cast only when
they could cast a sorcery cannot cast then.

The card is `t_sorcery_timer`, in tests/data/cast_only_at_sorcery_speed.cards.json.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_casts_only_at_sorcery_speed
from commanderblitz.engine.suspend import cast_for_free
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

TIMER = "t_sorcery_timer"  # each opponent casts only at sorcery speed
BARRACUDA = "t_barracuda"  # any player may cast spells as though they had flash
BOLT = "t_bolt"  # {R} instant
SORCERY = "t_sorcery"  # {R} sorcery
BEAR = "t_bear"  # {1}{G} creature
MOUNTAIN = "mountain"


def position(
    builder,
    *,
    lock: bool = True,
    active: int = 1,
    step: Step = Step.PRECOMBAT_MAIN,
    board1: tuple[str, ...] = (),
    hand0: tuple[str, ...] = (),
    hand1: tuple[str, ...] = (BOLT, SORCERY),
):
    """Player 0 holds the lock; player 1 is the opponent it names.

    Both have Mountains and a creature to aim at, so the only thing that can
    withhold a cast is timing. ``active`` and ``step`` place the window.
    """
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * 3 + [BEAR] + ([TIMER] if lock else []))
        .battlefield(1, [MOUNTAIN] * 3 + [BEAR, *board1])
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(step)
        .active(active)
        .build(advance=False)
    )


def castable(game, pid: int) -> set[str]:
    return {
        game.state.objects[a.source].def_id
        for a in legality._priority_actions(game.state, pid)
        if a.kind is ActionKind.CAST
    }


class TestTheLock:
    def test_an_instant_waits_for_sorcery_timing_off_turn(self, builder):
        game = position(builder, active=0)
        assert BOLT not in castable(game, 1)

    def test_without_the_lock_the_instant_is_castable(self, builder):
        """The control: the refusal above is the static's, not the position's."""
        game = position(builder, lock=False, active=0)
        assert BOLT in castable(game, 1)

    def test_in_their_own_main_phase_with_the_stack_empty_both_are_castable(self, builder):
        game = position(builder, active=1)
        assert castable(game, 1) == {BOLT, SORCERY}

    def test_in_their_own_combat_the_instant_waits(self, builder):
        """Their own turn is not enough: 307.1 needs a main phase."""
        game = position(builder, active=1, step=Step.DECLARE_ATTACKERS)
        assert BOLT not in castable(game, 1)

    def test_its_controller_is_unaffected(self, builder):
        game = position(builder, active=1, hand0=(BOLT,))
        assert BOLT in castable(game, 0)
        assert not player_casts_only_at_sorcery_speed(game.state, 0)
        assert player_casts_only_at_sorcery_speed(game.state, 1)


class TestAFlashPermissionDoesNotBeatIt:
    def test_cast_as_though_flash_is_overridden(self, builder):
        """101.2: the "can't" of the lock beats Barracuda's "may"."""
        open_game = position(builder, lock=False, active=0, board1=(BARRACUDA,))
        assert SORCERY in castable(open_game, 1), "the permission works on its own"
        game = position(builder, active=0, board1=(BARRACUDA,))
        assert castable(game, 1) == set()


class TestResolutionTimeCasts:
    def test_a_free_cast_while_something_resolves_is_refused(self, builder):
        """Cascade, suspend and rebound all cast during a resolution."""
        game = position(builder, active=1)
        bolt = next(o for o in game.state.players[1].hand if game.state.objects[o].def_id == BOLT)
        move_object(game.state, bolt, Zone.EXILE, to_player=1)
        assert cast_for_free(game.state, 1, bolt) is False
        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_its_controller_still_casts_for_free(self, builder):
        game = position(builder, active=1, hand0=(BOLT,))
        bolt = game.state.players[0].hand[0]
        move_object(game.state, bolt, Zone.EXILE, to_player=0)
        assert cast_for_free(game.state, 0, bolt) is True


class TestTheWearingOff:
    def test_the_source_leaving_reopens_the_window(self, builder):
        game = position(builder, active=0)
        assert BOLT not in castable(game, 1)
        move_object(game.state, only_oid(game, TIMER), Zone.GRAVEYARD)
        assert BOLT in castable(game, 1)


class TestTheLoader:
    def _card(self, **static) -> dict:
        return {
            "id": "t_bad_timer",
            "name": "Test Bad Timer",
            "oracle_text": "Each opponent can cast spells only any time they could cast a sorcery.",
            "mana_cost": "{1}{W}{U}",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "Each opponent can cast spells only any time they could cast a sorcery.",
                    "effect": "cast_only_at_sorcery_speed",
                    **static,
                }
            ],
        }

    def test_the_seats_are_required(self):
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(self._card()))

    def test_a_filter_is_refused(self):
        card = self._card(affects_player="opponent", affects={"types": ["Creature"]})
        with pytest.raises(DslError, match="cast_only_at_sorcery_speed"):
            compile_card(CardModel.model_validate(card))

    def test_teferis_line_loads(self):
        compile_card(CardModel.model_validate(self._card(affects_player="opponent")))
