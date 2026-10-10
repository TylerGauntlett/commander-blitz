""""As this land enters, you may pay 2 life. If you don't, it enters tapped."

The shock lands, and two fixes.

THE READING. The proxy generator read "enters tapped unless ..." and had no
reading for this sentence, which has no "unless" in it -- so it fell through to
the unconditional tapland, and all ten shock lands (and Mystic Peak, at 3 life)
shipped as duals that could never enter untapped. `unless_cost` on the
replacement was the shape all along; only the reading was missing.

THE CHOICE IS A LAND DROP. Paying is offered as one of two land drops
(`Action.enters_paid`) rather than asked mid-drop, so every seat answers it by
picking an action -- an agent, the heuristic AI, or a game run headless with no
UI to draw a question. `legality._land_drops` offers the pair;
`zones.offer_enters_costs` honours the answer and asks nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from commanderblitz.cards.proxy import _enters_tapped
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.zones import enters_cost_prompt
from tests.conftest import _default_answer

SHOCKS = [
    "blood_crypt",
    "breeding_pool",
    "godless_shrine",
    "hallowed_fountain",
    "overgrown_tomb",
    "sacred_foundry",
    "steam_vents",
    "stomping_ground",
    "temple_garden",
    "watery_grave",
]


def drops(game) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]


def play(builder, land: str, *, pay: bool, life: int = 40):
    game = builder(players=2).hand(0, [land]).build()
    game.state.players[0].life = life
    line = next(a for a in drops(game) if a.enters_paid in (pay, None))
    oid = line.source
    game.apply(line)
    asked = False
    while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
        asked = asked or p.kind is DecisionKind.MAY
        game.apply(_default_answer(game, p))
    return game, game.state.objects[oid], asked


class TestTwoLandDrops:
    def test_a_shock_land_is_two_drops(self, builder):
        game = builder(players=2).hand(0, ["blood_crypt"]).build()
        offered = drops(game)
        assert sorted(a.enters_paid for a in offered) == [False, True]
        # One row on the client, two chips: the base label is shared.
        assert {a.base_label for a in offered} == {"Play Blood Crypt"}
        assert {a.option_label for a in offered} == {"Pay 2 life, untapped", "Tapped"}

    def test_a_basic_is_one_drop(self, builder):
        game = builder(players=2).hand(0, ["forest"]).build()
        [line] = drops(game)
        assert line.enters_paid is None

    def test_at_two_life_there_is_only_the_tapped_drop(self, builder):
        """Paying would be unaffordable, so it is not offered -- the rule
        `offer_enters_costs` has always kept by not asking."""
        game = builder(players=2).hand(0, ["blood_crypt"]).build()
        game.state.players[0].life = 1
        [line] = drops(game)
        assert line.enters_paid is None


class TestTheDropDecides:
    @pytest.mark.parametrize("land", SHOCKS)
    def test_paying_two_life_enters_untapped(self, builder, land):
        game, obj, asked = play(builder, land, pay=True)
        assert not asked, "the drop carried the answer; nothing is asked"
        assert not obj.tapped
        assert game.state.players[0].life == 38

    @pytest.mark.parametrize("land", SHOCKS)
    def test_declining_enters_tapped(self, builder, land):
        game, obj, asked = play(builder, land, pay=False)
        assert not asked
        assert obj.tapped
        assert game.state.players[0].life == 40

    def test_mystic_peak_costs_three(self, builder):
        game, obj, _ = play(builder, "mystic_peak", pay=True)
        assert not obj.tapped
        assert game.state.players[0].life == 37


class TestTheQuestionWhereItIsStillAsked:
    """A permanent put onto the battlefield some other way still gets the
    question, and it names the price."""

    def test_it_names_the_price(self):
        replacement = {"event": "self_enters_tapped", "unless_cost": {"pay_life": 2}}
        from commanderblitz.engine.carddef import Cost

        prompt = enters_cost_prompt(replacement, Cost(pay_life=2), "Blood Crypt")
        assert prompt == "Pay 2 life so Blood Crypt enters untapped?"


class TestTheGeneratorReadsIt:
    def facts(self, text: str):
        return SimpleNamespace(oracle_text=text)

    def test_a_shock_land_gets_its_price(self):
        text = "({T}: Add {B} or {R}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped."
        [replacement], notes, _ = _enters_tapped(self.facts(text), ["Land"])
        assert replacement == {"event": "self_enters_tapped", "unless_cost": {"pay_life": 2}}
        assert notes == []

    def test_a_plain_tapland_is_unchanged(self):
        [replacement], _, _ = _enters_tapped(self.facts("This land enters tapped."), ["Land"])
        assert replacement == {"event": "self_enters_tapped"}
