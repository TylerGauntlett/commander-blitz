"""A token that enters with counters: `create_token`'s ``counters``.

Printlifter Ooze is the witness: "create a 0/0 green Ooze creature token with
trample. **The token enters with X +1/+1 counters on it**, where X is the number
of other creatures you control."

**The rules argument.** "Enters with" is a replacement on the token's own
arrival (614.1c), and the counters it places are part of that one event (122.6).
The token is never on the battlefield as a 0/0, so:

- 704.5f has nothing to bin -- a 0/0 given its counters *after* it arrives
  survives too, but only because SBAs wait for the effect to finish; the
  arrival itself would still have been a 0/0's;
- anything that looks at the token *as it enters* sees the counters. Elemental
  Bond ("Whenever a creature you control with power 3 or greater enters") draws
  for a 3-counter Ooze, and would not for `create_token` then `add_counters`;
- a counter replacement that applies to the arriving creature (Hardened Scales)
  modifies the one placement, once.

X is a value expression read once as the op runs, before any token exists, so
"other creatures you control" never counts the token itself. Below zero is
zero (107.1b), and zero leaves a 0/0 that dies.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import keywords, oids_of, plus_one_counters, pt, settle

OOZE = "ooze_0_0_g_trample"
BEAR = "t_bear"
BOND = "elemental_bond"
SCALES = "hardened_scales"
PRINTLIFTER = "printlifter_ooze"
CREATURES_YOU_CONTROL = {
    "count": {"zone": "battlefield", "controller": "you", "types": ["Creature"]}
}


def board(builder, *, mine=()):
    """Player 0 in their precombat main; the card in hand keeps the builder's
    auto-pass from handing an empty board's turn to player 1."""
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 2 + list(mine))
        .hand(0, ["forest"])
        .library(0, ["island"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def make_ooze(game, counters, **extra) -> dict:
    """Run ``create_token`` directly for player 0. Returns the bindings."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    spec = {"op": "create_token", "token": OOZE, "counters": counters, **extra}
    for _ in execute(ctx, [spec]):
        raise AssertionError("create_token asks nothing here")
    return ctx.bindings


def oozes(game) -> list[int]:
    return oids_of(game, OOZE, 0)


class TestTheCountersArriveWithIt:
    def test_x_counts_the_other_creatures(self, builder):
        game = board(builder, mine=[BEAR, BEAR, BEAR])
        make_ooze(game, {"+1/+1": CREATURES_YOU_CONTROL})
        settle(game)
        [ooze] = oozes(game)
        assert plus_one_counters(game, ooze) == 3
        assert pt(game, ooze) == (3, 3)

    def test_the_token_is_not_one_of_the_creatures_it_counts(self, builder):
        """Read before the token exists: one Bear makes a 1/1, not a 2/2."""
        game = board(builder, mine=[BEAR])
        make_ooze(game, {"+1/+1": CREATURES_YOU_CONTROL})
        [ooze] = oozes(game)
        assert pt(game, ooze) == (1, 1)

    def test_the_arrival_already_carries_them(self, builder):
        """Elemental Bond reads the entering creature's power: a 3-counter Ooze
        is a 3/3 as it enters, so the Bond draws."""
        game = board(builder, mine=[BOND, BEAR, BEAR, BEAR])
        hand = len(game.state.players[0].hand)
        make_ooze(game, {"+1/+1": CREATURES_YOU_CONTROL})
        settle(game)
        assert len(game.state.players[0].hand) == hand + 1

    def test_a_counter_replacement_modifies_the_one_placement(self, builder):
        """Hardened Scales applies once to the arrival's counters (2 + 1)."""
        game = board(builder, mine=[SCALES, BEAR, BEAR])
        make_ooze(game, {"+1/+1": CREATURES_YOU_CONTROL})
        [ooze] = oozes(game)
        assert plus_one_counters(game, ooze) == 3

    def test_the_binding_records_the_counted_token(self, builder):
        game = board(builder, mine=[BEAR])
        bindings = make_ooze(game, {"+1/+1": {"const": 2}}, **{"as": "made"})
        assert bindings["made"] == oozes(game)
        assert plus_one_counters(game, bindings["made"][0]) == 2


class TestTheBoundary:
    def test_zero_counters_leave_a_zero_zero_that_dies(self, builder):
        game = board(builder)
        make_ooze(game, {"+1/+1": CREATURES_YOU_CONTROL})
        assert pt(game, oozes(game)[0]) == (0, 0)
        sba.run(game.state)
        assert oozes(game) == []

    def test_a_negative_amount_is_zero(self, builder):
        """107.1b."""
        game = board(builder, mine=[BEAR])
        make_ooze(game, {"+1/+1": {"const": -3}})
        [ooze] = oozes(game)
        assert plus_one_counters(game, ooze) == 0
        sba.run(game.state)
        assert oozes(game) == []

    def test_every_token_made_gets_them(self, builder):
        game = board(builder, mine=[BEAR])
        make_ooze(game, {"+1/+1": {"const": 2}}, amount={"const": 2})
        assert [plus_one_counters(game, o) for o in oozes(game)] == [2, 2]


class TestTheLoaderRefuses:
    @staticmethod
    def probe(effect):
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Create a 0/0 Ooze with two +1/+1 counters on it.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_the_counters_load(self):
        compile_card(self.probe({"op": "create_token", "token": OOZE, "counters": {"+1/+1": 2}}))

    @pytest.mark.parametrize("counters", [{}, [], 2])
    def test_an_empty_or_malformed_map(self, counters):
        with pytest.raises(DslError, match="create_token's 'counters'"):
            compile_card(self.probe({"op": "create_token", "token": OOZE, "counters": counters}))

    def test_an_amount_that_is_not_a_value(self):
        with pytest.raises(DslError, match=r"counters\.\+1/\+1"):
            compile_card(
                self.probe(
                    {"op": "create_token", "token": OOZE, "counters": {"+1/+1": {"nonsense": 1}}}
                )
            )

    def test_a_near_miss_counter_kind(self):
        """`Vigilance` would be a tally nobody consults (122.1c)."""
        with pytest.raises(DslError):
            compile_card(
                self.probe({"op": "create_token", "token": OOZE, "counters": {"Vigilance": 2}})
            )


class TestPrintlifterOoze:
    """The witness, cast face down and turned up for its disguise cost."""

    def test_turning_it_up_makes_an_ooze_sized_by_the_others(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 7 + [BEAR, BEAR])
            .hand(0, [PRINTLIFTER])
            .library(0, ["forest"] * 20)
            .library(1, ["mountain"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        oid = game.state.players[0].hand[0]
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and a.source == oid and a.face_down
            )
        )
        settle(game)
        assert oozes(game) == []
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == oid
            )
        )
        settle(game)
        assert not game.state.objects[oid].face_down
        [ooze] = oozes(game)
        # The Printlifter and two Bears: the token is not one of the others.
        assert plus_one_counters(game, ooze) == 3
        assert pt(game, ooze) == (3, 3)
        assert "trample" in keywords(game, ooze)
