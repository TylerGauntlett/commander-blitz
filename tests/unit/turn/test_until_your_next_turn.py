""""Until your next turn" on a pump, a keyword grant, an animation and an ability lock.

Rule 611.2b: a continuous effect from a resolving spell or ability that says it
lasts "until your next turn" ends as its controller's next turn begins -- not at
this turn's cleanup (514.2), which is where every until-end-of-turn effect goes.
The engine already had that clock on five tables (block prohibitions,
unblockables, player protection, life locks, cast locks), each cleared in the
granting seat's untap step. It did not have it on the per-object `TempEffect`
list that `pump`, `grant_keyword`, `animate` and `lock_abilities` all write to,
so every one of those ended at cleanup, and a card written with a ``duration``
key loaded and silently wore off before the opponent's turn.

That is the wrong card, not a smaller one. Every witness is a planeswalker +1,
and its whole value is on the turns *between* its controller's:

- **Liliana, the Last Hope** -- "+1: Up to one target creature gets -2/-1 until
  your next turn." The -1 toughness is what kills an X/1 attacker next turn.
- **Dovin Baan** -- "+1: Until your next turn, up to one target creature gets
  -3/-0 and its activated abilities can't be activated."
- **Sorin, Solemn Visitor** -- "+1: Until your next turn, creatures you control
  get +1/+0 and gain lifelink." Lifelink on your blockers.
- **Nissa, Vital Force** -- "+1: … Until your next turn, it becomes a 5/5
  Elemental creature with haste. It's still a land." A blocker that protects
  her.

What is pinned below:

1. The effect survives cleanup and the opponents' whole turns.
2. It ends in the **controller's** untap step -- not the affected permanent's
   controller's -- before anything else happens that turn.
3. An ordinary until-end-of-turn entry beside it still ends at cleanup.
4. An eliminated controller never has that turn, so their entries go with them.
5. The loader refuses a misspelled duration on each op rather than falling back
   to end of turn.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.characteristics import chars
from automtg.engine.costs import mana_sources
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from tests.conftest import only_oid, pass_until

BEAR = "t_bear"  # 2/2
DORK = "t_dork"  # 1/1, {T}: add {G}


def position(builder, *, players: int = 2):
    """Player 0 is active; player 1 has a Bear and a Dork, player 0 a Bear and a Forest.

    Every seat holds a castable instant, so the position stops at a real
    decision on every turn instead of auto-passing whole turns forward.
    Returns ``(game, bear, dork)`` -- player 1's two creatures.
    """
    b = builder(players=players)
    for pid in range(players):
        b.battlefield(pid, ["mountain"]).hand(pid, ["t_bolt"]).library(pid, ["mountain"] * 20)
    game = b.battlefield(0, [BEAR, "forest"]).battlefield(1, [BEAR, DORK]).active(0).build()
    assert game.state.active_player == 0
    return game, only_oid(game, BEAR, 1), only_oid(game, DORK, 1)


def resolve(game, effects, *, target: int | None = None, controller: int = 0) -> None:
    """Resolve ``effects`` as ``controller``'s loyalty ability would, aimed at ``target``."""
    targets = {"t1": (TargetRef.obj(target),)} if target is not None else {}
    ctx = EffectContext(state=game.state, controller=controller, targets=targets)
    list(execute(ctx, effects))


def until_turn_of(game, pid: int) -> None:
    """Pass until ``pid``'s next turn has begun (its untap step has run)."""
    start = game.state.turn
    pass_until(game, lambda g: g.state.turn > start and g.state.active_player == pid)
    assert game.state.active_player == pid and game.state.turn > start


