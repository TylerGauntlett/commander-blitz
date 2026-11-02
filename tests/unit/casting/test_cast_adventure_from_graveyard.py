"""A play permission that reaches only a card's Adventure half.

    When Hildibrand Manderville dies, you may cast it from your graveyard as an
    Adventure until the end of your next turn.  (Hildibrand Manderville //
    Gentleman's Rise)

715.3: a player casting an adventurer card chooses whether to cast it "as an
Adventure", and the permission names that choice. So the line offered out of the
graveyard is the Adventure's -- timed, priced and targeted off Gentleman's Rise --
and never the creature's. Without `as_adventure` the same `grant_playable` offers
the front face, which is the near miss: a 2-mana creature recast from the
graveyard every time it dies, a different and stronger card than printed.

Resolved, the Adventure goes on its adventure in exile as any Adventure does
(715.3d), so the creature may be cast from there afterwards; the graveyard
permission does not outlive the zone change (400.7) nor its printed duration.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import pass_until, settle_completely

HILDI = "t_afg_hildi"
PLAIN = "t_afg_plain"
KILL = "t_afg_kill"


def position(builder, creature: str = HILDI):
    """Seat 0 controls the adventurer and six Swamps, and holds the removal.

    Returns ``(game, oid)`` with the game started in seat 0's main phase.
    """
    game = (
        builder(players=2)
        .battlefield(0, [creature] + ["swamp"] * 6)
        .battlefield(1, ["swamp"] * 4)
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .hand(0, [KILL])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    oid = next(o.oid for o in game.state.objects.values() if o.def_id == creature)
    return game, oid


def died(builder, creature: str = HILDI):
    """The adventurer has died to seat 0's own removal and its trigger resolved."""
    game, oid = position(builder, creature)
    kill = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == KILL
        and a.targets
        and a.targets[0].id == oid
    )
    game.apply(kill)
    settle_completely(game)
    assert game.state.objects[oid].zone is Zone.GRAVEYARD
    return game, oid


def casts(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


class TestOnlyTheAdventure:
    def test_the_adventure_is_offered_from_the_graveyard(self, builder):
        game, oid = died(builder)
        lines = casts(game, oid)
        assert lines
        assert all(a.second_face for a in lines)

    def test_the_creature_face_is_not(self, builder):
        game, oid = died(builder)
        assert not [a for a in casts(game, oid) if not a.second_face]

    def test_the_near_miss_without_the_key_offers_the_creature(self, builder):
        game, oid = died(builder, PLAIN)
        lines = casts(game, oid)
        assert any(not a.second_face for a in lines)
        assert not any(a.second_face for a in lines)

    def test_it_is_timed_off_the_adventure(self, builder):
        """Gentleman's Rise is an instant, so the line is open on the
        opponent's turn, where the creature face never would be."""
        game, oid = died(builder)
        pass_until(
            game,
            lambda g: g.state.turn == 2
            and g.state.step is Step.UPKEEP
            and g.pending() is not None
            and g.pending().player == 0,
        )
        assert casts(game, oid)


class TestResolving:
    def test_it_resolves_onto_an_adventure(self, builder):
        game, oid = died(builder)
        life = game.state.players[0].life
        game.apply(casts(game, oid)[0])
        settle_completely(game)
        obj = game.state.objects[oid]
        assert game.state.players[0].life == life + 3
        assert obj.zone is Zone.EXILE
        assert obj.on_adventure

    def test_the_creature_is_then_castable_from_exile(self, builder):
        game, oid = died(builder)
        game.apply(casts(game, oid)[0])
        settle_completely(game)
        pass_until(
            game,
            lambda g: g.state.turn == 3
            and g.state.step is Step.PRECOMBAT_MAIN
            and g.pending() is not None
            and g.pending().player == 0,
        )
        lines = casts(game, oid)
        assert lines and all(not a.second_face for a in lines)

    def test_the_cast_spends_the_permission(self, builder):
        """The card left the graveyard, so the grant on it is gone (400.7):
        out of exile it is the creature that is offered, never the half again."""
        game, oid = died(builder)
        game.apply(casts(game, oid)[0])
        settle_completely(game)
        obj = game.state.objects[oid]
        assert not obj.playable_as_adventure
        assert obj.playable_by is None
        assert not any(a.second_face for a in casts(game, oid))


class TestDuration:
    def test_it_lasts_through_your_next_turn(self, builder):
        game, oid = died(builder)
        pass_until(
            game,
            lambda g: g.state.turn == 3
            and g.state.step is Step.END_STEP
            and g.pending() is not None
            and g.pending().player == 0,
        )
        assert casts(game, oid)

    def test_it_ends_after_your_next_turn(self, builder):
        game, oid = died(builder)
        pass_until(
            game,
            lambda g: g.state.turn == 4 and g.pending() is not None and g.pending().player == 0,
        )
        assert not casts(game, oid)
        obj = game.state.objects[oid]
        assert obj.playable_by is None
        assert not obj.playable_as_adventure


class TestTheLoader:
    def card(self, effect, *, adventure: bool = True):
        model = {
            "id": "t_probe_afg",
            "name": "Probe Afg",
            "mana_cost": "{1}{B}",
            "types": ["Creature"],
            "power": 2,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "dies", "source": "self"},
                    "effects": [effect],
                }
            ],
        }
        if adventure:
            model["second_face"] = "t_afg_rise"
            model["adventure"] = True
        return compile_card(CardModel.model_validate(model))

    GRANT = {
        "op": "grant_playable",
        "objects": {"self_only": True, "zone": "graveyard"},
        "playable": "end_of_your_next_turn",
        "as_adventure": True,
    }

    def test_it_loads_on_an_adventurer(self):
        self.card(dict(self.GRANT))

    def test_a_card_with_no_adventure_is_refused(self):
        with pytest.raises(DslError, match="adventurer"):
            self.card(dict(self.GRANT), adventure=False)

    def test_it_needs_grant_playable(self):
        effect = {"op": "exile", "objects": {"self_only": True, "zone": "graveyard"},
                  "playable": "this_turn", "as_adventure": True}
        with pytest.raises(DslError, match="as_adventure"):
            self.card(effect)

    def test_the_only_value_is_true(self):
        with pytest.raises(DslError, match="only value"):
            self.card({**self.GRANT, "as_adventure": False})

    def test_flashback_beside_it_is_refused(self):
        with pytest.raises(DslError, match="as_flashback"):
            self.card({**self.GRANT, "as_flashback": True})

    def test_free_beside_it_is_refused(self):
        with pytest.raises(DslError, match="playable_free"):
            self.card({**self.GRANT, "playable_free": True})
