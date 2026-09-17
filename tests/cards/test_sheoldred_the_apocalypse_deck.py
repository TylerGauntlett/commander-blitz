"""The Sheoldred, the Apocalypse deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 casts a card once, in one fixed sandbox, and reads the
board, and two of its documented limits bite almost every card in this deck:

- **It never activates an ability.** Greed, Temple Bell, Otherworld Atlas, the
  two utility lands, Cabal Stronghold, Ob Nixilis's minus and Vilis's pump are the
  whole point of those cards, and the harness stops before any of them.
- **A trigger that never fires cannot be asserted.** This is a draw-punisher deck:
  nearly every card triggers on somebody *drawing*, on an upkeep or a draw step, on
  a land entering, on losing life or on dying, and nothing in the sandbox does any
  of those after the card under test. The honest expectation for Underworld Dreams
  is "it is on the battlefield".

So the authoring expectations are floors, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach, plus
the near miss -- the sentence that would be true of the card mis-written.

No card in the deck list is skipped. A simple spell whose gate expectation already
proves its text still has a class, a short one, aimed where the gate did not aim.
"""

from __future__ import annotations

import pytest

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.primitives import create_token
from automtg.engine.structs import TargetRef
from tests.conftest import (
    _default_answer,
    action_for_card,
    count_on_battlefield,
    only_oid,
    pass_until,
)

# A castable instant, and it is load bearing rather than scenery. With no play
# available to anybody the engine's auto-pass runs whole turns inside one
# `apply`, so every seat that must be seen stopping holds one of these.
ANCHOR = "t_plain_instant"  # {W}, gain 1 life
DRAW_TWO = "divination"  # {2}{U} sorcery, "Draw two cards."
BEAR = "t_bear"  # a vanilla green 2/2, {1}{G}
BIG = "t_five_five"  # a vanilla green 5/5
BLACK_BEAR = "cabal_evangel"  # a vanilla black 2/2, {1}{B}
BOLT = "lightning_bolt"  # {R}, 3 damage to any target

START = 40


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def settle(game) -> None:
    """Pass until the stack is empty and nobody is mid-resolution."""
    pass_until(
        game,
        lambda g: (
            not g.state.stack and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)
        ),
    )


def wait_to_cast(game, card_id: str, pid: int) -> None:
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().player == pid and castable(g, card_id),
    )


def cast_line(game, card_id: str, **match):
    return next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and all(getattr(a, k) == v for k, v in match.items())
    )


def cast(game, card_id: str, pid: int = 0, **match) -> int:
    """Cast ``card_id`` from ``pid``'s hand and let it resolve. Returns its oid."""
    wait_to_cast(game, card_id, pid)
    action = cast_line(game, card_id, **match)
    game.apply(action)
    settle(game)
    return action.source


def castable(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


def activations(game, oid: int, index: int | None = None) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (index is None or a.ability_index == index)
    ]


def activate(game, oid: int, index: int, **match) -> None:
    action = next(
        a
        for a in activations(game, oid, index)
        if all(getattr(a, k) == v for k, v in match.items())
    )
    game.apply(action)
    settle(game)


def decide(game, kind: DecisionKind, pick) -> None:
    """Stop at the next ``kind`` decision and answer it with the action ``pick`` likes."""
    pass_until(game, lambda g: g.pending() is not None and g.pending().kind is kind)
    game.apply(next(a for a in game.legal_actions() if pick(a)))


def choose_mode(game, mode: int) -> None:
    decide(
        game, DecisionKind.CHOOSE_MODE, lambda a: a.kind is ActionKind.CHOOSE and a.choice == mode
    )


def choose_target(game, ref: TargetRef) -> None:
    decide(
        game,
        DecisionKind.CHOOSE_OBJECTS,
        lambda a: a.kind is ActionKind.CHOOSE and a.targets and a.targets[0] == ref,
    )


def library(game, pid: int) -> int:
    return len(game.state.players[pid].library)


def libraries(game) -> list[int]:
    return [library(game, p.pid) for p in game.state.players]


def lives(game) -> list[int]:
    return [p.life for p in game.state.players]


def hand(game, pid: int) -> int:
    return len(game.state.players[pid].hand)


def drawn_since(before: list[int], game) -> list[int]:
    return [b - a for b, a in zip(before, libraries(game), strict=True)]


