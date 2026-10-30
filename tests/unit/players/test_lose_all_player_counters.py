"""Losing all counters: "Each opponent loses all counters." (Final Act)

Rule 122.1 puts counters on players as well as permanents, and "loses all
counters" means every one of every kind -- poison and energy in this model, and
any kind `player.PLAYER_COUNTER_KINDS` comes to list. Without the op nothing
could take a counter off a player at all: `remove_counters` takes one named
kind off *objects*, and `add_poison` and `add_energy` ignore a non-positive
amount. Final Act's fifth mode is the witness.

What the tests below pin, each invisible on screen:

- **Every kind, from the kinds list.** The op reads `PLAYER_COUNTER_KINDS`,
  so a card says "all counters" once and stays right when the list grows.
- **Only the named players.** "Each opponent" leaves the caster's poison and
  energy alone.
- **Through the funnel.** `primitives.remove_player_counters` bumps the
  characteristic cache, so a corrupted static (Skrelv's Hive) switches off the
  moment the opponent's poison is gone, and the log hears one
  ``counter_removed`` per kind that was there and none for a kind that was not.
- **The loader refuses** a missing ``player`` and a narrowing key the op would
  silently ignore.
"""

from __future__ import annotations

import dataclasses

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Keyword
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.player import PLAYER_COUNTER_KINDS, PlayerState
from commanderblitz.engine.primitives import remove_player_counters
from tests.conftest import keywords, only_oid

HIVE = "skrelv_s_hive"  # corrupted: toxic creatures you control have lifelink
MITE = "phyrexian_mite_1_1_c_toxic"

OP = {"op": "lose_all_player_counters", "player": "each_opponent"}


def position(builder, counters: dict[int, dict[str, int]], *, players: int = 3, mine=()):
    """A table with these counters written on these seats, and the cache bumped."""
    game = builder(players=players).battlefield(0, list(mine)).build(advance=False)
    for pid, kinds in counters.items():
        for kind, n in kinds.items():
            setattr(game.state.players[pid], kind, n)
    game.state.bump_chars()
    return game


def run(game, effects, controller: int = 0) -> None:
    ctx = EffectContext(state=game.state, controller=controller)
    for _ in execute(ctx, effects):
        raise AssertionError("lose_all_player_counters asks no question")


def counts(game, pid: int) -> dict[str, int]:
    return {kind: getattr(game.state.players[pid], kind) for kind in PLAYER_COUNTER_KINDS}


def removals(game) -> list:
    return [e for e in game.state.events if e.type is EventType.COUNTER_REMOVED]


class TestEveryKind:
    def test_an_opponent_loses_poison_and_energy(self, builder):
        game = position(builder, {1: {"poison": 7, "energy": 4}})
        run(game, [OP])
        assert counts(game, 1) == {"poison": 0, "energy": 0}

    @pytest.mark.parametrize("kind", PLAYER_COUNTER_KINDS)
    def test_each_kind_the_model_carries_comes_off(self, builder, kind):
        game = position(builder, {1: {kind: 3}})
        run(game, [OP])
        assert getattr(game.state.players[1], kind) == 0

    def test_the_kinds_list_names_player_counter_fields(self):
        fields = {f.name: f for f in dataclasses.fields(PlayerState)}
        for kind in PLAYER_COUNTER_KINDS:
            assert kind in fields, f"{kind!r} is not a PlayerState field"
            assert getattr(PlayerState(pid=0), kind) == 0, "a counter field starts at none"


class TestWhoLosesThem:
    def test_each_opponent_not_just_one(self, builder):
        game = position(builder, {1: {"poison": 2}, 2: {"energy": 5}})
        run(game, [OP])
        assert counts(game, 1) == counts(game, 2) == {"poison": 0, "energy": 0}

    def test_the_caster_keeps_theirs(self, builder):
        game = position(builder, {0: {"poison": 3, "energy": 6}, 1: {"poison": 1}})
        run(game, [OP])
        assert counts(game, 0) == {"poison": 3, "energy": 6}

    def test_each_player_reaches_the_caster_too(self, builder):
        game = position(builder, {0: {"energy": 2}, 1: {"poison": 1}})
        run(game, [{"op": "lose_all_player_counters", "player": "each_player"}])
        assert counts(game, 0) == counts(game, 1) == {"poison": 0, "energy": 0}

    def test_a_player_with_none_is_untouched(self, builder):
        game = position(builder, {})
        game.state.events.clear()
        run(game, [OP])
        assert counts(game, 1) == {"poison": 0, "energy": 0}
        assert not removals(game), "nothing came off, so nothing is said"


class TestThroughTheFunnel:
    def test_one_event_per_kind_that_was_there(self, builder):
        game = position(builder, {1: {"poison": 4, "energy": 2}}, players=2)
        game.state.events.clear()
        run(game, [OP])
        got = {(e.player, e.data["counter"], e.data["amount"], e.data["total"]) for e in removals(game)}
        assert got == {(1, "poison", 4, 0), (1, "energy", 2, 0)}

    def test_a_kind_at_zero_fires_nothing(self, builder):
        game = position(builder, {1: {"energy": 3}}, players=2)
        game.state.events.clear()
        run(game, [OP])
        assert [e.data["counter"] for e in removals(game)] == ["energy"]

    def test_the_primitive_takes_no_more_than_there_is(self, builder):
        game = position(builder, {1: {"poison": 2}}, players=2)
        assert remove_player_counters(game.state, 1, "poison", 5) == 2
        assert game.state.players[1].poison == 0
        assert remove_player_counters(game.state, 1, "poison", 1) == 0

    def test_a_corrupted_static_switches_off(self, builder):
        """No hand bump after the op: the funnel has to invalidate the cache."""
        game = position(builder, {1: {"poison": 3}}, players=2, mine=[HIVE, MITE])
        mite = only_oid(game, MITE, 0)
        assert Keyword.LIFELINK.value in keywords(game, mite)
        run(game, [OP])
        assert Keyword.LIFELINK.value not in keywords(game, mite)


class TestTheLoader:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Each opponent loses all counters.",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_printed_shape_loads(self):
        compile_card(self._card(OP))

    def test_a_missing_player_is_refused(self):
        with pytest.raises(DslError, match="needs 'player'"):
            compile_card(self._card({"op": "lose_all_player_counters"}))

    @pytest.mark.parametrize(
        ("key", "value"),
        [("counter", "poison"), ("kinds", ["poison"]), ("amount", {"const": 1})],
    )
    def test_a_narrowing_key_is_refused(self, key, value):
        with pytest.raises(DslError, match="takes no"):
            compile_card(self._card({**OP, key: value}))

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self._card({**OP, "player": "each_foe"}))
