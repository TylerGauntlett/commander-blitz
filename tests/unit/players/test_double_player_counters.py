"""Doubling a player's counters: "Double the number of each kind of counter you
have." (Aetheric Amplifier's second mode)

Rule 122.1 puts counters on players as well as permanents, and "double the
number of each kind" is the Deepglow Skate sentence aimed at a player: for every
kind the player already has, put that many more on. Without the op the sentence
could only be written as an `add_energy` beside an `add_poison`, which names two
kinds where the card names "each", and `double_counters` reads permanents alone.
Aetheric Amplifier is the witness.

What the tests below pin, each invisible on screen:

- **Every kind, from the kinds list.** The op reads `PLAYER_COUNTER_KINDS`, so a
  kind at zero stays at zero and each other kind doubles.
- **Only the named player.** "You have" leaves an opponent's counters alone.
- **A placement, not a set.** The extra goes on through the
  `add_poison`/`add_energy` funnels, so Innkeeper's Talent doubles what the
  doubling puts (2 becomes 6) and the log hears the number that arrived; and
  ten poison reached by doubling is lethal (704.5c).
- **The loader refuses** a missing ``player`` and a key the op would ignore.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.player import PLAYER_COUNTER_KINDS
from commanderblitz.engine.primitives import add_player_counters

TALENT = "t_pb_talent"  # Innkeeper's Talent level 3: counters you put are doubled

OP = {"op": "double_player_counters", "player": "you"}


def position(builder, counters: dict[int, dict[str, int]], *, players: int = 2, mine=()):
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
        raise AssertionError("double_player_counters asks no question")


def counts(game, pid: int) -> dict[str, int]:
    return {kind: getattr(game.state.players[pid], kind) for kind in PLAYER_COUNTER_KINDS}


class TestEachKind:
    def test_poison_and_energy_both_double(self, builder):
        game = position(builder, {0: {"poison": 3, "energy": 4}})
        run(game, [OP])
        assert counts(game, 0) == {"poison": 6, "energy": 8}

    @pytest.mark.parametrize("kind", PLAYER_COUNTER_KINDS)
    def test_each_kind_the_model_carries_doubles(self, builder, kind):
        game = position(builder, {0: {kind: 2}})
        run(game, [OP])
        assert getattr(game.state.players[0], kind) == 4

    def test_a_kind_at_zero_stays_at_zero(self, builder):
        game = position(builder, {0: {"energy": 5}})
        game.state.events.clear()
        run(game, [OP])
        assert counts(game, 0) == {"poison": 0, "energy": 10}
        assert not [e for e in game.state.events if e.type is EventType.POISON_ADDED]

    def test_a_player_with_none_gets_none(self, builder):
        game = position(builder, {})
        run(game, [OP])
        assert counts(game, 0) == {"poison": 0, "energy": 0}


class TestWhoseCounters:
    def test_you_not_an_opponent(self, builder):
        game = position(builder, {0: {"energy": 1}, 1: {"poison": 4, "energy": 2}})
        run(game, [OP])
        assert counts(game, 0) == {"poison": 0, "energy": 2}
        assert counts(game, 1) == {"poison": 4, "energy": 2}

    def test_a_player_spec_reaches_other_seats(self, builder):
        game = position(builder, {1: {"poison": 2}, 2: {"energy": 3}}, players=3)
        run(game, [{"op": "double_player_counters", "player": "each_opponent"}])
        assert counts(game, 1) == {"poison": 4, "energy": 0}
        assert counts(game, 2) == {"poison": 0, "energy": 6}


class TestAPlacement:
    def test_a_replacement_that_reaches_players_doubles_the_extra(self, builder):
        """2 energy plus a doubled 2: the Talent sees an effect putting two."""
        game = position(builder, {0: {"energy": 2}}, mine=[TALENT])
        run(game, [OP])
        assert game.state.players[0].energy == 6

    def test_the_event_carries_what_arrived(self, builder):
        game = position(builder, {0: {"energy": 3}})
        game.state.events.clear()
        run(game, [OP])
        (event,) = [e for e in game.state.events if e.type is EventType.ENERGY_ADDED]
        assert (event.player, event.data["amount"], event.data["total"]) == (0, 3, 6)

    def test_ten_poison_by_doubling_is_lethal(self, builder):
        game = position(builder, {1: {"poison": 5}})
        run(game, [{"op": "double_player_counters", "player": "each_opponent"}])
        sba.run(game.state)
        assert game.state.players[1].has_lost

    def test_the_funnel_refuses_a_kind_with_none(self, builder):
        game = position(builder, {})
        with pytest.raises(KeyError):
            add_player_counters(game.state, 0, "rad", 1)


class TestTheLoader:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Double the number of each kind of counter you have.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_printed_shape_loads(self):
        compile_card(self._card(OP))

    def test_a_missing_player_is_refused(self):
        with pytest.raises(DslError, match="needs 'player'"):
            compile_card(self._card({"op": "double_player_counters"}))

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("counter", "energy"),
            ("kinds", ["energy"]),
            ("amount", {"const": 1}),
            ("objects", {"zone": "battlefield"}),
        ],
    )
    def test_a_key_it_would_ignore_is_refused(self, key, value):
        with pytest.raises(DslError, match="takes no"):
            compile_card(self._card({**OP, key: value}))
