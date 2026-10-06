"""The Bard, King of Dale deck: the rest of the list, card by card.

The second half of `test_bard_king_of_dale_deck.py`, which says why these files
exist -- gate 5 casts a card once and never activates or triggers anything after
it -- and holds the helpers this file shares. Each class is one card, and asserts
the printed sentence the gate could not reach, plus the near miss.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.cards.test_bard_king_of_dale_deck import (
    ANCHOR,
    BEAR,
    DRAW_TWO,
    activate,
    cast,
    declare_attack,
    library,
    to_step,
    tokens,
)
from tests.conftest import (
    _default_answer,
    action_for_card,
    activations,
    count_on_battlefield,
    oids_of,
    only_oid,
    pass_until,
    settle_to_priority,
)

# ----------------------------------------------------------------------
# the rest of the deck, where the gate could not reach the printed text
# ----------------------------------------------------------------------


def castable(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


def resolve_answering(game, answer) -> None:
    """Settle the stack, handing every non-priority decision to ``answer``."""
    for _ in range(200):
        p = game.pending()
        if p is None or (p.kind is DecisionKind.PRIORITY and not game.state.stack):
            return
        if p.kind is DecisionKind.PRIORITY:
            game.apply(_default_answer(game, p))
        else:
            game.apply(answer(game, p))
    raise AssertionError("the stack never settled")


def say_yes(game, p):
    if p.kind is DecisionKind.MAY:
        return next(a for a in game.legal_actions() if a.kind is ActionKind.YES)
    return _default_answer(game, p)


class TestAbandonedAirTemple:
    """"This land enters tapped unless you control a basic land." / "{3}{W}, {T}: Put
    a +1/+1 counter on each creature you control." """

    def test_the_counters_go_on_each_creature_you_control_only(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["abandoned_air_temple", BEAR, "grizzly_bears"] + ["plains"] * 4)
            .battlefield(1, [BEAR])
            .build()
        )
        activate(game, only_oid(game, "abandoned_air_temple", 0), 1)
        assert game.state.objects[only_oid(game, BEAR, 0)].counters.get("+1/+1") == 1
        assert game.state.objects[only_oid(game, "grizzly_bears", 0)].counters.get("+1/+1") == 1
        assert not game.state.objects[only_oid(game, BEAR, 1)].counters.get("+1/+1")

    def played(self, builder, board) -> bool:
        game = builder(players=2).battlefield(0, board).hand(0, ["abandoned_air_temple"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "abandoned_air_temple"))
        return game.state.objects[only_oid(game, "abandoned_air_temple", 0)].tapped

    def test_it_enters_untapped_beside_a_basic_land(self, builder):
        assert not self.played(builder, ["plains"])

    def test_it_enters_tapped_without_one(self, builder):
        """A nonbasic land is not a basic land."""
        assert self.played(builder, ["floodfarm_verge"])


class TestAlandraSkyDreamer:
    """"Whenever you draw your second card each turn, create a 2/2 blue Drake creature
    token with flying." / "Whenever you draw your fifth card each turn, Alandra and
    Drakes you control each get +X/+X until end of turn, where X is the number of
    cards in your hand." """

    def position(self, builder, hand):
        return (
            builder(players=2)
            .battlefield(0, ["alandra_sky_dreamer", BEAR] + ["plains"] * 3 + ["island"] * 3)
            .hand(0, hand)
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )

    def test_the_second_card_makes_one_drake(self, builder):
        game = self.position(builder, [DRAW_TWO])
        cast(game, DRAW_TWO)
        [drake] = tokens(game, "drake_2_2_u_flying", 0)
        assert "flying" in {str(k) for k in chars(game.state, drake.oid).keywords}

    def test_the_fifth_card_pumps_alandra_and_drakes_by_hand_size(self, builder):
        game = self.position(builder, ["secret_rendezvous", DRAW_TWO])
        alandra, bear = only_oid(game, "alandra_sky_dreamer", 0), only_oid(game, BEAR, 0)
        cast(game, "secret_rendezvous")
        assert len(tokens(game, "drake_2_2_u_flying", 0)) == 1, "only the second card, once"
        cast(game, DRAW_TWO)

        assert len(game.state.players[0].hand) == 5
        [drake] = tokens(game, "drake_2_2_u_flying", 0)
        assert (chars(game.state, alandra).power, chars(game.state, alandra).toughness) == (7, 9)
        assert chars(game.state, drake.oid).power == 7
        assert chars(game.state, bear).power == 2, "a Bear is not a Drake"


