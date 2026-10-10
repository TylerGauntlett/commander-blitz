"""The Sheoldred, the Apocalypse deck: the cards the new engine capabilities unblocked.

Split from `test_sheoldred_the_apocalypse_deck.py`, which says why these files
exist and holds the helpers this file shares. Each class is one card the engine
could not express until a capability landed for it, and asserts what it prints.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars, protection_from
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.structs import TargetRef
from tests.cards.test_sheoldred_the_apocalypse_deck import (
    ANCHOR,
    BEAR,
    BIG,
    BLACK_BEAR,
    BOLT,
    DRAW_TWO,
    FILLER,
    START,
    activate,
    anchored,
    between_turns,
    cast,
    cast_line,
    castable,
    choose_target,
    decide,
    drawn_since,
    hand,
    i_draw_two,
    libraries,
    library,
    lives,
    opponent_draws_two,
    through_draw_step,
    to_step,
    wait_to_cast,
)
from tests.conftest import (
    _default_answer,
    activations,
    count_on_battlefield,
    only_oid,
    pass_until,
    pt,
    settle_to_priority,
)

# ----------------------------------------------------------------------
# the cards the new engine capabilities unblocked
# ----------------------------------------------------------------------


def resolve_answering(game, answers=None, limit: int = 200) -> list[DecisionKind]:
    """Pass until the stack is empty, answering each non-priority decision with
    ``answers[kind](actions)`` when given and the passive answer otherwise.
    Returns the decision kinds seen."""
    answers = answers or {}
    seen = []
    for _ in range(limit):
        p = game.pending()
        if p is None or (p.kind is DecisionKind.PRIORITY and not game.state.stack):
            return seen
        seen.append(p.kind)
        if p.kind in answers:
            game.apply(answers[p.kind](game.legal_actions()))
        else:
            game.apply(_default_answer(game, p))
    raise AssertionError("the stack never emptied")


def yes(actions):
    return next(a for a in actions if a.kind is ActionKind.YES)


class TestAlhammarretsArchive:
    """"If you would gain life, you gain twice that much life instead." / "If you
    would draw a card except the first one you draw in each of your draw steps, draw
    two cards instead." """

    def test_the_first_card_of_my_draw_step_is_not_doubled_and_the_next_is(self, builder):
        """Howling Mine's extra card is the second one drawn in the step: two."""
        game = between_turns(builder, boards={0: ["alhammarret_s_archive", "howling_mine"]})
        assert through_draw_step(game, 0) == [3, 0]

    def test_alone_my_draw_step_draws_one(self, builder):
        game = between_turns(builder, boards={0: ["alhammarret_s_archive"]})
        assert through_draw_step(game, 0) == [1, 0]

    def test_a_main_phase_draw_two_draws_four(self, builder):
        game = i_draw_two(builder, "alhammarret_s_archive")
        assert FILLER - library(game, 0) == 4
        assert library(game, 1) == FILLER

    def test_an_opponent_s_draw_is_not_doubled(self, builder):
        game = opponent_draws_two(builder, "alhammarret_s_archive")
        assert FILLER - library(game, 1) == 2

    def test_a_gain_is_doubled(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["alhammarret_s_archive"])).build()
        cast(game, ANCHOR)
        assert lives(game) == [START + 2, START]

    def test_an_opponent_s_gain_is_not(self, builder):
        """"If **you** would gain life"."""
        game = anchored(
            builder(players=2).battlefield(0, ["alhammarret_s_archive"]).active(1)
        ).build()
        cast(game, ANCHOR, pid=1)
        assert lives(game) == [START, START + 1]


