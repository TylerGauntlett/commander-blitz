"""Read ahead -- 702.155, a Saga that starts part-way through its story.

    "Read ahead (Choose a chapter and start with that many lore counters.
     Add one after your draw step. Skipped chapters don't trigger.
     Sacrifice after III.)"                     -- The Elder Dragon War

`test_saga.py` holds the three things the game does to every Saga. Read ahead
changes exactly one of them, the lore counter it enters with, and adds a rule
about which chapters that first placement wakes. Everything after the arrival
-- the tick, the trigger on reaching, the sacrifice -- is untouched, and
`TestAfterTheArrival` holds that it stays so.

**The choice is part of the arrival (702.155a).** Riot's shape, asked a moment
before the move by `zones.offer_read_ahead` on every route that can stop to
ask, so a Saga cast from hand is asked as it resolves rather than as it is cast,
and one returned from a graveyard is asked the same question.

**Skipped chapters do not trigger.** The Saga enters with N lore counters, and
714.2c read on its own would fire every chapter from I to N, because the count
went from zero past each of them. Read ahead says the ones below N are skipped,
which is the whole value of the keyword: The Elder Dragon War started on III is
a 4/4 Dragon for five mana, not a board wipe, a rummage and a Dragon.

`t_read_ahead_saga` is `t_saga` with the keyword: I draws, II gains 2 life, III
makes a 1/1 Human Soldier, so which chapters triggered reads straight off the
hand, the life total and the battlefield.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine import sagas
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Keyword, Step, Zone
from commanderblitz.engine.events import EventType
from tests.conftest import _default_answer, action_for_card, count_on_battlefield

SAGA = "t_read_ahead_saga"
PLAIN_SAGA = "t_saga"  # the same story without the keyword -- the control
RAISE = "t_read_ahead_raise"  # returns an enchantment card to the battlefield
SEASON = "t_rc_season"  # Doubling Season
TOKEN = "human_soldier_1_1_w"


def position(builder, hand=(SAGA,), *, board=(), graveyard=()):
    """Plains, a library to draw from, and player 0's precombat main phase.

    A spare land in hand as well, so player 0 always has a move left: with
    nothing to do the engine auto-passes into the next turn, and a tick
    asserted afterwards would be the opponent's.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 6)
        .battlefield(0, list(board))
        .hand(0, [*hand, "plains"])
        .graveyard(0, list(graveyard))
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def question(game):
    """The pending read-ahead question, or None."""
    pending = game.pending()
    if pending is None or pending.kind is not DecisionKind.CHOOSE_MODE:
        return None
    if pending.context.get("purpose") != "read_ahead":
        return None
    return pending


def resolve(game, chapter: int | None = None, limit: int = 200) -> list:
    """Resolve everything waiting, taking ``chapter`` when read ahead asks.

    Returns every read-ahead question that was put, so a test can say how many
    there were and who they went to. ``None`` answers passively, which is the
    first option.
    """
    asked = []
    for _ in range(limit):
        pending = question(game)
        if pending is not None:
            asked.append(pending)
            choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
            game.apply(choices[(chapter or 1) - 1])
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return asked
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("never settled")


def cast(game, chapter: int | None = None, card_id: str = SAGA) -> list:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    return resolve(game, chapter)


def find(game, def_id: str):
    return next(o for o in game.state.objects.values() if o.def_id == def_id)


def chapters(game) -> list[int]:
    return [
        e.data["chapter"] for e in game.state.events if e.type == EventType.CHAPTER_REACHED
    ]


def hand_size(game) -> int:
    return len(game.state.players[0].hand)


class TestTheQuestion:
    def test_it_is_one_choose_mode_with_an_option_per_chapter(self, builder):
        game = position(builder)
        asked = cast(game, 1)
        assert len(asked) == 1
        assert [o.label for o in asked[0].options] == [
            "Chapter I: Draw a card.",
            "Chapter II: You gain 2 life.",
            "Chapter III: Create a 1/1 white Human Soldier creature token.",
        ]

    def test_it_goes_to_the_controller(self, builder):
        game = position(builder)
        (asked,) = cast(game, 1)
        assert asked.player == 0

    def test_it_is_asked_on_resolution_not_on_the_cast(self, builder):
        """702.155a: "as this Saga enters". The click from hand casts it with
        no chapter attached, and the question comes as the spell resolves --
        cast, not yet on the battlefield."""
        game = position(builder)
        cast_action = action_for_card(game, ActionKind.CAST, SAGA)
        assert cast_action.choice is None
        game.apply(cast_action)
        assert question(game) is not None
        assert EventType.SPELL_CAST in [e.type for e in game.state.events]
        assert find(game, SAGA).zone is not Zone.BATTLEFIELD

    def test_a_saga_without_the_keyword_is_asked_nothing(self, builder):
        game = position(builder, hand=[PLAIN_SAGA])
        assert cast(game, card_id=PLAIN_SAGA) == []
        assert find(game, PLAIN_SAGA).counter(sagas.LORE) == 1

    def test_the_passive_answer_is_chapter_one(self, builder):
        """What a seat with no opinion takes -- the authoring verifier and the
        CPU strategies -- is the printed default of every other Saga."""
        game = position(builder)
        cast(game)
        assert find(game, SAGA).counter(sagas.LORE) == 1
        assert chapters(game) == [1]