class TestArchaeomancersMap:
    """"Whenever a land an opponent controls enters, if that player controls more lands
    than you, you may put a land card from your hand onto the battlefield." """

    def position(self, builder, their_lands: int):
        return (
            builder(players=2)
            .battlefield(0, ["archaeomancer_s_map", "plains", "plains"])
            .hand(0, ["island", ANCHOR])
            .battlefield(1, ["plains"] * their_lands)
            .hand(1, ["plains", ANCHOR])
            .active(1)
            .build()
        )

    def play_their_land(self, game) -> None:
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 1)
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "plains"))
        resolve_answering(game, say_yes)

    def test_falling_behind_puts_a_land_from_hand_onto_the_battlefield(self, builder):
        game = self.position(builder, their_lands=2)
        self.play_their_land(game)
        assert count_on_battlefield(game, "island", 0) == 1

    def test_drawing_level_does_not(self, builder):
        """Two lands to their three would; one to two ties, and "more" is not a tie."""
        game = self.position(builder, their_lands=1)
        self.play_their_land(game)
        assert count_on_battlefield(game, "island", 0) == 0


class TestAshnodsAltar:
    """"Sacrifice a creature: Add {C}{C}." """

    def test_sacrificing_a_creature_adds_two_colorless(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["ashnod_s_altar", BEAR, "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        altar, bear = only_oid(game, "ashnod_s_altar", 0), only_oid(game, BEAR, 0)
        game.apply(activations(game, altar)[0])
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, p))

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.players[0].mana_pool.total() == 2

    def test_no_creature_no_mana(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["ashnod_s_altar", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        assert not activations(game, only_oid(game, "ashnod_s_altar", 0))


class TestAustereCommand:
    """"Choose two — • Destroy all artifacts. • Destroy all enchantments. • Destroy all
    creatures with mana value 3 or less. • Destroy all creatures with mana value 4 or
    greater."

    The gate takes the first two modes. The creature split is the other half.
    """

    def test_the_big_creature_mode_spares_the_small(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .hand(0, ["austere_command"])
            .battlefield(1, [BEAR, "elesh_norn_grand_cenobite", "sol_ring", "cathars_crusade"])
            .build()
        )
        norn = only_oid(game, "elesh_norn_grand_cenobite", 1)
        ring, crusade = only_oid(game, "sol_ring", 1), only_oid(game, "cathars_crusade", 1)
        game.apply(action_for_card(game, ActionKind.CAST, "austere_command"))
        for mode in (1, 3):
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == mode)
            )
        settle_to_priority(game)

        assert norn not in game.state.battlefield, "mana value 7"
        assert crusade not in game.state.battlefield
        assert ring in game.state.battlefield, "artifacts were not chosen"
        # The Bear survives Norn's -2/-2 only because Norn died with it.
        assert count_on_battlefield(game, BEAR, 1) == 1, "mana value 2"

    def test_the_small_creature_mode_spares_the_big(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .hand(0, ["austere_command"])
            .battlefield(1, [BEAR, "moonshaker_cavalry"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "austere_command"))
        for mode in (0, 2):
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == mode)
            )
        settle_to_priority(game)
        assert count_on_battlefield(game, BEAR, 1) == 0
        assert count_on_battlefield(game, "moonshaker_cavalry", 1) == 1


class TestCatharsCrusade:
    """"Whenever a creature you control enters, put a +1/+1 counter on each creature you
    control." """

    def test_a_creature_entering_grows_the_team_itself_included(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["cathars_crusade", "grizzly_bears", "forest", "forest"])
            .hand(0, [BEAR])
            .battlefield(1, ["t_five_five"])
            .build()
        )
        cast(game, BEAR)
        assert game.state.objects[only_oid(game, "grizzly_bears", 0)].counters.get("+1/+1") == 1
        assert game.state.objects[only_oid(game, BEAR, 0)].counters.get("+1/+1") == 1
        assert not game.state.objects[only_oid(game, "t_five_five", 1)].counters.get("+1/+1")

    def test_an_opponent_s_creature_entering_does_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["cathars_crusade", "grizzly_bears", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["forest", "forest"])
            .hand(1, [BEAR])
            .active(1)
            .build()
        )
        cast(game, BEAR, pid=1)
        assert not game.state.objects[only_oid(game, "grizzly_bears", 0)].counters.get("+1/+1")