def pt(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return (c.power, c.toughness)


def anchored(b):
    """Give every seat a Plains and a castable instant, so the game stops in each
    step instead of auto-passing whole turns (and their draw steps) away."""
    for player in b.state.players:
        b = b.battlefield(player.pid, ["plains"]).hand(player.pid, [ANCHOR])
    return b


def to_step(game, step: Step, active: int) -> None:
    pass_until(game, lambda g: g.state.step is step and g.state.active_player == active)


def between_turns(builder, *, players: int = 2, ending: int = 1, boards=None, lands="plains"):
    """Stop in ``ending``'s end step, every seat holding a castable instant.

    ``boards`` maps a seat to extra permanents. The next turn is the seat after
    ``ending``; everything its untap, upkeep and draw steps do is then observable
    from here.
    """
    boards = boards or {}
    b = builder(players=players)
    for pid in range(players):
        b = b.battlefield(pid, [lands, *boards.get(pid, ())]).hand(pid, [ANCHOR])
    return b.active(ending).step(Step.END_STEP).build()


def through_draw_step(game, active: int) -> list[int]:
    """How many cards each seat draws from ``active``'s untap to its main phase."""
    before = libraries(game)
    to_step(game, Step.PRECOMBAT_MAIN, active)
    return drawn_since(before, game)


def through_upkeep_and_draw(game, active: int):
    """Libraries drawn and life changed from here to ``active``'s main phase."""
    before_libs, before_life = libraries(game), lives(game)
    to_step(game, Step.PRECOMBAT_MAIN, active)
    return (
        drawn_since(before_libs, game),
        [a - b for b, a in zip(before_life, lives(game), strict=True)],
    )


def opponent_draws_two(builder, watcher: str, *, players: int = 2, mine=()):
    """Player 1's main phase, holding Divination; ``watcher`` on player 0's side."""
    b = (
        builder(players=players)
        .battlefield(0, [watcher, "plains", *mine])
        .hand(0, [ANCHOR])
        .battlefield(1, ["island"] * 3 + ["plains"])
        .hand(1, [DRAW_TWO, ANCHOR])
    )
    for pid in range(2, players):
        b = b.battlefield(pid, ["plains"]).hand(pid, [ANCHOR])
    game = b.active(1).build()
    cast(game, DRAW_TWO, pid=1)
    return game


def i_draw_two(builder, watcher: str, *, players: int = 2, mine=(), hand_extra=()):
    """Player 0's main phase: ``watcher`` in play, and I cast Divination."""
    game = anchored(
        builder(players=players)
        .battlefield(0, [watcher, "island", "island", "island", *mine])
        .hand(0, [DRAW_TWO, *hand_extra])
    ).build()
    cast(game, DRAW_TWO)
    return game


# ----------------------------------------------------------------------
# the commander
# ----------------------------------------------------------------------


class TestSheoldredTheApocalypse:
    """"Whenever you draw a card, you gain 2 life." / "Whenever an opponent draws a
    card, they lose 2 life." """

    def test_you_gain_two_for_each_card_you_draw(self, builder):
        game = i_draw_two(builder, "sheoldred_the_apocalypse")
        assert lives(game) == [START + 4, START]

    def test_an_opponent_loses_two_for_each_card_they_draw(self, builder):
        game = opponent_draws_two(builder, "sheoldred_the_apocalypse")
        assert game.state.players[1].life == START - 4

    def test_an_opponent_drawing_does_not_gain_you_life(self, builder):
        """The near miss: "you gain" read off the wrong draw."""
        game = opponent_draws_two(builder, "sheoldred_the_apocalypse")
        assert game.state.players[0].life == START

    def test_your_own_draw_does_not_cost_you_life(self, builder):
        game = i_draw_two(builder, "sheoldred_the_apocalypse")
        assert game.state.players[1].life == START, "nobody else drew"
        assert game.state.players[0].life > START

    def test_each_draw_step_pays_out(self, builder):
        """The turn's own card counts: my draw step gains 2, theirs costs them 2."""
        game = between_turns(builder, boards={0: ["sheoldred_the_apocalypse"]})
        _, life = through_upkeep_and_draw(game, 0)
        assert life == [2, 0]
        _, life = through_upkeep_and_draw(game, 1)
        assert life == [0, -2]


# ----------------------------------------------------------------------
# the rest of the deck
# ----------------------------------------------------------------------


class TestBloodPact:
    """"Target player draws two cards and loses 2 life." -- aimed at an opponent."""

    def test_an_opponent_draws_two_and_loses_two(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["swamp"] * 3).hand(0, ["blood_pact"])
        ).build()
        before = libraries(game)
        cast(game, "blood_pact", targets=(TargetRef.player(1),))
        assert drawn_since(before, game) == [0, 2]
        assert lives(game) == [START, START - 2]

    def test_it_is_an_instant(self, builder):
        """Cast on the opponent's turn, which the gate never tried."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp"] * 3)
            .hand(0, ["blood_pact"])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(1)
        ).build()
        cast(game, "blood_pact", targets=(TargetRef.player(1),))
        assert game.state.players[1].life == START - 2


class TestBloodgiftDemon:
    """"At the beginning of your upkeep, target player draws a card and loses 1
    life." """

    def test_at_your_upkeep_the_opponent_you_target_draws_and_loses_one(self, builder):
        game = between_turns(builder, boards={0: ["bloodgift_demon"]})
        before_libs = libraries(game)
        choose_target(game, TargetRef.player(1))
        settle(game)
        assert drawn_since(before_libs, game)[1] == 1
        assert lives(game) == [START, START - 1]

    def test_it_can_target_you(self, builder):
        game = between_turns(builder, boards={0: ["bloodgift_demon"]})
        choose_target(game, TargetRef.player(0))
        settle(game)
        assert lives(game) == [START - 1, START]

    def test_not_at_an_opponent_s_upkeep(self, builder):
        """"Your upkeep": the opponent's turn asks nobody for a target."""
        game = between_turns(builder, ending=0, boards={0: ["bloodgift_demon"]})
        seen = []
        while not (game.state.active_player == 1 and game.state.step is Step.PRECOMBAT_MAIN):
            p = game.pending()
            seen.append(p.kind)
            game.apply(_default_answer(game, p))
        assert DecisionKind.CHOOSE_OBJECTS not in seen
        assert lives(game) == [START, START]


class TestCabalStronghold:
    """"{3}, {T}: Add {B} for each basic Swamp you control." """

    def test_it_adds_black_for_each_basic_swamp_and_not_a_nonbasic_one(self, builder):
        """Three basic Swamps and a Blood Crypt: three, not four -- and the opponent's
        Swamps are not mine."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["cabal_stronghold", "swamp", "swamp", "swamp", "blood_crypt"])
            .battlefield(0, ["plains"] * 3)
            .hand(0, [ANCHOR])
            .battlefield(1, ["swamp"] * 4)
        ).build()
        stronghold = only_oid(game, "cabal_stronghold", 0)
        game.apply(activations(game, stronghold, 1)[0])
        assert game.state.players[0].mana_pool.to_dict() == {"B": 3}
        assert game.state.objects[stronghold].tapped


class TestDamnablePact:
    """"Target player draws X cards and loses X life." -- X of 3, at an opponent."""

    def test_an_opponent_draws_x_and_loses_x(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["swamp"] * 5).hand(0, ["damnable_pact"])
        ).build()
        before = libraries(game)
        wait_to_cast(game, "damnable_pact", 0)
        game.apply(cast_line(game, "damnable_pact", targets=(TargetRef.player(1),)))
        decide(game, DecisionKind.CHOOSE_X, lambda a: a.kind is ActionKind.CHOOSE and a.choice == 3)
        settle(game)
        assert drawn_since(before, game) == [0, 3]
        assert lives(game) == [START, START - 3]


class TestDarkDeal:
    """"Each player discards all the cards in their hand, then draws that many cards
    minus one." """

    def test_each_player_draws_one_fewer_than_they_discarded(self, builder):
        """Every seat also holds an instant. Me four (Dark Deal itself is on the
        stack, not in hand) draw three; them three draw two; the third seat's single
        card draws nothing -- one minus one, not one."""
        game = anchored(
            builder(players=3)
            .battlefield(0, ["swamp"] * 3)
            .hand(0, ["dark_deal", BEAR, BEAR, BEAR])
            .hand(1, [BEAR, BEAR])
        ).build()
        before = libraries(game)
        cast(game, "dark_deal")
        assert drawn_since(before, game) == [3, 2, 0]
        assert [hand(game, p) for p in range(3)] == [3, 2, 0]
        assert [len(p.graveyard) for p in game.state.players] == [5, 3, 1], "four and the spell"


