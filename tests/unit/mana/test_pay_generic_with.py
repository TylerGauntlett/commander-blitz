"""Convoke and delve: paying generic mana with something that is not mana.

The census lists them apart — convoke as "a cost paid by tapping creatures",
delve as "a cost exiling from the graveyard to pay generic mana" — and they are
one capability. Both say the same thing: *each of these you spend pays for
{1}*. Only the currency differs.

**One cast line, and the pick is asked while paying.** Which creatures tap —
or which cards are exiled — is a `CHOOSE_OBJECTS` raised by the cast, the way
Captivating Vampire's five Vampires are, so the card is one row in the panel
whatever it could cost. The line carries the fewest the player must spend
(`pay_generic`): zero when the mana alone pays, which is the printed line, and
the floor the pick is asked at when it does not.

**It goes through the ordinary cost-reduction clamp.** The saving is netted
into the same `extra` the commander tax and emerge's sacrifice use, and `pay`
floors the generic part at zero — so no amount of convoking makes a spell free
of its coloured pips. That is convoke's documented simplification: "or one mana
of that creature's colour" is not modelled, which bites only on a spell whose
coloured pips a creature could have paid.

**The tap comes before the mana**, so the payment cannot tap a convoked
creature for mana as well: a creature taps once. A pick that convokes the very
creature the rest of the cost needed for mana is refused and asked again.

The ceiling is the spell's own generic cost. "Pays for {1}" and a spell with
three generic in it cannot absorb a fourth creature.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
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


def pick(game, purpose: str, oids) -> None:
    """Answer the convoke or delve pick with exactly these objects."""
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS, decision
    assert decision.context.get("purpose") == purpose, decision.context
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def oids_of(game, def_id: str, pid: int = 0) -> list[int]:
    return [o.oid for o in game.state.battlefield_objects(pid) if o.def_id == def_id]


class TestConvoke:
    def position(self, builder, *, lands=2, creatures=2, dorks=0):
        return (
            builder(players=2)
            .hand(0, [CONVOKER])
            .battlefield(0, ["mountain"] * lands)
            .battlefield(0, [BEAR] * creatures)
            .battlefield(0, ["t_dork"] * dorks)
            .build()
        )

    def test_one_line_per_target_however_many_could_convoke(self, builder):
        """The bug this shape fixes: one row per count, for every target."""
        game = self.position(builder, lands=4, creatures=2)
        lines = cast_lines(game)
        assert len(lines) == len({a.targets for a in lines})
        assert spends(game) == {0}, "the mana alone pays, so the printed line is the line"
        assert {a.base_label for a in lines} == {"Cast Test Convoker"}

    def test_the_cast_asks_which_creatures_tap(self, builder):
        game = self.position(builder, lands=4, creatures=2)
        game.apply(cast_lines(game)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "convoke"
        assert (decision.min_count, decision.max_count) == (0, 2)

    def test_the_picked_creatures_are_tapped(self, builder):
        game = self.position(builder, lands=3)
        assert spends(game) == {1}
        game.apply(cast_lines(game)[0])
        assert game.pending().min_count == 1
        pick(game, "convoke", oids_of(game, BEAR))
        settle(game)
        assert tapped_count(game, BEAR) == 2

    def test_convoking_saves_the_mana(self, builder):
        game = self.position(builder, lands=4, creatures=2)
        game.apply(cast_lines(game)[0])
        pick(game, "convoke", oids_of(game, BEAR)[:1])
        settle(game)
        assert tapped_count(game, BEAR) == 1
        assert tapped_count(game, "mountain") == 3

    def test_it_makes_an_unaffordable_spell_castable(self, builder):
        """The whole keyword: two lands cannot pay {3}{R} alone."""
        game = self.position(builder, lands=2, creatures=2)
        assert spends(game) == {2}, "the line's floor is the two creatures the mana is short"
        game.apply(cast_lines(game)[0])
        decision = game.pending()
        # Exactly two creatures to tap and two must be: nothing to ask.
        assert decision is None or decision.kind is not DecisionKind.CHOOSE_OBJECTS
        settle(game)
        assert tapped_count(game, BEAR) == 2

    def test_a_pick_that_strands_the_mana_is_asked_again(self, builder):
        """Convoking the dork the rest of the cost needed leaves {1}{R} to pay
        off one Mountain -- so the pick is refused rather than the cast failing."""
        game = self.position(builder, lands=1, creatures=2, dorks=1)
        assert spends(game) == {2}
        game.apply(cast_lines(game)[0])
        first = game.pending()
        pick(game, "convoke", [oids_of(game, "t_dork")[0], oids_of(game, BEAR)[0]])
        again = game.pending()
        assert again is not first and again.context["purpose"] == "convoke"
        assert "Not enough mana" in again.prompt
        assert tapped_count(game, BEAR) == 0 and tapped_count(game, "t_dork") == 0
        pick(game, "convoke", oids_of(game, BEAR))
        settle(game)
        assert tapped_count(game, BEAR) == 2
        assert tapped_count(game, "t_dork") == 1, "the dork tapped for mana instead"

    def test_with_no_creatures_only_the_printed_line_is_offered(self, builder):
        game = self.position(builder, lands=4, creatures=0)
        assert spends(game) == {0}

    def test_a_tapped_creature_cannot_convoke(self, builder):
        game = self.position(builder, lands=2, creatures=2)
        for obj in game.state.battlefield_objects(0):
            if obj.def_id == BEAR:
                obj.tapped = True
        assert cast_lines(game) == []

    def test_it_never_pays_the_coloured_pip(self, builder):
        """The documented simplification, stated as a boundary: convoking
        everything still leaves {R} to find."""
        game = self.position(builder, lands=0, creatures=4)
        assert cast_lines(game) == [], "no red source, so no line at any count"


class TestCleverConcealment:
    """The card the bug was reported on: "any number of target" permanents is
    declared mid-cast, so before this every count was its own row with nothing
    else to tell them apart."""

    def test_it_is_one_row(self, builder):
        game = (
            builder(players=2)
            .hand(0, ["clever_concealment"])
            .battlefield(0, ["plains"] * 4)
            .battlefield(0, [BEAR] * 2)
            .build()
        )
        assert len(cast_lines(game)) == 1


class TestDelve:
    def position(self, builder, *, lands=2, fodder=3):
        return (
            builder(players=2)
            .hand(0, [DELVER])
            .battlefield(0, ["island"] * lands)
            .graveyard(0, [BEAR] * fodder)
            .build()
        )

    def test_one_line_however_many_could_be_exiled(self, builder):
        game = self.position(builder, lands=4, fodder=2)
        assert len(cast_lines(game)) == 1
        assert spends(game) == {0}

    def test_the_picked_cards_are_exiled(self, builder):
        game = self.position(builder)
        graveyard = list(game.state.players[0].graveyard)
        game.apply(cast_lines(game)[0])
        pick(game, "delve", graveyard[:2])
        settle(game)
        assert set(game.state.players[0].exile) == set(graveyard[:2])

    def test_an_empty_graveyard_offers_only_the_printed_line(self, builder):
        game = self.position(builder, lands=4, fodder=0)
        assert spends(game) == {0}

    def test_the_spell_still_resolves(self, builder):
        game = self.position(builder, lands=2, fodder=3)
        before = len(game.state.players[0].hand)
        game.apply(cast_lines(game)[0])
        pick(game, "delve", list(game.state.players[0].graveyard)[:2])
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
        game.apply(cast_lines(game)[0])
        assert game.pending().max_count == 3

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
        spell = cast_lines(game)[0].source
        game.apply(cast_lines(game)[0])
        assert [o.ref.id for o in game.pending().options] != [spell]
        assert spell not in [o.ref.id for o in game.pending().options]


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
