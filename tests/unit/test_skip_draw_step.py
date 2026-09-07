"""A step that still happens, and a draw that does not.

"Skip your draw step." Necropotence -- and Yawgmoth's Bargain, Solitary
Confinement and the twelve other cards that print this exact sentence.

Rule 504.1 gives the active player one turn-based draw at the start of their
draw step. This is the first continuous effect in the engine that takes a
turn-based action away, and the whole of the design is *how much* it takes:

- **The draw goes.** Obvious, and the only half a naive implementation gets.
- **The step stays.** 500.1 -- skipping a step's turn-based action is not
  skipping the step. `EventType.DRAW_STEP` must still fire, because a Saga's
  lore tick and every "at the beginning of your draw step" trigger hang on it.
  Suppressing the event as well is the tempting one-line version, and it is a
  different game: a Saga under a Necropotence would silently stop advancing and
  nothing on screen would say why.
- **Only the turn-based draw.** A `draw` op resolving off a spell is untouched.
  Necropotence does not stop you casting Ancestral Recall, and an implementation
  that reached into `primitives.draw_cards` instead of the turn walk would.
- **It is the *controller's* draw, not everyone's.** `affects_player: "you"` --
  the opponent keeps drawing. Asserted because a skip written as a global would
  pass every single-player test.

And because it is a player-wide static like `no_hand_limit`, an "as long as…"
clause on it has to be *asked*: `_active_player_statics` exists because four
hand-rolled walks used to drop the condition and grant unconditionally. The
witness for the conditional case here is `t_conditional_skip`.
"""

from __future__ import annotations

from automtg.engine.characteristics import player_skips_draw_step
from automtg.engine.enums import Step, Zone
from automtg.engine.events import EventType
from automtg.engine.zones import move_object
from tests.conftest import pass_until


def board(builder, *, card: str | None = None, opponent: str | None = None, mountain: bool = False):
    """A game where player 0 may carry ``card`` and player 1 may carry ``opponent``.

    Both libraries are stocked deep enough that nothing runs out before the
    assertions do, and both players' draws are observable independently.

    **Both players hold a spare land.** Not decoration: the engine offers
    priority only where a player has something they could do, so a player whose
    draw is skipped and whose hand is empty has no legal action all turn and
    their whole turn passes without ever surfacing a decision. `pass_until` then
    sails through to decking, and every assertion here reads the wrong turn. The
    card in hand is never played -- `_default_answer` passes priority -- it only
    keeps the turn observable.
    """
    mine = [] if card is None else [card]
    if mountain:
        mine = [*mine, "mountain"]
    b = (
        builder(players=2)
        .battlefield(0, mine)
        .hand(0, ["forest"])
        .hand(1, ["forest"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
    )
    if opponent is not None:
        b = b.battlefield(1, [opponent])
    return b.build()


def library_size(game, pid: int) -> int:
    return len(game.state.players[pid].library)


def at_main_of(game, pid: int) -> None:
    """Run until ``pid`` has priority in their own precombat main phase."""
    pass_until(
        game,
        lambda g: g.state.active_player == pid and g.state.step is Step.PRECOMBAT_MAIN,
    )


def take_a_turn(game, pid: int) -> int:
    """Run through ``pid``'s next draw step; return the cards it drew.

    Measured main phase to main phase rather than around the draw step itself,
    for two reasons that both make the obvious version silently pass:

    - The turn-based draw happens as the step is **entered** -- `Game._run`
      drives `_draw_step` to completion before anybody gets priority -- so a
      before/after taken once ``state.step is Step.DRAW`` holds is taken after
      the card is already in hand, and reads zero whether or not the skip works.
    - Priority is not offered in an empty upkeep or draw step at all, so
      `pass_until` can never stop on one; waiting for `Step.UPKEEP` waits forever.

    Nothing else in this position draws, so the difference across the turn
    boundary is exactly that one draw step.
    """
    at_main_of(game, pid)
    before = library_size(game, pid)
    pass_until(game, lambda g: g.state.active_player != pid)
    at_main_of(game, pid)
    return before - library_size(game, pid)


class TestTheDrawIsSkipped:
    def test_a_normal_turn_draws_one(self, builder):
        """The control: without the static, the draw step draws."""
        game = board(builder)
        assert take_a_turn(game, 0) == 1

    def test_the_static_stops_the_draw(self, builder):
        game = board(builder, card="t_necro_skip")
        assert player_skips_draw_step(game.state, 0)
        assert take_a_turn(game, 0) == 0

    def test_it_stops_every_later_draw_step_too(self, builder):
        """A continuous effect, not a one-shot -- unlike "skip your *next* untap step"."""
        game = board(builder, card="t_necro_skip")
        assert take_a_turn(game, 0) == 0
        assert take_a_turn(game, 0) == 0

    def test_the_opponent_still_draws(self, builder):
        """`affects_player: "you"`. A global skip passes every one-sided test."""
        game = board(builder, card="t_necro_skip")
        assert not player_skips_draw_step(game.state, 1)
        assert take_a_turn(game, 1) == 1


class TestTheStepStillHappens:
    def test_the_draw_step_event_still_fires(self, builder):
        """500.1: the turn-based action is skipped, the step is not.

        The Saga tick and every "at the beginning of your draw step" trigger read
        this event, so an implementation that skipped the whole step would take
        them out silently.
        """
        game = board(builder, card="t_necro_skip")
        take_a_turn(game, 0)
        assert any(
            event.type == EventType.DRAW_STEP and event.player == 0
            for event in game.state.events
        )

    def test_the_turn_reaches_its_later_steps(self, builder):
        """A skipped draw does not strand the turn in the beginning phase."""
        game = board(builder, card="t_necro_skip")
        take_a_turn(game, 0)
        assert game.state.step is Step.PRECOMBAT_MAIN
        assert game.state.active_player == 0


class TestOnlyTheTurnBasedDraw:
    def test_a_draw_effect_still_draws(self, builder):
        """Necropotence does not stop you casting a draw spell."""
        from automtg.engine.primitives import draw_cards

        game = board(builder, card="t_necro_skip")
        before = library_size(game, 0)
        draw_cards(game.state, 0, 2)
        assert before - library_size(game, 0) == 2


class TestTheConditionIsAsked:
    def test_no_mountain_means_no_skip(self, builder):
        """The "as long as" clause is honoured, not dropped."""
        game = board(builder, card="t_conditional_skip")
        assert not player_skips_draw_step(game.state, 0)
        assert take_a_turn(game, 0) == 1

    def test_with_a_mountain_the_draw_is_skipped(self, builder):
        game = board(builder, card="t_conditional_skip", mountain=True)
        assert player_skips_draw_step(game.state, 0)
        assert take_a_turn(game, 0) == 0

    def test_it_wears_off_when_the_source_leaves(self, builder):
        """A continuous effect lives only as long as its source is on the battlefield."""
        game = board(builder, card="t_necro_skip")
        assert take_a_turn(game, 0) == 0
        source = next(
            obj.oid for obj in game.state.battlefield_objects(0) if obj.def_id == "t_necro_skip"
        )
        move_object(game.state, source, Zone.GRAVEYARD)
        assert not player_skips_draw_step(game.state, 0)
        assert take_a_turn(game, 0) == 1