class TestDecanterOfEndlessWater:
    """"You have no maximum hand size." / "{T}: Add one mana of any color." """

    @pytest.mark.parametrize("spell", [ANCHOR, BOLT, "t_dork", "feign_death"])
    def test_it_alone_pays_a_one_pip_spell_of_each_color(self, builder, spell):
        """White, red, green and black off the one artifact."""
        game = (
            builder(players=2)
            .battlefield(0, ["decanter_of_endless_water", BEAR])
            .hand(0, [spell])
            .build(advance=False)
        )
        game._advance()
        assert castable(game, spell)

    def test_you_keep_a_ten_card_hand_through_cleanup(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["decanter_of_endless_water"]).hand(0, [BEAR] * 10)
        ).build()
        pass_until(game, lambda g: g.state.active_player == 1)
        assert hand(game, 0) == 11, "ten Bears and the instant"

    def test_an_opponent_still_discards_to_seven(self, builder):
        """"**You** have no maximum hand size"."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["decanter_of_endless_water"])
            .hand(1, [BEAR] * 10)
            .active(1)
        ).build()
        pass_until(game, lambda g: g.state.active_player == 0)
        assert hand(game, 1) == 7


class TestDefile:
    """"Target creature gets -1/-1 until end of turn for each Swamp you control." """

    def test_it_counts_every_swamp_you_control_nonbasic_included(self, builder):
        """A Swamp and a Blood Crypt make -2/-2; the opponent's five Swamps do not
        count, or the 5/5 would die."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "blood_crypt", "plains"])
            .hand(0, ["defile"])
            .battlefield(1, [BIG] + ["swamp"] * 5)
        ).build()
        big = only_oid(game, BIG, 1)
        cast(game, "defile", targets=(TargetRef.obj(big),))
        assert pt(game, big) == (3, 3)

    def test_until_end_of_turn(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "swamp"])
            .hand(0, ["defile"])
            .battlefield(1, [BIG, "plains"])
            .hand(1, [ANCHOR])
        ).build()
        big = only_oid(game, BIG, 1)
        cast(game, "defile", targets=(TargetRef.obj(big),))
        assert pt(game, big) == (3, 3)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert pt(game, big) == (5, 5)


