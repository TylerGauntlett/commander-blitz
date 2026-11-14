""""You may cast it this turn. If that spell would be put into a graveyard,
exile it instead." -- a play permission's ``playable_exiles``.

Mission Briefing (`grant_playable` over your graveyard) and Dire Fleet
Daredevil (`exile` from an opponent's graveyard) are the witnesses.

**The rules argument.** The second sentence is a replacement effect (614.1a)
on the *spell*, not a resolution rider: it watches every way the spell can be
put into a graveyard. A spell can get there three ways -- by resolving
(608.2n), by being countered (701.6a) and by fizzling for want of targets
(608.2b) -- and the replacement exiles it on all three. Read only at
resolution, a countered or fizzled spell would land back in the graveyard
still carrying the turn's permission, castable again, and the card would be a
strictly better one than printed.

So the permission stamps the rider on the stack item as the spell is cast
under it (`StackItem.exiles_instead`), the one flag all three paths already
read. `as_flashback` ("gains flashback", Will of the Jeskai) sets the same
rider, and flashback's exile holds on the same three paths (702.34a).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, pass_until, settle, settle_to_priority

BRIEFING = "t_pe_briefing"  # grant_playable, playable_exiles
DAREDEVIL = "t_pe_daredevil"  # exile from an opponent's graveyard, playable_exiles
FLASHBACK = "t_will_flashback"  # grant_playable, as_flashback
PLAIN = "t_will_no_exile"  # grant_playable, no rider
BOLT = "t_bolt"  # {R}: 3 damage to target creature
BEAR = "t_bear"
COUNTERSPELL = "t_counterspell"


def position(builder, granter: str, *, response: str = COUNTERSPELL, theirs: bool = False):
    """Player 0 holds ``granter`` with a Bolt in a graveyard -- their own, or
    player 1's when ``theirs`` -- and player 1 has a Bear and ``response``.
    Returns ``(game, bolt_oid)``."""
    builder = (
        builder(players=2)
        .battlefield(0, ["mountain"] * 6 + ["island"] * 2)
        .battlefield(1, [BEAR, "island", "island", "mountain"])
        .hand(0, [granter])
        .hand(1, [response])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .graveyard(1 if theirs else 0, [BOLT])
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
    )
    game = builder.build()
    bolt = next(
        o.oid
        for o in game.state.objects.values()
        if o.def_id == BOLT and o.zone is Zone.GRAVEYARD
    )
    return game, bolt


def bear_of(game) -> int:
    return next(o.oid for o in game.state.objects.values() if o.def_id == BEAR)


def grant(game, granter: str) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, granter))
    settle_to_priority(game)


def bolt_the_bear(game, bolt: int):
    """Cast the granted Bolt at the Bear, if the permission offers it."""
    bear = bear_of(game)
    cast = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and a.source == bolt
            and a.targets
            and a.targets[0].id == bear
        ),
        None,
    )
    assert cast is not None, "the granted card is castable"
    game.apply(cast)


def respond(game, card_id: str) -> None:
    """Player 1 answers on the stack with ``card_id``: a counter, or their own
    Bolt at the Bear so the granted one fizzles."""
    pass_until(game, lambda g: g.pending().player == 1)
    if card_id == COUNTERSPELL:
        game.apply(action_for_card(game, ActionKind.CAST, COUNTERSPELL))
    else:
        bear = bear_of(game)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == card_id
                and a.targets
                and a.targets[0].id == bear
            )
        )
    settle(game)


def castable(game, oid: int) -> bool:
    return any(a.kind is ActionKind.CAST and a.source == oid for a in game.legal_actions())


def fizzled(game) -> bool:
    return any(e.type == "spell_fizzled" for e in game.state.events)


class TestTheRiderRidesOnTheStackItem:
    def test_the_cast_under_the_permission_carries_it(self, builder):
        game, bolt = position(builder, BRIEFING)
        grant(game, BRIEFING)
        bolt_the_bear(game, bolt)
        assert game.state.stack[-1].exiles_instead

    def test_a_bare_permission_does_not(self, builder):
        game, bolt = position(builder, PLAIN)
        grant(game, PLAIN)
        bolt_the_bear(game, bolt)
        assert not game.state.stack[-1].exiles_instead


class TestEveryWayIntoAGraveyard:
    def test_resolved_it_is_exiled(self, builder):
        game, bolt = position(builder, BRIEFING)
        grant(game, BRIEFING)
        bolt_the_bear(game, bolt)
        settle(game)
        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_countered_it_is_exiled(self, builder):
        game, bolt = position(builder, BRIEFING)
        grant(game, BRIEFING)
        bolt_the_bear(game, bolt)
        respond(game, COUNTERSPELL)
        assert any(e.type == "spell_countered" for e in game.state.events)
        assert game.state.objects[bolt].zone is Zone.EXILE
        assert not castable(game, bolt)

    def test_fizzled_it_is_exiled(self, builder):
        game, bolt = position(builder, BRIEFING, response=BOLT)
        grant(game, BRIEFING)
        bolt_the_bear(game, bolt)
        respond(game, BOLT)
        assert fizzled(game)
        assert game.state.objects[bolt].zone is Zone.EXILE


class TestFromAnOpponentsGraveyard:
    """Dire Fleet Daredevil: the card is theirs, the permission is yours, and
    "a graveyard" is its owner's -- which the rider replaces all the same."""

    def test_cast_with_any_type_and_exiled_on_resolution(self, builder):
        game, bolt = position(builder, DAREDEVIL, theirs=True)
        grant(game, DAREDEVIL)
        assert game.state.objects[bolt].zone is Zone.EXILE
        bolt_the_bear(game, bolt)
        settle(game)
        assert game.state.objects[bolt].zone is Zone.EXILE
        assert bolt not in game.state.players[1].graveyard

    def test_countered_it_stays_out_of_its_owners_graveyard(self, builder):
        game, bolt = position(builder, DAREDEVIL, theirs=True)
        grant(game, DAREDEVIL)
        bolt_the_bear(game, bolt)
        respond(game, COUNTERSPELL)
        assert game.state.objects[bolt].zone is Zone.EXILE
        assert bolt not in game.state.players[1].graveyard


