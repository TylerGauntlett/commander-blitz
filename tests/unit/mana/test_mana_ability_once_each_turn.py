""""Activate only once each turn" on a mana ability was never spent.

Vivi Ornitier: "{0}: Add X mana in any combination of {U} and/or {R}, where X is
Vivi Ornitier's power. Activate only during your turn and **only once each
turn**."

`legality._ability_aims` checks `once_each_turn` against
`turn_ledger.activations` for every activated ability alike, and `game._activate`
writes that ledger with a comment explaining exactly why it counts *before* the
cost is paid. But a mana ability activated by hand does not go through
`_activate` -- it goes through `_activate_mana`, deliberately, because a mana
ability uses no stack -- and that path never wrote the ledger at all.

So the printed limit was inert, and only a mana ability could notice: every other
activated ability spends its allowance on the way through `_activate`. Vivi taps
for his own power, which made the card an arbitrary amount of mana per turn
rather than one activation's worth.

The card cleared all six authoring gates with this bug in it, which is the point
of the per-card behavioural pass: gate 5 never activates an ability, so nothing
in the pipeline could have seen it.

`TestWithoutTheLimit` is the control that keeps this honest -- without it, "the
second activation is not offered" is equally consistent with an ability that
simply cannot be activated twice for some unrelated reason.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import pass_until

LIMITED = "t_once_font"  # "Activate only once each turn."
UNLIMITED = "t_unlimited_font"  # the same ability, no limit


def position(builder, font: str):
    """The font, and a reason for seat 0 to keep priority.

    The anchor in hand is load bearing rather than scenery: with nothing to do,
    seat 0 auto-passes and `legal_actions()` returns the *opponent's* list --
    where the font's ability is legitimately absent, and every assertion below
    would pass for the wrong reason.
    """
    game = (
        builder(players=2)
        .battlefield(0, [font, "island", "plains"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 10)
        .hand(0, ["t_plain_instant"])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    pending = game.pending()
    assert pending is not None and pending.player == 0, "seat 0 holds priority"
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == font)
    return game, oid


def offers(game, oid) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid]


def activate(game, oid) -> None:
    game.apply(offers(game, oid)[0])
    pass_until(game, lambda g: g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)


class TestTheLimitIsSpent:
    def test_the_first_activation_is_offered(self, builder):
        game, oid = position(builder, LIMITED)
        assert offers(game, oid)

    def test_the_second_is_not(self, builder):
        game, oid = position(builder, LIMITED)
        activate(game, oid)

        assert not offers(game, oid)

    def test_and_only_one_mana_was_made(self, builder):
        """The half a legality check alone would not prove."""
        game, oid = position(builder, LIMITED)
        activate(game, oid)

        assert game.state.players[0].mana_pool.total() == 1


class TestWithoutTheLimit:
    def test_it_can_be_activated_twice(self, builder):
        """The control. Without it the tests above prove nothing about the limit."""
        game, oid = position(builder, UNLIMITED)
        activate(game, oid)
        assert offers(game, oid), "no printed limit, so no limit"
        activate(game, oid)

        assert game.state.players[0].mana_pool.total() == 2


class TestItResetsWithTheTurn:
    def test_next_turn_it_is_offered_again(self, builder):
        """"once each **turn**", not once per game."""
        game, oid = position(builder, LIMITED)
        activate(game, oid)
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn
            and g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN,
        )

        assert offers(game, oid)
