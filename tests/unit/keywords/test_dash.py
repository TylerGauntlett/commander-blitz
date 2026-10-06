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

And then a price. The loader refused any `evoke` cost that was not strictly
cheaper than the printed one, on the sound argument that an alternative nobody
would take is dead weight that reads as a mechanic. That argument is about
*evoke*, which buys nothing with the price but the discount — a Mulldrifter
evoked is a Mulldrifter that dies. Dash buys something: haste, plus the enters
trigger for a turn, before the body goes back. Riders of Rohan (rule 702.108a)
is printed {3}{R}{W} and dashes for {4}{R}{W}, one mana *more*, and players pay
it. So the guard now reads `evoke_label`: evoke proper keeps the discount-only
invariant, a renamed cost may be the dearer one, and a cost *equal* to the
printed one is refused under every label because that is one cast offered twice.
"""

from __future__ import annotations

import copy

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import _default_answer, only_oid

DASHER = "t_dasher"  # 3/2, dash {1}{R}, printed {2}{R}
DEAR_DASHER = "t_dear_dasher"  # 3/3, dash {3}{R}, printed {2}{R} -- Riders' shape

#: A minimal dasher as a dict, so the price guard can be probed at load time.
DASH_CARD = {
    "id": "t_dash_probe",
    "name": "Test Dash Probe",
    "oracle_text": "Dash {1}{R}",
    "mana_cost": "{2}{R}",
    "evoke": "{1}{R}",
    "evoke_label": "dash",
    "types": ["Creature"],
    "subtypes": ["Goblin"],
    "power": 3,
    "toughness": 2,
    "abilities": [
        {
            "kind": "triggered",
            "text": "If you do, it gains haste.",
            "trigger": {
                "event": "self_enters",
                "source": "self",
                "condition": {"evoked": True},
            },
            "effects": [
                {"op": "grant_keyword", "keyword": "haste", "objects": {"self_only": True}}
            ],
        }
    ],
}


def compile_dash(**overrides):
    card = copy.deepcopy(DASH_CARD)
    card.update(overrides)
    return compile_card(CardModel.model_validate(card))


def position(builder, card: str = DASHER, lands: int = 4):
    return (
        builder(players=2)
        .hand(0, [card])
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


class TestADashMayCostMoreThanThePrintedLine:
    """Riders of Rohan: printed {3}{R}{W}, dash {4}{R}{W}. The extra mana is
    not a mistake, it is the price of haste and the enters trigger."""

    def test_a_dearer_dash_loads(self):
        card = compile_dash(evoke="{4}{R}")
        assert card.evoke.mana_value() == 5
        assert card.mana_cost.mana_value() == 3

    def test_the_dearer_line_is_offered(self, builder):
        game = position(builder, DEAR_DASHER)
        assert cast_lines(game) == [
            "Cast Test Dear Dasher",
            "Cast Test Dear Dasher (dash)",
        ]

    def test_it_costs_one_more_than_the_printed_line(self, builder):
        game = position(builder, DEAR_DASHER)
        untapped = lambda: sum(  # noqa: E731
            1
            for o in game.state.battlefield_objects(0)
            if not o.tapped and "Land" in game.state.card_of(o).types
        )
        before = untapped()
        game.apply(dash_line(game))
        settle(game)
        assert before - untapped() == 4, "{3}{R}, one more than the printed {2}{R}"

    def test_the_dearer_line_still_buys_haste_and_the_return(self, builder):
        """What the extra mana is *for*. Loading is not enough — the costlier
        cast must reach the same `evoked` flag the cheap one does."""
        game = position(builder, DEAR_DASHER)
        game.apply(dash_line(game))
        settle(game)
        oid = only_oid(game, DEAR_DASHER, 0)
        assert "haste" in chars(game.state, oid).keywords
        assert [t for t in game.state.delayed_triggers if t.step == "end_step"]


class TestThePriceGuardStillCatchesDeadWeight:
    """Relaxing a guard until it permits anything is not relaxing it. Both
    shapes it existed for are still load errors."""

    def test_a_dearer_evoke_proper_is_still_refused(self):
        """Evoke buys nothing but the discount, so above the printed price it
        is a line no player would ever take — the original error, unchanged."""
        with pytest.raises(DslError, match="not cheaper"):
            compile_dash(evoke="{4}{R}", evoke_label="evoked")

    def test_a_dearer_evoke_is_refused_when_the_label_is_omitted(self):
        card = copy.deepcopy(DASH_CARD)
        card.pop("evoke_label")
        card["evoke"] = "{4}{R}"
        with pytest.raises(DslError, match="not cheaper"):
            compile_card(CardModel.model_validate(card))

    def test_an_equal_price_is_refused_under_the_dash_label(self):
        """The one shape no label can excuse: the same cast offered twice."""
        with pytest.raises(DslError, match="same as the printed cost"):
            compile_dash(evoke="{2}{R}")

    def test_an_equal_price_is_refused_under_the_default_label(self):
        with pytest.raises(DslError, match="same as the printed cost"):
            compile_dash(evoke="{2}{R}", evoke_label="evoked")

    def test_the_boundary_is_one_mana(self):
        """{1}{R} is cheaper and loads, {2}{R} is equal and does not."""
        assert compile_dash(evoke="{1}{R}").evoke.mana_value() == 2
        with pytest.raises(DslError):
            compile_dash(evoke="{2}{R}")
