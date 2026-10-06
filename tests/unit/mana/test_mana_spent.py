""""…if **at least four mana was spent** to cast it."

The Emperor of Palamecia. The card asks about the *payment*, and the engine
could only answer about the printed cost — which is a different number whenever
anything interesting has happened:

- `mana_value_of` is what the card says it costs. A cost reduction, an
  alternative cost, a free cast and an additional cost each move what was paid
  without moving it.
- `additional_paid` is only the overpayment *above* the mana cost, so a plainly
  qualifying {3}{R} reports 0.
- `colors_of_mana_spent` and `mana_symbols` are about colour and about printed
  symbols, not about an amount.

So `pay_mana` records the total on the spell, beside `colors_spent` and
`mana_sources_spent` and for the same reason those two live there: it is
knowable exactly once, while the payment is happening. It **accumulates**,
because a cast with an additional cost pays in more than one call and "how much
mana was spent to cast it" is all of them.

`TestACostReductionChangesTheAnswer` is the test that matters: it is the case
where the printed value and the payment disagree, and the only one that can
tell the new leaf apart from `mana_value_of`.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import only_oid, pass_until

WATCHER = "t_emperor"  # +1/+1 when you cast a noncreature spell paid with 4+
CHEAP = "t_cheap_instant"  # {R} -- one mana
PRICEY = "t_pricey_instant"  # {3}{R} -- four mana
REDUCER = "t_runes"  # instant and sorcery spells you cast cost {1} less


def position(builder, spell: str, *, board=()):
    game = (
        builder(players=2)
        .battlefield(0, [WATCHER, *board, "mountain", "mountain", "mountain", "mountain"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .hand(0, [spell])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast_and_read_counters(game, spell: str) -> int:
    watcher = only_oid(game, WATCHER)
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == spell
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return game.state.objects[watcher].counters.get("+1/+1", 0)


class TestTheThresholdHolds:
    def test_a_four_mana_spell_trips_it(self, builder):
        game = position(builder, PRICEY)
        assert cast_and_read_counters(game, PRICEY) == 1

    def test_a_one_mana_spell_does_not(self, builder):
        game = position(builder, CHEAP)
        assert cast_and_read_counters(game, CHEAP) == 0


class TestACostReductionChangesTheAnswer:
    def test_a_four_cost_spell_paid_for_three_does_not_trip_it(self, builder):
        """The case `mana_value_of` gets wrong.

        {3}{R} is mana value 4 all day, but with a reducer out only three mana
        is spent -- and the card asks what was *spent*. A version built on the
        printed cost would put a counter on here.
        """
        game = position(builder, PRICEY, board=[REDUCER])
        assert cast_and_read_counters(game, PRICEY) == 0


class TestItReadsTheTriggeringSpell:
    def test_two_casts_are_judged_separately(self, builder):
        """The cheap one must not inherit the pricey one's payment."""
        game = (
            builder(players=2)
            .battlefield(0, [WATCHER] + ["mountain"] * 6)
            .battlefield(1, ["plains"])
            .library(0, ["forest"] * 20)
            .hand(0, [PRICEY, CHEAP])
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()

        assert cast_and_read_counters(game, PRICEY) == 1
        assert cast_and_read_counters(game, CHEAP) == 1, "still one -- the cheap one adds none"