class TestDismember:
    """"({B/P} can be paid with either {B} or 2 life.)" / "Target creature gets -5/-5
    until end of turn." """

    def test_one_land_and_four_life_kill_a_five_five(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["plains"])
            .hand(0, ["dismember"])
            .battlefield(1, [BIG])
        ).build()
        big = only_oid(game, BIG, 1)
        cast(game, "dismember", phyrexian=2, targets=(TargetRef.obj(big),))
        assert game.state.objects[big].zone is Zone.GRAVEYARD
        assert game.state.players[0].life == START - 4

    def test_one_land_alone_cannot_pay_for_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"])
            .hand(0, ["dismember"])
            .battlefield(1, [BIG])
            .build(advance=False)
        )
        game._advance()
        assert {a.phyrexian for a in game.legal_actions() if a.kind is ActionKind.CAST} == {2}

    def test_it_is_minus_five_not_destroy(self, builder):
        """A 3/7 survives as a -2/2."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "swamp", "swamp"])
            .hand(0, ["dismember"])
            .battlefield(1, ["catacomb_crocodile"])
        ).build()
        croc = only_oid(game, "catacomb_crocodile", 1)
        cast(game, "dismember", phyrexian=0, targets=(TargetRef.obj(croc),))
        assert game.state.objects[croc].zone is Zone.BATTLEFIELD
        assert pt(game, croc) == (-2, 2)
        assert game.state.players[0].life == START


class TestDreadPresence:
    """"Whenever a Swamp you control enters, choose one -- You draw a card and you lose
    1 life. / This creature deals 2 damage to any target and you gain 2 life." """

    def position(self, builder, land: str = "swamp", theirs=()):
        return anchored(
            builder(players=2)
            .battlefield(0, ["dread_presence"])
            .hand(0, [land])
            .battlefield(1, list(theirs))
        ).build()

    def play(self, game, land: str = "swamp") -> None:
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, land))

    def test_the_first_mode_draws_and_loses_one(self, builder):
        game = self.position(builder)
        before = libraries(game)
        self.play(game)
        choose_mode(game, 0)
        settle(game)
        assert drawn_since(before, game) == [1, 0]
        assert lives(game) == [START - 1, START]

    def test_the_second_mode_hits_a_player_and_gains_two(self, builder):
        """"Any target" -- the opponent's face, not only a creature."""
        game = self.position(builder)
        self.play(game)
        choose_mode(game, 1)
        choose_target(game, TargetRef.player(1))
        settle(game)
        assert lives(game) == [START + 2, START - 2]

    def test_the_second_mode_kills_a_bear(self, builder):
        game = self.position(builder, theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        self.play(game)
        choose_mode(game, 1)
        choose_target(game, TargetRef.obj(bear))
        settle(game)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_a_nonbasic_swamp_counts(self, builder):
        game = self.position(builder, land="watery_grave")
        self.play(game, "watery_grave")
        seen = []
        for _ in range(20):
            p = game.pending()
            if p.kind is DecisionKind.PRIORITY and not game.state.stack:
                break
            seen.append(p.kind)
            if p.kind is DecisionKind.CHOOSE_MODE:
                game.apply(next(a for a in game.legal_actions() if a.choice == 0))
            else:
                game.apply(_default_answer(game, p))
        assert DecisionKind.CHOOSE_MODE in seen

    def test_a_plains_does_nothing(self, builder):
        """"Whenever a **Swamp** you control enters"."""
        game = self.position(builder, land="plains")
        before = libraries(game)
        self.play(game, "plains")
        assert game.pending().kind is not DecisionKind.CHOOSE_MODE
        settle(game)
        assert drawn_since(before, game) == [0, 0]
        assert lives(game) == [START, START]

    def test_an_opponent_s_swamp_does_nothing(self, builder):
        """"A Swamp **you control**"."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["dread_presence", "plains"])
            .hand(0, [ANCHOR])
            .hand(1, ["swamp", ANCHOR])
            .battlefield(1, ["plains"])
            .active(1)
        ).build()
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 1)
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "swamp"))
        assert game.pending().kind is DecisionKind.PRIORITY
        assert not game.state.stack
        assert lives(game) == [START, START]


class TestEldritchPact:
    """"Target player draws X cards and loses X life, where X is the number of cards
    in their graveyard." """

    def test_x_is_the_targeted_player_s_graveyard_not_yours(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp"] * 7)
            .hand(0, ["eldritch_pact"])
            .graveyard(0, [BEAR])
            .graveyard(1, [BEAR] * 4)
        ).build()
        before = libraries(game)
        cast(game, "eldritch_pact", targets=(TargetRef.player(1),))
        assert drawn_since(before, game) == [0, 4]
        assert lives(game) == [START, START - 4]


class _DrawPinger:
    """"Whenever an opponent draws a card, [it] deals 1 damage to that player." """

    CARD = ""

    def test_an_opponent_takes_one_for_each_card_drawn(self, builder):
        game = opponent_draws_two(builder, self.CARD)
        assert lives(game) == [START, START - 2]

    def test_at_a_pod_only_the_one_who_drew(self, builder):
        game = opponent_draws_two(builder, self.CARD, players=3)
        assert lives(game) == [START, START - 2, START]

    def test_your_own_draws_are_free(self, builder):
        game = i_draw_two(builder, self.CARD)
        assert lives(game) == [START, START]

    def test_an_opponent_s_draw_step_costs_one(self, builder):
        game = between_turns(builder, ending=0, boards={0: [self.CARD]})
        _, life = through_upkeep_and_draw(game, 1)
        assert life == [0, -1]


class TestFateUnraveler(_DrawPinger):
    __doc__ = _DrawPinger.__doc__
    CARD = "fate_unraveler"


class TestUnderworldDreams(_DrawPinger):
    __doc__ = _DrawPinger.__doc__
    CARD = "underworld_dreams"


class _DiesAndReturns:
    """"Until end of turn, target creature gains 'When this creature dies, return it
    to the battlefield tapped under its owner's control with a +1/+1 counter on
    it.'" """

    CARD = ""

    def test_the_creature_comes_back_tapped_with_a_counter(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "mountain", BEAR])
            .hand(0, [self.CARD, BOLT])
        ).build()
        bear = only_oid(game, BEAR, 0)
        cast(game, self.CARD, targets=(TargetRef.obj(bear),))
        cast(game, BOLT, targets=(TargetRef.obj(bear),))

        back = only_oid(game, BEAR, 0)
        obj = game.state.objects[back]
        assert obj.tapped
        assert obj.counters.get("+1/+1") == 1
        assert pt(game, back) == (3, 3)

    def test_an_opponent_s_creature_returns_under_its_owner(self, builder):
        """"Under its **owner's** control" -- not the caster's."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "mountain"])
            .hand(0, [self.CARD, BOLT])
            .battlefield(1, [BEAR])
        ).build()
        bear = only_oid(game, BEAR, 1)
        cast(game, self.CARD, targets=(TargetRef.obj(bear),))
        cast(game, BOLT, targets=(TargetRef.obj(bear),))
        assert count_on_battlefield(game, BEAR, 1) == 1
        assert count_on_battlefield(game, BEAR, 0) == 0

    def test_it_lasts_only_until_end_of_turn(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "mountain", BEAR])
            .hand(0, [self.CARD, BOLT])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
        ).build()
        bear = only_oid(game, BEAR, 0)
        cast(game, self.CARD, targets=(TargetRef.obj(bear),))
        pass_until(game, lambda g: g.state.active_player == 1)
        cast(game, BOLT, targets=(TargetRef.obj(bear),))
        assert count_on_battlefield(game, BEAR) == 0


class TestFeignDeath(_DiesAndReturns):
    __doc__ = _DiesAndReturns.__doc__
    CARD = "feign_death"


class TestUndyingMalice(_DiesAndReturns):
    __doc__ = _DiesAndReturns.__doc__
    CARD = "undying_malice"


class TestFontOfMythos:
    """"At the beginning of each player's draw step, that player draws two additional
    cards." """

    def test_my_draw_step_draws_three_and_theirs_draws_me_nothing(self, builder):
        game = between_turns(builder, boards={0: ["font_of_mythos"]})
        assert through_draw_step(game, 0) == [3, 0]

    def test_an_opponent_s_draw_step_draws_them_three(self, builder):
        """"Each player's" -- and each draw step once, not once per player."""
        game = between_turns(builder, players=3, ending=0, boards={0: ["font_of_mythos"]})
        assert through_draw_step(game, 1) == [0, 3, 0]
        assert through_draw_step(game, 2) == [0, 0, 3]


