"""A timed "cast as though it had flash", granted by a resolving effect.

    Teferi, Time Raveler — "+1: Until your next turn, you may cast sorcery
    spells as though they had flash."

`cast_as_though_flash` existed only as a static -- no duration, no spell filter
-- and a loyalty ability leaves no permanent behind to carry one. Granting the
flash keyword is the tempting substitute and is wrong: `_timing_ok` reads
printed keywords, and the permission must cover cards drawn *after* the +1
resolved. So the op writes a per-player timed permission that `_timing_ok`
reads.

The claims:

- **Sorceries only.** A creature spell is still sorcery-speed.
- **Only the granting player.** The opponent gains nothing.
- **Until your next turn.** It survives the opponent's turn and goes in your
  own untap step -- not at this turn's cleanup.
- **A "can't" still wins.** Teferi's own static on an opponent's board is
  `cast_only_at_sorcery_speed`, asked first.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.casting import _timing_ok
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.temp_effects import clear_flash_permissions

GRANT = {"op": "grant_flash_permission", "types": ["Sorcery"], "duration": "until_your_next_turn"}


def a_game(builder):
    return builder(players=2).battlefield(0, ["plains"]).battlefield(1, ["forest"]).build(
        advance=False
    )


def grant(game, controller=0, spec=GRANT):
    ctx = EffectContext(state=game.state, controller=controller)
    for _ in execute(ctx, [spec]):
        pass


@pytest.fixture
def cards(registry):
    return registry.get("divination"), registry.get("grizzly_bears")


class TestSorceriesOnly:
    def test_a_sorcery_may_be_cast_at_instant_speed(self, builder, cards):
        game = a_game(builder)
        divination, _ = cards
        assert not _timing_ok(game.state, 0, divination, sorcery_speed=False)
        grant(game)
        assert _timing_ok(game.state, 0, divination, sorcery_speed=False)

    def test_a_creature_stays_sorcery_speed(self, builder, cards):
        game = a_game(builder)
        _, bears = cards
        grant(game)
        assert not _timing_ok(game.state, 0, bears, sorcery_speed=False)


class TestOnlyTheGrantingPlayer:
    def test_the_opponent_gains_nothing(self, builder, cards):
        game = a_game(builder)
        divination, _ = cards
        grant(game)
        assert not _timing_ok(game.state, 1, divination, sorcery_speed=False)


class TestUntilYourNextTurn:
    def test_this_turns_cleanup_does_not_end_it(self, builder, cards):
        game = a_game(builder)
        divination, _ = cards
        grant(game)
        clear_flash_permissions(game.state, "this_turn")
        assert _timing_ok(game.state, 0, divination, sorcery_speed=False)

    def test_the_opponents_untap_does_not_end_it(self, builder, cards):
        game = a_game(builder)
        divination, _ = cards
        grant(game)
        clear_flash_permissions(game.state, "until_your_next_turn", 1)
        assert _timing_ok(game.state, 0, divination, sorcery_speed=False)

    def test_your_own_untap_ends_it(self, builder, cards):
        game = a_game(builder)
        divination, _ = cards
        grant(game)
        clear_flash_permissions(game.state, "until_your_next_turn", 0)
        assert not _timing_ok(game.state, 0, divination, sorcery_speed=False)


class TestTheLoaderGuard:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_flash_grant",
                "name": "Test Flash Grant",
                "oracle_text": "You may cast sorcery spells as though they had flash.",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_grant_loads(self):
        compile_card(self._card(GRANT))

    def test_a_duration_is_required(self):
        with pytest.raises(DslError, match="duration"):
            compile_card(self._card({"op": "grant_flash_permission", "types": ["Sorcery"]}))

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(DslError, match="card type"):
            compile_card(self._card({**GRANT, "types": ["Sorceries"]}))