class TestTheWitnesses:
    """The shipped cards, end to end: the permission granted, the spell cast
    under it and countered, and the card in exile rather than back where it
    could be cast again."""

    def test_mission_briefing(self, builder):
        game, bolt = position(builder, "mission_briefing")
        grant(game, "mission_briefing")
        bolt_the_bear(game, bolt)
        respond(game, COUNTERSPELL)
        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_dire_fleet_daredevil(self, builder):
        game, bolt = position(builder, "dire_fleet_daredevil", theirs=True)
        grant(game, "dire_fleet_daredevil")
        assert game.state.objects[bolt].zone is Zone.EXILE
        bolt_the_bear(game, bolt)
        respond(game, COUNTERSPELL)
        assert game.state.objects[bolt].zone is Zone.EXILE
        assert bolt not in game.state.players[1].graveyard


class TestGrantedFlashbackSharesTheSeam:
    """`as_flashback` sets the same rider, so a granted flashback that is
    countered or fizzles is exiled too (702.34a) -- and a bare permission is
    the counterfactual, back in the graveyard to be cast again."""

    def test_a_countered_flashback_is_exiled(self, builder):
        game, bolt = position(builder, FLASHBACK)
        grant(game, FLASHBACK)
        bolt_the_bear(game, bolt)
        respond(game, COUNTERSPELL)
        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_a_fizzled_flashback_is_exiled(self, builder):
        game, bolt = position(builder, FLASHBACK, response=BOLT)
        grant(game, FLASHBACK)
        bolt_the_bear(game, bolt)
        respond(game, BOLT)
        assert fizzled(game)
        assert game.state.objects[bolt].zone is Zone.EXILE

    def test_a_countered_bare_permission_is_castable_again(self, builder):
        game, bolt = position(builder, PLAIN)
        grant(game, PLAIN)
        bolt_the_bear(game, bolt)
        respond(game, COUNTERSPELL)
        assert game.state.objects[bolt].zone is Zone.GRAVEYARD


class TestTheLoaderGuard:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_pe_probe",
                "name": "Test Playable Exiles Probe",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "oracle_text": "Probe.",
                "spell_effects": [effect],
            }
        )

    def test_the_printed_forms_load(self):
        compile_card(
            self._card(
                {"op": "grant_playable", "playable_exiles": True, "objects": {"zone": "graveyard"}}
            )
        )
        compile_card(
            self._card(
                {
                    "op": "exile",
                    "objects": {"zone": "graveyard"},
                    "playable": "this_turn",
                    "playable_exiles": True,
                }
            )
        )

    def test_a_bare_exile_is_refused(self):
        with pytest.raises(DslError, match="playable_exiles"):
            compile_card(
                self._card(
                    {"op": "exile", "objects": {"zone": "graveyard"}, "playable_exiles": True}
                )
            )

    @pytest.mark.parametrize("value", ["true", 1, False])
    def test_a_non_true_value_is_refused(self, value):
        with pytest.raises(DslError, match="playable_exiles"):
            compile_card(
                self._card(
                    {"op": "grant_playable", "playable_exiles": value, "objects": {"zone": "graveyard"}}
                )
            )

    @pytest.mark.parametrize("key", ["as_flashback", "as_adventure"])
    def test_beside_another_exile_is_refused(self, key):
        with pytest.raises(DslError, match="playable_exiles"):
            compile_card(
                self._card(
                    {
                        "op": "grant_playable",
                        "playable_exiles": True,
                        key: True,
                        "objects": {"zone": "graveyard"},
                    }
                )
            )
