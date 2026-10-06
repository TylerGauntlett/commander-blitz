"""Fateseal (701.20a): scrying somebody else's library, and *you* decide.

The census called this "`scry` on another player's library — the op is
hard-wired to the controller". It was the other way round, and the direction
matters. `player` had been a spec on `op_scry` all along, so scrying an
opponent's library already worked; what was hard-wired was the **asker**, to
the library's owner.

So a fateseal written without this change would have loaded, run, and handed the
decision to the opponent — letting them choose what to leave on top of their own
deck. That is not a partial implementation of fateseal; it is the opposite of
it, and nothing about the card or the log would have said so.

`chooser` therefore names who decides, separately from `player` naming whose
library. They are the same person for scry, which is why it took a keyword with
them apart to notice they were one thing.
"""

from __future__ import annotations

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext

BEAR = "t_bear"
WALL = "t_wall"
BIG = "t_big"


def run_scry(game, spec: dict, *, answer_bottom: bool, controller: int = 0):
    """Run one scry, returning the player each decision was put to.

    Read off the **yielded** `PendingDecision` rather than
    `state.pending_decision`: that field is written by `Game.apply` when it
    suspends a resolution, and driving the generator directly never goes
    through it. Reading the field instead reports whatever was there before,
    which is exactly the kind of test that passes while asking the wrong
    player.
    """
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [spec])
    asked: list[int] = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision.player)
            # Indices into the offered options, not oids -- `ask_objects`
            # answers with `[available[i] for i in answer]`.
            chosen = list(range(len(decision.options))) if answer_bottom else []
            decision = gen.send(chosen)
    except StopIteration:
        pass
    return asked


def library_ids(game, pid: int) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].library]


class TestWhoIsAsked:
    def test_scry_asks_the_library_owner(self, builder):
        """The default, and every scry card in the pool."""
        game = builder(players=2).library(0, [BEAR, WALL, BIG]).build(advance=False)
        asked = run_scry(
            game, {"op": "scry", "amount": {"const": 1}}, answer_bottom=False
        )
        assert asked == [0]

    def test_fateseal_asks_the_controller(self, builder):
        """The whole keyword. Asking the owner would let them choose what to
        leave on top of their own deck, which is worse than not having it."""
        game = builder(players=2).library(1, [BEAR, WALL, BIG]).build(advance=False)
        asked = run_scry(
            game,
            {"op": "scry", "amount": {"const": 1}, "player": 1, "chooser": "you"},
            answer_bottom=False,
        )
        assert asked == [0]

    def test_without_a_chooser_the_owner_is_still_asked(self, builder):
        """`player` alone is "that player scries", which some cards do say."""
        game = builder(players=2).library(1, [BEAR, WALL, BIG]).build(advance=False)
        asked = run_scry(
            game, {"op": "scry", "amount": {"const": 1}, "player": 1}, answer_bottom=False
        )
        assert asked == [1]


class TestItActsOnTheRightLibrary:
    def test_the_card_goes_to_the_bottom_of_the_targets_library(self, builder):
        game = builder(players=2).library(1, [BEAR, WALL, BIG]).build(advance=False)
        run_scry(
            game,
            {"op": "scry", "amount": {"const": 1}, "player": 1, "chooser": "you"},
            answer_bottom=True,
        )
        assert library_ids(game, 1) == [WALL, BIG, BEAR]

    def test_leaving_it_on_top_changes_nothing(self, builder):
        game = builder(players=2).library(1, [BEAR, WALL, BIG]).build(advance=False)
        run_scry(
            game,
            {"op": "scry", "amount": {"const": 1}, "player": 1, "chooser": "you"},
            answer_bottom=False,
        )
        assert library_ids(game, 1) == [BEAR, WALL, BIG]

    def test_your_own_library_is_untouched(self, builder):
        game = (
            builder(players=2)
            .library(0, [BIG, BIG, BIG])
            .library(1, [BEAR, WALL, BIG])
            .build(advance=False)
        )
        before = library_ids(game, 0)
        run_scry(
            game,
            {"op": "scry", "amount": {"const": 1}, "player": 1, "chooser": "you"},
            answer_bottom=True,
        )
        assert library_ids(game, 0) == before

    def test_an_empty_library_asks_nothing(self, builder):
        game = builder(players=2).library(1, []).build(advance=False)
        asked = run_scry(
            game,
            {"op": "scry", "amount": {"const": 1}, "player": 1, "chooser": "you"},
            answer_bottom=False,
        )
        assert asked == []


class TestTheCardLoads:
    def test_the_fateseal_card_compiles(self, registry):
        card = registry.get("t_fateseal")
        (effect,) = card.spell_effects
        assert effect["op"] == "scry"
        assert effect["player"] == {"target": "t1"}
        assert effect["chooser"] == "you"