class TestChivalricAlliance:
    """"Whenever you attack with two or more creatures, draw a card." / "{2}, Discard a
    card: Create a 2/2 white and blue Knight creature token with vigilance." """

    def attack(self, builder, bears: int) -> int:
        game = (
            builder(players=2)
            .battlefield(0, ["chivalric_alliance", "plains"] + [BEAR] * bears)
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN)
        before = library(game, 0)
        declare_attack(game, {oid: ("player", 1) for oid in oids_of(game, BEAR, 0)})
        settle_to_priority(game)
        return before - library(game, 0)

    def test_two_attackers_draw(self, builder):
        assert self.attack(builder, 2) == 1

    def test_one_attacker_does_not(self, builder):
        assert self.attack(builder, 1) == 0

    def test_discarding_makes_a_vigilant_knight(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["chivalric_alliance", "plains", "plains"])
            .hand(0, [BEAR])
            .build()
        )
        activate(game, only_oid(game, "chivalric_alliance", 0), 1)
        [knight] = tokens(game, "knight_2_2_wu_vigilance", 0)
        assert "vigilance" in {str(k) for k in chars(game.state, knight.oid).keywords}
        assert game.state.players[0].hand == [], "the Bear paid for it"

    def test_an_empty_hand_can_t_pay(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["chivalric_alliance", "plains", "plains"])
            .build(advance=False)
        )
        assert not activations(game, only_oid(game, "chivalric_alliance", 0), 1)


class TestDetectiveOfTheMonth:
    """"Ascend" / "As long as you have the city's blessing, Detectives you control can't
    be blocked." / "Whenever you draw your second card each turn, create a 2/2 white and
    blue Detective creature token." """

    def test_the_second_card_makes_a_detective(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["detective_of_the_month", "island", "island", "island"])
            .hand(0, [DRAW_TWO])
            .build()
        )
        cast(game, DRAW_TWO)
        assert len(tokens(game, "detective_2_2_wu", 0)) == 1

    def blockable(self, builder, permanents: int) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["detective_of_the_month", "detective_2_2_wu", "plains"])
            .battlefield(0, ["plains"] * (permanents - 3))
            .hand(0, [ANCHOR])
            .battlefield(1, [BEAR, "plains"])
            .hand(1, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        detective = only_oid(game, "detective_2_2_wu", 0)
        declare_attack(game, {detective: ("player", 1)})
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_BLOCKERS,
        )
        return any(
            a.kind is ActionKind.ADD_BLOCKER and detective in [t.id for t in a.targets]
            for a in game.legal_actions()
        )

    def test_with_ten_permanents_detectives_can_t_be_blocked(self, builder):
        assert not self.blockable(builder, 10)

    def test_with_nine_they_can(self, builder):
        assert self.blockable(builder, 9)


class TestEleshNornGrandCenobite:
    """"Other creatures you control get +2/+2." / "Creatures your opponents control get
    -2/-2." """

    def test_mine_grow_theirs_shrink_and_a_two_two_dies(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["elesh_norn_grand_cenobite", BEAR])
            .battlefield(1, [BEAR, "t_five_five"])
            .hand(0, [ANCHOR])
            .battlefield(0, ["plains"])
            .build()
        )
        norn = only_oid(game, "elesh_norn_grand_cenobite", 0)
        assert (chars(game.state, norn).power, chars(game.state, norn).toughness) == (4, 7), "other"
        mine = only_oid(game, BEAR, 0)
        assert (chars(game.state, mine).power, chars(game.state, mine).toughness) == (4, 4)
        five = only_oid(game, "t_five_five", 1)
        assert (chars(game.state, five).power, chars(game.state, five).toughness) == (3, 3)
        assert count_on_battlefield(game, BEAR, 1) == 0, "0 toughness, put into the graveyard"


class TestEmrakulsMessenger:
    """"Whenever you draw your second card each turn, create a 0/1 colorless Eldrazi
    Spawn creature token with "Sacrifice this token: Add {C}."" """

    def test_the_second_card_makes_a_spawn_and_the_third_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["emrakul_s_messenger"] + ["island"] * 3 + ["plains"] * 3)
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        cast(game, "secret_rendezvous")
        assert len(tokens(game, "eldrazi_spawn_0_1_c", 0)) == 1


class TestFlawlessManeuver:
    """"If you control a commander, you may cast this spell without paying its mana
    cost." """

    def position(self, builder, commander: bool):
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale"])
            .hand(0, ["flawless_maneuver"])
            .build(advance=False)
        )
        bard = only_oid(game, "bard_king_of_dale", 0)
        if commander:
            game.state.objects[bard].is_commander = True
            game.state.players[0].commanders.append(bard)
        game.state.bump_chars()
        game._advance()
        return game

    def test_with_the_commander_out_it_is_free(self, builder):
        assert castable(self.position(builder, commander=True), "flawless_maneuver")

    def test_the_same_creature_not_a_commander_does_not_pay_for_it(self, builder):
        assert not castable(self.position(builder, commander=False), "flawless_maneuver")


