""""Until your next turn, whenever …" -- a delayed trigger on 611.2b's clock,
scoped to more than one object.

    "+1: Choose up to two target creatures. Until your next turn, whenever
    either of those creatures deals combat damage, you draw a card."
                                            -- Tamiyo, Field Researcher

    "+1: Until your next turn, whenever a creature deals combat damage to
    Vraska the Unseen, destroy that creature."   -- Vraska the Unseen

`delayed_trigger` had three lifetimes. `this_turn` and `once_this_turn` end at
cleanup, which is before any opponent can attack -- and an opponent attacking is
the only thing Vraska's +1 is about, and half of what Tamiyo's is.
`until_it_fires` outlives the turn but fires once and never ends on its own, so
Tamiyo would draw one card for the rest of the game's first hit. Neither is a
smaller version of the card; both are different cards.

And the scope held one object. `subject` resolved its selector and kept
``chosen[0]``, so "either of those creatures" watched one of two.

What is pinned below:

1. The subscription repeats, survives cleanup and the opponents' turns, and is
   gone once its controller's next turn begins -- keyed by the controller, so a
   pod's other seats do not end it.
2. Either subject fires it; a creature outside the scope does not.
3. A subject that leaves the battlefield is struck out of the scope (400.7: it
   comes back a new object), and a subscription whose last subject left is
   dropped rather than widened to "any creature".
4. An eliminated controller's subscription goes with them.
5. The loader takes the new duration.
"""

from __future__ import annotations

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.primitives import damage_player
from automtg.engine.structs import TargetRef
from automtg.engine.zones import move_object
from tests.conftest import oids_of, pass_until

BEAR = "t_bear"  # 2/2

WATCH = {
    "op": "delayed_trigger",
    "text": "Until your next turn, whenever either of those creatures deals combat damage, "
    "you draw a card.",
    "duration": "until_your_next_turn",
    "trigger": {
        "event": "deals_combat_damage_to_player",
        "controller": "any",
        "subject": {"target": "t1"},
    },
    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
}


def position(builder, *, players: int = 2):
    """Player 0 is active; every seat has two Bears and a castable instant.

    The instant is what makes the position stop at a real decision each turn
    rather than auto-passing whole turns forward. Returns ``(game, mine, theirs)``
    -- each a list of that seat's two Bears.
    """
    b = builder(players=players)
    for pid in range(players):
        b.battlefield(pid, ["mountain", BEAR, BEAR]).hand(pid, ["t_bolt"])
        b.library(pid, ["mountain"] * 30)
    game = b.active(0).build()
    assert game.state.active_player == 0
    return game, sorted(oids_of(game, BEAR, 0)), sorted(oids_of(game, BEAR, 1))


def watch(game, *subjects: int, controller: int = 0) -> None:
    """Resolve Tamiyo's +1 for ``controller``, aimed at ``subjects``."""
    ctx = EffectContext(
        state=game.state,
        controller=controller,
        targets={"t1": tuple(TargetRef.obj(o) for o in subjects)},
    )
    list(execute(ctx, [WATCH]))


def connect(game, dealer: int, defender: int = 1) -> None:
    """``dealer`` deals combat damage to ``defender``; let the delayed half resolve."""
    damage_player(game.state, defender, 1, dealer, is_combat=True)
    pass_until(
        game,
        lambda g: not g.state.armed_delays
        and not g.state.stack
        and not g.state.pending_triggers,
    )


def hand_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def until_turn_of(game, pid: int) -> None:
    start = game.state.turn
    pass_until(game, lambda g: g.state.turn > start and g.state.active_player == pid)
    assert game.state.active_player == pid and game.state.turn > start


