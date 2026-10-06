"""The Lander Commander deck (Aesi, Tyrant of Gyre Strait): the two cards this
branch added, doing what they print.

Both cleared the six authoring gates, and both were measured by gate 5 at almost
nothing -- which is the gate's documented limit, not the cards':

- **Verdant Kraken** is an upkeep trigger, and the sandbox never reaches an
  upkeep. Its authored expectation is "it is on the battlefield".
- **Turntimber Symbiosis** looks at a sandbox library of basic lands, so the
  creature it may put onto the battlefield is never there; its expectation is
  "it resolved and found nothing". Its land face is a second face, which the
  gate never plays.

So these are the observations. Each pins the near miss as well: the Kraken's
token on an *opponent's* upkeep is still yours, and the Symbiosis' counters go
on a mana-value-3 creature and not a mana-value-4 one, and arrive with the card
in one placement rather than after it.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import _default_answer, action_for_card, oids_of, pass_until

AESI = "aesi_tyrant_of_gyre_strait"
KRAKEN = "verdant_kraken"
TENTACLE = "forest_tentacle_3_3_g_land"
SYMBIOSIS = "turntimber_symbiosis_turntimber_serpentine_wood"
WOOD = "turntimber_serpentine_wood"
BEAR = "t_bear"  # {1}{G} 2/2, mana value 2
BOUNDARY = "mossborn_hydra"  # {2}{G} 0/0 that enters with a +1/+1 counter: mana value 3
FOUR = "wickerbough_elder"  # {3}{G} 4/4 that enters with a -1/-1 counter: mana value 4
SCALES = "t_rc_scales"  # Hardened Scales: +1/+1 counters on your creatures, plus one
# A castable instant in each seat's hand: with no play available to anybody the
# engine's auto-pass runs whole turns inside one `apply` and overshoots the step
# under test.
ANCHOR = "t_plain_instant"


def tentacles(game, pid: int) -> list[int]:
    return oids_of(game, TENTACLE, pid)


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


class TestVerdantKraken:
    """"At the beginning of each player's upkeep, you create a 3/3 green Forest
    Tentacle land creature token. (It has "{T}: Add {G}." It's affected by
    summoning sickness until your next turn.)" """

    def upkeep(self, builder, *, whose: int, mine=(KRAKEN,)):
        """A main phase of the *other* seat's turn, passed to ``whose`` upkeep."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "plains", *mine])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(1 - whose)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(4)
            .build()
        )
        pass_until(game, lambda g: g.state.step is Step.UPKEEP and g.state.active_player == whose)
        answer(game)
        return game

    def test_your_upkeep_makes_one(self, builder):
        game = self.upkeep(builder, whose=0)
        assert len(tentacles(game, 0)) == 1

    def test_an_opponents_upkeep_makes_one_for_you(self, builder):
        """"Each player's upkeep" -- and "**you** create", so the active player
        is not who gets it."""
        game = self.upkeep(builder, whose=1)
        assert len(tentacles(game, 0)) == 1
        assert tentacles(game, 1) == []

    def test_the_token_is_a_three_three_forest_land_creature(self, builder):
        game = self.upkeep(builder, whose=0)
        [token] = tentacles(game, 0)
        c = chars(game.state, token)
        assert (c.power, c.toughness) == (3, 3)
        assert {"Land", "Creature"} <= set(c.types)
        assert {"Forest", "Tentacle"} <= set(c.subtypes)
        assert game.state.objects[token].is_token

    def test_summoning_sick_on_your_upkeep_not_after_an_opponents(self, builder):
        """The reminder text is the ordinary rule (302.6) applied to a land
        creature: made on your upkeep it cannot tap this turn; made on an
        opponent's it can by the time your turn comes."""
        game = self.upkeep(builder, whose=0)
        [mine] = tentacles(game, 0)
        assert game.state.objects[mine].summoning_sick(game.state.turn)

        game = self.upkeep(builder, whose=1)
        [made_on_theirs] = tentacles(game, 0)
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.step is Step.UPKEEP)
        assert not game.state.objects[made_on_theirs].summoning_sick(game.state.turn)

    def test_without_the_kraken_nothing(self, builder):
        game = self.upkeep(builder, whose=0, mine=())
        assert tentacles(game, 0) == []


class TestAesiMeetsTheKraken:
    """Aesi: "Landfall -- Whenever a land you control enters, you may draw a
    card." The Tentacle is a land, so every upkeep at the table draws Aesi's
    controller a card -- the reason the Kraken is in this list."""

    def test_an_opponents_upkeep_draws_you_a_card(self, builder):
        game = TestVerdantKraken().upkeep(builder, whose=1, mine=(KRAKEN, AESI))
        assert len(tentacles(game, 0)) == 1
        assert len(game.state.players[0].library) == 20 - 1
        assert len(game.state.players[1].library) == 20, "their draw step has not come yet"

    def test_the_draw_is_a_may(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest", KRAKEN, AESI])
            .battlefield(1, ["plains"])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(4)
            .build()
        )
        pass_until(game, lambda g: g.state.step is Step.UPKEEP and g.state.active_player == 1)
        library = len(game.state.players[0].library)
        answer(game, yes=False)
        assert len(tentacles(game, 0)) == 1
        assert len(game.state.players[0].library) == library


