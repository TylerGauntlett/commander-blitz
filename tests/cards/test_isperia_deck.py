"""The Isperia, Supreme Judge deck: its riskiest cards, doing what they print.

Every card in `isperia.cards.json` cleared the six authoring gates, and almost
every one was measured by gate 5 at "it is on the battlefield". That is the
gate's documented limit, not the cards': the sandbox casts a card once and stops.
It never declares an attack, never reaches another player's draw step, never
activates an ability and never gains life after the card is down. This deck is
a pile of flyers whose whole value lives in exactly those places:

- **Isperia** and **Skyknight Vanguard** are attack triggers -- one on the
  defending side, one on the attacking side.
- **Consecrated Sphinx** fires on an *opponent's* draw.
- **Archangel of Thune** fires on life gain.
- **Lyra Dawnbringer** and **Empyrean Eagle** are tribal/keyword anthems whose
  "other" and filter are easy to get wrong in either direction.
- **Sphinx of Magosi** is an activated ability.
- **Sunblast Angel** and **Sun Titan** are enters triggers whose filters (tapped
  creatures; mana value 3 or less, a permanent card) decide everything.
- **Emeria Angel** is landfall, which the gate never plays a land into.

Each class quotes the printed text and asserts the board, with a near miss
alongside: the creature that should *not* grow, the player who should *not*
draw, the card that should *not* come back.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import (
    _default_answer,
    action_for_card,
    advance_to_step,
    find_action,
    oids_of,
    only_oid,
    pass_until,
)

ISPERIA = "isperia_supreme_judge"
THUNE = "archangel_of_thune"
SPHINX = "consecrated_sphinx"
LYRA = "lyra_dawnbringer"
EAGLE = "empyrean_eagle"
VANGUARD = "skyknight_vanguard"
MAGOSI = "sphinx_of_magosi"
EMERIA = "emeria_angel"
SUNBLAST = "sunblast_angel"
TITAN = "sun_titan"
SERRA = "serra_angel"  # a vanilla 4/4 flying, vigilance Angel
DRAKE = "wind_drake"  # a vanilla 2/2 flying Drake
BIRD = "bird_1_1_w_flying"
SOLDIER = "soldier_1_1_w"
BEAR = "t_bear"  # {1}{G} 2/2, mana value 2, no keywords
# A castable instant in each seat's hand: with no play available to anybody the
# engine's auto-pass runs whole turns inside one `apply` and overshoots the step
# under test. It is also Archangel of Thune's life gain: "You gain 1 life."
ANCHOR = "t_plain_instant"


def answer(game, *, yes: bool = True, limit: int = 200) -> None:
    """Let the stack empty, saying ``yes`` to every `MAY`."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def declare(game, pid: int, attackers: list[int], defender: int) -> None:
    """``pid`` attacks ``defender`` (a player) with each of ``attackers``."""
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        and g.pending().player == pid,
    )
    for oid in attackers:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and a.targets[0].kind == "player"
                and a.targets[0].id == defender
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def cast(game, card_id: str) -> int:
    """Cast ``card_id`` from player 0's hand and let it resolve, saying yes to
    every `MAY`. Returns its oid."""
    action = action_for_card(game, ActionKind.CAST, card_id)
    game.apply(action)
    answer(game)
    return action.source


def hand_size(game, pid: int) -> int:
    return len(game.state.players[pid].hand)