class TestBalefulMastery:
    """"You may pay {1}{B} rather than pay this spell's mana cost." / "If the {1}{B}
    cost was paid, an opponent draws a card." / "Exile target creature or
    planeswalker." """

    def position(self, builder, swamps: int = 4, theirs: str = BEAR):
        return anchored(
            builder(players=2)
            .battlefield(0, ["swamp"] * swamps)
            .hand(0, ["baleful_mastery"])
            .battlefield(1, [theirs])
        ).build()

    def test_the_alternative_cost_exiles_and_the_opponent_draws(self, builder):
        game = self.position(builder)
        bear = only_oid(game, BEAR, 1)
        before = libraries(game)
        cast(game, "baleful_mastery", evoked=True, targets=(TargetRef.obj(bear),))
        assert game.state.objects[bear].zone is Zone.EXILE
        assert drawn_since(before, game) == [0, 1]

    def test_the_full_cost_hands_out_nothing(self, builder):
        game = self.position(builder)
        bear = only_oid(game, BEAR, 1)
        before = libraries(game)
        cast(game, "baleful_mastery", evoked=False, targets=(TargetRef.obj(bear),))
        assert game.state.objects[bear].zone is Zone.EXILE
        assert drawn_since(before, game) == [0, 0]

    def test_two_swamps_reach_only_the_alternative(self, builder):
        game = self.position(builder, swamps=2)
        lines = {
            a.evoked
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "baleful_mastery"
        }
        assert lines == {True}

    def test_it_exiles_a_planeswalker(self, builder):
        game = self.position(builder, theirs="t_walker")
        walker = only_oid(game, "t_walker", 1)
        cast(game, "baleful_mastery", evoked=False, targets=(TargetRef.obj(walker),))
        assert game.state.objects[walker].zone is Zone.EXILE


class TestCommandersPlate:
    """"Equipped creature gets +3/+3 and has protection from each color that's not in
    your commander's color identity." / "Equip commander {3}" / "Equip {5}"

    Sheoldred, mono-black, waits in the command zone and is cast from it.
    """

    def position(self, builder):
        game = anchored(
            builder(players=2)
            .commander(0, ["sheoldred_the_apocalypse"])
            .battlefield(0, ["commander_s_plate", BEAR] + ["swamp"] * 4 + ["plains"] * 4)
        ).build()
        return game, only_oid(game, "commander_s_plate", 0), only_oid(game, BEAR, 0)

    @staticmethod
    def reach(game, plate: int, index: int) -> set[int]:
        return {t.id for a in activations(game, plate, index) for t in a.targets}

    def test_equip_commander_has_nothing_to_reach_before_the_commander_lands(self, builder):
        game, plate, bear = self.position(builder)
        assert self.reach(game, plate, 2) == set()
        assert self.reach(game, plate, 3) == {bear}

    def test_equip_commander_reaches_only_the_commander(self, builder):
        game, plate, _ = self.position(builder)
        cast(game, "sheoldred_the_apocalypse")
        general = only_oid(game, "sheoldred_the_apocalypse", 0)
        assert self.reach(game, plate, 2) == {general}

    def test_the_equipped_commander_is_bigger_and_protected_from_the_other_four(self, builder):
        game, plate, _ = self.position(builder)
        cast(game, "sheoldred_the_apocalypse")
        general = only_oid(game, "sheoldred_the_apocalypse", 0)
        activate(game, plate, 2, targets=(TargetRef.obj(general),))
        assert game.state.objects[plate].attached_to == general
        assert pt(game, general) == (7, 8)
        assert protection_from(game.state, general) == frozenset("WURG")

    def test_equip_five_onto_a_bear(self, builder):
        """The identity is the Plate controller's commander's, whoever wears it."""
        game, plate, bear = self.position(builder)
        activate(game, plate, 3, targets=(TargetRef.obj(bear),))
        assert game.state.objects[plate].attached_to == bear
        assert pt(game, bear) == (5, 5)
        assert protection_from(game.state, bear) == frozenset("WURG")