class TestTurntimberSymbiosis:
    """"Look at the top seven cards of your library. You may put a creature card
    from among them onto the battlefield. If that card has mana value 3 or less,
    it enters with three additional +1/+1 counters on it. Put the rest on the
    bottom of your library in a random order." """

    def cast(self, builder, top, *, mine=(), take: bool = True):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 7 + list(mine))
            .hand(0, [SYMBIOSIS])
            .hand(1, [ANCHOR])
            .library(0, [*top, *(["island"] * (10 - len(top)))])
            .library(1, ["forest"] * 20)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        looked = list(game.state.players[0].library[:7])
        game.apply(action_for_card(game, ActionKind.CAST, SYMBIOSIS))
        for _ in range(200):
            decision = game.pending()
            if decision is None or (
                decision.kind is DecisionKind.PRIORITY
                and not game.state.stack
                and not game.state.pending_triggers
            ):
                break
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                if take and decision.options:
                    game.apply(
                        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE)
                    )
                    continue
                done = next(
                    (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION),
                    None,
                )
                game.apply(done or _default_answer(game, decision))
                continue
            game.apply(_default_answer(game, decision))
        return game, looked

    def test_a_small_creature_enters_with_three(self, builder):
        game, (bear, *_rest) = self.cast(builder, [BEAR])
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].counters == {"+1/+1": 3}
        c = chars(game.state, bear)
        assert (c.power, c.toughness) == (5, 5)

    def test_mana_value_three_is_three_or_less(self, builder):
        """Mossborn Hydra prints one counter of its own: one plus three."""
        game, (hydra, *_rest) = self.cast(builder, [BOUNDARY])
        assert game.state.objects[hydra].counters == {"+1/+1": 4}

    def test_mana_value_four_gets_none(self, builder):
        """Wickerbough Elder enters with only its own -1/-1 counter."""
        game, (elder, *_rest) = self.cast(builder, [FOUR])
        assert game.state.objects[elder].zone is Zone.BATTLEFIELD
        assert game.state.objects[elder].counters.get("+1/+1", 0) == 0

    def test_the_kraken_itself_gets_none(self, builder):
        game, (kraken, *_rest) = self.cast(builder, [KRAKEN])
        assert game.state.objects[kraken].zone is Zone.BATTLEFIELD
        assert game.state.objects[kraken].counters == {}

    def test_one_placement_with_hardened_scales(self, builder):
        """(1 + 3) + 1 = 5 on Mossborn Hydra. Counters added after it entered
        would be two placements, (1 + 1) + (3 + 1) = 6."""
        game, (hydra, *_rest) = self.cast(builder, [BOUNDARY], mine=[SCALES])
        assert game.state.objects[hydra].counters == {"+1/+1": 5}

    def test_it_may_put_nothing(self, builder):
        game, looked = self.cast(builder, [BEAR], take=False)
        assert all(game.state.objects[o].zone is Zone.LIBRARY for o in looked)

    def test_the_rest_go_to_the_bottom(self, builder):
        game, (_bear, *rest) = self.cast(builder, [BEAR])
        library = game.state.players[0].library
        assert len(library) == 9
        assert set(library[-6:]) == set(rest), "the six not taken, under the three unseen"

    def test_the_sorcery_ends_in_the_graveyard(self, builder):
        game, _looked = self.cast(builder, [BEAR])
        assert any(
            game.state.objects[o].def_id == SYMBIOSIS for o in game.state.players[0].graveyard
        )


class TestTurntimberSerpentineWood:
    """"As this land enters, you may pay 3 life. If you don't, it enters tapped.
    {T}: Add {G}." -- the back face, played as a land drop."""

    def play(self, builder, *, pay: bool):
        game = builder(players=2).hand(0, [SYMBIOSIS]).build()
        [line] = [
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.second_face
        ]
        card = line.source
        game.apply(line)
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
            if p.kind is DecisionKind.MAY:
                want = ActionKind.YES if pay else ActionKind.NO
                game.apply(next(a for a in game.legal_actions() if a.kind is want))
                continue
            game.apply(_default_answer(game, p))
        return game, game.state.objects[card]

    def test_paying_three_life_enters_untapped(self, builder):
        game, wood = self.play(builder, pay=True)
        assert game.state.card_of(wood).id == WOOD
        assert wood.zone is Zone.BATTLEFIELD and not wood.tapped
        assert game.state.players[0].life == 37

    def test_declining_enters_tapped(self, builder):
        game, wood = self.play(builder, pay=False)
        assert wood.tapped
        assert game.state.players[0].life == 40

    def test_it_taps_for_green(self, builder):
        game, wood = self.play(builder, pay=True)
        mana = [a for a in game.state.card_of(wood).abilities if a.is_mana_ability]
        assert len(mana) == 1