class TestFloodfarmVerge:
    """"{T}: Add {W}." / "{T}: Add {U}. Activate only if you control a Plains or an
    Island." """

    def position(self, builder, other: str | None):
        b = builder(players=2).battlefield(0, ["floodfarm_verge"]).hand(0, ["brainstorm", ANCHOR])
        if other:
            b = b.battlefield(0, [other], tapped=True)
        game = b.build()
        assert game.state.active_player == 0 and game.state.turn == 1, "stopped on my turn"
        return game

    def test_beside_a_plains_it_makes_blue(self, builder):
        """A tapped Plains pays nothing, but it is still a Plains you control."""
        assert castable(self.position(builder, "plains"), "brainstorm")

    def test_alone_it_makes_only_white(self, builder):
        game = self.position(builder, None)
        assert castable(game, ANCHOR)
        assert not castable(game, "brainstorm")


class TestGildedLotus:
    """"{T}: Add three mana of any one color." """

    def position(self, builder, spell: str):
        game = builder(players=2).battlefield(0, ["gilded_lotus"]).hand(0, [spell, ANCHOR]).build()
        assert game.state.active_player == 0 and game.state.turn == 1, "stopped on my turn"
        return game

    def test_it_pays_a_three_mana_blue_spell_alone(self, builder):
        assert castable(self.position(builder, DRAW_TWO), DRAW_TWO)

    def test_not_two_colours_at_once(self, builder):
        """"Any **one** color": {W}{U} is out of reach."""
        game = self.position(builder, "t_nth_draw_you")
        assert castable(game, ANCHOR), "white alone it makes"
        assert not castable(game, "t_nth_draw_you")


class TestHermesOverseerOfElpis:
    """"Whenever you cast a noncreature spell, create a 1/1 blue Bird creature token
    with flying and vigilance." / "Whenever you attack with one or more Birds, scry 2." """

    def test_a_noncreature_spell_makes_a_bird(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["hermes_overseer_of_elpis", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        cast(game, ANCHOR)
        [bird] = tokens(game, "bird_1_1_u_flying_vigilance", 0)
        assert {"flying", "vigilance"} <= {str(k) for k in chars(game.state, bird.oid).keywords}

    def test_a_creature_spell_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["hermes_overseer_of_elpis", "forest", "forest"])
            .hand(0, [BEAR])
            .build()
        )
        cast(game, BEAR)
        assert tokens(game, "bird_1_1_u_flying_vigilance") == []

    def scries(self, builder, attacker: str) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["hermes_overseer_of_elpis", attacker, "plains"])
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        declare_attack(game, {only_oid(game, attacker, 0): ("player", 1)})
        pass_until(
            game,
            lambda g: not g.state.stack
            or (g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS),
        )
        p = game.pending()
        return p.kind is DecisionKind.CHOOSE_OBJECTS and len(p.options) == 2

    def test_attacking_with_a_bird_scries_two(self, builder):
        assert self.scries(builder, "bird_1_1_u_flying_vigilance")

    def test_attacking_with_a_non_bird_does_not(self, builder):
        assert not self.scries(builder, BEAR)


class TestLoranOfTheThirdPath:
    """"{T}: You and target opponent each draw a card." """

    def test_both_players_draw(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, ["loran_of_the_third_path"])
            .build()
        )
        loran = only_oid(game, "loran_of_the_third_path", 0)
        before = [library(game, p) for p in range(3)]
        lines = activations(game, loran)
        assert sorted(a.targets[0].id for a in lines) == [1, 2], "an opponent, not me"
        at_two = next(a for a in lines if a.targets[0].id == 2)
        game.apply(at_two)
        settle_to_priority(game)
        assert [before[p] - library(game, p) for p in range(3)] == [1, 0, 1], "only the target"
        assert game.state.objects[loran].tapped