def pt(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return (c.power, c.toughness)


def keywords(game, oid: int) -> set[str]:
    return {str(k) for k in chars(game.state, oid).keywords}


class TestIsperiaSupremeJudge:
    """"Flying. Whenever a creature attacks you or a planeswalker you control,
    you may draw a card." """

    def position(self, builder, *, players: int = 2, bears: int = 1, isperia_seat: int = 0):
        b = builder(players=players)
        for pid in range(players):
            b.battlefield(pid, ["plains"]).hand(pid, [ANCHOR]).library(pid, ["island"] * 20)
        b.battlefield(isperia_seat, [ISPERIA])
        b.battlefield(1, [BEAR] * bears)
        return b.active(1).step(Step.PRECOMBAT_MAIN).build()

    def test_one_attacker_draws_you_one(self, builder):
        game = self.position(builder)
        before = hand_size(game, 0)
        declare(game, 1, oids_of(game, BEAR, 1), defender=0)
        answer(game)
        assert hand_size(game, 0) == before + 1
        assert len(game.state.players[0].library) == 19

    def test_each_attacker_is_its_own_trigger(self, builder):
        game = self.position(builder, bears=2)
        before = hand_size(game, 0)
        declare(game, 1, oids_of(game, BEAR, 1), defender=0)
        answer(game)
        assert hand_size(game, 0) == before + 2

    def test_the_draw_is_a_may(self, builder):
        game = self.position(builder)
        before = hand_size(game, 0)
        declare(game, 1, oids_of(game, BEAR, 1), defender=0)
        answer(game, yes=False)
        assert hand_size(game, 0) == before
        assert len(game.state.players[0].library) == 20

    def test_an_attack_on_someone_else_draws_nothing(self, builder):
        """Three players: seat 1 swings at seat 2, and Isperia's controller is
        not the one being attacked."""
        game = self.position(builder, players=3)
        before = hand_size(game, 0)
        declare(game, 1, oids_of(game, BEAR, 1), defender=2)
        answer(game)
        assert hand_size(game, 0) == before
        assert len(game.state.players[0].library) == 20
        assert len(game.state.players[2].library) == 20, "the defender owns no Isperia"


class TestSkyknightVanguard:
    """"Flying. Whenever this creature attacks, create a 1/1 white Soldier
    creature token that's tapped and attacking." """

    def attack(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", VANGUARD])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        declare(game, 0, [only_oid(game, VANGUARD, 0)], defender=1)
        answer(game)
        return game

    def test_the_soldier_enters_tapped_and_attacking(self, builder):
        game = self.attack(builder)
        soldier = only_oid(game, SOLDIER, 0)
        assert game.state.objects[soldier].tapped
        assert soldier in game.state.combat.attackers
        assert game.state.objects[soldier].is_token
        assert pt(game, soldier) == (1, 1)
        assert "flying" not in keywords(game, soldier), "the Soldier is not a flyer"

    def test_both_connect(self, builder):
        """3 from the Vanguard and 1 from the Soldier it brought along."""
        game = self.attack(builder)
        advance_to_step(game, Step.END_OF_COMBAT)
        assert game.state.players[1].life == 40 - 4

    def test_no_attack_no_soldier(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", VANGUARD])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        declare(game, 0, [], defender=1)
        answer(game)
        assert oids_of(game, SOLDIER) == []


class TestConsecratedSphinx:
    """"Flying. Whenever an opponent draws a card, you may draw two cards." """

    def position(self, builder, *, active: int):
        return (
            builder(players=2)
            .battlefield(0, ["plains", SPHINX])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .active(active)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(4)
            .build()
        )

    def test_an_opponents_draw_step_draws_you_two(self, builder):
        game = self.position(builder, active=0)
        pass_until(game, lambda g: g.state.step is Step.DRAW and g.state.active_player == 1)
        answer(game)
        assert len(game.state.players[1].library) == 19
        assert len(game.state.players[0].library) == 18

    def test_declining_draws_nothing(self, builder):
        game = self.position(builder, active=0)
        pass_until(game, lambda g: g.state.step is Step.DRAW and g.state.active_player == 1)
        answer(game, yes=False)
        assert len(game.state.players[0].library) == 20

    def test_your_own_draw_does_not_trigger_it(self, builder):
        """Nor do the two it draws you -- or it would loop on itself."""
        game = self.position(builder, active=1)
        pass_until(game, lambda g: g.state.step is Step.DRAW and g.state.active_player == 0)
        answer(game)
        assert len(game.state.players[0].library) == 19
        assert not game.state.stack


class TestArchangelOfThune:
    """"Flying, lifelink. Whenever you gain life, put a +1/+1 counter on each
    creature you control." """

    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["plains", THUNE, BEAR])
            .battlefield(1, ["plains", BEAR])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_gaining_life_grows_each_of_your_creatures(self, builder):
        game = self.position(builder)
        cast(game, ANCHOR)
        thune, mine = only_oid(game, THUNE, 0), only_oid(game, BEAR, 0)
        assert game.state.players[0].life == 41
        assert game.state.objects[thune].counters == {"+1/+1": 1}
        assert game.state.objects[mine].counters == {"+1/+1": 1}
        assert pt(game, thune) == (4, 5)
        assert pt(game, mine) == (3, 3)

    def test_an_opponents_creature_gets_nothing(self, builder):
        game = self.position(builder)
        cast(game, ANCHOR)
        theirs = only_oid(game, BEAR, 1)
        assert game.state.objects[theirs].counters == {}
        assert pt(game, theirs) == (2, 2)

    def test_its_own_lifelink_is_life_gained(self, builder):
        """Thune connects for 3, its controller gains 3 -- one life-gain event,
        so one counter, not three."""
        game = self.position(builder)
        thune = only_oid(game, THUNE, 0)
        declare(game, 0, [thune], defender=1)
        advance_to_step(game, Step.END_OF_COMBAT)
        answer(game)
        assert game.state.players[1].life == 37
        assert game.state.players[0].life == 43
        assert game.state.objects[thune].counters == {"+1/+1": 1}

    def test_an_opponents_life_gain_does_not_trigger_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", THUNE])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, ANCHOR))
        answer(game)
        assert game.state.players[1].life == 41
        assert game.state.objects[only_oid(game, THUNE, 0)].counters == {}


class TestLyraDawnbringer:
    """"Flying, first strike, lifelink. Other Angels you control get +1/+1 and
    have lifelink." """

    def position(self, builder, *, theirs=()):
        return (
            builder(players=2)
            .battlefield(0, ["plains", LYRA, SERRA, DRAKE])
            .battlefield(1, ["plains", *theirs])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_another_angel_gets_plus_one_and_lifelink(self, builder):
        game = self.position(builder)
        serra = only_oid(game, SERRA, 0)
        assert pt(game, serra) == (5, 5)
        assert "lifelink" in keywords(game, serra)

    def test_not_herself_not_a_non_angel_not_an_opponents_angel(self, builder):
        game = self.position(builder, theirs=[SERRA])
        assert pt(game, only_oid(game, LYRA, 0)) == (5, 5)
        drake = only_oid(game, DRAKE, 0)
        assert pt(game, drake) == (2, 2)
        assert "lifelink" not in keywords(game, drake)
        theirs = only_oid(game, SERRA, 1)
        assert pt(game, theirs) == (4, 4)
        assert "lifelink" not in keywords(game, theirs)

    def test_the_granted_lifelink_gains_life_in_combat(self, builder):
        game = self.position(builder)
        declare(game, 0, [only_oid(game, SERRA, 0)], defender=1)
        advance_to_step(game, Step.END_OF_COMBAT)
        assert game.state.players[1].life == 35
        assert game.state.players[0].life == 45


class TestEmpyreanEagle:
    """"Flying. Other creatures you control with flying get +1/+1." """

    def test_other_flyers_you_control_get_plus_one(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [EAGLE, DRAKE, BEAR])
            .battlefield(1, [DRAKE])
            .build(advance=False)
        )
        assert pt(game, only_oid(game, DRAKE, 0)) == (3, 3)
        assert pt(game, only_oid(game, EAGLE, 0)) == (2, 2), "other: not itself"
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2), "no flying, no bonus"
        assert pt(game, only_oid(game, DRAKE, 1)) == (2, 2), "you control: not theirs"

    def test_two_eagles_pump_each_other(self, builder):
        game = builder(players=2).battlefield(0, [EAGLE, EAGLE, DRAKE]).build(advance=False)
        assert [pt(game, o) for o in oids_of(game, EAGLE, 0)] == [(3, 3), (3, 3)]
        assert pt(game, only_oid(game, DRAKE, 0)) == (4, 4)


class TestSphinxOfMagosi:
    """"Flying. {2}{U}: Draw a card, then put a +1/+1 counter on this
    creature." """

    def test_each_activation_draws_and_grows(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [MAGOSI] + ["island"] * 6)
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .library(0, ["plains"] * 10)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        magosi = only_oid(game, MAGOSI, 0)
        for times in (1, 2):
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.ACTIVATE and a.source == magosi
                )
            )
            answer(game)
            assert len(game.state.players[0].library) == 10 - times
            assert game.state.objects[magosi].counters == {"+1/+1": times}
        assert pt(game, magosi) == (8, 8)
        assert not any(
            a.kind is ActionKind.ACTIVATE and a.source == magosi for a in game.legal_actions()
        ), "six Islands pay for two activations, not a third"


