"""Convoke and delve: paying generic mana with something that is not mana.

The census lists them apart — convoke as "a cost paid by tapping creatures",
delve as "a cost exiling from the graveyard to pay generic mana" — and they are
one capability. Both say the same thing: *each of these you spend pays for
{1}*. Only the currency differs.

**One cast line per number spent.** The count changes the price and is the
player's to choose, so it is part of the action's identity the way emerge's
victim is — convoking two and convoking three are two different things to do
with the same card. Zero is the printed line, already offered.

**It goes through the ordinary cost-reduction clamp.** The saving is netted
into the same `extra` the commander tax and emerge's sacrifice use, and `pay`
floors the generic part at zero — so no amount of convoking makes a spell free
of its coloured pips. That is convoke's documented simplification: "or one mana
of that creature's colour" is not modelled, which bites only on a spell whose
coloured pips a creature could have paid.

**The tap is charged after the mana**, rule 601.2g and the same order emerge's
sacrifice uses. It matters here in a way it does not there: a creature that
taps for mana must not then be convoked as well, and charging afterwards
against untapped creatures is what stops it.

The ceiling is the spell's own generic cost. "Pays for {1}" and a spell with
three generic in it cannot absorb a fourth creature.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

CONVOKER = "t_convoker"  # {3}{R} sorcery, convoke, 2 damage
DELVER = "t_delver"  # {3}{U} sorcery, delve, draw two
BEAR = "t_bear"


def cast_lines(game) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST]


def spends(game) -> set[int]:
    return {a.pay_generic for a in cast_lines(game)}


def settle(game, limit: int = 40) -> None:
    """Finish the cast, including the decisions its *cost* raises.

    Delve asks which cards to exile and convoke which creatures to tap, and
    both are asked **before** the spell reaches the stack. A loop that waits on
    an empty stack therefore returns immediately, leaving the cast suspended
    mid-payment with nothing having happened.
    """
    from commanderblitz.engine.enums import DecisionKind

    for _ in range(limit):
        decision = game.pending()
        if decision is not None and decision.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, decision))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return
        if decision is None:
            game._advance()
        else:
            game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def tapped_count(game, def_id: str, pid: int = 0) -> int:
    return sum(
        1 for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.tapped
    )


class TestConvoke:
    def position(self, builder, *, lands=2, creatures=2):
        return (
            builder(players=2)
            .hand(0, [CONVOKER])
            .battlefield(0, ["mountain"] * lands)
            .battlefield(0, [BEAR] * creatures)
            .build()
        )

    def test_a_line_is_offered_per_number_convoked(self, builder):
        game = self.position(builder, lands=4, creatures=2)
        assert spends(game) == {0, 1, 2}

    def test_the_creatures_are_tapped(self, builder):
        game = self.position(builder)
        line = next(a for a in cast_lines(game) if a.pay_generic == 2)
        game.apply(line)
        settle(game)
        assert tapped_count(game, BEAR) == 2

    def test_it_makes_an_unaffordable_spell_castable(self, builder):
        """The whole keyword: two lands cannot pay {3}{R} alone."""
        game = self.position(builder, lands=2, creatures=2)
        assert spends(game) == {2}, "only the fully-convoked line is affordable"

    def test_with_no_creatures_only_the_printed_line_is_offered(self, builder):
        game = self.position(builder, lands=4, creatures=0)
        assert spends(game) == {0}

    def test_a_tapped_creature_cannot_convoke(self, builder):
        game = self.position(builder, lands=4, creatures=2)
        for obj in game.state.battlefield_objects(0):
            if obj.def_id == BEAR:
                obj.tapped = True
        assert spends(game) == {0}

    def test_it_never_pays_the_coloured_pip(self, builder):
        """The documented simplification, stated as a boundary: convoking
        everything still leaves {R} to find."""
        game = self.position(builder, lands=0, creatures=4)
        assert cast_lines(game) == [], "no red source, so no line at any count"


class TestDelve:
    def position(self, builder, *, lands=2, fodder=3):
        return (
            builder(players=2)
            .hand(0, [DELVER])
            .battlefield(0, ["island"] * lands)
            .graveyard(0, [BEAR] * fodder)
            .build()
        )

    def test_a_line_is_offered_per_number_exiled(self, builder):
        game = self.position(builder, lands=4, fodder=2)
        assert spends(game) == {0, 1, 2}

    def test_the_cards_are_exiled(self, builder):
        game = self.position(builder)
        before = len(game.state.players[0].graveyard)
        line = next(a for a in cast_lines(game) if a.pay_generic == 2)
        game.apply(line)
        settle(game)
        assert len(game.state.players[0].exile) == 2
        assert len(game.state.players[0].graveyard) < before

    def test_an_empty_graveyard_offers_only_the_printed_line(self, builder):
        game = self.position(builder, lands=4, fodder=0)
        assert spends(game) == {0}

    def test_the_spell_still_resolves(self, builder):
        game = self.position(builder, lands=2, fodder=3)
        before = len(game.state.players[0].hand)
        line = next(a for a in cast_lines(game) if a.pay_generic == 2)
        game.apply(line)
        settle(game)
        assert len(game.state.players[0].hand) == before - 1 + 2, "cast one, drew two"


class TestTheCeiling:
    def test_it_never_exceeds_the_generic_cost(self, builder):
        """"Pays for {1}", and {3}{U} has only three generic in it."""
        game = (
            builder(players=2)
            .hand(0, [DELVER])
            .battlefield(0, ["island"] * 4)
            .graveyard(0, [BEAR] * 8)
            .build()
        )
        assert max(spends(game)) == 3

    def test_the_spell_itself_is_not_delve_fodder(self, builder):
        """It is on the stack by the time the cost is paid, not in the
        graveyard — and a spell that ate itself would be a different card."""
        game = (
            builder(players=2)
            .hand(0, [DELVER])
            .battlefield(0, ["island"] * 4)
            .graveyard(0, [BEAR])
            .build()
        )
        assert max(spends(game)) == 1


class TestTheLoaderKnowsIt:
    def test_the_cards_compile(self, registry):
        assert registry.get(CONVOKER).pay_generic_with == "tap_creatures"
        assert registry.get(DELVER).pay_generic_with == "exile_from_graveyard"

    def test_an_unknown_currency_is_refused(self):
        with pytest.raises((DslError, ValueError)):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{3}{U}",
                        "types": ["Sorcery"],
                        "pay_generic_with": "sacrifice_lands",
                        "spell_effects": [{"op": "noop"}],
                    }
                )
            )

    def test_a_card_without_it_is_unaffected(self, registry):
        assert registry.get("t_draw_spell").pay_generic_with is None
