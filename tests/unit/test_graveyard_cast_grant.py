""""Until end of turn, you may cast instant and sorcery spells from any graveyard."

Urabrask's third chapter, and Yawgmoth's Will before it. The engine's only
graveyard-cast permission was `cast_from_graveyard`, a **static**, and it is the
wrong shape three ways over for this sentence -- the same three ways
`BlockProhibition` inverted for "can't block":

- **It needs a permanent on the battlefield.** The chapter exiles the Saga in the
  same breath as granting the permission, so a static dies with its source before
  anybody could use it. `TestThePermissionOutlivesItsSource` is that claim, and
  the test card exiles itself for exactly that reason.
- **It has no clock.** This one ends with the turn.
- **It reaches its controller's own graveyard.** This one reaches the table.

`grant_playable` is the near miss and the interesting one, because it very nearly
works: it takes a selector, it is turn-scoped, and its `as_flashback` already
produces the exile the second printed sentence asks for. What it cannot be is
*standing*. It marks the cards it can see when it resolves, and a spell that
reaches a graveyard later in the same turn is castable under the printed card and
invisible to a snapshot. For a card whose whole point is a graveyard that refills
as you empty it, that is not a rounding error -- it is the loop.
`TestACardThatArrivesLater` is the difference.

The second printed sentence -- "if a spell cast this way would be put into a
graveyard, exile it instead" -- needed nothing at all. A graveyard cast already
exiles as it resolves, through `graveyard_cast_exiles`, which is why the grant is
spelled as an ordinary `cast_from_graveyard` static and read beside the real ones
rather than being a second implementation of the same permission.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until, settle_to_priority

ANY_GY = "t_yawgmoth"  # any_graveyard: true
OWN_GY = "t_own_graveyard_only"  # the same grant, own graveyard only
BAIT = "t_gy_gain"  # {R} instant, gain 2 life
OGRE = "t_gy_creature"  # {R} creature -- not an instant or sorcery


def position(builder, grant: str, *, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 6 + ["swamp"] * 3)
        .battlefield(1, ["plains"])
        .graveyard(0, list(mine))
        .graveyard(1, list(theirs))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [grant])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_the_grant(game, grant: str):
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == grant
    )
    game.apply(action)
    settle_to_priority(game)


def castable(game, oid: int) -> bool:
    return any(a.kind is ActionKind.CAST and a.source == oid for a in game.legal_actions())


def only_in(game, seat: int, card_id: str) -> int:
    found = [o for o in game.state.players[seat].graveyard if game.state.objects[o].def_id == card_id]
    assert len(found) == 1, f"expected one {card_id} in seat {seat}'s graveyard"
    return found[0]


class TestBeforeTheGrant:
    def test_a_graveyard_instant_is_not_castable(self, builder):
        """The control. Nothing below means anything without it."""
        game = position(builder, ANY_GY, mine=[BAIT])
        game._advance()
        assert not castable(game, only_in(game, 0, BAIT))


class TestYourOwnGraveyard:
    def test_the_instant_becomes_castable(self, builder):
        game = position(builder, ANY_GY, mine=[BAIT])
        oid = only_in(game, 0, BAIT)
        cast_the_grant(game, ANY_GY)

        assert castable(game, oid)

    def test_a_creature_card_does_not(self, builder):
        """"instant and sorcery spells" -- the `affects_spells` filter."""
        game = position(builder, ANY_GY, mine=[OGRE])
        oid = only_in(game, 0, OGRE)
        cast_the_grant(game, ANY_GY)

        assert not castable(game, oid)


class TestAnyGraveyard:
    def test_an_opponents_instant_becomes_castable(self, builder):
        """The half `cast_from_graveyard` could never reach."""
        game = position(builder, ANY_GY, theirs=[BAIT])
        oid = only_in(game, 1, BAIT)
        cast_the_grant(game, ANY_GY)

        assert castable(game, oid)

    def test_without_the_flag_it_does_not(self, builder):
        """Kept as a live card: the narrower permission must stay narrow.

        Widening *where the engine looks* without also asking, per card, whether
        a permission covers it would hand every graveyard to Edgar and to
        flashback.
        """
        game = position(builder, OWN_GY, theirs=[BAIT])
        oid = only_in(game, 1, BAIT)
        cast_the_grant(game, OWN_GY)

        assert not castable(game, oid)

    def test_and_your_own_still_is(self, builder):
        """The narrower card is narrower, not broken."""
        game = position(builder, OWN_GY, mine=[BAIT])
        oid = only_in(game, 0, BAIT)
        cast_the_grant(game, OWN_GY)

        assert castable(game, oid)


class TestThePermissionOutlivesItsSource:
    def test_the_granting_sorcery_is_in_exile(self, builder):
        """The premise: a static would have died here."""
        game = position(builder, ANY_GY, mine=[BAIT])
        cast_the_grant(game, ANY_GY)

        assert any(
            game.state.objects[o].def_id == ANY_GY for o in game.state.players[0].exile
        ), "the grant exiles itself, which is the whole reason it is not a static"

    def test_and_the_permission_still_stands(self, builder):
        game = position(builder, ANY_GY, mine=[BAIT])
        oid = only_in(game, 0, BAIT)
        cast_the_grant(game, ANY_GY)

        assert castable(game, oid)


class TestACardThatArrivesLater:
    """The difference from `grant_playable`, which snapshots.

    A card put into the graveyard *after* the grant resolved is castable under
    the printed sentence. This is the loop the card is played for.
    """

    def test_it_is_castable_too(self, builder):
        from automtg.engine.zones import move_object

        game = position(builder, ANY_GY, mine=[BAIT])
        cast_the_grant(game, ANY_GY)
        # A second instant reaches the graveyard after the fact.
        latecomer = game.state.players[0].library[0]
        move_object(game.state, latecomer, Zone.GRAVEYARD, cause="test")
        game.state.objects[latecomer].def_id = BAIT
        game._advance()

        assert castable(game, latecomer), "a standing permission, not a snapshot"


class TestTheSpellExilesOnResolution:
    def test_it_does_not_go_back_to_the_graveyard(self, builder):
        """The second printed sentence, which needed no code of its own.

        A graveyard cast already exiles as it resolves. Spelling the grant as an
        ordinary `cast_from_graveyard` static is what buys that for free.
        """
        game = position(builder, ANY_GY, mine=[BAIT])
        oid = only_in(game, 0, BAIT)
        cast_the_grant(game, ANY_GY)
        action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid)
        game.apply(action)
        settle_to_priority(game)

        assert game.state.objects[oid].zone is Zone.EXILE
        assert game.state.players[0].life == 42, "it resolved on the way"


class TestItEndsWithTheTurn:
    def test_the_permission_is_gone_next_turn(self, builder):
        game = position(builder, ANY_GY, mine=[BAIT])
        oid = only_in(game, 0, BAIT)
        cast_the_grant(game, ANY_GY)
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn
            and g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN,
        )

        assert not castable(game, oid)

    def test_and_the_record_is_dropped(self, builder):
        """Cleared rather than left to the turn check that reads it.

        A permission nobody clears accumulates one dead record per grant for the
        rest of the game.
        """
        game = position(builder, ANY_GY, mine=[BAIT])
        cast_the_grant(game, ANY_GY)
        assert game.state.graveyard_cast_grants
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert not game.state.graveyard_cast_grants


class TestTheLoaderRefusesAnUnmeteredPermission:
    def spell(self, effect):
        return {
            "id": "t_probe_gy",
            "name": "Probe Graveyard",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }

    def test_no_filter(self):
        """An empty filter frees the whole graveyard, so absence must be an error."""
        with pytest.raises(DslError, match="needs 'affects_spells'"):
            compile_card(
                CardModel.model_validate(
                    self.spell({"op": "grant_graveyard_cast", "grants_flashback": True})
                )
            )

    def test_neither_a_cap_nor_an_exile(self):
        """A permission that neither meters nor exiles is an engine, not a card."""
        with pytest.raises(DslError, match="max_per_turn"):
            compile_card(
                CardModel.model_validate(
                    self.spell(
                        {
                            "op": "grant_graveyard_cast",
                            "affects_spells": {"any_types": ["Instant"]},
                        }
                    )
                )
            )

    def test_a_cap_alone_is_enough(self):
        compile_card(
            CardModel.model_validate(
                self.spell(
                    {
                        "op": "grant_graveyard_cast",
                        "affects_spells": {"any_types": ["Instant"]},
                        "max_per_turn": 1,
                    }
                )
            )
        )
