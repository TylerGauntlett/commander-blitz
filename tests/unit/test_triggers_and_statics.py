"""Triggered abilities, static abilities and derived characteristics."""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.objects import PLUS_ONE
from tests.conftest import action_for_card, find_action, oids_of, only_oid, pass_until


class TestTriggers:
    def test_enters_the_battlefield_trigger(self, builder):
        game = (
            builder()
            .hand(0, ["t_etb_draw"])
            .battlefield(0, ["island", "island", "island"])
            .library(0, ["forest", "forest", "forest"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_etb_draw"))
        assert len(game.state.players[0].hand) == 1

    def test_dies_trigger(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_dies_gain"])
            .hand(1, ["t_bolt"])
            .battlefield(1, ["mountain"])
            .build()
        )
        pass_until(game, lambda g: g.pending() and g.pending().player == 1, limit=800)
        bolt = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.targets and a.targets[0].kind == "object"
        )
        game.apply(bolt)
        assert not oids_of(game, "t_dies_gain", 0)
        assert game.state.players[0].life == 42

    def test_upkeep_trigger(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_upkeep_draw"])
            .library(0, ["forest", "forest", "forest", "forest"])
            .build()
        )
        before = len(game.state.players[0].hand)
        pass_until(game, lambda g: g.state.turn == 3, limit=800)
        assert len(game.state.players[0].hand) > before

    def test_landfall_trigger_adds_a_counter(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_landfall"])
            .hand(0, ["forest"])
            .build()
        )
        landfaller = only_oid(game, "t_landfall", 0)
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert game.state.objects[landfaller].counter(PLUS_ONE) == 1
        assert chars(game.state, landfaller).power == 2

    def test_play_a_land_trigger_draws(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_land_draw"])
            .hand(0, ["forest"])
            .library(0, ["island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert len(game.state.players[0].hand) == 1

    def test_the_land_drop_is_counted_before_landfall_sees_it(self, builder):
        """Ordering, not a count: `lands_played` has to be up to date when the
        ETB fires, or an intervening-if that counts drops this turn reads stale."""
        game = builder().battlefield(0, ["t_landfall"]).hand(0, ["forest"]).build()
        played_at_fire: list[int] = []
        original = game.state.emit

        def spy(event_type, **kwargs):
            if event_type == "enters_battlefield":
                played_at_fire.append(game.state.players[0].lands_played)
            return original(event_type, **kwargs)

        game.state.emit = spy  # type: ignore[method-assign]
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert played_at_fire == [1]


class TestLandfallAcrossZones:
    """Landfall is "a land you control enters", for any reason.

    Every route to the battlefield goes through the same `move_object`, so this
    is really a test that the ramp ops do not bypass it -- and that they leave
    the entering land under the right controller, which the `controller: "you"`
    clause on every landfall trigger is compared against.
    """

    @staticmethod
    def _resolve(game, picks: int) -> None:
        """Answer the search decisions by taking the first `picks` options."""
        for _ in range(picks):
            decision = game.pending()
            assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
            choose = next(
                a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE
            )
            game.apply(choose)

    def test_cultivate_gives_exactly_one_landfall_trigger(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_landfall", "forest", "forest", "forest"])
            .hand(0, ["cultivate"])
            .library(0, ["forest", "island", "island", "island"])
            .build()
        )
        landfaller = only_oid(game, "t_landfall", 0)
        game.apply(action_for_card(game, ActionKind.CAST, "cultivate"))
        self._resolve(game, 2)  # one to the battlefield, one to hand
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[landfaller].counter(PLUS_ONE) == 1

    def test_explosive_vegetation_gives_two(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_landfall", "forest", "forest", "forest", "forest"])
            .hand(0, ["explosive_vegetation"])
            .library(0, ["forest", "island", "island", "island"])
            .build()
        )
        landfaller = only_oid(game, "t_landfall", 0)
        game.apply(action_for_card(game, ActionKind.CAST, "explosive_vegetation"))
        self._resolve(game, 2)
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[landfaller].counter(PLUS_ONE) == 2

    def test_a_fetched_land_enters_under_your_control(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_landfall", "forest", "forest"])
            .hand(0, ["rampant_growth"])
            .library(0, ["forest", "island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "rampant_growth"))
        self._resolve(game, 1)
        pass_until(game, lambda g: not g.state.stack)
        fetched = [
            obj
            for obj in game.state.battlefield_objects()
            if obj.def_id == "forest" and obj.tapped
        ]
        assert fetched and all(obj.controller == 0 for obj in fetched)

    def test_putting_a_land_onto_the_battlefield_is_not_playing_one(self, builder):
        """Horn of Greed reads "whenever a player *plays* a land".

        Cultivate puts a land onto the battlefield; it does not play one, so a
        land-drop trigger stays silent. Landfall (above) fires either way. This
        is the rules distinction, pinned so the two spellings stay distinct.

        Aesi used to be cited here too, wrongly: it prints landfall and belongs
        with the tests below, not this one.
        """
        game = (
            builder()
            .battlefield(0, ["t_land_draw", "forest", "forest", "forest"])
            .hand(0, ["cultivate"])
            .library(0, ["forest", "island", "island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "cultivate"))
        self._resolve(game, 2)
        pass_until(game, lambda g: not g.state.stack)
        # The only card in hand is the one Cultivate put there, not a draw.
        drawn = [e for e in game.state.events if e.type == "draw"]
        assert drawn == []

    @staticmethod
    def _settle(game, *, accept: bool) -> None:
        """Empty the stack, answering every "you may" the same way.

        `pass_until`'s passive answer to a MAY is No, which would quietly
        decline the very draw these two tests are about.
        """
        want = ActionKind.YES if accept else ActionKind.NO
        for _ in range(200):
            decision = game.pending()
            if decision is None:
                return
            if decision.kind is DecisionKind.MAY:
                game.apply(next(a for a in game.legal_actions() if a.kind is want))
                continue
            if not game.state.stack:
                return
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))

    def _aesi_ramping(self, builder):
        return (
            builder()
            .battlefield(0, ["aesi_tyrant_of_gyre_strait", "forest", "forest", "forest"])
            .hand(0, ["cultivate"])
            .library(0, ["forest", "island", "island", "island"])
            .build()
        )

    def test_aesi_draws_off_a_land_put_onto_the_battlefield(self, builder):
        """Aesi prints landfall, so a *put* land draws like a played one.

        It was hand-authored against `land_played` from stale text and stayed
        silent through every ramp spell in its own deck -- which is the opposite
        of what the card says, and the reason this test exists.
        """
        game = self._aesi_ramping(builder)
        game.apply(action_for_card(game, ActionKind.CAST, "cultivate"))
        self._resolve(game, 2)  # one to the battlefield, one to hand
        self._settle(game, accept=True)
        drawn = [e for e in game.state.events if e.type == "draw"]
        assert len(drawn) == 1

    def test_aesi_still_draws_off_an_ordinary_land_drop(self, builder):
        """The half the old `land_played` wiring got right, kept honest.

        Playing a land goes through `move_object` before `LAND_PLAYED` fires, so
        landfall covers the land drop as well -- but that is the case a move to
        `permanent_enters` could plausibly have broken, and nothing else pins it
        for this card.
        """
        game = (
            builder()
            .battlefield(0, ["aesi_tyrant_of_gyre_strait"])
            .hand(0, ["forest"])
            .library(0, ["island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        self._settle(game, accept=True)
        drawn = [e for e in game.state.events if e.type == "draw"]
        assert len(drawn) == 1

    def test_aesis_draw_can_be_declined(self, builder):
        """"You *may* draw a card" -- so the No branch has to be real."""
        game = self._aesi_ramping(builder)
        game.apply(action_for_card(game, ActionKind.CAST, "cultivate"))
        self._resolve(game, 2)
        self._settle(game, accept=False)
        drawn = [e for e in game.state.events if e.type == "draw"]
        assert drawn == []

    def test_eminence_style_trigger_works_from_the_command_zone(self, builder):
        game = (
            builder()
            .commander(0, ["t_cast_trigger"])
            .hand(0, ["t_bear"])
            .battlefield(0, ["forest", "forest"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        assert oids_of(game, "vampire_1_1_bw", 0)

    def test_a_trigger_only_fires_for_its_controller(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_land_draw"])
            .hand(1, ["forest"])
            .build()
        )
        pass_until(
            game,
            lambda g: g.state.active_player == 1
            and any(a.kind is ActionKind.PLAY_LAND for a in g.legal_actions()),
            limit=800,
        )
        watcher = only_oid(game, "t_land_draw", 0)
        events = game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        # Assert on the event log: apply() runs on to player 0's next turn, where
        # their draw step would muddy a hand-size comparison.
        assert not [
            e for e in events if e.type == "ability_triggered" and e.source == watcher
        ]

    def test_enters_with_x_counters(self, builder):
        game = (
            builder()
            .hand(0, ["t_x_spell"])
            .battlefield(0, ["forest", "forest", "forest", "forest"])
            .build()
        )
        cast = action_for_card(game, ActionKind.CAST, "t_x_spell")
        # The action no longer carries X: legality offers the spell at its floor
        # and `game._cast` asks. See tests/unit/test_choose_x.py.
        assert cast.x == 0
        game.apply(cast)
        # `CHOOSE_X` is pending *before* the spell reaches the stack, so "the
        # stack is empty" is already true here and would not wait for anything.
        # `_default_answer` takes the maximum X, which is what legality used to
        # pin -- so this still measures a Hydra cast for 3.
        pass_until(game, lambda g: oids_of(g, "t_x_spell", 0))
        hydra = only_oid(game, "t_x_spell", 0)
        assert game.state.objects[hydra].counter(PLUS_ONE) == 3
        assert chars(game.state, hydra).power == 3


class TestStaticAbilities:
    def test_anthem_pumps_your_creatures_only(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_anthem", "t_bear"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        mine = oids_of(game, "t_bear", 0)[0]
        theirs = oids_of(game, "t_bear", 1)[0]
        assert chars(game.state, mine).power == 3
        assert chars(game.state, theirs).power == 2

    def test_lord_excludes_itself(self, builder):
        game = builder().battlefield(0, ["t_lord", "t_bear"]).build()
        lord = only_oid(game, "t_lord", 0)
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, lord).power == 2
        assert chars(game.state, bear).power == 3

    def test_two_lords_stack(self, builder):
        game = builder().battlefield(0, ["t_lord", "t_lord", "t_bear"]).build()
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, bear).power == 4

    def test_keyword_grant(self, builder):
        game = builder().battlefield(0, ["t_flying_granter", "t_bear"]).build()
        bear = only_oid(game, "t_bear", 0)
        assert "flying" in chars(game.state, bear).keywords

    def test_static_stops_applying_when_its_source_leaves(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_anthem", "t_bear"])
            .hand(1, ["t_bolt"])
            .battlefield(1, ["mountain"])
            .build()
        )
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, bear).power == 3
        anthem = only_oid(game, "t_anthem", 0)
        from automtg.engine.zones import move_object

        move_object(game.state, anthem, Zone.GRAVEYARD)
        assert chars(game.state, bear).power == 2

    def test_counters_and_anthems_combine(self, builder):
        game = builder().battlefield(0, ["t_anthem", "t_bear"], counters={PLUS_ONE: 2}).build()
        bear = only_oid(game, "t_bear", 0)
        # 2/2 base, +1/+1 from the anthem, +2/+2 from counters.
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (5, 5)

    def test_characteristic_cache_invalidates(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build()
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, bear).power == 2
        from automtg.engine.primitives import add_counters

        add_counters(game.state, bear, PLUS_ONE, 3)
        assert chars(game.state, bear).power == 5


class TestUntilEndOfTurn:
    def test_pump_wears_off_at_cleanup(self, builder):
        game = (
            builder()
            .hand(0, ["t_pump_spell"])
            .battlefield(0, ["forest", "t_bear"])
            .build()
        )
        bear = only_oid(game, "t_bear", 0)
        game.apply(action_for_card(game, ActionKind.CAST, "t_pump_spell"))
        assert chars(game.state, bear).power == 5
        pass_until(game, lambda g: g.state.turn == 2, limit=800)
        assert chars(game.state, bear).power == 2

    def test_damage_clears_at_cleanup(self, builder):
        game = builder().battlefield(0, ["t_big"]).build()
        giant = only_oid(game, "t_big", 0)
        from automtg.engine.primitives import damage_permanent

        damage_permanent(game.state, giant, 3, None)
        assert game.state.objects[giant].damage == 3
        pass_until(game, lambda g: g.state.turn == 2, limit=800)
        assert game.state.objects[giant].damage == 0


class TestActivatedAbilities:
    def test_sacrifice_cost_asks_which_creature(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_sac_outlet", "t_bear", "t_flyer"])
            .build()
        )
        activate = find_action(game, ActionKind.ACTIVATE)
        game.apply(activate)
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        game.apply(find_action(game, ActionKind.CHOOSE, choice=0))
        pass_until(game, lambda g: g.state.players[0].life != 40, limit=50)
        assert game.state.players[0].life == 41
        assert len(game.state.creatures(0)) == 1

    def test_mana_abilities_are_not_offered_as_actions(self, builder):
        game = builder().battlefield(0, ["forest"]).hand(0, ["t_bear"]).build()
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE]

    def test_summoning_sick_creature_cannot_tap_for_mana(self, builder):
        from automtg.engine.costs import mana_sources

        game = builder().battlefield(0, ["t_dork"], sick=True).build(advance=False)
        assert mana_sources(game.state, 0) == []

    def test_a_settled_mana_dork_can_tap(self, builder):
        from automtg.engine.costs import mana_sources

        game = builder().battlefield(0, ["t_dork"]).build(advance=False)
        assert len(mana_sources(game.state, 0)) == 1
