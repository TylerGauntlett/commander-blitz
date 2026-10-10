"""Permanents whose activated abilities have been switched off for the turn.

"Its activated abilities can't be activated this turn" is not a characteristic
and not a keyword -- it is a permission. That distinction is the whole reason it
lives in `until_eot` and is read by legality and the mana solver rather than by
`chars`: a *mana* ability is an activated ability too, so a locked land that
still taps for mana would make the effect worth nothing against the only decks
that would mind it.

Koma, Cosmos Serpent is the card that needs it, so it is also the case here.
"""

from __future__ import annotations

from commanderblitz.engine.costs import mana_sources
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.primitives import lock_abilities
from tests.conftest import only_oid, pass_until

TAP_AND_LOCK, INDESTRUCTIBLE = 0, 1


class TestTheLockItself:
    def test_a_locked_land_makes_no_mana(self, builder):
        game = builder(players=2).battlefield(0, ["forest"] * 3).build()
        assert len(mana_sources(game.state, 0)) == 3

        lock_abilities(game.state, game.state.battlefield[0])
        assert len(mana_sources(game.state, 0)) == 2, "a locked land is not a mana source"

    def test_a_locked_permanent_offers_no_activated_abilities(self, builder):
        game = (
            builder(players=2).battlefield(0, ["swamp"] * 3 + ["mardu_hateblade"]).build()
        )
        blade = only_oid(game, "mardu_hateblade")

        def activations() -> int:
            return sum(
                1
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == blade
            )

        before = activations()
        lock_abilities(game.state, blade)
        assert before > 0, "the fixture should have had something to activate"
        assert activations() == 0

    def test_it_wears_off_at_end_of_turn(self, builder):
        """It is an until-end-of-turn effect, so cleanup already removes it."""
        game = builder(players=2).battlefield(0, ["forest"] * 3).build()
        lock_abilities(game.state, game.state.battlefield[0])
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1)
        assert len(mana_sources(game.state, 0)) == 3


class TestKomaUsesIt:
    """The activated ability: sacrifice another Serpent, choose one."""

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["koma_cosmos_serpent", "komas_coil_3_3_u"])
            .battlefield(1, ["forest"])
            .build()
        )

    def activate(self, game, mode: int, target_oid: int):
        koma = only_oid(game, "koma_cosmos_serpent")
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == koma
            and any(ref.id == target_oid for ref in a.targets)
        )
        game.apply(action)
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_MODE,
        )
        choose = next(
            a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == mode
        )
        game.apply(choose)

    def test_it_costs_another_serpent(self, builder):
        game = self.board(builder)
        coil = only_oid(game, "komas_coil_3_3_u")
        their_land = game.state.battlefield_objects(1)[0].oid

        self.activate(game, TAP_AND_LOCK, their_land)
        assert game.state.objects[coil].zone.value == "graveyard"

    def test_the_first_mode_taps_and_locks(self, builder):
        game = self.board(builder)
        their_land = game.state.battlefield_objects(1)[0].oid

        self.activate(game, TAP_AND_LOCK, their_land)
        assert game.state.objects[their_land].tapped
        assert game.state.objects[their_land].abilities_locked
        assert mana_sources(game.state, 1) == []

    def test_the_second_mode_makes_koma_indestructible(self, builder):
        from commanderblitz.engine.characteristics import chars

        game = self.board(builder)
        koma = only_oid(game, "koma_cosmos_serpent")
        their_land = game.state.battlefield_objects(1)[0].oid

        self.activate(game, INDESTRUCTIBLE, their_land)
        assert "indestructible" in chars(game.state, koma).keywords
        # The first mode's half must not have happened as well.
        assert not game.state.objects[their_land].tapped

    def test_the_upkeep_trigger_makes_a_coil_for_every_players_upkeep(self, builder):
        """"At the beginning of *each* upkeep" -- not just yours."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["koma_cosmos_serpent"])
            .build()
        )

        def coils() -> int:
            return sum(
                1
                for o in game.state.battlefield_objects(0)
                if o.def_id == "komas_coil_3_3_u"
            )

        start = game.state.turn
        # Far enough that two upkeeps -- one each -- have been and gone. Only
        # one of them is ours, so "each upkeep" and "your upkeep" give different
        # answers here, which is the whole point of the assertion.
        pass_until(game, lambda g: g.state.turn > start + 2)
        assert coils() == 2, "one per upkeep, whoever's turn it is"
