"""Dash and blitz: `evoke` is more general than its name.

The census routes dash as "an alternative cost, plus haste and a delayed
return", and blitz as the same with a sacrifice. Checking that against the
vocabulary rather than the description, all three parts already existed:

- ``evoke`` is an alternative mana cost offered from hand, plus a flag the card
  reads back with the `evoked` condition. Nothing in the engine sacrifices an
  evoked creature — Mulldrifter's own trigger does that. So `evoke` is not
  "the evoke keyword", it is *the mechanism* evoke, dash and blitz share.
- `grant_keyword` gives haste.
- `delay` schedules the return for the next end step.

So dash needed no engine work, and this file exists to hold that claim down.

What it *did* need was a label. The action list said "Cast Test Dasher
(evoked)" for a card that says dash — visible, on screen, and wrong about what
the player is buying. `evoke_label` is what the card calls its own cost, and it
is the whole change behind this test.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import _default_answer, only_oid

DASHER = "t_dasher"  # 3/2, dash {1}{R}, printed {2}{R}


def position(builder, lands: int = 4):
    return (
        builder(players=2)
        .hand(0, [DASHER])
        .battlefield(0, ["mountain"] * lands)
        .build()
    )


def cast_lines(game) -> list[str]:
    return [a.label for a in game.legal_actions() if a.kind is ActionKind.CAST]


def dash_line(game):
    (action,) = [
        a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.evoked
    ]
    return action


def settle(game, limit: int = 40) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


class TestTheDashCost:
    def test_both_prices_are_offered(self, builder):
        game = position(builder)
        assert cast_lines(game) == ["Cast Test Dasher", "Cast Test Dasher (dash)"]

    def test_the_line_is_called_dash_not_evoked(self, builder):
        """The one thing this needed. `evoke` is the mechanism; "evoked" is
        only one of the words printed on top of it."""
        game = position(builder)
        assert "(dash)" in dash_line(game).label
        assert "evoked" not in dash_line(game).label

    def test_it_costs_less(self, builder):
        game = position(builder)
        untapped = lambda: sum(  # noqa: E731
            1
            for o in game.state.battlefield_objects(0)
            if not o.tapped and "Land" in game.state.card_of(o).types
        )
        before = untapped()
        game.apply(dash_line(game))
        settle(game)
        assert before - untapped() == 2, "{1}{R}, not {2}{R}"


class TestWhatDashingDoes:
    def dash_it(self, builder):
        game = position(builder)
        game.apply(dash_line(game))
        settle(game)
        return game, only_oid(game, DASHER, 0)

    def test_it_has_haste(self, builder):
        game, oid = self.dash_it(builder)
        assert "haste" in chars(game.state, oid).keywords

    def test_a_return_is_scheduled(self, builder):
        game, _ = self.dash_it(builder)
        assert [t for t in game.state.delayed_triggers if t.step == "end_step"]

    def test_it_goes_back_to_hand_at_end_of_turn(self, builder):
        game, oid = self.dash_it(builder)
        for _ in range(80):
            if game.state.objects[oid].zone is Zone.HAND:
                break
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            game.apply(_default_answer(game, decision))
        assert game.state.objects[oid].zone is Zone.HAND

    def test_casting_it_normally_does_neither(self, builder):
        """The condition on the trigger is the whole of "if you do"."""
        game = position(builder)
        printed = next(
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and not a.evoked
        )
        game.apply(printed)
        settle(game)
        oid = only_oid(game, DASHER, 0)
        assert "haste" not in chars(game.state, oid).keywords
        assert not game.state.delayed_triggers


class TestTheDefaultIsUnchanged:
    def test_an_ordinary_evoke_card_still_says_evoked(self, builder):
        """`evoke_label` defaults, so no shipped card changed."""
        game = (
            builder(players=2)
            .hand(0, ["t_evoker"])
            .battlefield(0, ["island"] * 6)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        labels = [a.label for a in game.legal_actions() if a.kind is ActionKind.CAST]
        assert any("(evoked)" in label for label in labels)