class TestGeierReachSanitarium:
    """"{2}, {T}: Each player draws a card, then discards a card." """

    def test_each_player_draws_then_discards(self, builder):
        """Nobody's hand changes size; one card each goes from library to graveyard."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["geier_reach_sanitarium", "plains", "plains"])
            .hand(0, [BEAR])
        ).build()
        before = libraries(game)
        game.apply(activations(game, only_oid(game, "geier_reach_sanitarium", 0), 1)[0])
        settle(game)
        assert drawn_since(before, game) == [1, 1]
        assert [hand(game, 0), hand(game, 1)] == [2, 1]
        assert [len(p.graveyard) for p in game.state.players] == [1, 1]


class TestGixianPuppeteer:
    """"Whenever you draw your second card each turn, each opponent loses 2 life and
    you gain 2 life." / "When this creature dies, return another target creature card
    with mana value 3 or less from your graveyard to the battlefield." """

    def test_the_second_draw_fires_and_the_first_and_third_do_not(self, builder):
        """The draw step's card is the first: nothing. Divination then draws the
        second (fires) and the third (does not)."""
        game = anchored(
            builder(players=3)
            .battlefield(0, ["gixian_puppeteer", "island", "island", "island", "plains"])
            .hand(0, [DRAW_TWO, ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .battlefield(2, ["plains"])
            .hand(2, [ANCHOR])
            .active(2)
            .step(Step.END_STEP)
        ).build()
        to_step(game, Step.PRECOMBAT_MAIN, 0)
        assert lives(game) == [START, START, START], "the first card"
        cast(game, DRAW_TWO)
        assert lives(game) == [START + 2, START - 2, START - 2], "the second, and not the third"

    def test_an_opponent_s_second_card_does_not(self, builder):
        """"Whenever **you** draw"."""
        game = opponent_draws_two(builder, "gixian_puppeteer")
        assert lives(game) == [START, START]

    def die(self, builder, graveyard) -> tuple:
        """Bolt the Puppeteer over ``graveyard``, answering any target choice with the
        first card offered, and report what was offered."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["gixian_puppeteer", "mountain"])
            .hand(0, [BOLT])
            .graveyard(0, list(graveyard))
        ).build()
        pup = only_oid(game, "gixian_puppeteer", 0)
        wait_to_cast(game, BOLT, 0)
        game.apply(cast_line(game, BOLT, targets=(TargetRef.obj(pup),)))
        offered: set[str] = set()
        for _ in range(50):
            p = game.pending()
            if p.kind is DecisionKind.PRIORITY and not game.state.stack:
                break
            if p.kind is DecisionKind.CHOOSE_OBJECTS:
                offered |= {game.state.objects[o.ref.id].def_id for o in p.options if o.ref}
            game.apply(_default_answer(game, p))
        return game, pup, offered

    def test_dying_returns_a_small_creature_card(self, builder):
        game, pup, _ = self.die(builder, [BEAR])
        assert game.state.objects[pup].zone is Zone.GRAVEYARD
        assert count_on_battlefield(game, BEAR, 0) == 1

    def test_both_small_cards_are_offered_and_the_five_drop_is_not(self, builder):
        """"Mana value 3 or less"."""
        game, _, offered = self.die(builder, [BEAR, "grizzly_bears", BIG])
        assert offered == {BEAR, "grizzly_bears"}
        assert count_on_battlefield(game, BIG) == 0

    def test_a_lone_five_drop_stays_put(self, builder):
        game, _, _ = self.die(builder, [BIG])
        assert count_on_battlefield(game, BIG) == 0


class TestGreed:
    """"{B}, Pay 2 life: Draw a card." """

    def test_each_activation_costs_two_life_and_draws_one(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["greed", "swamp", "swamp"])).build()
        greed = only_oid(game, "greed", 0)
        before = library(game, 0)
        activate(game, greed, 0)
        activate(game, greed, 0)
        assert before - library(game, 0) == 2
        assert game.state.players[0].life == START - 4

    def test_at_one_life_it_cannot_be_paid(self, builder):
        """119.4: a player can pay life only if their total is at least the payment."""
        game = anchored(builder(players=2).battlefield(0, ["greed", "swamp"]).life(0, 1)).build()
        assert castable(game, ANCHOR), "stopped at my priority"
        assert not activations(game, only_oid(game, "greed", 0))

    def test_at_two_life_it_can(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["greed", "swamp"]).life(0, 2)).build()
        assert activations(game, only_oid(game, "greed", 0))

    def test_it_needs_black_mana(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["greed", "plains"])).build()
        assert castable(game, ANCHOR), "stopped at my priority"
        assert not activations(game, only_oid(game, "greed", 0))


class TestHowlingMine:
    """"At the beginning of each player's draw step, if this artifact is untapped,
    that player draws an additional card." """

    def test_untapped_each_player_draws_an_extra_card_on_their_own_draw_step(self, builder):
        game = between_turns(builder, ending=0, boards={0: ["howling_mine"]})
        assert through_draw_step(game, 1) == [0, 2]
        assert through_draw_step(game, 0) == [2, 0]

    def test_tapped_it_does_nothing(self, builder):
        """My Mine stays tapped through the opponent's untap step."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["howling_mine"], tapped=True)
            .battlefield(0, ["plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["plains"])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.END_STEP)
        ).build()
        assert through_draw_step(game, 1) == [0, 1]


class TestInfernalGrasp:
    """"Destroy target creature. You lose 2 life." """

    def test_it_destroys_a_black_creature_and_you_lose_the_life(self, builder):
        """Aimed at an opponent's black creature -- Snuff Out's near miss -- and the
        life is mine, not the creature's controller's."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "swamp"])
            .hand(0, ["infernal_grasp"])
            .battlefield(1, [BLACK_BEAR])
        ).build()
        victim = only_oid(game, BLACK_BEAR, 1)
        cast(game, "infernal_grasp", targets=(TargetRef.obj(victim),))
        assert game.state.objects[victim].zone is Zone.GRAVEYARD
        assert lives(game) == [START - 2, START]


class TestJetMedallion:
    """"Black spells you cast cost {1} less to cast."

    Each seat below also holds Defile, a {B} instant with a Bear to aim at, so the
    game stops at that seat's priority whether or not the spell under test is
    castable -- "not castable" is then a price, not an auto-pass.
    """

    def position(self, builder, *, medallion: int | None, pid: int, land: str, spell: str):
        b = builder(players=2).battlefield(0, [BEAR]).battlefield(pid, [land])
        if medallion is not None:
            b = b.battlefield(medallion, ["jet_medallion"])
        game = b.hand(pid, [spell, "defile"]).active(pid).build()
        assert castable(game, "defile") and game.pending().player == pid
        return game

    def test_a_two_mana_black_creature_off_one_swamp(self, builder):
        game = self.position(builder, medallion=0, pid=0, land="swamp", spell=BLACK_BEAR)
        assert castable(game, BLACK_BEAR)

    def test_without_it_one_swamp_is_not_enough(self, builder):
        """The control."""
        game = self.position(builder, medallion=None, pid=0, land="swamp", spell=BLACK_BEAR)
        assert not castable(game, BLACK_BEAR)

    def test_a_green_spell_is_not_discounted(self, builder):
        """"**Black** spells": a Bear off one Forest (and a Swamp's worth of nothing)."""
        game = (
            builder(players=2)
            .battlefield(0, ["jet_medallion", "forest", "swamp", BEAR])
            .hand(0, [BEAR, "defile"])
            .build()
        )
        assert castable(game, "defile")
        game.apply(cast_line(game, "defile"))
        settle(game)
        assert not castable(game, BEAR)

    def test_an_opponent_s_black_spell_is_not_discounted(self, builder):
        """"Spells **you** cast"."""
        game = self.position(builder, medallion=0, pid=1, land="swamp", spell=BLACK_BEAR)
        assert not castable(game, BLACK_BEAR)


class TestMasterOfTheFeast:
    """"At the beginning of your upkeep, each opponent draws a card." """

    def test_at_your_upkeep_each_opponent_draws(self, builder):
        game = between_turns(builder, players=3, ending=2, boards={0: ["master_of_the_feast"]})
        drawn, _ = through_upkeep_and_draw(game, 0)
        assert drawn == [1, 1, 1], "my draw step's card, and one each for them"

    def test_not_at_an_opponent_s_upkeep(self, builder):
        game = between_turns(builder, ending=0, boards={0: ["master_of_the_feast"]})
        drawn, _ = through_upkeep_and_draw(game, 1)
        assert drawn == [0, 1]


class TestMikokoroCenterOfTheSea:
    """"{2}, {T}: Each player draws a card." """

    def test_each_player_draws_one(self, builder):
        game = anchored(
            builder(players=3).battlefield(0, ["mikokoro_center_of_the_sea", "plains", "plains"])
        ).build()
        before = libraries(game)
        activate(game, only_oid(game, "mikokoro_center_of_the_sea", 0), 1)
        assert drawn_since(before, game) == [1, 1, 1]


class TestMutilate:
    """"All creatures get -1/-1 until end of turn for each Swamp you control." """

    def test_every_creature_shrinks_by_my_swamp_count(self, builder):
        """Three Swamps and a Blood Crypt: -4/-4 to mine and theirs alike. The
        opponent's five Swamps do not count, or the 5/5s would die too."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "swamp", "swamp", "blood_crypt", BIG])
            .hand(0, ["mutilate"])
            .battlefield(1, [BIG, BEAR] + ["swamp"] * 5)
        ).build()
        mine, theirs, bear = only_oid(game, BIG, 0), only_oid(game, BIG, 1), only_oid(game, BEAR, 1)
        cast(game, "mutilate")
        assert pt(game, mine) == (1, 1)
        assert pt(game, theirs) == (1, 1)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD


class TestObNixilisTheHateTwisted:
    """"Whenever an opponent draws a card, Ob Nixilis deals 1 damage to that player."
    / "-2: Destroy target creature. Its controller draws two cards." """

    def test_an_opponent_takes_one_for_each_card_drawn(self, builder):
        game = opponent_draws_two(builder, "ob_nixilis_the_hate_twisted")
        assert lives(game) == [START, START - 2]

    def test_your_own_draws_are_free(self, builder):
        game = i_draw_two(builder, "ob_nixilis_the_hate_twisted")
        assert lives(game) == [START, START]

    def test_minus_two_on_an_opponent_s_creature_draws_them_two_and_pings_twice(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["ob_nixilis_the_hate_twisted"])
            .battlefield(1, [BEAR])
        ).build()
        ob, bear = only_oid(game, "ob_nixilis_the_hate_twisted", 0), only_oid(game, BEAR, 1)
        before = libraries(game)
        activate(game, ob, 1, targets=(TargetRef.obj(bear),))
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert drawn_since(before, game) == [0, 2], "its controller draws, not me"
        assert lives(game) == [START, START - 2]
        assert game.state.objects[ob].counters["loyalty"] == 3

    def test_minus_two_on_your_own_creature_draws_you_two(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["ob_nixilis_the_hate_twisted", BEAR])
        ).build()
        ob, bear = only_oid(game, "ob_nixilis_the_hate_twisted", 0), only_oid(game, BEAR, 0)
        before = libraries(game)
        activate(game, ob, 1, targets=(TargetRef.obj(bear),))
        assert drawn_since(before, game) == [2, 0]
        assert lives(game) == [START, START]


class TestOtherworldAtlas:
    """"{T}: Put a charge counter on this artifact." / "{T}: Each player draws a card
    for each charge counter on this artifact." """

    def test_the_first_ability_adds_a_counter(self, builder):
        game = anchored(builder(players=2).battlefield(0, ["otherworld_atlas"])).build()
        atlas = only_oid(game, "otherworld_atlas", 0)
        activate(game, atlas, 0)
        assert game.state.objects[atlas].counters.get("charge") == 1
        assert game.state.objects[atlas].tapped

    def test_three_counters_draw_each_player_three(self, builder):
        game = anchored(
            builder(players=3).battlefield(0, ["otherworld_atlas"], counters={"charge": 3})
        ).build()
        atlas = only_oid(game, "otherworld_atlas", 0)
        before = libraries(game)
        activate(game, atlas, 1)
        assert drawn_since(before, game) == [3, 3, 3]
        assert game.state.objects[atlas].counters.get("charge") == 3, "the counters stay"

    def test_no_counters_draw_nothing(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["otherworld_atlas", "plains"]).hand(0, [ANCHOR])
        ).build()
        before = libraries(game)
        activate(game, only_oid(game, "otherworld_atlas", 0), 1)
        assert drawn_since(before, game) == [0, 0]