class TestEitherOfThoseCreatures:
    def test_the_first_subject_fires_it(self, builder):
        game, mine, theirs = position(builder)
        watch(game, mine[0], theirs[0])
        before = hand_size(game)
        connect(game, mine[0])
        assert hand_size(game) == before + 1

    def test_the_second_subject_fires_it_too(self, builder):
        """The whole of "either": the old scope kept only the first object."""
        game, mine, theirs = position(builder)
        watch(game, mine[0], theirs[0])
        before = hand_size(game)
        connect(game, theirs[0], defender=0)
        assert hand_size(game) == before + 1

    def test_a_creature_outside_the_scope_does_not(self, builder):
        game, mine, theirs = position(builder)
        watch(game, mine[0], theirs[0])
        before = hand_size(game)
        connect(game, mine[1])
        assert hand_size(game) == before

    def test_it_fires_every_time(self, builder):
        game, mine, theirs = position(builder)
        watch(game, mine[0], theirs[0])
        before = hand_size(game)
        connect(game, mine[0])
        connect(game, mine[0])
        assert hand_size(game) == before + 2


class TestTheClock:
    def test_it_is_live_on_the_opponents_turn(self, builder):
        """Where Vraska's +1 does all its work, and half of Tamiyo's."""
        game, mine, theirs = position(builder)
        watch(game, mine[0], theirs[0])
        until_turn_of(game, 1)
        before = hand_size(game)
        connect(game, theirs[0], defender=0)
        assert hand_size(game) == before + 1

    def test_it_is_gone_once_the_controllers_next_turn_begins(self, builder):
        game, mine, theirs = position(builder)
        watch(game, mine[0], theirs[0])
        until_turn_of(game, 1)
        until_turn_of(game, 0)
        assert game.state.delayed_triggers == []

    def test_another_seats_turn_does_not_end_it(self, builder):
        game, mine, theirs = position(builder, players=3)
        watch(game, mine[0], theirs[0])
        until_turn_of(game, 1)
        until_turn_of(game, 2)
        assert len(game.state.delayed_triggers) == 1
        until_turn_of(game, 0)
        assert game.state.delayed_triggers == []

    def test_a_this_turn_subscription_beside_it_still_ends_at_cleanup(self, builder):
        game, mine, _ = position(builder)
        watch(game, mine[0])
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": (TargetRef.obj(mine[1]),)}
        )
        list(execute(ctx, [{**WATCH, "duration": "this_turn"}]))
        assert len(game.state.delayed_triggers) == 2
        until_turn_of(game, 1)
        assert [d.duration for d in game.state.delayed_triggers] == ["until_your_next_turn"]


class TestASubjectThatLeaves:
    def test_it_is_not_watched_when_it_comes_back(self, builder):
        """400.7: the Bear that returns is a new object, and the oid is not."""
        game, mine, theirs = position(builder)
        watch(game, mine[0], theirs[0])
        move_object(game.state, mine[0], Zone.GRAVEYARD)
        move_object(game.state, mine[0], Zone.BATTLEFIELD)
        before = hand_size(game)
        connect(game, mine[0])
        assert hand_size(game) == before
        connect(game, theirs[0], defender=0)
        assert hand_size(game) == before + 1, "the other subject is still watched"

    def test_the_last_subject_leaving_drops_the_subscription(self, builder):
        """An empty scope must not read as no scope, which is every creature."""
        game, mine, _ = position(builder)
        watch(game, mine[0])
        move_object(game.state, mine[0], Zone.GRAVEYARD)
        assert game.state.delayed_triggers == []
        before = hand_size(game)
        connect(game, mine[1])
        assert hand_size(game) == before


class TestAnEliminatedController:
    def test_their_subscription_is_dropped(self, builder):
        game, mine, theirs = position(builder, players=3)
        watch(game, mine[0], theirs[0], controller=2)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert game.state.delayed_triggers == []

    def test_somebody_elses_is_left_alone(self, builder):
        game, mine, theirs = position(builder, players=3)
        watch(game, mine[0], theirs[0], controller=0)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert len(game.state.delayed_triggers) == 1


class TestTheLoader:
    def test_the_duration_and_a_two_target_scope_load(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_unt_watch",
                    "name": "Test Watch",
                    "mana_cost": "{U}",
                    "types": ["Sorcery"],
                    "oracle_text": WATCH["text"],
                    "targets": [
                        {
                            "id": "t1",
                            "kind": "permanent",
                            "count": 2,
                            "up_to": True,
                            "selector": {"types": ["Creature"]},
                        }
                    ],
                    "spell_effects": [WATCH],
                }
            )
        )