class TestLuminarchAscension:
    """"At the beginning of each opponent's end step, if you didn't lose life this turn,
    you may put a quest counter on this enchantment." / "{1}{W}: Create a 4/4 white
    Angel creature token with flying. Activate only if this enchantment has four or
    more quest counters on it." """

    def quest(self, builder, *, active: int, lose: bool = False) -> int:
        game = (
            builder(players=2)
            .battlefield(0, ["luminarch_ascension", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(active)
            .build()
        )
        if lose:
            from automtg.engine.primitives import lose_life

            lose_life(game.state, 0, 1)
        to_step(game, Step.END_STEP, active)
        resolve_answering(game, say_yes)
        return game.state.objects[only_oid(game, "luminarch_ascension", 0)].counters.get("quest", 0)

    def test_an_opponent_s_end_step_adds_a_quest_counter(self, builder):
        assert self.quest(builder, active=1) == 1

    def test_not_if_you_lost_life_this_turn(self, builder):
        assert self.quest(builder, active=1, lose=True) == 0

    def test_not_at_your_own_end_step(self, builder):
        assert self.quest(builder, active=0) == 0

    def angel_offered(self, builder, quest: int) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["luminarch_ascension"], counters={"quest": quest})
            .battlefield(0, ["plains", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        return bool(activations(game, only_oid(game, "luminarch_ascension", 0)))

    def test_four_counters_make_angels(self, builder):
        assert self.angel_offered(builder, 4)

    def test_three_do_not(self, builder):
        assert not self.angel_offered(builder, 3)


class TestMakindiStampede:
    """"Creatures you control get +2/+2 until end of turn." // Makindi Mesas: "This land
    enters tapped." """

    def test_the_pump_is_until_end_of_turn(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR] + ["plains"] * 5)
            .hand(0, ["makindi_stampede_makindi_mesas", ANCHOR])
            .battlefield(1, [BEAR, "plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        cast(game, "makindi_stampede_makindi_mesas")
        assert chars(game.state, mine).power == 4
        assert chars(game.state, theirs).power == 2, "creatures **you** control"
        pass_until(game, lambda g: g.state.active_player == 1)
        assert chars(game.state, mine).power == 2

    def test_the_back_face_is_a_tapped_land_drop(self, builder):
        game = builder(players=2).hand(0, ["makindi_stampede_makindi_mesas"]).build()
        line = next(
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.second_face
        )
        game.apply(line)
        obj = game.state.objects[line.source]
        assert game.state.card_of(obj).id == "makindi_mesas"
        assert obj.tapped


class TestMinasTirith:
    """"Minas Tirith enters tapped unless you control a legendary creature." / "{1}{W},
    {T}: Draw a card. Activate only if you attacked with two or more creatures this
    turn." """

    def played_tapped(self, builder, board) -> bool:
        game = builder(players=2).battlefield(0, board).hand(0, ["minas_tirith"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "minas_tirith"))
        return game.state.objects[only_oid(game, "minas_tirith", 0)].tapped

    def test_untapped_beside_a_legendary_creature(self, builder):
        assert not self.played_tapped(builder, ["bard_king_of_dale"])

    def test_tapped_beside_a_nonlegendary_one(self, builder):
        assert self.played_tapped(builder, [BEAR])

    def draw_offered_after_attacking_with(self, builder, bears: int) -> bool:
        game = (
            builder(players=2)
            .battlefield(0, ["minas_tirith", "plains", "plains"] + [BEAR] * bears)
            .hand(0, [ANCHOR])
            .step(Step.UPKEEP)
            .build()
        )
        declare_attack(game, {oid: ("player", 1) for oid in oids_of(game, BEAR, 0)})
        pass_until(
            game,
            lambda g: g.state.step is Step.POSTCOMBAT_MAIN
            and g.pending() is not None
            and g.pending().player == 0,
        )
        return bool(activations(game, only_oid(game, "minas_tirith", 0), 1))

    def test_after_attacking_with_two_the_draw_is_offered(self, builder):
        assert self.draw_offered_after_attacking_with(builder, 2)

    def test_after_attacking_with_one_it_is_not(self, builder):
        assert not self.draw_offered_after_attacking_with(builder, 1)


class TestMischievousMystic:
    """"Whenever you draw your second card each turn, create a 1/1 blue Faerie creature
    token with flying." """

    def test_draw_two_makes_one_faerie(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mischievous_mystic"] + ["island"] * 3 + ["plains"] * 3)
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        cast(game, "secret_rendezvous")
        assert len(tokens(game, "faerie_1_1_u_flying", 0)) == 1, "the second card, not the third"


class TestMonasteryMentor:
    """"Prowess" / "Whenever you cast a noncreature spell, create a 1/1 white Monk
    creature token with prowess." """

    def test_each_spell_makes_a_monk_and_the_monks_have_prowess(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["monastery_mentor", "plains", "plains"])
            .hand(0, [ANCHOR, ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        mentor = only_oid(game, "monastery_mentor", 0)
        cast(game, ANCHOR)
        [monk] = tokens(game, "monk_1_1_w_prowess", 0)
        assert chars(game.state, mentor).power == 3, "prowess"
        assert chars(game.state, monk.oid).power == 1, "made after the spell was cast"

        cast(game, ANCHOR)
        assert len(tokens(game, "monk_1_1_w_prowess", 0)) == 2
        assert chars(game.state, monk.oid).power == 2, "the first Monk's own prowess"

    def test_a_creature_spell_or_an_opponent_s_spell_makes_none(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["monastery_mentor", "forest", "forest"])
            .hand(0, [BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, BEAR)
        cast(game, ANCHOR, pid=1)
        assert tokens(game, "monk_1_1_w_prowess") == []
        assert chars(game.state, only_oid(game, "monastery_mentor", 0)).power == 2


class TestMoonshakerCavalry:
    """"When this creature enters, creatures you control gain flying and get +X/+X
    until end of turn, where X is the number of creatures you control." """

    def test_x_counts_the_team_including_itself(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, BEAR] + ["plains"] * 8)
            .hand(0, ["moonshaker_cavalry"])
            .battlefield(1, [BEAR, "plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        cast(game, "moonshaker_cavalry")
        bear = oids_of(game, BEAR, 0)[0]
        cavalry = only_oid(game, "moonshaker_cavalry", 0)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (5, 5)
        assert chars(game.state, cavalry).power == 9
        assert chars(game.state, only_oid(game, BEAR, 1)).power == 2, "not theirs"


class TestNadirKraken:
    """"Whenever you draw a card, you may pay {1}. If you do, put a +1/+1 counter on
    this creature and create a 1/1 blue Tentacle creature token." """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["nadir_kraken"] + ["island"] * 5)
            .hand(0, [DRAW_TWO])
            .build()
        )

    def test_paying_for_each_card_grows_it_twice(self, builder):
        game = self.position(builder)
        kraken = only_oid(game, "nadir_kraken", 0)
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_TWO))
        resolve_answering(game, say_yes)
        assert game.state.objects[kraken].counters.get("+1/+1") == 2
        assert len(tokens(game, "tentacle_1_1_u", 0)) == 2

    def test_declining_does_nothing(self, builder):
        game = self.position(builder)
        cast(game, DRAW_TWO)
        assert not game.state.objects[only_oid(game, "nadir_kraken", 0)].counters.get("+1/+1")
        assert tokens(game, "tentacle_1_1_u") == []


class TestNimbusMaze:
    """"{T}: Add {W}. Activate only if you control an Island." / "{T}: Add {U}. Activate
    only if you control a Plains." """

    def position(self, builder, other: str | None):
        # Ornithopter costs {0}: something castable keeps the turn from auto-passing
        # away on the board that makes no coloured mana at all.
        b = (
            builder(players=2)
            .battlefield(0, ["nimbus_maze"])
            .hand(0, ["brainstorm", ANCHOR, "ornithopter"])
        )
        if other:
            b = b.battlefield(0, [other], tapped=True)
        game = b.build()
        assert game.state.active_player == 0 and game.state.turn == 1, "stopped on my turn"
        return game

    def test_alone_it_makes_neither_colour(self, builder):
        game = self.position(builder, None)
        assert not castable(game, "brainstorm")
        assert not castable(game, ANCHOR)

    def test_an_island_unlocks_white_not_blue(self, builder):
        game = self.position(builder, "island")
        assert castable(game, ANCHOR)
        assert not castable(game, "brainstorm")

    def test_a_plains_unlocks_blue_not_white(self, builder):
        game = self.position(builder, "plains")
        assert castable(game, "brainstorm")
        assert not castable(game, ANCHOR)


class TestSecretRendezvous:
    """"You and target opponent each draw three cards." """

    def test_only_the_targeted_opponent_draws(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, ["plains"] * 3)
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        before = [library(game, p) for p in range(3)]
        cast(game, "secret_rendezvous", targets=next(
            a.targets
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and [t.id for t in a.targets] == [2]
        ))
        assert [before[p] - library(game, p) for p in range(3)] == [3, 0, 3]


class TestSicarianInfiltrator:
    """"Squad {2} (… you may pay {2} any number of times. When this creature enters,
    create that many tokens that are copies of it.)" / "When this creature enters, draw
    a card." """

    def test_squad_twice_makes_two_copies_and_each_draws(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7)
            .hand(0, ["sicarian_infiltrator"])
            .build()
        )
        before = library(game, 0)
        cast(game, "sicarian_infiltrator", additional_times=2)
        assert count_on_battlefield(game, "sicarian_infiltrator", 0) == 3
        assert len(tokens(game, "sicarian_infiltrator", 0)) == 2
        assert before - library(game, 0) == 3, "the copies have the enters trigger too"

    def test_unpaid_it_is_one_creature(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 7)
            .hand(0, ["sicarian_infiltrator"])
            .build()
        )
        cast(game, "sicarian_infiltrator", additional_times=0)
        assert count_on_battlefield(game, "sicarian_infiltrator", 0) == 1


class TestTataruTaru:
    """"When Tataru Taru enters, you draw a card and target opponent may draw a card." /
    "Whenever an opponent draws a card, if it isn't that player's turn, create a tapped
    Treasure token. This ability triggers only once each turn." """

    def test_an_opponent_drawing_on_my_turn_makes_one_treasure(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["tataru_taru", "plains", "plains", "plains"])
            .hand(0, ["secret_rendezvous"])
            .build()
        )
        cast(game, "secret_rendezvous")
        treasures = tokens(game, "treasure_token", 0)
        assert len(treasures) == 1, "three cards, once each turn"
        assert treasures[0].tapped

    def test_an_opponent_drawing_on_their_own_turn_makes_none(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["tataru_taru", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["island"] * 3)
            .hand(1, [DRAW_TWO])
            .active(1)
            .build()
        )
        cast(game, DRAW_TWO, pid=1)
        assert tokens(game, "treasure_token") == []

    def test_the_opponent_may_draw_when_it_enters(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "plains"])
            .hand(0, ["tataru_taru"])
            .build()
        )
        before = library(game, 1)
        game.apply(action_for_card(game, ActionKind.CAST, "tataru_taru"))
        asked = []

        def answer(g, p):
            asked.append(p.player)
            return say_yes(g, p)

        resolve_answering(game, answer)
        assert before - library(game, 1) == 1
        assert 1 in asked, "the opponent is the one who may"