class TestPsychosisCrawler:
    """"Psychosis Crawler's power and toughness are each equal to the number of cards
    in your hand." / "Whenever you draw a card, each opponent loses 1 life." """

    def test_its_size_tracks_your_hand(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["psychosis_crawler", "island", "island", "island"])
            .hand(0, [DRAW_TWO, BEAR, BEAR])
            .hand(1, [BEAR] * 6)
        ).build()
        crawler = only_oid(game, "psychosis_crawler", 0)
        assert pt(game, crawler) == (4, 4), "my four cards, not their seven"
        cast(game, DRAW_TWO)
        assert pt(game, crawler) == (5, 5), "one cast, two drawn"

    def test_each_card_you_draw_costs_each_opponent_one(self, builder):
        game = i_draw_two(builder, "psychosis_crawler", players=3, hand_extra=[BEAR])
        assert lives(game) == [START, START - 2, START - 2]

    def test_an_opponent_drawing_costs_nobody_anything(self, builder):
        game = opponent_draws_two(builder, "psychosis_crawler", mine=[])
        assert lives(game) == [START, START]


class TestRankleMasterOfPranks:
    """"Whenever Rankle deals combat damage to a player, choose any number -- Each
    player discards a card. / Each player loses 1 life and draws a card. / Each player
    sacrifices a creature of their choice." """

    def attack(self, builder, modes: set[int]):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["rankle_master_of_pranks", BEAR, "plains"])
            .hand(0, [ANCHOR, BEAR])
            .battlefield(1, [BIG, "plains"])
            .hand(1, [ANCHOR, BEAR])
            .step(Step.UPKEEP)
        ).build()
        rankle = only_oid(game, "rankle_master_of_pranks", 0)
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
                if a.kind is ActionKind.ADD_ATTACKER and a.source == rankle
            )
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        pass_until(
            game, lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE
        )
        while (p := game.pending()) is not None and p.kind is DecisionKind.CHOOSE_MODE:
            left = [
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice in modes and a.choice not in p.selected
            ]
            if left:
                game.apply(left[0])
            else:
                game.apply(next(a for a in game.legal_actions() if a.kind is not ActionKind.CHOOSE))
        before = (libraries(game), lives(game), [hand(game, 0), hand(game, 1)])
        settle(game)
        return game, rankle, before

    def test_the_draw_mode_costs_everyone_one_and_draws_everyone_one(self, builder):
        game, _, (libs, life, _) = self.attack(builder, {1})
        assert drawn_since(libs, game) == [1, 1]
        assert [a - b for b, a in zip(life, lives(game), strict=True)] == [-1, -1]

    def test_the_discard_mode_hits_both_hands(self, builder):
        game, _, (_, _, hands) = self.attack(builder, {0})
        assert [hand(game, 0), hand(game, 1)] == [hands[0] - 1, hands[1] - 1]

    def test_the_sacrifice_mode_takes_a_creature_from_each_player(self, builder):
        game, _, _ = self.attack(builder, {2})
        assert count_on_battlefield(game, BIG, 1) == 0
        mine = count_on_battlefield(game, BEAR, 0) + count_on_battlefield(
            game, "rankle_master_of_pranks", 0
        )
        assert mine == 1, "I sacrifice one of my two creatures too"

    def test_choosing_nothing_does_nothing(self, builder):
        """"Choose any number" includes none: only the three combat damage lands."""
        game, _, (libs, _, hands) = self.attack(builder, set())
        assert lives(game) == [START, START - 3]
        assert drawn_since(libs, game) == [0, 0]
        assert [hand(game, 0), hand(game, 1)] == hands
        assert count_on_battlefield(game, BIG, 1) == 1


