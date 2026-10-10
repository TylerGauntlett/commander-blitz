""""…exile up to two target artifacts and/or enchantments." -- a trigger with
more than one target asks for them one at a time.

    Angel of the Ruins, Terastodon.

The subset enumeration offered every pair as one button: "Ghostly Prison, Map",
"Ghostly Prison, Bident of Thassa", ... in no order, mixing both sides of the
table, with no art -- and past the option cap the pair the player wanted was
not offered at all. A trigger whose one spec takes several targets now asks
through `ask_targets`, the shape "any number of" and proliferate already use:
every legal single target is an option carrying its ref, and the size is the
decision's min/max.
"""

from __future__ import annotations

from commanderblitz.engine.enums import DecisionKind, Step, Zone
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

ANGEL = "angel_of_the_ruins"
RELICS = ["sol_ring", "arcane_signet"]


def angel_enters(builder):
    game = (
        builder(players=2)
        .battlefield(0, ["plains", *RELICS])
        .battlefield(1, ["ghostly_prison", "sol_ring"])
        .hand(0, [ANGEL])
        .library(0, ["plains"] * 10)
        .library(1, ["plains"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    move_object(game.state, game.state.players[0].hand[0], Zone.BATTLEFIELD)
    # The board was built waiting on a priority decision; drop it so the
    # advance loop puts the enters trigger on the stack.
    game.state.pending_decision = None
    game._advance()
    return game


def relics(game) -> set[int]:
    return {
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id in ("sol_ring", "arcane_signet", "ghostly_prison", ANGEL)
    }


class TestItAsksForEachTarget:
    def test_every_option_is_one_permanent(self, builder):
        game = angel_enters(builder)
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        refs = [o.ref for o in decision.options]
        assert all(ref is not None and ref.kind == "object" for ref in refs)
        assert {ref.id for ref in refs} == relics(game)

    def test_up_to_two_is_zero_to_two(self, builder):
        decision = angel_enters(builder).pending()
        assert (decision.min_count, decision.max_count) == (0, 2)


class TestTheChoiceIsWhatResolves:
    def test_the_two_picked_are_exiled_and_nothing_else(self, builder):
        game = angel_enters(builder)
        decision = game.pending()
        prison = only_oid(game, "ghostly_prison", 1)
        mine = only_oid(game, "arcane_signet", 0)
        for oid in (prison, mine):
            index = next(o.value for o in decision.options if o.ref.id == oid)
            game.apply(next(a for a in game.legal_actions() if a.choice == index))
        for _ in range(20):
            if game.state.objects[prison].zone is Zone.EXILE:
                break
            game.apply(game.legal_actions()[0])
        assert game.state.objects[prison].zone is Zone.EXILE
        assert game.state.objects[mine].zone is Zone.EXILE
        others = relics(game) - {prison, mine}
        assert all(game.state.objects[oid].zone is Zone.BATTLEFIELD for oid in others)
