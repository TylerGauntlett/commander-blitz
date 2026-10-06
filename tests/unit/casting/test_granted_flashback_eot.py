""""Each instant and sorcery card in your graveyard gains flashback until end of turn."

Will of the Jeskai's second mode. A turn-scoped grant, at the card's own mana
cost, and the card is **exiled** as it resolves.

The exile is the whole difference between flashback and a permission, and it is
needed here where Lier's static needed nothing. Which path the cast took is why:

- A `cast_from_graveyard` static sets `cast_from_graveyard` on the spell, and
  `graveyard_cast_exiles` (True for everything but escape) already exiles it.
- A `grant_playable` permission sets neither flag. Without its own rider the
  card goes back to the graveyard and can be cast again immediately — as many
  times as the turn's mana allows, which is strictly better than printed.

`TestWithoutTheRider` keeps that spelling alive as a card and shows the
difference: same grant, same cast, one flag apart.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import settle_to_priority

FLASHBACK = "t_will_flashback"  # grants flashback
PLAIN = "t_will_no_exile"  # grants a bare permission
BAIT = "t_demo_draw"  # {R} instant sitting in the graveyard


def position(builder, granter: str):
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 6)
        .battlefield(1, ["plains"])
        .graveyard(0, [BAIT])
        .library(0, ["forest"] * 10)
        .hand(0, [granter])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def grant_then_flash_back(game, granter: str) -> Zone:
    """Resolve the granter, cast the graveyard card, report where it ends."""
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == granter
    )
    game.apply(action)
    settle_to_priority(game)

    bait = next(o for o in game.state.objects.values() if o.def_id == BAIT and o.owner == 0)
    cast = next((a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == bait.oid), None)
    assert cast is not None, "the graveyard card is castable under the grant"
    game.apply(cast)
    settle_to_priority(game)
    return bait.zone


class TestTheGrant:
    def test_the_graveyard_card_becomes_castable(self, builder):
        game = position(builder, FLASHBACK)
        assert grant_then_flash_back(game, FLASHBACK) is not None

    def test_a_flashed_back_card_is_exiled(self, builder):
        """One cast per card, which is what "flashback" buys over a permission."""
        game = position(builder, FLASHBACK)
        assert grant_then_flash_back(game, FLASHBACK) is Zone.EXILE


class TestWithoutTheRider:
    def test_a_bare_permission_leaves_it_recastable(self, builder):
        """The counterfactual, kept as a live card.

        Back in the graveyard and still permitted, so the same card can be cast
        again for as long as the turn's mana lasts.
        """
        game = position(builder, PLAIN)
        assert grant_then_flash_back(game, PLAIN) is Zone.GRAVEYARD