def size(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


SHRINK = {
    "op": "pump",
    "power": -2,
    "toughness": -1,
    "objects": {"target": "t1"},
    "duration": "until_your_next_turn",
}


class TestItOutlastsTheTurn:
    def test_the_pump_is_standing_on_the_opponents_turn(self, builder):
        game, bear, _ = position(builder)
        resolve(game, [SHRINK], target=bear)
        assert size(game, bear) == (0, 1)
        until_turn_of(game, 1)
        assert size(game, bear) == (0, 1), "Liliana's -2/-1 wore off at cleanup"

    def test_it_ends_as_the_controllers_next_turn_begins(self, builder):
        game, bear, _ = position(builder)
        resolve(game, [SHRINK], target=bear)
        until_turn_of(game, 0)
        assert size(game, bear) == (2, 2)

    def test_it_survives_every_opponent_in_a_pod(self, builder):
        """The *controller's* turn ends it, not the next turn anybody takes."""
        game, bear, _ = position(builder, players=3)
        resolve(game, [SHRINK], target=bear)
        until_turn_of(game, 1)
        assert size(game, bear) == (0, 1)
        until_turn_of(game, 2)
        assert size(game, bear) == (0, 1), "the affected creature's controller is not the clock"
        until_turn_of(game, 0)
        assert size(game, bear) == (2, 2)

    def test_an_end_of_turn_pump_beside_it_still_ends_at_cleanup(self, builder):
        game, bear, _ = position(builder)
        resolve(game, [SHRINK], target=bear)
        resolve(game, [{"op": "pump", "power": 3, "toughness": 3, "objects": {"target": "t1"}}],
                target=bear)
        assert size(game, bear) == (3, 4)
        until_turn_of(game, 1)
        assert size(game, bear) == (0, 1)


class TestTheAbilityLock:
    """Dovin Baan: the lock has to bind on the turn the opponent would use it."""

    def test_the_lock_holds_through_the_opponents_turn_and_then_lifts(self, builder):
        game, _, dork = position(builder)
        resolve(
            game,
            [{"op": "lock_abilities", "objects": {"target": "t1"},
              "duration": "until_your_next_turn"}],
            target=dork,
        )
        until_turn_of(game, 1)
        assert game.state.objects[dork].abilities_locked
        sources = {m.oid for m in mana_sources(game.state, 1)}
        assert dork not in sources, "a locked Dork still tapped for mana"
        until_turn_of(game, 0)
        assert not game.state.objects[dork].abilities_locked

    def test_the_plain_lock_is_still_this_turn_only(self, builder):
        game, _, dork = position(builder)
        resolve(game, [{"op": "lock_abilities", "objects": {"target": "t1"}}], target=dork)
        until_turn_of(game, 1)
        assert not game.state.objects[dork].abilities_locked


class TestTheKeywordGrant:
    """Sorin, Solemn Visitor: +1/+0 and lifelink on everything you control."""

    def test_lifelink_and_the_pump_both_last_to_your_next_turn(self, builder):
        game, theirs, _ = position(builder)
        mine = only_oid(game, BEAR, 0)
        resolve(
            game,
            [
                {"op": "pump", "power": 1, "toughness": 0,
                 "objects": {"types": ["Creature"], "controller": "you"},
                 "duration": "until_your_next_turn"},
                {"op": "grant_keyword", "keyword": "lifelink",
                 "objects": {"types": ["Creature"], "controller": "you"},
                 "duration": "until_your_next_turn"},
            ],
        )
        until_turn_of(game, 1)
        assert size(game, mine) == (3, 2)
        assert "lifelink" in chars(game.state, mine).keywords
        assert size(game, theirs) == (2, 2), "only creatures you control"
        until_turn_of(game, 0)
        assert size(game, mine) == (2, 2)
        assert "lifelink" not in chars(game.state, mine).keywords


class TestTheAnimation:
    """Nissa, Vital Force: a land that is a 5/5 haste creature through their turn."""

    def test_the_land_stays_a_creature_with_haste_and_then_stops(self, builder):
        game, _, _ = position(builder)
        land = only_oid(game, "forest", 0)
        resolve(
            game,
            [{"op": "animate", "power": 5, "toughness": 5, "subtypes": ["Elemental"],
              "keywords": ["haste"], "objects": {"target": "t1"},
              "duration": "until_your_next_turn"}],
            target=land,
        )
        until_turn_of(game, 1)
        c = chars(game.state, land)
        assert "Creature" in c.types and "Land" in c.types
        assert (c.power, c.toughness) == (5, 5)
        assert "haste" in c.keywords, "the keyword rides the animation's clock"
        until_turn_of(game, 0)
        c = chars(game.state, land)
        assert "Creature" not in c.types
        assert "haste" not in c.keywords


class TestAnEliminatedControllersClockNeverComes:
    def test_their_entries_are_dropped(self, builder):
        game, bear, _ = position(builder, players=3)
        resolve(game, [SHRINK], target=bear, controller=2)
        assert size(game, bear) == (0, 1)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert size(game, bear) == (2, 2)

    def test_somebody_elses_entries_are_left_alone(self, builder):
        game, bear, _ = position(builder, players=3)
        resolve(game, [SHRINK], target=bear, controller=0)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert size(game, bear) == (0, 1)


class TestTheLoader:
    @staticmethod
    def _card(effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_long_shrink",
                "name": "Test Long Shrink",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "oracle_text": "Target creature gets -2/-1 until your next turn.",
                "targets": [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ],
                "spell_effects": [effect],
            }
        )

    @pytest.mark.parametrize(
        "effect",
        [
            SHRINK,
            {"op": "lock_abilities", "objects": {"target": "t1"},
             "duration": "until_your_next_turn"},
            {"op": "grant_keyword", "keyword": "lifelink", "objects": {"target": "t1"},
             "duration": "until_your_next_turn"},
            {"op": "animate", "power": 5, "toughness": 5, "objects": {"target": "t1"},
             "duration": "until_your_next_turn"},
            {"op": "pump", "power": 1, "toughness": 1, "objects": {"target": "t1"},
             "duration": "until_end_of_turn"},
        ],
    )
    def test_the_durations_load(self, effect):
        compile_card(self._card(effect))

    @pytest.mark.parametrize("op", ["pump", "lock_abilities", "animate", "grant_keyword"])
    def test_a_misspelled_duration_is_refused(self, op):
        effect = {"op": op, "objects": {"target": "t1"}, "duration": "until_next_turn",
                  "power": 1, "toughness": 1, "keyword": "lifelink"}
        with pytest.raises(DslError, match="duration"):
            compile_card(self._card(effect))
