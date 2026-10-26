"""The Lander Commander deck (Aesi, Tyrant of Gyre Strait): the cards the gates
could not watch, doing what they print.

Each cleared the six authoring gates, and each was measured by gate 5 at almost
nothing -- which is the gate's documented limit, not the cards':

- **Verdant Kraken** is an upkeep trigger, and the sandbox never reaches an
  upkeep. Its authored expectation is "it is on the battlefield".
- **Turntimber Symbiosis** looks at a sandbox library of basic lands, so the
  creature it may put onto the battlefield is never there; its expectation is
  "it resolved and found nothing". Its land face is a second face, which the
  gate never plays.
- **Oboro, Palace in the Clouds** returns itself for {1}, an activated ability,
  and gate 5 never activates one.

So these are the observations. Each pins the near miss as well: the Kraken's
token on an *opponent's* upkeep is still yours, and the Symbiosis' counters go
on a mana-value-3 creature and not a mana-value-4 one, and arrive with the card
in one placement rather than after it; Oboro's return is refused with no mana
to pay it, and its replay spends a land drop.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.costs import mana_sources
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import (
    _default_answer,
    action_for_card,
    activations,
    count_on_battlefield,
    find_action,
    hand_ids,
    oids_of,
    only_oid,
    pass_until,
)

AESI = "aesi_tyrant_of_gyre_strait"
KRAKEN = "verdant_kraken"
TENTACLE = "forest_tentacle_3_3_g_land"
SYMBIOSIS = "turntimber_symbiosis_turntimber_serpentine_wood"
WOOD = "turntimber_serpentine_wood"
OBORO = "oboro_palace_in_the_clouds"
BOUNCE = 1  # "{1}: Return Oboro to its owner's hand."; 0 is its mana ability
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
        # Two land drops for the back face: paying is part of which drop you
        # make (`Action.enters_paid`), not a question asked during it.
        [line] = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND and a.second_face and a.enters_paid is pay
        ]
        card = line.source
        game.apply(line)
        while (p := game.pending()) is not None and p.kind is not DecisionKind.PRIORITY:
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



class TestOboroPalaceInTheClouds:
    """"{T}: Add {U}. {1}: Return Oboro to its owner's hand." -- a land that
    goes back to hand to be played again, so in this list it is a landfall
    trigger Aesi's extra drop can buy every turn."""

    # Two Plains: whichever pays the {1}, the other keeps the {W} anchor
    # castable, so the turn stays seat 0's after the return resolves.
    HELD = ("plains", "plains")

    def board(self, builder, *, mine=(), tapped: bool = False, played: int = 0):
        game = (
            builder(players=2)
            .battlefield(0, [OBORO, *mine])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .lands_played(0, played)
            .build()
        )
        oboro = only_oid(game, OBORO, 0)
        game.state.objects[oboro].tapped = tapped
        return game, oboro

    def bounce(self, game, oboro) -> None:
        [line] = activations(game, oboro, BOUNCE)
        game.apply(line)
        answer(game)

    def test_one_mana_returns_it_to_hand(self, builder):
        game, oboro = self.board(builder, mine=self.HELD)
        self.bounce(game, oboro)
        assert hand_ids(game, 0).count(OBORO) == 1
        assert oids_of(game, OBORO, 0) == []

    def test_it_pays_for_its_own_return(self, builder):
        """The return costs {1}, not {T}: Oboro alone can tap for the {U} that
        pays it -- the line that saves it from a land-destruction spell."""
        game, oboro = self.board(builder)
        self.bounce(game, oboro)
        assert hand_ids(game, 0).count(OBORO) == 1

    def test_tapped_and_alone_it_cannot(self, builder):
        """The near miss: with no mana anywhere the {1} is unpayable, so a
        bare `{T}`-free activation must still be refused."""
        game, oboro = self.board(builder, tapped=True)
        assert activations(game, oboro, BOUNCE) == []

    def test_replayed_it_is_a_land_drop_and_a_card_off_aesi(self, builder):
        """Returned and replayed, it enters again, so Aesi's landfall draws --
        and the replay spends a land drop like any other, which is why the
        deck wants Aesi's second one."""
        game, oboro = self.board(builder, mine=[*self.HELD, AESI])
        self.bounce(game, oboro)
        library, turn = len(game.state.players[0].library), game.state.turn
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, OBORO))
        answer(game)
        assert game.state.turn == turn, "a draw step would also shrink the library"
        assert len(oids_of(game, OBORO, 0)) == 1
        assert game.state.players[0].lands_played == 1
        assert len(game.state.players[0].library) == library - 1

    def test_with_the_drops_spent_it_stays_in_hand(self, builder):
        """Aesi's two drops both used: the return still works, the replay
        does not."""
        game, oboro = self.board(builder, mine=[*self.HELD, AESI], played=2)
        self.bounce(game, oboro)
        assert game.state.active_player == 0
        assert hand_ids(game, 0).count(OBORO) == 1
        assert [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND] == []