class TestScrawlingCrawler:
    """"At the beginning of your upkeep, each player draws a card." / "Whenever an
    opponent draws a card, that player loses 1 life." """

    def test_your_upkeep_draws_everyone_one_and_charges_only_them(self, builder):
        game = between_turns(builder, boards={0: ["scrawling_crawler"]})
        drawn, life = through_upkeep_and_draw(game, 0)
        assert drawn == [2, 1], "upkeep and draw step for me, upkeep for them"
        assert life == [0, -1]

    def test_an_opponent_s_turn_draws_nobody_extra(self, builder):
        """"**Your** upkeep" -- but their draw step still costs them one."""
        game = between_turns(builder, ending=0, boards={0: ["scrawling_crawler"]})
        drawn, life = through_upkeep_and_draw(game, 1)
        assert drawn == [0, 1]
        assert life == [0, -1]


class TestSeizanPerverterOfTruth:
    """"At the beginning of each player's upkeep, that player loses 2 life and draws
    two cards." """

    def test_my_upkeep_costs_me(self, builder):
        game = between_turns(builder, boards={0: ["seizan_perverter_of_truth"]})
        drawn, life = through_upkeep_and_draw(game, 0)
        assert drawn == [3, 0]
        assert life == [-2, 0]

    def test_their_upkeep_costs_them_not_me(self, builder):
        """"**That** player", not Seizan's controller."""
        game = between_turns(builder, ending=0, boards={0: ["seizan_perverter_of_truth"]})
        drawn, life = through_upkeep_and_draw(game, 1)
        assert drawn == [0, 3]
        assert life == [0, -2]


class TestSheoldredsEdict:
    """"Choose one -- Each opponent sacrifices a nontoken creature of their choice. /
    ... a creature token of their choice. / ... a planeswalker of their choice." """

    def position(self, builder, players: int = 2):
        b = (
            builder(players=players)
            .battlefield(0, ["swamp", "swamp", BEAR])
            .hand(0, ["sheoldred_s_edict"])
        )
        for pid in range(1, players):
            b = b.battlefield(pid, [BEAR, "t_walker"])
        game = b.build(advance=False)
        for pid in range(players):
            create_token(game.state, "soldier_1_1_w", pid)
        game.state.bump_chars()
        game._advance()
        return game

    def edict(self, game, mode: int) -> None:
        wait_to_cast(game, "sheoldred_s_edict", 0)
        game.apply(cast_line(game, "sheoldred_s_edict"))
        while (p := game.pending()) is not None and not (
            p.kind is DecisionKind.PRIORITY and not game.state.stack
        ):
            if p.kind is DecisionKind.CHOOSE_MODE:
                game.apply(next(a for a in game.legal_actions() if a.choice == mode))
            else:
                game.apply(_default_answer(game, p))

    def survivors(self, game, pid: int) -> set[str]:
        return {
            ("token" if o.is_token else o.def_id)
            for o in game.state.battlefield_objects(pid)
            if o.def_id not in ("swamp",)
        }

    def test_the_nontoken_mode_spares_the_token(self, builder):
        game = self.position(builder)
        self.edict(game, 0)
        assert self.survivors(game, 1) == {"token", "t_walker"}
        assert self.survivors(game, 0) == {"token", BEAR}, "each opponent, not me"

    def test_the_token_mode_spares_the_card(self, builder):
        game = self.position(builder)
        self.edict(game, 1)
        assert self.survivors(game, 1) == {BEAR, "t_walker"}

    def test_the_planeswalker_mode_spares_the_creatures(self, builder):
        game = self.position(builder)
        self.edict(game, 2)
        assert self.survivors(game, 1) == {BEAR, "token"}

    def test_every_opponent_at_a_pod(self, builder):
        game = self.position(builder, players=3)
        self.edict(game, 0)
        assert self.survivors(game, 1) == self.survivors(game, 2) == {"token", "t_walker"}


