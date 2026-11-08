"""Vanishing: a permanent that enters with a clock and counts itself out.

    Vanishing 2 (This creature enters with two time counters on it. At the
    beginning of your upkeep, remove a time counter from it. When the last is
    removed, sacrifice it.)

702.63a makes the keyword three abilities, and the card writes none of them:
the card-level `vanishing` field is N, and the loader lowers it.

**The counters are a replacement**, not an enters trigger: the permanent is
never on the battlefield without them, so nothing can see it at zero and the
sacrifice cannot be dodged by answering a trigger.

**The tick is your upkeep's only**, and it has an intervening-if: a permanent
with no time counter left has nothing to remove.

**The sacrifice is a trigger of its own**, on the last time counter coming off
(`last_counter_removed`), not an `if` inside the tick. Without that, the last
counter removed by anything other than the tick -- a cost, another card's
effect -- would leave a permanent with no counters that is never sacrificed.
And it waits for the *last*: a removal that leaves one behind sacrifices
nothing.

Witness: Deep Forest Hermit (`deep_forest_hermit` in `data/cards/auto/`),
whose test twin without the Squirrels is `t_vanishing_sprite`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import TIME_COUNTER
from commanderblitz.engine.primitives import remove_counters
from tests.conftest import pass_until, settle

SPRITE = "t_vanishing_sprite"  # {1}{G} 2/2, Vanishing 2


def board(builder):
    """Player 0 on Forests with the Sprite in hand; a Forest keeps a play there.

    A position whose active player has nothing to do runs on by itself, so the
    Forests stay in hand to keep each test standing where it was put.
    """
    return (
        builder(players=2)
        .hand(0, [SPRITE, "forest", "forest", "forest"])
        .battlefield(0, ["forest"] * 2)
        .hand(1, ["forest"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )


def cast(builder):
    """Cast the Sprite on turn 1 and resolve it; return ``(game, oid)``."""
    game = board(builder)
    oid = next(
        o for o in game.state.players[0].hand if game.state.objects[o].def_id == SPRITE
    )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid)
    )
    pass_until(game, lambda g: not g.state.stack)
    assert game.state.objects[oid].zone is Zone.BATTLEFIELD
    return game, oid


def time_counters(game, oid):
    return game.state.objects[oid].counter(TIME_COUNTER)


def zone(game, oid):
    return game.state.objects[oid].zone


def to_main_of_turn(game, turn):
    """The first main phase of ``turn``: its upkeep, and the stack, behind it.

    Player 0 takes the odd turns.
    """
    pass_until(
        game,
        lambda g: g.state.turn == turn
        and g.state.step is Step.PRECOMBAT_MAIN
        and not g.state.stack,
    )


class TestItEntersWithTheCounters:
    """"This creature enters with N time counters on it.\""""

    def test_it_enters_with_two_time_counters(self, builder):
        game, oid = cast(builder)
        assert time_counters(game, oid) == 2

    def test_the_card_records_n(self):
        assert compile_card(_model()).vanishing == 2


class TestTheUpkeepTick:
    """"At the beginning of your upkeep, remove a time counter from it.\""""

    def test_your_upkeep_removes_one(self, builder):
        game, oid = cast(builder)
        to_main_of_turn(game, 3)
        assert time_counters(game, oid) == 1
        assert zone(game, oid) is Zone.BATTLEFIELD

    def test_an_opponents_upkeep_removes_none(self, builder):
        game, oid = cast(builder)
        to_main_of_turn(game, 2)
        assert time_counters(game, oid) == 2

    def test_it_is_an_ability_the_permanent_can_lose(self, builder):
        # 702.63a makes the tick one of the permanent's abilities.
        game, oid = cast(builder)
        game.state.objects[oid].lost_all_abilities = True
        game.state.bump_chars()
        to_main_of_turn(game, 3)
        assert time_counters(game, oid) == 2


class TestTheLastCounterSacrificesIt:
    """"When the last is removed, sacrifice it.\""""

    def test_the_upkeep_that_takes_the_last_counter_sacrifices_it(self, builder):
        game, oid = cast(builder)
        to_main_of_turn(game, 3)
        assert zone(game, oid) is Zone.BATTLEFIELD
        to_main_of_turn(game, 5)
        assert zone(game, oid) is Zone.GRAVEYARD

    def test_a_removal_that_leaves_one_sacrifices_nothing(self, builder):
        game, oid = cast(builder)
        remove_counters(game.state, oid, TIME_COUNTER, 1)
        settle(game)
        assert time_counters(game, oid) == 1
        assert zone(game, oid) is Zone.BATTLEFIELD

    def test_the_last_counter_removed_by_anything_sacrifices_it(self, builder):
        # The trigger is its own ability, so the tick is not the only road to
        # zero: an effect taking both counters at once sacrifices it too.
        game, oid = cast(builder)
        remove_counters(game.state, oid, TIME_COUNTER, 2)
        assert zone(game, oid) is Zone.BATTLEFIELD  # a trigger, not yet resolved
        settle(game)
        assert zone(game, oid) is Zone.GRAVEYARD

    def test_another_kinds_last_counter_is_not_it(self, builder):
        game, oid = cast(builder)
        game.state.objects[oid].add_counter("+1/+1", 1)
        remove_counters(game.state, oid, "+1/+1", 1)
        settle(game)
        assert zone(game, oid) is Zone.BATTLEFIELD


def _model(**overrides):
    base = dict(
        id="t_bad",
        name="Bad",
        mana_cost="{1}{G}",
        types=["Creature"],
        power=2,
        toughness=2,
        vanishing=2,
    )
    base.update(overrides)
    return CardModel(**base)


class TestTheLoaderRefusesTheSilentFailures:
    """Each would load clean and print a line the card does not perform."""

    @pytest.mark.parametrize("bad", [0, -1, "three", True, 2.5])
    def test_a_malformed_n_is_refused(self, bad):
        with pytest.raises(DslError, match="'vanishing' is N"):
            compile_card(_model(vanishing=bad))

    def test_vanishing_on_a_sorcery_is_refused(self):
        model = _model(types=["Sorcery"], power=None, toughness=None)
        with pytest.raises(DslError, match="only on permanent cards"):
            compile_card(model)

    def test_a_last_counter_removed_trigger_needs_its_kind(self):
        model = _model(
            vanishing=None,
            abilities=[
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": {"event": "last_counter_removed", "source": "self"},
                    "effects": [{"op": "draw", "amount": {"const": 1}}],
                }
            ],
        )
        with pytest.raises(DslError, match="needs 'counter'"):
            compile_card(model)


class TestThePrintedLineIsClaimed:
    """Gate 3: the field claims the line, and only with the printed number."""

    LINE = (
        "Vanishing 3 (This creature enters with three time counters on it. At the "
        "beginning of your upkeep, remove a time counter from it. When the last is "
        "removed, sacrifice it.)"
    )

    def residual(self, vanishing):
        from commanderblitz.cards.authoring.verify import residual_text

        card = compile_card(_model(oracle_text=self.LINE, vanishing=vanishing))
        return residual_text(card, card.oracle_text)

    def test_the_printed_line_is_claimed(self):
        assert self.residual(3) == ""

    def test_a_card_without_the_field_leaves_it_residual(self):
        assert "Vanishing 3" in self.residual(None)

    def test_a_different_n_cannot_claim_the_printed_one(self):
        assert "Vanishing 3" in self.residual(2)