NISSA = "nissa_worldsoul_speaker"
VERGE = "willowrush_verge"


class TestWillowrushVerge:
    """"{T}: Add {U}. / {T}: Add {G}. Activate only if you control a Forest or
    an Island."

    Gate 5 never taps a land. The near misses are the condition's two halves:
    an unconditional {G} is a strictly better dual, and a `subtypes` read as
    "a Forest and an Island" is a strictly worse one.
    """

    @staticmethod
    def sources(builder, *others: str) -> set[int]:
        game = builder(players=2).battlefield(0, [VERGE, *others]).build(advance=False)
        verge = only_oid(game, VERGE)
        return {s.ability_index for s in mana_sources(game.state, 0) if s.oid == verge}

    def test_alone_it_makes_only_blue(self, builder):
        assert self.sources(builder) == {0}

    def test_a_plains_does_not_turn_on_green(self, builder):
        assert self.sources(builder, "plains") == {0}

    def test_a_forest_turns_on_green(self, builder):
        assert self.sources(builder, "forest") == {0, 1}

    def test_an_island_alone_is_enough(self, builder):
        assert self.sources(builder, "island") == {0, 1}

    def test_an_opponents_forest_is_not_yours(self, builder):
        game = builder(players=2).battlefield(0, [VERGE]).battlefield(1, ["forest"]).build(
            advance=False
        )
        verge = only_oid(game, VERGE)
        assert {s.ability_index for s in mana_sources(game.state, 0) if s.oid == verge} == {0}


class TestNissaWorldsoulSpeaker:
    """"Landfall — Whenever a land you control enters, you get {E}{E}. / You
    may pay eight {E} rather than pay the mana cost for permanent spells you
    cast."

    Neither line fires in gate 5's sandbox, where no land enters and nobody
    has energy. The near misses: a landfall reading any player's land, energy
    given to the wrong seat, and the alternative cost offered one short.
    """

    @staticmethod
    def board(builder, *, energy=0, hand=("forest",), theirs=()):
        b = (
            builder(players=2)
            .battlefield(0, [NISSA])
            .battlefield(1, list(theirs))
            .hand(0, list(hand))
            .hand(1, [ANCHOR])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
        )
        b.state.players[0].energy = energy
        return b.build()

    def test_a_land_you_play_gives_two_energy(self, builder):
        game = self.board(builder)
        game.apply(find_action(game, ActionKind.PLAY_LAND))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.players[0].energy == 2
        assert game.state.players[1].energy == 0

    def test_two_lands_are_four(self, builder):
        game = self.board(builder, energy=2)
        game.apply(find_action(game, ActionKind.PLAY_LAND))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.players[0].energy == 4

    def test_an_opponents_land_gives_nothing(self, builder):
        """"A land **you control**": the opponent plays one on their own turn."""
        game = (
            builder(players=2)
            .battlefield(0, [NISSA])
            .hand(1, ["forest"])
            .hand(0, [ANCHOR])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(1)
            .build()
        )
        game.apply(find_action(game, ActionKind.PLAY_LAND))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert count_on_battlefield(game, "forest", 1) == 1
        assert game.state.players[0].energy == 0
        assert game.state.players[1].energy == 0

    def test_eight_energy_casts_a_permanent_spell_for_no_mana(self, builder):
        game = self.board(builder, energy=8, hand=(BEAR,))
        line = next(
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.granted_cost
        )
        game.apply(line)
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[0].energy == 0
        assert count_on_battlefield(game, BEAR, 0) == 1

    def test_seven_is_one_short(self, builder):
        game = self.board(builder, energy=7, hand=(BEAR,))
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.granted_cost]

    def test_an_instant_is_not_a_permanent_spell(self, builder):
        game = self.board(builder, energy=8, hand=(ANCHOR,))
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.granted_cost]