class TestSignInBlood:
    """"Target player draws two cards and loses 2 life." -- aimed at an opponent."""

    def test_an_opponent_draws_two_and_loses_two(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["swamp"] * 2).hand(0, ["sign_in_blood"])
        ).build()
        before = libraries(game)
        cast(game, "sign_in_blood", targets=(TargetRef.player(1),))
        assert drawn_since(before, game) == [0, 2]
        assert lives(game) == [START, START - 2]


class TestSnuffOut:
    """"If you control a Swamp, you may pay 4 life rather than pay this spell's mana
    cost." / "Destroy target nonblack creature. It can't be regenerated." """

    def test_four_life_and_a_swamp_cast_it_for_free(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp"])
            .hand(0, ["snuff_out"])
            .battlefield(1, [BEAR])
        ).build()
        bear, swamp = only_oid(game, BEAR, 1), only_oid(game, "swamp", 0)
        cast(game, "snuff_out", alternative=True, targets=(TargetRef.obj(bear),))
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.players[0].life == START - 4
        assert not game.state.objects[swamp].tapped

    def test_without_a_swamp_there_is_no_free_line(self, builder):
        """"If you control a **Swamp**": a Plains is not one, and the opponent's
        Swamp is not mine."""
        game = anchored(
            builder(players=2).hand(0, ["snuff_out"]).battlefield(1, [BEAR, "swamp"])
        ).build()
        assert castable(game, ANCHOR), "stopped at my priority"
        assert not castable(game, "snuff_out")

    def test_a_black_creature_is_not_a_target(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp"])
            .hand(0, ["snuff_out"])
            .battlefield(1, [BLACK_BEAR, BEAR])
        ).build()
        offered = {
            game.state.objects[t.id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == "snuff_out"
            for t in a.targets
        }
        assert offered == {BEAR}

    def test_a_regeneration_shield_does_not_save_it(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "forest", "t_regenerator"])
            .hand(0, ["snuff_out"])
        ).build()
        regen = only_oid(game, "t_regenerator", 0)
        activate(game, regen, 0)
        cast(game, "snuff_out", alternative=True, targets=(TargetRef.obj(regen),))
        assert game.state.objects[regen].zone is Zone.GRAVEYARD

    def test_the_control_infernal_grasp_is_regenerated_from(self, builder):
        """The same shield against a destroy that allows regeneration."""
        game = anchored(
            builder(players=2)
            .battlefield(0, ["swamp", "swamp", "forest", "t_regenerator"])
            .hand(0, ["infernal_grasp"])
        ).build()
        regen = only_oid(game, "t_regenerator", 0)
        activate(game, regen, 0)
        cast(game, "infernal_grasp", targets=(TargetRef.obj(regen),))
        assert game.state.objects[regen].zone is Zone.BATTLEFIELD


class TestTempleBell:
    """"{T}: Each player draws a card." """

    def test_each_player_draws_one(self, builder):
        game = anchored(builder(players=3).battlefield(0, ["temple_bell"])).build()
        before = libraries(game)
        activate(game, only_oid(game, "temple_bell", 0), 0)
        assert drawn_since(before, game) == [1, 1, 1]

    def test_once_a_turn(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["temple_bell", "plains"]).hand(0, [ANCHOR])
        ).build()
        bell = only_oid(game, "temple_bell", 0)
        activate(game, bell, 0)
        assert not activations(game, bell)


class TestVilisBrokerOfBlood:
    """"{B}, Pay 2 life: Target creature gets -1/-1 until end of turn." / "Whenever you
    lose life, draw that many cards. (Damage causes loss of life.)" """

    def test_the_activation_shrinks_a_creature_and_its_life_draws_two(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["vilis_broker_of_blood", "swamp"])
            .battlefield(1, [BEAR])
        ).build()
        vilis, bear = only_oid(game, "vilis_broker_of_blood", 0), only_oid(game, BEAR, 1)
        before = libraries(game)
        activate(game, vilis, 0, targets=(TargetRef.obj(bear),))
        assert pt(game, bear) == (1, 1)
        assert game.state.players[0].life == START - 2
        assert drawn_since(before, game) == [2, 0]

    def test_three_damage_draws_exactly_three(self, builder):
        game = anchored(
            builder(players=2)
            .battlefield(0, ["vilis_broker_of_blood", "plains"])
            .hand(0, [ANCHOR])
            .battlefield(1, ["mountain"])
            .hand(1, [BOLT])
            .active(1)
        ).build()
        before = libraries(game)
        cast(game, BOLT, pid=1, targets=(TargetRef.player(0),))
        assert game.state.players[0].life == START - 3
        assert drawn_since(before, game) == [3, 0]

    def test_an_opponent_losing_life_draws_nobody_anything(self, builder):
        """"Whenever **you** lose life"."""
        game = anchored(
            builder(players=2).battlefield(0, ["vilis_broker_of_blood", "mountain"]).hand(0, [BOLT])
        ).build()
        before = libraries(game)
        cast(game, BOLT, targets=(TargetRef.player(1),))
        assert game.state.players[1].life == START - 3
        assert drawn_since(before, game) == [0, 0]

    def test_gaining_life_draws_nothing(self, builder):
        game = anchored(
            builder(players=2).battlefield(0, ["vilis_broker_of_blood", "plains"]).hand(0, [ANCHOR])
        ).build()
        before = libraries(game)
        cast(game, ANCHOR)
        assert game.state.players[0].life == START + 1
        assert drawn_since(before, game) == [0, 0]
