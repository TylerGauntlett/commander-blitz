""""As this land enters, you may pay 2 life. If you don't, it enters tapped."

The shock lands. The proxy generator read "enters tapped unless ..." and had no
reading for this sentence, which has no "unless" in it -- so it fell through to
the unconditional tapland, and all ten shock lands (and Mystic Peak, at 3 life)
shipped as duals that could never enter untapped. Playtest: "no ability to pay
the life". The engine already had the shape -- `unless_cost` on the
replacement, asked by `zones.offer_enters_costs` -- and only the reading was
missing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from automtg.cards.proxy import _enters_tapped
from automtg.engine.enums import ActionKind, DecisionKind
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


def play(builder, land: str, *, pay: bool):
    game = builder(players=2).hand(0, [land]).build()
    line = next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND)
    oid = line.source
    game.apply(line)
    asked = False
    while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
        if p.kind is DecisionKind.MAY:
            asked = True
            want = ActionKind.YES if pay else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        game.apply(_default_answer(game, p))
    return game, game.state.objects[oid], asked


class TestTheChoiceIsOffered:
    @pytest.mark.parametrize("land", SHOCKS)
    def test_paying_two_life_enters_untapped(self, builder, land):
        game, obj, asked = play(builder, land, pay=True)
        assert asked, "the player is asked whether to pay"
        assert not obj.tapped
        assert game.state.players[0].life == 38

    @pytest.mark.parametrize("land", SHOCKS)
    def test_declining_enters_tapped(self, builder, land):
        game, obj, _ = play(builder, land, pay=False)
        assert obj.tapped
        assert game.state.players[0].life == 40

    def test_the_question_names_the_price(self, builder):
        """"Pay Blood Crypt's cost?" asked the player to remember the card."""
        game = builder(players=2).hand(0, ["blood_crypt"]).build()
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND))
        decision = game.pending()
        assert decision.kind is DecisionKind.MAY
        assert decision.prompt == "Pay 2 life so Blood Crypt enters untapped?"

    def test_mystic_peak_asks_three(self, builder):
        game, obj, asked = play(builder, "mystic_peak", pay=True)
        assert asked and not obj.tapped
        assert game.state.players[0].life == 37


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