class TestCryptGhast:
    """"Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each opponent
    loses 1 life and you gain that much life.)" / "Whenever you tap a Swamp for mana,
    add an additional {B}." """

    def test_a_swamp_taps_for_two_black_and_a_plains_for_one_white(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["crypt_ghast", "swamp"])).build()
        pool = game.state.players[0].mana_pool
        activate_mana_ability(game.state, only_oid(game, "swamp", 0), 0, 0)
        assert pool.to_dict() == {"B": 2}
        activate_mana_ability(game.state, only_oid(game, "plains", 0), 0, 0)
        assert pool.to_dict() == {"B": 2, "W": 1}

    def test_two_swamps_and_a_plains_cast_gray_merchant(self, builder):
        """Five mana, four of it black, off three lands."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["crypt_ghast", "swamp", "swamp"])
            .hand(0, ["gray_merchant_of_asphodel"])
        ).build()
        assert castable(game, "gray_merchant_of_asphodel")

    def test_without_it_they_do_not(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["swamp", "swamp"]).hand(0, ["gray_merchant_of_asphodel"])
        ).build()
        assert castable(game, ANCHOR), "stopped at my priority"
        assert not castable(game, "gray_merchant_of_asphodel")

    def test_extort_asks_once_per_spell_and_drains_each_opponent(self, builder):
        game = anchored(
            builder(players=3)
            .battlefield(0, ["crypt_ghast", "swamp", "swamp"])
            .hand(0, [BLACK_BEAR])
        ).build()
        wait_to_cast(game, BLACK_BEAR, 0)
        game.apply(cast_line(game, BLACK_BEAR))
        seen = resolve_answering(game, {DecisionKind.MAY: yes})
        assert seen.count(DecisionKind.MAY) == 1
        assert lives(game) == [START + 2, START - 1, START - 1]

    def test_declining_extort_costs_nobody(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["crypt_ghast", "swamp", "swamp"])
            .hand(0, [BLACK_BEAR])
        ).build()
        wait_to_cast(game, BLACK_BEAR, 0)
        game.apply(cast_line(game, BLACK_BEAR))
        assert DecisionKind.MAY in resolve_answering(game)
        assert lives(game) == [START, START]


class TestElderBrain:
    """"Menace" / "Whenever this creature attacks a player, exile all cards from that
    player's hand, then they draw that many cards. You may play lands and cast spells
    from among the exiled cards for as long as they remain exiled. If you cast a
    spell this way, you may spend mana as though it were mana of any color to cast
    it." """

    def attack(self, builder):
        """Elder Brain swings at a hand of Bolt, Island and the instant."""
        game = anchored(
            builder(players=2).battlefield(0, ["elder_brain"]).hand(1, [BOLT, "island"])
        ).build()
        brain = only_oid(game, "elder_brain", 0)
        theirs = list(game.state.players[1].hand)
        pass_until(
            game,
            lambda g: (
                g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
            ),
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == brain
            )
        )
        before = libraries(game)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        settle_to_priority(game)
        return game, theirs, before

    def test_the_attack_exiles_their_hand_and_they_draw_that_many(self, builder):
        game, theirs, before = self.attack(builder)
        assert set(theirs) <= set(game.state.players[1].exile)
        assert drawn_since(before, game) == [0, 3]
        assert hand(game, 1) == 3

    def test_their_red_bolt_is_mine_to_cast_off_a_plains(self, builder):
        game, _, _ = self.attack(builder)
        wait_to_cast(game, BOLT, 0)
        bolt = cast(game, BOLT, targets=(TargetRef.player(1),))
        to_step(game, Step.POSTCOMBAT_MAIN, 0)
        assert bolt in game.state.players[1].graveyard, "back to its owner's graveyard"
        assert game.state.players[1].life == START - 3 - 6, "the Bolt and the swing"

    def test_their_land_is_mine_to_play_after_combat(self, builder):
        game, _, _ = self.attack(builder)
        to_step(game, Step.POSTCOMBAT_MAIN, 0)
        island = next(
            o for o in game.state.players[1].exile if game.state.objects[o].def_id == "island"
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.PLAY_LAND and a.source == island
            )
        )
        assert game.state.objects[island].zone is Zone.BATTLEFIELD
        assert game.state.objects[island].controller == 0

    def test_the_owner_cannot_play_them(self, builder):
        """"**You** may play": the permission is the attacker's, not the owner's."""
        game, theirs, _ = self.attack(builder)
        pass_until(
            game,
            lambda g: (
                g.state.active_player == 1 and g.pending() is not None and g.pending().player == 1
            ),
        )
        assert not any(a.source in theirs for a in game.legal_actions())


