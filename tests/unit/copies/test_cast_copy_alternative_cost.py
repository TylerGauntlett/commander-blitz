"""Casting a copy of an exiled card for a printed price instead of its mana cost.

Blue Mage's Cane grants: "Whenever this creature attacks, exile up to one
target instant or sorcery card from defending player's graveyard. If you do,
copy it. You may cast the copy by paying {3} rather than paying its mana cost."

`cast_copy` only ever cast its copy free (Mizzix's Mastery, cipher). Wrapping
it in `may` + `pay {3}` would charge the {3} as a payment of its own, beside
the cast rather than as the spell's cost -- so a discount on instants and
sorceries would not reach it, a tax on the caster's spells would not either,
and an X in the copied card would be whatever the free cast left it. The
price is an **alternative cost** (118.9): it replaces the mana cost, the
cast's increases and reductions still apply on top (601.2f), an X the price
does not contain is 0 (107.3), and paying it is a choice -- declinable, and
never offered when it cannot be paid (118.4). `cast_copy`'s ``cost`` says so.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import find_action, oids_of, pass_until, settle_to_priority

LESSON = "t_cane_copy"  # exile a card from an opponent's graveyard, copy, cast for {3}
DIVINATION = "t_draw_spell"  # {2}{U} sorcery: draw two
INSIGHT = "t_cane_draw_x"  # {X}{U} instant: draw X
BOLT = "t_bolt"  # {R} instant: 3 damage to target creature


def position(builder, *, card=DIVINATION, islands=4, mine=(), theirs=()):
    """Player 0 with the Lesson in hand and ``islands`` Islands (one pays for
    the Lesson itself); ``card`` in player 1's graveyard. Returns the game."""
    return (
        builder(players=2)
        .battlefield(0, ["island"] * islands + list(mine))
        .battlefield(1, ["plains", *theirs])
        .graveyard(1, [card])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [LESSON])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_lesson(game) -> None:
    """Cast the Lesson and pass until its resolution asks something (or ends)."""
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == LESSON
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not any(i.def_id == LESSON for i in g.state.stack)
        or ((d := g.pending()) is not None and d.kind is not DecisionKind.PRIORITY),
    )


def offered(game) -> bool:
    decision = game.pending()
    return decision is not None and decision.kind is DecisionKind.MAY


def untapped_islands(game) -> int:
    return sum(not game.state.objects[o].tapped for o in oids_of(game, "island", 0))


def library(game, pid: int = 0) -> int:
    return len(game.state.players[pid].library)


def exiled_original(game, card_id: str):
    return next(
        o for o in game.state.objects.values() if o.def_id == card_id and not o.is_token
    )


class TestThePriceIsPaid:
    def test_yes_pays_three_and_the_copy_resolves(self, builder):
        game = position(builder)
        before = library(game)
        cast_lesson(game)
        assert offered(game)
        assert "{3}" in game.pending().prompt

        game.apply(find_action(game, ActionKind.YES))
        settle_to_priority(game)

        assert library(game) == before - 2, "the copied Divination drew two"
        assert untapped_islands(game) == 0, "{U} for the Lesson, {3} for the copy"

    def test_not_the_printed_mana_cost(self, builder):
        """Divination costs {2}{U}; the price is {3} generic, so three Islands
        pay it either way -- but a Mountain pays {3} and not {2}{U}."""
        game = position(builder, islands=1, mine=["mountain"] * 3)
        before = library(game)
        cast_lesson(game)
        assert offered(game)

        game.apply(find_action(game, ActionKind.YES))
        settle_to_priority(game)

        assert library(game) == before - 2

    def test_the_original_stays_in_exile(self, builder):
        game = position(builder)
        cast_lesson(game)
        game.apply(find_action(game, ActionKind.YES))
        settle_to_priority(game)

        assert exiled_original(game, DIVINATION).zone is Zone.EXILE
        assert not game.state.players[1].graveyard


