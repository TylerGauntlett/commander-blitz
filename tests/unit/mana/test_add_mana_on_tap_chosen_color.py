"""``add_mana_on_tap`` conditioned on mana of the source's chosen colour.

    "Whenever a land's ability causes you to add one or more mana of the
    chosen color, add an additional one mana of that color."    -- Caged Sun

Two things Forsaken Monument's ``{"produced": "{C}"}`` could not say.

**The colour is a question about the source.** ``produced`` took one literal
symbol, so the nearest spelling was ``{"types": ["Land"]}`` with no ``produced``
at all -- a card that adds the chosen colour to every land tap, an Island's {U}
included, which is a strictly stronger card than the printed one. ``produced``
now also takes ``{"chosen_color_of": "self"}``, the spelling ``add_mana`` already
uses for Utopia Sprawl, read off the source as the mana is made. Before the
colour is chosen it is met by nothing: the match-nothing default the chosen
colour has everywhere else, and the only safe one inside a payment (605.1a).

**"A land's ability causes you to add" is not "you tap a land for mana".**
106.12 makes "tapped for mana" a mana ability with {T} in its cost; Caged Sun's
trigger (605.1b) reads off any mana ability of a land. Molten Slagheap's "{1},
Remove X storage counters from this land: Add X mana in any combination of {B}
and/or {R}" does not tap, and with red chosen Caged Sun answers it.
``"any_mana_ability": true`` widens the static to it; without the key nothing
changes, so Crypt Ghast and Gauntlet of Power's "tapped for mana" stay tap-only.

Once per ability however much of the colour it made, as Forsaken Monument's
key is: "add **an additional one** mana".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, pay_mana
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _mana_option_label
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from tests.conftest import activations, find_action, oids_of, only_oid, static_probe

SUN = "t_cs_caged_sun"
TAP_ONLY = "t_cs_tap_only"
SLAGHEAP = "t_rcx_slagheap"

G = SYMBOL_INDEX["G"]
U = SYMBOL_INDEX["U"]
R = SYMBOL_INDEX["R"]
B = SYMBOL_INDEX["B"]
C = SYMBOL_INDEX["C"]


def position(builder, mine=(), theirs=(), *, chosen: str | None = "G", source: str = SUN):
    game = (
        builder(players=2)
        .battlefield(0, [source, *mine])
        .battlefield(1, list(theirs))
        .active(0)
        .build(advance=False)
    )
    oid = only_oid(game, source, 0)
    game.state.objects[oid].chosen_color = chosen
    return game, oid


def tap(game, card_id: str, pid: int = 0, ability: int = 0, option: int = 0) -> list[int]:
    oid = oids_of(game, card_id, pid)[0]
    activate_mana_ability(game.state, oid, ability, pid, option)
    return list(game.state.players[pid].mana_pool.amounts)


class TestTheChosenColor:
    def test_a_land_tapped_for_it_makes_one_more(self, builder):
        game, _ = position(builder, ["forest"])
        assert tap(game, "forest")[G] == 2

    def test_a_land_tapped_for_another_color_makes_only_its_own(self, builder):
        """The near miss: without ``produced`` the Island would add {G}."""
        game, _ = position(builder, ["island"])
        pool = tap(game, "island")
        assert (pool[U], pool[G]) == (1, 0)

    def test_the_color_follows_the_choice(self, builder):
        game, _ = position(builder, ["island"], chosen="U")
        assert tap(game, "island")[U] == 2

    def test_nothing_chosen_matches_nothing(self, builder):
        game, _ = position(builder, ["forest"], chosen=None)
        assert tap(game, "forest")[G] == 1

    def test_per_option_on_a_painland(self, builder):
        game, _ = position(builder, ["battlefield_forge"], chosen="R")
        pool = tap(game, "battlefield_forge", ability=1, option=0)
        assert (pool[R], pool[C]) == (2, 0)

    def test_the_painlands_colorless_does_not_count(self, builder):
        game, _ = position(builder, ["battlefield_forge"], chosen="R")
        pool = tap(game, "battlefield_forge", ability=0)
        assert (pool[R], pool[C]) == (0, 1)

    def test_a_nonland_does_not_count(self, builder):
        game, _ = position(builder, ["llanowar_elves"])
        assert tap(game, "llanowar_elves")[G] == 1

    def test_an_opponents_land_does_not_count(self, builder):
        game, _ = position(builder, theirs=["forest"])
        assert tap(game, "forest", pid=1)[G] == 1


class TestPlannerAndPaymentAgree:
    def test_two_forests_pay_four_green(self, builder):
        game, _ = position(builder, ["forest", "forest"])
        assert pay_mana(game.state, 0, ManaCost.parse("{G}{G}{G}{G}").with_x(0))

    def test_not_with_another_color_chosen(self, builder):
        game, _ = position(builder, ["forest", "forest"], chosen="U")
        assert not pay_mana(game.state, 0, ManaCost.parse("{G}{G}{G}").with_x(0))

    def test_the_chip_label_promises_the_extra_only_on_the_chosen_color(self, builder):
        game, _ = position(builder, ["battlefield_forge"], chosen="R")
        forge = oids_of(game, "battlefield_forge", 0)[0]
        ability = game.state.card(forge).abilities[1]
        assert _mana_option_label(game.state, forge, ability, 0) == "{R}{R}"
        assert _mana_option_label(game.state, forge, ability, 1) == "{W}"


def slagheap(builder, source: str, chosen: str = "R"):
    """Molten Slagheap with two storage counters and two Swamps for its {1}."""
    game = (
        builder(players=2)
        .battlefield(0, ["swamp", "swamp", SLAGHEAP, source])
        .hand(0, ["swamp"])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    only = only_oid(game, source, 0)
    game.state.objects[only].chosen_color = chosen
    land = only_oid(game, SLAGHEAP, 0)
    game.state.objects[land].counters["storage"] = 2
    return game, land


def remove_two(game, land: int, colors: str) -> list[int]:
    game.apply(activations(game, land, 2)[0])
    assert game.pending().kind is DecisionKind.CHOOSE_X
    game.apply(find_action(game, ActionKind.CHOOSE, choice=2))
    for color in colors:
        assert game.pending().kind is DecisionKind.CHOOSE_MODE
        game.apply(find_action(game, ActionKind.CHOOSE, choice=["B", "R"].index(color)))
    return list(game.state.players[0].mana_pool.amounts)


class TestAManaAbilityThatDoesNotTap:
    def test_a_lands_ability_counts_without_tapping(self, builder):
        game, land = slagheap(builder, SUN)
        pool = remove_two(game, land, "BR")
        assert (pool[B], pool[R]) == (1, 2)
        assert not game.state.objects[land].tapped

    def test_once_however_much_of_the_color(self, builder):
        game, land = slagheap(builder, SUN)
        assert remove_two(game, land, "RR")[R] == 3

    def test_none_of_the_color_none_extra(self, builder):
        game, land = slagheap(builder, SUN)
        pool = remove_two(game, land, "BB")
        assert (pool[B], pool[R]) == (2, 0)

    def test_tapped_for_mana_alone_does_not_answer_it(self, builder):
        """Without ``any_mana_ability`` the static is "tapped for mana" (106.12)."""
        game, land = slagheap(builder, TAP_ONLY)
        pool = remove_two(game, land, "BR")
        assert (pool[B], pool[R]) == (1, 1)

    def test_but_it_answers_a_tap(self, builder):
        game, _ = position(builder, ["forest"], source=TAP_ONLY)
        assert tap(game, "forest")[G] == 2


def _probe(tapped: dict, add_mana=None) -> CardModel:
    return CardModel.model_validate(
        static_probe(
            {
                "effect": "add_mana_on_tap",
                "affects_player": "you",
                "tapped_permanent": tapped,
                "add_mana": add_mana or {"chosen_color_of": "self"},
            }
        )
    )


class TestTheLoader:
    @pytest.mark.parametrize(
        "produced", [{"chosen_color_of": "enchanted"}, {"chosen_color_of": "self", "x": 1}, {}]
    )
    def test_only_the_selfs_chosen_color(self, produced):
        with pytest.raises(DslError, match="produced"):
            compile_card(_probe({"types": ["Land"], "produced": produced}))

    @pytest.mark.parametrize("flag", [False, 1, "yes"])
    def test_any_mana_ability_is_true_or_absent(self, flag):
        with pytest.raises(DslError, match="any_mana_ability"):
            compile_card(_probe({"types": ["Land"], "any_mana_ability": flag}))

    def test_not_beside_one_mana_of_any_color(self):
        with pytest.raises(DslError, match="any_mana_ability"):
            compile_card(_probe({"types": ["Land"], "any_mana_ability": True}, {"any_color": 1}))

    def test_the_fixtures_load(self, registry):
        assert registry.get(SUN).abilities
        assert registry.get(TAP_ONLY).abilities