class TestErebosGodOfTheDead:
    """"Indestructible" / "As long as your devotion to black is less than five, Erebos
    isn't a creature." / "Your opponents can't gain life." / "{1}{B}, Pay 2 life:
    Draw a card." """

    def test_an_opponent_cannot_gain_life(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["erebos_god_of_the_dead"]).active(1)
        ).build()
        cast(game, ANCHOR, pid=1)
        assert lives(game) == [START, START]

    def test_you_can(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["erebos_god_of_the_dead"])).build()
        cast(game, ANCHOR)
        assert lives(game) == [START + 1, START]

    def test_at_devotion_four_it_is_not_a_creature(self, builder):
        """Erebos, Gray Merchant and Crypt Ghast: four."""
        game = anchored(
            builder(players=2).battlefield(
                0, ["erebos_god_of_the_dead", "gray_merchant_of_asphodel", "crypt_ghast"]
            )
        ).build()
        erebos = only_oid(game, "erebos_god_of_the_dead", 0)
        assert "Creature" not in chars(game.state, erebos).types

    def test_at_devotion_five_it_is_a_five_seven(self, builder):
        game = anchored(
            builder(players=2).battlefield(
                0,
                ["erebos_god_of_the_dead", "gray_merchant_of_asphodel", "crypt_ghast", BLACK_BEAR],
            )
        ).build()
        erebos = only_oid(game, "erebos_god_of_the_dead", 0)
        assert "Creature" in chars(game.state, erebos).types
        assert pt(game, erebos) == (5, 7)

    def test_an_opponent_s_black_permanents_are_not_my_devotion(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["erebos_god_of_the_dead"])
            .battlefield(1, ["gray_merchant_of_asphodel", "crypt_ghast", BLACK_BEAR])
        ).build()
        erebos = only_oid(game, "erebos_god_of_the_dead", 0)
        assert "Creature" not in chars(game.state, erebos).types

    def test_the_activation_draws_for_two_life(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["erebos_god_of_the_dead", "swamp", "swamp"])
        ).build()
        erebos = only_oid(game, "erebos_god_of_the_dead", 0)
        before = libraries(game)
        activate(game, erebos, activations(game, erebos)[0].ability_index)
        assert drawn_since(before, game) == [1, 0]
        assert lives(game) == [START - 2, START]


class TestGrayMerchantOfAsphodel:
    """"When this creature enters, each opponent loses X life, where X is your
    devotion to black. You gain life equal to the life lost this way." """

    def test_two_opponents_lose_three_each_and_you_gain_six(self, builder):
        """Its own {B}{B} and a Cabal Evangel's {B}; the opponents' Evangels are not
        my devotion."""
        game = anchored(
            builder(players=3)
            .battlefield(0, ["swamp"] * 5 + [BLACK_BEAR])
            .hand(0, ["gray_merchant_of_asphodel"])
            .battlefield(1, [BLACK_BEAR])
            .battlefield(2, [BLACK_BEAR])
        ).build()
        cast(game, "gray_merchant_of_asphodel")
        assert lives(game) == [START + 6, START - 3, START - 3]

    def test_alone_it_is_two(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["swamp"] * 5).hand(0, ["gray_merchant_of_asphodel"])
        ).build()
        cast(game, "gray_merchant_of_asphodel")
        assert lives(game) == [START + 2, START - 2]

    def test_under_an_opponent_s_erebos_the_drain_lands_and_the_gain_does_not(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp"] * 5)
            .hand(0, ["gray_merchant_of_asphodel"])
            .battlefield(1, ["erebos_god_of_the_dead"])
        ).build()
        cast(game, "gray_merchant_of_asphodel")
        assert lives(game) == [START, START - 2]