class TestTheCasterMayDecline:
    def test_no_casts_nothing_and_pays_nothing(self, builder):
        game = position(builder)
        before = library(game)
        cast_lesson(game)

        game.apply(find_action(game, ActionKind.NO))
        settle_to_priority(game)

        assert library(game) == before
        assert untapped_islands(game) == 3
        assert exiled_original(game, DIVINATION).zone is Zone.EXILE

    def test_unaffordable_is_not_offered(self, builder):
        """Two Islands left after the Lesson: {3} cannot be paid, so no
        question whose yes would do nothing (118.4)."""
        game = position(builder, islands=3)
        before = library(game)
        cast_lesson(game)

        assert not offered(game)
        settle_to_priority(game)
        assert library(game) == before
        assert untapped_islands(game) == 2


class TestCostAdjustmentsApplyOnTop:
    def test_a_reduction_reaches_the_price(self, builder):
        """Archmage of Runes: instants and sorceries cost {1} less. The
        Lesson costs {U} still ({U} has no generic to reduce), and the copy
        {2} -- so three Islands are enough for both."""
        game = position(builder, islands=3, mine=["t_runes"])
        before = library(game)
        cast_lesson(game)
        assert offered(game)

        game.apply(find_action(game, ActionKind.YES))
        settle_to_priority(game)

        assert library(game) == before - 2
        assert untapped_islands(game) == 0

    def test_a_tax_reaches_the_price(self, builder):
        """An opponent's "spells your opponents cast cost {1} more" makes the
        Lesson {1}{U} and the copy {4}: five Islands are not enough for both."""
        game = position(builder, islands=5, theirs=["t_mana_toll_all"])
        before = library(game)
        cast_lesson(game)

        assert not offered(game)
        settle_to_priority(game)
        assert library(game) == before

    def test_a_tax_is_paid_when_it_can_be(self, builder):
        game = position(builder, islands=6, theirs=["t_mana_toll_all"])
        before = library(game)
        cast_lesson(game)
        assert offered(game)

        game.apply(find_action(game, ActionKind.YES))
        settle_to_priority(game)

        assert library(game) == before - 2
        assert untapped_islands(game) == 0


class TestXIsZero:
    def test_an_x_the_price_lacks_is_zero(self, builder):
        """107.3: the {3} has no X in it, so "draw X" draws nothing -- and the
        cast is still made and paid for."""
        game = position(builder, card=INSIGHT)
        before = library(game)
        cast_lesson(game)
        assert offered(game)

        game.apply(find_action(game, ActionKind.YES))
        settle_to_priority(game)

        assert library(game) == before
        assert untapped_islands(game) == 0


class TestTheCopyChoosesItsTargets:
    def choose(self, game, label: str) -> None:
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context.get("purpose") == "target", decision.context
        game.apply(next(a for a in game.legal_actions() if str(a) == f"Action({label})"))

    def test_the_caster_picks_the_target(self, builder):
        """601.2c: the copy is cast, so its controller declares its target --
        asked, among the bear and both players."""
        game = position(builder, card=BOLT, theirs=["t_bear"])
        bear = oids_of(game, "t_bear", 1)[0]
        cast_lesson(game)
        game.apply(find_action(game, ActionKind.YES))

        self.choose(game, "Test Bear")
        settle_to_priority(game)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_another_pick_hits_another_target(self, builder):
        game = position(builder, card=BOLT, theirs=["t_bear"])
        bear = oids_of(game, "t_bear", 1)[0]
        life = game.state.players[1].life
        cast_lesson(game)
        game.apply(find_action(game, ActionKind.YES))

        self.choose(game, "P1")
        settle_to_priority(game)

        assert game.state.players[1].life == life - 3
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_nothing_to_target_is_not_offered(self, builder):
        """No creature: the copy has no legal target, so it cannot be cast."""
        game = position(builder, card="t_cane_murder")
        cast_lesson(game)

        assert not offered(game)


class TestTheLoaderGuards:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_ccac_probe",
                "name": "Test Cast Copy Cost Probe",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "oracle_text": "Probe.",
                "spell_effects": [effect],
            }
        )

    def test_the_printed_form_loads(self):
        compile_card(self._card({"op": "cast_copy", "objects": {"binding": "x"}, "cost": "{3}"}))

    @pytest.mark.parametrize("cost", ["", 3, "three", "{X}", "{X}{U}"])
    def test_a_malformed_price_is_refused(self, cost):
        with pytest.raises(DslError):
            compile_card(
                self._card({"op": "cast_copy", "objects": {"binding": "x"}, "cost": cost})
            )