class TestEmeriaAngel:
    """"Flying. Landfall -- Whenever a land you control enters, you may create
    a 1/1 white Bird creature token with flying." """

    def test_your_land_drop_makes_a_flying_bird(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [EMERIA])
            .battlefield(1, ["plains"])
            .hand(0, ["plains"])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "plains"))
        answer(game)
        bird = only_oid(game, BIRD, 0)
        assert pt(game, bird) == (1, 1)
        assert "flying" in keywords(game, bird)

    def test_an_opponents_land_makes_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", EMERIA])
            .hand(0, [ANCHOR])
            .hand(1, ["plains"])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "plains"))
        answer(game)
        assert oids_of(game, BIRD) == []


class TestSunblastAngel:
    """"Flying. When this creature enters, destroy all tapped creatures." """

    def test_tapped_creatures_die_untapped_ones_live(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .battlefield(0, [BEAR], tapped=True)
            .battlefield(1, [BEAR], tapped=True)
            .battlefield(1, [DRAKE])
            .hand(0, [SUNBLAST])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bears = oids_of(game, BEAR)
        drake = only_oid(game, DRAKE, 1)
        angel = cast(game, SUNBLAST)
        assert all(game.state.objects[b].zone is Zone.GRAVEYARD for b in bears), (
            "every tapped creature -- its controller's own included"
        )
        assert game.state.objects[drake].zone is Zone.BATTLEFIELD
        assert game.state.objects[angel].zone is Zone.BATTLEFIELD, "it enters untapped"
        assert len(oids_of(game, "plains", 0)) == 6, "tapped lands are not creatures"


class TestSunTitan:
    """"Vigilance. Whenever this creature enters or attacks, you may return
    target permanent card with mana value 3 or less from your graveyard to the
    battlefield." -- the enters half."""

    def test_entering_returns_a_small_permanent_card(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .graveyard(0, [BEAR, SERRA, ANCHOR])
            .hand(0, [TITAN])
            .hand(1, [ANCHOR])
            .battlefield(1, ["plains"])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear, serra, rite = game.state.players[0].graveyard
        cast(game, TITAN)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[serra].zone is Zone.GRAVEYARD, "mana value 5"
        assert game.state.objects[rite].zone is Zone.GRAVEYARD, "an instant is not a permanent card"

    def test_an_opponents_graveyard_is_not_yours(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6)
            .graveyard(1, [BEAR])
            .hand(0, [TITAN])
            .hand(1, [ANCHOR])
            .battlefield(1, ["plains"])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        [theirs] = game.state.players[1].graveyard
        cast(game, TITAN)
        assert game.state.objects[theirs].zone is Zone.GRAVEYARD
        assert oids_of(game, BEAR) == []