class TestKrrikSonOfYawgmoth:
    """"Lifelink" / "For each {B} in a cost, you may pay 2 life rather than pay that
    mana." / "Whenever you cast a black spell, put a +1/+1 counter on K'rrik." """

    def position(self, builder, lands, spell):
        return anchored(
            builder(players=2)
            .battlefield(0, ["k_rrik_son_of_yawgmoth", *lands])
            .hand(0, [spell])
        ).build()

    def test_a_black_creature_off_a_plains_and_two_life_grows_krrik(self, builder):
        game = self.position(builder, ["plains"], BLACK_BEAR)
        krrik = only_oid(game, "k_rrik_son_of_yawgmoth", 0)
        cast(game, BLACK_BEAR, phyrexian=1)
        assert count_on_battlefield(game, BLACK_BEAR, 0) == 1
        assert game.state.players[0].life == START - 2
        assert game.state.objects[krrik].counters.get("+1/+1") == 1
        assert pt(game, krrik) == (3, 3)

    def test_the_mana_line_is_still_offered(self, builder):
        game = self.position(builder, ["swamp", "swamp"], BLACK_BEAR)
        lines = {
            a.phyrexian
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BLACK_BEAR
        }
        assert {0, 1} <= lines

    def test_a_green_spell_adds_no_counter(self, builder):
        """"A **black** spell"."""
        game = self.position(builder, ["forest", "forest"], BEAR)
        krrik = only_oid(game, "k_rrik_son_of_yawgmoth", 0)
        cast(game, BEAR)
        assert count_on_battlefield(game, BEAR, 0) == 1
        assert not game.state.objects[krrik].counters.get("+1/+1")
        assert game.state.players[0].life == START

    def test_an_opponent_s_black_spell_adds_no_counter(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["k_rrik_son_of_yawgmoth"])
            .battlefield(1, ["swamp", "swamp"])
            .hand(1, [BLACK_BEAR])
            .active(1)
        ).build()
        krrik = only_oid(game, "k_rrik_son_of_yawgmoth", 0)
        cast(game, BLACK_BEAR, pid=1)
        assert count_on_battlefield(game, BLACK_BEAR, 1) == 1
        assert not game.state.objects[krrik].counters.get("+1/+1")

    def test_greed_is_paid_in_life_alone(self, builder):
        """"Any cost": Greed's {B} is two more life, with no black source at all."""
        game = anchored(
            builder(players=2).battlefield(0, ["k_rrik_son_of_yawgmoth", "greed"])
        ).build()
        before = libraries(game)
        activate(game, only_oid(game, "greed", 0), 0)
        assert drawn_since(before, game) == [1, 0]
        assert game.state.players[0].life == START - 4