class TestThopterFabricator:
    """"Whenever you draw your second card each turn, create a 1/1 colorless Thopter
    artifact creature token with flying." / "Crew 2" """

    def test_the_second_card_makes_a_thopter(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["thopter_fabricator", "island", "island", "island"])
            .hand(0, [DRAW_TWO])
            .build()
        )
        cast(game, DRAW_TWO)
        [thopter] = tokens(game, "thopter_1_1_c_flying", 0)
        assert "Artifact" in {str(t) for t in chars(game.state, thopter.oid).types}

    def test_a_bear_crews_it_into_a_creature(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["thopter_fabricator", BEAR, "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        fabricator = only_oid(game, "thopter_fabricator", 0)
        assert "Creature" not in {str(t) for t in chars(game.state, fabricator).types}
        game.apply(activations(game, fabricator, 1)[0])
        resolve_answering(game, _default_answer)
        assert "Creature" in {str(t) for t in chars(game.state, fabricator).types}
        assert game.state.objects[only_oid(game, BEAR, 0)].tapped

    def test_a_one_one_cannot(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["thopter_fabricator", "t_dork", "plains"])
            .hand(0, [ANCHOR])
            .build()
        )
        assert not activations(game, only_oid(game, "thopter_fabricator", 0), 1)


class TestWillOfTheMardu:
    """"Choose one. If you control a commander as you cast this spell, you may choose
    both instead." """

    def modes_allowed(self, builder, commander: bool) -> int:
        game = (
            builder(players=2)
            .battlefield(0, ["bard_king_of_dale"] + ["plains"] * 3)
            .hand(0, ["will_of_the_mardu"])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        if commander:
            bard = only_oid(game, "bard_king_of_dale", 0)
            game.state.objects[bard].is_commander = True
            game.state.players[0].commanders.append(bard)
        game.state.bump_chars()
        game._advance()
        game.apply(action_for_card(game, ActionKind.CAST, "will_of_the_mardu"))
        p = game.pending()
        assert p.kind is DecisionKind.CHOOSE_MODE
        return p.max_count

    def test_with_a_commander_both(self, builder):
        assert self.modes_allowed(builder, commander=True) == 2

    def test_without_one_only_one(self, builder):
        assert self.modes_allowed(builder, commander=False) == 1


class TestWitchEnchanter:
    """"When this creature enters, destroy target artifact or enchantment an opponent
    controls." // Witch-Blessed Meadow: "As this land enters, you may pay 3 life. If you
    don't, it enters tapped." """

    def test_my_own_artifact_is_not_a_target(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["sol_ring"] + ["plains"] * 4)
            .hand(0, ["witch_enchanter_witch_blessed_meadow"])
            .battlefield(1, ["cathars_crusade"])
            .build()
        )
        cast(game, "witch_enchanter_witch_blessed_meadow")
        assert count_on_battlefield(game, "sol_ring", 0) == 1
        assert count_on_battlefield(game, "cathars_crusade", 1) == 0

    def test_paying_three_life_the_meadow_enters_untapped(self, builder):
        game = builder(players=2).hand(0, ["witch_enchanter_witch_blessed_meadow"]).build()
        line = next(
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.second_face
        )
        game.apply(line)
        resolve_answering(game, say_yes)
        obj = game.state.objects[line.source]
        assert game.state.card_of(obj).id == "witch_blessed_meadow"
        assert not obj.tapped
        assert game.state.players[0].life == 37


class TestCaretakersTalent:
    """"Whenever one or more tokens you control enter, draw a card. This ability
    triggers only once each turn." / "{W}: Level 2" / "When this Class becomes level 2,
    create a token that's a copy of target token you control." / "{3}{W}: Level 3" /
    "Creature tokens you control get +2/+2."

    The gate cast it at level 1 into a sandbox where no token entered afterwards, and
    never bought a level.
    """

    LEVEL_2, LEVEL_3 = 1, 3
    ILLUSION = "illusion_1_1_u"

    def position(self, builder, *, level: int = 1, active: int = 0):
        game = (
            builder(players=2)
            .battlefield(0, ["caretaker_s_talent"], level=level)
            .battlefield(0, [self.ILLUSION, BEAR] + ["plains"] * 4)
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(active)
            .build(advance=False)
        )
        # Placed rather than created, so the builder does not know it is a token.
        game.state.objects[only_oid(game, self.ILLUSION, 0)].is_token = True
        game.state.bump_chars()
        game._advance()
        return game, only_oid(game, "caretaker_s_talent", 0)

    def test_two_token_creations_in_a_turn_draw_once(self, builder):
        """Hermes makes a Bird on each of two spells: two batches, one card."""
        game = (
            builder(players=2)
            .battlefield(0, ["caretaker_s_talent", "hermes_overseer_of_elpis", "plains", "plains"])
            .hand(0, [ANCHOR, ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        before = library(game, 0)
        cast(game, ANCHOR)
        assert before - library(game, 0) == 1
        cast(game, ANCHOR)
        assert len(tokens(game, "bird_1_1_u_flying_vigilance", 0)) == 2
        assert before - library(game, 0) == 1, "only once each turn"

    def test_a_nontoken_creature_entering_draws_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["caretaker_s_talent", "forest", "forest"])
            .hand(0, [BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .build()
        )
        before = library(game, 0)
        cast(game, BEAR)
        assert library(game, 0) == before

    def test_level_two_is_offered_at_level_one_only(self, builder):
        game, talent = self.position(builder)
        assert activations(game, talent, self.LEVEL_2)
        game, talent = self.position(builder, level=2)
        assert not activations(game, talent, self.LEVEL_2)

    def test_level_two_is_not_offered_at_instant_speed(self, builder):
        game, talent = self.position(builder, active=1)
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
        assert game.state.active_player == 1
        assert not activations(game, talent, self.LEVEL_2)

    def test_level_three_is_not_offered_at_level_one(self, builder):
        """A ladder: level 3 is bought from level 2, not skipped to."""
        game, talent = self.position(builder)
        assert not activations(game, talent, self.LEVEL_3)

    def test_becoming_level_two_copies_a_token_and_level_three_does_not_again(self, builder):
        game, talent = self.position(builder)
        activate(game, talent, self.LEVEL_2)
        assert game.state.objects[talent].class_level == 2
        assert len(tokens(game, self.ILLUSION, 0)) == 2, "the Illusion and its copy"
        assert count_on_battlefield(game, BEAR, 0) == 1, "a token, not the Bear"

        pass_until(game, lambda g: g.state.active_player == 1)
        pass_until(
            game,
            lambda g: g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN
            and g.pending() is not None
            and g.pending().player == 0,
        )
        activate(game, talent, self.LEVEL_3)
        assert game.state.objects[talent].class_level == 3
        assert len(tokens(game, self.ILLUSION, 0)) == 2, "level 2's trigger does not fire again"

    def test_at_level_three_creature_tokens_get_two(self, builder):
        game, _ = self.position(builder, level=3)
        illusion, bear = only_oid(game, self.ILLUSION, 0), only_oid(game, BEAR, 0)
        assert (chars(game.state, illusion).power, chars(game.state, illusion).toughness) == (3, 3)
        assert chars(game.state, bear).power == 2, "a nontoken creature is not buffed"

    def test_below_level_three_they_do_not(self, builder):
        game, _ = self.position(builder, level=2)
        assert chars(game.state, only_oid(game, self.ILLUSION, 0)).power == 1