class TestTheChosenChapter:
    @pytest.mark.parametrize("chapter", [1, 2, 3])
    def test_only_the_chosen_chapter_triggers(self, builder, chapter):
        game = position(builder)
        cast(game, chapter)
        assert chapters(game) == [chapter]

    def test_chapter_one_is_an_ordinary_saga(self, builder):
        game = position(builder)
        before = hand_size(game)
        cast(game, 1)
        assert find(game, SAGA).counter(sagas.LORE) == 1
        assert hand_size(game) == before  # cast one, drew one

    def test_chapter_two_skips_the_draw(self, builder):
        game = position(builder)
        before, life = hand_size(game), game.state.players[0].life
        cast(game, 2)
        assert find(game, SAGA).counter(sagas.LORE) == 2
        assert game.state.players[0].life == life + 2
        assert hand_size(game) == before - 1  # the Saga left; nothing was drawn

    def test_chapter_three_makes_the_token_and_is_sacrificed(self, builder):
        """704.5s waits for the final chapter to leave the stack, then bins the
        Saga -- the same sacrifice as one that ticked its way there."""
        game = position(builder)
        cast(game, 3)
        assert count_on_battlefield(game, TOKEN, 0) == 1
        assert game.state.players[0].life == 40
        assert find(game, SAGA).zone is Zone.GRAVEYARD


class TestAfterTheArrival:
    def test_the_next_tick_reaches_the_next_chapter(self, builder):
        game = position(builder)
        cast(game, 2)
        sagas.turn_based_lore(game.state)
        resolve(game)
        assert chapters(game) == [2, 3]
        assert find(game, SAGA).zone is Zone.GRAVEYARD

    def test_a_saga_started_on_one_ticks_through_every_chapter(self, builder):
        game = position(builder)
        cast(game, 1)
        for _ in range(2):
            sagas.turn_based_lore(game.state)
            resolve(game)
        assert chapters(game) == [1, 2, 3]

    def test_it_still_reads_as_having_read_ahead(self, builder):
        game = position(builder)
        cast(game, 2)
        oid = find(game, SAGA).oid
        assert Keyword.READ_AHEAD.value in chars(game.state, oid).keywords


class TestOnePlacement:
    """The chosen number *is* the counter the Saga enters with, not one more
    placement after it: Doubling Season doubles it, and every chapter the
    doubled count reaches from the chosen one up triggers. Only the ones below
    the choice are skipped."""

    def test_doubling_season_doubles_the_chosen_number(self, builder):
        game = position(builder, board=[SEASON])
        cast(game, 1)
        assert chapters(game) == [1, 2]
        assert find(game, SAGA).counter(sagas.LORE) == 2

    def test_the_skipped_chapters_stay_skipped(self, builder):
        game = position(builder, board=[SEASON])
        cast(game, 2)
        assert chapters(game) == [2, 3]


class TestEveryArrivalIsAsked:
    def test_a_returned_saga_is_asked(self, builder):
        """Read ahead is about the Saga entering, not about the cast line."""
        game = position(builder, hand=[RAISE], graveyard=[SAGA])
        life = game.state.players[0].life
        asked = cast(game, 2, card_id=RAISE)
        assert len(asked) == 1
        assert find(game, SAGA).counter(sagas.LORE) == 2
        assert chapters(game) == [2]
        assert game.state.players[0].life == life + 2

    def test_the_choice_does_not_outlive_the_arrival(self, builder):
        """The answer belongs to one arrival (400.7): nothing is left on the
        object for a later one to read."""
        game = position(builder)
        cast(game, 2)
        assert find(game, SAGA).read_ahead_chapter is None