class TestNotDeadAfterAll:
    """"Until end of turn, target creature you control gains 'When this creature dies,
    return it to the battlefield tapped under its owner's control, then create a
    Wicked Role token attached to it.'" (The Role: "Enchanted creature gets +1/+1.
    When this token is put into a graveyard, each opponent loses 1 life.") """

    def position(self, builder, bolts: int = 1):
        return anchored(
            builder(players=2)
            .battlefield(0, ["swamp", *["mountain"] * bolts, BEAR])
            .hand(0, ["not_dead_after_all", *[BOLT] * bolts])
        ).build()

    def bolt_the_bear(self, game) -> None:
        cast(game, BOLT, targets=(TargetRef.obj(only_oid(game, BEAR, 0)),))

    def test_it_returns_tapped_wearing_a_wicked_role(self, builder):
        game = self.position(builder)
        cast(game, "not_dead_after_all", targets=(TargetRef.obj(only_oid(game, BEAR, 0)),))
        self.bolt_the_bear(game)
        back = only_oid(game, BEAR, 0)
        assert game.state.objects[back].tapped
        role = only_oid(game, "wicked_role", 0)
        assert game.state.objects[role].attached_to == back
        assert pt(game, back) == (3, 3)
        assert lives(game) == [START, START]

    def test_killed_again_it_stays_dead_and_the_role_drains(self, builder):
        """The grant was the old object's; the Role's own trigger is what remains."""
        game = self.position(builder, bolts=2)
        cast(game, "not_dead_after_all", targets=(TargetRef.obj(only_oid(game, BEAR, 0)),))
        self.bolt_the_bear(game)
        self.bolt_the_bear(game)
        assert count_on_battlefield(game, BEAR) == 0
        assert count_on_battlefield(game, "wicked_role") == 0
        assert lives(game) == [START, START - 1]

    def test_an_opponent_s_creature_is_not_a_target(self, builder):
        """"Target creature **you control**"."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", BLACK_BEAR])
            .hand(0, ["not_dead_after_all"])
            .battlefield(1, [BEAR])
        ).build()
        offered = {
            game.state.objects[t.id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "not_dead_after_all"
            for t in a.targets
        }
        assert offered == {BLACK_BEAR}


class TestObNixilisReignited:
    """"+1: You draw a card and you lose 1 life." / "-3: Destroy target creature." /
    "-8: Target opponent gets an emblem with 'Whenever a player draws a card, you lose
    2 life.'" """

    def test_plus_one_draws_and_loses_one(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["ob_nixilis_reignited"])).build()
        ob = only_oid(game, "ob_nixilis_reignited", 0)
        before = libraries(game)
        activate(game, ob, 0)
        assert drawn_since(before, game) == [1, 0]
        assert lives(game) == [START - 1, START]
        assert game.state.objects[ob].counters["loyalty"] == 6

    def test_minus_three_destroys_a_creature(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["ob_nixilis_reignited"]).battlefield(1, [BIG])
        ).build()
        ob, big = only_oid(game, "ob_nixilis_reignited", 0), only_oid(game, BIG, 1)
        activate(game, ob, 1, targets=(TargetRef.obj(big),))
        assert game.state.objects[big].zone is Zone.GRAVEYARD
        assert game.state.objects[ob].counters["loyalty"] == 2

    def test_minus_eight_is_not_offered_at_five(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["ob_nixilis_reignited"])).build()
        assert castable(game, ANCHOR), "stopped at my priority"
        assert not activations(game, only_oid(game, "ob_nixilis_reignited", 0), 2)

    def test_the_emblem_drains_the_opponent_on_anyone_s_draw(self, builder):
        """My Divination costs them four, their own draw step two more, and me nothing."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["ob_nixilis_reignited"], counters={"loyalty": 8})
            .battlefield(0, ["island"] * 3)
            .hand(0, [DRAW_TWO])
        ).build()
        ob = only_oid(game, "ob_nixilis_reignited", 0)
        activate(game, ob, 2, targets=(TargetRef.player(1),))
        assert game.state.objects[ob].zone is Zone.GRAVEYARD
        assert len(game.state.players[1].command) == 1
        assert game.state.players[0].command == []
        cast(game, DRAW_TWO)
        assert lives(game) == [START, START - 4]
        to_step(game, Step.PRECOMBAT_MAIN, 1)
        assert lives(game) == [START, START - 6]


class TestPeerIntoTheAbyss:
    """"Target player draws cards equal to half the number of cards in their library
    and loses half their life. Round up each time." """

    def position(self, builder, *, cards: int, life: int):
        return anchored(
            builder(players=2)
            .battlefield(0, ["swamp"] * 7)
            .hand(0, ["peer_into_the_abyss"])
            .library(1, ["island"] * cards)
            .life(1, life)
        ).build()

    def test_an_odd_library_and_an_odd_life_both_round_up(self, builder):
        game = self.position(builder, cards=7, life=9)
        cast(game, "peer_into_the_abyss", targets=(TargetRef.player(1),))
        assert library(game, 1) == 3, "four of seven drawn"
        assert game.state.players[1].life == 4, "five of nine lost"
        assert game.state.players[0].life == START

    def test_even_numbers_are_exact(self, builder):
        game = self.position(builder, cards=8, life=10)
        cast(game, "peer_into_the_abyss", targets=(TargetRef.player(1),))
        assert library(game, 1) == 4
        assert game.state.players[1].life == 5


class TestTeferisPuzzleBox:
    """"At the beginning of each player's draw step, that player puts the cards in
    their hand on the bottom of their library in any order, then draws that many
    cards." """

    def position(self, builder, ending: int = 1):
        return (
            builder(players=2)
            .battlefield(0, ["teferi_s_puzzle_box", "plains"])
            .hand(0, [ANCHOR, BEAR, BEAR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR, BEAR])
            .active(ending)
            .step(Step.END_STEP)
            .build()
        )

    def test_my_draw_step_swaps_my_hand_for_as_many_new_cards(self, builder):
        """Three held and the step's card: four to the bottom, four drawn."""
        game = self.position(builder)
        mine, theirs = list(game.state.players[0].hand), list(game.state.players[1].hand)
        before = libraries(game)
        to_step(game, Step.PRECOMBAT_MAIN, 0)
        assert hand(game, 0) == 4
        assert not set(mine) & set(game.state.players[0].hand)
        assert set(mine) <= set(game.state.players[0].library[-4:]), "on the bottom"
        assert library(game, 0) == before[0] - 1
        assert game.state.players[1].hand == theirs, "only the player whose draw step it is"

    def test_the_opponent_s_draw_step_swaps_theirs(self, builder):
        game = self.position(builder, ending=0)
        mine, theirs = list(game.state.players[0].hand), list(game.state.players[1].hand)
        to_step(game, Step.PRECOMBAT_MAIN, 1)
        assert hand(game, 1) == 3
        assert not set(theirs) & set(game.state.players[1].hand)
        assert game.state.players[0].hand == mine


class TestWellOfLostDreams:
    """"Whenever you gain life, you may pay {X}, where X is less than or equal to the
    amount of life you gained. If you do, draw X cards." """

    def gain(self, builder, *mine):
        """Cast the instant over the Well and ``mine``, and say yes."""
        game = anchored(builder(players=2).battlefield(0, ["well_of_lost_dreams", *mine])).build()
        wait_to_cast(game, ANCHOR, 0)
        game.apply(cast_line(game, ANCHOR))
        decide(game, DecisionKind.MAY, lambda a: a.kind is ActionKind.YES)
        return game

    def test_x_runs_to_the_life_gained_not_the_mana_open(self, builder):
        game = self.gain(builder, "island", "island", "island")
        p = game.pending()
        assert p.kind is DecisionKind.CHOOSE_X
        assert [o.value for o in p.options] == [0, 1]

    def test_paying_one_draws_one(self, builder):
        game = self.gain(builder, "island", "island", "island")
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == 1)
        )
        settle_to_priority(game)
        assert FILLER - library(game, 0) == 1
        assert game.state.players[0].life == START + 1
        islands = [o for o in game.state.battlefield_objects(0) if o.def_id == "island"]
        assert sum(o.tapped for o in islands) == 1

    def test_a_gain_doubled_by_the_archive_lets_x_reach_two(self, builder):
        """"The amount of life you gained" is what was gained, after the doubling."""
        game = self.gain(builder, "alhammarret_s_archive", "island", "island", "island")
        assert [o.value for o in game.pending().options] == [0, 1, 2]

    def test_an_opponent_s_gain_asks_me_nothing(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["well_of_lost_dreams", "island", "island"]).active(1)
        ).build()
        wait_to_cast(game, ANCHOR, 1)
        game.apply(cast_line(game, ANCHOR))
        assert DecisionKind.MAY not in resolve_answering(game)
        assert lives(game) == [START, START + 1]


class TestWitchOfTheMoors:
    """"Deathtouch" / "At the beginning of your end step, if you gained life this
    turn, each opponent sacrifices a creature of their choice and you return up to
    one target creature card from your graveyard to your hand." """

    def position(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["witch_of_the_moors"])
            .graveyard(0, [BEAR])
            .battlefield(1, [BIG])
        ).build()
        return game, game.state.players[0].graveyard[0]

    def test_after_a_gain_they_sacrifice_and_i_get_a_card_back(self, builder):
        game, bear = self.position(builder)
        cast(game, ANCHOR)
        choose_target(game, TargetRef.obj(bear))
        settle_to_priority(game)
        assert count_on_battlefield(game, BIG, 1) == 0
        assert bear in game.state.players[0].hand
        assert count_on_battlefield(game, "witch_of_the_moors", 0) == 1, "not me"

    def test_without_a_gain_nothing_happens(self, builder):
        game, bear = self.position(builder)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert count_on_battlefield(game, BIG, 1) == 1
        assert bear in game.state.players[0].graveyard

    def test_an_opponent_s_gain_is_not_mine(self, builder):
        """"If **you** gained life": they cast the instant on my turn."""
        game, bear = self.position(builder)
        cast(game, ANCHOR, pid=1)
        assert lives(game) == [START, START + 1]
        pass_until(game, lambda g: g.state.active_player == 1)
        assert count_on_battlefield(game, BIG, 1) == 1
        assert bear in game.state.players[0].graveyard
